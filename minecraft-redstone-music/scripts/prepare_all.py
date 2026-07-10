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

It does NOT copy into the Minecraft profile from a sandbox (that write would land in a
VMCache mirror the game never reads — see docs/RUNTIME_SANDBOX.md). Instead it stages
everything into the workspace `dist/` and emits `dist/DEPLOY_TO_GAME.bat`; the USER
double-clicks that (natively) to install, which writes `dist/DEPLOY_RECEIPT.txt` as proof.

Example:
  python scripts/prepare_all.py --midi song.mid --ns mysong --origin 0 0 255 \
      --mc-version 1.21.8 --form swave --prebuilt-rp qzpno_mv.zip \
      --prebuilt-mod-jar redpiano-1.0.0.jar \
      --world-dir "C:/.../saves/test/datapacks" --profile-dir "C:/.../Fabric 1.21.8" --dist dist
  # then: user double-clicks dist/DEPLOY_TO_GAME.bat ; verify with
  #   python scripts/deploy_bundle.py --verify dist
"""

import argparse
import glob
import hashlib
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
from runtime_guard import path_is_under_trae_vmcache, RuntimeGuardError  # noqa: E402
import deploy_bundle  # noqa: E402

DEFAULT_RP_OUT = os.path.join("build", "qzpno_mv.zip")


def _under_trae_vmcache(value):
    return path_is_under_trae_vmcache(value)


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


def _stage_jar(src, mods_dir):
    """Copy a jar into a staging mods/ dir (workspace), returning the target path."""
    os.makedirs(mods_dir, exist_ok=True)
    target = os.path.join(mods_dir, os.path.basename(src))
    if os.path.abspath(os.path.normpath(src)) != os.path.abspath(os.path.normpath(target)):
        shutil.copy2(src, target)
    return target


def _fabric_api_matches(path, mc_version):
    name = os.path.basename(path).lower()
    if not name.endswith(".jar") or "fabric-api" not in name:
        return False
    # Match the version as a WHOLE segment: fabric-api jars are named like
    # `fabric-api-0.115.0+1.21.8.jar`, so the MC version is the tail after the last '+'.
    # A plain substring test ('+1.21' in name) would wrongly match `+1.21.1` for `1.21`.
    stem = name[:-len(".jar")]
    return stem.endswith("+" + mc_version.lower())


def _find_fabric_api(mods_dir, mc_version):
    if not mods_dir or not os.path.isdir(mods_dir):
        return None
    matches = [
        os.path.join(mods_dir, name)
        for name in os.listdir(mods_dir)
        if _fabric_api_matches(name, mc_version)
    ]
    if not matches:
        return None
    return max(matches, key=lambda p: os.path.getmtime(p))


def _sha512_of(path):
    """Stream a file through sha512 in 1MB chunks (stdlib only, no full-file read into memory)."""
    h = hashlib.sha512()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_fabric_api(mods_dir, mc_version):
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
    # Corruption detection, not supply-chain security: a timed-out/truncated download can
    # leave a half-written jar on disk, and the old `if os.path.isfile: return` reused that
    # broken cache forever. sha512 (from Modrinth's own files[].hashes) catches that case.
    expected = (primary.get("hashes") or {}).get("sha512")
    if os.path.isfile(target):
        if not expected or _sha512_of(target) == expected:
            return target
        print(f"[warn] cached {target} 校验哈希不匹配(可能是上次下载被截断/损坏),重新下载")
        os.remove(target)
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
    if expected:
        if _sha512_of(target) != expected:
            os.remove(target)
            raise RedPianoError(
                f"downloaded Fabric API jar for {mc_version} failed sha512 verification "
                f"(likely a truncated/corrupt download); retry, or pass --fabric-api-jar manually."
            )
    else:
        print(f"[warn] Fabric API metadata for {mc_version} has no sha512 hash; skipping verification")
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


def _expected_sound_ids():
    """The 103 canonical `qzpno:<id>` sound-event ids the RedPiano mod plays — read
    from the single source of truth (assets/redpiano_map_multi.json, same file the mod's
    RedPianoMap.java mirrors). Returns a set like {'qzpno:pno_c4_mf', ...}. A supplied
    --prebuilt-rp whose sounds.json omits any of these leaves those note blocks SILENT
    in-game (the mixin cancels the vanilla sound and asks for the missing qzpno: event),
    so the resourcepack check compares against this set."""
    from redpiano_core import InstrumentMap  # local import: keep module import cheap
    imap = InstrumentMap.load()
    ids = set()
    for inst in imap.instruments.values():
        for sid in inst.get("sound", {}).values():
            ids.add(sid)
    return ids


def _resourcepack_event_ids(zip_path):
    """Read the qzpno sound-event ids DEFINED by a resourcepack zip (its
    assets/qzpno/sounds.json keys, namespaced as qzpno:<key>). Returns a set, or None
    if the zip has no readable sounds.json (older/foreign layout — we then skip the
    coverage warning rather than mis-report every id as missing)."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = {n.replace("\\", "/") for n in z.namelist()}
            target = "assets/qzpno/sounds.json"
            if target not in names:
                return None
            data = json.loads(z.read(target).decode("utf-8"))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return {f"qzpno:{k}" for k in data.keys()}


