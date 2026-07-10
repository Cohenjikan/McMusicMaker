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
import re
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

# Global timing constants — the qzpno samples are tuned for `/tick rate 80`, where
# one redstone-tick cell = 2 game-ticks (U = 2/80 = 0.025s). These are INVARIANT
# across the supported band (1.21..1.21.10 all run the same sample set at tick80), so
# they live here as the single source of truth and are surfaced on every
# VersionProfile. They are only *usable* when profile.has_tick_rate (>=1.20.3) — which
# get_version_profile enforces, refusing any version below that floor.
TPS = 80                    # the /tick rate target the samples are tuned for
GAME_TICKS_PER_CELL = 2     # 1 redstone-tick cell = 2 game-ticks at tick80


def _vrow(dp, rp, folder, packmeta, sign, has_tick, tier, conf, notes=""):
    """Build a VERSION_TABLE row. ``has_return_cmd`` shares the /tick rate floor
    (both `/tick rate` and `return`/`return run` landed in 1.20.3), so it is derived
    from ``has_tick``."""
    return {
        "dp_format": dp, "rp_format": rp, "function_folder": folder,
        "packmeta_shape": packmeta, "sign_dialect": sign,
        "has_tick_rate": has_tick, "has_return_cmd": has_tick,
        "tier": tier, "confidence": conf, "notes": notes,
    }


# §3 / §1.9  VERSION_TABLE — the SINGLE SOURCE OF TRUTH for every per-MC-version fact
# the datapack/resourcepack layer needs. (Mod-jar toolchain numbers live separately in
# mod_build.py, since the mod is recompiled out-of-band.) All dp/rp numbers are
# cross-verified against https://minecraft.wiki/w/Pack_format (high confidence).
# Anchored row: MC 1.21.8 -> dp=81, rp=64 (user-verified in-game).
#
# Row fields (see _vrow):
#   dp_format / rp_format  datapack / resourcepack pack_format integers (DIFFERENT lines)
#   function_folder        'function' (>=1.21, format-48 rename) | 'functions' (<=1.20.6)
#   packmeta_shape         'single' (<=1.21.8) | 'minmax' (>=1.21.9 / 25w31a: pack.mcmeta
#                          uses min_format/max_format; a single pack_format is silently
#                          disabled by MC there)
#   sign_dialect           'component_string' (1.20..1.21.4: messages are JSON-text STRINGS)
#                          'component_snbt'   (>=1.21.5: messages are SNBT COMPOUNDS, not
#                          strings — the old form renders as literal text on the sign)
#   has_tick_rate          /tick rate exists (>=1.20.3); False => tick80 model impossible
#                          => get_version_profile HARD-REFUSES (the honest floor)
#   tier                   'green'  fully auto (1.21..1.21.10): data + resourcepack + mod
#                                   (number-only recompile)
#                          'yellow' data/resourcepack auto, but the mod needs a Java
#                                   source-port (<1.21 scoreboard API) — OUT OF auto scope
#                          'red'    below the tick-rate floor (<=1.20.2) — refused
VERSION_TABLE = {
    # ── red: below the /tick rate floor (1.20.3). Present only so the refusal can
    #    name the real reason instead of a generic "unknown version". ──
    "1.20":    _vrow(15, 15, "functions", "single", "component_string", False, "red", "high",
                     "no /tick rate (added 1.20.3) -> the tick80 timing model is impossible"),
    "1.20.1":  _vrow(15, 15, "functions", "single", "component_string", False, "red", "high",
                     "see 1.20 (below the /tick rate floor)"),
    "1.20.2":  _vrow(18, 18, "functions", "single", "component_string", False, "red", "high",
                     "see 1.20 (below the /tick rate floor)"),
    # ── yellow: data adapts, but the mod needs a <1.21 scoreboard source-port. ──
    "1.20.3":  _vrow(26, 22, "functions", "single", "component_string", True,  "yellow", "high",
                     "the /tick rate floor; datapack OK but the mod needs a scoreboard source-port"),
    "1.20.4":  _vrow(26, 22, "functions", "single", "component_string", True,  "yellow", "high",
                     "plural folders functions/, tags/functions/; mod needs scoreboard port + Java 17"),
    "1.20.5":  _vrow(41, 32, "functions", "single", "component_string", True,  "yellow", "high",
                     "mod needs a <1.21 scoreboard source-port"),
    "1.20.6":  _vrow(41, 32, "functions", "single", "component_string", True,  "yellow", "high",
                     "mod needs a <1.21 scoreboard source-port"),
    # ── green: fully auto. Singular function/ folder (format-48 rename at 1.21). ──
    "1.21":    _vrow(48, 34, "function",  "single", "component_string", True,  "green", "high",
                     "24w21a/format 48: folders renamed to SINGULAR function/, tags/function/, etc."),
    "1.21.1":  _vrow(48, 34, "function",  "single", "component_string", True,  "green", "high", "same as 1.21"),
    "1.21.2":  _vrow(57, 42, "function",  "single", "component_string", True,  "green", "high", ""),
    "1.21.3":  _vrow(57, 42, "function",  "single", "component_string", True,  "green", "high", ""),
    "1.21.4":  _vrow(61, 46, "function",  "single", "component_string", True,  "green", "high",
                     "LAST version using JSON-string sign text components (1.21.5 -> SNBT)"),
    "1.21.5":  _vrow(71, 55, "function",  "single", "component_snbt",   True,  "green", "high",
                     "text components became SNBT compounds in NBT -> sign dialect flips here"),
    "1.21.6":  _vrow(80, 63, "function",  "single", "component_snbt",   True,  "green", "high", ""),
    "1.21.7":  _vrow(81, 64, "function",  "single", "component_snbt",   True,  "green", "high",
                     "last release using a single pack_format (1.21.9 -> min/max)"),
    "1.21.8":  _vrow(81, 64, "function",  "single", "component_snbt",   True,  "green", "high",
                     "ANCHORED: user-verified in-game; dp 81 / rp 64. Verified default."),
    "1.21.9":  _vrow(88, 69, "function",  "minmax", "component_snbt",   True,  "green", "high",
                     "25w31a: pack.mcmeta uses min_format/max_format (single pack_format disabled). "
                     "dp 88 / rp 69 (verified)."),
    "1.21.10": _vrow(88, 69, "function",  "minmax", "component_snbt",   True,  "green", "high",
                     "non-breaking after 1.21.9; same major format dp 88 / rp 69 (minor-versioned "
                     "pack formats introduced 1.21.9). min/max emission identical to 1.21.9."),
}


