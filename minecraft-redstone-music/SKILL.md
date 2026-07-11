---
name: minecraft-redstone-music
description: >-
  Turn a MIDI file into a playable Minecraft redstone music machine using real
  note blocks (RedPiano mod, Family A). Use this when the user wants to play a
  song / MIDI in Minecraft with redstone or note blocks, build a note-block
  song machine, or convert MIDI to a redstone music build. Triggers on requests
  like "把 MIDI 在 Minecraft 里用红石播放", "note block song", "MIDI to
  redstone music", "用红石播放这首歌", "做一个音符盒播放机", "redstone jukebox
  from MIDI". Works on ANY Minecraft Java version: 1.21..1.21.10 is a fully
  automated fast path, and every other version (old-version requests like
  "在 1.12/1.16/1.20 里用红石做音乐", "redstone music on 1.16.5", "note block
  song on an old version") is served by the craftsman path — the skill hands
  the agent domain knowledge, tactics, and verification so it builds by hand.
  Multi-instrument (piano/bass/lead/pad/drums), melody-cut, and a visual layout
  designer are supported. Family B (audio sample-slice) is out of scope.
---

<!-- The YAML block above is OPTIONAL metadata for Claude Code's skill loader (name +
     trigger phrases). Other agents/platforms can ignore it — there is no loader to satisfy;
     just read the body below (or README.md) and run scripts/build_machine.py. -->

# Minecraft Redstone Music (Family A — RedPiano)

## 两条腿:先判断走哪条路 (READ FIRST)

This skill is a **skill, not a one-size tool** — it plays a MIDI as redstone/note-block
music on **any** Minecraft Java version by choosing between two legs:

- **🟢 快速路径 (fast path) — MC `1.21`..`1.21.10`.** Fully automated: 11 prebuilt jars in
  the repo + a version table that self-syncs `pack_format`/folders/sign dialect. This path is
  high-quality and self-contained — **just follow the numbered steps below.** Don't rebuild or
  route around it.
- **🔨 工匠路径 (craftsman path) — every other version** (≤1.20.6, ancient releases, etc.).
  There's no prebuilt jar and no version-table row, so **you** plan/build/verify a single
  delivery by hand. The skill hands you the domain knowledge, tactics, and verification method:
  read **[docs/VERSION_TACTICS.md](docs/VERSION_TACTICS.md)** — it maps every version generation
  to a machine form, timing strategy, sound strategy, and a verify checklist, all anchored to the
  Codex compatibility report. (Bedrock is out — see VERSION_TACTICS §2.E.)

> **How to pick:** if the user's MC version is `1.21.x` (x ≤ 10) → fast path, the steps below.
> Any other version → open `docs/VERSION_TACTICS.md` and work from there. Everything from here
> to the end of the numbered steps is the **fast path**; the craftsman path lives in that doc.

---

## 这是什么?(给小白看的 30 秒说明)

- **它能干嘛**:你给它一个 MIDI 音乐文件(`.mid`),它就在你的 Minecraft 世界里
  **搭一台机器**,用真正的**音符盒 / 红石音乐**把这首歌弹出来。
- **你需要什么**:Minecraft Java 版 + Fabric 加载器 + **RedPiano 模组** + **qzpno 资源包**
  (Java 21 也要)。这些不用你自己折腾——**agent 会帮你装好/编好**。
- **最简单的玩法**:把你的 `.mid` 文件 + 你的 **Minecraft 存档文件夹** 交给 agent,
  选「**默认预设(推荐)**」,然后照着它打印出来的几步**游戏内命令**做一遍就行。
- **本质上**:这其实是一个 **agent 驱动的自动化工具**。绝大部分活儿都是 agent 在干——
  你只要回答一两个问题、在游戏里敲几条命令、按一下播放按钮,就能听到歌。

> 想自己设计走线 / 形状 / 粒子?可以,但那是**进阶可选项**(见下面第一问的「自定义」)。
> 不想折腾就选默认预设,照样能听到完整的歌。

> **老版本 MC 也能玩(1.16 / 1.12 之类)**:只是不能像 1.21 那样全自动——agent 会读
> `docs/VERSION_TACTICS.md`,按你的版本手工搭一台能响的机器,并**如实告诉你**这个版本能做到
> 什么、音色/精度差在哪(见上面「工匠路径」)。不会因为版本老就直接拒绝你。

---

Convert a MIDI file into a playable Minecraft RedPiano runtime bundle:
**datapack + enabled qzpno_mv resourcepack + installed RedPiano/Fabric API mods**. The datapack is
only the machine logic; sound requires the resourcepack to be present in the
Minecraft profile's `resourcepacks/` folder and selected in `options.txt` /
Options -> Resource Packs.

## 怎么使用 / 安装 (how to use / install this skill)

- **推荐:整仓 clone 后在仓库目录里直接用.** Clone/download the **whole** repo (not just this
  `minecraft-redstone-music/` folder), `cd` into it, and let the agent run the scripts directly —
  no registration step needed. This works with any agent/platform (Claude Code, Trae, Codex, a
  human shell, ...).
- **若要注册成 Claude Code skill,必须保留仓库目录结构.** The YAML frontmatter at the top of this
  file lets Claude Code's skill loader discover and trigger this skill by name. But the scripts
  under `scripts/` resolve sibling paths like `../binaries/` (prebuilt jars) **relative to the repo
  root** — so registering the skill only works if `minecraft-redstone-music/` stays inside the full
  repo tree. **Do not copy just this folder out on its own**; it will build datapacks but silently
  lose access to the prebuilt binaries described in [BINARIES.md](BINARIES.md). (The open-source
  repo does **not** ship a sample-carrying `poc/` — get a resourcepack via
  `scripts/make_demo_samples.py` or your own `qzpno_mv.zip`, see step 1 below.)
- **交付链只支持 Windows.** The generated installer is `DEPLOY_TO_GAME.bat` — a Windows batch
  file. This skill's install path assumes a Windows machine running Minecraft Java Edition. On a
  non-Windows native host, skip the `.bat` and either use `--install-now` (native, non-sandboxed
  hosts only) or copy `dist/` into the profile by hand; there is no `.sh`/`.command` equivalent
  shipped today.

## 用户端流程 (onboarding — 任何 agent / 平台按此驱动用户)

To fulfill a "make Minecraft redstone music from this MIDI" request, collect the inputs
below, then run the build command in step 4.

