# -*- coding: utf-8 -*-
"""17_build_nbinst.py — 音符盒「内置乐器替换」校准台 (资源包 + 数据包)。

放弃头颅路(自定义头颅音效不随 note 移调 + 不美观), 改走用户思路:
  资源包覆盖原版 16 种音符盒乐器的 .ogg 成钢琴采样,
  音符盒「正下方方块」选乐器, note 档 0..24 移调(原版乐器会移调)。无头颅。

本台校准三件事(决定建造器怎么设计):
  fact1 移调:   harp(dirt) 同一采样 note=0/6/12/18/24 -> 应听到上行琶音
  fact2 八度偏移: 同一采样 pno_c3_mf 放进 harp/bass/bell, 都 note=12 ->
                  音高相同? (偏移来自.ogg内容, 我控制) 还是不同? (乐器自带, 代码固定)
  fact3 响度:   harp(vol1.0) vs flute(vol0.3) 同采样同note -> 响度拉开?
  附: guitar 塞高采样 pno_c5_mf, 确认高八度采样也能加载发声。

产物:
  资源包 qznbinst (folder): assets/minecraft/sounds.json 覆盖 block.note_block.{harp,bass,bell,flute,guitar}
                            + 自带 pno_c3_mf/pno_c5_mf.ogg (自包含, 不依赖 qzpno 启用)
  数据包 qznbinst:          测试台 setup/playall/cleanup

Run: python 17_build_nbinst.py    (base python)
"""
import os, json, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, 'samples_piano')
NS = 'qznbinst'
Y = -60
BX, BZ = 200, 330                 # 独立区, 远离 qznbtest(BZ=301) 和乐曲机器
INST_PROFILE = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8"
WORLD_DP = INST_PROFILE + r"/saves/新的世界/datapacks"
RP_DIR   = INST_PROFILE + r"/resourcepacks"

# 乐器 -> (正下方方块, 采样事件, volume)  —— 校准用
INSTRUMENTS = {
    'harp':   ('dirt',        'pno_c3_mf', 1.0),
    'bass':   ('oak_planks',  'pno_c3_mf', 1.0),   # 同采样, 测八度偏移
    'bell':   ('gold_block',  'pno_c3_mf', 1.0),   # 同采样, 测八度偏移
    'flute':  ('clay',        'pno_c3_mf', 0.3),   # 同采样低音量, 测响度
    'guitar': ('white_wool',  'pno_c5_mf', 1.0),   # 高采样, 测高八度加载
}
SAMPLES_USED = sorted(set(s for (_, s, _) in INSTRUMENTS.values()))

