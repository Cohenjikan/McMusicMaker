# -*- coding: utf-8 -*-
"""46_build_inplace_multi.py — 任务5: 多乐器 原地调色板播放器(自动按 GM 家族分配音色)。

在 45(原地调色板 + 侧面红石块反复触发, 已实测稳定)基础上扩成**多乐器**:
  - 直接解析 .mid, 按通道的 program_change 给每个音符打上乐器标签;
  - **GM 家族 -> 采样集** 自动分配(`redpiano_map_multi.json` 的 family_map, 用户选"自动映射"):
    program//8 = 家族(0钢琴/4贝斯/10合成主音/11合成铺底...), ch9 = 鼓;
  - 每个乐器有自己的一组音色映射块(模组 RedPianoMap.java 已 wired 103 块: pno/bass/lead/pad/drum);
  - 调色板按 **(映射块, note值)** 去重, piano/voice/bass... 各自的块共用同一套侧面触发/复位时序。
发声/触发机制与 45 逐字一致(只把单一钢琴映射换成 per-note 多乐器映射)。
需 RedPiano 模组 + qzpno 资源包。先跑 `gen_multi_map.py` 生成 `redpiano_map_multi.json`。
Run: python 46_build_inplace_multi.py <song.mid> [NS] [OX] [PCOLS] [--name 显示名]
"""
import sys, os, json
import mido
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
import shutil

argv = sys.argv[1:]
NAME = None
if '--name' in argv:
    i = argv.index('--name'); NAME = argv[i + 1]; del argv[i:i + 2]
SRC   = argv[0] if len(argv) > 0 else 'C:/Users/Cohen/Downloads/七里香 周杰伦_爱给网_aigei_com.mid'
NS    = argv[1] if len(argv) > 1 else 'qlxm'
OX    = int(argv[2]) if len(argv) > 2 else 350000
PCOLS = int(argv[3]) if len(argv) > 3 else 16
OZ, Y = 0, 255
VOICES, TPS = 12, 80
ROWGAP = 3
U = 2 / TPS
SSTOP = 'stopsound @a'
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界 (1)/datapacks"
if NAME is None: NAME = os.path.splitext(os.path.basename(SRC))[0]

MM = json.load(open(os.path.join(HERE, 'redpiano_map_multi.json'), encoding='utf-8'))
FAMILY = {int(k): v for k, v in MM['family_map'].items()}
GDRUM  = {int(k): v for k, v in MM['gm_drum_map'].items()}
INSTR  = MM['instruments']
clamped = [0]

def map_note_multi(midi, vel, instr):
    inst = INSTR[instr]
    if not inst['pitched']:                                   # 鼓: GM note -> 鼓型, 不移调(nv=12 -> pitch 1.0)
        dtype = GDRUM.get(midi, 'snare')
        if dtype not in inst['types']: dtype = next(iter(inst['types']))
        return inst['types'][dtype], 12
    bands = inst['bands']
    band = min(bands, key=lambda b: abs(b - midi)); raw = 12 + (midi - band)
    nv = max(0, min(24, raw))
    if not (0 <= raw <= 24): clamped[0] += 1
    layer = ('p' if vel < 0.40 else ('mf' if vel < 0.72 else 'f')) if instr == 'pno' else 'mf'
    if layer not in inst['layers']: layer = 'mf' if 'mf' in inst['layers'] else inst['layers'][0]
    return inst['block'][f'{band}_{layer}'], nv

