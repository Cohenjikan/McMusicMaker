# -*- coding: utf-8 -*-
"""33_build_band.py — 多乐器真音符盒乐队整机(Family A, tick80)。

把 24(单乐器共享骨架同步)推广到【多乐器乐队】: piano + bass + lead + pad + drums,
每件乐器自带音色(各自的映射块 + 资源包采样), 一起合奏《Do You Feel It》(dyf)。

同步核心(沿用 24): 所有乐器的音符量化到【同一 U 网格】, 取所有乐器触发刻的【并集】
  构成【唯一共享骨架】cells[](变延迟中继器压缩空隙)。每条 lane 铺【完全相同】的中继器链
  -> 脉冲逐刻到同一列 -> 全 lane 列对齐 + 绝对同步(发声列红石灯同时点亮成竖排)。

每件乐器分到一段【连续的 lane 区(Z 带)】, 形成可见的乐器分区:
  piano -> bass -> lead -> pad -> drums。每件乐器每刻按复音上限(piano6/lead3/pad2/bass1/drums3)
  分配同刻并发音到它的多条 lane, 超出丢弃并计数。

发声列(同 24 的音符路径): 有音 = 映射导体块(被前中继器强充能)在 Y, 音符盒[note=nv] 在 Y+1,
  空气在 Y+2, 红石灯在 Y-1; 无音 = 纯石导体直通(0 延迟)。Rep 列 = 石支撑 + 中继器[facing=west,delay]。

乐器音高映射:
  piano: band=bands 中最近, nv=clamp(12+(midi-band),0,24), layer 按 vel(p<0.40, mf<0.72, else f)。
  bass/lead/pad(pitched 单层 mf): band=该乐器 bands 中最近, nv=clamp(12+(midi-band),0,24),
    block=instruments[inst]['map'][f'{band}_mf']['block']。
  drums(perc): midi 是 GM 鼓键(36/38/42/...), 映射到 drums.keys 中最近键; 用该键的 block;
    音符盒 note=12(模组 getPitchFromNote(12)=1.0 => 不变调, 原样播鼓)。

需 RedPiano 模组 + qzpno 资源包。
Run: <venv python> 33_build_band.py
"""
import os, sys, json, shutil
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # Windows GBK 控制台

HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'dyfb'
OX, OZ = 75000, 0
Y = 255
LANE_DZ = 2                      # 每条 lane 占 1 排, 间隔 2(留 1 空防串扰), 同 24
LAMP, RFACING, BATCH = 'minecraft:redstone_lamp', 'west', 2000
PASS = 'minecraft:stone'         # 无音发声列的纯导体直通块
VEL_FLOOR = 0.04
TPS, PULSE = 80, 4               # tick80 = Family A
U = 2 / TPS                      # 0.025s = 1 红石刻
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界 (1)/datapacks"
DEPLOY_DST = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界 (1)/datapacks/dyfb"

# 乐器顺序 + 复音上限 + 输入文件
INSTRUMENTS = [                  # (name, notes_file, poly_cap)
    ('piano', 'notes_dyf_piano.json', 6),
    ('bass',  'notes_dyf_bass.json',  1),
    ('lead',  'notes_dyf_lead.json',  3),
    ('pad',   'notes_dyf_pad.json',   2),
    ('drums', 'notes_dyf_drums.json', 3),
]

# ---------------- 映射 ----------------
rp = json.load(open(os.path.join(HERE, 'redpiano_map.json'), encoding='utf-8'))
PIANO_BANDS = rp['bands']
PIANO_MAP = rp['map']
INSTR = rp['instruments']

stats = {name: {'placed': 0, 'dropped': 0, 'clamped': 0} for name, _, _ in INSTRUMENTS}

def layer_of(v):
    return 'p' if v < 0.40 else ('mf' if v < 0.72 else 'f')

def map_piano(m, v):
    band = min(PIANO_BANDS, key=lambda b: abs(b - m)); nv = 12 + (m - band)
    if nv < 0 or nv > 24: stats['piano']['clamped'] += 1
    nv = max(0, min(24, nv))
    return PIANO_MAP[f'{band}_{layer_of(v)}']['block'], nv

