"""隔离测试 — 单条轨、短机器(MAXCELL=120≈26s,非正曲全长)、每格都触发一个固定节拍音(原版音效,无需资源包)。
目的:判定"周期性断音"是否来自红石长脉冲本身(单轨就能复现 -> 是脉冲/距离问题;单轨干净 -> 是7轨并行问题)。
同样用 tick rate 18.1 + 全程 forceload + 瞬时脉冲,保证与正曲机器机制一致。
Run: <venv-demucs python> 08_test_pulse.py
"""
import os, json, shutil
BRIDGE = r'<external-tool-dir>\nbviz'
NS = 'qztest'
OX, OZ, Y, DELAY = 30000, 0, -59, 2
BASE, RFACING, BATCH = 'white_wool', 'west', 2500
TPS = 18.1
MAXCELL = 120                               # 短测试(~26s):足够听到多次断点周期,又不会卡区块生成
CLICK = 'minecraft:block.note_block.hat'    # 原版音效,均匀节拍,断了一耳朵就听出来

DP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build', f'{NS}_redstone')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b): w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": "qztest pulse isolation"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))  # 缺这条则 buildstep 永不自动跑(GPT 指出)

SZ = OZ
cmd = f'execute as @a at @s run playsound {CLICK} master @s ~ ~ ~ 1 1 1'
build = ['gamerule commandModificationBlockLimit 2147483647', f'setblock {OX-1} {Y-1} {SZ} minecraft:{BASE}']
for c in range(MAXCELL + 1):
    cx = OX + 2 * c
    if c > 0:
        rx = OX + 2 * c - 1
        build += [f'setblock {rx} {Y-1} {SZ} minecraft:{BASE}',
                  f'setblock {rx} {Y} {SZ} minecraft:repeater[facing={RFACING},delay={DELAY}]']
    build.append(f'setblock {cx} {Y-1} {SZ} minecraft:command_block[facing=down,conditional=false]{{Command:"{cmd}",auto:0b}}')
    build.append(f'setblock {cx} {Y} {SZ} minecraft:redstone_wire')
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]

WX0, WZ0, WX1, WZ1 = OX - 4, SZ - 2, OX + 2 * MAXCELL + 2, SZ + 2
flbuild = []; cc = 0
while WX0 + cc * 16 <= WX1:
    a, b = WX0 + cc * 16, min(WX1, WX0 + (cc + 200) * 16)
    flbuild.append(f'forceload add {a} {WZ0} {b} {WZ1}'); cc += 200
SRC = (OX - 1, SZ); TRIG = [f'setblock {SRC[0]} {Y} {SRC[1]} minecraft:air']
SCH = [f'schedule clear {NS}:{f}' for f in ('done', 'fire', 'firestop', 'startbuild')]
END = MAXCELL * DELAY * 2 + 200

wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1',
            f'scoreboard players set PLAY {NS} 0', 'forceload remove all', 'tick rate 20'] + SCH + TRIG
   + [f'tellraw @a "[qztest] loaded. /function {NS}:setup"'])
wf('setup', [f'scoreboard players set PLAY {NS} 0', 'stopsound @a master'] + SCH + TRIG
   + [f'tp @a {OX+MAXCELL} {Y+3} {SZ}', f'schedule function {NS}:startbuild 200t',
      'tellraw @a "[qztest] 加载区块中,约10s后自动建造(短机器,不会卡)..."'])
wf('startbuild', flbuild + [f'scoreboard players set BLD {NS} 0', 'tellraw @a "[qztest] building..."'])
wf('tick', f'execute if score BLD {NS} matches 0.. run function {NS}:buildstep')
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('buildstep', bs)
for k, b in enumerate(batches): wf(f'bld/b{k}', b)
wf('builddone', f'scoreboard players set BLD {NS} -1\ntellraw @a ["",{{"text":"[qztest] built. ","color":"green"}},{{"text":"/function {NS}:play"}}]')
wf('play', [f'execute if score PLAY {NS} matches 1 run return 0', f'scoreboard players set PLAY {NS} 1',
            'stopsound @a master', f'tick rate {TPS}'] + TRIG
   + [f'schedule function {NS}:fire 2t', 'tellraw @a "[qztest] GO — 每格都该响,听有没有周期性断。"'])
wf('fire', flbuild + [f'setblock {SRC[0]} {Y} {SRC[1]} minecraft:redstone_block',
                      f'schedule function {NS}:firestop 6t', f'schedule function {NS}:done {END}t'])
wf('firestop', TRIG)
wf('done', f'scoreboard players set PLAY {NS} 0\nforceload remove all\ntick rate 20\ntellraw @a "[qztest] end."')
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647', f'scoreboard players set PLAY {NS} 0',
               'stopsound @a master', 'forceload remove all', 'tick rate 20'] + SCH + TRIG
   + [f'fill {WX0} {Y-2} {WZ0} {WX1} {Y+6} {WZ1} air', 'tellraw @a "[qztest] cleared."'])

dst = os.path.join(BRIDGE, 'datapacks', f'{NS}_redstone')
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print(f'qztest built: 1 lane, {MAXCELL} cells (same length), every cell fires {CLICK}, tick rate {TPS}')
print(f'batches={len(batches)}  -> deployed bridge {dst}')
