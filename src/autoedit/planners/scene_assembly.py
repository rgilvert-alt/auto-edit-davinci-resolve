"""Scene-assembly planner: filter/order shots, rough cut + marker per scene."""

from __future__ import annotations

from ..analyzers.common import Interval
from ..config import seconds_to_frames
from ..models import ClipSegment, EditPlan, Marker

_ORDERS = {"source", "longest", "shortest"}


def plan_scene_assembly(
    media_path: str,
    shots: list[Interval],
    source_fps: float,
    timeline_name: str,
    timeline_fps: float | None = None,
    min_scene_s: float = 0.0,
    max_scene_s: float | None = None,
    order: str = "source",
    limit: int | None = None,
) -> EditPlan:
    """Build an EditPlan selecting/ordering shots with a marker per scene.

    Source in/out points are measured at ``source_fps``; timeline placement and
    marker frames use ``timeline_fps`` (defaults to the source rate).
    """
    if order not in _ORDERS:
        raise ValueError(f"order must be one of {_ORDERS}, got {order!r}")
    timeline_fps = timeline_fps or source_fps

    selected = [
        s
        for s in shots
        if s.duration >= min_scene_s
        and (max_scene_s is None or s.duration <= max_scene_s)
    ]

    if order == "longest":
        selected.sort(key=lambda s: s.duration, reverse=True)
    elif order == "shortest":
        selected.sort(key=lambda s: s.duration)
    else:
        selected.sort(key=lambda s: s.start)

    if limit is not None:
        selected = selected[:limit]

    clips: list[ClipSegment] = []
    markers: list[Marker] = []
    record = 0
    for idx, shot in enumerate(selected, start=1):
        start_f = seconds_to_frames(shot.start, source_fps)
        end_f = seconds_to_frames(shot.end, source_fps)
        if end_f <= start_f:
            continue
        clips.append(
            ClipSegment(
                media_path=media_path,
                start_frame=start_f,
                end_frame=end_f,
                record_frame=record,
                track_index=1,
                name=f"Scene {idx}",
                source_fps=source_fps,
            )
        )
        markers.append(Marker(frame=record, name=f"Scene {idx}", color="Green"))
        record += seconds_to_frames((end_f - start_f) / source_fps, timeline_fps)

    return EditPlan(
        timeline_name=timeline_name,
        fps=timeline_fps,
        clips=clips,
        markers=markers,
        mode="scenes",
    )
