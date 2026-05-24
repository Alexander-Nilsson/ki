import datetime
import logging
from pathlib import Path

from anki_git.config import KiSyncConfig, SyncMode
from anki_git.engine.exporter import export_collection
from anki_git.engine.git_ops import get_existing_remote_url, open_repo

_export_timer = None
_config = None
_logger = logging.getLogger("anki_git")


def _get_remote_url(repo_path: Path, enabled: bool = True) -> str:
    if not enabled:
        return ""
    repo = open_repo(repo_path)
    return get_existing_remote_url(repo) if repo else ""


def _import(name):
    import importlib
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _apply_log_level():
    """Apply the log_level from config to the anki_git logger."""
    config = load_config()
    level_name = config.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)
    _logger.setLevel(level)


# Setup file logging in the addon data directory
def _setup_logging():
    from aqt import mw
    if mw is None or mw.addonManager is None:
        return
    addon_id = __name__.split(".")[0]
    log_dir = Path(mw.addonManager.addonsFolder()) / addon_id / "user_files"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "anki_git.log"
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        )
        _logger.addHandler(file_handler)
        _apply_log_level()
        _logger.info("AnkiGit logger initialized. Logging to %s", log_path)
    except Exception as e:
        print(f"AnkiGit: Could not setup file logging: {e}")


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
    _apply_log_level()
    aqt = _import("aqt")
    if aqt is not None:
        try:
            aqt.mw.addonManager.writeConfig(
                __name__.split(".")[0], config.to_dict()
            )
        except Exception as e:
            _logger.warning("Failed to save config: %s", e)


def sync_action() -> None:
    from aqt.qt import QMessageBox
    from aqt.operations import QueryOp
    from anki_git.engine.sync import sync_collection

    config = load_config()
    from aqt import mw

    if not config.repo_path:
        QMessageBox.warning(
            mw, "AnkiGit",
            "Please set a repository path in "
            "Tools > AnkiGit > Settings first."
        )
        return

    if mw is None or mw.col is None:
        QMessageBox.critical(mw, "AnkiGit", "No collection is open.")
        return

    if config.background_mode:
        _logger.info("Background sync triggered from menu")
        _run_background_sync(config)
        return

    repo_path = Path(config.repo_path)

    def do_sync(col):
        _logger.info("Starting two-way sync...")

        import threading
        event = threading.Event()
        resolved_report = [None]

        def conflict_handler(report):
            from anki_git.ui import ConflictResolutionDialog

            def on_main():
                diag = ConflictResolutionDialog(report, mw)
                if diag.exec():
                    resolved_report[0] = diag.resolved_report  # type: ignore[arg-type]
                else:
                    resolved_report[0] = report  # type: ignore[arg-type]
                event.set()
            mw.taskman.run_on_main(on_main)
            event.wait()
            return resolved_report[0]

        sync_mode = config.sync_mode
        conflict_cb = (
            conflict_handler if sync_mode == SyncMode.ALWAYS_ASK else None
        )

        def preview_handler(preview):
            event_preview = threading.Event()
            result_preview = [False]

            def on_main():
                from aqt.qt import QMessageBox
                parts = []
                if preview.notes_to_export:
                    parts.append(f"Notes to push to repo: {preview.notes_to_export}")
                if preview.notes_to_import:
                    parts.append(f"Notes to pull from repo: {preview.notes_to_import}")
                if preview.notes_to_delete_from_git:
                    parts.append(f"Notes to delete from repo: {preview.notes_to_delete_from_git}")
                if preview.notes_to_delete_from_anki:
                    parts.append(f"Notes to delete from Anki: {preview.notes_to_delete_from_anki}")
                if preview.notetypes_to_sync:
                    parts.append(f"Notetypes to sync: {preview.notetypes_to_sync}")
                if preview.conflicts_unresolved:
                    parts.append(f"Unresolved conflicts (will be skipped): {preview.conflicts_unresolved}")

                msg = "\n".join(parts) + "\n\nProceed with sync?"
                result_preview[0] = QMessageBox.question(
                    mw, "AnkiGit Sync Preview",
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                ) == QMessageBox.StandardButton.Yes
                event_preview.set()
            mw.taskman.run_on_main(on_main)
            event_preview.wait()
            return result_preview[0]

        preview_cb = preview_handler if not config.background_mode else None

        return sync_collection(
            col,
            repo_path,
            sync_mode=sync_mode,
            conflict_callback=conflict_cb,
            preview_callback=preview_cb,
            remote_url=_get_remote_url(repo_path, config.auto_push_after_snapshot),
            progress_callback=lambda text: mw.taskman.run_on_main(
                lambda: mw.progress.update(label=text)
            ),
            media_strategy=config.media_strategy,
        )

    def on_sync_done(result):
        if result.error:
            _logger.error("Sync failed: %s", result.error)
            QMessageBox.critical(
                mw, "AnkiGit Sync", f"Error: {result.error}"
            )
            return

        parts = []
        if result.notes_exported:
            parts.append(f"Notes exported: {result.notes_exported}")
        if result.notes_imported:
            parts.append(f"Notes imported: {result.notes_imported}")
        if result.notetypes_exported:
            parts.append(
                f"Notetypes exported: {result.notetypes_exported}"
            )
        if result.notetypes_imported:
            parts.append(
                f"Notetypes imported: {result.notetypes_imported}"
            )
        if result.conflicts_resolved:
            parts.append(
                f"Conflicts resolved: {result.conflicts_resolved}"
            )
        if result.conflicts_unresolved:
            parts.append(
                f"Conflicts unresolved: {result.conflicts_unresolved}"
            )
        parts.append(f"Duration: {result.duration_seconds:.1f}s")

        if not parts:
            QMessageBox.information(
                mw, "AnkiGit Sync",
                "No changes detected. Everything is in sync."
            )
            return

        QMessageBox.information(mw, "AnkiGit Sync", "\n".join(parts))

    def on_sync_failed(e):
        _logger.exception("Sync operation failed")
        QMessageBox.critical(mw, "AnkiGit", f"Sync failed: {e}")

    QueryOp(
        parent=mw,
        op=do_sync,
        success=on_sync_done,
    ).failure(on_sync_failed).with_progress("Syncing...").run_in_background()


