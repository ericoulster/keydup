"""Playback screening: don't hand corrupt / non-audio files to the media
backend (a native crash Python can't catch), and never store a blank
analysis error that shows a warning with no explanation."""

import numpy as np
import soundfile as sf

from keydup.analysis.probe import looks_like_audio
from keydup.db import Database
from keydup.domain import Track
from keydup.library import LibraryService
from keydup.ui.main_window import MainWindow


def test_looks_like_audio_rejects_html_and_empty(tmp_path):
    html = tmp_path / "fake.mp3"
    html.write_bytes(b" <!DOCTYPE html>\n<html lang=\"en\"><body>x</body></html>\n")
    assert looks_like_audio(str(html)) is False

    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    assert looks_like_audio(str(empty)) is False


def test_looks_like_audio_accepts_real_wav(tmp_path):
    wav = tmp_path / "real.wav"
    sr = 22050
    sf.write(wav, (0.2 * np.sin(2 * np.pi * 330 * np.linspace(0, 1, sr))).astype("float32"), sr)
    assert looks_like_audio(str(wav)) is True


def test_error_track_is_blocked_with_reason(qtbot, tmp_path):
    db = Database(tmp_path / "lib.db")
    window = MainWindow(LibraryService(db, auto_analyze=False))
    qtbot.addWidget(window)

    bad = Track(id=1, folder_id=1, path="/music/x.wma", filename="x.wma",
                status="error", error="no decoder could read this file")
    reason = window._playback_block_reason(bad)
    assert reason is not None and "no decoder" in reason

    # legacy error row with no message still blocks, with a generic reason
    blank = Track(id=2, folder_id=1, path="/music/y.wma", filename="y.wma",
                  status="error", error="")
    assert window._playback_block_reason(blank) is not None
    db.close()


def test_good_track_is_not_blocked(qtbot, tmp_path):
    db = Database(tmp_path / "lib.db")
    window = MainWindow(LibraryService(db, auto_analyze=False))
    qtbot.addWidget(window)

    wav = tmp_path / "ok.wav"
    sr = 22050
    sf.write(wav, (0.2 * np.sin(2 * np.pi * 330 * np.linspace(0, 1, sr))).astype("float32"), sr)
    good = Track(id=1, folder_id=1, path=str(wav), filename="ok.wav", status="done")
    assert window._playback_block_reason(good) is None
    db.close()
