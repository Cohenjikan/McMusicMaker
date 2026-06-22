# -*- coding: utf-8 -*-
"""30_build_full.py — 双轨辐射整机(7 lane -> 2 轨, 每轨辐射和弦; 共享骨架同步)。

重构: 旧版 7 条单音 lane(z 占 13) -> 2 条【辐射轨】, 每轨一个强充能导体同刻触发
  【上 + ±Z】三音(三音和弦), 共 6 声部。两轨用【完全相同的中继器骨架】(同延迟同列)
  -> 脉冲逐刻到同一列 -> 绝对同步、灯闪一致。配 RedPiano 实体绑定声音 -> 站哪都听全曲。
时序: tick80, U=1红石刻=0.025s, 变延迟中继器(1..4)压缩空隙(同 24/25)。
声部分配: 每刻和弦按音高降序取前 6, 高 3 -> 轨A, 次 3 -> 轨B; 轨内 上/+Z/-Z。第7+音丢弃(罕见)。
播放(健壮): setup 复位 -> [直接播放](站/飞均可听全曲) / [骑行播放](spectator 平滑滑行) / [停止] / 开关。
折叠(下一步, 几何已验脚本29): 把每条直链按平面蛇形折叠压 X; 见 DEVLOG。本机先直链(实体声音下长度不影响听感)。

需 RedPiano 模组(实体绑定声音 + rpcfg 开关) + qzpno 资源包。
Run: python 30_build_full.py [notes.json] [NS] [OX]
"""
import os, sys, json, shutil
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = sys.argv[1] if len(sys.argv) > 1 else 'notes_cjzm.json'
NS = sys.argv[2] if len(sys.argv) > 2 else 'qzv2'
OX = int(sys.argv[3]) if len(sys.argv) > 3 else 220000
OZ = 0
Y = 255
TRACK_Z = [0, 4]                  # 两轨基准 z(各辐射 ±1 -> 占 z=-1..1 与 3..5, 间隙 z=2)
LAMP, RFACING, BATCH = 'minecraft:redstone_lamp', 'west', 2000
PASS = 'minecraft:stone'          # 无音直通导体
VOICES = 6                        # 2 轨 x 3 声部
TPS, PULSE = 80, 4
U = 2 / TPS
CAM_TRAIL, RIDEY, CYAW, CPITCH = 0, Y + 4, -90, 28
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

# 量化 + 和弦声部分配: trackvoice[track][pos][tick] = (block, nv); pos 0=上 1=+Z 2=-Z
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

# 共享时间线(同 24/25): 触发刻并集 -> 唯一变延迟骨架, 两轨共用
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
    else: assert cum == v + OFFSET, f"时序错位 @tick {v}"

def track_spine(t, zb):
    """一条辐射轨: 沿共享 cells[] 铺中继器骨架; 发声列用该轨 3 声部辐射(上+±Z)。"""
    sz = OZ + zb
    out = [f'setblock {OX-1} {Y-1} {sz} {LAMP}']
    x = OX
    for kind, v in cells:
        if kind == 'rep':
            out.append(f'setblock {x} {Y-1} {sz} {LAMP}')
            out.append(f'setblock {x} {Y} {sz} minecraft:repeater[facing={RFACING},delay={v}]')
        else:
            above = trackvoice[t][0].get(v); pz = trackvoice[t][1].get(v); mz = trackvoice[t][2].get(v)
            out.append(f'setblock {x} {Y-1} {sz} {LAMP}')
            out.append(f'setblock {x} {Y} {sz} {above[0] if above else PASS}')        # C = 上音映射 或 直通
            if above:
                out.append(f'setblock {x} {Y+1} {sz} minecraft:note_block[note={above[1]}]')
                out.append(f'setblock {x} {Y+2} {sz} air')
            else:
                out.append(f'setblock {x} {Y+1} {sz} air')
            if pz:                                                                    # +Z 音(C 相邻强充能)
                out.append(f'setblock {x} {Y-1} {sz+1} {pz[0]}')
                out.append(f'setblock {x} {Y} {sz+1} minecraft:note_block[note={pz[1]}]')
                out.append(f'setblock {x} {Y+1} {sz+1} air')
            if mz:                                                                    # -Z 音
                out.append(f'setblock {x} {Y-1} {sz-1} {mz[0]}')
                out.append(f'setblock {x} {Y} {sz-1} minecraft:note_block[note={mz[1]}]')
                out.append(f'setblock {x} {Y+1} {sz-1} air')
        x += 1
    return out, x

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 双轨辐射整机(2 轨 x 3 声部, 共享骨架, tick80)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

