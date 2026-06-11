"""Configure harmonic matches by example: an anchor key is fixed on a
reference wheel; click the wedges that should count as its harmonic
matches. Moves are relative, so the example defines the rules for all
24 keys (letter-symmetric)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from keydup import harmonics
from keydup.ui.camelot_wheel import CamelotWheel

ANCHOR = "1A"


class HarmonicDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Harmonic matches")

        self.wheel = CamelotWheel(self)
        self.wheel.locked = frozenset({ANCHOR})
        self.wheel.setMinimumSize(300, 300)

        anchor_label = self.wheel.key_formatter(ANCHOR)
        hint = QLabel(
            f"Click the keys that count as harmonic matches for {anchor_label} "
            "(white ring). The pattern applies relative to every key.",
            self,
        )
        hint.setWordWrap(True)

        self.summary = QLabel("", self)
        self.summary.setWordWrap(True)

        standard = QPushButton("Standard", self)
        extended = QPushButton("Extended (+diagonals, +7)", self)
        presets = QHBoxLayout()
        presets.addWidget(QLabel("Presets:", self))
        presets.addWidget(standard)
        presets.addWidget(extended)
        presets.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.wheel, 1)
        layout.addWidget(self.summary)
        layout.addLayout(presets)
        layout.addWidget(buttons)

        standard.clicked.connect(lambda: self._load(harmonics.STANDARD_RULES))
        extended.clicked.connect(lambda: self._load(harmonics.EXTENDED_RULES))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.wheel.selection_changed.connect(self._on_selection)

        self._load(harmonics.saved_rules())

    def _load(self, rules) -> None:
        matches = harmonics.apply_rules(ANCHOR, rules) - {ANCHOR}
        self.wheel.set_selected(frozenset(matches))
        self._update_summary()

    def _on_selection(self, _keys) -> None:
        self._update_summary()

    def rules(self):
        return harmonics.rules_from_example(ANCHOR, self.wheel.selected())

    def _update_summary(self) -> None:
        self.summary.setText(f"Moves: {harmonics.describe(self.rules())}")
