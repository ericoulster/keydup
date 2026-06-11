"""Configurable harmonic-match rules.

A rule is a relative move on the key wheel: (number delta mod 12, flip
letter). The standard DJ definition is one step either way plus the
relative major/minor; the extended preset adds the diagonal moves
(3A -> 4B / 2B) and the +7 'energy boost' (one semitone up). Rules are
letter-symmetric: a rule derived from a minor anchor applies mirrored
to major keys."""

from __future__ import annotations

import json

from keydup.domain import parse_camelot

Rule = tuple[int, bool]  # (delta mod 12, flip letter)

STANDARD_RULES: frozenset[Rule] = frozenset({(1, False), (11, False), (0, True)})
EXTENDED_RULES: frozenset[Rule] = STANDARD_RULES | {
    (1, True),   # diagonal up: 3A -> 4B
    (11, True),  # diagonal down: 3A -> 2B
    (7, False),  # energy boost: +1 semitone, 3A -> 10A
}

_MOVE_NAMES = {
    (1, False): "+1",
    (11, False): "-1",
    (0, True): "relative",
    (1, True): "diag up",
    (11, True): "diag down",
    (7, False): "+7 energy",
    (5, False): "-7",
    (2, False): "+2",
}


def apply_rules(key: str, rules: frozenset[Rule]) -> frozenset[str]:
    """The key itself plus every rule applied to it."""
    number, letter = parse_camelot(key)
    out = {key}
    for delta, flip in rules:
        n = (number - 1 + delta) % 12 + 1
        l = ({"A": "B", "B": "A"}[letter]) if flip else letter
        out.add(f"{n}{l}")
    return frozenset(out)


def expand(keys: frozenset[str], rules: frozenset[Rule]) -> frozenset[str]:
    out: set[str] = set()
    for key in keys:
        out |= apply_rules(key, rules)
    return frozenset(out)


def rules_from_example(anchor: str, matches: frozenset[str]) -> frozenset[Rule]:
    """Derive the rule set from a clicked example: which wedges count as
    matches for the anchor key (the anchor itself is ignored)."""
    a_num, a_letter = parse_camelot(anchor)
    rules: set[Rule] = set()
    for key in matches:
        if key == anchor:
            continue
        n, letter = parse_camelot(key)
        rules.add(((n - a_num) % 12, letter != a_letter))
    return frozenset(rules)


def describe(rules: frozenset[Rule]) -> str:
    def name(rule: Rule) -> str:
        if rule in _MOVE_NAMES:
            return _MOVE_NAMES[rule]
        delta, flip = rule
        signed = delta if delta <= 6 else delta - 12
        return f"{signed:+d}{' flip' if flip else ''}"

    return " · ".join(name(r) for r in sorted(rules)) or "none"


def saved_rules() -> frozenset[Rule]:
    from PySide6.QtCore import QSettings

    raw = QSettings("keydup", "keydup").value("harmonic_rules")
    if not raw:
        return STANDARD_RULES
    try:
        return frozenset((int(d) % 12, bool(f)) for d, f in json.loads(raw))
    except Exception:
        return STANDARD_RULES


def save_rules(rules: frozenset[Rule]) -> None:
    from PySide6.QtCore import QSettings

    QSettings("keydup", "keydup").setValue(
        "harmonic_rules", json.dumps(sorted([d, f] for d, f in rules))
    )
