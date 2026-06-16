"""Filesystem locations: user data dir, bundled resources, model weights."""

from __future__ import annotations

import sys
from pathlib import Path

import platformdirs

APP_NAME = "keydup"


def data_dir() -> Path:
    d = Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "library.db"


def log_path() -> Path:
    return data_dir() / "keydup.log"


def resources_dir() -> Path:
    # In a PyInstaller bundle resources are collected under _MEIPASS.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "keydup" / "resources"
    return Path(__file__).parent / "resources"


def keynet_model_path() -> Path:
    """Explicit path to keypipe's key-detection checkpoint (works both
    installed and inside a PyInstaller bundle)."""
    import keypipe

    return Path(keypipe.__file__).parent / "checkpoints" / "keynet.pt"
