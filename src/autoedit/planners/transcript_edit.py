"""Transcript-editing planner: map word timings to keep ranges -> clips.

Two mutually exclusive selection modes:
  - delete_words:  drop the listed words wherever they occur (keep the rest).
  - keep_keywords: keep only transcript segments containing a keyword.
"""

from __future__ import annotations

import re

from ..analyzers.common import Interval
from ..analyzers.transcription import Transcript
from ..config import conform_timeline_frames, seconds_to_frames
from ..models import ClipSegment, EditPlan


def _normalize(text: str) -> str:
    return re.sub(r"[^\w]", "", text).lower()


def _keep_ranges_from_words(transcript: Transcript, drop: set[str]) -> list[Interval]:
    """Coalesce contiguous kept words into [start, end) spans."""
    ranges: list[Interval] = []
    run_start: float | None = None
    run_end: float | None = None
    for w in transcript.words:
        keep = _normalize(w.text) not in drop
        if keep:
            if run_start is None:
                run_start = w.start
            run_end = w.end
        else:
            if run_start is not None and run_end is not None:
                ranges.append(Interval(run_start, run_end))
            run_start = run_end = None
    if run_start is not None and run_end is not None:
        ranges.append(Interval(run_start, run_end))
    return ranges


def _keep_ranges_from_keywords(
    transcript: Transcript, keywords: set[str]
) -> list[Interval]:
    """Keep whole segments that contain any keyword."""
    ranges: list[Interval] = []
    for seg in transcript.segments:
        tokens = {_normalize(t) for t in seg.text.split()}
        if tokens & keywords:
            ranges.append(Interval(seg.start, seg.end))
    return ranges


def plan_transcript_edit(
    media_path: str,
    transcript: Transcript,
    source_fps: float,
    timeline_name: str,
    timeline_fps: float | None = None,
    delete_words: list[str] | None = None,
    keep_keywords: list[str] | None = None,
) -> EditPlan:
    """Build an EditPlan from a word-timed transcript.

    Source in/out points are measured at ``source_fps``; timeline placement
    ripples at ``timeline_fps`` (defaults to the source rate).
    """
    timeline_fps = timeline_fps or source_fps
    if keep_keywords:
        keep = _keep_ranges_from_keywords(
            transcript, {_normalize(k) for k in keep_keywords}
        )
    else:
        drop = {_normalize(w) for w in (delete_words or [])}
        keep = _keep_ranges_from_words(transcript, drop)

    clips: list[ClipSegment] = []
    record = 0
    for iv in keep:
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
        record += conform_timeline_frames(
            end_f - start_f, source_fps, timeline_fps
        )

    return EditPlan(
        timeline_name=timeline_name,
        fps=timeline_fps,
        clips=clips,
        mode="transcript",
    )