# 解析 .mid: 跟踪每通道 program, 给每个音符打乐器标签
mf = mido.MidiFile(SRC); cur_prog = defaultdict(int); active = {}; t = 0.0; notes = []
for msg in mf:
    t += msg.time
    if msg.type == 'program_change':
        cur_prog[msg.channel] = msg.program
    elif msg.type == 'note_on' and msg.velocity > 0:
        active[(msg.channel, msg.note)] = (t, msg.velocity)
    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
        k = (msg.channel, msg.note)
        if k in active:
            st, v = active.pop(k); ch = msg.channel
            instr = 'drum' if ch == 9 else FAMILY.get(cur_prog[ch] // 8, 'pno')
            notes.append({'t': round(st, 3), 'midi': int(msg.note), 'vel': round(v / 127.0, 3),
                          'instr': instr, 'ch': ch, 'prog': cur_prog[ch]})
notes.sort(key=lambda n: n['t'])

# per-part 统计(报告用)
partstat = defaultdict(lambda: {'notes': 0, 'instr': None, 'lo': 999, 'hi': -1})
for n in notes:
    ps = partstat[(n['ch'], n['prog'])]; ps['notes'] += 1; ps['instr'] = n['instr']
    ps['lo'] = min(ps['lo'], n['midi']); ps['hi'] = max(ps['hi'], n['midi'])

# 量化成刻, 建跨乐器调色板, 每刻和弦 = 用到的调色板索引集合
bycell = defaultdict(list)
for n in notes:
    if n['vel'] >= 0.04: bycell[round(n['t'] / U)].append(n)
ticks = sorted(bycell)
palette = {}; order = []; beats = []; dropped = 0
pal_instr = []   # 索引 -> 乐器(报告用)
for tk in ticks:
    g = sorted(bycell[tk], key=lambda x: -x['midi'])[:VOICES]
    dropped += max(0, len(bycell[tk]) - VOICES)
    idxs = []
    for n in g:
        block, nv = map_note_multi(n['midi'], n['vel'], n['instr'])
        key = (block, nv)
        if key not in palette:
            palette[key] = len(order); order.append(key); pal_instr.append(n['instr'])
        idxs.append(palette[key])
    beats.append((tk, sorted(set(idxs))))
P = len(order); NB = len(beats)

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
    put(build, x, Y - 1, z, block)
    put(build, x, Y,     z, f'minecraft:note_block[note={nv}]')
    put(build, x, Y + 1, z, 'air')
    put(build, x, Y,     z - 1, 'air')
def trig(i):
    x, z = pal_pos(i); return (x, Y, z - 1)

BATCH = 2000
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]
allx = [k[0] for k in occ]; allz = [k[2] for k in occ]
PBX = OX - 3
WX0, WZ0 = min(min(allx), PBX - 10) - 2, min(min(allz), OZ - 3) - 2
WX1, WZ1 = max(allx) + 2, max(allz) + 2

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} {NAME} 多乐器原地调色板播放器(侧面触发, tick80)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

flbuild = [f'forceload add {WX0} {WZ0} {WX1} {WZ1}']
wf('offall', [f'setblock {x} {y} {z} minecraft:air' for (x, y, z) in (trig(i) for i in range(P))])
for c, (tk, idxs) in enumerate(beats):
    lines = [f'execute if score PLAY {NS} matches 0 run return 0']
    lines += [f'setblock {x} {y} {z} minecraft:redstone_block' for (x, y, z) in (trig(i) for i in idxs)]
    lines.append(f'execute if score PLAY {NS} matches 1 run schedule function {NS}:offall 1t')
    if c + 1 < NB:
        dt = (beats[c + 1][0] - tk) * 2
        lines.append(f'execute if score PLAY {NS} matches 1 run schedule function {NS}:s/s{c+1} {dt}t')
    else:
        lines.append(f'schedule function {NS}:done 200t')
    wf(f's/s{c}', lines)
T0 = beats[0][0] * 2

def lbtn(bx, cmd, lines):
    msgs = ','.join('\'{"text":"%s"}\'' % s for s in (list(lines) + ['', '', '', ''])[:4])
    return [f'setblock {bx} {Y-1} {OZ} minecraft:redstone_lamp',
            f'setblock {bx} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"{cmd}",auto:0b}}',
            f'setblock {bx} {Y+1} {OZ} minecraft:stone_button[face=floor]',
            f'setblock {bx} {Y-1} {OZ-2} minecraft:redstone_lamp',
            'setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}' % (bx, Y, OZ-2, msgs)]
ctl = ['gamerule commandModificationBlockLimit 2147483647']
ctl += lbtn(PBX,   f'function {NS}:play',           ['[播放]', '多乐器', '调色板'])
ctl += lbtn(PBX-2, f'function {NS}:loop',           ['[循环播放]', '放完自动重放'])
ctl += lbtn(PBX-4, f'function {NS}:stop',           ['[停止]', '立即静音'])
ctl += lbtn(PBX-6, f'function {NS}:cfg/polytoggle', ['[复音增益]', '大和弦防糊'])
ctl += lbtn(PBX-8, f'function {NS}:cfg/humantoggle',['[微抖动]', '去复印感'])

RESET = [f'scoreboard players set PLAY {NS} 0', f'scoreboard players set LOOP {NS} 0']
wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1'] + RESET
   + ['scoreboard objectives add rpcfg dummy', 'scoreboard players set poly rpcfg 1', 'scoreboard players set human rpcfg 1',
      'forceload remove all', f'schedule clear {NS}:done']
   + [f'tellraw @a ["",{{"text":"[{NS}] {NAME} 多乐器原地调色板 loaded. ","color":"aqua"}},{{"text":"需模组+qzpno. /tick rate 80 -> /function {NS}:setup"}}]'])
