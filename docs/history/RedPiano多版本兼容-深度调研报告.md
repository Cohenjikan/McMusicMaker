# RedPiano 多版本兼容深度调研报告

调研日期：2026-07-03  
范围：按 `RedPiano多版本兼容-深度调研任务书.md` 查证 D-1 至 D-8。未改仓库代码。

## 总结

“只能兼容 1.21”不是技术死墙。更准确的裁定是：

- 原版 tick80 路线的硬下限仍是 **1.20.3**，因为 1.20.2 及以下没有原版 `/tick rate`。
- B-1（1.20.5/1.20.6）收益/成本比最高，但不是零改动：scoreboard API 已兼容，声音 API 基本兼容，主要需要把 `ResourceLocation.parse(...)` 换成 1.20.x 可用写法。
- B-2（1.20.3/1.20.4）也比任务书预估更乐观：scoreboard 新 API 在 1.20.3 已存在，不需要回退到旧 scoreboard API；仍需 Java 17、工具链行、格式行、实听。
- B-3（1.14-1.20.2）技术上可借 Carpet `/tick rate` 接近 tick80 语义，但产品形态会变成“RedPiano + Carpet 双 mod”，维护与验证成本显著上升。
- B-4（无 mod/无资源包、tick20 原版降档）仍是“通用 skill”叙事下最稳的战略选项。
- B-5（Stonecutter）暂不建议为 ≤10 个额外版本引入，除非决定长期维护 1.14-1.21 多版本发布线。

## D-1 记分板 API 分水岭

结论：`ScoreHolder` / `ReadOnlyScoreInfo` / `Scoreboard#getPlayerScoreInfo(ScoreHolder,Objective)` 的 Mojang 映射分水岭是 **1.20.3**，不是 1.20.5，也不是 1.21。

证据：

- Mojang 官方 `server_mappings`：
  - 1.20.2：无 `ScoreHolder`、无 `ReadOnlyScoreInfo`、无 `getPlayerScoreInfo`；旧签名是 `getOrCreatePlayerScore(String,Objective)`。
  - 1.20.3：出现 `ScoreHolder`、`ReadOnlyScoreInfo`、`getPlayerScoreInfo(ScoreHolder,Objective)`。
  - 1.20.4、1.20.5、1.20.6、1.21：同一组 API 持续存在。
- 对照源：
  - Mojang version manifest: <https://piston-meta.mojang.com/mc/game/version_manifest_v2.json>
  - 1.20.2 server mappings: <https://piston-data.mojang.com/v1/objects/dced504a9b5df367ddd3477adac084cea8024ba4/server.txt>
  - 1.20.3/1.20.4 server mappings: <https://piston-data.mojang.com/v1/objects/c1cafe916dd8b58ed1fe0564fc8f786885224e62/server.txt>
  - 1.20.5 server mappings: <https://piston-data.mojang.com/v1/objects/14be97974a77b09eb8bca88ed9268445f0fde3e7/server.txt>
  - 1.20.6 server mappings: <https://piston-data.mojang.com/v1/objects/9e96100f573a46ef44caab3e716d5eb974594bb7/server.txt>
  - 1.21 server mappings: <https://piston-data.mojang.com/v1/objects/31c77994d96f05ba25a870ada70f47f315330437/server.txt>
  - mappings.dev 1.20.4 `ReadOnlyScoreInfo`: <https://mappings.dev/1.20.4/net/minecraft/world/scores/ReadOnlyScoreInfo.html>
  - mappings.dev 1.20.6 `Scoreboard`: <https://mappings.dev/1.20.6/net/minecraft/world/scores/Scoreboard.html>

对 B 阶梯影响：

- **确认并上调 B-1**：1.20.5/1.20.6 不需要 scoreboard 回退。
- **修正 B-2**：1.20.3/1.20.4 也不需要旧 scoreboard API 改写；B-2 成本从“中”降到“小-中”，真正成本来自 Java/toolchain/实听。

## D-2 声音 API

结论：

