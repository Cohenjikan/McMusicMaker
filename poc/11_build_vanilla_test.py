# -*- coding: utf-8 -*-
"""11_build_vanilla_test.py — 对照实验:用原版音符盒声音替掉自定义采样。

和 10(qzsch 调度器)同样的音符/量化/7-lane/绝对刻调度,唯一区别:
  playsound 的声音从 qzpno:<自定义采样>  ->  原版 minecraft:block.note_block.harp(可 pitch)。
不需要资源包。目的:隔离"是不是自定义采样的问题"。

  原版声音不丢拍 -> 问题在自定义钢琴采样(编码/加载);
  原版声音还丢   -> 跟采样无关, 是 playsound/客户端声音引擎机制本身。

注意:音符盒只覆盖 ±1 八度(pitch 0.5-2.0, 中心 F#4=MIDI66),超出会被钳到边界(音高不准但仍出声)
      —— 本测试只看**节奏完整性**(有没有缺拍),音高不重要。

Run: python 11_build_vanilla_test.py   (读 ./notes.json, 部署到世界 qzvan_play)
"""
import os, json, shutil
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'qzvan'
SOUND = 'minecraft:block.note_block.harp'
TPS = 20
U = 0.221
MAXLANES = 7
VEL_FLOOR = 0.04
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"

notes = json.load(open(os.path.join(HERE, 'notes.json'), encoding='utf-8'))['notes']
# 同 06/10 的量化 + 7-lane 分配(每格按音高取前 7)
bycell = defaultdict(list)
for n in notes:
    if n['vel'] >= VEL_FLOOR:
        bycell[round(n['t'] / U)].append(n)
cellnotes = {}
for c, grp in bycell.items():
    sel = sorted(grp, key=lambda x: -x['midi'])[:MAXLANES]
    cellnotes[c] = sel
occ = sorted(cellnotes)

def vpitch(m):  # 原版音符盒绝对 pitch, 中心 F#4=66
    return round(max(0.5, min(2.0, 2 ** ((m - 66) / 12.0))), 5)
def off(c):
    return round(c * U * TPS)

DP = os.path.join(HERE, 'build', f'{NS}_play')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(
        ('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')

json.dump({"pack": {"pack_format": 81, "description": "qzvan vanilla note-block A/B (isolate custom samples)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)

for c in occ:
    lines = [f'execute as @a at @s run playsound {SOUND} master @s ~ ~ ~ {round(0.6+0.4*min(1.0,n["vel"]),3)} {vpitch(n["midi"])} 1'
             for n in cellnotes[c]]
    w(f'data/{NS}/function/c/{c}.mcfunction', lines)

play = ['stopsound @a master']
play += [f'schedule function {NS}:c/{c} {off(c)}t' for c in occ]
play += [f'schedule function {NS}:done {off(occ[-1]) + 40}t',
         'tellraw @a "[qzvan] vanilla note-block play (no custom samples). listen for drops."']
w(f'data/{NS}/function/play.mcfunction', play)
w(f'data/{NS}/function/done.mcfunction', 'tellraw @a "[qzvan] (end) replay: /function qzvan:play"')
w(f'data/{NS}/function/stop.mcfunction',
  ['stopsound @a master'] + [f'schedule clear {NS}:c/{c}' for c in occ] + [f'schedule clear {NS}:done', 'tellraw @a "[qzvan] stopped."'])

dst = os.path.join(WORLD_DP, f'{NS}_play')
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print('=== 11 vanilla test build ===')
print(f'occupied cells={len(occ)}  notes={sum(len(v) for v in cellnotes.values())}  sound={SOUND}')
print(f'deployed -> {dst}')
print('用法: /reload -> /tick rate 20 -> /function qzvan:play   (听节奏有没有缺拍, 音高不准是正常的)')
