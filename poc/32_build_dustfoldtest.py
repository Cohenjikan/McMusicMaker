# -*- coding: utf-8 -*-
"""32_build_dustfoldtest.py — 红石粉【0延迟U弯】最小验证台(31 折叠机的新几何)。

26 验过【中继器拐角】可平面折叠; 31 改用【纯红石粉U弯】(0延迟, 保 24/30 时序公式不变)。
本台单独验这个新弯: 单轨蛇形, 每行 6 格, 每 3 格一个升音, 行间用红石粉腿连。
判读(fire): 听到 7 个【依次升高】的音(0/4/8/.../24), 穿过 3 个红石粉U弯 = 0延迟弯成立
  -> 31 整机的折叠几何可信。某音后断 = 那个弯没通(把腿改回中继器即可, 见 31 注释)。

需 RedPiano 模组 + qzpno 资源包(cyan_terracotta -> pno_c3_mf)。
Run: python 32_build_dustfoldtest.py -> /reload -> /function qzdf:setup -> /function qzdf:fire
"""
import os, sys, json, shutil
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
NS, OX, OZ, Y = 'qzdf', 209000, 0, 255
D, ROWLEN, ROW_DZ = 2, 6, 6
PAD = 'minecraft:cyan_terracotta'
RFACE = {1: 'west', -1: 'east'}
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"
NCELLS = 22                                  # 22 格 -> ~3 行 -> 3 个 U 弯

# cells: 每 3 格一个升音 trig(0延迟), 其余 rep(delay D)
cells = []
ni = 0
for i in range(NCELLS):
    if i % 3 == 2:
        cells.append(('trig', min(24, ni * 4))); ni += 1
    else:
        cells.append(('rep', D))

# 折叠布局(同 31: 只在 'rep' 前换行)
pos, legs = [None] * NCELLS, []
x, z, d, col = 0, 0, 1, 0
for i in range(NCELLS):
    pos[i] = (x, z, d); x += d; col += 1
    last = (i == NCELLS - 1)
    if (not last) and col >= ROWLEN and cells[i + 1][0] == 'rep':
        legs.append((x, z, z + ROW_DZ)); z += ROW_DZ; d = -d; x += d; col = 0

b = [f'setblock {OX-1} {Y-1} {OZ} minecraft:stone']
for i, (xo, zo, dirx) in enumerate(pos):
    X, Z = OX + xo, OZ + zo
    kind, v = cells[i]
    b.append(f'setblock {X} {Y-1} {Z} minecraft:redstone_lamp')
    if kind == 'rep':
        b.append(f'setblock {X} {Y} {Z} minecraft:repeater[facing={RFACE[dirx]},delay={v}]')
    else:
        b.append(f'setblock {X} {Y} {Z} {PAD}')
        b.append(f'setblock {X} {Y+1} {Z} minecraft:note_block[note={v}]')
        b.append(f'setblock {X} {Y+2} {Z} air')
for (xleg, zf, zt) in legs:
    for zz in range(zf, zt + 1):
        b.append(f'setblock {OX+xleg} {Y-1} {OZ+zz} minecraft:stone')
        b.append(f'setblock {OX+xleg} {Y} {OZ+zz} minecraft:redstone_wire')

FX0, FX1, FZ0, FZ1 = OX - 2, OX + ROWLEN + 1, OZ - 2, OZ + (len(legs)) * ROW_DZ + 2
DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 红石粉0延迟U弯验证台"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w(f'data/{NS}/function/setup.mcfunction',
  [f'forceload add {FX0} {FZ0} {FX1} {FZ1}', f'fill {FX0} {Y-1} {FZ0} {FX1} {Y+2} {FZ1} air',
   f'setblock {OX-1} {Y-1} {OZ} minecraft:stone'] + b +
  [f'tp @a {OX+ROWLEN//2} {Y+9} {OZ-3} 0 70',
   f'tellraw @a ["",{{"text":"[{NS}] 红石粉U弯台已建。","color":"aqua"}},{{"text":" /function {NS}:fire -> 应听 {ni} 个升音, 穿 {len(legs)} 个红石粉弯。"}}]'])
w(f'data/{NS}/function/load.mcfunction', f'tellraw @a {{"text":"[{NS}] 红石粉U弯台 loaded. /function {NS}:setup -> :fire","color":"aqua"}}')
w(f'data/{NS}/function/fire.mcfunction',
  [f'tellraw @a {{"text":"[{NS}] fire! 升音应依次响起穿过红石粉弯。","color":"green"}}',
   f'setblock {OX-1} {Y} {OZ} minecraft:redstone_block', f'schedule function {NS}:fireoff 4t'])
w(f'data/{NS}/function/fireoff.mcfunction', f'setblock {OX-1} {Y} {OZ} minecraft:air')
w(f'data/{NS}/function/cleanup.mcfunction',
  [f'fill {FX0} {Y-1} {FZ0} {FX1} {Y+2} {FZ1} air', f'forceload remove {FX0} {FZ0} {FX1} {FZ1}', f'tellraw @a "[{NS}] 已清理。"'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 32 红石粉0延迟U弯验证台 ===')
print(f'单轨蛇形 {NCELLS}格, 每行{ROWLEN}, {len(legs)}个红石粉U弯, {ni}个升音(note {[min(24,k*4) for k in range(ni)]})')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup -> /function {NS}:fire (听{ni}个升音=弯通)')
