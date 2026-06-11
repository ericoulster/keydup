"""End-to-end analysis pipeline test with real models on synthetic
click tracks (known BPM ground truth). Slow (~tens of seconds, CPU)."""

import numpy as np
import pytest
import soundfile as sf

from keydup.db import Database
from keydup.library import LibraryService


def click_track(path, bpm, seconds=30, sr=44100):
    samples = np.zeros(sr * seconds, dtype=np.float32)
    step = int(sr * 60 / bpm)
    burst = (np.sin(2 * np.pi * 220 * np.arange(220) / sr) * np.linspace(1, 0, 220)).astype(
        np.float32
    )
    for i in range(0, len(samples) - len(burst), step):
        samples[i : i + len(burst)] += burst
    sf.write(path, samples, sr)


@pytest.fixture
def click_dir(tmp_path):
    click_track(tmp_path / "click128.wav", 128)
    click_track(tmp_path / "click174.wav", 174)
    return tmp_path


@pytest.mark.slow
def test_analysis_end_to_end(qtbot, tmp_path, click_dir):
    db = Database(tmp_path / "lib.db")
    library = LibraryService(db)  # auto_analyze kicks in after the scan

    with qtbot.waitSignal(library.analysis_finished, timeout=300_000):
        library.add_folder(str(click_dir))

    tracks = {t.filename: t for t in db.all_tracks()}
    assert all(t.status == "done" for t in tracks.values())
    assert tracks["click128.wav"].bpm == 128
    assert tracks["click174.wav"].bpm == 174
    assert all(t.key_camelot for t in tracks.values())
    assert all(t.bpm_source == "essentia" for t in tracks.values())
    assert all(t.analyzed_at for t in tracks.values())

    # nothing left pending; re-analyze queues it again
    assert db.pending_track_ids() == []
    some_id = tracks["click128.wav"].id
    with qtbot.waitSignal(library.analysis_finished, timeout=300_000):
        library.reanalyze([some_id])
    assert db.get_track(some_id).bpm == 128
    db.close()
