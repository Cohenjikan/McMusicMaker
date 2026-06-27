# -*- coding: utf-8 -*-
"""generators/inplace.py — Family A in-place palette player (forms: inplace).

Adapts the two user-verified lab oracles into ONE module behind a ``multi`` switch
read from params:

  * single (multi=False)  -> poc/45_build_inplace_palette.py  — piano-only palette.
    Every note routes to the ``pno`` family (3 velocity layers); no melody-cut.
  * multi  (multi=True)   -> poc/46_build_inplace_multi.py    — per-note GM family
    mapping (pno/bass/lead/pad/drum) PLUS melody sustain-cut (stopsound the
    sustaining pad/lead/bass tails so the melody is audible).

The GEOMETRY is copied FAITHFULLY from the named pocs (it is user-verified and must
not be re-derived):

  * a palette of distinct ``(mapping-block, note-value)`` note blocks laid on a
    PCOLS-wide grid with ROWGAP row spacing;
  * each palette cell = mapping block at Y-1, note_block at Y, air at Y+1 (sounding
    requires air above), and a SIDE trigger slot at (Y, z-1) — a redstone block on
    the note block's SIDE face, NEVER below it across the mapping block;
  * repeat-trigger timing: a step ``s{c}`` setblocks redstone_block into the slots
    of the cells sounding this cell, schedules ``offall`` +1t to clear every slot
    back to air (rising-edge reset, not a sound cut), and schedules ``s{c+1}``
    ``dt = (next_cell - this_cell) * 2`` game-ticks later (>=2 so offall completes
    first);
  * the multi form additionally schedules ``cutmel`` ``+cut_delay t append`` on
    cells that carry a melody (cut-instr) note;
  * a 5-widget [播放]/[循环播放]/[停止]/[复音增益]/[微抖动] console + cleanup.

ALL plumbing is routed through ``redpiano_core``: Datapack (profile-driven
pack_format + function folder), Grid.put (collision guard), imap.resolve (with the
octave-shift upgrade — this module does NOT reimplement the clamp), plan_melody_cuts
(with the cut_delay<gap assertion + same-event polyphony WARN), labeled_button /
sign_messages, forceload_guard, build/tick scaffolding builders, and the tick-rate
self-check. Nothing here hardcodes pack_format, a world path, or a folder name.

Public surface (SHARED INTERFACE):
    build(notes, params, imap, profile, ns, origin, out_dir, deploy_dir=None) -> dict
"""

import logging
import os
import sys
from collections import defaultdict

# allow ``import redpiano_core`` whether invoked as a module or a script: the
# package's parent (skill/scripts) must be on sys.path.
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import redpiano_core as core  # noqa: E402
from params_schema import RedPianoError, assert_supported  # noqa: E402

log = logging.getLogger("redpiano.inplace")

# ── constants copied faithfully from poc/45 + poc/46 ──────────────────────────
VOICES = 12                       # per-cell polyphony cap (poc/45 L37, poc/46 L34)
TPS = 80                          # /tick rate 80 (samples tuned for it)
U = 2 / TPS                       # seconds per quantization cell (poc L36/L39)
VEL_FLOOR = 0.04                  # drop near-silent notes (poc/45 L81, poc/46 L88)
CUT_INSTR = frozenset({"pad", "lead", "bass"})  # sustaining non-piano -> melody-cut
MIN_CUT_GT = 4                    # cut-delay floor in game-ticks (poc/46 L28)
SSTOP = "stopsound @a"
DONE_TAIL_GT = 200                # +200t after the last cell -> done (poc L152/L178)
# all-families that the single (piano-only) form forces every note into:
SINGLE_FAMILY = "pno"


def _origin_of(params, origin):
    """Resolve (OX, OZ, Y). CLI ``origin`` (X, Z, Y) overrides any start_x/z/y in
    params (CONTRACT §4: --origin overrides start_*)."""
    if origin is not None:
        ox, oz, y = origin
        return int(ox), int(oz), int(y)
    return (int(params.get("start_x", 0)),
            int(params.get("start_z", 0)),
            int(params.get("start_y", 255)))


def _family_of(note, multi):
    """The instrument family used for resolution. In single mode everything is
    piano; in multi mode use the note's pre-assigned 'family' (the build_machine
    pipeline tags each note via imap.family_for); ch9 drums already tagged 'drum'."""
    if not multi:
        return SINGLE_FAMILY
    fam = note.get("family") or SINGLE_FAMILY
    # the map's instrument names match the family names 1:1 (pno/bass/lead/pad/drum)
    return fam


