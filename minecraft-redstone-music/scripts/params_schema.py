# -*- coding: utf-8 -*-
"""params_schema.py — designer-export schema, defaults, and validation for the
RedPiano (Family A) skill.

Implements CONTRACT.md §2 *exactly*. This module is **standalone** — pure stdlib,
no project deps — so it can be imported by ``redpiano_core.py`` and the generators
without pulling in any geometry. The designer (``poc/layout_designer.html``) exports
~26 fields; only a subset is consumed by the v1 generators (``inplace`` / ``swave`` /
``straight`` / ``custom`` / ``multilane``).
Anything a generator does not consume, but is SET to a non-default value, is rejected
loudly (no silent drop). Anything that is exported only as designer preview/metadata
is whitelisted and ignored.

Public surface:
    SCHEMA_VERSION
    RedPianoError                     (re-exported so this file is import-light)
    FIELD_DEFAULTS / FIELD_CONSUMED   (the field table, machine-readable)
    UNIMPLEMENTED                     (designer features with no generator)
    load_params(path_or_dict, form)   (validate + default + cross-form reject)
    assert_supported(params, form)    (hard-fail on unimplemented designer combos)
"""

import json
import os

SCHEMA_VERSION = 1


class RedPianoError(Exception):
    """Raised on any contract violation. Defined here so params_schema has no
    dependency on redpiano_core; redpiano_core re-exports / shares this class."""


# ─────────────────────────────────────────────────────────────────────────────
# §2.1 Field table — full designer export.
#
# Each entry: (default, consumed_by) where consumed_by is a set of forms that
# actually READ the field, or one of the sentinels:
#   "none-yet"       -> exported by designer, NO generator implements it.
#   "ignore"         -> designer preview/metadata, never validated/consumed.
#   "both"           -> read by both inplace and swave (expanded below).
#   "scope-fail"     -> Family B (slice) — generators MUST hard-fail.
#
# A "derived" default is recorded as the sentinel DERIVED so load_params knows the
# real value comes from the MIDI at build time (the designer value is a preview hint
# and is NOT treated as authoritative).
# ─────────────────────────────────────────────────────────────────────────────

DERIVED = object()  # sentinel: real value derived from MIDI at build time

# form-membership sets used below
_ALLF = frozenset({"inplace", "swave", "straight", "custom", "multilane"})
_LINE = frozenset({"swave", "straight", "custom", "multilane"})  # all line/marching forms
_MARCH = frozenset({"swave", "straight", "custom"})   # single folded line, radiate chords
_MULTILANE = frozenset({"multilane"})                 # one parallel lane per voice
_BOTH = _ALLF                  # common fields, read by every form
_INPLACE = frozenset({"inplace"})
_SWAVE = _LINE                 # XRUN/ZMAX/dual/cells/etc. tolerated by all line forms
_CUSTOM = frozenset({"custom"})

