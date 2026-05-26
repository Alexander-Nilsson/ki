from dataclasses import dataclass, asdict
from enum import StrEnum


class SyncMode(StrEnum):
    ALWAYS_ASK = "always_ask"
    PREFER_ANKI = "prefer_anki"
    PREFER_REPO = "prefer_repo"
    ACCEPT_ALL = "accept_all"


SYNC_MODE_CHOICES = [
    (SyncMode.ALWAYS_ASK, "Always ask — show conflict dialog"),
    (SyncMode.PREFER_ANKI, "Prefer Anki — auto-resolve with Anki version"),
    (SyncMode.PREFER_REPO, "Prefer Repo — auto-resolve with repo version"),
    (SyncMode.ACCEPT_ALL, "Accept all — auto-merge when safe; Anki wins on true conflict"),
]


@dataclass
class KiSyncConfig:
    repo_path: str = ""
    auto_sync_on_startup: bool = True
    auto_snapshot_on_close: bool = True
    media_strategy: str = "none"
    auto_push_after_snapshot: bool = True
    log_level: str = "INFO"
    sync_mode: str = SyncMode.ALWAYS_ASK

    @classmethod
    def from_dict(cls, d: dict) -> "KiSyncConfig":
        if d is None:
            return cls()
        valid_keys = set(asdict(cls()).keys())
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered)

    def to_dict(self) -> dict:
        return asdict(self)
