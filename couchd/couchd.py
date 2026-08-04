#!/usr/bin/env python3
"""couchd stage 1 - the shadow control plane for the living-room console.

It watches the same world the four scripts watch (pad-home-watcher,
game-launch, steam-input-guard, the watcher's reconcile loop), keeps ONE
explicit state machine instead of four implicit ones, and says what it WOULD
do. It never does anything: there is no acting executor in this file, only
RecordingExecutor, so passivity is structural (C3/R1) rather than a flag that
could be forgotten. Stage 1 launches nothing (R1).

What it reads (all read-only, nothing is ever grabbed or written to):
  * the DualSense evdev button node - raw struct input_event, kernel
    timestamps used for ALL gesture arithmetic (R4);
  * /tmp/game-session and /tmp/game-suspended - via an inotify watch on the
    /tmp DIRECTORY filtered by name, so rename-writes are not missed;
  * the game's process tree - game-pids' logic ported in-process on psutil
    (R6: never a subprocess per tick);
  * X11 - window stacking/focus/class, via the read-only adapter in x11.py;
  * Kodi - a persistent notification socket on 127.0.0.1:9090 plus HTTP
    settings reads rate-limited to >= 10s, credentials from ~/couch/.env;
  * Steam's own logs - gameprocess_log.txt (the tracked-process ledger) and
    controller_ui.txt (menu routing), tailed (dev,ino,size)-aware.

What it writes (the only paths it ever touches):
  ~/couch/shadow/couchd-YYYYMMDD.jsonl     observations + intents + events
  ~/couch/shadow/snapshots-YYYYMMDD.jsonl  world snapshots (R8)
  ~/couch/shadow/status.json               atomic status for the phone
  ~/couch/shadow/couchd.lock               single-instance flock
  /tmp/couchd.log                          human one-liners, say() shape

Rollback is `systemctl --user stop couchd`; its absence is never an error.
"""
import asyncio
import contextlib
import errno
import fcntl
import json
import os
import re
import signal
import socket
import struct
import sys
import time
from dataclasses import dataclass, field, replace

HOME = os.path.expanduser('~')
COUCH = os.path.join(HOME, 'couch')
SHADOW_DIR = os.path.join(COUCH, 'shadow')
ENV_FILE = os.path.join(COUCH, '.env')
HUMAN_LOG = '/tmp/couchd.log'
LOCK_PATH = os.path.join(SHADOW_DIR, 'couchd.lock')

SESSION_FLAG = '/tmp/game-session'
SUSPENDED_FLAG = '/tmp/game-suspended'
VPAD_FIFO = '/tmp/vpad.fifo'
GUARD_PIDFILE = '/tmp/steam-input-guard.pid'
TMP_DIR = '/tmp'
WATCHED_TMP = {'game-session', 'game-suspended', 'vpad.fifo',
               'steam-input-guard.pid', 'tv-wake-request'}

# Steam's log directory, canonicalised ONCE (~/.steam/steam and
# ~/.steam/debian-installation are the same inode; R5 wants one path).
STEAM_LOGS = os.path.realpath(os.path.join(HOME, '.steam', 'steam', 'logs'))
GAMEPROCESS_LOG = os.path.join(STEAM_LOGS, 'gameprocess_log.txt')
CONTROLLER_UI_LOG = os.path.join(STEAM_LOGS, 'controller_ui.txt')

# -- timing (R6: supervisor loops never go below 1s outside attention) -----
TICK_SECONDS = 5.0            # anti-entropy tick (C16)
ATTENTION_PERIOD = 0.2        # sampling inside an attention window
ATTENTION_SECONDS = 3.0       # how long an observed change keeps us alert
MIN_PERIOD = 1.0              # floor outside attention windows
KODI_READ_INTERVAL = 10.0     # never faster, whatever the tick does
STATUS_INTERVAL = 3.0
SNAPSHOT_INTERVAL = 30.0
SNAPSHOT_MIN_GAP = 2.0        # attention-triggered snapshots are rate-limited
OBSERVER_STALE_SECONDS = 300.0

# -- model constants (ported from the scripts) ----------------------------
HOLD_SECONDS = 0.9            # pad-home-watcher's hold threshold
HANDOFF_TIMEOUT = 4.0         # its safety timeout when the release never comes
GUARD_WINDOW = 6.0            # steam-input-guard's enforcement window
MISSING_WINDOW_GRACE = 4.0    # C26
GONE_MISSES = 3               # C26: 3 consecutive misses before "gone"
PID_RESOLVER = 'couchd-psutil-tree'

UNKNOWN = 'unknown'
REGIONS = ('input_ownership', 'foreground', 'session', 'enforcement',
           'gesture', 'pad')

# per-app lifecycle (C26 + R4)
LIFECYCLE = ('LAUNCHING', 'STARTED', 'RUNNING', 'MISSING_WINDOW', 'FROZEN',
             'STOPPING', 'STOPPED', UNKNOWN)

EVENT_FORMAT = 'llHHi'        # struct input_event on x86_64
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)
EV_KEY = 0x01
BTN_MODE = 0x13c              # the PS button
PAD_WANTED = 'DualSense Wireless Controller'
PAD_UNWANTED = re.compile(r'Motion|Touchpad', re.I)

REAPER = 'reaper SteamLaunch'
SHAD = re.compile(r'Shadps4-sdl|mount_Shadps')


# =========================================================================
# environment / small helpers
# =========================================================================
def load_env(path=ENV_FILE):
    """~/couch/.env into os.environ without overriding what is already set.
    Same contract as tools/couchenv.py - credentials never live in source."""
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, val = line.partition('=')
        os.environ.setdefault(key.strip(), val.strip())


def say(msg):
    """One human line, in the same shape the other scripts use."""
    now = time.time()
    try:
        with open(HUMAN_LOG, 'a') as f:
            f.write(f"{time.strftime('%H:%M:%S', time.localtime(now))}"
                    f".{int(now % 1 * 1000):03d} {msg}\n")
    except OSError:
        pass


# =========================================================================
# pure model: observation
# =========================================================================
@dataclass(frozen=True)
class Observed:
    """Everything a decision may depend on. `None` in a scalar field means
    UNKNOWN (the source could not be read); the *_known flags say whether the
    source answered at all. Built by the daemon, but constructible by hand -
    reconcile() is a pure function of this and nothing else (C13)."""
    now: float = 0.0
    mono: float = 0.0

    # /tmp flags
    flags_known: bool = False
    session: dict = None                   # {'launcher_pid','mode','appid'}
    suspended: str = None                  # appid or 'bigpicture'

    # process tree
    pids_known: bool = False
    pid_states: dict = field(default_factory=dict)   # pid -> 'S'/'T'/...
    launcher_alive: bool = None

    # Kodi
    kodi_known: bool = False
    joystick: bool = None
    kodi_window: int = None                # currentwindow id (10106 = power)
    kodi_playing: bool = None

    # X11
    x_known: bool = False
    top_name: str = ''
    top_class: str = ''
    focused_class: str = ''
    kodi_window_present: bool = False
    big_picture_window: bool = False

    # Steam logs
    steam_known: bool = False
    steam_route: str = ''                  # last OnFocusWindowChanged text
    ui_mode: int = None                    # SSGL UI mode (4=BPM, 7=desktop)
    ledger: dict = field(default_factory=dict)      # appid -> tuple(pids)

    # pad / gesture (all times are KERNEL event timestamps, R4)
    pad_known: bool = False
    pad_present: bool = False
    button_down: bool = False
    down_since_k: float = None
    kernel_now: float = 0.0
    press_duration: float = None           # last completed press, seconds
    press_ended_at: float = None           # mono when that press ended

    # model state fed back in (maintained by Machine/daemon)
    regions: dict = field(default_factory=dict)
    region_since: dict = field(default_factory=dict)
    games: dict = field(default_factory=dict)        # appid -> lifecycle
    enforcement_target: str = None
    enforcement_until: float = 0.0
    recent: dict = field(default_factory=dict)       # intent key -> mono

    # -- derived conveniences (pure) --------------------------------------
    @property
    def session_present(self):
        return self.flags_known and self.session is not None

    @property
    def suspended_present(self):
        return self.flags_known and self.suspended is not None

    @property
    def session_mode(self):
        return (self.session or {}).get('mode', '')

    @property
    def running_pids(self):
        """Game pids that are actually executing ('T' means already frozen)."""
        return sorted(p for p, s in self.pid_states.items() if s != 'T')

    @property
    def frozen_pids(self):
        return sorted(p for p, s in self.pid_states.items() if s == 'T')

    @property
    def all_frozen(self):
        return bool(self.pid_states) and not self.running_pids

    @property
    def steam_menu_open(self):
        return 'ClientUI' in (self.steam_route or '')


def make_obs(**kw):
    """Terse constructor for tests and for the daemon: a quiescent, fully
    observed, Kodi-on-screen world with nothing running."""
    base = dict(
        now=1000.0, mono=1000.0,
        flags_known=True, session=None, suspended=None,
        pids_known=True, pid_states={}, launcher_alive=None,
        kodi_known=True, joystick=True, kodi_window=10000, kodi_playing=False,
        x_known=True, top_name='Kodi', top_class='Kodi', focused_class='Kodi',
        kodi_window_present=True, big_picture_window=False,
        steam_known=True, steam_route='', ui_mode=7, ledger={},
        pad_known=True, pad_present=True, button_down=False,
        down_since_k=None, kernel_now=1000.0, press_duration=None,
        press_ended_at=None,
        regions={'input_ownership': 'kodi', 'foreground': 'kodi',
                 'session': 'none', 'enforcement': 'none',
                 'gesture': 'idle', 'pad': 'present'},
        region_since={r: 0.0 for r in REGIONS},
        games={}, enforcement_target=None, enforcement_until=0.0, recent={})
    regions = dict(base['regions'])
    regions.update(kw.pop('regions', {}))
    base.update(kw)
    base['regions'] = regions
    return Observed(**base)


# =========================================================================
# pure model: intents
# =========================================================================
VERBS = ('freeze', 'thaw', 'route_pad', 'show', 'close_steam_menu', 'set_flag',
         'clear_flag', 'dismiss', 'launch', 'quit', 'kill', 'iconify',
         'request_tv_wake')
PID_VERBS = ('freeze', 'thaw', 'quit', 'kill')