def map_pitched(inst, m, v):
    bands = INSTR[inst]['bands']
    band = min(bands, key=lambda b: abs(b - m)); nv = 12 + (m - band)
    if nv < 0 or nv > 24: stats[inst]['clamped'] += 1
    nv = max(0, min(24, nv))
    return INSTR[inst]['map'][f'{band}_mf']['block'], nv

def map_drum(m, v):
    keys = INSTR['drums']['keys']
    key = min(keys, key=lambda k: abs(int(k) - m))      # 最近可用鼓键
    return keys[key]['block'], 12                         # note=12 => 不变调, 原样播鼓

def map_note(inst, m, v):
    if inst == 'piano': return map_piano(m, v)
    if inst == 'drums': return map_drum(m, v)
    return map_pitched(inst, m, v)

# ---------------- 量化 + 每件乐器分 lane(每 lane 每刻 <=1 音) ----------------
# all_trig = 所有乐器触发刻并集(共享骨架的基础)
all_trig = set()
inst_lane_at = {}          # name -> list[ dict(tick -> (block, nv)) ], 每个 dict = 一条 lane
inst_nlanes = {}           # name -> 实际用到的 lane 数

for name, fname, cap in INSTRUMENTS:
    notes = json.load(open(os.path.join(HERE, fname), encoding='utf-8'))['notes']
    bycell = defaultdict(list)
    for n in notes:
        if n['vel'] >= VEL_FLOOR:
            bycell[round(n['t'] / U)].append(n)
    lanes = [dict() for _ in range(cap)]
    for tick, grp in bycell.items():
        # piano/lead/pad 按音高降序; bass 单声;  drums 保留全部(按 t 顺序即可)
        g = grp if name == 'drums' else sorted(grp, key=lambda x: -x['midi'])
        for i, n in enumerate(g):
            if i >= cap:
                stats[name]['dropped'] += 1
                continue
            lanes[i][tick] = map_note(name, n['midi'], n['vel'])
            stats[name]['placed'] += 1
    nused = max((L + 1 for L in range(cap) if lanes[L]), default=1)
    inst_lane_at[name] = lanes[:nused]
    inst_nlanes[name] = nused
    all_trig.update(bycell.keys())

