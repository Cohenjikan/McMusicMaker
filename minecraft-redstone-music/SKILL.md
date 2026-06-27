---
name: minecraft-redstone-music
description: >-
  Turn a MIDI file into a playable Minecraft redstone music machine using real
  note blocks (RedPiano mod, Family A). Use this when the user wants to play a
  song / MIDI in Minecraft with redstone or note blocks, build a note-block
  song machine, or convert MIDI to a redstone music build. Triggers on requests
  like "把 MIDI 在 Minecraft 里用红石播放", "note block song", "MIDI to
  redstone music", "用红石播放这首歌", "做一个音符盒播放机", "redstone jukebox
  from MIDI". Multi-instrument (piano/bass/lead/pad/drums), melody-cut, and a
  visual layout designer are supported. Family B (audio sample-slice) is out of
  scope.
---

<!-- The YAML block above is OPTIONAL metadata for Claude Code's skill loader (name +
     trigger phrases). Other agents/platforms can ignore it — there is no loader to satisfy;
     just read the body below (or README.md) and run scripts/build_machine.py. -->

# Minecraft Redstone Music (Family A — RedPiano)

Convert a MIDI file into a self-contained Minecraft **datapack** that drives real
note blocks through the **RedPiano** mod, producing multi-instrument music with a
custom sampled resourcepack. You point the build script at a `.mid`, pick a
machine **form**, and it emits a datapack you `/reload` and play from an in-world
sign console.

## 用户端流程 (onboarding — 任何 agent / 平台按此驱动用户)

To fulfill a "make Minecraft redstone music from this MIDI" request, collect the inputs
below, then run the build command in step 4. (No special "skill" loader is needed — this
is a self-contained folder + one Python CLI; see README.md.)

> ## ⚠ 交付准则 — AGENT MUST READ before reporting success (the #1 failure mode)
> **"Datapack built" is NOT a deliverable, and "self-check passed" / "tier green" is NOT "it works".**
> The datapack only auto-adapts the *commands/format*; the SOUND needs a **version-matched mod jar +
> resourcepack**. If those don't match the MC version, the note blocks fall back to **vanilla** sounds
> (faint harp + booming basedrum) — exactly the symptom when an agent runs `build_machine.py` and stops.
> So for **any MC version other than `1.21.8`** (the only version with prebuilt binaries), BEFORE you
> report success you MUST prepare BOTH binaries:
> 1. **Resourcepack** — `python scripts/build_resourcepack.py --mc-version <v> --samples-root <dir>`.
>    The **samples are NOT in this folder** (licensed; see [BINARIES.md](BINARIES.md)) — obtain them and
>    point `--samples-root` at them. The prebuilt `qzpno_mv.zip` (rp 64) is reusable **only on 1.21.7 / 1.21.8**.
> 2. **Mod** — `python scripts/mod_build.py --mc-version <v> --write`, then `gradle build` in
>    `mod/redpiano/` (JDK 21; **needs network** the first time you target a version). Put the new jar
>    **plus the matching `fabric-api +<v>`** (NOT the 1.21.8 build) in `mods/`, then **restart MC**. The
>    mod source lives in the **full repo**, not this packaged `minecraft-redstone-music/` subfolder.
> 3. **Never claim it "works" before the user has listened in-game.** A recompiled Fabric mixin can
>    compile yet be silent or mis-pitched — only an in-game listen confirms it. Hand off the in-game
>    steps (step 4) and ask the user to confirm they actually hear it.
>
> **One command for 1–2:** `python scripts/prepare_all.py …` runs datapack → resourcepack → mod-config
> (→ optional `gradle build`) in order and stops at the in-game listen. **Simplest reliable path = target
> `1.21.8` (or 1.21.7)** where the binaries already match; pick another `1.21.x` only when you're ready to
> do the full re-adapt + recompile.

