"""Orchestration: analyzers/planners → EditPlan for all product modes.

Surfaces (CLI, MCP, UI) call these builders only; Resolve mutation is exclusive
to applier.apply_plan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Literal

from .config import get_settings
from .media import probe
from .models import EditPlan
from .planners.assemble import AssembleSource

VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".mxf", ".avi", ".mkv", ".braw", ".r3d"}
ReusePolicy = Literal["stop", "cycle", "reuse_best"]


def collect_broll(folder: str) -> list[str]:
    """Return sorted video files directly inside ``folder``."""
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder}")
    files = [
        str(p)
        for p in sorted(root.iterdir())
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    ]
    if not files:
        raise FileNotFoundError(f"No video files found in {folder}")
    return files


def resolve_timeline_fps(explicit: float | None, source_fps: float = 0.0) -> float:
    """Pick timeline clock: explicit → Resolve project → source → app default."""
    if explicit is not None:
        if explicit <= 0:
            raise ValueError(f"timeline_fps must be positive, got {explicit}")
        return explicit

    from .resolve_client import try_project_timeline_fps

    from_resolve = try_project_timeline_fps()
    if from_resolve:
        return from_resolve
    if source_fps > 0:
        return source_fps
    return get_settings().default_fps


def build_silence_plan(
    media_path: str,
    timeline_name: str,
    noise_db: float = -30.0,
    min_silence_s: float = 0.5,
    padding_s: float | None = None,
    min_gap_s: float | None = None,
    timeline_fps: float | None = None,
) -> EditPlan:
    from .analyzers.silence import detect_speech
    from .planners.silence_cut import plan_silence_cut

    settings = get_settings()
    info = probe(media_path)
    speech = detect_speech(media_path, noise_db=noise_db, min_silence_s=min_silence_s)
    return plan_silence_cut(
        media_path=media_path,
        speech=speech,
        source_fps=info.fps,
        timeline_name=timeline_name,
        timeline_fps=resolve_timeline_fps(timeline_fps, info.fps),
        padding_s=settings.silence_padding_s if padding_s is None else padding_s,
        min_gap_s=settings.silence_min_gap_s if min_gap_s is None else min_gap_s,
        total_s=info.duration_s,
    )


def build_transcript_plan(
    media_path: str,
    timeline_name: str,
    delete_words: list[str] | None = None,
    keep_keywords: list[str] | None = None,
    model_name: str | None = None,
    language: str | None = None,
    timeline_fps: float | None = None,
) -> EditPlan:
    from .analyzers.transcription import transcribe
    from .planners.transcript_edit import plan_transcript_edit

    info = probe(media_path)
    transcript = transcribe(media_path, model_name=model_name, language=language)
    return plan_transcript_edit(
        media_path=media_path,
        transcript=transcript,
        source_fps=info.fps,
        timeline_name=timeline_name,
        timeline_fps=resolve_timeline_fps(timeline_fps, info.fps),
        delete_words=delete_words,
        keep_keywords=keep_keywords,
    )


def build_scene_plan(
    media_path: str,
    timeline_name: str,
    threshold: float = 27.0,
    min_scene_s: float = 0.0,
    max_scene_s: float | None = None,
    order: str = "source",
    limit: int | None = None,
    timeline_fps: float | None = None,
) -> EditPlan:
    from .analyzers.scenes import detect_scenes
    from .planners.scene_assembly import plan_scene_assembly

    info = probe(media_path)
    shots = detect_scenes(media_path, threshold=threshold)
    return plan_scene_assembly(
        media_path=media_path,
        shots=shots,
        source_fps=info.fps,
        timeline_name=timeline_name,
        timeline_fps=resolve_timeline_fps(timeline_fps, info.fps),
        min_scene_s=min_scene_s,
        max_scene_s=max_scene_s,
        order=order,
        limit=limit,
    )


def build_montage_plan(
    timeline_name: str,
    music_path: str,
    broll_paths: list[str] | None = None,
    broll_folder: str | None = None,
    beats_per_clip: int = 4,
    reuse_policy: ReusePolicy = "cycle",
    timeline_fps: float | None = None,
) -> EditPlan:
    from .analyzers.beats import detect_beats
    from .planners.music_montage import plan_music_montage

    if not music_path:
        raise ValueError("montage requires a music track")
    paths = list(broll_paths or [])
    if broll_folder:
        paths.extend(collect_broll(broll_folder))
    # Dedupe preserving order
    seen: dict[str, None] = {}
    for p in paths:
        seen.setdefault(str(Path(p).expanduser()), None)
    paths = list(seen)
    if not paths:
        raise ValueError("montage requires broll_paths and/or broll_folder")

    source_fps_by_path = {path: probe(path).fps for path in paths}
    resolved_timeline_fps = resolve_timeline_fps(
        timeline_fps, source_fps_by_path[paths[0]]
    )
    beats = detect_beats(music_path)
    return plan_music_montage(
        broll_paths=paths,
        beats=beats,
        music_path=music_path,
        timeline_fps=resolved_timeline_fps,
        timeline_name=timeline_name,
        source_fps=source_fps_by_path,
        beats_per_clip=beats_per_clip,
        reuse_policy=reuse_policy,
    )


def build_assemble_plan(
    sources: list[AssembleSource] | list[str],
    timeline_name: str,
    per_clip: str = "scenes",
    music_path: str | None = None,
    timeline_fps: float | None = None,
) -> EditPlan:
    """Analyze/edit each source, then stitch results in order."""
    from .planners.assemble import full_clip_plan, stitch_plans

    normalized: list[AssembleSource] = []
    for s in sources:
        if isinstance(s, AssembleSource):
            normalized.append(s)
        else:
            normalized.append(AssembleSource(path=str(s), mode=per_clip))  # type: ignore[arg-type]
    if not normalized:
        raise ValueError("assemble requires at least one source")

    first_fps = probe(normalized[0].path).fps
    tl_fps = resolve_timeline_fps(timeline_fps, first_fps)

    partials: list[EditPlan] = []
    for src in normalized:
        if src.mode == "scenes":
            partials.append(
                build_scene_plan(
                    src.path, timeline_name=f"_part_{Path(src.path).stem}",
                    timeline_fps=tl_fps,
                )
            )
        elif src.mode == "silence":
            partials.append(
                build_silence_plan(
                    src.path, timeline_name=f"_part_{Path(src.path).stem}",
                    timeline_fps=tl_fps,
                )
            )
        elif src.mode == "none":
            info = probe(src.path)
            partials.append(
                full_clip_plan(
                    src.path,
                    source_fps=info.fps,
                    duration_s=info.duration_s or 0.0,
                    timeline_name=f"_part_{Path(src.path).stem}",
                    timeline_fps=tl_fps,
                )
            )
        else:
            raise ValueError(f"unknown assemble mode: {src.mode!r}")

    return stitch_plans(
        partials,
        timeline_name=timeline_name,
        timeline_fps=tl_fps,
        music_path=music_path,
    )


def build_story_plan(
    clip_paths: list[str],
    story: str,
    timeline_name: str,
    target_duration_s: float = 60.0,
    music_path: str | None = None,
    style: str | None = None,
    timeline_fps: float | None = None,
    *,
    save_storyboard_path: str | Path | None = None,
    save_catalogue_path: str | Path | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> EditPlan:
    """Autonomous first cut: catalogue → storyboard → fill → EditPlan."""
    from .analysis import analyze_catalogue
    from .storyboard import (
        fill_storyboard,
        story_to_storyboard,
        storyboard_to_edit_plan,
    )

    if not clip_paths:
        raise ValueError("story plan requires at least one clip")
    if not (story or "").strip():
        raise ValueError("story plan requires non-empty story text")

    catalogue = analyze_catalogue(
        clip_paths,
        detect_speech=False,
        on_progress=on_progress,
    )
    if save_catalogue_path:
        catalogue.save(save_catalogue_path)

    board = story_to_storyboard(
        story,
        target_duration_s=target_duration_s,
        style=style,
        timeline_fps=None,  # resolve only at EditPlan boundary
        title=timeline_name,
    )
    board = fill_storyboard(board, catalogue)

    first_fps = catalogue.clips[0].source_fps if catalogue.clips else 0.0
    tl_fps = resolve_timeline_fps(timeline_fps, first_fps)
    if save_storyboard_path:
        board.timeline_fps = tl_fps
        board.save(save_storyboard_path)

    return storyboard_to_edit_plan(
        board,
        catalogue,
        timeline_name=timeline_name,
        timeline_fps=tl_fps,
        music_path=music_path,
    )
