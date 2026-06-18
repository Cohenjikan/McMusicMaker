# 周期性断拍 — 根因诊断(深度调研 + 对抗式验证结论)

> 配套 `DEVLOG.md §0/§5/§6`。针对"播放时 ~8s 周期性断拍、画面流畅、只有声音断"。
> 方法:12 个子代理(8 路调研 + 4 路对抗验证)检索 minecraft.wiki / bugs.mojang.com / 红石与性能社区 / 源码分析,交叉验证。

## 结论:最可能是「周期性同步区块保存(sync-chunk-writes)stall 冻住服务端 tick 线程」

**机制(把全部症状统一起来)**:
- 单人 = **integrated server**:客户端**渲染线程**与服务端 **tick 线程**解耦。服务端 tick 一旦短暂 stall,**红石/命令方块/`/playsound` 触发全部冻住,但渲染线程独立、靠帧插值,画面/移动/生物照样丝滑** → 这正是"画面不卡、只有声音周期断"的根本机理。
- **`/playsound` 触发挂在游戏刻(服务端 tick)上**;服务端被冻 → 那一拍的声音不执行 = 缺一段。声音引擎虽是独立线程,但**触发**在 tick 上。
- **为什么是区块保存**:`sync-chunk-writes` 在单人**默认开启且无法关闭**(MC-177542),区块写盘在主线程**同步**进行,卡 tick + 受磁盘 IO 影响。自 1.18.2 起单个脏区块有"写后约 10s 内不重复写"的节流(≈你听到的 ~8s)。你的机器:**一条行进脉冲每次播放都改变 ~1246 个 repeater + 红石线的通电状态、横跨 ~156 个区块 → 全部标脏**;玩家在场让这簇塞满上千命令方块 block-entity 的区块持续标脏 → 每个保存周期要序列化海量脏区块 → stall 明显且周期性。
- **F3 MSPT 3.4ms 是均值**,会把偶发亚秒尖峰平均掉(spark 文档明确)→ "MSPT 正常"**不能**排除周期性微 stall。

**次要嫌疑:JVM GC stop-the-world 暂停**(每数秒一次、几十~两百毫秒)。但有反证:GC 冻结**整个 JVM(含渲染)**,理论上画面也该顿;你画面流畅 → 若是 GC,只能是暂停短到站着没察觉。可与"区块保存说"一并用下面的测试区分。

## 对抗式验证已排除 / 修正
| 假设 | 裁决 | 说明 |
|---|---|---|
| 红石长脉冲漏触发(脉冲整性) | **unlikely** | delay-2 repeater 对短脉冲**只拉长不吞**,对 6 刻脉冲确定性可靠、无漂移;且真漏触发会让红石动画/粒子也断,不会"只断声"。 |
| 声道/声池打满 | 排除 | F3 `Sounds 18–34/4095`,峰值 34 远未满(RSLS 已生效)。 |
| 音乐数据有空白 | 排除 | 离线渲染音频全程连续(仅头 1.3s/尾 1.9s)。 |
| `/playsound` 距离剔除 / 可听窗口随脉冲移动 | **对本实现不适用** | 命令是 `execute as @a at @s run playsound … @s ~ ~ ~`,声音播在**玩家身上(距离0)**,与命令方块位置无关。(调研里这条基于"声音在命令方块处"的误解。)→ 反而**加固**结论:声音恒在玩家身边,唯一会断 = 那一刻**触发没按时=服务端 stall**。 |
| 整盘 autosave(6000 tick) | 排除为 8s 主因 | 在 tick rate 18.1 下 ≈5.5 分钟,对不上 8s;~8s 来自**增量脏区块写盘节流(~10s)**或 GC。 |

## 决定性下一步(按顺序,前两步免费)
1. **`/save-off` 测试(免费、决定性)**:进世界后先 `/save-off`(关自动保存)→ setup → `/tick rate 18.1` → play。
   - **断拍消失** = 坐实「区块保存 stall」(也即临时解法)。演奏完 `/save-all` 再 `/save-on` 存档。
2. **spark 抓证据**:装 [spark](https://modrinth.com/mod/spark)(Fabric 客户端),播放时 `/spark profiler --only-ticks-over 70` + `/spark gcmonitor` + `/spark tickmonitor`。尖峰落在 **chunk serialize** → 区块保存;落在 **GC** → 垃圾回收;均值掩盖不了它。
3. **据结果永久修**:
   - 区块保存 → 装 **Smooth Chunk Save**(把集中写盘随时间摊平;vanilla 1.18 实测保存占 tick 从 11%→0.3%);或**减少 forceload 区块 / 缩短机器**;换 SSD。
   - GC → Modrinth profile 的 JVM 参数换 **ZGC**(`-XX:+UseZGC -XX:+ZGenerational`,暂停<1ms)+ 合理堆(别开太大)。

## 关于"8 秒手动补丁":不建议(治标 + 有副作用)
- 没碰根因(stall);且"重发脉冲"会与在线上行进的原脉冲在同一命令方块**叠播/回声/双音**;手动秒级时基远粗于 0.221s 的十六分音符,**必然引入新错位**。

## 若想从根上消除 stall(架构层,可选)
脉冲行进 = 不断改红石通电状态 = 不断标脏 156 个区块 = 保存负担。两条更稳的路(都仍保留红石视觉):
- **减少标脏面积**:把机器做**短/密**(更细网格但更短),或把发声与"行进脉冲"解耦——红石继续跑视觉,但发声用一个**每 tick 的数据包函数**在固定监听点精确触发(发声不依赖脉冲实时到达;注意:数据包发声同样是 tick-bound,**仍需先消除 stall**,它解决的是"行进脉冲改状态标脏"那部分)。
- **`/save-off` 工作流**:演奏/录屏时关存档,演奏完再存——最省事,零改动。

## 主要来源
- 单人 server/render 线程解耦 + tick-bound 行为:[Tick – wiki](https://minecraft.wiki/w/Tick)、Minecraft Forum(integrated server tick loop)
- 同步区块写盘卡主线程:[MC-177542](https://bugs.mojang.com/browse/MC-177542)、[Paper #738](https://github.com/PaperMC/Paper/issues/738)、[YouHaveTrouble/minecraft-optimization](https://github.com/YouHaveTrouble/minecraft-optimization)
- 单区块 ~10s 写盘节流(1.18.2):[chunk-save-throttling](https://github.com/TheRealWormbo/chunk-save-throttling)
- Smooth Chunk Save:[CurseForge](https://www.curseforge.com/minecraft/mc-mods/smooth-chunk-save)
- GC 卡顿 + ZGC/Shenandoah:[MC-273262](https://bugs-legacy.mojang.com/browse/MC-273262)、[brucethemoose flags](https://github.com/brucethemoose/Minecraft-Performance-Flags-Benchmarks)、[Aikar JVM](https://aikar.co/2018/07/02/tuning-the-jvm-g1gc-garbage-collector-flags-for-minecraft/)
- repeater 对短脉冲只拉长不吞:[Redstone Repeater – wiki](https://minecraft.wiki/w/Redstone_Repeater)、[Redstone circuits/Pulse](https://minecraft.wiki/w/Redstone_circuits/Pulse)
- spark 抓尖峰(均值掩盖 spike):[spark docs](https://spark.lucko.me/docs/guides/Finding-lag-spikes)
- 声道 247/OpenAL:[Sound – wiki](https://minecraft.wiki/w/Sound)、[MC-1538](https://bugs.mojang.com/browse/MC-1538)
