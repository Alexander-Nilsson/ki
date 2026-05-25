"""Shared export helpers used by both exporter.py and sync.py.

Provides a single-note export routine so the note-walking + serialization
logic lives in one place instead of being duplicated in exporter.py and
sync.py.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple, TYPE_CHECKING

from anki.collection import Collection
from anki.notes import NoteId

if TYPE_CHECKING:
    from anki_git.formats.notes_md import Note

_logger = logging.getLogger("anki_git")

DECKS_DIR = "decks"


def export_single_note(col: Collection, repo_path: Path, nid: int) -> Optional[Tuple[Path, str, Note]]:
    """Export a single note from Anki into repo files.

    Returns (file_path, serialized_content, Note) on success, None on failure.
    The caller is responsible for checksum comparison if needed.
    """
    from anki_git.formats.notes_md import Note, write_note_file

    try:
        note_obj = col.get_note(NoteId(nid))
    except Exception:
        _logger.warning("Failed to get note %d", nid)
        return None

    nt_dict = note_obj.note_type()
    if nt_dict is None:
        _logger.warning("Note %d has no notetype, skipping", nid)
        return None

    try:
        cards = note_obj.cards()
        if not cards:
            _logger.debug("Note %d has no cards, skipping", nid)
            return None
        deck_name = col.decks.name(cards[0].did)
    except Exception as e:
        _logger.warning("Failed to get deck for note %d: %s", nid, e)
        return None

    fields = dict(note_obj.items())
    note = Note(
        nid=nid,
        notetype=nt_dict["name"],
        tags=list(note_obj.tags),
        deck=deck_name,
        fields=fields,
    )
    serialized = note.serialize()
    deck_path_parts = deck_name.split("::")
    note_dir = repo_path / DECKS_DIR / Path(*deck_path_parts)
    path = write_note_file(note_dir, note, content=serialized)
    return path, serialized, note
