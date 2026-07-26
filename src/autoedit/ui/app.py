"""Standalone Flet desktop UI for AutoEdit."""

from __future__ import annotations

import subprocess
import traceback
from pathlib import Path

from .. import engine
from ..applier import apply_plan
from ..models import EditPlan
from ..resolve_client import ResolveConnectionError, try_project_timeline_fps


VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".mxf", ".avi", ".mkv"}
AUDIO_EXTS = {".wav", ".mp3", ".aac", ".aiff", ".m4a", ".flac"}


def _osascript(script: str) -> str:
    """Run AppleScript; returns stdout (empty on cancel)."""
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        # User cancel is typically non-zero with empty/error text — treat as empty.
        return ""
    return (proc.stdout or "").strip()


def pick_video_files() -> list[str]:
    """Native macOS multi-select Open panel via AppleScript.

    Flet's FilePicker on desktop does not reliably enable multiple selection.
    Use UTIs (not bare extensions) so iPhone .MOV / QuickTime files stay enabled.
    """
    script = """
set theFiles to choose file with prompt "Select video clips" ¬
    of type {"public.movie", "public.mpeg-4", "com.apple.quicktime-movie", ¬
    "public.avi", "org.matroska.mkv", "com.apple.m4v-video"} ¬
    with multiple selections allowed
set out to ""
repeat with f in theFiles
    set out to out & (POSIX path of f) & linefeed
end repeat
return out
"""
    raw = _osascript(script)
    return [line.strip() for line in raw.splitlines() if line.strip()]


def pick_audio_file() -> str | None:
    script = """
set f to choose file with prompt "Select music" ¬
    of type {"public.audio", "wav", "mp3", "aac", "aiff", "m4a", "flac"}
return POSIX path of f
"""
    path = _osascript(script)
    return path or None


def pick_folder() -> str | None:
    script = """
set d to choose folder with prompt "Select a folder of clips"
return POSIX path of d
"""
    path = _osascript(script)
    return path or None


