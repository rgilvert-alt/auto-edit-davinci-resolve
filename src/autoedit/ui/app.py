"""Standalone Flet desktop UI for AutoEdit."""

from __future__ import annotations

import traceback
from pathlib import Path

from .. import engine
from ..applier import apply_plan
from ..models import EditPlan
from ..resolve_client import ResolveConnectionError, try_project_timeline_fps
from ..storyboard import Storyboard, coverage_report, swap_to_candidate


VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".mxf", ".avi", ".mkv"}
AUDIO_EXTS = {".wav", ".mp3", ".aac", ".aiff", ".m4a", ".flac"}
VIDEO_EXTENSIONS = ["mov", "mp4", "m4v", "mxf", "avi", "mkv"]
AUDIO_EXTENSIONS = ["wav", "mp3", "aac", "aiff", "m4a", "flac"]
TRIM_STEP_S = 0.5


def main() -> None:
    try:
        import flet as ft  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "flet is not installed. Run: pip install 'autoedit[ui]'"
        ) from exc

    def app(page: ft.Page) -> None:
        page.title = "AutoEdit"
        page.window.width = 960
        page.window.height = 900
        page.padding = 20
        page.scroll = ft.ScrollMode.AUTO

        clip_paths: list[str] = []
        music_path: list[str | None] = [None]
        last_plan: list[EditPlan | None] = [None]
        last_storyboard: list[Storyboard | None] = [None]
        storyboard_path: list[Path | None] = [None]

        clips_col = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, height=160)
        clips_count = ft.Text("0 clips", size=12, color=ft.Colors.GREY_600)
        music_label = ft.Text("No music", size=13)
        status = ft.Text("Ready", size=12, color=ft.Colors.GREY_700)
        summary = ft.Text("", size=13)
        analysis_line = ft.Text("", size=11, color=ft.Colors.GREY_600)
        coverage_line = ft.Text("", size=11, color=ft.Colors.GREY_600)
        shots_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, height=320)
        create_btn = ft.FilledButton("Create First Cut", on_click=None)
        revise_btn = ft.OutlinedButton(
            "Revise unlocked", on_click=None, disabled=True
        )
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
        duration_field = ft.TextField(
            label="Sequence length (sec)", value="60", width=180
        )
        timeline_field = ft.TextField(label="Timeline", value="First Cut", width=220)
        fps_field = ft.TextField(label="FPS (empty = Auto)", value="", width=160)
        beats_field = ft.TextField(label="Beats per clip", value="4", width=140)
        story_section = ft.Column([ft.Text("STORY", weight=ft.FontWeight.BOLD), story_field])
        controls_row = ft.Row([assemble_opt, style_dd, duration_field, beats_field])

        def set_status(msg: str, *, error: bool = False) -> None:
            status.value = msg
            status.color = ft.Colors.RED_700 if error else ft.Colors.GREY_700
            page.update()

        def sync_mode_visibility(_e=None) -> None:
            m = mode.value or "story"
            story_section.visible = m == "story"
            assemble_opt.visible = m == "assemble"
            style_dd.visible = m == "story"
            duration_field.visible = m == "story"
            beats_field.visible = m == "montage"
            revise_btn.visible = m == "story"
            page.update()

        mode.on_change = sync_mode_visibility

        def refresh_resolve_status() -> None:
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

        async def pick_clips(_e) -> None:
            set_status("Opening clip picker…")
            try:
                files = await ft.FilePicker().pick_files(
                    dialog_title="Select video clips",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=VIDEO_EXTENSIONS,
                    allow_multiple=True,
                )
            except Exception as exc:
                set_status(f"Clip picker failed: {exc}", error=True)
                traceback.print_exc()
                return
            paths = [f.path for f in (files or []) if getattr(f, "path", None)]
            if not paths:
                set_status("No clips selected")
                return
            add_paths(paths)
            set_status(f"Added {len(paths)} clip(s)")

        async def pick_folder_btn(_e) -> None:
            set_status("Opening folder picker…")
            try:
                folder = await ft.FilePicker().get_directory_path(
                    dialog_title="Select a folder of clips"
                )
            except Exception as exc:
                set_status(f"Folder picker failed: {exc}", error=True)
                traceback.print_exc()
                return
            if not folder:
                set_status("No folder selected")
                return
            before = len(clip_paths)
            add_paths([folder])
            set_status(
                f"Added {len(clip_paths) - before} videos from {Path(folder).name}"
            )

        async def pick_music(_e) -> None:
            set_status("Opening music picker…")
            try:
                files = await ft.FilePicker().pick_files(
                    dialog_title="Select music",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=AUDIO_EXTENSIONS,
                    allow_multiple=False,
                )
            except Exception as exc:
                set_status(f"Music picker failed: {exc}", error=True)
                traceback.print_exc()
                return
            paths = [f.path for f in (files or []) if getattr(f, "path", None)]
            if not paths:
                set_status("No music selected")
                return
            add_paths(paths)
            set_status(f"Music: {Path(paths[0]).name}")

        def clear_music(_e) -> None:
            music_path[0] = None
            music_label.value = "No music"
            set_status("Music cleared")

        def persist_board_and_plan() -> EditPlan | None:
            board = last_storyboard[0]
            path = storyboard_path[0]
            if board is None or path is None:
                return None
            board.save(path)
            plan = engine.rebuild_story_plan(
                path,
                timeline_name=(timeline_field.value or board.title or "First Cut").strip(),
                music_path=music_path[0] if music_path[0] else board.music_path,
                snap_to_beats=False,
            )
            last_plan[0] = plan
            last_storyboard[0] = Storyboard.load(path)
            return plan

        def update_summary(plan: EditPlan | None, board: Storyboard | None) -> None:
            if plan is None:
                summary.value = ""
                coverage_line.value = ""
                revise_btn.disabled = True
                return
            dur_s = plan.duration_frames / plan.fps if plan.fps else 0
            coverage = ""
            rev = ""
            if board is not None:
                coverage = f" · story coverage {board.coverage:.0%}"
                rev = f" · rev {board.revision}"
                if board.last_timeline_name:
                    rev += f" · last applied “{board.last_timeline_name}”"
                if board.catalogue_path and Path(board.catalogue_path).is_file():
                    try:
                        from ..analysis.catalogue import MediaCatalogue

                        cat = MediaCatalogue.load(board.catalogue_path)
                        coverage_line.value = "Coverage: " + coverage_report(
                            board, cat
                        )
                    except Exception:
                        coverage_line.value = ""
                else:
                    coverage_line.value = ""
            else:
                coverage_line.value = ""
            marker_bit = f" · {len(plan.markers)} markers" if plan.markers else ""
            out_name = Path(board.last_plan_path).name if board and board.last_plan_path else ""
            saved = f"\nSaved {out_name}" if out_name else ""
            summary.value = (
                f"{len(plan.clips)} edits · {dur_s:.0f}s @ {plan.fps:g} fps"
                f"{coverage}{rev}{marker_bit}{saved}"
            )
            revise_btn.disabled = board is None

        def refresh_plan_shots(plan: EditPlan) -> None:
            """Evidence list for Assemble / Montage (no storyboard cards)."""
            shots_col.controls.clear()
            analysis_line.value = f"Mode: {plan.mode}"
            analysis_line.color = ft.Colors.GREY_600
            coverage_line.value = ""
            for i, clip in enumerate(plan.clips[:80]):
                name = Path(clip.media_path).name
                src_fps = clip.source_fps or plan.fps
                start_s = clip.start_frame / src_fps if src_fps else 0
                end_s = clip.end_frame / src_fps if src_fps else 0
                shots_col.controls.append(
                    ft.Text(
                        f"{i + 1}. {name}  {start_s:.1f}s–{end_s:.1f}s"
                        f"  → record {clip.record_frame}",
                        size=12,
                    )
                )
            page.update()

        def refresh_shots(board: Storyboard | None = None, plan: EditPlan | None = None) -> None:
            shots_col.controls.clear()
            if board is not None:
                last_storyboard[0] = board
            warns = list(getattr(board, "analysis_warnings", None) or [])
            if warns:
                analysis_line.value = "Analysis: " + " · ".join(warns[:3])
                analysis_line.color = ft.Colors.ORANGE_700
            elif board is not None:
                beat_ok = bool(board.music_path) and not any(
                    str(w).startswith("Beat snap skipped") for w in warns
                )
                analysis_line.value = (
                    "Analysis: ffmpeg frames + visual signals"
                    + (
                        " + CLIP tags"
                        if any((s.fill and s.fill.tags) for s in board.slots)
                        else ""
                    )
                    + (" · beat-snapped" if beat_ok else "")
                )
                analysis_line.color = ft.Colors.GREY_600
            elif plan is not None:
                refresh_plan_shots(plan)
                update_summary(plan, None)
                return
            else:
                analysis_line.value = ""

            if board is None:
                update_summary(plan, None)
                page.update()
                return

            for idx, slot in enumerate(board.slots):
                fill = slot.fill
                if fill is None:
                    continue
                name = Path(fill.media_path).name
                thumb = (
                    Path.cwd()
                    / ".autoedit"
                    / "thumbs"
                    / f"{Path(fill.media_path).stem}.jpg"
                )
                lock_label = "Unlock" if slot.locked else "Lock"
                alts = len(slot.candidates)

                def make_lock(i: int):
                    def _lock(_e):
                        b = last_storyboard[0]
                        if b is None or i >= len(b.slots):
                            return
                        b.slots[i].locked = not b.slots[i].locked
                        persist_board_and_plan()
                        refresh_shots(last_storyboard[0], last_plan[0])
                        set_status(
                            "Locked" if b.slots[i].locked else "Unlocked"
                        )

                    return _lock

                def make_swap(i: int):
                    def _swap(_e):
                        b = last_storyboard[0]
                        if b is None or i >= len(b.slots):
                            return
                        if not swap_to_candidate(b.slots[i], 0):
                            set_status("No alternate candidates", error=True)
                            return
                        persist_board_and_plan()
                        refresh_shots(last_storyboard[0], last_plan[0])
                        set_status("Swapped to next candidate")

                    return _swap

                def make_trim(i: int, delta: float):
                    def _trim(_e):
                        b = last_storyboard[0]
                        if b is None or i >= len(b.slots) or b.slots[i].fill is None:
                            return
                        fill_i = b.slots[i].fill
                        assert fill_i is not None
                        new_dur = max(0.8, fill_i.duration_s + delta)
                        fill_i.duration_s = round(new_dur, 3)
                        b.slots[i].duration_s = fill_i.duration_s
                        persist_board_and_plan()
                        refresh_shots(last_storyboard[0], last_plan[0])

                    return _trim

                def make_delete(i: int):
                    def _del(_e):
                        b = last_storyboard[0]
                        if b is None or i >= len(b.slots):
                            return
                        if b.slots[i].locked:
                            set_status("Unlock before deleting", error=True)
                            return
                        b.slots.pop(i)
                        persist_board_and_plan()
                        refresh_shots(last_storyboard[0], last_plan[0])
                        set_status("Shot removed")

                    return _del

                def make_move(i: int, direction: int):
                    def _move(_e):
                        b = last_storyboard[0]
                        if b is None:
                            return
                        j = i + direction
                        if j < 0 or j >= len(b.slots):
                            return
                        b.slots[i], b.slots[j] = b.slots[j], b.slots[i]
                        persist_board_and_plan()
                        refresh_shots(last_storyboard[0], last_plan[0])

                    return _move

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
                lock_bit = " 🔒" if slot.locked else ""
                left.append(
                    ft.Column(
                        [
                            ft.Text(
                                f"{idx + 1}. {name}  {fill.start_s:.1f}s–"
                                f"{fill.start_s + fill.duration_s:.1f}s"
                                f"  ·  score {fill.score:.2f}{lock_bit}",
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
                            ft.Row(
                                [
                                    ft.TextButton(lock_label, on_click=make_lock(idx)),
                                    ft.TextButton(
                                        f"Swap ({alts})",
                                        on_click=make_swap(idx),
                                        disabled=alts == 0,
                                    ),
                                    ft.TextButton("−0.5s", on_click=make_trim(idx, -TRIM_STEP_S)),
                                    ft.TextButton("+0.5s", on_click=make_trim(idx, TRIM_STEP_S)),
                                    ft.IconButton(
                                        icon=ft.Icons.ARROW_UPWARD,
                                        tooltip="Move up",
                                        on_click=make_move(idx, -1),
                                        icon_size=16,
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.ARROW_DOWNWARD,
                                        tooltip="Move down",
                                        on_click=make_move(idx, 1),
                                        icon_size=16,
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.DELETE_OUTLINE,
                                        tooltip="Delete shot",
                                        on_click=make_delete(idx),
                                        icon_size=16,
                                    ),
                                ],
                                spacing=0,
                                wrap=True,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    )
                )
                shots_col.controls.append(
                    ft.Row(
                        left,
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    )
                )

            update_summary(plan or last_plan[0], board)
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
            revise_btn.disabled = True
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
                        board = Storyboard.load(sb_path)
                        storyboard_path[0] = sb_path
                        last_plan[0] = plan
                        refresh_shots(board, plan)
                    elif m == "assemble":
                        plan = engine.build_assemble_plan(
                            clips,
                            timeline_name=name,
                            per_clip=per_clip,
                            music_path=music,
                            timeline_fps=fps,
                        )
                        out = Path(f"{name.replace(' ', '_')}.plan.json")
                        plan.save(out)
                        last_plan[0] = plan
                        last_storyboard[0] = None
                        storyboard_path[0] = None
                        refresh_shots(None, plan)
                        update_summary(plan, None)
                    else:
                        plan = engine.build_montage_plan(
                            timeline_name=name,
                            music_path=music or "",
                            broll_paths=clips,
                            beats_per_clip=beats,
                            timeline_fps=fps,
                        )
                        out = Path(f"{name.replace(' ', '_')}.plan.json")
                        plan.save(out)
                        last_plan[0] = plan
                        last_storyboard[0] = None
                        storyboard_path[0] = None
                        refresh_shots(None, plan)
                        update_summary(plan, None)

                    status.value = "First cut ready"
                    status.color = ft.Colors.GREY_700
                except Exception as exc:
                    summary.value = ""
                    shots_col.controls.clear()
                    analysis_line.value = ""
                    coverage_line.value = ""
                    status.value = str(exc)
                    status.color = ft.Colors.RED_700
                    traceback.print_exc()
                finally:
                    create_btn.disabled = False
                    apply_btn.disabled = False
                    revise_btn.disabled = last_storyboard[0] is None
                    page.update()

            page.run_thread(work)

        def revise_unlocked(_e) -> None:
            path = storyboard_path[0]
            if path is None or not path.is_file():
                set_status("Create a Story first cut before revising", error=True)
                return
            revise_btn.disabled = True
            create_btn.disabled = True
            apply_btn.disabled = True
            set_status("Revising unlocked shots…")
            page.update()

            name = (timeline_field.value or "First Cut").strip()

            def work() -> None:
                try:
                    # Prefer revision-named timeline for the next apply.
                    rev_board = Storyboard.load(path)
                    rev_name = f"{name} r{rev_board.revision + 1}"
                    plan = engine.revise_story_plan(
                        path,
                        timeline_name=rev_name,
                        snap_to_beats=True,
                    )
                    board = Storyboard.load(path)
                    last_plan[0] = plan
                    refresh_shots(board, plan)
                    status.value = f"Revision {board.revision} ready"
                    status.color = ft.Colors.GREY_700
                except Exception as exc:
                    status.value = str(exc)
                    status.color = ft.Colors.RED_700
                    traceback.print_exc()
                finally:
                    create_btn.disabled = False
                    apply_btn.disabled = False
                    revise_btn.disabled = False
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
                    board = last_storyboard[0]
                    path = storyboard_path[0]
                    if board is not None and path is not None:
                        board.last_timeline_name = result.timeline_name
                        board.save(path)
                        last_storyboard[0] = board
                        update_summary(plan, board)
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
        revise_btn.on_click = revise_unlocked
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
                        "Add clips… for multi-select .mov/.mp4. "
                        "Add folder… imports every video in that folder.",
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
            story_section,
            ft.Container(height=12),
            ft.Text("EDIT", weight=ft.FontWeight.BOLD),
            mode,
            controls_row,
            ft.Row([timeline_field, fps_field]),
            ft.Row(
                [
                    create_btn,
                    revise_btn,
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
            coverage_line,
            shots_col,
            ft.Divider(),
            status,
        )
        sync_mode_visibility()
        refresh_resolve_status()

    ft.app(target=app)


if __name__ == "__main__":
    main()
