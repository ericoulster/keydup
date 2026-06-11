"""Filter panel: Camelot wheel, harmonic-match toggle, BPM range.

Owns pushing filter state into the TrackFilterProxy; text search stays
in the toolbar, tag filtering joins in M4."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from superqt import QLabeledRangeSlider

from keydup.domain import expand_harmonic
from keydup.ui.camelot_wheel import CamelotWheel
from keydup.ui.track_table import TrackFilterProxy

BPM_MIN, BPM_MAX = 55, 215


class FilterBar(QWidget):
    def __init__(self, proxy: TrackFilterProxy, parent=None):
        super().__init__(parent)
        self.proxy = proxy

        self.wheel = CamelotWheel(self)
        self.harmonic = QCheckBox("Include harmonic matches", self)
        self.bpm = QLabeledRangeSlider(Qt.Horizontal, self)
        self.bpm.setRange(BPM_MIN, BPM_MAX)
        self.bpm.setValue((BPM_MIN, BPM_MAX))
        self.clear_button = QPushButton("Clear filters", self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.wheel)
        layout.addWidget(self.harmonic)
        layout.addWidget(QLabel("BPM range", self))
        layout.addWidget(self.bpm)
        layout.addWidget(self.clear_button)
        layout.addStretch(1)

        self.wheel.selection_changed.connect(lambda _: self._apply_keys())
        self.harmonic.toggled.connect(lambda _: self._apply_keys())
        self.bpm.valueChanged.connect(self._apply_bpm)
        self.clear_button.clicked.connect(self.clear_all)

    def _apply_keys(self) -> None:
        selected = self.wheel.selected()
        if selected and self.harmonic.isChecked():
            expanded = expand_harmonic(selected)
            self.wheel.set_harmonic_preview(expanded - selected)
            self.proxy.set_keys(expanded)
        else:
            self.wheel.set_harmonic_preview(frozenset())
            self.proxy.set_keys(selected)

    def _apply_bpm(self, value: tuple[int, int]) -> None:
        lo, hi = int(value[0]), int(value[1])
        if (lo, hi) == (BPM_MIN, BPM_MAX):
            self.proxy.set_bpm_range(None, None)  # full span = no filter
        else:
            self.proxy.set_bpm_range(lo, hi)

    def clear_all(self) -> None:
        self.wheel.clear()
        self.harmonic.setChecked(False)
        self.bpm.setValue((BPM_MIN, BPM_MAX))
