# Lens 1 — stage 2 input process — SYNTHESIS, 9 Aug 2026

Two blind reviewers, one identical brief, neither seeing the other:

* **sol** — gpt-5.6-sol via Codex CLI, read-only sandbox, one shot.
  10 findings (2 CRITICAL). `stage2-inputproc-review-20260809-sol.md`.
* **claude** — an Opus subagent in a detached worktree pinned to the commit
  BEFORE sol's report was committed, so the report did not exist in the tree
  it could see. 21 findings (4 CRITICAL). Report kept out of the repo; its
  content is reproduced per finding below.

Adjudicated against the live code by the main session. Every claim was read
back to the file before it was graded. This is the record of what was true,
what was fixed, and what is still open.

## The headline

Stage 2 was built before the flip machinery grew up, and never rejoined it.
Both reviewers reached that independently and from different directions.
Everything CRITICAL here is one of three shapes:

1. the pad gets grabbed and **nothing consumes the gestures** (the supervisor
   wire is a stub, and both existing gesture stacks go blind);
2. the **flip switch is not `owns.conf`** (it was pinned in the systemd unit),
   so the charter's one-step rollback did not release the pad;
3. the **evidence disappears** (the service user's `$HOME` is `/nonexistent`,
   and the logger swallows every write error by design).

None of it was live: stage 2 has never been installed. All of it was on the
path to flag day.

## Convergence

Where two blind reviewers agree, the claim is strong. Where they split, the
split was the useful part.

| finding | sol | claude | adjudicated |
|---|---|---|---|
| supervisor wire is a stub; cutover kills the PS button | #1 CRITICAL | #1 CRITICAL | **CONFIRMED, CRITICAL.** Same defect, two routes: sol via the pad-name filter (couchd wants `DualSense Wireless Controller`, we present `Microsoft X-Box 360 pad`), claude via the udev permissions (ds2000 cannot open the node at all, so legacy dies too). Both true, and they compound. |
| unit hardcodes `COUCHD_OWNS=input` | #2 CRITICAL | #2 CRITICAL | **CONFIRMED, CRITICAL.** claude found the sharper consequence: `status.json`'s `owns_declared` can never mention `input`, so the evidence record would be wrong about who owned the pad. |
| handoff timeout is dead code | #7 MEDIUM | #6 HIGH | **CONFIRMED. Graded HIGH** — a pad that drops mid-hold left no record at all, and this box has a documented Bluetooth fault. claude's grade wins. |
| E1.8 Kodi buttonmap paths are pre-Flatpak | #9 LOW | #9 HIGH | **CONFIRMED. Graded HIGH** — sol under-graded it. It is not cosmetic: the gate can pass falsely off the leftover apt-Kodi tree, certifying SR2 against a Kodi that is not running. |
| SR4 divergence | #3 (re-injection re-times the chord, so the double-tap window is measured wrong) | #4 (`poll()` latches `hold_fired`, so feed() calls a 0.85s press a hold) | **BOTH CONFIRMED, and they are different bugs.** claude's is the more dangerous and was reproduced with synthetic timestamps. sol's is real but conditional on how #1 is eventually wired. |
| hold tier vs the bindings | #6 (LONG_HOLD silently discarded) | #5 (`hold=none` swallows the press entirely) | **BOTH CONFIRMED.** Same root cause: inputproc never read `gestureconf`, so it knew the timings but not the bindings. One fix closes both. |
| queued chord survives the pad | #4 HIGH | #13 (second half) | **CONFIRMED, HIGH.** |
| udev / group breadth | #10 (the `input` supplementary group is broad) | #15 (the rule takes the Touchpad and Motion nodes and nothing ever reads them) | **SPLIT, both stand.** Different objections; claude's is the one with a visible symptom (the touchpad stops moving the cursor after flag day). |

Neither reviewer reported anything the other contradicted. There were no
refutations to resolve — the disagreements were all of severity, not of fact.

## Fixed in this pass

All of these are stage-2-only code. inputproc is not installed and not
running, so none of it touched the live console. `gesture.py` was deliberately
**not** modified: it is shared with the daemon that is executing gestures
tonight, and no finding required changing it.

