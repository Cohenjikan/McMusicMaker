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
    if not bycell:
        # notes 非空但全部 vel<0.04 -> bycell 为空, 会静默生成 0 音符空机器. 硬失败.
        raise RedPianoError(f"{len(notes)} 个音符全部低于力度阈值 0.04 — nothing to build")
    trig = sorted(bycell)
    lane_voices = [dict() for _ in range(NLANE)]
    lane_counts = [0] * NLANE
    cut_events = set()
    meldur = {}
    mel_event_of = {}        # tick -> sound_event of the longest cut-instr note in that cell
    _mel_best_dur = {}       # tick -> that note's dur (s), to pick the longest
    instr_count = defaultdict(int)
    # family -> {(block, note_value, sound_event)} of every FINAL landed timbre, for the
    # physical [音色展台] stand (dedup'd; recorded as each note is resolved+placed below).
    stand_palette = defaultdict(set)
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
            stand_palette[instr].add((r.block, r.note_value, r.sound_event))
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

    # per-cell pulse arrival (game-ticks) off the SHARED skeleton — identical for every lane
    # and signal track. Drives the deterministic pulse-kill (§1.6b): each rep cell's repeater
    # is tagged with arrival_gt so `stop` punches an air gap just ahead of the marching front.
    arr = core.arrival_gt_by_cell(cells)

    # §A preload sample points: author-frame points every 128 blocks along the shared +X
    # lane axis (Z at the lane-band center), so a spectator tp-walk warms every stretch of
    # real terrain the pulse crosses. Written in +X author frame; write_function rotates them.
    PRELOAD_STRIDE = 128
    ncells = len(cells)
    lane_zs = [OZ + int(L["z"]) for L in LANES]
    z_center = (min(lane_zs) + max(lane_zs)) // 2
    xmax = OX + (ncells - 1)
    pre_pts = []
    _px = OX
    while _px <= xmax:
        pre_pts.append((_px, z_center))
        _px += PRELOAD_STRIDE
    if not pre_pts or pre_pts[-1][0] != xmax:
        pre_pts.append((xmax, z_center))

    # §B play gate now probes the FULL preload sample set (pre_pts, one per 128 blocks) at the
    # lane-plane height, not just mid+far — see the play/playgo split below. lane0_y = lane
    # 0's world Y (the probe height).
    lane0_y = Y + int(LANES[0].get("y", 0))

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
    # every chain's repeater cell (all lanes + signal tracks), tagged with the shared-skeleton
    # arrival_gt, for the deterministic pulse-kill. block string captured verbatim so restore
    # is byte-faithful to the bld batch.
    rep_kill_records = []

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
                rblock = f"minecraft:repeater[facing={RFACE},delay={v}]"
                grid.put(out, x, yb, z, rblock)
                rep_kill_records.append((arr[i], x, yb, z, rblock))
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

    # 4b. timbre-palette STAND — physical showcase of every landed (block, note, event)
    #     triple, fired by real wall buttons (the true mod path; replaces the old [试音]
    #     playsound row). Emitted into the SAME grid so its blocks join the occ-based
    #     forceload chunk set + the cleanup fill bbox. Author +X frame; grows -X from
    #     PBX(=OX-3) and -Z from OZ-6 (behind the console at z=OZ, clear of lanes z>=OZ).
    stand_cells, stand_truncated, stand_walk = core.emit_palette_stand(
        grid, build_cmds, stand_palette, ox=OX, oz=OZ, y=Y,
        sx=OX - 3, sz0=OZ - 6, sign_dialect=profile.sign_dialect,
        base_block=BASE)

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
    allx = [k[0] for k in occ]
    allz = [k[2] for k in occ]
    ally = [k[1] for k in occ]
    WX0, WZ0, WX1, WZ1 = min(allx) - 2, min(allz) - 2, max(allx) + 2, max(allz) + 2
    WY0, WY1 = min(ally) - 2, max(ally) + 2

    # SCOPED remove of exactly this machine's bbox (covers every chunk added below) —
    # NEVER 'forceload remove all', which would撤销 a co-existing song's forceload in the
    # same world (先歌"玩家一走开就哑"; /reload re-triggers it). remove+add stay paired.
    flbuild = [core.forceload_remove_region(WX0, WZ0, WX1, WZ1)] + [
        f"forceload add {cx * 16} {cz * 16}" for (cx, cz) in chunks
    ]

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
    # §E-fix: 俯瞰点对准轨带本体中点。占用 bbox 会被音色展台(-Z/-X 侧)拽偏, 旧式
    # OZ+(span//2) 在轨带不从 OZ 起步时也跑偏(olk 实测 z=33, 轨带中心其实是 23)。
    CAMX = OX + ncells // 2
    CAMZ = (min(lane_zs) + max(lane_zs)) // 2

    # ── deterministic pulse-kill plan (§1.6b): bucket every chain's (lane + signal-track)
    #    repeater cells by the ELAPSED window that punches them to air on stop. Build-time
    #    asserts every bucket overlapping the song has >=1 repeater (else a stop there is a
    #    no-op). All lanes/signals share one skeleton, so arr[i] tags each chain's cell i. ──
    kill_plan = core.plan_kill_buckets(rep_kill_records, MUSIC_TICKS)
    kill_kz, kill_bodies, restore_bodies = core.kill_function_bodies(ns, kill_plan)

    # ── §E cam-follow plan (core.cam_follow_plan §1.6c, 与 swave 共享管线):
    #    直线多轨的几何最简 — 相机锚点 = 轨带中线(恒定 Z), x 随 cell 索引即前沿。
    #    坐标由 core 预旋转成 world 系浮点字面量, write_function 原样放行(勿改格式)。──
    # 方块中心中线: 方块 z 实体占 [z, z+1), 视觉正中 = (min+max+1)/2 — 用坐标中线
    # (min+max)/2 会向 -Z 偏半格, 骑乘视角一边比另一边多一格(用户实测)。
    _cam_zmid = (min(lane_zs) + max(lane_zs) + 1) / 2.0
    # 相机高度基准计入最高轨的垫高(lane_offsets 有 y 的阶梯机器, 相机不再贴着外侧高轨)。
    _cam_ybase = Y + max(int(L.get("y", 0)) for L in LANES)
    cam_pts = [(OX + i + 0.5, _cam_zmid) for i in range(ncells)]
    (cam_body, camoff_body, cam_ladder, cam_buckets,
     n_cam_windows, cam_home) = core.cam_follow_plan(
        ns, cam_pts, arr, MUSIC_TICKS, _cam_ybase, params.get("start_dir", "+X"), OX, OZ,
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
        # union footprint = the occupied-cell bbox ∪ the hand-placed console button row
        # (PBX..PBX-14 in X, OZ-2..OZ in Z — those blocks live in `placectl`, NOT the grid).
        cx0, cx1 = PBX - 14, PBX          # buttons span PBX-14 .. PBX (§E adds [跟拍])
        cz0, cz1 = OZ - 2, OZ
        bx0, bz0 = min(min(allx), cx0), min(min(allz), cz0)
        bx1, bz1 = max(max(allx), cx1), max(max(allz), cz1)
        shell_segs, interior_segs, shell_bbox = core.protection_shell(
            prot_cfg, bx0, bz0, bx1, bz1, Y)
        pro_segs = shell_segs + interior_segs      # ORDER: build shell, then clear cavity
        N_PRO = len(pro_segs)
        M_SHELL = len(shell_segs)
        SX0, SZ0, SX1, SZ1, _FY, _CY = shell_bbox
        # the shell is a solid rectangle around the whole footprint (⊇ the machine); its
        # forceload covers the machine build too. Honor --force-cap like the machine bbox.
        flshell = core.forceload_guard(SX0 - 2, SZ0 - 2, SX1 + 2, SZ1 + 2,
                                       auto_fold=force_cap)

    def lbtn(bx, cmd, lines):
        return core.labeled_button(bx, Y, OZ, cmd, lines,
                                   sign_dialect=profile.sign_dialect)

    ctl = ["gamerule commandModificationBlockLimit 2147483647"]
    ctl += lbtn(PBX, f"function {ns}:play", ["[直接播放]", "多轨分布", "听全曲", ""])
    ctl += lbtn(PBX - 2, f"function {ns}:view", ["[全景俯视]", "看多轨", "", ""])
    ctl += lbtn(PBX - 4, f"function {ns}:stop", ["[停止]", "立即静音", "", ""])
    ctl += lbtn(PBX - 6, f"function {ns}:cfg/polytoggle", ["[复音增益]", "大和弦防糊", "", ""])
    ctl += lbtn(PBX - 8, f"function {ns}:cfg/humantoggle", ["[微抖动]", "去复印感", "", ""])
    # §A preload button — same main row (z=OZ), one slot further -X (clear of lanes, z>=OZ).
    ctl += lbtn(PBX - 10, f"function {ns}:preload", ["[preload]", "预加载区块", "先按我再play", ""])
    # §C [音色展台] — tp to the physical stand (real note blocks + wall buttons). Replaces the
    # old [试音 <fam>] playsound row: a stand cell drives the genuine mod+resourcepack path.
    ctl += lbtn(PBX - 12, f"function {ns}:stand", ["[音色展台]", "去实体展台", "按墙钮听真声", ""])
    # §E [跟拍] — 骑上隐形相机架; play 后与脉冲前沿逐刻锁定, camoff/停止/halt 下架。
    ctl += lbtn(PBX - 14, f"function {ns}:cam", ["[跟拍]", "骑相机跟脉冲", "先按我再play", ""])

    RESET = [f"scoreboard players set PLAY {ns} 0", f"scoreboard players set SIL {ns} 0"]
    SCHED_CLEAR = [f"schedule clear {ns}:{f}" for f in
                   ("done", "fire", "firestop", "startbuild", "unsil", "cutmel")]
    TRIG_CLEAR = [f"setblock {sx} {sy} {sz} minecraft:air" for (sx, sy, sz) in sources]

    # ── shared HALT: one clean-slate reset reused by setup / preload / cleanup / prosetup.
    #    Zeroes play state (PLAY/SIL/PRE), parks every state machine idle (BLD/CLR/PRO = -1)
    #    and clears the schedule + trigger sources. PRO=-1 interrupts an in-flight shell
    #    build (PRO>=0) or shell removal (PRO<=-2). It deliberately does NOT touch PROT (the
    #    "built by prosetup" flag) or `stop`'s own SIL mute window. ──
    HALT = (RESET
            + [f"scoreboard players set PRE {ns} 0",
               f"scoreboard players set BLD {ns} -1",
               f"scoreboard players set CLR {ns} -1",
               f"scoreboard players set PRO {ns} -1",
               # pulse-kill state: a clean slate has no pulse in flight and the machine is
               # ARM'd (ready). ELAPSED is the game-tick counter used to time a kill (§1.6b).
               f"scoreboard players set ELAPSED {ns} 0",
               f"scoreboard players set ARM {ns} 1",
               # mute联动: a clean-slate halt is unmuted (rpcfg exists post-load).
               "scoreboard players set mute rpcfg 0",
               # §E cam-follow: clean slate 顺手撤掉相机架(kill 自动让骑手落地)。
               f"kill @e[tag={ns}_cam]"]
            + SCHED_CLEAR + TRIG_CLEAR)
    dp.write_function("halt", HALT)

    # perfmode (§A): perfon captures+disables the 5 tick-load gamerules, perfoff restores
    # them. Written UNCONDITIONALLY so /function <ns>:perfoff is available for manual recovery
    # after a crashed session (load preserves a leftover PERF=1 so the guard passes).
    dp.write_function("perfon", core.perfon_fn(ns))
    dp.write_function("perfoff", core.perfoff_fn(ns))

    dp.write_function("load",
        [f"scoreboard objectives add {ns} dummy",
         f"scoreboard players set BLD {ns} -1",
         f"scoreboard players set CLR {ns} -1",
         # pulse-kill state init (§1.6b): ELAPSED game-tick counter + ARM ready flag
         f"scoreboard players set ELAPSED {ns} 0",
         f"scoreboard players set ARM {ns} 1"] + RESET
        + [core.forceload_remove_region(WX0, WZ0, WX1, WZ1),
           "scoreboard objectives add rpcfg dummy",
           f"scoreboard players set poly_{ns} rpcfg 1",
           f"scoreboard players set human_{ns} rpcfg 1",
           # mute联动: the mod reads `mute` in rpcfg (0=emit, 1=silence note sounds);
           # init unmuted, tracked alongside SIL everywhere below.
           "scoreboard players set mute rpcfg 0",
           f"scoreboard players set PRE {ns} 0",
           # perfmode: init PERF=0 EXCEPT when a prior session crashed mid-perf (PERF
           # persisted 1) — then keep 1 so its captured ORIG_* stay valid and perfoff
           # (manual or via stop) still restores the gamerules.
           f"execute unless score PERF {ns} matches 1 run "
           f"scoreboard players set PERF {ns} 0",
           f'execute if score PERF {ns} matches 1 run tellraw @a "[{ns}] 检测到上次性能模式'
           f'未正常关闭, gamerule 可能仍被改; /function {ns}:perfoff 可恢复(或按[直接播放]'
           f'再[停止]自动恢复)。"']
        + core.bossbar_init_lines(ns, with_pro=prot_cfg is not None)
        + SCHED_CLEAR + TRIG_CLEAR
        # §E cam-follow: 世界重进时撤掉上次会话遗留的相机架(实体会存档)。
        + [f"kill @e[tag={ns}_cam]"]
        # protection: park PRO idle + record "no shell yet" (PROT=0). Gated -> load stays
        # zero-diff when protection is off.
        + ([f"scoreboard players set PRO {ns} -1",
            f"scoreboard players set PROT {ns} 0"] if prot_cfg else [])
        + [f'tellraw @a ["",{{"text":"[{ns}] 多轨分布式直线机 loaded. ","color":"aqua"}},'
           f'{{"text":"需RedPiano+qzpno. 手动 /tick rate 80 -> /function {ns}:setup -> 启用资源包 -> 按 [play]"}}]']
        + ([f'tellraw @a "[{ns}] 保护壳可选: 用 /function {ns}:prosetup 代替 setup 建屏障壳, '
            f'/function {ns}:unprotect 拆壳。"'] if prot_cfg else []))
    dp.write_function("setup",
        [f"function {ns}:halt",
         # perfmode ON (after halt's clean slate) for the build + performance; stop/done/
         # cleardone restore the gamerules.
         f"function {ns}:perfon",
         "gamemode creative @a", SSTOP] + flbuild
        + [f"tp @a {PBX} {Y + 3} {OZ}", f"schedule function {ns}:startbuild 100t",
           f'tellraw @a "[{ns}] reset+forceload({NCH}区块); building 多轨..."'])
    dp.write_function("startbuild",
        [f"scoreboard players set BLD {ns} 0"]
        # bossbar: reveal the green build bar (max = batch count the BLD counter walks)
        + core.bossbar_show(ns, "bld", len(batches))
        + [f'tellraw @a "[{ns}] building {NLANE}轨 + {len(SIGS)}信号轨, {len(cells)}cell..."'])
    dp.write_function("tick",
        # pulse-kill clock: count game-ticks while playing so `stop` can time the kill (§1.6b).
        [f"execute if score PLAY {ns} matches 1 run scoreboard players add ELAPSED {ns} 1",
         # §E cam-follow: 播放中且相机架在场时逐刻派发 (不跟拍=一条 if entity 失败, 零负担).
         f"execute if score PLAY {ns} matches 1 if entity @e[tag={ns}_cam] "
         f"run function {ns}:cam/step",
         # bossbar: mirror each driving score into its progress bar beside the dispatch.
         f"execute if score BLD {ns} matches 0.. run function {ns}:buildstep",
         core.bossbar_track(ns, "bld", "BLD"),
         f"execute if score CLR {ns} matches 0.. run function {ns}:clearstep",
         core.bossbar_track(ns, "clr", "CLR")]
        # protection: PRO>=0 drives the shell BUILD (prostep), PRO<=-2 drives the shell
        # REMOVAL (unprostep); PRO=-1 idle. Gated -> a no-protection tick is byte-identical.
        # The pro bar only tracks the BUILD band (matches 0..); removal has no bar.
        + ([f"execute if score PRO {ns} matches 0.. run function {ns}:prostep",
            core.bossbar_track(ns, "pro", "PRO"),
            f"execute if score PRO {ns} matches ..-2 run function {ns}:unprostep"]
           if prot_cfg else [])
        + [f"execute if score SIL {ns} matches 1 run {SSTOP}"])
    bs = [f"execute if score BLD {ns} matches {k} run function {ns}:bld/b{k}"
          for k in range(len(batches))]
    bs += [f"execute if score BLD {ns} matches {len(batches)} run function {ns}:builddone",
           f"execute if score BLD {ns} matches 0..{len(batches)} run scoreboard players add BLD {ns} 1"]
    dp.write_function("buildstep", bs)
    for k, b in enumerate(batches):
        dp.write_function(f"bld/b{k}", b)
    dp.write_function("placectl", ctl)
    dp.write_function("builddone",
        [f"scoreboard players set BLD {ns} -1",
         core.bossbar_hide(ns, "bld"),
         f"function {ns}:placectl",
         f'tellraw @a ["",{{"text":"[{ns}] built. ","color":"green"}},'
         f'{{"text":"{NLANE}轨分布式直线; 按[直接播放]/[全景俯视]"}}]']
        # protection: after a prosetup build (PROT=1), drop the player inside the console.
        # rotate_command does NOT recurse into `execute if score ... run <tail>`, so the
        # coord-bearing tp lives in a sub-function (proenter) that write_function rotates.
        # Gated -> a no-protection builddone is byte-identical.
        + ([f"execute if score PROT {ns} matches 1 run function {ns}:proenter"]
           if prot_cfg else []))
    dp.write_function("cutmel",
        [f"stopsound @a record {ev}" for ev in cut_events]
        or [f"# {ns}: 无旋律截断事件(纯钢琴/鼓)"])
    dp.write_function("playcore",
        [# perfmode ON for the performance (no-op if setup already turned it on; re-enables
         # after a stop turned it off). Sheds the tick-load that starves tick80 playback.
         f"function {ns}:perfon",
         # zero the pulse-kill clock BEFORE the pulse starts (fire is 2t out) so ELAPSED
         # tracks this performance's front from t0 (§1.6b).
         f"scoreboard players set ELAPSED {ns} 0",
         # §E cam-follow: 相机架(若在场)归位到起点 — tick 先自增 ELAPSED 再派发, 窗口 0
         # 的 matches 0 绝对校准永不命中, 重播时必须在这里显式归位(空选择器无害失败)。
         cam_home,
         f"scoreboard players set PLAY {ns} 1", f"scoreboard players set SIL {ns} 0",
         "scoreboard players set mute rpcfg 0",     # SIL 0 -> unmute mod note sounds
         SSTOP, f"schedule clear {ns}:cutmel"] + TRIG_CLEAR
        + [f"schedule function {ns}:fire 2t"])
    # §B play gate: probe the FULL preload sample set (pre_pts, one per 128 blocks) so `play`
    # refuses only when some stretch of the route is still ungenerated. A verified preload sets
    # PRE=2 (READY) and short-circuits to playgo; a superflat world passes every probe so play
    # works WITHOUT a preload (backward-compatible). loaded coords rotate via rotate_command
    # (§1.8) for a non-+X multilane (e.g. olk -X).
    fullline_probes = [
        f'execute unless loaded {px} {lane0_y + 1} {pz} run return run tellraw @a '
        f'"[{ns}] 机器沿线区块未加载完成——先按 [preload] 预加载(或稍等 forceload 生成完)再 play"'
        for (px, pz) in pre_pts
    ]
    dp.write_function("play",
        [f'execute if score PLAY {ns} matches 1 run return run tellraw @a "[{ns}] 正在播放, 先[停止]"',
         # READY (a verified preload finished): direct through, skip the probes.
         f"execute if score PRE {ns} matches 2 run return run function {ns}:playgo"]
        + fullline_probes
        + [f"function {ns}:playgo"])
    dp.write_function("playgo",
        [# ARM lock: a just-pressed [停止] punched the pulse to air and restores it 4gt later;
         # refuse to re-play during that window so the new pulse can't run into the air gap.
         f'execute if score ARM {ns} matches 0 run return run tellraw @a '
         f'"[{ns}] 机器复位中,约1秒后再按 [直接播放]"',
         f"function {ns}:playcore",
         f'tellraw @a "[{ns}] GO。多轨分布式直线, 站着听全曲。"',
         f'tellraw @a "[{ns}] 提示: /tick rate {TPS} 重进世界会重置,需重敲;若节奏拖慢'
         f'(日志见 Can\'t keep up)=服务器过载,试关 Distant Horizons/降渲染距离。"'])
    dp.write_function("view",
        ["gamemode spectator @a", f"tp @a {CAMX} {Y + 80} {CAMZ} 0 90",
         f'tellraw @a "[{ns}] 俯视多轨(spectator)。"'])
    # ── deterministic pulse-kill functions (§1.6b). killzone (guarded on PLAY==1) dispatches
    #    ELAPSED to kill/k<n>, which punches the near-front repeaters (all lanes + signals) to
    #    air (ARM=0) and schedules restore/k<n> 4gt out to rebuild them byte-for-byte (ARM=1).
    #    restore/* is DELIBERATELY absent from SCHED_CLEAR — even a halt mid-kill must let the
    #    restore fire, or the machine keeps an air hole. All setblocks author +X (rotated by
    #    write_function for a non-+X multilane).
    dp.write_function("killzone", kill_kz)
    for _n, _body in kill_bodies.items():
        dp.write_function(f"kill/k{_n}", _body)
    for _n, _body in restore_bodies.items():
        dp.write_function(f"restore/k{_n}", _body)

    # ── §E cam-follow functions. cam = 上架([跟拍]按钮), camoff = 下架, cam/step =
    #    ELAPSED 桶梯子(每刻由 tick 在 PLAY==1 且实体存在时调用), cam/c<n> = 桶体。──
    dp.write_function("cam", cam_body)
    dp.write_function("camoff", camoff_body)
    dp.write_function("cam/step", cam_ladder)
    for _n, _body in cam_buckets.items():
        dp.write_function(f"cam/c{_n}", _body)

    dp.write_function("stop",
        # NB: NO leading RESET — PLAY must stay 1 until killzone runs (it guards on PLAY==1).
        # Mute the samples, clear the schedule + sources, THEN physically kill the marching
        # pulse, and only then drop PLAY / restore gamerules.
        ["gamemode creative @a", SSTOP]
        + SCHED_CLEAR + TRIG_CLEAR
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
           # 重播时, 孤儿架会无人空跑一整首。
           f"kill @e[tag={ns}_cam]",
           f'tellraw @a "[{ns}] 已停止,可立即重播。"'])
    dp.write_function("unsil",
        [f"scoreboard players set SIL {ns} 0",
         "scoreboard players set mute rpcfg 0"])  # SIL 0 -> unmute
    fire_lines = flbuild + [f"setblock {sx} {sy} {sz} minecraft:redstone_block"
                            for (sx, sy, sz) in sources]
    fire_lines += [f"schedule function {ns}:cutmel {cut_sched[tk]}t append" for tk in mel_ticks]
    fire_lines += [f"schedule function {ns}:firestop {PULSE}t",
                   f"schedule function {ns}:done {END_TICKS}t"]
    dp.write_function("fire", fire_lines)
    dp.write_function("firestop", TRIG_CLEAR)
    dp.write_function("done",
        RESET + ["gamemode creative @a",
                 f"function {ns}:perfoff",       # song ended -> restore gamerules
                 f'tellraw @a "[{ns}] (end) 重放[直接播放]; 拆 /function {ns}:cleanup。"'])
    SEG = 200
    clr_segs = (WX1 - WX0 + 16) // SEG + 1
    for k in range(clr_segs):
        fx0 = WX0 + k * SEG
        fx1 = min(WX1, fx0 + SEG - 1)
        dp.write_function(f"clr/c{k}", f"fill {fx0} {WY0} {WZ0} {fx1} {WY1} {WZ1} air")
    dp.write_function("cleardone",
        [f"scoreboard players set CLR {ns} -1",
         core.bossbar_hide(ns, "clr"),
         core.forceload_remove_region(WX0, WZ0, WX1, WZ1),
         f"function {ns}:perfoff",       # teardown -> restore gamerules
         f'tellraw @a "[{ns}] cleaned."']
        # bossbar: teardown removes every bar this ns created (machine is gone).
        + core.bossbar_remove_all(ns, with_pro=prot_cfg is not None)
        # protection: machine bbox cleared; if a shell was raised by prosetup (PROT=1),
        # auto-run unprotect (PRO=-2 kicks unprostep, which ends by clearing PROT + the
        # shell forceload). Gated -> a no-protection cleardone is byte-identical.
        + ([f"execute if score PROT {ns} matches 1 run scoreboard players set PRO {ns} -2",
            f'execute if score PROT {ns} matches 1 run tellraw @a '
            f'"[{ns}] 拆除保护壳(分段)..."'] if prot_cfg else []))
    cs = [f"execute if score CLR {ns} matches {k} run function {ns}:clr/c{k}"
          for k in range(clr_segs)]
    cs += [f"execute if score CLR {ns} matches {clr_segs} run function {ns}:cleardone",
           f"execute if score CLR {ns} matches 0..{clr_segs} run scoreboard players add CLR {ns} 1"]
    dp.write_function("clearstep", cs)
    dp.write_function("cleanup",
        ["gamerule commandModificationBlockLimit 2147483647",
         f"function {ns}:halt", "gamemode creative @a", SSTOP]
        + [f"scoreboard players set CLR {ns} 0"]
        # bossbar: reveal the red teardown bar (max = clear segment count the CLR counter walks)
        + core.bossbar_show(ns, "clr", clr_segs)
        + [f'tellraw @a "[{ns}] tearing down..."'])
    for nm, sc in (("polytoggle", "poly"), ("humantoggle", "human")):
        scp = f"{sc}_{ns}"   # ns-scoped fake player so two songs don't clobber each other
        dp.write_function(f"cfg/{nm}",
            [f"scoreboard players set rptmp_{ns} rpcfg 1",
             f"scoreboard players operation rptmp_{ns} rpcfg -= {scp} rpcfg",
             f"scoreboard players operation {scp} rpcfg = rptmp_{ns} rpcfg",
             f'execute if score {scp} rpcfg matches 1 run tellraw @a "[{ns}] {sc} ON"',
             f'execute if score {scp} rpcfg matches 0 run tellraw @a "[{ns}] {sc} OFF"'])

    # §A preload: spectator tp-walk warms the real terrain the pulse crosses. PRE (in the
    # {ns} objective) is the chain sentinel: preload sets 1, stop/cleanup set 0; each pre/pN
    # early-returns on PRE==0, so a stop aborts the dynamic chain without schedule-clearing it.
    dp.write_function("preload",
        [f"function {ns}:halt", "gamemode spectator @a"] + flbuild
        + [f"scoreboard players set PRE {ns} 1"]        # 1 = 预加载中 (0 idle / 2 READY)
        + core.bossbar_show(ns, "pre", len(pre_pts))    # blue preload bar
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
        dp.write_function(f"pre/p{_k}",
            [f"execute if score PRE {ns} matches 0 run return 0",
             f"tp @a {_px} {Y + 16} {_pz}",
             f"bossbar set {ns}:pre value {_k + 1}",
             f'tellraw @a "[{ns}] 预加载 {_k + 1}/{_M} (验证下一段区块加载中)"',
             f"function {ns}:pre/w{_k}"])
        dp.write_function(f"pre/w{_k}",
            [f"execute if score PRE {ns} matches 0 run return 0",
             f"execute unless loaded {_nx} {Y + 1} {_nz} run "
             f"schedule function {ns}:pre/w{_k} 20t",
             f"execute if loaded {_nx} {Y + 1} {_nz} run function {ns}:pre/p{_k + 1}"])
    dp.write_function(f"pre/p{_M}",
        [f"execute if score PRE {ns} matches 0 run return 0",
         core.bossbar_hide(ns, "pre"),
         "gamemode creative @a",
         f"tp @a {PBX} {Y + 3} {OZ}",
         f"scoreboard players set PRE {ns} 2",       # 2 = READY -> play direct-throughs
         f'tellraw @a "[{ns}] 预加载完成(READY),按 [直接播放] 直接播放。"'])

    # §C stand: tp @a to the physical timbre-palette stand + tellraw a per-family summary.
    # Replaces the old audition/* playsound functions: the exhibit IS the audition, and a
    # cell's wall button drives the real mod+resourcepack sound path (not a playsound sample).
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
    #    PRO>=0 builds the shell then clears the cavity (pro/s*), hands off to startbuild
    #    (machine body), builddone drops the player inside; PRO<=-2 removes ONLY the shell
    #    geometry (unpro/u*). All fills are author +X frame (write_function rotates them).
    #    Every write here is gated on prot_cfg -> a no-protection build emits none of it. ──
    if prot_cfg is not None:
        SX0, SZ0, SX1, SZ1, _FY, _CY = shell_bbox
        dp.write_function("prosetup",
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
        for _k, _seg in enumerate(pro_segs):
            dp.write_function(f"pro/s{_k}", core.shell_fill_cmd(_seg))
        prostep = [f"execute if score PRO {ns} matches {_k} run function {ns}:pro/s{_k}"
                   for _k in range(N_PRO)]
        prostep += [
            f"execute if score PRO {ns} matches {N_PRO} run function {ns}:probuilddone",
            f"execute if score PRO {ns} matches 0..{N_PRO} run "
            f"scoreboard players add PRO {ns} 1"]
        dp.write_function("prostep", prostep)
        dp.write_function("probuilddone",
            [f"scoreboard players set PRO {ns} -1",
             core.bossbar_hide(ns, "pro"),       # hide shell bar; startbuild reveals build bar
             f"function {ns}:startbuild"])
        # proenter: plain tp so write_function rotates it (builddone calls it when PROT=1).
        dp.write_function("proenter",
            [f"tp @a {PBX} {Y + 2} {OZ + 1} 0 40",
             f'tellraw @a "[{ns}] 保护壳完成,已进壳内控制台。"'])

        # unprotect: remove ONLY the shell (fill air), segmented in the negative PRO band so
        # halt (PRO=-1) can abort it. PRO=-2 => u0, -3 => u1, ...
        dp.write_function("unprotect",
            [f"function {ns}:halt",
             f"scoreboard players set PRO {ns} -2",
             f'tellraw @a "[{ns}] 拆除保护壳(分段移除屏障壳,机器保留)..."'])
        for _k, _seg in enumerate(shell_segs):
            _x0, _y0, _z0, _x1, _y1, _z1, _b = _seg
            dp.write_function(f"unpro/u{_k}",
                f"fill {_x0} {_y0} {_z0} {_x1} {_y1} {_z1} minecraft:air")
        unprostep = [f"execute if score PRO {ns} matches {-2 - _k} run function {ns}:unpro/u{_k}"
                     for _k in range(M_SHELL)]
        unprostep += [
            f"execute if score PRO {ns} matches {-2 - M_SHELL} run function {ns}:unprodone",
            f"execute if score PRO {ns} matches {-2 - M_SHELL}..-2 run "
            f"scoreboard players remove PRO {ns} 1"]
        dp.write_function("unprostep", unprostep)
        dp.write_function("unprodone",
            [f"scoreboard players set PRO {ns} -1",
             f"scoreboard players set PROT {ns} 0",
             core.forceload_remove_region(SX0 - 2, SZ0 - 2, SX1 + 2, SZ1 + 2),
             f'tellraw @a "[{ns}] 保护壳已拆除。"'])

    deployed = dp.deploy(deploy_dir) if deploy_dir else None

    # 时长按实际触发的 trig 时间跨度算, 不含被力度阈值丢弃的音符 (与 swave/inplace 一致)
    duration_s = (trig[-1] - trig[0]) * U if len(trig) > 1 else 0.0
    nnote = sum(1 for vv in occ.values() if vv.startswith("minecraft:note_block"))
    # dropped notes MUST surface in WARNINGS (not just the stat field); >10% -> strong prefix
    warnings = list(plan.warnings)
    # 匀速 fork: uniform pacing is NOT implemented for multilane yet — the schema
    # default is pace=uniform, so say so honestly instead of silently building the
    # legacy compressed skeleton and letting the user expect a constant-speed front.
    if str(params.get("pace") or "uniform").lower() == "uniform":
        warnings.insert(0, (
            "multilane builds the legacy COMPRESSED (variable-speed) skeleton — "
            "pace=uniform 匀速跑道 is swave/straight/custom only for now; use "
            "--form straight for constant-speed filming"))
    if dropped > 0:
        placed = sum(lane_counts)
        total = placed + dropped
        pct = (100.0 * dropped / total) if total else 0.0
        pfx = "!! " if pct > 10.0 else ""
        warnings.insert(
            0,
            f"{pfx}dropped {dropped} note(s) ({pct:.0f}% of {total}) — over lane count "
            f"{NLANE} (raise --max-poly / add lanes, or reduce simultaneous notes)")
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
        # deterministic pulse-kill (§1.6b): ELAPSED bucket count + biggest single-bucket
        # repeater-kill count (all lanes + signal tracks pooled).
        "kill_buckets": kill_plan.n_buckets,
        "kill_cells_max": kill_plan.cells_max,
        # §E cam-follow: 压缩后的相机步进窗口数 / 派发桶数
        "cam_windows": n_cam_windows,
        "cam_buckets": len(cam_buckets),
        "stand_cells": stand_cells,
        "stand_truncated": stand_truncated,
        # protection (barrier-shell / prosetup) — off => enabled False, 0 segments, no bbox
        "protection_enabled": prot_cfg is not None,
        "shell_segments": M_SHELL,
        "interior_segments": len(interior_segs),
        "shell_bbox": shell_bbox,
        "preload_steps": len(pre_pts),
        "warnings": warnings,
        "deployed": deployed,
        "out": dp.root,
    }
