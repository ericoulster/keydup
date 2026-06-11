"""Fast scan pass: walk a folder, read file metadata with mutagen.

No ML here - this populates the table in seconds; key/BPM analysis runs
separately (analysis/analyzer.py). Runs on QThreadPool; results are
emitted in batches and written to SQLite on the main thread."""

from __future__ import annotations

import threading
from pathlib import Path

import mutagen
from PySide6.QtCore import QObject, QRunnable, Signal

from keypipe.utils import find_audio_files

from keydup.domain import TrackStub

BATCH_SIZE = 100


def read_stub(path: Path) -> TrackStub:
    stat = path.stat()
    artist = title = album = None
    duration = None
    try:
        audio = mutagen.File(path, easy=True)
    except Exception:
        audio = None
    if audio is not None:
        if audio.tags is not None:
            artist = (audio.tags.get("artist") or [None])[0]
            title = (audio.tags.get("title") or [None])[0]
            album = (audio.tags.get("album") or [None])[0]
        info = getattr(audio, "info", None)
        duration = getattr(info, "length", None)
    return TrackStub(
        path=str(path),
        filename=path.name,
        artist=artist,
        title=title,
        album=album,
        duration_s=duration,
        file_size=stat.st_size,
        file_mtime=stat.st_mtime,
    )


class ScanSignals(QObject):
    batch = Signal(int, list)       # folder_id, list[TrackStub]
    progress = Signal(int, int)     # done, total
    finished = Signal(int, set)     # folder_id, set of paths found
    failed = Signal(int, str)       # folder_id, message


class ScanWorker(QRunnable):
    def __init__(self, folder_id: int, folder_path: str):
        super().__init__()
        self.folder_id = folder_id
        self.folder_path = folder_path
        self.signals = ScanSignals()
        self.cancel = threading.Event()

    def run(self) -> None:
        try:
            files = find_audio_files(Path(self.folder_path), recursive=True)
            total = len(files)
            found: set[str] = set()
            batch: list[TrackStub] = []
            for i, path in enumerate(files, start=1):
                if self.cancel.is_set():
                    return
                try:
                    stub = read_stub(path)
                except OSError:
                    continue
                found.add(stub.path)
                batch.append(stub)
                if len(batch) >= BATCH_SIZE:
                    self.signals.batch.emit(self.folder_id, batch)
                    batch = []
                    self.signals.progress.emit(i, total)
            if batch:
                self.signals.batch.emit(self.folder_id, batch)
            self.signals.progress.emit(total, total)
            self.signals.finished.emit(self.folder_id, found)
        except Exception as exc:  # surfaced in the status bar, never silent
            self.signals.failed.emit(self.folder_id, str(exc))
