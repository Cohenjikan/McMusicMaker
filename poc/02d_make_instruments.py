"""Stage B(instruments)— build NEW sample libraries beyond piano so a song can be
re-performed as a multi-instrument band (Family A "RedPiano" real-note-block re-performance).

Produces 4 instruments, each mirroring the piano layout:
  poc/samples_<INST>/<id>.ogg   +   poc/samples_manifest_<INST>.json
  manifest schema = {sr, source, samples:[{id,file,note,base_midi,vlayer,dur},...]}

  1. bass   — pitched, MIDI 28..52 step 3 (E1..E3), 1 layer "mf"  (~9)
  2. lead   — pitched, MIDI 48..84 step 3 (C3..C6), 1 layer "mf"  (~13)
  3. pad    — pitched, MIDI 36..81 step 3,          1 layer "mf"  (~16)
  4. drums  — one-shots (kick/snare/hihat/tom/crash), vlayer="x"  (~5)

SOURCES
  drums -> REAL samples from Versilian Community Sample Library (VCSL), sgossner/VCSL, CC0-1.0.
           wav files are NOT git-lfs in that repo, so raw.githubusercontent.com gives real audio
           (verified: returns RIFF/WAVE, not an LFS pointer). Fully reproducible like Salamander.
  bass/lead/pad -> SYNTHESIZED (numpy). VCSL (the one confirmed-reproducible CC0 lib) has no
           electric/acoustic bass, no clean electric-guitar lead, and no warm string/synth pad
           (only pianos/harpsichords/mallets/harps). Karoryfer bass/guitar repos are NOT CC0
           (attribution/donationware). Per spec, when reliable per-note real downloads aren't
           findable in reasonable effort, fall back to high-quality numpy synthesis (ADSR +
           harmonics) for THAT instrument so the script ALWAYS produces a full set. These are
           marked "synthesized (numpy)" in the manifest source.

Conventions copied from 02c_make_piano_velocity.py: mono, 44100 Hz, ffmpeg libvorbis -q:a 6,
pitched sustain capped 2.8s with light 10% fade; drums keep natural length, minimal fade.

Run: <external-tool-dir>\\mc-noteblock-demo\\venv-demucs\\Scripts\\python.exe 02d_make_instruments.py
"""
import os, json, subprocess, urllib.request, urllib.parse
import numpy as np, soundfile as sf, librosa

HERE = os.path.dirname(os.path.abspath(__file__))
RAWDIR = os.path.join(os.path.dirname(HERE), '_work', 'vcsl_raw'); os.makedirs(RAWDIR, exist_ok=True)
SR = 44100
CAP_S = 2.8                       # pitched sustain length (match piano)
VCSL_RAW = 'https://raw.githubusercontent.com/sgossner/VCSL/master/'
VCSL_SRC = 'Versilian Community Sample Library (VCSL) by Versilian Studios / sgossner, CC0-1.0'
SYN_SRC  = 'synthesized (numpy) — ADSR + harmonics, no external samples, public domain'

rng = np.random.default_rng(7)   # reproducible noise for synth/drums

# ---------------------------------------------------------------- shared helpers
def midi_to_id_note(m):
    """MIDI int -> (slug like 'c3', display note like 'C3'). Uses sharps, no unicode."""
    nm = librosa.midi_to_note(int(m), unicode=False)        # e.g. 'C#3'
    return nm.replace('#', 's').lower(), nm

def light_fade_cap(a):
    """Cap to CAP_S and apply light 10% trailing fade (keeps natural sustain)."""
    a = a[:int(CAP_S * SR)]
    fl = min(int(len(a) * 0.10), len(a))
    if fl:
        a[-fl:] *= np.linspace(1, 0, fl)
    return a

def adsr(n, a_s, d_s, s_lvl, r_s):
    """Linear-ish ADSR envelope of length n samples (sustain fills the middle)."""
    A, D, R = int(a_s * SR), int(d_s * SR), int(r_s * SR)
    S = max(n - A - D - R, 0)
    env = np.concatenate([
        np.linspace(0, 1, A, endpoint=False) if A else np.array([]),
        np.linspace(1, s_lvl, D, endpoint=False) if D else np.array([]),
        np.full(S, s_lvl),
        np.linspace(s_lvl, 0, R) if R else np.array([]),
    ])
    if len(env) < n:
        env = np.concatenate([env, np.full(n - len(env), 0.0)])
    return env[:n].astype(np.float32)

