# -*- coding: utf-8 -*-
"""generators/swave.py — Family A S-wave (marching-pulse) generator.

Adapts the user-verified oracle ``poc/48_build_swave_multi.py`` (multi-instrument
mirror-balanced S-wave / folded marching pulse + melody-sustain cut), with ONE
structural change demanded by the skill contract:

    poc/48 read its geometry knobs from ``argv``; THIS generator consumes them from
    the validated designer ``params`` dict, and routes ALL plumbing through
    ``redpiano_core`` (Datapack, Grid collision guard, InstrumentMap.resolve with
    octave-shift, plan_melody_cuts, forceload_guard, labeled_button,
    version profile, direction rotation). NO hardcoded pack_format, NO hardcoded
    world path, NO unconditional deploy. (Tick rate is MANUAL — no tick-rate command
    block is emitted; the player types /tick rate 80.)

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

# ── §E cam-follow (实体锁定跟拍) ────────────────────────────────────────────
# 采样/平滑/压缩/派发管线与常量都在 core.cam_follow_plan (§1.6c, 与 multilane
# 共享); 本生成器只提供几何 — 每 cell 的相机锚点 (build() 内 §E plan 处)。


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

    # all notes below the velocity floor -> bycell empty; trig/cells/pos would be []
    # and later pos[0]/trig[-1] raise a bare IndexError. Fail loudly instead so
    # build_machine can surface a clean "no audible notes" message.
    if not bycell:
        raise RedPianoError(
            f"swave.build: all {len(notes)} notes are below the velocity floor "
            f"0.04 — no audible note to place")

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
    # family -> {(block, note_value, sound_event)} of every FINAL landed timbre, for the
    # physical [音色展台] stand (dedup'd; the resolve below records each as it is placed).
    stand_palette = defaultdict(set)

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
                stand_palette[instr].add((r.block, r.note_value, r.sound_event))
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

    # per-cell pulse arrival (game-ticks) off the SHARED skeleton — same for both mirror
    # tracks. Drives the deterministic pulse-kill (§1.6b): every rep cell's repeater is
    # tagged with arrival_gt so `stop` can punch an air gap just ahead of the marching front.
    arr = core.arrival_gt_by_cell(cells)

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

    # dual-track geometric self-check: with a Z-mirrored second track, the two tracks'
    # note-block bands each span PATH_ZSPAN in Z; if TRACK_SEP < PATH_ZSPAN+3 the bands
    # (plus their above/side note blocks) overlap and Grid.put raises a RAW collision at
    # cryptic coords. Catch it here with a human-readable message BEFORE any setblock.
    # The derive default (track_sep_override is None -> PATH_ZSPAN+3) is always safe, so
    # this only fires on an explicit, too-small designer/params override.
    SAFE_TRACK_SEP = PATH_ZSPAN + 3
    if dual_track and n_tracks > 1 and track_sep_override is not None \
            and TRACK_SEP < SAFE_TRACK_SEP:
        raise RedPianoError(
            f"track_sep={TRACK_SEP} is too small for this song: the dual mirror tracks "
            f"each span {PATH_ZSPAN} blocks in Z, so they need at least "
            f"track_sep={SAFE_TRACK_SEP} to not collide. Raise track_sep to "
            f">= {SAFE_TRACK_SEP}, or delete track_sep from params to let the program "
            f"auto-derive the safe value (PATH_ZSPAN+3).")

    TRACK_Z = [OZ + i * TRACK_SEP for i in range(n_tracks)]

    # Playhead coords for the particle editor: the track-0 melody note block (chord3's
    # "above" note at Y+1) for each TRIGGER cell. This is the SINGLE SOURCE OF TRUTH —
    # the editor loads this exact list instead of re-deriving the S-wave spine in JS
    # (the JS re-derivation drifted: wrong cell-index + turn timing). Mirrors
    # track_transform(track=0): x = OX+xo, z = TRACK_Z[0] + (zo - PATH_ZMIN).
    # The real note-block setblocks get rotated for non-+X play directions by
    # core.rotate_command (via Datapack direction=start_dir); the playhead coords
    # must undergo the SAME rot_xz around (OX,OZ) or they drift on -X/+Z/-Z.
    start_dir = _get(params, "start_dir", "+X")
    form_desc = {
        "swave": "mirror-balanced S-wave",
        "straight": "straight line",
        "custom": "custom route",
    }[form]
    console_form = {
        "swave": "mirror S-wave",
        "straight": f"straight {start_dir}",
        "custom": f"custom {start_dir}",
    }[form]

    def _ph_xz(xo, zo):
        return core.rot_xz(OX + xo, TRACK_Z[0] + (zo - PATH_ZMIN), start_dir, OX, OZ)

    playhead_cells = [
        {"tick": cells[i][1], "x": _ph_xz(xo, zo)[0],
         "y": Y + 1, "z": _ph_xz(xo, zo)[1]}
        for i, (xo, zo, _d) in enumerate(pos) if cells[i][0] == "trig"
    ]

    # preload sample points (§A): author-frame track-0 path points, one every 128 blocks
    # along the (monotone) main X axis, so a spectator tp-walk warms every stretch of
    # real terrain the pulse will cross (forceload tickets are down but Terralith gen lags).
    # Written in the +X author frame; Datapack.write_function rotates them for non-+X dirs.
    PRELOAD_STRIDE = 128
    pre_pts = []
    last_ax = None
    for (xo, zo, _d) in pos:
        ax = OX + xo
        az = OZ + (zo - PATH_ZMIN)
        if last_ax is None or ax - last_ax >= PRELOAD_STRIDE:
            pre_pts.append((ax, az))
            last_ax = ax
    far_xo, far_zo, _ = pos[-1]
    far_pt = (OX + far_xo, OZ + (far_zo - PATH_ZMIN))
    if not pre_pts or pre_pts[-1] != far_pt:
        pre_pts.append(far_pt)

    # §B play gate now probes the FULL preload sample set (pre_pts, one per 128 blocks)
    # rather than just mid+far — see the `play`/`playgo` split below.

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

    # every track's repeater cell, tagged with its shared-skeleton arrival_gt, for the
    # deterministic pulse-kill. BOTH mirror tracks contribute (same arrival, distinct z),
    # so a stop kills both tracks' repeaters near the front. block string is captured
    # verbatim so restore is byte-faithful to the bld batch.
    rep_kill_records = []

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
                rblock = f"minecraft:repeater[facing={RFACE[md]},delay={v}]"
                grid.put(out, x, Y, z, rblock)
                rep_kill_records.append((arr[i], x, Y, z, rblock))
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

    # ── 5b. timbre-palette STAND — a physical showcase of every landed (block, note,
    #        event) triple, fired by real wall buttons (the true mod path; replaces the old
    #        [试音] playsound row). Emitted into the SAME grid, so its footprint auto-joins
    #        the forceload + cleanup bbox. Author +X frame; grows -X from PBX(=OX-3) and -Z
    #        from OZ-6 (behind the console, clear of the freed OZ-3 row + the OX-1 pulse src).
    stand_cells, stand_truncated, stand_walk = core.emit_palette_stand(
        grid, build_cmds, stand_palette, ox=OX, oz=OZ, y=Y,
        sx=OX - 3, sz0=OZ - 6, sign_dialect=profile.sign_dialect,
        base_block=base_block)

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

    # ── deterministic pulse-kill plan (§1.6b): bucket every track's repeater cells by the
    #    ELAPSED window that should punch them to air on stop. Build-time asserts every
    #    bucket overlapping the song has >=1 repeater (else a stop there couldn't kill). ──
    kill_plan = core.plan_kill_buckets(rep_kill_records, MUSIC_TICKS)
    kill_kz, kill_bodies, restore_bodies = core.kill_function_bodies(ns, kill_plan)

    # ── §E cam-follow plan: 从共享骨架 arr[]+pos[] 采样"ELAPSED→相机坐标"逐刻时刻表,
    #    平滑后压缩成分段步进 + 绝对校准, 两级 ELAPSED 梯子派发 (细节见常量区注释)。
    #    坐标在此处用 core.rot_xz 预旋转成 world 系浮点数 — rotate_command 对带小数点的
    #    坐标 int() 失败原样放行, 所以 write_function 不会二次旋转 (刻意依赖, 勿改格式)。──
    #    几何: 双镜像轨 = 两轨正中(镜像对中点 Z 与 local_z 无关, 恒为
    #    (TRACK_Z[0]+TRACK_Z[-1]+PATH_ZSPAN-1)/2); 单轨 = 沿蛇形路径本身。
    if n_tracks > 1:
        _cam_zmid = (TRACK_Z[0] + TRACK_Z[-1] + PATH_ZSPAN - 1) / 2.0
        cam_pts = [(float(OX + xo), _cam_zmid) for (xo, _zo, _d) in pos]
    else:
        cam_pts = [(float(OX + xo), float(TRACK_Z[0] + (zo - PATH_ZMIN)))
                   for (xo, zo, _d) in pos]
    (cam_body, camoff_body, cam_ladder, cam_buckets,
     n_cam_windows, cam_home) = core.cam_follow_plan(
        ns, cam_pts, arr, MUSIC_TICKS, Y, start_dir, OX, OZ,
        height=_get(params, "cam_height", None),
        back=_get(params, "cam_back", None),
        dz=_get(params, "cam_dz", None))

    # ── protection (prosetup) barrier-shell geometry, author +X frame. None unless
    #    protection.enabled — every emission below is gated on prot_cfg so the OFF path
    #    is byte-for-byte identical to the no-protection build (zero-diff contract). ──
    prot_cfg = core.protection_config(_get(params, "protection", None))
    shell_segs = interior_segs = pro_segs = []
    shell_bbox = None
    N_PRO = M_SHELL = 0
    flshell = []
    if prot_cfg is not None:
        # union footprint = machine+stand grid bbox ∪ the hand-placed console button row
        # (PBX..PBX-14 in X, OZ-2..OZ in Z — those blocks live in `placectl`, NOT the grid).
        cx0, cx1 = PBX - 14, PBX          # buttons span PBX-14 .. PBX (§E adds [跟拍])
        cz0, cz1 = OZ - 2, OZ             # sign row (OZ-2) .. button row (OZ)
        bx0, bz0 = min(minx, cx0), min(minz, cz0)
        bx1, bz1 = max(maxx, cx1), max(maxz, cz1)
        shell_segs, interior_segs, shell_bbox = core.protection_shell(
            prot_cfg, bx0, bz0, bx1, bz1, Y)
        pro_segs = shell_segs + interior_segs      # ORDER: build shell, then clear cavity
        N_PRO = len(pro_segs)                      # prostep dispatch length (handoff at N_PRO)
        M_SHELL = len(shell_segs)                  # unprotect only removes the shell geometry
        SX0, SZ0, SX1, SZ1, _FY, _CY = shell_bbox
        # the shell footprint ⊇ the machine, so its forceload covers the machine build too.
        flshell = core.forceload_guard(SX0 - 2, SZ0 - 2, SX1 + 2, SZ1 + 2,
                                       auto_fold=auto_fold)

    # NOTE: the machine does NOT auto-set the tick rate. The auto command-block that ran
    # `/tick rate 80` was REMOVED — it proved unreliable in-game (user-tested: the auto-set
    # didn't take). The PLAYER must MANUALLY run `/tick rate 80` before playing (the samples
    # are tuned for tick80; without it playback is ~4x too slow).

    dp = core.Datapack(ns, name, out_dir, profile.mc_version,
                       direction=start_dir, ox=OX, oz=OZ)
    dp.write_pack_mcmeta(
        f"{ns} {name} multi-instrument {form_desc} + melody-cut, tick{TPS}")
    dp.write_load_tick_tags()

    RESET = [f"scoreboard players set PLAY {ns} 0",
             f"scoreboard players set SIL {ns} 0"]

    # ── shared HALT: one clean-slate reset reused by setup / preload / cleanup / prosetup.
    #    Zeroes the play state (PLAY/SIL/PRE), parks every state machine idle (BLD/CLR/PRO =
    #    -1) and clears the schedule + trigger sources. PRO=-1 interrupts an in-flight shell
    #    build (PRO>=0) OR shell removal (PRO<=-2). It deliberately does NOT touch PROT (the
    #    "built by prosetup" flag) or SIL's mute window — `stop` keeps its own semantics. ──
    HALT = (RESET
            + [f"scoreboard players set PRE {ns} 0",
               f"scoreboard players set BLD {ns} -1",
               f"scoreboard players set CLR {ns} -1",
               f"scoreboard players set PRO {ns} -1",
               # pulse-kill state: a clean slate has no pulse in flight and the machine is
               # ARM'd (ready to play). ELAPSED is the game-tick counter used to time a kill.
               f"scoreboard players set ELAPSED {ns} 0",
               f"scoreboard players set ARM {ns} 1",
               # mute联动: a clean-slate halt is unmuted (rpcfg exists post-load).
               "scoreboard players set mute rpcfg 0",
               # §E cam-follow: clean slate 顺手撤掉相机架(kill 自动让骑手落地)。
               f"kill @e[tag={ns}_cam]"]
            + SCHED_CLEAR
            + TRIG_CLEAR)
    dp.write_function("halt", HALT)

    # perfmode (§A): perfon captures+disables the 5 tick-load gamerules, perfoff restores
    # them. Written UNCONDITIONALLY so /function <ns>:perfoff is available for manual recovery
    # after a crashed session (load preserves a leftover PERF=1 so the guard passes).
    dp.write_function("perfon", core.perfon_fn(ns))
    dp.write_function("perfoff", core.perfoff_fn(ns))

    # ---- control console (labeled buttons via core.labeled_button) ----
    ctl = ["gamerule commandModificationBlockLimit 2147483647"]
    sd = profile.sign_dialect   # version-aware sign NBT (string <=1.21.4 / SNBT >=1.21.5)
    ctl += core.labeled_button(PBX, Y, OZ, f"function {ns}:play",
                               ["[play]", console_form, "full song"], sign_dialect=sd)
    ctl += core.labeled_button(PBX - 2, Y, OZ, f"function {ns}:view",
                               ["[overview]", f"see {console_form}", "lamp flow"], sign_dialect=sd)
    ctl += core.labeled_button(PBX - 4, Y, OZ, f"function {ns}:stop",
                               ["[stop]", "mute now", "if stuck"], sign_dialect=sd)
    ctl += core.labeled_button(PBX - 6, Y, OZ, f"function {ns}:cfg/polytoggle",
                               ["[poly gain]", "big chords", "anti-mud"], sign_dialect=sd)
    ctl += core.labeled_button(PBX - 8, Y, OZ, f"function {ns}:cfg/humantoggle",
                               ["[humanize]", "de-photocopy"], sign_dialect=sd)
    # §A preload button — same main row, one slot further -X (clear of the track x>=OX-1).
    ctl += core.labeled_button(PBX - 10, Y, OZ, f"function {ns}:preload",
                               ["[preload]", "预加载区块", "先按我再play"], sign_dialect=sd)
    # §C [音色展台] — tp to the physical stand (real note blocks + wall buttons). Replaces the
    # old [试音 <fam>] playsound row: a stand cell drives the genuine mod+resourcepack path.
    ctl += core.labeled_button(PBX - 12, Y, OZ, f"function {ns}:stand",
                               ["[音色展台]", "去实体展台", "按墙钮听真声"], sign_dialect=sd)
    # §E [跟拍] — 骑上隐形相机架; play 后与脉冲前沿逐刻锁定, camoff/停止/halt 下架。
    ctl += core.labeled_button(PBX - 14, Y, OZ, f"function {ns}:cam",
                               ["[跟拍]", "骑相机跟脉冲", "先按我再play"], sign_dialect=sd)

    dp.write_function("load",
                      [f"scoreboard objectives add {ns} dummy",
                       f"scoreboard players set BLD {ns} -1",
                       f"scoreboard players set CLR {ns} -1",
                       # pulse-kill state init (§1.6b): ELAPSED game-tick counter + ARM ready flag
                       f"scoreboard players set ELAPSED {ns} 0",
                       f"scoreboard players set ARM {ns} 1"]
                      + RESET
                      + [core.forceload_remove_region(WX0, WZ0, WX1, WZ1),
                         "scoreboard objectives add rpcfg dummy",
                         f"scoreboard players set poly_{ns} rpcfg 1",
                         f"scoreboard players set human_{ns} rpcfg 1",
                         # mute联动: the mod reads `mute` in rpcfg (0=emit, 1=silence note
                         # sounds); init unmuted, tracked alongside SIL everywhere below.
                         "scoreboard players set mute rpcfg 0",
                         f"scoreboard players set PRE {ns} 0",
                         # perfmode: init PERF=0 EXCEPT when a prior session crashed mid-perf
                         # (PERF persisted 1) — then keep 1 so its captured ORIG_* stay valid
                         # and perfoff (manual or via stop) still restores the gamerules.
                         f"execute unless score PERF {ns} matches 1 run "
                         f"scoreboard players set PERF {ns} 0",
                         f'execute if score PERF {ns} matches 1 run tellraw @a "[{ns}] '
                         f'检测到上次性能模式未正常关闭, gamerule 可能仍被改; '
                         f'/function {ns}:perfoff 可恢复(或按[play]再[stop]自动恢复)。"']
                      + core.bossbar_init_lines(ns, with_pro=prot_cfg is not None)
                      + SCHED_CLEAR
                      + TRIG_CLEAR
                      # §E cam-follow: 世界重进时撤掉上次会话遗留的相机架(实体会存档)。
                      + [f"kill @e[tag={ns}_cam]"]
                      # protection: park PRO idle + record "no shell yet" (PROT=0). Only
                      # emitted when protection.enabled -> load stays zero-diff otherwise.
                      + ([f"scoreboard players set PRO {ns} -1",
                          f"scoreboard players set PROT {ns} 0"] if prot_cfg else [])
                      + [f'tellraw @a ["",{{"text":"[{ns}] {name} multi-instr '
                         f'{form_desc} + melody-cut loaded. ","color":"aqua"}},'
                         f'{{"text":"need RedPiano + qzpno. Steps: /tick rate {TPS} (手动输入) '
                         f'-> /function {ns}:setup -> 启用资源包 -> press [play]."}}]']
                      + ([f'tellraw @a "[{ns}] 保护壳可选: 用 /function {ns}:prosetup 代替 '
                          f'setup 建屏障壳, /function {ns}:unprotect 拆壳。"'] if prot_cfg else []))

    dp.write_function("setup",
                      [f"function {ns}:halt",
                       # perfmode ON (after halt's clean slate) — sheds tick-load for the build
                       # and the ensuing performance; stop/done/cleardone restore it.
                       f"function {ns}:perfon",
                       "gamemode creative @a", SSTOP]
                      + flbuild
                      + [f"tp @a {PBX} {Y + 3} {OZ}",
                         f"schedule function {ns}:startbuild 100t",
                         f'tellraw @a "[{ns}] reset+forceload; building {form_desc}..."'])

    dp.write_function(
        "startbuild",
        [f"scoreboard players set BLD {ns} 0"]
        # bossbar: reveal the green build bar (max = batch count the BLD counter walks)
        + core.bossbar_show(ns, "bld", len(batches))
        + [f'tellraw @a "[{ns}] building {form_desc} '
           f'x{PATH_XSPAN} z{maxz - minz + 1}..."'])

    dp.write_function(
        "tick",
        # pulse-kill clock: count game-ticks while playing so `stop` can time the kill (§1.6b).
        [f"execute if score PLAY {ns} matches 1 run scoreboard players add ELAPSED {ns} 1",
         # §E cam-follow: 播放中且相机架在场时逐刻派发 (不跟拍=一条 if entity 失败, 零负担).
         f"execute if score PLAY {ns} matches 1 if entity @e[tag={ns}_cam] "
         f"run function {ns}:cam/step",
         # bossbar: mirror each driving score into its progress bar right beside the dispatch.
         f"execute if score BLD {ns} matches 0.. run function {ns}:buildstep",
         core.bossbar_track(ns, "bld", "BLD"),
         f"execute if score CLR {ns} matches 0.. run function {ns}:clearstep",
         core.bossbar_track(ns, "clr", "CLR")]
        # protection: PRO>=0 drives the shell BUILD (prostep), PRO<=-2 drives the shell
        # REMOVAL (unprostep); PRO=-1 is idle. Two disjoint bands off ONE score, gated so
        # a no-protection build's tick is byte-identical (no PRO line at all). The pro bar
        # only tracks the BUILD band (matches 0..); removal has no progress bar.
        + ([f"execute if score PRO {ns} matches 0.. run function {ns}:prostep",
            core.bossbar_track(ns, "pro", "PRO"),
            f"execute if score PRO {ns} matches ..-2 run function {ns}:unprostep"]
           if prot_cfg else [])
        + [f"execute if score SIL {ns} matches 1 run {SSTOP}"])

    bs = core.build_tick_dispatch(ns, len(batches))
    # poc/48 names the build driver `buildstep` (not `tick`); keep that.
    dp.write_function("buildstep", bs)
    for k, b in enumerate(batches):
        dp.write_function(f"bld/b{k}", b)

    dp.write_function("placectl", ctl)
    dp.write_function(
        "builddone",
        [f"scoreboard players set BLD {ns} -1",
         core.bossbar_hide(ns, "bld"),
         f"function {ns}:placectl",
         f'tellraw @a ["",{{"text":"[{ns}] built. ","color":"green"}},'
         f'{{"text":"X~{PATH_XSPAN}, Z~{maxz - minz + 1}; press [play]/[overview]"}}]']
        # protection: after a prosetup build (PROT=1), drop the player just inside the
        # console within the shell. The tp lives in a sub-function (proenter) because
        # rotate_command does NOT recurse into `execute if score ... run <tail>`, so a
        # coord-bearing tail must be a plain command that write_function rotates directly.
        # Gated -> a no-protection builddone is byte-identical.
        + ([f"execute if score PROT {ns} matches 1 run function {ns}:proenter"]
           if prot_cfg else []))

    dp.write_function(
        "cutmel",
        [f"stopsound @a record {ev}" for ev in cut_events_sorted]
        or [f"# {ns}: no melody-cut events (pure piano/drum)"])

    dp.write_function(
        "playcore",
        [# perfmode ON for the performance (no-op if setup already turned it on; re-enables
         # after a stop turned it off). Sheds the tick-load that starves tick80 playback.
         f"function {ns}:perfon",
         # zero the pulse-kill clock BEFORE the pulse starts (fire is 2t out) so ELAPSED
         # tracks this performance's front from t0 (§1.6b).
         f"scoreboard players set ELAPSED {ns} 0",
         # §E cam-follow: 相机架(若在场)归位到起点 — tick 先自增 ELAPSED 再派发, 窗口 0
         # 的 matches 0 绝对校准永不命中, 重播时必须在这里显式归位(空选择器无害失败)。
         cam_home,
         f"scoreboard players set PLAY {ns} 1",
         f"scoreboard players set SIL {ns} 0",
         "scoreboard players set mute rpcfg 0",     # SIL 0 -> unmute mod note sounds
         SSTOP,
         f"schedule clear {ns}:cutmel"]
        + TRIG_CLEAR
        + [f"schedule function {ns}:fire 2t"])

    # §B play gate: probe the FULL preload sample set (pre_pts, one per 128 blocks) so `play`
    # refuses only when some stretch of the route is still ungenerated (forceload ticket down
    # but Terralith terrain not caught up -> the pulse runs into ungenerated chunks and drops
    # out). A verified preload sets PRE=2 (READY) and short-circuits straight to playgo. A
    # superflat world loads instantly, so every probe passes and play works WITHOUT a preload
    # (backward-compatible). loaded-probe coords are rotated by rotate_command (§1.8).
    fullline_probes = [
        f'execute unless loaded {px} {Y + 1} {pz} run return run tellraw @a '
        f'"[{ns}] 机器沿线区块未加载完成——先按 [preload] 预加载(或稍等 forceload 生成完)再 play"'
        for (px, pz) in pre_pts
    ]
    dp.write_function(
        "play",
        [f'execute if score PLAY {ns} matches 1 run return run tellraw @a '
         f'"[{ns}] already playing, press [stop] first"',
         # READY (a verified preload finished): direct through, skip the probes.
         f"execute if score PRE {ns} matches 2 run return run function {ns}:playgo"]
        + fullline_probes
        + [f"function {ns}:playgo"])

    dp.write_function(
        "playgo",
        [# ARM lock: a just-pressed [stop] punched the pulse to air and restores it 4gt later;
         # refuse to re-play during that window so the new pulse can't run into the air gap.
         f'execute if score ARM {ns} matches 0 run return run tellraw @a '
         f'"[{ns}] 机器复位中,约1秒后再按 [play]"',
         f"function {ns}:playcore",
         f'tellraw @a "[{ns}] GO. multi-instr {form_desc}, melody sustain cut, '
         f'stand and listen."',
         f'tellraw @a "[{ns}] 提示: /tick rate {TPS} 重进世界会重置,需重敲;若节奏拖慢'
         f'(日志见 Can\'t keep up)=服务器过载,试关 Distant Horizons/降渲染距离。"'])

    dp.write_function(
        "view",
        ["gamemode spectator @a",
         f"tp @a {CAMX} {Y + 55} {CAMZ} 0 90",
         f'tellraw @a "[{ns}] overview of {form_desc} (spectator)."'])

    # ── deterministic pulse-kill functions (§1.6b). killzone (guarded on PLAY==1) dispatches
    #    ELAPSED to kill/k<n>, which punches the near-front repeaters to air (ARM=0) and
    #    schedules restore/k<n> 4gt out to rebuild them byte-for-byte (ARM=1). restore/* is
    #    DELIBERATELY absent from SCHED_CLEAR — even a halt mid-kill must let the restore fire,
    #    or the machine keeps an air hole. All setblocks are author +X; write_function rotates.
    dp.write_function("killzone", kill_kz)
    for _n, _body in kill_bodies.items():
        dp.write_function(f"kill/k{_n}", _body)
    for _n, _body in restore_bodies.items():
        dp.write_function(f"restore/k{_n}", _body)

    # ── §E cam-follow functions. cam = 上架([跟拍]按钮), camoff = 下架, cam/step =
    #    ELAPSED 桶梯子(每刻由 tick 在 PLAY==1 且实体存在时调用), cam/c<n> = 桶体
    #    (绝对校准 + 相对步进)。坐标已预旋转 (见 §E plan 注释), write_function 放行。──
    dp.write_function("cam", cam_body)
    dp.write_function("camoff", camoff_body)
    dp.write_function("cam/step", cam_ladder)
    for _n, _body in cam_buckets.items():
        dp.write_function(f"cam/c{_n}", _body)

    dp.write_function(
        "stop",
        # NB: NO leading RESET here — PLAY must stay 1 until killzone runs (it guards on
        # PLAY==1). Mute the samples, clear the schedule + sources, THEN physically kill the
        # marching pulse, and only then drop PLAY / restore gamerules.
        ["gamemode creative @a", SSTOP]
        + SCHED_CLEAR
        + TRIG_CLEAR
        + [f"scoreboard players set SIL {ns} 1",
           "scoreboard players set mute rpcfg 1",   # SIL 1 -> mute mod note sounds too
           # kill the pulse WHILE PLAY==1 (punch an air gap ahead of the front -> it dies);
           # restore/k<n> rebuilds the repeaters 4gt later (ARM gates replay until then).
           # ELAPSED 插桩: 若 stop 后 ~1s 音乐复活(漏杀), 用户报这个数字即可定位失效桶。
           f'tellraw @a ["",{{"text":"[{ns}] stop@ELAPSED=","color":"gray"}},'
           f'{{"score":{{"name":"ELAPSED","objective":"{ns}"}}}},'
           f'{{"text":" (若静音后音乐复活,请报告此数字)","color":"gray"}}]',
           f"function {ns}:killzone",
           f"scoreboard players set PLAY {ns} 0",
           f"function {ns}:perfoff",                # perfmode OFF — restore the captured gamerules
           f"scoreboard players set PRE {ns} 0",
           # the pulse is physically dead, so SIL only needs to cover the sample tails (~1s),
           # not the whole END_TICKS window (an old jar without mute is still fine at SIL 100t).
           f"schedule function {ns}:unsil 100t",
           f"tp @a {PBX} {Y + 3} {OZ}",
           # §E cam-follow: tp @a 已让骑手下架, 顺手撤掉相机架 — 否则不重按[跟拍]直接
           # 重播时, 孤儿架会无人空跑一整首(复审 nit)。
           f"kill @e[tag={ns}_cam]",
           f'tellraw @a "[{ns}] 已停止,可立即重播。"'])

    dp.write_function("unsil",
                      [f"scoreboard players set SIL {ns} 0",
                       "scoreboard players set mute rpcfg 0"])  # SIL 0 -> unmute

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
                 f"function {ns}:perfoff",       # song ended -> restore gamerules
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
        [f"scoreboard players set CLR {ns} -1",
         core.bossbar_hide(ns, "clr"),
         core.forceload_remove_region(WX0, WZ0, WX1, WZ1),
         f"function {ns}:perfoff",       # teardown -> restore gamerules
         f'tellraw @a "[{ns}] cleaned."']
        # bossbar: teardown removes every bar this ns created (machine is gone).
        + core.bossbar_remove_all(ns, with_pro=prot_cfg is not None)
        # protection: the machine bbox is cleared; if a shell was raised by prosetup
        # (PROT=1), auto-run unprotect (PRO=-2 kicks unprostep, which ends by clearing
        # PROT + the shell forceload). Gated -> a no-protection cleardone is unchanged.
        + ([f"execute if score PROT {ns} matches 1 run scoreboard players set PRO {ns} -2",
            f'execute if score PROT {ns} matches 1 run tellraw @a '
            f'"[{ns}] 拆除保护壳(分段)..."'] if prot_cfg else []))
    cs = [f"execute if score CLR {ns} matches {k} run function {ns}:clr/c{k}"
          for k in range(clr_segs)]
    cs += [f"execute if score CLR {ns} matches {clr_segs} run function {ns}:cleardone",
           f"execute if score CLR {ns} matches 0..{clr_segs} run "
           f"scoreboard players add CLR {ns} 1"]
    dp.write_function("clearstep", cs)
    dp.write_function(
        "cleanup",
        ["gamerule commandModificationBlockLimit 2147483647",
         f"function {ns}:halt",
         "gamemode creative @a", SSTOP]
        + [f"scoreboard players set CLR {ns} 0"]
        # bossbar: reveal the red teardown bar (max = clear segment count the CLR counter walks)
        + core.bossbar_show(ns, "clr", clr_segs)
        + [f'tellraw @a "[{ns}] tearing down..."'])

    dp.write_function(
        "cfg/polytoggle",
        [f"scoreboard players set rptmp_{ns} rpcfg 1",
         f"scoreboard players operation rptmp_{ns} rpcfg -= poly_{ns} rpcfg",
         f"scoreboard players operation poly_{ns} rpcfg = rptmp_{ns} rpcfg",
         f'execute if score poly_{ns} rpcfg matches 1 run tellraw @a "[{ns}] poly gain ON"',
         f'execute if score poly_{ns} rpcfg matches 0 run tellraw @a "[{ns}] poly gain OFF"'])
    dp.write_function(
        "cfg/humantoggle",
        [f"scoreboard players set rptmp_{ns} rpcfg 1",
         f"scoreboard players operation rptmp_{ns} rpcfg -= human_{ns} rpcfg",
         f"scoreboard players operation human_{ns} rpcfg = rptmp_{ns} rpcfg",
         f'execute if score human_{ns} rpcfg matches 1 run tellraw @a "[{ns}] humanize ON"',
         f'execute if score human_{ns} rpcfg matches 0 run tellraw @a "[{ns}] humanize OFF"'])

    # ── §A preload: spectator tp-walk to warm real terrain along the route ─────
    # PRE (in the {ns} objective) is the chain sentinel: preload sets it 1, stop/cleanup
    # set it 0. Each pre/pN early-returns if PRE==0, so a stop aborts the (dynamically
    # named) chain WITHOUT any `schedule clear pre/*` — SCHED_CLEAR stays a fixed list.
    dp.write_function(
        "preload",
        [f"function {ns}:halt", "gamemode spectator @a"]
        + flbuild
        + [f"scoreboard players set PRE {ns} 1"]       # 1 = 预加载中 (0 idle / 2 READY)
        + core.bossbar_show(ns, "pre", len(pre_pts))   # blue preload bar
        + [f'tellraw @a "[{ns}] 预加载开始: 逐段 tp + 验证式等待 {len(pre_pts)} 个采样点,'
           f'完成后自动回控制台并置 READY。请勿走动。"',
           f"schedule function {ns}:pre/p0 1t"])
    _M = len(pre_pts)
    # §B verified preload: each pre/p<k> tp's to point k, then hands to a wait function
    # pre/w<k> that SPINS (self-schedule 20t) until the NEXT sample point's chunk is actually
    # loaded (terrain gen caught up), instead of blindly waiting a fixed 30t. PRE==0 is the
    # sentinel: a stop/halt sets PRE 0, so every pre/p and pre/w early-returns and the dynamic
    # chain unwinds WITHOUT any schedule-clear. loaded-probe coords rotate via write_function.
    for _k, (_px, _pz) in enumerate(pre_pts):
        # wait target = the next point's chunk; clamp at the tail so the last step waits on
        # its own (already tp'd) chunk before advancing to the READY finish.
        _nx, _nz = pre_pts[_k + 1] if _k + 1 < _M else pre_pts[_k]
        dp.write_function(
            f"pre/p{_k}",
            [f"execute if score PRE {ns} matches 0 run return 0",
             f"tp @a {_px} {Y + 16} {_pz}",
             f"bossbar set {ns}:pre value {_k + 1}",
             f'tellraw @a "[{ns}] 预加载 {_k + 1}/{_M} (验证下一段区块加载中)"',
             f"function {ns}:pre/w{_k}"])
        dp.write_function(
            f"pre/w{_k}",
            [f"execute if score PRE {ns} matches 0 run return 0",
             f"execute unless loaded {_nx} {Y + 1} {_nz} run "
             f"schedule function {ns}:pre/w{_k} 20t",
             f"execute if loaded {_nx} {Y + 1} {_nz} run function {ns}:pre/p{_k + 1}"])
    dp.write_function(
        f"pre/p{_M}",
        [f"execute if score PRE {ns} matches 0 run return 0",
         core.bossbar_hide(ns, "pre"),
         "gamemode creative @a",
         f"tp @a {PBX} {Y + 3} {OZ}",
         f"scoreboard players set PRE {ns} 2",       # 2 = READY -> play direct-throughs
         f'tellraw @a "[{ns}] 预加载完成(READY),按 [play] 直接播放。"'])

    # ── §C stand: tp @a to the physical timbre-palette stand + tellraw a per-family summary.
    #    Replaces the old audition/* playsound functions: the exhibit itself IS the audition,
    #    and pressing a cell's wall button drives the real mod+resourcepack sound path.
    _stand_total = sum(stand_cells.values())
    _stand_parts = " ".join(f"{_f}:{_c}" for _f, _c in stand_cells.items()) or "(空)"
    _wx, _wz = stand_walk
    stand_body = [
        f"tp @a {_wx} {Y + 2} {_wz} 180 25",
        f'tellraw @a "[{ns}] 音色展台: {_stand_parts} (共{_stand_total}格)。沿走道逐格看牌,'
        f'按墙面石按钮=真实 mod+资源包发声(勿右键音符盒,会改音高毁展品)。"',
    ]
    if stand_truncated:
        stand_body.append(
            f'tellraw @a "[{ns}] 注意: 音色种类超过 {core.STAND_MAX_CELLS} 种,展台只摆前 '
            f'{core.STAND_MAX_CELLS} 格。"')
    dp.write_function("stand", stand_body)

    # ── §D protection: barrier-shell prosetup (opt-in entry point that REPLACES setup).
    #    Segmented state machine off the PRO score: PRO>=0 builds the shell then clears the
    #    cavity (pro/s*), hands off to startbuild (machine body), and builddone drops the
    #    player inside. PRO<=-2 removes ONLY the shell geometry (unpro/u*). All fills are
    #    author +X frame — Datapack.write_function rotates them for a non-+X direction.
    #    Every write here is gated on prot_cfg, so a no-protection build emits none of it. ──
    if prot_cfg is not None:
        SX0, SZ0, SX1, SZ1, _FY, _CY = shell_bbox
        # prosetup: halt -> forceload the shell (⊇ machine) -> mark PROT -> start PRO chain.
        dp.write_function(
            "prosetup",
            [f"function {ns}:halt",
             f"function {ns}:perfon",       # perfmode ON (like setup) for the shell+body build
             "gamemode creative @a", SSTOP]
            + flshell
            + [f"scoreboard players set PROT {ns} 1",
               f"tp @a {PBX} {Y + 3} {OZ}",
               f"scoreboard players set PRO {ns} 0"]
            + core.bossbar_show(ns, "pro", N_PRO)   # yellow shell-build bar
            + [f'tellraw @a "[{ns}] 保护壳施工: 先建屏障壳({M_SHELL}段)'
               f'{"+清腔" if interior_segs else ""}, 再建机器本体..."'])
        # per-segment fills (shell first, then interior clear) + the PRO dispatch.
        for _k, _seg in enumerate(pro_segs):
            dp.write_function(f"pro/s{_k}", core.shell_fill_cmd(_seg))
        prostep = [f"execute if score PRO {ns} matches {_k} run function {ns}:pro/s{_k}"
                   for _k in range(N_PRO)]
        prostep += [
            f"execute if score PRO {ns} matches {N_PRO} run function {ns}:probuilddone",
            f"execute if score PRO {ns} matches 0..{N_PRO} run "
            f"scoreboard players add PRO {ns} 1"]
        dp.write_function("prostep", prostep)
        # handoff: park PRO idle, hide the shell bar, then build the machine body
        # (startbuild reveals the green build bar).
        dp.write_function(
            "probuilddone",
            [f"scoreboard players set PRO {ns} -1",
             core.bossbar_hide(ns, "pro"),
             f"function {ns}:startbuild"])
        # proenter: drop the player just inside the console (builddone calls this when
        # PROT=1). Plain tp so write_function rotates the coords for a non-+X direction.
        dp.write_function(
            "proenter",
            [f"tp @a {PBX} {Y + 2} {OZ + 1} 0 40",
             f'tellraw @a "[{ns}] 保护壳完成,已进壳内控制台。"'])

        # unprotect: remove ONLY the shell (fill air over the shell segments), segmented in
        # the negative PRO band so halt (PRO=-1) can abort it. PRO=-2 => u0, -3 => u1, ...
        dp.write_function(
            "unprotect",
            [f"function {ns}:halt",
             f"scoreboard players set PRO {ns} -2",
             f'tellraw @a "[{ns}] 拆除保护壳(分段移除屏障壳,机器保留)..."'])
        for _k, _seg in enumerate(shell_segs):
            _x0, _y0, _z0, _x1, _y1, _z1, _b = _seg
            dp.write_function(
                f"unpro/u{_k}",
                f"fill {_x0} {_y0} {_z0} {_x1} {_y1} {_z1} minecraft:air")
        unprostep = [f"execute if score PRO {ns} matches {-2 - _k} run function {ns}:unpro/u{_k}"
                     for _k in range(M_SHELL)]
        unprostep += [
            f"execute if score PRO {ns} matches {-2 - M_SHELL} run function {ns}:unprodone",
            f"execute if score PRO {ns} matches {-2 - M_SHELL}..-2 run "
            f"scoreboard players remove PRO {ns} 1"]
        dp.write_function("unprostep", unprostep)
        dp.write_function(
            "unprodone",
            [f"scoreboard players set PRO {ns} -1",
             f"scoreboard players set PROT {ns} 0",
             core.forceload_remove_region(SX0 - 2, SZ0 - 2, SX1 + 2, SZ1 + 2),
             f'tellraw @a "[{ns}] 保护壳已拆除。"'])

    # ── 8. deploy is OPT-IN (only when deploy_dir given) ───────────────────────
    deployed_to = None
    if deploy_dir is not None:
        deployed_to = dp.deploy(deploy_dir)

    # ── 9. stats ───────────────────────────────────────────────────────────────
    n_rep = sum(1 for kind, _ in cells if kind == "rep")
    n_trig = sum(1 for kind, _ in cells if kind == "trig")
    nplaced = sum(len(trackvoice[t][p]) for t in range(n_tracks) for p in range(3))
    song_s = (trig[-1] - trig[0]) * U if len(trig) > 1 else 0.0

    # dropped notes MUST surface in the WARNINGS block (not just the stat field) so the
    # user sees them — >10% of placed notes uses a strong prefix. (plan.warnings already
    # carries melody-cut warnings; drop warning goes FIRST so it is most visible.)
    warnings = list(plan.warnings)
    if dropped > 0:
        total = nplaced + dropped
        pct = (100.0 * dropped / total) if total else 0.0
        pfx = "!! " if pct > 10.0 else ""
        warnings.insert(
            0,
            f"{pfx}dropped {dropped} note(s) ({pct:.0f}% of {total}) — over per-cell "
            f"polyphony cap {CELL_CAP} (raise --dual-track / fewer simultaneous notes)")

    stats = {
        "form": form,
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
        # deterministic pulse-kill (§1.6b): ELAPSED bucket count + biggest single-bucket
        # repeater-kill count (both tracks pooled).
        "kill_buckets": kill_plan.n_buckets,
        "kill_cells_max": kill_plan.cells_max,
        # §E cam-follow: 压缩后的相机步进窗口数 / 派发桶数
        "cam_windows": n_cam_windows,
        "cam_buckets": len(cam_buckets),
        "instr_distribution": dict(instr_count),
        "stand_cells": stand_cells,
        "stand_truncated": stand_truncated,
        # protection (barrier-shell / prosetup) — off => enabled False, 0 segments, no bbox
        "protection_enabled": prot_cfg is not None,
        "shell_segments": M_SHELL,
        "interior_segments": len(interior_segs),
        "shell_bbox": shell_bbox,
        "preload_steps": len(pre_pts),
        "warnings": warnings,
        "out_dir": dp.root,
        "deployed_to": deployed_to,
        # single-source-of-truth playhead for the particle editor (track-0 melody notes)
        "playhead_cells": playhead_cells,
        "playhead_origin": [core.rot_xz(OX, OZ, start_dir, OX, OZ)[0], Y,
                            core.rot_xz(OX, OZ, start_dir, OX, OZ)[1]],
        # music-tick OFFSET between trig cell T0 and its real schedule 2*(T0+OFFSET);
        # cli writes it as coords.json top-level "offset" so build_particles can align.
        "playhead_offset": OFFSET,
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
    if len(steps) + 1 < ncells:
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
