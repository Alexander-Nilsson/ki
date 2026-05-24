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
from anki_git.engine.checksums import content_hash, load_meta, save_meta
from anki_git.engine.conflict import (
    detect_conflicts,
    resolve_conflicts,
)
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


def _compute_anki_checksums(col: Collection) -> Dict[str, str]:
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
    from anki_git.formats.notes_md import parse_notes_file

    checksums = {}
    decks_dir = repo_path / DECKS_DIR
    for notes_file in sorted(decks_dir.rglob("*.md")):
        notes = parse_notes_file(notes_file)
        for note_data in notes:
            checksums[str(note_data.nid)] = content_hash(note_data.serialize())
    return checksums


def _import_single_note(col, repo_path: Path, nid: int) -> bool:
    """Import a single note from repo into Anki. Returns True on success."""
    from anki_git.formats.notes_md import parse_notes_file

    decks_dir = repo_path / DECKS_DIR
    for notes_file in sorted(decks_dir.rglob("*.md")):
        notes = parse_notes_file(notes_file)
        for note_data in notes:
            if note_data.nid == nid:
                try:
                    existing = col.get_note(nid)
                except Exception:
                    existing = None

                if existing is not None:
                    for key, value in note_data.fields.items():
                        if key in existing:
                            existing[key] = value
                    existing.tags = note_data.tags
                    existing.flush()
                    return True
                else:
                    model_id = col.models.id_for_name(note_data.notetype)
                    if model_id is None:
                        _logger.warning("Notetype '%s' not found for nid %d", note_data.notetype, nid)
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
    _logger.warning("Note %d not found in repo files", nid)
    return False


def _import_notetype(col, repo_path: Path, nt_name: str) -> bool:
    """Import a single notetype from repo into Anki."""
    notetypes_dir = repo_path / NOTETYPES_DIR
    repo_nt = read_all_notetypes(notetypes_dir)
    nt = repo_nt.get(nt_name)
    if nt is None:
        return False

    existing = col.models.by_name(nt_name)
    if existing:
        existing["flds"] = [
            {"name": f.name, "ord": f.ord, "font": f.font, "size": f.size, "sticky": f.sticky, "rtl": f.rtl}
            for f in nt.fields
        ]
        existing["tmpls"] = [
            {"name": t.name, "ord": t.ord, "qfmt": t.qfmt, "afmt": t.afmt}
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
    note = Note(nid=nid, notetype=nt_name, tags=list(note_obj.tags), deck=deck_name, fields=fields)
    deck_path_parts = deck_name.split("::")
    note_dir = repo_path / DECKS_DIR / Path(*deck_path_parts)
    serialized = note.serialize()
    write_note_file(note_dir, note, content=serialized)
    return True


def _compute_notetype_checksums(notetypes_dir: Path) -> Dict[str, str]:
    """Compute checksums for notetypes in the repo."""
    checksums = {}
    repo_nts = read_all_notetypes(notetypes_dir)
    for name, nt in repo_nts.items():
        checksums[name] = content_hash("\n".join(nt.to_yaml_lines()))
    return checksums


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
    anki_checksums = _compute_anki_checksums(col)

    if progress_callback:
        progress_callback("Computing repo checksums...")
    git_checksums = _compute_git_checksums(repo_path)

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

    # Apply changes: export (anki → repo)
    if progress_callback:
        progress_callback("Exporting changes to repo...")

    col.db.execute("begin")
    try:
        # Import git changes into Anki first
        for nid in notes_to_import_nids:
            if _import_single_note(col, repo_path, nid):
                result.notes_imported += 1

        col.db.execute("commit")
    except Exception as e:
        col.db.execute("rollback")
        _logger.exception("Failed to import notes from repo")
        result.error = str(e)
        return result

    # Write exported notes to files
    for nid in notes_to_export:
        if _export_single_note(col, repo_path, nid):
            result.notes_exported += 1
            decks_dir = repo_path / DECKS_DIR
            for f in decks_dir.rglob(f"{nid}.md"):
                changed_files.add(str(f.relative_to(repo_path)))

    new_anki_checksums = _compute_anki_checksums(col)

    # Detect notetype changes between Anki and repo
    anki_notetypes: Dict[str, Notetype] = {}
    for nt_dict in col.models.all():
        nt = Notetype.from_anki_dict(nt_dict)
        anki_notetypes[nt.name] = nt

    if progress_callback:
        progress_callback("Syncing notetypes...")

    # Compute notetype checksums from both sides
    anki_nt_checksums: Dict[str, str] = {
        name: content_hash("\n".join(nt.to_yaml_lines()))
        for name, nt in anki_notetypes.items()
    }
    repo_nt_checksums = _compute_notetype_checksums(notetypes_dir)

    # Simple diff: if notetype exists only in Anki, export it; only in repo, import it
    all_nt_names = set(list(anki_nt_checksums.keys()) + list(repo_nt_checksums.keys()))
    for name in all_nt_names:
        anki_nt = anki_notetypes.get(name)
        repo_checksum = repo_nt_checksums.get(name)
        anki_checksum = anki_nt_checksums.get(name)

        if anki_nt and (repo_checksum is None or anki_checksum != repo_checksum):
            write_notetype(notetypes_dir, anki_nt)
            yaml_path, css_path = notetype_paths(notetypes_dir, name)
            changed_files.add(str(yaml_path.relative_to(repo_path)))
            if anki_nt.css or css_path.exists():
                changed_files.add(str(css_path.relative_to(repo_path)))
            result.notetypes_exported += 1
        elif not anki_nt and repo_checksum is not None:
            _import_notetype(col, repo_path, name)
            result.notetypes_imported += 1

    notes_changed = result.notes_exported + notes_to_import_nids
    notetypes_changed = result.notetypes_exported + result.notetypes_imported

    if notes_changed > 0 or notetypes_changed > 0:
        if progress_callback:
            progress_callback("Committing changes...")
        meta["last_export_time"] = int(time.time())
        meta["note_checksums"] = new_anki_checksums
        meta["collection_path"] = str(col.path)
        save_meta(repo_path, meta)

        changed_files.add(str((repo_path / META_DIR / "meta.json").relative_to(repo_path)))

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
        "Sync took %.2fs: %d notes exported, %d notes imported, %d notetypes exported, %d notetypes imported",
        result.duration_seconds,
        result.notes_exported,
        result.notes_imported,
        result.notetypes_exported,
        result.notetypes_imported,
    )
    if progress_callback:
        progress_callback(f"Sync complete ({result.duration_seconds:.1f}s)")

    return result
