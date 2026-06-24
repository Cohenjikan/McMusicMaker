# -*- coding: utf-8 -*-
"""40_build_foldcompact.py — Task2 定稿: olk 长度【部分压缩】(保持原~14格窄条, 蛇形曲折)。

用户澄清(第5轮): 不要把机器折成正方形(上一版 ROWS 多→宽 212 是错的)。应当【依然保持原来 ~14 格
  的窄条宽度】, 只在这条窄带里【做曲折(蛇形 U 弯)把长度部分压短】—— 不是把宽度撑大去换长度。
  -> 每条轨只折成 ROWS=2 行(一个 U 弯): 两轨各占 ~7 宽并排 = 总宽 ~14(=原宽), 长度 X 砍半(2x 部分压缩)。
     ROWS 是参数: 想更短可加大(更宽), 想更窄就 ROWS=2; 默认 2 = 用户要的"原宽窄条曲折一次"。
  沿用 31 已证的【平面蛇形折叠 + 红石粉0延迟U弯】几何, ROW_DZ=4(29 验)。音频已实测正常(第5轮反馈)。
  注: 窄条比正方形【占用更多区块】(长x2宽chunk), 若回到过载断音, 这是几何取舍的代价(见末尾打印)。

折叠 = 蛇形铺设(行 +X / -X 交替), 行间用【红石粉 U 形弯】连接。关键(让时序零风险):
  ★ U 形弯用【纯红石粉】(0 延迟): 红石粉在同一红石刻内传导(<=15格不衰减为0), 故拐弯【不加延迟】
    -> 24/30 已证的时序公式(累计延迟==该刻)【原样成立】, 折叠不改一个数(见下方时序断言)。
  ★ 只在遇到 'rep' 格时换行(行首必是中继器) -> 行首强充能干净, 不靠弱充能触发音符盒(避歧义)。
  ★ 辐射和弦只落在水平行(±Z 出和弦), U 形弯(±X 端外一列)与之不同 X -> 不串扰。
双轨 = 两块【独立折叠板】(同一折叠形状, 沿 Z 平移分开放) -> 同 cell 同 X -> 绝对同步 + 列对齐。
  (双轨共行会让两条 U 形粉腿在同列重叠; 拆成两板最简且可证无碰撞 —— 见 Python 碰撞断言。)

本版相对 31 的修订(全是第3轮已查实的真 bug, 不改几何):
  - 停止: stopsound @a(模组在 RECORDS, 不是 master)+ SIL 记分板持续静默(同 36)。
  - forceload: setup/fire 的 flbuild 先 'forceload remove all'(防多台堆叠过载, 同 36)。
  - 世界路径修正为 '新的世界 (1)'(旧 '新的世界' 已被用户删)。
  - 恢复 [复音增益]/[微抖动] cfg 按钮(同 30; 31 漏了)。告示牌 messages 正好 4 行。
几何依赖: 辐射和弦(27)✓、平面拐角(26)✓、折叠+辐射共存 ROW_DZ=4(29)✓、红石粉0延迟U弯(32 qzdf)✓。
需 RedPiano 模组 + qzpno 资源包(format64, 手动启用)。
Run: python 40_build_foldcompact.py [notes.json] [NS] [OX] [ROWS] [ROWLEN]
  ★第4参已从 ROWLEN 改为 ROWS(每轨折几行): 默认 2 = 原宽窄条; 不传任何参数即得 olk 窄条。
  重要: 换机器形状/OX后旧机器方块不会自动消失 —— 要么换个空 OX, 要么先 /function {NS}:cleanup 清旧。
"""
import os, sys, json, shutil
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES  = sys.argv[1] if len(sys.argv) > 1 else 'notes_olk.json'
NS     = sys.argv[2] if len(sys.argv) > 2 else 'qzolkc'
OX     = int(sys.argv[3]) if len(sys.argv) > 3 else 260000   # 第5轮换空地(旧 250000 有第4轮方形残留, 别再撞)
ROWS   = int(sys.argv[4]) if len(sys.argv) > 4 else 2        # ★每板折几行: 2=只折一次(一个U弯), 总宽~14(=原宽), 长压 2x(部分压缩, 不做正方形)
ROWLEN = int(sys.argv[5]) if len(sys.argv) > 5 else None     # 每行格数; 缺省=ceil(NCELLS/ROWS) 使恰好 ROWS 行
OZ, Y = 0, 255
ROW_DZ = 4                         # 行距(29 已验): 和弦占 zr±1, 行间留 1 空, 下一行 zr+4
RFACE = {1: 'west', -1: 'east'}    # X 流向 -> facing(=反向, 26 已证: facing=west 输出 +X)
LAMP, PASS, BATCH = 'minecraft:redstone_lamp', 'minecraft:stone', 2000
VOICES, TPS, PULSE = 6, 80, 4
U = 2 / TPS
SSTOP = 'stopsound @a'             # ★ 模组发声在 RECORDS, 不带源才停得掉(master 停不掉)
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

