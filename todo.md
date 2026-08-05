# Couch — todo / resume

Phone-first web remote for the living-room Kodi box. Node/Express backend
(`server/`) brokering Kodi JSON-RPC + kodi-send + games/TV/lights, Svelte 5 +
Vite frontend (`web/`), served at `http://192.168.4.147:8790`. Runs as the
systemd **user** unit `couch.service` — never `node index.js` by hand (double-binds 8790).

Deep context lives in auto-memory: `~/.claude/projects/-home-ds2000-couch/memory/`
(`homelab-couch-app.md` = full build log, `couch-ios-ui-quirks.md` = the iOS gotchas).

## Build / deploy
- Frontend edit → `cd ~/couch/web && npm run build` then `systemctl --user restart couch`.
- Server-only edit → just `systemctl --user restart couch` (no rebuild).
- Build stamp shows in the theme sheet (`build YYYY-MM-DD HH:MM`) to confirm the phone loaded fresh.

## 🟡 DISK INCIDENT (5 Aug 14:57) - RECOVERED 15:36, watch phase

disk1 dropped offline under the Simpsons season-pack write load (second
RTL9210 dropout; first was during zip extraction). Donnie applied the
UAS quirk + rebooted 15:36: fsck clean, both enclosures now on
usb-storage, pool complete, qB prefs reverted, all six Simpsons packs
resumed. **Live experiment:** if it drops again on usb-storage it's
thermal, not the driver. GOTCHA found: couchd's WantedBy=
graphical-session.target never fires (lightdm autologin doesn't activate
the user target) so couchd does NOT autostart on boot - started by hand
15:41, unit fix belongs to the couchd session. Full detail in
auto-memory `homelab-usb-disk-dropout.md`.

## ▶ Resume here (updated 5 Aug 2026 ~15:40 — FIRST FLIP IS LIVE)

**`gestures` IS FLIPPED AND ACTING** (owns.conf, since 13:01). couchd
executes the PS-button vocabulary; pad-home-watcher yields and shadows it.
Rollback: empty `couchd/owns.conf` (instant), or `systemctl --user stop
couchd` (legacy takes it back within 30s via the heartbeat lease).
**Acceptance is still OPEN**: Donnie's evening pass is the gate.

Afternoon (commits f3ee617..bf34a27):
- Real-pad mini-test 13:56: 8 acted, 0 failures, switcher confirmed on
  screen. But it silently DROPPED one double-tap (see below).
- Synthetic pass in the fake-pad inhibit frame (14:07-14:15, TV never
  woke) found 3 bugs, all now FIXED in bf34a27:
  1. **Coalesced double-taps were silently dropped** (gating). Tap-1
     release + tap-2 press inside one ~50ms pass coalesce, the machine
     never reached `down-again`, no intent, no failure counter. Hit
     Donnie's own 48ms double-tap at 13:57:11. Fix: the table asks
     `gesture.PressTracker`'s decision (computed at the press in kernel
     time) from every state with a press in flight. Gaps 0/48/60/120ms
     all fire now; >=350ms correctly does not; multi-tap collapses to one.
  2. `show_switcher` had NO effect check and Kodi is the rate-limited
     observer, so an open dialog verdicted "unverified" forever. Added the
     check (window 12000) + targeted Kodi reads while a prediction is
     outstanding (0.5s floor).
  3. A no-session PS hold made couchd act where legacy does nothing. Now
     gated on `session_present`; "PS hold as universal return-to-Kodi"
     is a T5 candidate awaiting Donnie's ruling, NOT live.
  Plus: gestures that decide nothing now log `gesture-no-op` (a silent
  no-op is indistinguishable from a dropped press - that is how 1 hid).
- **Differ is post-flip aware**: reconstructs per-responsibility ownership
  windows, swaps roles when couchd owns (ACTED-ONLY/SHADOW-ONLY), never
  files yielded data as legacy-only, and prints an ACTING HEALTH block.
  First post-flip run: 12 acted, **0 gating divergences**, edge-to-decision
  **p95 97ms** vs the 250ms bound (Evening 1 baseline was 1445ms).
- `intents-archive.timer` (2 min) copies /tmp/legacy-intents.jsonl into
  shadow/legacy-intents-YYYYMMDD.jsonl - the last corpus that lived only
  on /tmp, which the 05:19 reboot ate mid-flip.
- Legacy bug 3 FIXED: tv-waker + pad-connect-daemon match a real DualSense
  by device name instead of any js* (Sunshine's virtual mouse held js0, so
  the TV silently stopped waking on pad connect). **`sudo systemctl
  restart pad-connect` still owed** to load it there.
