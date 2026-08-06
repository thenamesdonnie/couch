# Acceptance-pass findings — night of 6 Aug 2026 (02:30-04:30 BST)

## Couch-list scoreboard — ALL STEPS DONE except the soak
- Step 1 launch: PASS (couchd shadowed transitions correctly, 0 fails)
- Step 3 hold-suspend: PASS clean run 03:11 (all confirmable effects 0.01-0.43s;
  plus two earlier dirty runs under duress also acted correctly)
- Step 4 tap-resume: PASS first live run 03:14 (launch 0.62s, show 0.54s
  confirmed); 2nd clean pass 03:38 (thaw unstuck a BP loading hang)
- Step 2 double-tap switcher: couchd half PASS TWICE (freeze confirmed BEFORE
  switcher 0.7s; show_switcher confirmed 0.81s). Pick leg = legacy design
  item (see findings 1-2), NOT retried further.
- Step 5 fast double-tap: PASS 03:34:37 - Donnie's natural double-tap arrived
  COALESCED (ps-double-tap-coalesced, the bf34a27 edge) and acted correctly.
- Step 6 BP + hold: PASS 03:48 - correctly DIFFERENT chain for a pids-less
  session (set_flag only, no freeze/snapshot/iconify, reason
  ps-hold-bigpicture); handoff confirmed 0.27s; pad STAYED on Kodi, no
  tug-of-war (yesterday's flag-fight fix held). BP power menu pops on the
  hold (Steam stage-1 reaction, same family as Kodi 10106).
- Step 7 walk-away: PASS - 92s frozen, NOTHING touched it; resume via Kodi
  tile (legacy path, no couchd gesture - fine).
- Step 8 BT drop: PASS 03:45 - cut via bluetoothctl, reconnect on PS press
  16s later, ZERO phantom gestures, session untouched, tv-waker instant.
- tap-then-hold decides hold: seen live 03:20, correct.
- Donnie's rescue holds during broken states all executed correctly.
- Totals ~04:00: acted 97, action_failures 0, invariant violations 0.
- Two honest MISSED effect verdicts (correct behavior, real oracle gaps):
  close_steam_menu 03:34 (menu not routed, 8.5s) and launch-bigpicture 03:48
  (oracle waits on game pids; BP has none - needs a window-based oracle).

## Real findings for the differ / deploy day
1. GUARD SUPERSESSION FIGHT (biggest): legacy's switcher-pick resume spawns
   steam-input-guard(game) which SIGTERMs couchd's just-spawned kodi-guard
   ("superseded-by-newer-guard", legacy intent log 03:20:08) - both stacks
   share the guard binary+pidfile, newest kills oldest regardless of stack.
   Caused the Kodi<->BP loop ~03:16-03:20. Design question for the guard flip.
2. Switcher-pick resume on a BP-ADOPTED session (game launched inside BP UI,
   session adopted via bigpicture-appid-adoption) surfaces Steam BP instead of
   the game -> user clicks in BP -> overlapping resume flows. Needs a ruling.
3. snapshot + iconify effect checks: 4/4 UNVERIFIED live (5-17s timeouts),
   including on a clean uninterrupted suspend. They never confirm in the real
   environment. Oracles need rework.
4. spawn_guard leaks EVERY run: stale pidfile + leftover vpad.fifo after guard
   exit. couchd owned-resources flags them correctly. Guard should clean up.
5. steam-input-guard.log mixes local and UTC timestamps (cosmetic).
6. Steam overlay open/close flap at ~3/s for 60s+ during the loop (each PS
   press pokes Steam guide in stage 1; ammunition for the input flip).
7. REFREEZE-LOST-SUSPEND ORDERING HAZARD (seen 3x live: 03:18, 03:33, 03:42):
   legacy's resume thaws BEFORE clearing the suspended flag; in that gap
   couchd's reconcile shadow decides "would freeze [refreeze-lost-suspend]".
   If reconcile flips while legacy still owns transitions, couchd would
   RE-FREEZE the game mid-resume every time. MUST be resolved (ordering fix
   or model exception) BEFORE the reconcile flip. Tonight it is shadow-only.
8. vpad.fifo leak CONFIRMED HARMFUL then FIXED-BY-CLEANUP: while the stale
   fifo existed, every legacy guard close_steam_menu logged vpad_started:
   false (menu closing silently dead all night). After I removed the stale
   fifo+pidfile (03:41), the next guard created a fresh vpad (fifo 03:48).
   So spawn_guard's missing cleanup DISABLES the shared menu-close mechanism
   for both stacks. Raise finding 4's priority accordingly.
9. Switcher's Big Picture tile acted while a session sat FROZEN -> Steam BP
   hung "loading" indefinitely (blocked on SIGSTOPped game IPC). Donnie's
   tap-resume (thaw) unstuck it instantly. Switcher should not offer/act BP
   while a session is suspended, or must thaw first.
10. Legacy's yielded would-freeze recorded pids [] while couchd froze 18
    (03:34, game-pids resolver in yield mode) - differ pid-set-different
    rows will flag; triage note, not a live bug.

## FPS saga (console-level, NOT couchd) — ROOT CAUSE FOUND
- Symptom: Steam reports 60fps, feels ~20. Varied per relaunch.
- ROOT CAUSE: Steam Big Picture's steamwebhelper window left MAPPED FULLSCREEN
  behind the game by the game-launch path (ensure-bp-before-game). Compositor
  stacks live fullscreen surfaces (BP CEF + Kodi) under the game -> judder.
  Minimizing the BP window -> instantly smooth (03:5x). BP-UI-launched games
  are smooth because Steam minimizes BP itself.
- Red herrings tested and excluded: GPU low power state (pinning max changed
  nothing by itself), software rendering (game is on NVIDIA/DXVK), display
  mode (1080p60 correct), frozen pids (none).
- STILL CHANGED LIVE (restore/decide tomorrow):
  a) kodi-tv's ForceFullCompositionPipeline removed live (returns on next Kodi
     restart - line 24 of ~/.local/bin/kodi-tv). Watch Kodi for tearing
     tonight; decide tomorrow: drop from kodi-tv or restore.
  b) GPUPowerMizerMode back to auto (2) after A/B.
  c) xfwm4 compositing: ON (two OFF experiments broke game presentation
     black-screen; NEVER toggle under a live fullscreen game).
- DEPLOY-DAY FIX: game-launch should minimize/hide the BP window once the game
  window maps. Candidate too: session-keyed compositor/FFCP handling with the
  planned CPU governor watcher (add GPU PowerMizer there if wanted).
- Audio: game relaunches open their stream at 100% (blasted him once); master
  was at 32%, set to 60% baseline. Maybe session-start volume clamp.
- Master volume baseline now 60%.

## Env notes
- /tmp/couchd.log timestamps are UTC (wall clock BST = +1).
- python-xlib damage probe unreliable (BadRRCrtcError decode bug); install
  MangoHud for real frame-time work tomorrow.
- Evening evidence window for shadow-diff --window: from ~02:37 BST (pad
  connect 02:37) to end of session. Model d1adeed4083a throughout, one couchd
  process (pid 175610, up since 18:09 BST 5 Aug).
