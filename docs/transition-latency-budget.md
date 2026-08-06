# Console transition latency budget — MEASURED (6 Aug 2026)

Every number below is derived from real timestamps: `shadow/couchd-20260805/6.jsonl`
(epoch `t`, authoritative), `shadow/legacy-intents-*.jsonl` (+ evening1 archive),
`/tmp/game-launch.log` + `shadow/archive/game-launch.log` (ms-resolution phase
instrumentation), `/tmp/pause-snap.log`, and `docs/acceptance-20260806.md`.
Correlation is on epochs; couchd.log wall-clock was NOT used (UTC/BST wobble).
No optimization proposals here — measured truth only.

## How to read the numbers (two caveats that apply everywhere)

1. **Observation quantization.** couchd's "confirmed" effect latencies include
   waiting for the *next observation pass*. The pass cadence is adaptive:
   measured from daemon rows, **0.31–0.55 s/pass during gesture activity, ~2 s
   idle** (19 runs, 0.31–27 s/pass span; the 27 is an idle overnight run).
   So a "freeze confirmed 0.79s" does not mean SIGSTOP took 0.79s — the kill()
   is in-process and effectively instant; ~all of it is confirm-poll delay.
   The same applies to `foreground` transitions: "Kodi on top at +0.33" means
   *observed* on top at the next pass, real raise was earlier.
2. **Sample eras.** 5 Aug rows are shadow-mode (couchd predicted, legacy acted;
   no effect rows). 6 Aug rows post-flip are acting (effects with verdicts).
   Where it matters, stats are split. Known-bug episodes (BP-tile hang,
   cross-stack guard SIGTERM — see couch-legacy-bugs memory) produce the worst
   outliers and are flagged, not averaged away.

Design constants in play (from `couchd/gestureconf.py` + live
`script.couch.switcher/settings.xml`, verified live 6 Aug):
`hold_seconds = 0.9`, `double_tap_seconds = 0.35`, `long_hold_seconds = 3.0`
(unbound). Kernel edge → gesture decision: **p50 0.05s** (n=443 latency rows).

---

## 1. SUSPEND (PS hold): game → Kodi

Episodes reconstructed from gesture-region transitions + intents + effects
(n=20 total: 9 acting with effects, 11 shadow).

| Leg | n | p50 | worst | best | Nature |
|---|---|---|---|---|---|
| press → hold-fired | 20 | 0.85s | 1.01s | 0.70s | **design** (0.9s threshold; measured from observed press edge, ±poll) |
| hold-fired → freeze intent | 22 | ~0.00s | — | — | fires same pass |
| freeze intent → freeze CONFIRMED | 9 | 0.79s | 1.06s | 0.25s | SIGSTOP is in-process/instant; ~all confirm-poll |
| hold-fired → suspended-flag confirmed | 9 | 0.20s | 0.30s | 0.01s | direct file write (min 0.013s = true cost) |
| snapshot (pause-snap capture) | 1 | 0.18s | — | — | see §6; runs async, not on the visible path |
| hold-fired → release | 18 | 0.60–0.76s | 3.62s | 0.38s | **user-controlled** (how long Donnie keeps holding past the fire) |
| release → route_pad/show/iconify/guard intents | 9 | ~0.00s | — | — | decided at release edge |
| route_pad kodi (jsonrpc) confirmed | 9 | 0.32s | 0.43s | 0.05s | true RPC round-trip ≤50ms (min sample; cf. §6) |
| show kodi (raise) confirmed | 9 | 0.33s | 16.33s* | 0.15s | X raise in-process; poll-quantized. *outlier = the 03:16 BP/guard-loop bug episode |
| release → Kodi observed on top | 19 | **0.33s** | 5.73s | ~0.0s | the actual user-visible switch |
| **TOTAL press → Kodi on top** | 19 | **1.77–1.80s** | 8.92s | 1.20s | |