def _warn_missing_events(src):
    """Compare a prebuilt pack's sounds.json against the 103 canonical ids and print a
    [warn] listing any missing ones (missing => those blocks are silent in-game). Never
    raises: a partial-but-format-correct pack is still installable (some voices silent),
    so this is a warning, not a hard error. Returns the count of missing ids (0 = full)."""
    try:
        expected = _expected_sound_ids()
    except RedPianoError:
        return 0  # can't load the canonical map (shouldn't happen) — don't block install
    have = _resourcepack_event_ids(src)
    if have is None:
        print("  [warn] 无法读取该资源包的 assets/qzpno/sounds.json — 跳过音效覆盖检查"
              "（若装了 RedPiano 模组却听不到某些音，多半是这个包缺 qzpno: 音效）。")
        return 0
    missing = sorted(expected - have)
    if missing:
        shown = ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")
        print(f"  [warn] 该资源包缺少 {len(missing)}/{len(expected)} 个 qzpno: 音效事件"
              f"（这些音符盒在游戏里会【静音】，不会退回原版音色）: {shown}")
        print("         想要完整音色: 用 build_resourcepack.py --samples-root <全套采样> 重打包，"
              "或 python scripts/make_demo_samples.py 造一套开放 demo 音源。")
    return len(missing)


def _copy_prebuilt_resourcepack(src, out_zip, profile):
    lo, hi = _read_resourcepack_format(src)
    if not (lo <= profile.rp_format <= hi):
        actual = str(lo) if lo == hi else f"{lo}..{hi}"
        raise RedPianoError(
            f"这个资源包是格式 {actual}，但 MC {profile.mc_version} 需要 rp 格式 "
            f"{profile.rp_format} —— 格式不符 MC 会【静默禁用】整个包，导致全静音。\n"
            f"  修法(任选其一):\n"
            f"    1) 用它换版本重打包(不用采样文件夹): python scripts/build_resourcepack.py "
            f"--from-zip \"{src}\" --mc-version {profile.mc_version} --out <derived.zip>，再把 "
            f"<derived.zip> 作为 --prebuilt-rp 传进来;\n"
            f"    2) 若手头有全套采样文件夹，直接为本版本重建: python scripts/build_resourcepack.py "
            f"--mc-version {profile.mc_version} --samples-root <采样目录>。\n"
            f"  (prebuilt resourcepack {src} has rp format {actual}, MC {profile.mc_version} "
            f"needs rp {profile.rp_format}.)"
        )
    # Format is OK (MC will load it). Now warn — not fail — if it does not carry all 103
    # qzpno: events: a subset pack installs fine but leaves the uncovered blocks silent.
    _warn_missing_events(src)
    os.makedirs(os.path.dirname(out_zip) or ".", exist_ok=True)
    if os.path.abspath(os.path.normpath(src)) != os.path.abspath(os.path.normpath(out_zip)):
        shutil.copy2(src, out_zip)
    return out_zip


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


