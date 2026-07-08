# VERSION_TACTICS — 全版本战术地图（工匠路径）

> **读者**：拿到"把 MIDI 在某个 Minecraft 版本里用红石/音符盒播放"需求、且**目标版本落在绿档之外**的执行 agent。
> **定位**：这不是"本工具支持哪些版本"的清单，而是一张**作战地图**——你有完全行动力，本文告诉你**在任意版本上可以怎么打**：领域知识 + 战术方案 + 验证方法。skill 是"技能"不是"标准化工具"，对远古到最新的任意版本，你自己动手打，而不是硬拒。
> **事实底座**：所有 API 分水岭、格式数字、工具链矩阵均引自
> [`../../docs/history/RedPiano多版本兼容-深度调研报告.md`](../../docs/history/RedPiano多版本兼容-深度调研报告.md)（下称"报告"，逐条 D-1..D-8）。
> 本文任何数字若与报告冲突，以报告为准——发现冲突请先回报告核对。

---

## 0. 读法（先读这一段决定走哪条路）

- **绿档 = `1.21` .. `1.21.10`**：全自动快速路径，**不用读本文**。直接照
  [`../SKILL.md`](../SKILL.md) 走 `fetch_binaries.py` → `prepare_all.py` → `DEPLOY_TO_GAME.bat`。
  11 颗预编 jar 入库 + `VERSION_TABLE` 自适应 `pack_format`/文件夹/sign 方言，质量很高，**不要拆、不要在这条路上现场造轮子**。
- **绿档之外 = 本文的工匠路径**：任意非绿档版本都落在这里——**低于**绿档的 `≤1.20.6` / 远古 / 基岩，
  **以及高于绿档的未来版本（`>1.21.10`，如 1.22 / 1.23 及更高）**。没有预编 jar、没有现成 `VERSION_TABLE` 行，
  你按本文的分代战术，就地判断"这一版能打到什么程度、用什么机型、怎么验证"。
  > **向前（未来版本）反而是最容易的方向**——MC 的 API 向前只增不减，mod 多半零改动，
  > 你只需查新版的 `pack_format` + 重编 + 实听；真正的闸门是 Fabric 上游是否已出该版本的构建。详见 **§2.A⁺**。
- **明确不做**（用户已拍板否决"标准化工具"路线）：**不要**为新版本写适配代码——
  不加 `VERSION_TABLE` 行、不改 mod 的 Java 源、不编新 jar 入库。那是把 skill 变回工具。
  本文教你**现场为单次交付**打一台能响的机器（或诚实降档 / 诚实出局），而不是把新版本固化进仓库。
  > 例外：如果**用户明确要求**"给我把 mod 移植到 1.20.6 并长期维护"，那是另一个工程任务，
  > 参照 [`MOD_ARCHITECTURE.md`](MOD_ARCHITECTURE.md) §6 的完整移植流程，不在本文"单次交付"范围内。

---

## 1. 原语年表（造红石音乐机依赖哪些游戏原语，何时才有）

每一行：**原语 | 引入版本 | 对造音乐机意味着什么**。这是判断"某版本能打成什么样"的地基。