@dataclass
class Intent:
    """One would-do. `requires` names the regions this decision depends on:
    if any of them is UNKNOWN the intent is suppressed (R4). `cooldown` is
    what makes a level-based reconciler safe in SHADOW mode - nothing we
    'do' changes the world, so without it every pass would re-emit."""
    verb: str
    subject: str = None
    args: dict = field(default_factory=dict)
    reason: str = ''
    predict: dict = None
    requires: tuple = ()
    cooldown: float = 30.0

    def __post_init__(self):
        assert self.verb in VERBS, f'unknown verb {self.verb}'
        if self.verb in PID_VERBS:
            assert 'pids' in self.args and 'resolver' in self.args, \
                f'{self.verb} must carry pids + resolver (R4)'

    @property
    def key(self):
        return f'{self.verb}|{self.subject}|{self.reason}'

    def human(self):
        bits = [self.verb]
        if self.subject:
            bits.append(str(self.subject))
        pids = self.args.get('pids')
        if pids:
            bits.append(f'({len(pids)} pid(s))')
        return f'would {" ".join(bits)} [{self.reason}]'


# =========================================================================
# pure model: transition table
# =========================================================================
def _since(o, region):
    return o.mono - o.region_since.get(region, o.mono)


def _recent(o, key, window):
    t = o.recent.get(key)
    return t is not None and (o.mono - t) < window


# --- guards: pure predicates over Observed --------------------------------
def g_pad_seen(o):
    return o.pad_known and o.pad_present


def g_pad_gone(o):
    return o.pad_known and not o.pad_present


def g_pad_unknown(o):
    return not o.pad_known


def g_button_down(o):
    return o.pad_known and o.button_down


def g_hold_reached(o):
    """0.9s measured between KERNEL timestamps (R4). kernel_now is anchored
    on the last kernel event and extrapolated with wall time for the gap, so
    a held button with no further reports still fires."""
    return (o.button_down and o.down_since_k is not None
            and (o.kernel_now - o.down_since_k) >= HOLD_SECONDS)


def g_released(o):
    return not o.button_down


def g_released_tap_resume(o):
    return (not o.button_down and o.press_duration is not None
            and o.press_duration < HOLD_SECONDS and o.suspended_present)


def g_handoff_emitted(o):
    return (_recent(o, 'route_pad|kodi|gesture:hold-release', 3.0)
            or _recent(o, 'route_pad|kodi|gesture:hold-release-timeout', 3.0))


def g_handoff_overdue(o):
    """The release never arrived (the pad died mid-hold, or the button is
    stuck): the watcher hands over anyway after 4s rather than stranding the
    pad. This is a wall/monotonic deadline, not a kernel one - it exists
    precisely because no further kernel events are coming."""
    return _since(o, 'gesture') > HANDOFF_TIMEOUT


def g_resume_emitted(o):
    return any(k.startswith('launch|') and k.endswith('|gesture:tap-resume')
               and (o.mono - t) < 3.0 for k, t in o.recent.items())


def g_gesture_stale(o):
    """Nothing pending and the button is up: fall back to idle."""
    return not o.button_down and _since(o, 'gesture') > HANDOFF_TIMEOUT * 2


def g_session_present(o):
    return o.session_present


def g_session_absent(o):
    return o.flags_known and o.session is None


def g_session_live(o):
    return bool(o.pid_states) or o.big_picture_window


def g_session_grace_over(o):
    return _since(o, 'session') > 30.0


def g_launcher_dead_no_game(o):
    return (o.session_present and o.launcher_alive is False
            and o.pids_known and not o.pid_states)


def g_ending_done(o):
    return _since(o, 'session') > 5.0


def g_flags_unknown(o):
    return not o.flags_known


def g_joystick_true(o):
    return o.kodi_known and o.joystick is True


def g_joystick_false_menu(o):
    return (o.kodi_known and o.joystick is False and o.steam_menu_open
            and o.focused_class != 'steamwebhelper')


def g_joystick_false(o):
    return o.kodi_known and o.joystick is False


def g_kodi_unknown(o):
    return not o.kodi_known or o.joystick is None


def g_x_unknown(o):
    return not o.x_known


def g_fg_kodi(o):
    return o.x_known and o.top_name == 'Kodi'


def g_fg_bigpicture(o):
    return o.x_known and 'Big Picture' in (o.top_name or '')


def g_fg_game(o):
    return o.x_known and (o.top_class or '').startswith('steam_app')


def g_fg_other(o):
    return o.x_known


def g_enf_expired(o):
    return o.mono >= o.enforcement_until


def g_enf_kodi(o):
    return o.enforcement_target == 'kodi' and o.mono < o.enforcement_until


def g_enf_game(o):
    return o.enforcement_target == 'game' and o.mono < o.enforcement_until


GUARDS = {n[2:]: f for n, f in list(globals().items()) if n.startswith('g_')}

# The whole state machine as DATA: {region: {state: [(guard, next, reason)]}}.
# Being data buys the JSON dump, the mermaid export, and reasons-as-values
# for free; the "why" never hides inside a callback.
TRANSITIONS = {
    'pad': {
        UNKNOWN: [('pad_seen', 'present', 'pad-appeared'),
                  ('pad_gone', 'absent', 'no-pad')],
        'absent': [('pad_unknown', UNKNOWN, 'pad-observer-blind'),
                   ('pad_seen', 'present', 'pad-appeared')],
        'present': [('pad_unknown', UNKNOWN, 'pad-observer-blind'),
                    ('pad_gone', 'absent', 'pad-disconnected')],
    },
    'gesture': {
        UNKNOWN: [('pad_unknown', UNKNOWN, 'pad-observer-blind'),
                  ('button_down', 'down', 'ps-press'),
                  ('released', 'idle', 'pad-quiet')],
        'idle': [('pad_unknown', UNKNOWN, 'pad-observer-blind'),
                 ('button_down', 'down', 'ps-press')],
        'down': [('hold_reached', 'hold-fired', 'ps-held-0.9s'),
                 ('released_tap_resume', 'tap-resume', 'ps-tap-with-paused-game'),
                 ('released', 'idle', 'ps-tap-noop')],
        'hold-fired': [('released', 'handoff-pending', 'ps-released-after-hold'),
                       ('handoff_overdue', 'timed-out', 'release-never-came')],
        'handoff-pending': [('handoff_emitted', 'idle', 'handoff-decided'),
                            ('handoff_overdue', 'timed-out', 'release-never-came')],
        'timed-out': [('handoff_emitted', 'idle', 'handoff-decided'),
                      ('gesture_stale', 'idle', 'gesture-abandoned')],
        'tap-resume': [('resume_emitted', 'idle', 'resume-decided'),
                       ('gesture_stale', 'idle', 'gesture-abandoned')],
    },
    'session': {
        UNKNOWN: [('flags_unknown', UNKNOWN, 'flags-unreadable'),
                  ('session_present', 'starting', 'session-flag-appeared'),
                  ('session_absent', 'none', 'no-session-flag')],
        'none': [('flags_unknown', UNKNOWN, 'flags-unreadable'),
                 ('session_present', 'starting', 'session-flag-appeared')],
        'starting': [('flags_unknown', UNKNOWN, 'flags-unreadable'),
                     ('session_absent', 'ending', 'session-flag-gone'),
                     ('session_live', 'active', 'game-processes-up'),
                     ('session_grace_over', 'active', 'launch-grace-expired')],
        'active': [('flags_unknown', UNKNOWN, 'flags-unreadable'),
                   ('session_absent', 'ending', 'session-flag-gone'),
                   ('launcher_dead_no_game', 'orphaned', 'launcher-gone-no-game')],
        'orphaned': [('flags_unknown', UNKNOWN, 'flags-unreadable'),
                     ('session_absent', 'none', 'session-flag-gone')],
        'ending': [('flags_unknown', UNKNOWN, 'flags-unreadable'),
                   ('session_present', 'starting', 'session-flag-reappeared'),
                   ('ending_done', 'none', 'session-ended')],
    },
    'input_ownership': {
        UNKNOWN: [('kodi_unknown', UNKNOWN, 'kodi-unreadable'),
                  ('joystick_false_menu', 'steam-menu', 'steam-holds-the-pad'),
                  ('joystick_true', 'kodi', 'joystick-enabled'),
                  ('joystick_false', 'game', 'joystick-disabled')],
        'kodi': [('kodi_unknown', UNKNOWN, 'kodi-unreadable'),
                 ('joystick_false_menu', 'steam-menu', 'steam-holds-the-pad'),
                 ('joystick_false', 'game', 'joystick-disabled')],
        'game': [('kodi_unknown', UNKNOWN, 'kodi-unreadable'),
                 ('joystick_false_menu', 'steam-menu', 'steam-holds-the-pad'),
                 ('joystick_true', 'kodi', 'joystick-enabled')],
        'steam-menu': [('kodi_unknown', UNKNOWN, 'kodi-unreadable'),
                       ('joystick_true', 'kodi', 'joystick-enabled'),
                       ('joystick_false', 'game', 'steam-menu-closed')],
    },
    'foreground': {
        UNKNOWN: [('x_unknown', UNKNOWN, 'x-unreachable'),
                  ('fg_kodi', 'kodi', 'kodi-on-top'),
                  ('fg_bigpicture', 'bigpicture', 'big-picture-on-top'),
                  ('fg_game', 'game', 'game-window-on-top'),
                  ('fg_other', 'other', 'something-else-on-top')],
        'kodi': [('x_unknown', UNKNOWN, 'x-unreachable'),
                 ('fg_bigpicture', 'bigpicture', 'big-picture-on-top'),
                 ('fg_game', 'game', 'game-window-on-top'),
                 ('fg_kodi', 'kodi', 'kodi-on-top'),
                 ('fg_other', 'other', 'something-else-on-top')],
        'game': [('x_unknown', UNKNOWN, 'x-unreachable'),
                 ('fg_kodi', 'kodi', 'kodi-on-top'),
                 ('fg_bigpicture', 'bigpicture', 'big-picture-on-top'),
                 ('fg_game', 'game', 'game-window-on-top'),
                 ('fg_other', 'other', 'something-else-on-top')],
        'bigpicture': [('x_unknown', UNKNOWN, 'x-unreachable'),
                       ('fg_kodi', 'kodi', 'kodi-on-top'),
                       ('fg_game', 'game', 'game-window-on-top'),
                       ('fg_bigpicture', 'bigpicture', 'big-picture-on-top'),
                       ('fg_other', 'other', 'something-else-on-top')],
        'other': [('x_unknown', UNKNOWN, 'x-unreachable'),
                  ('fg_kodi', 'kodi', 'kodi-on-top'),
                  ('fg_bigpicture', 'bigpicture', 'big-picture-on-top'),
                  ('fg_game', 'game', 'game-window-on-top')],
    },
    'enforcement': {
        UNKNOWN: [('enf_kodi', 'kodi', 'guard-window-kodi'),
                  ('enf_game', 'game', 'guard-window-game'),
                  ('enf_expired', 'none', 'no-guard-window')],
        'none': [('enf_kodi', 'kodi', 'guard-window-kodi'),
                 ('enf_game', 'game', 'guard-window-game')],
        'kodi': [('enf_game', 'game', 'guard-window-superseded'),
                 ('enf_expired', 'none', 'guard-window-expired')],
        'game': [('enf_kodi', 'kodi', 'guard-window-superseded'),
                 ('enf_expired', 'none', 'guard-window-expired')],
    },
}


