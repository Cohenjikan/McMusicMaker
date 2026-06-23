# -*- coding: utf-8 -*-
"""36_build_linecoil.py — Task 2(修正版): 直线机器 + 长休止【Z向折线圈】(节奏100%不变)。

用户澄清: 不是把整机折成 2D 方阵(那是 Task3), 而是【整体保持直线】, 只把【长休止】的延迟
  折成一个 Z 向小线圈藏到主线外, 让主线上音符靠拢 -> 直线更短, 但每个音时值一个不差。
  例: 1---1---1---1----------1  ->  1---1---1---1(---长休止折进Z线圈)1

机制(全部复用已验证件):
  - 短间隔: 中继器直接内联(同 30)。
  - 长休止(rep数 >= COIL_MIN): 折成线圈 = 入口rep -> 红石粉拐角(0延迟) -> OUT列(sdir·Z) ->
    红石粉U弯(0延迟, 32已验) -> BACK列(回) -> 红石粉拐角 -> 出口rep -> 喂下一个音(强充能)。
    OUT/BACK 两列在 X 上隔开一格(中间空), 防入口/出口红石粉粘连短路。线圈只含中继器(=休止延迟),
    拐角/U弯是红石粉(0延迟) -> 线圈总延迟 == 该休止延迟 -> 24/30 时序公式原样成立(断言不变)。
  - 双轨辐射(6声部, 同30): 轨A(z=0)线圈朝 -Z, 轨B(z=4)线圈朝 +Z, 互不碰(碰撞断言兜底)。
停止已修(SIL 持续静默 + stopsound @a; 模组在 RECORDS 类别)。
需 RedPiano 模组 + qzpno 资源包。Run: python 36_build_linecoil.py [notes.json] [NS] [OX] [COIL_MIN]
"""
import os, sys, json, shutil
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = sys.argv[1] if len(sys.argv) > 1 else 'notes_olk.json'
NS = sys.argv[2] if len(sys.argv) > 2 else 'qzolkl'
OX = int(sys.argv[3]) if len(sys.argv) > 3 else 185000
COIL_MIN = int(sys.argv[4]) if len(sys.argv) > 4 else 10   # 休止 rep 数 >= 此值才折线圈(否则内联)
OZ, Y = 0, 255
COILW = 5                              # 线圈占 X 宽(主线推进 5 格代替 N 格)
TRACK = [(0, -1), (4, +1)]            # (基准z, 线圈朝向sdir): 轨A z=0朝-Z, 轨B z=4朝+Z
RFACE = {1: 'west', -1: 'east'}
FZ = {1: 'north', -1: 'south'}        # 输出 +Z=north, -Z=south
LAMP, PASS, BATCH = 'minecraft:redstone_lamp', 'minecraft:stone', 2000
VOICES, TPS, PULSE = 6, 80, 4
U = 2 / TPS
SSTOP = 'stopsound @a'                 # 模组发声在 RECORDS, 不带源才停得掉
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界 (1)/datapacks"

notes = json.load(open(os.path.join(HERE, NOTES), encoding='utf-8'))['notes']
rp = json.load(open(os.path.join(HERE, 'redpiano_map.json'), encoding='utf-8'))
bands = rp['bands']; RPMAP = rp['map']
def layer_of(v): return 'p' if v < 0.40 else ('mf' if v < 0.72 else 'f')
clamped = [0]
def map_note(m, v):
    band = min(bands, key=lambda b: abs(b - m)); nv = max(0, min(24, 12 + (m - band)))
    if not (0 <= 12 + (m - band) <= 24): clamped[0] += 1
    return RPMAP[f'{band}_{layer_of(v)}']['block'], nv

# 量化 + 和弦声部(同 30)
bycell = defaultdict(list)
for n in notes:
    if n['vel'] >= 0.04: bycell[round(n['t'] / U)].append(n)
