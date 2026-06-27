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

Supported (green) band: 1.21..1.21.9 — number-only retarget (no Java source edits; the
1.21.x scoreboard/sound API the mod uses compiles across the whole line). Below 1.21 the
mod needs a real Java source-port (the <1.21 scoreboard config API) + Java 17 at 1.20.4 —
out of this skill's auto scope; this helper prints that checklist instead of writing.

Pure stdlib. Examples:
  python scripts/mod_build.py --mc-version 1.21.9            # print the toolchain
  python scripts/mod_build.py --mc-version 1.21.9 --write    # apply to the mod build files
"""

import argparse
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from redpiano_core import RedPianoError, get_version_profile  # noqa: E402

MAPPINGS = "officialMojang"   # constant — staying on Mojang official keeps ports number-only

# Verified Fabric toolchain per MC version (cross-checked fabricmc.net + meta API, June 2026).
# loader is forward-compatible (a recent stable runs older MC), so the project anchor 0.17.3
# is used across the whole green band (>=0.17.0 also satisfies 1.21.9's bundled MixinExtras).
# fabric_api is the exact "+<mc>" build. loom must match the MC era. java is 21 across green.
# port_tier: "numbers" = pure number bump; "verify:*" = number bump + one genSources check.
MOD_TOOLCHAIN = {
    "1.21":   {"loom": "1.7",    "loader": "0.17.3", "fabric_api": "0.102.0+1.21",   "java": 21, "port_tier": "numbers", "notes": ""},
    "1.21.1": {"loom": "1.7",    "loader": "0.17.3", "fabric_api": "0.116.12+1.21.1", "java": 21, "port_tier": "numbers", "notes": "LTS-ish; fabric-api still backported"},
    "1.21.2": {"loom": "1.8",    "loader": "0.17.3", "fabric_api": "0.106.1+1.21.2",  "java": 21, "port_tier": "numbers", "notes": ""},
    "1.21.3": {"loom": "1.8",    "loader": "0.17.3", "fabric_api": "0.114.1+1.21.3",  "java": 21, "port_tier": "numbers", "notes": ""},
    "1.21.4": {"loom": "1.9",    "loader": "0.17.3", "fabric_api": "0.119.4+1.21.4",  "java": 21, "port_tier": "numbers", "notes": ""},
    "1.21.5": {"loom": "1.10",   "loader": "0.17.3", "fabric_api": "0.128.2+1.21.5",  "java": 21, "port_tier": "numbers", "notes": "loom 1.10 needs Gradle 8.12"},
    "1.21.6": {"loom": "1.10",   "loader": "0.17.3", "fabric_api": "0.128.2+1.21.6",  "java": 21, "port_tier": "numbers", "notes": ""},
    "1.21.7": {"loom": "1.10",   "loader": "0.17.3", "fabric_api": "0.129.0+1.21.7",  "java": 21, "port_tier": "numbers", "notes": ""},
    "1.21.8": {"loom": "1.10.5", "loader": "0.17.3", "fabric_api": "0.136.1+1.21.8",  "java": 21, "port_tier": "numbers", "notes": "ANCHOR — matches build.gradle byte-for-byte"},
    "1.21.9": {"loom": "1.11",   "loader": "0.17.3", "fabric_api": "0.134.1+1.21.9",  "java": 21, "port_tier": "verify:getEntityWorld",
               "notes": "yarn getWorld->getEntityWorld; under Mojang mappings verify the equivalent in genSources. fabric-api resource-loader rework."},
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
            f"1.21..1.21.9). See docs/MOD_ARCHITECTURE.md §6 to port further."
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


def build_argparser():
    p = argparse.ArgumentParser(
        prog="mod_build.py",
        description="Print (or --write) the verified RedPiano mod toolchain for a target "
                    "MC version. Does not run gradle.")
    p.add_argument("--mc-version", default="1.21.8", dest="mc_version",
                   help="target Minecraft version (1.21..1.21.9; default 1.21.8).")
    p.add_argument("--write", action="store_true",
                   help="apply the numbers to mod/redpiano/gradle.properties + the "
                        "fabric-loom plugin line in build.gradle.")
    p.add_argument("--mod-dir", default=None, dest="mod_dir",
                   help="path to mod/redpiano (default: ../../mod/redpiano from here).")
    p.add_argument("--set-mc-range", action="store_true", dest="set_mc_range",
                   help="ALSO set fabric.mod.json minecraft range to ~<version>. Only do "
                        "this for a version you have actually tested in-game.")
    return p


def main(argv=None):
    args = build_argparser().parse_args(argv)
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
        for v in ("1.21", "1.21.4", "1.21.5", "1.21.8", "1.21.9"):
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
        print("mod_build self-test PASSED")
        sys.exit(0)
    sys.exit(main())
