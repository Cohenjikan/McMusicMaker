# -*- coding: utf-8 -*-
"""gen_multi_map.py — 从模组 RedPianoMap.java 抽出【多乐器 垫底方块->采样】映射给 Python 生成器用。

模组(jar)里的 RedPianoMap.java 是音色映射的唯一真相(103 条: pno/bass/lead/pad/drum)。
本脚本解析它 -> `redpiano_map_multi.json`, 让任务5 的多乐器生成器无需手抄、永远与 jar 一致。
另写入 GM 乐器家族 -> 采样集 的自动分配表(用户选"按 GM 家族自动映射")。
Run: python gen_multi_map.py
"""
import re, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
JAVA = os.path.join(HERE, '..', 'mod', 'redpiano', 'src', 'main', 'java', 'com', 'redpiano', 'RedPianoMap.java')

PC = {'c':0,'cs':1,'d':2,'ds':3,'e':4,'f':5,'fs':6,'g':7,'gs':8,'a':9,'as':10,'b':11}
def note_to_midi(s):                      # 'c1'->24, 'ds1'->27, 'a5'->81, 'c6'->84
    m = re.match(r'([a-g]s?)(\d+)$', s)
    return (int(m.group(2)) + 1) * 12 + PC[m.group(1)]

txt = open(JAVA, encoding='utf-8').read()
# MAP.put(Blocks.WHITE_CONCRETE, new Entry("qzpno:pno_c1_p", 1.4f));
pat = re.compile(r'MAP\.put\(Blocks\.(\w+),\s*new Entry\("qzpno:([a-z0-9_]+)",\s*([\d.]+)f\)\)')
INST = {}     # instr -> {'pitched':bool, 'layers':set, 'bands':set, 'block':{key->block}, 'vol':{key->vol}, 'types':{...}}
for blk, sound, vol in pat.findall(txt):
    block = 'minecraft:' + blk.lower()
    vol = float(vol)
    toks = sound.split('_')
    instr = toks[0]
    d = INST.setdefault(instr, {'pitched': instr != 'drum', 'layers': set(), 'bands': set(),
                                'block': {}, 'vol': {}, 'sound': {}, 'types': {}})
    full = 'qzpno:' + sound                           # 完整音效事件 ID(用于 stopsound 截断延音)
    if instr == 'drum':                              # drum_kick_x / drum_hihat_closed_x
        dtype = '_'.join(toks[1:-1])                 # kick / snare / hihat_closed / tom / crash
        d['types'][dtype] = block; d['vol'][f'drum:{dtype}'] = vol; d['sound'][f'drum:{dtype}'] = full
    else:                                            # pno_c1_p / bass_e1_mf / lead_c3_mf / pad_c2_mf
        note, layer = toks[1], toks[2]
        band = note_to_midi(note)
        d['layers'].add(layer); d['bands'].add(band)
        d['block'][f'{band}_{layer}'] = block; d['vol'][f'{band}_{layer}'] = vol; d['sound'][f'{band}_{layer}'] = full

out = {'instruments': {}}
for instr, d in INST.items():
    if instr == 'drum':
        out['instruments'][instr] = {'pitched': False, 'types': d['types'], 'vol': d['vol'], 'sound': d['sound']}
    else:
        out['instruments'][instr] = {'pitched': True, 'layers': sorted(d['layers']),
                                     'bands': sorted(d['bands']), 'block': d['block'], 'vol': d['vol'], 'sound': d['sound']}

# GM 乐器家族(program//8, 0..15) -> 采样集(现有: pno/bass/lead/pad/drum); ch9=鼓
out['family_map'] = {
    0: 'pno',    # Piano
    1: 'pno',    # Chromatic Percussion (mallet) -> 钢琴音域最近
    2: 'pad',    # Organ
    3: 'lead',   # Guitar
    4: 'bass',   # Bass
    5: 'pad',    # Strings
    6: 'pad',    # Ensemble (含 Synth Voice/合唱/弦乐群)
    7: 'lead',   # Brass
    8: 'lead',   # Reed
    9: 'lead',   # Pipe
    10: 'lead',  # Synth Lead
    11: 'pad',   # Synth Pad
    12: 'pad',   # Synth Effects
    13: 'lead',  # Ethnic
    14: 'drum',  # Percussive
    15: 'drum',  # Sound Effects
}
# GM 打击乐 note -> 5 个可用鼓型(我们只有 kick/snare/hihat_closed/tom/crash)
out['gm_drum_map'] = {
    35: 'kick', 36: 'kick', 38: 'snare', 40: 'snare', 37: 'snare',
    42: 'hihat_closed', 44: 'hihat_closed', 46: 'hihat_closed', 54: 'hihat_closed',
    41: 'tom', 43: 'tom', 45: 'tom', 47: 'tom', 48: 'tom', 50: 'tom',
    49: 'crash', 57: 'crash', 51: 'crash', 59: 'crash', 52: 'crash', 55: 'crash',
}

json.dump(out, open(os.path.join(HERE, 'redpiano_map_multi.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('wrote redpiano_map_multi.json')
for instr, d in out['instruments'].items():
    if d['pitched']:
        print(f"  {instr:5} pitched  layers={d['layers']}  bands {min(d['bands'])}..{max(d['bands'])} ({len(d['bands'])})")
    else:
        print(f"  {instr:5} drum     types={list(d['types'])}")
print('  family_map:', out['family_map'])
total = sum(len(d.get('block', d.get('types', {}))) for d in out['instruments'].values())
print('  total mapped blocks:', total, '(should = 103)')
