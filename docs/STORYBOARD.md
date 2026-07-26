# Storyboard schema

The storyboard describes **editorial intent**, not Resolve frames.

Three layers stay separate:

| Artifact | Meaning |
|----------|---------|
| `MediaCatalogue` | What usable footage exists (signals, tags, descriptors) |
| `Storyboard` | What the film should communicate |
| `EditPlan` | Exactly what `applier.py` will put on the timeline |

## Principles

- Slots are roles + duration + intent.
- Fills use **seconds** (`start_s`, `duration_s`), never source/timeline frames.
- `timeline_fps` in storyboard files is usually `null` until convert time.
- Frame conversion happens only in `storyboard_to_edit_plan`.
- User Story text is editorial intent, not dialogue to match word-for-word.

## Pipeline

```text
analyze_catalogue(clips)          # ffmpeg frames → signals → CLIP tags
    → story_to_storyboard(story, target_duration_s)
    → fill_storyboard(storyboard, media_catalogue)
    → storyboard_to_edit_plan(...)   # optional per-shot markers
    → EditPlan
    → applier.py
```

## Analysis (what actually runs)

1. **Frame sampling** (`analyzers/frames.py`): one ffmpeg pass, keyframes + fps budget (~400 frames max), 224×224 center crop. Tries VideoToolbox, falls back to software.
2. **Visual signals** (`analyzers/visual.py`): motion, shake, luma, contrast, highlight/shadow clipping, colorfulness, sharpness; real shot cuts from histogram distance.
3. **Semantics** (`analyzers/semantics.py`): ONNX CLIP (no PyTorch) zero-shot tags over an adventure vocabulary + segment embeddings.
4. **Descriptor** (`analysis/describe.py`): human-readable line such as `"POV riding shot, forest trail — strong motion, steady, bright"`.

Warnings (missing CLIP, sampling failures) are stored on `MediaCatalogue.warnings` / `Storyboard.analysis_warnings` and shown in the UI — they are never swallowed silently.

## Slot fill (seconds) — schema v3

```json
"fill": {
  "media_path": "/path/to/clip.mp4",
  "start_s": 14.2,
  "duration_s": 4.0,
  "score": 0.82,
  "reason": "matches 'mountain pass' (0.31 CLIP); strong motion; chronological fit",
  "descriptor": "POV riding shot, gravel forest trail — strong motion, steady, bright",
  "tags": ["POV riding shot", "forest trail", "motorcycle"],
  "score_parts": {
    "clip": 0.14,
    "quality": 0.18,
    "chronology": 0.20,
    "steady": 0.05
  },
  "segment_id": "gx_014"
}
```

Slots also carry editor state:

- `locked` — regenerate unlocked leaves this fill alone
- `candidates` — ranked alternates for Swap in the UI

Storyboard metadata: `revision`, `catalogue_path`, `music_path`, `last_timeline_name`, `last_plan_path`.

When music is attached, Story mode snaps cut points toward nearby beats (`snap_fills_to_beats`) after fill. Beat times come from librosa when installed, otherwise an ffmpeg + numpy onset/tempo fallback (no PyTorch/llvmlite required).

Scarcity: if no exact visual exists, the filler picks the closest available segment and explains the approximation in `reason`. Near-duplicate embeddings and overused files are penalized.

## Evidence surfaces

- **AutoEdit UI**: FIRST CUT shot list with thumbnail, in/out, descriptor, score, reason, tags, coverage, plus Lock / Swap / Trim / Reorder / Delete. Mode-aware controls (Story / Assemble / Montage). **Revise unlocked** regenerates only unlocked shots.
- **Resolve markers**: one marker per shot (name = descriptor, note = reason + score parts). Marker frames are shifted by the timeline origin, same as clip `recordFrame`.
- **CLI**: `autoedit analyze --clip … --report analysis.txt`

## Timeline FPS resolution

```text
explicit user FPS → Resolve project FPS → AUTOEDIT_DEFAULT_FPS
```

See [`examples/storyboard.example.json`](../examples/storyboard.example.json).
