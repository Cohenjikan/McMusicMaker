#!/usr/bin/env python3
"""
transcribe_dyf.py
=================
Transcribe the Demucs stems of "Do You Feel It" (dyfi) into per-instrument
note sequences for a Minecraft real-note-block re-performance (Family A).

Outputs (project standard notes schema) into this folder:
  notes_dyf_bass.json   <- bass stem   (pyin monophonic, octave-folded)
  notes_dyf_drums.json  <- drums stem  (onset percussion, GM keys 36/38/42)
  notes_dyf_piano.json  <- piano stem  (basic-pitch polyphonic if avail, else pyin mono)
  notes_dyf_lead.json   <- guitar stem (basic-pitch polyphonic if avail, else pyin mono)
  notes_dyf_pad.json    <- other stem  (pyin monophonic, long sustain; may be skipped if too noisy)

Schema: {"notes":[{"t":seconds,"midi":int,"vel":0..1,"dur":seconds}, ...]}

vocals stem is SKIPPED ENTIRELY by design.

Runtime:
  * librosa / numpy / soundfile work uses venv-demucs python (the interpreter
    this script is normally launched with).
  * basic-pitch (piano + lead) is invoked as a SUBPROCESS using a separate
    venv (venv-bp) because it pulls a heavy tensorflow/onnx stack. If that
    venv / package is missing, those two stems fall back to pyin monophonic.

Reproducible: just run
  C:/Users/Cohen/mc-noteblock-demo/venv-demucs/Scripts/python.exe transcribe_dyf.py
"""

import json
import os
import subprocess
import sys
import tempfile

import numpy as np

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------
STEM_DIR = r"C:\Users\Cohen\mc-noteblock-demo\demucs_out\htdemucs_6s\dyfi"
ANALYSIS_JSON = r"C:\Users\Cohen\mc-noteblock-demo\stems_analysis_dyfi.json"
OUT_DIR = r"C:\Users\Cohen\Desktop\McMusicMaker\poc"
BP_PYTHON = r"C:\Users\Cohen\mc-noteblock-demo\venv-bp\Scripts\python.exe"

SR = 22050  # analysis sample rate for librosa work (downsample from 44.1k)

# General MIDI percussion keys (so the builder can map midi -> drum sample)
GM_KICK = 36
GM_SNARE = 38
GM_HIHAT = 42

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def stem_path(name):
    return os.path.join(STEM_DIR, f"{name}.wav")


def out_path(name):
    return os.path.join(OUT_DIR, f"notes_dyf_{name}.json")


def write_notes(name, notes):
    notes = sorted(notes, key=lambda n: (round(n["t"], 4), n["midi"]))
    path = out_path(name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"notes": notes}, fh)
    return path


def load_analysis():
    with open(ANALYSIS_JSON, "r", encoding="utf-8") as fh:
        return json.load(fh)


def summarize(name, notes, method):
    """Return a one-line dict summary and print a human line."""
    if not notes:
        print(f"[{name:5s}] EMPTY ({method})")
        return {"name": name, "n": 0, "method": method}
    mids = [n["midi"] for n in notes]
    ends = [n["t"] + n["dur"] for n in notes]
    total = max(ends)
    info = {
        "name": name,
        "n": len(notes),
        "midi_min": min(mids),
        "midi_max": max(mids),
        "total_dur": round(total, 2),
        "method": method,
    }
    print(
        f"[{name:5s}] notes={info['n']:4d}  midi={info['midi_min']:3d}..{info['midi_max']:3d}"
        f"  dur={info['total_dur']:7.2f}s  via {method}"
    )
    return info


# ---------------------------------------------------------------------------
# pyin monophonic transcription
# ---------------------------------------------------------------------------