| 原语 | 引入 | 对音乐机的意义 |
|---|---|---|
| **音符盒 (note block)** | 远古（Beta 1.2, 2011） | 一切的本源。任何有音符盒的版本都能做"中继器行进线 + 音符盒"的纯红石音乐机。乐器数随版本增长（见 §3 音色）。 |
| **命令方块** | 1.4.2 | 有它才能在世界里放"一条命令"。1.13 前没有函数数据包，命令方块链 + 结构方块是唯一的"程序化"手段。 |
| **`/setblock`** | 1.7.2 | 单点放方块。程序化摆机器的最小原语；1.13 前只能一条条命令方块喂。 |
| **`/fill`** | 1.8 | 批量放方块。骨架/中继器行大规模铺设靠它；本 skill 的生成器就是产 `fill`/`setblock` 清单。 |
| **函数数据包 + `/function`** | **1.13**（数据包形态；`/function` 命令本身 1.12 已有，走世界存档 `functions/` 目录） | 分水岭。1.13+ 才能把成百上千条 `setblock` 打包进 `.mcfunction`、随数据包分发，一条 `/function` 建整台机器。**1.13 以下**虽有 1.12 的世界内 `functions/` 命令雏形，但没有可分发的数据包形态——退回命令方块链或人肉摆放。 |
| **`/schedule`** | **1.14**（基础语法） | 定时执行函数=乐曲时间轴的引擎。melody-cut、逐拍触发都靠它。**1.14 才有**。 |
| **`/schedule … clear` / `append\|replace`** | **1.15** | 1.14 只有基础 `/schedule function <ns> <time>`；1.15+ 才有 `clear` 和 `append/replace` 修饰。本 skill 的 `cutmel` 复用 `append`——**在 1.14 上要改写成不依赖 append 的形态**。 |
| **原版 `/tick rate`** | **1.20.3** | **tick80 模型的硬下限**。qzpno 样本按 `/tick rate 80`（80 TPS）调音；`/tick rate` 1.20.3 才进原版。**1.20.2 及以下没有它**——要么装 Carpet（§2.C 战术 C-a），要么 tick20 降档（§2.C 战术 C-b）。`/return` 于 1.20.2（23w31a）加入，1.20.3 加的是 `return run`。 |
| **函数文件夹 `function/` 单数** | **1.21**（pack_format 48） | 1.21 把 `functions/`→`function/`、`tags/functions/`→`tags/function/`。**1.14–1.20.6 全是复数 `functions/`**（报告 D-7）。写数据包时这个字母 s 错了整包不加载。 |

**给 agent 的用法**：拿到版本先在这张表上从下往上勾——有没有 `/tick rate`？有没有 `/function`？有没有 `/schedule`？
每失去一个原语，机型就往"更手工"退一档。§2 就是按这些台阶分代给方案。

---

## 2. 分代战术（每代：可用原语 / 推荐机型 / 计时 / 声音 / 已知坑 / 验证清单）

### 2.A  `1.21` .. `1.21.10` — 快速路径（本文不重复）

绿档。走 [`../SKILL.md`](../SKILL.md)。本文到此为止不再展开。若用户版本在此带内却来读本文，把他领回 SKILL.md。

---

### 2.A⁺  高于绿档的未来版本（`> 1.21.10`，如 1.22 / 1.23、更高）— 向前兼容

**核心判断：向前比向后容易。** 向后退版本 API 会**消失**（`getPitchFromNote` 1.20 前没有、实体锚定
`playSeededSound` 1.19.3 前没有，越退越难）；向前 MC 的接口基本**只增不减**，mod 用到的
`NoteBlock.triggerEvent`（1.14.4→1.21 签名稳定）、`getPitchFromNote`、`ResourceLocation.parse`、
`Holder<SoundEvent>` 重载在未来版本里**大概率原封不动**——110 行 mod 源码很可能一个字不改就能编过。
连当初标为待核的 yarn `getWorld→getEntityWorld`（1.21.9）在官方 Mojang 映射下都没触发，
1.21.9 / 1.21.10 就是**零源码改动**编出来的。

**四步战术**（对 1.23 或任何 `>1.21.10` 的版本）：

1. **取两个 `pack_format`**（数据包 dp 与资源包 rp 是**两条不同的数**）——唯一必须查的关键数字。
   走 **§4 自检五问**第 3 问的 minecraft.wiki 实时 API；
   新版发布后 wiki 通常几天内更新。也可直接从该版本自带的**原版数据包 / 资源包的 `pack.mcmeta`** 里读出来。
   **绝不能猜**——猜错 rp = MC 静默禁用资源包 = 全静音（这是本项目栽过的坑，`get_version_profile` 的 "never guess" 就是为它）。
2. **确认 `pack.mcmeta` 形态**——1.21.9 起是 `min_format` / `max_format` 双值；向前多半沿用，
   `build_resourcepack.py` / `redpiano_core` 两种形态都已支持。
3. **确认文件夹名 / sign 方言**——`functions/`→`function/` 在 1.21 变过一次，未来可能再改新东西；自检五问逐个核。
4. **mod：填新工具链号 → 编 → `--check-jar` → 实听**。`mod_build.py --write` 写 gradle 数字，
   然后 gradle build + `--check-jar` 字节码校验 + **进游戏实听整曲**。（这是"单次交付"；除非用户要长期维护，不把 jar 固化入库——见 §0「明确不做」。）

