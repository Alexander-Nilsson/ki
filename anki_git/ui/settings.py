from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QCheckBox, QComboBox, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QLabel, QApplication,
)
from git import GitCommandError

from anki_git.config import KiSyncConfig, SYNC_MODE_CHOICES
from anki_git.engine.git_ops import open_repo, get_existing_remote_url


class SettingsDialog(QDialog):
    def __init__(self, config: KiSyncConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("AnkiGit Settings")
        self.setMinimumWidth(550)
        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        repo_group = QGroupBox("Repository", self)
        repo_layout = QFormLayout(repo_group)
        repo_path_layout = QHBoxLayout()
        self._repo_path_input = QLineEdit(self)
        self._repo_path_input.setPlaceholderText("/path/to/anki-repo")
        browse_btn = QPushButton("Browse...", self)
        browse_btn.clicked.connect(self._browse_repo)
        repo_path_layout.addWidget(self._repo_path_input)
        repo_path_layout.addWidget(browse_btn)
        repo_layout.addRow("Repo path:", repo_path_layout)
        remote_layout = QHBoxLayout()
        self._check_remote_btn = QPushButton("Check Remote", self)
        self._check_remote_btn.clicked.connect(self._check_remote)
        self._remote_check_label = QLabel("", self)
        remote_layout.addWidget(self._check_remote_btn)
        remote_layout.addWidget(self._remote_check_label)
        remote_layout.addStretch()
        repo_layout.addRow("Remote:", remote_layout)
        layout.addWidget(repo_group)

        sync_group = QGroupBox("Sync Behavior", self)
        sync_layout = QFormLayout(sync_group)
        self._auto_startup_cb = QCheckBox("Auto-sync on startup", self)
        sync_layout.addRow(self._auto_startup_cb)
        self._auto_close_cb = QCheckBox("Auto-snapshot on close", self)
        sync_layout.addRow(self._auto_close_cb)

        self._bg_mode_cb = QCheckBox("Background mode (no dialogs)", self)
        sync_layout.addRow(self._bg_mode_cb)
        bg_note = QLabel(
            "Run auto operations silently without progress or result dialogs.\n"
            "Errors are logged to the addon log file."
        )
        bg_note.setStyleSheet("color: #888; font-size: 11px;")
        sync_layout.addRow("", bg_note)

        self._auto_push_cb = QCheckBox("Auto-push after snapshot", self)
        sync_layout.addRow(self._auto_push_cb)

        self._sync_mode_combo = QComboBox(self)
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

        layout.addWidget(sync_group)

        media_group = QGroupBox("Media", self)
        media_layout = QFormLayout(media_group)
        self._media_strategy_combo = QComboBox(self)
        self._media_strategy_combo.addItems(["none", "symlink", "copy", "git-lfs"])
        media_layout.addRow("Media strategy:", self._media_strategy_combo)
        layout.addWidget(media_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_config(self):
        self._repo_path_input.setText(self.config.repo_path)
        self._auto_startup_cb.setChecked(self.config.auto_sync_on_startup)
        self._auto_close_cb.setChecked(self.config.auto_snapshot_on_close)
        self._bg_mode_cb.setChecked(self.config.background_mode)
        self._auto_push_cb.setChecked(self.config.auto_push_after_snapshot)

        idx = self._media_strategy_combo.findText(self.config.media_strategy)
        if idx >= 0:
            self._media_strategy_combo.setCurrentIndex(idx)
        idx = self._sync_mode_combo.findData(self.config.sync_mode)
        if idx >= 0:
            self._sync_mode_combo.setCurrentIndex(idx)

    def _save_and_accept(self):
        self.config.repo_path = self._repo_path_input.text().strip()
        self.config.auto_sync_on_startup = self._auto_startup_cb.isChecked()
        self.config.auto_snapshot_on_close = self._auto_close_cb.isChecked()
        self.config.background_mode = self._bg_mode_cb.isChecked()
        self.config.auto_push_after_snapshot = self._auto_push_cb.isChecked()
        self.config.media_strategy = self._media_strategy_combo.currentText()
        self.config.sync_mode = self._sync_mode_combo.currentData()
        self.accept()

    def _browse_repo(self):
        path = QFileDialog.getExistingDirectory(self, "Select Git Repository Path")
        if path:
            self._repo_path_input.setText(path)

    def _check_remote(self):
        from pathlib import Path

        path_str = self._repo_path_input.text().strip()
        if not path_str:
            self._remote_check_label.setText("No repo path set")
            return

        repo_path = Path(path_str)
        repo = open_repo(repo_path)
        if repo is None:
            self._remote_check_label.setText("Not a Git repository")
            return

        url = get_existing_remote_url(repo)
        if not url:
            self._remote_check_label.setText("No remote 'origin' configured")
            return

        self._check_remote_btn.setEnabled(False)
        self._check_remote_btn.setText("Verifying...")
        self._remote_check_label.setText("")
        QApplication.processEvents()

        try:
            repo.git.ls_remote("origin")
            self._remote_check_label.setText(f"Connected: {url}")
            self._remote_check_label.setStyleSheet("color: green;")
        except GitCommandError as e:
            self._remote_check_label.setText(f"Cannot reach remote: {str(e)[:80]}")
            self._remote_check_label.setStyleSheet("color: red;")
        except Exception as e:
            self._remote_check_label.setText(f"Error: {str(e)[:80]}")
            self._remote_check_label.setStyleSheet("color: red;")
        finally:
            self._check_remote_btn.setEnabled(True)
            self._check_remote_btn.setText("Check Remote")
