"""On-demand windowed key-change detection.

Not part of normal analysis - it's invoked explicitly (right-click >
Detect key changes) because per-window key detection is too noisy to
auto-flag modulations on this library (see EXPERIMENT_LOG.md). Runs on
the thread pool; results are persisted on the main thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal


class KeyChangeSignals(QObject):
    result = Signal(int, list)   # track_id, segments
    finished = Signal()
    failed = Signal(str)


class KeyChangeWorker(QRunnable):
    def __init__(self, jobs: list[tuple[int, str]]):
        super().__init__()
        self.jobs = jobs
        self.signals = KeyChangeSignals()

    def run(self) -> None:
        try:
            import torch

            from keypipe.inference import KeyDetector

            from keydup.paths import keynet_model_path

            device = "cuda" if torch.cuda.is_available() else "cpu"
            detector = KeyDetector(keynet_model_path(), device=device)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
            return

        for track_id, path in self.jobs:
            try:
                segments = detector.detect_segments(path)
            except Exception as exc:
                self.signals.failed.emit(f"{path}: {exc}")
                continue
            self.signals.result.emit(track_id, segments)
        self.signals.finished.emit()