trackvoice = [[dict(), dict(), dict()], [dict(), dict(), dict()]]
dropped = 0
for tick, grp in bycell.items():
    g = sorted(grp, key=lambda x: -x['midi'])
    for i, n in enumerate(g[:VOICES]): trackvoice[i // 3][i % 3][tick] = map_note(n['midi'], n['vel'])
    dropped += max(0, len(g) - VOICES)

# 共享骨架 cells[](同 24/30)
trig = sorted(bycell); MAXTICK = trig[-1]
OFFSET = 1 if trig[0] == 0 else 0
cells = []; prev = 0
for T0 in trig:
    T = T0 + OFFSET; G = T - prev
    reps = [4] * (G // 4) + ([G % 4] if G % 4 else [])
    if not reps: reps = [1]
    for d in reps: cells.append(('rep', d))
    cells.append(('trig', T0)); prev = T
cum = 0
for kind, v in cells:
    if kind == 'rep': cum += v
    else: assert cum == v + OFFSET, f"时序错位 @tick {v}"

# X-布局: 内联短休止 / 折线圈长休止 / 音符列. 两轨共用(同 X)
actions = []   # ('inline', delays, x) | ('coil', delays, x) | ('trig', tick, x)
mainx, i = OX, 0
ncoil = 0
while i < len(cells):
    if cells[i][0] == 'rep':
        j = i; delays = []
        while j < len(cells) and cells[j][0] == 'rep': delays.append(cells[j][1]); j += 1
        if len(delays) >= COIL_MIN:
            actions.append(('coil', delays, mainx)); mainx += COILW; ncoil += 1
        else:
            actions.append(('inline', delays, mainx)); mainx += len(delays)
        i = j
    else:
        actions.append(('trig', cells[i][1], mainx)); mainx += 1; i += 1
LEN_X = mainx - OX

occ = {}
def put(out, x, y, z, blk):
    k = (x, y, z)
    if k in occ and occ[k] != blk and 'air' not in (occ[k], blk): raise AssertionError(f"碰撞 @{k}: {occ[k]} vs {blk}")
    occ[k] = blk; out.append(f'setblock {x} {y} {z} {blk}')
def rep(out, x, z, face, d): put(out, x, Y-1, z, LAMP); put(out, x, Y, z, f'minecraft:repeater[facing={face},delay={d}]')
def dust(out, x, z): put(out, x, Y-1, z, PASS); put(out, x, Y, z, 'minecraft:redstone_wire')

def emit_coil(out, mx, tz, sdir, delays):
    N = len(delays); K = N - 2; K1 = (K + 1)//2; K2 = K - K1
    rep(out, mx, tz, 'west', delays[0])              # 入口rep
    dust(out, mx + 1, tz)                            # 入口拐角(0延迟)
    di = 1
    for k in range(K1):                              # OUT 列(x=mx+1, 朝 sdir·Z)
        rep(out, mx + 1, tz + (k + 1) * sdir, FZ[sdir], delays[di]); di += 1
    zleg = tz + (K1 + 1) * sdir                      # U弯腿(0延迟红石粉, x=mx+1..mx+3)
    for x in range(mx + 1, mx + 4): dust(out, x, zleg)
    for k in range(K2):                              # BACK 列(x=mx+3, 回 tz)
        rep(out, mx + 3, tz + (K1 - k) * sdir, FZ[-sdir], delays[di]); di += 1
    z = tz + (K1 - K2) * sdir                        # 填红石粉到出口(应对 K1>K2)
    while True:
        dust(out, mx + 3, z)
        if z == tz: break
        z -= sdir
    rep(out, mx + 4, tz, 'west', delays[N - 1])      # 出口rep -> 喂下一音
    assert di == N - 1

def emit_track(t):
    tz, sdir = TRACK[t]
    out = [f'setblock {OX-1} {Y-1} {tz} {PASS}']
    for kind, val, x in actions:
        if kind == 'inline':
            for k, d in enumerate(val): rep(out, x + k, tz, 'west', d)
        elif kind == 'coil':
            emit_coil(out, x, tz, sdir, val)
        else:                                        # trig: 该轨 3 声部辐射和弦(同 30)
            above = trackvoice[t][0].get(val); pz = trackvoice[t][1].get(val); mz = trackvoice[t][2].get(val)
            put(out, x, Y-1, tz, LAMP); put(out, x, Y, tz, above[0] if above else PASS)
            if above: put(out, x, Y+1, tz, f'minecraft:note_block[note={above[1]}]'); put(out, x, Y+2, tz, 'air')
            if pz: put(out, x, Y-1, tz+1, pz[0]); put(out, x, Y, tz+1, f'minecraft:note_block[note={pz[1]}]'); put(out, x, Y+1, tz+1, 'air')
            if mz: put(out, x, Y-1, tz-1, mz[0]); put(out, x, Y, tz-1, f'minecraft:note_block[note={mz[1]}]'); put(out, x, Y+1, tz-1, 'air')
    return out

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 直线+长休止Z线圈(节奏不变, tick80)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

build = ['gamerule commandModificationBlockLimit 2147483647']
for t in range(2): build += emit_track(t)
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]
allx = [k[0] for k in occ]; allz = [k[2] for k in occ]
WX0, WZ0, WX1, WZ1 = min(allx) - 2, min(allz) - 2, max(allx) + 2, max(allz) + 2
zc = (WZ1 // 16) - (WZ0 // 16) + 1; xstep = max(1, 240 // max(1, zc))
flbuild, cx = ['forceload remove all'], WX0
while cx <= WX1:
    cxe = min(WX1, cx + xstep * 16 - 1); flbuild.append(f'forceload add {cx} {WZ0} {cxe} {WZ1}'); cx = cxe + 1
src_pts = [(OX - 1, tz) for tz, _ in TRACK]
TRIG_CLEAR = [f'setblock {sx} {Y} {sz} minecraft:air' for sx, sz in src_pts]
SCHED_CLEAR = [f'schedule clear {NS}:{f}' for f in ('done', 'fire', 'firestop', 'startbuild', 'unsil')]
MUSIC_TICKS = (MAXTICK + OFFSET) * 2; END_TICKS = MUSIC_TICKS + 200
PBX = OX - 3
def lbtn(bx, cmd, lines):
    msgs = ','.join('\'{"text":"%s"}\'' % s for s in (list(lines) + ['', '', ''])[:3])
    return [f'setblock {bx} {Y-1} {OZ} {LAMP}',
            f'setblock {bx} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"{cmd}",auto:0b}}',
            f'setblock {bx} {Y+1} {OZ} minecraft:stone_button[face=floor]',
            f'setblock {bx} {Y-1} {OZ-2} {LAMP}',
            'setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}' % (bx, Y, OZ-2, msgs)]
ctl = ['gamerule commandModificationBlockLimit 2147483647']
ctl += lbtn(PBX, f'function {NS}:play', ['[直接播放]', '站着即可', '听全曲'])
ctl += lbtn(PBX-2, f'function {NS}:stop', ['[停止]', '立即静音'])
RESET = [f'scoreboard players set PLAY {NS} 0', f'scoreboard players set SIL {NS} 0']
wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1', f'scoreboard players set CLR {NS} -1']
   + RESET + ['forceload remove all', 'scoreboard objectives add rpcfg dummy', 'scoreboard players set poly rpcfg 1',
              'scoreboard players set human rpcfg 1'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] OLK 直线+线圈 loaded. ","color":"aqua"}},{{"text":"需模组+qzpno. /tick rate 80 -> /function {NS}:setup"}}]'])
wf('setup', RESET + ['gamemode creative @a', SSTOP, f'scoreboard players set CLR {NS} -1'] + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t', f'tellraw @a "[{NS}] reset+forceload; building..."'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building (直线 {LEN_X}格, {ncoil}个线圈)..."')
wf('tick', f'execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n'
           f'execute if score CLR {NS} matches 0.. run function {NS}:clearstep\n'
           f'execute if score SIL {NS} matches 1 run {SSTOP}')
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('buildstep', bs)
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
wf('placectl', ctl)
wf('builddone', f'scoreboard players set BLD {NS} -1\nfunction {NS}:placectl\n'
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"直线 {LEN_X}格(原~{len(cells)}). 按[直接播放]/[停止]"}}]')
wf('playcore', [f'scoreboard players set PLAY {NS} 1', f'scoreboard players set SIL {NS} 0', SSTOP] + TRIG_CLEAR + [f'schedule function {NS}:fire 2t'])
wf('play', [f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先按[停止]"',
            f'function {NS}:playcore', f'tellraw @a "[{NS}] GO。站着听全曲(声音绑你本人)。直线流光, 长休止处有Z线圈。"'])
