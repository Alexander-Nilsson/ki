from pathlib import Path

from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QCheckBox, QComboBox, QSpinBox, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QLabel,
)

from anki_git.config import KiSyncConfig, SYNC_MODE_CHOICES


def _get_remote_url_from_repo(repo) -> str:
    """Return the 'origin' remote URL from a git Repo object."""
    try:
        return repo.remote("origin").url
    except (ValueError, Exception):
        return ""


class SettingsDialog:
    def __init__(self, config: KiSyncConfig, parent=None):
        self.config = config
        self.dialog = QDialog(parent)
        self.dialog.setWindowTitle("AnkiGit Settings")
        self.dialog.setMinimumWidth(550)
        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        layout = QVBoxLayout(self.dialog)

        repo_group = QGroupBox("Repository", self.dialog)
        repo_layout = QFormLayout(repo_group)
        repo_path_layout = QHBoxLayout()
        self._repo_path_input = QLineEdit(self.dialog)
        self._repo_path_input.setPlaceholderText("/path/to/anki-repo")
        browse_btn = QPushButton("Browse...", self.dialog)
        browse_btn.clicked.connect(self._browse_repo)
        repo_path_layout.addWidget(self._repo_path_input)
        repo_path_layout.addWidget(browse_btn)
        repo_layout.addRow("Repo path:", repo_path_layout)
        layout.addWidget(repo_group)

        sync_group = QGroupBox("Sync Behavior", self.dialog)
        sync_layout = QFormLayout(sync_group)
        self._auto_startup_cb = QCheckBox("Auto-sync on startup", self.dialog)
        sync_layout.addRow(self._auto_startup_cb)
        self._auto_close_cb = QCheckBox("Auto-snapshot on close", self.dialog)
        sync_layout.addRow(self._auto_close_cb)

        self._bg_mode_cb = QCheckBox("Background mode (no dialogs)", self.dialog)
        sync_layout.addRow(self._bg_mode_cb)
        bg_note = QLabel(
            "Run auto operations silently without progress or result dialogs.\n"
            "Errors are logged to the addon log file."
        )
        bg_note.setStyleSheet("color: #888; font-size: 11px;")
        sync_layout.addRow("", bg_note)

        debounce_layout = QHBoxLayout()
        self._debounce_input = QSpinBox(self.dialog)
        self._debounce_input.setRange(500, 10000)
        self._debounce_input.setSingleStep(500)
        self._debounce_input.setSuffix(" ms")
        debounce_layout.addWidget(self._debounce_input)
        sync_layout.addRow("Debounce delay:", debounce_layout)

        self._sync_mode_combo = QComboBox(self.dialog)
        for value, label in SYNC_MODE_CHOICES:
            self._sync_mode_combo.addItem(label, value)
        sync_layout.addRow("Conflict resolution:", self._sync_mode_combo)

        mode_note = QLabel(
            "Always ask: show dialog for each conflict\n"
            "Anki wins: auto-resolve in favor of Anki\n"
            "Repo wins: auto-resolve in favor of repo\n"
            "Accept all: auto-accept non-conflicting changes; for true conflicts Anki wins"
        )
        mode_note.setStyleSheet("color: #888; font-size: 11px;")
        sync_layout.addRow("", mode_note)

        self._log_level_combo = QComboBox(self.dialog)
        self._log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        sync_layout.addRow("Log level:", self._log_level_combo)

        layout.addWidget(sync_group)

        media_group = QGroupBox("Media", self.dialog)
        media_layout = QFormLayout(media_group)
        self._media_strategy_combo = QComboBox(self.dialog)
        self._media_strategy_combo.addItems(["none", "symlink", "copy", "git-lfs"])
        media_layout.addRow("Media strategy:", self._media_strategy_combo)

        remote_url_layout = QHBoxLayout()
        self._remote_url_input = QLineEdit(self.dialog)
        self._remote_url_input.setPlaceholderText("https://github.com/user/repo.git")
        remote_url_layout.addWidget(self._remote_url_input)
        self._test_remote_btn = QPushButton("Test Remote", self.dialog)
        self._test_remote_btn.clicked.connect(self._test_remote)
        remote_url_layout.addWidget(self._test_remote_btn)
        media_layout.addRow("Remote URL:", remote_url_layout)

        self._auto_push_cb = QCheckBox("Auto-push after snapshot", self.dialog)
        media_layout.addRow(self._auto_push_cb)
        layout.addWidget(media_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self.dialog,
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.dialog.reject)
        layout.addWidget(buttons)

    def _load_config(self):
        self._repo_path_input.setText(self.config.repo_path)
        self._auto_startup_cb.setChecked(self.config.auto_sync_on_startup)
        self._auto_close_cb.setChecked(self.config.auto_snapshot_on_close)
        self._bg_mode_cb.setChecked(self.config.background_mode)
        self._debounce_input.setValue(self.config.debounce_delay_ms)
        idx = self._media_strategy_combo.findText(self.config.media_strategy)
        if idx >= 0:
            self._media_strategy_combo.setCurrentIndex(idx)
        self._remote_url_input.setText(self.config.remote_url)
        self._auto_push_cb.setChecked(self.config.auto_push_after_snapshot)
        idx = self._sync_mode_combo.findData(self.config.sync_mode)
        if idx >= 0:
            self._sync_mode_combo.setCurrentIndex(idx)

        idx = self._log_level_combo.findText(self.config.log_level.upper())
        if idx >= 0:
            self._log_level_combo.setCurrentIndex(idx)

        # Auto-detect existing remote from repo
        if not self.config.remote_url and self.config.repo_path:
            try:
                from anki_git.engine.git_ops import open_repo
                repo = open_repo(Path(self.config.repo_path))
                if repo is not None:
                    url = _get_remote_url_from_repo(repo)
                    if url:
                        self._remote_url_input.setText(url)
            except Exception:
                pass

    def _save_and_accept(self):
        self.config.repo_path = self._repo_path_input.text().strip()
        self.config.auto_sync_on_startup = self._auto_startup_cb.isChecked()
        self.config.auto_snapshot_on_close = self._auto_close_cb.isChecked()
        self.config.background_mode = self._bg_mode_cb.isChecked()
        self.config.debounce_delay_ms = self._debounce_input.value()
        self.config.media_strategy = self._media_strategy_combo.currentText()
        self.config.remote_url = self._remote_url_input.text().strip()
        self.config.auto_push_after_snapshot = self._auto_push_cb.isChecked()
        self.config.sync_mode = self._sync_mode_combo.currentData()
        self.config.log_level = self._log_level_combo.currentText()
        self.dialog.accept()

    def _test_remote(self):
        url = self._remote_url_input.text().strip()
        if not url:
            from aqt.qt import QMessageBox
            QMessageBox.warning(self.dialog, "Test Remote", "No remote URL entered.")
            return
        from aqt.qt import QMessageBox
        from git import GitCommandError
        from git import Repo
        try:
            repo_path = self._repo_path_input.text().strip()
            if repo_path:
                try:
                    repo = Repo(repo_path)
                    remote = repo.create_remote("_test_remote", url)
                    try:
                        remote.fetch(dry_run=True)
                        QMessageBox.information(
                            self.dialog, "Test Remote",
                            "Remote URL is valid and reachable.",
                        )
                    except GitCommandError as e:
                        QMessageBox.warning(
                            self.dialog, "Test Remote",
                            f"Remote URL is valid but not reachable:\n{e}",
                        )
                    finally:
                        try:
                            repo.delete_remote(remote)
                        except Exception:
                            pass
                    return
                except Exception:
                    pass
            # No valid local repo — just validate URL syntax via ls-remote
            import subprocess
            result = subprocess.run(
                ["git", "ls-remote", url],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                QMessageBox.information(
                    self.dialog, "Test Remote",
                    "Remote URL is valid and reachable.",
                )
            else:
                QMessageBox.warning(
                    self.dialog, "Test Remote",
                    f"Remote not reachable:\n{result.stderr.strip()}",
                )
        except subprocess.TimeoutExpired:
            QMessageBox.warning(
                self.dialog, "Test Remote",
                "Connection timed out after 15 seconds.",
            )
        except Exception as e:
            QMessageBox.critical(
                self.dialog, "Test Remote",
                f"Error testing remote:\n{e}",
            )

    def _browse_repo(self):
        path = QFileDialog.getExistingDirectory(self.dialog, "Select Git Repository Path")
        if path:
            self._repo_path_input.setText(path)

    def exec(self):
        return self.dialog.exec()
