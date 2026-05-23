"""Tests for the import engine."""

from anki_git.engine.importer import (
    ImportResult,
    preview_import,
    _compute_git_checksums,
)


def test_preview_import_no_repo(tmp_path):
    result = preview_import(tmp_path / "nonexistent")
    assert isinstance(result, ImportResult)
    assert result.notetypes_created == 0
    assert result.notes_created == 0


def test_preview_import_empty_repo(tmp_path):
    notetypes_dir = tmp_path / "notetypes"
    notetypes_dir.mkdir(parents=True)
    decks_dir = tmp_path / "decks"
    decks_dir.mkdir(parents=True)
    result = preview_import(tmp_path)
    assert result.notetypes_created == 0
    assert result.notes_created == 0


def test_preview_import_counts_notes(tmp_path):
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    note_file = decks_dir / "123.md"
    note_file.write_text(
        '<!-- note: nid=123 notetype=Basic tags=tag1 deck=Default -->\n## Front\nHello\n',
        encoding="utf-8",
    )
    result = preview_import(tmp_path)
    assert result.notes_created == 1


def test_preview_import_counts_notetypes(tmp_path):
    notetypes_dir = tmp_path / "notetypes"
    notetypes_dir.mkdir(parents=True)
    yaml_file = notetypes_dir / "Basic.yaml"
    yaml_file.write_text("name: Basic\nid: 1\nfields: []\ntemplates: []\ncss: ''\n", encoding="utf-8")
    result = preview_import(tmp_path)
    assert result.notetypes_created == 1


def test_compute_git_checksums(tmp_path):
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    note_file = decks_dir / "123.md"
    note_file.write_text(
        '<!-- note: nid=123 notetype=Basic tags=tag1 deck=Default -->\n## Front\nHello\n',
        encoding="utf-8",
    )
    checksums = _compute_git_checksums(tmp_path)
    assert "123" in checksums
    assert isinstance(checksums["123"], str)
    assert len(checksums["123"]) == 32


def test_import_result_defaults():
    r = ImportResult()
    assert r.notes_updated == 0
    assert r.notes_created == 0
    assert r.notetypes_updated == 0
    assert r.notetypes_created == 0
    assert r.errors == []
    assert r.warnings == []
    assert r.conflict_report is None
