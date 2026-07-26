"""Build a MediaCatalogue from source clips with real visual analysis."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path

import numpy as np

from ..analyzers.common import Interval
from ..analyzers.frames import sample_frames, write_jpeg_thumbnail
from ..analyzers.visual import (
    aggregate_signals,
    compute_frame_signals,
    detect_shots,
    energy_label,
    motion_label,
    quality_from_signals,
    window_long_shots,
)
from ..media import probe
from .cache import load_cached_clip, save_cached_clip
from .catalogue import MediaCatalogue, MediaClip, MediaSegment
from .describe import describe_segment

ProgressFn = Callable[[int, int, str], None]


def analyze_catalogue(
    clip_paths: list[str],
    *,
    use_cache: bool = True,
    force: bool = False,
    detect_speech: bool = False,
    enable_semantics: bool = True,
    on_progress: ProgressFn | None = None,
) -> MediaCatalogue:
    """Analyze each path into searchable segments. Prefer cache when valid.

    Runs ffmpeg frame sampling + numpy signal metrics (+ optional ONNX CLIP).
    Failures are recorded on ``catalogue.warnings`` instead of being swallowed.
    """
    if not clip_paths:
        raise ValueError("analyze_catalogue requires at least one clip path")

    clips: list[MediaClip] = []
    warnings: list[str] = []
    total = len(clip_paths)

    semantics_ok = False
    if enable_semantics:
        try:
            from ..analyzers import semantics as sem

            semantics_ok, sem_warn = sem.available()
            if sem_warn:
                warnings.append(sem_warn)
        except Exception as exc:  # pragma: no cover
            warnings.append(f"Semantic tagging unavailable: {exc}")
            semantics_ok = False

    for i, path in enumerate(clip_paths):
        resolved = str(Path(path).expanduser().resolve())
        name = Path(resolved).name
        if on_progress:
            on_progress(i + 1, total, f"{name} (cache)")
        clip: MediaClip | None = None
        if use_cache and not force:
            clip = load_cached_clip(resolved)
        if clip is None:
            if on_progress:
                on_progress(i + 1, total, f"{name} (sampling)")
            clip, clip_warnings = _analyze_clip(
                resolved,
                detect_speech=detect_speech,
                enable_semantics=semantics_ok,
                on_stage=lambda stage: on_progress(i + 1, total, f"{name} ({stage})")
                if on_progress
                else None,
            )
            warnings.extend(clip_warnings)
            if use_cache:
                save_cached_clip(clip)
        clips.append(clip)

    # Dedupe warnings while preserving order
    seen: set[str] = set()
    unique_warnings: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            unique_warnings.append(w)

    return MediaCatalogue(clips=clips, warnings=unique_warnings)


def _analyze_clip(
    path: str,
    *,
    detect_speech: bool = False,
    enable_semantics: bool = True,
    on_stage: Callable[[str], None] | None = None,
) -> tuple[MediaClip, list[str]]:
    warnings: list[str] = []
    info = probe(path)
    if info.fps <= 0:
        raise ValueError(f"Cannot catalogue video without fps: {path}")
    duration = info.duration_s or 0.0

    if on_stage:
        on_stage("sampling frames")
    try:
        sample = sample_frames(path)
    except Exception as exc:
        warnings.append(f"{Path(path).name}: frame sampling failed ({exc}); using full-clip fallback")
        return (
            _fallback_clip(path, info.fps, duration, warnings_note="no visual analysis"),
            warnings,
        )

    if on_stage:
        on_stage("measuring signals")
    frame_signals = compute_frame_signals(sample)
    shots = detect_shots(sample)
    if not shots and duration > 0:
        shots = [Interval(0.0, duration)]
    windows = window_long_shots(shots)

    speech_spans: list[Interval] = []
    if detect_speech:
        if on_stage:
            on_stage("speech")
        speech_spans = _detect_speech_safe(path, warnings)

    stem = Path(path).stem
    segments: list[MediaSegment] = []
    for scene_index, window in enumerate(windows):
        dur = max(0.0, window.end - window.start)
        if dur <= 0:
            continue
        sig = aggregate_signals(sample, frame_signals, window.start, window.end)
        motion = motion_label(sig.motion)
        energy = energy_label(sig.motion, sig.sharpness)
        speech = _overlaps_speech(window, speech_spans) if speech_spans else False

        tags: list[tuple[str, float]] = []
        embedding_b64: str | None = None
        if enable_semantics:
            if on_stage and scene_index == 0:
                on_stage("CLIP tags")
            tags, embedding_b64, sem_warn = _semantic_for_window(
                sample, window.start, window.end
            )
            if sem_warn:
                warnings.append(sem_warn)
                enable_semantics = False  # don't spam per window

        description, tag_labels = describe_segment(sig, tags)
        segments.append(
            MediaSegment(
                id=f"{stem}_{len(segments) + 1:03d}",
                start_s=round(window.start, 3),
                end_s=round(window.end, 3),
                duration_s=round(dur, 3),
                scene_index=scene_index,
                speech=speech,
                motion=motion,  # type: ignore[arg-type]
                energy=energy,  # type: ignore[arg-type]
                description=description,
                tags=tag_labels,
                quality_score=quality_from_signals(sig, dur),
                signals=sig.as_dict(),
                embedding=embedding_b64,
            )
        )

    # Representative thumbnail for the clip (first mid-frame)
    _maybe_write_clip_thumb(path, sample)

    return (
        MediaClip(
            media_path=path,
            source_fps=info.fps,
            duration_s=duration,
            captured_at=_capture_time(path),
            segments=segments,
        ),
        warnings,
    )


def _semantic_for_window(
    sample, start_s: float, end_s: float
) -> tuple[list[tuple[str, float]], str | None, str | None]:
    try:
        from ..analyzers import semantics as sem

        times = sample.times_s
        mask = (times >= start_s - 1e-6) & (times < end_s + 1e-6)
        idxs = np.where(mask)[0]
        if len(idxs) == 0:
            idxs = np.array(
                [int(np.argmin(np.abs(times - 0.5 * (start_s + end_s))))]
            )
        # Cap frames sent to CLIP per window
        if len(idxs) > 8:
            take = np.linspace(0, len(idxs) - 1, 8).astype(int)
            idxs = idxs[take]
        frames = sample.frames[idxs]
        result = sem.zero_shot_tags(frames)
        emb = sem.encode_embedding_b64(result.embedding)
        return result.tags, emb, result.warning
    except Exception as exc:  # pragma: no cover
        return [], None, f"CLIP failed: {exc}"


def _maybe_write_clip_thumb(path: str, sample) -> None:
    try:
        if len(sample.frames) == 0:
            return
        mid = sample.frames[len(sample.frames) // 2]
        out_dir = Path.cwd() / ".autoedit" / "thumbs"
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{Path(path).stem}.jpg"
        write_jpeg_thumbnail(mid, str(dest))
    except Exception:
        pass


def _fallback_clip(
    path: str, fps: float, duration: float, *, warnings_note: str
) -> MediaClip:
    windows = window_long_shots(
        [Interval(0.0, duration)] if duration > 0 else []
    )
    stem = Path(path).stem
    segments = []
    for i, w in enumerate(windows):
        dur = w.end - w.start
        segments.append(
            MediaSegment(
                id=f"{stem}_{i + 1:03d}",
                start_s=w.start,
                end_s=w.end,
                duration_s=dur,
                scene_index=i,
                speech=False,
                motion="medium",
                energy="medium",
                description=f"Unanalyzed window ({warnings_note})",
                tags=[],
                quality_score=0.4,
                signals={},
            )
        )
    return MediaClip(
        media_path=path,
        source_fps=fps,
        duration_s=duration,
        captured_at=_capture_time(path),
        segments=segments,
    )


def _detect_speech_safe(path: str, warnings: list[str]) -> list[Interval]:
    try:
        from ..analyzers.silence import detect_speech

        return detect_speech(path)
    except Exception as exc:
        warnings.append(f"{Path(path).name}: speech detection failed ({exc})")
        return []


def _overlaps_speech(shot: Interval, speech: list[Interval]) -> bool:
    for sp in speech:
        if sp.start < shot.end and sp.end > shot.start:
            overlap = min(shot.end, sp.end) - max(shot.start, sp.start)
            if overlap >= 0.5 or overlap / max(shot.duration, 1e-6) > 0.2:
                return True
    return False


def _capture_time(path: str) -> str | None:
    try:
        mtime = Path(path).stat().st_mtime
        return dt.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
    except OSError:
        return None
