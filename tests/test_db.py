from keydup.db import Database
from keydup.domain import CURRENT_ANALYSIS_VERSION, TrackStub


def _stub(path="/music/a.mp3", size=1000, mtime=1.0, duration=180.0):
    return TrackStub(
        path=path, filename=path.rsplit("/", 1)[-1], artist="A", title="T",
        album=None, duration_s=duration, file_size=size, file_mtime=mtime,
    )


def make_db(tmp_path):
    return Database(tmp_path / "test.db")


def test_insert_and_unchanged(tmp_path):
    db = make_db(tmp_path)
    folder = db.add_folder("/music")
    track, change = db.upsert_scanned(folder.id, _stub())
    assert change == "new" and track.status == "pending"
    _, change = db.upsert_scanned(folder.id, _stub())
    assert change == "unchanged"


def test_mtime_change_resets_analysis(tmp_path):
    db = make_db(tmp_path)
    folder = db.add_folder("/music")
    track, _ = db.upsert_scanned(folder.id, _stub())
    db.save_analysis(track.id, "8A", 0.9, 128, 0.8, "essentia")
    assert db.get_track(track.id).status == "done"
    _, change = db.upsert_scanned(folder.id, _stub(mtime=2.0))
    assert change == "updated"
    assert db.get_track(track.id).status == "pending"


def test_missing_and_fingerprint_rematch(tmp_path):
    db = make_db(tmp_path)
    folder = db.add_folder("/music")
    track, _ = db.upsert_scanned(folder.id, _stub())
    db.save_analysis(track.id, "8A", 0.9, 128, 0.8, "essentia")
    tag = db.create_tag("house", "genre")
    db.assign_tag(track.id, tag.id)

    # file vanishes (e.g. CLI renamed it)
    gone = db.mark_missing(folder.id, set())
    assert [t.id for t in gone] == [track.id]
    assert db.get_track(track.id).status == "missing"

    # same size+duration appears under a new name -> rebind, keep tags+analysis
    renamed = _stub(path="/music/a - 8A - 128.mp3")
    rebound, change = db.upsert_scanned(folder.id, renamed)
    assert change == "rematched"
    assert rebound.id == track.id
    assert rebound.path == "/music/a - 8A - 128.mp3"
    assert rebound.key_camelot == "8A"
    assert rebound.tag_names == ("house",)
    assert rebound.status == "done"


def test_stale_analysis_version_requeues(tmp_path):
    db = make_db(tmp_path)
    folder = db.add_folder("/music")
    track, _ = db.upsert_scanned(folder.id, _stub())
    db.save_analysis(track.id, "8A", 0.9, 128, 0.8, "essentia")
    db.conn.execute(
        "UPDATE tracks SET analysis_version = ? WHERE id = ?",
        (CURRENT_ANALYSIS_VERSION - 1, track.id),
    )
    db.conn.commit()
    _, change = db.upsert_scanned(folder.id, _stub())
    assert change == "updated"
    assert db.get_track(track.id).status == "pending"


def test_pending_ids_and_reset(tmp_path):
    db = make_db(tmp_path)
    folder = db.add_folder("/music")
    t1, _ = db.upsert_scanned(folder.id, _stub("/music/a.mp3"))
    t2, _ = db.upsert_scanned(folder.id, _stub("/music/b.mp3", size=2000))
    assert db.pending_track_ids() == [t1.id, t2.id]
    db.save_analysis(t1.id, "8A", 0.9, 128, 0.8, "essentia")
    assert db.pending_track_ids() == [t2.id]
    db.reset_for_reanalysis([t1.id])
    assert db.pending_track_ids() == [t1.id, t2.id]