> **语言跟随用户 (language follows the user).** Talk to the user in **whatever language they used**
> — questions, progress updates, error explanations, and the final delivery summary should all
> follow their language, not default to English or Chinese. Code, commands, and file paths stay
> as-is regardless of language.

> ## ⚠ 交付准则 — AGENT MUST READ before reporting success (the #1 failure mode)
> **You are almost certainly running in a filesystem SANDBOX (Trae SOLO / similar).** In it,
> writing to `C:\Minecraft\...` is silently redirected to a private mirror
> (`%APPDATA%\Roaming\TRAE SOLO CN\VMCache\...`) that the real, natively-running game **never
> reads**. So if you copy the datapack/resourcepack/mod into the profile and "verify" them,
> everything looks fine but the game is unchanged and `/function <ns>:setup` says *Unknown
> function*. This — not a build error — is why past runs "succeeded" yet nothing played.
> Full explanation: **[docs/RUNTIME_SANDBOX.md](docs/RUNTIME_SANDBOX.md)**. The rules:
>
> 1. **Build with `scripts/prepare_all.py`.** It writes the datapack + `qzpno_mv.zip` +
>    mod/Fabric API jars into the workspace `dist/` (the ONE place a sandbox can write
>    reliably) and emits **`dist/DEPLOY_TO_GAME.bat`** with the real paths + a token baked in.
>    Do **not** deploy into `C:\Minecraft\...` yourself, and do **not** hand-roll a
>    `deploy.ps1`/`deploy.bat` — `prepare_all.py` owns pathing, encoding, and options.txt.
> 2. **The last step is the USER's, not yours.** Tell the user to **double-click
>    `dist\DEPLOY_TO_GAME.bat` in Windows Explorer** (a native process, outside the sandbox —
>    that is what actually reaches the game). **Never run the `.bat` yourself** (subprocess /
>    Start-Process): if you run it, it inherits the sandbox and installs into the mirror.
> 3. **The receipt is the ONLY proof.** The song is in-game **only** after
>    `dist\DEPLOY_RECEIPT.txt` exists. Check it with
>    `python scripts/deploy_bundle.py --verify <dist>` (`✓ INSTALLED` exit 0 / `✗` exit 1).
>    Until it's `✓`, report **"built — NOT in game yet; the user must double-click
>    DEPLOY_TO_GAME.bat"**. Never say "installed / you can hear it now" without the receipt.
> 4. **On a genuinely native host only** (a real terminal, not a sandbox) you may add
>    `--install-now` to install inline and skip the `.bat`. Never use it inside a sandbox.
> 5. **工匠路径下诚实降级 (honest downgrade on the craftsman path).** Off the green band you
>    may end up delivering vanilla-timbre note blocks, tick20 timing, a Carpet dependency, or a
>    hand-ported jar — all legitimate. When you do, **say plainly what changed**: which timbre
>    (16 vanilla instruments vs 103 RedPiano samples), what timing precision (tick20 = 4× coarser
>    than tick80), and how much is now manual. **Never dress a craftsman delivery up as the
>    automated fast path**, and never claim RedPiano audio when you actually shipped vanilla
>    tones. An honest "here's what this version can do and what it costs" beats a false "fully
>    supported." (Details per generation: `docs/VERSION_TACTICS.md`.)
>
> **Do not hand-roll a datapack** *on the fast path*. A valid green-band Family A deliverable is
> generated by
> `scripts/prepare_all.py` / `scripts/build_machine.py` and contains a physical note-block
> machine (`setup`, `play`, many `setblock` commands, and a console). **The judgment call is
> whether you shipped a real note-block machine, not which script produced it:** a pack of
> `tick_*.mcfunction` files that only calls `playsound minecraft:block.note_block.*` is a vanilla
> background scheduler pretending to be a machine — it plays through no physical note block, so on
> the fast path rebuild it through the scripts. (The craftsman path may legitimately hand-emit a
> `setblock` list or command-block chain for an old version — still a physical machine, still
> valid; VERSION_TACTICS §2.D. What's never valid is a silent `playsound` scheduler passed off as
> a redstone machine.)
>
> **Sound needs version-matched binaries — jar via `fetch_binaries.py`, resourcepack you supply.**
> The datapack auto-adapts the *commands/format*, but the SOUND needs a **mod jar + `qzpno_mv.zip`
> that match the MC version**; a mismatch makes the note blocks fall back to **vanilla** tones (faint
> harp + booming basedrum). The **mod jar** is self-service: run
> **`python scripts/fetch_binaries.py --mc-version <ver>`** — it reads the shipped
> `binaries/binaries_manifest.json`, resolves the version's jar from the local `binaries/` folder
> (sha256-verified; **local hit = instant**), and prints a VERDICT (listened in-game vs only
> bytecode-checked). The jar is per-version: `fabric.mod.json` pins a `"minecraft"` range and Fabric
> **refuses to load a jar whose range doesn't cover the running game** — `fetch_binaries` selects the
> right one (`redpiano-1.0.0-mc<ver>.jar`). The **`qzpno_mv.zip` resourcepack is NOT in the repo** —
> its piano samples are **Salamander Grand Piano (CC-BY)**, which requires attribution on
> redistribution that was never packaged into the zip, so it ships separately (see
> [BINARIES.md](BINARIES.md) for the credit line; drums are CC0 and bass/lead/pad are
> synthesized, so only the piano slice carries an attribution obligation); `fetch_binaries`
> reports it as `separate` (not a failure) and prints how to build your own. Supply a
> `qzpno_mv.zip` you already
> have and derive a version-matched pack with **`build_resourcepack.py --from-zip <your qzpno_mv.zip>
> --mc-version <ver>`** (a base rp-64 pack serves 1.21.7/1.21.8 directly; other versions get only
> `pack.mcmeta` rewritten), or build from sample folders with `--samples-root`. Then feed the jar to
> `prepare_all.py` via `--prebuilt-mod-jar` (+ `--fabric-api-jar`) and your pack via `--prebuilt-rp`.
> If the target version has **no jar in the manifest**, `fetch_binaries` says so and points you to
> recompile (`mod_build.py --write` + Gradle) — a stripped sandbox usually can't build the jar, so
> prefer a version the manifest already carries. See [BINARIES.md](BINARIES.md).
>
> **NEVER hand-write or fake fabric-api / fabric-loader stubs to force the jar to compile.**
> The Gradle build MUST resolve the **real** fabric-api from `maven.fabricmc.net`. If you can't
> reach that maven (no network, blocked sandbox), the mod build is **BLOCKED** — report it as
> blocked and stop; do **not** hand-roll placeholder classes, empty interfaces, or a stub jar to
> get a green build. A fake dependency + a fake toolchain is a **silent failure the manifest can't
> catch** (it looks built but the mixin was compiled against nothing and plays no sound — this
> really happened). Prefer `--prebuilt-mod-jar <redpiano.jar>` when you can't build honestly. When
> a jar IS produced, sanity-check it before install with `mod_build.py --check-jar` (confirms the
> real fabric-api was resolved, not a stub) as a pre-deploy gate.
>
> **If `fetch_binaries.py` resolves a jar for the target, DO NOT compile the mod at all.** A
> version-matched jar ships in `../binaries/` for every version in the manifest — **11 jars,
> covering `1.21`..`1.21.10`** (see `binaries_manifest.json`). **Currently none of the 11 are
> confirmed by an in-game listen** — all are bytecode-checked only (`mod_build.py --check-jar`
> clean, not yet heard). **1.21.8** had previously been confirmed, but it was just rebuilt with a
> new global `mute` check and its `listened` flag was honestly reset to `false` pending a fresh
> listen after a full restart — see BINARIES.md's "Honesty: currently zero jars are
> listened-confirmed" note before claiming sound works. Inside the sandbox you **do not need and
> must not** run Gradle — run
> `fetch_binaries --mc-version <ver>` and pass its jar as `--prebuilt-mod-jar`. Only when the
> manifest has **no jar** for the target (i.e. outside `1.21`..`1.21.10`) should you recompile, and
> even then a stripped sandbox usually can't — building the mod in one is exactly what tempts the
> fatal fabric-api-stub shortcut above.
>
> **Never claim it "works" before an in-game listen.** A recompiled mixin can compile yet be
> silent or mis-pitched. After the receipt exists, hand off the in-game steps (step 4) and ask
> the user to confirm they actually hear it. Simplest reliable target = **1.21.8 / 1.21.7**.

