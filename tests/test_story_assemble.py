"""Assemble stitch + storyboard generate/fill/convert."""

from autoedit.analysis.catalogue import MediaCatalogue, MediaClip, MediaSegment
from autoedit.models import ClipSegment, EditPlan
from autoedit.planners.assemble import AssembleSource, stitch_plans
from autoedit.storyboard import (
    fill_storyboard,
    story_to_storyboard,
    storyboard_to_edit_plan,
)


def test_stitch_plans_reripples_record_frames():
    p1 = EditPlan(
        "a",
        30.0,
        clips=[ClipSegment("a.mov", 0, 50, 0, source_fps=50.0)],
    )
    p2 = EditPlan(
        "b",
        30.0,
        clips=[ClipSegment("b.mov", 10, 60, 0, source_fps=50.0)],
    )
    # Each is 1s source @50fps → 30 timeline frames.
    out = stitch_plans([p1, p2], timeline_name="T", timeline_fps=30.0)
    assert len(out.clips) == 2
    assert out.clips[0].record_frame == 0
    assert out.clips[1].record_frame == 30
    assert out.duration_frames == 60
    assert out.mode == "assemble"


def test_story_to_storyboard_splits_paragraphs():
    story = (
        "We left early in the morning.\n\n"
        "The mountains changed everything and the weather deteriorated.\n\n"
        "We reached the pass at sunset with relief."
    )
    board = story_to_storyboard(story, target_duration_s=30.0)
    assert len(board.slots) >= 3
    assert abs(sum(s.duration_s for s in board.slots) - 30.0) < 0.2
    assert board.timeline_fps is None
    assert all(s.fill is None for s in board.slots)


def test_fill_and_convert_uses_seconds_then_frames():
    catalogue = MediaCatalogue(
        clips=[
            MediaClip(
                media_path="/tmp/a.mov",
                source_fps=50.0,
                duration_s=20.0,
                captured_at="2024-01-01T08:00:00",
                segments=[
                    MediaSegment(
                        id="a_001",
                        start_s=0.0,
                        end_s=5.0,
                        duration_s=5.0,
                        speech=False,
                        energy="low",
                        quality_score=0.9,
                    ),
                    MediaSegment(
                        id="a_002",
                        start_s=5.0,
                        end_s=12.0,
                        duration_s=7.0,
                        speech=False,
                        energy="high",
                        quality_score=0.85,
                    ),
                ],
            )
        ]
    )
    board = story_to_storyboard(
        "Calm departure on the road.\n\nDramatic mountain climax.",
        target_duration_s=8.0,
    )
    filled = fill_storyboard(board, catalogue)
    assert filled.filled_count == len(filled.slots)
    assert all(s.fill and s.fill.start_s >= 0 for s in filled.slots)
    assert all("start_frame" not in s.fill.to_dict() for s in filled.slots if s.fill)

    plan = storyboard_to_edit_plan(
        filled, catalogue, timeline_name="Story", timeline_fps=30.0
    )
    assert plan.mode == "story"
    assert plan.fps == 30.0
    assert len(plan.clips) == filled.filled_count
    assert plan.clips[0].source_fps == 50.0
    # Contiguous ripple on timeline clock.
    assert plan.clips[0].record_frame == 0
    if len(plan.clips) > 1:
        assert plan.clips[1].record_frame == plan.clips[0].timeline_span(30.0)


def test_assemble_source_dataclass():
    s = AssembleSource("/a.mov", "scenes")
    assert s.mode == "scenes"
