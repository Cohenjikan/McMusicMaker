# -*- coding: utf-8 -*-
"""midi_report.py — pre-build MIDI quality preflight for the RedPiano skill.

Answers ONE question before you spend a build + an in-game listen on a MIDI:
"will this arrangement come out clean, or will the machine drop/mangle notes?"
It reuses the EXACT same readers the real build uses (build_machine.parse_midi_notes
+ redpiano_core.InstrumentMap.resolve), so its verdict matches what the generators
will actually do — no second, drifting model of the pipeline.

What it reports (see the thresholds printed at the bottom of every run):
  * length, total note count, per-family distribution, tempo-event count
  * pitch span (min-max MIDI) and, per family, the share of notes that fall OUTSIDE
    that family's sample bands and so get OCTAVE-SHIFTED by imap.resolve (judged by
    the SAME resolve() the build uses, not a re-derivation)
  * after quantizing to U=0.025s cells, the peak same-cell polyphony and the share of
    notes predicted DROPPED over each form's per-cell cap (inplace 12 / swave 6 /
    multilane 7 — the real generator constants)
  * predicted cell count and a ROUGH footprint estimate per form (each formula is
    marked "估算" — it is a planning aid, the generator owns the real geometry)
  * a one-line VERDICT pointing at the best-fit form, or a warning if a dense
    arrangement is predicted to drop enough notes to be worth re-arranging first.

This tool NEVER builds or deploys anything and is read-only. It exits 0 even when it
recommends re-arranging (a report is not itself a failure); only a usage error exits 2.

Pure stdlib + mido (via build_machine.parse_midi_notes).
"""

import argparse
import os
import sys
from collections import defaultdict

# Make the script importable from any cwd: its own dir holds redpiano_core,
# build_machine, params_schema and the generators/ package.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from params_schema import RedPianoError  # noqa: E402
import redpiano_core as core  # noqa: E402
import build_machine  # noqa: E402  (reuse parse_midi_notes + _ASSET_MAP)


# ── pipeline-true constants (mirrored from the generators, single source of truth) ──
U = 2.0 / core.TPS                 # 0.025s quantization cell (all forms, poc U=2/80)
VEL_FLOOR = 0.04                   # notes below this are dropped before placement
# per-cell polyphony caps — the REAL generator constants:
#   inplace  VOICES = 12                        (generators/inplace.py L58)
#   swave    CELL_CAP = min(6, n_tracks*3) = 6  (generators/swave.py VOICES=6, dual-track)
#   multilane NLANE = max_poly = 7 default      (generators/multilane.py L66)
FORM_CAP = {"inplace": 12, "swave": 6, "multilane": 7}
CUT_INSTR = frozenset({"pad", "lead", "bass"})  # sustaining families (melody-cut set)

# report thresholds (documented in the output so the judgement is auditable)
DROP_WARN_PCT = 10.0               # >this share dropped over the cap -> recommend re-arrange
SHIFT_WARN_PCT = 25.0             # >this share octave-shifted -> note the pitch approximation


def _count_tempo_events(midi_path):
    """Count set_tempo meta messages directly (mido), across all tracks. A count > 1
    means the piece changes tempo; parse_midi_notes already folds tempo into seconds,
    so this is purely informational (many tempo changes = a rubato/expressive MIDI)."""
    try:
        import mido
    except ImportError:
        raise RedPianoError(
            "the 'mido' package is required to read MIDI but is not installed. "
            "Install it with:  pip install mido")
    try:
        mf = mido.MidiFile(midi_path, clip=True)
    except (OSError, ValueError, EOFError, IndexError, KeyError) as e:
        raise RedPianoError(f"could not read MIDI '{midi_path}': {e}")
    n = 0
    for track in mf.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                n += 1
    return n


def _band_span(inst):
    """(min_band, max_band) for a pitched instrument's sample bands, else None."""
    if not inst.get("pitched"):
        return None
    bands = inst.get("bands") or []
    if not bands:
        return None
    return (min(bands), max(bands))


