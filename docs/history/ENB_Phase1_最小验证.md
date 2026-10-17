# ENB Phase 1 · 最小验证记录

> 分支：`enb-hifi-backend`（从 `main@a05e99a` 切出）  
> 日期：2026-07-24  
> 当前裁决：**WAITING — 尚未完成 Minecraft 1.21.1 人耳/人眼验收，禁止进入 Phase 2**

## 1. 本轮范围

只实现一次性探针 `poc/50_enb_probe.py`，不修改 `params_schema`、`build_machine`、
`fetch_binaries`、正式 generators 或 Family A。它生成独立诊断数据包，覆盖：

1. 钢琴、贝斯、弦乐、失真吉他、鼓组五类音色；
2. velocity、sustain、fade、delay；
3. 同 tick 12 音和弦（重复三轮）；
4. 直接写入 `SoundPath` / `PitchBendPoints` 的高级 NBT canary；
5. 保留精确 GM program/channel 的 MIDI 短片段；
6. ENB 钢琴与 RedPiano/Salamander 三层钢琴的随机标签 A/B 初筛；
7. 64 近场听感，以及 256 / all 分级的大规模方块与同 tick 性能压力测试。

此实现是 Phase 1 诊断工具，不是 ENB 正式后端。

## 2. 官方版本与校验

| 项 | 固定值 |
|---|---|
| Minecraft | `1.21.1` |
| ENB | `v1.9.1` |
| Modrinth version ID | `XYPff5nL` |
| 文件 | `extendednoteblock-1.9.1+1.21.1.jar` |
| 大小 | `21,128,320` bytes |
| SHA-256（本地下载复算） | `9fdf1f9464c824f7e7dbd4d964a6fe2e86fd52ba0379103feeb020ee603cc646` |
| SHA-512（与 Modrinth API 一致） | `7bfc06905c326ebd848fd48b626a66dd10e288a7ca412a4b52a0b707bea0837236882a41d7436279ee20324abafa3cc1b156119775e51f39ab12144389498647` |
| 官方源码核对 commit | `9c902c2071e704dfc2aa71e72909205c381244a7` |
| 官方下载 | <https://cdn.modrinth.com/data/JL9ooSG2/versions/XYPff5nL/extendednoteblock-1.9.1%2B1.21.1.jar> |

JAR 只临时下载用于校验，没有提交进仓库，也没有从中复制或拆出音色。
JAR 内 `fabric.mod.json` 声明 Fabric Loader `>=0.16.14`、Minecraft `~1.21.1`、
Java `>=21`、Fabric API `*`，环境为客户端和服务端。

A/B 对照也固定到实际制品，而不是仅引用当前源码：

| 对照制品 | SHA-256 |
|---|---|
| `binaries/redpiano-1.0.0-mc1.21.1.jar` | `9f752e555c083b4d47c3798439392c8dad6d44d27f2137a5d8acfbe8814ce4b9` |
| `minecraft-redstone-music/assets/qzpno_mv.zip` | `947779cbe34762aa0caf6ac1d8c709ba49455c2b5e86a1971517060c1c4c4758` |

反编译固定的 1.21.1 RedPiano JAR 后确认：它读取 `rpcfg` 的 `poly` / `human`，
但没有当前源码中的 `mute` 开关。因此探针不依赖 `mute`，而是在切换前和下一游戏刻
首个触发前各执行一次 `stopsound @a record`。

## 3. 源码核对后修正的关键假设

### 3.1 乐器不在 NBT 中

ENB v1.9.1 的 `getInstrumentId()` 读取音符盒正下方方块，再查
`InstrumentMap.BLOCK_TO_GM_INSTRUMENT`。探针因此嵌入官方 0..128 的 129 项唯一方块表；
抽查使用：

| Program | 乐器 | 垫底方块 |
|---:|---|---|
| 0 | Acoustic Grand Piano | `minecraft:dirt` |
| 33 | Electric Bass (finger) | `minecraft:spruce_planks` |
| 48 | String Ensemble 1 | `minecraft:calcite` |
| 30 | Distortion Guitar | `minecraft:obsidian` |
| 128 | Standard Drum Kit | `minecraft:sandstone` |

### 3.2 六个基础字段必须全写

`readNbt()` 对缺失字段会读成 0。探针每个 ENB 都完整写：

