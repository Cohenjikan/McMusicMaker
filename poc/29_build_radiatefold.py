# -*- coding: utf-8 -*-
"""29_build_radiatefold.py — 折叠 + 辐射和弦【集成最小台】。

把已分别验证的两件事合到一起, 验证它们【共存的几何】:
  - 折叠(26 已验): 平面蛇形, 水平拐角/U形, 行距 ROW_DZ。
  - 辐射和弦(27 已验): 一个强充能导体 C 同刻触发 上+±Z 三音(一个三和弦)。
难点 = 和弦在 ±Z 辐射, 折叠也在 Z 上换行 -> 行距必须 >= 和弦Z宽+间隙(本台 ROW_DZ=4: 和弦占 ±1,
  行间留 1 空)。验证: 沿折叠链每个和弦列同刻三音齐响, 拐过 U 形仍齐响、不串扰。
判读(fire): 听到 4 个【依次升高的大三和弦】(各一记齐响, 穿过 1 个 U 形弯) = 折叠+辐射可共存
  -> 整机"2轨道+折叠"只是把这条链(a)复制成 2 条 ±Z 错开(=两轨, 共享骨架天然同步)(b)多铺几行。

注: 单轨这里就是和弦轨; "2 轨"= 把此链整体平移 +Z 复制一份(上 4 音 / 下 4 音分轨), 骨架逐格相同=灯闪一致。
需 RedPiano 模组 + qzpno 资源包。Run: python 29_build_radiatefold.py -> /reload -> /function qzrf:setup -> /function qzrf:fire
"""
import os, json, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'qzrf'
OX, OZ, Y = 213000, 0, 255
D, ROWS, ROWLEN, ROW_DZ = 2, 2, 8, 4
FACE = {(1, 0): 'west', (-1, 0): 'east', (0, 1): 'north', (0, -1): 'south'}
PAD = 'minecraft:cyan_terracotta'
CHORD_ROOTS = [7, 10, 14, 17]            # 4 个三和弦根音(升高); 各 [root, root+4, root+7]
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"
SX = OX - 1

b = []
def rep(x, z, d):
    b.append(f'setblock {x} {Y-1} {z} minecraft:stone')
    b.append(f'setblock {x} {Y} {z} minecraft:repeater[facing={FACE[d]},delay={D}]')
def corner(x, z):                        # 0延迟拐角导体(无音)
    b.append(f'setblock {x} {Y-1} {z} minecraft:redstone_lamp')
    b.append(f'setblock {x} {Y} {z} minecraft:stone')
def chordcol(x, z, root):                # 0延迟辐射和弦: C(链导体+上音) + ±Z 两音, 同刻三音齐响
    n = [root, min(24, root + 4), min(24, root + 7)]
    b.append(f'setblock {x} {Y-1} {z} minecraft:redstone_lamp')
    b.append(f'setblock {x} {Y} {z} {PAD}')
    b.append(f'setblock {x} {Y+1} {z} minecraft:note_block[note={n[0]}]'); b.append(f'setblock {x} {Y+2} {z} air')
    b.append(f'setblock {x} {Y-1} {z+1} {PAD}')
    b.append(f'setblock {x} {Y} {z+1} minecraft:note_block[note={n[1]}]'); b.append(f'setblock {x} {Y+1} {z+1} air')
    b.append(f'setblock {x} {Y-1} {z-1} {PAD}')
    b.append(f'setblock {x} {Y} {z-1} minecraft:note_block[note={n[2]}]'); b.append(f'setblock {x} {Y+1} {z-1} air')

cx, cz, ci = OX, OZ, 0
for r in range(ROWS):
    d = (1, 0) if r % 2 == 0 else (-1, 0)
    for c in range(ROWLEN):
        if c % 3 == 2 and ci < len(CHORD_ROOTS):
            chordcol(cx, cz, CHORD_ROOTS[ci]); ci += 1
        else:
            rep(cx, cz, d)
        cx += d[0]; cz += d[1]
    if r < ROWS - 1:                     # U 形: 拐角 + (ROW_DZ-1)个+Z连接rep + 拐角
        corner(cx, cz)
        for _ in range(ROW_DZ - 1):
            cz += 1; rep(cx, cz, (0, 1))
        cz += 1; corner(cx, cz)
        nd = (1, 0) if (r + 1) % 2 == 0 else (-1, 0)
        cx += nd[0]; cz += nd[1]

FX0, FX1, FZ0, FZ1 = OX - 2, OX + ROWLEN + 1, OZ - 2, OZ + (ROWS - 1) * ROW_DZ + 2
DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 折叠+辐射和弦 集成最小台"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w(f'data/{NS}/function/setup.mcfunction',
  [f'forceload add {FX0} {FZ0} {FX1} {FZ1}', f'fill {FX0} {Y-1} {FZ0} {FX1} {Y+2} {FZ1} air',
   f'setblock {SX} {Y-1} {OZ} minecraft:stone'] + b +
  [f'tp @a {OX+4} {Y+9} {OZ+1} 0 75',
   f'tellraw @a ["",{{"text":"[{NS}] 折叠+辐射集成台已建。","color":"aqua"}},{{"text":" /function {NS}:fire -> 应听 4 个升高的齐响三和弦, 穿过 1 个 U 形弯。"}}]'])
w(f'data/{NS}/function/load.mcfunction', f'tellraw @a {{"text":"[{NS}] 折叠+辐射台 loaded. /function {NS}:setup -> /function {NS}:fire","color":"aqua"}}')
w(f'data/{NS}/function/fire.mcfunction',
  [f'tellraw @a {{"text":"[{NS}] fire! 折叠链上每个和弦列应同刻三音齐响, 升高 4 次。","color":"green"}}',
   f'setblock {SX} {Y} {OZ} minecraft:redstone_block', f'schedule function {NS}:fireoff 4t'])
w(f'data/{NS}/function/fireoff.mcfunction', f'setblock {SX} {Y} {OZ} minecraft:air')
w(f'data/{NS}/function/cleanup.mcfunction',
  [f'fill {FX0} {Y-1} {FZ0} {FX1} {Y+2} {FZ1} air', f'forceload remove {FX0} {FZ0} {FX1} {FZ1}', f'tellraw @a "[{NS}] 已清理。"'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 29 折叠+辐射和弦 集成最小台 ===')
print(f'蛇形 {ROWS}行x{ROWLEN}格 行距{ROW_DZ}; {len(CHORD_ROOTS)} 个三和弦(根 {CHORD_ROOTS}, 各上+±Z三音) 穿 1 个 U 形')
print(f'部署 -> {dst}  用法: /reload -> /function {NS}:setup -> /function {NS}:fire (听 4 个升高齐响和弦)')
