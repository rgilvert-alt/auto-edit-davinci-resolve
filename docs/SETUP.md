# Setup (macOS + DaVinci Resolve Studio)

Do this on the **iMac Pro** before running the engine or MCP tools.

## 1. Enable Resolve scripting

1. Open **DaVinci Resolve Studio**.
2. **DaVinci Resolve → Preferences → System → General**.
3. Set **External scripting using** to **Local**.
4. Restart Resolve if prompted.

## 2. Environment variables

Typical Studio install paths on macOS:

```bash
export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
export RESOLVE_SCRIPT_LIB="/Library/Application Support/Blackmagic Design/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
export PYTHONPATH="$PYTHONPATH:$RESOLVE_SCRIPT_API/Modules/"
```

Add these to `~/.zshrc` (or a project `.env` loaded by the CLI/MCP). Confirm paths exist on your Resolve version; adjust if Blackmagic moved them.

Smoke test (Resolve must be running):

```bash
python3 -c "import DaVinciResolveScript as dvr; r=dvr.scriptapp('Resolve'); print(r.GetProductName() if r else 'NOT CONNECTED')"
```

You should see a product name, not `NOT CONNECTED`.

## 3. System deps

- Python **3.10–3.12** (preferred for Resolve scripting compatibility)
- `ffmpeg` on PATH (`brew install ffmpeg`)

## 4. Project Python deps

After scaffolding on the iMac:

```bash
cd "/path/to/Auto Edit Davinci Resolve"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # or: pip install -e .
```

## 5. Resolve MCP (samuelgursky)

Install per upstream README: [samuelgursky/davinci-resolve-mcp](https://github.com/samuelgursky/davinci-resolve-mcp).

Register the server in Cursor MCP settings so the agent can drive Resolve for granular ops. Our auto-edit engine will also call `DaVinciResolveScript` directly for batch EditPlan applies.

## 6. Optional: Cursor MCP for this engine

Once `src/autoedit/mcp_server.py` exists, add a second MCP entry pointing at that FastMCP process (documented in README after implementation).
