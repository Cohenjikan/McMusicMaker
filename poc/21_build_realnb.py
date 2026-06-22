# -*- coding: utf-8 -*-
"""21_build_realnb.py — 真音符盒全曲机器(RedPiano 模组 + Method B 变延迟时序)。

100% 真音符盒(minecraft:note_block), 被红石脉冲触发, 模组让其按"正下方映射方块"
播我们的钢琴采样 + note档移调 + 自定义音量。零音色亏损、零伪造、真红石驱动。

每条 lane(3 z排):
  lane_z   : 脉冲线脊柱(Method B 变延迟 repeater + dust; 底座=红石灯进度带)
  lane_z+1 : 分接中继器(facing=north, 把脉冲插进音符盒)
  lane_z+2 : 真音符盒(垫底=映射方块, 上方空气)
时序: tick80 + 变延迟(1..4红石刻)精确落到每个发声刻(忠实 6ms)。分接中继器加恒定 delay-1(不影响相对节奏)。
红石灯: 脊柱底座全用 redstone_lamp, dust 经过即点亮 -> 流动光带显示播放位置(每刻仅几盏切换, 不卡)。

需 RedPiano 模组已装 + qzpno 资源包开。
Run(base python): python 21_build_realnb.py [notes_wll.json] [NS] [OX]
"""
import os, sys, json, shutil
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = sys.argv[1] if len(sys.argv) > 1 else 'notes_wll.json'
NS = sys.argv[2] if len(sys.argv) > 2 else 'qzwll'
OX = int(sys.argv[3]) if len(sys.argv) > 3 else 150000
OZ = 0
Y, LANE_DZ = 255, 4            # 天上(自然空气): 音符盒上方=空气可发声 + 红石灯可见, 免清理
LAMP, RFACING, BATCH = 'redstone_lamp', 'west', 2000
MAXLANES, VEL_FLOOR = 7, 0.04
TPS, PULSE = 80, 4
U = 2 / TPS                                # 0.025s = 1 红石刻
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"

notes = json.load(open(os.path.join(HERE, NOTES), encoding='utf-8'))['notes']
rp = json.load(open(os.path.join(HERE, 'redpiano_map.json'), encoding='utf-8'))
bands = rp['bands']                        # 20 段 base_midi
RPMAP = rp['map']                          # f'{band}_{layer}' -> {block, sound, vol}
man = json.load(open(os.path.join(HERE, 'samples_manifest_piano.json'), encoding='utf-8'))
MIDI_NAME = {int(s['base_midi']): s['note'] for s in man['samples']}   # 24->'C1'
VEL_CN = {'p': '弱', 'mf': '中', 'f': '强'}
used = {}                                  # (band,layer) -> block, 用于音色展示台
def layer_of(v): return 'p' if v < 0.40 else ('mf' if v < 0.72 else 'f')
clamped = [0]
def map_note(m, v):
    band = min(bands, key=lambda b: abs(b - m))
    nv = 12 + (m - band)
    if nv < 0 or nv > 24: clamped[0] += 1
    nv = max(0, min(24, nv))
    layer = layer_of(v)
    block = RPMAP[f'{band}_{layer}']['block']
    used[(band, layer)] = block
    return block, nv

# 量化到 1rt 格 + 分 lane
bycell = defaultdict(list)
for n in notes:
    if n['vel'] >= VEL_FLOOR: bycell[round(n['t'] / U)].append(n)
lane_at = [defaultdict(dict) for _ in range(MAXLANES)]   # lane_at[L][tick] = (block, nv)
dropped = 0
for tick, grp in bycell.items():
    for i, n in enumerate(sorted(grp, key=lambda x: -x['midi'])):
        if i >= MAXLANES: dropped += 1; continue
        lane_at[i][tick] = map_note(n['midi'], n['vel'])
NLANES = max((L + 1 for L in range(MAXLANES) if lane_at[L]), default=1)
trig_ticks = sorted(bycell)
MAXTICK = trig_ticks[-1]

