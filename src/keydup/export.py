"""Export an ordered set: copy its files into one directory with
order-preserving numbered names ('01 Track.mp3', '02 ...') so the set
order survives filename sorting (USB sticks, CDJs). Sources are copied,
never moved or modified."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from keydup.domain import Track


def export_names(tracks: list[Track]) -> list[str]:
    width = max(2, len(str(len(tracks))))
    return [f"{i:0{width}d} {t.filename}" for i, t in enumerate(tracks, start=1)]


class ExportSignals(QObject):
    progress = Signal(int, int)     # done, total
    finished = Signal(str)          # human-readable summary
    failed = Signal(str)


class SetExportWorker(QRunnable):
    def __init__(self, tracks: list[Track], dest_dir: str):
        super().__init__()
        self.tracks = tracks
        self.dest_dir = Path(dest_dir)
        self.signals = ExportSignals()
        self.cancel = threading.Event()

    def run(self) -> None:
        try:
            self.dest_dir.mkdir(parents=True, exist_ok=True)
            copied = skipped_existing = missing = 0
            names = export_names(self.tracks)
            total = len(self.tracks)
            for i, (track, name) in enumerate(zip(self.tracks, names), start=1):
                if self.cancel.is_set():
                    self.signals.finished.emit(f"Export cancelled after {copied} files")
                    return
                source = Path(track.path)
                dest = self.dest_dir / name
                if not source.exists():
                    missing += 1
                elif dest.exists():
                    skipped_existing += 1
                else:
                    shutil.copy2(source, dest)
                    copied += 1
                self.signals.progress.emit(i, total)
            summary = f"Exported {copied} files to {self.dest_dir}"
            if skipped_existing:
                summary += f" ({skipped_existing} already there)"
            if missing:
                summary += f" ({missing} missing on disk)"
            self.signals.finished.emit(summary)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