def analyze(notes, imap):
    """Compute the full pipeline-true report dict from the parsed notes + the imap.
    Uses imap.resolve (the build's own resolver) to judge octave-shift, and the same
    round(t/U) quantization the generators use to judge same-cell polyphony."""
    n_total = len(notes)
    dur_s = max((n["t"] + n["dur"]) for n in notes)
    midis = [n["midi"] for n in notes]

    fam_counts = defaultdict(int)
    for n in notes:
        fam_counts[n["family"]] += 1

    # audible notes (velocity floor) — the caps + quantization apply to these.
    audible = [n for n in notes if float(n.get("vel", 1.0)) >= VEL_FLOOR]
    n_below_floor = n_total - len(audible)

    # per-family octave-shift share, judged by the REAL resolver. For drums resolve()
    # never shifts (they are unpitched), so they trivially contribute 0 shifted.
    fam_shift = defaultdict(lambda: [0, 0])   # family -> [shifted, total]
    clamp_hits = 0
    for n in audible:
        fam = n["family"]
        try:
            r = imap.resolve(int(n["midi"]), float(n.get("vel", 0.7)), fam)
        except (KeyError, IndexError):
            # a family not in the map would already fail the build; count it as un-shiftable
            fam_shift[fam][1] += 1
            continue
        fam_shift[fam][1] += 1
        if r.shifted_octaves:
            fam_shift[fam][0] += 1
            if abs(r.shifted_octaves) == core.OCTAVE_SHIFT_CLAMP_SENTINEL:
                clamp_hits += 1

    # quantize to cells; peak same-cell polyphony + predicted drops per cap.
    bycell = defaultdict(int)
    for n in audible:
        bycell[round(n["t"] / U)] += 1
    n_cells = len(bycell)
    peak_poly = max(bycell.values()) if bycell else 0
    # predicted dropped notes over each cap = sum over cells of max(0, cell_count - cap)
    drops = {}
    for form, cap in FORM_CAP.items():
        drops[form] = sum(max(0, c - cap) for c in bycell.values())

    # band-span table (for the pitch-range context) + per-family in/out-of-range
    band_spans = {}
    for fam in ("pno", "bass", "lead", "pad"):
        inst = imap.instruments.get(fam)
        if inst:
            band_spans[fam] = _band_span(inst)

    return {
        "n_total": n_total,
        "n_below_floor": n_below_floor,
        "n_audible": len(audible),
        "dur_s": dur_s,
        "midi_min": min(midis),
        "midi_max": max(midis),
        "fam_counts": dict(fam_counts),
        "fam_shift": {k: tuple(v) for k, v in fam_shift.items()},
        "clamp_hits": clamp_hits,
        "n_cells": n_cells,
        "peak_poly": peak_poly,
        "drops": drops,
        "band_spans": band_spans,
    }


def _footprint_estimates(n_cells, rep):
    """ROUGH per-form footprint estimates (each marked 估算). The generators own the
    real geometry; these are order-of-magnitude planning aids only.

      swave     : folded S-wave. cells run XRUN=3 in X then step Z (ZMAX=4 amplitude),
                  so X span ~ ceil(cells/ (2*XRUN)) * XRUN and Z span ~ ZMAX*track. 估算.
      inplace   : a palette of DISTINCT (block,note) note blocks laid on a PCOLS=16 grid
                  with ROWGAP=3 rows -> ~16 wide x ceil(distinct/16)*3 deep. Uses the
                  distinct-note-block count when known, else the cell count as a ceiling. 估算.
      multilane : MAXPOLY=7 straight lanes at lane_dz=2 -> Z ~ 7*2, X ~ cells (one +X
                  cell per trigger). This is the widest/longest -> most chunks. 估算.
    """
    import math
    # swave 估算
    XRUN, ZMAX = 3, 4
    sw_x = max(XRUN, math.ceil(n_cells / max(1, 2 * XRUN)) * XRUN)
    sw_z = ZMAX * 2 + 3           # dual-track amplitude + separation (rough)
    # inplace 估算 — palette breadth: distinct note-block estimate (fallback = cells)
    distinct = rep.get("distinct_blocks", n_cells)
    PCOLS, ROWGAP = 16, 3
    ip_x = min(PCOLS, distinct)
    ip_z = math.ceil(distinct / PCOLS) * ROWGAP
    # multilane 估算 — one +X cell per trigger, 7 lanes deep
    ml_x = n_cells
    ml_z = 7 * 2
    return {
        "swave": (sw_x, sw_z),
        "inplace": (ip_x, ip_z),
        "multilane": (ml_x, ml_z),
    }


