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

    import faulthandler

    # if anything deadlocks (native library load order is fragile in
    # bundles), dump the hanging frame and exit instead of timing out
    faulthandler.dump_traceback_later(180, exit=True)

    def dyld_report(label: str) -> None:
        # how many copies of the contended native libs are actually
        # loaded - duplicate images are the deadlock suspects
        if sys.platform != "darwin":
            return
        import ctypes

        libc = ctypes.CDLL(None)
        count = libc._dyld_image_count()
        libc._dyld_get_image_name.restype = ctypes.c_char_p
        names = [libc._dyld_get_image_name(i).decode() for i in range(count)]
        for fragment in ("libomp", "tensorflow", "libtorch"):
            hits = [n for n in names if fragment in n.lower()]
            print(f"self-test[{label}]: {fragment} x{len(hits)} {hits[:3]}", flush=True)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QApplication(sys.argv)
    print("self-test: qt up", flush=True)
    dyld_report("after-qt")

    import numpy as np
    import soundfile as sf

    # construct the essentia/TF backend BEFORE importing torch's world:
    # loading torch first deadlocks essentia's dlopen in macOS bundles
    from keydup.analysis.backends import select_bpm_backend

    backend = select_bpm_backend()
    print(f"self-test: bpm backend ready ({backend.name})", flush=True)
    dyld_report("after-essentia")

    from keypipe.inference import KeyDetector

    key_detector = KeyDetector(paths.keynet_model_path(), device="cpu")
    print("self-test: key model loaded", flush=True)
    dyld_report("after-torch")

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
        print(f"self-test: key inference done ({key})", flush=True)
        detected_bpm = backend.detect_with_confidence(wav)[0]
        print(f"self-test: bpm inference done ({detected_bpm})", flush=True)
        assert key, "key detection returned nothing"
        assert abs(detected_bpm - bpm) <= 2, f"BPM {detected_bpm} != {bpm}"

    print(f"self-test OK (key={key}, bpm={detected_bpm}, backend={backend.name})")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    # keep the terminal clean; output is viewable in-app (View > Show Log)
    from keydup.logcapture import LogBuffer, install_log_capture, quiet_native_logs

    quiet_native_logs()
    log_buffer = LogBuffer()
    install_log_capture(log_buffer, paths.log_path())

    app = QApplication(sys.argv)
    app.setApplicationName("key'd up")
    app.setOrganizationName("keydup")
    app.setDesktopFileName("keydup")
    apply_theme(app)

    db = Database(paths.db_path())
    library = LibraryService(db)
    window = MainWindow(library, log_buffer=log_buffer)
    window.show()

    code = app.exec()
    db.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
