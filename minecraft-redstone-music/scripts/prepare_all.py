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
  4. mod jar        -> auto-detected Gradle + JDK 21, unless explicitly skipped
  5. mods install   -> copy RedPiano jar + matching Fabric API into the profile mods/

It is a thin SEQUENCER over the existing CLIs (each remains independently runnable); it owns
no build logic. It fails fast: an unsupported version is refused before any step runs, and a
failing step aborts the rest. The two hard limits it CANNOT remove are surfaced explicitly:
pack_format numbers for an unknown version must be added to the table (never guessed), and the
recompiled mixin must be listened to in-game.

Example:
  python scripts/prepare_all.py --midi song.mid --ns mysong --origin 0 0 255 \
      --mc-version 1.21.10 --form swave --samples-root poc \
      --world-dir "C:/.../saves/test/datapacks" --enable-resourcepack
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from redpiano_core import RedPianoError, get_version_profile, assert_build_supported  # noqa: E402

DEFAULT_RP_OUT = os.path.join("build", "qzpno_mv.zip")


def _default_mod_dir():
    return os.path.normpath(os.path.join(_HERE, "..", "..", "mod", "redpiano"))


def _has_sample_manifests(path):
    return bool(path) and os.path.isfile(os.path.join(path, "samples_manifest_piano.json"))


def _default_samples_root():
    """Full source checkouts keep the qzpno samples in ../../poc.

    Packaged skill bundles may not include those licensed samples, so this helper
    returns None there and the caller requires --samples-root/--prebuilt-rp.
    """
    candidate = os.path.normpath(os.path.join(_HERE, "..", "..", "poc"))
    return candidate if _has_sample_manifests(candidate) else None


def _is_auto(value):
    return value is None or str(value).strip().lower() == "auto"


def _exe(name):
    return name + ".exe" if os.name == "nt" else name


def _bat(name):
    return name + ".bat" if os.name == "nt" else name


def _check_output(argv, *, env=None):
    try:
        r = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    return r.returncode, r.stdout or ""


def _java_home_javac(java_home):
    return os.path.join(java_home, "bin", _exe("javac"))


def _javac_is_21(javac):
    code, out = _check_output([javac, "-version"])
    if code != 0:
        return False, out
    return bool(re.search(r"\bjavac\s+21(?:\.|\s|$)", out)), out.strip()


def _infer_java_home_from_javac(javac):
    return os.path.dirname(os.path.dirname(os.path.abspath(javac)))


def _common_jdk21_homes():
    if os.name != "nt":
        return []
    patterns = [
        r"C:\Program Files\Eclipse Adoptium\jdk-21*",
        r"C:\Program Files\Java\jdk-21*",
        r"C:\Program Files\Microsoft\jdk-21*",
        r"C:\Program Files\Zulu\zulu-21*",
        r"C:\Program Files\BellSoft\LibericaJDK-21*",
        r"C:\Program Files\Amazon Corretto\jdk21*",
    ]
    homes = []
    for pat in patterns:
        homes.extend(glob.glob(pat))
    return sorted(set(homes), reverse=True)


def _resolve_jdk21(java_home_arg):
    """Return (java_home, detail) for a JDK 21, or (None, detail)."""
    candidates = []
    if not _is_auto(java_home_arg):
        candidates.append(("given --java-home", java_home_arg))
    env_home = os.environ.get("JAVA_HOME")
    if env_home:
        candidates.append(("JAVA_HOME", env_home))
    javac = shutil.which(_exe("javac")) or shutil.which("javac")
    if javac:
        candidates.append(("PATH javac", _infer_java_home_from_javac(javac)))
    for home in _common_jdk21_homes():
        candidates.append(("common install", home))

    seen = set()
    details = []
    for source, home in candidates:
        if not home:
            continue
        home = os.path.abspath(os.path.normpath(home))
        if home in seen:
            continue
        seen.add(home)
        javac = _java_home_javac(home)
        if not os.path.isfile(javac):
            details.append(f"{source}: {home} has no bin/{_exe('javac')}")
            continue
        ok, out = _javac_is_21(javac)
        details.append(f"{source}: {home} -> {out}")
        if ok:
            return home, details[-1]
    return None, "; ".join(details) if details else "no JDK 21 candidates found"


