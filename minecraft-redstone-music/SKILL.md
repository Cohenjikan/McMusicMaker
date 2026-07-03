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

## 用户端流程 (onboarding — 任何 agent / 平台按此驱动用户)

To fulfill a "make Minecraft redstone music from this MIDI" request, collect the inputs
below, then run the build command in step 4. (No special "skill" loader is needed — this
is a self-contained folder + one Python CLI; see README.md.)

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
> **Sound needs version-matched binaries — now self-service via `fetch_binaries.py`.** The datapack
> auto-adapts the *commands/format*, but the SOUND needs a **mod jar + `qzpno_mv.zip` that match the
> MC version**; a mismatch makes the note blocks fall back to **vanilla** tones (faint harp + booming
> basedrum). Instead of hand-picking the jar every round, run
> **`python scripts/fetch_binaries.py --mc-version <ver>`**: it reads the shipped
> `binaries/binaries_manifest.json`, resolves the version's jar + the shared `qzpno_mv.zip` from the
> local `binaries/` folder (sha256-verified; **local hit = instant**, no network needed for a repo
> snapshot), and prints a VERDICT (whether that jar was actually listened in-game vs only bytecode-
> checked). The **mod jar is per-version**: `fabric.mod.json` pins a `"minecraft"` range and Fabric
> **refuses to load a jar whose range doesn't cover the running game** — `fetch_binaries` selects the
> right one for you (`redpiano-1.0.0-mc<ver>.jar`). The **`qzpno_mv.zip` is shared** at `rp_format 64`
> across 1.21.7/1.21.8; for a version whose `rp_format` differs (e.g. 1.21.9 = 69) derive a matching
> pack from that one zip with **`build_resourcepack.py --from-zip <qzpno_mv.zip> --mc-version <ver>`**
> (rewrites only `pack.mcmeta`; no sample folder needed). Then feed `fetch_binaries`'s outputs to
> `prepare_all.py` via `--prebuilt-rp` / `--prebuilt-mod-jar` (+ `--fabric-api-jar`). If the target
> version has **no jar in the manifest**, `fetch_binaries` says so and points you to recompile
> (`mod_build.py --write` + Gradle) — a stripped sandbox usually can't build the jar, so prefer a
> version the manifest already carries. See [BINARIES.md](BINARIES.md).
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
> version-matched jar ships in `../binaries/` for every version in the manifest (currently 1.21.7 /
> 1.21.8; more as they are added). Inside the sandbox you **do not need and must not** run Gradle —
> run `fetch_binaries --mc-version <ver>` and pass its jar as `--prebuilt-mod-jar`. Only when the
> manifest has **no jar** for the target should you recompile, and even then a stripped sandbox
> usually can't — building the mod in one is exactly what tempts the fatal fabric-api-stub shortcut
> above.
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
   - **Resourcepack source**: either `--samples-root` (full source repo: the repo-root `poc/`
     folder, which contains `samples_manifest_*.json` + `samples_*/*.ogg`) or a prebuilt
     `qzpno_mv.zip` that matches the target MC resourcepack format. Two paths, one folder: the
     **auto-detect** default is `../../poc` (anchored to `scripts/`, so `scripts/../../poc` =
     repo-root `poc/`); if you pass `--samples-root` **by hand it's relative to your shell's
     cwd** — from the repo root that same folder is just `./poc` (written `../poc` only in
     examples that run one dir deeper). When unsure, pass an absolute path.
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

2. **选播放形态 — pick a form.** Default = **`inplace` 原地调色板**: the in-game-verified,
   rock-solid, tiny-footprint form the user confirmed as "特别好" — reach for it unless there's a
   reason not to. Escape hatch: if the user wants the "playhead travels the line" animation, offer
   **`swave` S 型曲折直线** (generation-verified, full in-game listen still pending); custom
   routing/particles go through the HTMLs in step 5. Confirm the form when it's ambiguous, but you
   don't need a mandatory extra round-trip when the user already told you what they want (or said
   "just use the default"). The `midi_report.py` verdict (step 1) can steer this — a long/dense
   MIDI on `swave` reports a large footprint, nudging toward `inplace`.