**唯一真正的闸门：Fabric 上游是否已支持。** 这是 skill 自己解决不了的一环——
`fabric-loom` / `fabric-api` / `fabric-loader` 必须已经为该版本出了构建，否则根本编不出 mod；新版本刚发布有社区滞后期。
Fabric 没跟上时**诚实降级**（§0 交付准则第 5 条）：
- 退 **§3 原版音色数据包**——无 mod、纯原版音符盒音色 + tick20；数据包层纯表驱动，
  只要有了第 1 步的 `pack_format` 就能出一台**能响**的机器；
- 或如实告诉用户"mod 声音要等 Fabric 支持该版本，先给你原版音色版 / 稍后再补"，**绝不谎称已支持**。

**已知坑（版本越高越要防）**：越新的版本越可能带来某个结构性变动——新的 `pack.mcmeta` 字段、组件系统重做、
某个映射改名。所以第 4 步的**实听整曲**在未来版本上比任何时候都关键，自检五问第 5 问一条都不能省。

**验证清单**：同 §2.B（`/reload` 无报错、资源包无 "incompatible pack_format" 警告、日志 `[RedPiano] loaded`
无 mixin `InjectionError`、映射方块下音符盒响钢琴采样且音高正确、**实听整曲**）。

---

### 2.B  `1.20.3` – `1.20.6` — 最近邻带（tick80 仍成立，mod 需重编一处）

**这是绿档之外最值得认真打的一档**：原版 `/tick rate` 存在 → tick80 音乐模型完整成立，
数据包只是几个格式数字的差异，mod 的改动点极小。报告一页决策建议里，B-1（1.20.5/1.20.6）是"短期工程最优"，
B-2（1.20.3/1.20.4）是"低悬果加做"。

- **可用原语**：`/function`✓ `/schedule`(含 clear/append)✓ `/tick rate`✓ 全齐。跟绿档几乎等价。
- **推荐机型**：与绿档相同——`inplace`（原地调色板，footprint 最小、最稳）或 `swave`（S 波行进）。
  生成器逻辑不用改（它按版本档案产命令），只有**数据包格式**和**mod 二进制**要对上。
- **计时策略**：`/tick rate 80`，玩家手动敲（本 skill 一贯策略，机器不自设——见 `redpiano_core.py` L895 注释）。tick80 = 每红石刻 2 游戏刻 = 单元 U=0.025s，与绿档一致。
- **数据包格式（报告 D-7，务必查表逐行对）**：
  | MC | dp_format | rp_format | 函数文件夹 | sign 方言 |
  |---|---:|---:|---|---|
  | 1.20.3–1.20.4 | **26** | **22** | `functions`（复数!） | `front_text.messages` + JSON **string** |
  | 1.20.5–1.20.6 | **41** | **32** | `functions`（复数!） | `front_text.messages` + JSON **string** |
  - 注意两个陷阱：① 文件夹是**复数 `functions/`**（绿档是单数，别照搬）；② sign 用 1.20 后的
    `front_text.messages` 结构，但每条消息是 **JSON 文本字符串**方言（不是 1.21.5+ 的 SNBT compound）。
    `redpiano_core.py` 里对应 `sign_dialect="component_string"`——这个方言函数在 core 里已存在且可用，
    只是这些版本的 `VERSION_TABLE` 行被 `assert_build_supported` 归为 "yellow" 拒绝。
  - **单次交付的现场做法**：`get_version_profile` 对 1.20.3–1.20.6 能返回正确档案（它们有行、`has_tick_rate=True`），
    只是 `assert_build_supported` 把 yellow 拒了。你要么**手工按上表数字产数据包**（不改仓库），
    要么在你自己的临时脚本里绕过 assert 直接调 `get_version_profile` + `emit_*`（这属于"为单次交付现场打"，不是"加 VERSION_TABLE 行入库"）。
