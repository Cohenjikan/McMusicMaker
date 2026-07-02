# -*- coding: utf-8 -*-
"""build_resourcepack.py — version-driven qzpno_mv resourcepack repack (in-skill).

Ports poc/02e_build_resourcepack.py INTO the skill and makes it version-adaptive: the
resourcepack `pack_format` and the pack.mcmeta SHAPE are read from the single source of
truth (redpiano_core.get_version_profile), exactly like the datapack — so one
`--mc-version` flag self-syncs the resourcepack to match the datapack/mod.

What it does (Family A audio for the RedPiano mod):
  * gathers the 5 instrument sample libraries (piano/bass/lead/pad/drums) — each a
    folder of .ogg files + a `samples_manifest_<inst>.json` listing {file, id};
  * copies the .ogg into  <pack>/assets/qzpno/sounds/<file>;
  * writes  assets/qzpno/sounds.json  (one `master` event per id, played as
    `qzpno:<id>` by the mod);
  * writes  pack.mcmeta  with the version's resourcepack rp_format and the right
    SHAPE: single `pack_format` (<=1.21.8) or `min_format`/`max_format` (>=1.21.9);
  * zips the pack to <out>.

The samples themselves are large/licensed and DO NOT ship in this folder (see
BINARIES.md) — point `--samples-root` at the folder that holds the
`samples_manifest_*.json` + `samples_<inst>/` directories (the source repo's `poc/`).

Pure stdlib. Run e.g.:
  python scripts/build_resourcepack.py --mc-version 1.21.8 \
      --samples-root /path/to/source/poc --out build/qzpno_mv.zip
"""

import argparse
import json
import os
import shutil
import sys
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from redpiano_core import RedPianoError, get_version_profile, assert_build_supported  # noqa: E402
from runtime_guard import RuntimeGuardError, require_not_vmcache_targets  # noqa: E402

# instrument -> sample subfolder (matches poc/02e LIBS)
LIBS = [("piano", "samples_piano"), ("bass", "samples_bass"), ("lead", "samples_lead"),
        ("pad", "samples_pad"), ("drums", "samples_drums")]

PACK_DESCRIPTION = "qzpno 钢琴+乐队(piano/bass/lead/pad/drums) for RedPiano mod"


def rp_packmeta(profile, description=PACK_DESCRIPTION):
    """Build the resourcepack pack.mcmeta dict, version-driven (single source of truth).

    Mirrors the datapack pack.mcmeta SHAPE branch in redpiano_core.Datapack but with the
    RESOURCEPACK rp_format: single `pack_format` for <=1.21.8, `min_format`/`max_format`
    for >=1.21.9 (25w31a — a single pack_format is silently disabled there)."""
    if profile.packmeta_shape == "minmax":
        return {"pack": {"description": description,
                         "min_format": profile.rp_format,
                         "max_format": profile.rp_format}}
    return {"pack": {"pack_format": profile.rp_format, "description": description}}


