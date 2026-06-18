"""生成一个公有领域测试 MIDI(C 大调音阶 + 贝多芬《欢乐颂》开头,均 PD),用来证明
MIDI->机器这条精确管线"音高分毫不差、节奏正确"。Run: <venv-demucs python> gen_demo_midi.py
"""
import os, mido
HERE = os.path.dirname(os.path.abspath(__file__))
mid = mido.MidiFile(); mid.ticks_per_beat = 480
tr = mido.MidiTrack(); mid.tracks.append(tr)
tr.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(110), time=0))
def note(p, beats, vel=92):
    tr.append(mido.Message('note_on', note=p, velocity=vel, time=0))
    tr.append(mido.Message('note_off', note=p, velocity=0, time=int(beats * mid.ticks_per_beat)))
for p in [60, 62, 64, 65, 67, 69, 71, 72]:                     # C major scale (diagnostic: hear any off note)
    note(p, 0.5)
note(72, 0.5)
for p in [64, 64, 65, 67, 67, 65, 64, 62, 60, 60, 62, 64]:     # Ode to Joy opening (Beethoven, public domain)
    note(p, 0.5)
note(64, 0.75); note(62, 0.25); note(62, 1.0)
out = os.path.join(HERE, 'demo.mid'); mid.save(out)
print('wrote', out)
