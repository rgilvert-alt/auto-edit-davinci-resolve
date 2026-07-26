"""Music-montage planner: cut b-roll on beats, lay music from frame 0."""

from __future__ import annotations

from ..analyzers.beats import BeatGrid
from ..config import seconds_to_frames
from ..models import ClipSegment, EditPlan, Marker, MusicTrack


def plan_music_montage(
    broll_paths: list[str],
    beats: BeatGrid,
    music_path: str,
    timeline_fps: float,
    timeline_name: str,
    source_fps: float | dict[str, float] | None = None,
    beats_per_clip: int = 4,
    clip_source_start_frame: int = 0,
    add_beat_markers: bool = True,
    reuse_policy: str = "cycle",
) -> EditPlan:
    """Build an EditPlan placing one b-roll subclip per beat interval.

    Beats are wall-clock, so timeline positions use ``timeline_fps`` while each
    subclip's source out point is measured at that b-roll's own rate.
    ``source_fps`` may be one rate for all clips or a per-path mapping; None
    means the b-roll runs at the timeline rate.

    ``reuse_policy``:
      - cycle: wrap through b-roll list (default)
      - stop: stop when b-roll list is exhausted
      - reuse_best: always use the first clip after exhausting the list
    """
    if not broll_paths:
        raise ValueError("music montage requires at least one b-roll path")
    if beats_per_clip < 1:
        raise ValueError("beats_per_clip must be >= 1")
    if reuse_policy not in {"cycle", "stop", "reuse_best"}:
        raise ValueError(f"unknown reuse_policy: {reuse_policy!r}")

    beat_times = sorted(beats.beats)
    if len(beat_times) < 2:
        raise ValueError("need at least two beats to form an interval")

    # Cut points every `beats_per_clip` beats.
    cut_times = beat_times[::beats_per_clip]
    if cut_times[-1] != beat_times[-1]:
        cut_times.append(beat_times[-1])

    clips: list[ClipSegment] = []
    markers: list[Marker] = []
    for idx in range(len(cut_times) - 1):
        media = _pick_media(broll_paths, idx, reuse_policy)
        if media is None:
            break
        start_s = cut_times[idx]
        end_s = cut_times[idx + 1]
        record_f = seconds_to_frames(start_s, timeline_fps)
        end_record_f = seconds_to_frames(end_s, timeline_fps)
        if end_record_f <= record_f:
            continue
        clip_fps = _source_fps_for(media, source_fps, timeline_fps)
        # Source length is the beat interval measured on the clip's own clock.
        source_len = seconds_to_frames(end_s - start_s, clip_fps)
        if source_len <= 0:
            continue
        clips.append(
            ClipSegment(
                media_path=media,
                start_frame=clip_source_start_frame,
                end_frame=clip_source_start_frame + source_len,
                record_frame=record_f,
                track_index=1,
                source_fps=clip_fps,
            )
        )
        if add_beat_markers:
            markers.append(Marker(frame=record_f, name=f"Beat {idx + 1}", color="Cyan"))

    music = MusicTrack(media_path=music_path, start_frame=0, track_index=1)

    return EditPlan(
        timeline_name=timeline_name,
        fps=timeline_fps,
        clips=clips,
        markers=markers,
        music=music,
        mode="montage",
    )


def _pick_media(paths: list[str], idx: int, reuse_policy: str) -> str | None:
    if reuse_policy == "cycle":
        return paths[idx % len(paths)]
    if reuse_policy == "stop":
        return paths[idx] if idx < len(paths) else None
    # reuse_best
    if idx < len(paths):
        return paths[idx]
    return paths[0]


def _source_fps_for(
    media: str, source_fps: float | dict[str, float] | None, timeline_fps: float
) -> float:
    if source_fps is None:
        return timeline_fps
    if isinstance(source_fps, dict):
        return source_fps.get(media, timeline_fps)
    return source_fps