class Machine:
    """Regions + the one chokepoint every transition passes through (C15)."""

    def __init__(self, on_transition=None):
        self.regions = {r: UNKNOWN for r in REGIONS}
        self.since = {r: 0.0 for r in REGIONS}
        self.games = {}
        self._game_since = {}
        self._misses = {}
        self.on_transition = on_transition or (lambda *a: None)

    def transit(self, region, to, reason, mono):
        frm = self.regions.get(region, UNKNOWN)
        if frm == to:
            return False
        self.regions[region] = to
        self.since[region] = mono
        self.on_transition(region, frm, to, reason)
        return True

    def step(self, o):
        """Apply the table once per region. Guards see the observation with
        the CURRENT regions, so ordering inside a pass cannot matter."""
        for region in REGIONS:
            state = self.regions.get(region, UNKNOWN)
            rules = TRANSITIONS[region].get(state, ())
            for guard_name, nxt, reason in rules:
                if GUARDS[guard_name](o):
                    if nxt != state:
                        self.transit(region, nxt, reason, o.mono)
                    break
        self._step_games(o)
        return self.regions

    # -- dynamic per-app lifecycle map (R4/C26) ---------------------------
    def _step_games(self, o):
        seen = {}
        # Steam's ledger is the primary identity source (C24); the process
        # tree is the fallback and the state (S/T) source.
        for appid, pids in (o.ledger or {}).items():
            alive = [p for p in pids if p in o.pid_states]
            seen[appid] = alive
        if o.session_present:
            appid = o.session.get('appid') or o.session.get('mode') or 'session'
            seen.setdefault(appid, sorted(o.pid_states))
        if not seen and o.pid_states and o.suspended:
            seen[o.suspended] = sorted(o.pid_states)
        for appid, pids in seen.items():
            states = [o.pid_states.get(p) for p in pids if p in o.pid_states]
            if not o.pids_known:
                nxt, reason = UNKNOWN, 'process-observer-blind'
            elif not states:
                self._misses[appid] = self._misses.get(appid, 0) + 1
                if self._misses[appid] >= GONE_MISSES:
                    nxt, reason = 'STOPPED', 'no-processes-3-checks'
                else:
                    nxt, reason = 'LAUNCHING', 'session-without-processes-yet'
            else:
                self._misses[appid] = 0
                if all(s == 'T' for s in states):
                    nxt, reason = 'FROZEN', 'all-processes-stopped'
                elif (o.x_known and not o.top_class.startswith('steam_app')
                      and not o.big_picture_window
                      and o.mono - self._game_since.get(appid, o.mono)
                      > MISSING_WINDOW_GRACE and o.suspended is None):
                    nxt, reason = 'MISSING_WINDOW', 'processes-without-a-window'
                else:
                    nxt, reason = 'RUNNING', 'processes-running'
            cur = self.games.get(appid, UNKNOWN)
            if cur != nxt:
                self.games[appid] = nxt
                self._game_since[appid] = o.mono
                self.on_transition(f'game:{appid}', cur, nxt, reason)
        for appid in list(self.games):
            if appid not in seen and self.games[appid] != 'STOPPED':
                self.on_transition(f'game:{appid}', self.games[appid],
                                   'STOPPED', 'left-the-world')
                self.games[appid] = 'STOPPED'


# =========================================================================
# pure model: reconcile
# =========================================================================
def resolve_appid(o):
    """Who is "the game"? Steam's ledger beats the session flag's mode
    string, which is what fixes legacy bug R7(b): a game launched from
    inside Big Picture is recorded by game-launch as the literal string
    "bigpicture", so its own Kodi tile CLOSES it instead of resuming it."""
    live = [a for a, st in (o.games or {}).items()
            if st in ('RUNNING', 'FROZEN', 'MISSING_WINDOW', 'STARTED',
                      'LAUNCHING')]
    real = [a for a in live if a not in ('bigpicture', 'session', '')]
    if len(real) == 1:
        return real[0]
    ledger_real = [a for a in (o.ledger or {}) if a and a != 'bigpicture']
    if len(ledger_real) == 1 and (o.ledger[ledger_real[0]] or o.pid_states):
        return ledger_real[0]
    sess_appid = (o.session or {}).get('appid')
    if sess_appid and sess_appid != 'bigpicture':
        return sess_appid
    if real:
        return sorted(real)[0]
    if o.suspended and o.suspended != 'bigpicture':
        return o.suspended
    return sess_appid or o.suspended or (o.session or {}).get('mode') or None


def want_pad_owner(o):
    """Where the pad SHOULD be, level-based.

    The legacy formula is `want_kodi = not (session and not suspended)`,
    which is what makes legacy bug R7(a) bite: a pure Big Picture hold never
    writes /tmp/game-suspended (freeze_game only writes it inside `if
    pids:`), so ten seconds later reconcile decides the pad belongs to a
    "game" that is behind Kodi - the pad ends up routed to nobody. couchd
    asks instead whether anything is actually in front of the room."""
    if not o.session_present:
        return 'kodi'
    if o.suspended_present:
        return 'kodi'
    if o.running_pids:
        return 'game'
    if o.x_known and (o.big_picture_window or o.top_class.startswith('steam_app')):
        # Big Picture / the game is genuinely on screen
        if o.top_name == 'Kodi':
            return 'kodi'
        return 'game'
    if not o.x_known and o.pid_states:
        return 'game'
    return 'kodi'


def _pred(effect, deadline):
    return {'effect': effect, 'deadline_s': deadline}


def reconcile(o):
    """PURE. observed -> [intent]. No event argument (C13), no I/O.

    Four responsibilities, in the order the old stack runs them:
      1. gestures        (pad-home-watcher)
      2. transitions     (game-launch)
      3. enforcement     (steam-input-guard's four invariants)
      4. drift repairs   (the watcher's reconcile(), five repairs)
    """
    out = []
    g = o.regions.get('gesture', UNKNOWN)
    sess = o.regions.get('session', UNKNOWN)
    enf = o.regions.get('enforcement', UNKNOWN)
    appid = resolve_appid(o)
    running = o.running_pids

    # -- 1. gestures ------------------------------------------------------
    if g == 'hold-fired':
        if running:
            out.append(Intent(
                'freeze', appid,
                {'pids': running, 'resolver': PID_RESOLVER, 'signal': 'SIGSTOP',
                 'mode': o.session_mode},
                'gesture:ps-hold',
                _pred('all game pids in state T', 5.0),
                requires=('gesture', 'session'), cooldown=3.0))
            out.append(Intent(
                'set_flag', 'suspended', {'value': appid},
                'gesture:ps-hold', _pred('/tmp/game-suspended exists', 2.0),
                requires=('gesture', 'session'), cooldown=3.0))
        elif o.session_mode == 'bigpicture' or o.regions.get('foreground') == 'bigpicture':
            # R7(a) done RIGHT: record the suspend even though there is
            # nothing to freeze, so the joystick repair below can never
            # decide the pad belongs to an invisible Big Picture.
            out.append(Intent(
                'set_flag', 'suspended', {'value': 'bigpicture', 'pids': []},
                'gesture:ps-hold-bigpicture',
                _pred('/tmp/game-suspended exists', 2.0),
                requires=('gesture', 'session'), cooldown=3.0))

    if g in ('handoff-pending', 'timed-out'):
        reason = ('gesture:hold-release' if g == 'handoff-pending'
                  else 'gesture:hold-release-timeout')
        out.append(Intent('route_pad', 'kodi', {'via': 'kodi-jsonrpc'}, reason,
                          _pred('input.enablejoystick true', 2.0),
                          requires=('gesture', 'input_ownership'), cooldown=3.0))
        out.append(Intent('show', 'kodi', {'via': 'xlib-restack'}, reason,
                          _pred('top window is Kodi', 2.0),
                          requires=('gesture', 'foreground'), cooldown=3.0))
        out.append(Intent('close_steam_menu', 'steam',
                          {'via': 'vpad-guide', 'window_s': GUARD_WINDOW}, reason,
                          _pred('steam menu not routed', 6.0),
                          requires=('gesture',), cooldown=3.0))

    if g == 'tap-resume':
        out.append(Intent('launch', appid,
                          {'mode': 'resume', 'via': 'game-launch resume',
                           'suspended_flag': o.suspended},
                          'gesture:tap-resume',
                          _pred('game pids back in state S', 5.0),
                          requires=('gesture', 'session'), cooldown=3.0))
        if o.kodi_window == 10106:
            out.append(Intent('dismiss', 'power-menu', {'via': 'Input.Back'},
                              'gesture:tap-resume',
                              _pred('currentwindow != 10106', 2.0),
                              requires=('gesture',), cooldown=3.0))

    # -- 2. transitions ---------------------------------------------------
    if sess == 'starting':
        out.append(Intent('route_pad', 'game',
                          {'via': 'kodi-jsonrpc', 'mode': o.session_mode},
                          'transition:session-started',
                          _pred('input.enablejoystick false', 2.0),
                          requires=('session', 'input_ownership'), cooldown=10.0))
        out.append(Intent('show', appid or 'game',
                          {'via': 'xlib-restack', 'mode': o.session_mode},
                          'transition:session-started',
                          _pred('game window on top', 10.0),
                          requires=('session', 'foreground'), cooldown=10.0))
        out.append(Intent('request_tv_wake', 'tv', {'via': '/tmp/tv-wake-request'},
                          'transition:session-started',
                          _pred('tv on, input PC', 10.0),
                          requires=('session',), cooldown=30.0))
    if sess == 'ending':
        out.append(Intent('route_pad', 'kodi', {'via': 'kodi-jsonrpc'},
                          'transition:session-ended',
                          _pred('input.enablejoystick true', 2.0),
                          requires=('session', 'input_ownership'), cooldown=10.0))
        out.append(Intent('show', 'kodi', {'via': 'xlib-restack'},
                          'transition:session-ended',
                          _pred('top window is Kodi', 2.0),
                          requires=('session', 'foreground'), cooldown=10.0))

    # -- 3. enforcement window (steam-input-guard's invariants) -----------
    if enf in ('kodi', 'game'):
        if o.steam_menu_open and o.focused_class != 'steamwebhelper':
            out.append(Intent('close_steam_menu', 'steam',
                              {'via': 'vpad-guide', 'invariant': 1,
                               'route': o.steam_route[-60:]},
                              'guard:steam-menu-holds-the-pad',
                              _pred('routing leaves ClientUI', 3.0),
                              requires=('enforcement', 'foreground'), cooldown=5.0))
        if enf == 'kodi' and o.x_known and o.top_name != 'Kodi':
            out.append(Intent('show', 'kodi',
                              {'via': 'xlib-restack', 'invariant': 2,
                               'top': o.top_name or '?'},
                              'guard:wanted-window-not-on-top',
                              _pred('top window is Kodi', 2.0),
                              requires=('enforcement', 'foreground'), cooldown=5.0))
        if (enf == 'game' and o.x_known and o.top_name == 'Kodi'
                and not o.suspended_present):
            out.append(Intent('show', appid or 'game',
                              {'via': 'game-launch focus', 'invariant': 2,
                               'top': o.top_name},
                              'guard:kodi-on-top-mid-game',
                              _pred('game window on top', 2.0),
                              requires=('enforcement', 'foreground'), cooldown=5.0))
        if o.suspended_present and o.x_known and o.top_class.startswith('steam_app'):
            out.append(Intent('show', 'kodi',
                              {'via': 'xlib-restack', 'invariant': 3,
                               'topclass': o.top_class},
                              'guard:frozen-game-visible',
                              _pred('top window is Kodi', 2.0),
                              requires=('enforcement', 'foreground'), cooldown=5.0))
        if not o.suspended_present and o.all_frozen and o.pids_known:
            out.append(Intent('thaw', appid,
                              {'pids': o.frozen_pids, 'resolver': PID_RESOLVER,
                               'signal': 'SIGCONT', 'invariant': 4},
                              'guard:all-frozen-without-flag',
                              _pred('game pids back in state S', 3.0),
                              requires=('enforcement', 'session'), cooldown=5.0))

    # -- 4. drift repairs (the watcher's reconcile, five of them) ---------
    # Named invariant: no repair while a gesture is in flight - reconciling
    # mid-press is how Kodi ends up with a phantom held button.
    if g == 'idle':
        if sess == 'orphaned':
            out.append(Intent('clear_flag', 'session',
                              {'launcher_alive': False, 'pids': []},
                              'reconcile:orphaned-session',
                              _pred('/tmp/game-session gone', 2.0),
                              requires=('session',)))
            if o.suspended_present:
                out.append(Intent('clear_flag', 'suspended', {'pids': []},
                                  'reconcile:orphaned-session',
                                  _pred('/tmp/game-suspended gone', 2.0),
                                  requires=('session',)))
            out.append(Intent('route_pad', 'kodi', {'via': 'kodi-jsonrpc'},
                              'reconcile:orphaned-session',
                              _pred('input.enablejoystick true', 2.0),
                              requires=('session', 'input_ownership')))
            out.append(Intent('show', 'kodi', {'via': 'xlib-restack'},
                              'reconcile:orphaned-session',
                              _pred('top window is Kodi', 2.0),
                              requires=('session', 'foreground')))

        if (o.suspended_present and o.pids_known and not o.pid_states
                and o.suspended != 'bigpicture'):
            out.append(Intent('clear_flag', 'suspended',
                              {'pids': [], 'resolver': PID_RESOLVER,
                               'was': o.suspended},
                              'reconcile:stale-suspended-flag',
                              _pred('/tmp/game-suspended gone', 2.0),
                              requires=('session',)))

        if not o.suspended_present and o.all_frozen and o.pids_known:
            out.append(Intent('thaw', appid,
                              {'pids': o.frozen_pids, 'resolver': PID_RESOLVER,
                               'signal': 'SIGCONT'},
                              'reconcile:frozen-without-suspended-flag',
                              _pred('game pids back in state S', 3.0),
                              requires=('session',)))

        want = want_pad_owner(o)
        have = o.regions.get('input_ownership')
        if o.kodi_known and o.joystick is not None and have in ('kodi', 'game') \
                and have != want:
            out.append(Intent('route_pad', want,
                              {'via': 'kodi-jsonrpc', 'was': o.joystick},
                              'reconcile:joystick-setting-drift',
                              _pred(f'input.enablejoystick {want == "kodi"}', 2.0),
                              requires=('input_ownership', 'session')))

        if o.suspended_present and o.x_known and o.top_class.startswith('steam_app'):
            out.append(Intent('show', 'kodi', {'via': 'xlib-restack',
                                               'topclass': o.top_class},
                              'reconcile:frozen-game-visible',
                              _pred('top window is Kodi', 2.0),
                              requires=('foreground', 'session')))

    return _filter(o, out)


