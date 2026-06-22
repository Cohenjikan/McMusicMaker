# -*- coding: utf-8 -*-
"""24_build_sync.py — 同步密集真音符盒机器(共享中继器骨架, 音符列对齐)。

解决 23(密集)的问题: 23 给每条 lane 单独的中继器链(只塞本 lane 的音), 各 lane 长度不一
  ([3917,3340,...,1764]) -> 同一拍的音落在不同 X -> "音步岔开"、看着不同步。

本版(同步): 取所有 lane 触发刻的【并集】构成【唯一共享骨架】cells[], 7 条 lane 全部
  铺【完全相同】的中继器链(同延迟、同 X) -> 脉冲在每条 lane 同刻到达同一列
  -> 绝对同步 + 音符盒在 X 上对齐成列(发声列的红石灯同时点亮成一竖排)。
  发声列: 本 lane 有音 = 映射导体块(被前中继器强充能)+ 上坐音符盒; 无音 = 纯石导体直通(0延迟)。
  空白用变延迟中继器压缩: 每个 1..4 红石刻(0.1~0.4s)只占 1 格, gap 用 [4,4,..,余] 拼。
时序: tick80, U=1红石刻=0.025s。某发声列累计延迟(红石刻)== 该刻 -> 全曲忠实且各 lane 同步。

需 RedPiano 模组 + qzpno 资源包。Run: python 24_build_sync.py [notes_wll.json] [NS] [OX]
"""
import os, sys, json, shutil, math
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = sys.argv[1] if len(sys.argv) > 1 else 'notes_wll.json'
NS = sys.argv[2] if len(sys.argv) > 2 else 'qzws'
OX = int(sys.argv[3]) if len(sys.argv) > 3 else 170000
OZ = 0
Y, LANE_DZ = 255, 2            # 天上(上方空气=音符盒可发声); lane 占1排, 间隔2(留1空防串扰)
LAMP, RFACING, BATCH = 'redstone_lamp', 'west', 2000   # facing=west -> 输出 +X; 灯垫发声列下=进度
PASS = 'minecraft:stone'       # 无音发声列的纯导体直通块
MAXLANES, VEL_FLOOR = 7, 0.04
TPS, PULSE = 80, 4
U = 2 / TPS                    # 0.025s = 1 红石刻
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"

notes = json.load(open(os.path.join(HERE, NOTES), encoding='utf-8'))['notes']
rp = json.load(open(os.path.join(HERE, 'redpiano_map.json'), encoding='utf-8'))
bands = rp['bands']; RPMAP = rp['map']
def layer_of(v): return 'p' if v < 0.40 else ('mf' if v < 0.72 else 'f')
clamped = [0]
def map_note(m, v):
    band = min(bands, key=lambda b: abs(b - m)); nv = 12 + (m - band)
    if nv < 0 or nv > 24: clamped[0] += 1
    nv = max(0, min(24, nv))
    return RPMAP[f'{band}_{layer_of(v)}']['block'], nv

# --- 量化到 1 红石刻格 + 按音高排名分 lane(每 lane 每刻 <=1 音) ---
bycell = defaultdict(list)
for n in notes:
    if n['vel'] >= VEL_FLOOR: bycell[round(n['t'] / U)].append(n)
lane_at = [dict() for _ in range(MAXLANES)]    # lane_at[L] = {tick: (block, nv)}
dropped = 0
for tick, grp in bycell.items():
    for i, n in enumerate(sorted(grp, key=lambda x: -x['midi'])):
        if i >= MAXLANES: dropped += 1; continue
        lane_at[i][tick] = map_note(n['midi'], n['vel'])
NLANES = max((L + 1 for L in range(MAXLANES) if lane_at[L]), default=1)

