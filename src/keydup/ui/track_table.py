"""Track table: QAbstractTableModel over the in-memory track list, with
a QSortFilterProxyModel composing text / key / BPM / tag filters."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
)

from keydup.domain import Track

STATUS_GLYPHS = {
    "pending": "…",     # …
    "analyzing": "◔",   # ◔
    "done": "",
    "error": "⚠",       # ⚠
    "missing": "✗",     # ✗
}

COLUMNS = ("", "#", "Artist", "Title", "Key", "BPM", "Length", "Tags", "Filename")
(
    COL_STATUS,
    COL_POS,
    COL_ARTIST,
    COL_TITLE,
    COL_KEY,
    COL_BPM,
    COL_LENGTH,
    COL_TAGS,
    COL_FILENAME,
) = range(9)


def _fmt_duration(seconds: float | None) -> str:
    if not seconds:
        return ""
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


class TrackTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracks: list[Track] = []
        self._row_by_id: dict[int, int] = {}
        # when viewing a single 'set' tag, the # column shows the track's
        # position within that set
        self.active_set_id: int | None = None

    def set_active_set(self, tag_id: int | None) -> None:
        if tag_id != self.active_set_id:
            self.active_set_id = tag_id
            if self.tracks:
                self.dataChanged.emit(
                    self.index(0, COL_POS),
                    self.index(len(self.tracks) - 1, COL_POS),
                )

    # -- Qt model API ------------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.tracks)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        track = self.tracks[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return self._display(track, col)
        if role == Qt.UserRole:
            return self._sort_value(track, col)
        if role == Qt.ToolTipRole:
            if col == COL_STATUS and track.error:
                return track.error
            return track.path
        if role == Qt.TextAlignmentRole and col in (COL_POS, COL_KEY, COL_BPM, COL_LENGTH):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def _display(self, track: Track, col: int):
        if col == COL_STATUS:
            return STATUS_GLYPHS.get(track.status, "")
        if col == COL_POS:
            if self.active_set_id is None:
                return ""
            position = track.tag_positions.get(self.active_set_id)
            return str(position) if position else ""
        if col == COL_ARTIST:
            return track.artist or ""
        if col == COL_TITLE:
            return track.title or ""
        if col == COL_KEY:
            return track.key_camelot or ""
        if col == COL_BPM:
            return str(track.bpm) if track.bpm else ""
        if col == COL_LENGTH:
            return _fmt_duration(track.duration_s)
        if col == COL_TAGS:
            return ", ".join(track.tag_names)
        if col == COL_FILENAME:
            return track.filename
        return ""

    def _sort_value(self, track: Track, col: int):
        if col == COL_POS:
            if self.active_set_id is None:
                return 0
            return track.tag_positions.get(self.active_set_id) or 10**9
        if col == COL_KEY and track.key_camelot:
            # sort 1A,1B,2A... numerically around the wheel
            return int(track.key_camelot[:-1]) * 2 + (track.key_camelot[-1] == "B")
        if col == COL_BPM:
            return track.bpm or 0
        if col == COL_LENGTH:
            return track.duration_s or 0.0
        if col == COL_STATUS:
            return track.status
        return self._display(track, col).lower()

    # -- mutation ----------------------------------------------------------

    def set_tracks(self, tracks: list[Track]) -> None:
        self.beginResetModel()
        self.tracks = list(tracks)
        self._row_by_id = {t.id: i for i, t in enumerate(self.tracks)}
        self.endResetModel()

    def upsert_tracks(self, tracks: list[Track]) -> None:
        new = [t for t in tracks if t.id not in self._row_by_id]
        for track in tracks:
            row = self._row_by_id.get(track.id)
            if row is not None:
                self.tracks[row] = track
                self.dataChanged.emit(
                    self.index(row, 0), self.index(row, len(COLUMNS) - 1)
                )
        if new:
            start = len(self.tracks)
            self.beginInsertRows(QModelIndex(), start, start + len(new) - 1)
            for track in new:
                self._row_by_id[track.id] = len(self.tracks)
                self.tracks.append(track)
            self.endInsertRows()

    def track_at(self, row: int) -> Track:
        return self.tracks[row]


class TrackFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(Qt.UserRole)
        self.setDynamicSortFilter(True)
        self._text = ""
        self._keys: frozenset[str] = frozenset()
        self._bpm_range: tuple[int, int] | None = None
        self._tag_ids: frozenset[int] = frozenset()

    # Qt 6.10 replaces invalidateFilter() with begin/endFilterChange()
    def _begin(self) -> None:
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()

    def _end(self) -> None:
        if hasattr(self, "endFilterChange"):
            self.endFilterChange()
        else:
            self.invalidateFilter()

    def set_text(self, text: str) -> None:
        self._begin()
        self._text = text.strip().lower()
        self._end()

    def set_keys(self, keys: frozenset[str]) -> None:
        self._begin()
        self._keys = keys
        self._end()

    def set_bpm_range(self, lo: int | None, hi: int | None) -> None:
        self._begin()
        self._bpm_range = (lo, hi) if lo is not None else None
        self._end()

    def set_tag_ids(self, tag_ids: frozenset[int]) -> None:
        self._begin()
        self._tag_ids = tag_ids
        self._end()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        track: Track = self.sourceModel().tracks[source_row]
        if self._text:
            haystack = " ".join(
                filter(None, (track.artist, track.title, track.filename))
            ).lower()
            if self._text not in haystack:
                return False
        if self._keys and (track.key_camelot or "") not in self._keys:
            return False
        if self._bpm_range is not None:
            lo, hi = self._bpm_range
            if track.bpm is None or not (lo <= track.bpm <= hi):
                return False
        if self._tag_ids and not (self._tag_ids & track.tag_ids):
            return False
        return True
