# E0 and E1-functional — the operator's runbook

Two experiments, both on the **fake** pad, both **no root**, both abortable
in one command. Everything below is run as ds2000. Nothing here touches the
real DualSense, the real pad's udev rules, or Steam.

`evtest` and `jstest` are **not installed on this box** and installing them
needs sudo, so every check below uses the couchd venv instead. That is not a
workaround, it is the point: the venv is what the daemon itself runs.

Shorthand used throughout:

    PY=~/couch/couchd/.venv/bin/python

**Before either experiment**

* the real DualSense must be **off** (hold PS 10s, or it is simply not on).
  The rig refuses to start otherwise — that refusal is a feature, not a
  problem to work around;
* two terminals. Terminal A holds the rig, terminal B does everything else;
* `tail -f /tmp/inputproc.log` in a third if you like watching things work.

**Abort, at any moment, from any step:** Ctrl-C terminal A. The rig's
`finally` restores tv-waker, pad-record and pad-battery, destroys the uhid
device, and tells you whether the recordings corpus gained a file. There is
no state left behind and nothing to undo.

---

# E0 — does a synthetic DualSense bind?

**Question.** Does `hid_playstation` bind to hid-tools' emulator on *this*
kernel, and do we get the three input nodes plus a power_supply that the
real pad produces?

**Gate (SR9).** hid_playstation binds; 3 input nodes + power_supply;
BTN_MODE visible in the event stream. Any one missing = E0 fails and E1
does not start.

**Timebox: 45 minutes.** Past that, stop and write down what bound and what
did not — a partially-binding emulator is a finding, not a failure to push
through.

### E0.1 — start the rig  *(terminal A)*

    ~/couch/tools/fake-pad up

**Success:** it prints, in order, the inhibit list, the recordings count,
then a block ending with three input nodes and `power_supply: present`:

    fake-pad: inhibited: tv-waker.service, pad-record.service, pad-battery.service
    fake-pad: recordings before: 4 file(s)
    fake-pad: creating uhid DualSense, uniq=de:ad:be:ef:fa:ce
    fake-pad: device up:
    uniq (MAC):   de:ad:be:ef:fa:ce
    input nodes:  3
      /dev/input/eventNN  'DualSense Wireless Controller'
      ...
    power_supply: present

**Failure modes and what they mean:**

| what you see | meaning | do |
|---|---|---|
| `REFUSING: a real DualSense is connected` | the real pad is on | turn it off, retry |
| `WARNING: device did not report ready` | hid_playstation did not bind, or bound partially | E0 FAILS — record `dmesg \| tail -30`, stop |
| fewer than 3 input nodes | driver bound but the descriptor is not being read as we expect | E0 FAILS |
| `power_supply: MISSING` | hid_playstation bound generically, not as a DualSense | E0 FAILS |

### E0.2 — is BTN_MODE really there?  *(terminal B)*

    PY=~/couch/couchd/.venv/bin/python
    $PY - <<'EOF'
    from evdev import InputDevice, ecodes, list_devices
    for path in list_devices():
        d = InputDevice(path)
        if d.uniq == 'de:ad:be:ef:fa:ce' and d.name == 'DualSense Wireless Controller':
            keys = d.capabilities().get(ecodes.EV_KEY, [])
            axes = [c for c, _ in d.capabilities().get(ecodes.EV_ABS, [])]
            print(path, d.name, f'{len(keys)}b {len(axes)}a')
            print('BTN_MODE present:', ecodes.BTN_MODE in keys)
    EOF

**Success:** one line, `13b 8a`, and `BTN_MODE present: True`.
(13 buttons is right for a DualSense: our virtual pad is the 11-button one.)

### E0.3 — does the PS button actually travel?  *(terminal B, then A)*

