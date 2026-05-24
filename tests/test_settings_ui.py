"""Tests for the Settings dialog."""

import pytest

from anki_git.config import KiSyncConfig, SyncMode


class TestSettingsDialogLogic:
    """Test settings dialog logic without Qt."""

    def test_config_roundtrip(self):
        config = KiSyncConfig(
            repo_path="/tmp/test",
            auto_sync_on_startup=True,
            auto_snapshot_on_close=False,
            debounce_delay_ms=3000,
            media_strategy="symlink",
            log_level="DEBUG",
            sync_mode=SyncMode.PREFER_REPO,
        )
        d = config.to_dict()
        restored = KiSyncConfig.from_dict(d)
        assert restored == config

    def test_config_defaults(self):
        config = KiSyncConfig()
        assert config.sync_mode == SyncMode.ALWAYS_ASK
        assert config.media_strategy == "none"
        assert config.log_level == "INFO"

    def test_config_ignores_extra_keys(self):
        config = KiSyncConfig.from_dict({
            "repo_path": "/tmp/path",
            "nonexistent_key": "value",
        })
        assert config.repo_path == "/tmp/path"


@pytest.mark.integration
class TestSettingsDialogWithQt:
    """Test that SettingsDialog can be instantiated (needs aqt)."""

    def test_dialog_instantiates(self):
        from aqt.qt import QApplication, QWidget
        _ = QApplication.instance() or QApplication([])

        from anki_git.ui.settings import SettingsDialog

        config = KiSyncConfig(repo_path="/tmp/test")
        parent = QWidget()
        dialog = SettingsDialog(config, parent)
        assert dialog is not None
        assert dialog.config == config
        parent.deleteLater()
