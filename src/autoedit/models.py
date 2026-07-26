"""EditPlan data model with JSON (de)serialization.

An EditPlan is the single normalized artifact every planner produces and the
only thing the applier consumes. Frames are integers and authoritative.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass
class ClipSegment:
    """One positioned subclip on a timeline.

    Two frame clocks are in play. start_frame/end_frame are source-media frames
    measured at source_fps (in point inclusive, out point exclusive), while
    record_frame is a timeline-relative position measured at the plan's timeline
    fps on track_index (video tracks are 1-based to match Resolve).

    source_fps of None means the source runs at the plan's timeline fps, so both
    clocks coincide.
    """

    media_path: str
    start_frame: int
    end_frame: int
    record_frame: int
    track_index: int = 1
    name: str | None = None
    source_fps: float | None = None

    @property
    def duration_frames(self) -> int:
        """Length in *source* frames."""
        return self.end_frame - self.start_frame

    def duration_seconds(self, timeline_fps: float) -> float:
        """Wall-clock length, using source_fps when it differs from the timeline."""
        fps = self.source_fps or timeline_fps
        if fps <= 0:
            raise ValueError(f"source_fps must be positive, got {fps}")
        return self.duration_frames / fps

    def timeline_span(self, timeline_fps: float) -> int:
        """How many timeline frames this subclip occupies once conformed."""
        return int(round(self.duration_seconds(timeline_fps) * timeline_fps))

    def validate(self) -> None:
        if self.end_frame <= self.start_frame:
            raise ValueError(
                f"end_frame ({self.end_frame}) must be > start_frame "
                f"({self.start_frame}) for {self.media_path}"
            )
        if self.start_frame < 0:
            raise ValueError(f"start_frame must be >= 0, got {self.start_frame}")
        if self.record_frame < 0:
            raise ValueError(f"record_frame must be >= 0, got {self.record_frame}")
        if self.track_index < 1:
            raise ValueError(f"track_index must be >= 1, got {self.track_index}")
        if self.source_fps is not None and self.source_fps <= 0:
            raise ValueError(f"source_fps must be positive, got {self.source_fps}")


@dataclass
class Marker:
    """A timeline marker at a given timeline frame."""

    frame: int
    name: str = ""
    color: str = "Blue"
    note: str = ""
    duration_frames: int = 1


@dataclass
class MusicTrack:
    """Music laid on an audio track, by convention starting at frame 0."""

    media_path: str
    start_frame: int = 0
    track_index: int = 1
    name: str | None = None


@dataclass
class EditPlan:
    """A frame-accurate, previewable description of a timeline to build.

    ``fps`` is the *timeline* frame rate. Clip source in/out points may run at a
    different rate, carried per clip as ClipSegment.source_fps.
    """

    timeline_name: str
    fps: float
    clips: list[ClipSegment] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    music: MusicTrack | None = None
    mode: str | None = None
    schema_version: int = SCHEMA_VERSION

    # --- derived -----------------------------------------------------------

    @property
    def duration_frames(self) -> int:
        """Timeline length (in timeline frames) implied by the furthest out point."""
        ends = [c.record_frame + c.timeline_span(self.fps) for c in self.clips]
        return max(ends) if ends else 0

    def validate(self) -> None:
        if self.fps <= 0:
            raise ValueError(f"fps must be positive, got {self.fps}")
        for clip in self.clips:
            clip.validate()

    # --- serialization -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.music is None:
            data["music"] = None
        return data

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditPlan":
        clips = [ClipSegment(**c) for c in data.get("clips", [])]
        markers = [Marker(**m) for m in data.get("markers", [])]
        music_raw = data.get("music")
        music = MusicTrack(**music_raw) if music_raw else None
        return cls(
            timeline_name=data["timeline_name"],
            fps=float(data["fps"]),
            clips=clips,
            markers=markers,
            music=music,
            mode=data.get("mode"),
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
        )

    @classmethod
    def from_json(cls, text: str) -> "EditPlan":
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: str | Path) -> "EditPlan":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))
