# Next session brief — couch / couchd (written 5 Aug 2026 ~15:00)

> **17:15 UPDATE (review-fleet pass, commits a414699..d43fb75):** four
> adversarial reviewers swept the codebase on Donnie's instruction and
> every confirmed finding is fixed: the guard is wired into couchd's
> acted handoffs, the coalescing family is closed with consumable
> tracker markers, the differ now gates on action failures / missed
> effects / owner-inaction, the server's install/suspend hazards are
> gone, and the rigs are signal-safe. Final gesture-sweep 12/12; suites
> 441 + 213. Model fingerprint `d1adeed4083a` since ~17:10 - use
> `--window` for tonight's differ read. Fresh rulings queue in todo.md's
> NEXT. The health-check command and rules below are unchanged.

Read this first, then `todo.md`'s top "Resume here" block. Read
`docs/couchd-charter.md` before changing any couchd design decision.
Everything below is current as of commit `bee3cd8`.

## The one-line state

**couchd's first responsibility flip is LIVE**: `COUCHD_OWNS="gestures"`
in `couchd/owns.conf` since 5 Aug 13:01. couchd EXECUTES the PS-button
vocabulary; the legacy `pad-home-watcher` yields and logs what it would
have done instead. **Donnie's acceptance is still open** — his evening
couch pass is the gate. Nothing else is flipped.

## Health check (one command)

```
systemctl --user is-active couchd couch pad-home pad-record && \
python3 -c "import json;s=json.load(open('/home/ds2000/couch/shadow/status.json'));\
print(s['mode'],s['owns'],'acted',s.get('acted'),'fails',s.get('action_failures'),\
'observers ok',all(v['ok'] for v in s['observers'].values()))"
```

Expect: all active, `acting ['gestures'] ... fails 0 ... observers ok True`.
The `acted` counter is per-process and resets on restart; the durable
record is `shadow/couchd-YYYYMMDD.jsonl`.

## Rules (non-negotiable)

1. **Rollback must stay one step at all times**: empty `owns.conf`
   (instant), or `systemctl --user stop couchd` (legacy reclaims within
   30s via the status.json heartbeat lease). Never leave the box in a
   state where neither stack owns a responsibility.
2. **No new flips without Donnie's explicit acceptance of the current
   one.** One responsibility at a time, daytime, per the charter.
3. **Never wake the TV or launch a real game without him present.**
   `tv-waker` fires on pad connect, on `/tmp/tv-wake-request`, and on Kodi
   `Player.OnPlay`. Synthetic pad work MUST run inside `tools/fake-pad`'s
   inhibit frame (it stops tv-waker/pad-record/pad-battery and restores
   them on any exit, signals included).
4. **The fault rig is not to be run** (`tools/fault-rig`,
   `docs/fault-rig-runbook.md`): it needs a live game and Donnie present.
5. **Tests must never write live paths.** Two contamination bugs were
   fixed on 5 Aug (RecordingExecutor's `say()` spraying `/tmp/couchd.log`,
   ShadowLog binding its directory at import time). Inject sinks/tmp_path.
6. Prefer delegating to subagents (Opus for straightforward coding) to
   save context; adversarially review anything before it can act.

## Work available right now (no human needed)

Ordered by value. Pick up wherever makes sense.

1. ~~Synthetic gesture sweep~~ **DONE 15:25 (commit 500c6ae): 12/12 PASS
   via the new `tools/gesture-sweep`** - gap sweep, holds, tap-then-hold,
   stuck hold, burst, disconnect mid-hold; all switcher effects verdicted
   confirmed; 0 action failures; TV never woke. Re-run it any time couchd
   is acting on gestures; it preflights everything it assumes.
2. ~~Legacy bug 5~~ **DONE (commit 87c40fa)**: server/sys.js +
   server/steam.js now use `game-pids` (reaper tree) instead of
   `pgrep -f steamapps/common`; errors fail safe; couch restarted.
   `tools/fault-rig` injection 6 (`bystander-process`) can prove it fixed
   when the rig next runs (needs Donnie).
3. **Model catch-up: the settle window** — the one T5 note still not
   modeled. BLOCKED on Donnie's ruling: does a press swallowed during the
   1.2s post-transition settle seed the double-tap window? Do not guess.
4. **Differ: the `launch` verb** is in `CONTEXT_VERBS`, so the Big Picture
   pre-step is unchecked in both directions. Needs a decision about
   whether legacy's launches (which couchd cannot predict) stay
   context-only while `model_only` ones get compared.
5. **Evening-2 differ run** once Donnie has used the TV: use
   `tools/shadow-diff --window` (a whole-day run mixes model versions and
   most rows read stale). Triage into T1-T6; T4s gate the flip.

## What only Donnie can do

- **His evening couch pass** = the acceptance for `gestures`.
- `sudo systemctl restart pad-connect` (still owed: the daemon runs
  pre-fix code for legacy bug 3).
- The fault-rig session (~20 min, live game, runbook in docs/).
- Three rulings: the settle window (above); whether the phone's direct
  suspend/quit buttons should yield post-flip or stay a user-intent
  exception; the differ `launch` question (above).
- TV purchase decision (shortlist and follow-up work in `todo.md`).

## Facts not to re-derive (they cost real time on 5 Aug)

- **A sampled state machine must not infer an edge sequence from the
  states it happened to visit.** The gesture region samples at ~50ms; a
  fast double-tap's two edges coalesce into one pass. The fix is to ask
  `gesture.PressTracker` (which decides at the press, in kernel time),
  not to walk `idle→down→tap-wait→down-again`. SR4: that arithmetic lives
  in `gesture.py` and both stacks must decide identically.
- **A silent no-op is indistinguishable from a dropped press.** That is
  how the double-tap bug hid behind `action_failures: 0`. Gestures that
  decide nothing now log a `gesture-no-op` record; keep it that way.
- **Kodi is the one rate-limited observer** (>=10s per R6), so any C17
  effect only visible through Kodi needs a targeted read
  (`KodiObserver.request_read`) or it verdicts "unverified" forever.
- **couchd must never write `owns.conf`** — it is Donnie's daytime edit,
  and the unit's `ProtectSystem=strict` makes it read-only to the daemon.
  On repeated action failures couchd surfaces `action_failures`; a human
  decides the rollback.
- **Ownership is a lease, not a flag.** Legacy yields only while couchd's
  `status.json` heartbeat is under 30s old.
- **Blocking opens are a hazard in the observers.** `/tmp/vpad.fifo` with
  no writer once hung the whole daemon before sd_notify READY. Special
  files are observed by existence only.
- **`/dev/input/js0` is permanently the web remote's uinput mouse**; the
  real pad is js1/js2. Any "is a pad present" check must match the
  DualSense by device name, never by any `js*` node.
- Steam's `gameprocess_log.txt` is an authoritative per-appid PID ledger;
  `SSGL: UI mode (a->b)` marks Big Picture open/close (4=BPM, 7=desktop).
- The box hard-froze once at 05:19 (idle, no logs, first ever, 27h after
  a RAM swap; RAM is at stock 2667, XMP off). If it recurs: BIOS "Power
  Supply Idle Control = Typical Current Idle", then an overnight memtest.
  A crash can punch NUL holes in the JSONL corpora; the differ counts and
  skips them.
