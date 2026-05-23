import datetime
from pathlib import Path
from typing import Dict, List

from anki.collection import Collection

from anki_git.engine.checksums import load_meta, save_meta
from anki_git.engine.git_ops import (
    get_or_init_repo,
    stage_all,
    ensure_gitignore,
    create_snapshot_commit,
    push_to_remote,
    is_dirty,
)
from anki_git.formats.notetype_yaml import (
    Notetype,
    write_notetype,
    read_all_notetypes,
)
from anki_git.formats.notes_md import Note, write_note_file


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
    ):
        self.notes_changed = notes_changed
        self.notetypes_changed = notetypes_changed
        self.changed_decks = changed_decks or {}
        self.changed_notetypes = changed_notetypes or []
        self.error = error


def export_collection(
    col: Collection,
    repo_path: Path,
    remote_url: str = "",
    progress_callback: callable = None,
) -> ExportResult:
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

    changed_notetypes = []
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

    meta_checksums = meta.get("note_checksums", {})

    if progress_callback:
        progress_callback("Reading notes...")
    nids = col.db.list("SELECT id FROM notes WHERE id > 0")
    total = len(nids)
    notes_by_deck: Dict[str, List[Note]] = {}
    note_checksums: Dict[str, str] = {}
    notes_changed = 0

    for i, nid in enumerate(nids):
        if progress_callback and i % 100 == 0:
            progress_callback(f"Processing notes... {i}/{total}")
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
        tags = list(note_obj.tags)

        note = Note(
            nid=nid,
            notetype=nt_name,
            tags=tags,
            deck=deck_name,
            fields=fields,
        )

        serialized = note.serialize()
        checksum = str(hash(serialized))
        note_checksums[str(nid)] = checksum

        old_checksum = meta_checksums.get(str(nid))
        if old_checksum != checksum:
            notes_changed += 1

        if deck_name not in notes_by_deck:
            notes_by_deck[deck_name] = []
        notes_by_deck[deck_name].append(note)

        deck_path_parts = deck_name.split("::")
        note_dir = decks_dir.joinpath(*deck_path_parts)
        write_note_file(note_dir, note)

    if progress_callback:
        progress_callback("Writing note files...")

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

        stage_all(repo)
        if is_dirty(repo):
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

    return result
