"""Shared import helpers used by both importer.py and sync.py.

Extracted to eliminate code duplication between one-way import and two-way
sync. All functions operate on Anki collection objects (not aqt) so they
remain testable without the Anki Qt runtime.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Dict, Optional, Set, TYPE_CHECKING

from anki.collection import Collection

if TYPE_CHECKING:
    from anki_git.formats.notes_md import Note

_logger = logging.getLogger("anki_git")

NOTETYPES_DIR = "notetypes"
DECKS_DIR = "decks"


def compute_anki_checksums(col: Collection) -> Dict[str, str]:
    """Compute checksums for Anki notes using the same Note.serialize()
    format as git checksums, so conflict detection works correctly.
    """
    from anki_git.engine.checksums import content_hash
    from anki_git.formats.notes_md import Note

    checksums = {}
    db = col.db
    assert db is not None
    for nid in db.list("SELECT id FROM notes WHERE id > 0"):
        try:
            note_obj = col.get_note(nid)
        except Exception:
            continue
        nt_dict = note_obj.note_type()
        if nt_dict is None:
            continue
        nt_name = nt_dict["name"]
        try:
            cards = note_obj.cards()
            if not cards:
                continue
            deck_name = col.decks.name(cards[0].did)
        except Exception:
            continue
        note = Note(
            nid=nid, notetype=nt_name, tags=list(note_obj.tags),
            deck=deck_name, fields=dict(note_obj.items()),
        )
        checksums[str(nid)] = content_hash(note.serialize())
    return checksums


def compute_git_checksums(repo_path: Path) -> Dict[str, str]:
    from anki_git.engine.checksums import content_hash
    from anki_git.formats.notes_md import parse_notes_file

    checksums = {}
    decks_dir = repo_path / DECKS_DIR
    for notes_file in sorted(decks_dir.rglob("*.md")):
        notes = parse_notes_file(notes_file)
        for note_data in notes:
            checksums[str(note_data.nid)] = content_hash(note_data.serialize())
    return checksums


def load_all_repo_notes(repo_path: Path) -> Dict[int, "Note"]:
    """Build {nid: Note} lookup dict from all repo files.

    This is the O(n) alternative to scanning all files per-note (O(n*m)).
    """
    from anki_git.formats.notes_md import parse_notes_file

    notes: Dict[int, "Note"] = {}

    decks_dir = repo_path / DECKS_DIR
    for notes_file in sorted(decks_dir.rglob("*.md")):
        for note_data in parse_notes_file(notes_file):
            notes[note_data.nid] = note_data
    return notes


def import_single_note(col: Collection, repo_path: Path, nid: int,
                       notes_lookup: Optional[Dict[int, "Note"]] = None) -> bool:
    """Import a single note from repo into Anki. Returns True on success.

    Optionally accepts a pre-built notes_lookup dict; if not provided,
    builds one (less efficient for batch imports).
    """
    if notes_lookup is None:
        notes_lookup = load_all_repo_notes(repo_path)

    note_data = notes_lookup.get(nid)
    if note_data is None:
        _logger.warning("Note %d not found in repo files", nid)
        return False

    try:
        existing = col.get_note(nid)
    except Exception:
        existing = None

    if existing is not None:
        for key, value in note_data.fields.items():
            if key in existing:
                existing[key] = value
        existing.tags = note_data.tags
        col.update_note(existing)
        return True
    else:
        model_id = col.models.id_for_name(note_data.notetype)
        if model_id is None:
            _logger.warning("Notetype '%s' not found for nid %d",
                            note_data.notetype, nid)
            return False
        new_note = col.new_note(model_id)
        for key, value in note_data.fields.items():
            if key in new_note:
                new_note[key] = value
        new_note.tags = note_data.tags
        try:
            deck_id = col.decks.id(note_data.deck)
            col.add_note(new_note, deck_id)
            return True
        except Exception as e:
            _logger.warning("Failed to create note %d: %s", nid, e)
            return False


def delete_note_from_anki(col: Collection, nid: int) -> bool:
    """Remove a note from Anki by nid. Returns True on success."""
    try:
        col.get_note(nid)
        col.remove_notes([nid])
        return True
    except Exception:
        _logger.warning("Failed to delete note %d from Anki", nid)
        return False


def delete_note_from_repo(repo_path: Path, nid: int) -> bool:
    """Remove a note's file from the repo. Returns True if deleted."""
    decks_dir = repo_path / DECKS_DIR
    for f in decks_dir.rglob(f"{nid}.md"):
        try:
            f.unlink()
            return True
        except Exception as e:
            _logger.warning("Failed to delete repo file %s: %s", f, e)
            return False
    return False


