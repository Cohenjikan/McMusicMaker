# -*- coding: utf-8 -*-
# === STATUS: DEPRECATED ===
# Superseded by generators/swave.py (multi-instrument, melody-cut, core-routed).
# v1 use generators/swave.py or inplace.py; this is kept for reference/extension.
"""42_build_swave.py — Codex: OLK 连续 S 型波浪主链。

本脚本修正 Claude 40/41 的方向误解:
- 不是把整条线按 ROWS/ROWLEN 收纳成矩形行。
- 而是让同一条时间轴沿 +X 整体前进,在窄 Z 带里周期性 +Z/-Z 摆动,
  形成一条连续的 S 型/方波折线。
- 拐点用红石粉做 0 延迟桥接,但发声列和续链仍沿用已验证的
  "中继器强充能导体/音符盒"几何,不依赖弱充能发声。

Run:
  python 42_build_swave.py [notes.json] [NS] [OX] [XRUN] [ZMAX] [LIMIT_CELLS]

Defaults:
  notes_olk.json qzolks 300000 3 4 0

XRUN=3, ZMAX=4 表示每个局部波段在 X 方向走 3 个 cell,再用 3 个 cell
从 z=0 走到 z=4,因此约 2x 压缩 X 跨度,两轨总宽约 15 格。
LIMIT_CELLS>0 可生成小测试台。
"""

import json
import os
import shutil
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
# Asset roots resolved from __file__ (this file now lives in generators/_experimental/,
# two more levels deep than the old poc/ location). The single-instrument map and the
# notes_*.json fixtures live only under poc/; skill/assets/ ships the multi map.
SKILL_ASSETS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "assets"))
POC_DIR      = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "poc"))

# Optional --map <path> override (consumed before positional args are read).
_argv = sys.argv[1:]
MAP_OVERRIDE = None
if "--map" in _argv:
    _i = _argv.index("--map")
    MAP_OVERRIDE = _argv[_i + 1]
    del _argv[_i:_i + 2]

def _resolve(path, *roots):
    """Resolve an asset/notes path: absolute or cwd-relative as-is, else search roots."""
    if os.path.isabs(path) or os.path.exists(path):
        return path
    for r in roots:
        cand = os.path.join(r, path)
        if os.path.exists(cand):
            return cand
    return os.path.join(roots[0], path) if roots else path

NOTES = _argv[0] if len(_argv) > 0 else "notes_olk.json"
NS = _argv[1] if len(_argv) > 1 else "qzolks"
OX = int(_argv[2]) if len(_argv) > 2 else 300000
XRUN = int(_argv[3]) if len(_argv) > 3 else 3
ZMAX = int(_argv[4]) if len(_argv) > 4 else 4
LIMIT_CELLS = int(_argv[5]) if len(_argv) > 5 else 0

OZ, Y = 0, 255
VOICES, TPS, PULSE = 6, 80, 4
U = 2 / TPS
LAMP, PASS, BATCH = "minecraft:redstone_lamp", "minecraft:stone", 2000
SSTOP = "stopsound @a"
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界 (1)/datapacks"

if XRUN < 2:
    raise ValueError("XRUN must be >= 2")
if ZMAX < 2:
    raise ValueError("ZMAX must be >= 2")

RFACE = {
    (1, 0): "west",    # 已由旧脚本验证: facing=west 输出 +X
    (-1, 0): "east",
    (0, 1): "north",  # 旧调研记录: facing=north 输出 +Z
    (0, -1): "south",
}

notes = json.load(open(_resolve(NOTES, HERE, POC_DIR), encoding="utf-8"))["notes"]
MAP_PATH = MAP_OVERRIDE or _resolve("redpiano_map.json", SKILL_ASSETS, POC_DIR)
rp = json.load(open(MAP_PATH, encoding="utf-8"))
bands = rp["bands"]
RPMAP = rp["map"]


def layer_of(v):
    return "p" if v < 0.40 else ("mf" if v < 0.72 else "f")


clamped = [0]


def map_note(m, v):
    band = min(bands, key=lambda b: abs(b - m))
    nv = 12 + (m - band)
    if nv < 0 or nv > 24:
        clamped[0] += 1
    nv = max(0, min(24, nv))
    return RPMAP[f"{band}_{layer_of(v)}"]["block"], nv


