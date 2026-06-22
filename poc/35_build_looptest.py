# -*- coding: utf-8 -*-
"""35_build_looptest.py — 纯红石【反馈环时钟】最小验证台(Task 3 本地播放器的新机构)。

Task 3 = 不用"长条一次性脉冲", 改用【红石反馈环】当主动时钟: 脉冲扫完音带 -> 经二极管(单向中继器)
  绕回源点 -> 重新注入 -> 自动循环播放(本地 jukebox)。本台用一条短直音带单独验这个环:
  [播放]注入一次 -> 3 个升音应【无限循环】响起(环=主动时钟); [停止]切断反馈门 -> 当前一遍后停。
判读: 听到 0/12/24 三音反复循环 = 反馈环成立 -> 34 整机可用此环驱动。第一遍后就没了 = 反馈没接通。

机构要点:
  - 源节点 SN(OX-1) = 红石粉, 喂 cell0(facing=west)。注入 = [播放] 在 OX-2 放红石块 4t。
  - 反馈: 音带出口 -> 下移到回流道(z=OZ-2) -> 【二极管中继器】(单向, 防 SN 反灌音带) -> 回流到 OX-1 -> 经【门 G】上到 SN。
  - 门 G(OX-1,OZ-1): [停止]置 air 切断环; [播放]置红石粉接通环 + 注入。
  - SN 下垫红石灯 = 每循环一次闪一下(可见节拍/周期)。
需 RedPiano 模组 + qzpno 资源包。Run: python 35_build_looptest.py -> /reload -> /tick rate 80 -> /function qzlp:setup -> 按[播放]/[停止]
"""
import os, sys, json, shutil
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
NS, OX, OZ, Y = 'qzlp', 207000, 0, 255
D = 4                                  # 每格延迟(红石刻); tick80 下 0.1s/格
PAD = 'minecraft:cyan_terracotta'      # -> qzpno:pno_c3_mf
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界 (1)/datapacks"

# 直音带: 0=rep 1=rep 2=trig(0) 3=rep 4=trig(12) 5=rep 6=trig(24); 出口在 OX+7
cells = [('rep', D), ('rep', D), ('trig', 0), ('rep', D), ('trig', 12), ('rep', D), ('trig', 24)]
NC = len(cells); EXITX = OX + NC

b = []
def S(x, y, z, blk): b.append(f'setblock {x} {y} {z} {blk}')
# 源节点 + 时钟灯
S(OX - 1, Y - 1, OZ, 'minecraft:redstone_lamp')          # 时钟灯(SN 通电=亮)
S(OX - 1, Y, OZ, 'minecraft:redstone_wire')               # 源节点 SN
# 音带
for i, (kind, v) in enumerate(cells):
    X = OX + i
    if kind == 'rep':
        S(X, Y - 1, OZ, 'minecraft:stone'); S(X, Y, OZ, f'minecraft:repeater[facing=west,delay={v}]')
    else:
        S(X, Y - 1, OZ, 'minecraft:stone'); S(X, Y, OZ, PAD)
        S(X, Y + 1, OZ, f'minecraft:note_block[note={v}]'); S(X, Y + 2, OZ, 'air')
# 出口 -> 回流道(z=OZ-2): 竖直下移 + 二极管(单向 -X) + 回流 dust
S(EXITX, Y - 1, OZ, 'minecraft:stone'); S(EXITX, Y, OZ, 'minecraft:redstone_wire')          # 出口拾取
S(EXITX, Y - 1, OZ - 1, 'minecraft:stone'); S(EXITX, Y, OZ - 1, 'minecraft:redstone_wire')  # 下移 z
S(EXITX, Y - 1, OZ - 2, 'minecraft:stone'); S(EXITX, Y, OZ - 2, 'minecraft:redstone_wire')
S(EXITX - 1, Y - 1, OZ - 2, 'minecraft:stone')
S(EXITX - 1, Y, OZ - 2, 'minecraft:repeater[facing=east,delay=1]')   # 二极管: 单向流 -X(防反灌)
for x in range(OX - 1, EXITX - 1):                                    # 回流 dust 道 (-X) 到 OX-1
    S(x, Y - 1, OZ - 2, 'minecraft:stone'); S(x, Y, OZ - 2, 'minecraft:redstone_wire')
