"""Diff engine: compute field-level diffs between note/notetype states."""

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

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
            for line in fd.diff_lines
            if line.startswith("+") and not line.startswith("+++")
        )

    @property
    def deleted_lines(self) -> int:
        return sum(
            1 for fd in self.field_diffs
            for line in fd.diff_lines
            if line.startswith("-") and not line.startswith("---")
        )


@dataclass
class ComponentChange:
    component_type: str  # "field", "template", "css"
    name: str
    status: str  # "added", "removed", "modified"
    old_value: str = ""
    new_value: str = ""


@dataclass
class NotetypeDiff:
    name: str
    change_type: str  # "modified", "added", "deleted"
    component_changes: List[ComponentChange] = field(default_factory=list)
    # legacy fields kept for backwards compat
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


def compute_note_diff(old_note: Optional[Note], new_note: Optional[Note]) -> NoteDiff:
    if old_note is None:
        assert new_note is not None
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
        assert old_note is not None
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


def _diff_field_lists(old_fields, new_fields) -> List[ComponentChange]:
    changes = []
    old_by_name = {f.name: f for f in old_fields}
    new_by_name = {f.name: f for f in new_fields}
    all_names = set(old_by_name) | set(new_by_name)
    for name in sorted(all_names):
        of = old_by_name.get(name)
        nf = new_by_name.get(name)
        if of is None:
            assert nf is not None
            changes.append(ComponentChange(
                component_type="field", name=name, status="added",
                new_value=f"ord={nf.ord}"
            ))
        elif nf is None:
            assert of is not None
            changes.append(ComponentChange(
                component_type="field", name=name, status="removed",
                old_value=f"ord={of.ord}"
            ))
        elif (of.ord, of.font, of.size, of.sticky, of.rtl) != (nf.ord, nf.font, nf.size, nf.sticky, nf.rtl):
            changes.append(ComponentChange(
                component_type="field", name=name, status="modified",
                old_value=f"ord={of.ord} font={of.font} size={of.size}",
                new_value=f"ord={nf.ord} font={nf.font} size={nf.size}",
            ))
    return changes


def _diff_template_lists(old_tmpls, new_tmpls) -> List[ComponentChange]:
    changes = []
    old_by_name = {t.name: t for t in old_tmpls}
    new_by_name = {t.name: t for t in new_tmpls}
    all_names = set(old_by_name) | set(new_by_name)
    for name in sorted(all_names):
        ot = old_by_name.get(name)
        nt = new_by_name.get(name)
        if ot is None:
            changes.append(ComponentChange(
                component_type="template", name=name, status="added"
            ))
        elif nt is None:
            changes.append(ComponentChange(
                component_type="template", name=name, status="removed"
            ))
        elif ot.qfmt != nt.qfmt or ot.afmt != nt.afmt:
            changes.append(ComponentChange(
                component_type="template", name=name, status="modified"
            ))
    return changes


def compute_notetype_diff(
    old_nt: Optional[Notetype], new_nt: Optional[Notetype]
) -> Optional[NotetypeDiff]:
    if old_nt is None:
        assert new_nt is not None
        return NotetypeDiff(
            name=new_nt.name, change_type="added",
            component_changes=[ComponentChange(
                component_type="field", name="(new notetype)", status="added",
                new_value=f"{len(new_nt.fields)} fields, {len(new_nt.templates)} templates",
            )],
            fields_diff="(new notetype)",
        )

    if new_nt is None:
        assert old_nt is not None
        return NotetypeDiff(
            name=old_nt.name, change_type="deleted",
            component_changes=[ComponentChange(
                component_type="field", name="(deleted notetype)", status="removed",
                old_value=f"{len(old_nt.fields)} fields, {len(old_nt.templates)} templates",
            )],
            fields_diff="(deleted notetype)",
        )

    changes: List[ComponentChange] = []
    has_diff = False

    # Compare fields
    field_changes = _diff_field_lists(old_nt.fields, new_nt.fields)
    changes.extend(field_changes)
    if field_changes:
        has_diff = True

    # Compare templates
    tmpl_changes = _diff_template_lists(old_nt.templates, new_nt.templates)
    changes.extend(tmpl_changes)
    if tmpl_changes:
        has_diff = True

    # Compare CSS
    import difflib
    if old_nt.css != new_nt.css:
        has_diff = True
        css_diff_lines = list(difflib.unified_diff(
            old_nt.css.splitlines(keepends=True),
            new_nt.css.splitlines(keepends=True),
            fromfile=f"{new_nt.name}.css",
            tofile=f"{new_nt.name}.css",
            lineterm="",
        ))
        css_diff = "\n".join(css_diff_lines)
        changes.append(ComponentChange(
            component_type="css", name="style.css", status="modified",
            old_value=old_nt.css, new_value=new_nt.css,
        ))
    else:
        css_diff = ""

    if not has_diff:
        return None

    import json
    old_ser = json.dumps(_notetype_to_canonical(old_nt), indent=2, ensure_ascii=False, sort_keys=True)
    new_ser = json.dumps(_notetype_to_canonical(new_nt), indent=2, ensure_ascii=False, sort_keys=True)
    fields_diff = "\n".join(_unified_diff(old_ser, new_ser, f"{new_nt.name}.json"))

    return NotetypeDiff(
        name=new_nt.name,
        change_type="modified",
        component_changes=changes,
        fields_diff=fields_diff,
        css_diff=css_diff,
    )


def compute_export_diff(col, repo_path: Path, progress_callback: Optional[Callable] = None) -> DiffReport:
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


def compute_import_diff(col, repo_path: Path, progress_callback: Optional[Callable] = None) -> DiffReport:
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
