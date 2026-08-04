# Couch — todo / resume

Phone-first web remote for the living-room Kodi box. Node/Express backend
(`server/`) brokering Kodi JSON-RPC + kodi-send + games/TV/lights, Svelte 5 +
Vite frontend (`web/`), served at `http://192.168.4.147:8790`. Runs as the
systemd **user** unit `couch.service` — never `node index.js` by hand (double-binds 8790).

Deep context lives in auto-memory: `~/.claude/projects/-home-ds2000-couch/memory/`
(`homelab-couch-app.md` = full build log, `couch-ios-ui-quirks.md` = the iOS gotchas).

## Build / deploy
- Frontend edit → `cd ~/couch/web && npm run build` then `systemctl --user restart couch`.
- Server-only edit → just `systemctl --user restart couch` (no rebuild).
- Build stamp shows in the theme sheet (`build YYYY-MM-DD HH:MM`) to confirm the phone loaded fresh.

## ▶ Resume here (updated 4 Aug 2026, late night — couchd build session)

**READ FIRST: `docs/handoff-2026-08-04.md`** — the phone-readable sheet for
Donnie (what to test, the one command needed before pad use, the two
decisions only he can make). This block is the technical version.

**couch is now a GIT REPO** (standing risk closed). ~20 commits, history
born clean: all secrets scrubbed to `.env` (`server/config.js` reads env;
`data/secrets.json` legacy file still on disk, gitignored, deletable once
healthy), gitleaks-verified. Local only, no remote. `.env.example` current.

**LIVE on the box now** (all reversible; `systemctl --user stop couchd
pad-record` = back to 4-Aug-green, and that line is cheat-sheet line 1):
- `couchd.service` — stage-1 SHADOW daemon (`couchd/couchd.py`, 2.2k lines
  + `x11.py`). 7 observers, orthogonal state regions with `unknown`, pure
  `reconcile(observed)->intents`, invariants incl. owned-resources leak
  check, JSONL corpus in `shadow/`, `status.json`, Type=notify + watchdog,
  crash-loop-safe (Restart=on-failure/RestartSec=10/StartLimitBurst=5).
  Acts on NOTHING (only RecordingExecutor exists).
- `pad-record.service` — recorder, fixed: mtime-stamped markers at ~100ms,
  inline gzip, 14-day retention.
- Old stack instrumented (R3): watcher/game-launch/guard write machine
  intents to `/tmp/legacy-intents.jsonl` (log-only edits, behavior same).
- Phone: `/api/couchd/status` + Screen-tab couchd card.
- **Double-tap PS → TV switcher** (`script.couch.switcher` Kodi addon,
  versioned in `kodi-addons/`) and **gesture keybind settings** in Kodi
  (`couchd/gestureconf.py` is the single source both stacks read; safety
  rail forces a suspend_to_kodi binding). Both verified live tonight.

**NEXT (in order):**
1. **Donnie's couch pass** — checklist in the handoff sheet (his original
   pad checklist + the two new features). Every evening he uses the TV is
   shadow evidence toward the C9 gates.
2. **Morning after any evening:** `~/couch/tools/shadow-diff` (offline,
   never touches the TV). First real run: VALID, 0 divergences.
3. **Donnie's sudo session** (~10 min, `couchd/stage2/INSTALL.md`):
   couchd-input group + system user, udev rule (staged `.off`), rollback
   script + sudoers, inputproc.service, rollback REHEARSAL. Plus fix
   pad-connect-daemon + tv-waker's any-`js*` checks (see Open decisions).
4. Then E2 (Steam adopts the virtual pad; daytime, back up
   `~/.steam/debian-installation/config` first), then stage-2 flag day.

**Deferred to a daytime window:** psfuzz/chaos identity runs with couchd
live (M9), the `STEAM_GAMES_RUNNING` atom re-test with a game running.