- **声音策略（mod 重编——报告 D-1/D-2/D-3/D-5 已把改动点收敛到极小）**：
  - **记分板 API 不用动**：`ScoreHolder`/`ReadOnlyScoreInfo`/`getPlayerScoreInfo` 分水岭是 **1.20.3**（报告 D-1），
    1.20.3+ 已是新 API，`rpcfg` 那段（`RedPiano.java:65-71`）原样可用。
  - **唯一必改点**：`ResourceLocation.parse(...)` 是 **1.21 专属**（报告 D-2）。1.20.6 及以下改成
    `new ResourceLocation(e.sound)` 或 `ResourceLocation.tryParse(e.sound)`。这一处在 `NoteBlockMixin.java:35`。
  - **声音播放主重载可用**：`playSeededSound(Player, Entity, Holder<SoundEvent>, SoundSource, float, float, long)`
    在 1.20.x 全线存在（报告 D-2），per-player 居中的"完美音频"修复原样成立。
  - `getPitchFromNote(int)` 1.20 就有（报告 D-3），这一带**不用**内联音高公式。
  - **工具链（报告 D-5）**：Loom `1.10.5`；**1.20.3/1.20.4 用 Java 17**，**1.20.5/1.20.6 用 Java 21**。
    fabric-api 精确版本报告 D-5 表里逐版列了（如 `0.91.1+1.20.3`、`0.100.8+1.20.6`）。
  - agent 可现场按 [`MOD_ARCHITECTURE.md`](MOD_ARCHITECTURE.md) §6 的移植流程 + 报告执行这次编译；
    **但**：一个 jar 不能横跨版本（`fabric.mod.json` 的 `minecraft` range + Fabric 拒装不匹配的 jar），
    每个版本都要单独 build + 实听。**沙箱通常编不出 jar**（缺 JDK/网络到 maven.fabricmc.net）——
    编不了就**退而求其次用降档声音策略**（§3 原版音色 tick80/tick20），别硬编、**绝不造 fabric-api stub**（SKILL.md 明令、报告外的仓库铁律）。
- **已知坑**：① 文件夹复数忘了改 → 整包不加载（静默）；② rp_format 不匹配 → MC 静默禁用资源包 → 全静音；
  ③ 编出的 jar 的 `fabric.mod.json` minecraft range 没覆盖运行版本 → Fabric 拒装；④ 没实听就宣称成功。
- **验证清单**：
  - [ ] 数据包：`/reload` 无报错，`/function <ns>:setup` 建出实体机器（不是 Unknown function）。
  - [ ] 资源包：Options→Resource Packs 里 qzpno 在右侧已选用、无 "incompatible pack_format" 警告。
  - [ ] mod：日志有 `[RedPiano] loaded`，无 mixin `InjectionError`。
  - [ ] 声音：映射方块（如 white_concrete）下的音符盒响的是钢琴采样、音高正确，不是原版竖琴。
  - [ ] per-player：播放中走远不断音。
  - [ ] **实听一遍整曲**（MOD_ARCHITECTURE §6.6）——重编的 mixin 能编过却哑/走音，唯一判据是耳朵。

---

### 2.C  `1.14` – `1.20.2` — 无原版 `/tick rate` 带（三条战术任选）

此带有 `/function`、`/schedule`，但**没有原版 `/tick rate`**（1.20.3 才进）。tick80 不能靠原版拿到。
三条战术，按用户约束选：

#### 战术 C-a：Carpet mod 提供 `/tick rate 80`（报告 D-6）
- **原理**：Carpet 的 `TickSpeed`/`ServerTickRateManager` 把服务器主循环 50ms/tick 的等待改成 `1000/tickrate` ms，
  语义上接近原版 1.20.3+ 的 `/tick rate 80`（报告 D-6 源码证据）。装了 Carpet 就能 tick80，音乐模型完整成立。
- **版本可用性（报告 D-6 的 release 列表，逐版存在）**：1.14.4 / 1.15.2 / 1.16.5 / 1.17.1 / 1.18.2 /
  1.19.2 / 1.19.4 / 1.20 / 1.20.1 / 1.20.2 都有对应 Carpet release。
- **必须向用户申明的副作用**：`/tick rate` 是**全服务器加速**——红石、实体、随机刻、AI、函数调度全部按更短
  wall-clock tick 推进。若服务器扛不住 80 TPS，音乐速度会漂。**产品形态从"RedPiano + 数据/资源包"变成
  "RedPiano + Carpet 双 mod"**，安装说明要加 Carpet + 命令权限。
- **`/tick warp` 不能用**：它是"尽快推进 N tick"，会破坏实时听感——要 `/tick rate 80`，不是 warp（报告 D-6）。
- **agent 可独立执行度**：中。要额外让用户装 Carpet、还要给 1.14–1.20.2 编一份 RedPiano jar（见下声音策略）。
  能装 Carpet + 能编 jar → 这是此带最接近绿档音质的路。

