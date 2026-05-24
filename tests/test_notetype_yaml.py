"""Tests for notetype directory serialization/deserialization."""
import json
from pathlib import Path
import tempfile

from anki_git.formats.notetype_yaml import (
    Notetype,
    NotetypeField,
    NotetypeTemplate,
    write_notetype,
    read_notetype,
    read_all_notetypes,
    notetype_dir_path,
    notetype_paths,
)


BASIC_NT = Notetype(
    name="Basic",
    id=1234567890,
    fields=[
        NotetypeField(name="Front", ord=0, nt_id=1001),
        NotetypeField(name="Back", ord=1, nt_id=1002),
    ],
    templates=[
        NotetypeTemplate(
            name="Card 1",
            ord=0,
            qfmt="{{Front}}",
            afmt="{{FrontSide}}\n\n<hr id=answer>\n\n{{Back}}",
            nt_id=2001,
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
        NotetypeField(name="Text", ord=0, font="Arial", size=20, nt_id=1003),
        NotetypeField(name="Extra", ord=1, font="Arial", size=20, nt_id=1004),
    ],
    templates=[
        NotetypeTemplate(
            name="Cloze",
            ord=0,
            qfmt="{{cloze:Text}}",
            afmt="{{cloze:Text}}<br>\n{{Extra}}",
            nt_id=2002,
        ),
    ],
    css=".card { font-family: arial; font-size: 20px; }\n.cloze { font-weight: bold; color: blue; }",
    sort_field=0,
    type=1,
)


def test_write_and_read_notetype():
    with tempfile.TemporaryDirectory() as tmpdir:
        notetypes_root = Path(tmpdir) / "notetypes"
        write_notetype(notetypes_root, BASIC_NT)

        nt_dir = notetype_dir_path(notetypes_root, "Basic")
        assert nt_dir.is_dir()
        assert (nt_dir / "meta.json").exists()
        assert (nt_dir / "fields.json").exists()
        assert (nt_dir / "style.css").exists()
        assert (nt_dir / "Card 1").is_dir()
        assert (nt_dir / "Card 1" / "front.html").exists()
        assert (nt_dir / "Card 1" / "back.html").exists()

        meta = json.loads((nt_dir / "meta.json").read_text(encoding="utf-8"))
        assert meta["name"] == "Basic"
        assert meta["id"] == 1234567890
        assert meta["type"] == 0

        fields = json.loads((nt_dir / "fields.json").read_text(encoding="utf-8"))
        assert len(fields) == 2
        assert fields[0]["name"] == "Front"
        assert fields[0]["id"] == 1001

        templates = json.loads((nt_dir / "templates.json").read_text(encoding="utf-8"))
        assert len(templates) == 1
        assert templates[0]["name"] == "Card 1"
        assert templates[0]["id"] == 2001

        css = (nt_dir / "style.css").read_text(encoding="utf-8")
        assert "font-family: arial" in css

        front = (nt_dir / "Card 1" / "front.html").read_text(encoding="utf-8")
        assert front == "{{Front}}"

        back = (nt_dir / "Card 1" / "back.html").read_text(encoding="utf-8")
        assert "{{FrontSide}}" in back


def test_read_notetype():
    with tempfile.TemporaryDirectory() as tmpdir:
        notetypes_root = Path(tmpdir) / "notetypes"
        write_notetype(notetypes_root, BASIC_NT)

        nt_dir = notetype_dir_path(notetypes_root, "Basic")
        nt = read_notetype(nt_dir)
        assert nt is not None
        assert nt.name == "Basic"
        assert nt.id == 1234567890
        assert len(nt.fields) == 2
        assert nt.fields[0].name == "Front"
        assert nt.fields[0].id == 1001
        assert nt.fields[1].name == "Back"
        assert len(nt.templates) == 1
        assert nt.templates[0].name == "Card 1"
        assert nt.templates[0].qfmt == "{{Front}}"
        assert nt.templates[0].id == 2001
        assert nt.css == BASIC_NT.css
        assert nt.sort_field == 0
        assert nt.type == 0


def test_read_all_notetypes():
    with tempfile.TemporaryDirectory() as tmpdir:
        notetypes_root = Path(tmpdir) / "notetypes"
        write_notetype(notetypes_root, BASIC_NT)
        write_notetype(notetypes_root, CLOZE_NT)

        notetypes = read_all_notetypes(notetypes_root)
        assert len(notetypes) == 2
        assert "Basic" in notetypes
        assert "Cloze" in notetypes


def test_notetype_equality():
    nt1 = Notetype(
        name="Test", id=1,
        fields=[NotetypeField(name="F", ord=0)],
        templates=[NotetypeTemplate(name="C1", ord=0, qfmt="{{F}}", afmt="{{F}}")],
        css=".card {}",
    )
    nt2 = Notetype(
        name="Test", id=1,
        fields=[NotetypeField(name="F", ord=0)],
        templates=[NotetypeTemplate(name="C1", ord=0, qfmt="{{F}}", afmt="{{F}}")],
        css=".card {}",
    )
    assert nt1 == nt2


def test_notetype_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        notetypes_root = Path(tmpdir) / "notetypes"
        write_notetype(notetypes_root, BASIC_NT)

        paths = notetype_paths(notetypes_root, "Basic")
        filenames = {p.name for p in paths}
        assert "meta.json" in filenames
        assert "fields.json" in filenames
        assert "templates.json" in filenames
        assert "style.css" in filenames
        assert any("front.html" in str(p) for p in paths)
        assert any("back.html" in str(p) for p in paths)


def test_from_anki_dict():
    anki_dict = {
        "name": "Basic",
        "id": 1234567890,
        "flds": [
            {"name": "Front", "ord": 0, "font": "Arial", "size": 20, "sticky": False, "id": 1001},
            {"name": "Back", "ord": 1, "font": "Arial", "size": 20, "sticky": False, "id": 1002},
        ],
        "tmpls": [
            {"name": "Card 1", "ord": 0, "qfmt": "{{Front}}", "afmt": "{{FrontSide}}", "id": 2001},
        ],
        "css": ".card { }",
        "sortf": 0,
        "type": 0,
    }
    nt = Notetype.from_anki_dict(anki_dict)
    assert nt.name == "Basic"
    assert nt.id == 1234567890
    assert len(nt.fields) == 2
    assert nt.fields[0].id == 1001
    assert len(nt.templates) == 1
    assert nt.templates[0].id == 2001
    assert nt.sort_field == 0
