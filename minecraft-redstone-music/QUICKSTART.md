# QUICKSTART — build & play a redstone music machine

End-to-end checklist to go from a `.mid` file to music playing in Minecraft, using
the **RedPiano (Family A)** pipeline. Default & verified on **Minecraft 1.21.8**; any
**1.21.x up to 1.21.10** works — one `--mc-version` flag adapts `pack_format`, folders,
`pack.mcmeta` shape, and sign dialect from the version table.

---

## ⚠️ 没声?按顺序查这 3 项 (No sound? Check these 3, in order)

> Nine times out of ten it is one of these. Check **in this order** before debugging anything else.
>
> 1. **⚠ 资源包 `qzpno_mv` 你手动启用了吗?(最常见的「完全没声」原因)**
>    必须在 **选项 → 资源包 (Options → Resource Packs)** 里把 **`qzpno_mv`** **移到右侧「已选用」**——
>    这一步**没有自动化能替你点**,必须手动确认在「已选用」一侧。
>    若忘了启用、或 `rp_format` 不符,MC 会**静默禁用**该包 → 所有 `qzpno:` 音效变成
>    "unknown soundEvent" → **全静音**。`rp_format`(1.21.8 行为 **64**;其它版本由 `--mc-version`
>    从版本表自动取值)。获取/重打包资源包见 **[BINARIES.md](BINARIES.md)**,或用
>    `scripts/build_resourcepack.py` 在 skill 内按版本重打包。
> 2. **⚠ tick80 你手动设了吗?机器不会替你设。**
>    忘了 = 播放约 **4 倍慢** + 旋律截断(melody-cut)时序失准。**你必须自己在游戏里手动敲
>    `/tick rate 80`**(在按[播放]之前)。机器**不会**自动设置它(用命令方块自动设的方案已测试,
>    **不生效**)。
> 3. **RedPiano 模组 jar 是否在 `mods/` 且已重启 MC?**
>    换 jar 必须**完整重启** Minecraft(`/reload` 不够)。还需 Fabric Loader + Fabric API + Java 21。
>
> 注:在 **1.21.5+**(含默认的 1.21.8),控制台告示牌的文本现用 **SNBT** 方言(修掉了旧引号格式
> 在新版渲染成字面文本的潜伏 bug);方言在 1.21.5 自动切换。

---

## 0. Runtime rules

Use `scripts/prepare_all.py` for normal work. It is the default automation surface: it
deploys the datapack, builds/copies and enables `qzpno_mv.zip`, writes the RedPiano mod
build config, auto-detects Gradle + JDK 21, builds/copies the RedPiano jar into
`<profile>/mods/`, and reuses/downloads the matching Fabric API jar.

Manual runtime work is only for offline/partial artifacts. A result with no RedPiano jar
or no matching Fabric API in `mods/` is **not ready**. After any jar changes, fully restart
Minecraft; `/reload` is not enough for mods. The world must allow command blocks / cheats
because the machine uses command blocks and mass `setblock`.

## 1. (optional) Design a layout

Open **`designer/layout_designer.html`** in a browser. Load your MIDI, pick a form
(`inplace`/`swave`/`straight`/`custom`/`multilane`), tune the parameters, and **Export
params JSON**. This step is optional — if you skip it, every field takes its form's default.

## 2. Prepare the runtime bundle (preferred)

Use this for real handoff work. Do not add `--skip-*` flags unless the user explicitly
asked for a partial/offline artifact.

```bash
python scripts/prepare_all.py \
    --midi  path/to/song.mid \
    --form  swave \
    --ns    mysong \
    --origin 0 0 255 \
    --mc-version 1.21.8 \
    --world-dir "<profile>/saves/<world>/datapacks" \
    [--samples-root ../poc | --prebuilt-rp path/to/qzpno_mv.zip] \
    [--prebuilt-mod-jar path/to/redpiano.jar] [--fabric-api-jar path/to/fabric-api.jar]
```

- In a full source checkout, `prepare_all.py` auto-detects `../../poc` as the sample root.
- In a packaged skill bundle, pass `--samples-root` or `--prebuilt-rp`; otherwise the script
  refuses to silently skip the resourcepack.