wf('setup', RESET + ['gamemode creative @a', SSTOP, 'forceload remove all'] + flbuild + [f'tp @a {PBX} {Y+3} {OZ}',
   f'scoreboard players set BLD {NS} 0', f'tellraw @a "[{NS}] forceload+building (调色板 {P}音 {PCOLS}宽{PROWS}行)..."'])
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('tick', bs)
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
wf('placectl', ctl)
wf('builddone', f'scoreboard players set BLD {NS} -1\nfunction {NS}:placectl\n'
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"多乐器调色板 {P}音符盒(侧面触发,不过载). 按[播放]"}}]')
wf('playcore', [f'scoreboard players set PLAY {NS} 1', SSTOP, f'function {NS}:offall',
                f'schedule function {NS}:s/s0 {max(1,T0)}t'])
wf('play', [f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先[停止]"',
            f'scoreboard players set LOOP {NS} 0', f'function {NS}:playcore',
            f'tellraw @a "[{NS}] 播放(多乐器原地, 不过载)。站着听。"'])
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
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647'] + RESET + ['gamemode creative @a', SSTOP,
               f'schedule clear {NS}:done', f'fill {WX0} {Y-2} {WZ0} {WX1} {Y+1} {WZ1} air', 'forceload remove all',
               f'tellraw @a "[{NS}] cleaned up。"'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)

# 报告 + 交接文档
triggers = sum(len(idxs) for _, idxs in beats)
chunks = ((WX1 - WX0) // 16 + 1) * ((WZ1 - WZ0) // 16 + 1)
song_s = (ticks[-1] - ticks[0]) * U
instr_pal = defaultdict(int)
for ins in pal_instr: instr_pal[ins] += 1
parts_lines = []
for (ch, prog) in sorted(partstat):
    ps = partstat[(ch, prog)]
    tag = '鼓' if ps['instr'] == 'drum' else ('钢琴' if ps['instr'] == 'pno' else '★非钢')
    parts_lines.append(f"  ch{ch:>2} program {prog:>3} -> 采样集 **{ps['instr']}** [{tag}], {ps['notes']} 音, 音域 {ps['lo']}-{ps['hi']}")

HAND = f"""# {NS} — 多乐器原地调色板播放器(任务5) 交接文档

- 曲目: **{NAME}**  (源: `{os.path.basename(SRC)}`)
- 生成脚本: `poc/46_build_inplace_multi.py`(基于 45 调色板 + 侧面触发, 扩多乐器)
- 命名空间/坐标: `{NS}` @ X={OX}, Z={OZ}, Y={Y}

## 声部 -> 采样集(按 GM 家族自动映射)
{chr(10).join(parts_lines)}

## 指标
| 项 | 值 |
|---|---|
| 跨乐器调色板 | **{P}** 音符盒 ({dict(instr_pal)}) |
| 发声刻 / 总触发 | {NB} / {triggers} (dropped={dropped}, 钳音={clamped[0]}) |
| 网格 / 占地 | {PCOLS}宽 x {PROWS}行;X[{WX0}..{WX1}], Z[{WZ0}..{WZ1}] |
| **forceload** | **~{chunks} 区块 -> 不过载** |
| 曲长 | ~{song_s:.1f}s @ /tick rate 80 |

## MC 测试命令(需 RedPiano 模组 + qzpno 资源包)
```
/reload
/tick rate 80
/function {NS}:setup        # 等绿字 "built"
# [播放] / [循环播放] / [停止]
/function {NS}:cleanup
```
> 音色由 GM 家族自动分配(family_map in redpiano_map_multi.json)。想改某声部音色, 调 family_map 重跑即可。
"""
open(os.path.join(DP, f'{NS}_HANDOFF.md'), 'w', encoding='utf-8', newline='\n').write(HAND)

print(f'=== 46 多乐器原地调色板 [{NAME}] ===')
for line in parts_lines: print(line.replace('**', '').replace('★', ''))
print(f'跨乐器调色板={P} 音符盒 {dict(instr_pal)}; 发声刻={NB} 总触发={triggers} dropped={dropped} 钳音={clamped[0]}')
print(f'网格 {PCOLS}宽x{PROWS}行; 占地 x[{WX0}..{WX1}] z[{WZ0}..{WZ1}]; forceload ~{chunks} 区块; 曲长 ~{song_s:.1f}s')
print(f'批次={len(batches)}; 无碰撞✓; 部署 -> {dst}')
print(f'交接文档 -> build/{NS}/{NS}_HANDOFF.md')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup -> [播放]')
