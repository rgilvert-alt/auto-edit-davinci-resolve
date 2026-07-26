"""Analysis cache keyed by path + size + mtime + analysis_version."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .catalogue import ANALYSIS_VERSION, MediaClip


def cache_root() -> Path:
    root = Path.cwd() / ".autoedit" / "cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _file_fingerprint(path: Path) -> str:
    st = path.stat()
    raw = f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}|{ANALYSIS_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def cache_path_for(media_path: str) -> Path:
    path = Path(media_path).expanduser().resolve()
    return cache_root() / f"{_file_fingerprint(path)}.json"


def load_cached_clip(media_path: str) -> MediaClip | None:
    path = Path(media_path).expanduser()
    if not path.is_file():
        return None
    cache_file = cache_path_for(str(path))
    if not cache_file.is_file():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if int(data.get("analysis_version", 0)) != ANALYSIS_VERSION:
            return None
        clip = MediaClip.from_dict(data["clip"])
        if Path(clip.media_path).resolve() != path.resolve():
            return None
        return clip
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def save_cached_clip(clip: MediaClip) -> Path:
    cache_file = cache_path_for(clip.media_path)
    payload = {"analysis_version": ANALYSIS_VERSION, "clip": clip.to_dict()}
    cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return cache_file
