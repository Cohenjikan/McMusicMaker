# FEATURE_MATRIX.md — Family A (RedPiano) capability source of truth

**Status:** AUTHORITATIVE. This file is the single source of truth for *what the skill
can actually do today*. When any other doc (DEVLOG.md, README.md, poc comments, the
designer) disagrees with this table about capabilities, **this file wins**. It is
grounded in the real code now on disk under `scripts/` and in the user-verified
facts recorded below — not in aspirational handoff notes.

Scope: **Family A only** (RedPiano mod, real note blocks, `/tick rate 80`, resourcepack
`qzpno_mv`, datapack — formats are version-relative; rp_format 64 / dp_format 81 is the
**1.21.8** row). The skill is now **version-adaptive** across a supported auto band
(1.21..1.21.10); 1.21.8 is the verified default/anchor — see [Version adaptiveness](#version-adaptiveness)
below. Family B (audio slice) is an external repo and out of scope — see the last row.

Date: 2026-06-26 (swave/inplace in-game-verified status corrected 2026-07-08 — see the
capability matrix: `swave` has since been tested in-game multiple times and confirmed working;
`inplace` remains functionally complete but tested in-game fewer times).

---

## Capability matrix

Columns:
- **multi-instr?** — does the form map per-note GM families (pno/bass/lead/pad/drum) via
  `InstrumentMap`, or is every note forced to a single instrument?
- **melody-cut?** — does it schedule the event-level `stopsound` melody-sustain cut
  (`redpiano_core.plan_melody_cuts`) so sustaining pad/lead/bass tails don't bury the
  melody?
- **designer params?** — does it consume the validated designer JSON via
  `params_schema.load_params` + `assert_supported`?
- **in-game verified?** — has a real performance been confirmed by ear in Minecraft?
- **canonical script** — the one file you run/import today.
- **status** — production / experimental / deprecated / external.

| form | multi-instr? | melody-cut? | designer params? | in-game verified? | canonical script | status |
|---|---|---|---|---|---|---|
| **inplace-single** | no — every note forced to `pno` (3 velocity layers) | no (piano decays naturally; nothing to cut) | yes (`load_params`/`assert_supported`); `multi:false` selects this form | ✅ **yes** — user "完美" (《春娇与志明》, task4, oracle poc/45); functionally complete but tested in-game fewer times than `swave` | `scripts/generators/inplace.py` (`multi=False`) | **production (v1)** |
| **inplace-multi** | **yes** — per-note GM family via `imap.family_for`/`imap.resolve` | **yes** — `plan_melody_cuts(absolute=False)`, relative `cutmel` schedule append | yes; **set `multi:true` in params JSON to select** | ✅ **yes** — user "特别好" (《七里香》 `qlxm`, oracle poc/46); functionally complete but tested in-game fewer times than `swave` | `scripts/generators/inplace.py` (`multi=True`) | **production (v1)** |
| **swave** (marching-pulse mirror S-wave) | **yes** — per-note GM family; dual-track Z-mirror + greedy L/R balance | **yes** — `plan_melody_cuts(absolute=True)`, absolute `cutmel` schedule append at `(T0+OFFSET)*2 + d` | yes (`XRUN`/`ZMAX`/`base_block`/`dual_track_mirror`/`track_sep` consumed) | ✅ **yes — tested in-game multiple times and confirmed working** (《七里香》 `qlxs`, melody-cut timing confirmed by ear across repeated sessions) | `scripts/generators/swave.py` (oracle poc/48) | **production (v1)** |
| **straight** (long +X marching line) | **yes** | **yes** | yes (marching-family fields) | not separately listened (shares the swave pipeline) | `scripts/generators/swave.py` (`form=straight`) | **production (v1)** — degenerate swave; biggest footprint |
| **custom** (drawn waypoint route) | **yes** | **yes** | yes (`waypoints` from the designer 自定义, + marching fields) | **partially verified** — collision + timeline self-checks pass and repeater facings N/S/E/W are exercised, but the specific case of a **turn cell coinciding with a wide-side (radiate) chord** has not been verified: the `chord3` side blocks fan out perpendicular to the pulse direction, and at a turn the direction changes, so a dense chord landing exactly on a bend could in principle collide (rare, but possible — the `Grid.put` guard will catch it as a hard error rather than build silently). Ear-confirm also pending. | `scripts/generators/swave.py` (`form=custom`; `_layout_custom` lifted from verified poc/47) | **production (v1)** |
| _lab origin: poc/47_ | yes | no (lab build predates the cut) | argv-driven | its custom-path geometry was verified, then lifted into `swave.py` | `scripts/generators/_experimental/47_build_custom.py` | **[superseded]** — `form=custom` is now v1 via `swave.py`; standalone copy kept for reference |
| **multilane** (one parallel lane per voice) | **yes** | **yes** (poc/49 absolute cut) | yes (`chord_mode=multilane`, `max_poly`, `lane_dz`, `lane_offsets`, `signal_tracks` full 3D {dx,dy,dz}; all 4 cardinals) | geometry confirmed in-game (`olkml`); ear-confirm pending | `scripts/generators/multilane.py` (`form=multilane`, promoted from poc/49) | **production (v1)** — **soft footprint cap**: over it pass `--force-cap` to build anyway (a straight machine can't plane-fold, but it is **not** a guaranteed audio drop — tested fine at ~428 chunks; use swave for a smaller footprint). Distinct parallel-lane topology |
| _lab origin: poc/49_ | yes | yes | argv-driven | verified `olkml` | `scripts/generators/_experimental/49_build_multilane.py` | **[superseded]** — promoted into `generators/multilane.py` |
| **42 / 43** (single-piano S-wave, dual-track mirror) | no (single piano) | no | no (argv-driven lab scripts) | ✅ piano-only S-wave confirmed (`qzolks`/`wllsym`) | `scripts/generators/_experimental/42_build_swave.py`, `43_build_swave_balance.py` | **[deprecated]** — superseded by `swave.py` (which adds multi-instrument + melody-cut over the *same* verified geometry) |
| **Family-B slice** (audio sample slicing) | n/a (replays sliced source audio, not re-performed notes) | n/a | n/a — `method=slice` is a **hard-fail** in `load_params` | (verified in its own repo) | external repo `mc-noteblock-demo` (NOT in this skill) | **[external / out of scope]** — runs `/tick rate 20`, no mod; v1 generators hard-fail on `method=slice` |

### How to select a form

- `--form {inplace,swave,straight,custom,multilane}` on `build_machine.py`.
  `swave`/`straight`/`custom` are ONE generator (`generators/swave.py`) differing only in path
  spine; **`custom` needs a `--params` JSON with `waypoints`** (drawn in the designer 自定义).
  **`multilane`** is `generators/multilane.py` (one lane per voice) and needs a `--params` JSON
  with `chord_mode=multilane`; the forceload cap is a **soft** cap — over it pass `--force-cap`
  to build anyway (not a guaranteed audio drop; tested fine at ~428 chunks; use swave for a
  smaller footprint).
- **inplace-single vs inplace-multi is chosen by the `multi` field in the params JSON**, not
  by a CLI flag. The v1 default is **multi-instrument**: with no params (or `multi:true`) the
  CLI builds **inplace-multi** (per-GM-family + melody-cut). Pass a params JSON containing
  `"multi": false` to get the **piano-only single** build. (`multi` is a validated schema
  field; `build_machine.py` passes the params dict straight through to `generators/inplace.py`.)

---

## Version adaptiveness

The form matrix above is version-independent. **Which MC version a machine targets** is now
driven by one flag — `--mc-version` — which self-syncs the whole coherent output: **datapack +
resourcepack + mod-build config** all read from a single `VERSION_TABLE` in
`scripts/redpiano_core.py` (`get_version_profile` is the only accessor; nothing else hardcodes
a format number). See `CONTRACT.md` §3 and `MOD_ARCHITECTURE.md` §6.4.

> **This tier table is the AUTOMATION (fast-path) range, not the skill's whole reach.** A ⛔
> row means the *automated build* refuses — it is **not** the skill giving up on the version.
> Anything outside the green auto band is handed to the craftsman path in
> [`docs/VERSION_TACTICS.md`](VERSION_TACTICS.md), which builds a working machine per-delivery
> (or downgrades / bows out honestly). Auto-refusal ≠ skill-refusal throughout.

| version band | tier | what works |
|---|---|---|
| **1.21 .. 1.21.10** (1.21, .1, .2, .3, .4, .5, .6, .7, .8, .9) | 🟢 green | full auto: datapack + resourcepack + mod-build config self-sync from `--mc-version`. **1.21.8 = verified default & anchor** (user-tested in-game). |
| **1.20.3 .. 1.20.6** | 🟡 yellow | datapack/resourcepack adapt automatically, **but the RedPiano mod needs a real Java source-port** (the pre-1.21 scoreboard config API, + Java 17 at 1.20.4) — **out of auto scope**. `assert_build_supported()` refuses the mod-touching builds (`build_machine` / `build_particles` / `build_resourcepack`). |
| **≤ 1.20.2** | ⛔ auto-refused | **automated build hard-refuses** — no `/tick rate` (added 1.20.3) and no `return`; the tick80 timing model (80 TPS, samples tuned for it, repeater geometry baked at 0.025 s/cell) cannot work on the auto path → 4×-too-slow, unfixable *by automation*. **1.20.3 is the hard floor for the fast path.** **Auto-build refusal ≠ skill refusal** — the version is not a dead end: switch to the craftsman path in [`docs/VERSION_TACTICS.md`](VERSION_TACTICS.md) (Carpet `/tick rate 80`, tick20 downgrade, or vanilla-timbre mode). |
| unknown version | ⛔ auto-refused | automated build still **hard-fails** ("never guess", CONTRACT §1.9). **Auto-build refusal ≠ skill refusal** — hand it to the craftsman path in [`docs/VERSION_TACTICS.md`](VERSION_TACTICS.md) (its §4 five-question self-check locates the tactics for any unknown version). |

Per-version facts auto-derive from `VERSION_TABLE` (the **1.21.8** anchor row is dp 81 / rp 64):

- **datapack pack_format:** 1.21/.1 = 48, .2/.3 = 57, .4 = 61, .5 = 71, .6 = 80, .7/.8 = 81, .9 = 88.
- **resourcepack rp_format:** 1.21/.1 = 34, .2/.3 = 42, .4 = 46, .5 = 55, .6 = 63, .7/.8 = 64, .9 = 69.
- **function folder:** singular `function/` for all of 1.21.x (plural `functions/` only ≤ 1.20.6).
- **pack.mcmeta shape:** single `{"pack":{"pack_format":N,…}}` for ≤ 1.21.8; **min/max**
  `{"pack":{"min_format":N,"max_format":N,…}}` for ≥ 1.21.9 (25w31a) — dp 88 / rp 69 at 1.21.9.
  This is how **1.21.9 is supported** (no longer a hard-fail).
- **sign NBT dialect:** JSON-string entries `messages:['{"text":"hi"}']` for 1.20..1.21.4
  (`component_string`); **SNBT compound entries** `messages:[{"text":"hi"}]` for ≥ 1.21.5
  (`component_snbt`). The dialect now **flips at 1.21.5** — fixing a latent bug where on 1.21.5+
  (including the default 1.21.8) the old quoted form rendered as **literal text** on console signs.

New helper scripts (both ship a `--selftest`):

- `scripts/build_resourcepack.py` — version-driven `qzpno_mv` repack in the skill (reads
  rp_format + pack.mcmeta shape from the table). Flags: `--mc-version --samples-root --out`.
  Samples ship separately — see `BINARIES.md`.
- `scripts/mod_build.py` — prints (or `--write` applies) the **verified** mod toolchain per
  version (fabric-loom / fabric-loader / fabric-api / Java / Mojang mappings) + a porting-tier
  note. It does **not** run gradle and does **not** widen `fabric.mod.json`'s tested `minecraft`
  range unless you pass `--set-mc-range`. The mod build is parameterized: `mod/redpiano/build.gradle`
  reads `minecraft_version`/`loader_version`/`fabric_version`/`java_version` from
  `gradle.properties` (default = the 1.21.8 anchor, so an unedited build is byte-identical and
  still produces `redpiano-1.0.0.jar`, ~11.6 KB).

**Mod honesty (unchanged):** the mixin binds to internal `NoteBlock` bytecode, so **every**
target version still needs a recompiled jar **and one in-game listen**. Within 1.21.x the
retarget is number-only (no Java source edits); 1.21.9 is number-only too but verify the yarn
`getWorld`→`getEntityWorld` rename equivalent under Mojang mappings in `genSources`. Below 1.21
is a real Java source-port (scoreboard API); below ~1.19 an audio-API port; below 1.20.3 is
impossible. See `MOD_ARCHITECTURE.md` §6.4.

---

## Install prerequisites (Family A)

Family A re-performs notes on **real note blocks** read by the RedPiano mod, which routes
each note to a `/playsound` of a real instrument sample from the resource pack. All of the
following must be present in-game for a generated machine to make sound:

1. **RedPiano mod** installed (Fabric; built for your MC version — 1.21.8 is the verified
   anchor jar). The mod is what turns a note-block press into the correct instrument sample
   and emits it centered on every player (so the sound doesn't cut when you move). Without the
   mod the machine builds but plays vanilla note-block timbres at best. **The mixin binds to
   internal `NoteBlock` bytecode, so every target version needs a recompiled jar AND one
   in-game listen** — within 1.21.x the retarget is number-only (`mod_build.py`); below 1.21
   is a real Java source-port. See [Version adaptiveness](#version-adaptiveness).
2. **Resource pack `qzpno_mv`** enabled with the rp_format matching your MC version. A wrong
   rp_format makes MC silently disable the pack → silence. (dp_format and rp_format are
   *different* number lines — on **1.21.8** that is dp = 81, rp = 64; both auto-derive from
   `VERSION_TABLE`. See `CONTRACT.md` §3 and [Version adaptiveness](#version-adaptiveness).)
   `prepare_all.py --skip-resourcepack` builds without staging this pack; the honest result is
   **vanilla note-block timbres or total silence**, not RedPiano's sampled sound — only use it
   when a matching `qzpno_mv.zip` is already installed and enabled.
3. **An MC version in the supported auto band (1.21..1.21.10)**, selected via `--mc-version`;
   **1.21.8** is the verified default/anchor. `get_version_profile` drives dp_format / rp_format
   / folder names / pack.mcmeta shape from `VERSION_TABLE` (the single source of truth). Unknown
   versions still **hard-fail** ("never guess"). See [Version adaptiveness](#version-adaptiveness)
   and CONTRACT §3.2.
4. **`/tick rate 80`** — the samples are tuned for 80 TPS. **The PLAYER must type
   `/tick rate 80` manually before playing; the machine does NOT set it** (the earlier
   auto-set command block was removed — it didn't work reliably in practice). Without it,
   playback runs ~4× too slow (eerie/slow). (Family B, by contrast, runs at the vanilla
   `/tick rate 20`.)
5. **`mido`** (Python) to parse MIDI on the build side — see `requirements.txt`.
6. The machine **forceloads** the chunks it occupies so redstone pulses survive across
   unloaded chunks. inplace machines are tiny (~few chunks). swave/multilane can be large;
   the forceload cap is a **soft** cap (360 chunks) — over it the build refuses unless
   `--force-cap` is given, in which case it WARNs and builds anyway (not a guaranteed audio
   drop — tested fine at ~428 chunks).

Build, then deploy into a world (deploy is opt-in):

```
python scripts/build_machine.py --midi song.mid --form inplace \
       --ns mysong --origin 0 0 255 --mc-version 1.21.8
# add --params designer.json  to drive geometry / multi:true
# add --world-dir <saves>/<world>/datapacks  to deploy (default: build only)
```

In-game: `/reload`, then `/function <ns>:setup` (forceload + build), wait for "built",
type `/tick rate 80` manually (the machine does NOT set it), then press the
**[播放]/[play]** sign-button.

**Cam-follow (§E, swave/straight/custom/multilane, not inplace):** the console's
**[跟拍]** button mounts the player on an invisible armor-stand camera; after **[play]**
the stand is tp'd **every game tick** along the track midline, phase-locked to the pulse
front via the same `arr[]`/ELAPSED time base the kill plan uses (variable speed by design —
repeater delays are 1..4). Client vehicle interpolation makes riding smooth; free mouse-look
is preserved; replays snap the camera back to the start. Exit via **[stop]** or
`/function <ns>:camoff`. Emitted as `cam`, `camoff`, `cam/step` (two-level ELAPSED ladder,
~130 evals/tick) + `cam/c<n>` buckets; ~2 lines per 8 gt window. Camera anchor is tunable via designer/params
`cam_height` / `cam_back` / `cam_dz` (author frame; defaults 10/6/0 = auto track-band midline).

---

## Known constraints

These are real limitations of the v1 implementation, not bugs. They are the reason the
table marks some cells "no" and some "experimental".

1. **No velocity dynamics on non-piano instruments (single layer).** Only `pno` has 3
   velocity layers (`p`/`mf`/`f`). `bass`, `lead`, `pad`, and `drum` have a **single layer**
   (forced to `mf` / the first available layer), so velocity changes on those instruments
   produce no loudness/timbre change. (CONTRACT §0, §1.5.)

2. **Melody-cut is EVENT-level, not per-note.** The cut is `stopsound @a record <event>`,
   which silences *every* currently-ringing note that shares that sample event. This is the
   **safe case only for single-voice melodies**: when two or more notes of the *same*
   instrument event overlap (dense polyphonic pad/lead lines), cutting one cuts them all, so
   an earlier note can be silenced prematurely. `plan_melody_cuts` **WARNs** when it detects
   overlapping same-event notes. A true per-note cut is out of v1 scope. (CONTRACT §1.6;
   `redpiano_core.plan_melody_cuts`.) Pure-piano / pure-drum songs degrade gracefully to "no
   cuts" (nothing to cut).

3. **Polyphony caps and pitch range.** Per-cell polyphony is capped (inplace 12 voices,
   swave 6 voices / 3 per track); excess notes (lowest pitch first) are **dropped** and
   counted in the report. Notes outside a sample's playable band are **octave-shifted**
   (±12, pitch class preserved) to fit and counted; only if no octave fits is the pitch
   clamped as a last resort (reported, never silent). (CONTRACT §0, §1.5.)

4. **Tick rate differs by family.** Family A runs `/tick rate 80` (samples tuned for it);
   Family B (external slice repo) runs the vanilla `/tick rate 20`. Do not mix.

5. **Unimplemented designer fields still hard-fail (on the forms that don't use them).**
   `line_width_radiate != 3`, plane-fold `fold_gap`, and `method = slice` are listed in
   `params_schema.UNIMPLEMENTED`; `assert_supported` raises a clear error at the top of a
   build rather than silently dropping the field. **`start_dir` is now fully supported** — all
   4 cardinals (`+X`/`-X`/`+Z`/`-Z`) via emit-time rotation (`+X` = identity; non-`+X`
   generation-verified, in-game listen pending). **`signal_tracks` now consumes the full 3D
   offset {dx,dy,dz}** (multilane). **`chord_mode = multilane` and `max_poly`/`lane_dz`/
   `lane_offsets` are NOT globally unimplemented** — they hard-fail only on the marching forms
   (swave/straight/custom); `--form multilane` is a v1 form that consumes them. `form = custom`
   is likewise a v1 form, not unimplemented. (CONTRACT §2.3.)

6. **`_experimental/` is reference-only.** The scripts under
   `scripts/generators/_experimental/` (42/43/47/49) are **not** wired into
   `build_machine.py` (47's custom geometry has been lifted into `swave.py`; 49/multilane
   remains experimental), are not verified end-to-end through the skill, and may consume the
   raw lab argv interface rather than the validated params dict. Use `inplace.py` /
   `swave.py` for v1.

7. **Practical song-length ceilings (empirical, footprint-driven).** These are *rough
   guidance*, not hard limits — the actual gate is the forceload soft cap (360 chunks,
   `--force-cap` to override) and in-world server load, both of which scale with the machine's
   footprint, which scales with song length. As a working rule of thumb:
   - **swave** (folded mirror S-wave): comfortable up to **≲ 6 min** — the plane-fold keeps the
     footprint compact, so it takes the longest songs of any marching form.
   - **multilane** (one straight lane per voice): comfortable up to **≲ 4 min** — it is a
     straight machine that **cannot** plane-fold, so its footprint grows faster in X; longer
     songs push past the soft cap (tested fine at ~428 chunks with `--force-cap`, but that is
     the ceiling, not a target). Use swave for a smaller footprint on long songs.
   - **inplace** (in-place palette): **essentially length-independent** — the palette is a
     fixed grid of distinct note blocks re-triggered in place, so a longer song adds schedule
     entries, not blocks. Footprint stays ~constant (a few chunks) regardless of duration.
   `straight` shares the swave pipeline but has the biggest footprint (no fold) so it hits the
   cap soonest; `custom` depends entirely on the drawn route length. All of these are
   dominated by simultaneous-note density (polyphony drops) and forceload chunks — the build
   report prints both, and the forceload guard hard-fails past the soft cap unless `--force-cap`.