def _filter(o, intents):
    """R4's suppression rules, applied in one place so they are checkable."""
    keep, seen = [], set()
    for it in intents:
        if any(o.regions.get(r, UNKNOWN) == UNKNOWN for r in it.requires):
            continue
        if it.reason.startswith('reconcile:') and o.regions.get('gesture') != 'idle':
            continue
        if _recent(o, it.key, it.cooldown):
            continue
        if it.key in seen:
            continue
        seen.add(it.key)
        keep.append(it)
    return keep


# =========================================================================
# invariants (Sismic's contract vocabulary: pre/post/invariant lists)
# =========================================================================
def check_invariants(o, intents):
    """Returns a list of (name, detail) violations. Closure + convergence
    (C19): once legal, stay legal; from anywhere, reach a fixpoint."""
    bad = []
    for region, state in o.regions.items():
        if region.startswith('game:'):
            continue
        if region not in TRANSITIONS:
            bad.append(('region_exists', region))
        elif state not in TRANSITIONS[region] and state != UNKNOWN:
            bad.append(('legal_state', f'{region}={state}'))
    if o.regions.get('gesture') != 'idle':
        for it in intents:
            if it.reason.startswith('reconcile:'):
                bad.append(('no_repair_during_gesture', it.key))
    for it in intents:
        for r in it.requires:
            if o.regions.get(r, UNKNOWN) == UNKNOWN:
                bad.append(('no_intent_for_unknown_region', f'{it.key} needs {r}'))
    for it in intents:
        if it.verb in PID_VERBS and 'pids' not in it.args:
            bad.append(('pid_verbs_carry_pids', it.key))
    # convergence: feeding our own decisions back must reach a fixpoint
    recent = dict(o.recent)
    for it in intents:
        recent[it.key] = o.mono
    again = reconcile(replace(o, recent=recent))
    if again:
        bad.append(('convergence', ','.join(i.key for i in again)))
    return bad


def freeze_set_agreement(o, ledger_pids, tree_pids):
    """R4's continuous metric: couchd's would-freeze set vs the psutil port of
    game-pids vs Steam's own ledger, every tick, transition or not. Verb-level
    diffing alone would have been blind to the audit's Proton fix."""
    mine = set(o.running_pids)
    tree = set(tree_pids)
    led = set(ledger_pids)
    covered = mine | set(o.frozen_pids)      # what couchd accounts for at all
    return {
        'couchd_would_freeze': sorted(mine),
        'game_pids_tree': sorted(tree),
        'steam_ledger': sorted(led),
        'tree_minus_couchd': sorted(tree - covered),
        'ledger_minus_tree': sorted(led - tree),
        'tree_minus_ledger': sorted(tree - led),
        'agree': not (tree - covered) and not (led - tree),
    }


# =========================================================================
# effects: the executor interface (C3/C18) - shadow only
# =========================================================================
class Executor:
    """The seam every effect would pass through. There is deliberately no
    acting implementation anywhere in this codebase (R1): stage 1 cannot act
    even by accident."""

    def execute(self, intent, obs):
        raise NotImplementedError


class RecordingExecutor(Executor):
    def __init__(self, log, on_record=None):
        self.log = log
        self.on_record = on_record or (lambda i: None)
        self.count = 0

    def execute(self, intent, obs):
        rec = {
            'kind': 'intent',
            't': obs.now, 'mono': obs.mono,
            'verb': intent.verb, 'subject': intent.subject,
            'args': intent.args, 'reason': intent.reason,
            'regions': {k: v for k, v in obs.regions.items()},
            'predict': intent.predict,
        }
        self.log.write(rec)
        self.count += 1
        self.on_record(intent)
        say(intent.human())
        return rec


# =========================================================================
# output: shadow log, snapshots, status
# =========================================================================
class ShadowLog:
    """Append-only JSONL we own (C21): monotonic seq + monotonic clock + wall
    clock on every record. flush always, fsync when idle."""

    def __init__(self, directory=SHADOW_DIR, prefix='couchd'):
        self.dir = directory
        self.prefix = prefix
        os.makedirs(directory, exist_ok=True)
        self.seq = 0
        self._day = None
        self._f = None
        self._dirty = False
        self.counts = {}

    def _file(self):
        day = time.strftime('%Y%m%d')
        if day != self._day or self._f is None:
            if self._f:
                self._f.flush()
                os.fsync(self._f.fileno())
                self._f.close()
            self._day = day
            self._f = open(os.path.join(self.dir, f'{self.prefix}-{day}.jsonl'),
                           'a', buffering=1)
        return self._f

    def write(self, rec):
        self.seq += 1
        rec.setdefault('t', time.time())
        rec.setdefault('mono', time.monotonic())
        rec['seq'] = self.seq
        kind = rec.get('kind', '?')
        self.counts[kind] = self.counts.get(kind, 0) + 1
        try:
            f = self._file()
            f.write(json.dumps(rec, default=str) + '\n')
            f.flush()
            self._dirty = True
        except OSError as e:
            say(f'shadow log write failed: {e}')
        return rec

    def sync_if_idle(self):
        if self._dirty and self._f is not None:
            try:
                os.fsync(self._f.fileno())
            except OSError:
                pass
            self._dirty = False

    def close(self):
        if self._f is not None:
            try:
                self._f.flush()
                os.fsync(self._f.fileno())
            except OSError:
                pass
            self._f.close()
            self._f = None


def write_atomic(path, text):
    tmp = f'{path}.tmp.{os.getpid()}'
    with open(tmp, 'w') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# =========================================================================
# observers - every one of them read-only
# =========================================================================
class Source:
    def __init__(self, name):
        self.name = name
        self.ok = False
        self.last_update = 0.0
        self.last_change = 0.0
        self.events = 0
        self.detail = ''
        self.blind_reported = False

    def touch(self, ok=True, detail=''):
        self.ok = ok
        self.last_update = time.monotonic()
        self.detail = detail

    def health(self, mono):
        age = mono - self.last_update if self.last_update else None
        return {'ok': self.ok, 'events': self.events, 'detail': self.detail,
                'age_s': round(age, 1) if age is not None else None,
                'stale': bool(age is not None and age > OBSERVER_STALE_SECONDS)}


