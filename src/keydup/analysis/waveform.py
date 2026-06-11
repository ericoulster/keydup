"""Waveform peak extraction for the player display.

Decodes the file at a low sample rate (decode time dominates; frequency
detail is irrelevant for a peaks display) and reduces it to N peak bins.
Runs on QThreadPool; results are cached in the waveforms table."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Signal

BINS = 800
SAMPLE_RATE = 8000


def compute_peaks(path: str, bins: int = BINS) -> np.ndarray:
    import librosa

    samples, _sr = librosa.load(path, sr=SAMPLE_RATE, mono=True)
    if len(samples) == 0:
        return np.zeros(bins, dtype=np.float32)
    usable = len(samples) - (len(samples) % bins)
    if usable >= bins:
        chunks = np.abs(samples[:usable]).reshape(bins, -1)
        peaks = chunks.max(axis=1)
    else:  # extremely short file
        peaks = np.interp(
            np.linspace(0, len(samples) - 1, bins),
            np.arange(len(samples)),
            np.abs(samples),
        )
    top = float(peaks.max())
    if top > 0:
        peaks = peaks / top
    return peaks.astype(np.float32)


class WaveformSignals(QObject):
    done = Signal(int, object)   # track_id, np.ndarray
    failed = Signal(int, str)


class WaveformWorker(QRunnable):
    def __init__(self, track_id: int, path: str):
        super().__init__()
        self.track_id = track_id
        self.path = path
        self.signals = WaveformSignals()

    def run(self) -> None:
        try:
            self.signals.done.emit(self.track_id, compute_peaks(self.path))
        except Exception as exc:
            self.signals.failed.emit(self.track_id, str(exc))
