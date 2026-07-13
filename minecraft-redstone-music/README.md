# minecraft-redstone-music

Turn a **MIDI file** into a **Minecraft (Java) redstone-music machine**. The playable
runtime is a **datapack + enabled `qzpno_mv` resourcepack + RedPiano mod + Fabric API**:
the datapack drives real note blocks through the mod, and the resourcepack supplies the
sampled instruments (piano / bass / lead / pad / drums). One `--mc-version` flag self-syncs the datapack,
resourcepack, mod build, and profile install to
your target. The supported auto band is **1.21 … 1.21.10** (1.21.9 via min/max `pack.mcmeta`);
**1.21.8 is the verified default & anchor**.

- 支持 MP3/音频→MIDI 转换前置(basic-pitch/字节钢琴转录,开源代跑,质量提示见文档)——没有现成
  MIDI、只有音频文件也能起步,见 [SKILL.md](SKILL.md) 「用户只有 MP3/音频,没有 MIDI 怎么办」。

> **For any agent, on any platform.** This is a plain Python CLI — you read these docs and run a
> command. It works the same whether you're driving it from Trae, Codex, Mavis, Work Buddy,
> Claude, or a human shell. If you register it as a **Claude Code skill**, the YAML frontmatter in
> [SKILL.md](SKILL.md) is what lets the loader discover it by trigger phrase — but no loader is
> *required* to just use the folder directly.
>
> **Clone the whole repo — this folder alone is not enough.** The scripts under `scripts/`
> resolve sibling paths like `../binaries/` (prebuilt jars)
> relative to the repo root. **Do not copy just `minecraft-redstone-music/` out on its own** —
> keep it inside the full repo checkout, or those lookups silently fail to find the prebuilt
> binaries (see [BINARIES.md](BINARIES.md)). The attributed resourcepack is bundled locally at
> `assets/qzpno_mv.zip`.
>
> One OS caveat: the delivery chain (the generated **`DEPLOY_TO_GAME.bat` installer**) is
> **Windows-only** (Minecraft Java's usual home). On a non-Windows **native host** (not a
> sandbox), install with `--install-now` instead, or copy `dist/` into the profile by hand —
> there is no `.sh`/`.command` equivalent shipped today.

---

## 开场怎么说?(复制即用的提示词)

不知道第一句话对 agent 说什么?整仓 clone 后打开你的 agent(Claude Code / Trae / Codex …),
**按你的场景复制下面任意一条、填上 `<>` 里的内容发出去**即可——剩下的活 agent 会照
[SKILL.md](SKILL.md) 自己干,并在需要你动手时(游戏内命令、双击安装器)明确告诉你。

> **① 最简单:默认预设一条龙(推荐第一次用)**
> ```
> 我想把这首歌做成 Minecraft 红石音乐:<把 .mid 文件拖进对话或粘贴路径>。
> 我的游戏版本是 1.21.8,存档的 datapacks 路径是 <粘贴 saves\你的世界\datapacks 的完整路径>。
> 用默认预设帮我全程搞定,最后告诉我进游戏要敲哪几条命令。
> ```
>
> **② 只有 MP3,没有 MIDI**
> ```
> 我只有 MP3 没有 MIDI:<拖入 .mp3>。先帮我转成 MIDI 并告诉我转换质量怎么样,
> 值得做再继续做成红石音乐(游戏版本和存档路径:<填写>)。
> ```
>
> **③ 想自己设计机器的形状和走线**
> ```
> 我想自己设计机器的走线和形状。请教我打开 designer/layout_designer.html
> (整仓 clone 后浏览器直接打开),我画好导出 params JSON 之后你来构建
> (游戏版本和存档路径:<填写>)。
> ```
>
> **④ 我的 Minecraft 是老版本(1.16 / 1.12 …)**
> ```
> 我的 Minecraft 是 <版本号>(不是 1.21),还能做红石音乐吗?
> 请按工匠路径评估,如实告诉我这个版本能做到什么程度、音色差在哪,再动手。
> ```
>
> **⑤ 建好后要拍视频 / 展示**
> ```
> 机器建好后我要录视频:帮我配置好音色展台和保护壳,
> 建好后给我一套拍摄操作顺序(预加载 → 播放 → 运镜)。
> ```

