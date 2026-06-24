# -*- coding: utf-8 -*-
"""41_build_comb.py — Task2: olk 紧凑梳齿(3宽和弦 + 蛇形 + 红石粉0延迟转向)。

用户方案(第N轮敲定): 不拆两板。每个触发把【6 个音(双轨×3)挤进 3 格宽】——
  用【两个导体】(主导体被中继器强充能 + 相邻导体用红石粉0延迟连过来),各发 上+(+Z)+(-Z),
  合计 6 音落在 z-1..z+1 = 3 宽、x..x+1 = 2 长 的小块里。于是【行距从 8 降到 4】,
  同样宽 15 能折进 ~4 行(而非 2 行)-> 长度从 2527 砍到 ~1600。声部一个不砍。
转向: 每行末用【纯红石粉 0 延迟 U 弯】换行(同 32 已验), 转向不吃时序 -> 累计延迟一格不差。
  拐弯格只走红石粉、不放音符盒(行首必为中继器, 强充能干净)。
注: 第二导体靠红石粉【弱充能】触发音符盒——用户(红石专家)担保 1 格安全距离不漏电、弱充能能响;
    我这边只用 Python 兜底【时序断言 + 方块不重叠断言】, 弱充能的电学正确性由用户游戏内验。
Run: python 41_build_comb.py [notes.json] [NS] [OX] [ROWS]
"""
import os, sys, json, shutil
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = sys.argv[1] if len(sys.argv) > 1 else 'notes_olk.json'
NS    = sys.argv[2] if len(sys.argv) > 2 else 'qzolkc'
OX    = int(sys.argv[3]) if len(sys.argv) > 3 else 260000
ROWS  = int(sys.argv[4]) if len(sys.argv) > 4 else 4          # 折几行(宽~=3*ROWS+gap); 4行≈宽15
OZ, Y = 0, 255
ROW_DZ = 4                         # 行距(29已验): 3宽和弦(z±1) + 行间留1空 -> 下一行 +4
RFACE = {1: 'west', -1: 'east'}
LAMP, PASS, BATCH = 'minecraft:redstone_lamp', 'minecraft:stone', 2000
VOICES, TPS, PULSE = 6, 80, 4
U = 2 / TPS
SSTOP = 'stopsound @a'
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界 (1)/datapacks"

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

# ---- 量化 + 取每刻前6音(降序), 0..2=导体A三音, 3..5=导体B三音 ----
bycell = defaultdict(list)
for n in notes:
    if n['vel'] >= 0.04: bycell[round(n['t'] / U)].append(n)
voices = {}                                  # tick -> [6 个 (block,nv) 或 None]
dropped = 0
for tick, grp in bycell.items():
    g = sorted(grp, key=lambda x: -x['midi'])
    vs = [map_note(n['midi'], n['vel']) for n in g[:VOICES]] + [None] * VOICES
    voices[tick] = vs[:VOICES]
    dropped += max(0, len(g) - VOICES)

# ---- 共享时间线骨架 cells[](同 24/30) ----
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
cum = 0                                      # ★ 时序断言(红石粉转向=0延迟, 折叠不改)
for kind, v in cells:
    if kind == 'rep': cum += v
    else: assert cum == v + OFFSET, f"时序错位 @tick {v}: cum={cum} != {v+OFFSET}"

# ---- 展开: 'trig' 占 3 个 X 格 —— 导体A(中继器强充, 发前3音) -> 红石粉(0延迟, 把信号送下去 +
#   弱充能导体B) -> 导体B(发后3音) -> 下一中继器读B。红石粉0延迟=不吃时序; 实心导体相邻不传电,
#   所以中间必须夹一格红石粉(=用户说的"转向/连接用红石粉")。
#   eseq[i] = ('rep',d) | ('cA',tick) | ('wire',None) | ('cB',tick)
eseq = []
for kind, v in cells:
    if kind == 'rep': eseq.append(('rep', v))
    else: eseq.append(('cA', v)); eseq.append(('wire', None)); eseq.append(('cB', v))
NE = len(eseq)
ROWLEN = (NE + ROWS - 1) // ROWS              # 每行格数 -> 恰好 ROWS 行

# ---- 蛇形折叠展开序列: 只在 'rep' 前换行(行首=中继器, 强充能干净) ----
pos = [None] * NE                             # pos[i]=(xoff,zoff,dirx)
legs = []
x, z, d, col = 0, 0, 1, 0
for i in range(NE):
    pos[i] = (x, z, d)
    x += d; col += 1
    last = (i == NE - 1)
    nxt_rep = (not last) and eseq[i + 1][0] == 'rep'
    if (not last) and col >= ROWLEN and nxt_rep:
        legs.append((x, z, z + ROW_DZ)); z += ROW_DZ; d = -d; x += d; col = 0
NROWS = len(legs) + 1