# ---- 量化 + 双轨六声部分配(同 30/40) ----
bycell = defaultdict(list)
for n in notes:
    if n["vel"] >= 0.04:
        bycell[round(n["t"] / U)].append(n)

trackvoice = [[dict(), dict(), dict()], [dict(), dict(), dict()]]
dropped = 0
for tick, grp in bycell.items():
    g = sorted(grp, key=lambda x: -x["midi"])
    for i, n in enumerate(g[:VOICES]):
        trackvoice[i // 3][i % 3][tick] = map_note(n["midi"], n["vel"])
    dropped += max(0, len(g) - VOICES)


# ---- 共享时间线 cells[]: 触发刻并集 -> 唯一变延迟骨架 ----
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

cum = 0
for kind, v in cells:
    if kind == "rep":
        cum += v
    else:
        assert cum == v + OFFSET, f"时序错位 @tick {v}: cum={cum} != {v + OFFSET}"

if LIMIT_CELLS > 0:
    cells = cells[:LIMIT_CELLS]

used_trig = [v for kind, v in cells if kind == "trig"]
MAXTICK = max(used_trig) if used_trig else 0


# ---- 连续 S 型波浪路径: +X, +Z, +X, -Z, repeat ----
# ZMAX 是上下两条水平波峰/波谷的间距; 竖向段 cell 数为 ZMAX-1,
# 拐点红石粉占端点,不吃时间。
DIRS = [(1, 0), (0, 1), (1, 0), (0, -1)]
SEGLENS = [XRUN, ZMAX - 1, XRUN, ZMAX - 1]


def layout_swave(seq):
    pos = [None] * len(seq)          # (xoff, zoff, dir)
    turns = []                       # redstone dust corner positions (xoff, zoff)
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
        # 只在下一格是中继器时转向,保证转角后第一个时间格由中继器可靠接粉输入。
        # 水平段按 XRUN 控制节奏;竖向段按上下边界控制,避免等待中继器时
        # 产生的过冲在后续周期里累积成越来越宽的 Z 漂移。
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


pos, turns = layout_swave(cells)
path_x = [p[0] for p in pos]
path_z = [p[1] for p in pos]
if turns:
    path_x += [p[0] for p in turns]
    path_z += [p[1] for p in turns]
PATH_XSPAN = max(path_x) - min(path_x) + 1 if path_x else 1
PATH_ZSPAN = max(path_z) - min(path_z) + 1 if path_z else 1
TRACK_SEP = PATH_ZSPAN + 3
TRACK_Z = [OZ, OZ + TRACK_SEP]


# ---- 发射 setblock + 碰撞断言 ----
occ = {}


def put(out, x, y, z, blk):
    key = (x, y, z)
    if key in occ and occ[key] != blk and not (occ[key] == "air" or blk == "air"):
        raise AssertionError(f"碰撞 @{key}: {occ[key]} vs {blk}")
    occ[key] = blk
    out.append(f"setblock {x} {y} {z} {blk}")


def side_offsets(d):
    # 侧发声必须相对当前行进方向取垂直方向。
    if d[0] != 0:
        return (0, 1), (0, -1)
    return (1, 0), (-1, 0)


def chord3(out, x, z, d, vlist):
    above, side_a, side_b = vlist
    put(out, x, Y - 1, z, LAMP)
    put(out, x, Y, z, above[0] if above else PASS)
    if above:
        put(out, x, Y + 1, z, f"minecraft:note_block[note={above[1]}]")
        put(out, x, Y + 2, z, "air")

    off_a, off_b = side_offsets(d)
    if side_a:
        ax, az = x + off_a[0], z + off_a[1]
        put(out, ax, Y - 1, az, side_a[0])
        put(out, ax, Y, az, f"minecraft:note_block[note={side_a[1]}]")
        put(out, ax, Y + 1, az, "air")
    if side_b:
        bx, bz = x + off_b[0], z + off_b[1]
        put(out, bx, Y - 1, bz, side_b[0])
        put(out, bx, Y, bz, f"minecraft:note_block[note={side_b[1]}]")
        put(out, bx, Y + 1, bz, "air")


def emit_track(t, base_z):
    out = [f"setblock {OX - 1} {Y - 1} {base_z} {PASS}"]
    for i, (xo, zo, d) in enumerate(pos):
        x = OX + xo
        z = base_z + zo
        kind, v = cells[i]
        if kind == "rep":
            put(out, x, Y - 1, z, LAMP)
            put(out, x, Y, z, f"minecraft:repeater[facing={RFACE[d]},delay={v}]")
        else:
            vals = [trackvoice[t][p].get(v) for p in range(3)]
            chord3(out, x, z, d, vals)
    for xo, zo in turns:
        put(out, OX + xo, Y - 1, base_z + zo, PASS)
        put(out, OX + xo, Y, base_z + zo, "minecraft:redstone_wire")
    return out


DP = os.path.join(HERE, "build", NS)
if os.path.isdir(DP):
    shutil.rmtree(DP)
os.makedirs(DP)


def w(rel, content):
    p = os.path.join(DP, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8", newline="\n").write(
        content if content.endswith("\n") else content + "\n"
    )


def wf(name, body):
    w(f"data/{NS}/function/{name}.mcfunction", body if isinstance(body, str) else "\n".join(body))


json.dump(
    {
        "pack": {
            "pack_format": 81,
            "description": f"{NS} OLK continuous S-wave redstone path, tick80",
        }
    },
    open(os.path.join(DP, "pack.mcmeta"), "w", encoding="utf-8"),
    indent=2,
)
w("data/minecraft/tags/function/load.json", json.dumps({"values": [f"{NS}:load"]}))
w("data/minecraft/tags/function/tick.json", json.dumps({"values": [f"{NS}:tick"]}))

build = ["gamerule commandModificationBlockLimit 2147483647"]
for t in range(2):
    build += emit_track(t, TRACK_Z[t])
batches = [build[i : i + BATCH] for i in range(0, len(build), BATCH)]

allx = [k[0] for k in occ]
allz = [k[2] for k in occ]
WX0, WZ0, WX1, WZ1 = min(allx) - 2, min(allz) - 2, max(allx) + 2, max(allz) + 2
zc = (WZ1 // 16) - (WZ0 // 16) + 1
xstep = max(1, 240 // max(1, zc))
flbuild = ["forceload remove all"]
cx = WX0
while cx <= WX1:
    cxe = min(WX1, cx + xstep * 16 - 1)
    flbuild.append(f"forceload add {cx} {WZ0} {cxe} {WZ1}")
    cx = cxe + 1

src_pts = [(OX - 1, tz) for tz in TRACK_Z]
TRIG_CLEAR = [f"setblock {sx} {Y} {sz} minecraft:air" for sx, sz in src_pts]
SCHED_CLEAR = [f"schedule clear {NS}:{f}" for f in ("done", "fire", "firestop", "startbuild", "unsil")]
MUSIC_TICKS = (MAXTICK + OFFSET) * 2
END_TICKS = MUSIC_TICKS + 200
PBX = OX - 3
CAMX = OX + PATH_XSPAN // 2
CAMZ = (TRACK_Z[0] + TRACK_Z[1] + PATH_ZSPAN) // 2


def labeled_button(bx, cmd, lines):
    msgs = ",".join('\'{"text":"%s"}\'' % s for s in (list(lines) + ["", "", "", ""])[:4])
    return [
        f"setblock {bx} {Y - 1} {OZ} {LAMP}",
        f'setblock {bx} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"{cmd}",auto:0b}}',
        f"setblock {bx} {Y + 1} {OZ} minecraft:stone_button[face=floor]",
        f"setblock {bx} {Y - 1} {OZ - 2} {LAMP}",
        "setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}"
        % (bx, Y, OZ - 2, msgs),
    ]


ctl = ["gamerule commandModificationBlockLimit 2147483647"]
ctl += labeled_button(PBX, f"function {NS}:play", ["[直接播放]", "S波浪主链", "听全曲"])
ctl += labeled_button(PBX - 2, f"function {NS}:view", ["[全景俯视]", "看S波浪", "灯流光"])
ctl += labeled_button(PBX - 4, f"function {NS}:stop", ["[停止]", "立即静音", "卡住按这"])
ctl += labeled_button(PBX - 6, f"function {NS}:cfg/polytoggle", ["[复音增益]", "大和弦", "防糊"])
ctl += labeled_button(PBX - 8, f"function {NS}:cfg/humantoggle", ["[微抖动]", "去复印感"])

RESET = [f"scoreboard players set PLAY {NS} 0", f"scoreboard players set SIL {NS} 0"]
wf(
    "load",
    [f"scoreboard objectives add {NS} dummy", f"scoreboard players set BLD {NS} -1", f"scoreboard players set CLR {NS} -1"]
    + RESET
    + ["forceload remove all", "scoreboard objectives add rpcfg dummy", "scoreboard players set poly rpcfg 1", "scoreboard players set human rpcfg 1"]
    + SCHED_CLEAR
    + TRIG_CLEAR
    + [
        f'tellraw @a ["",{{"text":"[{NS}] S-wave loaded. ","color":"aqua"}},{{"text":"需RedPiano+qzpno. /tick rate 80 -> /function {NS}:setup"}}]'
    ],
)
wf(
    "setup",
    RESET
    + ["gamemode creative @a", SSTOP, f"scoreboard players set CLR {NS} -1"]
    + SCHED_CLEAR
    + TRIG_CLEAR
    + flbuild
    + [f"tp @a {PBX} {Y + 3} {OZ}", f"schedule function {NS}:startbuild 100t", f'tellraw @a "[{NS}] reset+forceload; building S-wave..."'],
)
wf("startbuild", f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building S-wave path x{PATH_XSPAN} z{max(allz)-min(allz)+1}..."')
wf(
    "tick",
    f"execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n"
    f"execute if score CLR {NS} matches 0.. run function {NS}:clearstep\n"
    f"execute if score SIL {NS} matches 1 run {SSTOP}",
)
bs = [f"execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}" for k in range(len(batches))]
bs += [
    f"execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone",
    f"execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1",
]
wf("buildstep", bs)
for k, b in enumerate(batches):
    wf(f"bld/b{k}", b)
wf("placectl", ctl)
wf(
    "builddone",
    f"scoreboard players set BLD {NS} -1\nfunction {NS}:placectl\n"
    f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"连续S波浪 X~{PATH_XSPAN}, Z~{max(allz)-min(allz)+1}; 按[直接播放]/[全景俯视]"}}]',
)
wf("playcore", [f"scoreboard players set PLAY {NS} 1", f"scoreboard players set SIL {NS} 0", SSTOP] + TRIG_CLEAR + [f"schedule function {NS}:fire 2t"])
wf(
    "play",
    [
        f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先按[停止]"',
        f"function {NS}:playcore",
        f'tellraw @a "[{NS}] GO。连续S型波浪主链,站着听全曲。"'
    ],
)
wf("view", ["gamemode spectator @a", f"tp @a {CAMX} {Y + 55} {CAMZ} 0 90", f'tellraw @a "[{NS}] 俯视S型波浪(spectator)。"'])
wf(
    "stop",
    RESET
    + ["gamemode creative @a", SSTOP]
    + SCHED_CLEAR
    + TRIG_CLEAR
    + [f"scoreboard players set SIL {NS} 1", f"schedule function {NS}:unsil {END_TICKS}t", f"tp @a {PBX} {Y + 3} {OZ}", f'tellraw @a "[{NS}] 已停止(立即静音)。"'],
)
wf("unsil", f"scoreboard players set SIL {NS} 0")
wf("fire", flbuild + [f"setblock {sx} {Y} {sz} minecraft:redstone_block" for sx, sz in src_pts] + [f"schedule function {NS}:firestop {PULSE}t", f"schedule function {NS}:done {END_TICKS}t"])
wf("firestop", TRIG_CLEAR)
wf("done", RESET + ["gamemode creative @a", f'tellraw @a "[{NS}] (end) 重放[直接播放]; 拆 /function {NS}:cleanup。"'])

SEG = 200
clr_segs = (WX1 - WX0 + 16) // SEG + 1
for k in range(clr_segs):
    fx0 = WX0 + k * SEG
    fx1 = min(WX1, fx0 + SEG - 1)
    wf(f"clr/c{k}", f"fill {fx0} {Y - 2} {WZ0} {fx1} {Y + 3} {WZ1} air")
wf("cleardone", [f"scoreboard players set CLR {NS} -1", "forceload remove all", f'tellraw @a "[{NS}] cleaned."'])
cs = [f"execute if score CLR {NS} matches {k} run function {NS}:clr/c{k}" for k in range(clr_segs)]
cs += [
    f"execute if score CLR {NS} matches {clr_segs} run function {NS}:cleardone",
    f"execute if score CLR {NS} matches 0..{clr_segs} run scoreboard players add CLR {NS} 1",
]
wf("clearstep", cs)
wf(
    "cleanup",
    ["gamerule commandModificationBlockLimit 2147483647"]
    + RESET
    + ["gamemode creative @a", SSTOP, f"scoreboard players set BLD {NS} -1"]
    + SCHED_CLEAR
    + TRIG_CLEAR
    + [f"scoreboard players set CLR {NS} 0", f'tellraw @a "[{NS}] tearing down..."'],
)
wf(
    "cfg/polytoggle",
    [
        "scoreboard players set rptmp rpcfg 1",
        "scoreboard players operation rptmp rpcfg -= poly rpcfg",
        "scoreboard players operation poly rpcfg = rptmp rpcfg",
        f'execute if score poly rpcfg matches 1 run tellraw @a "[{NS}] 复音增益 ON"',
        f'execute if score poly rpcfg matches 0 run tellraw @a "[{NS}] 复音增益 OFF"',
    ],
)
wf(
    "cfg/humantoggle",
    [
        "scoreboard players set rptmp rpcfg 1",
        "scoreboard players operation rptmp rpcfg -= human rpcfg",
        "scoreboard players operation human rpcfg = rptmp rpcfg",
        f'execute if score human rpcfg matches 1 run tellraw @a "[{NS}] 微抖动 ON"',
        f'execute if score human rpcfg matches 0 run tellraw @a "[{NS}] 微抖动 OFF"',
    ],
)

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst):
    shutil.rmtree(dst)
