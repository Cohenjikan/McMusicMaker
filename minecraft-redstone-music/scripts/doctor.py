# -*- coding: utf-8 -*-
"""doctor.py — one-shot "no sound" health check for a staged RedPiano deploy.

When a song "was built but nothing plays," the cause is almost always ONE of a short
list of install/version mismatches, not the datapack itself. This tool walks that list
against a real dist/ bundle + (optionally) the Minecraft profile/world, and prints a
numbered ✓/✗/SKIP checklist where every ✗ is followed by exactly how to fix it, ending
with a one-line VERDICT pointing at the first ✗.

The checks (each SKIPs with a reason when a needed path/param is missing):
  ① RECEIPT — reuse deploy_bundle.verify_receipt (token-checked). No receipt = the
     native DEPLOY_TO_GAME.bat never ran = NOTHING is actually in the game, so every
     later "read" of the profile is meaningless (it may be a VMCache mirror). This is
     the load-bearing check; the banner at the top says so.
  ② RESOURCEPACK PRESENT + FORMAT — <profile>/resourcepacks/qzpno_mv.zip exists and its
     pack.mcmeta rp format covers the target version's rp_format (VERSION_TABLE). A
     mismatched pack is silently disabled by MC -> total silence.
  ③ OPTIONS.TXT ENABLED — resourcePacks contains "file/qzpno_mv.zip" and it is NOT in
     incompatibleResourcePacks. A present-but-unselected pack = vanilla tones/silence.
  ④ MOD + FABRIC API — <profile>/mods has redpiano*.jar whose fabric.mod.json
     depends.minecraft covers the target (else Fabric refuses to load it), AND a
     fabric-api jar whose "+<version>" tail matches exactly.
  ⑤ DATAPACK ON DISK — <world>/<ns>/pack.mcmeta and
     data/<ns>/<function_folder>/setup.mcfunction exist (folder name is version-driven).
  ⑥ MANUAL REMINDERS — /tick rate 80 must be typed by hand; a changed mod jar needs a
     full MC restart (not /reload). Always shown (informational).

ns and mc-version are inferred from dist/ (receipt / .deploy_token / README / staged
datapack) when not passed. The tool is READ-ONLY: it never writes into the profile.

Exit: all green -> 0; any ✗ -> 1; usage error -> 2.
--selftest builds throwaway fixtures in a tempdir and asserts the exit codes + key
lines for the all-green case and three typical ✗ cases, printing SELFTEST OK.

Pure stdlib.
"""

import argparse
import json
import os
import sys
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from params_schema import RedPianoError  # noqa: E402
import redpiano_core as core  # noqa: E402
import deploy_bundle  # noqa: E402  (reuse verify_receipt + RP_ZIP_NAME)
from mod_build import _mc_range_matches  # noqa: E402  (fabric depends.minecraft matcher)

RP_ZIP = deploy_bundle.RP_ZIP_NAME   # "qzpno_mv.zip"
OPTIONS_ENTRY = "file/qzpno_mv.zip"

OK, BAD, SKIP = "✓", "✗", "SKIP"


class Check:
    """One checklist item: status (OK/BAD/SKIP), a headline, an optional fix line."""

    __slots__ = ("num", "status", "title", "fix")

    def __init__(self, num, status, title, fix=None):
        self.num = num
        self.status = status
        self.title = title
        self.fix = fix   # a "→ how to fix" line (BAD) or SKIP reason


# ─────────────────────────────────────────────────────────────────────────────
# dist/ inference — read whatever the bundle left behind (deploy_bundle layout).
# ─────────────────────────────────────────────────────────────────────────────

def _read_receipt_fields(dist_dir):
    """Parse key=value lines from DEPLOY_RECEIPT.txt if present. Returns {} if absent."""
    path = os.path.join(dist_dir, deploy_bundle.RECEIPT_NAME)
    if not os.path.isfile(path):
        return {}
    out = {}
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except OSError:
        return {}
    return out


def _infer_ns(dist_dir, explicit=None):
    """Infer the datapack namespace: explicit > receipt ns= > the single dir under
    dist/datapack/. Returns (ns_or_None, source_str)."""
    if explicit:
        return explicit, "--ns"
    rec = _read_receipt_fields(dist_dir)
    if rec.get("ns"):
        return rec["ns"], "receipt"
    dp = os.path.join(dist_dir, "datapack")
    if os.path.isdir(dp):
        subs = [d for d in os.listdir(dp) if os.path.isdir(os.path.join(dp, d))]
        if len(subs) == 1:
            return subs[0], "dist/datapack/"
    return None, "unknown"