def assemble_pack(samples_root, pack_dir, allow_partial=False):
    """Copy every manifest-listed .ogg into <pack_dir>/assets/qzpno/sounds/ and build the
    sounds.json mapping. Returns (sounds_json, counts). Raises RedPianoError if no
    samples are found at all, if ANY instrument manifest is missing (unless
    ``allow_partial``), or if a manifest references a missing .ogg.

    A missing manifest means that whole instrument silently falls back to vanilla in-game
    (bass/lead/pad/drum go mute), so by default a partial library is a HARD failure — the
    packaging chain must not report a half-built pack as OK. Pass ``allow_partial`` to
    knowingly ship a subset (the missing instruments are still printed as [warn])."""
    snd_dir = os.path.join(pack_dir, "assets", "qzpno", "sounds")
    if os.path.isdir(snd_dir):
        shutil.rmtree(snd_dir)
    os.makedirs(snd_dir)

    sounds_json, counts, missing, missing_manifests = {}, {}, [], []
    found_any_manifest = False
    for inst, sub in LIBS:
        man_path = os.path.join(samples_root, f"samples_manifest_{inst}.json")
        if not os.path.isfile(man_path):
            print(f"[warn] missing {man_path}, skipping {inst}")
            missing_manifests.append(inst)
            continue
        found_any_manifest = True
        man = json.load(open(man_path, encoding="utf-8"))
        srcdir = os.path.join(samples_root, sub)
        n = 0
        for s in man["samples"]:
            src = os.path.join(srcdir, s["file"])
            if not os.path.isfile(src):
                missing.append(src)
                continue
            shutil.copy2(src, os.path.join(snd_dir, s["file"]))
            sounds_json[s["id"]] = {"category": "master",
                                    "sounds": [{"name": f"qzpno:{s['id']}", "stream": False}]}
            n += 1
        counts[inst] = n

    if not found_any_manifest:
        raise RedPianoError(
            f"no sample manifests found under {samples_root} "
            f"(expected samples_manifest_piano.json etc.). The qzpno samples ship "
            f"separately — see BINARIES.md. Point --samples-root at the folder holding "
            f"the manifests + samples_<inst>/ dirs."
        )
    if missing_manifests and not allow_partial:
        raise RedPianoError(
            f"incomplete instrument set — missing manifest(s) for: "
            f"{', '.join(missing_manifests)} (expected all of "
            f"{', '.join(i for i, _ in LIBS)}). Those instruments would fall back to "
            f"vanilla/silence in-game. Point --samples-root at the full library, or pass "
            f"--allow-partial to knowingly ship only {', '.join(counts.keys())}."
        )
    if missing:
        raise RedPianoError(f"missing .ogg files referenced by manifests: {missing[:5]}"
                            f"{' ...' if len(missing) > 5 else ''}")

    json.dump(sounds_json,
              open(os.path.join(pack_dir, "assets", "qzpno", "sounds.json"), "w",
                   encoding="utf-8"),
              ensure_ascii=False)
    return sounds_json, counts


