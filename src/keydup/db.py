"""SQLite persistence. All access happens on the main (GUI) thread;
workers hand results back via signals, so no cross-thread connections."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from keydup.domain import CURRENT_ANALYSIS_VERSION, Folder, Tag, Track, TrackStub

SCHEMA_VERSION = 3

_SCHEMA = """
CREATE TABLE folders (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    last_scanned_at TEXT
);

CREATE TABLE tracks (
    id INTEGER PRIMARY KEY,
    folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    artist TEXT, title TEXT, album TEXT,
    duration_s REAL,
    file_size INTEGER NOT NULL,
    file_mtime REAL NOT NULL,
    key_camelot TEXT,
    key_confidence REAL,
    bpm INTEGER,
    bpm_confidence REAL,
    bpm_source TEXT,
    analysis_version INTEGER,
    analyzed_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','analyzing','done','error','missing')),
    error TEXT
);
CREATE INDEX idx_tracks_key ON tracks(key_camelot);
CREATE INDEX idx_tracks_bpm ON tracks(bpm);
CREATE INDEX idx_tracks_status ON tracks(status);
CREATE INDEX idx_tracks_folder ON tracks(folder_id);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'genre' CHECK (kind IN ('genre','set')),
    color TEXT,
    UNIQUE (name, kind)
);

