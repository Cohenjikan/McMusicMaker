# -*- coding: utf-8 -*-
"""47_build_custom.py — 任务7: 按 HTML 设计器导出的【自定义走线】生成红石机器(七里香, 多乐器)。

输入 = layout_designer.html 导出的参数 JSON(waypoints / base_block / dual / radiate ...)。
继承 43 号已验证的行进脉冲红石原语(中继器 RFACE 朝向 + 拐点红石粉 0 延迟桥 + 辐射和弦),
把 S 波路径换成用户自定义路点路径;按 46 号多乐器映射给七里香上色;
★关键安全修复: forceload 只加载【路径真正经过的区块】(本设计 ~288), 而非包围盒(~1880=过载)。

限制/说明(如实):
- 单轨(dual=false)按 43 验证几何 = 每格 3 声部(上+左右各1), 复音>3 会 dropped(报告数量)。双轨可补满但用户选了单轨。
- 本版未做旋律延音截断(行进脉冲版的 cut 需按脉冲到达时刻调度, 列为下一步)。
- 自定义路径若自交会触发碰撞断言(说明该设计物理上走不通, 需调路点)。
Run: python 47_build_custom.py <params.json> <NS> <OX> [LIMIT_CELLS]
"""
import os, sys, json, shutil
import mido
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))

PARAMS = sys.argv[1] if len(sys.argv) > 1 else "params_qlx_custom.json"
NS     = sys.argv[2] if len(sys.argv) > 2 else "qlxc"
OX     = int(sys.argv[3]) if len(sys.argv) > 3 else 360000
LIMIT  = int(sys.argv[4]) if len(sys.argv) > 4 else 0
MID    = r"~/Downloads/七里香 周杰伦_爱给网_aigei_com.mid"
OZ, Y  = 0, 255
TPS, PULSE, BATCH = 80, 4, 2000
U = 2 / TPS
SSTOP = "stopsound @a"
CUT_INSTR = {"pad", "lead", "bass"}   # 持续型非钢琴(易拖尾) -> 截延音; 钢琴/鼓不截
MIN_CUT_GT = 4                        # 截断延迟下限(游戏刻)
MELCAP_S = 1.2                        # 旋律延音上限(秒)
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界 (1)/datapacks"
RFACE = {(1, 0): "west", (-1, 0): "east", (0, 1): "north", (0, -1): "south"}

P = json.load(open(os.path.join(HERE, PARAMS), encoding="utf-8"))
WPS = [tuple(w) for w in P["waypoints"]]
BASE = P.get("base_block", "minecraft:stone")
DUAL = P.get("dual_track_mirror", False)
VPC = 3                                                   # 单路径几何只支持每格3声部(上+左右各1)
if DUAL:
    print("[警告] 自定义【单路径】暂不支持双轨6声部(chord 仅摆3, 旧版会静默丢3-5声部)。"
          "已按单轨3声部生成; 要6声部双轨镜像请用 48_build_swave_multi.py 的曲折直线S波形态。")

# ---- 多乐器映射(46 号同源)----
MM = json.load(open(os.path.join(HERE, "redpiano_map_multi.json"), encoding="utf-8"))
FAM = {int(k): v for k, v in MM["family_map"].items()}
GD = {int(k): v for k, v in MM["gm_drum_map"].items()}
INSTR = MM["instruments"]
clamped = [0]
def map_note_multi(midi, vel, instr):
    inst = INSTR[instr]
    if not inst["pitched"]:
        dt = GD.get(midi, "snare")
        if dt not in inst["types"]: dt = next(iter(inst["types"]))
        return inst["types"][dt], 12, inst["sound"][f"drum:{dt}"]
    bands = inst["bands"]; band = min(bands, key=lambda b: abs(b - midi)); raw = 12 + (midi - band)
    nv = max(0, min(24, raw))
    if not (0 <= raw <= 24): clamped[0] += 1
    layer = ("p" if vel < 0.40 else ("mf" if vel < 0.72 else "f")) if instr == "pno" else "mf"
    if layer not in inst["layers"]: layer = "mf" if "mf" in inst["layers"] else inst["layers"][0]
    key = f"{band}_{layer}"
    return inst["block"][key], nv, inst["sound"][key]