# field -> (default_value, consumed_by)
#   consumed_by is a frozenset of forms, or a string sentinel:
#     "none-yet" / "ignore" / "scope-fail"
FIELD_TABLE = {
    # ── common ────────────────────────────────────────────────────────────
    "song":          ("untitled",        _BOTH),
    "form":          (None,              _BOTH),   # required; checked explicitly
    "method":        ("redpiano",        _BOTH),   # 'slice' -> hard fail (§2.2.5)
    "base_block":    ("minecraft:stone", _BOTH),
    "start_x":       (0,                 _BOTH),
    "start_z":       (0,                 _BOTH),
    "start_y":       (255,               _BOTH),
    "start_dir":     ("+X",              _BOTH),   # only +X implemented (§2.4)
    "signal_tracks": (None,              _MULTILANE),  # parallel repeater chains; consumes full 3D offset {dx,dy,dz} (multilane.py emit_chain)
    "protection":    (None,              _LINE),   # barrier-shell (prosetup) — all line forms + multilane; validated shape in assert_supported
    # ── inplace-only ──────────────────────────────────────────────────────
    "palette_noteblocks": (DERIVED,      _INPLACE),  # preview hint; real size derived
    "PCOLS":              (16,           _INPLACE),
    "ROWGAP":             (3,            _INPLACE),
    "multi":              (True,         _INPLACE),  # multi-instrument (default) vs multi:false piano-only single
    # ── swave-only ────────────────────────────────────────────────────────
    "cells":              (DERIVED,      _SWAVE),  # preview; real count derived
    "sounding":           (DERIVED,      _SWAVE),  # preview; real count derived
    "XRUN":               (3,            _SWAVE),  # poc/48 default; designer hint 6
    "ZMAX":               (4,            _SWAVE),  # poc/48 default; designer hint 10
    "line_width_radiate": (3,            "none-yet"),
    "fold_gap":           (1,            "none-yet"),
    "dual_track_mirror":  (True,         _SWAVE),
    "track_sep":          (DERIVED,      _SWAVE),  # default PATH_ZSPAN+3, derived
    "chord_mode":         ("radiate",    _SWAVE),  # 'multilane' selects the multilane form
    "max_poly":           (7,            _MULTILANE),
    "lane_dz":            (2,            _MULTILANE),
    "lane_offsets":       (None,         _MULTILANE),
    "side_view":          (False,        "ignore"),  # render toggle, not a build param
    # ── §E cam-follow tuning([跟拍]相机锚点微调, line 形态; inplace 无相机) ──
    "cam_height":         (10,           _LINE),   # 相机悬停高度 (start_y + cam_height)
    "cam_back":           (6.0,          _LINE),   # 相机沿作者系 -X 退后量
    "cam_dz":             (0.0,          _LINE),   # 相机相对自动中线的横向偏移(作者系 +Z)
    # ── slice-only (Family B, OUT OF SCOPE) ───────────────────────────────
    "audio_file":     (None,  "scope-fail"),
    "audio_duration": (0,     "scope-fail"),
    "tick_rate":      (20,    "scope-fail"),
    "waypoints":      (None,  _CUSTOM),   # form=custom: the drawn route
    # ── designer metadata (ignored on load) ───────────────────────────────
    "schema_version": (SCHEMA_VERSION, "ignore"),  # designer stamps this on every export
    "result":     (None, "ignore"),
    "bbox_cells": (None, "ignore"),
    "slice_note": (None, "ignore"),
}

# convenience views
FIELD_DEFAULTS = {k: v[0] for k, v in FIELD_TABLE.items()}
FIELD_CONSUMED = {k: v[1] for k, v in FIELD_TABLE.items()}

# fields that are pure designer preview/metadata and never trigger cross-form
# rejection regardless of value.
_IGNORABLE = frozenset(k for k, c in FIELD_CONSUMED.items() if c == "ignore")

# the v1 forms: inplace + the marching-pulse family (swave / straight / custom) + multilane
_VALID_FORMS = _ALLF


# ─────────────────────────────────────────────────────────────────────────────
# §2.3 UNIMPLEMENTED — designer features with no generator. assert_supported()
# raises with the matching message if any of these is set to a non-default.
# ─────────────────────────────────────────────────────────────────────────────
UNIMPLEMENTED = {
    "chord_mode == 'multilane'":     "chord_mode=multilane is not a swave/straight/custom option (those use radiate) — use --form multilane instead",
    "line_width_radiate != 3":       "radiate width is fixed at 3 (above + 2 sides)",
    "fold_gap / plane-fold":         "fold_gap/plane-fold is not wired into swave/straight/custom",
    "method == 'slice'":             "Family B audio slice out of scope",
    "max_poly/lane_dz/lane_offsets": "max_poly/lane_dz/lane_offsets are multilane-only — use --form multilane (they don't apply to swave/straight/custom)",
}

# the four supported play directions (start_dir). +X is the authored geometry; -X/+Z/-Z
# are produced by a rotation transform applied at emit time (redpiano_core.rotate_command).
VALID_DIRS = ("+X", "-X", "+Z", "-Z")


def _is_set_nondefault(params, key):
    """True iff ``key`` is present in params with a value differing from its default.
    DERIVED defaults are never 'set to a non-default' for cross-form purposes — the
    real value comes from the MIDI, and the designer's preview number is advisory."""
    if key not in params:
        return False
    default = FIELD_DEFAULTS.get(key, None)
    if default is DERIVED:
        return False
    return params[key] != default


