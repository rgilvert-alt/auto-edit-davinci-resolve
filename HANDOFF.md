# Handoff: Auto Edit Engine → iMac Pro

This repo was started on a laptop **without** DaVinci Resolve. Implementation belongs on the **iMac Pro** that has Resolve Studio and Cursor.

Cursor chat history does not sync between machines. Everything the next agent needs is in this repo.

## What to do on the iMac Pro

1. Clone or copy this repo and open it as the Cursor workspace.
2. Install prerequisites (see [docs/SETUP.md](docs/SETUP.md)): Resolve scripting = Local, env vars, Python 3.10–3.12, ffmpeg.
3. Install/register [samuelgursky/davinci-resolve-mcp](https://github.com/samuelgursky/davinci-resolve-mcp) in Cursor MCP settings.
4. Start a **new Cursor chat** and paste the kickoff prompt below (or `@docs/PLAN.md` and say implement it).

## Kickoff prompt (paste into Cursor on the iMac)

```
Implement the Auto Edit Engine for DaVinci Resolve per docs/PLAN.md and HANDOFF.md.
This machine has DaVinci Resolve Studio. Reuse samuelgursky/davinci-resolve-mcp for Resolve control.
Build the auto-edit brain (analyzers → EditPlan → applier) with CLI + our own MCP.
Start with scaffolding + Resolve connection smoke test, then silence / transcript / scenes / music montage.
Do not skip docs/SETUP.md for scripting env vars.
```

## Locked decisions (do not re-ask)

| Topic | Decision |
| --- | --- |
| Edit modes | Silence removal, transcript editing, scene assembly, music montage |
| Resolve | Studio (paid), Python scripting API |
| MCP control layer | Reuse samuelgursky/davinci-resolve-mcp |
| Our surface | Engine MCP tools **and** deterministic CLI |
| Architecture | Analyzers → planners → `EditPlan` JSON → single applier → Resolve |
| Placement API | `MediaPool.AppendToTimeline([{mediaPoolItem, startFrame, endFrame, trackIndex, recordFrame}, ...])` |
| Build machine | iMac Pro with DR installed |

## Key files

- [docs/PLAN.md](docs/PLAN.md) — full architecture and implementation todos
- [docs/SETUP.md](docs/SETUP.md) — Resolve scripting / env setup
- [`.cursor/rules/autoedit.mdc`](.cursor/rules/autoedit.mdc) — persistent agent guidance

## Out of scope for the laptop that prepared this package

Do **not** implement analyzers, Resolve clients, or MCP servers on a machine without Resolve Studio. Only handoff docs live here until the iMac clone.