def main() -> None:
    try:
        import flet as ft  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "flet is not installed. Run: pip install 'autoedit[ui]'"
        ) from exc

    def app(page: ft.Page) -> None:
        page.title = "AutoEdit"
        page.window.width = 920
        page.window.height = 820
        page.padding = 20
        page.scroll = ft.ScrollMode.AUTO

        clip_paths: list[str] = []
        music_path: list[str | None] = [None]
        last_plan: list[EditPlan | None] = [None]

        clips_col = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, height=160)
        clips_count = ft.Text("0 clips", size=12, color=ft.Colors.GREY_600)
        music_label = ft.Text("No music", size=13)
        status = ft.Text("Ready", size=12, color=ft.Colors.GREY_700)
        summary = ft.Text("", size=13)
        analysis_line = ft.Text("", size=11, color=ft.Colors.GREY_600)
        shots_col = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, height=280)
        last_storyboard: list = [None]
        create_btn = ft.FilledButton("Create First Cut", on_click=None)
        apply_btn = ft.OutlinedButton("Apply to Resolve", on_click=None)
        story_field = ft.TextField(
            label="Story",
            hint_text="Tell the editor what happened or what the film should communicate.",
            multiline=True,
            min_lines=6,
            max_lines=12,
            expand=True,
        )
        mode = ft.RadioGroup(
            content=ft.Row(
                [
                    ft.Radio(value="story", label="Story"),
                    ft.Radio(value="assemble", label="Assemble"),
                    ft.Radio(value="montage", label="Montage"),
                ]
            ),
            value="story",
        )
        assemble_opt = ft.Dropdown(
            label="Per-clip treatment",
            value="scenes",
            options=[
                ft.dropdown.Option("scenes", "Scenes"),
                ft.dropdown.Option("silence", "Remove Silence"),
                ft.dropdown.Option("none", "Keep Full Clips"),
            ],
            width=220,
        )
        style_dd = ft.Dropdown(
            label="Style",
            value="Adventure documentary",
            options=[
                ft.dropdown.Option("Adventure documentary"),
                ft.dropdown.Option("Travel montage"),
                ft.dropdown.Option("Action short"),
            ],
            width=240,
        )
        duration_field = ft.TextField(label="Target length (sec)", value="60", width=160)
        timeline_field = ft.TextField(label="Timeline", value="First Cut", width=220)
        fps_field = ft.TextField(label="FPS (empty = Auto)", value="", width=160)
        beats_field = ft.TextField(label="Beats per clip", value="4", width=140)

        def set_status(msg: str, *, error: bool = False) -> None:
            status.value = msg
            status.color = ft.Colors.RED_700 if error else ft.Colors.GREY_700
            page.update()

        def refresh_resolve_status() -> None:
            """Probe Resolve off the UI thread — scriptapp can block for a long time."""
            set_status("Checking Resolve…")

            def work() -> None:
                try:
                    fps = try_project_timeline_fps()
                    if fps:
                        status.value = f"Resolve connected · project {fps:g} fps"
                        status.color = ft.Colors.GREY_700
                    else:
                        status.value = "Resolve not connected (preview still works)"
                        status.color = ft.Colors.GREY_700
                except Exception as exc:
                    status.value = f"Resolve check failed: {exc}"
                    status.color = ft.Colors.RED_700
                page.update()

            page.run_thread(work)

        def refresh_clips() -> None:
            clips_col.controls.clear()
            for i, path in enumerate(clip_paths):
                name = Path(path).name

                def make_remove(idx: int):
                    def _rm(_e):
                        if 0 <= idx < len(clip_paths):
                            clip_paths.pop(idx)
                            refresh_clips()

                    return _rm

                def make_up(idx: int):
                    def _up(_e):
                        if idx > 0:
                            clip_paths[idx - 1], clip_paths[idx] = (
                                clip_paths[idx],
                                clip_paths[idx - 1],
                            )
                            refresh_clips()

                    return _up

                clips_col.controls.append(
                    ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.ARROW_UPWARD,
                                tooltip="Move up",
                                on_click=make_up(i),
                                icon_size=16,
                            ),
                            ft.Text(name, expand=True, size=13),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                tooltip="Remove",
                                on_click=make_remove(i),
                                icon_size=16,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    )
                )
            clips_count.value = f"{len(clip_paths)} clip(s)"
            page.update()

        def add_paths(paths: list[str]) -> None:
            for p in paths:
                path = Path(p)
                if path.is_dir():
                    for child in sorted(path.iterdir()):
                        if child.is_file() and child.suffix.lower() in VIDEO_EXTS:
                            if str(child) not in clip_paths:
                                clip_paths.append(str(child))
                    continue
                suf = path.suffix.lower()
                if suf in VIDEO_EXTS:
                    if p not in clip_paths:
                        clip_paths.append(p)
                elif suf in AUDIO_EXTS:
                    music_path[0] = p
                    music_label.value = path.name
            refresh_clips()
            page.update()

        def pick_clips(_e) -> None:
            paths = pick_video_files()
            if paths:
                add_paths(paths)
                set_status(f"Added {len(paths)} clip(s)")

        def pick_folder_btn(_e) -> None:
            folder = pick_folder()
            if folder:
                before = len(clip_paths)
                add_paths([folder])
                set_status(
                    f"Added {len(clip_paths) - before} videos from {Path(folder).name}"
                )

        def pick_music(_e) -> None:
            path = pick_audio_file()
            if path:
                add_paths([path])

        def clear_music(_e) -> None:
            music_path[0] = None
            music_label.value = "No music"
            page.update()

        def refresh_shots(board=None, plan=None) -> None:
            shots_col.controls.clear()
            last_storyboard[0] = board
            warns = list(getattr(board, "analysis_warnings", None) or [])
            if warns:
                analysis_line.value = "Analysis: " + " · ".join(warns[:3])
                analysis_line.color = ft.Colors.ORANGE_700
            elif board is not None:
                analysis_line.value = (
                    "Analysis: ffmpeg frames + visual signals"
                    + (" + CLIP tags" if any(
                        (s.fill and s.fill.tags) for s in board.slots
                    ) else "")
                )
                analysis_line.color = ft.Colors.GREY_600
            else:
                analysis_line.value = ""

            if board is None:
                page.update()
                return

            for slot in board.slots:
                fill = slot.fill
                if fill is None:
                    continue
                name = Path(fill.media_path).name
                thumb = Path.cwd() / ".autoedit" / "thumbs" / f"{Path(fill.media_path).stem}.jpg"
                left: list = []
                if thumb.is_file():
                    left.append(
                        ft.Image(
                            src=str(thumb),
                            width=72,
                            height=72,
                            fit=ft.BoxFit.COVER,
                            border_radius=4,
                        )
                    )
                desc = fill.descriptor or "(no descriptor)"
                tags = ", ".join(fill.tags[:4]) if fill.tags else ""
                left.append(
                    ft.Column(
                        [
                            ft.Text(
                                f"{name}  {fill.start_s:.1f}s–"
                                f"{fill.start_s + fill.duration_s:.1f}s"
                                f"  ·  score {fill.score:.2f}",
                                size=12,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(desc, size=12),
                            ft.Text(
                                fill.reason or "",
                                size=11,
                                color=ft.Colors.GREY_600,
                            ),
                            ft.Text(
                                f"tags: {tags}" if tags else "",
                                size=11,
                                color=ft.Colors.BLUE_GREY_400,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    )
                )
                shots_col.controls.append(ft.Row(left, spacing=10, vertical_alignment=ft.CrossAxisAlignment.START))
            page.update()

        def parse_fps() -> float | None:
            raw = (fps_field.value or "").strip()
            if not raw:
                return None
            return float(raw)

        def create_first_cut(_e) -> None:
            if create_btn.disabled:
                return
            m = mode.value or "story"
            name = (timeline_field.value or "First Cut").strip()
            try:
                fps = parse_fps()
            except ValueError:
                set_status("FPS must be a number", error=True)
                return

            if not clip_paths:
                set_status("Add at least one clip", error=True)
                return
            if m == "story" and not (story_field.value or "").strip():
                set_status("Story text is required", error=True)
                return
            if m == "montage" and not music_path[0]:
                set_status("Montage requires a music track", error=True)
                return

            create_btn.disabled = True
            apply_btn.disabled = True
            set_status(f"Working… {len(clip_paths)} clip(s). Please wait.")
            summary.value = "Building first cut…"
            page.update()

            story_text = (story_field.value or "").strip()
            duration = float(duration_field.value or "60")
            style = style_dd.value
            per_clip = assemble_opt.value or "scenes"
            beats = int(beats_field.value or "4")
            music = music_path[0]
            clips = list(clip_paths)

            def work() -> None:
                try:
                    def on_progress(i: int, total: int, filename: str) -> None:
                        status.value = f"Analyzing {i}/{total}: {filename}"
                        page.update()

                    if m == "story":
                        sb_path = Path(f"{name.replace(' ', '_')}.storyboard.json")
                        plan = engine.build_story_plan(
                            clip_paths=clips,
                            story=story_text,
                            timeline_name=name,
                            target_duration_s=duration,
                            music_path=music,
                            style=style,
                            timeline_fps=fps,
                            save_storyboard_path=sb_path,
                            on_progress=on_progress,
                        )
                        coverage = ""
                        board = None
                        try:
                            from ..storyboard import Storyboard

                            board = Storyboard.load(sb_path)
                            coverage = f" · story coverage {board.coverage:.0%}"
                        except Exception:
                            pass
                        refresh_shots(board, plan)
                    elif m == "assemble":
                        plan = engine.build_assemble_plan(
                            clips,
                            timeline_name=name,
                            per_clip=per_clip,
                            music_path=music,
                            timeline_fps=fps,
                        )
                        coverage = ""
                        refresh_shots(None, plan)
                    else:
                        plan = engine.build_montage_plan(
                            timeline_name=name,
                            music_path=music or "",
                            broll_paths=clips,
                            beats_per_clip=beats,
                            timeline_fps=fps,
                        )
                        coverage = ""
                        refresh_shots(None, plan)

                    out = Path(f"{name.replace(' ', '_')}.plan.json")
                    plan.save(out)
                    last_plan[0] = plan
                    dur_s = plan.duration_frames / plan.fps if plan.fps else 0
                    marker_bit = (
                        f" · {len(plan.markers)} markers" if plan.markers else ""
                    )
                    summary.value = (
                        f"{len(plan.clips)} edits · {dur_s:.0f}s @ {plan.fps:g} fps"
                        f"{coverage}{marker_bit}\nSaved {out.name}"
                    )
                    status.value = "First cut ready"
                    status.color = ft.Colors.GREY_700
                except Exception as exc:
                    summary.value = ""
                    shots_col.controls.clear()
                    analysis_line.value = ""
                    status.value = str(exc)
                    status.color = ft.Colors.RED_700
                    traceback.print_exc()
                finally:
                    create_btn.disabled = False
                    apply_btn.disabled = False
                    page.update()

            page.run_thread(work)

        def do_apply(_e) -> None:
            plan = last_plan[0]
            if plan is None:
                set_status("Create a first cut before applying", error=True)
                return
            apply_btn.disabled = True
            set_status("Applying to Resolve…")
            page.update()

            def work() -> None:
                try:
                    result = apply_plan(plan)
                    status.value = (
                        f"Applied '{result.timeline_name}' · {result.clip_count} clips"
                    )
                    status.color = ft.Colors.GREY_700
                except ResolveConnectionError as exc:
                    status.value = str(exc)
                    status.color = ft.Colors.RED_700
                except Exception as exc:
                    status.value = str(exc)
                    status.color = ft.Colors.RED_700
                    traceback.print_exc()
                finally:
                    apply_btn.disabled = False
                    page.update()

            page.run_thread(work)

        create_btn.on_click = create_first_cut
        apply_btn.on_click = do_apply

        media_box = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("MEDIA", weight=ft.FontWeight.BOLD),
                            clips_count,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    clips_col,
                    ft.Row(
                        [
                            ft.OutlinedButton("Add clips…", on_click=pick_clips),
                            ft.OutlinedButton("Add folder…", on_click=pick_folder_btn),
                            ft.OutlinedButton("Add music…", on_click=pick_music),
                            ft.TextButton("Clear music", on_click=clear_music),
                        ]
                    ),
                    ft.Text(
                        "Add folder…: open the folder, then click Choose "
                        "(files look greyed — that is normal; .mov/.mp4 inside are imported). "
                        "Or Add clips… to pick files.",
                        size=11,
                        color=ft.Colors.GREY_600,
                    ),
                    ft.Row([ft.Text("Music:", size=13), music_label]),
                ]
            ),
            padding=12,
            border=ft.Border(
                top=ft.BorderSide(1, ft.Colors.GREY_400),
                right=ft.BorderSide(1, ft.Colors.GREY_400),
                bottom=ft.BorderSide(1, ft.Colors.GREY_400),
                left=ft.BorderSide(1, ft.Colors.GREY_400),
            ),
            border_radius=8,
        )

        page.add(
            media_box,
            ft.Container(height=12),
            ft.Text("STORY", weight=ft.FontWeight.BOLD),
            story_field,
            ft.Container(height=12),
            ft.Text("EDIT", weight=ft.FontWeight.BOLD),
            mode,
            ft.Row([assemble_opt, style_dd, duration_field, beats_field]),
            ft.Row([timeline_field, fps_field]),
            ft.Row(
                [
                    create_btn,
                    apply_btn,
                    ft.TextButton(
                        "Refresh status",
                        on_click=lambda e: refresh_resolve_status(),
                    ),
                ]
            ),
            ft.Container(height=8),
            ft.Text("FIRST CUT", weight=ft.FontWeight.BOLD),
            summary,
            analysis_line,
            shots_col,
            ft.Divider(),
            status,
        )
        refresh_resolve_status()

    ft.app(target=app)


if __name__ == "__main__":
    main()
