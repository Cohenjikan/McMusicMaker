# -*- coding: utf-8 -*-
"""parse_midi.py — MIDI -> notes.json (t/midi/vel/dur). 容错: clip=True + merge_tracks + 排除鼓(ch9)。
Run(venv-demucs python, 有 mido): python parse_midi.py <midi> <out.json>
"""
import sys, json, mido
path, out = sys.argv[1], sys.argv[2]
mid = mido.MidiFile(path, clip=True)
merged = mido.merge_tracks(mid.tracks)
tpb = mid.ticks_per_beat
tempo, sec = 500000, 0.0
on, notes = {}, []
for msg in merged:
    sec += mido.tick2second(msg.time, tpb, tempo)
    if msg.type == 'set_tempo':
        tempo = msg.tempo
    elif msg.type == 'note_on' and msg.velocity > 0 and getattr(msg, 'channel', 0) != 9:
        on[(msg.channel, msg.note)] = (sec, msg.velocity)
    elif (msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0)) and getattr(msg, 'channel', 0) != 9:
        k = (msg.channel, msg.note)
        if k in on:
            t0, vel = on.pop(k)
            notes.append({'t': round(t0, 4), 'midi': msg.note, 'vel': round(vel / 127.0, 4), 'dur': round(sec - t0, 4)})
notes.sort(key=lambda n: (n['t'], -n['midi']))
json.dump({'notes': notes}, open(out, 'w', encoding='utf-8'), ensure_ascii=False)
ms = [n['midi'] for n in notes]
durs = sorted(n['dur'] for n in notes)
print(f'notes={len(notes)} dur={notes[-1]["t"]:.1f}s  midi {min(ms)}-{max(ms)} (span {max(ms)-min(ms)})')
print(f'  dur 中位={durs[len(durs)//2]:.2f}s 最长={durs[-1]:.2f}s  长音(>2.8s)={sum(1 for d in durs if d>2.8)}个')
print(f'  力度 p/mf/f = {sum(1 for n in notes if n["vel"]<0.4)}/{sum(1 for n in notes if 0.4<=n["vel"]<0.72)}/{sum(1 for n in notes if n["vel"]>=0.72)}')
