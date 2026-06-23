# -*- coding: utf-8 -*-
"""38_build_cmdplayer.py — Task 3(修正): 命令方块/数据包【按节奏在原地触发红石块】打响音符盒。

用户原意(澄清): 不要长条行进脉冲, 也不是2D折叠 —— 而是【在原地】用数据包(命令方块)
  按节奏, 到点就给对应音符盒【放一个红石块】把它打响。无行进脉冲、无成千中继器 ->
  ★ 根治"服务器过载/音频丢失"(实测大机器 'Can't keep up 209 ticks behind' = 过载断音)。

机制:
  - 紧凑音符盒阵(原地): 每个【发声刻】= 一列, 列里每个声部一个音符盒(坐其音色映射块上, 上方空气)。
    列按网格折行排布(COLS 宽), 占地极小 -> forceload 只几十区块 -> 不过载。
  - 触发: 数据包 schedule 链, step_c 到该刻就在该列每个音符盒【下方放红石块】(强充映射块->音符盒响),
    schedule step_{c+1} 到下一刻的间隔。节奏 100% 由数据包(命令)控制, 在原地直接触发。
  - 音色/音高: 音符盒坐映射块(模组读它定音色)+ note 档移调(同所有 A 家族)。声音仍以玩家为中心。
  - 复音增益/微抖动 开关(rpcfg)保留; [播放]/[停止]/[循环]。tick80。
需 RedPiano 模组 + qzpno 资源包。Run: python 38_build_cmdplayer.py [notes.json] [NS] [OX] [COLS]
"""
import os, sys, json, shutil
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = sys.argv[1] if len(sys.argv) > 1 else 'notes_wll.json'
NS = sys.argv[2] if len(sys.argv) > 2 else 'wllc'
OX = int(sys.argv[3]) if len(sys.argv) > 3 else 300
COLS = int(sys.argv[4]) if len(sys.argv) > 4 else 24       # 网格宽(列折行) -> 紧凑原地
OZ, Y = 0, 255
VOICES, TPS = 8, 80                                         # 每刻最多 8 声部(原地无辐射限制)
U = 2 / TPS
SSTOP = 'stopsound @a'
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

# 量化 + 按刻成列(chord)
bycell = defaultdict(list)
for n in notes:
    if n['vel'] >= 0.04: bycell[round(n['t'] / U)].append(n)
ticks = sorted(bycell)
cols = []          # 每列: (tick, [(block,nv), ...])
dropped = 0
for t in ticks:
    g = sorted(bycell[t], key=lambda x: -x['midi'])
    cols.append((t, [map_note(n['midi'], n['vel']) for n in g[:VOICES]]))
    dropped += max(0, len(g) - VOICES)
NC = len(cols)
maxv = max(len(v) for _, v in cols)
ROWH = maxv + 2                                            # 每列网格行高(声部 + 间隔)

# 网格坐标: 列 c -> (gx=c%COLS, row=c//COLS); 世界 x=OX+gx, z=OZ+row*ROWH+voice
def col_pos(c):
    gx, row = c % COLS, c // COLS
    return OX + gx, OZ + row * ROWH
NROWS = (NC + COLS - 1) // COLS

occ = {}
def put(out, x, y, z, blk):
    k = (x, y, z)
    if k in occ and occ[k] != blk and 'air' not in (occ[k], blk): raise AssertionError(f"碰撞 @{k}: {occ[k]} vs {blk}")
    occ[k] = blk; out.append(f'setblock {x} {y} {z} {blk}')

build = ['gamerule commandModificationBlockLimit 2147483647']
trig_slots = []    # 所有红石块槽 (x,y,z) 用于清空
for c, (t, voices) in enumerate(cols):
    bx, bz = col_pos(c)
    for vi, (block, nv) in enumerate(voices):
        z = bz + vi
        put(build, bx, Y - 1, z, block)                                  # 音色映射块(被下方红石块强充)
        put(build, bx, Y, z, f'minecraft:note_block[note={nv}]')         # 真音符盒
        put(build, bx, Y + 1, z, 'air')                                  # 上方空气(发声必需)
        put(build, bx, Y - 2, z, 'air')                                  # 触发槽(放红石块=打响)
        trig_slots.append((bx, Y - 2, z))
