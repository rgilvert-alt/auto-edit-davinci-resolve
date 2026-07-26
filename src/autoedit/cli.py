"""Typer CLI for the auto-edit engine.

Each mode command builds an EditPlan, writes it to JSON, and optionally
previews or applies it to Resolve via the single applier path.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import typer

from . import engine
from .models import EditPlan
from .planners.assemble import AssembleSource

app = typer.Typer(
    add_completion=False,
    help="Auto-edit engine for DaVinci Resolve: story, assemble, montage, and more.",
    no_args_is_help=True,
)

_TIMELINE_FPS_HELP = (
    "Timeline frame rate. Defaults to the open Resolve project, "
    "else the source rate."
)


def _default_plan_path(timeline_name: str) -> Path:
    slug = re.sub(r"[^\w.-]+", "_", timeline_name).strip("_") or "plan"
    return Path(f"{slug}.plan.json")


def _finalize(plan: EditPlan, out: Optional[Path], preview: bool, do_apply: bool) -> None:
    plan.validate()
    out = out or _default_plan_path(plan.timeline_name)
    plan.save(out)
    typer.echo(
        f"Wrote plan: {out}  ({len(plan.clips)} clips, "
        f"{plan.duration_frames} frames @ {plan.fps} fps)"
    )
    if preview:
        typer.echo(plan.to_json())
    if do_apply:
        _apply(plan)


def _apply(plan: EditPlan) -> None:
    from .applier import apply_plan

    result = apply_plan(plan)
    typer.echo(
        f"Applied to Resolve: timeline '{result.timeline_name}', "
        f"{result.clip_count} clips, {result.marker_count} markers, "
        f"music={'yes' if result.music_applied else 'no'}."
    )


def _read_story(story: Optional[Path], story_text: Optional[str]) -> str:
    if story_text:
        return story_text
    if story:
        return Path(story).read_text(encoding="utf-8")
    raise typer.BadParameter("Provide --story FILE or --story-text TEXT")


@app.command()
def silence(
    path: str = typer.Argument(..., help="Media file to cut."),
    out_timeline: str = typer.Option(..., "--out-timeline", help="Timeline name."),
    out: Optional[Path] = typer.Option(None, "--out", help="Plan JSON path."),
    noise_db: float = typer.Option(-30.0, "--noise-db"),
    min_silence: float = typer.Option(0.5, "--min-silence"),
    padding: Optional[float] = typer.Option(None, "--padding"),
    min_gap: Optional[float] = typer.Option(None, "--min-gap"),
    timeline_fps: Optional[float] = typer.Option(
        None, "--timeline-fps", help=_TIMELINE_FPS_HELP
    ),
    preview: bool = typer.Option(False, "--preview"),
    do_apply: bool = typer.Option(False, "--apply"),
) -> None:
    """Silence removal -> jump-cut EditPlan."""
    plan = engine.build_silence_plan(
        media_path=path,
        timeline_name=out_timeline,
        noise_db=noise_db,
        min_silence_s=min_silence,
        padding_s=padding,
        min_gap_s=min_gap,
        timeline_fps=timeline_fps,
    )
    _finalize(plan, out, preview, do_apply)


@app.command()
def transcript(
    path: str = typer.Argument(..., help="Media file to transcribe/cut."),
    out_timeline: str = typer.Option(..., "--out-timeline"),
    out: Optional[Path] = typer.Option(None, "--out"),
    delete: list[str] = typer.Option([], "--delete", help="Word to drop (repeatable)."),
    keyword: list[str] = typer.Option(
        [], "--filter", help="Keep only segments with this keyword (repeatable)."
    ),
    model: Optional[str] = typer.Option(None, "--model", help="Whisper model."),
    language: Optional[str] = typer.Option(None, "--language"),
    timeline_fps: Optional[float] = typer.Option(
        None, "--timeline-fps", help=_TIMELINE_FPS_HELP
    ),
    preview: bool = typer.Option(False, "--preview"),
    do_apply: bool = typer.Option(False, "--apply"),
) -> None:
    """Transcript editing -> EditPlan (delete words or keyword filter)."""
    plan = engine.build_transcript_plan(
        media_path=path,
        timeline_name=out_timeline,
        delete_words=list(delete) or None,
        keep_keywords=list(keyword) or None,
        model_name=model,
        language=language,
        timeline_fps=timeline_fps,
    )
    _finalize(plan, out, preview, do_apply)


@app.command()
def scenes(
    path: str = typer.Argument(..., help="Media file to split into shots."),
    out_timeline: str = typer.Option(..., "--out-timeline"),
    out: Optional[Path] = typer.Option(None, "--out"),
    threshold: float = typer.Option(27.0, "--threshold"),
    min_scene: float = typer.Option(0.0, "--min-scene"),
    max_scene: Optional[float] = typer.Option(None, "--max-scene"),
    order: str = typer.Option("source", "--order", help="source|longest|shortest"),
    limit: Optional[int] = typer.Option(None, "--limit"),
    timeline_fps: Optional[float] = typer.Option(
        None, "--timeline-fps", help=_TIMELINE_FPS_HELP
    ),
    preview: bool = typer.Option(False, "--preview"),
    do_apply: bool = typer.Option(False, "--apply"),
) -> None:
    """Scene assembly -> rough cut EditPlan with a marker per scene."""
    plan = engine.build_scene_plan(
        media_path=path,
        timeline_name=out_timeline,
        threshold=threshold,
        min_scene_s=min_scene,
        max_scene_s=max_scene,
        order=order,
        limit=limit,
        timeline_fps=timeline_fps,
    )
    _finalize(plan, out, preview, do_apply)


@app.command()
def assemble(
    clip: list[str] = typer.Option(..., "--clip", help="Video clip (repeatable)."),
    out_timeline: str = typer.Option(..., "--out-timeline"),
    out: Optional[Path] = typer.Option(None, "--out"),
    per_clip: str = typer.Option(
        "scenes",
        "--per-clip",
        help="scenes | silence | none (Keep Full Clips)",
    ),
    music: Optional[str] = typer.Option(None, "--music"),
    timeline_fps: Optional[float] = typer.Option(
        None, "--timeline-fps", help=_TIMELINE_FPS_HELP
    ),
    preview: bool = typer.Option(False, "--preview"),
    do_apply: bool = typer.Option(False, "--apply"),
) -> None:
    """Per-clip analyze/edit, then stitch in order."""
    if per_clip not in {"scenes", "silence", "none"}:
        raise typer.BadParameter("--per-clip must be scenes|silence|none")
    sources = [AssembleSource(path=c, mode=per_clip) for c in clip]  # type: ignore[arg-type]
    plan = engine.build_assemble_plan(
        sources,
        timeline_name=out_timeline,
        music_path=music,
        timeline_fps=timeline_fps,
    )
    _finalize(plan, out, preview, do_apply)


@app.command()
def montage(
    out_timeline: str = typer.Option(..., "--out-timeline"),
    music: str = typer.Option(..., "--music", help="Music track (required)."),
    clip: list[str] = typer.Option([], "--clip", help="Video clip (repeatable)."),
    broll: Optional[str] = typer.Argument(
        None, help="Optional folder of b-roll clips."
    ),
    out: Optional[Path] = typer.Option(None, "--out"),
    beats_per_clip: int = typer.Option(4, "--beats-per-clip"),
    reuse_policy: str = typer.Option(
        "cycle", "--reuse-policy", help="cycle | stop | reuse_best"
    ),
    timeline_fps: Optional[float] = typer.Option(
        None, "--timeline-fps", help=_TIMELINE_FPS_HELP
    ),
    preview: bool = typer.Option(False, "--preview"),
    do_apply: bool = typer.Option(False, "--apply"),
) -> None:
    """Music montage -> beat-synced EditPlan."""
    plan = engine.build_montage_plan(
        timeline_name=out_timeline,
        music_path=music,
        broll_paths=list(clip) or None,
        broll_folder=broll,
        beats_per_clip=beats_per_clip,
        reuse_policy=reuse_policy,  # type: ignore[arg-type]
        timeline_fps=timeline_fps,
    )
    _finalize(plan, out, preview, do_apply)


@app.command("analyze")
def analyze_cmd(
    clip: list[str] = typer.Option(..., "--clip", help="Video clip (repeatable)."),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Write MediaCatalogue JSON."
    ),
    report: Optional[Path] = typer.Option(
        None, "--report", help="Write human-readable analysis report."
    ),
    force: bool = typer.Option(False, "--force", help="Ignore analysis cache."),
    no_semantics: bool = typer.Option(
        False, "--no-semantics", help="Skip ONNX CLIP tagging."
    ),
) -> None:
    """Analyse clips into a MediaCatalogue with descriptors and signals."""
    from .analysis import analyze_catalogue

    def _progress(i: int, total: int, label: str) -> None:
        typer.echo(f"[{i}/{total}] {label}")

    catalogue = analyze_catalogue(
        list(clip),
        force=force,
        enable_semantics=not no_semantics,
        on_progress=_progress,
    )
    out_path = out or Path("catalogue.json")
    catalogue.save(out_path)
    typer.echo(f"Wrote catalogue: {out_path}")
    text = catalogue.summary_report()
    if report:
        report.write_text(text, encoding="utf-8")
        typer.echo(f"Wrote report: {report}")
    else:
        typer.echo(text)


@app.command()
def story(
    out_timeline: str = typer.Option(..., "--out-timeline"),
    clip: list[str] = typer.Option(..., "--clip", help="Video clip (repeatable)."),
    story: Optional[Path] = typer.Option(None, "--story", help="Story text file."),
    story_text: Optional[str] = typer.Option(None, "--story-text"),
    duration: float = typer.Option(60.0, "--duration", help="Target length seconds."),
    music: Optional[str] = typer.Option(None, "--music"),
    style: Optional[str] = typer.Option(None, "--style"),
    out: Optional[Path] = typer.Option(None, "--out"),
    storyboard_out: Optional[Path] = typer.Option(
        None, "--storyboard-out", help="Write filled storyboard JSON."
    ),
    timeline_fps: Optional[float] = typer.Option(
        None, "--timeline-fps", help=_TIMELINE_FPS_HELP
    ),
    preview: bool = typer.Option(False, "--preview"),
    do_apply: bool = typer.Option(False, "--apply"),
) -> None:
    """Autonomous first cut from Story text + clips."""
    text = _read_story(story, story_text)
    sb_path = storyboard_out
    if sb_path is None:
        slug = re.sub(r"[^\w.-]+", "_", out_timeline).strip("_") or "story"
        sb_path = Path(f"{slug}.storyboard.json")
    plan = engine.build_story_plan(
        clip_paths=list(clip),
        story=text,
        timeline_name=out_timeline,
        target_duration_s=duration,
        music_path=music,
        style=style,
        timeline_fps=timeline_fps,
        save_storyboard_path=sb_path,
    )
    typer.echo(f"Wrote storyboard: {sb_path}")
    _finalize(plan, out, preview, do_apply)


@app.command()
def preview(plan_path: Path = typer.Argument(..., help="EditPlan JSON to inspect.")) -> None:
    """Load an EditPlan JSON, validate it, and print it. Never touches Resolve."""
    plan = EditPlan.load(plan_path)
    plan.validate()
    typer.echo(plan.to_json())


@app.command()
def apply(plan_path: Path = typer.Argument(..., help="EditPlan JSON to apply.")) -> None:
    """Apply an existing EditPlan JSON to Resolve (Resolve must be running)."""
    plan = EditPlan.load(plan_path)
    _apply(plan)


if __name__ == "__main__":
    app()
