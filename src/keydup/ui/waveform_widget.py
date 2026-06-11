"""Static waveform strip: peaks drawn as a mirrored bar chart, played
portion tinted with the accent color, click (or drag) to seek."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

UNPLAYED = QColor("#4a4b56")
PLAYED = QColor("#7c5cff")
LOADING = QColor("#2e2f38")


class WaveformWidget(QWidget):
    seek_fraction = Signal(float)  # 0.0 - 1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._peaks: np.ndarray | None = None
        self._progress = 0.0
        self._loading = False

    def set_peaks(self, peaks: np.ndarray | None) -> None:
        self._peaks = peaks
        self._loading = False
        self.update()

    def set_loading(self) -> None:
        self._peaks = None
        self._loading = True
        self.update()

    def set_progress(self, fraction: float) -> None:
        fraction = min(1.0, max(0.0, fraction))
        if abs(fraction - self._progress) * self.width() >= 0.5:
            self._progress = fraction
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        width, height = self.width(), self.height()
        mid = height / 2
        if self._peaks is None:
            painter.fillRect(0, int(mid) - 1, width, 2, LOADING)
            if self._loading:
                painter.setPen(QColor("#6b6c75"))
                painter.drawText(self.rect(), Qt.AlignCenter, "analyzing waveform…")
            return
        n = len(self._peaks)
        played_x = self._progress * width
        # one bar per pixel column, sampling the peak array
        for x in range(width):
            peak = self._peaks[min(n - 1, int(x * n / width))]
            half = max(1.0, peak * (mid - 3))
            painter.fillRect(
                x, int(mid - half), 1, int(half * 2),
                PLAYED if x <= played_x else UNPLAYED,
            )

    def _seek_to(self, x: float) -> None:
        if self._peaks is not None and self.width() > 0:
            self.seek_fraction.emit(min(1.0, max(0.0, x / self.width())))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._seek_to(event.position().x())

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            self._seek_to(event.position().x())