def onepole_lp(x, cutoff_hz):
    """Cheap one-pole low-pass; cutoff in Hz. Tames buzzy saw/square harmonics."""
    if cutoff_hz >= SR / 2:
        return x
    dt = 1.0 / SR
    rc = 1.0 / (2 * np.pi * cutoff_hz)
    alpha = dt / (rc + dt)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += alpha * (x[i] - acc)
        y[i] = acc
    return y

def write_ogg(outdir, oid, audio):
    """float32 mono -> wav -> ffmpeg libvorbis q6 ogg; remove wav. Returns ogg path."""
    wavp = os.path.join(outdir, oid + '.wav'); oggp = os.path.join(outdir, oid + '.ogg')
    sf.write(wavp, audio.astype(np.float32), SR, subtype='FLOAT')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wavp, '-ac', '1',
                    '-c:a', 'libvorbis', '-q:a', '6', oggp], check=True)
    os.remove(wavp)
    return oggp

def finish(inst, source, records):
    """records: list of (oid, note, base_midi, vlayer, audio_already_normed). Write manifest."""
    outdir = os.path.join(HERE, f'samples_{inst}'); os.makedirs(outdir, exist_ok=True)
    manifest = {'sr': SR, 'source': source, 'samples': []}
    for oid, note, base, vlayer, audio in sorted(records, key=lambda r: (r[2], r[0])):
        write_ogg(outdir, oid, audio)
        manifest['samples'].append({'id': oid, 'file': oid + '.ogg', 'note': note,
                                    'base_midi': float(base), 'vlayer': vlayer,
                                    'dur': round(len(audio) / SR, 3)})
    json.dump(manifest, open(os.path.join(HERE, f'samples_manifest_{inst}.json'), 'w',
                             encoding='utf-8'), indent=1)
    return outdir, manifest

# ---------------------------------------------------------------- synth voices
def synth_bass(f0, dur=CAP_S):
    """Finger/electric synth bass: detuned saws + sub sine, low-pass that opens then closes,
    punchy pluck ADSR. Harmonics via bandlimited-ish additive saw."""
    n = int(dur * SR); t = np.arange(n) / SR
    def saw(f):
        y = np.zeros(n)
        k = 1
        while k * f < SR / 2 and k <= 40:
            y += ((-1) ** (k + 1)) * np.sin(2 * np.pi * k * f * t) / k
            k += 1
        return y
    body = 0.6 * saw(f0) + 0.6 * saw(f0 * 1.005) + 0.5 * saw(f0 * 0.995)   # slight detune
    sub = 0.9 * np.sin(2 * np.pi * f0 * t)                                  # sub fundamental
    x = 0.5 * body + 0.5 * sub
    # moving low-pass: bright attack -> settles; emulate by blend of two fixed cutoffs
    bright = onepole_lp(x, min(f0 * 12, 4500))
    dark = onepole_lp(x, min(f0 * 4, 1400))
    sweep = np.exp(-t * 6.0)                       # 1->0 over ~0.2s
    x = sweep * bright + (1 - sweep) * dark
    env = adsr(n, 0.005, 0.10, 0.55, 0.30)
    return x * env

def synth_lead(f0, dur=CAP_S):
    """Bright pluck/synth lead: square+saw blend, fast attack, medium decay, slight vibrato,
    low-pass to keep it from being harsh."""
    n = int(dur * SR); t = np.arange(n) / SR
    vib = 1.0 + 0.004 * np.sin(2 * np.pi * 5.5 * t)
    ph = 2 * np.pi * f0 * np.cumsum(vib) / SR
    sq = np.sign(np.sin(ph))
    sw = np.zeros(n); k = 1
    while k * f0 < SR / 2 and k <= 30:
        sw += ((-1) ** (k + 1)) * np.sin(k * ph) / k
        k += 1
    x = 0.45 * sq + 0.55 * sw
    x = onepole_lp(x, min(f0 * 8 + 1500, 9000))
    env = adsr(n, 0.004, 0.18, 0.4, 0.5)
    return x * env

def synth_pad(f0, dur=CAP_S):
    """Warm sustained pad: additive sine stack (slightly inharmonic + detuned voices) with a
    slow chorus shimmer and soft attack/release. Choir/string-ish."""
    n = int(dur * SR); t = np.arange(n) / SR
    partials = [(1, 1.0), (2, 0.5), (3, 0.32), (4, 0.18), (5, 0.12), (6, 0.07)]
    x = np.zeros(n)
    for det in (0.997, 1.0, 1.003):                # 3 detuned voices = ensemble width
        for h, amp in partials:
            drift = 1.0 + 0.0015 * np.sin(2 * np.pi * (0.2 + 0.05 * h) * t)  # slow shimmer
            x += amp * np.sin(2 * np.pi * f0 * h * det * t * drift)
    x = onepole_lp(x, min(f0 * 8 + 2000, 8000))
    env = adsr(n, 0.35, 0.4, 0.7, 0.6)             # soft swell, long release
    return x * env

