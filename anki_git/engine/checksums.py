import hashlib
import json
from pathlib import Path
from typing import Dict, Optional

from anki.collection import Collection


META_DIR = ".ki"
META_FILE = "meta.json"


def content_hash(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def load_meta(repo_root: Path) -> dict:
    meta_path = repo_root / META_DIR / META_FILE
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def save_meta(repo_root: Path, meta: dict) -> None:
    meta_path = repo_root / META_DIR / META_FILE
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def quick_has_changes(col: Collection, repo_path: Path) -> Optional[bool]:
    """Quick check if anything has changed since last sync/export.

    Compares note count + MAX(mod) against stored baseline, and repo HEAD
    SHA against stored SHA.  Returns False if definitely nothing changed
    (full sync can be skipped), True if changes likely exist, or None if
    there is no baseline yet (first run).
    """
    from anki_git.engine.git_ops import is_dirty, open_repo

    meta = load_meta(repo_path)
    last_count = meta.get("last_note_count")
    last_max_mod = meta.get("last_max_mod")
    last_sha = meta.get("last_commit_sha")

    if last_count is None or last_max_mod is None:
        return None

    db = col.db
    assert db is not None
    count = db.scalar("SELECT COUNT(*) FROM notes WHERE id > 0") or 0
    max_mod = db.scalar("SELECT MAX(mod) FROM notes WHERE id > 0") or 0

    if count != last_count or max_mod != last_max_mod:
        return True

    repo = open_repo(repo_path)
    if repo is None:
        return True
    if is_dirty(repo):
        return True
    if last_sha and str(repo.head.commit) != last_sha:
        return True

    return False
