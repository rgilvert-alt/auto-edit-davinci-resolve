# Auto Edit — DaVinci Resolve

Python auto-edit engine for **DaVinci Resolve Studio**: silence removal, transcript editing, scene assembly, and music-synced montage.

**Status:** Handoff package only. Implement on the iMac Pro that has Resolve installed.

## Start here (iMac Pro)

1. Read [HANDOFF.md](HANDOFF.md) and paste the kickoff prompt into a new Cursor chat.
2. Follow [docs/SETUP.md](docs/SETUP.md) (Resolve scripting + env vars).
3. Implement per [docs/PLAN.md](docs/PLAN.md).

## Planned usage (after implementation)

```bash
# CLI (examples)
autoedit silence ./footage --out-timeline "Tight Talk"
autoedit montage ./broll --music ./track.wav --out-timeline "Beat Cut"

# MCP: our engine tools + samuelgursky/davinci-resolve-mcp
```

## License

TBD.
