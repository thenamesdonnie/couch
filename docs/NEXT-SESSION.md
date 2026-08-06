# Next session brief — couch / couchd (written 6 Aug 2026 ~04:30, post-acceptance)

Read this first, then `todo.md`'s top "▶ Resume here" block. Read
`docs/couchd-charter.md` before changing any couchd design decision.

## The one-line state

**`gestures` is FLIPPED and ACCEPTED** (Donnie, ~04:15 BST 6 Aug, after the
overnight couch pass). couchd executes the PS-button vocabulary; legacy
yields and shadows it. Differ over the pass: VALID, acted 87 / 0 failures /
0 OWNER-MISSED, latency p50 83ms. Evidence: `docs/acceptance-20260806.md`,
re-run with `tools/shadow-diff --window 02:30-04:10 --date 20260806`.
**Today is deploy day** — the ordered checklist lives in todo.md's resume
block (curtain whitelist, switcher addon reload, curtain wiring, guard
cleanup, BP-hide fix, kodi-tv FFCP decision, oracle fixes, sweep last).

## Health check (one command)

```
systemctl --user is-active couchd couch pad-home pad-record && \
python3 -c "import json;s=json.load(open('/home/ds2000/couch/shadow/status.json'));\
print(s['mode'],s['owns'],'acted',s.get('acted'),'fails',s.get('action_failures'),\
'observers ok',all(v['ok'] for v in s['observers'].values()))"
```

Expect: all active, `acting ['gestures'] ... fails 0 ... observers ok True`.
Model fingerprint should read `d1adeed4083a` until the curtain-whitelist model
change moves it (that change requires a differ note + couchd restart).

## Rules (non-negotiable) — unchanged

1. Rollback stays one step: empty `couchd/owns.conf` (instant) or
   `systemctl --user stop couchd` (legacy reclaims within 30s via the lease).
2. No new flips without Donnie's explicit acceptance of the current one.
   NEXT FLIP: `reconcile` is argued next BUT is hard-gated on the
   refreeze-lost-suspend ordering fix (see todo.md — legacy thaws before it
   clears the suspended flag; couchd-owning-reconcile would re-freeze
   mid-resume; observed in shadow 3x on 6 Aug).
3. Never wake the TV / launch a game without Donnie present; synthetic pad
   work only inside `tools/fake-pad`'s inhibit frame.
4. The fault rig is not to be run without him (docs/fault-rig-runbook.md).
5. Tests must never write live paths.
6. Prefer delegating to subagents; adversarially review anything that acts.

## Load-bearing facts from the acceptance night (cost real time)

- **Big Picture's window left mapped fullscreen behind a game wrecks frame
  pacing** ("Steam says 60, feels 20"). game-launch raises BP and never hides
  it; BP-UI launches hide it themselves. Fix = deploy item; interim rescue =
  iconify the steamwebhelper window.
- **Never toggle xfwm4 compositing under a live fullscreen game** — it
  black-screens/wedges the game's presentation (twice). Compositor changes
  only while nothing fullscreen is presenting.
- kodi-tv line 24 reapplies ForceFullCompositionPipeline on every Kodi start
  (double-composition with xfwm4). Removed live 6 Aug ~03:25; comes back on
  Kodi restart until the deploy decision.
- A stale `/tmp/vpad.fifo` makes every subsequent steam-input-guard run with
  `vpad_started: false` — menu-closing silently dead for BOTH stacks. Guard
  must clean pidfile+fifo on exit (deploy item; leak reproduced every run).
- Legacy's guard "superseded-by-newer-guard" protocol SIGTERMs the OTHER
  stack's guard too (caused the 03:16 Kodi<->BP loop). Ruling R-a.
- Legacy yield-path records pids=[] for every would-freeze (10 gating rows).
- snapshot + iconify effect oracles never confirm live (5/5 unverified);
  launch-bigpicture oracle needs windows, not pids.
- /tmp/couchd.log timestamps are UTC; wall clock is BST (+1).
- python-xlib's DAMAGE/error decoding is broken here — install MangoHud for
  frame-time work instead.
- Steam sees every PS press in stage 1 (overlay pops on tap, BP power menu on
  hold, Kodi 10106 on >=1s hold). All console-normal until the `input` flip
  (stage 2, built, combined cutover with gestures, needs Donnie's sudo).

## What only Donnie can do (current)

- Three NEW rulings from the acceptance night: R-a guard arbitration,
  R-b switcher-pick routing through Steam BP, R-c BP tile while suspended
  (details in todo.md). Plus the five standing 5-Aug rulings.
- `sudo systemctl restart pad-connect` (still owed, pre-fix code running).
- Governor flip sudo step when the CPU watcher lands; fault-rig session.
- TV/soundbar arrival tasks (LG C5 — see todo.md TV section).