1. **收集输入** — ask for three things:
   - **MIDI 文件** path (`.mid`).
   - **存档路径** — the world's `datapacks/` folder, for deployment.
   - **MC 版本号** — default & verified = **`1.21.8`**. The supported auto band is
     **`1.21`..`1.21.10`** (tier "green"): one `--mc-version` flag self-syncs pack_format,
     folders, the pack.mcmeta shape (single ≤1.21.8 / min-max ≥1.21.9), and the sign-NBT
     dialect (SNBT ≥1.21.5). Below **1.20.3** is refused (no `/tick rate` → the tick80
     timing model can't work); **1.20.3–1.20.6** is refused as "yellow" (data adapts but the
     mod needs a Java source-port); an unknown version **hard-fails** (no silent guess).
   > If the user uploads an **MP3 / audio** instead of MIDI: only the **slice** form
   > (Family B) reproduces original timbre, and that lives in the **external
   > `mc-noteblock-demo` repo — this skill cannot build it.** Say so and ask for a MIDI.

2. **选播放形态 — ask the user which form.** If your platform has a structured
   question/choice tool, use it; otherwise just ask in plain text. Default & recommended =
   **`swave` S 型曲折直线** (tell the user this is the default). Other MIDI option:
   **`inplace` 原地调色板** — the in-game-verified rock-solid fallback, tiny footprint.
   (custom routing/particles are step 5, via the HTMLs.) Offer `swave` first / "(推荐)".

3. **自动备好 mod + 音效包** for the chosen version (any of 1.21..1.21.10):
   - The RedPiano mod jar + `qzpno_mv` resourcepack are the two large binaries that ship
     **separately** (not inside this folder). See **[BINARIES.md](BINARIES.md)** for how to
     obtain/build them. Tell the user: drop the jar in `mods/` (restart MC), enable the pack in
     Options → Resource Packs.
   - **resourcepack** — repack it for the target version with
     `scripts/build_resourcepack.py --mc-version <ver> --samples-root <dir>` (rp_format +
     pack.mcmeta shape are read from the version table — no hand-editing).
   - **mod** — within 1.21.x a retarget is **number-only**: `scripts/mod_build.py
     --mc-version <ver> --write` sets the verified toolchain (loom / loader / fabric-api / Java)
     in `mod/redpiano/`, then rebuild the jar. The mixin binds to internal NoteBlock bytecode,
     so a recompiled jar still needs **one in-game listen**, and you should only widen the
     tested range to versions you actually verified. (Below 1.21 the mod needs a Java
     source-port — see `docs/MOD_ARCHITECTURE.md`.)

4. **生成 + 部署** — run `python scripts/build_machine.py --midi <mid> --form swave --ns <ns>
   --origin X Z Y --mc-version <ver> --world-dir <存档>/datapacks`. Report the stats, then the in-game
   steps: `/reload` → `/tick rate 80` → `/function <ns>:setup` → press the **[play]** sign.
   > **One-command (datapack + resourcepack + mod-config in one go):** for a non-1.21.8 target,
   > `scripts/prepare_all.py --midi <mid> --ns <ns> --origin X Z Y --mc-version <ver> --form swave
   > --samples-root <dir> [--world-dir … --rp-out … --gradle <path> --java-home <jdk>]` runs every
   > automatable step in order and stops at the one that can't be: the in-game listen. **For a version
   > other than 1.21.8, build_machine's report prints a ⚠ reminder** that the prebuilt 1.21.8 jar/pack
   > won't load there and must be rebuilt — heed it, or note blocks fall back to vanilla sounds.

5. **自定义需求 → 两个 HTML**(用法都是:浏览器里手动填 → 直接复制或导出 JSON 交给 agent):
   - `designer/layout_designer.html` — **自定义走线方式**(形态 / 尺寸 / 折叠 / 起点)。
     导出 layout params JSON → 传给 `build_machine.py --params`.
   - `designer/particle_editor.html` — **自定义关键帧 + 命令方块位置**(粒子 / 烟花 / 任意命令,
     同步音乐时间与世界坐标)。导出 particle_keyframes JSON → `build_particles.py`(见 docs/PARTICLES.md).

