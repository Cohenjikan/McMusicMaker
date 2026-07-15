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
# §1.1c  Performance mode (perfon/perfoff) — shed the persistent tick-load that
#   starves tick80 playback. In-game logs (Can't keep up) traced the choppiness to
#   the ×4 random-tick + mob-AI background load that runs every game-tick, not to the
#   machine itself. perfon captures the 5 tick-load gamerules into ns-scoped scores and
#   zeroes/false them; perfoff restores each PRECISELY (booleans from the captured 0/1,
#   randomTickSpeed from its enumerated original with a >3 fallback). Both are guarded so
#   redundant calls (setup then playcore both perfon) are no-ops. No coords -> the
#   direction-rotation in write_function passes every line through verbatim.
# ─────────────────────────────────────────────────────────────────────────────

# (score-name, gamerule) for the 5 captured gamerules. randomTickSpeed is numeric
# (enumerated restore); the other four are booleans (query returns 0/1).
_PERF_BOOL_RULES = [
    ("ORIG_MOB", "doMobSpawning"),
    ("ORIG_FIRE", "doFireTick"),
    ("ORIG_WEATHER", "doWeatherCycle"),
    ("ORIG_DAY", "doDaylightCycle"),
]


def perfon_fn(ns):
    """`perfon` body: capture (via `execute store result score ... run gamerule <rule>`,
    the query form) then disable the 5 tick-load gamerules. Guarded on PERF==1 so a second
    call (e.g. playcore after setup already turned it on) is a no-op and never re-captures
    the perf values as if they were the originals."""
    out = [f"execute if score PERF {ns} matches 1 run return 0"]
    # capture BEFORE mutating (guard above guarantees these are the true originals)
    out.append(
        f"execute store result score ORIG_RTS {ns} run gamerule randomTickSpeed")
    out += [f"execute store result score {s} {ns} run gamerule {g}"
            for s, g in _PERF_BOOL_RULES]
    out += ["gamerule randomTickSpeed 0",
            "gamerule doMobSpawning false",
            "gamerule doFireTick false",
            "gamerule doWeatherCycle false",
            "gamerule doDaylightCycle false",
            f"scoreboard players set PERF {ns} 1",
            f'tellraw @a "[{ns}] 性能模式 ON: 已暂存并关闭 随机刻/生物生成/火蔓延/天气/昼夜 '
            f'以给 tick80 播放减负(stop/结束/拆机会自动恢复)。"']
    return out


def perfoff_fn(ns):
    """`perfoff` body: restore the 5 gamerules perfon captured, precisely. Booleans go back
    from their captured 0/1; randomTickSpeed is restored from its enumerated original 0..3,
    with a >3 fallback to 3 (the vanilla default) plus a tellraw so a player who deliberately
    ran a high randomTickSpeed knows to set it back. Guarded on PERF==1 so a redundant perfoff
    (stop after the song already ended via done) is a no-op."""
    out = [f"execute unless score PERF {ns} matches 1 run return 0"]
    for s, g in _PERF_BOOL_RULES:
        out += [f"execute if score {s} {ns} matches 0 run gamerule {g} false",
                f"execute if score {s} {ns} matches 1 run gamerule {g} true"]
    out += [f"execute if score ORIG_RTS {ns} matches {v} run gamerule randomTickSpeed {v}"
            for v in (0, 1, 2, 3)]
    out += [f"execute if score ORIG_RTS {ns} matches 4.. run gamerule randomTickSpeed 3",
            f'execute if score ORIG_RTS {ns} matches 4.. run tellraw @a '
            f'"[{ns}] 注意: 你之前把 randomTickSpeed 设为 >3, 已回退为 3, 请按需自行改回。"',
            f"scoreboard players set PERF {ns} 0",
            f'tellraw @a "[{ns}] 性能模式 OFF: gamerule 已恢复。"']
    return out


# ─────────────────────────────────────────────────────────────────────────────
# §1.1d  Generation-progress bossbars — a visible progress bar for each long-running
#   segmented state machine (build / clear / protection-shell / preload), so generation
#   is no longer a black box. Four ids under the ns: bld(green) clr(red) pro(yellow,
#   only with protection) pre(blue). `load` (re)creates + hides them; each state machine
#   shows its bar at start (max/players/visible), the `tick` dispatch drives the value
#   from the driving score, and each done-handler hides its bar (cleardone removes all).
#   bossbar commands carry NO coords -> write_function's rotation passes them verbatim.
# ─────────────────────────────────────────────────────────────────────────────

# (id-suffix, label, bar-color). pro is appended only when protection is enabled.
_BOSSBAR_DEFS = [
    ("bld", "建造中", "green"),
    ("clr", "拆除中", "red"),
    ("pre", "预加载区块中", "blue"),
]
_BOSSBAR_PRO = ("pro", "保护壳施工中", "yellow")


def _bossbar_defs(with_pro):
    return _BOSSBAR_DEFS + ([_BOSSBAR_PRO] if with_pro else [])


def bossbar_init_lines(ns, with_pro=False):
    """`load` body fragment: (re)create the four progress bossbars and start hidden.
    `remove` before `add` is idempotent — a failed command inside a function is a silent
    no-op, so a first-ever load (nothing to remove) and a re-load (already exists) both end
    with exactly one fresh, hidden bar per id."""
    out = []
    for bid, label, color in _bossbar_defs(with_pro):
        out += [f"bossbar remove {ns}:{bid}",
                f'bossbar add {ns}:{bid} {{"text":"[{ns}] {label}"}}',
                f"bossbar set {ns}:{bid} color {color}",
                f"bossbar set {ns}:{bid} visible false"]
    return out


def bossbar_show(ns, bid, maxval):
    """State-machine start fragment: set the bar's max, attach @a, and reveal it."""
    return [f"bossbar set {ns}:{bid} max {maxval}",
            f"bossbar set {ns}:{bid} players @a",
            f"bossbar set {ns}:{bid} visible true"]


def bossbar_hide(ns, bid):
    """Done-handler fragment: hide one bar (kept defined so a later run can re-show it)."""
    return f"bossbar set {ns}:{bid} visible false"


def bossbar_track(ns, bid, score):
    """`tick` fragment: mirror the driving score into the bar's value while the machine is
    active (score in 0..). Placed beside the matching `run function ...:<step>` dispatch."""
    return (f"execute if score {score} {ns} matches 0.. store result bossbar {ns}:{bid} "
            f"value run scoreboard players get {score} {ns}")


