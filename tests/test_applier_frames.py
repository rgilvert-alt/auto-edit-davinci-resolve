"""Frame translation done by the applier, without touching Resolve."""

from autoedit.applier import MUSIC_AUDIO_TRACK, _build_clip_infos, _key
from autoedit.models import ClipSegment, EditPlan, MusicTrack


def _plan() -> EditPlan:
    return EditPlan(
        timeline_name="T",
        fps=30.0,
        clips=[
            ClipSegment("a.mov", 0, 100, record_frame=0, source_fps=50.0),
            ClipSegment("a.mov", 500, 600, record_frame=60, source_fps=50.0),
        ],
    )


def _items(plan: EditPlan) -> dict[str, object]:
    return {_key(c.media_path): object() for c in plan.clips}


def test_record_frames_shift_by_timeline_origin():
    """Resolve timelines start at their start timecode (01:00:00:00 = 108000).

    recordFrame is absolute, so plan-relative records must be offset or the
    clips land before the timeline head and the timeline looks empty.
    """
    plan = _plan()
    infos = _build_clip_infos(plan, _items(plan), timeline_start=108000)
    assert [i["recordFrame"] for i in infos] == [108000, 108060]


def test_record_frames_unshifted_when_origin_is_zero():
    plan = _plan()
    infos = _build_clip_infos(plan, _items(plan), timeline_start=0)
    assert [i["recordFrame"] for i in infos] == [0, 60]


def test_source_in_out_are_untouched_by_timeline_origin():
    """Source points live on the clip's clock; the origin must not leak in."""
    plan = _plan()
    infos = _build_clip_infos(plan, _items(plan), timeline_start=108000)
    assert [(i["startFrame"], i["endFrame"]) for i in infos] == [(0, 99), (500, 599)]


def test_clip_infos_omit_media_type_for_linked_av():
    """Omit mediaType so Resolve places linked video + audio (1 would be video-only)."""
    plan = _plan()
    infos = _build_clip_infos(plan, _items(plan), timeline_start=0)
    assert all("mediaType" not in i for i in infos)


def test_music_record_frame_shifts_by_origin():
    from autoedit.applier import _apply_music

    plan = EditPlan("T", 30.0, clips=[], music=MusicTrack("song.wav"))
    captured: dict[str, object] = {}
    added_tracks: list[str] = []

    class FakeTimeline:
        def GetTrackCount(self, track_type):
            assert track_type == "audio"
            return 1

        def AddTrack(self, track_type):
            added_tracks.append(track_type)
            return True

    class FakePool:
        def AppendToTimeline(self, infos):
            captured.update(infos[0])
            return [object()]

    class FakeClient:
        def media_pool(self):
            return FakePool()

    applied = _apply_music(
        plan,
        FakeClient(),
        {_key("song.wav"): object()},
        timeline_start=108000,
        timeline=FakeTimeline(),
    )
    assert applied is True
    assert captured["recordFrame"] == 108000
    assert captured["mediaType"] == 2
    assert captured["trackIndex"] == MUSIC_AUDIO_TRACK == 2
    assert added_tracks == ["audio"]


def test_music_track_default_is_a2():
    assert MusicTrack("song.wav").track_index == 2
