# Contributing

Thanks for helping. This project is an auto-edit engine for **DaVinci Resolve Studio**. Plans are frame-accurate JSON; Resolve is only mutated through one apply path.

## Dev setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# Optional: analyzers, desktop UI, MCP
pip install -e ".[analyzers,ui,mcp]"
cp .env.example .env
```

System deps: `ffmpeg` on PATH. Live Resolve applies need Studio running with Local scripting — see [docs/SETUP.md](docs/SETUP.md).

```bash
pytest
```

Unit tests must pass without Resolve, ffmpeg, ONNX, or Whisper. Do not add tests that require those unless they skip cleanly when unavailable.

## Architecture rules (do not break)

1. **Single apply path.** Only `src/autoedit/applier.py` may create or mutate Resolve timelines. Analyzers, planners, storyboard code, CLI, UI, and MCP produce or load an `EditPlan` — they never call Resolve placement APIs directly.
2. **Frame math is source of truth.** Source in/out live on the clip clock (`source_fps`); timeline placement uses `record_frame` at `EditPlan.fps`. Plans must stay previewable as JSON before apply.
3. **Reuse the catalogue → storyboard → EditPlan pipeline** for Story mode. Do not invent a parallel “smart cut” that bypasses `EditPlan`.

See [docs/PLAN.md](docs/PLAN.md), [docs/STORYBOARD.md](docs/STORYBOARD.md), and [HANDOFF.md](HANDOFF.md).

## Pull requests

- Keep PRs focused (one concern per PR when possible).
- Prefer adding or extending unit tests for planners, frame math, and scoring.
- Generated run output (`*.plan.json`, root `*.storyboard.json`, `*.catalogue.json`, `.autoedit/`) stays out of git; checked-in samples live under `examples/`.
- Say in the PR what you ran (`pytest`, optional UI/CLI smoke against Resolve).

## Issues

Include OS, Python version, Resolve version (if relevant), and the command or UI step that failed. For bad first cuts, a short story brief + how many clips helps more than screenshots alone.
