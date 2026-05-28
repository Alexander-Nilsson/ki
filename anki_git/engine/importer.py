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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anki_git.formats.notes_md import Note
    from anki_git.formats.notetype_yaml import Notetype
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
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    conflict_report: object = None


def preview_import(repo_path: Path, col=None) -> ImportResult:
    """Analyze what would change without applying anything (dry-run).

    If col is provided, performs real diffing via compute_import_diff.
    Otherwise falls back to simple file counting.
    """
    if col is not None:
        from anki_git.engine.diff import compute_import_diff_delta
        data = compute_import_diff_delta(col, repo_path)
        report = data.report
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
    from anki_git.formats.notes_md import parse_notes_file
    from anki_git.formats.notetype_yaml import read_all_notetypes

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


def pull_from_repo(col, repo_path: Path, conflict_callback=None,
                   sync_mode: str = "accept_all",
                   anki_checksums: dict[str, str] | None = None,
                   git_checksums: dict[str, str] | None = None,
                   git_notes_lookup: dict[int, "Note"] | None = None,
                   repo_notetypes: dict[str, "Notetype"] | None = None) -> ImportResult:
    """Import repo state into Anki with conflict detection and optional resolution.

    Steps:
    1. Compute checksums for current Anki notes, Git notes, and base (meta.json)
    2. Run conflict detection + auto-resolution
    3. If conflicts exist, invoke conflict_callback(report) for user resolution
    4. Apply only git-winning changes to Anki
    5. Delete from Anki notes that were deleted in repo (if resolution says so)
    6. Delete from repo notes that were deleted in Anki (if resolution says so)
    7. Persist tracking metadata (last_note_count, last_max_mod, last_commit_sha)
       to prevent unnecessary re-export on close
    8. Create verification commit recording the import

    conflict_callback receives a ConflictReport and must return a resolved ConflictReport.

    If anki_checksums / git_checksums / git_notes_lookup / repo_notetypes
    are provided, skips the corresponding filesystem scans.
    """
    from anki_git.engine.checksums import load_meta, save_meta
    from anki_git.engine.conflict import ConflictType, process_conflicts

    if anki_checksums is None:
        anki_checksums = import_helpers.compute_anki_checksums(col)
    if git_checksums is None and git_notes_lookup is None:
        git_checksums, git_notes_lookup = import_helpers.compute_git_checksums(repo_path)

    assert anki_checksums is not None
    assert git_checksums is not None and git_notes_lookup is not None

    meta = load_meta(repo_path)
    base_checksums = meta.get("note_checksums", {})

    report = process_conflicts(
        base_checksums, anki_checksums, git_checksums,
        sync_mode, col, repo_path, notes_lookup=git_notes_lookup,
    )

    if conflict_callback and report.has_conflicts:
        report = conflict_callback(report)

    resolved_nids: set[int] = set()
    delete_from_anki_nids: set[int] = set()
    delete_from_git_nids: set[int] = set()

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

    result = import_from_repo(col, repo_path, nid_filter=resolved_nids,
                              notes_lookup=git_notes_lookup,
                              repo_notetypes=repo_notetypes)
    result.conflict_report = report

    for nid in delete_from_anki_nids:
        if import_helpers.delete_note_from_anki(col, nid):
            result.notes_deleted_from_anki += 1

    for nid in delete_from_git_nids:
        if import_helpers.delete_note_from_repo(repo_path, nid):
            result.notes_deleted_from_git += 1

    assert col.db is not None
    meta["last_note_count"] = col.db.scalar(
        "SELECT COUNT(*) FROM notes WHERE id > 0"
    ) or 0
    meta["last_max_mod"] = col.db.scalar(
        "SELECT MAX(mod) FROM notes WHERE id > 0"
    ) or 0

    from anki_git.engine.git_ops import open_repo
    repo = open_repo(repo_path)
    meta["note_checksums"] = git_checksums

    total_imported = result.notes_updated + result.notes_created
    total_notetypes = result.notetypes_updated + result.notetypes_created
    if repo and (total_imported > 0 or total_notetypes > 0):
        parts = []
        if total_imported:
            parts.append(f"{total_imported} notes")
        if total_notetypes:
            parts.append(f"{total_notetypes} notetypes")
        msg = f"Import {', '.join(parts)} from repo"
        repo.git.commit("--allow-empty", "-m", msg)

    if repo:
        from contextlib import suppress
        with suppress(ValueError, Exception):
            meta["last_commit_sha"] = repo.head.commit.hexsha
    save_meta(repo_path, meta)

    return result


def import_from_repo(col, repo_path: Path,
                     nid_filter: set[int] | None = None,
                     notes_lookup: dict[int, "Note"] | None = None,
                     repo_notetypes: dict[str, "Notetype"] | None = None) -> ImportResult:
    """Apply repo state to an Anki collection.

    Must be called on Anki's main thread.
    If nid_filter is provided, only import notes whose nid is in the set.
    If notes_lookup / repo_notetypes are provided, skips filesystem scans.
    """
    result = ImportResult()

    try:
        col.db.execute("begin")
        import_helpers.import_notetypes(col, repo_path, result,
                                        repo_notetypes=repo_notetypes)
        import_helpers.import_notes(col, repo_path, result,
                                    nid_filter=nid_filter,
                                    notes_lookup=notes_lookup)
        col.db.execute("commit")
        _logger.info("Import complete: %d notes, %d notetypes",
                     result.notes_updated + result.notes_created,
                     result.notetypes_updated + result.notetypes_created)
    except Exception as e:
        col.db.execute("rollback")
        _logger.exception("Import failed")
        result.errors.append(str(e))

    return result
