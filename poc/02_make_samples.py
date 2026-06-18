"""Stage B — Karoryfer Black And Green Guitars (CC0) -> per-note mono .ogg + manifest.
取 green ordinario(twang)的 mf/rr1 单音,跨音域选 ~8 个;下载→削前导→硬截→长淡出→**实测真实基频**→全局归一→ogg。
实测基频规避了 Karoryfer 音名的八度约定问题(不靠文件名推音高)。
Run: <venv-demucs python> 02_make_samples.py
"""
import os, re, json, sys, subprocess, urllib.request
import numpy as np, soundfile as sf, librosa

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(os.path.dirname(HERE), '_work')
TREE = os.path.join(WORK, 'karo_tree.json')
RAWDIR = os.path.join(WORK, 'karo_raw'); os.makedirs(RAWDIR, exist_ok=True)
OUTDIR = os.path.join(HERE, 'samples'); os.makedirs(OUTDIR, exist_ok=True)
REPO = 'sfzinstruments/karoryfer.black-and-green-guitars'
SHA = 'b3b3249d37dc977a1a297bd2dc053e6d9b6b805c'
RAW = f'https://raw.githubusercontent.com/{REPO}/{SHA}/'
SR = 44100
CAP_S = 1.2                 # hard length cap (no note-off -> keep short so notes don't pile up)
N_SAMPLES = 8               # bands across the range

# --- pick a spread of mf/rr1 notes from green/ord ---
tree = json.load(open(TREE, encoding='utf-8'))['tree']
cand = [p['path'] for p in tree if re.search(r'Samples/green/ord/twang_[a-g#b]+\d_mf_rr1\.wav$', p['path'], re.I)]
def tok_midi(path):
    t = re.search(r'twang_([a-g][#b]?\d)_mf', os.path.basename(path), re.I).group(1)
    return librosa.note_to_midi(t[0].upper() + t[1:])
cand = sorted(set(cand), key=tok_midi)
if not cand:
    sys.exit('no green/ord mf/rr1 candidates found in tree')
idx = np.linspace(0, len(cand) - 1, min(N_SAMPLES, len(cand))).round().astype(int)
chosen = [cand[i] for i in sorted(set(idx.tolist()))]
print(f'[B] candidates={len(cand)}  chosen={len(chosen)}')

def fetch(path):
    dst = os.path.join(RAWDIR, os.path.basename(path))
    if not os.path.isfile(dst) or os.path.getsize(dst) == 0:
        urllib.request.urlretrieve(RAW + path, dst)
    return dst

def measure_midi(a):
    f0, vf, vp = librosa.pyin(a, fmin=float(librosa.note_to_hz('E1')), fmax=float(librosa.note_to_hz('E6')),
                              sr=SR, frame_length=4096)
    f0 = f0[np.isfinite(f0)]
    if len(f0) == 0:
        return None, None
    hz = float(np.median(f0))
    return hz, float(librosa.hz_to_midi(hz))

raw = []   # (filename, audio, base_midi, base_hz)
for path in chosen:
    wavp = fetch(path)
    a, _ = librosa.load(wavp, sr=SR, mono=True)
    pk = float(np.max(np.abs(a))) or 1.0
    nz = np.where(np.abs(a) > 0.12 * pk)[0]            # trim leading slow attack -> punchy onset
    if len(nz):
        a = a[nz[0]:]
    a = a[:int(CAP_S * SR)]                            # hard length cap
    fl = min(max(int(0.07 * SR), int(len(a) * 0.35)), len(a))   # long linear fade-out
    if fl:
        a[-fl:] *= np.linspace(1, 0, fl)
    hz, bm = measure_midi(a)
    if hz is None:
        print('   skip (no pitch):', os.path.basename(path)); continue
    raw.append((os.path.basename(path), a.astype(np.float32), round(bm, 2), round(hz, 2)))

if not raw:
    sys.exit('no usable samples')
gpeak = max(float(np.max(np.abs(a))) for _, a, *_ in raw) or 1.0
scale = (10 ** (-1.0 / 20)) / gpeak                    # global normalize -> -1 dBFS peak (keep inter-note balance)

manifest = {'sr': SR, 'source': 'Karoryfer Black And Green Guitars (green ordinario, mf/rr1), CC0', 'samples': []}
for i, (fn, a, bm, hz) in enumerate(sorted(raw, key=lambda r: r[2])):
    oid = f'gtr_b{i}'
    wavp = os.path.join(OUTDIR, oid + '.wav'); oggp = os.path.join(OUTDIR, oid + '.ogg')
    sf.write(wavp, a * scale, SR, subtype='FLOAT')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wavp, '-ac', '1',
                    '-c:a', 'libvorbis', '-q:a', '6', oggp], check=True)
    os.remove(wavp)
    manifest['samples'].append({'id': oid, 'file': oid + '.ogg', 'src': fn,
                                'base_midi': bm, 'base_hz': hz, 'dur': round(len(a) / SR, 3)})
json.dump(manifest, open(os.path.join(HERE, 'samples_manifest.json'), 'w', encoding='utf-8'), indent=1)

# --- verify gate ---
nm = lambda m: librosa.midi_to_note(int(round(m)), unicode=False)
print(f'[B] wrote {len(manifest["samples"])} ogg -> {OUTDIR}')
bases = [s['base_midi'] for s in manifest['samples']]
print(f'[B] measured pitch coverage: {min(bases):.1f}({nm(min(bases))}) .. {max(bases):.1f}({nm(max(bases))})')
for s in manifest['samples']:
    print(f'      {s["id"]:<7} base={s["base_midi"]:>5.1f}({nm(s["base_midi"])})  dur={s["dur"]:.2f}s  src={s["src"]}')
tot = sum(os.path.getsize(os.path.join(OUTDIR, s['file'])) for s in manifest['samples'])
print(f'[B] total ogg {tot/1024:.0f} KB')
