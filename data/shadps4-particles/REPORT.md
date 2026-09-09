# Ebrietas particle blow-up: root cause and fix

Investigated 5-6 Sep 2026, read-only (the game was running the whole time, so
nothing was built, launched or installed). Symptom: at Ebrietas, Daughter of the
Cosmos (Altar of Despair), the summon's aura, the water and the ground-slam
rocks spawn endlessly and cost frames. Happens at vblank 60 and 90.

## (a) Root cause: game-side, not emulator-side

**This is the documented Bloodborne 60 FPS-patch bug. Ebrietas' ground-break
attack SFX never retires above 30 fps, so its emitter runs forever.**

Evidence:

- shadps4-emu/ps4_cheats issue #72, "Bloodborne: Several issues with the 60 FPS
  patch", item 3: *"during this boss fight with the 60 FPS patch on, a lot of
  projectile/particles coming from one of Ebrietas' attack become infinite"*,
  causing performance degradation or crashes, and *"this simply doesn't happen
  without the patch"*. Last comment (par274, 3 Nov 2025), after Ludwig and the
  cutscene bugs were fixed: *"The Ebrietas issue still persists, though - that
  one still needs to be played at 30 FPS for now."*
- Nexus Bloodborne mod 41 ships a MAIN file dated 9 Dec 2024 called
  **"Stand Alone Ebrietas Sfx Fix"** whose description is
  *"changing to a proper Effect the ebrietas infinite ground breaking bugged
  attack, its for both INTEL and AMD"*. The same mod has earlier
  "Fixed Ebrietas Ground bugged" builds. The bug is well known to the BB modding
  scene and is fixed by replacing the FXR, not by emulator changes.
- The fix archive contains exactly **one** file:
  `dvdroot_ps4/sfx/frpg_sfxbnd_m24_02.ffxbnd.dcx` (716,848 bytes). m24_02 is the
  Upper Cathedral Ward block that holds the Altar of Despair. Our installed copy
  is the untouched vanilla extract (653,709 bytes, mtime 2 Aug 03:59,
  md5 `1c8e6270dc80bf75e05ef44e58146b88`); the fix is
  md5 `51b49f93e8ce850b2e278c32e8af2bfb`. Staged, not installed, at
  `~/couch/data/shadps4-particles/staging/fix/`.