Start the reader first — it exits by itself after 20 seconds:

    $PY - <<'EOF'
    import select, time
    from evdev import InputDevice, ecodes, list_devices
    def kname(code):
        # NOT ecodes.KEY[code]: that dict holds KEY_* only and raises
        # KeyError on every BTN_* code, BTN_MODE included.
        n = ecodes.bytype[ecodes.EV_KEY].get(code, code)
        return n if isinstance(n, str) else '/'.join(n)
    dev = [InputDevice(p) for p in list_devices()]
    d = [x for x in dev if x.uniq == 'de:ad:be:ef:fa:ce'
         and x.name == 'DualSense Wireless Controller'][0]
    print('reading', d.path, '- press things now')
    end = time.time() + 20
    while time.time() < end:
        r, _, _ = select.select([d.fd], [], [], 0.5)
        if r:
            for e in d.read():
                if e.type == ecodes.EV_KEY:
                    print(f'{e.sec}.{e.usec:06d} {kname(e.code)} {e.value}')
    EOF

Then, in terminal B (a second tab) or A's sibling shell:

    ~/couch/tools/fake-pad press ps
    ~/couch/tools/fake-pad hold ps 1.2
    ~/couch/tools/fake-pad press cross

**Success:** `BTN_MODE 1` / `BTN_MODE 0` pairs appear with kernel timestamps,
and the hold shows ~1.2s between them. `BTN_SOUTH` appears for cross.

> **Axis and dpad commands are LEVEL, not edge.** The rig holds stick and hat
> state across commands, and evdev emits nothing when a value does not
> change. `axis lx 1` twice in a row produces exactly one event — the second
> is correctly silent. When a value seems "missing", check the current level
> before concluding anything:
>
>     $PY -c "from evdev import InputDevice, ecodes, list_devices; \
>     d=[InputDevice(p) for p in list_devices()]; \
>     d=[x for x in d if x.uniq=='de:ad:be:ef:fa:ce' and x.name=='DualSense Wireless Controller'][0]; \
>     print({ecodes.ABS[c]: i.value for c,i in d.capabilities()[ecodes.EV_ABS]})"
>
> Centre the sticks (`axis lx 0`, `dpad center`) before a run if you want
> every command to produce an event.

**Gate:** all three of E0.1/E0.2/E0.3 green = **E0 PASSES**.

### E0.4 — stop, and check the corpus  *(terminal A)*

    ~/couch/tools/fake-pad quit

**Success:** `recordings unchanged - corpus clean` and
`restored: tv-waker.service, pad-record.service, pad-battery.service`.

**If you instead see the `WARNING: the recordings corpus GAINED n file(s)`
banner:** delete exactly those files from `~/couch/recordings/` before any
comparator run. pad-record woke up and recorded a phantom pad; the corpus
is the evidence base for R5 and must not contain fiction.

---

# E1-functional — grab, forward, rumble, and how fast

**Question.** With the rig up, can inputproc take exclusive ownership of the
fake pad's evdev node, present the vpad-shaped X360 clone, forward the whole
stream correctly, honour the full FF contract, and do it inside the latency
budget?

**Gates (SR9).**

| gate | number | where it comes from |
|---|---|---|
| forwarding latency | **p99 < 10 ms**, p50 reported | stage-2 budget |
| FF suite | 20 upload attempts → **`created 16 refused 4`**, then updates, erases and 16 re-creates — **no stall** | SR7 |
| Kodi map | `Microsoft_X-Box_360_pad_11b_8a.xml` **resolves** | SR2 |
| repeats | **k = 3** consecutive clean runs | SR9 |

Sixteen is the whole slot count, so four refusals is the PASS, not a fault:
E1.6 spells out why. **Read "What E1 does NOT prove" at the bottom before
you read a green run as a green stage** — three of these four gates are
narrower than they look.

**Timebox: 2 hours per run.**

> **Why `--no-ownership-assert` appears below.** SR5's ownership assertion
> checks that ds2000 has *no* ACL on the pad. During E1 that check must
> fail by construction: `71-dualsense-uaccess.rules` matches on the device
> *name*, the fake pad has the same name as the real one, so udev gives
> ds2000 an ACL on it — and E1 is a no-root experiment, so we do not touch
> that rule. The flag is rig-only and inputproc shouts a warning whenever
> it is used. **Never pass it at flag day.**

### E1.1 — rig up  *(terminal A)*

    ~/couch/tools/fake-pad up

Same success criteria as E0.1. Note the event node it prints for
`'DualSense Wireless Controller'`; call it `$PAD` below.