def snapshot_action() -> None:
    from aqt.qt import QMessageBox
    from aqt.operations import QueryOp
    from anki_git.ui import DiffDialog
    from anki_git.engine.diff import compute_export_diff

    config = load_config()
    from aqt import mw

    if not config.repo_path:
        QMessageBox.warning(
            mw, "AnkiGit",
            "Please set a repository path in "
            "Tools > AnkiGit > Settings first."
        )
        return

    if mw is None or mw.col is None:
        QMessageBox.critical(mw, "AnkiGit", "No collection is open.")
        return

    repo_path = Path(config.repo_path)

    def get_diff_with_progress(col):
        _logger.info("Computing export diff...")
        report = compute_export_diff(
            col, repo_path,
            progress_callback=lambda text: mw.taskman.run_on_main(
                lambda: mw.progress.update(label=text)
            )
        )
        _logger.info(
            "Diff computed: %d notes, %d notetypes changed",
            len(report.note_diffs), len(report.notetype_diffs)
        )
        if not report.has_changes:
            return report, None

        _logger.info("Converting report to UI data...")
        mw.taskman.run_on_main(
            lambda: mw.progress.update(label="Preparing preview...")
        )
        from anki_git.ui.diff import report_to_diff_data
        ui_data = report_to_diff_data(report)
        _logger.info("UI data ready (%d items)", len(ui_data))
        return report, ui_data

    def on_diff_done(result_tuple):
        _logger.info("on_diff_done reached")
        report, ui_data = result_tuple
        if not report.has_changes:
            _logger.info("No changes to export")
            QMessageBox.information(
                mw, "AnkiGit",
                "No changes detected. Nothing to export."
            )
            return

        _logger.info("Opening DiffDialog...")
        diff_dialog = DiffDialog(ui_data, mw)
        _logger.info("DiffDialog initialized")
        if not diff_dialog.exec():
            _logger.info("User discarded changes")
            return

        _logger.info("User accepted changes, starting export...")

        def do_export(col):
            return export_collection(
                col,
                repo_path,
                remote_url=_get_remote_url(repo_path, config.auto_push_after_snapshot),
                progress_callback=lambda text: mw.taskman.run_on_main(
                    lambda: mw.progress.update(label=text)
                ),
                media_strategy=config.media_strategy,
            )

        def on_export_done(result):
            if result.error:
                _logger.error("Export failed: %s", result.error)
                QMessageBox.critical(
                    mw, "AnkiGit Snapshot", f"Error: {result.error}"
                )
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
            QMessageBox.critical(
                mw, "AnkiGit", f"Snapshot failed: {e}"
            )

        QueryOp(
            parent=mw,
            op=do_export,
            success=on_export_done,
        ).failure(on_export_failed).with_progress(
            "Taking Snapshot..."
        ).run_in_background()

    def on_diff_failed(e):
        _logger.exception("Failed to compute export diff")
        QMessageBox.critical(
            mw, "AnkiGit", f"Failed to compute diff: {e}"
        )

    QueryOp(
        parent=mw,
        op=get_diff_with_progress,
        success=on_diff_done,
    ).failure(on_diff_failed).with_progress(
        "Reviewing Changes..."
    ).run_in_background()


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
            mw, "AnkiGit",
            "Please set a repository path in "
            "Tools > AnkiGit > Settings first."
        )
        return

    if mw is None or mw.col is None:
        QMessageBox.critical(mw, "AnkiGit", "No collection is open.")
        return

    repo_path = Path(config.repo_path)
    if not (repo_path / ".git").exists():
        QMessageBox.warning(
            mw, "AnkiGit",
            "No Git repository found. Take a snapshot first."
        )
        return

    def get_diff_with_progress(col):
        report = compute_import_diff(
            col, repo_path,
            progress_callback=lambda text: mw.taskman.run_on_main(
                lambda: mw.progress.update(label=text)
            )
        )
        if not report.has_changes:
            return report, None

        mw.taskman.run_on_main(
            lambda: mw.progress.update(label="Preparing preview...")
        )
        from anki_git.ui.diff import report_to_diff_data
        ui_data = report_to_diff_data(report)
        return report, ui_data

    def on_diff_done(result_tuple):
        report, ui_data = result_tuple
        if not report or not report.has_changes:
            QMessageBox.information(
                mw, "AnkiGit",
                "No changes detected. Nothing to import."
            )
            return

        diff_dialog = DiffDialog(ui_data, mw)
        if not diff_dialog.exec():
            return

        def do_import(col):
            col_path = Path(col.path)
            backup_path = (
                repo_path / ".ki" / "backups"
                / f"pre-import-{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}.anki2"
            )
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
                QMessageBox.critical(
                    mw, "AnkiGit", f"Import failed: {result.error}"
                )
                return

            msg = (
                f"Import complete.\n"
                f"Notes updated: {result.notes_updated}\n"
                f"Notes created: {result.notes_created}\n"
                f"Notetypes updated: {result.notetypes_updated}\n"
                f"Notetypes created: {result.notetypes_created}"
            )
            if result.warnings:
                _logger.warning(
                    "Import warnings: %s", result.warnings
                )
                msg += "\nWarnings:\n" + "\n".join(result.warnings[:5])
            if result.errors:
                _logger.error("Import errors: %s", result.errors)
                msg += "\nErrors:\n" + "\n".join(result.errors[:5])
            QMessageBox.information(mw, "AnkiGit Import", msg)
            mw.reset()

        def on_import_failed(e):
            _logger.exception("Import operation failed")
            QMessageBox.critical(
                mw, "AnkiGit", f"Import failed: {e}"
            )

        QueryOp(
            parent=mw,
            op=do_import,
            success=on_import_done,
        ).failure(on_import_failed).with_progress(
            "Pulling from Repo..."
        ).run_in_background()

    def on_diff_failed(e):
        _logger.exception("Failed to compute import diff")
        QMessageBox.critical(
            mw, "AnkiGit", f"Failed to compute diff: {e}"
        )

    QueryOp(
        parent=mw,
        op=get_diff_with_progress,
        success=on_diff_done,
    ).failure(on_diff_failed).with_progress(
        "Reviewing Changes..."
    ).run_in_background()


