# -*- coding: utf-8 -*-
"""26_build_foldtest.py — 折叠【最小实验台】。

验证目标(折叠唯一未证的几何): 一条红石中继器链能否在【水平面内拐 90°/U 形】
而不断信号、且保时序地依次触发真音符盒。
做法: 一条信号蛇行 3 行(+X / -X 交替, 用 +Z 连接), 沿途升音(note 递增)。
判读: 听到 6 个音【依次匀速上行】(0→5→10→15→20→24) = 拐角成立、平面折叠可行
      -> 再做整机 fold builder。某个音之后断了 = 那个拐角没通。

拐角原理(已核实 facing 语义: 输出方向 = facing 的反向; facing=west 输出 +X):
  进 repeater 输出 d 强充【拐角导体块 C】(0 延迟) -> 出 repeater 坐 C 邻格、facing
  使其从 C 读入并沿新方向输出。导体不加延迟, 仅出 repeater 自身 1 拍(并入既有节奏格)。

需 RedPiano 模组 + qzpno 资源包(垫底 cyan_terracotta -> pno_c3_mf)。
Run: python 26_build_foldtest.py  -> 游戏内 /reload -> /function qzft:setup -> /function qzft:fire
"""
import os, json, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'qzft'
OX, OZ, Y = 210000, 0, 255
D = 2                                   # 统一中继器延迟(红石刻) -> 匀速
ROWS, ROWLEN, ROW_DZ = 3, 8, 2          # 3 行蛇形, 每行 8 格, 行距 2(+Z 连接)
PAD = 'minecraft:cyan_terracotta'       # -> qzpno:pno_c3_mf
FACE = {(1, 0): 'west', (-1, 0): 'east', (0, 1): 'north', (0, -1): 'south'}   # 输出方向 -> facing(=反向)
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"

build = []
def rep(x, z, d):
    build.append(f'setblock {x} {Y-1} {z} minecraft:stone')
    build.append(f'setblock {x} {Y} {z} minecraft:repeater[facing={FACE[d]},delay={D}]')
def cond(x, z, note=None):              # 0 延迟导体; 有 note 则垫映射块+音符盒(发声格)
    build.append(f'setblock {x} {Y-1} {z} minecraft:redstone_lamp')              # 灯: 脉冲过时点亮, 可见蛇行
    build.append(f'setblock {x} {Y} {z} {PAD if note is not None else "minecraft:stone"}')
    if note is not None:
        build.append(f'setblock {x} {Y+1} {z} minecraft:note_block[note={note}]')
        build.append(f'setblock {x} {Y+2} {z} air')

# ---- 蛇行铺设 ----
cx, cz = OX, OZ
ni = 0; notes = []
for r in range(ROWS):
    d = (1, 0) if r % 2 == 0 else (-1, 0)                # 偶行 +X, 奇行 -X
    for c in range(ROWLEN):
        if c % 3 == 2:                                   # 每 3 格插一个发声格(0延迟), 升音
            note = min(24, ni * 5); ni += 1
            cond(cx, cz, note); notes.append((cx, cz, note))
        else:
            rep(cx, cz, d)
        cx += d[0]; cz += d[1]
    if r < ROWS - 1:                                     # U 形: 拐角1(转+Z) -> 连接rep -> 拐角2(转下一行)
        cond(cx, cz)                                     # C1: 收 d, 强充
        cz += 1; rep(cx, cz, (0, 1))                     # +Z 连接中继器(facing=north 读 C1 -> 输出 +Z)
        cz += 1; cond(cx, cz)                            # C2: 收 +Z, 强充 -> 喂下一行
        nd = (1, 0) if (r + 1) % 2 == 0 else (-1, 0)
        cx += nd[0]; cz += nd[1]                         # 进入下一行首格

# 边界(forceload + 清理)
xs = [OX - 2, OX + ROWLEN + 1]; zs = [OZ - 1, OZ + (ROWS - 1) * ROW_DZ + 1]
FX0, FX1 = min(xs), max(xs); FZ0, FZ1 = min(zs), max(zs)
SX = OX - 1                                              # 源(redstone_block fire 时放)喂第一个 +X repeater

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 折叠最小实验台(平面蛇形拐角验证)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))

setup = [f'forceload add {FX0} {FZ0} {FX1} {FZ1}',
         f'fill {FX0} {Y-1} {FZ0} {FX1} {Y+2} {FZ1} air',
         f'setblock {SX} {Y-1} {OZ} minecraft:stone'] + build + [
         f'tp @a {OX + ROWLEN//2} {Y+8} {OZ - 4} 0 75',
         f'tellraw @a ["",{{"text":"[{NS}] 折叠实验台已建。","color":"aqua"}},{{"text":" /function {NS}:fire -> 应听 6 音匀速上行(0/5/10/15/20/24), 灯沿蛇形流动并转过拐角。"}}]']
w(f'data/{NS}/function/setup.mcfunction', setup)
w(f'data/{NS}/function/load.mcfunction',
  f'tellraw @a {{"text":"[{NS}] 折叠实验台 loaded. /function {NS}:setup -> /function {NS}:fire","color":"aqua"}}')
w(f'data/{NS}/function/fire.mcfunction',
  [f'tellraw @a {{"text":"[{NS}] fire! 脉冲蛇行穿过 2 个 U 形拐角, 应依次升音。","color":"green"}}',
   f'setblock {SX} {Y} {OZ} minecraft:redstone_block',
   f'schedule function {NS}:fireoff 4t'])
w(f'data/{NS}/function/fireoff.mcfunction', f'setblock {SX} {Y} {OZ} minecraft:air')
w(f'data/{NS}/function/cleanup.mcfunction',
  [f'fill {FX0} {Y-1} {FZ0} {FX1} {Y+2} {FZ1} air', f'forceload remove {FX0} {FZ0} {FX1} {FZ1}',
   f'tellraw @a {{"text":"[{NS}] 已清理。","color":"aqua"}}'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 26 折叠最小实验台 ===')
print(f'蛇形 {ROWS}行 x {ROWLEN}格, 行距{ROW_DZ}, 统一 delay-{D}; 发声格 {len(notes)} 个(升音), 2 个 U 形拐角')
print(f'音符(按脉冲到达序): {[n for _,_,n in notes]}')
print(f'占地 x[{FX0}..{FX1}] z[{FZ0}..{FZ1}]  cells≈{ROWS*ROWLEN+ (ROWS-1)*3}')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /function {NS}:setup -> /function {NS}:fire  (听 6 音匀速上行=拐角通)')
