"""Waveform peaks/caching, set reordering, and view plumbing."""

import numpy as np
import pytest
import soundfile as sf

from keydup.analysis.waveform import compute_peaks
from keydup.db import Database
from keydup.domain import TrackStub
from keydup.library import LibraryService


def test_compute_peaks_shape_and_dynamics(tmp_path):
    sr = 22050
    # quiet first half, loud second half
    quiet = 0.05 * np.sin(2 * np.pi * 220 * np.linspace(0, 5, sr * 5))
    loud = 0.9 * np.sin(2 * np.pi * 220 * np.linspace(0, 5, sr * 5))
    path = tmp_path / "dyn.wav"
    sf.write(path, np.concatenate([quiet, loud]).astype("float32"), sr)

    peaks = compute_peaks(str(path), bins=100)
    assert peaks.shape == (100,)
    assert peaks.dtype == np.float32
    assert peaks.max() <= 1.0 + 1e-6
    assert peaks[:45].mean() < peaks[55:].mean() * 0.2  # quiet half is quiet


def _stub(path, size=1000, duration=10.0):
    return TrackStub(
        path=str(path), filename=str(path).rsplit("/", 1)[-1], artist=None,
        title=None, album=None, duration_s=duration, file_size=size, file_mtime=1.0,
    )


def test_waveform_cached_in_db(qtbot, tmp_path):
    sr = 22050
    path = tmp_path / "a.wav"
    t = np.linspace(0, 2, sr * 2, endpoint=False)
    sf.write(path, (0.5 * np.sin(2 * np.pi * 330 * t)).astype("float32"), sr)

    db = Database(tmp_path / "lib.db")
    library = LibraryService(db, auto_analyze=False)
    folder = db.add_folder(str(tmp_path))
    track, _ = db.upsert_scanned(folder.id, _stub(path))

    with qtbot.waitSignal(library.waveform_ready, timeout=30000) as blocker:
        library.request_waveform(track)
    track_id, peaks = blocker.args
    assert track_id == track.id and len(peaks) == 800

    # second request comes straight from the DB cache
    assert db.load_waveform(track.id) is not None
    with qtbot.waitSignal(library.waveform_ready, timeout=1000) as blocker:
        library.request_waveform(track)
    cached = blocker.args[1]
    assert np.allclose(cached, peaks)
    db.close()


def test_reorder_set_moves_block(tmp_path):
    db = Database(tmp_path / "t.db")
    library = LibraryService(db, auto_analyze=False)
    folder = db.add_folder("/music")
    tag = db.create_tag("gig", "set")
    ids = []
    for i in range(5):
        track, _ = db.upsert_scanned(folder.id, _stub(f"/music/{i}.mp3", size=100 + i))
        db.assign_tag(track.id, tag.id)
        ids.append(track.id)

    # drag tracks 0 and 1 (as a block) to before track 4
    library.reorder_set(tag.id, [ids[0], ids[1]], before_id=ids[4])
    assert db.set_track_ids_ordered(tag.id) == [ids[2], ids[3], ids[0], ids[1], ids[4]]

    # drop at the end
    library.reorder_set(tag.id, [ids[2]], before_id=None)
    assert db.set_track_ids_ordered(tag.id) == [ids[3], ids[0], ids[1], ids[4], ids[2]]
    db.close()


def test_view_reorder_toggling(qtbot):
    from keydup.ui.track_table import TrackTableView

    view = TrackTableView()
    qtbot.addWidget(view)
    view.set_reorder_enabled(True)
    assert view.dragEnabled() and view.acceptDrops()
    view.set_reorder_enabled(False)
    assert not view.acceptDrops()
