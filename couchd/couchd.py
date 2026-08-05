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
import faulthandler
import fcntl
import json
import os
import re
import signal
import socket
import stat as stat_module
import struct
import sys
import time
from dataclasses import dataclass, field, replace

# The PS-button arithmetic lives in ONE module (stage-2 design, SR4): stage 1
# and the stage-2 input process must decide tap-vs-hold identically or the
# shadow corpus stops being comparable to what the owning process did.
import gesture
import gestureconf
from gesture import HANDOFF_TIMEOUT, HOLD_SECONDS  # noqa: F401 (re-exported)

# Who owns what, read fresh from ~/couch/couchd/owns.conf every tick. Empty -
# the state it ships in - means couchd acts on nothing and the legacy scripts
# act on everything, which is the console exactly as it was.
import owns

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
# The gesture edge (R5). A show/route decision that rides the 5s tick is a
# second and a half of a room staring at the wrong window; the perceptual
# bound is 250ms, so a PS-button edge runs a pass NOW. The debounce is the
# only thing between it and the loop: 50ms coalesces the press/release pairs
# and the burst of a spammed button into single passes, and it is an order of
# magnitude inside the bound, so it costs nothing that can be felt.
EDGE_DEBOUNCE = 0.05
# Gesture deadlines (the hold threshold, the double-tap window, the handoff
# timeout) are edges too - they are just edges with no event behind them. The
# sleeper wakes ON them rather than at the next attention sample, and this is
# the floor it will not go below to do it.
EDGE_DEADLINE_FLOOR = 0.02
KODI_READ_INTERVAL = 10.0     # never faster, whatever the tick does
STATUS_INTERVAL = 3.0
SNAPSHOT_INTERVAL = 30.0
SNAPSHOT_MIN_GAP = 2.0        # attention-triggered snapshots are rate-limited
OBSERVER_STALE_SECONDS = 300.0

# -- model constants (ported from the scripts) ----------------------------
# HOLD_SECONDS (0.9, pad-home-watcher's hold threshold) and HANDOFF_TIMEOUT
# (4.0, its safety timeout when the release never comes) are imported from
# gesture.py above - SR4's shared module - and re-exported here so every
# existing importer of couchd.HOLD_SECONDS keeps working.
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

EVENT_FORMAT = gesture.EVENT_FORMAT   # struct input_event on x86_64
EVENT_SIZE = gesture.EVENT_SIZE
EV_KEY = gesture.EV_KEY
BTN_MODE = gesture.BTN_MODE           # the PS button
PAD_WANTED = 'DualSense Wireless Controller'
PAD_UNWANTED = re.compile(r'Motion|Touchpad', re.I)

REAPER = 'reaper SteamLaunch'
# Steam's two guide-button log lines, verbatim (steam-input-guard reads the
# same pair). The first is a TAP Steam swallowed - and swallowing it is what
# opens its desktop-mode overlay over the game; the second is a HOLD it
# ignored, which opens nothing. R7(f) is exactly that distinction.
GUIDE_SENT = 'Guide button sent to JS'
GUIDE_SKIPPED = 'Guide button skipped due to length'
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
    # When Steam last CONSUMED a guide press ("Guide button sent to JS"),
    # monotonic. In desktop UI mode that line is the only tell that Steam ate
    # the press and opened its overlay over the game - the routing config is
    # Desktop/413080 and never ClientUI, so the ClientUI arm cannot see it.
    # A "skipped due to length" line (a HOLD) is deliberately not this: it
    # opened nothing. See steam-input-guard.guide_consumed_since.
    guide_consumed_at: float = None

    # The enforcement window's pidfile. `guard_pid_ours` is couchd's own
    # write-through: a pidfile holding OUR pid must never be superseded, which
    # is the same rule the legacy watcher yields on.
    guard_pid: int = None
    guard_pid_ours: bool = False

    # pad / gesture (all times are KERNEL event timestamps, R4)
    pad_known: bool = False
    pad_present: bool = False
    button_down: bool = False
    down_since_k: float = None
    kernel_now: float = 0.0
    press_duration: float = None           # last completed press, seconds
    press_ended_at: float = None           # mono when that press ended
    double_armed: bool = False             # this press began inside the
    #                                        double-tap window of the last tap

    # The PS-button key bindings, as the addon's settings page left them.
    # BOTH stacks read the same file through ~/couch/couchd/gestureconf.py -
    # the live watcher dispatches on it, the model below decides its would-do
    # from it - so a rebind moves them together and the shadow diff stays
    # clean. Carrying it on Observed rather than reading the file from inside
    # reconcile() keeps the model pure (C13) and lets a test bind a gesture
    # without touching a path Kodi owns.
    bindings: dict = field(default_factory=lambda: dict(gestureconf.DEFAULT_BINDINGS))
    hold_seconds: float = HOLD_SECONDS
    double_tap_seconds: float = gesture.DOUBLE_TAP_S
    long_hold_seconds: float = gesture.LONG_HOLD_S

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

    def binding(self, name):
        """The effective action for one gesture. Defaults are the console's
        behaviour as shipped, so an Observed built without bindings decides
        exactly what it decided before the settings page existed."""
        return (self.bindings or {}).get(
            name, gestureconf.DEFAULT_BINDINGS.get(name, 'none'))


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
        guide_consumed_at=None, guard_pid=None, guard_pid_ours=False,
        pad_known=True, pad_present=True, button_down=False,
        down_since_k=None, kernel_now=1000.0, press_duration=None,
        press_ended_at=None, double_armed=False,
        bindings=dict(gestureconf.DEFAULT_BINDINGS),
        hold_seconds=HOLD_SECONDS, double_tap_seconds=gesture.DOUBLE_TAP_S,
        long_hold_seconds=gesture.LONG_HOLD_S,
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
         'request_tv_wake', 'show_switcher', 'tv_toggle', 'snapshot')
PID_VERBS = ('freeze', 'thaw', 'quit', 'kill')

# TOGGLES. These three verbs are not idempotent: the mechanism underneath each
# is a switch, so a second emission inside the first one's effect window does
# not repeat the decision, it UNDOES it. That is exactly the Steam menu
# close-then-reopen dance the guard's cross-window latch exists to prevent
# (commit f2ac188, seen live 02:53:48.9 + 02:53:53.2).
#
# In shadow it costs nothing; once couchd ACTS, the guide press takes ~2.5s to
# send and seconds more to show up in Steam's routing log, so their cooldowns
# must outlast their own predicted-effect deadlines or couchd re-decides on
# world state its own last action has not reached yet. Invariant, asserted in
# check_invariants and in the tests: for a toggle, cooldown > deadline.
TOGGLE_VERBS = ('close_steam_menu', 'tv_toggle')
TOGGLE_SUBJECTS = (('show', 'steam-menu'),)
GUIDE_TOGGLE_COOLDOWN = 8.0     # close_steam_menu (deadlines 3.0 and 6.0)
MENU_TOGGLE_COOLDOWN = 6.0      # show steam-menu (deadline 3.0)
TV_TOGGLE_COOLDOWN = 20.0       # tv_toggle (deadline 15.0)


def is_toggle(intent):
    return (intent.verb in TOGGLE_VERBS
            or (intent.verb, intent.subject) in TOGGLE_SUBJECTS)


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
    # MODELLED BUT NEVER PERFORMED. Two of the legacy stack's decisions belong
    # to the process the operator started (game-launch's Big-Picture pre-step
    # and its appid adoption): game-launch does NOT yield either of them when
    # couchd owns `transitions`, because couchd cannot stand in for the shell
    # that is currently launching the game. couchd still has to MODEL them or
    # its state is wrong about what the console is doing - so it decides them,
    # writes them to the corpus, and the acting executor refuses them by
    # construction rather than by a forgotten `if`. A model_only intent can
    # never become a double-action on flip day.
    model_only: bool = False

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
    a held button with no further reports still fires. The arithmetic itself
    is gesture.py's, shared with the stage-2 input process (SR4); the
    threshold is the settings page's, defaulting to 0.9."""
    return gesture.hold_reached(o.button_down, o.down_since_k, o.kernel_now,
                                o.hold_seconds)


def g_hold_fires(o):
    """...and the hold is actually bound to something.

    With `hold` set to Nothing the press must stay in 'down' long enough for
    the long-hold tier to see it; parking it in 'hold-fired' with no action
    would eat the press. Under the default bindings hold IS bound, so this is
    g_hold_reached and the table below behaves exactly as it always has.
    """
    return o.binding('hold') != 'none' and g_hold_reached(o)


def g_long_hold_fires(o):
    """The third tier, and only ever reachable with `hold` unbound - see
    gesture.LONG_HOLD_S and gestureconf.suppress for why the two cannot both
    fire off one press. gestureconf already guarantees that pairing, so the
    binding check here is belt and braces, not the rule."""
    return (o.binding('long_hold') != 'none' and o.binding('hold') == 'none'
            and gesture.long_hold_reached(o.button_down, o.down_since_k,
                                          o.kernel_now, o.long_hold_seconds))


def g_released(o):
    return not o.button_down


def g_released_no_handoff(o):
    """Released after a hold that was NOT the suspend.

    The suspend defers giving Kodi the pad to the release (audit failure 4),
    which is what 'handoff-pending' exists for. Any other bound hold action
    has already done whatever it does, so the gesture is simply over; without
    this the region would sit in 'handoff-pending' waiting for a handoff that
    is never coming and block drift repairs for the 4s timeout. Always false
    under the default bindings.
    """
    return not o.button_down and o.binding('hold') != 'suspend_to_kodi'


def g_released_tap_resume(o):
    """A tap that resumes the paused game, NOW.

    Donnie's 5 Aug amendment (gesture.paused_tap_decision, and the live
    watcher's `pending_resume`): while the double-tap is bound, a tap on a
    paused game cannot know yet that it is the whole gesture - a second tap
    inside the window means the switcher, which is exactly when the switcher
    is most useful. So the instant resume survives only where there is nothing
    to escalate to; otherwise the press falls through to 'tap-wait' and
    resumes from there when the window shuts (g_tap_resume_due).
    """
    return (not o.button_down and gesture.is_tap(o.press_duration)
            and o.suspended_present
            and o.binding('double_tap') == 'none')


def g_tap_resume_due(o):
    """The deferred resume's window ran out with no second tap.

    The suspended flag is re-read HERE rather than remembered from the press:
    a reconcile, the phone or a guard repair may have resumed the game inside
    those 350ms, and resuming a game that is already running would raise a
    window over the Kodi the player is looking at.
    """
    return (not o.button_down and o.suspended_present
            and gesture.is_tap(o.press_duration)
            and gesture.double_tap_window_over(_since(o, 'gesture'),
                                               o.double_tap_seconds))


def g_released_double(o):
    """The second half of a double-tap: released, itself a tap, and it began
    inside DOUBLE_TAP_S of the previous tap's release.

    `double_armed` is the tracker's, computed in KERNEL time (R4) - the
    tap-wait state below only says a second press is plausible, this says it
    actually was one. The hold transition is tried first in every state that
    has both, so tap-then-hold is always the hold.
    """
    return (not o.button_down and o.double_armed
            and gesture.is_tap(o.press_duration))


def g_double_window_over(o):
    """No second press came: the single tap is final and we go quiet.

    Monotonic, like the handoff timeout and for the same reason - it is the
    ABSENCE of an event, so there is no kernel timestamp to measure from. The
    decision that matters (released_double) stays kernel-exact.
    """
    return gesture.double_tap_window_over(_since(o, 'gesture'),
                                          o.double_tap_seconds)


def g_switcher_emitted(o):
    return _recent(o, 'show_switcher|tv|gesture:double-tap-switcher', 3.0)


def g_handoff_emitted(o):
    return (_recent(o, 'route_pad|kodi|gesture:hold-release', 3.0)
            or _recent(o, 'route_pad|kodi|gesture:hold-release-timeout', 3.0))


def g_handoff_overdue(o):
    """The release never arrived (the pad died mid-hold, or the button is
    stuck): the watcher hands over anyway after 4s rather than stranding the
    pad. This is a wall/monotonic deadline, not a kernel one - it exists
    precisely because no further kernel events are coming."""
    return gesture.handoff_overdue(_since(o, 'gesture'))


def g_resume_emitted(o):
    return any(k.startswith('launch|') and k.endswith('|gesture:tap-resume')
               and (o.mono - t) < 3.0 for k, t in o.recent.items())


def g_gesture_stale(o):
    """Nothing pending and the button is up: fall back to idle."""
    return gesture.gesture_stale(o.button_down, _since(o, 'gesture'))


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
    return (o.enforcement_target == 'game' and o.mono < o.enforcement_until
            and not o.suspended_present)


