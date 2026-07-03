# -*- coding: utf-8 -*-
"""49_build_multilane.py — 从设计器导出参数生成【多轨分布式和弦】直线行进脉冲机器。

消费 layout_designer.html 的新导出字段:
  - form=straight, chord_mode=multilane(每声部一轨, 旧 24/30 共享骨架模型);
  - start_x/start_z/start_y/start_dir(起点+方向; 本版支持 +X, 其它方向留作下一步);
  - max_poly + lane_offsets[{z,y}](每条轨相对脊柱的 Z/Y 位, 用户在侧视里拖出来的);
  - signal_tracks[{dx,dz,name}](纯中继器链, 无音符盒, 供玩家旁边摆命令方块做粒子);
  - base_block(信号基底/导体方块)。

几何 = 48 号已验证的"中继器链 → 强充导体 → 上方音符盒"原语, 每条声部一条独立链:
  - 全部轨共享同一 cells[] 时间骨架(rep 变延迟 + trig), 同 X 同延迟 → 脉冲逐刻列对齐(绝对同步);
  - 每刻按音高从高到低分给 lane 0..max_poly-1(每声部一轨), 超出 max_poly 丢弃;
  - 某轨该刻无音 = 纯导体直通(基底方块, 传脉冲不发声); 有音 = 映射块 + 上方音符盒。
  - 信号轨 = 全程 rep + 直通导体, 无音符盒。

注意: 直线(不折叠)的占地 ≈ X跨度 × Z宽 的整个包围盒, forceload 区块多(本曲 ~600+),
历史上长直线机易过载断音; 若断音, 改用设计器的 S 波折叠(曲折直线)缩短 X 跨度。

需 RedPiano 模组 + qzpno 资源包。
Run: python 49_build_multilane.py <params.json> <song.mid> [NS]
"""
import os, sys, json, shutil
import mido
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))

PARAMS = sys.argv[1] if len(sys.argv) > 1 else "params_olk_multilane.json"
MID    = sys.argv[2] if len(sys.argv) > 2 else r"~/Downloads/【Animenz】One Last Kiss - 新·福音战_爱给网_aigei_com.mid"
NS     = sys.argv[3] if len(sys.argv) > 3 else "olkml"

P = json.load(open(os.path.join(HERE, PARAMS), encoding="utf-8"))
OX = int(P.get("start_x", 0)); OZ = int(P.get("start_z", 0)); Y = int(P.get("start_y", 255))
DIRC = P.get("start_dir", "+X")
BASE = P.get("base_block", "minecraft:stone")
MAXPOLY = int(P.get("max_poly", 7))
LANES = P.get("lane_offsets") or [{"z": i * int(P.get("lane_dz", 2)), "y": 0} for i in range(MAXPOLY)]
NLANE = len(LANES)
SIGS = P.get("signal_tracks") or []
MELCAP_S = 1.2
CUT_INSTR = {"pad", "lead", "bass"}
MIN_CUT_GT = 4
TPS, PULSE, BATCH = 80, 4, 2000
U = 2 / TPS
SSTOP = "stopsound @a"
LAMP = "minecraft:redstone_lamp"
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界 (1)/datapacks"

if DIRC != "+X":
    print(f"[警告] start_dir={DIRC}: 本版只实装 +X 方向; 已按 +X 生成(旋转留作下一步)。")
if P.get("form") not in (None, "straight"):
    print(f"[提示] form={P.get('form')}: 本版按直线骨架生成(多轨直线); S 波折叠留作下一步。")

# +X 方向: 中继器 facing=west(48 已验证), 脉冲沿 +X 推进
RFACE = "west"

# ---- 多乐器映射(46/48 同源)----
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

# ---- 解析 MIDI(带乐器标签 + 时值)----
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

# ---- 量化 + 每声部一轨(按音高从高到低分到 lane 0..NLANE-1)----
bycell = defaultdict(list)
for n in notes:
    if n["vel"] >= 0.04: bycell[round(n["t"] / U)].append(n)