- 1.20.x 全线存在 `Level.playSeededSound(Player, Entity, Holder<SoundEvent>, SoundSource, float, float, long)`。
- 1.19.3 起存在 `Holder<SoundEvent>` 版实体锚定重载和 `SoundEvent.createVariableRangeEvent(ResourceLocation)`。
- 1.19.0-1.19.2 只有裸 `SoundEvent` 版实体锚定重载；无 `createVariableRangeEvent`。
- `ResourceLocation.parse(String)` 是 **1.21** 才出现；1.20.6 及以下应使用 `new ResourceLocation(String)` 或 `ResourceLocation.tryParse(String)`。

证据：

- Mojang `server_mappings` 中的 `Level#playSeededSound`：
  - 1.19/1.19.1/1.19.2：`playSeededSound(Player, Entity, SoundEvent, SoundSource, float, float, long)`。
  - 1.19.3/1.19.4/1.20.x/1.21：`playSeededSound(Player, Entity, Holder, SoundSource, float, float, long)`。
- `SoundEvent`：
  - 1.19.2：有 `SoundEvent(ResourceLocation)` 构造器，无 `createVariableRangeEvent`。
  - 1.19.3+：有 `createVariableRangeEvent(ResourceLocation)`。
- `ResourceLocation`：
  - 1.19.2-1.20.6：有 `tryParse(String)` 和字符串构造器。
  - 1.21：新增 `parse(String)`、`fromNamespaceAndPath(...)`、`withDefaultNamespace(...)`。
- 对照源同 D-1 的 Mojang `server_mappings`，另见：
  - mappings.dev 1.21 `Level`: <https://mappings.dev/1.21/net/minecraft/world/level/Level.html>
  - mappings.dev 1.21 `ResourceLocation`: <https://mappings.dev/1.21/net/minecraft/resources/ResourceLocation.html>

旧版替代写法：

- 1.20.3-1.20.6：`Holder.direct(SoundEvent.createVariableRangeEvent(new ResourceLocation(e.sound)))`。
- 1.19.3-1.20.2：同上，但仍受 tickrate/Carpet 方案影响。
- 1.19.0-1.19.2：需要裸 `SoundEvent` 路线，例如 `new SoundEvent(new ResourceLocation(e.sound))`，并调用裸 `SoundEvent` 重载。

对 B 阶梯影响：

- **修正 B-1**：不是零改动；至少要处理 `ResourceLocation.parse`。
- **确认 B-2 可控**：声音播放主重载可用，1.20.3/1.20.4 仍只需 `ResourceLocation` 写法兼容。
- **B-3 成本确认较大**：1.19.0-1.19.2 需要声音构造/播放路线分支。

## D-3 mixin 目标稳定性

结论：

- `NoteBlock.triggerEvent(BlockState, Level, BlockPos, int, int)` 从 1.14.4 到 1.21 签名稳定。
- `NoteBlock.NOTE` 从 1.14.4 到 1.21 一直是 `IntegerProperty`。
- `NoteBlock.getPitchFromNote(int)` 在 **1.20** 出现；1.19.4 及以下没有，需要内联 `2^((note-12)/12)`。

证据：

- Mojang `server_mappings`：
  - 1.14.4、1.15.2、1.16.5、1.17.1、1.18.2：有 `triggerEvent(...)` 和 `IntegerProperty NOTE`，无 `getPitchFromNote`。
  - 1.19.4：仍无 `getPitchFromNote`。
  - 1.20、1.20.1、1.20.2、1.20.3、1.20.6、1.21：有 `float getPitchFromNote(int)`。
- 对照源：
  - 1.20.6 `NoteBlock`: <https://mappings.dev/1.20.6/net/minecraft/world/level/block/NoteBlock.html>
  - 1.21 `NoteBlock`: <https://mappings.dev/1.21/net/minecraft/world/level/block/NoteBlock.html>

对 B 阶梯影响：

