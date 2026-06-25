# -*- coding: utf-8 -*-
"""44_build_inplace.py — 路线图【任务4】本地原地红石音乐播放器(稳定能力层)。

这是把 37/38(wllc)那套【命令方块红石块直接触发的本地播放器】沉淀成的**通用、稳定、可复用**能力层:
  - 占地小、零中继器、零行进脉冲 -> forceload 仅几十区块 -> 从根上规避"服务器过载/音频丢失"。
  - 适合作为**保底播放方案**:任何机器形态(直线/曲折直线)若因规模过载断音, 都可回落到本播放器。

与 38 的差异(只做"稳定能力层"必要的泛化, 发声/触发机制逐字不变):
  - **歌名参数化**: 38 把"我泪"硬编码进所有 tellraw/描述; 本脚本用 --name(或从文件名推断), 不再串歌名。
  - **可直接吃 .mid**: 入参既可是 notes.json, 也可以直接是 .mid(内部按 poly/全声道解析, 等价 midi_to_notes --poly)。
  - **自动产出交接文档**: build/<NS>_HANDOFF.md(指标 + MC 测试命令), 对齐 skill 的"测试命令+交接文档"产物。

机制(与 38 一致, 已实测稳定):
  - 紧凑音符盒阵(原地): 每个发声刻 = 一列, 列里每声部一个音符盒(坐其音色映射块上, 上方空气)。
    列按 COLS 宽折行 -> 占地极小。
  - 触发: 数据包 schedule 链 s/s0->s1->...; step_c 到点就给该列每个音符盒【下方放红石块】(强充映射块->音符盒响),
    并 schedule 下一刻。节奏 100% 由数据包控制, 在原地直接触发, 无行进脉冲、无中继器。
  - 音色/音高: 音符盒坐映射块(模组读它定音色)+ note 档移调。声音以玩家为中心(模组)。
  - 复音增益/微抖动 开关(rpcfg)保留; [播放]/[循环播放]/[停止]。tick80。
需 RedPiano 模组 + qzpno 资源包。
Run: python 44_build_inplace.py <song.mid|notes.json> [NS] [OX] [COLS] [--name 显示名]
"""
import os, sys, json, shutil
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))

# ---- 参数 ----
argv = sys.argv[1:]
NAME = None
if '--name' in argv:
    i = argv.index('--name'); NAME = argv[i + 1]; del argv[i:i + 2]
SRC  = argv[0] if len(argv) > 0 else 'notes_cjzm.json'
NS   = argv[1] if len(argv) > 1 else 'cjzmc'
OX   = int(argv[2]) if len(argv) > 2 else 330000
COLS = int(argv[3]) if len(argv) > 3 else 24            # 网格宽(列折行) -> 紧凑原地
OZ, Y = 0, 255
VOICES, TPS = 8, 80                                     # 每刻最多 8 声部(原地无辐射限制)
U = 2 / TPS
SSTOP = 'stopsound @a'
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界 (1)/datapacks"

# ---- 入口:.mid 直接解析(poly/全声道), 或读 notes.json ----
def parse_midi(path):
    import mido
    mf = mido.MidiFile(path); active = {}; t = 0.0; ev = []
    for msg in mf:
        t += msg.time
        if msg.type == 'note_on' and msg.velocity > 0:
            active[(msg.channel, msg.note)] = (t, msg.velocity)
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            k = (msg.channel, msg.note)
            if k in active:
                st, v = active.pop(k)
                ev.append({'t': round(st, 3), 'midi': int(msg.note),
                           'dur': round(max(t - st, 0.02), 3), 'vel': round(v / 127.0, 3)})
    ev.sort(key=lambda e: e['t'])
    return ev

srcpath = SRC if os.path.isabs(SRC) else os.path.join(HERE, SRC)
if SRC.lower().endswith('.mid') or SRC.lower().endswith('.midi'):
    notes = parse_midi(srcpath)
    if NAME is None: NAME = os.path.splitext(os.path.basename(SRC))[0]