trig = sorted(bycell)
lane_voices = [dict() for _ in range(NLANE)]   # lane -> {tick: (block, nv)}
lane_counts = [0] * NLANE
cut_events = set(); meldur = {}; instr_count = defaultdict(int); dropped = 0
for tk in trig:
    g = sorted(bycell[tk], key=lambda x: -x["midi"])[:NLANE]
    dropped += max(0, len(bycell[tk]) - NLANE)
    for li, n in enumerate(g):
        block, nv, sound = map_note_multi(n["midi"], n["vel"], n["instr"])
        lane_voices[li][tk] = (block, nv); lane_counts[li] += 1; instr_count[n["instr"]] += 1
        if n["instr"] in CUT_INSTR:
            cut_events.add(sound)
            meldur[tk] = n["dur"] if tk not in meldur else max(meldur[tk], n["dur"])

# ---- cells[] 共享时间骨架(rep 变延迟 + trig), 与 47/48 同 ----
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
    else: assert cum == v + OFFSET, f"时序错位 @{v}: cum={cum}!={v+OFFSET}"
used_trig = [v for k, v in cells if k == "trig"]
used_trig_set = set(used_trig)
MAXTICK = max(used_trig) if used_trig else 0

# ---- 旋律截断(钢琴曲为空; 多乐器曲沿用 48 算法)----
mel_ticks = sorted(tk for tk in meldur if tk in used_trig_set)
CAP_GT = round(MELCAP_S * 80)
cut_sched = {}
for j, tk in enumerate(mel_ticks):
    d = min(round(meldur[tk] * 80), CAP_GT)
    if j + 1 < len(mel_ticks): d = min(d, (mel_ticks[j + 1] - tk) * 2 - 1)
    cut_sched[tk] = (tk + OFFSET) * 2 + max(MIN_CUT_GT, d)
cut_events = sorted(cut_events)

# ---- 发射 setblock + 碰撞断言 ----
occ = {}
def put(out, x, y, z, blk):
    key = (x, y, z)
    if key in occ and occ[key] != blk and "air" not in (occ[key], blk):
        raise AssertionError(f"碰撞 @{key}: {occ[key]} vs {blk}")
    occ[key] = blk; out.append(f"setblock {x} {y} {z} {blk}")

sources = []   # (x,y,z) 每条链的红石源(脉冲起点)
def emit_chain(out, lz, ly, voices):
    """一条链(lane 或 signal): 沿 +X 铺 cells[]; voices=None 表示信号轨(全直通无音符盒)。
    地板/直通导体统一用 BASE(基座方块), 不再用红石灯(用户要求统一基座)。"""
    z = OZ + lz; yb = Y + ly
    put(out, OX - 1, yb - 1, z, BASE)          # 源脚下floor
    sources.append((OX - 1, yb, z))
    for i, (kind, v) in enumerate(cells):
        x = OX + i
        if kind == "rep":
            put(out, x, yb - 1, z, BASE)
            put(out, x, yb, z, f"minecraft:repeater[facing={RFACE},delay={v}]")
        else:
            note = voices.get(v) if voices is not None else None
            put(out, x, yb - 1, z, BASE)
            put(out, x, yb, z, note[0] if note else BASE)      # 映射块(导体) 或 基底直通
            if note:
                put(out, x, yb + 1, z, f"minecraft:note_block[note={note[1]}]")
                put(out, x, yb + 2, z, "air")

build = ["gamerule commandModificationBlockLimit 2147483647"]
for li in range(NLANE):
    emit_chain(build, LANES[li]["z"], LANES[li].get("y", 0), lane_voices[li])
for sg in SIGS:
    emit_chain(build, int(sg.get("dz", 0)), 0, None)           # 信号轨(无音符盒)
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]

# ---- per-path forceload(直线会接近包围盒, 仍只 add 经过的区块)----
chunks = sorted(set((x >> 4, z >> 4) for (x, _, z) in occ))
flbuild = ["forceload remove all"] + [f"forceload add {cx*16} {cz*16}" for (cx, cz) in chunks]
NCH = len(chunks)
allx = [k[0] for k in occ]; allz = [k[2] for k in occ]; ally = [k[1] for k in occ]
WX0, WZ0, WX1, WZ1 = min(allx) - 2, min(allz) - 2, max(allx) + 2, max(allz) + 2
WY0, WY1 = min(ally) - 2, max(ally) + 2

