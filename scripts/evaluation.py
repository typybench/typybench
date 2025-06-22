# usage: python evaluation.py -n <the_repo_name> -p <the_prediction_path_by_model_name>
#
import os
from argparse import ArgumentParser
from collections import defaultdict

import numpy as np
import pandas as pd
import pickle

from typybench.repo_similarity import get_repo_similarity

import collections


def compute_consistency_score(num_errors, num_vars):
    return np.exp(-num_errors / num_vars * 10)


def compute_consistency_score(num_errors, num_vars):
    return np.exp(-num_errors / num_vars * 10)


def get_data_by_dict(score_dict, result):
    """Assuming we get the score dictionary along with the result data itself
    score dict can be either from result.score_dict or result.exact_match_score_dict
    """

    missing_vars = result.missing_vars

    repo_overall_score = sum(score_dict.values()) / len(score_dict)
    print("length of score_dict:", len(score_dict))
    print("missing vars:", len(missing_vars))
    print("missing variables are:")
    for item in missing_vars:
        print(item)

    if len(score_dict) != len(missing_vars):
        repo_overall_score_wo_missing = (
            repo_overall_score * len(score_dict) / (len(score_dict) - len(missing_vars))
        )
    else:
        repo_overall_score_wo_missing = 0

    score_by_depth = defaultdict(list)
    # collect occurance of each type
    type_to_scores = defaultdict(list)
    for var_name, score in score_dict.items():
        type_meta_data = result.a_meta_dict[var_name]
        depth = min(type_meta_data.depth, 5)
        score_by_depth[depth].append(score)
        # meta data contains "mypy_type"
        # take the string representation of the mypy_type to be the type lable
        type_label = str(type_meta_data.mypy_type)
        type_to_scores[type_label].append(score)

    # Get the type label with count lower than 5
    # and get the average score of these types
    type_to_count = {k: len(v) for k, v in type_to_scores.items()}
    # filter out the labels with count less than 5
    lower_than_5 = [k for k, v in type_to_count.items() if v < 5]
    lower_than_5_average = sum(
        [
            sum(type_to_scores[type_label]) / len(type_to_scores[type_label])
            for type_label in lower_than_5
        ]
    ) / len(lower_than_5)
    # filter out the labels with count less than 10
    lower_than_10 = [k for k, v in type_to_count.items() if v < 10]
    lower_than_10_average = sum(
        [
            sum(type_to_scores[type_label]) / len(type_to_scores[type_label])
            for type_label in lower_than_10
        ]
    ) / len(lower_than_10)

    return (
        repo_overall_score,
        repo_overall_score_wo_missing,
        score_by_depth,
        lower_than_5_average,
        lower_than_10_average,
    )


def get_average_score(scores):
    if len(scores) == 0:
        return "N/A"
    return sum(scores) / len(scores)