# 变延迟格序列(Method B): gap -> (G-1)//4 个 delay-4 + 1 个余数触发格
cells = []        # (delay, trig_tick_or_None)
cum = 0
cam_path = []     # (到达游戏刻=2*cum_before, 该格X) 每个格(含填充), 相机逐格跟脉冲(不超前)
for T in trig_ticks:
    G = T - cum
    if G <= 0: continue
    nfill = (G - 1) // 4
    for _ in range(nfill):
        cam_path.append((2 * cum, OX + 2 * len(cells)))
        cells.append((4, None)); cum += 4
    tdelay = G - 4 * nfill
    cam_path.append((2 * cum, OX + 2 * len(cells)))
    cells.append((tdelay, T)); cum += tdelay
NCELLS = len(cells)
assert cum == MAXTICK, f"cum {cum} != MAXTICK {MAXTICK}"

DP = os.path.join(HERE, 'build', f'{NS}_realnb')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 真音符盒机器(RedPiano mod, tick80, 变延迟)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

def box(a0, a1, r0, r1): return OX + a0, OZ + r0, OX + a1, OZ + r1
def spine(lane_z, notes_at):
    sz = OZ + lane_z
    out = [f'setblock {OX-1} {Y-1} {sz} minecraft:{LAMP}']             # 源支撑
    for k, (d, trig) in enumerate(cells):
        rx = OX + 2*k; dx = OX + 2*k + 1
        out.append(f'setblock {rx} {Y-1} {sz} minecraft:{LAMP}')
        out.append(f'setblock {rx} {Y} {sz} minecraft:repeater[facing={RFACING},delay={d}]')
        out.append(f'setblock {dx} {Y-1} {sz} minecraft:{LAMP}')
        out.append(f'setblock {dx} {Y} {sz} minecraft:redstone_wire')
        if trig is not None and trig in notes_at:
            block, nv = notes_at[trig]
            out.append(f'setblock {dx} {Y-1} {sz+1} minecraft:smooth_stone')              # 分接中继器底座
            out.append(f'setblock {dx} {Y} {sz+1} minecraft:repeater[facing=north,delay=1]')  # 直插音符盒(+Z)
            out.append(f'setblock {dx} {Y-1} {sz+2} {block}')                              # 垫底映射方块
            out.append(f'setblock {dx} {Y} {sz+2} minecraft:note_block[note={nv}]')        # 真音符盒
            out.append(f'setblock {dx} {Y+1} {sz+2} air')                                  # 上方空气(保险, 发声必需)
    return out

A0, A1 = -(16 + 2 * len(used)), 2 * NCELLS + 3    # 西扩盖住控制台+音色展示台
R0, R1 = -3, (NLANES - 1) * LANE_DZ + 4
PBX = OX - 3

def sign(x, y, z, lines, facing='south'):
    msgs = ','.join("'{\"text\":\"%s\"}'" % t for t in (list(lines) + ['', '', '', ''])[:4])
    return 'setblock %d %d %d minecraft:oak_wall_sign[facing=%s]{front_text:{messages:[%s]}}' % (x, y, z, facing, msgs)

def control_and_showcase():
    out = []
    # 两个物理按钮(命令方块+按钮+木牌): 直接播放 / 相机播放 (飞过去按, 不靠指令)
    out += [f'setblock {OX-4} {Y-1} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"function {NS}:play",auto:0b}}',
            f'setblock {OX-4} {Y} {OZ} minecraft:stone_button[face=floor]',
            sign(OX-4, Y-1, OZ+1, ['[直接播放]', '无相机']),
            f'setblock {OX-6} {Y-1} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"function {NS}:play_cam",auto:0b}}',
            f'setblock {OX-6} {Y} {OZ} minecraft:stone_button[face=floor]',
            sign(OX-6, Y-1, OZ+1, ['[相机播放]', '自动跟随'])]
    # 音色展示台: 起点西侧一排, 每个用到的音色一站(垫底块+音符盒+按钮+中文木牌)
    for i, (band, layer) in enumerate(sorted(used.keys())):
        sx, sz = OX - 12 - 2 * i, OZ
        out += [f'setblock {sx} {Y-1} {sz} {used[(band, layer)]}',
                f'setblock {sx} {Y} {sz} minecraft:note_block[note=12]',
                f'setblock {sx} {Y+1} {sz} air',
                f'setblock {sx} {Y} {sz+1} minecraft:stone_button[face=wall,facing=south]',
                sign(sx, Y-1, sz+1, ['钢琴', MIDI_NAME.get(band, str(band)), VEL_CN[layer]])]
    return out

