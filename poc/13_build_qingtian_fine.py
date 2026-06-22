# -*- coding: utf-8 -*-
"""13_build_qingtian_fine.py — 晴天"细网格"版(确认 + 修复)。

读现有 notes.json(晴天, midi_to_notes.py 扫的真实秒), 用调度器在 round(t*20)=0.05s
细网格触发(不是红石那个 0.221s 粗格),复用钢琴采样。

目的:同一份晴天数据, 只把粗网格换成细网格。若不再卡拍 -> 坐实根因=0.221s 粗网格
塌音(非 MIDI 损坏、非采样、非红石),且这版即为晴天的修复版。

Run: python 13_build_qingtian_fine.py    (base python 即可, 不需 mido)
"""
import os, json, shutil
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'qzqtf'                 # 晴天 fine
SOUND_NS = 'qzpno'
TPS = 20
MAXPOLY = 8
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"

notes = json.load(open(os.path.join(HERE, 'notes.json'), encoding='utf-8'))['notes']
man = json.load(open(os.path.join(HERE, 'samples_manifest_piano.json'), encoding='utf-8'))
samples = man['samples']; bands = sorted(set(s['base_midi'] for s in samples))
bl = {(s['base_midi'], s['vlayer']): s['id'] for s in samples}
def layer_of(v): return 'p' if v < 0.40 else ('mf' if v < 0.72 else 'f')
def map_note(m, v):
    base = min(bands, key=lambda b: abs(b - m))
    return bl[(base, layer_of(v))], round(max(0.5, min(2.0, 2 ** ((m - base) / 12.0))), 5)

bytick = defaultdict(list)
for n in notes:
    if n['vel'] < 0.04: continue
    eid, pitch = map_note(n['midi'], n['vel'])
    vol = round(0.6 + 0.4 * min(1.0, n['vel']), 3)
    bytick[round(n['t'] * TPS)].append((n['midi'], eid, pitch, vol))
ticks = sorted(bytick)

DP = os.path.join(HERE, 'build', f'{NS}_play')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": "qzqtf 晴天 fine-grid (0.05s) scheduler — fix for coarse-grid drops"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
for tk in ticks:
    sel = sorted(bytick[tk], key=lambda x: -x[0])[:MAXPOLY]
    w(f'data/{NS}/function/t/{tk}.mcfunction',
      [f'execute as @a at @s run playsound {SOUND_NS}:{eid} master @s ~ ~ ~ {vol} {pitch} 1' for (_, eid, pitch, vol) in sel])
play = ['stopsound @a master'] + [f'schedule function {NS}:t/{tk} {tk}t' for tk in ticks]
play += [f'schedule function {NS}:done {ticks[-1] + 40}t', f'tellraw @a "[{NS}] qingtian fine-grid (0.05s). listen for drops."']
w(f'data/{NS}/function/play.mcfunction', play)
w(f'data/{NS}/function/done.mcfunction', f'tellraw @a "[{NS}] (end) replay: /function {NS}:play"')
w(f'data/{NS}/function/stop.mcfunction', ['stopsound @a master'] + [f'schedule clear {NS}:t/{tk}' for tk in ticks] + [f'schedule clear {NS}:done'])
dst = os.path.join(WORLD_DP, f'{NS}_play')
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print(f'=== 13 qingtian fine ===  notes={sum(1 for n in notes if n["vel"]>=0.04)}  发声刻={len(ticks)}  末刻={ticks[-1]}t={ticks[-1]/TPS:.1f}s')
print(f'对比: 粗网格(0.221s)占用格 ~1005; 细网格(0.05s)发声刻 {len(ticks)} (多 {len(ticks)-1005} 个=之前被塌掉的)')
print(f'deployed -> {dst}   用法: /reload -> /function {NS}:play')
