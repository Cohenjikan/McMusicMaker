# -*- coding: utf-8 -*-
"""generators/swave.py — Family A S-wave (marching-pulse) generator.

Adapts the user-verified oracle ``poc/48_build_swave_multi.py`` (multi-instrument
mirror-balanced S-wave / folded marching pulse + melody-sustain cut), with ONE
structural change demanded by the skill contract:

    poc/48 read its geometry knobs from ``argv``; THIS generator consumes them from
    the validated designer ``params`` dict, and routes ALL plumbing through
    ``redpiano_core`` (Datapack, Grid collision guard, InstrumentMap.resolve with
    octave-shift, plan_melody_cuts, forceload_guard, labeled_button,
    tickrate_command_block, version profile). NO hardcoded pack_format, NO hardcoded
    world path, NO unconditional deploy.

The verified geometry/timing is copied FAITHFULLY from poc/48 and must NOT be
re-derived (the marching forms are user-confirmed OK):
  * cells[] continuous folded timeline (trigger-tick union -> unique repeater skeleton);
  * repeater skeleton (delay 1..4) with the RFACE facing table (verified +X output);
  * 0-delay redstone-dust U-turn bridges at ``turns``;
  * chord3 radiate (above + 2 sides) per trigger cell;
  * dual-track Z-mirror (second track mirrored about the path mid-axis) + greedy
    left/right voice balance;
  * per-path forceload (X-strided) via core.forceload_guard;
  * the (T0+OFFSET)*2 game-tick arrival math for the absolute melody-cut schedule.

Exposes EXACTLY (SHARED INTERFACE):

    def build(notes, params, imap, profile, ns, origin, out_dir, deploy_dir=None) -> dict

``notes`` are the SHARED-INTERFACE note dicts:
    {'t', 'dur', 'midi', 'vel', 'family' in {'pno','bass','lead','pad','drum'},
     'drum_type'}.
Returns a stats dict with at least: note_count, dropped, octave_shifted,
forceload_chunks, duration_s, plus swave-specific cells/turns/x_span.
"""

import logging
import os
from collections import defaultdict

# Make sibling modules importable whether this is imported as a package
# (skill.scripts.generators.swave) or run from skill/scripts on sys.path.
import sys as _sys
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in _sys.path:
    _sys.path.insert(0, _SCRIPTS_DIR)

import redpiano_core as core               # noqa: E402
from redpiano_core import RedPianoError    # noqa: E402
from params_schema import assert_supported  # noqa: E402

log = logging.getLogger("redpiano.swave")


# ─────────────────────────────────────────────────────────────────────────────
# Verified constants (poc/48 L54-71) — DO NOT re-derive.
# ─────────────────────────────────────────────────────────────────────────────
TPS = 80
VOICES = 6                                # per-cell polyphony cap (poc/48 L54)
PULSE = 4                                 # pulse width in game-ticks (poc/48 L54)
LAMP = "minecraft:redstone_lamp"
BATCH = 2000
SSTOP = "stopsound @a"
CUT_INSTR = {"pad", "lead", "bass"}       # sustaining non-piano -> cut (poc/48 L57)
MIN_CUT_GT = 4                            # cut-delay floor in game-ticks (poc/48 L58)

# repeater facing table — verified: facing=west outputs +X, etc. (poc/48 L66-71).
RFACE = {
    (1, 0): "west",
    (-1, 0): "east",
    (0, 1): "north",
    (0, -1): "south",
}

# continuous S-wave path: +X, +Z, +X, -Z, repeat (poc/48 L214).
DIRS = [(1, 0), (0, 1), (1, 0), (0, -1)]