def history_action() -> None:
    from aqt import mw
    from aqt.qt import QMessageBox
    from anki_git.ui import HistoryDialog

    config = load_config()
    if not config.repo_path:
        QMessageBox.warning(
            mw, "AnkiGit",
            "Please set a repository path in "
            "Tools > AnkiGit > Settings first."
        )
        return
    repo_path = Path(config.repo_path)
    if not (repo_path / ".git").exists():
        QMessageBox.warning(
            mw, "AnkiGit",
            "No Git repository found. Take a snapshot first."
        )
        return

    dialog = HistoryDialog(repo_path, mw)
    dialog.exec()


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

    sync_act = QAction("Sync", mw)
    sync_act.triggered.connect(sync_action)
    parent_menu.addAction(sync_act)

    snapshot_act = QAction("Export to Repo (Snapshot)", mw)
    snapshot_act.triggered.connect(snapshot_action)
    parent_menu.addAction(snapshot_act)

    import_act = QAction("Import from Repo (Pull)", mw)
    import_act.triggered.connect(import_action)
    parent_menu.addAction(import_act)

    parent_menu.addSeparator()

    history_act = QAction("View History", mw)
    history_act.triggered.connect(history_action)
    parent_menu.addAction(history_act)

    settings_act = QAction("Settings...", mw)
    settings_act.triggered.connect(settings_action)
    parent_menu.addAction(settings_act)

    if parent_menu not in (a.menu() for a in mw.form.menubar.actions()):
        mw.form.menubar.addMenu(parent_menu)


