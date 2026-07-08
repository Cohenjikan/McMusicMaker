# 开发过程记录 · docs/history/

这里存放项目的**开发过程记录**（继承分析、可行性调研、开发日记、断音诊断、多版本兼容调研等）。

> ⚠️ 这些文档是按时间堆叠的**历史**，**可能与当前实现相互矛盾**（很多结论后来被推翻或迭代过）。
> **一切以 [`minecraft-redstone-music/docs/`](../../minecraft-redstone-music/docs/) 下的当前文档为准**。

如果你只是想用这个 skill，忽略本目录即可 —— 直接看根目录 [`README.md`](../../README.md) 和 [`minecraft-redstone-music/QUICKSTART.md`](../../minecraft-redstone-music/QUICKSTART.md)。

| 文件 | 内容 |
|---|---|
| `00_继承分析.md` | 既有研究继承、可复用资产、两条已被证伪的死路（切片回放 + 早期 MIDI 合成）。 |
| `01_可行性与架构.md` | 早期主报告：硬约束核实、三档可行性对照、推荐架构、工具链选型、最小 POC 计划。 |
| `DEVLOG.md` | 逐代 agent 的开发日记（按时间堆叠）。 |
| `RESEARCH_break_diagnosis.md` | 播放周期性断拍的成因深挖（区块存盘 stall 冻结服务端 tick）。 |
| `RedPiano多版本兼容-深度调研报告.md` | 多版本 API 分水岭 / 格式数字 / 工具链矩阵（D-1..D-8），当前 `VERSION_TACTICS.md` 的事实底座。 |
| `_CONSOLIDATION.md` | 一次阶段性整理记录。 |