- NEW legacy bug found live: Kodi can miss the BT-disconnect udev event,
  keep deleted fds, and never re-open the reconnected pad (dead controller
  in the UI). tv-waker now verifies Kodi holds the real node after each
  connect and toggles peripheral.joystick to force a rescan. Kodi's raw
  hotplug worked on all 3 later connects, so it is intermittent.
- Model fingerprint moved to `ecd01e9fdfa3` at 14:31. Tonight's pre-14:31
  rows read as stale-model; use `tools/shadow-diff --window` for a
  whole-evening read.

Late afternoon while Donnie was out (commits 500c6ae, 87c40fa):
- **Synthetic gesture sweep 15:22-15:25: 12/12 PASS, 0 action failures,
  TV never woke, frame restored, corpus clean.** `tools/gesture-sweep`
  (new, committed) drives fake-pad through the whole unexercised list:
  gap sweep 0/48/60/120/350ms (0/48 coalesce and take the bf34a27 edge
  from `down`, 60/120 walk `down-again`, 350 stays two singles), all 5
  switcher effects verdicted **confirmed** (0.8-1.7s vs the 3s deadline),
  no-session holds log their no-ops, tap-then-hold decides hold, stuck
  hold reaches release-never-came, 5-tap burst collapses to one switcher,
  uhid disconnect mid-hold survived acting on nothing. The bf34a27 fixes
  are end-to-end confirmed through the real acting daemon.
- Sweep review found a live-console fact worth knowing: **Kodi's own
  joystick layer opens the tv-poweroff context menu (10106) on every
  >=1s PS hold** (peripheral.joystick buttonmap + gamepad-poweroff.xml
  holdtime). Normal console behaviour, but the sweep dismisses 12000/
  10106 between scenarios and asserts nothing modal is left standing.
