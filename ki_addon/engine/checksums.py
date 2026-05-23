import hashlib
import json
from pathlib import Path
from typing import Dict


META_DIR = ".ki"
META_FILE = "meta.json"


def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def content_hash(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def notes_hash(notes: Dict[int, str]) -> Dict[str, str]:
    return {str(nid): content_hash(content) for nid, content in notes.items()}


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
