# Round 2: fix the two defects in your own diff

You already changed this worktree in response to `docs/audits/fix-brief-20260829.md`.
Your work is still here, uncommitted. Most of it is good. The launcher fix
(finding 4) is accepted as-is.

Running the full suite found two defects **caused by your diff**. This was
confirmed against two controls: the live tree and a second clean worktree at the
same commit both pass all 146 of the relevant tests. So these are yours, not
pre-existing and not environmental.

Fix ONLY these two things. Do not touch the launcher work. Do not refactor. Do
not "improve" anything else. Do not weaken or delete a test to make it pass.

Full suite before you start: `1419 passed, 8 failed`.
Command: `couchd/.venv/bin/python -m pytest couchd/ tools/ -q`

---

## Defect 1 (SERIOUS) - your switcher change double-fires

`couchd/test_reconcile.py::test_a_tap_that_opens_the_switcher_does_not_then_resume_the_game`
now fails at the final assertion:

```
AssertionError: the switcher was asked for twice:
  [('show', 'kodi'), ('spawn_guard', 'kodi'), ('show_switcher', 'tv')]
```

The test walks six further observation passes after the tap has already been
handled, with `suspended=APPID` and the game pids in state `T`. On one of those
later passes your code emits a SECOND batch: `show kodi`, `spawn_guard kodi`,
`show_switcher tv`, with `suspended_first: False`.

Why this matters more than a red test: `suspended_first: False` is the
**bare-restack branch**, the one that raises Kodi with nothing covering it. That
is the exact user-visible bug finding 3 asked you to eliminate. Firing it a
second time, after the switcher has already been requested, reproduces the Kodi
flash rather than removing it.

The pre-existing `g_tap_resume_due` mechanism stopped the old version of this
class of bug. Whatever state you added to gate the new show/confirm sequence is
not being cleared, or is being re-entered, once the first sequence completes.

Required: a single tap produces exactly one switcher request. Once the switcher
has been asked for, later passes over the same completed press must produce
nothing, and the gesture region must still end at `idle` as the test asserts.
Do not satisfy this by relaxing the test.

## Defect 2 - your new tests leak global state

Seven tests fail in `tools/test_kodiprofile.py`, a file you did not modify.

Reproduction:

```
couchd/.venv/bin/python -m pytest tools/test_kodiprofile.py -q
    -> 13 passed

couchd/.venv/bin/python -m pytest couchd/test_inputproc.py tools/test_kodiprofile.py -q
    -> 7 failed, 82 passed
```

So one or more of the tests you added to `couchd/test_inputproc.py` mutates
process-global state and does not restore it. Likely an environment variable, a
patched `HOME`, or a module-level cache that `kodiprofile` reads.

Required: your tests must restore whatever they change. Use `monkeypatch` or a
fixture with teardown rather than assigning to `os.environ` directly. Both
orderings above must pass.

---

When done, run the full suite and report the exact final counts. State plainly
whether `8 failed` is now `0 failed`, and if any failure remains, say which and
why rather than describing the run as clean.

Then write a short summary to `FIX-SUMMARY.md` in the worktree root: what you
changed for each defect, and anything you believe is still wrong.