- fake-pad grew a `sleep` command (gap timing in the rig's own stream).
- **Legacy bug 5 FIXED**: server/sys.js + server/steam.js now identify
  the game via `game-pids` (Steam's reaper tree) instead of
  `pgrep -f steamapps/common` - the phone's suspend button can no longer
  SIGSTOP a bystander, and under Proton it now finds the real game
  (S:\ cmdlines never matched the old pattern). Errors fail safe.
  couch restarted on the fix; phone UI verified serving.
- Suites: 608 passing (couchd 430 + tools 178).

Review-fleet pass (~16:00-17:15, Donnie's "wire it in now then fix
everything else", commits a414699..d43fb75):
- Four Fable adversarial reviewers swept the codebase; every confirmed
  finding is FIXED except three design questions left for Donnie (below).
- **Guard wired in** (a414699): couchd's acted handoffs spawn the real
  steam-input-guard exactly where legacy's handoff_to_kodi did; the verb
  is pre-declared T5 in the differ (legacy's spawn was implicit).
- **couchd model** (99901a4, d43fb75): the whole coalescing family is
  closed with CONSUMABLE tracker markers (hold_release_k + double_tap_k,
  twins of double_armed but spendable) - a whole hold or whole double
  swallowed by stalled passes now decides from idle; escape verbs cap
  backoff at 30s; a failed step skips its same-pass dependents; freeze
  effects no longer count vanished pids as frozen; launch-resume has a
  real oracle; couchd declines to act on a stale own-heartbeat (closes
  the both-stacks window); rebind hazards closed; iconify waits for the
  pause snap; stale Steam routes can't justify guide presses.
- **Differ gates honestly** (e393061): action failures, missed effects,
  SHADOW-ONLY owner-inaction and pid-set-different repeats all gate now;
  crashed runs split correctly (the 05:19 freeze reads right); rollover
  seeds anchors from yesterday. "gating 0" finally means something.
- **Server** (0109a45): install() can't kill Steam under a session;
  phone suspend = full game-launch suspend; MJPEG backpressure; CSRF
  cover on POSTs; corrupt appinfo.vdf can't spin the loop; game-launch
  suspend/resume/quit serialize on a flock.
- **Rigs** (e921dac): fake-pad signal-safe + atomic claim; sweep
  re-checks safety before every press; intents-archive survives crashes.
- **The sweep caught two of my own regressions live** (16:59 burst, 17:02
  60ms) that 441 unit tests could not - both fixed, final sweep 12/12.
- Model fingerprint is now `d1adeed4083a` (several restarts this
  afternoon; tonight's differ read MUST use --window from ~17:10).

**NEXT:** (1) Donnie's evening pass = the acceptance for `gestures`;
(2) morning after: `tools/shadow-diff --window` over the evening (the
differ now gates on acting health too);
(3) then the next flip (`reconcile` argued next), one at a time;
(4) fault rig (needs him + a live game); (5) rulings: the three below
PLUS two new from the fleet: should hold=switcher defer its handoff to
release like suspend does (currently hands off mid-press, a pinned
earlier decision the review challenged), and should ACTED-ONLY differ
rows gate post-flip (currently hand-triage).

**Suites:** couchd 441, tools 213, gitleaks clean.

### TV upgrade (researched 5 Aug 2026, decision Donnie's)

**GPU swap-day is prepped (5 Aug):** base OS is already RDNA4-ready (Mesa
25.2, kernel 6.14, navi48 firmware present). Pre-staged: couch House GPU
card reads amdgpu sysfs when nvidia-smi is gone (cb102ca), whisper-asr
falls back to CPU int8 by itself, kodi-tv applies amdgpu TearFree
alongside the NVIDIA line, Sunshine auto-detects VAAPI (nothing pinned).
Swap day = fit card + PSU, then `sudo bash ~/gpu-swap/gpu-swap-9070xt.sh`
(purges NVIDIA stack, deletes the xorg.conf NVIDIA pins that would
black-screen X, installs TearFree conf + VA/Vulkan tools), reboot, run
the printed sanity checks. Revert path in the script header.

**GPU swap plan (researched 5 Aug, Donnie leaning yes):** 9070 XT into this
box (PSU swap needed, ~300W card), 4070 to the main PC. On Linux amdgpu can't
do HDMI 2.1 (4K60 max over native HDMI) BUT: (a) DP->HDMI 2.1 adapters are
proven at 4K120+HDR+VRR on AMD+LG OLED - buy BOTH the UGREEN 85564 (CH7218,
best, VRR needs a not-yet-mainlined kernel patch) and Cable Matters 102101
(works on stock 6.14, VRR firmware must be flashed from a Windows DP machine
= Donnie's main PC, some flicker reports); (b) AMD started landing OFFICIAL
native HDMI 2.1 FRL+VRR kernel patches mid-2026, expected in a released
kernel ~7.3/7.4, so the adapter is a bridge not a life sentence. AMD also
unlocks Kodi GBM HDR + gamescope HDR properly. Sequence: RAM freeze
investigation closed -> PSU+GPU swap -> display-stack work. Whisper ASR
(Bazarr) is CUDA today, needs CPU/Vulkan rework after the swap.

**Switch-day is prepped (5 Aug):** webOS backend built beside the Android TV
one; `tv`/`tv-waker`/couch House tab all flip over when
`~/.config/tv-remote/tv.json` exists. Day-one steps: plug in the LG, put it
on the LAN, enable Settings > General > Devices > External Devices > "Turn
on via Wi-Fi", run `tv-setup-lg` (accept the prompt on the TV), done.
Optional after: install Jellyfin from the LG content store for native 4K
HDR/DV, reserve the TV's IP on the router. Rollback: delete tv.json,
restart tv-waker. The webOS code is untested until a real LG exists.

The current 1080p60 Toshiba with no VRR is what parks stage 3. Any HDMI
2.1 + VRR set un-parks it. The 4070 + 5700X3D drives 4K60 comfortably
(DLSS for heavy titles; at 4K everything is GPU-bound so the CPU is never
the limit), and 4K120 + VRR is the actual upgrade worth paying for.

Shortlist, UK prices checked 5 Aug:
- **LG C5 42" - the pick for a small room.** Full gaming spec survives at
  42" (4x HDMI 2.1, 4K144, G-Sync + FreeSync + HDMI VRR, ~9ms lag);
  panel is 20-30% dimmer in HDR than 55"+ (no Brightness Booster), blacks
  identical. New floor today £749 (Crampton and Moore / Spatial); Richer
  Sounds £769 with code RSTV80 buys a **6-year** guarantee; John Lewis
  ~£729 list with a 10% member discount and **5-year** guarantee is the
  best route if live. Dipped to £611-656 in June, cycles roughly monthly.
- **Currys eBay refurb 42" C5 £597**, "excellent", 12-month warranty -
  cheapest way in, and below every live new price.
- **LG C5 55" £969 / 65" £1,499** if the room suits it. C6 (2026) is
  better (165Hz, ~20% brighter) but not £700 better.
- **Burn-in-proof alternatives:** Samsung QN90F 43" £589 (only non-OLED
  sub-50" with real HDMI 2.1; no Dolby Vision, hurts the Jellyfin
  library), TCL C8K 65" ~£1,199 (only 2x HDMI 2.1, no 55" in UK).
- **No-gaming budget baseline:** TCL C6KS 50" ~£400. Kills stage 3.
- Skip Samsung generally here: no Dolby Vision or DTS anywhere in range.
- Sub-50" TVs with real HDMI 2.1 barely exist: TCL/Hisense/Sony UK ranges
  start at 55" for 120Hz. The gap between "best £400 TV" and "cheapest
  real gaming TV" is only ~£200.

Burn-in worry is handled: TV off when idle + Kodi screensaver now set to
black at 5 min (was none at all). OLED is fine for this usage.

**When a TV lands, couchd/homelab work:**
1. Port the `tv` command + tv-waker from Toshiba to LG webOS network
   control (the RTX 4070 passes no CEC at all, so network control stays
   the mechanism; webOS does network + WoL well; Pulse-Eight USB-CEC
   adapter is the fallback).
2. Set the input label to "PC" or 4K text fringes (chroma subsampling).
3. Add TV-standby-on-idle: couchd already knows menu + no playback + pad
   absent, which is exactly the trigger.
4. Revisit stage 3 (gamescope) - it only pays off with VRR. Known
   blocker to check first: NVIDIA's Linux driver has documented
   HDR+VRR flicker inside gamescope above 1440p120, driver-side and
   TV-independent.
5. 10-min panel check inside the return window: full-screen colour
   slides via Kodi for dead pixels, banding, uniformity.

## ▶ Overnight mandate (5 Aug 2026 ~08:45) — DONE

**THE OVERNIGHT MANDATE IS COMPLETE** (6 commits, 0e1169f..f3ee617):
task 0 startup hang fixed (fifo blocking open + faulthandler), task 1
acting executor + COUCHD_OWNS lease + legacy yielding flip-ready and
adversarially reviewed (7 SEV-2s found and fixed, ships OFF, owns.conf
empty), task 2 x11 events unswallowed + gesture-edge decisions + 9/10 T5
catch-ups, task 3 Evening-1 replay (38 divergences closed, matched 93->138,
found 3 real T4s, ALL FIXED: conditional guide press, verified supersede
kill, shared repair cooldowns; differ got model-version staleness +
--window + honest verdicts), task 4 fault rig staged NOT run, task 5
suites 410+167 green + gitleaks clean + MORNING SUMMARY written.
**READ: docs/handoff-2026-08-04.md MORNING SUMMARY** (top) - Donnie's
daytime list and the three rulings. docs/replay-2026-08-05.md has the
replay analysis.

**THE BOX HARD-FROZE at 05:19** (idle, no logs, lights on / no ssh / no
video; power-cycled 08:05; first ever; 27h after the RAM swap). RAM
config is prime suspect - dmidecode check + BIOS stock speed test are
item 1 on Donnie's sheet. A 16-min graphical-session cycle at 04:41
remains unexplained (not agents, not updates, not lightdm). Everything
recovered green at boot; snapshots-20260805.jsonl has a NUL crash hole
(the differ now counts and skips those).

**NEXT (in order):** Donnie's daytime sheet (morning summary items 1-4),
then Evening 2 per the compressed gate plan below, then daytime flips one
responsibility at a time. Legacy scripts are mirrored in legacy-mirror/
(deploy = cp to ~/.local/bin). The couch server/web now show owns state
on the Screen-tab card.

**5 Aug daytime notes:** gestures FLIPPED live ~13:01 (first flip; couch
acceptance pending Donnie's pad pass). RAM is at stock 2667 (XMP off), so
the freeze wasn't a boosted profile; if a second freeze happens, BIOS
"Power Supply Idle Control = Typical Current Idle" + overnight memtest.
Kodi screensaver set to black @ 5 min (was: none) for OLED safety. TV
shortlist researched (LG C5 65" ~£1,499 is the pick, agent report in
session); when a TV lands: port `tv` command + tv-waker to LG webOS
network control, add TV-standby-on-idle (couchd knows menu+no-playback+
pad-absent), revisit stage 3 (mind the NVIDIA gamescope HDR+VRR flicker
issue above 1440p120).

## ▶ Previous resume block (5 Aug 2026 ~03:15 — after Evening 1)

**EVENING 1 IS DONE and it worked**: 9 real bugs found with Donnie on the
couch, 8 fixed live + 1 deliberately stopped (see below), differ v3's
verdict on the current-model window: 0 gating divergences across 76
matched decisions. couchd out-decided the legacy stack during a live race
(guard thawed a fresh freeze; couchd re-emitted the correct freeze).
Evidence: docs/handoff-2026-08-04.md + this file's 5 Aug changelog +
shadow/couchd-20260805.jsonl + /tmp/legacy-intents.jsonl (copy into
~/couch/shadow/archive/ before any /tmp cleanup!).

**THE AGREED DECISION (Donnie, 03:00): stop fixing legacy coordination
bugs — accelerate the cutover.** The remaining visible issue (tap-resume
menu/raise dance, ~5s, always converges) is the coordination class that
couchd deletes by construction; patching it further = reimplementing
couchd in bash. Interim workaround given: resume with A on the tile, not
PS tap.

**OVERNIGHT MANDATE (Donnie, 03:15): execute everything remaining toward
flip-readiness while he sleeps.** Boundaries: NO real-game launches or
anything that wakes the TV or makes noise overnight (tv-waker fires on
launch; he is asleep at home) — synthetic/fake-pad work uses the rig's
inhibit frame only; no COUCHD_OWNS flips without his daytime acceptance
(charter). The work list, in order:
0. **FIRST: couchd is stuck "activating" as of 03:05** — watchdog killed
   it ~03:00, restart hangs before sd_notify READY (last log line
   02:57:51, single thread). Diagnose the startup hang (run foreground,
   faulthandler/SIGABRT for the stack; suspect a blocking observer init —
   Kodi socket / Steam log seed / pad node — that lacks a timeout under
   tonight's new conditions: BP mode churn, paused game). Fix + add a
   startup watchdog test. A down shadow costs nothing tonight, but the
   overnight work needs it healthy.
1. **Acting executor** in couchd + COUCHD_OWNS plumbing + legacy yielding
   (watcher/guard skip responsibilities couchd owns; couchd write-through
   of /tmp flags per R5-17). Adversarial review before merge (charter).
2. **couchd daemon fixes**: x11 observer emits NOTHING (wire its event
   subscription — blocking window-enforcement flip); gesture-adjacent
   show/route decisions must ride the gesture edge not the 5s tick
   (p95 1.4s vs 250ms bound); model catch-up for all "couchd model
   catch-up pending" T5 notes (iconify, refreeze, supersede-kill,
   suspended-mid-window, BP ensure/adoption, desktop-overlay close,
   snapshot, show_switcher on paused double-tap, settle window).
3. **Replay Evening 1** through the updated model (recordings/ has the
   real corpus + snapshots + legacy intents) — diffs should drop to
   ~zero retrospectively; what remains is real and gets triaged.
4. **Injected-fault rig staged** (commands scripted, NOT run overnight —
   they need a live game; morning/daytime job, listed on his sheet).
5. Re-run full test suites + gitleaks; commit each stage; update
   docs/handoff sheet with a fresh "MORNING SUMMARY" section on top:
   what's flip-ready, what needs his daytime 5 minutes.
Charter rules stand: shadow until his acceptance, one responsibility per
flip, daytime flips, rollback = stop couchd + old stack intact.

## ▶ Previous resume block (4 Aug 2026, late night — couchd build session)

**READ FIRST: `docs/handoff-2026-08-04.md`** — the phone-readable sheet for
Donnie (what to test, the one command needed before pad use, the two
decisions only he can make). This block is the technical version.

**couch is now a GIT REPO** (standing risk closed). ~20 commits, history
born clean: all secrets scrubbed to `.env` (`server/config.js` reads env;
`data/secrets.json` legacy file still on disk, gitignored, deletable once
healthy), gitleaks-verified. Local only, no remote. `.env.example` current.

**LIVE on the box now** (all reversible; `systemctl --user stop couchd
pad-record` = back to 4-Aug-green, and that line is cheat-sheet line 1):
- `couchd.service` — stage-1 SHADOW daemon (`couchd/couchd.py`, 2.2k lines
  + `x11.py`). 7 observers, orthogonal state regions with `unknown`, pure
  `reconcile(observed)->intents`, invariants incl. owned-resources leak
  check, JSONL corpus in `shadow/`, `status.json`, Type=notify + watchdog,
  crash-loop-safe (Restart=on-failure/RestartSec=10/StartLimitBurst=5).
  Acts on NOTHING (only RecordingExecutor exists).
- `pad-record.service` — recorder, fixed: mtime-stamped markers at ~100ms,
  inline gzip, 14-day retention.
- Old stack instrumented (R3): watcher/game-launch/guard write machine
  intents to `/tmp/legacy-intents.jsonl` (log-only edits, behavior same).
- Phone: `/api/couchd/status` + Screen-tab couchd card.
- **Double-tap PS → TV switcher** (`script.couch.switcher` Kodi addon,
  versioned in `kodi-addons/`) and **gesture keybind settings** in Kodi
  (`couchd/gestureconf.py` is the single source both stacks read; safety
  rail forces a suspend_to_kodi binding). Both verified live tonight.

**NEXT (in order):**
1. **Donnie's couch pass** — checklist in the handoff sheet (his original
   pad checklist + the three new features). Every evening he uses the TV
   is shadow evidence toward the C9 gates.
   **AGREED 5 Aug: the compressed 2-evening gate plan.** The C9 unit is
   transition coverage, not calendar. Evening 1 = directed scripted pass
   (write the numbered phone-readable step list into the handoff sheet
   FIRST) + live differ triage between segments (expect T1 comparator
   artifacts, fix in-loop) + injected-fault runs with legacy repairs
   briefly paused (Donnie present = the charter's monitoring). Evening 2
   = clean re-run + 1h organic free play. Gates close → COUCHD_OWNS
   flips happen in a DAYTIME window, one responsibility at a time, 5-min
   couch acceptance each. Post-cutover, Donnie reports bugs by timestamp
   (the corpus has the full decision trace); each becomes a replay test;
   two unexplained regressions = auto-revert to shadow per charter.
2. **Morning after any evening:** `~/couch/tools/shadow-diff` (offline,
   never touches the TV). First real run: VALID, 0 divergences.
3. **Donnie's sudo session** (~10 min, `couchd/stage2/INSTALL.md`):
   couchd-input group + system user, udev rule (staged `.off`), rollback
   script + sudoers, inputproc.service, rollback REHEARSAL. Plus fix
   pad-connect-daemon + tv-waker's any-`js*` checks (see Open decisions).
4. Then E2 (Steam adopts the virtual pad; daytime, back up
   `~/.steam/debian-installation/config` first), then stage-2 flag day.

**Deferred to a daytime window:** psfuzz/chaos identity runs with couchd
live (M9), the `STEAM_GAMES_RUNNING` atom re-test with a game running.

## Changelog — 2026-08-04 (late night, couchd build session)
Notes: `docs/couchd-stage1-design.md` (C1-C31 + rulings R1-R8),
`couchd-stage2-design.md` (S1-S9 + SR1-SR9), `couchd-stage3-design.md`.
- **Stage 1 SHIPPED to shadow.** /build pass (3 research agents: parallel-run
  practice, reconciler/statechart architecture, console-daemon prior art) then
  2 adversarial reviews. Biggest ruling: the old stack ALREADY logs its
  decisions, so the planned effect-inference engine died and ~4k LOC became
  ~1k. couchd + `tools/shadow-diff` (22 tests) + 30→191 test suite.
- **Stage 2 designed and built synthetic-only.** InputPlumber evaluated per
  charter and DECLINED with receipts (root-only #202, crash-bricks-pad #582,
  20-month rumble TODO #224, no kernel timestamps); its udev technique,
  persistence and 80ms chord pacing ported instead. Review found 8 blockers
  (no-root claim unimplementable as written → system-user model; 0640 would
  have silently killed rumble; sudo-at-night rollback; rig would wake the TV).
  Built: `couchd/gesture.py` (shared), `inputproc.py` (grab + exact-vpad X360
  clone + full FF contract), `tools/fake-pad` (uhid DS5 rig with inhibit
  frame), `couchd/stage2/` install bundle. **E0 + E1-functional PASSED**:
  forwarding p99 0.065-0.17ms (10ms budget), FF contract live, PS tap
  re-injected at 80.3ms / hold swallowed, persistence machine, Kodi buttonmap
  resolves, face-button transposition confirmed on hardware.
- **Stage 3 PARKED** with a written decision record (nothing to win at
  1080p60 SDR; `~/gamescope-deps.sh` is wrong as staged, corrections in the
  note). Revisit on TV upgrade / in-repo packaging / stage 4.
- **Double-tap PS → TV switcher** and **Kodi gesture keybind settings**
  (Donnie's requests) shipped and verified live.

## Roadmap: couchd (agreed 4 Aug 2026 — build rules: docs/couchd-charter.md)
The accretion phase is over; the architecture is understood (see
docs/audits/console-robustness-2026-08.md = the requirements spec, and
tools/psfuzz.py + tools/chaos.py = the acceptance tests). Strangler-pattern
consolidation into one control-plane daemon; engines (Kodi/Steam/games) stay.
The TV must keep working at every stage. Start AFTER the physical-pad pass.
1. **couchd**: one daemon absorbing pad-home-watcher + game-launch +
   steam-input-guard + reconcile. Internal state machine (no /tmp flags),
   API socket for couch app + Kodi tiles, structured logs, events stream.
2. **Input ownership**: couchd exclusively grabs the DualSense (evdev grab +
   udev-hide hidraw from Steam), presents a virtual pad (uinput/uhid) to the
   focused app. PS button becomes ours by construction; guard war deleted.
   Tradeoff accepted: games see generic X360 pad (no DS gyro/haptics).
3. **Gamescope-nested games**: game launches wrap in gamescope (deps script
   staged at ~/gamescope-deps.sh, needs Donnie's sudo once). Frame pacing +
   contained fullscreen. EXPERIMENT: NVIDIA+X11 is gamescope's weak combo.
4. **Own session compositor** (smithay/wlroots): couchd becomes the session;
   Kodi + games are surfaces. Months; only if 1-3 leave us hungry.

**Publishing (agreed direction):** share as a reference project ("my console
setup"), not a product - killer README from the audit doc, positioned as
"console-ify the box you already have" (vs Bazzite's OS takeover; see the
why-not-Bazzite reasoning: patched bluetooth.ko, X11 click-through, SIGSTOP
suspend all need a mutable X11 box). PREREQS before anything public: git init
(private first), scrub secrets into .env + .env.example (kodi password in
kodi.js, qBittorrent creds in downloads.js, LAN IPs throughout) so public
history never contains them. couchd, once real, is the properly adoptable
core. Generalise (Android TV pairing UI etc.) only if it gets traction.

Older "watch it on the couch" items (media controls track):

1. **Media Session / lock-screen + Dynamic Island** — REWRITTEN to an endless
   silent live stream from the box (`GET /api/silent`, ffmpeg anullsrc); no
   scrubber by design (a faked finite track's position can't be synced and
   bounced). Working: lock screen + Control Center + Dynamic Island, correct
   play/pause. KNOWN TRADE-OFF (chosen): the silent stream pauses when the TV
   pauses so the icon is right, which means a *very long* idle pause can let iOS
   drop the Now Playing session. If Donnie would rather keep the notification
   through long pauses at the cost of a less-correct paused icon, flip
   `updateMediaSession` in `web/src/lib/state.svelte.js` back to keeping the
   stream playing. Truly having both needs a native app wrapper.
2. **End-of-stream glitch guard** (`server/index.js reassess`) — YouTube HLS/DVR
   streams can run past EOF with Kodi never stopping (clock ticks past duration,
   no video). Guard stops the player when `position > duration + 3`. WATCH: that
   it backs out cleanly on the next YouTube finish AND never cuts a normal video
   ~3s early (if it does, raise the +3 margin).
3. **Smart rewind** (`server/index.js /api/player/step`) — for streams, pauses →
   seeks → waits for the buffer (`Player.Caching`/`CacheLevel`) → resumes, so
   YouTube rewind comes back cleanly. Confirmed snappier. Local files unaffected.

## Open decisions / risks
- ~~Couch is NOT under version control~~ **CLOSED 4 Aug**: git init done,
  secrets scrubbed first, history clean.
- **Sunshine's virtual `js0` breaks pad reconnect + TV wake** (found 4 Aug).
  `pad-connect-daemon:34` and `tv-waker:39` both test `glob('/dev/input/js*')`,
  so ANY virtual joystick (Sunshine, vpad rigs, the uhid test pad) makes them
  believe the pad is already there. Immediate: `systemctl --user stop
  app-dev.lizardbyte.app.Sunshine.service`. Real fix (needs Donnie): test the
  DualSense's own node instead of any js*. Sunshine is enabled and returns on
  every login.
- **Three legacy bugs found by the shadow work, NOT fixed (Donnie's call —
  behavioral edits to live plumbing).** Pre-declared in the differ so they
  don't read as couchd faults: (a) pure Big Picture PS-holds never write
  `/tmp/game-suspended`, so reconcile takes the pad off Kodi ~10s later and it
  belongs to nobody; (b) games launched FROM Big Picture record appid as the
  literal string `"bigpicture"`, so that game's Kodi tile CLOSES it instead of
  resuming; (c) the guard's pidfile isn't removed on normal exit (couchd's
  owned-resources invariant flags it every tick).
- **Three `steam_app_*` window-class predicates are fragile identity
  assumptions** (steam-input-guard:272, screen.js:271 and :291). They dissolve
  as couchd absorbs those responsibilities (its observation is pid-first);
  only worth fixing sooner if gamescope ever un-parks.
- **No auth** (LAN-only by design). A rota-style login MUST be added before any
  Cloudflare-tunnel exposure (pattern in the ROTA memory:
  rota-app-cloudflare-tunnel, rota-app-accounts).
- **Dynamic Island / lock-screen scrubber** are as good as a web app gets; a real
  Live Activity or a synced progress bar would need a native iOS wrapper.

## Changelog — 2026-08-04 (evening, robustness audit)
Full audit: `docs/audits/console-robustness-2026-08.md`. Headline: **Proton
games never actually froze on suspend** (Proton maps the library to `S:` so
path-matching missed eldenring.exe; only wrappers froze). Fixed with
`~/.local/bin/game-pids` (reaper process-tree identity, shared by watcher /
game-launch / guard / couch server) - verified live, all 18 ER processes
freeze/thaw now. Added: watcher `reconcile()` standing repair loop (orphaned
session, stale flag, lost thaw, joystick drift, frozen-game-visible, ~10s),
guard SIGTERM cleanup, 5s ACL retry.
- [B] Physical-pad end-to-end pass of today's changes (Donnie, from the couch).
- [B] uhid DualSense emulation to synthetically test Steam's hidraw path (project).
- [B] game-pids: exclude transient reaper children that are not games (Steam
  redistributable installers) if a phantom session ever appears.
- [B] Optional: dedicated "rescue" button in couch app (Screen->switcher->Kodi
  already serves as the panic button).

## Changelog — 2026-08-04 (afternoon, state-aware screen switcher)
- **Screen tab's app switcher now speaks the console state machine** (server
  only, no rebuild): picking Kodi mid-game runs `game-launch suspend` (freeze +
  pad to Kodi + guard) instead of a raw X raise; picking a paused game resumes
  it; picking a running game re-focuses it properly. Raw raises could strand
  the box (frozen game on top / Kodi shown while the pad stayed with the game).
- `xinput.py windows` now returns `cls` (wm_class); `screen.js windows()` badges
  the suspended game "· paused" in the list.
- Backing this: `steam-input-guard` (new, ~/.local/bin) enforcement loop after
  every suspend/resume - closes Steam's invisibly-open BP menu (root cause of
  the "black screen + steam menu, controller stolen" bug), re-asserts the right
  window, thaws a game that should be running, and never lets a frozen game sit
  visibly on top. See homelab-console-setup memory for the full story.

## Changelog — 2026-08-04 (media controls + playback polish)
- **Media Session REWRITTEN to a live silent stream.** Journey: generated silent
  WAV in memory → grew it per content (memory blew up on films) → seeking a fake
  finite track to the real position always bounced (iOS reads position from the
  element's own clock). Terminal fix: `GET /api/silent` streams endless silent
  MP3 (ffmpeg anullsrc, `-re`, killed on disconnect); the client plays it as one
  reused, gesture-unlocked element. No duration → iOS treats it LIVE → no
  scrubber, nothing to bounce. Side effect: it now shows on the **Dynamic Island**.
- **Play/pause icon** — iOS reads the icon from the element's paused state, so the
  element mirrors the TV (play/pause). `optimisticPlayPause` now calls
  `updateMediaSession` so an in-app pause flips the lock-screen icon instantly.
- **YouTube auto-1.25x audio-loss FIXED** — applying tempo mid audio-init silenced
  the stream; now settle ~1.3s, apply, re-assert ~2.8s (`applyYouTubeDefault`).
- **Smart rewind + end-of-stream guard** — see Resume items 2 and 3.

## Changelog — 2026-08-03 (evening, UI polish + fixes)
- **Sheet/card animation FIXED.** iOS snaps `transform` on a `position:fixed`
  element nested in scrolled `<main>`. Fix: `lib/portal.js` moves every sheet to
  `<body>` before animating. Entrance JS-driven in `lib/anim.js`; bottom-sheet slide.
- **Exit animations** — `slideDown`/`fadeOut` `out:` transitions on every sheet.
- **Scroll-behind fixed with CSS** — `.scrim{touch-action:none}` +
  `.sheet/.dsheet/.chooser{touch-action:pan-y;overscroll-behavior:contain}`.
  Removed a `position:fixed` body lock that jumped the nav bar + left a grey strip.
- **Safe-area sheet padding** → `max(18px, env(...))` (killed a dead grey band).
- **Discover detail holds until loaded** — fetch + decode art (`img.js
  decodeImages`) before opening; tapped card spins. No piecemeal pop-in.
- **Custom in-app seek scrubber** (Playing.svelte) — `setPointerCapture`,
  `touch-action:none`, optimistic, throttled ~200ms live seeks. (This is the
  in-app bar; the lock screen has no scrubber, see 4 Aug.)
- **TV power toggle on the Remote page** — top row, blue when on, `/api/tv` on/off.
- **Volume row added to Now Playing** (Playing.svelte).