def _infer_mc_version(dist_dir, explicit=None):
    """Infer the target MC version: explicit > receipt mc_version=. Returns
    (version_or_None, source_str). (The README/manifest do not carry it reliably.)"""
    if explicit:
        return explicit, "--mc-version"
    rec = _read_receipt_fields(dist_dir)
    if rec.get("mc_version"):
        return rec["mc_version"], "receipt"
    return None, "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# individual checks — each returns a Check.
# ─────────────────────────────────────────────────────────────────────────────

def check_receipt(dist_dir):
    """① reuse deploy_bundle.verify_receipt (token-checked)."""
    ok, info = deploy_bundle.verify_receipt(dist_dir)
    if ok:
        return Check(1, OK, f"deploy receipt present + token matches ({info})")
    # If the install scripts themselves are absent, the build never completed — pointing
    # the user at a nonexistent DEPLOY_TO_GAME.bat is a dead end. Tell them to re-run
    # prepare_all.py instead.
    bat = os.path.join(dist_dir, deploy_bundle.BAT_NAME)
    ps1 = os.path.join(dist_dir, deploy_bundle.PS1_NAME)
    if not os.path.isfile(bat) and not os.path.isfile(ps1):
        return Check(1, BAD,
                     "no valid deploy receipt — the bundle was NOT installed into the game",
                     f"→ 构建未完成（安装脚本 {deploy_bundle.BAT_NAME} 尚未生成），请重新完整"
                     f"运行 scripts/prepare_all.py 生成 dist/ 部署包，再由【用户本人】在资源"
                     f"管理器里双击 {deploy_bundle.BAT_NAME}。 Detail: {info}")
    return Check(1, BAD, "no valid deploy receipt — the bundle was NOT installed into the game",
                 f"→ the USER must double-click {bat} "
                 f"in Windows Explorer (native, not via an agent). "
                 f"Detail: {info}")


def _read_rp_format(zip_path):
    """(lo, hi) rp pack_format from a resourcepack zip's pack.mcmeta, or raise."""
    with zipfile.ZipFile(zip_path) as z:
        meta = json.loads(z.read("pack.mcmeta").decode("utf-8"))
    pack = meta.get("pack", {})
    if "pack_format" in pack:
        pf = int(pack["pack_format"])
        return pf, pf
    if "min_format" in pack and "max_format" in pack:
        return int(pack["min_format"]), int(pack["max_format"])
    raise RedPianoError("pack.mcmeta has no pack_format or min_format/max_format")


def check_resourcepack(profile_dir, profile):
    """② <profile>/resourcepacks/qzpno_mv.zip present + rp format covers target."""
    if not profile_dir:
        return Check(2, SKIP, "resourcepack file/format",
                     "no --profile-dir (and none inferable) — cannot inspect resourcepacks/")
    rp_path = os.path.join(profile_dir, "resourcepacks", RP_ZIP)
    if not os.path.isfile(rp_path):
        return Check(2, BAD, f"{RP_ZIP} missing from profile resourcepacks/",
                     f"→ install it: it must land at {rp_path}. Re-run "
                     f"scripts/prepare_all.py (stages it into dist/) and double-click "
                     f"DEPLOY_TO_GAME.bat, or copy qzpno_mv.zip there manually.")
    if profile is None:
        return Check(2, SKIP, f"{RP_ZIP} present but rp-format not checked",
                     "no --mc-version (and none inferable) — cannot compare rp_format")
    try:
        lo, hi = _read_rp_format(rp_path)
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError, RedPianoError) as e:
        return Check(2, BAD, f"{RP_ZIP} present but its pack.mcmeta is unreadable ({e})",
                     f"→ the zip is corrupt or not a resourcepack. Rebuild it with "
                     f"scripts/build_resourcepack.py --mc-version {profile.mc_version}.")
    if not (lo <= profile.rp_format <= hi):
        actual = str(lo) if lo == hi else f"{lo}..{hi}"
        return Check(2, BAD,
                     f"{RP_ZIP} rp format {actual} does NOT cover MC {profile.mc_version} "
                     f"(needs rp {profile.rp_format}) — MC silently disables it -> total silence",
                     f"→ rebuild for this version: python scripts/build_resourcepack.py "
                     f"--mc-version {profile.mc_version} --samples-root <dir> "
                     f"--out \"{rp_path}\"")
    return Check(2, OK, f"{RP_ZIP} present, rp format "
                        f"{lo if lo == hi else f'{lo}..{hi}'} covers MC {profile.mc_version} "
                        f"(rp {profile.rp_format})")