#### 战术 C-b：tick20 降档（不装任何 tick-rate 手段）
- **原理**：游戏锁 20 TPS，红石刻 = 2 游戏刻 = 0.1s（U=0.1s，而非 tick80 的 0.025s）。时值粒度粗 **4 倍**。
- **代价**：快速跑动的音符/密集节奏会糊；**慢曲、简单旋律可接受**。melody-cut 时序按 20 TPS 重算。
- **好处**：零外部依赖，不装 Carpet；只要 mod 能出（或走 §3 原版音色则连 mod 都不要）。
- **agent 可独立执行度**：高。这是"版本太老又不肯装 mod"的稳妥兜底。

#### 战术 C-c：原版音色模式（见 §3）
- 不编 mod、不装资源包，纯原版音符盒 16 乐器（本带 ≥1.14，16 种齐全）+ tick20。此带都有 `/function`+`/schedule` 可驱动。最省事、最怀旧。

**mod 移植点（若走 C-a/C-b 且要 RedPiano 音质，报告 D-2/D-3/D-5）**：
- `ResourceLocation.parse` 同样要换成 `new ResourceLocation`/`tryParse`（1.21 专属，报告 D-2）。
- **`getPitchFromNote(int)` 1.20 才有**（报告 D-3）：**1.19.4 及以下要内联音高公式** `2^((note-12)/12)`（12 半音一倍频，note 12 = 基准）。
- **`SoundEvent.createVariableRangeEvent` 1.19.3+**（报告 D-2）：**1.19.0–1.19.2 没有**，要走裸 `SoundEvent`
  路线——`new SoundEvent(new ResourceLocation(e.sound))` + 裸 `SoundEvent` 版的 `playSeededSound` 重载
  （1.19.0–1.19.2 的 `playSeededSound` 是 `(Player,Entity,SoundEvent,...)` 而非 `Holder` 版）。
- 记分板：**1.20.3 以下**才需要旧 `Score`-object API（报告 D-1；`ReadOnlyScoreInfo`/`ScoreHolder` 是 1.20.3+ 新类）。
  `rpcfg` 那段要退回旧记分板 API（`RedPiano.java:65-71`，MOD_ARCHITECTURE §4.6 有注）。
- Fabric API 生命周期事件**不是**瓶颈：`ServerTickEvents.END_SERVER_TICK` 低至 `0.28.5+1.14` 就有（报告 D-4），覆盖整条 1.14 线。
- **数据包/资源包格式**：报告 D-7 全表（下方 §5 复制了一份），逐版对 dp/rp/文件夹/sign/schedule。

> **⚠ 声明盲区：1.14–1.18 无已验证的 mod 移植路径。** 上面的 mod 移植点（含裸 `SoundEvent` 路线）最老只覆盖到
> **1.19.0–1.19.2**。**1.14–1.18 没有 `playSeededSound` 的实体锚定重载**（该重载是较晚才加进 `Player`/`Level` 声音 API 的），
> 因此 RedPiano"以玩家为中心发声"（走远不断音）这个核心修复，在 1.14–1.18 **没有已验证的移植路径**——本图不覆盖。
> 想在这些版本上追 RedPiano 音质（战术 C-a）的 agent，**须自行研究该版本的声音 API**：例如用 `playSound(Entity, ...)` 之类的
> 定位重载 + 让声音跟随玩家的策略，自己趟出一条路并**实听验证**；或者干脆改推战术 **(b) tick20 降档 / (c) 原版音色**——那两条不依赖此重载、稳妥可交付。
> **明说**：这是本图未覆盖的盲区，**不是已解决项**，不要当成"照抄就能编出来"。

---

### 2.D  `1.13` 及以下（数据包前夜 → 远古） — 纯红石 / 命令方块时代

红石音乐的**本源形态**。台阶继续往下掉：

- **1.13**：有 `/function` 数据包，但**没有 `/schedule`**（1.14 才有）。时间轴要靠命令方块链上的中继器延时，或 `/execute` 计数器。
- **1.13 以下（到远古 Beta）**：**没有函数数据包**。程序化手段只剩：
  - **命令方块链**（1.4.2+）：一串命令方块 + 中继器，逐拍触发音符盒。
  - **结构方块**（1.9/1.10+）：把手摆好的机器存成结构、批量粘贴。
  - **纯红石中继器计时**：中继器行进线 + 音符盒——**不依赖任何命令**，最古老、最通用，远古版本唯一的路。