def pyin_track(y, sr, fmin, fmax):
    """Run librosa.pyin -> arrays (f0_midi, voiced_flag, times, rms_frames)."""
    import librosa

    hop = 512
    f0, voiced_flag, voiced_prob = librosa.pyin(
        y, fmin=fmin, fmax=fmax, sr=sr, hop_length=hop, fill_na=np.nan
    )
    times = librosa.times_like(f0, sr=sr, hop_length=hop)
    midi = librosa.hz_to_midi(f0)  # nan where unvoiced
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    # align rms length to f0 length
    n = min(len(midi), len(rms), len(times))
    return midi[:n], voiced_flag[:n], times[:n], rms[:n]


def segment_pyin(midi, times, rms, *, min_dur=0.08, max_gap=0.06,
                 fold_low=None, fold_high=None):
    """
    Turn a per-frame midi contour into discrete note events by grouping
    consecutive frames whose rounded pitch is stable.

    fold_low / fold_high: if set, octave-fold any rounded pitch outside the
    [fold_low, fold_high] window back inside (kills pyin octave jumps that are
    musically implausible, e.g. bass leaping an octave up).
    """
    notes = []
    n = len(midi)
    cur_pitch = None
    cur_start = None
    cur_vels = []
    last_voiced_t = None

    def fold(p):
        if fold_low is None:
            return p
        while p > fold_high:
            p -= 12
        while p < fold_low:
            p += 12
        return p

    def flush(end_t):
        nonlocal cur_pitch, cur_start, cur_vels
        if cur_pitch is not None and end_t - cur_start >= min_dur:
            vel = float(np.clip(np.percentile(cur_vels, 80) if cur_vels else 0.3, 0.0, 1.0))
            notes.append({
                "t": round(float(cur_start), 4),
                "midi": int(cur_pitch),
                "vel": round(vel, 4),
                "dur": round(float(end_t - cur_start), 4),
            })
        cur_pitch = None
        cur_start = None
        cur_vels = []

    for i in range(n):
        m = midi[i]
        t = times[i]
        if np.isnan(m):
            # unvoiced: if gap long enough, close current note
            if last_voiced_t is not None and (t - last_voiced_t) > max_gap:
                flush(last_voiced_t)
            continue
        p = fold(int(round(m)))
        if cur_pitch is None:
            cur_pitch = p
            cur_start = t
            cur_vels = []
        elif p != cur_pitch:
            flush(t)
            cur_pitch = p
            cur_start = t
            cur_vels = []
        cur_vels.append(rms[i])
        last_voiced_t = t

    if last_voiced_t is not None:
        flush(last_voiced_t)

    # normalize velocity across track to a musical 0.25..1.0 band
    if notes:
        vmax = max(x["vel"] for x in notes) or 1.0
        for x in notes:
            x["vel"] = round(float(np.clip(0.25 + 0.75 * (x["vel"] / vmax), 0.0, 1.0)), 4)
    return notes


def transcribe_pyin_mono(name, fmin, fmax, *, min_dur=0.08, max_gap=0.06,
                         fold_low=None, fold_high=None, max_dur=None):
    import librosa
    y, sr = librosa.load(stem_path(name), sr=SR, mono=True)
    midi, voiced, times, rms = pyin_track(y, sr, fmin, fmax)
    notes = segment_pyin(midi, times, rms, min_dur=min_dur, max_gap=max_gap,
                         fold_low=fold_low, fold_high=fold_high)
    if max_dur is not None:
        for x in notes:
            if x["dur"] > max_dur:
                x["dur"] = max_dur
    return notes


# ---------------------------------------------------------------------------
# DRUMS — onset classification by band energy
# ---------------------------------------------------------------------------

