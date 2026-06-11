"""LibraryService: main-thread orchestrator between workers, the
database, and the UI. Owns all SQLite writes."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThreadPool, Signal

from keydup.db import Database
from keydup.domain import Folder, Track, TrackStub
from keydup.analysis.scanner import ScanWorker


class LibraryService(QObject):
    tracks_upserted = Signal(list)      # list[Track] - new or changed rows
    tracks_removed_from_disk = Signal(list)  # list[Track] now 'missing'
    scan_progress = Signal(int, int)    # done, total
    scan_started = Signal(str)          # folder path
    scan_finished = Signal(str)         # human-readable summary
    scan_failed = Signal(str)

    def __init__(self, db: Database, parent: QObject | None = None):
        super().__init__(parent)
        self.db = db
        self.pool = QThreadPool.globalInstance()
        self._active_scans: dict[int, ScanWorker] = {}

    # -- scanning ----------------------------------------------------------

    def add_folder(self, path: str) -> Folder:
        folder = self.db.add_folder(path)
        self.scan_folder(folder)
        return folder

    def scan_folder(self, folder: Folder) -> None:
        if folder.id in self._active_scans:
            return
        worker = ScanWorker(folder.id, folder.path)
        worker.signals.batch.connect(self._on_scan_batch)
        worker.signals.progress.connect(self.scan_progress)
        worker.signals.finished.connect(self._on_scan_finished)
        worker.signals.failed.connect(self._on_scan_failed)
        self._active_scans[folder.id] = worker
        self.scan_started.emit(folder.path)
        self.pool.start(worker)

    def rescan_all(self) -> None:
        for folder in self.db.list_folders():
            self.scan_folder(folder)

    def cancel_scans(self) -> None:
        for worker in self._active_scans.values():
            worker.cancel.set()

    def _on_scan_batch(self, folder_id: int, stubs: list[TrackStub]) -> None:
        changed: list[Track] = []
        for stub in stubs:
            track, change = self.db.upsert_scanned(folder_id, stub)
            if change != "unchanged":
                changed.append(track)
        if changed:
            self.tracks_upserted.emit(changed)

    def _on_scan_finished(self, folder_id: int, found_paths: set) -> None:
        gone = self.db.mark_missing(folder_id, found_paths)
        if gone:
            self.tracks_removed_from_disk.emit(gone)
        self.db.touch_folder_scanned(folder_id)
        self._active_scans.pop(folder_id, None)
        pending = len(self.db.pending_track_ids())
        self.scan_finished.emit(
            f"Scan complete - {len(found_paths)} files, {pending} awaiting analysis"
        )

    def _on_scan_failed(self, folder_id: int, message: str) -> None:
        self._active_scans.pop(folder_id, None)
        self.scan_failed.emit(message)

    # -- queries -----------------------------------------------------------

    def all_tracks(self) -> list[Track]:
        return self.db.all_tracks()
