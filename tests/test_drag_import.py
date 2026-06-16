"""Drag-and-drop import of files and folders."""

import numpy as np
import soundfile as sf

from keydup.db import Database
from keydup.library import LibraryService
from keydup.ui.main_window import MainWindow


def _wavs(dir_path, names):
    sr = 22050
    for n in names:
        sf.write(dir_path / n,
                 (0.2 * np.sin(2 * np.pi * 330 * np.linspace(0, 1, sr))).astype("float32"),
                 sr)


def test_add_files_imports_individual_tracks(qtbot, tmp_path):
    _wavs(tmp_path, ("a.wav", "b.wav", "c.wav"))
    db = Database(tmp_path / "lib.db")
    library = LibraryService(db, auto_analyze=False)

    added = library.add_files([str(tmp_path / "a.wav"), str(tmp_path / "b.wav")])
    assert {t.filename for t in added} == {"a.wav", "b.wav"}     # only the two
    assert {t.filename for t in db.all_tracks()} == {"a.wav", "b.wav"}
    assert len(library.session_new_ids) == 2                     # marked "new"
    # re-dropping the same file is a no-op
    assert library.add_files([str(tmp_path / "a.wav")]) == []
    db.close()


def test_import_paths_routes_and_filters(qtbot, tmp_path):
    folder = tmp_path / "album"
    folder.mkdir()
    _wavs(folder, ("track.wav",))
    _wavs(tmp_path, ("loose.wav",))
    (tmp_path / "notes.txt").write_text("not audio")

    db = Database(tmp_path / "lib.db")
    window = MainWindow(LibraryService(db, auto_analyze=False))
    qtbot.addWidget(window)

    calls = {"folders": [], "files": []}
    window.library.add_folder = lambda p, *a, **k: calls["folders"].append(p)
    window.library.add_files = lambda paths: calls["files"].append(paths)

    window.import_paths([
        str(folder),                 # dir -> add_folder
        str(tmp_path / "loose.wav"), # audio file -> add_files
        str(tmp_path / "notes.txt"), # non-audio -> filtered out
    ])
    assert calls["folders"] == [str(folder)]
    assert calls["files"] == [[str(tmp_path / "loose.wav")]]
    db.close()


def test_main_window_accepts_drops(qtbot, tmp_path):
    db = Database(tmp_path / "lib.db")
    window = MainWindow(LibraryService(db, auto_analyze=False))
    qtbot.addWidget(window)
    assert window.acceptDrops()
    db.close()