def transcribe_drums():
    """
    Use onsets from the analysis json (fps=20) and classify each into
    kick / snare / hihat using band energy + spectral centroid measured on
    a short window of the drums stem around each onset.
    """
    import librosa
    ana = load_analysis()
    fps = ana["fps"]
    onsets = ana["stems"]["drums"]["onsets"]

    y, sr = librosa.load(stem_path("drums"), sr=SR, mono=True)
    win = int(0.04 * sr)  # 40 ms analysis window

    # precompute band edges (Hz)
    def band_energy(seg):
        S = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        freqs = np.fft.rfftfreq(len(seg), 1.0 / sr)
        low = S[(freqs >= 20) & (freqs < 150)].sum()      # kick body
        mid = S[(freqs >= 150) & (freqs < 2000)].sum()    # snare body
        high = S[(freqs >= 5000)].sum()                   # cymbal/hat
        total = S.sum() + 1e-9
        centroid = (freqs * S).sum() / total
        return low, mid, high, centroid, total

    notes = []
    strengths = [o["strength"] for o in onsets] or [1.0]
    smax = max(strengths)

    for o in onsets:
        tick = o["tick"]
        t = tick / fps
        i0 = int(t * sr)
        seg = y[i0:i0 + win]
        if len(seg) < 16:
            continue
        low, mid, high, centroid, total = band_energy(seg)
        lf, mf, hf = low / total, mid / total, high / total

        # classification:
        #  - lots of low energy and low centroid  -> kick
        #  - high-frequency dominant / bright       -> hihat
        #  - otherwise (mid + broadband/noisy)      -> snare
        if hf > 0.30 or centroid > 4500:
            drum = GM_HIHAT
        elif lf > 0.45 and centroid < 1200:
            drum = GM_KICK
        else:
            drum = GM_SNARE

        vel = float(np.clip(0.3 + 0.7 * (o["strength"] / smax), 0.0, 1.0))
        notes.append({
            "t": round(float(t), 4),
            "midi": int(drum),
            "vel": round(vel, 4),
            "dur": 0.15,
        })
    return notes


# ---------------------------------------------------------------------------
# BASS — reuse analysis pitch_midi (pyin) + onsets, octave-fold to bass range
# ---------------------------------------------------------------------------

def transcribe_bass():
    """
    Reuse the per-frame pitch_midi (librosa pyin) already in the analysis json
    plus its rms, and segment into discrete notes. Octave-fold anything above
    a bass ceiling so pyin octave doublings don't fly off to MIDI 80+.
    """
    ana = load_analysis()
    fps = ana["fps"]
    st = ana["stems"]["bass"]
    pm = st["pitch_midi"]
    rms = st["rms"]
    n = min(len(pm), len(rms))

    midi = np.array([m if (m is not None and m > 0) else np.nan for m in pm[:n]], dtype=float)
    rmsa = np.array(rms[:n], dtype=float)
    times = np.arange(n) / fps

    # Bass realistic window: ~E1 (28) .. ~C4 (60). Fold outliers inside.
    notes = segment_pyin(
        midi, times, rmsa,
        min_dur=0.10, max_gap=0.08,
        fold_low=28, fold_high=55,
    )
    # bass notes shouldn't be absurdly long; clamp to 2s
    for x in notes:
        if x["dur"] > 2.0:
            x["dur"] = 2.0
    return notes


# ---------------------------------------------------------------------------
# basic-pitch (polyphonic) via subprocess into venv-bp
# ---------------------------------------------------------------------------

BP_RUNNER = r'''
import sys, json, os
wav = sys.argv[1]
out = sys.argv[2]
try:
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH
    model_output, midi_data, note_events = predict(wav)
    # note_events: list of (start_s, end_s, pitch_midi, amplitude(0..1), [bends])
    notes = []
    for ev in note_events:
        start, end, pitch, amp = ev[0], ev[1], ev[2], ev[3]
        notes.append({
            "t": round(float(start), 4),
            "midi": int(pitch),
            "vel": round(float(max(0.0, min(1.0, amp))), 4),
            "dur": round(float(max(0.02, end - start)), 4),
        })
    json.dump({"ok": True, "notes": notes}, open(out, "w"))
except Exception as e:
    import traceback
    json.dump({"ok": False, "error": repr(e), "tb": traceback.format_exc()}, open(out, "w"))
'''


def basic_pitch_available():
    if not os.path.exists(BP_PYTHON):
        return False
    try:
        r = subprocess.run(
            [BP_PYTHON, "-c", "import basic_pitch; print('ok')"],
            capture_output=True, text=True, timeout=120,
        )
        return r.returncode == 0 and "ok" in r.stdout
    except Exception:
        return False


