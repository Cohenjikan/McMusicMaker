# -*- coding: utf-8 -*-
"""27_build_chordtest.py — 和弦辐射【最小实验台】(用户设想: 一条信号同刻触发多个音符盒)。

验证: 一条红石信号到达某列时, 能否【同一刻】触发多个真音符盒 = 一个和弦(而非琶音)。
做法(最可靠的"直接相邻"法): 一个被强充能的映射导体 C(在 X 链上), 其【上方 + ±Z 两侧】各坐
一个音符盒(各自垫底映射块)→ C 一通电, 3 个相邻音符盒同刻发声 = 三音和弦。沿链放 2 个和弦列。
判读: 听到 2 个【齐响的和弦】(各一记"咚", 不是分解的"叮咚咚") = 一信号触发和弦成立。

关于 4 音: 直接相邻最多 3 个(上 + ±Z; 另三面=链入/链出/底座被占)。第 4 个需 dust 横向铺开
(你截图那种), 可靠性待测 —— 本台先证"同刻多音"这个核心, 通了再扩 dust。
两条轨道要灯闪一致 = 两条轨用【完全相同的中继器骨架】(同延迟同列)即天然同步, 与单轨同理。

需 RedPiano 模组 + qzpno 资源包。Run: python 27_build_chordtest.py -> /reload -> /function qzcd:setup -> /function qzcd:fire
"""
import os, json, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'qzcd'
OX, OZ, Y = 211000, 0, 255
D = 2
PAD = 'minecraft:cyan_terracotta'        # -> qzpno:pno_c3_mf (base note12=C3)
CHORDS = [(OX + 2, [12, 16, 19]),        # C 大三和弦 (C-E-G)
          (OX + 5, [17, 21, 24])]        # F 大三和弦 (F-A-C)
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"

build = []
def rep_w(x):                            # +X 链中继器
    build.append(f'setblock {x} {Y-1} {OZ} minecraft:stone')
    build.append(f'setblock {x} {Y} {OZ} minecraft:repeater[facing=west,delay={D}]')
def chord(x, notes):                     # 强充能映射导体 C + 上方/±Z 三个相邻音符盒 = 同刻三音
    build.append(f'setblock {x} {Y-1} {OZ} minecraft:redstone_lamp')               # 灯(和弦发声时亮)
    build.append(f'setblock {x} {Y} {OZ} {PAD}')                                   # C: 链导体 + 上音映射
    build.append(f'setblock {x} {Y+1} {OZ} minecraft:note_block[note={notes[0]}]') # 上音(垫 C)
    build.append(f'setblock {x} {Y+2} {OZ} air')
    build.append(f'setblock {x} {Y-1} {OZ+1} {PAD}')                               # +Z 音映射
    build.append(f'setblock {x} {Y} {OZ+1} minecraft:note_block[note={notes[1]}]') # +Z 音(被 C 强充能相邻触发)
    build.append(f'setblock {x} {Y+1} {OZ+1} air')
    build.append(f'setblock {x} {Y-1} {OZ-1} {PAD}')                               # -Z 音映射
    build.append(f'setblock {x} {Y} {OZ-1} minecraft:note_block[note={notes[2]}]') # -Z 音
    build.append(f'setblock {x} {Y+1} {OZ-1} air')

cset = {x for x, _ in CHORDS}
x0, x1 = OX, OX + 6
for x in range(x0, x1 + 1):
    if x in cset:
        chord(x, dict(CHORDS)[x])
    else:
        rep_w(x)

FX0, FX1, FZ0, FZ1 = OX - 2, x1 + 1, OZ - 2, OZ + 2
SX = OX - 1

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 和弦辐射最小台(一信号同刻多音)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))

setup = [f'forceload add {FX0} {FZ0} {FX1} {FZ1}',
         f'fill {FX0} {Y-1} {FZ0} {FX1} {Y+2} {FZ1} air',
         f'setblock {SX} {Y-1} {OZ} minecraft:stone'] + build + [
         f'tp @a {OX + 3} {Y+7} {OZ - 4} 0 65',
         f'tellraw @a ["",{{"text":"[{NS}] 和弦辐射台已建。","color":"aqua"}},{{"text":" /function {NS}:fire -> 应听 2 个齐响的大三和弦(各一记和弦, 非琶音)。"}}]']
w(f'data/{NS}/function/setup.mcfunction', setup)
w(f'data/{NS}/function/load.mcfunction',
  f'tellraw @a {{"text":"[{NS}] 和弦辐射台 loaded. /function {NS}:setup -> /function {NS}:fire","color":"aqua"}}')
w(f'data/{NS}/function/fire.mcfunction',
  [f'tellraw @a {{"text":"[{NS}] fire! 一脉冲应同刻触发各列 3 音(和弦)。","color":"green"}}',
   f'setblock {SX} {Y} {OZ} minecraft:redstone_block', f'schedule function {NS}:fireoff 4t'])
w(f'data/{NS}/function/fireoff.mcfunction', f'setblock {SX} {Y} {OZ} minecraft:air')
w(f'data/{NS}/function/cleanup.mcfunction',
  [f'fill {FX0} {Y-1} {FZ0} {FX1} {Y+2} {FZ1} air', f'forceload remove {FX0} {FZ0} {FX1} {FZ1}',
   f'tellraw @a {{"text":"[{NS}] 已清理。","color":"aqua"}}'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 27 和弦辐射最小台 ===')
print(f'2 个和弦列(C 链上, 各列上+±Z 三音直接相邻强充能, 同刻发声): {CHORDS}')
print(f'占地 x[{FX0}..{FX1}] z[{FZ0}..{FZ1}]')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /function {NS}:setup -> /function {NS}:fire  (听 2 个齐响和弦=一信号触发和弦成立)')
