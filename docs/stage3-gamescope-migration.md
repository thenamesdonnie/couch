# Stage 3 — what adopting gamescope per-game does to the console stack

Written 6 Aug 2026 (evening), for the next daytime session. Companion to
`docs/gamescope-spike-20260806.md` (the build) and `tools/gamescope-wrap`
(the launch wrapper, tested, nothing wired to it yet). Charter rule in
force throughout: gamescope IS the adoption — never fork it, wrap it.

Everything in §1 was verified TODAY on this box (source reading against
the 3.16.25 tree in `~/src/gamescope`, plus two brief niced 320x240
nested runs). Everything marked EXPERIMENT was not, and needs a live
session with Donnie.

## 1. Verified facts the rest of this doc stands on

**The window.** Nested gamescope presents exactly ONE window to the outer
X server:

    WM_CLASS(STRING) = "gamescope", "gamescope"
    WM_NAME / _NET_WM_NAME  = the INNER game's title (glxgears run showed
                              "glxgears" — gamescope mirrors the focused
                              embedded window's title outward)
    _NET_WM_PID             = gamescope's own pid
    _NET_WM_WINDOW_TYPE     = NORMAL

The game's real window lives inside gamescope's embedded Xwayland (`:1`)
and is INVISIBLE to the outer X server. No `steam_app_*` class ever
appears in the outer window list while a wrapped game runs. The title
mirroring is a small gift: name-based matching still sees the game's
name; class- and appid-from-class matching see nothing.

**The process tree.**

    gamescope ─── gamescopereaper ─── sh (gswrap shim) ─── game...

gamescopereaper is a subreaper, so the game's whole session (wine,
pv-adverb, everything) stays under it. Nothing about the game's own
subtree changes.

**Exit codes.** gamescope NEVER forwards the game's exit status — at any
version, not just the segfaulting one. Source: steamcompmgr.cpp:8311
discards `WaitForChild()`'s status and calls `ShutdownGamescope()`;
gamescopereaper returns 0/1 on its own account. Empirical: a child
exiting 7 produced gamescope rc 0. Separately, 3.16.25 reproducibly
SEGFAULTS in teardown (rc 139) when a client window was mapped (the
glxgears runs; also on SIGTERM), and exits 0 when none was (the bare
`sh -c` probes). Consequence: **pinning 3.16.19 buys nothing** — it would
remove the 139 but still report 0 regardless of how the game died.
`gamescope-wrap` solves this with a shim that writes the game's real
status to a file; the wrapper's exit code is always the game's. Session
logic must only ever see the wrapper's code, never gamescope's.

**The Steam overlay is stripped by design.** For any backend using a
Vulkan swapchain (the nested SDL backend does), gamescope removes
`gameoverlayrenderer.so` from the children's LD_PRELOAD
(steamcompmgr.cpp:8248–8266). So inside nested gamescope a Steam title
runs WITHOUT the overlay unless we fight for it (ScopeBuddy's reason to
exist). This is the single biggest unknown for Steam titles — see §6.

**Frame pacing caveat.** The spike measured a steady 30fps on the
UNFOCUSED nested window. A focused fullscreen run has not been measured.
Gate any real-game trial on seeing the full rate focused (EXPERIMENT).

## 2. Window-model impact — every site that assumes steam_app_* or game-window visibility

