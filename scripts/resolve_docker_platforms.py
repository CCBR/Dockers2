"""Resolve target platforms from a Dockerfile or an explicit override."""

import argparse
import os
from pathlib import Path
import re
import sys


def resolve_platforms(dockerfile: Path, override: str = "") -> str:
    declarations = re.findall(
        r"^[ \t]*#[ \t]*build-platforms:(.*)$", dockerfile.read_text(), re.MULTILINE
    )
    override = "".join(override.split())
    if override:
        platforms = override
    elif len(declarations) > 1:
        raise ValueError(f"{dockerfile} must contain at most one build-platforms declaration.")
    else:
        platforms = "".join(declarations[0].split()) if declarations else ""
        # An absent or empty declaration uses the default platform.
        platforms = platforms or "linux/amd64"

    selected = platforms.split(",")
    # buildx validates platform support; this only rejects malformed entries.
    if not all(
        re.fullmatch(r"[a-z0-9_]+/[a-z0-9_]+(/[a-z0-9_]+)?", platform) for platform in selected
    ):
        raise ValueError(
            f"Malformed platform selection for {dockerfile}: {platforms}. "
            "Use comma-separated os/arch[/variant] values, e.g. linux/amd64,linux/arm64."
        )
    if len(set(selected)) != len(selected):
        raise ValueError(f"Duplicate platforms in the platform selection for {dockerfile}.")
    return platforms


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dockerfile", type=Path)
    parser.add_argument("--platforms", default="")
    args = parser.parse_args()
    try:
        platforms = resolve_platforms(args.dockerfile, args.platforms)
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write(f"platforms={platforms}\n")
    except (OSError, ValueError) as error:
        sys.exit(f"::error::{error}")
    print(f"Building {args.dockerfile} for: {platforms}")


if __name__ == "__main__":
    main()
