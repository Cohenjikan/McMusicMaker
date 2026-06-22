# -*- coding: utf-8 -*-
"""Stage D deploy — 把 qzgtr 资源包(zip)+数据包(folder)装进 Modrinth 实例,并安全启用资源包。
匹配既有模式:resourcepacks/*.zip + options.txt "file/<ns>_mv.zip";datapack 以 FOLDER 进世界。
Run: <venv-demucs python> 05_deploy.py
"""
import os, sys, json, zipfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = r'C:\Minecraft\ModrinthApp\profiles\Fabric 1.21.8'
WORLD = '新的世界'
NS = sys.argv[1] if len(sys.argv) > 1 else 'qzpno'   # 默认当前曲(qzpno),避免误装旧 qzgtr
RP_SRC = os.path.join(HERE, 'build', f'{NS}_mv')
DP_SRC = os.path.join(HERE, 'build', f'{NS}_redstone')
assert os.path.isdir(RP_SRC) and os.path.isdir(DP_SRC), 'run 03_build_pack.py first'

# 1) resource pack -> zip into profile/resourcepacks (contents at zip ROOT)
rp_zip = os.path.join(PROFILE, 'resourcepacks', f'{NS}_mv.zip')
try:
    with zipfile.ZipFile(rp_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        for dp, _, fns in os.walk(RP_SRC):
            for fn in fns:
                full = os.path.join(dp, fn)
                z.write(full, os.path.relpath(full, RP_SRC))
    print(f'[1] RP  -> {rp_zip}  ({os.path.getsize(rp_zip)//1024} KB)')
except PermissionError:
    raise SystemExit('[1] RP zip 写入被拒(Minecraft 可能正开着锁住了资源包)。请先完全退出 MC 再跑本脚本。')

# 2) datapack -> FOLDER into the world's datapacks
dp_dst = os.path.join(PROFILE, 'saves', WORLD, 'datapacks', f'{NS}_redstone')
if os.path.isdir(dp_dst):
    shutil.rmtree(dp_dst)
shutil.copytree(DP_SRC, dp_dst)
print(f'[2] DP  -> {dp_dst}')

# 3) enable RP in options.txt (backup first; preserve newline style; keep existing packs)
opt = os.path.join(PROFILE, 'options.txt')
raw = open(opt, 'r', encoding='utf-8').read()
shutil.copyfile(opt, opt + '.qzgtrbak')
nl = '\r\n' if '\r\n' in raw else '\n'
entry = f'file/{NS}_mv.zip'
lines = raw.split(nl)
changed = False
for i, l in enumerate(lines):
    if l.startswith('resourcePacks:'):
        arr = json.loads(l[len('resourcePacks:'):])
        if entry not in arr:
            arr.append(entry); changed = True
        lines[i] = 'resourcePacks:' + json.dumps(arr)
if changed:
    open(opt, 'w', encoding='utf-8', newline='').write(nl.join(lines))
    print(f'[3] options.txt: 已追加 "{entry}"(备份 options.txt.qzgtrbak)')
else:
    print(f'[3] options.txt: "{entry}" 已在列表中,未改动')

print(f'\nDONE(部署 namespace = {NS})。重启 MC -> 进《新的世界》-> /reload -> '
      f'/tick rate 18.1 -> /function {NS}:setup -> 等 built -> /function {NS}:play')