## Changelog — 2026-08-04 (late night, couchd build session)
Notes: `docs/couchd-stage1-design.md` (C1-C31 + rulings R1-R8),
`couchd-stage2-design.md` (S1-S9 + SR1-SR9), `couchd-stage3-design.md`.
- **Stage 1 SHIPPED to shadow.** /build pass (3 research agents: parallel-run
  practice, reconciler/statechart architecture, console-daemon prior art) then
  2 adversarial reviews. Biggest ruling: the old stack ALREADY logs its
  decisions, so the planned effect-inference engine died and ~4k LOC became
  ~1k. couchd + `tools/shadow-diff` (22 tests) + 30→191 test suite.
- **Stage 2 designed and built synthetic-only.** InputPlumber evaluated per
  charter and DECLINED with receipts (root-only #202, crash-bricks-pad #582,
  20-month rumble TODO #224, no kernel timestamps); its udev technique,
  persistence and 80ms chord pacing ported instead. Review found 8 blockers
  (no-root claim unimplementable as written → system-user model; 0640 would
  have silently killed rumble; sudo-at-night rollback; rig would wake the TV).
  Built: `couchd/gesture.py` (shared), `inputproc.py` (grab + exact-vpad X360
  clone + full FF contract), `tools/fake-pad` (uhid DS5 rig with inhibit
  frame), `couchd/stage2/` install bundle. **E0 + E1-functional PASSED**:
  forwarding p99 0.065-0.17ms (10ms budget), FF contract live, PS tap
  re-injected at 80.3ms / hold swallowed, persistence machine, Kodi buttonmap
  resolves, face-button transposition confirmed on hardware.
- **Stage 3 PARKED** with a written decision record (nothing to win at
  1080p60 SDR; `~/gamescope-deps.sh` is wrong as staged, corrections in the
  note). Revisit on TV upgrade / in-repo packaging / stage 4.
- **Double-tap PS → TV switcher** and **Kodi gesture keybind settings**
  (Donnie's requests) shipped and verified live.

## Roadmap: couchd (agreed 4 Aug 2026 — build rules: docs/couchd-charter.md)
The accretion phase is over; the architecture is understood (see
docs/audits/console-robustness-2026-08.md = the requirements spec, and
tools/psfuzz.py + tools/chaos.py = the acceptance tests). Strangler-pattern
consolidation into one control-plane daemon; engines (Kodi/Steam/games) stay.
The TV must keep working at every stage. Start AFTER the physical-pad pass.
1. **couchd**: one daemon absorbing pad-home-watcher + game-launch +
   steam-input-guard + reconcile. Internal state machine (no /tmp flags),
   API socket for couch app + Kodi tiles, structured logs, events stream.
2. **Input ownership**: couchd exclusively grabs the DualSense (evdev grab +
   udev-hide hidraw from Steam), presents a virtual pad (uinput/uhid) to the
   focused app. PS button becomes ours by construction; guard war deleted.
   Tradeoff accepted: games see generic X360 pad (no DS gyro/haptics).
3. **Gamescope-nested games**: game launches wrap in gamescope (deps script
   staged at ~/gamescope-deps.sh, needs Donnie's sudo once). Frame pacing +
   contained fullscreen. EXPERIMENT: NVIDIA+X11 is gamescope's weak combo.
4. **Own session compositor** (smithay/wlroots): couchd becomes the session;
   Kodi + games are surfaces. Months; only if 1-3 leave us hungry.

**Publishing (agreed direction):** share as a reference project ("my console
setup"), not a product - killer README from the audit doc, positioned as
"console-ify the box you already have" (vs Bazzite's OS takeover; see the
why-not-Bazzite reasoning: patched bluetooth.ko, X11 click-through, SIGSTOP
suspend all need a mutable X11 box). PREREQS before anything public: git init
(private first), scrub secrets into .env + .env.example (kodi password in
kodi.js, qBittorrent creds in downloads.js, LAN IPs throughout) so public
history never contains them. couchd, once real, is the properly adoptable
core. Generalise (Android TV pairing UI etc.) only if it gets traction.

Older "watch it on the couch" items (media controls track):

1. **Media Session / lock-screen + Dynamic Island** — REWRITTEN to an endless
   silent live stream from the box (`GET /api/silent`, ffmpeg anullsrc); no
   scrubber by design (a faked finite track's position can't be synced and
   bounced). Working: lock screen + Control Center + Dynamic Island, correct
   play/pause. KNOWN TRADE-OFF (chosen): the silent stream pauses when the TV
   pauses so the icon is right, which means a *very long* idle pause can let iOS
   drop the Now Playing session. If Donnie would rather keep the notification
   through long pauses at the cost of a less-correct paused icon, flip
   `updateMediaSession` in `web/src/lib/state.svelte.js` back to keeping the
   stream playing. Truly having both needs a native app wrapper.
2. **End-of-stream glitch guard** (`server/index.js reassess`) — YouTube HLS/DVR
   streams can run past EOF with Kodi never stopping (clock ticks past duration,
   no video). Guard stops the player when `position > duration + 3`. WATCH: that
   it backs out cleanly on the next YouTube finish AND never cuts a normal video
   ~3s early (if it does, raise the +3 margin).
3. **Smart rewind** (`server/index.js /api/player/step`) — for streams, pauses →
   seeks → waits for the buffer (`Player.Caching`/`CacheLevel`) → resumes, so
   YouTube rewind comes back cleanly. Confirmed snappier. Local files unaffected.

## Open decisions / risks
- ~~Couch is NOT under version control~~ **CLOSED 4 Aug**: git init done,
  secrets scrubbed first, history clean.
- **Sunshine's virtual `js0` breaks pad reconnect + TV wake** (found 4 Aug).
  `pad-connect-daemon:34` and `tv-waker:39` both test `glob('/dev/input/js*')`,
  so ANY virtual joystick (Sunshine, vpad rigs, the uhid test pad) makes them
  believe the pad is already there. Immediate: `systemctl --user stop
  app-dev.lizardbyte.app.Sunshine.service`. Real fix (needs Donnie): test the
  DualSense's own node instead of any js*. Sunshine is enabled and returns on
  every login.
- **Three legacy bugs found by the shadow work, NOT fixed (Donnie's call —
  behavioral edits to live plumbing).** Pre-declared in the differ so they
  don't read as couchd faults: (a) pure Big Picture PS-holds never write
  `/tmp/game-suspended`, so reconcile takes the pad off Kodi ~10s later and it
  belongs to nobody; (b) games launched FROM Big Picture record appid as the
  literal string `"bigpicture"`, so that game's Kodi tile CLOSES it instead of
  resuming; (c) the guard's pidfile isn't removed on normal exit (couchd's
  owned-resources invariant flags it every tick).
- **Three `steam_app_*` window-class predicates are fragile identity
  assumptions** (steam-input-guard:272, screen.js:271 and :291). They dissolve
  as couchd absorbs those responsibilities (its observation is pid-first);
  only worth fixing sooner if gamescope ever un-parks.
- **No auth** (LAN-only by design). A rota-style login MUST be added before any
  Cloudflare-tunnel exposure (pattern in the ROTA memory:
  rota-app-cloudflare-tunnel, rota-app-accounts).
- **Dynamic Island / lock-screen scrubber** are as good as a web app gets; a real
  Live Activity or a synced progress bar would need a native iOS wrapper.

## Changelog — 2026-08-04 (evening, robustness audit)
Full audit: `docs/audits/console-robustness-2026-08.md`. Headline: **Proton
games never actually froze on suspend** (Proton maps the library to `S:` so
path-matching missed eldenring.exe; only wrappers froze). Fixed with
`~/.local/bin/game-pids` (reaper process-tree identity, shared by watcher /
game-launch / guard / couch server) - verified live, all 18 ER processes
freeze/thaw now. Added: watcher `reconcile()` standing repair loop (orphaned
session, stale flag, lost thaw, joystick drift, frozen-game-visible, ~10s),
guard SIGTERM cleanup, 5s ACL retry.
- [B] Physical-pad end-to-end pass of today's changes (Donnie, from the couch).
- [B] uhid DualSense emulation to synthetically test Steam's hidraw path (project).
- [B] game-pids: exclude transient reaper children that are not games (Steam
  redistributable installers) if a phantom session ever appears.
- [B] Optional: dedicated "rescue" button in couch app (Screen->switcher->Kodi
  already serves as the panic button).

## Changelog — 2026-08-04 (afternoon, state-aware screen switcher)
- **Screen tab's app switcher now speaks the console state machine** (server
  only, no rebuild): picking Kodi mid-game runs `game-launch suspend` (freeze +
  pad to Kodi + guard) instead of a raw X raise; picking a paused game resumes
  it; picking a running game re-focuses it properly. Raw raises could strand
  the box (frozen game on top / Kodi shown while the pad stayed with the game).
- `xinput.py windows` now returns `cls` (wm_class); `screen.js windows()` badges
  the suspended game "· paused" in the list.
- Backing this: `steam-input-guard` (new, ~/.local/bin) enforcement loop after
  every suspend/resume - closes Steam's invisibly-open BP menu (root cause of
  the "black screen + steam menu, controller stolen" bug), re-asserts the right
  window, thaws a game that should be running, and never lets a frozen game sit
  visibly on top. See homelab-console-setup memory for the full story.

## Changelog — 2026-08-04 (media controls + playback polish)
- **Media Session REWRITTEN to a live silent stream.** Journey: generated silent
  WAV in memory → grew it per content (memory blew up on films) → seeking a fake
  finite track to the real position always bounced (iOS reads position from the
  element's own clock). Terminal fix: `GET /api/silent` streams endless silent
  MP3 (ffmpeg anullsrc, `-re`, killed on disconnect); the client plays it as one
  reused, gesture-unlocked element. No duration → iOS treats it LIVE → no
  scrubber, nothing to bounce. Side effect: it now shows on the **Dynamic Island**.
- **Play/pause icon** — iOS reads the icon from the element's paused state, so the
  element mirrors the TV (play/pause). `optimisticPlayPause` now calls
  `updateMediaSession` so an in-app pause flips the lock-screen icon instantly.
- **YouTube auto-1.25x audio-loss FIXED** — applying tempo mid audio-init silenced
  the stream; now settle ~1.3s, apply, re-assert ~2.8s (`applyYouTubeDefault`).
- **Smart rewind + end-of-stream guard** — see Resume items 2 and 3.

## Changelog — 2026-08-03 (evening, UI polish + fixes)
- **Sheet/card animation FIXED.** iOS snaps `transform` on a `position:fixed`
  element nested in scrolled `<main>`. Fix: `lib/portal.js` moves every sheet to
  `<body>` before animating. Entrance JS-driven in `lib/anim.js`; bottom-sheet slide.
- **Exit animations** — `slideDown`/`fadeOut` `out:` transitions on every sheet.
- **Scroll-behind fixed with CSS** — `.scrim{touch-action:none}` +
  `.sheet/.dsheet/.chooser{touch-action:pan-y;overscroll-behavior:contain}`.
  Removed a `position:fixed` body lock that jumped the nav bar + left a grey strip.
- **Safe-area sheet padding** → `max(18px, env(...))` (killed a dead grey band).
- **Discover detail holds until loaded** — fetch + decode art (`img.js
  decodeImages`) before opening; tapped card spins. No piecemeal pop-in.
- **Custom in-app seek scrubber** (Playing.svelte) — `setPointerCapture`,
  `touch-action:none`, optimistic, throttled ~200ms live seeks. (This is the
  in-app bar; the lock screen has no scrubber, see 4 Aug.)
- **TV power toggle on the Remote page** — top row, blue when on, `/api/tv` on/off.
- **Volume row added to Now Playing** (Playing.svelte).
