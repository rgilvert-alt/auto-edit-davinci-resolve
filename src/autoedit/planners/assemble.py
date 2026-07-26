"""Assemble planner: per-clip analyze/edit, then stitch in source order."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..models import ClipSegment, EditPlan, MusicTrack

AssembleMode = Literal["scenes", "silence", "none"]


@dataclass
class AssembleSource:
    path: str
    mode: AssembleMode = "scenes"


def stitch_plans(
    partials: list[EditPlan],
    *,
    timeline_name: str,
    timeline_fps: float,
    music_path: str | None = None,
) -> EditPlan:
    """Concatenate EditPlan clips in order, re-rippling record_frame only."""
    clips: list[ClipSegment] = []
    record = 0
    for plan in partials:
        for c in plan.clips:
            span = c.timeline_span(timeline_fps)
            if span <= 0:
                continue
            clips.append(
                ClipSegment(
                    media_path=c.media_path,
                    start_frame=c.start_frame,
                    end_frame=c.end_frame,
                    record_frame=record,
                    track_index=c.track_index,
                    name=c.name,
                    source_fps=c.source_fps,
                )
            )
            record += span

    music = MusicTrack(media_path=music_path) if music_path else None
    return EditPlan(
        timeline_name=timeline_name,
        fps=timeline_fps,
        clips=clips,
        music=music,
        mode="assemble",
    )


def full_clip_plan(
    media_path: str,
    *,
    source_fps: float,
    duration_s: float,
    timeline_name: str,
    timeline_fps: float,
) -> EditPlan:
    """Passthrough: one segment covering the whole source."""
    from ..config import seconds_to_frames

    end_f = max(1, seconds_to_frames(duration_s, source_fps))
    return EditPlan(
        timeline_name=timeline_name,
        fps=timeline_fps,
        clips=[
            ClipSegment(
                media_path=media_path,
                start_frame=0,
                end_frame=end_f,
                record_frame=0,
                track_index=1,
                source_fps=source_fps,
            )
        ],
        mode="assemble",
    )