def _parse_options_packs(options_path):
    """Return (resource_packs list, incompatible list) from options.txt. Missing keys ->
    empty lists. Malformed JSON on a line -> empty list for that line (best-effort read)."""
    rp, inc = [], []
    for line in open(options_path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n").rstrip("\r")
        if line.startswith("resourcePacks:"):
            try:
                rp = json.loads(line[len("resourcePacks:"):] or "[]")
            except json.JSONDecodeError:
                rp = []
        elif line.startswith("incompatibleResourcePacks:"):
            try:
                inc = json.loads(line[len("incompatibleResourcePacks:"):] or "[]")
            except json.JSONDecodeError:
                inc = []
    return rp, inc


def check_options(profile_dir):
    """③ options.txt selects file/qzpno_mv.zip and it is not incompatible."""
    if not profile_dir:
        return Check(3, SKIP, "options.txt resource-pack selection",
                     "no --profile-dir (and none inferable) — cannot inspect options.txt")
    opt = os.path.join(profile_dir, "options.txt")
    if not os.path.isfile(opt):
        return Check(3, BAD, "options.txt not found in profile",
                     f"→ launch this Minecraft profile once (it creates {opt}), then "
                     f"enable qzpno_mv in Options -> Resource Packs (or re-run the "
                     f"native DEPLOY_TO_GAME.bat which selects it for you).")
    try:
        rp, inc = _parse_options_packs(opt)
    except OSError as e:
        return Check(3, BAD, f"options.txt unreadable ({e})",
                     f"→ check file permissions on {opt}.")
    if OPTIONS_ENTRY in inc:
        return Check(3, BAD, f"{OPTIONS_ENTRY} is in incompatibleResourcePacks -> disabled",
                     f"→ in-game Options -> Resource Packs, move qzpno_mv to the right "
                     f"(selected) side; or it will be re-enabled by DEPLOY_TO_GAME.bat. "
                     f"An 'incompatible' flag usually means an rp-format mismatch (see check ②).")
    if OPTIONS_ENTRY not in rp:
        return Check(3, BAD, f"{OPTIONS_ENTRY} not selected in options.txt resourcePacks",
                     f"→ enable qzpno_mv in Options -> Resource Packs (move it to the right "
                     f"side), or re-run the native DEPLOY_TO_GAME.bat (it selects it). "
                     f"Without this the note blocks play vanilla tones or nothing.")
    return Check(3, OK, f"{OPTIONS_ENTRY} selected in options.txt (and not incompatible)")


def _read_jar_json(jar_path, name):
    with zipfile.ZipFile(jar_path) as z:
        return json.loads(z.read(name).decode("utf-8"))


def _fabric_api_version_matches(jar_name, mc_version):
    """A fabric-api jar is named fabric-api-<x>+<mc>.jar; the MC tag is the segment after
    the LAST '+'. Match it as a whole segment (mirrors prepare_all._fabric_api_matches)."""
    name = jar_name.lower()
    if not name.endswith(".jar") or "fabric-api" not in name:
        return False
    stem = name[:-len(".jar")]
    return stem.endswith("+" + mc_version.lower())


def check_mods(profile_dir, profile):
    """④ redpiano*.jar (minecraft range covers target) + matching fabric-api jar."""
    if not profile_dir:
        return Check(4, SKIP, "mods (redpiano jar + fabric-api)",
                     "no --profile-dir (and none inferable) — cannot inspect mods/")
    mods_dir = os.path.join(profile_dir, "mods")
    if not os.path.isdir(mods_dir):
        # If BOTH mods/ and resourcepacks/ are missing, the profile dir looks empty —
        # almost always the --profile-dir points at the wrong place (multiple launchers /
        # version isolation), not that the mods just aren't installed yet.
        empty_note = ""
        if not os.path.isdir(os.path.join(profile_dir, "resourcepacks")):
            empty_note = (
                "  ℹ 该 profile 目录下 mods/ 和 resourcepacks/ 都不存在，看起来是空的——"
                "常见原因是电脑上有多个启动器（PCL2/HMCL/官方），或开了版本隔离；请确认 "
                "--profile-dir 指向游戏真正在用的目录（版本隔离时是 versions/<版本>/ 那层）。")
        return Check(4, BAD, "profile has no mods/ folder" + empty_note,
                     f"→ install the RedPiano jar + matching Fabric API into {mods_dir} "
                     f"(prepare_all.py stages both into dist/mods; DEPLOY_TO_GAME.bat copies them), "
                     f"then restart Minecraft.")
    all_entries = os.listdir(mods_dir)
    jars = [f for f in all_entries if f.lower().endswith(".jar")]
    redpiano = [f for f in jars if f.lower().startswith("redpiano")]

    # A neutral one-liner (never a ✗) when disabled/stale jars are lying around — that is
    # NORMAL and desirable after the deploy chain's "clean-then-install" renamed an old jar,
    # so we just note it (and remind the user they can be deleted once the new build is proven).
    disabled = [f for f in all_entries
                if f.lower().endswith((".disabled", ".stale"))]
    disabled_note = ""
    if disabled:
        disabled_note = ("  ℹ 另有 " + str(len(disabled)) +
                         " 个已禁用 jar(" + ", ".join(sorted(disabled)) +
                         ")，不影响加载；确认新版工作正常后可删除。")

    if not redpiano:
        return Check(4, BAD, "no redpiano*.jar in profile mods/" + disabled_note,
                     f"→ the RedPiano mod is required (it re-performs note blocks centered on "
                     f"each player). Install redpiano-*.jar into {mods_dir} and RESTART MC. "
                     f"Build/prepare it with scripts/prepare_all.py.")

    # DUPLICATE/RESIDUAL guard: more than one ACTIVE (.jar) redpiano*.jar means Fabric may load
    # the WRONG one by modid (the exact NoSuchFieldError crash class: an old -UNVERIFIED.jar left
    # behind next to the new build). Refuse until there is exactly one active redpiano jar.
    if len(redpiano) > 1:
        import time as _time
        rows = []
        for jar in sorted(redpiano):
            try:
                mt = os.path.getmtime(os.path.join(mods_dir, jar))
                mts = _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(mt))
            except OSError:
                mts = "?"
            rows.append(f"{jar} (mtime {mts})")
        newest = max(redpiano, key=lambda j: os.path.getmtime(os.path.join(mods_dir, j)))
        olds = [j for j in sorted(redpiano) if j != newest]
        fix_cmds = "; ".join(
            f'Rename-Item -LiteralPath "{os.path.join(mods_dir, j)}" -NewName "{j}.stale.disabled"'
            for j in olds)
        return Check(4, BAD,
                     f"发现 {len(redpiano)} 个活跃 redpiano*.jar — Fabric 可能按 modid 加载到"
                     f"旧毒 jar 而崩溃(NoSuchFieldError 一类): "
                     + "; ".join(rows) + disabled_note,
                     f"→ 只保留最新的 {newest}，把其余旧 jar 改名禁用（或删除）：{fix_cmds}  "
                     f"（改完重启 Minecraft；/reload 不够）。")

    # redpiano jar minecraft-range check (needs a target version)
    range_note = ""
    if profile is not None:
        covered = None
        for jar in redpiano:
            try:
                fmj = _read_jar_json(os.path.join(mods_dir, jar), "fabric.mod.json")
            except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
                continue
            dep = (fmj.get("depends") or {}).get("minecraft")
            if dep is None:
                continue
            if _mc_range_matches(dep, profile.mc_version):
                covered = jar
                break
        if covered is None:
            # gather what we saw for the fix message
            seen = []
            for jar in redpiano:
                try:
                    fmj = _read_jar_json(os.path.join(mods_dir, jar), "fabric.mod.json")
                    seen.append(f"{jar}:{(fmj.get('depends') or {}).get('minecraft')}")
                except Exception:
                    seen.append(f"{jar}:?")
            return Check(4, BAD,
                         f"redpiano jar present but its fabric.mod.json minecraft range does "
                         f"NOT cover MC {profile.mc_version} — Fabric will REFUSE to load it "
                         f"({'; '.join(seen)})" + disabled_note,
                         f"→ recompile the mod for {profile.mc_version} "
                         f"(python scripts/mod_build.py --mc-version {profile.mc_version} --write "
                         f"then gradle build; a mixin-recompiled jar needs one in-game listen), "
                         f"and only widen the range to versions you tested (--set-mc-range).")
        range_note = f", {covered} covers MC {profile.mc_version}"

    # fabric-api presence (+ version match when we know the target)
    if profile is not None:
        fab = [f for f in jars if _fabric_api_version_matches(f, profile.mc_version)]
        if not fab:
            any_fab = [f for f in jars if "fabric-api" in f.lower()]
            hint = (f" (found {any_fab} — wrong +version)" if any_fab else "")
            return Check(4, BAD,
                         f"no fabric-api jar for +{profile.mc_version} in mods/{hint}" + disabled_note,
                         f"→ RedPiano depends on Fabric API. Install fabric-api-*+"
                         f"{profile.mc_version}.jar into {mods_dir} and RESTART MC "
                         f"(prepare_all.py auto-downloads the matching build).")
        return Check(4, OK,
                     f"redpiano jar + fabric-api ({fab[0]}) present{range_note}" + disabled_note)
    # no target version to check ranges against — presence-only pass, with a note
    any_fab = [f for f in jars if "fabric-api" in f.lower()]
    if not any_fab:
        return Check(4, BAD, "redpiano jar present but no fabric-api jar in mods/" + disabled_note,
                     f"→ install a Fabric API jar into {mods_dir} and restart MC.")
    return Check(4, OK, f"redpiano jar + a fabric-api jar present "
                        f"(mc-version unknown — could not verify +version/range)" + disabled_note)


