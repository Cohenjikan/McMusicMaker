# -*- coding: utf-8 -*-
"""gen_redpiano_map.py — 生成「垫底方块 -> 钢琴音效」完整 60 映射。

20 段(采样 base_midi, 每3半音) x 3 力度(p/mf/f) = 60 -> 60 个不同垫底方块。
单一真相源: 同时产出
  ① RedPianoMap.java (模组的查表; 重编译生效)
  ② redpiano_map.json (建造器用: 给定(midi,vel)->垫底方块/note档/音效)

音量: 音符盒基准 NOTE_VOLUME=3.0, 资源包/这里的 volume 再乘。先给保守值, 可调。
Run: python gen_redpiano_map.py
"""
import os, json
from itertools import product
HERE = os.path.dirname(os.path.abspath(__file__))
MOD_JAVA = os.path.join(HERE, '..', 'mod', 'redpiano', 'src', 'main', 'java', 'com', 'redpiano', 'RedPianoMap.java')
MAP_JSON = os.path.join(HERE, 'redpiano_map.json')

LAYER_VOL = {'p': 1.40, 'mf': 1.70, 'f': 2.00}      # >1: 扩大可听半径(覆盖整机宽度); 太响整体下调

man = json.load(open(os.path.join(HERE, 'samples_manifest_piano.json'), encoding='utf-8'))
by_midi = {}
for s in man['samples']:
    by_midi.setdefault(int(s['base_midi']), {})[s['vlayer']] = s['id']
bands = sorted(by_midi)                               # 20 段
layers = ['p', 'mf', 'f']
combos = list(product(bands, layers))                 # 60, band-major

colors = ['white', 'orange', 'magenta', 'light_blue', 'yellow', 'lime', 'pink', 'gray',
          'light_gray', 'cyan', 'purple', 'blue', 'brown', 'green', 'red', 'black']
BLOCKS = ([f'{c}_concrete' for c in colors] + [f'{c}_terracotta' for c in colors] +
          [f'{c}_wool' for c in colors] +
          ['stone', 'granite', 'diorite', 'andesite', 'deepslate', 'calcite',
           'tuff', 'quartz_block', 'smooth_stone', 'sandstone', 'red_sandstone', 'bricks'])
assert len(BLOCKS) == 60, len(BLOCKS)
assert len(combos) == 60

entries = []   # (block, sound_event, vol, band, layer)
for (band, layer), block in zip(combos, BLOCKS):
    sid = by_midi[band][layer]                        # pno_c3_mf 等
    entries.append((block, f'qzpno:{sid}', LAYER_VOL[layer], band, layer))

# ① RedPianoMap.java
puts = '\n'.join(f'        MAP.put(Blocks.{b.upper()}, new Entry("{snd}", {vol}f));'
                 for (b, snd, vol, _, _) in entries)
java = '''package com.redpiano;

import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;

import java.util.HashMap;
import java.util.Map;

/** 「垫底方块 -> (音效事件, 音量)」完整映射 (gen_redpiano_map.py 生成; 勿手改)。
 *  20 段 x 3 力度 = 60 条。原版只有 16 条且写死; 这里任意大。 */
public final class RedPianoMap {
    public static final class Entry {
        public final String sound;
        public final float volume;
        public Entry(String sound, float volume) { this.sound = sound; this.volume = volume; }
    }

    private static final Map<Block, Entry> MAP = new HashMap<>();
    static {
%s
    }

    public static Entry lookup(Block b) { return MAP.get(b); }

    private RedPianoMap() {}
}
''' % puts
open(os.path.normpath(MOD_JAVA), 'w', encoding='utf-8', newline='\n').write(java)

# ② redpiano_map.json (建造器: band_layer -> block/sound/vol)
mj = {'bands': bands, 'layers': layers, 'map': {}}
for (block, snd, vol, band, layer) in entries:
    mj['map'][f'{band}_{layer}'] = {'block': f'minecraft:{block}', 'sound': snd, 'vol': vol}
json.dump(mj, open(MAP_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

print('=== gen_redpiano_map ===')
print(f'段(base_midi) x 层 = {len(bands)} x {len(layers)} = {len(entries)} 条')
print(f'  段: {bands}')
print(f'  音量: {LAYER_VOL}')
print(f'写出: {os.path.normpath(MOD_JAVA)}')
print(f'写出: {MAP_JSON}')
print('示例几条:')
for e in entries[:3] + entries[-2:]:
    print(f'  {e[0]:20s} -> {e[1]:16s} vol={e[2]} (band{e[3]} {e[4]})')