def _resolve_gradle(gradle_arg, mod_dir):
    """Return (gradle_launcher, detail), searching wrapper first, then PATH."""
    candidates = []
    if not _is_auto(gradle_arg):
        candidates.append(("given --gradle", gradle_arg))
    candidates.extend([
        ("project wrapper", os.path.join(mod_dir, _bat("gradlew"))),
        ("PATH gradle", shutil.which(_bat("gradle"))),
        ("PATH gradle", shutil.which(_exe("gradle"))),
        ("PATH gradle", shutil.which("gradle")),
    ])
    details = []
    seen = set()
    for source, path in candidates:
        if not path:
            continue
        path = os.path.abspath(os.path.normpath(path))
        if path in seen:
            continue
        seen.add(path)
        if os.path.isfile(path):
            return path, f"{source}: {path}"
        details.append(f"{source}: not found at {path}")
    return None, "; ".join(details) if details else "no Gradle launcher found"


def _latest_redpiano_jar(mod_dir):
    libs = os.path.join(mod_dir, "build", "libs")
    jars = []
    for path in glob.glob(os.path.join(libs, "*.jar")):
        name = os.path.basename(path).lower()
        if "sources" in name or "javadoc" in name or name.endswith("-dev.jar"):
            continue
        if name.startswith("redpiano"):
            jars.append(path)
    if not jars:
        return None
    return max(jars, key=lambda p: os.path.getmtime(p))


def _copy_to_profile_mods(src, profile_dir):
    mods_dir = os.path.join(profile_dir, "mods")
    os.makedirs(mods_dir, exist_ok=True)
    target = os.path.join(mods_dir, os.path.basename(src))
    if os.path.abspath(os.path.normpath(src)) != os.path.abspath(os.path.normpath(target)):
        shutil.copy2(src, target)
    return target


def _fabric_api_matches(path, mc_version):
    name = os.path.basename(path).lower()
    return (
        name.endswith(".jar")
        and "fabric-api" in name
        and ("+" + mc_version.lower()) in name
    )


def _find_fabric_api(profile_dir, mc_version):
    mods_dir = os.path.join(profile_dir, "mods")
    if not os.path.isdir(mods_dir):
        return None
    matches = [
        os.path.join(mods_dir, name)
        for name in os.listdir(mods_dir)
        if _fabric_api_matches(name, mc_version)
    ]
    if not matches:
        return None
    return max(matches, key=lambda p: os.path.getmtime(p))


