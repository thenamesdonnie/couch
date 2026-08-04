# couchd (stage 1: shadow mode)

One daemon that watches everything the four console scripts watch, keeps the
whole state machine in one place, and **says what it would do**. It does not
act. There is no acting executor anywhere in this code, so passivity is
structural, not a flag someone can forget to set.

The old stack (`pad-home-watcher`, `game-launch`, `steam-input-guard`, the
watcher's `reconcile()`) keeps doing the real work exactly as before. couchd
runs beside it, and we compare its would-do log against what actually
happened, evening after evening, until they agree.

Design note: `../docs/couchd-stage1-design.md`. Audit: `../docs/audits/console-robustness-2026-08.md`.

## Rollback

    systemctl --user stop couchd

That is the whole rollback. couchd being down is never an error and never
affects the console; nothing depends on it and nothing may be made to.

## What runs

| file | what it is |
|---|---|
| `couchd.py` | the daemon: observers, state machine, pure `reconcile()`, shadow output |
| `gesture.py` | the PS-button arithmetic: thresholds, predicates, `PressTracker` |
| `gestureconf.py` | the PS-button **key bindings**, read from Kodi's settings file |
| `x11.py` | the read-only python-xlib adapter (the only X code; replaced in stage 4) |
| `test_reconcile.py` | unit + Hypothesis tests for the pure model (no daemon, no I/O) |
| `test_gesture.py` | the tap / double-tap / hold / long-hold arithmetic |
| `test_gestureconf.py` | every failure path of the settings reader, and the safety rail |
| `couchd.service` | the systemd user unit. **Not installed by the build** |

Install (operator, when wanted):

    cp ~/couch/couchd/couchd.service ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user start couchd

Run it in the foreground instead, for a look:

    ~/couch/couchd/.venv/bin/python ~/couch/couchd/couchd.py

## Key bindings (Kodi > Add-ons > Program add-ons > Couch Switcher > Configure)

What the PS button does is a **setting**, not a constant, and both stacks read
the one file: `gestureconf.py` parses
`~/.kodi/userdata/addon_data/script.couch.switcher/settings.xml`, the live
watcher dispatches on it, and `reconcile()` decides its would-do from it. One
file, two stacks, so a rebind moves them together and the shadow diff still
compares like with like.

Defaults, which are exactly the console as it shipped:

| gesture | default action | what it does |
|---|---|---|
| `tap` | `none` | (a tap with a game **paused** always resumes it - see below) |
| `double_tap` | `switcher` | the on-TV switcher dialog |
| `hold` (0.9s) | `suspend_to_kodi` | freeze the game, hand the pad and the screen to Kodi |
| `hold_release` | `none` | fires when the button comes back up after a hold |
| `long_hold` (3.0s) | `none` | the third tier |

Actions: `none`, `suspend_to_kodi`, `switcher`, `steam_menu`, `power_menu`,
`quit_game`, `tv_toggle`, `desktop`. Timings: `hold_seconds` 0.9,
`double_tap_seconds` 0.35, `long_hold_seconds` 3.0.

Three rules that are not negotiable from the settings page:

* **the safety rail** - at least one gesture must reach `suspend_to_kodi`. It
  is the only way out of a running game from the couch, so a config that binds
  it away everywhere is rejected *as a whole* and `hold` is forced back to it,
  with a warning in `/tmp/couchd.log` and `/tmp/pad-home.log`.
* **the hold beats the long hold** - the hold fires at 0.9s exactly as it
  always has, and by then the press is spent. `long_hold` is therefore only
  reachable with `hold` set to Nothing; bound together, the long hold is
  dropped with a warning rather than double-firing.
* **the double-tap beats the tap**, for the mirror reason: with both bound,
  every double-tap would fire the tap action on its way through.

**A tap that resumes a paused game is not a binding.** It is the recovery
path - the only route back into a game this stack suspended - so binding it
away would strand the paused game. It stays state logic above the dispatch, in
the watcher and in the model's `tap-resume` state.

Nothing raises: a missing, truncated, half-written or nonsense settings file
degrades field by field to the defaults above and says so. The read is one
`stat()` unless the file changed, so both loops poll it every iteration and a
rebind lands within a tick - no restart, no reload signal.

## What it reads (all read-only)

* the DualSense evdev node - opened `O_RDONLY`, **never grabbed**; all gesture
  arithmetic uses the kernel's own event timestamps;
* `/tmp/game-session`, `/tmp/game-suspended` (plus `vpad.fifo`,
  `steam-input-guard.pid`, `tv-wake-request`) - inotify on the `/tmp`
  *directory* filtered by name, so rename-writes are never missed;
* the game process tree - `game-pids`' reaper/shadPS4 logic ported in-process
  onto psutil (never a subprocess per tick);
* X11 - window stacking, focus, class, Steam's root atoms. The only X write is
  subscribing to root events; `SubstructureRedirect`, `ResizeRedirect` and
  `XGrabServer` never appear in this code;
* Kodi - a persistent notification socket on `127.0.0.1:9090`, plus
  `Settings.GetSettingValue(input.enablejoystick)`, `GUI.GetProperties`
  and `Player.GetActivePlayers` over HTTP, never more often than every 10s.
  Credentials come from `~/couch/.env`, never from source;
* Steam's own logs - `gameprocess_log.txt` (the authoritative tracked-process
  ledger) and `controller_ui.txt` (menu routing), tailed `(dev,ino,size)`-aware;
