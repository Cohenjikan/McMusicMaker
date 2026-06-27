# -*- coding: utf-8 -*-
"""multilane.py — v1 generator: 多轨分布(每声部一轨)直线行进脉冲机器.

Promoted from the verified lab build poc/49 (`olkml`, geometry confirmed in-game).
Distinct topology from swave: instead of ONE folded line with radiate chords, each
voice gets its OWN parallel +X lane, all sharing one repeater skeleton (absolute
column-aligned sync, the old 24/30 model). Optional signal tracks = pure repeater
chains (no note blocks) for the player to place command blocks beside (粒子 sync).

Geometry/lifecycle copied faithfully from poc/49; plumbing routed through
redpiano_core (version-aware pack_format + function folder, opt-in deploy) and the
multi-instrument map (octave-shift, not silent clamp). The forceload soft-cap is a
SOFT warning (footprint/perf on weak hardware), NOT a guaranteed audio drop — over the
cap it refuses unless --force-cap is given, then it WARNs and builds anyway (user-tested
~428 chunks with no dropped notes). For a smaller footprint use the folded S-wave form.

SHARED INTERFACE:
    def build(notes, params, imap, profile, ns, origin, out_dir, deploy_dir=None) -> dict
"""

import os
import sys as _sys
from collections import defaultdict

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in _sys.path:
    _sys.path.insert(0, _SCRIPTS_DIR)

import redpiano_core as core  # noqa: E402
from redpiano_core import RedPianoError  # noqa: E402
from params_schema import assert_supported  # noqa: E402

TPS, PULSE, BATCH = 80, 4, 2000
U = 2.0 / TPS
CUT_INSTR = {"pad", "lead", "bass"}
MIN_CUT_GT = 4
MELCAP_S_DEFAULT = 1.2
RFACE = "west"               # +X pulse (poc/48 verified)
SSTOP = "stopsound @a"


def _get(params, key, default):
    if params is None:
        return default
    v = params.get(key, None)
    return default if v is None else v


def _instr_of(n):
    fam = n.get("family", n.get("instr", "pno"))
    return fam if fam in ("pno", "bass", "lead", "pad", "drum") else "pno"


