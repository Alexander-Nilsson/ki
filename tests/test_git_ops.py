"""Tests for git operations."""
from pathlib import Path

from anki_git.engine.git_ops import (
    init_repo,
    open_repo,
    get_or_init_repo,
    create_snapshot_commit,
    is_dirty,
    get_commit_count,
    ensure_gitignore,
)


def test_init_repo_creates_repo(tmp_path):
    repo = init_repo(tmp_path)
    assert (tmp_path / ".git").exists()
    assert not repo.is_dirty()


def test_open_repo_returns_none_for_nonexistent():
    repo = open_repo(Path("/nonexistent/path"))
    assert repo is None


def test_open_repo_finds_existing(tmp_path):
    init_repo(tmp_path)
    repo = open_repo(tmp_path)
    assert repo is not None


def test_get_or_init_repo_creates(tmp_path):
    get_or_init_repo(tmp_path)
    assert (tmp_path / ".git").exists()


def test_get_or_init_repo_reuses(tmp_path):
    init_repo(tmp_path)
    get_or_init_repo(tmp_path)
    assert (tmp_path / ".git").exists()


def test_stage_and_commit(tmp_path):
    repo = init_repo(tmp_path)
    f = tmp_path / "test.txt"
    f.write_text("hello", encoding="utf-8")
    repo.git.add(all=True)
    repo.index.commit("Initial commit")
    assert not is_dirty(repo)
    assert get_commit_count(repo) == 1


def test_is_dirty_with_unstaged(tmp_path):
    repo = init_repo(tmp_path)
    f = tmp_path / "test.txt"
    f.write_text("hello", encoding="utf-8")
    assert is_dirty(repo)


def test_commit_count_empty_repo(tmp_path):
    repo = init_repo(tmp_path)
    assert get_commit_count(repo) == 0


def test_commit_count_after_commits(tmp_path):
    repo = init_repo(tmp_path)
    f = tmp_path / "f.txt"
    f.write_text("v1", encoding="utf-8")
    repo.git.add(all=True)
    repo.index.commit("c1")
    assert get_commit_count(repo) == 1
    f.write_text("v2", encoding="utf-8")
    repo.git.add(all=True)
    repo.index.commit("c2")
    assert get_commit_count(repo) == 2


def test_ensure_gitignore_creates(tmp_path):
    ensure_gitignore(tmp_path)
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    assert ".ki/" in gitignore.read_text(encoding="utf-8")


def test_ensure_gitignore_does_not_overwrite(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("custom\n", encoding="utf-8")
    ensure_gitignore(tmp_path)
    content = gitignore.read_text(encoding="utf-8")
    assert content.startswith("custom\n")
    assert ".ki/" in content


def test_create_snapshot_commit(tmp_path):
    repo = init_repo(tmp_path)
    f = tmp_path / "notes.md"
    f.write_text("content", encoding="utf-8")
    repo.git.add(all=True)
    create_snapshot_commit(repo, ["decks/Default/123.md", "notetypes/Basic.yaml"])
    assert get_commit_count(repo) == 1
    msg = repo.head.commit.message
    assert "decks/Default/123.md" in msg
    assert "notetypes/Basic.yaml" in msg


def test_create_snapshot_commit_many_files(tmp_path):
    repo = init_repo(tmp_path)
    f = tmp_path / "notes.md"
    f.write_text("content", encoding="utf-8")
    repo.git.add(all=True)
    files = [f"decks/D/n{i}.md" for i in range(10)]
    create_snapshot_commit(repo, files)
    assert get_commit_count(repo) == 1
    msg = repo.head.commit.message
    assert "10 files changed" in msg
