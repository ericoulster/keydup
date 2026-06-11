"""BPM backend selection.

essentia (TempoCNN + onset correction via keypipe) is the only quality
backend today and has no Windows wheels; the protocol exists so a future
ONNX port can slot in for Windows builds."""

from __future__ import annotations

from typing import Protocol


class BpmBackend(Protocol):
    name: str

    def detect_with_confidence(self, path: str) -> tuple[int, float]: ...


class EssentiaBpmBackend:
    name = "essentia"

    def __init__(self, min_bpm: int = 55, max_bpm: int = 215):
        from keypipe.inference import BPMDetector  # imports essentia lazily

        self._detector = BPMDetector(min_bpm=min_bpm, max_bpm=max_bpm)

    def detect_with_confidence(self, path: str) -> tuple[int, float]:
        return self._detector.detect_with_confidence(path)


def select_bpm_backend() -> BpmBackend:
    try:
        import essentia.standard  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "No BPM backend available: essentia is not installed "
            "(it has no Windows wheels). Key detection still works."
        ) from exc
    return EssentiaBpmBackend()
