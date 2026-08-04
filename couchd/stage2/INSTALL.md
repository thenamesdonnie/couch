# stage 2 install kit — the one sudo session

Nothing in this directory is installed by anything automatic. It exists so
that the *entire* root-requiring part of stage 2 is one sitting, in daylight,
with the rollback rehearsed before it is needed.

**Factor 1, restated (SR1):** no root at runtime, root once at install, and
never at rollback. If you find yourself typing `sudo` outside this document
or outside `couchd-input-release`, something has gone wrong with the design,
not with your memory.

**Do the install with the real DualSense DISCONNECTED**, and do not
uncomment the real-pad rule lines yet. Steps 1–7 install the machinery; the
pad's routing does not change until you deliberately arm the rule at flag
day (step 9).

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

## 5. Let couchd-input reach the venv and the log directory

The venv lives under `/home/ds2000`, which is `0750 ds2000:ds2000`. Two ACLs,
narrower than loosening the home directory:

    sudo setfacl -m u:couchd-input:--x /home/ds2000
    sudo setfacl -m u:couchd-input:--x /home/ds2000/couch
    sudo setfacl -R -m u:couchd-input:rX /home/ds2000/couch/couchd
    sudo setfacl -m u:couchd-input:rwx /home/ds2000/couch/shadow
    sudo setfacl -d -m u:couchd-input:rw /home/ds2000/couch/shadow

Verify:

    sudo -u couchd-input /home/ds2000/couch/couchd/.venv/bin/python -c \
      "import sys; sys.path.insert(0,'/home/ds2000/couch/couchd'); \
       import inputproc; print('import ok')"

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
4. `sudo systemctl enable --now inputproc`;
5. `journalctl -u inputproc -f` and `tail -f /tmp/inputproc.log`.

Rollback at any point, no password, one command:

    sudo couchd-input-release

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
