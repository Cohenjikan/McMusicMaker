# -*- coding: utf-8 -*-
"""gen_redpiano_map.py — 生成「垫底方块 -> 乐器音效」完整映射(钢琴 + 新乐器库)。

★ 本轮扩展(Task 1 多乐器): 在原 60 钢琴映射【完全不动】的基础上, 追加 bass/lead/pad/drums。
  - 钢琴 60 条(20 段 x 3 力度)用原来的 60 个方块、原来的顺序、原来的音量 -> 已部署的钢琴机器
    (OLK 折叠 qzolkf 等)继续可用, 一个字节不变。
  - 新乐器各自的采样追加到一批【新方块】(EXTRA_BLOCKS), 互不冲突。
单一真相源, 同时产出:
  ① RedPianoMap.java (模组查表; 重编译生效) —— 钢琴 + 全部新乐器
  ② redpiano_map.json (建造器用): 钢琴 map 原样 + 新增 instruments{bass/lead/pad/drums}
新乐器音色 = 引入新乐器库(bass/lead/pad 为 numpy 合成, drums 为 VCSL CC0 真采样; 见 02d_make_instruments.py)。
Run: python gen_redpiano_map.py
"""
import os, json, sys
from itertools import product
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
MOD_JAVA = os.path.join(HERE, '..', 'mod', 'redpiano', 'src', 'main', 'java', 'com', 'redpiano', 'RedPianoMap.java')
MAP_JSON = os.path.join(HERE, 'redpiano_map.json')

# ===== 钢琴(原样, 不要改) =====
LAYER_VOL = {'p': 1.40, 'mf': 1.70, 'f': 2.00}
man = json.load(open(os.path.join(HERE, 'samples_manifest_piano.json'), encoding='utf-8'))
by_midi = {}
for s in man['samples']:
    by_midi.setdefault(int(s['base_midi']), {})[s['vlayer']] = s['id']
bands = sorted(by_midi)
layers = ['p', 'mf', 'f']
combos = list(product(bands, layers))                 # 60, band-major
colors = ['white', 'orange', 'magenta', 'light_blue', 'yellow', 'lime', 'pink', 'gray',
          'light_gray', 'cyan', 'purple', 'blue', 'brown', 'green', 'red', 'black']
PIANO_BLOCKS = ([f'{c}_concrete' for c in colors] + [f'{c}_terracotta' for c in colors] +
                [f'{c}_wool' for c in colors] +
                ['stone', 'granite', 'diorite', 'andesite', 'deepslate', 'calcite',
                 'tuff', 'quartz_block', 'smooth_stone', 'sandstone', 'red_sandstone', 'bricks'])
assert len(PIANO_BLOCKS) == 60 and len(combos) == 60

entries = []                                           # (block, sound, vol) -> RedPianoMap.java(全部)
piano_map = {}                                         # band_layer -> {block,sound,vol}
for (band, layer), block in zip(combos, PIANO_BLOCKS):
    sid = by_midi[band][layer]
    entries.append((block, f'qzpno:{sid}', LAYER_VOL[layer]))
    piano_map[f'{band}_{layer}'] = {'block': f'minecraft:{block}', 'sound': f'qzpno:{sid}', 'vol': LAYER_VOL[layer]}

# ===== 新乐器(追加; 用一批与钢琴不冲突的全实心可导电非重力方块) =====
INST_VOL = {'bass': 2.2, 'lead': 1.9, 'pad': 1.5, 'drums': 2.6}   # 新乐器基准音量(可调)
INSTRUMENTS = ['bass', 'lead', 'pad', 'drums']                    # 固定顺序 -> 方块分配确定
EXTRA_BLOCKS = (
    [f'{c}_glazed_terracotta' for c in colors] +                 # 16
    ['oak_planks', 'spruce_planks', 'birch_planks', 'jungle_planks', 'acacia_planks', 'dark_oak_planks',
     'mangrove_planks', 'cherry_planks', 'bamboo_planks', 'crimson_planks', 'warped_planks'] +   # 11
    ['cobblestone', 'mossy_cobblestone', 'stone_bricks', 'mossy_stone_bricks', 'cracked_stone_bricks',
     'chiseled_stone_bricks', 'polished_granite', 'polished_diorite', 'polished_andesite',
     'polished_deepslate', 'deepslate_bricks', 'deepslate_tiles', 'cobbled_deepslate', 'blackstone',
     'polished_blackstone', 'polished_blackstone_bricks', 'end_stone', 'end_stone_bricks', 'purpur_block',
     'nether_bricks', 'red_nether_bricks', 'prismarine', 'prismarine_bricks', 'dark_prismarine',
     'iron_block', 'gold_block', 'diamond_block', 'emerald_block', 'lapis_block', 'coal_block',
     'copper_block', 'bone_block', 'dripstone_block']             # 33
)                                                                  # 共 60 个备用方块
assert len(set(EXTRA_BLOCKS)) == len(EXTRA_BLOCKS), '备用方块有重复'
assert not (set(EXTRA_BLOCKS) & set(PIANO_BLOCKS)), '备用方块与钢琴方块冲突'

