# BINARIES.md — the two large runtime binaries

This package (`minecraft-redstone-music/`) is a **datapack generator + docs**. It needs **no
binaries to RUN** — `scripts/build_machine.py` emits a datapack from a MIDI with only Python +
`mido`. The binaries below are needed **only in Minecraft, to make the note blocks sound**.

All three ship in the repository: versioned **mod jars**, one offline **Fabric API** copy, and the
sampled **`assets/qzpno_mv.zip` resourcepack**. The resourcepack contains a root `CREDITS.txt`
attributing Salamander Grand Piano v3 / Alexander Holm under CC BY 3.0. Drums are VCSL CC0;
bass, lead, and pad are synthesized.

> **License at a glance** (details in the table further down): **piano = Salamander Grand Piano,
> CC-BY (credit the author if you redistribute)**; **drums = VCSL, CC0 (no attribution)**;
> **bass / lead / pad = numpy-synthesized (self-owned)**. Nothing here is "unknown license" — the
> required Salamander attribution is embedded in `qzpno_mv.zip/CREDITS.txt` and must remain there
> in redistributed copies.

| Binary | Ships in repo? | Goes in | Why it's needed | version-key |
|---|---|---|---|---|
| **RedPiano mod jar** (`redpiano-1.0.0-mc<ver>.jar`) | ✅ yes (`binaries/`) | profile `mods/` (restart MC) | turns a note-block press into the correct instrument sample, emitted centered on every player | **one jar per MC version** (see below) |
| **`qzpno_mv.zip` resourcepack** | ✅ yes (`minecraft-redstone-music/assets/`) | profile `resourcepacks/` (enable in Options → Resource Packs) | the 103-block sampled instruments the mod plays | **rp_format 64** base — automatically derived per version |
| **Fabric API jar** (`fabric-api-<v>+mc<ver>.jar`) | ✅ offline copy (`binaries/`, Apache-2.0) | profile `mods/` (restart MC) | the mod's runtime dependency; RedPiano refuses to load without it | one per MC version |

> Resolve the **mod jar** and verify the bundled resourcepack with
> **`python scripts/fetch_binaries.py --mc-version <ver>`**. `prepare_all.py` selects and repacks
> the resourcepack automatically when no replacement flags are supplied.

> Without these, a generated datapack still builds and the machine still *runs*, but you'll hear
> vanilla note-block tones at best (no mod) or **total silence** (resourcepack not enabled / wrong
> `pack_format` → MC silently disables it). See the "no sound?" box in [QUICKSTART.md](QUICKSTART.md).

---

## The bundled `binaries/` folder (in-repo, version-universal)

The **`binaries/`** folder ships **inside the repo snapshot**, a sibling of
`minecraft-redstone-music/` (`<root>/binaries/`, so from inside this skill folder it is
`../binaries/`). It holds **every green-band mod jar we have**, an offline Fabric API copy, and a
**`binaries_manifest.json`** that indexes them with sha256 hashes and per-jar verified-state. The
sampled `qzpno_mv.zip` lives in the skill's `assets/` folder; the manifest records its hash and
`in_repo: true`.

| File in `binaries/` | For | Notes |
|---|---|---|
| `binaries_manifest.json` | (index) | schema-1 manifest: one row per jar plus the bundled resourcepack hash. `fetch_binaries.py` reads it. |
| `redpiano-1.0.0-mc<ver>.jar` | **that `<ver>` only** | one mod jar per version; `fabric.mod.json` pins `"minecraft":"~<ver>"`. |
| `fabric-api-*+mc<ver>.jar` | that `<ver>` | offline copy of the Fabric API (**Apache-2.0**, from Modrinth / `maven.fabricmc.net`). Normally `prepare_all.py` auto-downloads this from Modrinth (public) — `fetch_binaries.py` does **not** manage it. |
| `../minecraft-redstone-music/assets/qzpno_mv.zip` | all supported 1.21.x versions | Canonical rp64 pack with 103 sounds and embedded `CREDITS.txt`; `prepare_all.py` derives other formats automatically. |

### Rule: `fetch_binaries.py` verifies both; `prepare_all.py` stages both

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
- **resourcepack** → `fetch_binaries` hash-checks `assets/qzpno_mv.zip`. `prepare_all.py` uses it by
  default and rewrites `pack.mcmeta` for other supported versions. Replacement packs remain
  supported through `--prebuilt-rp` or `--samples-root`.

### Honesty: currently zero jars are listened-confirmed (1.21.8 just changed, pending re-listen)

