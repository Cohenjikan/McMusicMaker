# McMusicMaker — 开发文档 / DEVLOG

> 把一首 **MIDI** 在 **Minecraft Java 1.21.8** 里用**红石机器**演奏出来:数据包驱动红石脉冲,每个音符触发 `/playsound` 播放**真实乐器采样**(资源包)。
> 本文给 **GPT 评阅**用:含整体架构、完整排查史、当前**唯一未解决问题**、以及机器的**精确规格**(便于复核红石逻辑)。
> 代码在本仓库;**版权素材(歌曲 MIDI、由其生成的 notes/schedule 数据、音频、采样)未入库**(见 §8),GPT 评阅只需代码+本文。

---

## 0. 置顶:当前唯一未解决的问题(请重点看这里)

**症状**:机器播放时出现**周期性"断拍"**——演奏中突然短暂静默一阵、然后接上,**大致每 ~6–13 秒一次(听感上有明显 ~8s 周期)**。

**已逐项排除(都有数据)**:
1. **不是音乐数据**:排程分析显示全曲 1005 个有音格、音符间隔几乎全是 1–2 格(0.22–0.44s),**整首只有 1 处 >1.55s 的空白**;离线渲染的预览音频(纯数学、无 MC)**全程连续**,只有开头 1.3s/结尾 1.9s 静默。→ 数据本身没有周期性空白。
2. **不是服务器卡顿(TPS)**:F3 `Integrated server @ 3.4/55.2 ms`(均 3.4ms,18.1 TPS 下每 tick 预算 55.2ms,用了 3.4ms),**画面/移动/生物全程流畅**(玩家确认"只有声音断、画面不卡")。
3. **不是声道上限**:装了 RSLS(把声道上限提到 4095),F3 `Sounds: 18–28/4087`,**远没满**(峰值同时发声仅 34)。
4. **forceload 256 上限 bug(已修)**:曾发现"整盘 forceload"单条命令 ~600 区块 > MC 的 **256 区块/条**上限被拒 → 机器没真正 forceload → 播放只覆盖玩家渲染距离。**已修**(切成 ≤240 区块/条,2 条命令)。**但修后断拍据报仍在**(或尚未干净复测)。

**求 GPT**:在"数据连续、TPS 满、声道没满、forceload 已修"的前提下,是什么让红石脉冲驱动的 `playsound` 出现 ~8s 周期性静默?重点怀疑**红石脉冲实现**(见 §5、§6)。

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
