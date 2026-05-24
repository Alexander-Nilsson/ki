"""Diff engine: compute field-level diffs between note/notetype states."""

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from anki_git.formats.notes_md import Note, parse_notes_file
from anki_git.formats.notetype_yaml import Notetype


@dataclass
class FieldDiff:
    field_name: str
    old_value: str
    new_value: str
    diff_lines: List[str] = field(default_factory=list)


@dataclass
class NoteDiff:
    nid: int
    deck: str
    notetype: str
    change_type: str  # "modified", "added", "deleted"
    field_diffs: List[FieldDiff] = field(default_factory=list)
    old_tags: List[str] = field(default_factory=list)
    new_tags: List[str] = field(default_factory=list)
    tags_changed: bool = False
    old_deck: Optional[str] = None
    old_notetype: Optional[str] = None

    @property
    def deck_changed(self) -> bool:
        return self.old_deck is not None and self.old_deck != self.deck

    @property
    def notetype_changed(self) -> bool:
        return self.old_notetype is not None and self.old_notetype != self.notetype

    @property
    def added_lines(self) -> int:
        return sum(
            1 for fd in self.field_diffs
            for l in fd.diff_lines
            if l.startswith("+") and not l.startswith("+++")
        )

    @property
    def deleted_lines(self) -> int:
        return sum(
            1 for fd in self.field_diffs
            for l in fd.diff_lines
            if l.startswith("-") and not l.startswith("---")
        )


@dataclass
class NotetypeDiff:
    name: str
    change_type: str  # "modified", "added", "deleted"
    fields_diff: str = ""
    templates_diff: str = ""
    css_diff: str = ""


@dataclass
class DiffReport:
    note_diffs: List[NoteDiff] = field(default_factory=list)
    notetype_diffs: List[NotetypeDiff] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return len(self.note_diffs) + len(self.notetype_diffs)

    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0


def _unified_diff(old: str, new: str, name: str) -> List[str]:
    return list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=name,
            tofile=name,
            lineterm="",
        )
    )


def compute_note_diff(old_note: Optional[Note], new_note: Note) -> NoteDiff:
    if old_note is None:
        return NoteDiff(
            nid=new_note.nid,
            deck=new_note.deck,
            notetype=new_note.notetype,
            change_type="added",
            field_diffs=[
                FieldDiff(
                    field_name=f,
                    old_value="",
                    new_value=v,
                    diff_lines=_unified_diff("", v, f),
                )
                for f, v in new_note.fields.items()
            ],
            new_tags=new_note.tags,
        )

    if new_note is None:
        return NoteDiff(
            nid=old_note.nid,
            deck=old_note.deck,
            notetype=old_note.notetype,
            change_type="deleted",
            field_diffs=[
                FieldDiff(
                    field_name=f,
                    old_value=v,
                    new_value="",
                    diff_lines=_unified_diff(v, "", f),
                )
                for f, v in old_note.fields.items()
            ],
            old_tags=old_note.tags,
        )

    field_diffs: List[FieldDiff] = []
    all_field_names = list(dict.fromkeys(list(old_note.fields.keys()) + list(new_note.fields.keys())))

    for fname in all_field_names:
        old_val = old_note.fields.get(fname, "")
        new_val = new_note.fields.get(fname, "")
        if old_val != new_val:
            field_diffs.append(
                FieldDiff(
                    field_name=fname,
                    old_value=old_val,
                    new_value=new_val,
                    diff_lines=_unified_diff(old_val, new_val, fname),
                )
            )

    old_tags_set = set(old_note.tags)
    new_tags_set = set(new_note.tags)
    tags_changed = old_tags_set != new_tags_set
    deck_changed = old_note.deck != new_note.deck
    nt_changed = old_note.notetype != new_note.notetype

    return NoteDiff(
        nid=new_note.nid,
        deck=new_note.deck,
        notetype=new_note.notetype,
        change_type="modified" if (field_diffs or tags_changed or deck_changed or nt_changed) else "unchanged",
        field_diffs=field_diffs,
        old_tags=old_note.tags,
        new_tags=new_note.tags,
        tags_changed=tags_changed,
        old_deck=old_note.deck,
        old_notetype=old_note.notetype,
    )


def _notetype_to_canonical(nt) -> dict:
    return {
        "name": nt.name,
        "id": nt.id,
        "fields": [
            {"name": f.name, "ord": f.ord, "font": f.font, "size": f.size, "sticky": f.sticky, "rtl": f.rtl}
            for f in nt.fields
        ],
        "templates": [
            {"name": t.name, "ord": t.ord, "qfmt": t.qfmt, "afmt": t.afmt}
            for t in nt.templates
        ],
    }


def compute_notetype_diff(
    old_nt: Optional[Notetype], new_nt: Notetype
) -> Optional[NotetypeDiff]:
    if old_nt is None:
        return NotetypeDiff(name=new_nt.name, change_type="added", fields_diff="(new notetype)")

    if new_nt is None:
        return NotetypeDiff(name=old_nt.name, change_type="deleted", fields_diff="(deleted notetype)")

    import json
    old_ser = json.dumps(_notetype_to_canonical(old_nt), indent=2, ensure_ascii=False, sort_keys=True)
    new_ser = json.dumps(_notetype_to_canonical(new_nt), indent=2, ensure_ascii=False, sort_keys=True)
    if old_ser == new_ser and old_nt.css == new_nt.css:
        return None

    fields_diff = "\n".join(_unified_diff(old_ser, new_ser, f"{new_nt.name}.json"))
    css_diff = "\n".join(_unified_diff(old_nt.css, new_nt.css, f"{new_nt.name}.css")) if old_nt.css != new_nt.css else ""

    return NotetypeDiff(
        name=new_nt.name,
        change_type="modified",
        fields_diff=fields_diff,
        css_diff=css_diff,
    )


