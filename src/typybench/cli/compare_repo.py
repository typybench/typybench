import argparse

import mypy.types
from loguru import logger

from ..repo_similarity import get_repo_similarity


def main(args):
    logger.info(f"Analyzing repo {args.a_repo_path} and repo {args.b_repo_path}")
    score_dict, (a_type_dict, a_stat), (b_type_dict, b_stat) = get_repo_similarity(
        a_repo_path=args.a_repo_path,
        b_repo_path=args.b_repo_path,
        return_type_dict=True,
        return_repo_stat=True,
    )
    for name, score in score_dict.items():
        if score == 1.0 and not args.verbose:
            continue
        a_type = a_type_dict[name]
        if name in b_type_dict:
            b_type = b_type_dict[name]
            logger.info(f"{name} ({a_type} <---> {b_type}): {score:.4f}")
        else:
            logger.info(f"{name} ({a_type} <---> [NotFound]]): {0:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("a_repo_path", type=str, help="path to the repo directory")
    parser.add_argument("b_repo_path", type=str, help="path to the repo directory")
    parser.add_argument(
        "--suffix",
        type=str,
        help="filename extension for finding python files in the repo",
        default=".py",
    )
    parser.add_argument("--verbose", action="store_true", help="enable verbose outputs")
    main(parser.parse_args())
