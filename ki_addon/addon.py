import os
from pathlib import Path
from typing import Optional

from aqt import mw, gui_hooks
from aqt.qt import (
    QAction, QMenu, QMessageBox, QTimer,
)
from anki.collection import Collection

from ki_addon.config import KiSyncConfig
from ki_addon.engine.exporter import export_collection, ExportResult
from ki_addon.engine.git_ops import get_or_init_repo, get_commit_count
from ki_addon.ui.settings import SettingsDialog
from ki_addon.ui.progress import ProgressDialog

_export_timer: Optional[QTimer] = None
_config: Optional[KiSyncConfig] = None


def load_config() -> KiSyncConfig:
    global _config
    if _config is not None:
        return _config
    if mw is None:
        _config = KiSyncConfig()
        return _config
    try:
        raw = mw.addonManager.getConfig(__name__.split(".")[0])
        _config = KiSyncConfig.from_dict(raw) if raw else KiSyncConfig()
    except Exception:
        _config = KiSyncConfig()
    return _config


def save_config(config: KiSyncConfig) -> None:
    global _config
    _config = config
    if mw is not None:
        try:
            mw.addonManager.writeConfig(__name__.split(".")[0], config.to_dict())
        except Exception:
            pass


def snapshot_action() -> None:
    config = load_config()
    if not config.repo_path:
        QMessageBox.warning(
            mw, "ki Sync", "Please set a repository path in Tools > ki Sync > Settings first."
        )
        return

    if mw is None or mw.col is None:
        QMessageBox.critical(mw, "ki Sync", "No collection is open.")
        return

    repo_path = Path(config.repo_path)

    dialog = ProgressDialog("Taking Snapshot...", mw)
    dialog.set_text("Exporting collection to Git repo...")
    dialog.show()

    try:
        result = export_collection(
            mw.col, repo_path, remote_url=config.remote_url if config.auto_push_after_snapshot else ""
        )
        dialog.close()

        if result.error:
            QMessageBox.critical(mw, "ki Sync Snapshot", f"Error: {result.error}")
            return

        repo = get_or_init_repo(repo_path)
        commit_count = get_commit_count(repo)
        msg = (
            f"Snapshot complete.\n"
            f"Notes changed: {result.notes_changed}\n"
            f"Notetypes changed: {result.notetypes_changed}\n"
            f"Total commits: {commit_count}"
        )
        QMessageBox.information(mw, "ki Sync Snapshot", msg)

    except Exception as e:
        dialog.close()
        QMessageBox.critical(mw, "ki Sync Snapshot", f"Snapshot failed: {e}")


def settings_action() -> None:
    config = load_config()
    dialog = SettingsDialog(config, mw)
    if dialog.exec():
        save_config(dialog.config)


def show_menu() -> None:
    if mw is None:
        return

    parent_menu = None
    for action in mw.form.menubar.actions():
        if action.text().strip().lower() == "tools":
            parent_menu = action.menu()
            break

    if parent_menu is None:
        parent_menu = QMenu("ki Sync", mw)

    snapshot_act = QAction("Take Snapshot", mw)
    snapshot_act.triggered.connect(snapshot_action)
    parent_menu.addAction(snapshot_act)

    settings_act = QAction("Settings...", mw)
    settings_act.triggered.connect(settings_action)
    parent_menu.addAction(settings_act)

    if parent_menu not in (a.menu() for a in mw.form.menubar.actions()):
        mw.form.menubar.addMenu(parent_menu)


def on_profile_open() -> None:
    config = load_config()
    if config.auto_sync_on_startup and config.repo_path:
        snapshot_action()


def on_profile_close() -> None:
    config = load_config()
    if config.auto_snapshot_on_close and config.repo_path:
        try:
            if mw is not None and mw.col is not None:
                repo_path = Path(config.repo_path)
                export_collection(mw.col, repo_path)
        except Exception:
            pass


def on_note_change(note) -> None:
    global _export_timer
    config = load_config()
    if not config.repo_path:
        return
    if _export_timer is not None:
        _export_timer.stop()
    _export_timer = QTimer()
    _export_timer.setSingleShot(True)
    _export_timer.timeout.connect(_debounced_export)
    _export_timer.start(config.debounce_delay_ms)


def _debounced_export() -> None:
    config = load_config()
    if mw is None or mw.col is None or not config.repo_path:
        return
    try:
        repo_path = Path(config.repo_path)
        export_collection(mw.col, repo_path)
    except Exception:
        pass


def init_addon() -> None:
    show_menu()
    gui_hooks.profile_did_open.append(on_profile_open)
    gui_hooks.profile_will_close.append(on_profile_close)
    gui_hooks.note_will_flush.append(on_note_change)