class VersionProfile:
    """Resolved per-MC-version facts. Single source of truth for pack_format numbers,
    the 1.21 plural->singular folder rename, the pack.mcmeta shape (single vs min/max),
    the sign-NBT dialect, the tick-rate/timing capability, and the support tier."""

    __slots__ = ("mc_version", "dp_format", "rp_format", "function_folder",
                 "tag_function_folder", "packmeta_shape", "sign_dialect",
                 "has_tick_rate", "has_return_cmd", "tier", "tps",
                 "game_ticks_per_cell", "confidence", "notes")

    def __init__(self, mc_version, row):
        self.mc_version = mc_version
        self.dp_format = row["dp_format"]
        self.rp_format = row["rp_format"]
        self.function_folder = row["function_folder"]
        # the tags/<x>/ segment follows the same singular/plural rename
        self.tag_function_folder = row["function_folder"]
        self.packmeta_shape = row["packmeta_shape"]
        self.sign_dialect = row["sign_dialect"]
        self.has_tick_rate = row["has_tick_rate"]
        self.has_return_cmd = row["has_return_cmd"]
        self.tier = row["tier"]
        self.tps = TPS
        self.game_ticks_per_cell = GAME_TICKS_PER_CELL
        self.confidence = row["confidence"]
        self.notes = row["notes"]

    @property
    def uses_minmax(self):
        """1.21.9+ (25w31a) uses pack.mcmeta min_format/max_format; a single
        pack_format is silently disabled there. Now fully emitted (write_pack_mcmeta)."""
        return self.packmeta_shape == "minmax"

    def __repr__(self):
        return (f"VersionProfile({self.mc_version}, dp={self.dp_format}, "
                f"rp={self.rp_format}, folder={self.function_folder!r}, "
                f"packmeta={self.packmeta_shape}, sign={self.sign_dialect}, "
                f"tier={self.tier}, conf={self.confidence})")


def get_version_profile(mc_version):
    """The ONLY accessor for pack_format / folder / dialect facts. Pure fact-resolver
    (CONTRACT §1.9): never guesses. RAISES on an unknown version, and on any version
    below the /tick rate floor (<=1.20.2, has_tick_rate=False) where the tick80 timing
    model cannot work. Resolving SUCCEEDS for every known buildable version including
    the 'yellow' 1.20.3..1.20.6 band — the green-band *build policy* is enforced
    separately by assert_build_supported(), so these facts stay queryable (e.g. for the
    plural-folder rename) without implying the mod exists there."""
    # Tolerate stray surrounding whitespace (e.g. a trailing space from a copy-paste or a
    # shell-quoted "1.21.8 "): a bare VERSION_TABLE lookup would otherwise miss and raise
    # "unknown version" for what is really a valid version with an extra space.
    if mc_version is not None:
        mc_version = str(mc_version).strip()
    row = VERSION_TABLE.get(mc_version)
    if row is None:
        raise RedPianoError(
            f"unknown mc_version {mc_version}; add it to VERSION_TABLE "
            f"(source dp/rp format from https://minecraft.wiki/w/Pack_format). "
            f"若确认版本在支持列表里，检查输入是否带多余空格。 "
            f"Auto-build doesn't know this version, but the skill can still help: "
            f"read docs/VERSION_TACTICS.md and take the craftsman path (plan/build/"
            f"verify it yourself for a single delivery)."
        )
    if not row["has_tick_rate"]:
        # The hard floor: no /tick rate (added 1.20.3) -> the game is locked at 20 TPS
        # and the samples are tuned for tick80, so playback is 4x too slow with the
        # repeater geometry physically baked at 0.025s/cell. Not a config knob — refuse.
        raise RedPianoError(
            f"mc_version {mc_version} predates the /tick rate command (added 1.20.3) and "
            f"`return` control flow; the RedPiano timing model runs the game at {TPS} TPS "
            f"and the samples are tuned for it, so on {mc_version} playback would be "
            f"{TPS // 20}x too slow with no way to correct it. 1.20.3 is the hard floor "
            f"for AUTO-build — but the skill can still help: read docs/VERSION_TACTICS.md "
            f"(§2.C offers Carpet-mod /tick rate to recover tick80, or a tick20/vanilla-"
            f"timbre downgrade) and take the craftsman path, or use 1.21.8 for the auto path."
        )
    if row["confidence"] == "low":
        log.warning("mc_version %s has LOW-confidence format data: %s",
                    mc_version, row["notes"])
    return VersionProfile(mc_version, row)


