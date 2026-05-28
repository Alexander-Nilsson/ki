"""Tests for the Settings dialog."""

import pytest

from anki_git.config import AnkiGitConfig, SyncMode


class TestSettingsDialogLogic:
    """Test settings dialog logic without Qt."""

    def test_config_roundtrip(self):
        config = AnkiGitConfig(
            repo_path="/tmp/test",
            auto_sync_on_startup=True,
            auto_snapshot_on_close=False,
            log_level="DEBUG",
            sync_mode=SyncMode.PREFER_REPO,
        )
        d = config.to_dict()
        restored = AnkiGitConfig.from_dict(d)
        assert restored == config

    def test_config_defaults(self):
        config = AnkiGitConfig()
        assert config.sync_mode == SyncMode.ALWAYS_ASK
        assert config.log_level == "INFO"

    def test_config_ignores_extra_keys(self):
        config = AnkiGitConfig.from_dict({
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

        config = AnkiGitConfig(repo_path="/tmp/test")
        parent = QWidget()
        dialog = SettingsDialog(config, parent)
        assert dialog is not None
        assert dialog.config == config
        parent.deleteLater()
