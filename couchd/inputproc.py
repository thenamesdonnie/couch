#!/usr/bin/env python3
"""couchd stage 2 - the input fast path (design note: S1-S9, SR1-SR9).

One job, one process (C22): hold the physical DualSense's evdev node open
with EVIOCGRAB so nothing else on the box can see it, and present in its
place a virtual pad that is a BYTE-FOR-BYTE clone of ~/.local/bin/vpad's
Xbox 360 device - same name, same 11 buttons, same 8 axes - because Kodi
resolves its buttonmap by `<name>_<b>b_<a>a.xml` and ships exactly
Microsoft_X-Box_360_pad_11b_8a.xml (SR2).

What it does with the stream:
  * forwards everything a 360 pad has, translating DualSense codes and
    stick ranges (see FACE_SWAP below - square/triangle are NOT a
    pass-through, and getting that wrong ships silently);
  * intercepts BTN_MODE when, and only when, COUCHD_OWNS grants "input":
    the press is WITHHELD from the virtual pad until the tap-or-hold
    question is settled by gesture.py (the same module stage 1 runs, SR4);
    a tap is then re-injected with InputPlumber's 80ms chord pacing, a
    hold is ours and is never forwarded;
  * re-uploads force feedback to the physical pad rather than decoding it
    (S3), with the full UPLOAD-create / UPLOAD-update / ERASE / playback /
    gain contract SR7 demands, and a cache so rumble survives a BT drop;
  * outlives BT drops (SR6): all-keys-up + centred axes + SYN once, then
    silence, holding the node for --persist-secs so Steam keeps the player
    slot; on give-up it DESTROYS the node to free that slot.

Runs as the system user couchd-input (SR1). No root at runtime, ever.

    inputproc.py --uniq aa:bb:cc:dd:ee:ff
    inputproc.py --device /dev/input/event21 --persist-secs 120

Rollback is `stage2/couchd-input-release` plus stopping this unit; the
udev rule alone un-flips nothing (SR3).
"""
import argparse
import errno
import fcntl
import grp
import json
import os
import pwd
import re
import select
import signal
import struct
import subprocess
import sys
import time
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gesture
import gestureconf
import owns as ownsconf
from gesture import EVENT_FORMAT, EVENT_SIZE

try:
    from evdev import AbsInfo, InputDevice, UInput, ecodes, ff
except ImportError as e:            # pragma: no cover - venv is the contract
    raise SystemExit(f'inputproc needs python-evdev >= 1.9.1 in the venv: {e}')

HOME = os.path.expanduser('~')
SHADOW_DIR = os.environ.get('COUCHD_SHADOW_DIR', os.path.join(HOME, 'couch', 'shadow'))
HUMAN_LOG = '/tmp/inputproc.log'
SUPERVISOR_SOCK = os.path.join(SHADOW_DIR, 'couchd.sock')

PAD_NAME = 'DualSense Wireless Controller'
PAD_UNWANTED = re.compile(r'Motion|Touchpad', re.I)
OWNER_GROUP = 'couchd-input'
DESKTOP_USER = 'ds2000'

FF_SLOTS = 16                   # memless slots, both sides (SR7's slot math)
PERSIST_SECONDS = 120.0         # SR6's hold window, calibrated at flag day
RESCAN_SECONDS = 1.0
HEALTH_SECONDS = 30.0
POLL_MS = 50                    # hold-detection granularity; forwarding is
                                # event-driven, so this is not a latency floor

# =========================================================================
# vpad's tables, cloned EXACTLY (SR2). test_inputproc.py parses
# ~/.local/bin/vpad and asserts these still match it, so drift is caught.
# =========================================================================
VPAD_NAME = 'Microsoft X-Box 360 pad'
VPAD_BUS, VPAD_VENDOR, VPAD_PRODUCT, VPAD_VERSION = 0x03, 0x045e, 0x028e, 0x0110

VPAD_BUTTONS = {
    'a': 0x130, 'b': 0x131, 'x': 0x133, 'y': 0x134,
    'lb': 0x136, 'rb': 0x137,
    'select': 0x13a, 'start': 0x13b, 'guide': 0x13c,
    'l3': 0x13d, 'r3': 0x13e,
}
# axis name -> (code, min, max)
VPAD_AXES = {
    'lx': (0x00, -32768, 32767), 'ly': (0x01, -32768, 32767),
    'lt': (0x02, 0, 255),
    'rx': (0x03, -32768, 32767), 'ry': (0x04, -32768, 32767),
    'rt': (0x05, 0, 255),
    'hat0x': (0x10, -1, 1), 'hat0y': (0x11, -1, 1),
}

# -- DualSense -> Xbox 360 translation ------------------------------------
# The face buttons are the trap. hid-playstation reports square as BTN_WEST
# (0x134) and triangle as BTN_NORTH (0x133); xpad reports X (the LEFT face
# button) as BTN_NORTH and Y (the TOP one) as BTN_WEST. Passing the codes
# through unchanged therefore puts square where Y belongs and triangle where
# X belongs - positionally wrong, and invisible until someone plays a game.
BTN_MAP = {
    ecodes.BTN_SOUTH: VPAD_BUTTONS['a'],       # cross    -> A
    ecodes.BTN_EAST: VPAD_BUTTONS['b'],        # circle   -> B
    ecodes.BTN_WEST: VPAD_BUTTONS['x'],        # square   -> X   (swap)
    ecodes.BTN_NORTH: VPAD_BUTTONS['y'],       # triangle -> Y   (swap)
    ecodes.BTN_TL: VPAD_BUTTONS['lb'],
    ecodes.BTN_TR: VPAD_BUTTONS['rb'],
    ecodes.BTN_SELECT: VPAD_BUTTONS['select'],  # create
    ecodes.BTN_START: VPAD_BUTTONS['start'],    # options
    ecodes.BTN_MODE: VPAD_BUTTONS['guide'],     # PS - intercepted, see below
    ecodes.BTN_THUMBL: VPAD_BUTTONS['l3'],
    ecodes.BTN_THUMBR: VPAD_BUTTONS['r3'],
    # BTN_TL2/BTN_TR2 (the DualSense's DIGITAL trigger clicks) are dropped on
    # purpose: a 360 pad has no such buttons, the analog ABS_Z/ABS_RZ below
    # carry the triggers, and inventing extra buttons breaks the 11b/8a
    # buttonmap name Kodi resolves.
}
STICK_AXES = {ecodes.ABS_X, ecodes.ABS_Y, ecodes.ABS_RX, ecodes.ABS_RY}
PASS_AXES = {ecodes.ABS_Z, ecodes.ABS_RZ,          # triggers, already 0..255
             ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y}   # hat, already -1..1


