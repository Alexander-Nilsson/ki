"""Tests for the two-way sync engine.

These are integration tests that require a real Anki collection.
The sync module (engine/sync.py) coordinates between Anki and Git,
making it inherently integration-level.
"""

import pytest

from anki_git.config import SyncMode


@pytest.mark.integration
class TestSyncWithCollection:
    def test_sync_empty_collection_empty_repo(self, anki_session, tmp_path):
        """Syncing an empty collection to an empty repo should be a no-op
        for notes (notetypes get exported on first sync).
        """
        from anki_git.engine.sync import sync_collection

        col = anki_session.collection
        result = sync_collection(col, tmp_path, sync_mode=SyncMode.ACCEPT_ALL)

        assert result.error == ""
        assert result.notes_exported == 0
        assert result.notes_imported == 0
        # Default Anki collection has notetypes, they export on first sync
        assert result.notetypes_exported > 0

    def test_sync_exports_new_notes_to_repo(self, anki_session, tmp_path):
        """New notes in Anki should be exported to the repo."""
        from anki_git.engine.sync import sync_collection

        col = anki_session.collection

        notetype = col.models.by_name("Basic")
        note = col.new_note(notetype)
        note.fields[0] = "Front"
        note.fields[1] = "Back"
        deck_id = col.decks.all_names_and_ids()[0].id
        col.add_note(note, deck_id)
        nid = note.id

        result = sync_collection(col, tmp_path, sync_mode=SyncMode.ACCEPT_ALL)

        assert result.error == ""
        assert result.notes_exported == 1
        assert result.notes_imported == 0

        # Verify file exists
        md_file = tmp_path / "decks" / "Default" / f"{nid}.md"
        assert md_file.exists()

    def test_sync_idempotent(self, anki_session, tmp_path):
        """Running sync twice with no changes should be a no-op."""
        from anki_git.engine.sync import sync_collection

        col = anki_session.collection
        _add_basic_note(col, "Hello", "World")

        r1 = sync_collection(col, tmp_path, sync_mode=SyncMode.ACCEPT_ALL)
        r2 = sync_collection(col, tmp_path, sync_mode=SyncMode.ACCEPT_ALL)

        assert r1.error == ""
        assert r2.error == ""
        assert r2.notes_exported == 0
        assert r2.notes_imported == 0

    def test_sync_imports_notes_from_repo(self, anki_session, tmp_path):
        """Notes in repo that are not in Anki should be imported."""
        from anki_git.engine.sync import sync_collection

        col = anki_session.collection

        # Create a notetype and note in the repo first with a unique name
        _setup_repo_notetype(tmp_path, "SyncTestNT")
        _setup_repo_note(
            tmp_path, 1, "SyncTestNT", "Default",
            {"Front": "Hello", "Back": "World"},
        )

        # Add the same notetype to Anki so notes can be imported
        nt = col.models.new("SyncTestNT")
        fm = col.models.new_field("Front")
        col.models.add_field(nt, fm)
        bm = col.models.new_field("Back")
        col.models.add_field(nt, bm)
        tmpl = col.models.new_template("Card 1")
        tmpl["qfmt"] = "{{Front}}"
        tmpl["afmt"] = "{{Back}}"
        col.models.add_template(nt, tmpl)
        col.models.add_dict(nt)

        result = sync_collection(col, tmp_path, sync_mode=SyncMode.ACCEPT_ALL)

        assert result.error == ""
        # Note exists in repo but not in Anki -> should be imported
        assert result.notes_imported >= 1

    def test_sync_deletion_propagation(self, anki_session, tmp_path):
        """Deleting a note in Anki should propagate to repo on next sync."""
        from anki_git.engine.sync import sync_collection

        col = anki_session.collection

        notetype = col.models.by_name("Basic")
        note = col.new_note(notetype)
        note.fields[0] = "Delete me"
        note.fields[1] = "Soon"
        deck_id = col.decks.all_names_and_ids()[0].id
        col.add_note(note, deck_id)
        nid = note.id

        # First sync to export
        sync_collection(col, tmp_path, sync_mode=SyncMode.ACCEPT_ALL)
        assert (tmp_path / "decks" / "Default" / f"{nid}.md").exists()

        # Now delete from Anki and sync again
        col.remove_notes([nid])

        result = sync_collection(col, tmp_path, sync_mode=SyncMode.ACCEPT_ALL)

        # Note should be removed from repo
        assert result.notes_deleted_from_git >= 1
        assert not (tmp_path / "decks" / "Default" / f"{nid}.md").exists()


def _add_basic_note(col, front, back):
    notetype = col.models.by_name("Basic")
    note = col.new_note(notetype)
    note.fields[0] = front
    note.fields[1] = back
    deck_id = col.decks.all_names_and_ids()[0].id
    col.add_note(note, deck_id)
    return note.id


def _setup_repo_notetype(repo_path, name):
    import json
    nt_dir = repo_path / "notetypes" / name
    nt_dir.mkdir(parents=True, exist_ok=True)
    (nt_dir / "meta.json").write_text(
        json.dumps({"name": name, "id": 1}), encoding="utf-8"
    )
    (nt_dir / "fields.json").write_text(
        json.dumps([
            {"name": "Front", "ord": 0},
            {"name": "Back", "ord": 1},
        ]), encoding="utf-8"
    )
    (nt_dir / "templates.json").write_text(
        json.dumps([
            {"name": "Card 1", "ord": 0},
        ]), encoding="utf-8"
    )
    card_dir = nt_dir / "Card 1"
    card_dir.mkdir(exist_ok=True)
    (card_dir / "front.html").write_text("{{Front}}", encoding="utf-8")
    (card_dir / "back.html").write_text("{{Back}}", encoding="utf-8")


def _setup_repo_note(repo_path, nid, notetype, deck, fields):
    deck_dir = repo_path / "decks" / deck
    deck_dir.mkdir(parents=True, exist_ok=True)
    field_lines = "\n".join(
        f"## {k}\n{v}" for k, v in fields.items()
    )
    tags_str = "tag1"
    content = (
        f"<!-- note: nid={nid} notetype={notetype}"
        f" tags={tags_str} deck={deck} -->\n"
        f"{field_lines}\n"
    )
    (deck_dir / f"{nid}.md").write_text(content, encoding="utf-8")
