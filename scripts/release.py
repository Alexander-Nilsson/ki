#!/usr/bin/env python3
"""Bump version, build, tag, and push.

Usage: python scripts/release.py [--push]
"""

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_new_version() -> str:
    with open(REPO_ROOT / "pyproject.toml", "rb") as f:
        v = tomllib.load(f)["project"]["version"].split(".")
    v[-1] = str(int(v[-1]) + 1)
    return ".".join(v)


def update_version_in_files(version: str) -> None:
    pattern = re.compile(r'^version = ".*"', re.MULTILINE)
    for path in ["pyproject.toml", "anki_git/__init__.py"]:
        full = REPO_ROOT / path
        content = full.read_text()
        content = pattern.sub(f'version = "{version}"', content)
        full.write_text(content)
        print(f"  Updated {path}")


def run(*args: str) -> None:
    print(f"  $ {' '.join(args)}")
    subprocess.run(args, cwd=REPO_ROOT, check=True)


def main() -> None:
    version = get_new_version()
    print(f"Bumping to v{version}")

    update_version_in_files(version)

    run(sys.executable, "build.py", "all")

    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "github-actions[bot]@users.noreply.github.com")

    run("git", "add", "pyproject.toml", "anki_git/__init__.py")
    run("git", "commit", "-m", f"Bump version to {version} [skip ci]")

    # Delete local tag if it exists, then create anew
    subprocess.run(["git", "tag", "-d", f"v{version}"], cwd=REPO_ROOT, capture_output=True)
    run("git", "tag", f"v{version}")

    if "--push" in sys.argv:
        run("git", "push", "origin", "main", f"+refs/tags/v{version}")

    # GitHub Actions output
    if github_output := os.environ.get("GITHUB_OUTPUT"):
        with open(github_output, "a") as f:
            f.write(f"version={version}\n")
            f.write(f"tag=v{version}\n")

    print(f"\nDone. version={version}, tag=v{version}")


if __name__ == "__main__":
    main()
