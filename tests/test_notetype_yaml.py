"""Tests for notetype YAML serialization/deserialization."""
from pathlib import Path
import tempfile

from anki_git.formats.notetype_yaml import (
    Notetype,
    NotetypeField,
    NotetypeTemplate,
    write_notetype,
    read_notetype,
    read_all_notetypes,
)


BASIC_NT = Notetype(
    name="Basic",
    id=1234567890,
    fields=[
        NotetypeField(name="Front", ord=0),
        NotetypeField(name="Back", ord=1),
    ],
    templates=[
        NotetypeTemplate(
            name="Card 1",
            ord=0,
            qfmt="{{Front}}",
            afmt="{{FrontSide}}\n\n<hr id=answer>\n\n{{Back}}",
        ),
    ],
    css=".card { font-family: arial; font-size: 20px; }",
    sort_field=0,
    type=0,
)


CLOZE_NT = Notetype(
    name="Cloze",
    id=9876543210,
    fields=[
        NotetypeField(name="Text", ord=0, font="Arial", size=20),
        NotetypeField(name="Extra", ord=1, font="Arial", size=20),
    ],
    templates=[
        NotetypeTemplate(
            name="Cloze",
            ord=0,
            qfmt="{{cloze:Text}}",
            afmt="{{cloze:Text}}<br>\n{{Extra}}",
        ),
    ],
    css=".card { font-family: arial; font-size: 20px; }\n.cloze { font-weight: bold; color: blue; }",
    sort_field=0,
    type=1,
)


def test_round_trip_basic():
    lines = BASIC_NT.to_yaml_lines()
    nt2 = Notetype.from_yaml_lines(lines)
    assert nt2.name == "Basic"
    assert nt2.id == 1234567890
    assert len(nt2.fields) == 2
    assert nt2.fields[0].name == "Front"
    assert nt2.fields[0].ord == 0
    assert nt2.fields[1].name == "Back"
    assert nt2.fields[1].ord == 1
    assert len(nt2.templates) == 1
    assert nt2.templates[0].name == "Card 1"
    assert "{{Front}}" in nt2.templates[0].qfmt
    assert nt2.css == ".card { font-family: arial; font-size: 20px; }"
    assert nt2.sort_field == 0
    assert nt2.type == 0


def test_round_trip_cloze():
    lines = CLOZE_NT.to_yaml_lines()
    nt2 = Notetype.from_yaml_lines(lines)
    assert nt2.name == "Cloze"
    assert nt2.type == 1
    assert len(nt2.fields) == 2
    assert nt2.fields[0].name == "Text"
    assert "cloze" in nt2.templates[0].qfmt
    assert "color: blue" in nt2.css


def test_round_trip_preserves_css():
    lines = BASIC_NT.to_yaml_lines()
    nt2 = Notetype.from_yaml_lines(lines)
    assert nt2.css == BASIC_NT.css


def test_write_and_read_notetype_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        notetypes_dir = Path(tmpdir) / "notetypes"
        write_notetype(notetypes_dir, BASIC_NT)

        yaml_path, css_path = notetypes_dir / "Basic.yaml", notetypes_dir / "Basic.css"
        assert yaml_path.exists()
        assert css_path.exists()
        assert ".card {" in css_path.read_text(encoding="utf-8")

        nt = read_notetype(yaml_path)
        assert nt is not None
        assert nt.name == "Basic"
        assert nt.css == BASIC_NT.css


def test_read_all_notetypes():
    with tempfile.TemporaryDirectory() as tmpdir:
        notetypes_dir = Path(tmpdir) / "notetypes"
        write_notetype(notetypes_dir, BASIC_NT)
        write_notetype(notetypes_dir, CLOZE_NT)

        notetypes = read_all_notetypes(notetypes_dir)
        assert len(notetypes) == 2
        assert "Basic" in notetypes
        assert "Cloze" in notetypes


def test_js_heavy_template_roundtrip():
    """Templates with JS containing single quotes and newlines must round-trip."""
    afmt = """{{FrontSide}}

<script>
let l = document.querySelectorAll('.prettify-tags > *');
if (tag) { }
</script>"""
    nt = Notetype(
        name="JS_Heavy",
        id=999,
        fields=[NotetypeField(name="Front", ord=0)],
        templates=[
            NotetypeTemplate(
                name="Card 1",
                ord=0,
                qfmt="{{Front}}",
                afmt=afmt,
            ),
        ],
        css=".card { }",
    )
    lines = nt.to_yaml_lines()
    nt2 = Notetype.from_yaml_lines(lines)
    assert nt2.templates[0].afmt == afmt
    assert nt2.templates[0].qfmt == "{{Front}}"


def test_template_with_tabs_and_quotes_roundtrip():
    """Templates with tabs (forces double-quoted YAML mode) must round-trip."""
    afmt = "{{FrontSide}}\n\n<script>\nlet el = document.querySelectorAll(\"\t.prettify-tags > *\");\nif (el) { el.innerHTML = \"test\"; }\n</script>"
    nt = Notetype(
        name="Tabs_And_Quotes",
        id=888,
        fields=[NotetypeField(name="Front", ord=0)],
        templates=[
            NotetypeTemplate(
                name="Card 1",
                ord=0,
                qfmt="{{Front}}",
                afmt=afmt,
            ),
        ],
        css=".card { }",
    )
    lines = nt.to_yaml_lines()
    nt2 = Notetype.from_yaml_lines(lines)
    assert nt2.templates[0].afmt == afmt


def test_from_anki_dict():
    anki_dict = {
        "name": "Basic",
        "id": 1234567890,
        "flds": [
            {"name": "Front", "ord": 0, "font": "Arial", "size": 20, "sticky": False},
            {"name": "Back", "ord": 1, "font": "Arial", "size": 20, "sticky": False},
        ],
        "tmpls": [
            {"name": "Card 1", "ord": 0, "qfmt": "{{Front}}", "afmt": "{{FrontSide}}"},
        ],
        "css": ".card { }",
        "sortf": 0,
        "type": 0,
    }
    nt = Notetype.from_anki_dict(anki_dict)
    assert nt.name == "Basic"
    assert nt.id == 1234567890
    assert len(nt.fields) == 2
    assert len(nt.templates) == 1
    assert nt.sort_field == 0