_menu_shown = False


def _run_background_sync(config: KiSyncConfig) -> None:
    """Run sync silently with no user dialogs. Only logs errors."""
    from aqt import mw
    from aqt.operations import QueryOp
    from anki_git.engine.sync import sync_collection

    repo_path = Path(config.repo_path)

    def do_sync(col):
        result = sync_collection(
            col, repo_path,
            sync_mode=config.sync_mode,
            conflict_callback=None,
            remote_url=_get_remote_url(repo_path, config.auto_push_after_snapshot),
            media_strategy=config.media_strategy,
        )
        if result.error:
            _logger.error("Background sync failed: %s", result.error)
        else:
            _logger.info(
                "Background sync: %d notes exported, %d notes imported",
                result.notes_exported, result.notes_imported,
            )
        return result

    QueryOp(
        parent=mw,
        op=do_sync,
        success=lambda _: None,
    ).run_in_background()


def _run_background_export(config: KiSyncConfig) -> None:
    """Run exporter silently with no user dialogs. Only logs errors."""
    from aqt import mw
    from aqt.operations import QueryOp
    from anki_git.engine.exporter import export_collection

    repo_path = Path(config.repo_path)

    def do_export(col):
        result = export_collection(
            col, repo_path,
            remote_url=_get_remote_url(repo_path, config.auto_push_after_snapshot),
            media_strategy=config.media_strategy,
        )
        if result.error:
            _logger.error("Background export failed: %s", result.error)
        else:
            _logger.info(
                "Background export: %d notes changed",
                result.notes_changed,
            )
        return result

    QueryOp(
        parent=mw,
        op=do_export,
        success=lambda _: None,
    ).run_in_background()


def on_profile_open() -> None:
    global _menu_shown
    if not _menu_shown:
        show_menu()
        _menu_shown = True
    config = load_config()
    if config.auto_sync_on_startup and config.repo_path:
        if config.background_mode:
            _run_background_sync(config)
        else:
            sync_action()


def on_profile_close() -> None:
    config = load_config()
    if config.auto_snapshot_on_close and config.repo_path:
        if config.background_mode:
            _run_background_export(config)
        else:
            try:
                from aqt import mw
                if mw is not None and mw.col is not None:
                    repo_path = Path(config.repo_path)
                    mw.progress.start(
                        label="Auto-snapshotting...", immediate=True
                    )
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
            op=lambda col: export_collection(
                col, repo_path,
                media_strategy=config.media_strategy,
            ),
            success=lambda _: None
        ).run_in_background()
    except Exception as e:
        _logger.warning("Debounced export failed: %s", e)


def _on_operation(changes, handler) -> None:
    if changes.note or changes.notetype:
        on_note_change(None)


def init_addon() -> None:
    if _import("aqt") is not None:
        _setup_logging()
    from aqt import gui_hooks
    gui_hooks.profile_did_open.append(on_profile_open)
    gui_hooks.profile_will_close.append(on_profile_close)
    gui_hooks.operation_did_execute.append(_on_operation)
