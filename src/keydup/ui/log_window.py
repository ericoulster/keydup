"""Read-only viewer for captured stdout/stderr. Hidden by default;
opened from View > Show Log."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from keydup.logcapture import LogBuffer


class LogWindow(QWidget):
    closed = Signal()

    def __init__(self, buffer: LogBuffer, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.Window)
        self.setWindowTitle("key'd up - log")
        self.resize(760, 420)

        self.view = QPlainTextEdit(self)
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(5000)
        font = QFont("monospace")
        font.setStyleHint(QFont.Monospace)
        self.view.setFont(font)
        self.view.setPlainText(buffer.snapshot())
        self.view.moveCursor(QTextCursor.End)

        clear = QPushButton("Clear", self)
        clear.clicked.connect(self.view.clear)
        controls = QHBoxLayout()
        controls.addStretch(1)
        controls.addWidget(clear)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view, 1)
        layout.addLayout(controls)

        buffer.appended.connect(self._append)

    def _append(self, text: str) -> None:
        at_bottom = self.view.verticalScrollBar().value() == (
            self.view.verticalScrollBar().maximum()
        )
        self.view.moveCursor(QTextCursor.End)
        self.view.insertPlainText(text)
        if at_bottom:
            self.view.moveCursor(QTextCursor.End)

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)
