# Transition speed-ups - static analysis of both stacks (6 Aug 2026)

Where the avoidable latency lives in the console's transition paths
(suspend / resume / launch / quit / switcher), for BOTH stacks, with
file:line receipts, measured costs where the box could give them, and a
risk class per change. Read-only pass: nothing here has been changed.

Risk classes:
- **[SCRIPT]** legacy script or server change - deploy + sweep, no model move.
- **[MODEL]** couchd change - moves the fingerprint, needs a differ note + sweep.
- **[DESIGN]** semantics/ordering change - needs Donnie's ruling.
- **[CONST]** design constant (hold 0.9s etc.) - listed only, never proposed.

SR4 note: nothing below touches the gesture ARITHMETIC (hold threshold,
double-tap window, settle). Two findings change legacy's *dispatch* latency
(when a decided gesture fires, not what is decided); they are flagged.

## Measured baseline (this box, 5700X3D)

From the live phase instrumentation (`/tmp/game-launch.log`, one real resume):

```
16:51:34.059 === resume
  thaw            +44ms
  flag clear      +28ms
  window map      +51ms
  power-menu curl  +9ms
  pad routed      +14ms
  focus asserted +1162ms   <- sleep 1 + focus_game spawn
16:51:35.378 resumed       total 1319ms
```

**The fixed `sleep 1` is ~77% of a resume.** Everything real (thaw, map,
Kodi RPC) totals ~150ms.

Helper spawn costs (timed on the box): `python3 -c pass` 16ms; `python3 -c
"from Xlib import display"` 44ms; `game-pids` 39ms; `xinput.py windows` 56ms;
`curtain status` 43ms; `systemd-run --user true` 30ms; `steam-uimode` 22ms.
So per-spawn overhead is tens of ms - the fixed sleeps and coarse polls
dominate everything.

## Ranked findings (by user-perceived saving)

| # | Finding | Where | Saving (per event) | Risk |
|---|---------|-------|--------------------|------|
| 1 | Resume's fixed `sleep 1` | game-launch:872 | **~850-950ms, every resume, both stacks** | [SCRIPT] |
| 2 | Launch arm: fixed `sleep 4` + 2s polls | game-launch:1080,1085,697 | **~2-5s to game-focused/BP-hidden, every launch** | [SCRIPT] |
| 3 | `ensure_big_picture` 1s confirm poll (and its serialization before the game spawn) | game-launch:191-217,1071-1072 | ~0.5s (poll); 1-5s more if overlapped | [SCRIPT] / overlap is [DESIGN] |
| 4 | Game-swap/quit teardown 1s polls | game-launch:736,777,988,1023 | 1-3s on "different game picked" and quit | [SCRIPT] |
| 5 | Phone-to-desktop fixed 700ms guard beat | server/screen.js:408 | ~500ms | [SCRIPT] |
| 6 | Watcher's 0.2s select tick delays decided gestures | pad-home-watcher:1321 | up to 200ms off hold-fire and deferred tap-resume | [SCRIPT] (SR4-flagged) |
| 7 | `curtain_show`'s redundant `status` pre-probe | game-launch:402-408 | ~45ms every curtained transition; ~300ms in the stale case | [SCRIPT] |
| 8 | Redundant helper round-trips (game-pids x3-4, xinput x2-3 per transition) | several, see below | ~150-300ms, mostly under the curtain | [SCRIPT], low yield |
| 9 | couchd: `route_pad` blocks the pass on sync Kodi HTTP (5s worst case) | couchd.py:3077,4423,3725 | ~0 normally; hygiene against a busy Kodi | [MODEL] |
| 10 | couchd: systemd-run spawn adds ~50-100ms before a helper runs | couchd.py:2334 | <100ms; keep (sandbox reasons are load-bearing) | [MODEL], not recommended |

## The receipts

### 1. Resume: the `sleep 1` (game-launch:872) - THE headline

`resume_game()` maps the frozen window back (`show_frozen_game`,
game-launch:858) then sleeps a flat 1s so xfwm4 finishes the deiconify
before `focus_game` runs - focus_game only ever looks at MAPPED windows
(game-launch:574). The live phase log shows the map itself completes in
~50ms; the sleep is padding for the worst case.

