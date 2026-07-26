"""Scene / shot boundary detection.

Prefers PySceneDetect when installed; otherwise uses the same ffmpeg +
histogram shot detector as the Story catalogue pipeline.
"""

from __future__ import annotations

from .common import Interval


def detect_scenes(path: str, threshold: float = 27.0) -> list[Interval]:
    """Return shots as [start, end) spans in seconds.

    ``threshold`` is the PySceneDetect ContentDetector value and is ignored
    by the ffmpeg fallback (which uses an adaptive histogram cut).
    """
    try:
        from scenedetect import detect, ContentDetector  # type: ignore
    except ImportError:
        return _detect_scenes_ffmpeg(path)

    scene_list = detect(path, ContentDetector(threshold=threshold))
    shots: list[Interval] = []
    for start, end in scene_list:
        shots.append(Interval(start.get_seconds(), end.get_seconds()))
    return shots


def _detect_scenes_ffmpeg(path: str) -> list[Interval]:
    from .frames import sample_frames
    from .visual import detect_shots

    sample = sample_frames(path)
    return detect_shots(sample)
