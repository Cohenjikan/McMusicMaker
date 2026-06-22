# -*- coding: utf-8 -*-
"""23_build_dense.py — 密集真音符盒机器(中继器链直连 + 音符盒坐在链上导体块, 紧凑)。

对比 21(松散): 21 每格=中继器(rx)+红石线(dx) 2格 + 分接3排 -> 5980长x31宽。
本版(密集): 一条纯中继器链(1格/中继器), 发声格=导体映射方块(被前中继器强充能),
  音符盒直接坐其上(上方空气), 空白只用中继器。-> 约半长、只1排/lane(窄很多)。
  每音 = ceil(gap/4) 个中继器 + 1 个发声格。
时序: tick80 + 链上中继器累计延迟=该音绝对刻(忠实)。强充能=原版中继器对前方块, 必触发上方音符盒。

需 RedPiano 模组 + qzpno 资源包。Run: python 23_build_dense.py [notes_wll.json] [NS] [OX]
"""
import os, sys, json, shutil
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = sys.argv[1] if len(sys.argv) > 1 else 'notes_wll.json'
NS = sys.argv[2] if len(sys.argv) > 2 else 'qzwd'
OX = int(sys.argv[3]) if len(sys.argv) > 3 else 160000
OZ = 0
Y, LANE_DZ = 255, 2            # 天上; lane 只占1排, 间隔2(留1空)
LAMP, RFACING, BATCH = 'redstone_lamp', 'west', 2000   # 导体块下垫红石灯(发声时亮=进度)
MAXLANES, VEL_FLOOR = 7, 0.04
TPS, PULSE = 80, 4
U = 2 / TPS
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

def lane_chain(lane_z, notes_at):
    """一条 lane 的中继器链 + 发声格。返回 (setblock列表, 末端X)。"""
    sz = OZ + lane_z
    out = [f'setblock {OX-1} {Y-1} {sz} minecraft:stone']     # 源支撑
    x, prev = OX, 0
    for T in sorted(notes_at):
        G = T - prev
        reps = [4] * (G // 4) + ([G % 4] if G % 4 else [])
        if not reps: reps = [1]                              # 防发声格直连源(弱充能不触发); +1刻全局偏移
        for d in reps:
            out.append(f'setblock {x} {Y-1} {sz} minecraft:stone')
            out.append(f'setblock {x} {Y} {sz} minecraft:repeater[facing={RFACING},delay={d}]')
            x += 1
        block, nv = notes_at[T]
        out.append(f'setblock {x} {Y-1} {sz} minecraft:{LAMP}')                       # 灯(发声时亮)
        out.append(f'setblock {x} {Y} {sz} {block}')                                  # 导体映射方块(被前中继器强充能)
        out.append(f'setblock {x} {Y+1} {sz} minecraft:note_block[note={nv}]')        # 音符盒
        out.append(f'setblock {x} {Y+2} {sz} air')                                    # 上方空气
        x += 1
        prev = T
    return out, x

DP = os.path.join(HERE, 'build', f'{NS}_dense')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 密集真音符盒(中继器链, tick80)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

build = ['gamerule commandModificationBlockLimit 2147483647']
endx = OX
for L in range(NLANES):
    cmds, ex = lane_chain(L * LANE_DZ, lane_at[L]); build += cmds; endx = max(endx, ex)
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
MAXTICK = max((max(d) for d in lane_at if d), default=1)
END_TICKS = MAXTICK * 2 + 200

wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1',
            f'scoreboard players set CLR {NS} -1', f'scoreboard players set PLAY {NS} 0', 'forceload remove all']
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] 我落泪 密集真音符盒 loaded. ","color":"aqua"}},{{"text":"需mod+资源包. 曲速80 -> /function {NS}:setup"}}]'])
wf('setup', [f'scoreboard players set PLAY {NS} 0', 'stopsound @a master', f'scoreboard players set CLR {NS} -1']
   + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t',
      f'tellraw @a "[{NS}] reset + forceloading; building... (等 BUILT)"'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building ({NLANES} lanes, {LEN}长)..."')
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
   + TRIG_CLEAR + [f'schedule function {NS}:fire 2t', f'tellraw @a "[{NS}] GO. 灯亮=发声位置。"'])
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

dst = os.path.join(WORLD_DP, f'{NS}_dense')
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
notecount = sum(len(d) for d in lane_at)
print('=== 23 密集真音符盒(中继器链) ===')
print(f'曲子={NOTES} 音符={notecount} dropped={dropped} 钳音={clamped[0]} lanes={NLANES}')
print(f'机器: {LEN}长 x {(NLANES-1)*LANE_DZ+1}宽 (~{LEN//16}x{((NLANES-1)*LANE_DZ)//16+1}区块)  每音≈{LEN/max(1,max(len(d) for d in lane_at)):.1f}格  批次={len(batches)}')
print(f'对比 21松散: 5980长x31宽 -> 本版 {LEN}长x{(NLANES-1)*LANE_DZ+1}宽')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> /function {NS}:play')
