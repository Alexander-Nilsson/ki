#!/usr/bin/env python3
"""Release automation for AnkiGit.

Usage:
  python scripts/release.py 0.2.0

This will:
  1. Update version in pyproject.toml and anki_git/__init__.py
  2. Commit the version change
  3. Create and push a git tag
  4. GitHub Actions will then build and create the release
"""
import re
import subprocess
import sys
from pathlib import Path


def get_current_version():
    try:
        import tomllib
        with open("pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except ImportError:
        import tomli
        with open("pyproject.toml", "rb") as f:
            return tomli.load(f)["project"]["version"]


def update_version(new_version):
    files = [
        ("pyproject.toml", r'^version = ".*"', f'version = "{new_version}"'),
        ("anki_git/__init__.py", r'^version = ".*"', f'version = "{new_version}"'),
    ]
    for path, pattern, replacement in files:
        p = Path(path)
        if not p.exists():
            print(f"  Skipped {path} (not found)")
            continue
        content = p.read_text()
        content = re.sub(pattern, replacement, content, count=1, flags=re.MULTILINE)
        p.write_text(content)
        print(f"  Updated {path}")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 1

    new_version = sys.argv[1]
    current = get_current_version()
    print(f"Current version: {current}")
    print(f"New version:     {new_version}")

    confirm = input("Continue? (y/N): ")
    if confirm.lower() != "y":
        print("Cancelled")
        return

    update_version(new_version)

    tag = f"v{new_version}"
    subprocess.run(["git", "add", "pyproject.toml", "anki_git/__init__.py"], check=True)
    subprocess.run(["git", "commit", "-m", f"Bump version to {new_version}"], check=True)
    subprocess.run(["git", "tag", "-a", tag, "-m", f"Release {tag}"], check=True)
    subprocess.run(["git", "push"], check=True)
    subprocess.run(["git", "push", "origin", tag], check=True)

    print(f"\nReleased {tag}! GitHub Actions will build and publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