build = ['gamerule commandModificationBlockLimit 2147483647']
endx = OX
for t in range(2):
    cmds, ex = track_spine(t, TRACK_Z[t]); build += cmds; endx = max(endx, ex)
LEN = endx - OX
CAMZ = OZ + (TRACK_Z[0] + TRACK_Z[1]) // 2
MUSIC_TICKS = (MAXTICK + OFFSET) * 2
RIDE_SPEED = round(LEN / max(1, MUSIC_TICKS), 4)
PBX = OX - 3
def labeled_button(bx, cmd, lines):
    msgs = ','.join('\'{"text":"%s"}\'' % s for s in (list(lines) + ['', '', '', ''])[:4])
    return [f'setblock {bx} {Y-1} {OZ} {LAMP}',
            f'setblock {bx} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"{cmd}",auto:0b}}',
            f'setblock {bx} {Y+1} {OZ} minecraft:stone_button[face=floor]',
            f'setblock {bx} {Y-1} {OZ-2} {LAMP}',
            'setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}' % (bx, Y, OZ - 2, msgs)]
build += labeled_button(PBX,    f'function {NS}:play',           ['[直接播放]', '站/飞均可', '听全曲'])
build += labeled_button(PBX-2,  f'function {NS}:play_ride',      ['[骑行播放]', 'spectator', '平滑巡游'])
build += labeled_button(PBX-4,  f'function {NS}:stop',           ['[停止]', '复位状态', '卡住按这'])
build += labeled_button(PBX-6,  f'function {NS}:cfg/polytoggle', ['[复音增益]', '大和弦', '防糊'])
build += labeled_button(PBX-8,  f'function {NS}:cfg/humantoggle',['[微抖动]', '去复印感'])
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]

WX0, WZ0, WX1, WZ1 = OX - 10, OZ - 3, endx + 2, OZ + TRACK_Z[1] + 2
zc = (WZ1 // 16) - (WZ0 // 16) + 1
xstep = max(1, 240 // zc)
flbuild, cx = [], WX0
while cx <= WX1:
    cxe = min(WX1, cx + xstep * 16 - 1)
    flbuild.append(f'forceload add {cx} {WZ0} {cxe} {WZ1}'); cx = cxe + 1

src_pts = [(OX - 1, OZ + zb) for zb in TRACK_Z]
TRIG_CLEAR = [f'setblock {sx} {Y} {sz} minecraft:air' for sx, sz in src_pts]
SCHED_CLEAR = [f'schedule clear {NS}:{f}' for f in ('done', 'fire', 'firestop', 'startbuild', 'ridestop')]
END_TICKS = MUSIC_TICKS + 200

# ---- 健壮播放 ----
RESET = [f'scoreboard players set PLAY {NS} 0', f'scoreboard players set RIDE {NS} 0', f'scoreboard players set CAM {NS} 0']
wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1',
            f'scoreboard players set CLR {NS} -1'] + RESET + ['forceload remove all',
            'scoreboard objectives add rpcfg dummy', 'scoreboard players set poly rpcfg 1', 'scoreboard players set human rpcfg 1']
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] 双轨辐射整机 loaded. ","color":"aqua"}},{{"text":"需RedPiano模组+qzpno包. 曲速80 -> /function {NS}:setup"}}]'])
wf('setup', RESET + ['gamemode creative @a', 'stopsound @a master', f'scoreboard players set CLR {NS} -1']
   + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t',
      f'tellraw @a "[{NS}] reset + forceloading; building... (等 BUILT)"'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building (2 轨 x {NCELLS}格)..."')
wf('tick', f'execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n'
           f'execute if score CLR {NS} matches 0.. run function {NS}:clearstep\n'
           f'execute if score RIDE {NS} matches 1 run tp @a ~{RIDE_SPEED} ~ ~')
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('buildstep', bs)
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
wf('builddone', f'scoreboard players set BLD {NS} -1\n'
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"曲速80. 按钮: [直接播放]/[骑行播放]/[停止]"}}]')
wf('playcore', [f'scoreboard players set PLAY {NS} 1', 'stopsound @a master'] + TRIG_CLEAR + [f'schedule function {NS}:fire 2t'])
wf('play', [f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先按[停止]"',
            f'scoreboard players set CAM {NS} 0', f'scoreboard players set RIDE {NS} 0', f'function {NS}:playcore',
            f'tellraw @a "[{NS}] GO。站着或自由飞都能听全曲(声音绑你本人)。灯随脉冲流动。"'])
