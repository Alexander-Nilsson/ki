"""Tests for three-way merge conflict detection.

Tests all 6 conflict cases:
  1. Changed in Anki AND in Git -> conflict
  2. Changed only in Anki -> Anki wins
  3. Changed only in Git -> Git wins
  4. Deleted in Anki, unchanged in Git -> delete from Git
  5. Deleted in Git, unchanged in Anki -> delete from Anki
  6. Deleted in both -> already gone
"""
from anki_git.engine.conflict import (
    detect_conflicts,
    ConflictType,
)


BASE = {
    "1": "base1",
    "2": "base2",
    "3": "base3",
    "4": "base4",
    "5": "base5",
    "6": "base6",
}


def test_conflict_changed_in_both():
    anki = {"1": "anki1"}
    git = {"1": "git1"}
    report = detect_conflicts(BASE, anki, git)
    conflicts = [c for c in report.conflicts if c.nid == 1]
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == ConflictType.CONFLICT


def test_anki_wins_when_only_anki_changed():
    anki = {"2": "anki2"}
    git = {"2": "base2"}
    report = detect_conflicts(BASE, anki, git)
    c = [c for c in report.conflicts if c.nid == 2][0]
    assert c.conflict_type == ConflictType.ANKI_WINS


def test_git_wins_when_only_git_changed():
    anki = {"3": "base3"}
    git = {"3": "git3"}
    report = detect_conflicts(BASE, anki, git)
    c = [c for c in report.conflicts if c.nid == 3][0]
    assert c.conflict_type == ConflictType.GIT_WINS


def test_delete_from_git_when_deleted_in_anki():
    anki = {}
    git = {"4": "base4"}
    report = detect_conflicts(BASE, anki, git)
    c = [c for c in report.conflicts if c.nid == 4][0]
    assert c.conflict_type == ConflictType.DELETE_FROM_GIT


def test_delete_from_anki_when_deleted_in_git():
    anki = {"5": "base5"}
    git = {}
    report = detect_conflicts(BASE, anki, git)
    c = [c for c in report.conflicts if c.nid == 5][0]
    assert c.conflict_type == ConflictType.DELETE_FROM_ANKI


def test_already_gone_when_deleted_in_both():
    anki = {}
    git = {}
    base = {"6": "base6"}
    report = detect_conflicts(base, anki, git)
    c = [c for c in report.conflicts if c.nid == 6][0]
    assert c.conflict_type == ConflictType.ALREADY_GONE


def test_no_conflicts_when_unchanged():
    report = detect_conflicts(BASE, BASE, BASE)
    assert len(report.conflicts) == 0


def test_report_has_conflicts_property():
    anki = {"1": "anki1"}
    git = {"1": "git1"}
    report = detect_conflicts(BASE, anki, git)
    assert report.has_conflicts is True

    report2 = detect_conflicts(BASE, BASE, BASE)
    assert report2.has_conflicts is False


def test_mixed_scenarios():
    anki = {
        "1": "anki1",
        "2": "anki2",
        "3": "base3",
        "5": "base5",
    }
    git = {
        "1": "git1",
        "2": "base2",
        "3": "git3",
        "4": "base4",
    }
    report = detect_conflicts(BASE, anki, git)
    types = {c.nid: c.conflict_type for c in report.conflicts}
    assert types[1] == ConflictType.CONFLICT
    assert types[2] == ConflictType.ANKI_WINS
    assert types[3] == ConflictType.GIT_WINS
    assert types[4] == ConflictType.DELETE_FROM_GIT
    assert types[5] == ConflictType.DELETE_FROM_ANKI
    assert types[6] == ConflictType.ALREADY_GONE
