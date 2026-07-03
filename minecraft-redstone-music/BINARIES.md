# BINARIES.md — the two large runtime binaries

This package (`minecraft-redstone-music/`) is a **datapack generator + docs**. It needs **no
binaries to RUN** — `scripts/build_machine.py` emits a datapack from a MIDI with only Python +
`mido`. The binaries below are needed **only in Minecraft, to make the note blocks sound**.

Two of them ship in the repo (the **mod jar** — one per version — and an offline **Fabric API**
copy); the **`qzpno_mv.zip` resourcepack does NOT** — its sampled instruments are of **unclear
license**, so it is **distributed separately, never committed to this repo** (this restores the
"copyright material stays out of the repo" rule from DEVLOG §8). You **supply your own**
resourcepack — build it from a `qzpno_mv.zip` you already have (`--from-zip`) or from sample
folders (`--samples-root`); see the "Sampled resourcepack" section below.

| Binary | Ships in repo? | Goes in | Why it's needed | version-key |
|---|---|---|---|---|
| **RedPiano mod jar** (`redpiano-1.0.0-mc<ver>.jar`) | ✅ yes (`binaries/`) | profile `mods/` (restart MC) | turns a note-block press into the correct instrument sample, emitted centered on every player | **one jar per MC version** (see below) |
| **`qzpno_mv.zip` resourcepack** | ❌ **no — samples ship separately** | profile `resourcepacks/` (enable in Options → Resource Packs) | the 103-block sampled instruments the mod plays | **rp_format 64** base — build/derive per version |
| **Fabric API jar** (`fabric-api-<v>+mc<ver>.jar`) | ✅ offline copy (`binaries/`, Apache-2.0) | profile `mods/` (restart MC) | the mod's runtime dependency; RedPiano refuses to load without it | one per MC version |

> Resolve the **mod jar** for your version with **`python scripts/fetch_binaries.py --mc-version
> <ver>`** (local-first, sha256-verified). For the **resourcepack**, that same command prints exactly
> how to build/supply your own — it never pretends to ship one.

> Without these, a generated datapack still builds and the machine still *runs*, but you'll hear
> vanilla note-block tones at best (no mod) or **total silence** (resourcepack not enabled / wrong
> `pack_format` → MC silently disables it). See the "no sound?" box in [QUICKSTART.md](QUICKSTART.md).

---

## The bundled `binaries/` folder (in-repo, version-universal)

The **`binaries/`** folder ships **inside the repo snapshot**, a sibling of
`minecraft-redstone-music/` (`<root>/binaries/`, so from inside this skill folder it is
`../binaries/`). It holds **every green-band mod jar we have**, an offline Fabric API copy, and a
**`binaries_manifest.json`** that indexes them with sha256 hashes and per-jar verified-state. The
sampled `qzpno_mv.zip` is **not** here — the manifest carries it only as a *pointer* (`in_repo:
false`), because its samples are unclear-license and ship separately.

| File in `binaries/` | For | Notes |
|---|---|---|
| `binaries_manifest.json` | (index) | schema-1 manifest: `base_url`, one `jars.<ver>` row per shipped jar (file + sha256 + `bytecode_checked` + `listened`), and a `resourcepack` **pointer** (`in_repo: false`, no sha) naming the pack you must supply. `fetch_binaries.py` reads it. |
| `redpiano-1.0.0-mc<ver>.jar` | **that `<ver>` only** | one mod jar per version; `fabric.mod.json` pins `"minecraft":"~<ver>"`. |
| `fabric-api-*+mc<ver>.jar` | that `<ver>` | offline copy of the Fabric API (**Apache-2.0**, from Modrinth / `maven.fabricmc.net`). Normally `prepare_all.py` auto-downloads this from Modrinth (public) — `fetch_binaries.py` does **not** manage it. |
| ~~`qzpno_mv.zip`~~ | — | **NOT in the repo.** Unclear-license samples ship separately; build/derive your own (see "Sampled resourcepack" below). |

### Rule: `fetch_binaries.py` auto-selects the jar; you supply the resourcepack

Don't hand-pick the jar. Run **`python scripts/fetch_binaries.py --mc-version <ver>`** and it
resolves the right jar from `binaries/` (sha256-verified). Why a jar must match: Fabric reads
`fabric.mod.json`'s `"minecraft"` range and **refuses to load a jar whose range doesn't cover the
running game** — so the `~1.21.8` jar is rejected on a 1.21.7 game (→ vanilla tones), and
vice-versa. `fetch_binaries` picks the covering one for you.

