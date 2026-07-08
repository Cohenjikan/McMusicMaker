# CONTRACT.md — Family A (RedPiano) skill build contract

**Status:** authoritative interface spec written by the FOUNDATION ARCHITECT (WF-1).
WF-2 (implementer) MUST build `scripts/*` against this document. The proven lab
generators (`poc/45`, `poc/46`, `poc/48`) are the *behavioral oracle*: every function
below is distilled from verified code in those files. Where this contract and a poc
disagree, the poc wins for **geometry/timing**, this contract wins for **API shape**.

Scope: **Family A only** — RedPiano mod, real note blocks, `/tick rate 80`, resourcepack
`qzpno_mv`, datapack + resourcepack + mod-build config all self-synced from one `--mc-version`.
**Supported auto band = 1.21..1.21.10** (tier "green"); **MC 1.21.8 = the verified default & anchor**
(dp_format 81, rp_format 64 — those are the 1.21.8 row). Family B (audio slice,
`method=slice`) is an external repo and is **out of scope** — generators MUST hard-fail on it.

The skill tree this contract governs:

```
scripts/
  build_machine.py          # CLI entry (§4)
  build_resourcepack.py     # version-driven qzpno_mv repack (§5)
  mod_build.py              # per-version mod toolchain printer/writer (§5)
  prepare_all.py            # one-command orchestrator: datapack+resourcepack+mod-config (§5)
  redpiano_core.py          # shared plumbing (§1)  — NO geometry here
  params_schema.py          # schema + validation (§2)
  generators/
    inplace.py              # consumes poc/45+46 geometry (multi/single palette)
    swave.py                # swave / straight / custom — poc/48 geometry + path spines
    multilane.py            # one parallel lane per voice (poc/49)
    _experimental/          # reference-only lab scripts (42/43/47/49)
assets/redpiano_map_multi.json   # 103-block map, single source of truth
```

---

## 0. Shared vocabulary & invariants (verified in poc)

| Term | Definition (verified source) |
|---|---|
| `U` | seconds per quantization cell = `2 / TPS` = `2/80 = 0.025s` (poc/45 L39, poc/46 L36, poc/48 L122). Note quantized to cell `round(t/U)`. |
| game-tick conversion | at `/tick rate 80`, **1 redstone-tick cell = 2 game-ticks**. `dt_gameticks = redstone_tick_delta * 2` (poc/45 L149, poc/48 L209). |
| `TPS` | 80 (RedPiano runs at `/tick rate 80`; samples are tuned for it). |
| `VOICES` | per-cell polyphony cap. in-place=12 (poc/45 L37), swave=6 (poc/48 L54). Excess notes (lowest pitch first) are **dropped** and counted. |
| velocity layer | `p` if `vel<0.40`, `mf` if `<0.72`, else `f` (poc/45 L71). Only `pno` has 3 layers; bass/lead/pad have only `mf`. |
| SIDE-trigger | redstone block placed on the note block's **side face** (same Y, z-1), never below. Bottom-trigger across the mapping block is INVALID (MEMORY: noteblock-trigger-side-not-bottom). |
| repeat-trigger | `setblock redstone_block` (air→redstone = rising edge = sound) then schedule `offall` +1t clears it to air; next press needs ≥2 game-ticks gap. |
| melody-cut | `stopsound @a record <event>` at note release, to kill sustaining pad/lead/bass tails that bury the melody. EVENT-level (not per-note). |
| `CUT_INSTR` | `{'pad','lead','bass'}` — sustaining non-piano instruments that get cut. piano (natural decay) and drum (short transient) are NOT cut (poc/46 L27, poc/48 L57). |
| `commandModificationBlockLimit` | gamerule set to `2147483647` before any mass setblock (every poc does this). |
| build batching | setblock commands chunked into `BATCH=2000` per `bld/bN` function, driven by a `BLD` scoreboard counter across ticks (all pocs). |

---

## 1. `redpiano_core.py` API

**Rule: only shared plumbing lives here. NO form-specific geometry** (no S-wave path, no
palette grid, no chord3 radiate — those live in `generators/`). Core is pure: it takes
data and produces strings/files, it never decides machine *shape*.

All functions raise `RedPianoError` (a module-level `class RedPianoError(Exception)`) on
contract violations, never silently degrade.

### 1.1 Datapack writer + lifecycle

```python
class Datapack:
    def __init__(self, ns: str, name: str, out_dir: str, mc_version: str): ...
```
- Resolves a `VersionProfile` via `get_version_profile(mc_version)` (§1.9) at construction;
  stores `dp_format` and `function_folder` from it.
- `out_dir/<ns>/` is the datapack root. If it exists it is **removed and recreated**
  (matches poc `shutil.rmtree` then `os.makedirs`).

```python
    def write(self, rel_path: str, content: str) -> None
```
- Writes `content` to `<root>/<rel_path>`, creating parent dirs. Forces `\n` line endings
  and a trailing newline (poc `w()` semantics, poc/45 L131).

```python
    def write_function(self, name: str, body: str | list[str]) -> None
```
- Writes `data/<ns>/<function_folder>/<name>.mcfunction`. `body` list is `'\n'.join`ed.
- **`function_folder` MUST come from the version profile** — `function` (singular) for
  1.21+, `functions` (plural) for pre-1.21. This is the ONLY place the rename is honored;
  poc hardcodes singular `function/` (poc/45 L134) — core MUST parameterize it.

