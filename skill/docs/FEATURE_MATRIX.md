# FEATURE_MATRIX.md — Family A (RedPiano) capability source of truth

**Status:** AUTHORITATIVE. This file is the single source of truth for *what the skill
can actually do today*. When any other doc (DEVLOG.md, README.md, poc comments, the
designer) disagrees with this table about capabilities, **this file wins**. It is
grounded in the real code now on disk under `skill/scripts/` and in the user-verified
facts recorded below — not in aspirational handoff notes.

Scope: **Family A only** (RedPiano mod, real note blocks, `/tick rate 80`, resourcepack
`qzpno_mv` rp_format 64, datapack dp_format 81 for MC 1.21.8). Family B (audio slice) is
an external repo and out of scope — see the last row.

Date: 2026-06-26.

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
| **inplace-single** | no — every note forced to `pno` (3 velocity layers) | no (piano decays naturally; nothing to cut) | yes (`load_params`/`assert_supported`); `multi:false` selects this form | ✅ **yes** — user "完美" (《春娇与志明》, task4, oracle poc/45) | `skill/scripts/generators/inplace.py` (`multi=False`) | **production (v1)** |
| **inplace-multi** | **yes** — per-note GM family via `imap.family_for`/`imap.resolve` | **yes** — `plan_melody_cuts(absolute=False)`, relative `cutmel` schedule append | yes; **set `multi:true` in params JSON to select** | ✅ **yes** — user "特别好" (《七里香》 `qlxm`, oracle poc/46) | `skill/scripts/generators/inplace.py` (`multi=True`) | **production (v1)** |
| **swave** (marching-pulse mirror S-wave) | **yes** — per-note GM family; dual-track Z-mirror + greedy L/R balance | **yes** — `plan_melody_cuts(absolute=True)`, absolute `cutmel` schedule append at `(T0+OFFSET)*2 + d` | yes (`XRUN`/`ZMAX`/`base_block`/`dual_track_mirror`/`track_sep` consumed) | ⚠️ **generation-verified only** — capability tested by user (《七里香》 `qlxs`); awaiting final in-game listen to confirm melody-cut timing by ear | `skill/scripts/generators/swave.py` (oracle poc/48) | **production (v1), pending ear-confirm** |
| **straight** (long +X marching line) | **yes** | **yes** | yes (marching-family fields) | not separately listened (shares the swave pipeline) | `skill/scripts/generators/swave.py` (`form=straight`) | **production (v1)** — degenerate swave; biggest footprint |
| **custom** (drawn waypoint route) | **yes** | **yes** | yes (`waypoints` from the designer 自定义, + marching fields) | geometry-confirmed (collision + timeline self-checks pass; repeater facings N/S/E/W exercised); ear-confirm pending | `skill/scripts/generators/swave.py` (`form=custom`; `_layout_custom` lifted from verified poc/47) | **production (v1)** |
| _lab origin: poc/47_ | yes | no (lab build predates the cut) | argv-driven | its custom-path geometry was verified, then lifted into `swave.py` | `skill/scripts/generators/_experimental/47_build_custom.py` | **[superseded]** — `form=custom` is now v1 via `swave.py`; standalone copy kept for reference |
| **multilane** (one parallel lane per voice) | **yes** | **yes** (poc/49 absolute cut) | yes (`chord_mode=multilane`, `max_poly`, `lane_dz`, `lane_offsets`, `signal_tracks` dz; `+X` only) | geometry confirmed in-game (`olkml`); ear-confirm pending | `skill/scripts/generators/multilane.py` (`form=multilane`, promoted from poc/49) | **production (v1)** — **hard-fails over the forceload cap** (straight machine can't fold; long songs → use swave). Distinct parallel-lane topology |
| _lab origin: poc/49_ | yes | yes | argv-driven | verified `olkml` | `skill/scripts/generators/_experimental/49_build_multilane.py` | **[superseded]** — promoted into `generators/multilane.py` |
| **42 / 43** (single-piano S-wave, dual-track mirror) | no (single piano) | no | no (argv-driven lab scripts) | ✅ piano-only S-wave confirmed (`qzolks`/`wllsym`) | `skill/scripts/generators/_experimental/42_build_swave.py`, `43_build_swave_balance.py` | **[deprecated]** — superseded by `swave.py` (which adds multi-instrument + melody-cut over the *same* verified geometry) |
| **Family-B slice** (audio sample slicing) | n/a (replays sliced source audio, not re-performed notes) | n/a | n/a — `method=slice` is a **hard-fail** in `load_params` | (verified in its own repo) | external repo `mc-noteblock-demo` (NOT in this skill) | **[external / out of scope]** — runs `/tick rate 20`, no mod; v1 generators hard-fail on `method=slice` |

### How to select a form

- `--form {inplace,swave,straight,custom,multilane}` on `build_machine.py`.
  `swave`/`straight`/`custom` are ONE generator (`generators/swave.py`) differing only in path
  spine; **`custom` needs a `--params` JSON with `waypoints`** (drawn in the designer 自定义).
  **`multilane`** is `generators/multilane.py` (one lane per voice) and needs a `--params` JSON
  with `chord_mode=multilane`; it **hard-fails over the forceload cap** (long songs → swave).
- **inplace-single vs inplace-multi is chosen by the `multi` field in the params JSON**, not
  by a CLI flag. The v1 default is **multi-instrument**: with no params (or `multi:true`) the
  CLI builds **inplace-multi** (per-GM-family + melody-cut). Pass a params JSON containing
  `"multi": false` to get the **piano-only single** build. (`multi` is a validated schema
  field; `build_machine.py` passes the params dict straight through to `generators/inplace.py`.)

---

## Install prerequisites (Family A)

Family A re-performs notes on **real note blocks** read by the RedPiano mod, which routes
each note to a `/playsound` of a real instrument sample from the resource pack. All of the
following must be present in-game for a generated machine to make sound:

1. **RedPiano mod** installed (Fabric, MC 1.21.8). The mod is what turns a note-block press
   into the correct instrument sample and emits it centered on every player (so the sound
   doesn't cut when you move). Without the mod the machine builds but plays vanilla
   note-block timbres at best.
2. **Resource pack `qzpno_mv`** enabled, `pack_format` (rp) = **64** for MC 1.21.8. A wrong
   rp_format makes MC silently disable the pack → silence. (dp_format and rp_format are
   *different* number lines — dp = 81, rp = 64 for 1.21.8. See `CONTRACT.md` §3.)
3. **MC version 1.21.8** (the project anchor; `get_version_profile` drives dp_format / folder
   names). Other versions need a `VERSION_TABLE` row (CONTRACT §3.2).
4. **`/tick rate 80`** — the samples are tuned for 80 TPS. The generated machine self-sets
   this: pressing **[play]** fires a command block that runs `/tick rate 80` (both `inplace`
   and `swave`/marching forms). If you still hear an eerie/slow performance, set `/tick rate 80`
   manually. (Family B, by contrast, runs at the vanilla `/tick rate 20`.)
5. **`mido`** (Python) to parse MIDI on the build side — see `skill/requirements.txt`.
6. The machine **forceloads** the chunks it occupies so redstone pulses survive across
   unloaded chunks. inplace machines are tiny (~few chunks). swave can be large; the build
   hard-fails above the forceload soft cap (360 chunks) unless `--force-cap` is given.

Build, then deploy into a world (deploy is opt-in):

```
python skill/scripts/build_machine.py --midi song.mid --form inplace \
       --ns mysong --origin 0 0 255 --mc-version 1.21.8
# add --params designer.json  to drive geometry / multi:true
# add --world-dir <saves>/<world>/datapacks  to deploy (default: build only)
```

In-game: `/reload`, then `/function <ns>:setup` (forceload + build), wait for "built",
then press the **[播放]/[play]** sign-button.

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

5. **Unimplemented designer fields still hard-fail.** `start_dir != +X`,
   `chord_mode = multilane`, `line_width_radiate != 3`, 3D `signal_tracks`, plane-fold
   `fold_gap`, and `method = slice` are listed in `params_schema.UNIMPLEMENTED`;
   `assert_supported` raises a clear error at the top of a build rather than silently
   dropping the field. (`form = custom` is **no longer** here — it is a v1 form.)
   (CONTRACT §2.3, §2.4.)

6. **`_experimental/` is reference-only.** The scripts under
   `skill/scripts/generators/_experimental/` (42/43/47/49) are **not** wired into
   `build_machine.py` (47's custom geometry has been lifted into `swave.py`; 49/multilane
   remains experimental), are not verified end-to-end through the skill, and may consume the
   raw lab argv interface rather than the validated params dict. Use `inplace.py` /
   `swave.py` for v1.
