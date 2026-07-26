"""Beat detection without requiring librosa."""

import numpy as np

from autoedit.analyzers.beats import estimate_beat_grid


def test_estimate_beat_grid_finds_approx_120_bpm():
    sr = 22050
    bpm = 120.0
    duration = 8.0
    t = np.arange(0, duration, 1.0 / sr)
    # Click every beat: short pulses on a silent bed.
    y = np.zeros_like(t)
    period = 60.0 / bpm
    for beat_t in np.arange(0.0, duration, period):
        i = int(round(beat_t * sr))
        if 0 <= i < len(y):
            end = min(len(y), i + int(0.02 * sr))
            y[i:end] = 1.0
    grid = estimate_beat_grid(y.astype(np.float32), sr)
    assert 100.0 <= grid.tempo <= 140.0
    assert len(grid.beats) >= 8
    # Spacing should be near the beat period.
    gaps = np.diff(grid.beats)
    assert abs(float(np.median(gaps)) - period) < 0.08


def test_estimate_beat_grid_short_audio():
    sr = 22050
    y = np.zeros(sr // 4, dtype=np.float32)
    grid = estimate_beat_grid(y, sr)
    assert grid.tempo > 0
    assert isinstance(grid.beats, list)