# ---------------------------------------------------------------- synth drum fallback
def syn_kick(dur=0.6):
    n = int(dur * SR); t = np.arange(n) / SR
    f = 120 * np.exp(-t * 30) + 45                 # pitch drop 120->45 Hz
    x = np.sin(2 * np.pi * np.cumsum(f) / SR)
    click = rng.standard_normal(int(0.004 * SR)) * np.linspace(1, 0, int(0.004 * SR))
    x[:len(click)] += 0.6 * click
    return x * adsr(n, 0.001, 0.05, 0.0, dur - 0.051)

def syn_snare(dur=0.4):
    n = int(dur * SR); t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    tone = 0.5 * (np.sin(2 * np.pi * 180 * t) + np.sin(2 * np.pi * 240 * t))
    x = 0.7 * noise + 0.3 * tone
    return x * adsr(n, 0.001, 0.08, 0.0, dur - 0.081)

def syn_hihat(dur=0.18):
    n = int(dur * SR)
    x = onepole_lp(rng.standard_normal(n), 9000)
    x = x - onepole_lp(x, 6000)                    # crude high-pass (bright metallic)
    return x * adsr(n, 0.0005, 0.04, 0.0, dur - 0.041)

def syn_tom(dur=0.5):
    n = int(dur * SR); t = np.arange(n) / SR
    f = 180 * np.exp(-t * 8) + 90
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.1 * rng.standard_normal(n)
    return x * adsr(n, 0.001, 0.06, 0.0, dur - 0.061)

def syn_crash(dur=1.4):
    n = int(dur * SR)
    x = onepole_lp(rng.standard_normal(n), 12000)
    x = x - onepole_lp(x, 4000)
    return x * adsr(n, 0.001, 0.2, 0.25, dur - 0.201)

# ---------------------------------------------------------------- builders
def build_pitched(inst, lo, hi, step, synth_fn):
    """Synthesize one 'mf' layer per MIDI band, global-normalize to -1 dBFS, write."""
    midis = list(range(lo, hi + 1, step))
    voices = []
    for m in midis:
        f0 = float(librosa.midi_to_hz(m))
        a = light_fade_cap(synth_fn(f0).astype(np.float32))
        slug, note = midi_to_id_note(m)
        voices.append((f'{inst}_{slug}_mf', note, m, 'mf', a))
    gpeak = max(float(np.max(np.abs(a))) for *_, a in voices) or 1.0
    scale = (10 ** (-1.0 / 20)) / gpeak
    voices = [(*v[:4], v[4] * scale) for v in voices]
    return finish(inst, SYN_SRC, voices)

# drum spec: (id_key, base_midi[GM perc], vcsl_relpath_or_None, synth_fn, cap_s, fade_frac)
DRUMS = [
    ('kick', 36, 'Membranophones/Struck Membranophones/Bass Drum 1/BDrumNew_hit_v7_rr1_Sum.wav',
        syn_kick, 0.6, 0.02),
    ('snare', 38, 'Membranophones/Struck Membranophones/Snare Drum, Modern 1/Snare2_HitSN_v7_rr1_Mid.wav',
        syn_snare, 0.5, 0.02),
    ('hihat_closed', 42, 'Idiophones/Struck Idiophones/Hi-Hat Cymbal/HiHat_Close_rr1_Mid.wav',
        syn_hihat, 0.25, 0.02),
    ('tom', 45, 'Membranophones/Struck Membranophones/Tom 1/Stick/TomH_HitS_v4_rr1_Mid.wav',
        syn_tom, 0.6, 0.02),
    ('crash', 49, 'Idiophones/Struck Idiophones/Suspended Cymbal 1/susCymb1_hit_fff1.wav',
        syn_crash, 1.5, 0.02),
]

