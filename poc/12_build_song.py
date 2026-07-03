# -*- coding: utf-8 -*-
"""12_build_song.py — 通用"换 MIDI 重构"建造器(调度器版, 复用钢琴采样)。

对照实验:换一首完全不同的 MIDI(龙卷风), 同样的调度器+采样机制, 看是否还卡拍。
  还卡 -> 和具体 MIDI 无关, 是系统性的(playsound/客户端机制);
  干净 -> 晴天 MIDI 的数据本身有问题。

调度器不需要红石那种 0.221 网格 -> 直接按音符**真实时间** round(t*20) 排到游戏刻,
忠实还原原速(无量化失真)。映射到最近钢琴 band 采样, 排除打击轨(channel 9)。

Run (用 venv-demucs python, 有 mido):
  <venv-demucs python> 12_build_song.py "<midi路径>" <命名空间>
"""
import sys, os, json, shutil
from collections import defaultdict
import mido

MIDI = sys.argv[1] if len(sys.argv) > 1 else r"~/Downloads/龙卷风_爱给网_aigei_com.mid"
NS = sys.argv[2] if len(sys.argv) > 2 else 'qzljf'
TPS = 20
SOUND_NS = 'qzpno'           # 复用现有钢琴资源包
MAXPOLY = 8                  # 单刻最多发声(防极端和弦)
WORLD_DP = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/saves/新的世界/datapacks"
HERE = os.path.dirname(os.path.abspath(__file__))

# --- 解析 MIDI(merge_tracks 正确处理 type-1 多轨+tempo; clip 容错坏字节; 排除打击) ---
mid = mido.MidiFile(MIDI, clip=True)
notes = []
tempo = 500000; t = 0.0; cur = defaultdict(list)
for msg in mido.merge_tracks(mid.tracks):
    t += mido.tick2second(msg.time, mid.ticks_per_beat, tempo)
    if msg.type == 'set_tempo':
        tempo = msg.tempo
    elif msg.type == 'note_on' and msg.velocity > 0 and getattr(msg, 'channel', 0) != 9:
        cur[(msg.channel, msg.note)].append((t, msg.velocity))
    elif (msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0)) and getattr(msg, 'channel', 0) != 9:
        k = (msg.channel, msg.note)
        if cur[k]:
            t0, v = cur[k].pop(0); notes.append((t0, msg.note, v / 127.0))
notes.sort()

# --- 钢琴采样映射(同 06) ---
man = json.load(open(os.path.join(HERE, 'samples_manifest_piano.json'), encoding='utf-8'))
samples = man['samples']
bands = sorted(set(s['base_midi'] for s in samples))
bl = {(s['base_midi'], s['vlayer']): s['id'] for s in samples}
def layer_of(v): return 'p' if v < 0.40 else ('mf' if v < 0.72 else 'f')
def map_note(m, v):
    base = min(bands, key=lambda b: abs(b - m))
    return bl[(base, layer_of(v))], round(max(0.5, min(2.0, 2 ** ((m - base) / 12.0))), 5)

# --- 按真实时间分刻 ---
bytick = defaultdict(list)
for (t0, m, v) in notes:
    if v < 0.04: continue
    eid, pitch = map_note(m, v)
    vol = round(0.6 + 0.4 * min(1.0, v), 3)
    bytick[round(t0 * TPS)].append((m, eid, pitch, vol))
ticks = sorted(bytick)

# --- 生成数据包 ---
DP = os.path.join(HERE, 'build', f'{NS}_play')
if os.path.isdir(DP): shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, body):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(('\n'.join(body) if isinstance(body, list) else body).rstrip('\n') + '\n')
json.dump({"pack": {"pack_format": 81, "description": f"{NS} reconstruction (scheduler, piano samples)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
for tk in ticks:
    sel = sorted(bytick[tk], key=lambda x: -x[0])[:MAXPOLY]
    w(f'data/{NS}/function/t/{tk}.mcfunction',
      [f'execute as @a at @s run playsound {SOUND_NS}:{eid} master @s ~ ~ ~ {vol} {pitch} 1' for (_, eid, pitch, vol) in sel])
play = ['stopsound @a master'] + [f'schedule function {NS}:t/{tk} {tk}t' for tk in ticks]
play += [f'schedule function {NS}:done {ticks[-1] + 40}t', f'tellraw @a "[{NS}] reconstruction play. listen for drops."']
w(f'data/{NS}/function/play.mcfunction', play)
w(f'data/{NS}/function/done.mcfunction', f'tellraw @a "[{NS}] (end) replay: /function {NS}:play"')
w(f'data/{NS}/function/stop.mcfunction', ['stopsound @a master'] + [f'schedule clear {NS}:t/{tk}' for tk in ticks] + [f'schedule clear {NS}:done'])

dst = os.path.join(WORLD_DP, f'{NS}_play')
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(DP, dst)
print(f'=== 12 build {NS} from {os.path.basename(MIDI)} ===')
print(f'notes={len(notes)}  发声刻数={len(ticks)}  末刻={ticks[-1]}t={ticks[-1]/TPS:.1f}s  采样复用={SOUND_NS}')
print(f'deployed -> {dst}')
print(f'用法: /reload -> /tick rate 20 -> /function {NS}:play')
