# -*- coding: utf-8 -*-
"""deploy_bundle.py — the honest last-mile installer for sandboxed agents.

WHY THIS EXISTS (read `docs/RUNTIME_SANDBOX.md` for the full story)
------------------------------------------------------------------
When an agent (Trae SOLO / GLM, some CI sandboxes, …) writes to a Minecraft
profile such as ``C:\\Minecraft\\ModrinthApp\\profiles\\Fabric 1.21.7\\...`` the
write can be *silently redirected* into the sandbox's copy-on-write mirror
(``%APPDATA%\\Roaming\\TRAE SOLO CN\\VMCache\\...\\drive\\C\\Minecraft\\...``).
The agent then reads the mirror back, sees its own files, and reports success —
but the natively-running game reads the REAL profile, which never changed. This
is the #1 reason "the datapack/resourcepack was built but nothing plays."

You cannot beat that redirection from inside the sandbox: it lives *below* the
Python process, so path heuristics and read-back checks both see the mirror.
The ONLY reliable channel is the project workspace itself — that folder is
bind-mounted to the real disk (that is why the agent's build artifacts show up
on the real Desktop). So the fix is:

  1. Build every artifact into the workspace ``dist/`` (the agent CAN do this).
  2. Emit a native ``DEPLOY_TO_GAME.bat`` (→ unicode-safe ``.ps1``) that the USER
     double-clicks in Windows Explorer — a native process, outside the sandbox,
     whose writes reach the real profile.
  3. That native script, and ONLY that native script, writes a signed
     ``DEPLOY_RECEIPT.txt`` back into ``dist/`` (the real workspace). The agent
     treats "receipt present with the matching token" as the sole proof of a
     real install. Its own writes into the profile can never forge the receipt,
     so it can no longer hallucinate success.

This module owns steps 1–3's file generation. It performs NO copy into the
profile itself (that is the native script's job); the only exception is
``install_now()`` for genuinely-native callers who pass ``--install-now``.

Pure stdlib.
"""

import argparse
import json
import os
import shutil
import sys
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from runtime_guard import RuntimeGuardError, path_is_under_trae_vmcache  # noqa: E402

RECEIPT_NAME = "DEPLOY_RECEIPT.txt"
PS1_NAME = "deploy_to_game.ps1"
BAT_NAME = "DEPLOY_TO_GAME.bat"
README_NAME = "README_部署说明.txt"
RP_ZIP_NAME = "qzpno_mv.zip"


def new_token():
    return uuid.uuid4().hex[:12]


def _rel_from_drive(path):
    """'C:/Minecraft/foo' -> ('C', 'Minecraft\\foo') for the VMCache-mirror probe."""
    p = os.path.abspath(path).replace("/", "\\")
    drive, rest = os.path.splitdrive(p)
    return drive.rstrip(":"), rest.lstrip("\\")


def stage_artifacts(dist_dir, *, ns, datapack_src_dir, rp_zip=None, mod_jars=None):
    """Copy the built artifacts into ``dist_dir`` in the layout the native script
    expects. Returns a manifest dict. Writes ONLY inside the (real) workspace."""
    os.makedirs(dist_dir, exist_ok=True)
    manifest = {"ns": ns, "datapack": None, "resourcepack": None, "mods": []}

    # datapack -> dist/datapack/<ns>/  (so the native script copies it to
    # <world>/datapacks/<ns>).
    if datapack_src_dir:
        if not os.path.isdir(datapack_src_dir):
            raise FileNotFoundError(f"datapack source not found: {datapack_src_dir}")
        dp_dst = os.path.join(dist_dir, "datapack", ns)
        if os.path.isdir(dp_dst):
            shutil.rmtree(dp_dst)
        shutil.copytree(datapack_src_dir, dp_dst)
        manifest["datapack"] = os.path.join("datapack", ns)

    # resourcepack zip -> dist/qzpno_mv.zip
    if rp_zip:
        if not os.path.isfile(rp_zip):
            raise FileNotFoundError(f"resourcepack zip not found: {rp_zip}")
        rp_dst = os.path.join(dist_dir, RP_ZIP_NAME)
        if os.path.abspath(rp_zip) != os.path.abspath(rp_dst):
            shutil.copy2(rp_zip, rp_dst)
        manifest["resourcepack"] = RP_ZIP_NAME

    # mod + fabric-api jars -> dist/mods/*.jar
    if mod_jars:
        mods_dst = os.path.join(dist_dir, "mods")
        os.makedirs(mods_dst, exist_ok=True)
        for jar in mod_jars:
            if not jar:
                continue
            if not os.path.isfile(jar):
                raise FileNotFoundError(f"mod jar not found: {jar}")
            dst = os.path.join(mods_dst, os.path.basename(jar))
            if os.path.abspath(jar) != os.path.abspath(dst):
                shutil.copy2(jar, dst)
            manifest["mods"].append(os.path.join("mods", os.path.basename(jar)))

    return manifest


