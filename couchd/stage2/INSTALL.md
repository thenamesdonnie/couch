# stage 2 install kit — the one sudo session

Nothing in this directory is installed by anything automatic. It exists so
that the *entire* root-requiring part of stage 2 is one sitting, in daylight,
with the rollback rehearsed before it is needed.

**Factor 1, restated (SR1):** no root at runtime, root once at install, and
never at rollback. If you find yourself typing `sudo` outside this document
or outside `couchd-input-release`, something has gone wrong with the design,
not with your memory.

**Do the install with the real DualSense DISCONNECTED**, and do not
uncomment the real-pad rule lines yet. Steps 1–7 install the machinery and
step 8 rehearses the rollback; the pad's routing does not change until you
deliberately arm the rule at flag day (steps 9–10, which are not part of
this sitting).

---

## Before you start

    cd ~/couch/couchd/stage2
    ls                       # the five files below should be here

| file | goes to | why |
|---|---|---|
| `couchd-input-release` | `/usr/local/sbin/` | the rollback (SR3) |
| `sudoers-couchd` | `/etc/sudoers.d/couchd` | NOPASSWD for exactly that script |
| `inputproc.service` | `/etc/systemd/system/` | the system unit (SR1/SR6) |
| `72-couchd-own-dualsense.rules` | `/etc/udev/rules.d/` | ownership (SR2) |
| `INSTALL.md` | nowhere | this |

---

## 1. The system user and group

    sudo groupadd --system couchd-input
    sudo useradd --system --gid couchd-input --groups input \
                 --home-dir /nonexistent --shell /usr/sbin/nologin \
                 couchd-input

Verify — `input` must be there, and `ds2000` must **not** be:

    id couchd-input
    getent group couchd-input        # expect: couchd-input:x:NNN:
    getent group input               # expect ...,couchd-input  — and NO ds2000

> If ds2000 ever appears in `couchd-input`, Steam is back inside the fence
> and stage 2 is silently a no-op. That is the single most important line in
> this file.

`--home-dir /nonexistent` is deliberate — a service account with no home is
one less thing to secure — but it has a consequence you must not lose:
`inputproc.py` derives its JSONL directory from `os.path.expanduser('~')`
unless `COUCHD_SHADOW_DIR` is set, and its logger swallows `OSError` on
purpose so that a broken evidence path can never take the pad down. Under
this user, an unset `COUCHD_SHADOW_DIR` means every evidence record is
written to `/nonexistent/couch/shadow`, fails, and is discarded **in
silence**. That is why `inputproc.service` sets `COUCHD_SHADOW_DIR`
explicitly, why step 5 ACLs the directory that variable points at, and why
step 10 makes you look at the file rather than assume it.

## 2. The rollback script (install this BEFORE the rule)

    sudo install -m 0755 -o root -g root couchd-input-release \
         /usr/local/sbin/couchd-input-release

Verify it is not writable by ds2000 — if it were, the sudoers line in step 3
would be a root shell:

    ls -l /usr/local/sbin/couchd-input-release
    # expect: -rwxr-xr-x 1 root root

## 3. The sudoers drop-in

    sudo install -m 0440 -o root -g root sudoers-couchd /etc/sudoers.d/couchd
    sudo visudo -c

`visudo -c` must print "parsed OK" for every file. **Do not skip it** — a
syntax error in `/etc/sudoers.d/` locks the box out of sudo entirely.

Then, in a *new* terminal as ds2000, prove it works with no password:

    sudo -n /usr/local/sbin/couchd-input-release
    # expect: "no rule at /etc/udev/rules.d/72-... (already released)" and
    #         exit 0, with no password prompt

## 4. The unit

    sudo install -m 0644 -o root -g root inputproc.service /etc/systemd/system/
    sudo systemctl daemon-reload
    # do NOT enable or start it yet

## 5. Let couchd-input reach the venv and the shadow directory

The venv and the shadow directory both live under `/home/ds2000`, which is
`0750 ds2000:ds2000`. ACLs, narrower than loosening the home directory:

    sudo setfacl -m u:couchd-input:--x /home/ds2000
    sudo setfacl -m u:couchd-input:--x /home/ds2000/couch
    sudo setfacl -R -m u:couchd-input:rX /home/ds2000/couch/couchd
    sudo setfacl -m u:couchd-input:rwx /home/ds2000/couch/shadow
    sudo setfacl -d -m u:couchd-input:rw /home/ds2000/couch/shadow

The last two lines are the ones that matter for evidence. `~/couch/shadow`
is where `COUCHD_SHADOW_DIR` in `inputproc.service` points, and it stays
ds2000-owned (couchd and the comparator read it as ds2000), so the service
user reaches it by ACL and nothing else: `rwx` to create today's file, and
the **default** ACL so that a file the service creates tomorrow is still
readable by ds2000 the day after. Drop the `-d` line and the first file of
each new day lands unreadable to everyone but the service.

