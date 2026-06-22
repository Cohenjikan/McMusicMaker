# -*- coding: utf-8 -*-
"""25_build_synccam.py — 24(同步骨架) + 红石驱动相机 + 灯流光。

在 24 之上加三件事(应对 OLK 实测: 太快跟不上 -> 出可听范围 -> 听感"断"):
 1) 红石驱动相机(用户方案A): 不靠预排时间(会漂), 而是从【真红石信号】触发 tp ——
    在每个发声列(触发刻)旁 z=-1 放一个命令方块, 被该列导体强充能时(=脉冲刚到该列)触发
    `execute if score CAM matches 1 run tp @a (X-trail) ...`。脉冲走到哪, 玩家被拽到哪,
    永远在脉冲处=永远在可听范围内、且与红石绝对同步(因为就是红石本身在驱动 tp)。
    休止符(无触发刻)时相机暂停, 反正没声; 下一个音到了再被拽过去(踩点)。
 2) 石头 -> 红石灯(用户要求, 已查证: 红石灯是可导电不透明方块, repeater->灯->repeater 成立,
    且被脉冲强充能时点亮 -> 发声/直通列随脉冲流动点亮)。映射块(发声块)保持原样(模组靠它定音色)。
 3) 两个按钮: [直接播放](无相机) / [相机播放](spectator + 红石驱动跟随)。

需 RedPiano 模组 + qzpno 资源包。Run: python 25_build_synccam.py [notes.json] [NS] [OX]
"""
import os, sys, json, shutil
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = sys.argv[1] if len(sys.argv) > 1 else 'notes_wll.json'
NS = sys.argv[2] if len(sys.argv) > 2 else 'qzws'
OX = int(sys.argv[3]) if len(sys.argv) > 3 else 170000
OZ = 0
Y, LANE_DZ = 255, 2
LAMP, RFACING, BATCH = 'minecraft:redstone_lamp', 'west', 2000   # 石头->灯: 支撑/直通/发声列垫底统一用灯
PASS = LAMP                    # 无音直通导体 = 灯(可导电 + 脉冲过时点亮)
MAXLANES, VEL_FLOOR = 7, 0.04
TPS, PULSE = 80, 4
U = 2 / TPS
# 相机(可调): 在脉冲后方 CAM_TRAIL 格、抬高、居中于 lane, 面向 +X(行进方向)俯视
CAM_TRAIL, CAMY_OFF, CYAW, CPITCH = 4, 6, -90, 32
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

bycell = defaultdict(list)
for n in notes:
    if n['vel'] >= VEL_FLOOR: bycell[round(n['t'] / U)].append(n)
lane_at = [dict() for _ in range(MAXLANES)]
dropped = 0
for tick, grp in bycell.items():
    for i, n in enumerate(sorted(grp, key=lambda x: -x['midi'])):
        if i >= MAXLANES: dropped += 1; continue
        lane_at[i][tick] = map_note(n['midi'], n['vel'])
NLANES = max((L + 1 for L in range(MAXLANES) if lane_at[L]), default=1)

# 共享骨架(同 24): 触发刻并集 -> 唯一中继器链, 各 lane 全等 -> 同步 + 列对齐
trig = sorted(bycell)
MAXTICK = trig[-1]
OFFSET = 1 if trig[0] == 0 else 0
cells = []
prev = 0
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

# 每个发声列的 X(各 lane 同 X) -> 相机 tp 锚点
cam_x = []
xx = OX
for kind, v in cells:
    if kind == 'trig': cam_x.append(xx)
    xx += 1
CAMZ = OZ + ((NLANES - 1) * LANE_DZ) // 2     # 居中于 lane 群

