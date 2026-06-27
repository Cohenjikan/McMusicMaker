# -*- coding: utf-8 -*-
"""prepare_all.py — one command to prepare the WHOLE runtime stack for a target version.

This is the "全盘自编译" orchestrator for the supported green band (1.21..1.21.10). Given
one --mc-version, it runs every step that CAN be automated, in order, and stops at the one
step that fundamentally cannot be (the in-game listen — a Fabric mixin binds to internal
NoteBlock bytecode, so a recompiled jar must be heard once before it is trusted):

  1. datapack        -> build_machine.py   (pack_format / folders / pack.mcmeta shape /
                                             sign dialect all auto-derived from the version)
  2. resourcepack    -> build_resourcepack.py  (rp_format auto; needs --samples-root)
  3. mod build-config-> mod_build.py --write    (sets gradle.properties + the loom line)
  4. mod jar (opt.)  -> <gradle> build           (only if --gradle is given; needs JDK 21)

It is a thin SEQUENCER over the existing CLIs (each remains independently runnable); it owns
no build logic. It fails fast: an unsupported version is refused before any step runs, and a
failing step aborts the rest. The two hard limits it CANNOT remove are surfaced explicitly:
pack_format numbers for an unknown version must be added to the table (never guessed), and the
recompiled mixin must be listened to in-game.

Example:
  python scripts/prepare_all.py --midi song.mid --ns mysong --origin 0 0 255 \
      --mc-version 1.21.10 --form swave --samples-root poc \
      --world-dir "C:/.../saves/test/datapacks" --rp-out "C:/.../resourcepacks/qzpno_mv.zip" \
      --gradle "C:/tools/gradle-8.12/bin/gradle.bat" --java-home "C:/jdk/jdk-21"
"""

import argparse
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from redpiano_core import RedPianoError, get_version_profile, assert_build_supported  # noqa: E402


def _default_mod_dir():
    return os.path.normpath(os.path.join(_HERE, "..", "..", "mod", "redpiano"))


