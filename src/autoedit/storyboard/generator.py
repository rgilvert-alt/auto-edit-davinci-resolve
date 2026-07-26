"""story_to_storyboard: editorial intent → empty Storyboard slots.

v1 uses heuristic structure from story text. Designed so an LLM backend can
replace this later without changing the Storyboard schema.
"""

from __future__ import annotations

import re

from .models import SlotExclude, SlotPrefer, StorySlot, Storyboard

_OPENING = re.compile(
    r"\b(left|depart|start|began|morning|calm|easy|optimistic|beginning)\b",
    re.I,
)
_TENSION = re.compile(
    r"\b(mountain|weather|narrow|isolat|difficult|deterior|tension|intense|"
    r"storm|rain|cold|steep|pass)\b",
    re.I,
)
_CLIMAX = re.compile(
    r"\b(climax|arrival|reach|summit|payoff|dramatic|scale)\b",
    re.I,
)
_RESOLUTION = re.compile(
    r"\b(sunset|relief|end|finish|finally|home|quiet|resolution)\b",
    re.I,
)


def story_to_storyboard(
    story: str,
    target_duration_s: float,
    style: str | None = None,
    timeline_fps: float | None = None,
    title: str | None = None,
) -> Storyboard:
    """Turn editorial story text into empty intent slots."""
    text = (story or "").strip()
    if not text:
        raise ValueError("Story text is required")
    if target_duration_s <= 0:
        raise ValueError("target_duration_s must be positive")

    beats = _split_beats(text)
    if not beats:
        beats = [text]

    sections = _sections(beats)
    weights = [w for _, _, _, w in sections]
    total_w = sum(weights) or 1.0
    durations = [max(1.5, target_duration_s * (w / total_w)) for w in weights]
    # Normalize to exact target.
    scale = target_duration_s / sum(durations)
    durations = [d * scale for d in durations]

    slots: list[StorySlot] = []
    for (beat, role, energy, _w), section_s in zip(sections, durations):
        tags = _guess_tags(beat)
        for shot_s in _shot_durations(section_s, style, role, energy):
            slots.append(
                StorySlot(
                    id=f"s{len(slots) + 1}",
                    role=role,
                    duration_s=round(shot_s, 2),
                    intent=beat.strip(),
                    prefer=SlotPrefer(
                        analysis=["scenes"],
                        energy=energy,
                        tags=list(tags),
                    ),
                    exclude=SlotExclude(has_speech=True),
                    fill=None,
                )
            )

    return Storyboard(
        title=title or _title_from_story(text),
        target_duration_s=target_duration_s,
        slots=slots,
        timeline_fps=timeline_fps,
        style=style,
    )


_ARC = (
    ("opening", "low", 0.9),
    ("progression", "medium", 1.0),
    ("climax", "high", 1.4),
    ("resolution", "medium", 1.0),
)

# Average shot length per style. Pacing, not beat count, decides how many shots
# a target duration needs — a one-line brief must still yield a full sequence.
_STYLE_SHOT_S = {
    "travel montage": 2.4,
    "adventure documentary": 3.6,
    "action short": 1.8,
    "vlog": 3.0,
}
_DEFAULT_SHOT_S = 3.0
_MIN_SHOT_S = 1.2
_MAX_SHOTS = 400


def _sections(beats: list[str]) -> list[tuple[str, str, str, float]]:
    """Return (intent, role, energy, weight) per story section.

    A single beat is expanded over the canonical arc so a short brief still
    produces a shaped film instead of one long shot.
    """
    if len(beats) == 1:
        return [(beats[0], role, energy, w) for role, energy, w in _ARC]

    n = len(beats)
    out: list[tuple[str, str, str, float]] = []
    for i, beat in enumerate(beats):
        role, energy, _ = _classify(i, n, beat)
        out.append((beat, role, energy, _role_weight(i, n, beat)))
    return out


def _shot_length(style: str | None, role: str, energy: str) -> float:
    base = _STYLE_SHOT_S.get((style or "").strip().lower(), _DEFAULT_SHOT_S)
    if energy == "high":
        base *= 0.8
    elif energy == "low":
        base *= 1.25
    if role == "climax":
        base *= 0.85
    elif role == "resolution":
        base *= 1.2
    return max(_MIN_SHOT_S, base)


def _shot_durations(
    section_s: float, style: str | None, role: str, energy: str
) -> list[float]:
    """Split a section into evenly paced shot slots."""
    target = _shot_length(style, role, energy)
    count = max(1, min(_MAX_SHOTS, int(round(section_s / target))))
    each = section_s / count
    return [each] * count


def _split_beats(text: str) -> list[str]:
    # Prefer paragraphs, then sentences.
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) >= 2:
        return paras
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) >= 2:
        # Bundle into 3–7 beats for pacing.
        return _bundle(sentences, min_beats=3, max_beats=7)
    return [text]


def _bundle(parts: list[str], min_beats: int, max_beats: int) -> list[str]:
    if len(parts) <= max_beats:
        return parts if len(parts) >= min_beats else parts
    # Chunk roughly evenly.
    size = max(1, len(parts) // max_beats)
    out: list[str] = []
    for i in range(0, len(parts), size):
        chunk = " ".join(parts[i : i + size]).strip()
        if chunk:
            out.append(chunk)
    return out[:max_beats] or parts


def _classify(index: int, n: int, text: str) -> tuple[str, str, bool]:
    if _RESOLUTION.search(text) or index == n - 1:
        return "resolution", "medium", True
    if _CLIMAX.search(text) or (n >= 3 and index == n - 2):
        return "climax", "high", True
    if _TENSION.search(text):
        return "tension", "high", True
    if _OPENING.search(text) or index == 0:
        return "opening", "low", True
    return "progression", "medium", True


def _role_weight(index: int, n: int, text: str) -> float:
    role, energy, _ = _classify(index, n, text)
    if role == "climax":
        return 1.4
    if role == "opening":
        return 0.9
    if energy == "high":
        return 1.2
    return 1.0


def _guess_tags(text: str) -> list[str]:
    tags: list[str] = []
    mapping = {
        "mountain": r"\bmountain|pass|summit\b",
        "road": r"\broad|route|highway|motorway\b",
        "weather": r"\brain|storm|weather|cloud|cold\b",
        "sunset": r"\bsunset|dusk|evening\b",
        "departure": r"\bleft|depart|start|morning\b",
        "motorcycle": r"\bmotorcycle|bike|ride|riding\b",
    }
    for tag, pat in mapping.items():
        if re.search(pat, text, re.I):
            tags.append(tag)
    return tags


def _title_from_story(text: str) -> str:
    first = text.strip().split("\n", 1)[0].strip()
    if len(first) > 48:
        first = first[:45].rstrip() + "…"
    return first or "Story Cut"
