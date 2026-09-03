# ds3-shot: unattended Dark Souls 3 UI screenshots

Photographs DS3's UI with nobody home, nothing on the TV, no controller, no
audio in the living room. Built 1 Sep 2026 for the MENU_DS3_LOGO / UI-mod
work so a change can be checked remotely against real renders.

    tools/ds3-shot              # inventory journey: ingame.png, equipment.png, inventory.png
    tools/ds3-shot title        # title.png (zero interaction, no save loaded)
    tools/ds3-shot menu         # mainmenu.png
    tools/ds3-shot loadlist     # loadlist.png (the character list, read-only)

Outputs land in `data/ds3-shot/shots/` and the paths are printed on stdout.
Non-zero exit and a loud message on any failure; nothing is left running
either way. A run takes 90-120 s. The vanilla reference frame for diffing is
`data/ds3-shot/reference/title-vanilla.png` (captured before any UI mod).

## How it works

- **Display**: gamescope `--backend headless` (the shadPS4 soak precedent,
  `~/src/gamescope/build/src`). The game renders on the GPU with no window on
  :0. Children get a nested Xwayland display (`:1`); the harness reads it
  from `data/ds3-shot/child-display`.
- **Game**: Proton Experimental invoked directly (`proton run`), bypassing
  `game-launch` and the whole TV/Kodi/pad handover.
- **Sandbox prefix**: `data/ds3-shot/compatdata-374320` is a full copy of the
  real compatdata. The real save file is NEVER OPENED by the harness; the
  copy has deliberately diverged from it (see State below).
- **Sandbox game dir**: `data/ds3-shot/game` is a farm of symlinks to the real
  `DARK SOULS III/Game` plus our own `steam_appid.txt`. The real install is
  read-only to the harness.
- **Screenshots**: `gamescopectl screenshot` (gamescope's own compositor
  capture). NOT X11 GetImage - see traps.
- **Input**: XTEST keys and mouse clicks on the nested Xwayland display via
  python3-Xlib. No controller, no rigs.
- **Verification**: every emitted PNG must be 1920x1080 with non-trivial
  variance; the journey additionally gates on two pixel probes calibrated
  from live captures: the main-menu highlight ellipse, and the in-game HUD
  (red HP bar + green stamina bar). A black frame cannot pass.
- **Audio**: a private `XDG_RUNTIME_DIR` hides the pipewire/pulse sockets, so
  the game finds no audio server. Nothing can reach the soundbar.

## State the harness depends on (do not casually reset)

The sandbox save (`compatdata-374320/pfx/.../DarkSoulsIII/*/DS30000.sl2`)
holds two things created on 1 Sep 2026, both of which live IN THE SAVE FILE:

1. **The harness character**: "shotbot", Knight, Level 9, parked at Cemetery
   of Ash. Created via New Game inside the sandbox. The inventory journey
   loads it with Continue (it is the newest save in the sandbox profile and
   every journey quits from it, so it stays the newest).
2. **Launch Setting = Play Offline** (System > Network). This is what makes
   the game boot showing "Offline" with no server login. DS3 persists it in
   the save file on a clean quit.

`--refresh-save` therefore refuses to run without `DS3SHOT_I_UNDERSTAND=1`,
because re-copying the real save DESTROYS both and the next run would launch
ONLINE with nothing to load. After a refresh, re-provision by hand (below).

## Offline: what is actually guaranteed

Proven by capture: the main menu reads "Offline" and no login/announcements
dialog appears (`shots/offline_menu.png`). Mechanisms, strongest first:

1. DS3's own Play Offline setting in the sandbox save - the game does not
   attempt a server login at all.
2. No EasyAntiCheat files exist in this install (neither in Game/ nor the
   Proton EAC runtime), so a server handshake could not complete even if
   asked. This mirrors the standard offline-modding configuration.
3. The steam-remote shim + tripwire (below) stop the one observed path by
   which a launch could escape the sandbox.

What is NOT blocked: the Steam client itself is online (it always is on this
box), steam_api connects to it, and Donnie will show as In-Game: DARK SOULS
III on Steam while a run is in flight. Playtime accrues. That is Steam-level
presence, not game-server traffic.