**Budget split at p50: 0.9s design (hold threshold) + ~0.7s user (release
timing) + ~0.35s implementation (the whole shuffle).** The implementation leg
is already small; the visible frame during it is the frozen game (a de-facto
curtain), so the hold-suspend does not run tools/curtain and doesn't need the
0.25s it costs. The three 4.3–5.7s release→Kodi outliers are the acceptance
night's known bug episodes, not the normal path.

Note: if the release edge is never observed, a **4.0s timeout** completes the
handoff (measured hold-fired→timed-out: n=12, p50 4.01s — design constant,
`hold-release-timeout`). Those episodes feel like a 4s hang; 12 occurrences in
two days, all in rig/edge conditions.

## 2. TAP-RESUME: Kodi → paused game

Two decision paths exist in the data:

| press → tap-decided | n | samples |
|---|---|---|
| immediate (`ps-tap-with-paused-game`) | 3 | 0.09 / 0.27 / 0.37s |
| via disambiguation window (`paused-tap-window-expired`) | 4 | 0.47 / 0.49 / 0.64 / 0.80s |

The 0.35s double-tap window is a **design constant** (it is what makes
double-tap-switcher possible); the window-expired path pays release-time +
0.35s + poll. Evidence is too thin (n=7 total) to say when the immediate path
applies — worth one deliberate check before optimizing the window.

From decision onward (couchd `launch mode=resume` → legacy `game-launch resume`,
correlated on epochs; plus game-launch's own ms phase instrumentation, n=6
phased resumes 6 Aug 02:51–16:51):

| Leg | n | p50 | range | Nature |
|---|---|---|---|---|
| launch intent → game-launch invoked (systemd-run spawn) | 5 | 0.04s | 0.03–0.25s | implementation (spawn overhead — cheap) |
| flag-cleared | 6 | +0.05s | 0.04–0.08 | file ops |
| thawed (SIGCONT tree) | 6 | +0.08s | 0.04–0.10 | cumulative; near-instant |
| window-mapped (re-map iconified frozen window) | 6 | +0.51s | 0.12–0.54 | X map + xfwm4; the 0.12 is today's shadps4 (no BP involved) |
| menu-checked (Kodi currentwindow curl) | 6 | +0.53s | +9–29ms leg | Kodi RPC round-trip ~10–30ms |
| pad-routed (jsonrpc joystick off) | 6 | +0.55s | +14–22ms leg | RPC round-trip ~20ms |
| **focus-asserted** | 6 | **+1.79s** | +1.31–1.82 | **`sleep 1` (fixed, in game-launch) + focus/BP-iconify X work ~0.16–0.25s** |

