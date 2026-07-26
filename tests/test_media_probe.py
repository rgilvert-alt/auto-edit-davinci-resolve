"""probe() must never invent a frame rate."""

import pytest

from autoedit import media
from autoedit.media import ProbeError, _parse_fps


def test_probe_raises_when_ffprobe_missing(monkeypatch):
    monkeypatch.setattr(media, "ffprobe_available", lambda: False)
    with pytest.raises(ProbeError, match="brew install ffmpeg"):
        media.probe("clip.mov")


def test_probe_raises_when_video_fps_unparseable(monkeypatch):
    monkeypatch.setattr(media, "ffprobe_available", lambda: True)

    class FakeProc:
        returncode = 0
        stdout = (
            '{"streams": [{"codec_type": "video", "avg_frame_rate": "0/0",'
            ' "r_frame_rate": "0/0"}], "format": {}}'
        )
        stderr = ""

    monkeypatch.setattr(media.subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(ProbeError, match="frame rate"):
        media.probe("clip.mov")


def test_probe_reports_zero_fps_for_audio_only(monkeypatch):
    monkeypatch.setattr(media, "ffprobe_available", lambda: True)

    class FakeProc:
        returncode = 0
        stdout = (
            '{"streams": [{"codec_type": "audio"}], "format": {"duration": "12.5"}}'
        )
        stderr = ""

    monkeypatch.setattr(media.subprocess, "run", lambda *a, **k: FakeProc())
    info = media.probe("song.wav")
    assert info.fps == 0.0
    assert info.has_audio is True
    assert info.has_video is False
    assert info.duration_s == 12.5


def test_probe_parses_fractional_frame_rate(monkeypatch):
    monkeypatch.setattr(media, "ffprobe_available", lambda: True)

    class FakeProc:
        returncode = 0
        stdout = (
            '{"streams": [{"codec_type": "video", "avg_frame_rate": "30000/1001"}],'
            ' "format": {"duration": "4.0"}}'
        )
        stderr = ""

    monkeypatch.setattr(media.subprocess, "run", lambda *a, **k: FakeProc())
    assert media.probe("clip.mov").fps == pytest.approx(29.97, abs=0.01)


def test_parse_fps_handles_junk():
    assert _parse_fps(None) is None
    assert _parse_fps("0/0") is None
    assert _parse_fps("50") == 50.0
