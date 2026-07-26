"""Sample frames from video via a single ffmpeg pass.

Spike findings (4K50 GoPro on Intel Mac):
- Full software decode of a 10-minute clip is multi-minute even with fps=0.64.
- Videotoolbox + full decode was *slower* than software for fps-filtered pulls.
- ``-skip_frame nokey`` is ~5–15× faster; combined with an fps budget it hits
  ~400 frames on a 10-minute clip in about 90s software / faster with VT.

Default: keyframes only + fps budget, try videotoolbox then fall back.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

import numpy as np

from ..media import ffmpeg_available, probe

FRAME_SIZE = 224
MAX_FRAMES = 400
MIN_SAMPLE_FPS = 0.5
MAX_SAMPLE_FPS = 2.0


@dataclass(frozen=True)
class FrameSample:
    """RGB frames plus the wall-clock times they correspond to."""

    frames: np.ndarray  # (n, 224, 224, 3) uint8
    times_s: np.ndarray  # (n,) float64
    sample_fps: float
    used_hwaccel: bool
    keyframes_only: bool


def sample_budget(duration_s: float, max_frames: int = MAX_FRAMES) -> float:
    """Pick a sampling fps that stays within ``max_frames``."""
    if duration_s <= 0:
        return MAX_SAMPLE_FPS
    target = max_frames / duration_s
    return float(min(MAX_SAMPLE_FPS, max(MIN_SAMPLE_FPS, target)))


def sample_frames(
    path: str,
    *,
    max_frames: int = MAX_FRAMES,
    prefer_hwaccel: bool = True,
    keyframes_only: bool = True,
) -> FrameSample:
    """Decode a budgeted set of 224×224 center-crop RGB frames.

    Raises RuntimeError when ffmpeg is missing or produces no frames.
    """
    if not ffmpeg_available():
        raise RuntimeError(
            "ffmpeg not found on PATH. Install it (brew install ffmpeg) "
            "to analyze video frames."
        )

    info = probe(path)
    duration = float(info.duration_s or 0.0)
    fps = sample_budget(duration, max_frames=max_frames)

    attempts: list[tuple[bool, bool]] = []
    if prefer_hwaccel:
        attempts.append((True, keyframes_only))
    attempts.append((False, keyframes_only))
    # Last resort: decode every frame at the budgeted fps (slow on 4K50).
    if keyframes_only:
        attempts.append((False, False))

    last_err: Exception | None = None
    for use_hw, use_nokey in attempts:
        try:
            frames = _run_ffmpeg(path, fps=fps, hwaccel=use_hw, nokey=use_nokey)
            if frames.size == 0:
                raise RuntimeError("ffmpeg returned zero frames")
            n = frames.shape[0]
            if duration > 0 and n > 1:
                times = np.linspace(0.0, duration, n, dtype=np.float64)
            elif duration > 0:
                times = np.array([0.0], dtype=np.float64)
            else:
                times = np.arange(n, dtype=np.float64) / max(fps, 1e-6)
            return FrameSample(
                frames=frames,
                times_s=times,
                sample_fps=fps,
                used_hwaccel=use_hw,
                keyframes_only=use_nokey,
            )
        except Exception as exc:  # pragma: no cover - env dependent
            last_err = exc
            continue

    raise RuntimeError(f"Failed to sample frames from {path}: {last_err}")


def _run_ffmpeg(
    path: str, *, fps: float, hwaccel: bool, nokey: bool
) -> np.ndarray:
    vf = (
        f"fps={fps:.4f},"
        f"scale=398:{FRAME_SIZE}:force_original_aspect_ratio=increase,"
        f"crop={FRAME_SIZE}:{FRAME_SIZE},format=rgb24"
    )
    cmd: list[str] = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if hwaccel:
        cmd += ["-hwaccel", "videotoolbox"]
    if nokey:
        cmd += ["-skip_frame", "nokey"]
    cmd += ["-i", path, "-vf", vf, "-f", "rawvideo", "-"]

    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or f"ffmpeg exited {proc.returncode}")

    raw = proc.stdout or b""
    frame_bytes = FRAME_SIZE * FRAME_SIZE * 3
    if not raw:
        return np.zeros((0, FRAME_SIZE, FRAME_SIZE, 3), dtype=np.uint8)
    usable = (len(raw) // frame_bytes) * frame_bytes
    arr = np.frombuffer(raw[:usable], dtype=np.uint8)
    return arr.reshape((-1, FRAME_SIZE, FRAME_SIZE, 3)).copy()


def write_jpeg_thumbnail(
    frame: np.ndarray, path: str, *, quality: int = 85
) -> str:
    """Write one RGB frame as JPEG via ffmpeg (no Pillow dependency)."""
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError(f"Expected HxWx3 RGB frame, got {frame.shape}")
    h, w, _ = frame.shape
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{w}x{h}",
        "-i",
        "-",
        "-frames:v",
        "1",
        "-q:v",
        str(max(2, min(31, int(round((100 - quality) / 3))))),
        "-y",
        path,
    ]
    proc = subprocess.run(cmd, input=np.ascontiguousarray(frame).tobytes(), capture_output=True)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"thumbnail write failed: {err}")
    return path
