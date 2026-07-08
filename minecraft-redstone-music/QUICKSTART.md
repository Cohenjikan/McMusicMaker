# QUICKSTART — build & play a redstone music machine

End-to-end checklist to go from a `.mid` file to music playing in Minecraft, using
the **RedPiano (Family A)** pipeline. Default & verified on **Minecraft 1.21.8**; any
**1.21.x up to 1.21.10** works — one `--mc-version` flag adapts `pack_format`, folders,
`pack.mcmeta` shape, and sign dialect from the version table.

> **Shell note:** every multi-line command block below uses **bash** syntax (trailing `\` for
> line continuation). On Windows, run these in **Git Bash** (or WSL). If you're in PowerShell,
> either run `bash` first, or rewrite the command onto one line without the `\` characters —
> PowerShell's own continuation character is a backtick and mixing the two will break the command.

---

## 🔊 只想先听个响？走开放音源最小 demo（不用自备采样）

第一次上手、只想验证「真能响」，别急着准备你自己的 MIDI 和采样——用随仓 `assets/demo.mid` + 脚本**当场合成**的开放音源（numpy，无网络/无 ffmpeg），三步就能建出完整 `dist/`：

> **两条硬前提**：**① 仅 Windows 交付**（`.bat` 安装器）；**② 必须整仓 clone**（脚本依赖 `../binaries/` 等仓库结构，不能只拷本子目录）。合成音色是**能出声的最小验证**，不是精修钢琴采样。

> 若 `pip install` 报 UnicodeDecodeError，先执行 `$env:PYTHONUTF8=1`（PowerShell）/ `export PYTHONUTF8=1`（bash）再重试。

```bash
cd minecraft-redstone-music
pip install -r requirements.txt -r requirements-demo.txt        # demo 多两个轻量包 numpy/soundfile

python scripts/fetch_binaries.py --mc-version 1.21.7            # 1) 解析随仓模组 jar
python scripts/make_demo_samples.py                            # 2) 合成 103 个开放音源采样 -> assets/demo_samples/
python scripts/prepare_all.py \
    --midi assets/demo.mid --form swave --ns demo --origin 0 0 255 \
    --mc-version 1.21.7 \
    --world-dir "<profile>/saves/<你的世界>/datapacks" --profile-dir "<profile>" \
    --dist dist \
    --prebuilt-mod-jar "../binaries/redpiano-1.0.0-mc1.21.7.jar" \
    --fabric-api-jar "../binaries/fabric-api-0.129.0+1.21.7.jar" \
    --samples-root assets/demo_samples                          # 3) 端到端 -> dist/ + 安装器
```

跑完**你本人双击** `dist\DEPLOY_TO_GAME.bat` 安装，再按下面主清单进游戏（`/tick rate 80`、启用资源包、`/function demo:setup` → 播放）。换其它绿档版本：把三处 `1.21.7` 一起改掉并**去掉** `--fabric-api-jar` 行（改为联网自动拉取）。完整版与说明见根 [`README.md`](../README.md) 的「5 分钟先听个响」小节。**这是构建级验证；游戏内实听按下面清单完成。**

---

## ⚠️ 没声?第一步跑 doctor.py, 再按顺序查这 3 项 (No sound? Run doctor.py first, then check these 3)

> **First, run the one-shot health check** — it catches almost every "no sound" cause at once:
>
> ```bash
> python scripts/doctor.py --dist dist --profile-dir "<profile>" \
>     --world-dir "<profile>/saves/<world>/datapacks" --mc-version 1.21.7 --ns <ns>
> ```
>
> It prints a numbered ✓/✗ checklist (deploy receipt? `qzpno_mv` enabled + `pack_format` matches?
> RedPiano + fabric-api in `mods/`? datapack in the world? tick-rate reminder), a **fix under each
> ✗**, and a final **VERDICT** line; all-green exits 0. Fix whatever it flags, then — if still
> silent — walk these three **in order** (nine times out of ten it is one of them):
>
> 0. **⚠ 你真的部署进游戏了吗?(在沙箱里跑 AI 时最常见、最隐蔽的原因)**
>    如果构建是由 AI 工具(Trae 等)在沙箱里做的,它写 `C:\Minecraft` 会被重定向到一个镜像,
>    **游戏根本读不到**。真正的部署必须由**你本人在资源管理器里双击 `dist\DEPLOY_TO_GAME.bat`**。
>    只有当 `dist\DEPLOY_RECEIPT.txt` 存在时才算真部署(`python scripts/deploy_bundle.py --verify dist`
>    会告诉你 `✓/✗`)。详见 **[docs/RUNTIME_SANDBOX.md](docs/RUNTIME_SANDBOX.md)**。
> 1. **⚠ 资源包 `qzpno_mv` 你手动启用了吗?**
>    双击 `.bat` 时会自动把它写进 `options.txt`;你只需在 **选项 → 资源包 (Options → Resource
>    Packs)** 里确认 **`qzpno_mv`** 在右侧「已选用」。若 `rp_format` 不符,MC 会**静默禁用**该包 →
>    所有 `qzpno:` 音效变 "unknown soundEvent" → **全静音**。`rp_format`(1.21.8/1.21.7 = **64**;
>    其它版本由 `--mc-version` 自动取值)。见 **[BINARIES.md](BINARIES.md)**。
> 2. **⚠ tick80 你手动设了吗?机器不会替你设。**
>    忘了 = 播放约 **4 倍慢** + 旋律截断(melody-cut)时序失准。**你必须自己在游戏里手动敲
>    `/tick rate 80`**(在按[播放]之前)。机器**不会**自动设置它(用命令方块自动设的方案已测试,
>    **不生效**)。
>    > **⚠ `/tick rate 80` 会加速整个世界**——不只是音乐机器,作物生长、刷怪、生物 AI、
>    > 所有红石电路全部跟着变快。多人/联机世界请谨慎使用。**听完记得敲 `/tick rate 20`
>    > 改回来**,否则世界会一直保持高速运行。
> 3. **RedPiano 模组 jar 是否在 `mods/`、版本对得上、且已重启 MC?**
>    换 jar 必须**完整重启** Minecraft(`/reload` 不够)。还需 Fabric Loader + Fabric API + Java 21——
>    **先照官方安装器装好 Fabric Loader**: <https://fabricmc.net/use/installer/>。
>    **模组 jar 必须匹配游戏版本**:`fabric.mod.json` 里钉了 `minecraft` 范围,不覆盖当前游戏就被
>    Fabric **拒载** → 变回 vanilla 音色。1.21.7 游戏用 `redpiano-1.0.0-mc1.21.7.jar`,1.21.8 用
>    `…-mc1.21.8.jar`;**别把 1.21.8 那颗装进 1.21.7**(它声明 `~1.21.8`,会被拒)。见 [BINARIES.md](BINARIES.md)。
>    RedPiano 的逻辑是**服务端(server-side)**的(`docs/MOD_ARCHITECTURE.md` §0/§6.4:内部按
>    `ServerLevel`/`ServerPlayer` 判断)——**单机**跟普通客户端模组一样装(单机的"服务端"就是你本机的
>    集成服务器);**联机/开服**则模组要装在**服务端**上,客户端装不装不影响声音是否响。
>
> 注:在 **1.21.5+**(含默认的 1.21.8),控制台告示牌的文本现用 **SNBT** 方言(修掉了旧引号格式
> 在新版渲染成字面文本的潜伏 bug);方言在 1.21.5 自动切换。

---

## 0. Runtime rules — build in the workspace, install via a native double-click

You are likely running in a filesystem **sandbox** (Trae SOLO / similar). In it, writing to
`C:\Minecraft\...` is silently redirected to a private mirror the real game never reads, so a
direct "deploy" looks fine but nothing plays. See **[docs/RUNTIME_SANDBOX.md](docs/RUNTIME_SANDBOX.md)**.
So the flow is split:

- **Build:** `scripts/prepare_all.py` stages the datapack + `qzpno_mv.zip` + mod/Fabric API
  jars into the workspace `dist/` and emits `dist/DEPLOY_TO_GAME.bat` with the real paths + a
  token baked in. This is reliable in a sandbox (the workspace is real).
- **Install (the user's job, once):** the **user double-clicks `dist\DEPLOY_TO_GAME.bat` in
  Windows Explorer** — a native process, outside the sandbox — which copies everything into
  the real profile, enables `qzpno_mv`, and writes `dist\DEPLOY_RECEIPT.txt`.
- **Proof:** the song is in-game only after that receipt exists —
  `python scripts/deploy_bundle.py --verify dist` (`✓`/`✗`). Never claim "installed" without it.

**Do NOT** deploy into `C:\Minecraft\...` yourself, **do NOT** run the `.bat` yourself (it would
inherit the sandbox and install into the mirror), and **do NOT** hand-write a `deploy.ps1` —
`prepare_all.py` handles path encoding, unicode world names, options.txt, and mod checks.
On a genuinely native host (not a sandbox) you may add `--install-now` to install inline.
After any mod jar change, fully restart Minecraft (`/reload` is not enough for mods).

**Two prerequisites before you start (a "no" means stop or warn):**
- **Java Edition only, not Bedrock.** Datapacks, `/function`, `/tick rate`, and the Fabric mod
  do not exist on **Bedrock** (Win10/11 "Minecraft" app, mobile, console). If you're on Bedrock,
  this tool cannot help — you need the **Java** launcher. 
- **The world must have cheats/OP on.** `/reload`, `/tick rate 80`, `/function` need
  **cheats (single-player)** or **OP (server)**. No cheats? Pause → **Open to LAN** → **Allow
  Cheats: ON** → Start; commands then work until you quit the world.

## 1a. (pre-check) Inspect the MIDI before choosing a form

```bash
python scripts/midi_report.py --midi path/to/song.mid [--form swave]
```

It reports duration, instrument-family mix, estimated dropped notes, estimated footprint, and a
one-line verdict — use it to pick a form (a long/dense song may push `swave`/`straight` to a large
footprint, favoring `inplace`).

**Choosing your first song:** if this is your first build, pick a **simple MIDI** — a single
melodic line or a lightly-arranged piece (solo piano, a simple pop lead) rather than a full
orchestral score. Dense/complex orchestral MIDIs (many simultaneous instruments/voices) will
**drop notes** past the per-cell polyphony cap and need octave-shifting to fit the sample range —
**this is expected behavior, not a bug**, but it means a complex first song is more likely to
sound "off" than a simple one. Run `midi_report.py` first and read its verdict before you commit
to a song; a high estimated-dropped-notes count is your cue to either simplify the MIDI or accept
the tradeoff going in.

## 1b. (optional) Design a layout

Open **`designer/layout_designer.html`** in a browser. Load your MIDI, pick a form
(`inplace`/`swave`/`straight`/`custom`/`multilane`), tune the parameters, and **Export
params JSON**. This step is optional — if you skip it, every field takes its form's default.

## 2. Build the bundle + emit the native installer (preferred)

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
    --profile-dir "<profile>" \
    --dist dist \
    [--samples-root path/to/poc | --prebuilt-rp path/to/qzpno_mv.zip] \
    [--prebuilt-mod-jar path/to/redpiano.jar] [--fabric-api-jar path/to/fabric-api.jar]
```

This produces `dist/` (staged datapack + `qzpno_mv.zip` + `mods/*.jar`) and
`dist/DEPLOY_TO_GAME.bat`. **It does not touch `C:\Minecraft` — that's the `.bat`'s job.**

- `--world-dir`/`--profile-dir` are the **real** game paths; they get baked into the `.bat`.
  `--profile-dir` must be the folder that directly contains `resourcepacks/`, `mods/`, and
  `options.txt` for the version you're targeting.
  > **⚠ Using PCL2 / HMCL with per-version isolation (版本隔离/独立) enabled?** Each version gets
  > its own private folder — point `--profile-dir` at that specific version's folder, typically
  > `.minecraft/versions/<你的版本>/`, **not** the shared `.minecraft` root (which has no
  > `resourcepacks/`/`mods/` of its own in that mode). If `doctor.py` fails **all four** checks
  > (receipt / resourcepack / options.txt / mods) at once, suspect a wrong `--profile-dir` first —
  > that's the signature of pointing at a folder that simply isn't the real profile.
- **Resolve the mod jar with one command:** `python scripts/fetch_binaries.py --mc-version <ver>`
  picks the version-matched mod jar from the sibling `binaries/` folder (local-first,
  sha256-verified) — no Gradle/JDK. Pass it as `--prebuilt-mod-jar`. (`fetch_binaries` picks the
  right jar — Fabric rejects a jar whose `~<ver>` range doesn't cover the game.)
- **Supply your own resourcepack:** the sampled `qzpno_mv.zip` is **not in the repo** — its piano
  samples are Salamander Grand Piano (**CC-BY**), which requires attribution on redistribution
  that isn't packaged into the zip, so it ships separately (drums are CC0, bass/lead/pad are
  synthesized — only piano carries the obligation; see [BINARIES.md](BINARIES.md) for the credit
  line). `fetch_binaries` reports it as `separate`, not an error. From a `qzpno_mv.zip` you have,
  derive a version-matched pack with
  `build_resourcepack.py --from-zip <your qzpno_mv.zip> --mc-version <ver> --out dist/qzpno_mv.zip`
  (a base rp-64 pack serves 1.21.7/1.21.8 as-is; other versions get only `pack.mcmeta` rewritten), or
  build from sample folders with `--samples-root`. Pass the result as `--prebuilt-rp`.
- **Or skip the resourcepack entirely:** `--skip-resourcepack` builds without staging one — the
  **honest effect** is the machine plays either **vanilla note-block timbres** or **total
  silence** (if `qzpno_mv` sound events are referenced but nothing matching is enabled in the
  world), not a guarantee of RedPiano's sampled sound. Only use it when a matching `qzpno_mv.zip`
  is already installed **and enabled** in the target profile.

  Golden offline command for **Fabric 1.21.7**, run from the `minecraft-redstone-music/` directory
  (`../binaries/…` resolves; `--prebuilt-rp` points at the pack you built above):

  ```bash
  python scripts/prepare_all.py --midi <mid> --form swave --ns mysong --origin 0 0 255 \
      --mc-version 1.21.7 \
      --world-dir "<profile>/saves/<world>/datapacks" --profile-dir "<profile>" \
      --prebuilt-rp      dist/qzpno_mv.zip \
      --prebuilt-mod-jar ../binaries/redpiano-1.0.0-mc1.21.7.jar \
      --fabric-api-jar   ../binaries/fabric-api-0.129.0+1.21.7.jar \
      --dist dist
  ```

  (If the shipped jar is still `…-mc1.21.7-UNVERIFIED.jar`, use that name verbatim.) In a full
  source checkout instead, `--samples-root` auto-detects `../../poc` (anchored to `scripts/`, i.e.
  repo-root `poc/`; a hand-passed `--samples-root` is relative to your shell's cwd, so use `./poc`
  from the repo root or an absolute path); the mod jar is built only if you have Gradle + JDK 21.
- If a required dependency is unavailable, `prepare_all.py` exits nonzero. Fix it and rerun;
  do not treat a partial build as complete.

**Then:** the user double-clicks `dist\DEPLOY_TO_GAME.bat` (Explorer, native). Confirm with
`python scripts/deploy_bundle.py --verify dist` → `✓ INSTALLED`. Only then is the song in-game.
(Native host with no sandbox? add `--install-now` to skip the `.bat`.)

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

- `--form inplace` is a tiny-footprint MVP, functionally complete but tested in-game fewer
  times than `swave`. `--form swave` is the marching-pulse path machine (product default) and
  **has been tested in-game multiple times and confirmed working**.
  `straight`/`custom`/`multilane` are also available — see `docs/FEATURE_MATRIX.md`.
- `--ns` is the datapack namespace **and** the scoreboard objective name.
  > **⚠ Pick a name you haven't used in this world before.** A `datapacks/<ns>/` folder that
  > already exists gets **overwritten wholesale** by a build using the same `--ns`. If you're
  > rebuilding the *same* song on purpose that's fine; otherwise pick a fresh, unique name.
- `--origin X Z Y` sets the world build origin (overrides `start_x/z/y` from params).
  > **⚠ The argument order is `X Z Y` — NOT `X Y Z`.** In-game, the **F3** debug screen shows
  > coordinates as `X Y Z` (e.g. `X: 120  Y: 71  Z: -340`). If you copy those numbers in that
  > order straight into `--origin`, you swap **height (Y)** and **Z**, and the machine gets
  > built at the wrong height (often underground) or the wrong horizontal position. Re-order
  > them: `--origin <X> <Z> <Y>` — i.e. `--origin 120 -340 71` for the F3 example above.
  >
  > **Picking a build site:**
  > 1. Stand where you want the machine's corner and open **F3** to read `X`/`Y`/`Z`.
  > 2. Pick **open, flat terrain** — the build clears/overwrites blocks in its footprint; nothing
  >    valuable should be there.
  > 3. Estimate the footprint **before** building: `python scripts/midi_report.py --midi <mid>
  >    --form <form>` prints an estimated footprint per form, so you know roughly how much space
  >    to clear (swave/straight/multilane can span hundreds of blocks for a long song; `inplace`
  >    stays tiny).
  > 4. **Strongly recommended:** try the whole flow on a **creative-mode test save** first,
  >    before building in a world you care about.
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
  > **⚠ This speeds up the ENTIRE world**, not just the machine — crop growth, mob spawning/AI,
  > redstone, everything runs 4× faster. Be careful on a multiplayer/shared server. **Set it
  > back with `/tick rate 20` when you're done listening.**
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

## 6. Tear it down (拆机) — 不想要了怎么拆

Every generated machine ships its own **`/function <NS>:cleanup`**. Verified against the actual
generator source (`scripts/generators/inplace.py`, `swave.py`, `multilane.py`):

```
/function <NS>:cleanup
```

**What it does:**
- Resets the `PLAY`/`LOOP`/`SIL` scoreboard **values** to 0 and stops sound (`stopsound @a`).
- Sets the player back to `gamemode creative` and clears any pending `schedule`d functions
  (`done`, and `cutmel` on multi-instrument builds).
- **Clears the machine's block footprint back to air** — an axis-aligned `fill ... air` over the
  build's bounding box (on `inplace`, one shot; on `swave`/`multilane`, a **segmented** teardown
  across multiple ticks — `cleanup` kicks off a `clearstep`/`clr/cN`/`cleardone` chain — because a
  single `fill` over a large footprint can exceed the command size limit; give it a moment on a
  big build).
- Runs `forceload remove all` — releases the forceload tickets the machine registered at `setup`.
- Prints a `tellraw` confirmation ("cleaned up." / "tearing down...").

**What it does NOT do:**
- It does **not** remove the `scoreboard objectives` themselves (`<ns>`, `rpcfg`) — only resets
  their values. The objective definitions stay registered until the datapack is removed.
- It does **not** delete the datapack files or unregister the datapack — the functions
  (`setup`/`play`/`cleanup`/…) remain callable; running `setup` again rebuilds the machine.
- It does **not** touch the resourcepack or the mod jar — those are shared runtime assets, not
  per-song.

**To fully remove a song**, run `cleanup` first (clears the physical blocks, cleanest), then
delete its folder from `<world>/datapacks/<ns>/` and `/reload`.

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
