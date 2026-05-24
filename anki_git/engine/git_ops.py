import datetime
import logging
from pathlib import Path
from typing import Optional
from datetime import timezone

from git import Repo, GitCommandError

_logger = logging.getLogger("anki_git")


def init_repo(repo_path: Path) -> Repo:
    repo_path.mkdir(parents=True, exist_ok=True)
    _logger.info("Initializing new Git repository at %s", repo_path)
    return Repo.init(repo_path)


def open_repo(repo_path: Path) -> Optional[Repo]:
    try:
        return Repo(repo_path)
    except (GitCommandError, Exception):
        return None


def get_or_init_repo(repo_path: Path) -> Repo:
    repo = open_repo(repo_path)
    if repo is None:
        repo = init_repo(repo_path)
    return repo


def stage_all(repo: Repo) -> None:
    repo.git.add(all=True)


def stage_files(repo: Repo, paths: list[str]) -> None:
    """Stage specific file paths relative to the repo root."""
    if not paths:
        return
    repo.index.add(paths)


def commit(repo: Repo, message: str) -> None:
    repo.index.commit(message)


def create_snapshot_commit(
    repo: Repo,
    notes_changed: int,
    notetypes_changed: int,
    changed_decks: dict,
    changed_notetypes: list,
    collection_path: str,
) -> None:
    deck_lines = ", ".join(f"{d} ({n} notes)" for d, n in changed_decks.items())
    nt_lines = ", ".join(changed_notetypes)
    timestamp = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    message = (
        f"snapshot: {notes_changed} notes changed, {notetypes_changed} notetypes updated\n"
        f"\n"
        f"Changed decks: {deck_lines}\n"
        f"Changed notetypes: {nt_lines}\n"
        f"Collection: {collection_path}\n"
        f"Timestamp: {timestamp}\n"
    )
    repo.index.commit(message)


def push_to_remote(repo: Repo, remote_url: str) -> None:
    if not remote_url:
        return
    _logger.info("Pushing to remote: %s", remote_url)
    try:
        try:
            remote = repo.remote("origin")
            if remote.url != remote_url:
                _logger.info("Updating remote origin URL to %s", remote_url)
                remote.set_url(remote_url)
        except ValueError:
            _logger.info("Creating remote origin with URL %s", remote_url)
            remote = repo.create_remote("origin", remote_url)

        remote.push(refspec="main:main")
    except Exception as e:
        _logger.exception("Failed to push to remote")
        raise


def is_dirty(repo: Repo) -> bool:
    return repo.is_dirty() or bool(repo.untracked_files)


def get_commit_count(repo: Repo) -> int:
    try:
        return len(list(repo.iter_commits()))
    except Exception:
        return 0


def ensure_gitignore(repo_root: Path) -> None:
    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".ki/backups\n", encoding="utf-8")
