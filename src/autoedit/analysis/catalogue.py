"""MediaCatalogue: searchable description of usable footage segments.

Separate from Storyboard (intent) and EditPlan (Resolve frames).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

ANALYSIS_VERSION = 3

Energy = Literal["low", "medium", "high"]
Motion = Literal["low", "medium", "high"]


@dataclass
class MediaSegment:
    id: str
    start_s: float
    end_s: float
    duration_s: float
    scene_index: int | None = None
    speech: bool | None = None
    motion: Motion | None = None
    energy: Energy | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    quality_score: float = 0.5
    signals: dict[str, float] = field(default_factory=dict)
    # base64 float16 CLIP embedding (optional)
    embedding: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaSegment":
        return cls(
            id=data["id"],
            start_s=float(data["start_s"]),
            end_s=float(data["end_s"]),
            duration_s=float(data["duration_s"]),
            scene_index=data.get("scene_index"),
            speech=data.get("speech"),
            motion=data.get("motion"),
            energy=data.get("energy"),
            description=data.get("description"),
            tags=list(data.get("tags") or []),
            quality_score=float(data.get("quality_score", 0.5)),
            signals={k: float(v) for k, v in (data.get("signals") or {}).items()},
            embedding=data.get("embedding"),
        )


@dataclass
class MediaClip:
    media_path: str
    source_fps: float
    duration_s: float
    captured_at: str | None = None
    segments: list[MediaSegment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_path": self.media_path,
            "source_fps": self.source_fps,
            "duration_s": self.duration_s,
            "captured_at": self.captured_at,
            "segments": [s.to_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaClip":
        return cls(
            media_path=data["media_path"],
            source_fps=float(data["source_fps"]),
            duration_s=float(data["duration_s"]),
            captured_at=data.get("captured_at"),
            segments=[MediaSegment.from_dict(s) for s in data.get("segments", [])],
        )


@dataclass
class MediaCatalogue:
    """What exists in the source footage."""

    clips: list[MediaClip] = field(default_factory=list)
    analysis_version: int = ANALYSIS_VERSION
    warnings: list[str] = field(default_factory=list)

    def all_segments(self) -> list[tuple[MediaClip, MediaSegment]]:
        out: list[tuple[MediaClip, MediaSegment]] = []
        for clip in self.clips:
            for seg in clip.segments:
                out.append((clip, seg))
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_version": self.analysis_version,
            "warnings": list(self.warnings),
            "clips": [c.to_dict() for c in self.clips],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    def summary_report(self) -> str:
        """Human-readable analysis report for CLI / MCP."""
        lines = [
            f"MediaCatalogue v{self.analysis_version}",
            f"Clips: {len(self.clips)}",
            f"Segments: {sum(len(c.segments) for c in self.clips)}",
        ]
        if self.warnings:
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        lines.append("")
        for clip in self.clips:
            name = Path(clip.media_path).name
            lines.append(
                f"## {name}  ({clip.duration_s:.1f}s @ {clip.source_fps:g} fps, "
                f"{len(clip.segments)} segments)"
            )
            for seg in clip.segments[:12]:
                desc = seg.description or "(no descriptor)"
                tags = ", ".join(seg.tags[:4]) if seg.tags else "-"
                lines.append(
                    f"  [{seg.start_s:6.1f}-{seg.end_s:6.1f}] "
                    f"q={seg.quality_score:.2f}  {desc}  tags=[{tags}]"
                )
            if len(clip.segments) > 12:
                lines.append(f"  … +{len(clip.segments) - 12} more")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaCatalogue":
        return cls(
            clips=[MediaClip.from_dict(c) for c in data.get("clips", [])],
            analysis_version=int(data.get("analysis_version", ANALYSIS_VERSION)),
            warnings=list(data.get("warnings") or []),
        )

    @classmethod
    def from_json(cls, text: str) -> "MediaCatalogue":
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: str | Path) -> "MediaCatalogue":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))
