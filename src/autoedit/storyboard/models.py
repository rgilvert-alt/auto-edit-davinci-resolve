"""Storyboard: editorial intent slots (seconds), separate from EditPlan frames."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SlotPrefer:
    analysis: list[str] = field(default_factory=list)
    energy: str | None = None
    motion: str | None = None
    tags: list[str] = field(default_factory=list)
    min_duration_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SlotPrefer":
        data = data or {}
        return cls(
            analysis=list(data.get("analysis") or []),
            energy=data.get("energy"),
            motion=data.get("motion"),
            tags=list(data.get("tags") or []),
            min_duration_s=data.get("min_duration_s"),
        )


@dataclass
class SlotExclude:
    has_speech: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SlotExclude":
        data = data or {}
        return cls(has_speech=data.get("has_speech"))


@dataclass
class SlotFill:
    """Time-based fill. Frame conversion happens only at EditPlan boundary."""

    media_path: str
    start_s: float
    duration_s: float
    score: float = 0.0
    reason: str = ""
    descriptor: str | None = None
    tags: list[str] = field(default_factory=list)
    score_parts: dict[str, float] = field(default_factory=dict)
    # Segment id from MediaCatalogue when known (helps regenerate / anti-dupe).
    segment_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SlotFill":
        return cls(
            media_path=data["media_path"],
            start_s=float(data["start_s"]),
            duration_s=float(data["duration_s"]),
            score=float(data.get("score", 0.0)),
            reason=str(data.get("reason") or ""),
            descriptor=data.get("descriptor"),
            tags=list(data.get("tags") or []),
            score_parts={
                k: float(v) for k, v in (data.get("score_parts") or {}).items()
            },
            segment_id=data.get("segment_id"),
        )


@dataclass
class StorySlot:
    id: str
    role: str
    duration_s: float
    intent: str
    prefer: SlotPrefer = field(default_factory=SlotPrefer)
    exclude: SlotExclude = field(default_factory=SlotExclude)
    fill: SlotFill | None = None
    locked: bool = False
    candidates: list[SlotFill] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "duration_s": self.duration_s,
            "intent": self.intent,
            "prefer": self.prefer.to_dict(),
            "exclude": self.exclude.to_dict(),
            "fill": self.fill.to_dict() if self.fill else None,
            "locked": self.locked,
            "candidates": [c.to_dict() for c in self.candidates],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StorySlot":
        fill_raw = data.get("fill")
        return cls(
            id=data["id"],
            role=data.get("role", "beat"),
            duration_s=float(data["duration_s"]),
            intent=str(data.get("intent") or ""),
            prefer=SlotPrefer.from_dict(data.get("prefer")),
            exclude=SlotExclude.from_dict(data.get("exclude")),
            fill=SlotFill.from_dict(fill_raw) if fill_raw else None,
            locked=bool(data.get("locked", False)),
            candidates=[
                SlotFill.from_dict(c) for c in (data.get("candidates") or [])
            ],
        )


@dataclass
class Storyboard:
    """What the edit is trying to communicate."""

    title: str
    target_duration_s: float
    slots: list[StorySlot] = field(default_factory=list)
    timeline_fps: float | None = None
    style: str | None = None
    schema_version: int = 3
    analysis_warnings: list[str] = field(default_factory=list)
    revision: int = 1
    music_path: str | None = None
    catalogue_path: str | None = None
    last_timeline_name: str | None = None
    last_plan_path: str | None = None
    keep_shoot_order: bool = True

    @property
    def filled_count(self) -> int:
        return sum(1 for s in self.slots if s.fill is not None)

    @property
    def coverage(self) -> float:
        if not self.slots:
            return 0.0
        return self.filled_count / len(self.slots)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "title": self.title,
            "target_duration_s": self.target_duration_s,
            "timeline_fps": self.timeline_fps,
            "style": self.style,
            "analysis_warnings": list(self.analysis_warnings),
            "revision": self.revision,
            "music_path": self.music_path,
            "catalogue_path": self.catalogue_path,
            "last_timeline_name": self.last_timeline_name,
            "last_plan_path": self.last_plan_path,
            "keep_shoot_order": self.keep_shoot_order,
            "slots": [s.to_dict() for s in self.slots],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Storyboard":
        return cls(
            title=data.get("title") or "Untitled",
            target_duration_s=float(data.get("target_duration_s") or 60),
            slots=[StorySlot.from_dict(s) for s in data.get("slots", [])],
            timeline_fps=data.get("timeline_fps"),
            style=data.get("style"),
            schema_version=int(data.get("schema_version", 3)),
            analysis_warnings=list(data.get("analysis_warnings") or []),
            revision=int(data.get("revision") or 1),
            music_path=data.get("music_path"),
            catalogue_path=data.get("catalogue_path"),
            last_timeline_name=data.get("last_timeline_name"),
            last_plan_path=data.get("last_plan_path"),
            keep_shoot_order=bool(data.get("keep_shoot_order", True)),
        )

    @classmethod
    def from_json(cls, text: str) -> "Storyboard":
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: str | Path) -> "Storyboard":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))
