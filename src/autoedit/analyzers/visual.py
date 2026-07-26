"""Frame-level visual metrics and shot boundary detection (numpy only)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .common import Interval
from .frames import FrameSample

# Split genuinely long static takes so the filler still has variety.
MAX_STATIC_SHOT_S = 8.0


@dataclass(frozen=True)
class FrameSignals:
    """Per-frame measurements; axis 0 aligns with FrameSample.frames."""

    luma_mean: np.ndarray
    luma_std: np.ndarray
    highlight_clip: np.ndarray
    shadow_clip: np.ndarray
    colorfulness: np.ndarray
    sharpness: np.ndarray
    motion: np.ndarray  # length n; motion[0] = 0
    shake: np.ndarray


@dataclass(frozen=True)
class SegmentSignals:
    """Aggregated metrics for one shot / window."""

    motion: float
    shake: float
    luma: float
    contrast: float
    highlight_clip: float
    shadow_clip: float
    colorfulness: float
    sharpness: float

    def as_dict(self) -> dict[str, float]:
        return {
            "motion": float(self.motion),
            "shake": float(self.shake),
            "luma": float(self.luma),
            "contrast": float(self.contrast),
            "highlight_clip": float(self.highlight_clip),
            "shadow_clip": float(self.shadow_clip),
            "colorfulness": float(self.colorfulness),
            "sharpness": float(self.sharpness),
        }


def compute_frame_signals(sample: FrameSample) -> FrameSignals:
    frames = sample.frames.astype(np.float32)
    if frames.size == 0:
        empty = np.zeros(0, dtype=np.float32)
        return FrameSignals(
            luma_mean=empty,
            luma_std=empty,
            highlight_clip=empty,
            shadow_clip=empty,
            colorfulness=empty,
            sharpness=empty,
            motion=empty,
            shake=empty,
        )

    # Rec. 601 luma
    luma = (
        0.299 * frames[:, :, :, 0]
        + 0.587 * frames[:, :, :, 1]
        + 0.114 * frames[:, :, :, 2]
    )
    luma_mean = luma.mean(axis=(1, 2))
    luma_std = luma.std(axis=(1, 2))
    highlight_clip = (luma > 245.0).mean(axis=(1, 2))
    shadow_clip = (luma < 10.0).mean(axis=(1, 2))

    rg = frames[:, :, :, 0] - frames[:, :, :, 1]
    yb = 0.5 * (frames[:, :, :, 0] + frames[:, :, :, 1]) - frames[:, :, :, 2]
    colorfulness = np.sqrt(rg.mean(axis=(1, 2)) ** 2 + yb.mean(axis=(1, 2)) ** 2) + (
        0.3 * np.sqrt(rg.std(axis=(1, 2)) ** 2 + yb.std(axis=(1, 2)) ** 2)
    )

    # Laplacian-variance sharpness on a downscaled luma (cheap).
    small = luma[:, ::2, ::2]
    # 3x3 laplacian via neighbours
    center = small[:, 1:-1, 1:-1]
    lap = (
        -4.0 * center
        + small[:, :-2, 1:-1]
        + small[:, 2:, 1:-1]
        + small[:, 1:-1, :-2]
        + small[:, 1:-1, 2:]
    )
    sharpness = lap.var(axis=(1, 2))

    motion = np.zeros(len(frames), dtype=np.float32)
    if len(frames) > 1:
        diffs = np.abs(frames[1:] - frames[:-1]).mean(axis=(1, 2, 3))
        motion[1:] = diffs / 255.0

    # Shake ≈ variance of local motion deltas (jitter), not overall travel.
    shake = np.zeros(len(frames), dtype=np.float32)
    if len(motion) > 2:
        d = np.diff(motion)
        # Rolling variance over a short window
        for i in range(len(motion)):
            lo = max(0, i - 2)
            hi = min(len(d), i + 1)
            if hi > lo:
                shake[i] = float(np.var(d[lo:hi]))

    return FrameSignals(
        luma_mean=luma_mean.astype(np.float32),
        luma_std=luma_std.astype(np.float32),
        highlight_clip=highlight_clip.astype(np.float32),
        shadow_clip=shadow_clip.astype(np.float32),
        colorfulness=colorfulness.astype(np.float32),
        sharpness=sharpness.astype(np.float32),
        motion=motion,
        shake=shake.astype(np.float32),
    )


def detect_shots(
    sample: FrameSample,
    *,
    hist_bins: int = 32,
    threshold: float | None = None,
    min_shot_s: float = 0.8,
) -> list[Interval]:
    """Find shot boundaries from RGB histogram distance peaks.

    Falls back to a single [0, duration] span when too few frames exist.
    Long static takes are later windowed by the catalogue builder.
    """
    frames = sample.frames
    times = sample.times_s
    duration = float(times[-1]) if len(times) else 0.0
    if len(frames) < 3 or duration <= 0:
        return [Interval(0.0, duration)] if duration > 0 else []

    dists = _histogram_distances(frames, bins=hist_bins)
    if threshold is None:
        # Adaptive: mean + 2.5σ, floored so tiny camera moves don't fire.
        mu = float(dists.mean())
        sigma = float(dists.std())
        threshold = max(0.35, mu + 2.5 * sigma)

    cuts = [0.0]
    last_t = 0.0
    for i, d in enumerate(dists, start=1):
        t = float(times[i])
        if d >= threshold and (t - last_t) >= min_shot_s:
            cuts.append(t)
            last_t = t
    if cuts[-1] < duration - 1e-3:
        cuts.append(duration)
    elif cuts[-1] < duration:
        cuts[-1] = duration

    shots: list[Interval] = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b - a >= min_shot_s * 0.5:
            shots.append(Interval(a, b))
    return shots or [Interval(0.0, duration)]


def aggregate_signals(
    sample: FrameSample,
    frame_signals: FrameSignals,
    start_s: float,
    end_s: float,
) -> SegmentSignals:
    """Mean the per-frame signals whose sample times fall in [start, end)."""
    times = sample.times_s
    if len(times) == 0:
        return SegmentSignals(0, 0, 0.5, 0, 0, 0, 0, 0)
    mask = (times >= start_s - 1e-6) & (times < end_s + 1e-6)
    if not np.any(mask):
        # Nearest frame
        idx = int(np.argmin(np.abs(times - 0.5 * (start_s + end_s))))
        mask = np.zeros(len(times), dtype=bool)
        mask[idx] = True

    def _mean(arr: np.ndarray) -> float:
        return float(arr[mask].mean()) if np.any(mask) else 0.0

    return SegmentSignals(
        motion=_mean(frame_signals.motion),
        shake=_mean(frame_signals.shake),
        luma=_mean(frame_signals.luma_mean) / 255.0,
        contrast=_mean(frame_signals.luma_std) / 255.0,
        highlight_clip=_mean(frame_signals.highlight_clip),
        shadow_clip=_mean(frame_signals.shadow_clip),
        colorfulness=_mean(frame_signals.colorfulness) / 255.0,
        sharpness=_mean(frame_signals.sharpness),
    )


def motion_label(motion: float) -> str:
    if motion >= 0.08:
        return "high"
    if motion >= 0.035:
        return "medium"
    return "low"


def energy_label(motion: float, sharpness: float) -> str:
    # Combine travel and detail: a sharp static landscape is still "medium".
    score = motion * 2.0 + min(1.0, sharpness / 500.0) * 0.15
    if score >= 0.12:
        return "high"
    if score >= 0.05:
        return "medium"
    return "low"


def quality_from_signals(sig: SegmentSignals, duration_s: float) -> float:
    """0–1 usability score from measured signals + duration."""
    q = 0.55
    # Prefer usable exposure
    if 0.2 <= sig.luma <= 0.8:
        q += 0.12
    else:
        q -= 0.1
    q -= min(0.2, sig.highlight_clip * 0.8 + sig.shadow_clip * 0.8)
    # Prefer sharp, not overly shaky
    q += min(0.15, sig.sharpness / 800.0)
    q -= min(0.15, sig.shake * 8.0)
    if duration_s < 0.6:
        q -= 0.25
    elif duration_s < 1.2:
        q -= 0.1
    return float(max(0.05, min(0.98, q)))


def window_long_shots(
    shots: list[Interval], max_s: float = MAX_STATIC_SHOT_S
) -> list[Interval]:
    """Split long takes into near-equal windows (filler variety)."""
    out: list[Interval] = []
    for shot in shots:
        dur = shot.end - shot.start
        if dur <= max_s * 1.5:
            out.append(shot)
            continue
        count = max(2, int(round(dur / max_s)))
        step = dur / count
        for i in range(count):
            out.append(
                Interval(shot.start + i * step, shot.start + (i + 1) * step)
            )
    return out


def _histogram_distances(frames: np.ndarray, bins: int) -> np.ndarray:
    n = len(frames)
    dists = np.zeros(n - 1, dtype=np.float32)
    prev = _rgb_hist(frames[0], bins)
    for i in range(1, n):
        cur = _rgb_hist(frames[i], bins)
        # Bhattacharyya-style distance on normalized histograms
        bc = np.sqrt(prev * cur).sum()
        dists[i - 1] = float(max(0.0, 1.0 - bc))
        prev = cur
    return dists


def _rgb_hist(frame: np.ndarray, bins: int) -> np.ndarray:
    hist = []
    for c in range(3):
        h, _ = np.histogram(frame[:, :, c], bins=bins, range=(0, 256), density=True)
        hist.append(h.astype(np.float32))
    arr = np.concatenate(hist)
    s = float(arr.sum()) or 1.0
    return arr / s
