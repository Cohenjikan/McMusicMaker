# BINARIES.md — the two large runtime binaries

This package (`minecraft-redstone-music/`) is a **datapack generator + docs**. It needs **no
binaries to RUN** — `scripts/build_machine.py` emits a datapack from a MIDI with only Python +
`mido`. The two large binaries below are needed **only in Minecraft, to make the note blocks
sound** — they are intentionally **not inside this folder** (they're large and built from
separately-licensed samples), so they ship **alongside** it.

| Binary | Goes in | Why it's needed | `pack_format` (1.21.8) |
|---|---|---|---|
| **RedPiano mod jar** (`redpiano-1.0.0.jar`) | profile `mods/` (restart MC) | turns a note-block press into the correct instrument sample, emitted centered on every player | n/a (Fabric mod) |
| **`qzpno_mv.zip` resourcepack** | profile `resourcepacks/` (enable in Options → Resource Packs) | the 103-block sampled instruments the mod plays | **rp = 64** (this is the 1.21.8 row) |

> Without these, a generated datapack still builds and the machine still *runs*, but you'll hear
> vanilla note-block tones at best (no mod) or **total silence** (resourcepack not enabled / wrong
> `pack_format` → MC silently disables it). See the "no sound?" box in [QUICKSTART.md](QUICKSTART.md).

---

## Easiest: use the prebuilt binaries

If you received this package as a bundle, the **prebuilt `redpiano-1.0.0.jar` and `qzpno_mv.zip`
should be included next to it** (e.g. a sibling `binaries/` folder or the same archive). Drop them
in `mods/` and `resourcepacks/` per the table above. That's all — skip the build steps below.

## Building them yourself (from the source repo)

Both are produced from the **McMusicMaker source repository** (this skill folder is a packaged
*subset* of it; the mod source and sample pipeline are **not** copied in here).

### 1. RedPiano mod jar
- Source: `mod/redpiano/` in the source repo. It's a **Fabric/Loom** mod whose **verified default
  anchor** is MC **1.21.8**, official Mojang mappings, fabric-loader 0.17.3, fabric-api
  0.136.1+1.21.8, **Java 21**. For another target version, run `scripts/mod_build.py --mc-version …`
  to print that version's verified toolchain (the gradle build reads `minecraft_version` etc. from
  `gradle.properties`; `mod_build.py --write` retargets them).
  [docs/MOD_ARCHITECTURE.md](docs/MOD_ARCHITECTURE.md) (bundled here) documents the source in full,
  including the §6.5 build notes.
- Build: from `mod/redpiano/`, run a Gradle build (`build` task) with `JAVA_HOME` pointing at a
  JDK 21. **Note:** there is **no `gradlew` wrapper committed** — use a locally installed Gradle, or
  add a wrapper (`gradle wrapper`) first. Jar output: `mod/redpiano/build/libs/redpiano-1.0.0.jar`.
- After swapping the jar you must **fully restart Minecraft** (a `/reload` is not enough).

### 2. `qzpno_mv.zip` resourcepack
- Built **in this skill** by `scripts/build_resourcepack.py` from per-instrument sample folders
  (`samples_piano` / `samples_bass` / `samples_lead` / `samples_pad` / `samples_drums`). **The
  samples are large/licensed and are NOT in the repo or this package** — supply your own (point
  `--samples-root` at them), or use the prebuilt zip.
- The builder is **version-driven**: pass `--mc-version` and it reads the right `rp_format` and
  `pack.mcmeta` shape from the version table in `scripts/redpiano_core.py`. For **1.21.8** that's
  **`rp_format = 64`**; e.g. 1.21.9 emits `rp_format = 69` with the `min_format`/`max_format`
  shape. Flags: `--mc-version`, `--samples-root`, `--out` (and `--selftest`).

## Other Minecraft versions

A single `--mc-version` flag self-syncs the whole output (datapack + resourcepack + mod-build config)
from `scripts/redpiano_core.py`'s version table (the one source of truth). The **supported auto band
is 1.21 .. 1.21.9**; **1.21.8 is the verified default & anchor** (user-tested in-game), not the only
option. Within that band the datapack `pack_format`, the resourcepack `rp_format`, and the
`pack.mcmeta` shape all derive automatically — including **1.21.9, which is now supported** via the
`min_format`/`max_format` `pack.mcmeta` form (no longer a hard-fail).

The mod, however, must still be **recompiled** per target version: run `scripts/mod_build.py` to print
the verified toolchain (fabric-loom / fabric-loader / fabric-api / Java / mappings) for a given
`--mc-version` (or `--write` to retarget the gradle build). Within 1.21.x the retarget is
number-only — no Java source edits. See [docs/MOD_ARCHITECTURE.md](docs/MOD_ARCHITECTURE.md) for the
porting checklist.

> The mixin binds to **internal NoteBlock bytecode**, so **every** target version still needs a
> **recompiled jar and one in-game listen** to confirm sound. Versions outside the auto band
> (≤ 1.20.6, or any version not in the table) are **hard-rejected** — the scripts **never guess**.