# ---- 发射 + 碰撞断言 ----
occ = {}
def put(out, x, y, zz, blk):
    k = (x, y, zz)
    if k in occ and occ[k] != blk and 'air' not in (occ[k], blk):
        raise AssertionError(f"碰撞 @{k}: {occ[k]} vs {blk}")
    occ[k] = blk; out.append(f'setblock {x} {y} {zz} {blk}')

def chord3(out, X, Z, vlist):
    """一个导体格: 强充能导体(或直通) + 上/+Z/-Z 三音(各坐映射块, 邻接强充能导体触发)。"""
    up, pz, mz = vlist
    put(out, X, Y - 1, Z, LAMP)
    put(out, X, Y, Z, up[0] if up else PASS)              # 链导体 = 上音映射块 或 直通
    if up: put(out, X, Y + 1, Z, f'minecraft:note_block[note={up[1]}]'); put(out, X, Y + 2, Z, 'air')
    if pz: put(out, X, Y - 1, Z + 1, pz[0]); put(out, X, Y, Z + 1, f'minecraft:note_block[note={pz[1]}]'); put(out, X, Y + 1, Z + 1, 'air')
    if mz: put(out, X, Y - 1, Z - 1, mz[0]); put(out, X, Y, Z - 1, f'minecraft:note_block[note={mz[1]}]'); put(out, X, Y + 1, Z - 1, 'air')

def emit():
    out = [f'setblock {OX-1} {Y-1} {OZ} {PASS}']          # 源支撑
    for i, (xo, zo, dirx) in enumerate(pos):
        X, Z = OX + xo, OZ + zo
        kind, v = eseq[i]
        if kind == 'rep':
            put(out, X, Y - 1, Z, LAMP)
            put(out, X, Y, Z, f'minecraft:repeater[facing={RFACE[dirx]},delay={v}]')
        elif kind == 'cA':
            chord3(out, X, Z, voices[v][0:3])             # 导体A(强充能): 前3音
        elif kind == 'wire':                              # 红石粉(0延迟): 续链 + 弱充能导体B
            put(out, X, Y - 1, Z, PASS); put(out, X, Y, Z, 'minecraft:redstone_wire')
        else:  # cB —— 被红石粉弱充能触发, 发后3音
            chord3(out, X, Z, voices[v][3:6])
    for (xleg, zf, zt) in legs:                           # 红石粉 0 延迟 U 弯
        for zz in range(zf, zt + 1):
            put(out, OX + xleg, Y - 1, OZ + zz, PASS)
            put(out, OX + xleg, Y, OZ + zz, 'minecraft:redstone_wire')
    return out

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} olk紧凑梳齿(3宽和弦, 红石粉0延迟转向, tick80)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

build = ['gamerule commandModificationBlockLimit 2147483647'] + emit()
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]
allx = [k[0] for k in occ]; allz = [k[2] for k in occ]
WX0, WZ0, WX1, WZ1 = min(allx) - 2, min(allz) - 2, max(allx) + 2, max(allz) + 2
zc = (WZ1 // 16) - (WZ0 // 16) + 1; xstep = max(1, 240 // max(1, zc))
flbuild, cx = ['forceload remove all'], WX0
while cx <= WX1:
    cxe = min(WX1, cx + xstep * 16 - 1); flbuild.append(f'forceload add {cx} {WZ0} {cxe} {WZ1}'); cx = cxe + 1
src = (OX - 1, OZ)
TRIG_CLEAR = [f'setblock {src[0]} {Y} {src[1]} minecraft:air']
SCHED_CLEAR = [f'schedule clear {NS}:{f}' for f in ('done', 'fire', 'firestop', 'startbuild', 'unsil')]
MUSIC_TICKS = (MAXTICK + OFFSET) * 2; END_TICKS = MUSIC_TICKS + 200
PBX = OX - 3
def lbtn(bx, cmd, lines):
    msgs = ','.join('\'{"text":"%s"}\'' % s for s in (list(lines) + ['', '', '', ''])[:4])
    return [f'setblock {bx} {Y-1} {OZ} {LAMP}',
            f'setblock {bx} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"{cmd}",auto:0b}}',
            f'setblock {bx} {Y+1} {OZ} minecraft:stone_button[face=floor]',
            f'setblock {bx} {Y-1} {OZ-2} {LAMP}',
            'setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}' % (bx, Y, OZ-2, msgs)]
ctl = ['gamerule commandModificationBlockLimit 2147483647']
ctl += lbtn(PBX,   f'function {NS}:play', ['[直接播放]', '站着即可', '听全曲'])
ctl += lbtn(PBX-2, f'function {NS}:stop', ['[停止]', '立即静音', '卡住按这'])
ctl += lbtn(PBX-4, f'function {NS}:cfg/polytoggle', ['[复音增益]', '大和弦', '防糊'])
ctl += lbtn(PBX-6, f'function {NS}:cfg/humantoggle', ['[微抖动]', '去复印感'])

RESET = [f'scoreboard players set PLAY {NS} 0', f'scoreboard players set SIL {NS} 0']
wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1', f'scoreboard players set CLR {NS} -1']
   + RESET + ['forceload remove all', 'scoreboard objectives add rpcfg dummy', 'scoreboard players set poly rpcfg 1',
              'scoreboard players set human rpcfg 1'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] olk 紧凑梳齿 loaded. ","color":"aqua"}},{{"text":"需模组+qzpno. /tick rate 80 -> /function {NS}:setup"}}]'])
wf('setup', RESET + ['gamemode creative @a', SSTOP, f'scoreboard players set CLR {NS} -1'] + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t', f'tellraw @a "[{NS}] reset+forceload; building..."'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building (梳齿 {NROWS}行 x {ROWLEN})..."')
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
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"梳齿 {NROWS}行x{ROWLEN}. 按[直接播放]/[停止]"}}]')
wf('playcore', [f'scoreboard players set PLAY {NS} 1', f'scoreboard players set SIL {NS} 0', SSTOP] + TRIG_CLEAR + [f'schedule function {NS}:fire 2t'])
wf('play', [f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先按[停止]"',
            f'function {NS}:playcore', f'tellraw @a "[{NS}] GO。站着听全曲(声音绑你本人)。"'])