Verify the import:

    sudo -u couchd-input /home/ds2000/couch/couchd/.venv/bin/python -c \
      "import sys; sys.path.insert(0,'/home/ds2000/couch/couchd'); \
       import inputproc; print('import ok')"

And verify the write, as the service user, *before* trusting the unit —
this is the failure that is otherwise completely silent:

    sudo -u couchd-input touch /home/ds2000/couch/shadow/.acl-probe
    ls -l /home/ds2000/couch/shadow/.acl-probe   # exists, owner couchd-input
    cat  /home/ds2000/couch/shadow/.acl-probe    # as ds2000: no "Permission
                                                 # denied" - the -d ACL works
    rm   /home/ds2000/couch/shadow/.acl-probe

If the `touch` fails, stop here. Everything downstream will appear to work
and will produce no evidence at all.

## 6. The udev rule — **rig-scoped first**

Install it scoped to the *fake* pad. This is what E1 uses, and it is the
version that cannot possibly touch the real pad:

    sed 's/__PAD_UNIQ__/de:ad:be:ef:fa:ce/' 72-couchd-own-dualsense.rules \
      | sudo tee /etc/udev/rules.d/72-couchd-own-dualsense.rules >/dev/null
    sudo udevadm control --reload-rules

Dry-run it against a real pad path (SR8: the real MAC must be **unmatched**).
With the real pad connected for this check only:

    udevadm test /sys/class/input/eventN 2>&1 | grep -i "couchd-own"
    # expect: NO match from 72-couchd-own-dualsense.rules
    getfacl -c /dev/input/eventN
    # expect: user:ds2000:rw-   (the real pad is untouched)

Then disconnect the real pad again.

## 7. Verification that survives updates (SR5)

Two commands, and one command you must **never** use.

    # correct:
    getfacl -c /dev/input/eventN
    udevadm info /dev/input/eventN | grep CURRENT_TAGS

    # WRONG — never use this to check ownership:
    udevadm info /dev/input/eventN | grep '^E: TAGS='

`TAG-=` clears only `CURRENT_TAGS`. The `TAGS` property keeps listing
`uaccess` forever, so a `TAGS` check passes while ds2000 still holds an ACL.
That is finding F5/F6, and it is why `inputproc.py`'s own ownership assertion
reads getfacl and the group, never `TAGS`.

**Owned (correct) looks like:**

    $ getfacl -c /dev/input/event21
    user::rw-
    group::rw-          <- group is couchd-input, see ls -l
    other::---
    (NO user:ds2000: line)

    $ ls -l /dev/input/event21
    crw-rw---- 1 root couchd-input ...

    $ udevadm info /dev/input/event21 | grep CURRENT_TAGS
    E: CURRENT_TAGS=:seat:   (no :uaccess:)

**Not owned looks like:** a `user:ds2000:rw-` line in getfacl, or
`CURRENT_TAGS` containing `uaccess`, or group `input` instead of
`couchd-input`.

## 8. Rehearse the rollback — before you need it

Do this now, while the rule is still rig-scoped and the real pad is
irrelevant. It is three minutes and it is the difference between a calm
evening and a bad one.

    sudo -n couchd-input-release
    ls -l /etc/udev/rules.d/72-couchd-own-dualsense.rules*
    # expect: only the .off file exists

At this point the unit is installed but not enabled, so the script prints
`inputproc.service already disabled` and moves on. That line is the visible
half of something worth knowing before flag day: the script both stops
**and disables** the unit, on purpose, because disarming the rule survives a
reboot and a bare `stop` does not. So after any real rollback, re-arming is
two things, not one — put the rule back *and* `sudo systemctl enable --now
inputproc`.

Put it back for E1:

    sudo mv /etc/udev/rules.d/72-couchd-own-dualsense.rules.off \
            /etc/udev/rules.d/72-couchd-own-dualsense.rules
    sudo udevadm control --reload-rules && sudo udevadm trigger

Add this line, verbatim, to the audit cheat sheet:

    pad dead / games see no controller ->  sudo couchd-input-release

## 9. Flag day only — arming the real pad

Not part of this sitting. When the flag-day checklist in
`docs/couchd-stage2-design.md` says so:

1. edit `/etc/udev/rules.d/72-couchd-own-dualsense.rules`: comment the
   `__PAD_UNIQ__`/rig line, uncomment the two real-pad lines at the bottom
   (evdev scoped to `aa:bb:cc:dd:ee:ff`, plus the model-scoped hidraw line);
