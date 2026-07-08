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
  * sounding-cell count AND the full marching-timeline cell count (occupied + the
    repeater cells that carry the rests between notes — the real footprint driver), plus
    a per-form forceload-CHUNK estimate derived from the SAME geometry the generators
    build. The estimate has no --origin (it runs BEFORE the user picks one) and MC
    chunking is origin-relative, so it predicts the STRADDLING (worst, and most common)
    origin rather than the exact chunk-aligned best case; measured accuracy is within a
    few chunks of real builds at any non-aligned origin, and it never UNDER-predicts.
    Each estimate is compared to the forceload soft cap: over-cap forms are RED-flagged
    (build hard-rejects them without --force-cap) and long songs are steered to inplace
    (its footprint barely grows).
  * a one-line VERDICT pointing at the best-fit form, or a warning if a dense
    arrangement is predicted to drop enough notes to be worth re-arranging first, or if
    the chosen form would exceed the forceload soft cap.

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
FOOTPRINT_NEAR_CAP_PCT = 70.0     # >this share of the forceload soft cap -> yellow warning

# duration rules-of-thumb where a folded/lane form starts hitting the forceload soft
# cap (empirical, tick80). Printed as a planning hint; the per-form estimate is authoritative.
DUR_HINT_SWAVE_S = 6 * 60         # swave (folded S-wave) ~<=6 min before it tops out
DUR_HINT_MULTILANE_S = 4 * 60     # multilane (straight) ~<=4 min before it tops out


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


def _timeline_cells(trig):
    """Count the FULL shared-timeline cells the marching generators emit for the
    sorted quantized trigger ticks ``trig`` — EXACT replica of the cells[] builder in
    generators/swave.py + generators/multilane.py (trigger-tick union -> repeater
    skeleton). This is the real footprint driver: the machine spans every rest between
    triggers as repeater cells, so a SPARSE long song has FAR more cells than occupied
    (trigger) cells. Returns (total_cells, rep_cells, trig_cells).

    This is why the old n_cells (occupied) footprint underestimated sparse long songs
    ~40x: it counted only the 120 sounding cells, not the ~3000 repeater cells that
    carry the silence between them.
    """
    if not trig:
        return 0, 0, 0
    offset = 1 if trig[0] == 0 else 0
    n_rep = 0
    n_trig = 0
    prev = 0
    for t0 in trig:
        t = t0 + offset
        g = t - prev
        # G ticks of gap -> ceil(G/4) repeater cells of delay <=4 (min 1), then 1 trig
        reps = (g // 4) + (1 if g % 4 else 0)
        if reps == 0:
            reps = 1
        n_rep += reps
        n_trig += 1
        prev = t
    return n_rep + n_trig, n_rep, n_trig


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
    n_cells = len(bycell)                 # OCCUPIED (sounding) cells
    peak_poly = max(bycell.values()) if bycell else 0
    # FULL marching-timeline cells (occupied + repeater-spacer cells across rests) —
    # the real footprint driver for swave/multilane (see _timeline_cells docstring).
    trig = sorted(bycell)
    timeline_cells, _rep_cells, _trig_cells = _timeline_cells(trig)
    # predicted dropped notes over each cap = sum over cells of max(0, cell_count - cap)
    drops = {}
    for form, cap in FORM_CAP.items():
        drops[form] = sum(max(0, c - cap) for c in bycell.values())

    # distinct resolved (block, note_value) palette — drives the inplace footprint
    # (inplace lays ONE note block per distinct sound, on a 16-wide grid; it does NOT
    # span the timeline, so its footprint stays tiny + roughly constant for long songs).
    palette = set()
    for n in audible:
        fam = n["family"]
        try:
            r = imap.resolve(int(n["midi"]), float(n.get("vel", 0.7)), fam)
        except (KeyError, IndexError):
            continue
        palette.add((r.block, r.note_value))
    palette_size = len(palette)

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
        "timeline_cells": timeline_cells,
        "palette_size": palette_size,
        "peak_poly": peak_poly,
        "drops": drops,
        "band_spans": band_spans,
    }


