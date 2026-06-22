"""On-demand key-change detection (auto-detection was removed as unreliable)."""

import re
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from keydup.db import Database
from keydup.domain import TrackStub
from keydup.library import LibraryService


def _track(db, path, duration=300.0):
    folder = db.add_folder(str(Path(path).parent))
    stub = TrackStub(path=str(path), filename=Path(path).name, artist=None,
                     title=None, album=None, duration_s=duration,
                     file_size=1, file_mtime=1.0)
    return db.upsert_scanned(folder.id, stub)[0]


def test_analysis_does_not_auto_detect_segments(monkeypatch):
    """The analyzer must NOT call detect_segments during normal analysis."""
    import keydup.analysis.analyzer as az
    src = Path(az.__file__).read_text()
    assert "detect_segments" not in src, "analyzer should not auto-run key segmentation"


def test_store_then_clear_roundtrip(tmp_path):
    db = Database(tmp_path / "lib.db")
    track = _track(db, tmp_path / "a.mp3")
    db.save_analysis(track.id, "10B", 0.49, 174, 0.8, "tempocnn-onnx")

    # a real multi-key result is stored + secondary derived
    segs = [
        {"start_s": 0, "end_s": 120, "key": "10B", "confidence": 0.6},
        {"start_s": 120, "end_s": 300, "key": "7A", "confidence": 0.6},
    ]
    db.save_key_segments(track.id, segs)
    assert db.get_track(track.id).key_secondary == "7A"
    assert len(db.load_key_segments(track.id)) == 2

    # clearing removes both the segments and the secondary flag
    db.clear_key_segments(track.id)
    assert db.get_track(track.id).key_secondary is None
    assert db.load_key_segments(track.id) == []
    db.close()


def test_on_demand_handler_branches(qtbot, tmp_path):
    db = Database(tmp_path / "lib.db")
    library = LibraryService(db, auto_analyze=False)
    track = _track(db, tmp_path / "a.mp3")
    db.save_analysis(track.id, "10B", 0.49, 174, 0.8, "tempocnn-onnx")

    emitted = []
    library.tracks_upserted.connect(emitted.append)

    # multi-key segments -> stored
    library._on_key_changes(track.id, [
        {"start_s": 0, "end_s": 150, "key": "10B", "confidence": 0.6},
        {"start_s": 150, "end_s": 300, "key": "7A", "confidence": 0.6},
    ])
    assert db.get_track(track.id).key_secondary == "7A"

    # a later single-key result clears it
    library._on_key_changes(track.id, [
        {"start_s": 0, "end_s": 300, "key": "10B", "confidence": 0.6},
    ])
    assert db.get_track(track.id).key_secondary is None
    db.close()


# the actual filename tells us this track really is dual-key (10A/10B)
AS_ONE = (
    "/home/hq/Music/03. Set Planning/Kawaii Karnival/Kawaii Karnival Set/"
    "23. As One - 10A or 10B - 87.50.mp3"
)


@pytest.mark.slow
@pytest.mark.skipif(not Path(AS_ONE).exists(), reason="sample track absent")
def test_on_demand_real_track(qtbot, tmp_path):
    db = Database(tmp_path / "lib.db")
    library = LibraryService(db, auto_analyze=False)
    track = _track(db, AS_ONE, duration=318.0)

    with qtbot.waitSignal(library.key_changes_finished, timeout=120000):
        library.detect_key_changes([track.id])

    segs = library.key_segments(track.id)
    assert segs, "on-demand detection should produce segments"
    db.close()
