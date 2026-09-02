# Faster DS3 HUD iteration: findings (2026-09-02)

Ranked by expected time saved per iteration. Current loop: ~2.5 min (build, copy, full boot ~40s, menu, save load, walk, shot, quit).

Bottom line up front:

- **No tool hot-reloads Scaleform/menu assets in DS3.** Not ModEngine2 (any mode), not me3, not the debug menu, not Smithbox/DSMapStudio. That answer is solid, stop hunting.
- The two real levers are: **(1) keep one session alive and cycle quit-to-title -> Continue** (needs a 10-minute experiment you can instrument from the Linux side with inotify), and **(2) preview .gfx layout outside the game in JPEXS**, which verifiably renders external DDS/TGA images if you drop them next to the .gfx.
- Guaranteed but smaller: **BootBoost** (10-15s off every boot) and **NoLogo** (kills intro logos, including the ones after save-and-quit).

---

## 1. Keep the game alive: quit-to-title, swap files, Continue (likely biggest win, needs one experiment)

**What it is.** Your harness tears the session down every run, but `run_inventory` already ends on "save and quit to title", and the `_dev` rail (`ds3-shot _dev start/menu/key/click/shot/stop`) is everything needed to drive a persistent session. If DS3 re-opens `menu/01_000_fe.gfx` / `menu/01_common.tpf.dcx` when a save is loaded (rather than only at process start), then the loop becomes: quitout (~10s) -> swap file in `mod/` -> Continue (~10-15s) -> shot. **~35-45s per iteration instead of ~150s.**

**Why it is plausible.** ModEngine2 hooks the game's archive lookups per file open (Detours IAT rewriting, see [ARCHITECTURE.md](https://github.com/soulsmods/ModEngine2/blob/main/ARCHITECTURE.md)), so ANY re-open by the game is served the current bytes of the override file. The whole question is whether the engine re-opens the menu resources on save load or keeps them resident from boot. Community evidence is silent either way for the FE movie. One caution from your own harness notes: the improper-shutdown dialog (drawn on the main menu, before any save load) already uses recoloured 01_common textures, so at least part of 01_common is loaded pre-menu; that says nothing about whether it is re-read later.

**The experiment (one run, definitive, no game knowledge needed).** From the Linux side, inotify tells you exactly when the game opens the override files:

```
inotifywait -m -e open,access \
  ~/couch/data/ds3-shot/game/mod/menu/01_000_fe.gfx \
  ~/couch/data/ds3-shot/game/mod/menu/01_common.tpf.dcx
```

Run a `_dev` session with `DS3SHOT_MOD=1`, note the opens during boot, then drive quit-to-title and Continue and watch whether opens fire again. If they do, second half of the experiment: swap in a garishly-edited file while at the title screen, Continue, screenshot, confirm the change landed. Alternative instrumentation: ModEngine2 writes `modengine.log` next to the launcher and logs hooked file requests, but inotify is simpler and does not depend on ME2 log verbosity.

