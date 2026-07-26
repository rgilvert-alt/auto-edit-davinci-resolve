"""Unit tests for visual metrics and descriptors (no ffmpeg/CLIP)."""

import numpy as np
import pytest

from autoedit.analyzers.frames import FrameSample
from autoedit.analyzers.visual import (
    SegmentSignals,
    aggregate_signals,
    compute_frame_signals,
    detect_shots,
    energy_label,
    motion_label,
    quality_from_signals,
    window_long_shots,
)
from autoedit.analyzers.common import Interval
from autoedit.analysis.describe import describe_segment
from autoedit.storyboard.filler import ScoreResult, score_candidate, FillContext
from autoedit.analysis.catalogue import MediaClip, MediaSegment
from autoedit.storyboard.models import StorySlot, SlotPrefer


def _sample(n: int = 10, duration: float = 10.0) -> FrameSample:
    # Synthetic: first half red, second half green → strong hist cut mid-way
    frames = np.zeros((n, 32, 32, 3), dtype=np.uint8)
    mid = n // 2
    frames[:mid, :, :, 0] = 200
    frames[mid:, :, :, 1] = 200
    # Add slight frame-to-frame noise for motion
    noise = (np.arange(n) % 3).astype(np.uint8)
    frames[:, 0, 0, 0] = np.clip(frames[:, 0, 0, 0] + noise * 10, 0, 255)
    times = np.linspace(0.0, duration, n)
    return FrameSample(
        frames=frames,
        times_s=times,
        sample_fps=n / duration,
        used_hwaccel=False,
        keyframes_only=True,
    )


def test_compute_frame_signals_shapes():
    sample = _sample()
    sig = compute_frame_signals(sample)
    assert len(sig.luma_mean) == len(sample.frames)
    assert len(sig.motion) == len(sample.frames)
    assert sig.motion[0] == 0.0


def test_detect_shots_finds_color_cut():
    sample = _sample(n=20, duration=20.0)
    shots = detect_shots(sample, threshold=0.2, min_shot_s=0.5)
    assert len(shots) >= 2
    assert shots[0].start == 0.0
    assert abs(shots[-1].end - 20.0) < 1e-6


def test_window_long_shots():
    shots = [Interval(0.0, 30.0)]
    windows = window_long_shots(shots, max_s=8.0)
    assert len(windows) >= 3
    assert abs(windows[0].start) < 1e-9
    assert abs(windows[-1].end - 30.0) < 1e-6


def test_describe_segment():
    sig = SegmentSignals(
        motion=0.1,
        shake=0.005,
        luma=0.7,
        contrast=0.2,
        highlight_clip=0.0,
        shadow_clip=0.0,
        colorfulness=0.3,
        sharpness=400.0,
    )
    desc, tags = describe_segment(sig, [("motorcycle", 0.4), ("forest trail", 0.3)])
    assert "motorcycle" in desc
    assert "strong motion" in desc
    assert "motorcycle" in tags


def test_quality_and_labels():
    assert motion_label(0.1) == "high"
    assert energy_label(0.1, 100.0) == "high"
    q = quality_from_signals(
        SegmentSignals(0.05, 0.0, 0.5, 0.2, 0.0, 0.0, 0.2, 300.0), 4.0
    )
    assert 0.4 < q < 1.0


def test_score_candidate_returns_parts():
    slot = StorySlot(
        id="s1",
        role="opening",
        duration_s=3.0,
        intent="calm forest trail",
        prefer=SlotPrefer(energy="low"),
    )
    seg = MediaSegment(
        id="a_001",
        start_s=0.0,
        end_s=5.0,
        duration_s=5.0,
        energy="low",
        motion="low",
        speech=False,
        quality_score=0.8,
        description="forest trail — calm, steady",
        tags=["forest trail"],
        signals={"motion": 0.02, "shake": 0.0, "luma": 0.5, "sharpness": 200.0},
    )
    clip = MediaClip("/tmp/a.mov", 30.0, 20.0, segments=[seg])
    ctx = FillContext()
    result = score_candidate(slot, seg, clip, ctx, 0.0, allow_reuse=True)
    assert isinstance(result, ScoreResult)
    assert result.score > 0
    assert "quality" in result.parts
    assert result.reason


def test_detect_scenes_falls_back_without_scenedetect(monkeypatch):
    """Assemble/Scenes must work when PySceneDetect is not installed."""
    import builtins

    from autoedit.analyzers import frames as frames_mod
    from autoedit.analyzers import scenes

    sample = _sample(12, 12.0)
    real_import = builtins.__import__

    def _block_scenedetect(name, *args, **kwargs):
        if name == "scenedetect" or name.startswith("scenedetect."):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_scenedetect)
    monkeypatch.setattr(frames_mod, "sample_frames", lambda path, **kw: sample)

    shots = scenes.detect_scenes("/tmp/clip.mov")
    assert len(shots) >= 1
    assert shots[0].start == pytest.approx(0.0)
    assert shots[-1].end == pytest.approx(12.0)
