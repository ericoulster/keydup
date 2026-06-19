"""Windowed key-segment detection, storage, and UI surfaces."""

from keypipe.inference import KeyDetector

from keydup.db import Database
from keydup.domain import Track
from keydup.ui.track_table import LOW_CONF_COLOR, TrackTableModel
from PySide6.QtCore import Qt


# -- collapse logic (pure, no model) ------------------------------------

def _windows(seq, win=30, hop=15):
    # seq: list of (key, conf) -> windowed tuples
    return [(i * hop, i * hop + win, k, c) for i, (k, c) in enumerate(seq)]


def test_collapse_suppresses_short_and_weak():
    # a long A, a 1-window weak blip, back to A -> single A segment
    w = _windows([("4A", 0.7)] * 6 + [("5B", 0.2)] + [("4A", 0.7)] * 6)
    segs = KeyDetector._collapse_windows(w, conf_floor=0.35, min_segment_s=45)
    assert [s["key"] for s in segs] == ["4A"]


def test_collapse_keeps_real_modulation():
    # sustained A then sustained B (each well over min_segment_s)
    w = _windows([("10A", 0.6)] * 6 + [("10B", 0.6)] * 6)
    segs = KeyDetector._collapse_windows(w, conf_floor=0.35, min_segment_s=45)
    assert [s["key"] for s in segs] == ["10A", "10B"]
    assert segs[0]["start_s"] == 0
    assert segs[1]["end_s"] == w[-1][1]


def test_collapse_weak_window_inherits_prior_key():
    w = _windows([("8A", 0.7)] * 4 + [("3B", 0.1)] + [("8A", 0.7)] * 4)
    segs = KeyDetector._collapse_windows(w, conf_floor=0.35, min_segment_s=45)
    assert [s["key"] for s in segs] == ["8A"]   # 3B@0.1 dropped, never introduced


# -- storage ------------------------------------------------------------

def test_save_segments_sets_secondary(tmp_path):
    db = Database(tmp_path / "lib.db")
    folder = db.add_folder("/m")
    from keydup.domain import TrackStub
    track, _ = db.upsert_scanned(folder.id, TrackStub(
        path="/m/a.mp3", filename="a.mp3", artist=None, title=None, album=None,
        duration_s=300.0, file_size=1, file_mtime=1.0))
    db.save_analysis(track.id, "10B", 0.49, 174, 0.8, "tempocnn-onnx")
    segs = [
        {"start_s": 0, "end_s": 60, "key": "10A", "confidence": 0.5},
        {"start_s": 60, "end_s": 280, "key": "10B", "confidence": 0.6},
        {"start_s": 280, "end_s": 300, "key": "10A", "confidence": 0.8},
    ]
    updated = db.save_key_segments(track.id, segs)
    # primary is 10B; secondary = the other key with most total duration (10A: 80s)
    assert updated.key_secondary == "10A"
    assert len(db.load_key_segments(track.id)) == 3
    db.close()


# -- UI surfaces --------------------------------------------------------

def _model_with(track):
    m = TrackTableModel()
    m.set_tracks([track])
    return m


def test_key_column_shows_secondary_and_dims_low_conf():
    from keydup.notation import get_formatter
    from keydup.ui.track_table import COL_KEY
    track = Track(id=1, folder_id=1, path="/m/a.mp3", filename="a.mp3",
                  key_camelot="10B", key_confidence=0.49, key_secondary="10A",
                  status="done")
    m = _model_with(track)
    m.set_key_formatter(get_formatter("camelot"))   # deterministic regardless of saved notation
    idx = m.index(0, COL_KEY)
    assert m.data(idx, Qt.DisplayRole) == "10B (+10A)"
    assert m.data(idx, Qt.ForegroundRole) == LOW_CONF_COLOR
    assert "may modulate" in m.data(idx, Qt.ToolTipRole)


def test_confident_single_key_has_no_flag():
    from keydup.ui.track_table import COL_KEY
    track = Track(id=2, folder_id=1, path="/m/b.mp3", filename="b.mp3",
                  key_camelot="4A", key_confidence=0.8, status="done")
    m = _model_with(track)
    idx = m.index(0, COL_KEY)
    assert m.data(idx, Qt.ForegroundRole) is None
    assert "(+" not in m.data(idx, Qt.DisplayRole)


def test_timeline_widget_renders(qtbot):
    from keydup.ui.key_timeline import KeyTimeline, key_hue_color
    tl = KeyTimeline()
    qtbot.addWidget(tl)
    assert not tl.has_segments()
    tl.set_segments([
        {"start_s": 0, "end_s": 60, "key": "10A", "confidence": 0.5},
        {"start_s": 60, "end_s": 120, "key": "10B", "confidence": 0.6},
    ], 120)
    tl.resize(200, 20)
    assert tl.has_segments()
    assert tl._segment_at(10)["key"] == "10A"   # left half
    assert tl._segment_at(190)["key"] == "10B"  # right half
    assert key_hue_color("10A") != key_hue_color("4A")
