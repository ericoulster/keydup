"""Segmented key-over-time strip for the playing track, shown under the
waveform when a track modulates. Blocks are colored by wheel hue; hover
shows the key and time range; click seeks."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from keydup.notation import get_formatter, saved_notation


def key_hue_color(key: str) -> QColor:
    """Hue mapping matching the Camelot wheel. Minor (A) and major (B)
    share a hue but differ in brightness so a relative-key change (the
    most common modulation) is visible, not just two identical greens."""
    try:
        number = int(key[:-1])
    except (ValueError, IndexError):
        return QColor("#444450")
    hue = ((number - 1) * 30 + 210) % 360
    if key.endswith("A"):       # minor: darker, less saturated
        return QColor.fromHsv(hue, 120, 140)
    return QColor.fromHsv(hue, 165, 205)  # major: brighter


def _mmss(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


class KeyTimeline(QWidget):
    seek_fraction = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self._segments: list = []
        self._duration = 0.0
        self.key_formatter = get_formatter(saved_notation())

    def set_key_formatter(self, formatter) -> None:
        self.key_formatter = formatter
        self.update()

    def set_segments(self, segments: list, duration: float) -> None:
        self._segments = segments or []
        self._duration = duration or (segments[-1]["end_s"] if segments else 0.0)
        self.update()

    def clear(self) -> None:
        self.set_segments([], 0.0)

    def has_segments(self) -> bool:
        return len(self._segments) > 1

    def paintEvent(self, event) -> None:
        if not self._segments or self._duration <= 0:
            return
        painter = QPainter(self)
        width, height = self.width(), self.height()
        bg = self.palette().window().color()
        font = painter.font()
        font.setPointSizeF(max(7.0, height * 0.55))
        painter.setFont(font)
        for seg in self._segments:
            x0 = int(seg["start_s"] / self._duration * width)
            x1 = int(seg["end_s"] / self._duration * width)
            rect_w = max(1, x1 - x0)
            painter.fillRect(x0, 0, rect_w, height, key_hue_color(seg["key"]))
            painter.setPen(QColor(bg))
            painter.drawLine(x0, 0, x0, height)
            label = self.key_formatter(seg["key"])
            if rect_w > 28:
                painter.setPen(QColor("#ffffff"))
                painter.drawText(x0 + 4, int(height * 0.75), label)

    def _segment_at(self, x: float):
        if not self._segments or self._duration <= 0 or self.width() <= 0:
            return None
        t = x / self.width() * self._duration
        for seg in self._segments:
            if seg["start_s"] <= t <= seg["end_s"]:
                return seg
        return None

    def mouseMoveEvent(self, event) -> None:
        seg = self._segment_at(event.position().x())
        if seg is not None:
            self.setToolTip(
                f"{self.key_formatter(seg['key'])} · "
                f"{_mmss(seg['start_s'])}-{_mmss(seg['end_s'])}"
            )
        else:
            self.setToolTip("")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.width() > 0:
            self.seek_fraction.emit(
                min(1.0, max(0.0, event.position().x() / self.width()))
            )