wf('play_ride', [f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先按[停止]"',
                 'gamemode spectator @a', f'tp @a {OX} {RIDEY} {CAMZ} {CYAW} {CPITCH}',
                 f'scoreboard players set RIDE {NS} 1', f'schedule function {NS}:ridestop {MUSIC_TICKS + 60}t',
                 f'function {NS}:playcore',
                 f'tellraw @a "[{NS}] GO(平滑巡游)。spectator 滑行+自由转视角; 声音绑你本人=不断不糊。"'])
wf('ridestop', [f'scoreboard players set RIDE {NS} 0', 'gamemode creative @a', f'tellraw @a "[{NS}] (巡游结束)"'])
wf('stop', RESET + ['gamemode creative @a', 'stopsound @a master'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a "[{NS}] 已停止/复位。可重新 [直接播放]/[骑行播放]。"'])
wf('fire', flbuild + [f'setblock {sx} {Y} {sz} minecraft:redstone_block' for sx, sz in src_pts]
   + [f'schedule function {NS}:firestop {PULSE}t', f'schedule function {NS}:done {END_TICKS}t'])
wf('firestop', TRIG_CLEAR)
wf('done', RESET + ['gamemode creative @a', 'forceload remove all',
           f'tellraw @a "[{NS}] (end) 重放: setup; 清除: cleanup。"'])
wf('cfg/polytoggle', ['scoreboard players set rptmp rpcfg 1', 'scoreboard players operation rptmp rpcfg -= poly rpcfg',
                      'scoreboard players operation poly rpcfg = rptmp rpcfg',
                      f'execute if score poly rpcfg matches 1 run tellraw @a "[{NS}] 复音增益 ON"',
                      f'execute if score poly rpcfg matches 0 run tellraw @a "[{NS}] 复音增益 OFF"'])
wf('cfg/humantoggle', ['scoreboard players set rptmp rpcfg 1', 'scoreboard players operation rptmp rpcfg -= human rpcfg',
                       'scoreboard players operation human rpcfg = rptmp rpcfg',
                       f'execute if score human rpcfg matches 1 run tellraw @a "[{NS}] 微抖动 ON"',
                       f'execute if score human rpcfg matches 0 run tellraw @a "[{NS}] 微抖动 OFF"'])
SEG = 200
clr_segs = (LEN + 16) // SEG + 1
for k in range(clr_segs):
    fx0 = WX0 + k * SEG; fx1 = min(endx + 2, fx0 + SEG - 1)
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
print('=== 30 双轨辐射整机 ===')
print(f'曲子={NOTES} 发声音={nplaced} dropped={dropped} 钳音={clamped[0]} OFFSET={OFFSET}')
print(f'骨架: {NCELLS}格 = {nrep}中继器 + {ncond}发声列(并集). 2 轨(z={TRACK_Z}) x 3 声部=6, 共享骨架->同步')
print(f'机器: {LEN}长 x {TRACK_Z[1]-(-1)+1}宽 (~{LEN//16}区块长)  批次={len(batches)}  (旧 7lane: 13宽; 本版省 ~5/7 中继器)')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> 按[直接播放]/[骑行播放]; 卡住按[停止]')