def g_enf_suspended_mid_window(o):
    """R7(d): a suspend that lands inside a GAME enforcement window ends it.

    Every game-mode invariant is moot the moment the game is meant to be
    frozen - it must not be raised, it must not be thawed, and Kodi belongs on
    top, which is the kodi window's job and not this one's. The legacy guard
    learned to close on this (`window_close reason=suspended-mid-window`)
    after the 4 Aug race where a resume's guard SIGCONTed a fresh freeze;
    couchd is a single arbiter, so for it the window simply ends.
    """
    return o.enforcement_target == 'game' and o.suspended_present


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
        # The hold is tried first, exactly as before; the long-hold tier below
        # it is unreachable unless `hold` is bound to Nothing (g_hold_fires /
        # g_long_hold_fires), so under the default bindings this list is the
        # one it has always been.
        'down': [('hold_fires', 'hold-fired', 'ps-held-0.9s'),
                 ('long_hold_fires', 'long-hold-fired', 'ps-held-long'),
                 ('released_tap_resume', 'tap-resume', 'ps-tap-with-paused-game'),
                 ('released', 'tap-wait', 'ps-tap-noop')],
        # A tap that did nothing (no paused game to resume) is not final until
        # the double-tap window shuts: a second press inside it is the
        # switcher gesture, not a new first tap. Nothing is DELAYED by this -
        # the tap's own action, if it had one, already fired from 'down' - so
        # the live watcher's tap latency is unchanged.
        'tap-wait': [('pad_unknown', UNKNOWN, 'pad-observer-blind'),
                     ('button_down', 'down-again', 'second-press-inside-window'),
                     # The deferred resume, before the plain expiry: a tap on a
                     # PAUSED game waited out the double-tap window here (see
                     # g_released_tap_resume) and now means what it always meant.
                     ('tap_resume_due', 'tap-resume', 'paused-tap-window-expired'),
                     ('double_window_over', 'idle', 'double-tap-window-expired')],
        # Reachable ONLY from tap-wait, which is why a double-tap can never
        # follow a tap that resumed a paused game: that tap goes to
        # 'tap-resume' instead, and the resume owns the pad from there.
        'down-again': [('hold_fires', 'hold-fired', 'ps-held-0.9s'),
                       ('long_hold_fires', 'long-hold-fired', 'ps-held-long'),
                       ('released_double', 'double-tap', 'ps-double-tap'),
                       ('released_tap_resume', 'tap-resume',
                        'ps-tap-with-paused-game'),
                       ('released', 'tap-wait', 'ps-tap-noop')],
        'double-tap': [('switcher_emitted', 'idle', 'switcher-decided'),
                       ('gesture_stale', 'idle', 'gesture-abandoned')],
        'hold-fired': [('released_no_handoff', 'idle', 'hold-action-done'),
                       ('released', 'handoff-pending', 'ps-released-after-hold'),
                       ('handoff_overdue', 'timed-out', 'release-never-came')],
        # A long hold has no deferred half: whatever it was bound to fired at
        # the threshold, so the release just ends the gesture.
        'long-hold-fired': [('released', 'idle', 'ps-released-after-long-hold'),
                            ('gesture_stale', 'idle', 'gesture-abandoned')],
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
        # R7(d): the suspend check comes FIRST. A game window whose game just
        # got frozen has nothing left to enforce, and spending its remaining
        # seconds fighting the player's own gesture is the 4 Aug race.
        'game': [('enf_suspended_mid_window', 'none', 'suspended-mid-window'),
                 ('enf_kodi', 'kodi', 'guard-window-superseded'),
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


def playing_despite_flag(o):
    """R7(d): /tmp/game-suspended is set, and the player is demonstrably
    playing anyway - the game is BOTH the top window and the focused one, with
    processes that are not stopped.

    That combination has exactly one honest reading: the flag is the thing
    that is wrong (a suspend whose freeze was undone, historically by a stale
    guard window's thaw-repair). Every consumer of the flag has to agree about
    it or they pull in opposite directions - which is why the legacy reconcile
    clears its own local `suspended` in that branch, and why this predicate is
    shared here between the repair, the pad-owner rule and the "a frozen game
    must not be what the room is looking at" repair.
    """
    return bool(o.suspended_present and o.pids_known and o.running_pids
                and o.suspended != 'bigpicture'
                and o.x_known and (o.top_class or '').startswith('steam_app')
                and (o.focused_class or '').startswith('steam_app'))


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
    if o.suspended_present and not playing_despite_flag(o):
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


# The guard's arm (b) holds off for the first beat of its window: Steam's
# overlay shows up ~0.3-1s after the press, and a check that ran before the
# log line existed would waste the one shot on nothing.
OVERLAY_ARM_DELAY = 1.2
STEAM_UI_DESKTOP = 7            # Steam's own numbering (steam-uimode.MODES)
STEAM_UI_BIG_PICTURE = 4


def _desktop_overlay_open(o):
    """R7(f): is Steam's DESKTOP-mode overlay sitting over the game?

    Pure, and deliberately the same five clauses as
    steam-input-guard.desktop_overlay_open: inside an enforcement window past
    its first beat, a session is live, Steam CONSUMED a guide press since the
    window opened, and steamwebhelper does not own the X focus (if it did, the
    player is deliberately in Steam and closing it would be rude).
    """
    if o.ui_mode != STEAM_UI_DESKTOP or not o.session_present:
        return False
    if 'steamwebhelper' in (o.focused_class or ''):
        return False
    if o.guide_consumed_at is None:
        return False
    opened = o.enforcement_until - GUARD_WINDOW
    if o.mono < opened + OVERLAY_ARM_DELAY:
        return False
    return o.guide_consumed_at >= opened


# =========================================================================
# pure model: the bound actions
# =========================================================================
# One gesture -> one reason tag, so a rebound gesture is legible in the log
# and in the differ without decoding args. The two the console shipped with
# ('gesture:ps-hold', 'gesture:ps-double-tap') keep their exact old spelling:
# whitelists, the enforcement-window trigger below and the differ's own
# triage all key off them.
GESTURE_REASON = {
    'tap': 'gesture:ps-tap',
    'double_tap': 'gesture:ps-double-tap',
    'hold': 'gesture:ps-hold',
    'hold_release': 'gesture:ps-hold-release',
    'long_hold': 'gesture:ps-long-hold',
}


def _snapshot_intent(appid, reason):
    """Keep the game's last rendered frame as its artwork while it is paused.

    An ACTION by the legacy stack (~/.local/bin/pause-snap, called from both
    suspend initiators), so it is a would-do here like any other. It only ever
    follows a freeze that actually stopped something: with nothing frozen
    there is no window whose last frame means anything, and neither live
    script emits it - Big Picture suspends have no snapshot.

    Ordering is deliberately NOT part of the contract. xfwm4 compositing keeps
    every mapped window's pixmap, so the capture is identical before or after
    the SIGSTOP and before or after Kodi is raised over the game; the live
    scripts snap after the STOP only so the freeze itself stays instant, and
    the watcher runs it off its select loop, so the effect can land a moment
    late. The differ's window is sized for that.
    """
    return Intent('snapshot', appid, {'via': 'pause-snap'}, reason,
                  _pred('a freeze-frame jpg for the appid', 5.0),
                  requires=('gesture', 'session'), cooldown=3.0)


def _iconify_intent(appid, reason):
    """R7(c): unmap the frozen game's window once Kodi has the screen.

    A SIGSTOPped client cannot answer the X server, so any pointer grab it
    held at the instant it froze stays held: its cursor sprite sits over Kodi
    and the phone's XTEST clicks are swallowed by a process that will never
    read them. X drops a grab when the grab window stops being VIEWABLE, so
    unmapping is what frees the pointer - raising Kodi over it does nothing.
    (pad-home-watcher.iconify_frozen_game, game-launch's iconify_game.)

    Ordering is part of the decision, not an accident: the freeze-frame is
    read off the window's compositing pixmap, which iconifying frees, so the
    legacy stack waits up to SNAP_WAIT_S for pause-snap before unmapping. The
    deadline below is sized for that wait rather than for the unmap itself.
    """
    return Intent('iconify', appid,
                  {'via': 'wm-change-state', 'reason': 'release-pointer-grab',
                   'after': 'snapshot'},
                  reason, _pred('the frozen game window is unmapped', 8.0),
                  requires=('gesture', 'session'), cooldown=5.0)


def _deiconify_intent(o, appid, reason):
    """The exact undo of _iconify_intent (R7(c)).

    Emitted on the resume and after any repair that thaws a game itself: a
    thawed game left iconified is audible, holds the pad, and shows the room
    nothing that explains either. On a window that was never iconified this is
    just a raise, which is why it is safe to emit unconditionally on the path.
    """
    return Intent('show', appid, {'via': 'activate', 'reason': 'deiconify'},
                  reason, _pred('the game window is mapped again', 8.0),
                  requires=('gesture', 'session') if reason.startswith('gesture:')
                  else ('session',), cooldown=5.0)


def _supersede_guard_intent(o, reason):
    """R7(d): close any enforcement window still open, BEFORE the freeze.

    A guard opened by a recent resume spends its seconds asserting game-mode
    invariants, one of which is "a game that should be running must be
    thawed". The 4 Aug 2026 race: 18 processes frozen at 02:13:33, SIGCONTed
    by the resume's guard at 02:13:34.865, leaving Kodi on screen with the
    game audible behind it. couchd is the single arbiter, so for its OWN
    window this is just the enforcement region ending - but a LEGACY guard
    process may still be out there holding the pidfile, and that one has to be
    superseded exactly as the watcher supersedes it.

    Never our own pid: a pidfile holding couchd's write-through is couchd's
    enforcement window, and SIGTERMing it would kill the daemon holding the
    console together. That is the same rule the legacy watcher yields on.
    """
    if not o.guard_pid or o.guard_pid_ours:
        return []
    return [Intent('kill', 'steam-input-guard',
                   {'pids': [o.guard_pid], 'resolver': 'guard-pidfile',
                    'signal': 'SIGTERM', 'reason': 'superseded-by-freeze'},
                   reason, _pred('the guard pidfile is gone or replaced', 5.0),
                   requires=('gesture',), cooldown=5.0)]


def _suspend_intents(o, appid, running, reason, defer_handoff):
    """`suspend_to_kodi`: freeze whatever is running and land on Kodi.

    Exactly the sequence the hold has always emitted. `defer_handoff` is what
    the hold needs and nothing else does: the pad must NOT move while the
    button is still down (audit failure 4), so the route/show/guard half is
    emitted from 'handoff-pending' on release instead. Any other gesture bound
    to this action has no release to wait for and hands off at once, which is
    what the double-tap switcher already did.
    """
    out = []
    if running:
        # Before the STOPs, not after (the watcher's own ordering).
        out += _supersede_guard_intent(o, reason)
        out.append(Intent(
            'freeze', appid,
            {'pids': running, 'resolver': PID_RESOLVER, 'signal': 'SIGSTOP',
             'mode': o.session_mode},
            reason, _pred('all game pids in state T', 5.0),
            requires=('gesture', 'session'), cooldown=3.0))
        out.append(Intent(
            'set_flag', 'suspended', {'value': appid},
            reason, _pred('/tmp/game-suspended exists', 2.0),
            requires=('gesture', 'session'), cooldown=3.0))
        out.append(_snapshot_intent(appid, reason))
    elif o.session_mode == 'bigpicture' or o.regions.get('foreground') == 'bigpicture':
        # R7(a) done RIGHT: record the suspend even though there is nothing to
        # freeze, so the joystick repair below can never decide the pad belongs
        # to an invisible Big Picture.
        out.append(Intent(
            'set_flag', 'suspended', {'value': 'bigpicture', 'pids': []},
            reason + '-bigpicture', _pred('/tmp/game-suspended exists', 2.0),
            requires=('gesture', 'session'), cooldown=3.0))
    else:
        return []           # no live game, not Big Picture: nothing meaningful
    if not defer_handoff:
        out += _handoff_intents(o, appid, reason)
    return out


def _handoff_intents(o, appid, reason):
    """Kodi gets the pad, the screen, and a guard window. The three of them
    always travel together; the watcher's handoff_to_kodi() is this.

    ...and then the frozen game's window goes, because Kodi being on top is
    not the same as the frozen client letting go of the pointer (R7(c)).
    Only when something is actually paused: a Big Picture suspend has no
    frozen window to unmap, and neither live script iconifies on that path.
    """
    out = [
        Intent('route_pad', 'kodi', {'via': 'kodi-jsonrpc'}, reason,
               _pred('input.enablejoystick true', 2.0),
               requires=('gesture', 'input_ownership'), cooldown=3.0),
        Intent('show', 'kodi', {'via': 'xlib-restack'}, reason,
               _pred('top window is Kodi', 2.0),
               requires=('gesture', 'foreground'), cooldown=3.0),
        # TOGGLE: cooldown outlasts the deadline (see TOGGLE_VERBS) - a
        # second guide press inside the first one's window REOPENS the menu.
        Intent('close_steam_menu', 'steam',
               {'via': 'vpad-guide', 'window_s': GUARD_WINDOW}, reason,
               _pred('steam menu not routed', 6.0),
               requires=('gesture',), cooldown=GUIDE_TOGGLE_COOLDOWN),
    ]
    frozen = bool(o.pids_known and o.frozen_pids)
    if appid and appid != 'bigpicture' and (o.suspended_present or frozen) \
            and (o.suspended or appid) != 'bigpicture':
        out.append(_iconify_intent(appid, reason))
    return out


def _switcher_intents(o, appid, running, reason, switcher_reason):
    """`switcher`: the on-TV dialog script.couch.switcher draws.

    The dialog is Kodi's and has to be navigable with the stick, so anything
    actually running is suspended FIRST - the whole suspend path, in the same
    order - and only then is the dialog asked for. That order is what the
    watcher does, so the differ sees the same sequence from both stacks.
    """
    out = []
    handed = False
    if o.session_present and running:
        out += _supersede_guard_intent(o, reason)
        out.append(Intent(
            'freeze', appid,
            {'pids': running, 'resolver': PID_RESOLVER, 'signal': 'SIGSTOP',
             'mode': o.session_mode},
            reason, _pred('all game pids in state T', 5.0),
            requires=('gesture', 'session'), cooldown=3.0))
        out.append(Intent(
            'set_flag', 'suspended', {'value': appid},
            reason, _pred('/tmp/game-suspended exists', 2.0),
            requires=('gesture', 'session'), cooldown=3.0))
        out.append(_snapshot_intent(appid, reason))
        handed = True
    elif o.session_present and (o.session_mode == 'bigpicture'
                                or o.regions.get('foreground') == 'bigpicture'):
        out.append(Intent(
            'set_flag', 'suspended', {'value': 'bigpicture', 'pids': []},
            reason, _pred('/tmp/game-suspended exists', 2.0),
            requires=('gesture', 'session'), cooldown=3.0))
        handed = True
    if handed:
        out += _handoff_intents(o, appid, reason)
    else:
        # Nothing to suspend, but the dialog still needs a visible Kodi -
        # including on the way back from the desktop, which is where this
        # gesture is most useful.
        out.append(Intent('show', 'kodi',
                          {'via': 'xlib-restack', 'showing_desktop': 'off'},
                          switcher_reason, _pred('top window is Kodi', 2.0),
                          requires=('gesture', 'foreground'), cooldown=3.0))
    out.append(Intent('show_switcher', 'tv',
                      {'via': 'kodi-addon:script.couch.switcher',
                       'suspended_first': handed},
                      switcher_reason, _pred('Kodi select dialog open', 3.0),
                      requires=('gesture',), cooldown=3.0))
    return out


def action_intents(o, gesture_name, appid, running, defer_handoff=False):
    """One bound gesture -> the would-dos it asks for.

    The whole binding dispatch is here, in the pure model, mirroring
    pad-home-watcher's `act()` verb for verb. Anything gestureconf can name
    must appear in both or the shadow diff is lying.
    """
    action = o.binding(gesture_name)
    if action == 'none':
        return []
    reason = GESTURE_REASON.get(gesture_name, f'gesture:ps-{gesture_name}')
    if action == 'suspend_to_kodi':
        return _suspend_intents(o, appid, running, reason, defer_handoff)
    if action == 'switcher':
        switcher_reason = ('gesture:double-tap-switcher'
                           if gesture_name == 'double_tap'
                           else f'{reason}-switcher')
        return _switcher_intents(o, appid, running, reason, switcher_reason)
    if action == 'steam_menu':
        # The same guide press steam-input-guard uses to CLOSE the menu; the
        # button is a toggle, so opening it is the identical effect.
        return [Intent('show', 'steam-menu', {'via': 'vpad-guide'}, reason,
                       _pred('steam menu routed', 3.0),
                       requires=('gesture',), cooldown=MENU_TOGGLE_COOLDOWN)]
    if action == 'power_menu':
        return [Intent('show', 'power-menu',
                       {'via': 'kodi-jsonrpc:GUI.ActivateWindow shutdownmenu'},
                       reason, _pred('currentwindow == 10106', 3.0),
                       requires=('gesture',), cooldown=3.0)]
    if action == 'quit_game':
        if not o.session_present:
            return []       # nothing to quit; game-launch would no-op too
        return [Intent('quit', appid or 'all',
                       {'pids': running, 'resolver': PID_RESOLVER,
                        'via': 'game-launch quit'},
                       reason, _pred('no game pids left', 20.0),
                       requires=('gesture', 'session'), cooldown=3.0)]
    if action == 'tv_toggle':
        return [Intent('tv_toggle', 'tv', {'via': 'tv toggle'}, reason,
                       _pred('tv power state flipped', 15.0),
                       requires=('gesture',), cooldown=TV_TOGGLE_COOLDOWN)]
    if action == 'desktop':
        # The couch server's own route, not a bare xfwm4 show-desktop: it
        # suspends a running game on the way out, the same as the phone does.
        return [Intent('show', 'desktop',
                       {'via': 'couch-api:/api/windows/activate'}, reason,
                       _pred('desktop showing', 5.0),
                       requires=('gesture', 'foreground'), cooldown=3.0)]
    return []               # an action gestureconf let through and we do not
    #                         know: decide nothing rather than guess


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
    # Every gesture goes through the SAME binding dispatch the live watcher
    # uses (action_intents above <-> pad-home-watcher's act()), reading the
    # same file through gestureconf. One file, two stacks: after a rebind the
    # shadow diff still compares like with like instead of scoring the model
    # against a console it no longer describes.
    #
    # T5 note (pre-declared, and deliberately EMPTY): the switcher landed in
    # BOTH stacks in the same change, so there is no whitelist entry to write
    # - show_switcher must appear in both streams or it is a real T4. The one
    # knowingly-different thing is timing, not decisions: couchd holds the
    # gesture region in 'tap-wait' for DOUBLE_TAP_S after any no-op tap, and
    # the "no repair while a gesture is in flight" invariant therefore
    # suppresses drift repairs for that 350ms; the watcher has no such pause.
    # A repair falling exactly in that window shows up as LEGACY-ONLY once and
    # is gone by the next 10s reconcile - triage it T6 (same decision, later),
    # never T4.
    if g == 'hold-fired':
        # defer_handoff: the pad must not move while the button is still down
        # (audit failure 4). The other half is emitted from 'handoff-pending'.
        out += action_intents(o, 'hold', appid, running, defer_handoff=True)

    if g in ('handoff-pending', 'timed-out'):
        reason = ('gesture:hold-release' if g == 'handoff-pending'
                  else 'gesture:hold-release-timeout')
        if o.binding('hold') == 'suspend_to_kodi':
            out += _handoff_intents(o, appid, reason)
        # ...and whatever the release itself is bound to, on top. 'none' by
        # default, so this line changes nothing until someone binds it.
        out += action_intents(o, 'hold_release', appid, running)

    if g == 'long-hold-fired':
        out += action_intents(o, 'long_hold', appid, running)

    if g == 'double-tap':
        out += action_intents(o, 'double_tap', appid, running)

    if g == 'tap-wait' and gesture.is_tap(o.press_duration, o.hold_seconds):
        # A tap that did nothing else. gestureconf guarantees this is bound
        # only when double_tap is not, so a real double-tap can never fire the
        # tap action on its way through; with the default bindings (tap=none)
        # nothing is emitted here at all. The tap that RESUMES a paused game
        # is not this: it is state logic, in 'tap-resume' below.
        #
        # The is_tap() re-check is not redundant. With `hold` bound to Nothing
        # a long press never leaves 'down' for 'hold-fired', so it releases
        # into 'tap-wait' like a tap does; the watcher measures the duration
        # before it dispatches and this has to as well, or a five-second press
        # would fire the tap action on one side of the diff only.
        out += action_intents(o, 'tap', appid, running)

    if g == 'tap-resume':
        out.append(Intent('launch', appid,
                          {'mode': 'resume', 'via': 'game-launch resume',
                           'suspended_flag': o.suspended},
                          'gesture:tap-resume',
                          _pred('game pids back in state S', 5.0),
                          requires=('gesture', 'session'), cooldown=3.0))
        # R7(c), the other half: the suspend UNMAPPED this window to free its
        # pointer grab, so the resume has to map it back or the player thaws a
        # game they cannot see. xfwm4 deiconifies on a pager _NET_ACTIVE_WINDOW,
        # which is what game-launch's `show <appid> via=activate` is.
        out.append(_deiconify_intent(o, appid, 'gesture:tap-resume'))
        if o.kodi_window == 10106:
            out.append(Intent('dismiss', 'power-menu', {'via': 'Input.Back'},
                              'gesture:tap-resume',
                              _pred('currentwindow != 10106', 2.0),
                              requires=('gesture',), cooldown=3.0))

    # -- 2. transitions ---------------------------------------------------
    if sess == 'starting':
        # R7(g): Big Picture is the console's UI mode for GAMING. Steam
        # autostarts -silent into DESKTOP mode (uimode 7), where the pad talks
        # to an overlay the guard could never see (that is R7(f) above), so
        # game-launch switches it per game at launch time. MODEL ONLY: the
        # shell that is launching the game does this and does not yield it,
        # so couchd decides it for its own state and performs nothing.
        if o.steam_known and o.ui_mode is not None \
                and o.ui_mode != STEAM_UI_BIG_PICTURE \
                and o.session_mode not in ('bigpicture', ''):
            out.append(Intent('launch', 'bigpicture',
                              {'via': 'steam-open-bigpicture', 'was': o.ui_mode,
                               'reason': 'ensure-bp-before-game',
                               'mode': o.session_mode, 'appid': appid},
                              'transition:ensure-bp-before-game',
                              _pred(f'SSGL UI mode {STEAM_UI_BIG_PICTURE}', 6.0),
                              requires=('session',), cooldown=30.0,
                              model_only=True))
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
    # R7(e): a game started from INSIDE Big Picture is invisible to our own
    # state - game-launch was invoked as `game-launch bigpicture`, so the
    # session line's appid field is EMPTY and every consumer that keys off it
    # works on the string "bigpicture" instead of a number. Live, 5 Aug 2026,
    # that made the game's own Kodi tile read a running game as "a different
    # game was picked", and it closed and relaunched it: the operator lost his
    # progress. The moment a real appid appears under a Big Picture session,
    # the session line is rewritten in place. MODEL ONLY, like the pre-step
    # above: the launching shell owns the line it wrote (and the watcher keeps
    # its own second net for a hold that lands before that poll comes round).
    if sess in ('starting', 'active') and o.session_present \
            and (o.session or {}).get('appid') in (None, '', 'bigpicture') \
            and appid and str(appid).isdigit() \
            and (o.session or {}).get('launcher_pid'):
        out.append(Intent('set_flag', 'session',
                          {'value': f"{o.session['launcher_pid']} steam {appid}",
                           'launcher': o.session['launcher_pid'],
                           'resolver': 'ledger', 'was': o.session_mode,
                           'reason': 'bigpicture-appid-adoption'},
                          'transition:bigpicture-appid-adoption',
                          _pred('/tmp/game-session names the real appid', 5.0),
                          requires=('session',), cooldown=30.0,
                          model_only=True))
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
                              requires=('enforcement', 'foreground'),
                              cooldown=GUIDE_TOGGLE_COOLDOWN))
        elif _desktop_overlay_open(o):
            # R7(f), invariant 1 arm (b). In DESKTOP ui mode Steam's routing
            # config is Desktop/413080 and NEVER ClientUI, so the arm above
            # cannot fire and never has - which is the "resuming with the PS
            # button ALWAYS brings up the Steam menu" report of 5 Aug 2026: a
            # TAP is consumed by Steam and opens its overlay over the game, a
            # HOLD is "skipped due to length" and opens nothing, which is
            # exactly why only the tap path was ever affected.
            #
            # ONE SHOT per window, and that is safety, not tidiness: the guide
            # is a TOGGLE and our own synthetic press lands in the same log as
            # the press that armed this, so a repeating arm would flip the
            # overlay on and off for the rest of the window. The cooldown is
            # the latch - GUIDE_TOGGLE_COOLDOWN (8s) outlasts the whole 6s
            # enforcement window, so it cannot fire twice inside one.
            out.append(Intent('close_steam_menu', 'steam',
                              {'via': 'vpad-guide', 'invariant': 1,
                               'reason': 'desktop-overlay-after-tap',
                               'ui_mode': o.ui_mode},
                              'guard:desktop-overlay-after-tap',
                              _pred('the overlay is gone', 6.0),
                              requires=('enforcement', 'foreground'),
                              cooldown=GUIDE_TOGGLE_COOLDOWN))
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
            # ...and the suspend that lost its flag may well have iconified it
            # (R7(c)): a thawed game left invisible is audible, holds the pad,
            # and shows the room nothing that explains either.
            out.append(_deiconify_intent(o, appid,
                                         'reconcile:thawed-without-flag'))

        # R7(d): a paused flag with the game still RUNNING. Nothing repaired
        # this until 5 Aug, which is why the 4 Aug guard-vs-freeze race stuck:
        # flag set, game audible behind Kodi, nothing converging. WHAT IS ON
        # SCREEN decides which way to converge - the flag is only wrong if the
        # player can actually see and drive the game.
        if (o.suspended_present and o.pids_known and o.running_pids
                and o.suspended != 'bigpicture'):
            if playing_despite_flag(o):
                out.append(Intent('clear_flag', 'suspended',
                                  {'pids': sorted(o.pid_states),
                                   'resolver': PID_RESOLVER,
                                   'topcls': o.top_class,
                                   'focuscls': o.focused_class},
                                  'reconcile:stale-suspended-while-playing',
                                  _pred('/tmp/game-suspended gone', 2.0),
                                  requires=('session', 'foreground')))
            else:
                out.append(Intent('freeze', appid,
                                  {'pids': o.running_pids,
                                   'resolver': PID_RESOLVER, 'signal': 'SIGSTOP',
                                   'topcls': o.top_class or '?'},
                                  'reconcile:refreeze-lost-suspend',
                                  _pred('all game pids in state T', 5.0),
                                  requires=('session',)))
                # A game that ran on behind Kodi has a live pointer grab again.
                out.append(_iconify_intent(appid,
                                           'reconcile:refreeze-lost-suspend'))

        want = want_pad_owner(o)
        have = o.regions.get('input_ownership')
        if o.kodi_known and o.joystick is not None and have in ('kodi', 'game') \
                and have != want:
            out.append(Intent('route_pad', want,
                              {'via': 'kodi-jsonrpc', 'was': o.joystick},
                              'reconcile:joystick-setting-drift',
                              _pred(f'input.enablejoystick {want == "kodi"}', 2.0),
                              requires=('input_ownership', 'session')))

        # A frozen game must never be what the room is looking at - but the
        # repair above may just have decided that this flag is the thing that
        # is wrong (game on top AND focused = the player is playing), and
        # raising Kodi over a game someone is playing is the opposite repair.
        # The legacy reconcile clears its local `suspended` in that branch for
        # exactly this reason; this is the same rule, written down.
        if o.suspended_present and o.x_known \
                and o.top_class.startswith('steam_app') \
                and not playing_despite_flag(o):
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
    for it in intents:
        # A toggle whose cooldown expires before its own predicted effect
        # deadline can re-decide on a world its last action has not reached -
        # and for a toggle "again" means "undo" (see TOGGLE_VERBS).
        if is_toggle(it) and it.predict and \
                it.cooldown <= float(it.predict.get('deadline_s', 0)):
            bad.append(('toggle_cooldown_outlasts_deadline',
                        f'{it.key} cooldown={it.cooldown} '
                        f'deadline={it.predict.get("deadline_s")}'))
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
    # `sayer` is injectable for the same reason ActingExecutor's is: without
    # it, every unit test that runs an intent through this object sprays
    # "would ..." lines into the LIVE /tmp/couchd.log, which is the phone's
    # log and the evening's evidence. The daemon passes nothing and gets say().
    # `context` is the daemon's per-pass stamp (R5's edge-to-decision latency).
    # A default of "nothing to add" keeps the pure-model tests, which construct
    # this object with a log and nothing else, exactly as they were.
    def __init__(self, log, on_record=None, sayer=say, context=None):
        self.log = log
        self.on_record = on_record or (lambda i: None)
        self.say = sayer
        self.context = context or (lambda: {})
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
        rec.update(self.context())
        self.log.write(rec)
        self.count += 1
        self.on_record(intent)
        self.say(intent.human())
        return rec


