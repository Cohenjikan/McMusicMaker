# -*- coding: utf-8 -*-
"""45_build_inplace_palette.py — 任务4(修正版): 调色板音符盒 + 侧面红石块反复触发 的本地原地播放器。

★ 用户在游戏里实测 38/44 播放失败, 给出两条根本修正:
  1) 红石块必须放在【音符盒侧面】直接给音符盒供电。放在底部(隔着音色映射块)不触发 ——
     红石块不会"强充"相邻不透明方块再把电传导到对面的机械, 所以 38/44 的"红石块垫在映射块下"
     这一几何是无效的(音符盒从未被点亮)。改为: 红石块放在音符盒同 Y 的侧面槽, 直接相邻 -> 上升沿发声。
  2) 不要把整张谱子(每个音符事件一个音符盒)铺出来; 只铺【全曲用到的不同音】= 一个调色板,
     同一个音反复触发同一个音符盒。春娇全曲只有 33 个不同音 -> 33 个音符盒(对比铺全谱 1231 个)。

机制:
  - 调色板: 全曲唯一 (音色映射块, note值) 各一个音符盒。音符盒坐映射块上(Y-1, 模组读它定音色),
    上方空气(Y+1, 发声必需), 侧面(Z-1)留一个空气【触发槽】。
  - 触发: 数据包 schedule 链。每个发声刻 s{c}: 给该和弦用到的调色板音符盒【侧面槽 setblock 红石块】
    (空气->红石 = 上升沿 = 响), 并 schedule offall(+1 游戏刻)把所有触发槽清回空气 = 为下次上升沿复位。
    清空气不会截断声音(采样时长由模组控制), 只是松开"按键"。
  - 反复触发: 每次都是干净的 空气->红石 上升沿, 同一个音符盒可被无限次重新打响。相邻刻 dt>=2 游戏刻,
    offall(+1t) 必在下一次按下(>=+2t)之前完成复位。
  - 占地: 调色板仅几十音符盒 -> forceload 仅几区块 -> 远小于铺全谱, 彻底不过载。声音以玩家为中心(模组)。
需 RedPiano 模组 + qzpno 资源包。
Run: python 45_build_inplace_palette.py <song.mid|notes.json> [NS] [OX] [PCOLS] [--name 显示名]
"""
import os, sys, json, shutil
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))

argv = sys.argv[1:]
NAME = None
if '--name' in argv:
    i = argv.index('--name'); NAME = argv[i + 1]; del argv[i:i + 2]
SRC   = argv[0] if len(argv) > 0 else 'notes_cjzm.json'
NS    = argv[1] if len(argv) > 1 else 'cjzmc'
OX    = int(argv[2]) if len(argv) > 2 else 340000
PCOLS = int(argv[3]) if len(argv) > 3 else 16     # 调色板网格宽
OZ, Y = 0, 255
VOICES, TPS = 12, 80                              # 每刻发声上限(调色板复用, 不再受布局限制)
ROWGAP = 3                                        # 调色板相邻行 Z 间距(>=3 保证触发槽不误触相邻行音符盒)
U = 2 / TPS
SSTOP = 'stopsound @a'
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界 (1)/datapacks"
# 38/44 旧"铺全谱"破机器曾建在 X=330000 一带, 这里清掉它的占地(分 2 段, 避开 /fill 32768 上限)
OLD_FILLS = ['fill 329996 253 -4 330027 257 100 air', 'fill 329996 253 101 330027 257 205 air']

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
if SRC.lower().endswith(('.mid', '.midi')):
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

# 量化成刻, 建调色板(唯一 (block, nv)), 每刻和弦 = 用到的调色板索引集合
bycell = defaultdict(list)
for n in notes:
    if n['vel'] >= 0.04: bycell[round(n['t'] / U)].append(n)
