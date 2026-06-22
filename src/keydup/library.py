"""LibraryService: main-thread orchestrator between workers, the
database, and the UI. Owns all SQLite writes."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThreadPool, Signal

from keydup.db import Database
from keydup.domain import Folder, Tag, Track, TrackStub
from keydup.analysis.analyzer import AnalysisController, AnalysisResult
from keydup.analysis.scanner import ScanWorker


class LibraryService(QObject):
    tracks_upserted = Signal(list)      # list[Track] - new or changed rows
    tracks_removed_from_disk = Signal(list)  # list[Track] now 'missing'
    scan_progress = Signal(int, int)    # done, total
    scan_started = Signal(str)          # folder path
    scan_finished = Signal(str)         # human-readable summary
    scan_failed = Signal(str)
    analysis_started = Signal(int)      # number of tracks queued
    analysis_progress = Signal(int, int)
    analysis_finished = Signal()
    analysis_failed = Signal(str)
    tags_changed = Signal()             # tag created/deleted
    key_changes_started = Signal(int)
    key_changes_finished = Signal()
    key_changes_failed = Signal(str)
    export_progress = Signal(int, int)
    export_finished = Signal(str)
    export_failed = Signal(str)
    waveform_ready = Signal(int, object)  # track_id, np.float32 array | None

    def __init__(self, db: Database, parent: QObject | None = None,
                 auto_analyze: bool = True):
        super().__init__(parent)
        self.db = db
        self.pool = QThreadPool.globalInstance()
        self._active_scans: dict[int, ScanWorker] = {}
        self._analysis: AnalysisController | None = None
        self.auto_analyze = auto_analyze
        # Tracks added during THIS run. In-memory by design: it dies with
        # the process, which is exactly "removed after the project closes".
        self.session_new_ids: set[int] = set()
        # folder_id -> (kind, name): tag to apply once the folder finishes
        # its first scan (from "add folder as genre/set")
        self._pending_auto_tag: dict[int, tuple[str, str]] = {}

    # -- scanning ----------------------------------------------------------

    def add_folder(self, path: str,
                   auto_tag: tuple[str, str] | None = None) -> Folder:
        folder = self.db.add_folder(path)
        if auto_tag is not None:
            self._pending_auto_tag[folder.id] = auto_tag
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

    def add_files(self, paths: list[str]) -> list[Track]:
        """Add individual audio files (e.g. dropped from a file manager).
        Their parent directories are registered as folders so the rows
        have a home and a later Rescan can pick up siblings."""
        from pathlib import Path

        from keydup.analysis.scanner import read_stub

        changed: list[Track] = []
        by_parent: dict[str, list[Path]] = {}
        for p in paths:
            path = Path(p)
            by_parent.setdefault(str(path.parent), []).append(path)
        for parent, files in by_parent.items():
            folder = self.db.add_folder(parent)
            for fp in files:
                try:
                    stub = read_stub(fp)
                except OSError:
                    continue
                track, change = self.db.upsert_scanned(folder.id, stub)
                if change == "new":
                    self.session_new_ids.add(track.id)
                if change != "unchanged":
                    changed.append(track)
        if changed:
            self.tracks_upserted.emit(changed)
        if self.auto_analyze:
            self.start_analysis()
        return changed

    def cancel_scans(self) -> None:
        for worker in self._active_scans.values():
            worker.cancel.set()

    def _on_scan_batch(self, folder_id: int, stubs: list[TrackStub]) -> None:
        changed: list[Track] = []
        for stub in stubs:
            track, change = self.db.upsert_scanned(folder_id, stub)
            if change == "new":
                self.session_new_ids.add(track.id)
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
        self._apply_auto_tag(folder_id)
        pending = len(self.db.pending_track_ids())
        self.scan_finished.emit(
            f"Scan complete - {len(found_paths)} files, {pending} awaiting analysis"
        )
        if self.auto_analyze and not self._active_scans:
            self.start_analysis()

    def _apply_auto_tag(self, folder_id: int) -> None:
        pending = self._pending_auto_tag.pop(folder_id, None)
        if pending is None:
            return
        kind, name = pending
        tag = self.db.create_tag(name, kind)
        # path-ordered so a 'set' gets a sensible initial track order
        changed = [self.db.assign_tag(tid, tag.id)
                   for tid in self.db.folder_track_ids(folder_id)]
        self.tags_changed.emit()
        if changed:
            self.tracks_upserted.emit(changed)

    def _on_scan_failed(self, folder_id: int, message: str) -> None:
        self._active_scans.pop(folder_id, None)
        self.scan_failed.emit(message)

    # -- analysis ------------------------------------------------------------

    def start_analysis(self) -> None:
        if self._analysis is not None and self._analysis.isRunning():
            return
        ids = self.db.pending_track_ids()
        jobs = []
        for track_id in ids:
            track = self.db.get_track(track_id)
            jobs.append((track.id, track.path))
        if not jobs:
            return
        controller = AnalysisController(jobs)
        controller.result_ready.connect(self._on_analysis_result)
        controller.progress.connect(self.analysis_progress)
        controller.finished_ok.connect(self._on_analysis_finished)
        controller.failed.connect(self.analysis_failed)
        self._analysis = controller
        self.analysis_started.emit(len(jobs))
        controller.start()

    def cancel_analysis(self) -> None:
        if self._analysis is not None:
            self._analysis.cancel.set()

    def reanalyze(self, track_ids: list[int]) -> None:
        tracks = self.db.reset_for_reanalysis(track_ids)
        self.tracks_upserted.emit(tracks)
        self.start_analysis()

    def _on_analysis_result(self, result: AnalysisResult) -> None:
        if result.error is not None:
            track = self.db.set_status(result.track_id, "error", result.error)
        else:
            track = self.db.save_analysis(
                result.track_id,
                result.key_camelot,
                result.key_confidence,
                result.bpm,
                result.bpm_confidence,
                result.bpm_source,
            )
        self.tracks_upserted.emit([track])

    # -- on-demand key-change detection --------------------------------------

    def key_segments(self, track_id: int) -> list:
        return self.db.load_key_segments(track_id)

    def detect_key_changes(self, track_ids: list[int]) -> None:
        """Run the windowed key-segment pass on demand (it is NOT run during
        normal analysis - too unreliable to auto-flag, see the analyzer)."""
        from keydup.analysis.keychange import KeyChangeWorker

        jobs = [(t.id, t.path) for t in (self.db.get_track(i) for i in track_ids)]
        if not jobs:
            return
        worker = KeyChangeWorker(jobs)
        worker.signals.result.connect(self._on_key_changes)
        worker.signals.finished.connect(self.key_changes_finished)
        worker.signals.failed.connect(self.key_changes_failed)
        self.key_changes_started.emit(len(jobs))
        self.pool.start(worker)

    def _on_key_changes(self, track_id: int, segments: list) -> None:
        if segments and len({s["key"] for s in segments}) > 1:
            track = self.db.save_key_segments(track_id, segments)
        else:
            track = self.db.clear_key_segments(track_id)  # single key: clear any prior
        self.tracks_upserted.emit([track])

    def _on_analysis_finished(self) -> None:
        if self._analysis is not None:
            # run() is returning as this queued slot fires; wait for the
            # thread to fully exit before dropping the last reference,
            # otherwise Qt aborts with "Destroyed while thread running".
            self._analysis.wait(10_000)
            self._analysis = None
        self.analysis_finished.emit()

    def shutdown(self) -> None:
        """Stop all background work and block until threads exit."""
        self.cancel_scans()
        self.cancel_analysis()
        if self._analysis is not None:
            self._analysis.wait(30_000)
            self._analysis = None
        self.pool.waitForDone(10_000)

    # -- tags ----------------------------------------------------------------

    def create_tag(self, name: str, kind: str) -> Tag:
        tag = self.db.create_tag(name, kind)
        self.tags_changed.emit()
        return tag

    def delete_tag(self, tag_id: int) -> None:
        self.db.delete_tag(tag_id)
        self.tags_changed.emit()
        # assignments cascade away; refresh every row's tag display
        self.tracks_upserted.emit(self.db.all_tracks())

    def list_tags(self) -> list[Tag]:
        return self.db.list_tags()

    def set_track_tag(self, track_id: int, tag_id: int, assigned: bool) -> None:
        if assigned:
            track = self.db.assign_tag(track_id, tag_id)
        else:
            track = self.db.unassign_tag(track_id, tag_id)
        self.tracks_upserted.emit([track])

    # -- ordered sets ---------------------------------------------------------

    def move_in_set(self, tag_id: int, track_id: int, delta: int) -> None:
        changed = self.db.move_in_set(tag_id, track_id, delta)
        if changed:
            self.tracks_upserted.emit(changed)

    def reorder_set(self, tag_id: int, moved_ids: list[int], before_id: int | None) -> None:
        """Move moved_ids (kept in their relative order) so they sit just
        before before_id in the set order, or at the end when None."""
        order = self.db.set_track_ids_ordered(tag_id)
        moved = [i for i in order if i in set(moved_ids)]
        rest = [i for i in order if i not in set(moved_ids)]
        at = rest.index(before_id) if before_id in rest else len(rest)
        changed = self.db.renumber_set(tag_id, rest[:at] + moved + rest[at:])
        if changed:
            self.tracks_upserted.emit(changed)

    def set_tracks_ordered(self, tag_id: int) -> list[Track]:
        return [self.db.get_track(i) for i in self.db.set_track_ids_ordered(tag_id)]

    def export_set(self, tag_id: int, dest_dir: str) -> None:
        from keydup.export import SetExportWorker

        worker = SetExportWorker(self.set_tracks_ordered(tag_id), dest_dir)
        worker.signals.progress.connect(self.export_progress)
        worker.signals.finished.connect(self.export_finished)
        worker.signals.failed.connect(self.export_failed)
        self.pool.start(worker)

    # -- waveforms ------------------------------------------------------------

    def request_waveform(self, track: Track) -> None:
        import numpy as np

        cached = self.db.load_waveform(track.id)
        if cached is not None:
            self.waveform_ready.emit(
                track.id, np.frombuffer(cached, dtype=np.float32)
            )
            return
        from keydup.analysis.waveform import WaveformWorker

        worker = WaveformWorker(track.id, track.path)
        worker.signals.done.connect(self._on_waveform_done)
        worker.signals.failed.connect(
            lambda track_id, _msg: self.waveform_ready.emit(track_id, None)
        )
        self.pool.start(worker)

    def _on_waveform_done(self, track_id: int, peaks) -> None:
        self.db.save_waveform(track_id, peaks.tobytes())
        self.waveform_ready.emit(track_id, peaks)

    # -- queries -----------------------------------------------------------

    def all_tracks(self) -> list[Track]:
        return self.db.all_tracks()
