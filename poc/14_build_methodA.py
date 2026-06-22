# -*- coding: utf-8 -*-
"""14_build_methodA.py — 方案A: 高 tick rate + delay-1 均匀细格红石机器(全曲)。

复用 06 的 N 并行脊柱架构, 但 delay-1(2游戏刻)+ tick rate 80 -> 每格 0.025s(6ms 误差,忠实)。
真红石: 一条 6t? 不, PULSE=4t 瞬时脉冲沿每条 lane 跑, 到命令方块就 playsound。
⚠ tick rate 命令在函数里加载失败 -> 不写进函数, play 里提醒手动 /tick rate 80。
代价: 机器约 2*MAXCELL ≈ 22000 方块长(细格 = 9x 现机器)。这是"忠实度 vs 长度"的直接路线。

Run(base python, 读 notes.json + manifest): python 14_build_methodA.py
"""
import os, sys, json, math, shutil
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = sys.argv[1] if len(sys.argv) > 1 else 'notes.json'   # 任意曲子的 notes.json
NS = sys.argv[2] if len(sys.argv) > 2 else 'qzpa'
OX = int(sys.argv[3]) if len(sys.argv) > 3 else 30000        # 不同曲子用不同 OX 防重叠
OZ = 0
Y, DELAY, LANE_DZ = -59, 1, 4      # ← delay-1
BASE, RFACING, BATCH = 'white_wool', 'west', 2000
MAXLANES, VEL_FLOOR = 7, 0.04
TPS = 80                           # ← 手动 /tick rate 80
PULSE = 4                          # 脉冲宽(游戏刻); delay-1 用 4t(=2红石刻)
U = 2 * DELAY / TPS                # 每格 = 2/80 = 0.025s

notes = json.load(open(os.path.join(HERE, NOTES), encoding='utf-8'))['notes']
man = json.load(open(os.path.join(HERE, 'samples_manifest_piano.json'), encoding='utf-8'))
samples = man['samples']; bands = sorted(set(s['base_midi'] for s in samples))
bl = {(s['base_midi'], s['vlayer']): s['id'] for s in samples}
def layer_of(v): return 'p' if v < 0.40 else ('mf' if v < 0.72 else 'f')
def map_note(m, v):
    base = min(bands, key=lambda b: abs(b - m))
    return bl[(base, layer_of(v))], round(max(0.5, min(2.0, 2 ** ((m - base) / 12.0))), 5)

bycell = defaultdict(list)
for n in notes:
    if n['vel'] >= VEL_FLOOR: bycell[round(n['t'] / U)].append(n)
lane_notes = [dict() for _ in range(MAXLANES)]
dropped = 0
for c, grp in bycell.items():
    for i, n in enumerate(sorted(grp, key=lambda x: -x['midi'])):
        if i >= MAXLANES: dropped += 1; continue
        eid, pitch = map_note(n['midi'], n['vel'])
        lane_notes[i][c] = (eid, pitch, round(0.6 + 0.4 * min(1.0, n['vel']), 3))
NLANES = max((L + 1 for L in range(MAXLANES) if lane_notes[L]), default=1)
MAXCELL = max(bycell)

DP = os.path.join(HERE, 'build', f'{NS}_redstone')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 晴天 方案A delay-1 fine-grid (tick80, 0.025s)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

def box(a0, a1, r0, r1): return OX + a0, OZ + r0, OX + a1, OZ + r1
def spine(r, lane):
    sx, sz = OX - 1, OZ + r
    out = [f'setblock {sx} {Y-1} {sz} minecraft:{BASE}']
    for c in range(MAXCELL + 1):
        cx = OX + 2 * c
        if c > 0:
            rx = OX + 2 * c - 1
            out.append(f'setblock {rx} {Y-1} {sz} minecraft:{BASE}')
            out.append(f'setblock {rx} {Y} {sz} minecraft:repeater[facing={RFACING},delay={DELAY}]')
        if c in lane:
            eid, pitch, vol = lane[c]
            cmd = f'execute as @a at @s run playsound {NS_SND}:{eid} master @s ~ ~ ~ {vol} {pitch} 1'
            out.append(f'setblock {cx} {Y-1} {sz} minecraft:command_block[facing=down,conditional=false]{{Command:"{cmd}",auto:0b}}')
        else:
            out.append(f'setblock {cx} {Y-1} {sz} minecraft:{BASE}')
        out.append(f'setblock {cx} {Y} {sz} minecraft:redstone_wire')
    return out
NS_SND = 'qzpno'                    # 复用现有钢琴资源包

