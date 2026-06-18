"""多声部建造器 — notes.json(全复音)+ 钢琴样本 -> 资源包(qzpno_mv)+ 数据包(qzpno_redstone)。
移植 v7 机制:N 条并行脊柱 + 滑动 forceload 窗口 + 分批建造 + 分批安全拆除 + 重播锁 + load 兜底。
每个音符 -> 就近钢琴 band 的 playsound(pitch=clamp(2^((midi-base)/12),0.5,2));单格复音按音高分配到不同声部。
独立命名空间 qzpno,不碰生产 / qzgtr。Run: <venv-demucs python> 06_build_poly.py [max_sec]
"""
import os, sys, json, math, shutil
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = r'C:\Users\Cohen\nbviz'
NS = 'qzpno'
OX, OZ = 25000, 0                 # 远离 qzgtr(20000)/nbviz(10000)/olk(0)
Y, DELAY, LANE_DZ = -59, 2, 4
BASE, RFACING, BATCH = 'white_wool', 'west', 2500
MAXLANES, VEL_FLOOR = 7, 0.04
TPS = 18.1                          # /tick rate(用户确认可用,精度 0.1)
U = 2 * DELAY / TPS                 # 每格秒数 = 1 个十六分音符:delay-2=4游戏刻 /18.1 = 0.221s ≈ ♩68
SEC = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0     # 0=full; 否则只建前 N 秒

notes = json.load(open(os.path.join(HERE, 'notes.json'), encoding='utf-8'))['notes']
if SEC > 0:
    notes = [n for n in notes if n['t'] < SEC]
man = json.load(open(os.path.join(HERE, 'samples_manifest_piano.json'), encoding='utf-8'))
samples = man['samples']
bands = sorted(set(s['base_midi'] for s in samples))
bl = {(s['base_midi'], s['vlayer']): s['id'] for s in samples}   # (音域band, 力度层) -> 样本 id
def layer_of(vel):
    return 'p' if vel < 0.40 else ('mf' if vel < 0.72 else 'f')   # MIDI 力度 -> 弱/中/强 真实采样
def map_note(m, vel):
    base = min(bands, key=lambda b: abs(b - m))
    eid = bl[(base, layer_of(vel))]
    return eid, round(max(0.5, min(2.0, 2 ** ((m - base) / 12.0))), 5), abs(m - base)

# --- voice-allocate: notes per cell -> distinct lanes (rank by pitch desc) ---
bycell = defaultdict(list)
for n in notes:
    if n['vel'] < VEL_FLOOR:
        continue
    bycell[round(n['t'] / U)].append(n)
lane_notes = [dict() for _ in range(MAXLANES)]
sched, dropped, max_stretch = [], 0, 0.0
for c, grp in bycell.items():
    for i, n in enumerate(sorted(grp, key=lambda x: -x['midi'])):
        if i >= MAXLANES:
            dropped += 1; continue
        eid, pitch, ds = map_note(n['midi'], n['vel']); max_stretch = max(max_stretch, ds)
        vol = round(0.6 + 0.4 * min(1.0, n['vel']), 3)        # 力度层管音色,音量做细微强弱
        lane_notes[i][c] = (eid, pitch, vol)
        sched.append({'cell': c, 'eid': eid, 'pitch': pitch, 'vol': vol})
NLANES = max((L + 1 for L in range(MAXLANES) if lane_notes[L]), default=1)
MAXCELL = max(bycell)
json.dump({'cell_ms': round(U * 1000, 2), 'maxcell': MAXCELL, 'ns': NS, 'cells': sched},
          open(os.path.join(HERE, 'schedule.json'), 'w', encoding='utf-8'), indent=1)

# --- polyphony / sound-cap self-check (samples ring full length, no note-off) ---
samp_dur = max(s['dur'] for s in samples); ring = math.ceil(samp_dur / U)
cells_sorted = sorted(c for c in bycell)
max_overlap = 0
for c in cells_sorted:
    max_overlap = max(max_overlap, sum(1 for e in sched if c - ring < e['cell'] <= c))

# ================= RESOURCE PACK =================
RP = os.path.join(HERE, 'build', f'{NS}_mv')
if os.path.isdir(RP):
    shutil.rmtree(RP)