ticks = sorted(bycell)
palette = {}            # (block, nv) -> 索引
order = []              # 索引 -> (block, nv)
beats = []              # (tick, [palette_idx, ...])
dropped = 0
for t in ticks:
    g = sorted(bycell[t], key=lambda x: -x['midi'])[:VOICES]
    dropped += max(0, len(bycell[t]) - VOICES)
    idxs = []
    for n in g:
        key = map_note(n['midi'], n['vel'])
        if key not in palette:
            palette[key] = len(order); order.append(key)
        idxs.append(palette[key])
    beats.append((t, sorted(set(idxs))))          # 同刻同音去重 -> 一次触发
P = len(order); NB = len(beats)

# 调色板布局: 索引 i -> (col=i%PCOLS, row=i//PCOLS); 音符盒 (x,Y,z), 触发槽 (x,Y,z-1)
def pal_pos(i):
    col, row = i % PCOLS, i // PCOLS
    return OX + col, OZ + row * ROWGAP
PROWS = (P + PCOLS - 1) // PCOLS

occ = {}
def put(out, x, y, z, blk):
    k = (x, y, z)
    if k in occ and occ[k] != blk and 'air' not in (occ[k], blk): raise AssertionError(f"碰撞 @{k}: {occ[k]} vs {blk}")
    occ[k] = blk; out.append(f'setblock {x} {y} {z} {blk}')

build = ['gamerule commandModificationBlockLimit 2147483647']
for i, (block, nv) in enumerate(order):
    x, z = pal_pos(i)
    put(build, x, Y - 1, z, block)                              # 音色映射块(模组读它定音色)
    put(build, x, Y,     z, f'minecraft:note_block[note={nv}]') # 真音符盒
    put(build, x, Y + 1, z, 'air')                              # 上方空气(发声必需)
    put(build, x, Y,     z - 1, 'air')                          # ★ 侧面触发槽(放红石块=打响)
def trig(i):
    x, z = pal_pos(i); return (x, Y, z - 1)

BATCH = 2000
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]
allx = [k[0] for k in occ]; allz = [k[2] for k in occ]
PBX = OX - 3                                                    # 控制台 x(在调色板左侧)
WX0, WZ0 = min(min(allx), PBX - 10) - 2, min(min(allz), OZ - 3) - 2
WX1, WZ1 = max(allx) + 2, max(allz) + 2

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} {NAME} 原地调色板播放器(侧面红石块反复触发, tick80)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

flbuild = [f'forceload add {WX0} {WZ0} {WX1} {WZ1}']
# offall: 清所有触发槽回空气(复位上升沿)
wf('offall', [f'setblock {x} {y} {z} minecraft:air' for (x, y, z) in (trig(i) for i in range(P))])
# step 链: 按下该刻和弦 -> 1t 后 offall 松开 -> dt 后下一刻
for c, (t, idxs) in enumerate(beats):
    lines = [f'execute if score PLAY {NS} matches 0 run return 0']
    lines += [f'setblock {x} {y} {z} minecraft:redstone_block' for (x, y, z) in (trig(i) for i in idxs)]
    lines.append(f'execute if score PLAY {NS} matches 1 run schedule function {NS}:offall 1t')
    if c + 1 < NB:
        dt = (beats[c + 1][0] - t) * 2                  # 红石刻差->游戏刻(tick80:*2); 必 >=2
        lines.append(f'execute if score PLAY {NS} matches 1 run schedule function {NS}:s/s{c+1} {dt}t')
    else:
        lines.append(f'schedule function {NS}:done 200t')
    wf(f's/s{c}', lines)
T0 = beats[0][0] * 2

def lbtn(bx, cmd, lines):
    msgs = ','.join('\'{"text":"%s"}\'' % s for s in (list(lines) + ['', '', '', ''])[:4])   # ★ 必须 4 行
    return [f'setblock {bx} {Y-1} {OZ} minecraft:redstone_lamp',
            f'setblock {bx} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"{cmd}",auto:0b}}',
            f'setblock {bx} {Y+1} {OZ} minecraft:stone_button[face=floor]',
            f'setblock {bx} {Y-1} {OZ-2} minecraft:redstone_lamp',
            'setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}' % (bx, Y, OZ-2, msgs)]
