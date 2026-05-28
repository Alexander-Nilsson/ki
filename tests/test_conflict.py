"""Tests for three-way merge conflict detection and notetype merging.

Conflict tests cover all 6 cases:
  1. Changed in Anki AND in Git -> conflict
  2. Changed only in Anki -> Anki wins
  3. Changed only in Git -> Git wins
  4. Deleted in Anki, unchanged in Git -> delete from Git
  5. Deleted in Git, unchanged in Anki -> delete from Anki
  6. Deleted in both -> already gone

Notetype merge tests cover field/template/CSS add/remove/modify.
"""
from anki_git.engine.conflict import (
    ConflictType,
    SyncMode,
    detect_conflicts,
    merge_notetypes,
)
from anki_git.formats.notetype_yaml import Notetype, NotetypeField, NotetypeTemplate

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


# ── Notetype merge tests ──────────────────────────────────────────

def _nt(name: str, fields: list[tuple], templates: list[tuple], css: str = "") -> Notetype:
    return Notetype(
        name=name,
        id=1,
        fields=[NotetypeField(name=f, ord=i, font="Arial", size=20)
                for i, (f,) in enumerate(fields)],
        templates=[NotetypeTemplate(name=t, ord=i, qfmt=qt, afmt=at)
                   for i, (t, qt, at) in enumerate(templates)],
        css=css,
    )


BASE_NT = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])


def test_merge_identical_notetypes():
    a = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])
    merged, conflicts = merge_notetypes(a, a, SyncMode.PREFER_ANKI)
    assert merged.name == "Basic"
    assert len(merged.fields) == 2
    assert len(merged.templates) == 1
    assert len(conflicts) == 0


def test_merge_field_added_in_git():
    a = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])
    g = _nt("Basic", [("Front",), ("Back",), ("Notes",)], [("Card 1", "Q", "A")])
    merged, conflicts = merge_notetypes(a, g, SyncMode.PREFER_ANKI)
    assert len(merged.fields) == 3
    assert merged.fields[2].name == "Notes"
    assert len(conflicts) == 0


def test_merge_field_union_keeps_anki_when_missing_in_git():
    """Merge is a union — fields only in Anki are kept, not removed."""
    a = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])
    g = _nt("Basic", [("Front",)], [("Card 1", "Q", "A")])
    merged, conflicts = merge_notetypes(a, g, SyncMode.PREFER_ANKI)
    assert len(merged.fields) == 2
    names = {f.name for f in merged.fields}
    assert names == {"Front", "Back"}
    assert len(conflicts) == 0


def test_merge_field_modified_different_font():
    a = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])
    g = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])
    g.fields[0].font = "Courier"
    merged, conflicts = merge_notetypes(a, g, SyncMode.PREFER_ANKI)
    assert len(conflicts) == 1
    assert conflicts[0].component_type == "field"
    assert conflicts[0].name == "Front"
    assert conflicts[0].resolved is True
    assert conflicts[0].resolution == "anki"
    front_field = next(f for f in merged.fields if f.name == "Front")
    assert front_field.font == "Arial"


def test_merge_field_modified_prefer_repo():
    a = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])
    g = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])
    g.fields[0].size = 30
    merged, conflicts = merge_notetypes(a, g, SyncMode.PREFER_REPO)
    assert len(conflicts) == 1
    assert conflicts[0].resolved is True
    assert conflicts[0].resolution == "git"
    front_field = next(f for f in merged.fields if f.name == "Front")
    assert front_field.size == 30


def test_merge_template_added_in_git():
    a = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])
    g = _nt("Basic", [("Front",), ("Back",)],
            [("Card 1", "Q", "A"), ("Card 2", "Q2", "A2")])
    merged, conflicts = merge_notetypes(a, g, SyncMode.PREFER_ANKI)
    assert len(merged.templates) == 2
    assert merged.templates[1].name == "Card 2"
    assert len(conflicts) == 0


def test_merge_template_union_keeps_anki_when_missing_in_git():
    """Merge is a union — templates only in Anki are kept."""
    a = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])
    g = _nt("Basic", [("Front",), ("Back",)], [])
    merged, conflicts = merge_notetypes(a, g, SyncMode.PREFER_ANKI)
    assert len(merged.templates) == 1
    assert merged.templates[0].name == "Card 1"
    assert len(conflicts) == 0


def test_merge_template_modified():
    a = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])
    g = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "NewQ", "A")])
    merged, conflicts = merge_notetypes(a, g, SyncMode.PREFER_ANKI)
    assert len(conflicts) == 1
    assert conflicts[0].component_type == "template"
    assert conflicts[0].name == "Card 1"
    assert conflicts[0].resolved is True
    assert conflicts[0].resolution == "anki"
    assert merged.templates[0].qfmt == "Q"


def test_merge_css_changed():
    a = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")], css=".card { color: black; }")
    g = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")], css=".card { color: red; }")
    merged, conflicts = merge_notetypes(a, g, SyncMode.PREFER_ANKI)
    assert len(conflicts) == 1
    assert conflicts[0].component_type == "css"
    assert merged.css == ".card { color: black; }"


def test_merge_css_prefer_repo():
    a = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")], css=".card { color: black; }")
    g = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")], css=".card { color: red; }")
    merged, conflicts = merge_notetypes(a, g, SyncMode.PREFER_REPO)
    assert merged.css == ".card { color: red; }"


def test_merge_always_ask_leaves_conflicts_unresolved():
    a = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])
    g = _nt("Basic", [("Front",), ("Back",)], [("Card 1", "Q", "A")])
    g.fields[0].font = "Courier"
    merged, conflicts = merge_notetypes(a, g, SyncMode.ALWAYS_ASK)
    assert len(conflicts) == 1
    assert conflicts[0].resolved is False
    front_field = next(f for f in merged.fields if f.name == "Front")
    assert front_field.font == "Arial"


def test_merge_multiple_changes():
    a = _nt("Basic", [("Front",), ("Back",), ("Notes",)],
            [("Card 1", "Q", "A")], css="body {}")
    g = _nt("Basic", [("Front",), ("Notes",)],
            [("Card 1", "Q", "A"), ("Card 2", "Q2", "A2")], css="div {}")
    merged, conflicts = merge_notetypes(a, g, SyncMode.PREFER_ANKI)
    assert len(merged.templates) == 2
    assert len(merged.fields) >= 3  # union with (name, ord) matching
    field_names = {f.name for f in merged.fields}
    assert "Front" in field_names
    assert "Back" in field_names
    assert "Notes" in field_names
    css_confs = [c for c in conflicts if c.component_type == "css"]
    assert len(css_confs) == 1
    assert css_confs[0].name == "style.css"
