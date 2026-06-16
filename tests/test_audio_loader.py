"""Corrupt-header-tolerant audio loading."""

import os

import numpy as np
import pytest
import soundfile as sf

from keypipe.utils import _header_frames_bogus, load_audio_mono

# A real-world FLAC whose STREAMINFO total-samples is the int64 "unknown"
# sentinel (2**63-1); soundfile would try to allocate exabytes.
CORRUPT_FLAC = (
    "/home/hq/Music/01 Tracks/1. J-rave/(C90) [S2TB-0018] The 4th EP2/"
    "01 New Game feat.Mayumi Morinaga - 3A - 170.flac"
)


def test_normal_file_loads_and_resamples(tmp_path):
    sr = 44100
    sf.write(tmp_path / "x.wav",
             (0.1 * np.sin(2 * np.pi * 440 * np.linspace(0, 2, sr * 2))).astype("float32"),
             sr)
    y = load_audio_mono(tmp_path / "x.wav", 22050)
    assert y.dtype == np.float32
    assert abs(len(y) - 22050 * 2) < 50      # resampled to target sr
    assert not _header_frames_bogus(str(tmp_path / "x.wav"))


def test_bogus_frame_count_detected():
    # int64 max and zero/negative both read as "don't trust the header"
    assert _MAX_check(2**63 - 1)
    assert _MAX_check(0)
    assert not _MAX_check(44100 * 200)        # a plausible 200s track


def _MAX_check(frames):
    from keypipe.utils import _MAX_PLAUSIBLE_FRAMES
    return frames <= 0 or frames > _MAX_PLAUSIBLE_FRAMES


@pytest.mark.skipif(not os.path.exists(CORRUPT_FLAC), reason="sample file absent")
def test_corrupt_flac_recovers_via_streaming():
    assert _header_frames_bogus(CORRUPT_FLAC)         # header is bogus
    y = load_audio_mono(CORRUPT_FLAC, 44100)
    assert y.dtype == np.float32
    assert len(y) > 44100 * 250                       # ~5 min recovered, not 0