ctl = ['gamerule commandModificationBlockLimit 2147483647']
ctl += lbtn(PBX,   f'function {NS}:play',           ['[播放]', '调色板', '侧触发, 放一遍'])
ctl += lbtn(PBX-2, f'function {NS}:loop',           ['[循环播放]', '放完自动重放'])
ctl += lbtn(PBX-4, f'function {NS}:stop',           ['[停止]', '立即静音'])
ctl += lbtn(PBX-6, f'function {NS}:cfg/polytoggle', ['[复音增益]', '大和弦防糊'])
ctl += lbtn(PBX-8, f'function {NS}:cfg/humantoggle',['[微抖动]', '去复印感'])

RESET = [f'scoreboard players set PLAY {NS} 0', f'scoreboard players set LOOP {NS} 0']
wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1'] + RESET
   + ['scoreboard objectives add rpcfg dummy', 'scoreboard players set poly rpcfg 1', 'scoreboard players set human rpcfg 1',
      'forceload remove all', f'schedule clear {NS}:done']
   + [f'tellraw @a ["",{{"text":"[{NS}] {NAME} 原地调色板播放器 loaded. ","color":"aqua"}},{{"text":"需模组+qzpno. /tick rate 80 -> /function {NS}:setup"}}]'])
wf('setup', RESET + ['gamemode creative @a', SSTOP, 'forceload remove all'] + flbuild + [f'tp @a {PBX} {Y+3} {OZ}',
   f'scoreboard players set BLD {NS} 0', f'tellraw @a "[{NS}] forceload+building (调色板 {P}音 {PCOLS}宽{PROWS}行)..."'])
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('tick', bs)
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
wf('placectl', ctl)
wf('builddone', f'scoreboard players set BLD {NS} -1\nfunction {NS}:placectl\n'
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"调色板 {P}音符盒(侧面触发,不过载). 按[播放]/[循环播放]/[停止]"}}]')
wf('playcore', [f'scoreboard players set PLAY {NS} 1', SSTOP, f'function {NS}:offall',
                f'schedule function {NS}:s/s0 {max(1,T0)}t'])
wf('play', [f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先[停止]"',
            f'scoreboard players set LOOP {NS} 0', f'function {NS}:playcore',
            f'tellraw @a "[{NS}] 播放(调色板侧面触发, 不过载)。站着听。"'])
wf('loop', [f'execute if score PLAY {NS} matches 1 run scoreboard players set LOOP {NS} 1',
            f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 已转循环。"',
            f'scoreboard players set LOOP {NS} 1', f'function {NS}:playcore', f'tellraw @a "[{NS}] 循环播放。"'])
wf('done', [f'execute if score LOOP {NS} matches 1 run function {NS}:playcore',
            f'execute if score LOOP {NS} matches 0 run scoreboard players set PLAY {NS} 0',
            f'execute if score LOOP {NS} matches 0 run function {NS}:offall',
            f'execute if score LOOP {NS} matches 0 run tellraw @a "[{NS}] (一遍结束)。"'])
wf('stop', RESET + ['gamemode creative @a', SSTOP, f'schedule clear {NS}:done', f'function {NS}:offall']
   + [f'tp @a {PBX} {Y+3} {OZ}', f'tellraw @a "[{NS}] 已停止(立即静音)。"'])
wf('cfg/polytoggle', ['scoreboard players set rptmp rpcfg 1', 'scoreboard players operation rptmp rpcfg -= poly rpcfg',
                      'scoreboard players operation poly rpcfg = rptmp rpcfg',
                      f'execute if score poly rpcfg matches 1 run tellraw @a "[{NS}] 复音增益 ON"',
                      f'execute if score poly rpcfg matches 0 run tellraw @a "[{NS}] 复音增益 OFF"'])
wf('cfg/humantoggle', ['scoreboard players set rptmp rpcfg 1', 'scoreboard players operation rptmp rpcfg -= human rpcfg',
                       'scoreboard players operation human rpcfg = rptmp rpcfg',
                       f'execute if score human rpcfg matches 1 run tellraw @a "[{NS}] 微抖动 ON"',
                       f'execute if score human rpcfg matches 0 run tellraw @a "[{NS}] 微抖动 OFF"'])
