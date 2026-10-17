# -*- coding: utf-8 -*-
"""50_enb_probe.py — Extended Note Block v1.9.1 / Minecraft 1.21.1 Phase-1 probe.

This is deliberately a POC, not a production backend.  It builds one isolated
diagnostic datapack containing:

* five-instrument timbre audition (piano, bass, strings, distortion guitar, drums);
* velocity / sustain / fade / delay checks;
* a repeated 12-note same-tick chord;
* direct SoundPath and PitchBendPoints NBT canaries;
* a short, program-aware excerpt from a real MIDI;
* a randomized single-blind ENB-piano vs RedPiano/Salamander A/B excerpt; and
* a configurable large block-entity stress bank.

ENB v1.9.1 derives its GM instrument from the block immediately below the
extended note block.  Its redstone FALLING edge also stops the sound.  Therefore
the RedPiano palette's proven one-tick pulse cannot be copied verbatim: ENB
triggers stay powered for at least delayedPlayingTime + sustainTime, while the
RedPiano side of the blind test is reset after one tick.

Build-only example (the default, safe path):

    python poc/50_enb_probe.py --midi poc/qingtian_piano.mid \
      --namespace enbprobe --origin 200 520 200 --tick-rate 80

Optional deployment (argument is the world's *datapacks* directory):

    python poc/50_enb_probe.py ... \
      --world-dir "C:/.../saves/ENB Probe/datapacks"

Dependencies: stdlib + mido==1.3.3 (the repository's existing core dependency).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SCRIPTS = REPO_ROOT / "minecraft-redstone-music" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import redpiano_core as core  # noqa: E402


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


MC_VERSION = "1.21.1"
ENB_VERSION = "1.9.1"
ENB_SOURCE_COMMIT = "9c902c2071e704dfc2aa71e72909205c381244a7"
ENB_MODRINTH_VERSION = "XYPff5nL"
ENB_JAR = "extendednoteblock-1.9.1+1.21.1.jar"
ENB_URL = (
    "https://cdn.modrinth.com/data/JL9ooSG2/versions/XYPff5nL/"
    "extendednoteblock-1.9.1%2B1.21.1.jar"
)
ENB_SHA256 = "9fdf1f9464c824f7e7dbd4d964a6fe2e86fd52ba0379103feeb020ee603cc646"
ENB_SHA512 = (
    "7bfc06905c326ebd848fd48b626a66dd10e288a7ca412a4b52a0b707bea08372"
    "36882a41d7436279ee20324abafa3cc1b156119775e51f39ab12144389498647"
)
REDPIANO_CONTROL_JAR = "redpiano-1.0.0-mc1.21.1.jar"
REDPIANO_CONTROL_SHA256 = (
    "9f752e555c083b4d47c3798439392c8dad6d44d27f2137a5d8acfbe8814ce4b9"
)
QZPNO_CONTROL_ZIP = "qzpno_mv.zip"
QZPNO_CONTROL_SHA256 = (
    "947779cbe34762aa0caf6ac1d8c709ba49455c2b5e86a1971517060c1c4c4758"
)
MAX_SUSTAIN_TICKS = 400  # ENB GUI/server update clamp in v1.9.1.
BUILD_BATCH = 1800
PROBE_FORCELOAD_CAP = 240  # stay below one vanilla forceload command's hard limit.
MAX_SOURCE_EVENTS = 4096
MAX_BLIND_EVENTS = 512
MAX_STRESS_EVENTS = 4096
HORIZONTAL_SAFE_LIMIT = 29_999_984
CELL_DX = 2
ROW_DZ = 3  # >=3: a side trigger cannot power the next row's note block.
PITCH_STATES = ("c", "cs", "d", "ds", "e", "f", "fs", "g", "gs", "a", "as", "b")


# Official v1.9.1 InstrumentMap.GM_INSTRUMENT_TO_BLOCK, indexed by GM program.
# 0..127 are melodic programs; 128 is the Standard Drum Kit.  This table is
# intentionally embedded in the POC so an offline probe cannot silently drift to
# a RedPiano family mapping.
GM_BLOCKS = (
    "minecraft:dirt",
    "minecraft:coarse_dirt",
    "minecraft:podzol",
    "minecraft:rooted_dirt",
    "minecraft:clay",
    "minecraft:terracotta",
    "minecraft:moss_block",
    "minecraft:red_nether_bricks",
    "minecraft:light_blue_concrete",
    "minecraft:polished_diorite",
    "minecraft:amethyst_block",
    "minecraft:iron_block",
    "minecraft:oak_planks",
    "minecraft:bone_block",
    "minecraft:gold_block",
    "minecraft:hay_block",
    "minecraft:beehive",
    "minecraft:dried_kelp_block",
    "minecraft:netherrack",
    "minecraft:quartz_block",
    "minecraft:mushroom_stem",
    "minecraft:bookshelf",
    "minecraft:bricks",
    "minecraft:mud_bricks",
    "minecraft:oak_log",
    "minecraft:white_wool",
    "minecraft:shroomlight",
    "minecraft:sea_lantern",
    "minecraft:soul_sand",
    "minecraft:blackstone",
    "minecraft:obsidian",
    "minecraft:glass",
    "minecraft:oak_wood",
    "minecraft:spruce_planks",
    "minecraft:birch_planks",
    "minecraft:jungle_planks",
    "minecraft:acacia_planks",
    "minecraft:dark_oak_planks",
    "minecraft:purpur_block",
    "minecraft:purpur_pillar",
    "minecraft:cherry_planks",
    "minecraft:mangrove_planks",
    "minecraft:crimson_planks",
    "minecraft:warped_planks",
    "minecraft:chiseled_stone_bricks",
    "minecraft:melon",
    "minecraft:smooth_sandstone",
    "minecraft:stone",
    "minecraft:calcite",
    "minecraft:light_gray_wool",
    "minecraft:end_stone",
    "minecraft:end_stone_bricks",
    "minecraft:soul_soil",
    "minecraft:cyan_wool",
    "minecraft:sculk",
    "minecraft:ancient_debris",
    "minecraft:waxed_cut_copper",
    "minecraft:waxed_exposed_cut_copper",
    "minecraft:waxed_copper_block",
    "minecraft:waxed_weathered_cut_copper",
    "minecraft:copper_ore",
    "minecraft:waxed_oxidized_copper",
    "minecraft:diamond_block",
    "minecraft:diamond_ore",
    "minecraft:yellow_terracotta",
    "minecraft:orange_terracotta",
    "minecraft:red_terracotta",
    "minecraft:brown_terracotta",
    "minecraft:white_concrete",
    "minecraft:light_gray_concrete",
    "minecraft:gray_concrete",
    "minecraft:black_concrete",
    "minecraft:stripped_spruce_log",
    "minecraft:bamboo_planks",
    "minecraft:bamboo_block",
    "minecraft:stripped_bamboo_block",
    "minecraft:tinted_glass",
    "minecraft:cherry_log",
    "minecraft:iron_bars",
    "minecraft:packed_mud",
    "minecraft:emerald_block",
    "minecraft:emerald_ore",
    "minecraft:lapis_block",
    "minecraft:lapis_ore",
    "minecraft:purple_glazed_terracotta",
    "minecraft:magenta_glazed_terracotta",
    "minecraft:cyan_glazed_terracotta",
    "minecraft:blue_glazed_terracotta",
    "minecraft:ochre_froglight",
    "minecraft:glowstone",
    "minecraft:verdant_froglight",
    "minecraft:crying_obsidian",
    "minecraft:white_stained_glass",
    "minecraft:netherite_block",
    "minecraft:beacon",
    "minecraft:pink_wool",
    "minecraft:dripstone_block",
    "minecraft:dead_tube_coral_block",
    "minecraft:magenta_concrete",
    "minecraft:soul_lantern",
    "minecraft:shulker_box",
    "minecraft:deepslate_emerald_ore",
    "minecraft:reinforced_deepslate",
    "minecraft:polished_blackstone",
    "minecraft:barrel",
    "minecraft:orange_concrete",
    "minecraft:red_sandstone",
    "minecraft:chiseled_quartz_block",
    "minecraft:bamboo_mosaic",
    "minecraft:crimson_stem",
    "minecraft:acacia_log",
    "minecraft:warped_stem",
    "minecraft:prismarine_bricks",
    "minecraft:lodestone",
    "minecraft:raw_iron_block",
    "minecraft:crafting_table",
    "minecraft:crimson_hyphae",
    "minecraft:warped_hyphae",
    "minecraft:honeycomb_block",
    "minecraft:bell",
    "minecraft:polished_andesite",
    "minecraft:lime_wool",
    "minecraft:dark_prismarine",
    "minecraft:birch_log",
    "minecraft:polished_blackstone_bricks",
    "minecraft:iron_trapdoor",
    "minecraft:gilded_blackstone",
    "minecraft:tuff",
    "minecraft:sandstone",
)


@dataclass(frozen=True)
class MidiNote:
    t: float
    dur: float
    midi: int
    velocity: int
    channel: int
    program: int


@dataclass
class ProbeEvent:
    bank: str
    tick: int
    midi: int
    velocity: int
    sustain: int
    program: int = 0
    backend: str = "enb"  # "enb" or "redpiano"
    delayed_ms: int = 0
    fade_in: int = 0
    fade_out: int = 0
    advanced: str | None = None  # contents of AdvancedData:{...}
    label: str = ""
    x: int | None = None
    y: int | None = None
    z: int | None = None

    def trigger(self) -> tuple[int, int, int]:
        assert self.x is not None and self.y is not None and self.z is not None
        return self.x, self.y, self.z - 1

    def hold_ticks(self, tick_rate: int) -> int:
        if self.backend == "redpiano":
            # The physical RedPiano pulse is one tick, but the centred sample has
            # no note-off edge. Keep the sequence alive for the MIDI duration so
            # ``done`` can stop both A/B tails at the same planned boundary.
            return max(1, self.sustain + 1)
        delay_ticks = math.ceil(self.delayed_ms * tick_rate / 1000.0)
        return max(1, delay_ticks + self.sustain + 1)


class ProbeError(core.RedPianoError):
    """Expected POC failure, printed as one clean line by ``main``."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _err_str(exc: BaseException) -> str:
    return str(exc) or f"{type(exc).__name__} (file may be truncated or corrupt)"


