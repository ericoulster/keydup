"""Dark theme: Fusion style + QPalette + a small app stylesheet.

Deliberately no third-party theme package (pyqtdarktheme is unmaintained)
and deliberately no QSS on QSlider - superqt's range slider paints itself
and heavy slider QSS breaks it."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from keydup.paths import resources_dir

ACCENT = QColor("#7c5cff")

_DARK = {
    QPalette.Window: "#1e1f24",
    QPalette.WindowText: "#e4e4e8",
    QPalette.Base: "#17181c",
    QPalette.AlternateBase: "#1c1d22",
    QPalette.Text: "#e4e4e8",
    QPalette.Button: "#26272e",
    QPalette.ButtonText: "#e4e4e8",
    QPalette.ToolTipBase: "#26272e",
    QPalette.ToolTipText: "#e4e4e8",
    QPalette.PlaceholderText: "#6b6c75",
    QPalette.BrightText: "#ff5c7a",
}


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in _DARK.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.Highlight, ACCENT)
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#5a5b63"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#5a5b63"))
    app.setPalette(palette)

    qss = resources_dir() / "keydup.qss"
    if qss.exists():
        app.setStyleSheet(qss.read_text())
