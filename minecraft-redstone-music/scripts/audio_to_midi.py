# -*- coding: utf-8 -*-
"""audio_to_midi.py — MP3/audio -> MIDI front-end for the RedPiano pipeline.

THE POINT — you have a *recording* (mp3/wav/flac/ogg/m4a), not a MIDI, but the whole
RedPiano machine pipeline eats MIDI. This is the EXPLICIT bridging step: transcribe the
audio to a standard type-1 .mid, which you then preflight with midi_report.py and build
with build_machine.py exactly like any other MIDI.

It is NOT wired into prepare_all.py on purpose — audio transcription is lossy and needs a
human to eyeball the result before spending a build. Run it by hand, read the honest
report it prints, and only then feed the .mid forward.

Two engines:
  * basic-pitch  (default / --engine auto): Spotify Basic Pitch, general-purpose
    polyphonic transcription. Apache-2.0. Handles any instrument, so it is the sane
    default for songs, band mixes, etc. Quality is "okay", never great.
  * piano        (--engine piano): qiuqiangkong high-resolution PIANO transcription (MIT).
    Markedly better than basic-pitch on SOLO PIANO, useless on anything else. Heavy
    (drags in torch, downloads a ~170MB checkpoint). Optional — only imported if you ask
    for it, and errors with a pip hint if it is not installed.

--engine auto NEVER silently reaches for the heavy piano engine: it always transcribes
with basic-pitch, and merely PRINTS a note about the piano engine when it detects the
piano lib installed, so the choice stays the user's.

Post-processing (both engines): drop notes shorter than --min-note-ms (transcription
noise), drop notes quieter than --velocity-floor (the same 0.04 floor the build uses),
normalize velocities to the full 1..127 range, sort by start time, and write a standard
type-1 MIDI (mido) whose absolute note times are second-accurate.

Depends on:  mido (core, already required) + basic-pitch (from requirements-audio.txt).
Compressed inputs (mp3/m4a) also need ffmpeg on PATH. See requirements-audio.txt.
"""

import argparse
import os
import sys

# Make the script importable from any cwd (mirrors the other scripts/ CLIs): its own dir
# holds params_schema (RedPianoError) alongside build_machine/redpiano_core.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from params_schema import RedPianoError  # noqa: E402


# ── constants ─────────────────────────────────────────────────────────────────────────
AUDIO_EXTS = (".mp3", ".wav", ".flac", ".ogg", ".m4a")
COMPRESSED_EXTS = (".mp3", ".m4a")     # need ffmpeg/audioread; give a decode-specific hint
DEFAULT_MIN_NOTE_MS = 60.0
DEFAULT_VEL_FLOOR = 0.04               # same audible-velocity floor the build/report use
PPQ = 480                              # ticks/beat of the written MIDI
TEMPO_US = 500_000                     # 120 BPM; combined with PPQ -> 960 ticks/sec (~1ms)
# transcribe at a floor at or below the user's --min-note-ms so genuinely short notes are
# SURFACED (and then honestly counted as filtered), never pre-swallowed by the engine.
RAW_FLOOR_MS = 30.0

PIP_HINT = "pip install -r requirements-audio.txt"
PIP_HINT_UTF8 = ("set PYTHONUTF8=1  &&  " + PIP_HINT +
                 "   (the leading `set PYTHONUTF8=1` avoids the old GBK/cp936 "
                 "'UnicodeDecodeError: gbk' pip crash on Chinese-locale Windows)")

DISCLAIMER = (
    "音频转录的 MIDI 质量必然低于原生 MIDI(和声粘连/幽灵音/时值破碎是常态),"
    "建议转完先跑 midi_report.py 预检,人声/多乐器混音效果最差,纯钢琴独奏最好"
)


# ── engine A: basic-pitch (general-purpose, default) ───────────────────────────────────
def _basic_pitch_model_path():
    """Pick which bundled Basic Pitch model to run. PREFER the ONNX model whenever
    onnxruntime is importable: it is the light, reliable runtime and sidesteps the
    heavyweight (and, on some Windows / Python-3.11 TensorFlow builds, outright broken)
    TF SavedModel loader that basic-pitch defaults to. Falls back to the package default
    only when onnxruntime is absent."""
    from basic_pitch import ICASSP_2022_MODEL_PATH
    try:
        import onnxruntime  # noqa: F401
        from basic_pitch import build_icassp_2022_model_path, FilenameSuffix
        onnx_path = build_icassp_2022_model_path(FilenameSuffix.onnx)
        if os.path.exists(onnx_path):
            return onnx_path
    except Exception:
        pass
    return ICASSP_2022_MODEL_PATH


