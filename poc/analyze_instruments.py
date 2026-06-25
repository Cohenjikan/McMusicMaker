# -*- coding: utf-8 -*-
"""analyze_instruments.py — 任务5 前置: 自动识别一首 MIDI 里哪些声部是钢琴 / 非钢琴。

依据 General MIDI:
  - program_change 的 program 号 -> GM 乐器(0-7=钢琴家族, 8+=非钢琴);
  - channel 9(0基)= GM 打击乐通道 -> 鼓(非钢琴), 与 program 无关;
  - 按【声部 = (track, channel)】统计: 乐器名/家族、音符数、音域、时长、复音, 并判 钢琴/非钢琴。
输出: 控制台报告 + `notes_<stem>_instruments.json`(每个声部一段, 供任务5 分配音色用)。
Run: python analyze_instruments.py <song.mid> [--json out.json]
"""
import sys, os, json
import mido
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

GM = [  # 128 General MIDI 乐器名(program 0..127)
 "Acoustic Grand Piano","Bright Acoustic Piano","Electric Grand Piano","Honky-tonk Piano",
 "Electric Piano 1","Electric Piano 2","Harpsichord","Clavi",
 "Celesta","Glockenspiel","Music Box","Vibraphone","Marimba","Xylophone","Tubular Bells","Dulcimer",
 "Drawbar Organ","Percussive Organ","Rock Organ","Church Organ","Reed Organ","Accordion","Harmonica","Tango Accordion",
 "Acoustic Guitar (nylon)","Acoustic Guitar (steel)","Electric Guitar (jazz)","Electric Guitar (clean)",
 "Electric Guitar (muted)","Overdriven Guitar","Distortion Guitar","Guitar Harmonics",
 "Acoustic Bass","Electric Bass (finger)","Electric Bass (pick)","Fretless Bass","Slap Bass 1","Slap Bass 2","Synth Bass 1","Synth Bass 2",
 "Violin","Viola","Cello","Contrabass","Tremolo Strings","Pizzicato Strings","Orchestral Harp","Timpani",
 "String Ensemble 1","String Ensemble 2","Synth Strings 1","Synth Strings 2","Choir Aahs","Voice Oohs","Synth Voice","Orchestra Hit",
 "Trumpet","Trombone","Tuba","Muted Trumpet","French Horn","Brass Section","Synth Brass 1","Synth Brass 2",
 "Soprano Sax","Alto Sax","Tenor Sax","Baritone Sax","Oboe","English Horn","Bassoon","Clarinet",
 "Piccolo","Flute","Recorder","Pan Flute","Blown Bottle","Shakuhachi","Whistle","Ocarina",
 "Lead 1 (square)","Lead 2 (sawtooth)","Lead 3 (calliope)","Lead 4 (chiff)","Lead 5 (charang)","Lead 6 (voice)","Lead 7 (fifths)","Lead 8 (bass+lead)",
 "Pad 1 (new age)","Pad 2 (warm)","Pad 3 (polysynth)","Pad 4 (choir)","Pad 5 (bowed)","Pad 6 (metallic)","Pad 7 (halo)","Pad 8 (sweep)",
 "FX 1 (rain)","FX 2 (soundtrack)","FX 3 (crystal)","FX 4 (atmosphere)","FX 5 (brightness)","FX 6 (goblins)","FX 7 (echoes)","FX 8 (sci-fi)",
 "Sitar","Banjo","Shamisen","Koto","Kalimba","Bag pipe","Fiddle","Shanai",
 "Tinkle Bell","Agogo","Steel Drums","Woodblock","Taiko Drum","Melodic Tom","Synth Drum","Reverse Cymbal",
 "Guitar Fret Noise","Breath Noise","Seashore","Bird Tweet","Telephone Ring","Helicopter","Applause","Gunshot"]
FAMILY = ["Piano","Chromatic Percussion","Organ","Guitar","Bass","Strings","Ensemble","Brass",
          "Reed","Pipe","Synth Lead","Synth Pad","Synth Effects","Ethnic","Percussive","Sound Effects"]