| # | what | where |
|---|---|---|
| c1 | **The interlock.** `main()` now refuses to own the pad while `report()` is a stub, with an explicit `--supervisor-stub-ok` escape for the rig. This does not fix the missing supervisor wire — it makes the living-room failure impossible to reach by accident. | `inputproc.py` `main()` |
| c2 | inputproc reads **`owns.conf`**, as that file's header always claimed it did. `COUCHD_OWNS` still wins when set, for the fake-pad rig. `Environment=COUCHD_OWNS=input` removed from the unit. | `inputproc.py` `grants_input()`, `stage2/inputproc.service` |
| c3 | `COUCHD_SHADOW_DIR` named explicitly in the unit, and `JsonlLog` now says `EVIDENCE LOST` once per new failure instead of swallowing it. `health` ticks carry `evidence_broken`. | `inputproc.py`, `stage2/inputproc.service` |
| c4 | **SR4.** `PressTracker.poll()` is gone from the input path. `poll_hold()` detects both tiers with the same non-latching predicates couchd's guards use, leaving the tracker pristine so `feed()` decides identically in both stacks. | `inputproc.py` `poll_hold()` |
| c5 | The hold tiers are **binding-gated** exactly as `couchd.g_hold_fires` gates them, and a `HOLD_RELEASE` where no bound tier fired is re-injected as the tap stage 1 would call it. Closes the `hold=none` swallow and the discarded `LONG_HOLD` together. | `inputproc.py` `on_guide()`, `poll_hold()` |
| c6 | The handoff timeout is reachable: the loop guard now requires the button to still be **down** (which is what "the release never came" means), and `detach()` reports a hold cut off by a lost pad. | `inputproc.py` |
| c7 | `detach()` clears the pending queue, so a dead pad cannot emit a phantom guide chord after `all_keys_up()`. | `inputproc.py` `detach()` |
| c8 | `emit()` returns success and records failures as evidence; `drain_pending()` abandons a half-sent chord and re-asserts all-keys-up rather than leaving a button held. | `inputproc.py` |
| c9 | `drain_pending()` emits **one** event per pass and pushes the rest of the chord out by however late it was, so a stalled loop can no longer collapse the 80ms gap to zero. | `inputproc.py` |
| c10 | The ownership assertion **degrades to observe-only** instead of `SystemExit(3)`, matching its own documented contract. It was killing a running process from the 1Hz rescan path and tripping `StartLimitBurst`, leaving the pad hidden with nothing able to read it. | `inputproc.py` `attach()` |
| c11 | `evaluate_ownership` **fails closed**: `read_acl` now returns `None` when getfacl could not be run (distinct from `''`), and the device's owning UID is checked, because getfacl renders the owner as `user::` and a node owned by ds2000 sailed through the named-entry regex. | `inputproc.py` |
| c12 | The FF handshake (`begin_upload` / `end_upload` / `begin_erase` / `end_erase`) is inside the guard. An ioctl error was killing the process, which to a running game is a controller unplug and a re-plug mid-fight. | `inputproc.py` |
| c13 | The poller reconciles on **(fd, role)**, not fd alone, so a reused descriptor number cannot dispatch the pad's readiness to the uinput handler and spin forever on an undrained POLLIN. | `inputproc.py` `loop()` |
| c14 | `phys_path` cleared on detach, so health ticks stop reporting a node that is not attached. | `inputproc.py` |
| t1 | **A real SR4 test.** The old one pinned three constants and called it SR4; it passed while the two stacks disagreed. The new tests feed identical kernel timestamps to both usages and assert the classification matches, assert the latch still exists in `gesture.py` (so the test cannot quietly stop testing anything), and assert structurally that the input path never calls `tracker.poll()` again. | `test_inputproc.py` |

Suite after: **1042 pass**, up from 1039. The 7 `tools/test_curtain.py`
failures are pre-existing, unrelated, and logged separately.

## Open — needs Donnie's ruling, not a patch

These are real and confirmed. They are not fixed because fixing them means
making a design decision that is his, not mine.

1. **The supervisor wire itself (CRITICAL, both reviewers).** `report()` must
   actually reach couchd. That is a protocol (the `SUPERVISOR_SOCK` constant
   exists and is unused, SO_PEERCRED, SR1/SR7's no-blocking-in-the-fast-path
   rule) plus a couchd-side consumer plus a `shadow-diff` that knows about
   `input` at all. It is a PROJECT. Until it exists, flag day cannot happen,
   and c1 now enforces that.
2. **What the flip switch should mean at runtime.** inputproc now reads
   `owns.conf` at startup. Should it re-read it live, the way couchd and the
   legacy scripts do? Live re-reading makes "empty the file" a true one-step
   rollback that ungrabs the pad within a tick — which is the charter — but it
   also means a mid-game edit or a half-written file hands the pad back under
   a running game. I did not decide this.
3. **The re-injected tap is ungated (sol #3, claude #17).** With `gestures`
   owned by couchd, a tap both fires couchd's action AND lands an 80ms guide
   chord on the virtual pad, which Kodi resolves through its own buttonmap.
   Whether the chord should be suppressed when couchd owns the gesture depends
   on the answer to #1, so it waits for it.
4. **The Touchpad and Motion nodes (claude #15).** The udev rule takes all
   three of the DualSense's input devices; inputproc opens one and drops
   touchpad and motion events entirely. After flag day the touchpad stops
   moving the cursor and the gyro reaches nothing, with no log line explaining
   it. Options are to narrow the rule or to forward those nodes; both are
   design.
5. **The `input` supplementary group (sol #10).** The unit joins `input` for
   `/dev/uinput` alone but thereby gains read access to every input device
   including keyboards. Tightening it means a udev-managed ACL or a device
   cgroup; worth doing, not urgent while the unit is uninstalled.

## Declined

* **sol #8 and claude's E1 criticisms** overlap on "the E-runbook's gates do
  not test what they claim". Correct, and being fixed in the runbook rather
  than the code — the gates were never the problem, the claims were.

## §Meta — what neither reviewer could do

Neither could run the suite in its sandbox (sol had no writable temp dir;
claude's worktree had no venv), so both reasoned statically about a process
that has never run outside the E1 rig. claude's finding 3 rests on INSTALL.md's
own `useradd --home-dir /nonexistent` plus systemd's documented behaviour
rather than on an installed unit — I confirmed the code half and the
INSTALL.md half, and the inference between them is sound but untested. The
fd-reuse coincidence behind claude #13 could not be constructed without a
device; the missing invariant is confirmed and now fixed regardless.
