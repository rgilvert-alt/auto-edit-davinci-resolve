"""fill_storyboard + score_candidate: match catalogue segments to intent slots."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..analysis.catalogue import MediaCatalogue, MediaClip, MediaSegment
from .models import SlotFill, StorySlot, Storyboard

MIN_SHOT_S = 0.8
CANDIDATE_COUNT = 5
# Soft-ban near-duplicates of recently used segment embeddings.
DUPLICATE_SIM_THRESHOLD = 0.92


@dataclass
class FillContext:
    used_segment_ids: set[str] = field(default_factory=set)
    chronology_preferred: bool = True
    segment_cursor: dict[str, float] = field(default_factory=dict)
    last_media_path: str | None = None
    file_use_counts: dict[str, int] = field(default_factory=dict)
    slot_position: float = 0.0
    average_shots_per_file: float = 1.0
    intent_embedding: np.ndarray | None = None
    recent_embeddings: list[np.ndarray] = field(default_factory=list)


@dataclass
class ScoreResult:
    score: float
    reason: str
    parts: dict[str, float]


@dataclass
class RankedCandidate:
    score: float
    clip: MediaClip
    seg: MediaSegment
    result: ScoreResult
    offset: float
    duration: float

    def to_fill(self) -> SlotFill:
        return SlotFill(
            media_path=self.clip.media_path,
            start_s=round(self.seg.start_s + self.offset, 3),
            duration_s=round(self.duration, 3),
            score=round(self.score, 3),
            reason=self.result.reason,
            descriptor=self.seg.description,
            tags=list(self.seg.tags),
            score_parts={k: round(v, 3) for k, v in self.result.parts.items()},
            segment_id=self.seg.id,
        )


def fill_storyboard(
    storyboard: Storyboard,
    media_catalogue: MediaCatalogue,
    *,
    chronology_preferred: bool = True,
    candidate_count: int = CANDIDATE_COUNT,
) -> Storyboard:
    """Fill empty/unlocked slots; leave locked fills untouched."""
    if not media_catalogue.clips:
        raise ValueError("MediaCatalogue has no clips")

    if media_catalogue.warnings and not storyboard.analysis_warnings:
        storyboard.analysis_warnings = list(media_catalogue.warnings)

    ctx = FillContext(chronology_preferred=chronology_preferred)
    capture_rank = _capture_ranks(media_catalogue)
    positions = _segment_positions(media_catalogue, capture_rank)
    _seed_context_from_locked(storyboard, media_catalogue, ctx)

    open_slots = [s for s in storyboard.slots if _needs_fill(s)]
    ctx.average_shots_per_file = max(
        1.0,
        (len(open_slots) + sum(1 for s in storyboard.slots if s.locked and s.fill))
        / max(1, len(media_catalogue.clips)),
    )
    last_index = max(1, len(open_slots) - 1)

    for i, slot in enumerate(open_slots):
        ctx.slot_position = i / last_index
        ctx.intent_embedding = _intent_embedding(slot.intent)
        ranked = rank_candidates(
            slot,
            media_catalogue,
            ctx,
            positions,
            top_n=candidate_count,
        )
        if not ranked:
            slot.fill = None
            slot.candidates = []
            continue
        best = ranked[0]
        slot.fill = best.to_fill()
        slot.candidates = [r.to_fill() for r in ranked[1:]]
        _commit_choice(ctx, best.clip, best.seg, best.offset, best.duration)

    return storyboard


def regenerate_unlocked(
    storyboard: Storyboard,
    media_catalogue: MediaCatalogue,
    *,
    chronology_preferred: bool = True,
) -> Storyboard:
    """Clear unlocked fills and refill; locked shots stay put."""
    for slot in storyboard.slots:
        if not slot.locked:
            slot.fill = None
            slot.candidates = []
    storyboard.revision = int(storyboard.revision or 1) + 1
    return fill_storyboard(
        storyboard, media_catalogue, chronology_preferred=chronology_preferred
    )


def rank_candidates(
    slot: StorySlot,
    media_catalogue: MediaCatalogue,
    ctx: FillContext,
    positions: dict[str, float] | None = None,
    *,
    top_n: int = CANDIDATE_COUNT,
) -> list[RankedCandidate]:
    """Return the top-N scored candidates for a slot (best first)."""
    if positions is None:
        positions = _segment_positions(media_catalogue, _capture_ranks(media_catalogue))

    min_usable = min(MIN_SHOT_S, slot.duration_s)
    scored: list[RankedCandidate] = []

    for reusing in (False, True):
        batch: list[RankedCandidate] = []
        for clip, seg in media_catalogue.all_segments():
            cursor = ctx.segment_cursor.get(seg.id, 0.0)
            offset = 0.0 if reusing else cursor
            available = seg.duration_s - offset
            if available < min_usable:
                continue
            if seg.id in ctx.used_segment_ids and not reusing:
                continue
            result = score_candidate(
                slot,
                seg,
                clip,
                ctx,
                positions.get(seg.id, 0.5),
                allow_reuse=True,
                available_s=available,
            )
            score = result.score
            reason = result.reason
            parts = dict(result.parts)
            if reusing:
                score *= 0.75
                reason = f"No unused footage left; reusing segment. {reason}"
                parts["reuse"] = -0.25
                result = ScoreResult(score, reason, parts)
            batch.append(
                RankedCandidate(
                    score=score,
                    clip=clip,
                    seg=seg,
                    result=result,
                    offset=offset,
                    duration=min(slot.duration_s, available),
                )
            )
        if batch:
            batch.sort(key=lambda c: c.score, reverse=True)
            # Deduplicate by segment id, keep best score.
            seen: set[str] = set()
            for cand in batch:
                if cand.seg.id in seen:
                    continue
                seen.add(cand.seg.id)
                scored.append(cand)
                if len(scored) >= top_n:
                    return scored
        if scored:
            return scored
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_n]


def swap_to_candidate(slot: StorySlot, candidate_index: int = 0) -> bool:
    """Promote ``candidates[candidate_index]`` into ``fill``, demoting current fill."""
    if not slot.candidates or candidate_index < 0 or candidate_index >= len(slot.candidates):
        return False
    current = slot.fill
    chosen = slot.candidates.pop(candidate_index)
    if current is not None:
        slot.candidates.insert(0, current)
    slot.fill = chosen
    return True


def coverage_report(storyboard: Storyboard, catalogue: MediaCatalogue) -> str:
    """Human summary of which source minutes were used vs ignored."""
    used_by_path: dict[str, float] = {}
    for slot in storyboard.slots:
        fill = slot.fill
        if fill is None:
            continue
        used_by_path[fill.media_path] = (
            used_by_path.get(fill.media_path, 0.0) + fill.duration_s
        )

    lines: list[str] = []
    unused: list[str] = []
    for clip in catalogue.clips:
        used = used_by_path.get(clip.media_path, 0.0)
        name = Path(clip.media_path).name
        if used <= 0.05:
            unused.append(name)
        else:
            pct = 100.0 * used / max(clip.duration_s, 1e-6)
            lines.append(f"{name}: {used:.0f}s used ({pct:.0f}% of file)")
    if unused:
        lines.append("unused: " + ", ".join(unused[:8]))
    return " · ".join(lines) if lines else "no coverage yet"


def score_candidate(
    slot: StorySlot,
    segment: MediaSegment,
    clip: MediaClip,
    ctx: FillContext,
    segment_position: float,
    *,
    allow_reuse: bool = False,
    available_s: float | None = None,
) -> ScoreResult:
    """Score a segment against a slot using measured signals + CLIP similarity."""
    if not allow_reuse and segment.id in ctx.used_segment_ids:
        return ScoreResult(-1.0, "already used", {})

    parts: dict[str, float] = {}
    reasons: list[str] = []
    score = 0.2 + 0.25 * float(segment.quality_score or 0.5)
    parts["quality"] = 0.25 * float(segment.quality_score or 0.5)

    need = slot.duration_s
    usable = segment.duration_s if available_s is None else available_s
    if usable + 1e-6 >= need:
        dur_term = 0.12
        reasons.append("duration fits")
    else:
        dur_term = 0.12 * (usable / max(need, 1e-6))
        reasons.append("shorter than requested; using available length")
    score += dur_term
    parts["duration"] = dur_term

    prefer_energy = (slot.prefer.energy or "").lower() or None
    sig = segment.signals or {}
    measured_motion = float(sig.get("motion", 0.0))
    if prefer_energy and segment.energy:
        if segment.energy == prefer_energy:
            score += 0.1
            parts["energy"] = 0.1
            reasons.append(f"energy={segment.energy}")
        elif {segment.energy, prefer_energy} == {"medium", "high"}:
            score += 0.04
            parts["energy"] = 0.04
        else:
            score -= 0.05
            parts["energy"] = -0.05

    prefer_motion = (slot.prefer.motion or "").lower() or None
    if prefer_motion and segment.motion == prefer_motion:
        score += 0.06
        parts["motion_pref"] = 0.06

    shake = float(sig.get("shake", 0.0))
    if shake < 0.015:
        score += 0.05
        parts["steady"] = 0.05
        reasons.append("steady")
    elif shake > 0.05:
        score -= 0.06
        parts["steady"] = -0.06
        reasons.append("shaky")

    luma = float(sig.get("luma", 0.5))
    if 0.2 <= luma <= 0.8:
        score += 0.04
        parts["exposure"] = 0.04
    else:
        score -= 0.05
        parts["exposure"] = -0.05
        reasons.append("poor exposure")

    if measured_motion >= 0.08:
        reasons.append("strong motion")
    elif measured_motion >= 0.035:
        reasons.append("moderate motion")

    clip_sim = _clip_similarity(ctx.intent_embedding, segment.embedding)
    if clip_sim is not None:
        clip_term = 0.45 * max(0.0, clip_sim)
        score += clip_term
        parts["clip"] = clip_term
        if clip_sim > 0.15:
            snippet = (slot.intent or "")[:40].strip()
            reasons.insert(0, f"matches '{snippet}' ({clip_sim:.2f} CLIP)")
    else:
        intent_l = (slot.intent or "").lower()
        tag_hits = [
            t
            for t in (segment.tags or [])
            if t.lower() in intent_l
            or any(w in t.lower() for w in intent_l.split() if len(w) > 3)
        ]
        for word in ("mountain", "road", "sunset", "rain", "pass", "forest", "trail"):
            if word in intent_l and any(word in t.lower() for t in segment.tags):
                tag_hits.append(word)
        if tag_hits:
            tag_term = min(0.2, 0.06 * len(set(tag_hits)))
            score += tag_term
            parts["tags"] = tag_term
            reasons.append("tags: " + ", ".join(sorted(set(tag_hits))[:4]))

    prefer_tags = {t.lower() for t in (slot.prefer.tags or [])}
    if prefer_tags and segment.tags:
        overlap = prefer_tags.intersection(t.lower() for t in segment.tags)
        if overlap:
            score += 0.08
            parts["prefer_tags"] = 0.08

    if slot.exclude.has_speech and segment.speech:
        score -= 0.35
        parts["speech"] = -0.35
        reasons.append("penalized speech")
    elif slot.exclude.has_speech and segment.speech is False:
        score += 0.03
        parts["speech"] = 0.03

    if usable < 0.8:
        score -= 0.25
        parts["short"] = -0.25
        reasons.append("short fragment")

    if ctx.last_media_path == clip.media_path:
        score -= 0.15
        parts["variety"] = -0.15
        reasons.append("same file as previous shot")

    overuse = ctx.file_use_counts.get(clip.media_path, 0) / ctx.average_shots_per_file
    if overuse > 1.0:
        penalty = min(0.3, 0.12 * (overuse - 1.0))
        score -= penalty
        parts["spread"] = -penalty
        reasons.append("file already well represented")

    # Soft-ban near-duplicate looks vs recently committed shots.
    dup = _max_embedding_sim(segment.embedding, ctx.recent_embeddings)
    if dup is not None and dup >= DUPLICATE_SIM_THRESHOLD:
        penalty = 0.2 + 0.3 * (dup - DUPLICATE_SIM_THRESHOLD) / max(
            1e-6, 1.0 - DUPLICATE_SIM_THRESHOLD
        )
        score -= penalty
        parts["duplicate"] = -penalty
        reasons.append("near-duplicate of recent shot")

    # Same source window soft ban (overlapping time on same file).
    if segment.id in ctx.used_segment_ids:
        score -= 0.1
        parts["same_window"] = -0.1

    if ctx.chronology_preferred:
        closeness = 1.0 - min(1.0, abs(segment_position - ctx.slot_position))
        chrono = 0.22 * closeness
        score += chrono
        parts["chronology"] = chrono
        if closeness >= 0.8:
            reasons.append("chronological fit")

    if not reasons:
        reasons.append(segment.description or "best available under current scoring")

    return ScoreResult(score, "; ".join(reasons), parts)


def _needs_fill(slot: StorySlot) -> bool:
    if slot.locked and slot.fill is not None:
        return False
    return slot.fill is None or not slot.fill.media_path


def _seed_context_from_locked(
    storyboard: Storyboard, catalogue: MediaCatalogue, ctx: FillContext
) -> None:
    """Treat locked fills as already committed so regenerate won't steal them."""
    by_id = {seg.id: (clip, seg) for clip, seg in catalogue.all_segments()}
    for slot in storyboard.slots:
        if not (slot.locked and slot.fill):
            continue
        fill = slot.fill
        pair = by_id.get(fill.segment_id or "")
        if pair is None:
            pair = _find_segment(catalogue, fill)
        if pair is not None:
            clip, seg = pair
            offset = max(0.0, fill.start_s - seg.start_s)
            _commit_choice(ctx, clip, seg, offset, fill.duration_s)
        else:
            if fill.segment_id:
                ctx.used_segment_ids.add(fill.segment_id)
            ctx.last_media_path = fill.media_path
            ctx.file_use_counts[fill.media_path] = (
                ctx.file_use_counts.get(fill.media_path, 0) + 1
            )


