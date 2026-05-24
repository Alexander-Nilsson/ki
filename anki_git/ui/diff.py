"""Diff viewer dialog: shows field-level changes in a git-diff-style UI."""

from typing import List

from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QTextBrowser,
    QLabel,
    QPushButton,
)

from anki_git.engine.diff import DiffReport, NoteDiff, NotetypeDiff


def _diff_to_html(diff_lines: List[str]) -> str:
    parts = ['<pre style="font-family: monospace; margin: 0; white-space: pre-wrap;">']
    for line in diff_lines:
        escaped = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        if line.startswith("+") and not line.startswith("+++"):
            parts.append(f'<span style="background-color: #e6ffec; color: #1a7f37;">{escaped}</span>\n')
        elif line.startswith("-") and not line.startswith("---"):
            parts.append(f'<span style="background-color: #ffebe9; color: #cf222e;">{escaped}</span>\n')
        elif line.startswith("@@"):
            parts.append(f'<span style="color: #0969da;">{escaped}</span>\n')
        elif line.startswith("---") or line.startswith("+++"):
            parts.append(f'<span style="color: #656d76;">{escaped}</span>\n')
        else:
            parts.append(f"{escaped}\n")
    parts.append("</pre>")
    return "".join(parts)


def _tags_diff_html(old_tags: List[str], new_tags: List[str]) -> str:
    old_set = set(old_tags)
    new_set = set(new_tags)
    if old_set == new_set:
        return ""
    added = new_set - old_set
    removed = old_set - new_set
    parts = ['<div style="margin-top: 8px;"><b>Tags:</b><br>']
    if removed:
        parts.append(f'<span style="color: #cf222e;">- {", ".join(sorted(removed))}</span><br>')
    if added:
        parts.append(f'<span style="color: #1a7f37;">+ {", ".join(sorted(added))}</span><br>')
    parts.append("</div>")
    return "".join(parts)


def _note_diff_to_html(nd: NoteDiff) -> str:
    parts = [
        f"<h3>{nd.change_type.upper()}  note {nd.nid}</h3>",
        f"<p><b>Deck:</b> {nd.deck} &nbsp; <b>Notetype:</b> {nd.notetype}</p>",
    ]
    if nd.tags_changed:
        parts.append(_tags_diff_html(nd.old_tags, nd.new_tags))
    for fd in nd.field_diffs:
        parts.append(f'<div style="margin-top: 12px;"><b>Field: {fd.field_name}</b></div>')
        parts.append(_diff_to_html(fd.diff_lines))
    if not nd.field_diffs and not nd.tags_changed:
        parts.append("<p><i>(no field-level changes)</i></p>")
    return "".join(parts)


def _notetype_diff_to_html(ntd: NotetypeDiff) -> str:
    parts = [f"<h3>{ntd.change_type.upper()}  notetype {ntd.name}</h3>"]
    if ntd.fields_diff:
        parts.append('<div style="margin-top: 8px;"><b>YAML / structure:</b></div>')
        parts.append(_diff_to_html(ntd.fields_diff.splitlines()))
    if ntd.css_diff:
        parts.append('<div style="margin-top: 8px;"><b>CSS:</b></div>')
        parts.append(_diff_to_html(ntd.css_diff.splitlines()))
    return "".join(parts)


class DiffViewDialog(QDialog):
    def __init__(
        self,
        report: DiffReport,
        parent=None,
        title="Review Changes",
        accept_label="Accept & Proceed",
    ):
        super().__init__(parent)
        self.report = report
        self._accept_label = accept_label
        self.setWindowTitle(f"AnkiGit — {title}")
        self.setMinimumSize(900, 600)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        summary = QLabel(
            f"<b>{len(self.report.note_diffs)} notes</b> and "
            f"<b>{len(self.report.notetype_diffs)} notetypes</b> changed.",
            self,
        )
        layout.addWidget(summary)

        splitter = QSplitter(self)

        self._item_list = QListWidget(self)
        self._item_list.setMinimumWidth(280)
        self._item_list.currentRowChanged.connect(self._on_selection_changed)
        splitter.addWidget(self._item_list)

        self._diff_view = QTextBrowser(self)
        self._diff_view.setOpenExternalLinks(False)
        self._diff_view.setStyleSheet(
            "QTextBrowser { font-family: 'monospace'; font-size: 13px; }"
        )
        splitter.addWidget(self._diff_view)

        splitter.setSizes([300, 600])
        layout.addWidget(splitter, 1)

        self._populate_items()

        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All", self)
        select_all_btn.clicked.connect(self.accept)
        deselect_btn = QPushButton("Cancel", self)
        deselect_btn.clicked.connect(self.reject)
        btn_layout.addWidget(select_all_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(deselect_btn)
        layout.addLayout(btn_layout)

        if self._item_list.count() > 0:
            self._item_list.setCurrentRow(0)

    def _populate_items(self):
        for nd in self.report.note_diffs:
            label = f"{'M' if nd.change_type == 'modified' else 'A' if nd.change_type == 'added' else 'D'}  {nd.deck} — {nd.nid}"
            item = QListWidgetItem(label)
            item.setData(256, ("note", nd))
            self._item_list.addItem(item)

        for ntd in self.report.notetype_diffs:
            label = f"{'M' if ntd.change_type == 'modified' else 'A' if ntd.change_type == 'added' else 'D'}  notetype {ntd.name}"
            item = QListWidgetItem(label)
            item.setData(256, ("notetype", ntd))
            self._item_list.addItem(item)

    def _on_selection_changed(self, row: int):
        if row < 0 or row >= self._item_list.count():
            self._diff_view.setHtml("")
            return
        item = self._item_list.item(row)
        kind, data = item.data(256)
        if kind == "note":
            html = _note_diff_to_html(data)
        else:
            html = _notetype_diff_to_html(data)
        self._diff_view.setHtml(html)
