"""Filter panel: Camelot wheel, harmonic-match toggle, BPM range.

Owns pushing filter state into the TrackFilterProxy; text search stays
in the toolbar, tag filtering joins in M4."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from superqt import QLabeledRangeSlider

from keydup import harmonics
from keydup.ui.camelot_wheel import CamelotWheel
from keydup.ui.harmonic_dialog import HarmonicDialog
from keydup.ui.track_table import TrackFilterProxy

BPM_MIN, BPM_MAX = 55, 215


class FilterBar(QWidget):
    def __init__(self, proxy: TrackFilterProxy, parent=None):
        super().__init__(parent)
        self.proxy = proxy

        self.wheel = CamelotWheel(self)
        self.harmonic = QCheckBox("Include harmonic matches", self)
        self.harmonic_config = QToolButton(self)
        self.harmonic_config.setText("⚙")
        self.harmonic_config.setToolTip("Configure which moves count as harmonic")
        self._rules = harmonics.saved_rules()
        self.bpm = QLabeledRangeSlider(Qt.Horizontal, self)
        self.bpm.setRange(BPM_MIN, BPM_MAX)
        self.bpm.setValue((BPM_MIN, BPM_MAX))
        self.clear_button = QPushButton("Clear filters", self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.wheel)
        harmonic_row = QHBoxLayout()
        harmonic_row.addWidget(self.harmonic, 1)
        harmonic_row.addWidget(self.harmonic_config)
        layout.addLayout(harmonic_row)
        layout.addWidget(QLabel("BPM range", self))
        layout.addWidget(self.bpm)
        layout.addWidget(self.clear_button)
        layout.addStretch(1)

        self.wheel.selection_changed.connect(lambda _: self._apply_keys())
        self.harmonic.toggled.connect(lambda _: self._apply_keys())
        self.harmonic_config.clicked.connect(self._configure_harmonics)
        self.bpm.valueChanged.connect(self._apply_bpm)
        self.clear_button.clicked.connect(self.clear_all)

    def _configure_harmonics(self) -> None:
        dialog = HarmonicDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self._rules = dialog.rules()
            harmonics.save_rules(self._rules)
            self._apply_keys()

    def _apply_keys(self) -> None:
        selected = self.wheel.selected()
        if selected and self.harmonic.isChecked():
            expanded = harmonics.expand(selected, self._rules)
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