def check_datapack(world_dir, ns, profile):
    """⑤ <world>/<ns>/pack.mcmeta + data/<ns>/<function_folder>/setup.mcfunction."""
    if not world_dir:
        return Check(5, SKIP, "datapack on disk in the world",
                     "no --world-dir — cannot inspect <world>/datapacks/<ns>/")
    if not ns:
        return Check(5, SKIP, "datapack on disk in the world",
                     "namespace unknown (pass --ns or ensure the receipt/dist carries it)")
    ffolder = profile.function_folder if profile is not None else None
    dp_root = os.path.join(world_dir, ns)
    pack_meta = os.path.join(dp_root, "pack.mcmeta")
    if not os.path.isfile(pack_meta):
        return Check(5, BAD, f"datapack pack.mcmeta missing at {dp_root}",
                     f"→ /function {ns}:setup will be \"Unknown function\" in-game. Deploy the "
                     f"datapack: --world-dir must be exactly <profile>/saves/<world>/datapacks, "
                     f"then /reload. Re-run prepare_all.py + DEPLOY_TO_GAME.bat if unsure.")
    # If we know the version, use its function_folder; else accept either singular/plural.
    if ffolder is not None:
        setup = os.path.join(dp_root, "data", ns, ffolder, "setup.mcfunction")
        candidates = [setup]
    else:
        candidates = [
            os.path.join(dp_root, "data", ns, "function", "setup.mcfunction"),
            os.path.join(dp_root, "data", ns, "functions", "setup.mcfunction"),
        ]
    if not any(os.path.isfile(c) for c in candidates):
        where = candidates[0] if ffolder is not None else " or ".join(candidates)
        return Check(5, BAD, f"setup.mcfunction missing (looked at {where})",
                     f"→ the datapack is present but incomplete (wrong function folder for this "
                     f"MC version, or a partial copy). Re-deploy the freshly built <out>/{ns} and "
                     f"/reload.")
    return Check(5, OK, f"datapack on disk: {dp_root}/pack.mcmeta + setup.mcfunction present")