def load_params(path_or_dict, form):
    """Validate, default, and normalize a designer params dict for the chosen ``form``.

    Implements CONTRACT.md §2.2. Steps:
      1. accept a JSON file path or an already-parsed dict;
      2. validate ``form`` is one of {inplace, swave, straight, custom, multilane}
         (any other -> RedPianoError);
      3. apply defaults from the field table for the chosen form;
      4. required-field check: a ``form`` in the dict must match the ``form`` arg;
         ``method`` must be 'redpiano';
      5. ``method == 'slice'`` -> HARD FAIL (Family B out of scope);
      6. cross-form rejection: any field SET to a non-default but NOT consumed by
         ``form`` raises (designer-metadata fields are whitelisted);
      7. return the normalized, defaulted dict.

    Returns a fresh dict (input is never mutated).
    """
    # 1. accept path or dict
    if isinstance(path_or_dict, str):
        if not os.path.isfile(path_or_dict):
            raise RedPianoError(f"params file not found: {path_or_dict}")
        with open(path_or_dict, encoding="utf-8") as f:
            try:
                raw = json.load(f)
            except json.JSONDecodeError as e:
                raise RedPianoError(f"params file {path_or_dict} is not valid JSON: {e}")
        if not isinstance(raw, dict):
            raise RedPianoError(f"params JSON must be an object, got {type(raw).__name__}")
    elif isinstance(path_or_dict, dict):
        raw = dict(path_or_dict)  # shallow copy; never mutate caller's dict
    else:
        raise RedPianoError(
            f"load_params expects a path (str) or dict, got {type(path_or_dict).__name__}"
        )

    # 2. validate the form argument
    if form not in _VALID_FORMS:
        raise RedPianoError(
            f"unknown form '{form}'; expected one of {sorted(_VALID_FORMS)}"
        )

    # 4a. if the dict carries its own 'form', it must agree with the form arg
    if "form" in raw and raw["form"] is not None:
        if raw["form"] != form:
            raise RedPianoError(
                f"params.form '{raw['form']}' disagrees with requested form '{form}'"
            )

    # 5. method == slice -> Family B hard fail (check on the RAW value before defaulting)
    method = raw.get("method", FIELD_DEFAULTS["method"])
    if method == "slice":
        raise RedPianoError(
            "method=slice (Family B audio-slice) is out of scope for this skill — "
            "use the external mc-noteblock-demo repo"
        )
    # 4b. method must be redpiano (the only other accepted value)
    if method != "redpiano":
        raise RedPianoError(
            f"unknown method '{method}'; only 'redpiano' (Family A) is supported"
        )

    # 6. cross-form rejection — any non-default field not consumed by this form.
    #    Run BEFORE applying defaults so we only judge what the user actually set.
    for key, value in raw.items():
        if key == "form" or key == "method":
            continue
        if key in _IGNORABLE:
            continue
        if key not in FIELD_TABLE:
            # unknown key: reject as unsupported for this form (no silent drop)
            raise RedPianoError(
                f"field '{key}' is not a known param (unsupported by form '{form}')"
            )
        consumed = FIELD_CONSUMED[key]
        if isinstance(consumed, frozenset):
            if form in consumed:
                continue  # consumed by this form -> fine
            # consumed by the *other* form only -> reject if set to a non-default
            if _is_set_nondefault(raw, key):
                raise RedPianoError(
                    f"field '{key}' is not supported by form '{form}'"
                )
        else:
            # sentinel: 'none-yet' / 'scope-fail' -> not consumed by ANY v1 generator.
            # scope-fail (slice fields) already handled for method; the remaining
            # slice-only fields and none-yet fields reject when set non-default.
            if _is_set_nondefault(raw, key):
                if consumed == "scope-fail":
                    raise RedPianoError(
                        f"field '{key}' belongs to Family B (slice) and is out of scope"
                    )
                raise RedPianoError(
                    f"field '{key}' is not supported by form '{form}'"
                )

    # 3 + 7. build the normalized dict: defaults first, then user overrides.
    out = {}
    for key, default in FIELD_DEFAULTS.items():
        out[key] = None if default is DERIVED else default
    for key, value in raw.items():
        if key in _IGNORABLE and key not in out:
            # keep ignorable metadata out of the build dict entirely
            continue
        out[key] = value
    out["form"] = form  # normalize to the requested form
    out["method"] = "redpiano"
    out["schema_version"] = SCHEMA_VERSION
    return out


