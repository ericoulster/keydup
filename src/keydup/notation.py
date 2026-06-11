"""Key notation display layer.

keypipe emits Camelot-style strings ('4A') and the DB stores them as the
canonical form, but 'Camelot' is Mixed In Key's branding - so the UI
defaults to Open Key notation (the Beatport/Traktor open standard:
1d-12d major, 1m-12m minor) and the notation is user-selectable,
including a custom mapping from a JSON file."""

from __future__ import annotations

import json
from typing import Callable

from keypipe.utils import camelot_to_key_name

from keydup.paths import data_dir

DEFAULT_NOTATION = "openkey"
NOTATIONS = ("openkey", "camelot", "names", "custom")
NOTATION_LABELS = {
    "openkey": "Open Key (1d-12m)",
    "camelot": "Wheel numbers (1A-12B)",
    "names": "Key names (F minor)",
    "custom": "Custom (notation.json)",
}

Formatter = Callable[[str], str]


def camelot_to_openkey(key: str) -> str:
    """'8B' -> '1d', '8A' -> '1m' (anchors: C major = 8B = 1d,
    A minor = 8A = 1m; both wheels step by fifths)."""
    number, letter = int(key[:-1]), key[-1].upper()
    return f"{(number - 8) % 12 + 1}{'d' if letter == 'B' else 'm'}"


def _names_formatter(key: str) -> str:
    try:
        return camelot_to_key_name(key) or key
    except Exception:
        return key


def custom_mapping_path():
    return data_dir() / "notation.json"


def ensure_custom_template() -> None:
    """Create an editable mapping file (pre-filled with Open Key labels)
    the first time the user picks the custom notation."""
    path = custom_mapping_path()
    if path.exists():
        return
    mapping = {
        f"{n}{letter}": camelot_to_openkey(f"{n}{letter}")
        for n in range(1, 13)
        for letter in ("A", "B")
    }
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True))


def _custom_formatter() -> Formatter:
    try:
        mapping = json.loads(custom_mapping_path().read_text())
    except Exception:
        mapping = {}

    def fmt(key: str) -> str:
        return str(mapping.get(key, camelot_to_openkey(key)))

    return fmt


def get_formatter(notation: str) -> Formatter:
    if notation == "camelot":
        return lambda key: key
    if notation == "names":
        return _names_formatter
    if notation == "custom":
        return _custom_formatter()
    return camelot_to_openkey


def saved_notation() -> str:
    from PySide6.QtCore import QSettings

    value = QSettings("keydup", "keydup").value("notation", DEFAULT_NOTATION)
    return value if value in NOTATIONS else DEFAULT_NOTATION


def save_notation(notation: str) -> None:
    from PySide6.QtCore import QSettings

    QSettings("keydup", "keydup").setValue("notation", notation)
