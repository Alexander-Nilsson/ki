import datetime
import logging
from pathlib import Path

from anki_git.config import KiSyncConfig
from anki_git.engine.exporter import export_collection
from anki_git.engine.git_ops import get_existing_remote_url, open_repo


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

            def handle_conflicts_bg(report):
                def _show():
                    diag = ConflictResolutionDialog(report, mw)
                    diag.exec()
                    return diag.resolved_report
                from anki_git.ui.utils import run_on_main_sync
                return run_on_main_sync(mw, _show)

            return pull_from_repo(
                col, repo_path,
                sync_mode=config.sync_mode,
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

    export_act = QAction("Export to Repo", mw)
    export_act.triggered.connect(snapshot_action)
    parent_menu.addAction(export_act)

    import_act = QAction("Import from Repo", mw)
    import_act.triggered.connect(import_action)
    parent_menu.addAction(import_act)

    settings_act = QAction("Settings...", mw)
    settings_act.triggered.connect(settings_action)
    parent_menu.addAction(settings_act)

    if parent_menu not in (a.menu() for a in mw.form.menubar.actions()):
        mw.form.menubar.addMenu(parent_menu)


_menu_shown = False
_last_sync_status: str = ""


def _get_last_sync_status() -> str:
    """Return a human-readable string about the last sync result."""
    return _last_sync_status




def _run_background_export(config: KiSyncConfig, quick: bool = False) -> None:
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
            quick=quick,
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


def _try_fetch(remote) -> None:
    try:
        remote.fetch()
    except Exception:
        pass


def _fetch_remote_background(repo_path: Path) -> None:
    """Fire-and-forget git fetch from origin in a daemon thread."""
    from anki_git.engine.git_ops import open_repo
    import threading

    repo = open_repo(repo_path)
    if repo is None:
        return
    try:
        remote = repo.remote("origin")
        threading.Thread(
            target=lambda: _try_fetch(remote),
            daemon=True,
        ).start()
    except (ValueError, Exception):
        pass


def _run_startup_import(config: KiSyncConfig) -> None:
    """Show import diff on startup. Let user accept/reject repo changes."""
    from aqt import mw
    from aqt.qt import QMessageBox
    from aqt.operations import QueryOp
    from anki_git.ui import DiffDialog
    from anki_git.engine.diff import compute_import_diff

    repo_path = Path(config.repo_path)

    def do_diff(col):
        _logger.info("Computing startup import diff...")
        report = compute_import_diff(
            col, repo_path,
            progress_callback=lambda text: mw.taskman.run_on_main(
                lambda: mw.progress.update(label=text)
            ),
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
            _logger.info("No repo changes to import on startup")
            return

        diff_dialog = DiffDialog(ui_data, mw)
        if not diff_dialog.exec():
            _logger.info("User discarded startup import changes")
            return

        _logger.info("User accepted startup import, starting import...")

        def do_import(col):
            col_path = Path(col.path)
            backup_path = (
                repo_path / ".ki" / "backups"
                / f"pre-import-{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}.anki2"
            )
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path.write_bytes(col_path.read_bytes())

            from anki_git.engine.importer import pull_from_repo
            result = pull_from_repo(
                col, repo_path,
                sync_mode=config.sync_mode,
            )

            from anki_git.engine.git_ops import (
                get_or_init_repo, stage_files, push_to_remote,
            )
            verify_repo = get_or_init_repo(repo_path)
            meta_path = repo_path / ".ki" / "meta.json"
            if meta_path.exists():
                stage_files(verify_repo, [str(meta_path.relative_to(repo_path))])
                num_notes = result.notes_updated + result.notes_created
                num_nt = result.notetypes_updated + result.notetypes_created
                msg_parts = []
                if num_notes:
                    msg_parts.append(f"{num_notes} notes")
                if num_nt:
                    msg_parts.append(f"{num_nt} notetypes")
                detail = ", ".join(msg_parts) if msg_parts else "metadata"
                verify_repo.index.commit(f"Import {detail} from repo")

            remote_url = _get_remote_url(repo_path, config.auto_push_after_snapshot)
            if remote_url:
                push_to_remote(verify_repo, remote_url)

            return result

        def on_import_done(result):
            if result.error:
                QMessageBox.critical(
                    mw, "AnkiGit", f"Import failed: {result.error}"
                )
                return

            parts = []
            if result.notes_updated:
                parts.append(f"Notes updated: {result.notes_updated}")
            if result.notes_created:
                parts.append(f"Notes created: {result.notes_created}")
            if result.notetypes_updated:
                parts.append(f"Notetypes updated: {result.notetypes_updated}")
            if result.notetypes_created:
                parts.append(f"Notetypes created: {result.notetypes_created}")
            if result.warnings:
                parts.append("Warnings: " + "; ".join(result.warnings[:3]))
            msg = "\n".join(parts) if parts else "Import complete."
            QMessageBox.information(mw, "AnkiGit Import", msg)
            mw.reset()

        def on_import_failed(e):
            QMessageBox.critical(mw, "AnkiGit", f"Import failed: {e}")

        QueryOp(
            parent=mw,
            op=do_import,
            success=on_import_done,
        ).failure(on_import_failed).with_progress(
            "Importing from repo..."
        ).run_in_background()

    def on_diff_failed(e):
        QMessageBox.critical(mw, "AnkiGit", f"Failed to compute diff: {e}")

    QueryOp(
        parent=mw,
        op=do_diff,
        success=on_diff_done,
    ).failure(on_diff_failed).with_progress(
        "Checking for changes..."
    ).run_in_background()


def on_profile_open() -> None:
    global _menu_shown
    if not _menu_shown:
        show_menu()
        _menu_shown = True
    config = load_config()
    if config.auto_sync_on_startup and config.repo_path:
        from aqt import mw
        if mw and mw.col:
            repo_path = Path(config.repo_path)
            if not (repo_path / ".git").exists():
                return
            _fetch_remote_background(repo_path)
            from anki_git.engine.checksums import quick_has_changes
            try:
                result = quick_has_changes(mw.col, repo_path)
                if result is False or result is None:
                    _logger.info(
                        "No changes or no baseline, skipping startup import"
                    )
                    return
            except Exception:
                pass
        _run_startup_import(config)


def on_profile_close() -> None:
    config = load_config()
    if config.auto_snapshot_on_close and config.repo_path:
        from aqt import mw
        if mw is None or mw.col is None:
            return
        repo_path = Path(config.repo_path)
        if not (repo_path / ".git").exists():
            return

        from anki_git.engine.checksums import quick_has_changes
        try:
            result = quick_has_changes(mw.col, repo_path)
            if result is False:
                _logger.info("No changes detected, skipping auto-export")
                return
        except Exception:
            pass

        remote_url = _get_remote_url(repo_path, config.auto_push_after_snapshot)

        if config.background_mode:
            _run_background_export(config, quick=True)
        else:
            try:
                mw.progress.start(
                    label="Auto-syncing changes...", immediate=True
                )
                try:
                    export_collection(
                        mw.col, repo_path,
                        remote_url=remote_url,
                        media_strategy=config.media_strategy,
                        progress_callback=lambda text: (
                            mw.progress.update(label=text),
                            mw.app.processEvents()
                        ) and None,
                        quick=True,
                    )
                finally:
                    mw.progress.finish()
            except Exception as e:
                _logger.warning("Auto-snapshot on close failed: %s", e)


def init_addon() -> None:
    if _import("aqt") is not None:
        _setup_logging()
    from aqt import gui_hooks
    gui_hooks.profile_did_open.append(on_profile_open)
    gui_hooks.profile_will_close.append(on_profile_close)
