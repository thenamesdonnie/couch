# gamescope spike — 6 Aug 2026 (LG C5 arrival day)

Feasibility spike for couchd stage 3 (charter: "gamescope IS the adoption —
never fork it, wrap it"). Question: what does it take to run gamescope on
THIS box (RX 9070 XT / Mesa 25.2.8 / kernel 6.14 / noble / X11+xfwm4),
without root?

**Verdict: build-now. A full gamescope 3.16.25 was built and smoke-tested
today with ZERO new system packages and no sudo.** Binary at
`~/src/gamescope/build/src/gamescope`. One optional apt line (below) makes
the setup cleaner, but nothing is blocked on it.

## 1. What exists today (checked 6 Aug 2026)

- **apt (noble)**: nothing. `apt-cache policy gamescope` = no candidate.
  Noble never got the package (wlroots/wayland dependency chain too old).
  Only hit is `mangoapp`.
- **PPA ppa:3v1n0/gamescope** (Marco Trevisan): gamescope
  **3.16.19-1~24.04.3 for noble, uploaded 20-21 Jan 2026** — actively
  maintained, 9 packages including its own wlroots-0.19. Still the stage-3
  design note's objection: it swaps in newer libwayland/libpixman
  system-wide on the living-room box. Viable fallback, not preferred.
- **PPA ppa:mortigar/gamescope**: 3.14.17, June 2024, dead (no activity in
  ~2 years). Skip.
- **Flatpak** `org.freedesktop.Platform.VulkanLayer.gamescope`: exists and
  is maintained, but it's a runtime extension aimed at **Flatpak Steam**;
  our Steam is native, and the tracker has repeated "nested X11 broke
  again" issues (#122: X server error on recent versions; socket-bind
  failures). Wrong shape for us. Skip.

## 2. The source build that worked (no sudo, no system installs)

Tag **3.16.25** (latest, ~/src/gamescope), all 19 submodules synced.
Noble's showstoppers and how each fell:

| Dep | Noble has | Needs | Resolution |
|---|---|---|---|
| wayland-server | 1.22.0 | >= 1.23.1 (wlroots 0.19.3) | meson subproject, static (wayland 1.26.0) |
| pixman-1 | 0.42.2 | >= 0.43 (wlroots) | meson subproject, static (0.46.5) |
| luajit | not installed | required | built locally into `~/src/prefix` (LuaJIT 2.1, seconds to build) |
| xwayland (.pc + binary) | not installed | build + runtime | **noble .deb extracted** (no install) into `~/src/prefix/xwayland`, .pc prefix rewritten; `ldd` clean, `Xwayland -version` runs (23.2.6) |
| wlroots 0.19.3, libliftoff, vkroots, libdisplay-info, openvr, glm, stb | — | — | vendored subprojects, static |
| everything else (X11 libs, libdrm 2.4.125, libinput, libseat, sdl2, libavif, libdecor, wayland-protocols 1.45, glslang, vulkan) | already present | — | this box is unusually well-stocked from earlier source work |

Optional-but-skipped: libpipewire-0.3 (screen capture feature, auto-off),
xcb-errors (not packaged in noble at all, wlroots optional), catch2
(unit tests, disabled), google-benchmark (disabled).

