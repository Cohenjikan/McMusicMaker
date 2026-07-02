# BINARIES.md — the two large runtime binaries

This package (`minecraft-redstone-music/`) is a **datapack generator + docs**. It needs **no
binaries to RUN** — `scripts/build_machine.py` emits a datapack from a MIDI with only Python +
`mido`. The two large binaries below are needed **only in Minecraft, to make the note blocks
sound** — they are intentionally **not inside this skill folder** (large, built from
separately-licensed samples), but they **do ship in the repo snapshot**, in a sibling
`binaries/` folder (`../binaries/`) indexed by a `binaries_manifest.json`. Resolve them for your
version with **`python scripts/fetch_binaries.py --mc-version <ver>`** (local-first, sha256-verified).

| Binary | Goes in | Why it's needed | version-key |
|---|---|---|---|
| **RedPiano mod jar** (`redpiano-1.0.0-mc<ver>.jar`) | profile `mods/` (restart MC) | turns a note-block press into the correct instrument sample, emitted centered on every player | **one jar per MC version** (see below) |
| **`qzpno_mv.zip` resourcepack** | profile `resourcepacks/` (enable in Options → Resource Packs) | the 103-block sampled instruments the mod plays | **rp_format 64** — covers **1.21.7 AND 1.21.8** |
| **Fabric API jar** (`fabric-api-<v>+mc<ver>.jar`) | profile `mods/` (restart MC) | the mod's runtime dependency; RedPiano refuses to load without it | one per MC version |

> Without these, a generated datapack still builds and the machine still *runs*, but you'll hear
> vanilla note-block tones at best (no mod) or **total silence** (resourcepack not enabled / wrong
> `pack_format` → MC silently disables it). See the "no sound?" box in [QUICKSTART.md](QUICKSTART.md).

---

## The bundled `binaries/` folder (in-repo, version-universal)

The **`binaries/`** folder now ships **inside the repo snapshot**, a sibling of
`minecraft-redstone-music/` (`<root>/binaries/`, so from inside this skill folder it is
`../binaries/`). It holds **every green-band jar we have**, the shared resourcepack, and a
**`binaries_manifest.json`** that indexes them with sha256 hashes and per-jar verified-state:

| File in `binaries/` | For | Notes |
|---|---|---|
| `binaries_manifest.json` | (index) | schema-1 manifest: `base_url`, the resourcepack entry, and one `jars.<ver>` row per shipped jar (file + sha256 + `bytecode_checked` + `listened`). `fetch_binaries.py` reads it. |
| `qzpno_mv.zip` | **all 1.21.x** | resourcepack, `rp_format 64`. Serves 1.21.7/1.21.8 directly; for other versions **derive** a matching pack with `build_resourcepack.py --from-zip` (only `pack.mcmeta` changes). |
| `redpiano-1.0.0-mc<ver>.jar` | **that `<ver>` only** | one mod jar per version; `fabric.mod.json` pins `"minecraft":"~<ver>"`. |
| `fabric-api-*+mc<ver>.jar` | that `<ver>` | optional offline copy of the Fabric API. Normally `prepare_all.py` auto-downloads this from Modrinth (public) — `fetch_binaries.py` does **not** manage it. |

### Rule: `fetch_binaries.py` auto-selects the jar; the resourcepack is shared

Don't hand-pick the jar. Run **`python scripts/fetch_binaries.py --mc-version <ver>`** and it
resolves the right jar + `qzpno_mv.zip` from `binaries/` (sha256-verified). Why a jar must match:
Fabric reads `fabric.mod.json`'s `"minecraft"` range and **refuses to load a jar whose range
doesn't cover the running game** — so the `~1.21.8` jar is rejected on a 1.21.7 game (→ vanilla
tones), and vice-versa. `fetch_binaries` picks the covering one for you.

- **Manifest has a jar for `<ver>`** → `fetch_binaries` returns it (exit 0). Pass it as
  `--prebuilt-mod-jar`. Its VERDICT flags whether that jar was **listened in-game** or only
  **check-jar clean** (listen once after installing).
- **No jar for `<ver>`** → `fetch_binaries` exits nonzero and points you to build one
  (`mod_build.py --mc-version <ver> --write` + Gradle), then `--gen-manifest` to register it.
- **resourcepack** → the same `qzpno_mv.zip` works for any version at rp 64; if `<ver>`'s rp_format
  differs (e.g. 1.21.9 = 69), derive a matching pack with
  `build_resourcepack.py --from-zip ../binaries/qzpno_mv.zip --mc-version <ver> --out <derived.zip>`.

### Honesty: only 1.21.8 has been listened in-game

The manifest marks **exactly one** jar `"listened": true` — **1.21.8**, the in-game anchor. Every
other jar is `bytecode_checked` (passed `mod_build.py --check-jar`, i.e. compiled against the real
maven fabric-api, not a stub) but **NOT yet heard** — a recompiled mixin can be silent or mis-pitched
even when bytecode-clean. So after installing any non-1.21.8 jar, **listen once** to confirm; the
`fetch_binaries` VERDICT says exactly this. A jar filename may carry a `-UNVERIFIED` suffix meaning
the same thing (see below).

### Private now, remote later (same manifest)