def import_notetype(col: Collection, repo_path: Path, nt_name: str) -> bool:
    """Import a single notetype from repo into Anki."""
    from anki_git.formats.notetype_yaml import read_all_notetypes

    notetypes_dir = repo_path / NOTETYPES_DIR
    repo_nt = read_all_notetypes(notetypes_dir)
    nt = repo_nt.get(nt_name)
    if nt is None:
        return False

    existing = col.models.by_name(nt_name)
    if existing:
        existing["flds"] = [
            {"name": f.name, "ord": f.ord, "font": f.font,
             "size": f.size, "sticky": f.sticky, "rtl": f.rtl}
            for f in nt.fields
        ]
        existing["tmpls"] = [
            {"name": t.name, "ord": t.ord, "qfmt": t.qfmt,
             "afmt": t.afmt}
            for t in nt.templates
        ]
        existing["css"] = nt.css
        col.models.save(existing)
    else:
        new_nt = col.models.new(nt_name)
        for f in nt.fields:
            field = col.models.new_field(f.name)
            field["rtl"] = f.rtl
            col.models.add_field(new_nt, field)
        for t in nt.templates:
            tmpl = col.models.new_template(t.name)
            tmpl["qfmt"] = t.qfmt
            tmpl["afmt"] = t.afmt
            col.models.add_template(new_nt, tmpl)
        new_nt["css"] = nt.css
        col.models.add_dict(new_nt)
    return True


def import_notetypes(col: Collection, repo_path: Path, result) -> None:
    """Import all notetypes from repo into Anki, updating result in-place."""
    from anki_git.formats.notetype_yaml import read_all_notetypes

    notetypes_dir = repo_path / NOTETYPES_DIR
    repo_notetypes = read_all_notetypes(notetypes_dir)

    for name, nt in repo_notetypes.items():
        existing = col.models.by_name(name)
        if existing:
            existing["flds"] = [
                {"name": f.name, "ord": f.ord, "font": f.font,
                 "size": f.size, "sticky": f.sticky, "rtl": f.rtl, "id": f.id}
                for f in nt.fields
            ]
            existing["tmpls"] = [
                {"name": t.name, "ord": t.ord, "qfmt": t.qfmt,
                 "afmt": t.afmt, "id": t.id}
                for t in nt.templates
            ]
            existing["css"] = nt.css
            col.models.save(existing)
            result.notetypes_updated += 1
        else:
            new_nt = col.models.new(name)
            for f in nt.fields:
                field = col.models.new_field(f.name)
                field["rtl"] = f.rtl
                col.models.add_field(new_nt, field)
            for t in nt.templates:
                tmpl = col.models.new_template(t.name)
                tmpl["qfmt"] = t.qfmt
                tmpl["afmt"] = t.afmt
                col.models.add_template(new_nt, tmpl)
            new_nt["css"] = nt.css
            col.models.add_dict(new_nt)
            result.notetypes_created += 1


def import_notes(col: Collection, repo_path: Path, result,
                 nid_filter: Optional[Set[int]] = None) -> None:
    """Import notes from repo into Anki.

    If nid_filter is provided, only import notes whose nid is in the set.
    Updates result in-place with notes_updated/notes_created/errors/warnings.
    """
    from anki_git.formats.notes_md import parse_notes_file

    decks_dir = repo_path / DECKS_DIR
    for notes_file in sorted(decks_dir.rglob("*.md")):
        notes = parse_notes_file(notes_file)
        for note_data in notes:
            if nid_filter is not None and note_data.nid not in nid_filter:
                continue

            try:
                existing = col.get_note(note_data.nid)
            except Exception:
                existing = None

            if existing is not None:
                for key, value in note_data.fields.items():
                    if key in existing:
                        existing[key] = value
                existing.tags = note_data.tags
                col.update_note(existing)
                result.notes_updated += 1
            else:
                model_id = col.models.id_for_name(note_data.notetype)
                if model_id is None:
                    _logger.warning(
                        "Notetype '%s' not found for nid %d",
                        note_data.notetype, note_data.nid,
                    )
                    result.warnings.append(
                        f"Notetype '{note_data.notetype}' not found "
                        f"for nid {note_data.nid}"
                    )
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
                    result.errors.append(
                        f"Failed to create note: {e}"
                    )


def cleanup_stale_repo_notes(col: Collection, repo_path: Path) -> int:
    """Remove repo note files for notes that no longer exist in Anki.

    Returns the number of files cleaned up.
    """
    db = col.db
    assert db is not None
    anki_nids = set(db.list("SELECT id FROM notes WHERE id > 0"))
    decks_dir = repo_path / DECKS_DIR
    cleaned = 0
    for notes_file in sorted(decks_dir.rglob("*.md")):
        from anki_git.formats.notes_md import parse_notes_file
        for note_data in parse_notes_file(notes_file):
            if note_data.nid not in anki_nids:
                try:
                    notes_file.unlink()
                    cleaned += 1
                except Exception as e:
                    _logger.warning(
                        "Failed to delete stale note file %s: %s",
                        notes_file, e,
                    )
    return cleaned
