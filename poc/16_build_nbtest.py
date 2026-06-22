# -*- coding: utf-8 -*-
"""16_build_nbtest.py — 音符盒自定义音色「机制验证台」(最小)。

核心问题(01 报告 §7 未决#4, 从未在 1.21.8 实测):
  音符盒顶部放带 note_block_sound 的玩家头颅 ->
    (a) 音符盒会不会播放该自定义音效?
    (b) 该自定义音效会不会随音符盒 note 档(0..24)移调?
  若 (b) 成立 -> 一个采样 band 配 note 0..24 即可覆盖, 「音符盒+自定义头颅」路成立,
                可把 Method B 的命令方块换成真音符盒(满足"红石音乐用音符盒发声")。
  若 (b) 不成立(自定义音效固定音高) -> 每半音都要一个采样, 或这条路要改。

附带验掉「给头颅写组件的最简命令」也是未决项 -> 同测两种 NBT 写法:
  测A: {note_block_sound:"qzpno:pno_c3_mf"}                         (方块实体 NBT 字段)
  测B: {components:{"minecraft:note_block_sound":"qzpno:pno_c3_mf"}} (数据组件写法)

对照组: 原版竖琴(无头颅) note=0/24, 确认机器+原版移调正常(排除"啥都不响=机器问题")。

Run: python 16_build_nbtest.py    (base python, 不需任何依赖)
用法见脚本末尾打印。
"""
import os, json, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'qznbtest'
SND = 'qzpno:pno_c3_mf'            # 中音区采样 C3=48; note0->C2(36) note24->C4(60), 两端可听
Y = -60                           # 地面方块层; 音符盒在 Y+1, 头颅在 Y+2
BX, BZ = 200, 301                 # 测试台基坐标(远离 X>=30000 的乐曲机器, 又靠近出生点)
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"

# (x偏移, note, kind)  kind: 'van'=原版对照, 'A'=NBT字段写法, 'B'=组件写法
BLOCKS = [
    (0,  0,  'van'), (2,  24, 'van'),
    (6,  0,  'A'),   (8,  12, 'A'),   (10, 24, 'A'),
    (14, 0,  'B'),   (16, 12, 'B'),   (18, 24, 'B'),
]
LABEL = {'van': '对照(原版竖琴)', 'A': '测A(NBT字段)', 'B': '测B(组件)'}

def head_nbt(kind):
    if kind == 'A': return '{note_block_sound:"%s"}' % SND
    if kind == 'B': return '{components:{"minecraft:note_block_sound":"%s"}}' % SND
    return None

DP = os.path.join(HERE, 'build', NS)
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(
        ('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": "qznbtest 音符盒+自定义头颅 机制验证台"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))

# ---- setup: 建测试台 ----
FX0, FZ0, FX1, FZ1 = BX - 8, BZ - 8, BX + 26, BZ + 4
setup = [f'forceload add {FX0} {FZ0} {FX1} {FZ1}',
         f'fill {FX0} {Y} {FZ0} {FX1} {Y+4} {FZ1} air',
         f'fill {FX0} {Y} {FZ0} {FX1} {Y} {FZ1} smooth_stone']           # 平台
for dx, note, kind in BLOCKS:
    x, z = BX + dx, BZ
    setup.append(f'setblock {x} {Y} {z} minecraft:dirt')                  # 下方=竖琴乐器(对照用)
    setup.append(f'setblock {x} {Y+1} {z} minecraft:note_block[note={note}]')
    nbt = head_nbt(kind)
    if nbt:
        setup.append(f'setblock {x} {Y+2} {z} minecraft:player_head[rotation=0]{nbt}')
setup += [f'tp @a {BX + 9} {Y+2} {BZ - 6} 0 25',
          f'tellraw @a ["",{{"text":"[{NS}] 测试台已建。","color":"aqua"}},'
          f'{{"text":"跑 /function {NS}:playall 听; 或手动 /function {NS}:cleanup 清理。"}}]',
          f'tellraw @a {{"text":"判读: 对照应低->高; 测A/测B 若响=该写法对, 若音高随note变=移调成立(路通)。","color":"yellow"}}']
w('data/qznbtest/function/setup.mcfunction', setup)
w('data/qznbtest/function/load.mcfunction',
  f'tellraw @a {{"text":"[{NS}] loaded. /function {NS}:setup 建台 -> /function {NS}:playall 验证","color":"aqua"}}')

# ---- playall: 红石块脉冲依次触发, 边播边报 ----
play = [f'tellraw @a {{"text":"[{NS}] play: 对照2 -> 测A3 -> 测B3 (每0.7s一个)","color":"green"}}']
for i, (dx, note, kind) in enumerate(BLOCKS):
    x, z = BX + dx, BZ
    # 脉冲函数: 在音符盒北侧(z-1)放红石块强充能 -> 音符盒上升沿发声; 2t 后撤掉
    w(f'data/qznbtest/function/p/{i}.mcfunction',
      [f'tellraw @a {{"text":"  -> {LABEL[kind]} note={note}","color":"gray"}}',
       f'setblock {x} {Y+1} {z-1} minecraft:redstone_block',
       f'schedule function {NS}:p/{i}_off 2t'])
    w(f'data/qznbtest/function/p/{i}_off.mcfunction',
      f'setblock {x} {Y+1} {z-1} minecraft:air')
    play.append(f'schedule function {NS}:p/{i} {i*14 + 5}t')
w('data/qznbtest/function/playall.mcfunction', play)

# ---- cleanup ----
w('data/qznbtest/function/cleanup.mcfunction',
  [f'fill {FX0} {Y} {FZ0} {FX1} {Y+4} {FZ1} air',
   f'forceload remove {FX0} {FZ0} {FX1} {FZ1}',
   f'tellraw @a {{"text":"[{NS}] 已清理。","color":"aqua"}}'])

dst = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 16 音符盒自定义音色 验证台 ===')
print(f'采样事件 = {SND}   坐标基 = ({BX},{Y},{BZ})   音符盒数 = {len(BLOCKS)}')
print(f'对照(原版): note 0/24   测A(NBT字段): 0/12/24   测B(组件): 0/12/24')
print(f'deployed -> {dst}')
print(f'用法: /reload -> /function {NS}:setup -> /function {NS}:playall   (清理: /function {NS}:cleanup)')
