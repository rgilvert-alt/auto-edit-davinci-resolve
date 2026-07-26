"""Music beat detection.

Prefers librosa when installed; otherwise decodes audio via ffmpeg and
estimates a tempo + beat grid with numpy (good enough for Story cut snaps).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

import numpy as np

from ..media import ffmpeg_available


@dataclass
class BeatGrid:
    tempo: float
    beats: list[float]  # beat onset times in seconds


def detect_beats(path: str) -> BeatGrid:
    """Return tempo + beat times (seconds) for an audio or video file."""
    try:
        import librosa  # type: ignore

        return _detect_beats_librosa(path, librosa)
    except ImportError:
        return _detect_beats_ffmpeg(path)


def _detect_beats_librosa(path: str, librosa) -> BeatGrid:
    y, sr = librosa.load(path, sr=None, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    tempo_val = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
    return BeatGrid(tempo=tempo_val, beats=[float(t) for t in beat_times])


def _detect_beats_ffmpeg(path: str, *, sr: int = 22050) -> BeatGrid:
    if not ffmpeg_available():
        raise RuntimeError(
            "Beat detection needs either librosa or ffmpeg on PATH. "
            "Install ffmpeg (brew install ffmpeg) or: pip install 'autoedit[analyzers]'."
        )
    samples = _load_mono_pcm(path, sr=sr)
    if samples.size < sr // 2:
        raise RuntimeError(f"Audio too short or empty for beat detection: {path}")
    return estimate_beat_grid(samples, sr)


def _load_mono_pcm(path: str, *, sr: int) -> np.ndarray:
    """Decode to mono float32 PCM via ffmpeg."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        path,
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        "1",
        "-ar",
        str(sr),
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or f"ffmpeg failed to decode audio from {path}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def estimate_beat_grid(
    samples: np.ndarray,
    sr: int,
    *,
    hop: int = 512,
    min_bpm: float = 70.0,
    max_bpm: float = 180.0,
) -> BeatGrid:
    """Estimate tempo and beat times from mono float samples (numpy only)."""
    if samples.ndim != 1:
        samples = samples.reshape(-1)
    # Onset strength: mean absolute diff of short-time RMS envelope.
    n = len(samples)
    if n < hop * 4:
        duration = n / float(sr)
        return BeatGrid(tempo=120.0, beats=[0.0] if duration > 0 else [])

    frames = 1 + (n - hop) // hop
    rms = np.empty(frames, dtype=np.float64)
    for i in range(frames):
        chunk = samples[i * hop : i * hop + hop]
        rms[i] = float(np.sqrt(np.mean(chunk * chunk) + 1e-12))
    onset = np.maximum(0.0, np.diff(rms, prepend=rms[0]))
    # Light smoothing
    if onset.size >= 3:
        onset = np.convolve(onset, np.ones(3) / 3.0, mode="same")

    tempo = _estimate_tempo(onset, sr=sr, hop=hop, min_bpm=min_bpm, max_bpm=max_bpm)
    period = 60.0 / tempo
    duration = n / float(sr)
    # Align phase to the strongest onset in the first few bars.
    search = min(len(onset), int((4 * period * sr) / hop) + 1)
    phase_frame = int(np.argmax(onset[: max(1, search)]))
    phase_t = phase_frame * hop / float(sr)

    beats: list[float] = []
    t = phase_t
    # Walk backward to start, then forward through the track.
    while t - period >= 0:
        t -= period
    while t < duration:
        if t >= 0:
            beats.append(round(float(t), 4))
        t += period

    if not beats:
        beats = [0.0]
    return BeatGrid(tempo=round(float(tempo), 2), beats=beats)


def _estimate_tempo(
    onset: np.ndarray,
    *,
    sr: int,
    hop: int,
    min_bpm: float,
    max_bpm: float,
) -> float:
    """Autocorrelation peak of the onset envelope → BPM."""
    # Normalize
    x = onset - onset.mean()
    if float(np.std(x)) < 1e-9:
        return 120.0
    x = x / (np.std(x) + 1e-9)
    # Biased autocorr via FFT
    n = int(2 ** np.ceil(np.log2(len(x) * 2)))
    fx = np.fft.rfft(x, n=n)
    ac = np.fft.irfft(fx * np.conj(fx), n=n)[: len(x)]
    ac = ac / (ac[0] + 1e-12)

    min_lag = max(1, int((60.0 / max_bpm) * sr / hop))
    max_lag = min(len(ac) - 1, int((60.0 / min_bpm) * sr / hop))
    if max_lag <= min_lag:
        return 120.0

    window = ac[min_lag : max_lag + 1]
    peak = int(np.argmax(window)) + min_lag
    bpm = 60.0 * sr / (peak * hop)
    # Prefer double/half if closer to a typical dance/edit tempo (~120).
    candidates = [bpm, bpm * 2.0, bpm * 0.5]
    candidates = [c for c in candidates if min_bpm <= c <= max_bpm]
    if not candidates:
        return float(np.clip(bpm, min_bpm, max_bpm))
    return float(min(candidates, key=lambda c: abs(c - 120.0)))