```python
    def write_pack_mcmeta(self, description: str) -> None
```
- Writes `pack.mcmeta`, `indent=2` (poc/45 L135). `dp_format` from the version profile,
  **never hardcoded 81**. The JSON SHAPE branches on `profile.packmeta_shape`:
  - `"single"` (≤1.21.8) → `{"pack": {"pack_format": self.dp_format, "description": description}}`.
  - `"minmax"` (≥1.21.9, 25w31a) → `{"pack": {"min_format": self.dp_format, "max_format": self.dp_format, "description": description}}`.
    Emitting a single `pack_format` on ≥1.21.9 would make MC silently disable the pack (= total silence),
    so the min/max shape is mandatory there.

```python
    def write_load_tick_tags(self) -> None
```
- Writes `data/minecraft/tags/<function_folder>/load.json` and `.../tick.json`, each
  `{"values": ["<ns>:load"]}` / `["<ns>:tick"]` (poc/45 L137-138).
- Tag folder is `tags/function/` (1.21+) or `tags/functions/` (pre-1.21) — same profile-driven
  rename. **This is a known historical footgun; the profile must drive it.**

```python
    def deploy(self, world_datapacks_dir: str) -> str
```
- Copies the built tree into `<world_datapacks_dir>/<ns>` (rmtree+copytree, poc/45 L212-214).
  Returns the destination path. Only called when `--world-dir` is given (deploy is opt-in; §4).

**Init/setup/cleanup scaffolding** — core provides *builders* that return command lists;
generators assemble them with form-specific block lists. Core MUST NOT invent machine
geometry, so these take the geometry-dependent pieces as arguments:

```python
def scoreboard_reset(ns: str) -> list[str]
    # ['scoreboard players set PLAY <ns> 0', 'scoreboard players set LOOP <ns> 0']  (poc/45 L170)
def build_load_fn(ns, name, extra_objectives=True) -> list[str]
    # objectives add, BLD=-1, RESET, rpcfg poly/human=1, scoped forceload remove <bbox>, schedule clear done, tellraw  (poc/45 L171-174)
def build_tick_dispatch(ns, n_batches) -> list[str]
    # the BLD-counter build driver (poc/45 L177-180)
def batch_setblocks(setblock_lines: list[str], batch=2000) -> list[list[str]]
    # split into bld/bN chunks
```
Behavior MUST byte-match the poc command sequences (these are user-verified). WF-2 may
refactor naming but a generated datapack from core+inplace MUST be functionally identical
to poc/46's output for the same MIDI.

### 1.2 `put()` — collision-guarded grid writer

```python
class Grid:
    def __init__(self): self.occ: dict[tuple[int,int,int], str] = {}
    def put(self, out: list[str], x: int, y: int, z: int, block: str) -> None
```
- Records `(x,y,z) -> block` in `self.occ` and appends `setblock {x} {y} {z} {block}` to `out`.
- **Collision guard (verified poc/45 L106-109, poc/48 L287-292):** if `(x,y,z)` already
  holds a *different* block AND neither old nor new is `air`/`minecraft:air`, raise
  `RedPianoError(f"collision @{(x,y,z)}: {old} vs {block}")`.
- **air may overwrite air, and air may NOT clobber a non-air block, and a non-air block may
  NOT clobber a different non-air block.** air-vs-nonair in either direction is allowed
  (the poc treats `'air' in (old,new)` as a pass — preserve that exact rule). The prompt's
  "forbid air overwriting non-air" is realized as: the *guard only fires* for two distinct
  non-air blocks; air operations never raise. WF-2: keep the poc's permissive air rule —
  it is load-bearing (overlapping `air` carve-outs around note blocks rely on it).
- Records timing only in the sense of insertion order in `out` (the command stream order IS
  the build order). No wall-clock timing.
- `bbox()` helper returns `(min_x,min_z,max_x,max_z)` over `occ` for forceload sizing.

### 1.3 Sign / button helpers — **exactly-4-line ASSERTION**

```python
def sign_messages(lines: list[str], sign_dialect: str) -> str
```
- Minecraft signs have exactly 4 lines. Core MUST **assert** `0 < len(lines) <= 4` and pad
  to 4 with empty strings, producing the entries inside `oak_sign{front_text:{messages:[...]}}`
  (poc/45 L157). If `len(lines) > 4` → `RedPianoError("sign needs <=4 lines, got N")`. (poc
  silently truncates with `[:4]`; the contract UPGRADES this to a hard assert so over-long
  labels are caught at generation time.)
- The entry SHAPE branches on `sign_dialect` (from the version profile):
  - `"component_string"` (1.20..1.21.4) → JSON-string entries, `messages:['{"text":"hi"}', ...]`.
  - `"component_snbt"` (≥1.21.5) → SNBT compound entries, `messages:[{"text":"hi"}, ...]`.
  - On 1.21.5+ (including the default 1.21.8) the old quoted form renders as LITERAL text on
    console signs — this was a latent bug; the dialect flip at 1.21.5 fixes it.

```python
def labeled_button(bx, y, oz, cmd: str, lines: list[str], sign_dialect: str, lamp="minecraft:redstone_lamp") -> list[str]
```
- Emits the 5-block console widget verbatim from poc/45 `lbtn` (L156-162): lamp at `Y-1,oz`,
  command_block `[facing=up]{Command:"<cmd>",auto:0b}` at `Y,oz`, stone_button `[face=floor]`
  at `Y+1,oz`, lamp at `Y-1,oz-2`, oak_sign at `Y,oz-2` with `sign_messages(lines, sign_dialect)`.

### 1.4 Forceload helpers — per-path add + over-threshold guard