# ---- 数据包 ----
DP = os.path.join(HERE, "build", NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8", newline="\n").write(c if c.endswith("\n") else c + "\n")
def wf(n, b): w(f"data/{NS}/function/{n}.mcfunction", b if isinstance(b, str) else "\n".join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 多轨分布式直线行进脉冲(每声部一轨), tick80"}},
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
ctl += lbtn(PBX,   f"function {NS}:play", ["[直接播放]", "多轨分布", "听全曲"])
ctl += lbtn(PBX-2, f"function {NS}:view", ["[全景俯视]", "看多轨"])
ctl += lbtn(PBX-4, f"function {NS}:stop", ["[停止]", "立即静音"])
ctl += lbtn(PBX-6, f"function {NS}:cfg/polytoggle", ["[复音增益]", "大和弦防糊"])
ctl += lbtn(PBX-8, f"function {NS}:cfg/humantoggle", ["[微抖动]", "去复印感"])

RESET = [f"scoreboard players set PLAY {NS} 0", f"scoreboard players set SIL {NS} 0"]
SCHED_CLEAR = [f"schedule clear {NS}:{f}" for f in ("done", "fire", "firestop", "startbuild", "unsil", "cutmel")]
TRIG_CLEAR = [f"setblock {sx} {sy} {sz} minecraft:air" for (sx, sy, sz) in sources]
wf("load", [f"scoreboard objectives add {NS} dummy", f"scoreboard players set BLD {NS} -1", f"scoreboard players set CLR {NS} -1"] + RESET
   + ["forceload remove all", "scoreboard objectives add rpcfg dummy", "scoreboard players set poly rpcfg 1", "scoreboard players set human rpcfg 1"]
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] 多轨分布式直线机 loaded. ","color":"aqua"}},{{"text":"需RedPiano+qzpno. /tick rate 80 -> /function {NS}:setup"}}]'])
wf("setup", RESET + ["gamemode creative @a", SSTOP, f"scoreboard players set CLR {NS} -1"] + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f"tp @a {PBX} {Y+3} {OZ}", f"schedule function {NS}:startbuild 100t", f'tellraw @a "[{NS}] reset+forceload({NCH}区块); building 多轨..."'])
wf("startbuild", f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building {NLANE}轨 + {len(SIGS)}信号轨, {len(cells)}cell..."')
wf("tick", f"execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n"
           f"execute if score CLR {NS} matches 0.. run function {NS}:clearstep\n"
           f"execute if score SIL {NS} matches 1 run {SSTOP}")
bs = [f"execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}" for k in range(len(batches))]
bs += [f"execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone",
       f"execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1"]
wf("buildstep", bs)
for k, b in enumerate(batches): wf(f"bld/b{k}", b)
wf("placectl", ctl)
wf("builddone", f"scoreboard players set BLD {NS} -1\nfunction {NS}:placectl\n"
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"{NLANE}轨分布式直线; 按[直接播放]/[全景俯视]"}}]')
wf("cutmel", [f"stopsound @a record {ev}" for ev in cut_events] or [f"# {NS}: 无旋律截断事件(纯钢琴/鼓)"])
wf("playcore", [f"scoreboard players set PLAY {NS} 1", f"scoreboard players set SIL {NS} 0", SSTOP, f"schedule clear {NS}:cutmel"] + TRIG_CLEAR + [f"schedule function {NS}:fire 2t"])
wf("play", [f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先[停止]"',
            f"function {NS}:playcore", f'tellraw @a "[{NS}] GO。多轨分布式直线, 站着听全曲。"'])
wf("view", ["gamemode spectator @a", f"tp @a {CAMX} {Y+80} {CAMZ} 0 90", f'tellraw @a "[{NS}] 俯视多轨(spectator)。"'])
wf("stop", RESET + ["gamemode creative @a", SSTOP] + SCHED_CLEAR + TRIG_CLEAR
   + [f"scoreboard players set SIL {NS} 1", f"schedule function {NS}:unsil {END_TICKS}t", f"tp @a {PBX} {Y+3} {OZ}", f'tellraw @a "[{NS}] 已停止。"'])
