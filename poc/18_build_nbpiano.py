# -*- coding: utf-8 -*-
"""18_build_nbpiano.py — 钢琴音符盒: 资源包 + 验证台(音质 + 几何)。

定案路线: 资源包覆盖原版音符盒乐器的 .ogg 成钢琴采样(不用头颅), 垫底方块选乐器,
note 档 0..24 移调。16 乐器槽 -> 排成「音域段 × 力度层」。
数据实测: 晴天/龙卷风 力度只用 mf+f(p 可忽略) -> 2 层; 音域 26-88 -> 6 段; 共 12 槽(<=16)。

本脚本产出:
  资源包 qzpnb (folder): 12 乐器 reskin = 6 段 × 2 力度(mf/f), 自带 12 个 .ogg。
  数据包 qzpnb:
    setup     -> 建「音符盒键盘」(每个出现过的(音高,力度)一个音符盒, 垫对应乐器方块)
                 + 几何测试台(4 个音符盒顶上盖红石线)
    playall   -> 调度器(诊断用!非最终产品)用真音符盒弹整首龙卷风 -> judge 音质
    geomtest  -> 脉冲那条红石线 -> 判: 顶上有红石线的音符盒能否发声(决定真机器几何)
    cleanup

注意: playall 是 20Hz 调度器仅作音质验证; 最终产品是 tick80 红石机器(下一步)。
Run(base python): python 18_build_nbpiano.py [notes_ljf.json]
"""
import os, sys, json, shutil
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, 'samples_piano')
SONG = sys.argv[1] if len(sys.argv) > 1 else 'notes_ljf.json'
NS = 'qzpnb'
Y0 = -60                          # 垫底乐器方块层; 音符盒 Y0+1; 顶部 Y0+2
BX, BZ = 200, 360                 # 键盘区
GX, GZ = 180, 400                 # 几何测试区
INST_PROFILE = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8"
WORLD_DP = INST_PROFILE + r"/saves/新的世界/datapacks"
RP_DIR   = INST_PROFILE + r"/resourcepacks"

VOL = {'mf': 0.6, 'f': 1.0}
def lay(v): return 'f' if v >= 0.72 else 'mf'
# 12 个 100% 确定映射的有音高乐器 (event, 垫底方块); 顺序 = band0(mf,f), band1(mf,f)...
INST_POOL = [('harp', 'dirt'), ('bass', 'oak_planks'),
             ('bell', 'gold_block'), ('chime', 'packed_ice'),
             ('flute', 'clay'), ('guitar', 'white_wool'),
             ('xylophone', 'bone_block'), ('iron_xylophone', 'iron_block'),
             ('bit', 'emerald_block'), ('banjo', 'hay_block'),
             ('pling', 'glowstone'), ('didgeridoo', 'pumpkin')]

notes = [n for n in json.load(open(os.path.join(HERE, SONG), encoding='utf-8'))['notes'] if n['vel'] >= 0.04]
man = json.load(open(os.path.join(HERE, 'samples_manifest_piano.json'), encoding='utf-8'))
by_midi = defaultdict(dict)
for s in man['samples']:
    by_midi[int(s['base_midi'])][s['vlayer']] = s['id']
