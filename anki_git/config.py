from dataclasses import dataclass, asdict


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

    @classmethod
    def from_dict(cls, d: dict) -> "KiSyncConfig":
        valid_keys = set(asdict(cls()).keys())
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered)

    def to_dict(self) -> dict:
        return asdict(self)
