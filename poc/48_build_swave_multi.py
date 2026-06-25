# -*- coding: utf-8 -*-
"""48_build_swave_multi.py — 任务5+首推形态: 多乐器 镜像均衡 S 型波浪(曲折直线)行进脉冲 + 旋律延音截断。

= 43 号(已验证的 S 型连续波浪时间轴 + 第二轨中轴镜像 + 双轨贪心均衡)
  ⊕ 46 号(直接读 .mid 按 GM 家族自动多乐器映射 + 持续型非钢琴旋律延音截断)。

为什么新建而不是改 43:
  43/wllsym 是用户已实测的单钢琴稳定版, 不动它(保留回退基线), 按 45->46 的惯例新增多乐器版。
  本脚本对纯钢琴曲(如我落泪钢琴版)退化为 43 的行为(全 pno, 无可截旋律); 对多乐器曲(七里香)
  自动给非钢琴声部上 pad/lead/bass 采样, 并把它们的延音收回到作曲时值, 让主旋律一颗颗清楚。

行进脉冲版旋律截断(与 46 同算法, 只把"相对发声那一刻"改成"相对 fire 的绝对游戏刻"):
  脉冲在 /tick rate 80 下到达 trig 刻 T0 的游戏刻 = (T0+OFFSET)*2 (与 cells[] 时间轴同源, 已游戏验证)。
  对每个含旋律(cut-instr)音的刻, 在
    release_gt = (T0+OFFSET)*2 + min(MIDI时值*80, MELCAP*80, 到下一旋律刻*2-1)
  处 `schedule function <NS>:cutmel <release_gt>t append`; cutmel = stopsound 掉所有 cut 事件
  (本曲旋律单声部 -> 全局停 pad 即只停当前音; 钢琴自然衰减/鼓短瞬态 不截)。

需 RedPiano 模组 + qzpno 资源包。先跑 gen_multi_map.py 生成 redpiano_map_multi.json。
Run:
  python 48_build_swave_multi.py <song.mid> [NS] [OX] [XRUN] [ZMAX] [LIMIT_CELLS] [--melcap 秒] [--name 名]
Defaults:
  七里香.mid qlxs 370000 3 4 0
"""

import json
import os
import shutil
import sys
import mido
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))

argv = sys.argv[1:]
NAME = None
MELCAP_S = 1.2
if "--name" in argv:
    i = argv.index("--name"); NAME = argv[i + 1]; del argv[i:i + 2]
if "--melcap" in argv:
    i = argv.index("--melcap"); MELCAP_S = float(argv[i + 1]); del argv[i:i + 2]

SRC = argv[0] if len(argv) > 0 else r"C:/Users/Cohen/Downloads/七里香 周杰伦_爱给网_aigei_com.mid"
NS = argv[1] if len(argv) > 1 else "qlxs"
OX = int(argv[2]) if len(argv) > 2 else 370000
XRUN = int(argv[3]) if len(argv) > 3 else 3
ZMAX = int(argv[4]) if len(argv) > 4 else 4
LIMIT_CELLS = int(argv[5]) if len(argv) > 5 else 0
if NAME is None:
    NAME = os.path.splitext(os.path.basename(SRC))[0]

OZ, Y = 0, 255
VOICES, TPS, PULSE = 6, 80, 4
LAMP, PASS, BATCH = "minecraft:redstone_lamp", "minecraft:stone", 2000
SSTOP = "stopsound @a"
CUT_INSTR = {"pad", "lead", "bass"}   # 持续型非钢琴(易拖尾) -> 截延音; 钢琴(自然衰减)/鼓(短瞬态)不截
MIN_CUT_GT = 4                        # 截断延迟下限(游戏刻; 80tps->0.05s), 防截到 attack 没声
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界 (1)/datapacks"

if XRUN < 2:
    raise ValueError("XRUN must be >= 2")
if ZMAX < 2:
    raise ValueError("ZMAX must be >= 2")

