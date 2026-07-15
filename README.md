<div align="center">

# McMusicMaker · 红石音乐机

把一首歌交给 AI agent，在 Minecraft 里搭成一台真正会演奏的音符盒红石机器。

**你不用会写代码，也不用自己研究红石。告诉 agent 你想要什么，它会带着你一步步完成。**

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/License-PolyForm%20Noncommercial%201.0.0-orange.svg?style=flat-square)](LICENSE)
[![Minecraft: Java 1.21–1.21.10](https://img.shields.io/badge/Minecraft-Java%201.21%E2%80%931.21.10-62B47A.svg?style=flat-square)](minecraft-redstone-music/docs/VERSION_TACTICS.md)
[![Windows](https://img.shields.io/badge/交付-Windows-4B8BF5.svg?style=flat-square)](#开始前准备)

</div>

---

## 它能做什么？

你给 agent 一首 MIDI（也可以先给 MP3）和一个 Minecraft 存档，它会：

- 分析歌曲，判断适合哪种红石机器；
- 把不同声部安排成钢琴、贝斯、主音、铺底和鼓；
- 生成数据包、资源包和需要的模组；
- 给你一个可以双击安装的文件；
- 告诉你进游戏后该输入什么命令、按哪个按钮播放。

最终听到的不是直接播放原曲音频，而是 Minecraft 世界里的**真实音符盒和红石线路在演奏**。

## 最简单的使用方法

### 1. 把整个项目交给 agent

下载或 clone **完整仓库**，然后用 Codex、Claude Code 或其他可以读写文件的 agent 打开这个文件夹。

> 不要只复制 `minecraft-redstone-music` 子文件夹，完整仓库里还有运行所需的文件。

### 2. 准备三样信息

- 你的歌曲文件：最好是 `.mid`；只有 `.mp3`、`.wav` 或 `.flac` 也可以先问 agent。
- 你的 Minecraft **Java 版**版本，例如 `1.21.8`。
- 你的存档文件夹。实在找不到也没关系，让 agent 帮你找。

如果你已经知道机器要建在哪里，再告诉 agent 游戏 F3 画面上的 `X / Y / Z` 坐标。第一次尝试建议使用创造模式测试存档，并提前备份。

### 3. 复制这段话发给 agent

```text
请使用这个仓库里的 minecraft-redstone-music skill，帮我把一首歌做成 Minecraft 红石音乐机。

我的 Minecraft 是 Java 版，版本是【填写版本】。
歌曲文件在【填写 MIDI 路径，或直接附上文件】。
存档在【填写存档路径；不知道就先帮我找】。

我不懂技术参数。请先检查歌曲，再用中文告诉我适合哪种机器、预计占地多大，并替我选择推荐方案。先不要假设已经安装成功；需要我双击文件或进入游戏操作时，请明确提醒我。
```

然后正常回答 agent 的问题即可。你不需要先读其他 `.md` 文档，也不需要自己拼命令。

## 选择你喜欢的机器

McMusicMaker 有 5 种机型。你可以自己选，也可以让 agent 分析歌曲后推荐：

| 机型 | 它是什么样 | 适合谁 | 需要注意 |
|---|---|---|---|
| **原地紧凑型** (`inplace`) | 所有音符集中在一个小型调色板中演奏，不铺设很长的线路 | 长歌曲、小场地、只想稳定听歌 | 占地最小，但看不到脉冲沿整条线路前进 |
| **S 形折线型** (`swave`) | 红石线路来回折叠成 S 形，播放时脉冲会沿线路移动 | 想兼顾观赏性和占地的用户 | 线路会随歌曲变长；歌曲越长，占地和性能压力越大 |
| **直线型** (`straight`) | 把整首歌沿一条直线铺开，结构最直观 | 短歌、教学展示、拥有超长空地的世界 | 通常占地最长，很容易穿过已有建筑或地形 |
| **自定义路线** (`custom`) | 在可视化设计器里自己画路线，让机器绕着建筑或景观行进 | 有明确造型想法、愿意自己设计路线的用户 | 需要多一步设计和导出；复杂路线应先检查是否相交或越界 |
| **多轨并行型** (`multilane`) | 不同声部各走一条并行轨道，同一时刻的音符横向对齐 | 想展示歌曲层次、追求大型舞台效果的用户 | 最壮观，也最容易占用大量区块；长歌需要谨慎 |

拿不准时，可以直接对 agent 说：

```text
请先分析 MIDI 的时长、音符密度和预计占地，再对照 README 的机型表推荐两个方案。告诉我各自的尺寸和取舍，等我选择后再生成。
```

还可以追加一句你的偏好，例如“尽量小”“脉冲要看得见”“绕着城堡走”或“不同乐器分轨展示”。

> 只有 MP3、WAV 或 FLAC 时，也可以先交给 agent 转成 MIDI。但音频转录会产生错音和漏音，钢琴独奏通常比人声、多乐器混音更适合转换。

## 进阶用户：两个自定义设计器

仓库里有两个可以直接在浏览器打开的 HTML 工具：

| 工具 | 可以自定义什么 | 交给 agent 什么 |
|---|---|---|
| [`layout_designer.html`](minecraft-redstone-music/designer/layout_designer.html) | 机器线路、形状、尺寸、折叠方式和起点，例如让线路绕着城堡或舞台行进 | 导出的线路参数 JSON |
| [`particle_editor.html`](minecraft-redstone-music/designer/particle_editor.html) | 跟随音乐时间轴安排命令方块、粒子、烟花和其他命令，决定它们在何时、何地触发 | 导出的命令方块关键帧 JSON |

你不需要自己研究 JSON。对 agent 说“带我使用线路设计器”或“我想制作命令方块跟轨”，它应该指导你打开对应 HTML，等你设计完成后再接手构建。

## 开始前准备

目前最顺畅的使用条件是：

- **Windows**；
- **Minecraft Java Edition**，不是基岩版；
- 推荐版本为 **1.21 到 1.21.10**，这些版本支持自动构建；
- 存档已开启作弊，或你在服务器中拥有 OP 权限；
- 愿意在安装模组后重启一次游戏。

更老或更新的 Java 版本也可以让 agent 尝试适配，但步骤会更多，音色和节奏精度也可能不同。基岩版目前不支持。

## 完成时你需要亲手做什么？

agent 完成构建后，会在 `dist` 文件夹里准备一个 `DEPLOY_TO_GAME.bat`。接下来通常只需要：

1. 关闭 Minecraft；
2. 在 Windows 资源管理器中双击 `DEPLOY_TO_GAME.bat`；
3. 重新启动游戏并进入目标存档；
4. 按 agent 给出的顺序启用资源包、输入命令并按下播放按钮。

这一步需要你亲手双击。agent 只有看到安装回执后，才应该告诉你“已经安装”。

> 音乐播放时会把整个世界的 tick rate 提高到 80，农作物、生物和其他红石也会一起加速。听完后按 agent 的提示恢复到 20。共享服务器上请先征得其他玩家同意。

## 游戏内指令表

`<ns>` 是构建时取的命名空间(agent 会告诉你)。控制台按钮和 `/function` 完全等价——按钮只是替你敲了那条命令。swave/直线/自定义与多轨(multilane)按钮同功能、标签略有差异,下表并列写出;inplace(原地紧凑)只有其中一部分按钮。

**① 每次进世界必敲(顺序固定):**

| 指令 | 作用 |
|---|---|
| `/reload` | 注册数据包函数(装包后/改包后敲一次) |
| `/tick rate 80` | **必须手敲**,机器不会自设;不敲=慢 4 倍。听完 `/tick rate 20` 还原 |
| `/function <ns>:setup` | 建机器+控制台(等 "built" 提示;保护壳版用 prosetup 代替) |

**② 控制台按钮(= `/function <ns>:<名字>`):**

| 按钮 | function | 作用 |
|---|---|---|
| [play] / [直接播放] | `play` | 播放全曲(带预加载门禁,区块没热会拒绝并提示) |
| [stop] / [停止] | `stop` | 立停:静音+物理断脉冲(4gt 后自动补回),可立即重播 |
| [overview] / [全景俯视] | `view` | 旁观者俯瞰全机 |
| [preload] | `preload` | 沿线验证式预加载区块(非超平坦世界先按它再 play) |
| [poly gain] / [复音增益] | `cfg/polytoggle` | 大和弦增益开关(防糊) |
| [humanize] / [微抖动] | `cfg/humantoggle` | 人性化微扰开关(去复印感) |
| [音色展台] | `stand` | tp 到实体音色展台(按墙面石按钮试听,勿右键音符盒) |
| [跟拍] | `cam` | **录制用**:骑隐形相机架,play 后与脉冲前沿逐刻锁定(位置可在设计器「跟拍相机」微调) |

**③ 可选手敲:**

| 指令 | 作用 |
|---|---|
| `/function <ns>:camoff` | 中途退出跟拍([stop] 也会自动下架) |
| `/function <ns>:prosetup` | 代替 setup:先建屏障保护壳再建机器(需 params 开 protection) |
| `/function <ns>:unprotect` | 只拆保护壳,机器保留 |
| `/function <ns>:cleanup` | 整机拆除(分段清空+撤 forceload) |

**④ 出问题时的救援:**

| 指令 | 何时用 |
|---|---|
| `/function <ns>:perfoff` | 闪退后 gamerule 没恢复(生物不刷/庄稼不长)时手动还原 |
| `/function <ns>:halt` | 万能复位:停一切状态机、清 schedule、撤相机架(不拆机器) |

**⑤ 其余函数**(`fire`/`tick`/`kill/*`/`cam/*`/`pre/*`/`pro/*` 等)都是内部零件,不要手动调用。

## 常见问题

**会破坏我的存档吗？**

机器会清理并占用建造范围内的方块。请使用空旷区域，第一次先在测试存档尝试，并保留备份。不要让 agent 在没有确认坐标和占地的情况下直接建造。

**为什么默认音色不像真实钢琴？**

默认已经随包提供包含钢琴、贝斯、主音、铺底和鼓的采样资源包。钢琴来自 Salamander Grand Piano；如果听到的是简单合成音色，说明当前使用的是备用 demo 包，可以让 agent 检查并切回随包资源。

**一定要 MIDI 吗？**

不一定，但 MIDI 最可靠。MP3 等音频可以先转录，效果取决于歌曲复杂度。

**能在老版本 Minecraft 使用吗？**

Java 版老版本可以尝试手工适配，但不会像 1.21–1.21.10 一样全自动。让 agent 先说明能做到什么、需要牺牲什么，再决定是否继续。

**为什么退出世界后歌曲变慢了？**

`tick rate 80` 不会永久保存，重新进入世界后需要再次设置。把现象告诉 agent，它会给你正确的命令。

<details>
<summary><strong>给开发者和想深入了解的人</strong></summary>

普通使用不需要阅读以下内容：

- [Skill 完整工作流程](minecraft-redstone-music/SKILL.md)
- [游戏内操作与排错](minecraft-redstone-music/QUICKSTART.md)
- [模组与资源包说明](minecraft-redstone-music/BINARIES.md)
- [不同 Minecraft 版本的适配策略](minecraft-redstone-music/docs/VERSION_TACTICS.md)
- [能力与限制列表](minecraft-redstone-music/docs/FEATURE_MATRIX.md)
- [RedPiano 模组架构](minecraft-redstone-music/docs/MOD_ARCHITECTURE.md)

</details>

## 关于与致谢

项目由 [Cohen](https://cohenjikan.com) 设计并把关方向，主要代码由 Anthropic 的 Claude 协助编写。更多项目见 GitHub [@Cohenjikan](https://github.com/Cohenjikan)。

感谢 Fabric API、mido、Minecraft 红石音乐社区，以及 Salamander Grand Piano、VCSL 等开放音源项目。

## 许可

代码以 [PolyForm Noncommercial 1.0.0](LICENSE) 发布，仅限非商业使用；商用授权请联系作者。

随包资源中的钢琴采样 Salamander Grand Piano v3 由 Alexander Holm 制作，以 CC BY 3.0 授权；署名与来源已写入资源包内的 `CREDITS.txt`。VCSL 鼓组为 CC0；歌曲 MIDI 及衍生数据的版权归原作者。详细说明见 [BINARIES.md](minecraft-redstone-music/BINARIES.md)。

<div align="center">
<sub>把你想听的歌告诉 agent，剩下的交给它。</sub>
</div>
