# Contributing

Thanks for helping. This project is an auto-edit engine for **DaVinci Resolve Studio**. Plans are frame-accurate JSON; Resolve is only mutated through one apply path.

## Dev setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui]"
# Optional: Whisper, PySceneDetect, librosa, ONNX CLIP, MCP
pip install -e ".[analyzers,mcp]"
cp .env.example .env
```

Prefer **Python 3.10–3.12** for optional analyzer wheels. On 3.13, core Story/UI still works; `librosa` may fail to build — beat snap falls back to ffmpeg + numpy.

System deps: `ffmpeg` on PATH. Live Resolve applies need Studio running with Local scripting — see [docs/SETUP.md](docs/SETUP.md).

```bash
pytest
```

Unit tests must pass without Resolve, ffmpeg, ONNX, or Whisper. Do not add tests that require those unless they skip cleanly when unavailable.

## Architecture rules (do not break)

1. **Single apply path.** Only `src/autoedit/applier.py` may create or mutate Resolve timelines. Analyzers, planners, storyboard code, CLI, UI, and MCP produce or load an `EditPlan` — they never call Resolve placement APIs directly.
2. **Frame math is source of truth.** Source in/out live on the clip clock (`source_fps`); timeline placement uses `record_frame` at `EditPlan.fps`. Plans must stay previewable as JSON before apply.
3. **Reuse the catalogue → storyboard → EditPlan pipeline** for Story mode. Editor refine (lock / swap / trim / revise) mutates the storyboard, then re-converts — it must not invent a second apply path.
4. **Optional deps degrade gracefully.** Missing PySceneDetect, librosa, or CLIP should warn and fall back (ffmpeg shots / numpy beats / signal-only scoring), not crash silently.

See [docs/STORYBOARD.md](docs/STORYBOARD.md), [docs/SETUP.md](docs/SETUP.md), and [README.md](README.md).

## Pull requests

- Keep PRs focused (one concern per PR when possible).
- Prefer adding or extending unit tests for planners, frame math, scoring, and editor refine helpers.
- Generated run output (`*.plan.json`, root `*.storyboard.json`, `*.catalogue.json`, `.autoedit/`) stays out of git; checked-in samples live under `examples/`.
- Say in the PR what you ran (`pytest`, optional UI/CLI smoke against Resolve).

## Issues

Include OS, Python version, Resolve version (if relevant), and the command or UI step that failed. For bad first cuts, a short story brief + how many clips helps more than screenshots alone.