- **确认 mixin 目标本身很稳**，但每个版本仍必须进游戏实听。
- **B-1/B-2 不受 `getPitchFromNote` 阻碍**。
- **B-3 中 1.19.4 及以下需要音高公式分支**。

## D-4 Fabric API 下限

结论：`ServerTickEvents.END_SERVER_TICK` 至少在 Fabric API `0.28.5+1.14` 中已存在，覆盖 1.14 线。Fabric lifecycle event 不是 1.14-1.20.6 的主要阻碍。

证据：

- Fabric API Javadoc：
  - `0.28.5+1.14` `ServerTickEvents`: <https://maven.fabricmc.net/docs/fabric-api-0.28.5+1.14/net/fabricmc/fabric/api/event/lifecycle/v1/ServerTickEvents.html>
  - `0.42.0+1.16`: <https://maven.fabricmc.net/docs/fabric-api-0.42.0+1.16/net/fabricmc/fabric/api/event/lifecycle/v1/ServerTickEvents.html>
  - `0.77.0+1.18.2`: <https://maven.fabricmc.net/docs/fabric-api-0.77.0+1.18.2/net/fabricmc/fabric/api/event/lifecycle/v1/ServerTickEvents.html>
  - `0.100.8+1.20.6`: <https://maven.fabricmc.net/docs/fabric-api-0.100.8+1.20.6/net/fabricmc/fabric/api/event/lifecycle/v1/ServerTickEvents.html>

对 B 阶梯影响：

- **确认**：B-3 的主要成本不是 lifecycle event，而是 tickrate、声音 API、音高辅助函数、工具链和实听。

## D-5 1.20.x 工具链矩阵

结论：对本机 Gradle 9.2.1，不建议回退到 Loom 1.7/1.8 era。建议先用现代 Loom 精确版 `1.10.5` 做 1.20.x 端口尝试；它的 Gradle module metadata 标注 `org.gradle.plugin.api-version=8.12`、`org.gradle.jvm.version=17`，比 1.11.8 更适合同时覆盖 1.20.3/1.20.4 的 Java 17 目标。1.11.8 标注 Gradle API 8.14、JVM 21，可作为 1.20.5+ 备选，但没必要先引入。

推荐 `MOD_TOOLCHAIN` 形态（需真实 build + `--check-jar` + 实听后才能算 verified）：

| MC | loom | fabric-loader 下限 | fabric-api | Java target | 备注 |
|---|---:|---:|---|---:|---|
| 1.20 | 1.10.5 | >=0.14.21 | 0.83.0+1.20 | 17 | red：无原版 `/tick rate`，仅 B-3/Carpet 或 tick20 |
| 1.20.1 | 1.10.5 | >=0.16.10 | 0.92.9+1.20.1 | 17 | red：无原版 `/tick rate`；选最新 API 会抬高 loader 下限 |
| 1.20.2 | 1.10.5 | >=0.14.22 | 0.91.6+1.20.2 | 17 | red：无原版 `/tick rate` |
| 1.20.3 | 1.10.5 | >=0.14.23 | 0.91.1+1.20.3 | 17 | yellow：原版 tick80 起点；API 小改 |
| 1.20.4 | 1.10.5 | >=0.15.1 | 0.97.3+1.20.4 | 17 | yellow：与 1.20.3 同类 |
| 1.20.5 | 1.10.5 | >=0.15.6 | 0.97.8+1.20.5 | 21 | B-1；改 `ResourceLocation.parse` |
| 1.20.6 | 1.10.5 | >=0.15.6 | 0.100.8+1.20.6 | 21 | B-1；改 `ResourceLocation.parse` |

证据：

- Fabric API Maven metadata: <https://maven.fabricmc.net/net/fabricmc/fabric-api/fabric-api/maven-metadata.xml>
- Fabric API jar `fabric.mod.json` 依赖：
  - `0.83.0+1.20`: fabricloader `>=0.14.21`, java `>=17`
  - `0.92.9+1.20.1`: fabricloader `>=0.16.10`, java `>=17`
  - `0.91.6+1.20.2`: fabricloader `>=0.14.22`, java `>=17`
  - `0.91.1+1.20.3`: fabricloader `>=0.14.23`, java `>=17`
  - `0.97.3+1.20.4`: fabricloader `>=0.15.1`, java `>=17`
  - `0.97.8+1.20.5`: fabricloader `>=0.15.6`, java `>=21`
  - `0.100.8+1.20.6`: fabricloader `>=0.15.6`, java `>=21`
