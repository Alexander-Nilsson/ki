from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QCheckBox, QComboBox, QSpinBox, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QLabel,
)

from anki_git.config import KiSyncConfig, SYNC_MODE_CHOICES


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

        self._auto_push_cb = QCheckBox("Auto-push after snapshot", self.dialog)
        sync_layout.addRow(self._auto_push_cb)

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

        layout.addWidget(sync_group)

        media_group = QGroupBox("Media", self.dialog)
        media_layout = QFormLayout(media_group)
        self._media_strategy_combo = QComboBox(self.dialog)
        self._media_strategy_combo.addItems(["none", "symlink", "copy", "git-lfs"])
        media_layout.addRow("Media strategy:", self._media_strategy_combo)
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
        self._auto_push_cb.setChecked(self.config.auto_push_after_snapshot)
        self._debounce_input.setValue(self.config.debounce_delay_ms)
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
        self.config.debounce_delay_ms = self._debounce_input.value()
        self.config.media_strategy = self._media_strategy_combo.currentText()
        self.config.sync_mode = self._sync_mode_combo.currentData()
        self.dialog.accept()

    def _browse_repo(self):
        path = QFileDialog.getExistingDirectory(self.dialog, "Select Git Repository Path")
        if path:
            self._repo_path_input.setText(path)

    def exec(self):
        return self.dialog.exec()