def check_reminders():
    """⑥ the two always-manual steps (informational; never a ✗)."""
    return Check(6, OK,
                 "reminders: type `/tick rate 80` MANUALLY (the machine never sets it; "
                 "~4x too slow without it) · a CHANGED mod jar needs a FULL MC restart "
                 "(/reload is not enough).")


def _sample_playsound_event():
    """Pick one REAL qzpno: sound-event id from the canonical map so the all-green verdict
    can hand the user a copy-paste in-game声测命令 (/playsound <id> master @s). Prefer a
    piano mf voice (loud, unmistakable); fall back to any id, then to a hardcoded default
    if the map can't be loaded (never crash the report over a nicety)."""
    try:
        imap = core.InstrumentMap.load()
    except Exception:
        return "qzpno:pno_c4_mf"
    ids = []
    for inst in imap.instruments.values():
        ids.extend(inst.get("sound", {}).values())
    for pref in ("qzpno:pno_c4_mf", "qzpno:pno_c4_f", "qzpno:pno_a4_mf"):
        if pref in ids:
            return pref
    return ids[0] if ids else "qzpno:pno_c4_mf"


# ─────────────────────────────────────────────────────────────────────────────
# driver
# ─────────────────────────────────────────────────────────────────────────────

def run_checks(dist_dir, profile_dir=None, world_dir=None, mc_version=None, ns=None):
    """Run every check and return (checks, resolved_ns, resolved_mc, profile_or_None)."""
    ns_val, ns_src = _infer_ns(dist_dir, ns)
    mc_val, mc_src = _infer_mc_version(dist_dir, mc_version)
    profile = None
    profile_err = None
    if mc_val:
        try:
            profile = core.get_version_profile(mc_val)
        except RedPianoError as e:
            profile_err = str(e)

    checks = [
        check_receipt(dist_dir),
        check_resourcepack(profile_dir, profile),
        check_options(profile_dir),
        check_mods(profile_dir, profile),
        check_datapack(world_dir, ns_val, profile),
        check_reminders(),
    ]
    # If the version was given but unresolvable, surface it on check ② as a SKIP reason
    # (rather than silently ignoring a bad --mc-version).
    if mc_val and profile is None and profile_err:
        checks[1] = Check(2, SKIP, "resourcepack file/format",
                          f"mc-version {mc_val} did not resolve: {profile_err}")
    return checks, (ns_val, ns_src), (mc_val, mc_src), profile


