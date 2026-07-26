"""Music beat detection via librosa."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BeatGrid:
    tempo: float
    beats: list[float]  # beat onset times in seconds


def detect_beats(path: str) -> BeatGrid:
    """Return tempo + beat times (seconds) for an audio file.

    Imports librosa lazily so the package works without it installed.
    """
    try:
        import librosa  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "librosa is not installed. Install extras: "
            "pip install 'autoedit[analyzers]'."
        ) from exc

    y, sr = librosa.load(path, sr=None, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    tempo_val = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
    return BeatGrid(tempo=tempo_val, beats=[float(t) for t in beat_times])