def _download_fabric_api(profile_dir, mc_version):
    mods_dir = os.path.join(profile_dir, "mods")
    os.makedirs(mods_dir, exist_ok=True)
    query = urllib.parse.urlencode({
        "game_versions": json.dumps([mc_version]),
        "loaders": json.dumps(["fabric"]),
    })
    api = "https://api.modrinth.com/v2/project/fabric-api/version?" + query
    req = urllib.request.Request(
        api,
        headers={"User-Agent": "McMusicMaker-prepare-all/1.0 (redpiano runtime helper)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            versions = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise RedPianoError(
            f"could not auto-download Fabric API metadata for {mc_version}: {e}. "
            f"Pass --fabric-api-jar <matching fabric-api +{mc_version} jar>."
        )
    if not versions:
        raise RedPianoError(
            f"Modrinth returned no Fabric API build for Minecraft {mc_version}; "
            f"pass --fabric-api-jar manually."
        )
    files = versions[0].get("files") or []
    primary = next((f for f in files if f.get("primary")), None) or (files[0] if files else None)
    if not primary or not primary.get("url") or not primary.get("filename"):
        raise RedPianoError(f"Fabric API metadata for {mc_version} has no downloadable jar")
    target = os.path.join(mods_dir, primary["filename"])
    if os.path.isfile(target):
        return target
    dreq = urllib.request.Request(
        primary["url"],
        headers={"User-Agent": "McMusicMaker-prepare-all/1.0 (redpiano runtime helper)"},
    )
    try:
        with urllib.request.urlopen(dreq, timeout=120) as r, open(target, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception as e:
        raise RedPianoError(
            f"could not auto-download Fabric API jar for {mc_version}: {e}. "
            f"Pass --fabric-api-jar <matching fabric-api +{mc_version} jar>."
        )
    return target


def _infer_profile_dir(world_dir=None, rp_out=None):
    """Infer the Minecraft profile root from a world datapacks path or rp output."""
    if world_dir:
        p = os.path.abspath(os.path.normpath(world_dir))
        if os.path.basename(p).lower() == "datapacks":
            saves_dir = os.path.dirname(os.path.dirname(p))
            if os.path.basename(saves_dir).lower() == "saves":
                return os.path.dirname(saves_dir)
    if rp_out:
        p = os.path.abspath(os.path.normpath(rp_out))
        parent = os.path.dirname(p)
        if os.path.basename(parent).lower() == "resourcepacks":
            return os.path.dirname(parent)
    return None


def _read_resourcepack_format(zip_path):
    try:
        with zipfile.ZipFile(zip_path) as z:
            meta = json.loads(z.read("pack.mcmeta").decode("utf-8"))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as e:
        raise RedPianoError(f"could not read resourcepack pack.mcmeta from {zip_path}: {e}")
    pack = meta.get("pack", {})
    if "pack_format" in pack:
        pf = int(pack["pack_format"])
        return pf, pf
    if "min_format" in pack and "max_format" in pack:
        return int(pack["min_format"]), int(pack["max_format"])
    raise RedPianoError(
        f"resourcepack {zip_path} has no pack_format or min_format/max_format in pack.mcmeta"
    )


def _copy_prebuilt_resourcepack(src, out_zip, profile):
    lo, hi = _read_resourcepack_format(src)
    if not (lo <= profile.rp_format <= hi):
        actual = str(lo) if lo == hi else f"{lo}..{hi}"
        raise RedPianoError(
            f"prebuilt resourcepack {src} has rp format {actual}, but MC "
            f"{profile.mc_version} needs rp {profile.rp_format}; rebuild it with "
            f"build_resourcepack.py --mc-version {profile.mc_version}"
        )
    os.makedirs(os.path.dirname(out_zip) or ".", exist_ok=True)
    if os.path.abspath(os.path.normpath(src)) != os.path.abspath(os.path.normpath(out_zip)):
        shutil.copy2(src, out_zip)
    return out_zip


def _ensure_rp_in_profile(rp_zip, profile_dir):
    target_dir = os.path.join(profile_dir, "resourcepacks")
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, os.path.basename(rp_zip))
    if os.path.abspath(os.path.normpath(rp_zip)) != os.path.abspath(os.path.normpath(target)):
        shutil.copy2(rp_zip, target)
        print(f"  resourcepack copied into profile -> {target}")
    return target


def _load_options_list(line, key):
    try:
        return json.loads(line[len(key) + 1:] or "[]")
    except json.JSONDecodeError as e:
        raise RedPianoError(f"could not parse {key} in options.txt: {e}")


def _enable_resourcepack(profile_dir, rp_zip):
    """Enable file/<zip> in <profile>/options.txt, preserving other packs."""
    opt = os.path.join(profile_dir, "options.txt")
    if not os.path.isfile(opt):
        raise RedPianoError(
            f"cannot auto-enable resourcepack because options.txt was not found at {opt}; "
            f"start this Minecraft profile once, or enable {os.path.basename(rp_zip)} manually"
        )

    raw = open(opt, "r", encoding="utf-8").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    entry = "file/" + os.path.basename(rp_zip)
    changed = False
    saw_resource_packs = False

    for i, line in enumerate(lines):
        if line.startswith("resourcePacks:"):
            saw_resource_packs = True
            arr = _load_options_list(line, "resourcePacks")
            if entry not in arr:
                arr.append(entry)
                changed = True
            lines[i] = "resourcePacks:" + json.dumps(arr, ensure_ascii=False)
        elif line.startswith("incompatibleResourcePacks:"):
            arr = _load_options_list(line, "incompatibleResourcePacks")
            if entry in arr:
                arr = [x for x in arr if x != entry]
                changed = True
            lines[i] = "incompatibleResourcePacks:" + json.dumps(arr, ensure_ascii=False)

    if not saw_resource_packs:
        lines.append("resourcePacks:" + json.dumps([entry], ensure_ascii=False))
        changed = True

    backup = opt + ".redpiano.bak"
    if changed:
        shutil.copyfile(opt, backup)
        open(opt, "w", encoding="utf-8", newline="").write(nl.join(lines))
    return entry, changed, backup


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
        description="One command to prepare datapack + resourcepack + RedPiano mod "
                    "runtime for a target MC version (1.21..1.21.10).")
    p.add_argument("--midi", required=True, help="source .mid file")
    p.add_argument("--ns", required=True, help="datapack namespace")
    p.add_argument("--origin", required=True, nargs=3, type=int, metavar=("X", "Z", "Y"))
    p.add_argument("--mc-version", required=True, dest="mc_version",
                   help="target MC version (1.21..1.21.10).")
    p.add_argument("--form", required=True,
                   choices=["inplace", "swave", "straight", "custom", "multilane"],
                   help="machine form. Ask/confirm this with the user; recommended swave, "
                        "safe fallback inplace.")
    p.add_argument("--params", default=None, help="designer JSON for build_machine (optional).")
    p.add_argument("--world-dir", default=None, dest="world_dir",
                   help="deploy the datapack into this world's datapacks dir (opt-in).")
    p.add_argument("--out", default="build", help="datapack staging dir (default build).")
    p.add_argument("--force-cap", action="store_true", dest="force_cap",
                   help="pass --force-cap to build_machine (forceload auto-fold).")
    # resourcepack
    p.add_argument("--samples-root", default=None, dest="samples_root",
                   help="folder with samples_manifest_*.json + samples_<inst>/ (ships "
                        "separately). Auto-detects ../../poc in a full source checkout.")
    p.add_argument("--prebuilt-rp", default=None, dest="prebuilt_rp",
                   help="existing qzpno_mv.zip to copy instead of rebuilding from samples.")
    p.add_argument("--skip-resourcepack", action="store_true", dest="skip_resourcepack",
                   help="explicitly skip the resourcepack step. Use only when you have "
                        "already installed and enabled a matching qzpno_mv.zip.")
    p.add_argument("--rp-out", default=DEFAULT_RP_OUT, dest="rp_out",
                   help="resourcepack .zip output path. If a profile is inferred/provided, "
                        "the default becomes <profile>/resourcepacks/qzpno_mv.zip.")
    p.add_argument("--profile-dir", default=None, dest="profile_dir",
                   help="Minecraft profile root, e.g. .../ModrinthApp/profiles/Fabric 1.21.8. "
                        "Usually inferred from --world-dir <profile>/saves/<world>/datapacks.")
    p.add_argument("--enable-resourcepack", action="store_true", dest="enable_resourcepack",
                   help="edit <profile>/options.txt so file/qzpno_mv.zip is selected "
                        "(kept for compatibility; this is automatic when a profile is known).")
    p.add_argument("--no-enable-resourcepack", action="store_true", dest="no_enable_resourcepack",
                   help="do not edit options.txt. Use only when you will enable the pack manually.")
    # mod
    p.add_argument("--mod-dir", default=None, dest="mod_dir",
                   help="path to mod/redpiano (default ../../mod/redpiano).")
    p.add_argument("--gradle", default="auto",
                   help="Gradle launcher path, or 'auto' to search project wrapper/PATH "
                        "(default auto).")
    p.add_argument("--java-home", default="auto", dest="java_home",
                   help="JAVA_HOME for a JDK 21, or 'auto' to search JAVA_HOME/PATH/common "
                        "install locations (default auto).")
    p.add_argument("--prebuilt-mod-jar", default=None, dest="prebuilt_mod_jar",
                   help="install this RedPiano jar instead of building one with Gradle.")
    p.add_argument("--skip-mod-build", action="store_true", dest="skip_mod_build",
                   help="explicitly skip RedPiano jar build. This produces a NOT READY "
                        "result unless a matching jar is already installed.")
    p.add_argument("--skip-mod-install", action="store_true", dest="skip_mod_install",
                   help="do not copy RedPiano jar into <profile>/mods.")
    p.add_argument("--fabric-api-jar", default="auto", dest="fabric_api_jar",
                   help="matching Fabric API jar to install, or 'auto' to reuse/download "
                        "a build for --mc-version (default auto).")
    p.add_argument("--no-download-fabric-api", action="store_true", dest="no_download_fabric_api",
                   help="do not use Modrinth to fetch Fabric API when it is missing.")
    p.add_argument("--skip-fabric-api-check", action="store_true", dest="skip_fabric_api_check",
                   help="explicitly skip Fabric API install/check. This is not a ready runtime.")
    args = p.parse_args(argv)

    # 0. fail fast on unsupported version BEFORE running anything.
    try:
        profile = get_version_profile(args.mc_version)
        assert_build_supported(profile)
    except RedPianoError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2

    # Resolve resourcepack intent before doing any work. Silent skips were the
    # common failure mode: a datapack deployed fine, but no qzpno_mv.zip existed
    # in the game profile, so the machine was silent or fell back to vanilla.
    if args.skip_resourcepack and (args.samples_root or args.prebuilt_rp):
        sys.stderr.write(
            "error: --skip-resourcepack cannot be combined with --samples-root or --prebuilt-rp\n"
        )
        return 2
    if args.samples_root and args.prebuilt_rp:
        sys.stderr.write("error: choose either --samples-root or --prebuilt-rp, not both\n")
        return 2
    if not args.samples_root and not args.prebuilt_rp and not args.skip_resourcepack:
        auto_samples = _default_samples_root()
        if auto_samples:
            args.samples_root = auto_samples
            print(f"[auto] using samples-root: {args.samples_root}")
        else:
            sys.stderr.write(
                "error: resourcepack is required. Pass --samples-root <dir> to build "
                "qzpno_mv.zip, --prebuilt-rp <zip> to install an existing pack, or "
                "--skip-resourcepack only if a matching qzpno_mv.zip is already installed "
                "and enabled.\n"
            )
            return 2
    if args.samples_root and not _has_sample_manifests(args.samples_root):
        sys.stderr.write(
            f"error: --samples-root {args.samples_root} does not contain "
            "samples_manifest_piano.json (expected the qzpno sample root)\n"
        )
        return 2

    profile_dir = args.profile_dir or _infer_profile_dir(args.world_dir, args.rp_out)
    if args.rp_out == DEFAULT_RP_OUT and profile_dir and not args.skip_resourcepack:
        args.rp_out = os.path.join(profile_dir, "resourcepacks", "qzpno_mv.zip")
    auto_enable_resourcepack = (
        not args.no_enable_resourcepack
        and not args.skip_resourcepack
        and profile_dir is not None
    )
    if args.enable_resourcepack and not profile_dir:
        sys.stderr.write(
            "error: --enable-resourcepack needs --profile-dir, or a --world-dir shaped like "
            "<profile>/saves/<world>/datapacks, or an --rp-out inside <profile>/resourcepacks\n"
        )
        return 2
    if args.no_enable_resourcepack and args.enable_resourcepack:
        sys.stderr.write("error: choose either --enable-resourcepack or --no-enable-resourcepack\n")
        return 2
    if args.prebuilt_mod_jar and args.skip_mod_build:
        print("[auto] --prebuilt-mod-jar was provided; it will be installed even though build is skipped.")

    mod_dir = args.mod_dir or _default_mod_dir()
    py = sys.executable
    here = _HERE
    pf = (f"min/max {profile.dp_format}" if profile.packmeta_shape == "minmax"
          else f"pack_format {profile.dp_format}")
    print("#" * 64)
    print(f"#  prepare_all — MC {args.mc_version}  (tier {profile.tier}; dp {pf}, rp {profile.rp_format})")
    print("#  datapack -> resourcepack -> mod-config -> mod jar -> mods install")
    if profile_dir:
        print(f"#  profile -> {profile_dir}")
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
    resourcepack_ready = False
    resourcepack_enabled = False
    if args.samples_root:
        rp_argv = [py, os.path.join(here, "build_resourcepack.py"),
                   "--mc-version", args.mc_version, "--samples-root", args.samples_root,
                   "--out", args.rp_out]
        if not _run("resourcepack (build_resourcepack.py)", rp_argv):
            return 1
        resourcepack_ready = True
    elif args.prebuilt_rp:
        print("\n" + "=" * 64)
        print("  STEP: resourcepack (prebuilt copy)")
        print(f"  source: {args.prebuilt_rp}")
        print(f"  out   : {args.rp_out}")
        print("=" * 64)
        try:
            _copy_prebuilt_resourcepack(args.prebuilt_rp, args.rp_out, profile)
        except RedPianoError as e:
            sys.stderr.write(f"error: {e}\n")
            return 2
        print(f"  copied -> {args.rp_out}  ({os.path.getsize(args.rp_out)//1024} KB)")
        resourcepack_ready = True
    else:
        print("\n" + "-" * 64)
        print("  STEP: resourcepack SKIPPED BY REQUEST (--skip-resourcepack).")
        print("  This path is allowed only because --skip-resourcepack was explicit.")
        print("  Verify qzpno_mv.zip is already installed and enabled before play.")
        print("-" * 64)

    if resourcepack_ready and auto_enable_resourcepack:
        print("\n" + "=" * 64)
        print("  STEP: enable resourcepack (options.txt)")
        print("=" * 64)
        try:
            args.rp_out = _ensure_rp_in_profile(args.rp_out, profile_dir)
            rp_entry, changed, backup = _enable_resourcepack(profile_dir, args.rp_out)
        except RedPianoError as e:
            sys.stderr.write(f"error: {e}\n")
            return 2
        resourcepack_enabled = True
        if changed:
            print(f"  enabled {rp_entry} in options.txt  (backup: {backup})")
        else:
            print(f"  {rp_entry} was already enabled in options.txt")

    # 3. MOD BUILD-CONFIG
    mb_argv = [py, os.path.join(here, "mod_build.py"),
               "--mc-version", args.mc_version, "--write", "--mod-dir", mod_dir]
    if not _run("mod build-config (mod_build.py --write)", mb_argv):
        return 1

    # 4. MOD JAR (default automation: build it unless a prebuilt jar is supplied
    # or the caller explicitly opts out).
    built_jar = False
    mod_jar = None
    mod_jar_source = None
    if args.prebuilt_mod_jar:
        if not os.path.isfile(args.prebuilt_mod_jar):
            sys.stderr.write(f"error: --prebuilt-mod-jar not found: {args.prebuilt_mod_jar}\n")
            return 2
        mod_jar = os.path.abspath(os.path.normpath(args.prebuilt_mod_jar))
        mod_jar_source = "prebuilt"
    elif args.skip_mod_build:
        print("\n" + "-" * 64)
        print("  STEP: mod jar SKIPPED BY REQUEST (--skip-mod-build).")
        print("  This is not a ready runtime unless RedPiano is already installed in mods/.")
        print("-" * 64)
    else:
        gradle, gradle_detail = _resolve_gradle(args.gradle, mod_dir)
        java_home, java_detail = _resolve_jdk21(args.java_home)
        if not gradle:
            sys.stderr.write(
                "error: RedPiano mod jar is required, but no Gradle launcher was found. "
                f"Search detail: {gradle_detail}. Install Gradle or pass --gradle <path>; "
                "do not report success without a jar.\n"
            )
            return 2
        if not java_home:
            sys.stderr.write(
                "error: RedPiano mod jar is required, but no JDK 21 with javac was found. "
                f"Search detail: {java_detail}. Install a JDK 21 or pass --java-home <path>; "
                "a JRE is not enough.\n"
            )
            return 2
        print(f"[auto] using Gradle: {gradle_detail}")
        print(f"[auto] using JDK 21: {java_detail}")
        env = dict(os.environ)
        env["JAVA_HOME"] = java_home
        env["PATH"] = os.path.join(java_home, "bin") + os.pathsep + env.get("PATH", "")
        if not _run(f"mod jar ({os.path.basename(gradle)} build)",
                    [gradle, "build"], cwd=mod_dir, env=env):
            print("  (the build-config IS written, but the runtime is NOT ready.)")
            return 1
        mod_jar = _latest_redpiano_jar(mod_dir)
        if not mod_jar:
            sys.stderr.write(
                f"error: Gradle build finished but no redpiano jar was found under "
                f"{os.path.join(mod_dir, 'build', 'libs')}\n"
            )
            return 1
        built_jar = True
        mod_jar_source = "built"

    # 5. MODS INSTALL (copy RedPiano + ensure matching Fabric API).
    installed_mod_jar = None
    fabric_api_ready = False
    fabric_api_path = None
    if profile_dir and not args.skip_mod_install:
        if mod_jar:
            installed_mod_jar = _copy_to_profile_mods(mod_jar, profile_dir)
            print(f"[auto] RedPiano jar installed -> {installed_mod_jar}")
        elif not args.skip_mod_build:
            sys.stderr.write("error: RedPiano jar was not built or supplied; runtime is not ready\n")
            return 1

        if args.skip_fabric_api_check:
            print("[auto] Fabric API check skipped by request; runtime may not load.")
        else:
            if not _is_auto(args.fabric_api_jar):
                if not os.path.isfile(args.fabric_api_jar):
                    sys.stderr.write(f"error: --fabric-api-jar not found: {args.fabric_api_jar}\n")
                    return 2
                if not _fabric_api_matches(args.fabric_api_jar, args.mc_version):
                    sys.stderr.write(
                        f"error: --fabric-api-jar does not look like a Fabric API build "
                        f"for +{args.mc_version}: {args.fabric_api_jar}\n"
                    )
                    return 2
                fabric_api_path = _copy_to_profile_mods(args.fabric_api_jar, profile_dir)
                fabric_api_ready = True
                print(f"[auto] Fabric API installed -> {fabric_api_path}")
            else:
                fabric_api_path = _find_fabric_api(profile_dir, args.mc_version)
                if fabric_api_path:
                    fabric_api_ready = True
                    print(f"[auto] Fabric API already present -> {fabric_api_path}")
                elif not args.no_download_fabric_api:
                    print("[auto] Fabric API missing; downloading matching build from Modrinth...")
                    try:
                        fabric_api_path = _download_fabric_api(profile_dir, args.mc_version)
                    except RedPianoError as e:
                        sys.stderr.write(f"error: {e}\n")
                        return 2
                    fabric_api_ready = True
                    print(f"[auto] Fabric API downloaded -> {fabric_api_path}")
                else:
                    sys.stderr.write(
                        f"error: matching Fabric API +{args.mc_version} was not found in "
                        f"{os.path.join(profile_dir, 'mods')}. Pass --fabric-api-jar <jar> "
                        "or allow the default Modrinth download.\n"
                    )
                    return 2
    elif profile_dir and args.skip_mod_install:
        print("[auto] mod install skipped by request; profile mods/ was not changed.")

    # ── consolidated summary + the one step that can't be automated ──
    print("\n" + "#" * 64)
    print(f"#  prepared for MC {args.mc_version}:")
    print(f"#    [x] datapack        ({args.ns}, {pf})"
          + (f"  deployed -> {args.world_dir}" if args.world_dir else "  (build/ — not deployed)"))
    if resourcepack_ready:
        suffix = "  enabled" if resourcepack_enabled else "  NOT auto-enabled"
        print(f"#    [x] resourcepack    (rp {profile.rp_format})  -> {args.rp_out}{suffix}")
    else:
        print("#    [!] resourcepack    SKIPPED BY REQUEST")
    print(f"#    [x] mod build-config (gradle.properties + loom line in {mod_dir})")
    if mod_jar:
        tag = "built" if built_jar else mod_jar_source
        print(f"#    [x] mod jar          ({tag}) -> {mod_jar}")
    else:
        print("#    [ ] mod jar          NOT built (explicitly skipped)")
    if installed_mod_jar:
        print(f"#    [x] RedPiano in mods -> {installed_mod_jar}")
    elif profile_dir and not args.skip_mod_install:
        print("#    [ ] RedPiano in mods NOT installed")
    if fabric_api_ready:
        print(f"#    [x] Fabric API       -> {fabric_api_path}")
    elif profile_dir and args.skip_fabric_api_check:
        print("#    [!] Fabric API       check skipped by request")
    print("#")
    print("#  STILL ON YOU (cannot be automated from the filesystem):")
    if installed_mod_jar or fabric_api_ready:
        print("#    - fully restart Minecraft after any mods/ jar change")
    elif profile_dir and (args.skip_mod_install or args.skip_mod_build):
        print(f"#    - install RedPiano + Fabric API for {args.mc_version}, then restart MC")
    elif not profile_dir:
        print(f"#    - copy RedPiano + Fabric API for {args.mc_version} into the profile mods/, then restart MC")
    if resourcepack_ready and not resourcepack_enabled:
        print(f"#    - enable {os.path.basename(args.rp_out)} in Options -> Resource Packs")
    elif not resourcepack_ready:
        print("#    - verify qzpno_mv.zip is already installed and enabled")
    print("#    - in-game: /reload -> /tick rate 80 (TYPE MANUALLY) -> /function %s:setup -> press [play]" % args.ns)
    print("#      (the machine does NOT set the tick rate; you must type /tick rate 80 yourself)")
    print("#    - LISTEN ONCE: a recompiled mixin can compile yet mis-behave; only trust it after you hear it.")
    print("#" * 64)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