wf('stop', RESET + ['gamemode creative @a', SSTOP] + SCHED_CLEAR + TRIG_CLEAR
   + [f'scoreboard players set SIL {NS} 1', f'schedule function {NS}:unsil {END_TICKS}t',
      f'tp @a {PBX} {Y+3} {OZ}', f'tellraw @a "[{NS}] 已停止(立即静音)。"'])
wf('unsil', f'scoreboard players set SIL {NS} 0')
wf('fire', flbuild + [f'setblock {src[0]} {Y} {src[1]} minecraft:redstone_block']
   + [f'schedule function {NS}:firestop {PULSE}t', f'schedule function {NS}:done {END_TICKS}t'])
wf('firestop', TRIG_CLEAR)
wf('done', RESET + ['gamemode creative @a', f'tellraw @a "[{NS}] (end) 重放[直接播放]; 拆 /function {NS}:cleanup。"'])
SEG = 200; clr_segs = (WX1 - WX0 + 16) // SEG + 1
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
wf('cfg/polytoggle', ['scoreboard players set rptmp rpcfg 1', 'scoreboard players operation rptmp rpcfg -= poly rpcfg',
                      'scoreboard players operation poly rpcfg = rptmp rpcfg',
                      f'execute if score poly rpcfg matches 1 run tellraw @a "[{NS}] 复音增益 ON"',
                      f'execute if score poly rpcfg matches 0 run tellraw @a "[{NS}] 复音增益 OFF"'])
wf('cfg/humantoggle', ['scoreboard players set rptmp rpcfg 1', 'scoreboard players operation rptmp rpcfg -= human rpcfg',
                       'scoreboard players operation human rpcfg = rptmp rpcfg',
                       f'execute if score human rpcfg matches 1 run tellraw @a "[{NS}] 微抖动 ON"',
                       f'execute if score human rpcfg matches 0 run tellraw @a "[{NS}] 微抖动 OFF"'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
nrep = sum(1 for k, _ in eseq if k == 'rep'); ncA = sum(1 for k, _ in eseq if k == 'cA')
nplaced = sum(1 for t in voices for v in voices[t] if v)
zwidth = max(allz) - min(allz) + 1
fold_chunks = ((WX1 // 16) - (WX0 // 16) + 1) * ((WZ1 // 16) - (WZ0 // 16) + 1)
print('=== 41 olk 紧凑梳齿(3宽和弦 + 红石粉0延迟转向) ===')
print(f'曲子={NOTES} 发声音={nplaced} dropped={dropped} 钳音={clamped[0]} OFFSET={OFFSET}')
print(f'骨架 {len(cells)}格 -> 展开 {NE}格({nrep}中继器 + {ncA}触发×2导体). 折 {NROWS}行 x {ROWLEN}, 行距{ROW_DZ}, {len(legs)}个红石粉U弯')
print(f'★宽度: {zwidth} 格(3宽和弦, 行距4; 对比 7宽老布局)')
print(f'★长度: X长~{WX1-WX0} (老布局同宽要 ~2528)')
print(f'占地 x[{WX0}..{WX1}]={WX1-WX0} z[{WZ0}..{WZ1}]={WZ1-WZ0}; {fold_chunks}区块; 批次={len(batches)}')
print(f'断言: 时序(cum==tick) ✓  碰撞(无重叠) ✓')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> [直接播放]; [停止]')
