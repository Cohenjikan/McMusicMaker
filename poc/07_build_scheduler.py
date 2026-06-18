"""时序引擎 v2 — 数据包游戏刻调度器(0.05s 精度),取代红石脊柱(0.1s 且不对齐 0.22s)。
- 节奏:每个音符按真实秒 -> 游戏刻 round(t*20),0.05s 分辨率(比延时器 0.1s 细一倍),无累积漂移。
- 延音:MIDI 时值 > 阈值的音符,每 ~0.5s 重击一次(衰减),即手册的"同音连击"。
- 混响:每次发声后 +0.15s / +0.4s 各加一个更轻的回声 tap,叠出空间感。
驱动:链式 schedule(每个有音符的刻一个函数,自调度下一个;PLAY 旗标可随时停)。无巨型机器,/function qzpno:play 即响(playsound 跟随玩家)。
Run: <venv-demucs python> 07_build_scheduler.py [max_sec]
"""
import os, sys, json, shutil
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = r'C:\Users\Cohen\nbviz'
NS = 'qzpno'
VEL_FLOOR = 0.04
REVERB = [(3, 0.40), (8, 0.18)]        # (刻延迟, 音量系数) 回声 tap:+0.15s / +0.40s
SUS_MIN_DUR, SUS_PERIOD, SUS_DECAY = 1.6, 10, 0.82   # 时值>1.6s 的音每 0.5s(10 刻)重击,衰减 0.82
LEAD = 3                               # 起手提前刻(首个 schedule 需 >=1)
SEC = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0

notes = json.load(open(os.path.join(HERE, 'notes.json'), encoding='utf-8'))['notes']
if SEC > 0:
    notes = [n for n in notes if n['t'] < SEC]
man = json.load(open(os.path.join(HERE, 'samples_manifest_piano.json'), encoding='utf-8'))
samples = sorted(man['samples'], key=lambda s: s['base_midi']); bases = [s['base_midi'] for s in samples]
def map_note(m):
    j = min(range(len(samples)), key=lambda k: abs(bases[k] - m))
    return samples[j]['id'], round(max(0.5, min(2.0, 2 ** ((m - bases[j]) / 12.0))), 5), abs(m - bases[j])

# --- expand notes into timed play-events (main strike + sustain re-strikes + reverb taps) ---
events, max_stretch = [], 0.0
for n in notes:
    if n['vel'] < VEL_FLOOR:
        continue
    u = int(n['t'] * 20 + 0.5) + LEAD          # round-half-up to game tick (0.05s)
    eid, pitch, ds = map_note(n['midi']); max_stretch = max(max_stretch, ds)
    vol0 = 0.35 + 0.65 * min(1.0, n['vel'])
    strikes = [0]
    dur_ticks = int(n['dur'] * 20)
    if n['dur'] > SUS_MIN_DUR:
        k = SUS_PERIOD
        while k < dur_ticks:
            strikes.append(k); k += SUS_PERIOD
    for si, st in enumerate(strikes):
        v = vol0 * (SUS_DECAY ** si)
        events.append((u + st, eid, pitch, round(v, 3)))
        for d, mlt in REVERB:
            events.append((u + st + d, eid, pitch, round(v * mlt, 3)))
events = [e for e in events if e[3] >= 0.05]
bytick = defaultdict(list)
for tk, eid, pitch, vol in events:
    bytick[tk].append((eid, pitch, vol))
ticks = sorted(bytick)
MAXTICK = ticks[-1]

# preview schedule (04 reads unit_s + events)
json.dump({'unit_s': 0.05, 'ns': NS, 'events': [{'u': tk, 'eid': e[0], 'pitch': e[1], 'vol': e[2]}
                                                 for tk in ticks for e in bytick[tk]]},
          open(os.path.join(HERE, 'schedule.json'), 'w', encoding='utf-8'), indent=0)

# polyphony self-check (samples ring ~1.4s = 28 ticks)
ring = 28
max_overlap = 0
for tk in ticks:
    max_overlap = max(max_overlap, sum(len(bytick[t2]) for t2 in ticks if tk - ring < t2 <= tk))

# ================= RESOURCE PACK (piano) =================
RP = os.path.join(HERE, 'build', f'{NS}_mv')
if os.path.isdir(RP):
    shutil.rmtree(RP)
