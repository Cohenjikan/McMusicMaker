# RUNTIME_SANDBOX.md — why "built" ≠ "in the game", and how to actually install

> **TL;DR for the agent:** You probably run inside a sandbox (Trae SOLO / similar).
> In it, writing to `C:\Minecraft\...` is silently redirected to a private mirror the
> real game never reads — so your "deploy" looks successful but nothing plays.
> **Do not deploy into the profile yourself.** Run `prepare_all.py`, which builds
> everything into the workspace `dist/` and emits `DEPLOY_TO_GAME.bat`. Tell the
> **user** to double-click that `.bat` in Windows Explorer. Treat the song as
> in-game **only** after `dist/DEPLOY_RECEIPT.txt` exists — never before.

## The failure this fixes

Symptom: an agent builds the datapack + resourcepack + mod, copies them into the
Minecraft profile, verifies the files are there, reports "done — you can hear it now",
and **the game is completely unchanged**. `/function <ns>:setup` says *Unknown function*.

Root cause: **the coding agent runs in a filesystem sandbox.** Tools like Trae SOLO run
the agent in a VM whose disk is a copy-on-write overlay. Only the **open project folder**
is bind-mounted to the real disk; **everything else is virtualized.** A write to
`C:\Minecraft\ModrinthApp\profiles\Fabric 1.21.7\...` is transparently redirected to:

```
%APPDATA%\Roaming\TRAE SOLO CN\VMCache\main-TRAE_SOLO-Yinli\drive\C\Minecraft\...
```

The agent then reads that mirror back, sees its own files, and believes it succeeded.
But Minecraft runs **natively** and reads the **real** `C:\Minecraft`, which never changed.

## Why you cannot fix this from inside the sandbox

The redirection happens **below** the Python/PowerShell process — at the VM's filesystem
layer. So:

- **Path heuristics don't help.** The path you pass (`C:\Minecraft\...`) is exactly right;
  it's the write that gets moved.
- **Read-back verification doesn't help.** Reading `C:\Minecraft\...` also hits the mirror,
  so everything looks consistent.
- **"Detect the sandbox and refuse" doesn't help.** A good sandbox is transparent from
  inside — detection false-negatives, so the agent sails through and deploys to the mirror
  anyway. (This is exactly what earlier versions of this skill did, and it never worked.)
- **You have no native shell.** "Just run it from a real terminal" is not an action the
  in-sandbox agent can take.

The **one** path that reliably reaches the real disk is the **project workspace itself**
(that's why your build artifacts show up on the real Desktop). Everything else is a mirror.

## The fix: build in the workspace, install via a native double-click

1. **Build** — `prepare_all.py` writes the datapack, `qzpno_mv.zip`, and the mod/Fabric API
   jars into the workspace `dist/`. This is 100% reliable in the sandbox.
2. **Emit a native installer** — it generates `dist/DEPLOY_TO_GAME.bat` (→ a unicode-safe
   `deploy_to_game.ps1`) with the real profile/world paths and a unique **token** baked in.
3. **User runs it natively** — the user **double-clicks `DEPLOY_TO_GAME.bat` in Windows
   Explorer.** That launches as a normal Windows process **outside** the sandbox, so its
   writes reach the **real** profile: it copies the datapack into the world, the resourcepack
   into `resourcepacks/`, the jars into `mods/`, and enables `qzpno_mv` in `options.txt`.
4. **Receipt = proof** — on success the `.bat` writes `dist/DEPLOY_RECEIPT.txt` (with the
   token) back into the workspace. Because that file can only be produced by a native run of
   the `.bat`, it is the **sole trustworthy signal** that the song is really in the game.
   Your own writes into `C:\Minecraft` can never forge it.

## Rules for the agent

- **Never** copy artifacts into `C:\Minecraft\...` yourself and call it done.
- **Never** run `DEPLOY_TO_GAME.bat` yourself (subprocess/`Start-Process`). If you run it,
  it inherits the sandbox and installs into the mirror. It must be launched by the **user**.
- After building, tell the user, in plain terms: *"双击 `dist\DEPLOY_TO_GAME.bat` 就能装进游戏"*
  (double-click this one file). Point at the exact path.
- **Report status honestly by the receipt:**
  - `python scripts/deploy_bundle.py --verify <dist>` → `✓ INSTALLED` (exit 0) or
    `✗ NOT INSTALLED` (exit 1). Only claim it's in-game when this is `✓`.
  - No receipt → say **"built, not in game yet — the user must double-click DEPLOY_TO_GAME.bat"**.
- On a **genuinely native host** (you are NOT in a sandbox — e.g. a real terminal), you may
  pass `--install-now` to `prepare_all.py` to copy into the profile inline and skip the `.bat`.
  Do **not** use `--install-now` from inside a sandbox.

## For the human

You only do one thing: **double-click `dist\DEPLOY_TO_GAME.bat`** (see `dist\README_部署说明.txt`).
A black window shows it copying into your game and prints `✓ 已真正部署到游戏`. If it instead
prints `✗ 检测到你是在 Trae 沙箱里运行`, that means an AI ran it for you — run it yourself from
Explorer. Then in-game: restart Minecraft (if the mod changed) → `/reload` → `/tick rate 80`
(type it yourself) → confirm `qzpno_mv` is enabled → `/function <ns>:setup` → press **[play]**.
