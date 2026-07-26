"""FastMCP server exposing the auto-edit engine.

Tools: analyze_media, plan_silence/transcript/scenes/montage, preview_plan,
apply_plan. Register alongside samuelgursky/davinci-resolve-mcp in Cursor.
"""

from __future__ import annotations

from typing import Any, Optional

from . import engine
from .media import probe
from .models import EditPlan


def _build_server():
    try:
        from fastmcp import FastMCP  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "fastmcp is not installed. Install extras: pip install 'autoedit[mcp]'."
        ) from exc

    mcp = FastMCP("autoedit")

    @mcp.tool()
    def analyze_media(path: str) -> dict[str, Any]:
        """Probe a media file for fps/duration/streams."""
        info = probe(path)
        return {
            "path": info.path,
            "fps": info.fps,
            "duration_s": info.duration_s,
            "has_video": info.has_video,
            "has_audio": info.has_audio,
        }

    @mcp.tool()
    def analyze_catalogue(
        clip_paths: list[str],
        force: bool = False,
        enable_semantics: bool = True,
    ) -> dict[str, Any]:
        """Build a MediaCatalogue with visual signals, descriptors, and tags."""
        from .analysis import analyze_catalogue as _analyze

        catalogue = _analyze(
            clip_paths,
            force=force,
            enable_semantics=enable_semantics,
        )
        return {
            "catalogue": catalogue.to_dict(),
            "report": catalogue.summary_report(),
            "warnings": catalogue.warnings,
        }

    @mcp.tool()
    def plan_silence(
        path: str,
        out_timeline: str,
        noise_db: float = -30.0,
        min_silence_s: float = 0.5,
        padding_s: Optional[float] = None,
        min_gap_s: Optional[float] = None,
        timeline_fps: Optional[float] = None,
    ) -> dict[str, Any]:
        """Build a silence-removal EditPlan and return it as a dict."""
        return engine.build_silence_plan(
            media_path=path,
            timeline_name=out_timeline,
            noise_db=noise_db,
            min_silence_s=min_silence_s,
            padding_s=padding_s,
            min_gap_s=min_gap_s,
            timeline_fps=timeline_fps,
        ).to_dict()

    @mcp.tool()
    def plan_transcript(
        path: str,
        out_timeline: str,
        delete_words: Optional[list[str]] = None,
        keep_keywords: Optional[list[str]] = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
        timeline_fps: Optional[float] = None,
    ) -> dict[str, Any]:
        """Build a transcript-editing EditPlan and return it as a dict."""
        return engine.build_transcript_plan(
            media_path=path,
            timeline_name=out_timeline,
            delete_words=delete_words,
            keep_keywords=keep_keywords,
            model_name=model,
            language=language,
            timeline_fps=timeline_fps,
        ).to_dict()

    @mcp.tool()
    def plan_scenes(
        path: str,
        out_timeline: str,
        threshold: float = 27.0,
        min_scene_s: float = 0.0,
        max_scene_s: Optional[float] = None,
        order: str = "source",
        limit: Optional[int] = None,
        timeline_fps: Optional[float] = None,
    ) -> dict[str, Any]:
        """Build a scene-assembly EditPlan and return it as a dict."""
        return engine.build_scene_plan(
            media_path=path,
            timeline_name=out_timeline,
            threshold=threshold,
            min_scene_s=min_scene_s,
            max_scene_s=max_scene_s,
            order=order,
            limit=limit,
            timeline_fps=timeline_fps,
        ).to_dict()

    @mcp.tool()
    def plan_montage(
        music_path: str,
        out_timeline: str,
        broll_paths: Optional[list[str]] = None,
        broll_folder: Optional[str] = None,
        beats_per_clip: int = 4,
        reuse_policy: str = "cycle",
        timeline_fps: Optional[float] = None,
    ) -> dict[str, Any]:
        """Build a music-montage EditPlan and return it as a dict."""
        return engine.build_montage_plan(
            timeline_name=out_timeline,
            music_path=music_path,
            broll_paths=broll_paths,
            broll_folder=broll_folder,
            beats_per_clip=beats_per_clip,
            reuse_policy=reuse_policy,  # type: ignore[arg-type]
            timeline_fps=timeline_fps,
        ).to_dict()

    @mcp.tool()
    def plan_assemble(
        clip_paths: list[str],
        out_timeline: str,
        per_clip: str = "scenes",
        music_path: Optional[str] = None,
        timeline_fps: Optional[float] = None,
    ) -> dict[str, Any]:
        """Per-clip analyze/edit then stitch. per_clip: scenes|silence|none."""
        return engine.build_assemble_plan(
            clip_paths,
            timeline_name=out_timeline,
            per_clip=per_clip,
            music_path=music_path,
            timeline_fps=timeline_fps,
        ).to_dict()

    @mcp.tool()
    def plan_story(
        clip_paths: list[str],
        story: str,
        out_timeline: str,
        target_duration_s: float = 60.0,
        music_path: Optional[str] = None,
        style: Optional[str] = None,
        timeline_fps: Optional[float] = None,
    ) -> dict[str, Any]:
        """Autonomous first cut from story text + clips."""
        return engine.build_story_plan(
            clip_paths=clip_paths,
            story=story,
            timeline_name=out_timeline,
            target_duration_s=target_duration_s,
            music_path=music_path,
            style=style,
            timeline_fps=timeline_fps,
        ).to_dict()

    @mcp.tool()
    def preview_plan(plan: dict[str, Any]) -> dict[str, Any]:
        """Validate an EditPlan dict and echo it back with a summary. No Resolve."""
        edit_plan = EditPlan.from_dict(plan)
        edit_plan.validate()
        return {
            "valid": True,
            "clip_count": len(edit_plan.clips),
            "duration_frames": edit_plan.duration_frames,
            "plan": edit_plan.to_dict(),
        }

    @mcp.tool()
    def apply_plan(plan: dict[str, Any]) -> dict[str, Any]:
        """Apply an EditPlan dict to Resolve (Resolve must be running)."""
        from .applier import apply_plan as _apply

        edit_plan = EditPlan.from_dict(plan)
        result = _apply(edit_plan)
        return {
            "timeline_name": result.timeline_name,
            "clip_count": result.clip_count,
            "marker_count": result.marker_count,
            "duration_frames": result.duration_frames,
            "music_applied": result.music_applied,
        }

    return mcp


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    _build_server().run()


if __name__ == "__main__":
    main()