grid = sorted(by_midi)
ms = sorted(n['midi'] for n in notes)
lo, hi = ms[0], ms[-1]
present = [L for L in ('mf', 'f') if any(lay(n['vel']) == L for n in notes)]
NB = min(6, len(INST_POOL) // len(present))     # 段数

def choose_centers(lo, hi, n, grid):
    """均匀分布段中心(snap 到采样格): 6 段下最小化最大变速; 想更低只能加段数。"""
    cs = []
    for i in range(n):
        c = min(grid, key=lambda g: abs(g - (lo + (hi - lo) * (i + 0.5) / n)))
        if c not in cs: cs.append(c)
    return sorted(cs)
centers = choose_centers(lo, hi, NB, grid)
NB = len(centers)
maxstretch = max(min(abs(c - n['midi']) for c in centers) for n in notes)
assert maxstretch <= 12, f"覆盖不足: 最大变速 {maxstretch} > 12 半音 (note档放不下)"
band_gain = [round(0.5 + 0.5 * bi / max(1, NB - 1), 3) for bi in range(NB)]   # 低段衰减: 治低音过重

def inst_for(bi, layer):
    return INST_POOL[len(present) * bi + present.index(layer)]
def band_of(m):
    return min(range(NB), key=lambda bi: abs(centers[bi] - m))
def note_val_of(m, bi):
    return max(0, min(24, 12 + (m - centers[bi])))

# ---------- 资源包 ----------
RP = os.path.join(HERE, 'build', f'{NS}_rp')
if os.path.isdir(RP): shutil.rmtree(RP)
os.makedirs(os.path.join(RP, 'assets', 'minecraft'))
os.makedirs(os.path.join(RP, 'assets', NS, 'sounds'))
json.dump({"pack": {"pack_format": 64, "description": f"qzpnb 钢琴音符盒 {NB}段x{len(present)}力度"}},
          open(os.path.join(RP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
sounds = {}
copied = set()
inst_table = []          # (bi, layer, inst, blk, center, sample, vol)
for bi in range(NB):
    for layer in present:
        inst, blk = inst_for(bi, layer)
        smp = by_midi[centers[bi]][layer]
        vol = round(min(1.0, band_gain[bi] * VOL[layer]), 3)
        sounds[f'block.note_block.{inst}'] = {
            "replace": True, "sounds": [{"name": f"{NS}:{smp}", "volume": vol, "stream": False}]}
        inst_table.append((bi, layer, inst, blk, centers[bi], smp, vol))
        if smp not in copied:
            shutil.copy(os.path.join(SAMPLES, f'{smp}.ogg'), os.path.join(RP, 'assets', NS, 'sounds', f'{smp}.ogg'))
            copied.add(smp)
json.dump(sounds, open(os.path.join(RP, 'assets', 'minecraft', 'sounds.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
dst_rp = os.path.join(RP_DIR, NS)
if os.path.isdir(dst_rp): shutil.rmtree(dst_rp)
shutil.copytree(RP, dst_rp)

# ---------- 数据包 ----------
DP = os.path.join(HERE, 'build', f'{NS}_dp')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(
        ('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": "qzpnb 钢琴音符盒 验证台(配同名资源包)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))

# 键盘: 每个出现过的 (midi, layer) 一个音符盒
keys = sorted(set((n['midi'], lay(n['vel'])) for n in notes))
kpos = {}
for idx, (m, layer) in enumerate(keys):
    col, row = idx % 20, idx // 20
    kpos[(m, layer)] = (BX + 2*col, BZ + 3*row, idx)   # 行距3: 防脉冲红石块串扰后一行同列
KX1 = BX + 2*19 + 2; KZ1 = BZ + 3*(len(keys)//20) + 2
FX0, FZ0, FX1, FZ1 = GX - 4, BZ - 4, KX1 + 4, GZ + 6   # 把键盘区+几何区一起 forceload

setup = [f'forceload add {FX0} {FZ0} {FX1} {FZ1}',
         f'fill {FX0} {Y0} {FZ0} {FX1} {Y0+4} {FZ1} air',
         f'fill {FX0} {Y0-1} {FZ0} {FX1} {Y0-1} {FZ1} smooth_stone']
for (m, layer), (x, z, idx) in kpos.items():
    bi = band_of(m); blk = inst_for(bi, layer)[1]; nv = note_val_of(m, bi)
    setup.append(f'setblock {x} {Y0} {z} minecraft:{blk}')
    setup.append(f'setblock {x} {Y0+1} {z} minecraft:note_block[note={nv}]')
    # Y0+2 留空气 (发声需要)
# 几何测试台: 4 个音符盒(垫 dirt=harp), 顶上盖红石线一条, note 递增便于分辨
for i in range(4):
    x, z = GX + i, GZ
    setup.append(f'setblock {x} {Y0} {z} minecraft:dirt')
    setup.append(f'setblock {x} {Y0+1} {z} minecraft:note_block[note={6 + i*4}]')
    setup.append(f'setblock {x} {Y0+2} {z} minecraft:redstone_wire')          # ← 顶上盖红石线
setup.append(f'setblock {GX-1} {Y0+1} {GZ} minecraft:smooth_stone')           # 红石块脉冲点的支撑
setup += [f'tp @a {BX + 18} {Y0+2} {BZ - 5} 0 35',
          f'tellraw @a ["",{{"text":"[{NS}] 验证台已建。","color":"aqua"}},'
          f'{{"text":" 启用资源包 qzpnb(置顶) + /tick rate 20, 再 /function {NS}:playall (听整首龙卷风音符盒钢琴)"}}]',
          f'tellraw @a {{"text":" 几何测试: /function {NS}:geomtest -> 看 GX={GX} 那4个顶上有红石线的音符盒能否响","color":"yellow"}}']
w(f'data/{NS}/function/setup.mcfunction', setup)
w(f'data/{NS}/function/load.mcfunction',
  f'tellraw @a {{"text":"[{NS}] loaded. 启用资源包 qzpnb -> /function {NS}:setup -> /function {NS}:playall","color":"aqua"}}')

# 键盘脉冲函数
for (m, layer), (x, z, idx) in kpos.items():
    w(f'data/{NS}/function/kb/{idx}.mcfunction',
      [f'setblock {x} {Y0+1} {z-1} minecraft:redstone_block', f'schedule function {NS}:kb/{idx}_off 2t'])
    w(f'data/{NS}/function/kb/{idx}_off.mcfunction', f'setblock {x} {Y0+1} {z-1} minecraft:air')

play = ['stopsound @a master',
        f'tellraw @a {{"text":"[{NS}] 弹奏龙卷风(音符盒钢琴, 20Hz调度器/诊断用). 听音质!","color":"green"}}']
for n in sorted(notes, key=lambda n: n['t']):
    idx = kpos[(n['midi'], lay(n['vel']))][2]
    play.append(f'schedule function {NS}:kb/{idx} {round(n["t"]*20)}t append')   # append! 否则同键被覆盖只响1次
last = round(max(n['t'] for n in notes) * 20) + 40
play.append(f'schedule function {NS}:done {last}t')
w(f'data/{NS}/function/playall.mcfunction', play)

# 快速 sanity: 低/中/高 3 个音慢放, 确认触发+音色
t3 = [keys[0], keys[len(keys)//2], keys[-1]]
test3 = ['stopsound @a master', f'tellraw @a {{"text":"[{NS}] test3: 低/中/高 3音慢放","color":"green"}}']
for j, k in enumerate(t3):
    test3.append(f'schedule function {NS}:kb/{kpos[k][2]} {10 + j*25}t')
w(f'data/{NS}/function/test3.mcfunction', test3)
w(f'data/{NS}/function/done.mcfunction', f'tellraw @a {{"text":"[{NS}] (end) 重听: /function {NS}:playall","color":"aqua"}}')

# 几何测试: 脉冲红石线
w(f'data/{NS}/function/geomtest.mcfunction',
  [f'tellraw @a {{"text":"[{NS}] geom: 脉冲顶上红石线 -> 4个音符盒该响(若顶上红石线不挡发声)","color":"green"}}',
   f'setblock {GX-1} {Y0+2} {GZ} minecraft:redstone_block', f'schedule function {NS}:geomoff 6t'])
w(f'data/{NS}/function/geomoff.mcfunction', f'setblock {GX-1} {Y0+2} {GZ} minecraft:air')

w(f'data/{NS}/function/cleanup.mcfunction',
  [f'fill {FX0} {Y0-1} {FZ0} {FX1} {Y0+4} {FZ1} air',
   f'forceload remove {FX0} {FZ0} {FX1} {FZ1}',
   f'tellraw @a {{"text":"[{NS}] 已清理。","color":"aqua"}}'])

dst_dp = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst_dp): shutil.rmtree(dst_dp)
shutil.copytree(DP, dst_dp)

from collections import Counter as _C
_st = _C(min(abs(c - n['midi']) for c in centers) for n in notes)
print('=== 18 钢琴音符盒 资源包+验证台 ===')
print(f'曲子={SONG}  音域 MIDI {lo}-{hi}  力度层={present}  段数={NB}  槽位={NB*len(present)}/16')
print(f'变速: 最大={maxstretch}半音  平均={sum(k*v for k,v in _st.items())/len(notes):.2f}  >=5半音的音={sum(v for k,v in _st.items() if k>=5)}({100*sum(v for k,v in _st.items() if k>=5)//len(notes)}%)')
print('段中心 & 乐器映射 (gain=低段衰减治低音):')
for bi in range(NB):
    row = '  '.join(f'{L}:{inst_for(bi,L)[0]}({inst_for(bi,L)[1]})' for L in present)
    print(f'  段{bi} 中心MIDI={centers[bi]:3d} gain={band_gain[bi]}: {row}')
print(f'键盘音符盒数={len(keys)}  调度音符={len(notes)}')
print(f'资源包 -> {dst_rp}')
print(f'数据包 -> {dst_dp}')
print(f'用法: 选项->资源包 启用 qzpnb(置顶) -> /tick rate 20 -> /reload -> /function {NS}:setup -> /function {NS}:playall (+ /function {NS}:geomtest)')