def parse_midi(path: Path) -> tuple[list[MidiNote], dict[str, int]]:
    """Program-aware MIDI reader.

    Unlike ``build_machine.parse_midi_notes``, this stores the exact program at
    NOTE ON.  Channel 9 is always ENB program 128.  Retriggers close the old
    segment instead of silently dropping it.
    """
    try:
        import mido
    except ImportError as exc:
        raise ProbeError(
            "缺少 MIDI 依赖 mido。请先运行: "
            "pip install -r minecraft-redstone-music/requirements.txt"
        ) from exc

    if not path.is_file():
        raise ProbeError(f"MIDI 文件不存在: {path}")
    try:
        midi_file = mido.MidiFile(str(path), clip=True)
    except (OSError, ValueError, EOFError, IndexError, KeyError) as exc:
        raise ProbeError(f"无法读取 MIDI '{path}': {_err_str(exc)}") from exc
    if midi_file.type == 2:
        raise ProbeError("不支持异步 MIDI type 2；请先转换为 type 0 或 type 1")

    current_program: dict[int, int] = defaultdict(int)
    active: dict[tuple[int, int], tuple[float, int, int]] = {}
    notes: list[MidiNote] = []
    now = 0.0
    retriggers = 0

    def close(key: tuple[int, int], end: float) -> None:
        nonlocal notes
        start, velocity, program = active.pop(key)
        channel, note = key
        notes.append(
            MidiNote(
                t=start,
                dur=max(end - start, 0.02),
                midi=int(note),
                velocity=int(velocity),
                channel=int(channel),
                program=128 if channel == 9 else int(program),
            )
        )

    try:
        for msg in midi_file:
            now += msg.time
            if msg.type == "program_change":
                current_program[msg.channel] = msg.program
            elif msg.type == "note_on" and msg.velocity > 0:
                key = (msg.channel, msg.note)
                if key in active:
                    close(key, now)
                    retriggers += 1
                active[key] = (
                    now,
                    msg.velocity,
                    128 if msg.channel == 9 else current_program[msg.channel],
                )
            elif msg.type == "note_off" or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                key = (msg.channel, msg.note)
                if key in active:
                    close(key, now)
    except (OSError, ValueError, TypeError, EOFError, IndexError, KeyError) as exc:
        raise ProbeError(f"解码 MIDI '{path}' 时失败: {_err_str(exc)}") from exc

    dangling = len(active)
    for key in list(active):
        close(key, now)

    notes.sort(key=lambda n: (n.t, -n.midi, n.channel))
    if not notes:
        raise ProbeError(f"MIDI 没有可播放音符: {path}")
    return notes, {"retriggers": retriggers, "dangling": dangling}


def select_excerpt(
    notes: Sequence[MidiNote],
    start_s: float,
    seconds: float,
    max_notes: int,
    tick_rate: int,
) -> list[MidiNote]:
    if not math.isfinite(start_s) or not math.isfinite(seconds):
        raise ProbeError("--start/--seconds 必须是有限数字")
    if start_s < 0 or seconds <= 0 or max_notes <= 0:
        raise ProbeError("--start 必须 >=0，--seconds/--max-notes 必须 >0")
    if max_notes > MAX_SOURCE_EVENTS:
        raise ProbeError(f"--max-notes 不得超过 {MAX_SOURCE_EVENTS}")
    candidates = [n for n in notes if start_s <= n.t < start_s + seconds]
    if not candidates:
        raise ProbeError(
            f"MIDI 在 {start_s:.2f}..{start_s + seconds:.2f}s 内没有音符；"
            "请调整 --start/--seconds"
        )
    if len(candidates) > max_notes:
        cutoff = round(candidates[max_notes - 1].t * tick_rate)
        # Never split a same-tick chord merely to hit the cap.
        candidates = [n for n in candidates if round(n.t * tick_rate) <= cutoff]
    if len(candidates) > MAX_SOURCE_EVENTS:
        raise ProbeError(
            f"同 tick 和弦展开为 {len(candidates)} 个事件，超过安全上限 "
            f"{MAX_SOURCE_EVENTS}"
        )
    first_t = candidates[0].t
    return [
        MidiNote(
            t=n.t - first_t,
            dur=n.dur,
            midi=n.midi,
            velocity=n.velocity,
            channel=n.channel,
            program=n.program,
        )
        for n in candidates
    ]


def sustain_ticks(seconds: float, tick_rate: int) -> tuple[int, bool]:
    raw = max(1, round(max(0.0, seconds) * tick_rate))
    return min(raw, MAX_SUSTAIN_TICKS), raw > MAX_SUSTAIN_TICKS


def pitch_state(midi_note: int) -> str:
    return PITCH_STATES[int(midi_note) % 12]


def enb_nbt(event: ProbeEvent) -> str:
    fields = [
        f"note:{int(event.midi)}",
        f"velocity:{int(event.velocity)}",
        f"sustainTime:{int(event.sustain)}",
        f"delayedPlayingTime:{int(event.delayed_ms)}",
        f"fadeInTime:{int(event.fade_in)}",
        f"fadeOutTime:{int(event.fade_out)}",
    ]
    if event.advanced:
        fields.append(f"AdvancedData:{{{event.advanced}}}")
    return "{" + ",".join(fields) + "}"


def enb_block(event: ProbeEvent) -> str:
    return (
        "extendednoteblock:extended_note_block"
        f"[powered=false,pitch={pitch_state(event.midi)}]"
        f"{enb_nbt(event)}"
    )


