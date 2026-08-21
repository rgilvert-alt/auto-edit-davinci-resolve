"""Tests for storyboard pacing, lock/regenerate, candidates, coverage."""

from autoedit.analysis.catalogue import MediaCatalogue, MediaClip, MediaSegment
from autoedit.storyboard import (
    coverage_report,
    fill_storyboard,
    regenerate_unlocked,
    story_to_storyboard,
    swap_to_candidate,
)
from autoedit.storyboard.models import SlotFill, StorySlot
from autoedit.storyboard.pacing import snap_fills_to_beats


def _catalogue() -> MediaCatalogue:
    return MediaCatalogue(
        clips=[
            MediaClip(
                media_path="/tmp/a.mov",
                source_fps=30.0,
                duration_s=40.0,
                captured_at="2024-01-01T08:00:00",
                segments=[
                    MediaSegment(
                        id="a_001",
                        start_s=0.0,
                        end_s=8.0,
                        duration_s=8.0,
                        speech=False,
                        energy="low",
                        quality_score=0.9,
                        description="calm road",
                        tags=["road"],
                    ),
                    MediaSegment(
                        id="a_002",
                        start_s=8.0,
                        end_s=16.0,
                        duration_s=8.0,
                        speech=False,
                        energy="medium",
                        quality_score=0.85,
                        description="trail ride",
                        tags=["trail"],
                    ),
                    MediaSegment(
                        id="a_003",
                        start_s=16.0,
                        end_s=24.0,
                        duration_s=8.0,
                        speech=False,
                        energy="high",
                        quality_score=0.8,
                        description="mountain pass",
                        tags=["mountain"],
                    ),
                    MediaSegment(
                        id="a_004",
                        start_s=24.0,
                        end_s=32.0,
                        duration_s=8.0,
                        speech=False,
                        energy="medium",
                        quality_score=0.75,
                        description="sunset",
                        tags=["sunset"],
                    ),
                ],
            ),
            MediaClip(
                media_path="/tmp/b.mov",
                source_fps=30.0,
                duration_s=20.0,
                captured_at="2024-01-01T09:00:00",
                segments=[
                    MediaSegment(
                        id="b_001",
                        start_s=0.0,
                        end_s=10.0,
                        duration_s=10.0,
                        speech=False,
                        energy="high",
                        quality_score=0.88,
                        description="action climb",
                        tags=["climb"],
                    ),
                ],
            ),
        ]
    )


def test_fill_stores_candidates_and_segment_id():
    cat = _catalogue()
    board = story_to_storyboard(
        "Morning departure on the road toward the mountains.",
        target_duration_s=12.0,
        style="Adventure documentary",
    )
    filled = fill_storyboard(board, cat)
    assert filled.filled_count == len(filled.slots)
    assert any(s.candidates for s in filled.slots)
    assert all(s.fill and s.fill.segment_id for s in filled.slots if s.fill)


def test_locked_survives_regenerate():
    cat = _catalogue()
    board = story_to_storyboard(
        "Calm start then dramatic mountain climax.",
        target_duration_s=10.0,
    )
    filled = fill_storyboard(board, cat)
    first = filled.slots[0]
    assert first.fill is not None
    locked_path = first.fill.media_path
    locked_start = first.fill.start_s
    first.locked = True

    revised = regenerate_unlocked(filled, cat)
    assert revised.revision == 2
    assert revised.slots[0].locked is True
    assert revised.slots[0].fill is not None
    assert revised.slots[0].fill.media_path == locked_path
    assert revised.slots[0].fill.start_s == locked_start


def test_swap_to_candidate_promotes_alternate():
    slot = StorySlot(
        id="s1",
        role="opening",
        duration_s=3.0,
        intent="road",
        fill=SlotFill("/tmp/a.mov", 0.0, 3.0, score=0.9, segment_id="a_001"),
        candidates=[
            SlotFill("/tmp/b.mov", 1.0, 3.0, score=0.8, segment_id="b_001"),
        ],
    )
    assert swap_to_candidate(slot, 0)
    assert slot.fill is not None
    assert slot.fill.media_path == "/tmp/b.mov"
    assert slot.candidates[0].media_path == "/tmp/a.mov"


def test_snap_fills_to_beats_nudges_cut():
    board = story_to_storyboard("A short ride.", target_duration_s=6.0)
    # Force two filled slots with known durations.
    board.slots = board.slots[:2]
    board.slots[0].fill = SlotFill("/tmp/a.mov", 0.0, 3.0)
    board.slots[0].duration_s = 3.0
    board.slots[1].fill = SlotFill("/tmp/a.mov", 8.0, 3.0)
    board.slots[1].duration_s = 3.0
    # Natural cuts at 3.0 and 6.0; beat near 3.2 should nudge first shot.
    snap_fills_to_beats(board, [0.0, 3.2, 6.1], max_nudge_s=0.4)
    assert abs(board.slots[0].fill.duration_s - 3.2) < 1e-6