build = ['gamerule commandModificationBlockLimit 2147483647']
for L in range(NLANES): build += spine(L * LANE_DZ, lane_at[L])
build += control_and_showcase()
SHOW_W = 12 + 2 * len(used)        # 展示台向西延伸宽度(forceload 要覆盖)
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
            f'scoreboard players set CLR {NS} -1', f'scoreboard players set PLAY {NS} 0',
            f'scoreboard players set CAM {NS} 0', 'forceload remove all']
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] 我落泪 真音符盒机器 loaded. ","color":"aqua"}},{{"text":"需RedPiano模组+qzpno包. 先曲速80, 再 /function {NS}:setup"}}]'])
wf('setup', [f'scoreboard players set PLAY {NS} 0', 'stopsound @a master', f'scoreboard players set CLR {NS} -1']
   + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t',
      f'tellraw @a "[{NS}] reset + forceloading; building... (等 BUILT)"'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building ({NLANES} lanes, {NCELLS} cells)..."')
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
   + TRIG_CLEAR + [f'schedule function {NS}:fire 2t', f'tellraw @a "[{NS}] GO. 红石灯流动=播放位置。"'])
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
    wf(f'clr/c{k}', f'fill {fx0} {Y-2} {fz0} {fx1} {Y+2} {fz1} air')
wf('cleardone', [f'scoreboard players set CLR {NS} -1', 'forceload remove all', f'tellraw @a "[{NS}] cleaned up."'])
cs = [f'execute if score CLR {NS} matches {k} run function {NS}:clr/c{k}' for k in range(clr_segs)]
cs += [f'execute if score CLR {NS} matches {clr_segs} run function {NS}:cleardone',
       f'execute if score CLR {NS} matches 0..{clr_segs} run scoreboard players add CLR {NS} 1']
wf('clearstep', cs)
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647', f'scoreboard players set PLAY {NS} 0',
               f'scoreboard players set CAM {NS} 0', 'gamemode creative @a',
               'stopsound @a master', f'scoreboard players set BLD {NS} -1'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'scoreboard players set CLR {NS} 0', f'tellraw @a "[{NS}] tearing down..."'])

# ---- 相机: 观察者 + 逐格跟随脉冲本身(不超前, 跟得住才听得到) + 低位前向"仰视"运镜 ----
# 相机在脉冲后方 TRAIL 格, 低位(Y+3), 面向 +X(脉冲行进方向)沿轨看向地平线
CAMY, CAMZ, CYAW, CPITCH, TRAIL = Y + 3, OZ + 14, -90, 5, 8
wf('camtp', f'$tp @a $(x) {CAMY} {CAMZ} {CYAW} {CPITCH}')
wf('nexttarget', [f'execute if score CAM {NS} matches 1 run data modify storage {NS}:cam m.x set from storage {NS}:cam q[0]',
                  f'execute if score CAM {NS} matches 1 run function {NS}:camtp with storage {NS}:cam m',
                  f'execute if score CAM {NS} matches 1 run data remove storage {NS}:cam q[0]'])
wf('camdone', [f'scoreboard players set CAM {NS} 0', 'gamemode creative @a', f'tellraw @a "[{NS}] (相机结束)"'])
_q = '[' + ','.join(str(X - TRAIL) for (_, X) in cam_path) + ']'
_camsched = [f'schedule function {NS}:nexttarget {gt}t append' for (gt, _) in cam_path]
wf('play_cam', [f'execute if score PLAY {NS} matches 1 run return 0',
                'gamemode spectator @a',
                f'data modify storage {NS}:cam q set value {_q}',
                f'scoreboard players set CAM {NS} 1']
   + _camsched + [f'schedule function {NS}:camdone {END_TICKS}t', f'function {NS}:play'])

dst = os.path.join(WORLD_DP, f'{NS}_realnb')
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 21 真音符盒全曲机器 ===')
print(f'曲子={NOTES}  音符={sum(len(v) for v in lane_at)} dropped={dropped} 钳音={clamped[0]}  lanes={NLANES}')
print(f'有音刻={len(trig_ticks)}  格数={NCELLS}  机器={2*NCELLS}长 x {R1-R0}宽 (~{2*NCELLS//16}x{(R1-R0)//16+1}区块)  批次={len(batches)}')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> /function {NS}:play')