The instrumentation block in game-launch says it best ("Resuming feels
sluggish (~2s) and nobody has measured WHERE that goes") — now measured: **the
single dominant leg is the hardcoded `sleep 1` before focus assertion
(+1.0s of the +1.24s focus leg), pure implementation cost.** The game's frame
is back on screen at window-mapped (~+0.5s); what the sleep delays is the
focus/raise guarantee and "resumed". Shadow foreground confirms the window
side: decided→game-observed-on-top best samples 0.18s / 0.95s (poll-quantized);
the 4.3–13s samples are BP-interference bug episodes (R-b / BP-left-mapped).
Curtain, when a fresh frame exists, is shown synchronously *before* the thaw:
adds ~0.25s serial at the front (claimed; no live per-show timing yet — see §6).

**User-perceived p50: press → game frame visible ≈ 1.0–1.3s** (decide 0.1–0.8
+ spawn 0.04 + map 0.5), **press → input/focus certain ≈ 2.3–2.6s** (the
sleep). n=6 phased; more samples land automatically every resume.

## 3. SWITCHER (double-tap)

n=52 double-taps (sweeps + real), 48 with `show_switcher`.

| Leg | n | p50 | worst | best | Nature |
|---|---|---|---|---|---|
| first press → second press | 23 | 0.20s | 0.40s | 0.11s | user |
| second press → double-tap decided | 23 | 0.12s | 0.26s | 0.07s | decided ON the second press — the 0.35s window is NOT waited out here |
| decided → show_switcher intent | 48 | ~0.00s | | | |
| show_switcher intent → dialog CONFIRMED | 45 | **1.01s** | 1.66s | 0.24s | Kodi `Addons.ExecuteAddon` + addon python startup + dialog build + **280ms slide animation (design)** + confirm-poll |
| **second press → dialog visible** | 22 | **1.13s** | 3.26s | 0.93s | |

Matches the acceptance sweep (12/12, confirms 0.8–1.7s) and the acceptance doc
(0.81s). Of the ~1.0s: ~0.28s is the deliberate sheet animation (design,
`ui.animated_dialog`), up to ~0.3–0.5s is confirm-poll inflation, leaving
roughly 0.3–0.5s of real Kodi ExecuteAddon + python-dialog startup
(implementation). With a live game, freeze fires *before* the switcher
(confirmed 0.7s before, acceptance doc) so the game is already held.

**Pick → resume leg:** no per-pick timing exists in the shadow streams (the
pick lands inside the addon; the resume that follows is §2's path, and R-b
says it currently routes via Big Picture — a known bug, not a latency
constant). EVIDENCE TOO THIN — instrument the pick if this leg matters.

## 4. COLD LAUNCH (Games row tile → playing)

Sources: legacy `invoked`/`launch` rows, game-launch.log, couchd session +
foreground transitions. Steam-game episodes (367520 = Hollow Knight unless
noted):

| Leg | n | p50 | range | Nature |
|---|---|---|---|---|
| tile click → game-launch invoked | 0 | — | — | **UNMEASURED** (no click timestamp exists; Kodi plugin exec, believed small) |
| invoked → launch verb + session flag | 15 | 0.01s | 0.01–0.26s | implementation (trivial) |
| ensure-BP when Steam is in desktop uimode | 1 | 1.15s | — | "big picture confirmed after 1s" (1s poll cadence); only on the uimode-7 path |
| steam command → game pids up ("running") | 6 | ~3.2s | 2.0–5.9s | **Steam-controlled** (BP launch itself: 2–3s to running, n=10) |
| session-start → pids active (couchd view) | 10 | 1.2s | 0.8–2.9s | same thing observed from couchd |
| pids up → game window mapped | 7 | **~14.6s** | 6.2–31.3s | **game-controlled** (HK binary + Proton load; this IS the 14–26s Donnie feels) |
| window mapped → focused + BP hidden | — | ≤2s | — | focus retry cadence 2s (design of the retry loop), iconify ~0.2s |
| **session-start → game observed on top** | 7 | **15.6s** | 9.1–32.7s | |

**Plumbing accounts for ~1.5s of a ~16s cold launch (invoked+flags 0.3s,
ensure-BP 1.15s when needed, focus quantization ≤2s tail). Everything else is
Steam (~3s) and the game binary (~6–31s).** shadPS4 contrast: process up in
0.08s, window later (emulator-controlled). FOCUS_WAIT_MAX_S=40 cap never hit
in these samples.

## 5. QUIT (hold → quit / phone quit): game → Kodi

n=10 full quit episodes with per-step legacy rows:

| Leg | p50 | range | Nature |
|---|---|---|---|
| invoked → thaw (frozen games first) | 0.2s | 0.1–0.3 | implementation |
| thaw → close request sent (`quit:all`) | 1.2s | 1.2–1.7 | implementation (window enumeration) |
| close request → flags cleared / route_pad+show kodi | ~3s | 1.0–3.7 | **design: the polite save-window** (games that ignore it get force-killed; worst observed 10s on 5 Aug 16:37) |
| **invoked → show kodi / pad to Kodi** | **4.3s** | 2.3–5.4 | |
| Kodi observed on top after show | +0.6–5.8s | | poll + bug-episode outliers |

The dominant leg is the deliberate chance for the game to save on quit —
design (bounded), with the actual duration **game-controlled**. shadPS4 quit
today: 2.3s end-to-end.

## 6. The named suspects, quantified

| Suspect | Measured | Verdict |
|---|---|---|
| pause-snap capture | snapshot intent 1786032593.673 → jpg `...93857.jpg` = **184ms** (n=1; effect-confirm 0.602s once, oracle broken for 10 "unverified" — known deploy item) | cheap; runs before the raise but off the critical visible path |
| curtain show | claimed ~0.24–0.25s synchronous (tool docstring + todo); wired into game-launch suspend/resume 6 Aug evening; live evidence = **one** fade line (17:48:58), zero live show-duration samples | **SERIALIZES**: suspend arm runs snap (0.18s) → curtain_show (~0.25s) *before* pad→Kodi/raise; resume shows it *before* the thaw. Adds ~0.4s serial for the shuffle it hides. EVIDENCE THIN — its 8s-watchdog worst case is also unverified live (todo says so) |
| route_pad via kodi-jsonrpc | game-launch phase legs: **14–22ms**; couchd effect min 0.05s, p50 0.245s (poll-inflated) | true cost ~20ms; a non-problem |
| systemd-run spawn of acted verbs | couchd launch intent → game-launch `invoked`: **0.03–0.25s, p50 0.04s** (n=5; the 0.25 was the busy 5 Aug night) | ~40ms typical; a non-problem |
| iconify / show X round-trips | iconify confirmed 0.203/0.229s (n=2 confirmable; 8 unverified = broken oracle); show-kodi p50 0.204s, min 0.15 | real X cost ~0.2s incl. poll; fine |
| guard spawn | spawn_guard confirmed p50 0.31s (n=16); guard needs ~2s to first enforcement (differ-docstring residual) | spawn cheap; the 2s is protection lag, not user-visible transition lag |
| 1.2s OVERLAY_ARM_DELAY | arming gate for the desktop-overlay check *inside* the guard window (couchd.py:1265,1315) | delays nothing user-visible; only the earliest possible overlay repair |
| focus retry cadence (2s) | launch-path only (resume maps directly); window maps arrive 6–31s after pids | adds ≤2s quantization to a game-dominated wait; negligible |
| double-tap window (0.35s) | switcher: decided on the second press, window NOT waited out. Tap-resume: paid only on the window-expired path (+~0.4s) | design constant; only the tap-resume path ever feels it |

## Top 5 dominant legs by user-perceived cost

1. **Cold launch: pids-up → window mapped, p50 ~14.6s (range 6–31s).**
   Game-controlled (game binary + Proton load; Steam adds ~3s before it).
   Our plumbing is ~1.5s of a ~16s total.
2. **Quit: the polite close/save window, ~3s of a ~4.3s p50 total (worst 10s).**
   Design (save-on-quit chance); duration game-controlled.
3. **Tap-resume: the fixed `sleep 1` + focus assert, +1.24s of the 1.8s
   resume, on every single resume.** Pure implementation cost, and the game
   frame is already visible at +0.5s — this leg delays only the focus/raise
   guarantee. The instrumentation was built precisely to find this; it did.
4. **Switcher: intent → dialog visible, p50 1.01s** = ~0.28s deliberate
   animation (design) + ~0.3–0.5s Kodi ExecuteAddon/python startup
   (implementation) + confirm-poll inflation.
5. **Suspend: 0.9s hold threshold + ~0.7s user release timing, against only
   ~0.35s implementation.** The felt latency of suspend is almost entirely
   design + user; the machine's share is already about a third of a second.

Cross-cutting: couchd's *observed* confirms and foreground milestones carry
0.3–2s of poll quantization — any future optimization must re-measure with the
game-launch-style ms phase instrumentation, not shadow confirms, or it will
chase the poll.

## Evidence too thin to size (honest list)

- Tile click → game-launch invoked (no click timestamp anywhere).
- Switcher pick → resume start (nothing logs the pick instant).
- Curtain show duration live (claimed 0.24s from bench; 0 live samples).
- Which taps take the immediate vs window-expired decision path (n=3 vs 4).
- snapshot/iconify true latencies beyond n=1–2 (their effect oracles never
  confirm live — known deploy item, 5/5 unverified on acceptance night).
- Hold-suspend on a *Big Picture* session (n=5 flag rows, no full chains).
