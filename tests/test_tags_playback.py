"""Tag assignment/filtering and playback smoke (offscreen)."""

import numpy as np
import pytest
import soundfile as sf
from PySide6.QtCore import Qt
from PySide6.QtMultimedia import QMediaPlayer

from keydup.db import Database
from keydup.library import LibraryService
from keydup.ui.main_window import MainWindow
from keydup.ui.tag_panel import TagPanel
from keydup.ui.track_table import COL_FILENAME


@pytest.fixture
def lib_with_tracks(qtbot, tmp_path):
    sr = 22050
    for name in ("a.wav", "b.wav"):
        t = np.linspace(0, 1.5, int(sr * 1.5), endpoint=False)
        sf.write(tmp_path / name, (0.2 * np.sin(2 * np.pi * 330 * t)).astype("float32"), sr)
    db = Database(tmp_path / "lib.db")
    library = LibraryService(db, auto_analyze=False)
    with qtbot.waitSignal(library.scan_finished, timeout=15000):
        library.add_folder(str(tmp_path))
    return library


def test_tag_assign_and_filter(qtbot, lib_with_tracks):
    library = lib_with_tracks
    window = MainWindow(library)
    qtbot.addWidget(window)

    tracks = library.all_tracks()
    house = library.create_tag("house", "genre")
    summer = library.create_tag("summer set", "set")
    library.set_track_tag(tracks[0].id, house.id, True)
    library.set_track_tag(tracks[1].id, summer.id, True)

    # model rows picked up the tag names
    by_file = {t.filename: t for t in window.model.tracks}
    assert by_file["a.wav"].tag_names == ("house",)
    assert by_file["b.wav"].tag_names == ("summer set",)

    # checking a tag in the panel filters the table
    panel: TagPanel = window.tag_panel

    def group(label):
        for i in range(panel.tree.topLevelItemCount()):
            if panel.tree.topLevelItem(i).text(0) == label:
                return panel.tree.topLevelItem(i)
        raise AssertionError(f"no {label} group")

    root = group("Genres")
    assert root.child(0).text(0) == "house"
    root.child(0).setCheckState(0, Qt.Checked)
    assert window.proxy.rowCount() == 1
    assert window.proxy.index(0, COL_FILENAME).data() == "a.wav"

    # unassign -> filtered out entirely
    library.set_track_tag(tracks[0].id, house.id, False)
    assert window.proxy.rowCount() == 0

    # uncheck -> all back
    root.child(0).setCheckState(0, Qt.Unchecked)
    assert window.proxy.rowCount() == 2

    # delete tag refreshes panel
    library.delete_tag(house.id)
    assert group("Genres").childCount() == 0
    library.db.close()


def test_playback_loads_media(qtbot, lib_with_tracks):
    library = lib_with_tracks
    window = MainWindow(library)
    qtbot.addWidget(window)
    track = library.all_tracks()[0]

    window.player.play_track(track)
    qtbot.waitUntil(
        lambda: window.player.player.mediaStatus()
        in (
            QMediaPlayer.BufferedMedia,
            QMediaPlayer.LoadedMedia,
            QMediaPlayer.EndOfMedia,
        ),
        timeout=10000,
    )
    assert window.player.player.duration() > 0
    assert "a.wav" in window.player.now_playing.text() or window.player.now_playing.text()
    window.player.player.stop()
    library.db.close()