def _find_segment(
    catalogue: MediaCatalogue, fill: SlotFill
) -> tuple[MediaClip, MediaSegment] | None:
    for clip, seg in catalogue.all_segments():
        if clip.media_path != fill.media_path:
            continue
        if seg.start_s - 0.05 <= fill.start_s < seg.end_s + 0.05:
            return clip, seg
    return None


def _commit_choice(
    ctx: FillContext,
    clip: MediaClip,
    seg: MediaSegment,
    offset: float,
    duration: float,
) -> None:
    ctx.used_segment_ids.add(seg.id)
    ctx.segment_cursor[seg.id] = offset + duration
    ctx.last_media_path = clip.media_path
    ctx.file_use_counts[clip.media_path] = (
        ctx.file_use_counts.get(clip.media_path, 0) + 1
    )
    emb = _decode_embedding(seg.embedding)
    if emb is not None:
        ctx.recent_embeddings.append(emb)
        if len(ctx.recent_embeddings) > 8:
            ctx.recent_embeddings = ctx.recent_embeddings[-8:]


def _decode_embedding(embedding_b64: str | None) -> np.ndarray | None:
    if not embedding_b64:
        return None
    try:
        from ..analyzers import semantics as sem

        return sem.decode_embedding_b64(embedding_b64)
    except Exception:
        return None