```python
FORCELOAD_SOFT_CAP = 360   # chunks; above this MC perf/limits degrade

def forceload_add_region(x0, z0, x1, z1) -> str
    # single 'forceload add x0 z0 x1 z1'
def forceload_split(x0, z0, x1, z1, max_chunks_per_cmd=...) -> list[str]
    # poc/48 L383-388: walk X in xstep*16 strides so each 'forceload add' stays small,
    # because one forceload command is itself chunk-limited. Returns ['forceload remove <bbox>', add...]
    # (a SCOPED remove of just this machine's region — never 'remove all').
def forceload_guard(x0, z0, x1, z1, *, auto_fold=False) -> list[str]
```
- Computes `chunks = ((x1//16)-(x0//16)+1) * ((z1//16)-(z0//16)+1)` (poc/48 L559 fold_chunks formula).
- If `chunks > FORCELOAD_SOFT_CAP`:
  - `auto_fold=False` (default) → **HARD FAIL**: `RedPianoError(f"forceload {chunks} chunks > {FORCELOAD_SOFT_CAP}; machine too large — fold the layout or raise --force-cap")`.
  - `auto_fold=True` → emit a WARN (return value carries it / `logging.warning`) and proceed with
    `forceload_split(...)` so the region is added in safe strides. Folding the *geometry*
    (plane-fold U-turns) is a generator concern; core only splits the forceload command itself.
- in-place machines are tiny (~few chunks, poc/45) so they pass trivially; swave can be large.

### 1.5 Multi-instrument map loader + note resolver

