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
                       user=DESKTOP_USER):
    """SR5: on every pad appearance, assert we really are the only owner.

    Returns (ok, [problems]). Never uses `udevadm info TAGS` - TAG-= clears
    only CURRENT_TAGS, so TAGS still lists uaccess forever and would make
    this check pass while ds2000 still has an ACL. getfacl is the truth.
    """
    problems = []
    if gid_name != group:
        problems.append(f'group is {gid_name!r}, want {group!r}')
    if (mode & 0o060) != 0o060:
        problems.append(f'group lacks rw (mode {mode & 0o777:04o}, want 0660)')
    if mode & 0o006:
        problems.append(f'world-accessible (mode {mode & 0o777:04o})')
    if acl_text and re.search(rf'^user:{re.escape(user)}:', acl_text, re.M):
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
    """getfacl text, or '' if the tool is missing. Bounded, never blocking."""
    try:
        out = subprocess.run(['getfacl', '-cE', path], capture_output=True,
                             text=True, timeout=2.0)
        return out.stdout or ''
    except (OSError, subprocess.SubprocessError):
        return ''


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
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError:
            pass

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
        except OSError:
            pass
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
        self.tracker = gesture.PressTracker()
        self.ffmap = FFMap()
        self.persist = Persistence(args.persist_secs)
        self.phys = None
        self.phys_path = None
        self.ui = None
        self.grabbed = False
        self.pending = deque()     # (deadline_mono, etype, code, value)
        self.latencies = deque(maxlen=4096)
        self.counts = {'in': 0, 'out': 0, 'dropped': 0, 'ff': 0,
                       'gesture': 0, 'reinjected': 0}
        self.gesture_at = time.monotonic()
        self.hold_pending = False
        self.stop = False
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
            return
        try:
            os.write(self.ui.fd, struct.pack(EVENT_FORMAT, sec, usec,
                                             etype, code, value))
            self.counts['out'] += 1
        except OSError as e:
            say(f'virtual write failed: {e}')

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
        upload = self.ui.begin_upload(request_id)
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
            self.ui.end_upload(upload)
            self.counts['ff'] += 1

    def ff_erase(self, request_id):
        """UI_FF_ERASE - the one SR7 singles out: unhandled, a closing game
        stalls 30 SECONDS per effect waiting for a reply that never comes."""
        erase = self.ui.begin_erase(request_id)
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
            self.ui.end_erase(erase)
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
            dev.close()
            raise SystemExit(3)
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
        ok, problems = evaluate_ownership(gid_name, st.st_mode,
                                          read_acl(path))
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
        self.tracker.reset()
        self.hold_pending = False
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
            self.report('gesture', event='ps-hold-release',
                        held=self.tracker.press_duration, kernel_t=round(k, 6))

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
        while self.pending and self.pending[0][0] <= mono:
            _, etype, code, value = self.pending.popleft()
            self.emit(etype, code, value)
            self.syn()

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
            for fd in list(registered):
                if fd not in want:
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
            # hold fires on the KERNEL clock, extrapolated - a held button
            # with no further reports must still decide (R4)
            if self.own and self.tracker.poll() == gesture.HOLD:
                self.gesture_at = mono
                self.report('gesture', event='ps-hold',
                            held=self.tracker.held_for())
            # the release that never came
            if (self.own and self.hold_pending and not self.tracker.button_down
                    and gesture.handoff_overdue(mono - self.gesture_at)):
                self.hold_pending = False
                self.report('gesture', event='ps-hold-release-timeout',
                            held=None)
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
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    # COUCHD_OWNS is the flag day. Without "input" in it this process is a
    # forwarder that intercepts NOTHING - BTN_MODE goes straight through and
    # the legacy pad-home-watcher keeps its gestures.
    args.own_input = owns('input') and not args.observe
    InputProc(args).run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
