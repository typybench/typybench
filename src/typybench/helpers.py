__all__ = ["get_type_dict_from_code", "get_type_dict_from_repo", "is_valid_python_file"]

import ast
import os
import pathlib
import shutil
import sys
import tempfile
from typing import Dict, Optional, List

import mypy.nodes
import mypy.types
from loguru import logger
from mypy import build
from mypy.build import BuildSource
from mypy.options import Options


def is_valid_python_code(code: str) -> bool:
    try:
        ast.parse(code)
    except SyntaxError:
        return False
    return True


def is_valid_python_file(path: str) -> bool:
    with open(path, "r") as reader:
        print("path:", path)
        return is_valid_python_code(reader.read())


def get_module_name_from_path(path: str) -> str:
    module_path, module_name = os.path.split(path)
    module = module_path.split(os.sep)
    module_name = os.path.splitext(module_name)[0]
    if module_name != "__init__":
        module.append(os.path.splitext(module_name)[0])
    # filter out empty module names
    module = filter(bool, module)
    return ".".join(module)


def remove_duplicated_files(paths: List[str]):
    """
    Remove duplicated python source files if there is a directory with the same name.
    For example, if we have the following directory structure:
    ```
    root/
      foo/
        __init__.py
      foo.py
      __init__.py
    ```
    Then `foo.py` will be discarded

    Or:

    ```
    root/
      test.pyi
      test.py
    ```
    Then only `test.py` will be kept
    """
    results = []
    for path in paths:
        dirname, basename = os.path.split(path)
        module, ext = os.path.splitext(basename)
        if basename != "__init__.py" and os.path.exists(
            os.path.join(dirname, module, "__init__.py")
        ):
            continue
        if ext == ".pyi" and os.path.exists(os.path.join(dirname, f"{module}.py")):
            continue
        results.append(path)
    return results


def filter_errors(error_data: dict):
    keep_keys = ["attr-defined", "assignment", "arg-type", "union-attr", "index"]
    filtered_keys = "others"
    keyword = "incompatible"

    # Initialize a new dictionary to hold the filtered data
    filtered_data = {}

    # Process each key-value pair in the original data
    for key, value in error_data.items():
        # If the key is one of the keys to keep, add it directly to the filtered data
        if key in keep_keys:
            for message in value["messages"]:
                if message.startswith("/tmp"):
                    if key not in filtered_data:
                        filtered_data[key] = {"count": 0, "messages": []}
                    filtered_data[key]["messages"].append(message)
                    filtered_data[key]["count"] += 1
        # Check the messages for the "incompatible" keyword and add them to "others"
        elif "messages" in value:
            for message in value["messages"]:
                if keyword in message and message.startswith("/tmp"):
                    if filtered_keys not in filtered_data:
                        filtered_data[filtered_keys] = {"count": 0, "messages": []}
                    filtered_data[filtered_keys]["messages"].append(message)
                    filtered_data[filtered_keys]["count"] += 1

    return filtered_data


def analyze_mypy_errors(errors: List[str]):
    # Expected mypy error format:
    # file_path:line_number: error: message [error-code]
    # Example:
    # src/module.py:10: error: Something went wrong [error-code]

    error_data = {}
    for line in errors:
        # Split the line into parts
        try:
            # Split by colon to separate file, line, and the rest
            file_part, line_part, error_part = line.split(":", 2)

            # Further split the error_part to get the message and error code
            if "error:" in error_part:
                _, message_with_code = error_part.split("error:", 1)
                message_with_code = message_with_code.strip()

                # Extract the error code within square brackets
                if "[" in message_with_code and message_with_code.endswith("]"):
                    message, error_code = message_with_code.rsplit("[", 1)
                    message = message.strip()
                    error_code = error_code[:-1]  # Remove the closing bracket
                else:
                    # If no error code is present, categorize under 'unknown'
                    message = message_with_code
                    error_code = "unknown"

                # Initialize the error type in the dictionary if not present
                if error_code not in error_data:
                    error_data[error_code] = {"count": 0, "messages": []}

                # Prepare the full error line
                full_error_line = (
                    f"{file_part}:{line_part}: error: {message} [{error_code}]"
                )

                # Increment the count and append the full error line
                error_data[error_code]["count"] += 1
                error_data[error_code]["messages"].append(full_error_line)
        except ValueError:
            # If the line doesn't match the expected format, skip it
            continue
    return error_data


def find_python_modules(repo_path: str, base_path: Optional[str] = None):
    if base_path is None:
        base_path = repo_path

    modules = dict()
    for path in os.listdir(repo_path):
        path = os.path.join(repo_path, path)
        if os.path.isdir(path):
            if os.path.exists(os.path.join(path, "__init__.py")):
                python_code_files = list(map(str, pathlib.Path(path).rglob("*.py")))
                python_stub_files = list(map(str, pathlib.Path(path).rglob("*.pyi")))
                modules[path] = remove_duplicated_files(
                    python_code_files + python_stub_files
                )
            else:
                modules.update(find_python_modules(path, base_path=base_path))
        elif os.path.splitext(path)[1] in (".py", ".pyi"):
            modules[path] = [path]
    return modules


def is_submodule(a: str, b: str):
    a = a.split(".")
    b = b.split(".")

    for i, e in enumerate(b):
        if i >= len(a) or e != a[i]:
            return False
    return True


