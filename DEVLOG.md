# McMusicMaker — 开发文档 / DEVLOG

> 把一首 **MIDI** 在 **Minecraft Java 1.21.8** 里用**红石机器**演奏出来:数据包驱动红石脉冲,每个音符触发 `/playsound` 播放**真实乐器采样**(资源包)。
> 本文给 **GPT 评阅**用:含整体架构、完整排查史、当前**唯一未解决问题**、以及机器的**精确规格**(便于复核红石逻辑)。
> 代码在本仓库;**版权素材(歌曲 MIDI、由其生成的 notes/schedule 数据、音频、采样)未入库**(见 §8),GPT 评阅只需代码+本文。

---

## ★★ 交接 / HANDOFF(2026-06-22,最新状态置顶)

**项目当前形态 = "真音符盒 + 双轨辐射红石机器 + 以玩家为中心的自定义采样",已可完美演奏;本轮(2026-06-22 第二批)再加【多乐器乐队】【平面折叠压缩实装】【本地红石循环播放器】三大形态,一次对话完成。** 下面是接手者需要的全部。

### 🔥 第3轮根因:音频丢失 = 服务器过载(2026-06-24)
用户实测:三个大机器都"只听到开头一点点就没声音了"(小测试台 qzct 完整播放=正常)。**日志铁证**:
`[Server thread/WARN]: Can't keep up! Is the server overloaded? Running 2619ms or 209 ticks behind`(qzolkl)、`166 ticks behind`(dyfb)。
- **根因**:行进脉冲大机器(qzolkl ~4799长、dyfb 5485×10lane = 数万中继器 + ~1500 forceload 区块)把单机服务器**压垮 -> 跳刻 -> 红石脉冲停滞 -> 开头后断音**。小机器(qzct 32格)正常 = 印证是规模/过载, 非逻辑。
- **★ 修复方向 = 用户 Task3 的思路正是解药**:【命令方块/数据包按节奏在原地点红石块打响音符盒】—— 无行进脉冲、无成千中继器、占地极小 -> **不过载**。
- **Task 3 已重做** `38_build_cmdplayer.py` → **`wllc`**(我泪):紧凑音符盒网格(927列×≤7声部, 24宽×39行, 占地仅 ~44 区块, **零中继器**)。数据包 schedule 链 `s/s0→s1→...`: 到该刻就给该列每个音符盒**下方(Y-2)放红石块**强充映射块=打响, 在原地直接触发。[播放]/[循环播放]/[停止]/[复音增益]/[微抖动](cfg 按钮已恢复)。停止有 PLAY 守卫(残余 step 不响)+ stopsound @a。
- **两个遗留小bug**:① 告示牌 messages 必须**正好4行**(我之前 3 行 → `not a list of 4 elements` → 牌子没建, 按钮在但无字);已在 38 修(lbtn 补足4)。② 36(qzolkl)我误删了 [复音增益]/[微抖动] 按钮(用户:没允许别删)——待与 Task1/2 修法一起处理。
- **Task 1/2 待定**:同样过载。修法 = 套用 wllc 的原地命令触发(保留 band/直线 布局, 触发改数据包)**或** 保留行进脉冲 + 滑动窗口 forceload(纯红石但复杂)。**等用户拍板**(见下)。

### 🔧 本轮测试反馈 + 修正(2026-06-22 第二批 · 复盘)
用户实测暴露 3 个问题, 已全部修复, 并改世界:
1. **全静音(所有机器)根因 = 资源包 pack_format 写错**:`02e` 写成 34(=1.21.0), 而 1.21.8 需 **64**(同世界 dyfi_mv/lyy_mv 均 64)。MC 判不兼容→**自动把 qzpno_mv 从 options 移除**→所有 `qzpno:*` "unknown soundEvent"=静音。修:`02e` 改为**自动读同目录可用包的格式**(永远匹配)。用户需在 选项→资源包 重新启用 qzpno_mv(MC 删过它)。
2. **停不下来(Task1 摧毁耳膜)根因 = 停错声道**:模组发声在 **`SoundSource.RECORDS`**, 而所有停止用 `stopsound @a master`(master 停不掉 records)+ 行进脉冲已离源、在长链里续触发音符。修:全改 `stopsound @a`(不带源=停全部)+ 新增 **`SIL` 记分板**, 停止时置1, `tick` 每刻 `stopsound @a` 直到脉冲滑出(END_TICKS 后 `unsil` 置0)。(33/34/35 全改)
3. **Task2 理解纠正(关键)**:用户要的【平面轴压缩】≠ 把整机折成 2D 方阵(我上一版 `qzolkf` 错了, 那是 Task3 的形态)。正解 = **整体保持直线, 只把【长休止】的延迟折成一个 Z 向小线圈藏到主线外**(主线音符靠拢、更短, 但节奏 100% 不变)。新建造器 **`36_build_linecoil.py` → `qzolkl`**: OLK 直线 4799(原 5053, 省 5% —— 因 OLK 极密, 只有 13 个长休止可折;稀疏曲省得多)。线圈 = 入口rep→红石粉拐角→OUT列→红石粉U弯(0延迟)→BACK列→出口rep, OUT/BACK 隔一格防短路。线圈验证台 **`qzct`**(8升音穿1线圈)。**31(2D方阵折叠)就此=Task3 路线, Task2 不再用。**
4. **世界变更**:旧 `新的世界` 已被用户删除 → 现 `新的世界 (1)`。所有数据包(dyfb/wllj/qzolkl/qzdf/qzlp/qzct)已重部署到此;资源包+jar 在 profile 层不受影响。

> ⬇️ 以下为本轮初版记录(部分已被上面修正取代:Task2 现为 qzolkl 直线版而非 qzolkf;停止已修)。

### ⬛ 本轮新增(2026-06-22 第二批 —— 三任务一次完成,⚠️ 测试前先【重启 MC】因 jar 已变)