- **Manifest has a jar for `<ver>`** → `fetch_binaries` returns it (exit 0). Pass it as
  `--prebuilt-mod-jar`. Its VERDICT flags whether that jar was **listened in-game** or only
  **check-jar clean** (listen once after installing).
- **No jar for `<ver>`** → `fetch_binaries` exits nonzero and points you to build one
  (`mod_build.py --mc-version <ver> --write` + Gradle), then `--gen-manifest` to register it.
- **resourcepack** → `fetch_binaries` reports it as `separate` (○, **not** a failure — the exit code
  hinges on the jar alone) and prints the self-supply commands. Have your own `qzpno_mv.zip`? derive
  a version-matched pack with `build_resourcepack.py --from-zip <your qzpno_mv.zip> --mc-version
  <ver> --out <derived.zip>`; a base rp-64 pack serves 1.21.7/1.21.8 directly, other versions get a
  rewritten `pack.mcmeta`.

### Honesty: only 1.21.8 has been listened in-game

The manifest marks **exactly one** jar `"listened": true` — **1.21.8**, the in-game anchor. Every
other jar is `bytecode_checked` (passed `mod_build.py --check-jar`, i.e. compiled against the real
maven fabric-api, not a stub) but **NOT yet heard** — a recompiled mixin can be silent or mis-pitched
even when bytecode-clean. So after installing any non-1.21.8 jar, **listen once** to confirm; the
`fetch_binaries` VERDICT says exactly this. A jar filename may carry a `-UNVERIFIED` suffix meaning
the same thing (see below).

### Private now, remote later (same manifest)