def _ps1_source(*, ns, world_datapacks_dir, profile_dir, mc_version, token, manifest):
    """The native PowerShell installer. Runs OUTSIDE the sandbox (double-clicked),
    copies dist/ artifacts into the real profile, enables the pack, self-checks
    against the VMCache mirror, and writes the signed receipt on success."""
    world = os.path.abspath(world_datapacks_dir).replace("/", "\\") if world_datapacks_dir else ""
    profile = os.path.abspath(profile_dir).replace("/", "\\") if profile_dir else ""
    drive, rel = _rel_from_drive(world) if world else ("", "")
    has_dp = "1" if manifest.get("datapack") else "0"
    has_rp = "1" if manifest.get("resourcepack") else "0"
    has_mods = "1" if manifest.get("mods") else "0"

    tpl = r"""# DEPLOY_TO_GAME — native installer generated by deploy_bundle.py
# Double-click DEPLOY_TO_GAME.bat in Windows Explorer to run this. Do NOT let an
# in-sandbox agent invoke it — it must run as a native process to reach the game.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Dist        = $PSScriptRoot
$Ns          = '@@NS@@'
$McVersion   = '@@MCVER@@'
$Token       = '@@TOKEN@@'
$World       = '@@WORLD@@'          # <profile>/saves/<world>/datapacks
$Profile     = '@@PROFILE@@'        # profile root
$HasDatapack = '@@HAS_DP@@' -eq '1'
$HasRp       = '@@HAS_RP@@' -eq '1'
$HasMods     = '@@HAS_MODS@@' -eq '1'

Write-Host ''
Write-Host '======================================================================'
Write-Host "  RedPiano 部署到游戏  (song: $Ns  |  MC $McVersion)"
Write-Host '======================================================================'
Write-Host "  来源 dist : $Dist"
Write-Host "  世界      : $World"
Write-Host "  profile   : $Profile"
Write-Host ''

$copied = @()

function Copy-Tree($src, $dst) {
    if (-not (Test-Path $src)) { throw "缺少来源: $src" }
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force
}

# 1) datapack -> <world>/datapacks/<ns>
if ($HasDatapack) {
    if ([string]::IsNullOrWhiteSpace($World)) {
        throw "本包含 datapack 但没有目标世界目录（$World 为空）。请用带 --world-dir 的 prepare_all 重新生成本安装器，再双击。"
    }
    $dpSrc = Join-Path $Dist ("datapack\" + $Ns)
    $dpDst = Join-Path $World $Ns
    if (Test-Path $dpDst) { Remove-Item -Recurse -Force $dpDst }
    Copy-Tree $dpSrc $dpDst
    Write-Host "  [x] datapack -> $dpDst"
    $copied += "datapack:$dpDst"
}

# 2) resourcepack -> <profile>/resourcepacks/qzpno_mv.zip
if ($HasRp) {
    $rpSrc = Join-Path $Dist 'qzpno_mv.zip'
    $rpDir = Join-Path $Profile 'resourcepacks'
    New-Item -ItemType Directory -Force -Path $rpDir | Out-Null
    Copy-Item -Path $rpSrc -Destination (Join-Path $rpDir 'qzpno_mv.zip') -Force
    Write-Host "  [x] resourcepack -> $(Join-Path $rpDir 'qzpno_mv.zip')"
    $copied += "resourcepack:$(Join-Path $rpDir 'qzpno_mv.zip')"

    # enable file/qzpno_mv.zip in options.txt. Edit the JSON array as a STRING —
    # PowerShell 5.1's ConvertTo-Json mangles small arrays into {value;Count} objects,
    # and its UTF8 writer prepends a BOM that would corrupt options.txt. We preserve
    # existing packs and write UTF-8 without BOM via .NET.
    $opt = Join-Path $Profile 'options.txt'
    if (Test-Path $opt) {
        Copy-Item $opt "$opt.redpiano.bak" -Force
        $entry = 'file/qzpno_mv.zip'
        $q = '"' + $entry + '"'
        $lines = Get-Content -LiteralPath $opt -Encoding UTF8
        $sawRp = $false
        $out = foreach ($line in $lines) {
            if ($line -like 'resourcePacks:*') {
                $sawRp = $true
                $val = $line.Substring('resourcePacks:'.Length).Trim()
                if ($val -notlike "*$q*") {
                    if ($val -eq '[]' -or $val -eq '') { $val = "[$q]" }
                    else { $val = $val.Substring(0, $val.Length - 1) + ",$q]" }
                }
                'resourcePacks:' + $val
            } elseif ($line -like 'incompatibleResourcePacks:*') {
                $val = $line.Substring('incompatibleResourcePacks:'.Length)
                $val = $val.Replace(",$q", '').Replace("$q,", '').Replace($q, '')
                'incompatibleResourcePacks:' + $val
            } else { $line }
        }
        if (-not $sawRp) { $out += "resourcePacks:[$q]" }
        [System.IO.File]::WriteAllLines($opt, $out, (New-Object System.Text.UTF8Encoding $false))
        Write-Host "  [x] options.txt: $entry 已选用 (备份 options.txt.redpiano.bak)"
    } else {
        Write-Host "  [!] options.txt 不存在 — 请先把该 Minecraft profile 启动一次，再重跑本脚本，"
        Write-Host "      或在 游戏 选项->资源包 里手动把 qzpno_mv 移到右侧。"
    }
}

# 3) mods -> <profile>/mods/
$staleCount = 0
if ($HasMods) {
    $modsDir = Join-Path $Profile 'mods'
    New-Item -ItemType Directory -Force -Path $modsDir | Out-Null

    # 本次要装的 jar 文件名清单（dist/mods 下的），用于"先清后装"：任何在 profile/mods 里
    # 的旧 redpiano*.jar / fabric-api-*.jar 只要【不在】这个清单里，就先改名 .stale.disabled。
    # 根因：安装只 Copy -Force 覆盖同名文件，从不清理不同名的旧版本 jar（如换版本导致文件名
    # 改变、或上次残留的 -UNVERIFIED.jar），Fabric 会按 modid 加载到旧毒 jar 而崩溃/重复加载。
    $installing = @{}
    Get-ChildItem -Path (Join-Path $Dist 'mods') -Filter *.jar | ForEach-Object {
        $installing[$_.Name.ToLowerInvariant()] = $true
    }

    # 只清"活跃"(.jar 结尾)的旧 jar；已经是 .disabled/.stale 的不动。改名不删除，保留回滚。
    Get-ChildItem -Path $modsDir -Filter *.jar -File -ErrorAction SilentlyContinue | ForEach-Object {
        $lower = $_.Name.ToLowerInvariant()
        $isRedpiano = $lower.StartsWith('redpiano')
        $isFabricApi = $lower.StartsWith('fabric-api')
        if (($isRedpiano -or $isFabricApi) -and (-not $installing.ContainsKey($lower))) {
            $stalePath = $_.FullName + '.stale.disabled'
            if (Test-Path $stalePath) { Remove-Item -LiteralPath $stalePath -Force }
            Rename-Item -LiteralPath $_.FullName -NewName ($_.Name + '.stale.disabled') -Force
            Write-Host "  [!] 旧 jar 已禁用 -> $($_.Name).stale.disabled  (被本次安装的新版取代)"
            $staleCount += 1
        }
    }

    Get-ChildItem -Path (Join-Path $Dist 'mods') -Filter *.jar | ForEach-Object {
        Copy-Item $_.FullName -Destination (Join-Path $modsDir $_.Name) -Force
        Write-Host "  [x] mod -> $(Join-Path $modsDir $_.Name)"
        $copied += "mod:$($_.Name)"
    }
}

# ---- self-check: did our write reach the REAL disk, or a Trae VMCache mirror? ----
$virtualized = $false
if ($HasDatapack -and $World) {
    try {
        $probe = Join-Path $World '.mcmm_probe.txt'
        Set-Content -LiteralPath $probe -Value $Token -Encoding ASCII
        $vmBase = Join-Path $env:APPDATA 'TRAE SOLO CN\VMCache'
        if (Test-Path $vmBase) {
            $rel = '@@REL@@'                       # Minecraft\...\datapacks\.mcmm_probe.txt
            $leak = Get-ChildItem -Path $vmBase -Directory -ErrorAction SilentlyContinue |
                ForEach-Object { Join-Path $_.FullName ("drive\@@DRIVE@@\" + $rel + "\.mcmm_probe.txt") } |
                Where-Object { Test-Path $_ }
            if ($leak) { $virtualized = $true }
        }
        Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
    } catch { }
}

Write-Host ''
if ($virtualized) {
    Write-Host '######################################################################'
    Write-Host '  ✗ 检测到你是在 Trae 沙箱里运行这个脚本！写入被重定向到 VMCache 镜像，'
    Write-Host '    并没有真正进入游戏。请在 Windows 资源管理器里【双击】DEPLOY_TO_GAME.bat，'
    Write-Host '    不要让 agent 代跑。未生成回执 —— 视为【未部署】。'
    Write-Host '######################################################################'
    exit 3
}

# ---- success: write the signed receipt into the REAL workspace ----
$receipt = @(
    "RECEIPT v1",
    "token=$Token",
    "ns=$Ns",
    "mc_version=$McVersion",
    "world=$World",
    "profile=$Profile",
    "copied=" + ($copied -join '; '),
    "note=written by native DEPLOY_TO_GAME on the real host"
)
[System.IO.File]::WriteAllLines((Join-Path $Dist '@@RECEIPT@@'), $receipt, (New-Object System.Text.UTF8Encoding $false))
Write-Host '======================================================================'
Write-Host "  ✓ 已真正部署到游戏。回执: $(Join-Path $Dist '@@RECEIPT@@')"
Write-Host '======================================================================'
if ($staleCount -gt 0) {
    Write-Host "  已禁用 $staleCount 个旧 jar (.stale.disabled)，确认新版工作正常后可删除。"
}
Write-Host '  接下来在游戏里（按顺序）：'
if ($HasMods) { Write-Host '   0. 完整重启 Minecraft（换过 mod jar，/reload 不够）' }
Write-Host "   1. /reload"
Write-Host "   2. /tick rate 80        ← 必须手动敲，机器不会自己设"
if ($HasRp) { Write-Host '   3. 选项->资源包：确认 qzpno_mv 在右侧“已选用”' }
Write-Host "   4. /function $Ns`:setup"
Write-Host "   5. 按 [play] 牌子/按钮"
Write-Host ''
"""
    # ns/world/profile/token 都被替换进 PowerShell 单引号字符串。值里若含 '（'O'Brien' 世界名、
    # it's-a-test 之类完全合法的 Windows 文件夹名）会提前闭合单引号 -> .ps1 语法崩溃甚至注入。
    # PowerShell 单引号串里转义 ' 的办法是把它加倍成 ''。数字/布尔占位符（HAS_*/DRIVE/RECEIPT）
    # 是我们自己生成的固定值, 无需转义。
    def _psq(s):
        return s.replace("'", "''")

    repl = {
        "@@NS@@": _psq(ns), "@@MCVER@@": _psq(mc_version), "@@TOKEN@@": _psq(token),
        "@@WORLD@@": _psq(world), "@@PROFILE@@": _psq(profile),
        "@@HAS_DP@@": has_dp, "@@HAS_RP@@": has_rp, "@@HAS_MODS@@": has_mods,
        "@@REL@@": _psq(rel), "@@DRIVE@@": _psq(drive), "@@RECEIPT@@": RECEIPT_NAME,
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    return tpl


def _bat_source():
    """Double-clickable wrapper: launch the .ps1 natively with UTF-8 + bypass policy."""
    return (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "powershell -NoProfile -ExecutionPolicy Bypass -File \"%~dp0" + PS1_NAME + "\"\r\n"
        "echo.\r\n"
        "pause\r\n"
    )


def _readme_source(*, ns, world_datapacks_dir, profile_dir):
    return (
        "如何把这首歌真正装进 Minecraft\n"
        "==============================\n\n"
        "为什么需要这一步：\n"
        "  你用的 AI 工具（Trae 等）跑在沙箱里，它写 C:\\Minecraft 会被悄悄改写到一个\n"
        "  镜像目录，游戏根本读不到。所以真正的“装进游戏”这一步，必须由【你本人】在\n"
        "  沙箱之外的 Windows 上执行。\n\n"
        "怎么做（就一步）：\n"
        f"  1. 在【Windows 资源管理器】里，双击本文件夹里的  {BAT_NAME}\n"
        "     （不要让 AI 帮你运行它——必须你自己双击）。\n"
        "  2. 黑色窗口会显示把 datapack / 资源包 / mod 复制到：\n"
        f"        世界    : {world_datapacks_dir}\n"
        f"        profile : {profile_dir}\n"
        "     并自动在 options.txt 里启用 qzpno_mv 资源包。\n"
        "  3. 看到 “✓ 已真正部署到游戏” 即成功；此时本文件夹会生成 DEPLOY_RECEIPT.txt。\n"
        "     若看到 “✗ 检测到你是在 Trae 沙箱里运行” —— 说明是 AI 代跑的，请你亲自双击。\n\n"
        "然后进游戏（按顺序）：\n"
        "  完整重启 MC（如换过 mod） -> /reload -> /tick rate 80（手动敲）->\n"
        f"  确认资源包 qzpno_mv 已选用 -> /function {ns}:setup -> 按 [play]。\n"
    )


def build_deploy_bundle(dist_dir, *, ns, world_datapacks_dir, profile_dir, mc_version,
                        datapack_src_dir, rp_zip=None, mod_jars=None, token=None):
    """Stage artifacts + emit the native deploy scripts into ``dist_dir``.

    Returns a dict with the token and the generated file paths. Performs NO write
    into the Minecraft profile — that is the emitted script's job, run natively."""
    token = token or new_token()
    # Conservative ns check: a datapack namespace is required to be [a-z0-9_-] by Minecraft
    # itself, so any other char is already invalid — and rejecting here also removes the ' /
    # whitespace injection surface for the generated .ps1 ($Ns is spliced into paths + a
    # PS single-quoted string). Fail loud rather than emit a bundle that crashes on run.
    import re as _re
    if not ns or not _re.fullmatch(r"[a-z0-9_-]+", ns):
        raise RuntimeGuardError(
            f"invalid datapack namespace {ns!r}: must be non-empty and only [a-z0-9_-] "
            "(Minecraft's own rule for a datapack namespace).")
    dist_dir = os.path.abspath(dist_dir)
    # dist/ MUST live on the real disk. If it resolves under the VMCache mirror, the .bat
    # (run natively) would not find the staged artifacts. Refuse rather than mislead.
    if path_is_under_trae_vmcache(dist_dir):
        raise RuntimeGuardError(
            f"--dist {dist_dir} resolves under the Trae VMCache mirror. Stage into the real "
            "project workspace (e.g. 'dist' under the open project folder) so the native "
            "DEPLOY_TO_GAME.bat can read it.")
    # Clear any stale receipt/token from a PREVIOUS build so a leftover cannot masquerade as
    # a successful deploy of THIS build (verify_receipt only trusts a fresh, matching token).
    for stale in (RECEIPT_NAME, ".deploy_token"):
        try:
            os.remove(os.path.join(dist_dir, stale))
        except OSError:
            pass
    manifest = stage_artifacts(dist_dir, ns=ns, datapack_src_dir=datapack_src_dir,
                               rp_zip=rp_zip, mod_jars=mod_jars)

    ps1 = os.path.join(dist_dir, PS1_NAME)
    # utf-8-sig (BOM) is INTENTIONAL and required here: Windows PowerShell 5.1 reads a
    # BOM-less .ps1 as the system ANSI code page (GBK on a Chinese Windows), which mangles
    # the Chinese Write-Host strings. The BOM makes PS read it as UTF-8. (options.txt and the
    # receipt are written WITHOUT a BOM, via .NET, because Minecraft parses them itself.)
    with open(ps1, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(_ps1_source(ns=ns, world_datapacks_dir=world_datapacks_dir,
                            profile_dir=profile_dir, mc_version=mc_version,
                            token=token, manifest=manifest))
    bat = os.path.join(dist_dir, BAT_NAME)
    with open(bat, "w", encoding="utf-8", newline="") as f:
        f.write(_bat_source())
    readme = os.path.join(dist_dir, README_NAME)
    with open(readme, "w", encoding="utf-8", newline="") as f:
        f.write(_readme_source(ns=ns, world_datapacks_dir=world_datapacks_dir,
                              profile_dir=profile_dir))

    # a token sidecar so verify_receipt() knows what to look for without re-plumbing
    with open(os.path.join(dist_dir, ".deploy_token"), "w", encoding="utf-8") as f:
        f.write(token)

    return {"token": token, "dist_dir": dist_dir, "manifest": manifest,
            "bat": bat, "ps1": ps1, "readme": readme,
            "receipt": os.path.join(dist_dir, RECEIPT_NAME)}


def verify_receipt(dist_dir, token=None):
    """Return (installed: bool, info: str). installed is True ONLY when a receipt
    written by the native script exists with the matching token. This is the sole
    trusted proof of a real in-game install for a sandboxed agent."""
    dist_dir = os.path.abspath(dist_dir)
    if token is None:
        tok_path = os.path.join(dist_dir, ".deploy_token")
        if os.path.isfile(tok_path):
            token = open(tok_path, encoding="utf-8").read().strip()
    receipt = os.path.join(dist_dir, RECEIPT_NAME)
    if not os.path.isfile(receipt):
        return False, (f"未找到回执 {receipt} —— 说明还没有真正部署到游戏。"
                       f"请让【用户本人】在资源管理器里双击 {os.path.join(dist_dir, BAT_NAME)}。")
    # fail-closed: 没有 token 可核对时(.deploy_token 缺失且未显式传入), 无法确认这份回执
    # 归属本次构建。绝不能因为"回执文件存在"就放行 —— 那样任何一份残留旧回执都会被误判为
    # 本次成功部署, 击穿"回执是唯一可信证明"的前提。
    if not token:
        return False, (f".deploy_token 缺失, 无法确认回执 {receipt} 归属本次构建。"
                       f"请重新 prepare + 让【用户本人】双击 {BAT_NAME} 部署本次构建。")
    body = open(receipt, encoding="utf-8", errors="replace").read()
    # line-exact token match (a substring test could false-match a longer token)
    lines = [ln.strip() for ln in body.splitlines()]
    if token and f"token={token}" not in lines:
        return False, (f"回执 {receipt} 的 token 不匹配（可能是上一次构建的旧回执）。"
                       f"请重新双击 {BAT_NAME} 部署本次构建。")
    return True, f"已确认真正部署（回执 {receipt}）。"


def _enable_pack_in_options(profile_dir, entry="file/qzpno_mv.zip"):
    """Add ``entry`` to resourcePacks in <profile>/options.txt (unicode-safe), remove it
    from incompatibleResourcePacks, preserving other packs. Returns (changed, note)."""
    opt = os.path.join(profile_dir, "options.txt")
    if not os.path.isfile(opt):
        return False, f"options.txt not found at {opt} (start the profile once, or enable manually)"
    raw = open(opt, "r", encoding="utf-8").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    changed = False
    saw = False
    for i, line in enumerate(lines):
        if line.startswith("resourcePacks:"):
            saw = True
            try:
                arr = json.loads(line[len("resourcePacks:"):] or "[]")
            except json.JSONDecodeError:
                arr = []
            if entry not in arr:
                arr.append(entry)
                changed = True
            lines[i] = "resourcePacks:" + json.dumps(arr, ensure_ascii=False, separators=(",", ":"))
        elif line.startswith("incompatibleResourcePacks:"):
            try:
                arr = json.loads(line[len("incompatibleResourcePacks:"):] or "[]")
            except json.JSONDecodeError:
                arr = []
            if entry in arr:
                arr = [x for x in arr if x != entry]
                changed = True
            lines[i] = "incompatibleResourcePacks:" + json.dumps(arr, ensure_ascii=False, separators=(",", ":"))
    if not saw:
        lines.append("resourcePacks:" + json.dumps([entry], ensure_ascii=False, separators=(",", ":")))
        changed = True
    if changed:
        shutil.copyfile(opt, opt + ".redpiano.bak")
        open(opt, "w", encoding="utf-8", newline="").write(nl.join(lines))
    return changed, f"{entry} {'enabled' if changed else 'already enabled'} in options.txt"


def _probe_write_hit_vmcache_mirror(target_dir, token):
    """Python port of the .ps1 self-check: write a probe file into ``target_dir`` and see
    whether it leaked into a Trae VMCache mirror (``%APPDATA%/TRAE SOLO CN/VMCache/*/drive/
    <drive>/<rel>/``). Returns True iff the write was silently redirected into the mirror.

    The probe file is always cleaned up (finally). This is the ONLY reliable way to tell
    from inside the sandbox whether a write really reached the real disk."""
    probe = os.path.join(target_dir, ".mcmm_probe.txt")
    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(probe, "w", encoding="ascii") as f:
            f.write(token)
        vm_base = os.path.join(os.environ.get("APPDATA", ""), "TRAE SOLO CN", "VMCache")
        if not os.path.isdir(vm_base):
            return False
        drive, rel = _rel_from_drive(target_dir)
        for entry in os.listdir(vm_base):
            mirror = os.path.join(vm_base, entry, "drive", drive, rel, ".mcmm_probe.txt")
            if os.path.isfile(mirror):
                return True
        return False
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass


def install_now(dist_dir, *, world_datapacks_dir, profile_dir, ns, manifest, token,
                mc_version):
    """Native-only inline install (for callers who pass --install-now on a real host).
    Mirrors what the .ps1 does, in Python. Writes the receipt on completion.

    DO NOT call this from inside a sandbox — it would install into the mirror and
    then (falsely) write a receipt. It is gated by the CLI's native intent."""
    copied = []
    if manifest.get("datapack") and world_datapacks_dir:
        src = os.path.join(dist_dir, "datapack", ns)
        dst = os.path.join(world_datapacks_dir, ns)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        copied.append(f"datapack:{dst}")
    if manifest.get("resourcepack") and profile_dir:
        rp_dir = os.path.join(profile_dir, "resourcepacks")
        os.makedirs(rp_dir, exist_ok=True)
        shutil.copy2(os.path.join(dist_dir, RP_ZIP_NAME), os.path.join(rp_dir, RP_ZIP_NAME))
        copied.append(f"resourcepack:{os.path.join(rp_dir, RP_ZIP_NAME)}")
        _changed, note = _enable_pack_in_options(profile_dir)
        copied.append(f"options:{note}")
    staled = []
    if manifest.get("mods") and profile_dir:
        mods_dir = os.path.join(profile_dir, "mods")
        os.makedirs(mods_dir, exist_ok=True)
        # "先清后装" (mirrors the .ps1): any ACTIVE (.jar) redpiano*/fabric-api-* jar in the
        # profile that is NOT among the filenames we're about to install gets renamed to
        # <name>.stale.disabled first. Copy2 only overwrites SAME-named files; a version bump
        # that changes the filename (or a leftover -UNVERIFIED.jar) would otherwise linger and
        # Fabric would load the old jar by modid -> NoSuchFieldError crash / duplicate load.
        installing = {os.path.basename(r).lower() for r in manifest["mods"]}
        for existing in os.listdir(mods_dir):
            low = existing.lower()
            if not low.endswith(".jar"):
                continue  # already .disabled/.stale — leave it
            if not (low.startswith("redpiano") or low.startswith("fabric-api")):
                continue
            if low in installing:
                continue  # same filename — will be overwritten in place below
            stale_dst = os.path.join(mods_dir, existing + ".stale.disabled")
            if os.path.exists(stale_dst):
                os.remove(stale_dst)
            os.rename(os.path.join(mods_dir, existing), stale_dst)
            staled.append(existing)
            copied.append(f"stale:{existing}.stale.disabled")
        for rel in manifest["mods"]:
            src = os.path.join(dist_dir, rel)
            shutil.copy2(src, os.path.join(mods_dir, os.path.basename(src)))
            copied.append(f"mod:{os.path.basename(src)}")
    # Self-check BEFORE writing the receipt: even though --install-now is documented as
    # native-only, nothing physically stops an agent from passing it inside the sandbox with a
    # real C:\Minecraft path — the copytree above would then land in the VMCache mirror while
    # this (workspace) receipt still writes, forging a "native host" receipt. Probe the real
    # write target the same way the .ps1 does; if it leaked into the mirror, refuse to write the
    # receipt so the deploy handshake cannot be forged.
    probe_target = (world_datapacks_dir if (manifest.get("datapack") and world_datapacks_dir)
                    else profile_dir)
    if probe_target and _probe_write_hit_vmcache_mirror(probe_target, token):
        raise RuntimeGuardError(
            f"--install-now write to {probe_target} was redirected into the Trae VMCache "
            "mirror — nothing reached the real game. Refusing to write a receipt (that would "
            "forge a 'native host' install). Run inside the sandbox is unsupported; have the "
            f"user double-click {BAT_NAME} on the real host instead.")
    receipt = os.path.join(dist_dir, RECEIPT_NAME)
    receipt_lines = [
        "RECEIPT v1", f"token={token}", f"ns={ns}", f"mc_version={mc_version}",
        f"world={world_datapacks_dir}", f"profile={profile_dir}",
        "copied=" + "; ".join(copied),
        "note=written by --install-now on a native host",
    ]
    if staled:
        receipt_lines.append("stale=" + "; ".join(f"{s}.stale.disabled" for s in staled))
    with open(receipt, "w", encoding="utf-8") as f:
        f.write("\n".join(receipt_lines))
    if staled:
        print(f"已禁用 {len(staled)} 个旧 jar (.stale.disabled)，"
              f"确认新版工作正常后可删除：{', '.join(staled)}")
    return receipt, copied


def _cli(argv=None):
    p = argparse.ArgumentParser(
        prog="deploy_bundle.py",
        description="Check whether a dist/ bundle has been really deployed into the game "
                    "(i.e. whether the native DEPLOY_TO_GAME.bat has run and left a receipt).")
    p.add_argument("--verify", metavar="DIST", required=True,
                   help="dist/ dir to check for a valid DEPLOY_RECEIPT.txt")
    args = p.parse_args(argv)
    ok, info = verify_receipt(args.verify)
    print(("✓ INSTALLED — " if ok else "✗ NOT INSTALLED — ") + info)
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(_cli())