class PadObserver:
    """DualSense BTN_MODE, read-only, never grabbed. pad-record's device
    discovery, pad-home-watcher's raw struct parsing, kernel timestamps."""

    def __init__(self, world):
        self.w = world
        self.src = world.src('pad')
        self.fds = {}
        self.present = False
        self.button_down = False
        self.down_since_k = None
        self.last_k = 0.0            # last kernel timestamp seen
        self.last_k_wall = 0.0       # wall clock when we saw it
        self.press_duration = None
        self.press_ended_at = None
        self.first_event_latency = None    # R5: pad-appearance -> first event
        self.presses = 0                   # cross-checked against Steam's log
        self._appeared_at = None

    @staticmethod
    def find_pads():
        nodes = {}
        try:
            blocks = open('/proc/bus/input/devices').read().split('\n\n')
        except OSError:
            return nodes
        for b in blocks:
            m = re.search(r'N: Name="([^"]*)"', b)
            if not m or PAD_WANTED not in m.group(1) or PAD_UNWANTED.search(m.group(1)):
                continue
            h = re.search(r'H: Handlers=.*?(event\d+)', b)
            if h:
                nodes['/dev/input/' + h.group(1)] = m.group(1)
        return nodes

    def kernel_now(self):
        """Kernel timebase, extrapolated over the gap since the last event.
        All gesture arithmetic stays in this timebase (R4); without the
        extrapolation a held button with no further reports never fires."""
        if not self.last_k:
            return time.time()
        return self.last_k + (time.time() - self.last_k_wall)

    async def run(self, loop):
        while True:
            try:
                self._rescan(loop)
                self.src.touch(True, f'{len(self.fds)} node(s)')
            except Exception as e:
                self.src.touch(False, f'{type(e).__name__}: {e}')
            await asyncio.sleep(2.0)

    def _rescan(self, loop):
        nodes = self.find_pads()
        for path in list(self.fds):
            if path not in nodes:
                self._drop(loop, path, 'disconnected')
        for path in nodes:
            if path in self.fds:
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except PermissionError:
                self.src.touch(False, 'no permission (dualsense udev rule?)')
                continue
            except OSError as e:
                self.src.touch(False, str(e))
                continue
            self.fds[path] = fd
            self._appeared_at = time.monotonic()
            loop.add_reader(fd, self._readable, loop, path, fd)
            self.w.log.write({'kind': 'obs', 'source': 'pad', 'event': 'node-open',
                              'node': path})
            self.w.attention('pad-appeared')
        self.present = bool(self.fds)

    def _drop(self, loop, path, why):
        fd = self.fds.pop(path, None)
        if fd is not None:
            with contextlib.suppress(Exception):
                loop.remove_reader(fd)
            with contextlib.suppress(OSError):
                os.close(fd)
            self.w.log.write({'kind': 'obs', 'source': 'pad',
                              'event': 'node-close', 'node': path, 'why': why})
        self.present = bool(self.fds)
        if not self.fds:
            self.button_down = False
            self.down_since_k = None

    def _readable(self, loop, path, fd):
        try:
            data = os.read(fd, EVENT_SIZE * 64)
        except BlockingIOError:
            return
        except OSError:
            self._drop(loop, path, 'read error')
            self.w.attention('pad-gone')
            return
        if not data:
            self._drop(loop, path, 'eof')
            self.w.attention('pad-gone')
            return
        for off in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
            sec, usec, etype, code, value = struct.unpack_from(EVENT_FORMAT,
                                                              data, off)
            k = sec + usec / 1e6
            self.last_k, self.last_k_wall = k, time.time()
            self.src.events += 1
            if etype == EV_KEY and code == BTN_MODE:
                if self._appeared_at is not None:
                    self.first_event_latency = time.monotonic() - self._appeared_at
                    self._appeared_at = None
                    self.w.log.write({'kind': 'obs', 'source': 'pad',
                                      'event': 'first-event-latency',
                                      'seconds': round(self.first_event_latency, 3)})
                self.presses += (1 if value == 1 else 0)
                if value == 1:
                    self.button_down = True
                    self.down_since_k = k
                elif value == 0:
                    if self.down_since_k is not None:
                        self.press_duration = k - self.down_since_k
                        self.press_ended_at = time.monotonic()
                    self.button_down = False
                    self.down_since_k = None
                self.w.log.write({'kind': 'obs', 'source': 'pad',
                                  'event': 'BTN_MODE', 'value': value,
                                  'kernel_t': round(k, 6),
                                  'duration': (round(self.press_duration, 3)
                                               if value == 0 and self.press_duration
                                               else None)})
                self.w.attention('ps-button')
                self.src.last_change = time.monotonic()

    def close(self, loop):
        for path in list(self.fds):
            self._drop(loop, path, 'shutdown')


class FlagObserver:
    """The /tmp shared truth. Watches the DIRECTORY filtered by name, because
    inotify follows inodes and these files are rewritten by rename."""

    def __init__(self, world):
        self.w = world
        self.src = world.src('flags')
        self.state = {}          # name -> (content, mtime)
        self.read_all()

    def read_all(self):
        changed = []
        for name in sorted(WATCHED_TMP):
            path = os.path.join(TMP_DIR, name)
            try:
                content = open(path).read().strip()
                mtime = os.stat(path).st_mtime
            except OSError:
                content, mtime = None, None
            prev = self.state.get(name)
            if prev is None or prev[0] != content:
                changed.append((name, content, mtime))
            self.state[name] = (content, mtime)
        self.src.touch(True, f'{sum(1 for v in self.state.values() if v[0] is not None)} present')
        for name, content, mtime in changed:
            self.src.events += 1
            self.src.last_change = time.monotonic()
            self.w.log.write({'kind': 'obs', 'source': 'flags', 'event': 'flag',
                              'name': name, 'value': content,
                              'mtime': round(mtime, 3) if mtime else None})
        return changed

    def session(self):
        raw = self.state.get('game-session', (None, None))[0]
        if raw is None:
            return None
        parts = raw.split()
        pid = None
        with contextlib.suppress(ValueError, IndexError):
            pid = int(parts[0])
        mode = parts[1] if len(parts) > 1 else ''
        appid = parts[2] if len(parts) > 2 and parts[2] else None
        return {'launcher_pid': pid, 'mode': mode, 'appid': appid, 'raw': raw}

    def suspended(self):
        return self.state.get('game-suspended', (None, None))[0]

    async def run(self):
        try:
            from asyncinotify import Inotify, Mask
        except ImportError:
            self.src.touch(False, 'asyncinotify missing; polling only')
            return
        mask = (Mask.CREATE | Mask.DELETE | Mask.MOVED_TO | Mask.MOVED_FROM |
                Mask.CLOSE_WRITE | Mask.MODIFY | Mask.ATTRIB)
        while True:
            try:
                with Inotify() as inot:
                    inot.add_watch(TMP_DIR, mask)
                    with contextlib.suppress(OSError):
                        inot.add_watch(STEAM_LOGS, Mask.MODIFY | Mask.CREATE |
                                       Mask.MOVED_TO)
                    self.src.touch(True, 'inotify up')
                    async for event in inot:
                        name = event.name.name if event.name else ''
                        if str(event.watch.path) == STEAM_LOGS:
                            self.w.attention('steam-log')
                            continue
                        if name in WATCHED_TMP:
                            self.read_all()
                            self.w.attention(f'flag:{name}')
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.src.touch(False, f'{type(e).__name__}: {e}')
                await asyncio.sleep(5)


class PidObserver:
    """game-pids' logic, in-process on psutil (R6). The identity of "the
    game" is tree membership under `reaper SteamLaunch` (plus shadPS4's
    AppImage names) - never cmdline path matching, which is failure 1 in the
    audit (Proton maps the library to S:, so eldenring.exe has no
    'steamapps' anywhere and the old pattern froze seven wrappers while the
    game played on)."""

    # M4 (box burden): a full psutil walk of this box costs ~57ms. Never at
    # attention rate; and with no session, no paused flag and an empty Steam
    # ledger, nothing depends on the tree faster than the anti-entropy tick.
    MIN_SCAN_INTERVAL = 1.0
    IDLE_SCAN_INTERVAL = 5.0

    def __init__(self, world):
        self.w = world
        self.src = world.src('pids')
        self.states = {}
        self.tree = []
        self.launcher_alive = None
        self._psutil = None
        self._last_scan = 0.0
        self._cmd_cache = {}     # pid -> (create_time, cmdline); PID-reuse safe

    def _ps(self):
        if self._psutil is None:
            import psutil
            self._psutil = psutil
        return self._psutil

    def scan(self, launcher_pid=None, force=False, busy=True):
        now = time.monotonic()
        interval = self.MIN_SCAN_INTERVAL if busy else self.IDLE_SCAN_INTERVAL
        if not force and now - self._last_scan < interval:
            return self.src.ok
        self._last_scan = now
        try:
            psutil = self._ps()
        except ImportError as e:
            self.src.touch(False, f'psutil missing: {e}')
            self.states, self.tree = {}, []
            return False
        me = os.getpid()
        procs, children, roots = {}, {}, set()
        seen_pids = set()
        try:
            for p in psutil.process_iter(['pid', 'ppid', 'status',
                                          'create_time']):
                try:
                    info = p.info
                except Exception:
                    continue
                pid = info['pid']
                procs[pid] = info
                seen_pids.add(pid)
                children.setdefault(info['ppid'] or 0, []).append(pid)
                if pid == me:
                    continue
                # cmdline is the expensive read; cache it against create_time
                # so a steady box costs almost nothing (M4 box burden).
                cached = self._cmd_cache.get(pid)
                if cached is not None and cached[0] == info['create_time']:
                    cmd = cached[1]
                else:
                    try:
                        cmd = ' '.join(p.cmdline() or ())
                    except Exception:
                        cmd = ''
                    self._cmd_cache[pid] = (info['create_time'], cmd)
                if REAPER in cmd or SHAD.search(cmd):
                    roots.add(pid)
        except Exception as e:
            self.src.touch(False, f'{type(e).__name__}: {e}')
            return False
        for dead in set(self._cmd_cache) - seen_pids:
            del self._cmd_cache[dead]
        out, stack = set(), list(roots)
        while stack:
            p = stack.pop()
            if p in out:
                continue
            out.add(p)
            stack.extend(children.get(p, ()))
        states = {}
        for pid in sorted(out):
            st = procs.get(pid, {}).get('status') or ''
            states[pid] = 'T' if st == psutil.STATUS_STOPPED else \
                {'sleeping': 'S', 'running': 'R', 'disk-sleep': 'D',
                 'zombie': 'Z', 'idle': 'I'}.get(st, st[:1].upper() or '?')
        changed = states != self.states
        self.states, self.tree = states, sorted(out)
        self.launcher_alive = (psutil.pid_exists(launcher_pid)
                               if launcher_pid else None)
        self.src.touch(True, f'{len(states)} pid(s)')
        if changed:
            self.src.events += 1
            self.src.last_change = time.monotonic()
            self.w.log.write({'kind': 'obs', 'source': 'pids',
                              'event': 'tree', 'pids': self.tree,
                              'states': {str(k): v for k, v in states.items()}})
            self.w.attention('pid-tree')
        return True