def gm_name(p): return GM[p] if 0 <= p < 128 else f"prog{p}"
def gm_family(p): return FAMILY[p // 8] if 0 <= p < 128 else "?"
def is_piano(prog, channel): return channel != 9 and 0 <= prog <= 7   # ch9=drums=非钢琴

def analyze(path):
    mf = mido.MidiFile(path)
    # 累积每条 (track,channel) 的事件; program 可能随时间切换 -> 取按时间区段最常用 + 记全部
    parts = {}   # (track,ch) -> dict
    for ti, tr in enumerate(mf.tracks):
        tname = None; cur_prog = {}; abst = 0
        for msg in tr:
            abst += msg.time
            if msg.type == 'track_name': tname = msg.name
            elif msg.type == 'program_change':
                cur_prog[msg.channel] = msg.program
                key = (ti, msg.channel)
                parts.setdefault(key, _newpart(ti, msg.channel, tname))
                parts[key]['progs'][msg.program] = parts[key]['progs'].get(msg.program, 0)
            elif msg.type == 'note_on' and msg.velocity > 0:
                ch = msg.channel; key = (ti, ch)
                p = parts.setdefault(key, _newpart(ti, ch, tname))
                prog = cur_prog.get(ch, 0)
                p['progs'][prog] = p['progs'].get(prog, 0) + 1
                p['notes'] += 1
                p['pitch_lo'] = min(p['pitch_lo'], msg.note); p['pitch_hi'] = max(p['pitch_hi'], msg.note)
                p['t_lo'] = min(p['t_lo'], abst); p['t_hi'] = max(p['t_hi'], abst)
                if tname and not p['name']: p['name'] = tname
    # 换算 tick->秒 需 tempo; 简化用默认 500000us/beat 若无 set_tempo。这里只报相对量级。
    return mf, parts

def _newpart(ti, ch, tname):
    return {'track': ti, 'channel': ch, 'name': tname, 'progs': {}, 'notes': 0,
            'pitch_lo': 999, 'pitch_hi': -1, 't_lo': 10**12, 't_hi': 0}

def main():
    path = sys.argv[1]
    outj = None
    if '--json' in sys.argv: outj = sys.argv[sys.argv.index('--json') + 1]
    mf, parts = analyze(path)
    rows = []
    for key in sorted(parts):
        p = parts[key]
        if p['notes'] == 0: continue
        # 主 program = 该声部音符最多的 program(ch9 视为鼓)
        main_prog = max(p['progs'], key=p['progs'].get) if p['progs'] else 0
        drums = (p['channel'] == 9)
        piano = is_piano(main_prog, p['channel'])
        rows.append({**p, 'main_prog': (-1 if drums else main_prog),
                     'instrument': ('Drums (GM ch10)' if drums else gm_name(main_prog)),
                     'family': ('Percussion (Drumkit)' if drums else gm_family(main_prog)),
                     'piano': bool(piano),
                     'all_progs': sorted(p['progs'])})
    rows.sort(key=lambda r: -r['notes'])
    total = sum(r['notes'] for r in rows)
    print(f"=== {os.path.basename(path)} | format {mf.type}, {len(mf.tracks)} tracks, 共 {len(rows)} 个发声声部, {total} 音 ===\n")
    hdr = f"{'声部(trk,ch)':12} {'钢琴?':5} {'乐器(主program)':30} {'家族':22} {'音符':>6} {'音域':>9} {'其它program'}"
    print(hdr); print('-' * len(hdr))
    for r in rows:
        tag = '钢琴' if r['piano'] else '★非钢'
        rng = f"{r['pitch_lo']}-{r['pitch_hi']}"
        others = '' if len(r['all_progs']) <= 1 else ' '.join(f"{q}:{gm_name(q)[:10]}" for q in r['all_progs'] if q != (r['main_prog'] if r['main_prog']>=0 else None))
        print(f"({r['track']:>2},{r['channel']:>2})    {tag:5} {r['instrument'][:30]:30} {r['family'][:22]:22} {r['notes']:>6} {rng:>9} {others}")
    npn = [r for r in rows if not r['piano']]
    print(f"\n--- 判定 ---")
    print(f"钢琴声部: {len([r for r in rows if r['piano']])} 个, {sum(r['notes'] for r in rows if r['piano'])} 音")
    print(f"★非钢琴声部: {len(npn)} 个, {sum(r['notes'] for r in npn)} 音:")
    for r in npn:
        print(f"   - (trk{r['track']},ch{r['channel']}) {r['instrument']} [{r['family']}], {r['notes']} 音, 音域 {r['pitch_lo']}-{r['pitch_hi']}")
    if outj:
        json.dump({'file': os.path.basename(path), 'parts': rows}, open(outj, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print(f"\n-> {outj}")

if __name__ == '__main__':
    main()