**前置门槛 (Pre-flight) — confirm these TWO before step 0 (a "no" here means stop or warn):**
   - **(a) Java 版, 不是基岩版 (Bedrock).** This whole pipeline is **Java Edition only** — it
     relies on datapacks, `/function`, `/tick rate`, and a Fabric mod, none of which exist on
     **Bedrock (Windows 10/11 "Minecraft" app, phones, consoles, Realms-Bedrock)**. If the user
     is on Bedrock, **say so plainly and stop** — there is no Bedrock path here. Confirm they run
     the **Java** launcher (Modrinth / official Java launcher / Prism, `.minecraft`/profile folder).
   - **(b) 目标世界已开作弊 / 有 OP.** `/reload`, `/tick rate 80`, and `/function <ns>:setup` all
     require **cheats enabled (single-player)** or **OP (server/LAN)**. If the save was created
     **without cheats**, the quick fix is: pause → **对局域网开放 (Open to LAN)** → **允许作弊: 开
     (Allow Cheats: ON)** → click Start; commands work until you quit the world. Confirm this now,
     or the in-game steps in step 4 will silently fail with "无权限/Unknown or incomplete command."

0. **默认预设 还是 自定义?** — the **default is 默认预设(推荐)**: you pick a good form and
   build; the user only provides the MIDI + save folder. Use it unless the user signals they want
   to shape the build. The **escape hatch** is 自定义: the user designs in the visual HTML tools
   that ship here and exports JSON —
   - `designer/layout_designer.html` — 走线 / 形状 / 尺寸 / 折叠 / 起点 (routing/shape).
   - `designer/particle_editor.html` — 粒子 / 烟花 / 命令方块关键帧 (particles).

   Most users don't know these designers exist, so **mention both by name early** rather than
   burying them in step 5 — that's how the user discovers the option. You don't need a rigid
   two-round quiz; read what the user wants and only ask when it's genuinely ambiguous.