wf('stop', RESET + ['gamemode creative @a', SSTOP, f'scoreboard players set SIL {NS} 1',
                    f'schedule function {NS}:unsil {END_TICKS}t'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'tp @a {PBX} {Y+3} {OZ}', f'tellraw @a "[{NS}] 已停止(立即静音)。"'])
wf('unsil', f'scoreboard players set SIL {NS} 0')
wf('fire', flbuild + [f'setblock {sx} {Y} {sz} minecraft:redstone_block' for sx, sz in src_pts]
   + [f'schedule function {NS}:firestop {PULSE}t', f'schedule function {NS}:done {END_TICKS}t'])
wf('firestop', TRIG_CLEAR)
wf('done', RESET + ['gamemode creative @a', f'tellraw @a "[{NS}] (end) 重放[直接播放]; 拆 /function {NS}:cleanup。"'])
SEG = 200; clr_segs = (LEN_X + 16) // SEG + 1
for k in range(clr_segs):
    fx0 = WX0 + k * SEG; fx1 = min(WX1, fx0 + SEG - 1); wf(f'clr/c{k}', f'fill {fx0} {Y-2} {WZ0} {fx1} {Y+3} {WZ1} air')
wf('cleardone', [f'scoreboard players set CLR {NS} -1', 'forceload remove all', f'tellraw @a "[{NS}] cleaned."'])
cs = [f'execute if score CLR {NS} matches {k} run function {NS}:clr/c{k}' for k in range(clr_segs)]
cs += [f'execute if score CLR {NS} matches {clr_segs} run function {NS}:cleardone',
       f'execute if score CLR {NS} matches 0..{clr_segs} run scoreboard players add CLR {NS} 1']
wf('clearstep', cs)
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647'] + RESET + ['gamemode creative @a', SSTOP,
              f'scoreboard players set BLD {NS} -1'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'scoreboard players set CLR {NS} 0', f'tellraw @a "[{NS}] tearing down..."'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
ntrig = sum(1 for a in actions if a[0] == 'trig')
ninline = sum(1 for a in actions if a[0] == 'inline')
nplaced = sum(len(trackvoice[t][p]) for t in range(2) for p in range(3))
saved_pct = (len(cells) - LEN_X) * 100 // len(cells)
print('=== 36 OLK 直线+长休止Z线圈 ===')
print(f'曲子={NOTES} 发声音={nplaced} dropped={dropped} 钳音={clamped[0]}')
print(f'动作: {ntrig}音 + {ninline}内联段 + {ncoil}线圈')
print(f'直线长 X={LEN_X} (原直链~{len(cells)}, 省 {len(cells)-LEN_X}={saved_pct}%)')
print(f'占地 x[{WX0}..{WX1}]={WX1-WX0} z[{WZ0}..{WZ1}]={WZ1-WZ0}(线圈Z鳍); 批次={len(batches)}; 无碰撞✓')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> [直接播放]; [停止]立即静音')
