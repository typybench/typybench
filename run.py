import subprocess
import multiprocessing
import argparse
import os
import functools
import sys


def is_available_repo(root: str, name: str):
    return os.path.isdir(os.path.join(root, name)) and not name.startswith(".")


def evaluate_repo(path: str, uid: int, gid: int, user: str):
    repo = os.path.basename(path)

    commands = [
        "docker",
        "run",
        "-i",
    ]
    if sys.platform == "linux":
        commands.extend([f"--user", f"{uid}:{gid}"])
    commands.extend(
        [
            f"--rm",
            # fmt: off
            f"--mount", f"type=bind,source={os.path.realpath(path)},target=/mnt/{repo}",
            f"--security-opt", "seccomp:unconfined",
            # fmt: on
            f"typybench-{repo.lower()}",
        ]
    )

    pipe = subprocess.run(
        commands,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return dict(
        path=path,
        repo=repo,
        stderr=pipe.stderr,
        stdout=pipe.stdout,
        return_code=pipe.returncode,
        commands=pipe.args,
    )


def build_repo(repo: str, uid: int, gid: int, user: str, data_path: str):
    commands = [
        "docker",
        "build",
        # fmt: off
        f"--build-arg", f"REPO={repo}",
        f"--build-arg", f"BUILD_OS={sys.platform}",
        # fmt: on
    ]
    if sys.platform == "linux":
        commands.extend(
            [
                # fmt: off
                f"--build-arg", f"UID={uid}",
                f"--build-arg", f"GID={gid}",
                f"--build-arg", f"USER={user}",
                # fmt: on
            ]
        )
    else:
        commands.extend(
            [
                # fmt: off
                f"--build-arg", f"USER=root",
                # fmt: on
            ]
        )
    commands.extend(
        [
            f"--build-context",
            f"data={os.path.join(data_path, repo)}",
            f"-t",
            f"typybench-{repo.lower()}",
            f"{os.path.dirname(os.path.realpath(__file__))}",
        ]
    )
    pipe = subprocess.run(
        commands,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return dict(
        repo=repo,
        stderr=pipe.stderr,
        stdout=pipe.stdout,
        return_code=pipe.returncode,
        commands=pipe.args,
    )


def main(args):
    available_repos = [
        x for x in os.listdir(args.data_path) if is_available_repo(args.data_path, x)
    ]
    if args.repo is not None:
        if args.repo in available_repos:
            available_repos = [args.repo]
        else:
            raise RuntimeError(f"Repo {args.repo} is not found")

    if args.build:
        mapper = functools.partial(build_repo, data_path=args.data_path)
        enabled_repos = available_repos
    else:
        mapper = evaluate_repo
        enabled_repos = []
        for x in os.listdir(args.pred_path):
            if is_available_repo(args.pred_path, x):
                if x in available_repos:
                    enabled_repos.append(os.path.join(args.pred_path, x))
                else:
                    print(f"{x} is not found as a available repo")
    for x in enabled_repos:
        print(f"-> Found an available repo {x} to evaluate")

    mapper = functools.partial(mapper, uid=args.uid, gid=args.gid, user=args.user)
    with multiprocessing.Pool(processes=args.num_workers) as pool:
        key = "repo" if args.build else "path"
        for x in pool.imap_unordered(mapper, enabled_repos):
            if x["return_code"]:
                print(f"... Failure on {key} {x[key]}")
                print(f"... commands:\n{x['commands']}\n")
                print(f"... stdout:\n{x['stdout'].decode()}\n")
                print(f"... stderr:\n{x['stderr'].decode()}\n")
            else:
                print(f"... Finished {key} {x[key]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-path", type=str, required=True, help="path to the typybenchdata folder"
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=1,
        help="the number of parallel workers for speeding up evaluation",
    )
    parser.add_argument(
        "--uid", type=int, default=os.geteuid(), help="the current user id"
    )
    parser.add_argument(
        "--gid", type=int, default=os.getegid(), help="the current user group id"
    )
    parser.add_argument(
        "--user", type=str, default=os.getlogin(), help="the current user name"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--build", action="store_true", help="to build the docker image for evaluation"
    )
    group.add_argument(
        "--pred-path",
        type=str,
        help="to evaluate all repos under the given prediction path",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="specify a single repo to be evaluated (rather than evaluate all repos under the prediction path)",
    )
    main(parser.parse_args())
