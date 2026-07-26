# Setup (macOS + DaVinci Resolve Studio)

Required before **Apply to Resolve** (CLI, UI, or MCP). Preview / plan generation works without Resolve.

## 1. Enable Resolve scripting

1. Open **DaVinci Resolve Studio**.
2. **DaVinci Resolve → Preferences → System → General**.
3. Set **External scripting using** to **Local**.
4. Restart Resolve if prompted.

## 2. Environment variables

Typical Studio paths on macOS (confirm they exist for your version):

```bash
export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
export RESOLVE_SCRIPT_LIB="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
export PYTHONPATH="$PYTHONPATH:$RESOLVE_SCRIPT_API/Modules/"
```

Copy [`.env.example`](../.env.example) to `.env` for the CLI/UI, or add the exports to `~/.zshrc`.

Smoke test (Resolve must be running):

```bash
python3 -c "import DaVinciResolveScript as dvr; r=dvr.scriptapp('Resolve'); print(r.GetProductName() if r else 'NOT CONNECTED')"
```

You should see a product name, not `NOT CONNECTED`.

## 3. System deps

- Python **3.10–3.12** preferred (Resolve scripting compatibility; 3.13 is OK for core UI)
- `ffmpeg` on PATH (`brew install ffmpeg`)

## 4. Project Python deps

```bash
cd /path/to/auto-edit-davinci-resolve
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui]"
pip install -e ".[analyzers,mcp]"   # optional heavy backends
cp .env.example .env
```

Launch UI: `autoedit-ui`.

## 5. Optional MCP servers

- Granular Resolve control: [samuelgursky/davinci-resolve-mcp](https://github.com/samuelgursky/davinci-resolve-mcp)
- This engine’s tools: `autoedit-mcp` (FastMCP) — `analyze_*`, `plan_*`, `preview_plan`, `apply_plan`

Register both in Cursor MCP settings if you want agent-driven editing.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Apply fails / NOT CONNECTED | Studio running; scripting = Local; env paths exist |
| No beat snap / orange warning | ffmpeg on PATH (numpy fallback); librosa optional |
| Assemble Scenes fails on missing PySceneDetect | Update to current code (ffmpeg shot fallback) or `pip install 'autoedit[analyzers]'` |
| CLIP tags missing | `onnxruntime` + `tokenizers` via `[analyzers]`; analysis still runs without them |