RFACE = {
    (1, 0): "west",    # 已由旧脚本验证: facing=west 输出 +X
    (-1, 0): "east",
    (0, 1): "north",  # facing=north 输出 +Z
    (0, -1): "south",
}

# ---- 多乐器映射(46 号同源)----
MM = json.load(open(os.path.join(HERE, "redpiano_map_multi.json"), encoding="utf-8"))
FAMILY = {int(k): v for k, v in MM["family_map"].items()}
GDRUM = {int(k): v for k, v in MM["gm_drum_map"].items()}
INSTR = MM["instruments"]
clamped = [0]


def map_note_multi(midi, vel, instr):
    inst = INSTR[instr]
    if not inst["pitched"]:                                   # 鼓: GM note -> 鼓型, 不移调
        dtype = GDRUM.get(midi, "snare")
        if dtype not in inst["types"]:
            dtype = next(iter(inst["types"]))
        return inst["types"][dtype], 12, inst["sound"][f"drum:{dtype}"]
    bands = inst["bands"]
    band = min(bands, key=lambda b: abs(b - midi))
    raw = 12 + (midi - band)
    nv = max(0, min(24, raw))
    if not (0 <= raw <= 24):
        clamped[0] += 1
    layer = ("p" if vel < 0.40 else ("mf" if vel < 0.72 else "f")) if instr == "pno" else "mf"
    if layer not in inst["layers"]:
        layer = "mf" if "mf" in inst["layers"] else inst["layers"][0]
    key = f"{band}_{layer}"
    return inst["block"][key], nv, inst["sound"][key]


