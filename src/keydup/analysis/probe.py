"""Cheap pre-playback check.

Handing a corrupt or non-audio file to the Qt media backend has crashed
the app (a native fault Python can't catch), so we screen files before
playing. This is a fast header sniff, not a decoder: it only rejects the
clearly-not-audio cases (a saved HTML page with an .mp3 extension, an
empty file) and defaults to allowing anything binary, so it never blocks
a real track it simply can't recognise. Files that failed analysis are
screened separately by their stored error."""

from __future__ import annotations


def looks_like_audio(path: str, head_bytes: int = 1024) -> bool:
    """False only when the file's first bytes look like text/HTML or the
    file is empty; True for anything with binary content (i.e. real audio)
    or if the file can't be read here (let the normal play path report it)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(head_bytes)
    except OSError:
        return True
    if not head:
        return False
    # audio containers carry binary bytes (NUL, frame syncs) in the first KB
    if b"\x00" in head:
        return True
    stripped = head.lstrip()
    if stripped[:1] == b"<" or stripped[:5].lower() == b"<!doc":
        return False  # HTML/XML
    printable = sum(1 for b in head if b in (9, 10, 13) or 32 <= b <= 126)
    return printable / len(head) < 0.95  # mostly-text with no NULs -> not audio
