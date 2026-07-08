# minecraft-redstone-music

Turn a **MIDI file** into a **Minecraft (Java) redstone-music machine**. The playable
runtime is a **datapack + enabled `qzpno_mv` resourcepack + RedPiano mod + Fabric API**:
the datapack drives real note blocks through the mod, and the resourcepack supplies the
sampled instruments (piano / bass / lead / pad / drums). One `--mc-version` flag self-syncs the datapack,
resourcepack, mod build, and profile install to
your target. The supported auto band is **1.21 … 1.21.10** (1.21.9 via min/max `pack.mcmeta`);
**1.21.8 is the verified default & anchor**.

> **For any agent, on any platform.** This is a plain Python CLI — you read these docs and run a
> command. It works the same whether you're driving it from Trae, Codex, Mavis, Work Buddy,
> Claude, or a human shell. If you register it as a **Claude Code skill**, the YAML frontmatter in
> [SKILL.md](SKILL.md) is what lets the loader discover it by trigger phrase — but no loader is
> *required* to just use the folder directly.
>
> **Clone the whole repo — this folder alone is not enough.** The scripts under `scripts/`
> resolve sibling paths like `../binaries/` (prebuilt jars) and `../../poc` (sample sources)
> relative to the repo root. **Do not copy just `minecraft-redstone-music/` out on its own** —
> keep it inside the full repo checkout, or those lookups silently fail to find the prebuilt
> binaries and sample sources (see [BINARIES.md](BINARIES.md)).
>
> One OS caveat: the delivery chain (the generated **`DEPLOY_TO_GAME.bat` installer**) is
> **Windows-only** (Minecraft Java's usual home). On a non-Windows **native host** (not a
> sandbox), install with `--install-now` instead, or copy `dist/` into the profile by hand —
> there is no `.sh`/`.command` equivalent shipped today.

---

