import re
from enum import Enum
from pathlib import Path
from typing import Set


class MediaStrategy(Enum):
    NONE = "none"
    SYMLINK = "symlink"
    COPY = "copy"
    GIT_LFS = "git-lfs"


_MEDIA_PATTERN = re.compile(r'\[sound:(.*?)\]|<img[^>]*src="([^"]*)"')


def handle_media(
    media_dir: Path,
    repo_media_dir: Path,
    strategy: MediaStrategy,
    filenames: Set[str],
) -> None:
    if strategy == MediaStrategy.NONE:
        return

    repo_media_dir.mkdir(parents=True, exist_ok=True)

    for fname in filenames:
        src = media_dir / fname
        dst = repo_media_dir / fname
        if not src.exists():
            continue
        if dst.exists():
            continue

        if strategy == MediaStrategy.SYMLINK:
            try:
                dst.symlink_to(src.resolve())
            except OSError as e:
                import logging
                logging.getLogger("anki_git").warning("Failed to symlink media %s: %s", fname, e)
        elif strategy == MediaStrategy.COPY:
            dst.write_bytes(src.read_bytes())
        elif strategy == MediaStrategy.GIT_LFS:
            dst.write_bytes(src.read_bytes())


def get_media_filenames_from_fields(fields: str) -> Set[str]:
    names = set()
    for match in _MEDIA_PATTERN.finditer(fields):
        if match.group(1):
            names.add(match.group(1))
        if match.group(2):
            names.add(match.group(2))
    return names