# cleanup: 清新机器 + 顺带抹掉 38/44 留在 330000 的旧破机器
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647'] + RESET + ['gamemode creative @a', SSTOP,
               f'schedule clear {NS}:done', f'fill {WX0} {Y-2} {WZ0} {WX1} {Y+1} {WZ1} air'] + OLD_FILLS
               + ['forceload remove all', f'tellraw @a "[{NS}] cleaned up (含旧 330000 破机器)。"'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)

triggers = sum(len(idxs) for _, idxs in beats)
chunks = ((WX1 - WX0) // 16 + 1) * ((WZ1 - WZ0) // 16 + 1)
song_s = (ticks[-1] - ticks[0]) * U
HAND = f"""# {NS} — 原地调色板红石音乐播放器(任务4·修正版) 交接文档

- 曲目: **{NAME}**  (源: `{os.path.basename(SRC)}`)
- 生成脚本: `poc/45_build_inplace_palette.py`
- 形态: 本地原地 / 调色板 / **侧面红石块反复触发**(零中继器, 零行进脉冲)
- 命名空间/坐标: `{NS}` @ X={OX}, Z={OZ}, Y={Y}

## 对 38/44 的根本修正(用户游戏实测)
1. 红石块放【音符盒侧面】直接供电(38/44 放底部隔着映射块 -> 不触发, 已废弃)。
2. 只铺【用到的不同音】= 调色板, 同音反复触发同一个音符盒(本曲 {P} 音符盒, 对比铺全谱 {len(notes)} 个)。

## 指标
| 项 | 值 |
|---|---|
| 调色板音符盒 | **{P}** (唯一音; dropped={dropped}, 钳音={clamped[0]}) |
| 发声刻(beat) | {NB};  总触发次数 {triggers} |
| 复音上限 | {VOICES} |
| 网格 | {PCOLS} 宽 x {PROWS} 行 (行距 {ROWGAP}) |
| 占地 | X[{WX0}..{WX1}], Z[{WZ0}..{WZ1}] |
| **forceload 区块** | **~{chunks}** (极小 -> 不过载) |
| 曲长 | ~{song_s:.1f}s @ /tick rate 80 |
| step 函数 | {NB} (schedule 链) + offall(复位) |

## 触发时序(反复触发的关键)
- s{{c}}: 该刻和弦音符盒侧槽 `setblock redstone_block`(空气->红石=上升沿=响)。
- +1t: `offall` 把所有触发槽清回空气(松开按键, 不截断采样)。
- +dt(>=2t): 下一刻 s{{c+1}} 再按下 -> 干净上升沿 -> 同音可无限重触发。

## 依赖
- RedPiano 模组 (`mod/redpiano/`, jar 在 mods/)
- qzpno 资源包 (`qzpno_mv.zip`, 选项->资源包 启用)

## MC 测试命令
```
/reload
/tick rate 80
/function {NS}:setup        # 等绿字 "built"(会 tp 你到控制台)
# 按牌子: [播放] / [循环播放] / [停止]
/function {NS}:cleanup      # 收尾: 抹本机 + 旧 330000 破机器 + 解除 forceload
```
"""
open(os.path.join(DP, f'{NS}_HANDOFF.md'), 'w', encoding='utf-8', newline='\n').write(HAND)

print(f'=== 45 原地调色板播放器 [{NAME}] ===')
print(f'源={os.path.basename(SRC)} 调色板={P}音符盒 (vs 铺全谱{len(notes)}) dropped={dropped} 钳音={clamped[0]}')
print(f'发声刻={NB} 总触发={triggers}; 网格 {PCOLS}宽x{PROWS}行(行距{ROWGAP}); 占地 x[{WX0}..{WX1}] z[{WZ0}..{WZ1}]')
print(f'★侧面红石块触发 + offall复位 -> 同音反复触发; forceload 仅 ~{chunks} 区块 -> 不过载')
print(f'曲长 ~{song_s:.1f}s; 批次={len(batches)}; 无碰撞✓')
print(f'部署 -> {dst}')
print(f'交接文档 -> build/{NS}/{NS}_HANDOFF.md')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> [播放]/[循环播放]/[停止]')