def assert_supported(params, form):
    """Hard-fail (RedPianoError) if any UNIMPLEMENTED designer feature is set to a
    non-default value. Generators call this FIRST, before emitting a single block,
    so an unsupported designer JSON fails loudly at the top — not mid-build.

    Implements CONTRACT.md §2.3. ``params`` is assumed already normalized by
    ``load_params`` (defaults applied), but this is robust to a raw dict too.
    """
    if form not in _VALID_FORMS:
        raise RedPianoError(
            f"unknown form '{form}'; expected one of {sorted(_VALID_FORMS)}"
        )

    def _get(key):
        return params.get(key, FIELD_DEFAULTS.get(key))

    # method == slice (defensive — load_params already rejects this)
    if _get("method") == "slice":
        raise RedPianoError(UNIMPLEMENTED["method == 'slice'"])

    # start_dir: all four cardinals are supported (the +X-authored geometry is rotated at
    # emit time by redpiano_core.rotate_command). Validate the value; reject unknowns.
    if _get("start_dir") not in (None,) + VALID_DIRS:
        raise RedPianoError(
            f"start_dir must be one of {' / '.join(VALID_DIRS)} (got {_get('start_dir')!r})"
        )

    # §E cam-follow tuning: 数值旋钮([跟拍]相机锚点微调); 非数值硬失败, 不静默建坏相机。
    for _ck in ("cam_height", "cam_back", "cam_dz"):
        _cv = _get(_ck)
        if _cv is not None and (isinstance(_cv, bool) or not isinstance(_cv, (int, float))):
            raise RedPianoError(f"{_ck} must be a number (got {_cv!r})")

    # signal_tracks: multilane now consumes the FULL 3D offset (dx/dy/dz). Validate the
    # shape AND each element — a bad JSON (e.g. [1,2,3] instead of a list of objects)
    # would otherwise sail through here and crash multilane.py L194 with a raw
    # AttributeError ('int' object has no attribute 'get'), breaking the "clean one-line
    # error, never a traceback" contract. Reject non-dict / non-numeric offsets loudly.
    sig = _get("signal_tracks")
    if sig is not None:
        if not isinstance(sig, (list, tuple)):
            raise RedPianoError("signal_tracks must be a list of {dx,dy,dz} offset objects")
        for i, sg in enumerate(sig):
            if not isinstance(sg, dict):
                raise RedPianoError(
                    f"signal_tracks[{i}] must be a {{dx,dy,dz}} object, got "
                    f"{type(sg).__name__}"
                )
            for axis in ("dx", "dy", "dz"):
                if axis not in sg:
                    continue
                val = sg[axis]
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    raise RedPianoError(
                        f"signal_tracks[{i}].{axis} must be a number, got "
                        f"{type(val).__name__}"
                    )

    # protection (barrier-shell / prosetup): all line forms + multilane consume it. Validate
    # the SHAPE here so a malformed block raises a single clean RedPianoError up front instead
    # of crashing the generator's fill-segmenter mid-build ("clean one-line error, never a
    # traceback" contract). None / absent = feature off (zero-diff), never validated.
    prot = _get("protection")
    if prot is not None:
        if not isinstance(prot, dict):
            raise RedPianoError(
                'protection must be an object, e.g. {"enabled":true,'
                '"block":"minecraft:barrier","margin_xz":3,"floor_margin":2,'
                '"headroom":5,"clear_interior":true} (got '
                f"{type(prot).__name__})")
        _prot_allowed = {"enabled", "block", "margin_xz", "floor_margin",
                         "headroom", "clear_interior"}
        _extra = set(prot) - _prot_allowed
        if _extra:
            raise RedPianoError(
                f"protection has unknown key(s) {sorted(_extra)}; allowed keys are "
                f"{sorted(_prot_allowed)}")
        for _k in ("enabled", "clear_interior"):
            if _k in prot and not isinstance(prot[_k], bool):
                raise RedPianoError(
                    f"protection.{_k} must be true/false, got "
                    f"{type(prot[_k]).__name__}")
        for _k in ("margin_xz", "floor_margin", "headroom"):
            if _k in prot:
                _v = prot[_k]
                # bool is an int subclass — reject it explicitly (a margin isn't true/false)
                if isinstance(_v, bool) or not isinstance(_v, int) or _v < 0:
                    raise RedPianoError(
                        f"protection.{_k} must be a non-negative integer, got {_v!r}")
        if "block" in prot and not isinstance(prot["block"], str):
            raise RedPianoError(
                f"protection.block must be a string block id, got "
                f"{type(prot['block']).__name__}")

    # form=custom REQUIRES a non-empty waypoints route — fail fast here (step 3) instead
    # of letting the build run MIDI-parse + melody-cut planning and only crash mid-way in
    # the generator, which violates the documented "fail fast custom" contract (§4).
    if form == "custom":
        wps = _get("waypoints")
        if not isinstance(wps, (list, tuple)) or not wps:
            raise RedPianoError(
                "custom form requires params['waypoints'] to be a non-empty list of "
                "route points ({x,z} or [x,z]) — draw a route in the designer"
            )

    # marching-pulse (swave/straight/custom) unimplemented features
    if form in _MARCH:
        if _get("chord_mode") == "multilane":
            raise RedPianoError(UNIMPLEMENTED["chord_mode == 'multilane'"])
        if _get("line_width_radiate") not in (None, 3):
            raise RedPianoError(UNIMPLEMENTED["line_width_radiate != 3"])
        # plane-fold / fold_gap not wired in swave
        if _get("fold_gap") not in (None, 1):
            raise RedPianoError(UNIMPLEMENTED["fold_gap / plane-fold"])
        # multilane params unused
        if (_get("max_poly") not in (None, 7)
                or _get("lane_dz") not in (None, 2)
                or _get("lane_offsets") not in (None,)):
            raise RedPianoError(UNIMPLEMENTED["max_poly/lane_dz/lane_offsets"])


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    def expect_raise(fn, needle=None, label=""):
        try:
            fn()
        except RedPianoError as e:
            if needle and needle not in str(e):
                raise AssertionError(f"{label}: wrong message {e!r} (want '{needle}')")
            print(f"  ok (raised): {label} -> {e}")
            return
        raise AssertionError(f"{label}: expected RedPianoError, none raised")

    # defaults applied, no params
    p = load_params({}, "inplace")
    assert p["PCOLS"] == 16 and p["ROWGAP"] == 3, p
    assert p["form"] == "inplace" and p["method"] == "redpiano"
    assert p["schema_version"] == SCHEMA_VERSION
    print("ok: inplace defaults", {k: p[k] for k in ("PCOLS", "ROWGAP", "start_dir")})

    p = load_params({"XRUN": 6, "ZMAX": 10}, "swave")
    assert p["XRUN"] == 6 and p["ZMAX"] == 10, p
    print("ok: swave overrides", {k: p[k] for k in ("XRUN", "ZMAX")})

    # cross-form rejection: inplace field under swave
    expect_raise(lambda: load_params({"PCOLS": 20}, "swave"),
                 "not supported by form 'swave'", "PCOLS under swave")
    expect_raise(lambda: load_params({"XRUN": 8}, "inplace"),
                 "not supported by form 'inplace'", "XRUN under inplace")

    # slice -> hard fail
    expect_raise(lambda: load_params({"method": "slice"}, "inplace"),
                 "out of scope", "method=slice")

    # custom form now loads (with a route); straight loads too
    pc = load_params({"form": "custom",
                      "waypoints": [{"x": 0, "z": 0}, {"x": 8, "z": 0}, {"x": 8, "z": 6}]},
                     "custom")
    assert pc["form"] == "custom" and pc["waypoints"], pc
    print("ok: custom loads with waypoints")
    ps = load_params({"XRUN": 6}, "straight")  # marching field tolerated by straight
    assert ps["form"] == "straight", ps
    print("ok: straight loads (marching fields tolerated)")

    # form disagreement
    expect_raise(lambda: load_params({"form": "swave"}, "inplace"),
                 "disagrees", "form mismatch")

    # default values are NOT rejected even when the field belongs to the other form
    p = load_params({"PCOLS": 16}, "swave")  # PCOLS==default -> allowed (no-op)
    print("ok: default-valued cross-form field tolerated")

    # assert_supported: start_dir — all 4 cardinals now PASS; an invalid one raises
    for d in ("+X", "-X", "+Z", "-Z"):
        assert_supported(load_params({}, "inplace") | {"start_dir": d}, "inplace")
    print("ok: all 4 start_dir cardinals pass assert_supported")
    expect_raise(lambda: assert_supported(load_params({}, "inplace") | {"start_dir": "+Y"}, "inplace"),
                 "start_dir must be one of", "invalid start_dir rejected")
    # assert_supported: multilane
    expect_raise(lambda: assert_supported(load_params({}, "swave") | {"chord_mode": "multilane"}, "swave"),
                 "multilane", "chord_mode multilane")

    # K1: signal_tracks per-element validation — a bad JSON must raise RedPianoError
    # (naming the offending index) rather than crash the multilane generator with a
    # raw AttributeError.
    expect_raise(lambda: assert_supported(load_params({"signal_tracks": [1, 2, 3]}, "multilane"), "multilane"),
                 "signal_tracks[0]", "signal_tracks bare ints")
    expect_raise(lambda: assert_supported(load_params({"signal_tracks": [{"dz": 2}, "nope"]}, "multilane"), "multilane"),
                 "signal_tracks[1]", "signal_tracks non-dict element")
    expect_raise(lambda: assert_supported(load_params({"signal_tracks": [{"dx": "5"}]}, "multilane"), "multilane"),
                 "signal_tracks[0].dx", "signal_tracks non-numeric offset")
    # a well-formed signal_tracks passes
    assert_supported(load_params({"signal_tracks": [{"dx": 5, "dy": 3, "dz": 10}, {"dz": 2}]}, "multilane"), "multilane")
    print("ok: signal_tracks per-element validation")

    # K2: custom REQUIRES non-empty waypoints — fail fast in assert_supported
    expect_raise(lambda: assert_supported(load_params({"form": "custom"}, "custom"), "custom"),
                 "waypoints", "custom missing waypoints")
    expect_raise(lambda: assert_supported(load_params({"form": "custom", "waypoints": []}, "custom"), "custom"),
                 "waypoints", "custom empty waypoints")
    assert_supported(load_params({"form": "custom",
                                  "waypoints": [{"x": 0, "z": 0}, {"x": 8, "z": 0}]}, "custom"), "custom")
    print("ok: custom waypoints fail-fast in assert_supported")
    # a clean normalized dict passes assert_supported
    assert_supported(load_params({"XRUN": 6}, "swave"), "swave")
    assert_supported(load_params({"PCOLS": 24}, "inplace"), "inplace")
    print("ok: assert_supported passes clean params")

    # K3: protection (barrier-shell) — consumed by all line forms + multilane; inplace rejects.
    _prot_ok = {"enabled": True, "block": "minecraft:barrier", "margin_xz": 3,
                "floor_margin": 2, "headroom": 5, "clear_interior": True}
    for _f in ("swave", "straight", "multilane"):
        assert_supported(load_params({"protection": dict(_prot_ok)}, _f), _f)
    # a partial dict (defaults filled by the generator) also validates
    assert_supported(load_params({"protection": {"enabled": True}}, "straight"), "straight")
    # a disabled shell validates too (still a well-formed dict)
    assert_supported(load_params({"protection": {"enabled": False}}, "multilane"), "multilane")
    print("ok: well-formed protection passes on line forms + multilane")
    # cross-form: protection is NOT an inplace field -> load_params rejects a non-default
    expect_raise(lambda: load_params({"protection": dict(_prot_ok)}, "inplace"),
                 "not supported by form 'inplace'", "protection under inplace")
    # malformed shapes each raise a clean one-liner (never a generator traceback)
    expect_raise(lambda: assert_supported(load_params({"protection": [1, 2]}, "swave"), "swave"),
                 "protection must be an object", "protection not a dict")
    expect_raise(lambda: assert_supported(load_params({"protection": {"bogus": 1}}, "swave"), "swave"),
                 "unknown key", "protection unknown key")
    expect_raise(lambda: assert_supported(load_params({"protection": {"enabled": 1}}, "swave"), "swave"),
                 "protection.enabled must be true/false", "protection.enabled non-bool")
    expect_raise(lambda: assert_supported(load_params({"protection": {"clear_interior": "yes"}}, "swave"), "swave"),
                 "protection.clear_interior must be true/false", "protection.clear_interior non-bool")
    expect_raise(lambda: assert_supported(load_params({"protection": {"margin_xz": -1}}, "swave"), "swave"),
                 "protection.margin_xz must be a non-negative integer", "protection.margin_xz negative")
    expect_raise(lambda: assert_supported(load_params({"protection": {"headroom": 2.5}}, "swave"), "swave"),
                 "protection.headroom must be a non-negative integer", "protection.headroom float")
    expect_raise(lambda: assert_supported(load_params({"protection": {"floor_margin": True}}, "swave"), "swave"),
                 "protection.floor_margin must be a non-negative integer", "protection.floor_margin bool")
    expect_raise(lambda: assert_supported(load_params({"protection": {"block": 12}}, "swave"), "swave"),
                 "protection.block must be a string", "protection.block non-str")
    print("ok: malformed protection each raise a clean RedPianoError")

    print("params_schema self-test PASSED")