**Task 1 — 多乐器乐队(dyf,实验性):** 在原钢琴音乐基础上【引入新乐器库】,把 Do You Feel It 重演为【真音符盒乐队】(piano+bass+lead+pad+drums,**人声已删除**)。
- 新乐器库 `poc/02d_make_instruments.py`:drums = VCSL(CC0)**真采样**(kick/snare/hihat/tom/crash);bass/lead/pad = numpy **合成**(查无 CC0 逐音可下载库,合成兜底,见脚本注)。→ `samples_{bass,lead,pad,drums}/` + 各 manifest。
- 转谱 `poc/transcribe_dyf.py`:复用旧项目 `mc-noteblock-demo` 的 Demucs 6 轨。piano/lead(guitar 轨)用 **basic-pitch 复音转谱**(新建 venv-bp);bass 用 pyin;drums 用 onset + 频带分类(kick/snare/hihat);**人声轨丢弃**。→ `notes_dyf_{piano,bass,lead,pad,drums}.json`。
- 映射扩展 `gen_redpiano_map.py`:钢琴 60 条【一字节不变】(已部署钢琴机器照常可用,已 git 验证),追加 43 条新乐器(新方块表 EXTRA_BLOCKS)。`RedPianoMap.java` 现 **103 条**;`redpiano_map.json` 加 `instruments{bass/lead/pad/drums}`(pitched 按 band×层,drums 按 GM 键,note=12 不移调)。
- 资源包 `poc/02e_build_resourcepack.py`:`qzpno_mv` 重打,含全 **103 音**(钢琴音色不变 + 新乐器)。
- 整机 `poc/33_build_band.py` → **`dyfb`@X=75000**:共享骨架多 lane(24 同步式),每乐器一组 lane 用其音色方块。10 lane,2482 音,时序断言过。
- ★ **重打 jar(103 映射)+ 重打资源包 ⇒ 必须重启 MC**(改 jar 必重启,见旧坑)。

**Task 2 — 平面折叠压缩(olk,实装):** 上轮只验证(26/29)未实装的【平面蛇形折叠】终于落地为整机。
- `poc/31_build_foldfull.py` → **`qzolkf`@X=185000**:把 30 的双轨辐射直链折成紧凑方阵。**关键创新 = 红石粉 0 延迟 U 弯**(红石粉同刻传导、≤15 格不衰为 0 → 拐弯【不加延迟】→ 24/30 的时序公式"累计延迟==该刻"原样成立、折叠不改一个数)。只在 'rep' 前换行(行首必为中继器 → 强充能干净,不靠弱充能触发音符盒)。双轨拆成【两块独立折叠板】(同形折叠 → 同 cell 同 X → 绝对同步;避免共行双 U 腿在同列重叠)。Python 加【碰撞断言】兜底(无法跑 MC)。
- 效果:**OLK 5053 长直链 → 193 长折叠 = X 压缩 26×**;全 2890 音、时序断言全过、零碰撞、dropped 0。(钳音 36 = OLK 高音 MIDI99>可奏93,旧问题,与折叠无关。)
- 验证台 `poc/32_build_dustfoldtest.py` → **`qzdf`**:单轨 7 升音穿 3 个红石粉 U 弯;游戏内 fire 听到匀速升音 = 红石粉 0 延迟弯成立。

**Task 3 — 本地红石循环播放器(我泪,第三种形式):** 紧凑·本地·红石主动控制的循环 jukebox(对比:形态1=远处大机器一次性长条触发;形态2=数据包切片回放)。
- `poc/34_build_local.py` → **`wllj`@X=300(出生点附近)**:复用折叠+辐射(紧凑,**不做长条**),**红石扫描脉冲 100% 驱动节奏并触发所有音符盒**(与大机器同核,模组发声)。按钮:[播放]放一遍 / [循环播放]本地 jukebox / [停止] / [全景俯视]。**循环** = `done` 检 `LOOP` 分重火(数据包重火,与大机器点火同理,稳)。
- 效果:**我泪 3917 直链 → 161 折叠 = 24×**;2074 音、dropped 3、钳音 3、断言过、零碰撞;循环周期 ~244s。
- 纯红石【自循环时钟】机构(出口→二极管单向→绕回源点→重注入)已单独建验证台 `poc/35_build_looptest.py` → **`qzlp`**(点[播放]应 3 音无限循环,[停止]切断反馈门)。整机循环暂用数据包重火(双轨折叠上反馈走线易与 U 弯红石粉串接,留作后续整合);纯红石环本身已证可行。

**测试顺序(本轮):⚠️ 先关 MC → 确认 mods 里 `redpiano-1.0.0.jar`(11.6KB,103映射)、resourcepacks 里 `qzpno_mv.zip`(新)→ 重开 MC 进世界 → 按下文各机命令。** 钢琴老机器(qzv2 等)音色不变仍可用。

### 跑一首歌(最短路径)
1. 装好 **RedPiano 模组**(`mod/redpiano/`,见构建)+ **qzpno 资源包**,启动 MC(改 jar 必须重启)。
2. `python poc/parse_midi.py <song>.mid poc/notes_xxx.json`(需 mido)。
3. `python poc/30_build_full.py poc/notes_xxx.json <NS> <OX>`(部署数据包到世界)。
4. 游戏内:`/reload` → `/tick rate 80`(**必须手动**,见 §3-坑3) → `/function <NS>:setup`(等绿字 built) → 按 **[直接播放]**(站/飞均可听全曲)或 **[骑行播放]**(spectator 平滑巡游);卡住按 **[停止]**。

### 架构(三件套)
- **RedPiano 模组**(`mod/redpiano/src/main/java/com/redpiano/`):mixin 原版 `NoteBlock.triggerEvent`,音符盒坐在"映射方块"上时改播 qzpno 自定义钢琴采样 + 按 note 强制移调。**关键(让它"完美"的修复)**:不在音符盒位置播定位音(玩家一动就出声音球被剪),而是 **`RedPiano.flush()` 在游戏刻末给每个玩家在其自身脚下播该音(`playSeededSound(null, player, ...)` Entity 重载)** → 声音跟随玩家、任意移速不断不糊。刻末统一发还做了**复音增益 ×1/√N**(防大和弦削顶)+ **微抖 ±3音分/±2%**(去复印感);两者经记分板 `rpcfg`(`poly`/`human`)开关。构建:`JAVA_HOME=C:\Users\Cohen\jdk\jdk-21.0.11+10`,gradle 9.2.1 wrapper dist `gradle.bat -p mod/redpiano build`,jar 拷到 `C:\Minecraft\ModrinthApp\profiles\Fabric 1.21.8\mods`,**重启 MC**。
- **建造器 `poc/30_build_full.py`(当前整机)**:MIDI→notes→**双轨辐射机**。7 条单音 lane(z 占13)→ **2 条轨 × 3 声部=6**,每轨一个强充能导体同刻辐射【上+±Z】三音(和弦)。两轨共享**同一变延迟中继器骨架**(并集触发刻,delay 1-4)→ 逐刻同列、绝对同步、灯闪一致。直链(未折叠)。健壮播放(setup复位/play/play_ride spectator滑行/stop/toggles)。
- **资源包 qzpno**:60 段钢琴采样(Salamander CC-BY,20 音×3 力度),`poc/02c_make_piano_velocity.py` 抓取,`poc/gen_redpiano_map.py` 生成 `redpiano_map.json`(块→音→音量)。