def test_coverage_report_mentions_unused():
    cat = _catalogue()
    board = story_to_storyboard("Road trip.", target_duration_s=4.0)
    filled = fill_storyboard(board, cat)
    report = coverage_report(filled, cat)
    assert "used" in report or "unused" in report


def test_strict_chronology_fills_are_monotonic():
    from autoedit.storyboard.filler import _capture_ranks, _segment_positions

    cat = _catalogue()
    board = story_to_storyboard(
        "Morning road. Trail climb. Mountain pass. Sunset.",
        target_duration_s=16.0,
    )
    board.keep_shoot_order = True
    filled = fill_storyboard(board, cat, chronology_strict=True)
    positions = _segment_positions(cat, _capture_ranks(cat))
    pos_list = [
        positions[s.fill.segment_id]
        for s in filled.slots
        if s.fill and s.fill.segment_id
    ]
    assert pos_list
    assert pos_list == sorted(pos_list)


def test_soft_chronology_can_pick_earlier_after_late_lock():
    from autoedit.storyboard.filler import _capture_ranks, _segment_positions

    cat = _catalogue()
    positions = _segment_positions(cat, _capture_ranks(cat))
    late_id = "b_001"
    late_pos = positions[late_id]

    board = story_to_storyboard(
        "First beat. Second beat. Third beat.",
        target_duration_s=12.0,
    )
    assert len(board.slots) >= 2
    board.slots[0].fill = SlotFill(
        media_path="/tmp/b.mov",
        start_s=0.0,
        duration_s=board.slots[0].duration_s,
        score=1.0,
        segment_id=late_id,
    )
    board.slots[0].locked = True
    for slot in board.slots[1:]:
        slot.fill = None
        slot.candidates = []

    soft = fill_storyboard(board, cat, chronology_strict=False)
    soft_later = [
        positions[s.fill.segment_id]
        for s in soft.slots[1:]
        if s.fill and s.fill.segment_id
    ]
    assert soft_later
    assert any(p < late_pos - 1e-6 for p in soft_later)


def test_strict_stops_when_no_later_footage():
    """When nothing later remains, leave trailing slots empty — never go backward."""
    from autoedit.storyboard.filler import _capture_ranks, _segment_positions

    cat = _catalogue()
    positions = _segment_positions(cat, _capture_ranks(cat))
    late_id = "b_001"
    late_pos = positions[late_id]

    board = story_to_storyboard(
        "First beat. Second beat. Third beat.",
        target_duration_s=12.0,
    )
    board.slots[0].fill = SlotFill(
        media_path="/tmp/b.mov",
        start_s=0.0,
        duration_s=10.0,  # entire late segment — nothing later remains
        score=1.0,
        segment_id=late_id,
    )
    board.slots[0].locked = True
    for slot in board.slots[1:]:
        slot.fill = None
        slot.candidates = []

    filled = fill_storyboard(board, cat, chronology_strict=True)
    later_fills = [s.fill for s in filled.slots[1:] if s.fill]
    assert later_fills == []
    assert all(s.fill is None for s in filled.slots[1:])
    assert any("Keep shoot order: stopped" in w for w in filled.analysis_warnings)
    assert any("no later footage left" in w for w in filled.analysis_warnings)
    # Locked late fill is the only fill; nothing earlier sneaks in.
    only = [s.fill for s in filled.slots if s.fill]
    assert len(only) == 1
    assert only[0].segment_id == late_id
    assert positions[late_id] == late_pos


def test_no_identical_reuse_windows():
    """Reuse must advance the cursor — never repeat the same in/out."""
    cat = _catalogue()
    # Demand more slots than unique segments so reuse would be tempted.
    board = story_to_storyboard(
        "A. B. C. D. E. F. G. H. I. J. K. L.",
        target_duration_s=36.0,
    )
    filled = fill_storyboard(board, cat, chronology_strict=True)
    windows = [
        (s.fill.media_path, round(s.fill.start_s, 2), round(s.fill.duration_s, 2))
        for s in filled.slots
        if s.fill
    ]
    assert windows
    assert len(windows) == len(set(windows)), f"duplicate windows: {windows}"


def test_storyboard_v3_roundtrip_locked_candidates(tmp_path):
    board = story_to_storyboard("Trip.", target_duration_s=4.0)
    board.slots[0].locked = True
    board.slots[0].fill = SlotFill(
        media_path="/tmp/a.mov",
        start_s=0.0,
        duration_s=2.0,
        score=0.5,
        segment_id="a_001",
    )
    board.slots[0].candidates = [
        SlotFill(media_path="/tmp/b.mov", start_s=0.0, duration_s=2.0, score=0.4)
    ]
    board.catalogue_path = "/tmp/x.catalogue.json"
    board.music_path = "/tmp/m.wav"
    board.revision = 3
    board.keep_shoot_order = False
    path = tmp_path / "t.storyboard.json"
    board.save(path)
    loaded = type(board).load(path)
    assert loaded.schema_version == 3
    assert loaded.slots[0].locked is True
    assert loaded.slots[0].candidates
    assert loaded.catalogue_path.endswith("catalogue.json")
    assert loaded.revision == 3
    assert loaded.keep_shoot_order is False
