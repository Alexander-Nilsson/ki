"""Two-way sync engine: merge changes between Anki collection and Git repo.

Flow:
  1. Compute checksums for Anki notes, Git notes, and base (meta.json)
  2. Run three-way conflict detection
  3. Auto-resolve based on sync_mode or prompt user for true conflicts
  4. Apply resolved changes in both directions
  5. Update meta.json and commit
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Set

from anki.collection import Collection

from anki_git.config import SyncMode
from anki_git.engine.checksums import load_meta, save_meta
from anki_git.engine.conflict import (
    detect_conflicts,
    resolve_conflicts,
    merge_notetypes,
    ConflictType,
)
from anki_git.engine.git_ops import (
    get_or_init_repo,
    stage_files,
    ensure_gitignore,
    create_snapshot_commit,
    push_to_remote,
    get_commit_count,
)
from anki_git.engine import import_helpers
from anki_git.formats.notetype_yaml import (
    Notetype,
    read_all_notetypes,
    write_notetype,
    notetype_paths,
)
from anki_git.formats.notes_md import Note, write_note_file

_logger = logging.getLogger("anki_git")

NOTETYPES_DIR = "notetypes"
DECKS_DIR = "decks"
META_DIR = ".ki"


@dataclass
class SyncResult:
    notes_exported: int = 0
    notes_imported: int = 0
    notetypes_exported: int = 0
    notetypes_imported: int = 0
    notes_deleted_from_git: int = 0
    notes_deleted_from_anki: int = 0
    conflicts_resolved: int = 0
    conflicts_unresolved: int = 0
    error: str = ""
    duration_seconds: float = 0.0
    commit_count: int = 0


def _export_single_note(col, repo_path: Path, nid: int) -> bool:
    """Export a single note from Anki into repo files."""
    try:
        note_obj = col.get_note(nid)
    except Exception:
        return False

    nt_name = note_obj.note_type()["name"]
    try:
        cards = note_obj.cards()
        if not cards:
            return False
        deck_name = col.decks.name(cards[0].did)
    except Exception:
        return False

    fields = dict(note_obj.items())
    note = Note(
        nid=nid, notetype=nt_name, tags=list(note_obj.tags),
        deck=deck_name, fields=fields,
    )
    deck_path_parts = deck_name.split("::")
    note_dir = repo_path / DECKS_DIR / Path(*deck_path_parts)
    serialized = note.serialize()
    write_note_file(note_dir, note, content=serialized)
    return True


def sync_collection(
    col: Collection,
    repo_path: Path,
    sync_mode: str = SyncMode.ALWAYS_ASK,
    conflict_callback: Callable = None,
    remote_url: str = "",
    progress_callback: Callable = None,
    media_strategy: str = "none",
) -> SyncResult:
    _start = time.perf_counter()
    result = SyncResult()

    if progress_callback:
        progress_callback("Initializing repository...")
    repo = get_or_init_repo(repo_path)
    ensure_gitignore(repo_path)

    if progress_callback:
        progress_callback("Loading metadata...")
    meta = load_meta(repo_path)
    base_checksums = meta.get("note_checksums", {})

    if progress_callback:
        progress_callback("Computing Anki checksums...")
    anki_checksums = import_helpers.compute_anki_checksums(col)

    if progress_callback:
        progress_callback("Computing repo checksums...")
    git_checksums = import_helpers.compute_git_checksums(repo_path)

    if progress_callback:
        progress_callback("Detecting conflicts...")
    report = detect_conflicts(base_checksums, anki_checksums, git_checksums)

    resolve_conflicts(report, sync_mode)

    if report.has_conflicts and conflict_callback and sync_mode == SyncMode.ALWAYS_ASK:
        unresolved = [c for c in report.conflicts if not c.resolved]
        if unresolved:
            if progress_callback:
                progress_callback("Waiting for conflict resolution...")
            report = conflict_callback(report)

    changed_files: Set[str] = set()
    notes_to_export: set[int] = set()
    notes_to_import_nids: set[int] = set()
    delete_from_anki_nids: set[int] = set()
    delete_from_git_nids: set[int] = set()

    if progress_callback:
        progress_callback("Processing changes...")

    notetypes_dir = repo_path / NOTETYPES_DIR

    for c in report.conflicts:
        if not c.resolved:
            result.conflicts_unresolved += 1
            continue
        result.conflicts_resolved += 1

        if c.resolution == "anki":
            notes_to_export.add(c.nid)
        elif c.resolution == "git":
            notes_to_import_nids.add(c.nid)

        if c.conflict_type == ConflictType.DELETE_FROM_ANKI:
            delete_from_anki_nids.add(c.nid)
        if c.conflict_type == ConflictType.DELETE_FROM_GIT:
            delete_from_git_nids.add(c.nid)

    # Build notes lookup once for O(n) import
    notes_lookup = import_helpers.load_all_repo_notes(repo_path)

    # Apply changes: import (repo -> anki)
    if progress_callback:
        progress_callback("Importing changes from repo...")

    col.db.execute("begin")
    try:
        for nid in notes_to_import_nids:
            if import_helpers.import_single_note(
                col, repo_path, nid, notes_lookup=notes_lookup,
            ):
                result.notes_imported += 1

        for nid in delete_from_anki_nids:
            if import_helpers.delete_note_from_anki(col, nid):
                result.notes_deleted_from_anki += 1

        col.db.execute("commit")
    except Exception as e:
        col.db.execute("rollback")
        _logger.exception("Failed to import notes from repo")
        result.error = str(e)
        return result

    # Apply changes: export (anki -> repo)
    if progress_callback:
        progress_callback("Exporting changes to repo...")

    for nid in notes_to_export:
        if _export_single_note(col, repo_path, nid):
            result.notes_exported += 1
            decks_dir = repo_path / DECKS_DIR
            for f in decks_dir.rglob(f"{nid}.md"):
                changed_files.add(str(f.relative_to(repo_path)))

    for nid in delete_from_git_nids:
        if import_helpers.delete_note_from_repo(repo_path, nid):
            result.notes_deleted_from_git += 1
            md_path = repo_path / DECKS_DIR / f"{nid}.md"
            if md_path.exists():
                changed_files.add(str(md_path.relative_to(repo_path)))

    new_anki_checksums = import_helpers.compute_anki_checksums(col)

    # Detect notetype changes between Anki and repo
    anki_notetypes: Dict[str, Notetype] = {}
    for nt_dict in col.models.all():
        nt = Notetype.from_anki_dict(nt_dict)
        anki_notetypes[nt.name] = nt

    if progress_callback:
        progress_callback("Syncing notetypes...")

    repo_notetypes = read_all_notetypes(notetypes_dir)
    all_nt_names = set(anki_notetypes) | set(repo_notetypes)

    for name in sorted(all_nt_names):
        anki_nt = anki_notetypes.get(name)
        git_nt = repo_notetypes.get(name)

        if anki_nt and git_nt:
            if anki_nt == git_nt:
                continue
            merged, nt_conflicts = merge_notetypes(anki_nt, git_nt, sync_mode)
            write_notetype(notetypes_dir, merged)
            for p in notetype_paths(notetypes_dir, name):
                changed_files.add(str(p.relative_to(repo_path)))
            import_helpers.import_notetype(col, repo_path, name)
            for c in nt_conflicts:
                if c.resolved:
                    result.conflicts_resolved += 1
                else:
                    result.conflicts_unresolved += 1
            result.notetypes_exported += 1
            result.notetypes_imported += 1
        elif anki_nt:
            write_notetype(notetypes_dir, anki_nt)
            for p in notetype_paths(notetypes_dir, name):
                changed_files.add(str(p.relative_to(repo_path)))
            result.notetypes_exported += 1
        elif git_nt:
            import_helpers.import_notetype(col, repo_path, name)
            result.notetypes_imported += 1

    notes_changed = result.notes_exported + result.notes_imported
    notetypes_changed = result.notetypes_exported + result.notetypes_imported

    if notes_changed > 0 or notetypes_changed > 0:
        if progress_callback:
            progress_callback("Committing changes...")
        meta["last_export_time"] = int(time.time())
        meta["note_checksums"] = new_anki_checksums
        meta["collection_path"] = str(col.path)
        save_meta(repo_path, meta)

        changed_files.add(
            str((repo_path / META_DIR / "meta.json").relative_to(repo_path))
        )

        stage_files(repo, list(changed_files))
        create_snapshot_commit(
            repo,
            notes_changed=notes_changed,
            notetypes_changed=notetypes_changed,
            changed_decks={},
            changed_notetypes=[],
            collection_path=str(col.path),
        )

        if remote_url:
            if progress_callback:
                progress_callback("Pushing to remote...")
            push_to_remote(repo, remote_url)

    result.commit_count = get_commit_count(repo)
    result.duration_seconds = time.perf_counter() - _start
    _logger.info(
        "Sync took %.2fs: %d notes exported, %d notes imported, "
        "%d notetypes exported, %d notetypes imported",
        result.duration_seconds,
        result.notes_exported,
        result.notes_imported,
        result.notetypes_exported,
        result.notetypes_imported,
    )
    if progress_callback:
        progress_callback(
            f"Sync complete ({result.duration_seconds:.1f}s)"
        )

    return result