```mcfunction
setblock X Y Z extendednoteblock:extended_note_block[powered=false,pitch=c]{note:60,velocity:100,sustainTime:80,delayedPlayingTime:0,fadeInTime:0,fadeOutTime:4}
```

Minecraft 1.21.1 的物品组件化没有把方块实体 `/setblock` SNBT 改成
`minecraft:block_entity_data`；探针明确禁止输出这种错误包装。

### 3.3 ENB 不能照搬 RedPiano 的 1 tick 断电脉冲

官方 `neighborUpdate()` 在上升沿发声、下降沿调用 `stopNote()`。因此现有 Family A
的 “触发后 1 tick 清红石” 会直接截断 ENB 的 `sustainTime`。

探针采用每个 MIDI 事件一个 ENB 方块：

- 播放前先全部断电；
- 等 1 游戏刻制造干净上升沿；
- ENB 保持高电平至少 `delay + sustain + 1 tick`；
- 盲听中的 RedPiano 方块仍按原有 1 tick 脉冲复位。

结束调度按全部事件的 `max(onset + hold)` 计算，不能只看最后一组 onset；否则“早开始、
晚结束”的长音会被 `done -> off/all` 提前截断。自测包含这一回归。

### 3.4 tick rate 必须参与持续时间换算

ENB 的 sustain/fade 按服务器 tick 推进。探针默认沿用 Family A 的 `/tick rate 80`，
所以 `dur 秒 → round(dur × 80)`；若指定 `--tick-rate 20` 则乘 20。tick rate 仍须由
玩家手动输入；仓库既有游戏实测已证明机器自动设置不可靠，因此探针函数不会自动修改全局
tick rate，测试结束也由玩家手动 `/tick rate 20` 恢复。
所有值限制到 ENB 当前 1..400 tick 范围，并在 manifest 报告长音截断数。

### 3.5 首次启动必须手动激活默认音色包

官方配置的 `activeSoundPackId` 初值为空；客户端在没有 active pack 时会直接跳过播放。
ENB 会把 JAR 内的 `extendednoteblock_default.zip` 提取到资源包目录，但**不会替用户默认
选中它**。首次测试必须在 `选项 -> 音色包` 中点击“默认音色”，确认绿色箭头出现并等待
资源重载完成，同时把“唱片/唱片机”音量设为大于 0。探针的 `load`、`builddone` 和生成
报告都重复提示这一步；服务端数据包无法替客户端检测或激活。

### 3.6 试听位置、A/B 与压力测试边界

ENB 是约 16 格有效范围的位置声，而固定的 RedPiano 是玩家头部居中声。探针把普通 bank
压缩到 8 列、每格 X 间距 2 / Z 间距 3，并为每项生成固定试听坐标和 barrier 落脚台；
每次测试会自动把在线玩家传送过去。A/B 两边使用相同相对几何，只接受 RedPiano 可比音域
MIDI 12..93。

这仍不是严格感知盲测：定位、响度以及脚下方块外观都可能泄露后端。游戏内随机标签只作为
**闭眼/遮屏、由第二人触发的单盲初筛**。若要把钢琴偏好作为 GO 证据，必须在固定点分别
录音、响度归一化，再由第三方随机重命名后评分。`stress_64` 可做近场听感；256 / all
距离超过 ENB 声音半径，只能评估方块实体、MSPT/FPS、服务端日志，不能靠人耳统计吞音。

### 3.7 生命周期与维度

公共 `setup` / `test/*` / `verify` / `inspect` / `stop` / `cleanup` 都固定在
`minecraft:overworld` 执行。`/reload` 会撤销本探针的 scoped forceload；此后远程
`setup` / `stop` / `cleanup` 会先重新强加载目标区块，等 1 游戏刻，再断电、建造或清理，
避免对未加载区块执行 `setblock`。探针硬拒绝超过 240 chunks 的布局，也不输出
`forceload remove all`。

### 3.8 129 乐器垫底的物理稳定性

官方映射中包含 `soul_lantern`（program 99）和 `bell`（119），两者直接悬空会破坏并让
ENB 读到错误乐器。每个事件现在都有 Y-2 石头地基、Y-1 乐器垫底、Y 音符盒、Y+1 空气；
因此合法 Y 原点收紧为 `-62..318`。

## 4. 自动化结果

内置自测命令：

```powershell
python poc/50_enb_probe.py --selftest
```