BATCH = 2000
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]
allx = [k[0] for k in occ]; allz = [k[2] for k in occ]
WX0, WZ0, WX1, WZ1 = min(allx) - 2, min(allz) - 2, max(allx) + 2, max(allz) + 2

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 我泪 原地命令触发播放器(数据包按节奏点红石块, tick80)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

# forceload(紧凑, 只几十区块) —— 一条覆盖整阵
flbuild = [f'forceload add {WX0} {WZ0} {WX1} {WZ1}']
PULSE = 3
# step_c: 给该列每个音符盒下放红石块(打响) + schedule 下一列
for c, (t, voices) in enumerate(cols):
    bx, bz = col_pos(c)
    lines = [f'execute if score PLAY {NS} matches 0 run return 0']     # 停止后队列里残余 step 不再响
    lines += [f'setblock {bx} {Y-2} {bz+vi} minecraft:redstone_block' for vi in range(len(voices))]
    if c + 1 < NC:
        dt = (cols[c + 1][0] - t) * 2                       # 红石刻差 -> 游戏刻(tick80: *2)
        lines.append(f'execute if score PLAY {NS} matches 1 run schedule function {NS}:s/s{c+1} {max(1, dt)}t')
    else:
        lines.append(f'schedule function {NS}:done {200}t')
    wf(f's/s{c}', lines)
T0 = cols[0][0] * 2
MUSIC_TICKS = (ticks[-1] + 1) * 2

# 清红石块(分段, 防一函数过大)
CLRSEG = 1500
clr_funcs = []
for i in range(0, len(trig_slots), CLRSEG):
    seg = trig_slots[i:i + CLRSEG]
    name = f'clr/c{i//CLRSEG}'
    wf(name, [f'setblock {x} {y} {z} minecraft:air' for (x, y, z) in seg])
    clr_funcs.append(f'function {NS}:{name}')

PBX = OX - 3
def lbtn(bx, cmd, lines):
    msgs = ','.join('\'{"text":"%s"}\'' % s for s in (list(lines) + ['', '', '', ''])[:4])   # ★ 必须 4 行
    return [f'setblock {bx} {Y-1} {OZ} minecraft:redstone_lamp',
            f'setblock {bx} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"{cmd}",auto:0b}}',
            f'setblock {bx} {Y+1} {OZ} minecraft:stone_button[face=floor]',
            f'setblock {bx} {Y-1} {OZ-2} minecraft:redstone_lamp',
            'setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}' % (bx, Y, OZ-2, msgs)]
ctl = ['gamerule commandModificationBlockLimit 2147483647']
ctl += lbtn(PBX,   f'function {NS}:play',           ['[播放]', '原地命令', '触发, 放一遍'])
ctl += lbtn(PBX-2, f'function {NS}:loop',           ['[循环播放]', '放完自动重放'])
ctl += lbtn(PBX-4, f'function {NS}:stop',           ['[停止]', '立即静音'])
ctl += lbtn(PBX-6, f'function {NS}:cfg/polytoggle', ['[复音增益]', '大和弦防糊'])
ctl += lbtn(PBX-8, f'function {NS}:cfg/humantoggle',['[微抖动]', '去复印感'])

RESET = [f'scoreboard players set PLAY {NS} 0', f'scoreboard players set LOOP {NS} 0']
wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1'] + RESET
   + ['scoreboard objectives add rpcfg dummy', 'scoreboard players set poly rpcfg 1', 'scoreboard players set human rpcfg 1',
      'forceload remove all', f'schedule clear {NS}:done']
   + [f'tellraw @a ["",{{"text":"[{NS}] 我泪 原地命令播放器 loaded. ","color":"aqua"}},{{"text":"需模组+qzpno. /tick rate 80 -> /function {NS}:setup"}}]'])
