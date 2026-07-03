<div align="center">

# McMusicMaker · 红石音乐机

**中文** · MIDI → Minecraft Redstone Music Machine

### 把任意一首 MIDI，在 Minecraft 里用真·音符盒 + 红石线路演奏出来。<br/>不是切片回放原曲 —— 是分轨转写音高、映射到真实乐器采样、按节奏在世界里搭一台会响的机器。

*一个「红石音乐 + agent skill」的作品：你给 agent 一首 MIDI 和一个存档，它替你把机器搭进世界。*

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/License-PolyForm%20Noncommercial%201.0.0-orange.svg?style=flat-square)](LICENSE)
[![Minecraft: Java 1.21–1.21.10](https://img.shields.io/badge/Minecraft-Java%201.21%E2%80%931.21.10-62B47A.svg?style=flat-square)](minecraft-redstone-music/docs/VERSION_TACTICS.md)
[![Fabric](https://img.shields.io/badge/Mod-Fabric%20%2B%20JDK%2021-DBB863.svg?style=flat-square)](minecraft-redstone-music/docs/MOD_ARCHITECTURE.md)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white)](minecraft-redstone-music/requirements.txt)
[![Stars](https://img.shields.io/github/stars/Cohenjikan/McMusicMaker?style=flat-square&logo=github)](https://github.com/Cohenjikan/McMusicMaker/stargazers)

</div>

---

## 这是什么

McMusicMaker 是一个 **agent 驱动的 Claude Code skill**，不是一个你自己敲参数的纯命令行工具。你把一首 **`.mid`** 文件和一个 **Minecraft 存档**交给 agent，它替你完成整条流水线：分析 MIDI、转写音高、映射到乐器采样、生成红石数据包、打包资源包与模组、并交付一台在世界里**真的会响**的音符盒机器。

它和「切片回放原曲音频」的红石音乐是两回事 —— 那条路已被证伪（见 [`00_继承分析.md`](00_继承分析.md)）。这里走的是**真实重构**：每个音符是一次真正的音符盒演奏，由自研的 **RedPiano** Fabric 模组把音色替换成对应的乐器采样，并把声音**以每个玩家为中心**播放，所以音乐会跟着你走、不会因为走远而断掉。

它有两条腿：

- 🟢 **绿档全自动**（Minecraft Java **1.21 – 1.21.10**）—— 这些版本我们有随仓的自编模组 jar，一条命令端到端出活。
- 🔨 **工匠路径**（任意版本，远古 → 未来）—— 版本不在绿档时，按 [`docs/VERSION_TACTICS.md`](minecraft-redstone-music/docs/VERSION_TACTICS.md) 手工适配（自编模组 / 换采样 / 调 `pack_format`）。

---

## 它能做什么

| 能力 | 说明 |
|---|---|
| **多乐器映射** | 一张 **103 块 / 5 乐器**的采样映射，把 MIDI 的分轨音色对应到不同的音符盒乐器，而不是全曲一个音色。 |
| **melody-cut 旋律不被埋** | pad / lead / bass 采样会盖住旋律；对每个旋律音**逐音 `stopsound` 截断**（精确到具体音效事件），让主旋律浮上来。 |
| **5 种机型** | `inplace`（原地调色板，验证过的 MVP，占地极小）/ `swave`（行进脉冲波）/ `straight`（直线）/ `custom`（自定义走线）/ `multilane`（多轨共享时间轴）。 |
| **可视化设计器** | 浏览器里的 `layout_designer.html`（加载真 MIDI + 路线播放头 + 多轨 / 侧视图，导出参数 JSON）与 `particle_editor.html`（粒子编辑）。 |
| **版本自适应引擎** | 一个 `--mc-version` 自同步 `pack_format`、数据包文件夹单复数、`pack.mcmeta` 形态、告示牌 sign 方言（1.21.5+ 走 SNBT）。 |
| **预检 + 体检** | `midi_report.py` 播前预检（时长 / 乐器分布 / 掉音估计 / 占地估计 + 一句话选型建议）；`doctor.py` 一键体检整条「没声」链路，逐项 ✓/✗ + 修复建议。 |
| **沙箱安全交付** | 在工作区构建到 `dist/`，产出原生 `DEPLOY_TO_GAME.bat` + 部署回执 `DEPLOY_RECEIPT.txt` —— 根治「AI 在沙箱里部署、真游戏读不到」的静默失败（见 [`docs/RUNTIME_SANDBOX.md`](minecraft-redstone-music/docs/RUNTIME_SANDBOX.md)）。 |

---

## 快速开始

### 前置

- **Minecraft Java Edition**（**不是** 基岩版 / Bedrock —— 数据包、`/function`、`/tick rate` 和 Fabric 模组在基岩版都不存在）。
- **Fabric Loader + Fabric API + JDK 21**（模组运行依赖）。
- **Python 3.8+**（`pip install -r minecraft-redstone-music/requirements.txt`，核心只依赖 `mido`）。
- 存档需开**作弊 / OP**（`/reload`、`/tick rate`、`/function` 需要）。

> ⚠️ **乐器采样不随仓分发。** 采样资源包 `qzpno_mv.zip`（版权不明的钢琴等采样）**不在本仓库**里 —— 请自备，或用脚本从各自的开放采样源重新生成。随仓分发的只有 **11 颗自编 RedPiano 模组 jar**（绿档 1.21 – 1.21.10）与 **Fabric API jar**（Apache-2.0）。详见 [`minecraft-redstone-music/BINARIES.md`](minecraft-redstone-music/BINARIES.md)。

### 🟢 绿档路径（golden 命令）

在 `minecraft-redstone-music/` 目录下跑（这样 `../binaries/…` 能解析到随仓的模组 jar）：

```bash
python scripts/prepare_all.py \
    --midi  path/to/song.mid \
    --form  swave \
    --ns    mysong \
    --origin 0 0 255 \
    --mc-version 1.21.8 \
    --world-dir   "<profile>/saves/<world>/datapacks" \
    --profile-dir "<profile>" \
    --dist dist \
    --samples-root ./poc            # ← 你自备的采样目录（源码检出里的 poc/）
    #   或  --prebuilt-rp path/to/qzpno_mv.zip   ← 你自备的现成资源包
```

- **模组 jar 走随仓 `binaries/`**：`python scripts/fetch_binaries.py --mc-version <ver>` 会按版本挑对 jar（sha256 校验、local-first），把它作为 `--prebuilt-mod-jar` 传入；Fabric API 由 `prepare_all.py` 自动从 Modrinth 拉取。
- **资源包必须你自备**：传 `--samples-root <采样目录>` 让脚本现打 `qzpno_mv.zip`，或 `--prebuilt-rp <你已有的 qzpno_mv.zip>`。
- 产物在工作区 `dist/`（数据包 + `qzpno_mv.zip` + `mods/*.jar`）+ 原生安装器 `dist/DEPLOY_TO_GAME.bat`。**它不碰 `C:\Minecraft` —— 那是 `.bat` 的活**：由**你本人在资源管理器里双击** `.bat` 安装，再用 `python scripts/deploy_bundle.py --verify dist` 确认 `✓ INSTALLED`。
- 完整清单（含「没声？先跑 doctor」排查框）见 [`minecraft-redstone-music/QUICKSTART.md`](minecraft-redstone-music/QUICKSTART.md)。

### 🔨 工匠路径（任意版本）

版本不在绿档（远古版本 / 未来新版）时，按 [`minecraft-redstone-music/docs/VERSION_TACTICS.md`](minecraft-redstone-music/docs/VERSION_TACTICS.md) 手工适配：重编对应版本的模组、按 `--mc-version` 调 `pack_format` / 文件夹 / sign 方言、必要时换采样。

---

## 文档

| 文档 | 内容 |
|---|---|
| [`minecraft-redstone-music/SKILL.md`](minecraft-redstone-music/SKILL.md) | skill 主入口：agent 该怎么问、怎么选型、怎么一步步交付。 |
| [`minecraft-redstone-music/QUICKSTART.md`](minecraft-redstone-music/QUICKSTART.md) | 从 `.mid` 到游戏里响的端到端清单 + 「没声」三步排查。 |
| [`minecraft-redstone-music/docs/VERSION_TACTICS.md`](minecraft-redstone-music/docs/VERSION_TACTICS.md) | 版本战术：绿档之外任意版本怎么手工适配。 |
| [`minecraft-redstone-music/docs/CONTRACT.md`](minecraft-redstone-music/docs/CONTRACT.md) | 设计器 → 生成器的参数契约（导出 JSON 的 schema）。 |
| [`minecraft-redstone-music/docs/MOD_ARCHITECTURE.md`](minecraft-redstone-music/docs/MOD_ARCHITECTURE.md) | RedPiano Fabric 模组架构：音色替换 + 以玩家为中心发声。 |
| [`minecraft-redstone-music/docs/FEATURE_MATRIX.md`](minecraft-redstone-music/docs/FEATURE_MATRIX.md) | 权威能力矩阵：5 种机型 / 各特性的状态与边界。 |
| [`minecraft-redstone-music/docs/RUNTIME_SANDBOX.md`](minecraft-redstone-music/docs/RUNTIME_SANDBOX.md) | 沙箱交付：为什么必须工作区构建 + 原生 `.bat` + 回执握手。 |
| [`minecraft-redstone-music/BINARIES.md`](minecraft-redstone-music/BINARIES.md) | 两类运行时二进制（模组 jar / 采样资源包）从哪来、怎么解析、许可归属。 |

---

## 关于

McMusicMaker 是一个 **vibecoding** 作品：由我（[Cohen](https://cohenjikan.com)）设计并把关方向，主要的代码由 **Anthropic 的 Claude** 编写处理。仓库里完整保留了这段人机协作的**开发日记**（[`DEVLOG.md`](DEVLOG.md) 与调研笔记 [`00_继承分析.md`](00_继承分析.md) / [`01_可行性与架构.md`](01_可行性与架构.md)），可以看到红石音乐从「切片回放」被证伪、到「真实重构」落地的完整迭代史。

它也是我一系列**非商业、源码公开**项目中的一个。更多项目见我的主页 **[cohenjikan.com](https://cohenjikan.com)** 与 GitHub **[@Cohenjikan](https://github.com/Cohenjikan)**。

---

## 开源致谢

**站在这些开源工作与社区之上：**

- **Fabric API** —— RedPiano 模组的运行依赖（[Apache-2.0](https://github.com/FabricMC/fabric)），jar 随仓分发。
- **Karoryfer** —— 电吉他采样（**CC0**）；**VCSL** 鼓组采样（CC0）；**Salamander** 钢琴采样（CC BY，需署名）。
- **[mido](https://github.com/mido/mido)** —— MIDI 解析。
- **Minecraft / Mojang** —— 音符盒、红石、数据包、`/function` 与 `/tick rate` 这套可编程世界本身。
- **红石音乐社区 / RedPiano 思路** —— 「用真·音符盒重新演奏、而非回放原曲」的方向来自这个社区的探索。
- **开发协作** —— 主要代码由 **Anthropic 的 Claude** 编写处理（vibecoding）。

---

## 许可

代码以 **[PolyForm Noncommercial 1.0.0](LICENSE)** 许可发布 —— **源码公开、仅限非商业使用**；商用授权请联系作者。随仓的 **RedPiano 模组 jar** 同样按 PolyForm NC 授权；**Fabric API jar** 按其自身的 **Apache-2.0** 再分发。

**乐器采样各自保留上游许可，且不随仓分发** —— Karoryfer 电吉他 / VCSL 鼓组为 **CC0**，Salamander 钢琴为 **CC BY**（需署名），其余采样（如来源不明的钢琴包）版权归原作者所有、仅作**非商业**使用，由你自行获取并遵守其许可。歌曲 MIDI 及其衍生数据的版权归原作者，不包含在本仓库中。详见 [`LICENSE`](LICENSE) 与 [`minecraft-redstone-music/BINARIES.md`](minecraft-redstone-music/BINARIES.md)。

<div align="center">
<sub>把任意一首 MIDI，在 Minecraft 里用真·音符盒演奏出来。</sub>
</div>
