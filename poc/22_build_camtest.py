# -*- coding: utf-8 -*-
"""22_build_camtest.py — 数据包「自动跟随相机」机制测试台(独立小验证)。

验证: 观察者模式 + 每游戏刻 tp + 缓动, 目标点按队列推进(宏读 storage)。
若相机能沿一排路标平滑滑过 -> 机制成立 -> 接到全曲机器(变速跟随脉冲)。
机制(同将用于全曲): CAMX(X*12定点) 每刻向 TGT 缓动; TGT 由 nexttarget 从队列弹出推进; 宏 tp 玩家。

Run: python 22_build_camtest.py   (base python)
"""
import os, json, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'qzcam'
Y, Z = 100, 300
X0, STEP, NWP = 300, 20, 11          # 11 个路标, 间隔20, X=300..500
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(
        ('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": "qzcam 自动跟随相机机制测试"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

XEND = X0 + STEP * (NWP - 1)
# setup: 路标(每20一个金块) + 连续线(便于看相机滑动)
setup = [f'forceload add {X0-4} {Z-4} {XEND+4} {Z+4}',
         f'fill {X0-2} {Y-1} {Z} {XEND+2} {Y-1} {Z} smooth_stone']
for i in range(NWP):
    x = X0 + STEP * i
    setup.append(f'setblock {x} {Y} {Z} minecraft:gold_block')
setup += [f'tp @a {X0} {Y+10} {Z-3} 0 50',
          f'tellraw @a "[{NS}] 测试台已建(X={X0}..{XEND}, 一排金块路标)。/function {NS}:run 看相机是否平滑滑过"']
w(f'data/{NS}/function/setup.mcfunction', setup)
w(f'data/{NS}/function/load.mcfunction',
  [f'scoreboard objectives add {NS} dummy', f'scoreboard players set CAM {NS} 0',
   f'tellraw @a "[{NS}] loaded. /function {NS}:setup -> /function {NS}:run"'])

# 相机机制
CAMY, CAMZ, CYAW, CPITCH = Y + 10, Z - 3, 0, 50
w(f'data/{NS}/function/camtp.mcfunction', f'$tp @a $(x) {CAMY} {CAMZ} {CYAW} {CPITCH}')   # 宏: 仅X动态
w(f'data/{NS}/function/nexttarget.mcfunction',
  [f'execute if score CAM {NS} matches 1 store result score TGT {NS} run data get storage {NS}:cam targets[0] 12.0',
   f'execute if score CAM {NS} matches 1 run data remove storage {NS}:cam targets[0]'])
w(f'data/{NS}/function/camtick.mcfunction',
  [f'scoreboard players operation TMP {NS} = TGT {NS}',
   f'scoreboard players operation TMP {NS} -= CAMX {NS}',
   f'scoreboard players operation TMP {NS} /= F {NS}',           # 缓动: (目标-当前)/F
   f'scoreboard players operation CAMX {NS} += TMP {NS}',
   f'execute store result storage {NS}:cam m.x double 0.0833333 run scoreboard players get CAMX {NS}',  # X*12/12 -> 真X
   f'function {NS}:camtp with storage {NS}:cam m'])
w(f'data/{NS}/function/tick.mcfunction',
  f'execute if score CAM {NS} matches 1 run function {NS}:camtick')

targets = [X0 + STEP * i for i in range(1, NWP)]              # 余下10个目标
run = [f'gamemode spectator @a',
       f'scoreboard players set CAMX {NS} {X0 * 12}',
       f'scoreboard players set TGT {NS} {X0 * 12}',
       f'scoreboard players set F {NS} 8',                    # 缓动系数(越大越慢)
       f'data modify storage {NS}:cam targets set value {targets}',
       f'scoreboard players set CAM {NS} 1',
       f'tellraw @a "[{NS}] run! 相机应从X={X0}平滑滑到X={XEND}(看金块逐个掠过)"']
for i in range(1, NWP):
    run.append(f'schedule function {NS}:nexttarget {i*8}t append')   # 每0.4s(tick20)推进一个目标
run.append(f'schedule function {NS}:camdone {NWP*8 + 30}t')
w(f'data/{NS}/function/run.mcfunction', run)
w(f'data/{NS}/function/camdone.mcfunction',
  [f'scoreboard players set CAM {NS} 0', 'gamemode creative @a', f'tellraw @a "[{NS}] camera done."'])
w(f'data/{NS}/function/cleanup.mcfunction',
  [f'scoreboard players set CAM {NS} 0', 'gamemode creative @a',
   f'fill {X0-2} {Y-1} {Z} {XEND+2} {Y} {Z} air', f'forceload remove {X0-4} {Z-4} {XEND+4} {Z+4}',
   f'tellraw @a "[{NS}] 已清理。"'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 22 自动跟随相机 机制测试台 ===')
print(f'路标 X={X0}..{XEND} (每{STEP}一个金块, 共{NWP})  缓动F=8  目标每8t推进')
print(f'deployed -> {dst}')
print(f'用法: /reload -> /function {NS}:setup -> /function {NS}:run (看相机平滑滑过金块)  清理 /function {NS}:cleanup')
