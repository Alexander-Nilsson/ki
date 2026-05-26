import logging
from pathlib import Path
from typing import Optional

from git import Repo, GitCommandError, InvalidGitRepositoryError

_logger = logging.getLogger("anki_git")


def validate_repo_path(repo_path: Path) -> bool:
    """Validate that repo_path is a reasonable directory path.

    Returns True if the path looks valid (doesn't verify git init state).
    """
    if not str(repo_path).strip():
        return False
    resolved = repo_path.resolve()
    if resolved.exists() and not resolved.is_dir():
        _logger.error("Repo path exists but is not a directory: %s", repo_path)
        return False
    return True


def init_repo(repo_path: Path) -> Repo:
    repo_path.mkdir(parents=True, exist_ok=True)
    _logger.info("Initializing new Git repository at %s", repo_path)
    return Repo.init(repo_path)


def open_repo(repo_path: Path) -> Optional[Repo]:
    try:
        return Repo(repo_path)
    except (InvalidGitRepositoryError, GitCommandError, Exception):
        return None


def get_or_init_repo(repo_path: Path) -> Repo:
    if not validate_repo_path(repo_path):
        raise ValueError(f"Invalid repository path: {repo_path}")
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


def create_snapshot_commit(
    repo: Repo,
    changed_files: list[str],
) -> None:
    if not changed_files:
        return
    sorted_files = sorted(changed_files)
    if len(sorted_files) <= 5:
        subject = ", ".join(sorted_files)
    else:
        subject = f"{len(sorted_files)} files changed"
    body = "\n".join(f"- {f}" for f in sorted_files)
    message = f"{subject}\n\n{body}" if len(sorted_files) > 5 else subject
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

        branch = repo.active_branch.name
        remote.push(refspec=f"{branch}:{branch}")
    except Exception:
        _logger.exception("Failed to push to remote")
        raise


def is_dirty(repo: Repo) -> bool:
    return repo.is_dirty() or bool(repo.untracked_files)


def get_commit_count(repo: Repo) -> int:
    try:
        return len(list(repo.iter_commits()))
    except Exception:
        _logger.exception("Failed to get commit count")
        return 0


def ensure_gitignore(repo_root: Path) -> None:
    gitignore = repo_root / ".gitignore"
    lines = [".ki/"]
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    new_lines = [l for l in lines if l not in existing]
    if new_lines:
        gitignore.write_text(
            "\n".join(existing + new_lines) + "\n",
            encoding="utf-8",
        )


def get_existing_remote_url(repo: Repo) -> str:
    """Return the URL of the 'origin' remote if it exists."""
    try:
        return repo.remote("origin").url
    except (ValueError, Exception):
        _logger.debug("No remote 'origin' configured")
        return ""
