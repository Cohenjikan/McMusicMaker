"""Stage A — 晴天 guitar stem -> notes.json (monophonic, librosa pyin).
POC 转写:用已装的 librosa(无需 basic-pitch)。提取单音主旋律线;basic-pitch 复音留作 Iterate。
Run: <venv-demucs python> 01_transcribe.py [seconds]   (默认 45s 的 POC 窗口;0=整曲)
"""
import sys, os, json
import numpy as np
import librosa

STEMDIR = r'C:\Users\Cohen\mc-noteblock-demo\demucs_out\htdemucs_6s\qingtian_audio'
# 每个声部用合适的音域(避免抓到 bleed 低频):vocals/melody 是单音、pyin 最准、最易听出曲子
RANGES = {'vocals': ('C3', 'C6'), 'guitar': ('E2', 'E6'), 'bass': ('E1', 'G3'),
          'piano': ('A2', 'C6'), 'other': ('C3', 'C6')}
STEMNAME = sys.argv[1] if (len(sys.argv) > 1 and sys.argv[1] in RANGES) else 'vocals'
SEC = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0
START = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0   # 起始秒(跳过纯器乐前奏)
STEM = os.path.join(STEMDIR, STEMNAME + '.wav')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notes.json')
SR = 22050
HOP = 256                       # ~11.6 ms/frame
FMIN = float(librosa.note_to_hz(RANGES[STEMNAME][0]))
FMAX = float(librosa.note_to_hz(RANGES[STEMNAME][1]))
SEMITONE_TOL = 0.6              # frames within this many semitones of the running median = same note
MINDUR = 0.08                   # drop notes shorter than 80 ms (noise)

print(f'[A] load {STEMNAME} ({FMIN:.0f}-{FMAX:.0f}Hz) start={START}s sec={SEC or "full"}')
y, _ = librosa.load(STEM, sr=SR, mono=True, offset=START, duration=(SEC if SEC > 0 else None))
print(f'[A] pyin (fmin={FMIN:.1f} fmax={FMAX:.1f}) ...')
f0, vflag, vprob = librosa.pyin(y, fmin=FMIN, fmax=FMAX, sr=SR, hop_length=HOP, frame_length=2048)
times = librosa.times_like(f0, sr=SR, hop_length=HOP)
rms = librosa.feature.rms(y=y, hop_length=HOP, frame_length=2048)[0]
n = min(len(f0), len(rms), len(times))
f0, vflag, times, rms = f0[:n], vflag[:n], times[:n], rms[:n]
midi = np.where(np.isfinite(f0), librosa.hz_to_midi(f0), np.nan)

# --- segment voiced frames into note events ---
segs = []   # (i0, i1)
i0 = None
for i in range(n):
    voiced = bool(vflag[i]) and np.isfinite(midi[i])
    if voiced and i0 is None:
        i0 = i
        med = midi[i]
    elif voiced and i0 is not None:
        med = np.median(midi[i0:i + 1])
        if abs(midi[i] - med) > SEMITONE_TOL:      # pitch jumped -> new note
            segs.append((i0, i)); i0 = i
    elif (not voiced) and i0 is not None:
        segs.append((i0, i)); i0 = None
if i0 is not None:
    segs.append((i0, n))

rms_peak = float(np.max(rms)) or 1.0
notes = []
for a, b in segs:
    t = float(times[a]); dur = float(times[b - 1] - times[a]) + HOP / SR
    if dur < MINDUR:
        continue
    m = int(round(float(np.median(midi[a:b]))))
    vel = round(float(np.max(rms[a:b]) / rms_peak), 3)
    notes.append({'t': round(t, 3), 'midi': m, 'dur': round(dur, 3), 'vel': vel})

notes = [x for x in notes if x['vel'] >= 0.03]            # drop near-silent artifacts
json.dump({'sr': SR, 'hop': HOP, 'sec': SEC, 'start': START, 'stemname': STEMNAME, 'stem': STEM, 'notes': notes},
          open(OUT, 'w', encoding='utf-8'), indent=1)

# --- verify-gate prints ---
print(f'[A] notes={len(notes)}  -> {OUT}')
if notes:
    ms = [x['midi'] for x in notes]
    lo, hi, md = min(ms), max(ms), int(np.median(ms))
    nm = lambda m: librosa.midi_to_note(m, unicode=False)
    print(f'[A] MIDI range {lo}({nm(lo)}) .. {hi}({nm(hi)})  median {md}({nm(md)})  notes/sec={len(notes)/max(times[-1],1):.2f}')
    print('[A] pitch histogram (per octave):')
    hist = {}
    for m in ms:
        hist[m // 12] = hist.get(m // 12, 0) + 1
    for oct_ in sorted(hist):
        print(f'      MIDI {oct_*12:>3}-{oct_*12+11:<3}: {"#"*hist[oct_]} ({hist[oct_]})')
    print('[A] first 12 notes (t, note, dur, vel):')
    for x in notes[:12]:
        print(f'      t={x["t"]:6.2f}  {nm(x["midi"]):<4}  dur={x["dur"]:.2f}  vel={x["vel"]}')
else:
    print('[A] WARNING: no notes — guitar stem may be too quiet/bleedy; consider bass stem fallback.')