# 门 G: (OX-1,OZ-1) 连接回流道(OZ-2) 到 SN(OZ)
S(OX - 1, Y - 1, OZ - 1, 'minecraft:stone'); S(OX - 1, Y, OZ - 1, 'minecraft:redstone_wire')  # G(默认接通)

FX0, FX1, FZ0, FZ1 = OX - 4, EXITX + 2, OZ - 4, OZ + 2
DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": f"{NS} 红石反馈环时钟验证台"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
PBX = OX - 4
def btn(bx, cmd, label):
    return [f'setblock {bx} {Y-1} {OZ} minecraft:redstone_lamp',
            f'setblock {bx} {Y} {OZ} minecraft:command_block[facing=up]{{Command:"{cmd}",auto:0b}}',
            f'setblock {bx} {Y+1} {OZ} minecraft:stone_button[face=floor]',
            'setblock %d %d %d minecraft:oak_sign[rotation=0]{front_text:{messages:[\'{"text":"%s"}\']}}' % (bx, Y, OZ - 2, label)]
w(f'data/{NS}/function/setup.mcfunction',
  [f'forceload add {FX0} {FZ0} {FX1} {FZ1}', f'fill {FX0} {Y-1} {FZ0} {FX1} {Y+2} {FZ1} air'] + b
  + btn(PBX, f'function {NS}:play', '[播放]') + btn(PBX - 2, f'function {NS}:stop', '[停止]')
  + [f'tp @a {OX+3} {Y+8} {OZ-5} 0 65',
     f'tellraw @a ["",{{"text":"[{NS}] 反馈环台已建。","color":"aqua"}},{{"text":" 按[播放] -> 3升音应无限循环; [停止]停。"}}]'])
w(f'data/{NS}/function/load.mcfunction', f'tellraw @a {{"text":"[{NS}] 反馈环台 loaded. /tick rate 80 -> /function {NS}:setup","color":"aqua"}}')
w(f'data/{NS}/function/play.mcfunction',
  [f'setblock {OX-1} {Y} {OZ-1} minecraft:redstone_wire',            # 接通门 G
   f'setblock {OX-2} {Y} {OZ} minecraft:redstone_block',            # 注入
   f'schedule function {NS}:injoff 4t',
   f'tellraw @a {{"text":"[{NS}] 播放(循环)。","color":"green"}}'])
w(f'data/{NS}/function/injoff.mcfunction', f'setblock {OX-2} {Y} {OZ} minecraft:air')
w(f'data/{NS}/function/stop.mcfunction',
  [f'setblock {OX-1} {Y} {OZ-1} minecraft:air',                     # 切断门 G -> 环死
   f'setblock {OX-2} {Y} {OZ} minecraft:air',
   'stopsound @a',                                                  # ★ 模组在 RECORDS 类别, 不带源才停得掉
   f'tellraw @a {{"text":"[{NS}] 停止(切断反馈环)。","color":"yellow"}}'])
w(f'data/{NS}/function/cleanup.mcfunction',
  [f'fill {FX0} {Y-1} {FZ0} {FX1} {Y+2} {FZ1} air', f'forceload remove {FX0} {FZ0} {FX1} {FZ1}', f'tellraw @a "[{NS}] 已清理。"'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 35 红石反馈环时钟验证台 ===')
print(f'直音带 {NC}格(3升音 0/12/24), 出口 OX+{NC} -> 二极管单向回流 -> 门G -> 源 = 自循环环')
print(f'部署 -> {dst}')
print(f'用法: /reload -> /tick rate 80 -> /function {NS}:setup -> 按[播放](应无限循环) / [停止]')