wf('setup', RESET + ['gamemode creative @a', SSTOP] + flbuild + [f'tp @a {PBX} {Y+3} {OZ}',
   f'scoreboard players set BLD {NS} 0', f'tellraw @a "[{NS}] forceload+building (原地阵 {NC}列x{maxv}声部, {COLS}宽{NROWS}行)..."'])
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('tick', bs)        # 建造分批(BLD 计数); 播放用 schedule 链, 不占 tick
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
wf('placectl', ctl)
wf('builddone', f'scoreboard players set BLD {NS} -1\nfunction {NS}:placectl\n'
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"原地阵 {COLS}x{NROWS*ROWH}格(无中继器=不过载). 按[播放]/[循环播放]/[停止]"}}]')
wf('playcore', [f'scoreboard players set PLAY {NS} 1', SSTOP] + clr_funcs + [f'schedule function {NS}:s/s0 {max(1,T0)}t'])
wf('play', [f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先[停止]"',
            f'scoreboard players set LOOP {NS} 0', f'function {NS}:playcore',
            f'tellraw @a "[{NS}] 播放(原地命令触发, 不过载)。站着听。"'])
wf('loop', [f'execute if score PLAY {NS} matches 1 run scoreboard players set LOOP {NS} 1',
            f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 已转循环。"',
            f'scoreboard players set LOOP {NS} 1', f'function {NS}:playcore', f'tellraw @a "[{NS}] 循环播放。"'])
wf('done', [f'execute if score LOOP {NS} matches 1 run function {NS}:playcore',
            f'execute if score LOOP {NS} matches 0 run scoreboard players set PLAY {NS} 0',
            f'execute if score LOOP {NS} matches 0 run tellraw @a "[{NS}] (一遍结束)。"'])
wf('stop', RESET + ['gamemode creative @a', SSTOP, f'schedule clear {NS}:done'] + clr_funcs
   + [f'tp @a {PBX} {Y+3} {OZ}', f'tellraw @a "[{NS}] 已停止(立即静音)。"'])
wf('cfg/polytoggle', ['scoreboard players set rptmp rpcfg 1', 'scoreboard players operation rptmp rpcfg -= poly rpcfg',
                      'scoreboard players operation poly rpcfg = rptmp rpcfg',
                      f'execute if score poly rpcfg matches 1 run tellraw @a "[{NS}] 复音增益 ON"',
                      f'execute if score poly rpcfg matches 0 run tellraw @a "[{NS}] 复音增益 OFF"'])
wf('cfg/humantoggle', ['scoreboard players set rptmp rpcfg 1', 'scoreboard players operation rptmp rpcfg -= human rpcfg',
                       'scoreboard players operation human rpcfg = rptmp rpcfg',
                       f'execute if score human rpcfg matches 1 run tellraw @a "[{NS}] 微抖动 ON"',
                       f'execute if score human rpcfg matches 0 run tellraw @a "[{NS}] 微抖动 OFF"'])
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647'] + RESET + ['gamemode creative @a', SSTOP,
               f'schedule clear {NS}:done', f'fill {WX0} {Y-2} {WZ0} {WX1} {Y+1} {WZ1} air', 'forceload remove all',
               f'tellraw @a "[{NS}] cleaned up."'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 38 我泪 原地命令触发播放器 ===')
print(f'曲子={NOTES} 发声音={sum(len(v) for _,v in cols)} dropped={dropped} 钳音={clamped[0]} 最大复音={maxv}')
print(f'原地阵: {NC}列 -> 网格 {COLS}宽 x {NROWS}行 x {ROWH}(行高); 占地 x[{WX0}..{WX1}]={WX1-WX0} z[{WZ0}..{WZ1}]={WZ1-WZ0}')
print(f'★无中继器/无行进脉冲 -> forceload 仅 ~{((WX1-WX0)//16+1)*((WZ1-WZ0)//16+1)} 区块 -> 不过载')
print(f'触发: {NC}个 step 函数(schedule链), 数据包按节奏在原地点红石块。批次={len(batches)}; 无碰撞✓')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> [播放]/[循环播放]/[停止]')