- Fabric Loom metadata:
  - `1.10.5`: <https://maven.fabricmc.net/net/fabricmc/fabric-loom/1.10.5/fabric-loom-1.10.5.module>
  - `1.11.8`: <https://maven.fabricmc.net/net/fabricmc/fabric-loom/1.11.8/fabric-loom-1.11.8.module>
- Fabric Meta API for mappings/loader discovery:
  - Yarn 1.20.6 example: <https://meta.fabricmc.net/v2/versions/yarn/1.20.6>
  - Loader 1.20.6 example: <https://meta.fabricmc.net/v2/versions/loader/1.20.6>

对 B 阶梯影响：

- **B-1/B-2 工具链可落地**，但必须按版本 build，不应指望一个 jar 横跨版本。
- **1.20.5/1.20.6 要 Java 21**；1.20.3/1.20.4 runtime 仍是 Java 17 目标。

## D-6 Carpet 方案可行性

结论：Carpet 方案可行，但它改变产品边界：B-3 不再是“RedPiano Fabric mod + 数据/资源包”，而是“RedPiano + Carpet + 数据/资源包”。`/tick rate` 语义上会改变服务器 tick 间隔，因此 `/schedule` 和红石计时这类以 game tick 推进的系统会随之加速；这与原版 1.20.3+ `/tick rate 80` 的目标语义接近。但必须实听，并要接受全服务器加速副作用。

版本可用性证据：

- 官方 GitHub Releases（gnembon/fabric-carpet）：
  - 1.14.4：`v1.14.4-thunder` / `v1.1-scorcher`
  - 1.15.2：`v1.3-frozen` / `v1.4-homebound`
  - 1.16.5：1.4.23+ 系列
  - 1.17.1：1.4.42+ 系列
  - 1.18.2：1.4.66+ 系列
  - 1.19.2：1.4.83/1.4.84
  - 1.19.4：1.4.100/1.4.101
  - 1.20/1.20.1：1.4.112
  - 1.20.2：1.4.118/1.4.119/1.4.121
- Releases: <https://github.com/gnembon/fabric-carpet/releases>

语义证据：

- Carpet 旧版 `TickSpeed.tickrate(rate)` 设置 `mspt = 1000 / tickrate`；新版通过 `ServerTickRateManager#setTickRate`。
- Carpet `MinecraftServer_tickspeedMixin` 将 vanilla 服务器主循环中的固定 50ms tick 等待替换为 Carpet 的 `mspt`，并在 warp 时尽量连续 tick。
- 源码：
  - 1.20.2 `TickSpeed.java`: <https://raw.githubusercontent.com/gnembon/fabric-carpet/1.4.121/src/main/java/carpet/helpers/TickSpeed.java>
  - 1.20.2 `TickCommand.java`: <https://raw.githubusercontent.com/gnembon/fabric-carpet/1.4.121/src/main/java/carpet/commands/TickCommand.java>
  - 1.20.2 `MinecraftServer_tickspeedMixin.java`: <https://raw.githubusercontent.com/gnembon/fabric-carpet/1.4.121/src/main/java/carpet/mixins/MinecraftServer_tickspeedMixin.java>
  - 1.14.4 `TickSpeed.java`: <https://raw.githubusercontent.com/gnembon/fabric-carpet/v1.1-scorcher/src/main/java/carpet/helpers/TickSpeed.java>
- `/schedule` 以 gametick 为单位延迟执行；Java 版 1.14 加入 `/schedule`，1.15 加入 `clear` 和 `append|replace`：<https://minecraft.wiki/w/Commands/schedule>