os.makedirs(os.path.join(RP, f'assets/{NS}/sounds'))
json.dump({"pack": {"pack_format": 64, "description": "qzpno 晴天 piano (Salamander CC-BY 3.0) scheduler v2"}},
          open(os.path.join(RP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
json.dump({s['id']: {"category": "master", "sounds": [{"name": f"{NS}:{s['id']}", "stream": False}]} for s in samples},
          open(os.path.join(RP, f'assets/{NS}/sounds.json'), 'w', encoding='utf-8'))
for s in samples:
    shutil.copyfile(os.path.join(HERE, 'samples_piano', s['file']), os.path.join(RP, f'assets/{NS}/sounds/{s["id"]}.ogg'))

# ================= DATAPACK (scheduler) =================
DP = os.path.join(HERE, 'build', f'{NS}_redstone')
if os.path.isdir(DP):
    shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b):
    w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": "qzpno 晴天 piano scheduler v2 (0.05s)"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))

# one function per populated tick: play its sounds, then schedule the next tick (chain); PLAY flag gates stop
for i, tk in enumerate(ticks):
    lines = [f'execute if score PLAY {NS} matches 0 run return 0']
    for eid, pitch, vol in bytick[tk]:
        lines.append(f'execute as @a at @s run playsound {NS}:{eid} master @s ~ ~ ~ {vol} {pitch} 1')
    if i < len(ticks) - 1:
        lines.append(f'schedule function {NS}:seq/s{i + 1} {ticks[i + 1] - tk}t')
    else:
        lines.append(f'function {NS}:done')
    wf(f'seq/s{i}', lines)

wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set PLAY {NS} 0', 'stopsound @a master',
            f'tellraw @a ["",{{"text":"[qzpno] 晴天钢琴(调度器 v2)loaded. ","color":"aqua"}},{{"text":"/function {NS}:play"}}]'])
wf('setup', [f'tellraw @a "[qzpno] v2 无需建造,直接 /function {NS}:play(声音跟随你,任意位置可听)。"'])
wf('play', [f'execute if score PLAY {NS} matches 1 run return 0', f'scoreboard players set PLAY {NS} 1',
            'stopsound @a master', f'schedule function {NS}:seq/s0 {ticks[0]}t',
            'tellraw @a "[qzpno] GO — 晴天钢琴(0.05s 精度 + 延音 + 混响)."'])
wf('stop', [f'scoreboard players set PLAY {NS} 0', 'stopsound @a master', 'tellraw @a "[qzpno] stopped."'])
wf('done', [f'scoreboard players set PLAY {NS} 0',
            f'tellraw @a "[qzpno] (end) replay: /function {NS}:play;停止:/function {NS}:stop"'])
wf('cleanup', [f'scoreboard players set PLAY {NS} 0', 'stopsound @a master', 'tellraw @a "[qzpno] (v2 无方块需清理) stopped."'])

# ================= self-check + deploy to bridge =================
errs = []
have = {s['id'] for s in samples}
for tk in ticks:
    for eid, pitch, vol in bytick[tk]:
        if eid not in have: errs.append(f'missing {eid}')
        if not (0.5 <= pitch <= 2.0): errs.append(f'pitch oob {pitch}')
for s in samples:
    if not os.path.isfile(os.path.join(RP, f'assets/{NS}/sounds/{s["id"]}.ogg')): errs.append(f'no ogg {s["id"]}')
def deploy(src, sub, name):
    d = os.path.join(BRIDGE, sub); os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, name)
    if os.path.isdir(dst): shutil.rmtree(dst)
    shutil.copytree(src, dst)
deploy(RP, 'resourcepacks', f'{NS}_mv'); deploy(DP, 'datapacks', f'{NS}_redstone')

print('=== 07 scheduler v2 ===')
print(f'notes={len(notes)}  play-events={len(events)} (main+sustain+reverb)  populated ticks={len(ticks)}  span={MAXTICK*0.05:.1f}s')
print(f'resolution=0.05s  pitch stretch max={max_stretch:.1f}st  MAX SIMULTANEOUS≈{max_overlap} (247 cap -> {"OK" if max_overlap<200 else "RISK"})')
print(f'reverb taps={REVERB}  sustain: dur>{SUS_MIN_DUR}s re-strike every {SUS_PERIOD/20:.2f}s')
print(f'seq functions={len(ticks)}')
print('SELF-CHECK:', 'PASS' if not errs else 'FAIL: ' + '; '.join(errs[:5]))
