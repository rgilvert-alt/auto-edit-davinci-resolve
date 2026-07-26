"""Word-timed transcription via faster-whisper."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import get_settings


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class TranscriptSegment:
    text: str
    start: float
    end: float
    words: list[Word] = field(default_factory=list)


@dataclass
class Transcript:
    language: str
    segments: list[TranscriptSegment] = field(default_factory=list)

    @property
    def words(self) -> list[Word]:
        out: list[Word] = []
        for seg in self.segments:
            out.extend(seg.words)
        return out


def transcribe(
    path: str,
    model_name: str | None = None,
    language: str | None = None,
) -> Transcript:
    """Transcribe ``path`` with word timestamps.

    Imports faster-whisper lazily so the package works without it installed.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "faster-whisper is not installed. Install extras: "
            "pip install 'autoedit[analyzers]'."
        ) from exc

    model_name = model_name or get_settings().whisper_model
    model = WhisperModel(model_name)
    segments, info = model.transcribe(
        path, language=language, word_timestamps=True
    )

    result_segments: list[TranscriptSegment] = []
    for seg in segments:
        words = [
            Word(text=w.word, start=float(w.start), end=float(w.end))
            for w in (seg.words or [])
        ]
        result_segments.append(
            TranscriptSegment(
                text=seg.text,
                start=float(seg.start),
                end=float(seg.end),
                words=words,
            )
        )
    return Transcript(language=info.language, segments=result_segments)
