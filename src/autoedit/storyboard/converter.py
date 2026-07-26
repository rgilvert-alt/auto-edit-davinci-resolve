"""storyboard_to_edit_plan: seconds → dual-clock EditPlan frames."""

from __future__ import annotations

from ..analysis.catalogue import MediaCatalogue
from ..config import seconds_to_frames
from ..models import ClipSegment, EditPlan, Marker, MusicTrack
from .models import Storyboard


def storyboard_to_edit_plan(
    storyboard: Storyboard,
    media_catalogue: MediaCatalogue,
    *,
    timeline_name: str,
    timeline_fps: float,
    music_path: str | None = None,
    add_markers: bool = True,
) -> EditPlan:
    """Convert filled storyboard time selections into an executable EditPlan."""
    if timeline_fps <= 0:
        raise ValueError(f"timeline_fps must be positive, got {timeline_fps}")

    fps_by_path = {c.media_path: c.source_fps for c in media_catalogue.clips}
    from pathlib import Path

    for c in media_catalogue.clips:
        fps_by_path[str(Path(c.media_path).resolve())] = c.source_fps

    clips: list[ClipSegment] = []
    markers: list[Marker] = []
    record = 0
    for slot in storyboard.slots:
        fill = slot.fill
        if fill is None:
            continue
        source_fps = fps_by_path.get(fill.media_path) or fps_by_path.get(
            str(Path(fill.media_path).expanduser().resolve())
        )
        if not source_fps or source_fps <= 0:
            raise ValueError(f"Unknown source_fps for {fill.media_path}")

        start_f = seconds_to_frames(fill.start_s, source_fps)
        end_f = seconds_to_frames(fill.start_s + fill.duration_s, source_fps)
        if end_f <= start_f:
            end_f = start_f + max(1, seconds_to_frames(fill.duration_s, source_fps))
        span = int(round((end_f - start_f) / source_fps * timeline_fps))
        if span <= 0:
            continue
        clips.append(
            ClipSegment(
                media_path=fill.media_path,
                start_frame=start_f,
                end_frame=end_f,
                record_frame=record,
                track_index=1,
                name=slot.role,
                source_fps=source_fps,
            )
        )
        if add_markers:
            name = (fill.descriptor or slot.role or "shot")[:48]
            note_bits = [fill.reason] if fill.reason else []
            if fill.tags:
                note_bits.append("tags: " + ", ".join(fill.tags[:6]))
            if fill.score_parts:
                top = sorted(
                    fill.score_parts.items(), key=lambda kv: -abs(kv[1])
                )[:4]
                note_bits.append(
                    "parts: " + ", ".join(f"{k}={v:+.2f}" for k, v in top)
                )
            markers.append(
                Marker(
                    frame=record,
                    name=name,
                    color="Lavender",
                    note=" | ".join(note_bits)[:400],
                    duration_frames=max(
                        1, min(span, seconds_to_frames(1.0, timeline_fps))
                    ),
                )
            )
        record += span

    music = MusicTrack(media_path=music_path) if music_path else None
    return EditPlan(
        timeline_name=timeline_name,
        fps=timeline_fps,
        clips=clips,
        markers=markers,
        music=music,
        mode="story",
    )
