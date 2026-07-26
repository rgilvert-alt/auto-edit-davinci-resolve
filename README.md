# Auto Edit — DaVinci Resolve

Standalone + CLI auto-edit engine for **DaVinci Resolve Studio**. Primary product flow: paste a **Story**, analyze adventure/travel footage, generate an autonomous **first cut**, then apply through the single Resolve path.

```text
MediaCatalogue → Storyboard → EditPlan → applier.py → Resolve
```

AI/planning never mutates timelines directly. Surfaces: **desktop UI** (`autoedit-ui`), Typer CLI, optional FastMCP.

## Modes

| Mode | Purpose |
|------|---------|
| **Story** | Autonomous first cut from story/brief + clips |
| **Assemble** | Per-clip Scenes / Remove Silence / Keep Full Clips, then stitch |
| **Montage** | Beat-sync clips to required music |
| silence / transcript / scenes | Single-clip CLI utilities |

Adventure footage often has little speech — Story treats text as **editorial intent**, not dialogue to match word-for-word. See [docs/STORYBOARD.md](docs/STORYBOARD.md).

## Two frame clocks

- `ClipSegment.start_frame` / `end_frame` — **source** frames at `source_fps`
- `ClipSegment.record_frame` — **timeline-relative** at `EditPlan.fps`
- Applier adds the timeline start frame (e.g. 108000 at 01:00:00:00)

Storyboard fills stay in **seconds**; frames appear only at EditPlan conversion.

## Install

Python 3.10+, `ffmpeg` on PATH (`brew install ffmpeg`). Resolve scripting: [docs/SETUP.md](docs/SETUP.md).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -e '.[analyzers,ui,mcp]'   # scenes/beats + desktop UI + MCP
cp .env.example .env
```

## Desktop UI

```bash
autoedit-ui
```

1. Add / reorder clips (optional music)
2. Paste Story text
3. Mode: Story (default), Assemble, or Montage
4. **Create First Cut** → writes `.plan.json` (+ `.storyboard.json` for Story)
5. **Apply to Resolve** (Studio running, Local scripting)

## CLI

```bash
# Autonomous story cut
autoedit story \
  --clip A.mp4 --clip B.mp4 \
  --story examples/story.txt \
  --duration 60 \
  --out-timeline "Mountain Day" \
  --preview

# Assemble (scenes per clip, then stitch)
autoedit assemble \
  --clip A.mp4 --clip B.mp4 \
  --per-clip scenes \
  --out-timeline "Assemble Test" \
  --preview

# Montage (music required)
autoedit montage \
  --clip A.mp4 --clip B.mp4 \
  --music track.wav \
  --beats-per-clip 4 \
  --out-timeline "Beat Cut" \
  --preview

autoedit preview "Mountain Day.plan.json"
autoedit apply "Mountain Day.plan.json"
```

`--timeline-fps` pins the timeline clock; otherwise Resolve project fps (if connected) or source fps.

## MCP

Tools: `analyze_media`, `plan_story`, `plan_assemble`, `plan_montage`, `plan_silence`, `plan_transcript`, `plan_scenes`, `preview_plan`, `apply_plan`.

## Tests

```bash
pytest
```

Analysis cache lives in `.autoedit/cache/` (gitignored).

## Project layout

- `src/autoedit/engine.py` — `build_story_plan` / `build_assemble_plan` / `build_montage_plan`
- `src/autoedit/applier.py` — sole Resolve mutator
- `src/autoedit/analysis/` — MediaCatalogue + cache
- `src/autoedit/storyboard/` — generate / fill / convert
- `src/autoedit/planners/` — silence, transcript, scenes, assemble, montage
- `src/autoedit/ui/` — Flet desktop app
- `src/autoedit/cli.py` / `mcp_server.py`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Unit tests run in CI without Resolve or ffmpeg.

## License

[MIT](LICENSE)
