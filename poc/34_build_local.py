# -*- coding: utf-8 -*-
"""34_build_local.py — 我泪【完全本地·红石循环播放器】(第三种形式)。

定位(用户): 不做"几千格长条一次性触发", 而是一台【紧凑·本地·可循环】的红石播放器:
  - 紧凑/本地: 复用 31 的平面蛇形折叠(红石粉0延迟U弯) + 双轨辐射 -> X 长仅 ROWLEN, 摆在出生点附近。
  - 红石主动控制节奏型: 乐曲的每一拍/每个音 100% 由红石扫描脉冲触发(与大机器同核, 模组发声)。
  - 循环(本地 jukebox): [循环播放] 让它放完自动再放(done 检 LOOP 分 -> 重新点火), [停止]停。
    (纯红石自循环时钟的最小机构见 35_build_looptest.py=qzlp 已单独验证: 出口->二极管->绕回源->重注入。
     整机这条反馈环走线在双轨折叠上易与U弯红石粉串接, 故整机循环用 1 行数据包重火[与大机器点火同理]稳妥;
     纯红石环已在 qzlp 证可行, 后续可整合。)
  - 节奏完美: 复用 24/30/31 的共享骨架 + 时序断言(累计延迟==该刻), 折叠0延迟 -> 一个数不差。
需 RedPiano 模组 + qzpno 资源包。Run: python 34_build_local.py [notes.json] [NS] [OX] [ROWLEN]
"""
import os, sys, json, shutil
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES  = sys.argv[1] if len(sys.argv) > 1 else 'notes_wll.json'
NS     = sys.argv[2] if len(sys.argv) > 2 else 'wllj'
OX     = int(sys.argv[3]) if len(sys.argv) > 3 else 300         # 出生点附近(本地)
ROWLEN = int(sys.argv[4]) if len(sys.argv) > 4 else 160
OZ, Y = 0, 255
ROW_DZ = 6
RFACE = {1: 'west', -1: 'east'}
LAMP, PASS, BATCH = 'minecraft:redstone_lamp', 'minecraft:stone', 2000
VOICES, TPS, PULSE = 6, 80, 4
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
    if n['vel'] >= 0.04: bycell[round(n['t'] / U)].append(n)