A network namespace was tried and DOES NOT WORK - see trap 3.

## Provisioning (only needed after a save refresh or sandbox rebuild)

Semi-manual, using the dev verbs (`_dev start/shot/key/click/stop`) or a
session at the game: from the main menu set System > Network >
Launch Setting = Play Offline, quit cleanly via the menu (that writes the
save), relaunch, New Game, name a character, Knight, finalize, wait for the
Cemetery of Ash spawn, then in-game menu > System > last tab > Quit Game >
YES. The key/click grammar is in the traps below and in the tool's comments.

## Limitations

- Only the harness character's inventory/equipment can be photographed. The
  real characters are out of bounds by design (and the harness never opens
  the real save file at all).
- The journeys depend on menu geometry at 1920x1080 and on the sandbox
  save's state (Continue = shotbot). A UI mod that MOVES menu items or
  changes the boot flow can break navigation; the probes will catch it and
  fail loudly rather than emit wrong pictures.
- One run at a time (flock). Refuses to run during a live TV game session.
- First frame ~10-20 s warm; budget 3 min for a cold shader-cache boot.

## TRAPS (each one cost real time; all observed live on 1 Sep 2026)

1. **Direct `proton run` of DS3 relaunches the game through Steam.** The exe
   execs `steam.exe steam://run/374320//` when steam_api cannot verify the
   session; Proton forwards that to the HOST Steam client via
   `steam-runtime-steam-remote` (found on PATH), and Steam then launched the
   REAL game, with the REAL prefix and save, outside the sandbox, on the
   session display. It happened twice before it was contained. Defences, all
   three active: `steam_appid.txt` in the sandbox game dir, a no-op
   `steam-runtime-steam-remote` shim leading PATH, and a tripwire that kills
   any `SteamLaunch AppId=374320` process on sight.

2. **`SteamAppId`/`SteamGameId` env vars alone did NOT stop the relaunch.**
   They were exported from the start; the relaunch still fired whenever
   steam_api could not reach the Steam client. Reachability is the real
   trigger (see 3), the appid file/env only matter once the client answers.

3. **A network namespace breaks Steam IPC and CAUSES the relaunch.** Inside
   `unshare --net`, wine logs `steamclient_init_registry Failed to connect to
   Steam`, steam_api gives up, the game requests the Steam relaunch and
   exits. The IPC needs the host network namespace (abstract socket or
   localhost TCP). So netns-offline and a working direct launch are mutually
   exclusive for this title; offline is enforced at the game level instead.

4. **gamescope segfaults inside an unprivileged userns.** `/tmp/.X11-unix`
   maps to an unmapped owner, wlroots refuses to create Xwayland sockets
   ("not owned by root or us"), then crashes. If you ever need a namespace,
   put only the game inside it, never gamescope. (Moot now - see 3.)

5. **X11 GetImage sees black under gamescope WSI.** The game presents via
   the gamescope WSI layer, not through Xwayland, so `import`/xwd on :1
   capture nothing. `gamescopectl screenshot` reads the composited plane and
   is the only correct capture path. It needs `XDG_RUNTIME_DIR` and
   `GAMESCOPE_WAYLAND_DISPLAY=gamescope-0` pointing at the harness's private
   runtime dir, and it saves ASYNCHRONOUSLY - wait for the file.

6. **DS3's menus ignore Return, Escape (mostly), Tab and PageDown.** The real
   keyboard grammar: arrows navigate, `e` = confirm (A), `q` = back (B).
   Escape works only for opening the in-game menu. Dialogs whose prompts show
   controller glyphs (the announcements box, YES/NO confirms) do not respond
   to any key tried - they need MOUSE CLICKS on the buttons. The System
   settings category tabs are also mouse-clickable (y=240; in-game the last
   tab at x=1105 is Quit Game). Mouse motion+click via XTEST works
   everywhere.

7. **"No EAC = offline" is FALSE for login.** Without EAC files the game
   still attempted a server login and SUCCEEDED (fetched the server
   announcements box; regulation 1.35 intact). Only DS3's own Play Offline
   setting stops the attempt. That setting lives in the SAVE FILE and only
   persists on a clean in-game quit - backing out of the settings menu writes
   nothing to disk.

