"""Stage B(piano) — Salamander Grand Piano (CC-BY 3.0, Alexander Holm) -> per-note mono .ogg + manifest.
取 C1..A5 每小三度一个 v9 单音(覆盖晴天钢琴 D1..A5,移调 ≤1.5 半音);下载→削前导→硬截→长淡出→实测/命名校验→全局归一→ogg。
署名:Salamander Grand Piano by Alexander Holm, CC-BY 3.0。Run: <venv-demucs python> 02b_make_piano_samples.py
"""
import os, json, subprocess, urllib.request, urllib.parse
import numpy as np, soundfile as sf, librosa

HERE = os.path.dirname(os.path.abspath(__file__))
RAWDIR = os.path.join(os.path.dirname(HERE), '_work', 'sal_raw'); os.makedirs(RAWDIR, exist_ok=True)
OUTDIR = os.path.join(HERE, 'samples_piano'); os.makedirs(OUTDIR, exist_ok=True)
RAW = 'https://raw.githubusercontent.com/sfzinstruments/SalamanderGrandPiano/master/Samples/'
SR = 44100
CAP_S = 1.4
V = 'v9'
NOTES = ['C1', 'D#1', 'F#1', 'A1', 'C2', 'D#2', 'F#2', 'A2', 'C3', 'D#3', 'F#3', 'A3',
         'C4', 'D#4', 'F#4', 'A4', 'C5', 'D#5', 'F#5', 'A5']

def fetch(note):
    fn = f'{note}{V}.flac'
    dst = os.path.join(RAWDIR, fn.replace('#', 's'))
    if not os.path.isfile(dst) or os.path.getsize(dst) == 0:
        urllib.request.urlretrieve(RAW + urllib.parse.quote(fn), dst)
    return dst

def measure_midi(a):
    f0, vf, vp = librosa.pyin(a, fmin=float(librosa.note_to_hz('A0')), fmax=float(librosa.note_to_hz('C7')),
                              sr=SR, frame_length=4096)
    f0 = f0[np.isfinite(f0)]
    return (float(np.median(f0)) if len(f0) else None)

raw = []
for note in NOTES:
    name_midi = int(librosa.note_to_midi(note))
    p = fetch(note)
    a, _ = librosa.load(p, sr=SR, mono=True)
    pk = float(np.max(np.abs(a))) or 1.0
    nz = np.where(np.abs(a) > 0.12 * pk)[0]
    if len(nz):
        a = a[nz[0]:]
    a = a[:int(CAP_S * SR)]
    fl = min(max(int(0.07 * SR), int(len(a) * 0.30)), len(a))
    if fl:
        a[-fl:] *= np.linspace(1, 0, fl)
    hz = measure_midi(a)
    meas = librosa.hz_to_midi(hz) if hz else None
    # Salamander naming is standard-tuned; trust name unless pyin disagrees by >1.5 st
    base = name_midi if (meas is None or abs(meas - name_midi) <= 1.5) else round(meas)
    raw.append((note, a.astype(np.float32), float(base), round(meas, 2) if meas else None))

gpeak = max(float(np.max(np.abs(a))) for _, a, *_ in raw) or 1.0
scale = (10 ** (-1.0 / 20)) / gpeak
manifest = {'sr': SR, 'source': 'Salamander Grand Piano by Alexander Holm, CC-BY 3.0', 'samples': []}
for i, (note, a, base, meas) in enumerate(sorted(raw, key=lambda r: r[2])):
    oid = f'pno_b{i}'
    wavp = os.path.join(OUTDIR, oid + '.wav'); oggp = os.path.join(OUTDIR, oid + '.ogg')
    sf.write(wavp, a * scale, SR, subtype='FLOAT')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wavp, '-ac', '1',
                    '-c:a', 'libvorbis', '-q:a', '6', oggp], check=True)
    os.remove(wavp)
    manifest['samples'].append({'id': oid, 'file': oid + '.ogg', 'note': note,
                                'base_midi': base, 'meas_midi': meas, 'dur': round(len(a) / SR, 3)})
json.dump(manifest, open(os.path.join(HERE, 'samples_manifest_piano.json'), 'w', encoding='utf-8'), indent=1)

nm = lambda m: librosa.midi_to_note(int(round(m)), unicode=False)
print(f'[Bp] wrote {len(manifest["samples"])} piano ogg -> {OUTDIR}')
bs = [s['base_midi'] for s in manifest['samples']]
print(f'[Bp] coverage {min(bs):.0f}({nm(min(bs))})..{max(bs):.0f}({nm(max(bs))})  (MIDI 晴天 needs 26..81)')
for s in manifest['samples']:
    print(f"      {s['id']:<7} {s['note']:<4} base={s['base_midi']:.0f} meas={s['meas_midi']} dur={s['dur']:.2f}")
tot = sum(os.path.getsize(os.path.join(OUTDIR, s['file'])) for s in manifest['samples'])
print(f'[Bp] total {tot/1024:.0f} KB')