def _events_basic_pitch(audio_path, raw_floor_ms):
    """Transcribe with Spotify Basic Pitch. Returns a list of raw note tuples
    (start_s, end_s, midi_pitch, amp_0_1). Raises RedPianoError with a pip hint if the
    package is missing, or a decode hint if the audio cannot be read."""
    try:
        from basic_pitch.inference import predict
    except ImportError:
        raise RedPianoError(
            "the 'basic-pitch' package is required for --engine basic-pitch/auto but is "
            "not installed. Install it with:  " + PIP_HINT_UTF8)

    _probe_decodable(audio_path)  # clean decode/ffmpeg hint before the engine runs
    try:
        # minimum_note_length is in ms; keep it AT/BELOW our raw floor so we, not the
        # engine, own the --min-note-ms decision (and can count what we drop honestly).
        _model_out, _midi, note_events = predict(
            audio_path,
            _basic_pitch_model_path(),
            minimum_note_length=float(raw_floor_ms),
        )
    except RedPianoError:
        raise
    except Exception as e:
        # decode failures were already probed above; anything here is an engine/runtime
        # fault (e.g. a broken model runtime). Report it honestly, do NOT mislabel it as
        # a decode error.
        raise RedPianoError(
            f"basic-pitch failed to transcribe '{audio_path}' "
            f"({type(e).__name__}: {e}). If this mentions a model/runtime load, your "
            f"basic-pitch inference runtime is broken — install onnxruntime "
            f"(pip install onnxruntime) for a clean lightweight runtime.")
    # note_events: (start_s, end_s, pitch, amplitude, [pitch_bends])
    out = []
    for ev in note_events:
        start_s, end_s, pitch, amp = ev[0], ev[1], int(ev[2]), float(ev[3])
        out.append((float(start_s), float(end_s), pitch, amp))
    return out


# ── engine B: piano_transcription_inference (piano-only, optional, heavy) ──────────────
def _events_piano(audio_path):
    """Transcribe with qiuqiangkong high-resolution PIANO transcription. Returns raw note
    tuples (start_s, end_s, midi_pitch, amp_0_1). Piano-only; heavy (torch + a ~170MB
    checkpoint downloaded on first run). Raises RedPianoError with a pip hint if missing."""
    try:
        from piano_transcription_inference import (
            PianoTranscription, sample_rate, load_audio)
    except ImportError:
        raise RedPianoError(
            "--engine piano needs the optional 'piano_transcription_inference' package, "
            "which is NOT installed by requirements-audio.txt (it is piano-only and pulls "
            "in torch + a ~170MB checkpoint). Install it with:  "
            "pip install piano_transcription_inference   "
            "(then re-run with --engine piano). For non-piano audio use --engine basic-pitch.")

    _probe_decodable(audio_path)
    try:
        audio, _ = load_audio(audio_path, sr=sample_rate, mono=True)
    except (OSError, RuntimeError, ValueError) as e:
        raise _decode_error(audio_path, e)
    try:
        transcriptor = PianoTranscription(device="cpu", checkpoint_path=None)
        # transcribe() writes a MIDI to disk if given a path; we only want the note events,
        # so hand it a throwaway path next to the input and read est_note_events back.
        tmp_mid = audio_path + ".pti_tmp.mid"
        result = transcriptor.transcribe(audio, tmp_mid)
    except Exception as e:  # torch/model failures are opaque; wrap as a clean RedPianoError
        raise RedPianoError(
            f"piano_transcription_inference failed to transcribe '{audio_path}': {e}")
    finally:
        try:
            if os.path.isfile(audio_path + ".pti_tmp.mid"):
                os.remove(audio_path + ".pti_tmp.mid")
        except OSError:
            pass
    out = []
    for ev in result.get("est_note_events", []):
        start_s = float(ev["onset_time"])
        end_s = float(ev["offset_time"])
        pitch = int(ev["midi_note"])
        amp = float(ev.get("velocity", 100)) / 127.0
        out.append((start_s, end_s, pitch, amp))
    return out