def run_basic_pitch(wav):
    """Run basic-pitch in venv-bp on a wav; return (notes, error_or_None)."""
    with tempfile.TemporaryDirectory() as td:
        runner = os.path.join(td, "bp_runner.py")
        outj = os.path.join(td, "out.json")
        with open(runner, "w", encoding="utf-8") as fh:
            fh.write(BP_RUNNER)
        try:
            subprocess.run(
                [BP_PYTHON, runner, wav, outj],
                capture_output=True, text=True, timeout=600,
            )
        except subprocess.TimeoutExpired:
            return None, "basic-pitch timed out"
        if not os.path.exists(outj):
            return None, "basic-pitch produced no output"
        res = json.load(open(outj))
        if res.get("ok"):
            return res["notes"], None
        return None, res.get("error", "unknown basic-pitch error")


def transcribe_poly_or_mono(name, stem, fmin, fmax, bp_ok):
    """piano / lead: basic-pitch polyphonic if available, else pyin mono."""
    if bp_ok:
        notes, err = run_basic_pitch(stem_path(stem))
        if notes is not None and len(notes) > 0:
            return notes, "basic-pitch (polyphonic)"
        print(f"  ! basic-pitch failed for {name}: {err}; falling back to pyin", file=sys.stderr)
    notes = transcribe_pyin_mono(stem, fmin, fmax, min_dur=0.08, max_gap=0.07)
    return notes, "pyin (monophonic fallback)"


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    summaries = []

    bp_ok = basic_pitch_available()
    print(f"basic-pitch available: {bp_ok}\n")

    # ---- BASS (pyin mono, reuse analysis) ----
    bass = transcribe_bass()
    write_notes("bass", bass)
    summaries.append(summarize("bass", bass, "pyin (monophonic, analysis json)"))

    # ---- DRUMS (onset classification) ----
    drums = transcribe_drums()
    write_notes("drums", drums)
    # extra drum breakdown
    from collections import Counter
    c = Counter(d["midi"] for d in drums)
    summaries.append(summarize("drums", drums,
        f"onset band-energy (kick={c[GM_KICK]}, snare={c[GM_SNARE]}, hihat={c[GM_HIHAT]})"))

    # ---- PIANO ----
    piano, m = transcribe_poly_or_mono("piano", "piano", fmin=55.0, fmax=2000.0, bp_ok=bp_ok)
    write_notes("piano", piano)
    summaries.append(summarize("piano", piano, m))

    # ---- LEAD (guitar) ----
    lead, m = transcribe_poly_or_mono("lead", "guitar", fmin=80.0, fmax=2000.0, bp_ok=bp_ok)
    write_notes("lead", lead)
    summaries.append(summarize("lead", lead, m))

    # ---- PAD (other, optional sparse sustain) ----
    # pyin monophonic with long sustain; if it yields too few stable notes we
    # still write it but flag it.
    pad = transcribe_pyin_mono("other", fmin=65.0, fmax=1200.0,
                               min_dur=0.25, max_gap=0.12, max_dur=4.0)
    write_notes("pad", pad)
    summaries.append(summarize("pad", pad, "pyin (monophonic, long sustain)"))

    # ---- plausibility flags ----
    print("\n=== plausibility flags ===")
    flags = []
    for s in summaries:
        if s["n"] == 0:
            flags.append(f"{s['name']}: 0 notes (empty/skipped)")
            continue
        if s["n"] < 20:
            flags.append(f"{s['name']}: only {s['n']} notes (<20)")
        if s["name"] == "bass" and s.get("midi_max", 0) > 60:
            flags.append(f"bass: midi_max {s['midi_max']} > 60 (suspicious for bass)")
    if not flags:
        print("  none")
    for f in flags:
        print("  FLAG:", f)

    print("\nDone. Files written to", OUT_DIR)


if __name__ == "__main__":
    main()
