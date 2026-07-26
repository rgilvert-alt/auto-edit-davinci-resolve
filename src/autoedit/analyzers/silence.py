"""Silence / speech detection via ffmpeg's ``silencedetect`` filter."""

from __future__ import annotations

import re
import subprocess

from ..media import ffmpeg_available, probe
from .common import Interval, invert_intervals

_SILENCE_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


def detect_silence(
    path: str,
    noise_db: float = -30.0,
    min_silence_s: float = 0.5,
) -> list[Interval]:
    """Return silent spans (seconds) using ffmpeg silencedetect."""
    if not ffmpeg_available():
        raise RuntimeError(
            "ffmpeg not found on PATH. Install it (brew install ffmpeg) to use "
            "silence detection."
        )
    cmd = [
        "ffmpeg",
        "-i",
        path,
        "-af",
        f"silencedetect=noise={noise_db}dB:d={min_silence_s}",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stderr = proc.stderr or ""

    silences: list[Interval] = []
    pending_start: float | None = None
    for line in stderr.splitlines():
        m_start = _SILENCE_START.search(line)
        if m_start:
            pending_start = float(m_start.group(1))
            continue
        m_end = _SILENCE_END.search(line)
        if m_end and pending_start is not None:
            silences.append(Interval(max(0.0, pending_start), float(m_end.group(1))))
            pending_start = None
    return silences


def detect_speech(
    path: str,
    noise_db: float = -30.0,
    min_silence_s: float = 0.5,
) -> list[Interval]:
    """Return speech spans (seconds): the complement of detected silence."""
    info = probe(path)
    duration = info.duration_s
    silences = detect_silence(path, noise_db=noise_db, min_silence_s=min_silence_s)
    if duration is None:
        # Without a known duration, extend to the last silence end.
        duration = max((s.end for s in silences), default=0.0)
    return invert_intervals(silences, duration)
