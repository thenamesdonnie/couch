# couchd stage 2 — design note (input ownership)

Status: research complete; adversarial review done (findings F1-F22).
Constraints S1-S9 stand AS AMENDED by the rulings below — where a ruling
contradicts earlier text, the ruling wins. Stage 2 code is developed and
tested ENTIRELY against a synthetic uhid DualSense; the real pad's routing
changes only at a flag day with Donnie present.

## Adversarial review rulings (binding)

**SR1 (F1) — Execution model, honestly.** There is no no-root mechanism to
put a ds2000 process in a group ds2000 isn't in (measured:
`systemd-run --user -p SupplementaryGroups=` fails EPERM), and adding
ds2000 to couchd-input would re-admit Steam. The input process therefore
runs as a dedicated SYSTEM user `couchd-input` (system unit,
`User=couchd-input`, `SupplementaryGroups=input` for /dev/uinput), no
BindsTo=graphical-session (it idles safely when X is down). Factor 1
restated: **no root at runtime; root once at install** (group + udev rule
+ unit + sudoers drop-in) **and never at rollback** (SR3). couchd's
supervisor socket accepts SO_PEERCRED uid ∈ {ds2000, couchd-input};
gesture events flow input-process → supervisor.

**SR2 (F2, F12, F22) — Device correctness.** Udev MODE is **0660** (evdev
FF playback is a write()); the input process asserts W_OK at grab time and
fails LOUDLY if absent (python-evdev silently falls back to O_RDONLY).
Virtual pad ffbit = **FF_RUMBLE only** (the physical DualSense memless set
is the ceiling; advertising FF_PERIODIC without waveform bits fails
uploads at our own device; invariant: virtual ffbit ⊆ physical ffbit).
Virtual pad shape pinned to vpad's exact kernel-xpad clone: name
"Microsoft X-Box 360 pad", 11 buttons, 8 axes, analog Z/RZ triggers —
Kodi resolves buttonmaps by `<name>_<b>b_<a>a.xml` and ships
Microsoft_X-Box_360_pad_11b_8a.xml; E1 asserts that map resolves.

**SR3 (F3) — Rollback without sudo-at-night.** A NOPASSWD sudoers drop-in
scoped to ONE root-owned script (`couchd-input-release`: mv rule to .off,
udevadm reload + trigger, restore uaccess) installed at the same sudo
moment as the rule. Cheat-sheet line added verbatim. Flipping
COUCHD_OWNS=input off ALSO runs it (the rule alone un-flips nothing).
Phone switcher stays the pad-free escape (F7).

**SR4 (F4, F18, F19) — The coupled cutover, declared.** Owning input
necessarily takes gestures and the legacy watcher's sight with it:
flag day is a DECLARED COMBINED cutover of input+gestures, not a charter
violation by accident. Before it: reconcile() re-homes into couchd's
supervisor (needs no pad); the gesture arithmetic is ONE shared module
used by stage-1 shadow and the input process (corpus stays comparable;
comparator re-versioned and re-run on the archive per R5); the
controller_ui.txt press cross-check retires in favor of the input
process's own press counter + recorded stream. Per-consumer migration
table: pad-record's job moves into the input process (records the
grabbed stream); ps-button gains a send-via-couchd path; psfuzz/chaos
are PORTED to drive couchd and land BEFORE flag day (F21); watcher gets
the reconcile-on-PermissionError patch as a flagged pre-flag-day legacy
edit (Donnie decision — it's behavioral, outside R3's log-only license).
Unaffected (verified): pad-connect-daemon, tv-waker, pad-battery,
sys.js (sysfs/glob readers), guard, game-launch.

**SR5 (F5, F6) — Verification that survives updates.** TAG-= clears only
CURRENT_TAGS (udevadm info TAGS still shows uaccess — never use it);
verification is getfacl + CURRENT_TAGS. On every pad appearance the input
process asserts ownership (no ds2000 ACL, group couchd-input, rw); on
failure it REFUSES to own, logs loudly, leaves legacy enabled. The
71-dualsense-uaccess ordering dependency documented. SDL hint reworded:
protects SDL games couchd launches only; covering the Steam client means
taking over ~/.config/autostart/steam.desktop — its own scoped item with
rollback.

