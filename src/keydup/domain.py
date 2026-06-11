"""Core data types and Camelot-wheel logic."""

from __future__ import annotations

from dataclasses import dataclass, field

# Bump when detection models/algorithms change; tracks with an older
# version are re-queued for analysis on the next rescan.
CURRENT_ANALYSIS_VERSION = 1

TRACK_STATUSES = ("pending", "analyzing", "done", "error", "missing")


@dataclass
class TrackStub:
    """Result of the fast scan pass (filesystem + mutagen, no ML)."""

    path: str
    filename: str
    artist: str | None
    title: str | None
    album: str | None
    duration_s: float | None
    file_size: int
    file_mtime: float


@dataclass
class Track:
    id: int
    folder_id: int
    path: str
    filename: str
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    duration_s: float | None = None
    file_size: int = 0
    file_mtime: float = 0.0
    key_camelot: str | None = None
    key_confidence: float | None = None
    bpm: int | None = None
    bpm_confidence: float | None = None
    bpm_source: str | None = None
    analysis_version: int | None = None
    analyzed_at: str | None = None
    status: str = "pending"
    error: str | None = None
    tag_ids: frozenset[int] = frozenset()
    tag_names: tuple[str, ...] = ()


@dataclass
class Tag:
    id: int
    name: str
    kind: str  # 'genre' | 'set'
    color: str | None = None


@dataclass
class Folder:
    id: int
    path: str
    last_scanned_at: str | None = None


def parse_camelot(key: str) -> tuple[int, str]:
    """'8A' -> (8, 'A'). Raises ValueError on malformed input."""
    number, letter = int(key[:-1]), key[-1].upper()
    if not (1 <= number <= 12) or letter not in ("A", "B"):
        raise ValueError(f"not a Camelot key: {key!r}")
    return number, letter


def camelot_neighbors(key: str) -> frozenset[str]:
    """The harmonically compatible keys for a Camelot key: itself, one
    step either way around the wheel, and the relative major/minor."""
    number, letter = parse_camelot(key)
    up = number % 12 + 1
    down = (number - 2) % 12 + 1
    other = "B" if letter == "A" else "A"
    return frozenset({key, f"{up}{letter}", f"{down}{letter}", f"{number}{other}"})


def expand_harmonic(keys: frozenset[str]) -> frozenset[str]:
    out: set[str] = set()
    for key in keys:
        out |= camelot_neighbors(key)
    return frozenset(out)