else:
    notes = json.load(open(srcpath, encoding='utf-8'))['notes']
    if NAME is None: NAME = os.path.splitext(os.path.basename(SRC))[0]

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
json.dump({"pack": {"pack_format": 81, "description": f"{NS} {NAME} 原地命令触发播放器(数据包按节奏点红石块, tick80)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

# forceload(紧凑, 只几十区块) —— 一条覆盖整阵
flbuild = [f'forceload add {WX0} {WZ0} {WX1} {WZ1}']
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
   + [f'tellraw @a ["",{{"text":"[{NS}] {NAME} 原地命令播放器 loaded. ","color":"aqua"}},{{"text":"需模组+qzpno. /tick rate 80 -> /function {NS}:setup"}}]'])
wf('setup', RESET + ['gamemode creative @a', SSTOP, 'forceload remove all'] + flbuild + [f'tp @a {PBX} {Y+3} {OZ}',
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

# ---- 交接文档(指标 + MC 测试命令)----
sounding = sum(len(v) for _, v in cols)
chunks = ((WX1 - WX0) // 16 + 1) * ((WZ1 - WZ0) // 16 + 1)
song_s = (ticks[-1] - ticks[0]) * U
HAND = f"""# {NS} — 原地红石音乐播放器(任务4) 交接文档

- 曲目: **{NAME}**  (源: `{os.path.basename(SRC)}`)
- 生成脚本: `poc/44_build_inplace.py`
- 形态: 本地原地命令触发(命令方块红石块直接打响音符盒, 零中继器, 零行进脉冲)
- 命名空间/坐标: `{NS}` @ X={OX}, Z={OZ}, Y={Y}

## 指标
| 项 | 值 |
|---|---|
| 发声音符 | {sounding} (dropped={dropped}, 钳音={clamped[0]}) |
| 发声刻(列) | {NC} |
| 最大复音 | {maxv} (每刻上限 {VOICES}) |
| 网格 | {COLS} 宽 x {NROWS} 行 x {ROWH} 行高 |
| 占地 | X[{WX0}..{WX1}]={WX1-WX0}, Z[{WZ0}..{WZ1}]={WZ1-WZ0} |
| **forceload 区块** | **~{chunks}** (紧凑 -> 不过载) |
| 曲长 | ~{song_s:.1f}s @ /tick rate 80 |
| step 函数 | {NC} (schedule 链), 建造批次 {len(batches)} |

## 依赖
- RedPiano 模组 (`mod/redpiano/`, jar 在 mods/)
- qzpno 资源包 (`qzpno_mv.zip`, 选项->资源包 启用)

## MC 测试命令
```
/reload
/tick rate 80
/function {NS}:setup        # 等绿字 "built"(会 tp 你到控制台)
# 按牌子: [播放] / [循环播放] / [停止] / [复音增益] / [微抖动]
# 收尾: /function {NS}:cleanup  (抹掉机器 + 解除 forceload)
```
"""
open(os.path.join(DP, f'{NS}_HANDOFF.md'), 'w', encoding='utf-8', newline='\n').write(HAND)

print(f'=== 44 原地命令触发播放器 [{NAME}] ===')
print(f'源={os.path.basename(SRC)} 发声音={sounding} dropped={dropped} 钳音={clamped[0]} 最大复音={maxv}')
print(f'原地阵: {NC}列 -> 网格 {COLS}宽 x {NROWS}行 x {ROWH}(行高); 占地 x[{WX0}..{WX1}]={WX1-WX0} z[{WZ0}..{WZ1}]={WZ1-WZ0}')
print(f'★无中继器/无行进脉冲 -> forceload 仅 ~{chunks} 区块 -> 不过载')
print(f'触发: {NC}个 step 函数(schedule链); 曲长 ~{song_s:.1f}s; 批次={len(batches)}; 无碰撞✓')
print(f'部署 -> {dst}')
print(f'交接文档 -> build/{NS}/{NS}_HANDOFF.md')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> [播放]/[循环播放]/[停止]')