**SR6 (F7, F8) — Input process lifecycle spec.** System unit,
Restart=on-failure RestartSec=2 StartLimitBurst=5; crash =
controller-disconnect to the game (audit-failure-10 class reborn) —
status.json + couch app show "pad unowned" and the phone switcher is the
escape. Persistence spec: on BT loss emit all-keys-up + centered axes +
SYN once then silence; hold the node for a bound calibrated from
pad-connect.service's logged reconnect times; on give-up DESTROY the node
(free Steam's slot); on reconnect re-key and re-upload the cached FF
effects (F11 — otherwise rumble dies silently after any BT hiccup).

**SR7 (F9, F10) — Full FF contract.** UPLOAD-create (id -1 → map),
UPLOAD-update (translate id! or 16 slots exhaust), **UI_FF_ERASE**
(begin_erase/end_erase — unhandled, a closing game stalls 30s PER
EFFECT), EV_FF playback + FF_GAIN by mapped id. Every handler
bounded-time; FF handling never shares a blocking path with gesture/socket
work. Slot math verified safe (16 memless slots both sides, 1:1 map).
Rig test: upload 20, update, erase; assert no -ENOSPC, no stall.
(F9 confirmed: EVIOCGRAB doesn't block the grabber's own writes/uploads —
S3 is legal once 0660.)

**SR8 (F13-F17) — Rig safety is an inhibit SET, not a udev rule.** A uhid
DS5 on this box otherwise: wakes the TV and forces HDMI 2 (tv-waker polls
js* — its .off udev rule is irrelevant), blocks the REAL pad's only
reconnect path (pad-connect.service's usable() tests any js* — latent
stack bug, fix flagged), starts a pad-record recording (corpus
pollution), gets adopted by watcher/couchd/Steam (Steam writes a sibling
gyro vdf keyed on the fake MAC), and shows on the phone. The rig
therefore owns setup/teardown: inhibit tv-waker + pad-record +
pad-battery, assert TV state unchanged, assert recordings gained no
file, restore everything in finally. E1's scoping rule matches
ATTRS{uniq}=="<fake MAC>" ONLY (dry-run with udevadm test; assert the
real MAC AA:BB:CC:DD:EE:FF unmatched) — which means the LIVE rule is
never exercised by the ladder, so flag-day step 1 is a real-pad getfacl +
CURRENT_TAGS check. E2 reclassified: daytime, box token, Donnie-aware,
Steam config backed up (cp -a of config/) with restore line.

**SR9 (F20) — Stage-2 gates, since C9/R5 can't certify mechanism.**
E0: hid_playstation binds, 3 nodes + power_supply, BTN_MODE visible.
E1: forwarding latency p50/p99 reported (budget <10ms p99 added);
FF suite green (SR7); Kodi map resolves (SR2); scoped-rule dry-run clean;
k=3 consecutive clean runs. E2: Steam adopts virtual pad as first-class
(BP nav on real UI), routing latency vs C10's 250ms, press counter
matches sent presses. Each experiment carries a C12 timebox; the
flag-day checklist lives IN THIS DOC before flag day and includes:
real-pad ACL check, hot-unplug mid-game, BT reconnect under the patched
bluetooth.ko, Elden Ring rumble (unverified anywhere upstream), guard
deletion only one stage later (charter).

## What it does for the product (plain language)

Today the PS button is a war: Steam hears the real DualSense over hidraw
no matter what we do, so steam-input-guard exists to un-do what Steam does.
Stage 2 ends the war by ownership instead of enforcement: couchd's input
process becomes the only thing that can open the pad, and it presents a
virtual Xbox 360 pad to whatever should have input. The PS button is ours
by construction; the guard's menu-close battle is deleted, not won.
Accepted trade-off (roadmap): games see a generic X360 pad, so no
DualSense gyro/haptics/adaptive triggers — plain rumble is kept.

## Decision: build custom; adopt InputPlumber's techniques, not its daemon

InputPlumber (the charter's mandated candidate) was evaluated seriously
against v0.78.0 source. It IS this daemon, but adopting it loses on the
axes that matter for this box; the decisive factors:

1. **Root.** InputPlumber is root-only (issue #202 open 2 years), with
   auth_admin polkit on exactly the calls couchd needs, on a box where
   everything else is the user session. The custom path needs NO root
   anywhere (S1) — strictly better than the thing we'd adopt partly for
   its maturity. C30 cites InputPlumber's CVEs as the cautionary tale;
   adopting imports the tale.
2. **Crash bricks the pad.** Its hide mechanism is runtime chmod-000 +
   udev reload; unclean exit leaves the family's controller dead until
   manual repair (issues #582/#586, open). Our static udev rule is
   declarative: no runtime, crash-immune, rollback = rename to .off.
3. **Rumble.** Its DualSense hidraw output has `// TODO: handle effect
   duration` (issue #224, open 20 months, our exact device: multi-second
   stuck rumble). Our design never decodes effects at all (S3).
4. **Kernel timestamps.** Its D-Bus InputEvent(s,d) carries none; R4
   requires gesture arithmetic on kernel time. Grabbing evdev keeps them.
5. **Single arbiter (C27).** Adopting makes couchd a polkit client of a
   second root daemon whose bus policy upstream has a TODO to tighten.
6. **We'd use ~5%** (no profiles/LED/IMU/network/multi-device).

Ported from InputPlumber because they're earned knowledge: persist the
virtual pad across BT drop/reconnect so Steam keeps the controller and
player slot (their persist:true); 80ms chord event spacing with reversed
release order; clear virtual-pad state whenever ownership changes.

## Constraints

**S1 — No-root ownership topology.** Group `couchd-input`; the input
fast-path process (separate process per C22, ~200-400 lines python-evdev)
runs in it. Udev rule at priority **72** (before 73-seat-late.rules
queues the uaccess builtin — this beats InputPlumber's priority-96 +
chmod race):

    /etc/udev/rules.d/72-couchd-own-dualsense.rules
    SUBSYSTEM=="hidraw", KERNELS=="0005:054C:0CE6*",
      TAG-="uaccess", OWNER="root", GROUP="couchd-input", MODE="0640"
    SUBSYSTEM=="input", KERNEL=="event*|js*",
      ATTRS{id/vendor}=="054c", ATTRS{id/product}=="0ce6",
      TAG-="uaccess", OWNER="root", GROUP="couchd-input", MODE="0640"

Steam (ds2000) then cannot open the physical pad at all — hidraw AND
evdev — so there is no phantom pad and no SDL layer to fight. Add
0003:... variant if USB ever used. Staged as `.off` until flag day;
rollback line (mv to .off + udevadm reload/trigger) goes on the audit
cheat sheet. Needs Donnie's sudo once (rule install + group).

**S2 — Virtual pad.** uinput X360 (bus 0x03, 045e:028e, FF_RUMBLE +
FF_PERIODIC + FF_GAIN, ff_effects_max 16 — InputPlumber's exact recipe).
It gets ID_INPUT_JOYSTICK → uaccess → ds2000/Steam sees a first-class
controller; X360 has been a Steam Input first-class citizen since 2018.
Note the double virtualization (our X360 → Steam Input → Steam's own
28DE:11FF virtual pad → game): well-trodden by every handheld distro,
but the added latency is MEASURED in the rig, not assumed.

**S3 — Rumble by re-upload, never decode.** On UI_FF_UPLOAD at the
virtual pad: begin_upload, re-upload the same ff_effect to the PHYSICAL
pad's grabbed evdev node (kernel hid-playstation registers memless FF —
it handles duration/replay/stop), keep an effect-id map, forward
play/stop events by mapped id. Sidesteps InputPlumber #224 by
construction; zero hidraw writes needed.

**S4 — Gesture timing on kernel event timestamps** (R4 carried forward);
the input process does the 0.9s hold arithmetic itself and reports
gesture events to the supervisor over the socket.

**S5 — Persistence.** The virtual pad outlives BT drops; on pad
reconnect the same uinput node resumes (Steam keeps player slot). Grab
in a finally-released context (C27); stuck-button clear (all keys up +
SYN) on every ownership change and on teardown.

**S6 — Steam belt-and-braces.** SDL_GAMECONTROLLER_IGNORE_DEVICES=
0x054c/0x0ce6 injected into environments couchd launches (C23 activates
in stage 2) as defense against udev regressions after Steam/systemd
updates. Steam Input's DualSense support stays globally enabled (nothing
to bind = no behavior; unchanged if we roll back).

**S7 — The uhid test rig (audit item 18, finally).** Port hid-tools'
`PS5ControllerBluetooth` (kernel HID maintainer's own test emulator,
~complete: BT report descriptor, CRC-signed feature reports 0x05
calibration / 0x09 pairing / 0x20 firmware, uniq MAC, BT byte offsets).
Success oracle: hid_playstation binds, three input nodes + power_supply
appear. Lesson from InputPlumber #459 baked in: unhandled reports return
success, never error. /dev/uhid already carries a ds2000 ACL (sunshine
rule) — no root. Hazards: the fake pad matches the real pad's udev rules
and is visible to Kodi/watcher/Steam, so rig runs respect the existing
flag gates and 99-dualsense-tv.rules stays .off (it already is).

**S8 — Experiment ladder (all fake-pad, all flag-gated, TV-safe):**
E0: rig alone — fake pad binds, evtest shows BTN_MODE. E1: udev rule
scoped to the FAKE pad only + grab + X360 forward + FF re-upload,
verified with getfacl/evtest/jstest. E2: Steam sees only the virtual pad
(fake pad hidden by the scoped rule) — BP navigation, controller_ui.txt
routing, latency measurement. Flag day (real pad, Donnie home, daytime):
rule un-.off'd + input process enabled under COUCHD_OWNS="input"; his
couch acceptance checklist gates it; old guard stack stays installed.

**S9 — python-evdev**: apt has 1.7.0 (grab/UInput fine) but UI_FF_*
constants arrived in 1.9.1 → pip 1.9.3 into couchd's venv (gcc present).

## What could be wrong in ways tests won't catch

- Steam's behavior when the physical pad vanishes mid-session (vs never
  seen): rig E2 covers cold start; the hot-unplug path needs the flag-day
  checklist.
- Double-virtualization latency: measured in E2 (input-to-virtual-pad
  and virtual-pad-to-Steam-routing), against the C10 250ms perceptual
  bound and stage-2's own <10ms forwarding budget.
- BT DualSense quirks the rig can't reproduce (link-quality stalls,
  the patched bluetooth.ko interaction): flag-day checklist + fallback.
- Elden Ring rumble via X360 emulation: unverified anywhere — it's on
  the flag-day acceptance checklist explicitly.

## Sources

InputPlumber v0.78.0 source (manager.rs auto_manage, composite_device
InterceptMode/write_chord_events 80ms, udev/mod.rs hide pattern,
dualsense.rs FF TODO), issues #202/#224/#459/#582, PR #586; SUSE
advisory 2026-01-09 (CVE-2025-66005/-14338, fixed v0.69); hhd hide.py;
Valve 60-steam-input.rules (BT hidraw uaccess line 38); this box's
73-seat-late.rules semantics (measured); kernel hid-playstation.c
(memless FF, calibration); hid-tools sony_gamepad.py (2124-line DS5
emulator); Steam Input X360 support announcements; libmanette writeup
(28DE:11FF double virtualization). Full agent reports in session
transcripts, 4 Aug 2026.
