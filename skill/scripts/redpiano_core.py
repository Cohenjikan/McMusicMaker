# -*- coding: utf-8 -*-
"""redpiano_core.py — shared plumbing for the RedPiano (Family A) skill.

Implements CONTRACT.md §1, §3 EXACTLY. **Only shared plumbing lives here — NO
form-specific geometry.** The S-wave path, palette grid, and chord3/radiate
emission are *geometry* and belong in ``generators/`` (§1.8). Core takes data and
produces strings/files; it never decides machine *shape*.

Every function raises ``RedPianoError`` on contract violations — never silently
degrades. The proven lab generators (poc/45, poc/46, poc/48) are the behavioral
oracle: the datapack command sequences, the 4-line-sign rule, the side-trigger /
collision semantics, and the map resolution are byte-faithful to them, with the
contract's logic upgrades layered in:
  * collision guard forbids two distinct non-air blocks (air ops always pass);
  * resolver OCTAVE-SHIFTS out-of-range notes instead of silently clamping pitch;
  * forceload over-threshold guard (hard-fail or auto-fold split);
  * version-table-driven pack_format + folder names (never hardcoded 81/`function`);
  * tick-rate command-block + self-check;
  * melody-cut scheduler with cut<gap assertion + same-event polyphony WARN.

Pure stdlib only.
"""

import json
import logging
import os
import shutil

# share the exception + schema helpers from params_schema (no geometry there).
from params_schema import RedPianoError  # noqa: F401  (re-exported)

log = logging.getLogger("redpiano")


# ─────────────────────────────────────────────────────────────────────────────
# §3 / §1.9  VERSION_TABLE + profile accessor
#   Resource-pack and data-pack pack_format are DIFFERENT number lines.
#   Anchored: MC 1.21.8 -> dp_format=81, rp_format=64 (poc generators dp=81,
#   poc/02e resourcepack rp=64, user-verified in-game).
# ─────────────────────────────────────────────────────────────────────────────

# mc_version : (dp_format, rp_format, function_folder, confidence, notes)
VERSION_TABLE = {
    "1.20.4":  (26, 22, "functions", "high",
                "last pre-rename line; plural folders functions/, tags/functions/"),
    "1.21":    (48, 34, "function",  "high",
                "24w21a/format 48: folders renamed to SINGULAR function/, tags/function/, "
                "advancement/, predicate/, loot_table/"),
    "1.21.1":  (48, 34, "function",  "high",  "same as 1.21"),
    "1.21.2":  (57, 42, "function",  "high",  ""),
    "1.21.3":  (57, 42, "function",  "high",  ""),
    "1.21.4":  (61, 46, "function",  "high",  ""),
    "1.21.5":  (71, 55, "function",  "high",  ""),
    "1.21.6":  (80, 63, "function",  "high",  ""),
    "1.21.7":  (81, 64, "function",  "high",  ""),
    "1.21.8":  (81, 64, "function",  "high",
                "ANCHORED: matches poc generators (dp 81) + poc/02e resourcepack (rp 64). "
                "Project target."),
    "1.21.9":  (88, 69, "function",  "low",
                "25w31a+ switched to min_format/max_format; single pack_format deprecated. "
                "Numbers approximate — verify before use."),
}


class VersionProfile:
    """Resolved per-MC-version format/folder facts. Single source of truth for
    pack_format numbers and the 1.21 plural->singular folder rename."""

    __slots__ = ("mc_version", "dp_format", "rp_format", "function_folder",
                 "tag_function_folder", "confidence", "notes")

    def __init__(self, mc_version, dp_format, rp_format, function_folder,
                 confidence, notes):
        self.mc_version = mc_version
        self.dp_format = dp_format
        self.rp_format = rp_format
        self.function_folder = function_folder
        # the tags/<x>/ segment follows the same singular/plural rename
        self.tag_function_folder = function_folder
        self.confidence = confidence
        self.notes = notes

    @property
    def uses_minmax(self):
        """1.21.9+ uses pack.mcmeta min_format/max_format; single pack_format is
        deprecated there. Not yet truly supported (write_pack_mcmeta warns)."""
        return self.mc_version >= "1.21.9"

    def __repr__(self):
        return (f"VersionProfile({self.mc_version}, dp={self.dp_format}, "
                f"rp={self.rp_format}, folder={self.function_folder!r}, "
                f"conf={self.confidence})")


def get_version_profile(mc_version):
    """The ONLY accessor for pack_format / folder facts. Raises on an unknown
    version — never guesses (CONTRACT §1.9). Nothing else in the codebase may
    hardcode a pack_format or folder name."""
    row = VERSION_TABLE.get(mc_version)
    if row is None:
        raise RedPianoError(
            f"unknown mc_version {mc_version}; add it to VERSION_TABLE "
            f"(source dp/rp format from https://minecraft.wiki/w/Pack_format)"
        )
    dp_format, rp_format, function_folder, confidence, notes = row
    if confidence == "low":
        log.warning("mc_version %s has LOW-confidence format data: %s",
                    mc_version, notes)
    profile = VersionProfile(mc_version, dp_format, rp_format, function_folder,
                             confidence, notes)
    # 1.21.9+ switched pack.mcmeta to min_format/max_format; a single pack_format is
    # SILENTLY DISABLED by MC (= total silence). We don't emit min/max yet, so hard-fail
    # rather than hand the user a build that won't load. (Honest > a silent footgun.)
    if profile.uses_minmax:
        raise RedPianoError(
            f"mc_version {mc_version} (>=1.21.9) needs pack.mcmeta min_format/max_format, "
            f"which this skill does not emit yet — a single pack_format={dp_format} would be "
            f"silently disabled by MC. Use 1.21.8 (the project target) until min/max is added."
        )
    return profile