# ---- 解析 .mid: 跟踪每通道 program, 给每个音符打乐器标签 + 时值 ----
mf = mido.MidiFile(SRC)
cur_prog = defaultdict(int)
active = {}
t = 0.0
notes = []
for msg in mf:
    t += msg.time
    if msg.type == "program_change":
        cur_prog[msg.channel] = msg.program
    elif msg.type == "note_on" and msg.velocity > 0:
        active[(msg.channel, msg.note)] = (t, msg.velocity)
    elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
        k = (msg.channel, msg.note)
        if k in active:
            st, v = active.pop(k); ch = msg.channel
            instr = "drum" if ch == 9 else FAMILY.get(cur_prog[ch] // 8, "pno")
            notes.append({"t": round(st, 3), "midi": int(msg.note), "vel": round(v / 127.0, 3),
                          "dur": round(max(t - st, 0.02), 3), "instr": instr, "ch": ch, "prog": cur_prog[ch]})
notes.sort(key=lambda n: n["t"])

U = 2 / TPS

# per-part 统计(报告用)
partstat = defaultdict(lambda: {"notes": 0, "instr": None, "lo": 999, "hi": -1})
for n in notes:
    ps = partstat[(n["ch"], n["prog"])]
    ps["notes"] += 1; ps["instr"] = n["instr"]
    ps["lo"] = min(ps["lo"], n["midi"]); ps["hi"] = max(ps["hi"], n["midi"])

# ---- 量化 + 双轨六声部贪心均衡分配(43 算法), 同时收集旋律截断数据 ----
bycell = defaultdict(list)
for n in notes:
    if n["vel"] >= 0.04:
        bycell[round(n["t"] / U)].append(n)

trackvoice = [[dict(), dict(), dict()], [dict(), dict(), dict()]]
track_note_counts = [0, 0]
track_tick_counts = [0, 0]
dropped = 0
cut_events = set()        # 所有用到的 cut-instr 采样事件(stopsound 目标)
meldur = {}               # tick -> 该刻旋律(cut-instr)音的 MIDI 时值(秒, 取最长), 无则不在表
instr_count = defaultdict(int)
for tick in sorted(bycell):
    grp = bycell[tick]
    g = sorted(grp, key=lambda x: -x["midi"])
    placed = g[:VOICES]
    slots = [[], []]
    for n in placed:
        choices = [tt for tt in range(2) if len(slots[tt]) < 3]
        target = min(choices, key=lambda tt: (track_note_counts[tt] + len(slots[tt]), tt))
        slots[target].append(n)
    for tt in range(2):
        if slots[tt]:
            track_tick_counts[tt] += 1
        for p, n in enumerate(slots[tt]):
            block, nv, sound = map_note_multi(n["midi"], n["vel"], n["instr"])
            trackvoice[tt][p][tick] = (block, nv)
            track_note_counts[tt] += 1
            instr_count[n["instr"]] += 1
            if n["instr"] in CUT_INSTR:
                cut_events.add(sound)
                md = n["dur"]
                meldur[tick] = md if tick not in meldur else max(meldur[tick], md)
    dropped += max(0, len(g) - VOICES)


# ---- 共享时间线 cells[]: 触发刻并集 -> 唯一变延迟骨架(43 原样)----
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
used_trig_set = set(used_trig)
MAXTICK = max(used_trig) if used_trig else 0

# ---- 旋律延音截断: 每个含旋律的刻算 release 游戏刻(相对 fire), 在 fire 里 schedule cutmel ----
mel_ticks = sorted(tk for tk in meldur if tk in used_trig_set)
CAP_GT = round(MELCAP_S * 80)
cut_sched = {}            # tick -> release 游戏刻(相对 fire, 用于 schedule)
cut_delays = []           # 每音的截断延迟(游戏刻, 仅报告用)
for j, tk in enumerate(mel_ticks):
    d = min(round(meldur[tk] * 80), CAP_GT)                     # MIDI 时值 -> 游戏刻, 封顶
    if j + 1 < len(mel_ticks):
        d = min(d, (mel_ticks[j + 1] - tk) * 2 - 1)            # 不越过下一旋律刻(避免截到下一个)
    d = max(MIN_CUT_GT, d)
    cut_delays.append(d)
    cut_sched[tk] = (tk + OFFSET) * 2 + d                       # 发声刻 + 截断延迟 = 相对 fire 的绝对游戏刻
cut_events = sorted(cut_events)


# ---- 连续 S 型波浪路径(43 原样): +X, +Z, +X, -Z, repeat ----
DIRS = [(1, 0), (0, 1), (1, 0), (0, -1)]
SEGLENS = [XRUN, ZMAX - 1, XRUN, ZMAX - 1]


def layout_swave(seq):
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


pos, turns = layout_swave(cells)
path_x = [p[0] for p in pos]
path_z = [p[1] for p in pos]
if turns:
    path_x += [p[0] for p in turns]
    path_z += [p[1] for p in turns]
PATH_ZMIN = min(path_z) if path_z else 0
PATH_ZMAX = max(path_z) if path_z else 0
PATH_XSPAN = max(path_x) - min(path_x) + 1 if path_x else 1
PATH_ZSPAN = PATH_ZMAX - PATH_ZMIN + 1 if path_z else 1
TRACK_SEP = PATH_ZSPAN + 3
TRACK_Z = [OZ, OZ + TRACK_SEP]


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


# ---- 发射 setblock + 碰撞断言(43 原样)----
occ = {}


def put(out, x, y, z, blk):
    key = (x, y, z)
    if key in occ and occ[key] != blk and not (occ[key] == "air" or blk == "air"):
        raise AssertionError(f"碰撞 @{key}: {occ[key]} vs {blk}")
    occ[key] = blk
    out.append(f"setblock {x} {y} {z} {blk}")


def side_offsets(d):
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


def emit_track(t):
    start_xo, start_zo, _ = pos[0]
    _, src_z, _ = track_transform(t, start_xo, start_zo, (1, 0))
    out = [f"setblock {OX - 1} {Y - 1} {src_z} {PASS}"]
    for i, (xo, zo, d) in enumerate(pos):
        mxo, z, md = track_transform(t, xo, zo, d)
        x = OX + mxo
        kind, v = cells[i]
        if kind == "rep":
            put(out, x, Y - 1, z, LAMP)
            put(out, x, Y, z, f"minecraft:repeater[facing={RFACE[md]},delay={v}]")
        else:
            vals = [trackvoice[t][p].get(v) for p in range(3)]
            chord3(out, x, z, md, vals)
    for xo, zo in turns:
        txo, tz = track_turn(t, xo, zo)
        put(out, OX + txo, Y - 1, tz, PASS)
        put(out, OX + txo, Y, tz, "minecraft:redstone_wire")
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
            "description": f"{NS} {NAME} 多乐器镜像均衡S型波浪+旋律截断, tick80",
        }
    },
    open(os.path.join(DP, "pack.mcmeta"), "w", encoding="utf-8"),
    indent=2,
)
w("data/minecraft/tags/function/load.json", json.dumps({"values": [f"{NS}:load"]}))
w("data/minecraft/tags/function/tick.json", json.dumps({"values": [f"{NS}:tick"]}))