A0, A1 = -7, 2 * MAXCELL + 3
R0, R1 = -3, (NLANES - 1) * LANE_DZ + 2
PBX = OX - 3
build = ['gamerule commandModificationBlockLimit 2147483647']
for L in range(NLANES): build += spine(L * LANE_DZ, lane_notes[L])
build += [f'setblock {PBX} {Y-1} {OZ} minecraft:stone',
          f'setblock {PBX} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"function {NS}:play",auto:0b}}',
          f'setblock {PBX} {Y+1} {OZ} minecraft:stone_button[face=floor]']
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]

WX0, WZ0, WX1, WZ1 = box(A0, A1, R0, R1)
zc = (WZ1 // 16) - (WZ0 // 16) + 1
xstep = max(1, 240 // zc)
flbuild, cx = [], WX0
while cx <= WX1:
    cxe = min(WX1, cx + xstep * 16 - 1)
    flbuild.append(f'forceload add {cx} {WZ0} {cxe} {WZ1}'); cx = cxe + 1

src_pts = [(OX - 1, OZ + L * LANE_DZ) for L in range(NLANES)]
TRIG_CLEAR = [f'setblock {sx} {Y} {sz} minecraft:air' for sx, sz in src_pts]
SCHED_CLEAR = [f'schedule clear {NS}:{f}' for f in ('done', 'fire', 'firestop', 'startbuild')]
END_TICKS = MAXCELL * DELAY * 2 + 200

wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1',
            f'scoreboard players set CLR {NS} -1', f'scoreboard players set PLAY {NS} 0', 'forceload remove all']
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] 晴天 方案A(delay-1 细格) loaded. ","color":"aqua"}},{{"text":"先 /tick rate 80, 再 /function {NS}:setup"}}]'])
wf('setup', [f'scoreboard players set PLAY {NS} 0', 'stopsound @a master', f'scoreboard players set CLR {NS} -1']
   + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t',
      f'tellraw @a "[{NS}] reset + forceloading; building... (机器超长, 等 BUILT)"'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building ({NLANES} lanes, 超长)..."')
wf('tick', f'execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n'
           f'execute if score CLR {NS} matches 0.. run function {NS}:clearstep')
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('buildstep', bs)
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
wf('builddone', f'scoreboard players set BLD {NS} -1\n'
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"确保 /tick rate 80, 再按钮/ /function {NS}:play"}}]')
wf('play', [f'execute if score PLAY {NS} matches 1 run return 0', f'scoreboard players set PLAY {NS} 1', 'stopsound @a master']
   + TRIG_CLEAR + [f'schedule function {NS}:fire 2t',
                   f'tellraw @a "[{NS}] GO (方案A). 若曲速不对=tick rate 不是 80。"'])
wf('fire', flbuild + [f'setblock {sx} {Y} {sz} minecraft:redstone_block' for sx, sz in src_pts]
   + [f'schedule function {NS}:firestop {PULSE}t', f'schedule function {NS}:done {END_TICKS}t'])
wf('firestop', TRIG_CLEAR)
wf('done', f'scoreboard players set PLAY {NS} 0\nforceload remove all\n'
   f'tellraw @a "[{NS}] (end) replay: /function {NS}:setup; cleanup: /function {NS}:cleanup."')
SEG = 256
clr_segs = (A1 - A0) // SEG + 1
for k in range(clr_segs):
    a0 = A0 + k * SEG; a1 = min(A1, a0 + SEG - 1)
    fx0, fz0, fx1, fz1 = box(a0, a1, R0, R1)
    wf(f'clr/c{k}', f'fill {fx0} {Y-2} {fz0} {fx1} {Y+6} {fz1} air')
wf('cleardone', [f'scoreboard players set CLR {NS} -1', 'forceload remove all', f'tellraw @a "[{NS}] cleaned up."'])
cs = [f'execute if score CLR {NS} matches {k} run function {NS}:clr/c{k}' for k in range(clr_segs)]
cs += [f'execute if score CLR {NS} matches {clr_segs} run function {NS}:cleardone',
       f'execute if score CLR {NS} matches 0..{clr_segs} run scoreboard players add CLR {NS} 1']
wf('clearstep', cs)
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647', f'scoreboard players set PLAY {NS} 0',
               'stopsound @a master', f'scoreboard players set BLD {NS} -1'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'scoreboard players set CLR {NS} 0', f'tellraw @a "[{NS}] tearing down..."'])

WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"
dst = os.path.join(WORLD_DP, f'{NS}_redstone')
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 14 方案A (delay-1, tick80, 0.025s) ===')
print(f'notes={sum(len(v) for v in lane_notes)} dropped={dropped} lanes={NLANES} MAXCELL={MAXCELL}')
print(f'机器: {2*MAXCELL} 长 x {R1-R0} 宽 (~{2*MAXCELL//16}x{(R1-R0)//16+1} 区块)  建造批次={len(batches)} 脉冲={PULSE}t forceload命令={len(flbuild)}')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> /function {NS}:play')