# ── decode helpers (clean ffmpeg guidance instead of a raw backend traceback) ──────────
def _probe_decodable(audio_path):
    """Decode the first second of the audio up front so an undecodable file (missing
    ffmpeg for mp3/m4a, or a corrupt/mislabeled file) surfaces as a clean single-line
    error + fix, not an opaque engine traceback. Cheap (1s) and format-agnostic."""
    try:
        import librosa  # basic-pitch's own audio backend; present once deps are installed
    except ImportError:
        return  # no probe available; let the engine try and its wrapper handle failure
    try:
        librosa.load(audio_path, sr=None, mono=True, duration=1.0)
    except Exception as e:
        raise _decode_error(audio_path, e)


def _decode_error(audio_path, e):
    """Build a RedPianoError explaining an audio-decode failure with an actionable fix."""
    ext = os.path.splitext(audio_path)[1].lower()
    if ext in COMPRESSED_EXTS:
        return RedPianoError(
            f"could not decode '{audio_path}' ({type(e).__name__}: {e}). "
            f"Decoding {ext} needs ffmpeg on PATH — install it "
            f"(winget install Gyan.FFmpeg) and reopen your shell, or convert the file to "
            f".wav first and pass that instead.")
    return RedPianoError(
        f"could not decode audio '{audio_path}' ({type(e).__name__}: {e}). "
        f"Make sure the file is a valid {'/'.join(AUDIO_EXTS)} audio file.")


# ── post-processing (shared by both engines) ───────────────────────────────────────────
def postprocess(raw_events, min_note_ms, vel_floor):
    """Filter + normalize raw (start_s, end_s, pitch, amp) tuples into final notes.

    Drops (and counts) notes shorter than ``min_note_ms`` (transcription noise) and notes
    quieter than ``vel_floor`` (would be dropped by the build's velocity floor anyway),
    then normalizes surviving amplitudes to the full 1..127 MIDI velocity range and sorts
    by start time. Returns (notes, stats) where each note is
    {"t","dur","midi","vel"} (vel 1..127) and stats has the drop breakdown."""
    min_s = float(min_note_ms) / 1000.0
    kept = []
    n_short = 0
    n_quiet = 0
    for start_s, end_s, pitch, amp in raw_events:
        dur = end_s - start_s
        if dur < min_s:
            n_short += 1
            continue
        if amp < float(vel_floor):
            n_quiet += 1
            continue
        kept.append([start_s, max(dur, 0.02), int(pitch), float(amp)])

    peak = max((k[3] for k in kept), default=0.0)
    notes = []
    for start_s, dur, pitch, amp in kept:
        # normalize to full dynamic range by the peak amplitude; floor at velocity 1.
        vel = 1 if peak <= 0 else max(1, min(127, int(round((amp / peak) * 127))))
        notes.append({"t": round(start_s, 4), "dur": round(dur, 4),
                      "midi": pitch, "vel": vel})
    notes.sort(key=lambda n: (n["t"], n["midi"]))
    stats = {
        "n_raw": len(raw_events),
        "n_kept": len(notes),
        "n_short": n_short,
        "n_quiet": n_quiet,
    }
    return notes, stats


def write_midi(notes, out_path):
    """Write ``notes`` as a standard type-1 MIDI with mido. Times are converted from
    absolute seconds to ticks at PPQ/TEMPO_US, so playback seconds match the transcription
    (the RedPiano readers fold tempo back into seconds, so this round-trips exactly)."""
    try:
        import mido
    except ImportError:
        raise RedPianoError(
            "the 'mido' package is required to write MIDI but is not installed. "
            "Install it with:  pip install mido")

    def sec2tick(sec):
        return int(round(mido.second2tick(max(0.0, sec), PPQ, TEMPO_US)))

    # flatten to (tick, is_on, pitch, vel) and order off-before-on within a tick so a
    # same-pitch retrigger at the boundary does not swallow itself.
    evs = []
    for n in notes:
        on_t = sec2tick(n["t"])
        off_t = sec2tick(n["t"] + n["dur"])
        if off_t <= on_t:
            off_t = on_t + 1
        evs.append((on_t, 1, n["midi"], n["vel"]))
        evs.append((off_t, 0, n["midi"], 0))
    evs.sort(key=lambda e: (e[0], e[1]))   # is_on=0 (off) sorts before is_on=1 (on)

    mid = mido.MidiFile(type=1, ticks_per_beat=PPQ)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="audio_to_midi", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=TEMPO_US, time=0))
    track.append(mido.Message("program_change", program=0, channel=0, time=0))
    prev = 0
    for tick, is_on, pitch, vel in evs:
        delta = tick - prev
        prev = tick
        if is_on:
            track.append(mido.Message("note_on", note=pitch, velocity=vel,
                                      channel=0, time=delta))
        else:
            track.append(mido.Message("note_off", note=pitch, velocity=0,
                                      channel=0, time=delta))
    track.append(mido.MetaMessage("end_of_track", time=0))

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    mid.save(out_path)