3. **备好 mod + 音效包** for the chosen version (any of 1.21..1.21.10) — **start with
   `fetch_binaries.py`**:
   - The RedPiano mod jar + `qzpno_mv` resourcepack are runtime assets, not optional extras.
     `prepare_all.py` **stages** them into the workspace `dist/` (the native `.bat` then
     installs them — see step 4). It does not copy into `<profile>` from a sandbox.
   - **one command resolves both** — `python scripts/fetch_binaries.py --mc-version <ver>`
     reads `binaries/binaries_manifest.json` and resolves the version's jar + shared
     `qzpno_mv.zip` from the local `binaries/` folder (sha256-verified; local hit is instant).
     Its VERDICT tells you whether that jar was **listened in-game** or only **check-jar clean**
     (so you know to listen once). If the manifest has **no jar for the version**, it says so and
     points you to build one.
   - **resourcepack** — pass `fetch_binaries`'s `qzpno_mv.zip` as `--prebuilt-rp`. If the target
     version's `rp_format` differs from the shipped zip's 64 (e.g. 1.21.9 = 69), first derive a
     matching pack from it: `build_resourcepack.py --from-zip <qzpno_mv.zip> --mc-version <ver>
     --out <derived.zip>` — this rewrites only `pack.mcmeta` (rp_format + single/minmax shape from
     the version table) and needs **no sample folder**. `prepare_all.py` also validates the
     rp_format matches, so a mismatch is caught either way. (Building from scratch instead —
     `--samples-root <dir>` — is still supported and is pure stdlib: it only **copies already-
     encoded `.ogg`** into the zip, no ffmpeg. Its prerequisite is a samples folder with
     `samples_manifest_*.json` + `samples_*/*.ogg`.)
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
   `--prebuilt-rp` + `--prebuilt-mod-jar` (ship beside the skill) so no Gradle/JDK/ffmpeg is
   needed. In a full source checkout, `--samples-root` auto-detects `../../poc`. Do not add
   `--skip-*` flags unless the user explicitly asks for a partial artifact.
   If `prepare_all.py` exits nonzero, fix the missing dependency or report blocked — do not
   summarize it as complete.

   **▸ 版本参数化黄金路径 (version-parameterized golden path).** For ANY supported version, the
   four steps are the same — only `<ver>` changes:
   1. **Ask the user their MC version** (`<ver>`, e.g. 1.21.7 / 1.21.8 / 1.21.9).
   2. **`python scripts/fetch_binaries.py --mc-version <ver>`** — resolves the jar + `qzpno_mv.zip`
      from the local `binaries/` folder (local hit = instant; note its VERDICT re: listened vs
      check-jar-only). No manifest jar for `<ver>`? it tells you to build one (or pick a version
      that has one).
   3. **If `<ver>`'s rp_format ≠ 64** (the shipped zip), derive a matching pack:
      `python scripts/build_resourcepack.py --from-zip ../binaries/qzpno_mv.zip --mc-version <ver>
      --out dist/qzpno_mv.zip`. For 1.21.7/1.21.8 (both rp 64) skip this and use the zip as-is.
   4. **`prepare_all.py`** as below, with `--prebuilt-rp` / `--prebuilt-mod-jar` pointing at the
      fetch/derive outputs. Fabric API stays on the Modrinth auto-download (public); pass
      `--fabric-api-jar` only offline. Optionally gate the jar first with
      `mod_build.py --mc-version <ver> --check-jar <jar>`.

   **▸ 打包分发场景 — concrete example (Fabric 1.21.7, offline, prebuilt binaries).** The golden
   path above, instantiated for the common handoff: a repo-snapshot with a sibling `binaries/`
   folder and a user on **Fabric 1.21.7**. Run it **from the `minecraft-redstone-music/`
   directory**, so `../binaries/…` resolves. Every path here is real — `--world-dir` and
   `--profile-dir` **must be the user's actual game paths (ask them first)**; the two shown are
   only placeholders. All binaries are passed explicitly, so **no Modrinth / network is needed**:

   ```bash
   python scripts/prepare_all.py \
       --midi <mid> \
       --form swave \
       --ns  mysong \
       --origin 0 0 255 \
       --mc-version 1.21.7 \
       --world-dir  "<profile>/saves/<world>/datapacks" \
       --profile-dir "<profile>" \
       --prebuilt-rp      ../binaries/qzpno_mv.zip \
       --prebuilt-mod-jar ../binaries/redpiano-1.0.0-mc1.21.7.jar \
       --fabric-api-jar   ../binaries/fabric-api-0.129.0+1.21.7.jar \
       --dist dist
   ```

   Notes: the **mod jar is the `mc1.21.7` one** (the `mc1.21.8` jar declares `~1.21.8` and Fabric
   would reject it on a 1.21.7 game); `qzpno_mv.zip` is the same for 1.21.7/1.21.8. If the shipped
   jar is still named `…-mc1.21.7-UNVERIFIED.jar`, use that filename verbatim (the `-UNVERIFIED`
   just means "listen once to confirm"); optionally gate it first with
   `python scripts/mod_build.py --mc-version 1.21.7 --check-jar ../binaries/redpiano-1.0.0-mc1.21.7.jar`
   (exit 0 = bytecode-clean, safe to install). For a **1.21.8** game, swap `--mc-version 1.21.8` and
   the mod jar to `../binaries/redpiano-1.0.0-mc1.21.8.jar` (+ a 1.21.8 fabric-api jar). Every flag
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
     4. **确认资源包** — the `.bat` already enabled `qzpno_mv` in `options.txt`; the user just
        confirms it's on the right (selected) side in Options → Resource Packs.
     5. `/function <ns>:setup` — build the physical machine + console at the origin.
     6. press the **[play]** sign/button.
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

