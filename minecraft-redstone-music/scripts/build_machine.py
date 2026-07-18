# -*- coding: utf-8 -*-
"""build_machine.py — single orchestration entry for the RedPiano (Family A) skill.

Implements CONTRACT.md §4. This is the ONE CLI a user runs to turn a MIDI file
into an in-world RedPiano machine datapack. It owns NO geometry and NO plumbing of
its own — it wires together the proven pieces:

    parse MIDI (mido, program-tracking)            -> tagged notes
    assign per-note family (GM program // 8, ch9)   -> NOTE['family']
    InstrumentMap.load(redpiano_map_multi.json)     -> 103-block resolver
    get_version_profile(--mc-version)               -> dp_format / folder names
    load_params(--params, --form)                   -> validated designer dict
    generators[<form>].build(...)                   -> datapack in build/<ns>/
    (opt-in) Datapack.deploy via --world-dir

All real work lives in ``redpiano_core`` (plumbing), ``params_schema`` (validation),
and ``generators/<form>.py`` (geometry). This file MUST NOT duplicate any of it.

Pipeline order is exactly CONTRACT §4:
  1. profile = get_version_profile(mc_version)   (fail fast on unknown version)
  2. params  = load_params(params_or_{}, form)   (fail fast cross-form / slice / custom)
  3. assert_supported(params, form)              (fail fast on unimplemented designer)
  4. parse MIDI -> tagged notes (program-tracking reader)
  5. imap = InstrumentMap.load(...)              (asserts 103 blocks)
  6. dispatch generators[form].build(notes, params, imap, profile, ns, origin, out, world)
  7. print stats + in-game next-steps

Expected failures (missing mido, bad MIDI, unknown version, unsupported param,
oversize forceload) print a clean one-line error and exit non-zero — never a raw
traceback. Deploy is opt-in: with no --world-dir the datapack stays in build/<ns>/.

NOTE schema (the SHARED INTERFACE contract between this file and the generators):
    {'t': float start-seconds, 'dur': float seconds, 'midi': int, 'vel': float 0..1,
     'family': 'pno'|'bass'|'lead'|'pad'|'drum', 'drum_type': str|None}

Pure stdlib + mido (for MIDI parsing only).
"""

import argparse
import importlib
import json
import os
import sys

# Make the script importable from any cwd: its own dir holds redpiano_core,
# params_schema, and the generators/ package.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from params_schema import RedPianoError, load_params, assert_supported  # noqa: E402
import redpiano_core as core  # noqa: E402


# Asset path resolved relative to THIS file so it works from any cwd.
_ASSET_MAP = os.path.join(_HERE, "..", "assets", "redpiano_map_multi.json")

# v1 forms map to generator modules under generators/. swave/straight/custom share
# ONE module (generators.swave) — they differ only in path spine, selected by params["form"].
_GENERATOR_MODULES = {
    "inplace": "generators.inplace",
    "swave": "generators.swave",
    "straight": "generators.swave",
    "custom": "generators.swave",
    "multilane": "generators.multilane",
}


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: program-tracking MIDI reader -> tagged NOTE dicts
#   Adapted FAITHFULLY from poc/46 L63-77 (the verified program-tracking reader)
#   and poc/analyze_instruments.py (GM family routing). Family + drum_type are
#   assigned via the InstrumentMap so there is a single source of truth.
# ─────────────────────────────────────────────────────────────────────────────

def _err_str(e):
    """str(exception), with a non-empty fallback. Some mido/mido-dependency errors
    (e.g. a truncated struct.error) stringify to '' — an empty error message reads
    as a broken script rather than a bad input file."""
    s = str(e)
    return s if s else f"{type(e).__name__} (file may be truncated or corrupt)"


