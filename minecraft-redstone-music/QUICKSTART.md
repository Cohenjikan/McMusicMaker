# QUICKSTART — build & play a redstone music machine

End-to-end checklist to go from a `.mid` file to music playing in Minecraft, using
the **RedPiano (Family A)** pipeline. Default & verified on **Minecraft 1.21.8**; any
**1.21.x up to 1.21.9** works — one `--mc-version` flag adapts `pack_format`, folders,
`pack.mcmeta` shape, and sign dialect from the version table.

---

## ⚠️ 没声?按顺序查这 3 项 (No sound? Check these 3, in order)

> Nine times out of ten it is one of these. Check **in this order** before debugging anything else.
>
> 1. **资源包 `qzpno_mv` 是否在「选项 → 资源包」手动启用?**
>    格式不符时 MC 会**静默禁用**该包 → 所有 `qzpno:` 音效变成 "unknown soundEvent" → **全静音**。
>    确认它在「已选用」一侧;若不在,多半是 `rp_format` 不对(1.21.8 行为 **64**;
>    其它版本由 `--mc-version` 从版本表自动取值)。获取/重打包资源包见
>    **[BINARIES.md](BINARIES.md)**,或用 `scripts/build_resourcepack.py` 在 skill 内按版本重打包。
> 2. **`/tick rate 80` 是否设了?**
>    忘了 = 播放约 **4 倍慢** + 旋律截断(melody-cut)时序失准。**按[播放]会自动触发一个命令方块运行
>    `/tick rate 80`**(无需手输);若仍听到异常慢,在游戏里手动设一次 `/tick rate 80` 确认。
> 3. **RedPiano 模组 jar 是否在 `mods/` 且已重启 MC?**
>    换 jar 必须**完整重启** Minecraft(`/reload` 不够)。还需 Fabric Loader + Fabric API + Java 21。
>
> 注:在 **1.21.5+**(含默认的 1.21.8),控制台告示牌的文本现用 **SNBT** 方言(修掉了旧引号格式
> 在新版渲染成字面文本的潜伏 bug);方言在 1.21.5 自动切换。

---

## 0. One-time install (runtime stack)

1. Install **Fabric Loader + Fabric API + Java 21** for Minecraft **1.21.8**
   (the verified default). For another `1.21.x` target, run
   `python scripts/mod_build.py --mc-version <ver>` to print the verified toolchain
   (fabric-loom / fabric-loader / fabric-api / Java) for that version.
2. Put the **RedPiano mod jar** in `mods/`. **Restart Minecraft.**
   (The jar is not in this folder — see [BINARIES.md](BINARIES.md) to obtain/build it.)
   The mixin binds to **internal NoteBlock bytecode**, so every target version still needs
   a **recompiled jar plus one in-game listen** — within `1.21.x` the retarget is
   number-only (`scripts/mod_build.py --write`), no Java source edits.
3. Put **`qzpno_mv.zip`** in `resourcepacks/` and **enable it** in
   Options → Resource Packs (drag it to the right-hand "Selected" column).
   (Not in this folder — see [BINARIES.md](BINARIES.md); `rp_format=64` is the **1.21.8** row,
   other versions derive from the version table.) Repack it for any version in the skill with
   `python scripts/build_resourcepack.py --mc-version <ver> --samples-root <dir> --out qzpno_mv.zip`.
4. Confirm the world allows command blocks / has cheats on (the machine uses
   command blocks and mass `setblock`).

## 1. (optional) Design a layout

Open **`designer/layout_designer.html`** in a browser. Load your MIDI, pick a form
(`inplace`/`swave`/`straight`/`custom`/`multilane`), tune the parameters, and **Export
params JSON**. This step is optional — if you skip it, every field takes its form's default.

## 2. Build the datapack

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

## 3. Load it in-game

In the world where you want the machine:

```
/reload
/tick rate 80
/function <NS>:setup
```

- `/reload` registers the new datapack functions.
- `/tick rate 80` sets the tempo the samples are tuned for (the machine also self-sets
  this via a command block, but set it manually to be safe).
- `/function <NS>:setup` builds the physical machine at the origin (mass `setblock`,
  batched across ticks — give it a moment) and places the sign+button console.

## 4. Play

Go to the console the `setup` built (at the origin) and **press the play button**
under the sign. The machine triggers the note blocks in time; the RedPiano mod emits
each note centered on every player, so the music follows you.

To rebuild for a different song, run `build_machine.py` again with a new `--ns`, then
repeat steps 3–4.

---

## Common pitfalls beyond the top-3 box

- **Eerie / slow / out-of-sync playback** → almost always `/tick rate 80` was not set
  (or reverted). Re-set it.
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
