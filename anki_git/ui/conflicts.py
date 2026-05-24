from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QGroupBox, QMenu,
    QDialogButtonBox,
)

from anki_git.engine.conflict import ConflictReport, ConflictType


class ConflictResolutionDialog(QDialog):
    def __init__(self, report: ConflictReport, parent=None):
        super().__init__(parent)
        self.report = report
        self.resolved_report = report
        self.setWindowTitle("AnkiGit — Conflict Resolution")
        self.setMinimumSize(700, 500)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        if not self.report.has_conflicts:
            no_conflicts = QLabel("No conflicts detected.", self)
            layout.addWidget(no_conflicts)
        else:
            info = QLabel(
                f"{self.report.total} notes need attention. "
                f"{sum(1 for c in self.report.conflicts if c.conflict_type == ConflictType.CONFLICT)} conflicts.",
                self,
            )
            layout.addWidget(info)

            self._table = QTableWidget(self)
            self._table.setColumnCount(3)
            self._table.setHorizontalHeaderLabels(
                ["NID", "Conflict Type", "Action"]
            )
            self._table.horizontalHeader().setStretchLastSection(True)
            self._table.setSelectionBehavior(
                QTableWidget.SelectionBehavior.SelectRows
            )

            conflicts_to_show = [
                c for c in self.report.conflicts
                if c.conflict_type == ConflictType.CONFLICT
            ]
            self._table.setRowCount(len(conflicts_to_show))

            for i, c in enumerate(conflicts_to_show):
                self._table.setItem(
                    i, 0, QTableWidgetItem(str(c.nid))
                )
                self._table.setItem(
                    i, 1, QTableWidgetItem(c.conflict_type.value)
                )

                action_btn = QPushButton("Choose...", self._table)
                action_btn.clicked.connect(
                    lambda _, idx=i: self._show_choice_menu(idx)
                )
                self._table.setCellWidget(i, 2, action_btn)

            self._table.resizeColumnsToContents()
            layout.addWidget(self._table)

            bulk_group = QGroupBox("Bulk Actions", self)
            bulk_layout = QHBoxLayout(bulk_group)
            keep_anki_btn = QPushButton("Keep All Anki", self)
            keep_anki_btn.clicked.connect(
                lambda: self._resolve_all("anki")
            )
            keep_git_btn = QPushButton("Keep All Git", self)
            keep_git_btn.clicked.connect(
                lambda: self._resolve_all("git")
            )
            bulk_layout.addWidget(keep_anki_btn)
            bulk_layout.addWidget(keep_git_btn)
            layout.addWidget(bulk_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _show_choice_menu(self, row: int):
        conflicts_to_show = [
            c for c in self.report.conflicts
            if c.conflict_type == ConflictType.CONFLICT
        ]
        c = conflicts_to_show[row]
        menu = QMenu(self)
        anki_action = menu.addAction("Keep Anki Version")
        git_action = menu.addAction("Keep Git Version")
        chosen = menu.exec(
            self._table.cellWidget(row, 2).mapToGlobal(
                self._table.cellWidget(row, 2).rect().center()
            )
        )
        if chosen == anki_action:
            c.resolution = "anki"
            c.resolved = True
            self._table.cellWidget(row, 2).setText("Anki")
        elif chosen == git_action:
            c.resolution = "git"
            c.resolved = True
            self._table.cellWidget(row, 2).setText("Git")

    def _resolve_all(self, choice: str):
        """Mark all conflicts as resolved with the given choice.

        Does NOT call accept() — lets the user review and click OK.
        """
        for c in self.report.conflicts:
            if c.conflict_type == ConflictType.CONFLICT:
                c.resolution = choice
                c.resolved = True
        # Update the table UI to reflect choices
        for row in range(self._table.rowCount()):
            btn = self._table.cellWidget(row, 2)
            if btn:
                btn.setText("Anki" if choice == "anki" else "Git")
