from dataclasses import dataclass, asdict
from enum import StrEnum


class SyncMode(StrEnum):
    ALWAYS_ASK = "always_ask"
    PREFER_ANKI = "prefer_anki"
    PREFER_REPO = "prefer_repo"
    ACCEPT_ALL = "accept_all"


SYNC_MODE_CHOICES = [
    (SyncMode.ALWAYS_ASK, "Always ask"),
    (SyncMode.PREFER_ANKI, "Anki wins"),
    (SyncMode.PREFER_REPO, "Repo wins"),
    (SyncMode.ACCEPT_ALL, "Accept all (auto-resolve)"),
]


@dataclass
class KiSyncConfig:
    repo_path: str = ""
    auto_sync_on_startup: bool = False
    auto_snapshot_on_close: bool = False
    debounce_delay_ms: int = 2000
    media_strategy: str = "none"
    remote_url: str = ""
    auto_push_after_snapshot: bool = False
    log_level: str = "INFO"
    sync_mode: str = SyncMode.ALWAYS_ASK
    background_mode: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "KiSyncConfig":
        if d is None:
            return cls()
        valid_keys = set(asdict(cls()).keys())
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered)

    def to_dict(self) -> dict:
        return asdict(self)