def _run_main(argv=None):
    p = argparse.ArgumentParser(
        prog="prepare_all.py",
        description="One command to prepare datapack + resourcepack + RedPiano mod "
                    "runtime for a target MC version (1.21..1.21.10).")
    p.add_argument("--midi", required=True, help="source .mid file")
    p.add_argument("--ns", required=True, help="datapack namespace")
    p.add_argument("--origin", required=True, nargs=3, type=int, metavar=("X", "Z", "Y"),
                   help="注意顺序是 X Z Y，不是游戏 F3 显示的 X Y Z。machine origin: "
                        "world X, world Z, then world Y (height).")
    p.add_argument("--mc-version", required=True, dest="mc_version",
                   help="target MC version (1.21..1.21.10).")
    p.add_argument("--form", required=True,
                   choices=["inplace", "swave", "straight", "custom", "multilane"],
                   help="machine form. Ask/confirm this with the user; recommended swave, "
                        "safe fallback inplace.")
    p.add_argument("--params", default=None, help="designer JSON for build_machine (optional).")
    p.add_argument("--world-dir", required=True, dest="world_dir",
                   help="target world's datapacks dir, e.g. .../saves/<world>/datapacks. "
                        "REQUIRED: it is baked into the generated DEPLOY_TO_GAME.bat as the "
                        "datapack destination — without it the .bat would crash on an empty "
                        "path when double-clicked.")
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
                   help="explicitly skip the resourcepack step. Consequence: with the RedPiano "
                        "mod installed, note blocks go COMPLETELY SILENT (the mod remaps sound to "
                        "a qzpno: custom event with no resourcepack to back it); without the mod, "
                        "you get vanilla note-block timbres. Only use this if the target profile "
                        "already has a matching qzpno_mv.zip installed and enabled.")
    p.add_argument("--rp-out", default=DEFAULT_RP_OUT, dest="rp_out",
                   help="LEGACY / compat only. The resourcepack is always staged into the "
                        "workspace dist/ (as qzpno_mv.zip) for the native DEPLOY_TO_GAME.bat; "
                        "this value no longer controls where the pack goes. It is now used "
                        "solely to help infer the profile dir when --profile-dir is omitted.")
    p.add_argument("--profile-dir", default=None, dest="profile_dir",
                   help="Minecraft profile root, e.g. .../ModrinthApp/profiles/Fabric 1.21.8. "
                        "Usually inferred from --world-dir <profile>/saves/<world>/datapacks. "
                        "Baked into the generated DEPLOY_TO_GAME.bat.")
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
                   help="do not stage the RedPiano jar / Fabric API into the bundle (datapack "
                        "+ resourcepack only). Use only when the mods are already installed.")
    p.add_argument("--fabric-api-jar", default="auto", dest="fabric_api_jar",
                   help="matching Fabric API jar to install, or 'auto' to reuse/download "
                        "a build for --mc-version (default auto).")
    p.add_argument("--no-download-fabric-api", action="store_true", dest="no_download_fabric_api",
                   help="do not use Modrinth to fetch Fabric API when it is missing.")
    p.add_argument("--skip-fabric-api-check", action="store_true", dest="skip_fabric_api_check",
                   help="explicitly skip Fabric API install/check. This is not a ready runtime.")
    # deploy bundle
    p.add_argument("--dist", default="dist", dest="dist",
                   help="workspace staging dir for the deploy bundle (default 'dist'). Must be "
                        "inside the real project folder — that is the ONE path a sandboxed agent "
                        "can write to reliably.")
    p.add_argument("--install-now", action="store_true", dest="install_now",
                   help="NATIVE HOSTS ONLY: copy the staged artifacts straight into the profile "
                        "now (skips the double-click .bat). Do NOT use inside a Trae/sandbox "
                        "runtime — it would install into the VMCache mirror.")
    args = p.parse_args(argv)

    # 0. fail fast on unsupported version BEFORE running anything.
    try:
        profile = get_version_profile(args.mc_version)
        assert_build_supported(profile)
    except RedPianoError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2

    # fail fast when --world-dir clearly points at the save/world folder itself
    # instead of saves/<world>/datapacks underneath it — it is REQUIRED here and
    # gets baked straight into the generated DEPLOY_TO_GAME.bat, so a wrong folder
    # silently corrupts the whole install path.
    _world_base = os.path.basename(os.path.normpath(args.world_dir))
    if _world_base.lower() != "datapacks":
        sys.stderr.write(
            f"error: --world-dir '{args.world_dir}' 看起来指到了存档目录本身，--world-dir "
            f"必须指到 saves/<世界>/datapacks 这一层 (got a folder named '{_world_base}', "
            f"expected 'datapacks')\n"
        )
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
    world_datapacks_dir = args.world_dir

    # Hard error only if a target LITERALLY resolves under the VMCache mirror (someone
    # pasted a VMCache path). We no longer try to *detect* the sandbox and refuse — that
    # was unreliable (the sandbox is transparent from inside) and left the agent with no
    # working path. Instead we always build in the workspace and emit a native installer.
    for pth in (profile_dir, world_datapacks_dir):
        if _under_trae_vmcache(pth):
            sys.stderr.write(
                f"error: target {pth} is under the Trae VMCache mirror, not the real "
                "profile. Pass the real C:\\Minecraft\\... path instead.\n")
            return 2

    if args.install_now and not (profile_dir and world_datapacks_dir):
        sys.stderr.write(
            "error: --install-now needs both a real --world-dir and a --profile-dir "
            "(or an inferable one).\n")
        return 2

    mod_dir = args.mod_dir or _default_mod_dir()
    dist_dir = os.path.abspath(args.dist)
    mods_stage = os.path.join(dist_dir, "mods")
    # Fail fast (before the expensive builds) if dist/ is under VMCache or not writable.
    if _under_trae_vmcache(dist_dir):
        sys.stderr.write(
            f"error: --dist {dist_dir} is under the Trae VMCache mirror. Stage into the real "
            "project workspace so the native DEPLOY_TO_GAME.bat can read it.\n")
        return 2
    try:
        os.makedirs(dist_dir, exist_ok=True)
        _probe = os.path.join(dist_dir, ".write_test")
        with open(_probe, "w") as _f:
            _f.write("ok")
        os.remove(_probe)
    except OSError as e:
        sys.stderr.write(f"error: cannot write to --dist {dist_dir}: {e}\n")
        return 2
    # Clear any receipt/token left by a PREVIOUS prepare_all NOW, up front — not only inside
    # build_deploy_bundle (step 6). Any of steps 1-5 can fail and return early before step 6
    # runs; a leftover receipt+token from a past successful deploy would then survive and make
    # `deploy_bundle.py --verify` falsely report THIS (failed) build as installed. build_deploy_bundle
    # still clears them again as a belt-and-suspenders safeguard.
    for _stale in (deploy_bundle.RECEIPT_NAME, ".deploy_token"):
        try:
            os.remove(os.path.join(dist_dir, _stale))
        except OSError:
            pass
    py = sys.executable
    here = _HERE
    pf = (f"min/max {profile.dp_format}" if profile.packmeta_shape == "minmax"
          else f"pack_format {profile.dp_format}")
    print("#" * 64)
    print(f"#  prepare_all — MC {args.mc_version}  (tier {profile.tier}; dp {pf}, rp {profile.rp_format})")
    print("#  build (workspace) -> stage dist/ -> emit native DEPLOY_TO_GAME.bat")
    print(f"#  dist    -> {dist_dir}")
    if world_datapacks_dir:
        print(f"#  world   -> {world_datapacks_dir}")
    if profile_dir:
        print(f"#  profile -> {profile_dir}")
    print("#" * 64)

    # 1. DATAPACK — build into the workspace only (NEVER copy into the profile here;
    #    from a sandbox that copy lands in the VMCache mirror and is invisible in-game).
    dp_argv = [py, os.path.join(here, "build_machine.py"),
               "--midi", args.midi, "--form", args.form, "--ns", args.ns,
               "--origin", str(args.origin[0]), str(args.origin[1]), str(args.origin[2]),
               "--mc-version", args.mc_version, "--out", args.out, "--staged-run"]
    if args.params:
        dp_argv += ["--params", args.params]
    if args.force_cap:
        dp_argv += ["--force-cap"]
    if not _run("datapack (build_machine.py)", dp_argv):
        return 1
    datapack_src = os.path.join(args.out, args.ns)

    # 2. RESOURCEPACK — build/copy the qzpno_mv.zip into the workspace dist/.
    rp_zip = None
    rp_stage = os.path.join(dist_dir, deploy_bundle.RP_ZIP_NAME)
    if args.samples_root:
        rp_argv = [py, os.path.join(here, "build_resourcepack.py"),
                   "--mc-version", args.mc_version, "--samples-root", args.samples_root,
                   "--out", rp_stage]
        if not _run("resourcepack (build_resourcepack.py)", rp_argv):
            return 1
        rp_zip = rp_stage
    elif args.prebuilt_rp:
        print("\n" + "=" * 64)
        print("  STEP: resourcepack (prebuilt copy)")
        print(f"  source: {args.prebuilt_rp} -> {rp_stage}")
        print("=" * 64)
        try:
            _copy_prebuilt_resourcepack(args.prebuilt_rp, rp_stage, profile)
        except RedPianoError as e:
            sys.stderr.write(f"error: {e}\n")
            return 2
        print(f"  copied -> {rp_stage}  ({os.path.getsize(rp_stage)//1024} KB)")
        rp_zip = rp_stage
    else:
        print("\n" + "-" * 64)
        print("  STEP: resourcepack SKIPPED (--skip-resourcepack). No qzpno_mv.zip staged.")
        print("        诚实后果: 装了 RedPiano 模组时，音符盒会【彻底静音】(模组把声音改成")
        print("        qzpno: 自定义事件，没有资源包=无音效); 只有【不装模组】时才是原版音色。")
        print("        仅当目标 profile 里已装好并启用了匹配的 qzpno_mv.zip 时才用本开关。")
        print("-" * 64)

    # 3. MOD BUILD-CONFIG (only meaningful if the mod source is present).
    #    STEP 3 rewrites mod/redpiano/gradle.properties + build.gradle in place. If the
    #    Gradle build (STEP 4) then fails for lack of a toolchain, that edit would be left
    #    behind polluting the mod source. So PROBE Gradle + JDK 21 FIRST (reusing STEP 4's
    #    own resolvers); if either is missing, skip BOTH steps 3 and 4 with a human note
    #    pointing at --prebuilt-mod-jar, and never touch the mod source files.
    #    (The --prebuilt-mod-jar / --skip-mod-build / --skip-mod-install paths already skip
    #    this whole block, so they never write to the mod source either.)
    resolved_gradle = None
    resolved_java_home = None
    resolved_java_detail = None
    want_build = (not args.skip_mod_install and not args.prebuilt_mod_jar
                  and not args.skip_mod_build and os.path.isdir(mod_dir))
    if want_build:
        resolved_gradle, gradle_detail = _resolve_gradle(args.gradle, mod_dir)
        resolved_java_home, resolved_java_detail = _resolve_jdk21(args.java_home)
        if not resolved_gradle or not resolved_java_home:
            print("\n" + "-" * 64)
            print("  STEP: mod build-config + jar SKIPPED — no Gradle/JDK 21 toolchain.")
            print(f"        gradle: {gradle_detail}")
            print(f"        jdk21 : {resolved_java_detail}")
            print("  未检测到 Gradle / JDK 21，跳过模组自编（未改动 mod 源文件）。请改用")
            print("  --prebuilt-mod-jar <redpiano jar>（scripts/fetch_binaries.py 可取随仓 jar），")
            print("  或安装 Gradle + JDK 21 后重跑。")
            print("-" * 64)
            want_build = False
        else:
            mb_argv = [py, os.path.join(here, "mod_build.py"),
                       "--mc-version", args.mc_version, "--write", "--mod-dir", mod_dir]
            if not _run("mod build-config (mod_build.py --write)", mb_argv):
                return 1

    # 4. MOD JAR — prefer a prebuilt jar (packaged bundles ship one; avoids needing
    #    Gradle/JDK inside a stripped sandbox). Fall back to a Gradle build if source
    #    is present. Result is a jar path in the workspace, later staged into dist/mods.
    built_jar = False
    mod_jar = None
    mod_jar_source = None
    if args.skip_mod_install:
        print("\n" + "-" * 64)
        print("  STEP: mod + Fabric API SKIPPED (--skip-mod-install).")
        print("  Bundle = datapack + resourcepack only; RedPiano must already be in mods/.")
        print("-" * 64)
    elif args.prebuilt_mod_jar:
        if not os.path.isfile(args.prebuilt_mod_jar):
            sys.stderr.write(f"error: --prebuilt-mod-jar not found: {args.prebuilt_mod_jar}\n")
            return 2
        mod_jar = os.path.abspath(os.path.normpath(args.prebuilt_mod_jar))
        mod_jar_source = "prebuilt"
    elif args.skip_mod_build:
        print("\n" + "-" * 64)
        print("  STEP: mod jar SKIPPED BY REQUEST (--skip-mod-build).")
        print("  Not a ready runtime unless a matching RedPiano jar is already in mods/.")
        print("-" * 64)
    elif not want_build:
        # STEP 3 already printed the "no Gradle/JDK 21 — use --prebuilt-mod-jar" note and
        # left the mod source untouched. Nothing to build; leave mod_jar unset so the
        # honest summary shows the jar as NOT provided.
        pass
    else:
        # Toolchain was probed + confirmed available before STEP 3; reuse it (do NOT
        # re-resolve — STEP 3 only wrote the build config because these were present).
        gradle = resolved_gradle
        java_home = resolved_java_home
        print(f"[auto] using Gradle: {gradle}")
        print(f"[auto] using JDK 21: {resolved_java_detail}")
        env = dict(os.environ)
        env["JAVA_HOME"] = java_home
        env["PATH"] = os.path.join(java_home, "bin") + os.pathsep + env.get("PATH", "")
        if not _run(f"mod jar ({os.path.basename(gradle)} build)",
                    [gradle, "build"], cwd=mod_dir, env=env):
            return 1
        mod_jar = _latest_redpiano_jar(mod_dir)
        if not mod_jar:
            sys.stderr.write(
                f"error: Gradle build finished but no redpiano jar was found under "
                f"{os.path.join(mod_dir, 'build', 'libs')}\n")
            return 1
        built_jar = True
        mod_jar_source = "built"

    # 5. FABRIC API — resolve a matching build into the workspace dist/mods.
    fabric_api_path = None
    if not args.skip_mod_install and not args.skip_fabric_api_check and mod_jar:
        if not _is_auto(args.fabric_api_jar):
            if not os.path.isfile(args.fabric_api_jar):
                sys.stderr.write(f"error: --fabric-api-jar not found: {args.fabric_api_jar}\n")
                return 2
            if not _fabric_api_matches(args.fabric_api_jar, args.mc_version):
                sys.stderr.write(
                    f"error: --fabric-api-jar is not a Fabric API build for "
                    f"+{args.mc_version}: {args.fabric_api_jar}\n")
                return 2
            fabric_api_path = args.fabric_api_jar
        else:
            fabric_api_path = _find_fabric_api(mods_stage, args.mc_version)
            if not fabric_api_path and not args.no_download_fabric_api:
                print("[auto] Fabric API missing; downloading matching build from Modrinth...")
                try:
                    fabric_api_path = _download_fabric_api(mods_stage, args.mc_version)
                except RedPianoError as e:
                    sys.stderr.write(f"error: {e}\n")
                    return 2
            if not fabric_api_path:
                sys.stderr.write(
                    f"error: no matching Fabric API +{args.mc_version}. Pass "
                    "--fabric-api-jar <jar> or allow the Modrinth download.\n")
                return 2

    mod_jars = [j for j in (mod_jar, fabric_api_path) if j]

    # 6. STAGE + emit the native deploy bundle (or install now on a real host).
    token = deploy_bundle.new_token()
    try:
        result = deploy_bundle.build_deploy_bundle(
            dist_dir, ns=args.ns, world_datapacks_dir=world_datapacks_dir,
            profile_dir=profile_dir, mc_version=args.mc_version,
            datapack_src_dir=datapack_src, rp_zip=rp_zip, mod_jars=mod_jars, token=token)
    except RuntimeGuardError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2
    except (OSError, FileNotFoundError) as e:
        sys.stderr.write(f"error: could not stage deploy bundle: {e}\n")
        return 1

    installed = False
    if args.install_now:
        print("\n" + "=" * 64)
        print("  STEP: --install-now (native host) — copying into the real profile")
        print("=" * 64)
        try:
            receipt, copied = deploy_bundle.install_now(
                dist_dir, world_datapacks_dir=world_datapacks_dir, profile_dir=profile_dir,
                ns=args.ns, manifest=result["manifest"], token=token, mc_version=args.mc_version)
        except RuntimeGuardError as e:
            sys.stderr.write(f"error: {e}\n")
            return 3
        except OSError as e:
            sys.stderr.write(f"error: --install-now copy failed: {e}\n")
            return 1
        installed = True
        for c in copied:
            print(f"  [x] {c}")
        print(f"  receipt -> {receipt}")

    # ── honest summary ──
    print("\n" + "#" * 64)
    print(f"#  BUILT for MC {args.mc_version}  ->  dist: {dist_dir}")
    print(f"#    [x] datapack      {args.ns}  ({pf})")
    print(f"#    [{'x' if rp_zip else ' '}] resourcepack  "
          + (f"qzpno_mv.zip (rp {profile.rp_format})" if rp_zip else "SKIPPED"))
    print(f"#    [{'x' if mod_jar else ' '}] mod jar       "
          + (f"{mod_jar_source} ({os.path.basename(mod_jar)})" if mod_jar else "NOT provided"))
    print(f"#    [{'x' if fabric_api_path else ' '}] fabric api    "
          + (os.path.basename(fabric_api_path) if fabric_api_path else "—"))
    print("#")
    if installed:
        print("#  ✓ INSTALLED NOW (native host): receipt written. Restart MC / /reload,")
        print(f"#    /tick rate 80 (manual), enable qzpno_mv, /function {args.ns}:setup, [play].")
    else:
        print("#  ⚠ NOT IN THE GAME YET. From a sandbox, writing to C:\\Minecraft goes to a")
        print("#    VMCache mirror the game never reads. The ONE reliable install step is:")
        print(f"#      >>> the user DOUBLE-CLICKS  {result['bat']}  <<<")
        print("#      (in Windows Explorer — a native process, outside the sandbox).")
        print("#    It copies datapack+resourcepack+mods into the real profile, enables the")
        print(f"#    pack, and writes {deploy_bundle.RECEIPT_NAME} back here on success.")
        print("#    Do NOT run the .bat yourself and do NOT claim it's in-game until that")
        print(f"#    receipt exists — check with:  python scripts/deploy_bundle.py --verify {dist_dir}")
        print(f"#    or read {os.path.join(dist_dir, deploy_bundle.RECEIPT_NAME)}.")
    print("#    Then in-game: restart MC (if mods changed) -> /reload -> /tick rate 80")
    print(f"#    (TYPE MANUALLY) -> enable qzpno_mv -> /function {args.ns}:setup -> [play].")
    print("#    LISTEN ONCE before trusting a recompiled mixin.")
    print("#" * 64)
    return 0


def main(argv=None):
    try:
        return _run_main(argv)
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