# ---- 解析七里香(带乐器标签)----
mf = mido.MidiFile(MID); cur = defaultdict(int); active = {}; t = 0.0; notes = []
for msg in mf:
    t += msg.time
    if msg.type == "program_change": cur[msg.channel] = msg.program
    elif msg.type == "note_on" and msg.velocity > 0: active[(msg.channel, msg.note)] = (t, msg.velocity)
    elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
        k = (msg.channel, msg.note)
        if k in active:
            st, v = active.pop(k); ch = msg.channel
            instr = "drum" if ch == 9 else FAM.get(cur[ch] // 8, "pno")
            notes.append({"t": round(st, 3), "midi": int(msg.note), "vel": round(v / 127.0, 3),
                          "dur": round(max(t - st, 0.02), 3), "instr": instr})

# ---- 量化 + 单轨声部分配 ----
bycell = defaultdict(list)
for n in notes:
    if n["vel"] >= 0.04: bycell[round(n["t"] / U)].append(n)
trig = sorted(bycell)
voices = {}; dropped = 0
cut_events = set(); meldur = {}; instr_count = defaultdict(int)   # 旋律截断数据
for tk in trig:
    g = sorted(bycell[tk], key=lambda x: -x["midi"])[:VPC]
    dropped += max(0, len(bycell[tk]) - VPC)
    vl = []
    for n in g:
        block, nv, sound = map_note_multi(n["midi"], n["vel"], n["instr"])
        vl.append((block, nv)); instr_count[n["instr"]] += 1
        if n["instr"] in CUT_INSTR:
            cut_events.add(sound)
            meldur[tk] = n["dur"] if tk not in meldur else max(meldur[tk], n["dur"])
    voices[tk] = vl

# ---- cells[] 时间骨架(rep 变延迟 + trig)----
OFFSET = 1 if trig and trig[0] == 0 else 0
cells = []; prev = 0
for T0 in trig:
    T = T0 + OFFSET; G = T - prev
    reps = [4] * (G // 4) + ([G % 4] if G % 4 else [])
    if not reps: reps = [1]
    for d in reps: cells.append(("rep", d))
    cells.append(("trig", T0)); prev = T
cum = 0
for kind, v in cells:
    if kind == "rep": cum += v
    else: assert cum == v + OFFSET, f"时序错位 @{v}"
if LIMIT > 0: cells = cells[:LIMIT]
used_trig = [v for k, v in cells if k == "trig"]
used_trig_set = set(used_trig)
MAXTICK = max(used_trig) if used_trig else 0

# ---- 旋律延音截断: 每个含旋律的刻算 release 游戏刻(相对 fire), 在 fire 里 schedule cutmel ----
# 脉冲到达 trig 刻 T0 的游戏刻 = (T0+OFFSET)*2 (与 cells[] 时间轴同源); release = 该刻 + 截断延迟。
mel_ticks = sorted(tk for tk in meldur if tk in used_trig_set)
CAP_GT = round(MELCAP_S * 80)
cut_sched = {}; cut_delays = []
for j, tk in enumerate(mel_ticks):
    d = min(round(meldur[tk] * 80), CAP_GT)                 # MIDI 时值 -> 游戏刻, 封顶
    if j + 1 < len(mel_ticks):
        d = min(d, (mel_ticks[j + 1] - tk) * 2 - 1)         # 不越过下一旋律刻
    d = max(MIN_CUT_GT, d); cut_delays.append(d)
    cut_sched[tk] = (tk + OFFSET) * 2 + d                   # 相对 fire 的绝对游戏刻
cut_events = sorted(cut_events)

# ---- 自定义路点 -> 路径(X 后 Z 直角, 拐点插红石粉, 单轨)----
def layout_custom(wps, ncells):
    steps = []; cx, cz = wps[0]
    for k in range(1, len(wps)):
        tx, tz = wps[k]
        while cx != tx: s = 1 if tx > cx else -1; steps.append((s, 0)); cx += s
        while cz != tz: s = 1 if tz > cz else -1; steps.append((0, s)); cz += s
    x, z = wps[0]
    if not steps: return [(x, z, (1, 0))], []
    pos = [(x, z, steps[0])]; turns = []; curd = steps[0]; si = 1
    while len(pos) < ncells:
        sd = steps[si] if si < len(steps) else curd; si += 1
        if sd == curd:
            x += sd[0]; z += sd[1]; pos.append((x, z, sd))
        else:
            turns.append((x + curd[0], z + curd[1]))
            x += curd[0] + sd[0]; z += curd[1] + sd[1]
            pos.append((x, z, sd)); curd = sd
    return pos[:ncells], turns
pos, turns = layout_custom(WPS, len(cells))

# ---- 发射 setblock + 碰撞断言(自交=碰撞)----
occ = {}
def put(out, x, y, z, blk):
    key = (x, y, z)
    if key in occ and occ[key] != blk and "air" not in (occ[key], blk):
        raise AssertionError(f"碰撞 @{key}: {occ[key]} vs {blk}  (自定义路径自交? 调整路点)")
    occ[key] = blk; out.append(f"setblock {x} {y} {z} {blk}")
def side_off(d): return ((0, 1), (0, -1)) if d[0] != 0 else ((1, 0), (-1, 0))
def chord(out, x, z, d, vl):
    above = vl[0] if len(vl) > 0 else None
    put(out, x, Y - 1, z, BASE)
    put(out, x, Y, z, above[0] if above else BASE)
    if above:
        put(out, x, Y + 1, z, f"minecraft:note_block[note={above[1]}]"); put(out, x, Y + 2, z, "air")
    oa, ob = side_off(d)
    for sd, off in ((vl[1] if len(vl) > 1 else None, oa), (vl[2] if len(vl) > 2 else None, ob)):
        if sd:
            ax, az = x + off[0], z + off[1]
            put(out, ax, Y - 1, az, sd[0]); put(out, ax, Y, az, f"minecraft:note_block[note={sd[1]}]"); put(out, ax, Y + 1, az, "air")

build = ["gamerule commandModificationBlockLimit 2147483647"]
for i, (x, z, d) in enumerate(pos):
    wx, wz = OX + x, OZ + z; kind, v = cells[i]
    if kind == "rep":
        put(build, wx, Y - 1, wz, BASE)
        put(build, wx, Y, wz, f"minecraft:repeater[facing={RFACE[d]},delay={v}]")
    else:
        chord(build, wx, wz, d, voices.get(v, []))
for (tx, tz) in turns:
    put(build, OX + tx, Y - 1, OZ + tz, BASE); put(build, OX + tx, Y, OZ + tz, "minecraft:redstone_wire")
d0 = pos[0][2]; SRC = (OX + pos[0][0] - d0[0], OZ + pos[0][1] - d0[1])
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]

# ---- 关键: 只 forceload 路径经过的区块(非包围盒)----
chunks = sorted(set((x >> 4, z >> 4) for (x, _, z) in occ))
flbuild = ["forceload remove all"] + [f"forceload add {cx*16} {cz*16}" for (cx, cz) in chunks]
NCH = len(chunks)
allx = [k[0] for k in occ]; allz = [k[2] for k in occ]
WX0, WZ0, WX1, WZ1 = min(allx) - 2, min(allz) - 2, max(allx) + 2, max(allz) + 2

DP = os.path.join(HERE, "build", NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8", newline="\n").write(c if c.endswith("\n") else c + "\n")
def wf(n, b): w(f"data/{NS}/function/{n}.mcfunction", b if isinstance(b, str) else "\n".join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 七里香 自定义走线(行进脉冲, per-path forceload, tick80)"}},
          open(os.path.join(DP, "pack.mcmeta"), "w", encoding="utf-8"), indent=2)
w("data/minecraft/tags/function/load.json", json.dumps({"values": [f"{NS}:load"]}))
w("data/minecraft/tags/function/tick.json", json.dumps({"values": [f"{NS}:tick"]}))

MUSIC_TICKS = (MAXTICK + OFFSET) * 2; END_TICKS = MUSIC_TICKS + 200; PBX = OX - 3
CAMX, CAMZ = OX + (max(allx) - min(allx)) // 2, OZ + (max(allz) - min(allz)) // 2
def lbtn(bx, cmd, lines):
    msgs = ",".join('\'{"text":"%s"}\'' % s for s in (list(lines) + ["", "", "", ""])[:4])
    return [f"setblock {bx} {Y-1} {OZ} minecraft:redstone_lamp",
            f'setblock {bx} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"{cmd}",auto:0b}}',
            f"setblock {bx} {Y+1} {OZ} minecraft:stone_button[face=floor]",
            f"setblock {bx} {Y-1} {OZ-2} minecraft:redstone_lamp",
            "setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}" % (bx, Y, OZ-2, msgs)]
ctl = ["gamerule commandModificationBlockLimit 2147483647"]
ctl += lbtn(PBX,   f"function {NS}:play", ["[直接播放]", "自定义走线", "听全曲"])
ctl += lbtn(PBX-2, f"function {NS}:view", ["[全景俯视]", "看走线"])
ctl += lbtn(PBX-4, f"function {NS}:stop", ["[停止]", "立即静音"])
ctl += lbtn(PBX-6, f"function {NS}:cfg/polytoggle", ["[复音增益]", "大和弦防糊"])
ctl += lbtn(PBX-8, f"function {NS}:cfg/humantoggle", ["[微抖动]", "去复印感"])

RESET = [f"scoreboard players set PLAY {NS} 0", f"scoreboard players set SIL {NS} 0"]
SCHED_CLEAR = [f"schedule clear {NS}:{f}" for f in ("done", "fire", "firestop", "startbuild", "cutmel")]
TRIG_CLEAR = [f"setblock {SRC[0]} {Y} {SRC[1]} minecraft:air"]
wf("load", [f"scoreboard objectives add {NS} dummy", f"scoreboard players set BLD {NS} -1"] + RESET
   + ["forceload remove all", "scoreboard objectives add rpcfg dummy", "scoreboard players set poly rpcfg 1", "scoreboard players set human rpcfg 1"]
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] 七里香 自定义走线 loaded. ","color":"aqua"}},{{"text":"需RedPiano+qzpno. /tick rate 80 -> /function {NS}:setup"}}]'])
wf("setup", RESET + ["gamemode creative @a", SSTOP] + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f"tp @a {PBX} {Y+3} {OZ}", f"schedule function {NS}:startbuild 60t", f'tellraw @a "[{NS}] reset+forceload({NCH}区块); building..."'])
wf("startbuild", f"scoreboard players set BLD {NS} 0\ntellraw @a \"[{NS}] building 自定义走线 ({len(cells)}cell, {len(turns)}拐点)...\"")
wf("tick", f"execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n"
           f"execute if score SIL {NS} matches 1 run {SSTOP}")
bs = [f"execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}" for k in range(len(batches))]
bs += [f"execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone",
       f"execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1"]
wf("buildstep", bs)
for k, b in enumerate(batches): wf(f"bld/b{k}", b)
wf("placectl", ctl)
wf("builddone", f"scoreboard players set BLD {NS} -1\nfunction {NS}:placectl\n"
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"自定义走线; 按[直接播放]/[全景俯视]"}}]')
wf("cutmel", [f"stopsound @a record {ev}" for ev in cut_events] or [f"# {NS}: 无旋律截断事件(纯钢琴/鼓)"])
wf("playcore", [f"scoreboard players set PLAY {NS} 1", f"scoreboard players set SIL {NS} 0", SSTOP, f"schedule clear {NS}:cutmel"] + TRIG_CLEAR + [f"schedule function {NS}:fire 2t"])
wf("play", [f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先[停止]"',
            f"function {NS}:playcore", f'tellraw @a "[{NS}] GO。自定义走线, 站着听全曲。"'])
