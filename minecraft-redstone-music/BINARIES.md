# BINARIES.md — the two large runtime binaries

This package (`minecraft-redstone-music/`) is a **datapack generator + docs**. It needs **no
binaries to RUN** — `scripts/build_machine.py` emits a datapack from a MIDI with only Python +
`mido`. The two large binaries below are needed **only in Minecraft, to make the note blocks
sound** — they are intentionally **not inside this folder** (they're large and built from
separately-licensed samples), so they ship **alongside** it.

| Binary | Goes in | Why it's needed | `pack_format` (1.21.8) |
|---|---|---|---|
| **RedPiano mod jar** (`redpiano-1.0.0.jar`) | profile `mods/` (restart MC) | turns a note-block press into the correct instrument sample, emitted centered on every player | n/a (Fabric mod) |
| **`qzpno_mv.zip` resourcepack** | profile `resourcepacks/` (enable in Options → Resource Packs) | the 103-block sampled instruments the mod plays | **rp = 64** |

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
- Source: `mod/redpiano/` in the source repo. It's a **Fabric/Loom** mod: MC **1.21.8**, official
  Mojang mappings, fabric-loader 0.17.3, fabric-api 0.136.1+1.21.8, **Java 21**.
  [docs/MOD_ARCHITECTURE.md](docs/MOD_ARCHITECTURE.md) (bundled here) documents the source in full,
  including the §6.5 build notes.
- Build: from `mod/redpiano/`, run a Gradle build (`build` task) with `JAVA_HOME` pointing at a
  JDK 21. **Note:** there is **no `gradlew` wrapper committed** — use a locally installed Gradle, or
  add a wrapper (`gradle wrapper`) first. Jar output: `mod/redpiano/build/libs/redpiano-1.0.0.jar`.
- After swapping the jar you must **fully restart Minecraft** (a `/reload` is not enough).

### 2. `qzpno_mv.zip` resourcepack
- Built by `poc/02e_build_resourcepack.py` in the source repo from per-instrument sample folders
  (`samples_piano` / `samples_bass` / `samples_lead` / `samples_pad` / `samples_drums`). **The
  samples are large/licensed and are NOT in the repo or this package** — supply your own, or use the
  prebuilt zip.
- The builder targets **`rp_format = 64`** for 1.21.8 (it has `detect_rp_format()` to auto-match a
  version). ⚠ The script currently **hardcodes its output path** to a local Modrinth
  `resourcepacks/` dir — edit that path (or copy the produced `qzpno_mv.zip` out manually) before
  running on another machine.

## Other Minecraft versions

For a non-1.21.8 version the mod must be **recompiled** against it and the resourcepack repacked at
that version's `rp_format` (and the datapack `pack_format` changes too — handled automatically by
`scripts/redpiano_core.py`'s version table). See [docs/MOD_ARCHITECTURE.md](docs/MOD_ARCHITECTURE.md)
for the porting checklist. The build scripts here **hard-fail on versions ≥ 1.21.9** until
`pack.mcmeta` `min_format`/`max_format` support is added (a single `pack_format` would be silently
rejected). **1.21.8 is the supported target.**
