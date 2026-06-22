# -*- coding: utf-8 -*-
"""10_build_scheduler2.py — 纯数据包调度器版(对照实验/pivot 候选)。

不用红石、不用 forceload、不用建机器:在 play 时用 `schedule` 把每个 cell 的 playsound
排在它的精确游戏刻上触发。复用现有 qzpno 资源包(同样的采样/音高/音量)。

关键:用**绝对 tick 偏移** round(cell * U * 20) 命中 ♩68 正确曲速(默认 tick rate 20,
不需要 /tick rate——避开了"tick rate 命令在函数里加载报错"的坑)。绝对偏移=零漂移。

目的:和红石脉冲机器做 A/B。新版不掉拍 → 元凶是红石机器;还掉 → 客户端声音层。

Run: python 10_build_scheduler2.py    (读 ./schedule.json, 部署到世界数据包 qzsch_play)
"""
import os, json, shutil
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'qzsch'                       # 函数命名空间(独立, 不碰 qzpno 红石版)
SOUND_NS = 'qzpno'                 # 复用现有资源包(qzpno_mv) 的采样
TPS = 20                           # 默认 tick rate; 绝对偏移在此基准下命中 ♩68
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"

sch = json.load(open(os.path.join(HERE, 'schedule.json'), encoding='utf-8'))
U = sch['cell_ms'] / 1000.0        # 0.221s = 一个十六分音符 @♩68
cells = sch['cells']               # [{cell, eid, pitch, vol}, ...] (已含 7-lane 分配)

bycell = defaultdict(list)
for e in cells:
    bycell[e['cell']].append((e['eid'], e['pitch'], e['vol']))
occ = sorted(bycell)
def off(c):                        # cell -> 绝对游戏刻偏移(命中真实曲速)
    return round(c * U * TPS)

# ---- 生成数据包 ----
DP = os.path.join(HERE, 'build', f'{NS}_play')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(
        ('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')

json.dump({"pack": {"pack_format": 81, "description": "qzsch 晴天 钢琴 纯调度器(无红石) A/B 测试"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)

# 每个 cell 一个函数:把该 cell 的若干 playsound 播在玩家身上
for c in occ:
    lines = [f'execute as @a at @s run playsound {SOUND_NS}:{eid} master @s ~ ~ ~ {vol} {pitch} 1'
             for (eid, pitch, vol) in bycell[c]]
    w(f'data/{NS}/function/c/{c}.mcfunction', lines)

# play:清场 + 把每个 cell 排到它的绝对刻 + 末尾 done
play = ['stopsound @a master']
play += [f'schedule function {NS}:c/{c} {off(c)}t' for c in occ]
play += [f'schedule function {NS}:done {off(occ[-1]) + 40}t',
         f'tellraw @a "[qzsch] scheduler play (no redstone). listen for drops."']
w(f'data/{NS}/function/play.mcfunction', play)

w(f'data/{NS}/function/done.mcfunction',
  f'tellraw @a "[qzsch] (end) replay: /function {NS}:play"')

# stop:中止(清掉所有未触发的 schedule + 停声)
stop = ['stopsound @a master'] + [f'schedule clear {NS}:c/{c}' for c in occ] + [f'schedule clear {NS}:done',
        'tellraw @a "[qzsch] stopped."']
w(f'data/{NS}/function/stop.mcfunction', stop)

# ---- 部署到世界 ----
dst = os.path.join(WORLD_DP, f'{NS}_play')
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)

print('=== 10 scheduler2 build ===')
print(f'occupied cells={len(occ)}  notes(playsounds)={len(cells)}  U={U*1000:.1f}ms  tick_rate={TPS}')
print(f'tempo: cell c -> tick round(c*{U*TPS:.2f}); last cell {occ[-1]} -> {off(occ[-1])}t = {off(occ[-1])/TPS:.1f}s (♩{60/(U*4):.0f})')
print(f'datapack functions: {len(occ)} cell-funcs + play/done/stop')
print(f'deployed -> {dst}')
print('用法(游戏内): /reload  ->  /tick rate 20(确保默认)  ->  /function qzsch:play')
