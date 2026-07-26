"""Compose human-readable descriptors from signals + semantic tags."""

from __future__ import annotations

from ..analyzers.visual import SegmentSignals, energy_label, motion_label


def describe_segment(
    signals: SegmentSignals,
    tags: list[tuple[str, float]] | None = None,
    *,
    tag_threshold: float = 0.18,
) -> tuple[str, list[str]]:
    """Return (description, tag_labels) for a catalogue segment."""
    tag_labels: list[str] = []
    if tags:
        for label, score in tags:
            if score >= tag_threshold and label not in tag_labels:
                tag_labels.append(label)
            if len(tag_labels) >= 4:
                break

    motion = motion_label(signals.motion)
    energy = energy_label(signals.motion, signals.sharpness)
    quals: list[str] = []
    if motion == "high":
        quals.append("strong motion")
    elif motion == "medium":
        quals.append("moderate motion")
    else:
        quals.append("calm")

    if signals.shake < 0.015:
        quals.append("steady")
    elif signals.shake > 0.04:
        quals.append("shaky")

    if signals.luma >= 0.65:
        quals.append("bright")
    elif signals.luma <= 0.25:
        quals.append("dark")

    if signals.highlight_clip > 0.08:
        quals.append("clipped highlights")
    if signals.shadow_clip > 0.08:
        quals.append("crushed shadows")

    head = ", ".join(tag_labels[:3]) if tag_labels else f"{energy} energy shot"
    tail = ", ".join(quals)
    description = f"{head} — {tail}" if tail else head
    return description, tag_labels
