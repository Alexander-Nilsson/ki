"""Tests for Markdown note serialization/deserialization."""
from pathlib import Path
import tempfile

from anki_git.formats.notes_md import (
    Note,
    parse_note_section,
    parse_notes_file,
    write_notes_file,
)


SINGLE_NOTE = """\
<!-- note: nid=1234567890 notetype=Basic tags=japanese::vocab deck=Japanese::N5 -->
## Front
日本語

## Back
Japanese language
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


def test_parse_invalid_nid_non_digit():
    """Non-digit nid doesn't match HEADER_PATTERN (which requires digits only)."""
    text = "<!-- note: nid=abc notetype=Basic tags=tag1 deck=Default -->\n## Front\nHello"
    assert parse_note_section(text) is None


def test_parse_invalid_nid_negative():
    """Negative nid doesn't match HEADER_PATTERN either."""
    text = "<!-- note: nid=-123 notetype=Basic tags=tag1 deck=Default -->\n## Front\nHello"
    assert parse_note_section(text) is None


def test_parse_missing_notetype():
    """Header missing notetype is rejected."""
    text = "<!-- note: nid=123 tags=tag1 deck=Default -->\n## Front\nHello"
    assert parse_note_section(text) is None


def test_parse_missing_nid():
    """Header missing nid is rejected."""
    text = "<!-- note: notetype=Basic tags=tag1 deck=Default -->\n## Front\nHello"
    assert parse_note_section(text) is None


def test_parse_unclosed_comment():
    """Unclosed HTML comment returns None."""
    text = "<!-- note: nid=123 notetype=Basic tags=tag1 deck=Default\n## Front\nHello"
    assert parse_note_section(text) is None


def test_parse_single_hash_heading_treated_as_content():
    """Single # heading is not a field separator; content before any ## heading is discarded."""
    text = "<!-- note: nid=1 notetype=Basic tags= deck=Default -->\n# Front\nHello\n## Back\nWorld"
    note = parse_note_section(text)
    assert note is not None
    # "# Front\nHello" appears before the first ## heading, so it is discarded
    assert note.fields == {"Back": "World"}


def test_parse_content_before_header():
    """Text before the header comment makes the first line not match, returning None."""
    text = "garbage\n<!-- note: nid=123 notetype=Basic tags= deck=Default -->\n## Front\nHello"
    assert parse_note_section(text) is None


def test_parse_duplicate_field_names():
    """When duplicate field names appear, the last occurrence wins."""
    text = "<!-- note: nid=1 notetype=Basic tags= deck=Default -->\n## Front\nFirst\n## Front\nSecond"
    note = parse_note_section(text)
    assert note is not None
    assert note.fields["Front"] == "Second"


def test_parse_tags_with_trailing_colon():
    """Tags like 'foo::bar::' produce an empty trailing tag component."""
    text = "<!-- note: nid=1 notetype=Basic tags=foo::bar:: deck=Default -->\n## Front\nHello"
    note = parse_note_section(text)
    assert note is not None
    assert note.tags == ["foo", "bar", ""]


def test_parse_whitespace_only_field():
    """A field containing only whitespace should be preserved."""
    text = "<!-- note: nid=1 notetype=Basic tags= deck=Default -->\n## Front\n   \n## Back\nHello"
    note = parse_note_section(text)
    assert note is not None
    assert note.fields["Front"] == "   "
    assert note.fields["Back"] == "Hello"


def test_parse_file_skips_invalid_notes():
    """parse_notes_file silently skips sections that don't parse as valid notes."""
    content = (
        '<!-- note: nid=1 notetype=Basic tags= deck=Default -->\n## Front\nValid\n'
        '\n'
        'this is not a valid note header\n'
        '\n'
        '<!-- note: nid=2 notetype=Basic tags= deck=Default -->\n## Front\nAlso valid'
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "notes.md"
        path.write_text(content, encoding="utf-8")
        notes = parse_notes_file(path)
        assert len(notes) == 2
        assert notes[0].nid == 1
        assert notes[1].nid == 2


def test_parse_file_fully_malformed():
    """A file with no valid note headers returns an empty list."""
    content = "# Just a heading\n\nSome random text\n\n## Another heading"
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "notes.md"
        path.write_text(content, encoding="utf-8")
        notes = parse_notes_file(path)
        assert notes == []


def test_parse_field_with_extra_newlines():
    """Extra blank lines inside a field are preserved as content."""
    text = "<!-- note: nid=1 notetype=Basic tags= deck=Default -->\n## Front\nLine1\n\nLine3\n## Back\nEnd"
    note = parse_note_section(text)
    assert note is not None
    assert note.fields["Front"] == "Line1\n\nLine3"
    assert note.fields["Back"] == "End"