def build_resourcepack(mc_version, samples_root, out_zip, staging_dir=None,
                       allow_partial=False):
    """Assemble + zip the qzpno_mv resourcepack for ``mc_version``. Returns a stats dict."""
    profile = get_version_profile(mc_version)
    assert_build_supported(profile)  # green band only (mirror the datapack build policy)

    staging_dir = staging_dir or os.path.join(os.path.dirname(out_zip) or ".",
                                              "qzpno_mv")
    if os.path.isdir(staging_dir):
        shutil.rmtree(staging_dir)
    os.makedirs(staging_dir)

    sounds_json, counts = assemble_pack(samples_root, staging_dir,
                                        allow_partial=allow_partial)

    # version-driven pack.mcmeta (rp_format + single/minmax shape)
    meta = rp_packmeta(profile)
    json.dump(meta, open(os.path.join(staging_dir, "pack.mcmeta"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # zip (root contains pack.mcmeta + assets/)
    os.makedirs(os.path.dirname(out_zip) or ".", exist_ok=True)
    if os.path.isfile(out_zip):
        os.remove(out_zip)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(staging_dir):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, staging_dir))

    return {
        "mc_version": mc_version,
        "rp_format": profile.rp_format,
        "packmeta_shape": profile.packmeta_shape,
        "events": len(sounds_json),
        "counts": counts,
        "out_zip": out_zip,
        "size_kb": os.path.getsize(out_zip) // 1024,
    }


def build_argparser():
    p = argparse.ArgumentParser(
        prog="build_resourcepack.py",
        description="Repack the qzpno_mv resourcepack for a target MC version "
                    "(rp_format + pack.mcmeta shape auto-derived from the version table).")
    p.add_argument("--mc-version", default="1.21.8", dest="mc_version",
                   help="target Minecraft version (drives rp_format; default 1.21.8).")
    p.add_argument("--samples-root", required=True, dest="samples_root",
                   help="folder holding samples_manifest_*.json + samples_<inst>/ dirs "
                        "(ships separately — see BINARIES.md).")
    p.add_argument("--out", default=os.path.join("build", "qzpno_mv.zip"),
                   help="output .zip path (default build/qzpno_mv.zip).")
    p.add_argument("--allow-partial", action="store_true", dest="allow_partial",
                   help="knowingly ship a subset of instruments when some "
                        "samples_manifest_*.json are missing (those instruments fall back "
                        "to vanilla in-game). Without this, a missing manifest hard-fails.")
    return p


def main(argv=None):
    args = build_argparser().parse_args(argv)
    try:
        # Only a literal VMCache-mirror --out is rejected. Building a zip anywhere else
        # (incl. the workspace dist/) is a safe local artifact — never refuse it.
        require_not_vmcache_targets([args.out])
    except RuntimeGuardError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2
    try:
        stats = build_resourcepack(args.mc_version, args.samples_root, args.out,
                                   allow_partial=args.allow_partial)
    except RedPianoError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2
    shape = ("min/max " if stats["packmeta_shape"] == "minmax" else "pack_format ")
    print("=== qzpno_mv resourcepack ===")
    print(f"  mc-version : {stats['mc_version']}")
    print(f"  rp format  : {shape}{stats['rp_format']}")
    print(f"  events     : {stats['events']} ogg")
    for inst, n in stats["counts"].items():
        print(f"    {inst:6s}: {n}")
    print(f"  packed -> {stats['out_zip']}  ({stats['size_kb']} KB)")
    print("  note: enable it in Options → Resource Packs. If MC ever disabled it for a "
          "format mismatch, re-enable after this rebuild (no MC restart needed).")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    # tiny self-test path: `python build_resourcepack.py --selftest` checks the
    # version-driven pack.mcmeta shape without needing the (separately-shipped) samples.
    if "--selftest" in sys.argv:
        p8 = get_version_profile("1.21.8")
        m8 = rp_packmeta(p8)
        assert m8["pack"]["pack_format"] == 64 and "min_format" not in m8["pack"], m8
        p9 = get_version_profile("1.21.9")
        m9 = rp_packmeta(p9)
        assert m9["pack"]["min_format"] == 69 and m9["pack"]["max_format"] == 69, m9
        assert "pack_format" not in m9["pack"], m9
        print("ok: rp pack.mcmeta 1.21.8 single pack_format=64; 1.21.9 min/max=69")

        # partial-library policy: a subset library hard-fails by default, and
        # --allow-partial (allow_partial=True) knowingly ships what's there.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = os.path.join(td, "samples")
            os.makedirs(os.path.join(root, "samples_piano"))
            with open(os.path.join(root, "samples_piano", "c4.ogg"), "wb") as f:
                f.write(b"OggS")  # placeholder .ogg
            json.dump({"samples": [{"file": "c4.ogg", "id": "piano_c4"}]},
                      open(os.path.join(root, "samples_manifest_piano.json"), "w",
                           encoding="utf-8"))
            # only piano present -> default must hard-fail (bass/lead/pad/drums missing).
            try:
                assemble_pack(root, os.path.join(td, "pack_strict"))
                raise AssertionError("partial library should have raised")
            except RedPianoError as e:
                assert "incomplete instrument set" in str(e), str(e)
                for inst in ("bass", "lead", "pad", "drums"):
                    assert inst in str(e), str(e)
            # allow_partial -> succeeds with just piano.
            sj, counts = assemble_pack(root, os.path.join(td, "pack_partial"),
                                       allow_partial=True)
            assert counts.get("piano") == 1 and "bass" not in counts, (counts, sj)
        print("ok: partial library hard-fails by default; --allow-partial ships the subset")
        print("build_resourcepack self-test PASSED")
        sys.exit(0)
    sys.exit(main())
