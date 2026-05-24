"""Tests for shared import helpers module."""

import pytest

from anki_git.engine.import_helpers import (
    compute_git_checksums,
    load_all_repo_notes,
    delete_note_from_repo,
)


class TestComputeGitChecksums:
    def test_empty_decks_dir(self, tmp_path):
        (tmp_path / "decks").mkdir(parents=True)
        assert compute_git_checksums(tmp_path) == {}

    def test_returns_checksums(self, tmp_path):
        decks_dir = tmp_path / "decks" / "Default"
        decks_dir.mkdir(parents=True)
        note_file = decks_dir / "123.md"
        note_file.write_text(
            '<!-- note: nid=123 notetype=Basic tags=tag1 deck=Default -->\n'
            '## Front\nHello\n',
            encoding="utf-8",
        )
        checksums = compute_git_checksums(tmp_path)
        assert "123" in checksums
        assert len(checksums["123"]) == 32

    def test_skips_malformed_notes(self, tmp_path):
        decks_dir = tmp_path / "decks" / "Default"
        decks_dir.mkdir(parents=True)
        (decks_dir / "1.md").write_text(
            '<!-- note: nid=1 notetype=Basic tags=tag1 deck=Default -->\n'
            '## Front\nValid\n',
            encoding="utf-8",
        )
        (decks_dir / "2.md").write_text(
            'garbage no header\n',
            encoding="utf-8",
        )
        checksums = compute_git_checksums(tmp_path)
        assert "1" in checksums
        assert "2" not in checksums


class TestLoadAllRepoNotes:
    def test_empty(self, tmp_path):
        (tmp_path / "decks").mkdir(parents=True)
        assert load_all_repo_notes(tmp_path) == {}

    def test_loads_notes(self, tmp_path):
        decks_dir = tmp_path / "decks" / "Default"
        decks_dir.mkdir(parents=True)
        (decks_dir / "1.md").write_text(
            '<!-- note: nid=1 notetype=Basic tags= tag1 deck=Default -->\n'
            '## Front\nHello\n',
            encoding="utf-8",
        )
        notes = load_all_repo_notes(tmp_path)
        assert 1 in notes
        assert notes[1].deck == "Default"


class TestDeleteNoteFromRepo:
    def test_deletes_existing_file(self, tmp_path):
        decks_dir = tmp_path / "decks" / "Default"
        decks_dir.mkdir(parents=True)
        md_path = decks_dir / "123.md"
        md_path.write_text("content", encoding="utf-8")

        assert delete_note_from_repo(tmp_path, 123) is True
        assert not md_path.exists()

    def test_nonexistent_nid(self, tmp_path):
        (tmp_path / "decks").mkdir(parents=True)
        assert delete_note_from_repo(tmp_path, 999) is False


@pytest.mark.integration
def test_cleanup_stale_repo_notes(anki_session, tmp_path):
    """Verify cleanup removes files whose nids no longer exist in Anki."""
    from anki_git.engine.import_helpers import cleanup_stale_repo_notes

    col = anki_session.collection

    # Create a note in Anki
    notetype = col.models.by_name("Basic")
    note = col.new_note(notetype)
    note.fields[0] = "Existing"
    note.fields[1] = "Note"
    deck_id = col.decks.all_names_and_ids()[0].id
    col.add_note(note, deck_id)
    existing_nid = note.id

    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    (decks_dir / f"{existing_nid}.md").write_text(
        f'<!-- note: nid={existing_nid} notetype=Basic tags= deck=Default -->\n'
        '## Front\nExisting\n## Back\nNote\n',
        encoding="utf-8",
    )
    # nid=2 doesn't exist in Anki but has a file in repo
    (decks_dir / "2.md").write_text(
        '<!-- note: nid=2 notetype=Basic tags= deck=Default -->\n'
        '## Front\nWorld\n## Back\nStale\n',
        encoding="utf-8",
    )
    cleaned = cleanup_stale_repo_notes(col, tmp_path)
    assert cleaned == 1
    assert not (decks_dir / "2.md").exists()
    assert (decks_dir / f"{existing_nid}.md").exists()
