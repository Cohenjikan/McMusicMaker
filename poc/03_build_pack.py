"""Stage C — notes.json + samples -> resource pack (qzgtr_mv) + datapack (qzgtr_redstone), deploy to bridge.
重构核心:每个音符 -> 就近 band 的 playsound,pitch=clamp(2^((midi-base)/12),0.5,2.0)。
复用 v7 红石脊柱/forceload/play/cleanup 模式;单声部(每 cell 最多 1 个 playsound,远低于 247)。
独立命名空间 qzgtr,不碰生产。Run: <venv-demucs python> 03_build_pack.py
"""
import os, json, math, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = r'<external-tool-dir>\nbviz'
BRIDGE_DP = os.path.join(BRIDGE, 'datapacks')
BRIDGE_RP = os.path.join(BRIDGE, 'resourcepacks')
NS = 'qzgtr'
OX, OZ = 20000, 0                  # far from nbviz(+10000)/olk(0)
Y, DELAY, CELL_MS = -59, 2, 200
BASE = 'white_wool'
VEL_FLOOR = 0.05                   # drop near-silent transcription artifacts
RFACING = 'west'                   # repeater OUTPUTS opposite its facing -> +x
BATCH = 2500

notes = json.load(open(os.path.join(HERE, 'notes.json'), encoding='utf-8'))['notes']
man = json.load(open(os.path.join(HERE, 'samples_manifest.json'), encoding='utf-8'))
samples = sorted(man['samples'], key=lambda s: s['base_midi'])
bases = [s['base_midi'] for s in samples]

def map_note(m):
    j = min(range(len(samples)), key=lambda k: abs(bases[k] - m))
    pitch = 2 ** ((m - bases[j]) / 12.0)
    return samples[j]['id'], round(max(0.5, min(2.0, pitch)), 5), abs(m - bases[j])

# --- notes -> per-cell command (single lane; keep loudest on collision) ---
cell_note = {}
max_stretch = 0.0
for nt in notes:
    if nt['vel'] < VEL_FLOOR:
        continue
    cell = int(round(nt['t'] * 1000.0 / CELL_MS))
    eid, pitch, dsemi = map_note(nt['midi'])
    max_stretch = max(max_stretch, dsemi)
    vol = round(0.4 + 0.6 * min(1.0, nt['vel']), 3)
    if cell not in cell_note or nt['vel'] > cell_note[cell]['vel']:
        cell_note[cell] = {'eid': eid, 'pitch': pitch, 'vol': vol, 'vel': nt['vel']}
onset = sorted(cell_note)
MAXCELL = onset[-1]
json.dump({'cell_ms': CELL_MS, 'maxcell': MAXCELL, 'ns': NS,
           'cells': [{'cell': c, **cell_note[c]} for c in onset]},
          open(os.path.join(HERE, 'schedule.json'), 'w', encoding='utf-8'), indent=1)

# --- self-check: polyphony (samples have NO note-off -> they ring full length & overlap) ---
samp_dur = max(s['dur'] for s in samples)
ring_cells = math.ceil(samp_dur * 1000.0 / CELL_MS)
max_overlap = 0
for c in onset:
    max_overlap = max(max_overlap, sum(1 for o in onset if c - ring_cells < o <= c))

# ================= RESOURCE PACK (folder) =================
RP = os.path.join(HERE, 'build', f'{NS}_mv')
if os.path.isdir(RP):
    shutil.rmtree(RP)