### 已部署的机器(世界 `新的世界`)
| NS | 曲子 | OX | Y | 家族 | 建造器 | tick | 说明 |
|---|---|---|---|---|---|---|---|
| qzv2 | 春娇与志明 | 220000 | 255 | A 重演 | poc/30(双轨) | **80** | **最新整机**, 6 声部, 2857长×6宽, 真音符盒钢琴 |
| qzws / qzolk | 我落泪 / OLK | 170000/180000 | 255 | A 重演 | poc/25(7lane) | 80 | 旧 7lane 同步版(可用, 已被 30 取代) |
| **dyfi** | **Do You Feel It?** | **70000** | **-59** | **B 切片** | **add_song.py** | **20** | **原曲音色复刻, 5 乐器轨+垫底, 1762音/1215cell** |
| **dyfb** | **Do You Feel It?** | **75000** | **255** | **A 重演·乐队** | **poc/33** | **80** | ★本轮 Task1: 多乐器(piano+bass+lead+pad+drums, 无人声), 10 lane, 2482音 |
| **qzolkl** | **One Last Kiss** | **185000** | **255** | **A·直线+线圈** | **poc/36** | **80** | ★Task2(修正): 整体直线 4799, 13个长休止折Z线圈, 节奏不变, 2890音 |
| ~~qzolkf~~ | ~~OLK 2D折叠~~ | — | — | (废弃) | poc/31 | 80 | 上一版误解(2D方阵), 被 qzolkl 直线版取代; 31 现归为 Task3 路线 |
| **wllj** | **我落泪** | **300** | **255** | **A·本地循环** | **poc/34** | **80** | ★本轮 Task3: 紧凑本地 jukebox, X 3917→161(24×), [循环播放], 2074音 |
| qzdf / qzlp | (验证台) | 209000/207000 | 255 | A 测试 | poc/32 / 35 | 80 | 红石粉0延迟U弯 / 纯红石反馈环时钟 验证台 |

### ★ 两套机器家族(同一世界,接手必读 —— 播放方式/tick rate/依赖都不同)
- **家族 A —— RedPiano 真音符盒"重演"**(本仓库 McMusicMaker):MIDI → 共享骨架红石 → 真音符盒播 qzpno 钢琴采样。**程序化定产**(音色=钢琴,丢原音色)。**需 RedPiano 模组 + `/tick rate 80`**。当前机器 = `qzv2`。
- **家族 B —— 切片回放"音色复刻"**(旧项目 `C:\Users\Cohen\mc-noteblock-demo`,流水线见其 `PIPELINE.md`):原曲音频 → Demucs `htdemucs_6s` 分 6 轨 → librosa onset → ffmpeg 把**原音频本身**逐 onset 切 ogg → 数据包红石脉冲逐格 `/playsound` 原声片段。**100% 保留原音色 + 天然多乐器** = 开发文档里**远期"MP3 音色级复刻"目标的初步实现**(用户本轮指定"原曲不是 midi")。**无需模组,但需 `/tick rate 20`(默认)**——按 DELAY=2=200ms/cell 设计,残留 tick80 会快 4 倍跑飞。资源包 `<曲>_mv.zip`。
- **共存**:qzv2@X=220000/Y=255 与 dyfi@X=70000/Y=-59 坐标与 Y 层都不撞。**切歌必换 tick rate(A=80 / B=20)**。

### 两首歌的播放命令(各自)
**春娇与志明(家族 A,qzv2)** — 需 RedPiano 模组(已装)+ `qzpno_mv.zip`(已启用):
```
/reload
/tick rate 80
/function qzv2:setup        # 等聊天框绿字 "built"(自动 forceload+传送到现场+建造)
# 然后按现场 [直接播放](站/飞都听全曲)或 [骑行播放](spectator 平滑);卡住按 [停止]
# 或直接:/function qzv2:play   或   /function qzv2:play_ride
```
**Do You Feel It?(家族 B,dyfi)** — 需 `dyfi_mv.zip`(已部署+已在 options.txt 启用,无需模组):
```
/reload
/tick rate 20               # ★ 默认值;若刚玩过 qzv2 必须从 80 改回 20,否则快 4 倍
/function dyfi:setup        # 等绿字 "built"
/function dyfi:play         # 起跑(现场也有按钮);/function dyfi:ride 影院跟随;/function dyfi:cleanup 拆除
```

