"""精确路线 — MIDI 文件 -> notes.json(复用归档 song_model.py 的 mido 解析)。
这是"用户上传 MIDI 精确复刻"的输入层:符号化音符,无转写损耗。
默认 --melody:按 200ms cell 取最高音(主旋律/天际线),给单声部机器;多声部=后续多轨。
Run: <venv-demucs python> midi_to_notes.py <file.mid> [--melody] [--channel N] [--transpose S] [--start s] [--sec s]
"""
import sys, os, json, mido

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'notes.json')
CELL_MS = 200
a = sys.argv[1:]
MID = a[0]
def opt(flag, default=None, cast=str):
    return cast(a[a.index(flag) + 1]) if flag in a else default
MELODY = ('--melody' in a) or True if '--poly' not in a else False
CHAN = opt('--channel', None, int)
TRANS = opt('--transpose', 0, int)
START = opt('--start', 0.0, float)
SEC = opt('--sec', 0.0, float)

mf = mido.MidiFile(MID)
events, active, t = [], {}, 0.0
for msg in mf:                              # msg.time already in seconds, play order across tracks
    t += msg.time
    if msg.type == 'note_on' and msg.velocity > 0:
        active[(msg.channel, msg.note)] = (t, msg.velocity)
    elif msg.type in ('note_off',) or (msg.type == 'note_on' and msg.velocity == 0):
        k = (msg.channel, msg.note)
        if k in active:
            st, v = active.pop(k)
            events.append({'t': st, 'dur': max(t - st, 0.02), 'ch': msg.channel, 'pitch': msg.note + TRANS, 'vel': v})

if CHAN is not None:
    events = [e for e in events if e['ch'] == CHAN]
if SEC > 0:
    events = [e for e in events if START <= e['t'] < START + SEC]
for e in events:
    e['t'] -= START
events = [e for e in events if e['t'] >= 0]

if MELODY:                                  # top-voice per 200ms cell -> monophonic melody line
    by_cell = {}
    for e in sorted(events, key=lambda x: x['t']):
        c = round(e['t'] * 1000.0 / CELL_MS)
        if c not in by_cell or e['pitch'] > by_cell[c]['pitch']:
            by_cell[c] = e
    events = sorted(by_cell.values(), key=lambda x: x['t'])

notes = [{'t': round(e['t'], 3), 'midi': int(e['pitch']), 'dur': round(e['dur'], 3),
          'vel': round(e['vel'] / 127.0, 3)} for e in events]
json.dump({'sr': None, 'hop': None, 'sec': SEC, 'start': START, 'stemname': 'midi',
           'stem': MID, 'notes': notes}, open(OUT, 'w', encoding='utf-8'), indent=1)

print(f'[MIDI] {os.path.basename(MID)} -> {len(notes)} notes (melody={MELODY}, chan={CHAN}, transpose={TRANS})')
if notes:
    ms = [n['midi'] for n in notes]
    print(f'[MIDI] range {min(ms)}..{max(ms)}  span {max(n["t"] for n in notes):.1f}s')
