"""Scene / shot boundary detection via PySceneDetect."""

from __future__ import annotations

from .common import Interval


def detect_scenes(path: str, threshold: float = 27.0) -> list[Interval]:
    """Return shots as [start, end) spans in seconds.

    Imports PySceneDetect lazily so the package works without it installed.
    """
    try:
        from scenedetect import detect, ContentDetector  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "PySceneDetect is not installed. Install extras: "
            "pip install 'autoedit[analyzers]'."
        ) from exc

    scene_list = detect(path, ContentDetector(threshold=threshold))
    shots: list[Interval] = []
    for start, end in scene_list:
        shots.append(Interval(start.get_seconds(), end.get_seconds()))
    return shots