The pattern across the stack is two-legged: pid-first matching (which
SURVIVES, because gamescope's window carries gamescope's pid and
gamescope sits inside the session's pid set for Steam launches — §3) and
`steam_app_*` class matching (which goes DARK). The stack already
contains a working precedent for a class-less game: **shadPS4**. Every
gamescope-wrapped game degrades to the shadPS4-shaped observation path —
which exists and works — but several sites get actively WRONG rather than
merely degraded, because a mapped fullscreen `gamescope`-class window is
not "no game window", it is "an unknown window on top", the exact shape
both stacks repair against (the curtain learned this the hard way).

The clean fix is ONE new fact, applied everywhere: **class `gamescope`
is a game window.** Ideally one shared predicate per stack, not eleven
edits of `.startswith('steam_app')`.

### couchd

| Site | Today | Under gamescope | Needs |
|---|---|---|---|
| `couchd/x11.py:320` (scanner) | `steam_app*` → `game_windows`; top window class recorded | `game_windows` = (), top_class = `gamescope` | classify `gamescope` into `game_windows`; this is the root fix most rules inherit |
| `couchd/couchd.py:745` `g_fg_game` | fg region's game leg = top_class `steam_app*` | fg settles on **'other'** for the whole session — every `('foreground', ...)` rule misreads the screen, and fg='other' is what guards treat as drift | accept `gamescope` as game |
| `couchd.py:1102` (guard branch, top not-a-game) | repairs when a non-game covers things | fires against a healthy game | same predicate |
| `couchd.py:1164–1165` ("top AND focused = the player is playing" disambiguation) | stops the frozen-game repair from raising Kodi over a live game | escape hatch never fires → Kodi could be raised over a game being PLAYED | same predicate, for both top and focused class |
| `couchd.py:1183` (BP/game genuinely on screen) | — | game leg dead | same predicate |
| `couchd.py:1787`, `couchd.py:1906` (`guard:frozen-game-visible`) | frozen `steam_app*` on top → raise Kodi | frozen gamescope window on top is NOT repaired (invariant 3 hole) | same predicate |
| `couchd.py:2444` `_eff_show` oracle | — | game leg dead | same predicate |
| `couchd.py:2547–2550` `_eff_iconify` oracle | two legs: top not steam_app AND appid not in `game_windows` = truly unmapped | **false positive**: a still-mapped, covered gamescope window passes both legs, confirming an iconify that failed — the exact bug this oracle was built to catch | game_windows must carry `gamescope`; the appid leg can additionally match the session appid file instead of class |

### legacy stack (`legacy-mirror/`, live copies in `~/.local/bin`)

| Site | Today | Under gamescope | Needs |
|---|---|---|---|
| `pad-home-watcher:1057` `top_is_frozen_game` (invariant 3) | frozen steam_app visible → raise Kodi | misses the frozen gamescope window | add class (same place the curtain whitelist went) |
| `pad-home-watcher:1171` (playing disambiguation) | clears a stale suspended read when top+focus are the game | never fires → possible Kodi-over-live-game | add class |
| `steam-input-guard:600` (invariant 3 again) | same repair | same hole | add class |
| `game-launch:493` (focus_game window match) | pid-first, class second | **pid leg survives** (gamescope pid ∈ game-pids set on Steam launches) | verify only; add class for belt |
| game-launch BP-hide / steamwebhelper iconify | — | untouched (Big Picture's window is not inside gamescope) | nothing |

### couch app + Kodi addon

| Site | Today | Under gamescope | Needs |
|---|---|---|---|
| `server/xinput.py:163` (window walk) | pid ∈ game-pids OR steam_app | pid leg survives; row's `cls` becomes `gamescope` | nothing to work, add class for belt |
| `server/screen.js:356` (mark paused rows) | steam_app rows get the frame/thumb | misses; drops to the existing shadPS4 fallback (`pausedWindowId` by pid) — works, but always the fallback | add `gamescope` to the fast path |
| `server/screen.js:434` (activateWindow routing) | paused OR steam_app → gameLaunch resume/focus | a RUNNING wrapped game's row falls through to a plain raise — loses the proper focus path (squatter iconify etc.) | add class |
| `server/screen.js` capture (root `import`) | root grab during game sessions | gamescope's window is an ordinary redirected X window; root grab sees it | verify once (the recipe's "not black" gate) |
| `~/.local/bin/pause-snap` | resolves the game window via xinput's pid-first matcher; `import -window <id>` reads the redirected pixmap of a covered, frozen window | same mechanism, one window further out: captures the gamescope window | verify frozen-capture not black (EXPERIMENT); mechanism is identical to today's |
| `script.couch.switcher/pausedframe.py:83` (appid from class) | steam_app_<appid> | class leg dead; thumb-url and `/tmp/game-suspended` fallbacks already cover it (shadPS4 path) | verify only |
| switcher thumbnails generally | keyed by session appid from game-launch, not by window class | unchanged | nothing |

## 3. Session-model impact

**game-pids still sees everything — for Steam launches.** game-pids roots
on the `reaper SteamLaunch` CMDLINE and takes all descendants. With the
launch option `gamescope-wrap -- %command%`, the wrapper, gamescope,
gamescopereaper, the shim and the game are ALL descendants of Steam's
reaper, so the pid set now contains gamescope itself. Freeze/thaw
(SIGSTOP/SIGCONT the set) therefore freezes the WHOLE tree including
gamescope: its window stops presenting, xfwm4's compositor keeps the last
frame on screen exactly as it does for today's frozen game windows, and
nothing inside gamescope can react to the frozen child because gamescope
is frozen too — which is the safe shape (no "child unresponsive" logic
can run). On SIGCONT everything resumes together.

**The shadPS4 asymmetry (needs a ruling).** game-pids roots shadPS4 on
its AppImage NAMES. If game-launch wraps it (`gamescope-wrap --
Shadps4...`), gamescope is the game's ANCESTOR, not descendant — so the
pid set contains the game but NOT gamescope. Freeze then stops the game
while gamescope stays live, compositing the last-rendered surface. Both
shapes end with a stale frame on screen; they differ in whether
gamescope's event loop stays alive while frozen. Options: (a) accept the
asymmetry (client-only freeze is arguably gentler — gamescope keeps
servicing X/Wayland), (b) add `gamescope-wrap`'s cmdline as a game-pids
root so both launches freeze whole-tree. Decide before the shadPS4
trial; either way it is one honest EXPERIMENT with Donnie present:
freeze, wait minutes, thaw, confirm clean presentation both shapes.

**gamescope's reaction to a frozen child** (whole-tree case: none, it is
frozen too; client-only case): from source, gamescope has no
client-liveness watchdog on the Xwayland surface — a SIGSTOPped client
just stops committing buffers, and the last commit stays on screen. The
`cv_shutdown_on_primary_child_death` path fires on EXIT, not on stop.
Risk rated low, but a long-freeze (hours) resume has never been run:
EXPERIMENT.

