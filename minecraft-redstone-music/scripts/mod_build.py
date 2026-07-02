# -*- coding: utf-8 -*-
"""mod_build.py — version-driven RedPiano mod-build helper.

The RedPiano Fabric mod is the ONE version surface the Python pipeline cannot fully
auto-adapt: a mixin binds to internal NoteBlock bytecode, so every target version needs
a recompiled jar AND one in-game listen (a recompiled-but-unverified jar is a footgun).
What this helper DOES do is turn "recompile the mod" from a research task into a command:

  * PRINT the verified toolchain numbers (fabric-loom / fabric-loader / fabric-api / Java /
    mappings) + the porting tier for a target MC version — sourced from the cross-checked
    Fabric matrix (fabricmc.net + meta API), with the 1.21.8 anchor matching build.gradle.
  * optionally `--write` those numbers into mod/redpiano/gradle.properties + the
    fabric-loom plugin-version line in build.gradle, so the next `gradlew build` targets
    the chosen version. It does NOT run gradle, and does NOT widen the tested `minecraft`
    range in fabric.mod.json unless you pass --set-mc-range (and even then it warns).

Supported (green) band: 1.21..1.21.10 — number-only retarget (no Java source edits; the
1.21.x scoreboard/sound API the mod uses compiles across the whole line). Below 1.21 the
mod needs a real Java source-port (the <1.21 scoreboard config API) + Java 17 at 1.20.4 —
out of this skill's auto scope; this helper prints that checklist instead of writing.

It can also VERIFY a freshly-built jar before you trust it: `--check-jar <jar>` guards
against a "hand-written fabric-api stub" build (which compiles but crashes at startup with
NoSuchFieldError) by inspecting fabric.mod.json + disassembling the ServerTickEvents field
reference. See check_jar() below.

Pure stdlib. Examples:
  python scripts/mod_build.py --mc-version 1.21.9            # print the toolchain
  python scripts/mod_build.py --mc-version 1.21.9 --write    # apply to the mod build files
  python scripts/mod_build.py --mc-version 1.21.8 \
      --check-jar mod/redpiano/build/libs/redpiano-1.0.0.jar  # verify a built jar
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import zipfile
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from redpiano_core import RedPianoError, get_version_profile  # noqa: E402

MAPPINGS = "officialMojang"   # constant — staying on Mojang official keeps ports number-only

# Verified Fabric toolchain per MC version (cross-checked fabricmc.net + meta API, June 2026).
# loader is forward-compatible (a recent stable runs older MC), so the project anchor 0.17.3
# is used across the whole green band (>=0.17.0 also satisfies 1.21.9's bundled MixinExtras).
# fabric_api is the exact "+<mc>" build. loom must be an EXACT published plugin version —
# Gradle cannot resolve an era label like "1.10" (bit the 1.21.7 rebuild; 1.10.5 is
# build-proven for 1.21.5..1.21.8). The 1.7/1.8/1.9/1.11 rows are still era-level: look up
# the exact patch on fabricmc.net before a --write build there. java is 21 across green.
# port_tier: "numbers" = pure number bump; "verify:*" = number bump + one genSources check.
MOD_TOOLCHAIN = {
    "1.21":   {"loom": "1.7",    "loader": "0.17.3", "fabric_api": "0.102.0+1.21",   "java": 21, "port_tier": "numbers", "notes": ""},
    "1.21.1": {"loom": "1.7",    "loader": "0.17.3", "fabric_api": "0.116.12+1.21.1", "java": 21, "port_tier": "numbers", "notes": "LTS-ish; fabric-api still backported"},
    "1.21.2": {"loom": "1.8",    "loader": "0.17.3", "fabric_api": "0.106.1+1.21.2",  "java": 21, "port_tier": "numbers", "notes": ""},
    "1.21.3": {"loom": "1.8",    "loader": "0.17.3", "fabric_api": "0.114.1+1.21.3",  "java": 21, "port_tier": "numbers", "notes": ""},
    "1.21.4": {"loom": "1.9",    "loader": "0.17.3", "fabric_api": "0.119.4+1.21.4",  "java": 21, "port_tier": "numbers", "notes": ""},
    "1.21.5": {"loom": "1.10.5", "loader": "0.17.3", "fabric_api": "0.128.2+1.21.5",  "java": 21, "port_tier": "numbers", "notes": "loom 1.10 era needs Gradle 8.12+"},
    "1.21.6": {"loom": "1.10.5", "loader": "0.17.3", "fabric_api": "0.128.2+1.21.6",  "java": 21, "port_tier": "numbers", "notes": ""},
    "1.21.7": {"loom": "1.10.5", "loader": "0.17.3", "fabric_api": "0.129.0+1.21.7",  "java": 21, "port_tier": "numbers", "notes": "jar rebuilt+--check-jar verified 2026-07-02 (listen pending)"},
    "1.21.8": {"loom": "1.10.5", "loader": "0.17.3", "fabric_api": "0.136.1+1.21.8",  "java": 21, "port_tier": "numbers", "notes": "ANCHOR — matches build.gradle byte-for-byte"},
    "1.21.9": {"loom": "1.11",   "loader": "0.17.3", "fabric_api": "0.134.1+1.21.9",  "java": 21, "port_tier": "verify:getEntityWorld",
               "notes": "yarn getWorld->getEntityWorld; under Mojang mappings verify the equivalent in genSources. fabric-api resource-loader rework."},
    "1.21.10": {"loom": "1.11",  "loader": "0.17.3", "fabric_api": "0.138.4+1.21.10", "java": 21, "port_tier": "verify:getEntityWorld",
               "notes": "non-breaking sibling of 1.21.9 (same loom 1.11 era). Same getWorld->getEntityWorld verify note."},
}


def default_mod_dir():
    """Best-guess mod dir: <repo>/mod/redpiano (one level above the skill folder). The
    mod ships separately from the skill, so this may not exist in a packaged copy."""
    return os.path.normpath(os.path.join(_HERE, "..", "..", "mod", "redpiano"))


def toolchain_for(mc_version):
    """Return the toolchain dict for a green-band version, or raise RedPianoError with a
    tier-specific explanation for yellow/red (out of the mod's auto scope)."""
    profile = get_version_profile(mc_version)  # also enforces the /tick rate floor (red)
    tc = MOD_TOOLCHAIN.get(mc_version)
    if tc is None:
        if profile.tier == "yellow":
            raise RedPianoError(
                f"mc_version {mc_version} (yellow): the mod needs a real Java source-port "
                f"below 1.21 — rewrite RedPiano.java readCfg() from the 1.21 "
                f"ScoreHolder/ReadOnlyScoreInfo scoreboard API to the older "
                f"Scoreboard.getOrCreatePlayerScore()/Score API, and use Java 17 at 1.20.4. "
                f"This is out of the skill's auto scope (see docs/MOD_ARCHITECTURE.md §6). "
                f"No number-only toolchain row exists."
            )
        raise RedPianoError(
            f"mc_version {mc_version}: no mod toolchain row (supported mod band is "
            f"1.21..1.21.10). See docs/MOD_ARCHITECTURE.md §6 to port further."
        )
    return profile, tc


def _print(mc_version):
    profile, tc = toolchain_for(mc_version)
    print(f"=== RedPiano mod toolchain — MC {mc_version} (tier {profile.tier}) ===")
    print(f"  fabric-loom   : {tc['loom']}     (plugins{{}} block in build.gradle)")
    print(f"  fabric-loader : {tc['loader']}")
    print(f"  fabric-api    : {tc['fabric_api']}")
    print(f"  java          : {tc['java']}")
    print(f"  mappings      : {MAPPINGS} (loom.officialMojangMappings())")
    print(f"  port tier     : {tc['port_tier']}")
    if tc["notes"]:
        print(f"  notes         : {tc['notes']}")
    if tc["port_tier"].startswith("verify:"):
        print(f"  ! verify '{tc['port_tier'].split(':',1)[1]}' in Loom genSources before trusting the jar.")
    print("")
    print("  Apply to the mod build files:  add --write")
    print("  Then build (no wrapper committed — see MOD_ARCHITECTURE.md §6.3):")
    print("    cd mod/redpiano && JAVA_HOME=<jdk-%d> <gradle>/bin/gradle.bat build" % tc["java"])
    print("  Jar -> mod/redpiano/build/libs/redpiano-1.0.0.jar  (verify mtime/size changed).")
    print("  IMPORTANT: a recompiled jar still needs ONE in-game listen — the mixin binds")
    print("  to internal NoteBlock bytecode, so only widen fabric.mod.json to versions you")
    print("  actually tested (this helper will not widen it for you unless --set-mc-range).")


def _sub_line(text, pattern, replacement, label):
    new, n = re.subn(pattern, replacement, text)
    if n == 0:
        raise RedPianoError(f"could not find {label} to update (pattern: {pattern!r})")
    return new


def _write(mc_version, mod_dir, set_mc_range):
    profile, tc = toolchain_for(mc_version)
    gp = os.path.join(mod_dir, "gradle.properties")
    bg = os.path.join(mod_dir, "build.gradle")
    if not (os.path.isfile(gp) and os.path.isfile(bg)):
        raise RedPianoError(
            f"mod build files not found under {mod_dir} (looked for gradle.properties + "
            f"build.gradle). The mod ships separately from the skill — pass --mod-dir."
        )
    changed = []

    # gradle.properties: minecraft/loader/fabric/java version props (per-line).
    gp_text = open(gp, encoding="utf-8").read()
    gp_text = _sub_line(gp_text, r"(?m)^minecraft_version=.*$", f"minecraft_version={mc_version}", "minecraft_version")
    gp_text = _sub_line(gp_text, r"(?m)^loader_version=.*$",    f"loader_version={tc['loader']}", "loader_version")
    gp_text = _sub_line(gp_text, r"(?m)^fabric_version=.*$",    f"fabric_version={tc['fabric_api']}", "fabric_version")
    gp_text = _sub_line(gp_text, r"(?m)^java_version=.*$",      f"java_version={tc['java']}", "java_version")
    open(gp, "w", encoding="utf-8", newline="\n").write(gp_text)
    changed.append("gradle.properties (minecraft/loader/fabric/java)")

    # build.gradle: the fabric-loom plugin version line.
    bg_text = open(bg, encoding="utf-8").read()
    bg_text = _sub_line(bg_text,
                        r"(id 'fabric-loom' version ')[^']*(')",
                        lambda m: m.group(1) + tc["loom"] + m.group(2),
                        "fabric-loom plugin version")
    open(bg, "w", encoding="utf-8", newline="\n").write(bg_text)
    changed.append(f"build.gradle (fabric-loom {tc['loom']})")

    # fabric.mod.json minecraft range — ONLY with explicit opt-in, and warn.
    fmj = os.path.join(mod_dir, "src", "main", "resources", "fabric.mod.json")
    if set_mc_range and os.path.isfile(fmj):
        fmj_text = open(fmj, encoding="utf-8").read()
        fmj_text = _sub_line(fmj_text,
                             r'("minecraft":\s*")[^"]*(")',
                             lambda m: m.group(1) + f"~{mc_version}" + m.group(2),
                             "fabric.mod.json minecraft range")
        open(fmj, "w", encoding="utf-8", newline="\n").write(fmj_text)
        changed.append(f"fabric.mod.json (minecraft ~{mc_version})")

    return profile, tc, changed


# --- --check-jar: guard against a "hand-written fabric-api stub" jar -----------------
# Background (the June-2026 GLM footgun): in the sandbox, gradle sometimes could NOT reach
# maven.fabricmc.net, and a build that hand-writes a local fabric-api STUB compiles fine
# but ships a jar whose ServerTickEvents.END_SERVER_TICK field points at a *nested-class*
# Event (descriptor `LServerTickEvents$Event;`) instead of the real top-level
# `Lnet/fabricmc/fabric/api/event/Event;`. That jar loads then crashes at startup with
# `NoSuchFieldError END_SERVER_TICK`. Gradle succeeds, mtime/size change, so the only tell
# was the in-game crash. --check-jar catches it before the game ever launches.

# The one field reference that distinguishes a real fabric-api from a stub.
_STE_OWNER = "net/fabricmc/fabric/api/event/lifecycle/v1/ServerTickEvents"
_STE_FIELD = "END_SERVER_TICK"
_STE_GOOD_DESC = "Lnet/fabricmc/fabric/api/event/Event;"  # real top-level Event
_REDPIANO_CLASS = "com/redpiano/RedPiano.class"           # the entrypoint that registers it


def _find_javap():
    """Locate javap via JAVA_HOME then PATH. Returns a path or None (own small probe — do
    not import prepare_all here, that's not this helper's file)."""
    exe = "javap.exe" if os.name == "nt" else "javap"
    jh = os.environ.get("JAVA_HOME")
    if jh:
        cand = os.path.join(jh, "bin", exe)
        if os.path.isfile(cand):
            return cand
    return shutil.which("javap")


def _check_fabric_mod_json(jar, mc_version):
    """(a) Read fabric.mod.json from the jar: id must be 'redpiano', and the declared
    `depends.minecraft` range must be compatible with --mc-version. Returns a list of
    problem strings (empty = ok)."""
    problems = []
    try:
        with zipfile.ZipFile(jar) as z:
            with z.open("fabric.mod.json") as f:
                fmj = json.load(f)
    except KeyError:
        return [f"{os.path.basename(jar)}: no fabric.mod.json inside (not a Fabric mod jar?)"]
    except (zipfile.BadZipFile, json.JSONDecodeError, OSError) as e:
        return [f"{os.path.basename(jar)}: cannot read fabric.mod.json ({e})"]

    if fmj.get("id") != "redpiano":
        problems.append(f"fabric.mod.json id={fmj.get('id')!r}, expected 'redpiano'")

    mc_dep = (fmj.get("depends") or {}).get("minecraft")
    if mc_dep is None:
        problems.append("fabric.mod.json depends.minecraft missing")
    elif not _mc_range_matches(mc_dep, mc_version):
        problems.append(f"fabric.mod.json depends.minecraft={mc_dep!r} does not cover "
                        f"--mc-version {mc_version} (rebuild/--set-mc-range for this target)")
    return problems


def _mc_range_matches(dep, mc_version):
    """Tiny compatibility check for the fabric depends.minecraft form the mod actually
    uses. Handles '*', an exact string, and the '~1.21.x' (same minor, patch >=) tilde
    range that --set-mc-range writes. Conservative: unknown syntax -> treat as matching so
    we never reject a valid-but-unusual range (id + bytecode are the real guards)."""
    dep = str(dep).strip()
    if dep in ("*", mc_version):
        return True
    if dep.startswith("~"):
        base = dep[1:]
        b, v = base.split("."), mc_version.split(".")
        # tilde on a.b.c pins a.b and allows patch >= c (Fabric's ~ semantics).
        if len(b) >= 2 and len(v) >= 2 and b[:2] == v[:2]:
            try:
                bp = int(b[2]) if len(b) > 2 else 0
                vp = int(v[2]) if len(v) > 2 else 0
                return vp >= bp
            except ValueError:
                return True
        return False
    if dep in (">=" + mc_version, mc_version + "+"):
        return True
    return True  # unknown syntax: don't false-reject


def _check_bytecode(jar, javap):
    """(b) javap-disassemble RedPiano.class and verify the ServerTickEvents.END_SERVER_TICK
    field reference uses the real top-level Event descriptor, not a nested stub one.
    Returns (problems, checked): checked=False means the class/ref wasn't found to inspect."""
    tmp = None
    try:
        # extract RedPiano.class to a temp dir so javap has a plain file to read.
        import tempfile
        tmp = tempfile.mkdtemp(prefix="rpcheck_")
        try:
            with zipfile.ZipFile(jar) as z:
                z.extract(_REDPIANO_CLASS, tmp)
        except KeyError:
            return ([f"{_REDPIANO_CLASS} not found in jar (entrypoint missing?)"], False)
        clsfile = os.path.join(tmp, *_REDPIANO_CLASS.split("/"))
        try:
            out = subprocess.run([javap, "-p", "-c", "-v", clsfile],
                                 capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            return ([f"javap failed to run on {_REDPIANO_CLASS}: {e}"], False)
        if out.returncode != 0:
            return ([f"javap exited {out.returncode} on {_REDPIANO_CLASS}: "
                     f"{(out.stderr or '').strip()[:200]}"], False)
        return _scan_javap(out.stdout)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def _scan_javap(text):
    """Parse javap -v output for the END_SERVER_TICK Fieldref and validate its descriptor.
    javap renders it as e.g.
      #36 = Fieldref  #13.#35  // net/.../ServerTickEvents.END_SERVER_TICK:Lnet/.../Event;
    Returns (problems, checked)."""
    # match the resolved '// owner.FIELD:descriptor' comment on a Fieldref line.
    pat = re.compile(r"Fieldref.*//\s*(\S+)\.%s:(\S+)" % re.escape(_STE_FIELD))
    for line in text.splitlines():
        m = pat.search(line)
        if not m:
            continue
        owner, desc = m.group(1), m.group(2)
        if desc != _STE_GOOD_DESC:
            return ([f"{_STE_FIELD} field descriptor is {desc!r} (owner {owner}), expected "
                     f"{_STE_GOOD_DESC!r} — this is the hand-written fabric-api STUB "
                     f"footgun (nested-class Event) that crashes at startup with "
                     f"NoSuchFieldError. Rebuild against the real maven.fabricmc.net "
                     f"fabric-api, do NOT hand-write a stub."], True)
        return ([], True)
    # RedPiano.class exists but never references END_SERVER_TICK: nothing to validate here.
    return ([], False)


def check_jar(jar, mc_version):
    """Verify a compiled RedPiano jar is not poisoned by a fake fabric-api stub, BEFORE the
    game launches. Three checks:
      (a) fabric.mod.json: id=='redpiano' and depends.minecraft covers --mc-version;
      (b) javap-disassemble RedPiano.class and require the ServerTickEvents.END_SERVER_TICK
          reference to use the real top-level `Lnet/fabricmc/fabric/api/event/Event;`
          descriptor (a stub uses a nested `LServerTickEvents$Event;` -> NoSuchFieldError);
      (c) if javap is unavailable, WARN 'bytecode NOT verified' rather than fake-green.
    Returns 0 (ok, possibly with an honest bytecode WARN) or 1 (a real problem)."""
    if not os.path.isfile(jar):
        print(f"error: jar not found: {jar}", file=sys.stderr)
        return 1

    print(f"=== check-jar {os.path.basename(jar)} (target MC {mc_version}) ===")
    problems = []

    # (a) manifest
    man_problems = _check_fabric_mod_json(jar, mc_version)
    problems += man_problems
    if not man_problems:
        print("  ok  fabric.mod.json: id=redpiano, minecraft range covers target")

    # (b)/(c) bytecode via javap
    javap = _find_javap()
    if javap is None:
        print("  WARN bytecode NOT verified — no javap on JAVA_HOME/PATH; cannot confirm "
              "the ServerTickEvents.END_SERVER_TICK descriptor is the real fabric-api "
              "(a stub jar would still crash at startup). Install a JDK to fully verify.")
    else:
        bc_problems, checked = _check_bytecode(jar, javap)
        problems += bc_problems
        if bc_problems:
            pass  # reported below
        elif checked:
            print(f"  ok  bytecode: END_SERVER_TICK -> {_STE_GOOD_DESC} (real fabric-api)")
        else:
            print("  WARN bytecode NOT verified — RedPiano.class did not reference "
                  "END_SERVER_TICK to inspect (entrypoint changed?); stub check skipped.")

    if problems:
        print("  --- FAILED ---")
        for p in problems:
            print(f"  ERROR {p}", file=sys.stderr)
        return 1
    print("  jar OK (still needs ONE in-game listen — bytecode-clean != mixin-correct).")
    return 0


def build_argparser():
    p = argparse.ArgumentParser(
        prog="mod_build.py",
        description="Print (or --write) the verified RedPiano mod toolchain for a target "
                    "MC version. Does not run gradle.")
    p.add_argument("--mc-version", default="1.21.8", dest="mc_version",
                   help="target Minecraft version (1.21..1.21.10; default 1.21.8).")
    p.add_argument("--write", action="store_true",
                   help="apply the numbers to mod/redpiano/gradle.properties + the "
                        "fabric-loom plugin line in build.gradle.")
    p.add_argument("--mod-dir", default=None, dest="mod_dir",
                   help="path to mod/redpiano (default: ../../mod/redpiano from here).")
    p.add_argument("--set-mc-range", action="store_true", dest="set_mc_range",
                   help="ALSO set fabric.mod.json minecraft range to ~<version>. Only do "
                        "this for a version you have actually tested in-game.")
    p.add_argument("--check-jar", default=None, dest="check_jar", metavar="JAR",
                   help="verify a built jar (fabric.mod.json + bytecode) is not a "
                        "fake-fabric-api stub before trusting it. Exits 1 on a real "
                        "problem, 0 if clean (or honestly WARNs when javap is absent).")
    return p


def main(argv=None):
    args = build_argparser().parse_args(argv)
    if args.check_jar:
        # jar verification is standalone (no toolchain print/write); returns 0/1.
        return check_jar(args.check_jar, args.mc_version)
    try:
        if args.write:
            mod_dir = args.mod_dir or default_mod_dir()
            profile, tc, changed = _write(args.mc_version, mod_dir, args.set_mc_range)
            print(f"=== applied RedPiano mod toolchain — MC {args.mc_version} (tier {profile.tier}) ===")
            for c in changed:
                print(f"  updated: {c}")
            if not args.set_mc_range:
                print("  (fabric.mod.json minecraft range left as-is — pass --set-mc-range "
                      "once you've tested this version in-game.)")
            print(f"  next: cd {mod_dir} && <gradle> build  (JDK {tc['java']}); then a full "
                  f"MC restart + one in-game listen.")
        else:
            _print(args.mc_version)
    except RedPianoError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if "--selftest" in sys.argv:
        # toolchain rows resolve for the whole green band; yellow/red raise cleanly.
        for v in ("1.21", "1.21.4", "1.21.5", "1.21.8", "1.21.9", "1.21.10"):
            prof, tc = toolchain_for(v)
            assert tc["fabric_api"].endswith("+" + v), (v, tc)
            assert prof.tier == "green"
        assert MOD_TOOLCHAIN["1.21.8"]["fabric_api"] == "0.136.1+1.21.8"
        for v, needle in (("1.20.4", "source-port"), ("1.20.2", "tick rate")):
            try:
                toolchain_for(v)
                raise AssertionError(f"{v} should have raised")
            except RedPianoError as e:
                assert needle in str(e), (v, str(e))
        print("ok: green-band toolchain rows resolve; yellow/red raise with reason")

        # --check-jar (a) fabric.mod.json path + (c) javap-missing WARN path, via a
        # constructed minimal zip (no real jar / gradle needed for the self-test).
        import tempfile
        # depends.minecraft range matcher
        assert _mc_range_matches("*", "1.21.8")
        assert _mc_range_matches("~1.21.8", "1.21.8")
        assert _mc_range_matches("~1.21.1", "1.21.8")      # same minor, patch >=
        assert not _mc_range_matches("~1.21.9", "1.21.8")  # patch too high
        assert not _mc_range_matches("~1.20.4", "1.21.8")  # different minor
        # javap Fieldref scanner: good vs stub descriptor
        good = ("  #36 = Fieldref  #13.#35  // net/fabricmc/fabric/api/event/lifecycle/"
                "v1/ServerTickEvents.END_SERVER_TICK:Lnet/fabricmc/fabric/api/event/Event;")
        assert _scan_javap(good) == ([], True), _scan_javap(good)
        stub = ("  #36 = Fieldref  #13.#35  // net/fabricmc/fabric/api/event/lifecycle/"
                "v1/ServerTickEvents.END_SERVER_TICK:LServerTickEvents$Event;")
        prob, checked = _scan_javap(stub)
        assert checked and prob and "stub" in prob[0].lower(), (prob, checked)
        assert _scan_javap("no fieldref here") == ([], False)
        with tempfile.TemporaryDirectory() as td:
            # good manifest -> no manifest problems
            okjar = os.path.join(td, "ok.jar")
            with zipfile.ZipFile(okjar, "w") as z:
                z.writestr("fabric.mod.json", json.dumps(
                    {"id": "redpiano", "depends": {"minecraft": "~1.21.8"}}))
            assert _check_fabric_mod_json(okjar, "1.21.8") == []
            # wrong id + non-covering range -> two problems
            badjar = os.path.join(td, "bad.jar")
            with zipfile.ZipFile(badjar, "w") as z:
                z.writestr("fabric.mod.json", json.dumps(
                    {"id": "notredpiano", "depends": {"minecraft": "~1.20.4"}}))
            bp = _check_fabric_mod_json(badjar, "1.21.8")
            assert any("id=" in p for p in bp) and any("minecraft" in p for p in bp), bp
            # no fabric.mod.json at all
            emptyjar = os.path.join(td, "empty.jar")
            with zipfile.ZipFile(emptyjar, "w") as z:
                z.writestr("readme.txt", "x")
            assert _check_fabric_mod_json(emptyjar, "1.21.8"), "missing fmj should problem"
        print("ok: --check-jar fabric.mod.json (id/range) + javap descriptor scan")
        print("mod_build self-test PASSED")
        sys.exit(0)
    sys.exit(main())