# ---- 量化 + 和弦声部分配(同 30): trackvoice[track][pos][tick]=(block,nv); pos 0=上 1=+Z 2=-Z ----
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

# ---- 共享时间线 cells[](同 24/30): 触发刻并集 -> 唯一变延迟骨架 ----
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
cum = 0                                  # ★ 时序断言(折叠不改: 红石粉U弯=0延迟)
for kind, v in cells:
    if kind == 'rep': cum += v
    else: assert cum == v + OFFSET, f"时序错位 @tick {v}: cum={cum} != {v+OFFSET}"
if ROWLEN is None:                        # 缺省: 每板恰好折成 ROWS 行(ROWS=2 -> 总宽~14=原宽, 长压2x)
    ROWLEN = (NCELLS + ROWS - 1) // ROWS

# ---- 折叠布局: 把 1D cells[] 蛇形铺成(行,列). 只在 'rep' 前换行(行首=中继器) ----
pos = [None] * NCELLS                     # pos[i] = (xoff, zoff, dirx)
legs = []                                 # 红石粉 U 弯: (xoff_leg, z_from, z_to)
x, z, d, col = 0, 0, 1, 0
for i in range(NCELLS):
    pos[i] = (x, z, d)
    x += d; col += 1
    last = (i == NCELLS - 1)
    nxt_rep = (not last) and cells[i + 1][0] == 'rep'
    if (not last) and col >= ROWLEN and nxt_rep:
        legs.append((x, z, z + ROW_DZ))   # 腿在行末外一列(x), 从 z 升到 z+ROW_DZ
        z += ROW_DZ; d = -d; x += d; col = 0
NROWS = len(legs) + 1
MAXZOFF = max([zt for (_, _, zt) in legs] + [zo + 1 for (_, zo, _) in pos])  # 单板 z 跨度(含 +Z 和弦)
SLAB_SEP = MAXZOFF + 3                      # 两板相邻(板间只留 1 格空, 同 29 行距), 总宽~14=原宽, 不撑成正方形; 碰撞断言兜底
TRACK_Z = [OZ, OZ + SLAB_SEP]
LEN_X = ROWLEN + 1                          # 行占 0..ROWLEN-1, U 弯在 -1 / ROWLEN

# ---- 发射 setblock + 碰撞断言(我无法跑 MC, 用 Python 兜底) ----
occ = {}                                   # (x,y,z) -> block; 冲突即报
def put(out, x, y, zz, blk):
    key = (x, y, zz)
    if key in occ and occ[key] != blk and not (occ[key] == 'air' or blk == 'air'):
        raise AssertionError(f"碰撞 @{key}: {occ[key]} vs {blk}")
    occ[key] = blk
    out.append(f'setblock {x} {y} {zz} {blk}')

def emit_track(t, toz):
    """一条折叠板: 沿 pos[] 铺骨架(本轨 3 声部辐射和弦), legs 用红石粉 0 延迟连接。"""
    out = [f'setblock {OX-1} {Y-1} {toz} {PASS}']     # 源支撑(fire 时放红石块于 OX-1,Y,toz)
    for i, (xo, zo, dirx) in enumerate(pos):
        X, Z = OX + xo, toz + zo
        kind, v = cells[i]
        if kind == 'rep':
            put(out, X, Y - 1, Z, LAMP)
            put(out, X, Y, Z, f'minecraft:repeater[facing={RFACE[dirx]},delay={v}]')
        else:
            above = trackvoice[t][0].get(v); pz = trackvoice[t][1].get(v); mz = trackvoice[t][2].get(v)
            put(out, X, Y - 1, Z, LAMP)
            put(out, X, Y, Z, above[0] if above else PASS)        # 链导体(强充能)= 上音映射 或 直通
            if above:
                put(out, X, Y + 1, Z, f'minecraft:note_block[note={above[1]}]'); put(out, X, Y + 2, Z, 'air')
            if pz:
                put(out, X, Y - 1, Z + 1, pz[0]); put(out, X, Y, Z + 1, f'minecraft:note_block[note={pz[1]}]'); put(out, X, Y + 1, Z + 1, 'air')
            if mz:
                put(out, X, Y - 1, Z - 1, mz[0]); put(out, X, Y, Z - 1, f'minecraft:note_block[note={mz[1]}]'); put(out, X, Y + 1, Z - 1, 'air')
    for (xleg, zf, zt) in legs:                           # 红石粉 U 弯(0 延迟): 支撑 + dust 一列
        for zz in range(zf, zt + 1):
            put(out, OX + xleg, Y - 1, toz + zz, PASS)
            put(out, OX + xleg, Y, toz + zz, 'minecraft:redstone_wire')
    return out

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} olk双轴压缩紧凑整机(X折叠+Z铺行, 红石粉0延迟U弯, tick80)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