os.makedirs(os.path.join(RP, f'assets/{NS}/sounds'))
json.dump({"pack": {"pack_format": 64, "description": "qzgtr — 晴天 guitar reconstruction (Karoryfer CC0)"}},
          open(os.path.join(RP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
sounds = {s['id']: {"category": "master", "sounds": [{"name": f"{NS}:{s['id']}", "stream": False}]} for s in samples}
json.dump(sounds, open(os.path.join(RP, f'assets/{NS}/sounds.json'), 'w', encoding='utf-8'))
for s in samples:
    shutil.copyfile(os.path.join(HERE, 'samples', s['file']), os.path.join(RP, f'assets/{NS}/sounds/{s["id"]}.ogg'))

# ================= DATAPACK (folder) =================
DP = os.path.join(HERE, 'build', f'{NS}_redstone')
if os.path.isdir(DP):
    shutil.rmtree(DP)
os.makedirs(DP, exist_ok=True)
def w(rel, c):
    p = os.path.join(DP, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\n').write(c if c.endswith('\n') else c + '\n')
def wf(n, b):
    w(f'data/{NS}/function/{n}.mcfunction', b if isinstance(b, str) else '\n'.join(b))
json.dump({"pack": {"pack_format": 81, "description": "qzgtr 晴天 guitar reconstruction v1"}},
          open(os.path.join(DP, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)
w('data/minecraft/tags/function/load.json', json.dumps({"values": [f"{NS}:load"]}))
w('data/minecraft/tags/function/tick.json', json.dumps({"values": [f"{NS}:tick"]}))

def cmd_of(c):
    o = cell_note[c]
    return f'execute as @a at @s run playsound {NS}:{o["eid"]} master @s ~ ~ ~ {o["vol"]} {o["pitch"]} 1'

# aligned spine (single lane @ across=0): cell = [repeater @2c-1 | dust-tap @2c]; src feeds cell0 @ a=-1
SX, SZ = OX - 1, OZ
build = ['gamerule commandModificationBlockLimit 2147483647',
         f'setblock {SX} {Y-1} {SZ} minecraft:{BASE}']
for c in range(MAXCELL + 1):
    cx = OX + 2 * c
    if c > 0:
        rx = OX + 2 * c - 1
        build.append(f'setblock {rx} {Y-1} {SZ} minecraft:{BASE}')
        build.append(f'setblock {rx} {Y} {SZ} minecraft:repeater[facing={RFACING},delay={DELAY}]')
    if c in cell_note:
        build.append(f'setblock {cx} {Y-1} {SZ} minecraft:command_block[facing=down,conditional=false]{{Command:"{cmd_of(c)}",auto:0b}}')
    else:
        build.append(f'setblock {cx} {Y-1} {SZ} minecraft:{BASE}')
    build.append(f'setblock {cx} {Y} {SZ} minecraft:redstone_wire')
# play button behind cell0
PBX = OX - 3
build += [f'setblock {PBX} {Y-1} {SZ} minecraft:stone',
          f'setblock {PBX} {Y} {SZ} minecraft:command_block[facing=up,conditional=false]{{Command:"function {NS}:play",auto:0b}}',
          f'setblock {PBX} {Y+1} {SZ} minecraft:stone_button[face=floor]']

# world box (1-wide strip) -> forceload whole thing in setup (small: ~ MAXCELL*2 blocks long, 1 wide)
WX0, WX1 = PBX - 2, OX + 2 * MAXCELL + 2
WZ0, WZ1 = SZ - 2, SZ + 2
batches = [build[i:i + BATCH] for i in range(0, len(build), BATCH)]

SCHED_CLEAR = [f'schedule clear {NS}:{f}' for f in ('done', 'fire', 'firestop', 'startbuild')]
TRIG_CLEAR = [f'setblock {SX} {Y} {SZ} minecraft:air']
END_TICKS = MAXCELL * DELAY * 2 + 200

wf('load', [f'scoreboard objectives add {NS} dummy',
            f'scoreboard players set BLD {NS} -1', f'scoreboard players set CLR {NS} -1',
            f'scoreboard players set PLAY {NS} 0', 'forceload remove all'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'tellraw @a ["",{{"text":"[qzgtr] 晴天吉他重构 loaded. ","color":"aqua"}},{{"text":"/function {NS}:setup"}}]'])
wf('setup', [f'scoreboard players set PLAY {NS} 0', 'stopsound @a master', f'scoreboard players set CLR {NS} -1']
   + SCHED_CLEAR + TRIG_CLEAR
   + [f'forceload add {WX0} {WZ0} {WX1} {WZ1}', f'tp @a {PBX} {Y+3} {SZ}',
      f'schedule function {NS}:startbuild 100t',
      'tellraw @a "[qzgtr] reset + forceloading; building in ~5s (wait for BUILT)..."'])
wf('startbuild', f'scoreboard players set BLD {NS} 0\ntellraw @a "[qzgtr] building..."')
wf('tick', f'execute if score BLD {NS} matches 0.. run function {NS}:buildstep\n'
           f'execute if score CLR {NS} matches 0.. run function {NS}:clearstep')
bs = [f'execute if score BLD {NS} matches {k} run function {NS}:bld/b{k}' for k in range(len(batches))]
bs += [f'execute if score BLD {NS} matches {len(batches)} run function {NS}:builddone',
       f'execute if score BLD {NS} matches 0..{len(batches)} run scoreboard players add BLD {NS} 1']
wf('buildstep', bs)
for k, b in enumerate(batches):
    wf(f'bld/b{k}', b)
wf('builddone', f'scoreboard players set BLD {NS} -1\n'
   f'tellraw @a ["",{{"text":"[qzgtr] built. ","color":"green"}},{{"text":"press the button / /function {NS}:play"}}]')
wf('play', [f'execute if score PLAY {NS} matches 1 run return 0',
            f'scoreboard players set PLAY {NS} 1', 'stopsound @a master'] + TRIG_CLEAR
   + [f'schedule function {NS}:fire 2t', 'tellraw @a "[qzgtr] GO — 晴天吉他重构."'])
wf('fire', [f'setblock {SX} {Y} {SZ} minecraft:redstone_block',
            f'schedule function {NS}:firestop 6t', f'schedule function {NS}:done {END_TICKS}t'])
wf('firestop', TRIG_CLEAR)
wf('done', f'scoreboard players set PLAY {NS} 0\nforceload remove all\n'
   f'tellraw @a "[qzgtr] (end) replay: /function {NS}:setup; cleanup: /function {NS}:cleanup."')
# batched clear
SEG = 256
clr_segs = (WX1 - WX0) // SEG + 1
for k in range(clr_segs):
    a0 = WX0 + k * SEG; a1 = min(WX1, a0 + SEG - 1)
    wf(f'clr/c{k}', f'fill {a0} {Y-2} {WZ0} {a1} {Y+6} {WZ1} air')
wf('cleardone', [f'scoreboard players set CLR {NS} -1', 'forceload remove all',
                 'tellraw @a "[qzgtr] cleaned up."'])
cs = [f'execute if score CLR {NS} matches {k} run function {NS}:clr/c{k}' for k in range(clr_segs)]
cs += [f'execute if score CLR {NS} matches {clr_segs} run function {NS}:cleardone',
       f'execute if score CLR {NS} matches 0..{clr_segs} run scoreboard players add CLR {NS} 1']
wf('clearstep', cs)
wf('cleanup', ['gamerule commandModificationBlockLimit 2147483647', f'scoreboard players set PLAY {NS} 0',
               'stopsound @a master', f'scoreboard players set BLD {NS} -1'] + SCHED_CLEAR + TRIG_CLEAR
   + [f'scoreboard players set CLR {NS} 0', 'tellraw @a "[qzgtr] tearing down (batched)..."'])

# ================= self-check (verify gate) =================
errs = []
ref_ids = {o['eid'] for o in cell_note.values()}
have_ids = {s['id'] for s in samples}
miss = ref_ids - have_ids
if miss: errs.append(f'commands reference missing sample ids: {miss}')
for s in samples:
    if not os.path.isfile(os.path.join(RP, f'assets/{NS}/sounds/{s["id"]}.ogg')):
        errs.append(f'missing ogg in RP: {s["id"]}')
for o in cell_note.values():
    if not (0.5 <= o['pitch'] <= 2.0): errs.append(f'pitch out of range: {o}')

# ================= deploy to bridge (folders) =================
def deploy(src, dstroot, name):
    os.makedirs(dstroot, exist_ok=True)
    dst = os.path.join(dstroot, name)
    if os.path.isdir(dst): shutil.rmtree(dst)
    shutil.copytree(src, dst); return dst
dp_dst = deploy(DP, BRIDGE_DP, f'{NS}_redstone')
rp_dst = deploy(RP, BRIDGE_RP, f'{NS}_mv')

print('=== Stage C build report ===')
print(f'notes(used)={len(cell_note)} / transcribed={len(notes)}  MAXCELL={MAXCELL}  length={2*MAXCELL} blocks (~{2*MAXCELL/16:.0f} chunks)')
print(f'pitch stretch max={max_stretch:.1f} semitones (smaller=better timbre; <=6 good)')
pitches = [o['pitch'] for o in cell_note.values()]
print(f'playsound pitch range {min(pitches):.3f}..{max(pitches):.3f} (all within 0.5..2.0)')
print(f'sample ring={ring_cells} cells ({samp_dur:.2f}s); MAX SIMULTANEOUS sounds={max_overlap}  (247 cap -> {"OK" if max_overlap<200 else "RISK"})')
print(f'RP -> {rp_dst}\nDP -> {dp_dst}')
print('SELF-CHECK:', 'PASS' if not errs else ('FAIL: ' + '; '.join(errs)))
