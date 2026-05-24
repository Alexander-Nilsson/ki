import datetime
import logging
from pathlib import Path
from typing import List

from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextBrowser, QFrame,
    Qt,
)
from aqt import mw

from anki_git.engine.git_ops import get_commit_log, get_commit_diff

_logger = logging.getLogger("anki_git")


class HistoryDialog(QDialog):
    def __init__(self, repo_path: Path, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.commits: List[dict] = []
        self.setWindowTitle("AnkiGit — Commit History")
        self.resize(1000, 650)
        self._setup_ui()
        self._apply_style()
        self._load_history()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("toolbar2")
        toolbar.setFixedHeight(40)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(15, 0, 15, 0)

        title = QLabel("Commit History")
        title.setObjectName("toolbarTitle")
        tb_layout.addWidget(title)
        tb_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setObjectName("toolbarClose")
        close_btn.clicked.connect(self.accept)
        tb_layout.addWidget(close_btn)

        layout.addWidget(toolbar)

        # Content
        content = QFrame()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Commit list
        self.commit_list = QListWidget()
        self.commit_list.setObjectName("commitList")
        self.commit_list.setFixedWidth(320)
        self.commit_list.currentRowChanged.connect(self._on_commit_selected)
        content_layout.addWidget(self.commit_list)

        # Border
        border = QFrame()
        border.setFixedWidth(1)
        border.setObjectName("panelBorder")
        content_layout.addWidget(border)

        # Diff view
        self.diff_view = QTextBrowser()
        self.diff_view.setObjectName("diffView")
        self.diff_view.setOpenExternalLinks(False)
        content_layout.addWidget(self.diff_view)

        layout.addWidget(content, 1)

    def _apply_style(self):
        is_dark = mw.pm.night_mode() if mw else False
        bg = "#1a1a1a" if is_dark else "#ffffff"
        text = "#ffffff" if is_dark else "#1a1a1a"
        border = "#333333" if is_dark else "#e0e0e0"
        active_bg = "#2a2a2a" if is_dark else "#f5f5f5"

        self.setStyleSheet(f"""
            QDialog {{ background-color: {bg}; color: {text}; }}
            #toolbar2 {{ border-bottom: 1px solid {border};
                         background-color: {bg}; }}
            #toolbarTitle {{ font-weight: bold; font-size: 13px; color: {text}; }}
            #toolbarClose {{ background: transparent; border: 1px solid {border};
                            padding: 4px 12px; border-radius: 4px; color: {text}; }}
            #commitList {{ border: none; background-color: {bg};
                          outline: none; font-size: 11px; }}
            #commitList::item {{ padding: 8px 10px;
                                border-bottom: 1px solid {border}; }}
            #commitList::item:selected {{
                background-color: {active_bg};
                border-left: 2px solid #3498db;
            }}
            #panelBorder {{ background-color: {border}; }}
            #diffView {{ border: none; background-color: {bg};
                         font-family: monospace; font-size: 11px; }}
        """)

    def _load_history(self):
        from anki_git.engine.git_ops import open_repo
        repo = open_repo(self.repo_path)
        if repo is None:
            self.diff_view.setPlainText("No git repository found at this path.")
            return

        self.commits = get_commit_log(repo)
        self.commit_list.clear()

        if not self.commits:
            self.commit_list.addItem("No commits yet")
            return

        for c in self.commits:
            ts = datetime.datetime.fromtimestamp(
                c["timestamp"], datetime.timezone.utc
            ).strftime("%Y-%m-%d %H:%M")
            short_msg = c["message"].split("\n")[0]
            n_files = len(c["files_changed"])
            label = (
                f"{c['hexsha']}  {ts}\n"
                f"{short_msg[:60]}\n"
                f"{n_files} file{'s' if n_files != 1 else ''}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, c)
            self.commit_list.addItem(item)

    def _on_commit_selected(self, row: int):
        if row < 0 or row >= len(self.commits):
            return
        c = self.commits[row]
        diff_text = get_commit_diff(
            Path(self.repo_path), c["hexsha"]
        )
        if not diff_text:
            self.diff_view.setPlainText("(no diff content)")
            return

        is_dark = mw.pm.night_mode() if mw else False
        add_color = "#3B6D11" if is_dark else "#22863a"
        del_color = "#c0392b" if is_dark else "#cb2431"
        muted = "#888888"

        escaped = (
            diff_text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        html_lines = ['<html><body style="white-space: pre; font-family: monospace;">']
        for line in escaped.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                html_lines.append(
                    f'<span style="color: {add_color};">{line}</span>\n'
                )
            elif line.startswith("-") and not line.startswith("---"):
                html_lines.append(
                    f'<span style="color: {del_color};">{line}</span>\n'
                )
            elif line.startswith("@@"):
                html_lines.append(
                    f'<span style="color: {muted};">{line}</span>\n'
                )
            else:
                html_lines.append(f"{line}\n")
        html_lines.append("</body></html>")
        self.diff_view.setHtml("".join(html_lines))