def lane_spine(lane_z, notes_at):
    sz = OZ + lane_z
    out = [f'setblock {OX-1} {Y-1} {sz} {LAMP}']            # 源支撑(灯)
    x = OX
    for kind, v in cells:
        if kind == 'rep':
            out.append(f'setblock {x} {Y-1} {sz} {LAMP}')
            out.append(f'setblock {x} {Y} {sz} minecraft:repeater[facing={RFACING},delay={v}]')
        else:
            note = notes_at.get(v)
            if note:
                block, nv = note
                out.append(f'setblock {x} {Y-1} {sz} {LAMP}')                          # 灯(发声列亮)
                out.append(f'setblock {x} {Y} {sz} {block}')                           # 映射导体(定音色)
                out.append(f'setblock {x} {Y+1} {sz} minecraft:note_block[note={nv}]')
                out.append(f'setblock {x} {Y+2} {sz} air')
            else:
                out.append(f'setblock {x} {Y-1} {sz} {LAMP}')                          # 支撑(灯)
                out.append(f'setblock {x} {Y} {sz} {PASS}')                            # 直通导体=灯(导电+点亮)
                out.append(f'setblock {x} {Y+1} {sz} air')
        x += 1
    return out, x

DP = os.path.join(HERE, 'build', f'{NS}_synccam')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 同步真音符盒 + 红石驱动相机 + 灯流光"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

build = ['gamerule commandModificationBlockLimit 2147483647']
endx = OX
for L in range(NLANES):
    cmds, ex = lane_spine(L * LANE_DZ, lane_at[L]); build += cmds; endx = max(endx, ex)
# 红石驱动相机: 每个发声列 z=-1 放命令方块, 被 lane0 该列导体(强充能)触发 -> tp(仅 CAM=1)
for X in cam_x:
    tp = f"execute if score CAM {NS} matches 1 run tp @a {X-CAM_TRAIL} {Y+CAMY_OFF} {CAMZ} {CYAW} {CPITCH}"
    build.append(f'setblock {X} {Y} {OZ-1} minecraft:command_block[facing=up,conditional=false]{{Command:"{tp}",auto:0b}}')
# 带标签的按钮(每个命令方块南侧立一块木牌写用途, 防越来越多记不住)
def labeled_button(bx, cmd, lines):
    msgs = ','.join('\'{"text":"%s"}\'' % t for t in (list(lines) + ['', '', '', ''])[:4])
    return [f'setblock {bx} {Y-1} {OZ} {LAMP}',
            f'setblock {bx} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"{cmd}",auto:0b}}',
            f'setblock {bx} {Y+1} {OZ} minecraft:stone_button[face=floor]',
            f'setblock {bx} {Y-1} {OZ-1} {LAMP}',
            'setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[%s]}}' % (bx, Y, OZ - 1, msgs)]
PBX = OX - 3
build += labeled_button(PBX,   f'function {NS}:play',           ['[直接播放]', '站着或自由飞', '都听全曲'])
build += labeled_button(PBX-2, f'function {NS}:play_cam',       ['[相机播放]', '红石驱动tp', 'spectator跟随'])
build += labeled_button(PBX-4, f'function {NS}:play_ride',      ['[骑行播放]', '骑隐形实体', '平滑巡游'])
build += labeled_button(PBX-6, f'function {NS}:cfg/polytoggle', ['[复音增益开关]', '大和弦降幅', '防糊/削顶'])
build += labeled_button(PBX-8, f'function {NS}:cfg/humantoggle',['[微抖动开关]', '+-3音分/2%', '去复印感'])
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]
LEN = endx - OX
WX0, WZ0, WX1, WZ1 = OX - 6, OZ - 2, endx + 2, OZ + (NLANES - 1) * LANE_DZ + 2