**Session end.** The stack detects end-of-session by the pid set
emptying. When the game exits, gamescope notices within ~1s ("Primary
child shut down!"), tears down (possibly via the 139 segfault), the
reaper kills stragglers, and the whole subtree vanishes — same observable
as today, slightly delayed. The teardown segfault leaves core dumps
(observed today, `core dumped`); if systemd-coredump retention ever
matters, cap it — cosmetic.

**Exit codes.** Anything that inspects how the game ended must read
`gamescope-wrap`'s exit status (the game's real one, laundered per §1) —
never gamescope's. game-launch currently treats "pids gone" as the
signal and largely ignores exit codes; nothing regresses, but the
wrapper's log line (`game exited N; gamescope exited M (laundered)`) is
the truth to consult when triaging "did the game crash".

## 4. Rollout shape

**Per-game opt-in, nothing global.**

- Steam title: launch option `~/couch/tools/gamescope-wrap -- %command%`.
  Rollback: delete the launch option, or `GSWRAP_DISABLE=1` in the env
  to turn the wrapper into a pass-through without touching Steam at all.
- shadPS4: game-launch's own command line grows the wrapper prefix.
  Rollback: remove the prefix. (Wiring game-launch is deploy-gated work,
  NOT part of this repo-only session.)
- The wrapper is always-safe by construction: no gamescope build, a
  broken build, or a pre-game gamescope death all end in the game
  exec'ing bare with a loud log line. Proven by `tools/gamescope-wrap-rig`
  and `tools/test_gamescope_wrap.py`.

**Guinea pig: shadPS4 Bloodborne.** Reasoning:

1. The observation model barely moves: the stack ALREADY runs shadPS4
   with no `steam_app_*` window — every class-matching site is already on
   its fallback leg for this title. Gamescope adds one new fact (the
   outer window's class) instead of ten regressions.
2. No Steam Input, no Steam overlay, no LD_PRELOAD fight — the §1
   overlay-stripping unknown is simply not in play.
3. The launch command is OURS (game-launch), so opt-in and rollback are
   one line we control, with no Steam config edits.
4. It is the title with the most to gain from the endgame (upscale now;
   VRR/HDR/4K120 when the DP→HDMI 2.1 adapter lands), so the trial buys
   real information.
   Against it: it is Donnie's most-played game — which the rules already
   answer: first trial with Donnie present, rollback is one line.

Hollow Knight (the old recipe's pick) becomes the SECOND trial — the
first Steam-path title, after the §2 class fixes land, chosen because it
is light, offline, and has a chaos-test baseline. It is the right place
to answer the overlay/Steam Input question, not the first step.

**What stays identical:** pad routing and the vpad guard, tv-waker,
launch/quit flows, BP-hide, Kodi, the curtain, pause-snap's mechanism,
the switcher's appid plumbing, game-pids' algorithm.

**Order of work (daytime):**
1. §2 class fixes (one predicate per stack) + tests; couchd's in shadow
   they diff clean like any model change (differ note + restart).
2. Pre-flight gates: focused-fullscreen frame rate, `import -window
   root` not black under a nested gamescope, frozen-window capture.
3. shadPS4 Bloodborne trial with Donnie (launch, suspend, switcher,
   resume, quit — the 5-minute checklist).
4. Steam-path trial (Hollow Knight) only after the overlay question has
   an answer.

## 5. The DRM-mode endgame delta (later work, kept short)

Embedded (`--backend drm`) is where VRR/HDR/4K120 actually live, and it
changes the shape of the world, not just a window class: gamescope owns a
VT and becomes DRM master via logind/libseat, so the game is no longer a
window in Kodi's X session AT ALL — Kodi's X server and gamescope's seat
session alternate via VT switch. couchd's transition responsibility then
includes: orchestrating the VT switch (and its failure modes — a dead
compositor on the active VT is a black TV), knowing "what is on screen"
without a shared X server to scan (gamescopectl / gamescope's control
socket become the observer), and input routing across two seats' devices.
pause-snap and the curtain dissolve (gamescope can screenshot and fade
itself); the §2 window-model fixes are all X-session-scoped and simply
stop mattering during embedded sessions. This is stage-4-shaped; the
nested adoption is deliberately the smaller first bite.

## 6. Open questions

Needing Donnie (rulings / presence):
1. Guinea-pig confirmation: shadPS4 Bloodborne first, Hollow Knight
   second (§4) — and the trial itself needs him on the couch.
2. Freeze-shape ruling: whole-tree vs client-only for shadPS4 (§3), and
   whether game-pids should learn `gamescope-wrap` as a root.
3. Tolerate-the-139 vs pin 3.16.19: recommendation is tolerate (the
   wrapper launders it and the pin does not produce exit codes anyway,
   §1) — but it is a couchd-adjacent behaviour change and his call.

Needing a live session (EXPERIMENTS, all brief):
4. Focused nested fullscreen actually reaches 120Hz (spike only saw the
   30fps unfocused path).
5. Steam overlay + Steam Input inside nested gamescope for a real Steam
   title (overlay is stripped by design, §1): does the guard's model
   hold; does the PS-button vocabulary still reach Steam; what does
   ScopeBuddy's LD_PRELOAD dance buy us if we need it.
6. Freeze/thaw a wrapped game (both shapes), including a long freeze;
   pause-snap capture of the frozen gamescope window not black.
7. `import -window root` not black over a nested gamescope session (the
   recipe's phone-screen-tab gate).
8. xfwm4 unredirect behaviour on the fullscreen gamescope window at
   1080p120 (interacts with the X-side VRR notes in todo.md — do NOT
   toggle compositing under a live game while checking).
