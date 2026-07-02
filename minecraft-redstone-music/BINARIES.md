# BINARIES.md — the two large runtime binaries

This package (`minecraft-redstone-music/`) is a **datapack generator + docs**. It needs **no
binaries to RUN** — `scripts/build_machine.py` emits a datapack from a MIDI with only Python +
`mido`. The two large binaries below are needed **only in Minecraft, to make the note blocks
sound** — they are intentionally **not inside this folder** (they're large and built from
separately-licensed samples), so they ship **alongside** it.

| Binary | Goes in | Why it's needed | version-key |
|---|---|---|---|
| **RedPiano mod jar** (`redpiano-1.0.0-mc<ver>.jar`) | profile `mods/` (restart MC) | turns a note-block press into the correct instrument sample, emitted centered on every player | **one jar per MC version** (see below) |
| **`qzpno_mv.zip` resourcepack** | profile `resourcepacks/` (enable in Options → Resource Packs) | the 103-block sampled instruments the mod plays | **rp_format 64** — covers **1.21.7 AND 1.21.8** |
| **Fabric API jar** (`fabric-api-<v>+mc<ver>.jar`) | profile `mods/` (restart MC) | the mod's runtime dependency; RedPiano refuses to load without it | one per MC version |

> Without these, a generated datapack still builds and the machine still *runs*, but you'll hear
> vanilla note-block tones at best (no mod) or **total silence** (resourcepack not enabled / wrong
> `pack_format` → MC silently disables it). See the "no sound?" box in [QUICKSTART.md](QUICKSTART.md).

---

## The bundled `binaries/` folder (what ships beside this skill)

When this skill is delivered as a repo-snapshot bundle, a sibling **`binaries/`** folder ships
next to `minecraft-redstone-music/` (i.e. `<root>/binaries/`, so from inside this skill folder it
is `../binaries/`). This curated round contains **four** files:

| File in `binaries/` | For | Notes |
|---|---|---|
| `qzpno_mv.zip` | **1.21.7 AND 1.21.8** | resourcepack, `rp_format 64`. The data format is identical across 1.21.7/1.21.8, so **one pack serves both** — no per-version repack. |
| `redpiano-1.0.0-mc1.21.8.jar` | **1.21.8 only** | mod jar; `fabric.mod.json` declares `"minecraft":"~1.21.8"`. **Already listened in-game** (verified). |
| `redpiano-1.0.0-mc1.21.7.jar` | **1.21.7 only** | mod jar; `fabric.mod.json` declares `"minecraft":"~1.21.7"`. Freshly compiled on the real toolchain; `--check-jar` bytecode gate passed; **in-game listen still pending** (see `-UNVERIFIED` note below). |
| `fabric-api-0.129.0+1.21.7.jar` | **1.21.7** | Fabric API dependency for a 1.21.7 game. Ship the matching one for 1.21.8 if targeting 1.21.8. |

### Rule: the resourcepack is shared, but pick the jar by MC version

The **data format is version-shared for 1.21.7 ↔ 1.21.8** (datapack `pack_format 81`, resourcepack
`rp_format 64` are the same), so **`qzpno_mv.zip` works on both** — pass the same `--prebuilt-rp`
either way. The **mod jar is NOT interchangeable**: Fabric reads `fabric.mod.json`'s
`"minecraft"` range and **refuses to load a jar whose range doesn't cover the running game**. So:

- **Game is 1.21.7** → pass `--prebuilt-mod-jar ../binaries/redpiano-1.0.0-mc1.21.7.jar`.
- **Game is 1.21.8** → pass `--prebuilt-mod-jar ../binaries/redpiano-1.0.0-mc1.21.8.jar`.
- Any **other 1.21.x** → no prebuilt jar ships; you must **recompile** the mod (see below). The
  resourcepack also needs a repack only if its `rp_format` differs from 64 (e.g. 1.21.9 = 69).

> ⚠ **Do NOT use the 1.21.8 jar on a 1.21.7 game** (or vice-versa). Its `~1.21.8` range makes
> Fabric **reject it at startup** — the mod never loads and the note blocks fall back to **vanilla**
> harp/basedrum tones. (Earlier docs wrongly claimed the 1.21.8 jar was "byte-compatible with
> 1.21.7 and directly usable" — that was **false**; the range check blocks it.)

### What the `-UNVERIFIED` suffix in a jar filename means

A jar named `redpiano-1.0.0-mc<ver>-UNVERIFIED.jar` = **built but not yet confirmed by an in-game
listen** (a recompiled mixin can compile clean yet be silent or mis-pitched — bytecode-clean ≠
mixin-correct). It is safe to ship, but treat it as "verify by listening once." Once someone
confirms sound in-game, the `-UNVERIFIED` suffix is dropped (→ `redpiano-1.0.0-mc<ver>.jar`).

**Before installing any jar** — verified or not — you can re-run the bytecode gate:

```bash
python scripts/mod_build.py --mc-version <ver> --check-jar ../binaries/redpiano-1.0.0-mc<ver>.jar
```

It confirms `fabric.mod.json`'s range covers the target and that the mod was compiled against the
**real** `maven.fabricmc.net` fabric-api (not a hand-written stub). Exit 0 = clean; exit 1 = a real
problem (e.g. the fake-fabric-api nested-`Event` stub footgun) — do not install that jar.

---

## Easiest: use the prebuilt binaries

If you received this package as a bundle, the **prebuilt jars + `qzpno_mv.zip` ship in the sibling
`binaries/` folder** (`../binaries/` from inside this skill). For a **1.21.7 or 1.21.8** game you
need **no Gradle/JDK/ffmpeg at all** — just point the build at them (`--prebuilt-rp`,
`--prebuilt-mod-jar` for the version's jar, `--fabric-api-jar`). See the golden command in
[SKILL.md](SKILL.md) step 4. That's all — skip the build steps below.

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
  add a wrapper (`gradle wrapper`) first. Jar output: `mod/redpiano/build/libs/redpiano-1.0.0.jar`
  (rename to `redpiano-1.0.0-mc<ver>.jar`, appending `-UNVERIFIED` until you've listened in-game).
- After building, gate it with `mod_build.py --mc-version <ver> --check-jar <jar>` (rejects a
  fabric-api stub) **before** trusting it, then **fully restart Minecraft** (a `/reload` is not enough).
- **⚠ In a sandbox you do NOT need to build this at all** for a 1.21.7 or 1.21.8 game — the matching
  jar already ships in `../binaries/`. Do not compile the mod inside a stripped/offline sandbox
  (see the "never hand-write a fabric-api stub" rule in [SKILL.md](SKILL.md)).

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
is 1.21 .. 1.21.10**; **1.21.8 is the verified default & anchor** (user-tested in-game), not the only
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