# =========================================================================
# effects: the ACTING executor (flip-ready; owns nothing by default)
# =========================================================================
# Everything below this line is dead code while ~/couch/couchd/owns.conf is
# empty, and dead in the structural sense R1 asks for: ExecutorRouter only
# CONSTRUCTS an ActingExecutor for responsibilities that are actually owned, so
# with an empty file no object in this process is able to do anything at all.
# Passivity stays a property of the object graph, not of a flag someone might
# forget to check.
LOCAL_BIN = os.path.join(HOME, '.local', 'bin')
GAME_LAUNCH = os.path.join(LOCAL_BIN, 'game-launch')
GAME_PIDS = os.path.join(LOCAL_BIN, 'game-pids')
PAUSE_SNAP = os.path.join(LOCAL_BIN, 'pause-snap')
VPAD = os.path.join(LOCAL_BIN, 'vpad')
TV_BIN = os.path.join(LOCAL_BIN, 'tv')
XINPUT = os.path.join(COUCH, 'server', 'xinput.py')
TV_WAKE_REQUEST = '/tmp/tv-wake-request'
COUCH_API = 'http://localhost:8790'
SNAP_CLEAR_ON_UNSUSPEND = True

# The guide press that toggles Steam's menu: vpad up (if nobody else has one),
# press, hand it back. Exactly steam-input-guard's sequence including its two
# measured beats - Steam needs ~1.5s to enumerate the pad and ~1s to act on the
# press - which is why this is a detached shell line and not three calls in the
# supervisor's loop (R6: the loop never blocks on Steam).
GUIDE_PRESS_SH = (
    f'if [ ! -e /tmp/vpad.fifo ]; then "{VPAD}" up >/dev/null 2>&1; '
    f'started=1; sleep 1.5; fi; "{VPAD}" press guide >/dev/null 2>&1; '
    f'sleep 1; [ -n "${{started:-}}" ] && "{VPAD}" quit >/dev/null 2>&1; true')