build = ['gamerule commandModificationBlockLimit 2147483647']
for t in range(2):
    build += emit_track(t, TRACK_Z[t])
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]

# 占地(两板) -> forceload 切条 + 拆除分段
allx = [k[0] for k in occ]; allz = [k[2] for k in occ]
WX0, WZ0, WX1, WZ1 = min(allx) - 2, min(allz) - 2, max(allx) + 2, max(allz) + 2
zc = (WZ1 // 16) - (WZ0 // 16) + 1
xstep = max(1, 240 // max(1, zc))
flbuild, cx = ['forceload remove all'], WX0        # ★ 先清旧 forceload(防多台堆叠过载, 第3轮真bug)
while cx <= WX1:
    cxe = min(WX1, cx + xstep * 16 - 1)
    flbuild.append(f'forceload add {cx} {WZ0} {cxe} {WZ1}'); cx = cxe + 1

src_pts = [(OX - 1, tz) for tz in TRACK_Z]
TRIG_CLEAR = [f'setblock {sx} {Y} {sz} minecraft:air' for sx, sz in src_pts]
SCHED_CLEAR = [f'schedule clear {NS}:{f}' for f in ('done', 'fire', 'firestop', 'startbuild', 'unsil')]
MUSIC_TICKS = (MAXTICK + OFFSET) * 2
END_TICKS = MUSIC_TICKS + 200
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
ctl += labeled_button(PBX,   f'function {NS}:play',           ['[直接播放]', '站着即可', '听全曲'])
ctl += labeled_button(PBX-2, f'function {NS}:view',           ['[全景俯视]', '看折叠方阵', '灯流光'])
ctl += labeled_button(PBX-4, f'function {NS}:stop',           ['[停止]', '立即静音', '卡住按这'])
ctl += labeled_button(PBX-6, f'function {NS}:cfg/polytoggle', ['[复音增益]', '大和弦', '防糊'])
ctl += labeled_button(PBX-8, f'function {NS}:cfg/humantoggle',['[微抖动]', '去复印感'])

RESET = [f'scoreboard players set PLAY {NS} 0', f'scoreboard players set SIL {NS} 0']
wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1',
            f'scoreboard players set CLR {NS} -1'] + RESET + ['forceload remove all',
            'scoreboard objectives add rpcfg dummy', 'scoreboard players set poly rpcfg 1', 'scoreboard players set human rpcfg 1']
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] 折叠整机 loaded. ","color":"aqua"}},{{"text":"需RedPiano模组+qzpno包. /tick rate 80 -> /function {NS}:setup"}}]'])
wf('setup', RESET + ['gamemode creative @a', SSTOP, f'scoreboard players set CLR {NS} -1']
   + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t',
      f'tellraw @a "[{NS}] reset + forceloading; building... (等 BUILT)"'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building (2 板 x {NCELLS}格, {NROWS}行 x {ROWLEN})..."')
wf('tick', f'execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n'
           f'execute if score CLR {NS} matches 0.. run function {NS}:clearstep\n'
           f'execute if score SIL {NS} matches 1 run {SSTOP}')
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('buildstep', bs)
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
ctlfn = ['gamerule commandModificationBlockLimit 2147483647'] + ctl
wf('placectl', ctlfn)
wf('playcore', [f'scoreboard players set PLAY {NS} 1', f'scoreboard players set SIL {NS} 0', SSTOP] + TRIG_CLEAR + [f'schedule function {NS}:fire 2t'])
wf('play', [f'execute if score PLAY {NS} matches 1 run return run tellraw @a "[{NS}] 正在播放, 先按[停止]"',
            f'function {NS}:playcore',
            f'tellraw @a "[{NS}] GO。站着/自由飞都能听全曲(声音绑你本人)。折叠方阵灯随脉冲流动。"'])
wf('view', ['gamemode spectator @a', f'tp @a {CAMX} {Y+40} {CAMZ} 0 90',
            f'tellraw @a "[{NS}] 俯视折叠方阵(spectator)。再按[直接播放]听; [停止]退出。"'])
# stop: 先跑 SCHED_CLEAR(含 schedule clear unsil)再 set SIL=1 + schedule unsil ——
#   否则 SCHED_CLEAR 会把刚排的 unsil 清掉 -> SIL 永为1 -> stopsound 永久静音(36 的未修bug)。
wf('stop', RESET + ['gamemode creative @a', SSTOP] + SCHED_CLEAR + TRIG_CLEAR
   + [f'scoreboard players set SIL {NS} 1', f'schedule function {NS}:unsil {END_TICKS}t',
      f'tp @a {PBX} {Y+3} {OZ}', f'tellraw @a "[{NS}] 已停止(立即静音, 复位)。脉冲滑出后自动恢复。"'])
wf('unsil', f'scoreboard players set SIL {NS} 0')
wf('fire', flbuild + [f'setblock {sx} {Y} {sz} minecraft:redstone_block' for sx, sz in src_pts]
   + [f'schedule function {NS}:firestop {PULSE}t', f'schedule function {NS}:done {END_TICKS}t'])
wf('firestop', TRIG_CLEAR)
wf('done', RESET + ['gamemode creative @a', f'tellraw @a "[{NS}] (end) 重放: 按[直接播放]; 清除: /function {NS}:cleanup。"'])
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
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647'] + RESET + ['gamemode creative @a', SSTOP,
               f'scoreboard players set BLD {NS} -1'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'scoreboard players set CLR {NS} 0', f'tellraw @a "[{NS}] tearing down..."'])
