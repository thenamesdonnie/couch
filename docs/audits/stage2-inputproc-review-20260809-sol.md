# Lens 1 — stage 2 input process — sol review, 9 Aug 2026

Reviewer: gpt-5.6-sol via Codex CLI 0.144.6, read-only sandbox, one shot.
Prompt: shared preamble (refreshed to 9 Aug live state) + Lens 1 mission,
per `docs/adversarial-review-gpt-sol.md`. 73,328 tokens.

**UNADJUDICATED.** Every line below is a claim, not a fact. Nothing here is
applied until a Fable session verifies it against the code and writes the
synthesis. The blind Claude half of the pair has not been run yet.

---

1. `couchd/inputproc.py:523` — gesture delivery to couchd is still a stub, while `PadObserver` only discovers physical devices named `DualSense Wireless Controller` (`couchd/couchd.py:3437`), so an input cutover removes couchd’s only gesture source. Scenario: enable `inputproc.service` with the real-pad rule → inputproc grabs the DualSense and creates an X360-named virtual pad → couchd cannot open the physical node and ignores the virtual node → inputproc records the hold only in JSONL instead of sending it to couchd → the currently live hold/context-menu gesture does nothing. **CRITICAL, CONFIRMED**

2. `couchd/stage2/inputproc.service:34` — the service unconditionally grants itself `COUCHD_OWNS=input` instead of reading `owns.conf` or participating in its heartbeat lease, bypassing the declared combined cutover and rollback machinery. Scenario: follow `INSTALL.md:184` while `owns.conf` still contains only `gestures` → merely enabling the service grabs the real pad and starts withholding PS events despite `input` never being flipped → legacy cannot see the pad and couchd receives no supervisor events → the room loses its entire PS-button vocabulary outside the ownership/evidence gate. **CRITICAL, CONFIRMED**

3. `couchd/inputproc.py:836` — each withheld tap is re-injected only after its own release, changing release-to-press timing and making physical and Stage-1 double-tap classifications disagree. Scenario using kernel timestamps: first press/release `100.00→100.10`, second press/release `100.30→100.50` → inputproc correctly classifies a double because the physical release-to-press gap is `0.20s < 0.35s`, but virtual chords occur approximately `100.10→100.18` and `100.50→100.58`, so couchd measures a `0.32s` gap here—and a slightly longer second tap, e.g. release at `100.55`, produces `0.37s` and two singles instead of one double. **HIGH, CONFIRMED**

4. `couchd/inputproc.py:869` — device loss does not clear queued re-injection events, allowing a disconnected pad to generate a phantom guide press after the all-keys-up frame. Scenario: a short press is released and `inject_tap()` queues guide-down/guide-up; Bluetooth disappears before the loop drains the queue → `on_loss()` emits all keys up → the next loop still drains the stale guide chord onto the retained virtual pad → Steam/game sees a PS tap after the physical controller has vanished. **HIGH, CONFIRMED**

5. `couchd/inputproc.py:555` — virtual write failures are swallowed without invalidating the virtual pad or restoring all keys up, so a partial re-injection can leave consumers with a permanently held guide button. Scenario: queued guide-down writes successfully, then the guide-up write raises `OSError` → `emit()` only logs and returns → the virtual device remains present and no retry or recovery frame follows → the game sees BTN_MODE held until a later disconnect or process restart. **HIGH, PLAUSIBLE**

6. `couchd/inputproc.py:994` — the polling path handles only `HOLD` and silently discards `LONG_HOLD`, breaking shared gesture semantics when the long tier is enabled. Scenario: configure hold=`none`, long_hold=`suspend_to_kodi`, then hold PS beyond three seconds → `PressTracker.poll()` returns `HOLD` at 0.9s and later `LONG_HOLD`, but inputproc reports only the former and ignores the latter → couchd never receives the configured escape gesture. **MEDIUM, CONFIRMED**

7. `couchd/inputproc.py:999` — the “release never came” timeout is unreachable because every path that makes `button_down` false also clears `hold_pending`. Scenario: the pad disappears after a hold fires but before release → `detach()` resets both fields at lines 783–784 → the timeout guard can never become true → no `ps-hold-release-timeout` reaches the future supervisor, contrary to the claimed missing-release handling. **MEDIUM, CONFIRMED**