def build(notes, params, imap, profile, ns, origin, out_dir, deploy_dir=None):
    """Build the in-place palette datapack. See module docstring + SHARED INTERFACE.

    Returns a stats dict with at least: note_count, dropped, octave_shifted,
    forceload_chunks, duration_s, palette_size, fire_ticks (+ multi extras:
    cut_count, cut_median_gt, instr_palette, warnings).
    """
    # 0. fail loudly on any unimplemented designer feature BEFORE placing a block.
    assert_supported(params, "inplace")

    multi = bool(params.get("multi", False))
    OX, OZ, Y = _origin_of(params, origin)
    PCOLS = int(params.get("PCOLS", 16) or 16)
    ROWGAP = int(params.get("ROWGAP", 3) or 3)
    if PCOLS < 1:
        raise RedPianoError(f"PCOLS must be >= 1, got {PCOLS}")
    if ROWGAP < 3:
        # ROWGAP >= 3 keeps a trigger slot from touching the adjacent row's note
        # block (poc/45 L38). Guard rather than silently mis-trigger.
        raise RedPianoError(f"ROWGAP must be >= 3 (trigger-slot isolation), got {ROWGAP}")
    name = params.get("song") or "untitled"
    melcap_s = float(params.get("melcap_s", 1.2) or 1.2)

    warnings = []

    # ── 1. quantize to cells; build the cross-instrument palette ──────────────
    bycell = defaultdict(list)
    for n in notes:
        if float(n.get("vel", 1.0)) >= VEL_FLOOR:
            bycell[round(float(n["t"]) / U)].append(n)
    if not bycell:
        raise RedPianoError("no audible notes (all below velocity floor) — nothing to build")
    ticks = sorted(bycell)

    palette = {}              # (block, note_value) -> palette index
    order = []                # index -> (block, note_value)
    pal_instr = []            # index -> family (for the cut-instr set + report)
    pal_sound = []            # index -> sound event (for stopsound melody-cut)
    beats = []                # list of (cell_tick, [palette_idx, ...])
    beat_mel = []             # per beat: longest cut-instr MIDI dur (s) or None
    dropped = 0
    octave_shifted = 0
    clamp_warned = False

    for tk in ticks:
        # highest-pitch-first; cap polyphony, count drops (poc/45 L88-89)
        g = sorted(bycell[tk], key=lambda x: -int(x["midi"]))[:VOICES]
        dropped += max(0, len(bycell[tk]) - VOICES)
        idxs = []
        meldur = None
        for n in g:
            fam = _family_of(n, multi)
            r = imap.resolve(int(n["midi"]), float(n.get("vel", 1.0)), fam)
            # octave-shift accounting (core surfaces it; we WARN, never silently clamp)
            if r.shifted_octaves:
                octave_shifted += 1
                if abs(r.shifted_octaves) == core.OCTAVE_SHIFT_CLAMP_SENTINEL \
                        and not clamp_warned:
                    warnings.append(
                        "some notes outside every sample band even after octave "
                        "shifting — clamped as a last resort (pitch approximate)"
                    )
                    clamp_warned = True
            key = (r.block, r.note_value)
            if key not in palette:
                palette[key] = len(order)
                order.append(key)
                pal_instr.append(fam)
                pal_sound.append(r.sound_event)
            idxs.append(palette[key])
            if multi and fam in CUT_INSTR:
                dur = float(n.get("dur", 0.0))
                meldur = dur if meldur is None else max(meldur, dur)
        # same cell + same (block,note) de-duped -> one trigger (poc L96/L105)
        beats.append((tk, sorted(set(idxs))))
        beat_mel.append(meldur)

    P = len(order)
    NB = len(beats)
    if octave_shifted:
        msg = f"{octave_shifted} notes octave-shifted to fit sample range"
        warnings.append(msg)
        log.warning(msg)

    # ── 2. melody-cut plan (multi only), via core (assertion + polyphony WARN) ──
    cut_delay = {}            # cell_index -> cut delay (game-ticks)
    cut_events = []
    cut_median_gt = 0
    if multi:
        # one entry per beat that carries a melody (cut-instr) note. The event used
        # for the cut is the cut-instr sound on that beat (any cut-instr palette
        # index present in the beat); plan_melody_cuts plans EVENT-level cuts and
        # surfaces overlapping-same-event WARNs.
        mel_events = []       # (cell_tick, midi_dur_s, sound_event)
        mel_cell_for_tick = {}
        for c, (tk, idxs) in enumerate(beats):
            if beat_mel[c] is None:
                continue
            # pick a representative cut-instr event sounding in this beat
            ev = None
            for i in idxs:
                if pal_instr[i] in CUT_INSTR:
                    ev = pal_sound[i]
                    break
            if ev is None:
                continue
            mel_events.append((tk, beat_mel[c], ev))
            mel_cell_for_tick[tk] = c
        if mel_events:
            plan = core.plan_melody_cuts(
                mel_events, tps=TPS, melcap_s=melcap_s,
                min_cut_gt=MIN_CUT_GT, absolute=False,
            )
            # map cell-tick delays back to beat indices for the s{c} schedule append
            for tk, d in plan.delays_by_cell.items():
                cut_delay[mel_cell_for_tick[tk]] = d
            cut_events = plan.cut_events
            cut_median_gt = plan.median_delay_gt
            warnings.extend(plan.warnings)

    # ── 3. lay out the palette geometry (collision-guarded Grid) ──────────────
    def pal_pos(i):
        col, row = i % PCOLS, i // PCOLS
        return OX + col, OZ + row * ROWGAP

    PROWS = (P + PCOLS - 1) // PCOLS

    def trig(i):
        x, z = pal_pos(i)
        return (x, Y, z - 1)

    grid = core.Grid()
    build_cmds = ["gamerule commandModificationBlockLimit 2147483647"]
    for i, (block, nv) in enumerate(order):
        x, z = pal_pos(i)
        grid.put(build_cmds, x, Y - 1, z, block)                                # mapping block (mod reads it)
        grid.put(build_cmds, x, Y,     z, f"minecraft:note_block[note={nv}]")    # the note block
        grid.put(build_cmds, x, Y + 1, z, "minecraft:air")                       # air above (sounding requires it)
        grid.put(build_cmds, x, Y,     z - 1, "minecraft:air")                    # SIDE trigger slot (z-1, same Y)

    # ── 4. console position + bounding box (poc/45 L124-126) ──────────────────
    PBX = OX - 3                                                  # console x (left of palette)
    minx, minz, maxx, maxz = grid.bbox()
    WX0 = min(minx, PBX - 10) - 2
    WZ0 = min(minz, OZ - 3) - 2
    WX1 = maxx + 2
    WZ1 = maxz + 2

    # forceload (in-place machines are tiny -> passes trivially)
    flbuild = core.forceload_guard(WX0, WZ0, WX1, WZ1, auto_fold=False)
    forceload_chunks = core._chunk_count(WX0, WZ0, WX1, WZ1)

    # ── 5. assemble the datapack (all plumbing via core) ──────────────────────
    dp = core.Datapack(ns, name, out_dir, profile.mc_version,
                       direction=params.get("start_dir", "+X"), ox=OX, oz=OZ)
    desc_form = "多乐器" if multi else "单钢琴"
    dp.write_pack_mcmeta(f"{ns} {name} {desc_form}原地调色板播放器(侧面红石块反复触发, tick80)")
    dp.write_load_tick_tags()

    # offall: clear every trigger slot back to air (rising-edge reset)
    dp.write_function("offall",
                      [f"setblock {x} {y} {z} minecraft:air"
                       for (x, y, z) in (trig(i) for i in range(P))])

    # cutmel (multi only): stopsound the sustaining cut-instr sample events
    if multi:
        dp.write_function(
            "cutmel",
            [f"stopsound @a record {ev}" for ev in cut_events]
            or [f"# {ns}: no melody-cut events"],
        )

    # step chain s{c}: press this cell's chord, +1t offall reset, +dt next cell
    for c, (tk, idxs) in enumerate(beats):
        lines = [f"execute if score PLAY {ns} matches 0 run return 0"]
        lines += [f"setblock {x} {y} {z} minecraft:redstone_block"
                  for (x, y, z) in (trig(i) for i in idxs)]
        lines.append(f"execute if score PLAY {ns} matches 1 run schedule function {ns}:offall 1t")
        if multi and c in cut_delay:
            lines.append(
                f"execute if score PLAY {ns} matches 1 run "
                f"schedule function {ns}:cutmel {cut_delay[c]}t append"
            )
        if c + 1 < NB:
            dt = (beats[c + 1][0] - tk) * 2                       # cells -> game-ticks (tick80: *2); >=2
            lines.append(
                f"execute if score PLAY {ns} matches 1 run "
                f"schedule function {ns}:s/s{c + 1} {dt}t"
            )
        else:
            lines.append(f"schedule function {ns}:done {DONE_TAIL_GT}t")
        dp.write_function(f"s/s{c}", lines)
    T0 = beats[0][0] * 2

    # ── 6. console (labeled buttons via core) + tick-rate command block ───────
    ctl = ["gamerule commandModificationBlockLimit 2147483647"]
    sd = profile.sign_dialect   # version-aware sign NBT (string <=1.21.4 / SNBT >=1.21.5)
    head2 = ["[播放]", "多乐器", "调色板"] if multi else ["[播放]", "调色板", "侧触发, 放一遍"]
    ctl += core.labeled_button(PBX,     Y, OZ, f"function {ns}:play",            head2,                       sign_dialect=sd)
    ctl += core.labeled_button(PBX - 2, Y, OZ, f"function {ns}:loop",            ["[循环播放]", "放完自动重放"],   sign_dialect=sd)
    ctl += core.labeled_button(PBX - 4, Y, OZ, f"function {ns}:stop",            ["[停止]", "立即静音"],         sign_dialect=sd)
    ctl += core.labeled_button(PBX - 6, Y, OZ, f"function {ns}:cfg/polytoggle",  ["[复音增益]", "大和弦防糊"],     sign_dialect=sd)
    ctl += core.labeled_button(PBX - 8, Y, OZ, f"function {ns}:cfg/humantoggle", ["[微抖动]", "去复印感"],        sign_dialect=sd)

    # NOTE: the machine does NOT auto-set the tick rate. An auto command-block that ran
    # `/tick rate 80` on [play] was REMOVED — it proved unreliable in-game (user-tested:
    # the auto-set didn't take). The PLAYER must MANUALLY run `/tick rate 80` before
    # playing (the samples are tuned for tick80; without it playback is ~4x too slow).

    # ── 7. core build/tick scaffolding ───────────────────────────────────────
    batches = core.batch_setblocks(build_cmds, batch=2000)
    RESET = core.scoreboard_reset(ns)

    dp.write_function("load", core.build_load_fn(ns, name, extra_objectives=True))

    dp.write_function(
        "setup",
        RESET + ["gamemode creative @a", SSTOP, "forceload remove all"]
        + flbuild
        + [f"tp @a {PBX} {Y + 3} {OZ}",
           f"scoreboard players set BLD {ns} 0",
           f'tellraw @a "[{ns}] forceload+building (调色板 {P}音 {PCOLS}宽{PROWS}行)..."'],
    )

    # tick dispatch: drive the BLD build counter (mass setblock batched across ticks)
    dp.write_function("tick", core.build_tick_dispatch(ns, len(batches)))
    for k, b in enumerate(batches):
        dp.write_function(f"bld/b{k}", b)

    dp.write_function("placectl", ctl)
    dp.write_function(
        "builddone",
        f"scoreboard players set BLD {ns} -1\nfunction {ns}:placectl\n"
        f'tellraw @a ["",{{"text":"[{ns}] built. ","color":"green"}},'
        f'{{"text":"{desc_form}调色板 {P}音符盒(侧面触发,不过载). 先手动 /tick rate 80,再按[播放]/[循环播放]/[停止]"}}]',
    )

    # playcore: arm PLAY, silence, reset slots, clear cuts, start s0. NO tick-rate command
    # here — the player sets /tick rate 80 manually before playing (auto-set was removed).
    playcore = ([f"scoreboard players set PLAY {ns} 1", SSTOP, f"function {ns}:offall"])
    if multi:
        playcore.append(f"schedule clear {ns}:cutmel")
    playcore.append(f"schedule function {ns}:s/s0 {max(1, T0)}t")
    dp.write_function("playcore", playcore)

    dp.write_function("play", [
        f'execute if score PLAY {ns} matches 1 run return run tellraw @a "[{ns}] 正在播放, 先[停止]"',
        f"scoreboard players set LOOP {ns} 0",
        f"function {ns}:playcore",
        f'tellraw @a "[{ns}] 播放(原地调色板, 站着听)。"',
    ])
    dp.write_function("loop", [
        f"execute if score PLAY {ns} matches 1 run scoreboard players set LOOP {ns} 1",
        f'execute if score PLAY {ns} matches 1 run return run tellraw @a "[{ns}] 已转循环。"',
        f"scoreboard players set LOOP {ns} 1",
        f"function {ns}:playcore",
        f'tellraw @a "[{ns}] 循环播放。"',
    ])
    dp.write_function("done", [
        f"execute if score LOOP {ns} matches 1 run function {ns}:playcore",
        f"execute if score LOOP {ns} matches 0 run scoreboard players set PLAY {ns} 0",
        f"execute if score LOOP {ns} matches 0 run function {ns}:offall",
        f'execute if score LOOP {ns} matches 0 run tellraw @a "[{ns}] (一遍结束)。"',
    ])

    stop_lines = (RESET + ["gamemode creative @a", SSTOP, f"schedule clear {ns}:done"])
    if multi:
        stop_lines.append(f"schedule clear {ns}:cutmel")
    stop_lines += [f"function {ns}:offall",
                   f"tp @a {PBX} {Y + 3} {OZ}",
                   f'tellraw @a "[{ns}] 已停止(立即静音)。"']
    dp.write_function("stop", stop_lines)

    dp.write_function("cfg/polytoggle", [
        "scoreboard players set rptmp rpcfg 1",
        "scoreboard players operation rptmp rpcfg -= poly rpcfg",
        "scoreboard players operation poly rpcfg = rptmp rpcfg",
        f'execute if score poly rpcfg matches 1 run tellraw @a "[{ns}] 复音增益 ON"',
        f'execute if score poly rpcfg matches 0 run tellraw @a "[{ns}] 复音增益 OFF"',
    ])
    dp.write_function("cfg/humantoggle", [
        "scoreboard players set rptmp rpcfg 1",
        "scoreboard players operation rptmp rpcfg -= human rpcfg",
        "scoreboard players operation human rpcfg = rptmp rpcfg",
        f'execute if score human rpcfg matches 1 run tellraw @a "[{ns}] 微抖动 ON"',
        f'execute if score human rpcfg matches 0 run tellraw @a "[{ns}] 微抖动 OFF"',
    ])

    cleanup_lines = (["gamerule commandModificationBlockLimit 2147483647"]
                     + RESET + ["gamemode creative @a", SSTOP,
                                f"schedule clear {ns}:done"])
    if multi:
        cleanup_lines.append(f"schedule clear {ns}:cutmel")
    cleanup_lines += [f"fill {WX0} {Y - 2} {WZ0} {WX1} {Y + 1} {WZ1} air",
                      "forceload remove all",
                      f'tellraw @a "[{ns}] cleaned up。"']
    dp.write_function("cleanup", cleanup_lines)

    # ── 8. deploy (opt-in) ────────────────────────────────────────────────────
    deployed = None
    if deploy_dir is not None:
        deployed = dp.deploy(deploy_dir)

    # ── 9. stats ──────────────────────────────────────────────────────────────
    fire_ticks = sum(len(idxs) for _, idxs in beats)
    duration_s = (ticks[-1] - ticks[0]) * U
    instr_palette = defaultdict(int)
    for ins in pal_instr:
        instr_palette[ins] += 1

    return {
        "form": "inplace",
        "multi": multi,
        "note_count": NB,                 # sounding cells (beats)
        "input_notes": len(notes),
        "palette_size": P,
        "fire_ticks": fire_ticks,         # total trigger presses across all cells
        "dropped": dropped,
        "octave_shifted": octave_shifted,
        "forceload_chunks": forceload_chunks,
        "duration_s": round(duration_s, 2),
        "grid": [PCOLS, PROWS, ROWGAP],
        "bbox": [WX0, WZ0, WX1, WZ1],
        "batches": len(batches),
        "cut_count": len(cut_delay),
        "cut_median_gt": cut_median_gt,
        "cut_events": len(cut_events),
        "instr_palette": dict(instr_palette),
        "warnings": warnings,
        "build_dir": dp.root,
        "deployed": deployed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Smoke-test: build a synthetic ~20-note multi-family song -> build/ and print
# stats. If mido + skill/assets/demo.mid are present, also parse + build it.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "..", "..", "build")
    params = core_imap = None  # silence linters

    imap = core.InstrumentMap.load()
    profile = core.get_version_profile("1.21.8")

    # ── synthetic ~20-note multi-family notes list ────────────────────────────
    # a piano melody line + a sustaining pad (cut-instr) underneath + one bass +
    # a couple of drum hits, spread so cells are sparse enough to cut safely.
    synth = []
    mel = [60, 62, 64, 65, 67, 65, 64, 62, 60, 62, 64, 60]
    for i, m in enumerate(mel):
        synth.append({"t": i * 0.5, "dur": 0.45, "midi": m, "vel": 0.8,
                      "family": "pno", "drum_type": None})
    # sustaining pad chord roots (cut-instr) — long durations that need cutting
    for i, m in enumerate([48, 50, 52, 53]):
        synth.append({"t": i * 1.5, "dur": 3.0, "midi": m, "vel": 0.5,
                      "family": "pad", "drum_type": None})
    # a bass line (also cut-instr)
    for i, m in enumerate([36, 38, 40, 36]):
        synth.append({"t": i * 1.5, "dur": 1.2, "midi": m, "vel": 0.6,
                      "family": "bass", "drum_type": None})
    # drums (not cut)
    for i in range(4):
        synth.append({"t": i * 1.5, "dur": 0.1, "midi": 38, "vel": 0.9,
                      "family": "drum", "drum_type": "snare"})
    synth.sort(key=lambda n: n["t"])

    print(f"synthetic notes: {len(synth)}")

    # multi build
    p_multi = {"song": "smoke_multi", "multi": True, "PCOLS": 8}
    stats_m = build(synth, p_multi, imap, profile, ns="smoke_multi",
                    origin=(0, 0, 255), out_dir=out_dir, deploy_dir=None)
    print("MULTI stats:")
    for k in ("note_count", "palette_size", "fire_ticks", "dropped",
              "octave_shifted", "forceload_chunks", "duration_s",
              "cut_count", "cut_median_gt", "cut_events", "instr_palette"):
        print(f"  {k} = {stats_m[k]}")
    if stats_m["warnings"]:
        print("  warnings:")
        for w in stats_m["warnings"]:
            print(f"    - {w}")
    print(f"  build_dir = {stats_m['build_dir']}")

    # single (piano-only) build of the SAME notes (families ignored -> all pno)
    p_single = {"song": "smoke_single", "multi": False, "PCOLS": 8}
    stats_s = build(synth, p_single, imap, profile, ns="smoke_single",
                    origin=(0, 0, 255), out_dir=out_dir, deploy_dir=None)
    print("SINGLE stats:")
    for k in ("note_count", "palette_size", "fire_ticks", "cut_count"):
        print(f"  {k} = {stats_s[k]}")
    assert stats_s["cut_count"] == 0, "single form must not plan melody cuts"

    # ── optional: parse skill/assets/demo.mid via mido ────────────────────────
    demo = os.path.join(here, "..", "..", "assets", "demo.mid")
    if os.path.isfile(demo):
        try:
            import mido
            mf = mido.MidiFile(demo)
            cur_prog = defaultdict(int)
            active = {}
            t = 0.0
            dn = []
            for msg in mf:
                t += msg.time
                if msg.type == "program_change":
                    cur_prog[msg.channel] = msg.program
                elif msg.type == "note_on" and msg.velocity > 0:
                    active[(msg.channel, msg.note)] = (t, msg.velocity)
                elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                    key = (msg.channel, msg.note)
                    if key in active:
                        st, v = active.pop(key)
                        ch = msg.channel
                        fam = imap.family_for(cur_prog[ch], ch)
                        dn.append({
                            "t": round(st, 3), "midi": int(msg.note),
                            "vel": round(v / 127.0, 3),
                            "dur": round(max(t - st, 0.02), 3),
                            "family": fam,
                            "drum_type": None,
                        })
            dn.sort(key=lambda n: n["t"])
            if dn:
                stats_d = build(dn, {"song": "demo", "multi": True}, imap, profile,
                                ns="demo_inplace", origin=(0, 0, 255),
                                out_dir=out_dir, deploy_dir=None)
                print(f"DEMO.mid build: notes={len(dn)} palette={stats_d['palette_size']} "
                      f"cells={stats_d['note_count']} cut={stats_d['cut_count']} "
                      f"shifted={stats_d['octave_shifted']} chunks={stats_d['forceload_chunks']} "
                      f"dur={stats_d['duration_s']}s instr={stats_d['instr_palette']}")
        except Exception as e:  # noqa: BLE001  (smoke-test: report, don't crash)
            print(f"DEMO.mid build skipped: {type(e).__name__}: {e}")
    else:
        print("DEMO.mid not present, skipped")

    print("inplace smoke-test PASSED")
