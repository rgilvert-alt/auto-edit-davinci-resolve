"""The single path that turns an EditPlan into a Resolve timeline.

No other module mutates timelines. Uses batched, positioned AppendToTimeline
calls so cuts are frame-accurate, then adds markers and the optional music clip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import EditPlan
from .resolve_client import ResolveClient


@dataclass
class ApplyResult:
    timeline_name: str
    clip_count: int
    marker_count: int
    duration_frames: int
    music_applied: bool


def apply_plan(plan: EditPlan, client: ResolveClient | None = None) -> ApplyResult:
    """Build the timeline described by ``plan`` inside Resolve.

    Steps: validate -> import all referenced media -> create timeline ->
    positioned batch append -> markers -> music. Returns a summary.
    """
    plan.validate()
    client = client or ResolveClient()

    media_paths = _referenced_media(plan)
    item_by_path = client.find_or_import(media_paths)

    timeline = client.create_timeline(plan.timeline_name)
    actual_name = timeline.GetName() or plan.timeline_name

    # recordFrame is an absolute timeline frame, and Resolve timelines start at
    # their start timecode (typically 01:00:00:00). Plan record frames are
    # relative to the timeline head, so shift them by that origin.
    timeline_start = int(timeline.GetStartFrame())

    clip_infos = _build_clip_infos(plan, item_by_path, timeline_start)
    if clip_infos:
        appended = client.media_pool().AppendToTimeline(clip_infos)
        if not appended:  # pragma: no cover - env dependent
            raise RuntimeError("AppendToTimeline returned no items.")

    music_applied = _apply_music(
        plan, client, item_by_path, timeline_start, timeline=timeline
    )
    # Markers use the same absolute timeline clock as recordFrame.
    marker_count = _apply_markers(plan, timeline, timeline_start)

    return ApplyResult(
        timeline_name=actual_name,
        clip_count=len(clip_infos),
        marker_count=marker_count,
        duration_frames=plan.duration_frames,
        music_applied=music_applied,
    )


def _referenced_media(plan: EditPlan) -> list[str]:
    paths = [c.media_path for c in plan.clips]
    if plan.music is not None:
        paths.append(plan.music.media_path)
    # Preserve order, dedupe.
    seen: dict[str, None] = {}
    for p in paths:
        seen.setdefault(p, None)
    return list(seen)


# Resolve AppendToTimeline mediaType: 1 = video only, 2 = audio only.
# Omitting mediaType places linked video + audio when the clip has sound.
MUSIC_AUDIO_TRACK = 2


def _build_clip_infos(
    plan: EditPlan, item_by_path: dict[str, Any], timeline_start: int = 0
) -> list[dict[str, Any]]:
    infos: list[dict[str, Any]] = []
    for clip in plan.clips:
        infos.append(
            {
                "mediaPoolItem": item_by_path[_key(clip.media_path)],
                "startFrame": clip.start_frame,
                # Resolve treats endFrame as inclusive; our model out point is
                # exclusive, so subtract one.
                "endFrame": clip.end_frame - 1,
                "trackIndex": clip.track_index,
                "recordFrame": timeline_start + clip.record_frame,
            }
        )
    return infos


def _ensure_audio_tracks(timeline: Any, count: int) -> None:
    """Add audio tracks until ``timeline`` has at least ``count`` of them."""
    if timeline is None or count < 1:
        return
    try:
        existing = int(timeline.GetTrackCount("audio") or 0)
    except Exception:  # pragma: no cover - env dependent
        return
    while existing < count:
        if not timeline.AddTrack("audio"):  # pragma: no cover - env dependent
            break
        existing += 1


def _apply_music(
    plan: EditPlan,
    client: ResolveClient,
    item_by_path: dict[str, Any],
    timeline_start: int = 0,
    *,
    timeline: Any = None,
) -> bool:
    """Lay optional music on A2 so it sits under linked clip audio on A1."""
    if plan.music is None:
        return False
    music = plan.music
    track_index = MUSIC_AUDIO_TRACK
    _ensure_audio_tracks(timeline, track_index)
    item = item_by_path[_key(music.media_path)]
    info = {
        "mediaPoolItem": item,
        "startFrame": 0,
        "trackIndex": track_index,
        "recordFrame": timeline_start + music.start_frame,
        "mediaType": 2,  # audio only
    }
    appended = client.media_pool().AppendToTimeline([info])
    return bool(appended)


def _apply_markers(
    plan: EditPlan, timeline: Any, timeline_start: int = 0
) -> int:
    """Place markers. ``m.frame`` is plan-relative; shift by timeline origin."""
    count = 0
    for m in plan.markers:
        ok = timeline.AddMarker(
            timeline_start + int(m.frame),
            m.color or "Blue",
            m.name or "",
            m.note or "",
            max(1, m.duration_frames),
        )
        if ok:
            count += 1
    return count


def _key(path: str) -> str:
    from pathlib import Path

    return str(Path(path).expanduser().resolve())