def assert_build_supported(profile):
    """Enforce the skill's supported auto-build band (green = 1.21..1.21.10). 'yellow'
    versions (1.20.3..1.20.6) resolve their datapack facts fine, but the RedPiano mod
    is NOT auto-supported below 1.21 (the scoreboard config API changed; it needs a
    small Java source-port + Java 17), so refuse cleanly rather than hand out a
    datapack with no mod behind it. To opt into yellow: port + recompile the mod (see
    docs/MOD_ARCHITECTURE.md §6) and relax this guard. 'red' is already refused upstream
    in get_version_profile (the /tick rate floor)."""
    if profile.tier == "yellow":
        raise RedPianoError(
            f"mc_version {profile.mc_version} is in the 'yellow' band: the datapack and "
            f"resourcepack adapt automatically, but the RedPiano mod is not auto-supported "
            f"below 1.21 (the scoreboard config API changed; it needs a small Java "
            f"source-port + Java 17). This skill's supported auto range is 1.21..1.21.10 — "
            f"use a 1.21.x version, or port+recompile the mod per docs/MOD_ARCHITECTURE.md "
            f"§6 and remove this guard. Auto-build doesn't support this version, but the "
            f"skill can still help: read docs/VERSION_TACTICS.md (§2.B is exactly this "
            f"1.20.3..1.20.6 band) and take the craftsman path."
        )


# ─────────────────────────────────────────────────────────────────────────────
# §1.0  Namespace validation + path-containment guard (destructive-op safety)
#   ns flows into os.path.join + shutil.rmtree in three places (Datapack.__init__,
#   Datapack.deploy, deploy_bundle.install_now). An unvalidated ns is a directory-
#   traversal hole: '../..' or an absolute path escapes the build dir and rmtree
#   deletes outside it (up to saves/). validate_namespace closes it at the source;
#   _assert_subpath is defense-in-depth in case the regex is ever loosened.
# ─────────────────────────────────────────────────────────────────────────────

def validate_namespace(ns):
    """Assert ``ns`` is a safe datapack namespace / scoreboard objective name.

    Rule: ``re.fullmatch(r"[a-z0-9_-]+")``, non-empty. Minecraft itself also permits
    ``.`` in a namespace, but ``.`` is DELIBERATELY excluded: it would let ``..``
    through, and ns is joined into a filesystem path that later gets rmtree'd — a
    ``../..`` or absolute ns could delete outside the build dir (worst case saves/).
    The narrow rule also fails loud instead of silently emitting a datapack whose
    namespace / scoreboard objective MC rejects at load (uppercase / CJK / dots =>
    a pack that installs but never plays). Raises RedPianoError on violation."""
    if not ns or not re.fullmatch(r"[a-z0-9_-]+", ns):
        raise RedPianoError(
            f"非法命名空间 namespace={ns!r}: 必须非空且只含 [a-z0-9_-]+ —— 它同时是数据包 "
            f"namespace 和 scoreboard objective 名。刻意排除点号 '.'(MC 允许，但会放行 "
            f"'..' 让 ns 拼进随后 rmtree 的路径越界删除，最坏删到 saves/);且大写/中文/点号 "
            f"这类非法 ns 即便不越界，也会静默产出一个进游戏加载失败、永远不响的坏数据包。"
        )


def _assert_subpath(child, base, what):
    """Assert ``child`` resolves strictly inside ``base`` before a rmtree/copytree
    touches it. Defense-in-depth behind validate_namespace: if the ns regex is ever
    loosened this still refuses an escape. Windows: normcase folds case + separators;
    commonpath raises ValueError across different drives — treat that (and any
    non-containment, and child == base) as an escape."""
    a_child = os.path.normcase(os.path.abspath(child))
    a_base = os.path.normcase(os.path.abspath(base))
    try:
        common = os.path.commonpath([a_child, a_base])
    except ValueError:
        common = None
    if common != a_base or a_child == a_base:
        raise RedPianoError(
            f"路径越界防线: {what} 解析到 {os.path.abspath(child)!r},不在 base "
            f"{os.path.abspath(base)!r} 之内 —— 拒绝对 base 之外(或 base 本身)做破坏性操作。"
        )


# ─────────────────────────────────────────────────────────────────────────────
# §1.1  Datapack writer + lifecycle
# ─────────────────────────────────────────────────────────────────────────────

class Datapack:
    """Datapack tree writer. Resolves a VersionProfile at construction and uses
    it for ALL pack_format numbers + folder names (the ONLY place the 1.21
    plural->singular rename is honored). Mirrors the poc ``w()`` / ``wf()``
    semantics byte-for-byte, but profile-driven instead of hardcoded.
    """

    def __init__(self, ns, name, out_dir, mc_version, direction="+X", ox=0, oz=0):
        # MUST precede any path build / rmtree below: a bad ns is a traversal hole.
        validate_namespace(ns)
        self.ns = ns
        self.name = name
        self.mc_version = mc_version
        self.profile = get_version_profile(mc_version)
        self.dp_format = self.profile.dp_format
        self.function_folder = self.profile.function_folder
        self.tag_function_folder = self.profile.tag_function_folder
        # play direction: '+X' (identity, verified path) or '-X'/'+Z'/'-Z' (rotate emitted
        # commands around (ox,oz) — §1.8). ox/oz are the machine origin's X/Z.
        self.direction = direction or "+X"
        self.ox = int(ox)
        self.oz = int(oz)
        self.root = os.path.join(out_dir, ns)
        _assert_subpath(self.root, out_dir, "datapack root")
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
        # rotate the emitted geometry for a non-+X play direction (§1.8). +X is a no-op.
        if self.direction != "+X":
            body = "\n".join(rotate_command(line, self.direction, self.ox, self.oz)
                             for line in body.split("\n"))
        self.write(f"data/{self.ns}/{self.function_folder}/{name}.mcfunction", body)

    def write_pack_mcmeta(self, description):
        """Write pack.mcmeta with the profile's dp_format (NEVER hardcoded 81),
        indent=2 (poc/45 L135). The SHAPE is profile-driven: <=1.21.8 use a single
        `pack_format`; >=1.21.9 (25w31a) use `min_format`/`max_format` (a single
        pack_format is silently disabled by MC there -> total silence)."""
        if self.profile.packmeta_shape == "minmax":
            # 1.21.9+: single pack_format is rejected; emit min/max (same number for
            # both, = support exactly this format). description first to mirror the
            # 1.21.9 pack.mcmeta example shape.
            meta = {"pack": {"description": description,
                             "min_format": self.dp_format,
                             "max_format": self.dp_format}}
        else:
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
        _assert_subpath(dst, world_datapacks_dir, "world datapack dir")
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