8. **The save file is one file for ALL characters** (`DS30000.sl2`, BND4
   container, AES-encrypted entries). There is no per-character file to
   isolate; any run that can write a character can write the file holding the
   irreplaceable one. Hence the sandbox-copy design: the real file is never
   opened. Also: as of 1 Sep 2026 the real save contains ONLY "lenk"
   (Level 92, 26h) - the promised 5-minute throwaway did not exist in it,
   which is why the harness has its own character instead.

9. **pgrep self-match, two new flavours.** (a) A monitor/guard whose script
   text contains the pattern kills ITSELF (`pgrep -f "SteamLaunch
   AppId=374320"` matched the guard's own bash). Bracket-escape the pattern:
   `AppId=37432[0]`. (b) teardown's sweep kills any OTHER shell whose command
   line merely mentions the sandbox paths - never run `ds3-shot` in a
   compound command that also names `compatdata-374320` or `ds3-shot/game`,
   or your own shell gets reaped (exit 144).

10. **The launch subshell inherits the tool's flock fd** and would hold the
    lock for the whole game session; `exec 9>&-` inside the subshell. Same
    family: gamescope needs `gamescopereaper` on PATH or it dies instantly.

11. **The gamescope session ignores SIGTERM at the title screen** (the game
    swallows it); teardown escalates to SIGKILL after 10 s. Safe here because
    every journey quits through the game's own save-and-quit first, so no
    save write can be in flight by the time the kill lands.

12. **`~/.local/bin/proton` is NOT Valve Proton** - it is the triton
    profiler's CLI. Always use the full path to the Steam Proton script.

13. **DS3 writes nothing to disk on settings Apply.** Changed settings only
    reach the save on clean quit. Verify persistence by relaunching, not by
    watching file mtimes after the change.

## What was verified, and how

- Two consecutive `ds3-shot inventory` runs end-to-end (23:02 and 23:04,
  1 Sep 2026), each producing fresh 1920x1080 PNGs of the in-game HUD, the
  Equipment screen and the Inventory screen, verified by eye (Estus Flask
  card, Player Status column, Long Sword item card) and by the pixel probes;
  plus `ds3-shot title`. Nothing left running afterwards (pgrep clean).
- The real save's md5 was checked repeatedly through the session and never
  changed: `136380b6fddc850f40e139d0f7326d76`, mtime 30 Aug 01:52 throughout.
- "Offline" proven by capture at the main menu after the setting persisted.

## Traps found 3 Sep 2026 (agents and captures)

* `teardown` pkills anything whose command line matches `ds3-shot/game` or
  `compatdata-374320`. That includes the shell that called it, background
  waiters of the calling session, and a `pgrep` you typed with those strings.
  Put deploy+capture+copy in a script file, run it under
  `flock data/ds3-shot/agent.lock`, poll its log, and write such patterns as
  `D[a]rkSoulsIII` when you grep for the game yourself.
* `DS3SHOT_FAST=1` exits the journey before the pause-menu shot, so
  `DS3SHOT_PAUSE=...` needs a non-fast run. Modes: `1` (one shot), `sweep`
  (Right x4), `down` (one Down), `downsweep` (Down x5). `DS3SHOT_STATUS=1`
  adds a Status screen shot; `DS3SHOT_EARLY=1` a sweep during the load.
* A run that dies without `_dev stop` leaves the gamescope session and
  `data/ds3-shot/lock` behind, and the next launch never renders a frame
  ("no rendered frame within 180s"). Kill the leftovers by pid, remove the
  lock file.
* `--refresh-save` needs `DS3SHOT_MOD=1` too when mod overrides are staged
  (the preflight guard runs for every verb). It replaces the harness
  character with the real save; `tools/ds3-state load harness-cemetery-20260903`
  brings the Cemetery character back.
* Reading a sandbox game's memory without sudo: make your process a child
  subreaper before `_dev start` (tools/ds3-menuflag-scan does it), and walk
  children per thread (Wine forks from worker threads).