当前结果：系统 Python 自测 `PASS`；带 `mido` 的 Python 3.11 完整 MIDI 自测也为
`PASS`；既有 `redpiano_core.py --selftest` 仍为 `PASS`。已覆盖：

- pack format 48、单数 `function/` / `tags/function/`；
- 仅允许 MC 1.21.1；
- GM 0..128 映射完整且唯一；
- 六字段 SNBT 与 float/double 高级 NBT 后缀；
- 20/80 tick rate 的 sustain 换算与 400 tick 上限；
- 12 音同 tick 落在同一 step；
- ENB 不生成 1 tick 断电；
- 全序列长音尾部不被最后一个短音提前截断；
- 重播前完整断电，并在下一 tick 首触发前再次停止 `record` 类尾音；
- 不在函数中自动修改 tick rate；
- Overworld 包装、先 forceload 后断电/建造/清理；
- 分批建造、240 chunks 硬上限、scoped forceload、无 `forceload remove all`；
- 每个 bank 的固定试听点、barrier 落脚台与全事件石头地基；
- MIDI type 2、NaN/Infinity、超大事件数和越界坐标均明确拒绝；
- 固定 RedPiano/qzpno 对照哈希，A/B 只选 MIDI 12..93；
- build-only 默认不触碰存档，部署路径需显式指向 `saves/<world>/datapacks`。

用本地熟悉 MIDI 生成：

```powershell
python poc/50_enb_probe.py `
  --midi poc/qingtian_piano.mid `
  --namespace enbprobe `
  --origin 200 520 200 `
  --tick-rate 80 `
  --start 0 --seconds 12 --max-notes 64 `
  --blind-notes 32 --stress-count 512
```

生成结果（build-only，未部署）：

| 项 | 值 |
|---|---:|
| MIDI SHA-256 | `3dbcce5f615fc40d0b923f2d7dd04938a8d2755e8ea233861eed95735614e7b9` |
| 选中 MIDI 音符 | 51 |
| 物理事件块 | 694 |
| ENB / RedPiano A/B | 662 / 32 |
| 压测 ENB | 512 |
| setblock 建造命令 | 3,480（2 批） |
| 占地 | X `200..214`，Z `519..843`，Y `200` |
| forceload | 42 chunks |
| 固定试听平台 | 10 |
| 生成函数文件 | 320 |
| sustain 被 400 tick 截断 | 0 |

生成目录 `build/enbprobe/` 受 `.gitignore` 管理；其中
`ENB_PROBE_REPORT.md`、`probe_manifest.json` 和 `blind_key.json` 是本轮可重建产物。

## 5. 尚未完成的人工门

当前机器只有既有 `Fabric 1.18` 与 `Fabric 1.21.8` 配置，没有可直接复用的 1.21.1
测试实例。本轮没有伪装成“实听通过”，也没有将 1.21.8 当成 ENB 兼容版本。

| 验收项 | 状态 | 待记录证据 |
|---|---|---|
| 五类音色是否真的可接受 | 未验证 | 试听人、片段、主观评分 |
| velocity / sustain / fade / delay | 未验证 | 预期与实听时长/响度 |
| 1.21.1 `/setblock` + NBT | 未验证 | `verify` 与 `inspect` 原始输出 |
| 12 音同 tick 稳定性 | 未验证 | 三轮爆音/吞音次数 |
| 64 同 tick 近场听感 | 未验证 | 爆音/吞音次数 |
| 256 / 512 性能压测 | 未验证 | `/tick query`、MSPT、FPS、服务端日志；不以人耳统计吞音 |
| ENB vs Salamander 随机标签初筛 | 未验证 | 闭眼/遮屏 A/B 评分后再揭盲 |
| 录音归一化严格盲评 | 未验证 | 随机标签、评分人、偏好 |

## 6. 裁决规则

- 全部重大项可接受：记录证据后改为 **GO**，才允许开始 Phase 2。
- 任一重大项不合格：改为 **NO-GO**，本分支止损，不写正式后端。
- 当前：**WAITING**。自动生成成功只证明“可构造”，不证明“好听、稳定、值得接入”。

## 7. 一手来源

- ENB 官方仓库：<https://github.com/atemukesu/ExtendedNoteBlock>
- 官方 generator preparation：
  <https://atemukesu.github.io/ExtendedNoteBlock/manual/generator_preparation.html>
- Modrinth：<https://modrinth.com/mod/extendednoteblock>