build = ["gamerule commandModificationBlockLimit 2147483647"]
for t in range(2):
    build += emit_track(t)
batches = [build[i: i + BATCH] for i in range(0, len(build), BATCH)]

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

src_pts = []
for t in range(2):
    start_xo, start_zo, _ = pos[0]
    _, src_z, _ = track_transform(t, start_xo, start_zo, (1, 0))
    src_pts.append((OX - 1, src_z))
TRIG_CLEAR = [f"setblock {sx} {Y} {sz} minecraft:air" for sx, sz in src_pts]
SCHED_CLEAR = [f"schedule clear {NS}:{f}" for f in ("done", "fire", "firestop", "startbuild", "unsil", "cutmel")]
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
ctl += labeled_button(PBX, f"function {NS}:play", ["[直接播放]", "多乐器镜像", "听全曲"])
ctl += labeled_button(PBX - 2, f"function {NS}:view", ["[全景俯视]", "看镜像S", "灯流光"])
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
        f'tellraw @a ["",{{"text":"[{NS}] {NAME} 多乐器镜像均衡S波+旋律截断 loaded. ","color":"aqua"}},{{"text":"需RedPiano+qzpno. /tick rate 80 -> /function {NS}:setup"}}]'
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
wf("startbuild", f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building 多乐器镜像均衡S波 x{PATH_XSPAN} z{max(allz)-min(allz)+1}..."')
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
    f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"多乐器曲折直线 X~{PATH_XSPAN}, Z~{max(allz)-min(allz)+1}; 按[直接播放]/[全景俯视]"}}]',
)
# cutmel: 停掉旋律(持续型非钢琴)采样 = 收延音; 只停 record 源上的这些事件, 钢琴(也走record但不同事件)不受影响
wf("cutmel", [f"stopsound @a record {ev}" for ev in cut_events] or [f"# {NS}: 无旋律截断事件(纯钢琴/鼓)"])
wf("playcore", [f"scoreboard players set PLAY {NS} 1", f"scoreboard players set SIL {NS} 0", SSTOP, f"schedule clear {NS}:cutmel"] + TRIG_CLEAR + [f"schedule function {NS}:fire 2t"])
wf(
    "play",
    [
        f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先按[停止]"',
        f"function {NS}:playcore",
        f'tellraw @a "[{NS}] GO。多乐器镜像均衡S型波浪, 主旋律已截延音, 站着听全曲。"'
    ],
)
wf("view", ["gamemode spectator @a", f"tp @a {CAMX} {Y + 55} {CAMZ} 0 90", f'tellraw @a "[{NS}] 俯视镜像S型波浪(spectator)。"'])
wf(
    "stop",
    RESET
    + ["gamemode creative @a", SSTOP]
    + SCHED_CLEAR
    + TRIG_CLEAR
    + [f"scoreboard players set SIL {NS} 1", f"schedule function {NS}:unsil {END_TICKS}t", f"tp @a {PBX} {Y + 3} {OZ}", f'tellraw @a "[{NS}] 已停止(立即静音)。"'],
)
wf("unsil", f"scoreboard players set SIL {NS} 0")
# fire: 起脉冲(两轨源各放红石块) + 排所有旋律刻的 cutmel(相对 fire 的绝对游戏刻, append 互不覆盖)
fire_lines = flbuild + [f"setblock {sx} {Y} {sz} minecraft:redstone_block" for sx, sz in src_pts]
fire_lines += [f"schedule function {NS}:cutmel {cut_sched[tk]}t append" for tk in mel_ticks]
fire_lines += [f"schedule function {NS}:firestop {PULSE}t", f"schedule function {NS}:done {END_TICKS}t"]
wf("fire", fire_lines)
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
active_track_counts = track_note_counts[:]
active_track_tick_counts = track_tick_counts[:]
nplaced = sum(len(trackvoice[t][p]) for t in range(2) for p in range(3))
if LIMIT_CELLS:
    active_ticks = used_trig_set
    nplaced = sum(1 for t in range(2) for p in range(3) for tick in trackvoice[t][p] if tick in active_ticks)
    active_track_counts = [
        sum(1 for p in range(3) for tick in trackvoice[t][p] if tick in active_ticks)
        for t in range(2)
    ]
    active_track_tick_counts = [
        len({tick for p in range(3) for tick in trackvoice[t][p] if tick in active_ticks})
        for t in range(2)
    ]