os.makedirs(os.path.join(RP, f'assets/{NS}/sounds'))
json.dump({"pack": {"pack_format": 64, "description": "qzpno 晴天 piano reconstruction (Salamander CC-BY 3.0)"}},
          open(os.path.join(RP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
json.dump({s['id']: {"category": "master", "sounds": [{"name": f"{NS}:{s['id']}", "stream": False}]} for s in samples},
          open(os.path.join(RP, f'assets/{NS}/sounds.json'), 'w', encoding='utf-8'))
for s in samples:
    shutil.copyfile(os.path.join(HERE, 'samples_piano', s['file']), os.path.join(RP, f'assets/{NS}/sounds/{s["id"]}.ogg'))

# ================= DATAPACK =================
DP = os.path.join(HERE, 'build', f'{NS}_redstone')
if os.path.isdir(DP):
    shutil.rmtree(DP)
os.makedirs(DP)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b):
    w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": "qzpno 晴天 piano polyphonic v1"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

def box(a0, a1, r0, r1):
    return OX + a0, OZ + r0, OX + a1, OZ + r1
def spine(r, lane):                       # one redstone lane @ across=r; lane = {cell:(eid,pitch,vol)}
    sx, sz = OX - 1, OZ + r
    out = [f'setblock {sx} {Y-1} {sz} minecraft:{BASE}']
    for c in range(MAXCELL + 1):
        cx = OX + 2 * c
        if c > 0:
            rx = OX + 2 * c - 1
            out.append(f'setblock {rx} {Y-1} {sz} minecraft:{BASE}')
            out.append(f'setblock {rx} {Y} {sz} minecraft:repeater[facing={RFACING},delay={DELAY}]')
        if c in lane:
            eid, pitch, vol = lane[c]
            cmd = f'execute as @a at @s run playsound {NS}:{eid} master @s ~ ~ ~ {vol} {pitch} 1'
            out.append(f'setblock {cx} {Y-1} {sz} minecraft:command_block[facing=down,conditional=false]{{Command:"{cmd}",auto:0b}}')
        else:
            out.append(f'setblock {cx} {Y-1} {sz} minecraft:{BASE}')
        out.append(f'setblock {cx} {Y} {sz} minecraft:redstone_wire')
    return out

A0, A1 = -7, 2 * MAXCELL + 3
R0, R1 = -3, (NLANES - 1) * LANE_DZ + 2
PBX = OX - 3
build = ['gamerule commandModificationBlockLimit 2147483647']
for L in range(NLANES):
    build += spine(L * LANE_DZ, lane_notes[L])
build += [f'setblock {PBX} {Y-1} {OZ} minecraft:stone',
          f'setblock {PBX} {Y} {OZ} minecraft:command_block[facing=up,conditional=false]{{Command:"function {NS}:play",auto:0b}}',
          f'setblock {PBX} {Y+1} {OZ} minecraft:stone_button[face=floor]']
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]

# setup forceload: whole box, BUT /forceload add 单条命令上限 256 区块 -> 必须按 z 宽度切 x,使每条 <=240 区块
WX0, WZ0, WX1, WZ1 = box(A0, A1, R0, R1)
zc = (WZ1 // 16) - (WZ0 // 16) + 1                 # z 方向区块数
xstep = max(1, 240 // zc)                          # 每条命令沿 x 的区块数,保证 xstep*zc <= 240 < 256
flbuild, cx = [], WX0
while cx <= WX1:
    cxe = min(WX1, cx + xstep * 16 - 1)
    flbuild.append(f'forceload add {cx} {WZ0} {cxe} {WZ1}')
    cx = cxe + 1

# 不再用滑动 forceload 窗口:它每 40 格(8.84s)滑动一次、每次加载新区块=周期性卡顿→实时断音
# (已由排程分析定位:数据本身无周期空白)。改为整盘 forceload 并在播放期间保持(build 已验证 312 区块可承载)。
fl_steps = []

src_pts = [(OX - 1, OZ + L * LANE_DZ) for L in range(NLANES)]
TRIG_CLEAR = [f'setblock {sx} {Y} {sz} minecraft:air' for sx, sz in src_pts]
SCHED_CLEAR = [f'schedule clear {NS}:{f}' for f in ('done', 'fire', 'firestop', 'startbuild')] + \
              [f'schedule clear {NS}:fl/f{i}' for i in range(len(fl_steps))]
END_TICKS = MAXCELL * DELAY * 2 + 200

wf('load', [f'scoreboard objectives add {NS} dummy', f'scoreboard players set BLD {NS} -1',
            f'scoreboard players set CLR {NS} -1', f'scoreboard players set PLAY {NS} 0', 'forceload remove all',
            f'function {NS}:tempo_reset']
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[qzpno] 晴天钢琴(多声部)loaded. ","color":"aqua"}},{{"text":"/function {NS}:setup"}}]'])
wf('setup', [f'scoreboard players set PLAY {NS} 0', 'stopsound @a master', f'scoreboard players set CLR {NS} -1']
   + SCHED_CLEAR + TRIG_CLEAR + flbuild
   + [f'tp @a {PBX} {Y+3} {OZ}', f'schedule function {NS}:startbuild 100t',
      'tellraw @a "[qzpno] reset + forceloading; building in ~5s (wait BUILT)..."'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[qzpno] building (7 lanes)..."')
wf('tick', f'execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n'
           f'execute if score CLR {NS} matches 0.. run function {NS}:clearstep')
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('buildstep', bs)
for k, b in enumerate(batches):
    wf(f'bld/b{k}', b)
wf('builddone', f'scoreboard players set BLD {NS} -1\n'
   f'tellraw @a ["",{{"text":"[qzpno] built (机器保持加载,无滑窗卡顿). ","color":"green"}},{{"text":"press button / /function {NS}:play"}}]')
wf('play', [f'execute if score PLAY {NS} matches 1 run return 0', f'scoreboard players set PLAY {NS} 1',
            'stopsound @a master', f'function {NS}:tempo']
   + TRIG_CLEAR + [f'schedule function {NS}:fire 2t', 'tellraw @a "[qzpno] GO — 晴天钢琴(均匀节奏)."'])
wf('fire', flbuild + [f'setblock {sx} {Y} {sz} minecraft:redstone_block' for sx, sz in src_pts]
   + [f'schedule function {NS}:firestop 6t', f'schedule function {NS}:done {END_TICKS}t'])
wf('firestop', TRIG_CLEAR)
wf('done', f'scoreboard players set PLAY {NS} 0\nforceload remove all\nfunction {NS}:tempo_reset\n'
   f'tellraw @a "[qzpno] (end) replay: /function {NS}:setup; cleanup: /function {NS}:cleanup."')
SEG = 256
clr_segs = (A1 - A0) // SEG + 1
for k in range(clr_segs):
    a0 = A0 + k * SEG; a1 = min(A1, a0 + SEG - 1)
    fx0, fz0, fx1, fz1 = box(a0, a1, R0, R1)
    wf(f'clr/c{k}', f'fill {fx0} {Y-2} {fz0} {fx1} {Y+6} {fz1} air')
wf('cleardone', [f'scoreboard players set CLR {NS} -1', 'forceload remove all', 'tellraw @a "[qzpno] cleaned up."'])
cs = [f'execute if score CLR {NS} matches {k} run function {NS}:clr/c{k}' for k in range(clr_segs)]
cs += [f'execute if score CLR {NS} matches {clr_segs} run function {NS}:cleardone',
       f'execute if score CLR {NS} matches 0..{clr_segs} run scoreboard players add CLR {NS} 1']
wf('clearstep', cs)
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647', f'scoreboard players set PLAY {NS} 0',
               'stopsound @a master', f'scoreboard players set BLD {NS} -1'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'scoreboard players set CLR {NS} 0', f'function {NS}:tempo_reset', 'tellraw @a "[qzpno] tearing down (batched)..."'])
wf('tempo', f'tick rate {TPS}\ntellraw @a "[qzpno] tick rate -> {TPS} (≈♩68,每格 1 个十六分音符,均匀)"')
wf('tempo_reset', 'tick rate 20')

# ================= self-check + deploy to bridge =================
errs = []
have = {s['id'] for s in samples}
for e in sched:
    if e['eid'] not in have: errs.append(f'missing sample {e["eid"]}')
    if not (0.5 <= e['pitch'] <= 2.0): errs.append(f'pitch oob {e["pitch"]}')
for s in samples:
    if not os.path.isfile(os.path.join(RP, f'assets/{NS}/sounds/{s["id"]}.ogg')): errs.append(f'no ogg {s["id"]}')
def deploy(src, sub, name):
    d = os.path.join(BRIDGE, sub); os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, name)
    if os.path.isdir(dst): shutil.rmtree(dst)
    shutil.copytree(src, dst); return dst
deploy(RP, 'resourcepacks', f'{NS}_mv'); deploy(DP, 'datapacks', f'{NS}_redstone')

print('=== 06 poly build (16分网格 + tick rate) ===')
print(f'BPM≈{60/(U*4):.1f}  U(16th)={U*1000:.1f}ms  tick_rate={TPS}  delay={DELAY}  (1 cell = 1 sixteenth)')
print(f'notes used={len(sched)}/{len(notes)} dropped(>{MAXLANES}/cell)={dropped}  lanes={NLANES}  MAXCELL={MAXCELL}')
print(f'machine: {2*MAXCELL} long x {R1-R0} wide  (~{2*MAXCELL//16}x{(R1-R0)//16+1} chunks)  build batches={len(batches)} fl_windows={len(fl_steps)}')
print(f'pitch stretch max={max_stretch:.1f} st  sample ring={ring} cells  MAX SIMULTANEOUS={max_overlap} (247 cap -> {"OK" if max_overlap<200 else "RISK"})')
print('SELF-CHECK:', 'PASS' if not errs else 'FAIL: ' + '; '.join(errs[:5]))