def bossbar_remove_all(ns, with_pro=False):
    """`cleardone` (teardown) fragment: remove every bossbar this ns created."""
    return [f"bossbar remove {ns}:{bid}" for bid, _l, _c in _bossbar_defs(with_pro)]


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
# §1.3b  Timbre-palette STAND — a PHYSICAL showcase of every distinct landed
#   (mapping-block, note-value, sound-event) triple. Unlike a [试音] playsound button,
#   each stand cell is a REAL note block (mapping block directly below, air above) fired
#   by a wall button, so pressing it drives the genuine mod + resourcepack sound path —
#   that is the whole point of the exhibit. Emitted through the collision-guarded Grid so
#   the stand's footprint auto-joins the machine's forceload + cleanup bounding box.
#   Author +X frame; the caller's Datapack.write_function rotates it for non-+X directions.
# ─────────────────────────────────────────────────────────────────────────────

STAND_FAMILY_ORDER = ("pno", "bass", "lead", "pad", "drum")  # fixed section order
STAND_MAX_CELLS = 256      # truncate the palette past this (stats WARN); bounds setblocks
STAND_COLS = 16            # cells per row
STAND_CELL_DX = 2          # column spacing, grows -X
STAND_ROW_DZ = 4           # row spacing, grows -Z (block + north-face sign/button + aisle)


def _stand_short(s):
    """Trim a namespace + any blockstate/NBT for a sign label:
    ``qzpno:pno_c4_mf`` -> ``pno_c4_mf``; ``minecraft:iron_block[x=y]`` -> ``iron_block``."""
    return s.split("[")[0].split("{")[0].split(":")[-1]


def emit_palette_stand(grid, out, palette_by_family, *, ox, oz, y, sx, sz0,
                       sign_dialect, base_block="minecraft:stone"):
    """Emit a physical timbre-palette stand into ``grid`` (author +X frame).

    ``palette_by_family``: {family: iterable of (block, note_value, sound_event)} — the
    FINAL landed triples the caller dedup'd. Families are laid out in STAND_FAMILY_ORDER;
    within a family triples are sorted by (sound_event, note_value, block).

    Per cell at (cx, cz), through the collision-guarded Grid:
        mapping block   (cx, y,   cz)     # the mod reads THIS to choose the sample
        note block      (cx, y+1, cz)     # minecraft:note_block[note=<nv>]
        air             (cx, y+2, cz)     # a note block needs air above it to sound
        wall button     (cx, y+1, cz-1)   # stone_button[face=wall,facing=north] on the note
                                          #   block's NORTH face — pressing = redstone power =
                                          #   the REAL mod sound path. (NEVER right-click a
                                          #   stand note block: that re-pitches it, ruining
                                          #   the exhibit.)
        label wall sign (cx, y,   cz-1)   # on the mapping block's NORTH face, read from the
                                          #   same -Z aisle the button is pressed from; its
                                          #   backboard is the mapping block. Lines:
                                          #     1 event (no ns:)  2 block short id  3 note=<n> fam
    Rows grow -Z; each family gets a standing-sign header (backboard = base_block). Cells past
    STAND_MAX_CELLS are dropped and ``truncated`` is set True.

    Returns (stand_cells, truncated, walk_xz):
        stand_cells  {family: cells_placed}  (fixed order, only non-empty families)
        truncated    bool                    (palette exceeded STAND_MAX_CELLS)
        walk_xz      (x, z)                   aisle-entrance tp target (author frame)
    """
    # normalize + sort each family's triples (dedup defensively via set)
    fam_lists = {}
    for fam in STAND_FAMILY_ORDER:
        trips = palette_by_family.get(fam)
        if trips:
            fam_lists[fam] = sorted(set(trips), key=lambda t: (t[2], t[1], t[0]))
    total = sum(len(v) for v in fam_lists.values())
    truncated = total > STAND_MAX_CELLS

    # per-family placed counts under the GLOBAL cap (greedy, fixed order)
    budget = STAND_MAX_CELLS
    placed_n = {}
    for fam in STAND_FAMILY_ORDER:
        if fam not in fam_lists:
            continue
        take = min(len(fam_lists[fam]), budget)
        if take > 0:
            placed_n[fam] = take
        budget -= take

    stand_cells = {}
    walk_xz = None
    cur_z = sz0
    for fam in STAND_FAMILY_ORDER:
        n_take = placed_n.get(fam, 0)
        if n_take == 0:
            continue
        trips = fam_lists[fam]
        # ── family header: standing sign on a backing block, read from the +Z entrance ──
        hz = cur_z
        grid.put(out, sx, y, hz, base_block)
        hdr = sign_messages([f"== {fam.upper()} ==", f"{n_take} 格音色",
                             "按墙钮=真实发声"], sign_dialect)
        grid.put(out, sx, y + 1, hz,
                 "minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}" % hdr)
        if walk_xz is None:
            walk_xz = (sx + 3, hz + 2)   # entrance just +X/+Z of the first header
        # ── cells ──
        row0 = hz - STAND_ROW_DZ
        for k in range(n_take):
            block, nv, ev = trips[k]
            col, row = k % STAND_COLS, k // STAND_COLS
            cx = sx - col * STAND_CELL_DX
            cz = row0 - row * STAND_ROW_DZ
            grid.put(out, cx, y, cz, block)                                       # mapping block
            grid.put(out, cx, y + 1, cz, f"minecraft:note_block[note={nv}]")      # real note block
            grid.put(out, cx, y + 2, cz, "minecraft:air")                         # air above (sounding)
            grid.put(out, cx, y + 1, cz - 1,                                      # wall button (north face)
                     "minecraft:stone_button[face=wall,facing=north]")
            lbl = sign_messages([_stand_short(ev), _stand_short(block),
                                 f"note={nv} {fam}"], sign_dialect)
            grid.put(out, cx, y, cz - 1,                                          # label sign (north face)
                     "minecraft:oak_wall_sign[facing=north]"
                     "{front_text:{messages:[%s]}}" % lbl)
        stand_cells[fam] = n_take
        nrows = (n_take + STAND_COLS - 1) // STAND_COLS
        last_row_z = row0 - (nrows - 1) * STAND_ROW_DZ
        cur_z = last_row_z - 2 * STAND_ROW_DZ    # gap before the next family's header

    if walk_xz is None:                          # empty palette (no families) — degenerate
        walk_xz = (sx + 3, sz0 + 2)
    return stand_cells, truncated, walk_xz


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
# §1.4b  Protection shell (prosetup) — a segmented barrier box around the machine
#   footprint. The shell is built by a PRO-scored state machine BEFORE the machine
#   body: fill the six faces, (optionally) clear the interior cavity to air, then hand
#   off to the machine build. Emitted in the author +X frame; Datapack.write_function
#   rotates every `fill` for a non-+X play direction. Consumed by all line forms +
#   multilane; validated in params_schema.assert_supported.
# ─────────────────────────────────────────────────────────────────────────────

# per-segment fill bounds (Minecraft caps a single fill at 32768 blocks; keep the X
# stride short too so no one fill spans an unwieldy column count).
SHELL_MAX_XLEN = 128
SHELL_MAX_VOL = 32768