def _chunks(x_blocks, z_blocks):
    """Rough chunk count for an X-by-Z block footprint (16 blocks/chunk each axis)."""
    return max(1, (x_blocks // 16 + 1)) * max(1, (z_blocks // 16 + 1))


def _pct(part, whole):
    return (100.0 * part / whole) if whole else 0.0


def print_report(midi_path, notes, imap, rep, tempo_events, form_focus=None):
    """Emit the human report. ``form_focus`` (optional --form) is highlighted, but all
    three forms' drop/footprint numbers are shown so the choice is informed."""
    print("=" * 64)
    print(f"  MIDI preflight — {os.path.basename(midi_path)}")
    print("=" * 64)
    print(f"  length         : {rep['dur_s']:.1f}s")
    print(f"  notes          : {rep['n_total']} total"
          + (f"  ({rep['n_below_floor']} below vel floor {VEL_FLOOR}, "
             f"{rep['n_audible']} audible)" if rep["n_below_floor"] else ""))
    fam_str = ", ".join(f"{k}={v}" for k, v in sorted(rep["fam_counts"].items()))
    print(f"  families       : {fam_str}")
    print(f"  tempo events   : {tempo_events}"
          + ("  (constant tempo)" if tempo_events <= 1 else "  (tempo changes — expressive/rubato)"))
    print(f"  pitch span     : MIDI {rep['midi_min']}-{rep['midi_max']}")

    # sample-band context + per-family octave-shift share (via imap.resolve)
    print("")
    print("  sample bands (pitched families) + out-of-range -> octave-shift share:")
    for fam in ("pno", "bass", "lead", "pad"):
        span = rep["band_spans"].get(fam)
        sh = rep["fam_shift"].get(fam)
        if span is None:
            continue
        if sh and sh[1]:
            shp = _pct(sh[0], sh[1])
            flag = "  <-- high" if shp > SHIFT_WARN_PCT else ""
            print(f"    {fam:<5} bands MIDI {span[0]}-{span[1]}   "
                  f"shifted {sh[0]}/{sh[1]} ({shp:.0f}%){flag}")
        else:
            print(f"    {fam:<5} bands MIDI {span[0]}-{span[1]}   (no notes)")
    drum_n = rep["fam_counts"].get("drum", 0)
    if drum_n:
        print(f"    drum  unpitched (GM->drum-type map), never octave-shifted  ({drum_n} notes)")
    if rep["clamp_hits"]:
        print(f"    ! {rep['clamp_hits']} note(s) could not fit even after octave-shifting "
              f"-> clamped (pitch approximate)")

    # quantization + polyphony / predicted drops
    print("")
    print(f"  quantized cells (U={U:.3f}s): {rep['n_cells']}")
    print(f"  peak same-cell polyphony    : {rep['peak_poly']} notes in one cell")
    print("  predicted DROPPED notes over each form's per-cell cap:")
    for form in ("inplace", "swave", "multilane"):
        d = rep["drops"][form]
        p = _pct(d, rep["n_audible"])
        cap = FORM_CAP[form]
        mark = " <" if form == form_focus else "  "
        flag = "  <-- would re-arrange" if p > DROP_WARN_PCT else ""
        print(f"   {mark}{form:<10} cap {cap:<2}  drop {d} ({p:.1f}%){flag}")

    # footprint estimates (all 估算)
    fps = _footprint_estimates(rep["n_cells"], rep)
    print("")
    print("  rough footprint per form (估算 — generator owns real geometry):")
    for form in ("swave", "inplace", "multilane"):
        xb, zb = fps[form]
        ch = _chunks(xb, zb)
        mark = " <" if form == form_focus else "  "
        print(f"   {mark}{form:<10} ~{xb} x {zb} blocks  (~{ch} chunks) 估算")

    # ── verdict ──
    print("")
    print("-" * 64)
    verdict = _verdict(rep, form_focus)
    print(f"  VERDICT: {verdict}")
    print("-" * 64)
    print("  thresholds used: vel floor "
          f"{VEL_FLOOR}; per-cell caps inplace=12/swave=6/multilane=7; "
          f"drop>{DROP_WARN_PCT:.0f}% -> re-arrange; shift>{SHIFT_WARN_PCT:.0f}% -> pitch approximate.")
    print("  (all numbers use the SAME parse+resolve the build uses; footprints are 估算.)")


def _verdict(rep, form_focus):
    """One-line recommendation. Pick the form with the fewest predicted drops as the
    'recommended' one; warn if even that drops more than DROP_WARN_PCT of the audible
    notes (dense/chordy arrangement -> suggest a simpler MIDI)."""
    # rank forms by predicted drop share (lower = better), tie-break inplace<swave<multilane
    order = ["inplace", "swave", "multilane"]
    best = min(order, key=lambda f: (rep["drops"][f], order.index(f)))
    best_pct = _pct(rep["drops"][best], rep["n_audible"])
    focus_note = ""
    # only nudge toward a different form when it ACTUALLY drops fewer notes; when the
    # focus form ties the best (both 0%), the choice is footprint/aesthetics, not drops.
    if form_focus and form_focus != best and rep["drops"][form_focus] > rep["drops"][best]:
        fp = _pct(rep["drops"][form_focus], rep["n_audible"])
        focus_note = (f" (你选的 {form_focus} 预计丢音 {fp:.1f}%; "
                      f"{best} 更省音)")
    if best_pct > DROP_WARN_PCT:
        return (f"和弦密集，最省音的 {best} 仍预计丢音 {best_pct:.1f}% "
                f"(峰值同格 {rep['peak_poly']} 音 > cap {FORM_CAP[best]}) — "
                f"建议换编曲更简单的 MIDI，或减少同时发声的声部。{focus_note}")
    if best_pct > 0:
        return (f"适合直接构建 (推荐 {best}，预计丢音仅 {best_pct:.1f}%)。{focus_note}")
    return (f"适合直接构建 (推荐 {best}，预计零丢音)。{focus_note}")


def build_argparser():
    p = argparse.ArgumentParser(
        prog="midi_report.py",
        description="Pre-build MIDI quality preflight for the RedPiano skill: predicts "
                    "octave-shift, per-cell polyphony drops, cell count and rough "
                    "footprint per form, using the build's own parse+resolve. Read-only.")
    p.add_argument("--midi", required=True, help="source .mid file to preflight")
    p.add_argument("--form", default=None,
                   choices=["swave", "inplace", "multilane"],
                   help="optional form to highlight in the report (all three are shown).")
    return p


def run(args):
    imap = core.InstrumentMap.load(build_machine._ASSET_MAP)
    notes = build_machine.parse_midi_notes(args.midi, imap)
    tempo_events = _count_tempo_events(args.midi)
    rep = analyze(notes, imap)
    print_report(args.midi, notes, imap, rep, tempo_events, form_focus=args.form)


def main(argv=None):
    args = build_argparser().parse_args(argv)
    try:
        run(args)
    except RedPianoError as e:
        # expected failure (missing mido, bad/empty MIDI): clean one-line error.
        sys.stderr.write(f"error: {e}\n")
        return 2
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    return 0


def _selftest():
    """Run the report over assets/demo.mid and assert the key fields exist + are sane.
    Uses the real parse+resolve (no mocks); prints SELFTEST OK on success."""
    demo = os.path.join(_HERE, "..", "assets", "demo.mid")
    assert os.path.isfile(demo), f"demo.mid not found at {demo}"
    imap = core.InstrumentMap.load(build_machine._ASSET_MAP)
    notes = build_machine.parse_midi_notes(demo, imap)
    assert notes, "demo.mid parsed to zero notes"
    tempo_events = _count_tempo_events(demo)
    assert tempo_events >= 1, f"expected >=1 tempo event, got {tempo_events}"
    rep = analyze(notes, imap)
    # key fields present
    for k in ("n_total", "dur_s", "midi_min", "midi_max", "fam_counts",
              "fam_shift", "n_cells", "peak_poly", "drops", "band_spans"):
        assert k in rep, f"missing report field {k!r}"
    assert rep["n_total"] == len(notes)
    assert rep["dur_s"] > 0
    assert rep["midi_min"] <= rep["midi_max"]
    assert set(rep["drops"]) == set(FORM_CAP), rep["drops"]
    assert rep["peak_poly"] >= 1
    # drops are monotonic in cap: a larger cap can never drop MORE.
    assert rep["drops"]["inplace"] <= rep["drops"]["multilane"] <= rep["drops"]["swave"], \
        rep["drops"]
    # verdict is a non-empty string that names a form
    v = _verdict(rep, None)
    assert isinstance(v, str) and v and any(f in v for f in FORM_CAP), v
    # the full report prints without raising
    print_report(demo, notes, imap, rep, tempo_events, form_focus="swave")
    print("SELFTEST OK")
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