* `/tmp/game-launch.log`'s `===` lines, as *trigger* observations only.

## What it writes (the only paths it touches)

    ~/couch/shadow/couchd-YYYYMMDD.jsonl     observations, intents, transitions, invariants
    ~/couch/shadow/snapshots-YYYYMMDD.jsonl  periodic world snapshots
    ~/couch/shadow/status.json               current state, rewritten atomically every ~3s
    ~/couch/shadow/couchd.lock               single-instance flock (held fd)
    /tmp/couchd.log                          human one-liners, same shape as the other scripts

Nothing else. The unit enforces it: `ProtectSystem=strict` with
`ReadWritePaths=%h/couch/shadow /tmp` and nothing more.

## Reading status.json

    cat ~/couch/shadow/status.json | python3 -m json.tool

* `regions` - the six state regions. Any of them can read `unknown`, which
  means *that source could not be observed*; couchd suppresses every decision
  that depends on an unknown region rather than guessing.
  * `input_ownership` kodi | game | steam-menu | unknown
  * `foreground` kodi | game | bigpicture | other | unknown
  * `session` none | starting | active | orphaned | ending | unknown
  * `enforcement` none | kodi | game (couchd's model of a guard window)
  * `gesture` idle | down | hold-fired | handoff-pending | timed-out |
    tap-resume | tap-wait | down-again | double-tap | long-hold-fired — the
    middle three are the double-tap switcher: a no-op tap parks in `tap-wait`
    for 0.35s (`gesture.DOUBLE_TAP_S`), a second press inside that window is
    `down-again`, and its release — if it is a tap and not a hold — is
    `double-tap`, which asks for the on-TV switcher. `long-hold-fired` is the
    third tier and is unreachable unless `hold` is bound to Nothing.
* `bindings` / `timings` - what the PS button is bound to right now, straight
  from the addon's settings page.
  * `pad` present | absent | unknown
* `games` - appid → lifecycle (`LAUNCHING`/`RUNNING`/`FROZEN`/`MISSING_WINDOW`/
  `STOPPED`…), from Steam's ledger crossed with the process tree.
* `last_would_do` - the last three decisions, in the same words as
  `/tmp/couchd.log`.
* `observers` - per source: `ok`, `age_s` since its last update, `events`,
  `stale`. **A source that is not ok invalidates that evening's comparison**;
  it does not invalidate the daemon, which keeps running degraded.
* `counts` - event counts by log kind; `passes`, `intents`,
  `invariant_violations`; `ps_presses` cross-checks the evdev press count
  against Steam's own `Guide button` lines (two independent channels for the
  same physical press).

The phone reads this file: the couch server proxies it at
`/api/couchd/status` and the Screen tab shows three lines from it.

## Log kinds (`couchd-YYYYMMDD.jsonl`)

Every record has `t` (epoch float), `mono` (monotonic float), `seq`
(monotonic int) and `kind`.

* `intent` - a would-do. `{verb, subject, args, reason, regions, predict}`.
  `predict` is `{effect, deadline_s}` (or null): the observable this decision
  expects, so the model can be scored before anything ever acts.
  `freeze`/`thaw`/`quit`/`kill` always carry `args.pids` + `args.resolver`.
* `obs` - an observation. `source` is one of `pad`, `flags`, `pids`, `kodi`,
  `x11`, `steam`, `trigger`, `world`. Together these are the replay corpus.
* `transition` - `{region, from, to, reason}`, through the one chokepoint.
* `invariant` - a check result; `ok:false` carries the violations.
* `agreement` - the freeze-set agreement metric (couchd vs the process tree vs
  Steam's ledger) and the PS-press channel cross-check.
* `observer_blind` - a source went quiet, a log rotated, or Kodi went away.
* `daemon` - start/stop.

`snapshots-YYYYMMDD.jsonl` holds `kind: "snapshot"` records (flags, pid
states, joystick, top window, regions) every 30s and on every attention
trigger - the corpus for the reconcile responsibility, which the pad recorder
structurally cannot cover because it only runs while a pad is present.

## Timing

Anti-entropy tick every 5s. Any observed change opens a ~3s attention window
sampled at 200ms, so a fault is seen before the legacy repair loops erase it.
Outside an attention window nothing runs faster than 1s; Kodi is never read
more often than every 10s whatever else is happening. Measured idle cost on
this box: ~2% of one core, ~38MB RSS.

## Tests

    cd ~/couch/couchd
    .venv/bin/python -m pytest -q

`test_reconcile.py` exercises the pure model only - the audit's failure modes (orphaned
session, stale flag, lost thaw, joystick drift, frozen game visible), the
gesture boundary (0.8s is a tap, 0.9s is a hold), unknown-region suppression,
the two pre-declared legacy bugs that couchd is supposed to get *right*, and a
Hypothesis state machine driving random observation sequences through the real
transition table asserting the named invariants after every step. It also
pins the bindings: that the defaults decide exactly what the console decided
before the settings page existed, and that a rebound gesture changes the
emitted intent on both sides of the diff.

`test_gestureconf.py` is mostly failure paths - empty, truncated, non-XML and
nonsense files, unknown actions, out-of-range timings - plus the safety rail
and the two precedence rules. It also checks the addon's own
`resources/settings.xml` against the module's vocabulary and its `strings.po`,
so the page and the reader cannot drift apart. Nothing in it writes to
`~/.kodi/userdata`; that path is Kodi's.