class KodiObserver:
    """Persistent JSON-RPC notification socket (127.0.0.1:9090) for events,
    plus HTTP reads rate-limited to >= 10s for the three settings the state
    machine needs. Credentials come from ~/couch/.env, never from source."""

    def __init__(self, world):
        self.w = world
        self.src = world.src('kodi')
        self.joystick = None
        self.window = None
        self.playing = None
        self.last_read = 0.0
        self.connected = False
        load_env()
        self.url = os.environ.get('KODI_URL', 'http://localhost:8090') + '/jsonrpc'
        self.user = os.environ.get('KODI_USER', 'kodi')
        self.password = os.environ.get('KODI_PASSWORD')
        self.host = os.environ.get('KODI_EVENT_HOST', '127.0.0.1')
        self.port = int(os.environ.get('KODI_EVENT_PORT', '9090'))

    # -- notifications ----------------------------------------------------
    async def run_notifications(self):
        backoff = 1.0
        decoder = json.JSONDecoder()
        while True:
            try:
                reader, writer = await asyncio.open_connection(self.host, self.port)
                self.connected = True
                self.src.touch(True, 'notification socket up')
                self.w.log.write({'kind': 'obs', 'source': 'kodi',
                                  'event': 'socket-connected'})
                backoff = 1.0
                buf = ''
                while True:
                    chunk = await reader.read(65536)
                    if not chunk:
                        raise ConnectionError('kodi closed the socket')
                    buf += chunk.decode('utf-8', 'replace')
                    while buf.strip():
                        try:
                            obj, idx = decoder.raw_decode(buf.lstrip())
                        except ValueError:
                            break
                        buf = buf.lstrip()[idx:]
                        self.src.events += 1
                        self.src.last_change = time.monotonic()
                        method = obj.get('method', '')
                        self.w.log.write({'kind': 'obs', 'source': 'kodi',
                                          'event': 'notification',
                                          'method': method,
                                          'params': obj.get('params')})
                        if method.startswith('Player.'):
                            self.playing = method in ('Player.OnPlay',
                                                      'Player.OnResume')
                        if method in ('GUI.OnScreensaverActivated',
                                      'Player.OnPlay', 'Player.OnStop',
                                      'Application.OnSettingsChanged'):
                            self.last_read = 0.0   # force a fresh settings read
                        # Add-ons chatter on this socket (jellyfin sends
                        # Other.KeepAlive); only the console's own vocabulary
                        # is worth an attention window.
                        if method.startswith(('Player.', 'GUI.', 'System.',
                                              'Application.', 'Input.')):
                            self.w.attention(f'kodi:{method}')
            except asyncio.CancelledError:
                with contextlib.suppress(Exception):
                    writer.close()
                raise
            except Exception as e:
                self.connected = False
                self.src.touch(False, f'{type(e).__name__}: {e}')
                with contextlib.suppress(Exception):
                    writer.close()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    # -- rate-limited settings reads --------------------------------------
    def _http(self, method, params):
        import base64
        import urllib.request
        body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method,
                           'params': params}).encode()
        req = urllib.request.Request(self.url, data=body,
                                     headers={'content-type': 'application/json'})
        if self.password:
            token = base64.b64encode(
                f'{self.user}:{self.password}'.encode()).decode()
            req.add_header('Authorization', 'Basic ' + token)
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def _read_all(self):
        js = self._http('Settings.GetSettingValue',
                        {'setting': 'input.enablejoystick'})
        joystick = js.get('result', {}).get('value')
        gui = self._http('GUI.GetProperties', {'properties': ['currentwindow']})
        window = gui.get('result', {}).get('currentwindow', {}).get('id')
        players = self._http('Player.GetActivePlayers', {})
        playing = bool(players.get('result'))
        return joystick, window, playing

    async def poll(self):
        """Never faster than KODI_READ_INTERVAL, whatever the tick does."""
        now = time.monotonic()
        if now - self.last_read < KODI_READ_INTERVAL:
            return
        self.last_read = now
        if not self.password:
            self.joystick = self.window = self.playing = None
            self.src.touch(False, 'KODI_PASSWORD not set (see .env)')
            return
        try:
            joystick, window, playing = await asyncio.to_thread(self._read_all)
        except Exception as e:
            # Kodi being down is normal (crash-restart windows): degrade the
            # region to unknown and let the observer-health heartbeat raise
            # the one observer_blind record, rather than one per read.
            self.joystick = self.window = self.playing = None
            self.src.touch(False, f'{type(e).__name__}: {e}')
            return
        changed = (joystick, window, playing) != (self.joystick, self.window,
                                                  self.playing)
        self.joystick, self.window, self.playing = joystick, window, playing
        self.src.touch(True, f'joystick={joystick} window={window}')
        if changed:
            self.src.events += 1
            self.src.last_change = time.monotonic()
            self.w.log.write({'kind': 'obs', 'source': 'kodi', 'event': 'settings',
                              'joystick': joystick, 'window': window,
                              'playing': playing})
            self.w.attention('kodi-settings')


class Tailer:
    """~40 lines of log tailing done properly: (dev, ino, size), and DRAIN
    THE OLD FD BEFORE REOPENING on rotation - the step naive versions miss.
    copytruncate (size shrank, same inode) seeks back to 0 and shouts."""

    SEED_BYTES = 256 * 1024   # replay this much history on the first open

    def __init__(self, path, world, name, seed=True):
        self.path = path
        self.w = world
        self.name = name
        self.f = None
        self.ino = None
        self.dev = None
        self.pos = 0
        self.last_line = 0.0
        self.seed = seed

    def _open(self, seek_end=True):
        """First open seeks BACK a little instead of to EOF: without it
        couchd starts blind to the routing state and the ledger until Steam
        writes its next line, which on a quiet evening can be hours."""
        try:
            f = open(self.path, 'r', encoding='utf-8', errors='replace')
            st = os.fstat(f.fileno())
        except OSError as e:
            self.f = None
            return f'{type(e).__name__}: {e}'
        if seek_end:
            if self.seed:
                f.seek(max(0, st.st_size - self.SEED_BYTES))
                if st.st_size > self.SEED_BYTES:
                    f.readline()          # drop the partial line
                self.seed = False
            else:
                f.seek(0, os.SEEK_END)
        self.f, self.ino, self.dev = f, st.st_ino, st.st_dev
        self.pos = f.tell()
        return None

    def read_new(self):
        """Yields new lines; handles rotation and truncation."""
        lines = []
        if self.f is None:
            err = self._open()
            if err:
                return lines, err
        # has the path been replaced under us?
        try:
            st = os.stat(self.path)
        except OSError as e:
            return lines, f'{type(e).__name__}: {e}'
        rotated = (st.st_ino, st.st_dev) != (self.ino, self.dev)
        truncated = st.st_size < self.pos
        for line in self.f:                       # drain the old fd first
            lines.append(line.rstrip('\n'))
        self.pos = self.f.tell()
        if rotated:
            self.f.close()
            err = self._open(seek_end=False)
            self.w.log.write({'kind': 'observer_blind', 'source': self.name,
                              'why': 'log rotated', 'path': self.path})
            if err:
                return lines, err
            for line in self.f:
                lines.append(line.rstrip('\n'))
            self.pos = self.f.tell()
        elif truncated:
            self.f.seek(0)
            self.w.log.write({'kind': 'observer_blind', 'source': self.name,
                              'why': 'log truncated (copytruncate)',
                              'path': self.path})
            for line in self.f:
                lines.append(line.rstrip('\n'))
            self.pos = self.f.tell()
        if lines:
            self.last_line = time.monotonic()
        return lines, None

    def close(self):
        if self.f is not None:
            with contextlib.suppress(OSError):
                self.f.close()
            self.f = None


class SteamObserver:
    """Steam's own two logs. gameprocess_log.txt is the authoritative tracked
    -process ledger (C24), controller_ui.txt is the only readable view of
    Steam's private menu/routing state."""

    ADD = re.compile(r'AppID (\d+) adding PID (\d+)')
    DROP = re.compile(r'AppID (\d+) no longer tracking PID (\d+)')
    REMOVE = re.compile(r'Remove (\d+) from running list')
    UIMODE = re.compile(r'SSGL: UI mode \((\d+)->(\d+)\)')
    FOCUS = re.compile(r'OnFocusWindowChanged to window type: (\S+?),? AppID (\d+)')

    def __init__(self, world):
        self.w = world
        self.src = world.src('steam')
        self.ledger = {}
        self.route = ''
        self.ui_mode = None
        self.game = Tailer(GAMEPROCESS_LOG, world, 'steam:gameprocess')
        self.ui = Tailer(CONTROLLER_UI_LOG, world, 'steam:controller_ui')
        self.silent_since = time.monotonic()
        # R5: Steam sees the PS button over hidraw, we see it over evdev. Two
        # independent channels for the same physical press; their counts
        # disagreeing means one of the two observers is blind.
        self.guide_presses = 0
        self._seeded = False

    def poll(self):
        errs = []
        changed = False
        lines, err = self.game.read_new()
        if err:
            errs.append(err)
        for line in lines:
            m = self.ADD.search(line)
            if m:
                self.ledger.setdefault(m.group(1), set()).add(int(m.group(2)))
                changed = True
                continue
            m = self.DROP.search(line)
            if m:
                self.ledger.get(m.group(1), set()).discard(int(m.group(2)))
                changed = True
                continue
            m = self.REMOVE.search(line)
            if m:
                self.ledger.pop(m.group(1), None)
                changed = True
                continue
            m = self.UIMODE.search(line)
            if m:
                self.ui_mode = int(m.group(2))
                changed = True
        lines, err = self.ui.read_new()
        if err:
            errs.append(err)
        for line in lines:
            if 'OnFocusWindowChanged' in line:
                self.route = line.strip()
                changed = True
            elif 'Guide button' in line:
                self.guide_presses += 1
                changed = True
        if not self._seeded:
            # The first read replays log history to learn the current ledger,
            # route and UI mode. Those are state; the guide-press COUNT is a
            # rate, and must start from this run, not from Steam's backlog.
            self._seeded = True
            self.guide_presses = 0
        if changed:
            self.src.events += 1
            self.src.last_change = time.monotonic()
            self.silent_since = time.monotonic()
            self.w.log.write({'kind': 'obs', 'source': 'steam', 'event': 'logs',
                              'ledger': {k: sorted(v) for k, v in self.ledger.items()},
                              'route': self.route[-90:], 'ui_mode': self.ui_mode})
            self.w.attention('steam-log')
        self.src.touch(not errs, '; '.join(errs) if errs else
                       f'{len(self.ledger)} app(s) tracked')
        return changed

    def ledger_pids(self):
        out = set()
        for pids in self.ledger.values():
            out |= pids
        return out

    def close(self):
        self.game.close()
        self.ui.close()


