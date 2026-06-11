"""Offscreen GUI smoke test: build the window, scan a folder of real
(generated) wav files, see rows appear and filters work."""

import numpy as np
import pytest
import soundfile as sf

from keydup.db import Database
from keydup.library import LibraryService
from keydup.ui.main_window import MainWindow


@pytest.fixture
def music_dir(tmp_path):
    sr = 22050
    for name, freq in [("one.wav", 220), ("two.wav", 440), ("three.wav", 330)]:
        t = np.linspace(0, 2.0, sr * 2, endpoint=False)
        sf.write(tmp_path / name, (0.2 * np.sin(2 * np.pi * freq * t)).astype("float32"), sr)
    return tmp_path


def test_scan_populates_table(qtbot, tmp_path, music_dir):
    db = Database(tmp_path / "lib.db")
    library = LibraryService(db)
    window = MainWindow(library)
    qtbot.addWidget(window)

    with qtbot.waitSignal(library.scan_finished, timeout=15000):
        library.add_folder(str(music_dir))

    assert window.model.rowCount() == 3
    assert {t.filename for t in window.model.tracks} == {"one.wav", "two.wav", "three.wav"}
    assert all(t.status == "pending" for t in window.model.tracks)
    assert all(t.duration_s and abs(t.duration_s - 2.0) < 0.1 for t in window.model.tracks)

    # restart: persistence
    window2 = MainWindow(LibraryService(db))
    qtbot.addWidget(window2)
    assert window2.model.rowCount() == 3

    # text filter through the proxy
    window.proxy.set_text("two")
    assert window.proxy.rowCount() == 1
    window.proxy.set_text("")
    assert window.proxy.rowCount() == 3
    db.close()


def test_rescan_is_unchanged(qtbot, tmp_path, music_dir):
    db = Database(tmp_path / "lib.db")
    library = LibraryService(db)
    with qtbot.waitSignal(library.scan_finished, timeout=15000):
        library.add_folder(str(music_dir))

    seen = []
    library.tracks_upserted.connect(seen.append)
    with qtbot.waitSignal(library.scan_finished, timeout=15000):
        library.rescan_all()
    assert seen == []  # nothing changed on disk -> no model churn
    db.close()
