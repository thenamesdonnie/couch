# couchd stage 2 — design note (input ownership)

Status: research complete (adopt-vs-build evaluation done per charter);
awaiting adversarial review before the input-layer code is written. Builds
on docs/couchd-stage1-design.md (C22 topology, C27 ownership hygiene, C30
security, R1/R4 rulings). Stage 2 code is developed and tested ENTIRELY
against a synthetic uhid DualSense; the real pad's routing changes only at
a flag day with Donnie present.

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
