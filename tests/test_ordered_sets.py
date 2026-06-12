"""Ordered set semantics and export-to-directory."""

from pathlib import Path

from keydup.db import Database
from keydup.domain import TrackStub
from keydup.export import SetExportWorker, export_names
from keydup.library import LibraryService


def _stub(path, size=1000, duration=180.0):
    return TrackStub(
        path=path, filename=path.rsplit("/", 1)[-1], artist="A", title="T",
        album=None, duration_s=duration, file_size=size, file_mtime=1.0,
    )


def make_set(tmp_path):
    db = Database(tmp_path / "t.db")
    folder = db.add_folder("/music")
    tracks = []
    for i in range(4):
        t, _ = db.upsert_scanned(folder.id, _stub(f"/music/{i}.mp3", size=1000 + i))
        tracks.append(t)
    tag = db.create_tag("gig", "set")
    for t in tracks:
        db.assign_tag(t.id, tag.id)
    return db, tag, tracks


def test_assignment_order_is_set_order(tmp_path):
    db, tag, tracks = make_set(tmp_path)
    assert db.set_track_ids_ordered(tag.id) == [t.id for t in tracks]
    positions = [db.get_track(t.id).tag_positions[tag.id] for t in tracks]
    assert positions == [1, 2, 3, 4]


def test_move_in_set(tmp_path):
    db, tag, tracks = make_set(tmp_path)
    ids = [t.id for t in tracks]
    db.move_in_set(tag.id, ids[3], -1)
    assert db.set_track_ids_ordered(tag.id) == [ids[0], ids[1], ids[3], ids[2]]
    db.move_in_set(tag.id, ids[0], +1)
    assert db.set_track_ids_ordered(tag.id) == [ids[1], ids[0], ids[3], ids[2]]
    # clamped at the edges
    db.move_in_set(tag.id, ids[1], -1)
    assert db.set_track_ids_ordered(tag.id)[0] == ids[1]
    # positions renumbered 1..n
    assert sorted(
        db.get_track(i).tag_positions[tag.id] for i in ids
    ) == [1, 2, 3, 4]


def test_unassign_then_assign_appends_at_end(tmp_path):
    db, tag, tracks = make_set(tmp_path)
    db.unassign_tag(tracks[0].id, tag.id)
    db.assign_tag(tracks[0].id, tag.id)
    assert db.set_track_ids_ordered(tag.id)[-1] == tracks[0].id


def test_export_names_padding():
    class T:
        def __init__(self, filename):
            self.filename = filename

    names = export_names([T(f"{c}.mp3") for c in "abc"])
    assert names == ["01 a.mp3", "02 b.mp3", "03 c.mp3"]


def test_export_worker_copies_in_order(qtbot, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    db = Database(tmp_path / "t.db")
    folder = db.add_folder(str(src))
    library = LibraryService(db, auto_analyze=False)
    tag = db.create_tag("gig", "set")
    for name in ("zeta.mp3", "alpha.mp3", "mid.mp3"):
        p = src / name
        p.write_bytes(b"x" * 100)
        track, _ = db.upsert_scanned(
            folder.id, _stub(str(p), size=100, duration=10.0)
        )
        db.assign_tag(track.id, tag.id)

    failures = []
    library.export_failed.connect(failures.append)

    dest = tmp_path / "out"
    with qtbot.waitSignal(
        library.export_finished, timeout=30000, raising=False
    ) as blocker:
        library.export_set(tag.id, str(dest))
    assert blocker.signal_triggered, f"export did not finish; failures: {failures}"
    assert "Exported 3 files" in blocker.args[0]
    # assignment order preserved via numbered prefixes, not alphabetical
    assert sorted(p.name for p in dest.iterdir()) == [
        "01 zeta.mp3",
        "02 alpha.mp3",
        "03 mid.mp3",
    ]
    # sources untouched
    assert sorted(p.name for p in src.iterdir()) == ["alpha.mp3", "mid.mp3", "zeta.mp3"]

    # re-export skips existing
    with qtbot.waitSignal(library.export_finished, timeout=10000) as blocker:
        library.export_set(tag.id, str(dest))
    assert "3 already there" in blocker.args[0]
    db.close()