The repo is currently **PRIVATE**, so anonymous raw downloads don't work — `fetch_binaries.py` is
**local-first**: on a repo snapshot every **mod jar** is already in `binaries/`, so it just
sha256-verifies them (no network). The manifest bakes in a public `base_url`
(`raw.githubusercontent.com/Cohenjikan/McMusicMaker/main/binaries`); once the repo is **public**, the
**same** `fetch_binaries` call transparently downloads any missing **jar** from there and verifies its
hash. The **resourcepack is never fetched** (it's not in the repo, public or not) — you always supply
your own; that's the one part of the workflow that requires a local pack.

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

## Easiest: `fetch_binaries.py` for the jar, then build your resourcepack

If you received this package as a repo snapshot, the **prebuilt mod jars + manifest ship in the
sibling `binaries/` folder** (`../binaries/` from inside this skill). One command resolves the jar
you need for a target version, with no Gradle/JDK:

```bash
python scripts/fetch_binaries.py --mc-version <ver>
```

It sha256-verifies the version's **jar** from `binaries/` (local hit = instant, no network), reports
the **resourcepack** as `separate` (you supply it), and prints a VERDICT. Then pass the jar to
`prepare_all.py` as `--prebuilt-mod-jar` (Fabric API stays on the public Modrinth auto-download; pass
`--fabric-api-jar` only offline), and pass **your own** resourcepack as `--prebuilt-rp`. To make that
resourcepack: if you have a `qzpno_mv.zip`, derive a version-matched pack with
`build_resourcepack.py --from-zip <your qzpno_mv.zip> --mc-version <ver>` (a base rp-64 pack serves
1.21.7/1.21.8 directly); otherwise build from sample folders with `--samples-root` (next section).
See the version-parameterized golden path in [SKILL.md](SKILL.md) step 4. Skip the mod-build steps
below unless the manifest lacks a jar for your version.

**Maintainer note — registering a new jar:** drop `redpiano-1.0.0-mc<ver>.jar` into `binaries/`
and run `python scripts/fetch_binaries.py --gen-manifest ../binaries`. It rescans the folder and
rewrites `binaries_manifest.json` (parsing `<ver>` from each filename, re-hashing every file),
**preserving** any prior `"listened": true` flags so an in-game confirmation is never lost.

## Building them yourself (from the source repo)

Both are produced from the **McMusicMaker source repository** (this skill folder is a packaged
*subset* of it; the mod source and sample pipeline are **not** copied in here). The **mod jar**
already ships prebuilt in `binaries/`; the **resourcepack** never ships and always requires this
build step (or a `qzpno_mv.zip` you already have).

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

### 2. `qzpno_mv.zip` sampled resourcepack — **you supply the samples** (not in this repo)

The 103-block sampled resourcepack is **not distributed with this repo**: its samples are of
**unclear license**, so per the "copyright material stays out of the repo" rule (DEVLOG §8) it ships
**separately**. You provide it, one of two ways:

- **Have your own `qzpno_mv.zip` already? — derive from it (no sample folder):**
  `scripts/build_resourcepack.py --from-zip <your qzpno_mv.zip> --mc-version <ver> --out <derived.zip>`
  rewrites **only** `pack.mcmeta` (rp_format + single/minmax shape from the version table) and passes
  every `.ogg` + `sounds.json` through unchanged. One zip → any 1.21.x pack. For 1.21.7/1.21.8 (both
  rp 64) you can use the zip as-is.
- **Build from scratch (needs sample folders):** `scripts/build_resourcepack.py --samples-root <dir>`
  builds the zip from per-instrument folders (`samples_piano` / `samples_bass` / `samples_lead` /
  `samples_pad` / `samples_drums`), each with a `samples_manifest_<inst>.json`. It only **copies
  already-encoded `.ogg`** (no ffmpeg). (`--samples-root` and `--from-zip` are mutually exclusive.)

**Sample licensing — know what you're bundling.** These are the sources the original pack was built
from; obtain them yourself under their own terms (none are redistributed here):

| Instrument | Source in the original pack | License | You must |
|---|---|---|---|
| **drums** | VCSL / Karoryfer real samples (kick/snare/hihat/tom/crash) | **CC0** (public domain) | free to use; no attribution required |
| **piano** | Salamander Grand Piano | **CC-BY** | **credit the author** if you redistribute |
| **bass / lead / pad** | numpy-synthesized (no external library) | your own synthesis output | regenerate or replace freely |

> The `piano` slice is the reason the shipped `qzpno_mv.zip` is treated as unclear-license for
> *redistribution* — Salamander's CC-BY attribution obligation was never packaged into the zip. If
> you build your own pack, either honor CC-BY for the piano samples or swap in a CC0 / self-owned
> piano set. drums are CC0 and bass/lead/pad are synthetic, so those carry no redistribution burden.

The builder is **version-driven** either way: `--mc-version` reads the right `rp_format` +
`pack.mcmeta` shape from the version table in `scripts/redpiano_core.py`. For **1.21.8** that's
**`rp_format = 64`**; 1.21.9 emits **69** with the `min_format`/`max_format` shape. Flags:
`--mc-version`, `--samples-root` | `--from-zip`, `--out` (and `--selftest`).

## Other Minecraft versions

A single `--mc-version` flag self-syncs the whole output (datapack + resourcepack + mod-build config)
from `scripts/redpiano_core.py`'s version table (the one source of truth). The **supported auto band
is 1.21 .. 1.21.10**; **1.21.8 is the verified default & anchor** (user-tested in-game), not the only
option. Within that band the datapack `pack_format`, the resourcepack `rp_format`, and the
`pack.mcmeta` shape all derive automatically — including **1.21.9** via the `min_format`/`max_format`
`pack.mcmeta` form. For the **resourcepack**, supply your own base `qzpno_mv.zip` (not in the repo)
and `build_resourcepack.py --from-zip <your qzpno_mv.zip>` derives any other version's pack from it
by rewriting only `pack.mcmeta` — no re-encoding needed.

The **mod jar** is the one surface that still needs a **recompile** for a version not already in the
manifest: run `scripts/mod_build.py` to print the verified toolchain (fabric-loom / fabric-loader /
fabric-api / Java / mappings) for a `--mc-version` (or `--write` to retarget the gradle build), build,
then `fetch_binaries.py --gen-manifest ../binaries` to register the result. Within 1.21.x the retarget
is number-only — no Java source edits. See [docs/MOD_ARCHITECTURE.md](docs/MOD_ARCHITECTURE.md) for the
porting checklist.

> The mixin binds to **internal NoteBlock bytecode**, so **every** target version still needs a
> **recompiled jar and one in-game listen** to confirm sound. Versions outside the auto band
> (≤ 1.20.6, or any version not in the table) are **hard-rejected** — the scripts **never guess**.