CREATE TABLE track_tags (
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    position INTEGER,
    PRIMARY KEY (track_id, tag_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            self.conn.executescript(_SCHEMA)
        if version < 2:
            self.conn.executescript(
                """CREATE TABLE IF NOT EXISTS waveforms (
                       track_id INTEGER PRIMARY KEY
                           REFERENCES tracks(id) ON DELETE CASCADE,
                       peaks BLOB NOT NULL
                   );"""
            )
        if version < 3:
            self.conn.executescript(
                """CREATE TABLE IF NOT EXISTS track_keys (
                       track_id INTEGER NOT NULL
                           REFERENCES tracks(id) ON DELETE CASCADE,
                       seq INTEGER NOT NULL,
                       start_s REAL NOT NULL,
                       end_s REAL NOT NULL,
                       key_camelot TEXT NOT NULL,
                       confidence REAL,
                       PRIMARY KEY (track_id, seq)
                   );"""
            )
            cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(tracks)")}
            if "key_secondary" not in cols:
                self.conn.execute("ALTER TABLE tracks ADD COLUMN key_secondary TEXT")
        if version < SCHEMA_VERSION:
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- folders ----------------------------------------------------------

    def add_folder(self, path: str) -> Folder:
        cur = self.conn.execute(
            "INSERT INTO folders (path) VALUES (?) ON CONFLICT(path) DO NOTHING", (path,)
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM folders WHERE path = ?", (path,)).fetchone()
        return Folder(id=row["id"], path=row["path"], last_scanned_at=row["last_scanned_at"])

    def list_folders(self) -> list[Folder]:
        rows = self.conn.execute("SELECT * FROM folders ORDER BY path").fetchall()
        return [Folder(id=r["id"], path=r["path"], last_scanned_at=r["last_scanned_at"]) for r in rows]

    def remove_folder(self, folder_id: int) -> None:
        self.conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        self.conn.commit()

    def touch_folder_scanned(self, folder_id: int) -> None:
        self.conn.execute(
            "UPDATE folders SET last_scanned_at = ? WHERE id = ?", (_now(), folder_id)
        )
        self.conn.commit()

    # -- scanning ---------------------------------------------------------

    def upsert_scanned(self, folder_id: int, stub: TrackStub) -> tuple[Track, str]:
        """Insert or refresh a track found by the fast scan pass.

        Returns (track, change) where change is 'new', 'updated',
        'rematched', or 'unchanged'. File-content changes (mtime/size) and
        stale analysis versions reset status to 'pending'.
        """
        row = self.conn.execute("SELECT * FROM tracks WHERE path = ?", (stub.path,)).fetchone()
        if row is None:
            rematched = self._rematch_missing(folder_id, stub)
            if rematched is not None:
                return rematched, "rematched"
            cur = self.conn.execute(
                """INSERT INTO tracks (folder_id, path, filename, artist, title, album,
                                       duration_s, file_size, file_mtime, status)
                   VALUES (?,?,?,?,?,?,?,?,?, 'pending')""",
                (folder_id, stub.path, stub.filename, stub.artist, stub.title,
                 stub.album, stub.duration_s, stub.file_size, stub.file_mtime),
            )
            self.conn.commit()
            return self.get_track(cur.lastrowid), "new"

        changed = (row["file_mtime"], row["file_size"]) != (stub.file_mtime, stub.file_size)
        stale = (
            row["status"] == "done"
            and (row["analysis_version"] or 0) < CURRENT_ANALYSIS_VERSION
        )
        was_missing = row["status"] == "missing"
        if changed:
            self.conn.execute(
                """UPDATE tracks SET filename=?, artist=?, title=?, album=?, duration_s=?,
                       file_size=?, file_mtime=?, status='pending', error=NULL
                   WHERE id=?""",
                (stub.filename, stub.artist, stub.title, stub.album, stub.duration_s,
                 stub.file_size, stub.file_mtime, row["id"]),
            )
            self.conn.commit()
            return self.get_track(row["id"]), "updated"
        if stale or was_missing:
            new_status = "pending" if (stale or row["analysis_version"] is None) else "done"
            if was_missing and not stale and row["analyzed_at"] is not None:
                new_status = "done"
            self.conn.execute(
                "UPDATE tracks SET status=?, error=NULL WHERE id=?", (new_status, row["id"])
            )
            self.conn.commit()
            return self.get_track(row["id"]), "updated"
        return self.get_track(row["id"]), "unchanged"

    def _rematch_missing(self, folder_id: int, stub: TrackStub) -> Track | None:
        """Fingerprint re-match: a 'missing' row with the same size and
        duration is the same file renamed (e.g. by the keypipe CLI's
        filename tagging). Rebind it to the new path so tags and analysis
        survive."""
        if stub.duration_s is None:
            return None
        row = self.conn.execute(
            """SELECT id FROM tracks
               WHERE status='missing' AND file_size=? AND duration_s IS NOT NULL
                 AND ABS(duration_s - ?) < 0.5
               LIMIT 1""",
            (stub.file_size, stub.duration_s),
        ).fetchone()
        if row is None:
            return None
        restored = "done"
        old = self.conn.execute(
            "SELECT analyzed_at, analysis_version FROM tracks WHERE id=?", (row["id"],)
        ).fetchone()
        if old["analyzed_at"] is None or (old["analysis_version"] or 0) < CURRENT_ANALYSIS_VERSION:
            restored = "pending"
        self.conn.execute(
            """UPDATE tracks SET folder_id=?, path=?, filename=?, artist=?, title=?, album=?,
                   file_mtime=?, status=?, error=NULL
               WHERE id=?""",
            (folder_id, stub.path, stub.filename, stub.artist, stub.title, stub.album,
             stub.file_mtime, restored, row["id"]),
        )
        self.conn.commit()
        return self.get_track(row["id"])

    def folder_track_ids(self, folder_id: int) -> list[int]:
        """Track ids in a folder, path-ordered (set order on auto-tag)."""
        rows = self.conn.execute(
            "SELECT id FROM tracks WHERE folder_id=? AND status != 'missing' ORDER BY path",
            (folder_id,),
        ).fetchall()
        return [r["id"] for r in rows]

    def mark_missing(self, folder_id: int, present_paths: set[str]) -> list[Track]:
        rows = self.conn.execute(
            "SELECT id, path FROM tracks WHERE folder_id = ? AND status != 'missing'",
            (folder_id,),
        ).fetchall()
        gone = [r["id"] for r in rows if r["path"] not in present_paths]
        if gone:
            self.conn.executemany(
                "UPDATE tracks SET status='missing' WHERE id=?", [(i,) for i in gone]
            )
            self.conn.commit()
        return [self.get_track(i) for i in gone]

    # -- analysis ---------------------------------------------------------

    def pending_track_ids(self) -> list[int]:
        rows = self.conn.execute(
            "SELECT id FROM tracks WHERE status IN ('pending','analyzing') ORDER BY id"
        ).fetchall()
        return [r["id"] for r in rows]

    def set_status(self, track_id: int, status: str, error: str | None = None) -> Track:
        self.conn.execute(
            "UPDATE tracks SET status=?, error=? WHERE id=?", (status, error, track_id)
        )
        self.conn.commit()
        return self.get_track(track_id)

    def save_analysis(
        self,
        track_id: int,
        key_camelot: str | None,
        key_confidence: float | None,
        bpm: int | None,
        bpm_confidence: float | None,
        bpm_source: str | None,
    ) -> Track:
        self.conn.execute(
            """UPDATE tracks SET key_camelot=?, key_confidence=?, bpm=?, bpm_confidence=?,
                   bpm_source=?, analysis_version=?, analyzed_at=?, status='done', error=NULL
               WHERE id=?""",
            (key_camelot, key_confidence, bpm, bpm_confidence, bpm_source,
             CURRENT_ANALYSIS_VERSION, _now(), track_id),
        )
        self.conn.commit()
        return self.get_track(track_id)

    def reset_for_reanalysis(self, track_ids: list[int]) -> list[Track]:
        self.conn.executemany(
            "UPDATE tracks SET status='pending', error=NULL WHERE id=?",
            [(i,) for i in track_ids],
        )
        self.conn.commit()
        return [self.get_track(i) for i in track_ids]

    # -- tracks -----------------------------------------------------------

    _TRACK_QUERY = """
        SELECT t.*,
               COALESCE(GROUP_CONCAT(g.id || ':' || COALESCE(tt.position, 0)), '') AS tag_refs,
               COALESCE(GROUP_CONCAT(g.name, CHAR(31)), '') AS tag_names
        FROM tracks t
        LEFT JOIN track_tags tt ON tt.track_id = t.id
        LEFT JOIN tags g ON g.id = tt.tag_id
    """

    def _row_to_track(self, row: sqlite3.Row) -> Track:
        tag_ids: set[int] = set()
        tag_positions: dict[int, int] = {}
        for ref in row["tag_refs"].split(","):
            if not ref:
                continue
            tag_id, position = ref.split(":")
            tag_ids.add(int(tag_id))
            if int(position):
                tag_positions[int(tag_id)] = int(position)
        tag_names = tuple(x for x in row["tag_names"].split(chr(31)) if x)
        return Track(
            id=row["id"], folder_id=row["folder_id"], path=row["path"],
            filename=row["filename"], artist=row["artist"], title=row["title"],
            album=row["album"], duration_s=row["duration_s"],
            file_size=row["file_size"], file_mtime=row["file_mtime"],
            key_camelot=row["key_camelot"], key_confidence=row["key_confidence"],
            key_secondary=row["key_secondary"],
            bpm=row["bpm"], bpm_confidence=row["bpm_confidence"],
            bpm_source=row["bpm_source"], analysis_version=row["analysis_version"],
            analyzed_at=row["analyzed_at"], status=row["status"], error=row["error"],
            tag_ids=frozenset(tag_ids), tag_names=tag_names,
            tag_positions=tag_positions,
        )

    def get_track(self, track_id: int) -> Track:
        row = self.conn.execute(
            self._TRACK_QUERY + " WHERE t.id = ? GROUP BY t.id", (track_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no track with id {track_id}")
        return self._row_to_track(row)

    def all_tracks(self) -> list[Track]:
        rows = self.conn.execute(self._TRACK_QUERY + " GROUP BY t.id ORDER BY t.id").fetchall()
        return [self._row_to_track(r) for r in rows]

    # -- waveforms ----------------------------------------------------------

    def save_waveform(self, track_id: int, peaks: bytes) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO waveforms (track_id, peaks) VALUES (?,?)",
            (track_id, peaks),
        )
        self.conn.commit()

    def load_waveform(self, track_id: int) -> bytes | None:
        row = self.conn.execute(
            "SELECT peaks FROM waveforms WHERE track_id=?", (track_id,)
        ).fetchone()
        return row["peaks"] if row else None

    # -- key segments -------------------------------------------------------

    def save_key_segments(self, track_id: int, segments: list) -> Track:
        """Replace a track's key segments and recompute its secondary key
        (the longest segment whose key differs from the primary)."""
        self.conn.execute("DELETE FROM track_keys WHERE track_id=?", (track_id,))
        self.conn.executemany(
            """INSERT INTO track_keys (track_id, seq, start_s, end_s, key_camelot, confidence)
               VALUES (?,?,?,?,?,?)""",
            [(track_id, i, s["start_s"], s["end_s"], s["key"], s.get("confidence"))
             for i, s in enumerate(segments)],
        )
        primary = self.conn.execute(
            "SELECT key_camelot FROM tracks WHERE id=?", (track_id,)
        ).fetchone()["key_camelot"]
        duration_by_key: dict[str, float] = {}
        for s in segments:
            if s["key"] != primary:
                duration_by_key[s["key"]] = (
                    duration_by_key.get(s["key"], 0.0) + (s["end_s"] - s["start_s"])
                )
        secondary = max(duration_by_key, key=duration_by_key.get) if duration_by_key else None
        self.conn.execute(
            "UPDATE tracks SET key_secondary=? WHERE id=?", (secondary, track_id)
        )
        self.conn.commit()
        return self.get_track(track_id)

    def clear_key_segments(self, track_id: int) -> Track:
        self.conn.execute("DELETE FROM track_keys WHERE track_id=?", (track_id,))
        self.conn.execute("UPDATE tracks SET key_secondary=NULL WHERE id=?", (track_id,))
        self.conn.commit()
        return self.get_track(track_id)

    def load_key_segments(self, track_id: int) -> list:
        rows = self.conn.execute(
            """SELECT start_s, end_s, key_camelot, confidence FROM track_keys
               WHERE track_id=? ORDER BY seq""",
            (track_id,),
        ).fetchall()
        return [
            {"start_s": r["start_s"], "end_s": r["end_s"],
             "key": r["key_camelot"], "confidence": r["confidence"]}
            for r in rows
        ]

    # -- tags -------------------------------------------------------------

    def create_tag(self, name: str, kind: str, color: str | None = None) -> Tag:
        self.conn.execute(
            "INSERT INTO tags (name, kind, color) VALUES (?,?,?) ON CONFLICT(name, kind) DO NOTHING",
            (name, kind, color),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM tags WHERE name=? AND kind=?", (name, kind)
        ).fetchone()
        return Tag(id=row["id"], name=row["name"], kind=row["kind"], color=row["color"])

    def list_tags(self) -> list[Tag]:
        rows = self.conn.execute("SELECT * FROM tags ORDER BY kind, name").fetchall()
        return [Tag(id=r["id"], name=r["name"], kind=r["kind"], color=r["color"]) for r in rows]

    def delete_tag(self, tag_id: int) -> None:
        self.conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))
        self.conn.commit()

    def assign_tag(self, track_id: int, tag_id: int) -> Track:
        # assignment order is set order: append at the end
        self.conn.execute(
            """INSERT OR IGNORE INTO track_tags (track_id, tag_id, position)
               VALUES (?, ?, (SELECT COALESCE(MAX(position), 0) + 1
                              FROM track_tags WHERE tag_id = ?))""",
            (track_id, tag_id, tag_id),
        )
        self.conn.commit()
        return self.get_track(track_id)

    def unassign_tag(self, track_id: int, tag_id: int) -> Track:
        self.conn.execute(
            "DELETE FROM track_tags WHERE track_id=? AND tag_id=?", (track_id, tag_id)
        )
        self.conn.commit()
        return self.get_track(track_id)

    # -- ordered sets -------------------------------------------------------

    def set_track_ids_ordered(self, tag_id: int) -> list[int]:
        rows = self.conn.execute(
            """SELECT track_id FROM track_tags
               WHERE tag_id = ? ORDER BY position, track_id""",
            (tag_id,),
        ).fetchall()
        return [r["track_id"] for r in rows]

    def renumber_set(self, tag_id: int, ordered_track_ids: list[int]) -> list[Track]:
        """Rewrite positions 1..n in the given order; returns the tracks."""
        self.conn.executemany(
            "UPDATE track_tags SET position=? WHERE tag_id=? AND track_id=?",
            [(i, tag_id, tid) for i, tid in enumerate(ordered_track_ids, start=1)],
        )
        self.conn.commit()
        return [self.get_track(tid) for tid in ordered_track_ids]

    def move_in_set(self, tag_id: int, track_id: int, delta: int) -> list[Track]:
        """Move a track up (delta=-1) or down (+1) in a set's order.
        Returns all tracks in the set (positions are renumbered)."""
        order = self.set_track_ids_ordered(tag_id)
        if track_id not in order:
            return []
        i = order.index(track_id)
        j = max(0, min(len(order) - 1, i + delta))
        order.insert(j, order.pop(i))
        return self.renumber_set(tag_id, order)
