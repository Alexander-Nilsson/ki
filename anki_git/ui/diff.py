"""Diff viewer dialog: hierarchical tree view with compact change summaries."""

from typing import Dict, List

from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QTextBrowser,
    QLabel,
    QPushButton,
)

from anki_git.engine.diff import DiffReport, NoteDiff, NotetypeDiff


_DIFF_STYLE = """
body { margin: 4px; font-family: monospace; font-size: 12px; }
.line-add { background-color: #e6ffec; color: #1a7f37; }
.line-del { background-color: #ffebe9; color: #cf222e; }
.line-hunk { color: #0969da; }
.line-meta { color: #656d76; }
.field-label { color: #888; font-size: 11px; margin-top: 6px; }
.header { font-weight: bold; margin-bottom: 2px; }
"""


def _diff_to_html(diff_lines: List[str]) -> str:
    parts = ['<pre style="margin: 0; white-space: pre-wrap;">']
    for line in diff_lines:
        escaped = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        cls = ""
        if line.startswith("+") and not line.startswith("+++"):
            cls = ' class="line-add"'
        elif line.startswith("-") and not line.startswith("---"):
            cls = ' class="line-del"'
        elif line.startswith("@@"):
            cls = ' class="line-hunk"'
        elif line.startswith("---") or line.startswith("+++"):
            cls = ' class="line-meta"'
        parts.append(f'<span{cls}>{escaped}</span>\n')
    parts.append("</pre>")
    return "".join(parts)


def _note_diff_to_html(nd: NoteDiff) -> str:
    header = f"{nd.change_type.upper()} note {nd.nid} &mdash; {nd.deck} ({nd.notetype})"
    parts = [f'<div class="header">{header}</div>']
    if nd.tags_changed:
        old_set = set(nd.old_tags)
        new_set = set(nd.new_tags)
        added = new_set - old_set
        removed = old_set - new_set
        tags = []
        if removed:
            tags.append(f'<span style="color:#cf222e;">-{",".join(sorted(removed))}</span>')
        if added:
            tags.append(f'<span style="color:#1a7f37;">+{",".join(sorted(added))}</span>')
        parts.append("<div>" + " ".join(tags) + "</div>")
    for fd in nd.field_diffs:
        parts.append(f'<div class="field-label"># {fd.field_name}</div>')
        parts.append(_diff_to_html(fd.diff_lines))
    return "".join(parts)


def _notes_diff_to_html(notes: List[NoteDiff]) -> str:
    return "".join(_note_diff_to_html(nd) for nd in notes)


def _notetype_diff_to_html(ntd: NotetypeDiff) -> str:
    parts = [f'<div class="header">{ntd.change_type.upper()} notetype {ntd.name}</div>']
    if ntd.fields_diff:
        parts.append(_diff_to_html(ntd.fields_diff.splitlines()))
    if ntd.css_diff:
        parts.append('<div class="field-label"># css</div>')
        parts.append(_diff_to_html(ntd.css_diff.splitlines()))
    return "".join(parts)


def _count_label(nd: NoteDiff) -> str:
    a, d = nd.added_lines, nd.deleted_lines
    if a == 0 and d == 0:
        return "±0"
    parts = []
    if a:
        parts.append(f"+{a}")
    if d:
        parts.append(f"-{d}")
    return " ".join(parts)


def _deck_count_label(notes: List[NoteDiff]) -> str:
    total_a = sum(nd.added_lines for nd in notes)
    total_d = sum(nd.deleted_lines for nd in notes)
    parts = []
    if total_a:
        parts.append(f"+{total_a}")
    if total_d:
        parts.append(f"-{total_d}")
    return " ".join(parts) if parts else "±0"


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
        self._notetype_items: Dict[str, NotetypeDiff] = {}
        self.setWindowTitle(f"AnkiGit — {title}")
        self.setMinimumSize(800, 400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        summary = QLabel(
            f"<b>{len(self.report.note_diffs)} notes</b>, "
            f"<b>{len(self.report.notetype_diffs)} notetypes</b> changed.",
            self,
        )
        layout.addWidget(summary)

        splitter = QSplitter(self)

        self._tree = QTreeWidget(self)
        self._tree.setMinimumWidth(220)
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(14)
        self._tree.setRootIsDecorated(True)
        self._tree.currentItemChanged.connect(self._on_selection_changed)
        splitter.addWidget(self._tree)

        self._diff_view = QTextBrowser(self)
        self._diff_view.setOpenExternalLinks(False)
        self._diff_view.setStyleSheet(
            "QTextBrowser { font-family: monospace; font-size: 12px; }"
        )
        self._diff_view.document().setDefaultStyleSheet(_DIFF_STYLE)
        splitter.addWidget(self._diff_view)

        splitter.setSizes([250, 550])
        layout.addWidget(splitter, 1)

        self._populate_tree()

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        accept_btn = QPushButton(self._accept_label, self)
        accept_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(accept_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        if self._tree.topLevelItemCount() > 0:
            self._tree.setCurrentItem(self._tree.topLevelItem(0))

    def _populate_tree(self):
        decks: Dict[str, List[NoteDiff]] = {}
        for nd in self.report.note_diffs:
            decks.setdefault(nd.deck, []).append(nd)

        for deck_name in sorted(decks):
            notes = decks[deck_name]
            count = _deck_count_label(notes)
            deck_item = QTreeWidgetItem([f"{deck_name}  ({count})"])
            deck_item.setData(0, 256, ("deck", notes))
            deck_item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)

            for nd in sorted(notes, key=lambda x: x.nid):
                label = f"{nd.nid}  {_count_label(nd)}"
                child = QTreeWidgetItem([label])
                child.setData(0, 256, ("note", nd))
                child.setTextAlignment(0, 0)
                deck_item.addChild(child)

            self._tree.addTopLevelItem(deck_item)

        for ntd in self.report.notetype_diffs:
            prefix = {"modified": "M", "added": "A", "deleted": "D"}.get(ntd.change_type, "?")
            item = QTreeWidgetItem([f"{prefix}  notetype {ntd.name}"])
            item.setData(0, 256, ("notetype", ntd))
            self._tree.addTopLevelItem(item)

    def _on_selection_changed(self, current, previous):
        if current is None:
            self._diff_view.setHtml("")
            return
        kind, data = current.data(0, 256)
        if kind == "note":
            html = _note_diff_to_html(data)
        elif kind == "deck":
            html = _notes_diff_to_html(data)
        else:
            html = _notetype_diff_to_html(data)
        self._diff_view.setHtml(html)