# ── report ─────────────────────────────────────────────────────────────────────────────
def print_report(audio_path, out_path, engine, notes, stats):
    """Honest transcription report: what came out, what got filtered, the quality caveat,
    and the exact next commands (midi_report preflight + a build)."""
    print("=" * 66)
    print(f"  audio -> MIDI  ({engine})")
    print("=" * 66)
    print(f"  in           : {audio_path}")
    print(f"  out          : {out_path}")
    if notes:
        dur_s = max(n["t"] + n["dur"] for n in notes)
        lo = min(n["midi"] for n in notes)
        hi = max(n["midi"] for n in notes)
        print(f"  notes out    : {stats['n_kept']}")
        print(f"  pitch span   : MIDI {lo}-{hi}  ({hi - lo} semitones)")
        print(f"  length       : {dur_s:.1f}s")
    else:
        print("  notes out    : 0  (nothing survived transcription+filtering)")
    print(f"  filtered     : {stats['n_short']} short (<{DEFAULT_MIN_NOTE_MS_LABEL}ms) "
          f"+ {stats['n_quiet']} quiet (<vel floor) noise notes "
          f"= {stats['n_short'] + stats['n_quiet']} of {stats['n_raw']} raw")
    print("")
    print("  免责: " + DISCLAIMER)
    print("")
    print("-" * 66)
    print("  下一步 (next):")
    rel = _rel_to_root(out_path)
    print(f"    python scripts/midi_report.py --midi {rel} --form swave")
    print(f"    python scripts/build_machine.py --midi {rel} --form swave "
          f"--ns mysong --origin 0 0 -60")
    print("-" * 66)


# label used inside print_report so the min-note-ms in the message tracks the actual arg
DEFAULT_MIN_NOTE_MS_LABEL = str(int(DEFAULT_MIN_NOTE_MS))


def _rel_to_root(path):
    """Path relative to the repo root (scripts/..), for copy-pasteable next-step commands."""
    root = os.path.dirname(_HERE)
    try:
        return os.path.relpath(os.path.abspath(path), root).replace("\\", "/")
    except ValueError:
        return path


# ── auto-engine note ───────────────────────────────────────────────────────────────────
def _piano_installed():
    import importlib.util
    return importlib.util.find_spec("piano_transcription_inference") is not None


def _resolve_engine(engine):
    """Resolve --engine auto to a concrete engine. auto ALWAYS returns basic-pitch, but
    prints a note about the piano engine when the piano lib is installed and the audio may
    be solo piano — so auto never silently picks the heavy engine."""
    if engine != "auto":
        return engine
    if _piano_installed():
        print("note: --engine auto uses basic-pitch (general-purpose). You also have "
              "piano_transcription_inference installed — for a SOLO-PIANO recording, "
              "--engine piano is markedly more accurate (but piano-only, and slower). "
              "Sticking with basic-pitch; pass --engine piano to switch.", file=sys.stderr)
    return "basic-pitch"


# ── CLI plumbing ───────────────────────────────────────────────────────────────────────
def build_argparser():
    p = argparse.ArgumentParser(
        prog="audio_to_midi.py",
        description="Transcribe an audio recording (mp3/wav/flac/ogg/m4a) to a standard "
                    "type-1 MIDI for the RedPiano pipeline. Explicit front-end step; "
                    "NOT part of prepare_all. Read the honest report, then feed the .mid "
                    "to midi_report.py + build_machine.py.")
    p.add_argument("--audio", required=True,
                   help="input audio file (%s)" % "/".join(AUDIO_EXTS))
    p.add_argument("--out", default=None,
                   help="output .mid path (default: the audio path with a .mid extension)")
    p.add_argument("--engine", default="auto",
                   choices=["auto", "basic-pitch", "piano"],
                   help="auto (default): always transcribe with basic-pitch, but note the "
                        "piano engine if it is installed; basic-pitch: general-purpose; "
                        "piano: piano-only, optional/heavy (torch + ~170MB checkpoint).")
    p.add_argument("--min-note-ms", type=float, default=DEFAULT_MIN_NOTE_MS,
                   dest="min_note_ms",
                   help="drop transcribed notes shorter than this many ms as noise "
                        "(default %g)" % DEFAULT_MIN_NOTE_MS)
    p.add_argument("--velocity-floor", type=float, default=DEFAULT_VEL_FLOOR,
                   dest="velocity_floor",
                   help="drop transcribed notes quieter than this 0..1 amplitude "
                        "(matches the build's velocity floor, default %g)" % DEFAULT_VEL_FLOOR)
    return p


