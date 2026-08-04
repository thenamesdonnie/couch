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
| `x11.py` | the read-only python-xlib adapter (the only X code; replaced in stage 4) |
| `test_reconcile.py` | unit + Hypothesis tests for the pure model (no daemon, no I/O) |
| `couchd.service` | the systemd user unit. **Not installed by the build** |

Install (operator, when wanted):

    cp ~/couch/couchd/couchd.service ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user start couchd

Run it in the foreground instead, for a look:

    ~/couch/couchd/.venv/bin/python ~/couch/couchd/couchd.py

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
    tap-resume | tap-wait | down-again | double-tap — the last three are the
    double-tap switcher: a no-op tap parks in `tap-wait` for 0.35s
    (`gesture.DOUBLE_TAP_S`), a second press inside that window is
    `down-again`, and its release — if it is a tap and not a hold — is
    `double-tap`, which asks for the on-TV switcher. Nothing is delayed by
    the wait: a tap's own action, if it had one, already fired from `down`.
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
    .venv/bin/python -m pytest test_reconcile.py -q

They exercise the pure model only - the audit's failure modes (orphaned
session, stale flag, lost thaw, joystick drift, frozen game visible), the
gesture boundary (0.8s is a tap, 0.9s is a hold), unknown-region suppression,
the two pre-declared legacy bugs that couchd is supposed to get *right*, and a
Hypothesis state machine driving random observation sequences through the real
transition table asserting the named invariants after every step.
