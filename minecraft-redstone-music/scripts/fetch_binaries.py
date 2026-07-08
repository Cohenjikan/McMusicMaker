# -*- coding: utf-8 -*-
"""fetch_binaries.py — version-universal, local-first RedPiano binary fetcher.

Replaces the old "every round a human hand-curates ONE version's jar" step with a
self-service resolver keyed on a single ``--mc-version`` flag. It resolves the runtime
binaries a target version needs:

  * the version-matched RedPiano mod jar (``redpiano-1.0.0-mc<ver>.jar``) — the one binary
    that ships in the repo's ``binaries/`` folder and is resolved here; and
  * the ``qzpno_mv.zip`` sampled-instrument resourcepack — piano samples are Salamander
    Grand Piano (CC-BY, attribution required), drums are VCSL (CC0), and bass/lead/pad are
    synthesized; the pack **ships separately, NOT in this repo** (see BINARIES.md).
    This tool does not ship it; when a target version needs it, the tool prints exactly how
    to supply your own (``build_resourcepack.py --from-zip <your qzpno_mv.zip>`` or
    ``--samples-root <dir>``, or any other qzpno-shaped pack).

against a manifest (``binaries_manifest.json``) that ships INSIDE the repo snapshot
next to a top-level ``binaries/`` folder. (Fabric API is NOT resolved here — it stays
on prepare_all.py's public Modrinth auto-download.)

Local-first, remote-as-upgrade. The repo is currently PRIVATE, so anonymous raw
downloads do not work: the PRIMARY path is a **local cache hit** — if ``dest`` already
holds a file whose sha256 matches the manifest, it is accepted with no network. Only on
a miss does it fall back to ``base_url`` (the public raw path baked into the manifest,
ready for when the repo goes public); a hash mismatch there deletes the bad file and
fails loudly. So on a fresh repo-snapshot everything is already local and this is an
offline verify; after the repo is public it becomes a real fetcher on the SAME manifest.

Honesty: the manifest records per-jar ``bytecode_checked`` / ``listened`` flags. Only
1.21.8 is ``listened`` (the single in-game anchor); every other jar is bytecode-clean but
NOT yet heard, so the VERDICT tells you to listen once after installing.

Samples are separate: the ``resourcepack`` manifest entry is now just a POINTER (it names
``qzpno_mv.zip`` and carries ``in_repo: false``), because the sampled instruments are not
in this repo. The report always tells you to build/supply the pack yourself; the exit code
depends ONLY on the mod jar (the thing this repo actually ships).

CLI:
  python scripts/fetch_binaries.py --mc-version 1.21.8
  python scripts/fetch_binaries.py --mc-version 1.21.9 --dest /some/binaries
  python scripts/fetch_binaries.py --gen-manifest ../../binaries   # (re)write the manifest
  python scripts/fetch_binaries.py --selftest

Exit codes: 0 = the mod jar is present + verified (the resourcepack is user-supplied and
never fails the run); 1 = the jar is missing/unfetchable; 2 = usage / manifest error.
Pure stdlib.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from redpiano_core import RedPianoError  # noqa: E402

# The public raw base the manifest bakes in (used once the repo is public). It is only a
# DEFAULT — the manifest's own ``base_url`` field wins, and --base-url overrides both.
DEFAULT_BASE_URL = "https://raw.githubusercontent.com/Cohenjikan/McMusicMaker/main/binaries"

MANIFEST_NAME = "binaries_manifest.json"
RP_ZIP_NAME = "qzpno_mv.zip"
# the shared resourcepack's canonical rp_format (1.21.7/1.21.8 anchor); other versions
# derive their pack from this zip with build_resourcepack.py --from-zip.
RP_BASE_FORMAT = 64
# the ONE version whose jar has been confirmed by an in-game listen — every generated
# manifest defaults `listened=false` except this anchor (and preserves prior true flags).
LISTENED_ANCHOR = "1.21.8"


def _default_dest():
    """The repo-snapshot binaries/ folder: <repo>/binaries, i.e. two levels above the
    skill's scripts/ dir. Ships alongside minecraft-redstone-music/."""
    return os.path.normpath(os.path.join(_HERE, "..", "..", "binaries"))


