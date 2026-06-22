# -*- coding: utf-8 -*-
"""15_build_methodB.py — 方案B: 变延迟链红石机器(全曲, 高效)。

和 A 同样 0.025s 分辨率(tick80)、同样忠实(6ms),但**变延迟格**压缩空白:
  - 仍是 06 的 7 并行同步 lane + repeater→dust→命令方块(验证过的脉冲机制, 低风险);
  - 但每格的 repeater 延迟可变 1–4(红石刻):两个相邻"有音刻"之间用 delay-4 快走、
    最后一格用余数 delay 精确落到目标刻 → 空段被 4x 压缩。
  - 累计延迟到每个有音格 = 该音的 tick(rt),所以发声时刻忠实到 1rt=0.025s。
长度约 A 的 1/3(~7800 vs 22032 方块)。真红石、脉冲行进触发,不违反原则。
⚠ tick rate 命令在函数里加载失败 -> play 里提醒手动 /tick rate 80。

Run(base python): python 15_build_methodB.py
"""
import os, sys, json, shutil
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = sys.argv[1] if len(sys.argv) > 1 else 'notes.json'   # 任意曲子
NS = sys.argv[2] if len(sys.argv) > 2 else 'qzpb'
OX = int(sys.argv[3]) if len(sys.argv) > 3 else 40000
NS_SND = 'qzpno'
OZ = 0
Y, LANE_DZ = -59, 4
BASE, RFACING, BATCH = 'white_wool', 'west', 2000
MAXLANES, VEL_FLOOR = 7, 0.04
TPS = 80
PULSE = 4
U = 2 / TPS                        # 0.025s = 1 红石刻

notes = json.load(open(os.path.join(HERE, NOTES), encoding='utf-8'))['notes']
man = json.load(open(os.path.join(HERE, 'samples_manifest_piano.json'), encoding='utf-8'))
samples = man['samples']; bands = sorted(set(s['base_midi'] for s in samples))
bl = {(s['base_midi'], s['vlayer']): s['id'] for s in samples}
def layer_of(v): return 'p' if v < 0.40 else ('mf' if v < 0.72 else 'f')
def map_note(m, v):
    base = min(bands, key=lambda b: abs(b - m))
    return bl[(base, layer_of(v))], round(max(0.5, min(2.0, 2 ** ((m - base) / 12.0))), 5)

# 量化到 1rt 格 + 7-lane 分配
bycell = defaultdict(list)
for n in notes:
    if n['vel'] >= VEL_FLOOR: bycell[round(n['t'] / U)].append(n)
lane_at = [defaultdict(dict) for _ in range(MAXLANES)]   # lane_at[L] = {tick:(eid,pitch,vol)}
dropped = 0
for tick, grp in bycell.items():
    for i, n in enumerate(sorted(grp, key=lambda x: -x['midi'])):
        if i >= MAXLANES: dropped += 1; continue
        eid, pitch = map_note(n['midi'], n['vel'])
        lane_at[i][tick] = (eid, pitch, round(0.6 + 0.4 * min(1.0, n['vel']), 3))
NLANES = max((L + 1 for L in range(MAXLANES) if lane_at[L]), default=1)
trig_ticks = sorted(bycell)
MAXTICK = trig_ticks[-1]

# 变延迟格序列: 每个 gap 用 (G-1)//4 个 delay-4 + 1 个 delay=余数 的触发格
cells = []   # (delay, trig_tick_or_None)
cum = 0
for T in trig_ticks:
    G = T - cum
    if G <= 0:  # 同刻重复(不应发生,distinct), 跳过
        continue
    nfill = (G - 1) // 4
    for _ in range(nfill):
        cells.append((4, None)); cum += 4
    tdelay = G - 4 * nfill          # 1..4
    cells.append((tdelay, T)); cum += tdelay
NCELLS = len(cells)
assert cum == MAXTICK, f"cum {cum} != MAXTICK {MAXTICK}"

DP = os.path.join(HERE, 'build', f'{NS}_redstone')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 晴天 方案B 变延迟链 (tick80, 0.025s, 高效)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

def box(a0, a1, r0, r1): return OX + a0, OZ + r0, OX + a1, OZ + r1
def spine(lane_z, notes_at):
    sz = OZ + lane_z
    out = [f'setblock {OX-1} {Y-1} {sz} minecraft:{BASE}']    # source 支撑
    for k, (d, trig) in enumerate(cells):
        rx = OX + 2 * k; dx = OX + 2 * k + 1
        out.append(f'setblock {rx} {Y-1} {sz} minecraft:{BASE}')
        out.append(f'setblock {rx} {Y} {sz} minecraft:repeater[facing={RFACING},delay={d}]')
        if trig is not None and trig in notes_at:
            eid, pitch, vol = notes_at[trig]
            cmd = f'execute as @a at @s run playsound {NS_SND}:{eid} master @s ~ ~ ~ {vol} {pitch} 1'
            out.append(f'setblock {dx} {Y-1} {sz} minecraft:command_block[facing=down,conditional=false]{{Command:"{cmd}",auto:0b}}')
        else:
            out.append(f'setblock {dx} {Y-1} {sz} minecraft:{BASE}')
        out.append(f'setblock {dx} {Y} {sz} minecraft:redstone_wire')
    return out

A0, A1 = -7, 2 * NCELLS + 3
R0, R1 = -3, (NLANES - 1) * LANE_DZ + 2
PBX = OX - 3
build = ['gamerule commandModificationBlockLimit 2147483647']
for L in range(NLANES): build += spine(L * LANE_DZ, lane_at[L])
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
END_TICKS = MAXTICK * 2 + 200

wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1',
            f'scoreboard players set CLR {NS} -1', f'scoreboard players set PLAY {NS} 0', 'forceload remove all']
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] 晴天 方案B(变延迟链) loaded. ","color":"aqua"}},{{"text":"先把曲速调到 80, 再 /function {NS}:setup"}}]'])
wf('setup', [f'scoreboard players set PLAY {NS} 0', 'stopsound @a master', f'scoreboard players set CLR {NS} -1']
   + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t',
      f'tellraw @a "[{NS}] reset + forceloading; building... (等 BUILT)"'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building ({NLANES} lanes)..."')
wf('tick', f'execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n'
           f'execute if score CLR {NS} matches 0.. run function {NS}:clearstep')
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('buildstep', bs)
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
wf('builddone', f'scoreboard players set BLD {NS} -1\n'
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"确保曲速 80, 再按钮/ /function {NS}:play"}}]')
wf('play', [f'execute if score PLAY {NS} matches 1 run return 0', f'scoreboard players set PLAY {NS} 1', 'stopsound @a master']
   + TRIG_CLEAR + [f'schedule function {NS}:fire 2t', f'tellraw @a "[{NS}] GO (方案B)."'])
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
print('=== 15 方案B (变延迟链, tick80, 0.025s) ===')
print(f'notes={sum(len(v) for v in lane_at)} dropped={dropped} lanes={NLANES} 有音刻={len(trig_ticks)} MAXTICK={MAXTICK}')
print(f'格数={NCELLS} (其中触发格={len(trig_ticks)}, 延迟格={NCELLS-len(trig_ticks)})')
print(f'机器: {2*NCELLS} 长 x {R1-R0} 宽 (~{2*NCELLS//16}x{(R1-R0)//16+1} 区块)  批次={len(batches)} forceload={len(flbuild)}')
print(f'对比 A: A={2*MAXTICK}长, B={2*NCELLS}长 (B 是 A 的 {100*NCELLS/MAXTICK:.0f}%)')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> /function {NS}:play')
