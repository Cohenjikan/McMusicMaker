# -*- coding: utf-8 -*-
"""28_build_dusttest.py — dust 触发音符盒【最小验证】(为辐射和弦的"第4音"探路)。

直接相邻最多 3 音(上+±Z); 第 4 音需把信号用红石线(dust)横向引出再触发音符盒。
本台验证: 被强充能的导体 C 引出的【红石线末端/旁侧】能否触发真音符盒。
判读(fire 后):
  - 参考音(C 正上方, 直接相邻, 必响)= note12。
  - dust 末端音(C -> dust 2格 -> 音符盒)= note19。响 = dust 能触发, 第4音可行。
  - dust 旁侧音(dust 线旁贴一个音符盒)= note24。响 = 旁侧也行(可一线串多音)。
听到 2 音(只参考音)= dust 不触发, 改用别法; 听到 3 音 = dust 末端可行; 听到全部 = 旁侧也行。

需 RedPiano 模组 + qzpno 资源包。Run: python 28_build_dusttest.py -> /reload -> /function qzdt:setup -> /function qzdt:fire
"""
import os, json, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'qzdt'
OX, OZ, Y = 212000, 0, 255
PAD = 'minecraft:cyan_terracotta'        # -> pno_c3_mf
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"
SX = OX - 1                              # 源 redstone_block(fire 放)

b = []
def s(x, y, z, blk): b.append(f'setblock {x} {y} {z} {blk}')
# 进信号: 源 -> repeater -> C(强充能映射导体)
s(OX, Y-1, OZ, 'minecraft:stone'); s(OX, Y, OZ, 'minecraft:repeater[facing=west,delay=2]')   # 读源, 输出+X 强充 C
s(OX+1, Y-1, OZ, 'minecraft:redstone_lamp'); s(OX+1, Y, OZ, PAD)                              # C
# 参考音: C 正上方(直接相邻, 必响)
s(OX+1, Y+1, OZ, 'minecraft:note_block[note=12]'); s(OX+1, Y+2, OZ, 'air')
# dust 末端音: C -> dust(-Z 2格) -> 音符盒(z=-3)
s(OX+1, Y-1, OZ-1, 'minecraft:stone'); s(OX+1, Y, OZ-1, 'minecraft:redstone_wire')            # dust1(贴 C, 被强充能=15)
s(OX+1, Y-1, OZ-2, 'minecraft:stone'); s(OX+1, Y, OZ-2, 'minecraft:redstone_wire')            # dust2
s(OX+1, Y-1, OZ-3, PAD); s(OX+1, Y, OZ-3, 'minecraft:note_block[note=19]'); s(OX+1, Y+1, OZ-3, 'air')  # 末端音(dust 指入)
# dust 旁侧音: 在 dust2 旁(+X 侧)贴一个音符盒(z=-2, x=OX+2)
s(OX+2, Y-1, OZ-2, PAD); s(OX+2, Y, OZ-2, 'minecraft:note_block[note=24]'); s(OX+2, Y+1, OZ-2, 'air')   # 旁侧音(dust 旁邻)

FX0, FX1, FZ0, FZ1 = OX-2, OX+3, OZ-4, OZ+2
DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": f"{NS} dust 触发音符盒验证"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w(f'data/{NS}/function/setup.mcfunction',
  [f'forceload add {FX0} {FZ0} {FX1} {FZ1}', f'fill {FX0} {Y-1} {FZ0} {FX1} {Y+2} {FZ1} air',
   f'setblock {SX} {Y-1} {OZ} minecraft:stone'] + b +
  [f'tp @a {OX+1} {Y+6} {OZ-7} 0 55',
   f'tellraw @a ["",{{"text":"[{NS}] dust 验证台已建。","color":"aqua"}},{{"text":" /function {NS}:fire -> 听几个音: 1(只参考)=dust不行; 2=末端行; 3=旁侧也行。"}}]'])
w(f'data/{NS}/function/load.mcfunction', f'tellraw @a {{"text":"[{NS}] dust 验证台 loaded. /function {NS}:setup -> /function {NS}:fire","color":"aqua"}}')
w(f'data/{NS}/function/fire.mcfunction',
  [f'tellraw @a {{"text":"[{NS}] fire! 参考音(上)必响; 听 dust 末端音/旁侧音是否也响。","color":"green"}}',
   f'setblock {SX} {Y} {OZ} minecraft:redstone_block', f'schedule function {NS}:fireoff 4t'])
w(f'data/{NS}/function/fireoff.mcfunction', f'setblock {SX} {Y} {OZ} minecraft:air')
w(f'data/{NS}/function/cleanup.mcfunction',
  [f'fill {FX0} {Y-1} {FZ0} {FX1} {Y+2} {FZ1} air', f'forceload remove {FX0} {FZ0} {FX1} {FZ1}', f'tellraw @a "[{NS}] 已清理。"'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 28 dust 触发验证台 ===')
print('参考音 note12(上, 必响) / dust末端音 note19 / dust旁侧音 note24')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /function {NS}:setup -> /function {NS}:fire  (响几个音判断 dust 是否触发)')