- Our frame-rate mechanism is exactly the one the issue blames. Per
  `~/couch/tools/bb-fps`, the eboot in use is Lance McDonald's 60 fps MOD build
  with a *dynamic* frame delta, and rate is set purely by
  `config.json GPU.vblank_frequency` (currently 60). Every "FPS++" XML patch is
  `isEnabled="false"` in `Bloodborne.xml` and has been all evening (verified
  against tonight's `.pre-fps-*` / `.pre-cheat-*` backups). So "60 fps" here
  means the 60 fps eboot, which is what issue #72 is about, and raising vblank
  to 90 makes it worse for the same reason: it is a frame-rate-scaled emitter,
  not a frame-time problem. That matches "happens at both 60 and 90".
- The "SFXR60fpsCutsceneFixForDLCandVariousBOSSES" mod we have installed does
  **not** cover this. Its whole payload is
  `sfx/frpg_sfxbnd_m21.ffxbnd.dcx`, `sfx/frpg_sfxbnd_m25.ffxbnd.dcx` and ten
  `remo/*.remobnd.dcx` cutscene binders. No m24, and it only touches cutscenes.

## The emulator hypotheses, and why they are not it

1. **GDS append/consume (upstream d6857fb).** Real, and we do have the old code:
   `resource_tracking_pass.cpp:687-708` bakes the GDS address at shader-compile
   time from `info.user_data[ud_reg] >> 16` and emits `ir.Imm32(gds_addr >> 2)`.
   `StageSpecialization` (`src/shader_recompiler/specialization.h`) does **not**
   include user-data values in the shader key, so two dispatches of the same
   shader with different M0 collapse onto one pipeline carrying one stale
   counter address. That is a genuine latent correctness bug and d6857fb is the
   right fix. But it is not this symptom: the same blow-up is reported on stock
   upstream builds by users who have none of our patches, and it disappears at
   30 fps, which no GPU-side counter bug would do. **Not verified either way:**
   whether Bloodborne's SFX shaders use `ds_append`/`ds_consume` at all. Proving
   it needs `dump_shaders=true` and a grep for `DataAppend`, which needs the
   emulator, so it was not done.
2. **Our GpuComm / texture-cache levers.** Ruled out. `readbacks_mode=0`,
   `direct_memory_access_enabled=false`, `copy_gpu_buffers=false`,
   `patch_shaders=false`: all conservative. The five opt-in flag files
   (`shadps4-lazy-pending-ops`, `-lock-keep`, `-fetch-memo`,
   `-precompile-tilers`, `-epoll-sleep`) are stutter levers on submission and
   fault paths; none touch particle simulation, and the bug predates them by two
   years. Tonight's session log has zero GPU errors: no GDS lines, no shader
   asserts, no "Unable to track M0 source".
3. **Upstream issue search.** Done. `repo:shadps4-emu/shadPS4 bloodborne
   particles` returns nothing current (only #1873, missing particles, closed);
   the live tracking is in `ps4_cheats` #72 above.

## (b) Upstream commits, and whether they cherry-pick

Tested in a throwaway worktree off HEAD `fabc12a` under the session scratchpad
(worktree removed afterwards; the main tree was never touched):

| commit | what | onto HEAD |
|---|---|---|
| `d6857fb` | compute GDS offset dynamically instead of a compile-time constant (#4875) | **clean** |
| `3e45847` | emulate scaled min/max blending (#4768) | **clean** |
| `fc74821` | decorate written storage buffers as Coherent (#4896) | conflict (`spirv_emit_context.cpp/.h`) |
| `e29cf71` | shared-memory barriers + divergent loop detection (#4941) | conflict (`vk_pipeline_serialization.cpp`) |

## (c) Plan

**The fix (do this):** drop the standalone Ebrietas SFX file in. One file, no
build, no emulator change.

```
# with the game CLOSED
cp ~/games/ps4/CUSA00900/dvdroot_ps4/sfx/frpg_sfxbnd_m24_02.ffxbnd.dcx \
   ~/couch/data/shadps4-particles/staging/vanilla-m24_02.ffxbnd.dcx
cp ~/couch/data/shadps4-particles/staging/fix/dvdroot_ps4/sfx/frpg_sfxbnd_m24_02.ffxbnd.dcx \
   ~/games/ps4/CUSA00900/dvdroot_ps4/sfx/
```

Checked the patch-dir shadow trap from `tools/bb-patchdir-fix`: there is **no**
`frpg_sfxbnd_m24_02.ffxbnd.dcx` in `CUSA00900-patch/dvdroot_ps4/sfx/` (it holds
only m29a and m29c), so the base-dir copy really is the one that loads. Revert
is a copy-back of the saved vanilla file.

**Fallback if the SFX swap does not take:** fight her at 30 fps, the workaround
the upstream thread settled on. `bb-fps` only offers 60/90/120; adding
`'30': None` to its `TARGETS` dict makes `bb-fps 30` work, since this eboot's
delta is dynamic and vblank alone sets the rate.

**Emulator, separately and not as the fix:** take `d6857fb` as hygiene next time
you rebuild. It cherry-picks clean and removes a real stale-GDS-address bug. Do
not attribute any Ebrietas improvement to it. Leave `fc74821` and `e29cf71`
alone until the 87-commit rebase is done properly.

## (d) Test plan

1. Close the game. Install as above. Relaunch, stay at vblank 60 (`bb-fps status`
   should print `fps target: 60`).
2. Go to Ebrietas. Watch her **ground-slam / ground-break attack**: the rock
   debris must appear, play out and vanish within a couple of seconds. Old
   behaviour: debris accumulates and never clears, and the pile grows every slam.
3. Also check the two secondary reports, which may or may not be in the same
   binder: the summoned Mensis Scholar's aura, and the water spouting pebbles.
   If the rocks are fixed but those two remain, the arena's other SFX binders
   (`frpg_sfxbnd_m24.ffxbnd.dcx`, `frpg_sfxbnd_commoneffects.ffxbnd.dcx`) are the
   next thing to swap; the full mod-41 v29 build covers them.
4. Proof: **your eyes, not MangoHud.** See below.

## (e) Not verified, stated plainly

- **The MangoHud CSVs cannot see this problem.** Both of tonight's runs
  (`shadps4_2026-09-05_23-14-23.csv`, 74,455 samples, and
  `..._23-50-06.csv`, 24,420 samples) read fps median **60.0**, 1st percentile
  59.6, and every 600-sample window medians at exactly 60.0. VRAM peaked 7.5 GB,
  GPU load median 61-64%. The presenter paces to vblank, so MangoHud is counting
  presents, not guest simulation: it will read 60.0 while the game itself is
  crawling. Do not use these CSVs to judge the fix, and there is no log line that
  proves it either. Judge it by looking at the rocks.
- I could not confirm which of the three visual complaints beyond the rocks the
  m24_02 swap covers. The mod author only claims the ground-break attack.
- I did not confirm that Bloodborne uses `ds_append`/`ds_consume` at all
  (needs `dump_shaders`, needs the emulator).
- Nothing was built and nothing was installed. The only writes this
  investigation made are under `~/couch/data/shadps4-particles/`.