def print_report(dist_dir, checks, ns_info, mc_info, profile_dir, world_dir):
    ns_val, ns_src = ns_info
    mc_val, mc_src = mc_info

    print("#" * 72)
    print("#  RedPiano \"没声音\" 体检 (doctor)")
    print("#  警示: 在沙箱里\"读\"到的 profile 也可能是 VMCache 镜像 — 只有 dist/ 里的")
    print("#        回执 (check ①) 才是\"真的进了游戏\"的铁证。其余检查只在回执为真时可信。")
    print("#" * 72)
    print(f"  dist        : {os.path.abspath(dist_dir)}")
    print(f"  namespace   : {ns_val or '(unknown)'}  [{ns_src}]")
    print(f"  mc-version  : {mc_val or '(unknown)'}  [{mc_src}]")
    print(f"  profile-dir : {profile_dir or '(not given)'}")
    print(f"  world-dir   : {world_dir or '(not given)'}")
    print("-" * 72)

    first_bad = None
    for c in checks:
        print(f"  {c.num}. {c.status}  {c.title}")
        if c.fix:
            print(f"       {c.fix}")
        if c.status == BAD and first_bad is None:
            first_bad = c

    print("-" * 72)
    if first_bad is None:
        n_skip = sum(1 for c in checks if c.status == SKIP)
        if n_skip:
            print(f"  VERDICT: 已查项全部通过，但有 {n_skip} 项 SKIP（缺参数没查全）— "
                  f"补上 --profile-dir/--world-dir/--mc-version 再体检一次才算彻底。")
        else:
            ev = _sample_playsound_event()
            print("  VERDICT: 全部通过。若仍没声音，先确认已手动 /tick rate 80 且资源包在右侧已选用。")
            print(f"           一键验声(进游戏敲): /playsound {ev} master @s ~ ~ ~ 1 1")
            print(f"             听到钢琴音=资源包生效; 报 \"Unknown sound event: {ev}\" 或没声"
                  f"=包没启用/格式不符(回到 check ②③)。")
    else:
        print(f"  VERDICT: 第 {first_bad.num} 项失败 — {first_bad.title}。先修这一项"
              f"（见其 → 行），再重跑本体检。")
    print("#" * 72)
    return first_bad is None


def build_argparser():
    p = argparse.ArgumentParser(
        prog="doctor.py",
        description="One-shot 'no sound' health check for a staged RedPiano dist/ bundle "
                    "against the Minecraft profile/world. Read-only; never writes the profile.")
    p.add_argument("--dist", required=True, help="the dist/ bundle dir to check (has the receipt).")
    p.add_argument("--profile-dir", default=None, dest="profile_dir",
                   help="Minecraft profile root (has resourcepacks/, mods/, options.txt).")
    p.add_argument("--world-dir", default=None, dest="world_dir",
                   help="the world's datapacks dir (<profile>/saves/<world>/datapacks).")
    p.add_argument("--mc-version", default=None, dest="mc_version",
                   help="target MC version (inferred from the receipt if omitted).")
    p.add_argument("--ns", default=None,
                   help="datapack namespace (inferred from the receipt / dist/datapack/ if omitted).")
    return p


