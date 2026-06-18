# POC SPEC — 晴天电吉他"真实重构"(Karpathy loop)

> 方法论证明:跑通 **分离 → 转写 → 取样 → 映射 → 游戏内按节奏播放**,证明产物是"乐谱+音色"(可换音色/可移调),而非原曲切片回放。
> 独立命名空间 **`qzgtr`**,**不触碰** `mc-noteblock-demo` 生产脚本(build_qingtian_v7.py / add_song.py / songs.json)与 nbviz/olk 产物。

## 成功标准(整体)
在 MC Java 1.21.8 中部署 `qzgtr` 资源包+数据包后,一条单声部红石机器按晴天吉他的真实节奏触发 **Karoryfer CC0 电吉他样本**,音高=转写所得音符。可重播、可安全拆除(复用 v7)。

## 分阶段 spec + 验证门(每步 RUN 后看输出才进下一步)

| 阶段 | 脚本 | 产物 | 验证门(通过判据) |
|---|---|---|---|
| **A 转写** | `01_transcribe.py [sec]` | `notes.json` | librosa pyin 单音;前 45s 出 **≥ 30 个音符**,音高落在 MIDI ~40–88(E2–E6),打印音高直方图+前 12 音符人工核对像吉他旋律线。垃圾→回退 bass stem |
| **B 取样** | `02_make_samples.py` | `samples/*.ogg` + `samples_manifest.json` | 从 Karoryfer **green twang** 拉 ~8 个单音(覆盖 E2–E5,每 ≤2 八度一个 band),处理为 mono / 削前导 / 硬截 ≤1.0s / 长淡出 / 全局归一 → ogg。每个 ogg 是**单音**、时长≤cap |
| **C 打包** | `03_build_pack.py [sec]` | `qzgtr_mv`(RP)+`qzgtr_redstone`(DP),部署到交换桥 | 每音符→`playsound qzgtr:gtr_b<k> ... <vol> <pitch> 1`,`pitch=clamp(2^((midi−base)/12),0.5,2.0)` 就近选 band;**单声部=每 cell 1 个 playsound**(同 cell 多音取最响,远低于 247 上限);sounds.json 合法、每个事件有对应 ogg;pack_format DP81/RP64。**自检脚本断言全部通过** |
| **D 游戏内** | 用户手动 | — | `/reload`→`/function qzgtr:setup`→等 built→`play`。**A/B 听感**:重构吉他 vs 原 guitar stem;无 MC-180398 卡顿。**重构性证明**:换样本/整体移调只改映射不动原曲 |

## 不变量(别违反)
- 不改 mc-noteblock-demo 生产文件;只新增 `RedstoneMusic/poc/` 下脚本与 `qzgtr_*` 产物。
- 样本仅用 **Karoryfer Black And Green Guitars(CC0)**;资源包注明来源。
- 复用 v7 的脊柱/forceload/play/cleanup 模式(照搬其红石写法,换命名空间与每 cell 命令)。

## 当前状态
- [x] 输入就位:`qingtian_audio/guitar.wav` 已缓存;Karoryfer 仓库可达;librosa 已装(basic-pitch 未装→A 先用 librosa,basic-pitch 复音留作 Iterate)
- [x] **A 转写**:45s 出 85 音符,E2–D#4,1.89 音符/秒 → `notes.json`
- [x] **B 取样**:8 个 green twang 单音,实测基频 E2–D6(发现 Karoryfer 音名高 1 八度,实测已纠正),137KB → `samples/` + `samples_manifest.json`
- [x] **C 打包**:83/85 音符,移调最大 2.9 半音,pitch 0.886–1.182,**最大同时发声=4**(远低于 247),自检 PASS,已部署 `qzgtr_mv`+`qzgtr_redstone` → 交换桥。离线预览 `reconstruction_preview.ogg`
- [ ] **D 游戏内(用户)**:`/reload`→`setup`→`play`,A/B 听感 + 无卡顿