def parse_midi_notes(midi_path, imap):
    """Parse ``midi_path`` with mido into the SHARED-INTERFACE NOTE schema.

    Tracks program_change per channel (poc/46 reader). Each note is tagged with:
      t        start-seconds (mido folds tempo via the file-level iterator)
      dur      seconds (floored at 0.02s, matching poc/46 max(t-st, 0.02))
      midi     note number (int)
      vel      velocity 0..1
      family   imap.family_for(program, channel)  (ch9 -> 'drum', else GM prog//8)
      drum_type  for drums: imap.gm_drum_map.get(midi); else None

    Returns a time-sorted list of NOTE dicts. Raises RedPianoError on a missing
    mido dependency or an unreadable MIDI file (no raw traceback to the user).
    """
    try:
        import mido
    except ImportError:
        raise RedPianoError(
            "the 'mido' package is required to parse MIDI but is not installed. "
            "Install it with:  pip install mido"
        )

    if not os.path.isfile(midi_path):
        raise RedPianoError(f"MIDI file not found: {midi_path}")

    try:
        mf = mido.MidiFile(midi_path, clip=True)
    except (OSError, ValueError, EOFError, IndexError, KeyError) as e:
        raise RedPianoError(f"could not read MIDI '{midi_path}': {_err_str(e)}")

    cur_prog = {}      # channel -> current program (default 0)
    active = {}        # (channel, note) -> (start_seconds, velocity 0..127)
    t = 0.0
    notes = []
    retrigger_count = 0
    try:
        for msg in mf:  # file-level iterator yields delta seconds, tempo folded
            t += msg.time
            if msg.type == "program_change":
                cur_prog[msg.channel] = msg.program
            elif msg.type == "note_on" and msg.velocity > 0:
                key = (msg.channel, msg.note)
                if key in active:
                    # Retrigger: a note_on for a (channel, note) that is still ON
                    # (sustain-pedal/legato overlap, or a sloppy MIDI missing the
                    # note_off). Silently overwriting `active[key]` here used to
                    # DROP the first segment's audible note entirely. Instead close
                    # the old segment at the current instant, same as a real note_off,
                    # then open the new one.
                    st, vel = active.pop(key)
                    ch = msg.channel
                    prog = cur_prog.get(ch, 0)
                    family = imap.family_for(prog, ch)
                    drum_type = imap.gm_drum_map.get(msg.note) if family == "drum" else None
                    notes.append({
                        "t": round(st, 4),
                        "dur": round(max(t - st, 0.02), 4),
                        "midi": int(msg.note),
                        "vel": round(vel / 127.0, 4),
                        "family": family,
                        "drum_type": drum_type,
                    })
                    retrigger_count += 1
                active[key] = (t, msg.velocity)
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                key = (msg.channel, msg.note)
                if key in active:
                    st, vel = active.pop(key)
                    ch = msg.channel
                    prog = cur_prog.get(ch, 0)
                    family = imap.family_for(prog, ch)
                    drum_type = imap.gm_drum_map.get(msg.note) if family == "drum" else None
                    notes.append({
                        "t": round(st, 4),
                        "dur": round(max(t - st, 0.02), 4),
                        "midi": int(msg.note),
                        "vel": round(vel / 127.0, 4),
                        "family": family,
                        "drum_type": drum_type,
                    })
    except (OSError, ValueError, EOFError, IndexError, KeyError) as e:
        raise RedPianoError(f"error while decoding MIDI '{midi_path}': {_err_str(e)}")

    # Flush notes still ON at end-of-file (missing/lost note_off). Silently dropping
    # them loses real audible notes on sloppy MIDIs; instead close them at the song end
    # (dur = end - start, floored 0.02s to match the note_off path) and WARN once.
    if active:
        for (ch, note), (st, vel) in active.items():
            prog = cur_prog.get(ch, 0)
            family = imap.family_for(prog, ch)
            drum_type = imap.gm_drum_map.get(note) if family == "drum" else None
            notes.append({
                "t": round(st, 4),
                "dur": round(max(t - st, 0.02), 4),
                "midi": int(note),
                "vel": round(vel / 127.0, 4),
                "family": family,
                "drum_type": drum_type,
            })
        print(f"  WARN: {len(active)} note(s) had no note_off; closed at song end "
              f"(t={t:.2f}s). MIDI may be truncated.")

    if retrigger_count:
        print(f"  WARN: {retrigger_count} retriggered notes were split "
              f"(sustain-pedal/legato overlap)")

    if not notes:
        raise RedPianoError(
            f"no playable notes found in '{midi_path}' — is it an empty or "
            f"unsupported MIDI file?"
        )

    notes.sort(key=lambda n: (n["t"], -n["midi"]))
    return notes