class TriggerObserver:
    """R4's trigger channels. What made the old stack act is often invisible
    in the world itself (a tile picked on the phone, a power-menu quit), and
    without it three of the four responsibilities produce unmatched
    legacy-only diffs forever. These lines are recorded as OBSERVATIONS for
    the differ's alignment and to open an attention window - they are never a
    source of intents, or couchd would just be echoing legacy's decisions."""

    MARK = re.compile(r'^\d\d:\d\d:\d\d(?:\.\d+)? === (.*)$')
    LOGS = {'game-launch': '/tmp/game-launch.log'}

    def __init__(self, world):
        self.w = world
        self.src = world.src('triggers')
        self.tails = {name: Tailer(path, world, f'trigger:{name}', seed=False)
                      for name, path in self.LOGS.items()}
        self.last = ''

    def poll(self):
        errs = []
        for name, tail in self.tails.items():
            lines, err = tail.read_new()
            if err:
                errs.append(f'{name}: {err}')
            for line in lines:
                m = self.MARK.match(line.strip())
                if not m:
                    continue
                self.last = m.group(1)
                self.src.events += 1
                self.src.last_change = time.monotonic()
                self.w.log.write({'kind': 'obs', 'source': 'trigger',
                                  'channel': name, 'text': m.group(1)})
                self.w.attention(f'trigger:{m.group(1)[:24]}')
        self.src.touch(not errs, '; '.join(errs) if errs else (self.last or 'quiet'))

    def close(self):
        for tail in self.tails.values():
            tail.close()


class X11Observer:
    def __init__(self, world):
        self.w = world
        self.src = world.src('x11')
        self.adapter = None
        self._fd = None
        self._next_connect = 0.0

    def _load(self):
        if self.adapter is None:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from x11 import X11Adapter
            os.environ.setdefault('DISPLAY', ':0')
            os.environ.setdefault('XAUTHORITY', os.path.join(HOME, '.Xauthority'))
            self.adapter = X11Adapter(os.environ.get('DISPLAY', ':0'))
        return self.adapter

    def attach(self, loop):
        """Connect (or reconnect) to X. A dead display must degrade the
        foreground region to `unknown` and keep the daemon alive, not
        crash-loop it, so failures back off instead of retrying per pass."""
        if time.monotonic() < self._next_connect:
            return
        try:
            a = self._load()
        except Exception as e:
            self._next_connect = time.monotonic() + 5.0
            self.src.touch(False, f'{type(e).__name__}: {e}')
            return
        if not a.connect():
            self._next_connect = time.monotonic() + 5.0
            self.src.touch(False, a.state.reason)
            self._detach(loop)
            return
        fd = a.fileno()
        if fd is not None and fd != self._fd:
            self._detach(loop)
            self._fd = fd
            with contextlib.suppress(Exception):
                loop.add_reader(fd, self._readable, loop)

    def _detach(self, loop):
        if self._fd is not None:
            with contextlib.suppress(Exception):
                loop.remove_reader(self._fd)
            self._fd = None

    def _readable(self, loop):
        try:
            if self.adapter.drain():
                self.src.events += 1
                self.src.last_change = time.monotonic()
                self.w.attention('x11-event')
            if self.adapter.d is None:      # adapter dropped the connection
                self._detach(loop)
        except Exception as e:
            self.src.touch(False, f'{type(e).__name__}: {e}')
            self._detach(loop)

    def poll(self, loop):
        if self.adapter is None or self.adapter.d is None:
            self.attach(loop)
        if self.adapter is None or self.adapter.d is None:
            return None
        st = self.adapter.refresh()
        self.src.touch(st.ok, st.reason or f'top={st.top_name!r}')
        return st

    def close(self, loop):
        self._detach(loop)
        if self.adapter is not None:
            self.adapter.close()


# =========================================================================
# the daemon
# =========================================================================
class World:
    """Shared observer state + the one place attention mode is triggered."""

    def __init__(self, log):
        self.log = log
        self.sources = {}
        self.attention_until = 0.0
        self.attention_reason = ''
        self.attention_events = 0
        self.wake = asyncio.Event()

    def src(self, name):
        return self.sources.setdefault(name, Source(name))

    def attention(self, reason):
        """An observed change: sample at ATTENTION_PERIOD for a few seconds so
        a fault is seen before the legacy repair loops erase it (blocker 10).
        Also wakes the loop immediately - a slow tick must never swallow a
        button press."""
        self.attention_until = time.monotonic() + ATTENTION_SECONDS
        self.attention_reason = reason
        self.attention_events += 1
        self.wake.set()

    @property
    def attentive(self):
        return time.monotonic() < self.attention_until


