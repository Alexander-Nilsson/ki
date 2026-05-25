"""Import engine: apply changes from Git repo back into Anki collection.

This module reads the Markdown notes and YAML notetypes from the repo
and writes them into the Anki collection. All collection writes happen on
the main thread via mw.taskman.run_on_main().

Matching strategy:
  - Notes: matched by nid. If nid exists in collection -> update.
           If nid absent -> create new note.
  - Notetypes: matched by name. If name exists -> update preserving ID.
               If name absent -> create new.
"""

import logging
from pathlib import Path
from typing import List, Optional, Set
from dataclasses import dataclass, field

from anki_git.engine import import_helpers

_logger = logging.getLogger("anki_git")


@dataclass
class ImportResult:
    notes_updated: int = 0
    notes_created: int = 0
    notetypes_updated: int = 0
    notetypes_created: int = 0
    notes_deleted_from_anki: int = 0
    notes_deleted_from_git: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    conflict_report: object = None


def preview_import(repo_path: Path, col=None) -> ImportResult:
    """Analyze what would change without applying anything (dry-run).

    If col is provided, performs real diffing via compute_import_diff.
    Otherwise falls back to simple file counting.
    """
    if col is not None:
        from anki_git.engine.diff import compute_import_diff
        report = compute_import_diff(col, repo_path)
        created = sum(1 for d in report.note_diffs if d.change_type == "added")
        modified = sum(1 for d in report.note_diffs if d.change_type == "modified")
        deleted = sum(1 for d in report.note_diffs if d.change_type == "deleted")
        nt_created = sum(1 for d in report.notetype_diffs if d.change_type == "added")
        nt_modified = sum(1 for d in report.notetype_diffs if d.change_type == "modified")
        nt_deleted = sum(1 for d in report.notetype_diffs if d.change_type == "deleted")
        return ImportResult(
            notes_created=created,
            notes_updated=modified,
            notetypes_created=nt_created,
            notetypes_updated=nt_modified,
            warnings=[] if not (deleted or nt_deleted) else [
                f"{deleted} notes would be deleted",
                f"{nt_deleted} notetypes would be deleted",
            ],
        )

    # Fallback: simple file counting without collection access
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


def pull_from_repo(col, repo_path: Path, conflict_callback=None) -> ImportResult:
    """Import repo state into Anki with conflict detection and optional resolution.

    Steps:
    1. Compute checksums for current Anki notes, Git notes, and base (meta.json)
    2. Run conflict detection
    3. If conflicts exist, invoke conflict_callback(report) for user resolution
    4. Apply only git-winning changes to Anki
    5. Delete from Anki notes that were deleted in repo (if resolution says so)
    6. Delete from repo notes that were deleted in Anki (if resolution says so)
    7. Save updated checksums to meta.json

    conflict_callback receives a ConflictReport and must return a resolved ConflictReport.
    """
    from anki_git.engine.conflict import detect_conflicts, enrich_conflicts_with_content, ConflictType
    from anki_git.engine.checksums import load_meta, save_meta

    anki_checksums = import_helpers.compute_anki_checksums(col)
    git_checksums, _ = import_helpers.compute_git_checksums(repo_path)
    meta = load_meta(repo_path)
    base_checksums = meta.get("note_checksums", {})

    report = detect_conflicts(base_checksums, anki_checksums, git_checksums)
    enrich_conflicts_with_content(report, col, repo_path)

    if conflict_callback and report.has_conflicts:
        report = conflict_callback(report)

    resolved_nids: Set[int] = set()
    delete_from_anki_nids: Set[int] = set()
    delete_from_git_nids: Set[int] = set()

    for c in report.conflicts:
        if not c.resolved:
            continue
        if c.resolution == "git":
            resolved_nids.add(c.nid)
        elif c.resolution == "anki":
            pass  # Keep Anki version, nothing to import
        if c.conflict_type == ConflictType.DELETE_FROM_ANKI:
            delete_from_anki_nids.add(c.nid)
        if c.conflict_type == ConflictType.DELETE_FROM_GIT:
            delete_from_git_nids.add(c.nid)

    result = import_from_repo(col, repo_path, nid_filter=resolved_nids)
    result.conflict_report = report

    for nid in delete_from_anki_nids:
        if import_helpers.delete_note_from_anki(col, nid):
            result.notes_deleted_from_anki += 1

    for nid in delete_from_git_nids:
        if import_helpers.delete_note_from_repo(repo_path, nid):
            result.notes_deleted_from_git += 1

    meta["note_checksums"] = git_checksums
    save_meta(repo_path, meta)

    return result


def import_from_repo(col, repo_path: Path,
                     nid_filter: Optional[Set[int]] = None) -> ImportResult:
    """Apply repo state to an Anki collection.

    Must be called on Anki's main thread.
    If nid_filter is provided, only import notes whose nid is in the set.
    """
    result = ImportResult()

    try:
        col.db.execute("begin")
        import_helpers.import_notetypes(col, repo_path, result)
        import_helpers.import_notes(col, repo_path, result,
                                    nid_filter=nid_filter)
        col.db.execute("commit")
        _logger.info("Import complete: %d notes, %d notetypes",
                     result.notes_updated + result.notes_created,
                     result.notetypes_updated + result.notetypes_created)
    except Exception as e:
        col.db.execute("rollback")
        _logger.exception("Import failed")
        result.errors.append(str(e))

    return result