# ─────────────────────────────────────────────────────────────────────────────
# §1.1  Datapack writer + lifecycle
# ─────────────────────────────────────────────────────────────────────────────

class Datapack:
    """Datapack tree writer. Resolves a VersionProfile at construction and uses
    it for ALL pack_format numbers + folder names (the ONLY place the 1.21
    plural->singular rename is honored). Mirrors the poc ``w()`` / ``wf()``
    semantics byte-for-byte, but profile-driven instead of hardcoded.
    """

    def __init__(self, ns, name, out_dir, mc_version):
        self.ns = ns
        self.name = name
        self.mc_version = mc_version
        self.profile = get_version_profile(mc_version)
        self.dp_format = self.profile.dp_format
        self.function_folder = self.profile.function_folder
        self.tag_function_folder = self.profile.tag_function_folder
        self.root = os.path.join(out_dir, ns)
        # like the poc: remove and recreate the datapack root
        if os.path.isdir(self.root):
            shutil.rmtree(self.root)
        os.makedirs(self.root)

    def write(self, rel_path, content):
        """Write ``content`` to <root>/<rel_path>, creating parent dirs. Forces
        \\n line endings and a trailing newline (poc ``w()`` semantics, poc/45 L131)."""
        p = os.path.join(self.root, rel_path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if not content.endswith("\n"):
            content = content + "\n"
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    def write_function(self, name, body):
        """Write data/<ns>/<function_folder>/<name>.mcfunction. ``body`` list is
        '\\n'.join'ed. function_folder comes from the version profile — `function`
        (singular) for 1.21+, `functions` (plural) for pre-1.21 (poc hardcodes
        singular; core parameterizes it)."""
        if not isinstance(body, str):
            body = "\n".join(body)
        self.write(f"data/{self.ns}/{self.function_folder}/{name}.mcfunction", body)

    def write_pack_mcmeta(self, description):
        """Write pack.mcmeta with the profile's dp_format (NEVER hardcoded 81),
        indent=2 (poc/45 L135). 1.21.9+ (min_format/max_format) is rejected upstream
        in get_version_profile, so dp_format here is always a valid single pack_format."""
        meta = {"pack": {"pack_format": self.dp_format, "description": description}}
        # pack.mcmeta is a raw JSON file at the root (not via write(), which adds \n);
        # keep indent=2 like the poc.
        p = os.path.join(self.root, "pack.mcmeta")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def write_load_tick_tags(self):
        """Write data/minecraft/tags/<function_folder>/{load,tick}.json, each
        {"values": ["<ns>:load"]} / ["<ns>:tick"] (poc/45 L137-138). Folder is
        tags/function/ (1.21+) or tags/functions/ (pre-1.21) — profile-driven."""
        tag_dir = f"data/minecraft/tags/{self.tag_function_folder}"
        self.write(f"{tag_dir}/load.json",
                   json.dumps({"values": [f"{self.ns}:load"]}))
        self.write(f"{tag_dir}/tick.json",
                   json.dumps({"values": [f"{self.ns}:tick"]}))

    def deploy(self, world_datapacks_dir):
        """Copy the built tree into <world_datapacks_dir>/<ns> (rmtree+copytree,
        poc/45 L212-214). Returns the destination path. Opt-in (only called when
        --world-dir is given)."""
        dst = os.path.join(world_datapacks_dir, self.ns)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(self.root, dst)
        return dst


# ── Init/setup/cleanup scaffolding builders ──────────────────────────────────
# Core provides *builders* that return command lists; generators assemble them
# with form-specific block lists. Core MUST NOT invent machine geometry.

def scoreboard_reset(ns):
    """['scoreboard players set PLAY <ns> 0', 'scoreboard players set LOOP <ns> 0']
    (poc/45 L170). The PLAY/LOOP reset pair used by in-place machines."""
    return [
        f"scoreboard players set PLAY {ns} 0",
        f"scoreboard players set LOOP {ns} 0",
    ]


def build_load_fn(ns, name, extra_objectives=True):
    """The `load` function body (poc/45 L171-174): add objectives, BLD=-1, the
    PLAY/LOOP reset, rpcfg poly/human=1, forceload remove all, schedule clear
    done, and the loaded tellraw. ``extra_objectives`` toggles the rpcfg block."""
    out = [
        f"scoreboard objectives add {ns} dummy",
        f"scoreboard players set BLD {ns} -1",
    ]
    out += scoreboard_reset(ns)
    if extra_objectives:
        out += [
            "scoreboard objectives add rpcfg dummy",
            "scoreboard players set poly rpcfg 1",
            "scoreboard players set human rpcfg 1",
        ]
    out += [
        "forceload remove all",
        f"schedule clear {ns}:done",
        f'tellraw @a ["",{{"text":"[{ns}] {name} loaded. ","color":"aqua"}},'
        f'{{"text":"need RedPiano mod + qzpno pack. /tick rate 80 -> /function {ns}:setup"}}]',
    ]
    return out


def build_tick_dispatch(ns, n_batches):
    """The BLD-counter build driver for the `tick` function (poc/45 L177-180):
    for k in 0..n_batches-1 run bld/bN; at n_batches run builddone; while in
    0..n_batches increment BLD."""
    bs = [
        f"execute if score BLD {ns} matches {k} run function {ns}:bld/b{k}"
        for k in range(n_batches)
    ]
    bs += [
        f"execute if score BLD {ns} matches {n_batches} run function {ns}:builddone",
        f"execute if score BLD {ns} matches 0..{n_batches} run scoreboard players add BLD {ns} 1",
    ]
    return bs


def batch_setblocks(setblock_lines, batch=2000):
    """Split a flat command stream into bld/bN chunks of ``batch`` lines each
    (BATCH=2000 in every poc). Returns a list of lists, preserving order."""
    return [setblock_lines[i:i + batch] for i in range(0, len(setblock_lines), batch)]


# ─────────────────────────────────────────────────────────────────────────────
# §1.2  Grid — collision-guarded grid writer
# ─────────────────────────────────────────────────────────────────────────────

_AIR = ("air", "minecraft:air")


def _is_air(block):
    return block in _AIR


class Grid:
    """Collision-guarded setblock writer. The command-stream order IS the build
    order; insertion order in ``out`` is preserved. ``occ`` records the final
    block intended at each (x,y,z) for collision detection + bbox sizing.

    Collision rule (verified poc/45 L106-109, poc/48 L287-292): the guard fires
    ONLY for two DISTINCT non-air blocks. air may overwrite air, air may overwrite
    a non-air block, and a non-air block may overwrite air — none of those raise.
    The poc treats ``'air' in (old,new)`` as a pass; that permissive air rule is
    load-bearing (overlapping air carve-outs around note blocks rely on it).
    """

    def __init__(self):
        self.occ = {}

    def put(self, out, x, y, z, block):
        """Record (x,y,z)->block and append ``setblock x y z block`` to ``out``.
        Raise RedPianoError on a collision between two distinct non-air blocks."""
        key = (x, y, z)
        old = self.occ.get(key)
        if old is not None and old != block and not (_is_air(old) or _is_air(block)):
            raise RedPianoError(f"collision @{key}: {old} vs {block}")
        self.occ[key] = block
        out.append(f"setblock {x} {y} {z} {block}")

    def bbox(self):
        """Return (min_x, min_z, max_x, max_z) over ``occ`` for forceload sizing.
        Raises if the grid is empty (a machine with no blocks is a generator bug)."""
        if not self.occ:
            raise RedPianoError("bbox() on empty grid — no blocks were placed")
        xs = [k[0] for k in self.occ]
        zs = [k[2] for k in self.occ]
        return (min(xs), min(zs), max(xs), max(zs))


# ─────────────────────────────────────────────────────────────────────────────
# §1.3  Sign / button helpers — exactly-4-line ASSERTION
# ─────────────────────────────────────────────────────────────────────────────

def sign_messages(lines):
    """Minecraft signs have exactly 4 lines. Assert 0 < len(lines) <= 4 and pad to
    4 with empty strings, producing the JSON-text-component CSV used in
    oak_sign{front_text:{messages:[...]}} (poc/45 L157). >4 lines -> RedPianoError
    (the poc silently truncates with [:4]; the contract UPGRADES this to a hard
    assert so over-long labels are caught at generation time)."""
    if not (0 < len(lines) <= 4):
        raise RedPianoError(f"sign needs <=4 lines, got {len(lines)}")
    padded = (list(lines) + ["", "", "", ""])[:4]
    return ",".join('\'{"text":"%s"}\'' % s for s in padded)


def labeled_button(bx, y, oz, cmd, lines, lamp="minecraft:redstone_lamp"):
    """Emit the 5-block console widget verbatim from poc/45 ``lbtn`` (L156-162):
    lamp at Y-1,oz; command_block[facing=up]{Command:"<cmd>",auto:0b} at Y,oz;
    stone_button[face=floor] at Y+1,oz; lamp at Y-1,oz-2; oak_sign at Y,oz-2 with
    sign_messages(lines)."""
    msgs = sign_messages(lines)
    return [
        f"setblock {bx} {y - 1} {oz} {lamp}",
        f'setblock {bx} {y} {oz} minecraft:command_block[facing=up,conditional=false]'
        f'{{Command:"{cmd}",auto:0b}}',
        f"setblock {bx} {y + 1} {oz} minecraft:stone_button[face=floor]",
        f"setblock {bx} {y - 1} {oz - 2} {lamp}",
        "setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}"
        % (bx, y, oz - 2, msgs),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# §1.4  Forceload helpers — per-path add + over-threshold guard
# ─────────────────────────────────────────────────────────────────────────────

FORCELOAD_SOFT_CAP = 360  # chunks; above this MC perf/limits degrade


def _chunk_count(x0, z0, x1, z1):
    """((x1//16)-(x0//16)+1) * ((z1//16)-(z0//16)+1) — poc/48 L559 fold_chunks formula.
    Uses floor-division (Python // floors toward -inf), matching the poc on negative
    coordinates."""
    return ((x1 // 16) - (x0 // 16) + 1) * ((z1 // 16) - (z0 // 16) + 1)


def forceload_add_region(x0, z0, x1, z1):
    """A single 'forceload add x0 z0 x1 z1' command."""
    return f"forceload add {x0} {z0} {x1} {z1}"


def forceload_split(x0, z0, x1, z1, max_chunks_per_cmd=240):
    """Walk X in xstep*16 strides so each 'forceload add' stays small, because one
    forceload command is itself chunk-limited (poc/48 L380-388). Returns
    ['forceload remove all', add...]. ``max_chunks_per_cmd`` is the per-command
    chunk budget (poc uses 240)."""
    zc = (z1 // 16) - (z0 // 16) + 1
    xstep = max(1, max_chunks_per_cmd // max(1, zc))
    out = ["forceload remove all"]
    cx = x0
    while cx <= x1:
        cxe = min(x1, cx + xstep * 16 - 1)
        out.append(f"forceload add {cx} {z0} {cxe} {z1}")
        cx = cxe + 1
    return out


def forceload_guard(x0, z0, x1, z1, *, auto_fold=False):
    """Compute the chunk count and guard against oversize forceload regions.

    chunks > FORCELOAD_SOFT_CAP:
      * auto_fold=False (default) -> HARD FAIL RedPianoError.
      * auto_fold=True            -> WARN + forceload_split (safe strides).
    Folding the *geometry* (plane-fold U-turns) is a generator concern; core only
    splits the forceload *command* itself.

    Returns a list of forceload commands (always ['forceload remove all', add...]).
    In-place machines are tiny so they pass trivially with a single add; swave can
    be large.
    """
    chunks = _chunk_count(x0, z0, x1, z1)
    if chunks > FORCELOAD_SOFT_CAP:
        if not auto_fold:
            raise RedPianoError(
                f"forceload {chunks} chunks > {FORCELOAD_SOFT_CAP}; machine too large "
                f"— fold the layout or raise --force-cap"
            )
        log.warning(
            "forceload %d chunks > soft cap %d; auto-folding the forceload command "
            "into safe strides (--force-cap)", chunks, FORCELOAD_SOFT_CAP,
        )
        return forceload_split(x0, z0, x1, z1)
    # within cap: still split for safety on wide regions, but a single add is fine.
    return forceload_split(x0, z0, x1, z1)


# ─────────────────────────────────────────────────────────────────────────────
# §1.5  Multi-instrument map loader + note resolver
# ─────────────────────────────────────────────────────────────────────────────

class Resolved:
    """Result of InstrumentMap.resolve(): the chosen note block, its note value
    (0..24 -> pitch), the sound event ID (for stopsound melody-cut), and the signed
    octave-shift count applied to fit the sample's playable range."""

    __slots__ = ("block", "note_value", "sound_event", "shifted_octaves")

    def __init__(self, block, note_value, sound_event, shifted_octaves):
        self.block = block
        self.note_value = note_value
        self.sound_event = sound_event
        self.shifted_octaves = shifted_octaves

    def __iter__(self):
        # tuple-friendly: (block, note_value, sound_event, shifted_octaves)
        return iter((self.block, self.note_value, self.sound_event,
                     self.shifted_octaves))

    def __repr__(self):
        return (f"Resolved(block={self.block!r}, nv={self.note_value}, "
                f"event={self.sound_event!r}, shift={self.shifted_octaves})")


# sentinel for "could not fit even after octave shifting; clamped as last resort"
OCTAVE_SHIFT_CLAMP_SENTINEL = 99


class InstrumentMap:
    """Loads redpiano_map_multi.json (the 103-block / 5-instrument map, single
    source of truth from the mod's RedPianoMap.java). Provides GM-family routing
    and per-note resolution with the octave-shift upgrade.
    """

    def __init__(self, instruments, family_map, gm_drum_map):
        self.instruments = instruments
        self.family_map = family_map
        self.gm_drum_map = gm_drum_map
        n = self.total_blocks()
        if n != 103:
            raise RedPianoError(
                f"redpiano_map_multi.json has {n} mapped blocks, expected 103 "
                f"(map out of sync with mod RedPianoMap.java?)"
            )

    @classmethod
    def load(cls, path=None):
        """Load the map JSON. Default path is assets/redpiano_map_multi.json
        relative to this file's parent (skill/). family_map / gm_drum_map keys are
        strings in JSON -> cast to int (poc/46 L42-43)."""
        if path is None:
            here = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(here, "..", "assets", "redpiano_map_multi.json")
        if not os.path.isfile(path):
            raise RedPianoError(f"instrument map not found: {path}")
        with open(path, encoding="utf-8") as f:
            mm = json.load(f)
        try:
            instruments = mm["instruments"]
            family_map = {int(k): v for k, v in mm["family_map"].items()}
            gm_drum_map = {int(k): v for k, v in mm["gm_drum_map"].items()}
        except (KeyError, ValueError, AttributeError) as e:
            raise RedPianoError(f"malformed instrument map {path}: {e}")
        return cls(instruments, family_map, gm_drum_map)

    def total_blocks(self):
        """Count mapped blocks across all instruments. MUST equal 103
        (gen_multi_map.py L83-84)."""
        return sum(len(d.get("block", d.get("types", {})))
                   for d in self.instruments.values())

    def family_for(self, program, channel):
        """channel==9 -> 'drum'; else family_map.get(program//8, 'pno') (poc/46 L74)."""
        if channel == 9:
            return "drum"
        return self.family_map.get(program // 8, "pno")

    @staticmethod
    def _layer_for(vel01, instr, available_layers):
        """Velocity layer (poc/45 L71 / poc/46 L57): pno -> p/mf/f by velocity;
        all other instruments forced to mf (or first available layer)."""
        if instr == "pno":
            layer = "p" if vel01 < 0.40 else ("mf" if vel01 < 0.72 else "f")
        else:
            layer = "mf"
        if layer not in available_layers:
            layer = "mf" if "mf" in available_layers else available_layers[0]
        return layer

    def resolve(self, midi, vel01, instr):
        """Resolve a note to (block, note_value, sound_event, shifted_octaves).

        Drums (pitched=False): GM note -> drum type (default 'snare', else first
        available); returns (types[dtype], 12, sound['drum:'+dtype], 0). note_value
        12 -> pitch 1.0, no transpose (poc/46 L49-52).

        Pitched: nearest band, raw = 12 + (midi - band). If raw is in [0,24] the
        note plays at that pitch directly. OCTAVE-SHIFT upgrade (CONTRACT §1.5,
        replaces the poc's silent clamp): if raw < 0 or raw > 24, shift midi by whole
        octaves (+/-12) toward the band's range until 0 <= raw <= 24, preserving pitch
        class, then recompute. Record the signed shift count. If even after shifting
        it cannot fit (band table genuinely too narrow), clamp as a last resort and
        mark shifted_octaves = +/-OCTAVE_SHIFT_CLAMP_SENTINEL. No silent corruption.
        """
        inst = self.instruments[instr]

        # ── drums ────────────────────────────────────────────────────────────
        if not inst["pitched"]:
            dtype = self.gm_drum_map.get(midi, "snare")
            if dtype not in inst["types"]:
                dtype = next(iter(inst["types"]))
            return Resolved(inst["types"][dtype], 12,
                            inst["sound"][f"drum:{dtype}"], 0)

        # ── pitched ──────────────────────────────────────────────────────────
        bands = inst["bands"]
        layers = inst["layers"]

        def nearest_band(m):
            return min(bands, key=lambda b: abs(b - m))

        m = midi
        band = nearest_band(m)
        raw = 12 + (m - band)
        shifted = 0

        if not (0 <= raw <= 24):
            # shift by whole octaves toward the playable range, preserving pitch class.
            # re-pick the nearest band after each shift (the band table is sparse).
            for _ in range(12):  # bounded: MIDI range / 12 is well under 12 iterations
                if raw < 0:
                    m += 12
                    shifted += 1
                elif raw > 24:
                    m -= 12
                    shifted -= 1
                else:
                    break
                band = nearest_band(m)
                raw = 12 + (m - band)
                if 0 <= raw <= 24:
                    break
            if not (0 <= raw <= 24):
                # last resort: clamp pitch, flag with the sentinel so generators WARN.
                clamped_nv = max(0, min(24, raw))
                sign = 1 if raw > 24 else -1
                layer = self._layer_for(vel01, instr, layers)
                key = f"{band}_{layer}"
                return Resolved(inst["block"][key], clamped_nv, inst["sound"][key],
                                sign * OCTAVE_SHIFT_CLAMP_SENTINEL)

        nv = max(0, min(24, raw))  # in-range here; max/min are belt-and-suspenders
        layer = self._layer_for(vel01, instr, layers)
        key = f"{band}_{layer}"
        return Resolved(inst["block"][key], nv, inst["sound"][key], shifted)


# ─────────────────────────────────────────────────────────────────────────────
# §1.6  Melody-cut scheduler helper
# ─────────────────────────────────────────────────────────────────────────────

class MelodyCutPlan:
    """Output of plan_melody_cuts(). Fields per CONTRACT §1.6:
      delays_by_cell:   {cell_tick: cut_delay_gameticks}  (relative-mode, in-place)
      schedule_by_cell: {cell_tick: absolute_schedule_t}  (absolute-mode, swave)
      cut_events:       sorted unique sound events (drives the cutmel body)
      warnings:         list of WARN strings (also emitted via logging.warning)
      median_delay_gt:  median cut delay in game-ticks (report metric)
    """

    __slots__ = ("delays_by_cell", "schedule_by_cell", "cut_events",
                 "warnings", "median_delay_gt")

    def __init__(self, delays_by_cell, schedule_by_cell, cut_events,
                 warnings, median_delay_gt):
        self.delays_by_cell = delays_by_cell
        self.schedule_by_cell = schedule_by_cell
        self.cut_events = cut_events
        self.warnings = warnings
        self.median_delay_gt = median_delay_gt


def plan_melody_cuts(mel_events, *, tps=80, melcap_s=1.2, min_cut_gt=4,
                     offset=0, absolute=False):
    """Plan EVENT-level melody-sustain cuts (CONTRACT §1.6, distilled from
    poc/46 L109-122 and poc/48 L198-210).

    ``mel_events``: list of (cell_tick, midi_dur_s, sound_event). One entry per
    melody cell (the longest cut-instr note in that cell). Cells need not be sorted;
    this function sorts by cell_tick.

    For each melody cell, compute the cut delay in game-ticks::

        d = min(round(midi_dur_s * tps), round(melcap_s * tps))      # cap sustain
        d = min(d, (next_mel_tick - this_tick) * 2 - 1)  if next     # don't overrun next
        d = max(min_cut_gt, d)

    Generation-time ASSERTION: after computing ``d``, the cut floor (min_cut_gt) can
    never push the cut past the next note's onset. If min_cut_gt >= gap_to_next
    (in game-ticks) raise RedPianoError. (The poc relies on the ``-1`` and ``max()``
    ordering but never asserts; the contract makes it explicit.)

    ``absolute=True`` (swave): schedule_by_cell[tick] = (tick + offset) * 2 + d
    (poc/48 L209). ``absolute=False`` (in-place): only delays_by_cell is meaningful
    (relative ``schedule ... cutmel <d>t append``, poc/46 L173).

    Polyphony WARN: the cut is EVENT-level (stopsound @a record <event> kills ALL
    ringing notes sharing that event). For each cut, if MORE THAN ONE melody note of
    the SAME sound_event is still ringing at the cut time (overlapping
    [onset, onset+dur] windows sharing an event), a WARN is emitted — earlier notes
    are silenced prematurely. This is the documented v1 limitation (a true per-note
    cut is out of scope).
    """
    events = sorted(mel_events, key=lambda e: e[0])
    ticks = [e[0] for e in events]
    durs = [e[1] for e in events]
    snds = [e[2] for e in events]

    cap_gt = round(melcap_s * tps)
    delays_by_cell = {}
    schedule_by_cell = {}
    warnings = []

    for j, tk in enumerate(ticks):
        d = min(round(durs[j] * tps), cap_gt)
        if j + 1 < len(ticks):
            gap_gt = (ticks[j + 1] - tk) * 2  # cells -> game-ticks (tick80: *2)
            # cut-floor assertion: the floor can never reach the next onset.
            if min_cut_gt >= gap_gt:
                raise RedPianoError(
                    f"cut_delay floor {min_cut_gt}gt >= gap {gap_gt}gt to next "
                    f"melody note @cell {tk}; notes too dense to cut safely"
                )
            d = min(d, gap_gt - 1)
        d = max(min_cut_gt, d)
        # invariant: d must land strictly before the next onset.
        if j + 1 < len(ticks):
            gap_gt = (ticks[j + 1] - tk) * 2
            assert d < gap_gt, (
                f"internal: cut delay {d} not < gap {gap_gt} @cell {tk}"
            )
        delays_by_cell[tk] = d
        if absolute:
            schedule_by_cell[tk] = (tk + offset) * 2 + d

    # ── polyphony WARN: per cut, detect a same-event note still ringing. ──
    # The cut is EVENT-level: stopsound @a record <event> kills EVERY note of that
    # event that is still sounding. The hazard is when an EARLIER same-event note k
    # is still NATURALLY ringing (its full MIDI duration [onset_k, onset_k+dur_k]
    # has not elapsed) at the moment note j's cut fires — that earlier note gets
    # chopped prematurely by j's cut. Use the natural (uncapped) MIDI duration for
    # the ring window, and the planned cut delay for the cut time. (game-ticks.)
    natural_gt = [round(durs[k] * tps) for k in range(len(ticks))]
    for j, tk in enumerate(ticks):
        ev = snds[j]
        onset_j = tk * 2
        cut_j = onset_j + delays_by_cell[tk]
        overlapping = 0
        for k, tk2 in enumerate(ticks):
            if k == j or snds[k] != ev:
                continue
            onset_k = tk2 * 2
            natural_release_k = onset_k + natural_gt[k]
            # note k (same event) starts before j's cut and is STILL ringing
            # naturally when j's cut fires -> j's event-level cut silences it early.
            if onset_k < cut_j < natural_release_k:
                overlapping += 1
        if overlapping >= 1:
            short = ev.split(":")[-1] if ":" in ev else ev
            msg = (f"event-level cut: {overlapping + 1} overlapping {short} notes "
                   f"share one cut @cell {tk} — earlier note(s) will be silenced "
                   f"prematurely")
            warnings.append(msg)
            log.warning(msg)

    # ── cross-event hazard SUMMARY (honest report, not "0 warnings"). ──
    # The in-game cutmel is GLOBAL: at each scheduled cut it runs `stopsound @a record
    # <ev>` for EVERY cut event, so a still-ringing note of a DIFFERENT event is also
    # silenced. The per-cell WARN above only sees SAME-event overlaps; count the
    # cross-event overlaps too so a polyphonic song doesn't falsely report no hazard.
    cross = 0
    for j, tk in enumerate(ticks):
        cut_j = tk * 2 + delays_by_cell[tk]
        for k, tk2 in enumerate(ticks):
            if k == j or snds[k] == snds[j]:
                continue
            onset_k = tk2 * 2
            if onset_k < cut_j < onset_k + natural_gt[k]:
                cross += 1
    if cross:
        msg = (f"event-level cut is GLOBAL: {cross} cross-instrument note-overlap(s) get "
               f"shortened by the melody-cut (melody stays audible; dense pad/lead/bass "
               f"tails may thin). v1 limitation — per-note cut is out of scope.")
        warnings.append(msg)
        log.warning(msg)

    cut_events = sorted(set(snds))
    if delays_by_cell:
        ds = sorted(delays_by_cell.values())
        median = ds[len(ds) // 2]
    else:
        median = 0
    return MelodyCutPlan(delays_by_cell, schedule_by_cell, cut_events,
                         warnings, median)


# ─────────────────────────────────────────────────────────────────────────────
# §1.7  Tick-rate handling
# ─────────────────────────────────────────────────────────────────────────────

def tickrate_command_block(x, y, z, rate=80, facing="up"):
    """A command_block that runs '/tick rate <rate>' so the machine self-sets tempo
    on use. The machine MUST NOT assume the player typed /tick rate 80 (MEMORY:
    redpiano-runtime-gotchas 'eerie/slow = needs manual /tick rate 80'). Returns the
    setblock command(s) placing an auto-off command block primed with the tick-rate
    command; wire its activation into setup/play."""
    return [
        f'setblock {x} {y} {z} minecraft:command_block[facing={facing},conditional=false]'
        f'{{Command:"tick rate {rate}",auto:0b}}',
    ]

# NOTE: a `tickrate_selfcheck` once lived here but was removed — it could not actually
# detect the rate (gametime advances by 1 per game-tick regardless of /tick rate) and
# spammed a false WARN every tick. The machine instead self-SETS the rate: generators
# place a tickrate_command_block in the console and fire it from `playcore` (pressing
# [play] runs `/tick rate 80` automatically). No per-tick check, no manual typing.


# ─────────────────────────────────────────────────────────────────────────────
# §1.8 (reserved) — radiate/chord/palette/S-wave layout are GEOMETRY -> generators/
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    def expect_raise(fn, needle=None, label=""):
        try:
            fn()
        except RedPianoError as e:
            if needle and needle not in str(e):
                raise AssertionError(f"{label}: wrong message {e!r} (want '{needle}')")
            print(f"  ok (raised): {label} -> {e}")
            return
        raise AssertionError(f"{label}: expected RedPianoError, none raised")

    # ── version profile ──────────────────────────────────────────────────────
    prof = get_version_profile("1.21.8")
    assert prof.dp_format == 81 and prof.rp_format == 64, prof
    assert prof.function_folder == "function" and prof.tag_function_folder == "function"
    print("ok: 1.21.8 profile", prof)
    prof2 = get_version_profile("1.20.4")
    assert prof2.dp_format == 26 and prof2.function_folder == "functions", prof2
    print("ok: 1.20.4 profile (plural folders)", prof2)
    expect_raise(lambda: get_version_profile("9.9.9"),
                 "unknown mc_version", "unknown version")

    # ── collision guard ──────────────────────────────────────────────────────
    g = Grid()
    out = []
    g.put(out, 0, 0, 0, "minecraft:stone")
    g.put(out, 0, 0, 0, "minecraft:air")       # air over non-air: allowed
    g.put(out, 0, 0, 0, "minecraft:stone")     # same block re-place: allowed
    print("ok: air<->nonair operations don't raise")
    expect_raise(lambda: g.put([], 0, 0, 0, "minecraft:dirt"),
                 "collision", "distinct non-air collision")
    assert g.bbox() == (0, 0, 0, 0)
    print("ok: bbox", g.bbox())

    # ── sign 4-line assert ───────────────────────────────────────────────────
    assert sign_messages(["a", "b"]).count("text") == 4
    expect_raise(lambda: sign_messages(["1", "2", "3", "4", "5"]),
                 "sign needs <=4 lines", "over-long sign")
    btn = labeled_button(10, 255, 0, "function ns:play", ["[play]"])
    assert len(btn) == 5 and "command_block" in btn[1]
    print("ok: labeled_button 5 blocks; sign asserts <=4 lines")

    # ── instrument map + octave-shift resolver ───────────────────────────────
    imap = InstrumentMap.load()
    assert imap.total_blocks() == 103
    print("ok: InstrumentMap loaded, 103 blocks")
    # in-range pitched note (pno band 60 = C4-ish): midi 60 -> raw 12
    r = imap.resolve(60, 0.5, "pno")
    assert r.note_value == 12 and r.shifted_octaves == 0, r
    print("ok: in-range resolve", r)
    # out-of-range LOW pitched note forces an octave shift up (not a silent clamp).
    # bass bands 28..52; a very low midi like 4 should shift UP toward the range.
    r_low = imap.resolve(4, 0.5, "bass")
    assert r_low.shifted_octaves > 0, r_low
    assert 0 <= r_low.note_value <= 24, r_low
    print("ok: low note octave-shifted UP (no silent clamp)", r_low)
    # out-of-range HIGH note shifts down.
    r_hi = imap.resolve(120, 0.5, "bass")
    assert r_hi.shifted_octaves < 0 and 0 <= r_hi.note_value <= 24, r_hi
    print("ok: high note octave-shifted DOWN", r_hi)
    # drum: nv=12, no shift, drum event
    rd = imap.resolve(38, 0.9, "drum")
    assert rd.note_value == 12 and rd.shifted_octaves == 0 and "drum" in rd.sound_event
    print("ok: drum resolve", rd)
    # family routing
    assert imap.family_for(0, 0) == "pno" and imap.family_for(33, 9) == "drum"
    assert imap.family_for(33, 0) == "bass"  # program 33 // 8 == 4 -> bass
    print("ok: family routing")

    # ── forceload guard ──────────────────────────────────────────────────────
    fl = forceload_guard(0, 0, 32, 32)  # tiny -> passes
    assert fl[0] == "forceload remove all"
    print("ok: small forceload passes", len(fl), "commands")
    expect_raise(lambda: forceload_guard(0, 0, 16000, 16000),  # huge -> hard fail
                 "too large", "oversize forceload hard-fail")
    fl2 = forceload_guard(0, 0, 16000, 16000, auto_fold=True)  # folds instead
    assert fl2[0] == "forceload remove all" and len(fl2) > 1
    print("ok: oversize forceload auto-folds into", len(fl2), "commands")

    # ── melody-cut plan: relative + absolute + assertion + polyphony WARN ─────
    # two melody cells, sparse -> clean cut
    plan = plan_melody_cuts(
        [(0, 0.5, "qzpno:pad_c2_mf"), (40, 0.5, "qzpno:pad_c2_mf")],
        absolute=False)
    assert 0 in plan.delays_by_cell and 40 in plan.delays_by_cell
    print("ok: relative melody-cut plan", plan.delays_by_cell, "events", plan.cut_events)
    plan_abs = plan_melody_cuts(
        [(0, 0.5, "qzpno:pad_c2_mf"), (40, 0.5, "qzpno:pad_c2_mf")],
        absolute=True, offset=1)
    assert plan_abs.schedule_by_cell[0] == (0 + 1) * 2 + plan_abs.delays_by_cell[0]
    print("ok: absolute melody-cut schedule", plan_abs.schedule_by_cell)
    # too-dense -> cut-floor assertion fires (gap 2 cells -> 4 gt == min_cut_gt 4)
    expect_raise(
        lambda: plan_melody_cuts([(0, 1.0, "e"), (2, 1.0, "e")], min_cut_gt=4),
        "too dense to cut safely", "dense cut-floor assertion")
    # overlapping same-event notes -> polyphony WARN
    plan_ov = plan_melody_cuts(
        [(0, 5.0, "qzpno:pad_c2_mf"), (5, 5.0, "qzpno:pad_c2_mf"),
         (50, 0.3, "qzpno:pad_c2_mf")],
        melcap_s=2.0)
    assert any("overlapping" in w for w in plan_ov.warnings), plan_ov.warnings
    print("ok: polyphony WARN fired ->", plan_ov.warnings[0])

    # ── tick-rate helper (self-SET command block; the broken self-check was removed) ──
    tcb = tickrate_command_block(0, 255, 0)
    assert "tick rate 80" in tcb[0]
    print("ok: tick-rate command-block (machine self-sets the rate on play)")

    # ── Datapack writer (temp dir) ───────────────────────────────────────────
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        dp = Datapack("testns", "Test Song", td, "1.21.8")
        dp.write_pack_mcmeta("test pack")
        dp.write_load_tick_tags()
        dp.write_function("load", build_load_fn("testns", "Test Song"))
        dp.write_function("tick", build_tick_dispatch("testns", 3))
        # profile-driven singular folder for 1.21.8
        assert os.path.isfile(os.path.join(dp.root, "data", "testns", "function", "load.mcfunction"))
        assert os.path.isfile(os.path.join(dp.root, "data", "minecraft", "tags", "function", "load.json"))
        meta = json.load(open(os.path.join(dp.root, "pack.mcmeta")))
        assert meta["pack"]["pack_format"] == 81
        print("ok: Datapack writes profile-driven singular folders + dp_format 81")
        # pre-1.21 -> plural folders
        dp2 = Datapack("oldns", "Old", td, "1.20.4")
        dp2.write_load_tick_tags()
        dp2.write_function("load", ["say hi"])
        assert os.path.isfile(os.path.join(dp2.root, "data", "oldns", "functions", "load.mcfunction"))
        assert os.path.isfile(os.path.join(dp2.root, "data", "minecraft", "tags", "functions", "load.json"))
        print("ok: pre-1.21 Datapack writes PLURAL folders")

    print("redpiano_core self-test PASSED")