# ---------------- 共享骨架 cells[]: 所有乐器触发刻并集 -> 唯一中继器链 ----------------
trig = sorted(all_trig)
MAXTICK = trig[-1]
OFFSET = 1 if trig[0] == 0 else 0      # 首音在 tick0 时全局 +1 刻(防发声格直连源弱充能); 各 lane 同偏移=不影响同步
cells = []                              # ('rep', delay 1..4) | ('trig', 原始tick)
prev = 0
for T0 in trig:
    T = T0 + OFFSET; G = T - prev
    reps = [4] * (G // 4) + ([G % 4] if G % 4 else [])
    if not reps: reps = [1]
    for d in reps: cells.append(('rep', d))
    cells.append(('trig', T0))
    prev = T
NCELLS = len(cells)
# 校验: 每个发声列累计延迟(红石刻) == 该刻 + OFFSET
cum = 0
for kind, v in cells:
    if kind == 'rep': cum += v
    else: assert cum == v + OFFSET, f"时序错位 @tick {v}: cum={cum} != {v + OFFSET}"

# ---------------- lane 排布: 每件乐器一段连续 Z 带 ----------------
# lane_specs = [ (name, lane_z_offset, notes_at_dict) ... ] 按乐器顺序展开
lane_specs = []
lane_idx = 0
inst_zspan = {}            # name -> (first_lane_idx, last_lane_idx)  仅用于报告
for name, _, _ in INSTRUMENTS:
    first = lane_idx
    for notes_at in inst_lane_at[name]:
        lane_specs.append((name, lane_idx * LANE_DZ, notes_at))
        lane_idx += 1
    inst_zspan[name] = (first, lane_idx - 1)
NLANES = lane_idx

def lane_spine(lane_z, notes_at):
    """一条 lane: 沿共享 cells[] 铺完全相同的中继器骨架; 发声列按本 lane 是否有音放音符盒/直通(同 24)。"""
    sz = OZ + lane_z
    out = [f'setblock {OX-1} {Y-1} {sz} minecraft:stone']    # 源支撑(红石块 fire 时放 OX-1,Y)
    x = OX
    for kind, v in cells:
        if kind == 'rep':
            out.append(f'setblock {x} {Y-1} {sz} minecraft:stone')
            out.append(f'setblock {x} {Y} {sz} minecraft:repeater[facing={RFACING},delay={v}]')
        else:                                                # 发声列(所有 lane 同 X -> 对齐成列)
            note = notes_at.get(v)
            if note:
                block, nv = note
                out.append(f'setblock {x} {Y-1} {sz} {LAMP}')                            # 灯(发声列亮)
                out.append(f'setblock {x} {Y} {sz} {block}')                             # 映射导体(前中继器强充能)
                out.append(f'setblock {x} {Y+1} {sz} minecraft:note_block[note={nv}]')   # 真音符盒
                out.append(f'setblock {x} {Y+2} {sz} air')                               # 上方空气(发声必需)
            else:
                out.append(f'setblock {x} {Y-1} {sz} minecraft:stone')                   # 支撑
                out.append(f'setblock {x} {Y} {sz} {PASS}')                              # 纯导体直通(0延迟, 无音)
                out.append(f'setblock {x} {Y+1} {sz} air')
        x += 1
    return out, x

# ---------------- 数据包脚手架(同 24/30) ----------------
DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 多乐器真音符盒乐队(piano+bass+lead+pad+drums, 共享骨架, tick80)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

build = ['gamerule commandModificationBlockLimit 2147483647']
endx = OX
for name, lz, notes_at in lane_specs:
    cmds, ex = lane_spine(lz, notes_at); build += cmds; endx = max(endx, ex)
LEN = endx - OX
PBX = OX - 3

def labeled_button(bx, cmd, lines):
    msgs = ','.join('\'{"text":"%s"}\'' % s for s in (list(lines) + ['', '', '', ''])[:4])
    return [f'setblock {bx} {Y-1} {OZ} {LAMP}',
            f'setblock {bx} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"{cmd}",auto:0b}}',
            f'setblock {bx} {Y+1} {OZ} minecraft:stone_button[face=floor]',
            f'setblock {bx} {Y-1} {OZ-2} {LAMP}',
            'setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}' % (bx, Y, OZ - 2, msgs)]
build += labeled_button(PBX,   f'function {NS}:play', ['[直接播放]', '站/飞均可', '听全曲'])
build += labeled_button(PBX-2, f'function {NS}:stop', ['[停止]', '复位状态', '卡住按这'])
build += labeled_button(PBX-4, f'function {NS}:cleanup', ['[拆机]', '清除方块'])
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]

WX0, WZ0, WX1, WZ1 = OX - 8, OZ - 3, endx + 2, OZ + (NLANES - 1) * LANE_DZ + 2
zc = (WZ1 // 16) - (WZ0 // 16) + 1
xstep = max(1, 240 // zc)
flbuild, cx = [], WX0
while cx <= WX1:
    cxe = min(WX1, cx + xstep * 16 - 1)
    flbuild.append(f'forceload add {cx} {WZ0} {cxe} {WZ1}'); cx = cxe + 1

src_pts = [(OX - 1, OZ + lz) for _, lz, _ in lane_specs]
TRIG_CLEAR = [f'setblock {sx} {Y} {sz} minecraft:air' for sx, sz in src_pts]
SCHED_CLEAR = [f'schedule clear {NS}:{f}' for f in ('done', 'fire', 'firestop', 'startbuild')]
END_TICKS = (MAXTICK + OFFSET) * 2 + 200

RESET = [f'scoreboard players set PLAY {NS} 0', f'scoreboard players set SIL {NS} 0']
wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1',
            f'scoreboard players set CLR {NS} -1'] + RESET + ['forceload remove all',
            'scoreboard objectives add rpcfg dummy', 'scoreboard players set poly rpcfg 1',
            'scoreboard players set human rpcfg 1']
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] Do You Feel It 乐队整机 loaded. ","color":"aqua"}},'
      f'{{"text":"需RedPiano模组+qzpno包. 曲速80 -> /function {NS}:setup"}}]'])
