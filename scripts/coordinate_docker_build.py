"""Coordinate stable image builds across workflows.

Example: python3 scripts/coordinate_docker_build.py key image/Dockerfile.v1
"""

import argparse
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import subprocess
import sys


def image_identity(dockerfile: str, repository: str) -> tuple[str, str]:
    """Derive the image repository and tag used by build-docker."""
    path = PurePosixPath(dockerfile)
    if (
        not dockerfile
        or path.is_absolute()
        or ".." in path.parts
        or "\n" in dockerfile
        or "\r" in dockerfile
    ):
        raise ValueError(f"Invalid Dockerfile path: {dockerfile!r}")
    if "." not in path.name:
        raise ValueError(f"Dockerfile has no tag: {dockerfile!r}")
    tag = path.name.split(".", 1)[1]
    if path.parent == PurePosixPath("."):
        owner, separator, repo = repository.partition("/")
        image = re.sub(r"[^a-z0-9]+", "-", repo.lower()).strip("-")
        if not owner or not separator or not image:
            raise ValueError("GITHUB_REPOSITORY must contain an owner and repository.")
    else:
        image = path.parent.name
    return image, tag


def image_key(dockerfile: str, repository: str) -> str:
    """Derive a lock key from the image repository and tag used by build-docker."""
    image, tag = image_identity(dockerfile, repository)
    identity = json.dumps([image.lower(), tag.lower()], separators=(",", ":"))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run Git with literal paths and report command failures."""
    env = os.environ.copy()
    env["GIT_LITERAL_PATHSPECS"] = "1"
    try:
        return subprocess.run(
            ["git", *args], check=check, capture_output=True, text=True, env=env
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"Git {' '.join(args)} failed: {error.stderr.strip()}") from error


def current_on_main(dockerfile: str, repository: str) -> bool:
    """Check that matching image build contexts have not changed since checkout."""
    key = image_key(dockerfile, repository)
    run_git("fetch", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main")
    ancestor = run_git("merge-base", "--is-ancestor", "HEAD", "origin/main", check=False)
    if ancestor.returncode not in (0, 1):
        raise RuntimeError(f"Cannot compare checkout with main: {ancestor.stderr.strip()}")
    if ancestor.returncode == 1:
        return False

    candidates = {str(PurePosixPath(dockerfile))}
    for revision in ("HEAD", "origin/main"):
        files = run_git("ls-tree", "-r", "-z", "--name-only", revision).stdout.split("\0")
        for file in files:
            if file and "." in PurePosixPath(file).name:
                if image_key(file, repository) == key:
                    candidates.add(file)
    paths = {str(PurePosixPath(file).parent) for file in candidates}
    diff = run_git("diff", "--quiet", "HEAD", "origin/main", "--", *sorted(paths), check=False)
    if diff.returncode not in (0, 1):
        raise RuntimeError(f"Cannot compare image files with main: {diff.stderr.strip()}")
    return diff.returncode == 0


def main() -> int:
    """Write a matrix, lock key, or stable-publication decision to GITHUB_OUTPUT."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("matrix", "key", "check"))
    parser.add_argument("dockerfile", nargs="?")
    args = parser.parse_args()
    try:
        repository = os.environ["GITHUB_REPOSITORY"]
        if args.command == "matrix":
            files = json.loads(os.environ["FILES_JSON"])
            if not isinstance(files, list) or not all(isinstance(file, str) for file in files):
                raise ValueError("FILES_JSON must be a list of Dockerfile paths.")
            value = json.dumps(
                [{"file": file, "key": image_key(file, repository)} for file in files]
            )
            name = "matrix"
        elif not args.dockerfile:
            raise ValueError("A Dockerfile path is required.")
        elif args.command == "key":
            name, value = "key", image_key(args.dockerfile, repository)
        else:
            name = "current"
            value = str(current_on_main(args.dockerfile, repository)).lower()
            if value == "false":
                print("::notice::Skipping superseded stable image build.")
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            print(f"{name}={value}", file=output)
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"::error::Cannot coordinate Docker build: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
