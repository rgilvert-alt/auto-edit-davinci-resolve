"""Silence-removal planner: keep speech spans, ripple into jump cuts."""

from __future__ import annotations

from ..analyzers.common import Interval
from ..config import conform_timeline_frames, seconds_to_frames
from ..models import ClipSegment, EditPlan


def _pad_and_merge(
    speech: list[Interval], padding_s: float, min_gap_s: float, total_s: float | None
) -> list[Interval]:
    if not speech:
        return []
    padded: list[Interval] = []
    for iv in sorted(speech, key=lambda i: i.start):
        start = max(0.0, iv.start - padding_s)
        end = iv.end + padding_s
        if total_s is not None:
            end = min(end, total_s)
        padded.append(Interval(start, end))

    merged = [padded[0]]
    for iv in padded[1:]:
        last = merged[-1]
        if iv.start - last.end < min_gap_s:
            merged[-1] = Interval(last.start, max(last.end, iv.end))
        else:
            merged.append(iv)
    return merged


def plan_silence_cut(
    media_path: str,
    speech: list[Interval],
    source_fps: float,
    timeline_name: str,
    timeline_fps: float | None = None,
    padding_s: float = 0.15,
    min_gap_s: float = 0.30,
    total_s: float | None = None,
) -> EditPlan:
    """Build an EditPlan that keeps padded, merged speech spans on V1.

    Source in/out points are measured at ``source_fps``; timeline placement
    ripples at ``timeline_fps`` (defaults to the source rate).
    """
    timeline_fps = timeline_fps or source_fps
    kept = _pad_and_merge(speech, padding_s, min_gap_s, total_s)

    clips: list[ClipSegment] = []
    record = 0
    for iv in kept:
        start_f = seconds_to_frames(iv.start, source_fps)
        end_f = seconds_to_frames(iv.end, source_fps)
        if end_f <= start_f:
            continue
        clips.append(
            ClipSegment(
                media_path=media_path,
                start_frame=start_f,
                end_frame=end_f,
                record_frame=record,
                track_index=1,
                source_fps=source_fps,
            )
        )
        # Advance on the timeline clock, not the source clock.
        record += conform_timeline_frames(
            end_f - start_f, source_fps, timeline_fps
        )

    return EditPlan(
        timeline_name=timeline_name,
        fps=timeline_fps,
        clips=clips,
        mode="silence",
    )
