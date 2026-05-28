"""Smoke tests for the AnkiGit addon.

These verify the addon loads without errors against the real anki runtime.
Follows the pattern from Anki-Dictionary-Addon's test_addon_loads.py.
"""
import os

import pytest

try:
    import anki  # noqa: F401

    _anki_available = True
except ImportError:
    _anki_available = False

integration = pytest.mark.skipif(
    not _anki_available,
    reason="anki package not available in this environment",
)

# Ensure offscreen Qt platform for headless environments
if "DISPLAY" not in os.environ and "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"


@integration
@pytest.mark.integration
class TestAddonImports:
    """Verify all addon modules can be imported."""

    def test_engine_modules_importable(self):
        import anki_git.config  # noqa: F401
        import anki_git.engine.checksums  # noqa: F401
        import anki_git.engine.conflict  # noqa: F401
        import anki_git.engine.exporter  # noqa: F401
        import anki_git.engine.git_ops  # noqa: F401
        import anki_git.formats.media  # noqa: F401
        import anki_git.formats.notes_md  # noqa: F401
        import anki_git.formats.notetype_yaml  # noqa: F401

    def test_addon_init(self):
        """Simulate the addon's entry point running."""
        from anki_git.addon import init_addon

        init_addon()

    def test_ui_modules_importable(self):
        import anki_git.ui.conflicts  # noqa: F401
        import anki_git.ui.settings  # noqa: F401


@integration
@pytest.mark.integration
class TestCollectionBasics:
    """Verify we can create and use a real Anki collection."""

    def test_collection_opens_and_closes(self, anki_session):
        assert anki_session.collection is not None
        assert anki_session.collection.path.endswith("collection.anki2")

    def test_default_deck_exists(self, anki_session):
        col = anki_session.collection
        decks = col.decks.all_names_and_ids()
        assert any(d.name == "Default" for d in decks)

    def test_default_notetypes_exist(self, anki_session):
        col = anki_session.collection
        names = [m["name"] for m in col.models.all()]
        assert "Basic" in names
        assert "Cloze" in names


@integration
@pytest.mark.integration
class TestEngineAgainstCollection:
    """Exercise the engine layer against a real Anki collection."""

    def test_export_snapshot_creates_repo(self, anki_session, tmp_path):
        from anki_git.engine.exporter import export_collection

        col = anki_session.collection

        notetype = col.models.by_name("Basic")
        note = col.new_note(notetype)
        note.fields[0] = "Hello"
        note.fields[1] = "World"
        deck_id = col.decks.all_names_and_ids()[0].id
        col.add_note(note, deck_id)

        result = export_collection(col, tmp_path)

        assert result.error == ""
        assert (tmp_path / ".git").exists()
        assert (tmp_path / "notetypes").exists()
        assert (tmp_path / "decks").exists()

    def test_export_twice_is_idempotent(self, anki_session, tmp_path):
        from anki_git.engine.exporter import export_collection

        col = anki_session.collection

        notetype = col.models.by_name("Basic")
        note = col.new_note(notetype)
        note.fields[0] = "Hello"
        note.fields[1] = "World"
        deck_id = col.decks.all_names_and_ids()[0].id
        col.add_note(note, deck_id)

        r1 = export_collection(col, tmp_path)
        r2 = export_collection(col, tmp_path)

        assert r1.error == ""
        assert r2.error == ""
        assert r2.notes_changed == 0
        assert r2.notetypes_changed == 0

    def test_notetype_dir_roundtrip(self, anki_session, tmp_path):
        from anki_git.formats.notetype_yaml import (
            Notetype,
            notetype_dir_path,
            read_notetype,
            write_notetype,
        )

        col = anki_session.collection
        nt_dict = col.models.by_name("Basic")
        nt = Notetype.from_anki_dict(nt_dict)

        notetypes_root = tmp_path / "notetypes"
        write_notetype(notetypes_root, nt)

        nt_dir = notetype_dir_path(notetypes_root, "Basic")
        loaded = read_notetype(nt_dir)
        assert loaded is not None
        assert loaded.name == "Basic"
        assert len(loaded.fields) == len(nt.fields)
        assert len(loaded.templates) == len(nt.templates)

    def test_notetype_with_js_roundtrip(self, anki_session, tmp_path):
        """Templates with JS special chars must serialize/deserialize cleanly."""
        from anki_git.formats.notetype_yaml import (
            Notetype,
            NotetypeField,
            NotetypeTemplate,
            notetype_dir_path,
            read_notetype,
            write_notetype,
        )

        nt = Notetype(
            name="JS_Test",
            id=999,
            fields=[NotetypeField(name="Front", ord=0)],
            templates=[
                NotetypeTemplate(
                    name="Card 1",
                    ord=0,
                    qfmt="{{Front}}",
                    afmt="""{{FrontSide}}

<script>
let el = document.querySelectorAll('.prettify-tags > *');
if (el) { el.innerHTML = 'test'; }
</script>""",
                )
            ],
            css=".card { font-family: arial; }",
        )

        notetypes_root = tmp_path / "notetypes"
        write_notetype(notetypes_root, nt)
        nt_dir = notetype_dir_path(notetypes_root, "JS_Test")
        loaded = read_notetype(nt_dir)
        assert loaded is not None
        assert loaded.templates[0].afmt == nt.templates[0].afmt
        assert loaded.templates[0].qfmt == nt.templates[0].qfmt

    def test_note_file_export(self, tmp_path):
        from anki_git.formats.notes_md import Note, write_note_file

        note = Note(
            nid=1234567890,
            notetype="Basic",
            tags=["tag1", "tag2"],
            deck="Default",
            fields={"Front": "Hello", "Back": "World"},
        )

        path = write_note_file(tmp_path, note)
        assert path.name == "1234567890.md"
        assert path.exists()
        content = path.read_text()
        assert "Hello" in content
        assert "World" in content

    def test_export_diff_compute(self, anki_session, tmp_path):
        """Full workflow: export → modify note → compute export diff."""
        from anki_git.engine.diff import compute_export_diff
        from anki_git.engine.exporter import export_collection

        col = anki_session.collection

        notetype = col.models.by_name("Basic")
        note = col.new_note(notetype)
        note.fields[0] = "Hello"
        note.fields[1] = "World"
        deck_id = col.decks.all_names_and_ids()[0].id
        col.add_note(note, deck_id)
        nid = note.id

        export_collection(col, tmp_path)

        note2 = col.get_note(nid)
        note2.fields[0] = "Modified"
        col.update_note(note2)

        report = compute_export_diff(col, tmp_path)

        assert report.total_changes > 0
        assert any(d.nid == nid for d in report.note_diffs)