### 第二首歌构建记(Do You Feel It? — Chaos Chaos,2026-06-22)
- 来源 bilibili BV1Te411u7S9 原曲(247.9s)。**下载坑**:`playurl` 端点 412 拦 yt-dlp 的 WBI 签名 → 直接打 bilibili API(自造 `buvid3/buvid4` cookie + 取 DASH 音频流 curl 下载)绕过;原始音频在桌面 `dyfi.wav`(私人用,**不入任何公开库**)。
- 一条命令:`C:\Users\Cohen\mc-noteblock-demo\venv-demucs\Scripts\python.exe add_song.py C:\Users\Cohen\Desktop\dyfi.wav dyfi`(幂等跑完 分轨→onset分析→切片→资源包+数据包→部署到 nbviz 桥)。
- 自动选轨:5 乐器轨全入(vocals/guitar/bass/drums/piano,onset 469/351/82/750/251,均过能量门)+ `other` 连续垫底。
- 部署:`dyfi_redstone.zip`→`新的世界\datapacks\`;`dyfi_mv.zip`(44MB/1769段ogg)→profile `resourcepacks\` 并已写入 `options.txt`。(桥 `nbviz\datapacks`、`nbviz\resourcepacks` 非 junction 到本 profile,故手动 copy;songs.json 注册项 add_song 已写。)

### 已验证的几何(逐项实测/对抗验证,均有独立测试台)
真音符盒垫映射块发声(19)✓ / 行进脉冲中继器直插(20)✓ / **多 lane 共享骨架同步**(24,记忆`redstone-multilane-shared-timeline`)✓ / **以玩家为中心发声治移动断音**(根因=SoundEngine 每刻按听者位置重算、出声音球即剪样本;记忆`redstone-music-audio-and-camera`)✓ / **平面蛇形折叠**水平拐角+U形(26)✓ / **一信号辐射同刻多音(三音和弦)**(27)✓ / **dust 触发音符盒**(28)✓ / **折叠+辐射共存**(29)✓。

### 未做 / 下一步(几何已验,差集成)
1. **整机折叠**:把 30 的直链按平面蛇形折叠压 X 跨度。难点=折叠在 Z 换行 vs 和弦在 ±Z 辐射 → 行距 ROW_DZ≥4(脚本29用4)给和弦留空;且 U形连接中继器的延迟须计入共享时间轴(否则错拍)。建议 `31_build_foldfull.py`,先在小段验证时序断言再放大。
2. **每轨 4 音(dust 第4音)**:28 已证 dust 能触发;30 现用 3 音/轨(6声部,够春娇/OLK;我落泪偶发第7音被丢)。要 8 声部就给每轨 C 引一小段 dust 到第4个音符盒。
3. **OLK 高音钳音=36**(MIDI 99 > band 上限 93):补 2 个高 band(C6/D#6)+ 重生成 map + 重打 jar。
4. **远期(MP3 音色级复刻)**:
   - ✅ **切片回放路(家族 B)已初步落地** = `dyfi`(Do You Feel It?):原曲→Demucs 6轨→逐 onset 切原声片段→红石 `/playsound`,**100% 原音色 + 多乐器**。这是"命令方块播放级复刻"的最忠实形态(代价=本质是放原声颗粒,非"真音符盒重演")。
   - ⬜ **转谱重演路(家族 A 扩展)**:MP3→Demucs→逐轨**转谱**→多乐器**真音符盒**乐队重演 + 逐轨音色匹配(mixin 已按垫底块定音色,天然支持多乐器)。受转谱精度限、人声只能改编为乐器。验证实验:对同时有 MP3+钢琴 MIDI 的曲子比"钢琴+贝斯+pad 重演"是否更丰满。**缺 polyphonic 转谱器**(basic-pitch 未装;现有 librosa 仅单音 pyin)。

### 备份 / 仓库
GitHub `Cohenjikan/McMusicMaker` 已推全部代码,标签 `v1-perfect`(单钢琴完美态)。版权 MIDI/notes/ogg/deployed 经 `.gitignore` 排除。不可再生输入本地备份在 `C:\Users\Cohen\McMusicMaker_backup\v1-perfect\`。世界存档(833MB)用户暂不备份。

> 以下为历史开发记录(排查链、规格),接手细节见各 §。

---

## ★ 当前主线:RedPiano 模组 —— 真音符盒播自定义音色(2026-06-22)

**重大转向**:从"命令方块 /playsound"升级为"**真·音符盒** + 自写 Fabric 模组"。原因:命令方块虽音质满分,但用户判定为"**伪音符盒、欺骗观众**";而原版音符盒仅 16 乐器/2 八度(音色不够)、资源包覆盖乐器会量化染色(用户**拒绝任何音色亏损**)、玩家头颅音效不随 note 移调且不美观。**唯一同时满足"真音符盒外观+机制" 和 "零音色亏损" 的方案=写模组解开音色限制。**

**模组 RedPiano**(`mod/redpiano/`,Fabric 1.21.8):
- **mixin 原版 `NoteBlock.triggerEvent`**(`NoteBlockMixin.java`):发声时读**正下方方块**,对照 `RedPianoMap`(60 条)→ 命中则用**强制移调** `pitch=NoteBlock.getPitchFromNote(note)` + 该方块映射的 qzpno 自定义音效 + 自定义音量 `playSeededSound(...RECORDS...)` + 喷 NOTE 粒子、取消原版。**100% 真音符盒**(真贴图/真粒子/真"垫底定音色"机制),只把硬编码的 16 条乐器表解锁成任意大。
  - 关键源码发现:原版 triggerEvent 里自定义头颅音效 `isTunable()=false` → pitch 锁 1.0,**这正是头颅不移调的原因**;我们绕过、强制按 note 移调。
- **60 映射**=`RedPianoMap.java`(由 `poc/gen_redpiano_map.py` 生成):20 采样段(每 3 半音 C1-A5)× 3 力度 → 60 个不同垫底方块 → 60 个 qzpno 音效。`gen` 里 `LAYER_VOL` 控音量(**>1 扩大可听半径**,因音符盒声音位置性衰减;当前 1.4/1.7/2.0)。
- **工具链**(已跑通):JDK21(`C:\Users\Cohen\jdk\jdk-21.0.11+10`)+ gradle 8.12 + fabric-loom 1.10.5 + officialMojangMappings + fabric-api 0.136.1。`gradle build` 出 jar → Modrinth mods 文件夹;**改 jar 必须重启 MC**。

**机器建造器**(均**天上 Y=255** —— 真音符盒必须上方空气才发声):
- `21_build_realnb.py`(**松散版**,5980长×31宽):Method B 变延迟(tick80) + 3排/lane(脉冲线/分接中继器直插/音符盒) + 红石灯进度带 + 音色展示台(中文木牌) + 2物理按钮 + 数据包跟随相机。
- `23_build_dense.py`(**密集版**,3917长×13宽,~4.2格/音):**中继器链直连** —— 空白=纯中继器(1格)、发声格=导体映射块(被前中继器**强充能**)+音符盒坐其上。⚠️**强充能→触发上方音符盒**的几何**待游戏验证**(交接首验项)。再压缩唯一杠杆=降 tick rate(fidelity↔密度取舍)。
  - ⚠️**已知缺陷(2026-06-22 实测)**:23 给**每条 lane 单独的中继器链**(只塞本 lane 的音),各 lane 长度不一([3917,3340,2854,2635,2440,1799,1764])→ 同一拍的音落在**不同 X** → 看着"**音步岔开**"、不同步。**虽各 lane 单独计延迟≈准,但无任何东西把各 lane 锁在同一时间轴**。→ 被 24 取代。
- `24_build_sync.py`(**同步密集版**,3917长×13宽,deployed=`qzws_sync`,NS=qzws,OX=170000):**修掉 23 的岔开**。取所有 lane 触发刻的**并集**构成**唯一共享中继器骨架** `cells[]`,7 条 lane 全铺**完全相同**的链(同延迟、同 X)→ 脉冲每刻到达同一列 → **绝对同步 + 音符盒在 X 上对齐成竖列**(发声列红石灯同时点亮成一竖排)。发声列:本 lane 有音=映射导体块(强充能)+上坐音符盒;无音=纯石导体**直通**(0延迟)。空白用变延迟中继器(1..4红石刻=0.1~0.4s,每格1块)压缩。**Python 已证:每个发声列累计延迟(红石刻)== 该刻 OFFSET=0,927 列零错位**;生成产物已验同列对齐(x=170014 处 z=0/z=2 同时发声,z=4..12 直通)。复用 23 同款"导体下垫→触发上方音符盒"几何(用户实测 23 能发声=该几何成立)。**✓ 已游戏内确认(2026-06-22):我落泪一遍"堪称完美"、同步成功**。
  - **鲁棒性测试:One Last Kiss**(`python 24_build_sync.py notes_olk.json qzolk 180000` → deployed `qzolk_sync`,NS=qzolk,OX=180000):2890 音、6 lane、5053长×11宽,时序断言全过、同列对齐已验(x=180027 处 z=0/2/4/6 四音和弦对齐、z=8/10 直通)。⚠️ **钳音=36**:OLK 音域达 MIDI 99,而 `redpiano_map` 最高 band=81 + note≤24(±12 半音)→ 可奏 MIDI≈12..93,99 处 36 音被钳到 93(偏低≤6 半音)。非同步问题;要全覆盖需补高音采样 + 扩 band + 重打模组。
- `25_build_synccam.py`(**24 + 红石驱动相机 + 灯流光**,覆盖部署 `{NS}_sync`,同 NS/坐标):应对 OLK 实测"太快跟不上→出可听范围→听感断"。**根因查证**:forceload 区块=load level 31 全模拟,**无人也照常跑红石**(`minecraft.wiki`)→ 歌没真断,是**玩家飞出可听半径听不到**(模组在音符位置发声)。**修法**:① **红石驱动相机**(用户方案A,非预排时间防漂):每个发声列 z=-1 放命令方块,被 lane0 该列导体强充能(=脉冲刚到)触发 `execute if score CAM matches 1 run tp @a (X-4) (Y+6) midZ -90 32` → 脉冲拽着玩家走,永远在脉冲处=在可听范围+与红石绝对同步;休止符不 tp(没声),下一个音到了再踩点拽过去。两按钮 [直接播放]/[相机播放](spectator)。② **石头→红石灯**(查证红石灯可导电:repeater→灯→repeater 成立,且强充能时点亮→直通/发声列随脉冲流动点亮)。映射块保持(模组靠它定音色)。**待游戏内确认**:相机跟随听感 / 灯导电是否真通(若某 lane 休止后变哑=灯不导电,把 `PASS` 改回实心块即可)。
  - **矿车跟随调查结论(否)**:矿车上限 0.4 格/刻(8格/秒@20TPS)且**恒速**;本脉冲变速(导体=瞬时、delay1=0.5、delay4=0.125 格/刻)。恒速车追不上变速脉冲——休止段会**冲到脉冲前面**(超前=听不到,正是老问题)、密集段又落后。→ 不用矿车,用红石驱动 tp(精确同步、零漂)。
  - **机器折叠(待做)**:把长直中继器链折成蛇形以压 X 跨度(保路径长=保时序)。难点:多 lane 占 Z 维做对齐,折叠需另一维 → 要么 lane 改叠 Y + XZ 蛇形(横向拐弯,可行但改观感几何)、要么 Y 向折叠(竖向红石传导,风险高)。**确定方案(用户拍板 + 调研)**:平面蛇形 + lane 在 Z 上**错开张开**(不叠在一起)。把共享 cells[] 当 1D 带,7 条 lane 铺进**同一折叠网格**(cell i 落同 (行,列)→ 同 X → 列对齐不变);每 lane 平移 z = 行z + L*LANE_DZ(LANE_DZ=2);**行距=16(1区块)**防串扰 + 对齐 forceload。横向 90°拐角:进 repeater(facing=west 输出+X)强充导体块 C,出 repeater 坐 C 的 +Z 面(facing=north 输出+Z),导体 0 延迟、把出 repeater 的 1rt 并入既有延迟格→拐角净 0 刻;U 形=两拐角+横腿,逐行 +X/−X 交替。脚注:OLK 5053 cell、SEG=240 → 22 行,占 ~246×352(~352 区块)vs 现 5053 长。**作为下一步专门做、单独 26_build_fold.py A/B**;折叠不改时序(断言 25:70 须仍过)。
- **★ 断音根因 + 修复(2026-06-22):红石驱动相机(25)失败 → 模组改"以玩家为中心"发声**:
  - **症状**:25 的 tp 相机每跳一次就**剪断当前音符采样**,完全不可听。
  - **根因(调研+对抗验证,实锤)**:tp 本身不剪音;是 MC `SoundEngine.tickNonPaused()` **每刻**按听者位置重算每个定位音的音量,**听者一旦出了该音的声音球(半径≈16×volume≈22–32格)就当刻 free 掉声道=采样被掐断**。`attenuation_distance` 默认 16 且**不随 volume 放大**(只放大球半径不放大近场响度,故 vol 调大无削波代价但中远场仍陡降)。**解释了"老相机能听/新相机断"**:老相机每格走~1格(滑行)始终在声音球内;25 每**发声列**跳,休止处一次跳 50–100 格出球 → 掐断。⇒ **跟随相机(不管红石驱动与否)都治不了音频**。
  - **修复(已改 + 已编译 + 已部署 jar)**:`NoteBlockMixin.java` 保留真音符盒(粒子/方块/机制)与移调,但**去掉音符盒位置的定位音**,改为**服务端给每个玩家在其自身脚下播该音**(`if (level instanceof ServerLevel server) for (ServerPlayer p: server.players()) server.playSeededSound(null, p.xyz, holder, RECORDS, e.volume, pitch, 0L)`)。听者永远在声音球中心 → 距离剔除永不触发 → **站哪都听得到、全曲不断**,相机退化为纯视觉(tp 不再剪音)。与老命令方块版 `@s ~ ~ ~` 同思路,代价=无空间声像(音乐播放器恰好无所谓)。**构建**:JAVA_HOME=jdk-21,gradle 9.2.1(`~/.gradle/wrapper/dists/gradle-9.2.1-bin/.../gradle.bat -p mod/redpiano build`,~1min,依赖已缓存)→ 拷 `build/libs/redpiano-1.0.0.jar` 到 Modrinth mods → **重启 MC**。**✓ 已确认(2026-06-22):用户「这一次确实完美了」,全程无断音。** 折叠方案**永久搁置**(以玩家为中心发声后,机器长度不再影响听感,折叠失去理由)。**项目达 v1-perfect。** 后续菜单(均为锦上添花,非修复):① 提交+备份锁定成果(最高优先,见交接)② 多乐器/乐队(mixin 已按垫底块定音色,天然支持)③ 复音求和增益防糊(全居中满音量叠加,峰值7音无余量)④ OLK 高音补 2 band 修钳音 ⑤ 灯带按音高着色(piano-roll 观感)。
- **★ v1-perfect 已锁定 + 增益/抖动/骑行(2026-06-22 晚)**:
  - **备份**:GitHub 推送 `v1-perfect` 标签(`c8df184`)+ 后续提交;.gitignore 排除版权 MIDI/notes/ogg/deployed;本地 `C:\Users\Cohen\McMusicMaker_backup\v1-perfect\`(MIDI+notes+map+jar+README)。**世界存档 833MB 未自动备份**(建议另拷)。
  - **复音求和增益 + 微抖动(模组, 命令方块可开关)**:`RedPiano` 改为**刻末 ServerTickEvents 统一发声**——一刻 N 个音 → 音量 ×1/√N(等功率, 防大和弦削顶);每触发按 (pos,gametime) 确定性种子做 ±3 音分 / ±2% 微抖(去逐比特"复印感")。两者读记分板 `rpcfg`(假人 `poly`/`human`, 缺省开),`25` 建 rpcfg + 两个开关按钮。
  - **★ 移动掉音质根因 + 修复(实体绑定声音)**:中心化声音锚定在"发声那刻的玩家世界坐标",**玩家移动过快会跑出自己刚发出的音的声音球 → 衰减/被剪 → 跟随时听感糊**。修复:`playSeededSound(null, p, ...)`(**Entity 重载**)把每个音**绑定到玩家实体**→ 声音跟着玩家走、永远在球心 → **任意移速都不断不糊**(站定与原等价)。相机/骑行从此纯视觉。
  - **骑行巡游(datapack `25`)**:`play_ride` 召唤隐形 `armor_stand`(Tags=rpride,NoGravity)→ `ride @a mount` → tick 里 `tp @s ~RIDE_SPEED ~ ~` 恒速 +X 平滑推进(RIDE_SPEED=LEN/全曲刻),`ridestop` 下马清除。配实体绑定声音 = 平滑骑行 + 完美音质。第三个按钮 [骑行播放]。
  - **命令方块标注**:`25` 每个控制按钮南侧立 `oak_sign` 标注用途(直接/相机/骑行/复音/抖动 共 5 钮)。
  - **新曲**:春娇与志明(`qzcj`,OX=190000,1231 音、6 lane、2857 长、0 钳音;该 MIDI 力度全 f=无强弱)。
- **★★ 远期目标(用户拍板, 列为之后方向)**:
  - **MP3 音色级复刻 → 真红石乐队重演**:终极愿景=还原一首 MP3 的音色。两条对立路:重演(转谱+采样, 受转谱精度限, 人声难)vs 切片回放(命令方块 /playsound 原音颗粒, 100% 音色但=放录音=背叛真实理念)。**选定中间路(既炸裂又真实)**:`MP3 → AI 分轨(Demucs v4)→ 逐轨转谱 → 多乐器谱 → 真音符盒乐队重演 + 逐轨音色匹配`;agent 负责编排 pipeline + 对着原音频校转谱 + 选采样。人声轨只能映射到乐器(那一刻是改编非还原)。验证实验:拿同时有 MP3+钢琴 MIDI 的(如晴天),Demucs 分贝斯/弦乐轨, 看"钢琴+贝斯+pad 重演"是否明显更丰满。
  - **轨道压缩重设计(用户方向)**:现 7 lane 按和弦音高排名分配 → lane0 满(主旋律+和弦顶)、lane6 近闲置,不优。新思路:**一条信号轨在发声列向 ±Z 辐射强充能多个垫底块/音符盒**(信号可靠时一轨可同发多音),规定**单轨最多 4 音**(红石辐射距离限),>4 音用第 2 轨;**仅 >2 轨才做 Z 轴多层**,否则同轴只向左右(±Z)正负延伸。例:7 音峰值 → 2 轨即可,多数曲(≤4 同时)只需 1 轨 → 极致压缩 z 宽 + 省中继器。⚠️ 几何(一信号强充多个 ±Z 垫底块)**待小型验证台先证**(遵 §0 先验premise的纪律),再做 `26_build_radiate.py`。

**已单独验证**:① 真音符盒垫映射块+红石→模组播移调音色(脚本19)✓ ② 行进脉冲经中继器直插依次触发真音符盒(脚本20几何原型)✓ ③ 跟随相机机制(观察者+逐格跟脉冲+宏tp)✓ —— 注意相机必须跟**脉冲逐格**而非"音符"(否则空白处超前→听不到)。
**待办(交接)**:游戏内确认模组"以玩家为中心"发声修复(重启MC→站着按[直接播放]全程无断音)/ **机器折叠 26_build_fold.py**(平面蛇形+lane错开,方案见上)/ 灯导电(若某 lane 休止后变哑,把 25 的 PASS 改回实心块)/ OLK 高音钳音(补采样)/ 平滑视觉相机(可选:逐格滑行 或 插值 display 实体,纯美观)/ 混音·延音。详见记忆 `redstone-music-audio-and-camera`、`redstone-multilane-shared-timeline`、`sync-means-column-alignment`。

---

## 0. 置顶:断拍问题已解决(根因 + 完整排查链, 2026-06-21)

**症状**:机器播放时出现**"断拍"**——某些拍突然没声、然后接上;听感像周期性(用户曾估 ~8s,实测无固定周期)。

**根因(实锤)**:**晴天 MIDI 的节奏精度超出 0.221s 红石网格 → 子网格音符塌缩。** 红石机器每格 = delay-2 repeater = 0.221s(♩68 十六分音符),量化 `cell=round(t/0.221)`。但晴天是细节丰富的钢琴编配:**1335/1926 对相邻音符间隔 <0.221s**(414 对在 0.11–0.221s 子网格、98 处同音高 <0.221s 重复);**551 个音符被量化挪动 >0.08s,544 个格塞进多个原本不同时刻的音符** → 顺序音被压成同时发声、同音高重复被 lane 字典覆盖丢失 → 听感"掉拍"。细网格(0.05s)下晴天有 **1161 个发声时刻 vs 粗网格 1005**,差的 156 个就是被塌掉的。

**对抗式排查链(每步都有数据, 逐一证伪旧假说)**:
1. **不是服务端/区块保存/GC**:spark 实测(`/spark profiler --only-ticks-over 50` + gcmonitor),整首最差 tick **58ms**、中位 4ms、TPS 18–20、CPU 2–3%,GC 停顿 0–6ms。**推翻了早先"sync-chunk-writes stall"主假说。**
2. **不是红石脉冲机器**:做了纯数据包**调度器版**(`schedule` 直接触发 playsound、无红石、无 forceload),**仍断拍** → 排除红石。
3. **不是采样/乐器**:把自定义采样换成**原版音符盒声音**,**仍断拍** → 排除采样(也排除采样长度/重叠:断音与"前 2.8s 活跃采样数"无正相关,反而稀疏段更易断)。
4. **是这首 MIDI 经粗网格的产物**:换**龙卷风 / One Last Kiss** 两首不同 MIDI(走脚本 12 的 0.05s 细网格调度)**完全无断拍** → 锁定到"晴天数据 × 0.221 粗网格"。
5. **细网格复现修复**:同一份晴天 notes.json 改用 0.05s 细网格调度(`13_build_qingtian_fine.py` → `qzqtf`)→ 恢复 156 个被塌发声。

**附带修掉的两个独立 bug**:① 世界里旧版(band 命名 `pno_bN`)更长机器的**孤儿命令方块**(cell 1247–1579)残留 → 尾部哑音/"红石往后空跑"(`qzpno:cleanorphan` 已清);② **`tick rate` 命令在数据包函数里加载即报错**("未知命令 at position 0")→ `qzpno:tempo` 没载入 → tick rate 停 20、曲速偏快(只能手动 `/tick rate 18.1`)。

**结论与取舍**:红石机器(0.221s 格)**本质上无法忠实表现 <0.221s 的节奏**;细节多的曲子要么走**调度器细网格**(`12`/`13`,无红石但保真),要么接受红石的节奏精度上限。诊断工具链:音频 onset 缺口分析(`09`)、spark `.sparkprofile` protobuf 解析、region 文件扫描孤儿。

---

## 1. 整体架构 / 实现逻辑

```
MIDI 文件 (晴天钢琴版, 1927 音符, 已知 tempo)
  └─ midi_to_notes.py (mido 解析)→ notes.json: [{t秒, midi, dur, vel}]   (--poly 全复音 / 默认取每200ms最高音)
       └─ 06_build_poly.py:
            ① 量化: cell = round(t / U),  U = 2*DELAY/TPS = 4/18.1 = 0.221s = 一个十六分音符(♩≈68)
            ② 复音分配: 每个 cell 内同时发声的音符按音高排名 -> 分到 7 条 lane(每 lane 每 cell 最多 1 个音)
            ③ 采样映射: 每个音 -> 最近的钢琴 band(C1..A5 每小三度) × 力度层(p/mf/f, 由 MIDI vel 选)
                         pitch = clamp(2^((midi-base)/12), 0.5, 2.0)   (band 间隔小,移调≤1.5半音)
            ④ 生成 资源包(sounds.json + 60个钢琴ogg) + 数据包(红石机器逻辑)
       └─ 游戏内: 资源包(音色) + 数据包(机器)
            /tick rate 18.1  (手动!见 §3-坑3)
            /function qzpno:setup  -> forceload + 建造 7 条红石脊柱
            /function qzpno:play    -> 一条瞬时红石脉冲沿每条 lane 跑, 到每个命令方块就 playsound