2. `sudo udevadm control --reload-rules && sudo udevadm trigger`;
3. reconnect the real pad and run the step-7 verification **on the real
   pad** — SR8 notes the live rule is never exercised by the fake-pad
   ladder, so this getfacl + CURRENT_TAGS check is its first real test;
4. `sudo systemctl enable --now inputproc`. This starts the process; it does
   **not** flip anything. The unit used to pin `COUCHD_OWNS=input` in its own
   environment, which made enabling it the flip - bypassing the declared
   combined cutover with `gestures`, and breaking the charter's one-step
   rollback, because emptying `owns.conf` then did not release the pad.
   inputproc reads `couchd/owns.conf` itself now, exactly as that file's
   header always said it would. Started with `input` absent from that file,
   it is a forwarder: BTN_MODE goes straight through and the legacy watcher
   keeps its gestures;
5. the actual flip is adding `input` to `couchd/owns.conf` and restarting the
   unit. It is read at startup, not live, so the restart is required — see
   the open ruling in
   `docs/audits/stage2-inputproc-review-20260809-synthesis.md` before
   assuming otherwise;
6. **inputproc will refuse to own the pad** while the couchd supervisor
   socket is a stub, and at the time of writing it still is. That refusal is
   deliberate: grabbing the pad blinds both existing gesture stacks, and
   nothing consumes what inputproc intercepts, so the whole PS-button
   vocabulary would be dead in the room with `status.json` still reporting a
   healthy `acting`. Wire the supervisor first. `--supervisor-stub-ok` exists
   for the rig and must never appear at flag day;
7. `journalctl -u inputproc -f` and `tail -f /tmp/inputproc.log`.

Rollback at any point, no password, one command:

    sudo couchd-input-release

It stops the unit, disables it, and disarms the rule, so the box comes back
from a reboot still rolled back. Exit 0 means every step did what it said;
exit 1 means at least one printed a WARNING and you should read it rather
than assume the pad is back. Getting back to armed is step 9 again, from
the top.

## 10. Prove the evidence file exists — first thing after the first start

Do not skip this and do not infer it from the journal. The journal is
systemd's record that the process started; the JSONL is inputproc's record
of what it *did*, and the two fail independently. Because the logger
swallows `OSError` by design (see step 1), a wrong or unreachable
`COUCHD_SHADOW_DIR` produces a perfectly healthy-looking unit that has
written nothing, and you would not find out until the evening you needed
the evidence.

With the unit running and the pad connected, press the PS button once, then:

    ls -l ~/couch/shadow/inputproc-$(date +%Y%m%d).jsonl

Three things must all be true: **the file exists**, **it is non-empty**, and
**it is owned by `couchd-input`**. An empty file means the process opened it
and produced no records; no file at all means the path is wrong; ds2000
ownership means it is yesterday's hand-run leftover and not this unit's
work at all — check the timestamp.

Then confirm it is actually this run and actually moving:

    tail -2 ~/couch/shadow/inputproc-$(date +%Y%m%d).jsonl
    # expect a JSON object per line, with a recent "t", and a "kind":"press"
    # or "kind":"gesture" record from the button you just pressed

    wc -l ~/couch/shadow/inputproc-$(date +%Y%m%d).jsonl   # note the number
    # press PS again, wait a moment
    wc -l ~/couch/shadow/inputproc-$(date +%Y%m%d).jsonl   # must have grown

If the file is missing or empty, the fault is one of three things and they
are quick to tell apart: `systemctl show inputproc -p Environment` (is
`COUCHD_SHADOW_DIR` actually set?), `systemctl show inputproc -p
ReadWritePaths` (does the sandbox allow that directory?), and step 5's
`touch` probe (does the ACL allow it?). Fix it before flag day continues —
an inputproc with no evidence trail is not something to run overnight.

---

## What is deliberately NOT here

* **The hidraw rule is not MAC-scoped.** It cannot be: nothing in a hidraw
  device's sysfs ancestry carries `uniq`, and a hidraw uevent has no
  `HID_UNIQ`. `ATTRS{uniq}` on a hidraw rule matches nothing and silently
  turns the whole rule into a no-op. Valve's own `60-steam-input.rules`
  scopes hidraw by `KERNELS` pattern for the same reason. Consequence:
  enabling the hidraw line hides every DualSense on the box, so it stays
  commented out until E2/flag day, both of which are already "real pad
  disconnected, Donnie present" (SR8).
* **`SDL_GAMECONTROLLER_IGNORE_DEVICES` for the Steam client.** S6/SR5:
  what couchd launches is covered by the launcher's environment; covering
  the Steam *client* means taking over `~/.config/autostart/steam.desktop`,
  which is its own scoped item with its own rollback.
* **Deleting steam-input-guard.** Charter: the old stack stays installed
  and working for one full stage after the cutover.
