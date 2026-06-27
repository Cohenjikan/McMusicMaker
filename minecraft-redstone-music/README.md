# minecraft-redstone-music

Turn a **MIDI file** into a **Minecraft (Java) redstone-music machine**. The playable
runtime is a **datapack + enabled `qzpno_mv` resourcepack + RedPiano mod + Fabric API**:
the datapack drives real note blocks through the mod, and the resourcepack supplies the
sampled instruments (piano / bass / lead / pad / drums). One `--mc-version` flag self-syncs the datapack,
resourcepack, mod build, and profile install to
your target. The supported auto band is **1.21 … 1.21.10** (1.21.9 via min/max `pack.mcmeta`);
**1.21.8 is the verified default & anchor**.

> **For any agent, on any platform.** This is a plain, self-contained folder + one Python
> CLI. There is **no special "skill" loader, registry, or env var** to set up — you read these
> docs and run a command. It works the same whether you're driving it from Trae, Codex, Mavis,
> Work Buddy, Claude, or a human shell.

---

## Quick start

```bash
# 0. one-time: install the only Python dependency
pip install -r requirements.txt           # just `mido` (MIDI parsing)

# 1. build a datapack from a MIDI (datapack-only smoke test)
python scripts/build_machine.py --midi assets/demo.mid --form inplace \
       --ns mysong --origin 0 0 255 --mc-version 1.21.8
```

- `--midi` your `.mid` (a license-clean `assets/demo.mid` is bundled to smoke-test with).
- `--form` `inplace` (rock-solid, tiny, in-game-verified) is the safe smoke test; **`swave`**
  is the recommended default for the full "playhead travels the line" machine. Other forms:
  `straight`, `custom`, `multilane` (see [SKILL.md](SKILL.md) / [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md)).
- `--ns` datapack namespace (also the scoreboard name). `--origin X Z Y` is the world build
  origin (note the order: **X Z Y**). `--mc-version` is any version in the supported auto band
  **1.21 … 1.21.10** (defaults to the verified `1.21.8` anchor); pack_format, function-folder name,
  `pack.mcmeta` shape and sign-NBT dialect all auto-derive from the version table. An unknown
  version still **hard-fails** ("never guess").
- The datapack is written to `build/<ns>/`. Add `--world-dir "<world>/datapacks"` to deploy it
  straight into a world (otherwise copy `build/<ns>/` there yourself). Deploy is opt-in.
- The script prints a stats report **and the exact in-game next steps**. Read them back to the user.

For a real handoff, use the runtime command. It builds/deploys the datapack, builds/copies
the resourcepack into the profile and selects it in `options.txt`, writes the RedPiano mod
build config, auto-detects Gradle + JDK 21 to build/install the RedPiano jar, and reuses or
downloads the matching Fabric API jar:

```bash
python scripts/prepare_all.py --midi path/to/song.mid --form swave --ns mysong \
       --origin 0 0 255 --mc-version 1.21.8 \
       --world-dir "<profile>/saves/<world>/datapacks" \
       [--samples-root ../poc | --prebuilt-rp path/to/qzpno_mv.zip] \
       [--prebuilt-mod-jar path/to/redpiano.jar] [--fabric-api-jar path/to/fabric-api.jar]
```

In a full source checkout, `prepare_all.py` auto-detects `../../poc` as the sample root.
In a packaged skill bundle, pass `--samples-root` or `--prebuilt-rp`; otherwise it refuses
to silently skip the resourcepack. Do not use `--skip-*` flags for normal handoff; a missing
RedPiano jar or Fabric API means the runtime is **not ready**, not complete.

## Play it in Minecraft

1. Run `prepare_all.py` for the target profile/world, then fully restart Minecraft if any
   jar in `mods/` changed.
2. In-game: `/reload` → `/function <ns>:setup` (wait for "built") → press the
   **[播放]/[play]** sign-button. Pressing play auto-runs `/tick rate 80`.

> **No sound?** 9 times out of 10 it's the resourcepack not enabled, RedPiano/Fabric API
> missing from `mods/`, Minecraft not restarted after jar changes, or tick rate reverted — see
> the triage box at the top of [QUICKSTART.md](QUICKSTART.md).

## What's in this folder

| Path | What |
|---|---|
| `scripts/build_machine.py` | the build CLI (this is the entry point you run) |
| `scripts/build_particles.py` | optional: music-synced particle/command tracks (see docs/PARTICLES.md) |
| `scripts/prepare_all.py` | preferred handoff CLI: datapack + resourcepack install/enable + RedPiano jar build/install + Fabric API install |
| `scripts/build_resourcepack.py` | version-driven `qzpno_mv` resourcepack repack (`--mc-version`; samples ship separately, see BINARIES.md) |
| `scripts/mod_build.py` | low-level helper: prints/applies the verified mod toolchain per `--mc-version`; `prepare_all.py` runs the build by default |
| `scripts/redpiano_core.py`, `params_schema.py`, `generators/` | the engine (`VERSION_TABLE` in `redpiano_core.py` is the single source of truth for per-version facts) |
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
