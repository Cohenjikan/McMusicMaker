# -*- coding: utf-8 -*-
"""20_build_geomproto.py — 真音符盒机器「几何原型」(可靠分接版)。

验证: 行进的红石脉冲能否依次触发真音符盒。音符盒需"上方空气", 故脉冲不能盖顶,
也不能靠 dust 侧连(红石线不自动连音符盒)。用**中继器直插**(强充能, 必触发)。

3 排布局(z 由南到北):
  ZN=BZ   : 音符盒行(垫 cyan_terracotta=pno_c3_mf, 上方空气, note=0/6/12/18/24)
  ZT=BZ-1 : 分接中继器(facing=north 输入北/输出南+Z 插入音符盒)
  ZL=BZ-2 : 脉冲线(分接点 dust + 之间 facing=west 中继器排序; 脉冲自西向东行进)
判读: 上行钢琴琶音(5声渐高) = 行进脉冲触发真音符盒成立 -> 建全机器。

facing 语义(已核实 DiodeBlock): FACING=输入端(背面), 输出在对面。
  脉冲线向东(+X): 源在西 -> facing=west(输入西/输出东)。
  分接插入音符盒向南(+Z): 输入北(脉冲线) -> facing=north。
前提: 已重启MC装新mod + qzpno资源包开。
Run: python 20_build_geomproto.py
"""
import os, json, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'qzgeo'
Y0 = -60
BX, BZ = 200, 420
PAD = 'cyan_terracotta'          # -> qzpno:pno_c3_mf
NOTES = [0, 6, 12, 18, 24]
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"
ZN, ZT, ZL = BZ, BZ - 1, BZ - 2

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(
        ('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": "qzgeo 真音符盒机器几何原型(中继器直插)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))

N = len(NOTES)
FX0, FZ0, FX1, FZ1 = BX - 4, ZL - 2, BX + 2*N + 2, ZN + 2
setup = [f'forceload add {FX0} {FZ0} {FX1} {FZ1}',
         f'fill {FX0} {Y0-1} {FZ0} {FX1} {Y0+4} {FZ1} air',
         f'fill {FX0} {Y0-1} {FZ0} {FX1} {Y0-1} {FZ1} smooth_stone']
for i, note in enumerate(NOTES):
    x = BX + 2*i
    setup.append(f'setblock {x} {Y0} {ZN} minecraft:{PAD}')                       # 垫底映射方块
    setup.append(f'setblock {x} {Y0+1} {ZN} minecraft:note_block[note={note}]')   # 真音符盒(上方空气)
    setup.append(f'setblock {x} {Y0} {ZT} minecraft:smooth_stone')
    setup.append(f'setblock {x} {Y0+1} {ZT} minecraft:repeater[facing=north,delay=1]')  # 直插音符盒(+Z)
    setup.append(f'setblock {x} {Y0} {ZL} minecraft:smooth_stone')
    setup.append(f'setblock {x} {Y0+1} {ZL} minecraft:redstone_wire')             # 分接点 dust
    if i < N - 1:
        rx = x + 1
        setup.append(f'setblock {rx} {Y0} {ZL} minecraft:smooth_stone')
        setup.append(f'setblock {rx} {Y0+1} {ZL} minecraft:repeater[facing=west,delay=2]')  # 排序
# 源(西端)
setup.append(f'setblock {BX-1} {Y0} {ZL} minecraft:smooth_stone')
setup.append(f'setblock {BX-1} {Y0+1} {ZL} minecraft:redstone_wire')
setup.append(f'setblock {BX-2} {Y0} {ZL} minecraft:smooth_stone')
setup += [f'tp @a {BX + N} {Y0+3} {ZN + 3} 180 35',
          f'tellraw @a ["",{{"text":"[{NS}] 几何原型已建。","color":"aqua"}},'
          f'{{"text":" /function {NS}:fire -> 听是否上行琶音(=行进脉冲依次触发真音符盒)"}}]']
w(f'data/{NS}/function/setup.mcfunction', setup)
w(f'data/{NS}/function/load.mcfunction',
  f'tellraw @a {{"text":"[{NS}] loaded (需重启MC装mod). /function {NS}:setup -> /function {NS}:fire","color":"aqua"}}')

w(f'data/{NS}/function/fire.mcfunction',
  [f'tellraw @a {{"text":"[{NS}] fire! 脉冲向东行进, 应依次触发 note 0/6/12/18/24","color":"green"}}',
   f'setblock {BX-2} {Y0+1} {ZL} minecraft:redstone_block',
   f'schedule function {NS}:fireoff 16t'])
w(f'data/{NS}/function/fireoff.mcfunction', f'setblock {BX-2} {Y0+1} {ZL} minecraft:air')
w(f'data/{NS}/function/cleanup.mcfunction',
  [f'fill {FX0} {Y0-1} {FZ0} {FX1} {Y0+4} {FZ1} air',
   f'forceload remove {FX0} {FZ0} {FX1} {FZ1}',
   f'tellraw @a {{"text":"[{NS}] 已清理。","color":"aqua"}}'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 20 真音符盒几何原型(中继器直插) ===')
print(f'垫底={PAD}(->pno_c3_mf)  音符盒={N}  note={NOTES}')
print(f'3排: 音符盒z={ZN} / 分接中继器z={ZT}(facing=north) / 脉冲线z={ZL}(facing=west排序)')
print(f'deployed -> {dst}')
print(f'用法: 重启MC -> /reload -> /function {NS}:setup -> /function {NS}:fire')