两个常见小问题:
- **存档路径怎么找**:资源管理器打开存档文件夹(官方启动器在 `%APPDATA%\.minecraft\saves\`,
  Modrinth App 在 `profiles\<档案名>\saves\`),进你的世界文件夹,和 `level.dat` 同级有个
  `datapacks` 文件夹——把它的完整路径整个复制给 agent。
- **MIDI 哪里找**:爱给网 / MuseScore / BitMidi 等,**首选钢琴独奏版**(音轨干净、还原度最好)。

---

> **Shell note:** the multi-line commands below use **bash** syntax (trailing `\` for line
> continuation). On Windows, run them in **Git Bash** (or WSL); PowerShell users should either
> launch `bash` first or rewrite the command onto a single line without the `\` characters.

## Quick start

```bash
# 0. one-time: install the only Python dependency
pip install -r requirements.txt           # just `mido` (MIDI parsing)

# 1. build a datapack from a MIDI (datapack-only smoke test)
python scripts/build_machine.py --midi assets/demo.mid --form inplace \
       --ns mysong --origin 0 0 255 --mc-version 1.21.8
```

- `--midi` your `.mid` (a license-clean `assets/demo.mid` is bundled to smoke-test with).
- `--form` `inplace` (tiny footprint, functionally complete, tested in-game fewer times than
  `swave`) is a safe smoke test; **`swave`** is the recommended default for the full "playhead
  travels the line" machine and **has been tested in-game multiple times and confirmed working**.
  Other forms: `straight`, `custom`, `multilane` (see [SKILL.md](SKILL.md) / [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md)).
- `--ns` datapack namespace (also the scoreboard name — **pick a name you haven't used before**;
  reusing one overwrites that datapack's existing folder). `--origin X Z Y` is the world build
  origin (note the order: **X Z Y**, NOT the `X Y Z` order the in-game F3 screen shows — see
  [QUICKSTART.md](QUICKSTART.md) §3 for the full warning + site-picking guidance). `--mc-version` is any version in the supported auto band
  **1.21 … 1.21.10** (defaults to the verified `1.21.8` anchor); pack_format, function-folder name,
  `pack.mcmeta` shape and sign-NBT dialect all auto-derive from the version table. Outside this
  band the auto-build `raise`s (it only auto-builds green) — that's the cue to switch to the
  **craftsman path** ([docs/VERSION_TACTICS.md](docs/VERSION_TACTICS.md)): the skill still helps
  you build a working machine by hand on any version, it just isn't automated.
- The datapack is written to `build/<ns>/`. Add `--world-dir "<world>/datapacks"` to deploy it
  straight into a world (otherwise copy `build/<ns>/` there yourself). Deploy is opt-in.
- The script prints a stats report **and the exact in-game next steps**. Read them back to the user.

For a real handoff, use the runtime command. It **stages** the datapack + `qzpno_mv.zip` +
mod/Fabric API jars into the workspace `dist/` and emits **`dist/DEPLOY_TO_GAME.bat`** with the
real profile paths + a token baked in. It does **not** install into `<profile>` itself — that
is deliberate: an AI tool usually runs in a filesystem **sandbox** where writing to `C:\Minecraft`
is silently redirected to a mirror the real game never reads (see
[docs/RUNTIME_SANDBOX.md](docs/RUNTIME_SANDBOX.md)). The workspace `dist/` is the one place a
sandbox can write reliably.

```bash
python scripts/prepare_all.py --midi path/to/song.mid --form swave --ns mysong \
       --origin 0 0 255 --mc-version 1.21.8 \
       --world-dir "<profile>/saves/<world>/datapacks" \
       --profile-dir "<profile>" --dist dist \
       [--prebuilt-mod-jar path/to/redpiano.jar] [--fabric-api-jar path/to/fabric-api.jar]
```

`--world-dir`/`--profile-dir` are the **real** game paths; they get baked into the `.bat`, not
written to now. `prepare_all.py` automatically finds `assets/qzpno_mv.zip` and converts its
metadata for the target version. Do not use `--skip-*` flags for normal handoff; a
missing RedPiano jar or Fabric API means the runtime is **not ready**, not complete.

**Resourcepack: bundled by default.** Use `--samples-root <dir>` or `--prebuilt-rp <zip>` only to
replace the included sounds. `--skip-resourcepack` builds without one. Its honest effect: the machine plays either **vanilla note-block
timbres** or **total silence** (if `qzpno_mv` sound events are referenced but nothing matching is
enabled in the world) — it is **not** a promise of RedPiano's sampled sound. Only use it when a
matching `qzpno_mv.zip` is already installed and enabled in the target profile.

> **Packaged bundle? Resolve the binaries with one command.** The prebuilt jars and manifest ship
> in sibling `binaries/`; `qzpno_mv.zip` ships in this skill's `assets/`.
> Run **`python scripts/fetch_binaries.py --mc-version <ver>`** — it picks the version-matched mod
> jar and verifies the resourcepack. Pass the jar as `--prebuilt-mod-jar`; the resourcepack needs
> no flag. No manifest jar for `<ver>`? recompile. See
> [BINARIES.md](BINARIES.md) and the golden path in [QUICKSTART.md](QUICKSTART.md) §2.

**Install (the user's job, once):** tell the user to **double-click `dist\DEPLOY_TO_GAME.bat` in
Windows Explorer** — a native process, outside the sandbox — which copies everything into the real
profile, enables `qzpno_mv`, and writes `dist\DEPLOY_RECEIPT.txt`. **Never run the `.bat` yourself**
(it would inherit the sandbox). The song is in-game **only** after that receipt exists — confirm
with `python scripts/deploy_bundle.py --verify dist` (`✓ INSTALLED` / `✗`); never claim "installed"
without it. On a genuinely native host (not a sandbox) you may add `--install-now` to install inline
and skip the `.bat`.

## Play it in Minecraft

> Prerequisites: **Java Edition** (not Bedrock — datapacks/`/function`/`/tick rate`/Fabric mods
> don't exist there), and a world with **cheats/OP on** (needed for `/reload`, `/tick rate 80`,
> `/function`; no cheats → Open to LAN → Allow Cheats: ON).

1. Run `prepare_all.py` for the target profile/world, have the **user double-click
   `dist\DEPLOY_TO_GAME.bat`** to install (see the handoff section above), then fully restart
   Minecraft if any jar in `mods/` changed.
2. In-game, **in this exact order** (same as [SKILL.md](SKILL.md) step 4 / [QUICKSTART.md](QUICKSTART.md) step 4):
   1. `/reload` — register the datapack functions.
   2. **`/tick rate 80` — ⚠ YOU must type this manually.** The machine does **NOT** self-set the
      tick rate (auto-set via a command block was tested and does **not** work). Without it,
      playback is **~4× too slow** and melody-cut timing is off.
      **⚠ This speeds up the ENTIRE world** (crops, mob AI, redstone, everything) — be careful on
      a shared/multiplayer world, and run `/tick rate 20` afterward to set it back.
   3. **Confirm the resourcepack** — the installer already enabled `qzpno_mv` in `options.txt`;
      in **Options → Resource Packs** verify `qzpno_mv` is on the right (selected) side.
   4. `/function <ns>:setup` (wait for "built") → press the **[播放]/[play]** sign-button.

> **No sound?** Run `python scripts/doctor.py --dist dist --profile-dir <profile> --world-dir
> <world>/datapacks --mc-version <ver> --ns <ns>` first — it prints a ✓/✗ checklist with a fix
> under each ✗. 9 times out of 10 it's the resourcepack not enabled, `/tick rate 80` not typed,
> RedPiano/Fabric API missing (or a **version-mismatched** mod jar) in `mods/`, or Minecraft not
> restarted after jar changes — see the triage box at the top of [QUICKSTART.md](QUICKSTART.md).

## What's in this folder

| Path | What |
|---|---|
| `scripts/build_machine.py` | the build CLI (this is the entry point you run) |
| `scripts/build_particles.py` | optional: music-synced particle/command tracks (see docs/PARTICLES.md) |
| `scripts/prepare_all.py` | preferred handoff CLI: stages datapack + resourcepack + RedPiano/Fabric API jars into `dist/` and emits `dist\DEPLOY_TO_GAME.bat` (the user double-clicks it to install; verify with `deploy_bundle.py --verify dist`) |
| `scripts/deploy_bundle.py` | `--verify dist`: checks the `DEPLOY_RECEIPT.txt` handshake — the only proof the `.bat` really installed into the game |
| `scripts/doctor.py` | `--dist dist [--profile-dir --world-dir --mc-version --ns]`: one-shot "no sound?" health check — numbered ✓/✗ list, a fix under each ✗, final VERDICT; all-green exits 0 |
| `scripts/midi_report.py` | `--midi <mid> [--form]`: pre-build MIDI quality check (duration / family mix / est. dropped notes / est. footprint / one-line verdict) — run before choosing a form |
| `scripts/fetch_binaries.py` | `--mc-version <ver>`: resolve the version-matched RedPiano jar and verify bundled `assets/qzpno_mv.zip`; `--gen-manifest <dir>` (re)writes the manifest |
| `scripts/build_resourcepack.py` | version-driven `qzpno_mv` resourcepack repack (`--mc-version`; `--from-zip` derives any 1.21.x pack from one shipped zip, or `--samples-root` builds from scratch — see BINARIES.md) |
| `scripts/mod_build.py` | low-level helper: prints/applies the verified mod toolchain per `--mc-version`; `prepare_all.py` runs the build by default |
| `scripts/redpiano_core.py`, `params_schema.py`, `generators/` | the engine (`VERSION_TABLE` in `redpiano_core.py` is the single source of truth for per-version facts) |
| `assets/demo.mid`, `assets/redpiano_map_multi.json` | bundled test MIDI + the 103-block instrument map |
| `designer/*.html` | browser tools to customize routing + particle placement (optional) |
| `SKILL.md` | the agent-onboarding flow (collect inputs → pick form → build → install) |
| `QUICKSTART.md` | end-to-end checklist + "no sound?" troubleshooting |
| `docs/CONTRACT.md` | the build-script interface spec | 
| `docs/FEATURE_MATRIX.md` | authoritative capability table (which forms do what) |
| `docs/PARTICLES.md`, `docs/MOD_ARCHITECTURE.md` | particle workflow / mod internals |
| `BINARIES.md` | how to obtain/build the two large binaries (mod jar + resourcepack) |

## Reusing this package (self-distribution)

**Datapack-only builds (`scripts/build_machine.py`) are self-contained within this folder**:
every script, the test MIDI, and the instrument map it needs live under
`minecraft-redstone-music/` (it only reaches `../assets/`, still inside this same folder tree).
Invoke it with folder-relative or absolute paths — the scripts resolve their own assets relative
to themselves, so they run from any working directory. No Claude-specific loader, registry entry,
or environment variable is required for this path.

**The full runtime pipeline (`prepare_all.py`, `fetch_binaries.py`, `mod_build.py`) needs the
whole repo**, not just this folder — see the "Clone the whole repo" note near the top of this
file. Those scripts auto-detect sibling paths **outside** `minecraft-redstone-music/`:
`../../binaries` (prebuilt jars), `../../mod/redpiano` (mod
source). If you copy only `minecraft-redstone-music/` elsewhere, those lookups won't find
anything — the RedPiano jars still need sibling `binaries/`, while `qzpno_mv.zip` stays inside
this skill's `assets/`. These runtime assets matter only
**in-game**, not to build a bare datapack.

## Scope

**Family A only** — RedPiano mod, real note blocks, `/tick rate 80`. Audio sample-slicing
(`method=slice`, "Family B") is a different external project and is **out of scope** (the build
scripts hard-fail on it). If the user has only an MP3 and wants the original timbre, tell them this
tool needs a MIDI.
