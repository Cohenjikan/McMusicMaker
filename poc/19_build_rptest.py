# -*- coding: utf-8 -*-
"""19_build_rptest.py — RedPiano 模组 v1 验证台(真音符盒 + 垫底映射方块)。

验证 mixin: 真·音符盒(minecraft:note_block)垫在映射方块上, 被红石触发时
是否播我们的钢琴采样 + 随 note 移调。映射(与 RedPianoMap.java v1 一致):
  white_concrete -> qzpno:pno_c3_mf (C3=48, 中)
  gold_block     -> qzpno:pno_c1_mf (低)
  iron_block     -> qzpno:pno_c5_mf (高)

判读:
  white_concrete note=0/6/12/18/24 -> 应上行琶音(移调成立 + 自定义音色)
  gold/iron @12 -> 不同垫底块 -> 不同采样(低/高)

前提: ① mod jar 已进 mods + **重启 MC** ② qzpno 资源包启用。
Run: python 19_build_rptest.py
"""
import os, json, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'qzrptest'
Y0 = -60                          # 垫底映射方块层; 音符盒 Y0+1; 上方 Y0+2 留空气
BX, BZ = 200, 360
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"

SEQ = [
    ('white_concrete', 0,  'white_concrete note0 (应=C2)'),
    ('white_concrete', 6,  'white_concrete note6'),
    ('white_concrete', 12, 'white_concrete note12 (应=C3 原音)'),
    ('white_concrete', 18, 'white_concrete note18'),
    ('white_concrete', 24, 'white_concrete note24 (应=C4)'),
    ('gold_block',     12, 'gold_block note12 (低采样 pno_c1)'),
    ('iron_block',     12, 'iron_block note12 (高采样 pno_c5)'),
]

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(
        ('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": "qzrptest RedPiano mod v1 验证台"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))

FX0, FZ0, FX1, FZ1 = BX - 4, BZ - 4, BX + 2*len(SEQ) + 4, BZ + 4
setup = [f'forceload add {FX0} {FZ0} {FX1} {FZ1}',
         f'fill {FX0} {Y0} {FZ0} {FX1} {Y0+4} {FZ1} air',
         f'fill {FX0} {Y0-1} {FZ0} {FX1} {Y0-1} {FZ1} smooth_stone']
for i, (blk, note, _lab) in enumerate(SEQ):
    x, z = BX + 2*i, BZ
    setup.append(f'setblock {x} {Y0} {z} minecraft:{blk}')                 # 垫底=映射方块
    setup.append(f'setblock {x} {Y0+1} {z} minecraft:note_block[note={note}]')  # 真音符盒, 上方留空气
setup += [f'tp @a {BX + len(SEQ)} {Y0+2} {BZ - 5} 0 30',
          f'tellraw @a ["",{{"text":"[{NS}] RedPiano 验证台已建。","color":"aqua"}},'
          f'{{"text":" 确认已重启MC装mod + qzpno资源包开。/function {NS}:playall"}}]']
w(f'data/{NS}/function/setup.mcfunction', setup)
w(f'data/{NS}/function/load.mcfunction',
  f'tellraw @a {{"text":"[{NS}] loaded. (需先重启MC装mod) /function {NS}:setup -> /function {NS}:playall","color":"aqua"}}')

play = ['stopsound @a master',
        f'tellraw @a {{"text":"[{NS}] 真音符盒播放: white_concrete移调5 + 低/高2","color":"green"}}']
for i, (blk, note, lab) in enumerate(SEQ):
    x, z = BX + 2*i, BZ
    w(f'data/{NS}/function/p/{i}.mcfunction',
      [f'tellraw @a {{"text":"  {i+1}. {lab}","color":"gray"}}',
       f'setblock {x} {Y0+1} {z-1} minecraft:redstone_block',
       f'schedule function {NS}:p/{i}_off 2t'])
    w(f'data/{NS}/function/p/{i}_off.mcfunction', f'setblock {x} {Y0+1} {z-1} minecraft:air')
    play.append(f'schedule function {NS}:p/{i} {i*16 + 5}t append')
w(f'data/{NS}/function/playall.mcfunction', play)
w(f'data/{NS}/function/cleanup.mcfunction',
  [f'fill {FX0} {Y0-1} {FZ0} {FX1} {Y0+4} {FZ1} air',
   f'forceload remove {FX0} {FZ0} {FX1} {FZ1}',
   f'tellraw @a {{"text":"[{NS}] 已清理。","color":"aqua"}}'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 19 RedPiano v1 验证台 ===')
print('映射(须与 RedPianoMap.java 一致): white_concrete->pno_c3_mf, gold_block->pno_c1_mf, iron_block->pno_c5_mf')
print(f'deployed -> {dst}')
print(f'用法: 重启MC(装mod) -> /reload -> /function {NS}:setup -> /function {NS}:playall')