- **音色**：只有原版音符盒——乐器数随版本（§3 音色表）。**没有 mod、没有采样资源包**（Fabric/采样机制这些老版本没有或差异巨大）。
- **机型**：全手工。**但本 skill 的几何知识仍然适用**——S-wave 折线、palette 调色板、多轨列对齐（memory: sync = 列对齐）
  这些拓扑是红石音乐的通用图纸，与版本无关。
- **agent 怎么用生成器**：把 `generators/` 的输出**当图纸**，人肉/写个小脚本翻译成：
  - 一份 `setblock` 清单（≥1.7.2 能一条条喂命令方块），或
  - 直接**指导玩家手摆**（给出音符盒坐标 + 每个音符盒的 note 值 + 中继器延时链）。
  生成器算好的"哪一拍触发哪个音、几何布局怎么摆"仍然值钱，只是最后一公里从 `/function` 换成手工/命令方块。
- **验证**：没有实体机器自检，只能**进世界手动触发一遍听**。慢曲优先（无 tick80，锁 20 TPS，粒度粗）。

---

### 2.E  基岩版 (Bedrock) — 诚实出局

- **裁定**：**告知用户并停止，不硬套**。基岩版没有 Fabric mod、没有 Java 数据包/`/function` 的等价物
  （行为包命令子集差异大），本 skill 的整条管线（数据包 + `/function` + `/tick rate` + Fabric mod）都不成立。
- **行为准则**：一句话讲清"这是 Java 版专属管线，基岩版走不通"，然后停。**不要**假装能做、不要硬套 Java 战术。
  （SKILL.md 前置门槛 (a) 已把 Bedrock 列为 stop 条件——本文与之一致。）

---

## 3. 通用降档模式（原版音色，任意 1.13+ 无 mod 无资源包）

**是什么**：不装 RedPiano mod、不装 qzpno 资源包，纯用**原版音符盒乐器**（1.14+ 满 16 种；1.12–1.13 只有 10 种；更早更少，见下）+ **tick20**。
只要 ≥1.13（有 `/function`）就能用数据包驱动；1.13 以下退回命令方块/纯红石（§2.D）。

**原版音符盒乐器数（音色台阶）**：
- 1.14+：**16 乐器**——1.14 又加了 6 种（iron_xylophone / cow_bell / didgeridoo / bit / banjo / pling）补齐到 16。
- 1.12–1.13：**10 乐器**——1.12 在原 5 种上加了 5 种（bell / flute / chime / guitar / xylophone），共 10。**不是 16**（16 要到 1.14）。
- 1.9–1.11：5 乐器（harp/bass/snare/hat/basedrum）。
- 更早：更少 / 仅基础音。
- 触发口诀（memory: noteblock-trigger-side-not-bottom）：音符盒**从侧面**用红石块激活，别从底下穿过映射方块。

**何时该主动推荐它**（不要默认硬上 mod）：
- 用户**不肯装 mod**（只想要数据包/纯原版世界）。
- 版本**太老**（<1.20.3 且不肯装 Carpet，或 mod 编不出）。
- 用户**只要怀旧味**——原版音符盒音色本身就是很多人想要的"红石音乐"声音。
- 沙箱/离线**编不出 jar**——与其造假 stub（禁止），不如诚实降到原版音色。

**代价**：音色是原版音符盒乐器（1.14+ 满 16 种，1.13 只有 10 种）而非 103 采样；tick20 粒度粗 4 倍。但它**零依赖、几乎任意版本可跑、绝不静默失败**，
是"通用 skill"叙事下最稳的战略选项（报告 B-4）。

---

## 4. 任意版本自检五问（面对未知版本怎么快速摸清地形）

拿到一个不认识的版本号，按顺序问自己这五问，就能定位战术：

1. **`/tick rate` 存在吗？** —— **≥1.20.3 = 有**（tick80 成立，走 §2.B 音质路）；**≤1.20.2 = 没有**
   （走 §2.C：Carpet / tick20 / 原版音色）。这是第一分水岭。
2. **函数文件夹叫什么？** —— **≥1.21 = 单数 `function/`**；**1.14–1.20.6 = 复数 `functions/`**；
   **≤1.13 无 `/function`**（退命令方块/纯红石 §2.D）。字母 s 错 = 整包静默不加载。
3. **pack_format 多少？** —— 数据包 dp 和资源包 rp 是**两条不同的数**，查下方 §5 全表；查不到就去
   **minecraft.wiki 的 `Pack format` 模板**现查（方法见 §5 末）。rp 不匹配 = MC **静默禁用资源包 = 全静音**。
