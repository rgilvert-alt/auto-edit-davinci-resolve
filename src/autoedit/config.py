"""Configuration and frame-math helpers.

Frame integers are the source of truth for edits. Seconds only appear at
analyzer boundaries and are converted to frames as early as possible using the
clip/timeline fps.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is a core dep, but keep import defensive.
    def load_dotenv(*_args, **_kwargs):  # type: ignore
        return False


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Resolve paths + engine defaults, sourced from environment / .env."""

    resolve_script_api: str | None = None
    resolve_script_lib: str | None = None
    whisper_model: str = "base"
    silence_padding_s: float = 0.15
    silence_min_gap_s: float = 0.30
    default_fps: float = 24.0

    resolve_modules_path: str | None = field(default=None)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load .env once and build immutable Settings."""
    load_dotenv()
    api = os.environ.get("RESOLVE_SCRIPT_API") or None
    modules = f"{api}/Modules" if api else None
    return Settings(
        resolve_script_api=api,
        resolve_script_lib=os.environ.get("RESOLVE_SCRIPT_LIB") or None,
        whisper_model=os.environ.get("AUTOEDIT_WHISPER_MODEL", "base"),
        silence_padding_s=_get_float("AUTOEDIT_SILENCE_PADDING_S", 0.15),
        silence_min_gap_s=_get_float("AUTOEDIT_SILENCE_MIN_GAP_S", 0.30),
        default_fps=_get_float("AUTOEDIT_DEFAULT_FPS", 24.0),
        resolve_modules_path=modules,
    )


# --- Frame math (source of truth) -----------------------------------------


def seconds_to_frames(seconds: float, fps: float) -> int:
    """Convert seconds to a frame index/count, rounding to nearest frame."""
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    return int(round(seconds * fps))


def frames_to_seconds(frames: int, fps: float) -> float:
    """Convert a frame count to seconds."""
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    return frames / fps


def conform_timeline_frames(
    source_frames: int, source_fps: float, timeline_fps: float
) -> int:
    """Timeline frames occupied after conforming ``source_frames`` to ``timeline_fps``.

    Uses truncation (not round-half-up). Rounding up made AutoEdit advance
    ``recordFrame`` one frame past where Resolve typically ends the previous
    clip on mixed-rate timelines (e.g. 50→30), leaving systematic 1-frame gaps.
    """
    if source_fps <= 0 or timeline_fps <= 0:
        raise ValueError(
            f"fps must be positive, got source_fps={source_fps}, "
            f"timeline_fps={timeline_fps}"
        )
    if source_frames <= 0:
        return 0
    if abs(source_fps - timeline_fps) < 1e-6:
        return int(source_frames)
    return max(1, int(source_frames * timeline_fps / source_fps))
