"""Tests for Markdown note serialization/deserialization."""
from pathlib import Path
import tempfile

from anki_git.formats.notes_md import (
    Note,
    parse_note_section,
    parse_notes_file,
    serialize_notes,
    write_notes_file,
)


SINGLE_NOTE = """\
<!-- note: nid=1234567890 notetype=Basic tags=japanese::vocab deck=Japanese::N5 -->
## Front
日本語

## Back
Japanese language
"""

TWO_NOTES = """\
<!-- note: nid=1234567890 notetype=Basic tags=japanese::vocab deck=Japanese::N5 -->
## Front
日本語

## Back
Japanese language

<!-- note: nid=9876543210 notetype=Cloze tags=math deck=Math::Calculus -->
## Text
The derivative of {{c1::sin(x)}} is {{c2::cos(x)}}
"""

NOTE_WITH_EMPTY_FIELD = """\
<!-- note: nid=1111111111 notetype=Basic tags= deck=Default -->
## Front
Hello

## Back
"""


def test_parse_single_note():
    note = parse_note_section(SINGLE_NOTE)
    assert note is not None
    assert note.nid == 1234567890
    assert note.notetype == "Basic"
    assert note.tags == ["japanese", "vocab"]
    assert note.deck == "Japanese::N5"
    assert len(note.fields) == 2
    assert note.fields["Front"] == "日本語"
    assert note.fields["Back"] == "Japanese language"


def test_parse_two_notes():
    text = TWO_NOTES
    sections = text.strip().split("\n\n")
    # Rejoin to simulate the file
    note1 = parse_note_section(
        "<!-- note: nid=1234567890 notetype=Basic tags=japanese::vocab deck=Japanese::N5 -->\n## Front\n日本語\n\n## Back\nJapanese language"
    )
    assert note1 is not None
    assert note1.nid == 1234567890

    note2 = parse_note_section(
        "<!-- note: nid=9876543210 notetype=Cloze tags=math deck=Math::Calculus -->\n## Text\nThe derivative of {{c1::sin(x)}} is {{c2::cos(x)}}"
    )
    assert note2 is not None
    assert note2.nid == 9876543210
    assert note2.notetype == "Cloze"
    assert "c1" in note2.fields["Text"]


def test_parse_with_empty_field():
    note = parse_note_section(NOTE_WITH_EMPTY_FIELD)
    assert note is not None
    assert note.nid == 1111111111
    assert note.fields["Front"] == "Hello"
    assert note.fields["Back"] == ""


def test_serialize_round_trip():
    note = Note(
        nid=1234567890,
        notetype="Basic",
        tags=["japanese", "vocab"],
        deck="Japanese::N5",
        fields={"Front": "日本語", "Back": "Japanese language"},
    )
    serialized = note.serialize()
    parsed = parse_note_section(serialized)
    assert parsed is not None
    assert parsed.nid == note.nid
    assert parsed.notetype == note.notetype
    assert parsed.tags == note.tags
    assert parsed.deck == note.deck
    assert parsed.fields == note.fields


def test_serialize_preserves_cloze():
    note = Note(
        nid=9876543210,
        notetype="Cloze",
        tags=["math"],
        deck="Math::Calculus",
        fields={"Text": "The derivative of {{c1::sin(x)}} is {{c2::cos(x)}}"},
    )
    serialized = note.serialize()
    assert "c1" in serialized
    assert "c2" in serialized
    assert "Cloze" in serialized


def test_write_and_read_notes_file():
    notes = [
        Note(nid=1, notetype="Basic", tags=["a"], deck="Default", fields={"Front": "Q1", "Back": "A1"}),
        Note(nid=2, notetype="Basic", tags=["b"], deck="Default", fields={"Front": "Q2", "Back": "A2"}),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "notes.md"
        write_notes_file(path, notes)
        assert path.exists()

        parsed = parse_notes_file(path)
        assert len(parsed) == 2
        assert parsed[0].nid == 1
        assert parsed[1].nid == 2


def test_parse_empty_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "notes.md"
        path.write_text("", encoding="utf-8")
        notes = parse_notes_file(path)
        assert notes == []


def test_parse_nonexistent_file():
    notes = parse_notes_file(Path("/nonexistent/notes.md"))
    assert notes == []


def test_missing_header_returns_none():
    result = parse_note_section("## Front\nHello\n\n## Back\nWorld")
    assert result is None