```python
class InstrumentMap:
    @classmethod
    def load(cls, path="assets/redpiano_map_multi.json") -> "InstrumentMap"
```
- Loads the JSON (structure verified in poc/redpiano_map_multi.json): `instruments` (pno/bass/
  lead/pad/drum), `family_map` (GM program//8 → instr), `gm_drum_map` (GM note → drum type).
  Keys in family_map/gm_drum_map are strings → cast to int on load (poc/46 L42-43).
- `total_blocks()` MUST equal **103** (assert; gen_multi_map.py L83-84). Raise if not.

```python
    def family_for(self, program: int, channel: int) -> str
        # channel==9 -> 'drum'; else family_map.get(program//8, 'pno')  (poc/46 L74)

    def resolve(self, midi: int, vel01: float, instr: str) -> Resolved
```
Returns `Resolved(block: str, note_value: int, sound_event: str, shifted_octaves: int)`.
Logic verified in poc/46 `map_note_multi` L47-60 / poc/48 L81-98, **with one upgrade**:

- **Drums** (`pitched=False`): `dtype = gm_drum_map.get(midi, 'snare')`, fall back to first
  available type; returns `(types[dtype], 12, sound['drum:'+dtype], 0)`. `note_value=12` →
  pitch 1.0, no transpose.
- **Pitched**: pick nearest band `band = min(bands, key=|b-midi|)`, `raw = 12 + (midi-band)`,
  `note_value = clamp(raw, 0, 24)`.
  - **OCTAVE-SHIFT upgrade (prompt requirement, replaces poc's silent clamp):** if
    `raw < 0` or `raw > 24`, the note is outside the sample's playable range. Instead of
    clamping pitch (poc just does `max(0,min(24,raw))` and counts it as `clamped`), core MUST
    **shift `midi` by whole octaves (±12) toward the band's range until `0 <= raw <= 24`**,
    preserving pitch class, then recompute. Record `shifted_octaves` (signed count) and the
    resolver MUST surface a per-call report so the generator can WARN
    `"N notes octave-shifted to fit sample range"`. If even after shifting it cannot fit
    (band table genuinely too narrow), clamp as last resort and mark `shifted_octaves` with a
    sentinel + WARN. **No silent pitch corruption.**
  - velocity layer: `pno` → p/mf/f by velocity; others forced to `mf` (or first available
    layer). `key = f"{band}_{layer}"`; returns `(block[key], note_value, sound[key], shifted)`.

### 1.6 Melody-cut scheduler helper

```python
def plan_melody_cuts(
    mel_events: list[MelEvent],   # each: (cell_tick, midi_dur_s, sound_event)
    *, tps=80, melcap_s=1.2, min_cut_gt=4, offset=0, absolute=False
) -> MelodyCutPlan
```
Distilled from poc/46 L109-122 and poc/48 L198-210. For each melody cell, compute the cut
delay in game-ticks:
```
d = min(round(midi_dur_s * tps), round(melcap_s * tps))         # cap the sustain
d = min(d, (next_mel_tick - this_tick) * 2 - 1)  if next exists  # don't overrun next melody note
d = max(min_cut_gt, d)
```
- **Generation-time ASSERTION (prompt requirement):** after computing `d`, assert
  `d < (next_mel_tick - this_tick) * 2` — i.e. the cut floor (`min_cut_gt`) can never push
  the cut *past* the next note's onset. If `min_cut_gt >= gap_to_next`, raise
  `RedPianoError(f"cut_delay floor {min_cut_gt}gt >= gap {gap}gt to next melody note @cell {tick}; notes too dense to cut safely")`. (poc relies on the `-1` and `max()` ordering but never asserts; contract makes it explicit.)
- `absolute=True` (swave): also returns per-cell absolute schedule time
  `(tick + offset) * 2 + d` for `schedule function <ns>:cutmel <t>t append` (poc/48 L209).
  `absolute=False` (in-place): returns relative `d` for `schedule ... cutmel <d>t append` (poc/46 L173).
- **Polyphony WARN (prompt requirement):** the cut is EVENT-level (`stopsound @a record <event>`
  kills ALL currently-ringing notes that share that sample event). `plan_melody_cuts` MUST
  detect, per cut, whether **more than one melody note of the same `sound_event` is still
  ringing** at the cut time (overlapping `[onset, onset+dur]` windows sharing an event) and
  emit `logging.warning("event-level cut: K overlapping <event> notes share one cut — earlier note(s) will be silenced prematurely")`. This is the documented limitation that a true
  per-note cut would need (out of v1 scope). The plan also exposes
  `cut_events: list[str]` = sorted unique events to drive the `cutmel` function body
  (`stopsound @a record <ev>` per event, poc/46 L167 / poc/48 L466).

`MelodyCutPlan` fields: `.delays_by_cell: dict[int,int]`, `.schedule_by_cell: dict[int,int]`
(absolute mode), `.cut_events: list[str]`, `.warnings: list[str]`, `.median_delay_gt: int`.

### 1.7 Tick-rate handling

- **Tick rate is MANUAL.** The PLAYER must type `/tick rate 80` manually before playing; the
  machine does **NOT** set it. Without it, playback runs ~4× too slow (eerie/slow — MEMORY:
  redpiano-runtime-gotchas "eerie/slow = needs manual /tick rate 80").
- `redpiano_core.tickrate_command_block` was **DELETED**: the earlier auto-set command block
  (fired from `playcore` on **[play]**) proved unreliable in-game, so it was removed. There is
  no self-set mechanism — the rate must be set by hand.
- **No gametime "self-check".** An earlier `tickrate_selfcheck` was also removed: gametime
  advances by exactly 1 per game-tick *regardless* of `/tick rate`, so a delta check cannot
  detect the rate and only spams a false WARN every tick.

### 1.8 Direction rotation (emit-time)

```python
def rot_xz(x, z, start_dir) -> tuple[int, int]
def rotate_command(cmd: str, start_dir) -> str
```
- All form geometry is authored **+X**; `start_dir` (`+X`/`-X`/`+Z`/`-Z`) is applied at emit
  time by rotating the authored coords. `rot_xz` rotates an `(x, z)` pair around the origin;
  `rotate_command` applies it to `setblock`/`forceload`/`tp` coordinates and remaps `facing=` /
  `rotation=` blockstates accordingly.
- **`+X` is the identity** (verified: the emitted path is byte-unchanged at `+X`). All four
  cardinals are supported; non-`+X` output is generation-verified (round-trips, collision-free)
  but still needs an **in-game listen** (the facings bind to in-world redstone).

radiate/chord emission is **NOT** here: `chord3` / radiate / palette grid / S-wave path layout
are **geometry** → they live in `generators/`. Core must not gain them.

### 1.9 Version profile accessor

```python
def get_version_profile(mc_version: str) -> VersionProfile
```
- `VersionProfile` carries `dp_format:int`, `rp_format:int`, `function_folder:str`,
  `tag_function_folder:str`, `packmeta_shape:str` (`"single"`|`"minmax"`), `sign_dialect:str`
  (`"component_string"`|`"component_snbt"`), `has_tick_rate:bool`, `has_return_cmd:bool`,
  `tier:str` (`"green"`|`"yellow"`), `tps:int`, `game_ticks_per_cell:int`, `notes:str`,
  `confidence:str`.
- Looks up `mc_version` in `VERSION_TABLE` (§3). **RAISES `RedPianoError(f"unknown mc_version {v}; add it to VERSION_TABLE")` on miss** — never guesses. This is the single accessor; nothing else
  in the codebase may hardcode a pack_format or folder name.
- **Tick-rate floor refusal (≤1.20.2):** versions below 1.20.3 have no `/tick rate` (added
  1.20.3) and no `return`, so the tick80 timing model (80 TPS, samples tuned for it, repeater
  geometry baked at 0.025s/cell) cannot work (4×-too-slow, unfixable). `get_version_profile`
  **HARD-REFUSES** these. **1.20.3 = the hard floor.**
- **1.21.9 RESOLVES** (no longer a hard-fail): it is a supported row with `packmeta_shape="minmax"`,
  so `write_pack_mcmeta` emits `min_format`/`max_format`. (Replaces the old guard that hard-failed
  any `uses_minmax`/≥1.21.9 version.)
- `function_folder` is `"function"` (1.21+) or `"functions"` (pre-1.21);
  `tag_function_folder` is `"function"` / `"functions"` correspondingly (the `tags/<x>/` segment).

```python
def assert_build_supported(profile: VersionProfile) -> None
```
- Green-band policy gate. Raises `RedPianoError` if `profile.tier != "green"` (i.e. the
  1.20.3..1.20.6 **"yellow"** band, whose datapack/resourcepack adapt automatically but whose
  RedPiano mod needs a real Java source-port + Java 17 — OUT OF the skill's auto scope). The
  three build entry points (`build_machine` + `build_particles` + `build_resourcepack`) call it
  before emitting anything, so yellow versions fail loudly at the top. (≤1.20.2 never reaches
  here — `get_version_profile` already refused it.)

---

## 2. `params_schema.py` contract

```python
SCHEMA_VERSION = 1
```

### 2.1 Field table (full designer export, from `designer/layout_designer.html` — the `updateUI` export builder)

`consumed-by` = which generator reads it. `none-yet` = exported by designer but **no generator
implements it** → if SET to a non-default, `load_params` MUST raise (§2.3).

| field | type | req? | default | consumed by | notes |
|---|---|---|---|---|---|
| `song` | str | optional | `"untitled"` | both (display name) | from MIDI stem if absent |
| `form` | enum `inplace\|swave\|straight\|custom\|multilane` | **required** | — | dispatch | all five are v1; swave/straight/custom share `generators/swave.py` |
| `method` | enum `redpiano\|slice` | optional | `redpiano` | both | **`slice` = Family B, OUT OF SCOPE → hard-fail** |
| `base_block` | str | optional | `minecraft:stone` | both | the conductive base/`PASS` block |
| `start_x` | int | optional | `0` | both (origin X) | overridden by CLI `--origin` |
| `start_z` | int | optional | `0` | both (origin Z) | " |
| `start_y` | int | optional | `255` | both (origin Y) | " |
| `start_dir` | enum `+X\|-X\|+Z\|-Z` | optional | `+X` | both | **all 4 cardinals supported** via emit-time rotation (`redpiano_core` §1.8); `+X` = identity; non-`+X` generation-verified, in-game listen pending |
| `signal_tracks` | list[`{dx,dz,dy,name}`] \| null | optional | `null` | multilane | particle/redstone signal lanes; **full 3D offset {dx,dy,dz} all consumed by multilane** |
| **inplace-only** | | | | | |
| `palette_noteblocks` | int | optional | (derived) | inplace (report/ref) | actual palette size is derived from MIDI; designer value is a preview hint |
| `PCOLS` | int | optional | `16` | inplace | palette grid width (poc/45 `PCOLS`) |
| `ROWGAP` | int | optional | `3` | inplace | palette row Z spacing (poc/45 `ROWGAP`, ≥3) |
| `multi` | bool | optional | `true` | inplace | multi-instrument (default) vs `false` = piano-only single |
| **swave-only** | | | | | |
| `cells` | int | optional | (derived) | swave (preview) | real cell count derived from MIDI timeline |
| `sounding` | int | optional | (derived) | swave (preview) | real sounding count derived |
| `XRUN` | int | optional | `3` (poc/48) / `6` (designer) | swave | X run length per S segment; **≥2** |
| `ZMAX` | int | optional | `4` (poc/48) / `10` (designer) | swave | Z amplitude of S wave; **≥2** |
| `line_width_radiate` | int | optional | `3` | none-yet | radiate chord width; poc fixes 3-wide (above+2 sides). **width≠3 unimplemented** |
| `fold_gap` | int | optional | `1` | none-yet | plane-fold gap; **not wired in swave/straight/custom** |
| `dual_track_mirror` | bool | optional | `true` | swave | second track mirror (poc/48 always 2-track mirror) |
| `track_sep` | int | optional | omit → backend derives `PATH_ZSPAN+3` (recommended) | swave | inter-track Z separation. **Do NOT ship a literal `3`** — with `dual_track_mirror` the safe minimum is the song-dependent `PATH_ZSPAN+3`, so a fixed `3` collides. Omit the field (designer omits it unless the user manually overrides SEP) and the backend derives the safe value; an explicit override below `PATH_ZSPAN+3` is rejected with a "needs at least N" error, never a raw collision. |
| `chord_mode` | enum `radiate\|multilane` | optional | `radiate` | swave (radiate) / multilane | `multilane` selects the **multilane form**; rejected on swave/straight/custom (§2.3) |
| `max_poly` | int | optional | `7` | multilane | consumed by `--form multilane`; rejected on swave/straight/custom |
| `lane_dz` | int | optional | `2` | multilane | consumed by `--form multilane`; rejected on swave/straight/custom |
| `lane_offsets` | list \| null | optional | `null` | multilane | consumed by `--form multilane`; rejected on swave/straight/custom |
| **custom-only** | | | | | |
| `waypoints` | list[[x,z]] \| null | optional | `null` | custom | `form=custom` route; **required** (non-empty) on custom (§2.3), rejected on other forms |
| `side_view` | bool | optional | `false` | none (designer-only) | render toggle, not a build param — ignored |
| **slice-only (Family B, OUT OF SCOPE)** | | | | | |
| `audio_file` | str \| null | optional | `null` | none (slice) | hard-fail if `method=slice` |
| `audio_duration` | num | optional | `0` | none (slice) | " |
| `tick_rate` | int | optional | `20` (slice) | none (slice) | " |
| `result` / `bbox_cells` | object | optional | — | none (designer metadata) | echoed preview metrics; **ignored on load** (not authoritative) |

> `result`, `bbox_cells`, `side_view`, and `slice_note` are designer *preview/metadata* and
> are explicitly IGNORED (not required, not validated, never consumed). All real metrics are
> derived from the MIDI at build time.

### 2.2 `load_params`

```python
def load_params(path_or_dict: str | dict, form: str) -> dict
```
1. Accept a JSON file path or an already-parsed dict.
2. Validate `form` ∈ {`inplace`,`swave`,`straight`,`custom`,`multilane`} (anything else →
   `RedPianoError`). `swave`/`straight`/`custom` dispatch to `generators/swave.py`; `multilane`
   to `generators/multilane.py`; `inplace` to `generators/inplace.py`.
3. Apply defaults from the table for the chosen form.
4. **Required-field check:** `form` must be present (the dict's own `form` must match the
   `form` arg, else raise). No other field is strictly required (all have defaults), but
   `method` must be `redpiano`.
5. **`method=slice` → HARD FAIL:** `RedPianoError("method=slice (Family B audio-slice) is out of scope for this skill — use the external mc-noteblock-demo repo")`.
6. **Cross-form rejection (prompt requirement — NO silent drop):** for any field that is SET
   to a **non-default** value but is NOT consumed by `form`, raise
   `RedPianoError(f"field '{k}' is not supported by form '{form}'")`. Example: passing
   `PCOLS=20` with `form=swave`, or `XRUN=8` with `form=inplace`. Designer-metadata fields
   (`result`,`bbox_cells`,`side_view`) are whitelisted as ignorable and do NOT trigger this.
7. Return the normalized, defaulted dict.

### 2.3 Unimplemented designer features — generators MUST hard-fail

`params_schema.py` exposes a constant:
```python
UNIMPLEMENTED = {
  "chord_mode == 'multilane'":"chord_mode=multilane is not a swave/straight/custom option — use --form multilane instead",
  "line_width_radiate != 3":  "radiate width is fixed at 3 (above + 2 sides)",
  "fold_gap / plane-fold":    "fold_gap/plane-fold is not wired into swave/straight/custom",
  "method == 'slice'":        "Family B audio slice out of scope",
  "max_poly/lane_dz/lane_offsets": "multilane-only — use --form multilane (don't apply to swave/straight/custom)",
}
```
and a helper `assert_supported(params, form)` that generators call FIRST; it raises
`RedPianoError` with the matching message if any unimplemented combination is set to a
non-default.

> **These hard-fails are GATED to the marching forms.** `assert_supported` only checks
> `chord_mode`/`line_width_radiate`/`fold_gap`/`max_poly`/`lane_*` when
> `form ∈ {swave, straight, custom}` (`params_schema.py` `if form in _MARCH`). **`multilane`
> and `custom` ARE v1 forms** — `--form multilane` consumes `chord_mode=multilane`/`max_poly`/
> `lane_dz`/`lane_offsets`/`signal_tracks` (full 3D offset {dx,dy,dz}); `--form custom`
> consumes `waypoints`. The
> entries above only reject those fields when you set them on a form that doesn't use them
> (e.g. `max_poly` on `swave`). Generators call `assert_supported` before emitting
a single block, so an unsupported designer JSON fails loudly at the top, not mid-build.

---

## 3. VERSION_TABLE data

Single source of truth in `redpiano_core.py`. Resource-pack and data-pack `pack_format` are
**different number lines** — do not conflate. Anchored values: **MC 1.21.8 → dp_format=81,
rp_format=64** (confirmed against `poc/02e_build_resourcepack.py` default `rp=64` and every
generator's hardcoded `pack_format: 81`, and the Minecraft Wiki Pack_format table).

Each entry is now a **rich record (dict)**, not the old 5-tuple — it carries `packmeta_shape`,
`sign_dialect`, `has_tick_rate`, `has_return_cmd`, `tier`, `tps`, `game_ticks_per_cell` alongside
the formats. Rows span **1.20..1.21.9**. `get_version_profile` is the only accessor (§1.9).

```python
VERSION_TABLE = {
  # mc_version : {dp_format, rp_format, function_folder, packmeta_shape, sign_dialect,
  #               has_tick_rate, has_return_cmd, tier, tps, game_ticks_per_cell,
  #               confidence, notes}
  # ── ≤1.20.2: HARD-REFUSED (no /tick rate, no return; tick80 impossible). 1.20.3 = hard floor.
  # ── 1.20.3..1.20.6 = tier "yellow": dp/rp adapt, but mod needs a Java source-port → assert_build_supported() refuses.
  "1.20.4":  {"dp_format":26, "rp_format":22, "function_folder":"functions",
              "packmeta_shape":"single", "sign_dialect":"component_string",
              "has_tick_rate":True, "has_return_cmd":True, "tier":"yellow",
              "tps":80, "game_ticks_per_cell":2, "confidence":"high",
              "notes":"last pre-rename line; plural folders functions/, tags/functions/. YELLOW: mod needs <1.21 scoreboard-API source-port + Java 17."},
  # ── 1.21..1.21.10 = tier "green" (supported auto band).
  "1.21":    {"dp_format":48, "rp_format":34, "function_folder":"function",
              "packmeta_shape":"single", "sign_dialect":"component_string",
              "has_tick_rate":True, "has_return_cmd":True, "tier":"green",
              "tps":80, "game_ticks_per_cell":2, "confidence":"high",
              "notes":"24w21a/format 48: folders renamed to SINGULAR function/, tags/function/, advancement/, predicate/, loot_table/"},
  "1.21.1":  {"dp_format":48, "rp_format":34, "function_folder":"function",
              "packmeta_shape":"single", "sign_dialect":"component_string", "tier":"green", "confidence":"high", "notes":"same as 1.21"},
  "1.21.2":  {"dp_format":57, "rp_format":42, "function_folder":"function",
              "packmeta_shape":"single", "sign_dialect":"component_string", "tier":"green", "confidence":"high", "notes":""},
  "1.21.3":  {"dp_format":57, "rp_format":42, "function_folder":"function",
              "packmeta_shape":"single", "sign_dialect":"component_string", "tier":"green", "confidence":"high", "notes":""},
  "1.21.4":  {"dp_format":61, "rp_format":46, "function_folder":"function",
              "packmeta_shape":"single", "sign_dialect":"component_string", "tier":"green", "confidence":"high",
              "notes":"last component_string sign line; ≥1.21.5 flips to component_snbt"},
  "1.21.5":  {"dp_format":71, "rp_format":55, "function_folder":"function",
              "packmeta_shape":"single", "sign_dialect":"component_snbt", "tier":"green", "confidence":"high",
              "notes":"sign dialect flips to SNBT compound entries; old quoted form renders as literal text"},
  "1.21.6":  {"dp_format":80, "rp_format":63, "function_folder":"function",
              "packmeta_shape":"single", "sign_dialect":"component_snbt", "tier":"green", "confidence":"high", "notes":""},
  "1.21.7":  {"dp_format":81, "rp_format":64, "function_folder":"function",
              "packmeta_shape":"single", "sign_dialect":"component_snbt", "tier":"green", "confidence":"high", "notes":""},
  "1.21.8":  {"dp_format":81, "rp_format":64, "function_folder":"function",
              "packmeta_shape":"single", "sign_dialect":"component_snbt",
              "has_tick_rate":True, "has_return_cmd":True, "tier":"green",
              "tps":80, "game_ticks_per_cell":2, "confidence":"high",
              "notes":"★ ANCHORED & VERIFIED DEFAULT: matches poc generators (dp 81) + poc/02e resourcepack (rp 64), user-tested in-game."},
  "1.21.9":  {"dp_format":88, "rp_format":69, "function_folder":"function",
              "packmeta_shape":"minmax", "sign_dialect":"component_snbt", "tier":"green", "confidence":"high",
              "notes":"25w31a switched pack.mcmeta to min_format/max_format (packmeta_shape=minmax). SUPPORTED via min/max emission; dp 88 / rp 69 format-verified, in-game listen pending."},
  "1.21.10": {"dp_format":88, "rp_format":69, "function_folder":"function",
              "packmeta_shape":"minmax", "sign_dialect":"component_snbt", "tier":"green", "confidence":"high",
              "notes":"non-breaking sibling of 1.21.9 -> same major format 88/69 (minor-versioned pack formats introduced 1.21.9). Top of the supported band."},
}
```
(Fields omitted on a row inherit the documented per-family defaults — e.g. `tps=80`,
`game_ticks_per_cell=2`, `has_tick_rate/has_return_cmd=True` across the 1.21.x rows.)

### 3.1 Confidence & sources

| version | dp | rp | conf | source |
|---|---|---|---|---|
| 1.20.4 | 26 | 22 | high | Minecraft Wiki Pack_format (pre-rename anchor) |
| 1.21 / .1 | 48 | 34 | high | Wiki Pack_format; folder rename = snapshot 24w21a / format 48 |
| 1.21.2 / .3 | 57 | 42 | high | Wiki Pack_format |
| 1.21.4 | 61 | 46 | high | Wiki Pack_format |
| 1.21.5 | 71 | 55 | high | Wiki Pack_format |
| 1.21.6 | 80 | 63 | high | Wiki Pack_format |
| 1.21.7 | 81 | 64 | high | Wiki Pack_format |
| **1.21.8** | **81** | **64** | **high** | Wiki Pack_format + **anchored in repo** (poc generators dp=81, poc/02e rp=64, user-verified in-game) |
| 1.21.9 | 88 | 69 | **high** | Wiki; 1.21.9 uses `min_format`/`max_format` (`packmeta_shape="minmax"`) — **SUPPORTED via min/max emission**; formats verified, in-game listen pending |
| 1.21.10 | 88 | 69 | **high** | Wiki; non-breaking sibling of 1.21.9 → same major 88/69 (minor-versioned formats since 1.21.9). Top of the supported band |

> **Conflict note (resolved):** an initial web search reported "1.21.8 → pack format 64",
> which conflated the **resource-pack** number (64) with the **data-pack** number. The
> authoritative Wiki Pack_format table and the repo's own anchors confirm **dp=81, rp=64** for
> 1.21.8. The skill MUST treat dp and rp as separate columns.

### 3.2 Adding a new version (documented mechanism)

To support a new MC version, add **one row** to `VERSION_TABLE` in `redpiano_core.py` via the
`_vrow(dp, rp, folder, packmeta, sign, has_tick, tier, conf, notes)` helper (the row is a
rich dict, not the old 5-tuple). Source the two format numbers from
`https://minecraft.wiki/w/Pack_format` (data pack column AND resource pack column — they
differ). Set `function_folder="function"` for 1.21+ and `"functions"` for pre-1.21, plus
`packmeta_shape`/`sign_dialect`/`has_tick_rate`/`tier`. Set `confidence="low"` and a `notes`
caveat until verified in-game; promote to `"high"` after a successful in-world test.
**For 1.21.9+** set `packmeta_shape="minmax"` so `write_pack_mcmeta` emits
`min_format`/`max_format` (§1.4) — a single `pack_format` there would make MC silently disable
the pack (= total silence). 1.21.9 is **now supported** via this min/max emission (it is no
longer a hard-fail). Versions in the 1.20.3..1.20.6 band must be `tier="yellow"` so
`assert_build_supported` (§1.9) refuses them; ≤1.20.2 is hard-refused by `get_version_profile`
itself (below the `/tick rate` floor). Every consumer goes through `get_version_profile`.

---

## 4. `build_machine.py` CLI contract

```
python build_machine.py --midi <file>
                        [--params <json>]
                        --form {inplace,swave,straight,custom,multilane}
                        --ns <NS>
                        --origin X Z Y
                        --mc-version 1.21.8
                        [--name <display>]
                        [--melcap <seconds>]          # default 1.2
                        [--world-dir <dir>]           # if given, deploy datapack there
                        [--no-deploy]                 # DEFAULT: build only, do NOT copy to a world
                        [--force-cap]                 # allow forceload auto-fold above soft cap instead of hard-fail
```

Flags:
- `--midi` (required): source `.mid`. Parsed with the program-tracking MIDI reader (poc/46
  L63-77 semantics: track `program_change` per channel, ch9→drum, tag every note with
  `instr/dur/vel`).
- `--params` (optional): designer JSON. If omitted, all fields take defaults for `--form`.
- `--form` (required): one of `inplace`/`swave`/`straight`/`custom`/`multilane`. Must agree
  with `params.form` if both given. (`custom` needs `--params` with `waypoints`; `multilane`
  needs `--params` with `chord_mode=multilane`. The forceload cap is a **soft** cap — over it,
  pass `--force-cap` to build anyway; multilane is a straight machine so it can't plane-fold,
  but it is not a guaranteed audio drop — tested fine at ~428 chunks. For a smaller footprint
  use swave.)
- `--ns` (required): datapack namespace (also scoreboard objective name).
- `--origin X Z Y` (required): world origin; **overrides** `start_x/start_z/start_y` from params.
- `--mc-version` (required, default `1.21.8`): drives `get_version_profile` → dp_format,
  function folder. Unknown version → hard fail (§1.9).
- `--world-dir` / `--no-deploy`: deploy is **opt-in**. Default is `--no-deploy` (build into
  `build/<ns>/` only). `--world-dir <dir>` calls `Datapack.deploy`. Mutually exclusive.

**Pipeline order (WF-2 implements exactly this):**
1. `profile = get_version_profile(mc_version)` (fail fast on unknown version).
2. `params = load_params(params_or_{}, form)` (fail fast on cross-form / slice / custom).
3. `assert_supported(params, form)` (fail fast on unimplemented designer features).
4. Parse MIDI → tagged notes (program-tracking reader).
5. `imap = InstrumentMap.load(assets/redpiano_map_multi.json)` (asserts 103 blocks).
6. Dispatch to `generators/<form>.py`, passing `(notes, params, origin, imap, profile, melcap)`.
   The generator: quantizes to cells (`U=2/80`), builds palette/timeline, resolves every note
   via `imap.resolve` (collecting octave-shift WARNs), lays out geometry with `Grid.put`
   (collision-guarded), plans melody cuts via `plan_melody_cuts` (collecting polyphony WARNs +
   the cut-floor assertion), and assembles datapack functions via core builders.
7. `forceload_guard(bbox, auto_fold=force_cap)` — hard-fail or fold.
8. Write datapack (`Datapack.write_*`, profile-driven formats + folder names).
9. If `--world-dir`: `deploy`. Else leave in `build/<ns>/`.
10. Print a report (palette/cells, dropped, octave-shifted count, cut count + median delay,
    forceload chunks, song length, all WARNs) — mirrors the poc stdout summaries.

**Exit behavior:** any `RedPianoError` → non-zero exit with the message; no partial deploy
(build into staging dir, only `deploy` copies — a failed build never touches a world).

---

## 5. Companion CLIs (`build_resourcepack.py`, `mod_build.py`)

Both are version-driven off the same `VERSION_TABLE`/`get_version_profile` (§1.9, §3) so one
`--mc-version` self-syncs datapack + resourcepack + mod-build. Both call
`assert_build_supported(profile)` (refuse yellow) and both expose `--selftest`.

### 5.1 `build_resourcepack.py`

```
python build_resourcepack.py --mc-version 1.21.8 --samples-root <dir> --out <dir> [--selftest]
```
- Repacks the `qzpno_mv` resourcepack IN the skill (ports `poc/02e_build_resourcepack.py`,
  de-hardcoded). Reads `rp_format` AND the `pack.mcmeta` shape (`packmeta_shape`, §1.4) from the
  version table — **never hardcodes 64**. (rp_format 64 is the 1.21.8 row.)
- Samples ship separately — see [BINARIES.md](../BINARIES.md).

### 5.2 `mod_build.py`

```
python mod_build.py --mc-version 1.21.8 [--write] [--set-mc-range] [--selftest]
```
- Prints (or `--write` applies) the VERIFIED mod toolchain per version — fabric-loom /
  fabric-loader / fabric-api / Java / Mojang mappings — plus a porting-tier note. It does **NOT**
  run gradle and does **NOT** widen `fabric.mod.json`'s tested `minecraft` range unless you pass
  `--set-mc-range`.
- The mod build is **parameterized**: `mod/redpiano/build.gradle` reads
  `minecraft_version`/`loader_version`/`fabric_version`/`java_version` from `gradle.properties`
  (default = the 1.21.8 anchor, so an unedited build is byte-identical). `--write` retargets those
  + rewrites the fabric-loom plugin-version line. (Verified: an offline `gradle build` still
  produces `redpiano-1.0.0.jar` (~11.6 KB) at the anchor.)
- **MOD HONESTY (preserved):** the mixin binds to INTERNAL NoteBlock bytecode, so EVERY target
  version still needs a recompiled jar AND one in-game listen. Within 1.21.x the retarget is
  NUMBER-ONLY (no Java source edits); 1.21.9 is number-only too but verify the yarn
  `getWorld`→`getEntityWorld` rename equivalent under Mojang mappings in `genSources`. Below 1.21
  = real Java source-port (scoreboard API); below ~1.19 = audio API port; below 1.20.3 =
  impossible. See [MOD_ARCHITECTURE.md](MOD_ARCHITECTURE.md).

---

## Appendix — verified-fact cross-reference (for WF-2 sanity checks)

- in-place trigger geometry & repeat: poc/45 L99-153 (palette pos, `put`, side trigger slot
  `z-1`, `offall` reset, `schedule s{c+1} {dt}t` with `dt=delta*2`).
- multi-instrument resolve + family map: poc/46 L41-76; map JSON poc/redpiano_map_multi.json.
- melody-cut (relative): poc/46 L109-122 (delays), L167 (`cutmel` body), L173 (schedule append).
- melody-cut (absolute, swave): poc/48 L198-210, L466, L488.
- S-wave path + mirror + radiate chord3: poc/48 L213-339 (geometry → `generators/swave.py`, NOT core).
- forceload split: poc/48 L380-388; chunk count formula L559.
- sign 4-line / labeled button: poc/45 L156-162.
- pack_format / tags: poc/45 L135-138 (hardcoded 81 + singular `function/` → MUST become profile-driven).
- resourcepack rp_format detection + default 64: poc/02e L41-52.
- `/tick rate 80` requirement: MEMORY redpiano-runtime-gotchas; U/game-tick conversion poc L39/L149.

**Sources (version research):**
- [Minecraft Wiki — Pack format](https://minecraft.wiki/w/Pack_format) (authoritative dp/rp number tables)
- [Minecraft Wiki — Data pack](https://minecraft.wiki/w/Data_pack)
- Folder rename to singular = snapshot **24w21a** / data pack format **48** (1.21):
  [minecraftcommands.github.io/wiki/debugging](https://minecraftcommands.github.io/wiki/debugging.html),
  [baugues.com/minecraft-functions](https://www.baugues.com/minecraft-functions/)
- Repo anchors: `poc/02e_build_resourcepack.py` (rp=64), `poc/45/46/48` (dp=81), `poc/redpiano_map_multi.json` (103 blocks).
