"""Media probing helpers (ffprobe) shared by analyzers.

Kept dependency-light: shells out to ffprobe. A wrong frame rate silently
corrupts every cut downstream, so probing never guesses -- it raises instead.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaInfo:
    """Probed media facts. ``fps`` is 0.0 for audio-only files."""

    path: str
    fps: float
    duration_s: float | None
    has_video: bool
    has_audio: bool


class ProbeError(RuntimeError):
    """Raised when media facts cannot be established."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def _parse_fps(rate: str | None) -> float | None:
    if not rate:
        return None
    if "/" in rate:
        num, _, den = rate.partition("/")
        try:
            n, d = float(num), float(den)
            return n / d if d else None
        except ValueError:
            return None
    try:
        return float(rate)
    except ValueError:
        return None


def probe(path: str | Path) -> MediaInfo:
    """Probe a media file for fps/duration/streams.

    Raises ProbeError rather than substituting a default frame rate: guessing
    here would silently misplace every cut in the resulting plan. Audio-only
    files legitimately report fps 0.0.
    """
    path = str(path)

    if not ffprobe_available():
        raise ProbeError(
            f"ffprobe not found on PATH, cannot determine the frame rate of {path}. "
            "Install it with: brew install ffmpeg"
        )

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ProbeError(f"ffprobe failed for {path}: {proc.stderr.strip()}")

    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video is None:
        if audio is None:
            raise ProbeError(f"No video or audio stream found in {path}")
        fps = 0.0
    else:
        fps = _parse_fps(video.get("avg_frame_rate")) or _parse_fps(
            video.get("r_frame_rate")
        )
        if not fps or fps <= 0:
            raise ProbeError(
                f"Could not determine a video frame rate for {path}. "
                "ffprobe reported no usable avg_frame_rate or r_frame_rate."
            )

    duration = None
    fmt = data.get("format", {})
    if fmt.get("duration"):
        try:
            duration = float(fmt["duration"])
        except ValueError:
            duration = None

    return MediaInfo(
        path=path,
        fps=float(fps),
        duration_s=duration,
        has_video=video is not None,
        has_audio=audio is not None,
    )
