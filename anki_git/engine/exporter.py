import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from anki.collection import Collection
from anki.models import NotetypeDict

from anki_git.engine.checksums import notes_hash, load_meta, save_meta
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
from anki_git.formats.notes_md import Note, write_notes_file


DECK_NOTES_FILE = "notes.md"
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


def export_collection(col: Collection, repo_path: Path, remote_url: str = "") -> ExportResult:
    result = ExportResult()

    repo = get_or_init_repo(repo_path)
    ensure_gitignore(repo_path)

    meta = load_meta(repo_path)
    last_export_time = meta.get("last_export_time", 0)

    notetypes_dir = repo_path / NOTETYPES_DIR
    decks_dir = repo_path / DECKS_DIR

    old_notetypes = read_all_notetypes(notetypes_dir)

    current_notetypes: Dict[str, Notetype] = {}
    for nt_dict in col.models.all():
        nt = Notetype.from_anki_dict(nt_dict)
        current_notetypes[nt.name] = nt

    changed_notetypes = []
    for name, nt in current_notetypes.items():
        old = old_notetypes.get(name)
        old_yaml = "\n".join(old.to_yaml_lines()) if old else ""
        new_yaml = "\n".join(nt.to_yaml_lines())
        if old_yaml != new_yaml:
            changed_notetypes.append(name)
            write_notetype(notetypes_dir, nt)

    meta_checksums = meta.get("note_checksums", {})

    nids = col.db.list("SELECT id FROM notes WHERE id > 0")
    notes_by_deck: Dict[str, List[Note]] = {}
    note_checksums: Dict[str, str] = {}
    notes_changed = 0

    for nid in nids:
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

        deck_path_parts = deck_name.split("::")
        if deck_name not in notes_by_deck:
            notes_by_deck[deck_name] = []
        notes_by_deck[deck_name].append(note)

    for deck_name, deck_notes in notes_by_deck.items():
        deck_path_parts = deck_name.split("::")
        notes_file_path = decks_dir.joinpath(*deck_path_parts) / DECK_NOTES_FILE
        write_notes_file(notes_file_path, deck_notes)

    result.notes_changed = notes_changed
    result.notetypes_changed = len(changed_notetypes)
    result.changed_notetypes = changed_notetypes
    result.changed_decks = {d: len(ns) for d, ns in notes_by_deck.items()}

    if notes_changed > 0 or result.notetypes_changed > 0:
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
            push_to_remote(repo, remote_url)

    return result