# ---------- 资源包 ----------
RP = os.path.join(HERE, 'build', f'{NS}_rp')
if os.path.isdir(RP): shutil.rmtree(RP)
os.makedirs(os.path.join(RP, 'assets', 'minecraft'))
os.makedirs(os.path.join(RP, 'assets', NS, 'sounds'))
json.dump({"pack": {"pack_format": 64, "description": "qznbinst 音符盒乐器->钢琴 校准台"}},
          open(os.path.join(RP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
for s in SAMPLES_USED:
    shutil.copy(os.path.join(SAMPLES, f'{s}.ogg'), os.path.join(RP, 'assets', NS, 'sounds', f'{s}.ogg'))
sounds = {}
for inst, (_blk, smp, vol) in INSTRUMENTS.items():
    sounds[f'block.note_block.{inst}'] = {
        "replace": True,
        "sounds": [{"name": f"{NS}:{smp}", "volume": vol, "stream": False}]
    }
json.dump(sounds, open(os.path.join(RP, 'assets', 'minecraft', 'sounds.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
dst_rp = os.path.join(RP_DIR, NS)
if os.path.isdir(dst_rp): shutil.rmtree(dst_rp)
shutil.copytree(RP, dst_rp)

# ---------- 数据包 (测试台) ----------
# 播放序列: 先 harp 移调 5 个, 再 八度/响度/高采样 5 个
SEQ = [
    ('harp', 0,  'harp n0'),  ('harp', 6,  'harp n6'),  ('harp', 12, 'harp n12'),
    ('harp', 18, 'harp n18'), ('harp', 24, 'harp n24'),
    ('harp', 12, '== harp c3 @12 (基准音高/满音量)'),
    ('bass', 12, 'bass c3 @12 (和上一个比音高?)'),
    ('bell', 12, 'bell c3 @12 (和基准比音高?)'),
    ('flute',12, 'flute c3 @12 vol0.3 (和基准比响度?)'),
    ('guitar',12,'guitar c5 @12 (应比c3高~2八度)'),
]

DP = os.path.join(HERE, 'build', f'{NS}_dp')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(
        ('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": "qznbinst 音符盒乐器替换 校准台 (配同名资源包)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))

FX0, FZ0, FX1, FZ1 = BX - 8, BZ - 8, BX + 2*len(SEQ) + 6, BZ + 4
setup = [f'forceload add {FX0} {FZ0} {FX1} {FZ1}',
         f'fill {FX0} {Y} {FZ0} {FX1} {Y+4} {FZ1} air',
         f'fill {FX0} {Y} {FZ0} {FX1} {Y} {FZ1} smooth_stone']
for i, (inst, note, _label) in enumerate(SEQ):
    blk = INSTRUMENTS[inst][0]
    x, z = BX + 2*i, BZ
    setup.append(f'setblock {x} {Y} {z} minecraft:{blk}')                 # 正下方 = 选乐器
    setup.append(f'setblock {x} {Y+1} {z} minecraft:note_block[note={note}]')
    # 上方留空气(音符盒发声需要), 不放头颅
setup += [f'tp @a {BX + len(SEQ)} {Y+2} {BZ - 6} 0 25',
          f'tellraw @a ["",{{"text":"[{NS}] 校准台已建。","color":"aqua"}},'
          f'{{"text":"先在 选项->资源包 启用 qznbinst(置顶), 再 /function {NS}:playall"}}]']
w(f'data/{NS}/function/setup.mcfunction', setup)
w(f'data/{NS}/function/load.mcfunction',
  f'tellraw @a {{"text":"[{NS}] loaded. 启用资源包 qznbinst -> /function {NS}:setup -> /function {NS}:playall","color":"aqua"}}')

play = [f'tellraw @a {{"text":"[{NS}] play: harp移调5 -> 八度/响度/高采样5 (每0.8s一个)","color":"green"}}']
for i, (inst, note, label) in enumerate(SEQ):
    x, z = BX + 2*i, BZ
    w(f'data/{NS}/function/p/{i}.mcfunction',
      [f'tellraw @a {{"text":"  {i+1}. {label}","color":"gray"}}',
       f'setblock {x} {Y+1} {z-1} minecraft:redstone_block',
       f'schedule function {NS}:p/{i}_off 2t'])
    w(f'data/{NS}/function/p/{i}_off.mcfunction', f'setblock {x} {Y+1} {z-1} minecraft:air')
    play.append(f'schedule function {NS}:p/{i} {i*16 + 5}t')
w(f'data/{NS}/function/playall.mcfunction', play)
w(f'data/{NS}/function/cleanup.mcfunction',
  [f'fill {FX0} {Y} {FZ0} {FX1} {Y+4} {FZ1} air',
   f'forceload remove {FX0} {FZ0} {FX1} {FZ1}',
   f'tellraw @a {{"text":"[{NS}] 已清理。","color":"aqua"}}'])

dst_dp = os.path.join(WORLD_DP, NS)
if os.path.isdir(dst_dp): shutil.rmtree(dst_dp)
shutil.copytree(DP, dst_dp)

print('=== 17 音符盒内置乐器替换 校准台 ===')
print(f'采样: {SAMPLES_USED}')
print('乐器映射:')
for inst, (blk, smp, vol) in INSTRUMENTS.items():
    print(f'  block.note_block.{inst:7s} <- {blk:12s}  采样={smp}  vol={vol}')
print(f'资源包 -> {dst_rp}')
print(f'数据包 -> {dst_dp}')
print(f'用法: 选项->资源包 启用 qznbinst(置顶) -> /reload -> /function {NS}:setup -> /function {NS}:playall')