### E1.2 — take the pad  *(terminal B)*

    PY=~/couch/couchd/.venv/bin/python
    COUCHD_OWNS=input $PY ~/couch/couchd/inputproc.py \
        --uniq de:ad:be:ef:fa:ce --no-ownership-assert --persist-secs 30

**Success:** four lines, in this order:

    inputproc starting (COUCHD_OWNS grants input: True)
    WARNING: --no-ownership-assert - SR5 ownership check is OFF. ...
    physical pad /dev/input/eventNN GRABBED uniq=de:ad:be:ef:fa:ce
    virtual pad up: Microsoft X-Box 360 pad 11b 8a ff=['FF_RUMBLE', 'FF_GAIN'] node=/dev/input/eventMM

**Failure modes:**

| what you see | meaning | do |
|---|---|---|
| `opened READ-ONLY - evdev fell back` | the node is not writable; FF would fail later | ABORT. This is SR2 catching exactly what it exists to catch |
| `EVIOCGRAB refused` | something else already grabbed it | find it (`ls -l /proc/*/fd \| grep eventNN`), stop it |
| `ff=[]` and the no-FF_RUMBLE warning | the emulator exposes no rumble | E1's FF gate cannot run on the rig; record it and continue with latency + Kodi only |

**Abort/rollback:** Ctrl-C. The grab is released in a `finally`, all keys go
up, and the virtual node is destroyed. The fake pad is immediately back to
ungrabbed.

### E1.3 — is the grab exclusive?  *(terminal C)*

    $PY - <<'EOF'
    from evdev import InputDevice, list_devices
    for p in list_devices():
        d = InputDevice(p)
        if d.uniq == 'de:ad:be:ef:fa:ce' and d.name == 'DualSense Wireless Controller':
            try:
                d.grab(); d.ungrab(); print('NOT EXCLUSIVE:', p)
            except OSError as e:
                print('exclusive (good):', p, e)
    EOF

**Success:** `exclusive (good)` — a second grabber gets EBUSY. If it prints
`NOT EXCLUSIVE`, inputproc did not actually grab and every downstream result
is meaningless. ABORT.

### E1.4 — the forward path, and the face-button trap  *(terminal C)*

Reader on the **virtual** pad:

    $PY - <<'EOF'
    import select, time
    from evdev import InputDevice, ecodes, list_devices
    def kname(code):
        n = ecodes.bytype[ecodes.EV_KEY].get(code, code)
        return n if isinstance(n, str) else '/'.join(n)
    v = [InputDevice(p) for p in list_devices()]
    v = [x for x in v if x.name == 'Microsoft X-Box 360 pad'][0]
    print('reading virtual', v.path)
    end = time.time() + 30
    while time.time() < end:
        r, _, _ = select.select([v.fd], [], [], 0.5)
        if r:
            for e in v.read():
                if e.type == ecodes.EV_KEY:
                    print('KEY', kname(e.code), e.value)
                elif e.type == ecodes.EV_ABS:
                    print('ABS', ecodes.ABS[e.code], e.value)
    EOF

Then drive the fake pad:

    ~/couch/tools/fake-pad press square
    ~/couch/tools/fake-pad press triangle
    ~/couch/tools/fake-pad press cross
    ~/couch/tools/fake-pad axis lx 1
    ~/couch/tools/fake-pad axis lx 0
    ~/couch/tools/fake-pad dpad left
    ~/couch/tools/fake-pad dpad center

**Success, exactly:**