def run(args):
    global DEFAULT_MIN_NOTE_MS_LABEL
    DEFAULT_MIN_NOTE_MS_LABEL = ("%g" % args.min_note_ms)

    if not os.path.isfile(args.audio):
        raise RedPianoError(f"audio file not found: {args.audio}")
    ext = os.path.splitext(args.audio)[1].lower()
    if ext not in AUDIO_EXTS:
        raise RedPianoError(
            f"unsupported audio extension '{ext}'. Supported: {'/'.join(AUDIO_EXTS)}.")

    out_path = args.out or (os.path.splitext(args.audio)[0] + ".mid")
    if os.path.abspath(out_path) == os.path.abspath(args.audio):
        raise RedPianoError("--out would overwrite the input audio; choose a .mid path")

    engine = _resolve_engine(args.engine)
    # transcribe at a floor no higher than the user's min-note-ms so short notes are
    # surfaced and honestly counted as filtered rather than pre-swallowed by the engine.
    raw_floor = min(float(args.min_note_ms), RAW_FLOOR_MS)
    if engine == "piano":
        raw = _events_piano(args.audio)
    else:
        raw = _events_basic_pitch(args.audio, raw_floor)

    if not raw:
        raise RedPianoError(
            f"the {engine} engine transcribed ZERO notes from '{args.audio}'. "
            f"Is it (near-)silent, or the wrong file? Try a cleaner recording.")

    notes, stats = postprocess(raw, args.min_note_ms, args.velocity_floor)
    if not notes:
        raise RedPianoError(
            f"all {stats['n_raw']} transcribed notes were filtered out "
            f"({stats['n_short']} too short, {stats['n_quiet']} too quiet). "
            f"Lower --min-note-ms / --velocity-floor, or use a cleaner recording.")

    write_midi(notes, out_path)
    print_report(args.audio, out_path, engine, notes, stats)


def main(argv=None):
    args = build_argparser().parse_args(argv)
    try:
        run(args)
    except RedPianoError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    return 0


def _selftest():
    """Offline self-test: exercise postprocess + write_midi + the mido round-trip WITHOUT
    any engine (no basic-pitch/torch needed). Asserts filtering, velocity normalization,
    and that the written MIDI reads back with second-accurate note times."""
    import tempfile
    # raw events: two good notes, one too-short, one too-quiet.
    raw = [
        (0.00, 0.50, 60, 0.90),   # keep, loudest -> vel 127
        (0.50, 0.62, 64, 0.45),   # keep (120ms > 60ms floor)
        (1.00, 1.02, 67, 0.80),   # too short (20ms < 60ms) -> filtered
        (1.50, 2.00, 72, 0.01),   # too quiet (0.01 < 0.04) -> filtered
    ]
    notes, stats = postprocess(raw, DEFAULT_MIN_NOTE_MS, DEFAULT_VEL_FLOOR)
    assert stats["n_raw"] == 4 and stats["n_kept"] == 2, stats
    assert stats["n_short"] == 1 and stats["n_quiet"] == 1, stats
    assert notes[0]["midi"] == 60 and notes[0]["vel"] == 127, notes[0]
    assert 1 <= notes[1]["vel"] <= 127, notes[1]
    assert notes == sorted(notes, key=lambda n: (n["t"], n["midi"])), "not sorted"

    tmp = os.path.join(tempfile.gettempdir(), "_a2m_selftest.mid")
    write_midi(notes, tmp)
    import mido
    mf = mido.MidiFile(tmp, clip=True)
    # round-trip: recover absolute onset seconds and compare to the source within 3ms.
    t = 0.0
    onsets = {}
    for msg in mf:
        t += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            onsets.setdefault(msg.note, t)
    assert abs(onsets[60] - 0.00) < 0.003, onsets
    assert abs(onsets[64] - 0.50) < 0.003, onsets
    assert 72 not in onsets and 67 not in onsets, onsets  # filtered ones absent
    os.remove(tmp)
    print("SELFTEST OK  (postprocess + write_midi round-trip, no engine)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