# --- 共享骨架 cells[]: 所有 lane 触发刻并集 -> 唯一中继器链(各 lane 必同步) ---
trig = sorted(bycell)
MAXTICK = trig[-1]
OFFSET = 1 if trig[0] == 0 else 0      # 首音在 tick0 时加 1 刻全局偏移(防发声格直连源弱充能); 各 lane 同偏移=不影响同步
cells = []                              # ('rep', delay 1..4) | ('trig', 原始tick)
prev = 0
for T0 in trig:
    T = T0 + OFFSET; G = T - prev
    reps = [4] * (G // 4) + ([G % 4] if G % 4 else [])
    if not reps: reps = [1]
    for d in reps: cells.append(('rep', d))
    cells.append(('trig', T0))
    prev = T
NCELLS = len(cells)
# 校验: 每个发声列的累计延迟(红石刻) 必须 == 该刻+OFFSET
cum = 0
for kind, v in cells:
    if kind == 'rep': cum += v
    else: assert cum == v + OFFSET, f"时序错位 @tick {v}: cum={cum} != {v + OFFSET}"

def lane_spine(lane_z, notes_at):
    """一条 lane: 沿共享 cells[] 铺完全相同的中继器骨架; 发声列按本 lane 是否有音放音符盒/直通。"""
    sz = OZ + lane_z
    out = [f'setblock {OX-1} {Y-1} {sz} minecraft:stone']    # 源支撑(红石块 fire 时放 OX-1,Y)
    x = OX
    for kind, v in cells:
        if kind == 'rep':
            out.append(f'setblock {x} {Y-1} {sz} minecraft:stone')
            out.append(f'setblock {x} {Y} {sz} minecraft:repeater[facing={RFACING},delay={v}]')
        else:                                                # 发声列(所有 lane 同 X -> 对齐成列)
            note = notes_at.get(v)
            if note:
                block, nv = note
                out.append(f'setblock {x} {Y-1} {sz} minecraft:{LAMP}')                  # 灯(发声列亮)
                out.append(f'setblock {x} {Y} {sz} {block}')                             # 映射导体(前中继器强充能)
                out.append(f'setblock {x} {Y+1} {sz} minecraft:note_block[note={nv}]')   # 真音符盒
                out.append(f'setblock {x} {Y+2} {sz} air')                               # 上方空气(发声必需)
            else:
                out.append(f'setblock {x} {Y-1} {sz} minecraft:stone')                   # 支撑
                out.append(f'setblock {x} {Y} {sz} {PASS}')                              # 纯导体直通(0延迟, 无音)
                out.append(f'setblock {x} {Y+1} {sz} air')
        x += 1
    return out, x

DP = os.path.join(HERE, 'build', f'{NS}_sync')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 同步真音符盒(共享中继器骨架, tick80)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

build = ['gamerule commandModificationBlockLimit 2147483647']
endx = OX
for L in range(NLANES):
    cmds, ex = lane_spine(L * LANE_DZ, lane_at[L]); build += cmds; endx = max(endx, ex)
PBX = OX - 3
build += [f'setblock {PBX} {Y-1} {OZ} minecraft:stone',
          f'setblock {PBX} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"function {NS}:play",auto:0b}}',
          f'setblock {PBX} {Y+1} {OZ} minecraft:stone_button[face=floor]']
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]
LEN = endx - OX
WX0, WZ0, WX1, WZ1 = OX - 6, OZ - 2, endx + 2, OZ + (NLANES - 1) * LANE_DZ + 2

