import datetime
import logging
import time
from pathlib import Path
from typing import Dict, List, Set

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
from anki_git.formats.notetype_yaml import (
    Notetype,
    write_notetype,
    read_all_notetypes,
    notetype_paths,
)
from anki_git.formats.notes_md import Note, write_note_file
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
        changed_decks: Dict[str, int] = None,
        changed_notetypes: List[str] = None,
        error: str = "",
        duration_seconds: float = 0.0,
        commit_count: int = 0,
    ):
        self.notes_changed = notes_changed
        self.notetypes_changed = notetypes_changed
        self.changed_decks = changed_decks or {}
        self.changed_notetypes = changed_notetypes or []
        self.error = error
        self.duration_seconds = duration_seconds
        self.commit_count = commit_count


def export_collection(
    col: Collection,
    repo_path: Path,
    remote_url: str = "",
    progress_callback: callable = None,
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
    decks_dir = repo_path / DECKS_DIR

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
        try:
            old_yaml = "\n".join(old.to_yaml_lines()) if old else ""
        except Exception:
            old_yaml = ""
        new_yaml = "\n".join(nt.to_yaml_lines())
        if old_yaml != new_yaml:
            changed_notetypes.append(name)
            write_notetype(notetypes_dir, nt)
            yaml_path, css_path = notetype_paths(notetypes_dir, name)
            changed_files.add(str(yaml_path.relative_to(repo_path)))
            if nt.css or css_path.exists():
                changed_files.add(str(css_path.relative_to(repo_path)))

    meta_checksums = meta.get("note_checksums", {})

    if progress_callback:
        progress_callback("Reading notes...")
    nids = col.db.list("SELECT id FROM notes WHERE id > 0")
    total = len(nids)
    notes_by_deck: Dict[str, List[Note]] = {}
    note_checksums: Dict[str, str] = {}
    notes_changed = 0
    media_filenames: set = set()
    _nt_name_cache: Dict[int, str] = {}

    for i, nid in enumerate(nids):
        if progress_callback and i % 20 == 0:
            progress_callback(f"Processing notes... {i}/{total}")
        try:
            note_obj = col.get_note(nid)
        except Exception as e:
            _logger.warning("Failed to get note %d: %s", nid, e)
            continue
        mid = note_obj.mid
        if mid not in _nt_name_cache:
            _nt_name_cache[mid] = note_obj.note_type()["name"]
        nt_name = _nt_name_cache[mid]
        try:
            cards = note_obj.cards()
            if not cards:
                _logger.debug("Note %d has no cards, skipping", nid)
                continue
            deck_name = col.decks.name(cards[0].did)
        except Exception as e:
            _logger.warning("Failed to get deck for note %d: %s", nid, e)
            continue

        fields = dict(note_obj.items())
        tags = list(note_obj.tags)

        note = Note(
            nid=nid,
            notetype=nt_name,
            tags=tags,
            deck=deck_name,
            fields=fields,
        )

        serialized = note.serialize()
        checksum = content_hash(serialized)
        note_checksums[str(nid)] = checksum

        old_checksum = meta_checksums.get(str(nid))
        if old_checksum != checksum:
            notes_changed += 1
            deck_path_parts = deck_name.split("::")
            note_dir = decks_dir.joinpath(*deck_path_parts)
            note_path = write_note_file(note_dir, note, content=serialized)
            changed_files.add(str(note_path.relative_to(repo_path)))

        if deck_name not in notes_by_deck:
            notes_by_deck[deck_name] = []
        notes_by_deck[deck_name].append(note)

        if media_strategy != "none":
            for field_value in fields.values():
                media_filenames.update(get_media_filenames_from_fields(field_value))

    if media_strategy != "none" and media_filenames:
        if progress_callback:
            progress_callback("Handling media files...")
        col_media_dir = Path(col.media.dir()) if hasattr(col, "media") else col.path.parent / "collection.media"
        repo_media_dir = repo_path / "media"
        strategy = MediaStrategy(media_strategy)
        handle_media(col_media_dir, repo_media_dir, strategy, media_filenames)

    result.notes_changed = notes_changed
    result.notetypes_changed = len(changed_notetypes)
    result.changed_notetypes = changed_notetypes
    result.changed_decks = {d: len(ns) for d, ns in notes_by_deck.items()}

    if notes_changed > 0 or result.notetypes_changed > 0:
        if progress_callback:
            progress_callback("Committing changes...")
        meta["last_export_time"] = int(datetime.datetime.utcnow().timestamp())
        meta["note_checksums"] = note_checksums
        meta["collection_path"] = str(col.path)
        save_meta(repo_path, meta)

        changed_files.add(str((repo_path / META_DIR / "meta.json").relative_to(repo_path)))

        stage_files(repo, list(changed_files))
        create_snapshot_commit(
            repo,
            notes_changed=notes_changed,
            notetypes_changed=result.notetypes_changed,
            changed_decks=result.changed_decks,
            changed_notetypes=changed_notetypes,
            collection_path=str(col.path),
        )

        if remote_url:
            if progress_callback:
                progress_callback("Pushing to remote...")
            push_to_remote(repo, remote_url)

    result.commit_count = get_commit_count(repo)
    result.duration_seconds = time.perf_counter() - _start
    _logger.info(
        "Snapshot took %.2fs: %d notes changed, %d notetypes changed",
        result.duration_seconds,
        notes_changed,
        result.notetypes_changed,
    )
    if progress_callback:
        progress_callback(f"Snapshot complete ({result.duration_seconds:.1f}s)")

    return result