Three local build tweaks were needed (all recorded here so they aren't
re-derived; none touch gamescope's runtime code — this is still "wrap,
never fork"):

1. `subprojects/wayland.wrap` and `subprojects/pixman.wrap` copied up from
   `subprojects/wlroots/subprojects/` (meson only honours wraps at the
   superproject level), pinned wayland to tag `1.26.0`, and given
   `[provide]` sections (`dependency_names = wayland-server, wayland-client,
   wayland-cursor, wayland-egl` / `= pixman-1`) so the WHOLE tree uses one
   wayland — mixing static subproject wayland with system 1.22 in one
   binary would be a symbol-clash minefield.
2. One-line fix in `protocol/meson.build:4` — add
   `internal: 'wayland_scanner'` to the `get_variable(pkgconfig: ...)`
   call (upstream never hits this because distros build against system
   wayland; PR-able upstream).
3. `-Dwayland:scanner` stays default (true); the subproject's own scanner
   is used via meson override.

The configure line (from `~/src/gamescope`):

```
PKG_CONFIG_PATH=$HOME/src/prefix/lib/pkgconfig:$HOME/src/prefix/xwayland/usr/lib/x86_64-linux-gnu/pkgconfig \
meson setup build -Ddefault_library=static -Dbenchmark=disabled \
  -Denable_openvr_support=false -Denable_tests=false \
  --force-fallback-for=libliftoff,vkroots,wayland,pixman \
  -Dwayland:tests=false -Dwayland:documentation=false -Dwayland:dtd_validation=false \
  -Dpixman:tests=disabled -Dpixman:demos=disabled
ninja -C build -j8
```

Artifacts: `build/src/gamescope` (+ `gamescopereaper`, `gamescopectl`),
WSI layer `build/layer/libVkLayer_FROG_gamescope_wsi_x86_64.so` +
`VkLayer_FROG_gamescope_wsi.x86_64.json`. ~1.7 GB tree, ~4.8 MB prefix.

### The optional apt line (cleanliness, not necessity)

```
sudo apt install xwayland libluajit-5.1-dev libpipewire-0.3-dev
```

- `xwayland` replaces the extracted-deb hack (then delete
  `~/src/prefix/xwayland`, drop its PKG_CONFIG_PATH entry, reconfigure —
  the Xwayland path is baked in at configure time).
- `libluajit-5.1-dev` replaces the local LuaJIT prefix.
- `libpipewire-0.3-dev` turns on the screen-capture feature (nice for the
  phone app's screen tab, not required).
- wayland/pixman stay static subprojects forever — noble can never ship
  them new enough; that part is not fixable by apt.

## 3. Smoke test (nested, windowed, under the live X session)

`gamescope -w 1280 -h 720 --backend sdl -- glxgears` with
`PATH=$HOME/src/gamescope/build/src:$PATH` (it execs `gamescopereaper`
from PATH — without it, instant "Failed to start process" abort).

- **Composites correctly.** RADV picks up the 9070 XT, DRM format
  modifiers supported, embedded Xwayland spawns on `:1`, gears render in
  a floating xfwm4 window.
- **Steady 30.0 fps** — this is the *unfocused* nested window path (test
  ran headless-ish; window never had host focus). `-r 60 -o 60` did not
  lift it; didn't chase further since the TV was in evening use and the
  production path is embedded DRM anyway. A focused window should vsync
  at 60; re-verify by hand once.
- **Child-exit gate (the stage-3 recipe's #2133/#2139 concern)**: on
  `glxgears` exiting, gamescope logs "Primary child shut down!" and
  terminates promptly — good for session lifecycle — **but via SIGSEGV in
  teardown (exit 139), reproducibly, at 3.16.25**. No stray processes
  left behind after ~1 s. So the recipe's "pin 3.16.19" caution still has
  teeth: exit code 139 vs 0 matters if couchd ever inspects the wrapper's
  exit status. Either pin 3.16.19 (checkout + same recipe, subprojects
  may differ slightly) or treat any-exit-as-exit in the wrap.

## 4. The 4K120 / VRR / HDR path (once the DP->HDMI 2.1 adapter arrives)

Flags confirmed against the 3.16.25 source (`src/main.cpp`):

- Resolution/rate: `-W 3840 -H 2160` (output), `-w`/`-h` (game render
  res), `-r 120` (nested/game refresh), `-o` (unfocused rate).
- **VRR**: `--adaptive-sync`. Only meaningful in **embedded** mode
  (`--backend drm`, gamescope owns the display); in nested mode the host
  X server owns vsync and xfwm4 has no VRR.
- **HDR**: `--hdr-enabled` (+ `--hdr-sdr-content-nits N`, default 400,
  for SDR content luminance; `--hdr-itm-enabled` + `--hdr-itm-sdr-nits` /
  `--hdr-itm-target-nits` for SDR->HDR inverse tone mapping; debug:
  `--hdr-debug-force-support`, `--hdr-debug-force-output`,
  `--hdr-debug-heatmap`). Requires the **WSI layer** installed for
  clients (point `VK_ADD_LAYER_PATH`/`XDG_DATA_DIRS` at
  `build/layer/`, or copy the json+so into
  `~/.local/share/vulkan/implicit_layer.d` with a fixed .so path), and
  `DXVK_HDR=1` for Proton titles. HDR is also embedded-mode-only.
- Hardware chain notes: AMD has no native HDMI 2.1 FRL on Linux (HDMI
  Forum blocked it) — 4K120 needs the DP->HDMI 2.1 adapter, which is
  exactly what's in the post. VRR passthrough over such adapters is
  adapter-chip-dependent; the C5 does HDMI VRR, so test with the actual
  adapter before promising it. Kernel 6.14 mainline amdgpu exposes the
  standard `Colorspace`/HDR metadata connector props gamescope's
  shader-composite HDR path uses; the Steam-Deck-private AMD color props
  (scanout offload) are NOT in Ubuntu generic kernels — expect the
  shader fallback, verify on hardware.
- Embedded mode on this box means gamescope on its own VT (libseat/logind
  grants DRM master to the active VT's session, still no root), i.e. a
  VT-switch away from the Kodi X session — that is stage-4-shaped
  territory and a separate design note. Nested-under-X11 today gets
  window collapse + upscaling only: no VRR, no HDR.

## 5. Recommended wrap point (charter stage 3: wrap, never fork)

Unchanged from `couchd-stage3-design.md`'s preserved recipe, now
unblocked by the C5:

- Per-game Steam launch option `scopebuddy -- %command%` (shape (a)) —
  the only reversible integration; gamescope lands inside the reaper tree
  so game-pids/freeze/thaw/guard survive unchanged. Rollback = delete the
  launch option.
- Keep honoring the recipe's NEVERs: no `-e`/`--steam`, no `-g` grab
  (SIGSTOP + grab = wedge), no setcap CAP_SYS_NICE on the binary.
- The three `steam_app_*` window-class dependents (steam-input-guard:272,
  screen.js:271/:291) still need the class-regression check before any
  real-game trial.
- Pre-flight gates from the recipe: nested glxgears (PASSED today),
  exits-when-child-exits (passed-with-segv, see §3 — decide pin vs
  tolerate before cutover), `import -window root` not black (untested).
- Do NOT re-run today's dependency archaeology: the working tree in
  `~/src/gamescope` + this doc + `~/src/prefix` are the whole recipe.
  The stage-3 note's claim "`~/gamescope-deps.sh` is WRONG" still stands;
  today's list supersedes it.

## State left on the box

- `~/src/gamescope` — tag 3.16.25 + the 3 build tweaks, fully built.
- `~/src/LuaJIT`, `~/src/prefix` (luajit install + extracted xwayland deb).
- Nothing installed system-wide, nothing running, no strays, not committed.