def scale_stick(value):
    """DualSense 0..255 (0 = up/left) -> X360 -32768..32767, same polarity.

    xpad already reports "up is negative", and hid-playstation already
    reports "0 is up", so this is a pure range change with no inversion.
    """
    return max(-32768, min(32767, int(value) * 257 - 32768))


def translate(etype, code, value):
    """One physical event -> one virtual event, or None to drop it.

    Pure, so the whole translation table is testable without a device.
    """
    if etype == gesture.EV_SYN:
        return (etype, code, value) if code == gesture.SYN_REPORT else None
    if etype == gesture.EV_KEY:
        out = BTN_MAP.get(code)
        return None if out is None else (etype, out, 1 if value else 0)
    if etype == gesture.EV_ABS:
        if code in STICK_AXES:
            return (etype, code, scale_stick(value))
        if code in PASS_AXES:
            return (etype, code, value)
        return None
    return None                     # EV_MSC, touchpad slots, everything else


# =========================================================================
# pure logic: capabilities, permissions, ownership, flags
# =========================================================================
def virtual_capabilities(ff_codes=()):
    """The uinput capability dict for an exact vpad clone."""
    caps = {
        ecodes.EV_KEY: sorted(VPAD_BUTTONS.values()),
        ecodes.EV_ABS: [(code, AbsInfo(0, lo, hi, 0, 0, 0))
                        for code, lo, hi in sorted(VPAD_AXES.values())],
    }
    if ff_codes:
        caps[ecodes.EV_FF] = sorted(ff_codes)
    return caps


def choose_ff_codes(physical_ff):
    """SR2's invariant, mechanised: virtual ffbit is FF_RUMBLE (plus FF_GAIN
    if the pad has it) and is ALWAYS a subset of the physical set.

    Advertising FF_PERIODIC without waveform bits fails uploads at our own
    device, which is why the ceiling is the DualSense's memless set.
    """
    physical = set(physical_ff or ())
    return [c for c in (ecodes.FF_RUMBLE, ecodes.FF_GAIN) if c in physical]


def assert_writable(flags, path='<device>'):
    """SR2: python-evdev silently falls back to O_RDONLY when O_RDWR fails,
    and a read-only node makes every FF upload and playback write fail much
    later, somewhere confusing. Fail here, loudly, instead."""
    if (flags & os.O_ACCMODE) != os.O_RDWR:
        raise PermissionError(
            errno.EACCES,
            f'{path} opened READ-ONLY - evdev fell back. FF playback is a '
            f'write(): udev MODE must be 0660 and this process must be in '
            f'group {OWNER_GROUP} (SR2)')
    return True


def evaluate_ownership(gid_name, mode, acl_text, group=OWNER_GROUP,
                       user=DESKTOP_USER, owner_name=None):
    """SR5: on every pad appearance, assert we really are the only owner.

    Returns (ok, [problems]). Never uses `udevadm info TAGS` - TAG-= clears
    only CURRENT_TAGS, so TAGS still lists uaccess forever and would make
    this check pass while ds2000 still has an ACL. getfacl is the truth.

    This FAILS CLOSED. `acl_text is None` means getfacl could not be run, and
    that is a problem, not a pass - the check exists precisely to catch a
    lingering uaccess ACL, so being unable to look is the same as not knowing.
    `owner_name` is the device's owning UID: getfacl renders the owner as
    `user::rw-`, never `user:ds2000:rw-`, so a node owned BY ds2000 sails past
    the named-entry regex while Steam can still open it.
    """
    problems = []
    if owner_name is not None and owner_name == user:
        problems.append(f'{user} OWNS the node (want root; getfacl renders '
                        f'the owner as user::, so no ACL entry shows this)')
    if gid_name != group:
        problems.append(f'group is {gid_name!r}, want {group!r}')
    if (mode & 0o060) != 0o060:
        problems.append(f'group lacks rw (mode {mode & 0o777:04o}, want 0660)')
    if mode & 0o006:
        problems.append(f'world-accessible (mode {mode & 0o777:04o})')
    if acl_text is None:
        problems.append('getfacl unavailable - cannot prove uaccess was '
                        'cleared (install the acl package)')
    elif re.search(rf'^user:{re.escape(user)}:', acl_text, re.M):
        problems.append(f'{user} still holds an ACL (uaccess not cleared)')
    return (not problems), problems


def owns(what, env=None):
    """COUCHD_OWNS is a comma/space list of what couchd is allowed to own.
    Anything not listed runs in observe-and-forward-only mode."""
    raw = (os.environ if env is None else env).get('COUCHD_OWNS', '') or ''
    return what in [t for t in re.split(r'[,\s]+', raw) if t]


# =========================================================================
# pure logic: the force-feedback id map (SR7)
# =========================================================================
class FFFull(Exception):
    """All 16 memless slots are live; the 17th create must return -ENOSPC
    rather than silently overwriting somebody's rumble."""


class FFMap:
    """Virtual effect id <-> physical effect id, 1:1, bounded at 16 slots.

    The virtual side's ids are handed to us by the uinput kernel side; the
    physical side's come back from the pad's own upload. Nothing here talks
    to a device: it is the bookkeeping only, so the invariants SR7 cares
    about (translation both ways, update reuses the slot, erase frees it,
    exhaustion is an error not a wrap) are testable with plain integers.
    """

    def __init__(self, slots=FF_SLOTS):
        self.slots = slots
        self.to_phys = {}          # virtual id -> physical id
        self.to_virt = {}          # physical id -> virtual id
        self.blobs = {}            # virtual id -> effect bytes (SR6 re-upload)

    # -- queries ----------------------------------------------------------
    def phys_for(self, virt):
        return self.to_phys.get(virt)

    def virt_for(self, phys):
        return self.to_virt.get(phys)

    def live(self):
        return len(self.to_phys)

    def can_create(self):
        return self.live() < self.slots

    def cached(self):
        """(virtual id, effect bytes) for every live effect, oldest first."""
        return [(v, self.blobs[v]) for v in sorted(self.to_phys)]

    # -- mutations --------------------------------------------------------
    def bind(self, virt, phys, blob=b''):
        """UPLOAD-create: a new virtual effect gets a new physical slot."""
        if virt in self.to_phys:
            raise ValueError(f'virtual effect {virt} already bound')
        if not self.can_create():
            raise FFFull(f'{self.slots} effect slots exhausted')
        if phys in self.to_virt:
            raise ValueError(f'physical effect {phys} already mapped')
        self.to_phys[virt] = phys
        self.to_virt[phys] = virt
        self.blobs[virt] = blob
        return phys

    def update(self, virt, blob=b''):
        """UPLOAD-update: SAME slot, new parameters. If this allocated a new
        slot instead, 16 uploads of one effect would exhaust the device."""
        if virt not in self.to_phys:
            raise KeyError(virt)
        self.blobs[virt] = blob
        return self.to_phys[virt]

    def rebind(self, virt, phys):
        """Physical pad came back with new slot numbers (SR6)."""
        if virt not in self.to_phys:
            raise KeyError(virt)
        old = self.to_phys[virt]
        self.to_virt.pop(old, None)
        if phys in self.to_virt and self.to_virt[phys] != virt:
            raise ValueError(f'physical effect {phys} already mapped')
        self.to_phys[virt] = phys
        self.to_virt[phys] = virt
        return phys

    def erase(self, virt):
        """UI_FF_ERASE. Unhandled, a closing game stalls 30s PER EFFECT."""
        phys = self.to_phys.pop(virt, None)
        self.blobs.pop(virt, None)
        if phys is not None:
            self.to_virt.pop(phys, None)
        return phys

    def forget_physical(self):
        """Pad gone: the physical ids are meaningless now, the cache is not."""
        self.to_virt.clear()

    def clear(self):
        self.to_phys.clear()
        self.to_virt.clear()
        self.blobs.clear()