wf('setup', RESET + ['gamemode creative @a', 'stopsound @a', f'scoreboard players set CLR {NS} -1']
   + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t',
      f'tellraw @a "[{NS}] reset + forceloading; building... (等 BUILT)"'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\n'
   f'tellraw @a "[{NS}] building ({NLANES} lanes x {NCELLS} 格 = 全同步骨架)..."')
wf('tick', f'execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n'
           f'execute if score CLR {NS} matches 0.. run function {NS}:clearstep\n'
           f'execute if score SIL {NS} matches 1 run stopsound @a')   # 停止后持续静默(脉冲滑出期间)
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('buildstep', bs)
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
wf('builddone', f'scoreboard players set BLD {NS} -1\n'
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"曲速80. 按[直接播放] 或 /function {NS}:play"}}]')
wf('playcore', [f'scoreboard players set PLAY {NS} 1', f'scoreboard players set SIL {NS} 0', 'stopsound @a'] + TRIG_CLEAR
   + [f'schedule function {NS}:fire 2t'])
wf('play', [f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先按[停止]"',
            f'function {NS}:playcore',
            f'tellraw @a "[{NS}] GO。乐队合奏(声音绑你本人, 站/飞均可)。发声列灯成竖排同时亮=已同步。"'])
wf('stop', RESET + ['gamemode creative @a', 'stopsound @a', f'scoreboard players set SIL {NS} 1',
                    f'schedule function {NS}:unsil {END_TICKS}t'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a "[{NS}] 已停止(声音立即消失; 残余脉冲静默滑出)。"'])
wf('unsil', f'scoreboard players set SIL {NS} 0')
wf('fire', flbuild + [f'setblock {sx} {Y} {sz} minecraft:redstone_block' for sx, sz in src_pts]
   + [f'schedule function {NS}:firestop {PULSE}t', f'schedule function {NS}:done {END_TICKS}t'])
wf('firestop', TRIG_CLEAR)
wf('done', RESET + ['gamemode creative @a', 'forceload remove all',
           f'tellraw @a "[{NS}] (end) 重放: /function {NS}:play; 清除: /function {NS}:cleanup。"'])
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
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647'] + RESET + ['gamemode creative @a',
              'stopsound @a', f'scoreboard players set BLD {NS} -1'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'scoreboard players set CLR {NS} 0', f'tellraw @a "[{NS}] tearing down..."'])

# ---------------- 部署(copytree, 同 24/30) ----------------
dst = DEPLOY_DST
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)

# ---------------- 报告 ----------------
nrep = sum(1 for k, _ in cells if k == 'rep'); ncond = sum(1 for k, _ in cells if k == 'trig')
WIDTH = (NLANES - 1) * LANE_DZ + 1
print('=== 33 多乐器真音符盒乐队整机 (Do You Feel It) ===')
print(f'NS={NS}  OX={OX} OZ={OZ} Y={Y}  TPS={TPS} (Family A, tick80)  OFFSET={OFFSET} 刻')
print(f'共享骨架: {NCELLS} 格 = {nrep} 中继器 + {ncond} 发声列(=所有乐器触发刻并集) -> 全 {NLANES} lane 同骨架 => 绝对同步 + 音符列对齐')
print(f'机器: {LEN} 长 x {WIDTH} 宽 (~{LEN//16} x {WIDTH//16 + 1} 区块)  批次={len(batches)}')
print('--- 每乐器统计 (placed / dropped / clamped | lanes | lane_idx 区间) ---')
tot_placed = tot_dropped = tot_clamped = 0
for name, _, cap in INSTRUMENTS:
    s = stats[name]; lo, hi = inst_zspan[name]
    tot_placed += s['placed']; tot_dropped += s['dropped']; tot_clamped += s['clamped']
    print(f'  {name:6s} cap={cap}: placed={s["placed"]:4d}  dropped={s["dropped"]:3d}  clamped={s["clamped"]:3d}  '
          f'| lanes={inst_nlanes[name]:2d}  | lane[{lo}..{hi}] z={lo*LANE_DZ}..{hi*LANE_DZ}')
print(f'  TOTAL       : placed={tot_placed}  dropped={tot_dropped}  clamped={tot_clamped}  | lanes={NLANES}')
print(f'时序校验: 通过 (每发声列 cum == tick + OFFSET)')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等 BUILT) -> 按[直接播放] 或 /function {NS}:play')
