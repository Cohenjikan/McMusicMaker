#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_particles.py — Task 6 consumer: particle_keyframes JSON  ->  datapack.

Pairs with skill/designer/particle_editor.html, which exports a
``particle_keyframes`` v1 JSON: per-keyframe music time (t_sec / music_tick /
cell), the pulse world coordinate (playhead), and a list of command blocks
(type / abs-or-rel position / command). This generator turns that into a Family-A
datapack that fires each command at the right GAME-TICK (synced to the song) at
the right world coordinate.

Why scheduled functions instead of physically-placed command blocks:
  Timed, music-synced firing of *physical* command blocks needs a redstone clock
  + per-tick selection logic and is fragile. Scheduled functions are the robust,
  exact equivalent — each keyframe becomes ``schedule function <ns>:k/<id> <Δt>t``
  off a single fire, so every command lands on its own game-tick. The editor's
  "command block" (type / position / command) maps 1:1 to one scheduled command;
  ``type`` is carried through but v1 fires each once (repeat = add keyframes).

Timing model (matches the music machine, /tick rate 80):
  1 music cell = 2 game-ticks = 0.025s real  => delay_gt = round(t_sec * tps).
  The editor quantized note times at the same U=2/80, so t_sec aligns with where
  the pulse is. ``--offset-gt`` shifts all firings by a constant if you observe a
  lead/lag in-game (same calibration knob as the melody-cut).

Sync:
  --music-ns <NS>  auto-fires particles on the rising edge of the music's PLAY
                   scoreboard (the music machine sets ``scoreboard players set
                   PLAY <NS> 1`` on play) — particles start exactly with the song,
                   and stop when the song stops. Without it, a [粒子播放]/[停止]
                   console sign triggers them manually.

Robustness reuses redpiano_core: pack_format + folder come from the version table
(unknown --mc-version hard-fails, no hardcoded 81); deploy is opt-in (--world-dir;
default writes build/ only).
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import redpiano_core as core  # noqa: E402
from redpiano_core import RedPianoError  # noqa: E402

SCHEMA_VERSION = 1


# ───────────────────────────── input ─────────────────────────────