# ─────────────────────────────────────────────────────────────────────────────
# Reporting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _summarize_notes(notes):
    """A small pre-build note summary (family counts, span) for the report."""
    fam_counts = {}
    for n in notes:
        fam_counts[n["family"]] = fam_counts.get(n["family"], 0) + 1
    midis = [n["midi"] for n in notes]
    dur_s = max((n["t"] + n["dur"]) for n in notes)
    return fam_counts, (min(midis), max(midis)), dur_s


def _print_report(args, notes, stats, deployed_to, profile=None):
    """Print a clean stats summary + the in-game next-steps. Mirrors the poc
    stdout summaries (palette/cells, dropped, octave-shifted, cut count + median,
    forceload chunks, song length, all WARNs)."""
    fam_counts, midi_span, dur_s = _summarize_notes(notes)
    stats = stats or {}

    print("")
    print("=" * 64)
    print(f"  RedPiano machine built — {args.name}  (form: {args.form})")
    print("=" * 64)
    print(f"  namespace      : {args.ns}")
    print(f"  mc-version     : {args.mc_version}")
    if profile is not None:
        # Make the version self-sync VISIBLE: every format/dialect below was derived
        # from the one --mc-version flag, not hardcoded.
        pf = (f"min/max {profile.dp_format}" if profile.packmeta_shape == "minmax"
              else f"pack_format {profile.dp_format}")
        print(f"  version profile: dp {pf} · rp {profile.rp_format} · "
              f"folder {profile.function_folder}/ · sign {profile.sign_dialect} · "
              f"tier {profile.tier}")
    print(f"  origin (X Z Y) : {args.origin[0]} {args.origin[1]} {args.origin[2]}")
    print("")
    print(f"  notes          : {stats.get('note_count', len(notes))}"
          f"  (input {len(notes)})")
    fam_str = ", ".join(f"{k}={v}" for k, v in sorted(fam_counts.items()))
    print(f"  families       : {fam_str}")
    print(f"  midi span      : {midi_span[0]}-{midi_span[1]}")
    print(f"  song length    : {stats.get('duration_s', dur_s):.1f}s")
    print(f"  dropped notes  : {stats.get('dropped', 0)}  (over per-cell polyphony cap)")
    print(f"  octave-shifted : {stats.get('octave_shifted', 0)}  "
          f"(notes nudged +/-12 to fit sample range)")
    print(f"  forceload      : {stats.get('forceload_chunks', '?')} chunks")

    def _print_pacing(stats):
        if "pace" not in stats:
            return
        if stats["pace"] == "uniform":
            g = stats.get("grid_rt") or 1
            mps = {1: 80, 2: 40, 3: 27, 4: 20}.get(g, "?")
            fit = stats.get("grid_fit") or {}
            sfx = ""
            if fit.get("auto"):
                sfx = (f"; grid=auto -> {g} ({fit.get('on_grid', 0) * 100:.0f}% "
                       f"on-grid, {fit.get('merges', 0)} merges, max shift "
                       f"{fit.get('max_shift_rt', 0)} rt)")
            print(f"  pacing         : uniform 匀速跑道 (grid {g} rt/slot, "
                  f"{stats.get('pad_cells', 0)} rest cells, front ~{mps} m/s @tick80{sfx})")
        else:
            print(f"  pacing         : compressed (legacy variable-speed packing)")

    # form-specific lines
    if args.form == "inplace":
        if "palette_size" in stats:
            print(f"  palette        : {stats['palette_size']} distinct note blocks")
        if "fire_ticks" in stats:
            print(f"  fire ticks     : {stats['fire_ticks']}")
    elif args.form in ("swave", "straight", "custom"):
        _print_pacing(stats)
        if "cells" in stats:
            print(f"  cells          : {stats['cells']}")
        if "turns" in stats:
            print(f"  path turns     : {stats['turns']}")
        if "x_span" in stats:
            print(f"  x span         : {stats['x_span']} blocks")
    elif args.form == "multilane":
        _print_pacing(stats)
        if "cells" in stats:
            print(f"  cells          : {stats['cells']}")
        if "lanes" in stats:
            print(f"  lanes          : {stats['lanes']} (+{stats.get('signal_tracks', 0)} signal)")
        if "lane_counts" in stats:
            print(f"  lane note dist : {stats['lane_counts']}")

    # melody-cut metrics, if the generator surfaced them. The two generators name
    # the median field differently (inplace: cut_median_gt, swave: median_cut_gt);
    # accept either so the median prints for both forms.
    median_gt = stats.get("median_cut_gt", stats.get("cut_median_gt", "?"))
    cut_n = stats.get("cut_count", stats.get("mel_cut_cells", "?"))
    if cut_n != "?" or median_gt != "?":
        print(f"  melody cuts    : {cut_n}  "
              f"(median delay {median_gt} game-ticks)")

    # WARNs collected by the generator (octave-shift / event-level cut overlap)
    warnings = stats.get("warnings") or []
    if warnings:
        print("")
        print(f"  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"    ! {w}")

    print("")
    print("-" * 64)
    if deployed_to:
        nfun = (stats or {}).get("_deploy_verified")
        print(f"  ✓ datapack copied to world: {deployed_to}")
        if nfun:
            print(f"    ({nfun} functions + pack.mcmeta confirmed on disk)")
        print("  ⚠ NOTE: 'confirmed on disk' only proves the bytes are where THIS process can")
        print("    see them. Inside a Trae/sandbox runtime a C:\\Minecraft write is redirected to")
        print("    the VMCache mirror and the real game never sees it. For a sandbox-safe install")
        print("    use  scripts/prepare_all.py  (it emits a native DEPLOY_TO_GAME.bat + receipt).")
        print("  In-game steps (the song needs ALL of these, in order):")
        print("    1. /reload")
        print("    2. /tick rate 80                  ⚠ TYPE THIS MANUALLY — the machine does NOT set it")
        print("                                       (samples tuned for tick80; ~4x too slow without it)")
        print(f"    3. /function {args.ns}:setup       (builds the machine in the world)")
        print("    4. enable the qzpno_mv resourcepack in Options -> Resource Packs (or = total silence)")
        print("    5. press the [play] sign/button to perform the song")
    elif getattr(args, "staged_run", False):
        out_path = os.path.join(args.out, args.ns)
        print(f"  staged build (prepare_all manages install) — datapack at: {out_path}")
    else:
        out_path = os.path.join(args.out, args.ns)
        print("  ⛔ NOT INSTALLED IN ANY WORLD — this was a BUILD-ONLY run (no --world-dir).")
        print(f"     The datapack exists ONLY at: {out_path}")
        print(f"     >>> /function {args.ns}:setup will be \"Unknown function\" in-game until you")
        print( "         deploy it. DO NOT report success or tell the user to run it yet. <<<")
        print("     Install it ONE of these ways:")
        print(f"       - re-run with  --world-dir <profile>/saves/<world>/datapacks   (auto-verified), or")
        print("       - use  scripts/prepare_all.py  (deploys datapack + resourcepack + mod), or")
        print(f"       - copy  {out_path}  into <world>/datapacks/ yourself, then /reload")
    print("")
    print("  RUNTIME ASSETS the song also needs (datapack alone is silent):")
    print("    - qzpno_mv.zip in the profile resourcepacks/ folder AND enabled in Options -> Resource Packs.")
    print("    - RedPiano mod + matching Fabric API in mods/, then Minecraft restarted.")
    print("    - For an end-to-end run, use scripts/prepare_all.py (default automation).")
    # Version-specific reminder: every green-band version has a bundled jar, and the
    # bundled resourcepack is repacked automatically; agents should still use the resolver.
    if profile is not None and profile.mc_version != "1.21.8":
        v = profile.mc_version
        print("-" * 64)
        print(f"  ℹ MC {v} needs its matching RedPiano jar and resourcepack format {profile.rp_format}.")
        print(f"    Run fetch_binaries.py --mc-version {v} for the bundled jar, then prepare_all.py.")
        print(f"    prepare_all automatically selects assets/qzpno_mv.zip and repacks it for {v}.")
    print("-" * 64)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_argparser():
    p = argparse.ArgumentParser(
        prog="build_machine.py",
        description="Build a RedPiano (Family A) redstone music machine datapack "
                    "from a MIDI file. Default = write to build/<ns>/ only; pass "
                    "--world-dir to deploy into a world.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="example:\n"
               "  python build_machine.py --midi song.mid --form inplace "
               "--ns mysong --origin 100 200 80\n"
               "  python build_machine.py --midi song.mid --form swave "
               "--ns mysong --origin 0 0 120 --world-dir ~/.minecraft/saves/World/datapacks",
    )
    p.add_argument("--midi", required=True,
                   help="source .mid file (parsed with mido, program-tracking)")
    p.add_argument("--params", default=None,
                   help="optional designer JSON (file path). Omitted = all defaults "
                        "for --form.")
    p.add_argument("--pace", default=None, choices=["uniform", "compressed"],
                   help="marching-pulse pacing (swave/straight/custom). uniform="
                        "匀速跑道: constant front speed, rests take space — the fork "
                        "default, best for filming. compressed=legacy delay-4 gap "
                        "packing: shortest machine, variable speed. Omitted = params "
                        "value or the schema default (uniform).")
    p.add_argument("--grid", default=None, choices=["auto", "1", "2", "3", "4"],
                   help="uniform pacing step in redstone-ticks per slot. auto(默认)="
                        "按节奏最适配: pick the largest of 4/3/2 that the song's "
                        "onsets already sit on (zero merges, >=95%% on-grid), else "
                        "fall back to 1 (loss-free). 1..4 = force a period "
                        "(tick80 front speed ~80/40/27/20 m/s for 1/2/3/4).")
    p.add_argument("--form", required=True,
                   choices=["inplace", "swave", "straight", "custom", "multilane"],
                   help="machine form. swave=S-wave (default product), straight=long "
                        "line, custom=waypoint route (needs --params with waypoints), "
                        "multilane=one parallel lane per voice (+X; --params optional — "
                        "soft forceload cap, over it pass --force-cap to build anyway), "
                        "inplace=palette. Must agree with params.form if both given.")
    p.add_argument("--ns", required=True,
                   help="datapack namespace (also the scoreboard objective name)")
    p.add_argument("--origin", required=True, nargs=3, type=int,
                   metavar=("X", "Z", "Y"),
                   help="注意顺序是 X Z Y，不是游戏 F3 显示的 X Y Z。world origin X Z Y "
                        "(overrides start_x/start_z/start_y in params)")
    p.add_argument("--mc-version", default="1.21.8", dest="mc_version",
                   help="target Minecraft version (drives pack_format + folder names; "
                        "default 1.21.8). Unknown version -> hard fail.")
    p.add_argument("--name", default=None,
                   help="display name for the song (default: MIDI file stem)")
    p.add_argument("--melcap", type=float, default=1.2,
                   help="melody-cut sustain cap in seconds (default 1.2)")
    p.add_argument("--out", default="build",
                   help="staging output dir (default 'build'); datapack lands in <out>/<ns>/")
    p.add_argument("--world-dir", default=None, dest="world_dir",
                   help="if given, deploy the datapack into this world's datapacks dir. "
                        "Deploy is OPT-IN; omit to build only.")
    p.add_argument("--no-deploy", action="store_true",
                   help="explicit build-only (the default). Mutually exclusive with "
                        "--world-dir.")
    p.add_argument("--force-cap", action="store_true", dest="force_cap",
                   help="allow forceload auto-fold above the soft cap instead of "
                        "hard-failing on an oversize machine.")
    p.add_argument("--staged-run", action="store_true", dest="staged_run",
                   help=argparse.SUPPRESS)  # internal: set by prepare_all.py, which
    # manages install itself — suppresses the misleading "NOT INSTALLED IN ANY
    # WORLD" banner on what is actually just this pipeline's first stage.
    return p


# World height limits (Minecraft 1.18+ world). The machine itself only spans a
# few blocks above/below the placement Y (mapping block at Y-1/Y-2, note blocks
# at Y/Y+1, occasional Y+2/Y+3 signage) — use a generous margin so a legitimate
# origin near the very top/bottom is still caught before any work is wasted.
WORLD_MIN_Y = -64
WORLD_MAX_Y = 319
_ORIGIN_Y_MARGIN = 8


def _check_origin_y(origin_y):
    """Fail fast (human error, no traceback) when --origin's Y would place the
    machine outside the buildable world height range."""
    lo = origin_y - _ORIGIN_Y_MARGIN
    hi = origin_y + _ORIGIN_Y_MARGIN
    if lo < WORLD_MIN_Y or hi > WORLD_MAX_Y:
        raise RedPianoError(
            f"--origin Y={origin_y} puts the machine outside the buildable world "
            f"height range [{WORLD_MIN_Y}, {WORLD_MAX_Y}] (the machine spans roughly "
            f"Y {lo}..{hi} around the given Y). Pick an origin Y further from the "
            f"world's floor/ceiling."
        )


def _check_world_dir(world_dir):
    """Fail fast when --world-dir clearly points at the save/world folder itself
    instead of the saves/<world>/datapacks folder underneath it — the #1 in-the-wild
    mistake that makes the deploy silently land in the wrong place."""
    if not world_dir:
        return
    base = os.path.basename(os.path.normpath(world_dir))
    if base.lower() != "datapacks":
        raise RedPianoError(
            f"--world-dir '{world_dir}' 看起来指到了存档目录本身，--world-dir 必须指到 "
            f"saves/<世界>/datapacks 这一层 (got a folder named '{base}', expected "
            f"'datapacks')"
        )


def run(args):
    """The pipeline (CONTRACT §4). Raises RedPianoError on any expected failure;
    main() converts that into a clean exit. Returns nothing."""

    # --world-dir and --no-deploy are mutually exclusive.
    if args.world_dir and args.no_deploy:
        raise RedPianoError(
            "--world-dir and --no-deploy are mutually exclusive (deploy is opt-in; "
            "pass --world-dir to deploy, or neither to build only)"
        )

    # fail fast on a --world-dir that clearly isn't a saves/<world>/datapacks folder.
    _check_world_dir(args.world_dir)

    # fail fast on an --origin Y outside the buildable world height range.
    _check_origin_y(args.origin[2])

    # fail fast on an invalid --ns before any MIDI parse: it is the datapack namespace
    # AND scoreboard objective name, and it feeds os.path.join + rmtree downstream.
    core.validate_namespace(args.ns)

    # default display name = MIDI file stem
    if args.name is None:
        args.name = os.path.splitext(os.path.basename(args.midi))[0] or "untitled"

    # 1. version profile — fail fast on unknown version / below the /tick rate floor,
    #    then enforce the supported auto-build band (green 1.21..1.21.10; 'yellow'
    #    1.20.x resolves its datapack facts but the mod isn't auto-supported there).
    profile = core.get_version_profile(args.mc_version)
    core.assert_build_supported(profile)

    # 2. params — fail fast on cross-form / slice / custom.
    params = load_params(args.params if args.params is not None else {}, args.form)
    # carry the display name through (params.song is a display field)
    if not params.get("song") or params.get("song") == "untitled":
        params["song"] = args.name

    # 2b. CLI pacing overrides (匀速 fork) — every marching-pulse form, incl. multilane.
    if args.pace is not None or args.grid is not None:
        if args.form == "inplace":
            raise RedPianoError(
                "--pace/--grid apply to the marching-pulse forms "
                "(swave/straight/custom/multilane) — inplace has no pulse")
        if args.pace is not None:
            params["pace"] = args.pace
        if args.grid is not None:
            params["grid"] = args.grid if args.grid == "auto" else int(args.grid)

    # 3. unimplemented designer features — fail fast before any block is emitted.
    assert_supported(params, args.form)

    # 4. parse MIDI -> tagged notes. (load the imap first so family routing has the
    #    single source of truth; the contract orders imap at step 5, but family
    #    assignment needs it — load it here and reuse it as the step-5 resolver.)
    imap = core.InstrumentMap.load(_ASSET_MAP)  # step 5 (asserts 103 blocks)
    notes = parse_midi_notes(args.midi, imap)   # step 4 (uses imap.family_for)

    # 6. dispatch to the form's generator.
    mod_name = _GENERATOR_MODULES[args.form]
    try:
        gen = importlib.import_module(mod_name)
    except ImportError as e:
        raise RedPianoError(
            f"generator module '{mod_name}' for form '{args.form}' could not be "
            f"imported: {e}"
        )
    if not hasattr(gen, "build"):
        raise RedPianoError(
            f"generator '{mod_name}' has no build() entry point (expected "
            f"build(notes, params, imap, profile, ns, origin, out_dir, deploy_dir))"
        )

    origin = (args.origin[0], args.origin[1], args.origin[2])
    deploy_dir = args.world_dir  # None unless --world-dir given (opt-in deploy)

    # Pass --melcap and --force-cap through params so the generator (which owns the
    # melody-cut + forceload calls) can honor them without widening the build()
    # signature beyond the SHARED INTERFACE.
    params = dict(params)
    # Generators read the sustain cap as `melcap_s` (CONTRACT §1.6 / inplace L113,
    # swave L90). The CLI exposes it as --melcap; bridge the name so --melcap is
    # actually honored instead of silently defaulting to 1.2.
    params["melcap"] = args.melcap
    params["melcap_s"] = args.melcap
    params["force_cap"] = bool(args.force_cap)
    # Family A v1 is multi-instrument (103-block map, per-family melody-cut). The
    # inplace generator gates family resolution + melody-cut on params["multi"];
    # without this it silently collapses every note to piano and plans 0 cuts.
    # (swave is always multi.) Allow an explicit params override to force single.
    params.setdefault("multi", True)

    stats = gen.build(
        notes, params, imap, profile,
        ns=args.ns, origin=origin, out_dir=args.out, deploy_dir=deploy_dir,
    )
    if not isinstance(stats, dict):
        # the generator must return a stats dict per the SHARED INTERFACE; tolerate
        # a None return without crashing the report, but note it.
        stats = {} if stats is None else {"_stats": stats}

    # 6b. particle-editor coords sidecar — SINGLE SOURCE OF TRUTH for the playhead.
    #     Marching forms surface per-trigger melody-note world coords; the particle
    #     editor loads this file so it stops re-deriving (and drifting from) the geometry.
    #     Written next to the datapack in <out>/ (not deployed into the world).
    coords_path = None
    pcells = stats.get("playhead_cells")
    if pcells:
        coords_path = os.path.join(args.out, f"{args.ns}_coords.json")
        os.makedirs(args.out, exist_ok=True)
        with open(coords_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump({
                "kind": "machine_coords",
                "schema_version": 1,
                "form": args.form,
                "song": args.name,
                "origin": stats.get("playhead_origin",
                                    [args.origin[0], args.origin[2], args.origin[1]]),
                "tps": profile.tps,
                # machine-schedule OFFSET (music-ticks) the generator applied to trigger
                # timing. The particle editor passes this through so build_particles can
                # re-add it and stay tick-aligned with the melody-cut. Absent => 0.
                "offset": stats.get("playhead_offset", 0),
                "notes": pcells,
            }, f, ensure_ascii=False, indent=1)

    # 7. report. deploy happened INSIDE build() (only when deploy_dir is not None);
    #    surface the destination if the generator reported it, else synthesize it.
    deployed_to = None
    if deploy_dir is not None:
        deployed_to = stats.get("deployed_to") or os.path.join(deploy_dir, args.ns)
        # VERIFY the deploy actually landed. A silently-failed copy (wrong --world-dir,
        # permissions, etc.) must NOT be reported as success — that is the #1 in-the-wild
        # failure (agent builds, says "/function X:setup", but the pack never reached the
        # world → "unknown function" in-game). Confirm pack.mcmeta + the setup function.
        ff = profile.function_folder
        must_exist = [
            os.path.join(deployed_to, "pack.mcmeta"),
            os.path.join(deployed_to, "data", args.ns, ff, "setup.mcfunction"),
        ]
        missing = [p for p in must_exist if not os.path.isfile(p)]
        if missing:
            raise RedPianoError(
                f"DEPLOY VERIFICATION FAILED — missing under {deployed_to}: {missing}. The "
                f"datapack did NOT install; /function {args.ns}:setup would be 'unknown "
                f"function' in-game. Ensure --world-dir is exactly "
                f"<profile>/saves/<world>/datapacks (NOT the profile root or save root) and "
                f"is writable."
            )
        fdir = os.path.join(deployed_to, "data", args.ns, ff)
        stats["_deploy_verified"] = sum(
            1 for _r, _d, fs in os.walk(fdir) for f in fs if f.endswith(".mcfunction"))
    _print_report(args, notes, stats, deployed_to, profile)
    if coords_path:
        print(f"  particle coords : {coords_path}")
        print(f"    -> load into designer/particle_editor.html (导入机器坐标) for")
        print(f"       pixel-accurate particle placement on this {args.form} machine.")


def main(argv=None):
    args = build_argparser().parse_args(argv)
    try:
        run(args)
    except RedPianoError as e:
        # expected failure: clean one-line error, no traceback.
        sys.stderr.write(f"error: {e}\n")
        return 2
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    return 0


if __name__ == "__main__":
    # robust unicode stdout for Chinese song names / tellraw echoes on Windows.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
