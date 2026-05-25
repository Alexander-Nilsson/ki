"""Tests for the import engine."""

import pytest

from anki_git.engine.importer import (
    ImportResult,
    preview_import,
)
from anki_git.engine.import_helpers import compute_git_checksums


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
    import json
    notetypes_root = tmp_path / "notetypes"
    nt_dir = notetypes_root / "Basic"
    nt_dir.mkdir(parents=True)
    (nt_dir / "meta.json").write_text(json.dumps({"name": "Basic", "id": 1}), encoding="utf-8")
    (nt_dir / "fields.json").write_text("[]", encoding="utf-8")
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
    checksums, notes = compute_git_checksums(tmp_path)
    assert "123" in checksums
    assert isinstance(checksums["123"], str)
    assert len(checksums["123"]) == 32
    assert 123 in notes


def test_import_result_defaults():
    r = ImportResult()
    assert r.notes_updated == 0
    assert r.notes_created == 0
    assert r.notetypes_updated == 0
    assert r.notetypes_created == 0
    assert r.errors == []
    assert r.warnings == []
    assert r.conflict_report is None


# --- Malformed data tests ---

def test_preview_import_malformed_nid(tmp_path):
    """A note with non-digit nid is silently skipped by preview_import."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    note_file = decks_dir / "123.md"
    note_file.write_text(
        '<!-- note: nid=abc notetype=Basic tags=tag1 deck=Default -->\n## Front\nHello\n',
        encoding="utf-8",
    )
    result = preview_import(tmp_path)
    assert result.notes_created == 0


def test_preview_import_no_header(tmp_path):
    """A file with no valid note header should yield 0 notes."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    note_file = decks_dir / "123.md"
    note_file.write_text(
        '# Just a heading\n\nSome random markdown with no proper header\n',
        encoding="utf-8",
    )
    result = preview_import(tmp_path)
    assert result.notes_created == 0


def test_preview_import_mixed_valid_invalid(tmp_path):
    """Valid notes count even if there are malformed files in the same repo."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)

    # Valid note
    (decks_dir / "1.md").write_text(
        '<!-- note: nid=1 notetype=Basic tags=tag1 deck=Default -->\n## Front\nValid\n',
        encoding="utf-8",
    )
    # Malformed note (missing notetype)
    (decks_dir / "2.md").write_text(
        '<!-- note: nid=2 tags=tag1 deck=Default -->\n## Front\nBad\n',
        encoding="utf-8",
    )
    # Another valid note
    (decks_dir / "3.md").write_text(
        '<!-- note: nid=3 notetype=Basic tags=tag2 deck=Default -->\n## Front\nAlso valid\n',
        encoding="utf-8",
    )

    result = preview_import(tmp_path)
    assert result.notes_created == 2


def test_preview_import_empty_note_file(tmp_path):
    """An empty .md file in the decks dir contributes 0 notes."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    (decks_dir / "empty.md").write_text("", encoding="utf-8")
    result = preview_import(tmp_path)
    assert result.notes_created == 0


def test_preview_import_non_md_files_ignored(tmp_path):
    """Files without .md extension in the decks dir are ignored by rglob('*.md')."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    (decks_dir / "note.txt").write_text("some content", encoding="utf-8")
    (decks_dir / "note.json").write_text("{}", encoding="utf-8")
    result = preview_import(tmp_path)
    assert result.notes_created == 0


def test_preview_import_unclosed_comment(tmp_path):
    """A note with unclosed HTML comment is skipped."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    note_file = decks_dir / "1.md"
    note_file.write_text(
        "<!-- note: nid=1 notetype=Basic tags= deck=Default\n## Front\nHello\n",
        encoding="utf-8",
    )
    result = preview_import(tmp_path)
    assert result.notes_created == 0


def test_compute_git_checksums_malformed_note(tmp_path):
    """Malformed notes are excluded from git checksums."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    # Valid note
    (decks_dir / "1.md").write_text(
        '<!-- note: nid=1 notetype=Basic tags=tag1 deck=Default -->\n## Front\nHello\n',
        encoding="utf-8",
    )
    # Malformed note
    (decks_dir / "2.md").write_text(
        'garbage content no header\n',
        encoding="utf-8",
    )
    checksums, notes = compute_git_checksums(tmp_path)
    assert "1" in checksums
    assert "2" not in checksums
    assert 1 in notes
    assert 2 not in notes


def test_compute_git_checksums_empty_decks_dir(tmp_path):
    """Empty decks dir produces empty checksums."""
    (tmp_path / "decks").mkdir(parents=True)
    checksums, notes = compute_git_checksums(tmp_path)
    assert checksums == {}
    assert notes == {}


@pytest.mark.integration
def test_import_from_repo_malformed(tmp_path, anki_session):
    """import_from_repo gracefully handles malformed note files."""
    col = anki_session.collection

    # Set up a basic notetype in the collection
    nt = col.models.new("Basic")
    fm = col.models.new_field("Front")
    col.models.add_field(nt, fm)
    bm = col.models.new_field("Back")
    col.models.add_field(nt, bm)
    tmpl = col.models.new_template("Card 1")
    tmpl["qfmt"] = "{{Front}}"
    tmpl["afmt"] = "{{Back}}"
    col.models.add_template(nt, tmpl)
    col.models.add_dict(nt)

    # Set up repo with a valid notetype and a mix of valid/malformed notes
    repo = tmp_path / "repo"
    import json
    notetypes_root = repo / "notetypes"
    nt_dir = notetypes_root / "Basic"
    nt_dir.mkdir(parents=True)
    (nt_dir / "meta.json").write_text(json.dumps({"name": "Basic", "id": 1}), encoding="utf-8")
    (nt_dir / "fields.json").write_text(json.dumps([
        {"name": "Front", "ord": 0},
        {"name": "Back", "ord": 1},
    ]), encoding="utf-8")
    card_dir = nt_dir / "Card 1"
    card_dir.mkdir()
    (card_dir / "front.html").write_text("{{Front}}", encoding="utf-8")
    (card_dir / "back.html").write_text("{{Back}}", encoding="utf-8")
    decks_dir = repo / "decks" / "Default"
    decks_dir.mkdir(parents=True)

    # Valid note
    (decks_dir / "1.md").write_text(
        '<!-- note: nid=1 notetype=Basic tags=tag1 deck=Default -->\n## Front\nQ1\n## Back\nA1\n',
        encoding="utf-8",
    )
    # Malformed note (missing notetype)
    (decks_dir / "2.md").write_text(
        '<!-- note: nid=2 tags= deck=Default -->\n## Front\nQ2\n',
        encoding="utf-8",
    )
    # Malformed note (no header)
    (decks_dir / "3.md").write_text(
        '## Front\nQ3\n',
        encoding="utf-8",
    )
    # Valid note that has no corresponding notetype yet
    (decks_dir / "4.md").write_text(
        '<!-- note: nid=4 notetype=Basic tags= deck=Default -->\n## Front\nQ4\n## Back\nA4\n',
        encoding="utf-8",
    )

    from anki_git.engine.importer import import_from_repo
    result = import_from_repo(col, repo)

    # 2 valid notes (1 and 4) should have been imported
    assert result.notes_created == 2
    assert len(result.errors) == 0
    assert len(result.warnings) == 0  # notetype Basic is present
