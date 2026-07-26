import pytest

from autoedit.analyzers.beats import BeatGrid
from autoedit.analyzers.common import Interval, invert_intervals
from autoedit.analyzers.transcription import Transcript, TranscriptSegment, Word
from autoedit.planners.music_montage import plan_music_montage
from autoedit.planners.scene_assembly import plan_scene_assembly
from autoedit.planners.silence_cut import plan_silence_cut
from autoedit.planners.transcript_edit import plan_transcript_edit


def test_invert_intervals_complement():
    silence = [Interval(2.0, 3.0), Interval(5.0, 6.0)]
    speech = invert_intervals(silence, total=8.0)
    assert [(i.start, i.end) for i in speech] == [
        (0.0, 2.0),
        (3.0, 5.0),
        (6.0, 8.0),
    ]


def test_silence_cut_ripples_contiguously_no_padding():
    speech = [Interval(0.0, 1.0), Interval(2.0, 3.0)]
    plan = plan_silence_cut(
        "a.mov", speech, source_fps=24, timeline_name="T",
        padding_s=0.0, min_gap_s=0.10, total_s=3.0,
    )
    assert len(plan.clips) == 2
    # Source frames come from original media positions.
    assert (plan.clips[0].start_frame, plan.clips[0].end_frame) == (0, 24)
    assert (plan.clips[1].start_frame, plan.clips[1].end_frame) == (48, 72)
    # Record frames ripple with no gaps.
    assert plan.clips[0].record_frame == 0
    assert plan.clips[1].record_frame == 24
    assert plan.duration_frames == 48


def test_silence_cut_merges_when_gap_below_min():
    speech = [Interval(0.0, 1.0), Interval(1.1, 2.0)]
    plan = plan_silence_cut(
        "a.mov", speech, source_fps=24, timeline_name="T",
        padding_s=0.0, min_gap_s=0.5, total_s=2.0,
    )
    assert len(plan.clips) == 1
    assert (plan.clips[0].start_frame, plan.clips[0].end_frame) == (0, 48)


def test_silence_cut_padding_clamped_at_zero():
    speech = [Interval(0.05, 1.0)]
    plan = plan_silence_cut(
        "a.mov", speech, source_fps=24, timeline_name="T",
        padding_s=0.15, min_gap_s=0.3, total_s=2.0,
    )
    # start padded to max(0, 0.05-0.15)=0
    assert plan.clips[0].start_frame == 0


def test_silence_cut_50fps_source_on_30fps_timeline():
    """Source in/out use the clip clock; record frames use the timeline clock.

    A 50fps clip on a 30fps timeline must not advance record frames by source
    frame counts, or every cut after the first leaves a gap.
    """
    speech = [Interval(0.0, 1.0), Interval(2.0, 3.0)]
    plan = plan_silence_cut(
        "a.mov", speech, source_fps=50, timeline_name="T", timeline_fps=30,
        padding_s=0.0, min_gap_s=0.10, total_s=3.0,
    )
    assert plan.fps == 30
    # Source points at 50fps: 1s = 50 frames, 2s = 100 frames.
    assert (plan.clips[0].start_frame, plan.clips[0].end_frame) == (0, 50)
    assert (plan.clips[1].start_frame, plan.clips[1].end_frame) == (100, 150)
    assert plan.clips[0].source_fps == 50
    # Record points at 30fps: each 1s clip occupies 30 timeline frames.
    assert plan.clips[0].record_frame == 0
    assert plan.clips[1].record_frame == 30
    assert plan.duration_frames == 60


def _transcript() -> Transcript:
    words = [
        Word("Hello", 0.0, 0.5),
        Word("um", 0.5, 0.8),
        Word("world", 0.8, 1.2),
    ]
    seg = TranscriptSegment("Hello um world", 0.0, 1.2, words)
    return Transcript(language="en", segments=[seg])


def test_transcript_delete_word_creates_two_ranges():
    plan = plan_transcript_edit(
        "a.mov", _transcript(), source_fps=10, timeline_name="T", delete_words=["um"]
    )
    # "Hello" [0,0.5) and "world" [0.8,1.2) kept as two clips.
    assert len(plan.clips) == 2
    assert (plan.clips[0].start_frame, plan.clips[0].end_frame) == (0, 5)
    assert (plan.clips[1].start_frame, plan.clips[1].end_frame) == (8, 12)
    assert plan.clips[1].record_frame == 5  # rippled after first clip (len 5)


def test_transcript_keyword_filter_keeps_segment():
    plan = plan_transcript_edit(
        "a.mov", _transcript(), source_fps=10, timeline_name="T", keep_keywords=["world"]
    )
    assert len(plan.clips) == 1
    assert (plan.clips[0].start_frame, plan.clips[0].end_frame) == (0, 12)