wf("view", ["gamemode spectator @a", f"tp @a {CAMX} {Y+70} {CAMZ} 0 90", f'tellraw @a "[{NS}] 俯视走线(spectator)。"'])
wf("stop", RESET + ["gamemode creative @a", SSTOP] + SCHED_CLEAR + TRIG_CLEAR
   + [f"scoreboard players set SIL {NS} 1", f"schedule function {NS}:unsil {END_TICKS}t", f"tp @a {PBX} {Y+3} {OZ}", f'tellraw @a "[{NS}] 已停止。"'])
wf("unsil", f"scoreboard players set SIL {NS} 0")
fire_lines = flbuild + [f"setblock {SRC[0]} {Y} {SRC[1]} minecraft:redstone_block"]
fire_lines += [f"schedule function {NS}:cutmel {cut_sched[tk]}t append" for tk in mel_ticks]
fire_lines += [f"schedule function {NS}:firestop {PULSE}t", f"schedule function {NS}:done {END_TICKS}t"]
wf("fire", fire_lines)
wf("firestop", TRIG_CLEAR)
wf("done", RESET + ["gamemode creative @a", f'tellraw @a "[{NS}] (end) 重放[直接播放]; 拆 /function {NS}:cleanup。"'])
wf("cleanup", ["gamerule commandModificationBlockLimit 2147483647"] + RESET + ["gamemode creative @a", SSTOP, f"scoreboard players set BLD {NS} -1"]
   + SCHED_CLEAR + TRIG_CLEAR + [f"fill {WX0} {Y-2} {WZ0} {WX1} {Y+3} {WZ1} air", "forceload remove all", f'tellraw @a "[{NS}] cleaned."'])