shutil.copytree(DP, dst)

nrep = sum(1 for kind, _ in cells if kind == "rep")
ntrig = sum(1 for kind, _ in cells if kind == "trig")
nplaced = sum(len(trackvoice[t][p]) for t in range(2) for p in range(3) if not LIMIT_CELLS)
if LIMIT_CELLS:
    active_ticks = {v for kind, v in cells if kind == "trig"}
    nplaced = sum(1 for t in range(2) for p in range(3) for tick in trackvoice[t][p] if tick in active_ticks)
zwidth = max(allz) - min(allz) + 1
xspan = WX1 - WX0 + 1
fold_chunks = ((WX1 // 16) - (WX0 // 16) + 1) * ((WZ1 // 16) - (WZ0 // 16) + 1)
straight_x = len(cells)

print("=== 42 Codex OLK 连续 S 型波浪主链 ===")
print(f"曲子={NOTES} NS={NS} OX={OX} limit_cells={LIMIT_CELLS}")
print(f"发声音={nplaced} dropped={dropped if not LIMIT_CELLS else 'test'} 钳音={clamped[0]} OFFSET={OFFSET}")
print(f"cells={len(cells)} = {nrep}中继器 + {ntrig}发声列; turns={len(turns)}; XRUN={XRUN}; ZMAX={ZMAX}")
print(f"路径长度={len(cells)}; X跨度≈{PATH_XSPAN} (直线≈{straight_x}, 压缩 {straight_x / max(1, PATH_XSPAN):.2f}x)")
print(f"Z带宽={zwidth}; 两轨 base z={TRACK_Z}; forceload≈{fold_chunks}区块")
print("形态: 单条连续 S 型波浪线 ✓; 无 ROWS/ROWLEN 矩形收纳 ✓")
print("断言: 时间轴 ✓  碰撞 ✓")
print(f"部署 -> {dst}")
print(f"用法: /reload -> /tick rate 80 -> /function {NS}:setup -> 等 built -> [直接播放]")
