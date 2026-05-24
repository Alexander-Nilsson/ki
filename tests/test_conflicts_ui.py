"""Tests for the conflict resolution UI dialog."""

import pytest

from anki_git.engine.conflict import ConflictReport, ConflictType, NoteConflict


class TestConflictResolutionDialogLogic:
    """Test the conflict resolution logic by creating reports directly."""

    def test_report_has_conflicts_true(self):
        report = ConflictReport(conflicts=[
            NoteConflict(nid=1, conflict_type=ConflictType.CONFLICT),
        ])
        assert report.has_conflicts is True

    def test_report_has_conflicts_false(self):
        report = ConflictReport(conflicts=[
            NoteConflict(nid=1, conflict_type=ConflictType.ANKI_WINS),
            NoteConflict(nid=1, conflict_type=ConflictType.GIT_WINS),
        ])
        assert report.has_conflicts is False

    def test_resolve_all_conflicts(self):
        """Simulate what _resolve_all does in the dialog."""
        report = ConflictReport(conflicts=[
            NoteConflict(nid=1, conflict_type=ConflictType.CONFLICT),
            NoteConflict(nid=2, conflict_type=ConflictType.CONFLICT),
        ])
        for c in report.conflicts:
            if c.conflict_type == ConflictType.CONFLICT:
                c.resolution = "anki"
                c.resolved = True

        assert all(c.resolved for c in report.conflicts)
        assert all(c.resolution == "anki" for c in report.conflicts)

    def test_partial_resolution(self):
        """Only CONFLICT type notes need resolution."""
        report = ConflictReport(conflicts=[
            NoteConflict(nid=1, conflict_type=ConflictType.CONFLICT),
            NoteConflict(nid=2, conflict_type=ConflictType.ANKI_WINS),
            NoteConflict(nid=3, conflict_type=ConflictType.GIT_WINS),
        ])
        for c in report.conflicts:
            if c.conflict_type == ConflictType.CONFLICT:
                c.resolution = "git"
                c.resolved = True

        # ANKI_WINS and GIT_WINS should have been auto-resolved (they are
        # not CONFLICT type, so resolve_conflicts handles them)
        from anki_git.engine.conflict import resolve_conflicts
        resolve_conflicts(report, "always_ask")

        assert report.conflicts[0].resolved is True  # manually resolved
        assert report.conflicts[1].resolved is True  # auto-resolved
        assert report.conflicts[2].resolved is True  # auto-resolved


@pytest.mark.integration
class TestConflictDialogWithQt:
    """Test that ConflictResolutionDialog can be instantiated (needs aqt)."""

    def test_dialog_instantiates(self):
        """Verify dialog creates without error (smoke test)."""
        from aqt.qt import QApplication, QWidget
        _ = QApplication.instance() or QApplication([])

        from anki_git.ui.conflicts import ConflictResolutionDialog

        report = ConflictReport(conflicts=[
            NoteConflict(nid=1, conflict_type=ConflictType.CONFLICT),
            NoteConflict(nid=2, conflict_type=ConflictType.ANKI_WINS),
        ])
        parent = QWidget()
        dialog = ConflictResolutionDialog(report, parent)
        assert dialog is not None
        assert dialog.resolved_report == report
        parent.deleteLater()