def fetch_vcsl(relpath):
    """Download a VCSL wav to cache; return local path or None on failure. Detects LFS pointer."""
    fn = relpath.split('/')[-1].replace('#', 's')
    dst = os.path.join(RAWDIR, fn)
    if not os.path.isfile(dst) or os.path.getsize(dst) == 0:
        url = VCSL_RAW + urllib.parse.quote(relpath)
        try:
            urllib.request.urlretrieve(url, dst)
        except Exception as e:
            print(f'  [drum] download FAILED {fn}: {e}')
            return None
    if os.path.getsize(dst) < 2000:                # LFS pointer / truncated -> not real audio
        print(f'  [drum] {fn} too small ({os.path.getsize(dst)}B) — treating as unavailable')
        return None
    return dst

def build_drums():
    """Prefer real VCSL one-shots; per-drum fall back to synthesis if download fails.
    Mixed-source label reflects what actually happened."""
    voices = []; used_real = 0; used_syn = 0
    for key, base, relpath, synth_fn, cap_s, fade_frac in DRUMS:
        a = None; real = False
        if relpath:
            p = fetch_vcsl(relpath)
            if p:
                a, _ = librosa.load(p, sr=SR, mono=True)   # downmix stereo->mono, resample
                # trim leading silence (same idea as piano)
                pk = float(np.max(np.abs(a))) or 1.0
                nz = np.where(np.abs(a) > 0.02 * pk)[0]
                if len(nz):
                    a = a[nz[0]:]
                a = a[:int(cap_s * SR)]
                real = True
        if a is None:
            a = synth_fn()
            used_syn += 1
        else:
            used_real += 1
        a = a.astype(np.float32)
        fl = min(int(len(a) * fade_frac), len(a))          # minimal fade, avoid end click
        if fl:
            a[-fl:] *= np.linspace(1, 0, fl)
        voices.append((f'drum_{key}_x', key, base, 'x', a))
    # global-normalize across the kit
    gpeak = max(float(np.max(np.abs(a))) for *_, a in voices) or 1.0
    scale = (10 ** (-1.0 / 20)) / gpeak
    voices = [(*v[:4], v[4] * scale) for v in voices]
    if used_real and used_syn:
        src = f'{VCSL_SRC} (real: {used_real} one-shots) + {SYN_SRC} (fallback: {used_syn})'
    elif used_real:
        src = VCSL_SRC
    else:
        src = SYN_SRC
    return finish('drums', src, voices)

# ---------------------------------------------------------------- run
def report(inst, outdir, manifest, kind):
    ss = manifest['samples']
    bs = sorted(set(s['base_midi'] for s in ss))
    nm = lambda m: librosa.midi_to_note(int(m), unicode=False)
    tot = 0; missing = []
    for s in ss:
        fp = os.path.join(outdir, s['file'])
        if not os.path.isfile(fp) or os.path.getsize(fp) == 0:
            missing.append(s['file'])
        else:
            tot += os.path.getsize(fp)
    rng_txt = (f'{min(bs):.0f}({nm(min(bs))})..{max(bs):.0f}({nm(max(bs))})'
               if inst != 'drums' else
               'GM perc ' + ','.join(f'{s["note"]}={s["base_midi"]:.0f}' for s in ss))
    print(f'[{inst}] {len(ss)} ogg | {kind} | MIDI {rng_txt} | {tot/1024:.0f} KB'
          + (f' | MISSING {missing}' if missing else ' | all files present'))
    print(f'        source: {manifest["source"]}')
    return missing

if __name__ == '__main__':
    print('=== 02d_make_instruments: building bass / lead / pad (synth) + drums (real VCSL) ===')
    results = []
    od, mf = build_pitched('bass', 28, 52, 3, synth_bass); results.append(('bass', od, mf, 'SYNTH'))
    od, mf = build_pitched('lead', 48, 84, 3, synth_lead); results.append(('lead', od, mf, 'SYNTH'))
    od, mf = build_pitched('pad', 36, 81, 3, synth_pad);  results.append(('pad', od, mf, 'SYNTH'))
    od, mf = build_drums();                                results.append(('drums', od, mf, 'REAL/VCSL'))

    print('\n--- VERIFY ---')
    all_missing = []
    for inst, od, mf, kind in results:
        all_missing += report(inst, od, mf, kind)
    grand = sum(sum(os.path.getsize(os.path.join(od, s['file']))
                    for s in mf['samples']) for _, od, mf, _ in results)
    print(f'\nTOTAL {sum(len(mf["samples"]) for _,_,mf,_ in results)} samples across '
          f'{len(results)} instruments, {grand/1024:.0f} KB')
    print('RESULT: ' + ('OK — all manifest oggs exist & non-empty' if not all_missing
                        else f'FAIL — missing {all_missing}'))
