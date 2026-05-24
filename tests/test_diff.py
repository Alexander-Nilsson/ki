"""Tests for the diff engine."""

from anki_git.formats.notes_md import Note
from anki_git.formats.notetype_yaml import Notetype, NotetypeField
from anki_git.engine.diff import compute_note_diff, compute_notetype_diff


def test_note_diff_no_changes():
    old = Note(nid=1, notetype="Basic", tags=["a"], deck="Default", fields={"Front": "Q", "Back": "A"})
    new = Note(nid=1, notetype="Basic", tags=["a"], deck="Default", fields={"Front": "Q", "Back": "A"})
    nd = compute_note_diff(old, new)
    assert nd.change_type == "unchanged"
    assert nd.field_diffs == []


def test_note_diff_field_changed():
    old = Note(nid=1, notetype="Basic", tags=["a"], deck="Default", fields={"Front": "Old Q", "Back": "A"})
    new = Note(nid=1, notetype="Basic", tags=["a"], deck="Default", fields={"Front": "New Q", "Back": "A"})
    nd = compute_note_diff(old, new)
    assert nd.change_type == "modified"
    assert len(nd.field_diffs) == 1
    assert nd.field_diffs[0].field_name == "Front"
    assert nd.field_diffs[0].old_value == "Old Q"
    assert nd.field_diffs[0].new_value == "New Q"


def test_note_diff_multiple_fields():
    old = Note(nid=1, notetype="Basic", tags=[], deck="Default", fields={"Front": "Q1", "Back": "A1", "Extra": "E1"})
    new = Note(nid=1, notetype="Basic", tags=[], deck="Default", fields={"Front": "Q2", "Back": "A1", "Extra": "E2"})
    nd = compute_note_diff(old, new)
    assert nd.change_type == "modified"
    assert len(nd.field_diffs) == 2
    names = {f.field_name for f in nd.field_diffs}
    assert names == {"Front", "Extra"}


def test_note_diff_tags_changed():
    old = Note(nid=1, notetype="Basic", tags=["a", "b"], deck="Default", fields={"Front": "Q"})
    new = Note(nid=1, notetype="Basic", tags=["a", "c"], deck="Default", fields={"Front": "Q"})
    nd = compute_note_diff(old, new)
    assert nd.change_type == "modified"
    assert nd.tags_changed
    assert nd.field_diffs == []


def test_note_diff_added():
    new = Note(nid=1, notetype="Basic", tags=["a"], deck="Default", fields={"Front": "Q"})
    nd = compute_note_diff(None, new)
    assert nd.change_type == "added"
    assert len(nd.field_diffs) == 1
    assert nd.field_diffs[0].field_name == "Front"


def test_note_diff_deleted():
    old = Note(nid=1, notetype="Basic", tags=["a"], deck="Default", fields={"Front": "Q"})
    nd = compute_note_diff(old, None)
    assert nd.change_type == "deleted"
    assert len(nd.field_diffs) == 1


def test_note_diff_diff_lines_format():
    old = Note(nid=1, notetype="Basic", tags=[], deck="Default", fields={"Front": "Hello"})
    new = Note(nid=1, notetype="Basic", tags=[], deck="Default", fields={"Front": "Hello World"})
    nd = compute_note_diff(old, new)
    assert len(nd.field_diffs) == 1
    lines = nd.field_diffs[0].diff_lines
    assert any(l.startswith("-Hello") for l in lines)
    assert any(l.startswith("+Hello World") for l in lines)


def test_notetype_diff_no_changes():
    old = Notetype(name="Basic", id=1, fields=[], templates=[], css="")
    new = Notetype(name="Basic", id=1, fields=[], templates=[], css="")
    assert compute_notetype_diff(old, new) is None


def test_notetype_diff_field_added():
    old = Notetype(name="Basic", id=1, fields=[], templates=[], css="")
    new = Notetype(name="Basic", id=1, fields=[NotetypeField("Front", 0)], templates=[], css="")
    ntd = compute_notetype_diff(old, new)
    assert ntd is not None
    assert ntd.change_type == "modified"
    assert "Front" in ntd.fields_diff


def test_notetype_diff_added():
    new = Notetype(name="NewType", id=2, fields=[], templates=[], css="")
    ntd = compute_notetype_diff(None, new)
    assert ntd is not None
    assert ntd.change_type == "added"


def test_notetype_diff_deleted():
    old = Notetype(name="OldType", id=1, fields=[], templates=[], css="")
    ntd = compute_notetype_diff(old, None)
    assert ntd is not None
    assert ntd.change_type == "deleted"
