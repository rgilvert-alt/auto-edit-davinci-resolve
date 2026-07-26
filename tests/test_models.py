import pytest

from autoedit.models import ClipSegment, EditPlan, Marker, MusicTrack


def make_plan() -> EditPlan:
    return EditPlan(
        timeline_name="Test",
        fps=24.0,
        clips=[
            ClipSegment("a.mov", 0, 24, record_frame=0),
            ClipSegment("a.mov", 48, 72, record_frame=24),
        ],
        markers=[Marker(frame=0, name="start", color="Red")],
        music=MusicTrack("track.wav"),
        mode="silence",
    )


def test_duration_frames_from_furthest_out_point():
    plan = make_plan()
    assert plan.duration_frames == 48  # 24 + 24


def test_json_roundtrip_preserves_everything():
    plan = make_plan()
    restored = EditPlan.from_json(plan.to_json())
    assert restored.to_dict() == plan.to_dict()
    assert restored.music is not None
    assert restored.music.media_path == "track.wav"
    assert restored.mode == "silence"


def test_json_roundtrip_without_music():
    plan = EditPlan("T", 30.0, clips=[ClipSegment("a.mov", 0, 30, 0)])
    restored = EditPlan.from_json(plan.to_json())
    assert restored.music is None
    assert restored.to_dict() == plan.to_dict()


def test_save_and_load(tmp_path):
    plan = make_plan()
    path = tmp_path / "x.plan.json"
    plan.save(path)
    assert EditPlan.load(path).to_dict() == plan.to_dict()


def test_validate_rejects_bad_clip():
    plan = EditPlan("T", 24.0, clips=[ClipSegment("a.mov", 10, 10, 0)])
    with pytest.raises(ValueError):
        plan.validate()


def test_clip_duration():
    assert ClipSegment("a.mov", 10, 40, 0).duration_frames == 30


def test_timeline_span_conforms_source_rate():
    """100 source frames at 50fps is 2s, which is 60 frames on a 30fps timeline."""
    clip = ClipSegment("a.mov", 0, 100, record_frame=0, source_fps=50.0)
    assert clip.duration_frames == 100
    assert clip.duration_seconds(30.0) == pytest.approx(2.0)
    assert clip.timeline_span(30.0) == 60


def test_timeline_span_matches_duration_when_rates_agree():
    clip = ClipSegment("a.mov", 0, 48, record_frame=0)
    assert clip.timeline_span(24.0) == 48


def test_plan_duration_uses_timeline_span_not_source_frames():
    plan = EditPlan(
        "T",
        30.0,
        clips=[
            ClipSegment("a.mov", 0, 100, record_frame=0, source_fps=50.0),
            ClipSegment("a.mov", 200, 300, record_frame=60, source_fps=50.0),
        ],
    )
    assert plan.duration_frames == 120


def test_source_fps_survives_json_roundtrip():
    plan = EditPlan(
        "T", 30.0, clips=[ClipSegment("a.mov", 0, 100, 0, source_fps=50.0)]
    )
    restored = EditPlan.from_json(plan.to_json())
    assert restored.clips[0].source_fps == 50.0
    assert restored.to_dict() == plan.to_dict()


def test_validate_rejects_non_positive_source_fps():
    plan = EditPlan("T", 30.0, clips=[ClipSegment("a.mov", 0, 10, 0, source_fps=0.0)])
    with pytest.raises(ValueError):
        plan.validate()
