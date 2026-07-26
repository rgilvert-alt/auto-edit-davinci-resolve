"""Shared analyzer types (seconds-domain intervals)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    """A half-open time span in seconds: [start, end)."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def invert_intervals(
    intervals: list[Interval], total: float
) -> list[Interval]:
    """Return the complement of ``intervals`` within [0, total).

    Used to turn silence spans into speech spans (and vice versa).
    """
    result: list[Interval] = []
    cursor = 0.0
    for iv in sorted(intervals, key=lambda i: i.start):
        start = max(0.0, iv.start)
        if start > cursor:
            result.append(Interval(cursor, min(start, total)))
        cursor = max(cursor, min(iv.end, total))
    if cursor < total:
        result.append(Interval(cursor, total))
    return [iv for iv in result if iv.duration > 0]
