"""Stage B(piano v2)— Salamander Grand Piano,每音取 3 个力度层(弱/中/强)+ 更长样本。
解决"强弱无法调整/档次差":按 MIDI 力度选真实力度采样(真音色变化),全局归一保留 p<f 的自然强弱;
样本加长(2.8s)+ 轻淡出,保留钢琴自然延音。署名 Salamander Grand Piano / Alexander Holm / CC-BY 3.0。
Run: <venv-demucs python> 02c_make_piano_velocity.py
"""
import os, json, subprocess, urllib.request, urllib.parse
import numpy as np, soundfile as sf, librosa

HERE = os.path.dirname(os.path.abspath(__file__))
RAWDIR = os.path.join(os.path.dirname(HERE), '_work', 'sal_raw'); os.makedirs(RAWDIR, exist_ok=True)
OUTDIR = os.path.join(HERE, 'samples_piano'); os.makedirs(OUTDIR, exist_ok=True)
RAW = 'https://raw.githubusercontent.com/sfzinstruments/SalamanderGrandPiano/master/Samples/'
SR = 44100
CAP_S = 2.8                                   # 更长 -> 自然延音(之前 1.4s 太短=断气)
NOTES = ['C1', 'D#1', 'F#1', 'A1', 'C2', 'D#2', 'F#2', 'A2', 'C3', 'D#3', 'F#3', 'A3',
         'C4', 'D#4', 'F#4', 'A4', 'C5', 'D#5', 'F#5', 'A5']
VLAYERS = [('p', 'v4'), ('mf', 'v9'), ('f', 'v14')]   # 弱/中/强 三档 Salamander 力度层

def slug(note):
    return note.replace('#', 's').lower()
def fetch(note, vtok):
    fn = f'{note}{vtok}.flac'
    dst = os.path.join(RAWDIR, fn.replace('#', 's'))
    if not os.path.isfile(dst) or os.path.getsize(dst) == 0:
        urllib.request.urlretrieve(RAW + urllib.parse.quote(fn), dst)
    return dst

raw = []                                      # (note, lname, audio, base_midi)
for note in NOTES:
    base = int(librosa.note_to_midi(note))    # Salamander 标准律,音名即真实音高
    for lname, vtok in VLAYERS:
        a, _ = librosa.load(fetch(note, vtok), sr=SR, mono=True)
        pk = float(np.max(np.abs(a))) or 1.0
        nz = np.where(np.abs(a) > 0.12 * pk)[0]
        if len(nz):
            a = a[nz[0]:]
        a = a[:int(CAP_S * SR)]
        fl = min(int(len(a) * 0.10), len(a))  # 轻淡出(只削最后 10%)-> 保留延音
        if fl:
            a[-fl:] *= np.linspace(1, 0, fl)
        raw.append((note, lname, a.astype(np.float32), float(base)))

gpeak = max(float(np.max(np.abs(a))) for _, _, a, _ in raw) or 1.0
scale = (10 ** (-1.0 / 20)) / gpeak           # 全局归一:保留 p<mf<f 的自然强弱差
manifest = {'sr': SR, 'source': 'Salamander Grand Piano by Alexander Holm, CC-BY 3.0', 'samples': []}
for note, lname, a, base in sorted(raw, key=lambda r: (r[3], r[1])):
    oid = f'pno_{slug(note)}_{lname}'
    wavp = os.path.join(OUTDIR, oid + '.wav'); oggp = os.path.join(OUTDIR, oid + '.ogg')
    sf.write(wavp, a * scale, SR, subtype='FLOAT')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wavp, '-ac', '1',
                    '-c:a', 'libvorbis', '-q:a', '6', oggp], check=True)
    os.remove(wavp)
    manifest['samples'].append({'id': oid, 'file': oid + '.ogg', 'note': note,
                                'base_midi': base, 'vlayer': lname, 'dur': round(len(a) / SR, 3)})
json.dump(manifest, open(os.path.join(HERE, 'samples_manifest_piano.json'), 'w', encoding='utf-8'), indent=1)

nm = lambda m: librosa.midi_to_note(int(m), unicode=False)
bs = sorted(set(s['base_midi'] for s in manifest['samples']))
print(f'[Bpv] wrote {len(manifest["samples"])} ogg ({len(bs)} 音 x {len(VLAYERS)} 力度层) -> {OUTDIR}')
print(f'[Bpv] 音域 {min(bs):.0f}({nm(min(bs))})..{max(bs):.0f}({nm(max(bs))})  cap={CAP_S}s  力度层={[l for l,_ in VLAYERS]}')
tot = sum(os.path.getsize(os.path.join(OUTDIR, s['file'])) for s in manifest['samples'])
print(f'[Bpv] total {tot/1024:.0f} KB')
