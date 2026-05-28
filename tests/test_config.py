"""Tests for config module."""
from anki_git.config import SYNC_MODE_CHOICES, AnkiGitConfig, SyncMode


class TestSyncMode:
    def test_is_str_enum(self):
        assert SyncMode.ALWAYS_ASK == "always_ask"
        assert SyncMode.PREFER_ANKI == "prefer_anki"
        assert SyncMode.PREFER_REPO == "prefer_repo"
        assert SyncMode.ACCEPT_ALL == "accept_all"

    def test_choices_match_values(self):
        for value, _ in SYNC_MODE_CHOICES:
            assert value in (
                SyncMode.ALWAYS_ASK,
                SyncMode.PREFER_ANKI,
                SyncMode.PREFER_REPO,
                SyncMode.ACCEPT_ALL,
            )

    def test_enum_uniqueness(self):
        values = [SyncMode.ALWAYS_ASK, SyncMode.PREFER_ANKI,
                  SyncMode.PREFER_REPO, SyncMode.ACCEPT_ALL]
        assert len(set(values)) == 4


class TestAnkiGitConfig:
    def test_defaults(self):
        cfg = AnkiGitConfig()
        assert cfg.repo_path == ""
        assert cfg.auto_sync_on_startup is True
        assert cfg.auto_snapshot_on_close is True
        assert cfg.media_strategy == "none"
        assert cfg.log_level == "INFO"
        assert cfg.sync_mode == SyncMode.ALWAYS_ASK

    def test_from_dict_filters_invalid_keys(self):
        cfg = AnkiGitConfig.from_dict({
            "repo_path": "/tmp/test",
            "invalid_key": "should_be_ignored",
            "log_level": "DEBUG",
        })
        assert cfg.repo_path == "/tmp/test"
        assert cfg.log_level == "DEBUG"
        assert not hasattr(cfg, "invalid_key")

    def test_from_dict_empty(self):
        cfg = AnkiGitConfig.from_dict({})
        assert cfg.repo_path == ""

    def test_from_dict_none(self):
        cfg = AnkiGitConfig.from_dict(None)
        assert cfg.repo_path == ""

    def test_to_dict_roundtrip(self):
        cfg1 = AnkiGitConfig(
            repo_path="/tmp/repo",
            auto_sync_on_startup=False,
            auto_snapshot_on_close=False,
            media_strategy="symlink",
            log_level="DEBUG",
            sync_mode=SyncMode.PREFER_ANKI,
        )
        d = cfg1.to_dict()
        cfg2 = AnkiGitConfig.from_dict(d)
        assert cfg1 == cfg2

    def test_sync_mode_string_equality(self):
        """StrEnum instances compare equal to their string values."""
        assert SyncMode.ALWAYS_ASK == "always_ask"
        assert SyncMode("always_ask") == SyncMode.ALWAYS_ASK

    def test_config_accepts_sync_mode_string(self):
        """AnkiGitConfig accepts both StrEnum and plain string for sync_mode."""
        cfg = AnkiGitConfig(sync_mode="prefer_anki")
        assert cfg.sync_mode == SyncMode.PREFER_ANKI
        assert cfg.sync_mode == "prefer_anki"
