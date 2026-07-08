# -*- coding: utf-8 -*-
"""make_demo_samples.py — self-contained OPEN-SOURCE demo sample set (numpy synthesis).

THE POINT — "先听个响" (hear a sound in 5 minutes) with ZERO licensed downloads.
This generator SYNTHESIZES every one of the 103 sound events the RedPiano mod plays
(60 piano + 9 bass + 13 lead + 16 pad + 5 drum) as short mono .ogg clips, and writes the
exact `samples_manifest_<inst>.json` + `samples_<inst>/` layout that
`build_resourcepack.py --samples-root` (and therefore `prepare_all.py --samples-root`)
consumes. No network, no ffmpeg, no librosa — just numpy + soundfile.

Why it is license-clean: every clip is our OWN numpy synthesis output (public domain /
self-owned), so the resulting resourcepack carries NO third-party redistribution burden.
It is NOT the polished Salamander piano — it is a plain synth voice meant to prove the whole
pipeline sounds, so a newcomer can build a complete `dist/` from a fresh clone and hear the
machine before deciding whether to source the nicer sampled instruments (see BINARIES.md).

The 103 sound-event IDs are the CONTRACT with the mod's RedPianoMap.java. This script reads
them straight from assets/redpiano_map_multi.json (the same single source of truth the
resolver loads), so the manifest ids ALWAYS match the map — the mod finds every `qzpno:<id>`.

Dependencies:  numpy, soundfile  (both pure wheels; libsndfile ships inside the soundfile
wheel and encodes OGG/Vorbis directly — no ffmpeg). Install:
    pip install -r requirements-demo.txt

Run (writes into scripts/../assets/demo_samples/ by default):
    python scripts/make_demo_samples.py
Then feed the folder to the build:
    python scripts/prepare_all.py ... --samples-root assets/demo_samples
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

SR = 44100

# ── note-name -> MIDI (must match poc/gen_multi_map.py note_to_midi exactly) ──────────
_PC = {"c": 0, "cs": 1, "d": 2, "ds": 3, "e": 4, "f": 5, "fs": 6,
       "g": 7, "gs": 8, "a": 9, "as": 10, "b": 11}


def _note_to_midi(tok):
    """'c1'->24, 'ds1'->27, 'a5'->81, 'c6'->84 (same convention as gen_multi_map.py)."""
    import re
    m = re.match(r"([a-g]s?)(\d+)$", tok)
    if not m:
        raise ValueError(f"cannot parse note token {tok!r}")
    return (int(m.group(2)) + 1) * 12 + _PC[m.group(1)]


# ── instrument -> sample subfolder (matches build_resourcepack.LIBS) ──────────────────
LIBS = [("pno", "piano", "samples_piano"),
        ("bass", "bass", "samples_bass"),
        ("lead", "lead", "samples_lead"),
        ("pad", "pad", "samples_pad"),
        ("drum", "drums", "samples_drums")]
# note: build_resourcepack keys its LIBS by ("piano","bass","lead","pad","drums"); the map's
# instrument keys are ("pno","bass","lead","pad","drum"). We map map-key -> manifest-key here.


def _read_sound_ids(map_path):
    """Return {map_inst_key: {sound_id: base_midi_or_None}} from redpiano_map_multi.json.

    sound ids look like 'pno_c1_p', 'bass_e1_mf', 'lead_c3_mf', 'pad_c2_mf', 'drum_kick_x'.
    For pitched instruments base_midi is parsed from the note token; drums are unpitched
    (base_midi None -> synthesized as a percussion one-shot by id keyword)."""
    with open(map_path, encoding="utf-8") as f:
        mm = json.load(f)
    out = {}
    for inst, d in mm["instruments"].items():
        ids = {}
        for _key, full in d.get("sound", {}).items():
            sid = full.split(":", 1)[1] if ":" in full else full
            toks = sid.split("_")
            if inst == "drum":
                ids[sid] = None            # e.g. drum_kick_x, drum_hihat_closed_x
            else:
                ids[sid] = _note_to_midi(toks[1])   # pno_c1_p -> 'c1' -> 24
        out[inst] = ids
    return out


# ── synthesis voices (pure numpy; short, normalized) ──────────────────────────────────
def _adsr(np, n, a_s, d_s, s_lvl, r_s):
    A, D, R = int(a_s * SR), int(d_s * SR), int(r_s * SR)
    S = max(n - A - D - R, 0)
    parts = []
    if A:
        parts.append(np.linspace(0, 1, A, endpoint=False))
    if D:
        parts.append(np.linspace(1, s_lvl, D, endpoint=False))
    parts.append(np.full(S, s_lvl))
    if R:
        parts.append(np.linspace(s_lvl, 0, R))
    env = np.concatenate(parts) if parts else np.zeros(n)
    if len(env) < n:
        env = np.concatenate([env, np.zeros(n - len(env))])
    return env[:n].astype("float32")


def _saw(np, f0, t, kmax=30):
    y = np.zeros(len(t))
    k = 1
    while k * f0 < SR / 2 and k <= kmax:
        y += ((-1) ** (k + 1)) * np.sin(2 * np.pi * k * f0 * t) / k
        k += 1
    return y


def _voice_piano(np, midi, dur=1.2):
    """Simple struck-string-ish tone: fundamental + a few decaying harmonics, percussive
    envelope. Not Salamander — a clean, recognizable pitched pluck."""
    f0 = 440.0 * 2 ** ((midi - 69) / 12.0)
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for h, amp, dk in ((1, 1.0, 3.0), (2, 0.5, 4.5), (3, 0.28, 6.0), (4, 0.14, 8.0)):
        x += amp * np.sin(2 * np.pi * f0 * h * t) * np.exp(-t * dk)
    env = _adsr(np, n, 0.003, 0.12, 0.35, dur - 0.13)
    return x * env


def _voice_bass(np, midi, dur=1.0):
    f0 = 440.0 * 2 ** ((midi - 69) / 12.0)
    n = int(dur * SR)
    t = np.arange(n) / SR
    body = 0.6 * _saw(np, f0, t, 24) + 0.6 * np.sin(2 * np.pi * f0 * t)
    env = _adsr(np, n, 0.005, 0.10, 0.5, dur - 0.11)
    return body * env


def _voice_lead(np, midi, dur=1.0):
    f0 = 440.0 * 2 ** ((midi - 69) / 12.0)
    n = int(dur * SR)
    t = np.arange(n) / SR
    vib = 1.0 + 0.004 * np.sin(2 * np.pi * 5.5 * t)
    ph = 2 * np.pi * f0 * np.cumsum(vib) / SR
    x = 0.5 * np.sign(np.sin(ph)) + 0.5 * np.sin(ph)
    env = _adsr(np, n, 0.004, 0.16, 0.4, dur - 0.16)
    return x * env


def _voice_pad(np, midi, dur=1.4):
    f0 = 440.0 * 2 ** ((midi - 69) / 12.0)
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for det in (0.997, 1.0, 1.003):
        for h, amp in ((1, 1.0), (2, 0.5), (3, 0.3), (4, 0.18)):
            x += amp * np.sin(2 * np.pi * f0 * h * det * t)
    env = _adsr(np, n, 0.30, 0.35, 0.7, 0.5)
    return x * env


def _voice_drum(np, sid, rng):
    """Percussion one-shot chosen by keyword in the id (drum_kick_x etc.)."""
    if "kick" in sid:
        dur = 0.5
        n = int(dur * SR)
        t = np.arange(n) / SR
        f = 120 * np.exp(-t * 30) + 45
        x = np.sin(2 * np.pi * np.cumsum(f) / SR)
        return x * _adsr(np, n, 0.001, 0.05, 0.0, dur - 0.051)
    if "snare" in sid:
        dur = 0.35
        n = int(dur * SR)
        t = np.arange(n) / SR
        x = 0.7 * rng.standard_normal(n) + 0.3 * np.sin(2 * np.pi * 200 * t)
        return x * _adsr(np, n, 0.001, 0.08, 0.0, dur - 0.081)
    if "hihat" in sid:
        dur = 0.16
        n = int(dur * SR)
        x = rng.standard_normal(n)
        return x * _adsr(np, n, 0.0005, 0.04, 0.0, dur - 0.041)
    if "tom" in sid:
        dur = 0.45
        n = int(dur * SR)
        t = np.arange(n) / SR
        f = 180 * np.exp(-t * 8) + 90
        x = np.sin(2 * np.pi * np.cumsum(f) / SR)
        return x * _adsr(np, n, 0.001, 0.06, 0.0, dur - 0.061)
    # crash / fallback
    dur = 1.2
    n = int(dur * SR)
    x = rng.standard_normal(n)
    return x * _adsr(np, n, 0.001, 0.2, 0.25, dur - 0.201)


def _normalize(np, a, peak_dbfs=-1.0):
    pk = float(np.max(np.abs(a))) or 1.0
    return (a * ((10 ** (peak_dbfs / 20.0)) / pk)).astype("float32")


def build(map_path, out_root, quiet=False):
    """Synthesize all 103 sounds into out_root as samples_<inst>/ + manifests. Returns stats."""
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as e:
        raise SystemExit(
            f"error: make_demo_samples needs numpy + soundfile ({e}). "
            f"Install with:  pip install -r requirements-demo.txt")
    if "OGG" not in sf.available_formats():
        raise SystemExit(
            "error: this soundfile/libsndfile build cannot encode OGG "
            f"(available: {list(sf.available_formats())}). Update soundfile: "
            "pip install -U soundfile")

    ids_by_inst = _read_sound_ids(map_path)
    rng = np.random.default_rng(7)
    os.makedirs(out_root, exist_ok=True)
    stats = {}
    total = 0

    for map_key, man_key, sub in LIBS:
        ids = ids_by_inst.get(map_key, {})
        subdir = os.path.join(out_root, sub)
        os.makedirs(subdir, exist_ok=True)
        samples = []
        for sid in sorted(ids):
            base = ids[sid]
            if map_key == "pno":
                a = _voice_piano(np, base)
            elif map_key == "bass":
                a = _voice_bass(np, base)
            elif map_key == "lead":
                a = _voice_lead(np, base)
            elif map_key == "pad":
                a = _voice_pad(np, base)
            else:
                a = _voice_drum(np, sid, rng)
            a = _normalize(np, a.astype("float32"))
            fn = sid + ".ogg"
            sf.write(os.path.join(subdir, fn), a, SR, format="OGG", subtype="VORBIS")
            rec = {"id": sid, "file": fn, "dur": round(len(a) / SR, 3)}
            if base is not None:
                rec["base_midi"] = base
            samples.append(rec)
        manifest = {
            "sr": SR,
            "source": "synthesized (numpy) — public-domain demo voices, no external samples",
            "samples": samples,
        }
        man_path = os.path.join(out_root, f"samples_manifest_{man_key}.json")
        with open(man_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        stats[man_key] = len(samples)
        total += len(samples)
        if not quiet:
            kb = sum(os.path.getsize(os.path.join(subdir, s["file"])) for s in samples) / 1024
            print(f"  {man_key:6s}: {len(samples):3d} ogg -> {subdir}  ({kb:.0f} KB)")

    if not quiet:
        print(f"  TOTAL : {total} ogg (expected 103)")
    stats["total"] = total
    stats["out_root"] = out_root
    return stats


def build_argparser():
    p = argparse.ArgumentParser(
        prog="make_demo_samples.py",
        description="Synthesize the 103 open-source demo sounds (numpy) into a "
                    "--samples-root the resourcepack builder consumes. No network/ffmpeg.")
    p.add_argument("--map", default=os.path.join(_HERE, "..", "assets",
                                                  "redpiano_map_multi.json"),
                   help="instrument map (source of the 103 sound-event ids).")
    p.add_argument("--out", default=os.path.join(_HERE, "..", "assets", "demo_samples"),
                   help="output samples-root dir (default assets/demo_samples).")
    p.add_argument("--quiet", action="store_true", help="suppress per-instrument report.")
    return p


def main(argv=None):
    args = build_argparser().parse_args(argv)
    map_path = os.path.abspath(args.map)
    out_root = os.path.abspath(args.out)
    if not os.path.isfile(map_path):
        sys.stderr.write(f"error: instrument map not found: {map_path}\n")
        return 2
    print("=== make_demo_samples — synthesizing open-source demo voices ===")
    stats = build(map_path, out_root, quiet=args.quiet)
    if stats["total"] != 103:
        sys.stderr.write(
            f"error: expected 103 sounds but produced {stats['total']} — the map "
            f"({map_path}) is out of sync with the 103-block contract.\n")
        return 1
    print(f"OK -> {out_root}")
    print("Next:  python scripts/prepare_all.py ... --samples-root "
          + os.path.relpath(out_root, os.path.join(_HERE, "..")))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if "--selftest" in sys.argv:
        # tiny self-test: ids parse to 103 and note tokens resolve, WITHOUT writing audio.
        _map = os.path.join(_HERE, "..", "assets", "redpiano_map_multi.json")
        by = _read_sound_ids(_map)
        tot = sum(len(v) for v in by.values())
        assert tot == 103, f"expected 103 ids, got {tot}: {[(k, len(v)) for k, v in by.items()]}"
        assert by["pno"]["pno_c1_p"] == 24, by["pno"].get("pno_c1_p")
        assert by["bass"]["bass_e1_mf"] == 28, by["bass"].get("bass_e1_mf")
        assert by["lead"]["lead_c6_mf"] == 84, by["lead"].get("lead_c6_mf")
        assert all(v is None for v in by["drum"].values()), by["drum"]
        print(f"selftest OK: 103 sound ids parse "
              f"({', '.join(f'{k}={len(v)}' for k, v in by.items())})")
        sys.exit(0)
    sys.exit(main())
