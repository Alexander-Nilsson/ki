import re
from pathlib import Path
from typing import Dict, List, Optional


HEADER_PATTERN = re.compile(
    r"<!--\s*note:\s*nid=(?P<nid>\d+)\s+notetype=(?P<notetype>\S+)"
    r"(?:\s+tags=(?P<tags>\S*))?"
    r"(?:\s+deck=(?P<deck>.+?))?\s*-->"
)


class NoteField:
    def __init__(self, name: str, content: str):
        self.name = name
        self.content = content


class Note:
    def __init__(
        self,
        nid: int,
        notetype: str,
        tags: List[str],
        deck: str,
        fields: Dict[str, str],
    ):
        self.nid = nid
        self.notetype = notetype
        self.tags = tags
        self.deck = deck
        self.fields = fields

    def serialize(self) -> str:
        parts = [
            f"<!-- note: nid={self.nid} notetype={self.notetype} tags={'::'.join(self.tags)} deck={self.deck} -->",
        ]
        for name, content in self.fields.items():
            parts.append(f"## {name}")
            if content:
                parts.append(content)
            parts.append("")
        return "\n".join(parts).rstrip("\n") + "\n"


def parse_note_section(text: str) -> Optional[Note]:
    lines = text.strip().split("\n")
    if not lines:
        return None

    header_match = HEADER_PATTERN.match(lines[0])
    if not header_match:
        return None

    nid = int(header_match.group("nid"))
    notetype = header_match.group("notetype")
    tags_str = header_match.group("tags")
    deck = header_match.group("deck")
    tags = tags_str.split("::") if tags_str else []

    fields = {}
    current_name = None
    current_lines = []

    for line in lines[1:]:
        field_match = re.match(r"^##\s+(.+)$", line)
        if field_match:
            if current_name is not None:
                fields[current_name] = "\n".join(current_lines).strip()
            current_name = field_match.group(1).strip()
            current_lines = []
        elif current_name is not None:
            current_lines.append(line)

    if current_name is not None:
        fields[current_name] = "\n".join(current_lines).strip()

    return Note(nid=nid, notetype=notetype, tags=tags, deck=deck, fields=fields)


def parse_notes_file(path: Path) -> List[Note]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"\n(?=<!--\s*note:)", text)
    notes = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        note = parse_note_section(section)
        if note:
            notes.append(note)
    return notes


def serialize_notes(notes: List[Note]) -> str:
    return "\n".join(n.serialize() for n in notes) + "\n"


def write_notes_file(path: Path, notes: List[Note]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_notes(notes), encoding="utf-8")
