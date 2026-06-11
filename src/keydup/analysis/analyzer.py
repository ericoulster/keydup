"""Slow pass: key/BPM analysis on a worker QThread.

Detectors are constructed once and shared across an internal thread pool
(the same pattern keypipe's CLI uses); every result is emitted from the
QThread itself, so slots connected from the main thread run there."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import torch
from PySide6.QtCore import QThread, Signal

from keydup.paths import keynet_model_path

WORKERS = 4


@dataclass
class AnalysisResult:
    track_id: int
    key_camelot: str | None = None
    key_confidence: float | None = None
    bpm: int | None = None
    bpm_confidence: float | None = None
    bpm_source: str | None = None
    error: str | None = None


class AnalysisController(QThread):
    result_ready = Signal(object)   # AnalysisResult
    progress = Signal(int, int)     # done, total
    finished_ok = Signal()
    failed = Signal(str)            # setup failure (model load etc.)

    def __init__(self, jobs: list[tuple[int, str]], parent=None):
        """jobs: list of (track_id, file path)."""
        super().__init__(parent)
        self.jobs = jobs
        self.cancel = threading.Event()

    def run(self) -> None:
        try:
            from keypipe.inference import KeyDetector

            from keydup.analysis.backends import select_bpm_backend

            device = "cuda" if torch.cuda.is_available() else "cpu"
            key_detector = KeyDetector(keynet_model_path(), device=device)
            bpm_backend = select_bpm_backend()
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        def analyze(track_id: int, path: str) -> AnalysisResult:
            if self.cancel.is_set():
                return AnalysisResult(track_id, error="cancelled")
            try:
                key, key_conf = key_detector.detect_with_confidence(path)
                bpm, bpm_conf = bpm_backend.detect_with_confidence(path)
                return AnalysisResult(
                    track_id,
                    key_camelot=key,
                    key_confidence=float(key_conf),
                    bpm=int(bpm),
                    bpm_confidence=float(bpm_conf),
                    bpm_source=bpm_backend.name,
                )
            except Exception as exc:
                return AnalysisResult(track_id, error=str(exc))

        total = len(self.jobs)
        done = 0
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(analyze, tid, path) for tid, path in self.jobs]
            for future in as_completed(futures):
                result = future.result()
                done += 1
                if result.error == "cancelled" or self.cancel.is_set():
                    continue
                self.result_ready.emit(result)
                self.progress.emit(done, total)
        self.finished_ok.emit()