class Couchd:
    def __init__(self):
        os.makedirs(SHADOW_DIR, exist_ok=True)
        self.log = ShadowLog()
        self.snapshots = ShadowLog(prefix='snapshots')
        self.world = World(self.log)
        self.machine = Machine(on_transition=self._on_transition)
        self.executor = RecordingExecutor(self.log, on_record=self._on_intent)
        self.pad = PadObserver(self.world)
        self.flags = FlagObserver(self.world)
        self.pids = PidObserver(self.world)
        self.kodi = KodiObserver(self.world)
        self.steam = SteamObserver(self.world)
        self.triggers = TriggerObserver(self.world)
        self.x11 = X11Observer(self.world)
        self.recent = {}
        self.enforcement_target = None
        self.enforcement_until = 0.0
        self.last_would_do = []
        self.started = time.time()
        self.started_mono = time.monotonic()
        self.last_status = 0.0
        self.last_snapshot = 0.0
        self.last_world_obs = ''
        self.passes = 0
        self.owned = {'leaks': []}
        self._last_leaks = None
        self._press_channels = (0, 0)
        self.suppressed = 0
        self.violations = 0
        self.stop = None
        self._lock_fd = None
        self._tasks = []

    # -- single instance --------------------------------------------------
    def acquire_lock(self):
        fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            if e.errno in (errno.EACCES, errno.EAGAIN):
                return False
            raise
        os.ftruncate(fd, 0)
        os.write(fd, f'{os.getpid()}\n'.encode())
        self._lock_fd = fd            # held open for the process's lifetime
        return True

    # -- chokepoint callbacks --------------------------------------------
    def _on_transition(self, region, frm, to, reason):
        self.log.write({'kind': 'transition', 'region': region, 'from': frm,
                        'to': to, 'reason': reason})
        say(f'{region}: {frm} -> {to} ({reason})')
        self.world.attention(f'transition:{region}')

    def _on_intent(self, intent):
        self.recent[intent.key] = time.monotonic()
        self.last_would_do = ([intent.human()] + self.last_would_do)[:3]
        # couchd's own enforcement window: exactly what the old stack does by
        # spawning steam-input-guard after every transition.
        if intent.reason.startswith(('gesture:hold-release', 'transition:session-ended',
                                     'reconcile:orphaned-session')):
            self.enforcement_target = 'kodi'
            self.enforcement_until = time.monotonic() + GUARD_WINDOW
        elif intent.reason in ('gesture:tap-resume', 'transition:session-started'):
            self.enforcement_target = 'game'
            self.enforcement_until = time.monotonic() + GUARD_WINDOW

    # -- observation assembly --------------------------------------------
    def observe(self, loop):
        self.flags.read_all()
        session = self.flags.session()
        busy = bool(session or self.flags.suspended() or self.steam.ledger
                    or self.pids.states)
        self.pids.scan((session or {}).get('launcher_pid'), busy=busy)
        self.steam.poll()
        self.triggers.poll()
        xst = self.x11.poll(loop)
        pad_src = self.world.src('pad')
        return Observed(
            now=time.time(), mono=time.monotonic(),
            flags_known=self.world.src('flags').ok,
            session=session, suspended=self.flags.suspended(),
            pids_known=self.world.src('pids').ok,
            pid_states=dict(self.pids.states),
            launcher_alive=self.pids.launcher_alive,
            kodi_known=self.world.src('kodi').ok and self.kodi.joystick is not None,
            joystick=self.kodi.joystick, kodi_window=self.kodi.window,
            kodi_playing=self.kodi.playing,
            x_known=bool(xst and xst.ok),
            top_name=(xst.top_name if xst else ''),
            top_class=(xst.top_class if xst else ''),
            focused_class=(xst.focused_class if xst else ''),
            kodi_window_present=bool(xst and xst.kodi_present),
            big_picture_window=bool(xst and xst.big_picture),
            steam_known=self.world.src('steam').ok,
            steam_route=self.steam.route, ui_mode=self.steam.ui_mode,
            ledger={k: tuple(sorted(v)) for k, v in self.steam.ledger.items()},
            pad_known=pad_src.ok, pad_present=self.pad.present,
            button_down=self.pad.button_down,
            down_since_k=self.pad.down_since_k,
            kernel_now=self.pad.kernel_now(),
            press_duration=self.pad.press_duration,
            press_ended_at=self.pad.press_ended_at,
            regions=dict(self.machine.regions),
            region_since=dict(self.machine.since),
            games=dict(self.machine.games),
            enforcement_target=self.enforcement_target,
            enforcement_until=self.enforcement_until,
            recent=dict(self.recent))

    # -- one pass ---------------------------------------------------------
    def pass_once(self, loop):
        o = self.observe(loop)
        self.machine.step(o)
        o = replace(o, regions=dict(self.machine.regions),
                    region_since=dict(self.machine.since),
                    games=dict(self.machine.games))
        intents = reconcile(o)
        bad = check_invariants(o, intents)
        if bad:
            self.violations += len(bad)
            self.log.write({'kind': 'invariant', 'ok': False,
                            'violations': [{'name': n, 'detail': d} for n, d in bad],
                            'regions': dict(o.regions)})
            say('invariant violation: ' + '; '.join(f'{n}({d})' for n, d in bad))
        for it in intents:
            self.executor.execute(it, o)
        self.passes += 1
        return o, intents

    def anti_entropy(self, o):
        """Things that run on the slow tick only, never at attention rate."""
        agree = freeze_set_agreement(o, self.steam.ledger_pids(), self.pids.tree)
        if not agree['agree'] or agree['tree_minus_ledger'] or agree['ledger_minus_tree']:
            self.log.write({'kind': 'agreement', **agree})
        # R5: an observer-health gate independent of diffing. A source that
        # has gone quiet invalidates an evening rather than passing an empty
        # comparison, so say so loudly, once per episode.
        mono = time.monotonic()
        for name, s in self.world.sources.items():
            stale = (s.last_update and mono - s.last_update > OBSERVER_STALE_SECONDS)
            if (stale or not s.ok) and not s.blind_reported:
                s.blind_reported = True
                self.log.write({'kind': 'observer_blind', 'source': name,
                                'why': 'stale' if stale else 'not ok',
                                'age_s': round(mono - s.last_update, 1)
                                if s.last_update else None,
                                'detail': s.detail})
                say(f'observer {name} is blind: {s.detail or "stale"}')
            elif s.ok and not stale and s.blind_reported:
                s.blind_reported = False
                self.log.write({'kind': 'obs', 'source': name,
                                'event': 'observer-recovered',
                                'detail': s.detail})
        # the two independent views of the same physical PS press (R5)
        channels = (self.pad.presses, self.steam.guide_presses)
        if channels != self._press_channels:
            self._press_channels = channels
            self.log.write({'kind': 'agreement', 'metric': 'ps_press_channels',
                            'evdev_presses': self.pad.presses,
                            'steam_guide_lines': self.steam.guide_presses,
                            'pad_first_event_latency_s': (
                                round(self.pad.first_event_latency, 3)
                                if self.pad.first_event_latency else None)})
        # Owned-resources invariant: checked every tick, but only WRITTEN when
        # the answer changes - a standing leak must not drown the log.
        owned = self.owned_resources(o)
        self.owned = owned
        if owned['leaks'] != self._last_leaks:
            self._last_leaks = list(owned['leaks'])
            self.log.write({'kind': 'invariant', 'ok': not owned['leaks'],
                            'name': 'owned_resources', **owned})
            for leak in owned['leaks']:
                say(f'owned-resources: {leak}')

    def owned_resources(self, o):
        """R4's leak class (audit failure 10): a superseded guard leaving a
        virtual pad behind is a phantom player 2 forever. couchd owns nothing
        in shadow, so anything found here is somebody else's leak."""
        import psutil
        vpad = os.path.exists(VPAD_FIFO)
        guard_pid = None
        with contextlib.suppress(OSError, ValueError):
            guard_pid = int(open(GUARD_PIDFILE).read().strip())
        guard_alive = bool(guard_pid and psutil.pid_exists(guard_pid))
        uinput = sorted(n for n in PadObserver.find_pads())
        leaks = []
        if vpad and not guard_alive:
            leaks.append('vpad.fifo with no live guard')
        if guard_pid and not guard_alive:
            leaks.append(f'stale guard pidfile (pid {guard_pid})')
        if o.suspended_present and o.pids_known and not o.pid_states \
                and o.suspended != 'bigpicture':
            leaks.append('suspended flag with no frozen processes')
        if o.session_present and o.launcher_alive is False and not o.pid_states:
            leaks.append('session flag with a dead launcher')
        return {'vpad_fifo': vpad, 'guard_pid': guard_pid,
                'guard_alive': guard_alive, 'pad_nodes': uinput,
                'expected_owned': [], 'leaks': leaks}

    # -- outputs ----------------------------------------------------------
    def write_status(self, o):
        mono = time.monotonic()
        status = {
            't': time.time(), 'pid': os.getpid(),
            'uptime_s': round(mono - self.started_mono, 1),
            'mode': 'shadow', 'attention': self.world.attentive,
            'regions': dict(o.regions), 'games': dict(o.games),
            'last_would_do': list(self.last_would_do),
            'observers': {n: s.health(mono) for n, s in self.world.sources.items()},
            'counts': dict(self.log.counts),
            'passes': self.passes, 'intents': self.executor.count,
            'invariant_violations': self.violations,
            'ps_presses': {'evdev': self.pad.presses,
                           'steam_guide_lines': self.steam.guide_presses,
                           'first_event_latency_s': (
                               round(self.pad.first_event_latency, 3)
                               if self.pad.first_event_latency else None)},
            'last_trigger': self.triggers.last,
            'resource_leaks': list(self.owned.get('leaks', ())),
            'shadow_log': os.path.join(SHADOW_DIR, f'couchd-{time.strftime("%Y%m%d")}.jsonl'),
        }
        write_atomic(os.path.join(SHADOW_DIR, 'status.json'),
                     json.dumps(status, indent=1, default=str))

    def write_snapshot(self, o, why):
        """R8's world-snapshot corpus: the reconcile responsibility runs pad
        or no pad, so the pad recorder structurally cannot cover it."""
        self.snapshots.write({
            'kind': 'snapshot', 'why': why,
            'flags': {'session': (o.session or {}).get('raw'),
                      'suspended': o.suspended},
            'pids': {str(p): s for p, s in o.pid_states.items()},
            'joystick': o.joystick, 'kodi_window': o.kodi_window,
            'top': [o.top_name, o.top_class], 'focused': o.focused_class,
            'steam_route': (o.steam_route or '')[-90:], 'ui_mode': o.ui_mode,
            'ledger': {k: list(v) for k, v in (o.ledger or {}).items()},
            'pad': {'present': o.pad_present, 'down': o.button_down},
            'regions': dict(o.regions), 'games': dict(o.games),
        })

    def log_world_obs(self, o):
        """The periodic full-world observation record (kind 'obs', source
        'world'), written when anything observable changed."""
        fingerprint = json.dumps({
            's': (o.session or {}).get('raw'), 'x': o.suspended,
            'p': sorted(o.pid_states.items()), 'j': o.joystick,
            'w': o.kodi_window, 't': [o.top_name, o.top_class],
            'f': o.focused_class, 'r': (o.steam_route or '')[-60:],
            'u': o.ui_mode, 'd': o.button_down, 'a': o.pad_present,
        }, sort_keys=True, default=str)
        if fingerprint == self.last_world_obs:
            return False
        self.last_world_obs = fingerprint
        self.log.write({'kind': 'obs', 'source': 'world',
                        'session': (o.session or {}).get('raw'),
                        'suspended': o.suspended,
                        'pids': {str(p): s for p, s in o.pid_states.items()},
                        'joystick': o.joystick, 'kodi_window': o.kodi_window,
                        'top': [o.top_name, o.top_class],
                        'focused': o.focused_class,
                        'steam_route': (o.steam_route or '')[-90:],
                        'ui_mode': o.ui_mode,
                        'pad': {'present': o.pad_present, 'down': o.button_down},
                        'known': {'flags': o.flags_known, 'pids': o.pids_known,
                                  'kodi': o.kodi_known, 'x11': o.x_known,
                                  'steam': o.steam_known, 'pad': o.pad_known}})
        return True

    # -- main loop --------------------------------------------------------
    async def run(self):
        loop = asyncio.get_running_loop()
        self.stop = asyncio.Event()
        def _stop():
            self.stop.set()
            self.world.wake.set()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, _stop)
        say(f'couchd up (shadow mode, pid {os.getpid()}); '
            f'writing {SHADOW_DIR}')
        self.log.write({'kind': 'daemon', 'event': 'start', 'pid': os.getpid(),
                        'mode': 'shadow', 'steam_logs': STEAM_LOGS})
        self._tasks = [asyncio.create_task(self.pad.run(loop)),
                       asyncio.create_task(self.flags.run()),
                       asyncio.create_task(self.kodi.run_notifications())]
        self.x11.attach(loop)
        notify('READY=1')
        notify('STATUS=shadow mode, observing')
        last_tick = 0.0
        try:
            while not self.stop.is_set():
                mono = time.monotonic()
                await self.kodi.poll()
                slow = mono - last_tick >= TICK_SECONDS
                o, intents = self.pass_once(loop)
                self.log_world_obs(o)
                if slow:
                    last_tick = mono
                    self.anti_entropy(o)
                    self.log.sync_if_idle()
                if mono - self.last_status >= STATUS_INTERVAL:
                    self.last_status = mono
                    self.write_status(o)
                due = mono - self.last_snapshot
                if due >= SNAPSHOT_INTERVAL or (
                        self.world.attentive and due >= SNAPSHOT_MIN_GAP):
                    self.last_snapshot = mono
                    self.write_snapshot(
                        o, self.world.attention_reason if self.world.attentive
                        else 'periodic')
                notify('WATCHDOG=1')
                await self._sleep_until_next(mono)
        finally:
            await self.shutdown(loop)

    async def _sleep_until_next(self, started):
        """The pacing rule, in one place (R6). Base tick TICK_SECONDS; an
        observed change wakes us early but never lets us sample faster than
        ATTENTION_PERIOD; outside an attention window nothing ever runs
        faster than MIN_PERIOD. Kodi has its own >=10s limiter."""
        target = ATTENTION_PERIOD if self.world.attentive else TICK_SECONDS
        while not self.stop.is_set():
            elapsed = time.monotonic() - started
            if elapsed >= target:
                return
            self.world.wake.clear()
            try:
                await asyncio.wait_for(self.world.wake.wait(), target - elapsed)
            except (asyncio.TimeoutError, TimeoutError):
                return
            if self.stop.is_set():
                return
            # woken by an observer: respond fast, but honour the floor
            floor = ATTENTION_PERIOD if self.world.attentive else MIN_PERIOD
            elapsed = time.monotonic() - started
            if elapsed < floor:
                await asyncio.sleep(floor - elapsed)
            return

    async def shutdown(self, loop):
        notify('STOPPING=1')
        say('couchd stopping')
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self.pad.close(loop)
        self.x11.close(loop)
        self.steam.close()
        self.triggers.close()
        self.log.write({'kind': 'daemon', 'event': 'stop',
                        'passes': self.passes, 'intents': self.executor.count,
                        'counts': dict(self.log.counts)})
        self.log.close()
        self.snapshots.close()
        if self._lock_fd is not None:
            with contextlib.suppress(OSError):
                os.close(self._lock_fd)
            self._lock_fd = None
        say('couchd stopped')


def notify(state):
    try:
        from systemd import daemon
    except ImportError:
        return
    with contextlib.suppress(Exception):
        daemon.notify(state)


def main():
    load_env()
    d = Couchd()
    if not d.acquire_lock():
        say('another couchd holds the lock; exiting')
        print('couchd: already running', file=sys.stderr)
        return 1
    try:
        asyncio.run(d.run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
