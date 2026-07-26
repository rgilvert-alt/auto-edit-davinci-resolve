# Testing AutoEdit (early access)

Thank you for trying this. AutoEdit builds a **documented first cut** from a story brief + clips, then applies it to **DaVinci Resolve Studio**. There is no standalone `.app` yet — you need a short Python install.

## Who this is for

Editors who already use **DaVinci Resolve Studio** on macOS and can install `ffmpeg` + a Python venv. Adventure / travel / GoPro-style dumps are the sweet spot.

## Smoke test (about 15 minutes)

1. **Install** (see [README](../README.md) and [SETUP.md](SETUP.md)):

   ```bash
   git clone https://github.com/rgilvert-alt/auto-edit-davinci-resolve.git
   cd auto-edit-davinci-resolve
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e ".[ui]"
   cp .env.example .env   # set RESOLVE_SCRIPT_* paths
   brew install ffmpeg    # if needed
   ```

2. Open **Resolve Studio**, set **Preferences → System → General → External scripting = Local**.
3. Run `autoedit-ui`, add **5–20 clips** (optional music), paste a short Story.
4. Click **Create First Cut**. Skim the shot list (descriptors / scores / coverage).
5. Optionally Lock / Swap a shot, then **Apply to Resolve**. Confirm a new timeline appears.

## What feedback helps most

Open a GitHub issue with the **Tester feedback** template, or start a [Discussion](https://github.com/rgilvert-alt/auto-edit-davinci-resolve/discussions). Please include:

- macOS version, Python version, Resolve version
- Rough clip count / duration, and whether you used music
- Did Create First Cut succeed? Apply?
- Was the cut *usable as a rough cut*, or mostly wrong selects?
- One sentence on the worst miss (wrong reel, too jumpy, ignored story, etc.)

## Invite blurb (copy / paste)

Use this in email, Discord, Blackmagic forum, or r/davinciresolve:

> I'm looking for Resolve Studio editors to try **AutoEdit** — an open-source tool that turns a short story brief + a dump of adventure/travel clips into a documented first cut in DaVinci Resolve (with reasons per shot, then Apply to a new timeline).
>
> Early stage: macOS + Python install (not a DMG yet). ~15 min smoke test.
>
> Repo: https://github.com/rgilvert-alt/auto-edit-davinci-resolve  
> Tester guide: https://github.com/rgilvert-alt/auto-edit-davinci-resolve/blob/main/docs/TESTING.md  
> Release: https://github.com/rgilvert-alt/auto-edit-davinci-resolve/releases/tag/v0.1.0
>
> If you try it, a short note on whether the cut was usable (and your Resolve/Python versions) would help a lot — Issues or Discussions on the repo are perfect.

## Forum / Reddit post (slightly longer)

**Title ideas:** `Open-source auto first-cut for Resolve Studio (story brief → timeline)` · `Looking for Resolve editors to try an adventure-footage rough-cut tool`

**Body:**

> Problem: you come back from a trip with dozens of clips and a vague sense of the story. Assembling a first cut by hand takes forever.
>
> AutoEdit analyzes the footage (ffmpeg + visual signals; optional CLIP tags), builds a storyboard from your brief, shows why each shot was picked, lets you lock/swap/trim, then applies a frame-accurate plan to a new Resolve timeline.
>
> Needs: macOS, ffmpeg, Python 3.10+, **DaVinci Resolve Studio** with Local scripting. No App Store build yet.
>
> https://github.com/rgilvert-alt/auto-edit-davinci-resolve  
> Smoke test: https://github.com/rgilvert-alt/auto-edit-davinci-resolve/blob/main/docs/TESTING.md
>
> Feedback on cut quality and Apply reliability is especially useful.
