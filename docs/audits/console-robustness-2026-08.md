# Console session system: robustness audit (4 Aug 2026)

Scope: pad-home-watcher, game-launch, steam-input-guard, game-pids, vpad /
ps-button test rigs, couch Screen-tab switcher (screen.js/xinput.py), and the
Kodi / Steam / game state machine. Production = the living-room TV; it stayed
green throughout (Kodi Home, services active, no flags left behind).

## The state machine

States: Kodi-only · Big Picture browsing · game running (pad->game) · game
suspended (pad->Kodi). Shared truth: `/tmp/game-session` ("<launcher pid>
<mode> <appid>"), `/tmp/game-suspended`, Kodi's `input.enablejoystick`, X
stacking/focus, process states (S/T), and Steam's private menu/routing state
(readable only via `controller_ui.txt` `OnFocusWindowChanged` lines).

## Robustness requirements and their implementation

| Requirement | Implementation | Status |
|---|---|---|
| One identity for "the game" | `~/.local/bin/game-pids`: reaper SteamLaunch process tree + shadPS4 AppImage names; used by watcher, game-launch, guard, couch server | DONE (this audit) |
| All transitions via one manager | game-launch modes (steam/bigpicture/shadps4/resume/suspend/quit/focus); watcher and Screen-tab switcher both route through it | DONE |
| Convergent enforcement, not one-shots | steam-input-guard 6s loop after every transition (menu-close, right window on top, no frozen game visible, thaw-repair), single-instance via pidfile+SIGTERM | DONE |
| Standing drift repair | watcher `reconcile()` every ~10s, with or without pad: orphaned session, stale paused flag, lost thaw, joystick-setting drift, frozen-game-visible | DONE (this audit) |
| Supervision at every layer | systemd Restart=always on pad-home + couch; kodi-tv watchdog for Kodi; guard supersede | DONE (pre-existing + verified) |
| Pad-independent escape hatches | couch app Screen-tab switcher (state-aware) + power menu quit; SSH cheat sheet below | DONE |
| Test rig | psfuzz.py (fake-DS + vpad = a real thumb; screenshots + window stack + Steam routing + Kodi window per step); ps-button; vpad | DONE |

## Failure modes found and their grades

| # | Failure mode | How it occurs | Grade | Outcome |
|---|---|---|---|---|
| 1 | **Proton games never actually froze** | pgrep matched `steamapps/common`, but Proton maps the library to `S:` so `eldenring.exe`'s cmdline has no "steamapps"; only 7 wrappers froze, the game ran on invisibly (the "mystery un-freeze") | A | FIXED: game-pids process-tree identity. Verified live: all 18 ER processes T on hold, S on resume |
| 2 | Loose cmdline matching counts bystanders as game processes | any process whose cmdline mentions the path (rsync backups, test shells) was frozen/counted | A | FIXED by game-pids (tree membership, not text match) |
| 3 | Steam menu invisibly captures the pad | Steam sees every PS press over hidraw and toggles its BP menu out of sync with our screens | A | FIXED earlier today: guard invariant 1 (menu-close via vpad guide) |
| 4 | Kodi phantom-held button opens power menu | joystick re-enabled mid-hold; Kodi misses the release | A | FIXED: freeze at 0.9s, handoff on release (+4s timeout) |
| 5 | Frozen game visibly on top | window raised after guard window / raw switcher raise | A | FIXED: guard invariant 3 + reconcile + state-aware switcher |
| 6 | Lost thaw (game frozen, no paused flag) | CONT raced or freeze hit partial set | A | FIXED: guard invariant 4 + reconcile thaw-repair (verified with decoys) |
| 7 | Kodi crash-restart reloads stale joystick setting | crash restarts don't save settings; box has known Kodi 20 teardown crashes | A | FIXED: reconcile compares setting to session state every 10s (verified) |
| 8 | Orphaned session (launcher killed, no trap) | SIGKILL/crash of game-launch; pad never returns to Kodi | A | FIXED: reconcile reclaims (verified) |
| 9 | Stale paused flag (game killed externally) | next PS tap misfires | A | FIXED: reconcile removes (verified) |
| 10 | Guard leaks vpad when superseded | SIGTERM killed it before cleanup; phantom player-2 forever | A | FIXED: SIGTERM handler (verified pidfile cleanup) |
| 11 | PS button dead 30s after pad connect | udev ACL race -> PermissionError -> long penalty sleep | A | FIXED: 5s retry |
| 12 | Stale power menu behind resumed game | hold opens it, tap resumes over it | A | FIXED earlier today: resume dismisses window 10106 |
| 13 | Concurrent transitions (PS spam + switcher) | interleaved freeze/thaw/flag writes | C | Accepted: operations idempotent, invariants converge; no lock added |
| 14 | Steam raises windows outside guard windows (update dialogs etc.) | no session; Kodi covered | C | Accepted: switcher/PS hold recovers; auto-enforcing would fight legit desktop use |
| 15 | guard re-reads whole controller_ui.txt each second | file growth | C | Accepted: file is rotated by Steam, small |
| 16 | SIGSTOP of online games (EAC/co-op) drops connections | suspension by design | C | Accepted + documented: offline fine, online sessions will drop on suspend |
| 17 | Precise-tree edge: Steam redistributable installs run under reaper briefly | transient false session membership | B→todo | Low impact; note in todo |
| 18 | Real-DualSense Steam path (hidraw) untestable synthetically | uhid emulation is a project | B→todo | Physical-pad test is the human item |

## Recovery layers (in order)

1. **Automatic, continuous**: watcher reconcile every ~10s (flags vs processes
   vs joystick vs visible window) - runs pad or no pad.
2. **Automatic, per transition**: steam-input-guard 6s enforcement after every
   suspend/resume/switcher action.
3. **Pad gestures**: HOLD PS always tries to land you on Kodi with the pad;
   on home, HOLD opens the power menu (quit lives there), TAP resumes.
4. **Phone (works even with the pad stolen)**: couch app Screen tab ->
   switcher -> tap **Kodi** = the panic button (proper suspend + guard);
   tap the paused game to resume. Power menu on Kodi = save-and-quit.
5. **SSH / Claude cheat sheet** (all as ds2000, no sudo):
   - `game-launch quit` - save-and-close everything, pad back to Kodi
   - `game-launch suspend` / `resume` / `focus` - manual transitions
   - `steam-input-guard kodi 6` - force Kodi + close Steam's menu
   - `game-pids` - what the system thinks the game session is
   - `systemctl --user restart pad-home couch` - the daemons
   - `rm /tmp/game-session /tmp/game-suspended` - nuke session state (then
     reconcile makes reality match within 10s)
   - logs: /tmp/pad-home.log, /tmp/game-launch.log, /tmp/steam-input-guard.log
6. **Reboot**: everything reconstructs from autostart; /tmp flags clear.

## Verification evidence

- psfuzz runs (3): all steps matched expectations incl. Steam controller
  routing; screenshots archived in the session scratchpad (screenshots not preserved).
- Elden Ring live: hold -> 18/18 processes T (incl. eldenring.exe), resume ->
  18/18 S, quit -> clean, Kodi Home. This is the first time Proton suspend
  has actually worked.
- Reconcile: orphaned session, stale flag, joystick drift, lost thaw (fwd and
  backslash decoys) each staged and repaired within one 10s tick.
- Guard SIGTERM: pidfile removed on supersede.
- Production green at close: pad-home + couch active, Kodi on Home, no
  session/suspended flags, no decoys or virtual pads left.

## Deferred ([B], in todo.md)

- Physical-pad end-to-end pass of today's changes (human).
- uhid full-DualSense emulation to test Steam's hidraw path synthetically.
- Consider excluding transient `reaper` children that are not games (Steam
  redistributable installers) if it ever misfires.

## Audit-of-the-audit sweep

- Every [A] verified live above - none are code-read-only. 
- The one thing NOT verifiable from here: real-pad hidraw behavior (item 18).
- Pattern edits touched 4 callers; all 4 compile-checked and the two daemons
  restarted and re-verified against the live ER session afterwards.
- Test contamination (self-matching shells) invalidated two intermediate test
  results before being caught; final results all used non-matching probes.

## Addendum: theory-3 chaos test (same evening)

Human-chaotic press trains (couch/tools/chaos.py): spam taps 150-200ms apart,
gestures fired mid-transition (tap then hold during the menu animation, tap
during the kodi-guard window, hold mid-resume), double holds, boundary-length
presses (0.7s / 0.95s), all through both channels at once against a live
Hollow Knight Big Picture session. 8/8 bursts converged to a consistent state
(flags vs process states vs pad routing vs visible window all agreeing) in
0.1-1.3s, and quit landed clean. Caveat: the checker can sample a state that
is momentarily consistent while a queued transition is still landing (it then
converges again - every later burst re-verified this); and this exercises
timing chaos only, not the real DualSense hidraw path (theory 1).
