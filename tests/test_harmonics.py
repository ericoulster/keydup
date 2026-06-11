from keydup import harmonics
from keydup.harmonics import (
    EXTENDED_RULES,
    STANDARD_RULES,
    apply_rules,
    expand,
    rules_from_example,
)


def test_standard_matches_classic_neighbors():
    assert apply_rules("8A", STANDARD_RULES) == frozenset({"8A", "7A", "9A", "8B"})


def test_extended_rules_erics_examples():
    matches = apply_rules("3A", EXTENDED_RULES)
    # diagonals
    assert "4B" in matches and "2B" in matches
    # +7 energy boost
    assert "10A" in matches
    assert matches == frozenset({"3A", "2A", "4A", "3B", "4B", "2B", "10A"})


def test_extended_wraps_around():
    matches = apply_rules("12B", EXTENDED_RULES)
    assert "1A" in matches    # diagonal up wraps
    assert "7B" in matches    # 12 + 7 -> 7


def test_letter_symmetry():
    # rules derived from a minor example mirror onto major keys
    a = apply_rules("3A", EXTENDED_RULES)
    b = apply_rules("3B", EXTENDED_RULES)
    assert {k[-1] for k in a if k != "3B"} >= {"A"}
    assert "4A" in b and "2A" in b and "10B" in b


def test_rules_from_example_roundtrip():
    for rules in (STANDARD_RULES, EXTENDED_RULES):
        matches = apply_rules("1A", rules) - {"1A"}
        assert rules_from_example("1A", matches) == rules
    # anchor independence: same pattern from a different anchor
    matches = apply_rules("5B", EXTENDED_RULES) - {"5B"}
    assert rules_from_example("5B", matches) == EXTENDED_RULES


def test_describe_names_moves():
    text = harmonics.describe(EXTENDED_RULES)
    for fragment in ("+1", "-1", "relative", "diag up", "diag down", "+7 energy"):
        assert fragment in text


def test_save_load_roundtrip(qtbot):
    original = harmonics.saved_rules()
    try:
        harmonics.save_rules(EXTENDED_RULES)
        assert harmonics.saved_rules() == EXTENDED_RULES
        harmonics.save_rules(STANDARD_RULES)
        assert harmonics.saved_rules() == STANDARD_RULES
    finally:
        harmonics.save_rules(original)


def test_dialog_roundtrip(qtbot):
    from keydup.ui.harmonic_dialog import HarmonicDialog

    original = harmonics.saved_rules()
    try:
        harmonics.save_rules(STANDARD_RULES)
        dialog = HarmonicDialog()
        qtbot.addWidget(dialog)
        assert dialog.rules() == STANDARD_RULES
        # click the +7 wedge (8A relative to anchor 1A) on the reference wheel
        dialog.wheel.set_selected(dialog.wheel.selected() | {"8A"})
        assert (7, False) in dialog.rules()
        assert "+7 energy" in dialog.summary.text()
    finally:
        harmonics.save_rules(original)


def test_filter_uses_extended_rules(qtbot):
    from keydup.domain import Track
    from keydup.ui.filter_bar import FilterBar
    from keydup.ui.track_table import TrackFilterProxy, TrackTableModel

    model = TrackTableModel()
    model.set_tracks([
        Track(id=i, folder_id=1, path=f"/m/{i}.mp3", filename=f"{i}.mp3",
              key_camelot=key, status="done")
        for i, key in enumerate(["8A", "7A", "9A", "8B", "3A", "3B"], start=1)
    ])
    proxy = TrackFilterProxy()
    proxy.setSourceModel(model)

    original = harmonics.saved_rules()
    try:
        harmonics.save_rules(EXTENDED_RULES)
        bar = FilterBar(proxy)
        qtbot.addWidget(bar)
        bar.wheel.set_selected(frozenset({"8A"}))
        bar.harmonic.setChecked(True)
        visible = {
            model.tracks[proxy.mapToSource(proxy.index(r, 0)).row()].key_camelot
            for r in range(proxy.rowCount())
        }
        # +7 energy boost pulls in 3A; 3B (not a match of 8A) stays out
        assert visible == {"8A", "7A", "9A", "8B", "3A"}
        assert expand(frozenset({"8A"}), EXTENDED_RULES) == frozenset(
            {"8A", "7A", "9A", "8B", "9B", "7B", "3A"}
        )
    finally:
        harmonics.save_rules(original)