4. **sign 方言是哪种？** —— **1.20 前**：`Text1`–`Text4`（旧结构）；**1.20–1.21.4**：`front_text.messages` + JSON
   **字符串**（`component_string`）；**≥1.21.5**：`front_text.messages` + **SNBT compound**（`component_snbt`）。
   控制台告示牌方言错 = 牌子上渲染成一串字面文本。
5. **听过一遍了吗？** —— 上面全绿也不算完。重编 mixin 能编过却哑/走音；资源包 pack_format 蒙对了也可能采样缺失。
   **实听整曲**是唯一的最终判据（MOD_ARCHITECTURE §6.6）。没听过 = 报"已构建，未实听确认"，不报成功。

**去 minecraft.wiki 现查的方法**（报告 D-7 给的 API 端点）：
- 数据包格式全表：`https://minecraft.wiki/api.php?action=parse&page=Template%3AData%20pack%20format&prop=wikitext&format=json`
- 资源包格式全表：`https://minecraft.wiki/api.php?action=parse&page=Template%3AResource%20pack%20format&prop=wikitext&format=json`
- `/schedule` 语法与历史：`https://minecraft.wiki/w/Commands/schedule`
- 告示牌 NBT：`https://minecraft.wiki/w/Sign`
- mod API 分水岭（记分板/声音/NoteBlock 签名）：官方 `server_mappings` + `mappings.dev`（报告 D-1/D-2/D-3 列了每版精确 URL）。

---

## 5. 数据包/资源包格式全表（1.14–1.20.6，报告 D-7 原样复制）

引用必须与此表一致（=报告 D-7）：

| MC | dp | rp | function_folder | packmeta | sign 方言 | schedule |
|---|---:|---:|---|---|---|---|
| 1.14–1.14.4 | 4 | 4 | functions | single | Text1-Text4 JSON string | basic（仅基础语法，**无 clear/append**） |
| 1.15–1.16.1 | 5 | 5 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.16.2–1.16.5 | 6 | 6 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.17–1.17.1 | 7 | 7 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.18–1.18.1 | 8 | 8 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.18.2 | 9 | 8 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.19–1.19.2 | 10 | 9 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.19.3 | 10 | 12 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.19.4 | 12 | 13 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.20–1.20.1 | 15 | 15 | functions | single | front_text.messages JSON string | clear/append/replace |
| 1.20.2 | 18 | 18 | functions | single | front_text.messages JSON string | clear/append/replace |
| 1.20.3–1.20.4 | 26 | 22 | functions | single | front_text.messages JSON string | clear/append/replace |
| 1.20.5–1.20.6 | 41 | 32 | functions | single | front_text.messages JSON string | clear/append/replace |

（1.21+：dp 从 48 起、文件夹改单数 `function/`、1.21.5+ sign 转 SNBT、1.21.9+ pack.mcmeta 转 min/max——那些在绿档 `VERSION_TABLE` 里，见 `redpiano_core.py`。）

**注意**：dp 与 rp 在很多版本**不相等**（如 1.18.2 dp9/rp8、1.19.3 dp10/rp12、1.19.4 dp12/rp13、
1.20.3 dp26/rp22、1.20.6 dp41/rp32）——分别对，别混用一个数。

---

## 6. mod 移植手册摘要（110 行 mod 的全部版本敏感点，报告 D-1..D-4 提炼）

一张表管住 RedPiano 全部版本敏感点。**每一版本都必须实听**——mixin 绑内部 NoteBlock 字节码，能编过 ≠ 会响。

