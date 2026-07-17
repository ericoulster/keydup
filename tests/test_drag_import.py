"""Drag-and-drop import of files and folders."""

import numpy as np
import soundfile as sf
from PySide6.QtCore import Qt

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
    window.library.add_files = lambda paths, **k: calls["files"].append(paths)

    window.import_paths([
        str(folder),                 # dir -> add_folder
        str(tmp_path / "loose.wav"), # audio file -> add_files
        str(tmp_path / "notes.txt"), # non-audio -> filtered out
    ])
    assert calls["folders"] == [str(folder)]
    assert calls["files"] == [[str(tmp_path / "loose.wav")]]
    db.close()


def _check_tag(panel, tag_id):
    """Tick a tag in the panel tree, the way clicking its checkbox would."""
    for r in range(panel.tree.topLevelItemCount()):
        root = panel.tree.topLevelItem(r)
        for c in range(root.childCount()):
            child = root.child(c)
            if child.data(0, Qt.UserRole) == tag_id:
                child.setCheckState(0, Qt.Checked)
                return
    raise AssertionError(f"tag {tag_id} is not in the panel")


def test_add_files_assigns_tags_to_new_and_known_tracks(qtbot, tmp_path):
    _wavs(tmp_path, ("a.wav",))
    db = Database(tmp_path / "lib.db")
    library = LibraryService(db, auto_analyze=False)
    genre = library.create_tag("techno", "genre")

    added = library.add_files([str(tmp_path / "a.wav")], tag_ids=[genre.id])
    assert [t.filename for t in added] == ["a.wav"]
    assert genre.id in added[0].tag_ids

    # the point of the feature: re-dropping an ALREADY-imported track onto a
    # different active tag files it there too, on top of what it already has
    dj_set = library.create_tag("my set", "set")
    again = library.add_files([str(tmp_path / "a.wav")], tag_ids=[dj_set.id])
    assert len(again) == 1  # emitted despite the file itself being unchanged
    assert again[0].tag_ids == frozenset({genre.id, dj_set.id})

    # still a no-op when nothing is checked
    assert library.add_files([str(tmp_path / "a.wav")]) == []
    db.close()


def test_add_folder_assigns_existing_tags_after_scan(qtbot, tmp_path):
    _wavs(tmp_path, ("a.wav", "b.wav"))
    db = Database(tmp_path / "lib.db")
    library = LibraryService(db, auto_analyze=False)
    dj_set = library.create_tag("my set", "set")

    with qtbot.waitSignal(library.scan_finished, timeout=15000):
        library.add_folder(str(tmp_path), tag_ids=[dj_set.id])

    assert all(dj_set.id in t.tag_ids for t in db.all_tracks())
    assert [t.name for t in library.list_tags()] == ["my set"]  # none created
    db.close()


def test_import_paths_applies_checked_tags(qtbot, tmp_path):
    _wavs(tmp_path, ("loose.wav",))
    db = Database(tmp_path / "lib.db")
    window = MainWindow(LibraryService(db, auto_analyze=False))
    qtbot.addWidget(window)
    genre = window.library.create_tag("techno", "genre")

    seen = {}
    window.library.add_files = lambda paths, tag_ids=(): seen.update(
        paths=paths, tag_ids=set(tag_ids)
    )

    window.import_paths([str(tmp_path / "loose.wav")])
    assert seen["tag_ids"] == set()  # nothing checked -> untagged import

    _check_tag(window.tag_panel, genre.id)
    window.import_paths([str(tmp_path / "loose.wav")])
    assert seen["tag_ids"] == {genre.id}
    db.close()


def test_main_window_accepts_drops(qtbot, tmp_path):
    db = Database(tmp_path / "lib.db")
    window = MainWindow(LibraryService(db, auto_analyze=False))
    qtbot.addWidget(window)
    assert window.acceptDrops()
    db.close()