Fix shape: replace the fixed sleep with a bounded converge - retry
`focus_game` at ~100ms cadence up to ~1.5s (it already returns nonzero when
the window is not found, exactly the signal needed; the launch path's
`focus_game_when_mapped` at game-launch:699 is this pattern at 2s cadence).
Or a single `xinput.py wait-mapped <wid>` that selects on X StructureNotify
events - truly event-driven, one spawn. Either way the resume lands at
~350-500ms total instead of ~1300ms.

Both stacks benefit: couchd's resume verb spawns this same script
(`_a_launch` -> `game-launch resume`, couchd.py:3048), so no model change
and no fingerprint move. The differ's effect oracle gives resume a 5.0s
deadline (couchd.py:1720) - a faster resume only confirms sooner.

### 2. Launch arm: `sleep 4` + 2s polls (game-launch:1078-1090)

The steam arm after `steam://rungameid`:
- `while ! game_running; do sleep 2` (line 1080) - the game's processes are
  detected up to 2s after they appear (game_running is a 39ms helper; a
  0.5s poll costs ~8% duty during a ~5s wait, nothing).
- then a flat `sleep 4` (line 1085) before the first `focus_game_when_mapped`.
  This predates the retry loop (added 6 Aug); the retry loop already
  handles a window that is not there yet, so the fixed 4s is now pure
  padding for fast-mapping games.
- `FOCUS_RETRY_S=2` (line 697): the window is focused - and, critically,
  **Big Picture is iconified behind it** (the frame-pacing fix rides the
  same successful attempt, line 639-646) - on average 1s after it maps,
  worst 2s. Each retry costs ~100ms of helper spawns, so a 0.5s cadence is
  affordable; an event-driven MapNotify wait is better still.

Why it is user-visible: until that focus lands, BP sits mapped fullscreen
behind (or over) the game - the "Steam says 60, feels 20" state plus
possible squatting. Every second shaved here is a second less of the worst
visual state the console has. Same pattern in the shadps4 arm
(lines 1129, 1134) and the bigpicture arm's 2s `bp_running` poll (line
1096, each probe a ~80ms python/Xlib spawn).

### 3. `ensure_big_picture` (game-launch:191-218, called at 1071)

Two separable pieces:
- **Poll cadence** [SCRIPT]: it confirms the uimode flip at 1s intervals up
  to 6s (lines 204-206; `steam-uimode` costs 22ms). A 0.25s poll shaves
  ~0.4s average off every desktop-mode launch for free.