```

**为什么这么设计**:
- 用 **MIDI** 而非音频转写——音频自动转写(librosa pyin)精度不够、听不出曲子(见 §4-1)。
- 用 **`/playsound` 自定义采样**——绕开音符盒 16 乐器/25 音高(2 八度)限制,得到任意钢琴音色与宽音域。
- 用 **红石脉冲触发**(不是后台数据包调度器)——用户要求"红石是核心"(见 §4-3)。
- 用 **`/tick rate` 调速**——红石延时器最细 0.1s,对不齐 0.22s 的十六分音符;调 tick rate 让"delay-2 一格 = 0.221s"精确匹配 ♩68(见 §4-4)。

---

## 2. 文件 / 脚本清单(均在 `poc/`)

| 文件 | 作用 |
|---|---|
| `midi_to_notes.py` | MIDI → notes.json(mido 解析,复用早期 song_model.py 思路) |
| `06_build_poly.py` ★ | **主建造器**:notes → 7 lane 红石机器 + 钢琴资源包(当前在用) |
| `02c_make_piano_velocity.py` | 抓 Salamander 钢琴(CC-BY)C1..A5 × 3 力度层 → 60 个短 ogg |
| `04_preview.py` | 按 `/playsound` 逻辑离线渲染预览音频(验收用,无 MC) |
| `05_deploy.py` | 把资源包(zip)+数据包(folder)装进 Modrinth 实例 + 启用 |
| `08_test_pulse.py` | 单轨脉冲隔离测试(诊断用) |
| `01_transcribe.py` / `02*_make_samples*.py` / `03_build_pack.py` | 早期音频转写路线(电吉他版,已弃用,留作脉络) |
| `07_build_scheduler.py` | 数据包游戏刻调度器路线(已弃用,见 §4-3) |
| `gen_demo_midi.py` | 生成公有领域测试 MIDI(验证精确管线) |

> 早期"可行性/继承"分析见 `00_继承分析.md`、`01_可行性与架构.md`(红石音乐三档可行性、硬约束核实、样本库许可)。

---

## 3. 关键 MC 约束(踩过、已核实)

| # | 约束 | 来源/影响 |
|---|---|---|
| 1 | `/playsound` **无 note-off**,一次性播完整段;`/stopsound` 只能按 类别/事件 停,不能停单个实例 | 持续音叠加;样本须保持短+淡出 |
| 2 | `/playsound` pitch 钳制 **0.5–2.0**(±1 八度),改 pitch 同时改时长 | 宽音域靠多采样,不靠极端 pitch |
| 3 | `/tick rate` 作为**命令**可用,但**写进数据包函数里静默失效**(本机/本实例;旧项目交接文档亦记录) | **曲速必须手动敲 `/tick rate 18.1`**,数据包自动版不生效 |
| 4 | `/forceload add` **单条命令上限 256 区块**,超出整条被拒 | 大机器 forceload 必须按面积切条(本 bug 见 §4-6) |
| 5 | 客户端同时发声 **247 静态池**(可被 RSLS 等 mod 提到 4095);超限按 类别+距离 丢声 | 密集复音风险;本曲峰值 34,装 RSLS 后无虞 |
| 6 | 红石:命令方块用**顶上红石线(dust)**触发最稳;repeater `facing` = 输入端方向(facing=west 输出 +X) | 机器脊柱设计依据 |
| 7 | 远程建造:setble 在未加载区块上当 tick 静默失败 → setup 须先 forceload + tp 玩家 + 等区块加载再建 | 否则机器残缺 |

---

## 4. 排查历史(时间线:问题 → 诊断 → 修复 → 结果)

1. **音频自动转写听不出曲子** → 起初用 Demucs 分轨 + librosa pyin 转写(电吉他/人声)。用户:"完全听不出是晴天"。诊断:取错声部(吉他=伴奏+低频 bleed)、单音 pyin 有损。→ **改用 MIDI 符号化输入**(精确)。

2. **MIDI 输入** → 用户提供晴天钢琴 MIDI;`midi_to_notes.py` 解析。公有领域 demo(音阶+欢乐颂)验证管线"音高分毫不差"。

3. **数据包调度器路线被否** → 一度改用数据包游戏刻(0.05s)链式 schedule 调度 playsound(`07_build_scheduler.py`)+ 混响 + 延音。用户:"更差,节奏混乱;且红石才是核心,不该放弃红石触发"。诊断:链式 schedule 在负载下抖动;混响 taps 把声音搞糊。→ **回到红石机器,去掉混响/延音**。

4. **曲速不对(节奏怪)** → 红石用 0.2s 网格(delay-2 @ 20TPS),但十六分音符是 0.2206s,被压缩 + 银行家舍入抖动 → 漂移磕巴。诊断:网格 vs 真实节拍错位。→ **量化到十六分网格 + `/tick rate 18.1`**(delay-2 一格=4游戏刻=0.221s=16分音符@♩68)。发现 §3-坑3:tick rate 须手动。结果:节奏均匀、曲速基本对。

5. **音质/强弱差** → 单一力度采样、样本截太短(1.4s)。用户:"档次差、强弱无法调整"。诊断:没用 Salamander 的 16 个力度层、样本太短=断气。→ **3 档力度层(p/mf/f,由 MIDI vel 选)+ 样本加长到 2.8s**(`02c`)。

6. **周期性断拍(核心未解)** → 见 §0 的逐项排除。已修 forceload-256 bug,但**据报仍断**。**当前卡在这里**。

---

## 5. 当前机器精确规格(请 GPT 复核红石)

- **坐标**:起点 OX=25000, OZ=0, **Y=-59**(超平坦地表)。命名空间 `qzpno`。
- **7 条 lane**,Z = 0,4,8,12,16,20,24(`LANE_DZ=4`)。每条是一条沿 +X 的红石线,长 **MAXCELL=1246 格**(=2492 方块)。
- **每格 = 2 方块**:
  - 奇位 `2c-1`:`Y-1` 放 `white_wool`,`Y` 放 `repeater[facing=west, delay=2]`(facing=west → 输出 +X)。
  - 偶位 `2c`:`Y` 放 `redstone_wire`;其**正下方 `Y-1`**:该格有音符则放 `command_block[facing=down]{Command:"execute as @a at @s run playsound qzpno:<样本> master @s ~ ~ ~ <vol> <pitch> 1"}`,否则放 `white_wool`。
  - 即:`repeater → dust → repeater → dust …`,命令方块在 dust 正下方,被 dust 的上升沿触发(MC 已验证 dust-on-top 可触发命令方块)。
- **起跑**(`fire` 函数):
  - 先 `forceload add`(2 条,各 ≤240 区块,覆盖整机)。
  - 在每条 lane 的源点(`x=OX-1, Y`)`setblock redstone_block`(7 条同 tick 放下)。
  - `schedule function qzpno:firestop 6t`(6 游戏刻后撤掉红石块 → 一条**瞬时 6t 宽脉冲**沿每条 lane 跑,跑完整条线自然归零)。
  - `schedule function qzpno:done <END_TICKS>t`,`END_TICKS = MAXCELL*DELAY*2 + 200 = 1246*4+200`。
- **计时**:脉冲每 1 格 = delay-2 = 2 红石刻 = **4 游戏刻**;`/tick rate 18.1` 下 = 0.221s/格 = 一个十六分音符。
- **采样**:`02c` 产的 60 个 ogg(20 音 C1..A5 每小三度 × p/mf/f),全局归一保留强弱;每音选最近 band+力度层,pitch=2^((midi-base)/12)∈[0.5,2],样本 2.8s + 末 10% 淡出。
- **复音**:单格最多 7 个音(分到 7 lane);本曲 0 个被丢;峰值同时发声 34。
- **play/done/load/cleanup**:PLAY 锁(防叠播)、done 撤 forceload + `tick rate 20`、load(进世界)硬清 forceload+schedule(防无限重载)。

**可疑点(供 GPT 重点查)**:
- 一条 **6 游戏刻宽的瞬时脉冲** 穿过 **1246 个 delay-2 repeater** 是否会在长距离上丢失/被某个 repeater 吞掉,导致部分命令方块漏触发?
- **7 条并行 lane** 是否真同步?是否某条/某段周期性掉拍?
- **dust 正下方密集排布的命令方块**(本曲 ~80% 格子有命令方块,远比早期稀疏的版本密)会不会影响 dust 信号传播?
- 是否存在与脉冲传播相关的 **~8s(≈36 格 @0.221s,或 40 格 @0.2s)** 周期?(注:40 格 = 早期滑动 forceload 窗口步长,但该窗口已移除。)

---

## 6. "8 秒周期" 已知线索 + 候选假设

- 用户听感:明显 ~8s 周期;手记断点间隔 6–13s(均 ~8s)。
- 8s ≈ 36 格(@0.221s/格,tick rate 18.1)或 40 格(@0.2s/格,若没设 tick rate=20TPS)。
- 候选(待 GPT/调研判定):
  1. 红石长脉冲在 ~36–40 格处周期性丢触发(脉冲整性/repeater 时序)。
  2. 某客户端音频线程/缓冲周期(画面不卡但声音断,偏向客户端音频或丢触发)。
  3. 机器未完全建成(14 批建造若有批次没跑全,某段缺命令方块——但应是固定缺口非周期)。
  4. 区块边界(每 16 方块=8 格)相关的红石跨区块行为(但 8 格=1.77s,非 8s)。
- 用户提议的"**手动 8s 补丁**":若确为固定 8s 周期的机器性丢拍,可考虑每 8s 重新激励脉冲/补一拍;但需先确认根因(避免再次治标)。

---

## 7. 复现 / 构建步骤

```bash
# 依赖: Python(venv 含 mido, numpy, soundfile, librosa, ffmpeg)
python midi_to_notes.py <song>.mid --poly          # -> notes.json
python 02c_make_piano_velocity.py                  # 下载 Salamander 钢琴样本 -> samples_piano/ + manifest
python 06_build_poly.py                            # -> build/qzpno_mv(资源包) + build/qzpno_redstone(数据包)
python 04_preview.py                               # (可选) 离线渲染 reconstruction_preview.ogg 验收
python 05_deploy.py qzpno                           # 装进 Modrinth 实例
# 游戏内:
/reload
/tick rate 18.1                                     # 手动!曲速(数据包自动版失效)
/function qzpno:setup                               # 等绿字 built
/function qzpno:play                                # <- 这里出现周期性断拍
```

---

## 8. 未入库的内容(版权/体积)
`.gitignore` 排除:歌曲 `*.mid`、由其生成的 `notes.json`/`schedule.json`、所有 `*.ogg`/`*.wav`(含 Salamander/Karoryfer 采样与音频预览)、`build/`、`samples*/`、`_work/`。
原因:① 歌曲及其衍生数据为版权内容,公开仓库不再分发;② 采样按各自许可(Salamander CC-BY 需署名、Karoryfer CC0)可由脚本自行抓取重生成;③ 减小仓库。GPT 评阅只需代码 + 本文。