def run(args):
    if not os.path.isdir(args.dist):
        raise RedPianoError(f"--dist directory not found: {args.dist}")
    checks, ns_info, mc_info, _profile = run_checks(
        args.dist, profile_dir=args.profile_dir, world_dir=args.world_dir,
        mc_version=args.mc_version, ns=args.ns)
    all_ok = print_report(args.dist, checks, ns_info, mc_info,
                          args.profile_dir, args.world_dir)
    return 0 if all_ok else 1


def main(argv=None):
    args = build_argparser().parse_args(argv)
    try:
        return run(args)
    except RedPianoError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130


# ─────────────────────────────────────────────────────────────────────────────
# self-test — build throwaway fixtures and assert exit codes + key lines.
# ─────────────────────────────────────────────────────────────────────────────

def _selftest():
    import tempfile
    import shutil
    import io
    import contextlib

    def _capture(argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = main(argv)
        return code, buf.getvalue()

    root = tempfile.mkdtemp(prefix="rpdoctor_")
    try:
        mc = "1.21.8"
        profile = core.get_version_profile(mc)
        ns = "testsong"

        # ── build an ALL-GREEN fixture ───────────────────────────────────────
        dist = os.path.join(root, "dist")
        prof = os.path.join(root, "profile")
        world = os.path.join(prof, "saves", "w", "datapacks")
        os.makedirs(dist)
        os.makedirs(os.path.join(prof, "resourcepacks"))
        os.makedirs(os.path.join(prof, "mods"))
        os.makedirs(world)

        # (①) a valid receipt + matching token
        token = "deadbeef1234"
        with open(os.path.join(dist, ".deploy_token"), "w", encoding="utf-8") as f:
            f.write(token)
        with open(os.path.join(dist, deploy_bundle.RECEIPT_NAME), "w", encoding="utf-8") as f:
            f.write("\n".join(["RECEIPT v1", f"token={token}", f"ns={ns}",
                               f"mc_version={mc}", "note=selftest"]))
        # also stage datapack under dist so ns can be inferred without --ns
        os.makedirs(os.path.join(dist, "datapack", ns))

        # (②) a resourcepack zip whose rp format covers the target
        rp_zip = os.path.join(prof, "resourcepacks", RP_ZIP)
        with zipfile.ZipFile(rp_zip, "w") as z:
            z.writestr("pack.mcmeta", json.dumps(
                {"pack": {"pack_format": profile.rp_format, "description": "qzpno"}}))
        # (③) options.txt with the pack selected
        with open(os.path.join(prof, "options.txt"), "w", encoding="utf-8") as f:
            f.write(f'resourcePacks:["vanilla","{OPTIONS_ENTRY}"]\n'
                    'incompatibleResourcePacks:[]\n')
        # (④) redpiano jar (range covers) + matching fabric-api jar
        rj = os.path.join(prof, "mods", "redpiano-1.0.0.jar")
        with zipfile.ZipFile(rj, "w") as z:
            z.writestr("fabric.mod.json", json.dumps(
                {"id": "redpiano", "depends": {"minecraft": f"~{mc}"}}))
        with zipfile.ZipFile(os.path.join(prof, "mods", f"fabric-api-0.136.1+{mc}.jar"), "w") as z:
            z.writestr("readme", "x")
        # (⑤) datapack on disk in the world
        dp = os.path.join(world, ns)
        os.makedirs(os.path.join(dp, "data", ns, profile.function_folder))
        with open(os.path.join(dp, "pack.mcmeta"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"pack": {"pack_format": profile.dp_format, "description": ns}}))
        with open(os.path.join(dp, "data", ns, profile.function_folder, "setup.mcfunction"),
                  "w", encoding="utf-8") as f:
            f.write("say setup\n")

        # ALL-GREEN: exit 0, ns inferred, verdict passes.
        code, out = _capture(["--dist", dist, "--profile-dir", prof, "--world-dir", world])
        assert code == 0, f"all-green expected exit 0, got {code}\n{out}"
        assert "全部通过" in out, out
        assert "1. ✓" in out and "5. ✓" in out, out
        # ns inferred from receipt (no --ns passed)
        assert ns in out, out
        # all-green must hand the user a REAL qzpno: playsound self-test (a live id from the map)
        assert "/playsound qzpno:" in out, out
        _ev = _sample_playsound_event()
        assert _ev in out and _ev.startswith("qzpno:"), (_ev, out)

        # ── ✗ case A: NO receipt (delete it) -> check ① BAD, exit 1 ───────────
        distA = os.path.join(root, "distA")
        shutil.copytree(dist, distA)
        os.remove(os.path.join(distA, deploy_bundle.RECEIPT_NAME))
        code, out = _capture(["--dist", distA, "--profile-dir", prof, "--world-dir", world,
                              "--mc-version", mc, "--ns", ns])
        assert code == 1, f"no-receipt expected exit 1, got {code}\n{out}"
        assert "1. ✗" in out, out
        assert "第 1 项失败" in out, out

        # ── ✗ case B: resourcepack rp-format mismatch -> check ② BAD, exit 1 ──
        profB = os.path.join(root, "profileB")
        shutil.copytree(prof, profB)
        with zipfile.ZipFile(os.path.join(profB, "resourcepacks", RP_ZIP), "w") as z:
            z.writestr("pack.mcmeta", json.dumps(
                {"pack": {"pack_format": profile.rp_format + 5, "description": "wrong"}}))
        code, out = _capture(["--dist", dist, "--profile-dir", profB, "--world-dir", world,
                              "--mc-version", mc, "--ns", ns])
        assert code == 1, f"rp-mismatch expected exit 1, got {code}\n{out}"
        assert "2. ✗" in out, out
        assert "第 2 项失败" in out, out

        # ── ✗ case C: pack present but NOT selected in options.txt -> ③ BAD ───
        profC = os.path.join(root, "profileC")
        shutil.copytree(prof, profC)
        with open(os.path.join(profC, "options.txt"), "w", encoding="utf-8") as f:
            f.write('resourcePacks:["vanilla"]\nincompatibleResourcePacks:[]\n')
        code, out = _capture(["--dist", dist, "--profile-dir", profC, "--world-dir", world,
                              "--mc-version", mc, "--ns", ns])
        assert code == 1, f"not-selected expected exit 1, got {code}\n{out}"
        assert "3. ✗" in out, out
        assert "第 3 项失败" in out, out

        # ── ✗ case D: TWO active redpiano*.jar (residual old jar) -> ④ BAD ────
        # This is the exact crime-scene class: a leftover -UNVERIFIED.jar left next to the new
        # build makes Fabric load the wrong one by modid -> NoSuchFieldError crash.
        profD = os.path.join(root, "profileD")
        shutil.copytree(prof, profD)
        rjOld = os.path.join(profD, "mods", "redpiano-1.0.0-mc1.21.7-UNVERIFIED.jar")
        with zipfile.ZipFile(rjOld, "w") as z:
            z.writestr("fabric.mod.json", json.dumps(
                {"id": "redpiano", "depends": {"minecraft": f"~{mc}"}}))
        code, out = _capture(["--dist", dist, "--profile-dir", profD, "--world-dir", world,
                              "--mc-version", mc, "--ns", ns])
        assert code == 1, f"double-redpiano expected exit 1, got {code}\n{out}"
        assert "4. ✗" in out, out
        assert "第 4 项失败" in out, out
        assert "个活跃 redpiano" in out, out
        # both filenames + the fix command must be reported
        assert "redpiano-1.0.0-mc1.21.7-UNVERIFIED.jar" in out and "redpiano-1.0.0.jar" in out, out
        assert "Rename-Item" in out, out

        # ── ✓ case E: single active jar + a .stale.disabled present -> ④ OK ───
        # A disabled/stale leftover is NORMAL after clean-then-install; it must NOT be a ✗,
        # only a neutral one-line note.
        profE = os.path.join(root, "profileE")
        shutil.copytree(prof, profE)
        # rename our staged old jar to .stale.disabled (as the deploy chain would)
        with open(os.path.join(profE, "mods",
                               "redpiano-1.0.0-mc1.21.7-UNVERIFIED.jar.stale.disabled"),
                  "w", encoding="utf-8") as f:
            f.write("stale placeholder")
        code, out = _capture(["--dist", dist, "--profile-dir", profE, "--world-dir", world,
                              "--mc-version", mc, "--ns", ns])
        assert code == 0, f"single-jar+disabled expected exit 0, got {code}\n{out}"
        assert "4. ✓" in out, out
        assert "个已禁用 jar" in out, out          # neutral note shown
        assert "4. ✗" not in out, out              # NOT a failure

        # ── SKIP path: no profile/world given -> checks ②③④⑤ SKIP, exit 0 ────
        code, out = _capture(["--dist", dist])
        assert code == 0, f"receipt-only expected exit 0 (rest SKIP), got {code}\n{out}"
        assert "SKIP" in out, out

        print("SELFTEST OK")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
