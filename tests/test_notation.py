import json

from keydup import notation
from keydup.notation import camelot_to_openkey, get_formatter


def test_openkey_anchors():
    # C major: Camelot 8B = Open Key 1d; A minor: 8A = 1m
    assert camelot_to_openkey("8B") == "1d"
    assert camelot_to_openkey("8A") == "1m"
    # F minor (keypipe '4A') is Open Key 9m; Ab minor 1A -> 6m
    assert camelot_to_openkey("4A") == "9m"
    assert camelot_to_openkey("1A") == "6m"
    assert camelot_to_openkey("12B") == "5d"


def test_openkey_is_bijective():
    keys = {f"{n}{x}" for n in range(1, 13) for x in "AB"}
    assert len({camelot_to_openkey(k) for k in keys}) == 24


def test_formatters():
    assert get_formatter("camelot")("4A") == "4A"
    assert get_formatter("openkey")("4A") == "9m"
    assert "minor" in get_formatter("names")("4A").lower()


def test_custom_formatter(tmp_path, monkeypatch):
    monkeypatch.setattr(notation, "custom_mapping_path", lambda: tmp_path / "n.json")
    (tmp_path / "n.json").write_text(json.dumps({"4A": "Fm!"}))
    fmt = get_formatter("custom")
    assert fmt("4A") == "Fm!"
    assert fmt("8B") == "1d"  # unmapped keys fall back to Open Key


def test_model_uses_formatter(qtbot):
    from keydup.domain import Track
    from keydup.ui.track_table import COL_KEY, TrackTableModel

    model = TrackTableModel()
    model.set_tracks([
        Track(id=1, folder_id=1, path="/m/a.mp3", filename="a.mp3",
              key_camelot="4A", status="done")
    ])
    model.set_key_formatter(get_formatter("openkey"))
    assert model.index(0, COL_KEY).data() == "9m"
    model.set_key_formatter(get_formatter("camelot"))
    assert model.index(0, COL_KEY).data() == "4A"


def test_about_text_credits_eric():
    from keydup.ui.main_window import about_text

    text = about_text()
    assert "Eric Oulster" in text
    assert "https://github.com/ericoulster" in text