zc = (WZ1 // 16) - (WZ0 // 16) + 1
xstep = max(1, 240 // zc)
flbuild, cx = [], WX0
while cx <= WX1:
    cxe = min(WX1, cx + xstep * 16 - 1)
    flbuild.append(f'forceload add {cx} {WZ0} {cxe} {WZ1}'); cx = cxe + 1

src_pts = [(OX - 1, OZ + L * LANE_DZ) for L in range(NLANES)]
TRIG_CLEAR = [f'setblock {sx} {Y} {sz} minecraft:air' for sx, sz in src_pts]
SCHED_CLEAR = [f'schedule clear {NS}:{f}' for f in ('done', 'fire', 'firestop', 'startbuild')]
END_TICKS = (MAXTICK + OFFSET) * 2 + 200

wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1',
            f'scoreboard players set CLR {NS} -1', f'scoreboard players set PLAY {NS} 0', 'forceload remove all']
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] 我落泪 同步真音符盒 loaded. ","color":"aqua"}},{{"text":"需mod+资源包. 曲速80 -> /function {NS}:setup"}}]'])
wf('setup', [f'scoreboard players set PLAY {NS} 0', 'stopsound @a master', f'scoreboard players set CLR {NS} -1']
   + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t',
      f'tellraw @a "[{NS}] reset + forceloading; building... (等 BUILT)"'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building ({NLANES} lanes x {NCELLS} 格 = 全同步骨架)..."')
wf('tick', f'execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n'
           f'execute if score CLR {NS} matches 0.. run function {NS}:clearstep')
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('buildstep', bs)
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
wf('builddone', f'scoreboard players set BLD {NS} -1\n'
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"确保曲速80, 按钮/ /function {NS}:play"}}]')
wf('play', [f'execute if score PLAY {NS} matches 1 run return 0', f'scoreboard players set PLAY {NS} 1', 'stopsound @a master']
   + TRIG_CLEAR + [f'schedule function {NS}:fire 2t', f'tellraw @a "[{NS}] GO. 发声列灯成竖排同时亮=已同步。"'])
wf('fire', flbuild + [f'setblock {sx} {Y} {sz} minecraft:redstone_block' for sx, sz in src_pts]
   + [f'schedule function {NS}:firestop {PULSE}t', f'schedule function {NS}:done {END_TICKS}t'])
wf('firestop', TRIG_CLEAR)
wf('done', f'scoreboard players set PLAY {NS} 0\nforceload remove all\n'
   f'tellraw @a "[{NS}] (end) replay: /function {NS}:setup; cleanup: /function {NS}:cleanup."')
SEG = 200
clr_segs = (LEN + 12) // SEG + 1
for k in range(clr_segs):
    fx0 = OX - 6 + k * SEG; fx1 = min(endx + 2, fx0 + SEG - 1)
    wf(f'clr/c{k}', f'fill {fx0} {Y-2} {WZ0} {fx1} {Y+3} {WZ1} air')
wf('cleardone', [f'scoreboard players set CLR {NS} -1', 'forceload remove all', f'tellraw @a "[{NS}] cleaned up."'])
cs = [f'execute if score CLR {NS} matches {k} run function {NS}:clr/c{k}' for k in range(clr_segs)]
cs += [f'execute if score CLR {NS} matches {clr_segs} run function {NS}:cleardone',
       f'execute if score CLR {NS} matches 0..{clr_segs} run scoreboard players add CLR {NS} 1']
wf('clearstep', cs)
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647', f'scoreboard players set PLAY {NS} 0',
               'stopsound @a master', f'scoreboard players set BLD {NS} -1'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'scoreboard players set CLR {NS} 0', f'tellraw @a "[{NS}] tearing down..."'])

dst = os.path.join(WORLD_DP, f'{NS}_sync')
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
notecount = sum(len(d) for d in lane_at)
nrep = sum(1 for k, _ in cells if k == 'rep'); ncond = sum(1 for k, _ in cells if k == 'trig')
print('=== 24 同步真音符盒(共享中继器骨架) ===')
print(f'曲子={NOTES} 音符={notecount} dropped={dropped} 钳音={clamped[0]} lanes={NLANES} OFFSET={OFFSET}刻')
print(f'共享骨架: {NCELLS}格 = {nrep}中继器 + {ncond}发声列(=触发刻并集). 7 lane 全同骨架 -> 绝对同步 + 音符列对齐')
print(f'机器: {LEN}长 x {(NLANES-1)*LANE_DZ+1}宽 (~{LEN//16}x{((NLANES-1)*LANE_DZ)//16+1}区块)  批次={len(batches)}')
print(f'对比 23密集: 各 lane 长度不一(3917..1764)岔开 -> 本版 7 lane 全 {LEN} 对齐同步')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> /function {NS}:play')