zc = (WZ1 // 16) - (WZ0 // 16) + 1
xstep = max(1, 240 // zc)
flbuild, cx = [], WX0
while cx <= WX1:
    cxe = min(WX1, cx + xstep * 16 - 1)
    flbuild.append(f'forceload add {cx} {WZ0} {cxe} {WZ1}'); cx = cxe + 1

src_pts = [(OX - 1, OZ + L * LANE_DZ) for L in range(NLANES)]
TRIG_CLEAR = [f'setblock {sx} {Y} {sz} minecraft:air' for sx, sz in src_pts]
SCHED_CLEAR = [f'schedule clear {NS}:{f}' for f in ('done', 'fire', 'firestop', 'startbuild', 'ridestop')]
END_TICKS = (MAXTICK + OFFSET) * 2 + 200
MUSIC_TICKS = (MAXTICK + OFFSET) * 2                       # 全曲游戏刻(脉冲跑完全机的时长)
RIDEY = Y + 3                                              # 骑行载体高度(在 lane 群上方)
RIDE_SPEED = round(LEN / max(1, MUSIC_TICKS), 4)          # 骑行恒速: 每刻 +X 这么多格, 全机≈全曲时长

wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1',
            f'scoreboard players set CLR {NS} -1', f'scoreboard players set PLAY {NS} 0',
            f'scoreboard players set CAM {NS} 0', f'scoreboard players set RIDE {NS} 0', 'forceload remove all',
            'scoreboard objectives add rpcfg dummy',                          # mod 读此目标做复音增益/微抖开关
            'scoreboard players set poly rpcfg 1', 'scoreboard players set human rpcfg 1']
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[{NS}] 同步真音符盒+相机 loaded. ","color":"aqua"}},{{"text":"需mod+资源包. 曲速80 -> /function {NS}:setup"}}]'])
wf('setup', [f'scoreboard players set PLAY {NS} 0', 'stopsound @a master', f'scoreboard players set CLR {NS} -1']
   + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t',
      f'tellraw @a "[{NS}] reset + forceloading; building... (等 BUILT)"'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[{NS}] building ({NLANES} lanes x {NCELLS}格 + {len(cam_x)}相机锚点)..."')
wf('tick', f'execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n'
           f'execute if score CLR {NS} matches 0.. run function {NS}:clearstep\n'
           f'execute if score RIDE {NS} matches 1 as @e[tag=rpride,limit=1] at @s run tp @s ~{RIDE_SPEED} ~ ~')
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('buildstep', bs)
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
wf('builddone', f'scoreboard players set BLD {NS} -1\n'
   f'tellraw @a ["",{{"text":"[{NS}] built. ","color":"green"}},{{"text":"曲速80. [直接播放]按钮 或 [相机播放]按钮(自动跟随)"}}]')
# playcore: 真正起跑(被 play / play_cam 共用; CAM 由各自先设好)
wf('playcore', [f'execute if score PLAY {NS} matches 1 run return 0', f'scoreboard players set PLAY {NS} 1', 'stopsound @a master']
   + TRIG_CLEAR + [f'schedule function {NS}:fire 2t'])
# 开关: 算术翻转 new = 1 - old(rptmp 暂存), 防"同函数内顺序重判"翻不动
wf('cfg/polytoggle', ['scoreboard players set rptmp rpcfg 1', 'scoreboard players operation rptmp rpcfg -= poly rpcfg',
                      'scoreboard players operation poly rpcfg = rptmp rpcfg',
                      f'execute if score poly rpcfg matches 1 run tellraw @a "[{NS}] 复音增益 ON (大和弦自动降幅防糊)"',
                      f'execute if score poly rpcfg matches 0 run tellraw @a "[{NS}] 复音增益 OFF (原始满音量)"'])
wf('cfg/humantoggle', ['scoreboard players set rptmp rpcfg 1', 'scoreboard players operation rptmp rpcfg -= human rpcfg',
                       'scoreboard players operation human rpcfg = rptmp rpcfg',
                       f'execute if score human rpcfg matches 1 run tellraw @a "[{NS}] 微抖动 ON (±3音分/±2%, 去复印感)"',
                       f'execute if score human rpcfg matches 0 run tellraw @a "[{NS}] 微抖动 OFF"'])
wf('play', [f'scoreboard players set CAM {NS} 0', f'function {NS}:playcore',
            f'tellraw @a "[{NS}] GO(无相机)。灯随脉冲流动点亮。"'])
wf('play_cam', [f'execute if score PLAY {NS} matches 1 run return 0', 'gamemode spectator @a',
                f'scoreboard players set CAM {NS} 1', f'function {NS}:playcore',
                f'tellraw @a "[{NS}] GO(相机跟随)。红石驱动 tp, 永远跟着脉冲。"'])
# 骑行播放: 骑隐形 armor_stand 平滑巡游(tick 里恒速 +X 推进); 声音绑玩家本人 -> 移动不断不糊
wf('play_ride', [f'execute if score PLAY {NS} matches 1 run return 0', 'kill @e[tag=rpride]',
                 f'summon armor_stand {OX} {RIDEY} {CAMZ} {{Invisible:1b,NoGravity:1b,Tags:["rpride"],Rotation:[-90f,12f]}}',
                 f'ride @a mount @e[tag=rpride,limit=1]', f'scoreboard players set RIDE {NS} 1',
                 f'scoreboard players set CAM {NS} 0',
                 f'schedule function {NS}:ridestop {MUSIC_TICKS + 60}t', f'function {NS}:playcore',
                 f'tellraw @a "[{NS}] GO(骑行巡游)。声音绑定你本人, 任意移速都不断不糊。Shift 下马自由飞也行。"'])
wf('ridestop', [f'scoreboard players set RIDE {NS} 0', 'ride @a dismount', 'kill @e[tag=rpride]',
                f'tellraw @a "[{NS}] (骑行巡游结束)"'])
wf('fire', flbuild + [f'setblock {sx} {Y} {sz} minecraft:redstone_block' for sx, sz in src_pts]
   + [f'schedule function {NS}:firestop {PULSE}t', f'schedule function {NS}:done {END_TICKS}t'])
wf('firestop', TRIG_CLEAR)
wf('done', [f'scoreboard players set PLAY {NS} 0',
            f'execute if score CAM {NS} matches 1 run gamemode creative @a',
            f'scoreboard players set CAM {NS} 0',
            f'execute if score RIDE {NS} matches 1 run ride @a dismount', 'kill @e[tag=rpride]',
            f'scoreboard players set RIDE {NS} 0', 'forceload remove all',
            f'tellraw @a "[{NS}] (end) replay: /function {NS}:setup; cleanup: /function {NS}:cleanup."'])
SEG = 200
clr_segs = (LEN + 12) // SEG + 1
for k in range(clr_segs):
    fx0 = OX - 6 + k * SEG; fx1 = min(endx + 2, fx0 + SEG - 1)
    wf(f'clr/c{k}', f'fill {fx0} {Y-2} {WZ0} {fx1} {Y+3} {WZ1} air')
wf('cleardone', [f'scoreboard players set CLR {NS} -1', 'forceload remove all', f'tellraw @a "[{NS}] cleaned up."'])
cs = [f'execute if score CLR {NS} matches {k} run function {NS}:clr/c{k}' for k in range(clr_segs)]
cs += [f'execute if score CLR {NS} matches {clr_segs} run function {NS}:cleardone',
       f'execute if score CLR {NS} matches 0..{clr_segs} run scoreboard players add CLR {NS} 1']
wf('clearstep', cs)
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647', f'scoreboard players set PLAY {NS} 0',
               f'execute if score CAM {NS} matches 1 run gamemode creative @a', f'scoreboard players set CAM {NS} 0',
               'ride @a dismount', 'kill @e[tag=rpride]', f'scoreboard players set RIDE {NS} 0',
               'stopsound @a master', f'scoreboard players set BLD {NS} -1'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'scoreboard players set CLR {NS} 0', f'tellraw @a "[{NS}] tearing down..."'])

dst = os.path.join(WORLD_DP, f'{NS}_sync')      # 覆盖 24 的部署(同命名空间, 避免重复定义冲突)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
notecount = sum(len(d) for d in lane_at)
nrep = sum(1 for k, _ in cells if k == 'rep'); ncond = sum(1 for k, _ in cells if k == 'trig')
print('=== 25 同步真音符盒 + 红石驱动相机 + 灯流光 ===')
print(f'曲子={NOTES} 音符={notecount} dropped={dropped} 钳音={clamped[0]} lanes={NLANES} OFFSET={OFFSET}')
print(f'骨架: {NCELLS}格 = {nrep}中继器 + {ncond}发声列. 相机锚点={len(cam_x)}(每发声列1个, 红石驱动)')
print(f'机器: {LEN}长 x {(NLANES-1)*LANE_DZ+1}宽  批次={len(batches)}  相机: trail={CAM_TRAIL} Y+{CAMY_OFF} z={CAMZ} yaw={CYAW} pitch={CPITCH}')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup (等BUILT) -> 按[相机播放]按钮 或 /function {NS}:play_cam')
