"""Stage C verify — render schedule.json to audio EXACTLY like MC /playsound would:
each note = its chosen sample resampled by the pitch ratio (pitch changes speed+duration), no note-off
(full sample plays), summed at cell times. This is a faithful offline proxy of the in-game result.
Also trims the original guitar stem for A/B. Run: <venv-demucs python> 04_preview.py
"""
import os, json, subprocess
import numpy as np, soundfile as sf, librosa

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 44100
sched = json.load(open(os.path.join(HERE, 'schedule.json'), encoding='utf-8'))
if 'events' in sched:                                  # scheduler v2: game-tick events
    U = sched['unit_s']
    items = [(e['u'] * U, e['eid'], e['pitch'], e['vol']) for e in sched['events']]
else:                                                  # old redstone-cell format
    CM = sched['cell_ms']
    items = [(c['cell'] * CM / 1000.0, c['eid'], c['pitch'], c['vol']) for c in sched['cells']]
maxt = max((t for t, *_ in items), default=0.0)
cache = {}
def samp(eid):
    if eid not in cache:
        sd = 'samples_piano' if eid.startswith('pno') else 'samples'
        a, _ = librosa.load(os.path.join(HERE, sd, eid + '.ogg'), sr=SR, mono=True)
        cache[eid] = a.astype(np.float32)
    return cache[eid]

end = int((maxt + 3.0) * SR)
mix = np.zeros(end + SR, np.float32)
for (t, eid, pitch, vol) in items:
    a = samp(eid); p = float(pitch)
    idx = np.arange(0, len(a), p)                       # resample by pitch ratio (MC playsound = speed/pitch change)
    a2 = np.interp(idx, np.arange(len(a)), a).astype(np.float32) * float(vol)
    t0 = int(t * SR)
    mix[t0:t0 + len(a2)] += a2

pk = float(np.max(np.abs(mix))) or 1.0
mix *= (10 ** (-1.0 / 20)) / pk
wavp = os.path.join(HERE, 'reconstruction_preview.wav')
sf.write(wavp, mix, SR)
oggp = os.path.join(HERE, 'reconstruction_preview.ogg')
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wavp, '-c:a', 'libvorbis', '-q:a', '5', oggp], check=True)

# original stem for A/B — match the transcribed stem + window (from notes.json)
nj = json.load(open(os.path.join(HERE, 'notes.json'), encoding='utf-8'))
stemname = nj.get('stemname', 'guitar'); start = float(nj.get('start', 0.0))
STEM = os.path.join(r'C:\Users\Cohen\mc-noteblock-demo\demucs_out\htdemucs_6s\qingtian_audio', stemname + '.wav')
sec = maxt + 2.0
origp = os.path.join(HERE, f'original_{stemname}.ogg')
if os.path.isfile(STEM):
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{start:.2f}', '-t', f'{sec:.2f}', '-i', STEM,
                    '-ac', '1', '-c:a', 'libvorbis', '-q:a', '5', origp], check=True)
else:
    origp = None
    print('(no source stem audio for A/B — symbolic MIDI input)')

print(f'events rendered={len(items)}  dur={len(mix)/SR:.1f}s')
print(f'-> {oggp} ({os.path.getsize(oggp)//1024} KB)')
if origp:
    print(f'-> {origp} ({os.path.getsize(origp)//1024} KB)  (original stem, A/B)')
