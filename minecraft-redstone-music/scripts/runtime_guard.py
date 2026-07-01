# -*- coding: utf-8 -*-
"""Minimal, honest runtime guards.

History: an earlier version tried to DETECT the Trae SOLO sandbox (by process
ancestry, PATH markers, etc.) and REFUSE to run. That approach could not work —
a good sandbox is transparent from inside, so the detection false-negatived and
the agent sailed through and deployed into the VMCache mirror anyway; and when it
DID fire it told the agent to "run from a native shell" it does not have. The real
fix is architectural (build in the workspace, install via a native-launched
DEPLOY_TO_GAME.bat + receipt — see ``deploy_bundle.py`` / ``docs/RUNTIME_SANDBOX.md``),
not heuristic detection.

What remains here is the one thing that IS reliable: refusing a path that
LITERALLY resolves under the Trae VMCache mirror (a plain substring test — no
guessing about the runtime). That only catches "someone pasted a VMCache path";
it is not, and cannot be, a general sandbox detector.
"""

import os


TRAE_VMCACHE_MARKER = "\\appdata\\roaming\\trae solo cn\\vmcache\\"


class RuntimeGuardError(Exception):
    """Raised when a target path literally resolves under the Trae VMCache mirror."""


def path_probe(value):
    if not value:
        return ""
    try:
        p = os.path.abspath(os.path.normpath(str(value)))
    except (OSError, ValueError):
        p = str(value)
    return p.replace("/", "\\").lower()


def path_is_under_trae_vmcache(value):
    """True iff ``value`` resolves under %APPDATA%\\Roaming\\TRAE SOLO CN\\VMCache.
    Writes there are a sandbox mirror the real game never reads."""
    return TRAE_VMCACHE_MARKER in path_probe(value)


def require_not_vmcache_targets(targets):
    bad = [p for p in (targets or ()) if path_is_under_trae_vmcache(p)]
    if bad:
        raise RuntimeGuardError(
            f"target {bad[0]} resolves under the Trae VMCache mirror, not the real "
            "game profile. VMCache is a copy-on-write shadow of C:\\; point at the real "
            "C:\\Minecraft\\... path instead. (The real install runs via the native "
            "DEPLOY_TO_GAME.bat that deploy_bundle.py emits.)"
        )
