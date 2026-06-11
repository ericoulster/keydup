"""Interactive Camelot wheel: 12 outer wedges (B/major), 12 inner
wedges (A/minor), 12 o'clock at the top like Mixed In Key.

Click toggles a key, right-click or Esc clears, hover highlights.
Emits selection_changed(frozenset[str]). The filter bar passes back the
harmonically-expanded set for preview tinting."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from keypipe.utils import camelot_to_key_name

from keydup.notation import get_formatter, saved_notation

WEDGE_SPAN = 30.0  # degrees


def _wedge_path(center: QPointF, r_inner: float, r_outer: float, start_angle: float) -> QPainterPath:
    outer = QRectF(center.x() - r_outer, center.y() - r_outer, 2 * r_outer, 2 * r_outer)
    inner = QRectF(center.x() - r_inner, center.y() - r_inner, 2 * r_inner, 2 * r_inner)
    path = QPainterPath()
    path.arcMoveTo(outer, start_angle)
    path.arcTo(outer, start_angle, WEDGE_SPAN)
    path.arcTo(inner, start_angle + WEDGE_SPAN, -WEDGE_SPAN)
    path.closeSubpath()
    return path


class CamelotWheel(QWidget):
    selection_changed = Signal(object)  # frozenset[str]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._selected: set[str] = set()
        self._harmonic_preview: frozenset[str] = frozenset()
        self._hovered: str | None = None
        self._paths: dict[str, QPainterPath] = {}
        self.key_formatter = get_formatter(saved_notation())
        # keys that can't be toggled (e.g. the anchor in the harmonic
        # rule dialog); painted with a highlight ring
        self.locked: frozenset[str] = frozenset()

    def set_key_formatter(self, formatter) -> None:
        self.key_formatter = formatter
        self.update()

    # -- public API ----------------------------------------------------------

    def selected(self) -> frozenset[str]:
        return frozenset(self._selected)

    def set_selected(self, keys: frozenset[str]) -> None:
        if set(keys) != self._selected:
            self._selected = set(keys)
            self._emit_and_update()

    def set_harmonic_preview(self, keys: frozenset[str]) -> None:
        self._harmonic_preview = frozenset(keys)
        self.update()

    def clear(self) -> None:
        if self._selected:
            self._selected.clear()
            self._emit_and_update()

    def _emit_and_update(self) -> None:
        self.selection_changed.emit(frozenset(self._selected))
        self.update()

    # -- geometry --------------------------------------------------------------

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize

        return QSize(220, 220)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return width

    def resizeEvent(self, event) -> None:
        self._rebuild_paths()
        super().resizeEvent(event)

    def _rebuild_paths(self) -> None:
        side = min(self.width(), self.height())
        center = QPointF(self.width() / 2, self.height() / 2)
        r_outer = side / 2 - 4
        r_mid = r_outer * 0.72
        r_hub = r_outer * 0.44
        self._paths.clear()
        for n in range(1, 13):
            # wedge n is centered at 90 - n*30 degrees: 12 at the top,
            # numbers increasing clockwise
            start = 90.0 - n * WEDGE_SPAN - WEDGE_SPAN / 2
            self._paths[f"{n}B"] = _wedge_path(center, r_mid, r_outer, start)
            self._paths[f"{n}A"] = _wedge_path(center, r_hub, r_mid, start)

    # -- painting --------------------------------------------------------------

    def _wedge_color(self, key: str) -> QColor:
        n = int(key[:-1])
        hue = ((n - 1) * 30 + 210) % 360  # 12 distinct hues around the wheel
        is_minor = key.endswith("A")
        if key in self._selected:
            color = QColor.fromHsv(hue, 200, 235)
        elif key in self._harmonic_preview:
            color = QColor.fromHsv(hue, 160, 150)
        else:
            color = QColor.fromHsv(hue, 120 if is_minor else 140, 78)
        if key == self._hovered and key not in self._selected:
            color = color.lighter(135)
        return color

    def paintEvent(self, event) -> None:
        if not self._paths:
            self._rebuild_paths()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bg = self.palette().window().color()
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, min(self.width(), self.height()) / 26))
        font.setBold(True)
        painter.setFont(font)

        for key, path in self._paths.items():
            if key in self.locked:
                painter.setPen(QPen(QColor("#ffffff"), 2))
            else:
                painter.setPen(QPen(bg, 2))
            painter.setBrush(self._wedge_color(key))
            painter.drawPath(path)

        # labels on top of wedges
        for key, path in self._paths.items():
            rect = path.boundingRect()
            selected = key in self._selected
            painter.setPen(QColor("#ffffff") if selected else QColor("#d4d4dc"))
            painter.drawText(
                self._label_rect(key), Qt.AlignCenter, self.key_formatter(key)
            )

        if self._selected:
            painter.setPen(QColor("#9a9aa5"))
            small = QFont(self.font())
            small.setPointSizeF(max(7.0, min(self.width(), self.height()) / 30))
            painter.setFont(small)
            hub = QRectF(0, 0, self.width(), self.height())
            painter.drawText(
                hub,
                Qt.AlignCenter,
                "\n".join(self.key_formatter(k) for k in sorted(self._selected)[:4]),
            )

    def _label_rect(self, key: str) -> QRectF:
        import math

        side = min(self.width(), self.height())
        center = QPointF(self.width() / 2, self.height() / 2)
        r_outer = side / 2 - 4
        radius = r_outer * (0.86 if key.endswith("B") else 0.58)
        n = int(key[:-1])
        angle_deg = 90.0 - n * WEDGE_SPAN
        angle = math.radians(angle_deg)
        x = center.x() + radius * math.cos(angle)
        y = center.y() - radius * math.sin(angle)
        return QRectF(x - 18, y - 12, 36, 24)

    # -- interaction -------------------------------------------------------------

    def _key_at(self, pos: QPointF) -> str | None:
        for key, path in self._paths.items():
            if path.contains(pos):
                return key
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            self.clear()
            return
        key = self._key_at(event.position())
        if key is None or key in self.locked:
            return
        if key in self._selected:
            self._selected.discard(key)
        else:
            self._selected.add(key)
        self._emit_and_update()

    def mouseMoveEvent(self, event) -> None:
        key = self._key_at(event.position())
        if key != self._hovered:
            self._hovered = key
            if key:
                label = self.key_formatter(key)
                try:
                    name = camelot_to_key_name(key)
                except Exception:
                    name = None
                self.setToolTip(f"{label} - {name}" if name and name != label else label)
            self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = None
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.clear()
        else:
            super().keyPressEvent(event)