8. `couchd/stage2/E-runbook.md:276` — E1’s gesture gate checks only inputproc’s local log and virtual single-tap output, so three green runs cannot detect the absent supervisor integration, deferred-dispatch disagreement, stale pending queue, or missing-release failure. Scenario: run E1.2–E1.8 three times exactly as written → tap/hold lines and X360 events satisfy E1.5 → the runbook declares all SR9 gates passed even though the actual couchd gesture consumer has received zero events and would fail immediately at cutover. **MEDIUM, CONFIRMED**

9. `couchd/stage2/E-runbook.md:399` — the Kodi-map gate still probes the removed distro profile and host `/usr/share/kodi`, not the active Flatpak profile resolved by `kodiprofile`. Scenario: Kodi’s X360 buttonmap exists only inside the Flatpak installation/profile → the virtual pad is correctly mapped live, but E1.8 reports `DOES NOT RESOLVE` and blocks certification based on obsolete paths. **LOW, CONFIRMED**

10. `couchd/stage2/inputproc.service:33` — membership in the broad `input` group gives the input process read access to unrelated input devices, including keyboards, rather than only `/dev/uinput` and the selected DualSense. Scenario: an inputproc bug or dependency compromise enumerates `/dev/input/event*` → it can read keyboard events despite its stated single-pad role; the unit’s device access is materially broader than required. **LOW, CONFIRMED**

Grab/ungrab paths found sound: normal exit and exceptions enter `shutdown()`, SIGKILL closes kernel-held FDs, refused/second grabs close their device without creating an injector.

Udev match scoping found sound: evdev/js ownership is vendor/product/MAC scoped; the deliberately broad all-DualSense hidraw match is explicitly disclosed and staged.

Sudoers bundle found sound: the NOPASSWD command is argument-free and targets a root-owned fixed rollback script.

Force-feedback bookkeeping found sound in the reviewed create/update/erase/reconnect paths.

**§Meta:** I could not execute pytest because the read-only environment exposes no writable temporary directory; I also could not exercise real EVIOCGRAB, udev ordering, systemd scheduling, Bluetooth disappearance, or partial `/dev/uinput` write failures without touching the live input stack. The live Flatpak gesture settings were verified directly: tap=`home`, double-tap=`switcher`, hold=`context_menu`.

---

## Spot-check of the two CRITICALs (Claude, same day — NOT the adjudication)

This is not the synthesis. It is a same-session check of whether the two
CRITICAL claims point at code that actually reads the way sol says, so the
findings can be triaged before the blind Claude half and the Fable
adjudication exist. Severity is left as sol graded it.

**#1 — gesture delivery is a stub, and couchd cannot see the virtual pad.**
Both halves hold. `couchd/inputproc.py:522-527` says so in its own docstring:
"STUB - the couchd supervisor socket ... is a LATER wire-up. Until then every
event lands in the JSONL and the human log". And the name filter is literal:
`couchd/couchd.py:134` `PAD_WANTED = 'DualSense Wireless Controller'`, matched
at `couchd.py:3445`, while `couchd/inputproc.py:81` presents
`VPAD_NAME = 'Microsoft X-Box 360 pad'`. After a cutover couchd's `find_pads()`
returns an empty dict and `report()` writes to a file nobody reads. Since the
`input` flip is declared a COMBINED cutover with `gestures`, and `gestures` is
the responsibility that is live tonight, this would take the PS button out of
the room at the moment of the flip.

**#2 — the unit self-grants ownership.**
Literal: `couchd/stage2/inputproc.service:34` is `Environment=COUCHD_OWNS=input`,
and `INSTALL.md` step 9.4 is `sudo systemctl enable --now inputproc`. Worth
adding to what sol found: `couchd/inputproc.py:214-217` reads `COUCHD_OWNS`
from **the process environment**, never from `couchd/owns.conf`, and
`inputproc.py:1060` resolves it **once at startup**. So two charter properties
do not reach stage 2 — `owns.conf` is not the one file both stacks read, and
emptying it is not a rollback for the input process. The documented rollback
(`sudo couchd-input-release`) exists and is one command, so this is a
divergence from the charter's rollback story rather than an absence of one.

Not checked here: findings 3-10.
