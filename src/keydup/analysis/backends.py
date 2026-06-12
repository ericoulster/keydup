"""BPM backend selection.

Two interchangeable TempoCNN backends from keypipe: essentia
(TensorFlow) where its wheels exist and bundle cleanly (Linux), and the
ONNX reimplementation everywhere else (Windows has no essentia wheels;
macOS PyInstaller bundles deadlock loading TensorFlow next to torch).
Validated 2026-06-12: ONNX scored 12/13 vs essentia's 9/13 on the
Kawaii Karnival benchmark - no quality compromise."""

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


class OnnxBpmBackend:
    name = "tempocnn-onnx"

    def __init__(self, min_bpm: int = 55, max_bpm: int = 215):
        from keypipe.inference_onnx import OnnxBPMDetector

        self._detector = OnnxBPMDetector(min_bpm=min_bpm, max_bpm=max_bpm)

    def detect_with_confidence(self, path: str) -> tuple[int, float]:
        return self._detector.detect_with_confidence(path)


def select_bpm_backend() -> BpmBackend:
    try:
        import essentia.standard  # noqa: F401

        return EssentiaBpmBackend()
    except ImportError:
        pass
    try:
        import onnxruntime  # noqa: F401

        return OnnxBpmBackend()
    except ImportError as exc:
        raise RuntimeError(
            "No BPM backend available: neither essentia nor onnxruntime "
            "is installed. Key detection still works."
        ) from exc
