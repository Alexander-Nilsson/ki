import datetime
import logging
from pathlib import Path

from anki_git.config import KiSyncConfig
from anki_git.engine.exporter import export_collection
from anki_git.engine.git_ops import get_or_init_repo, get_commit_count

_export_timer = None
_config = None
_logger = logging.getLogger("anki_git")


def _import(name):
    import importlib
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def load_config() -> KiSyncConfig:
    global _config
    if _config is not None:
        return _config
    aqt = _import("aqt")
    if aqt is None:
        _config = KiSyncConfig()
        return _config
    try:
        raw = aqt.mw.addonManager.getConfig(__name__.split(".")[0])
        _config = KiSyncConfig.from_dict(raw) if raw else KiSyncConfig()
    except Exception:
        _config = KiSyncConfig()
    return _config


def save_config(config: KiSyncConfig) -> None:
    global _config
    _config = config
    aqt = _import("aqt")
    if aqt is not None:
        try:
            aqt.mw.addonManager.writeConfig(__name__.split(".")[0], config.to_dict())
        except Exception as e:
            _logger.warning("Failed to save config: %s", e)


def snapshot_action() -> None:
    from aqt.qt import QMessageBox, QApplication
    from anki_git.ui import ProgressDialog

    config = load_config()
    from aqt import mw

    if not config.repo_path:
        QMessageBox.warning(
            mw, "AnkiGit", "Please set a repository path in Tools > AnkiGit > Settings first."
        )
        return

    if mw is None or mw.col is None:
        QMessageBox.critical(mw, "AnkiGit", "No collection is open.")
        return

    repo_path = Path(config.repo_path)
    dialog = ProgressDialog("Taking Snapshot...", mw)
    dialog.set_text("Exporting collection to Git repo...")
    dialog.show()
    QApplication.processEvents()

    def progress(text: str) -> None:
        dialog.set_text(text)
        QApplication.processEvents()

    try:
        result = export_collection(
            mw.col, repo_path,
            remote_url=config.remote_url if config.auto_push_after_snapshot else "",
            progress_callback=progress,
            media_strategy=config.media_strategy,
        )
        dialog.close()

        if result.error:
            QMessageBox.critical(mw, "AnkiGit Snapshot", f"Error: {result.error}")
            return

        repo = get_or_init_repo(repo_path)
        commit_count = get_commit_count(repo)
        msg = (
            f"Snapshot complete.\n"
            f"Notes changed: {result.notes_changed}\n"
            f"Notetypes changed: {result.notetypes_changed}\n"
            f"Total commits: {commit_count}"
        )
        QMessageBox.information(mw, "AnkiGit Snapshot", msg)

    except Exception as e:
        dialog.close()
        QMessageBox.critical(mw, "AnkiGit Snapshot", f"Snapshot failed: {e}")


def import_action() -> None:
    from aqt.qt import QMessageBox, QApplication
    from anki_git.ui import ProgressDialog, ConflictResolutionDialog
    from anki_git.engine.importer import pull_from_repo

    config = load_config()
    from aqt import mw

    if not config.repo_path:
        QMessageBox.warning(
            mw, "AnkiGit", "Please set a repository path in Tools > AnkiGit > Settings first."
        )
        return

    if mw is None or mw.col is None:
        QMessageBox.critical(mw, "AnkiGit", "No collection is open.")
        return

    repo_path = Path(config.repo_path)
    if not (repo_path / ".git").exists():
        QMessageBox.warning(mw, "AnkiGit", "No Git repository found. Take a snapshot first.")
        return

    dialog = ProgressDialog("Pulling from Repo...", mw)
    dialog.set_text("Analyzing collection and repo...")
    dialog.show()
    QApplication.processEvents()

    def progress(text: str) -> None:
        dialog.set_text(text)
        QApplication.processEvents()

    def handle_conflicts(report):
        dialog.close()
        report_dialog = ConflictResolutionDialog(report, mw)
        if report_dialog.exec():
            return report_dialog.resolved_report
        return report

    try:
        col_path = Path(mw.col.path)
        backup_path = repo_path / ".ki" / "backups" / f"pre-import-{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}.anki2"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(col_path.read_bytes())
        progress("Backup created.")

        progress("Computing checksums and detecting conflicts...")
        result = pull_from_repo(
            mw.col, repo_path,
            conflict_callback=handle_conflicts,
        )
        dialog.close()

        msg = (
            f"Import complete.\n"
            f"Notes updated: {result.notes_updated}\n"
            f"Notes created: {result.notes_created}\n"
            f"Notetypes updated: {result.notetypes_updated}\n"
            f"Notetypes created: {result.notetypes_created}"
        )
        if result.warnings:
            msg += "\nWarnings:\n" + "\n".join(result.warnings[:5])
        if result.errors:
            msg += "\nErrors:\n" + "\n".join(result.errors[:5])
        QMessageBox.information(mw, "AnkiGit Import", msg)

    except Exception as e:
        dialog.close()
        _logger.error("Import failed: %s", e)
        QMessageBox.critical(mw, "AnkiGit Import", f"Import failed: {e}")


def settings_action() -> None:
    from aqt import mw
    from anki_git.ui import SettingsDialog
    config = load_config()
    dialog = SettingsDialog(config, mw)
    if dialog.exec():
        save_config(dialog.config)


def show_menu() -> None:
    from aqt import mw
    from aqt.qt import QAction, QMenu

    if mw is None:
        return

    parent_menu = None
    for action in mw.form.menubar.actions():
        if action.text().strip().lower() == "tools":
            parent_menu = action.menu()
            break

    if parent_menu is None:
        parent_menu = QMenu("AnkiGit", mw)

    snapshot_act = QAction("Take Snapshot", mw)
    snapshot_act.triggered.connect(snapshot_action)
    parent_menu.addAction(snapshot_act)

    import_act = QAction("Pull from Repo", mw)
    import_act.triggered.connect(import_action)
    parent_menu.addAction(import_act)

    settings_act = QAction("Settings...", mw)
    settings_act.triggered.connect(settings_action)
    parent_menu.addAction(settings_act)

    if parent_menu not in (a.menu() for a in mw.form.menubar.actions()):
        mw.form.menubar.addMenu(parent_menu)


_menu_shown = False


def on_profile_open() -> None:
    global _menu_shown
    if not _menu_shown:
        show_menu()
        _menu_shown = True
    config = load_config()
    if config.auto_sync_on_startup and config.repo_path:
        snapshot_action()


def on_profile_close() -> None:
    config = load_config()
    if config.auto_snapshot_on_close and config.repo_path:
        try:
            from aqt import mw
            if mw is not None and mw.col is not None:
                repo_path = Path(config.repo_path)
                export_collection(mw.col, repo_path, media_strategy=config.media_strategy)
        except Exception as e:
            _logger.warning("Auto-snapshot on close failed: %s", e)


def on_note_change(note) -> None:
    global _export_timer
    from aqt.qt import QTimer

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
    from aqt import mw
    if mw is None or mw.col is None or not config.repo_path:
        return
    try:
        repo_path = Path(config.repo_path)
        export_collection(mw.col, repo_path, media_strategy=config.media_strategy)
    except Exception as e:
        _logger.warning("Debounced export failed: %s", e)


def _on_operation(changes, handler) -> None:
    if changes.note or changes.notetype:
        on_note_change(None)


def init_addon() -> None:
    from aqt import gui_hooks
    gui_hooks.profile_did_open.append(on_profile_open)
    gui_hooks.profile_will_close.append(on_profile_close)
    gui_hooks.operation_did_execute.append(_on_operation)
