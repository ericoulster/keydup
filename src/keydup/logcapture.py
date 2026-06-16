"""Keep the terminal clean: capture stdout/stderr into an in-app buffer
and a log file instead. View > Show Log surfaces it on demand.

POSIX redirects at the file-descriptor level so native C/C++ output
(TensorFlow, essentia) is captured too, not just Python prints."""

from __future__ import annotations

import os
import sys
import threading
from collections import deque

from PySide6.QtCore import QObject, Signal


class LogBuffer(QObject):
    appended = Signal(str)

    def __init__(self, max_lines: int = 5000):
        super().__init__()
        self._lines: deque[str] = deque(maxlen=max_lines)

    def add(self, text: str) -> None:
        self._lines.append(text)
        self.appended.emit(text)

    def snapshot(self) -> str:
        return "".join(self._lines)


def quiet_native_logs() -> None:
    """Turn the chattiest native libraries down to errors. Must run
    before they import (TensorFlow reads these at import time)."""
    for key, value in {
        "TF_CPP_MIN_LOG_LEVEL": "3",
        "TF_ENABLE_ONEDNN_OPTS": "0",
        "GRPC_VERBOSITY": "ERROR",
        "KMP_WARNINGS": "0",
        "QT_LOGGING_RULES": "qt.multimedia.ffmpeg=false",
    }.items():
        os.environ.setdefault(key, value)


def install_log_capture(buffer: LogBuffer, log_path) -> None:
    """Redirect this process's stdout/stderr into ``buffer`` and a log
    file so nothing reaches the terminal."""
    log_file = open(log_path, "a", buffering=1, errors="replace")

    if sys.platform != "win32":
        read_fd, write_fd = os.pipe()
        os.dup2(write_fd, 1)
        os.dup2(write_fd, 2)
        os.close(write_fd)
        try:
            sys.stdout.reconfigure(line_buffering=True)
            sys.stderr.reconfigure(line_buffering=True)
        except (AttributeError, ValueError):
            pass

        def drain() -> None:
            with os.fdopen(read_fd, "r", errors="replace") as pipe:
                for line in pipe:
                    log_file.write(line)
                    buffer.add(line)

        threading.Thread(target=drain, daemon=True, name="log-drain").start()
    else:
        # fd-level dup2 is unreliable for windowed Windows exes (no
        # console fds); a Python tee covers our own output and the
        # bundle ships the quiet ONNX backend anyway.
        class _Tee:
            def write(self, text: str) -> int:
                log_file.write(text)
                buffer.add(text)
                return len(text)

            def flush(self) -> None:
                log_file.flush()

        sys.stdout = sys.stderr = _Tee()
