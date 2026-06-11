"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from keydup import paths
from keydup.db import Database
from keydup.library import LibraryService
from keydup.ui.main_window import MainWindow
from keydup.ui.theme import apply_theme


def self_test() -> int:
    """Used by CI on the built bundle: open a DB, load both models, and
    run real inference on a generated click track - fully offline."""
    import os
    import tempfile
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QApplication(sys.argv)

    import numpy as np
    import soundfile as sf

    from keypipe.inference import KeyDetector

    from keydup.analysis.backends import select_bpm_backend

    key_detector = KeyDetector(paths.keynet_model_path(), device="cpu")
    backend = select_bpm_backend()

    with tempfile.TemporaryDirectory() as td:
        Database(Path(td) / "selftest.db").close()
        sr, bpm = 44100, 128
        samples = np.zeros(sr * 15, dtype=np.float32)
        burst = (
            np.sin(2 * np.pi * 220 * np.arange(220) / sr) * np.linspace(1, 0, 220)
        ).astype(np.float32)
        for i in range(0, len(samples) - len(burst), int(sr * 60 / bpm)):
            samples[i : i + len(burst)] += burst
        wav = str(Path(td) / "click.wav")
        sf.write(wav, samples, sr)

        key = key_detector.detect(wav)
        detected_bpm = backend.detect_with_confidence(wav)[0]
        assert key, "key detection returned nothing"
        assert abs(detected_bpm - bpm) <= 2, f"BPM {detected_bpm} != {bpm}"

    print(f"self-test OK (key={key}, bpm={detected_bpm}, backend={backend.name})")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    app = QApplication(sys.argv)
    app.setApplicationName("key'd up")
    app.setOrganizationName("keydup")
    app.setDesktopFileName("keydup")
    apply_theme(app)

    db = Database(paths.db_path())
    library = LibraryService(db)
    window = MainWindow(library)
    window.show()

    code = app.exec()
    db.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
