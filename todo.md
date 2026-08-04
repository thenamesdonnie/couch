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

## ▶ Resume here
All shipped and live. Latest **web** build is **2026-08-04 00:45**; the server
has later server-only changes applied by restart (smart rewind, end-of-stream
guard, state-aware Screen-tab switcher). The whole console robustness pass is
live too: `docs/audits/console-robustness-2026-08.md` is the map (failure
modes, recovery layers, SSH cheat sheet); test rigs preserved in `tools/`
(psfuzz.py, chaos.py; they need the session's ps-button/vpad in ~/.local/bin).

**Evdev recorder is ARMED (4 Aug):** `pad-record.service` (user unit,
`tools/pad-record`) passively records every DualSense session to
`recordings/pad-*.jsonl.gz` — raw events + game-session/suspended markers —
for the couchd replay suite (charter discipline 2). Auto-starts on pad
connect, needs nothing from Donnie; verified with a synthetic ps-button tap.
Disable: `systemctl --user disable --now pad-record`. When git init happens,
`recordings/` goes in `.gitignore`.

**NEXT: Donnie's physical-pad pass from the couch** (the one thing untestable
remotely - Steam hears the real DualSense over hidraw, which no rig here can
fake). Try, in Elden Ring: hold PS (game should NOW truly freeze - watch CPU
drop, this never worked before today), tap on home to resume, tap PS in-game
(Steam menu opens, tap again closes), then try to break it: spam presses,
ambiguous ~0.8s presses, presses during transitions. Also: phone Screen tab ->
switcher -> Kodi mid-game (panic button), and with the TV OFF start a video /
launch a game from the phone (TV should wake in ~6-8s). If anything sticks
longer than ~10s, note the time and check /tmp/pad-home.log,
/tmp/game-launch.log, /tmp/steam-input-guard.log.

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
- **Couch is NOT under version control** (no `.git`). One bad edit from
  unrecoverable. Worth a `git init` + first commit — ask Donnie before doing it.
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
