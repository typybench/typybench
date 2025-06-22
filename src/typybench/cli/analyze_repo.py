import requests
import ast
import json
from typing import List, Tuple, Optional
import os
import argparse

BASE_URL = "https://api.github.com"


def get_github_token(token: Optional[str] = None):
    if token is not None:
        return token
    return os.environ.get("GITHUB_TOKEN")


def extract_repo_info(repo_url: str) -> Tuple[str, str]:
    parts = repo_url.rstrip("/").split("/")
    owner = parts[-2]
    repo = parts[-1]
    return owner, repo


def get_files_in_directory(
    owner: str,
    repo: str,
    path: str = "",
    depth: int = 0,
    max_depth: int = 3,
    *,
    github_token: str,
) -> List[str]:
    url = f"{BASE_URL}/repos/{owner}/{repo}/contents/{path}"
    headers = {"Authorization": f"token {github_token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    items = response.json()

    files = []
    for item in items:
        if item["type"] == "file" and item["name"].endswith(".py"):
            files.append(item["path"])
        elif item["type"] == "dir" and depth < max_depth:
            files.extend(
                get_files_in_directory(
                    owner,
                    repo,
                    item["path"],
                    depth + 1,
                    max_depth,
                    github_token=github_token,
                )
            )

    return files


def fetch_file_content(
    owner: str, repo: str, file_path: str, *, github_token: str
) -> str:
    url = f"{BASE_URL}/repos/{owner}/{repo}/contents/{file_path}"
    headers = {"Authorization": f"token {github_token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    file_content = requests.get(response.json()["download_url"]).text
    return file_content


def count_functions_with_annotations(
    file_content: str, file_path: str
) -> Tuple[int, int, int, int, float, List[str], List[dict]]:
    tree = ast.parse(file_content)
    total_functions = 0
    annotated_functions = 0
    functions_with_defaults = 0
    total_annotations = 0
    function_names = []
    modified_functions = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            total_functions += 1
            function_names.append(node.name)
            has_annotation = False
            has_default = len(node.args.defaults) > 0
            annotations_count = sum(1 for arg in node.args.args if arg.annotation) + (
                1 if node.returns else 0
            )
            if annotations_count > 0:
                annotated_functions += 1
            total_annotations += annotations_count
            if has_default:
                functions_with_defaults += 1

            # Remove typing information and store the modified function
            modified_node = remove_typing_information(node)
            modified_functions.append(
                {
                    "name": node.name,
                    "modified_function": ast.unparse(modified_node),
                    "path": file_path,
                }
            )

    average_annotations = total_annotations / total_functions if total_functions else 0
    return (
        total_functions,
        annotated_functions,
        functions_with_defaults,
        total_annotations,
        average_annotations,
        function_names,
        modified_functions,
    )


def remove_typing_information(node: ast.FunctionDef) -> ast.FunctionDef:
    for arg in node.args.args:
        arg.annotation = None
    if node.returns:
        node.returns = None
    return node


def get_repo_details(owner: str, repo: str, *, github_token: str) -> dict:
    url = f"{BASE_URL}/repos/{owner}/{repo}"
    headers = {"Authorization": f"token {github_token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    repo_info = response.json()

    # Get the latest commit hash
    commits_url = f"{BASE_URL}/repos/{owner}/{repo}/commits"
    commits_response = requests.get(commits_url, headers=headers)
    commits_response.raise_for_status()
    latest_commit = commits_response.json()[0]["sha"]

    return {
        "stars": repo_info["stargazers_count"],
        "created_at": repo_info["created_at"],
        "updated_at": repo_info["updated_at"],
        "latest_commit": latest_commit,
    }


def analyze_repository(repo_url: str, *, github_token: str) -> dict:
    owner, repo = extract_repo_info(repo_url)
    try:
        repo_details = get_repo_details(owner, repo, github_token=github_token)
        files = get_files_in_directory(
            owner,
            repo,
            max_depth=1,
            github_token=github_token,
        )
        total_files = len(files)
        total_functions = 0
        total_annotated_functions = 0
        total_functions_with_defaults = 0
        total_annotations = 0
        all_function_names = []
        all_modified_functions = []

        for file_path in files:
            file_content = fetch_file_content(
                owner, repo, file_path, github_token=github_token
            )
            result = count_functions_with_annotations(file_content, file_path)
            (
                functions,
                annotated_functions,
                functions_with_defaults,
                annotations,
                average_annotations,
                function_names,
                modified_functions,
            ) = result
            total_functions += functions
            total_annotated_functions += annotated_functions
            total_functions_with_defaults += functions_with_defaults
            total_annotations += annotations
            all_function_names.extend(function_names)
            all_modified_functions.extend(modified_functions)

        average_annotations = (
            total_annotations / total_functions if total_functions else 0
        )

        return {
            "repository": repo_url,
            "stars": repo_details["stars"],
            "created_at": repo_details["created_at"],
            "updated_at": repo_details["updated_at"],
            "latest_commit": repo_details["latest_commit"],
            "total_files": total_files,
            "total_functions": total_functions,
            "total_annotated_functions": total_annotated_functions,
            "total_functions_with_defaults": total_functions_with_defaults,
            "average_annotations_per_function": average_annotations,
            "function_names": all_function_names,
            "modified_functions": all_modified_functions,
        }

    except requests.exceptions.HTTPError as err:
        return {"repository": repo_url, "error": str(err)}


def main(args):
    if args.github_token is not None:
        github_token = args.github_token
    else:
        github_token = os.environ.get("GITHUB_TOKEN", None)
    if github_token is None:
        raise ValueError(
            "Github Token is not specified (either via command line "
            "interface or the environment variable GITHUB_TOKEN)"
        )
    with open(args.input_file, "r") as reader:
        results = []
        for repo_url in reader:
            repo_url = repo_url.strip()
            if not repo_url:
                continue

            print(f"Analyzing repository: {repo_url}")
            result = analyze_repository(repo_url, github_token=github_token)
            results.append(result)

    with open(args.output_file, "w") as file:
        json.dump(results, file, indent=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input_file",
        type=str,
        required=True,
        help="path to a file of list of repositories to be analyzed",
    )
    parser.add_argument(
        "--output_file",
        type=str,
        required=True,
        help="path to the output file of repo statistics",
    )
    parser.add_argument(
        "--github_token",
        type=str,
        help="the github token for accessing the repositories",
    )
    main(parser.parse_args())
