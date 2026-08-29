# couchd core review, 29 Aug 2026 - adjudication

Reviewer: gpt-5.6-sol via Codex, read-only, reasoning effort high.
Raw report: `couchd-core-review-20260829-sol.md` (UNADJUDICATED).
This file records what was checked back against the code by Claude.

Only a single reviewer ran this lens, so the blind-pair half of the documented
method is MISSING. Treat unverified rows accordingly.

| # | Claim | Adjudicated | Notes |
|---|---|---|---|
| 1 | Input ownership cached at startup | **CONFIRMED** | `grants_input()` called once, `inputproc.py:1411`. `self.own = args.own_input` at `:549`. Only other write is `self.own = False` at `:877`. Main loop at `:1303` reloads `gestureconf.load()` and never re-reads `owns.conf`. |
| 2 | Configurable timings don't reach the classifier | **CONFIRMED** | `couchd.py:3701` builds `gesture.PressTracker()` with NO arguments. `inputproc.py:551` builds the same class WITH conf values. `couchd.py:5277` re-reads `hold_seconds` into `Observed` every pass, with a comment boasting that a rebind takes effect without a restart. Line cited as 3699, actually 3701. |
| 3 | A dropped supervisor message can synthesise a hold from a tap | **NOT VERIFIED** | Plausible and the queues are documented as dropping. Not checked line by line. Live drop counters are zero. |
| 4 | uinput write failure leaves the pad consumed while health stays green | **NOT VERIFIED** | Same. `write_failures: 0` live. |
| 5 | Gesture timing uses the wall clock | **CONFIRMED, narrower than stated** | `EVIOCSCLOCKID` and `CLOCK_MONOTONIC` appear nowhere in couchd's Python. So kernel event timestamps are realtime. BUT the loop's stuck-button guard does use `time.monotonic()` (`inputproc.py:1303`), so the exposure is narrower than the report implies. |
| 6 | Stalled launcher yields an indefinite active session | **NOT VERIFIED** | Reasonable from the cited lines; not chased. |

## The one that matters most

**#1 is a safety-net failure, not a feature bug.** The documented rollback for
the input flip is to remove `input` from `owns.conf`. That does nothing to a
running inputproc: it keeps `EVIOCGRAB` and keeps withholding `BTN_MODE`.
Because axes and ordinary buttons still pass through the virtual pad, the
failure presents as *a selectively dead PS button*, not as a dead service, which
is the hardest possible shape to diagnose from the sofa.

`sudo couchd-input-release` still works and remains the real lever. The config
rollback is the one that lies.

## Reviewer quality note

Worth recording: on the transition lens the same reviewer was told to prefer a
single shared root cause and **refused**, stating the evidence split. It was
right. On this lens it repeatedly marked where a defect is masked by current
live config rather than claiming a live fire. That is the behaviour the method
is trying to buy, and it argues for keeping the effort at `high`.

## Not done

- No blind Claude pair on this lens. The method wants one before fixes land.
- #3, #4, #6 unverified.
- Nothing fixed yet. No code changed.
