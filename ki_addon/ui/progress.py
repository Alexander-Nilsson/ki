from aqt.qt import QWidget, QLabel, QProgressBar, QVBoxLayout, QDialog


class ProgressWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._label = QLabel("", self)
        self._bar = QProgressBar(self)
        self._bar.setRange(0, 0)
        self._layout.addWidget(self._label)
        self._layout.addWidget(self._bar)
        self.setLayout(self._layout)

    def show_progress(self, text: str) -> None:
        self._label.setText(text)
        self.show()

    def hide_progress(self) -> None:
        self._label.setText("")
        self.hide()


class ProgressDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self._layout = QVBoxLayout(self)
        self._label = QLabel("", self)
        self._bar = QProgressBar(self)
        self._bar.setRange(0, 0)
        self._layout.addWidget(self._label)
        self._layout.addWidget(self._bar)
        self.setLayout(self._layout)

    def set_text(self, text: str) -> None:
        self._label.setText(text)
