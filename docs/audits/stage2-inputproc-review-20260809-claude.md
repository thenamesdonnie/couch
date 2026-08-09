# Lens 1 — stage 2 input process — claude review, 9 Aug 2026

Reviewer: an Opus subagent, blind. It worked in a detached git worktree
pinned to b72660b - the commit BEFORE sol's report was committed - so the
other reviewer's findings did not exist in the tree it could read. Same
prompt as the sol half, byte for byte below the worktree header.

**UNADJUDICATED.** Claims, not facts. The adjudication is in
`stage2-inputproc-review-20260809-synthesis.md`.

---


Scope: `couchd/inputproc.py`, `couchd/stage2/*`, `couchd/test_inputproc.py`.
Graded against live state read at review time: `owns.conf` = `COUCHD_OWNS="gestures"`;
`shadow/status.json` mode `acting`, owns `["gestures"]`, pad region `absent`;
switcher `settings.xml` (Flatpak profile) = `tap=home, double_tap=switcher,
hold=context_menu, hold_release=none, long_hold=none`.

---

## 1. Flipping `input` blinds BOTH gesture stacks, and the replacement wire is a stub

`couchd/inputproc.py:63` (`SUPERVISOR_SOCK`, defined and never used), `:523-538`
(`report()`, explicitly "STUB - the couchd supervisor socket ... is a LATER
wire-up"), against `couchd/couchd.py:3407-3409` and `:3476` (PadObserver opens
`/dev/input/eventN` read-only) and `couchd/README.md:140` (`| input | *(stage 2's
input process)* | — |` — the "script that yields" column is empty).