def _run(label, argv, *, cwd=None, env=None):
    """Run a sub-step, streaming its output. Returns True on success, False on failure."""
    print("\n" + "=" * 64)
    print(f"  STEP: {label}")
    print("  $ " + " ".join(str(a) for a in argv))
    print("=" * 64)
    try:
        r = subprocess.run(argv, cwd=cwd, env=env)
    except OSError as e:
        print(f"  !! could not run {label}: {e}")
        return False
    if r.returncode != 0:
        print(f"  !! {label} FAILED (exit {r.returncode}) — aborting the remaining steps.")
        return False
    return True


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="prepare_all.py",
        description="One command to prepare datapack + resourcepack + mod build-config "
                    "(and optionally the jar) for a target MC version (1.21..1.21.10).")
    p.add_argument("--midi", required=True, help="source .mid file")
    p.add_argument("--ns", required=True, help="datapack namespace")
    p.add_argument("--origin", required=True, nargs=3, type=int, metavar=("X", "Z", "Y"))
    p.add_argument("--mc-version", required=True, dest="mc_version",
                   help="target MC version (1.21..1.21.10).")
    p.add_argument("--form", default="swave",
                   choices=["inplace", "swave", "straight", "custom", "multilane"],
                   help="machine form (default swave).")
    p.add_argument("--params", default=None, help="designer JSON for build_machine (optional).")
    p.add_argument("--world-dir", default=None, dest="world_dir",
                   help="deploy the datapack into this world's datapacks dir (opt-in).")
    p.add_argument("--out", default="build", help="datapack staging dir (default build).")
    p.add_argument("--force-cap", action="store_true", dest="force_cap",
                   help="pass --force-cap to build_machine (forceload auto-fold).")
    # resourcepack
    p.add_argument("--samples-root", default=None, dest="samples_root",
                   help="folder with samples_manifest_*.json + samples_<inst>/ (ships "
                        "separately). Omit to SKIP the resourcepack step (with a note).")
    p.add_argument("--rp-out", default=os.path.join("build", "qzpno_mv.zip"), dest="rp_out",
                   help="resourcepack .zip output path (default build/qzpno_mv.zip).")
    # mod
    p.add_argument("--mod-dir", default=None, dest="mod_dir",
                   help="path to mod/redpiano (default ../../mod/redpiano).")
    p.add_argument("--gradle", default=None,
                   help="path to a gradle launcher; if given, actually build the mod jar. "
                        "Omit to only write the build-config and print the build command.")
    p.add_argument("--java-home", default=None, dest="java_home",
                   help="JAVA_HOME (JDK 21) for the gradle build.")
    args = p.parse_args(argv)

    # 0. fail fast on unsupported version BEFORE running anything.
    try:
        profile = get_version_profile(args.mc_version)
        assert_build_supported(profile)
    except RedPianoError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2

    mod_dir = args.mod_dir or _default_mod_dir()
    py = sys.executable
    here = _HERE
    pf = (f"min/max {profile.dp_format}" if profile.packmeta_shape == "minmax"
          else f"pack_format {profile.dp_format}")
    print("#" * 64)
    print(f"#  prepare_all — MC {args.mc_version}  (tier {profile.tier}; dp {pf}, rp {profile.rp_format})")
    print(f"#  datapack -> resourcepack -> mod-config" + ("  -> gradle build" if args.gradle else ""))
    print("#" * 64)

    # 1. DATAPACK
    dp_argv = [py, os.path.join(here, "build_machine.py"),
               "--midi", args.midi, "--form", args.form, "--ns", args.ns,
               "--origin", str(args.origin[0]), str(args.origin[1]), str(args.origin[2]),
               "--mc-version", args.mc_version, "--out", args.out]
    if args.params:
        dp_argv += ["--params", args.params]
    if args.world_dir:
        dp_argv += ["--world-dir", args.world_dir]
    if args.force_cap:
        dp_argv += ["--force-cap"]
    if not _run("datapack (build_machine.py)", dp_argv):
        return 1

    # 2. RESOURCEPACK
    if args.samples_root:
        rp_argv = [py, os.path.join(here, "build_resourcepack.py"),
                   "--mc-version", args.mc_version, "--samples-root", args.samples_root,
                   "--out", args.rp_out]
        if not _run("resourcepack (build_resourcepack.py)", rp_argv):
            return 1
    else:
        print("\n" + "-" * 64)
        print("  STEP: resourcepack — SKIPPED (no --samples-root given).")
        print(f"  The qzpno samples ship separately (see BINARIES.md). To repack for "
              f"{args.mc_version} (rp_format {profile.rp_format}):")
        print(f"    python scripts/build_resourcepack.py --mc-version {args.mc_version} "
              f"--samples-root <dir> --out {args.rp_out}")
        print("-" * 64)

    # 3. MOD BUILD-CONFIG
    mb_argv = [py, os.path.join(here, "mod_build.py"),
               "--mc-version", args.mc_version, "--write", "--mod-dir", mod_dir]
    if not _run("mod build-config (mod_build.py --write)", mb_argv):
        return 1

    # 4. MOD JAR (optional — needs a real toolchain)
    built_jar = False
    if args.gradle:
        env = dict(os.environ)
        if args.java_home:
            env["JAVA_HOME"] = args.java_home
        if not _run(f"mod jar ({os.path.basename(args.gradle)} build)",
                    [args.gradle, "build"], cwd=mod_dir, env=env):
            print("  (the build-config IS written; you can run the gradle build manually.)")
            return 1
        built_jar = True

    # ── consolidated summary + the one step that can't be automated ──
    print("\n" + "#" * 64)
    print(f"#  prepared for MC {args.mc_version}:")
    print(f"#    [x] datapack        ({args.ns}, {pf})"
          + (f"  deployed -> {args.world_dir}" if args.world_dir else "  (build/ — not deployed)"))
    if args.samples_root:
        print(f"#    [x] resourcepack    (rp {profile.rp_format})  -> {args.rp_out}")
    else:
        print(f"#    [ ] resourcepack    SKIPPED (no --samples-root)")
    print(f"#    [x] mod build-config (gradle.properties + loom line in {mod_dir})")
    if built_jar:
        print(f"#    [x] mod jar          -> {os.path.join(mod_dir, 'build', 'libs', 'redpiano-1.0.0.jar')}")
    else:
        print(f"#    [ ] mod jar          NOT built — run: cd {mod_dir} && <gradle> build (JDK 21),"
              f" or pass --gradle/--java-home")
    print("#")
    print("#  STILL ON YOU (cannot be automated):")
    print(f"#    · drop the jar in <profile>/mods/ + the fabric-api build for {args.mc_version}; restart MC")
    if args.samples_root:
        print(f"#    · put {os.path.basename(args.rp_out)} in <profile>/resourcepacks/ + enable it")
    print("#    · in-game: /reload -> /tick rate 80 -> /function %s:setup -> press [play]" % args.ns)
    print("#    · LISTEN ONCE — a recompiled mixin can compile yet mis-behave; only trust it after you hear it.")
    print("#" * 64)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
