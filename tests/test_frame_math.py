import pytest

from autoedit.config import frames_to_seconds, seconds_to_frames


def test_seconds_to_frames_rounds_to_nearest():
    assert seconds_to_frames(1.0, 24) == 24
    assert seconds_to_frames(1.02, 24) == 24  # 24.48 -> 24
    assert seconds_to_frames(1.03, 24) == 25  # 24.72 -> 25
    assert seconds_to_frames(0.0, 30) == 0


def test_frames_to_seconds_roundtrip():
    assert frames_to_seconds(48, 24) == pytest.approx(2.0)
    assert frames_to_seconds(seconds_to_frames(3.0, 25), 25) == pytest.approx(3.0)


def test_invalid_fps_raises():
    with pytest.raises(ValueError):
        seconds_to_frames(1.0, 0)
    with pytest.raises(ValueError):
        frames_to_seconds(1, -5)