def evaluate(path_to_repo, path_to_pred_folder):
    filename_result = os.path.join(args.pred_path, f"{args.repo_name}_result_dict.pkl")

    if os.path.exists(filename_result):
        print(f"Result exists, reading...")
        with open(filename_result, "rb") as file1:
            data = pickle.load(file1)
        result = data["result"]

        score_dict = result.score_dict
        missing_vars = result.missing_vars
        exact_score_dict = result.exact_match_score_dict

        repo_overall_score = data["repo_overall_score"]
        repo_overall_score_wo_missing = data["repo_overall_score_wo_missing"]
        c = data["c"]
        repo_overall_score_exact = data["repo_overall_score_exact"]
        repo_overall_score_wo_missing_exact = data["repo_overall_score_wo_missing"]
        c_exact = data["c_exact"]
        lower_than_5_average = data["lower_than_5_average"]
        lower_than_10_average = data["lower_than_10_average"]
        lower_than_5_average_exact = data["lower_than_5_average_exact"]
        lower_than_10_average_exact = data["lower_than_10_average_exact"]
    else:
        print(f"Analyzing results...")
        result = get_repo_similarity(
            path_to_repo,
            path_to_pred_folder,
            base_line_repo_path=None,
        )

        score_dict = result.score_dict
        missing_vars = result.missing_vars
        exact_score_dict = result.exact_match_score_dict
        (
            repo_overall_score,
            repo_overall_score_wo_missing,
            c,
            lower_than_5_average,
            lower_than_10_average,
        ) = get_data_by_dict(score_dict, result)
        (
            repo_overall_score_exact,
            repo_overall_score_wo_missing_exact,
            c_exact,
            lower_than_5_average_exact,
            lower_than_10_average_exact,
        ) = get_data_by_dict(exact_score_dict, result)

        # We do not store meta dict as they cannot be pickled
        # Instead we store analyzed score dict (i.e. repo_overall_score ...)
        result.a_meta_dict.clear()
        result.b_meta_dict.clear()

        print("Saving Results...")
        with open(filename_result, "wb") as f1:
            pickle.dump(
                {
                    "result": result,
                    "repo_overall_score": repo_overall_score,
                    "repo_overall_score_wo_missing": repo_overall_score_wo_missing,
                    "c": c,
                    "repo_overall_score_exact": repo_overall_score_exact,
                    "repo_overall_score_wo_missing_exact": repo_overall_score_wo_missing_exact,
                    "c_exact": c_exact,
                    "lower_than_5_average": lower_than_5_average,
                    "lower_than_10_average": lower_than_10_average,
                    "lower_than_5_average_exact": lower_than_5_average_exact,
                    "lower_than_10_average_exact": lower_than_10_average_exact,
                },
                f1,
            )

    print(
        "inconsistency_score",
        compute_consistency_score(
            result.a_repo_stat["filtered_errors_count"], len(score_dict)
        ),
        compute_consistency_score(
            result.b_repo_stat["filtered_errors_count"], len(score_dict)
        ),
    )
    print(
        f"Average similarity score for the entire repo is {repo_overall_score} and missing vars is {len(missing_vars)} total is {len(score_dict)}\n"
        f"Average similarity score for the entire repo without counting missing vars is {repo_overall_score_wo_missing}"
    )

    for depth, scores in sorted(c.items()):
        print(
            f"Depth {depth} has {len(scores)} variables with average similarity score {get_average_score(scores)}"
        )

    print(
        f"Average exact score for the entire repo is {repo_overall_score_exact} and missing vars is {len(missing_vars)} total is {len(exact_score_dict)}\n"
        f"Average exact score for the entire repo without counting missing vars is {repo_overall_score_wo_missing_exact}"
    )
    for depth, scores in sorted(c_exact.items()):
        print(
            f"Depth {depth} has {len(scores)} variables with average exact score {get_average_score(scores)}"
        )

    df = pd.DataFrame(
        {
            "repo_name": [args.repo_name],
            "total_vars": [len(score_dict)],
            "overall_score": [repo_overall_score],
            "overall_score_wo_missing": [repo_overall_score_wo_missing],
            "overall_score_exact": [repo_overall_score_exact],
            "overall_score_wo_missing_exact": [repo_overall_score_wo_missing_exact],
            "missing_ratio": [len(missing_vars) / len(score_dict)],
            "depth_1_score": [get_average_score(c[1])],
            "depth_2_score": [get_average_score(c[2])],
            "depth_3_score": [get_average_score(c[3])],
            "depth_4_score": [get_average_score(c[4])],
            "depth_5_score": [get_average_score(c[5])],
            "depth_1_score_exact": [get_average_score(c_exact[1])],
            "depth_2_score_exact": [get_average_score(c_exact[2])],
            "depth_3_score_exact": [get_average_score(c_exact[3])],
            "depth_4_score_exact": [get_average_score(c_exact[4])],
            "depth_5_score_exact": [get_average_score(c_exact[5])],
            "repo_a_consistency": [result.a_repo_stat["filtered_errors_count"]],
            "repo_b_consistency": [result.b_repo_stat["filtered_errors_count"]],
            "lower_than_5_average": [lower_than_5_average],
            "lower_than_10_average": [lower_than_10_average],
            "lower_than_5_average_exact": [lower_than_5_average_exact],
            "lower_than_10_average_exact": [lower_than_10_average_exact],
        }
    )
    output_file = os.path.join(args.pred_path, f"{args.repo_name}_results_w_exact.csv")
    df.to_csv(output_file, index=False, float_format=lambda x: f"{x:.4f}")
    print(f"Result is saved to {output_file}")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-n", "--repo-name", type=str, help="the name of the repo", required=True
    )
    parser.add_argument(
        "-d",
        "--data-path",
        type=str,
        help="the path to the data",
        default="../typybenchdata",
    )
    parser.add_argument(
        "-p",
        "--pred-path",
        type=str,
        help="the path to the prediction directory by model name",
    )

    args = parser.parse_args()
    args.data_path = os.path.join(args.data_path, args.repo_name)
    args.repo_path = os.path.join(args.data_path, "original_repo")
    if args.pred_path is None:
        args.pred_path = args.repo_path
    else:
        args.pred_path = os.path.join(args.pred_path, args.repo_name)
    evaluate(args.repo_path, args.pred_path)