**Outcomes.**
- Files re-read on save load: build the persistent loop as a thin driver over `_dev` (quitout clicks are already coded in `run_inventory`). Expect ~4x.
- Files re-read only at title screen creation or not at all: fall back to option 3 (boot-time cuts). Known community fact for context: the debug menu can reload CHARACTERS (chr files re-read from disk mid-session, "Reload Chr" / "Reload all characters" in the [DS3 debug menu transcription](https://docs.google.com/document/d/1dYDRQLBI0lQzM41nqTje14YHCVn0wEBxzb2xSJiUc3c/edit)), which proves the engine has live re-open paths through the VFS; menu resources were just never given one.

**Linux/Proton:** all host-side, no new tools. **Confidence:** high that the experiment answers the question; genuinely 50/50 on which way it lands. Even a "no" is worth the 10 minutes.

---

## 2. Special K live texture injection (texture-only, could make texture tweaks near-instant, medium risk)

**What it is.** [Special K](https://github.com/SpecialKO/SpecialK) has a D3D11 texture mod pipeline: dump game textures by hash, drop replacement DDS files in `SK_Res/inject/textures/<hash>.dds`, and it swaps them at texture-creation time. Crucially it has a **live reload** path: `ReloadAllTextures` / "Reload This Texture" exist in the D3D11 texture manager and mod-tools UI (`src/render/d3d11/tex_mgr/d3d11_tex_mgr.cpp`, `src/render/d3d11/mod_tools/d3d11_texture_mods.cpp` in the repo). If it works under your stack, a texture change becomes: overwrite DDS, hit reload in the SK OSD (drivable via XTEST like everything else), screenshot. **Seconds per texture iteration, no relaunch.** Does nothing for .gfx layout changes.

**Linux/Proton:** unofficial but real. Working recipes exist, e.g. the [NieR Automata Linux setup guide for Special K + DXVK](https://www.nexusmods.com/nierautomata/mods/739): local install of SK's dlls in the game dir plus `WINEDLLOVERRIDES="dxgi=n,b" ...` style overrides so SK loads above DXVK. Your sandbox game dir is a symlink farm you own, so dropping SK files there touches nothing real. Docs: [SK dumping and injecting textures guide](https://steamcommunity.com/sharedfiles/filedetails/?id=1491783680), [special-k.info](https://www.special-k.info/).

**Gotchas.** SK + ME2 both hooking the process is the main instability risk (ME2 uses Detours, SK hooks D3D11/DXGI, they usually coexist but test). HUD textures are created once at load, so without the reload button you gain nothing; the reload button is the whole point. Whether SK's texture cache sees Scaleform-created textures in DS3 specifically is unverified. Turn off SK's HDR/present meddling before trusting colour-accurate captures.

**Confidence:** medium that it can be made to work, low-medium that it is stable enough to trust. Budget an afternoon.

---

## 3. Cut the boot itself: BootBoost + NoLogo + (optionally) me3 (guaranteed, stacks with everything)

- **[BootBoost](https://www.nexusmods.com/darksouls3/mods/303)** ([source, TKGP/JKAnderson](https://github.com/JKAnderson/BootBoost)): DS3 spends 10-15s of every boot RSA-decrypting the `.bhd` archive headers. BootBoost decrypts them once and writes them back, after which the game loads them directly. **Saves 10-15s per boot, forever.** Run `BootBoost.exe` once under the sandbox Proton prefix in the sandbox game dir; it will need the `.bhd` symlinks replaced by real copies first (the real install stays untouched, which fits your rails). ME2 is unaffected, archives still work normally.
- **[NoLogo](https://github.com/bladecoding/DarkSouls3RemoveIntroScreens)** (blcd/bladecoding, [speedrun-legal](https://www.speedrun.com/darksouls3/resources)): dinput8.dll that removes the intro logo screens, both at boot and after save-and-quit. Your harness polls rather than sleeps, so the saving is real (the logos are several seconds each way). Load it via ME2's `external_dlls` in `config_darksouls3.toml` rather than as a dinput8 proxy, since ME2 is your injector. Alternative: [Fast Launch (Skip Intro)](https://www.nexusmods.com/darksouls3/mods/1817) on Nexus.
- **[me3](https://github.com/garyttierney/me3)** (ModEngine2's successor): v0.8.0 added DS3 support, it runs natively on Linux (launches .me3 profiles on Linux desktops, finds Windows binaries automatically), and since v0.7.0 it has **BootBoost built in** ([NEWS](https://github.com/garyttierney/me3/blob/main/NEWS.md), [v0.7.0](https://github.com/garyttierney/me3/releases/tag/v0.7.0), [v0.8.0](https://github.com/garyttierney/me3/releases/tag/v0.8.0)). No hot reload here either, but if you ever rework the harness, me3 is the cleaner Linux citizen. Not worth a migration just for this.

**Total: roughly 15-25s off every launch, zero risk, an hour of setup.** If option 1's experiment says quitout is enough, this still speeds the first boot of each batch session.

---

## 4. Preview .gfx layout outside the game (kills a large fraction of launches for layout work)

**JPEXS FFDec's internal preview renders GFx external images if the files are next to the .gfx.** Verified behaviour from the FFDec tracker: `DefineExternalImage2` / `DefineSubImage` referenced files (e.g. `foo_i1.dds`) are loaded from the same directory as the opened .gfx and shown in the preview; missing ones render red ([issue #2171](https://www.free-decompiler.com/flash/issues/2171-images-appearing-as-solid-red-in-ffdec-and-upon-export), [FFDec 18.3 news: TGA support in GFX previews](https://blog.free-decompiler.com/2023/02/25/news-in-ffdec-18-3-x/)). So: extract the TPF's DDS files with your existing toolchain, name them as the gfx's external-image tags expect, drop them beside `01_000_fe.gfx`, and FFDec shows the HUD frames with real art. FFDec is Java, runs natively on Linux, and has a CLI (`-export frame/image`) so you could script "render frame N to PNG" and diff against your simulator without a GUI. It will not run ActionScript-driven runtime layout (gauge fill logic etc.), it is a static/frame preview, but for transform, placement, and art iteration it is a zero-launch loop.

**Ruffle** now accepts GFx header signatures ([PR #9090](https://github.com/ruffle-rs/ruffle/pull/9090), merged) but implements **no Scaleform-specific tags**, so `DefineExternalImage2`/`DefineSubImage` content is simply absent. To use ruffle (which WOULD run the AS timeline) you would need a build step rewriting external-image tags into embedded `DefineBitsLossless2` equivalents. Doable with your toolchain or a JPEXS script, but it is engineering, and Scaleform AS2 extensions may still misbehave. Secondary option.

**Scaleform GFxMediaPlayer** (the real SDK player, the only renderer that natively understands external DDS and Scaleform extensions): Autodesk discontinued GFx in 2017, but the SDKs are archived at [archive.org/details/scaleform-gfx-sdks](https://archive.org/details/scaleform-gfx-sdks) and mirrored on GitHub ([Raitou/GFx-SDK](https://github.com/Raitou/GFx-SDK), [Final-Game-Production-Inc/Autodesk-Scaleform-GFx-SDK](https://github.com/Final-Game-Production-Inc/Autodesk-Scaleform-GFx-SDK)); `GFxMediaPlayer.exe` lives in `Bin/` of SDK 4.x and is a plain D3D9 app that should run under Wine. Most faithful offline render, but untested under Wine and DS3's AS may reference game-injected objects and error. **Confidence: medium-low, try only if FFDec preview proves insufficient.**

---

## 5. Save states: no. (Q3 answered plainly)

- **No memory savestate tool exists for DS3.** Nothing in the [Grand Archives cheat table](https://github.com/The-Grand-Archives/Dark-Souls-III-CT-TGA), the practice tool, or anywhere else snapshots full game state. Process-level checkpointing (CRIU) cannot capture GPU/Vulkan state, so that road is closed too.
- Closest things, all of which still require the save-load you already pay:
  - [johndisandonato's DS3 Practice Tool](https://github.com/veeenu/darksoulsiii-practice-tool): position save/load, official Linux/Proton support ("fully supports Linux, should run on Steam Deck seamlessly", install as dinput8.dll with `WINEDLLOVERRIDES="dinput8=n,b"`). Useful only if you later need the character standing somewhere specific for a HUD state.
  - [SoulsSpeedruns Save Organizer](https://github.com/Kahmul/SoulsSpeedruns-Save-Organizer): savefile swapping, not state.
  - The TGA cheat table runs on Linux via [protonhax](https://github.com/jcnils/protonhax) (documented in its README) if you ever want CE against the sandbox.

---

## 6. Dead ends and loose ends (so you stop hunting)

- **ModEngine2 hot reload: does not exist.** The `debug` config flag and the [Debug Menu Extension](https://deepwiki.com/soulsmods/ModEngine2/6.2-debug-menu-extension) only unlock the retail-stripped dev menus (model viewer, stage select, sound test, free cam). I read the full community transcription of the DS3 debug menu: the MENUMAN / Front End sections toggle FE visibility, animation speeds and state flags, and there is "Reload Chr" for characters, but **nothing re-reads menu gfx or tpf from disk**.
- **me3: no hot reload either** (checked NEWS/CHANGELOG through current).
- **Smithbox/DSMapStudio: no live link to a running DS3 for UI assets.** Their param reloader hot-patches params in memory, which is the precedent for "live" workflows, but it writes param bytes, it does not touch the resource repository.
- **iGP11** ([Nexus](https://www.nexusmods.com/darksouls3/mods/28)): the old DS3 texture injector. Reported broken after later game patches, D3D11 proxying under DXVK is dubious, and Special K supersedes it. Skip.
- **Death / fast travel does not reflush menu textures.** Streaming re-reads are for map/chr assets; FE resources are resident.
- **Two parallel sandbox instances** (pipeline two iterations at once): unverified whether steam_api tolerates a second session of appid 374320 against the one running Steam client. Cheap to test with a copy of the sandbox, but it only halves latency if you have two independent changes in flight, which your batching already approximates. Low priority.
- **soulsmodding wiki UI guides** (for reference, both are JPEXS-workflow docs, neither mentions any reload trick): [Replacing and Appending UI Elements](https://docs.google.com/document/d/1XCO2ecZDU3uwAHISE2EHz3EKvfc1joK99WQXZTkbDHM/edit), [Adjusting UI Elements](https://docs.google.com/document/d/19TTmIGe2tsfRxW_4UObFD59sYW1rnggWtk-tfzdPk9o/preview).

---

## Suggested order of attack

1. Run the inotify quitout experiment (10 min). If yes: build the persistent-session driver on the `_dev` rail, iteration drops to ~35-45s. This is the only candidate that speeds up BOTH gfx and tpf changes in-game.
2. Install BootBoost + NoLogo in the sandbox (1 hour, guaranteed 15-25s per boot regardless of 1).
3. Set up the FFDec side-by-side preview (extracted DDS next to the gfx) and fold it into the pre-flight: most layout mistakes die before ever costing a launch.
4. If texture tweaking remains the grind after 1-3, spend the afternoon on Special K live injection.