def _span_chunks_worst(n_blocks):
    """Max number of 16-wide chunks an ``n_blocks``-long span can occupy, over ALL
    origin offsets. A span of B blocks touches at least ``(B-1)//16 + 1`` chunks (when
    chunk-aligned) and AT MOST ``(B-1)//16 + 2`` (when it straddles a chunk boundary).

    midi_report has NO origin (it is a pre-build preflight — the user has not yet picked
    an --origin), and MC's ``coord >> 4`` chunking is origin-relative, so the SAME machine
    occupies 1 more chunk-row per axis at almost every origin than at the exact chunk-
    aligned one. The OLD estimate implicitly assumed origin (0,0) (``range(-1, tl)`` /
    ``i*2 >> 4``), which is the degenerate BEST case: it matched real only when the build
    happened to sit at a chunk boundary, and UNDER-predicted ~2x at every other origin
    (V1: multilane 381 predicted vs 760 built — silently within the 360 cap yet really
    over it). We predict the STRADDLING (worst, and by far most common) case so the
    estimate never under-reports the footprint the user will actually get."""
    return (n_blocks - 1) // 16 + 2


def _footprint_estimates(rep):
    """Per-form forceload-CHUNK estimates, derived from the SAME geometry the generators
    build. Returns {form: (chunks, x_blocks, z_blocks)}.

    Two footprint drivers, both origin-honest:
      * swave/multilane footprint is driven by the FULL marching timeline
        (``timeline_cells`` = occupied + repeater-spacer cells), NOT the occupied-cell
        count. A sparse long song has ~25x more timeline cells than sounding cells, so the
        old n_cells model underestimated its footprint ~40x.
      * chunk counts use ``_span_chunks_worst`` (straddling case) per axis, because the
        report has no origin and MC chunking is origin-relative: the aligned-origin count
        the old model used under-predicted ~2x at nearly every real origin.

      swave     : folded S-wave, XRUN=3 forward then step Z, ZMAX=4 amplitude, dual-track.
                  X advances 2*XRUN blocks per (2*XRUN + 2*(ZMAX-1))-cell fold period; the
                  dual-track Z band is ~21 blocks. Forceload = bbox padded ±2 (grid.bbox).
      inplace   : a palette of DISTINCT (block,note) note blocks on a PCOLS=16 x ROWGAP=3
                  grid -> tiny + roughly CONSTANT regardless of song length. This is the
                  long-song escape hatch (its footprint does not grow with the timeline).
      multilane : MAXPOLY=7 straight lanes; one +X column per timeline cell. Footprint =
                  the occupied-chunk set (the generator forceloads set((x>>4,z>>4)), NO ±2
                  pad): x-chunks over the (source + tl columns) span * z-chunks over the
                  13-block 7-lane band. Widest/longest.
    """
    import math
    tl = rep.get("timeline_cells", rep.get("n_cells", 0))

    # ── multilane: occupied-chunk set (matches the generator, NO bbox pad) ─────────
    #   columns occupy x in [OX-1 (source) .. OX+tl-1] -> tl+1 blocks wide; 7 lanes at
    #   lane_dz=2 -> z 0..12 -> 13 blocks. Worst-case straddle per axis (see _span_...).
    ml_lane_dz, ml_lanes = 2, 7
    ml_x_blocks = tl + 1                       # source column + one per timeline cell
    ml_z_blocks = (ml_lanes - 1) * ml_lane_dz + 1   # 13
    ml_chunks = max(1, _span_chunks_worst(ml_x_blocks) * _span_chunks_worst(ml_z_blocks))

    # ── swave: folded S-wave; X from the fold period, Z band ~21 blocks (dual-track) ─
    XRUN, ZMAX = 3, 4
    period = 2 * XRUN + 2 * (ZMAX - 1)        # cells per full S fold (12 by default)
    x_per_period = 2 * XRUN                    # net X advance per fold (6 by default)
    sw_x = max(XRUN, math.ceil(tl / max(1, period)) * x_per_period)
    sw_z_blocks = 21                           # observed dual-track Z span (default ZMAX=4)
    # forceload = grid.bbox() padded -2/+2 on each axis -> span grows by 4 blocks per axis.
    sw_chunks = max(1, _span_chunks_worst(sw_x + 4) * _span_chunks_worst(sw_z_blocks + 4))

    # ── inplace: distinct-palette grid, does NOT span the timeline ────────────────
    P = max(1, rep.get("palette_size", rep.get("n_cells", 1)))
    PCOLS, ROWGAP = 16, 3
    PROWS = (P + PCOLS - 1) // PCOLS
    ip_x_blocks = min(PCOLS, P)
    ip_z_blocks = (PROWS - 1) * ROWGAP + 1
    # bbox incl. the console at PBX=OX-3 (WX0 = min(OX, PBX-10)-2), matches the generator
    ip_wx0 = min(0, -3 - 10) - 2
    ip_wx1 = ip_x_blocks - 1 + 2
    ip_wz0 = min(0, -3) - 2
    ip_wz1 = ip_z_blocks - 1 + 2
    ip_chunks = max(1, ((ip_wx1 // 16) - (ip_wx0 // 16) + 1)
                    * ((ip_wz1 // 16) - (ip_wz0 // 16) + 1))

    return {
        "swave": (sw_chunks, sw_x, sw_z_blocks),
        "inplace": (ip_chunks, ip_x_blocks, ip_z_blocks),
        "multilane": (ml_chunks, ml_x_blocks, ml_z_blocks),
    }


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
    print(f"  quantized cells (U={U:.3f}s): {rep['n_cells']} sounding"
          f"  /  {rep['timeline_cells']} timeline (incl. rest/repeater cells)")
    print(f"  peak same-cell polyphony    : {rep['peak_poly']} notes in one cell")
    print("  predicted DROPPED notes over each form's per-cell cap:")
    for form in ("inplace", "swave", "multilane"):
        d = rep["drops"][form]
        p = _pct(d, rep["n_audible"])
        cap = FORM_CAP[form]
        mark = " <" if form == form_focus else "  "
        flag = "  <-- would re-arrange" if p > DROP_WARN_PCT else ""
        print(f"   {mark}{form:<10} cap {cap:<2}  drop {d} ({p:.1f}%){flag}")

    # footprint estimates vs the forceload soft cap (worst-case origin; never under-predicts)
    fps = _footprint_estimates(rep)
    cap = core.FORCELOAD_SOFT_CAP
    near = cap * FOOTPRINT_NEAR_CAP_PCT / 100.0
    print("")
    print(f"  estimated footprint per form vs forceload soft cap ({cap} chunks):")
    for form in ("swave", "inplace", "multilane"):
        ch, xb, zb = fps[form]
        mark = " <" if form == form_focus else "  "
        if ch > cap:
            flag = (f"  <-- 会被 build 硬拒 (>{cap} 软上限); 加 --force-cap 才建, "
                    f"长歌建议改 inplace")
        elif ch > near:
            flag = f"  <-- 接近上限 ({_pct(ch, cap):.0f}% of {cap})"
        else:
            flag = ""
        print(f"   {mark}{form:<10} ~{ch} chunks  (~{xb} x {zb} blocks) 估算{flag}")
    print(f"  时长经验值: swave 约 <= {DUR_HINT_SWAVE_S // 60} 分钟、"
          f"multilane 约 <= {DUR_HINT_MULTILANE_S // 60} 分钟就会触顶软上限; "
          f"更长的曲子选 inplace (占地几乎不随时长增长)。")

    # ── verdict ──
    print("")
    print("-" * 64)
    verdict = _verdict(rep, form_focus, fps)
    print(f"  VERDICT: {verdict}")
    print("-" * 64)
    print("  thresholds used: vel floor "
          f"{VEL_FLOOR}; per-cell caps inplace=12/swave=6/multilane=7; "
          f"drop>{DROP_WARN_PCT:.0f}% -> re-arrange; shift>{SHIFT_WARN_PCT:.0f}% -> pitch approximate; "
          f"footprint>{core.FORCELOAD_SOFT_CAP} chunks -> build hard-rejects (--force-cap).")
    print("  (all numbers use the SAME parse+resolve the build uses; footprint estimates "
          "predict the worst-case (straddling) origin and never under-report, but the "
          "generator owns exact geometry — a chunk-aligned origin can come out smaller.)")


def _verdict(rep, form_focus, fps=None):
    """One-line recommendation. Pick the form with the fewest predicted drops as the
    'recommended' one; warn if even that drops more than DROP_WARN_PCT of the audible
    notes (dense/chordy arrangement -> suggest a simpler MIDI). When ``fps`` (footprint
    chunk estimates) is given, also RED-flag a focus/recommended form that would blow the
    forceload soft cap and steer toward inplace (the long-song escape hatch)."""
    cap = core.FORCELOAD_SOFT_CAP
    fps = fps or _footprint_estimates(rep)

    def _ch(form):
        return fps[form][0]

    # footprint gate FIRST: a form over the soft cap is HARD-REJECTED at build unless
    # --force-cap, so warn about it before the drop-based recommendation — this is the
    # sparse-long-song failure the old n_cells estimate hid entirely.
    if form_focus and _ch(form_focus) > cap:
        alt = "inplace" if _ch("inplace") <= cap else min(
            ("inplace", "swave", "multilane"), key=_ch)
        return (f"你选的 {form_focus} 预计占地 ~{_ch(form_focus)} chunk > 软上限 {cap} — "
                f"build 会硬拒 (除非加 --force-cap)。长歌建议改 --form {alt} "
                f"(预计 ~{_ch(alt)} chunk，占地几乎不随时长增长)。")

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
    # if the DROP-recommended form itself blows the cap, redirect to inplace.
    cap_note = ""
    if _ch(best) > cap and _ch("inplace") <= cap:
        cap_note = (f" 但 {best} 预计占地 ~{_ch(best)} chunk > 软上限 {cap}，"
                    f"长歌请改 --form inplace (~{_ch('inplace')} chunk)。")

    if best_pct > DROP_WARN_PCT:
        return (f"和弦密集，最省音的 {best} 仍预计丢音 {best_pct:.1f}% "
                f"(峰值同格 {rep['peak_poly']} 音 > cap {FORM_CAP[best]}) — "
                f"建议换编曲更简单的 MIDI，或减少同时发声的声部。{focus_note}{cap_note}")
    if best_pct > 0:
        return (f"适合直接构建 (推荐 {best}，预计丢音仅 {best_pct:.1f}%)。{focus_note}{cap_note}")
    return (f"适合直接构建 (推荐 {best}，预计零丢音)。{focus_note}{cap_note}")


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
              "fam_shift", "n_cells", "timeline_cells", "palette_size",
              "peak_poly", "drops", "band_spans"):
        assert k in rep, f"missing report field {k!r}"
    # timeline_cells >= occupied cells (it adds the rest/repeater spacer cells)
    assert rep["timeline_cells"] >= rep["n_cells"], (rep["timeline_cells"], rep["n_cells"])
    # footprint estimate returns (chunks, x, z) >=1 per form, and inplace is the smallest
    fps = _footprint_estimates(rep)
    for form in FORM_CAP:
        assert form in fps and len(fps[form]) == 3 and fps[form][0] >= 1, fps
    assert fps["inplace"][0] <= fps["swave"][0], fps  # inplace never larger than swave
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
