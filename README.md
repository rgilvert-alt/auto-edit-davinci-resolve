# Auto Edit — DaVinci Resolve

Auto-edit engine for **DaVinci Resolve Studio**. Paste a **Story**, analyze adventure/travel footage, refine a documented **first cut**, then apply through the single Resolve path.

```text
MediaCatalogue → Storyboard → EditPlan → applier.py → Resolve
```

Planning never mutates timelines directly. Surfaces: **desktop UI** (`autoedit-ui`), Typer CLI, optional FastMCP.

## Modes

| Mode | Purpose |
|------|---------|
| **Story** | First cut from story/brief + clips (visual analysis + CLIP tags when available) |
| **Assemble** | Per-clip Scenes / Remove Silence / Keep Full Clips, then stitch |
| **Montage** | Beat-sync clips to required music |
| silence / transcript / scenes / analyze | Single-clip or catalogue CLI utilities |

Adventure footage often has little speech — Story treats text as **editorial intent**, not dialogue to match word-for-word. See [docs/STORYBOARD.md](docs/STORYBOARD.md).

## Two frame clocks

- `ClipSegment.start_frame` / `end_frame` — **source** frames at `source_fps`
- `ClipSegment.record_frame` — **timeline-relative** at `EditPlan.fps`
- Applier adds the timeline start frame (e.g. 108000 at 01:00:00:00)

Storyboard fills stay in **seconds**; frames appear only at EditPlan conversion.

## Install

- Python **3.10–3.12** preferred (3.13 works for core UI/Story; heavy extras like `librosa` may fail to build)
- `ffmpeg` on PATH (`brew install ffmpeg`)
- Resolve scripting: [docs/SETUP.md](docs/SETUP.md)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui]"
# Optional: Whisper, PySceneDetect, librosa, ONNX CLIP
pip install -e ".[analyzers,mcp]"
cp .env.example .env
```

Core Story analysis needs **ffmpeg + numpy** (always). ONNX CLIP and librosa are optional: without CLIP you still get visual signals/descriptors; without librosa, beat snap uses an ffmpeg + numpy fallback.

## Desktop UI

```bash
autoedit-ui
```

1. Add / reorder clips (optional music) via native file pickers
2. Paste Story text (Story mode)
3. Mode: Story (default), Assemble, or Montage — controls are mode-aware
4. Set **Sequence length** (Story) and Style as needed
5. **Create First Cut** → `.plan.json` (+ `.storyboard.json` / `.catalogue.json` for Story)
6. Refine shots: **Lock / Swap / Trim / Reorder / Delete**; **Revise unlocked** to regenerate the rest
7. **Apply to Resolve** (Studio running, Local scripting)

FIRST CUT shows thumbnails, descriptors, scores, reasons, tags, and source coverage. With music, Story snaps cut points toward beats when detection succeeds.

## CLI

```bash
# Autonomous story cut
autoedit story \
  --clip A.mp4 --clip B.mp4 \
  --story examples/story.txt \
  --duration 60 \
  --out-timeline "Mountain Day" \
  --preview

# Catalogue + human-readable report
autoedit analyze --clip A.mp4 --clip B.mp4 --report analysis.txt

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

Assemble **Scenes** prefers PySceneDetect when installed; otherwise uses the same ffmpeg histogram shot detector as Story analysis.

## MCP

Tools: `analyze_media`, `analyze_catalogue`, `plan_story`, `plan_assemble`, `plan_montage`, `plan_silence`, `plan_transcript`, `plan_scenes`, `preview_plan`, `apply_plan`.

## Tests

```bash
pytest
```

CI runs unit tests on Python 3.10 and 3.12 without Resolve. Analysis cache lives in `.autoedit/cache/` (gitignored). Generated run files at the repo root (`*.plan.json`, `*.storyboard.json`, `*.catalogue.json`) are gitignored; samples live under `examples/`.

## Project layout

- `src/autoedit/engine.py` — `build_story_plan` / `revise_story_plan` / assemble / montage
- `src/autoedit/applier.py` — sole Resolve mutator
- `src/autoedit/analysis/` — MediaCatalogue + cache
- `src/autoedit/storyboard/` — generate / fill / pace / convert
- `src/autoedit/analyzers/` — frames, visual, semantics, beats, silence, scenes
- `src/autoedit/planners/` — silence, transcript, scenes, assemble, montage
- `src/autoedit/ui/` — Flet desktop app
- `src/autoedit/cli.py` / `mcp_server.py`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
