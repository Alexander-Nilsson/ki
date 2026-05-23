"""Tests for content hashing and meta.json persistence."""
from pathlib import Path
import tempfile
import json

from ki_addon.engine.checksums import (
    file_hash,
    content_hash,
    notes_hash,
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


def test_file_hash(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello", encoding="utf-8")
    h = file_hash(f)
    assert isinstance(h, str)
    assert len(h) == 32


def test_notes_hash():
    notes = {1: "content1", 2: "content2"}
    hashes = notes_hash(notes)
    assert "1" in hashes
    assert "2" in hashes
    assert hashes["1"] == content_hash("content1")
    assert hashes["2"] == content_hash("content2")


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