| API / 位置 | 分水岭 | ≥ 分水岭写法（当前 1.21.8） | 旧版写法 | 文件:行 | 报告 |
|---|---|---|---|---|---|
| `ResourceLocation.parse(String)` | **1.21 专属** | `ResourceLocation.parse(e.sound)` | `new ResourceLocation(e.sound)` 或 `.tryParse(e.sound)`（≤1.20.6） | `NoteBlockMixin.java:35` | D-2 |
| `SoundEvent.createVariableRangeEvent` | **1.19.3+** | `createVariableRangeEvent(rl)` | 1.19.2-：`new SoundEvent(rl)`（裸构造器，无此工厂） | `NoteBlockMixin.java:35` | D-2 |
| `playSeededSound(...Holder<SoundEvent>...)` | **1.19.3+** 有 Holder 重载 | `(Player, Entity, Holder<SoundEvent>, SoundSource, float, float, long)` | 1.19.0–1.19.2：只有裸 `SoundEvent` 版实体锚定重载（无 Holder，无 `Holder.direct` 包裹） | `RedPiano.java:58` | D-2 |
| `NoteBlock.getPitchFromNote(int)` | **1.20+** | `NoteBlock.getPitchFromNote(note)` | 1.19.4-：**内联** `(float)Math.pow(2.0,(note-12)/12.0)` | `NoteBlockMixin.java:32` | D-3 |
| 记分板 `ScoreHolder`/`ReadOnlyScoreInfo`/`getPlayerScoreInfo` | **1.20.3+** | 当前 `rpcfg` 读法原样 | ≤1.20.2：旧 `Score`-object API（`getOrCreatePlayerScore(String,Objective)`） | `RedPiano.java:65-71` | D-1 |
| `NoteBlock.triggerEvent(BlockState,Level,BlockPos,int,int)→boolean` | **1.14.4–1.21 签名稳定** | 原样 `@Inject method="triggerEvent"` | 稳定（Yarn 映射下叫 `onSyncedBlockEvent`，仅换映射才变） | `NoteBlockMixin.java:26-27` | D-3 |
| `NoteBlock.NOTE`（IntegerProperty） | **1.14.4–1.21 稳定** | `state.getValue(NoteBlock.NOTE)` | 原样 | `NoteBlockMixin.java:31` | D-3 |
| `SoundSource.RECORDS` 枚举 | 长期稳定 | 原样 | 原样 | `RedPiano.java:58` | — |
| `ServerTickEvents.END_SERVER_TICK` | **fabric-api 0.28.5+1.14 起** | 原样 | 覆盖到 1.14，**不是瓶颈** | `RedPiano.java:36` | D-4 |
| 工具链 Java target | — | 21 | **1.20.3/1.20.4 = Java 17**；1.20.5/1.20.6 = Java 21；更早按 fabric-api 该版要求 | `gradle.properties` | D-5 |
| fabric-api / loader 精确版 | 每版不同 | 见 SKILL.md | 报告 D-5 表逐版列（如 `0.91.1+1.20.3`、`0.100.8+1.20.6`）；Loom 建议 `1.10.5` | `gradle.properties` | D-5 |

**移植铁律**（与 SKILL.md 一致）：
- 一个 jar **不能横跨版本**——`fabric.mod.json` 的 `minecraft` range + Fabric 拒装不匹配 jar；每版单独 build。
- **绝不**手写/伪造 fabric-api / fabric-loader stub 去骗编译通过——那是过不了 manifest 的静默失败（编出来对着空气编、不响）。
  编不出（无网 / 沙箱缺 JDK）就**报 blocked 并停**，或退到 §3 原版音色降档，不造假。
- 改 jar 要**重启 Minecraft**，不是 `/reload`（mod 类 JVM 启动时才加载）。
- 完整逐步移植流程见 [`MOD_ARCHITECTURE.md`](MOD_ARCHITECTURE.md) §6（本表是其 §6.1 检查表的报告-对齐摘要）。

---

## 附：一句话决策树

```
目标版本？
├─ 1.21..1.21.10 ................. 绿档，走 SKILL.md，别读本文
├─ 1.20.3..1.20.6 ................ §2.B：tick80 成立；数据包按 D-7 格式；mod 改 ResourceLocation.parse 一处 + Java17/21
├─ 1.14..1.20.2 .................. §2.C：无原版 /tick rate → (a)Carpet tick80 / (b)tick20 降档 / (c)原版音色
├─ 1.13 .......................... §2.D：有 /function 无 /schedule；命令方块链计时 + 原版音色
├─ ≤1.12（含远古） ............... §2.D：无函数数据包；纯红石中继器行 + 音符盒，生成器输出当图纸
└─ 基岩版 ........................ §2.E：诚实告知走不通并停，不硬套
```

*落笔自查：本文所有 API 分水岭（1.20.3 tick-rate/记分板、1.21 ResourceLocation.parse、1.20 getPitchFromNote、
1.19.3 createVariableRangeEvent/Holder 重载、1.14.4–1.21 triggerEvent 稳定、0.28.5+1.14 fabric-api）与全部
dp/rp 格式数字，均与 `RedPiano多版本兼容-深度调研报告.md` D-1..D-7 逐条一致。*