def _redpiano_resolver() -> tuple[list[int], dict[str, dict[str, object]]]:
    path = HERE / "redpiano_map.json"
    if not path.is_file():
        raise ProbeError(f"盲听对照所需映射不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return [int(v) for v in payload["bands"]], payload["map"]


def redpiano_block(midi_note: int, velocity: int) -> tuple[str, int]:
    bands, mapping = _redpiano_resolver()
    band = min(bands, key=lambda b: abs(b - midi_note))
    raw = 12 + midi_note - band
    note_value = max(0, min(24, raw))
    v = velocity / 127.0
    layer = "p" if v < 0.40 else ("mf" if v < 0.72 else "f")
    entry = mapping[f"{band}_{layer}"]
    return str(entry["block"]), note_value


def _mk_event(
    bank: str,
    tick_s: float,
    note: int,
    velocity: int,
    dur_s: float,
    tick_rate: int,
    *,
    program: int = 0,
    backend: str = "enb",
    delayed_ms: int = 0,
    fade_in: int = 0,
    fade_out: int | None = None,
    advanced: str | None = None,
    label: str = "",
) -> tuple[ProbeEvent, bool]:
    sustain, clamped = sustain_ticks(dur_s, tick_rate)
    if fade_out is None:
        fade_out = min(4, max(0, sustain // 8))
    return (
        ProbeEvent(
            bank=bank,
            tick=max(0, round(tick_s * tick_rate)),
            midi=max(0, min(127, int(note))),
            velocity=max(1, min(127, int(velocity))),
            sustain=sustain,
            program=max(0, min(128, int(program))),
            backend=backend,
            delayed_ms=max(0, int(delayed_ms)),
            fade_in=max(0, int(fade_in)),
            fade_out=max(0, int(fade_out)),
            advanced=advanced,
            label=label,
        ),
        clamped,
    )


def plan_timbre(tick_rate: int) -> list[ProbeEvent]:
    # Required five-way spot check from the branch plan.
    programs = [
        (0, (60, 64, 67, 72), "Acoustic Grand Piano"),
        (33, (36, 40, 43, 48), "Electric Bass (finger)"),
        (48, (60, 64, 67, 72), "String Ensemble 1"),
        (30, (52, 55, 59, 64), "Distortion Guitar"),
        (128, (36, 38, 42, 49), "Standard Drum Kit"),
    ]
    out: list[ProbeEvent] = []
    cursor = 0.0
    for program, notes, name in programs:
        for note in notes:
            event, _ = _mk_event(
                "timbre",
                cursor,
                note,
                105,
                0.50,
                tick_rate,
                program=program,
                fade_out=2,
                label=f"{name} / MIDI {note}",
            )
            out.append(event)
            cursor += 0.60
        cursor += 0.80
    return out


def plan_dynamics(tick_rate: int) -> list[ProbeEvent]:
    out: list[ProbeEvent] = []
    # Same note, separated in time: velocity should be the only audible variable.
    for idx, velocity in enumerate((24, 72, 120)):
        event, _ = _mk_event(
            "dynamics",
            idx * 1.20,
            60,
            velocity,
            0.80,
            tick_rate,
            fade_out=2,
            label=f"velocity={velocity}",
        )
        out.append(event)
    # Same note and velocity: internal sustain must end at visibly different times
    # while the redstone source remains high long enough for the longest one.
    for idx, dur_s in enumerate((0.25, 1.00, 3.00)):
        event, _ = _mk_event(
            "dynamics",
            4.2 + idx * 3.5,
            60,
            100,
            dur_s,
            tick_rate,
            fade_out=0,
            label=f"sustain={dur_s:.2f}s",
        )
        out.append(event)
    # Fade and real-millisecond delay canaries.
    for idx, fade in enumerate((0, 8)):
        event, _ = _mk_event(
            "dynamics",
            15.0 + idx * 2.8,
            67,
            100,
            2.0,
            tick_rate,
            fade_out=fade,
            label=f"fadeOutTime={fade}",
        )
        out.append(event)
    delayed, _ = _mk_event(
        "dynamics",
        20.8,
        72,
        100,
        1.0,
        tick_rate,
        delayed_ms=250,
        fade_out=2,
        label="delayedPlayingTime=250ms",
    )
    out.append(delayed)
    return out


def plan_chord(tick_rate: int) -> list[ProbeEvent]:
    notes = (48, 52, 55, 60, 64, 67, 72, 76, 79, 84, 88, 91)
    out: list[ProbeEvent] = []
    for repeat in range(3):
        for note in notes:
            event, _ = _mk_event(
                "chord",
                repeat * 2.5,
                note,
                105,
                1.5,
                tick_rate,
                program=0,
                fade_out=3,
                label=f"12-note chord repeat {repeat + 1}",
            )
            out.append(event)
    return out


def plan_advanced(tick_rate: int) -> list[ProbeEvent]:
    soundpath = (
        "SoundPath:["
        "{x:-8.0d,y:0.0d,z:0.0d},"
        "{x:0.0d,y:2.0d,z:0.0d},"
        "{x:8.0d,y:0.0d,z:0.0d}"
        "]"
    )
    pitchbend = (
        "PitchBendPoints:["
        "{t:0.0f,v:0.0f},"
        "{t:1.0f,v:12.0f}"
        "]"
    )
    a, _ = _mk_event(
        "advanced",
        0.0,
        72,
        100,
        4.0,
        tick_rate,
        program=80,
        fade_out=4,
        advanced=soundpath,
        label="direct SoundPath (external-generator canary)",
    )
    b, _ = _mk_event(
        "advanced",
        5.0,
        60,
        100,
        3.0,
        tick_rate,
        program=0,
        fade_out=3,
        advanced=pitchbend,
        label="PitchBendPoints 0 -> +12",
    )
    return [a, b]


def plan_midi(
    notes: Sequence[MidiNote],
    tick_rate: int,
    bank: str,
    *,
    backend: str = "enb",
    force_program: int | None = None,
) -> tuple[list[ProbeEvent], int]:
    out: list[ProbeEvent] = []
    clamped = 0
    for note in notes:
        event, was_clamped = _mk_event(
            bank,
            note.t,
            note.midi,
            note.velocity,
            note.dur,
            tick_rate,
            program=note.program if force_program is None else force_program,
            backend=backend,
            label=(
                f"MIDI ch={note.channel} program={note.program} "
                f"note={note.midi}"
            ),
        )
        out.append(event)
        clamped += int(was_clamped)
    return out, clamped


def plan_stress(count: int, tick_rate: int) -> list[ProbeEvent]:
    if count < 0:
        raise ProbeError("--stress-count 必须 >=0")
    if count > MAX_STRESS_EVENTS:
        raise ProbeError(f"--stress-count 不得超过 {MAX_STRESS_EVENTS}")
    programs = (0, 33, 48, 30, 128)
    drum_notes = (36, 38, 42, 46, 49)
    out: list[ProbeEvent] = []
    for idx in range(count):
        program = programs[idx % len(programs)]
        note = drum_notes[idx % len(drum_notes)] if program == 128 else 48 + idx % 25
        event, _ = _mk_event(
            "stress",
            0.0,
            note,
            72,
            0.25,
            tick_rate,
            program=program,
            fade_out=1,
            label=f"stress #{idx + 1}",
        )
        out.append(event)
    return out


def listener_position(events: Sequence[ProbeEvent]) -> tuple[float, float, float]:
    """Return a reproducible listening point above the centre of one bank."""
    if not events:
        raise ProbeError("cannot calculate a listener position for an empty bank")
    if any(event.x is None or event.y is None or event.z is None for event in events):
        raise ProbeError("listener position requested before bank allocation")
    xs = [int(event.x) for event in events]
    ys = [int(event.y) for event in events]
    zs = [int(event.z) for event in events]
    # Event/trigger columns are spaced by CELL_DX. Choose a neighbouring empty
    # column near the centre so a dedicated listener platform never caps a note.
    platform_x = math.floor((min(xs) + max(xs)) / 2.0)
    if (platform_x - min(xs)) % CELL_DX == 0:
        platform_x += 1
    return (
        float(platform_x) + 0.5,
        float(max(ys) + 2),
        round((min(zs) + max(zs)) / 2.0 + 0.5, 1),
    )


def allocate_banks(
    banks: Sequence[tuple[str, list[ProbeEvent]]],
    origin: tuple[int, int, int],
    cols: int = 8,
) -> dict[str, dict[str, object]]:
    ox, oz, y = origin
    cursor_z = oz
    zones: dict[str, dict[str, object]] = {}
    for bank_name, events in banks:
        if not events:
            continue
        bank_cols = cols
        for idx, event in enumerate(events):
            event.x = ox + (idx % bank_cols) * CELL_DX
            event.y = y
            event.z = cursor_z + (idx // bank_cols) * ROW_DZ
        rows = (len(events) + bank_cols - 1) // bank_cols
        zones[bank_name] = {
            "x0": ox,
            "z0": cursor_z - 1,
            "x1": ox + (min(bank_cols, len(events)) - 1) * CELL_DX,
            "z1": cursor_z + max(0, rows - 1) * ROW_DZ,
            "count": len(events),
            "listener": list(listener_position(events)),
        }
        cursor_z += rows * ROW_DZ + 8
    return zones


def _all_unique_events(banks: Sequence[tuple[str, list[ProbeEvent]]]) -> list[ProbeEvent]:
    return [event for _name, events in banks for event in events]


def emit_blocks(
    grid: core.Grid,
    events: Sequence[ProbeEvent],
) -> list[str]:
    commands: list[str] = []
    for event in events:
        assert event.x is not None and event.y is not None and event.z is not None
        if event.backend == "enb":
            support = GM_BLOCKS[event.program]
            note_block = enb_block(event)
        elif event.backend == "redpiano":
            support, note_value = redpiano_block(event.midi, event.velocity)
            note_block = f"minecraft:note_block[note={note_value}]"
        else:
            raise ProbeError(f"unknown probe backend: {event.backend}")
        # Some official GM supports (notably soul_lantern and bell) break unless
        # their floor is solid. A universal foundation keeps all 129 programs stable.
        grid.put(commands, event.x, event.y - 2, event.z, "minecraft:stone")
        grid.put(commands, event.x, event.y - 1, event.z, support)
        grid.put(commands, event.x, event.y, event.z, note_block)
        grid.put(commands, event.x, event.y + 1, event.z, "minecraft:air")
        tx, ty, tz = event.trigger()
        grid.put(commands, tx, ty, tz, "minecraft:air")
    return commands


def _write_chunked_function(
    dp: core.Datapack, name: str, commands: Sequence[str], chunk: int = BUILD_BATCH
) -> list[str]:
    refs: list[str] = []
    chunks = [list(commands[i : i + chunk]) for i in range(0, len(commands), chunk)]
    if not chunks:
        dp.write_function(name, ["return 0"])
        return [name]
    for idx, part in enumerate(chunks):
        child = f"{name}/c{idx}"
        dp.write_function(child, part)
        refs.append(child)
    dp.write_function(name, [f"function {dp.ns}:{ref}" for ref in refs])
    return refs


def write_sequence(
    dp: core.Datapack,
    name: str,
    events: Sequence[ProbeEvent],
    tick_rate: int,
) -> list[str]:
    """Write one schedule chain and return every function id that may be scheduled."""
    if not events:
        return []
    grouped: dict[int, list[ProbeEvent]] = defaultdict(list)
    for event in events:
        grouped[event.tick].append(event)
    ticks = sorted(grouped)
    sequence_end = max(event.tick + event.hold_ticks(tick_rate) for event in events)
    scheduled: list[str] = []

    for idx, tick in enumerate(ticks):
        step = f"seq/{name}/s{idx:04d}"
        scheduled.append(step)
        group = grouped[tick]
        lines = [f"execute unless score PLAY {dp.ns} matches 1 run return 0"]
        if idx == 0:
            # The pinned 1.21.1 RedPiano control JAR has no rpcfg mute switch.
            # A second stop one tick after stop_silent drains any late queued sample
            # immediately before the new A/B triggers are enqueued.
            lines.append("stopsound @a record")
        lines.extend(
            f"setblock {x} {y} {z} minecraft:redstone_block"
            for x, y, z in (event.trigger() for event in group)
        )

        redpiano_events = [event for event in group if event.backend == "redpiano"]
        enb_events = [event for event in group if event.backend == "enb"]
        if redpiano_events:
            off_rp = f"seq/{name}/off{idx:04d}_redpiano"
            scheduled.append(off_rp)
            dp.write_function(
                off_rp,
                [
                    f"setblock {x} {y} {z} minecraft:air"
                    for x, y, z in (event.trigger() for event in redpiano_events)
                ],
            )
            lines.append(f"schedule function {dp.ns}:{off_rp} 1t replace")
        hold = 1
        if enb_events:
            hold = max(event.hold_ticks(tick_rate) for event in enb_events)
            off_enb = f"seq/{name}/off{idx:04d}_enb"
            scheduled.append(off_enb)
            dp.write_function(
                off_enb,
                [
                    f"setblock {x} {y} {z} minecraft:air"
                    for x, y, z in (event.trigger() for event in enb_events)
                ],
            )
            lines.append(f"schedule function {dp.ns}:{off_enb} {hold}t replace")

        if idx + 1 < len(ticks):
            delta = max(1, ticks[idx + 1] - tick)
            lines.append(
                f"schedule function {dp.ns}:seq/{name}/s{idx + 1:04d} {delta}t replace"
            )
        else:
            # A long note may have started before the final onset and still be
            # sounding. End against the whole sequence tail, not the last group.
            done_delay = max(1, sequence_end - tick + 2)
            lines.append(f"schedule function {dp.ns}:done {done_delay}t replace")
        dp.write_function(step, lines)

    duration_s = (sequence_end - ticks[0]) / tick_rate
    listen_x, listen_y, listen_z = listener_position(events)
    dp.write_function(
        f"internal/test/{name}",
        [
            f"function {dp.ns}:stop_silent",
            (
                f"execute as @a in minecraft:overworld run tp @s "
                f"{listen_x:.1f} {listen_y:.1f} {listen_z:.1f}"
            ),
            "scoreboard players set poly rpcfg 1",
            "scoreboard players set human rpcfg 1",
            f"scoreboard players set PLAY {dp.ns} 1",
            (
                f'tellraw @a "[{dp.ns}] 开始 {name}: {len(events)} 个触发, '
                f'约 {duration_s:.1f}s @ tick rate {tick_rate}; 已固定试听位置。"'
            ),
            # One full tick of low power after stop_silent guarantees a fresh edge.
            f"schedule function {dp.ns}:seq/{name}/s0000 1t replace",
        ],
    )
    dp.write_function(
        f"test/{name}",
        [
            (
                "execute in minecraft:overworld run "
                f"function {dp.ns}:internal/test/{name}"
            )
        ],
    )
    return scheduled


def _score_nbt_check(
    ns: str, pos: tuple[int, int, int], path: str, expected: int
) -> list[str]:
    x, y, z = pos
    return [
        f"scoreboard players set EXPECT {ns} {expected}",
        f"scoreboard players set ACTUAL {ns} -2147483648",
        (
            f"execute store result score ACTUAL {ns} run "
            f"data get block {x} {y} {z} {path} 1"
        ),
        (
            f"execute unless score ACTUAL {ns} = EXPECT {ns} run "
            f"scoreboard players add FAIL {ns} 1"
        ),
    ]


def write_verify(
    dp: core.Datapack,
    dynamics: Sequence[ProbeEvent],
    advanced: Sequence[ProbeEvent],
) -> None:
    sentinel = dynamics[0]
    soundpath = advanced[0]
    pitchbend = advanced[1]
    assert sentinel.x is not None and sentinel.y is not None and sentinel.z is not None
    assert soundpath.x is not None and soundpath.y is not None and soundpath.z is not None
    assert pitchbend.x is not None and pitchbend.y is not None and pitchbend.z is not None
    pos = (sentinel.x, sentinel.y, sentinel.z)
    sx, sy, sz = pos
    sp = (soundpath.x, soundpath.y, soundpath.z)
    pb = (pitchbend.x, pitchbend.y, pitchbend.z)
    lines = [
        f"scoreboard players set FAIL {dp.ns} 0",
        (
            f"execute unless block {sx} {sy} {sz} "
            "extendednoteblock:extended_note_block[powered=false,pitch=c] "
            f"run scoreboard players add FAIL {dp.ns} 1"
        ),
        (
            f"execute unless block {sx} {sy - 1} {sz} minecraft:dirt "
            f"run scoreboard players add FAIL {dp.ns} 1"
        ),
    ]
    lines += _score_nbt_check(dp.ns, pos, "note", sentinel.midi)
    lines += _score_nbt_check(dp.ns, pos, "velocity", sentinel.velocity)
    lines += _score_nbt_check(dp.ns, pos, "sustainTime", sentinel.sustain)
    lines += _score_nbt_check(dp.ns, pos, "delayedPlayingTime", sentinel.delayed_ms)
    lines += _score_nbt_check(dp.ns, pos, "fadeInTime", sentinel.fade_in)
    lines += _score_nbt_check(dp.ns, pos, "fadeOutTime", sentinel.fade_out)
    lines += [
        (
            f"execute unless data block {sp[0]} {sp[1]} {sp[2]} "
            "AdvancedData.SoundPath[1] "
            f"run scoreboard players add FAIL {dp.ns} 1"
        ),
        (
            f"execute unless data block {pb[0]} {pb[1]} {pb[2]} "
            "AdvancedData.PitchBendPoints[1] "
            f"run scoreboard players add FAIL {dp.ns} 1"
        ),
    ]
    lines += _score_nbt_check(dp.ns, sp, "AdvancedData.SoundPath[1].x", 0)
    lines += _score_nbt_check(dp.ns, sp, "AdvancedData.SoundPath[1].y", 2)
    lines += _score_nbt_check(dp.ns, sp, "AdvancedData.SoundPath[1].z", 0)
    lines += _score_nbt_check(dp.ns, pb, "AdvancedData.PitchBendPoints[1].t", 1)
    lines += _score_nbt_check(dp.ns, pb, "AdvancedData.PitchBendPoints[1].v", 12)
    lines += [
        (
            f'execute if score FAIL {dp.ns} matches 0 run tellraw @a '
            f'"[{dp.ns}] 静态校验 PASS: 方块状态、垫底乐器、6 个基础 NBT、'
            'SoundPath、PitchBendPoints 的结构和值均正确。"'
        ),
        (
            f'execute unless score FAIL {dp.ns} matches 0 run tellraw @a '
            f'"[{dp.ns}] 静态校验 FAIL: 请运行 /function {dp.ns}:inspect 并保存原始输出。"'
        ),
    ]
    dp.write_function("internal/verify", lines)
    dp.write_function(
        "verify",
        [
            (
                "execute in minecraft:overworld run "
                f"function {dp.ns}:internal/verify"
            )
        ],
    )
    dp.write_function(
        "internal/inspect",
        [
            f"data get block {sx} {sy} {sz}",
            f"data get block {sp[0]} {sp[1]} {sp[2]}",
            f"data get block {pb[0]} {pb[1]} {pb[2]}",
        ],
    )
    dp.write_function(
        "inspect",
        [
            (
                "execute in minecraft:overworld run "
                f"function {dp.ns}:internal/inspect"
            )
        ],
    )


def _public_event(event: ProbeEvent) -> dict[str, object]:
    blind = event.bank in {"blind_a", "blind_b"}
    return {
        "bank": event.bank,
        "tick": event.tick,
        "midi": event.midi,
        "velocity": event.velocity,
        "sustainTime": event.sustain,
        "program": None if blind else event.program,
        "backend": "hidden" if blind else event.backend,
        "delayedPlayingTime": event.delayed_ms,
        "fadeInTime": event.fade_in,
        "fadeOutTime": event.fade_out,
        "advanced": bool(event.advanced),
        "pos": [event.x, event.y, event.z],
        "trigger": list(event.trigger()),
        "label": event.label,
    }


def audit_datapack(root: Path, ns: str) -> dict[str, int]:
    """Static pack audit: format/folders, function references and forbidden hazards."""
    pack = json.loads((root / "pack.mcmeta").read_text(encoding="utf-8"))
    if pack.get("pack", {}).get("pack_format") != 48:
        raise ProbeError("generated pack.mcmeta is not MC 1.21.1 datapack format 48")
    function_root = root / "data" / ns / "function"
    tag_root = root / "data" / "minecraft" / "tags" / "function"
    if not function_root.is_dir() or not tag_root.is_dir():
        raise ProbeError("generated pack did not use the 1.21 singular function folders")

    paths = sorted(function_root.rglob("*.mcfunction"))
    ids = {
        path.relative_to(function_root).as_posix()[: -len(".mcfunction")]
        for path in paths
    }
    call_pattern = re.compile(
        rf"(?:^|\s)(?:schedule\s+)?function\s+{re.escape(ns)}:"
        r"([a-z0-9_./-]+)"
    )
    clear_pattern = re.compile(
        rf"(?:^|\s)schedule\s+clear\s+{re.escape(ns)}:([a-z0-9_./-]+)"
    )
    refs: set[str] = set()
    line_count = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        line_count += len(text.splitlines())
        if "forceload remove all" in text:
            raise ProbeError(f"unsafe global forceload removal in {path}")
        if "minecraft:block_entity_data" in text:
            raise ProbeError(f"wrong item-component wrapper in block SNBT: {path}")
        refs.update(match.group(1) for match in call_pattern.finditer(text))
        refs.update(match.group(1) for match in clear_pattern.finditer(text))
        if path.parent.name == "bld" and len(text.splitlines()) > BUILD_BATCH:
            raise ProbeError(f"build batch exceeds {BUILD_BATCH} commands: {path}")
    missing = sorted(refs - ids)
    if missing:
        raise ProbeError(f"generated function references are missing: {missing[:8]}")
    return {
        "function_files": len(paths),
        "function_lines": line_count,
        "function_references": len(refs),
    }


def report_markdown(manifest: dict[str, object], ns: str) -> str:
    source = manifest["source_midi"]
    counts = manifest["counts"]
    bounds = manifest["bounds"]
    return f"""# ENB Phase 1 探针交接

> 当前结论：**尚未裁决，Phase 2 禁止启动。** 本文件只是可执行的人工验收台。

## 固定环境

- Minecraft: **1.21.1**
- Extended Note Block: **v{ENB_VERSION}**
- ENB JAR: `{ENB_JAR}`
- SHA-256: `{ENB_SHA256}`
- tick rate: **{manifest['tick_rate']}**
- 输入 MIDI: `{source['path']}`
- 输入 SHA-256: `{source['sha256']}`
- 选取: {source['selected_notes']} 音符，窗口 {source['start_s']}..{source['end_s']}s
- 物理事件块: {counts['physical_events']}（ENB {counts['enb']} / RedPiano 对照 {counts['redpiano']}）
- 压测块: {counts['stress']}
- 占地: X[{bounds['x0']}..{bounds['x1']}], Z[{bounds['z0']}..{bounds['z1']}], Y={bounds['y']}
- forceload: **{bounds['chunks']} chunks**（探针硬上限 {PROBE_FORCELOAD_CAP}）

## 依赖

1. 客户端和服务端都安装官方 `{ENB_JAR}`。
   其 `fabric.mod.json` 要求 Fabric Loader `>=0.16.14`、Java `>=21`、Fabric API，
   且 Minecraft 必须匹配 `~1.21.1`。
2. **首次启动必须激活 ENB 默认音色包，否则会完全静音。** 打开
   `选项 -> 音色包`，点击“默认音色 (`extendednoteblock_default.zip`)”，直到该行出现
   绿色箭头，等待资源重载完成，并确认“唱片/唱片机”音量大于 0。
   ENB 的初始 `activeSoundPackId` 为空，数据包无法替客户端完成这一步。
3. ENB 音色只能来自官方 JAR / 官方音色包；本仓库没有复制任何 ENB 音色。
4. A/B 固定使用本仓库 `binaries/{REDPIANO_CONTROL_JAR}`
   （SHA-256 `{REDPIANO_CONTROL_SHA256}`）与
   `minecraft-redstone-music/assets/{QZPNO_CONTROL_ZIP}`
   （SHA-256 `{QZPNO_CONTROL_SHA256}`）。
5. **先不要打开 `blind_key.json`**；完成 A/B 记录后再揭盲。

## 游戏内顺序

```mcfunction
# 先按上节激活默认音色包并等待资源重载
/reload
/tick rate {manifest['tick_rate']}
/function {ns}:setup
# 等待绿色 built 提示
/function {ns}:verify

/function {ns}:test/timbre
/function {ns}:test/dynamics
/function {ns}:test/chord
/function {ns}:test/advanced
/function {ns}:test/midi

# 随机标签初筛：听者闭眼/遮屏，由第二人触发；每项“结束”后再运行下一项
/function {ns}:test/blind_a
/function {ns}:test/blind_b

# 分级压力；不要直接从 all 开始
/function {ns}:test/stress_64
/function {ns}:test/stress_256
/function {ns}:test/stress_all

/function {ns}:stop
/function {ns}:cleanup
/tick rate 20
```

tick rate 必须由玩家手动设置；探针不会自动修改它（仓库既有实测表明自动设置不可靠）。
测试结束后也请手动恢复为 20。
所有公共入口固定在 Overworld 执行。每次测试会停止 `record` 类声音、完整断电、
把在线玩家传送到该 bank 的固定试听点，等 1 游戏刻，再制造新的红石上升沿。
请只在隔离的单人测试世界运行，并等“本项播放结束”后再切换项目。

### A/B 边界

- A/B 使用相同片段、相同相对布局与固定试听点，只接受可比音域 MIDI 12..93；
  RedPiano 固定为生产默认 `poly=1`、`human=1`。固定的 1.21.1 控制 JAR 没有
  `mute` 开关，因此切换时用相隔 1 游戏刻的两次 `stopsound @a record` 排空尾音。
- `blind_key.json` 隐藏随机后端标签，但这只是**单盲初筛**：ENB 是位置声，
  RedPiano 是玩家头部居中声，而且脚下方块外观也不同；定位、响度和画面都可能泄露后端。
  初筛时必须闭眼/遮屏并由第二人触发。若要把偏好作为 GO 证据，
  应在固定试听点分别录音、响度归一化，再由第三方随机重命名后评分。
- `stress_64` 的紧凑区域可用于近场听感；`stress_256` / `stress_all` 超过 ENB
  约 16 格的位置声有效范围，只用于方块实体、MSPT/FPS 和触发性能，**不得据此统计吞音**。

## 人工验收（必须逐项填）

| 项 | 结果 | 原始观察 / 数值 |
|---|---|---|
| 钢琴、贝斯、弦乐、失真吉他、鼓组音色 | 未验证 | |
| velocity 24/72/120 响度关系 | 未验证 | |
| sustain 0.25/1/3 秒与 fade/delay | 未验证 | |
| `/setblock` + 六字段 NBT + SoundPath | 未验证 | `verify` 输出： |
| 12 音同 tick，重复三轮，无爆音/吞音 | 未验证 | 吞音次数： |
| 64 同 tick 近场听感 | 未验证 | 爆音/吞音次数： |
| 256 / all 方块与同 tick 性能 | 未验证 | MSPT、FPS、服务端日志（不填吞音）： |
| ENB 钢琴 vs Salamander 随机单盲初筛 | 未验证 | A： / B： / 偏好： |
| 录音归一化后的严格盲评 | 未验证 | 随机标签、评分人、偏好： |

### 性能记录

在 setup 前、setup 后、每档 stress 后分别运行 `/tick query`，并记录 F3 FPS。
若需要服务端剖析，再用 `/debug start`、跑一档、`/debug stop` 保存报告。

## GO / NO-GO

- **GO**：所有主清单可接受，且没有 NBT、同 tick 和性能重大故障。
- **NO-GO**：任何一项重大不合格；停止本分支，在 `docs/history` 写明证据。
- **当前：WAITING**（尚无人耳、人眼实测，不能进入 Phase 2）。
"""


def build_probe(
    *,
    midi_path: Path,
    midi_notes: Sequence[MidiNote],
    parse_stats: dict[str, int],
    ns: str,
    name: str,
    origin: tuple[int, int, int],
    out_dir: Path,
    tick_rate: int,
    stress_count: int,
    blind_notes_count: int,
    blind_seed: int,
    excerpt_start_s: float = 0.0,
    excerpt_seconds: float | None = None,
) -> tuple[dict[str, object], Path]:
    core.validate_namespace(ns)
    if not 0 < blind_notes_count <= MAX_BLIND_EVENTS:
        raise ProbeError(f"--blind-notes 必须在 1..{MAX_BLIND_EVENTS}")
    if not 0 <= stress_count <= MAX_STRESS_EVENTS:
        raise ProbeError(f"--stress-count 必须在 0..{MAX_STRESS_EVENTS}")
    if len(midi_notes) > MAX_SOURCE_EVENTS:
        raise ProbeError(f"MIDI 事件不得超过 {MAX_SOURCE_EVENTS}")
    if not (-62 <= origin[2] <= 318):
        raise ProbeError(
            f"--origin 的 Y={origin[2]} 超出探针安全范围 -62..318 "
            "(需要 Y-2 地基、Y-1 乐器垫底和 Y+1 空气)"
        )
    if len(GM_BLOCKS) != 129 or len(set(GM_BLOCKS)) != 129:
        raise ProbeError("内嵌 ENB GM 垫底方块表损坏：必须是 0..128 共 129 个唯一方块")

    timbre = plan_timbre(tick_rate)
    dynamics = plan_dynamics(tick_rate)
    chord = plan_chord(tick_rate)
    advanced = plan_advanced(tick_rate)
    midi_events, midi_clamped = plan_midi(midi_notes, tick_rate, "midi")

    # RedPiano's qzpno palette covers MIDI 12..93.  Using anything outside that
    # range would clamp only the control backend and reveal/corrupt the A/B.
    blind_candidates = [
        note for note in midi_notes if note.channel != 9 and 12 <= note.midi <= 93
    ]
    if not blind_candidates:
        raise ProbeError(
            "A/B 需要至少一个非鼓且位于 RedPiano 可比音域 MIDI 12..93 的音符"
        )
    blind_source = select_excerpt(
        blind_candidates,
        0.0,
        max(0.001, blind_candidates[-1].t + 0.001),
        blind_notes_count,
        tick_rate,
    )
    rng = random.Random(blind_seed)
    a_backend = rng.choice(("enb", "redpiano"))
    b_backend = "redpiano" if a_backend == "enb" else "enb"
    blind_a, blind_a_clamped = plan_midi(
        blind_source,
        tick_rate,
        "blind_a",
        backend=a_backend,
        force_program=0,
    )
    blind_b, blind_b_clamped = plan_midi(
        blind_source,
        tick_rate,
        "blind_b",
        backend=b_backend,
        force_program=0,
    )
    stress = plan_stress(stress_count, tick_rate)

    banks: list[tuple[str, list[ProbeEvent]]] = [
        ("timbre", timbre),
        ("dynamics", dynamics),
        ("chord", chord),
        ("advanced", advanced),
        ("midi", midi_events),
        ("blind_a", blind_a),
        ("blind_b", blind_b),
        ("stress", stress),
    ]
    zones = allocate_banks(banks, origin)
    all_events = _all_unique_events(banks)
    sequences: dict[str, list[ProbeEvent]] = {
        "timbre": timbre,
        "dynamics": dynamics,
        "chord": chord,
        "advanced": advanced,
        "midi": midi_events,
        "blind_a": blind_a,
        "blind_b": blind_b,
    }
    if stress:
        sequences["stress_64"] = stress[: min(64, len(stress))]
        sequences["stress_256"] = stress[: min(256, len(stress))]
        sequences["stress_all"] = stress

    grid = core.Grid()
    build_commands = emit_blocks(grid, all_events)
    sequence_listeners = {
        sequence_name: listener_position(events)
        for sequence_name, events in sequences.items()
    }
    listener_platforms = {
        (math.floor(x), math.floor(y) - 1, math.floor(z))
        for x, y, z in sequence_listeners.values()
    }
    for px, py, pz in sorted(listener_platforms):
        grid.put(build_commands, px, py, pz, "minecraft:barrier")
    x0, z0, x1, z1 = grid.bbox()
    if (
        x0 < -HORIZONTAL_SAFE_LIMIT
        or x1 > HORIZONTAL_SAFE_LIMIT
        or z0 < -HORIZONTAL_SAFE_LIMIT
        or z1 > HORIZONTAL_SAFE_LIMIT
    ):
        raise ProbeError(
            "探针最终边界超出 Minecraft 水平安全范围 "
            f"±{HORIZONTAL_SAFE_LIMIT}: X[{x0}..{x1}] Z[{z0}..{z1}]"
        )
    chunks = core._chunk_count(x0, z0, x1, z1)
    if chunks > PROBE_FORCELOAD_CAP:
        raise ProbeError(
            f"forceload {chunks} chunks > Phase-1 探针上限 {PROBE_FORCELOAD_CAP}; "
            "请减小 --stress-count 或使用更紧凑的测试原点"
        )
    forceload_commands = core.forceload_guard(x0, z0, x1, z1)

    dp = core.Datapack(
        ns=ns,
        name=name,
        out_dir=str(out_dir),
        mc_version=MC_VERSION,
        ox=origin[0],
        oz=origin[1],
    )
    dp.write_pack_mcmeta(
        f"{name} — ENB v{ENB_VERSION} Phase-1 probe, MC {MC_VERSION}"
    )
    dp.write_load_tick_tags()

    batches = core.batch_setblocks(build_commands, BUILD_BATCH)
    for idx, batch in enumerate(batches):
        dp.write_function(f"bld/b{idx}", batch)
    dp.write_function("tick", core.build_tick_dispatch(ns, len(batches)))

    # Physical trigger reset and exact-position cleanup are chunked.  No global
    # ``forceload remove all`` and no broad fill over neighboring builds.
    trigger_lines = sorted(
        {
            f"setblock {x} {y} {z} minecraft:air"
            for x, y, z in (event.trigger() for event in all_events)
        }
    )
    _write_chunked_function(dp, "off/all", trigger_lines)
    occupied = sorted(
        {
            (event.x, event.y - 2, event.z)
            for event in all_events
        }
        | {
            (event.x, event.y - 1, event.z)
            for event in all_events
        }
        | {(event.x, event.y, event.z) for event in all_events}
        | {event.trigger() for event in all_events}
        | listener_platforms
    )
    clear_lines = [f"setblock {x} {y} {z} minecraft:air" for x, y, z in occupied]
    _write_chunked_function(dp, "clear/all", clear_lines)

    if not stress:
        for sequence_name in ("stress_64", "stress_256", "stress_all"):
            dp.write_function(
                f"test/{sequence_name}",
                [
                    (
                        f'tellraw @a "[{ns}] 压测 bank 未生成；'
                        '重新运行脚本并把 --stress-count 设为正数。"'
                    )
                ],
            )

    scheduled_ids: list[str] = []
    for sequence_name, events in sequences.items():
        scheduled_ids.extend(write_sequence(dp, sequence_name, events, tick_rate))

    cancel_lines = [
        f"schedule clear {ns}:done",
        f"schedule clear {ns}:internal/setup_build",
        f"schedule clear {ns}:internal/stop_commit",
        f"schedule clear {ns}:internal/cleanup_commit",
    ]
    cancel_lines += [f"schedule clear {ns}:{fid}" for fid in sorted(set(scheduled_ids))]
    dp.write_function("cancel", cancel_lines)
    dp.write_function(
        "stop_silent",
        [
            f"scoreboard players set PLAY {ns} 0",
            f"function {ns}:cancel",
            "stopsound @a record",
            f"function {ns}:off/all",
        ],
    )
    dp.write_function(
        "stop",
        [
            (
                "execute in minecraft:overworld run "
                f"function {ns}:internal/stop_begin"
            )
        ],
    )
    add_forceload_commands = [
        command for command in forceload_commands if command.startswith("forceload add ")
    ]
    dp.write_function(
        "internal/stop_begin",
        [
            f"scoreboard players set PLAY {ns} 0",
            f"function {ns}:cancel",
            "stopsound @a record",
            *add_forceload_commands,
            f"schedule function {ns}:internal/stop_commit 1t replace",
        ],
    )
    dp.write_function(
        "internal/stop_commit",
        [
            f"function {ns}:stop_silent",
            f'tellraw @a "[{ns}] 已停止并清空全部红石触发槽。"',
        ],
    )
    dp.write_function(
        "done",
        [
            f"scoreboard players set PLAY {ns} 0",
            f"function {ns}:off/all",
            "stopsound @a record",
            f'tellraw @a "[{ns}] 本项播放结束；请记录观察后再跑下一项。"',
        ],
    )

    write_verify(dp, dynamics, advanced)
    scoped_remove = core.forceload_remove_region(x0, z0, x1, z1)
    dp.write_function(
        "load",
        [
            f"scoreboard objectives add {ns} dummy",
            "scoreboard objectives add rpcfg dummy",
            f"scoreboard players set BLD {ns} -1",
            f"scoreboard players set PLAY {ns} 0",
            f"function {ns}:cancel",
            "stopsound @a record",
            f"execute in minecraft:overworld run {scoped_remove}",
            (
                f'tellraw @a "[{ns}] ENB Phase-1 探针已加载（尚未建造）。'
                f'先手动 /tick rate {tick_rate}，再运行 /function {ns}:setup"'
            ),
            (
                f'tellraw @a "[{ns}] 音频前置：选项 -> 音色包，点击“默认音色 '
                '(extendednoteblock_default.zip)”直到出现绿色箭头并等待资源重载；'
                '同时确认“唱片/唱片机”音量大于 0。未激活会静音。"'
            ),
        ],
    )
    dp.write_function(
        "setup",
        [
            (
                "execute in minecraft:overworld run "
                f"function {ns}:internal/setup_begin"
            )
        ],
    )
    dp.write_function(
        "internal/setup_begin",
        [
            f"scoreboard players set PLAY {ns} 0",
            f"function {ns}:cancel",
            "stopsound @a record",
            *forceload_commands,
            f"scoreboard players set BLD {ns} -1",
            (
                f'tellraw @a "[{ns}] 正在强加载 {chunks} 个区块；'
                '下一游戏刻开始安全断电和建造。"'
            ),
            f"schedule function {ns}:internal/setup_build 1t replace",
        ],
    )
    dp.write_function(
        "internal/setup_build",
        [
            f"function {ns}:stop_silent",
            "scoreboard players set poly rpcfg 1",
            "scoreboard players set human rpcfg 1",
            f"scoreboard players set BLD {ns} 0",
            (
                f'tellraw @a "[{ns}] 建造中：{len(all_events)} 个事件块，'
                f'{len(batches)} 批；等待 built 提示。"'
            ),
        ],
    )
    dp.write_function(
        "builddone",
        [
            f"scoreboard players set BLD {ns} -1",
            f"function {ns}:verify",
            (
                f'tellraw @a "[{ns}] built. 依次运行 test/timbre、dynamics、'
                'chord、advanced、midi、blind_a/b、stress_64/256/all。"'
            ),
            (
                f'tellraw @a "[{ns}] 若任何 ENB 项静音，先停止测试并检查默认音色包'
                '是否有绿色箭头、资源是否已重载、唱片/唱片机音量是否大于 0。"'
            ),
        ],
    )
    dp.write_function(
        "cleanup",
        [
            (
                "execute in minecraft:overworld run "
                f"function {ns}:internal/cleanup_begin"
            )
        ],
    )
    dp.write_function(
        "internal/cleanup_begin",
        [
            f"scoreboard players set PLAY {ns} 0",
            f"function {ns}:cancel",
            "stopsound @a record",
            *add_forceload_commands,
            f"schedule function {ns}:internal/cleanup_commit 1t replace",
        ],
    )
    dp.write_function(
        "internal/cleanup_commit",
        [
            f"function {ns}:stop_silent",
            f"scoreboard players set BLD {ns} -1",
            f"function {ns}:clear/all",
            scoped_remove,
            (
                f'tellraw @a "[{ns}] 已精确拆除探针；'
                '请手动 /tick rate 20 恢复世界速度。"'
            ),
        ],
    )

    enb_count = sum(event.backend == "enb" for event in all_events)
    redpiano_count = len(all_events) - enb_count
    manifest: dict[str, object] = {
        "schema": 1,
        "phase": "Phase 1 / minimum validation only",
        "status": "WAITING_FOR_IN_GAME_HUMAN_TEST",
        "mc_version": MC_VERSION,
        "tick_rate": tick_rate,
        "namespace": ns,
        "name": name,
        "origin_x_z_y": list(origin),
        "execution_dimension": "minecraft:overworld",
        "forceload_chunk_cap": PROBE_FORCELOAD_CAP,
        "comparison_control": {
            "kind": "randomized single-blind screening",
            "midi_range": [12, 93],
            "listener_teleport": True,
            "same_relative_geometry": True,
            "redpiano": {
                "jar": REDPIANO_CONTROL_JAR,
                "jar_sha256": REDPIANO_CONTROL_SHA256,
                "resource_pack": QZPNO_CONTROL_ZIP,
                "resource_pack_sha256": QZPNO_CONTROL_SHA256,
                "rpcfg": {"poly": 1, "human": 1},
                "mute_available": False,
                "transition": "two record-category stopsound commands one tick apart",
            },
            "known_cue": "ENB positional; RedPiano player-centred",
            "strict_preference_gate": "loudness-normalized, independently relabelled recordings",
        },
        "stress_interpretation": {
            "stress_64": "near-field audio plus performance",
            "stress_256": "performance only; do not infer dropped audio by ear",
            "stress_all": "performance only; do not infer dropped audio by ear",
        },
        "enb": {
            "version": ENB_VERSION,
            "source_commit": ENB_SOURCE_COMMIT,
            "modrinth_version_id": ENB_MODRINTH_VERSION,
            "jar": ENB_JAR,
            "url": ENB_URL,
            "sha256": ENB_SHA256,
            "sha512": ENB_SHA512,
        },
        "source_midi": {
            "path": str(midi_path),
            "sha256": _sha256(midi_path),
            "selected_notes": len(midi_notes),
            "start_s": round(excerpt_start_s, 4),
            "end_s": round(
                excerpt_start_s
                + (
                    excerpt_seconds
                    if excerpt_seconds is not None
                    else max((n.t for n in midi_notes), default=0.0)
                ),
                4,
            ),
            "selected_onset_span_s": round(
                max((n.t for n in midi_notes), default=0.0), 4
            ),
            "parse": parse_stats,
            "sustain_clamped": midi_clamped,
        },
        "counts": {
            "physical_events": len(all_events),
            "enb": enb_count,
            "redpiano": redpiano_count,
            "stress": len(stress),
            "build_commands": len(build_commands),
            "build_batches": len(batches),
            "midi": len(midi_events),
            "blind_each": len(blind_source),
            "blind_ineligible": len(midi_notes) - len(blind_candidates),
            "sustain_clamped_total": (
                midi_clamped + blind_a_clamped + blind_b_clamped
            ),
        },
        "bounds": {
            "x0": x0,
            "z0": z0,
            "x1": x1,
            "z1": z1,
            "y": origin[2],
            "chunks": chunks,
        },
        "zones": zones,
        "sequence_listeners": {
            key: list(value) for key, value in sequence_listeners.items()
        },
        "listener_platforms": len(listener_platforms),
        "sequences": {key: len(value) for key, value in sequences.items()},
        "events": [_public_event(event) for event in all_events],
    }
    manifest["static_audit"] = audit_datapack(Path(dp.root), ns)
    dp.write("probe_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    dp.write("ENB_PROBE_REPORT.md", report_markdown(manifest, ns))
    blind_key = {
        "warning": "Complete and record A/B listening before reading this file.",
        "seed": blind_seed,
        "A": a_backend,
        "B": b_backend,
        "enb_piano_program": 0,
        "redpiano": "Salamander three-layer qzpno mapping",
    }
    dp.write("blind_key.json", json.dumps(blind_key, ensure_ascii=False, indent=2))
    return manifest, Path(dp.root)


def deploy_build(build_root: Path, world_datapacks: Path, ns: str) -> Path:
    if world_datapacks.name.lower() != "datapacks":
        raise ProbeError(
            f"--world-dir 必须直接指向 saves/<世界>/datapacks；当前是 {world_datapacks}"
        )
    if not world_datapacks.is_dir():
        raise ProbeError(f"--world-dir 不存在或不是目录: {world_datapacks}")
    destination = world_datapacks / ns
    if destination.exists():
        raise ProbeError(
            f"部署目标已存在，POC 为避免误删不会覆盖: {destination}；"
            "请换 --namespace，或先在确认后手动移走旧探针"
        )
    shutil.copytree(build_root, destination)
    required = [
        destination / "pack.mcmeta",
        destination / "data" / ns / "function" / "setup.mcfunction",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ProbeError(f"部署后校验失败，缺少: {missing}")
    return destination


def run_selftest() -> None:
    assert len(GM_BLOCKS) == 129
    assert len(set(GM_BLOCKS)) == 129
    assert GM_BLOCKS[0] == "minecraft:dirt"
    assert GM_BLOCKS[30] == "minecraft:obsidian"
    assert GM_BLOCKS[33] == "minecraft:spruce_planks"
    assert GM_BLOCKS[48] == "minecraft:calcite"
    assert GM_BLOCKS[128] == "minecraft:sandstone"
    assert pitch_state(60) == "c" and pitch_state(61) == "cs"
    assert sustain_ticks(1.0, 20) == (20, False)
    assert sustain_ticks(1.0, 80) == (80, False)
    assert sustain_ticks(99.0, 80) == (400, True)

    event = ProbeEvent(
        bank="test",
        tick=0,
        midi=64,
        velocity=120,
        sustain=80,
        delayed_ms=250,
        fade_in=2,
        fade_out=4,
        advanced=(
            "SoundPath:[{x:0.0d,y:0.0d,z:0.0d},"
            "{x:1.0d,y:0.0d,z:0.0d}]"
        ),
    )
    nbt = enb_nbt(event)
    for field in (
        "note:64",
        "velocity:120",
        "sustainTime:80",
        "delayedPlayingTime:250",
        "fadeInTime:2",
        "fadeOutTime:4",
        "AdvancedData:{SoundPath:",
        "0.0d",
    ):
        assert field in nbt, field
    assert "minecraft:block_entity_data" not in nbt

    synthetic = [
        MidiNote(0.0, 0.5, 60, 64, 0, 0),
        MidiNote(0.0, 0.5, 64, 96, 0, 0),
        MidiNote(0.5, 1.0, 67, 127, 0, 0),
    ]
    for bad_start, bad_seconds in ((math.nan, 1.0), (0.0, math.inf)):
        try:
            select_excerpt(synthetic, bad_start, bad_seconds, 3, 80)
        except ProbeError:
            pass
        else:
            raise AssertionError("non-finite excerpt arguments must be rejected")

    with tempfile.TemporaryDirectory(prefix="enb_probe_selftest_") as temp:
        temp_path = Path(temp)
        try:
            import mido
        except ImportError:
            mido = None
        if mido is not None:
            parser_midi = temp_path / "parser.mid"
            mf = mido.MidiFile(type=0, ticks_per_beat=480)
            track = mido.MidiTrack()
            mf.tracks.append(track)
            track.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
            track.append(mido.Message("program_change", channel=0, program=30, time=0))
            track.append(mido.Message("note_on", channel=0, note=60, velocity=90, time=0))
            # A program change before NOTE OFF must not relabel the active note.
            track.append(mido.Message("program_change", channel=0, program=48, time=10))
            track.append(mido.Message("note_off", channel=0, note=60, time=10))
            track.append(mido.Message("note_on", channel=9, note=36, velocity=100, time=0))
            track.append(mido.Message("note_off", channel=9, note=36, time=10))
            track.append(mido.Message("note_on", channel=0, note=62, velocity=80, time=0))
            track.append(mido.Message("note_on", channel=0, note=62, velocity=70, time=10))
            track.append(mido.Message("note_off", channel=0, note=62, time=10))
            track.append(mido.Message("note_on", channel=0, note=65, velocity=60, time=0))
            track.append(mido.MetaMessage("end_of_track", time=10))
            mf.save(str(parser_midi))
            parsed, parser_stats = parse_midi(parser_midi)
            assert next(note for note in parsed if note.midi == 60).program == 30
            assert next(note for note in parsed if note.channel == 9).program == 128
            assert sum(note.midi == 62 for note in parsed) == 2
            assert parser_stats == {"retriggers": 1, "dangling": 1}

            type2_midi = temp_path / "type2.mid"
            type2 = mido.MidiFile(type=2, ticks_per_beat=480)
            type2_track = mido.MidiTrack()
            type2.tracks.append(type2_track)
            type2_track.append(
                mido.Message("note_on", channel=0, note=60, velocity=90, time=0)
            )
            type2_track.append(
                mido.Message("note_off", channel=0, note=60, time=10)
            )
            type2.save(str(type2_midi))
            try:
                parse_midi(type2_midi)
            except ProbeError as exc:
                assert "type 2" in str(exc)
            else:
                raise AssertionError("MIDI type 2 must be rejected cleanly")

        midi_stub = temp_path / "source.mid"
        # build_probe only hashes this path; parsing is independently exercised in
        # normal generation, so a deterministic stub keeps --selftest mido-free.
        midi_stub.write_bytes(b"MThd-selftest")
        manifest, root = build_probe(
            midi_path=midi_stub,
            midi_notes=synthetic,
            parse_stats={"retriggers": 0, "dangling": 0},
            ns="enbselftest",
            name="ENB self-test",
            origin=(0, 0, 200),
            out_dir=temp_path / "build",
            tick_rate=80,
            stress_count=12,
            blind_notes_count=3,
            blind_seed=7,
            excerpt_start_s=0.0,
            excerpt_seconds=1.5,
        )
        assert manifest["mc_version"] == MC_VERSION
        assert (root / "pack.mcmeta").is_file()
        assert (
            root / "data" / "minecraft" / "tags" / "function" / "load.json"
        ).is_file()
        assert (
            root / "data" / "enbselftest" / "function" / "setup.mcfunction"
        ).is_file()
        pack = json.loads((root / "pack.mcmeta").read_text(encoding="utf-8"))
        assert pack["pack"]["pack_format"] == 48
        all_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in root.rglob("*.mcfunction")
        )
        assert "forceload remove all" not in all_text
        assert "minecraft:block_entity_data" not in all_text
        assert "commandModificationBlockLimit" not in all_text
        assert "\ntick rate " not in "\n" + all_text
        assert "stopsound @a record" in all_text
        assert "minecraft:stone" in all_text
        assert "minecraft:barrier" in all_text
        assert "schedule function enbselftest:seq/chord/" in all_text
        chord_first = (
            root
            / "data"
            / "enbselftest"
            / "function"
            / "seq"
            / "chord"
            / "s0000.mcfunction"
        ).read_text(encoding="utf-8")
        assert chord_first.count("minecraft:redstone_block") == 12
        assert "off0000_enb 1t" not in chord_first
        run_timbre_wrapper = (
            root
            / "data"
            / "enbselftest"
            / "function"
            / "test"
            / "timbre.mcfunction"
        ).read_text(encoding="utf-8")
        assert (
            "execute in minecraft:overworld run "
            "function enbselftest:internal/test/timbre"
        ) in run_timbre_wrapper
        run_timbre = (
            root
            / "data"
            / "enbselftest"
            / "function"
            / "internal"
            / "test"
            / "timbre.mcfunction"
        ).read_text(encoding="utf-8")
        assert "stop_silent" in run_timbre
        assert "in minecraft:overworld run tp @s" in run_timbre
        assert "scoreboard players set poly rpcfg 1" in run_timbre
        assert "s0000 1t replace" in run_timbre

        setup_wrapper = (
            root / "data" / "enbselftest" / "function" / "setup.mcfunction"
        ).read_text(encoding="utf-8")
        setup_begin = (
            root
            / "data"
            / "enbselftest"
            / "function"
            / "internal"
            / "setup_begin.mcfunction"
        ).read_text(encoding="utf-8")
        setup_build = (
            root
            / "data"
            / "enbselftest"
            / "function"
            / "internal"
            / "setup_build.mcfunction"
        ).read_text(encoding="utf-8")
        assert "execute in minecraft:overworld" in setup_wrapper
        assert "forceload add " in setup_begin
        assert "stop_silent" not in setup_begin
        assert "stop_silent" in setup_build

        cleanup_begin = (
            root
            / "data"
            / "enbselftest"
            / "function"
            / "internal"
            / "cleanup_begin.mcfunction"
        ).read_text(encoding="utf-8")
        cleanup_commit = (
            root
            / "data"
            / "enbselftest"
            / "function"
            / "internal"
            / "cleanup_commit.mcfunction"
        ).read_text(encoding="utf-8")
        assert "forceload add " in cleanup_begin
        assert cleanup_commit.index("function enbselftest:clear/all") < (
            cleanup_commit.index("forceload remove ")
        )

        verify_text = (
            root
            / "data"
            / "enbselftest"
            / "function"
            / "internal"
            / "verify.mcfunction"
        ).read_text(encoding="utf-8")
        for required in (
            "fadeInTime",
            "fadeOutTime",
            "AdvancedData.SoundPath[1].y",
            "AdvancedData.PitchBendPoints[1].v",
        ):
            assert required in verify_text

        report = (root / "ENB_PROBE_REPORT.md").read_text(encoding="utf-8")
        assert "extendednoteblock_default.zip" in report
        assert "单盲初筛" in report and "位置声" in report
        assert manifest["listener_platforms"] > 0

        tail_dp = core.Datapack(
            ns="enbtailtest",
            name="tail regression",
            out_dir=str(temp_path / "tail"),
            mc_version=MC_VERSION,
            ox=0,
            oz=0,
        )
        tail_events = [
            ProbeEvent("tail", 0, 60, 100, 240),
            ProbeEvent("tail", 160, 64, 100, 8),
        ]
        allocate_banks([("tail", tail_events)], (0, 0, 200))
        write_sequence(tail_dp, "overhang", tail_events, 80)
        tail_last = (
            Path(tail_dp.root)
            / "data"
            / "enbtailtest"
            / "function"
            / "seq"
            / "overhang"
            / "s0001.mcfunction"
        ).read_text(encoding="utf-8")
        assert "schedule function enbtailtest:done 83t replace" in tail_last
    print("ENB Phase-1 probe self-test: PASS")


def build_argparser() -> argparse.ArgumentParser:
    default_midi = REPO_ROOT / "minecraft-redstone-music" / "assets" / "demo.mid"
    parser = argparse.ArgumentParser(
        description=(
            "Build the isolated ENB v1.9.1 / MC 1.21.1 Phase-1 diagnostic datapack. "
            "This does not add a production backend."
        )
    )
    parser.add_argument("--midi", default=str(default_midi), help="source MIDI")
    parser.add_argument("--namespace", "--ns", default="enbprobe", dest="namespace")
    parser.add_argument("--name", default=None, help="display name")
    parser.add_argument(
        "--origin",
        nargs=3,
        type=int,
        metavar=("X", "Z", "Y"),
        default=(0, 0, 200),
        help="probe origin in repository convention X Z Y (default: 0 0 200)",
    )
    parser.add_argument("--mc-version", default=MC_VERSION)
    parser.add_argument(
        "--tick-rate",
        type=int,
        choices=(20, 80),
        default=80,
        help="server tick rate; sustain and MIDI schedule scale with it (default: 80)",
    )
    parser.add_argument("--start", type=float, default=0.0, help="MIDI excerpt start seconds")
    parser.add_argument("--seconds", type=float, default=12.0, help="excerpt length seconds")
    parser.add_argument("--max-notes", type=int, default=64)
    parser.add_argument("--blind-notes", type=int, default=32)
    parser.add_argument("--blind-seed", type=int, default=20260723)
    parser.add_argument(
        "--stress-count",
        type=int,
        default=512,
        help="large ENB bank size; 0 disables it (default: 512)",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "build"),
        help="staging parent; datapack lands at <out>/<namespace>",
    )
    parser.add_argument(
        "--world-dir",
        default=None,
        help="optional saves/<world>/datapacks directory; omitted = build only",
    )
    parser.add_argument("--selftest", action="store_true")
    return parser


def run(args: argparse.Namespace) -> None:
    if args.mc_version != MC_VERSION:
        raise ProbeError(
            f"ENB Phase-1 探针只允许 Minecraft {MC_VERSION}；收到 {args.mc_version}。"
            "不静默降级，也不修改 Family A 支持范围。"
        )
    if not 0 < args.blind_notes <= MAX_BLIND_EVENTS:
        raise ProbeError(f"--blind-notes 必须在 1..{MAX_BLIND_EVENTS}")
    if not 0 < args.max_notes <= MAX_SOURCE_EVENTS:
        raise ProbeError(f"--max-notes 必须在 1..{MAX_SOURCE_EVENTS}")
    if not 0 <= args.stress_count <= MAX_STRESS_EVENTS:
        raise ProbeError(f"--stress-count 必须在 0..{MAX_STRESS_EVENTS}")
    if not math.isfinite(args.start) or not math.isfinite(args.seconds):
        raise ProbeError("--start/--seconds 必须是有限数字")
    midi_path = Path(args.midi).expanduser().resolve()
    all_notes, parse_stats = parse_midi(midi_path)
    excerpt = select_excerpt(
        all_notes, args.start, args.seconds, args.max_notes, args.tick_rate
    )
    name = args.name or f"{midi_path.stem} ENB Phase-1"
    manifest, build_root = build_probe(
        midi_path=midi_path,
        midi_notes=excerpt,
        parse_stats=parse_stats,
        ns=args.namespace,
        name=name,
        origin=tuple(args.origin),
        out_dir=Path(args.out).expanduser().resolve(),
        tick_rate=args.tick_rate,
        stress_count=args.stress_count,
        blind_notes_count=args.blind_notes,
        blind_seed=args.blind_seed,
        excerpt_start_s=args.start,
        excerpt_seconds=args.seconds,
    )
    destination = None
    if args.world_dir:
        destination = deploy_build(
            build_root, Path(args.world_dir).expanduser().resolve(), args.namespace
        )

    counts = manifest["counts"]
    bounds = manifest["bounds"]
    print("=" * 72)
    print(f"ENB Phase-1 probe built: {build_root}")
    print(
        f"MC {MC_VERSION} / ENB {ENB_VERSION} / tick rate {args.tick_rate} / "
        f"MIDI {counts['midi']} notes"
    )
    print(
        f"events={counts['physical_events']} (ENB={counts['enb']}, "
        f"RedPiano blind={counts['redpiano']}), stress={counts['stress']}"
    )
    print(
        f"bbox X[{bounds['x0']}..{bounds['x1']}] "
        f"Z[{bounds['z0']}..{bounds['z1']}] chunks={bounds['chunks']}"
    )
    if destination:
        print(f"DEPLOY VERIFIED: {destination}")
        print(f"Next: /reload -> /function {args.namespace}:setup")
    else:
        print("BUILD ONLY: 尚未安装进任何世界，不能在游戏里调用函数。")
        print(
            "按 ENB_PROBE_REPORT.md 安装官方 ENB/Fabric 依赖后，"
            "再用 --world-dir 部署到 1.21.1 测试存档。"
        )
    print("Phase 2 remains gated until every human checklist item is recorded.")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    try:
        if args.selftest:
            run_selftest()
        else:
            run(args)
    except (ProbeError, core.RedPianoError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {_err_str(exc)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