## FEATURE MATRIX (authoritative — single source of truth)

> This table supersedes any conflicting status in `DEVLOG.md`. If DEVLOG and this
> disagree, **this table wins.**

| form | geometry | multi-instrument | melody-cut | designer-params | tested status |
|---|---|---|---|---|---|
| **`inplace`** | palette of distinct note blocks, re-triggered in place (poc/45 + poc/46) | yes — piano/bass/lead/pad/drums | yes (event-level, relative schedule) | partial (`PCOLS`, `ROWGAP`) | **VERIFIED MVP** — user-confirmed "特别好" |
| **`swave`** | S-wave marching-pulse path, dual-track mirror, radiate chords (poc/48) | yes — piano/bass/lead/pad/drums | yes (event-level, absolute schedule) | `XRUN`, `ZMAX`, `track_sep`, `dual_track_mirror` | **CAPABILITY TESTED** — generates OK, awaiting full in-game listen |
| **`straight`** | long straight +X marching line (degenerate swave) — same plumbing | yes | yes | (marching family) | **v1** — shares verified swave pipeline; largest footprint |
| **`custom`** | waypoint route (drawn in the designer), 0-delay dust U-turns — `_layout_custom` lifted from verified poc/47, fed through swave's plumbing | yes | yes | `waypoints` (+ marching family) | **v1** — geometry-confirmed (collision/timeline self-checks pass); single folded line |
| **`multilane`** | one parallel +X lane per voice, shared skeleton (the old 24/30 model); optional signal-track repeater chains for command-block particles (`generators/multilane.py`, promoted from verified poc/49) | yes | yes | `chord_mode=multilane`, `max_poly`, `lane_dz`, `lane_offsets`, `signal_tracks` (dz) | **v1** — geometry confirmed (`olkml`); **HARD-fails over the forceload cap** (a straight machine can't fold itself — long songs must use `swave`) |

> `straight`/`custom` are the SAME generator as `swave` (`generators/swave.py`) with a different path spine; all marching forms reuse the dual-track mirror, per-path forceload, melody-cut, and collision/timeline guards. `multilane` is a distinct topology (`generators/multilane.py`). Two things are genuinely NOT implemented and stay disabled in the designer: **non-`+X` directions** (the geometry is authored `+X` only; the old code silently faked rotation — a bug now hard-failed) and **3D signal-track `dx`/`dy`** offsets (multilane consumes `dz` only). For the full music-synced particle workflow use `designer/particle_editor.html` + `scripts/build_particles.py` (see `docs/PARTICLES.md`).

Notes on the matrix columns:
- **multi-instrument** uses `assets/redpiano_map_multi.json` — 103 note blocks across
  5 instruments (pno/bass/lead/pad/drum), the single source of truth mirrored from the
  mod's `RedPianoMap.java`.
- **melody-cut** is **event-level**: at a melody note's release it issues
  `stopsound @a record <sample-event>`, killing sustaining pad/lead/bass tails that
  would otherwise bury the melody. Piano (natural decay) and drum (transient) are not
  cut. This is not yet per-note (a true per-note cut is out of v1 scope).
- **designer-params** = how much of the `layout_designer.html` export each form
  actually consumes. Unconsumed designer fields cause a **hard fail**, never a silent
  drop (see `docs/CONTRACT.md` §2).

## What it does (the Family A pipeline)

1. **Parse MIDI** with a program-tracking reader: per-channel `program_change`
   tracking, channel 9 → drums, every note tagged with `instr / duration / velocity`.
2. **Quantize** to cells of `U = 2/80 = 0.025 s` (RedPiano runs at `/tick rate 80`,
   so 1 redstone-tick cell = 2 game-ticks).
3. **Resolve** each note to a concrete note block + sample event via the 103-block
   instrument map (nearest pitch band, velocity layer, octave-shift to keep notes in
   the sample's playable range).
4. **Lay out geometry** for the chosen form (collision-guarded grid):
   - `inplace` — a **palette** of only the distinct `(mapping-block, note)` note blocks,
     each re-triggered by a **SIDE-face** redstone block (never bottom). Re-trigger =
     `setblock redstone_block` (air→redstone rising edge = sound), then `+1t` clear back
     to air to re-arm.
   - `swave` — a marching-pulse **S-wave** path of repeaters (delay 1–4) bridged by
     0-delay redstone-dust U-turns, with radiate chords and a mirrored dual track.
5. **Plan melody cuts** — schedule `cutmel` (`stopsound @a record <event>`) at each
   melody note's release, capped so it never overruns the next melody note.
6. **Emit the datapack** — version-aware `pack_format` and function-folder names,
   batched mass-`setblock` build functions, a `load`/`tick`/`setup`/`play` lifecycle,
   and an in-world sign+button console.

The build is staged into `build/<ns>/` and only copied into a world when you
pass `--world-dir` (deploy is opt-in).

## Canonical forms

- **`swave` — the default.** Marching-pulse S-wave path with the visual "playhead travels
  the line" effect; multi-instrument + melody-cut. Generation-verified; full in-game listen
  pending. **This is the product default** (offer it first).
- **`inplace` — the rock-solid fallback.** Tiny footprint (a few chunks), in-place palette
  re-triggering, **user-verified in-game** ("特别好"). Offer when the user wants zero risk or
  a minimal build.
- **`custom` — drawn routes.** The user draws a waypoint path in `layout_designer.html`
  (自定义) and exports `waypoints`; `generators/swave.py` walks it with 0-delay dust U-turns
  through the same verified plumbing. Use when the user wants a specific shape.
- **`straight` — the simple long line.** A degenerate swave (no folding); biggest footprint.
  Mostly superseded by `swave`, kept for completeness.

## Install prerequisites

This skill produces a datapack only. The runtime stack must be installed by the user:

1. **Fabric Loader + Fabric API + Java 21** for the target Minecraft version
   (verified default **1.21.8**; supported auto band **1.21..1.21.10**).
2. **RedPiano mod jar** in `mods/` (then restart Minecraft — a jar swap needs a full
   restart, not `/reload`). This jar is **not inside this folder** — see
   [BINARIES.md](BINARIES.md) for how to obtain/build it (`docs/MOD_ARCHITECTURE.md` is the
   mod-source reference for whoever compiles it).
3. **`qzpno_mv` resourcepack** placed in `resourcepacks/` and **manually enabled** in
   Options → Resource Packs. If its `pack_format` does not match the MC version, MC
   **silently disables it → total silence.** The `pack_format` is version-specific (e.g. **64**
   for 1.21.8) and is auto-set by `scripts/build_resourcepack.py` from the version table.
   This zip is **not inside this folder** — see [BINARIES.md](BINARIES.md).
4. **`/tick rate 80`** must be active when playing — the samples are tuned for it.
   Forgetting it = ~4× slow playback and inaccurate melody-cut timing. The generated
   machine wires a command-block to self-set the rate, but verify in-game.

> **Large binary assets bundled separately.** The prebuilt **RedPiano mod jar** and
> **`qzpno_mv.zip`** resourcepack are large binaries and are **not** in this folder.
> Bundle/distribute them alongside it — full obtain/build instructions are in
> **[BINARIES.md](BINARIES.md)**. The text assets that *are* bundled here are
> `assets/redpiano_map_multi.json` (103-block instrument map) and `assets/demo.mid`.

## Scope

**Family A only** — RedPiano mod, real note blocks. The Family B audio sample-slice
pipeline (`method=slice`) lives in an external repo (`mc-noteblock-demo`) and is **out
of scope**; the generators hard-fail on `method=slice`.

## Next step

See **[QUICKSTART.md](QUICKSTART.md)** for the end-to-end build-and-play checklist and
the "no sound?" troubleshooting box. The authoritative interface spec for the build
scripts is **[docs/CONTRACT.md](docs/CONTRACT.md)**.