def get_type_dict_from_repo(repo_path: str, return_stat: bool = False):
    python_modules = find_python_modules(repo_path)
    python_files = []
    valid_python_files = []

    with tempfile.TemporaryDirectory() as temp_dir:
        sources = []
        for module_path, file_paths in python_modules.items():
            for path in map(str, file_paths):
                relpath = os.path.relpath(path, repo_path)
                module = get_module_name_from_path(relpath)
                if module.startswith("."):  # ignore any packages start with a dot
                    continue

                python_files.append(path)
                if not is_valid_python_file(path):
                    logger.warning(
                        f"Ignore file {path} as it is not a valid python file"
                    )
                    continue

                temp_path = os.path.join(temp_dir, relpath)
                os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                shutil.copyfile(path, temp_path)
                source = BuildSource(path=temp_path, module=module, base_dir=temp_dir)
                sources.append(source)

        options = Options()
        options.no_site_packages = True
        options.no_silence_site_packages = True
        options.incremental = False
        while True:
            try:
                result = build.build(sources=sources, options=options)
                break
            except mypy.build.CompileError as e:
                path_to_delete = dict()
                for x in e.messages:
                    path, line, *_ = x.split(":")
                    if path.startswith("/tmp"):
                        path = os.path.relpath(path, temp_dir)
                        path_to_delete[path] = x
                for path, message in path_to_delete.items():
                    found = False
                    for i in range(len(sources)):
                        source_path = os.path.relpath(sources[i].path, temp_dir)
                        if source_path == path:
                            logger.warning(
                                f"Ignore file {path} "
                                f"as it compiles with error: {message}"
                            )
                            os.remove(os.path.join(temp_dir, path))
                            sources.pop(i)
                            found = True
                            break
                    if not found:
                        raise FileNotFoundError(
                            f"Cannot find the corresponding file to delete: {os.path.join(temp_dir, path)}"
                        ) from e

        for source in sources:
            valid_python_files.append(
                os.path.join(repo_path, os.path.relpath(source.path, temp_dir))
            )

    errors = dict()
    if result.errors:
        errors = "\n".join(result.errors)
        logger.debug(f"==> Repo Path: {repo_path} Errors:\n{errors}")
        errors = analyze_mypy_errors(result.errors)

    type_info = {}
    for m in result.files.values():
        type_info.update(get_type_dict_from_symbol_table(m.names))

    repo_modules = [
        get_module_name_from_path(os.path.relpath(m, repo_path)) for m in python_modules
    ]
    modules = list(type_info.keys())
    for key in modules:
        module = key
        module = module.split("::")[0]
        module = module.split("@")[0]
        if module.split(".")[-1] in (
            "__name__",
            "__doc__",
            "__file__",
            "__package__",
            "__spec__",
            "__annotations__",
            "__path__",
            "__match_args__",
            "__dataclass_fields__",
        ):
            type_info.pop(key)
            continue

        is_repo_module = False
        for repo_module in repo_modules:
            if is_submodule(module, repo_module):
                is_repo_module = True
                break
        if not is_repo_module:
            type_info.pop(key)

    if return_stat:

        def count_errors(e):
            r = 0
            for x in e.values():
                r += x["count"]
            return r

        filtered_errors = filter_errors(errors)
        stat = {
            "python_files": python_files,
            "valid_python_files": valid_python_files,
            "invalid_python_files": [
                path for path in python_files if path not in valid_python_files
            ],
            "errors": errors,
            "errors_count": count_errors(filtered_errors),
            "filtered_errors": filtered_errors,
            "filtered_errors_count": count_errors(filtered_errors),
        }
        return type_info, stat
    else:
        return type_info


def get_type_dict_from_code(code: str):
    sources = [BuildSource("main", "__main__", text=code)]
    options = Options()
    options.modules = list(sys.modules.values())
    result = build.build(sources=sources, options=options)
    type_info = {}
    for module in result.files.values():
        if module.name == "__main__":
            type_info.update(get_type_dict_from_symbol_table(module.names))
    return type_info


def get_type_dict_from_symbol_table(table: Dict[str, mypy.nodes.SymbolTableNode]):
    type_info = {}
    for name, node in table.items():
        if isinstance(node.node, mypy.nodes.TypeInfo):  # A new class
            type_info.update(get_type_dict_from_symbol_table(node.node.names))
        elif isinstance(node.node, mypy.nodes.Var) and node.node.type is not None:
            type_info[node.fullname] = node.node.type
        elif isinstance(node.node, mypy.nodes.FuncDef):
            if hasattr(node.node, "arguments"):
                for arg in node.node.arguments:
                    arg = arg.variable
                    if arg.type is None:
                        continue
                    type_info[f"{node.fullname}@{arg.name}"] = arg.type
            elif node.node.type is not None:
                for arg_name, arg_type in zip(
                    node.node.arg_names, node.node.type.arg_types
                ):
                    type_info[f"{node.fullname}@{arg_name}"] = arg_type

            if node.node.type is not None:
                type_info[f"{node.fullname}::return"] = node.node.type.ret_type
        elif isinstance(node.node, mypy.nodes.TypeAlias):
            type_info[node.fullname] = node.node.target
        elif isinstance(
            node.node,
            (
                mypy.nodes.Decorator,
                mypy.nodes.OverloadedFuncDef,
                mypy.nodes.TypeVarExpr,
                mypy.nodes.ParamSpecExpr,
                mypy.nodes.TypeVarTupleExpr,
            ),
        ):
            pass
        elif isinstance(node.node, mypy.nodes.MypyFile):
            pass
        else:
            logger.warning(
                f"Ignore Mypy Node: {type(node.node)}\n"  #
                f"  Fullname: {node.fullname}"
            )
    return type_info