- When a profile is inferred from `--world-dir`, the script edits `<profile>/options.txt`
  so `file/qzpno_mv.zip` is selected. If `options.txt` is missing, start that Minecraft
  profile once and rerun.
- If Gradle/JDK 21/Fabric API download is unavailable, `prepare_all.py` exits nonzero.
  Fix the missing dependency and rerun; do not treat the datapack alone as complete.

## 3. Build the datapack only (smoke test)

```bash
python scripts/build_machine.py \
    --midi  path/to/song.mid \
    --form  inplace \
    --ns    mysong \
    --origin 0 0 255 \
    --mc-version 1.21.8 \
    [--params exported_params.json] \
    [--name "显示名"] \
    [--melcap 1.2]
```

- `--form inplace` is the **verified MVP** (rock-solid, tiny footprint). `--form swave`
  is the marching-pulse path machine (product default, in-game listen pending).
  `straight`/`custom`/`multilane` are also available — see `docs/FEATURE_MATRIX.md`.
- `--ns` is the datapack namespace **and** the scoreboard objective name.
- `--origin X Z Y` sets the world build origin (overrides `start_x/z/y` from params).
- The build is staged into `build/<ns>/`. **Deploy is opt-in:** add
  `--world-dir "<world>/datapacks"` to copy it straight into a world.
- Read the printed report: palette/cell count, dropped notes, octave-shifted count,
  melody-cut count + median delay, forceload chunk count, and any WARNs.

If you did **not** pass `--world-dir`, copy `build/<ns>/` into your world's
`datapacks/` folder yourself.

## 4. Load it in-game

In the world where you want the machine, do these **in this exact order**:

```
/reload
/tick rate 80
/function <NS>:setup
```

- `/reload` registers the new datapack functions.
- **⚠ `/tick rate 80` — YOU must type this manually.** The machine does **NOT** self-set the
  tick rate (auto-set via a command block was tested and does **not** work). Without it,
  playback is **~4× too slow** and melody-cut timing is off. This is a **required** step, not
  an optional diagnostic — type it yourself before pressing `[play]`.
- **⚠ 启用资源包 — 别忘了手动开 `qzpno_mv`(最常见的「完全没声」原因).** Before playing, open
  **Options → Resource Packs** and move **`qzpno_mv`** to the right (selected) side. It must be
  the `pack_format` matching your MC version (1.21.8 = **64**); otherwise MC **silently disables
  it → total silence**. Nothing automates this click — confirm it yourself in-game.
- `/function <NS>:setup` builds the physical machine at the origin (mass `setblock`,
  batched across ticks — give it a moment) and places the sign+button console.

## 5. Play

Make sure you have already (1) typed `/tick rate 80` yourself and (2) enabled the
`qzpno_mv` resource pack in **Options → Resource Packs** (see step 4) — neither is
automatic. Then go to the console the `setup` built (at the origin) and **press the play
button** under the sign. The machine triggers the note blocks in time; the RedPiano mod emits
each note centered on every player, so the music follows you.

To rebuild for a different song, run `build_machine.py` again with a new `--ns`, then
repeat steps 3–4.

---

## Common pitfalls beyond the top-3 box

- **Eerie / slow / out-of-sync playback** → you likely forgot to type `/tick rate 80`
  yourself, or it reverted. The machine does **not** set it for you — type `/tick rate 80`
  manually, then press `[play]` again.
- **Can't stop the music** → the mod plays on the `record` source; use
  `/stopsound @a record` (the machine also exposes a stop control).
- **Build seems to do nothing on `setup`** → mass `setblock` is batched across ticks
  behind a build counter; wait a few seconds. Confirm
  `commandModificationBlockLimit` is large (the machine raises it automatically).
- **Datapack not recognized after copy** → wrong folder layout for the MC version.
  1.21+ uses **singular** `function/` and `tags/function/`; pre-1.21 uses plural
  `functions/`. The build script handles this from `--mc-version`; if you hand-edited,
  re-check the folder names.
- **`method=slice` error** → that's Family B (audio slice), out of scope here. Use the
  external `mc-noteblock-demo` repo.