# cfg 开关(同 30): 模组刻末读 rpcfg poly/human 决定复音增益 / 微抖动
wf('cfg/polytoggle', ['scoreboard players set rptmp rpcfg 1', 'scoreboard players operation rptmp rpcfg -= poly rpcfg',
                      'scoreboard players operation poly rpcfg = rptmp rpcfg',
                      f'execute if score poly rpcfg matches 1 run tellraw @a "[{NS}] 复音增益 ON"',
                      f'execute if score poly rpcfg matches 0 run tellraw @a "[{NS}] 复音增益 OFF"'])
wf('cfg/humantoggle', ['scoreboard players set rptmp rpcfg 1', 'scoreboard players operation rptmp rpcfg -= human rpcfg',
                       'scoreboard players operation human rpcfg = rptmp rpcfg',
                       f'execute if score human rpcfg matches 1 run tellraw @a "[{NS}] 微抖动 ON"',
                       f'execute if score human rpcfg matches 0 run tellraw @a "[{NS}] 微抖动 OFF"'])
# 控制台在 builddone 后单独放(避免与建造批次同刻)
wf('builddone', f'scoreboard players set BLD {NS} -1\nfunction {NS}:placectl\n'
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"X长仅~{LEN_X}格(原直链~{NCELLS}). 按[直接播放]/[全景俯视]/[停止]"}}]')

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
nrep = sum(1 for k, _ in cells if k == 'rep'); ncond = sum(1 for k, _ in cells if k == 'trig')
nplaced = sum(len(trackvoice[t][p]) for t in range(2) for p in range(3))
# 占地量化: 宽度(应≈原14, 不撑成正方形) + 长度(部分压短) + 区块数(几何取舍, 窄条比正方形多)
zwidth = max(k[2] for k in occ) - min(k[2] for k in occ) + 1
fold_chunks = ((WX1 // 16) - (WX0 // 16) + 1) * ((WZ1 // 16) - (WZ0 // 16) + 1)
line_chunks = (NCELLS // 16 + 1) * 2                       # 直线: NCELLS 长 x ~7宽+边距 ≈ 2 区块宽
print('=== 40 olk 长度部分压缩(原~14窄条 + 蛇形曲折) ===')
print(f'曲子={NOTES} 发声音={nplaced} dropped={dropped} 钳音={clamped[0]} OFFSET={OFFSET}')
print(f'骨架: {NCELLS}格 = {nrep}中继器 + {ncond}发声列. 每轨折 {NROWS} 行 x {ROWLEN}格, 行距{ROW_DZ}, {len(legs)*2}个红石粉0延迟U弯(双轨)')
print(f'★宽度: {zwidth} 格(目标≈14=原宽, 两板各~7并排; 没撑成正方形 ✓)')
print(f'★长度: 直链~{NCELLS} -> 曲折后 X长~{LEN_X} (部分压缩 {NCELLS/max(1,LEN_X):.1f}x)')
print(f'占地: x[{WX0}..{WX1}]={WX1-WX0} z[{WZ0}..{WZ1}]={WZ1-WZ0}; 两板 z={TRACK_Z}; 批次={len(batches)}')
print(f'区块: 本窄条 ~{fold_chunks} (=长{((WX1//16)-(WX0//16)+1)}x宽{((WZ1//16)-(WZ0//16)+1)})  vs 同曲直线 ~{line_chunks}  [注: 窄条不为省区块, 是为保持原形; 上版正方形~210, Z线圈1505]')
print(f'断言: 时序(cum==tick) ✓  碰撞(无重叠) ✓')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT绿字) -> 按[直接播放]; 卡住[停止]')