def test_transcript_50fps_source_on_30fps_timeline():
    plan = plan_transcript_edit(
        "a.mov", _transcript(), source_fps=50, timeline_name="T", timeline_fps=30,
        delete_words=["um"],
    )
    # "Hello" [0,0.5) -> source 0..25 at 50fps, 15 timeline frames at 30fps.
    assert (plan.clips[0].start_frame, plan.clips[0].end_frame) == (0, 25)
    assert plan.clips[1].record_frame == 15


def test_scene_assembly_orders_longest_and_limits():
    shots = [Interval(0, 1), Interval(1, 4), Interval(4, 6)]
    plan = plan_scene_assembly(
        "a.mov", shots, source_fps=24, timeline_name="T", order="longest", limit=2
    )
    assert len(plan.clips) == 2
    # Longest (3s) first, then (2s).
    assert plan.clips[0].duration_frames == 72
    assert plan.clips[1].duration_frames == 48
    assert len(plan.markers) == 2
    assert plan.markers[0].frame == 0
    assert plan.markers[1].frame == 72


def test_scene_assembly_min_length_filter():
    shots = [Interval(0, 0.2), Interval(1, 3)]
    plan = plan_scene_assembly(
        "a.mov", shots, source_fps=24, timeline_name="T", min_scene_s=0.5
    )
    assert len(plan.clips) == 1


def test_scene_assembly_markers_use_timeline_clock():
    shots = [Interval(0, 1), Interval(2, 3)]
    plan = plan_scene_assembly(
        "a.mov", shots, source_fps=50, timeline_name="T", timeline_fps=30
    )
    # Each 1s scene is 50 source frames but 30 timeline frames.
    assert (plan.clips[0].start_frame, plan.clips[0].end_frame) == (0, 50)
    assert plan.clips[1].record_frame == 30
    assert [m.frame for m in plan.markers] == [0, 30]


def test_scene_assembly_rejects_bad_order():
    with pytest.raises(ValueError):
        plan_scene_assembly("a.mov", [], source_fps=24, timeline_name="T", order="weird")


def test_music_montage_cuts_on_beats_and_attaches_music():
    beats = BeatGrid(tempo=120.0, beats=[0.0, 0.5, 1.0, 1.5])
    plan = plan_music_montage(
        ["b1.mov", "b2.mov"], beats, "song.wav", timeline_fps=24, timeline_name="T",
        beats_per_clip=1,
    )
    # 3 intervals between 4 beats.
    assert len(plan.clips) == 3
    assert plan.clips[0].record_frame == 0
    assert plan.clips[1].record_frame == 12  # 0.5s @ 24
    assert plan.clips[2].record_frame == 24
    # B-roll cycles.
    assert plan.clips[0].media_path == "b1.mov"
    assert plan.clips[1].media_path == "b2.mov"
    assert plan.clips[2].media_path == "b1.mov"
    assert plan.music is not None
    assert plan.music.media_path == "song.wav"
    assert plan.music.start_frame == 0


def test_music_montage_beats_per_clip():
    beats = BeatGrid(tempo=120.0, beats=[0.0, 0.5, 1.0, 1.5, 2.0])
    plan = plan_music_montage(
        ["b1.mov"], beats, "song.wav", timeline_fps=24, timeline_name="T",
        beats_per_clip=2,
    )
    # cut points at 0.0, 1.0, 2.0 -> 2 clips.
    assert len(plan.clips) == 2
    assert plan.clips[0].record_frame == 0
    assert plan.clips[1].record_frame == 24


def test_music_montage_per_path_source_fps():
    """Beats are wall-clock, so each b-roll's source length uses its own rate."""
    beats = BeatGrid(tempo=120.0, beats=[0.0, 1.0, 2.0])
    plan = plan_music_montage(
        ["b1.mov", "b2.mov"], beats, "song.wav", timeline_fps=30, timeline_name="T",
        source_fps={"b1.mov": 50.0, "b2.mov": 25.0},
        beats_per_clip=1,
    )
    assert len(plan.clips) == 2
    # Both are 1s long on the timeline (30 frames) but differ in source frames.
    assert plan.clips[0].duration_frames == 50
    assert plan.clips[1].duration_frames == 25
    assert [c.record_frame for c in plan.clips] == [0, 30]
    assert plan.duration_frames == 60


def test_music_montage_requires_beats():
    with pytest.raises(ValueError):
        plan_music_montage(["b.mov"], BeatGrid(120, [0.0]), "s.wav", 24, "T")
