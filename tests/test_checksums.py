"""Tests for content hashing and meta.json persistence."""
from pathlib import Path
import tempfile
import json

from anki_git.engine.checksums import (
    content_hash,
    load_meta,
    save_meta,
)


def test_content_hash_is_deterministic():
    h1 = content_hash("hello world")
    h2 = content_hash("hello world")
    assert h1 == h2
    assert isinstance(h1, str)
    assert len(h1) == 32


def test_content_hash_differs():
    assert content_hash("foo") != content_hash("bar")


def test_quick_has_changes_no_baseline():
    """Returns None when no meta baseline exists."""
    from unittest.mock import MagicMock
    from anki_git.engine.checksums import quick_has_changes

    col = MagicMock()
    result = quick_has_changes(col, Path("/nonexistent"))
    assert result is None


def test_quick_has_changes_count_differs(tmp_path):
    """Returns True when note count changed."""
    from unittest.mock import MagicMock
    from anki_git.engine.checksums import quick_has_changes, save_meta

    save_meta(tmp_path, {"last_note_count": 5, "last_max_mod": 100})
    col = MagicMock()
    col.db.scalar.side_effect = [10, 200]
    result = quick_has_changes(col, tmp_path)
    assert result is True


def test_quick_has_changes_mod_differs(tmp_path):
    """Returns True when max mod changed."""
    from unittest.mock import MagicMock
    from anki_git.engine.checksums import quick_has_changes, save_meta

    save_meta(tmp_path, {"last_note_count": 5, "last_max_mod": 100})
    col = MagicMock()
    col.db.scalar.side_effect = [5, 200]
    result = quick_has_changes(col, tmp_path)
    assert result is True


def test_quick_has_changes_no_repo(tmp_path):
    """Returns True when repo path has no valid git repo."""
    from unittest.mock import MagicMock
    from anki_git.engine.checksums import quick_has_changes, save_meta

    save_meta(tmp_path, {"last_note_count": 5, "last_max_mod": 100})
    col = MagicMock()
    col.db.scalar.side_effect = [5, 100]
    result = quick_has_changes(col, tmp_path)
    assert result is True


def test_quick_has_changes_no_changes(tmp_path):
    """Returns False when nothing changed (no SHA stored, not dirty)."""
    import json
    from unittest.mock import MagicMock
    from anki_git.engine.checksums import quick_has_changes
    from anki_git.engine.git_ops import init_repo

    repo = init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("", encoding="utf-8")
    repo.index.add([".gitignore"])
    repo.index.commit("init")
    meta_path = tmp_path / ".ki" / "meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps({
        "last_note_count": 5, "last_max_mod": 100,
    }, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    repo.index.add([".ki/meta.json"])
    repo.index.commit("meta")
    col = MagicMock()
    col.db.scalar.side_effect = [5, 100]
    result = quick_has_changes(col, tmp_path)
    assert result is False


def test_quick_repo_has_changes_no_baseline(tmp_path):
    """Returns None when no meta baseline exists."""
    from anki_git.engine.checksums import quick_repo_has_changes
    result = quick_repo_has_changes(tmp_path)
    assert result is None


def test_quick_repo_has_changes_no_repo(tmp_path):
    """Returns True when repo path has no valid git repo."""
    from anki_git.engine.checksums import quick_repo_has_changes, save_meta

    save_meta(tmp_path, {"last_commit_sha": "abc123"})
    result = quick_repo_has_changes(tmp_path)
    assert result is True


def test_quick_repo_has_changes_clean(tmp_path):
    """Returns False when repo is clean and has baseline."""
    from anki_git.engine.checksums import quick_repo_has_changes, save_meta
    from anki_git.engine.git_ops import init_repo

    repo = init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text(".ki/\n", encoding="utf-8")
    repo.index.add([".gitignore"])
    repo.index.commit("init")

    save_meta(tmp_path, {"last_commit_sha": str(repo.head.commit)})

    result = quick_repo_has_changes(tmp_path)
    assert result is False


def test_quick_repo_has_changes_dirty(tmp_path):
    """Returns True when repo has uncommitted changes."""
    from anki_git.engine.checksums import quick_repo_has_changes, save_meta
    from anki_git.engine.git_ops import init_repo

    repo = init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("", encoding="utf-8")
    repo.index.add([".gitignore"])
    repo.index.commit("init")

    save_meta(tmp_path, {"last_commit_sha": str(repo.head.commit)})

    # Make repo dirty with a content file change
    decks_dir = tmp_path / "decks"
    decks_dir.mkdir()
    (decks_dir / "note.md").write_text("dirty", encoding="utf-8")

    result = quick_repo_has_changes(tmp_path)
    assert result is True


def test_save_and_load_meta(tmp_path):
    meta = {"last_export_time": 1700000000, "note_checksums": {"1": "abc"}}
    save_meta(tmp_path, meta)
    meta_path = tmp_path / ".ki" / "meta.json"
    assert meta_path.exists()
    loaded = json.loads(meta_path.read_text(encoding="utf-8"))
    assert loaded == meta


def test_load_meta_nonexistent():
    meta = load_meta(Path("/nonexistent"))
    assert meta == {}


def test_load_meta_returns_saved(tmp_path):
    meta = {"key": "value"}
    save_meta(tmp_path, meta)
    loaded = load_meta(tmp_path)
    assert loaded == meta


def test_save_meta_creates_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        deep_path = Path(tmpdir) / "a" / "b" / "c"
        save_meta(deep_path, {"test": True})
        assert (deep_path / ".ki" / "meta.json").exists()