# The frozen game's window, unmapped so its stuck pointer grab dies with it
# (pad-home-watcher.iconify_frozen_game, same two xinput.py calls).
ICONIFY_SH = (
    f'pids=$("{GAME_PIDS}" 2>/dev/null | tr "\\n" " "); [ -n "$pids" ] || exit 0; '
    f'wid=$(timeout 5 python3 "{XINPUT}" gamewin $pids 2>/dev/null); '
    f'case "$wid" in 0x*) timeout 5 python3 "{XINPUT}" iconify "$wid" ;; esac')


class ActionFailed(Exception):
    """C11: an action that did not happen. Logged loudly, never retried in
    the same breath - the level-based next pass (or, having yielded nothing,
    the legacy repair loops) is what converges the world."""


class Actuators:
    """Every side effect couchd is able to have, and nothing else.

    One small object so the acting paths can be unit-tested against a fake:
    no test ever signals a pid, writes a /tmp flag, talks to Kodi or spawns a
    process. Each primitive is bounded: signals and flag writes are syscalls,
    Kodi is a 5s HTTP call, and anything that could take longer than a tick
    (Steam, the TV, game-launch) is DETACHED - its outcome is judged by C17's
    predicted effect, not by a return code we would have to block for.
    """

    def __init__(self, kodi_rpc=None, on_flag_write=None, spawn_scope=True):
        import itertools
        self.kodi_rpc = kodi_rpc
        self.on_flag_write = on_flag_write or (lambda name, content: None)
        # spawn_scope: run helpers as transient systemd UNITS (see spawn()).
        # Named for what it used to do; kept so the tests' one call site and
        # any future rig can turn it off and get a plain detached child.
        self.spawn_scope = spawn_scope
        self._seq = itertools.count(1)

    # -- processes --------------------------------------------------------
    def signal(self, pids, signum):
        sent, missing = [], []
        for pid in pids:
            try:
                os.kill(int(pid), signum)
                sent.append(int(pid))
            except (OSError, ValueError):
                missing.append(pid)
        if pids and not sent:
            raise ActionFailed(f'no pid of {sorted(pids)} could be signalled')
        return {'sent': sent, 'missing': missing, 'signal': int(signum)}

    # Environment a helper needs that couchd's own unit may not have passed on.
    PASS_ENV = ('DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR', 'PATH', 'HOME')

    def spawn(self, argv, env=None, shell_line=None):
        """Detached, and OUT of couchd's sandbox - which needs a transient
        UNIT, not a scope.

        A `--scope` runs the command in THIS process's context: the sandbox is
        per-process and per-mount-namespace, so `ProtectSystem=strict`,
        the seccomp filter and MemoryDenyWriteExecute all follow the child
        into the scope. The concrete casualty is pause-snap, which writes
        ~/couch/data/paused and would take EROFS. A transient unit is execed by
        the USER MANAGER instead, so the child gets the session's own
        environment, its own lifetime (couchd restarting does not kill it) and
        its own accounting (couchd's MemoryMax=256M does not apply to Steam).

        The setsid fallback exists only for a box without systemd-run: it is
        best-effort and DOES inherit the sandbox, so anything it starts may
        fail to write where the same command succeeds under a unit. C17's
        effect check is what notices either way.
        """
        import subprocess
        cmd = ['/bin/sh', '-c', shell_line] if shell_line else list(argv)
        full_env = dict(os.environ, **(env or {}))
        if self.spawn_scope:
            unit = f'couchd-act-{os.getpid()}-{next(self._seq)}'
            run = ['systemd-run', '--user', f'--unit={unit}', '--quiet',
                   '--collect']
            for key in self.PASS_ENV:
                if os.environ.get(key):
                    run.append(f'--setenv={key}={os.environ[key]}')
            for key, val in (env or {}).items():
                run.append(f'--setenv={key}={val}')
            # `--` matters: without it systemd-run would read a child's own
            # options (pause-snap --clear) as its own.
            run.append('--')
            try:
                p = subprocess.Popen(run + cmd, start_new_session=True,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, env=full_env)
                return {'pid': p.pid, 'argv': cmd, 'unit': unit}
            except OSError:
                pass                      # no systemd-run: fall through
        try:
            p = subprocess.Popen(cmd, start_new_session=True,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, env=full_env)
        except OSError as e:
            raise ActionFailed(f'spawn {cmd[0]} failed: {e}') from e
        # Sandboxed: same process context as couchd, so a write outside
        # ReadWritePaths will fail. Flagged in the record, not hidden.
        return {'pid': p.pid, 'argv': cmd, 'unit': None, 'sandboxed': True}

    # -- /tmp flags (write-through; formats copied from the writers) -------
    def write_flag(self, path, content, name=None):
        """Atomic rename-write, because that is what the FlagObserver's
        inotify design (and every other reader on this box) assumes."""
        try:
            write_atomic(path, content)
        except OSError as e:
            raise ActionFailed(f'write {path} failed: {e}') from e
        self.on_flag_write(name or os.path.basename(path), content)
        return {'path': path, 'bytes': len(content)}

    def remove_flag(self, path, name=None):
        try:
            os.remove(path)
            existed = True
        except FileNotFoundError:
            existed = False
        except OSError as e:
            raise ActionFailed(f'remove {path} failed: {e}') from e
        self.on_flag_write(name or os.path.basename(path), None)
        return {'path': path, 'existed': existed}

    def touch(self, path, name=None):
        try:
            with open(path, 'a'):
                os.utime(path, None)
        except OSError as e:
            raise ActionFailed(f'touch {path} failed: {e}') from e
        self.on_flag_write(name or os.path.basename(path), '')
        return {'path': path}

    # -- Kodi -------------------------------------------------------------
    def kodi(self, method, params):
        if self.kodi_rpc is None:
            raise ActionFailed('no Kodi RPC available')
        try:
            res = self.kodi_rpc(method, params)
        except Exception as e:
            raise ActionFailed(f'kodi {method} failed: {e}') from e
        if isinstance(res, dict) and res.get('error'):
            raise ActionFailed(f'kodi {method}: {res["error"]}')
        return {'method': method, 'params': params}

    # -- X ----------------------------------------------------------------
    def raise_kodi(self):
        """Kodi's window Above + focused - the same three Xlib calls
        pad-home-watcher.focus_kodi and game-launch's focus_kodi make, on a
        short-lived display so nothing is left holding the server."""
        try:
            from Xlib import X, display
        except ImportError as e:
            raise ActionFailed(f'python-Xlib missing: {e}') from e
        d = None
        try:
            d = display.Display()

            def find(w):
                try:
                    for c in w.query_tree().children:
                        if (c.get_wm_name() or '') == 'Kodi':
                            return c
                        r = find(c)
                        if r:
                            return r
                except Exception:
                    pass
                return None
            w = find(d.screen().root)
            if w is None:
                raise ActionFailed('no Kodi window on this display')
            w.configure(stack_mode=X.Above)
            with contextlib.suppress(Exception):
                d.set_input_focus(w, X.RevertToParent, X.CurrentTime)
            d.sync()
            return {'window': hex(w.id)}
        except ActionFailed:
            raise
        except Exception as e:
            raise ActionFailed(f'raise kodi failed: {e}') from e
        finally:
            if d is not None:
                with contextlib.suppress(Exception):
                    d.close()

    # -- the couch server -------------------------------------------------
    def couch_api(self, path, payload):
        import urllib.request
        body = json.dumps(payload).encode()
        req = urllib.request.Request(COUCH_API + path, data=body,
                                     headers={'content-type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                r.read()
        except Exception as e:
            raise ActionFailed(f'couch api {path} failed: {e}') from e
        return {'path': path, 'payload': payload}


# -- C17: what each verb's world should look like afterwards ---------------
# Pure functions of the next Observed, so the deadline check is testable
# without a world. None means "no honest oracle in stage 1": the prediction is
# still logged, and the verdict says 'unverified' rather than inventing a pass.
def _eff_freeze(o, it):
    return o.pids_known and all(o.pid_states.get(p, 'T') == 'T'
                                for p in it.args.get('pids', ()))


def _eff_thaw(o, it):
    return o.pids_known and all(o.pid_states.get(p, 'S') != 'T'
                                for p in it.args.get('pids', ()))


def _eff_set_flag(o, it):
    if not o.flags_known:
        return False
    return (o.suspended is not None if it.subject == 'suspended'
            else o.session is not None)


def _eff_clear_flag(o, it):
    if not o.flags_known:
        return False
    return (o.suspended is None if it.subject == 'suspended'
            else o.session is None)


def _eff_route_pad(o, it):
    if not o.kodi_known or o.joystick is None:
        return False
    return o.joystick is (it.subject == 'kodi')


def _eff_show(o, it):
    if it.subject == 'kodi':
        return o.x_known and o.top_name == 'Kodi'
    if it.subject == 'power-menu':
        return o.kodi_known and o.kodi_window == 10106
    if it.subject in ('game', 'bigpicture') or (it.subject or '').isdigit():
        return o.x_known and (o.top_class.startswith('steam_app')
                              or o.big_picture_window)
    return None


def _eff_dismiss(o, it):
    return o.kodi_known and o.kodi_window is not None and o.kodi_window != 10106


def _eff_close_menu(o, it):
    return o.steam_known and not o.steam_menu_open


EFFECT_CHECKS = {
    'freeze': _eff_freeze, 'thaw': _eff_thaw,
    'set_flag': _eff_set_flag, 'clear_flag': _eff_clear_flag,
    'route_pad': _eff_route_pad, 'show': _eff_show,
    'dismiss': _eff_dismiss, 'close_steam_menu': _eff_close_menu,
}


class ActingExecutor(Executor):
    """Executes the intents of the responsibilities couchd owns.

    Contract, in order of importance:
      1. it refuses any intent whose responsibility is not in `owned` (the
         router already routes by that, so this is the second lock);
      2. verb -> action is ONE table (ACTIONS), so "what can couchd do" is a
         list you can read in ten seconds;
      3. every action logs C17's predicted effect + deadline, and the verdict
         lands in the same corpus a few seconds later;
      4. C11: a failed or timed-out action logs loudly and does NOTHING
         further. No retry storm, no half-finished sequence chased with a
         second sequence. The next pass re-derives from the world, and the
         standing escape is the file back to empty - legacy's reconcile
         converges within one ~10s tick (proven by the 4 Aug audit).
    """

    ACTIONS = {
        'freeze': '_a_freeze',
        'thaw': '_a_thaw',
        'kill': '_a_kill',
        'quit': '_a_quit',
        'launch': '_a_launch',
        'set_flag': '_a_set_flag',
        'clear_flag': '_a_clear_flag',
        'route_pad': '_a_route_pad',
        'show': '_a_show',
        'close_steam_menu': '_a_close_steam_menu',
        'dismiss': '_a_dismiss',
        'iconify': '_a_iconify',
        'snapshot': '_a_snapshot',
        'show_switcher': '_a_show_switcher',
        'tv_toggle': '_a_tv_toggle',
        'request_tv_wake': '_a_request_tv_wake',
    }

    # C11 backoff: an action that keeps failing is a responsibility couchd
    # should hand back, not a thing to retry every cooldown until the disk
    # fills. Three consecutive failures of the same (verb, subject) and it
    # doubles from BACKOFF_BASE up to BACKOFF_MAX; a success, or any ownership
    # change, clears it. Only the entering/leaving transitions are said out
    # loud - the skips themselves stay in the JSONL corpus.
    BACKOFF_AFTER = 3
    BACKOFF_BASE = 30.0
    BACKOFF_MAX = 300.0

    def __init__(self, log, actuators, on_record=None, owned=(), sayer=say,
                 context=None):
        self.log = log
        self.act = actuators
        self.on_record = on_record or (lambda i: None)
        self.owned = frozenset(owned)
        self.say = sayer
        self.context = context or (lambda: {})
        self.count = 0
        self.failures = 0
        self.pending = []          # C17 predictions awaiting their deadline
        self.fails = {}            # (verb, subject) -> {'n', 'until', 'said'}
        self.skipped = 0

    # -- the seam ---------------------------------------------------------
    def execute(self, intent, obs):
        resp = owns.responsibility_for_reason(intent.reason)
        rec = {
            'kind': 'intent', 'acted': True, 'responsibility': resp,
            't': obs.now, 'mono': obs.mono,
            'verb': intent.verb, 'subject': intent.subject,
            'args': intent.args, 'reason': intent.reason,
            'regions': {k: v for k, v in obs.regions.items()},
            'predict': intent.predict,
        }
        rec.update(self.context())
        if intent.model_only:
            # Decided, recorded, never performed: the responsibility for this
            # one stays with the process that launches the game (see
            # Intent.model_only). Not a failure and not a refusal - there is
            # nothing here for couchd to do.
            rec.update(acted=False,
                       action={'ok': True, 'model_only': 'legacy keeps this '
                               'step (game-launch does not yield it)'})
            self.log.write(rec)
            self.on_record(intent)
            return rec
        if resp not in self.owned:
            # Unreachable through the router; kept because "acts only on what
            # it owns" is the whole safety claim and deserves two locks.
            rec.update(acted=False, action={'ok': False, 'refused':
                                            f'{resp} is not owned'})
            self.log.write(rec)
            self.say(f'REFUSED {intent.human()} - {resp} is not owned')
            return rec
        key = (intent.verb, intent.subject)
        # Never act twice on a decision whose first action has not been judged
        # yet: for a toggle that is the close-then-reopen dance, and for
        # everything else it is a second helper racing the first.
        if any((p['intent'].verb, p['intent'].subject) == key
               for p in self.pending):
            self.skipped += 1
            rec.update(acted=False,
                       action={'ok': True, 'skipped': 'previous action of this '
                               '(verb, subject) is still inside its C17 '
                               'deadline'})
            self.log.write(rec)
            self.on_record(intent)        # the cooldown still applies
            return rec
        back = self.fails.get(key)
        if back and obs.mono < back['until']:
            self.skipped += 1
            rec.update(acted=False,
                       action={'ok': False, 'backoff': True,
                               'consecutive_failures': back['n'],
                               'retry_in_s': round(back['until'] - obs.mono, 1)})
            self.log.write(rec)           # corpus keeps every one of these
            self.on_record(intent)        # ...the human log does not
            return rec
        method = self.ACTIONS.get(intent.verb)
        try:
            if method is None:
                raise ActionFailed(f'no action for verb {intent.verb}')
            rec['action'] = {'ok': True, **(getattr(self, method)(intent, obs)
                                            or {})}
            self.count += 1
            self.say(f'DID {intent.human()}')
            self._note_success(key)
        except ActionFailed as e:
            self.failures += 1
            rec['acted'] = False
            rec['action'] = {'ok': False, 'error': str(e)}
            # Loud, per C11, and in the phone-readable log: a responsibility
            # that cannot act is a responsibility to hand back.
            self.say(f'ACTION FAILED {intent.human()}: {e} '
                     f'(doing nothing further; roll back with an empty '
                     f'owns.conf)')
            self._note_failure(key, obs)
        except Exception as e:                     # never take the daemon down
            self.failures += 1
            rec['acted'] = False
            rec['action'] = {'ok': False, 'error': f'{type(e).__name__}: {e}'}
            self.say(f'ACTION CRASHED {intent.human()}: {type(e).__name__}: {e}')
            self._note_failure(key, obs)
        self.log.write(rec)
        self.on_record(intent)
        if rec['acted'] and intent.predict:
            self.pending.append({
                'intent': intent,
                'deadline': obs.mono + float(intent.predict.get('deadline_s', 5)),
                'started': obs.mono,
                'check': EFFECT_CHECKS.get(intent.verb),
            })
        return rec

    # -- C11 backoff ------------------------------------------------------
    def _note_failure(self, key, obs):
        st = self.fails.setdefault(key, {'n': 0, 'until': 0.0, 'said': False})
        st['n'] += 1
        if st['n'] >= self.BACKOFF_AFTER:
            wait = min(self.BACKOFF_BASE * 2 ** (st['n'] - self.BACKOFF_AFTER),
                       self.BACKOFF_MAX)
            st['until'] = obs.mono + wait
            if not st['said']:
                st['said'] = True
                self.say(f'{key[0]} {key[1]}: {st["n"]} consecutive failures - '
                         f'backing off (up to {self.BACKOFF_MAX:.0f}s). '
                         f'This responsibility wants handing back.')
            self.log.write({'kind': 'daemon', 'event': 'action-backoff',
                            'verb': key[0], 'subject': key[1],
                            'failures': st['n'], 'wait_s': round(wait, 1)})

    def _note_success(self, key):
        st = self.fails.pop(key, None)
        if st and st['said']:
            self.say(f'{key[0]} {key[1]}: acting again after '
                     f'{st["n"]} failure(s)')
            self.log.write({'kind': 'daemon', 'event': 'action-backoff-cleared',
                            'verb': key[0], 'subject': key[1],
                            'failures': st['n']})

    def forget_failures(self, why='owns-changed'):
        """Ownership moved: whatever was failing is somebody else's problem or
        a fresh start, either way the backoff state is stale."""
        if self.fails:
            self.log.write({'kind': 'daemon', 'event': 'action-backoff-reset',
                            'why': why, 'keys': [list(k) for k in self.fails]})
        self.fails.clear()

    # -- C17: did the world get there? ------------------------------------
    def check_pending(self, o):
        """Called once a pass. Confirms or fails every outstanding
        prediction, then forgets it: a missed effect is evidence, not a queue
        of work (C11 - couchd does not chase its own actions)."""
        out, still = [], []
        for p in self.pending:
            it = p['intent']
            got = None
            if p['check'] is not None:
                with contextlib.suppress(Exception):
                    got = p['check'](o, it)
            if got is True:
                out.append((p, 'confirmed', o.mono - p['started']))
            elif o.mono >= p['deadline']:
                out.append((p, 'unverified' if p['check'] is None else 'missed',
                            o.mono - p['started']))
            else:
                still.append(p)
        self.pending = still
        for p, verdict, latency in out:
            it = p['intent']
            self.log.write({
                'kind': 'effect', 'verdict': verdict, 'verb': it.verb,
                'subject': it.subject, 'reason': it.reason,
                'expected': (it.predict or {}).get('effect'),
                'deadline_s': (it.predict or {}).get('deadline_s'),
                'latency_s': round(latency, 3),
                'regions': dict(o.regions)})
            if verdict == 'missed':
                self.say(f'EFFECT MISSED after {latency:.1f}s: '
                         f'{(it.predict or {}).get("effect")} '
                         f'[{it.verb} {it.subject}] - not retrying (C11)')
        return out

    # -- the actions ------------------------------------------------------
    def _a_freeze(self, it, o):
        return self.act.signal(it.args.get('pids', ()), signal.SIGSTOP)

    def _a_thaw(self, it, o):
        return self.act.signal(it.args.get('pids', ()), signal.SIGCONT)

    def _a_kill(self, it, o):
        return self.act.signal(it.args.get('pids', ()), signal.SIGTERM)

    def _a_quit(self, it, o):
        return self.act.spawn([GAME_LAUNCH, 'quit'])

    def _a_launch(self, it, o):
        """R1 holds even here: couchd STARTS nothing. The one launch it may
        perform is `resume`, which thaws a game this console already froze -
        the recovery path the whole gesture vocabulary depends on (a paused
        game with no way back is precisely what pad-home-watcher refuses to
        allow anyone to bind away)."""
        if (it.args or {}).get('mode') != 'resume':
            raise ActionFailed('stage 1 launches nothing (R1); '
                               f'refused mode={(it.args or {}).get("mode")!r}')
        return self.act.spawn([GAME_LAUNCH, 'resume'])

    def _a_set_flag(self, it, o):
        value = str((it.args or {}).get('value', ''))
        if it.subject == 'suspended':
            # EXACTLY pad-home-watcher.freeze_game's write: the appid, no
            # trailing newline (`with open(SUSPENDED,'w') as f: f.write(appid)`).
            return self.act.write_flag(SUSPENDED_FLAG, value, 'game-suspended')
        if it.subject == 'session':
            # EXACTLY game-launch's `echo "$$ $MODE $APPID" > "$SESSION"`:
            # three space-separated fields and echo's trailing newline.
            text = value if value.endswith('\n') else value + '\n'
            return self.act.write_flag(SESSION_FLAG, text, 'game-session')
        raise ActionFailed(f'no flag named {it.subject!r}')

    def _a_clear_flag(self, it, o):
        if it.subject == 'suspended':
            res = self.act.remove_flag(SUSPENDED_FLAG, 'game-suspended')
            if SNAP_CLEAR_ON_UNSUSPEND:
                # Legacy clears the freeze-frames in the same breath
                # (clear_snapshots / clear_snaps); a frame that outlives its
                # pause is a Kodi tile lying about the console's state.
                with contextlib.suppress(ActionFailed):
                    self.act.spawn([PAUSE_SNAP, '--clear'])
            return res
        if it.subject == 'session':
            return self.act.remove_flag(SESSION_FLAG, 'game-session')
        raise ActionFailed(f'no flag named {it.subject!r}')

    def _a_route_pad(self, it, o):
        return self.act.kodi('Settings.SetSettingValue',
                             {'setting': 'input.enablejoystick',
                              'value': it.subject == 'kodi'})

    def _a_show(self, it, o):
        if it.subject == 'kodi':
            return self.act.raise_kodi()
        if it.subject == 'power-menu':
            return self.act.kodi('GUI.ActivateWindow',
                                 {'window': 'shutdownmenu'})
        if it.subject == 'steam-menu':
            return self.act.spawn(None, shell_line=GUIDE_PRESS_SH)
        if it.subject == 'desktop':
            return self.act.couch_api('/api/windows/activate', {'id': 'desktop'})
        # a game, by appid or by the generic 'game': game-launch's focus_game
        # is the only thing that knows how to find it (pid, class, fallback).
        return self.act.spawn([GAME_LAUNCH, 'focus'])

    def _a_close_steam_menu(self, it, o):
        return self.act.spawn(None, shell_line=GUIDE_PRESS_SH)

    def _a_dismiss(self, it, o):
        return self.act.kodi('Input.Back', {})

    def _a_iconify(self, it, o):
        return self.act.spawn(None, shell_line=ICONIFY_SH)

    def _a_snapshot(self, it, o):
        return self.act.spawn([PAUSE_SNAP, str(it.subject), it.reason],
                              env={'PAUSE_SNAP_SRC': 'couchd'})

    def _a_show_switcher(self, it, o):
        return self.act.kodi('Addons.ExecuteAddon',
                             {'addonid': 'script.couch.switcher'})

    def _a_tv_toggle(self, it, o):
        return self.act.spawn([TV_BIN, 'toggle'])

    def _a_request_tv_wake(self, it, o):
        # tv-waker consumes this within half a second and wakes the set only
        # if it is in standby. The ONLY couchd write outside the two flags.
        return self.act.touch(TV_WAKE_REQUEST, 'tv-wake-request')


class ExecutorRouter(Executor):
    """Owned -> ActingExecutor, everything else -> RecordingExecutor.

    The acting object is built the first time something is owned and dropped
    the moment nothing is (R1's structural passivity), so `owns.conf` empty is
    byte-identical to the daemon that had no acting code at all.
    """

    def __init__(self, recording, acting_factory, sayer=say, log=None):
        self.recording = recording
        self.acting_factory = acting_factory
        self.acting = None
        self.owned = frozenset()
        self.say = sayer
        self.log = log

    @property
    def count(self):
        return self.recording.count + (self.acting.count if self.acting else 0)

    @property
    def failures(self):
        return self.acting.failures if self.acting else 0

    def set_owns(self, current):
        """Apply a fresh parse of owns.conf. Returns True if it changed."""
        actable = frozenset(current.actable)
        if actable == self.owned and (self.acting is not None) == bool(actable):
            return False
        was = sorted(self.owned)
        self.owned = actable
        if not actable:
            self.acting = None            # the object itself goes away
        else:
            if self.acting is None:
                self.acting = self.acting_factory()
            self.acting.owned = actable
            self.acting.forget_failures()
        self.say(f'ownership changed: {was or ["(nothing)"]} -> '
                 f'{sorted(actable) or ["(nothing - shadow)"]}')
        if self.log is not None:
            self.log.write({'kind': 'daemon', 'event': 'owns-changed',
                            'was': was, 'now': sorted(actable),
                            'acting': self.acting is not None})
        return True

    def execute(self, intent, obs):
        resp = owns.responsibility_for_reason(intent.reason)
        if self.acting is not None and resp in self.owned:
            return self.acting.execute(intent, obs)
        return self.recording.execute(intent, obs)

    def check_pending(self, o):
        return self.acting.check_pending(o) if self.acting else []


# =========================================================================
# output: shadow log, snapshots, status
# =========================================================================
class ShadowLog:
    """Append-only JSONL we own (C21): monotonic seq + monotonic clock + wall
    clock on every record. flush always, fsync when idle."""

    # `directory=None` means "wherever SHADOW_DIR points WHEN I AM BUILT", not
    # "wherever it pointed when this module was imported". A default bound at
    # def time is how a unit test that redirects SHADOW_DIR still ends up
    # appending to the live evening's corpus - the same class of mistake as
    # the /tmp/couchd.log spray, and it costs an evening of evidence.
    def __init__(self, directory=None, prefix='couchd'):
        directory = directory or SHADOW_DIR
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
        # ALL the tap/hold arithmetic is gesture.py's, byte for byte the same
        # module the stage-2 input process runs (SR4).
        self.tracker = gesture.PressTracker()
        self.first_event_latency = None    # R5: pad-appearance -> first event
        self._appeared_at = None

    # The tracker's state IS the observer's state; these read-only views keep
    # observe()/write_status() unchanged.
    button_down = property(lambda self: self.tracker.button_down)
    down_since_k = property(lambda self: self.tracker.down_since_k)
    press_duration = property(lambda self: self.tracker.press_duration)
    press_ended_at = property(lambda self: self.tracker.press_ended_at)
    presses = property(lambda self: self.tracker.presses)
    double_armed = property(lambda self: self.tracker.double_armed)
    doubles = property(lambda self: self.tracker.doubles)

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
        return self.tracker.kernel_now()

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
            self.tracker.reset()

    def _readable(self, loop, path, fd):
        try:
            data = os.read(fd, EVENT_SIZE * 64)
        except BlockingIOError:
            return
        except OSError:
            self._drop(loop, path, 'read error')
            self.w.attention('pad-gone', edge=True)
            return
        if not data:
            self._drop(loop, path, 'eof')
            self.w.attention('pad-gone', edge=True)
            return
        for off in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
            sec, usec, etype, code, value = struct.unpack_from(EVENT_FORMAT,
                                                              data, off)
            k = sec + usec / 1e6
            self.tracker.note_event(k)
            self.src.events += 1
            if etype == EV_KEY and code == BTN_MODE:
                if self._appeared_at is not None:
                    self.first_event_latency = time.monotonic() - self._appeared_at
                    self._appeared_at = None
                    self.w.log.write({'kind': 'obs', 'source': 'pad',
                                      'event': 'first-event-latency',
                                      'seconds': round(self.first_event_latency, 3)})
                self.tracker.feed(k, value)
                self.w.log.write({'kind': 'obs', 'source': 'pad',
                                  'event': 'BTN_MODE', 'value': value,
                                  'kernel_t': round(k, 6),
                                  'duration': (round(self.press_duration, 3)
                                               if value == 0 and self.press_duration
                                               else None),
                                  'double_armed': self.tracker.double_armed})
                # THE gesture edge: every show/route/switcher decision the
                # room can feel hangs off this event, so it runs a pass now
                # instead of waiting for the tick (R5).
                self.w.attention('ps-button', edge=True, kernel_t=k)
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
                st = os.lstat(path)
                mtime = st.st_mtime
                # Only regular files carry readable content. vpad.fifo is a
                # FIFO: a blocking open() with no writer parks the whole
                # daemon in wait_for_partner (the 5 Aug 03:00 startup hang).
                # For special files, existence IS the observation.
                if stat_module.S_ISREG(st.st_mode):
                    content = open(path).read().strip()
                else:
                    content = f'<{stat_module.filemode(st.st_mode)[0]}>'
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
            rec = {'kind': 'obs', 'source': 'flags', 'event': 'flag',
                   'name': name, 'value': content,
                   'mtime': round(mtime, 3) if mtime else None}
            if self.w.was_self_written(name, content):
                # couchd's own write-through, coming back through inotify.
                # Annotated, never suppressed: the observation is real and the
                # differ needs it - it just has an author.
                rec['self_written'] = True
            self.w.log.write(rec)
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
        self.was_absent = False

    def _open(self, seek_end=True):
        """First open seeks BACK a little instead of to EOF: without it
        couchd starts blind to the routing state and the ledger until Steam
        writes its next line, which on a quiet evening can be hours."""
        try:
            f = open(self.path, 'r', encoding='utf-8', errors='replace')
            st = os.fstat(f.fileno())
        except OSError as e:
            self.f = None
            if isinstance(e, FileNotFoundError):
                self.was_absent = True
            return f'{type(e).__name__}: {e}'
        if self.was_absent:
            # Born after we started watching (e.g. /tmp log after a reboot):
            # everything in it is new, so read from the top - EOF would
            # swallow the very line whose appearance created the file.
            seek_end = False
            self.was_absent = False
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

    # Steam's own wording, both halves of it (steam-input-guard reads the same
    # two lines out of controller_ui.txt).
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
        # ...and the CONSUMED ones specifically, which is a different fact:
        # "Guide button sent to JS" is a tap Steam ate (and opened its desktop
        # overlay with), "Guide button skipped due to length" is a hold it
        # ignored. R7(f)'s whole detection is that distinction.
        self.guide_consumed_at = None
        self.guide_consumed = 0
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
                if GUIDE_SENT in line:
                    self.guide_consumed += 1
                    self.guide_consumed_at = time.monotonic()
                changed = True
        if not self._seeded:
            # The first read replays log history to learn the current ledger,
            # route and UI mode. Those are state; the guide-press COUNT is a
            # rate, and must start from this run, not from Steam's backlog.
            # Same for the consumed timestamp: a press from before couchd
            # started must never arm an enforcement window's overlay check.
            self._seeded = True
            self.guide_presses = 0
            self.guide_consumed = 0
            self.guide_consumed_at = None
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
        errs, absent = [], []
        for name, tail in self.tails.items():
            lines, err = tail.read_new()
            if err:
                # These logs live in /tmp and are created on first use: after
                # a reboot they simply don't exist until something launches.
                # Absence is quiet, not observer-blindness (5 Aug boot).
                if err.startswith('FileNotFoundError'):
                    absent.append(name)
                else:
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
        if errs:
            detail = '; '.join(errs)
        elif absent:
            detail = ', '.join(f'{n} log absent (nothing launched yet)'
                               for n in absent)
        else:
            detail = self.last or 'quiet'
        self.src.touch(not errs, detail)

    def close(self):
        for tail in self.tails.values():
            tail.close()


class X11Observer:
    """X as an EVENT source, with the poll kept as belt and braces (R6).

    Acquisition happens two ways - the root-window event subscription read off
    the asyncio loop, and the periodic scan - and both end in x11.py's single
    `_scan()`, so there is exactly one interpretation of the screen and no
    chance of the two paths disagreeing. An event never writes a region: it
    marks the cache dirty and wakes the pass, and the pass re-derives
    `foreground` from the same normalization the tick uses.

    A dead display degrades `foreground` to `unknown` and is retried with
    backoff. It may never take the daemon down: X restarting under a running
    couchd is a Tuesday, not an incident.
    """

    BACKOFF = (1.0, 2.0, 5.0, 10.0, 30.0)
    LOG_MIN_GAP = 1.0          # at most one x11 obs record a second

    def __init__(self, world):
        self.w = world
        self.src = world.src('x11')
        self.adapter = None
        self._fd = None
        self._next_connect = 0.0
        self._fails = 0
        self._last_log = 0.0
        self._last_shape = None

    def _backoff(self):
        wait = self.BACKOFF[min(self._fails, len(self.BACKOFF) - 1)]
        self._fails += 1
        self._next_connect = time.monotonic() + wait
        return wait

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
            wait = self._backoff()
            self.src.touch(False, f'{type(e).__name__}: {e} (retry {wait:.0f}s)')
            return
        if not a.connect():
            wait = self._backoff()
            self.src.touch(False, f'{a.state.reason} (retry {wait:.0f}s)')
            self._detach(loop)
            return
        fd = a.fileno()
        if fd is not None and fd != self._fd:
            self._detach(loop)
            self._fd = fd
            with contextlib.suppress(Exception):
                loop.add_reader(fd, self._readable, loop)
        if self._fails:
            self._fails = 0
            self.w.log.write({'kind': 'obs', 'source': 'x11',
                              'event': 'connected', 'display': a.display_name})

    def _detach(self, loop):
        if self._fd is not None:
            with contextlib.suppress(Exception):
                loop.remove_reader(self._fd)
            self._fd = None

    def _readable(self, loop):
        """The event path. It interprets nothing - it counts, wakes the pass
        and lets the pass re-derive the world through the same scan."""
        try:
            self.adapter.drain()
            if self.adapter.d is None:      # adapter dropped the connection
                self._detach(loop)
                self.src.touch(False, self.adapter.state.reason)
                self.w.attention('x11-lost')
                return
            # take_events(), not drain()'s return: the tally has to be CLAIMED
            # or the next poll counts the same events a second time.
            n = self.adapter.take_events()
            if n:
                self._note(n)
                # A window appearing or vanishing is exactly the class of
                # change a show/route decision hangs off, so it wakes the loop.
                self.w.attention('x11-event')
        except Exception as e:
            self.src.touch(False, f'{type(e).__name__}: {e}')
            self._detach(loop)

    def _note(self, n):
        self.src.events += n
        self.src.last_change = time.monotonic()

    def poll(self, loop):
        if self.adapter is None or self.adapter.d is None:
            self.attach(loop)
        if self.adapter is None or self.adapter.d is None:
            return None
        st = self.adapter.refresh()
        # The scan drains the socket itself (see x11.py): whatever it swallowed
        # is counted HERE or it is counted nowhere.
        n = self.adapter.take_events()
        if n:
            self._note(n)
        if self.adapter.d is None:
            self._detach(loop)
            self.src.touch(False, self.adapter.state.reason)
            return None
        self.src.touch(st.ok, st.reason or
                       f'top={st.top_name!r} ev={self.adapter.events}')
        self._log_change(st, n)
        return st

    def _log_change(self, st, n):
        """Give the corpus an x11 channel at last: one record whenever the
        NORMALIZED view moves, rate-limited, so the differ's observer-health
        gate can see this source is alive and the morning triage can read what
        the screen was doing."""
        shape = (st.ok, st.top_name, st.top_class, st.focused_class,
                 st.kodi_present, st.big_picture, st.game_windows)
        if shape == self._last_shape:
            return
        now = time.monotonic()
        if self._last_shape is not None and now - self._last_log < self.LOG_MIN_GAP:
            return
        self._last_shape = shape
        self._last_log = now
        self.w.log.write({'kind': 'obs', 'source': 'x11', 'event': 'screen',
                          'top': [st.top_name, st.top_class],
                          'focused': st.focused_class,
                          'kodi_present': st.kodi_present,
                          'big_picture': st.big_picture,
                          'game_windows': list(st.game_windows),
                          'n_windows': st.n_windows,
                          'events': self.adapter.events,
                          'events_since': n})

    def close(self, loop):
        self._detach(loop)
        if self.adapter is not None:
            self.adapter.close()


# =========================================================================
# the daemon
# =========================================================================
class World:
    """Shared observer state + the one place attention mode is triggered."""

    SELF_WRITE_MEMORY = 15.0     # how long a self-write stays recognisable

    def __init__(self, log):
        self.log = log
        self.sources = {}
        self.attention_until = 0.0
        self.attention_reason = ''
        self.attention_events = 0
        self.wake = asyncio.Event()
        self.self_writes = {}     # flag name -> (content, mono) we wrote
        # The gesture EDGE: the observation that must be decided on now, not
        # at the next tick (R5's 250ms perceptual bound). Set by attention()
        # and consumed by exactly one pass.
        self.edge = None
        self.edges = 0
        self.edges_coalesced = 0

    def src(self, name):
        return self.sources.setdefault(name, Source(name))

    # -- self-written flags (feedback-loop hygiene) ------------------------
    def note_self_write(self, name, content):
        """Recorded the instant an actuator writes a /tmp flag, so the flag
        observer can label the change it is about to see as OURS.

        It is only ever a LABEL: couchd stays level-based, so re-observing its
        own write is not just harmless but the point - the world now matches
        what was wanted, and the same reconcile that asked for it stops asking.
        Without the label, though, the corpus (and the morning triage) could
        not tell couchd's own writes apart from the legacy stack's."""
        self.self_writes[name] = (content, time.monotonic())

    def was_self_written(self, name, content):
        seen = self.self_writes.get(name)
        if not seen:
            return False
        want, when = seen
        if time.monotonic() - when > self.SELF_WRITE_MEMORY:
            return False
        if want is None:
            return content is None
        return content is not None and content.strip() == str(want).strip()

    def attention(self, reason, edge=False, kernel_t=None):
        """An observed change: sample at ATTENTION_PERIOD for a few seconds so
        a fault is seen before the legacy repair loops erase it (blocker 10).
        Also wakes the loop immediately - a slow tick must never swallow a
        button press.

        `edge=True` marks the change as one a DECISION hangs off directly (the
        PS button's own transitions, above all): the loop then runs a pass
        after EDGE_DEBOUNCE rather than at the attention floor, and the
        decisions it produces are stamped with their edge-to-decision latency.
        Edges inside the debounce COALESCE onto the first one - a press and
        its release 30ms apart are two edges but one pass, and the latency is
        measured from the edge that has not been decided yet.
        """
        self.attention_until = time.monotonic() + ATTENTION_SECONDS
        self.attention_reason = reason
        self.attention_events += 1
        if edge:
            self.edges += 1
            if self.edge is None:
                self.edge = {'reason': reason, 'mono': time.monotonic(),
                             'kernel_t': kernel_t, 'seq': self.edges}
            else:
                # An earlier edge is still waiting to be decided: keep ITS
                # timestamp (the latency that matters is the oldest undecided
                # one) and record that this one rode along.
                self.edges_coalesced += 1
                self.edge['coalesced'] = self.edge.get('coalesced', 0) + 1
                self.edge['reason'] = reason
                if kernel_t is not None:
                    self.edge['kernel_t'] = kernel_t
        self.wake.set()

    def take_edge(self):
        """Hand the pending edge to the pass that is about to run. Exactly one
        pass ever sees a given edge, which is what keeps the latency number
        honest and stops a decided edge re-triggering the loop."""
        edge, self.edge = self.edge, None
        return edge

    @property
    def edge_pending(self):
        return self.edge is not None

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
        # Shadow is the default and the fallback: the recorder is always here,
        # the acting half is built only while owns.conf names something (R1).
        self.edge = None            # the edge this pass is deciding (R5)
        self.edge_intents = 0
        self.last_edge_latency = None
        self.recorder = RecordingExecutor(self.log, on_record=self._on_intent,
                                          context=self.intent_context)
        self.actuators = Actuators(kodi_rpc=self._kodi_rpc,
                                   on_flag_write=self.world.note_self_write)
        self.executor = ExecutorRouter(self.recorder, self._make_acting,
                                       log=self.log)
        self.owns = owns.load()
        self._owns_warned = None
        self._env_warned = False
        self._guard_pidfile_ours = False
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
        self._conf_bindings = None      # last bindings said out loud
        self._conf_warnings = None
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
        # 'gesture:ps-double-tap' is only ever emitted when the double-tap
        # actually suspended something, which is exactly when the watcher
        # spawns steam-input-guard - the plain switcher (nothing running)
        # spawns no guard and so opens no window.
        # A rebound gesture that hands the pad to Kodi spawns a guard too, so
        # the trigger keys off the handoff's own close_steam_menu rather than
        # a list of reasons that would go stale on every new binding. Under
        # the default bindings that intent only ever appears at hold-release
        # and ps-double-tap, both of which are named below anyway, so this
        # adds nothing to today's behaviour.
        handoff = (intent.verb == 'close_steam_menu'
                   and intent.reason.startswith('gesture:'))
        if handoff or intent.reason.startswith(
                ('gesture:hold-release', 'gesture:ps-double-tap',
                 'transition:session-ended', 'reconcile:orphaned-session')):
            self.enforcement_target = 'kodi'
            self.enforcement_until = time.monotonic() + GUARD_WINDOW
        elif intent.reason in ('gesture:tap-resume', 'transition:session-started'):
            self.enforcement_target = 'game'
            self.enforcement_until = time.monotonic() + GUARD_WINDOW

    # -- ownership (the flip switch) --------------------------------------
    def _kodi_rpc(self, method, params):
        """The acting executor's Kodi channel is the observer's own HTTP
        client: one place holds the credentials, one place holds the timeout."""
        return self.kodi._http(method, params)

    def _make_acting(self):
        return ActingExecutor(self.log, self.actuators,
                              on_record=self._on_intent,
                              owned=self.executor.owned,
                              context=self.intent_context)

    def refresh_owns(self):
        """Re-read owns.conf (a stat unless it changed) and apply it.

        Every tick, deliberately: a flip - and much more importantly a
        ROLLBACK to empty - must take effect within one tick with nothing
        restarted, on both stacks at once."""
        cur = owns.load()
        if cur.warnings and cur.warnings != self._owns_warned:
            self._owns_warned = cur.warnings
            for w in cur.warnings:
                say(f'owns.conf: {w}')
            self.log.write({'kind': 'daemon', 'event': 'owns-warning',
                            'warnings': list(cur.warnings),
                            'file': cur.path})
        env = os.environ.get('COUCHD_OWNS')
        if env and not self._env_warned:
            self._env_warned = True
            if owns.parse(f'COUCHD_OWNS={env}').names != cur.names:
                say(f'COUCHD_OWNS={env!r} is set in the environment and does '
                    f'NOT match {cur.path}; the FILE is the source of truth '
                    f'(both stacks read it) and the environment is ignored')
        self.owns = cur
        if self.executor.set_owns(cur):
            # Ownership just moved. If the guard came with it, clear any dead
            # pid sitting in the pidfile before we start writing our own.
            self.scavenge_guard_pidfile()
        return cur

    def scavenge_guard_pidfile(self):
        """A guard pidfile naming a dead process, removed BEFORE couchd starts
        writing its own pid there.

        The hazard is pid reuse: couchd write-throughs this file, gets
        SIGKILLed (watchdog, OOM), and the number it left behind is handed to
        some unrelated process by the kernel - which the next suspend then
        SIGTERMs, because that is what the pidfile means. Cheap to prevent,
        impossible to debug after the fact.

        ONLY while couchd owns the guard. In shadow this file belongs to the
        old stack and couchd does not touch it: a stale one is reported as a
        leak by owned_resources() and repaired by nobody, which is exactly the
        passivity contract (M2)."""
        if 'guard' not in self.executor.owned:
            return
        try:
            raw = open(GUARD_PIDFILE).read().strip()
            pid = int(raw)
        except (OSError, ValueError):
            return
        if pid == os.getpid():
            return
        import psutil
        if psutil.pid_exists(pid):
            return
        with contextlib.suppress(ActionFailed):
            self.actuators.remove_flag(GUARD_PIDFILE, 'steam-input-guard.pid')
        say(f'scavenged a stale guard pidfile (pid {pid} is gone) before '
            f'taking the guard')
        self.log.write({'kind': 'daemon', 'event': 'guard-pidfile-scavenged',
                        'stale_pid': pid})

    def guard_pidfile_holder(self):
        """(pid, is-ours) for /tmp/steam-input-guard.pid, or (None, False).

        The model needs both halves. A LIVE foreign pid there is an
        enforcement window somebody else is running, and a freeze has to
        supersede it before the STOPs (R7(d)); a pid that is couchd's own
        write-through is couchd's OWN window, and SIGTERMing that would kill
        the daemon holding the console together - which is precisely the rule
        the legacy watcher yields on.
        """
        raw = self.flags.state.get('steam-input-guard.pid', (None, None))[0]
        try:
            pid = int((raw or '').strip())
        except (TypeError, ValueError):
            return None, False
        if pid == os.getpid():
            return pid, True
        try:
            import psutil
            if not psutil.pid_exists(pid):
                return None, False
        except Exception:
            pass
        return pid, self._guard_pidfile_ours

    def sync_guard_pidfile(self, o):
        """Write-through of /tmp/steam-input-guard.pid while couchd owns the
        guard responsibility (R5-17 / brief D).

        The file's meaning on this box is "an enforcement window is open, and
        this pid owns it": pad-home-watcher.supersede_guard() and the guard's
        own supersede() both read it. When couchd runs the window instead, the
        file has to keep saying that or a suspend would think no window is
        open. Format is the writer's byte for byte - `f.write(str(os.getpid()))`,
        no trailing newline - and the removal keeps the same rule the guard's
        SIGTERM handler uses: only if it is still OURS.

        (The matching legacy edit makes supersede_guard yield while couchd owns
        the guard; without it the watcher would SIGTERM this daemon.)"""
        ours_now = 'guard' in self.executor.owned and \
            self.enforcement_until > time.monotonic()
        if ours_now == self._guard_pidfile_ours:
            return
        try:
            if ours_now:
                self.actuators.write_flag(GUARD_PIDFILE, str(os.getpid()),
                                          'steam-input-guard.pid')
                self._guard_pidfile_ours = True
            else:
                current = ''
                with contextlib.suppress(OSError):
                    current = open(GUARD_PIDFILE).read().strip()
                if current == str(os.getpid()):
                    self.actuators.remove_flag(GUARD_PIDFILE,
                                               'steam-input-guard.pid')
                self._guard_pidfile_ours = False
        except ActionFailed as e:
            say(f'guard pidfile write-through failed: {e}')
            self._guard_pidfile_ours = False

    # -- key bindings -----------------------------------------------------
    def gesture_conf(self):
        """The PS-button bindings, cached on the settings file's mtime.

        Read-only, and outside ~/couch/shadow, so it does not widen what the
        daemon writes; the unit's ReadWritePaths are unchanged. A warning is
        said once per distinct set, not per pass - a rejected config (the
        safety rail) must be visible in /tmp/couchd.log without drowning it.
        """
        conf = gestureconf.load()
        if conf.warnings and conf.warnings != self._conf_warnings:
            self._conf_warnings = conf.warnings
            for w in conf.warnings:
                say(f'bindings: {w}')
            self.log.write({'kind': 'obs', 'source': 'bindings',
                            'event': 'settings-warning',
                            'warnings': list(conf.warnings),
                            'bindings': dict(conf.bindings)})
        if conf.bindings != self._conf_bindings:
            self._conf_bindings = dict(conf.bindings)
            say('bindings: ' + ', '.join(f'{k}={v}' for k, v in
                                         conf.bindings.items()))
            self.log.write({'kind': 'obs', 'source': 'bindings',
                            'event': 'bindings-changed',
                            'bindings': dict(conf.bindings),
                            'timings': conf.timings})
        return conf

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
        conf = self.gesture_conf()
        guard_pid, guard_ours = self.guard_pidfile_holder()
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
            guide_consumed_at=self.steam.guide_consumed_at,
            ledger={k: tuple(sorted(v)) for k, v in self.steam.ledger.items()},
            guard_pid=guard_pid, guard_pid_ours=guard_ours,
            pad_known=pad_src.ok, pad_present=self.pad.present,
            button_down=self.pad.button_down,
            down_since_k=self.pad.down_since_k,
            kernel_now=self.pad.kernel_now(),
            press_duration=self.pad.press_duration,
            press_ended_at=self.pad.press_ended_at,
            double_armed=self.pad.double_armed,
            # Re-read every pass; gestureconf.load() is a stat() unless the
            # file changed, so a rebind takes effect on the next tick without
            # a restart, exactly as it does in the watcher.
            bindings=dict(conf.bindings), hold_seconds=conf.hold_seconds,
            double_tap_seconds=conf.double_tap_seconds,
            long_hold_seconds=conf.long_hold_seconds,
            regions=dict(self.machine.regions),
            region_since=dict(self.machine.since),
            games=dict(self.machine.games),
            enforcement_target=self.enforcement_target,
            enforcement_until=self.enforcement_until,
            recent=dict(self.recent))

    # -- one pass ---------------------------------------------------------
    def pass_once(self, loop):
        # Ownership first: an intent must be routed by the file as it is NOW,
        # not as it was when the daemon started.
        self.refresh_owns()
        # Claim the edge BEFORE observing: everything decided from here on is
        # this edge's consequence, and a second edge arriving mid-pass has to
        # get its own pass rather than being credited to this one. Passes are
        # never reentrant - the loop is single-threaded and pass_once is
        # synchronous - so "one edge, one pass" needs nothing but this.
        self.edge = self.world.take_edge()
        self.edge_intents = 0
        o = self.observe(loop)
        self.machine.step(o)
        o = replace(o, regions=dict(self.machine.regions),
                    region_since=dict(self.machine.since),
                    games=dict(self.machine.games))
        # C17: last pass's predictions, judged against this pass's world,
        # before any new decision is taken on top of them.
        self.executor.check_pending(o)
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
        self.sync_guard_pidfile(o)
        self.passes += 1
        self.log_edge(o, intents)
        return o, intents

    # -- R5: edge-to-decision latency ------------------------------------
    def intent_context(self):
        """The per-intent stamp both executors add to their JSONL record.

        This is the number R5 gates: how long after the physical edge (the
        kernel timestamp of the BTN_MODE event, where there is one) couchd
        DECIDED. The differ's matched-offset distribution measures the same
        thing from the outside, against the legacy stack; this measures it
        from the inside, so a regression is attributable without a second
        stack to compare against.
        """
        e = self.edge
        if not e:
            return {'trigger': 'tick'}
        self.edge_intents += 1
        out = {'trigger': 'edge',
               'edge': {'reason': e['reason'], 'edge_seq': e['seq'],
                        'coalesced': e.get('coalesced', 0)},
               'edge_latency_s': round(max(0.0, time.monotonic() - e['mono']), 4)}
        if e.get('kernel_t'):
            # Kernel time is the honest zero (R4): it is when the button
            # actually moved, not when we got round to reading it.
            out['edge_kernel_latency_s'] = round(
                max(0.0, self.pad.kernel_now() - e['kernel_t']), 4)
        return out

    def log_edge(self, o, intents):
        """One record per decided edge, so the distribution is greppable
        without re-deriving it from the intent stream."""
        e = self.edge
        if not e:
            return
        self.last_edge_latency = round(max(0.0, time.monotonic() - e['mono']), 4)
        rec = {'kind': 'latency', 'event': 'gesture-edge', 't': o.now,
               'reason': e['reason'], 'edge_seq': e['seq'],
               'coalesced': e.get('coalesced', 0),
               'decide_latency_s': self.last_edge_latency,
               'intents': [i.key for i in intents],
               'gesture': o.regions.get('gesture')}
        if e.get('kernel_t'):
            rec['kernel_latency_s'] = round(
                max(0.0, self.pad.kernel_now() - e['kernel_t']), 4)
        self.log.write(rec)

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
        # What couchd itself is holding right now, so a resource of OURS is
        # never triaged as somebody else's leak (and so a leak of ours shows up
        # as one the moment the list and the world disagree).
        expected = ['guard-pidfile'] if self._guard_pidfile_ours else []
        return {'vpad_fifo': vpad, 'guard_pid': guard_pid,
                'guard_alive': guard_alive, 'pad_nodes': uinput,
                'expected_owned': expected, 'leaks': leaks}

    # -- outputs ----------------------------------------------------------
    def write_status(self, o):
        mono = time.monotonic()
        status = {
            't': time.time(), 'pid': os.getpid(),
            'uptime_s': round(mono - self.started_mono, 1),
            # 'shadow' until owns.conf names something couchd can execute; the
            # phone's couchd card shows this line and the list beside it.
            'mode': 'acting' if self.executor.owned else 'shadow',
            'owns': sorted(self.executor.owned),
            'owns_declared': self.owns.sorted,
            'owns_file': self.owns.path,
            'owns_warnings': list(self.owns.warnings),
            'acted': (self.executor.acting.count if self.executor.acting else 0),
            'action_failures': self.executor.failures,
            'action_skipped': (self.executor.acting.skipped
                               if self.executor.acting else 0),
            'action_backoff': (sorted('%s %s' % k for k in
                                      self.executor.acting.fails)
                               if self.executor.acting else []),
            'attention': self.world.attentive,
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
            # R5: how many decisions rode the gesture edge rather than the
            # tick, and how many neighbouring edges the debounce absorbed.
            'edges': {'seen': self.world.edges,
                      'coalesced': self.world.edges_coalesced,
                      'last_latency_s': self.last_edge_latency},
            'resource_leaks': list(self.owned.get('leaks', ())),
            # What the PS button is actually bound to right now, so the phone
            # can show it without re-reading Kodi's addon_data itself.
            'bindings': dict(o.bindings),
            'timings': {'hold_seconds': o.hold_seconds,
                        'double_tap_seconds': o.double_tap_seconds,
                        'long_hold_seconds': o.long_hold_seconds},
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
        self.refresh_owns()
        mode = 'acting' if self.executor.owned else 'shadow mode'
        say(f'couchd up ({mode}, pid {os.getpid()}); {owns.describe(self.owns)}'
            f'; writing {SHADOW_DIR}')
        self.log.write({'kind': 'daemon', 'event': 'start', 'pid': os.getpid(),
                        'mode': 'acting' if self.executor.owned else 'shadow',
                        'owns': sorted(self.executor.owned),
                        'owns_file': self.owns.path,
                        'steam_logs': STEAM_LOGS})
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
                await self._sleep_until_next(mono, self.gesture_deadline(o))
        finally:
            await self.shutdown(loop)

    def gesture_deadline(self, o):
        """When the next gesture guard could flip with no further events.

        The hold threshold, the double-tap window and the handoff timeout are
        decisions taken by a CLOCK, not by an event, and sampling for them at
        the attention rate charges every one of them up to 200ms of latency
        for nothing. Returning the moment itself lets the sleeper wake on it.
        Monotonic seconds from now, or None.
        """
        if o is None:
            return None
        out = []
        g = o.regions.get('gesture')
        if o.button_down and o.down_since_k is not None:
            # kernel clock -> "how much longer", which is the same number in
            # any timebase because both are advancing at one second a second.
            held = max(0.0, o.kernel_now - o.down_since_k)
            if o.binding('hold') != 'none':
                out.append(o.hold_seconds - held)
            if o.binding('long_hold') != 'none' and o.binding('hold') == 'none':
                out.append(o.long_hold_seconds - held)
        since = o.mono - o.region_since.get('gesture', o.mono)
        if g == 'tap-wait':
            out.append(o.double_tap_seconds - since)
        if g in ('hold-fired', 'handoff-pending'):
            out.append(HANDOFF_TIMEOUT - since)
        out = [d for d in out if d is not None and d > 0]
        return min(out) if out else None

    async def _sleep_until_next(self, started, deadline=None):
        """The pacing rule, in one place (R6). Base tick TICK_SECONDS; an
        observed change wakes us early but never lets us sample faster than
        ATTENTION_PERIOD; outside an attention window nothing ever runs
        faster than MIN_PERIOD. Kodi has its own >=10s limiter.

        Two things outrank all of that, and only these two (R5):

          * a gesture EDGE runs a pass after EDGE_DEBOUNCE. Nothing else may
            be that fast, and nothing may make the tick or the watchdog wait
            on it: the loop still pings the watchdog and still runs its slow
            tick on schedule, because both are keyed off elapsed time rather
            than off how the pass was triggered;
          * a gesture DEADLINE (the hold threshold and friends) wakes us at
            the moment itself instead of at the next attention sample.
        """
        if self.world.edge_pending:
            # An edge arrived while the pass was running: it gets its own pass
            # immediately, minus the debounce that coalesces its neighbours.
            await asyncio.sleep(EDGE_DEBOUNCE)
            return
        target = ATTENTION_PERIOD if self.world.attentive else TICK_SECONDS
        if deadline is not None:
            target = min(target, max(deadline, EDGE_DEADLINE_FLOOR))
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
            if self.world.edge_pending:
                # The button moved. Coalesce for EDGE_DEBOUNCE (a press and
                # its release land tens of ms apart and are one decision), then
                # decide - no attention floor, no minimum period.
                await asyncio.sleep(EDGE_DEBOUNCE)
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
        # C27: release in `finally` on every teardown path. A guard pidfile
        # left behind by a stopped couchd would make the next suspend think an
        # enforcement window is open and SIGTERM a pid that no longer exists.
        if self._guard_pidfile_ours:
            with contextlib.suppress(Exception):
                if open(GUARD_PIDFILE).read().strip() == str(os.getpid()):
                    self.actuators.remove_flag(GUARD_PIDFILE,
                                               'steam-input-guard.pid')
            self._guard_pidfile_ours = False
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
    # The systemd watchdog kills with SIGABRT; with faulthandler enabled that
    # SIGABRT lands in the journal as a Python traceback instead of a bare
    # core dump, so the next hang is diagnosable from the log alone.
    faulthandler.enable()
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