- **Serialization** [DESIGN]: the game spawn (`steam://rungameid`, line
  1072) waits for BP confirm. Steam queues a rungameid issued during a
  mode switch, so firing it immediately after `steam://open/bigpicture`
  would overlap the 1-6s confirm with the game's own startup. BUT the
  ordering is deliberate ("into Big Picture first, so the pad talks to a UI
  the guard can repair", line 1068) - in desktop mode a guide tap is
  swallowed into an overlay invariant 1(b) has to clean up after. The
  launch is never *blocked* on failure (line 213 launches anyway), so the
  ordering is best-effort already; overlapping it is a semantics call.
  Needs Donnie.

### 4. Teardown polls (close_games + different-game-picked)

- `close_games`: `sleep 1` after the thaw before collecting pids (line
  736), then up to 8x1s waiting for WM_DELETE to be honoured (line 777),
  then shadPS4's 6x1s (line 793). The 1s poll granularity means a game
  that exits in 200ms still costs a full second per stage.
- "A different game was picked" (steam/shadps4 arms, lines 988 and 1023):
  up to 10x1s waiting for the old launcher's session flag to clear, ON TOP
  of close_games. Worst case the player stares at Kodi for ~15s before the
  new tile even launches.

Fix shape: 0.25s polls with the same deadlines. Same convergence, ~4x less
discretization waste. The save-on-quit grace itself (8s ask-nicely) is a
semantics choice and stays.

### 5. server/screen.js desktop path: fixed 700ms (screen.js:404-409)

Switching the phone to the desktop runs `game-launch suspend`
synchronously, then a flat 700ms `setTimeout` so the backgrounded guard can
claim its pidfile before the zero-length superseding guard fires. Polling
`/tmp/steam-input-guard.pid` at 50ms (bounded at 1s) converges in ~100-200ms
typical. Also note sys.js:88 holds the phone's suspend HTTP response for
the whole synchronous suspend (up to curtain fade); an early response with
the work detached would make the phone UI feel ~1s snappier - cosmetic,
same [SCRIPT] class.

### 6. Watcher dispatch latency: the 0.2s select tick (pad-home-watcher:1321)

The gesture DECISIONS are clock-based but only checked when the 0.2s select
timeout expires, so:
- a hold fires up to 200ms after the 0.9s threshold (couchd wakes ON the
  deadline, EDGE_DEADLINE_FLOOR 0.02, couchd.py:99 + gesture_deadline at
  5018 - so legacy is currently the laggier stack by up to 200ms);
- a deferred tap-resume (paused game, double-tap bound) fires up to 200ms
  after its 0.35s window closes (lines 1454-1459) - up to 550ms between
  finger-up and `game-launch resume` even spawning.

Fix shape: compute the select timeout as
`min(0.2, next_deadline - now)` from the pending hold/long-hold/deferral
deadlines. **No threshold value changes** - the arithmetic (gesture.py) is
untouched, only when the already-decided action dispatches. SR4-adjacent:
flag it in the deploy note and run the gesture sweep after; the differ
should only see legacy's timestamps move closer to couchd's.

### 7. Curtain: the redundant `status` pre-probe (game-launch:400-408)

`curtain_show` runs `timeout 3 curtain status` (~43ms) before every show to
clear a stale curtain, then `curtain show`. But `cmd_show` (tools/curtain:
886-905) already handles a live daemon by atomically swapping the image
(and replaces a wedged one). The pre-probe + clear is therefore redundant
with the tool's own logic: dropping it saves ~45ms on every curtained
transition and ~300ms (clear + respawn) in the stale case, with identical
outcomes. The show itself is a fresh python + Xlib + Pillow daemon spawn,
~240ms synchronous - by design (the caller must know the shuffle is
hidden). On the resume it runs before the thaw/flag work (~70ms of
non-visible work it could overlap) - marginal, skip.

The fade: `timeout 5 curtain fade` (game-launch:427) blocks ~0.5-0.9s
(0.4s dissolve + wait_gone at tools/curtain:919) - but the fade IS the
user-visible reveal, so this is not waste. The only thing serialized behind
it is the suspend arm's guard spawn (game-launch:970); moving the spawn
before the fade is a free ~0.5s earlier enforcement window if wanted.

### 8. Redundant round-trips per transition

One legacy suspend (phone switcher path) forks ~20 processes: game-pids,
pause-snap (which forks game-pids + xinput gamewin + import + identify +
convert + a detached kodi-refresh), curtain status + CLI + daemon,
focus_kodi python, xinput gamewin + xinput iconify, curtain fade CLI, and
steam-input-guard (which forks game-pids once per second for 6s,
steam-input-guard:303). A resume is similar. At ~40-60ms each the
avoidable duplication is ~150-300ms, mostly hidden under the curtain:
- `game-pids` runs 3-4x per transition (game-launch:317 via cont_all /
  _game_window / focus_game; pause-snap:180; watcher:262); it is a full
  /proc scan each time. A `--cache 1s` seam or passing the pid list down
  would cut it to one.
- `hide_frozen_game`/`show_frozen_game` each spawn xinput twice (gamewin
  then iconify/activate, game-launch:458-478; watcher:514-521). A combined
  `xinput.py iconify-game <pids>` verb halves it.
- The watcher opens a second X Display per reconcile pass
  (`curtain_visible` watcher:994, `screen_classes` watcher:1023) - already
  noted in review; off the critical path (10s cadence), tidy-only.
- Resume makes 2-3 sequential Kodi JSON-RPC HTTP round trips
  (GUI.GetProperties at game-launch:862, optional Input.Back, then
  Settings.SetSettingValue) - batchable as one JSON-RPC array, ~10-20ms,
  note only.

### 9-10. couchd side (all [MODEL] - fingerprint moves)

- `_a_route_pad` (couchd.py:3077) calls the observer's sync `_http`
  (couchd.py:3725, timeout=5) directly in the event loop, so a busy Kodi
  can stall a whole pass and everything behind it (the raise_kodi that
  follows in the same handoff). Normally ~10-30ms; the observers' reads
  already go through `asyncio.to_thread` (couchd.py:3771). Hygiene fix,
  no perceived saving today.
- Spawn-per-verb via systemd-run (couchd.py:2334) costs ~30ms to issue plus
  ~50-100ms unit start before the helper runs. The sandbox-escape rationale
  (couchd.py:2311-2327) is load-bearing; the only in-process candidates
  (signals, flag writes, Kodi RPC, raise_kodi) are ALREADY in-process.
  Recommend leaving it.
- `ICONIFY_SH` (couchd.py:2165-2172) polls 0.1s up to 4s for the snapshot
  jpg before unmapping - detached, off the critical path; it only delays
  the pointer-grab release (same contract as the watcher's SNAP_WAIT_S 4.0,
  watcher:330). Note only.
- Gesture edge handling is already tight: EDGE_DEBOUNCE 0.05 (couchd.py:94),
  deadline-wake (couchd.py:5018-5045), measured edge-to-decision p50 71ms
  on the current model. Nothing to shave without touching R5/R6.
- The Kodi 10s observer's targeted-read gap is ALREADY fixed:
  `request_read` + KODI_EFFECT_READ_FLOOR 0.5 (couchd.py:3738-3753). No
  action.

### Already-instrumented / evidence hooks

The resume phase logger (game-launch:802-813) exists precisely to answer
finding 1 and has - its own comment says "delete once the answer is known".
The answer is known: the sleep. Keep the logger through the fix's sweep,
then delete per its contract.

## [CONST] - design constants observed on these paths (list only, per SR4)

| Constant | Value | Where | Cost it imposes |
|----------|-------|-------|-----------------|
| HOLD_SECONDS | 0.9s | gesture.py:27 | floor on every hold gesture |
| DOUBLE_TAP_S | 0.35s | gesture.py:55 | every tap-resume of a paused game waits it out (Donnie's 5 Aug ruling) - 350ms before every resume dispatch |
| SETTLE_S | 1.2s | gesture.py:74 | presses in the 1.2s after a transition are swallowed whole (watcher:1332, couchd mirrors) |
| HANDOFF_TIMEOUT | 4.0s | gesture.py:28 | only on a lost release |
| Guard cadence / window | 1s x 6s | steam-input-guard:662,499 | repairs land up to 1s late; overlay close armed at +1.2s (line 534) |
| vpad beats | 1.5s + 1.0s | guard:595,608; watcher:803,806; couchd GUIDE_PRESS_SH:2150 | Steam-measured enumeration/act delays, load-bearing |
| THAW_RECHECK_S / THAW_CONFIRM_S / FLAG_DRIFT_PERSIST_S | 0.6 / 1.0 / 2.0 | watcher:407; guard:284; couchd:447 | the resume-ordering protocol's debounces (deployed 6 Aug) - do not touch |
| Curtain watchdog / fade | 8s / 0.4s | tools/curtain:86-88 | the fade is the reveal, not waste |

## Recommended first batch (low risk, high yield, all [SCRIPT])

Everything below is legacy-script/server-only: no fingerprint move, no
gesture arithmetic, one deploy + the 12-point sweep after.

1. **Resume `sleep 1` -> bounded 100ms focus-converge** (finding 1).
   ~900ms off every resume, on both stacks. Keep the phase logger through
   the sweep to prove it.
2. **Launch arm: drop the `sleep 4`, tighten `game_running` poll to 0.5s,
   FOCUS_RETRY_S 2 -> 0.5** (finding 2). 2-5s less of the BP-behind-game
   worst state per launch.
3. **`ensure_big_picture` confirm poll 1s -> 0.25s** (finding 3, poll half
   only - the overlap half goes to Donnie as a ruling).
4. **screen.js 700ms -> pidfile poll** (finding 5). Deploy = restart couch.
5. **Drop `curtain_show`'s status pre-probe** (finding 7). Trivial, and
   test_curtain already covers the replace-image path.
6. **Teardown polls 1s -> 0.25s** (finding 4) - same deadlines, finer grain.

Second batch, gated: the watcher's dynamic select timeout (finding 6,
SR4-flag + gesture sweep + one differ evening), and the round-trip
consolidation (finding 8) if the first batch's numbers say the residue
still matters.

Expected feel after batch 1: resume ~1.3s -> ~0.45s, suspend unchanged
(already curtained), launches converge on the game window 2-5s sooner,
phone desktop switch ~0.5s snappier.