trackvoice = [[dict(), dict(), dict()], [dict(), dict(), dict()]]
dropped = 0
for tick, grp in bycell.items():
    g = sorted(grp, key=lambda x: -x['midi'])
    for i, n in enumerate(g[:VOICES]):
        trackvoice[i // 3][i % 3][tick] = map_note(n['midi'], n['vel'])
    dropped += max(0, len(g) - VOICES)

trig = sorted(bycell); MAXTICK = trig[-1]
OFFSET = 1 if trig[0] == 0 else 0
cells = []; prev = 0
for T0 in trig:
    T = T0 + OFFSET; G = T - prev
    reps = [4] * (G // 4) + ([G % 4] if G % 4 else [])
    if not reps: reps = [1]
    for d in reps: cells.append(('rep', d))
    cells.append(('trig', T0))
    prev = T
NCELLS = len(cells)
cum = 0
for kind, v in cells:
    if kind == 'rep': cum += v
    else: assert cum == v + OFFSET, f"时序错位 @tick {v}: cum={cum} != {v+OFFSET}"

# 折叠布局(同 31)
pos = [None] * NCELLS; legs = []
x, z, d, col = 0, 0, 1, 0
for i in range(NCELLS):
    pos[i] = (x, z, d); x += d; col += 1
    last = (i == NCELLS - 1)
    if (not last) and col >= ROWLEN and cells[i + 1][0] == 'rep':
        legs.append((x, z, z + ROW_DZ)); z += ROW_DZ; d = -d; x += d; col = 0
NROWS = len(legs) + 1
MAXZOFF = max([zt for (_, _, zt) in legs] + [zo + 1 for (_, zo, _) in pos])
SLAB_SEP = MAXZOFF + 6
TRACK_Z = [OZ, OZ + SLAB_SEP]
LEN_X = ROWLEN + 1

occ = {}
def put(out, x, y, zz, blk):
    key = (x, y, zz)
    if key in occ and occ[key] != blk and not (occ[key] == 'air' or blk == 'air'):
        raise AssertionError(f"碰撞 @{key}: {occ[key]} vs {blk}")
    occ[key] = blk
    out.append(f'setblock {x} {y} {zz} {blk}')

def emit_track(t, toz):
    out = [f'setblock {OX-1} {Y-1} {toz} {PASS}']
    for i, (xo, zo, dirx) in enumerate(pos):
        X, Z = OX + xo, toz + zo
        kind, v = cells[i]
        if kind == 'rep':
            put(out, X, Y - 1, Z, LAMP); put(out, X, Y, Z, f'minecraft:repeater[facing={RFACE[dirx]},delay={v}]')
        else:
            above = trackvoice[t][0].get(v); pz = trackvoice[t][1].get(v); mz = trackvoice[t][2].get(v)
            put(out, X, Y - 1, Z, LAMP); put(out, X, Y, Z, above[0] if above else PASS)
            if above:
                put(out, X, Y + 1, Z, f'minecraft:note_block[note={above[1]}]'); put(out, X, Y + 2, Z, 'air')
            if pz:
                put(out, X, Y - 1, Z + 1, pz[0]); put(out, X, Y, Z + 1, f'minecraft:note_block[note={pz[1]}]'); put(out, X, Y + 1, Z + 1, 'air')
            if mz:
                put(out, X, Y - 1, Z - 1, mz[0]); put(out, X, Y, Z - 1, f'minecraft:note_block[note={mz[1]}]'); put(out, X, Y + 1, Z - 1, 'air')
    for (xleg, zf, zt) in legs:
        for zz in range(zf, zt + 1):
            put(out, OX + xleg, Y - 1, toz + zz, PASS); put(out, OX + xleg, Y, toz + zz, 'minecraft:redstone_wire')
    return out

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 我泪 本地红石循环播放器(折叠双轨, tick80)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

build = ['gamerule commandModificationBlockLimit 2147483647']
for t in range(2): build += emit_track(t, TRACK_Z[t])
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]

allx = [k[0] for k in occ]; allz = [k[2] for k in occ]
WX0, WZ0, WX1, WZ1 = min(allx) - 2, min(allz) - 2, max(allx) + 2, max(allz) + 2
zc = (WZ1 // 16) - (WZ0 // 16) + 1
xstep = max(1, 240 // max(1, zc))
flbuild, cx = [], WX0
while cx <= WX1:
    cxe = min(WX1, cx + xstep * 16 - 1)
    flbuild.append(f'forceload add {cx} {WZ0} {cxe} {WZ1}'); cx = cxe + 1

src_pts = [(OX - 1, tz) for tz in TRACK_Z]
TRIG_CLEAR = [f'setblock {sx} {Y} {sz} minecraft:air' for sx, sz in src_pts]
SCHED_CLEAR = [f'schedule clear {NS}:{f}' for f in ('done', 'fire', 'firestop', 'startbuild')]
MUSIC_TICKS = (MAXTICK + OFFSET) * 2
END_TICKS = MUSIC_TICKS + 60
PBX = OX - 3
CAMX, CAMZ = OX + ROWLEN // 2, (TRACK_Z[0] + TRACK_Z[1]) // 2

def labeled_button(bx, cmd, lines):
    msgs = ','.join('\'{"text":"%s"}\'' % s for s in (list(lines) + ['', '', '', ''])[:4])
    return [f'setblock {bx} {Y-1} {OZ} {LAMP}',
            f'setblock {bx} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"{cmd}",auto:0b}}',
            f'setblock {bx} {Y+1} {OZ} minecraft:stone_button[face=floor]',
            f'setblock {bx} {Y-1} {OZ-2} {LAMP}',
            'setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}' % (bx, Y, OZ - 2, msgs)]
ctl = []
ctl += labeled_button(PBX,   f'function {NS}:play',     ['[播放]', '放一遍', '红石扫描'])
ctl += labeled_button(PBX-2, f'function {NS}:loop',     ['[循环播放]', '本地jukebox', '放完自动重放'])
ctl += labeled_button(PBX-4, f'function {NS}:stop',     ['[停止]', '停+不再循环'])
ctl += labeled_button(PBX-6, f'function {NS}:view',     ['[全景俯视]', '看紧凑方阵'])

RESET = [f'scoreboard players set PLAY {NS} 0', f'scoreboard players set LOOP {NS} 0']
wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1',
            f'scoreboard players set CLR {NS} -1'] + RESET + ['forceload remove all',
            'scoreboard objectives add rpcfg dummy', 'scoreboard players set poly rpcfg 1', 'scoreboard players set human rpcfg 1']
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] 我泪 本地红石循环播放器 loaded. ","color":"aqua"}},{{"text":"需RedPiano模组+qzpno包. /tick rate 80 -> /function {NS}:setup"}}]'])
wf('setup', RESET + ['gamemode creative @a', 'stopsound @a master', f'scoreboard players set CLR {NS} -1']
   + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t',
      f'tellraw @a "[{NS}] reset + forceloading; building... (等 BUILT)"'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building (折叠双轨 {NCELLS}格 {NROWS}行)..."')
wf('tick', f'execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n'
           f'execute if score CLR {NS} matches 0.. run function {NS}:clearstep')
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('buildstep', bs)
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
ctlfn = ['gamerule commandModificationBlockLimit 2147483647'] + ctl
wf('placectl', ctlfn)
wf('builddone', f'scoreboard players set BLD {NS} -1\nfunction {NS}:placectl\n'
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"本地播放器 X长~{LEN_X}格. 按[播放]/[循环播放]/[停止]"}}]')
# 点火核心(纯红石扫描) + 数据包循环
wf('playcore', [f'scoreboard players set PLAY {NS} 1', 'stopsound @a master'] + TRIG_CLEAR + [f'schedule function {NS}:fire 2t'])
wf('fire', flbuild + [f'setblock {sx} {Y} {sz} minecraft:redstone_block' for sx, sz in src_pts]
   + [f'schedule function {NS}:firestop {PULSE}t', f'schedule function {NS}:done {END_TICKS}t'])