for nm, sc in (("polytoggle", "poly"), ("humantoggle", "human")):
    wf(f"cfg/{nm}", ["scoreboard players set rptmp rpcfg 1", f"scoreboard players operation rptmp rpcfg -= {sc} rpcfg",
                     f"scoreboard players operation {sc} rpcfg = rptmp rpcfg",
                     f'execute if score {sc} rpcfg matches 1 run tellraw @a "[{NS}] {sc} ON"',
                     f'execute if score {sc} rpcfg matches 0 run tellraw @a "[{NS}] {sc} OFF"'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)

nrep = sum(1 for k, _ in cells if k == "rep"); ntrig = len(used_trig)
nplaced = sum(min(VPC, len(voices.get(v, []))) for v in used_trig)
xspan = max(allx) - min(allx) + 1; zspan = max(allz) - min(allz) + 1
print(f"=== 47 自定义走线 [{NS}] 七里香 ===")
print(f"参数={PARAMS} 路点={len(WPS)} 单轨={not DUAL}(每格{VPC}声部) LIMIT={LIMIT}")
print(f"cells={len(cells)} = {nrep}中继器 + {ntrig}发声列; 拐点={len(turns)}; 发声音={nplaced} dropped={dropped} 钳音={clamped[0]}")
print(f"乐器分布(发声盒)={dict(instr_count)}")
cut_ds = sorted(cut_delays)
print(f"★旋律延音截断: {len(mel_ticks)} 个旋律刻, 停 {len(cut_events)} 个事件; 截延迟中位 {cut_ds[len(cut_ds)//2]/80:.2f}s (上限 {MELCAP_S}s)" if mel_ticks else "★旋律延音截断: 无 cut-instr 声部(纯钢琴/鼓), 不截")
print(f"占地 X[{WX0}..{WX1}]={xspan} Z[{WZ0}..{WZ1}]={zspan}")
print(f"★per-path forceload = {NCH} 区块 (包围盒会是 {((WX1//16)-(WX0//16)+1)*((WZ1//16)-(WZ0//16)+1)} -> 已避免过载)")
print(f"批次={len(batches)}; 无碰撞(路径不自交)✓; 部署 -> {dst}")
print(f"用法: /reload -> /tick rate 80 -> /function {NS}:setup (等 built) -> [直接播放]")