def build_load_fn(ns, name, extra_objectives=True, remove_region=None):
    """The `load` function body (poc/45 L171-174): add objectives, BLD=-1, the
    PLAY/LOOP reset, rpcfg poly/human=1, a SCOPED forceload remove, schedule clear
    done, and the loaded tellraw. ``extra_objectives`` toggles the rpcfg block.

    ``remove_region`` = (x0, z0, x1, z1): the machine's own bounding box. ``load`` runs
    on every /reload, so it MUST NOT撤销 a co-existing song's forceload — the remove is
    scoped to this machine's bbox. When None (e.g. the self-test), the remove is omitted
    entirely (still never 'remove all')."""
    out = [
        f"scoreboard objectives add {ns} dummy",
        f"scoreboard players set BLD {ns} -1",
    ]
    out += scoreboard_reset(ns)
    if extra_objectives:
        out += [
            "scoreboard objectives add rpcfg dummy",
            f"scoreboard players set poly_{ns} rpcfg 1",
            f"scoreboard players set human_{ns} rpcfg 1",
        ]
    # ``name`` is user-controlled (--song / MIDI filename) and may contain " or \\;
    # build the tellraw payload as a dict and json.dumps it so the text is escaped and
    # the emitted command is always valid JSON. json.dumps(name)[1:-1] yields the
    # escaped body without its surrounding quotes for inline interpolation.
    esc_name = json.dumps(name)[1:-1]
    if remove_region is not None:
        out.append(forceload_remove_region(*remove_region))
    out += [
        f"schedule clear {ns}:done",
        f'tellraw @a ["",{{"text":"[{ns}] {esc_name} loaded. ","color":"aqua"}},'
        f'{{"text":"need RedPiano mod + qzpno pack. Steps: /tick rate 80 (手动输入) -> /function {ns}:setup -> 启用资源包 -> press [play]."}}]',
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

def sign_messages(lines, dialect="component_string"):
    """Minecraft signs have exactly 4 lines. Assert 0 < len(lines) <= 4 and pad to 4
    with empty strings, producing the per-line text-component CSV used inside
    oak_sign{front_text:{messages:[...]}} (poc/45 L157). >4 lines -> RedPianoError
    (the poc silently truncated with [:4]; the contract UPGRADES this to a hard assert).

    The serialization of each entry is VERSION-DEPENDENT (the profile.sign_dialect
    field — see VERSION_TABLE):

      'component_string'  (MC 1.20 .. 1.21.4): each entry is a JSON-text STRING,
                          e.g.  '{"text":"hi"}'  — wrapped in single quotes so it is an
                          SNBT string whose contents are parsed as a JSON component.
      'component_snbt'    (MC >= 1.21.5): text components became NBT, so each entry is an
                          SNBT COMPOUND, e.g.  {"text":"hi"}  (NO wrapping quotes). On
                          1.21.5+ the old quoted form renders as LITERAL text on the sign
                          (a cosmetic bug), so the dialect MUST flip at 1.21.5.

    Generators pass profile.sign_dialect; the default keeps the historical 1.20..1.21.4
    string form for any caller that does not (e.g. the self-test)."""
    if not (0 < len(lines) <= 4):
        raise RedPianoError(f"sign needs <=4 lines, got {len(lines)}")
    padded = (list(lines) + ["", "", "", ""])[:4]
    # Line text may be user-controlled (e.g. a song name) or a CJK literal (e.g. [播放]);
    # build the JSON-component body with json.dumps(..., ensure_ascii=False) so a `"`/`\\`
    # inside the text is JSON-escaped but CJK stays literal. `[1:-1]` drops the surrounding
    # quotes json.dumps adds. ensure_ascii=True would emit \uXXXX, which is a LEGAL escape in
    # the >=1.21.5 SNBT-double-quote dialect but ILLEGAL in the <=1.21.4 single-quoted SNBT
    # string wrapper (brigadier readStringUntil only accepts \' and \\), so the whole
    # setblock would fail to parse in-game. Keep it literal to stay valid in BOTH dialects.
    def _jbody(s):
        return json.dumps(s, ensure_ascii=False)[1:-1]
    if dialect == "component_snbt":
        # >=1.21.5: SNBT compound entries — {"text":"..."} with no wrapping quotes. This SNBT
        # dialect (double-quoted) accepts \" and \\, which is exactly the JSON escape set the
        # body already carries, so the JSON-escaped body is used verbatim.
        return ",".join('{"text":"%s"}' % _jbody(s) for s in padded)
    if dialect == "component_string":
        # 1.20..1.21.4: JSON-text string entries — '{"text":"..."}'. The whole entry is a
        # single-quoted SNBT string whose contents are then parsed as JSON. That outer SNBT
        # layer only understands \\ and \' escapes, so the (already JSON-escaped) body must be
        # SNBT-escaped: backslash FIRST (so JSON's own \\ / \" backslashes are doubled), then
        # single quotes. This keeps the inner JSON intact after the SNBT layer decodes it.
        def _snbt_wrap(body):
            return body.replace("\\", "\\\\").replace("'", "\\'")
        return ",".join('\'{"text":"%s"}\'' % _snbt_wrap(_jbody(s))
                        for s in padded)
    raise RedPianoError(
        f"unknown sign dialect {dialect!r} (expected 'component_string' for 1.20..1.21.4 "
        f"or 'component_snbt' for >=1.21.5; legacy <1.20 signs are below the tick-rate floor)"
    )


def labeled_button(bx, y, oz, cmd, lines, *, sign_dialect="component_string",
                   lamp="minecraft:redstone_lamp"):
    """Emit the 5-block console widget verbatim from poc/45 ``lbtn`` (L156-162):
    lamp at Y-1,oz; command_block[facing=up]{Command:"<cmd>",auto:0b} at Y,oz;
    stone_button[face=floor] at Y+1,oz; lamp at Y-1,oz-2; oak_sign at Y,oz-2 with
    sign_messages(lines). ``sign_dialect`` (profile.sign_dialect) selects the sign-NBT
    serialization so console signs render correctly on the target version (string form
    1.20..1.21.4, SNBT-compound form >=1.21.5)."""
    msgs = sign_messages(lines, sign_dialect)
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


def forceload_remove_region(x0, z0, x1, z1):
    """A single SCOPED 'forceload remove x0 z0 x1 z1' command.

    NEVER emit 'forceload remove all' — it is a GLOBAL command that would撤销 a
    *second* song's forceload in the same world (co-existing machines互杀: the
    first song's chunks stop being kept loaded, so it goes silent when the player
    walks away; every /reload re-triggers it). Removing only THIS machine's own
    bounding box leaves any other machine's forceload intact. The region passed
    here MUST match the region that forceload_split/guard ADD, so remove+add stay
    paired per machine."""
    return f"forceload remove {x0} {z0} {x1} {z1}"


def forceload_split(x0, z0, x1, z1, max_chunks_per_cmd=240):
    """Tile the region into a 2D grid of sub-regions so each 'forceload add' stays under
    ``max_chunks_per_cmd`` chunks, because one forceload command is itself chunk-limited
    (poc/48 L380-388). Returns ['forceload remove <bbox>', add...] — a SCOPED remove of
    exactly this machine's bounding box (NOT 'remove all', which would撤销 a co-existing
    song's forceload). budget 240 per add.

    The X stride is sized to fit the full Z span in one row; but when the Z span ALONE
    already exceeds the budget, that leaves an X stride of 1 column whose per-command
    chunk count is still (1 * zc) > budget. So Z is split into strides too — a full 2D
    tiling — guaranteeing every emitted add is <= budget regardless of aspect ratio."""
    zc = (z1 // 16) - (z0 // 16) + 1
    # X columns per command, then Z rows per command within that column width. When the
    # Z span fits the budget, zstep spans all of Z (single row per column, unchanged
    # behavior); when Z alone is oversize, xstep collapses to 1 and zstep bounds each add.
    xstep = max(1, max_chunks_per_cmd // max(1, zc))
    zstep = max(1, max_chunks_per_cmd // max(1, min(xstep, zc)))
    # SCOPED remove of exactly this machine's bbox (paired with the adds below) — never
    # 'remove all', which would撤销 a co-existing song's forceload in the same world.
    out = [forceload_remove_region(x0, z0, x1, z1)]
    # Each stride's END must land on a chunk boundary, else an unaligned origin makes
    # adjacent strides START mid-chunk and CO-COUNT the shared boundary chunk-row/column:
    # the per-command chunk count then EXCEEDS the budget (measured 482 > 240 at x0=z0=100)
    # and strides OVERLAP. Snap each end to the last block of the (aligned) chunk `step`
    # chunks forward: end = ((c//16)+step)*16 - 1, clamped to the region. The next stride
    # resumes at end+1, which is exactly the next chunk's first block (aligned). Chunk-aligned
    # origins are unaffected (the snap coincides with the old cx+step*16-1).
    cx = x0
    while cx <= x1:
        cxe = min(x1, ((cx // 16) + xstep) * 16 - 1)
        cz = z0
        while cz <= z1:
            cze = min(z1, ((cz // 16) + zstep) * 16 - 1)
            out.append(f"forceload add {cx} {cz} {cxe} {cze}")
            cz = cze + 1
        cx = cxe + 1
    return out


def forceload_guard(x0, z0, x1, z1, *, auto_fold=False):
    """Compute the chunk count and guard against oversize forceload regions.

    chunks > FORCELOAD_SOFT_CAP:
      * auto_fold=False (default) -> HARD FAIL RedPianoError.
      * auto_fold=True            -> WARN + forceload_split (safe strides).
    Folding the *geometry* (plane-fold U-turns) is a generator concern; core only
    splits the forceload *command* itself.

    Returns a list of forceload commands (always ['forceload remove <bbox>', add...] —
    the remove is SCOPED to this machine's bbox, never 'remove all', so a co-existing
    song's forceload survives). In-place machines are tiny so they pass trivially with a
    single add; swave can be large.
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
            msg = (f"event-level cut: {overlapping + 1} overlapping {short} notes share one "
                   f"cut @cell {tk} — an earlier tail MAY be shortened slightly (a sustaining "
                   f"pad/lead/bass tail; usually INAUDIBLE — user-tested no audible note loss)")
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
        msg = (f"event-level cut is GLOBAL: {cross} cross-instrument tail-overlap(s) MAY be "
               f"trimmed by the melody-cut (the melody always stays audible; only dense "
               f"pad/lead/bass tails are affected, and user-testing found this INAUDIBLE — no "
               f"dropped notes). Informational, not a defect — per-note cut is out of v1 scope.")
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

# The machine does NOT auto-set the tick rate. An auto command-block that ran
# `/tick rate {rate}` (and an even older per-tick `tickrate_selfcheck`) were BOTH removed:
# the self-check could not detect the rate (gametime advances 1/game-tick regardless of
# /tick rate), and the auto command-block proved unreliable in-game (user-tested: the
# auto-set didn't take). Policy: the PLAYER types `/tick rate 80` MANUALLY before playing.
# Generators must NOT emit a tick-rate command block; the in-game instructions say so.


# ─────────────────────────────────────────────────────────────────────────────
# §1.8  Direction rotation — play the +X-authored machine along -X / +Z / -Z.
#   The generators author geometry along +X. To support the other three cardinals we
#   rotate the EMITTED commands around the origin (a rigid transform): rotate the (x,z)
#   integer coords in setblock/forceload/tp, and remap directional blockstates
#   (repeater/observer/... `facing=`, sign `rotation=`). +X is the IDENTITY (the verified
#   path stays byte-for-byte unchanged). Generation-verified (round-trips, collision-free);
#   the non-+X facings bind to in-world redstone, so a new direction needs an in-game listen.
# ─────────────────────────────────────────────────────────────────────────────

_FACING_CW = {"north": "east", "east": "south", "south": "west", "west": "north"}  # 90° CW
_DIR_TURNS = {"+X": 0, "+Z": 1, "-X": 2, "-Z": 3}  # quarter-turns CW from +X
# block-edit regex: name[states]rest  (states may be empty)
_BLOCK_STATE_RE = re.compile(r"^([^\[\]]+)\[([^\]]*)\](.*)$")


def rot_xz(x, z, direction, ox, oz):
    """Rotate point (x,z) around (ox,oz) so a +X-extending machine extends ``direction``.
    +X is identity. (+Z=90° CW, -X=180°, -Z=90° CCW.)"""
    dx, dz = x - ox, z - oz
    if direction == "+X":
        return x, z
    if direction == "+Z":
        return ox - dz, oz + dx
    if direction == "-X":
        return ox - dx, oz - dz
    if direction == "-Z":
        return ox + dz, oz - dx
    raise RedPianoError(f"unknown direction {direction!r} (expected +X/-X/+Z/-Z)")


def _remap_state_token(token, turns):
    """Rotate a single blockstate token (`facing=west`, `rotation=3`) `turns` quarter-CW."""
    if "=" not in token:
        return token
    k, v = token.split("=", 1)
    if k == "facing" and v in _FACING_CW:
        for _ in range(turns):
            v = _FACING_CW[v]
        return f"{k}={v}"
    if k == "rotation":
        try:
            return f"{k}={(int(v) + 4 * turns) % 16}"
        except ValueError:
            return token
    return token


def _rotate_block_states(block, turns):
    """Rewrite `facing=`/`rotation=` inside a block's [..] state list for `turns` CW."""
    m = _BLOCK_STATE_RE.match(block)
    if not m or turns == 0:
        return block
    name, states, rest = m.group(1), m.group(2), m.group(3)
    if not states:
        return block
    new = ",".join(_remap_state_token(t.strip(), turns) for t in states.split(","))
    return f"{name}[{new}]{rest}"


def rotate_command(cmd, direction, ox, oz):
    """Rotate one datapack command's geometry for a non-+X play direction. ``direction``
    == '+X' returns ``cmd`` unchanged (identity). Otherwise rotates the integer (x,z) coords
    in setblock / fill / forceload add/remove / tp around (ox,oz) and remaps facing/rotation
    blockstates. ``fill`` carries TWO absolute corner points (x0 y0 z0 x1 y1 z1); both are
    rotated independently — a rigid rotation maps a box to a box, so any corner ordering is
    fine and no re-sort is needed. ``execute (if|unless) loaded X Y Z run <tail>`` rotates the
    loaded probe coords AND recurses into <tail> (which may itself be a setblock/tp, or a
    coordinate-free tellraw/return that recursion returns verbatim). Commands without rotatable
    integer coords (relative `~`, selectors, scoreboard, tellraw) pass through verbatim."""
    if direction == "+X":
        return cmd
    turns = _DIR_TURNS.get(direction)
    if turns is None:
        raise RedPianoError(f"unknown direction {direction!r} (expected +X/-X/+Z/-Z)")
    parts = cmd.split(" ")
    head = parts[0]
    try:
        # `execute (if|unless) loaded X Y Z run <tail>` — rotate the loaded coords, then
        # recurse into <tail> so a nested setblock/tp is rotated too (a coordinate-free
        # tail like `return run tellraw ...` recurses to an unchanged verbatim string).
        if (head == "execute" and len(parts) >= 8
                and parts[1] in ("if", "unless") and parts[2] == "loaded"
                and parts[6] == "run"):
            x, y, z = int(parts[3]), int(parts[4]), int(parts[5])
            nx, nz = rot_xz(x, z, direction, ox, oz)
            tail = rotate_command(" ".join(parts[7:]), direction, ox, oz)
            return f"execute {parts[1]} loaded {nx} {y} {nz} run {tail}"
        if head == "setblock" and len(parts) >= 5:
            x, y, z = int(parts[1]), int(parts[2]), int(parts[3])
            nx, nz = rot_xz(x, z, direction, ox, oz)
            block = _rotate_block_states(" ".join(parts[4:]), turns)
            return f"setblock {nx} {y} {nz} {block}"
        if head == "fill" and len(parts) >= 7:
            x0, y0, z0 = int(parts[1]), int(parts[2]), int(parts[3])
            x1, y1, z1 = int(parts[4]), int(parts[5]), int(parts[6])
            nx0, nz0 = rot_xz(x0, z0, direction, ox, oz)
            nx1, nz1 = rot_xz(x1, z1, direction, ox, oz)
            rest = " ".join(parts[7:])
            if rest:
                rest = " " + _rotate_block_states(rest, turns)
            return f"fill {nx0} {y0} {nz0} {nx1} {y1} {nz1}{rest}"
        if head == "forceload" and len(parts) >= 4 and parts[1] in ("add", "remove"):
            action = parts[1]
            x1, z1 = int(parts[2]), int(parts[3])
            nx1, nz1 = rot_xz(x1, z1, direction, ox, oz)
            if len(parts) >= 6:
                x2, z2 = int(parts[4]), int(parts[5])
                nx2, nz2 = rot_xz(x2, z2, direction, ox, oz)
                return f"forceload {action} {nx1} {nz1} {nx2} {nz2}"
            return f"forceload {action} {nx1} {nz1}"
        if head == "tp" and len(parts) >= 5:
            x, y, z = int(parts[2]), int(parts[3]), int(parts[4])
            nx, nz = rot_xz(x, z, direction, ox, oz)
            return f"tp {parts[1]} {nx} {y} {nz}"
    except (ValueError, IndexError):
        return cmd  # non-integer coords (relative/selector) -> leave verbatim
    return cmd


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

    # ── version profile (single source of truth) ─────────────────────────────
    prof = get_version_profile("1.21.8")
    assert prof.dp_format == 81 and prof.rp_format == 64, prof
    assert prof.function_folder == "function" and prof.tag_function_folder == "function"
    assert prof.packmeta_shape == "single" and prof.sign_dialect == "component_snbt"
    assert prof.tier == "green" and prof.has_tick_rate and prof.tps == 80
    print("ok: 1.21.8 profile", prof)
    # 1.21.4 = last JSON-string sign dialect; 1.21.5 flips to SNBT.
    assert get_version_profile("1.21.4").sign_dialect == "component_string"
    assert get_version_profile("1.21.5").sign_dialect == "component_snbt"
    print("ok: sign dialect flips component_string -> component_snbt at 1.21.5")
    # 1.21.9 now RESOLVES (no longer blanket-rejected) with the min/max packmeta shape.
    prof9 = get_version_profile("1.21.9")
    assert prof9.dp_format == 88 and prof9.rp_format == 69 and prof9.uses_minmax, prof9
    print("ok: 1.21.9 profile (min/max pack.mcmeta)", prof9)
    # 1.21.10 = non-breaking sibling of 1.21.9 (same 88/69 minmax); top of the green band.
    prof10 = get_version_profile("1.21.10")
    assert prof10.dp_format == 88 and prof10.rp_format == 69 and prof10.uses_minmax
    assert prof10.tier == "green" and prof10.sign_dialect == "component_snbt"
    assert_build_supported(prof10)  # green passes
    print("ok: 1.21.10 profile (green, min/max, same 88/69 as 1.21.9)", prof10)
    # yellow band: facts resolve, but the build policy refuses (mod not auto <1.21).
    prof_y = get_version_profile("1.20.4")
    assert prof_y.dp_format == 26 and prof_y.function_folder == "functions" and prof_y.tier == "yellow"
    print("ok: 1.20.4 profile resolves (plural folders, yellow tier)", prof_y)
    expect_raise(lambda: assert_build_supported(prof_y),
                 "yellow", "yellow band refused by build policy")
    assert_build_supported(prof)   # green passes silently
    assert_build_supported(prof9)  # 1.21.9 green passes silently
    # red band: below the /tick rate floor -> refuse with the timing reason.
    expect_raise(lambda: get_version_profile("1.20.2"),
                 "tick rate", "below tick-rate floor (1.20.2)")
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

    # ── sign 4-line assert + version-aware dialect ───────────────────────────
    assert sign_messages(["a", "b"]).count("text") == 4
    expect_raise(lambda: sign_messages(["1", "2", "3", "4", "5"]),
                 "sign needs <=4 lines", "over-long sign")
    # dialect: 1.20..1.21.4 wraps each entry in single quotes (JSON string); 1.21.5+
    # drops them (SNBT compound). The ONLY difference is the wrapping quotes.
    s_str = sign_messages(["[play]"], "component_string")
    s_snbt = sign_messages(["[play]"], "component_snbt")
    assert s_str.startswith("'{") and "'" in s_str, s_str
    assert s_snbt.startswith('{"text"') and "'" not in s_snbt, s_snbt
    expect_raise(lambda: sign_messages(["x"], "legacy"), "unknown sign dialect",
                 "unknown sign dialect rejected")
    btn = labeled_button(10, 255, 0, "function ns:play", ["[play]"],
                         sign_dialect="component_snbt")
    assert len(btn) == 5 and "command_block" in btn[1]
    assert "'" not in btn[4], btn[4]   # SNBT-compound sign has no wrapping quotes
    print("ok: labeled_button 5 blocks; sign dialect string/snbt; <=4 lines")

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
    # SCOPED remove of exactly this bbox — NEVER 'remove all' (co-existing songs互杀 guard).
    assert fl[0] == "forceload remove 0 0 32 32", fl[0]
    assert not any("remove all" in c for c in fl), fl
    print("ok: small forceload passes (scoped remove)", len(fl), "commands")
    expect_raise(lambda: forceload_guard(0, 0, 16000, 16000),  # huge -> hard fail
                 "too large", "oversize forceload hard-fail")
    fl2 = forceload_guard(0, 0, 16000, 16000, auto_fold=True)  # folds instead
    assert fl2[0] == "forceload remove 0 0 16000 16000" and len(fl2) > 1
    assert not any("remove all" in c for c in fl2), "no remove-all in folded forceload"
    print("ok: oversize forceload auto-folds into", len(fl2), "commands (scoped remove)")

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

    # ── tick rate is MANUAL: no auto tick-rate command block is emitted anymore. ──
    assert not hasattr(sys.modules[__name__], "tickrate_command_block"), \
        "tickrate_command_block must stay removed (player sets /tick rate 80 manually)"
    print("ok: no auto tick-rate command block (player types /tick rate 80 manually)")

    # ── direction rotation (§1.8): +X identity, others rotate + remap facing/rotation ──
    assert rotate_command("setblock 5 64 3 minecraft:stone", "+X", 0, 0) == "setblock 5 64 3 minecraft:stone"
    assert rot_xz(1, 0, "+Z", 0, 0) == (0, 1) and rot_xz(1, 0, "-X", 0, 0) == (-1, 0) and rot_xz(1, 0, "-Z", 0, 0) == (0, -1)
    assert rot_xz(*rot_xz(7, 3, "+Z", 0, 0), "-Z", 0, 0) == (7, 3)   # +Z then -Z round-trips
    assert "facing=north" in rotate_command("setblock 2 64 0 minecraft:repeater[facing=west,delay=2]", "+Z", 0, 0)
    assert "rotation=4" in rotate_command('setblock 0 64 0 minecraft:oak_sign[rotation=0]{a}', "+Z", 0, 0)
    assert rotate_command("forceload remove -2 -3 8 7", "-Z", 0, 0) == \
        "forceload remove -3 2 7 -8"
    assert rotate_command("scoreboard players set PLAY ns 1", "-X", 0, 0) == "scoreboard players set PLAY ns 1"
    # `execute (if|unless) loaded X Y Z run <tail>`: rotate loaded coords + recurse into tail.
    # -Z, coordinate-free tail (tellraw) recurses to verbatim.
    assert rotate_command('execute unless loaded 5 64 3 run return run tellraw @a "x"', "-Z", 0, 0) == \
        'execute unless loaded 3 64 -5 run return run tellraw @a "x"'
    # +Z, tail IS a setblock -> its coords rotate too (recursion), same rot as the loaded probe.
    assert rotate_command("execute if loaded 2 64 0 run setblock 2 64 0 minecraft:stone", "+Z", 0, 0) == \
        "execute if loaded 0 64 2 run setblock 0 64 2 minecraft:stone"
    print("ok: direction rotation (+X identity; +Z/-X/-Z rotate coords + facing/rotation + execute-loaded)")

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
        assert meta["pack"]["pack_format"] == 81 and "min_format" not in meta["pack"]
        print("ok: Datapack writes profile-driven singular folders + single dp_format 81")
        # 1.21.9 -> min_format/max_format pack.mcmeta (single pack_format would be disabled)
        dp9 = Datapack("ns9", "V9", td, "1.21.9")
        dp9.write_pack_mcmeta("v9 pack")
        meta9 = json.load(open(os.path.join(dp9.root, "pack.mcmeta")))
        assert meta9["pack"]["min_format"] == 88 and meta9["pack"]["max_format"] == 88
        assert "pack_format" not in meta9["pack"]
        print("ok: 1.21.9 Datapack writes min_format/max_format (88)")
        # pre-1.21 -> plural folders (facts resolve even though the build policy is green-only)
        dp2 = Datapack("oldns", "Old", td, "1.20.4")
        dp2.write_load_tick_tags()
        dp2.write_function("load", ["say hi"])
        assert os.path.isfile(os.path.join(dp2.root, "data", "oldns", "functions", "load.mcfunction"))
        assert os.path.isfile(os.path.join(dp2.root, "data", "minecraft", "tags", "functions", "load.json"))
        print("ok: pre-1.21 Datapack writes PLURAL folders")

    # ── namespace validation + traversal-rmtree regression (destructive-op safety) ──
    for bad in ["../evil", "..", "C:/temp_x", "/tmp/x", "a/b", "A", "春娇", "", "a.b"]:
        expect_raise(lambda b=bad: validate_namespace(b), "namespace",
                     f"reject bad ns {bad!r}")
    for good in ("cjzm", "test_ns-1"):
        validate_namespace(good)  # legal -> must NOT raise
    print("ok: validate_namespace accepts [a-z0-9_-]+, rejects ../ .. abs a/b A CJK '' a.b")
    # REGRESSION: a traversal ns must raise BEFORE any rmtree. Build a sentinel sibling
    # of the (sub)build dir and prove Datapack('../<sentinel>', ...) leaves it intact.
    _sandbox = tempfile.mkdtemp()
    try:
        _sentinel = os.path.join(_sandbox, "SENTINEL_KEEP")
        os.makedirs(_sentinel)
        open(os.path.join(_sentinel, "canary.txt"), "w").close()
        _sub = os.path.join(_sandbox, "build")
        os.makedirs(_sub)
        expect_raise(lambda: Datapack("../SENTINEL_KEEP", "Evil", _sub, "1.21.8"),
                     "namespace", "traversal ns rejected pre-rmtree")
        assert os.path.isfile(os.path.join(_sentinel, "canary.txt")), \
            "SENTINEL deleted — the raise happened AFTER rmtree!"
        print("ok: traversal ns raised before rmtree (sentinel dir intact)")
        # a legal ns still builds fine under the same sandbox.
        _okdp = Datapack("cjzm", "Fine", _sub, "1.21.8")
        assert os.path.isdir(_okdp.root) and os.path.basename(_okdp.root) == "cjzm"
        print("ok: legal ns builds under sandbox ->", _okdp.root)
    finally:
        shutil.rmtree(_sandbox, ignore_errors=True)

    print("redpiano_core self-test PASSED")