wf('firestop', TRIG_CLEAR)
wf('done', [f'execute if score LOOP {NS} matches 1 run function {NS}:playcore',                # 循环=重火(本地jukebox)
            f'execute if score LOOP {NS} matches 0 run scoreboard players set PLAY {NS} 0',
            f'execute if score LOOP {NS} matches 0 run tellraw @a "[{NS}] (一遍结束) 再按[播放]/[循环播放]。"'])
wf('play', [f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先按[停止]"',
            f'scoreboard players set LOOP {NS} 0', f'function {NS}:playcore',
            f'tellraw @a "[{NS}] 播放一遍。站着即可听(声音绑你本人)。红石扫描脉冲驱动节奏。"'])
wf('loop', [f'execute if score PLAY {NS} matches 1 run scoreboard players set LOOP {NS} 1',
            f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 已转为循环。"',
            f'scoreboard players set LOOP {NS} 1', f'function {NS}:playcore',
            f'tellraw @a "[{NS}] 循环播放(本地jukebox): 放完自动重放, 直到按[停止]。"'])
wf('stop', RESET + ['gamemode creative @a', 'stopsound @a master'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'tp @a {PBX} {Y+3} {OZ}', f'tellraw @a "[{NS}] 已停止(并取消循环)。"'])
wf('view', ['gamemode spectator @a', f'tp @a {CAMX} {Y+40} {CAMZ} 0 90',
            f'tellraw @a "[{NS}] 俯视紧凑方阵。再按[播放]听; [停止]退出。"'])
SEG = 200
clr_segs = (max(allx) - WX0 + 16) // SEG + 1
for k in range(clr_segs):
    fx0 = WX0 + k * SEG; fx1 = min(WX1, fx0 + SEG - 1)
    wf(f'clr/c{k}', f'fill {fx0} {Y-2} {WZ0} {fx1} {Y+3} {WZ1} air')
wf('cleardone', [f'scoreboard players set CLR {NS} -1', 'forceload remove all', f'tellraw @a "[{NS}] cleaned up."'])
cs = [f'execute if score CLR {NS} matches {k} run function {NS}:clr/c{k}' for k in range(clr_segs)]
cs += [f'execute if score CLR {NS} matches {clr_segs} run function {NS}:cleardone',
       f'execute if score CLR {NS} matches 0..{clr_segs} run scoreboard players add CLR {NS} 1']
wf('clearstep', cs)
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647'] + RESET + ['gamemode creative @a', 'stopsound @a master',
               f'scoreboard players set BLD {NS} -1'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'scoreboard players set CLR {NS} 0', f'tellraw @a "[{NS}] tearing down..."'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
nrep = sum(1 for k, _ in cells if k == 'rep'); ncond = sum(1 for k, _ in cells if k == 'trig')
nplaced = sum(len(trackvoice[t][p]) for t in range(2) for p in range(3))
print('=== 34 我泪 本地红石循环播放器 ===')
print(f'曲子={NOTES} 发声音={nplaced} dropped={dropped} 钳音={clamped[0]} OFFSET={OFFSET}')
print(f'骨架: {NCELLS}格 = {nrep}中继器 + {ncond}发声列. 折叠 {NROWS}行 x {ROWLEN}, {len(legs)}个红石粉U弯(0延迟)')
print(f'本地播放器: X长~{LEN_X}格 (vs 直链~{NCELLS}); 占地 x[{WX0}..{WX1}] z[{WZ0}..{WZ1}]; 两板 z={TRACK_Z}; 批次={len(batches)}; 无碰撞✓')
print(f'循环周期 = {MUSIC_TICKS} game-tick (~{MUSIC_TICKS/TPS:.0f}s @tick80)')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> [播放]一遍 / [循环播放]jukebox / [停止]')