def _default_manifest_path():
    """binaries_manifest.json inside the repo-snapshot binaries/ folder."""
    return os.path.join(_default_dest(), MANIFEST_NAME)


def sha256_file(path):
    """Streaming sha256 hex digest of a file (never loads the whole file into memory)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(manifest_path):
    """Read + validate binaries_manifest.json. Raises RedPianoError on missing/malformed."""
    if not os.path.isfile(manifest_path):
        raise RedPianoError(
            f"binaries manifest not found: {manifest_path}. It ships inside the repo "
            f"snapshot's binaries/ folder; generate one with "
            f"`fetch_binaries.py --gen-manifest <binaries-dir>` (see BINARIES.md)."
        )
    try:
        with open(manifest_path, encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RedPianoError(f"cannot read binaries manifest {manifest_path}: {e}")
    if man.get("schema") != 1:
        raise RedPianoError(
            f"binaries manifest {manifest_path} has schema {man.get('schema')!r}, "
            f"expected 1 (regenerate with --gen-manifest)"
        )
    if "jars" not in man:
        raise RedPianoError(
            f"binaries manifest {manifest_path} is missing 'jars' "
            f"(regenerate with --gen-manifest)"
        )
    return man


def _fetch_remote(url, dest_path):
    """Download ``url`` -> ``dest_path`` (streamed). Raises RedPianoError on any failure.
    The caller verifies sha256 AFTER this and deletes on mismatch."""
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    req = urllib.request.Request(
        url, headers={"User-Agent": "McMusicMaker-fetch-binaries/1.0 (redpiano runtime)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(dest_path, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:  # urllib raises a wide family (URLError/HTTPError/OSError/ssl)
        # do not leave a truncated file behind
        try:
            os.remove(dest_path)
        except OSError:
            pass
        raise RedPianoError(
            f"could not download {url}: {e}. The repo is PRIVATE, so anonymous raw "
            f"downloads fail until it is public — supply the file locally in the binaries "
            f"dir instead (it ships inside the repo snapshot)."
        )


def resolve_one(file_name, want_sha, dest, base_url):
    """Resolve a single binary into ``dest`` and verify its sha256.

    Returns (status, detail):
      status 'local'  -> already in dest with a matching sha256 (the private-repo path).
      status 'fetched'-> downloaded from base_url and sha256-verified.
      status 'missing'-> not local AND could not be fetched/verified (detail explains).
    A downloaded file whose sha256 does NOT match ``want_sha`` is DELETED and reported
    'missing' (never silently trusted)."""
    dest_path = os.path.join(dest, file_name)

    # 1) local cache hit (primary path for a private repo / offline snapshot)
    if os.path.isfile(dest_path):
        got = sha256_file(dest_path)
        if want_sha and got == want_sha:
            return "local", dest_path
        if want_sha:
            # a local file exists but its hash is wrong — do NOT overwrite blindly; the
            # remote fetch below may repair it, but report the mismatch either way.
            local_mismatch = (f"local {file_name} sha256 {got[:12]}.. != manifest "
                              f"{want_sha[:12]}..")
        else:
            # manifest carries no sha for this entry — accept the local file as-is.
            return "local", dest_path
    else:
        local_mismatch = None

    # 2) remote fallback (works once the repo is public; base_url is baked in the manifest)
    if not base_url:
        detail = local_mismatch or f"{file_name} not in {dest} and no base_url to fetch from"
        return "missing", detail
    url = base_url.rstrip("/") + "/" + file_name
    try:
        _fetch_remote(url, dest_path)
    except RedPianoError as e:
        detail = str(e) if local_mismatch is None else f"{local_mismatch}; {e}"
        return "missing", detail
    got = sha256_file(dest_path)
    if want_sha and got != want_sha:
        try:
            os.remove(dest_path)
        except OSError:
            pass
        return "missing", (f"downloaded {file_name} sha256 {got[:12]}.. != manifest "
                           f"{want_sha[:12]}.. — deleted (corrupt/tampered)")
    return "fetched", dest_path


def fetch(mc_version, dest, manifest_path, base_url=None):
    """Resolve the jar + resourcepack for ``mc_version``. Returns a report dict:
      {mc_version, dest, items:[{name,role,status,detail,sha_ok,verified}], jar_row,
       rp_note, ok(bool)}.
    Raises RedPianoError for a usage/manifest problem (no jar row for the version, etc.).
    A per-file miss is reported in the dict (ok=False), NOT raised — the caller maps that
    to exit 1."""
    man = load_manifest(manifest_path)
    base_url = base_url or man.get("base_url") or DEFAULT_BASE_URL

    jars = man["jars"]
    if mc_version not in jars:
        have = ", ".join(sorted(jars.keys())) or "(none)"
        raise RedPianoError(
            f"no RedPiano jar for MC {mc_version} in the manifest (have: {have}). "
            f"Build one with `mod_build.py --mc-version {mc_version} --write` + a Gradle "
            f"build (see BINARIES.md), then `--gen-manifest` to register it — or target a "
            f"version the manifest already carries."
        )
    jar_row = jars[mc_version]
    rp = man.get("resourcepack") or {}

    items = []
    # jar — the ONE binary this repo actually ships and resolves. The exit code hinges on it.
    jstatus, jdetail = resolve_one(jar_row["file"], jar_row.get("sha256"), dest, base_url)
    items.append({
        "name": jar_row["file"], "role": "mod jar", "status": jstatus, "detail": jdetail,
        "bytecode_checked": bool(jar_row.get("bytecode_checked")),
        "listened": bool(jar_row.get("listened")),
    })

    # resourcepack — piano=Salamander Grand Piano (CC-BY, attribution required), drums=VCSL
    # (CC0), bass/lead/pad=synthesized; the pack ships SEPARATELY (not in this repo). We
    # do NOT fail on it. If the manifest still carries a real in-repo entry with a sha (legacy
    # snapshots) AND the file happens to be present locally, we verify it as a courtesy;
    # otherwise we emit a 'separate' status with a clear self-supply pointer.
    rp_file = rp.get("file") or RP_ZIP_NAME
    rp_in_repo = bool(rp.get("in_repo", False))
    rp_sha = rp.get("sha256")
    if rp_in_repo and rp_sha and os.path.isfile(os.path.join(dest, rp_file)):
        rstatus, rdetail = resolve_one(rp_file, rp_sha, dest, base_url)
    else:
        rstatus, rdetail = "separate", _rp_supply_hint(rp_file, dest)
    items.append({
        "name": rp_file, "role": "resourcepack", "status": rstatus, "detail": rdetail,
        "bytecode_checked": None, "listened": None,
    })

    # ok = the jar resolved. The resourcepack is user-supplied, so 'separate' does NOT fail.
    jar_item = items[0]
    ok = jar_item["status"] in ("local", "fetched")
    return {
        "mc_version": mc_version, "dest": dest, "items": items,
        "jar_row": jar_row, "rp_note": rp.get("note", ""), "ok": ok,
    }


def _rp_supply_hint(rp_file, dest):
    """The graceful-degradation guidance printed when the sampled resourcepack is not in the
    repo (piano samples are Salamander Grand Piano CC-BY, drums are VCSL CC0, bass/lead/pad
    are synthesized, and the pack ships separately). Names the exact self-supply
    commands rather than crashing or pretending the pack is available."""
    return (
        f"{rp_file} is NOT in this repo — piano samples are Salamander Grand Piano (CC-BY, "
        f"attribution required), drums are VCSL (CC0), and bass/lead/pad are synthesized; the "
        f"pack ships SEPARATELY (see BINARIES.md). Supply your own pack:\n"
        f"        • have your own qzpno_mv.zip? derive a version-matched pack with:\n"
        f"            python scripts/build_resourcepack.py --from-zip <your qzpno_mv.zip> "
        f"--mc-version <ver> --out dist/qzpno_mv.zip\n"
        f"        • building from sample folders instead:\n"
        f"            python scripts/build_resourcepack.py --samples-root <dir> "
        f"--mc-version <ver> --out dist/qzpno_mv.zip\n"
        f"        • or drop any qzpno-shaped resourcepack into {dest} and pass it as "
        f"--prebuilt-rp.\n"
        f"      (The mod jar above is all this repo ships; without a resourcepack you get "
        f"vanilla note-block tones.)"
    )


# ── --gen-manifest: scan a binaries/ dir and (re)write binaries_manifest.json ──────────

def _parse_ver_from_jar(name):
    """Extract '<ver>' from redpiano-1.0.0-mc<ver>.jar (tolerates a -UNVERIFIED suffix).
    Returns the version string or None if the name is not a RedPiano version jar."""
    low = name.lower()
    if not (low.startswith("redpiano") and low.endswith(".jar")):
        return None
    stem = name[:-len(".jar")]
    marker = "-mc"
    idx = stem.find(marker)
    if idx < 0:
        return None
    ver = stem[idx + len(marker):]
    # drop a trailing -UNVERIFIED (case-insensitive) marker if present
    for suffix in ("-UNVERIFIED", "-unverified"):
        if ver.endswith(suffix):
            ver = ver[:-len(suffix)]
    return ver or None


def gen_manifest(binaries_dir, base_url=None):
    """Scan ``binaries_dir`` and write ``binaries_manifest.json`` into it. Returns the
    manifest dict. The ``listened`` flag is preserved from any existing manifest (so a
    human's in-game confirmation is never overwritten by a rescan); new jars default
    listened=false except the 1.21.8 anchor. Raises RedPianoError if the dir or the
    resourcepack zip is missing."""
    if not os.path.isdir(binaries_dir):
        raise RedPianoError(f"--gen-manifest dir not found: {binaries_dir}")
    base_url = base_url or DEFAULT_BASE_URL

    # preserve prior `listened` flags (in-game confirmations must survive a rescan).
    prior_listened = {}
    existing_path = os.path.join(binaries_dir, MANIFEST_NAME)
    if os.path.isfile(existing_path):
        try:
            with open(existing_path, encoding="utf-8") as f:
                prev = json.load(f)
            for ver, row in (prev.get("jars") or {}).items():
                if row.get("listened"):
                    prior_listened[ver] = True
        except (OSError, json.JSONDecodeError):
            pass  # a corrupt prior manifest is simply ignored (we rewrite it cleanly)

    names = sorted(os.listdir(binaries_dir))

    # resourcepack — piano samples are Salamander Grand Piano (CC-BY, attribution required),
    # drums are VCSL (CC0), and bass/lead/pad are synthesized; the pack ships SEPARATELY, so
    # the zip is normally ABSENT from binaries/. That is NOT an error: we write a POINTER
    # entry (in_repo=false, no sha) so the manifest documents the pack's shape without
    # claiming to carry it. If a local qzpno_mv.zip IS present (a maintainer's own copy),
    # we hash it and mark in_repo=true as a courtesy — but it must never be committed.
    rp_path = os.path.join(binaries_dir, RP_ZIP_NAME)
    if os.path.isfile(rp_path):
        resourcepack = {
            "file": RP_ZIP_NAME,
            "rp_format": RP_BASE_FORMAT,
            "sha256": sha256_file(rp_path),
            "in_repo": True,
            "note": ("local copy present (piano samples = Salamander Grand Piano, CC-BY, "
                     "attribution required; drums = VCSL, CC0; bass/lead/pad = synthesized) "
                     "— do NOT commit; other 1.21.x: repack pack.mcmeta with "
                     "build_resourcepack.py --from-zip"),
        }
    else:
        resourcepack = {
            "file": RP_ZIP_NAME,
            "rp_format": RP_BASE_FORMAT,
            "sha256": None,
            "in_repo": False,
            "note": ("piano samples = Salamander Grand Piano (CC-BY, attribution required); "
                     "drums = VCSL (CC0); bass/lead/pad = synthesized. The qzpno_mv "
                     "resourcepack ships separately (not in this repo); supply your own via "
                     "build_resourcepack.py --from-zip / --samples-root (see BINARIES.md)"),
        }

    # jars
    jars = {}
    for name in names:
        ver = _parse_ver_from_jar(name)
        if ver is None:
            continue
        jars[ver] = {
            "file": name,
            "sha256": sha256_file(os.path.join(binaries_dir, name)),
            "bytecode_checked": True,   # rescanned jars are assumed --check-jar clean
            "listened": bool(prior_listened.get(ver) or ver == LISTENED_ANCHOR),
        }

    manifest = {
        "schema": 1,
        "base_url": base_url,
        "resourcepack": resourcepack,
        "jars": jars,
    }
    with open(existing_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return manifest


# ── reporting ──────────────────────────────────────────────────────────────────────────

def _print_report(report):
    print("=== fetch RedPiano binaries ===")
    print(f"  mc-version : {report['mc_version']}")
    print(f"  dest       : {report['dest']}")
    for it in report["items"]:
        if it["status"] in ("local", "fetched"):
            mark = "✓"
        elif it["status"] == "separate":
            mark = "○"  # user-supplied, not a failure
        else:
            mark = "✗"
        verified = ""
        if it["role"] == "mod jar":
            if it["listened"]:
                verified = " [listened in-game]"
            elif it["bytecode_checked"]:
                verified = " [check-jar clean, NOT yet listened]"
            else:
                verified = " [UNVERIFIED]"
        elif it["role"] == "resourcepack" and it["status"] == "separate":
            verified = " [samples ship separately — supply your own]"
        print(f"  {mark} {it['role']:12s} {it['name']}  ({it['status']}){verified}")
        if it["status"] in ("missing", "separate"):
            print(f"      -> {it['detail']}")
    if report["rp_note"]:
        print(f"  note       : {report['rp_note']}")
    # VERDICT — hinges on the mod jar only (the resourcepack is user-supplied by design).
    if report["ok"]:
        jar = next(i for i in report["items"] if i["role"] == "mod jar")
        if jar["listened"]:
            print("  VERDICT: mod jar present + verified; jar was listened in-game. Install "
                  "it, supply your own qzpno_mv resourcepack (see ○ above), then confirm sound.")
        else:
            print("  VERDICT: mod jar present; jar is check-jar clean but NOT yet listened — "
                  "install it, supply your own qzpno_mv resourcepack (see ○ above), then "
                  "LISTEN ONCE to confirm sound/pitch.")
    else:
        print("  VERDICT: mod jar MISSING (see ✗ above). Supply it locally in the binaries "
              "dir, or (once the repo is public) let base_url fetch it — then supply your own "
              "resourcepack (see ○).")


def build_argparser():
    p = argparse.ArgumentParser(
        prog="fetch_binaries.py",
        description="Resolve the version-matched RedPiano mod jar for a target MC version "
                    "(local-first; remote once the repo is public). The qzpno_mv resourcepack "
                    "(piano = Salamander Grand Piano CC-BY, drums = VCSL CC0, bass/lead/pad = "
                    "synthesized) ships SEPARATELY (not in this repo) — supply your own.")
    p.add_argument("--mc-version", dest="mc_version", default=None,
                   help="target Minecraft version (selects the jar row from the manifest).")
    p.add_argument("--dest", default=None,
                   help="binaries dir to resolve into (default: ../../binaries from here).")
    p.add_argument("--manifest", default=None,
                   help="path to binaries_manifest.json (default: <dest>/.. snapshot copy).")
    p.add_argument("--base-url", dest="base_url", default=None,
                   help="override the remote base URL (default: the manifest's base_url).")
    p.add_argument("--gen-manifest", dest="gen_manifest", default=None, metavar="DIR",
                   help="scan DIR and (re)write binaries_manifest.json into it, then exit.")
    return p


def main(argv=None):
    args = build_argparser().parse_args(argv)
    # normalize --mc-version once at the entry point: fetch()'s `mc_version not in jars`
    # is a bare dict-key lookup (no internal stripping like redpiano_core's
    # get_version_profile), so a trailing space ("1.21.8 ") would otherwise miss a
    # manifest row that is really present.
    if args.mc_version is not None:
        args.mc_version = args.mc_version.strip()

    # --gen-manifest is a standalone maintenance mode.
    if args.gen_manifest is not None:
        try:
            man = gen_manifest(args.gen_manifest, base_url=args.base_url)
        except RedPianoError as e:
            sys.stderr.write(f"error: {e}\n")
            return 2
        out = os.path.join(args.gen_manifest, MANIFEST_NAME)
        print(f"wrote {out}")
        print(f"  base_url    : {man['base_url']}")
        rpm = man["resourcepack"]
        if rpm.get("in_repo"):
            print(f"  resourcepack: {rpm['file']} (rp_format {rpm['rp_format']}, "
                  f"LOCAL copy — piano=Salamander CC-BY/drums=VCSL CC0/bass-lead-pad="
                  f"synthesized, do NOT commit)")
        else:
            print(f"  resourcepack: {rpm['file']} (rp_format {rpm['rp_format']}, "
                  f"ships SEPARATELY — not in repo; supply your own)")
        print(f"  jars        : {len(man['jars'])}")
        for ver in sorted(man["jars"]):
            row = man["jars"][ver]
            flag = "listened" if row["listened"] else "check-jar only"
            print(f"    {ver:8s} -> {row['file']}  ({flag})")
        return 0

    if not args.mc_version:
        sys.stderr.write("error: --mc-version is required (or use --gen-manifest <dir>)\n")
        return 2

    dest = args.dest or _default_dest()
    manifest_path = args.manifest or os.path.join(dest, MANIFEST_NAME)
    # if --dest is given without --manifest, prefer the manifest inside that dest; if
    # neither is given, fall back to the snapshot default (same dir as the default dest).
    if not os.path.isfile(manifest_path) and args.manifest is None:
        manifest_path = _default_manifest_path()

    try:
        report = fetch(args.mc_version, dest, manifest_path, base_url=args.base_url)
    except RedPianoError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2
    _print_report(report)
    return 0 if report["ok"] else 1


# ── self-test ────────────────────────────────────────────────────────────────────────────

def _selftest():
    """tempfile-based: a fake manifest + fake files exercise gen-manifest (no zip) /
    local-hit / hash-mismatch / separate-resourcepack / missing-version. Pure stdlib,
    no network."""
    import tempfile

    def _write(path, data):
        with open(path, "wb") as f:
            f.write(data)

    with tempfile.TemporaryDirectory() as td:
        binaries = os.path.join(td, "binaries")
        os.makedirs(binaries)
        jar_name = "redpiano-1.0.0-mc1.21.8.jar"
        jar_bytes = b"FAKE-REDPIANO-JAR-1.21.8"
        _write(os.path.join(binaries, jar_name), jar_bytes)
        jar_sha = hashlib.sha256(jar_bytes).hexdigest()

        # (0) --gen-manifest with NO qzpno_mv.zip present (the normal open-source state):
        #     it must NOT fail; it writes an in_repo=false pointer resourcepack entry and
        #     still records the jar + marks 1.21.8 listened.
        man = gen_manifest(binaries, base_url="http://127.0.0.1:0/nope")
        assert man["schema"] == 1 and man["jars"]["1.21.8"]["file"] == jar_name
        assert man["jars"]["1.21.8"]["listened"] is True, man["jars"]["1.21.8"]
        assert man["jars"]["1.21.8"]["sha256"] == jar_sha
        assert man["resourcepack"]["in_repo"] is False, man["resourcepack"]
        assert man["resourcepack"]["sha256"] is None, man["resourcepack"]
        assert "separately" in man["resourcepack"]["note"].lower(), man["resourcepack"]
        manifest_path = os.path.join(binaries, MANIFEST_NAME)
        print("ok: --gen-manifest with no qzpno_mv.zip skips the resourcepack (pointer entry)")

        # (1) LOCAL HIT + SEPARATE RP: jar present -> ok True; resourcepack absent -> status
        #     'separate' (NOT a failure) with a self-supply hint. No network.
        rpt = fetch("1.21.8", binaries, manifest_path, base_url="http://127.0.0.1:0/nope")
        assert rpt["ok"] is True, rpt
        jar_item = next(i for i in rpt["items"] if i["role"] == "mod jar")
        rp_item = next(i for i in rpt["items"] if i["role"] == "resourcepack")
        assert jar_item["status"] == "local", jar_item
        assert rp_item["status"] == "separate", rp_item
        assert "ships SEPARATELY" in rp_item["detail"], rp_item
        assert "build_resourcepack.py --from-zip" in rp_item["detail"], rp_item
        print("ok: jar local hit -> ok; resourcepack 'separate' with self-supply guidance")

        # (2) HASH MISMATCH: corrupt the local jar; with a dead base_url the remote repair
        #     also fails, so it must report missing (never silently trust a wrong hash) and
        #     the whole run fails (jar drives ok).
        _write(os.path.join(binaries, jar_name), b"CORRUPTED")
        rpt2 = fetch("1.21.8", binaries, manifest_path, base_url="http://127.0.0.1:0/nope")
        assert rpt2["ok"] is False, rpt2
        jar_item2 = next(i for i in rpt2["items"] if i["role"] == "mod jar")
        assert jar_item2["status"] == "missing" and "sha256" in jar_item2["detail"], jar_item2
        print("ok: local hash mismatch is rejected (reported missing, not trusted)")
        _write(os.path.join(binaries, jar_name), jar_bytes)  # restore for cleanliness

        # (3) COURTESY LOCAL RP: if a maintainer DOES keep a private qzpno_mv.zip in the dir,
        #     --gen-manifest marks it in_repo=true and fetch verifies it as 'local'.
        rp_bytes = b"FAKE-QZPNO-MV-ZIP"
        _write(os.path.join(binaries, RP_ZIP_NAME), rp_bytes)
        man_local = gen_manifest(binaries, base_url="http://127.0.0.1:0/nope")
        assert man_local["resourcepack"]["in_repo"] is True, man_local["resourcepack"]
        assert man_local["resourcepack"]["sha256"] == hashlib.sha256(rp_bytes).hexdigest()
        rpt3 = fetch("1.21.8", binaries, manifest_path, base_url="http://127.0.0.1:0/nope")
        rp_item3 = next(i for i in rpt3["items"] if i["role"] == "resourcepack")
        assert rp_item3["status"] == "local", rp_item3
        os.remove(os.path.join(binaries, RP_ZIP_NAME))  # back to the shipped (no-zip) state
        gen_manifest(binaries, base_url="http://127.0.0.1:0/nope")
        print("ok: a maintainer's private qzpno_mv.zip is verified in_repo (never committed)")

        # (4) MISSING VERSION: a version with no jar row raises a clear usage error.
        try:
            fetch("1.21.99", binaries, manifest_path)
            raise AssertionError("missing version should have raised")
        except RedPianoError as e:
            assert "no RedPiano jar for MC 1.21.99" in str(e), str(e)
            assert "1.21.8" in str(e), str(e)  # names what IS available
        print("ok: unknown version raises with a build-or-switch pointer")

        # (5) missing manifest -> clean error
        try:
            load_manifest(os.path.join(td, "nope", MANIFEST_NAME))
            raise AssertionError("missing manifest should have raised")
        except RedPianoError as e:
            assert "manifest not found" in str(e), str(e)
        print("ok: missing manifest raises cleanly")

    print("fetch_binaries self-test PASSED")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if "--selftest" in sys.argv:
        _selftest()
        sys.exit(0)
    sys.exit(main())
