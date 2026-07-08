<div align="center">

# McMusicMaker · 红石音乐机

**中文** · MIDI → Minecraft Redstone Music Machine

### 把任意一首 MIDI，在 Minecraft 里用真·音符盒 + 红石线路演奏出来。<br/>不是回放原曲音频 —— 是分轨转写音高、映射到真实乐器采样、按节奏在世界里搭一台会响的机器。

*一个「红石音乐 + Claude Code skill」的作品：你给 agent 一首 MIDI 和一个存档，它替你把机器搭进世界。*

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/License-PolyForm%20Noncommercial%201.0.0-orange.svg?style=flat-square)](LICENSE)
[![Minecraft: Java 1.21–1.21.10](https://img.shields.io/badge/Minecraft-Java%201.21%E2%80%931.21.10-62B47A.svg?style=flat-square)](minecraft-redstone-music/docs/VERSION_TACTICS.md)
[![Fabric](https://img.shields.io/badge/Mod-Fabric%20%2B%20JDK%2021-DBB863.svg?style=flat-square)](minecraft-redstone-music/docs/MOD_ARCHITECTURE.md)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white)](minecraft-redstone-music/requirements.txt)
[![Stars](https://img.shields.io/github/stars/Cohenjikan/McMusicMaker?style=flat-square&logo=github)](https://github.com/Cohenjikan/McMusicMaker/stargazers)

</div>

---

<!-- DEMO-PATH -->

## 🔊 5 分钟先听个响（官方最小 demo，不用自备任何采样）

第一次上手、只想快速验证「这套东西真能在 Minecraft 里响」？走这条**开放音源最小路径**：用随仓自带的 `assets/demo.mid`，音色由脚本**当场用 numpy 合成**（我们自产的开放音源，无任何许可负担），全程**不下载、不需要 ffmpeg**，一条链就能把完整 `dist/` 建出来。

> ⚠️ **两条硬前提**（和主流程一致）：**① 仅 Windows 交付**（安装器是 `.bat`）；**② 必须整仓 clone**——脚本依赖仓库结构（如 `../binaries/` 里的模组 jar），**不要**只单独拷 `minecraft-redstone-music/` 子目录。
>
> 说明：这里的合成音色是**能出声的最小验证**，不是精修的 Salamander 钢琴采样；先听个响，满意后再按 [采样与署名](#采样与署名) / [`BINARIES.md`](minecraft-redstone-music/BINARIES.md) 换成更好的采样即可。

**准备一次**（安装 Python 依赖 —— demo 路径比主流程多两个轻量包 `numpy`/`soundfile`）：

```bash
cd minecraft-redstone-music
pip install -r requirements.txt -r requirements-demo.txt
```

> 若 pip 报 UnicodeDecodeError，先执行 `$env:PYTHONUTF8=1`（PowerShell）/ `export PYTHONUTF8=1`（bash）再重试。

**三步出 `dist/`**（把 `<你的世界>` 换成你存档名；下面 PowerShell / bash 双版任选）：

<details open>
<summary><b>PowerShell</b>（反引号续行）</summary>

```powershell
# 1) 解析随仓模组 jar（这里用 1.21.7，随仓也带 Fabric API jar，全程离线）
python scripts/fetch_binaries.py --mc-version 1.21.7

# 2) 合成 103 个开放音源 demo 采样（写到 assets/demo_samples/，无网络/无 ffmpeg）
python scripts/make_demo_samples.py

# 3) 端到端：datapack + 资源包 + 模组 -> dist/ + 安装器
python scripts/prepare_all.py `
    --midi assets/demo.mid `
    --form swave `
    --ns demo `
    --origin 0 0 255 `
    --mc-version 1.21.7 `
    --world-dir "<profile>/saves/<你的世界>/datapacks" `
    --profile-dir "<profile>" `
    --dist dist `
    --prebuilt-mod-jar "../binaries/redpiano-1.0.0-mc1.21.7.jar" `
    --fabric-api-jar "../binaries/fabric-api-0.129.0+1.21.7.jar" `
    --samples-root assets/demo_samples
```

</details>

<details>
<summary><b>bash</b>（反斜杠续行；Windows 上用 Git Bash）</summary>

```bash
# 1) 解析随仓模组 jar（这里用 1.21.7，随仓也带 Fabric API jar，全程离线）
python scripts/fetch_binaries.py --mc-version 1.21.7

# 2) 合成 103 个开放音源 demo 采样（写到 assets/demo_samples/，无网络/无 ffmpeg）
python scripts/make_demo_samples.py

# 3) 端到端：datapack + 资源包 + 模组 -> dist/ + 安装器
python scripts/prepare_all.py \
    --midi assets/demo.mid \
    --form swave \
    --ns demo \
    --origin 0 0 255 \
    --mc-version 1.21.7 \
    --world-dir "<profile>/saves/<你的世界>/datapacks" \
    --profile-dir "<profile>" \
    --dist dist \
    --prebuilt-mod-jar "../binaries/redpiano-1.0.0-mc1.21.7.jar" \
    --fabric-api-jar "../binaries/fabric-api-0.129.0+1.21.7.jar" \
    --samples-root assets/demo_samples
```

</details>

跑完 `dist/` 里就有：数据包 `demo/` + `qzpno_mv.zip`（含 103 个合成采样）+ `mods/`（模组 jar + Fabric API）+ `DEPLOY_TO_GAME.bat`。**接着由你本人在资源管理器里双击** `dist\DEPLOY_TO_GAME.bat` 安装（脚本不碰你的游戏目录），进游戏后按 [`QUICKSTART.md`](minecraft-redstone-music/QUICKSTART.md) 手动 `/tick rate 80`、启用资源包、`/function demo:setup` → 播放。

> 上面是 **1.21.7** 的例子（随仓正好带了 1.21.7 的 Fabric API jar，可完全离线）。其它绿档版本（如 1.21.8）把三处 `1.21.7` 一起改掉，并**去掉** `--fabric-api-jar` 那行——`prepare_all.py` 会自动从 Modrinth 拉取匹配的 Fabric API（需联网一次）。
>
> ℹ️ 上述为**构建级验证**（`dist/` 产物齐全、资源包含全部 103 音效、`pack.mcmeta` 版本号正确）；**游戏内实听**请自行按 QUICKSTART 完成。

---

## 这是什么

你把一首 **`.mid`** 文件和一个 **Minecraft 存档**交给 agent，它替你跑完整条流水线，最后在世界里交付一台**真的会响**的音符盒机器：每个音符是一次真正的音符盒演奏，由自研的 **RedPiano** Fabric 模组把音色替换成对应乐器采样，并**以每个玩家为中心**发声，所以音乐会跟着你走、不会因为走远而断掉。

它有两条腿：**绿档全自动**（Minecraft Java **1.21 – 1.21.10** —— 这些版本随仓带有编好的模组 jar，一条命令端到端出活）；以及**工匠路径**（其余任意版本 —— 按 [`docs/VERSION_TACTICS.md`](minecraft-redstone-music/docs/VERSION_TACTICS.md) 手工适配模组 / 采样 / `pack_format`）。

---

## 它能做什么

| 你得到什么 | 说明 |
|---|---|
| **一首 MIDI → 一台会响的机器** | 交给 agent `.mid` + 存档，产出世界里可直接演奏的音符盒机器，无需你手搓红石。 |
| **多乐器音色，不是一个音色到底** | 一张 **103 块 / 5 乐器**采样映射，把 MIDI 各分轨对应到不同乐器音色。 |
| **主旋律不被伴奏埋掉** | pad / lead / bass 采样会盖住旋律；对每个旋律音**逐音 `stopsound` 截断**（精确到具体音效事件），让主旋律浮上来。 |
| **多种机型任你选** | `swave`（行进脉冲波，游戏内多次实测的推荐机型）/ `inplace`（原地调色板，占地极小）/ `straight`（直线）/ `custom`（自定义走线）/ `multilane`（多轨共享时间轴）。 |
| **浏览器可视化设计器** | `layout_designer.html`（加载真 MIDI + 路线播放头 + 多轨 / 侧视图，导出参数 JSON）与 `particle_editor.html`（粒子编辑）。 |
| **一个版本号自适应** | `--mc-version` 自动同步 `pack_format`、数据包文件夹单复数、`pack.mcmeta` 形态、告示牌 sign 方言（1.21.5+ 走 SNBT）。 |
| **播前预检 + 没声体检** | `midi_report.py` 播前预检（时长 / 乐器分布 / 掉音估计 / 占地估计 + 一句话选型建议）；`doctor.py` 一键体检整条「没声」链路，逐项 ✓/✗ + 修复建议。 |
| **一键安装器，双击即装，回执确认** | 在工作区构建到 `dist/`，产出原生 `DEPLOY_TO_GAME.bat`（你双击安装）+ 部署回执，根治「AI 在沙箱里部署、真游戏读不到」的静默失败（见 [`docs/RUNTIME_SANDBOX.md`](minecraft-redstone-music/docs/RUNTIME_SANDBOX.md)）。 |

---

## 快速开始

### 前置

- **仅支持 Windows 交付。** 安装器是 `.bat` 脚本，交付链目前只覆盖 Windows。
- **必须整仓 clone 使用。** 脚本依赖仓库结构（如 `../binaries/` 里的模组 jar）——**不要**只单独拷 `minecraft-redstone-music/` 子目录，那样会缺依赖。
- **Minecraft Java Edition**（**不是**基岩版 —— 数据包、`/function`、`/tick rate`、Fabric 模组在基岩版都不存在）。
- **Fabric Loader + Fabric API + JDK 21**（模组运行依赖）。Loader 安装见官方安装器：<https://fabricmc.net/use/installer/>。
- **Python 3.8+**：`pip install -r minecraft-redstone-music/requirements.txt`（核心只依赖 `mido`）。若 pip 报 UnicodeDecodeError，先执行 `$env:PYTHONUTF8=1`（PowerShell）/ `export PYTHONUTF8=1`（bash）再重试。
- 存档需开**作弊 / OP**（`/reload`、`/tick rate`、`/function` 需要）。

> ⚠️ **乐器采样不随仓分发。** 成品采样资源包 `qzpno_mv.zip`**不在本仓库**里 —— 请自备（见下方[采样与署名](#采样与署名)）。随仓的运行时二进制只有 **11 颗自编 RedPiano 模组 jar**（绿档 1.21 – 1.21.10）与 **Fabric API jar**（Apache-2.0）。详见 [`minecraft-redstone-music/BINARIES.md`](minecraft-redstone-music/BINARIES.md)。

### 🟢 绿档路径（golden 命令，照抄可跑）

在**仓库根目录**整仓 clone 之后，进入 `minecraft-redstone-music/`（这样 `../binaries/…` 能解析到随仓模组 jar），分两步：

**第一步 —— 解析出版本匹配的模组 jar**（把它作为 `--prebuilt-mod-jar` 传给第二步）：

```bash
# 挑选并校验绿档模组 jar，落到仓库的 binaries/ 目录
python scripts/fetch_binaries.py --mc-version 1.21.8
# → 产物路径: ../binaries/redpiano-1.0.0-mc1.21.8.jar
```

**第二步 —— 端到端准备数据包 + 资源包 + 模组，产出安装器**。

采样参数**三选一**（下面示例用第一种，另两种在注释里）：

<details open>
<summary><b>PowerShell</b>（反引号续行）</summary>

```powershell
python scripts/prepare_all.py `
    --midi "path/to/song.mid" `
    --form swave `
    --ns mysong `
    --origin 0 0 255 `
    --mc-version 1.21.8 `
    --world-dir "<profile>/saves/<world>/datapacks" `
    --profile-dir "<profile>" `
    --dist dist `
    --prebuilt-mod-jar "../binaries/redpiano-1.0.0-mc1.21.8.jar" `
    --samples-root "path/to/your/samples"
# 采样三选一（上一行任选其一）:
#   --samples-root "path/to/your/samples"    你自备的采样目录(内含 samples_manifest_*.json + samples_<inst>/), 脚本现打 qzpno_mv.zip
#   --prebuilt-rp  "path/to/qzpno_mv.zip"    你已有的现成采样资源包, 直接复制
#   --skip-resourcepack                      不打资源包: 世界端没装匹配资源包时 = 原版音符盒音色 或 静音(不保证出你要的采样音色)
```

</details>

<details>
<summary><b>bash</b>（反斜杠续行）</summary>

```bash
python scripts/prepare_all.py \
    --midi "path/to/song.mid" \
    --form swave \
    --ns mysong \
    --origin 0 0 255 \
    --mc-version 1.21.8 \
    --world-dir "<profile>/saves/<world>/datapacks" \
    --profile-dir "<profile>" \
    --dist dist \
    --prebuilt-mod-jar "../binaries/redpiano-1.0.0-mc1.21.8.jar" \
    --samples-root "path/to/your/samples"
# 采样三选一（上一行任选其一）:
#   --samples-root "path/to/your/samples"    你自备的采样目录(内含 samples_manifest_*.json + samples_<inst>/), 脚本现打 qzpno_mv.zip
#   --prebuilt-rp  "path/to/qzpno_mv.zip"    你已有的现成采样资源包, 直接复制
#   --skip-resourcepack                      不打资源包: 世界端没装匹配资源包时 = 原版音符盒音色 或 静音(不保证出你要的采样音色)
```

</details>

- `--origin` 顺序是 **X Z Y**（不是 F3 显示的 X Y Z）。`--samples-root` 指向**你自备**的采样目录 —— 仓库里**不含**成品采样。
- 产物在工作区 `dist/`（数据包 + `qzpno_mv.zip` + `mods/*.jar`）+ 原生安装器 `dist/DEPLOY_TO_GAME.bat`。脚本**不碰**你的游戏目录 —— 由**你本人在资源管理器里双击** `DEPLOY_TO_GAME.bat` 安装，再用 `python scripts/deploy_bundle.py --verify dist` 确认 `✓ INSTALLED`。
- 装好后在游戏里手动 `/tick rate 80`、确认资源包已在游戏内启用，再演奏。完整清单（含「没声？先跑 doctor」排查框）见 [`minecraft-redstone-music/QUICKSTART.md`](minecraft-redstone-music/QUICKSTART.md)。

### 🔨 工匠路径（任意版本）

目标版本落在绿档之外（远古 / 未来新版）时，按 [`minecraft-redstone-music/docs/VERSION_TACTICS.md`](minecraft-redstone-music/docs/VERSION_TACTICS.md) 手工适配：重编对应版本的模组、按 `--mc-version` 调 `pack_format` / 文件夹 / sign 方言、必要时换采样。

---

## 采样与署名

本仓库**不分发成品采样包**。各乐器采样的来源与许可如下 —— 若你自备并分发采样包，**须遵守各自许可**：

- **钢琴 —— Salamander Grand Piano**：**CC BY**，**需署名**（这是本项目当前**待落实的义务**：分发时请在你的资源包 / 说明里给出对 Salamander Grand Piano 作者的署名）。
- **鼓组 —— VCSL**：**CC0**（公有领域，无署名义务）。
- **bass / lead / pad**：**合成音色**（脚本生成，非采样上游作品）。

从采样目录现打资源包、或从你已有的 `qzpno_mv.zip` 派生版本匹配包的具体命令，见 [`minecraft-redstone-music/BINARIES.md`](minecraft-redstone-music/BINARIES.md) 与 `scripts/build_resourcepack.py --help`。

---

## 文档

| 文档 | 内容 |
|---|---|
| [`minecraft-redstone-music/SKILL.md`](minecraft-redstone-music/SKILL.md) | skill 主入口：agent 该怎么问、怎么选型、怎么一步步交付。 |
| [`minecraft-redstone-music/QUICKSTART.md`](minecraft-redstone-music/QUICKSTART.md) | 从 `.mid` 到游戏里响的端到端清单 + 「没声」三步排查。 |
| [`minecraft-redstone-music/BINARIES.md`](minecraft-redstone-music/BINARIES.md) | 两类运行时二进制（模组 jar / 采样资源包）从哪来、怎么解析、许可归属。 |
| [`minecraft-redstone-music/docs/VERSION_TACTICS.md`](minecraft-redstone-music/docs/VERSION_TACTICS.md) | 版本战术：绿档之外任意版本怎么手工适配。 |
| [`minecraft-redstone-music/docs/CONTRACT.md`](minecraft-redstone-music/docs/CONTRACT.md) | 设计器 → 生成器的参数契约（导出 JSON 的 schema）。 |
| [`minecraft-redstone-music/docs/MOD_ARCHITECTURE.md`](minecraft-redstone-music/docs/MOD_ARCHITECTURE.md) | RedPiano Fabric 模组架构：音色替换 + 以玩家为中心发声。 |
| [`minecraft-redstone-music/docs/FEATURE_MATRIX.md`](minecraft-redstone-music/docs/FEATURE_MATRIX.md) | 权威能力矩阵：5 种机型 / 各特性的状态与边界。 |
| [`minecraft-redstone-music/docs/RUNTIME_SANDBOX.md`](minecraft-redstone-music/docs/RUNTIME_SANDBOX.md) | 沙箱交付：为什么必须工作区构建 + 原生 `.bat` + 回执握手。 |
| [`docs/history/`](docs/history/) | 开发过程记录（继承分析 / 可行性调研 / 开发日记等，可能与当前实现矛盾，仅作留档）。 |

> 目录导览：`poc/` = 开发期实验脚本，**普通使用者请忽略**；日常使用只需 `minecraft-redstone-music/`。

---

## 关于

由 [Cohen](https://cohenjikan.com) 设计并把关方向，**主要代码由 Anthropic 的 Claude 编写处理**（vibecoding）。完整的人机协作开发史留档在 [`docs/history/`](docs/history/)。这也是我一系列**非商业、源码公开**项目中的一个 —— 更多见 **[cohenjikan.com](https://cohenjikan.com)** 与 GitHub **[@Cohenjikan](https://github.com/Cohenjikan)**。

---

## 开源致谢

- **Fabric API** —— RedPiano 模组的运行依赖（[Apache-2.0](https://github.com/FabricMC/fabric)），jar 随仓分发。
- **Salamander Grand Piano** —— 钢琴采样（**CC BY**，需署名）；**VCSL** —— 鼓组采样（**CC0**）。
- **[mido](https://github.com/mido/mido)** —— MIDI 解析。
- **Minecraft / Mojang** —— 音符盒、红石、数据包、`/function` 与 `/tick rate` 这套可编程世界本身。
- **红石音乐社区 / RedPiano 思路** —— 「用真·音符盒重新演奏、而非回放原曲」的方向来自这个社区的探索。
- **开发协作** —— 主要代码由 **Anthropic 的 Claude** 编写处理（vibecoding）。

---

## 许可

代码以 **[PolyForm Noncommercial 1.0.0](LICENSE)** 许可发布 —— **源码公开、仅限非商业使用**；商用授权请联系作者。随仓的 **RedPiano 模组 jar** 同样按 PolyForm NC 授权；**Fabric API jar** 按其自身的 **Apache-2.0** 再分发。

**乐器采样各自保留上游许可，且不随仓分发** —— 钢琴为 **Salamander Grand Piano（CC BY，需署名）**，鼓组 **VCSL 为 CC0**，bass / lead / pad 为**合成音色**。你自行获取采样并遵守其许可；分发采样包时请落实 Salamander 的署名义务。歌曲 MIDI 及其衍生数据的版权归原作者，不包含在本仓库中。详见 [`LICENSE`](LICENSE) 与 [`minecraft-redstone-music/BINARIES.md`](minecraft-redstone-music/BINARIES.md)。

<div align="center">
<sub>把任意一首 MIDI，在 Minecraft 里用真·音符盒演奏出来。</sub>
</div>