> **Shell note:** the multi-line commands below use **bash** syntax (trailing `\` for line
> continuation). On Windows, run them in **Git Bash** (or WSL); PowerShell users should either
> launch `bash` first or rewrite the command onto a single line without the `\` characters.

## Quick start

```bash
# 0. one-time: install the only Python dependency
pip install -r requirements.txt           # just `mido` (MIDI parsing)

# 1. build a datapack from a MIDI (datapack-only smoke test)
python scripts/build_machine.py --midi assets/demo.mid --form inplace \
       --ns mysong --origin 0 0 255 --mc-version 1.21.8
```

- `--midi` your `.mid` (a license-clean `assets/demo.mid` is bundled to smoke-test with).
- `--form` `inplace` (tiny footprint, functionally complete, tested in-game fewer times than
  `swave`) is a safe smoke test; **`swave`** is the recommended default for the full "playhead
  travels the line" machine and **has been tested in-game multiple times and confirmed working**.
  Other forms: `straight`, `custom`, `multilane` (see [SKILL.md](SKILL.md) / [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md)).
- `--ns` datapack namespace (also the scoreboard name — **pick a name you haven't used before**;
  reusing one overwrites that datapack's existing folder). `--origin X Z Y` is the world build
  origin (note the order: **X Z Y**, NOT the `X Y Z` order the in-game F3 screen shows — see
  [QUICKSTART.md](QUICKSTART.md) §3 for the full warning + site-picking guidance). `--mc-version` is any version in the supported auto band
  **1.21 … 1.21.10** (defaults to the verified `1.21.8` anchor); pack_format, function-folder name,
  `pack.mcmeta` shape and sign-NBT dialect all auto-derive from the version table. Outside this
  band the auto-build `raise`s (it only auto-builds green) — that's the cue to switch to the
  **craftsman path** ([docs/VERSION_TACTICS.md](docs/VERSION_TACTICS.md)): the skill still helps
  you build a working machine by hand on any version, it just isn't automated.
- The datapack is written to `build/<ns>/`. Add `--world-dir "<world>/datapacks"` to deploy it
  straight into a world (otherwise copy `build/<ns>/` there yourself). Deploy is opt-in.
- The script prints a stats report **and the exact in-game next steps**. Read them back to the user.

For a real handoff, use the runtime command. It **stages** the datapack + `qzpno_mv.zip` +
mod/Fabric API jars into the workspace `dist/` and emits **`dist/DEPLOY_TO_GAME.bat`** with the
real profile paths + a token baked in. It does **not** install into `<profile>` itself — that
is deliberate: an AI tool usually runs in a filesystem **sandbox** where writing to `C:\Minecraft`
is silently redirected to a mirror the real game never reads (see
[docs/RUNTIME_SANDBOX.md](docs/RUNTIME_SANDBOX.md)). The workspace `dist/` is the one place a
sandbox can write reliably.

```bash
python scripts/prepare_all.py --midi path/to/song.mid --form swave --ns mysong \
       --origin 0 0 255 --mc-version 1.21.8 \
       --world-dir "<profile>/saves/<world>/datapacks" \
       --profile-dir "<profile>" --dist dist \
       [--samples-root path/to/poc | --prebuilt-rp path/to/qzpno_mv.zip] \
       [--prebuilt-mod-jar path/to/redpiano.jar] [--fabric-api-jar path/to/fabric-api.jar]
```

`--world-dir`/`--profile-dir` are the **real** game paths; they get baked into the `.bat`, not
written to now. In a full source checkout, `prepare_all.py` auto-detects `../../poc` as the
sample root (anchored to `scripts/`, i.e. repo-root `poc/`; a hand-passed `--samples-root` is
relative to your shell's cwd, so use `./poc` from the repo root or an absolute path). In a
packaged skill bundle, pass `--samples-root` or `--prebuilt-rp`; otherwise it
refuses to silently skip the resourcepack. Do not use `--skip-*` flags for normal handoff; a
missing RedPiano jar or Fabric API means the runtime is **not ready**, not complete.

**Resourcepack: pick exactly one.** `--samples-root <dir>` (build from a full samples folder),
`--prebuilt-rp <qzpno_mv.zip>` (a pack you already have), or `--skip-resourcepack` (build without
one). The honest effect of `--skip-resourcepack`: the machine plays either **vanilla note-block
timbres** or **total silence** (if `qzpno_mv` sound events are referenced but nothing matching is
enabled in the world) — it is **not** a promise of RedPiano's sampled sound. Only use it when a
matching `qzpno_mv.zip` is already installed and enabled in the target profile.

> **Packaged bundle? Resolve the binaries with one command.** The prebuilt jars + shared
> `qzpno_mv.zip` + a `binaries_manifest.json` ship in a sibling `binaries/` folder (`../binaries/`).
> Run **`python scripts/fetch_binaries.py --mc-version <ver>`** — it picks the version-matched mod
> jar and the resourcepack from `binaries/` (local-first, sha256-verified; remote once the repo is
> public) and tells you whether that jar was listened in-game or only bytecode-checked. Pass its
> outputs as `--prebuilt-rp` / `--prebuilt-mod-jar`. `qzpno_mv.zip` is `rp_format 64` (serves
> 1.21.7/1.21.8 directly); for another version derive a matching pack with
> `build_resourcepack.py --from-zip`. No manifest jar for `<ver>`? recompile. See
> [BINARIES.md](BINARIES.md) and the golden path in [QUICKSTART.md](QUICKSTART.md) §2.

**Install (the user's job, once):** tell the user to **double-click `dist\DEPLOY_TO_GAME.bat` in
Windows Explorer** — a native process, outside the sandbox — which copies everything into the real
profile, enables `qzpno_mv`, and writes `dist\DEPLOY_RECEIPT.txt`. **Never run the `.bat` yourself**
(it would inherit the sandbox). The song is in-game **only** after that receipt exists — confirm
with `python scripts/deploy_bundle.py --verify dist` (`✓ INSTALLED` / `✗`); never claim "installed"
without it. On a genuinely native host (not a sandbox) you may add `--install-now` to install inline
and skip the `.bat`.

## Play it in Minecraft

> Prerequisites: **Java Edition** (not Bedrock — datapacks/`/function`/`/tick rate`/Fabric mods
> don't exist there), and a world with **cheats/OP on** (needed for `/reload`, `/tick rate 80`,
> `/function`; no cheats → Open to LAN → Allow Cheats: ON).

1. Run `prepare_all.py` for the target profile/world, have the **user double-click
   `dist\DEPLOY_TO_GAME.bat`** to install (see the handoff section above), then fully restart
   Minecraft if any jar in `mods/` changed.
2. In-game, **in this exact order** (same as [SKILL.md](SKILL.md) step 4 / [QUICKSTART.md](QUICKSTART.md) step 4):
   1. `/reload` — register the datapack functions.
   2. **`/tick rate 80` — ⚠ YOU must type this manually.** The machine does **NOT** self-set the
      tick rate (auto-set via a command block was tested and does **not** work). Without it,
      playback is **~4× too slow** and melody-cut timing is off.
      **⚠ This speeds up the ENTIRE world** (crops, mob AI, redstone, everything) — be careful on
      a shared/multiplayer world, and run `/tick rate 20` afterward to set it back.
   3. **Confirm the resourcepack** — the installer already enabled `qzpno_mv` in `options.txt`;
      in **Options → Resource Packs** verify `qzpno_mv` is on the right (selected) side.
   4. `/function <ns>:setup` (wait for "built") → press the **[播放]/[play]** sign-button.

> **No sound?** Run `python scripts/doctor.py --dist dist --profile-dir <profile> --world-dir
> <world>/datapacks --mc-version <ver> --ns <ns>` first — it prints a ✓/✗ checklist with a fix
> under each ✗. 9 times out of 10 it's the resourcepack not enabled, `/tick rate 80` not typed,
> RedPiano/Fabric API missing (or a **version-mismatched** mod jar) in `mods/`, or Minecraft not
> restarted after jar changes — see the triage box at the top of [QUICKSTART.md](QUICKSTART.md).

## What's in this folder

| Path | What |
|---|---|
| `scripts/build_machine.py` | the build CLI (this is the entry point you run) |
| `scripts/build_particles.py` | optional: music-synced particle/command tracks (see docs/PARTICLES.md) |
| `scripts/prepare_all.py` | preferred handoff CLI: stages datapack + resourcepack + RedPiano/Fabric API jars into `dist/` and emits `dist\DEPLOY_TO_GAME.bat` (the user double-clicks it to install; verify with `deploy_bundle.py --verify dist`) |
| `scripts/deploy_bundle.py` | `--verify dist`: checks the `DEPLOY_RECEIPT.txt` handshake — the only proof the `.bat` really installed into the game |
| `scripts/doctor.py` | `--dist dist [--profile-dir --world-dir --mc-version --ns]`: one-shot "no sound?" health check — numbered ✓/✗ list, a fix under each ✗, final VERDICT; all-green exits 0 |
| `scripts/midi_report.py` | `--midi <mid> [--form]`: pre-build MIDI quality check (duration / family mix / est. dropped notes / est. footprint / one-line verdict) — run before choosing a form |
| `scripts/fetch_binaries.py` | `--mc-version <ver>`: resolve the version-matched RedPiano jar + shared `qzpno_mv.zip` from the sibling `binaries/` folder (local-first, sha256-verified); `--gen-manifest <dir>` (re)writes the manifest |
| `scripts/build_resourcepack.py` | version-driven `qzpno_mv` resourcepack repack (`--mc-version`; `--from-zip` derives any 1.21.x pack from one shipped zip, or `--samples-root` builds from scratch — see BINARIES.md) |
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

**Datapack-only builds (`scripts/build_machine.py`) are self-contained within this folder**:
every script, the test MIDI, and the instrument map it needs live under
`minecraft-redstone-music/` (it only reaches `../assets/`, still inside this same folder tree).
Invoke it with folder-relative or absolute paths — the scripts resolve their own assets relative
to themselves, so they run from any working directory. No Claude-specific loader, registry entry,
or environment variable is required for this path.

**The full runtime pipeline (`prepare_all.py`, `fetch_binaries.py`, `mod_build.py`) needs the
whole repo**, not just this folder — see the "Clone the whole repo" note near the top of this
file. Those scripts auto-detect sibling paths **outside** `minecraft-redstone-music/`:
`../../binaries` (prebuilt jars), `../../poc` (sample sources), `../../mod/redpiano` (mod
source). If you copy only `minecraft-redstone-music/` elsewhere, those lookups won't find
anything — the two large runtime binaries (RedPiano mod jar + `qzpno_mv.zip`) still need the
sibling `binaries/`/`poc/` folders described in [BINARIES.md](BINARIES.md); they matter only
**in-game**, not to build a bare datapack.

## Scope

**Family A only** — RedPiano mod, real note blocks, `/tick rate 80`. Audio sample-slicing
(`method=slice`, "Family B") is a different external project and is **out of scope** (the build
scripts hard-fail on it). If the user has only an MP3 and wants the original timbre, tell them this
tool needs a MIDI.