5. **自定义需求 → 两个 HTML**(用法都是:浏览器里手动填 → 直接复制或导出 JSON 交给 agent):
   - `designer/layout_designer.html` — **自定义走线方式**(形态 / 尺寸 / 折叠 / 起点)。
     导出 layout params JSON → 传给 `build_machine.py --params`.
   - `designer/particle_editor.html` — **自定义关键帧 + 命令方块位置**(粒子 / 烟花 / 任意命令,
     同步音乐时间与世界坐标)。导出 particle_keyframes JSON → `build_particles.py`(见 docs/PARTICLES.md).

## Forms & pipeline (details live in references)

Five forms share one MIDI→resolve→layout→melody-cut→emit pipeline. Pick by footprint/effect;
the full capability table, per-form verified status, and the 6-stage pipeline are in the
authoritative reference — **don't re-derive them here**:

- **`inplace`** — in-place palette, tiny footprint, **user-verified "特别好"**. The default.
- **`swave`** — marching-pulse S-wave with the "playhead travels the line" effect;
  generation-verified, ear-confirm pending. Offer when the user wants the animation.
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
   (verified default **1.21.8**; supported auto band **`1.21`..`1.21.10`**). The script
   auto-detects JDK 21/Gradle for RedPiano builds and downloads/reuses Fabric API when
   possible; missing toolchain/network means **not ready**, not success.
2. **RedPiano mod jar** in `<profile>/mods/` (then restart Minecraft — a jar swap needs a
   full restart, not `/reload`). The easy path is `fetch_binaries.py --mc-version <ver>` →
   pass its jar as `--prebuilt-mod-jar`. `prepare_all.py` can also build one via Gradle when
   the manifest lacks the version and a JDK 21 is present.
3. **`qzpno_mv` resourcepack** placed in `resourcepacks/` and **manually enabled by the
   user** in **Options → Resource Packs** (moved to the right/selected side). `prepare_all.py`
   copies the zip and tries to select it in `options.txt`, but the user MUST still confirm
   the pack is on the selected side in-game — forgetting this is **the #1 cause of total
   silence**. If its `pack_format` does not match the MC version, MC **silently disables it →
   total silence.** The `pack_format` is version-specific (e.g. **64** for 1.21.8); the shipped
   zip is rp 64, and for any other version `scripts/build_resourcepack.py --from-zip` derives a
   matching pack from it (rp_format + shape from the version table, no samples needed).
   This zip is **not inside this folder** — resolve it with `fetch_binaries.py`; see
   [BINARIES.md](BINARIES.md).
4. **tick80** is required for playback timing. **The user must manually type `/tick rate 80`
   in-game** before pressing `[play]` — the machine does **NOT** self-set it (auto-set via a
   command block was tested and does not work). Without it, playback runs **~4× too slow** and
   melody-cut timing is off. Make this a required in-game step, not just a diagnostic.

> **Large binary assets bundled separately.** The prebuilt **RedPiano mod jar** and
> **`qzpno_mv.zip`** resourcepack are large binaries and are **not** in this folder.
> Bundle/distribute them alongside it — full obtain/build instructions are in
> **[BINARIES.md](BINARIES.md)**. The text assets that *are* bundled here are
> `assets/redpiano_map_multi.json` (103-block instrument map) and `assets/demo.mid`.

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
