"""Import engine: apply changes from Git repo back into Anki collection.

This module reads the Markdown notes and YAML notetypes from the repo
and writes them into the Anki collection. All collection writes happen on
the main thread via mw.taskman.run_on_main().

Matching strategy:
  - Notes: matched by nid. If nid exists in collection → update.
           If nid absent → create new note.
  - Notetypes: matched by name. If name exists → update preserving ID.
               If name absent → create new.
"""

from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field


@dataclass
class ImportResult:
    notes_updated: int = 0
    notes_created: int = 0
    notetypes_updated: int = 0
    notetypes_created: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def preview_import(repo_path: Path) -> ImportResult:
    """Analyze what would change without applying anything (dry-run)."""
    result = ImportResult()
    from anki_git.formats.notetype_yaml import read_all_notetypes
    from anki_git.formats.notes_md import parse_notes_file

    notetypes_dir = repo_path / "notetypes"
    decks_dir = repo_path / "decks"

    repo_notetypes = read_all_notetypes(notetypes_dir)
    result.notetypes_created = len(repo_notetypes)

    for nt_name, nt in repo_notetypes.items():
        note_count = 0
        for notes_file in decks_dir.rglob("notes.md"):
            notes = parse_notes_file(notes_file)
            for note in notes:
                if note.notetype == nt_name:
                    note_count += 1

    return result


def import_from_repo(col, repo_path: Path) -> ImportResult:
    """Apply repo state to an Anki collection.

    Must be called on Anki's main thread.
    """
    result = ImportResult()

    try:
        col.db.begin()
        _import_notetypes(col, repo_path, result)
        _import_notes(col, repo_path, result)
        col.db.commit()
    except Exception as e:
        col.db.rollback()
        result.errors.append(str(e))

    return result


def _import_notetypes(col, repo_path: Path, result: ImportResult) -> None:
    from anki_git.formats.notetype_yaml import read_all_notetypes, Notetype

    notetypes_dir = repo_path / "notetypes"
    repo_notetypes = read_all_notetypes(notetypes_dir)

    for name, nt in repo_notetypes.items():
        existing = col.models.by_name(name)
        if existing:
            existing["flds"] = [
                {"name": f.name, "ord": f.ord, "font": f.font, "size": f.size, "sticky": f.sticky}
                for f in nt.fields
            ]
            existing["tmpls"] = [
                {"name": t.name, "ord": t.ord, "qfmt": t.qfmt, "afmt": t.afmt}
                for t in nt.templates
            ]
            existing["css"] = nt.css
            col.models.save(existing)
            result.notetypes_updated += 1
        else:
            new_nt = col.models.new(name)
            for f in nt.fields:
                field = col.models.new_field(f.name)
                col.models.add_field(new_nt, field)
            for t in nt.templates:
                tmpl = col.models.new_template(t.name)
                tmpl["qfmt"] = t.qfmt
                tmpl["afmt"] = t.afmt
                col.models.add_template(new_nt, tmpl)
            new_nt["css"] = nt.css
            col.models.add_dict(new_nt)
            result.notetypes_created += 1


def _import_notes(col, repo_path: Path, result: ImportResult) -> None:
    from anki_git.formats.notes_md import parse_notes_file
    from anki.utils import int_time

    decks_dir = repo_path / "decks"
    for notes_file in sorted(decks_dir.rglob("notes.md")):
        notes = parse_notes_file(notes_file)
        for note_data in notes:
            try:
                existing = col.get_note(note_data.nid)
                for key, value in note_data.fields.items():
                    if key in existing:
                        existing[key] = value
                existing.tags = note_data.tags
                existing.flush()
                result.notes_updated += 1
            except Exception:
                model_id = col.models.id_for_name(note_data.notetype)
                if model_id is None:
                    result.warnings.append(f"Notetype '{note_data.notetype}' not found for nid {note_data.nid}")
                    continue
                new_note = col.new_note(model_id)
                for key, value in note_data.fields.items():
                    if key in new_note:
                        new_note[key] = value
                new_note.tags = note_data.tags
                try:
                    deck_id = col.decks.id(note_data.deck)
                    col.add_note(new_note, deck_id)
                    result.notes_created += 1
                except Exception as e:
                    result.errors.append(f"Failed to create note: {e}")