The repo is currently **PRIVATE**, so anonymous raw downloads don't work — `fetch_binaries.py` is
**local-first**: on a repo snapshot every binary is already in `binaries/`, so it just sha256-verifies
them (no network). The manifest already bakes in a public `base_url`
(`raw.githubusercontent.com/Cohenjikan/McMusicMaker/main/binaries`); once the repo is **public**, the
**same** `fetch_binaries` call transparently downloads any missing binary from there and verifies its
hash. Nothing about the workflow changes when that happens.

> ⚠ **Never cross jars across versions manually.** If you bypass `fetch_binaries` and pass the wrong
> jar, its `~<ver>` range makes Fabric **reject it at startup** — the mod never loads and note blocks
> fall back to **vanilla** harp/basedrum tones. (Earlier docs wrongly claimed the 1.21.8 jar was
> "byte-compatible with 1.21.7" — **false**; the range check blocks it.)

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

## Easiest: `fetch_binaries.py`, then use the prebuilt binaries

If you received this package as a repo snapshot, the **prebuilt jars + `qzpno_mv.zip` + manifest
ship in the sibling `binaries/` folder** (`../binaries/` from inside this skill). One command
resolves the two you need for a target version, with no Gradle/JDK/ffmpeg:

```bash
python scripts/fetch_binaries.py --mc-version <ver>
```

It sha256-verifies the version's jar + the shared `qzpno_mv.zip` from `binaries/` (local hit =
instant, no network) and prints a VERDICT. Then pass them to `prepare_all.py` as `--prebuilt-rp`
/ `--prebuilt-mod-jar` (Fabric API stays on the public Modrinth auto-download; pass
`--fabric-api-jar` only offline). If `<ver>`'s `rp_format` ≠ 64, first derive a matching pack with
`build_resourcepack.py --from-zip` (next section). See the version-parameterized golden path in
[SKILL.md](SKILL.md) step 4. That's all — skip the build steps below unless the manifest lacks a
jar for your version.

**Maintainer note — registering a new jar:** drop `redpiano-1.0.0-mc<ver>.jar` into `binaries/`
and run `python scripts/fetch_binaries.py --gen-manifest ../binaries`. It rescans the folder and
rewrites `binaries_manifest.json` (parsing `<ver>` from each filename, re-hashing every file),
**preserving** any prior `"listened": true` flags so an in-game confirmation is never lost.

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
- **Easiest — derive from the shipped zip (no samples):** for any version whose `rp_format` ≠ 64,
  `scripts/build_resourcepack.py --from-zip ../binaries/qzpno_mv.zip --mc-version <ver> --out
  <derived.zip>` rewrites **only** `pack.mcmeta` (rp_format + single/minmax shape from the version
  table) and passes every `.ogg` + `sounds.json` through unchanged. This is the normal path — one
  shipped zip → any 1.21.x pack, no licensed sample folder needed.
- **From scratch (needs samples):** `scripts/build_resourcepack.py --samples-root <dir>` builds the
  zip from per-instrument sample folders (`samples_piano` / `samples_bass` / `samples_lead` /
  `samples_pad` / `samples_drums`). **The samples are large/licensed and are NOT in the repo** —
  supply your own, or just use `--from-zip` above. (`--samples-root` and `--from-zip` are mutually
  exclusive.)
- Either way the builder is **version-driven**: `--mc-version` reads the right `rp_format` +
  `pack.mcmeta` shape from the version table in `scripts/redpiano_core.py`. For **1.21.8** that's
  **`rp_format = 64`**; 1.21.9 emits **69** with the `min_format`/`max_format` shape. Flags:
  `--mc-version`, `--samples-root` | `--from-zip`, `--out` (and `--selftest`).

## Other Minecraft versions

A single `--mc-version` flag self-syncs the whole output (datapack + resourcepack + mod-build config)
from `scripts/redpiano_core.py`'s version table (the one source of truth). The **supported auto band
is 1.21 .. 1.21.10**; **1.21.8 is the verified default & anchor** (user-tested in-game), not the only
option. Within that band the datapack `pack_format`, the resourcepack `rp_format`, and the
`pack.mcmeta` shape all derive automatically — including **1.21.9** via the `min_format`/`max_format`
`pack.mcmeta` form. For the **resourcepack**, `fetch_binaries.py` gives you the rp-64 base zip and
`build_resourcepack.py --from-zip` derives any other version's pack from it — no samples needed.

The **mod jar** is the one surface that still needs a **recompile** for a version not already in the
manifest: run `scripts/mod_build.py` to print the verified toolchain (fabric-loom / fabric-loader /
fabric-api / Java / mappings) for a `--mc-version` (or `--write` to retarget the gradle build), build,
then `fetch_binaries.py --gen-manifest ../binaries` to register the result. Within 1.21.x the retarget
is number-only — no Java source edits. See [docs/MOD_ARCHITECTURE.md](docs/MOD_ARCHITECTURE.md) for the
porting checklist.

> The mixin binds to **internal NoteBlock bytecode**, so **every** target version still needs a
> **recompiled jar and one in-game listen** to confirm sound. Versions outside the auto band
> (≤ 1.20.6, or any version not in the table) are **hard-rejected** — the scripts **never guess**.
