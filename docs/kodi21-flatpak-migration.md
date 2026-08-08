# Kodi 20 (apt) -> Kodi 21 (Flatpak)

Written 8 Aug 2026, from a work-day session with the TV in standby. Everything
here that could be verified without root or a live Kodi 21 has been verified;
everything that could not is marked **UNVERIFIED** and carries the command that
settles it.

## Why

Ubuntu's repos stop at Kodi 20.5 and the team-xbmc PPA has no noble build, so
Flathub is the only route to 21. What we are buying:

- The Python 3.12 subinterpreter-teardown segfault (xbmc/xbmc#24440) that makes
  a third to a half of cold boots crash once. The Flatpak carries its own
  Python inside the Freedesktop 24.08 runtime, so the host's 3.12 stops being
  our problem.
- Whatever that buys us in turn: the `kodi-tv` crash-restart loop, the
  `reuselanguageinvoker` metadata we re-apply after every addon update, and the
  never-live-switch-skins rule all exist to work around that one bug.
- Possibly the two wedged-Kodi episodes of 8 Aug (answers a JSON-RPC ping,
  ignores everything else).

Rollback stays "launch the old one": apt Kodi is not touched, not purged, and
its profile at `~/.kodi` is left byte-identical apart from one deliberate
change described under *The skin problem* below.

## What the Flatpak actually is

App id **`tv.kodi.Kodi`** (not `org.xbmc.Kodi`, which 404s on Flathub).
Stable is **21.3-Omega** on `org.freedesktop.Platform//24.08`. Facts taken from
the Flathub manifest (`flathub/tv.kodi.Kodi`, `tv.kodi.Kodi.yml` and
`patches/kodi.sh.in.patch`), not from memory:

**The profile moves.** The Flathub build patches `kodi.sh` to

```sh
export CRASHLOG_DIR=${XDG_DATA_HOME}
export KODI_DATA=${XDG_DATA_HOME}
export KODI_HOME=/app/share/kodi
```

so `special://home` is **`~/.var/app/tv.kodi.Kodi/data/`**, not `~/.kodi` and
not `~/.var/app/tv.kodi.Kodi/.kodi`. `userdata/`, `addons/`, `temp/` and
`media/` all hang off that. Crash logs land there too instead of `$HOME`.

**Binary addons are built in.** `addon-list.txt` in the manifest compiles
`inputstream.adaptive`, `inputstream.ffmpegdirect`, `peripheral.joystick`,
`vfs.*`, the audio decoders and the screensavers into the app. So:

- our hand-assembled `~/.kodi/addons/inputstream.adaptive` (dpkg-deb'd out of
  the Debian package, needing `libwebm.so.1` off `~/.local/lib` via
  `LD_LIBRARY_PATH`) is **not migrated** - it is host-ABI and would shadow the
  Flatpak's own. The `LD_LIBRARY_PATH` line in `kodi-tv` therefore only applies
  on the apt path.
- `kodi-peripheral-joystick` (apt) likewise stops mattering.

**What it is already allowed to do**, from `finish-args`:

| grant | covers |
| --- | --- |
| `--device=all` | the DualSense, `/dev/dri` |
| `--share=network` | JSON-RPC :8090, EventServer UDP :9777, notification TCP :9090, couch server :8790 |
| `--share=ipc`, `--socket=fallback-x11` | X11 (the session is X11, so fallback resolves to x11) |
| `--socket=pulseaudio` | PipeWire's pulse server |
| `--filesystem=/mnt` | **the media disks** - `sources.xml` reads `/mnt/media/...` directly |
| `--filesystem=/media`, `/run/media`, `/run/udev:ro`, `/run/lirc` | removable media, udev |
| `--system-talk-name=org.freedesktop.{login1,UDisks2,UPower,Avahi}` | suspend/idle, disks, battery |

**What it is not allowed to do**, and what we add - see *Overrides* below.

## The migration, decided

### Copy, not symlink, for the profile

`~/.kodi` is **copied** to `~/.var/app/tv.kodi.Kodi/data/`. Not symlinked, not
bind-mounted, not shared. The reason is the rollback promise:

- Kodi 21 upgrades the video/music databases on first run (`MyVideos121` ->
  `MyVideos131`) and rewrites `guisettings.xml`, `profiles.xml` and every
  `addon_data/*/settings.xml` in its own format. A Kodi 20 that later reads
  those gets a downgrade it has no code path for.
- `addons/` cannot be shared either: the two Kodis disagree about which addons
  are compatible (see below), and each writes its own `addons*.db`.

The cost is ~360 MB of duplicated profile and the fact that a library watch or
a resume point recorded on one build is invisible to the other. That is the
correct trade while apt Kodi is a parachute rather than a daily driver. When
the parachute is cut, `~/.kodi` gets deleted and the duplication goes with it.

Not copied: `addons/packages` (212 MB of addon zips, a cache), `temp/`,
`addons/inputstream.adaptive` (above), `addons/skin.arctic.zephyr.mod` and
`addons/skin.copacetic` (both refused by Kodi 21, see below).

### The skin stays a symlink - but only in the new profile

`skin.couch` is the one thing that *is* a symlink, because it is git-tracked at
`~/couch/kodi-addons/skin.couch` and the whole point of that arrangement is
edit-in-repo, reload-on-TV. That does not change.

### The skin problem

Kodi 21's `addons/xbmc.gui/addon.xml` reads

```xml
<addon id="xbmc.gui" version="5.17.0" provider-name="Team Kodi">
  <backwards-compatibility abi="5.17.0"/>
```

Kodi 20's has no `backwards-compatibility` element at all. A skin declaring
`<import addon="xbmc.gui" version="5.16.0"/>` is therefore **refused by Kodi
21**, and a skin declaring `5.17.0` is **refused by Kodi 20**. There is no
value that satisfies both, and no conditional in addon.xml. Verified against
both tags; this is also why Copacetic keeps a `nexus` branch (1.6.9, gui
5.16.0) separate from `master` (2.7.0, gui 5.17.0).

Consequence, and the one deliberate change to the old profile:

- `~/.var/app/tv.kodi.Kodi/data/addons/skin.couch` -> symlink to the repo, and
  the repo's `addon.xml` moves to `5.17.0`. This is the living skin.
- `~/.kodi/addons/skin.couch` stops being a symlink and becomes a **frozen
  copy** of the skin as it stands at cutover, still declaring `5.16.0`. So a
  rollback to apt Kodi gets the skin it had on the day, not a 5.17 skin it
  would refuse.

Done while Kodi is down, during the cutover, not under a live instance.

`skin.arctic.zephyr.mod` (gui 5.15.0) and `skin.copacetic` (5.16.0) are refused
by Kodi 21 and are not migrated. The fallback skin on the new profile is
Estuary, which ships inside the app. Every other installed addon imports
`xbmc.python` 3.0.0 or 3.0.1, and Kodi 21 ships `xbmc.python` 3.0.1 with
`<backwards-compatibility abi="3.0.0"/>`, so **no other addon is blocked** -
checked across all 55 installed addons.

## Overrides, and why each one

Applied with `flatpak override --user tv.kodi.Kodi`. Three grants:

| override | why |
| --- | --- |
| `--filesystem=home` | Kodi's own plugins read the whole console out of `$HOME`: `~/.steam/**` (the Steam manifests and library art the Games row is built from), `~/games/ps4`, `~/.local/share/game-tiles/**` (composed tiles, heroes, achievements, playtime stamps), `~/.local/share/shadPS4`, `~/couch/data/**` (paused frames, loading cards), `~/couch/tools/**`. The narrow alternative is eight `--filesystem=` lines that would go stale the next time a path moves; on a single-user box where Kodi already runs as that user, one line is honest. |
| `--filesystem=/tmp` | The console's coordination flags live in `/tmp` - `game-session`, `game-suspended` - and a Flatpak gets a private tmpfs there by default, so `script.tvpoweroff`, `script.couch.switcher` and `games.py` would all read an empty directory and conclude no game is running. Also keeps `TakeScreenshot(/tmp/x.png)` working. `/tmp` is not in flatpak's `dont_export_in` list (`common/flatpak-exports.c`), and `never_export_as_symlink()` special-cases it, so exporting it is a supported path. **UNVERIFIED until flatpak is installed** - `tools/kodi21-migrate verify` checks it directly and the addons have a fallback that does not depend on it. |
| `--talk-name=org.freedesktop.Flatpak` | The escape hatch. Kodi has to *run host programs*: `games.py` spawns `~/.local/bin/game-launch` and three `~/couch/tools/*` fetchers, `script.tvpoweroff` spawns `~/.local/bin/tv` and `game-launch`. Those are host scripts wanting `xdotool`, `xrandr`, `pgrep`, `wmctrl`, `steam`, `bluetoothctl` and the host `python3` - none of which exist in the Freedesktop runtime, however visible the script file is. `flatpak-spawn --host` runs them in the real session, and needs this bus name. |

This is close to "sandbox off", and that is deliberate: we are using Flatpak as
a *packaging* mechanism to get Kodi 21 onto noble, not as a security boundary.
Kodi already runs as `ds2000` with full access to everything listed. Nothing
here grants Kodi something the apt build did not already have.

## Crossing the sandbox

`~/couch/kodi-addons/couchhost/couchhost.py` is the shim, vendored into each
addon that needs it. Three calls:

- `host_run(argv, **kw)` - `subprocess.Popen`, transparently prefixed with
  `flatpak-spawn --host` when running inside a sandbox.
- `host_read(path)` - file contents or `None`; direct read first, then
  `flatpak-spawn --host cat` if the direct read fails inside a sandbox. So the
  `/tmp` override is an optimisation, not a dependency.
- `in_sandbox()` - `os.path.exists('/.flatpak-info')`. On the apt build every
  call is a plain passthrough, which is what keeps rollback honest.

## Which Kodi is running

`~/.local/bin/kodi-tv` grew a flavour switch:

1. `$KODI_FLAVOUR` if set (`apt` or `flatpak`),
2. else `~/couch/data/kodi-flavour`,
3. else `apt`.

kodi-tv writes the resolved flavour back to `~/couch/data/kodi-flavour-active`
at launch, and that file is what the host stack reads to find the profile.
`couchd/kodiprofile.py` and `server/kodiprofile.js` are the two resolvers; both
fall back to `~/.kodi` when the file is absent, so nothing changes until the
switch is thrown.

Everything else in `kodi-tv` is host-side and flavour-independent, and stays
exactly as it was: the `flock` against twin instances, `xset` blanking off,
TearFree, the hand-built 4K120 modeline block, the `pactl` wait before launch,
the boot-unmute subshell, and the crash-restart loop.

The crash-restart loop still applies on the Flatpak path: the in-sandbox
`kodi.sh` exits with the child's status, so a segfault still surfaces as 139
through `flatpak run`.

## What we are NOT retiring yet

The point of the migration is to delete the crash-workaround layer, but none of
it can be *proved* dead from a work-day session with the TV in standby. Each
one below has a retirement criterion instead. Retire on evidence, one at a
time, not as a batch.

| workaround | retire when |
| --- | --- |
| `kodi-tv` crash-restart loop | 14 days with no `kodi_crashlog-*` in `~/.var/app/tv.kodi.Kodi/data/` and no `tries=` increment. It is also a general safety net, so the honest end state may be "keep, but stop pretending it is a Python bug". |
| `reuselanguageinvoker` in script.copacetic.helper / embuary | a cold boot with debug logging that shows no `Py_EndInterpreter` churn. Harmless and a small perf win either way, so this is the lowest-value one to remove. |
| never live-switch skins / never `ReloadSkin()` | one deliberate `ReloadSkin()` on Kodi 21 with the TV on and Donnie watching. This is the one that would change day-to-day work the most. |
| jellyfin `startupDelay=45` | after the above, since it exists purely to thin the boot churn window. |

## Checked, and cheaper than it looked

Things that read like they must break and do not. Each was checked against a
primary source rather than reasoned about, because each would have cost an
evening.

- **`XBMC.GetInfoBooleans` / `XBMC.GetInfoLabels` still exist in 21.3.** The
  legacy JSON-RPC namespace is right there in
  `xbmc/interfaces/json-rpc/JSONServiceDescription.cpp`. So `kodi-tv`'s
  boot-unmute wait and `tools/kodi-refresh-games`'s guard are safe. Had it
  gone, both would have failed *soft* - a two-minute timeout and a refresh
  that always says "leave it alone".
- **Pillow is inside the Flatpak** (`python-pillow`, 12.3.0, in the manifest).
  It reaches Kodi on the apt build only by accident, via the host's user
  site-packages, and `script.module.pil` is not installed - so this could
  have silently un-composed every home-row tile. `verify` imports it.
- **`kodi-send` comes from a separate package**, `kodi-eventclients-kodi-send`,
  not from `kodi`. Four host callers use it (`pause-snap`'s minimise
  animation, `pad-battery`, the server's `PlayerControl(tempo)`,
  `jellyseerr-watchnow`). Nothing is being purged, so this only matters the
  day apt-Kodi goes: keep that one package.
- **The media disks need no override.** `sources.xml` reads `/mnt/media/...`
  directly and the manifest already grants `--filesystem=/mnt`.
- **Nothing reads Kodi's log or crash logs**, and **nothing uses
  `TakeScreenshot`** - the only screenshots on the box are host-side X grabs
  (`pause-snap`, `server/screen.js`). So `CRASHLOG_DIR` moving into the app
  data dir costs nothing, and there is no screenshot path to redirect.
- **`~/.config/autostart/kodi.desktop` already runs `kodi-tv`**, so the launch
  path needed no change at all - the flavour switch inside kodi-tv is the
  whole of it.
- **Window identity is unchanged.** Every focus/raise path matches WM
  name/class `Kodi`, and Flatpak does not rewrite those. `pgrep -x kodi.bin`
  still matches, so `server/sys.js`'s hardened restart still works.

## Known, not fixed

- `16x9/MusicVisualisation.xml` references an include, `Like_focused`, that
  nothing defines. Inherited from Copacetic 1.6.1, unrelated to Omega, in a
  screen this box never opens. Pinned as a known exception in
  `tools/test_skin_omega.py` so the integrity check can be strict about
  everything else.
- `16x9/Custom_1196_Couch_HaloPicker.xml` hardcodes an absolute path to one
  game's composed tile (`.../game-tiles/composed/291550.png`). Works, because
  `--filesystem=home` covers it. Still a hardcoded appid in shipped skin XML.
- Seven tests in `tools/test_curtain.py` fail on this box: the curtain daemon
  does not write its pidfile under the test's private Xvfb. **Pre-existing** -
  they fail identically at `e222beb`, before any of this work - and unrelated
  to the migration. Worth its own look.

## It ran — 8 Aug 2026, ~19:30

Donnie ran the sudo; the rest was executed here. Kodi 21.3-Omega is live on
`skin.couch`, the TV never left standby.

**What was verified, not assumed** (JSON-RPC + Kodi's own `TakeScreenshot`,
which writes to `~/couch/recordings/skin-shots/` and so needs no TV):

- All 13 in-sandbox checks pass, including the one this doc had marked
  UNVERIFIED: **`--filesystem=/tmp` really does export the host `/tmp`.**
  `couchhost`'s `flatpak-spawn` fallback was proved working separately, so
  that override stays an optimisation.
- The **databases migrated**: `MyVideos131.db`, `MyMusic83.db` and `TV46.db`
  were created beside the untouched 121/82/40 originals — exactly the reason
  the profile is a copy. Library intact: **88 movies, 30 TV shows**.
  jellyfin-for-kodi logged its own "Omega database migration is complete".
- The **Games row renders 8 tiles** through the sandbox, art and all, with
  Bloodborne labelled **"· paused"** — which is `/tmp/game-suspended` being
  read across the boundary, i.e. couchhost end to end.
- **Achievements/trophies**: Elden Ring 42, Bloodborne 40 (the PS4 TRP
  trophies, real names), Hollow Knight 63.
- **Library page (1197)** renders Next up / Continue / New with artwork.
  **YouTube (1196)** returns the subscriptions feed and the plugin root; the
  sign-in tokens survived the copy. Its grid is empty for a few seconds on
  first open — that is API latency, not a fault.
- The **DualSense button map travelled** (`addon_data/peripheral.joystick/…/
  DualSense_Wireless_Controller_13b_8a.xml`), both keymaps travelled,
  `input.enablejoystick` is true, and `peripheral.joystick` initialised the
  pad with its 13 buttons against `game.controller.default`.

**Three things worth knowing:**

1. **Kodi 20 wedged on the way out.** `Application.Quit` saved settings, then
   hung in `CPythonInvoker: waiting on thread` at 110% CPU and never exited —
   the Python-teardown hang this migration exists to remove, on its way out
   the door. SIGKILL, as the runbook says. Nothing was lost (settings had
   already been written).
2. **Kodi 21 offered to install `game.controller.ps.dualanalog` and it was
   DECLINED, deliberately.** Our two joystick keymaps bind with
   `profile="game.controller.default"`, and a keymap whose profile does not
   match the pad's controller profile never attaches — that is a documented
   trap on this box. The pad works on `game.controller.default` as before.
   The install would have failed anyway: at +1s from a cold start the addon
   DB still held the **nexus** repository index inherited from the old
   profile, so it resolved a `…/addons/nexus/…` URL. The index refreshed
   itself to Omega (3.4.0) a minute later; nothing to fix.
3. **`Custom_1196_Couch_HaloPicker.xml` and `Custom_1196_Couch_YouTube.xml`
   both claim window 1196.** Kodi logs `id already in use` at every startup
   and loads the YouTube one; the halo picker is dead and its own comment
   calls it "temporary". Pre-existing, harmless, one line of log noise —
   deleting it is a one-liner whenever somebody wants to.

The three long-running consumers (`couch`, `couchd`, `pad-home`) were
restarted onto the new resolver and confirmed reading the new profile —
couchd logs `bindings: tap=home, double_tap=switcher, hold=context_menu`.
**couchd's model fingerprint moved to `44d3542b8bba`** (gestureconf changed
shape), which matters to whoever reads the shadow differ next.

## Verification ladder

`tools/kodi21-migrate` runs these in order and refuses to continue on a
failure. Steps 1-6 need no TV; step 7 needs Donnie.

1. `flatpak --version`, remote present, app installed, `21.3-Omega`.
2. Overrides applied and readable back (`flatpak override --show`).
3. Inside the sandbox: `$HOME/couch` readable, `/tmp/kodi-tv.lock` visible,
   `flatpak-spawn --host true` succeeds, `/mnt/media/movies` lists.
4. Profile copied, `skin.couch` symlink resolves, no `inputstream.adaptive`,
   `guisettings.xml` still carries webserver/port/password and the EventServer.
5. Kodi 21 starts, reaches home, answers JSON-RPC on :8090 and `kodi-send` on
   :9777, and reports `skin.couch` as the active skin.
6. Routes: Games row populates, achievements shelf opens, Library page, YouTube
   window 1196, `TakeScreenshot` of each.
7. Donnie, at the set: picture, audio over eARC, 4K120, the pad, a film, a
   game launch and a suspend/resume cycle.