def _max_embedding_sim(
    embedding_b64: str | None, recent: list[np.ndarray]
) -> float | None:
    if not recent:
        return None
    emb = _decode_embedding(embedding_b64)
    if emb is None:
        return None
    try:
        from ..analyzers import semantics as sem

        return max(sem.cosine_similarity(emb, other) for other in recent)
    except Exception:
        return None


def _intent_embedding(intent: str) -> np.ndarray | None:
    text = (intent or "").strip()
    if not text:
        return None
    try:
        return _cached_text_embed(text)
    except Exception:
        return None


@lru_cache(maxsize=64)
def _cached_text_embed(text: str) -> np.ndarray | None:
    try:
        from ..analyzers import semantics as sem

        ok, _ = sem.available()
        if not ok:
            return None
        return sem.embed_text([text])[0]
    except Exception:
        return None


def _clip_similarity(
    intent_emb: np.ndarray | None, embedding_b64: str | None
) -> float | None:
    if intent_emb is None or not embedding_b64:
        return None
    try:
        from ..analyzers import semantics as sem

        seg_emb = sem.decode_embedding_b64(embedding_b64)
        if seg_emb is None:
            return None
        return sem.cosine_similarity(intent_emb, seg_emb)
    except Exception:
        return None


def _segment_positions(
    catalogue: MediaCatalogue, capture_rank: dict[str, float]
) -> dict[str, float]:
    ordered = sorted(
        catalogue.clips, key=lambda c: capture_rank.get(c.media_path, 0.0)
    )
    n = len(ordered)
    positions: dict[str, float] = {}
    for i, clip in enumerate(ordered):
        base = i / n
        for seg in clip.segments:
            within = seg.start_s / clip.duration_s if clip.duration_s > 0 else 0.0
            positions[seg.id] = base + min(1.0, max(0.0, within)) / n
    return positions


def _capture_ranks(catalogue: MediaCatalogue) -> dict[str, float]:
    dated: list[tuple[str, str]] = []
    undated: list[str] = []
    for clip in catalogue.clips:
        if clip.captured_at:
            dated.append((clip.media_path, clip.captured_at))
        else:
            undated.append(clip.media_path)
    dated.sort(key=lambda x: x[1])
    ranks: dict[str, float] = {}
    for i, (path, _) in enumerate(dated):
        ranks[path] = float(i)
    base = float(len(dated))
    for j, path in enumerate(undated):
        ranks[path] = base + float(j)
    for i, clip in enumerate(catalogue.clips):
        ranks[clip.media_path] = ranks.get(clip.media_path, float(i)) + i * 0.001
    return ranks