副作用：

- 全服务器加速：红石、实体、随机刻、AI、函数调度等全部按更短 wall-clock tick 推进。
- 性能风险：若服务器维持不了 80 TPS，音乐速度和触发稳定性会漂移。
- 部署风险：用户必须安装 Carpet，且命令权限/规则配置要纳入安装说明。
- `/tick warp` 不适合音乐实时播放；它是“尽快推进 N tick”，会破坏真实时间听感。B-3 应使用 `/tick rate 80`，不是 warp。

对 B 阶梯影响：

- **确认 B-3 可行，但成本“大”成立**。
- 若产品希望仍称“原版 tick80”，Carpet 路线会削弱叙事；若接受“兼容旧版需 Carpet”，则 B-3 是工程可做项。

## D-7 数据包/资源包格式表（1.14-1.20.6）

结论：`function_folder` 在 1.14-1.20.6 全部是复数 `functions/`，1.21 才改为单数 `function/`。`pack.mcmeta` 在 1.14-1.20.6 仍用单一 `pack_format`。`/schedule` 在 1.14 有基本 syntax，1.15+ 有 `clear` 和 `append|replace`。告示牌 NBT 在 1.20 发生结构性变化。

建议 `_vrow` 风格表：

| MC | dp | rp | function_folder | packmeta | sign 方言 | schedule |
|---|---:|---:|---|---|---|---|
| 1.14-1.14.4 | 4 | 4 | functions | single | Text1-Text4 JSON string | basic |
| 1.15-1.16.1 | 5 | 5 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.16.2-1.16.5 | 6 | 6 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.17-1.17.1 | 7 | 7 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.18-1.18.1 | 8 | 8 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.18.2 | 9 | 8 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.19-1.19.2 | 10 | 9 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.19.3 | 10 | 12 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.19.4 | 12 | 13 | functions | single | Text1-Text4 JSON string | clear/append/replace |
| 1.20-1.20.1 | 15 | 15 | functions | single | front_text.messages JSON string | clear/append/replace |
| 1.20.2 | 18 | 18 | functions | single | front_text.messages JSON string | clear/append/replace |
| 1.20.3-1.20.4 | 26 | 22 | functions | single | front_text.messages JSON string | clear/append/replace |
| 1.20.5-1.20.6 | 41 | 32 | functions | single | front_text.messages JSON string | clear/append/replace |

证据：

- Minecraft Wiki API `Template:Data pack format`：
  - 1.14-1.14.4 dp 4
  - 1.15-1.16.1 dp 5
  - 1.16.2-1.16.5 dp 6
  - 1.17-1.17.1 dp 7
  - 1.18-1.18.1 dp 8
  - 1.18.2 dp 9
  - 1.19-1.19.3 dp 10
  - 1.19.4 dp 12
  - 1.20-1.20.1 dp 15
  - 1.20.2 dp 18
  - 1.20.3-1.20.4 dp 26
  - 1.20.5-1.20.6 dp 41
  - 1.21 dp 48 includes legacy folder rename to singular `function/`
  - API URL: <https://minecraft.wiki/api.php?action=parse&page=Template%3AData%20pack%20format&prop=wikitext&format=json>
- Minecraft Wiki API `Template:Resource pack format`:
  - 1.14-1.14.4 rp 4
  - 1.15-1.16.1 rp 5
  - 1.16.2-1.16.5 rp 6
  - 1.17-1.17.1 rp 7
  - 1.18-1.18.2 rp 8
  - 1.19-1.19.2 rp 9
  - 1.19.3 rp 12
  - 1.19.4 rp 13
  - 1.20-1.20.1 rp 15
  - 1.20.2 rp 18
  - 1.20.3-1.20.4 rp 22
  - 1.20.5-1.20.6 rp 32
  - API URL: <https://minecraft.wiki/api.php?action=parse&page=Template%3AResource%20pack%20format&prop=wikitext&format=json>