**Defect.** Nothing anywhere consumes inputproc's gesture output: `grep -rn
inputproc` over the repo finds only `gesture.py`'s comments, `todo.md`, and the
tests; `tools/shadow-diff` has no reference to `inputproc` or `input`. So the
moment inputproc owns the pad, the PS-button vocabulary has no path to any
executor.

**Scenario.** Flag day, INSTALL.md step 9: the udev rule is armed
(`OWNER=root GROUP=couchd-input MODE=0660`, uaccess stripped) and `systemctl
enable --now inputproc` runs. couchd runs as ds2000; `PadObserver._rescan`
(`couchd.py:3476`) now gets `PermissionError` and logs `no permission (dualsense
udev rule?)`, so the `pad` region sits at `absent` forever — and even with the ACL
present, `EVIOCGRAB` would starve it. The legacy `pad-home-watcher` reads the same
node and dies the same way. `owns.conf` still says `gestures`, so couchd is the
declared executor of tap=home / double_tap=switcher / hold=context_menu, and it
receives zero BTN_MODE events. Result: PS button completely dead in the living
room, with `status.json` reporting `mode: acting, owns: [gestures]` and no error.
The only thing the pad still does is the re-injected guide chord into the virtual
X360 pad, which Kodi will interpret with its own buttonmap.

**Severity: CRITICAL. CONFIRMED.**
The declared "combined cutover with gestures" (owns.conf comment, stage-2 SR4) is
precisely what makes this fatal rather than latent: `gestures` is already flipped
and live. Nothing in INSTALL.md step 9 or E-runbook E1 checks that a gesture still
reaches an executor after the grab.

---

## 2. The unit hardcodes `COUCHD_OWNS=input`, so `owns.conf` is not the switch and emptying it does not roll back

`couchd/stage2/inputproc.service:34` (`Environment=COUCHD_OWNS=input`),
`couchd/inputproc.py:214-218` (`owns()` reads `os.environ`), `:1060`
(`args.own_input = owns('input') and not args.observe`, evaluated once in `main`).

**Defect.** `owns.py`'s module docstring — "the ONE file both stacks read at
runtime", "read fresh (stat-cached) on every couchd tick and every legacy
decision, so a flip - or a rollback to empty - takes effect within a tick with no
restart of anything" — and its `RESPONSIBILITIES` comment ("`input` is stage 2's
(the input process reads it)") are both false for stage 2. inputproc never opens
`owns.conf`; it reads an environment variable that the unit pins to `input`
unconditionally, once, at process start.

**Scenario.** Evening, something is wrong, Donnie follows the charter rollback in
`owns.conf`'s own header: "ROLLBACK, in order: empty this file FIRST (both stacks
pick it up within a tick, nothing restarts)". couchd stops acting on gestures
within a tick; legacy's `owns.owns()` lease also goes false and legacy resumes —
except neither can read the pad, because inputproc is still grabbing it and the
udev rule still hides it. The documented rollback makes the console *worse*: it
removes the only executor while the grab stays. The correct rollback is a
different, undocumented-in-owns.conf command (`sudo couchd-input-release`), and
`shadow/status.json` will never list `input` in `owns` because couchd, not
inputproc, writes that file.

Second-order: `status.json`'s `owns_declared` vs `owns` distinction
(`README.md:176`) exists specifically so the record can say `input` was declared
but not executed by stage 1 — but with the switch in the unit, `input` can be
*executing* while `owns_declared` never mentions it. The evidence record is then
wrong about who owned the pad.

**Severity: CRITICAL. CONFIRMED.**

---

## 3. Every JSONL record inputproc writes at flag day is silently discarded

`couchd/inputproc.py:60-63` (`HOME = os.path.expanduser('~')`; `SHADOW_DIR =
os.environ.get('COUCHD_SHADOW_DIR', os.path.join(HOME, 'couch', 'shadow'))`),
`:429-455` (`JsonlLog.__init__` swallows `OSError` from `makedirs`, `write`
swallows `OSError` from `open`/`write`), `:1041` (`--log-dir` default), against
`INSTALL.md:37` (`useradd --system ... --home-dir /nonexistent couchd-input`) and
`inputproc.service:29,36,46`.

**Defect.** The unit runs as `User=couchd-input`, whose passwd home is
`/nonexistent`. systemd sets `$HOME` from passwd, so `expanduser('~')` is
`/nonexistent` and `SHADOW_DIR` becomes `/nonexistent/couch/shadow`. The unit sets
neither `COUCHD_SHADOW_DIR` nor `--log-dir`; `WorkingDirectory` does not affect
`expanduser`. `makedirs` fails (cannot create `/nonexistent` as a non-root user)
and is swallowed; every `write()` fails to open and is swallowed. There is no
error path — `JsonlLog` is designed to never raise.

**Scenario.** Flag day. `journalctl -u inputproc -f` shows the `say()` lines
(those go to stdout as well as the file), so it looks healthy. But
`~/couch/shadow/inputproc-YYYYMMDD.jsonl` is never created, so E-runbook E1.5's
`grep '"kind": "gesture"' ~/couch/shadow/inputproc-$(date +%Y%m%d).jsonl`, E1.6's
FF-map cross-check and E1.7's `p99_ms` gate all read a nonexistent file. The
flag-day acceptance has no evidence at all, and the SR7 FF map and the SR6
persistence transitions become unobservable. This is invisible during E1 because
E1 runs as ds2000, where `$HOME` is right.

The unit's `ReadWritePaths=/home/ds2000/couch/shadow` (`:46`) and INSTALL.md
step 5's two `setfacl` lines on that directory are dead weight — they grant access
to a path the process never names.

**Severity: CRITICAL** (corrupts the evidence machinery the flip is gated on).
**CONFIRMED** in the code; the `$HOME=/nonexistent` premise is INSTALL.md's own
`useradd` line, not observed on the box (the unit is not installed).

---

## 4. SR4 divergence: `poll()`'s latched `hold_fired` overrides the true kernel duration — stage 2 says hold-release where stage 1 says tap

`couchd/inputproc.py:994` (`if self.own and self.tracker.poll() == gesture.HOLD`),
`couchd/gesture.py:348` (`was_hold = self.hold_fired or self.long_hold_fired`) and
`:353` (`if was_hold or not is_tap(...)`), against `couchd/couchd.py` which calls
`tracker.poll()` nowhere (only `steam.poll()`, `triggers.poll()`, `kodi.poll()`).

**Defect.** `poll()` decides on `kernel_now()` — the kernel clock *extrapolated
with wall time* since the last event. Once it latches `hold_fired`, the shared
`feed()` classifies the eventual release as `HOLD_RELEASE` **regardless of the
release's real kernel timestamp**. Stage 1 never polls, so `hold_fired` is always
False there and the same release is classified purely by `press_duration`. Same
kernel timestamps in, two different gestures out.

**Scenario** (reproduced against the worktree's `gesture.py` with synthetic
timestamps, no device):

```
press  kernel k=1000.000, read at wall 500.00
release kernel k=1000.850  (0.85s — a TAP by both stacks' arithmetic)
        but inputproc's loop is stalled and reads it at wall 501.10
stage 2: poll(wall=500.90) -> HOLD   ; feed(1000.85, 0) -> 'hold-release'
stage 1: (never polls)               ; feed(1000.85, 0) -> 'tap'
press_duration = 0.85, is_tap = True in both.   => DIVERGENT
```

Required stall is only `0.9 - press_duration` wall-seconds between the release
arriving and inputproc reading it — for a 0.88s press, 20ms; one scheduler slice
under a game launch. Consequences with tonight's bindings: couchd fires
`tap=home` (raises Kodi) while inputproc classifies a hold and therefore **never
re-injects the withheld guide press** — the button is eaten. It also compounds:
stage 1's tracker arms `last_tap_ended_k` (a tap), stage 2's disarms it
(`gesture.py:355`), so a second press within 0.35s is a `double-tap` → switcher
for stage 1 and a plain re-injected tap for stage 2.

**Severity: CRITICAL** (SR4 is the invariant the combined cutover rests on, and
`gestures` executes live). **CONFIRMED** — divergence reproduced; the field
trigger (a ≥20-250ms loop stall) is inferred, not measured.

---

## 5. inputproc knows nothing about the bindings, so `hold=none` makes it swallow every long press

`couchd/inputproc.py:505` (`self.tracker = gesture.PressTracker()` — no
`long_hold_seconds`, no `gestureconf`), `:847-850` (`HOLD_RELEASE` → report only,
never re-injected), against `couchd/couchd.py:541-549` (`g_hold_fires` =
`o.binding('hold') != 'none' and g_hold_reached(o)`) and its comment at `:544-547`
("With `hold` set to Nothing the press must stay in 'down' long enough for the
long-hold tier to see it").

**Defect.** Stage 1's hold is binding-gated; stage 2's is not. With `hold=none`,
stage 1 leaves a 1.5s press in `down` and releases it into `tap-wait` — a TAP.
Stage 2's `feed()` returns `HOLD_RELEASE` and the press is never forwarded to the
virtual pad. `gestureconf`'s precedence rule makes `hold=none` a *supported and
documented* configuration (it is the only way to enable `long_hold`), and it is
one dropdown on the Couch Switcher settings page.

**Scenario.** Donnie sets `hold=none, long_hold=quit_game` on the settings page
(the pairing gestureconf exists to support; `hold_release` and `long_hold` are
already exposed there and currently `none`). He presses PS for 1.5s. couchd's
region reaches `tap-wait`, `g_tap_window_fire` fires 0.35s later, `tap=home`
executes. inputproc classified it `ps-hold-release`, so no guide press ever
reaches Kodi or the game — and if `tap` were also `none`, the press does nothing
at all, anywhere, forever, with the log recording a hold that no stack acted on.

**Severity: HIGH** (latent today because `hold=context_menu`; one settings change
away, and the settings page is the sanctioned way to change it). **CONFIRMED.**

---

## 6. The handoff timeout is unreachable — a pad that drops mid-hold is silently dropped

`couchd/inputproc.py:999-1003`:

```python
if (self.own and self.hold_pending and not self.tracker.button_down
        and gesture.handoff_overdue(mono - self.gesture_at)):
```

**Defect.** The guard is self-contradictory. `hold_pending` is set only on `DOWN`
(`:833`) and cleared on *every* release outcome (`:841`, `:848`) and in `detach()`
(`:784`). `button_down` is cleared only by a release event or by `tracker.reset()`
— which `detach()` calls immediately before clearing `hold_pending`. So
`hold_pending and not button_down` is never simultaneously true: while the release
is missing, `button_down` stays True; once anything clears `button_down`,
`hold_pending` is already False. The branch — commented "the release that never
came" — is dead code.

**Scenario.** Bloodborne is running. Donnie holds PS to open the context menu; at
1.2s the Bluetooth link drops mid-press (this box has a documented L2CAP fault and
a patched `bluetooth.ko`). `on_physical_readable` gets EOF → `on_loss` → `detach`
→ `tracker.reset()` + `hold_pending = False`. inputproc emits `all_keys_up` and
holds the virtual node for 120s. No `ps-hold-release` and no
`ps-hold-release-timeout` is ever reported; the withheld press is discarded with
no record that a hold was in flight. `gesture.HANDOFF_TIMEOUT` — which exists
"precisely BECAUSE no further kernel events are coming (a dead pad mid-hold)"
(`gesture.py:14-16`) — is imported and never usefully applied.

**Severity: HIGH. CONFIRMED.**

---

## 7. SR5's ownership assertion terminates the process instead of degrading, and the unit then gives up permanently with the pad still hidden

`couchd/inputproc.py:730-732` (`if self.own and self.args.assert_ownership and not
self.check_ownership(path): dev.close(); raise SystemExit(3)`) against
`check_ownership`'s own contract at `:750-752` ("On failure REFUSE to own, log
loudly, **leave the legacy stack enabled** - never half-own the pad") and
`inputproc.service:23-24,38` (`StartLimitBurst=5`, `StartLimitIntervalSec=300`,
`Restart=on-failure`, `RestartSec=2`).

**Defect.** The documented behaviour is "refuse to own" — i.e. keep running as a
forwarder. The implemented behaviour is `SystemExit(3)` from inside `attach()`,
which is also called from the 1Hz rescan path in `loop()` (`:1011`), so it kills a
*running* process, not just a starting one. Five failures inside 300s (10s at
`RestartSec=2`) and systemd stops restarting.

**Scenario.** Post-flag-day, the pad reconnects over Bluetooth. udev has processed
the `add` event but logind has not yet finished revoking the previous uaccess ACL,
or a distro update reinstates `71-dualsense-uaccess.rules` ordering: `getfacl`
still shows `user:ds2000:rw-`. `check_ownership` fails, `SystemExit(3)`, restart,
same result — five times in ten seconds, unit dead. Now: the udev rule is still
armed, so the pad is `root:couchd-input 0660` with no ACL; ds2000 cannot open it;
couchd's PadObserver logs `no permission`; legacy's watcher likewise; inputproc is
gone. **No process on the box can read the pad**, and there is no virtual pad
either. Recovery is `sudo couchd-input-release` — which is on the cheat sheet, so
this is survivable, but it is a self-inflicted total input loss triggered by a
transient permission race, from a code path that E1 never exercises (E1 runs with
`--no-ownership-assert` by construction, E-runbook.md:169-176).

**Severity: HIGH. CONFIRMED** (code path); the udev/logind race that triggers it is
PLAUSIBLE rather than observed.

---

## 8. `evaluate_ownership` passes when `getfacl` is missing, and never checks the device OWNER

`couchd/inputproc.py:399-406` (`read_acl` returns `''` on `OSError`) and `:194-211`
(`if acl_text and re.search(...)`), plus the absence of any `st_uid` check in
`evaluate_ownership`.

**Defect (a).** The module's own comment says "`getfacl` is the truth" and
explicitly rejects `udevadm info TAGS` as a false-pass. But if `getfacl` is not
installed (the `acl` package), `read_acl` returns `''`, the `if acl_text` guard
short-circuits, and the ACL check is skipped **silently** — `check_ownership` logs
`ok: true, problems: []`. The one check that stands between Steam and the pad
fails open, with no warning, on exactly the failure mode the code was written to
avoid.

**Defect (b).** Only `st_gid`, mode bits and named-user ACL entries are checked.
A device owned by `ds2000` with mode `0660` passes: `getfacl -cE` renders the
owner as `user::rw-`, not `user:ds2000:rw-`, so the regex at `:209` (anchored on
`^user:ds2000:`) does not match, and `(mode & 0o060) == 0o060` and `not (mode &
0o006)` both hold. INSTALL.md step 7's *human* procedure catches this (`ls -l`
must show `root couchd-input`), but the automated assertion does not. Named-group
ACLs (`group:input:rw-`) and other named users are likewise unchecked.

**Scenario.** A future edit or a distro rule drops `OWNER="root"` from
`72-couchd-own-dualsense.rules` (the flag-day lines at `:49-50` are hand-edited on
the night, per INSTALL.md step 9.1). The pad comes up `ds2000:couchd-input 0660`.
`check_ownership` returns True, inputproc grabs — and Steam, running as ds2000,
can still open the node. Two grabbers race for the pad, which is the C27 violation
SR5 was written to make impossible, and the health record asserts `ok: true`.

**Severity: HIGH. CONFIRMED** (both are readable directly from the predicate).

---

## 9. E1.8's Kodi buttonmap gate points at paths Kodi stopped using on 8 Aug

`couchd/stage2/E-runbook.md:399-402`:

```python
roots = ['/home/ds2000/.kodi/userdata/addon_data/peripheral.joystick/'
         'resources/buttonmaps/xml/linux',
         '/usr/share/kodi/addons/peripheral.joystick/resources/'
         'buttonmaps/xml/linux']
```

plus the sanity note at `:422-425` ("the box already has a hand-made
`linux/DualSense_Wireless_Controller_13b_8a.xml` override in Kodi's userdata").

**Defect.** Kodi is Kodi 21.3 as a Flatpak since `27bc1d4` (8 Aug). Its profile is
`~/.var/app/tv.kodi.Kodi/data` — `couchd/kodiprofile.py` exists as "one place that
knows where Kodi's profile is" (`74ed172`) and documents at length that it is
neither `~/.kodi` nor `~/.var/app/tv.kodi.Kodi/.kodi`. The runbook hardcodes
`~/.kodi` and the distro addon path, neither of which the running Kodi reads;
under the Flatpak the shipped buttonmaps live inside the app image, not
`/usr/share/kodi`.

**Scenario.** Flag day, k=3 run 1, E1.8. Either it prints `RESULT: DOES NOT
RESOLVE` and the operator burns the evening chasing a virtual-pad shape that is
actually correct (`11b 8a` is right, `test_inputproc.py:88-96` pins it), or —
worse — it prints `RESULT: RESOLVES` off the leftover apt-Kodi tree and passes an
SR2 gate against a Kodi that is not running. Either way the gate does not test
what it claims. The `13b_8a` override the note cites as proof of the naming scheme
is also under the old profile.

**Severity: HIGH** (an SR9 gate that cannot pass, or passes falsely, on the
console's only reading of it). **CONFIRMED.**

---

## 10. The latency gate excludes the one path that does blocking I/O

`couchd/inputproc.py:800` (`now_wall = time.time()` — sampled *once, before* the
per-event loop), `:816` (`self.latencies.append(now_wall - k)`), `:807-809`
(BTN_MODE `continue`s out before ever reaching the append), against
E-runbook.md:158-166 and `:373-375` ("The number is kernel-timestamp-to-forward
inside this process only").

**Defect (a).** The sample is `read_time − kernel_time`. It contains no part of
inputproc's own work: `translate()`, `emit()`, the `os.write` to uinput, the FF
handling, the JSONL write. The gate's stated meaning ("to-forward") is not the
quantity measured; it is a pure delivery-latency measurement that would look
identical if `emit()` were a no-op.

**Defect (b).** `on_guide` returns before line 816, so **no BTN_MODE event ever
contributes a latency sample** — and that is the only path that calls `report()`,
which calls `say()` (`:463-472`: `open()` + `write()` + `close()` on
`/tmp/inputproc.log`, plus `print(..., flush=True)`) and `JsonlLog.write()`
synchronously inside the event loop. The single code path with blocking file I/O
in the hot loop is excluded from the budget by construction. E1.7 compounds this
by driving only `axis lx` traffic.

**Scenario.** E1.7 reports `p99_ms 1.4`, the gate passes three times, flag day
proceeds. In the room, every PS press pays two synchronous file opens plus a
journal write before the chord is queued, and that cost is unmeasured and
unmeasurable from the evidence.

**Severity: MEDIUM. CONFIRMED.**

---

## 11. `begin_upload` / `end_upload` / `begin_erase` sit outside the try — one FF ioctl error kills the input process mid-game

`couchd/inputproc.py:593` (`upload = self.ui.begin_upload(request_id)` — before
`try:` at `:595`), `:633` (`self.ui.end_upload(upload)` inside `finally`, itself
unprotected), `:638` (`erase = self.ui.begin_erase(request_id)`), `:659`.

**Defect.** The careful `except Exception` blocks inside `ff_upload`/`ff_erase`
guard the translation, not the uinput handshake. An `OSError` from `begin_upload`,
`end_upload` or `begin_erase` propagates out of `on_virtual_readable` → out of
`loop()` → to `run()`'s `finally`, which shuts the process down. There is no
try/except anywhere in `loop()`.

**Scenario.** Elden Ring uploads a rumble effect at the same moment the persistence
window expires and `destroy_virtual()` closes the uinput fd, or the game exits
while an upload request is in flight. `begin_upload` raises `OSError`. inputproc
exits, `Restart=on-failure` brings it back 2s later with a *new* uinput node — to
the running game that is a controller unplug followed by a different controller
plugging in, mid-fight, and Steam re-assigns the player slot. The `# never stall
the game` comment at `:628` is defeated by the two lines it does not cover.

**Severity: MEDIUM. CONFIRMED** (control-flow); the triggering ioctl error is
PLAUSIBLE.

---

## 12. `read_acl` forks a subprocess with a 2s timeout inside the single-threaded input loop

`couchd/inputproc.py:399-406` (`subprocess.run(['getfacl', ...], timeout=2.0)`),
called from `check_ownership` (`:759`), called from `attach()` (`:730`), called
from `loop()`'s rescan every `RESCAN_SECONDS = 1.0` (`:1009-1012`).

**Defect.** The ownership check runs *before* the grab on every attach, and
`attach()` is retried at 1Hz whenever `self.phys is None`. `subprocess.run` is
fully blocking: while it runs, nothing is forwarded and no FF request is answered.

**Scenario A.** The pad reconnects inside the persistence window. The virtual pad
is still live and a game may be mid-rumble. `attach()` blocks the loop for the
duration of a fork+exec+getfacl (and up to 2s if `getfacl` stalls on `/dev`),
during which UI_FF_ERASE requests go unanswered — the exact 30s-per-effect stall
SR7 exists to prevent, just moved one layer out.

**Scenario B.** A second inputproc is started by mistake (or the first is running
while the rule is not armed): `dev.grab()` gets EBUSY, `attach()` returns False
(`:736-742`), and the process forks `getfacl` once per second, indefinitely, with
no backoff and a `say()` line per attempt into `/tmp/inputproc.log`.

**Severity: MEDIUM. CONFIRMED.**

---

## 13. The chord's 80 ms spacing collapses whenever the loop stalls longer than the gap

`couchd/inputproc.py:863-868`:

```python
def drain_pending(self, mono):
    while self.pending and self.pending[0][0] <= mono:
        _, etype, code, value = self.pending.popleft()
        self.emit(etype, code, value); self.syn()
```

**Defect.** `mono` is sampled once at the top of the loop (`:960`). If ≥80 ms of
wall time passes between `inject_tap()` queueing `(T, press)` and `(T+0.080,
release)` and the next `drain_pending`, both entries satisfy `<= mono` and are
emitted back-to-back in one `while` pass with no delay between them. `CHORD_GAP`
exists precisely because "a synthesised press/release pair sent back-to-back is
dropped or coalesced by consumers" (`gesture.py:95-98`). The stall sources are in
this same file: finding 12's `read_acl`, finding 10's `say()`/JSONL writes, or
plain scheduler preemption under a game launch.

Related, same function: `pending` is never cleared by `detach()`, `on_loss()` or
`shutdown()`, so a queued press can be emitted *after* `all_keys_up()` — i.e. after
the "every button released, ONE SYN, then silence" guarantee at `:571-580`. The
matching release follows 80ms later so nothing sticks, but the S5/SR6 invariant is
violated as written.

**Severity: MEDIUM. CONFIRMED** (the collapse is unconditional given the stall);
the stall magnitude in the field is PLAUSIBLE.

---

## 14. The poller's fd→role map is never re-validated, so a reused fd number can be dispatched to the wrong handler

`couchd/inputproc.py:964-976`:

```python
for fd in list(registered):
    if fd not in want: poller.unregister(fd); registered.pop(fd)
for fd, which in want.items():
    if fd not in registered: poller.register(fd, select.POLLIN); registered[fd] = which
```

**Defect.** `registered` is keyed by raw fd number and its *role* is only written
when the fd is newly added. Closes (`detach()` at `:779`, `destroy_virtual()` at
`:585`) and opens (`attach()` at `:723`, `create_virtual()` at `:543`) both happen
in the tail of a single loop iteration (`:1004-1012`), before the map is
reconciled at the top of the next. If a closed fd number is re-issued for the
*other* role within that window, the map keeps the stale role and neither branch
corrects it: the fd is in `want`, so it is not unregistered, and it is in
`registered`, so it is not re-registered.

**Scenario.** The persistence window expires (`A_DESTROY`, `:1004-1008`) closing
the uinput fd `U`; on a later iteration `attach()` succeeds and `open_physical`
receives `U` as the lowest free descriptor (reachable when the old physical fd
number has been taken in the meantime — `JsonlLog`'s midnight day-rollover reopen
at `:446-451` does exactly that). `create_virtual` then takes a fresh fd. From the
next iteration on, `registered[U] == 'virt'`, so the *physical* pad's readiness
dispatches to `on_virtual_readable()`, which reads the (different) uinput fd, gets
`BlockingIOError`, and returns. The physical fd is never drained, so `POLLIN` stays
asserted: `poller.poll()` returns immediately forever. Net effect: virtual pad
present and healthy-looking, every button press ignored, 100% of one core burned,
`health` ticks reporting `grabbed: true` and `in` frozen.

**Severity: MEDIUM. CONFIRMED** as a missing invariant; the fd-number coincidence
is **PLAUSIBLE** and I could not construct it without a device.

---

## 15. The udev rule strips uaccess from the pad's Touchpad and Motion nodes, which nothing grabs and nothing forwards

`couchd/stage2/72-couchd-own-dualsense.rules:24` and `:49`
(`SUBSYSTEM=="input", KERNEL=="event*|js*", ATTRS{id/vendor}=="054c",
ATTRS{id/product}=="0ce6", ATTRS{uniq}=="<mac>"`), against
`couchd/inputproc.py:66` (`PAD_UNWANTED = re.compile(r'Motion|Touchpad')`) and
`:394-395` (`find_pad` returns only button nodes; `attach()` grabs `found[0]`).

**Defect / breadth.** The MAC scoping is correct and matches nothing but this pad
(I checked: no keyboard, no BT audio device, no other controller can match
vendor 054c + product 0ce6 + that uniq). The problem is the opposite of
over-breadth *within* the pad: the rule takes ownership of **all three** of the
DualSense's input devices — `DualSense Wireless Controller`, `... Motion Sensors`,
`... Touchpad` (see `test_inputproc.py:548-567`, which enumerates exactly these) —
but inputproc discovers and grabs only the first, and `translate()` drops all
touchpad and motion events (`:151-152`). So after the flip the touchpad and gyro
nodes are owned by `couchd-input`, read by nobody, and unreachable by ds2000.

**Scenario.** Flag day. The DualSense touchpad stops moving the Kodi/X cursor and
the gyro stops reaching anything, with no log line anywhere explaining it, because
the only process that can open those nodes never opens them. E1 does not detect
this: E1.4 exercises buttons, sticks and the hat on the main node only, and E1.3's
exclusivity check filters to `d.name == 'DualSense Wireless Controller'`.

Separately, `KERNEL=="event*|js*"` does not cover `mouse*`; the Touchpad input
device is not grabbed, so its mousedev node may keep delivering to `/dev/input/mice`
— an input path outside the fence. **PLAUSIBLE**, not verified.

**Severity: MEDIUM. CONFIRMED** for the ownership/no-reader gap.

---

## 16. E1's FF gate contradicts itself, and tests the kernel rather than `FFMap`

`couchd/stage2/E-runbook.md:165` (gate table: "FF suite | 20 uploads, updates,
erases — **no -ENOSPC, no stall**") versus `:315-322,344-346` (the step's own
success criterion: "`created 16 refused 4` — sixteen slots, and the seventeenth is
a clean refusal").

**Defect (a).** The gate table and the step disagree about whether ENOSPC is a
pass or a fail. An operator working from the table alone would abort a correct run.

**Defect (b).** `create_virtual` passes `max_effects=FF_SLOTS` (`inputproc.py:545`),
so the uinput kernel side refuses the 17th upload before the request ever reaches
`ff_upload`. `created 16 refused 4` therefore proves nothing about
`FFMap.can_create()` / the `-ENOSPC` branch at `:602-607` — that branch is
unreachable through this test, and would stay green if it were deleted. The
exhaustion invariant is only covered by `test_inputproc.py:214-225`, which
exercises `FFMap` in isolation.

**Severity: MEDIUM. CONFIRMED.**

---

## 17. The re-injected tap is unconditional, so with `gestures` owned a tap fires twice

`couchd/inputproc.py:836-846` and its comment: "A double-tap is still two taps as
far as the virtual pad is concerned ... Only the CONSUMER (couchd / the watcher)
reads the pair as one gesture, so nothing here has to know about the switcher."

**Defect.** couchd is not the only consumer of the virtual pad — Kodi and the
running game are, and they read it as a button. `inject_tap()` is gated on nothing:
not on the foreground, not on whether `gestures` is owned, not on the binding. The
comment's premise holds only while gestures are *not* owned by couchd.

**Scenario.** Tonight's bindings, Kodi foreground. Donnie taps PS. couchd's
gesture region reaches `tap-fired` and executes `tap=home` (raise Kodi +
`ActivateWindow(home)`, per `ddab8a4`). 80ms of chord also lands on the virtual
X360 pad as `BTN_MODE`, which Kodi resolves through
`Microsoft_X-Box_360_pad_11b_8a.xml` as the guide button — a second, independent
action on the window couchd just raised. On a double-tap, *both* taps are injected
(`:836`) while couchd opens the switcher: two guide presses into whatever the
switcher raises. Note the comment at `:838` also claims the pair is "spaced as they
arrived", which is not what `inject_tap` does — each press is flattened to a fixed
80ms and shifted to its own release time.

**Severity: MEDIUM. CONFIRMED** for the code; the room-level outcome depends on
Kodi's guide mapping, which I could not exercise — **PLAUSIBLE.**

---

## 18. The one NOPASSWD root grant permits arbitrary argv and the script resolves six binaries by bare name

`couchd/stage2/sudoers-couchd:15` (`ds2000 ALL=(root) NOPASSWD:
/usr/local/sbin/couchd-input-release`) and `couchd-input-release:27-62`
(`systemctl`, `mv`, `udevadm`, `sed`, and `udevadm info` all unqualified; no
`set -e`, no `PATH=` reset).

**Defect.** The header claims "It takes no arguments on purpose - there is no way
to turn it into a general-purpose root shell." A sudoers command spec with no
argument list permits **any** arguments; restricting to none requires
`/usr/local/sbin/couchd-input-release ""`. The actual safety comes from the script
ignoring `$@`, which is a property of the script, not of the grant — so the
comment's reasoning does not hold for a future edit that starts reading `$1`.
Independently, the script's root-privileged body depends entirely on sudo's
`secure_path` being compiled in; nothing in the bundle asserts it.

**Scenario.** Someone later adds `--force` or `--rule PATH` handling to
`couchd-input-release` (an obvious next step for the rig-vs-real rule swap), on the
assumption documented in the file that arguments cannot reach it. They do, as root,
without a password.

**Severity: MEDIUM. CONFIRMED** for the sudoers semantics; the escalation is
conditional on a future edit.

---

## 19. Rollback stops the unit but leaves it enabled

`couchd/stage2/couchd-input-release:27-32` (`systemctl stop`, no `disable`),
`inputproc.service:71-72` (`WantedBy=multi-user.target`), INSTALL.md:184
(`sudo systemctl enable --now inputproc`).

**Defect.** `couchd-input-release` disarms the udev rule (durable, survives reboot)
and stops the unit (not durable). The two halves of the flip therefore roll back
with different lifetimes.

**Scenario.** Something goes wrong at 11pm, Donnie runs `sudo couchd-input-release`,
the pad comes back, the evening is saved. The box reboots the next day. inputproc
starts (still enabled), `COUCHD_OWNS=input` from the unit, the rule is `.off` so
the pad still carries ds2000's uaccess ACL and group `input` →
`check_ownership` fails → finding 7's `SystemExit(3)` → 5 restarts → dead unit,
5 `REFUSING to own` blocks in the journal, and a `physical pad ... GRABBED`
attempt each time the pad appears. Benign but noisy; the failure mode is only
benign because finding 7 exits rather than half-owning.

**Severity: LOW. CONFIRMED.**

---

## 20. `test_couchd_and_inputproc_share_one_threshold` claims SR4 and pins three constants

`couchd/test_inputproc.py:412-418`:

```python
"""SR4 in one assertion: if these ever diverge, the shadow corpus stops
being comparable to what the owning process actually did."""
assert couchd.HOLD_SECONDS is gesture.HOLD_SECONDS
assert couchd.HANDOFF_TIMEOUT is gesture.HANDOFF_TIMEOUT
assert couchd.BTN_MODE == gesture.BTN_MODE
```

**Defect.** SR4 is "both stacks must decide identically", not "both stacks import
the same three numbers". `DOUBLE_TAP_S`, `LONG_HOLD_S`, `SETTLE_S` and `CHORD_GAP`
are unpinned, and — more to the point — no test anywhere feeds one event sequence
to both classifiers and asserts they agree. Findings 4 and 5 are both exactly the
kind of divergence this test's docstring promises to catch, and both pass it.

Coverage gap, same file: there is no test of `on_guide`, `inject_tap`,
`drain_pending`, `on_loss`/`on_reconnect` wiring, `attach`/`detach`, or the
poller loop. Every defect in findings 4, 6, 11, 13, 14 and 17 lives in untested
code. The pure layers (`FFMap`, `Persistence`, `translate`, `find_pad`) are tested
thoroughly; the layer that touches the pad is not tested at all.

**Severity: LOW** (hygiene, but it is why this file reached 9 Aug unreviewed with
findings 4 and 6 in it). **CONFIRMED.**

---

## 21. Smaller things

* `couchd/inputproc.py:733-741` — on a refused `EVIOCGRAB`, `self.phys` is reset to
  `None` but `self.phys_path` is left pointing at the device, so every subsequent
  `health` tick (`:910`) reports `node: /dev/input/eventNN, grabbed: false` as
  though a node were attached. **LOW, CONFIRMED.**
* `couchd/inputproc.py:822-825` — in observe mode the forwarded `BTN_MODE` gets its
  own `syn()`, splitting it out of the physical report it arrived in; a
  simultaneous PS+cross press is delivered to consumers as two reports.
  **LOW, CONFIRMED.**
* `couchd/stage2/E-runbook.md:454` — `ls /dev/input/by-id | grep -i x-box` as the
  "nothing left over" check: uinput devices do not reliably get `by-id` symlinks,
  so this passes whether or not a leftover virtual pad exists. Check
  `/proc/bus/input/devices` for `Microsoft X-Box 360 pad` instead. **LOW, CONFIRMED.**
* `couchd/stage2/E-runbook.md:427-443,458-461` — E1.9 (persistence) is marked
  "optional" and is excluded from the k=3 rule, yet the destroy→reattach path it
  covers is where finding 14 lives and is the mechanism SR6 exists for.
  **LOW, CONFIRMED.**

---

## Regions attacked and found sound

* **`FFMap` (SR7 bookkeeping).** bind/update/rebind/erase/`forget_physical` keep a
  true bijection through every ordering I could construct, `cached()` snapshots
  before mutation so `reupload_ff`'s iterate-and-rebind is safe, and
  `test_inputproc.py:186-291` genuinely pins it.
* **`Persistence` (SR6).** The three-state machine is correct and total;
  `on_reconnect`'s action ordering (`A_CREATE` < `A_KEYS_UP` < `A_REUPLOAD`) is
  right and pinned; `on_loss`/`tick` are idempotent.
* **DualSense→X360 translation.** The face-button swap is correct in the direction
  the comment claims (hid-playstation BTN_WEST=square → X360 X), `scale_stick` is
  monotonic, in-range and non-inverting across all 256 inputs, the digital trigger
  clicks are correctly dropped to preserve the `11b/8a` buttonmap name, and
  `virtual_capabilities` reproduces vpad exactly.
* **Grab/ungrab lifecycle on the exit paths.** I could not construct a path that
  leaves the device grabbed with a live process and no injector: every exit from
  `run()` passes through `finally: shutdown()` → `all_keys_up` → `detach` (ungrab)
  → `destroy_virtual`, `create_virtual` failing after a grab propagates to that
  same `finally`, and a second inputproc's refused grab degrades to a harmless
  rescan (its cost is finding 12). Process death by SIGKILL leaves nothing stuck:
  the kernel releases uinput keys on device unregister.
* **`find_pad` discovery.** Name filter, `Motion|Touchpad` exclusion, uniq scoping
  (case-insensitive both ways) and the missing-procfile path are all correct.
* **udev rule scoping and priority.** The 71 < 72 < 73 argument is right,
  `TAG-="uaccess"` before the uaccess builtin is queued is the correct mechanism,
  the getfacl-not-TAGS reasoning is right, and the evdev line cannot match anything
  but this one pad. The documented non-MAC-scopability of the hidraw line is
  correct.
* **`couchd-input-release` sequencing.** Stop the grabber, then disarm the rule,
  then reload+trigger+settle, then belt-and-braces per-device retrigger — the
  order is right and each step is idempotent.

---

## §Meta — what I could not verify

* **I could not run any test suite.** The worktree has no `couchd/.venv`, `evdev`
  is not importable from the system python, and the real venv lives under the path
  I was told not to read. Everything about `evdev`'s behaviour (`InputDevice`
  opening `O_RDWR|O_NONBLOCK`, `UInput.fd`, `begin_upload`'s error surface,
  `upload.effect.id` being kernel-allocated) is from the library's documented
  contract, not from reading the installed copy. I did exercise `gesture.py`
  standalone with synthetic timestamps, which is how finding 4 was reproduced.
* **inputproc has never run on this box outside E1**, so there is no runtime
  evidence for any of it. `shadow/status.json` shows `pad: absent` and no
  `inputproc-*.jsonl` is referenced anywhere. Findings 3, 7, 14 and 15 rest on
  static reasoning about a process that has never been installed.
* **`$HOME` for `User=couchd-input`** (finding 3) is inferred from INSTALL.md's
  `useradd --home-dir /nonexistent` plus systemd's documented behaviour of setting
  `$HOME` from passwd. I could not confirm it — the user does not exist on the box
  and the unit is not installed.
* **fd allocation order** (finding 14) cannot be constructed without a device; I
  report the missing invariant as confirmed and the specific coincidence as
  plausible.
* **udev matching semantics** for `KERNEL=="event*|js*"` alternation and
  `ATTRS{}` same-parent matching are from the udev man page, not tested; I could
  not run `udevadm test` (it would touch the live pad's routing).
* **Kodi-side consequences** of the re-injected chord (finding 17) and of losing
  the Touchpad/Motion nodes (finding 15) would need the console in front of me.
* I deliberately did not open `docs/audits/`, and I have not seen the other
  reviewer's output.
