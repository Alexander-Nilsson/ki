"""Tests for engine/exporter.py — the snapshot/export pipeline."""
from pathlib import Path

import pytest

from anki_git.engine.exporter import ExportResult, export_collection


class TestExportResult:
    def test_defaults(self):
        r = ExportResult()
        assert r.notes_changed == 0
        assert r.notetypes_changed == 0
        assert r.notes_deleted_from_repo == 0
        assert r.changed_decks == {}
        assert r.changed_notetypes == []
        assert r.error == ""
        assert r.duration_seconds == 0.0
        assert r.commit_count == 0

    def test_custom_values(self):
        r = ExportResult(
            notes_changed=5,
            notetypes_changed=2,
            changed_decks={"Default": 5},
            changed_notetypes=["Basic"],
            error="",
            commit_count=1,
        )
        assert r.notes_changed == 5
        assert r.notetypes_changed == 2
        assert r.changed_decks == {"Default": 5}
        assert r.changed_notetypes == ["Basic"]
        assert r.commit_count == 1


@pytest.mark.integration
class TestExportCollection:
    def test_empty_collection(self, anki_session):
        col = anki_session.collection
        repo_path = Path(anki_session.base) / "repo"
        result = export_collection(col, repo_path)
        assert result.notes_changed == 0
        assert result.error == ""
        assert (repo_path / ".git").exists()
        assert (repo_path / ".gitignore").exists()
        assert (repo_path / ".anki_git" / "meta.json").exists()

    def test_single_note_export(self, anki_session):
        col = anki_session.collection
        repo_path = Path(anki_session.base) / "repo"
        note = col.new_note(col.models.by_name("Basic"))
        note["Front"] = "hello"
        note["Back"] = "world"
        col.add_note(note, col.decks.id("Default"))

        result = export_collection(col, repo_path)
        assert result.notes_changed == 1
        assert result.error == ""
        assert result.commit_count == 1

        md_files = list((repo_path / "decks" / "Default").rglob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text(encoding="utf-8")
        assert "hello" in content
        assert "world" in content

    def test_two_notes_same_deck(self, anki_session):
        col = anki_session.collection
        repo_path = Path(anki_session.base) / "repo"
        for i in range(2):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = f"front{i}"
            note["Back"] = f"back{i}"
            col.add_note(note, col.decks.id("Default"))

        result = export_collection(col, repo_path)
        assert result.notes_changed == 2
        md_files = list((repo_path / "decks" / "Default").rglob("*.md"))
        assert len(md_files) == 2

    def test_notetype_export(self, anki_session):
        col = anki_session.collection
        repo_path = Path(anki_session.base) / "repo"
        export_collection(col, repo_path)
        nt_dir = repo_path / "notetypes"
        assert nt_dir.exists()
        entries = list(nt_dir.iterdir())
        assert len(entries) >= 1
        for entry in entries:
            assert entry.is_dir()
            yaml_files = list(entry.rglob("*"))
            assert len(yaml_files) >= 1

    def test_idempotent_export_no_changes(self, anki_session):
        col = anki_session.collection
        repo_path = Path(anki_session.base) / "repo"
        export_collection(col, repo_path)
        result = export_collection(col, repo_path)
        assert result.notes_changed == 0
        assert result.commit_count == 1  # no new commit

    def test_export_detects_change(self, anki_session):
        col = anki_session.collection
        repo_path = Path(anki_session.base) / "repo"
        note = col.new_note(col.models.by_name("Basic"))
        note["Front"] = "v1"
        note["Back"] = "v1"
        col.add_note(note, col.decks.id("Default"))
        export_collection(col, repo_path)

        note["Front"] = "v2"
        col.update_note(note)
        result = export_collection(col, repo_path)
        assert result.notes_changed == 1
        assert result.commit_count == 2

    def test_progress_callback_invoked(self, anki_session):
        col = anki_session.collection
        repo_path = Path(anki_session.base) / "repo"
        calls = []

        def cb(text: str):
            calls.append(text)

        export_collection(col, repo_path, progress_callback=cb)
        assert len(calls) > 0
        assert any("Initializing" in c for c in calls)
        assert any("complete" in c for c in calls)

    def test_repo_path_is_initialized(self, anki_session):
        col = anki_session.collection
        repo_path = Path(anki_session.base) / "nested" / "repo"
        export_collection(col, repo_path)
        assert (repo_path / ".git").exists()
        assert (repo_path / ".gitignore").exists()
        assert (repo_path / ".anki_git" / "meta.json").exists()

    def test_notes_without_cards_skipped(self, anki_session):
        col = anki_session.collection
        repo_path = Path(anki_session.base) / "repo"
        note = col.new_note(col.models.by_name("Basic"))
        note["Front"] = "orphan"
        note["Back"] = "orphan"
        col.add_note(note, col.decks.id("Default"))
        col.remove_notes([note.id])

        result = export_collection(col, repo_path)
        assert result.notes_changed == 0

    def test_multiple_decks(self, anki_session):
        col = anki_session.collection
        repo_path = Path(anki_session.base) / "repo"
        for deck_name in ["DeckA", "DeckB"]:
            did = col.decks.id(deck_name)
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = f"from {deck_name}"
            note["Back"] = "x"
            col.add_note(note, did)

        result = export_collection(col, repo_path)
        assert result.notes_changed == 2
        assert "DeckA" in result.changed_decks
        assert "DeckB" in result.changed_decks
        assert (repo_path / "decks" / "DeckA").exists()
        assert (repo_path / "decks" / "DeckB").exists()

    def test_notetype_changes_detected(self, anki_session):
        col = anki_session.collection
        repo_path = Path(anki_session.base) / "repo"
        export_collection(col, repo_path)
        old_count = len(list((repo_path / "notetypes").rglob("*.yaml")))

        model = col.models.by_name("Basic")
        model["css"] = "body { color: red; }"
        col.models.save(model)

        result = export_collection(col, repo_path)
        assert result.notetypes_changed >= 1