def build(notes, params, imap, profile, ns, origin, out_dir, deploy_dir=None):
    """Build the S-wave (marching-pulse) RedPiano machine. See module docstring."""
    # ── 0. fail loudly on unimplemented designer features BEFORE any geometry ──
    form = _get(params, "form", "swave")
    if form not in ("swave", "straight", "custom"):
        form = "swave"
    assert_supported(params, form)

    # ── geometry knobs from validated params (poc/48 defaults if absent) ───────
    XRUN = int(_get(params, "XRUN", 3))
    ZMAX = int(_get(params, "ZMAX", 4))
    base_block = _get(params, "base_block", "minecraft:stone")
    PASS = base_block                       # the conductive base/PASS block
    name = _get(params, "song", None) or "untitled"
    melcap_s = float(_get(params, "melcap_s", 1.2))
    dual_track = bool(_get(params, "dual_track_mirror", True))
    # designer track_sep override (DERIVED default -> None -> use poc PATH_ZSPAN+3)
    track_sep_override = _get(params, "track_sep", None)

    if XRUN < 2:
        raise RedPianoError("XRUN must be >= 2")
    if ZMAX < 2:
        raise RedPianoError("ZMAX must be >= 2")

    # ── origin: CLI --origin (X, Z, Y) overrides params start_* (handled upstream)
    OX, OZ, Y = int(origin[0]), int(origin[1]), int(origin[2])

    if not notes:
        raise RedPianoError("swave.build: empty notes list — nothing to build")

    # ── 1. quantize + greedy dual-track balance; collect cut data ──────────────
    U = 2.0 / TPS
    octave_shifted = [0]   # signed-nonzero resolve count (octave shifts applied)
    clamp_sentinel = [0]   # resolves that hit the clamp sentinel (could not fit)

    bycell = defaultdict(list)
    for n in notes:
        if n.get("vel", 1.0) >= 0.04:
            bycell[round(n["t"] / U)].append(n)

    n_tracks = 2 if dual_track else 1
    # per-cell capacity = min(global VOICES cap, total track slots = n_tracks*3). Without
    # this, a single-track config (dual_track_mirror=false) admits VOICES=6 notes but has
    # only 3 slots, so the slot-assign min() below hits an empty choices list and raises a
    # raw traceback. Cap honestly and count the rest as dropped.
    CELL_CAP = min(VOICES, n_tracks * 3)
    trackvoice = [[dict(), dict(), dict()] for _ in range(n_tracks)]
    track_note_counts = [0] * n_tracks
    track_tick_counts = [0] * n_tracks
    dropped = 0
    cut_events = set()
    meldur = {}              # tick -> longest cut-instr MIDI duration (s) in that cell
    instr_count = defaultdict(int)

    def _resolve(n):
        instr = _instr_of(n)
        r = imap.resolve(int(n["midi"]), float(n.get("vel", 0.7)), instr)
        sh = r.shifted_octaves
        if sh:
            if abs(sh) == core.OCTAVE_SHIFT_CLAMP_SENTINEL:
                clamp_sentinel[0] += 1
            else:
                octave_shifted[0] += 1
        return instr, r

    for tick in sorted(bycell):
        grp = bycell[tick]
        g = sorted(grp, key=lambda x: -x["midi"])      # keep highest pitches (poc/48 L148)
        placed = g[:CELL_CAP]
        slots = [[] for _ in range(n_tracks)]
        for nn in placed:
            choices = [tt for tt in range(n_tracks) if len(slots[tt]) < 3]
            target = min(choices,
                         key=lambda tt: (track_note_counts[tt] + len(slots[tt]), tt))
            slots[target].append(nn)
        for tt in range(n_tracks):
            if slots[tt]:
                track_tick_counts[tt] += 1
            for p, nn in enumerate(slots[tt]):
                instr, r = _resolve(nn)
                trackvoice[tt][p][tick] = (r.block, r.note_value)
                track_note_counts[tt] += 1
                instr_count[instr] += 1
                if instr in CUT_INSTR:
                    cut_events.add(r.sound_event)
                    md = float(nn.get("dur", 0.1))
                    meldur[tick] = md if tick not in meldur else max(meldur[tick], md)
        dropped += max(0, len(g) - CELL_CAP)

    # ── 2. shared timeline cells[]: trigger-tick union -> unique skeleton (poc/48 L168)
    trig = sorted(bycell)
    OFFSET = 1 if trig and trig[0] == 0 else 0
    cells = []
    prev = 0
    for T0 in trig:
        T = T0 + OFFSET
        G = T - prev
        reps = [4] * (G // 4) + ([G % 4] if G % 4 else [])
        if not reps:
            reps = [1]
        for d in reps:
            cells.append(("rep", d))
        cells.append(("trig", T0))
        prev = T

    # timing self-check (poc/48 L184-189) — preserved verbatim.
    cum = 0
    for kind, v in cells:
        if kind == "rep":
            cum += v
        else:
            if cum != v + OFFSET:
                raise RedPianoError(
                    f"timeline misalignment @tick {v}: cum={cum} != {v + OFFSET}")

    used_trig = [v for kind, v in cells if kind == "trig"]
    used_trig_set = set(used_trig)
    MAXTICK = max(used_trig) if used_trig else 0

    # ── 3. melody-sustain cut plan via core scheduler (absolute mode, poc/48 L198) ─
    mel_events = [
        (tk, meldur[tk], _event_for_cell(tk, notes, U, imap))
        for tk in sorted(meldur) if tk in used_trig_set
    ]
    # the sound_event used for the schedule key is irrelevant (the cut is event-level
    # and fires every cut_event); but plan_melody_cuts needs a per-cell event for the
    # polyphony WARN. Use the cell's dominant cut-instr event.
    plan = core.plan_melody_cuts(
        mel_events, tps=TPS, melcap_s=melcap_s, min_cut_gt=MIN_CUT_GT,
        offset=OFFSET, absolute=True,
    )
    mel_ticks = sorted(plan.delays_by_cell)
    # cut_events drives the cutmel body; union the resolved cut events with the plan's.
    cut_events_sorted = sorted(set(cut_events) | set(plan.cut_events))

    # ── 4. path layout — swave (default) / straight / custom waypoints ──────────
    #   straight & custom reuse the SAME downstream plumbing (RFACE, dual mirror,
    #   per-path forceload, melody-cut); only the spine differs. The collision guard
    #   (Grid.put) + timeline self-check above are the safety net: a self-intersecting
    #   or mis-timed path raises, never produces a silent broken machine.
    if form == "straight":
        pos, turns = _layout_straight(cells)
    elif form == "custom":
        pos, turns = _layout_custom(cells, _get(params, "waypoints", None))
    else:
        SEGLENS = [XRUN, ZMAX - 1, XRUN, ZMAX - 1]
        pos, turns = _layout_swave(cells, XRUN, ZMAX, SEGLENS)
    path_x = [p[0] for p in pos]
    path_z = [p[1] for p in pos]
    if turns:
        path_x += [p[0] for p in turns]
        path_z += [p[1] for p in turns]
    PATH_ZMIN = min(path_z) if path_z else 0
    PATH_ZMAX = max(path_z) if path_z else 0
    PATH_XSPAN = max(path_x) - min(path_x) + 1 if path_x else 1
    PATH_ZSPAN = PATH_ZMAX - PATH_ZMIN + 1 if path_z else 1
    TRACK_SEP = (int(track_sep_override) if track_sep_override is not None
                 else PATH_ZSPAN + 3)
    TRACK_Z = [OZ + i * TRACK_SEP for i in range(n_tracks)]

    # Playhead coords for the particle editor: the track-0 melody note block (chord3's
    # "above" note at Y+1) for each TRIGGER cell. This is the SINGLE SOURCE OF TRUTH —
    # the editor loads this exact list instead of re-deriving the S-wave spine in JS
    # (the JS re-derivation drifted: wrong cell-index + turn timing). Mirrors
    # track_transform(track=0): x = OX+xo, z = TRACK_Z[0] + (zo - PATH_ZMIN).
    playhead_cells = [
        {"tick": cells[i][1], "x": OX + xo,
         "y": Y + 1, "z": TRACK_Z[0] + (zo - PATH_ZMIN)}
        for i, (xo, zo, _d) in enumerate(pos) if cells[i][0] == "trig"
    ]

    def track_transform(track, xo, zo, d):
        local_z = zo - PATH_ZMIN
        if track == 0:
            return xo, TRACK_Z[track] + local_z, d
        mirror_z = PATH_ZSPAN - 1 - local_z
        return xo, TRACK_Z[track] + mirror_z, (d[0], -d[1])

    def track_turn(track, xo, zo):
        local_z = zo - PATH_ZMIN
        if track == 0:
            return xo, TRACK_Z[track] + local_z
        mirror_z = PATH_ZSPAN - 1 - local_z
        return xo, TRACK_Z[track] + mirror_z

    # ── 5. emit setblocks through the collision-guarded Grid (poc/48 L283-339) ──
    grid = core.Grid()

    def side_offsets(d):
        if d[0] != 0:
            return (0, 1), (0, -1)
        return (1, 0), (-1, 0)

    def chord3(out, x, z, d, vlist):
        above, side_a, side_b = vlist
        grid.put(out, x, Y - 1, z, LAMP)
        grid.put(out, x, Y, z, above[0] if above else PASS)
        if above:
            grid.put(out, x, Y + 1, z, f"minecraft:note_block[note={above[1]}]")
            grid.put(out, x, Y + 2, z, "air")
        off_a, off_b = side_offsets(d)
        if side_a:
            ax, az = x + off_a[0], z + off_a[1]
            grid.put(out, ax, Y - 1, az, side_a[0])
            grid.put(out, ax, Y, az, f"minecraft:note_block[note={side_a[1]}]")
            grid.put(out, ax, Y + 1, az, "air")
        if side_b:
            bx, bz = x + off_b[0], z + off_b[1]
            grid.put(out, bx, Y - 1, bz, side_b[0])
            grid.put(out, bx, Y, bz, f"minecraft:note_block[note={side_b[1]}]")
            grid.put(out, bx, Y + 1, bz, "air")

    def emit_track(t):
        start_xo, start_zo, _ = pos[0]
        _, src_z, _ = track_transform(t, start_xo, start_zo, (1, 0))
        # pulse-source conductive base one block before X origin (poc/48 L324)
        out = [f"setblock {OX - 1} {Y - 1} {src_z} {PASS}"]
        for i, (xo, zo, d) in enumerate(pos):
            mxo, z, md = track_transform(t, xo, zo, d)
            x = OX + mxo
            kind, v = cells[i]
            if kind == "rep":
                grid.put(out, x, Y - 1, z, LAMP)
                grid.put(out, x, Y, z,
                         f"minecraft:repeater[facing={RFACE[md]},delay={v}]")
            else:
                vals = [trackvoice[t][p].get(v) for p in range(3)]
                chord3(out, x, z, md, vals)
        for xo, zo in turns:
            txo, tz = track_turn(t, xo, zo)
            grid.put(out, OX + txo, Y - 1, tz, PASS)
            grid.put(out, OX + txo, Y, tz, "minecraft:redstone_wire")
        return out

    build_cmds = ["gamerule commandModificationBlockLimit 2147483647"]
    for t in range(n_tracks):
        build_cmds += emit_track(t)
    batches = core.batch_setblocks(build_cmds, batch=BATCH)

    # ── 6. forceload region via core guard (per-path X-strided, poc/48 L380-388) ─
    minx, minz, maxx, maxz = grid.bbox()
    WX0, WZ0, WX1, WZ1 = minx - 2, minz - 2, maxx + 2, maxz + 2
    auto_fold = bool(_get(params, "force_cap", False))
    flbuild = core.forceload_guard(WX0, WZ0, WX1, WZ1, auto_fold=auto_fold)
    forceload_chunks = ((WX1 // 16) - (WX0 // 16) + 1) * ((WZ1 // 16) - (WZ0 // 16) + 1)

    # ── 7. assemble datapack functions (poc/48 control surface, profile-driven) ─
    src_pts = []
    for t in range(n_tracks):
        start_xo, start_zo, _ = pos[0]
        _, src_z, _ = track_transform(t, start_xo, start_zo, (1, 0))
        src_pts.append((OX - 1, src_z))
    TRIG_CLEAR = [f"setblock {sx} {Y} {sz} minecraft:air" for sx, sz in src_pts]
    SCHED_CLEAR = [f"schedule clear {ns}:{f}"
                   for f in ("done", "fire", "firestop", "startbuild",
                             "unsil", "cutmel")]
    MUSIC_TICKS = (MAXTICK + OFFSET) * 2
    END_TICKS = MUSIC_TICKS + 200
    PBX = OX - 3
    CAMX = OX + PATH_XSPAN // 2
    CAMZ = (TRACK_Z[0] + TRACK_Z[-1] + PATH_ZSPAN) // 2

    # tick-rate command block (machine self-sets /tick rate 80 — CONTRACT §1.7).
    # placed beside the console; activated by setup via a redstone block on top.
    TRX, TRY, TRZ = PBX - 10, Y, OZ
    tickrate_setblock = core.tickrate_command_block(TRX, TRY, TRZ, rate=TPS)
    tickrate_fire = [f"setblock {TRX} {TRY + 1} {TRZ} minecraft:redstone_block",
                     f"schedule function {ns}:trclr 2t"]

    dp = core.Datapack(ns, name, out_dir, profile.mc_version)
    dp.write_pack_mcmeta(
        f"{ns} {name} multi-instrument mirror-balanced S-wave + melody-cut, tick{TPS}")
    dp.write_load_tick_tags()

    RESET = [f"scoreboard players set PLAY {ns} 0",
             f"scoreboard players set SIL {ns} 0"]

    # ---- control console (labeled buttons via core.labeled_button) ----
    ctl = ["gamerule commandModificationBlockLimit 2147483647"]
    sd = profile.sign_dialect   # version-aware sign NBT (string <=1.21.4 / SNBT >=1.21.5)
    ctl += core.labeled_button(PBX, Y, OZ, f"function {ns}:play",
                               ["[play]", "mirror S-wave", "full song"], sign_dialect=sd)
    ctl += core.labeled_button(PBX - 2, Y, OZ, f"function {ns}:view",
                               ["[overview]", "see mirror S", "lamp flow"], sign_dialect=sd)
    ctl += core.labeled_button(PBX - 4, Y, OZ, f"function {ns}:stop",
                               ["[stop]", "mute now", "if stuck"], sign_dialect=sd)
    ctl += core.labeled_button(PBX - 6, Y, OZ, f"function {ns}:cfg/polytoggle",
                               ["[poly gain]", "big chords", "anti-mud"], sign_dialect=sd)
    ctl += core.labeled_button(PBX - 8, Y, OZ, f"function {ns}:cfg/humantoggle",
                               ["[humanize]", "de-photocopy"], sign_dialect=sd)
    ctl += tickrate_setblock

    dp.write_function("load",
                      [f"scoreboard objectives add {ns} dummy",
                       f"scoreboard players set BLD {ns} -1",
                       f"scoreboard players set CLR {ns} -1"]
                      + RESET
                      + ["forceload remove all",
                         "scoreboard objectives add rpcfg dummy",
                         "scoreboard players set poly rpcfg 1",
                         "scoreboard players set human rpcfg 1"]
                      + SCHED_CLEAR
                      + TRIG_CLEAR
                      + [f'tellraw @a ["",{{"text":"[{ns}] {name} multi-instr mirror '
                         f'S-wave + melody-cut loaded. ","color":"aqua"}},'
                         f'{{"text":"need RedPiano + qzpno. /function {ns}:setup '
                         f'(self-sets /tick rate {TPS})"}}]'])

    dp.write_function("setup",
                      RESET
                      + ["gamemode creative @a", SSTOP,
                         f"scoreboard players set CLR {ns} -1"]
                      + SCHED_CLEAR
                      + TRIG_CLEAR
                      + tickrate_fire
                      + flbuild
                      + [f"tp @a {PBX} {Y + 3} {OZ}",
                         f"schedule function {ns}:startbuild 100t",
                         f'tellraw @a "[{ns}] reset+forceload; building S-wave..."'])

    # trclr: clear the transient tick-rate redstone trigger block back to air.
    dp.write_function("trclr", f"setblock {TRX} {TRY + 1} {TRZ} minecraft:air")

    dp.write_function(
        "startbuild",
        f"scoreboard players set BLD {ns} 0\n"
        f'tellraw @a "[{ns}] building mirror-balanced S-wave '
        f'x{PATH_XSPAN} z{maxz - minz + 1}..."')

    dp.write_function(
        "tick",
        f"execute if score BLD {ns} matches 0.. run function {ns}:buildstep\n"
        f"execute if score CLR {ns} matches 0.. run function {ns}:clearstep\n"
        f"execute if score SIL {ns} matches 1 run {SSTOP}")

    bs = core.build_tick_dispatch(ns, len(batches))
    # poc/48 names the build driver `buildstep` (not `tick`); keep that.
    dp.write_function("buildstep", bs)
    for k, b in enumerate(batches):
        dp.write_function(f"bld/b{k}", b)

    dp.write_function("placectl", ctl)
    dp.write_function(
        "builddone",
        f"scoreboard players set BLD {ns} -1\nfunction {ns}:placectl\n"
        f'tellraw @a ["",{{"text":"[{ns}] built. ","color":"green"}},'
        f'{{"text":"X~{PATH_XSPAN}, Z~{maxz - minz + 1}; press [play]/[overview]"}}]')

    dp.write_function(
        "cutmel",
        [f"stopsound @a record {ev}" for ev in cut_events_sorted]
        or [f"# {ns}: no melody-cut events (pure piano/drum)"])

    dp.write_function(
        "playcore",
        [f"scoreboard players set PLAY {ns} 1",
         f"scoreboard players set SIL {ns} 0", SSTOP,
         f"schedule clear {ns}:cutmel"]
        + TRIG_CLEAR
        + [f"schedule function {ns}:fire 2t"])

    dp.write_function(
        "play",
        [f'execute if score PLAY {ns} matches 1 run return run tellraw @a '
         f'"[{ns}] already playing, press [stop] first"',
         f"function {ns}:playcore",
         f'tellraw @a "[{ns}] GO. multi-instr mirror S-wave, melody sustain cut, '
         f'stand and listen."'])

    dp.write_function(
        "view",
        ["gamemode spectator @a",
         f"tp @a {CAMX} {Y + 55} {CAMZ} 0 90",
         f'tellraw @a "[{ns}] overview of mirror S-wave (spectator)."'])

    dp.write_function(
        "stop",
        RESET
        + ["gamemode creative @a", SSTOP]
        + SCHED_CLEAR
        + TRIG_CLEAR
        + [f"scoreboard players set SIL {ns} 1",
           f"schedule function {ns}:unsil {END_TICKS}t",
           f"tp @a {PBX} {Y + 3} {OZ}",
           f'tellraw @a "[{ns}] stopped (instant mute)."'])

    dp.write_function("unsil", f"scoreboard players set SIL {ns} 0")

    # fire: raise pulse (redstone block on each track source) + schedule absolute
    # melody cuts (relative to fire, append so they don't overwrite). poc/48 L486-490.
    fire_lines = list(flbuild)
    fire_lines += [f"setblock {sx} {Y} {sz} minecraft:redstone_block"
                   for sx, sz in src_pts]
    fire_lines += [f"schedule function {ns}:cutmel {plan.schedule_by_cell[tk]}t append"
                   for tk in mel_ticks]
    fire_lines += [f"schedule function {ns}:firestop {PULSE}t",
                   f"schedule function {ns}:done {END_TICKS}t"]
    dp.write_function("fire", fire_lines)
    dp.write_function("firestop", TRIG_CLEAR)
    dp.write_function(
        "done",
        RESET + ["gamemode creative @a",
                 f'tellraw @a "[{ns}] (end) replay [play]; teardown /function '
                 f'{ns}:cleanup."'])

    # ---- teardown (segmented fill clear), poc/48 L494-515 ----
    SEG = 200
    clr_segs = (WX1 - WX0 + 16) // SEG + 1
    for k in range(clr_segs):
        fx0 = WX0 + k * SEG
        fx1 = min(WX1, fx0 + SEG - 1)
        dp.write_function(f"clr/c{k}",
                          f"fill {fx0} {Y - 2} {WZ0} {fx1} {Y + 3} {WZ1} air")
    dp.write_function(
        "cleardone",
        [f"scoreboard players set CLR {ns} -1", "forceload remove all",
         f'tellraw @a "[{ns}] cleaned."'])
    cs = [f"execute if score CLR {ns} matches {k} run function {ns}:clr/c{k}"
          for k in range(clr_segs)]
    cs += [f"execute if score CLR {ns} matches {clr_segs} run function {ns}:cleardone",
           f"execute if score CLR {ns} matches 0..{clr_segs} run "
           f"scoreboard players add CLR {ns} 1"]
    dp.write_function("clearstep", cs)
    dp.write_function(
        "cleanup",
        ["gamerule commandModificationBlockLimit 2147483647"]
        + RESET
        + ["gamemode creative @a", SSTOP, f"scoreboard players set BLD {ns} -1"]
        + SCHED_CLEAR
        + TRIG_CLEAR
        + [f"scoreboard players set CLR {ns} 0",
           f'tellraw @a "[{ns}] tearing down..."'])

    dp.write_function(
        "cfg/polytoggle",
        ["scoreboard players set rptmp rpcfg 1",
         "scoreboard players operation rptmp rpcfg -= poly rpcfg",
         "scoreboard players operation poly rpcfg = rptmp rpcfg",
         f'execute if score poly rpcfg matches 1 run tellraw @a "[{ns}] poly gain ON"',
         f'execute if score poly rpcfg matches 0 run tellraw @a "[{ns}] poly gain OFF"'])
    dp.write_function(
        "cfg/humantoggle",
        ["scoreboard players set rptmp rpcfg 1",
         "scoreboard players operation rptmp rpcfg -= human rpcfg",
         "scoreboard players operation human rpcfg = rptmp rpcfg",
         f'execute if score human rpcfg matches 1 run tellraw @a "[{ns}] humanize ON"',
         f'execute if score human rpcfg matches 0 run tellraw @a "[{ns}] humanize OFF"'])

    # ── 8. deploy is OPT-IN (only when deploy_dir given) ───────────────────────
    deployed_to = None
    if deploy_dir is not None:
        deployed_to = dp.deploy(deploy_dir)

    # ── 9. stats ───────────────────────────────────────────────────────────────
    n_rep = sum(1 for kind, _ in cells if kind == "rep")
    n_trig = sum(1 for kind, _ in cells if kind == "trig")
    nplaced = sum(len(trackvoice[t][p]) for t in range(n_tracks) for p in range(3))
    song_s = (trig[-1] - trig[0]) * U if len(trig) > 1 else 0.0

    for w in plan.warnings:
        pass  # already logged by plan_melody_cuts

    stats = {
        "form": "swave",
        "note_count": nplaced,
        "dropped": dropped,
        "octave_shifted": octave_shifted[0],
        "octave_clamped": clamp_sentinel[0],
        "forceload_chunks": forceload_chunks,
        "duration_s": round(song_s, 2),
        # swave-specific
        "cells": len(cells),
        "turns": len(turns),
        "x_span": PATH_XSPAN,
        "z_span": maxz - minz + 1,
        "repeaters": n_rep,
        "trigger_cells": n_trig,
        "tracks": n_tracks,
        "mel_cut_cells": len(mel_ticks),
        "cut_events": len(cut_events_sorted),
        "median_cut_gt": plan.median_delay_gt,
        "instr_distribution": dict(instr_count),
        "warnings": list(plan.warnings),
        "out_dir": dp.root,
        "deployed_to": deployed_to,
        # single-source-of-truth playhead for the particle editor (track-0 melody notes)
        "playhead_cells": playhead_cells,
        "playhead_origin": [OX, Y, OZ],
    }
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (module-private)
# ─────────────────────────────────────────────────────────────────────────────

def _get(params, key, default):
    """params.get(key) but treat None (DERIVED-normalized) as 'absent' -> default."""
    if params is None:
        return default
    v = params.get(key, None)
    return default if v is None else v


def _instr_of(n):
    """SHARED-INTERFACE 'family' -> instrument-map key. The map uses the same
    names (pno/bass/lead/pad/drum); fall back to pno on anything unexpected."""
    fam = n.get("family", "pno")
    return fam if fam in ("pno", "bass", "lead", "pad", "drum") else "pno"


def _layout_swave(seq, XRUN, ZMAX, SEGLENS):
    """Continuous S-wave path layout — copied verbatim from poc/48 L218-250.
    Returns (pos, turns): pos[i] = (x, z, dir) per cell; turns = U-turn dust cells."""
    pos = [None] * len(seq)
    turns = []
    x = z = 0
    phase = 0
    d = DIRS[phase]
    segcount = 0
    for i, (kind, _) in enumerate(seq):
        pos[i] = (x, z, d)
        last = i == len(seq) - 1
        if last:
            break
        segcount += 1
        if phase in (0, 2):
            ready = segcount >= SEGLENS[phase]
        elif phase == 1:
            ready = z >= ZMAX
        else:
            ready = z <= 0
        want_turn = ready and seq[i + 1][0] == "rep"
        if want_turn:
            nd = DIRS[(phase + 1) % len(DIRS)]
            dust = (x + d[0], z + d[1])
            next_cell = (dust[0] + nd[0], dust[1] + nd[1])
            turns.append(dust)
            x, z = next_cell
            phase = (phase + 1) % len(DIRS)
            d = nd
            segcount = 0
        else:
            x += d[0]
            z += d[1]
    return pos, turns


def _layout_straight(seq):
    """Straight +X marching path: one cell per +X step, no turns. The degenerate
    case of the swave layout (a single horizontal segment) — reuses all downstream
    plumbing unchanged. Longest footprint; folds into swave for compactness."""
    return [(i, 0, (1, 0)) for i in range(len(seq))], []


def _normalize_waypoints(wps):
    """Designer waypoints -> list of (x, z) int tuples. Accepts {x,z} dicts or
    [x,z] pairs. The path SHAPE is what matters (origin is applied later), so the
    absolute waypoint coords are used as-is and the layout normalizes to (0,0)."""
    if not wps:
        raise RedPianoError(
            "custom form requires params['waypoints'] (a list of {x,z} points). "
            "Draw a route in layout_designer.html (自定义) and export its JSON."
        )
    out = []
    for w in wps:
        if isinstance(w, dict):
            out.append((int(w.get("x", 0)), int(w.get("z", 0))))
        elif isinstance(w, (list, tuple)) and len(w) >= 2:
            out.append((int(w[0]), int(w[1])))
        else:
            raise RedPianoError(f"bad waypoint {w!r}; expected {{x,z}} or [x,z]")
    return out


def _layout_custom(seq, waypoints):
    """Waypoint custom path. Lifted VERBATIM from the verified poc/47 ``layout_custom``
    (same (x,z,dir) + dust-turns format as ``_layout_swave``), normalized so the first
    cell sits at (0,0). Hard-fails (TC-4) if the drawn path is too short to cover every
    cell — never silently runs the pulse off the end of the user's route."""
    ncells = len(seq)
    wps = _normalize_waypoints(waypoints)
    if len(wps) < 2:
        raise RedPianoError("custom form needs >= 2 waypoints in params['waypoints']")
    # expand waypoints into unit steps (X first, then Z — matches the designer)
    steps = []
    cx, cz = wps[0]
    for k in range(1, len(wps)):
        tx, tz = wps[k]
        while cx != tx:
            s = 1 if tx > cx else -1
            steps.append((s, 0)); cx += s
        while cz != tz:
            s = 1 if tz > cz else -1
            steps.append((0, s)); cz += s
    if len(steps) < ncells:
        raise RedPianoError(
            f"custom path too short: waypoints yield {len(steps) + 1} cells but the "
            f"song needs {ncells}. Extend the drawn route — refusing to run the pulse "
            f"off the end of the path."
        )
    # walk, normalized to (0,0), inserting a 0-delay dust bridge at each turn.
    x, z = 0, 0
    if not steps:
        return [(0, 0, (1, 0))], []
    pos = [(0, 0, steps[0])]
    turns = []
    curd = steps[0]
    si = 1
    while len(pos) < ncells:
        sd = steps[si] if si < len(steps) else curd
        si += 1
        if sd == curd:
            x += sd[0]; z += sd[1]
            pos.append((x, z, sd))
        else:
            turns.append((x + curd[0], z + curd[1]))
            x += curd[0] + sd[0]; z += curd[1] + sd[1]
            pos.append((x, z, sd)); curd = sd
    return pos[:ncells], turns


def _event_for_cell(tick, notes, U, imap):
    """Resolve a representative cut-instr sound event for a cell, for the
    plan_melody_cuts polyphony WARN (event-level cut shares one event). Picks the
    longest cut-instr note quantizing to ``tick``; falls back to a sentinel event."""
    best = None
    best_dur = -1.0
    for n in notes:
        if round(n["t"] / U) != tick:
            continue
        if _instr_of(n) not in CUT_INSTR:
            continue
        if float(n.get("dur", 0.0)) > best_dur:
            best_dur = float(n.get("dur", 0.0))
            best = n
    if best is None:
        return f"{imap.instruments.get('pad', {}).get('_ns', 'qzpno')}:cut_cell_{tick}"
    r = imap.resolve(int(best["midi"]), float(best.get("vel", 0.7)), _instr_of(best))
    return r.sound_event
