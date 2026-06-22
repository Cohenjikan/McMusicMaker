# -*- coding: utf-8 -*-
"""09_detect_breaks.py — 探测红石音乐播放中的"断拍"位置 (完全不依赖任何游戏指令)。

录一遍游戏内播放(务必录"系统声音/桌面音频", 不是麦克风), 本脚本扫出每个静默
断点的精确时间戳 + 时长, 映射到第几拍 / 第几 cell, 并给出关键判据:

  * positional  —— 两遍录音的断点落在 **同样的歌曲位置**(同几个 cell)
                    → 机器 / 红石脉冲故障 → 改触发方式(pivot)能根治。
  * temporal    —— 断点之间 **墙钟间隔恒定(~8s)** 但歌曲位置每遍漂移
                    → 服务端 tick 被冻(区块保存 / GC)→ pivot 须同时缩小机器足迹才有效。

附带还判断: 每个断点 **之后** 的音符是"挤成一团"(stall 之后追帧 catch-up)
            还是"干净接上"(真丢拍) —— 这俩机理不同, 一看便知。

用法:
    # 单遍: 看断点在哪、是否 ~8s 周期
    python 09_detect_breaks.py rec.mp4

    # 两遍: 自动判 positional vs temporal(强烈建议录两遍)
    python 09_detect_breaks.py rec1.mp4 rec2.mp4

    # 可调参数
    python 09_detect_breaks.py rec.mp4 --grid 0.221 --silence-db -45 --min-gap 0.6

依赖: numpy, soundfile; 以及 PATH 上的 ffmpeg(用于从 mp4/mkv/webm 提取音轨)。
     这些 DEVLOG §7 的 venv 里都有。
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np

# ---- 音频读取 (wav/flac/ogg 直读; 其它格式先用 ffmpeg 转 wav) -----------------
def load_audio(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".wav", ".flac", ".ogg"):
        import soundfile as sf
        x, sr = sf.read(path, always_2d=True)
        return x.mean(axis=1).astype(np.float64), sr
    # mp4 / mkv / webm / m4a ... : ffmpeg -> 临时 wav (单声道 22.05k)
    if not _have_ffmpeg():
        sys.exit("需要 ffmpeg 来解码 %s, 但 PATH 上没找到。请用 .wav/.flac/.ogg, 或装 ffmpeg。" % ext)
    tmp = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", path, "-ac", "1", "-ar", "22050", tmp],
            check=True,
        )
        import soundfile as sf
        x, sr = sf.read(tmp)
        return (x.mean(axis=1) if x.ndim > 1 else x).astype(np.float64), sr
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _have_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


# ---- RMS 包络 + 静音段检测 ----------------------------------------------------
def rms_envelope(x, sr, hop=0.010, win=0.025):
    """返回 (times[s], rms_dB)。dB 以整段 95 百分位响度为 0 参考。"""
    h, w = int(sr * hop), int(sr * win)
    n = max(1, (len(x) - w) // h)
    frames = np.lib.stride_tricks.as_strided(
        x, shape=(n, w), strides=(x.strides[0] * h, x.strides[0])
    )
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    ref = np.percentile(rms, 95) + 1e-12          # 音乐的"响"参考, 抗背景噪声
    db = 20 * np.log10(rms / ref)
    t = np.arange(n) * hop
    return t, db


def find_gaps(t, db, silence_db, min_gap, hop=0.010):
    """低于阈值且连续时长 >= min_gap 的段 = 断点。返回 [(start, dur)]。"""
    silent = db < silence_db
    gaps, i, n = [], 0, len(silent)
    while i < n:
        if silent[i]:
            j = i
            while j < n and silent[j]:
                j += 1
            dur = (j - i) * hop
            if dur >= min_gap:
                gaps.append((t[i], dur))
            i = j
        else:
            i += 1
    return gaps


def first_onset(t, db, silence_db):
    """第一帧有声 = 歌曲实际开始, 用于把两遍录音对齐到同一"歌曲零点"。"""
    active = np.where(db >= silence_db)[0]
    return t[active[0]] if len(active) else 0.0


def onset_rate(x, sr, lo, hi, hop=0.010, win=0.025, silence_db=-45):
    """[lo,hi) 秒内的音符起音数(RMS 上升沿过阈值), 用于看断后是否'挤成一团'。"""
    t, db = rms_envelope(x[int(lo * sr):int(hi * sr)] if hi > lo else x[:0], sr, hop, win)
    if len(db) < 2:
        return 0
    rising = (db[1:] >= silence_db) & (db[:-1] < silence_db)
    return int(rising.sum())


# ---- 单遍分析 ----------------------------------------------------------------
def analyze(path, grid, silence_db, min_gap):
    x, sr = load_audio(path)
    t, db = rms_envelope(x, sr)
    t0 = first_onset(t, db, silence_db)
    gaps = find_gaps(t, db, silence_db, min_gap)
    # 去掉开头/结尾的天然静默(DEVLOG: 头 1.3s / 尾 1.9s)
    total = len(x) / sr
    gaps = [(s, d) for (s, d) in gaps if s > t0 + 0.3 and s < total - 0.3]

    print("\n=== %s ===" % os.path.basename(path))
    print("时长 %.1fs | 采样率 %d | 歌曲起点 ~%.2fs | 断点阈值 %ddB / 最短 %.2fs"
          % (total, sr, t0, silence_db, min_gap))
    if not gaps:
        print("未检出明显断点(在阈值下)。可调 --silence-db(更接近0更敏感)或 --min-gap(更小更敏感)。")
        return {"path": path, "t0": t0, "gaps": [], "x": x, "sr": sr}

    print("检出 %d 个断点:" % len(gaps))
    print("  #   断点起(s)  时长(s)  歌曲位置(cell)  断后1s音符数")
    rows = []
    for k, (s, d) in enumerate(gaps, 1):
        cell = round((s - t0) / grid)
        post = onset_rate(x, sr, s + d, s + d + 1.0, silence_db=silence_db)
        rows.append((s, d, cell, post))
        print("  %-3d %8.2f %8.2f %12d %12d" % (k, s, d, cell, post))

    starts = [g[0] for g in gaps]
    if len(starts) >= 2:
        diffs = np.diff(starts)
        print("断点墙钟间隔(s): %s" % ", ".join("%.1f" % v for v in diffs))
        print("  → 间隔均值 %.2fs, 标准差 %.2fs %s"
              % (diffs.mean(), diffs.std(),
                 "(间隔很稳 → 偏 temporal/服务端周期卡)" if diffs.std() < 1.2
                 else "(间隔不稳 → 偏 positional/机器固定缺口)"))
    base = onset_rate(x, sr, t0, t0 + 5.0, silence_db=silence_db) / 5.0
    bunched = [r for r in rows if r[3] > base * 1.8]
    if bunched:
        print("  ⚠ %d 个断点之后音符明显变密(>基线1.8x) → 像 stall 之后'追帧 catch-up'"
              % len(bunched))
    else:
        print("  断后音符密度正常 → 像'真丢拍'(missed), 不是追帧")
    return {"path": path, "t0": t0, "gaps": gaps, "rows": rows, "x": x, "sr": sr}


# ---- 两遍比较: positional vs temporal ---------------------------------------
def compare(a, b, grid, tol_cells=3):
    print("\n========== 判据: positional vs temporal ==========")
    if not a["gaps"] or not b["gaps"]:
        print("至少一遍没检出断点, 无法比较。先单遍调好阈值再录两遍。")
        return
    cells_a = sorted(round((s - a["t0"]) / grid) for s, _ in a["gaps"])
    cells_b = sorted(round((s - b["t0"]) / grid) for s, _ in b["gaps"])
    print("rec1 断点 cell: %s" % cells_a)
    print("rec2 断点 cell: %s" % cells_b)
    matched = sum(1 for c in cells_a if any(abs(c - d) <= tol_cells for d in cells_b))
    frac = matched / max(1, len(cells_a))
    print("两遍 cell 位置重合率: %d/%d = %.0f%% (容差 ±%d cell)"
          % (matched, len(cells_a), 100 * frac, tol_cells))
    if frac >= 0.6:
        print("\n>>> 结论: **POSITIONAL** —— 断点固定在同样的歌曲位置。")
        print("    = 机器/红石脉冲故障(某些 cell 的命令方块没被触发)。")
        print("    改触发方式(指令控制红石)能根治; 不必先去折腾区块保存/GC。")
    else:
        print("\n>>> 结论: **TEMPORAL** —— 断点歌曲位置每遍漂移。")
        print("    = 服务端 tick 被周期性冻住(区块保存 / GC)。")
        print("    pivot 必须同时把机器做短/减少标脏面积才有效; 或装 Smooth Chunk Save / 换 ZGC。")
        print("    下一步可用 spark 精确归因: /spark profiler start --only-ticks-over 50 → 播放 → /spark profiler stop")


def main():
    ap = argparse.ArgumentParser(description="探测红石音乐播放的断拍位置 (positional vs temporal)")
    ap.add_argument("files", nargs="+", help="一段或多段游戏播放录音(录系统声音)")
    ap.add_argument("--grid", type=float, default=0.221, help="一个 cell 的秒数(默认 0.221 = 十六分@♩68)")
    ap.add_argument("--silence-db", type=float, default=-45.0, help="静音阈值 dB(越接近0越敏感, 默认-45)")
    ap.add_argument("--min-gap", type=float, default=0.6, help="算作断点的最短静默秒数(默认0.6, 高于正常音符间隔)")
    args = ap.parse_args()

    results = [analyze(f, args.grid, args.silence_db, args.min_gap) for f in args.files]
    if len(results) >= 2:
        compare(results[0], results[1], args.grid)
    elif len(results) == 1 and results[0]["gaps"]:
        print("\n提示: 再录一遍用 `python 09_detect_breaks.py rec1 rec2` 即可自动判 positional/temporal。")


if __name__ == "__main__":
    main()
