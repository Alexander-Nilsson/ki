"""Diff review dialog for git-style change review."""

import difflib
import logging
from typing import List, Dict, Any, Optional

from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QTextBrowser,
    QSizePolicy,
    Qt,
    QSize,
)
from aqt import mw

_logger = logging.getLogger("anki_git")


def get_token_diff(old_str: str, new_str: str):
    """Perform token-level diffing using SequenceMatcher.
    Limit input length to avoid O(N^3) performance issues on very long lines.
    """
    # If lines are extremely long, token diff is likely useless and very slow
    MAX_LINE_LEN = 5000
    if len(old_str) > MAX_LINE_LEN or len(new_str) > MAX_LINE_LEN:
        return (
            old_str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
            new_str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

    sm = difflib.SequenceMatcher(None, old_str, new_str)
    res_old = []
    res_new = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        o_val = old_str[i1:i2].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        n_val = new_str[j1:j2].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if tag == 'equal':
            res_old.append(o_val)
            res_new.append(n_val)
        elif tag == 'replace':
            res_old.append(f'<span class="highlight-del">{o_val}</span>')
            res_new.append(f'<span class="highlight-add">{n_val}</span>')
        elif tag == 'delete':
            res_old.append(f'<span class="highlight-del">{o_val}</span>')
        elif tag == 'insert':
            res_new.append(f'<span class="highlight-add">{n_val}</span>')
    return "".join(res_old), "".join(res_new)


def format_diff_line(prefix: str, content: str, line_no: str, cls: str, is_html: bool = False) -> str:
    if not is_html:
        content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""
    <tr>
        <td class="gutter">{line_no}</td>
        <td class="prefix">{prefix}</td>
        <td class="content {cls}">{content}</td>
    </tr>
    """

class SidebarItemWidget(QWidget):
    def __init__(self, item_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.data = item_data
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        status = self.data.get("status", "modified")
        dot_color = {"modified": "#888", "added": "#2ecc71", "deleted": "#e74c3c"}.get(status, "#888")
        
        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {dot_color}; font-size: 14px;")
        layout.addWidget(self.dot)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        id_label = QLabel(str(self.data.get("id", "")))
        id_label.setObjectName("idLabel")
        text_layout.addWidget(id_label)

        sub_text = ""
        if self.data["type"] == "note":
            sub_text = self.data.get("notetype", "")
        else:
            sub_text = self.data.get("notetype", "") # For templates this is 'front'/'back'/'css'

        sub_label = QLabel(sub_text)
        sub_label.setObjectName("subLabel")
        text_layout.addWidget(sub_label)
        
        layout.addLayout(text_layout)
        layout.addStretch()


def report_to_diff_data(report) -> List[Dict[str, Any]]:
    """Convert engine DiffReport to the structure expected by DiffDialog."""
    data = []
    
    # If there are thousands of notes, we might want to cap it for the UI
    # but for now let's just make sure individual notes don't hang.
    MAX_FIELD_LEN = 20000 

    for nd in report.note_diffs:
        fields = []
        for fd in nd.field_diffs:
            old_val = fd.old_value
            new_val = fd.new_value
            
            # If field is too large, diffing it is extremely slow and likely unreadable
            if len(old_val) > MAX_FIELD_LEN or len(new_val) > MAX_FIELD_LEN:
                hunks = [{
                    "removed": "(Field too large to diff - see raw file)" if old_val else "",
                    "added": "(Field too large to diff - see raw file)" if new_val else "",
                    "context_before": "",
                    "context_after": ""
                }]
            else:
                # We use SequenceMatcher to find hunks for the UI
                s = difflib.SequenceMatcher(None, old_val.splitlines(), new_val.splitlines())
                hunks = []
                for tag, i1, i2, j1, j2 in s.get_opcodes():
                    if tag == 'equal':
                        continue
                    hunks.append({
                        "removed": "\n".join(old_val.splitlines()[i1:i2]),
                        "added": "\n".join(new_val.splitlines()[j1:j2]),
                        "context_before": "\n".join(old_val.splitlines()[max(0, i1-2):i1]),
                        "context_after": "\n".join(old_val.splitlines()[i2:i2+2])
                    })
            fields.append({"name": fd.field_name, "hunks": hunks})
        
        data.append({
            "type": "note",
            "status": nd.change_type,
            "id": str(nd.nid),
            "notetype": nd.notetype,
            "deck": nd.deck,
            "fields": fields
        })

    for ntd in report.notetype_diffs:
        fields = []
        if ntd.fields_diff:
            fields.append({
                "name": "YAML",
                "hunks": [{"removed": "", "added": ntd.fields_diff, "context_before": "", "context_after": ""}]
            })
        if ntd.css_diff:
            fields.append({
                "name": "CSS",
                "hunks": [{"removed": "", "added": ntd.css_diff, "context_before": "", "context_after": ""}]
            })
        data.append({
            "type": "template",
            "status": ntd.change_type,
            "id": ntd.name,
            "notetype": "yaml/css",
            "fields": fields
        })
    return data


class DiffDialog(QDialog):
    def __init__(self, diff_data: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.diff_data = diff_data
        self.current_index = 0
        
        self.setWindowTitle("Review Changes")
        self.resize(1000, 700)
        self._setup_ui()
        self._apply_style()
        
        if self.diff_data:
            self._load_item(0)

    @classmethod
    def from_report(cls, report, parent=None):
        return cls(report_to_diff_data(report), parent)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        self.toolbar = QFrame()
        self.toolbar.setObjectName("toolbar")
        self.toolbar.setFixedHeight(40)
        toolbar_layout = QHBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(15, 0, 15, 0)
        
        total_count = len(self.diff_data)
        added = sum(1 for x in self.diff_data if x["status"] == "added")
        modified = sum(1 for x in self.diff_data if x["status"] == "modified")
        deleted = sum(1 for x in self.diff_data if x["status"] == "deleted")
        
        stats_label = QLabel(f"{total_count} items")
        stats_label.setObjectName("statsLabel")
        toolbar_layout.addWidget(stats_label)
        
        def add_dot_stat(color, count):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; margin-left: 10px;")
            toolbar_layout.addWidget(dot)
            toolbar_layout.addWidget(QLabel(str(count)))

        add_dot_stat("#888", modified)
        add_dot_stat("#2ecc71", added)
        add_dot_stat("#e74c3c", deleted)
        
        toolbar_layout.addStretch()
        
        self.discard_btn = QPushButton("Discard")
        self.discard_btn.setObjectName("discardBtn")
        self.discard_btn.clicked.connect(self.reject)
        toolbar_layout.addWidget(self.discard_btn)
        
        self.commit_btn = QPushButton("Commit")
        self.commit_btn.setObjectName("commitBtn")
        self.commit_btn.clicked.connect(self.accept)
        toolbar_layout.addWidget(self.commit_btn)
        
        main_layout.addWidget(self.toolbar)

        # Main Content (Sidebar + Diff)
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(200)
        self.sidebar.currentRowChanged.connect(self._load_item)
        self._populate_sidebar()
        content_layout.addWidget(self.sidebar)
        
        # Border
        border = QFrame()
        border.setFixedWidth(1)
        border.setObjectName("panelBorder")
        content_layout.addWidget(border)
        
        # Main Diff Panel
        diff_panel = QWidget()
        diff_panel_layout = QVBoxLayout(diff_panel)
        diff_panel_layout.setContentsMargins(0, 0, 0, 0)
        diff_panel_layout.setSpacing(0)
        
        # Diff Header
        self.diff_header = QFrame()
        self.diff_header.setObjectName("diffHeader")
        self.diff_header.setFixedHeight(60)
        header_layout = QHBoxLayout(self.diff_header)
        header_layout.setContentsMargins(20, 10, 20, 10)
        
        title_layout = QVBoxLayout()
        self.header_title = QLabel("Note ID")
        self.header_title.setObjectName("headerTitle")
        self.header_subtitle = QLabel("Deck Path")
        self.header_subtitle.setObjectName("headerSubtitle")
        title_layout.addWidget(self.header_title)
        title_layout.addWidget(self.header_subtitle)
        header_layout.addLayout(title_layout)
        
        header_layout.addStretch()
        
        self.change_counts = QLabel("+0 / -0")
        self.change_counts.setObjectName("changeCounts")
        header_layout.addWidget(self.change_counts)
        
        diff_panel_layout.addWidget(self.diff_header)
        
        # Diff Scroll Area
        self.diff_browser = QTextBrowser()
        self.diff_browser.setObjectName("diffBrowser")
        self.diff_browser.setOpenExternalLinks(False)
        diff_panel_layout.addWidget(self.diff_browser)
        
        content_layout.addWidget(diff_panel)
        main_layout.addWidget(content_widget, 1)

        # Footer
        self.footer = QFrame()
        self.footer.setObjectName("footer")
        self.footer.setFixedHeight(40)
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(15, 0, 15, 0)
        
        self.counter_label = QLabel("0 of 0 changes")
        footer_layout.addWidget(self.counter_label)
        
        footer_layout.addStretch()
        
        self.prev_btn = QPushButton("Prev")
        self.prev_btn.clicked.connect(self._prev_item)
        footer_layout.addWidget(self.prev_btn)
        
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self._next_item)
        footer_layout.addWidget(self.next_btn)
        
        main_layout.addWidget(self.footer)

    def _apply_style(self):
        is_dark = mw.pm.night_mode() if mw else False
        bg_color = "#1a1a1a" if is_dark else "#ffffff"
        text_color = "#ffffff" if is_dark else "#1a1a1a"
        border_color = "#333333" if is_dark else "#e0e0e0"
        muted_color = "#888888"
        active_bg = "#2a2a2a" if is_dark else "#f5f5f5"
        
        qss = f"""
            QDialog {{ background-color: {bg_color}; color: {text_color}; }}
            #toolbar {{ border-bottom: 1px solid {border_color}; background-color: {bg_color}; }}
            #footer {{ border-top: 1px solid {border_color}; background-color: {bg_color}; }}
            #sidebar {{ border: none; background-color: {bg_color}; outline: none; }}
            #sidebar::item {{ border-bottom: 1px solid {border_color}; }}
            #sidebar::item:selected {{ 
                background-color: {active_bg}; 
                border-left: 2px solid {text_color};
            }}
            #panelBorder {{ background-color: {border_color}; }}
            #diffHeader {{ border-bottom: 1px solid {border_color}; background-color: {bg_color}; }}
            #headerTitle {{ font-weight: bold; font-size: 14px; color: {text_color}; }}
            #headerSubtitle {{ color: {muted_color}; font-size: 11px; }}
            #changeCounts {{ font-weight: bold; }}
            #diffBrowser {{ border: none; background-color: {bg_color}; }}
            #statsLabel {{ font-weight: bold; }}
            #discardBtn {{ background-color: transparent; border: 1px solid {border_color}; padding: 4px 12px; border-radius: 4px; color: {text_color}; }}
            #commitBtn {{ background-color: #3498db; color: white; border: none; padding: 4px 12px; border-radius: 4px; font-weight: bold; }}
            #commitBtn:hover {{ background-color: #2980b9; }}
            
            /* Sidebar section labels */
            .sectionLabel {{ color: {muted_color}; font-size: 10px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; padding: 10px 12px 5px 12px; }}
            
            /* Labels in Sidebar Widgets */
            #idLabel {{ color: {text_color}; font-weight: 500; }}
            #subLabel {{ color: {muted_color}; font-size: 10px; }}
        """
        self.setStyleSheet(qss)
        
        # Style for QTextBrowser HTML
        diff_qss = f"""
            body {{ font-family: monospace; font-size: 12px; color: {text_color}; background-color: {bg_color}; margin: 0; }}
            table {{ border-collapse: collapse; width: 100%; }}
            .gutter {{ width: 40px; color: {muted_color}; text-align: right; padding-right: 10px; border-right: 1px solid {border_color}; -webkit-user-select: none; }}
            .prefix {{ width: 20px; text-align: center; font-weight: bold; }}
            .content {{ white-space: pre-wrap; padding-left: 5px; }}
            .line-add-bg {{ background-color: rgba(59, 109, 17, 0.18); color: #3B6D11; }}
            .line-del-bg {{ background-color: rgba(162, 45, 45, 0.18); color: #c0392b; }}
            .highlight-add {{ background-color: rgba(59, 109, 17, 0.45); }}
            .highlight-del {{ background-color: rgba(162, 45, 45, 0.45); }}
            .field-label {{ background-color: {active_bg}; color: {muted_color}; font-size: 10px; font-weight: bold; padding: 4px 10px; margin-top: 10px; text-transform: uppercase; }}
        """
        self.diff_browser.document().setDefaultStyleSheet(diff_qss)

    def _populate_sidebar(self):
        _logger.info("Populating DiffDialog sidebar with %d items", len(self.diff_data))
        notes = [d for d in self.diff_data if d["type"] == "note"]
        templates = [d for d in self.diff_data if d["type"] == "template"]
        
        self.sidebar_map = [] # To map row index to diff_data index
        
        # Performance optimization: if there are thousands of changes, 
        # setItemWidget for all of them will hang the UI.
        # We limit the number of widgets for now.
        MAX_WIDGETS = 500
        total_selectable = 0

        if notes:
            header = QListWidgetItem("NOTE CONTENT")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setSizeHint(QSize(0, 30))
            self.sidebar.addItem(header)
            lbl = QLabel("  NOTE CONTENT")
            lbl.setProperty("class", "sectionLabel")
            self.sidebar.setItemWidget(header, lbl)
            
            for item_idx, item in enumerate(self.diff_data):
                if item["type"] != "note":
                    continue
                
                self.sidebar_map.append(item_idx)
                li = QListWidgetItem()
                li.setSizeHint(QSize(0, 50))
                # Store the data index directly in the item
                li.setData(Qt.ItemDataRole.UserRole, total_selectable)
                li.setData(Qt.ItemDataRole.UserRole + 1, item_idx)
                
                self.sidebar.addItem(li)
                if total_selectable < MAX_WIDGETS:
                    self.sidebar.setItemWidget(li, SidebarItemWidget(item))
                else:
                    li.setText(f"Note {item['id']}") # Fallback for performance
                
                total_selectable += 1
                
        if templates:
            if notes:
                # Spacer/Divider
                divider = QListWidgetItem()
                divider.setFlags(Qt.ItemFlag.NoItemFlags)
                divider.setSizeHint(QSize(0, 1))
                self.sidebar.addItem(divider)
            
            header = QListWidgetItem("TEMPLATES")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setSizeHint(QSize(0, 30))
            self.sidebar.addItem(header)
            lbl = QLabel("  TEMPLATES")
            lbl.setProperty("class", "sectionLabel")
            self.sidebar.setItemWidget(header, lbl)
            
            for item_idx, item in enumerate(self.diff_data):
                if item["type"] != "template":
                    continue
                
                self.sidebar_map.append(item_idx)
                li = QListWidgetItem()
                li.setSizeHint(QSize(0, 50))
                li.setData(Qt.ItemDataRole.UserRole, total_selectable)
                li.setData(Qt.ItemDataRole.UserRole + 1, item_idx)

                self.sidebar.addItem(li)
                if total_selectable < MAX_WIDGETS:
                    self.sidebar.setItemWidget(li, SidebarItemWidget(item))
                else:
                    li.setText(item['id'])
                
                total_selectable += 1
        
        _logger.info("Sidebar population complete")

    def _load_item(self, sidebar_row):
        item = self.sidebar.item(sidebar_row)
        if not item or not (item.flags() & Qt.ItemFlag.ItemIsSelectable):
            return

        # Use stored data instead of searching (O(1) instead of O(N))
        selectable_idx = item.data(Qt.ItemDataRole.UserRole)
        data_idx = item.data(Qt.ItemDataRole.UserRole + 1)
        
        if data_idx is None:
            return
            
        self.current_index = selectable_idx
        data = self.diff_data[data_idx]
        
        _logger.debug("Loading item %d (id: %s)", data_idx, data["id"])
        
        self.header_title.setText(str(data["id"]))
        self.header_subtitle.setText(data.get("deck") or data.get("notetype") or "")
        
        self._render_diff(data)
        
        self.counter_label.setText(f"{self.current_index + 1} of {len(self.diff_data)} changes")
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < len(self.diff_data) - 1)

    def _render_diff(self, data):
        html = ["<body><table>"]
        total_added = 0
        total_removed = 0
        
        for field in data.get("fields", []):
            html.append(f'<tr><td colspan="3" class="field-label">{field["name"].upper()}</td></tr>')
            
            old_ln = 1
            new_ln = 1
            
            for hunk in field.get("hunks", []):
                # Context before
                for line in hunk.get("context_before", "").splitlines():
                    html.append(format_diff_line(" ", line, f"{old_ln}", ""))
                    old_ln += 1
                    new_ln += 1
                
                removed_lines = hunk.get("removed", "").splitlines()
                added_lines = hunk.get("added", "").splitlines()
                
                max_lines = max(len(removed_lines), len(added_lines))
                for i in range(max_lines):
                    if i < len(removed_lines) and i < len(added_lines):
                        old_t, new_t = get_token_diff(removed_lines[i], added_lines[i])
                        html.append(format_diff_line("-", old_t, f"{old_ln}", "line-del-bg", is_html=True))
                        html.append(format_diff_line("+", new_t, f"{new_ln}", "line-add-bg", is_html=True))
                        old_ln += 1
                        new_ln += 1
                        total_removed += 1
                        total_added += 1
                    elif i < len(removed_lines):
                        html.append(format_diff_line("-", removed_lines[i], f"{old_ln}", "line-del-bg"))
                        old_ln += 1
                        total_removed += 1
                    elif i < len(added_lines):
                        html.append(format_diff_line("+", added_lines[i], f"{new_ln}", "line-add-bg"))
                        new_ln += 1
                        total_added += 1
                
                # Context after
                for line in hunk.get("context_after", "").splitlines():
                    html.append(format_diff_line(" ", line, f"{old_ln}", ""))
                    old_ln += 1
                    new_ln += 1
        
        html.append("</table></body>")
        self.diff_browser.setHtml("".join(html))
        self.change_counts.setText(f"+{total_added} / -{total_removed}")
        self.change_counts.setStyleSheet(f"color: {'#3B6D11' if total_added > 0 else '#888'};")

    def _prev_item(self):
        if self.current_index > 0:
            self._select_selectable_item(self.current_index - 1)

    def _next_item(self):
        if self.current_index < len(self.diff_data) - 1:
            self._select_selectable_item(self.current_index + 1)

    def _select_selectable_item(self, target_data_idx):
        current_selectable_idx = 0
        for i in range(self.sidebar.count()):
            li = self.sidebar.item(i)
            if li.flags() & Qt.ItemFlag.ItemIsSelectable:
                if current_selectable_idx == target_data_idx:
                    self.sidebar.setCurrentRow(i)
                    return
                current_selectable_idx += 1