| you pressed | the virtual pad must report |
|---|---|
| square | `BTN_NORTH` (which is an X360 pad's **X**) |
| triangle | `BTN_WEST` (which is an X360 pad's **Y**) |
| cross | `BTN_SOUTH` (**A**) |
| `axis lx 1` | `ABS_X 32767` |
| `axis lx 0` | `ABS_X` near 0 (±300) |
| `dpad left` | `ABS_HAT0X -1` |

> If square shows up as `BTN_WEST` the face buttons were passed through
> unswapped and the pad is positionally wrong — X and Y transposed in every
> game. This is the single most likely silent bug in the whole stage and it
> is why this table is spelled out.

### E1.5 — the PS button is OURS  *(terminal C reader still running)*

    ~/couch/tools/fake-pad press ps          # short: a TAP
    ~/couch/tools/fake-pad hold ps 1.5       # long: a HOLD

**Success:**

* the tap produces **one** `BTN_MODE 1` / `BTN_MODE 0` pair on the virtual
  pad, ~80 ms apart (the re-injected chord), *after* the release — not
  during the press;
* the hold produces **no** `BTN_MODE` on the virtual pad at all;
* `/tmp/inputproc.log` shows `gesture ps-tap 0.12s` and then
  `gesture ps-hold 0.9s` followed by `gesture ps-hold-release 1.5s`.

Cross-check the arithmetic against stage 1's own module:

    grep '"kind": "gesture"' ~/couch/shadow/inputproc-$(date +%Y%m%d).jsonl | tail -5

**Failure:** a `BTN_MODE` on the virtual pad during a hold means the
withhold logic did not engage — check that `COUCHD_OWNS=input` really is in
the environment (without it the process forwards BTN_MODE by design).

### E1.6 — the FF suite (SR7)  *(terminal C)*

Twenty create *attempts* — only sixteen slots exist, so four must be
refused — then updates, erases, and sixteen more creates. That last batch
is the real test: if erase did not free the slots, it returns ENOSPC.

    $PY - <<'EOF'
    import time
    from evdev import InputDevice, ecodes, ff, list_devices
    v = [InputDevice(p) for p in list_devices()]
    v = [x for x in v if x.name == 'Microsoft X-Box 360 pad'][0]
    def rumble(strong, weak):
        e = ff.Effect(ecodes.FF_RUMBLE, -1, 0,
                      ff.Trigger(0, 0), ff.Replay(400, 0),
                      ff.EffectType(ff_rumble_effect=ff.Rumble(strong, weak)))
        return e
    ids, enospc, slowest = [], 0, 0.0
    for i in range(20):                      # CREATE x20 (16 must fit, 4 must fail cleanly)
        t = time.monotonic()
        try:
            ids.append(v.upload_effect(rumble(0x4000 + i, 0x2000)))
        except OSError as ex:
            enospc += 1
        slowest = max(slowest, time.monotonic() - t)
    print('created', len(ids), 'refused', enospc)
    for i, fid in enumerate(ids):            # UPDATE (same id back in)
        e = rumble(0x7000, 0x1000); e.id = fid
        t = time.monotonic(); v.upload_effect(e)
        slowest = max(slowest, time.monotonic() - t)
    print('updated', len(ids))
    v.write(ecodes.EV_FF, ids[0], 1); time.sleep(0.5)   # PLAY
    v.write(ecodes.EV_FF, ids[0], 0)                    # STOP
    v.write(ecodes.EV_FF, ecodes.FF_GAIN, 0xC000)       # GAIN
    for fid in ids:                                     # ERASE
        t = time.monotonic(); v.erase_effect(fid)
        slowest = max(slowest, time.monotonic() - t)
    print('erased', len(ids))
    again = []
    for i in range(16):                                 # slots must be free again
        again.append(v.upload_effect(rumble(0x3000, 0x3000)))
    print('re-created', len(again))
    for fid in again:
        v.erase_effect(fid)
    print('slowest single FF operation: %.1f ms' % (slowest * 1000))
    EOF

**Success, all four:**

* `created 16 refused 4` — sixteen slots, and the seventeenth is a clean
  refusal, not a wrap-around or a crash;
* `updated 16` with no exception — updates reuse slots (if they allocated,
  this line would have thrown ENOSPC);
* `erased 16` then `re-created 16` — erase really frees;
* `slowest single FF operation` well under 1000 ms. **A ~30 000 ms figure
  means UI_FF_ERASE is not being answered** — that is the exact stall SR7
  exists to prevent, and it would freeze a real game on exit.

> **What the four refusals are, and are not, evidence of.** `create_virtual`
> passes `max_effects=FF_SLOTS`, so the *kernel's* uinput side counts the
> slots and returns -ENOSPC on the seventeenth upload itself. The request
> never reaches inputproc, and inputproc's own exhaustion branch — the one
> that answers UI_FF_UPLOAD with -ENOSPC when its slot map is full — does
> not run in this step at all. So `created 16 refused 4` proves the slot
> count agrees end to end and that a refusal is clean rather than a
> wrap-around or a crash. It does **not** prove our exhaustion handling.
> That invariant is covered only by `test_inputproc.py`; do not report this
> step as having exercised it.

Then confirm the map in inputproc's own log:

    grep '"kind": "ff"' ~/couch/shadow/inputproc-$(date +%Y%m%d).jsonl \
      | tail -20

You should see `upload-create` with distinct `phys` ids, `upload-update`
with the **same** `virt`/`phys` pair, `play`, `stop`, `gain`, and `erase`.

### E1.7 — latency  *(terminal C)*

Generate traffic, then read the health record:

    for i in $(seq 200); do ~/couch/tools/fake-pad axis lx 1;
                            ~/couch/tools/fake-pad axis lx -1; done

    grep '"event": "tick"' ~/couch/shadow/inputproc-$(date +%Y%m%d).jsonl \
      | tail -3

**Gate: `p99_ms` < 10.0**, and record `p50_ms` alongside it. The number is
kernel-timestamp-to-forward inside this process only; the double-
virtualisation figure (our X360 → Steam Input → Steam's own virtual pad) is
E2's measurement, not this one.

**If p99 ≥ 10 ms:** do not tune anything yet — record it, check the box is
not busy (`uptime`), and re-run. Three runs of the same number is a result;
one run is weather.

### E1.8 — the Kodi buttonmap assertion (SR2)  *(terminal C)*

Kodi's peripheral.joystick resolves a buttonmap by
`<sanitised name>_<buttons>b_<axes>a.xml`. This computes the filename from
the **live virtual pad** and looks for it where Kodi actually looks.

**Do not hardcode a Kodi path here.** Since 8 Aug 2026 the running Kodi is
the 21.3 Flatpak, whose profile is `~/.var/app/tv.kodi.Kodi/data` — not
`~/.kodi`, and not `~/.var/app/tv.kodi.Kodi/.kodi`. `couchd/kodiprofile.py`
is the one place that knows this, and it answers with the flavour that was
last *launched* rather than the one that is merely chosen. An earlier
version of this step checked `~/.kodi` and `/usr/share/kodi` and so could
fail against a perfectly good virtual pad, or — worse — pass off the
leftover apt-Kodi tree that is still installed as the rollback.

The apt build ships its buttonmaps under `/usr/share/kodi`; the Flatpak
ships them **inside the app image**, under the deploy directory, so that
root has to be built from the flavour rather than assumed:

    $PY - <<'EOF'
    import os, re, sys
    sys.path.insert(0, '/home/ds2000/couch/couchd')
    import kodiprofile
    from evdev import InputDevice, ecodes, list_devices
    v = [InputDevice(p) for p in list_devices()]
    v = [x for x in v if x.name == 'Microsoft X-Box 360 pad'][0]
    caps = v.capabilities()
    b = len(caps.get(ecodes.EV_KEY, []))
    a = len(caps.get(ecodes.EV_ABS, []))
    fn = '%s_%db_%da.xml' % (re.sub(r'[^A-Za-z0-9_.-]', '_', v.name), b, a)
    flav = kodiprofile.flavour()
    print('virtual pad:', v.path, v.name, f'{b}b {a}a')
    print('Kodi flavour (last LAUNCHED):', flav)
    print('profile:', kodiprofile.profile_dir())
    print('Kodi would look for:', fn)
    sub = 'resources/buttonmaps/xml/linux'
    # 1. the user's own overrides, written by the addon into the profile;
    # 2. the addon if Kodi has updated it into the profile's addons dir,
    #    which shadows the shipped copy;
    # 3. the shipped copy: /usr/share/kodi for apt, inside the app image
    #    for the Flatpak (user install first, then a system-wide one).
    roots = [os.path.join(kodiprofile.addon_data('peripheral.joystick'), sub),
             os.path.join(kodiprofile.addons_dir(), 'peripheral.joystick', sub)]
    if flav == 'flatpak':
        deploy = 'files/share/kodi/addons/peripheral.joystick'
        roots += [os.path.join(os.path.expanduser(d), deploy, sub) for d in (
            '~/.local/share/flatpak/app/tv.kodi.Kodi/current/active',
            '/var/lib/flatpak/app/tv.kodi.Kodi/current/active')]
    else:
        roots.append('/usr/share/kodi/addons/peripheral.joystick/' + sub)
    hit = False
    for r in roots:
        p = os.path.join(r, fn)
        ok = os.path.exists(p)
        hit = hit or ok
        print(('  FOUND    ' if ok else '  missing  ') + p)
    print('RESULT:', 'RESOLVES' if hit else 'DOES NOT RESOLVE')
    EOF

**Success:** `Kodi flavour (last LAUNCHED): flatpak`,
`Kodi would look for: Microsoft_X-Box_360_pad_11b_8a.xml`, and
`RESULT: RESOLVES` off the app-image root, i.e. a `FOUND` line under
`~/.local/share/flatpak/app/tv.kodi.Kodi/current/active/files/share/kodi/`.
That file is shipped, so the first two roots are *expected* to say
`missing` — only the RESULT line is the gate.

**Read the flavour line before you read the result.** If it says `apt` when
Kodi 21 is what actually runs, the gate has resolved against the wrong tree
and its answer means nothing; fix `~/couch/data/kodi-flavour-active` (it is
written by `kodi-tv` at every launch, so launching Kodi once repairs it)
and re-run.

**Failure:** if the counts are not `11b 8a`, the virtual pad has drifted
from vpad's shape and `test_inputproc.py`'s table-equality tests should have
caught it — run them before doing anything else:

    $PY -m pytest ~/couch/couchd/test_inputproc.py -q

(Sanity note: the hand-made `linux/DualSense_Wireless_Controller_13b_8a.xml`
override came across the Flatpak migration and is present under **both**
profiles: below `userdata/addon_data/peripheral.joystick/` in
`~/.var/app/tv.kodi.Kodi/data` for the running Kodi, and still in `~/.kodi`
for the apt rollback. Checked 9 Aug 2026. It
is proof that this box uses the `linux` provider and this naming scheme —
but note it is proof about the *pad's own* map, which stage 2 hides; it is
not a substitute for the RESULT line above.)

### E1.9 — persistence  *(MANDATORY, and part of k=3)*

This step was written as "optional, do it once". It is not optional, and
the reason is worth spelling out: destroy → reattach is the *only* path in
the whole ladder that re-runs the poller's fd bookkeeping. Everything
E1.2–E1.8 touches runs on fds opened once at startup, so a wrong fd role
after a reattach — the physical node's fd left registered where the virtual
node's belongs, or a stale fd still in the poll set — is invisible to every
earlier step and shows up in real life as a pad that goes dead the first
time Bluetooth blinks. SR6 exists for exactly this path. A run that skips
E1.9 has tested the easy half.

With inputproc still running, kill the rig from terminal A (Ctrl-C), watch
`/tmp/inputproc.log`, then bring the rig back with `fake-pad up`.

**Success:**

* on loss: `physical pad gone (eof)` then
  `holding the virtual pad for 30s` — and the virtual pad node still exists;
* if you wait past 30 s: `persistence window expired: destroying the
  virtual pad so Steam can free the player slot`, node gone;
* on reconnect inside the window: `ff re-upload after reconnect: n ok,
  0 failed`, and re-running E1.6's play/stop still rumbles.

`--persist-secs 30` is used here only so this step takes half a minute; the
unit ships 120. Do the reconnect-inside-the-window case every run — the
expiry case can be done once per k=3, since it is a timer rather than a
reattach.

### E1.10 — tear down, in this order

1. terminal B: Ctrl-C inputproc → `inputproc stopping`, keys up, node destroyed
2. terminal A: `~/couch/tools/fake-pad quit` → units restored, corpus clean
3. terminal C: nothing to do

Then confirm the box is exactly as it was:

    systemctl --user is-active tv-waker pad-record pad-battery
    ls ~/couch/recordings | wc -l          # unchanged from E0.1's count
    grep 'Microsoft X-Box 360 pad' /proc/bus/input/devices   # expect NO output

> The last line used to be `ls /dev/input/by-id | grep -i x-box`, which was
> worthless: `by-id` symlinks come from
> `/usr/lib/udev/rules.d/60-persistent-input.rules`, and every `SYMLINK+=`
> line there is gated on `ENV{ID_BUS}=="?*"`, which udev only sets for a
> usb/bluetooth/serio/rmi ancestry. A uinput device has none of those, so a
> leftover virtual pad gets no `by-id` entry at all and the check passed
> whether or not one was there. `/proc/bus/input/devices` is the kernel's
> own list and always names the device. If it *does* print an
> `N: Name="Microsoft X-Box 360 pad"` line, an inputproc is still running
> somewhere — find it
> (`pgrep -af inputproc.py`) before starting the next run, or the next run
> grabs nothing and every number it produces is fiction.

---

## The k=3 rule

E1 passes when **E1.2 through E1.9 are green three times in a row**, on
three separate rig starts. Record for each run: p50/p99, the FF suite's four
lines, the Kodi flavour + RESULT lines, and E1.9's reconnect line. One green
run proves the code can work; three prove it does.

E1.9 is inside the k=3 window deliberately. It is the reattach path, so it
is the one step whose bug is a *state* bug rather than a logic bug — the
kind that shows up on the second or third go and not the first, which is the
whole reason k=3 is three and not one.

Keep the three runs' numbers somewhere durable — the flag-day checklist in
`docs/couchd-stage2-design.md` compares against them, and E2's
double-virtualisation latency is only meaningful next to E1's baseline.

## What E1 does NOT prove

The first three items here are not scope decisions like the ones after
them. They are gaps *inside* the gates E1 does run — places where a green
run is compatible with the thing being broken. Read them before quoting a
green E1 at anyone, including yourself.

* **That anything downstream receives a gesture.** E1.5 checks that a tap
  and a hold are classified correctly and that BTN_MODE is withheld, and it
  reads the answer out of `/tmp/inputproc.log` and the JSONL. That is the
  whole loop. `InputProc.report()` is an explicit stub — its docstring says
  so — because the couchd supervisor socket is a later wire-up, and nothing
  in this repo reads `~/couch/shadow/inputproc-*.jsonl` (checked 9 Aug
  2026: `inputproc.py` is the only file that mentions it). So E1 proves the
  gesture was *detected*, and proves nothing at all about it being *acted
  on*. On the day the PS button is supposed to open the couch switcher, the
  wire that makes it do so has never been tested by this ladder.
* **That the latency figure covers the slow path.** The p99 gate is honest
  about what it measures but not about what it samples. `latencies.append`
  sits at the end of the forward loop and is only reached on `EV_SYN` of a
  forwarded event; a `BTN_MODE` event hits `continue` and returns before it,
  so guide presses contribute no samples. And BTN_MODE is precisely the path
  that calls `report()`, which does a **blocking JSONL write**. The one code
  path doing file I/O in the fast path is therefore the one path excluded
  from the latency gate. E1.7 makes this worse by driving stick traffic only
  (`axis lx`), so even the pad's *other* buttons are barely represented.
  Treat `p99 < 10 ms` as "stick forwarding is fast", not "inputproc is
  fast".
* **That inputproc refuses a 17th effect correctly.** See E1.6's note: the
  kernel refuses it first, so our own -ENOSPC branch never runs on the rig.
  Unit tests only.
* **Steam.** E1 never starts Steam. Whether Steam adopts the virtual pad as
  first-class is E2, which is a daytime, Donnie-aware experiment with the
  Steam config backed up (`cp -a ~/.steam/steam/config ...`).
* **The live udev rule.** E1 grabs a pad that ds2000 can still open; the
  real ownership rule is never exercised by this ladder (SR8). That is why
  flag-day step 1 is a real-pad `getfacl` + `CURRENT_TAGS` check, and why
  `--no-ownership-assert` exists at all.
* **Bluetooth reality.** Link-quality stalls and the patched `bluetooth.ko`
  interaction cannot be reproduced by uhid. Flag-day checklist.
* **Elden Ring rumble through X360 emulation.** Unverified anywhere
  upstream; it is on the flag-day acceptance checklist explicitly.