@integration
@pytest.mark.integration
class TestUiAgainstEngine:
    """Exercise UI components against real data (needs aqt/Qt)."""

    def test_diff_view_dialog_creates(self, anki_session, tmp_path):
        """Verify DiffViewDialog instantiates without AttributeError.

        This catches PyQt6 regressions like missing ShowIndicator.
        """
        from aqt.qt import QApplication

        _ = QApplication.instance() or QApplication([])

        from anki_git.engine.diff import DiffReport, FieldDiff, NoteDiff, NotetypeDiff
        from anki_git.ui.diff import DiffDialog

        nd = NoteDiff(
            nid=42,
            deck="Default",
            notetype="Basic",
            change_type="modified",
            field_diffs=[
                FieldDiff(
                    field_name="Front",
                    old_value="Hello",
                    new_value="Modified",
                    diff_lines=["--- Front", "+++ Front", "-Hello", "+Modified"],
                )
            ],
        )
        ntd = NotetypeDiff(
            name="Basic", change_type="modified",
            fields_diff="diff content", css_diff=".card{}",
        )
        report = DiffReport(note_diffs=[nd], notetype_diffs=[ntd])

        dialog = DiffDialog.from_report(report)
        assert dialog is not None

    def test_diff_view_dialog_with_export(self, anki_session, tmp_path):
        """Full workflow: export → modify → compute diff → build dialog."""
        from aqt.qt import QApplication

        _ = QApplication.instance() or QApplication([])

        from anki_git.engine.diff import compute_export_diff
        from anki_git.engine.exporter import export_collection
        from anki_git.ui.diff import DiffDialog

        col = anki_session.collection

        notetype = col.models.by_name("Basic")
        note = col.new_note(notetype)
        note.fields[0] = "Front text"
        note.fields[1] = "Back text"
        deck_id = col.decks.all_names_and_ids()[0].id
        col.add_note(note, deck_id)

        export_collection(col, tmp_path)

        note2 = col.get_note(note.id)
        note2.fields[0] = "Updated front"
        col.update_note(note2)

        report = compute_export_diff(col, tmp_path)

        assert report.has_changes

        dialog = DiffDialog.from_report(report)
        assert dialog is not None


@integration
@pytest.mark.integration
class TestAddonActions:
    """Verify high-level actions in addon.py (glue logic)."""

    def test_snapshot_action_workflow(self, anki_session, tmp_path):
        """Verify snapshot_action triggers the right sequence of QueryOps."""
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        from anki_git.addon import snapshot_action

        with patch("anki_git.addon.load_config") as mock_load_config, \
             patch("aqt.mw", spec=True) as mock_mw, \
             patch("aqt.operations.QueryOp") as mock_query_op, \
             patch("anki_git.ui.DiffDialog") as mock_diff_dialog:

            # Setup config
            config = MagicMock()
            config.repo_path = str(tmp_path)
            config.media_strategy = "none"
            mock_load_config.return_value = config

            # Setup mw
            mock_mw.col = anki_session.collection
            mock_mw.taskman = MagicMock()

            # Track QueryOp calls
            query_ops = []
            def mock_query_op_init(parent, op, success):
                qop = MagicMock()
                query_ops.append({"op": op, "success": success})
                qop.failure.return_value = qop
                qop.with_progress.return_value = qop
                return qop
            mock_query_op.side_effect = mock_query_op_init

            # Trigger action
            snapshot_action()

            assert len(query_ops) == 1
            assert query_ops[0]["op"].__name__ == "get_diff_with_progress"

            # Simulate first QueryOp success
            report = MagicMock()
            report.has_changes = True
            ui_data = []
            mock_diff_dialog.return_value.exec.return_value = True # User accepts

            query_ops[0]["success"]((report, ui_data))

            # Verify second QueryOp (the export) is triggered
            assert len(query_ops) == 2
            assert query_ops[1]["op"].__name__ == "do_export"

            # Verify export operation works
            with patch("anki_git.addon.export_collection") as mock_export:
                query_ops[1]["op"](mock_mw.col)
                mock_export.assert_called_once()
                args, _ = mock_export.call_args
                assert args[0] == mock_mw.col
                assert args[1] == Path(config.repo_path)