As of this build, the manifest marks **all 11 jars** `"listened": false` — including **1.21.8**,
the long-standing in-game anchor. That is not a regression in what was already proven; it's the
manifest being honest about a **new binary**: 1.21.8 was just **rebuilt** to add a global `mute`
check in `rpcfg` (fixes "stopsound, then a leftover note still slips through in the same tick"),
so it is a **different jar** from the one that was previously heard, and its `listened` flag was
correctly reset to `false` until someone confirms *this* jar in-game. For the record: the
**previous, pre-mute** 1.21.8 jar *had* been listened and confirmed working — the underlying sound
path is proven; only this specific rebuild is unconfirmed.

Every jar (all 11) is `bytecode_checked` (passed `mod_build.py --check-jar`, i.e. compiled against
the real maven fabric-api, not a stub) but **NOT yet heard** — a recompiled mixin can be silent or
mis-pitched even when bytecode-clean. So after installing **any** jar right now, including the new
1.21.8, **listen once** to confirm; the `fetch_binaries` VERDICT says exactly this. **Installing
the new 1.21.8 jar requires a full Minecraft restart** (`/reload` does not reload mod jars). Once
someone confirms sound in-game, flip its `listened` flag back to `true` (see "registering a new
jar" below) — don't claim it works before that.

The other ten jars (every version except 1.21.8) do **not** yet have the `mute` check — they were
built before this change and haven't been recompiled since. This is harmless to use as-is: `mute`
is a **datapack-side** scoreboard (`rpcfg mute`) that an old jar simply never reads (a no-op for
it), and `stop`'s existing ~100-tick silence window (`SIL`) still covers the same "trailing sample
tail" case those jars need. `mute` will reach the remaining ten the next time each is recompiled —
see "Maintainer note" below. A jar filename may carry a `-UNVERIFIED` suffix meaning the same
"not yet heard" state (see below).

### Private now, remote later (same manifest)

The repo is currently **PRIVATE**, so anonymous raw downloads don't work — `fetch_binaries.py` is
**local-first**: on a repo snapshot every **mod jar** is already in `binaries/`, so it just
sha256-verifies them (no network). The manifest bakes in a public `base_url`
(`raw.githubusercontent.com/Cohenjikan/McMusicMaker/main/binaries`); once the repo is **public**, the
**same** `fetch_binaries` call transparently downloads any missing **jar** from there and verifies its
hash. The resourcepack is already a local skill asset and is verified from
`minecraft-redstone-music/assets/qzpno_mv.zip`; it is never downloaded at build time.

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

## Easiest: verify the bundled runtime, then build

If you received this package as a repo snapshot, the **prebuilt mod jars + manifest ship in the
sibling `binaries/` folder** (`../binaries/` from inside this skill). One command resolves the jar
you need for a target version, with no Gradle/JDK:

```bash
python scripts/fetch_binaries.py --mc-version <ver>
```

It sha256-verifies the version's **jar** from `binaries/` and the sampled resourcepack from
`assets/`, then prints a VERDICT. Pass the jar to `prepare_all.py` as `--prebuilt-mod-jar`; do not
pass a resourcepack flag unless replacing the bundled sounds. Fabric API stays on the public
Modrinth auto-download; pass `--fabric-api-jar` only for an offline build.
See the version-parameterized golden path in [SKILL.md](SKILL.md) step 4. Skip the mod-build steps
below unless the manifest lacks a jar for your version.

**Maintainer note — registering a new jar:** drop `redpiano-1.0.0-mc<ver>.jar` into `binaries/`
and run `python scripts/fetch_binaries.py --gen-manifest ../binaries`. It rescans the folder and
rewrites `binaries_manifest.json` (parsing `<ver>` from each filename, re-hashing every file),
**preserving** any prior `"listened": true` flags so an in-game confirmation is never lost.

## Building them yourself (from the source repo)

Both are produced from the **McMusicMaker source repository** (this skill folder is a packaged
*subset* of it; the mod source and sample pipeline are **not** copied in here). Both ship
prebuilt: the **mod jar** in `binaries/`, the **resourcepack** as `assets/qzpno_mv.zip` (with
embedded credits). The build steps below are only needed to rebuild or replace them yourself.

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

### 2. `qzpno_mv.zip` sampled resourcepack — bundled with attribution

The 103-block sampled resourcepack ships at `assets/qzpno_mv.zip`. Its piano is Salamander Grand
Piano v3 under CC BY 3.0, and the required author/source/license notice is embedded in
`CREDITS.txt`. Keep that file inside every redistributed copy.

The bundled pack is the default. These optional paths are for replacing or rebuilding it:

- **Have your own `qzpno_mv.zip` already? — derive from it (no sample folder):**
  `scripts/build_resourcepack.py --from-zip <your qzpno_mv.zip> --mc-version <ver> --out <derived.zip>`
  rewrites **only** `pack.mcmeta` (rp_format + single/minmax shape from the version table) and passes
  every `.ogg` + `sounds.json` through unchanged. One zip → any 1.21.x pack. For 1.21.7/1.21.8 (both
  rp 64) you can use the zip as-is.
- **Build from scratch (needs sample folders):** `scripts/build_resourcepack.py --samples-root <dir>`
  builds the zip from per-instrument folders (`samples_piano` / `samples_bass` / `samples_lead` /
  `samples_pad` / `samples_drums`), each with a `samples_manifest_<inst>.json`. It only **copies
  already-encoded `.ogg`** (no ffmpeg). (`--samples-root` and `--from-zip` are mutually exclusive.)
- **Just want a sound, no downloads? — synthesize the open-source demo samples:**
  `python scripts/make_demo_samples.py` writes a full `--samples-root` at `assets/demo_samples/`
  (all 103 sound-event ids the mod plays, synthesized with **numpy** — public-domain / self-owned,
  **no licensed material, no network, no ffmpeg**), then feed it to the builder or straight to
  `prepare_all.py --samples-root assets/demo_samples`. Needs the two extra deps in
  `requirements-demo.txt` (`numpy` + `soundfile`; libsndfile inside the `soundfile` wheel encodes
  the `.ogg` directly). This is the **"先听个响" path** in the root README / QUICKSTART — the voices
  are plain synth, not the polished Salamander piano, but they prove the whole chain sounds with
  zero licensing burden.

#### Two-tier demo (honest expectations)

- **tier 0 — zero extra deps, just build the machine:** `prepare_all.py ... --skip-resourcepack`
  builds `dist/` with **no resourcepack**. Be honest about what you'll hear, and note it depends on
  whether the **RedPiano mod** is installed: **with the mod** (the normal case) the note blocks are
  **totally silent** — the mixin cancels the vanilla sound and asks for a `qzpno:` id that has no
  `.ogg` behind it without the pack; **without the mod** you get **vanilla note-block tones**. Either
  way it is **not** the sampled instruments, and it never "falls back to vanilla as a graceful
  degrade" once the mod is in. Use this only to confirm the datapack/machine builds.
- **tier 1 — open-source samples (recommended demo):** the `make_demo_samples.py` path above —
  `pip install -r requirements-demo.txt` then the three-step chain — gives you an actual **`qzpno_mv.zip`
  full of 103 synthesized voices**, so the mod finds every `qzpno:<id>` and the machine plays a real
  (if plain) timbre. This is the path that is **build-verified end-to-end** from a clean clone.

**Sample licensing — know what is bundled:**

| Instrument | Source in the original pack | License | You must |
|---|---|---|---|
| **drums** | VCSL / Karoryfer real samples (kick/snare/hihat/tom/crash) | **CC0** (public domain) | free to use; no attribution required |
| **piano** | Salamander Grand Piano (by Alexander Holm) | **CC-BY 3.0** | **credit the author** if you redistribute — see attribution box below |
| **bass / lead / pad** | numpy-synthesized (no external library) | your own synthesis output | regenerate or replace freely |

> Salamander's **CC-BY 3.0** license permits redistribution with attribution. The bundled pack now
> satisfies that requirement through its root `CREDITS.txt`. If you rebuild the pack, the builder
> writes the same canonical credit automatically. The fully synthetic demo pack contains no
> Salamander material.

> **Do not remove `CREDITS.txt`.** It names Alexander Holm, Salamander Grand Piano v3, CC BY 3.0,
> the license URL, the source URL, and the transformations used by McMusicMaker.

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
`pack.mcmeta` form. `prepare_all.py` derives every target version from bundled
`assets/qzpno_mv.zip` by rewriting only `pack.mcmeta` — no re-encoding needed.

The **mod jar** is the one surface that still needs a **recompile** for a version not already in the
manifest: run `scripts/mod_build.py` to print the verified toolchain (fabric-loom / fabric-loader /
fabric-api / Java / mappings) for a `--mc-version` (or `--write` to retarget the gradle build), build,
then `fetch_binaries.py --gen-manifest ../binaries` to register the result. Within 1.21.x the retarget
is number-only — no Java source edits. See [docs/MOD_ARCHITECTURE.md](docs/MOD_ARCHITECTURE.md) for the
porting checklist.

> The mixin binds to **internal NoteBlock bytecode**, so **every** target version still needs a
> **recompiled jar and one in-game listen** to confirm sound. Versions outside the auto band
> (≤ 1.20.6, or any version not in the table) are **hard-rejected** — the scripts **never guess**.