wf("unsil", f"scoreboard players set SIL {NS} 0")
fire_lines = flbuild + [f"setblock {sx} {sy} {sz} minecraft:redstone_block" for (sx, sy, sz) in sources]
fire_lines += [f"schedule function {NS}:cutmel {cut_sched[tk]}t append" for tk in mel_ticks]
fire_lines += [f"schedule function {NS}:firestop {PULSE}t", f"schedule function {NS}:done {END_TICKS}t"]
wf("fire", fire_lines)
wf("firestop", TRIG_CLEAR)
wf("done", RESET + ["gamemode creative @a", f'tellraw @a "[{NS}] (end) 重放[直接播放]; 拆 /function {NS}:cleanup。"'])
SEG = 200
clr_segs = (WX1 - WX0 + 16) // SEG + 1
for k in range(clr_segs):
    fx0 = WX0 + k * SEG; fx1 = min(WX1, fx0 + SEG - 1)
    wf(f"clr/c{k}", f"fill {fx0} {WY0} {WZ0} {fx1} {WY1} {WZ1} air")
wf("cleardone", [f"scoreboard players set CLR {NS} -1", "forceload remove all", f'tellraw @a "[{NS}] cleaned."'])
cs = [f"execute if score CLR {NS} matches {k} run function {NS}:clr/c{k}" for k in range(clr_segs)]
cs += [f"execute if score CLR {NS} matches {clr_segs} run function {NS}:cleardone",
       f"execute if score CLR {NS} matches 0..{clr_segs} run scoreboard players add CLR {NS} 1"]
wf("clearstep", cs)
wf("cleanup", ["gamerule commandModificationBlockLimit 2147483647"] + RESET + ["gamemode creative @a", SSTOP, f"scoreboard players set BLD {NS} -1"]
   + SCHED_CLEAR + TRIG_CLEAR + [f"scoreboard players set CLR {NS} 0", f'tellraw @a "[{NS}] tearing down..."'])
for nm, sc in (("polytoggle", "poly"), ("humantoggle", "human")):
    wf(f"cfg/{nm}", ["scoreboard players set rptmp rpcfg 1", f"scoreboard players operation rptmp rpcfg -= {sc} rpcfg",
                     f"scoreboard players operation {sc} rpcfg = rptmp rpcfg",
                     f'execute if score {sc} rpcfg matches 1 run tellraw @a "[{NS}] {sc} ON"',
                     f'execute if score {sc} rpcfg matches 0 run tellraw @a "[{NS}] {sc} OFF"'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)

# ---- 报告 ----
nrep = sum(1 for k, _ in cells if k == "rep"); ntrig = len(used_trig)
nplaced = sum(lane_counts)
nnote = sum(1 for vv in occ.values() if vv.startswith("minecraft:note_block"))
xspan = max(allx) - min(allx) + 1; zspan = max(allz) - min(allz) + 1; yspan = max(ally) - min(ally) + 1
bbox_chunks = ((WX1 // 16) - (WX0 // 16) + 1) * ((WZ1 // 16) - (WZ0 // 16) + 1)
print(f"=== 49 多轨分布式直线 [{NS}] {P.get('song','?')[:30]} ===")
print(f"参数={PARAMS} 起点({OX},{OZ},Y{Y}) 方向={DIRC} 基底={BASE.replace('minecraft:','')}")
print(f"轨数={NLANE}(max_poly={MAXPOLY}) + 信号轨={len(SIGS)}; 每声部一轨(按音高分配)")
print(f"lane 音数分布={lane_counts}  乐器={dict(instr_count)}")
print(f"cells={len(cells)}={nrep}中继器+{ntrig}发声列; 发声音={nplaced} dropped={dropped} 钳音={clamped[0]}; 音符盒={nnote}")
print(f"旋律截断: {len(mel_ticks)}个旋律刻/{len(cut_events)}事件 (钢琴曲为0)")
print(f"占地 X[{WX0}..{WX1}]={xspan} Z[{WZ0}..{WZ1}]={zspan} Y[{WY0}..{WY1}]={yspan}")
print(f"★per-path forceload={NCH}区块 (包围盒 {bbox_chunks})")
if NCH > 360:
    print(f"⚠ forceload {NCH} 区块 > ~360 安全线: 长直线易过载断音! 若断音, 用设计器换 S波折叠缩短 X 跨度后重导出。")
print(f"批次={len(batches)}; 无碰撞✓ 时序✓; 部署 -> {dst}")
print(f"用法: /reload -> /tick rate 80 -> /function {NS}:setup (等 built) -> [直接播放]")