PROTECTION_DEFAULTS = {
    "enabled": False,
    "block": "minecraft:barrier",
    "margin_xz": 3,      # horizontal padding beyond the machine+console footprint
    "floor_margin": 2,   # blocks below the machine's Y-2 base for the floor slab
    "headroom": 5,       # blocks above the machine's Y+3 top for the ceiling slab
    "clear_interior": True,
}


def protection_config(prot):
    """Normalize a validated protection dict (or None) into a full config with defaults
    applied. Returns None when ``prot`` is falsy OR enabled is not True — i.e. None means
    "no shell, emit nothing" (the zero-diff path). params_schema.assert_supported has
    already validated the shape, so this only fills defaults."""
    if not prot:
        return None
    cfg = dict(PROTECTION_DEFAULTS)
    cfg.update(prot)
    if not cfg.get("enabled"):
        return None
    return cfg


def _seg_box(x0, y0, z0, x1, y1, z1, block, *,
             max_xlen=SHELL_MAX_XLEN, max_vol=SHELL_MAX_VOL):
    """Tile an axis-aligned box [x0..x1]x[y0..y1]x[z0..z1] into fill segments. Each segment
    has BOTH horizontal spans <= ``max_xlen`` AND volume <= ``max_vol``. Returns a list of
    (x0,y0,z0,x1,y1,z1,block) tuples that cover the box exactly once (no overlap, no gap).
    Empty box (any hi<lo) -> [].

    Both X and Z strides are capped at ``max_xlen`` (not just X): a non-+X play direction
    rotates author X<->Z, so bounding ONLY author-X would let the in-game X-span blow past
    the cap after a +/-Z rotation. Capping both keeps the rotated fill's X-span <= max_xlen
    for every direction; the Y stride then bounds any remaining volume."""
    if x1 < x0 or y1 < y0 or z1 < z0:
        return []
    segs = []
    xs = x0
    while xs <= x1:
        xe = min(x1, xs + max_xlen - 1)
        xlen = xe - xs + 1
        ylen_full = y1 - y0 + 1
        # Z stride: bounded by the length cap AND the volume budget (at full Y height).
        max_zlen = max(1, min(max_xlen, max_vol // (xlen * ylen_full)))
        zs = z0
        while zs <= z1:
            ze = min(z1, zs + max_zlen - 1)
            zlen = ze - zs + 1
            max_ylen = max(1, max_vol // (xlen * zlen))
            ys = y0
            while ys <= y1:
                ye = min(y1, ys + max_ylen - 1)
                segs.append((xs, ys, zs, xe, ye, ze, block))
                ys = ye + 1
            zs = ze + 1
        xs = xe + 1
    return segs


def protection_shell(cfg, bx0, bz0, bx1, bz1, y, *,
                     max_xlen=SHELL_MAX_XLEN, max_vol=SHELL_MAX_VOL):
    """Compute the barrier-shell geometry around the union footprint [bx0..bx1]x[bz0..bz1]
    at machine height ``y`` (author +X frame). Returns (shell_segs, interior_segs, bbox):

        shell_segs     list of (x0,y0,z0,x1,y1,z1,block) — floor + ceiling + 4 walls, a
                       WATERTIGHT box (every perimeter cell covered exactly once).
        interior_segs  list of fill-air segments for the interior cavity (empty when
                       clear_interior is false); strictly INSIDE the shell (never a shell cell).
        bbox           (SX0, SZ0, SX1, SZ1, FLOOR_Y, CEIL_Y) — the shell extent.

    Geometry (contract): floor top surface at Y-2-floor_margin, ceiling bottom at
    Y+3+headroom, horizontal extent = footprint +/- margin_xz. Floor and ceiling are single
    Y layers over the full XZ rectangle; the 4 walls fill the perimeter for the Y range
    strictly between them (east/west walls span the full Z, north/south walls span X minus
    the shared corner columns, so the box is closed with no double-placed cell)."""
    m = int(cfg["margin_xz"])
    block = cfg["block"]
    SX0, SZ0 = bx0 - m, bz0 - m
    SX1, SZ1 = bx1 + m, bz1 + m
    FLOOR_Y = y - 2 - int(cfg["floor_margin"])
    CEIL_Y = y + 3 + int(cfg["headroom"])

    shell = []
    # floor + ceiling: full XZ rectangle, one Y layer each
    shell += _seg_box(SX0, FLOOR_Y, SZ0, SX1, FLOOR_Y, SZ1, block,
                      max_xlen=max_xlen, max_vol=max_vol)
    shell += _seg_box(SX0, CEIL_Y, SZ0, SX1, CEIL_Y, SZ1, block,
                      max_xlen=max_xlen, max_vol=max_vol)
    # walls: only the Y band strictly between floor and ceiling
    wy0, wy1 = FLOOR_Y + 1, CEIL_Y - 1
    if wy1 >= wy0:
        # west (x=SX0) + east (x=SX1) walls span the full Z (own the corners)
        shell += _seg_box(SX0, wy0, SZ0, SX0, wy1, SZ1, block,
                          max_xlen=max_xlen, max_vol=max_vol)
        shell += _seg_box(SX1, wy0, SZ0, SX1, wy1, SZ1, block,
                          max_xlen=max_xlen, max_vol=max_vol)
        # north (z=SZ0) + south (z=SZ1) walls span X minus the corner columns
        if SX1 - 1 >= SX0 + 1:
            shell += _seg_box(SX0 + 1, wy0, SZ0, SX1 - 1, wy1, SZ0, block,
                              max_xlen=max_xlen, max_vol=max_vol)
            shell += _seg_box(SX0 + 1, wy0, SZ1, SX1 - 1, wy1, SZ1, block,
                              max_xlen=max_xlen, max_vol=max_vol)

    interior = []
    if cfg.get("clear_interior"):
        interior = _seg_box(SX0 + 1, wy0, SZ0 + 1, SX1 - 1, wy1, SZ1 - 1,
                            "minecraft:air", max_xlen=max_xlen, max_vol=max_vol)

    return shell, interior, (SX0, SZ0, SX1, SZ1, FLOOR_Y, CEIL_Y)


def shell_fill_cmd(seg):
    """Render one (x0,y0,z0,x1,y1,z1,block) segment as a `fill` command string
    (author +X frame; Datapack.write_function rotates it for a non-+X direction)."""
    x0, y0, z0, x1, y1, z1, block = seg
    return f"fill {x0} {y0} {z0} {x1} {y1} {z1} {block}"


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
# §1.6b  Deterministic pulse-kill buckets — physically kill the marching pulse on stop.
#   A `stop` mid-song must not leave a redstone pulse still marching down the repeater
#   line (it would keep firing note blocks / block an instant re-play). SIL/mute cover the
#   SAMPLE tails, but the pulse itself is a physical redstone signal — the only way to end
#   it deterministically is to punch an AIR gap in a repeater just ahead of its front, which
#   the signal cannot cross. 4 game-ticks later the repeater is restored byte-for-byte so
#   the machine is intact and instantly replayable.
#
#   The generator knows, at COMPILE time, when the pulse reaches every cell: a repeater with
#   delay d red-stone-ticks = 2d game-ticks, so arrival_gt(cell) = 2 x cumulative delay. At
#   run time an ELAPSED score counts game-ticks while PLAY==1, so `stop` reads ELAPSED, maps
#   it to a time BUCKET, and kills every repeater whose arrival_gt sits in that bucket's
#   (padded) window — guaranteeing a dead repeater at/ahead of the front wherever it is.
#
#   Bucket n covers ELAPSED in [128n, 128n+127]; its KILL WINDOW = repeater cells with
#   arrival_gt in [128n-16, 128n+127+80] (back-pad absorbs the ELAPSED->arrival offset;
#   forward-pad guarantees killed repeaters AHEAD of the front). Windows overlap between
#   buckets by design; that is fine — only ONE bucket fires per stop (the one ELAPSED is in).
# ─────────────────────────────────────────────────────────────────────────────

KILL_BUCKET_GT = 128   # ELAPSED bucket width in game-ticks
KILL_WIN_BACK = 64     # kill window extends this many gt before the bucket's ELAPSED start.
# 64 (was 16): the BACK edge is the only edge that actually kills — the front lookahead air
# heals (4gt restore) before the dominant 8gt repeater hop completes, so it is inert. A thin
# back margin (16 -> ~6-14gt usable after discretization) leaks the pulse whenever the real
# front lags ELAPSED by >=11gt (in-game 偶发 "stop 后 ~1s 音乐复活"). Widening BACKWARD only
# deletes already-passed, unpowered repeaters — strictly safe, no re-trigger risk — and lifts
# the tolerated front-lag to ~55gt+. (2026-07-12 static pulse simulation on the deployed pack.)
KILL_WIN_FWD = 80      # ...and this many gt past the bucket's ELAPSED end (front lookahead)
KILL_RESTORE_DELAY_GT = 4  # restore the punched repeaters this many game-ticks later


def arrival_gt_by_cell(cells):
    """Given the shared-timeline ``cells`` (list of ('rep', delay) | ('trig', tick)),
    return ``arr`` where ``arr[i]`` = the pulse arrival at cell i in GAME-TICKS =
    2 x (cumulative repeater delay in redstone-ticks reaching cell i's input).

    This depends ONLY on the shared skeleton, so a cell index maps to the SAME arrival
    for every mirror track / parallel lane (they all share one repeater skeleton). At a
    trig cell arr = 2 x (sum of preceding rep delays) = 2 x (T0+OFFSET) — the same value
    the melody-cut schedule uses — so kill timing and cut timing agree by construction."""
    out = []
    cum = 0
    for kind, v in cells:
        out.append(2 * cum)
        if kind == "rep":
            cum += v
    return out


class KillPlan:
    """Output of plan_kill_buckets(). Fields:
      buckets     list[list[(x,y,z,block)]] — per-bucket repeater cells to punch to air
                  (author +X frame; the caller's write_function rotates them).
      n_buckets   total buckets (indices 0..n_buckets-1), continuous over ELAPSED
                  0..music_ticks+200.
      cells_max   the largest single-bucket cell count (report metric / stats).
    """

    __slots__ = ("buckets", "n_buckets", "cells_max")

    def __init__(self, buckets, n_buckets, cells_max):
        self.buckets = buckets
        self.n_buckets = n_buckets
        self.cells_max = cells_max


def plan_kill_buckets(rep_cells, music_ticks):
    """Bucket every repeater cell by the ELAPSED window that should kill it.

    ``rep_cells``: iterable of ``(arrival_gt, x, y, z, block)`` — EVERY repeater cell
    across all tracks/lanes/signal-tracks (author +X frame). ``block`` is the exact
    repeater blockstate string emitted at build time (so restore is byte-faithful).

    Buckets span 0..N where N = (music_ticks+200)//128 (continuous ELAPSED coverage of
    0..music_ticks+200). Bucket n collects cells with arrival_gt in
    [128n-KILL_WIN_BACK, 128n+127+KILL_WIN_FWD].

    Build-time GUARD (CONTRACT §5.①): a bucket whose ELAPSED interval overlaps the song
    [0, music_ticks] (i.e. 128n <= music_ticks) MUST contain >= 1 repeater cell — else a
    stop landing there would be a silent no-op. Raise RedPianoError (fail at build, never
    ship a machine whose stop can't kill the pulse). Tail buckets past music_ticks may be
    empty (the pulse has already finished there)."""
    top = music_ticks + 200
    n_buckets = top // KILL_BUCKET_GT + 1
    rep_cells = list(rep_cells)
    buckets = []
    for n in range(n_buckets):
        lo = KILL_BUCKET_GT * n - KILL_WIN_BACK
        hi = KILL_BUCKET_GT * n + (KILL_BUCKET_GT - 1) + KILL_WIN_FWD
        buckets.append([(x, y, z, block) for (a, x, y, z, block) in rep_cells
                        if lo <= a <= hi])
    for n in range(n_buckets):
        elapsed_lo = KILL_BUCKET_GT * n
        if elapsed_lo <= music_ticks and not buckets[n]:
            raise RedPianoError(
                f"kill bucket {n} (ELAPSED {elapsed_lo}..{elapsed_lo + KILL_BUCKET_GT - 1}) "
                f"overlaps the song [0,{music_ticks}] but its kill window "
                f"[{KILL_BUCKET_GT * n - KILL_WIN_BACK}.."
                f"{KILL_BUCKET_GT * n + KILL_BUCKET_GT - 1 + KILL_WIN_FWD}] contains NO "
                f"repeater — a stop landing here could not kill the pulse. (repeater "
                f"skeleton too sparse for the {KILL_BUCKET_GT}gt bucketing?)")
    cells_max = max((len(b) for b in buckets), default=0)
    return KillPlan(buckets, n_buckets, cells_max)


def kill_function_bodies(ns, plan):
    """Render the kill/restore datapack function bodies from a KillPlan.

    Returns ``(killzone_body, kill_bodies, restore_bodies)``:
      killzone_body     lines for ``<ns>:killzone`` — the PLAY guard + a CONTINUOUS,
                        non-overlapping ELAPSED ladder dispatching to kill/k<n>. The LAST
                        rung is open-ended (``matches {lo}..``) so a stray late ELAPSED is
                        still covered; it is always a pure tail (no-op) bucket.
      kill_bodies       {n: body} for ``<ns>:kill/k<n>`` — set ARM=0, setblock air per
                        cell, schedule restore/k<n>.
      restore_bodies    {n: body} for ``<ns>:restore/k<n>`` — setblock the exact repeater
                        per cell, set ARM=1. **restore/* MUST NEVER be added to any
                        SCHED_CLEAR list**: even if a halt interrupts, the 4gt restore must
                        still fire or the machine keeps an air hole.

    All setblock lines are AUTHOR +X frame — the caller writes them via
    Datapack.write_function, which rotates coords + blockstates for a non-+X direction, so
    a restore line stays byte-identical to the same cell's line in the build (bld) batch."""
    killzone = [f"execute unless score PLAY {ns} matches 1 run return 0"]
    kill_bodies = {}
    restore_bodies = {}
    last = plan.n_buckets - 1
    for n in range(plan.n_buckets):
        lo = KILL_BUCKET_GT * n
        if n == last:
            rung = f"matches {lo}.."               # open-ended tail rung
        else:
            rung = f"matches {lo}..{lo + KILL_BUCKET_GT - 1}"
        killzone.append(
            f"execute if score ELAPSED {ns} {rung} run function {ns}:kill/k{n}")
        kb = [f"scoreboard players set ARM {ns} 0"]
        kb += [f"setblock {x} {y} {z} minecraft:air"
               for (x, y, z, _block) in plan.buckets[n]]
        kb.append(f"schedule function {ns}:restore/k{n} {KILL_RESTORE_DELAY_GT}t")
        kill_bodies[n] = kb
        rb = [f"setblock {x} {y} {z} {block}"
              for (x, y, z, block) in plan.buckets[n]]
        rb.append(f"scoreboard players set ARM {ns} 1")
        restore_bodies[n] = rb
    return killzone, kill_bodies, restore_bodies


# ─────────────────────────────────────────────────────────────────────────────
# §1.6c  Cam-follow (实体锁定跟拍) — swave/straight/custom 与 multilane 共享.
#   玩家骑一个隐形盔甲架([跟拍]按钮), 盔甲架由 ELAPSED 时基逐刻搬运, 与脉冲前沿
#   (arr[] 到达刻)锁死。为什么不是飞行/追路标: 脉冲速度本就不恒定(repeater 1..4 档
#   延迟 + 0 延迟 U 弯), 只有"生成期已知的到达时刻表"能精确跟住; 且 ELAPSED 与红石
#   同为服务端游戏刻, /tick rate 缩放、服务器卡顿都自动同相, 永不漂移。客户端对
#   载具移动做插值(骑乘=丝滑来源), 每刻一次小步 tp 即平滑。
#   分工: 几何(相机锚点 pts)由生成器提供 — core 不发明机器几何(与 §1.6b 同约)。
# ─────────────────────────────────────────────────────────────────────────────

CAM_HEIGHT = 10          # 相机悬停高度 (Y + CAM_HEIGHT)
CAM_BACK = 6.0           # 相机沿作者系 -X 退后量, 让前沿保持在画面前方
CAM_SMOOTH_GT = 16       # 前沿位置移动平均半窗(gt) — 抹平延迟档位突变与 U 弯瞬移
CAM_WIN_GT = 8           # 压缩窗口: 每窗一条绝对校准 + 一条逐刻相对步进(零累积漂移)
CAM_BUCKET_GT = 1024     # 两级派发桶宽(对齐 killzone 手法, 压低每刻命令评估数)
CAM_FIRE_OFS = 2         # playcore 后 fire 延迟 2t: arr=0 对应 ELAPSED≈2


def cam_follow_plan(ns, pts, arr, music_ticks, y, start_dir, ox, oz):
    """§1.6c cam-follow: 生成实体锁定跟拍的全部函数体。

    输入: ``pts[i]`` = 生成器给的 cell i 相机锚点(作者 +X 系, float (x,z));
    ``arr[i]`` = 脉冲到达 cell i 的游戏刻(相对 fire, arrival_gt_by_cell)。产出:

      cam_body      <ns>:cam — 召唤隐形盔甲架 + ride 上架([跟拍]按钮)
      camoff_body   <ns>:camoff — 下架 + 撤实体
      ladder        <ns>:cam/step — ELAPSED 桶梯子(tick 每刻在 PLAY==1 时调用)
      buckets       {n: body} <ns>:cam/c<n> — 每 CAM_WIN_GT 一条绝对校准(matches s)
                    + 一条逐刻相对步进(matches s+1..e); 绝对线消漂移, 相对线保平滑
      n_windows     窗口数(stats)
      cam_home      playcore 用: 重播前把相机架(若在场)归位到起点 — tick 先自增
                    ELAPSED 再派发, 窗口 0 的 matches 0 绝对校准永不命中, 重播时
                    必须显式归位(空选择器无害失败)

    坐标处理: 锚点退后 CAM_BACK、抬高 CAM_HEIGHT 后用 rot_xz 预旋转到 world 系,
    渲染成带小数点的浮点字面量 — rotate_command 对非整数坐标 int() 失败原样放行,
    write_function 不会二次旋转。相对步进包在 execute 里, 本就不被旋转, 故 (dx,dz)
    同样预旋转。summon 不在 rotate_command 处理表内(任何方向都原样放行)。"""
    n = len(pts)
    a = [g + CAM_FIRE_OFS for g in arr]          # 到达刻 -> ELAPSED 域
    T = music_ticks + CAM_FIRE_OFS

    # 1. 逐刻采样前沿位置(相邻 cell 间线性插值; trig/U 弯的 0 时长段位置瞬移,
    #    交给下面的移动平均抹平)。
    raw = []
    j = 0
    for t in range(T + 1):
        while j + 1 < n and a[j + 1] <= t:
            j += 1
        if j + 1 < n and a[j] <= t:
            span = a[j + 1] - a[j]
            f = (t - a[j]) / span if span else 1.0
            x = pts[j][0] + (pts[j + 1][0] - pts[j][0]) * f
            z = pts[j][1] + (pts[j + 1][1] - pts[j][1]) * f
            raw.append((x, z))
        else:
            raw.append(pts[j if a[j] <= t else 0])

    # 2. ±CAM_SMOOTH_GT 移动平均(前缀和) -> 平滑轨迹; 同时退后 + 预旋转到 world 系。
    px = [0.0]
    pz = [0.0]
    for (x, z) in raw:
        px.append(px[-1] + x)
        pz.append(pz[-1] + z)
    cam = []
    for t in range(T + 1):
        lo = max(0, t - CAM_SMOOTH_GT)
        hi = min(T, t + CAM_SMOOTH_GT)
        cnt = hi - lo + 1
        sx = (px[hi + 1] - px[lo]) / cnt - CAM_BACK   # 作者系 -X 退后
        sz = (pz[hi + 1] - pz[lo]) / cnt
        cam.append(rot_xz(sx, sz, start_dir, ox, oz))
    CY = y + CAM_HEIGHT

    # 3. 压缩成窗口: 窗口 k 覆盖 ELAPSED [s, e] (e = min(s+W-1, T))。tick s 一条绝对
    #    校准 tp(把上个窗口的舍入残差一并归零, 残差 ≤ 8gt x 5e-5 ≈ 4e-4 格, 不可见),
    #    tick s+1..e 逐刻相对步进。每刻恰好命中一条 -> 无双移、无跳变、无累积漂移。
    W = CAM_WIN_GT
    sel = f"@e[tag={ns}_cam,limit=1]"
    buckets = {}
    n_windows = 0
    for s in range(0, T + 1, W):
        e = min(s + W - 1, T)
        bn = s // CAM_BUCKET_GT
        body = buckets.setdefault(bn, [])
        x0, z0 = cam[s]
        body.append(f"execute if score ELAPSED {ns} matches {s} run "
                    f"tp {sel} {x0:.3f} {CY} {z0:.3f}")
        if e > s:
            dx = (cam[e][0] - cam[s][0]) / (e - s)
            dz = (cam[e][1] - cam[s][1]) / (e - s)
            body.append(f"execute if score ELAPSED {ns} matches {s + 1}..{e} "
                        f"as {sel} at @s run tp @s ~{dx:.4f} ~ ~{dz:.4f}")
        n_windows += 1

    ladder = []
    for bn in sorted(buckets):
        lo = bn * CAM_BUCKET_GT
        hi = lo + CAM_BUCKET_GT - 1
        ladder.append(f"execute if score ELAPSED {ns} matches {lo}..{hi} run "
                      f"function {ns}:cam/c{bn}")

    # 4. 上/下架。ride 为 Java 1.19.4+ 语法 (ride <骑手> mount <载具>)。
    x0, z0 = cam[0]
    cam_body = [
        f"kill @e[tag={ns}_cam]",
        f'summon minecraft:armor_stand {x0:.3f} {CY} {z0:.3f} '
        f'{{Tags:["{ns}_cam"],Invisible:1b,NoGravity:1b,Invulnerable:1b}}',
        f"ride @p mount @e[tag={ns}_cam,limit=1]",
        f'tellraw @a "[{ns}] 跟拍就位(可自由转头)。按 [play] 后相机与脉冲前沿逐刻锁定;'
        f'中途退出按 [stop] 或 /function {ns}:camoff。"',
    ]
    camoff_body = [
        f"execute as @e[tag={ns}_cam] on passengers run ride @s dismount",
        f"kill @e[tag={ns}_cam]",
        f'tellraw @a "[{ns}] 跟拍已退出。"',
    ]
    cam_home = f"tp {sel} {x0:.3f} {CY} {z0:.3f}"
    return cam_body, camoff_body, ladder, buckets, n_windows, cam_home


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

    # ── pulse-kill buckets (§1.6b): arrival math + bucketing + ladder + assertions ──
    # a small shared skeleton: rep(2), trig(0), rep(4), rep(1), trig(5) — note trig arrival
    # equals 2*(T0+OFFSET) with OFFSET derived by the caller (here OFFSET=0, trigs>0).
    _cells = [("rep", 2), ("trig", 3), ("rep", 4), ("rep", 1), ("trig", 8)]
    _arr = arrival_gt_by_cell(_cells)
    # cum: 0 (rep2 input), then +2 -> trig arrival 4 == 2*(3+0)? no: this toy trig=3 with
    # cum after rep2 = 2 -> arrival 4. The real generators build cells so cum==T0+OFFSET;
    # here we only assert the CUMULATIVE math, not the toy's musical consistency.
    assert _arr == [0, 4, 4, 12, 14], _arr        # 2*[0,2,2,6,7]
    print("ok: arrival_gt_by_cell cumulative math", _arr)
    # rep cells across TWO mirror tracks (same arrival, distinct z) -> both killed per bucket
    _reps = [
        (_arr[0], 10, 64, 0, "minecraft:repeater[facing=west,delay=2]"),
        (_arr[0], 10, 64, 9, "minecraft:repeater[facing=west,delay=2]"),   # mirror track
        (_arr[2], 12, 64, 0, "minecraft:repeater[facing=west,delay=4]"),
        (_arr[3], 13, 64, 0, "minecraft:repeater[facing=west,delay=1]"),
    ]
    _kp = plan_kill_buckets(_reps, music_ticks=14)
    # music_ticks 14 -> top 214 -> n_buckets = 214//128 + 1 = 2 (buckets 0,1)
    assert _kp.n_buckets == 2, _kp.n_buckets
    # bucket 0 window [-16, 207] catches every rep (arrivals 0,0,12,14) -> 4 cells
    assert len(_kp.buckets[0]) == 4, _kp.buckets[0]
    assert _kp.cells_max == 4, _kp.cells_max
    print("ok: plan_kill_buckets", _kp.n_buckets, "buckets, max", _kp.cells_max, "cells")
    # build-time GUARD: a bucket overlapping [0,music_ticks] with NO repeater -> raise. Force
    # it by claiming a long song (music_ticks 5000) but supplying only near-zero-arrival reps.
    expect_raise(lambda: plan_kill_buckets(
        [(0, 1, 64, 0, "minecraft:repeater[facing=west,delay=1]")], music_ticks=5000),
        "NO", "sparse-skeleton kill guard")
    # ladder: continuous, non-overlapping, PLAY guard first, open-ended last rung, and the
    # restore line is byte-identical to the rep cell's block (so it matches the bld batch).
    _kz, _kb, _rb = kill_function_bodies("qz", _kp)
    assert _kz[0] == "execute unless score PLAY qz matches 1 run return 0", _kz[0]
    assert "matches 0..127 run function qz:kill/k0" in _kz[1]
    assert _kz[-1].endswith("matches 128.. run function qz:kill/k1"), _kz[-1]   # open last rung
    # kill body: ARM=0 first, air setblocks, restore schedule last
    assert _kb[0][0] == "scoreboard players set ARM qz 0"
    assert _kb[0][-1] == "schedule function qz:restore/k0 4t"
    assert "setblock 10 64 0 minecraft:air" in _kb[0] and "setblock 10 64 9 minecraft:air" in _kb[0]
    # restore body: exact repeater setblock + ARM=1 last; air coords == restore coords set
    assert "setblock 10 64 0 minecraft:repeater[facing=west,delay=2]" in _rb[0]
    assert _rb[0][-1] == "scoreboard players set ARM qz 1"
    _air = {c.split(" minecraft:air")[0] for c in _kb[0] if c.startswith("setblock")}
    _res = {c.rsplit(" minecraft:repeater", 1)[0] for c in _rb[0] if c.startswith("setblock")}
    assert _air == _res, (_air, _res)   # every killed coord is restored, and vice-versa
    print("ok: kill_function_bodies ladder+guard+byte-faithful restore (air coords==restore coords)")

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

    # ── stand wall-button / wall-sign rotation: `facing=` (compass) rotates, `face=wall`
    #    (mount type) is rotation-invariant and must NOT change; NBT + spaces survive. ──
    _b = rotate_command("setblock 3 64 5 minecraft:stone_button[face=wall,facing=north]", "+Z", 0, 0)
    assert "face=wall" in _b and "facing=east" in _b, _b        # north --+Z(1 CW)--> east
    _b2 = rotate_command("setblock 3 64 5 minecraft:stone_button[face=wall,facing=north]", "-Z", 0, 0)
    assert "face=wall" in _b2 and "facing=west" in _b2, _b2     # north --(-Z=3 CW)--> west
    _sgn = ('setblock 2 64 3 minecraft:oak_wall_sign[facing=north]'
            '{front_text:{messages:[{"text":"note=12 pno"}]}}')
    _rs = rotate_command(_sgn, "+Z", 0, 0)
    assert _rs.startswith("setblock -3 64 2 "), _rs             # (2,3)->(-3,2) around origin
    assert "facing=east" in _rs and '"text":"note=12 pno"' in _rs, _rs  # facing rot + NBT/space intact
    print("ok: wall button/sign rotate facing=, keep face=wall, preserve spaced NBT")

    # ── palette stand emission (collision-free, fixed family order, truncation) ──
    _grid, _out = Grid(), []
    _pal = {
        "pno": [("minecraft:iron_block", 12, "qzpno:pno_c4_mf"),
                ("minecraft:gold_block", 5, "qzpno:pno_a3_p")],
        "drum": [("minecraft:tnt", 12, "qzpno:drum:snare")],
    }
    _cells, _trunc, _walk = emit_palette_stand(
        _grid, _out, _pal, ox=0, oz=0, y=64, sx=-3, sz0=-6,
        sign_dialect="component_snbt", base_block="minecraft:stone")
    assert _cells == {"pno": 2, "drum": 1} and not _trunc, (_cells, _trunc)
    assert sum(1 for c in _out if "note_block" in c) == 3, _out          # 3 real note blocks
    assert sum(1 for c in _out if "stone_button[face=wall" in c) == 3    # 3 wall buttons
    assert sum(1 for c in _out if "oak_wall_sign" in c) == 3             # 3 per-cell labels
    assert sum(1 for c in _out if "oak_sign[rotation=0]" in c) == 2      # 2 family headers
    # note block sits directly ABOVE its mapping block (mod reads the block below); the
    # button/label sit one block NORTH (z-1) on those two blocks' faces. pno sorts by event
    # so col 0 = gold_block/pno_a3_p @ (sx, y, sz0-ROW_DZ) = (-3, 64, -10).
    assert "setblock -3 64 -10 minecraft:gold_block" in _out                     # mapping @ (cx,y,cz)
    assert "setblock -3 65 -10 minecraft:note_block[note=5]" in _out             # note   @ (cx,y+1,cz)
    assert "setblock -3 66 -10 minecraft:air" in _out                            # air    @ (cx,y+2,cz)
    assert "setblock -3 65 -11 minecraft:stone_button[face=wall,facing=north]" in _out  # button @ (cx,y+1,cz-1)
    assert any(c.startswith("setblock -3 64 -11 minecraft:oak_wall_sign") for c in _out)  # label @ (cx,y,cz-1)
    print("ok: emit_palette_stand ->", _cells, "collision-free, walk@", _walk)
    _big = {"pno": [("minecraft:stone", i % 25, "qzpno:e%04d" % i) for i in range(300)]}
    _g2, _o2 = Grid(), []
    _c2, _t2, _ = emit_palette_stand(_g2, _o2, _big, ox=0, oz=0, y=64, sx=-3, sz0=-6,
                                     sign_dialect="component_snbt")
    assert _t2 and _c2["pno"] == STAND_MAX_CELLS, (_t2, _c2)
    print("ok: emit_palette_stand truncates a", 300, "-triple palette to", STAND_MAX_CELLS)

    # ── protection shell: config normalization + segmenter bounds + watertight box ──
    assert protection_config(None) is None
    assert protection_config({"enabled": False}) is None          # disabled -> None (zero-diff)
    _cfg = protection_config({"enabled": True})                   # defaults fill in
    assert _cfg == {"enabled": True, "block": "minecraft:barrier", "margin_xz": 3,
                    "floor_margin": 2, "headroom": 5, "clear_interior": True}, _cfg
    _cfg2 = protection_config({"enabled": True, "block": "minecraft:glass", "margin_xz": 5})
    assert _cfg2["block"] == "minecraft:glass" and _cfg2["margin_xz"] == 5
    print("ok: protection_config normalizes (None when disabled)")

    def _seg_ok(segs, max_xlen=SHELL_MAX_XLEN, max_vol=SHELL_MAX_VOL):
        cells = {}
        for (x0, y0, z0, x1, y1, z1, _b) in segs:
            xlen = x1 - x0 + 1
            zlen = z1 - z0 + 1
            vol = xlen * (y1 - y0 + 1) * zlen
            assert xlen <= max_xlen, ("xlen", xlen)
            assert zlen <= max_xlen, ("zlen", zlen)   # both spans bounded (rotation-safe)
            assert vol <= max_vol, ("vol", vol)
            for xx in range(x0, x1 + 1):
                for yy in range(y0, y1 + 1):
                    for zz in range(z0, z1 + 1):
                        k = (xx, yy, zz)
                        assert k not in cells, ("overlap", k)   # each cell covered once
                        cells[k] = _b
        return cells

    # a wide, thin slab (like a real floor) forces X + Z striding
    _floor = _seg_box(0, 64, 0, 400, 64, 300, "minecraft:barrier")
    _fcells = _seg_ok(_floor)
    assert len(_fcells) == 401 * 1 * 301, len(_fcells)           # exact cover, no gap
    assert max(x1 - x0 + 1 for (x0, _, _, x1, _, _, _) in _floor) <= 128
    print("ok: _seg_box tiles a 401x301 floor (xlen<=128, vol<=32768, exact cover)")

    # full shell around a small footprint: six faces watertight, interior excludes shell
    _sh, _int, _bb = protection_shell(
        {"enabled": True, "block": "minecraft:barrier", "margin_xz": 3,
         "floor_margin": 2, "headroom": 5, "clear_interior": True},
        bx0=0, bz0=0, bx1=10, bz1=6, y=64)
    SX0, SZ0, SX1, SZ1, FY, CY = _bb
    assert (SX0, SZ0, SX1, SZ1) == (-3, -3, 13, 9), _bb          # +/- margin_xz=3
    assert FY == 64 - 2 - 2 and CY == 64 + 3 + 5, _bb            # floor/ceiling planes
    _scells = _seg_ok(_sh)                                       # shell has no self-overlap
    # every perimeter cell of the box is present, and no cell strictly interior is a shell cell
    _shell_keys = set(_scells)
    missing = []
    for xx in range(SX0, SX1 + 1):
        for yy in range(FY, CY + 1):
            for zz in range(SZ0, SZ1 + 1):
                on_face = (yy == FY or yy == CY or xx == SX0 or xx == SX1
                           or zz == SZ0 or zz == SZ1)
                if on_face and (xx, yy, zz) not in _shell_keys:
                    missing.append((xx, yy, zz))
                if (not on_face) and (xx, yy, zz) in _shell_keys:
                    missing.append(("interior-has-shell", xx, yy, zz))
    assert not missing, missing[:8]
    # each of the six faces is fully covered (sample the four corners + center of each)
    for (label, pts) in [
        ("floor",  [(SX0, FY, SZ0), (SX1, FY, SZ1), (5, FY, 3)]),
        ("ceil",   [(SX0, CY, SZ0), (SX1, CY, SZ1), (5, CY, 3)]),
        ("west",   [(SX0, FY + 1, SZ0), (SX0, CY - 1, SZ1)]),
        ("east",   [(SX1, FY + 1, SZ0), (SX1, CY - 1, SZ1)]),
        ("north",  [(5, FY + 1, SZ0), (5, CY - 1, SZ0)]),
        ("south",  [(5, FY + 1, SZ1), (5, CY - 1, SZ1)]),
    ]:
        for p in pts:
            assert p in _shell_keys, (label, p)
    # interior clear is strictly inside the shell (never a shell cell), fills the cavity
    _icells = _seg_ok(_int)
    for k in _icells:
        assert k not in _shell_keys, ("interior touches shell", k)
        xx, yy, zz = k
        assert SX0 < xx < SX1 and SZ0 < zz < SZ1 and FY < yy < CY, k
    assert len(_icells) == (SX1 - SX0 - 1) * (SZ1 - SZ0 - 1) * (CY - FY - 1), len(_icells)
    # clear_interior=false -> no interior segments
    _sh2, _int2, _ = protection_shell(
        {"enabled": True, "block": "minecraft:barrier", "margin_xz": 1,
         "floor_margin": 0, "headroom": 0, "clear_interior": False},
        bx0=0, bz0=0, bx1=4, bz1=4, y=100)
    assert _int2 == [], _int2
    print("ok: protection_shell watertight (6 faces), interior clears cavity only")

    # ── perfmode: capture-then-disable + precise restore (guards, enumerated RTS) ──
    _on = perfon_fn("qz")
    assert _on[0] == "execute if score PERF qz matches 1 run return 0", _on[0]
    # all 5 gamerules captured via the query form BEFORE any mutation
    assert "execute store result score ORIG_RTS qz run gamerule randomTickSpeed" in _on
    for _s, _g in _PERF_BOOL_RULES:
        assert f"execute store result score {_s} qz run gamerule {_g}" in _on, (_s, _g)
    _first_cap = next(i for i, c in enumerate(_on) if c.startswith("execute store result"))
    _first_set = next(i for i, c in enumerate(_on) if c.startswith("gamerule "))
    assert _first_cap < _first_set, "must capture before disabling"
    for _dis in ("gamerule randomTickSpeed 0", "gamerule doMobSpawning false",
                 "gamerule doFireTick false", "gamerule doWeatherCycle false",
                 "gamerule doDaylightCycle false", "scoreboard players set PERF qz 1"):
        assert _dis in _on, _dis
    _off = perfoff_fn("qz")
    assert _off[0] == "execute unless score PERF qz matches 1 run return 0", _off[0]
    # booleans restored from captured 0/1
    for _s, _g in _PERF_BOOL_RULES:
        assert f"execute if score {_s} qz matches 0 run gamerule {_g} false" in _off
        assert f"execute if score {_s} qz matches 1 run gamerule {_g} true" in _off
    # randomTickSpeed enumerated 0..3 + a 4.. fallback to 3 (+ a warn tellraw)
    for _v in (0, 1, 2, 3):
        assert (f"execute if score ORIG_RTS qz matches {_v} run gamerule "
                f"randomTickSpeed {_v}") in _off, _v
    assert "execute if score ORIG_RTS qz matches 4.. run gamerule randomTickSpeed 3" in _off
    assert any(c.startswith("execute if score ORIG_RTS qz matches 4.. run tellraw")
               for c in _off), "missing >3 fallback tellraw"
    assert "scoreboard players set PERF qz 0" in _off
    print("ok: perfon/perfoff capture-then-disable + precise enumerated restore")

    # ── bossbars: three ids (four with pro), idempotent init, tracker, teardown ──
    _bi = bossbar_init_lines("qz", with_pro=False)
    for _bid, _lbl, _col in _BOSSBAR_DEFS:
        assert f"bossbar remove qz:{_bid}" in _bi                       # remove before add
        assert f'bossbar add qz:{_bid} {{"text":"[qz] {_lbl}"}}' in _bi
        assert f"bossbar set qz:{_bid} color {_col}" in _bi
        assert f"bossbar set qz:{_bid} visible false" in _bi
        assert _bi.index(f"bossbar remove qz:{_bid}") < \
            _bi.index(f'bossbar add qz:{_bid} {{"text":"[qz] {_lbl}"}}')
    assert not any("qz:pro" in c for c in _bi), "pro bar must be off without protection"
    _bip = bossbar_init_lines("qz", with_pro=True)
    assert 'bossbar add qz:pro {"text":"[qz] 保护壳施工中"}' in _bip
    assert "bossbar set qz:pro color yellow" in _bip
    assert bossbar_show("qz", "bld", 7) == [
        "bossbar set qz:bld max 7", "bossbar set qz:bld players @a",
        "bossbar set qz:bld visible true"]
    assert bossbar_hide("qz", "pre") == "bossbar set qz:pre visible false"
    assert bossbar_track("qz", "bld", "BLD") == (
        "execute if score BLD qz matches 0.. store result bossbar qz:bld value "
        "run scoreboard players get BLD qz")
    assert bossbar_remove_all("qz", with_pro=True) == [
        "bossbar remove qz:bld", "bossbar remove qz:clr", "bossbar remove qz:pre",
        "bossbar remove qz:pro"]
    assert bossbar_remove_all("qz", with_pro=False) == [
        "bossbar remove qz:bld", "bossbar remove qz:clr", "bossbar remove qz:pre"]
    # the bossbar tracker survives direction rotation unchanged (no coords)
    assert rotate_command(bossbar_track("qz", "clr", "CLR"), "-Z", 0, 0) == \
        bossbar_track("qz", "clr", "CLR")
    print("ok: bossbar init(idempotent)/show/hide/track/remove_all + rotation-safe")

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
