"""Beat-aware pacing helpers for Story mode."""

from __future__ import annotations

from .filler import MIN_SHOT_S
from .models import Storyboard


def snap_fills_to_beats(
    storyboard: Storyboard,
    beats: list[float],
    *,
    max_nudge_s: float = 0.4,
) -> Storyboard:
    """Nudge filled shot durations so cut points land near music beats.

    Narrative order is unchanged. Only durations move, and only when a beat
    sits within ``max_nudge_s`` of the natural cut. Total runtime drifts by at
    most ``max_nudge_s`` per shot.
    """
    if not beats:
        return storyboard

    beat_list = sorted(float(b) for b in beats if b >= 0)
    if not beat_list:
        return storyboard

    t = 0.0
    for slot in storyboard.slots:
        fill = slot.fill
        if fill is None:
            continue
        natural_end = t + fill.duration_s
        nearest = min(beat_list, key=lambda b: abs(b - natural_end))
        if abs(nearest - natural_end) <= max_nudge_s and nearest > t + MIN_SHOT_S:
            new_dur = nearest - t
            fill.duration_s = round(new_dur, 3)
            slot.duration_s = round(new_dur, 3)
            t = nearest
        else:
            t = natural_end

    return storyboard
