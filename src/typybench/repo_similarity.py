__all__ = [
    "get_repo_similarity",
]

import dataclasses
import os.path
from typing import Optional

import mypy.types

from .helpers import *
from .type_similarity import *


@dataclasses.dataclass
class RepoSimilarity:
    score_dict: dict
    exact_match_score_dict: dict
    a_meta_dict: dict
    b_meta_dict: dict
    a_repo_stat: dict
    b_repo_stat: dict
    missing_vars: set


def compare_type_info(a_type_dict, b_type_dict, baseline_type_dict):
    score_dict = {}
    exact_match_score_dict = {}
    a_meta_dict = {}
    b_meta_dict = {}
    missing_vars = set()
    for var_name in a_type_dict:
        if isinstance(a_type_dict[var_name], mypy.types.AnyType):
            continue
        if var_name in baseline_type_dict and not isinstance(
            baseline_type_dict[var_name], mypy.types.AnyType
        ):
            continue

        try:
            a_meta_dict[var_name] = get_mypy_type_meta(a_type_dict[var_name])
        except SkippedType:
            continue

        var_name_in_b_dict = False
        try:
            if var_name in b_type_dict:
                b_meta_dict[var_name] = get_mypy_type_meta(b_type_dict[var_name])
                var_name_in_b_dict = True
        except SkippedType:
            pass

        if var_name_in_b_dict:
            var_score = get_type_similarity(
                a_type=a_type_dict[var_name], b_type=b_type_dict[var_name]
            )
            score_dict[var_name] = var_score
            exact_match_score_dict[var_name] = int(
                str(a_type_dict[var_name]) == str(b_type_dict[var_name])
            )
        else:
            score_dict[var_name] = 0
            exact_match_score_dict[var_name] = 0
            missing_vars.add(var_name)

    return score_dict, exact_match_score_dict, a_meta_dict, b_meta_dict, missing_vars


def get_repo_similarity(
    a_repo_path: str,
    b_repo_path: str,
    base_line_repo_path: Optional[str] = None,
):
    if os.path.basename(a_repo_path) != "original_repo":
        raise RuntimeError("Cannot infer the baseline repo")
    if base_line_repo_path is None:
        base_line_repo_path = os.path.join(
            os.path.dirname(a_repo_path), "repo_without_types"
        )

    if os.path.isdir(os.path.join(a_repo_path, "src")):
        a_repo_path = os.path.join(a_repo_path, "src")
    if os.path.isdir(os.path.join(a_repo_path, "lib")):
        a_repo_path = os.path.join(a_repo_path, "lib")

    if os.path.isdir(os.path.join(b_repo_path, "src")):
        b_repo_path = os.path.join(b_repo_path, "src")
    if os.path.isdir(os.path.join(b_repo_path, "lib")):
        b_repo_path = os.path.join(b_repo_path, "lib")

    a_type_dict, a_repo_stat = get_type_dict_from_repo(
        repo_path=a_repo_path, return_stat=True
    )
    b_type_dict, b_repo_stat = get_type_dict_from_repo(
        repo_path=b_repo_path, return_stat=True
    )
    baseline_type_dict = get_type_dict_from_repo(repo_path=base_line_repo_path)
    score_dict, exact_match_score_dict, a_meta_dict, b_meta_dict, missing_vars = (
        compare_type_info(
            a_type_dict=a_type_dict,
            b_type_dict=b_type_dict,
            baseline_type_dict=baseline_type_dict,
        )
    )

    result = RepoSimilarity(
        score_dict=score_dict,
        exact_match_score_dict=exact_match_score_dict,
        a_meta_dict=a_meta_dict,
        b_meta_dict=b_meta_dict,
        a_repo_stat=a_repo_stat,
        b_repo_stat=b_repo_stat,
        missing_vars=missing_vars,
    )
    return result
