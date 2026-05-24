import datetime
import logging
from pathlib import Path

from anki_git.config import KiSyncConfig
from anki_git.engine.exporter import export_collection
from anki_git.engine.git_ops import get_or_init_repo, get_commit_count

_export_timer = None
_config = None
_logger = logging.getLogger("anki_git")

# Setup file logging for debugging
_log_path = Path(__file__).parent.parent / "anki_git.log"
_file_handler = logging.FileHandler(_log_path, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
_logger.addHandler(_file_handler)
_logger.setLevel(logging.DEBUG)
_logger.info("AnkiGit logger initialized. Logging to %s", _log_path)


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
    from aqt.qt import QMessageBox
    from aqt.operations import QueryOp
    from anki_git.ui import DiffDialog
    from anki_git.engine.diff import compute_export_diff

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

    def get_diff_with_progress(col):
        report = compute_export_diff(
            col, repo_path,
            progress_callback=lambda text: mw.taskman.run_on_main(
                lambda: mw.progress.update(label=text, type="sticky")
            )
        )
        if not report.has_changes:
            return report, None
        
        mw.taskman.run_on_main(lambda: mw.progress.update(label="Preparing preview...", type="sticky"))
        from anki_git.ui.diff import report_to_diff_data
        ui_data = report_to_diff_data(report)
        return report, ui_data

    def on_diff_done(result_tuple):
        report, ui_data = result_tuple
        if not report.has_changes:
            QMessageBox.information(mw, "AnkiGit", "No changes detected. Nothing to export.")
            return

        diff_dialog = DiffDialog(ui_data, mw)
        if not diff_dialog.exec():
            return

        def do_export(col):
            return export_collection(
                col, repo_path,
                remote_url=config.remote_url if config.auto_push_after_snapshot else "",
                progress_callback=lambda text: mw.taskman.run_on_main(
                    lambda: mw.progress.update(label=text, type="sticky")
                ),
                media_strategy=config.media_strategy,
            )

        def on_export_done(result):
            if result.error:
                _logger.error("Export failed: %s", result.error)
                QMessageBox.critical(mw, "AnkiGit Snapshot", f"Error: {result.error}")
                return

            msg = (
                f"Snapshot complete.\n"
                f"Notes changed: {result.notes_changed}\n"
                f"Notetypes changed: {result.notetypes_changed}\n"
                f"Total commits: {result.commit_count}\n"
                f"Duration: {result.duration_seconds:.1f}s"
            )
            QMessageBox.information(mw, "AnkiGit Snapshot", msg)

        def on_export_failed(e):
            _logger.exception("Export operation failed")
            QMessageBox.critical(mw, "AnkiGit", f"Snapshot failed: {e}")

        QueryOp(
            parent=mw,
            op=do_export,
            success=on_export_done,
        ).failure(on_export_failed).with_progress("Taking Snapshot...").run_in_background()

    def on_diff_failed(e):
        _logger.exception("Failed to compute export diff")
        QMessageBox.critical(mw, "AnkiGit", f"Failed to compute diff: {e}")

    QueryOp(
        parent=mw,
        op=get_diff_with_progress,
        success=on_diff_done,
    ).failure(on_diff_failed).with_progress("Reviewing Changes...").run_in_background()


def import_action() -> None:
    from aqt.qt import QMessageBox
    from aqt.operations import QueryOp
    from anki_git.ui import ConflictResolutionDialog, DiffDialog
    from anki_git.engine.importer import pull_from_repo
    from anki_git.engine.diff import compute_import_diff

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

    def get_diff_with_progress(col):
        report = compute_import_diff(
            col, repo_path,
            progress_callback=lambda text: mw.taskman.run_on_main(
                lambda: mw.progress.update(label=text, type="sticky")
            )
        )
        if not report.has_changes:
            return report, None
        
        mw.taskman.run_on_main(lambda: mw.progress.update(label="Preparing preview...", type="sticky"))
        from anki_git.ui.diff import report_to_diff_data
        ui_data = report_to_diff_data(report)
        return report, ui_data

    def on_diff_done(result_tuple):
        report, ui_data = result_tuple
        if not report or not report.has_changes:
            QMessageBox.information(mw, "AnkiGit", "No changes detected. Nothing to import.")
            return

        diff_dialog = DiffDialog(ui_data, mw)
        if not diff_dialog.exec():
            return

        def do_import(col):
            col_path = Path(col.path)
            backup_path = repo_path / ".ki" / "backups" / f"pre-import-{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}.anki2"
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path.write_bytes(col_path.read_bytes())

            import threading
            def handle_conflicts_bg(report):
                event = threading.Event()
                resolved = [report]
                def on_main():
                    diag = ConflictResolutionDialog(report, mw)
                    if diag.exec():
                        resolved[0] = diag.resolved_report
                    event.set()
                mw.taskman.run_on_main(on_main)
                event.wait()
                return resolved[0]

            return pull_from_repo(
                col, repo_path,
                conflict_callback=handle_conflicts_bg,
            )

        def on_import_done(result):
            if result.error:
                _logger.error("Import failed: %s", result.error)
                QMessageBox.critical(mw, "AnkiGit", f"Import failed: {result.error}")
                return

            msg = (
                f"Import complete.\n"
                f"Notes updated: {result.notes_updated}\n"
                f"Notes created: {result.notes_created}\n"
                f"Notetypes updated: {result.notetypes_updated}\n"
                f"Notetypes created: {result.notetypes_created}"
            )
            if result.warnings:
                _logger.warning("Import warnings: %s", result.warnings)
                msg += "\nWarnings:\n" + "\n".join(result.warnings[:5])
            if result.errors:
                _logger.error("Import errors: %s", result.errors)
                msg += "\nErrors:\n" + "\n".join(result.errors[:5])
            QMessageBox.information(mw, "AnkiGit Import", msg)
            mw.reset()

        def on_import_failed(e):
            _logger.exception("Import operation failed")
            QMessageBox.critical(mw, "AnkiGit", f"Import failed: {e}")

        QueryOp(
            parent=mw,
            op=do_import,
            success=on_import_done,
        ).failure(on_import_failed).with_progress("Pulling from Repo...").run_in_background()

    def on_diff_failed(e):
        _logger.exception("Failed to compute import diff")
        QMessageBox.critical(mw, "AnkiGit", f"Failed to compute diff: {e}")

    QueryOp(
        parent=mw,
        op=get_diff_with_progress,
        success=on_diff_done,
    ).failure(on_diff_failed).with_progress("Reviewing Changes...").run_in_background()


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
                mw.progress.start(label="Auto-snapshotting...", immediate=True)
                try:
                    export_collection(
                        mw.col, repo_path,
                        media_strategy=config.media_strategy,
                        progress_callback=lambda text: (
                            mw.progress.update(label=text),
                            mw.app.processEvents()
                        )
                    )
                finally:
                    mw.progress.finish()
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
        from aqt.operations import QueryOp
        QueryOp(
            parent=mw,
            op=lambda col: export_collection(col, repo_path, media_strategy=config.media_strategy),
            success=lambda _: None
        ).run_in_background()
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
