import logging
import time
from pathlib import Path
from collections.abc import Callable
from typing import Dict, List, Optional, Set

from anki.collection import Collection

from anki_git.engine.checksums import content_hash, load_meta, save_meta
from anki_git.engine.git_ops import (
    get_or_init_repo,
    stage_files,
    ensure_gitignore,
    create_snapshot_commit,
    push_to_remote,
    get_commit_count,
)
from anki_git.engine import export_helpers, import_helpers
from anki_git.formats.notetype_yaml import (
    Notetype,
    write_notetype,
    read_all_notetypes,
    notetype_paths,
)
from anki_git.formats.notes_md import Note
from anki_git.formats.media import handle_media, get_media_filenames_from_fields, MediaStrategy

_logger = logging.getLogger("anki_git")

NOTETYPES_DIR = "notetypes"
DECKS_DIR = "decks"
META_DIR = ".ki"


class ExportResult:
    def __init__(
        self,
        notes_changed: int = 0,
        notetypes_changed: int = 0,
        notes_deleted_from_repo: int = 0,
        changed_decks: Optional[Dict[str, int]] = None,
        changed_notetypes: Optional[List[str]] = None,
        error: str = "",
        duration_seconds: float = 0.0,
        commit_count: int = 0,
    ):
        self.notes_changed = notes_changed
        self.notetypes_changed = notetypes_changed
        self.notes_deleted_from_repo = notes_deleted_from_repo
        self.changed_decks = changed_decks or {}
        self.changed_notetypes = changed_notetypes or []
        self.error = error
        self.duration_seconds = duration_seconds
        self.commit_count = commit_count


def export_collection(
    col: Collection,
    repo_path: Path,
    remote_url: str = "",
    progress_callback: Optional[Callable[[str], None]] = None,
    media_strategy: str = "none",
) -> ExportResult:
    _start = time.perf_counter()
    result = ExportResult()

    if progress_callback:
        progress_callback("Initializing repository...")
    repo = get_or_init_repo(repo_path)
    ensure_gitignore(repo_path)

    if progress_callback:
        progress_callback("Loading metadata...")
    meta = load_meta(repo_path)

    notetypes_dir = repo_path / NOTETYPES_DIR

    if progress_callback:
        progress_callback("Exporting notetypes...")
    old_notetypes = read_all_notetypes(notetypes_dir)

    current_notetypes: Dict[str, Notetype] = {}
    for nt_dict in col.models.all():
        nt = Notetype.from_anki_dict(nt_dict)
        current_notetypes[nt.name] = nt

    changed_notetypes: List[str] = []
    changed_files: Set[str] = set()
    for name, nt in current_notetypes.items():
        old = old_notetypes.get(name)
        if nt != old:
            changed_notetypes.append(name)
            write_notetype(notetypes_dir, nt)
            for p in notetype_paths(notetypes_dir, name):
                changed_files.add(str(p.relative_to(repo_path)))

    meta_checksums = meta.get("note_checksums", {})

    if progress_callback:
        progress_callback("Reading notes...")
    db = col.db
    assert db is not None
    nids = db.list("SELECT id FROM notes WHERE id > 0")
    total = len(nids)
    notes_by_deck: Dict[str, List[Note]] = {}
    note_checksums: Dict[str, str] = {}
    notes_changed = 0
    media_filenames: set = set()

    for i, nid in enumerate(nids):
        if progress_callback and i % 20 == 0:
            progress_callback(f"Processing notes... {i}/{total}")
        exported = export_helpers.export_single_note(col, repo_path, nid)
        if exported is None:
            continue
        file_path, serialized, note = exported

        checksum = content_hash(serialized)
        note_checksums[str(nid)] = checksum

        old_checksum = meta_checksums.get(str(nid))
        if old_checksum != checksum:
            notes_changed += 1
            changed_files.add(str(file_path.relative_to(repo_path)))

        deck_name = note.deck
        if deck_name not in notes_by_deck:
            notes_by_deck[deck_name] = []
        notes_by_deck[deck_name].append(note)

        if media_strategy != "none":
            for field_value in note.fields.values():
                media_filenames.update(get_media_filenames_from_fields(field_value))

    # Clean up stale repo files for deleted Anki notes
    if progress_callback:
        progress_callback("Cleaning up stale files...")
    cleaned = import_helpers.cleanup_stale_repo_notes(
        col, repo_path, anki_nids=set(nids),
    )
    if cleaned > 0:
        result.notes_deleted_from_repo = cleaned

    if media_strategy != "none" and media_filenames:
        if progress_callback:
            progress_callback("Handling media files...")
        col_media_dir = (
            Path(col.media.dir()) if hasattr(col, "media") and col.media is not None
            else Path(col.path).parent / "collection.media"
        )
        repo_media_dir = repo_path / "media"
        strategy = MediaStrategy(media_strategy)
        handle_media(col_media_dir, repo_media_dir, strategy, media_filenames)

    result.notes_changed = notes_changed
    result.notetypes_changed = len(changed_notetypes)
    result.changed_notetypes = changed_notetypes
    result.changed_decks = {d: len(ns) for d, ns in notes_by_deck.items()}

    if notes_changed > 0 or result.notetypes_changed > 0 or cleaned > 0:
        if progress_callback:
            progress_callback("Committing changes...")
        meta["last_export_time"] = int(time.time())
        meta["note_checksums"] = note_checksums
        meta["collection_path"] = str(col.path)
        save_meta(repo_path, meta)

        changed_files.add(
            str((repo_path / META_DIR / "meta.json").relative_to(repo_path))
        )

        stage_files(repo, list(changed_files))
        create_snapshot_commit(repo, list(changed_files))

        if remote_url:
            if progress_callback:
                progress_callback("Pushing to remote...")
            push_to_remote(repo, remote_url)

    # Store tracking data for quick_has_changes()
    meta["last_note_count"] = db.scalar("SELECT COUNT(*) FROM notes WHERE id > 0") or 0
    meta["last_max_mod"] = db.scalar("SELECT MAX(mod) FROM notes WHERE id > 0") or 0
    meta["last_commit_sha"] = str(repo.head.commit)
    save_meta(repo_path, meta)

    result.commit_count = get_commit_count(repo)
    result.duration_seconds = time.perf_counter() - _start
    _logger.info(
        "Snapshot took %.2fs: %d notes changed, %d notetypes changed",
        result.duration_seconds,
        notes_changed,
        result.notetypes_changed,
    )
    if progress_callback:
        progress_callback(
            f"Snapshot complete ({result.duration_seconds:.1f}s)"
        )

    return result
