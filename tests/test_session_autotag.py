"""Session-new marking and folder-as-genre/set auto-tagging."""

import numpy as np
import soundfile as sf

from keydup.db import Database
from keydup.domain import Track
from keydup.library import LibraryService
from keydup.ui.add_folder_dialog import AddFolderDialog
from keydup.ui.track_table import COL_TAGS, TrackFilterProxy, TrackTableModel


def make_folder(tmp_path, names=("a.wav", "b.wav", "c.wav")):
    sr = 22050
    for n in names:
        t = np.linspace(0, 1.0, sr, endpoint=False)
        sf.write(tmp_path / n, (0.2 * np.sin(2 * np.pi * 330 * t)).astype("float32"), sr)
    return tmp_path


def test_session_new_marks_added_tracks_and_dies_with_run(qtbot, tmp_path):
    make_folder(tmp_path)
    db = Database(tmp_path / "lib.db")
    library = LibraryService(db, auto_analyze=False)
    with qtbot.waitSignal(library.scan_finished, timeout=15000):
        library.add_folder(str(tmp_path))

    assert len(library.session_new_ids) == 3

    # rescan: nothing new on disk -> set unchanged
    with qtbot.waitSignal(library.scan_finished, timeout=15000):
        library.rescan_all()
    assert len(library.session_new_ids) == 3

    # a fresh service = a new "session": the marks are gone, tracks persist
    library2 = LibraryService(db, auto_analyze=False)
    assert library2.session_new_ids == set()
    assert len(library2.all_tracks()) == 3
    db.close()


def test_session_filter_and_label(qtbot):
    model = TrackTableModel()
    tracks = [
        Track(id=i, folder_id=1, path=f"/m/{i}.mp3", filename=f"{i}.mp3",
              status="done", tag_names=("house",) if i == 2 else ())
        for i in (1, 2, 3)
    ]
    model.set_tracks(tracks)
    model.session_new_ids = {1, 3}  # ids 1 and 3 added this session

    proxy = TrackFilterProxy()
    proxy.setSourceModel(model)

    # "New" label appears in the Tags column for session tracks
    assert model.index(0, COL_TAGS).data() == "New"
    assert model.index(1, COL_TAGS).data() == "house"   # not session-new
    assert model.index(2, COL_TAGS).data() == "New"

    proxy.set_session_new_only(True)
    visible = {model.tracks[proxy.mapToSource(proxy.index(r, 0)).row()].id
               for r in range(proxy.rowCount())}
    assert visible == {1, 3}
    proxy.set_session_new_only(False)
    assert proxy.rowCount() == 3


def test_auto_tag_genre(qtbot, tmp_path):
    make_folder(tmp_path)
    db = Database(tmp_path / "lib.db")
    library = LibraryService(db, auto_analyze=False)
    with qtbot.waitSignal(library.scan_finished, timeout=15000):
        library.add_folder(str(tmp_path), auto_tag=("genre", "trance"))

    tags = library.list_tags()
    assert [(t.name, t.kind) for t in tags] == [("trance", "genre")]
    tag_id = tags[0].id
    assert all(tag_id in t.tag_ids for t in db.all_tracks())
    db.close()


def test_auto_tag_set_gets_path_order_positions(qtbot, tmp_path):
    make_folder(tmp_path, names=("03.wav", "01.wav", "02.wav"))
    db = Database(tmp_path / "lib.db")
    library = LibraryService(db, auto_analyze=False)
    with qtbot.waitSignal(library.scan_finished, timeout=15000):
        library.add_folder(str(tmp_path), auto_tag=("set", "my set"))

    tag = library.list_tags()[0]
    assert tag.kind == "set"
    ordered_ids = db.set_track_ids_ordered(tag.id)
    names = [db.get_track(i).filename for i in ordered_ids]
    assert names == ["01.wav", "02.wav", "03.wav"]  # path-ordered, not scan-order
    db.close()


def test_add_folder_dialog_choices(qtbot):
    dialog = AddFolderDialog("/music/Deep House", None)
    qtbot.addWidget(dialog)
    assert dialog.name_edit.text() == "Deep House"   # prefilled from basename
    assert not dialog.name_edit.isEnabled()          # disabled until tagging
    assert dialog.auto_tag() is None

    dialog.genre_radio.setChecked(True)
    assert dialog.name_edit.isEnabled()
    assert dialog.auto_tag() == ("genre", "Deep House")

    dialog.set_radio.setChecked(True)
    dialog.name_edit.setText("Summer 26")
    assert dialog.auto_tag() == ("set", "Summer 26")