def compute_export_diff(col, repo_path: Path, progress_callback: callable = None) -> DiffReport:
    """Compare current Anki collection vs repo state for export preview."""
    from anki_git.formats.notetype_yaml import read_all_notetypes as _read_nt

    report = DiffReport()

    if progress_callback:
        progress_callback("Reading notetypes...")

    notetypes_dir = repo_path / "notetypes"
    decks_dir = repo_path / "decks"

    old_notetypes = _read_nt(notetypes_dir)
    current_notetypes: Dict[str, Notetype] = {}
    for nt_dict in col.models.all():
        nt = Notetype.from_anki_dict(nt_dict)
        current_notetypes[nt.name] = nt

    all_nt_names = set(list(old_notetypes.keys()) + list(current_notetypes.keys()))
    for name in sorted(all_nt_names):
        old_nt = old_notetypes.get(name)
        new_nt = current_notetypes.get(name)
        diff = compute_notetype_diff(old_nt, new_nt)
        if diff:
            report.notetype_diffs.append(diff)

    nids = col.db.list("SELECT id FROM notes WHERE id > 0")
    total = len(nids)
    repo_notes_by_id: Dict[int, Note] = {}
    if decks_dir.exists():
        files = list(decks_dir.rglob("*.md"))
        for i, notes_file in enumerate(files):
            if progress_callback and i % 50 == 0:
                progress_callback(f"Scanning repo... {i}/{len(files)}")
            for n in parse_notes_file(notes_file):
                repo_notes_by_id[n.nid] = n

    seen_ids = set()
    for i, nid in enumerate(nids):
        if progress_callback and i % 20 == 0:
            progress_callback(f"Diffing notes... {i}/{total}")
        try:
            note_obj = col.get_note(nid)
        except Exception:
            continue
        nt_name = note_obj.note_type()["name"]
        try:
            cards = note_obj.cards()
            if not cards:
                continue
            deck_name = col.decks.name(cards[0].did)
        except Exception:
            continue
        fields = dict(note_obj.items())
        new_note = Note(nid=nid, notetype=nt_name, tags=list(note_obj.tags), deck=deck_name, fields=fields)
        seen_ids.add(nid)

        old_note = repo_notes_by_id.get(nid)
        nd = compute_note_diff(old_note, new_note)
        if nd.change_type != "unchanged":
            report.note_diffs.append(nd)

    for nid, old_note in repo_notes_by_id.items():
        if nid not in seen_ids:
            nd = compute_note_diff(old_note, None)
            report.note_diffs.append(nd)

    return report


def compute_import_diff(col, repo_path: Path, progress_callback: callable = None) -> DiffReport:
    """Compare repo state vs current Anki collection for import preview."""
    from anki_git.formats.notetype_yaml import read_all_notetypes as _read_nt

    report = DiffReport()

    if progress_callback:
        progress_callback("Reading notetypes...")

    notetypes_dir = repo_path / "notetypes"
    decks_dir = repo_path / "decks"

    repo_notetypes = _read_nt(notetypes_dir)
    col_notetypes: Dict[str, Notetype] = {}
    for nt_dict in col.models.all():
        nt = Notetype.from_anki_dict(nt_dict)
        col_notetypes[nt.name] = nt

    all_nt_names = set(list(repo_notetypes.keys()) + list(col_notetypes.keys()))
    for name in sorted(all_nt_names):
        old_nt = col_notetypes.get(name)
        new_nt = repo_notetypes.get(name)
        diff = compute_notetype_diff(old_nt, new_nt)
        if diff:
            report.notetype_diffs.append(diff)

    col_notes_by_id: Dict[int, Note] = {}
    nids = col.db.list("SELECT id FROM notes WHERE id > 0")
    total_col = len(nids)
    for i, nid in enumerate(nids):
        if progress_callback and i % 50 == 0:
            progress_callback(f"Analyzing collection... {i}/{total_col}")
        try:
            note_obj = col.get_note(nid)
        except Exception:
            continue
        nt_name = note_obj.note_type()["name"]
        try:
            cards = note_obj.cards()
            if not cards:
                continue
            deck_name = col.decks.name(cards[0].did)
        except Exception:
            continue
        col_notes_by_id[nid] = Note(nid=nid, notetype=nt_name, tags=list(note_obj.tags), deck=deck_name, fields=dict(note_obj.items()))

    seen_ids = set()
    notes_files = sorted(decks_dir.rglob("*.md")) if decks_dir.exists() else []
    total_files = len(notes_files)
    for i, notes_file in enumerate(notes_files):
        if progress_callback and i % 5 == 0:
            progress_callback(f"Diffing repo files... {i}/{total_files}")
        for repo_note in parse_notes_file(notes_file):
            seen_ids.add(repo_note.nid)
            col_note = col_notes_by_id.get(repo_note.nid)
            nd = compute_note_diff(col_note, repo_note)
            if nd.change_type != "unchanged":
                report.note_diffs.append(nd)

    for nid, col_note in col_notes_by_id.items():
        if nid not in seen_ids:
            nd = compute_note_diff(col_note, None)
            report.note_diffs.append(nd)

    return report