def load_keyframes(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RedPianoError("particle JSON must be an object")
    if data.get("kind") != "particle_keyframes":
        raise RedPianoError(
            f"not a particle_keyframes file (kind={data.get('kind')!r}); "
            f"export it from skill/designer/particle_editor.html"
        )
    sv = data.get("schema_version")
    if sv != SCHEMA_VERSION:
        raise RedPianoError(
            f"schema_version {sv} != {SCHEMA_VERSION} (this build_particles); "
            f"re-export from a matching particle_editor.html"
        )
    kfs = data.get("keyframes")
    if not isinstance(kfs, list) or not kfs:
        raise RedPianoError("no keyframes in file — nothing to build")
    return data


def block_command(block):
    """Build the runnable command for one block: ``execute positioned X Y Z run
    <command>``. Uses the editor-resolved absolute ``pos`` (already accounts for
    rel-to-playhead). Strips a leading slash. Falls back to the raw command if no
    position is present."""
    cmd = (block.get("command") or "").strip()
    if cmd.startswith("/"):
        cmd = cmd[1:]
    if not cmd:
        return None
    pos = block.get("pos")
    if isinstance(pos, (list, tuple)) and len(pos) == 3:
        x, y, z = pos
        return f"execute positioned {x} {y} {z} run {cmd}"
    return cmd


# ───────────────────────────── build ─────────────────────────────

def build(data, ns, out_dir, mc_version, *, music_ns=None, offset_gt=0,
          tps=None, console_origin=None, deploy_dir=None):
    name = data.get("song") or ns
    tps = tps or int(data.get("tps", 80) or 80)
    layout = data.get("linked_layout") or {}
    if console_origin is None:
        ox = int(layout.get("OX", 0))
        oy = int(layout.get("OY", 255))
        oz = int(layout.get("OZ", 0))
        console_origin = (ox, oy, oz - 6)   # offset off the machine spine
    cx, cy, cz = console_origin

    dp = core.Datapack(ns, name, out_dir, mc_version)

    # --- per-keyframe schedule plan -------------------------------------------
    kfs = data["keyframes"]
    plan = []          # (kid, delay_gt, [command,...])
    total_blocks = 0
    skipped = 0
    for i, kf in enumerate(kfs):
        kid = kf.get("id", i)
        t_sec = float(kf.get("t_sec", 0.0))
        # prefer the quantized music_tick (*2 game-ticks/cell) for pulse alignment
        mt = kf.get("music_tick")
        if isinstance(mt, (int, float)):
            delay = int(round(mt)) * 2
        else:
            delay = int(round(t_sec * tps))
        delay = max(1, delay + int(offset_gt))   # schedule needs >= 1t
        cmds = []
        for b in (kf.get("blocks") or []):
            line = block_command(b)
            if line:
                cmds.append(line)
            else:
                skipped += 1
        if cmds:
            plan.append((kid, delay, cmds))
            total_blocks += len(cmds)
    if not plan:
        raise RedPianoError("every keyframe was empty / had no valid command")

    # --- keyframe functions ----------------------------------------------------
    # k/<id>  = guarded entry (only runs while PF==1); kb/<id> = raw commands.
    for kid, delay, cmds in plan:
        dp.write_function(f"kb/{kid}", cmds)
        dp.write_function(f"k/{kid}", [
            f"execute if score PF {ns} matches 1 run function {ns}:kb/{kid}"
        ])

    # --- fire / clearall / stop ------------------------------------------------
    clearall = [f"schedule clear {ns}:k/{kid}" for kid, _, _ in plan]
    dp.write_function("clearall", clearall or ["# nothing to clear"])

    fire = [
        f"function {ns}:clearall",
        f"scoreboard players set PF {ns} 1",
    ]
    for kid, delay, _ in plan:
        fire.append(f"schedule function {ns}:k/{kid} {delay}t append")
    fire.append(
        f'tellraw @a ["",{{"text":"[{ns}] 粒子轨道开始 ","color":"light_purple"}},'
        f'{{"text":"{len(plan)} 帧 / {total_blocks} 命令","color":"gray"}}]'
    )
    dp.write_function("fire", fire)

    dp.write_function("stop", [
        f"scoreboard players set PF {ns} 0",
        f"function {ns}:clearall",
        f'tellraw @a [{{"text":"[{ns}] 粒子停止","color":"gray"}}]',
    ])

    # --- load / tick -----------------------------------------------------------
    load = [
        f"scoreboard objectives add {ns} dummy",
        f"scoreboard players set PF {ns} 0",
    ]
    if music_ns:
        load += [
            f"scoreboard players set PREV {ns} 0",
            f"scoreboard players set MP {ns} 0",
        ]
    load.append(
        f'tellraw @a ["",{{"text":"[{ns}] {name} 粒子轨道 loaded. ","color":"light_purple"}},'
        + (f'{{"text":"自动跟随 {music_ns} 的[播放](若按播放无粒子: 确认 {music_ns} '
           f'是音乐机器的命名空间且已 /reload)","color":"gray"}}]'
           if music_ns else
           f'{{"text":"/function {ns}:setup -> 牌子 [粒子播放]","color":"gray"}}]')
    )
    dp.write_function("load", load)

    if music_ns:
        # auto-sync: rising edge of music PLAY -> fire; falling edge -> stop.
        # `get` of a missing objective fails -> store result writes 0 -> safe.
        tick = [
            f"execute store result score MP {ns} run scoreboard players get PLAY {music_ns}",
            f"execute if score MP {ns} matches 1 if score PREV {ns} matches 0 run function {ns}:fire",
            f"execute if score MP {ns} matches 0 if score PREV {ns} matches 1 run function {ns}:stop",
            f"scoreboard players operation PREV {ns} = MP {ns}",
        ]
    else:
        tick = ["# no --music-ns: particles are triggered by the [粒子播放] sign"]
    dp.write_function("tick", tick)

    # --- setup / cleanup (console signs) --------------------------------------
    # Two labeled buttons: [粒子播放] -> fire, [停止] -> stop. Spaced by 4 in Z so
    # the 5-block widgets (which span oz and oz-2) don't overlap.
    setup = [
        f'tellraw @a [{{"text":"[{ns}] building 粒子控制台...","color":"gray"}}]',
        f"scoreboard objectives add {ns} dummy",
        f"scoreboard players set PF {ns} 0",
    ]
    sd = dp.profile.sign_dialect   # version-aware sign NBT (string <=1.21.4 / SNBT >=1.21.5)
    setup += core.labeled_button(cx, cy, cz, f"function {ns}:fire",
                                 [f"{name}", "粒子轨道", "[粒子播放]", ""], sign_dialect=sd)
    setup += core.labeled_button(cx, cy, cz - 4, f"function {ns}:stop",
                                 ["", "粒子", "[停止]", ""], sign_dialect=sd)
    setup += [
        f"setblock {cx} {cy} {cz + 2} minecraft:redstone_lamp",
        f"tp @a {cx} {cy} {cz + 4}",
        f'tellraw @a [{{"text":"[{ns}] 控制台 built @ {cx} {cy} {cz}","color":"green"}}]',
    ]
    dp.write_function("setup", setup)

    cleanup = [
        f"scoreboard players set PF {ns} 0",
        f"function {ns}:clearall",
        f"fill {cx - 1} {cy - 1} {cz + 2} {cx + 1} {cy + 1} {cz - 7} minecraft:air",
        f"scoreboard objectives remove {ns}",
        f'tellraw @a [{{"text":"[{ns}] 粒子轨道 cleaned up","color":"gray"}}]',
    ]
    dp.write_function("cleanup", cleanup)

    # --- pack meta + tags ------------------------------------------------------
    desc = f"{ns} 粒子/命令方块 关键帧轨道 ({len(plan)}帧/{total_blocks}命令" \
           + (f", 跟随 {music_ns}" if music_ns else "") + ")"
    dp.write_pack_mcmeta(desc)
    dp.write_load_tick_tags()

    deployed = dp.deploy(deploy_dir) if deploy_dir else None

    return {
        "ns": ns,
        "out": dp.root,
        "deployed": deployed,
        "keyframes": len(plan),
        "commands": total_blocks,
        "skipped_empty": skipped,
        "tps": tps,
        "offset_gt": int(offset_gt),
        "music_ns": music_ns,
        "console_origin": [cx, cy, cz],
        "max_delay_gt": max((d for _, d, _ in plan), default=0),
    }


# ───────────────────────────── CLI ─────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build a particle/command-block keyframe datapack from a "
                    "particle_editor.html export. Default = write build/<ns>/ only; "
                    "pass --world-dir to deploy into a world."
    )
    ap.add_argument("--keyframes", required=True,
                    help="particle_keyframes JSON exported by particle_editor.html")
    ap.add_argument("--ns", required=True, help="datapack namespace (also scoreboard objective)")
    ap.add_argument("--mc-version", default="1.21.8",
                    help="target Minecraft version (drives pack_format + folders; "
                         "unknown -> hard fail). Default 1.21.8")
    ap.add_argument("--music-ns", default=None,
                    help="namespace of the music machine; auto-fires particles on its "
                         "PLAY rising edge (perfect sync). Omit = manual sign trigger.")
    ap.add_argument("--offset-gt", type=int, default=0,
                    help="constant game-tick shift applied to every firing "
                         "(calibrate if particles lead/lag the music). Default 0")
    ap.add_argument("--console-origin", nargs=3, type=int, metavar=("X", "Y", "Z"),
                    default=None, help="where to place the [粒子播放] console "
                                       "(default: linked_layout origin, Z-6)")
    ap.add_argument("--out", default="build", help="output dir (default build/)")
    ap.add_argument("--world-dir", default=None,
                    help="world datapacks/ dir; only then is the pack deployed")
    args = ap.parse_args(argv)

    try:
        data = load_keyframes(args.keyframes)
        profile = core.get_version_profile(args.mc_version)  # hard-fail on unknown / below floor
        core.assert_build_supported(profile)                 # green band only (match the music build)
        stats = build(
            data, args.ns, args.out, args.mc_version,
            music_ns=args.music_ns, offset_gt=args.offset_gt,
            console_origin=tuple(args.console_origin) if args.console_origin else None,
            deploy_dir=args.world_dir,
        )
    except RedPianoError as e:
        ap.error(str(e))
        return 2
    except (OSError, json.JSONDecodeError) as e:
        ap.error(f"could not read keyframes file: {e}")
        return 2

    print("─" * 64)
    print(f"  粒子轨道 datapack: {stats['ns']}  ({args.mc_version}, dp_format {profile.dp_format})")
    print(f"  keyframes fired : {stats['keyframes']}   commands: {stats['commands']}"
          + (f"   skipped empty: {stats['skipped_empty']}" if stats['skipped_empty'] else ""))
    print(f"  timing          : tps {stats['tps']}, offset {stats['offset_gt']}gt, "
          f"last fire @ {stats['max_delay_gt']}gt ({stats['max_delay_gt']/stats['tps']:.1f}s)")
    print(f"  sync            : " + (f"auto-follows music PLAY of '{stats['music_ns']}'"
                                     if stats['music_ns'] else "manual [粒子播放] sign"))
    print(f"  console         : {stats['console_origin']}")
    print("─" * 64)
    if stats["deployed"]:
        print(f"  deployed -> {stats['deployed']}")
        print(f"  in-game: /reload  ->  /tick rate 80")
        if stats["music_ns"]:
            print(f"           /function {args.ns}:setup is optional — it auto-fires when")
            print(f"           you press the music's [play] (PLAY of '{stats['music_ns']}').")
        else:
            print(f"           /function {args.ns}:setup  ->  press [粒子播放] when the song plays")
    else:
        print(f"  Datapack written to: {stats['out']}  (NOT deployed)")
        print(f"  install: copy build\\{args.ns} into <world>/datapacks/  (or use --world-dir), then /reload")
    return 0


if __name__ == "__main__":
    # robust unicode stdout for Chinese tellraw echoes + box-drawing summary on a
    # non-UTF-8 console (cp1252 etc.) — otherwise the post-build print raises
    # UnicodeEncodeError and a driving agent mis-reads a successful build as failed.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
