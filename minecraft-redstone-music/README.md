# minecraft-redstone-music

Turn a **MIDI file** into a **Minecraft (Java 1.21.8) redstone-music machine**: this tool
emits a self-contained **datapack** that drives real **note blocks** through the **RedPiano**
mod, playing your song with sampled instruments (piano / bass / lead / pad / drums).

> **For any agent, on any platform.** This is a plain, self-contained folder + one Python
> CLI. There is **no special "skill" loader, registry, or env var** to set up — you read these
> docs and run a command. It works the same whether you're driving it from Trae, Codex, Mavis,
> Work Buddy, Claude, or a human shell.

---

## Quick start (the one command)

```bash
# 0. one-time: install the only Python dependency
pip install -r requirements.txt           # just `mido` (MIDI parsing)

# 1. build a datapack from a MIDI (run from INSIDE this folder; paths are folder-relative)
python scripts/build_machine.py --midi assets/demo.mid --form inplace \
       --ns mysong --origin 0 0 255 --mc-version 1.21.8
```

- `--midi` your `.mid` (a license-clean `assets/demo.mid` is bundled to smoke-test with).
- `--form` `inplace` (rock-solid, tiny, in-game-verified) is the safe smoke test; **`swave`**
  is the recommended default for the full "playhead travels the line" machine. Other forms:
  `straight`, `custom`, `multilane` (see [SKILL.md](SKILL.md) / [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md)).
- `--ns` datapack namespace (also the scoreboard name). `--origin X Z Y` is the world build
  origin (note the order: **X Z Y**). `--mc-version` must be `1.21.8` (the supported target).
- The datapack is written to `build/<ns>/`. Add `--world-dir "<world>/datapacks"` to deploy it
  straight into a world (otherwise copy `build/<ns>/` there yourself). Deploy is opt-in.
- The script prints a stats report **and the exact in-game next steps**. Read them back to the user.

## Play it in Minecraft

1. Install the runtime stack (one-time) — see **[BINARIES.md](BINARIES.md)** + [QUICKSTART.md](QUICKSTART.md):
   Fabric Loader + Fabric API + Java 21, the **RedPiano mod jar** in `mods/` (restart MC), and the
   **`qzpno_mv` resourcepack** enabled. *(These two large binaries ship separately — see BINARIES.md.)*
2. Copy `build/<ns>/` into your world's `datapacks/` folder (or use `--world-dir`).
3. In-game: `/reload` → `/tick rate 80` → `/function <ns>:setup` (wait for "built") → press the
   **[播放]/[play]** sign-button. Pressing play also auto-runs `/tick rate 80`.

> **No sound?** 9 times out of 10 it's the resourcepack not enabled, the wrong `/tick rate`, or the
> mod jar missing — see the triage box at the top of [QUICKSTART.md](QUICKSTART.md).

## What's in this folder

| Path | What |
|---|---|
| `scripts/build_machine.py` | the build CLI (this is the entry point you run) |
| `scripts/build_particles.py` | optional: music-synced particle/command tracks (see docs/PARTICLES.md) |
| `scripts/redpiano_core.py`, `params_schema.py`, `generators/` | the engine (no need to touch) |
| `assets/demo.mid`, `assets/redpiano_map_multi.json` | bundled test MIDI + the 103-block instrument map |
| `designer/*.html` | browser tools to customize routing + particle placement (optional) |
| `SKILL.md` | the agent-onboarding flow (collect inputs → pick form → build → install) |
| `QUICKSTART.md` | end-to-end checklist + "no sound?" troubleshooting |
| `docs/CONTRACT.md` | the build-script interface spec | 
| `docs/FEATURE_MATRIX.md` | authoritative capability table (which forms do what) |
| `docs/PARTICLES.md`, `docs/MOD_ARCHITECTURE.md` | particle workflow / mod internals |
| `BINARIES.md` | how to obtain/build the two large binaries (mod jar + resourcepack) |

## Reusing this package (self-distribution)

This folder is **fully self-contained**: every script, the test MIDI, the instrument map, and all
docs are inside it. The only external runtime dependency is **Python 3 + `mido`**
(`pip install -r requirements.txt`). To reuse it from any agent/platform: **keep the folder intact**
and invoke `scripts/build_machine.py` with folder-relative or absolute paths — the scripts resolve
their own assets relative to themselves, so they run from any working directory. No Claude-specific
loader, registry entry, or environment variable is required. The only things that live **outside**
this folder are the two large runtime binaries (RedPiano mod jar + `qzpno_mv.zip`) — see
[BINARIES.md](BINARIES.md); they are needed only **in-game**, not to build a datapack.

## Scope

**Family A only** — RedPiano mod, real note blocks, `/tick rate 80`. Audio sample-slicing
(`method=slice`, "Family B") is a different external project and is **out of scope** (the build
scripts hard-fail on it). If the user has only an MP3 and wants the original timbre, tell them this
tool needs a MIDI.
