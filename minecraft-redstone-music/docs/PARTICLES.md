# 粒子 / 命令方块 轨道 (Task 6)

把粒子/烟花/任意命令同步绑定到红石音乐的播放时间与世界坐标。两件套:一个浏览器**创作端**(打关键帧、编命令方块)+ 一个 Python **生成端**(出数据包,按游戏刻精确触发)。

## 端到端流程

```
1) 先生成机器: python build_machine.py --form swave --ns <NS> --origin X Z Y --mc-version 1.21.8
     → 除数据包外, 还在 build/ 旁生成 <NS>_coords.json
       = 每个音符的真实世界坐标(单一真相, 直接取自生成器几何)
2) 打开 designer/particle_editor.html
     · 载入与机器同一首 MIDI
     · 🎯 导入机器坐标 = 上一步的 <NS>_coords.json
         → 对位光标精确贴合真实音符, swave/straight/custom 也准
         (旧的"导入布局 JSON"只是快速预览; swave 上光标会偏 1~3 格 → 以机器坐标为准)
     · ▶ 播放, 在想加效果的时刻打关键帧(光标显示该音符的真实坐标)
     · 每帧加命令方块: 相对脉冲(跟随音乐)或绝对坐标 / 命令
         ⚠ 相对模式命令体请用 `~ ~ ~`(让它跟随光标); 别在命令里写死绝对坐标, 否则偏移失效
     · 批量: ⧉+Δ 复制(1 1 1→2 2 2)、铺到后续N帧、复制到所有帧
     · 导出 particle_keyframes JSON
3) python scripts/build_particles.py --keyframes <导出.json> --ns <NS> [--music-ns <音乐NS>]
4) 游戏内: /reload → /tick rate 80 → 触发(见下)
```
> **原地 inplace:** 调色板在原地反复触发, 没有移动的脉冲 → 光标=静态 origin, 无需机器坐标文件,
> 编辑器对 inplace 天然正确。机器坐标文件仅用于 swave/straight/custom 这类**走线**形态。

## 生成器 build_particles.py

```
python scripts/build_particles.py
       --keyframes song_particles.json     # particle_editor 导出
       --ns qlxfx                           # 数据包命名空间
       [--music-ns qlxm]                    # 音乐机器 NS → 自动跟随其 [播放] 触发
       [--offset-gt 0]                      # 整体游戏刻偏移(粒子领先/滞后时校准)
       [--mc-version 1.21.8]                # 版本表驱动 pack_format/牌子 NBT; 默认 1.21.8(实测锚点)
                                            #   支持自动带 1.21..1.21.9; 1.20.3-1.20.6/未知版本拒建(assert_build_supported)
       [--console-origin X Y Z]             # 控制台牌子位置(默认布局 origin, Z-6)
       [--world-dir <world>/datapacks]      # 给了才部署; 默认只写 build/
```

### 触发方式
- **`--music-ns` 自动同步(推荐):** 数据包每刻监视音乐机器的 `PLAY` 记分板;音乐一按 `[播放]`(PLAY 0→1)粒子轨道**自动同刻开火**,停止同理。无需第二次手动触发,天然同步。
- **手动:** 不给 `--music-ns` 时,`/function <NS>:setup` 摆出 `[粒子播放]`/`[停止]` 牌子,在歌曲开始时按下。

## 时序模型

`/tick rate 80` 下 1 音乐 cell = 2 游戏刻 = 0.025s。编辑器按同一 `U=2/80` 量化,故关键帧 `t_sec` 与脉冲位置对齐:**触发延迟 = music_tick × 2 游戏刻**(= `round(t_sec × tps)`),相对开火时刻调度。若实测粒子整体领先/滞后,用 `--offset-gt` 加一个常量偏移即可(与旋律截断同一套校准思路)。

## 实现要点(为何如此)
- **用 `schedule function` 而非物理命令方块计时:** 物理命令方块要红石时钟 + 每刻选择逻辑、脆弱;调度函数是精确、稳健的等价物 —— 每个关键帧 = `schedule function <NS>:k/<id> <Δt>t`,落在各自游戏刻。编辑器里的"命令方块"(类型/坐标/命令)1:1 映射为一条调度命令(`type` 透传,v1 各触发一次;要循环就多打关键帧)。
- **PF 守卫:** `fire` 置 `PF=1` 并调度全部;每个 `k/<id>` 用 `execute if score PF <NS> matches 1 run …` 包裹;`stop` 置 `PF=0` 并 `schedule clear` 全部 → 可干净停止/重播。
- **坐标(单一真相):** 走线形态的对位光标**直接取自生成器导出的 `<NS>_coords.json`**(每个触发格 track-0 旋律音符盒的真实世界坐标),编辑器不再自己重算走线(早期 JS 重算与生成器漂移过, swave 上偏 1~3 格)。编辑器导出的 `pos` 已是绝对世界坐标(相对块按该帧真实 playhead 解析),生成器直接 `execute positioned X Y Z run <命令>`。注意 `positioned` 只设锚点:命令体写死绝对坐标会忽略锚点,故相对块用 `~ ~ ~`。
- **鲁棒性复用 redpiano_core:** pack_format/文件夹/牌子 NBT 方言均来自版本表 `get_version_profile`(不硬编码),并经 `assert_build_supported()` 把关 —— 1.20.3-1.20.6/未知版本硬失败,1.21.9 经 min/max pack.mcmeta 支持(详见 [CONTRACT](CONTRACT.md));中文 tellraw/牌子写 UTF-8(1.21.5+ 的控制台牌子改用 SNBT compound NBT 方言,避免旧引号形式被当字面量渲染);默认 `--no world-dir` 不部署。

## 导出 schema(particle_keyframes v1)
```jsonc
{ "schema_version":1, "kind":"particle_keyframes", "song":"...", "tps":80,
  "linked_layout":{ "form","OX","OY","OZ","XRUN","ZMAX","cells" },
  "keyframes":[ { "id","t_sec","music_tick","cell","playhead":[x,y,z],
    "blocks":[ { "id","type","mode":"rel|abs","offset":[dx,dy,dz],"pos":[x,y,z],
                 "command","resolved" } ] } ] }
```

## 状态
- ✅ 创作端 `particle_editor.html` + 生成端 `build_particles.py`:浏览器/命令行均已实测(关键帧坐标、调度延迟 music_tick×2、PF 守卫、自动同步 tick、版本表、UTF-8 全部验证)。
- ✅ **走线形态定位已修(2026-06-27):** 改用生成器导出的 `<NS>_coords.json` 作单一真相,swave 对位光标与真实音符**逐格一致(浏览器实测 32/32, 0 误差)**;根除了"JS 重算与 Python 生成器漂移"。
- ⏳ **待游戏实听:** 在真实机器上确认粒子与音乐同刻(必要时调 `--offset-gt`)。
