#!/usr/bin/env python3
"""Resolve scripting connection smoke test.

Run with Resolve Studio open and env vars from .env / SETUP.md exported:

    python3 scripts/resolve_smoke.py

Prints the product name and current project on success, or a clear
NOT CONNECTED message otherwise. Never touches a timeline.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except ImportError as exc:
        print(f"Cannot import DaVinciResolveScript: {exc}")
        print("Set RESOLVE_SCRIPT_API/RESOLVE_SCRIPT_LIB/PYTHONPATH (see SETUP.md).")
        return 2

    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        print("NOT CONNECTED (is DaVinci Resolve Studio running?)")
        return 1

    print(f"Connected: {resolve.GetProductName()} {resolve.GetVersionString()}")
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject() if pm else None
    if project is not None:
        print(f"Current project: {project.GetName()}")
    else:
        print("Connected, but no project is open.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
