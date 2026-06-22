# McMusicMaker — 工程整理说明

> 本文件夹是 **McMusicMaker**（红石音乐"真实重构"项目）的**完整工程副本**，
> 于 **2026-06-21** 从 `C:\Users\Cohen\nbviz` 散落各处的内容整理汇集而成。
> GitHub：https://github.com/Cohenjikan/McMusicMaker

整理方式为**复制**——原文件在 `nbviz` 里**原位保留未动**，本副本不影响原 git 仓库，
也不影响 `nbviz\datapacks`、`nbviz\resourcepacks` 指向游戏的 junction 部署。

---

## 这个项目是什么

把红石音乐从"切片回放原曲"升级为 **分轨 → 转写音高 → 真实乐器取样 → 按节奏 playsound** 的
可行性调研 + 落地 POC。引擎 Minecraft Java **1.21.8**。推荐架构 Tier 2（数据包 + 资源包），
复用现有 v7 红石时序引擎。POC = 晴天吉他轨 / 钢琴轨。详见 `README.md`、`01_可行性与架构.md`。

---

## 目录结构

```
McMusicMaker/
├── .git/                       完整 git 仓库，origin 仍指向 github.com/Cohenjikan/McMusicMaker
├── .gitignore
├── README.md                   项目说明（一句话结论 + 状态）
├── 00_继承分析.md               既有研究继承、可复用资产、两条已证伪的死路
├── 01_可行性与架构.md           主报告：硬约束核实、三档可行性对照、推荐架构、工具链
├── DEVLOG.md                   开发日志
├── RESEARCH_break_diagnosis.md  卡顿成因深挖（周期性区块存盘 stall 冻结服务端 tick）
├── _work/                      原始乐器采样源（115M，git 忽略，本副本含）
│   ├── karo_raw/               Karoryfer CC0 电吉他样本（twang_*.wav）
│   ├── sal_raw/                钢琴样本（Salamander，*.flac，按音高×力度分层）
│   ├── karo_tree.json
│   └── sal_tree.json
├── poc/                        POC 脚本与产物
│   ├── 01_transcribe.py        basic-pitch 转写 MIDI
│   ├── 02_make_samples.py / 02b_make_piano_samples.py / 02c_make_piano_velocity.py
│   ├── 03_build_pack.py        生成资源包 + 数据包
│   ├── 04_preview.py / 05_deploy.py
│   ├── 06_build_poly.py / 07_build_scheduler.py / 08_test_pulse.py
│   ├── gen_demo_midi.py / midi_to_notes.py
│   ├── SPEC.md
│   └── build/                  生成的成品包（git 忽略，本副本含）
│       ├── qzgtr_mv/  qzgtr_redstone/      晴天吉他 资源包 / 数据包
│       ├── qzpno_mv/  qzpno_redstone/      晴天钢琴 资源包 / 数据包
│       └── qztest_redstone/                 脉冲测试数据包（未部署）
└── deployed/                   游戏实际部署的 POC 包（从 nbviz junction 复制，见下方说明）
    ├── datapacks/{qzgtr_redstone, qzpno_redstone}
    └── resourcepacks/{qzgtr_mv, qzpno_mv}
```

### 关于 `deployed/`
这是 `nbviz\datapacks` 与 `nbviz\resourcepacks`（指向游戏的 junction）里实际部署的 4 个 POC 包。
经字节级比对，**与 `poc/build/` 下对应的包完全一致**——保留它只是为了呈现游戏的成品部署布局
（datapacks/ + resourcepacks/ 分置），并非额外/不同的内容。`poc/build/` 里另有未部署的
`qztest_redstone` 测试包。

---

## git 工作区状态（已忠实保留）

- HEAD：`c7e5801`（与 GitHub `main` 一致）
- 未提交改动（复制时一并保留）：`poc/05_deploy.py`、`poc/08_test_pulse.py` 两处本地修改
- `deployed/` 与本文件 `_CONSOLIDATION.md` 为新增的未跟踪文件（本地工作副本，未纳入 git）

---

## 未纳入本文件夹的相关项目（刻意排除，仅记录关系）

McMusicMaker 之外还有两个**音乐相关但不同**的项目，是被本项目判定为"死路"的**老切片回放方案**，
按整理范围**不收入**本文件夹：

| 项目 | 原位置 | 说明 |
|---|---|---|
| `mc-noteblock-demo` | `C:\Users\Cohen\mc-noteblock-demo`（在 nbviz 外） | Demucs 分轨 + onset 切片回放 后端（add_song.py / build_qingtian_v7.py） |
| `nbviz-studio` | `C:\Users\Cohen\nbviz\nbviz-studio` | 上面那个切片回放后端的 PySide6 GUI 前端 |

如需把整个红石音乐生态（含以上老方案 + media 里的 rickroll 母带）一并归档，可另行整理。

---

*整理统计：82 目录 / 383 文件（含 .git）的 RedstoneMusic 工作树 + 4 个部署包 ≈ 152 MB。*
