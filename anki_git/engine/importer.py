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

import logging
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, field

_logger = logging.getLogger("anki_git")


@dataclass
class ImportResult:
    notes_updated: int = 0
    notes_created: int = 0
    notetypes_updated: int = 0
    notetypes_created: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    conflict_report: object = None


def preview_import(repo_path: Path) -> ImportResult:
    """Analyze what would change without applying anything (dry-run)."""
    from anki_git.formats.notetype_yaml import read_all_notetypes
    from anki_git.formats.notes_md import parse_notes_file

    notetypes_dir = repo_path / "notetypes"
    decks_dir = repo_path / "decks"

    repo_notetypes = read_all_notetypes(notetypes_dir)
    note_count = 0
    for notes_file in sorted(decks_dir.rglob("*.md")):
        notes = parse_notes_file(notes_file)
        note_count += len(notes)

    return ImportResult(
        notetypes_created=len(repo_notetypes),
        notes_created=note_count,
    )


def _compute_anki_checksums(col) -> Dict[str, str]:
    from anki_git.engine.checksums import content_hash

    checksums = {}
    for nid in col.db.list("SELECT id FROM notes WHERE id > 0"):
        try:
            note_obj = col.get_note(nid)
        except Exception:
            continue
        serialized = "\n".join(f"{k}: {v}" for k, v in sorted(note_obj.items()))
        checksums[str(nid)] = content_hash(serialized)
    return checksums


def _compute_git_checksums(repo_path: Path) -> Dict[str, str]:
    from anki_git.engine.checksums import content_hash
    from anki_git.formats.notes_md import parse_notes_file

    checksums = {}
    decks_dir = repo_path / "decks"
    for notes_file in sorted(decks_dir.rglob("*.md")):
        notes = parse_notes_file(notes_file)
        for note_data in notes:
            checksums[str(note_data.nid)] = content_hash(note_data.serialize())
    return checksums


def pull_from_repo(col, repo_path: Path, conflict_callback=None) -> ImportResult:
    """Import repo state into Anki with conflict detection and optional resolution.

    Steps:
    1. Compute checksums for current Anki notes, Git notes, and base (meta.json)
    2. Run conflict detection
    3. If conflicts exist, invoke conflict_callback(report) for user resolution
    4. Apply import
    5. Save updated checksums to meta.json

    conflict_callback receives a ConflictReport and must return a resolved ConflictReport.
    """
    from anki_git.engine.conflict import detect_conflicts
    from anki_git.engine.checksums import load_meta, save_meta

    anki_checksums = _compute_anki_checksums(col)
    git_checksums = _compute_git_checksums(repo_path)
    meta = load_meta(repo_path)
    base_checksums = meta.get("note_checksums", {})

    report = detect_conflicts(base_checksums, anki_checksums, git_checksums)

    if conflict_callback and report.has_conflicts:
        report = conflict_callback(report)

    resolved_nids = set()
    for c in report.conflicts:
        if c.resolved and c.resolution in ("anki", "git"):
            resolved_nids.add(str(c.nid))

    result = import_from_repo(col, repo_path)
    result.conflict_report = report

    meta["note_checksums"] = git_checksums
    save_meta(repo_path, meta)

    return result


def import_from_repo(col, repo_path: Path) -> ImportResult:
    """Apply repo state to an Anki collection.

    Must be called on Anki's main thread.
    """
    result = ImportResult()

    try:
        col.db.execute("begin")
        _import_notetypes(col, repo_path, result)
        _import_notes(col, repo_path, result)
        col.db.execute("commit")
        _logger.info("Import complete: %d notes, %d notetypes",
                    result.notes_updated + result.notes_created,
                    result.notetypes_updated + result.notetypes_created)
    except Exception as e:
        col.db.execute("rollback")
        _logger.exception("Import failed")
        result.errors.append(str(e))

    return result


def _import_notetypes(col, repo_path: Path, result: ImportResult) -> None:
    from anki_git.formats.notetype_yaml import read_all_notetypes

    notetypes_dir = repo_path / "notetypes"
    repo_notetypes = read_all_notetypes(notetypes_dir)

    for name, nt in repo_notetypes.items():
        existing = col.models.by_name(name)
        if existing:
            existing["flds"] = [
                {
                    "name": f.name,
                    "ord": f.ord,
                    "font": f.font,
                    "size": f.size,
                    "sticky": f.sticky,
                    "rtl": f.rtl,
                    "id": f.id,
                }
                for f in nt.fields
            ]
            existing["tmpls"] = [
                {"name": t.name, "ord": t.ord, "qfmt": t.qfmt, "afmt": t.afmt, "id": t.id}
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


def _import_notes(col, repo_path: Path, result: ImportResult) -> None:
    from anki_git.formats.notes_md import parse_notes_file

    decks_dir = repo_path / "decks"
    for notes_file in sorted(decks_dir.rglob("*.md")):
        notes = parse_notes_file(notes_file)
        for note_data in notes:
            try:
                existing = col.get_note(note_data.nid)
            except Exception:
                existing = None

            if existing is not None:
                for key, value in note_data.fields.items():
                    if key in existing:
                        existing[key] = value
                existing.tags = note_data.tags
                existing.flush()
                result.notes_updated += 1
            else:
                model_id = col.models.id_for_name(note_data.notetype)
                if model_id is None:
                    _logger.warning("Notetype '%s' not found for nid %d", note_data.notetype, note_data.nid)
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
