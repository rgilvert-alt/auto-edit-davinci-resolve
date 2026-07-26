"""Thin wrapper around DaVinciResolveScript.

Responsibilities are deliberately narrow: connect, import media, create/select
timelines, and resolve MediaPoolItems by path. All timeline mutation lives in
applier.py so there is exactly one apply path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .config import get_settings


class ResolveConnectionError(RuntimeError):
    """Raised when we cannot reach a running Resolve instance."""


def _ensure_module_path() -> None:
    """Make sure Resolve's Modules dir is importable, using env if needed."""
    settings = get_settings()
    modules = settings.resolve_modules_path
    if modules and modules not in sys.path and Path(modules).exists():
        sys.path.append(modules)


def _import_dvr():
    _ensure_module_path()
    try:
        import DaVinciResolveScript as dvr  # type: ignore

        return dvr
    except ImportError as exc:  # pragma: no cover - env dependent
        raise ResolveConnectionError(
            "Cannot import DaVinciResolveScript. Export RESOLVE_SCRIPT_API/"
            "RESOLVE_SCRIPT_LIB/PYTHONPATH per SETUP.md."
        ) from exc


def try_project_timeline_fps() -> float | None:
    """Read the current project's timeline frame rate, or None if unavailable.

    Deliberately non-fatal: planning must work with Resolve closed.
    """
    try:
        client = ResolveClient()
        rate = client.current_project().GetSetting("timelineFrameRate")
    except Exception:
        return None
    try:
        fps = float(rate)
    except (TypeError, ValueError):
        return None
    return fps if fps > 0 else None


class ResolveClient:
    """Live connection to Resolve; created only when an apply is requested."""

    def __init__(self) -> None:
        dvr = _import_dvr()
        self._resolve = dvr.scriptapp("Resolve")
        if self._resolve is None:  # pragma: no cover - env dependent
            raise ResolveConnectionError(
                "NOT CONNECTED. Is DaVinci Resolve Studio running?"
            )
        self._pm = self._resolve.GetProjectManager()

    # --- project / media pool ---------------------------------------------

    @property
    def resolve(self) -> Any:
        return self._resolve

    def current_project(self) -> Any:
        project = self._pm.GetCurrentProject()
        if project is None:  # pragma: no cover - env dependent
            raise ResolveConnectionError("No project open in Resolve.")
        return project

    def media_pool(self) -> Any:
        return self.current_project().GetMediaPool()

    def import_media(self, paths: list[str]) -> list[Any]:
        """Import files into the current Media Pool folder; return the items."""
        media_storage = self._resolve.GetMediaStorage()
        abs_paths = [str(Path(p).expanduser().resolve()) for p in paths]
        items = media_storage.AddItemListToMediaPool(abs_paths)
        return items or []

    def find_or_import(self, paths: list[str]) -> dict[str, Any]:
        """Map each media path to a MediaPoolItem, importing missing ones.

        Matching is by absolute file path against clip 'File Path' properties.
        """
        wanted = {str(Path(p).expanduser().resolve()): None for p in paths}
        index = self._index_pool_by_path()

        missing = [p for p in wanted if p not in index]
        if missing:
            self.import_media(missing)
            index = self._index_pool_by_path()

        for p in list(wanted):
            item = index.get(p)
            if item is None:  # pragma: no cover - env dependent
                raise ResolveConnectionError(f"Could not import/find media: {p}")
            wanted[p] = item
        return wanted

    def _index_pool_by_path(self) -> dict[str, Any]:
        """Walk all media pool folders and index clips by file path."""
        index: dict[str, Any] = {}
        root = self.media_pool().GetRootFolder()
        stack = [root]
        while stack:
            folder = stack.pop()
            for clip in folder.GetClipList() or []:
                fp = clip.GetClipProperty("File Path")
                if fp:
                    index[str(Path(fp).resolve())] = clip
            stack.extend(folder.GetSubFolderList() or [])
        return index

    # --- timelines ---------------------------------------------------------

    def timeline_names(self) -> set[str]:
        project = self.current_project()
        names: set[str] = set()
        for i in range(1, int(project.GetTimelineCount() or 0) + 1):
            tl = project.GetTimelineByIndex(i)
            if tl is not None:
                names.add(tl.GetName())
        return names

    def unique_timeline_name(self, preferred: str) -> str:
        """Return ``preferred`` or ``preferred 2``, ``preferred 3``, … if taken."""
        existing = self.timeline_names()
        if preferred not in existing:
            return preferred
        n = 2
        while f"{preferred} {n}" in existing:
            n += 1
        return f"{preferred} {n}"

    def set_current_timeline(self, name: str) -> bool:
        """Select a timeline by name if it exists. Returns True on success."""
        project = self.current_project()
        for i in range(1, int(project.GetTimelineCount() or 0) + 1):
            tl = project.GetTimelineByIndex(i)
            if tl is not None and tl.GetName() == name:
                project.SetCurrentTimeline(tl)
                return True
        return False

    def create_timeline(self, name: str) -> Any:
        """Create an empty timeline (unique name if needed) and make it current."""
        mp = self.media_pool()
        actual = self.unique_timeline_name(name)
        timeline = mp.CreateEmptyTimeline(actual)
        if timeline is None:  # pragma: no cover - env dependent
            raise ResolveConnectionError(f"Failed to create timeline '{actual}'.")
        self.current_project().SetCurrentTimeline(timeline)
        return timeline