# =========================================================================
# pure logic: the persistence state machine (SR6)
# =========================================================================
OWNED, LOST, GONE = 'owned', 'lost', 'gone'
A_KEYS_UP = 'keys-up'          # all buttons 0 + axes centred + one SYN
A_DESTROY = 'destroy'          # free Steam's player slot
A_CREATE = 'create'            # a new virtual node is needed
A_REUPLOAD = 'reupload-ff'     # F11: rumble dies silently after a BT hiccup


class Persistence:
    """The virtual pad outlives Bluetooth drops - but not forever.

    loss  -> emit all-keys-up ONCE then silence, hold the node
    tick  -> after persist_secs, DESTROY the node (Steam gets its slot back)
    back  -> re-key and re-upload the cached effects; recreate if destroyed
    """

    def __init__(self, persist_secs=PERSIST_SECONDS):
        self.persist_secs = persist_secs
        self.state = OWNED
        self.deadline = None
        self.lost_at = None

    def on_loss(self, mono):
        if self.state != OWNED:
            return []
        self.state = LOST
        self.lost_at = mono
        self.deadline = mono + self.persist_secs
        return [A_KEYS_UP]

    def tick(self, mono):
        if self.state == LOST and mono >= self.deadline:
            self.state = GONE
            self.deadline = None
            return [A_DESTROY]
        return []

    def on_reconnect(self, mono):
        if self.state == OWNED:
            return []
        actions = [A_CREATE] if self.state == GONE else []
        actions += [A_KEYS_UP, A_REUPLOAD]
        self.state = OWNED
        self.deadline = None
        self.lost_at = None
        return actions

    def remaining(self, mono):
        if self.state != LOST:
            return None
        return max(0.0, self.deadline - mono)


# =========================================================================
# device discovery / permissions
# =========================================================================
def find_pad(uniq=None, name=PAD_NAME, procfile='/proc/bus/input/devices'):
    """The button node for the pad, from /proc/bus/input/devices.

    Same discovery pad-record and couchd's PadObserver use, plus the uniq
    filter the rig needs: the fake pad and the real one are the same model
    and are told apart ONLY by MAC.
    """
    found = []
    try:
        with open(procfile) as f:
            blocks = f.read().split('\n\n')
    except OSError:
        return found
    for b in blocks:
        m = re.search(r'N: Name="([^"]*)"', b)
        if not m or name not in m.group(1) or PAD_UNWANTED.search(m.group(1)):
            continue
        u = re.search(r'U: Uniq=(\S*)', b)
        got = (u.group(1) if u else '').lower()
        if uniq and got != uniq.lower():
            continue
        h = re.search(r'H: Handlers=.*?(event\d+)', b)
        if h:
            found.append(('/dev/input/' + h.group(1), m.group(1), got))
    return found


def read_acl(path):
    """getfacl text, or None if the tool could not be run.

    None and '' are DIFFERENT answers and the caller must treat them so: ''
    means "asked, no named ACL entries", None means "could not ask". Returning
    '' for both is how the one check standing between Steam and the pad used
    to pass silently on a box without the `acl` package installed.
    """
    try:
        out = subprocess.run(['getfacl', '-cE', path], capture_output=True,
                             text=True, timeout=2.0)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout or ''


def open_physical(path):
    """Open O_RDWR and PROVE it (SR2), then grab happens in the caller."""
    if not os.access(path, os.W_OK):
        raise PermissionError(errno.EACCES, f'{path}: no write access - FF '
                                            f'playback is a write() (SR2)')
    dev = InputDevice(path)
    try:
        assert_writable(fcntl.fcntl(dev.fd, fcntl.F_GETFL), path)
    except Exception:
        dev.close()
        raise
    return dev


# =========================================================================
# logging
# =========================================================================
class JsonlLog:
    """~/couch/shadow/inputproc-YYYYMMDD.jsonl, same shape as couchd's."""

    def __init__(self, directory=SHADOW_DIR, prefix='inputproc'):
        self.dir, self.prefix = directory, prefix
        self.seq = 0
        self._day = None
        self._f = None
        self.broken = None
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            self.broken = str(e)

    def write(self, rec):
        self.seq += 1
        rec.setdefault('t', time.time())
        rec.setdefault('mono', time.monotonic())
        rec['seq'] = self.seq
        day = time.strftime('%Y%m%d')
        try:
            if day != self._day or self._f is None:
                if self._f:
                    self._f.close()
                self._day = day
                self._f = open(os.path.join(
                    self.dir, f'{self.prefix}-{day}.jsonl'), 'a', buffering=1)
            self._f.write(json.dumps(rec, default=str) + '\n')
            self.broken = None
        except OSError as e:
            # Still never raises - a logger that can kill the input path is
            # worse than a silent one. But "silent" was taken literally: under
            # the real unit the service user's home is /nonexistent, so every
            # record went nowhere and the process looked healthy in journalctl
            # while the flip's entire evidence trail did not exist. Say it,
            # once per new failure.
            if self.broken != str(e):
                self.broken = str(e)
                say(f'EVIDENCE LOST: cannot write {self.dir}: {e}')
        return rec

    def close(self):
        if self._f:
            self._f.close()
            self._f = None


def say(msg):
    now = time.time()
    line = (f"{time.strftime('%H:%M:%S', time.localtime(now))}"
            f".{int(now % 1 * 1000):03d} {msg}")
    try:
        with open(HUMAN_LOG, 'a') as f:
            f.write(line + '\n')
    except OSError:
        pass
    print(line, flush=True)