def build(notes, params, imap, profile, ns, origin, out_dir, deploy_dir=None):
    """Build the multilane (one-lane-per-voice) straight marching machine."""
    # 0. fail loudly on unimplemented designer features first
    assert_supported(params, "multilane")

    if not notes:
        raise RedPianoError("multilane.build: empty notes list — nothing to build")

    OX, OZ, Y = int(origin[0]), int(origin[1]), int(origin[2])
    BASE = _get(params, "base_block", "minecraft:stone")
    name = _get(params, "song", None) or ns
    melcap_s = float(_get(params, "melcap_s", MELCAP_S_DEFAULT))
    MAXPOLY = int(_get(params, "max_poly", 7))
    lane_dz = int(_get(params, "lane_dz", 2))
    LANES = _get(params, "lane_offsets", None) or [
        {"z": i * lane_dz, "y": 0} for i in range(MAXPOLY)
    ]
    NLANE = len(LANES)
    SIGS = _get(params, "signal_tracks", None) or []

    ffolder = profile.function_folder   # honored via core.Datapack, kept for reference

    # 1. quantize + per-lane voice assignment (high->low pitch into lanes 0..NLANE-1)
    octave_shifted = [0]
    bycell = defaultdict(list)
    for n in notes:
        if n.get("vel", 1.0) >= 0.04:
            bycell[round(n["t"] / U)].append(n)
    trig = sorted(bycell)
    lane_voices = [dict() for _ in range(NLANE)]
    lane_counts = [0] * NLANE
    cut_events = set()
    meldur = {}
    mel_event_of = {}        # tick -> sound_event of the longest cut-instr note in that cell
    _mel_best_dur = {}       # tick -> that note's dur (s), to pick the longest
    instr_count = defaultdict(int)
    dropped = 0

    def _resolve(n):
        instr = _instr_of(n)
        r = imap.resolve(int(n["midi"]), float(n.get("vel", 0.7)), instr)
        if r.shifted_octaves and abs(r.shifted_octaves) != core.OCTAVE_SHIFT_CLAMP_SENTINEL:
            octave_shifted[0] += 1
        return instr, r

    for tk in trig:
        g = sorted(bycell[tk], key=lambda x: -x["midi"])[:NLANE]
        dropped += max(0, len(bycell[tk]) - NLANE)
        for li, n in enumerate(g):
            instr, r = _resolve(n)
            lane_voices[li][tk] = (r.block, r.note_value)
            lane_counts[li] += 1
            instr_count[instr] += 1
            if instr in CUT_INSTR:
                cut_events.add(r.sound_event)
                md = float(n.get("dur", 0.1))
                meldur[tk] = md if tk not in meldur else max(meldur[tk], md)
                # per-cell representative cut event = the longest cut-instr note's
                # event (for plan_melody_cuts' polyphony WARN; cut is event-level).
                if md >= _mel_best_dur.get(tk, -1.0):
                    _mel_best_dur[tk] = md
                    mel_event_of[tk] = r.sound_event

    # 2. shared timeline cells[] (rep delays + trig) — identical to swave/47/48
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
    cum = 0
    for kind, v in cells:
        if kind == "rep":
            cum += v
        else:
            if cum != v + OFFSET:
                raise RedPianoError(f"timeline misalignment @tick {v}: cum={cum} != {v + OFFSET}")
    used_trig = [v for k, v in cells if k == "trig"]
    used_trig_set = set(used_trig)
    MAXTICK = max(used_trig) if used_trig else 0

    # 3. melody-sustain cut via core scheduler (absolute game-tick schedule).
    #    Routes through core.plan_melody_cuts so the contract's cut-floor assertion
    #    (MIN_CUT_GT can never push a cut past the next onset) is enforced — a dense
    #    melody now HARD-FAILS instead of silently clipping the next note's attack.
    mel_events = [
        (tk, meldur[tk], mel_event_of[tk])
        for tk in sorted(meldur) if tk in used_trig_set
    ]
    plan = core.plan_melody_cuts(
        mel_events, tps=TPS, melcap_s=melcap_s, min_cut_gt=MIN_CUT_GT,
        offset=OFFSET, absolute=True,
    )
    mel_ticks = sorted(plan.delays_by_cell)
    cut_sched = plan.schedule_by_cell
    # cut_events drives the cutmel body; union resolved cut events with the plan's.
    cut_events = sorted(set(cut_events) | set(plan.cut_events))
    median_cut_gt = plan.median_delay_gt

    # 4. emit setblocks + collision guard (core.Grid)
    grid = core.Grid()
    build_cmds = ["gamerule commandModificationBlockLimit 2147483647"]
    sources = []   # (x,y,z) redstone source per chain

    def emit_chain(out, lz, ly, voices, lx=0):
        # lx/ly/lz = per-chain X/Y/Z offset off the origin. Voice lanes use lx=0 (they
        # share the +X spine); signal tracks may offset in 3D (dx/dy/dz).
        z = OZ + lz
        yb = Y + ly
        x0 = OX + lx
        grid.put(out, x0 - 1, yb - 1, z, BASE)
        sources.append((x0 - 1, yb, z))
        for i, (kind, v) in enumerate(cells):
            x = x0 + i
            if kind == "rep":
                grid.put(out, x, yb - 1, z, BASE)
                grid.put(out, x, yb, z, f"minecraft:repeater[facing={RFACE},delay={v}]")
            else:
                note = voices.get(v) if voices is not None else None
                grid.put(out, x, yb - 1, z, BASE)
                grid.put(out, x, yb, z, note[0] if note else BASE)
                if note:
                    grid.put(out, x, yb + 1, z, f"minecraft:note_block[note={note[1]}]")
                    grid.put(out, x, yb + 2, z, "air")

    for li in range(NLANE):
        emit_chain(build_cmds, LANES[li]["z"], LANES[li].get("y", 0), lane_voices[li])
    # signal tracks: pure repeater chains for command-block particles. Now consume the
    # full 3D offset (dx/dy/dz) — previously dz only (poc/49 dropped dx/dy).
    for sg in SIGS:
        emit_chain(build_cmds, int(sg.get("dz", 0)), int(sg.get("dy", 0)), None,
                   lx=int(sg.get("dx", 0)))

    batches = core.batch_setblocks(build_cmds, BATCH)

    # 5. per-path forceload. The footprint ≈ the bounding box (a straight multilane can't
    #    fold itself). Over the SOFT cap this is a footprint/perf concern on weak hardware —
    #    NOT a guaranteed audio drop (user-tested ~428 chunks with no dropped notes). Honor
    #    --force-cap: without it, refuse a big footprint (and suggest swave); with it, WARN
    #    and build anyway. The forceload is already emitted one `add` per chunk (safe stride).
    occ = grid.occ
    chunks = sorted(set((x >> 4, z >> 4) for (x, _, z) in occ))
    NCH = len(chunks)
    force_cap = bool(params.get("force_cap")) if params else False
    if NCH > core.FORCELOAD_SOFT_CAP and not force_cap:
        raise RedPianoError(
            f"multilane footprint = {NCH} forceload chunks > soft cap {core.FORCELOAD_SOFT_CAP}. "
            f"A straight multilane ≈ its bounding box, so a long song has a large footprint that "
            f"may stress a weak server. Pass --force-cap to build it anyway (per-chunk forceload; "
            f"tested fine at ~428 chunks), or use --form swave (folded S-wave) for a smaller footprint."
        )
    if NCH > core.FORCELOAD_SOFT_CAP:
        core.log.warning(
            "multilane footprint %d chunks > soft cap %d; building anyway (--force-cap). "
            "Per-chunk forceload — a large footprint, not a guaranteed audio drop.",
            NCH, core.FORCELOAD_SOFT_CAP)
    flbuild = ["forceload remove all"] + [
        f"forceload add {cx * 16} {cz * 16}" for (cx, cz) in chunks
    ]

    allx = [k[0] for k in occ]
    allz = [k[2] for k in occ]
    ally = [k[1] for k in occ]
    WX0, WZ0, WX1, WZ1 = min(allx) - 2, min(allz) - 2, max(allx) + 2, max(allz) + 2
    WY0, WY1 = min(ally) - 2, max(ally) + 2

    # 6. datapack — via core.Datapack (version-aware pack_format + folder names)
    dp = core.Datapack(ns, name, out_dir, profile.mc_version,
                       direction=params.get("start_dir", "+X"), ox=OX, oz=OZ)
    dp.write_pack_mcmeta(
        f"{ns} 多轨分布式直线行进脉冲(每声部一轨, {NLANE}轨+{len(SIGS)}信号轨), tick80"
    )
    dp.write_load_tick_tags()

    MUSIC_TICKS = (MAXTICK + OFFSET) * 2
    END_TICKS = MUSIC_TICKS + 200
    PBX = OX - 3
    CAMX = OX + (max(allx) - min(allx)) // 2
    CAMZ = OZ + (max(allz) - min(allz)) // 2

    def lbtn(bx, cmd, lines):
        return core.labeled_button(bx, Y, OZ, cmd, lines,
                                   sign_dialect=profile.sign_dialect)

    ctl = ["gamerule commandModificationBlockLimit 2147483647"]
    ctl += lbtn(PBX, f"function {ns}:play", ["[直接播放]", "多轨分布", "听全曲", ""])
    ctl += lbtn(PBX - 2, f"function {ns}:view", ["[全景俯视]", "看多轨", "", ""])
    ctl += lbtn(PBX - 4, f"function {ns}:stop", ["[停止]", "立即静音", "", ""])
    ctl += lbtn(PBX - 6, f"function {ns}:cfg/polytoggle", ["[复音增益]", "大和弦防糊", "", ""])
    ctl += lbtn(PBX - 8, f"function {ns}:cfg/humantoggle", ["[微抖动]", "去复印感", "", ""])

    RESET = [f"scoreboard players set PLAY {ns} 0", f"scoreboard players set SIL {ns} 0"]
    SCHED_CLEAR = [f"schedule clear {ns}:{f}" for f in
                   ("done", "fire", "firestop", "startbuild", "unsil", "cutmel")]
    TRIG_CLEAR = [f"setblock {sx} {sy} {sz} minecraft:air" for (sx, sy, sz) in sources]

    dp.write_function("load",
        [f"scoreboard objectives add {ns} dummy",
         f"scoreboard players set BLD {ns} -1",
         f"scoreboard players set CLR {ns} -1"] + RESET
        + ["forceload remove all", "scoreboard objectives add rpcfg dummy",
           "scoreboard players set poly rpcfg 1", "scoreboard players set human rpcfg 1"]
        + SCHED_CLEAR + TRIG_CLEAR
        + [f'tellraw @a ["",{{"text":"[{ns}] 多轨分布式直线机 loaded. ","color":"aqua"}},'
           f'{{"text":"需RedPiano+qzpno. 手动 /tick rate 80 -> /function {ns}:setup -> 启用资源包 -> 按 [play]"}}]'])
    dp.write_function("setup",
        RESET + ["gamemode creative @a", SSTOP, f"scoreboard players set CLR {ns} -1"]
        + SCHED_CLEAR + TRIG_CLEAR + flbuild
        + [f"tp @a {PBX} {Y + 3} {OZ}", f"schedule function {ns}:startbuild 100t",
           f'tellraw @a "[{ns}] reset+forceload({NCH}区块); building 多轨..."'])
    dp.write_function("startbuild",
        f'scoreboard players set BLD {ns} 0\n'
        f'tellraw @a "[{ns}] building {NLANE}轨 + {len(SIGS)}信号轨, {len(cells)}cell..."')
    dp.write_function("tick",
        f"execute if score BLD {ns} matches 0.. run function {ns}:buildstep\n"
        f"execute if score CLR {ns} matches 0.. run function {ns}:clearstep\n"
        f"execute if score SIL {ns} matches 1 run {SSTOP}")
    bs = [f"execute if score BLD {ns} matches {k} run function {ns}:bld/b{k}"
          for k in range(len(batches))]
    bs += [f"execute if score BLD {ns} matches {len(batches)} run function {ns}:builddone",
           f"execute if score BLD {ns} matches 0..{len(batches)} run scoreboard players add BLD {ns} 1"]
    dp.write_function("buildstep", bs)
    for k, b in enumerate(batches):
        dp.write_function(f"bld/b{k}", b)
    dp.write_function("placectl", ctl)
    dp.write_function("builddone",
        f"scoreboard players set BLD {ns} -1\nfunction {ns}:placectl\n"
        f'tellraw @a ["",{{"text":"[{ns}] built. ","color":"green"}},'
        f'{{"text":"{NLANE}轨分布式直线; 按[直接播放]/[全景俯视]"}}]')
    dp.write_function("cutmel",
        [f"stopsound @a record {ev}" for ev in cut_events]
        or [f"# {ns}: 无旋律截断事件(纯钢琴/鼓)"])
    dp.write_function("playcore",
        [f"scoreboard players set PLAY {ns} 1", f"scoreboard players set SIL {ns} 0",
         SSTOP, f"schedule clear {ns}:cutmel"] + TRIG_CLEAR
        + [f"schedule function {ns}:fire 2t"])
    dp.write_function("play",
        [f'execute if score PLAY {ns} matches 1 run return run tellraw @a "[{ns}] 正在播放, 先[停止]"',
         f"function {ns}:playcore",
         f'tellraw @a "[{ns}] GO。多轨分布式直线, 站着听全曲。"'])
    dp.write_function("view",
        ["gamemode spectator @a", f"tp @a {CAMX} {Y + 80} {CAMZ} 0 90",
         f'tellraw @a "[{ns}] 俯视多轨(spectator)。"'])
    dp.write_function("stop",
        RESET + ["gamemode creative @a", SSTOP] + SCHED_CLEAR + TRIG_CLEAR
        + [f"scoreboard players set SIL {ns} 1",
           f"schedule function {ns}:unsil {END_TICKS}t",
           f"tp @a {PBX} {Y + 3} {OZ}", f'tellraw @a "[{ns}] 已停止。"'])
    dp.write_function("unsil", f"scoreboard players set SIL {ns} 0")
    fire_lines = flbuild + [f"setblock {sx} {sy} {sz} minecraft:redstone_block"
                            for (sx, sy, sz) in sources]
    fire_lines += [f"schedule function {ns}:cutmel {cut_sched[tk]}t append" for tk in mel_ticks]
    fire_lines += [f"schedule function {ns}:firestop {PULSE}t",
                   f"schedule function {ns}:done {END_TICKS}t"]
    dp.write_function("fire", fire_lines)
    dp.write_function("firestop", TRIG_CLEAR)
    dp.write_function("done",
        RESET + ["gamemode creative @a",
                 f'tellraw @a "[{ns}] (end) 重放[直接播放]; 拆 /function {ns}:cleanup。"'])
    SEG = 200
    clr_segs = (WX1 - WX0 + 16) // SEG + 1
    for k in range(clr_segs):
        fx0 = WX0 + k * SEG
        fx1 = min(WX1, fx0 + SEG - 1)
        dp.write_function(f"clr/c{k}", f"fill {fx0} {WY0} {WZ0} {fx1} {WY1} {WZ1} air")
    dp.write_function("cleardone",
        [f"scoreboard players set CLR {ns} -1", "forceload remove all",
         f'tellraw @a "[{ns}] cleaned."'])
    cs = [f"execute if score CLR {ns} matches {k} run function {ns}:clr/c{k}"
          for k in range(clr_segs)]
    cs += [f"execute if score CLR {ns} matches {clr_segs} run function {ns}:cleardone",
           f"execute if score CLR {ns} matches 0..{clr_segs} run scoreboard players add CLR {ns} 1"]
    dp.write_function("clearstep", cs)
    dp.write_function("cleanup",
        ["gamerule commandModificationBlockLimit 2147483647"] + RESET
        + ["gamemode creative @a", SSTOP, f"scoreboard players set BLD {ns} -1"]
        + SCHED_CLEAR + TRIG_CLEAR
        + [f"scoreboard players set CLR {ns} 0", f'tellraw @a "[{ns}] tearing down..."'])
    for nm, sc in (("polytoggle", "poly"), ("humantoggle", "human")):
        dp.write_function(f"cfg/{nm}",
            ["scoreboard players set rptmp rpcfg 1",
             f"scoreboard players operation rptmp rpcfg -= {sc} rpcfg",
             f"scoreboard players operation {sc} rpcfg = rptmp rpcfg",
             f'execute if score {sc} rpcfg matches 1 run tellraw @a "[{ns}] {sc} ON"',
             f'execute if score {sc} rpcfg matches 0 run tellraw @a "[{ns}] {sc} OFF"'])

    deployed = dp.deploy(deploy_dir) if deploy_dir else None

    duration_s = (notes and max(n["t"] + n.get("dur", 0.0) for n in notes)) or 0.0
    nnote = sum(1 for vv in occ.values() if vv.startswith("minecraft:note_block"))
    return {
        "note_count": sum(lane_counts),
        "input_notes": len(notes),
        "dropped": dropped,
        "octave_shifted": octave_shifted[0],
        "forceload_chunks": NCH,
        "duration_s": round(duration_s, 1),
        "cells": len(cells),
        "lanes": NLANE,
        "signal_tracks": len(SIGS),
        "lane_counts": lane_counts,
        "note_blocks": nnote,
        "mel_cut_cells": len(mel_ticks),
        "cut_count": len(mel_ticks),
        "median_cut_gt": median_cut_gt,
        "warnings": list(plan.warnings),
        "deployed": deployed,
        "out": dp.root,
    }