zwidth = max(allz) - min(allz) + 1
fold_chunks = ((WX1 // 16) - (WX0 // 16) + 1) * ((WZ1 // 16) - (WZ0 // 16) + 1)
straight_x = len(cells)
song_s = (trig[-1] - trig[0]) * U if len(trig) > 1 else 0

parts_lines = []
for (ch, prog) in sorted(partstat):
    ps = partstat[(ch, prog)]
    tag = "鼓" if ps["instr"] == "drum" else ("钢琴" if ps["instr"] == "pno" else "★非钢")
    parts_lines.append(f"  ch{ch:>2} program {prog:>3} -> 采样集 {ps['instr']} [{tag}], {ps['notes']} 音, 音域 {ps['lo']}-{ps['hi']}")

cut_ds = sorted(cut_delays)
print("=== 48 多乐器 镜像均衡 S 型波浪(曲折直线) + 旋律截断 ===")
for line in parts_lines:
    print(line)
print(f"曲子={NAME} NS={NS} OX={OX} limit_cells={LIMIT_CELLS} melcap={MELCAP_S}s")
print(f"发声音={nplaced} dropped={dropped if not LIMIT_CELLS else 'test'} 钳音={clamped[0]} OFFSET={OFFSET}")
print(f"乐器分布(发声盒)={dict(instr_count)}")
print(f"轨道音符数 A/B={active_track_counts[0]}/{active_track_counts[1]}; 有音列 A/B={active_track_tick_counts[0]}/{active_track_tick_counts[1]}")
print(f"★旋律延音截断: {len(mel_ticks)} 个旋律刻, 停 {len(cut_events)} 个事件 {[e.split(':')[1].split('_')[0] for e in cut_events][:1]}...; 截延迟中位 {cut_ds[len(cut_ds)//2]/80:.2f}s (上限 {MELCAP_S}s)" if mel_ticks else "★旋律延音截断: 无 cut-instr 声部(纯钢琴/鼓), 不截")
print(f"cells={len(cells)} = {nrep}中继器 + {ntrig}发声列; turns={len(turns)}; XRUN={XRUN}; ZMAX={ZMAX}")
print(f"路径长度={len(cells)}; X跨度≈{PATH_XSPAN} (直线≈{straight_x}, 压缩 {straight_x / max(1, PATH_XSPAN):.2f}x)")
print(f"Z带宽={zwidth}; 两轨 base z={TRACK_Z}; forceload≈{fold_chunks}区块; 曲长≈{song_s:.1f}s")
print("形态: 单条连续 S 型波浪线 ✓; 第二轨中轴镜像 ✓; 贪心均衡分配 ✓")
print("断言: 时间轴 ✓  碰撞 ✓")
print(f"部署 -> {dst}")
print(f"用法: /reload -> /tick rate 80 -> /function {NS}:setup -> 等 built -> [直接播放]")
