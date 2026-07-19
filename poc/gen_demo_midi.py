"""生成随包的 license-clean 冒烟测试 MIDI(minecraft-redstone-music/assets/demo.mid)。

全部音符均为本项目原创的通用测试素材(音阶跑动 + 根音 + 三度叠置垫底 + 导音短句 + 基础鼓循环),
不含任何受版权保护的旋律,可自由随仓分发。它的用途是证明 MIDI→机器这条管线
"音高分毫不差、节奏正确、多声部对齐":5 个声部各自考一件事——
  piano 音阶跑动 → 单音音高准不准; bass 二分根音 → 长音不断; pad 叠置和弦 → 同刻多音;
  lead 高音区短句 → 音域上界; drums 十六分踩镲 → 密集节奏不丢音。

Run: python poc/gen_demo_midi.py [输出路径]
"""
import os, sys, mido

PPQ = 480
BPM = 110
BEAT = PPQ                                     # 一拍 = 480 tick
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, os.pardir, 'minecraft-redstone-music', 'assets', 'demo.mid')

# ── 声部 1: 钢琴音阶跑动(C 大调上行→下行→再上行, 每音半拍) ──────────────────
PIANO = [60, 62, 64, 65, 67, 69, 67, 65, 64, 62, 60, 62, 64, 67, 72]
# ── 声部 2: 贝斯根音(I–V–IV–ii, 每音一拍, 每个根音重复两次) ─────────────────
BASS = [36, 36, 43, 43, 41, 41, 38, 38]
# ── 声部 3: 垫底和弦(每两拍换一个, 尾部交叠 96 tick 形成连奏) ────────────────
PAD = [(48, 55), (55, 62), (53, 60), (50, 57)]
PAD_STEP, PAD_OVERLAP = 2 * BEAT, 96
# ── 声部 4: 高音区导音短句(每音半拍, 断奏) ──────────────────────────────────
LEAD = [96, 98, 100, 98, 96, 93, 91, 96]
LEAD_START, LEAD_STEP, LEAD_DUR = 120, 240, 192
# ── 声部 5: 鼓循环(底鼓/军鼓交替 + 十六分踩镲, 循环 8 遍) ────────────────────
KICK, SNARE, HIHAT = 36, 38, 42
DRUM_BARS, DRUM_UNIT = 8, BEAT


def to_track(events, program=None, channel=0):
    """把 [(绝对tick, 'on'/'off', 音高, 力度)] 事件表转成 delta-time 轨道。"""
    tr = mido.MidiTrack()
    if program is not None:
        tr.append(mido.Message('program_change', channel=channel, program=program, time=0))
    prev = 0
    for tick, kind, note, vel in events:                      # 稳定排序: 同刻事件保持写入顺序
        tr.append(mido.Message('note_' + kind, channel=channel, note=note,
                               velocity=vel, time=tick - prev))
        prev = tick
    return tr


def seq(notes, dur, vel, start=0, step=None):
    """等距单音序列 → 事件表(step 默认与 dur 相同, 即无缝连奏)。"""
    step = dur if step is None else step
    ev = []
    for i, p in enumerate(notes):
        t = start + i * step
        ev += [(t, 'on', p, vel), (t + dur, 'off', p, 0)]
    return ev


mid = mido.MidiFile(type=1, ticks_per_beat=PPQ)

tempo = mido.MidiTrack()
tempo.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(BPM), time=0))
mid.tracks.append(tempo)

mid.tracks.append(to_track(seq(PIANO, BEAT // 2, 96), program=0, channel=0))
mid.tracks.append(to_track(seq(BASS, BEAT, 80), program=33, channel=1))

pad = []
for i, chord in enumerate(PAD):                               # 和弦交叠: 下一个进来后旧的才松手
    t = i * PAD_STEP
    pad += [(t, 'on', p, 64) for p in chord]
    pad += [(t + PAD_STEP + PAD_OVERLAP, 'off', p, 0) for p in chord]
mid.tracks.append(to_track(sorted(pad, key=lambda e: e[0]), program=89, channel=2))

mid.tracks.append(to_track(seq(LEAD, LEAD_DUR, 88, start=LEAD_START, step=LEAD_STEP),
                           program=81, channel=3))

drums = []
for bar in range(DRUM_BARS):                                  # 每单位: 底鼓/军鼓在前后半, 踩镲走十六分
    t0 = bar * DRUM_UNIT
    drums += [(t0, 'on', KICK, 100), (t0 + 120, 'off', KICK, 0),
              (t0 + DRUM_UNIT // 2, 'on', SNARE, 90), (t0 + DRUM_UNIT // 2 + 120, 'off', SNARE, 0)]
    for k in range(4):
        t = t0 + k * (DRUM_UNIT // 4)
        drums += [(t, 'on', HIHAT, 70), (t + 48, 'off', HIHAT, 0)]
mid.tracks.append(to_track(sorted(drums, key=lambda e: e[0]), channel=9))

out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT)
mid.save(out)
print('wrote', out)