instruments = {}
bi = 0
for inst in INSTRUMENTS:
    mf = os.path.join(HERE, f'samples_manifest_{inst}.json')
    if not os.path.isfile(mf):
        print(f'[warn] 缺 {mf}, 跳过 {inst}'); continue
    im = json.load(open(mf, encoding='utf-8'))
    vol = INST_VOL[inst]
    if inst == 'drums':                                # 鼓: 按 GM 键(base_midi) -> 方块, 不移调
        keys = {}
        for s in sorted(im['samples'], key=lambda r: r['base_midi']):
            block = EXTRA_BLOCKS[bi]; bi += 1
            entries.append((block, f"qzpno:{s['id']}", vol))
            keys[int(s['base_midi'])] = {'block': f'minecraft:{block}', 'sound': f"qzpno:{s['id']}", 'vol': vol, 'name': s['note']}
        instruments[inst] = {'kind': 'perc', 'keys': keys}
    else:                                              # 旋律乐器: band(base_midi) x 层 -> 方块
        ibands = sorted({int(s['base_midi']) for s in im['samples']})
        ilayers = sorted({s['vlayer'] for s in im['samples']})
        imap = {}
        for s in sorted(im['samples'], key=lambda r: (r['base_midi'], r['vlayer'])):
            block = EXTRA_BLOCKS[bi]; bi += 1
            entries.append((block, f"qzpno:{s['id']}", vol))
            imap[f"{int(s['base_midi'])}_{s['vlayer']}"] = {'block': f'minecraft:{block}', 'sound': f"qzpno:{s['id']}", 'vol': vol}
        instruments[inst] = {'kind': 'pitched', 'bands': ibands, 'layers': ilayers, 'map': imap}
assert bi <= len(EXTRA_BLOCKS), f'备用方块不够: 需 {bi} 有 {len(EXTRA_BLOCKS)}'

# ===== ① RedPianoMap.java(钢琴 + 全部新乐器) =====
puts = '\n'.join(f'        MAP.put(Blocks.{b.upper()}, new Entry("{snd}", {vol}f));' for (b, snd, vol) in entries)
java = '''package com.redpiano;

import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;

import java.util.HashMap;
import java.util.Map;

/** 「垫底方块 -> (音效事件, 音量)」完整映射 (gen_redpiano_map.py 生成; 勿手改)。
 *  钢琴 60 条 + 新乐器(bass/lead/pad/drums)。原版只有 16 条且写死; 这里任意大。 */
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

# ===== ② redpiano_map.json(钢琴原样 + instruments) =====
mj = {'bands': bands, 'layers': layers, 'map': piano_map, 'instruments': instruments}
json.dump(mj, open(MAP_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

print('=== gen_redpiano_map (钢琴 + 新乐器) ===')
print(f'钢琴: {len(piano_map)} 条(不变). 新乐器: {sum(1 for _ in instruments)} 种, 共追加 {bi} 个采样/方块')
for inst, d in instruments.items():
    if d['kind'] == 'perc':
        print(f"  {inst:6s}(鼓): {len(d['keys'])} 键 {[v['name'] for v in d['keys'].values()]}")
    else:
        print(f"  {inst:6s}: {len(d['map'])} 采样, 段 {d['bands']}")
print(f'RedPianoMap.java 总条数 = {len(entries)} (钢琴60 + 新{bi})')
print(f'写出: {os.path.normpath(MOD_JAVA)}')
print(f'写出: {MAP_JSON}')