def ff_name(code):
    """'FF_RUMBLE', not "('FF_EFFECT_MIN', 'FF_RUMBLE')".

    evdev's reverse maps return a TUPLE for any code that has aliases, and
    FF_RUMBLE (80) collides with FF_EFFECT_MIN, FF_GAIN (96) with
    FF_MAX_EFFECTS. Log the real name, not the range sentinel.
    """
    name = ecodes.FF.get(code, code)
    if isinstance(name, str):
        return name
    real = [n for n in name if not n.endswith(('_MIN', '_MAX', '_MAX_EFFECTS'))]
    return real[0] if real else name[0]


def percentile(values, pct):
    if not values:
        return None
    s = sorted(values)
    i = min(len(s) - 1, max(0, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[i]


# =========================================================================
# the process
# =========================================================================
class InputProc:
    def __init__(self, args):
        self.args = args
        self.log = JsonlLog(args.log_dir)
        self.own = args.own_input
        self.conf = gestureconf.load()
        self.tracker = gesture.PressTracker(
            hold_seconds=self.conf.hold_seconds,
            double_tap_s=self.conf.double_tap_seconds,
            long_hold_seconds=self.conf.long_hold_seconds)
        # The hold tiers are announced from HERE, not from PressTracker.poll()
        # - see poll_hold(). These two are the "already announced" latches
        # poll() would otherwise keep inside the tracker, where they would
        # change what feed() decides.
        self._hold_reported = False
        self._long_hold_reported = False
        self.ffmap = FFMap()
        self.persist = Persistence(args.persist_secs)
        self.phys = None
        self.phys_path = None
        self.ui = None
        self.grabbed = False
        self.pending = deque()     # (deadline_mono, etype, code, value)
        self.latencies = deque(maxlen=4096)
        self.counts = {'in': 0, 'out': 0, 'dropped': 0, 'ff': 0,
                       'gesture': 0, 'reinjected': 0, 'write_failures': 0}
        self.gesture_at = time.monotonic()
        self.hold_pending = False
        self.stop = False
        self.degraded = None
        self._next_scan = 0.0
        self._next_health = time.monotonic() + HEALTH_SECONDS

    # -- supervisor socket ------------------------------------------------
    def report(self, kind, **fields):
        """Gesture/press events out of the fast path.

        STUB - the couchd supervisor socket (SO_PEERCRED uid in {ds2000,
        couchd-input}, SR1) is a LATER wire-up. Until then every event lands
        in the JSONL and the human log, which is what the E-runbook reads.
        Deliberately not a blocking send: SR7 forbids gesture/socket work
        sharing a blocking path with FF handling.
        """
        rec = dict(fields)
        rec.update({'kind': kind, 'owns_input': self.own})
        self.log.write(rec)
        if kind == 'gesture':
            self.counts['gesture'] += 1
            say(f"gesture {fields.get('event')} "
                f"{round(fields.get('held', 0) or 0, 3)}s")

    # -- virtual pad ------------------------------------------------------
    def create_virtual(self, ff_codes):
        caps = virtual_capabilities(ff_codes)
        self.ui = UInput(caps, name=VPAD_NAME, vendor=VPAD_VENDOR,
                         product=VPAD_PRODUCT, version=VPAD_VERSION,
                         bustype=VPAD_BUS, max_effects=FF_SLOTS)
        say(f'virtual pad up: {VPAD_NAME} '
            f'{len(caps[ecodes.EV_KEY])}b {len(caps[ecodes.EV_ABS])}a '
            f'ff={[ff_name(c) for c in ff_codes]} node={self.ui.device.path}')
        self.log.write({'kind': 'virtual-pad', 'event': 'created',
                        'name': VPAD_NAME, 'node': self.ui.device.path,
                        'buttons': len(caps[ecodes.EV_KEY]),
                        'axes': len(caps[ecodes.EV_ABS]),
                        'ff': [int(c) for c in ff_codes]})

    def emit(self, etype, code, value, sec=0, usec=0):
        """Raw struct write, vpad's emit(). The kernel restamps uinput input,
        so the timestamp is carried for completeness only - the kernel times
        we actually reason with are the PHYSICAL ones, read before this."""
        if self.ui is None:
            return False
        try:
            os.write(self.ui.fd, struct.pack(EVENT_FORMAT, sec, usec,
                                             etype, code, value))
            self.counts['out'] += 1
            return True
        except OSError as e:
            # A swallowed write is how a button gets stuck: if the DOWN half
            # of a chord lands and the UP half does not, the game holds that
            # button until something else releases it. Record it as evidence
            # (say() alone never reaches the corpus) and let the caller
            # decide - drain_pending abandons the rest of the chord and
            # re-asserts all-keys-up.
            self.counts['write_failures'] += 1
            say(f'virtual write failed: {e}')
            self.log.write({'kind': 'virtual-pad', 'event': 'write-failed',
                            'etype': int(etype), 'code': int(code),
                            'value': int(value), 'error': str(e)})
            return False

    def syn(self):
        self.emit(gesture.EV_SYN, gesture.SYN_REPORT, 0)

    def all_keys_up(self):
        """S5/SR6: every button released, every axis centred, ONE SYN, then
        silence. A stuck button across an ownership change is the worst
        failure this process can have."""
        for code in sorted(VPAD_BUTTONS.values()):
            self.emit(gesture.EV_KEY, code, 0)
        for code, lo, hi in sorted(VPAD_AXES.values()):
            self.emit(gesture.EV_ABS, code, 0 if lo < 0 else lo)
        self.syn()
        self.log.write({'kind': 'virtual-pad', 'event': 'all-keys-up'})

    def destroy_virtual(self):
        if self.ui is not None:
            try:
                self.ui.close()
            except Exception:
                pass
            self.log.write({'kind': 'virtual-pad', 'event': 'destroyed'})
            self.ui = None

    # -- force feedback (SR7) --------------------------------------------
    def ff_upload(self, request_id):
        """UI_FF_UPLOAD: create (id -1 -> map) AND update (translate the id,
        same slot). Bounded: one begin/end pair, no retries, no waiting."""
        # The handshake itself is outside the careful try below unless it is
        # guarded here: an OSError from begin_upload/end_upload propagates out
        # of the poll loop and kills the process, which to a running game is a
        # controller unplug followed by a different controller plugging in.
        try:
            upload = self.ui.begin_upload(request_id)
        except (OSError, RuntimeError) as e:
            self.counts['ff'] += 1
            self.log.write({'kind': 'ff', 'event': 'upload-handshake-failed',
                            'error': f'{type(e).__name__}: {e}'})
            return
        upload.retval = 0
        try:
            virt = int(upload.effect.id)
            eff = ff.Effect.from_buffer_copy(upload.effect)
            phys = self.ffmap.phys_for(virt)
            if phys is None:
                if not self.ffmap.can_create():
                    upload.retval = -errno.ENOSPC
                    self.log.write({'kind': 'ff', 'event': 'upload-create',
                                    'virt': virt, 'error': 'ENOSPC'})
                    return
                eff.id = -1
                new = self._phys_upload(eff)
                eff.id = -1
                self.ffmap.bind(virt, new, bytes(memoryview(eff)))
                self.log.write({'kind': 'ff', 'event': 'upload-create',
                                'virt': virt, 'phys': new,
                                'type': int(eff.type), 'live': self.ffmap.live()})
            else:
                eff.id = phys
                self._phys_upload(eff)
                eff.id = -1
                self.ffmap.update(virt, bytes(memoryview(eff)))
                self.log.write({'kind': 'ff', 'event': 'upload-update',
                                'virt': virt, 'phys': phys,
                                'live': self.ffmap.live()})
        except FFFull:
            upload.retval = -errno.ENOSPC
        except OSError as e:
            upload.retval = -(e.errno or errno.EIO)
            self.log.write({'kind': 'ff', 'event': 'upload-failed',
                            'error': str(e)})
        except Exception as e:                       # never stall the game
            upload.retval = -errno.EIO
            self.log.write({'kind': 'ff', 'event': 'upload-failed',
                            'error': f'{type(e).__name__}: {e}'})
        finally:
            try:
                self.ui.end_upload(upload)
            except (OSError, RuntimeError) as e:
                self.log.write({'kind': 'ff', 'event': 'upload-end-failed',
                                'error': f'{type(e).__name__}: {e}'})
            self.counts['ff'] += 1

    def ff_erase(self, request_id):
        """UI_FF_ERASE - the one SR7 singles out: unhandled, a closing game
        stalls 30 SECONDS per effect waiting for a reply that never comes."""
        try:
            erase = self.ui.begin_erase(request_id)
        except (OSError, RuntimeError) as e:
            self.counts['ff'] += 1
            self.log.write({'kind': 'ff', 'event': 'erase-handshake-failed',
                            'error': f'{type(e).__name__}: {e}'})
            return
        erase.retval = 0
        try:
            virt = int(erase.effect_id)
            phys = self.ffmap.erase(virt)
            if phys is not None and self.phys is not None:
                try:
                    self.phys.erase_effect(phys)
                except OSError as e:
                    # The pad may already be gone; the game must still be
                    # answered, and our map is authoritative either way.
                    self.log.write({'kind': 'ff', 'event': 'erase-physical',
                                    'phys': phys, 'error': str(e)})
            self.log.write({'kind': 'ff', 'event': 'erase', 'virt': virt,
                            'phys': phys, 'live': self.ffmap.live()})
        except Exception as e:
            erase.retval = -errno.EIO
            self.log.write({'kind': 'ff', 'event': 'erase-failed',
                            'error': f'{type(e).__name__}: {e}'})
        finally:
            try:
                self.ui.end_erase(erase)
            except (OSError, RuntimeError) as e:
                self.log.write({'kind': 'ff', 'event': 'erase-end-failed',
                                'error': f'{type(e).__name__}: {e}'})
            self.counts['ff'] += 1

    def ff_play(self, code, value):
        """EV_FF on the virtual node: playback/stop by effect id, or the
        global knobs. Gain is a device property, not an effect, so it is
        forwarded as itself; everything else is an id and is translated."""
        if self.phys is None:
            return
        try:
            if code in (ecodes.FF_GAIN, ecodes.FF_AUTOCENTER):
                self.phys.write(ecodes.EV_FF, code, value)
                self.log.write({'kind': 'ff', 'event': 'gain',
                                'code': int(code), 'value': int(value)})
                return
            phys = self.ffmap.phys_for(int(code))
            if phys is None:
                self.log.write({'kind': 'ff', 'event': 'play-unmapped',
                                'virt': int(code)})
                return
            self.phys.write(ecodes.EV_FF, phys, value)
            self.log.write({'kind': 'ff',
                            'event': 'play' if value else 'stop',
                            'virt': int(code), 'phys': phys,
                            'value': int(value)})
        except OSError as e:
            self.log.write({'kind': 'ff', 'event': 'play-failed',
                            'error': str(e)})
        finally:
            self.counts['ff'] += 1

    def _phys_upload(self, eff):
        if self.phys is None:
            raise OSError(errno.ENODEV, 'physical pad absent')
        return self.phys.upload_effect(eff)

    def reupload_ff(self):
        """SR6/F11: after a BT hiccup the pad's slots are empty. Without
        this, rumble dies silently for the rest of the session."""
        self.ffmap.forget_physical()
        ok = failed = 0
        for virt, blob in self.ffmap.cached():
            try:
                eff = ff.Effect.from_buffer_copy(blob)
                eff.id = -1
                self.ffmap.rebind(virt, self._phys_upload(eff))
                ok += 1
            except Exception as e:
                failed += 1
                self.log.write({'kind': 'ff', 'event': 'reupload-failed',
                                'virt': virt, 'error': str(e)})
        if ok or failed:
            say(f'ff re-upload after reconnect: {ok} ok, {failed} failed')
        self.log.write({'kind': 'ff', 'event': 'reupload', 'ok': ok,
                        'failed': failed})

    # -- the physical pad -------------------------------------------------
    def attach(self):
        """Find, open, verify, grab. Returns True when we own the pad."""
        found = find_pad(self.args.uniq) if not self.args.device else [
            (self.args.device, '', '')]
        if not found:
            return False
        path = found[0][0]
        try:
            dev = open_physical(path)
        except (OSError, PermissionError) as e:
            say(f'cannot own {path}: {e}')
            self.log.write({'kind': 'health', 'event': 'open-failed',
                            'node': path, 'error': str(e)})
            return False
        if self.own and self.args.assert_ownership and not self.check_ownership(path):
            # check_ownership's contract is "REFUSE to own, log loudly, leave
            # the legacy stack enabled - never half-own the pad". It used to
            # SystemExit(3) instead, from a path the 1Hz rescan also calls, so
            # a transient permission race (logind's uaccess ACL not yet
            # revoked on a reconnect) killed a RUNNING process five times in
            # ten seconds and tripped StartLimitBurst. The unit then stayed
            # dead with the udev rule still armed: no inputproc, and no other
            # process able to open the pad either. Degrade instead - forward
            # everything, intercept nothing, and keep saying so.
            self.own = False
            self.degraded = 'ownership assertion failed'
            say('DEGRADED to observe-and-forward-only: not owning the pad. '
                'The legacy stack keeps its gestures. Fix the udev rule and '
                'restart; `sudo couchd-input-release` if the pad is hidden.')
            self.log.write({'kind': 'health', 'event': 'degraded',
                            'why': 'ownership-assert', 'node': path})
        self.phys, self.phys_path = dev, path
        if self.own:
            try:
                dev.grab()
                self.grabbed = True
            except OSError as e:
                say(f'EVIOCGRAB refused on {path}: {e} - NOT owning')
                dev.close()
                self.phys = None
                return False
        say(f'physical pad {path} '
            f'{"GRABBED" if self.grabbed else "observed (no ownership)"} '
            f'uniq={found[0][2] or "?"}')
        self.log.write({'kind': 'health', 'event': 'attached', 'node': path,
                        'uniq': found[0][2], 'grabbed': self.grabbed})
        return True

    def check_ownership(self, path):
        """SR5: assert on EVERY appearance. On failure REFUSE to own, log
        loudly, leave the legacy stack enabled - never half-own the pad."""
        try:
            st = os.stat(path)
            gid_name = grp.getgrgid(st.st_gid).gr_name
        except (OSError, KeyError) as e:
            say(f'ownership check could not stat {path}: {e}')
            return False
        try:
            owner_name = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            owner_name = str(st.st_uid)
        ok, problems = evaluate_ownership(gid_name, st.st_mode,
                                          read_acl(path),
                                          owner_name=owner_name)
        self.log.write({'kind': 'health', 'event': 'ownership',
                        'node': path, 'ok': ok, 'problems': problems,
                        'group': gid_name, 'mode': oct(st.st_mode & 0o777)})
        if not ok:
            say(f'REFUSING to own {path}: ' + '; '.join(problems))
            say('legacy stack left enabled; fix the udev rule then restart')
        return ok

    def detach(self, why):
        if self.phys is None:
            return
        if self.own and self.hold_pending:
            # A press was in flight when the pad went. No release is coming,
            # and the tracker is about to be reset, so this is the only moment
            # the record can say a hold was cut off rather than simply
            # vanishing.
            self.report('gesture', event='ps-hold-release-timeout',
                        held=self.tracker.held_for(), why=why)
        # Anything still queued for the virtual pad belongs to a press on a
        # pad that no longer exists. Draining it after all_keys_up() would
        # emit a phantom guide chord into whatever is running - and would
        # break the "every button released, ONE SYN, then silence" guarantee.
        if self.pending:
            self.log.write({'kind': 'virtual-pad', 'event': 'pending-dropped',
                            'queued': len(self.pending), 'why': why})
            self.pending.clear()
        if self.grabbed:
            try:
                self.phys.ungrab()
            except OSError:
                pass
            self.grabbed = False
        try:
            self.phys.close()
        except OSError:
            pass
        self.phys = None
        self.phys_path = None
        self.tracker.reset()
        self.hold_pending = False
        self._hold_reported = False
        self._long_hold_reported = False
        self.log.write({'kind': 'health', 'event': 'detached', 'why': why})
        say(f'physical pad gone ({why})')

    # -- the stream -------------------------------------------------------
    def on_physical_readable(self):
        try:
            data = os.read(self.phys.fd, EVENT_SIZE * 64)
        except BlockingIOError:
            return
        except OSError:
            self.on_loss('read error')
            return
        if not data:
            self.on_loss('eof')
            return
        now_wall = time.time()
        for off in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
            sec, usec, etype, code, value = struct.unpack_from(
                EVENT_FORMAT, data, off)
            k = sec + usec / 1e6
            self.tracker.note_event(k, now_wall)
            self.counts['in'] += 1
            if etype == gesture.EV_KEY and code == gesture.BTN_MODE:
                self.on_guide(k, value, sec, usec)
                continue
            out = translate(etype, code, value)
            if out is None:
                self.counts['dropped'] += 1
                continue
            self.emit(out[0], out[1], out[2], sec, usec)
            if etype == gesture.EV_SYN:
                self.latencies.append(now_wall - k)

    def on_guide(self, k, value, sec, usec):
        """BTN_MODE. Observe mode forwards it untouched; owning mode WITHHOLDS
        it until gesture.py has settled tap-or-hold (a forwarded press that
        later turns out to be a hold is exactly the war stage 2 ends)."""
        if not self.own:
            out = translate(gesture.EV_KEY, gesture.BTN_MODE, value)
            self.emit(out[0], out[1], out[2], sec, usec)
            self.syn()
            self.report('press', event='BTN_MODE', value=value,
                        kernel_t=round(k, 6), forwarded=True)
            self.tracker.feed(k, value)
            return
        outcome = self.tracker.feed(k, value)
        self.gesture_at = time.monotonic()
        if outcome == gesture.DOWN:
            self.hold_pending = True
            self._hold_reported = False
            self._long_hold_reported = False
            self.report('press', event='BTN_MODE', value=1,
                        kernel_t=round(k, 6), forwarded=False)
        elif outcome in (gesture.TAP, gesture.DOUBLE_TAP):
            # A double-tap is still two taps as far as the virtual pad is
            # concerned: it gets both, spaced as they arrived. Only the
            # CONSUMER (couchd / the watcher) reads the pair as one gesture,
            # so nothing here has to know about the switcher.
            self.hold_pending = False
            self.report('gesture',
                        event=('ps-double-tap'
                               if outcome == gesture.DOUBLE_TAP else 'ps-tap'),
                        held=self.tracker.press_duration, kernel_t=round(k, 6))
            self.inject_tap()
        elif outcome == gesture.HOLD_RELEASE:
            self.hold_pending = False
            if not (self._hold_reported or self._long_hold_reported):
                # feed() is NOT binding-aware: it calls any press over
                # hold_seconds a hold. Stage 1 is - couchd's g_hold_fires is
                # `binding('hold') != "none" and g_hold_reached`, so with the
                # hold unbound it keeps a long press in 'down' and releases it
                # as a TAP. Honour the same gate here, or a long press with
                # hold=none is swallowed: withheld from the virtual pad,
                # never re-injected, gone.
                self.report('gesture', event='ps-tap',
                            held=self.tracker.press_duration,
                            kernel_t=round(k, 6), over_hold_threshold=True)
                self.inject_tap()
                return
            self.report('gesture', event='ps-hold-release',
                        held=self.tracker.press_duration, kernel_t=round(k, 6))

    def binding(self, name):
        """The effective action for one gesture, read from the SAME config
        file couchd reads. Defaults match couchd's Observed.binding()."""
        return (self.conf.bindings or {}).get(
            name, gestureconf.DEFAULT_BINDINGS.get(name, 'none'))

    def poll_hold(self, mono):
        """Announce the hold tiers, at most once per press.

        SR4, and the reason this does not call `PressTracker.poll()`: poll()
        LATCHES `hold_fired` on the tracker, and the shared `feed()` then
        classifies the eventual release as HOLD_RELEASE regardless of that
        release's real kernel duration (gesture.py's `was_hold`). Stage 1
        never polls, so its identical tracker classifies the same release by
        duration alone. One stalled loop iteration near the threshold is
        therefore enough to make the two stacks decide differently about the
        same press - which is exactly the invariant the combined input+gestures
        cutover rests on. So the tiers are detected with the same non-latching
        predicates couchd's guards use, and the tracker is left pristine.
        """
        t = self.tracker
        k = t.kernel_now()
        if (not self._hold_reported and self.binding('hold') != 'none'
                and gesture.hold_reached(t.button_down, t.down_since_k, k,
                                         t.hold_seconds)):
            self._hold_reported = True
            self.gesture_at = mono
            self.report('gesture', event='ps-hold', held=t.held_for())
        if (not self._long_hold_reported and t.long_hold_seconds is not None
                and self.binding('long_hold') != 'none'
                and gesture.long_hold_reached(t.button_down, t.down_since_k, k,
                                              t.long_hold_seconds)):
            self._long_hold_reported = True
            self.gesture_at = mono
            self.report('gesture', event='ps-long-hold', held=t.held_for())

    def inject_tap(self):
        """The withheld tap, re-injected to the VIRTUAL pad with
        InputPlumber's 80ms chord pacing - back-to-back press/release is
        coalesced or missed by consumers. Queued, not slept through: a
        blocking sleep here would stall forwarding for 80ms."""
        base = time.monotonic()
        for offset, value in gesture.chord_schedule():
            self.pending.append((base + offset, gesture.EV_KEY,
                                 VPAD_BUTTONS['guide'], value))
        self.counts['reinjected'] += 1

    def drain_pending(self, mono):
        """ONE queued event per pass, never two.

        `mono` is sampled once at the top of the loop, so a pass that arrives
        more than CHORD_GAP late used to find both halves of the chord due and
        emit them back-to-back in a single while-loop - which is precisely the
        coalescing CHORD_GAP exists to prevent. Being late is also not a reason
        to compress: the rest of the chord is pushed out by the lateness, so
        the GAP survives even when the absolute timing does not.
        """
        if not self.pending or self.pending[0][0] > mono:
            return
        due, etype, code, value = self.pending.popleft()
        if not self.emit(etype, code, value):
            # The virtual pad is not taking writes. Abandoning the chord
            # half-sent is what leaves a button held, so drop the remainder
            # and re-assert a known-good state.
            self.pending.clear()
            self.all_keys_up()
            return
        self.syn()
        late = mono - due
        if late > 0 and self.pending:
            self.pending = deque((d + late, t, c, v)
                                 for d, t, c, v in self.pending)

    def on_loss(self, why):
        self.detach(why)
        for action in self.persist.on_loss(time.monotonic()):
            if action == A_KEYS_UP:
                self.all_keys_up()
        say(f'holding the virtual pad for {self.args.persist_secs:.0f}s')

    def on_reconnect(self):
        for action in self.persist.on_reconnect(time.monotonic()):
            if action == A_CREATE:
                self.create_virtual(choose_ff_codes(
                    self.phys.capabilities().get(ecodes.EV_FF, [])))
            elif action == A_KEYS_UP:
                self.all_keys_up()
            elif action == A_REUPLOAD:
                self.reupload_ff()

    # -- virtual-side events (FF requests) --------------------------------
    def on_virtual_readable(self):
        try:
            events = list(self.ui.read())
        except BlockingIOError:
            return
        except OSError as e:
            say(f'virtual node read failed: {e}')
            return
        for ev in events:
            if ev.type == ecodes.EV_UINPUT:
                if ev.code == ecodes.UI_FF_UPLOAD:
                    self.ff_upload(ev.value)
                elif ev.code == ecodes.UI_FF_ERASE:
                    self.ff_erase(ev.value)
            elif ev.type == ecodes.EV_FF:
                self.ff_play(ev.code, ev.value)

    # -- health -----------------------------------------------------------
    def health(self, mono):
        rec = {'kind': 'health', 'event': 'tick',
               'state': self.persist.state,
               'grabbed': self.grabbed, 'owns_input': self.own,
               'degraded': self.degraded,
               'evidence_broken': self.log.broken,
               'node': self.phys_path,
               'ff_live': self.ffmap.live(),
               'p50_ms': None, 'p99_ms': None}
        lats = list(self.latencies)
        if lats:
            rec['p50_ms'] = round(percentile(lats, 50) * 1000, 3)
            rec['p99_ms'] = round(percentile(lats, 99) * 1000, 3)
            rec['samples'] = len(lats)
        rec.update(self.counts)
        self.log.write(rec)
        say(f"health {self.persist.state} in={self.counts['in']} "
            f"out={self.counts['out']} ff={self.counts['ff']} "
            f"p50={rec['p50_ms']}ms p99={rec['p99_ms']}ms")

    # -- the loop ---------------------------------------------------------
    def run(self):
        signal.signal(signal.SIGTERM, self._signal)
        signal.signal(signal.SIGINT, self._signal)
        say(f'inputproc starting (COUCHD_OWNS grants input: {self.own})')
        if self.own and not self.args.assert_ownership:
            say('WARNING: --no-ownership-assert - SR5 ownership check is OFF. '
                'This is legal for the fake-pad rig ONLY, never at flag day.')
        if not self.own:
            say('observe-and-forward-only: BTN_MODE IS forwarded, nothing '
                'is intercepted')
        try:
            self.attach()
            if self.phys is not None:
                ff_codes = choose_ff_codes(
                    self.phys.capabilities().get(ecodes.EV_FF, []))
                if ecodes.FF_RUMBLE not in ff_codes:
                    say('WARNING: physical pad advertises no FF_RUMBLE; the '
                        'virtual pad will carry no force feedback (SR2 subset)')
                self.create_virtual(ff_codes)
            else:
                # A uinput device's capabilities are fixed at UI_DEV_CREATE,
                # so we CANNOT create the virtual pad before we know the
                # physical pad's ffbit - guessing here is how you end up
                # advertising rumble the pad cannot do. Start in the
                # give-up state instead; the first attach creates it.
                say('no pad present yet - the virtual pad is created when '
                    'one appears (its FF bits must match the physical pad)')
                self.persist.state = GONE
            self.loop()
        finally:
            self.shutdown()

    def loop(self):
        poller = select.poll()
        registered = {}
        while not self.stop:
            mono = time.monotonic()
            self.drain_pending(mono)

            # (re)register whatever fds exist right now
            want = {}
            if self.phys is not None:
                want[self.phys.fd] = 'phys'
            if self.ui is not None:
                want[self.ui.fd] = 'virt'
            # Reconcile on (fd, role), not fd alone. A closed fd number is
            # reusable immediately, so the physical pad can be handed the
            # number the destroyed uinput node just gave up - and a map keyed
            # on the number alone would keep the stale role, dispatch the
            # pad's readiness to the uinput handler, never drain the pad, and
            # spin on a permanently asserted POLLIN.
            for fd, which in list(registered.items()):
                if want.get(fd) != which:
                    poller.unregister(fd)
                    registered.pop(fd)
            for fd, which in want.items():
                if fd not in registered:
                    poller.register(fd, select.POLLIN)
                    registered[fd] = which

            timeout = POLL_MS
            if self.pending:
                timeout = max(1, int((self.pending[0][0] - mono) * 1000))
            for fd, mask in poller.poll(timeout):
                which = registered.get(fd)
                if which == 'phys' and mask & select.POLLIN:
                    self.on_physical_readable()
                elif which == 'virt' and mask & select.POLLIN:
                    self.on_virtual_readable()
                elif mask & (select.POLLERR | select.POLLHUP):
                    if which == 'phys':
                        self.on_loss('pollhup')

            mono = time.monotonic()
            if self.own:
                self.conf = gestureconf.load()
                self.poll_hold(mono)
            # The release that never came: the button is STILL DOWN and no
            # further kernel events are coming (dead pad, stuck button), so
            # this is measured on the monotonic clock. The old form of this
            # guard also required `not button_down`, which detach() is the
            # only thing that produces - and detach() clears hold_pending on
            # the next line, so the branch could never run. A pad lost
            # mid-press is now reported by detach() itself.
            if (self.own and self.hold_pending and self.tracker.button_down
                    and gesture.handoff_overdue(mono - self.gesture_at)):
                self.hold_pending = False
                self.report('gesture', event='ps-hold-release-timeout',
                            held=self.tracker.held_for(), why='no-release')
            for action in self.persist.tick(mono):
                if action == A_DESTROY:
                    say('persistence window expired: destroying the virtual '
                        'pad so Steam can free the player slot')
                    self.destroy_virtual()
            if self.phys is None and mono >= self._next_scan:
                self._next_scan = mono + RESCAN_SECONDS
                if self.attach():
                    self.on_reconnect()
            if mono >= self._next_health:
                self._next_health = mono + HEALTH_SECONDS
                self.health(mono)

    def _signal(self, signum, frame):
        self.stop = True

    def shutdown(self):
        say('inputproc stopping')
        try:
            if self.ui is not None:
                self.all_keys_up()
        except Exception:
            pass
        self.detach('shutdown')
        self.destroy_virtual()
        self.log.write({'kind': 'health', 'event': 'stopped', **self.counts})
        self.log.close()


# =========================================================================
def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group()
    g.add_argument('--device', help='/dev/input/eventN (skips discovery)')
    g.add_argument('--uniq', help='pad MAC, e.g. aa:bb:cc:dd:ee:ff')
    p.add_argument('--persist-secs', type=float, default=PERSIST_SECONDS,
                   help='hold the virtual pad this long after a BT drop')
    p.add_argument('--log-dir', default=SHADOW_DIR)
    p.add_argument('--observe', action='store_true',
                   help='force observe-and-forward-only, ignoring COUCHD_OWNS')
    # RIG ONLY. The fake pad is uaccess'd to ds2000 by 71-dualsense-uaccess
    # (it matches on name, and the fake pad has the same name), so SR5's
    # ownership assertion CANNOT pass during E1-functional, which is a
    # no-root experiment by design. Never pass this at flag day - it is the
    # check that stops us half-owning the real pad next to Steam.
    p.add_argument('--no-ownership-assert', dest='assert_ownership',
                   action='store_false', default=True,
                   help='RIG ONLY: skip SR5 ownership assertion (E1)')
    # RIG ONLY, and a different kind of dangerous from the one above: this
    # one says "yes, I know the gestures I intercept go nowhere".
    p.add_argument('--supervisor-stub-ok', action='store_true',
                   help='RIG ONLY: own the pad even though the couchd '
                        'supervisor wire is still a stub')
    return p.parse_args(argv)


def grants_input(env_override=None):
    """Does this process own the pad?

    `couchd/owns.conf` is the answer, because owns.conf's own header says so:
    "input - stage 2 only - the input PROCESS reads this name". It used to be
    read from COUCHD_OWNS in the environment, which the systemd unit pinned to
    `input` unconditionally - so merely enabling the unit grabbed the pad, the
    declared combined cutover with `gestures` was bypassed, and the charter's
    one-step rollback ("empty this file FIRST") did not release it.

    COUCHD_OWNS still wins WHEN SET, because the fake-pad rig drives this
    process without touching the console's real ownership file. An unset
    variable means "ask owns.conf", which is what the unit now does.
    """
    raw = (os.environ if env_override is None else env_override).get(
        'COUCHD_OWNS')
    if raw is not None:
        return owns('input', env={'COUCHD_OWNS': raw})
    # load(), not owns(): owns() also requires couchd's heartbeat to be fresh,
    # which is the LEGACY stack's question ("may I stand down?"). This process
    # is not legacy - it must own the pad or not own it on the declaration
    # alone, or a couchd restart would silently hand the pad back mid-session.
    return 'input' in ownsconf.load().names


def main(argv=None):
    args = parse_args(argv)
    args.own_input = grants_input() and not args.observe
    if args.own_input and not args.supervisor_stub_ok:
        # THE interlock. report() is still a stub: inputproc's gestures land
        # in a JSONL file and nothing in this repo reads it. Meanwhile owning
        # the pad means grabbing it, so couchd's PadObserver (which matches on
        # the name 'DualSense Wireless Controller' and would see only our
        # X360-named virtual node) and the legacy watcher both go blind. With
        # `gestures` flipped, that is the entire PS-button vocabulary dead in
        # the living room, with status.json still reporting a healthy
        # `acting`. Refuse rather than discover it on the sofa.
        raise SystemExit(
            'REFUSING to own the pad: the couchd supervisor wire is still a '
            'stub (see report()), so nothing would consume the gestures this '
            'process intercepts, and grabbing the pad blinds both existing '
            'gesture stacks. Wire the supervisor socket first, or pass '
            '--supervisor-stub-ok if you are deliberately testing the grab '
            'path with the gesture vocabulary expendable.')
    InputProc(args).run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
