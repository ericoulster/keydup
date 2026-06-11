"""Reveal a file in the OS file manager, selecting it where supported."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def reveal_in_file_manager(path: str) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
        return
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(Path(path))])
        return
    if _reveal_via_dbus(path):
        return
    subprocess.Popen(["xdg-open", str(Path(path).parent)])


def _reveal_via_dbus(path: str) -> bool:
    """org.freedesktop.FileManager1.ShowItems selects the file itself;
    available on Nautilus, Dolphin, Nemo and friends."""
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtDBus import QDBusConnection, QDBusInterface

        bus = QDBusConnection.sessionBus()
        iface = QDBusInterface(
            "org.freedesktop.FileManager1",
            "/org/freedesktop/FileManager1",
            "org.freedesktop.FileManager1",
            bus,
        )
        if not iface.isValid():
            return False
        url = QUrl.fromLocalFile(path).toString()
        reply = iface.call("ShowItems", [url], "")
        return reply.errorName() == ""
    except Exception:
        return False
