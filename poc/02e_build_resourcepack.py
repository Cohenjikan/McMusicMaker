# -*- coding: utf-8 -*-
"""02e_build_resourcepack.py — 组装 qzpno 资源包(钢琴 + 新乐器), 重新打包并部署。

把 5 个采样库(piano/bass/lead/pad/drums)的 ogg 全部放进 qzpno 资源包:
  build/qzpno_mv/assets/qzpno/sounds/<id>.ogg  +  sounds.json(每个 id 一条 master 事件)。
钢琴 ogg 原样保留(id/文件名不变)-> 已部署钢琴机器音色不变; 仅【追加】新乐器音效。
模组播 qzpno:<id> -> 解析到 assets/qzpno/sounds/<id>.ogg。
Run: python 02e_build_resourcepack.py
"""
import os, sys, json, shutil, zipfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.join(HERE, 'build', 'qzpno_mv')
SND = os.path.join(PACK, 'assets', 'qzpno', 'sounds')
RP_DST = r"C:/Minecraft/ModrinthApp/profiles/Fabric 1.21.8/resourcepacks/qzpno_mv.zip"
LIBS = [('piano', 'samples_piano'), ('bass', 'samples_bass'), ('lead', 'samples_lead'),
        ('pad', 'samples_pad'), ('drums', 'samples_drums')]

if os.path.isdir(SND): shutil.rmtree(SND)
os.makedirs(SND)
sounds_json, counts, missing = {}, {}, []
for inst, sub in LIBS:
    man_path = os.path.join(HERE, f'samples_manifest_{inst}.json')
    if not os.path.isfile(man_path):
        print(f'[warn] 缺 {man_path}, 跳过'); continue
    man = json.load(open(man_path, encoding='utf-8'))
    srcdir = os.path.join(HERE, sub)
    n = 0
    for s in man['samples']:
        src = os.path.join(srcdir, s['file'])
        if not os.path.isfile(src): missing.append(src); continue
        shutil.copy2(src, os.path.join(SND, s['file']))
        sounds_json[s['id']] = {"category": "master", "sounds": [{"name": f"qzpno:{s['id']}", "stream": False}]}
        n += 1
    counts[inst] = n

assert not missing, f"缺 ogg: {missing[:5]}"
json.dump(sounds_json, open(os.path.join(PACK, 'assets', 'qzpno', 'sounds.json'), 'w', encoding='utf-8'), ensure_ascii=False)
# ★ pack_format 必须匹配 MC 版本! 用错(如 34=1.21.0)MC 判"不兼容"并把本包从 options 移除
#   -> 所有 qzpno 音 "unknown soundEvent" = 全静音(本轮踩过)。自动读同目录可用包的格式以永远匹配。
def detect_rp_format(default=64):
    rpdir = os.path.dirname(RP_DST)
    for ref in ('dyfi_mv.zip', 'lyy_mv.zip', 'qzgtr_mv.zip'):
        p = os.path.join(rpdir, ref)
        if os.path.isfile(p):
            try:
                with zipfile.ZipFile(p) as z:
                    return json.loads(z.read('pack.mcmeta'))['pack']['pack_format']
            except Exception:
                pass
    return default
RP_FORMAT = detect_rp_format(64)
json.dump({"pack": {"pack_format": RP_FORMAT, "description": "qzpno 钢琴+乐队(piano/bass/lead/pad/drums) for RedPiano mod"}},
          open(os.path.join(PACK, 'pack.mcmeta'), 'w', encoding='utf-8'), indent=2)

# 打包 zip(根含 pack.mcmeta + assets/)
if os.path.isfile(RP_DST): os.remove(RP_DST)
with zipfile.ZipFile(RP_DST, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(PACK):
        for f in files:
            full = os.path.join(root, f)
            z.write(full, os.path.relpath(full, PACK))

total = sum(counts.values())
print('=== 02e 资源包(钢琴+新乐器) ===')
print(f'sounds.json 事件数 = {len(sounds_json)} (= {total} 个 ogg)')
for inst, sub in LIBS:
    if inst in counts: print(f'  {inst:6s}: {counts[inst]} ogg')
print(f'打包 -> {RP_DST}  ({os.path.getsize(RP_DST)//1024} KB)  pack_format={RP_FORMAT}')
print('注: 若 MC 曾因格式不兼容把本包从 options 移除 -> 游戏内 选项→资源包 重新启用 qzpno_mv 即可(无需重启)。')