- `/schedule` syntax and history: <https://minecraft.wiki/w/Commands/schedule>
- Sign NBT:
  - Sign page says pre-1.20 uses `Text1`-`Text4`; current format uses `front_text.messages` and `back_text`: <https://minecraft.wiki/w/Sign>
  - Data pack format 15 explicitly notes 1.20 sign NBT changed from `Text1` to `front_text.messages[0]`.

对 B 阶梯影响：

- **B-1/B-2 的数据/资源包格式行直接可加**。
- **B-3 可表驱动**，但 sign 方言和 schedule 1.14 差异要显式分支。

## D-8 Stonecutter 评估

结论：Stonecutter 适合长期、多 loader、多版本、差异源较多的 Minecraft mod；对当前 RedPiano 110 行 Fabric-only mod，短期不值得先引入。若未来决定维护 1.14-1.21 长线，或 B-3 变成正式产品线，再考虑 B-5。

证据：

- Stonecutter README：定位为 “multi-version environment manager”，主要面向 Loom-based Fabric Java 项目，并提供 IntelliJ 插件辅助切换版本。仓库：<https://github.com/stonecutter-versioning/stonecutter>
- Blahaj README：定位为 “Fully automated Gradle plugin for managing multiversion Minecraft mods, built on Stonecutter”。仓库：<https://github.com/axlecoffee/blahaj>
- Stonecraft README：定位为减少 multi-loader/multi-version Minecraft mod workspace 样板代码，基于 Stonecutter + Architectury。仓库：<https://github.com/meza/Stonecraft>

对 RedPiano 的收益：

- 能把 1.20.3/1.20.4、1.20.5/1.20.6、1.21.x 的版本差异集中管理。
- 适合后续自动产多版本 jar、自动切换 active version、减少手工改 Gradle 数字。

对 RedPiano 的成本：

- 需要改造 Gradle 布局、settings、source set/版本目录或预处理注释。
- 需要维护 Stonecutter active version 和 IDE/Gradle 工作流。
- 对 110 行 mod 来说，当前实际差异点只有：
  - `ResourceLocation.parse` vs constructor/tryParse
  - 1.19.4- `getPitchFromNote` fallback
  - 1.19.2- bare `SoundEvent`
  - 可能的 toolchain/fabric.mod.json 版本号

对 B 阶梯影响：

- **B-5 暂缓**。
- 若只做 B-1/B-2，建议用少量版本分支/小 helper，而不是引入 Stonecutter。
- 若正式做 B-3 全覆盖，再重新评估 B-5。

## 一页决策建议

如果只做一档，先做 **B-1：1.20.5/1.20.6**。

理由：

- 用户收益明确：把兼容线从 1.21.x 下探到 1.20.5/1.20.6。
- 技术改动极小：scoreboard API 已存在，声音 Holder 重载已存在；主要修 `ResourceLocation.parse`。
- 工具链清晰：Java 21、Fabric API 精确版本已查明、Loom 可复用现代版本。
- 仍需每版本实听，但只新增两个版本，维护成本可控。

推荐执行顺序：

1. 做 B-1：给 1.20.5/1.20.6 加 `VERSION_TABLE`、`MOD_TOOLCHAIN` 行；mod 内抽一个 `resourceLocation(String)` 兼容点；分别 build + `--check-jar` + 实听。
2. 顺手做 B-2 的预研构建：1.20.3/1.20.4 由于 scoreboard 已兼容，成本低于原预估；但 Java 17 和真实运行验证单独处理。
3. 不急于做 B-3：只有当“旧版覆盖”是明确产品目标时，再引入 Carpet 路线。
4. 将 B-4 作为独立产品叙事：`vanilla/tick20/basic-note-block` 模式，而不是 RedPiano 的向后兼容补丁。
5. 暂缓 B-5：等 B-1/B-2 完成后，如果版本矩阵继续扩张，再上 Stonecutter。

最终裁定：

- **短期工程最优：B-1。**
- **低悬果加做：B-2。**
- **战略通用版：B-4。**
- **大版本长线维护：B-3 + 可能的 B-5。**