1. **收集输入** — ask for these things:
   - **MIDI 文件** path (`.mid`). **拿到 MIDI 先跑质量预检**, before choosing a form:
     `python scripts/midi_report.py --midi <mid> [--form <form>]`. It prints a build-time preflight —
     duration, instrument-family distribution, estimated dropped notes, estimated footprint, and a
     one-line verdict. **Show that verdict to the user** and let it inform the form choice (step 2):
     e.g. a long/dense MIDI on `swave`/`straight` may report a large footprint → suggest `inplace`.
   - **存档路径** — the world's `datapacks/` folder, for deployment. If it looks like
     `<profile>/saves/<world>/datapacks`, infer `<profile>` from it.
   - **Minecraft profile root** (or confirm the inferred one). The resourcepack must land in
     `<profile>/resourcepacks/qzpno_mv.zip`; a datapack path alone is not enough.
     **Using PCL2 / HMCL with per-version isolation (版本隔离/独立)?** `--profile-dir` must point
     to that specific version's own folder — typically `.minecraft/versions/<你的版本>/` — **not**
     the shared `.minecraft` root. Full guidance: [QUICKSTART.md](QUICKSTART.md) §"--profile-dir".
   - **Resourcepack source — pick exactly one of these four (开源仓库默认走第①条):**
     1. **没有自己的音源?先跑 `python scripts/make_demo_samples.py`**(合成 103 个开放音源到
        `assets/demo_samples/`,纯 numpy,不用网络/ffmpeg,无版权顾虑),再把
        `--samples-root assets/demo_samples` 传给 `prepare_all.py`。**这是开源仓库的默认路径** ——
        本仓库不随附 Salamander 采样,`poc/` 里也没有音源文件,所以「自动探测」不是一个可用的默认值。
        **交付时必须如实告知用户:这是合成 demo 音色,不是 Salamander 真钢琴**;想要真钢琴音色见下面
        第②条 + [BINARIES.md](BINARIES.md)。完整演示链见
        [QUICKSTART.md](QUICKSTART.md) 顶部「只想先听个响」小节。
     2. **`--prebuilt-rp <qzpno_mv.zip>`** — a `qzpno_mv.zip` **you already have** (the sampled
        pack ships separately; build/derive one per [BINARIES.md](BINARIES.md), the piano samples
        are Salamander Grand Piano under CC-BY and need attribution if you redistribute — see
        BINARIES.md for the credit line).
     3. **`--samples-root <dir>`** — a full samples folder you have of your own (containing
        `samples_manifest_*.json` + `samples_*/*.ogg`), when it is **not** the demo folder from
        option ①. Pass an absolute path or one relative to your shell's cwd — there is no
        working auto-detect fallback in the open-source repo (the old `../../poc` auto-detect
        assumed a private, sample-carrying checkout; the public repo's `poc/` ships **without**
        any samples, so omitting `--samples-root` here will fail, not silently find something).
     4. **`--skip-resourcepack`** — build the datapack/mod runtime **without** staging any
        resourcepack. **诚实后果(取决于装没装模组):** 装了 **RedPiano 模组**时 → **彻底静音**
        (模组的 mixin 会取消原版音符盒声音、改播 `qzpno:` 自定义事件，没有资源包=那个事件没有
        任何 `.ogg` 支撑=无声);**不装模组**时 → 原版 16 种音符盒音色。**它绝不会**"自己退回原版
        音色当降级"。只有当匹配的 `qzpno_mv.zip` 已经装好**并启用**在目标 profile 时才用本开关。
        换音色/自备包的正规做法见本文档下方 [「音色与资源包」](#音色与资源包换音色--默认加载保障)。
   - **Mod status**: inspect `<profile>/mods/`, but do not stop there. Default behavior is to
     build/install RedPiano and install/reuse/download the matching Fabric API automatically;
     only the final Minecraft restart and listen test remain user actions.
   - **MC 版本号** — default & verified = **`1.21.8`**. The **automated** band is
     **`1.21`..`1.21.10`** (tier "green"): one `--mc-version` flag self-syncs pack_format,
     folders, the pack.mcmeta shape (single ≤1.21.8 / min-max ≥1.21.9), and the sign-NBT
     dialect (SNBT ≥1.21.5). **Outside this band, switch to the craftsman path** — don't treat
     it as a dead end. Below 1.20.3 loses `/tick rate` (so tick80 needs Carpet or a tick20
     downgrade), 1.20.3–1.20.6 adapts the data but the mod wants a one-line Java port, and older
     versions step down through the primitives — **all of this is mapped, per generation, in
     [docs/VERSION_TACTICS.md](docs/VERSION_TACTICS.md)**. The build scripts still `raise` off the
     green band (they only *auto*-build green), and their error text now points here too; that's a
     signal to open VERSION_TACTICS and build by hand, not to stop.
   > If the user uploads an **MP3 / audio** instead of MIDI: only the **slice** form
   > (Family B) reproduces original timbre, and that lives in the **external
   > `mc-noteblock-demo` repo — this skill cannot build it.** Say so and ask for a MIDI.

2. **选播放形态 — pick a form.** Default = **`inplace` 原地调色板**: functionally complete and
   the user confirmed a build as "特别好", but it has been **tested in-game fewer times** than
   `swave` — reach for it unless there's a reason not to. Escape hatch: if the user wants the
   "playhead travels the line" animation, offer **`swave` S 型曲折直线** (`--form swave`) — this
   form **has been tested in-game multiple times and confirmed working**; custom routing/particles
   go through the HTMLs in step 5. Confirm the form when it's ambiguous, but you don't need a
   mandatory extra round-trip when the user already told you what they want (or said "just use the
   default"). The `midi_report.py` verdict (step 1) can steer this — a long/dense MIDI on `swave`
   reports a large footprint, nudging toward `inplace`.
   > **时长经验值:** `swave`/`multilane` 的占地随歌曲时长增长,长歌容易撞上 360 区块的
   > forceload 软上限(超限需 `--force-cap` 才能强建,不是保证不断音)。经验值:`swave` 约
   > **≤6 分钟**、`multilane` 约 **≤4 分钟** 以内通常安全;更长的歌优先选 **`inplace`**——
   > 它是原地调色板,占地基本恒定,不随时长增长。拿不准就先跑 `midi_report.py` 看估算占地。

3. **备好 mod + 音效包** for the chosen version (any of 1.21..1.21.10) — **start with
   `fetch_binaries.py`**:
   - The RedPiano mod jar + `qzpno_mv` resourcepack are runtime assets, not optional extras.
     `prepare_all.py` **stages** them into the workspace `dist/` (the native `.bat` then
     installs them — see step 4). It does not copy into `<profile>` from a sandbox.
   - **the jar is one command** — `python scripts/fetch_binaries.py --mc-version <ver>`
     reads `binaries/binaries_manifest.json` and resolves the version's jar from the local
     `binaries/` folder (sha256-verified; local hit is instant). It also reports the resourcepack
     as `separate` (○) with self-supply guidance — that's expected, not an error. Its VERDICT tells
     you whether that jar was **listened in-game** or only **check-jar clean** (so you know to listen
     once). If the manifest has **no jar for the version**, it says so and points you to build one.
   - **resourcepack (you supply it — not in the repo)** — the sampled `qzpno_mv.zip` ships
     separately because its piano samples (Salamander Grand Piano, CC-BY) need attribution on
     redistribution that isn't packaged into the zip (see [BINARIES.md](BINARIES.md)). Provide your own and pass it as
     `--prebuilt-rp`. Have a `qzpno_mv.zip`? derive a version-matched pack:
     `build_resourcepack.py --from-zip <your qzpno_mv.zip> --mc-version <ver> --out <derived.zip>`
     — rewrites only `pack.mcmeta` (rp_format + single/minmax shape from the version table), no
     sample folder needed; a base rp-64 pack serves 1.21.7/1.21.8 directly. `prepare_all.py`
     validates the rp_format matches, so a mismatch is caught either way. (Building from scratch —
     `--samples-root <dir>` — is also supported and pure stdlib: it only **copies already-encoded
     `.ogg`** into the zip, no ffmpeg. Prerequisite: a samples folder with `samples_manifest_*.json`
     + `samples_*/*.ogg`; see BINARIES.md for sample licensing.)
   - **mod** — pass `fetch_binaries`'s jar as `--prebuilt-mod-jar`. A stripped sandbox usually
     cannot run Gradle/JDK, so prefer the resolved jar. Only when the manifest lacks the version
     do you retarget (number-only within 1.21.x: `mod_build.py --write` + a Gradle build on a
     native host, then `fetch_binaries --gen-manifest` to register it). The mixin binds to
     internal NoteBlock bytecode, so a recompiled jar still needs **one in-game listen**. (Below
     1.21 the mod needs a Java source-port — see `docs/MOD_ARCHITECTURE.md`.)

4. **生成 + 交付** — one end-to-end command; it builds into `dist/` and emits the native
   installer (it does **not** and should **not** write into `C:\Minecraft` from a sandbox):
   `python scripts/prepare_all.py --midi <mid> --ns <ns> --origin X Z Y --mc-version <ver>
   --form swave --world-dir <profile>/saves/<world>/datapacks --profile-dir <profile>
   [--samples-root <dir> | --prebuilt-rp <qzpno_mv.zip>]
   [--prebuilt-mod-jar <redpiano.jar>] [--fabric-api-jar <fabric-api.jar>] --dist dist`.
   `--world-dir`/`--profile-dir` are the **real** game paths — they get baked into the
   generated `.bat`, not written to now. For **1.21.8 / 1.21.7**, pass the prebuilt
   `--prebuilt-mod-jar` (ships in `binaries/`) plus a `--prebuilt-rp` you supply (the sampled
   resourcepack is **not** in the repo — build/derive your own, see step 3), so no Gradle/JDK is
   needed. No resourcepack yet? run `python scripts/make_demo_samples.py` and pass
   `--samples-root assets/demo_samples` (see step 1's resourcepack option ①) — there is **no**
   working auto-detect fallback in this open-source repo. Do not add `--skip-*` flags unless the
   user explicitly asks for a partial artifact.

   > **⚠ `--origin` order is `X Z Y`, NOT `X Y Z`.** The in-game F3 debug screen shows coordinates
   > as `X Y Z` — copying them in that order swaps height and Z and puts the machine somewhere
   > wrong (often underground or in the wrong spot). Read X, Z, Y off F3 in that order when typing
   > the flag. Full site-picking guidance: [QUICKSTART.md](QUICKSTART.md) §1a/§2.
   > **新手不必纠结坐标**:走默认预设时直接用 `--origin 0 0 100` 就行——进游戏后机器会出现在
   > 世界水平坐标 (0, 0)、高度 100 附近(开阔地多半没问题,若那里有地形挡着就往上调高度)。
   > 或者告诉 agent 你现在站在哪(报一下 F3 上的 X/Z/Y),由 agent 帮你换算成 `--origin` 的
   > `X Z Y` 顺序——不需要自己心算坐标转换。
   > **⚠ `--ns` must be a name you haven't used before** in this world's `datapacks/` folder — an
   > existing datapack directory with the same namespace gets **overwritten wholesale**.
   > **多歌共存:** 同一个世界里可以建多首歌(各自不同的 `--ns`),本版本起每首歌的
   > forceload/开关都按自己的 `--ns` 隔离,不会互相踩掉对方的建筑或播放状态——但**同时只应该
   > 播放一首**(两首同时播会混音,而且都要人站在附近才不断音)。**旧版本生成的歌**(在这次
   > forceload 隔离修复之前建的)仍然可能和新歌互相干扰;与新歌共存前,建议先对旧机器跑
   > `/function <旧ns>:cleanup` 拆除重建,而不是让新旧数据包一起留在 `datapacks/` 里。
   If `prepare_all.py` exits nonzero, fix the missing dependency or report blocked — do not
   summarize it as complete.

   **▸ 版本参数化黄金路径 (version-parameterized golden path).** For ANY supported version, the
   four steps are the same — only `<ver>` changes:
   1. **Ask the user their MC version** (`<ver>`, e.g. 1.21.7 / 1.21.8 / 1.21.9).
   2. **`python scripts/fetch_binaries.py --mc-version <ver>`** — resolves the **jar** from the
      local `binaries/` folder (local hit = instant; note its VERDICT re: listened vs
      check-jar-only) and reports the resourcepack as `separate` (you supply it). No manifest jar
      for `<ver>`? it tells you to build one (or pick a version that has one).
   3. **Supply your own resourcepack** (not in the repo). From a `qzpno_mv.zip` you have, derive a
      version-matched pack:
      `python scripts/build_resourcepack.py --from-zip <your qzpno_mv.zip> --mc-version <ver>
      --out dist/qzpno_mv.zip`. For 1.21.7/1.21.8 (both rp 64) you can use the base zip as-is; other
      versions get only `pack.mcmeta` rewritten. (No `qzpno_mv.zip`? build from sample folders with
      `--samples-root` — see BINARIES.md for sample licensing.)
   4. **`prepare_all.py`** as below, with `--prebuilt-rp` / `--prebuilt-mod-jar` pointing at the
      fetch/derive outputs. **Fabric API version note:** `binaries/` only bundles the **1.21.7**
      Fabric API jar in-repo; for any other `<ver>`, leave `--fabric-api-jar` unset (default
      `auto`) so `prepare_all.py` downloads the matching build from Modrinth automatically — this
      needs network. **Offline on a non-1.21.7 version?** you must supply your own matching
      `--fabric-api-jar <jar>` ahead of time; there is no bundled fallback for it. Optionally gate
      the mod jar first with `mod_build.py --mc-version <ver> --check-jar <jar>`.

   **▸ 打包分发场景 — concrete example (Fabric 1.21.7, offline, prebuilt jar).** The golden
   path above, instantiated for the common handoff: a repo-snapshot with a sibling `binaries/`
   folder and a user on **Fabric 1.21.7**. Run it **from the `minecraft-redstone-music/`
   directory**, so `../binaries/…` resolves. Every path here is real — `--world-dir` and
   `--profile-dir` **must be the user's actual game paths (ask them first)**; the two shown are
   only placeholders. The **jar + Fabric API** come from `binaries/`; the **`--prebuilt-rp` is a
   resourcepack you supplied** (not in the repo — build it per step 3 first). With all three passed
   explicitly, **no Modrinth / network is needed**:

   > bash 语法（行尾 `\` 续行）；PowerShell 用户请用 Git Bash 运行，或把整条命令改写成不带 `\` 的单行。

   ```bash
   python scripts/prepare_all.py \
       --midi <mid> \
       --form swave \
       --ns  mysong \
       --origin 0 0 255 \
       --mc-version 1.21.7 \
       --world-dir  "<profile>/saves/<world>/datapacks" \
       --profile-dir "<profile>" \
       --prebuilt-rp      dist/qzpno_mv.zip \
       --prebuilt-mod-jar ../binaries/redpiano-1.0.0-mc1.21.7.jar \
       --fabric-api-jar   ../binaries/fabric-api-0.129.0+1.21.7.jar \
       --dist dist
   ```

   Notes: the **mod jar is the `mc1.21.7` one** (the `mc1.21.8` jar declares `~1.21.8` and Fabric
   would reject it on a 1.21.7 game); a base rp-64 `qzpno_mv.zip` is the same for 1.21.7/1.21.8
   (`--prebuilt-rp dist/qzpno_mv.zip` = the pack you built in step 3). If the supplied
   jar is still named `…-mc1.21.7-UNVERIFIED.jar`, use that filename verbatim (the `-UNVERIFIED`
   just means "listen once to confirm"); optionally gate it first with
   `python scripts/mod_build.py --mc-version 1.21.7 --check-jar ../binaries/redpiano-1.0.0-mc1.21.7.jar`
   (exit 0 = bytecode-clean, safe to install). For a **1.21.8** game, swap `--mc-version 1.21.8` and
   the mod jar to `../binaries/redpiano-1.0.0-mc1.21.8.jar`, and **drop the `--fabric-api-jar`
   line entirely** — `binaries/` only ships the **1.21.7** Fabric API jar
   (`fabric-api-0.129.0+1.21.7.jar`), which does **not** match a 1.21.8 game; omitting the flag
   lets `prepare_all.py` auto-download the matching build from Modrinth instead (needs network —
   offline on 1.21.8, supply your own matching jar). Every flag
   above is real on the current `prepare_all.py` — confirm any variant with
   `python scripts/prepare_all.py --help`.

   **Then deliver the one manual step and stop claiming more than the receipt proves:**
   - Tell the user (point at the exact path): **「双击 `dist\DEPLOY_TO_GAME.bat`（在 Windows
     资源管理器里，不要让 AI 代跑）就能装进游戏」**. That native double-click copies the
     datapack/resourcepack/mods into the real profile, enables `qzpno_mv`, and writes
     `dist\DEPLOY_RECEIPT.txt`.
   - **Verify before you claim success:** `python scripts/deploy_bundle.py --verify dist`.
     Only `✓ INSTALLED` means the song is really in the game. No receipt → say **"built, NOT
     in game yet — user must double-click DEPLOY_TO_GAME.bat"**. See
     [docs/RUNTIME_SANDBOX.md](docs/RUNTIME_SANDBOX.md).
   - After the receipt exists, the in-game steps (the `.bat` also prints these), **in order**:
     1. full restart Minecraft if the mod jar changed (a jar swap needs restart, not `/reload`).
     2. `/reload` — register the datapack functions.
     3. `/tick rate 80` — **⚠ 用户必须自己手动敲这一条**. Without it playback is **~4× too
        slow** and melody-cut timing is off. **The machine does NOT self-set it.**
        > **⚠ `/tick rate 80` speeds up the ENTIRE world** — crops, mob spawning/AI, redstone,
        > everything, not just the music machine. Be cautious on a multiplayer/shared world.
        > **Remember to `/tick rate 20` back** when done listening.
        > **⚠ Tick rate does NOT persist across sessions.** Quitting/rejoining the world or
        > restarting the game silently resets it back to `20` — the user must retype
        > `/tick rate 80` **every session**, even if they set it correctly last time.
        > **⚠ Server overload can defeat tick rate even when it IS set.** A big machine
        > (hundreds of forceload chunks) plus a heavy world (Distant Horizons, Terralith-style
        > terrain gen mid-generation) can push the server past what it can simulate; watch the
        > log for `Can't keep up! Running N ticks behind` (seen as high as ~8914 ticks in
        > testing) — when that appears, real TPS has already collapsed regardless of the
        > `/tick rate 80` setting, and playback sounds slow/dragging/choppy. Mitigate with a
        > smaller-footprint form (`inplace`), disabling Distant Horizons or lowering render
        > distance, waiting for nearby chunks to finish generating before playing, or not
        > running multiple machines at once.
        > **若用户报"第二次播放变慢了"**:先问**是否重进过世界/重启过游戏**(tick rate 重置是最常见
        > 原因),再看服务器日志有没有 `Can't keep up!`(服务器过载是第二常见原因),排除这两条之后
        > 再怀疑是构建/生成器本身的问题。
     4. **确认资源包** — the `.bat` already enabled `qzpno_mv` in `options.txt`; the user just
        confirms it's on the right (selected) side in Options → Resource Packs.
     5. `/function <ns>:setup` — build the physical machine + console at the origin.
     6. **非超平坦世界(Terralith 等地形生成 mod)先按控制台的 `[preload]`** — 把玩家切成旁观者、
        沿机器路径每 128 格 tp 一次,但走的是**验证式等待**:每段都等下一段区块真正加载完成
        (`loaded` 判定通过)才推进,不是固定时间间隔硬等;头顶有一条**蓝色 bossbar** 显示"第几段/
        共几段"进度,地形生成越慢等得越久是正常现象。跑完自动传回控制台、置 READY 并提示完成;
        超平坦世界可跳过。
     7. press the **[play]** sign/button. **⚠ `[play]` 现在带 preload 门禁** — 沿线远端区块没
        加载完时会拒绝启动并提示先按 `[preload]`,这是有意为之,不是 bug。**⚠ `[play]`(连同
        `setup`/`prosetup`)现在会自动临时改 5 个高负载 gamerule(性能模式/perfmode:
        `randomTickSpeed`→0、关生物生成/火/天气/昼夜)给 tick80 播放减负**,`[stop]`/播放结束/
        拆机时会自动精确恢复;若游戏是闪退/强杀等异常方式退出、没来得及恢复,重进后手动敲
        `/function <ns>:perfoff` 即可恢复。
        > **中途想停/重播?** 按控制台的 **`[stop]`**——它现在会物理挖断行进中的中继器(4 游戏刻
        > 后自动补回),所以停下后可以**立刻**重按 `[play]` 干净重播,不用等整首歌播完;手速极快
        > 连续按时看到"机器复位中,约1秒后再按"提示属正常复位锁(ARM lock),稍等即可,不是 bug。
     8. (展示用,可选) 控制台后方有一个 **`[音色展台]`** 按钮,按下会 tp 到一座实体展台逐格试听
        真实发声路径——**⚠ 别右键展台里的音符盒,会改音高毁掉展品,只用侧面石按钮试听**。
   > **⚠ 「完全没声」先跑一键体检 `doctor.py`, 再看这三项.** The fastest triage is
   > `python scripts/doctor.py --dist dist --profile-dir <profile> --world-dir <world>/datapacks
   > --mc-version <ver> --ns <ns>` — it prints a numbered ✓/✗ checklist (receipt present?
   > `qzpno_mv` enabled with the matching `pack_format`? mod + fabric-api in `mods/`? datapack in
   > the world? tick-rate reminder) with a **fix line under every ✗** and a final **VERDICT**;
   > all-green = exit 0. Then, in order: ①`dist\DEPLOY_RECEIPT.txt` 在不在(不在=根本没部署,让用户
   > 双击 `.bat`);② `qzpno_mv` 是否在 Options → Resource Packs 右侧「已选用」(其 `pack_format`
   > 必须匹配 MC 版本:1.21.8/1.21.7 = **64**,不匹配 MC 会静默禁用 → 全静音);③ 有没有手动敲
   > `/tick rate 80`。
   > Bare `scripts/build_machine.py` is datapack-only; for a playable result use
   > `prepare_all.py` (it stages the resourcepack + mod and emits the native installer).
   > **给 agent 的两条常见排查(非"没声"类):**
   > - 用户问**"怎么卡在预加载/`[preload]` 半天不动"** → 这是**地形生成慢**,属正常现象(§4 步骤 6:
   >   现在是验证式等待,不是固定间隔硬等),让用户看头顶**蓝色 bossbar** 的进度,不要当成卡死去
   >   重启;地形生成 mod(Terralith 等)越重的世界越慢。
   > - 用户报**"gamerule 被改了 / 生物不刷了 / 庄稼不长了"** → 这是性能模式(perfmode)的临时改动
   >   没被自动恢复,通常因为闪退/强杀游戏,没走到 `[stop]`/播放结束/拆机这几个自动恢复点,不是
   >   bug 也不需要重新生成机器——让用户在游戏里手动敲 **`/function <ns>:perfoff`** 即可恢复。

5. **自定义需求 → 两个 HTML**(用法都是:浏览器里手动填 → 直接复制或导出 JSON 交给 agent):
   - `designer/layout_designer.html` — **自定义走线方式**(形态 / 尺寸 / 折叠 / 起点)。
     导出 layout params JSON → 传给 `build_machine.py --params`. params JSON 可选加一个
     `protection` 字段(`straight`/`swave`/`custom`/`multilane` 支持,`inplace` 不支持)开一层
     可选保护壳,产物会多出 `<ns>:prosetup`(代替 `setup`,先分段建壳再建机器)和
     `<ns>:unprotect`(只拆壳);字段与用法见 [QUICKSTART.md](QUICKSTART.md) §7「区块保护」。
     > **⚠ agent 若要替用户把 `protection.clear_interior` 设为 `true`,必须先在聊天里向用户
     > 明确确认**——它会真的清空保护壳包围盒内的地形/水/岩浆,且不可逆,不能替用户默认打开。
   - `designer/particle_editor.html` — **自定义关键帧 + 命令方块位置**(粒子 / 烟花 / 任意命令,
     同步音乐时间与世界坐标)。导出 particle_keyframes JSON → `build_particles.py`(见 docs/PARTICLES.md).

## Forms & pipeline (details live in references)

Five forms share one MIDI→resolve→layout→melody-cut→emit pipeline. Pick by footprint/effect;
the full capability table, per-form verified status, and the 6-stage pipeline are in the
authoritative reference — **don't re-derive them here**:

- **`inplace`** — in-place palette, tiny footprint, **user-verified "特别好"**; functionally
  complete but tested in-game fewer times than `swave`. The default.
- **`swave`** — marching-pulse S-wave with the "playhead travels the line" effect;
  **tested in-game multiple times and confirmed working**. Offer when the user wants the animation.
- **`straight` / `custom` / `multilane`** — long line / drawn waypoint route / one lane per
  voice. All v1, geometry-confirmed. `custom` and `multilane` need a designer `--params` JSON.

→ **Capability matrix + pipeline + known constraints:** [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md)
(authoritative single source of truth; supersedes DEVLOG). Multi-instrument uses the 103-block
`assets/redpiano_map_multi.json`; melody-cut is event-level; unconsumed designer fields hard-fail
(`docs/CONTRACT.md` §2). Craftsman-path form choices per version: `docs/VERSION_TACTICS.md`.

## Install prerequisites (fast-path #1-silence checklist)

The low-level machine generator produces a datapack, but the playable deliverable is the
datapack plus active runtime assets. For normal requests, `prepare_all.py` owns these
steps by default; this section is a checklist, not a reason to stop and hand work back.

1. **Fabric Loader + Fabric API + Java 21** for the target Minecraft version
   (verified default **1.21.8**; supported auto band **`1.21`..`1.21.10`**). Install **Fabric
   Loader** first via the official installer: <https://fabricmc.net/use/installer/>. The script
   auto-detects JDK 21/Gradle for RedPiano builds and downloads/reuses Fabric API when
   possible; missing toolchain/network means **not ready**, not success.
2. **RedPiano mod jar** in `<profile>/mods/` (then restart Minecraft — a jar swap needs a
   full restart, not `/reload`). The easy path is `fetch_binaries.py --mc-version <ver>` →
   pass its jar as `--prebuilt-mod-jar`. `prepare_all.py` can also build one via Gradle when
   the manifest lacks the version and a JDK 21 is present. RedPiano is **server-side logic**
   (`docs/MOD_ARCHITECTURE.md` §0/§6.4 — it gates on `ServerLevel`/`ServerPlayer`); for
   **singleplayer** just install it like any client mod (the integrated server runs on your
   machine). For a **dedicated multiplayer server**, install RedPiano on the **server**; it is
   shipped with `environment: "*"` so a client copy is harmless but not load-bearing.
3. **`qzpno_mv` resourcepack** placed in `resourcepacks/` and **manually enabled by the
   user** in **Options → Resource Packs** (moved to the right/selected side). `prepare_all.py`
   copies the zip and tries to select it in `options.txt`, but the user MUST still confirm
   the pack is on the selected side in-game — forgetting this is **the #1 cause of total
   silence**. If its `pack_format` does not match the MC version, MC **silently disables it →
   total silence.** The `pack_format` is version-specific (e.g. **64** for 1.21.8); a base
   `qzpno_mv.zip` is rp 64, and for any other version `scripts/build_resourcepack.py --from-zip`
   derives a matching pack from it (rp_format + shape from the version table, no re-encoding needed).
   This zip is **not in the repo** — its piano samples (Salamander Grand Piano, CC-BY) need
   attribution on redistribution that isn't packaged into the zip, so it ships separately; **you
   supply your own** (build/derive it per [BINARIES.md](BINARIES.md), which has the credit line).
   `fetch_binaries.py` resolves only the mod jar, not this pack.
4. **tick80** is required for playback timing. **The user must manually type `/tick rate 80`
   in-game** before pressing `[play]` — the machine does **NOT** self-set it (auto-set via a
   command block was tested and does not work). Without it, playback runs **~4× too slow** and
   melody-cut timing is off. Make this a required in-game step, not just a diagnostic.
   **⚠ It also does not persist across sessions** — quitting/rejoining or restarting resets it
   to `20`, so this is a per-session step, not a one-time setup. If a session that already had
   tick80 set starts sounding slow again, also check the server log for `Can't keep up! Running
   N ticks behind` (server overload can defeat tick80 even when it's set) — see step 4's
   in-game-order notes above for the full triage.

> **Large binary assets bundled separately.** The prebuilt **RedPiano mod jar** and
> **`qzpno_mv.zip`** resourcepack are large binaries and are **not** in this folder.
> Bundle/distribute them alongside it — full obtain/build instructions are in
> **[BINARIES.md](BINARIES.md)**. The text assets that *are* bundled here are
> `assets/redpiano_map_multi.json` (103-block instrument map) and `assets/demo.mid`.

## 音色与资源包(换音色 · 默认加载保障)

> 一句话详版在 [BINARIES.md](BINARIES.md);QUICKSTART.md 顶部有小白版。这里回答三件最常被担心的事。

**① 默认链路一定会启用资源包吗?会,没有"试一下失败就退回原版"的静默降级。** 默认走
`prepare_all.py`:它把 `qzpno_mv.zip` 塞进 `dist/`,生成的 **`DEPLOY_TO_GAME.bat`** 在你双击安装时
会**主动把 `file/qzpno_mv.zip` 写进 `options.txt` 的 `resourcePacks` 数组**(并从
`incompatibleResourcePacks` 移除),即"强制选用"。它不会"尝试加载、发现不行就悄悄用原版顶替"——
要么装好并选用,要么在 `.bat`/`doctor.py` 里**明确报错**告诉你哪一步没成。唯一需要你手动确认的
是进游戏后在 **选项 → 资源包** 里看一眼 `qzpno_mv` 在右侧"已选用"(这一步谁也替不了)。
> ⚠ **装的时候先完全退出 Minecraft**:`options.txt` 会在游戏退出时被内存里的旧设置覆盖,游戏开着
> 双击安装器 = 启用被冲掉、进游戏发现没生效。安装器和 `README_部署说明.txt` 现在都会检测并警告。

**② 音色不兼容/资源包缺失会怎样?——装了模组就是"彻底静音",不是退回原版。** 这是必须诚实交代
的一点:RedPiano 模组的 mixin **取消了原版音符盒声音**,改播 `qzpno:<id>` 自定义音效事件。所以——
- 装了模组 + 资源包**格式不符**(MC 静默禁用)或**缺失** → 那些 `qzpno:` 事件没有 `.ogg` 支撑 →
  **完全没声**(不是原版 harp/bass 音色);
- **只有不装模组**时,音符盒才响原版 16 音色;
- 想验证到底响没响:`doctor.py` 全绿时会给你一条 **`/playsound qzpno:pno_c4_mf master @s`**,进游戏
  敲,听到钢琴=资源包生效,报 `Unknown sound event` 或没声=包没启用/格式不符。

**③ 想换音色怎么办?两条正规路径,都不会"锁死一个包"。**
- **换采样重打包(想要不同真实音色/自己的采样):**
  `python scripts/build_resourcepack.py --mc-version <ver> --samples-root <你的采样目录> --out my.zip`,
  再把 `my.zip` 作为 `--prebuilt-rp` 传给 `prepare_all.py`。采样目录结构=每个乐器一个
  `samples_<inst>/` 文件夹 + 一个 `samples_manifest_<inst>.json`(见 BINARIES.md「Sampled
  resourcepack」)。没有采样又想先听响:`python scripts/make_demo_samples.py` 合成一套开放 demo 音源。
- **自备打好的 `.zip`(`--prebuilt-rp <zip>`):** 你的 zip 必须满足两个契约,否则会被拒或部分静音:
  1. **`pack_format` 要对上目标版本**(1.21/1.21.1=34、1.21.4=46、1.21.5=55、1.21.6=63、
     **1.21.7/1.21.8=64**、1.21.9/1.21.10=69 且用 `min_format`/`max_format` 形状)。不符会被
     `prepare_all.py` **硬拒**并教你用 `build_resourcepack.py --from-zip <你的zip> --mc-version <ver>`
     换版本重打包(只改 `pack.mcmeta`,不用重编码,一个 zip 派生任意 1.21.x)。
  2. **要覆盖全部 103 个 `qzpno:` 音效事件**(与 `assets/redpiano_map_multi.json` 对齐)。缺哪些,
     `prepare_all.py` 会 **`[warn]` 列出**(缺的那些音符盒在游戏里静音,不退回原版),但不阻断安装。

**④ 世界升级到新 MC 版本后要重建吗?——只需重跑资源包,机器本体不用重建。** 旧 `qzpno_mv.zip`
在新版本会因 `pack_format` 不符被 MC 自动禁用(→静音)。修法:`build_resourcepack.py --from-zip
<旧 qzpno_mv.zip> --mc-version <新版本>` 派生一个新版包,重新装/选用即可;datapack 机器结构本身在
1.21.x 内不用重建(命令/格式由 `--mc-version` 自适应,重建机器只在需要换 MIDI/形态时才做)。

## Scope

**Family A only** — RedPiano mod, real note blocks (re-performed notes). The Family B
**audio sample-slice** pipeline (`method=slice` — chopping the *original recording* into
per-tick ogg slices for MP3-faithful timbre) lives in an external repo (`mc-noteblock-demo`)
and is **out of scope**; the generators hard-fail on `method=slice`. This is a *technique*
boundary, not a version one — don't confuse it with the craftsman path's honest vanilla-timbre
downgrade (§ delivery rule 5), which is a legitimate in-scope Family A fallback on old versions.

## Next step

- **Fast path (1.21.x):** [QUICKSTART.md](QUICKSTART.md) for the end-to-end build-and-play
  checklist + "no sound?" triage; [docs/CONTRACT.md](docs/CONTRACT.md) for the build-script
  interface spec; [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md) for capabilities.
- **Craftsman path (any other version):** [docs/VERSION_TACTICS.md](docs/VERSION_TACTICS.md) —
  the per-generation domain-knowledge + tactics + verify map.
