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

# The supervisor wire (stage 2). couchd LISTENS; the input process connects
# and sends RAW BTN_MODE events with their kernel timestamps, which the
# PadObserver below feeds to the same PressTracker it feeds from evdev. See
# supervisor.py's module docstring for why the wire carries observations and
# never classified gestures. Until something connects, none of it runs.
import supervisor

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
GUARD_BIN = '/home/ds2000/.local/bin/steam-input-guard'
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
# ...except ONE targeted read after couchd acts on something only a Kodi read
# can confirm (see KODI_OBSERVED_EFFECTS). It is not a second cadence: it is a
# single read, asked for by name, and the limiter governs everything else.
KODI_EFFECT_READ_FLOOR = 0.5  # two targeted reads may not come closer than this
# The window id Kodi gives a select dialog - what script.couch.switcher draws.
KODI_SELECT_DIALOG = 12000
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
# The source files that DECIDE things. A corpus is only comparable with
# another corpus written by the same model, so the daemon fingerprints these
# at startup and stamps the answer on its start record; tools/shadow-diff keys
# "stale model" off that fingerprint instead of off "newest process start
# wins", which used to mark an entire evening stale because the daemon was
# restarted after it (and turned a 4-minute idle window into the verdict).
MODEL_DIR = os.path.dirname(os.path.abspath(__file__))
# supervisor.py is in here because it decides what couchd SEES: what it drops,
# what it reorders and what it refuses as malformed all change the input the
# rest of this file reasons over, and two corpora written either side of a
# change to it are not one model's evidence.
MODEL_FILES = ('couchd.py', 'gesture.py', 'gestureconf.py', 'owns.py',
               'supervisor.py')


def model_version():
    """{'version': 12 hex chars, 'files': [...], 'git': head-or-None}.

    A content hash rather than a git SHA: the SHA says which commit is checked
    out, the hash says what the daemon is actually running, and on this box
    those differ every time someone edits before committing. The git head is
    recorded beside it because it is what a human reads.
    """
    import hashlib
    h = hashlib.sha256()
    seen = []
    for name in MODEL_FILES:
        try:
            with open(os.path.join(MODEL_DIR, name), 'rb') as f:
                h.update(f.read())
            seen.append(name)
        except OSError:
            h.update(b'<unreadable>')
    return {'version': h.hexdigest()[:12], 'files': seen, 'git': git_head()}


def git_head():
    """The checked-out commit, read from .git without spawning git (the unit's
    sandbox has no business running subprocesses at startup). None if there is
    no repo, which is never an error."""
    try:
        head = open(os.path.join(COUCH, '.git', 'HEAD')).read().strip()
    except OSError:
        return None
    if not head.startswith('ref:'):
        return head[:12] or None
    try:
        ref = head.split(None, 1)[1]
        return open(os.path.join(COUCH, '.git', ref)).read().strip()[:12]
    except (OSError, IndexError):
        return None


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
    # WM_CLASS of every MAPPED steam_app_* window, straight from the X11
    # scan. What the iconify oracle needs: an iconified window is unmapped,
    # so it leaves this tuple - a window merely COVERED by Kodi does not.
    game_windows: tuple = ()

    # Freeze-frames pause-snap has written: appid -> wall-clock capture time
    # of the newest jpg (the <appid>__<epoch_ms>.jpg filename convention).
    # What the snapshot oracle reads; {} when the paused dir is empty/absent.
    snaps: dict = field(default_factory=dict)

    # Steam logs
    steam_known: bool = False
    steam_route: str = ''                  # last OnFocusWindowChanged text
    steam_route_at: float = None           # mono when that line was read
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
    hold_release_pending: bool = False     # the tracker classified a
    #                                        HOLD_RELEASE no state has taken
    #                                        yet (both edges coalesced)
    double_tap_pending: bool = False       # ...and its double twin: a
    #                                        DOUBLE_TAP decided while the
    #                                        machine sat in idle throughout

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
    # First-sighting clocks for the two flag/pid disagreements the drift
    # repairs act on (Machine._track_drift): mono when the pair started
    # disagreeing in that direction, None while it does not. The repairs
    # require the disagreement to OUTLIVE a resume's flag-first critical
    # section (FLAG_DRIFT_PERSIST_S) before treating it as drift. A
    # hand-built Observed that sets the disagreeing fields without these
    # answers "held forever" (drift_persisted's None arm), so the repairs
    # fire exactly as they did before the debounce existed.
    suspended_running_since: float = None
    frozen_noflag_since: float = None

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
        game_windows=(), snaps={},
        steam_known=True, steam_route='', steam_route_at=1000.0, ui_mode=7,
        ledger={},
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
        games={}, enforcement_target=None, enforcement_until=0.0, recent={},
        suspended_running_since=None, frozen_noflag_since=None)
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
         'request_tv_wake', 'show_switcher', 'tv_toggle', 'snapshot',
         'spawn_guard')
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
REPAIR_COOLDOWN = 30.0          # Intent's default, named where a repair's two
#                                 halves have to be given it explicitly (T4-3)
# How long a flag/pid DISAGREEMENT must persist before the freeze/thaw drift
# repairs believe it (the reconcile-flip hard gate, 6 Aug 2026). game-launch
# clears /tmp/game-suspended BEFORE its SIGCONTs on every resume path, so the
# sub-second between the two reads exactly like a lost thaw - and before that
# reorder, the sub-second the OLD order left read like a lost suspend, which
# is what this model decided three times on the acceptance night (would
# freeze [reconcile:refreeze-lost-suspend], 03:18/03:33/03:42): acted, that
# is a SIGSTOP mid-resume. Real drift persists for minutes (the 4 Aug race
# sat stuck until repaired); a resume's critical section is gone in well
# under a second, and its worst-case straddle - flag data read just before
# the rm, pid data just after the SIGCONTs - lives inside ONE pass. Two
# seconds of persistence therefore separates them cleanly, and the repairs
# still land an order of magnitude inside their 10s legacy cadence. The
# watcher's THAW_RECHECK_S and the guard's THAW_CONFIRM_S are this same
# contract on their own cadences.
FLAG_DRIFT_PERSIST_S = 2.0
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
    cooldown: float = REPAIR_COOLDOWN
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


def g_released_hold_coalesced(o):
    """A whole hold whose press AND release landed between two passes.

    The region is sampled and the button is not (the coalesced double-tap
    lesson, one tier up): a loop stall longer than hold_seconds - a hung
    Kodi read, an X scan - swallows both edges, the machine never sees the
    button down, and a >=0.9s press used to fall through to ps-tap-noop and
    drop the suspend in silence. The tracker already decided HOLD_RELEASE at
    the release, in kernel time; `hold_release_pending` is that decision
    held for a level-based reader, consumed when the region takes it
    (_on_transition) and superseded by any new press. Bound-hold only: with
    `hold` unbound the long-hold tier has no equivalent marker, which is a
    declared gap, not an accident."""
    return (o.binding('hold') != 'none' and not o.button_down
            and o.hold_release_pending)


def g_released_double_coalesced(o):
    """BOTH taps of a double landed inside stalled passes: the machine sat
    in idle throughout, so none of the in-flight states that ask
    g_released_double ever ran. Caught live by the sweep's 60ms scenario
    (5 Aug 17:02, two coalesced passes in a row under post-restart load).
    Guarded on the tracker's CONSUMABLE double_tap marker, never on raw
    double_armed - which deliberately survives the release and would
    re-fire from idle forever (the stale-arming hazard the bf34a27 comment
    warned about). Consumed on any entry to the double-tap state."""
    return (o.binding('double_tap') != 'none' and not o.button_down
            and o.double_tap_pending)


def g_released_double(o):
    """The second half of a double-tap: released, itself a tap, and it began
    inside DOUBLE_TAP_S of the previous tap's release.

    This is THE double-tap decision, and it is the tracker's, not the table's
    (SR4). Every state with a press in flight - 'down', 'tap-wait' and
    'down-again' - asks it, because which of those states the machine happens
    to be sitting in depends on how the edges fell relative to the passes, and
    that is sampling luck rather than anything the player did. What the player
    did is what `double_armed` records, in kernel time, at the press.

    `double_armed` is the tracker's, computed in KERNEL time (R4) - the
    tap-wait state below only says a second press is plausible, this says it
    actually was one. The hold transition is tried first in every state that
    has both, so tap-then-hold is always the hold.
    """
    return (not o.button_down and o.double_armed
            and gesture.is_tap(o.press_duration))


def g_tap_window_fire(o):
    """The deferred BOUND tap's window shut with no second press: fire it.

    Ordered before the plain expiry in 'tap-wait', so an unbound tap still
    falls through to idle exactly as before. is_tap() for the same reason the
    emission re-checks it: with `hold` unbound a >=0.9s press releases into
    'tap-wait' and must not fire the tap action."""
    return (o.binding('tap') != 'none'
            and gesture.is_tap(o.press_duration, o.hold_seconds)
            and gesture.double_tap_window_over(_since(o, 'gesture'),
                                               o.double_tap_seconds))


def g_tap_decided(o):
    """The tap's bound action was emitted, whatever it is bound to - the
    same state-closing rule as g_double_tap_decided one tier up."""
    return any(k.count('|') >= 2
               and k.split('|', 2)[2].startswith('gesture:ps-tap')
               and (o.mono - t) < 3.0 for k, t in o.recent.items())


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


def g_double_tap_decided(o):
    """The double-tap's bound action was emitted, WHATEVER it is bound to.

    g_switcher_emitted matches only the default binding's exact intent key,
    so with double_tap rebound (steam_menu, power_menu, tv_toggle...) the
    region used to park in 'double-tap' for the whole 8s gesture_stale
    fallback - suppressing repairs, and re-emitting the action when its
    cooldown expired inside those 8s (a second guide press at +6s toggles
    the menu it just opened; adversarial review, 5 Aug). Any recent intent
    whose reason names the double-tap closes the state."""
    return any(k.count('|') >= 2
               and k.split('|', 2)[2].startswith(('gesture:double-tap',
                                                  'gesture:ps-double-tap'))
               and (o.mono - t) < 3.0 for k, t in o.recent.items())


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


# The freeze-frame overlay tools/curtain draws over suspend/resume shuffles
# (WM_CLASS couch-curtain, deploy item 1, 6 Aug 2026). By construction it is
# an unknown fullscreen window on top of the console - exactly the shape the
# guards read as drift - so BOTH stacks whitelist the class. couchd
# classifies it as a transition overlay rather than 'other': foreground
# 'other' during a suspend is what trips guard:wanted-window-not-on-top, and
# a repair restacking against a window that re-raises itself is a fight.
CURTAIN_CLASS = 'couch-curtain'


def curtain_on_top(o):
    """A couch-curtain overlay is the top window: a transition is being
    HIDDEN, not drifted into. Shared by the foreground classifier and by
    every repair that would otherwise read the covered screen as drift.
    Matched on class OR name because the tool sets both to the same string
    and a window that lost one property mid-teardown must still count."""
    return bool(o.x_known and CURTAIN_CLASS in ((o.top_class or ''),
                                                (o.top_name or '')))


def g_fg_curtain(o):
    return curtain_on_top(o)


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
                 ('button_down', 'down', 'ps-press'),
                 # Both edges of a whole HOLD swallowed by one stalled pass:
                 # the machine never left idle, but the tracker decided
                 # HOLD_RELEASE at the release (see g_released_hold_coalesced).
                 ('released_hold_coalesced', 'hold-fired', 'ps-hold-coalesced'),
                 # ...and a whole DOUBLE swallowed by two: both taps
                 # coalesced, decided by the tracker's consumable marker
                 # (see g_released_double_coalesced).
                 ('released_double_coalesced', 'double-tap',
                  'ps-double-tap-coalesced')],
        # The hold is tried first, exactly as before; the long-hold tier below
        # it is unreachable unless `hold` is bound to Nothing (g_hold_fires /
        # g_long_hold_fires), so under the default bindings this list is the
        # one it has always been.
        # `released_double` sits here, above the ordinary release, because the
        # REGION IS SAMPLED AND THE BUTTON IS NOT. A pass is a level-based look
        # at the world, so when two edges land between two passes the machine
        # sees only the last one: tap-1's release and tap-2's press 48ms apart
        # both fall inside one 50ms debounce, the pass sees "still down", and
        # the machine never leaves this state - so tap-2's release used to fall
        # through to ps-tap-noop and the double-tap was dropped in silence.
        # (Live, 5 Aug 13:57:11.5: a real double-tap by the owner, edge_seq 19,
        # coalesced:1, no intent, while the yielded watcher shows legacy firing
        # the switcher. >=120ms fired, 48ms did not.)
        #
        # The fix is to ask the arbiter instead of inferring from the path
        # taken: gesture.PressTracker already decided this release completes a
        # double (it computes double_armed at the PRESS, in kernel time, and
        # holds it through the release), and g_released_double is that
        # decision. SR4 says the arithmetic lives in gesture.py and both stacks
        # read it; the table's job is to trust it from every state where a
        # press is in flight, not to re-derive it from the states it happened
        # to pass through.
        'down': [('hold_fires', 'hold-fired', 'ps-held-0.9s'),
                 ('long_hold_fires', 'long-hold-fired', 'ps-held-long'),
                 # ...and the coalesced variant: press seen, then a stall ate
                 # the rest of the hold and the release. Tried before the
                 # double/tap releases for the same reason hold_fires is
                 # first: a >=0.9s press is a hold, and HOLD_RELEASE has
                 # already disarmed the double-tap window.
                 ('released_hold_coalesced', 'hold-fired', 'ps-hold-coalesced'),
                 ('released_double', 'double-tap', 'ps-double-tap-coalesced'),
                 ('released_tap_resume', 'tap-resume', 'ps-tap-with-paused-game'),
                 ('released', 'tap-wait', 'ps-tap-noop')],
        # A tap that did nothing (no paused game to resume) is not final until
        # the double-tap window shuts: a second press inside it is the
        # switcher gesture, not a new first tap. Nothing is DELAYED by this -
        # the tap's own action, if it had one, already fired from 'down' - so
        # the live watcher's tap latency is unchanged.
        'tap-wait': [('pad_unknown', UNKNOWN, 'pad-observer-blind'),
                     ('button_down', 'down-again', 'second-press-inside-window'),
                     # tap, then a WHOLE second press >=0.9s inside one pass
                     # gap: the tracker called it HOLD_RELEASE (tap-then-hold
                     # is always the hold) and disarmed the window.
                     ('released_hold_coalesced', 'hold-fired',
                      'ps-hold-coalesced'),
                     # ...and the same coalescing hazard one step later: when
                     # tap-2's press AND its release both land between two
                     # passes, the machine never enters 'down-again' either.
                     # Reaching this rule requires a press since we arrived
                     # here (nothing else can set double_armed), so a stale
                     # arming cannot fire it.
                     ('released_double', 'double-tap', 'ps-double-tap-coalesced'),
                     # The deferred resume, before the plain expiry: a tap on a
                     # PAUSED game waited out the double-tap window here (see
                     # g_released_tap_resume) and now means what it always meant.
                     ('tap_resume_due', 'tap-resume', 'paused-tap-window-expired'),
                     # The deferred BOUND tap (tap + double-tap both bound
                     # since 8 Aug 2026): window shut, no second press - the
                     # tap fires from its own state so the emission below gets
                     # a pass to run before the region reaches idle.
                     ('tap_window_fire', 'tap-fired', 'tap-window-expired'),
                     ('double_window_over', 'idle', 'double-tap-window-expired')],
        # Reachable ONLY from tap-wait via the shut window: the single tap is
        # now final and its bound action emits here (mirroring 'double-tap').
        'tap-fired': [('pad_unknown', UNKNOWN, 'pad-observer-blind'),
                      ('button_down', 'down', 'ps-press'),
                      ('tap_decided', 'idle', 'tap-decided')],
        # Reachable ONLY from tap-wait, which is why a double-tap can never
        # follow a tap that resumed a paused game: that tap goes to
        # 'tap-resume' instead, and the resume owns the pad from there.
        'down-again': [('hold_fires', 'hold-fired', 'ps-held-0.9s'),
                       ('long_hold_fires', 'long-hold-fired', 'ps-held-long'),
                       ('released_hold_coalesced', 'hold-fired',
                        'ps-hold-coalesced'),
                       ('released_double', 'double-tap', 'ps-double-tap'),
                       ('released_tap_resume', 'tap-resume',
                        'ps-tap-with-paused-game'),
                       ('released', 'tap-wait', 'ps-tap-noop')],
        'double-tap': [('switcher_emitted', 'idle', 'switcher-decided'),
                       # rebound double-taps: whatever the action, its
                       # emission closes the state (see g_double_tap_decided)
                       ('double_tap_decided', 'idle', 'double-tap-decided'),
                       ('gesture_stale', 'idle', 'gesture-abandoned')],
        'hold-fired': [('released_no_handoff', 'idle', 'hold-action-done'),
                       ('released', 'handoff-pending', 'ps-released-after-hold'),
                       ('handoff_overdue', 'timed-out', 'release-never-came')],
        # A long hold has no deferred half: whatever it was bound to fired at
        # the threshold, so the release just ends the gesture.
        'long-hold-fired': [('released', 'idle', 'ps-released-after-long-hold'),
                            # A STUCK button: both exits above need button-up,
                            # so a release that never comes used to park here
                            # forever, re-firing the bound action every
                            # cooldown (tv_toggle every 20s). Same deadline as
                            # the hold's own stuck path.
                            ('handoff_overdue', 'timed-out',
                             'release-never-came'),
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
        # 'fg_curtain' sits ABOVE 'fg_other' in every list: the curtain is,
        # by construction, a window no other guard recognises, and falling
        # through to 'other' ("something-else-on-top") mid-transition is what
        # the whitelist exists to prevent. It sits BELOW kodi/bigpicture/game
        # only for reading order - when the curtain is on top those guards
        # are false anyway (the top window's class/name is couch-curtain).
        UNKNOWN: [('x_unknown', UNKNOWN, 'x-unreachable'),
                  ('fg_kodi', 'kodi', 'kodi-on-top'),
                  ('fg_bigpicture', 'bigpicture', 'big-picture-on-top'),
                  ('fg_game', 'game', 'game-window-on-top'),
                  ('fg_curtain', 'curtain', 'transition-curtain-on-top'),
                  ('fg_other', 'other', 'something-else-on-top')],
        'kodi': [('x_unknown', UNKNOWN, 'x-unreachable'),
                 ('fg_bigpicture', 'bigpicture', 'big-picture-on-top'),
                 ('fg_game', 'game', 'game-window-on-top'),
                 ('fg_kodi', 'kodi', 'kodi-on-top'),
                 ('fg_curtain', 'curtain', 'transition-curtain-on-top'),
                 ('fg_other', 'other', 'something-else-on-top')],
        'game': [('x_unknown', UNKNOWN, 'x-unreachable'),
                 ('fg_kodi', 'kodi', 'kodi-on-top'),
                 ('fg_bigpicture', 'bigpicture', 'big-picture-on-top'),
                 ('fg_game', 'game', 'game-window-on-top'),
                 ('fg_curtain', 'curtain', 'transition-curtain-on-top'),
                 ('fg_other', 'other', 'something-else-on-top')],
        'bigpicture': [('x_unknown', UNKNOWN, 'x-unreachable'),
                       ('fg_kodi', 'kodi', 'kodi-on-top'),
                       ('fg_game', 'game', 'game-window-on-top'),
                       ('fg_bigpicture', 'bigpicture', 'big-picture-on-top'),
                       ('fg_curtain', 'curtain', 'transition-curtain-on-top'),
                       ('fg_other', 'other', 'something-else-on-top')],
        'curtain': [('x_unknown', UNKNOWN, 'x-unreachable'),
                    ('fg_kodi', 'kodi', 'kodi-on-top'),
                    ('fg_bigpicture', 'bigpicture', 'big-picture-on-top'),
                    ('fg_game', 'game', 'game-window-on-top'),
                    ('fg_curtain', 'curtain', 'transition-curtain-on-top'),
                    ('fg_other', 'other', 'something-else-on-top')],
        'other': [('x_unknown', UNKNOWN, 'x-unreachable'),
                  ('fg_kodi', 'kodi', 'kodi-on-top'),
                  ('fg_bigpicture', 'bigpicture', 'big-picture-on-top'),
                  ('fg_game', 'game', 'game-window-on-top'),
                  ('fg_curtain', 'curtain', 'transition-curtain-on-top')],
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


def hold_marker_spent(region, frm, to):
    """Has the gesture region FINISHED with the press the tracker's
    HOLD_RELEASE marker describes?

    Two cases spend it: the region TAKES the hold (entering hold-fired,
    coalesced or live, or handoff-pending off the release), and the region
    COMPLETES a hold gesture back to idle from any of its states. The second
    case is not decoration: a stuck hold's release arrives while the region
    is already in 'timed-out' - the timeout path handled the press - and an
    unspent marker then re-entered hold-fired from idle as a phantom hold,
    eating every press that landed during the ~12s walk (caught live by
    tools/gesture-sweep's burst scenario, 5 Aug 16:59: five taps, zero
    switchers)."""
    if region != 'gesture':
        return False
    return (to in ('hold-fired', 'handoff-pending')
            or (frm in ('hold-fired', 'handoff-pending', 'timed-out',
                        'long-hold-fired') and to == 'idle'))


class Machine:
    """Regions + the one chokepoint every transition passes through (C15)."""

    def __init__(self, on_transition=None):
        self.regions = {r: UNKNOWN for r in REGIONS}
        self.since = {r: 0.0 for r in REGIONS}
        self.games = {}
        self._game_since = {}
        self._misses = {}
        # Flag/pid drift clocks (Observed.suspended_running_since /
        # frozen_noflag_since; see FLAG_DRIFT_PERSIST_S).
        self.drift_since = {'suspended_running': None, 'frozen_noflag': None}
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
        self._track_drift(o)
        self._step_games(o)
        return self.regions

    def _track_drift(self, o):
        """First-sighting clocks for the two flag/pid disagreements the drift
        repairs act on. The conditions mirror reconcile()'s repair guards
        exactly - a clock that ran on a different predicate would debounce a
        different repair than the one it gates (FLAG_DRIFT_PERSIST_S)."""
        held = {
            # the refreeze / stale-while-playing family
            'suspended_running': bool(
                o.suspended_present and o.pids_known and o.running_pids
                and o.suspended != 'bigpicture'),
            # the lost-thaw family (guard invariant 4 + the reconcile repair)
            'frozen_noflag': bool(
                o.flags_known and o.suspended is None and o.pids_known
                and o.all_frozen),
        }
        for name, is_held in held.items():
            if not is_held:
                self.drift_since[name] = None
            elif self.drift_since[name] is None:
                self.drift_since[name] = o.mono

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
                      and not curtain_on_top(o)
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


def drift_persisted(o, since):
    """Has this flag/pid disagreement outlived a resume's critical section?

    game-launch clears the suspended flag BEFORE its SIGCONTs (6 Aug 2026),
    so a sub-second disagreement in either direction is a transition in
    flight, not drift - and the OLD ordering's version of that transient is
    what this model decided refreeze-lost-suspend on, three times, on the
    acceptance night. `since` is Machine._track_drift's first sighting; None
    means no tracking (a hand-built Observed), which reads as "held forever"
    so the repairs behave exactly as they did before the debounce."""
    return since is None or (o.mono - since) >= FLAG_DRIFT_PERSIST_S


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


def steam_menu_holding_pad(o):
    """Is Steam's menu OBSERVED open, holding the pad behind whatever is on
    screen? The routing channel, which is the signal legacy's guard checks.

    This gate exists because the guide press is a TOGGLE (see TOGGLE_VERBS):
    sent at a menu that is already closed it OPENS one, over the Kodi the
    gesture just gave the room back. The Evening-1 replay found couchd
    emitting close_steam_menu on all 21 hold-releases against legacy's 11
    conditional ones, so post-flip ~10 handoffs in 21 would have opened the
    Steam menu on the way out of a game. A cooldown cannot save this: it stops
    a SECOND press, and the damage here is done by the first.

    `steam_known` is part of the predicate, not a caller's problem: an unread
    routing log means the menu state is UNKNOWN, and a toggle fired blind is
    exactly the coin-flip this gate removes.

    The freshness bound: a ClientUI route read from a Steam that has since
    exited and restarted is not evidence of an open menu, and the guide
    press it would justify is a toggle that OPENS one on the fresh Steam
    (adversarial review, 5 Aug). Ten minutes is generous for a real menu;
    past it the at-handoff close is skipped and the guard window - which
    re-reads the routing log itself - is the enforcement, as it always was.
    """
    fresh = (o.steam_route_at is not None
             and (o.mono - o.steam_route_at) < 600.0)
    return bool(o.steam_known and o.steam_menu_open and fresh
                and 'steamwebhelper' not in (o.focused_class or ''))


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


def _iconify_intent(appid, reason, cooldown=3.0):
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

    `cooldown` is the CALLER'S, deliberately: this intent is never a decision
    on its own, it is the second half of a freeze or a handoff, and a half
    that re-fires on a different cadence from its other half is no longer one
    decision. The Evening-1 replay caught the original 5s against the refreeze
    repair's 30s: 48 iconifies for 9 freezes over one episode (T4-3).
    """
    return Intent('iconify', appid,
                  {'via': 'wm-change-state', 'reason': 'release-pointer-grab',
                   'after': 'snapshot'},
                  reason, _pred('the frozen game window is unmapped', 8.0),
                  requires=('gesture', 'session'), cooldown=cooldown)


def _deiconify_intent(o, appid, reason, cooldown=3.0):
    """The exact undo of _iconify_intent (R7(c)).

    Emitted on the resume and after any repair that thaws a game itself: a
    thawed game left iconified is audible, holds the pad, and shows the room
    nothing that explains either. On a window that was never iconified this is
    just a raise, which is why it is safe to emit unconditionally on the path.
    """
    return Intent('show', appid, {'via': 'activate', 'reason': 'deiconify'},
                  reason, _pred('the game window is mapped again', 8.0),
                  requires=('gesture', 'session') if reason.startswith('gesture:')
                  else ('session',), cooldown=cooldown)


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
    elif o.session_present and (o.session_mode == 'bigpicture'
                                or o.regions.get('foreground') == 'bigpicture'):
        # R7(a) done RIGHT: record the suspend even though there is nothing to
        # freeze, so the joystick repair below can never decide the pad belongs
        # to an invisible Big Picture. Gated on a SESSION existing, same as
        # _switcher_intents always was: legacy's freeze_game() reads the mode
        # from the session file, so with no session it writes nothing.
        out.append(Intent(
            'set_flag', 'suspended', {'value': 'bigpicture', 'pids': []},
            reason + '-bigpicture', _pred('/tmp/game-suspended exists', 2.0),
            requires=('gesture', 'session'), cooldown=3.0))
    elif o.regions.get('foreground') == 'bigpicture':
        # Steam's shell on top with NO session - it raised itself off the raw
        # PS presses, or stayed up after a session ended. Nothing to suspend
        # and NO flag to write: stamping "bigpicture" here with no session is
        # what armed every later PS tap into "resume big picture" and threw
        # the operator back onto the screen he was escaping (7 Aug 2026, the
        # stuck-on-BP report). The way out is the handoff alone.
        pass
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
    ]
    # ...and the menu, ONLY if Steam actually has one open (see
    # steam_menu_holding_pad). Legacy does not press the guide button here
    # either: handoff_to_kodi() spawns steam-input-guard, whose invariant 1
    # checks the routing log first. The menu that Steam opens a beat LATER,
    # off the same physical press, is caught by the guard window the
    # spawn_guard intent below opens - the REAL steam-input-guard, because
    # couchd's own enforcement model carries `guard:` reasons it does not
    # own and legacy's watcher yields the whole gesture including its guard
    # spawn (adversarial review, 5 Aug: with neither side spawning it, a
    # late Steam menu captured the pad with nothing to close it, ever).
    if steam_menu_holding_pad(o):
        # TOGGLE: cooldown outlasts the deadline (see TOGGLE_VERBS) - a
        # second guide press inside the first one's window REOPENS the menu.
        out.append(Intent('close_steam_menu', 'steam',
                          {'via': 'vpad-guide', 'window_s': GUARD_WINDOW,
                           'route': (o.steam_route or '')[-60:]}, reason,
                          _pred('steam menu not routed', 6.0),
                          requires=('gesture',), cooldown=GUIDE_TOGGLE_COOLDOWN))
    frozen = bool(o.pids_known and o.frozen_pids)
    if appid and appid != 'bigpicture' and (o.suspended_present or frozen) \
            and (o.suspended or appid) != 'bigpicture':
        # ...on the same cadence as the route/show it travels with: one
        # decision, one cooldown (T4-3).
        out.append(_iconify_intent(appid, reason, cooldown=3.0))
    # The guard window, exactly where legacy's handoff_to_kodi() spawns it
    # (its last line, unconditionally). While `guard` is not flipped, the
    # real steam-input-guard is the ONLY enforcement actor there is - see
    # the comment above - so an acted handoff must open one just as the
    # yielded watcher would have. The guard reads owns.conf itself: the day
    # `guard` flips, the spawned process records-and-exits and couchd's own
    # enforcement intents start acting, with no change here.
    out.append(Intent('spawn_guard', 'kodi',
                      {'via': 'steam-input-guard kodi',
                       'window_s': GUARD_WINDOW}, reason,
                      _pred('guard window open (pidfile live)', 2.0),
                      requires=('gesture',), cooldown=3.0))
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
        # ...and a guard window, for the same reason the handoff above opens
        # one. A bare restack is a single push: whatever held the screen can
        # take it straight back, and Steam's window is documented in this repo
        # as doing exactly that. Donnie reported the switcher "going to Kodi
        # for a second then back", and the shadow log shows the shape of it -
        # five double-taps in 22 seconds at 14:22, every one of them
        # suspended_first:false, every one a lone `show kodi` with nothing
        # holding it there.
        #
        # The suspend path never had this problem because _handoff_intents
        # ends in a guard. This is that same last line, on the branch that was
        # missing it - not a new mechanism, just the asymmetry closed.
        out.append(Intent('spawn_guard', 'kodi',
                          {'via': 'steam-input-guard kodi',
                           'window_s': GUARD_WINDOW}, switcher_reason,
                          _pred('guard window open (pidfile live)', 2.0),
                          requires=('gesture',), cooldown=3.0))
    out.append(Intent('show_switcher', 'tv',
                      {'via': 'kodi-addon:script.couch.switcher',
                       'suspended_first': handed},
                      switcher_reason,
                      # 3s is the right deadline and always was: the addon
                      # starts, asks the couch server for the window list and
                      # draws in a measured 1.3-1.5s. What was wrong was the
                      # LOOKING - the only observer that can see this dialog
                      # reads every 10s, so the verdict was decided by the
                      # sampler. KODI_OBSERVED_EFFECTS now keeps a targeted
                      # read coming while this prediction is outstanding, so
                      # the deadline is judged against the world.
                      _pred('Kodi select dialog open', 3.0),
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
    if action == 'home':
        # In a game this IS the suspend escape; on the home screen it is just
        # a window activation. Mirrors act()'s SESSION check via the model's
        # session_present.
        if o.session_present:
            return _suspend_intents(o, appid, running, reason, defer_handoff)
        return [Intent('show', 'home',
                       {'via': 'kodi-jsonrpc:GUI.ActivateWindow home'},
                       reason, _pred('currentwindow == 10000', 3.0),
                       requires=('gesture',), cooldown=3.0)]
    if action == 'context_menu':
        # PS5 hold: Steam's menu over a running game, power menu otherwise.
        if o.session_present:
            return [Intent('show', 'steam-menu', {'via': 'vpad-guide'},
                           reason, _pred('steam menu routed', 3.0),
                           requires=('gesture',),
                           cooldown=MENU_TOGGLE_COOLDOWN)]
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
        # NO SESSION, NO HANDOFF - matching pad-home-watcher.hold_ready(), which
        # returns os.path.exists(SESSION) for suspend_to_kodi and therefore
        # never spends the hold at all when nothing is running. couchd used to
        # emit the whole handoff regardless; on a Kodi screen that is
        # idempotent, but from the DESKTOP it would raise Kodi where the old
        # stack did nothing, which is a behaviour change nobody declared.
        #
        # RULED, 7 Aug 2026, for ONE screen: Donnie, stuck on a session-less
        # Big Picture ("holding the ps button doesn't work when it sticks me
        # on steam bp"), holds PS to get the room back. So: foreground ==
        # bigpicture hands off even with no session, under its own reason
        # (-bp-return) so the differ can pre-declare the one-sided rows
        # (legacy's hold_ready never even spends this hold). The DESKTOP case
        # is still unruled and stays a no-op decision (see the note in
        # tools/shadow-diff's triage docstring).
        bp_stuck = o.regions.get('foreground') == 'bigpicture'
        if o.binding('hold') == 'suspend_to_kodi' \
                and (o.session_present or bp_stuck):
            if not o.session_present:
                reason += '-bp-return'
            out += _handoff_intents(o, appid, reason)
        # ...and whatever the release itself is bound to, on top. 'none' by
        # default, so this line changes nothing until someone binds it.
        out += action_intents(o, 'hold_release', appid, running)

    if g == 'long-hold-fired':
        out += action_intents(o, 'long_hold', appid, running)

    if g == 'double-tap':
        out += action_intents(o, 'double_tap', appid, running)

    if (g in ('tap-wait', 'tap-fired')
            and gesture.is_tap(o.press_duration, o.hold_seconds)
            and (g == 'tap-fired' or o.binding('double_tap') == 'none')):
        # A tap that did nothing else. With the double-tap unbound it fires at
        # once; with both bound it fires only when the window shuts with no
        # second press - the same deferral the watcher runs (Donnie accepted
        # the latency, 8 Aug 2026), mirrored level-based here: while the
        # window is open this guard is false, once it shuts the intent emits
        # and its cooldown dedupes the repeat passes. The tap that RESUMES a
        # paused game is not this: it is state logic, in 'tap-resume' below.
        #
        # The is_tap() re-check is not redundant. With `hold` bound to Nothing
        # a long press never leaves 'down' for 'hold-fired', so it releases
        # into 'tap-wait' like a tap does; the watcher measures the duration
        # before it dispatches and this has to as well, or a five-second press
        # would fire the tap action on one side of the diff only.
        out += action_intents(o, 'tap', appid, running)

    if g == 'tap-resume':
        # The bigpicture pseudo-app predicts a WINDOW, not pids: a Big
        # Picture suspend froze nothing, so 'game pids back in state S' is a
        # prediction the world can never satisfy and the oracle verdicted an
        # honest resume MISSED (acceptance night, 03:48). Same verb, same
        # decision, same deadline - only the observable effect differs.
        out.append(Intent('launch', appid,
                          {'mode': 'resume', 'via': 'game-launch resume',
                           'suspended_flag': o.suspended},
                          'gesture:tap-resume',
                          _pred('big picture window on top'
                                if str(appid) == 'bigpicture'
                                else 'game pids back in state S', 5.0),
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
        if steam_menu_holding_pad(o):
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
        # ...unless the thing on top is the transition curtain: it is COVERING
        # the shuffle this very guard window belongs to, and restacking Kodi
        # against a self-raising overlay is a fight nobody wins. Expected
        # during a transition window, not drift (deploy item 1, 6 Aug 2026).
        if enf == 'kodi' and o.x_known and o.top_name != 'Kodi' \
                and not curtain_on_top(o):
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
        # ...and only once the frozen-without-flag world has OUTLIVED a
        # resume's flag-first critical section (drift_persisted): a thaw
        # fired into that sub-second merely duplicates the resume's own
        # SIGCONTs, but it is still a decision the differ has to explain.
        if not o.suspended_present and o.all_frozen and o.pids_known \
                and drift_persisted(o, o.frozen_noflag_since):
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

        # The lost-thaw net waits out a resume's flag-first critical section
        # (drift_persisted): frozen-without-flag for under a second IS the
        # resume, whose own SIGCONTs are milliseconds away. Real lost thaws
        # persist and are repaired 2s in - an order of magnitude inside this
        # net's legacy 10s cadence.
        if not o.suspended_present and o.all_frozen and o.pids_known \
                and drift_persisted(o, o.frozen_noflag_since):
            out.append(Intent('thaw', appid,
                              {'pids': o.frozen_pids, 'resolver': PID_RESOLVER,
                               'signal': 'SIGCONT'},
                              'reconcile:frozen-without-suspended-flag',
                              _pred('game pids back in state S', 3.0),
                              requires=('session',)))
            # ...and the suspend that lost its flag may well have iconified it
            # (R7(c)): a thawed game left invisible is audible, holds the pad,
            # and shows the room nothing that explains either.
            # REPAIR_COOLDOWN, matching the thaw it belongs to: the pair is
            # one repair and re-fires as one (T4-3).
            out.append(_deiconify_intent(o, appid,
                                         'reconcile:thawed-without-flag',
                                         cooldown=REPAIR_COOLDOWN))

        # R7(d): a paused flag with the game still RUNNING. Nothing repaired
        # this until 5 Aug, which is why the 4 Aug guard-vs-freeze race stuck:
        # flag set, game audible behind Kodi, nothing converging. WHAT IS ON
        # SCREEN decides which way to converge - the flag is only wrong if the
        # player can actually see and drive the game.
        # ...but never from UNDER the curtain: flag-set-with-pids-running is
        # exactly what the middle of a curtained suspend (freeze in flight)
        # looks like, and WHAT IS ON SCREEN - the tie-breaker this repair
        # runs on - is unreadable while the overlay covers it. A transition
        # in progress is not drift; the repair resumes the pass after the
        # curtain drops. And never before the disagreement has OUTLIVED a
        # transition's critical section (drift_persisted): the resume paths
        # now clear the flag before their SIGCONTs, so this pair can only be
        # observed through a single pass's read straddle - the acceptance
        # night's 3x shadow refreeze was precisely this repair firing inside
        # the old ordering's gap, and acted it would have SIGSTOPped the
        # game mid-resume. Real 4 Aug-style stuck states persist for minutes
        # and are repaired 2s in.
        if (o.suspended_present and o.pids_known and o.running_pids
                and o.suspended != 'bigpicture'
                and not curtain_on_top(o)
                and drift_persisted(o, o.suspended_running_since)):
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
                # Same cadence as its freeze: the Evening-1 replay caught this
                # pair firing 9 freezes against 48 iconifies (T4-3).
                out.append(_iconify_intent(appid,
                                           'reconcile:refreeze-lost-suspend',
                                           cooldown=REPAIR_COOLDOWN))

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
# DISABLED 7 Aug 2026 after a live incident: a synthetic guide press drives
# Steam Big Picture's OWN menu, and a run of them (this verb fired once, the
# legacy guard three more inside 5s) reached Steam's power options and
# SUSPENDED THE MACHINE mid-game at 01:55:13 - Steam called logind, the TV
# lost signal, Donnie had to hit the power button. The mechanism has also
# never confirmed: every close_steam_menu effect check has verdicted MISSED.
# The verb still exists (removing it would be a vocabulary change and the
# differ compares it), but its body is inert unless the file switch exists.
# Redesign before re-enabling: a press that cannot reach a power menu, gated
# on evidence the menu is really open, owned by exactly ONE stack.
GUIDE_PRESS_ENABLED_FLAG = os.path.expanduser(
    '~/couch/data/steam-guide-press-enabled')
GUIDE_PRESS_SH = (
    f'if [ ! -e "{GUIDE_PRESS_ENABLED_FLAG}" ]; then '
    f'echo "guide press SKIPPED (disabled 7 Aug; see GUIDE_PRESS_SH)"; '
    f'exit 0; fi; '
    f'if [ ! -e /tmp/vpad.fifo ]; then "{VPAD}" up >/dev/null 2>&1; '
    f'started=1; sleep 1.5; fi; "{VPAD}" press guide >/dev/null 2>&1; '
    f'sleep 1; [ -n "${{started:-}}" ] && "{VPAD}" quit >/dev/null 2>&1; true')

# The frozen game's window, unmapped so its stuck pointer grab dies with it
# (pad-home-watcher.iconify_frozen_game, same two xinput.py calls).
# The wait loop at the front is legacy's _SNAP_DONE.wait(4.0), cross-process:
# iconifying frees the compositing pixmap pause-snap reads, so the unmap must
# not beat the capture or the pause tile goes black (the two are independent
# transient units here, with no in-process event to share). A jpg younger
# than 15s in the paused dir is the capture landing; 4s with none and we
# proceed anyway, exactly as the watcher does - the snap is cosmetic and the
# unmap must not be hostage to it.
PAUSED_DIR = os.path.expanduser('~/couch/data/paused')
ICONIFY_SH = (
    f'for i in $(seq 1 40); do '
    f'[ -n "$(find "{PAUSED_DIR}" -maxdepth 1 -name "*.jpg" '
    f'-newermt "-15 seconds" 2>/dev/null | head -1)" ] && break; '
    f'sleep 0.1; done; '
    f'pids=$("{GAME_PIDS}" 2>/dev/null | tr "\\n" " "); [ -n "$pids" ] || exit 0; '
    f'wid=$(timeout 5 python3 "{XINPUT}" gamewin $pids 2>/dev/null); '
    f'case "$wid" in 0x*) timeout 5 python3 "{XINPUT}" iconify "$wid" ;; esac')


def snap_captures(directory):
    """Observed.snaps: appid -> wall-clock time (s) of the newest freeze-frame
    in pause-snap's paused dir. Read-only, and cheap by construction: the dir
    is bounded at two small jpgs per paused game and in practice one game is
    paused at a time. The capture time comes from the FILENAME
    (<appid>__<epoch_ms>.jpg - pause-snap mints a fresh name per capture so
    Kodi's texture cache cannot serve the previous pause), never from mtime,
    so a copied or touched file cannot lie about when it was captured.
    `directory` is explicit - the daemon passes PAUSED_DIR, tests pass
    tmp_path - because a default bound to the live path is how a unit test
    ends up reading the console's real paused dir."""
    out = {}
    try:
        names = os.listdir(directory)
    except OSError:
        return out                  # no dir yet = nothing captured
    for name in names:
        if not name.endswith('.jpg'):
            continue
        stem = name[:-4]
        if stem.endswith('.tile'):  # the poster crop of the same capture
            stem = stem[:-5]
        appid, sep, ms = stem.rpartition('__')
        if not sep or not appid or not ms.isdigit():
            continue
        ts = int(ms) / 1000.0
        if ts > out.get(appid, 0.0):
            out[appid] = ts
    return out


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
    def signal(self, pids, signum, verify=None):
        """Signal a pid set. `verify(pid) -> reason-or-None` is checked
        IMMEDIATELY before each kill and a refusal is a skip, never a failure:
        a pid that has already exited is the world agreeing with us early, and
        a pid that is no longer who we think it is must not be signalled at
        all (see verify_guard_pid)."""
        sent, missing, refused = [], [], []
        for pid in pids:
            if verify is not None:
                why = verify(pid)
                if why:
                    refused.append({'pid': pid, 'why': why})
                    continue
            try:
                os.kill(int(pid), signum)
                sent.append(int(pid))
            except (OSError, ValueError):
                missing.append(pid)
        out = {'sent': sent, 'missing': missing, 'signal': int(signum)}
        if refused:
            out['refused'] = refused
        if pids and not sent:
            if refused:
                # Nothing was signalled and nothing went wrong: every target
                # failed its pre-signal check.
                out['skipped'] = '; '.join(r['why'] for r in refused)[:200]
                return out
            raise ActionFailed(f'no pid of {sorted(pids)} could be signalled')
        return out

    #: what a guard process's command line must contain to be one
    GUARD_NAME = 'steam-input-guard'

    def verify_guard_pid(self, pid, pidfile=None, name=None):
        """Three checks, at EXECUTION time, before a SIGTERM leaves this
        process. Returns the reason to refuse, or None to go ahead.

        The 5 Aug replay found couchd naming guard pid 1673365 when the
        pidfile had held 1673613 for 412ms - and during that stretch the guard
        respawned five times in twenty seconds. A pid that has exited on a box
        cycling processes that fast is a pid the kernel may already have handed
        to somebody else, and `os.kill` does not ask who it is talking to.

        (a) the pidfile still names this pid - re-read NOW, not the flag
            observation the pass began with;
        (b) the process exists;
        (c) it is actually a guard, by command line - the check that makes pid
            reuse survivable rather than merely unlikely.
        """
        pidfile = pidfile or GUARD_PIDFILE
        name = name or self.GUARD_NAME
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return f'{pid!r} is not a pid'
        if pid == os.getpid():
            return 'that pid is couchd itself'
        try:
            current = open(pidfile).read().strip()
        except OSError:
            return f'{pidfile} is gone - the window closed itself'
        if current != str(pid):
            return (f'{pidfile} now names {current or "nothing"}, not {pid} '
                    f'- the guard was replaced between decision and action')
        try:
            import psutil
            cmd = ' '.join(psutil.Process(pid).cmdline() or [])
        except Exception as e:      # NoSuchProcess, AccessDenied, no psutil
            return f'pid {pid} is gone or unreadable ({type(e).__name__})'
        if name not in cmd:
            return (f'pid {pid} is not {name} ({cmd[:60]!r}) - refusing to '
                    f'signal a recycled pid')
        return None

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
    """Every pid the intent named is OBSERVABLY in state T. A pid that has
    VANISHED does not count as frozen: defaulting missing pids to 'T' let a
    game that quit at the instant of the hold verdict 'confirmed' for a
    freeze that froze nothing - a lie in the exact corpus acceptance is
    judged from (adversarial review, 5 Aug). An honest 'missed' when the
    game exited is the correct record; the level-based re-decision already
    copes with the world having moved."""
    pids = it.args.get('pids', ())
    return (o.pids_known and bool(pids)
            and all(o.pid_states.get(p) == 'T' for p in pids))


def _eff_thaw(o, it):
    return o.pids_known and all(o.pid_states.get(p, 'S') != 'T'
                                for p in it.args.get('pids', ()))


def _eff_launch(o, it):
    """Only the resume has an oracle in stage 1: the game's pids are back
    and none of them is frozen - exactly the thaw's world-shape, read from
    the live tree because a resume's intent carries no pid list. Other
    launch subjects return None (no honest oracle -> 'unverified'), which
    beats the old state of affairs where NO launch was ever judged and a
    systematically failing resume looked healthy (adversarial review).

    EXCEPT the bigpicture pseudo-app, which has no game pids to come back:
    a pid oracle on it waits 5s at a world that already looks 'wrong' and
    verdicts an honest resume MISSED ('game pids back in state S', 03:48 on
    the acceptance night). Big Picture's resume is a WINDOW effect - its
    shell surfaces over Kodi - so the check is the same top-window shape
    g_fg_bigpicture classifies from."""
    if it.args.get('mode') != 'resume':
        return None
    if str(it.subject) == 'bigpicture':
        return bool(o.x_known and 'Big Picture' in (o.top_name or ''))
    return bool(o.pids_known and o.pid_states and not o.frozen_pids)


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


def _eff_show_switcher(o, it):
    """The switcher addon draws a Kodi dialog, so the dialog being the
    current window IS the effect. Without this the verdict was 'unverified'
    for want of a check at all - the prediction said "Kodi select dialog open"
    and nothing ever looked.

    Two window shapes are the effect: the stock select dialog (12000), and
    the addon's animated WindowXMLDialog, which Kodi allocates out of the
    python-window pool (13000-13099) with no way to pin it. Both count -
    the addon's ui.animated_dialog setting flips between them at runtime,
    and the check must not decide which one the user prefers."""
    return o.kodi_known and (o.kodi_window == KODI_SELECT_DIALOG
                             or (o.kodi_window is not None
                                 and 13000 <= o.kodi_window <= 13099))


def _eff_spawn_guard(o, it):
    """A guard window is open: the pidfile names a live guard that is not
    couchd's own scavengeable leftover. The pidfile lands within ~100ms of
    the spawn and the flag observer sees it by inotify, so the 2s deadline
    is generous."""
    return bool(o.guard_pid) and not o.guard_pid_ours


# How recent a freeze-frame has to be to count as THIS suspend's capture.
# Staleness is nearly impossible by construction - both stacks clear the
# paused dir on resume (clear_snapshots / pause-snap --clear), and a game
# cannot be suspended twice without a resume between - so the bound is belt
# and braces against a clear that failed, sized to dwarf the 5s prediction
# window plus pause-snap's own capture time.
SNAP_FRESH_S = 30.0
# ...and the sharper anchor: the capture must postdate the snapshot ORDER.
# The relative bound alone falsely confirms a double fault (adversarial
# review, 6 Aug): suspend A captures at T; a resume at T+10 whose
# clear_snapshots fails; suspend B at T+15 whose pause-snap also fails -
# B's oracle would confirm off A's 15s-old jpg. The pending record carries
# the wall clock of the moment couchd acted (p['t0']), and a capture older
# than that is somebody else's, however fresh. The epsilon absorbs skew
# between couchd's clock and the filename stamp pause-snap mints (same
# host, but the capture pipeline reads its clock a beat after ours).
SNAP_ORDER_SKEW_S = 2.0


def _eff_snapshot(o, it, ordered_at=None):
    """A freeze-frame jpg for the appid exists, postdates THIS order, and is
    fresh.

    This was the 5/5-unverified oracle of the acceptance night: the
    prediction said 'a freeze-frame jpg for the appid' and nothing ever
    looked - snapshot had no entry in EFFECT_CHECKS, so every live suspend
    ran out its 5s deadline and verdicted 'unverified' (latencies 5-17s
    depending on pass cadence) while the jpg sat on disk. The daemon now
    reads the paused dir each pass (Observed.snaps, filename convention
    <appid>__<epoch_ms>.jpg); a capture is the effect when its embedded
    wall-clock time is at or after the order (minus SNAP_ORDER_SKEW_S) and
    within SNAP_FRESH_S. All three timestamps are wall clock - o.now, the
    filename's epoch-ms, and ordered_at - so no mono/wall mixing.

    `ordered_at=None` (a caller outside check_pending, e.g. a bare oracle
    test) degrades to the freshness bound alone."""
    ts = (o.snaps or {}).get(str(it.subject or ''))
    if ts is None:
        return False
    if ordered_at is not None and ts < ordered_at - SNAP_ORDER_SKEW_S:
        return False                # a LEFTOVER capture, not this order's
    return (o.now - ts) <= SNAP_FRESH_S


# The C17 checker hands this oracle the pending record's order time as a
# third argument (see check_pending). An explicit marker, not arity
# sniffing: a new anchored oracle opts in by setting the same attribute.
_eff_snapshot.wants_order_time = True


def _eff_iconify(o, it):
    """The frozen game's window has LEFT the screen's stacking order.

    The other 5/5-unverified oracle: no check was registered, so 'the frozen
    game window is unmapped' timed out ~8s on every live suspend even though
    the unmap worked every time. What the X11 observer actually sees when
    iconify succeeds on this box: the window stops being mapped, so it
    leaves the scan entirely - the top window stops being a steam_app and
    the game's WM_CLASS drops out of Observed.game_windows (the mapped
    steam_app list). Both legs matter: Kodi is raised over the game in the
    same handoff, so 'top is not the game' alone would confirm an iconify
    that silently failed - the game_windows leg is what tells covered from
    unmapped. Non-Steam sessions (shadPS4) have no steam_app class to look
    for, so for them the top-window leg is the whole oracle."""
    if not o.x_known:
        return False
    if (o.top_class or '').startswith('steam_app'):
        return False                # a game window still owns the screen
    appid = str(it.subject or '')
    if appid.isdigit() and f'steam_app_{appid}' in (o.game_windows or ()):
        return False                # still mapped: covered is not unmapped
    return True


EFFECT_CHECKS = {
    'freeze': _eff_freeze, 'thaw': _eff_thaw,
    'set_flag': _eff_set_flag, 'clear_flag': _eff_clear_flag,
    'route_pad': _eff_route_pad, 'show': _eff_show,
    'dismiss': _eff_dismiss, 'close_steam_menu': _eff_close_menu,
    'show_switcher': _eff_show_switcher,
    'spawn_guard': _eff_spawn_guard,
    'launch': _eff_launch,
    'snapshot': _eff_snapshot,
    'iconify': _eff_iconify,
}

# Effects that are only visible through a KODI READ. Kodi is the one observer
# with a rate limiter on it (>=10s, R6: the anti-entropy tick may never drive
# Kodi's read rate), so an effect that lands in 200ms and is looked for on a
# 10s cadence gets judged by whichever came first - which is why a switcher
# dialog that was demonstrably on screen from 13:57:04.8 verdicted
# 'unverified' at 13:57:07.9. After acting on one of these the daemon asks
# for ONE targeted read (Couchd.pass_once -> KodiObserver.request_read), so
# the check races the deadline fairly instead of losing to the limiter.
KODI_OBSERVED_EFFECTS = ('route_pad', 'dismiss', 'show_switcher')


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
        'spawn_guard': '_a_spawn_guard',
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
                 context=None, heartbeat_fresh=None):
        self.log = log
        self.act = actuators
        self.on_record = on_record or (lambda i: None)
        self.owned = frozenset(owned)
        self.say = sayer
        self.context = context or (lambda: {})
        self.heartbeat_fresh = heartbeat_fresh   # None = always fresh (tests)
        self.count = 0
        self.failures = 0
        self.pending = []          # C17 predictions awaiting their deadline
        self.fails = {}            # (verb, subject) -> {'n', 'until', 'said'}
        self.skipped = 0
        self._failed_reason = None  # (reason, pass mono, key) of the last
        #                             failed step, for dependent-skip scoping

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
        if self.heartbeat_fresh is not None and not self.heartbeat_fresh():
            # Our lease may already look dead to the other stack (a stalled
            # pass ages status.json past what legacy tolerates): acting NOW
            # risks two stacks driving one world. Decline this pass; the run
            # loop republishes the heartbeat immediately after, and the next
            # pass acts on a lease legacy can see.
            self.skipped += 1
            rec.update(acted=False,
                       action={'ok': False, 'declined': 'stale-heartbeat: '
                               'legacy may have reclaimed this lease'})
            self.log.write(rec)
            self.on_record(intent)
            self.say(f'DECLINED {intent.human()}: own heartbeat is stale - '
                     f'republishing before acting')
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
        failed = self._failed_reason
        if (failed and intent.reason == failed[0] and obs.mono == failed[1]
                and key != failed[2]):
            # An earlier step of this SAME decision failed IN THIS PASS (one
            # pass = one obs.mono): the steps of one reason are a sequence,
            # not independent acts. A freeze that failed must not be followed
            # by the set_flag that asserts a pause happened, or the flag lies
            # to every reader of /tmp (adversarial review, 5 Aug). Scoped to
            # the pass and to OTHER steps: the failing step's own retries are
            # backoff's business, and the next pass re-derives the whole
            # decision from the world.
            self.skipped += 1
            rec.update(acted=False,
                       action={'ok': False, 'dependent_skipped':
                               f'an earlier {failed[0]} step failed'})
            self.log.write(rec)
            self.on_record(intent)
            self.say(f'SKIPPED {intent.human()}: earlier step of the same '
                     f'decision failed')
            return rec
        gone = self._precondition_gone(intent, obs)
        if gone:
            # C17 has always judged an action AFTER the fact. This is the same
            # idea before it: the world the decision was taken on has moved, so
            # the action is not wanted any more. Not a failure - nothing went
            # wrong - and the cooldown still applies, because the decision was
            # made and re-deciding it next pass is the level-based answer.
            self.skipped += 1
            rec.update(acted=False,
                       action={'ok': True, 'precondition_gone': gone})
            self.log.write(rec)
            self.on_record(intent)
            self.say(f'SKIPPED {intent.human()}: {gone}')
            return rec
        method = self.ACTIONS.get(intent.verb)
        try:
            if method is None:
                raise ActionFailed(f'no action for verb {intent.verb}')
            res = getattr(self, method)(intent, obs) or {}
            rec['action'] = {'ok': True, **res}
            if res.get('skipped'):
                # The actuator itself declined at the last instant (a pid that
                # failed its pre-signal check). Same shape as above: recorded,
                # counted as a skip, never as a success or a failure.
                rec['acted'] = False
                self.skipped += 1
                self.say(f'SKIPPED {intent.human()}: {res["skipped"]}')
            else:
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
            self._failed_reason = (intent.reason, obs.mono, key)
        except Exception as e:                     # never take the daemon down
            self.failures += 1
            rec['acted'] = False
            rec['action'] = {'ok': False, 'error': f'{type(e).__name__}: {e}'}
            self.say(f'ACTION CRASHED {intent.human()}: {type(e).__name__}: {e}')
            self._note_failure(key, obs)
            self._failed_reason = (intent.reason, obs.mono, key)
        self.log.write(rec)
        self.on_record(intent)
        if rec['acted'] and intent.predict:
            self.pending.append({
                'intent': intent,
                'deadline': obs.mono + float(intent.predict.get('deadline_s', 5)),
                'started': obs.mono,
                't0': obs.now,     # wall clock of the ORDER, for anchored
                #                    oracles (filename stamps are wall clock)
                'check': EFFECT_CHECKS.get(intent.verb),
            })
        return rec

    # -- C17, before the fact ---------------------------------------------
    # A verb whose action is IRREVERSIBLE-IF-WRONG re-checks the predicate its
    # decision rested on, at execution time. Two of them:
    #
    #   close_steam_menu  the guide button is a toggle, so a press at a menu
    #                     that is not open OPENS one (T4-1);
    #   kill              a pid read out of a file a respawning guard rewrites
    #                     may already belong to somebody else (T4-2).
    #
    # Everything else is level-based and idempotent: pressing it again when it
    # was not needed changes nothing, so it does not earn a pre-check.
    PRECONDITIONS = {'close_steam_menu': '_pre_close_steam_menu',
                     'kill': '_pre_kill'}

    def _precondition_gone(self, intent, obs):
        method = self.PRECONDITIONS.get(intent.verb)
        if not method:
            return None
        try:
            return getattr(self, method)(intent, obs)
        except Exception as e:      # a check that cannot run is a refusal
            return f'precondition check failed ({type(e).__name__}: {e})'

    def _pre_close_steam_menu(self, it, obs):
        """Re-evaluate whatever justified this particular press."""
        if it.reason == 'guard:desktop-overlay-after-tap':
            if _desktop_overlay_open(obs):
                return None
            return ('Steam\'s desktop overlay is no longer open - a guide '
                    'press now would open it')
        if steam_menu_holding_pad(obs):
            return None
        return ('Steam\'s menu is not open (routing %r) - the guide button is '
                'a toggle, so pressing it now would OPEN the menu'
                % ((obs.steam_route or '')[-40:] if obs.steam_known
                   else 'unknown'))

    def _pre_kill(self, it, obs):
        if it.subject != Actuators.GUARD_NAME or self.act is None:
            return None
        pids = it.args.get('pids') or ()
        if not pids:
            return 'no pid to signal'
        why = [self.act.verify_guard_pid(p) for p in pids]
        if all(why):                # every target failed its check
            return '; '.join(w for w in why if w)[:200]
        return None

    # The verbs that ARE the way out of a game: the suspend's route/freeze
    # and the resume's launch/thaw. Backing one of these off for the full
    # 300s wedges the couch's only escapes while the lease sees a perfectly
    # healthy heartbeat and never hands anything back (adversarial review,
    # 5 Aug) - so their backoff is capped at BACKOFF_BASE. The failure is
    # still said loudly and still skips; it just never grows to minutes.
    ESCAPE_VERBS = ('route_pad', 'freeze', 'thaw', 'launch')

    # -- C11 backoff ------------------------------------------------------
    def _note_failure(self, key, obs):
        st = self.fails.setdefault(key, {'n': 0, 'until': 0.0, 'said': False})
        st['n'] += 1
        if st['n'] >= self.BACKOFF_AFTER:
            cap = (self.BACKOFF_BASE if key[0] in self.ESCAPE_VERBS
                   else self.BACKOFF_MAX)
            wait = min(self.BACKOFF_BASE * 2 ** (st['n'] - self.BACKOFF_AFTER),
                       cap)
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
                    if getattr(p['check'], 'wants_order_time', False):
                        # An anchored oracle: it needs to know WHEN this
                        # action was ordered, or a leftover artefact from a
                        # previous order could confirm it (_eff_snapshot's
                        # double-fault scenario). p['t0'] is the wall clock
                        # of the execute() that queued this prediction.
                        got = p['check'](o, it, p.get('t0'))
                    else:
                        got = p['check'](o, it)
            # A registered check that only ever answers None has no oracle
            # for THIS subject (e.g. _eff_show for steam-menu/desktop): at
            # the deadline that is 'unverified', not 'missed' - a standing
            # false EFFECT MISSED alarm teaches the room to ignore the real
            # ones (adversarial review, 5 Aug).
            p['sawbool'] = p.get('sawbool', False) or isinstance(got, bool)
            if got is True:
                out.append((p, 'confirmed', o.mono - p['started']))
            elif o.mono >= p['deadline']:
                verdict = ('missed' if p['check'] is not None
                           and p['sawbool'] else 'unverified')
                out.append((p, verdict, o.mono - p['started']))
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
        # The guard supersede is the only kill couchd has, and it is aimed at
        # a pid read out of a file that a respawning guard rewrites. Verified
        # per pid, immediately before the signal (T4-2).
        verify = (self.act.verify_guard_pid
                  if it.subject == self.act.GUARD_NAME else None)
        return self.act.signal(it.args.get('pids', ()), signal.SIGTERM,
                               verify=verify)

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
        if it.subject == 'home':
            self.act.raise_kodi()
            return self.act.kodi('GUI.ActivateWindow', {'window': 'home'})
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

    def _a_spawn_guard(self, it, o):
        # The real steam-input-guard, detached as its own transient unit,
        # exactly where legacy's handoff_to_kodi() spawned it. The guard
        # reads owns.conf on startup: while `guard` is unflipped it enforces
        # (which is the point - couchd's own guard: intents are unowned and
        # record-only), and the day guard flips it records-and-exits on its
        # own, so this action never needs to know.
        return self.act.spawn([GUARD_BIN, str(it.subject)])


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
                            # The declared set as well as the actable one - see
                            # the start record. `input` never appears in `now`
                            # (couchd cannot execute it) and the differ would
                            # otherwise read a flipped input evening as though
                            # it had never been flipped.
                            'now_declared': current.sorted,
                            'acting': self.acting is not None})
        return True

    def execute(self, intent, obs):
        resp = owns.responsibility_for_reason(intent.reason)
        if self.acting is not None and resp in self.owned:
            return self.acting.execute(intent, obs)
        return self.recording.execute(intent, obs)

    def check_pending(self, o):
        return self.acting.check_pending(o) if self.acting else []

    def pending_verbs(self):
        """Verbs whose predicted effect has not been judged yet - what the
        daemon uses to decide it should go and LOOK (C17)."""
        return [p['intent'].verb for p in self.acting.pending] if self.acting else []


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
        self._present = False
        # ALL the tap/hold arithmetic is gesture.py's, byte for byte the same
        # module the stage-2 input process runs (SR4).
        self.tracker = gesture.PressTracker()
        self.first_event_latency = None    # R5: pad-appearance -> first event
        self._appeared_at = None
        # The stage-2 wire (supervisor.py). BOTH default False, and while they
        # are, every line below behaves exactly as it did before the wire
        # existed: `supervised` is only ever set by SupervisorObserver, and it
        # only sets it while an authorised peer is actually connected.
        self.supervised = False
        self.supervised_present = False

    # The tracker's state IS the observer's state; these read-only views keep
    # observe()/write_status() unchanged.
    button_down = property(lambda self: self.tracker.button_down)
    down_since_k = property(lambda self: self.tracker.down_since_k)
    press_duration = property(lambda self: self.tracker.press_duration)
    press_ended_at = property(lambda self: self.tracker.press_ended_at)
    presses = property(lambda self: self.tracker.presses)
    double_armed = property(lambda self: self.tracker.double_armed)
    doubles = property(lambda self: self.tracker.doubles)
    hold_release_pending = property(
        lambda self: self.tracker.hold_release_k is not None)
    double_tap_pending = property(
        lambda self: self.tracker.double_tap_k is not None)

    @property
    def present(self):
        """Is there a pad? Whoever can actually see one answers.

        Once the stage-2 input process owns the pad it is the ONLY thing on
        the box that can see the device: it holds the node with EVIOCGRAB, and
        under the flag-day udev rule ds2000 cannot open it at all. Our own node
        scan would then find nothing and report the pad absent while somebody
        is holding it - so while the wire is live, what the wire says IS the
        answer. With no supervisor connected this is the plain attribute it has
        always been.
        """
        return self.supervised_present if self.supervised else self._present

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
        self._present = bool(self.fds)

    def _drop(self, loop, path, why):
        fd = self.fds.pop(path, None)
        if fd is not None:
            with contextlib.suppress(Exception):
                loop.remove_reader(fd)
            with contextlib.suppress(OSError):
                os.close(fd)
            self.w.log.write({'kind': 'obs', 'source': 'pad',
                              'event': 'node-close', 'node': path, 'why': why})
        self._present = bool(self.fds)
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
        if self.supervised:
            # The wire is live and is the source of truth for this pad. The
            # bytes still have to be consumed (an undrained POLLIN spins the
            # loop forever), but feeding them would double-count every press
            # against the tracker. This is belt and braces: at flag day this
            # node is grabbed by the input process and we never opened it.
            return
        for off in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
            sec, usec, etype, code, value = struct.unpack_from(EVENT_FORMAT,
                                                              data, off)
            k = sec + usec / 1e6
            self.tracker.note_event(k)
            self.src.events += 1
            if etype == EV_KEY and code == BTN_MODE:
                self.note_button(k, value)

    def note_button(self, k, value, via='evdev'):
        """ONE BTN_MODE event, from whichever channel carried it.

        Both channels land here on purpose: the tracker, the corpus record and
        the gesture edge must be identical whether the event arrived from our
        own read of the evdev node or over the supervisor wire from the process
        that grabbed it. `via` is a LABEL on the evidence and changes no
        decision - which is the point, and what makes a flipped `input` evening
        comparable with every evening before it.
        """
        if via != 'evdev':
            # The evdev path counts every event it reads, stick wiggles and
            # all; the wire only ever carries the button, so its events are
            # counted here instead.
            self.src.events += 1
        if self._appeared_at is not None:
            self.first_event_latency = time.monotonic() - self._appeared_at
            self._appeared_at = None
            self.w.log.write({'kind': 'obs', 'source': 'pad',
                              'event': 'first-event-latency',
                              'seconds': round(self.first_event_latency, 3)})
        self.tracker.feed(k, value)
        rec = {'kind': 'obs', 'source': 'pad',
               'event': 'BTN_MODE', 'value': value,
               'kernel_t': round(k, 6),
               'duration': (round(self.press_duration, 3)
                            if value == 0 and self.press_duration
                            else None),
               'double_armed': self.tracker.double_armed}
        if via != 'evdev':
            rec['via'] = via
        self.w.log.write(rec)
        # THE gesture edge: every show/route/switcher decision the
        # room can feel hangs off this event, so it runs a pass now
        # instead of waiting for the tick (R5).
        self.w.attention('ps-button', edge=True, kernel_t=k)
        self.src.last_change = time.monotonic()

    def close(self, loop):
        for path in list(self.fds):
            self._drop(loop, path, 'shutdown')


class SupervisorObserver:
    """The second source for pad events: stage 2's input process.

    A listener thread accepts the connection and validates every line; this
    object drains what the thread queued, once per pass, on the daemon's own
    single thread. No socket is ever touched from the loop.

    THE SAFETY PROPERTY, which the tests pin: with nothing connected, this
    object changes NOTHING. `drain()` finds an empty queue, leaves
    `pad.supervised` False, and every decision couchd takes is the decision it
    took before this class existed. couchd owns gestures on a live console;
    the wire is inert until something authorised is on the other end of it.
    """

    def __init__(self, world, pad, path=None, allow_users=None):
        self.w = world
        self.pad = pad
        self.listener = supervisor.SupervisorListener(
            path=path or supervisor.default_path(SHADOW_DIR),
            allow_users=(allow_users if allow_users is not None
                         else supervisor.ALLOWED_USERS),
            on_log=say)
        self.src = None             # created by start(), not by construction
        self.events = 0             # presses that came over the wire
        self.messages = 0
        self.last_event_mono = None
        self.peer_pid = None
        self.peer_user = None
        self.peer_owns_input = None
        self.peer_drops = 0         # drops the SENDER reported (SR7)
        self.peer_degraded = None
        self.started = False

    # -- lifecycle --------------------------------------------------------
    def start(self):
        """Open the listening socket. A failure is a note, never fatal."""
        self.src = self.w.src('supervisor')
        self.started = self.listener.start()
        if self.started:
            self.src.touch(True, 'listening, no supervisor connected')
        else:
            self.src.touch(False, self.listener.error or 'not listening')
            self.w.log.write({'kind': 'observer_blind', 'source': 'supervisor',
                              'why': 'listen-failed',
                              'detail': self.listener.error})
        return self.started

    def close(self):
        self.listener.close()
        self.started = False
        # Hand the pad region back to our own eyes: a stopped daemon must not
        # leave the observer believing a wire that is gone.
        self.pad.supervised = False

    @property
    def connected(self):
        return self.listener.connected

    # -- per-pass ---------------------------------------------------------
    def drain(self):
        """Apply everything the wire delivered since the last pass."""
        for msg in self.listener.get_all():
            self.messages += 1
            self._apply(msg)
        # Set the pad observer's mode LAST, from the live connection state, so
        # a connect and its first messages take effect in the same pass.
        self.pad.supervised = self.connected
        if not self.connected:
            self.pad.supervised_present = False
        if self.src is not None and self.started:
            self.src.touch(True, ('peer pid %s (%s)' % (self.peer_pid,
                                                        self.peer_user)
                                  if self.connected
                                  else 'listening, no supervisor connected'))

    def _apply(self, msg):
        kind = msg.get('kind')
        if kind == 'press':
            self.events += 1
            self.last_event_mono = time.monotonic()
            # OBSERVATION, not decision: the raw event and its kernel
            # timestamp go straight into the same tracker the evdev path
            # feeds, and couchd's own state machine classifies it (SR4).
            self.pad.note_button(msg['kernel_t'], msg['value'], via='supervisor')
        elif kind == 'pad':
            attached = msg['state'] == 'attached'
            if attached != self.pad.supervised_present:
                self.w.log.write({'kind': 'obs', 'source': 'pad',
                                  'event': ('node-open' if attached
                                            else 'node-close'),
                                  'node': msg.get('node'),
                                  'why': msg.get('why'), 'via': 'supervisor'})
                self.w.attention('pad-appeared' if attached else 'pad-gone',
                                 edge=not attached)
            self.pad.supervised_present = attached
            if not attached:
                # Same contract as _drop(): a pad that went away takes its
                # in-flight press with it, or a level-based reader walks the
                # tap paths off a press that no longer exists.
                self.pad.tracker.reset()
        elif kind == 'hello':
            self.peer_pid = msg['pid']
            self.peer_owns_input = msg.get('owns_input')
            self.w.log.write({'kind': 'obs', 'source': 'supervisor',
                              'event': 'hello', 'pid': msg['pid'],
                              'version': msg.get('version'),
                              'owns_input': msg.get('owns_input'),
                              'sender': msg.get('sender')})
        elif kind == 'health':
            self.peer_drops = msg.get('drops', 0)
            self.peer_degraded = msg.get('degraded')
            self.w.log.write({'kind': 'obs', 'source': 'supervisor',
                              'event': 'peer-health', 'drops': msg.get('drops'),
                              'owns_input': msg.get('owns_input'),
                              'degraded': msg.get('degraded'),
                              'state': msg.get('state')})
        elif kind == '_connected':
            self.peer_pid, self.peer_user = msg.get('pid'), msg.get('user')
            self.w.log.write({'kind': 'obs', 'source': 'supervisor',
                              'event': 'connected', 'pid': msg.get('pid'),
                              'user': msg.get('user')})
        elif kind == '_disconnected':
            self.peer_pid = self.peer_user = None
            self.peer_owns_input = None
            self.pad.supervised_present = False
            # The wire went away mid-press: forget it, exactly as a dropped
            # evdev node does.
            self.pad.tracker.reset()
            self.w.log.write({'kind': 'obs', 'source': 'supervisor',
                              'event': 'disconnected', 'pid': msg.get('pid'),
                              'why': msg.get('why')})
            self.w.attention('supervisor-gone', edge=True)

    def status(self, mono=None):
        """What status.json says about the wire, so the health check can see
        it without opening a socket."""
        mono = time.monotonic() if mono is None else mono
        li = self.listener
        return {'listening': li.listening, 'path': li.path,
                'connected': self.connected,
                'peer_pid': self.peer_pid, 'peer_user': self.peer_user,
                'peer_owns_input': self.peer_owns_input,
                'connections': li.connections, 'rejected': li.rejected,
                'malformed': li.malformed,
                'events': self.events, 'messages': self.messages,
                # Two drop counters, and they mean different things: `drops`
                # is our own inbound queue overflowing (couchd fell behind),
                # `peer_drops` is what the input process threw away because
                # nobody was listening or the wire was slow (SR7).
                'drops': li.dropped, 'peer_drops': self.peer_drops,
                'peer_degraded': self.peer_degraded,
                'last_event_age_s': (round(mono - self.last_event_mono, 3)
                                     if self.last_event_mono is not None
                                     else None),
                'error': li.error}


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
        self._forced = None        # a targeted read asked for by name
        self._last_forced = 0.0
        self.forced_reads = 0
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

    def request_read(self, why):
        """Ask for ONE targeted read on the next pass, ahead of the limiter.

        C17 judges an action by watching the world get there. For the effects
        only Kodi can show us that is a race between a 200ms effect and a 10s
        sampling interval, and the interval wins - which is not evidence about
        the model, it is evidence about the sampler. So couchd asks for a
        single read when it has just done something Kodi can confirm, and
        wakes the loop so the next pass carries it. Rate-limited in its own
        right (KODI_EFFECT_READ_FLOOR): a burst of actions is still one read.
        """
        if time.monotonic() - self._last_forced < KODI_EFFECT_READ_FLOOR:
            return False
        self._forced = why
        self.w.attention(f'kodi-effect:{why}')
        return True

    async def poll(self):
        """Never faster than KODI_READ_INTERVAL, whatever the tick does - with
        the one exception request_read() exists for."""
        now = time.monotonic()
        forced, self._forced = self._forced, None
        if forced is None and now - self.last_read < KODI_READ_INTERVAL:
            return
        if forced is not None:
            self._last_forced = now
            self.forced_reads += 1
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
                              'playing': playing, 'targeted': forced})
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
        self.route_at = None      # mono when that route line was READ
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
                pids = self.ledger.get(m.group(1))
                if pids is not None:
                    pids.discard(int(m.group(2)))
                    if not pids:
                        # A DROP that empties the set without its REMOVE ever
                        # arriving used to leave a phantom appid: game:X
                        # LAUNCHING/STOPPED churn, and a permanently-truthy
                        # ledger kept PidObserver on its 1s busy cadence
                        # forever (adversarial review, 5 Aug).
                        self.ledger.pop(m.group(1), None)
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
                self.route_at = time.monotonic()
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
        self.model = model_version()   # fingerprinted once, at construction
        self._noop_since = None        # last gesture said to have decided nothing
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
        # Constructed here, but it opens NOTHING until run() calls start():
        # importing or instantiating couchd must never bind a socket.
        self.supervisor = SupervisorObserver(self.world, self.pad)
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
        if hold_marker_spent(region, frm, to):
            self.pad.tracker.consume_hold_release()
        if region == 'gesture' and to == 'double-tap':
            # Whichever edge got here - live, coalesced-from-down, or the
            # idle marker - the double is taken; the marker must not re-fire
            # it once the switcher decides and the region returns to idle.
            self.pad.tracker.consume_double_tap()

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
        # The handoff's SIGNATURE is route_pad(kodi) off a gesture - the one
        # intent every hand-the-pad-back path emits unconditionally. It used to
        # key off close_steam_menu, which stopped being unconditional the day
        # that press was gated on the menu actually being open (T4-1); a guard
        # window that only opened when Steam had already misbehaved would be
        # exactly backwards, since watching for that is what the window is for.
        handoff = (intent.verb == 'route_pad' and intent.subject == 'kodi'
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
                              context=self.intent_context,
                              heartbeat_fresh=self._heartbeat_fresh)

    def _heartbeat_fresh(self):
        """Is couchd's OWN lease still visibly alive to the other stack?

        Legacy re-acts the moment status.json goes >30s stale, but a couchd
        that stalled 30-60s (an X scan, a wedged Kodi read) used to resume
        acting the instant it unwedged - a window where BOTH stacks act on
        one world, the one advertised impossibility (adversarial review,
        5 Aug). Under 25s of the 30s lease is fresh; past it, decline to act
        for one pass - the run loop rewrites status.json right after, and
        the next pass acts on a lease legacy can see."""
        return (time.monotonic() - self.last_status) < 25.0

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
        # The wire FIRST: a press that arrived over it belongs to this pass's
        # world, exactly as one read from evdev between passes does.
        self.supervisor.drain()
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
            game_windows=tuple(xst.game_windows) if xst else (),
            snaps=snap_captures(PAUSED_DIR),
            steam_known=self.world.src('steam').ok,
            steam_route=self.steam.route, steam_route_at=self.steam.route_at,
            ui_mode=self.steam.ui_mode,
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
            hold_release_pending=self.pad.hold_release_pending,
            double_tap_pending=self.pad.double_tap_pending,
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
                    games=dict(self.machine.games),
                    suspended_running_since=self.machine.drift_since[
                        'suspended_running'],
                    frozen_noflag_since=self.machine.drift_since[
                        'frozen_noflag'])
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
            rec = self.executor.execute(it, o)
            # C17 needs the world looked at, not just waited on: an effect only
            # a Kodi read can show gets one targeted read on the next pass, so
            # the check races the deadline instead of the 10s limiter.
            if (rec or {}).get('acted') and it.verb in KODI_OBSERVED_EFFECTS:
                self.kodi.request_read(it.verb)
        # ...and keep looking while the prediction is outstanding. The switcher
        # dialog takes 1.3-1.5s to draw, so one read at +0.2s would miss it and
        # the next scheduled one lands 10s later, past the deadline. Bounded
        # twice over: only while something is pending, and never faster than
        # KODI_EFFECT_READ_FLOOR.
        waiting = [v for v in self.executor.pending_verbs()
                   if v in KODI_OBSERVED_EFFECTS]
        if waiting:
            self.kodi.request_read('pending:' + waiting[0])
        self.note_noop_gesture(o, intents)
        self.sync_guard_pidfile(o)
        self.passes += 1
        self.log_edge(o, intents)
        return o, intents

    def note_noop_gesture(self, o, intents):
        """A gesture that fired and decided NOTHING, said out loud once.

        A silent no-op is indistinguishable from a dropped press, both in the
        room and in the corpus - which is exactly how the coalesced double-tap
        went unnoticed. The one that is deliberate (a hold with no session:
        legacy's hold_ready gate, see reconcile) therefore records itself as a
        decision, so the evening's evidence says "decided to do nothing" rather
        than saying nothing at all.
        """
        g = o.regions.get('gesture')
        if g not in ('hold-fired', 'handoff-pending', 'timed-out',
                     'double-tap', 'long-hold-fired'):
            self._noop_since = None
            return
        since = o.region_since.get('gesture')
        if intents or self._noop_since == since:
            return
        self._noop_since = since
        why = ('no session: the hold has nothing to suspend and legacy would '
               'not have spent it either' if not o.session_present
               else 'nothing left to decide (already done, or cooled down)')
        self.log.write({'kind': 'decision', 'event': 'gesture-no-op',
                        'gesture': g, 'binding': o.binding('hold'),
                        'session': bool(o.session_present), 'why': why,
                        'regions': dict(o.regions)})
        say(f'gesture {g}: nothing to do ({why})')

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
            'model_version': self.model['version'], 'git': self.model['git'],
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
            # The stage-2 wire, so the health check can tell "no supervisor"
            # from "a supervisor that is dropping our pad events on the floor"
            # without opening a socket of its own.
            'supervisor': self.supervisor.status(mono),
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
        try:
            write_atomic(os.path.join(SHADOW_DIR, 'status.json'),
                         json.dumps(status, indent=1, default=str))
        except OSError as e:
            # The heartbeat write is the LEASE. A transient FS error (ENOSPC,
            # a wobbly disk - this box had one today) must not take the whole
            # daemon down through the run loop: a dead daemon stops acting
            # NOW, while a stale heartbeat hands gestures back to legacy in
            # 30s by design. Say it loudly and let the next interval retry;
            # if the condition persists, the lease lapsing IS the rollback.
            say(f'STATUS WRITE FAILED ({e}) - heartbeat at risk; legacy '
                f'reclaims via the lease if this persists')

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
        mv = model_version()
        self.log.write({'kind': 'daemon', 'event': 'start', 'pid': os.getpid(),
                        'mode': 'acting' if self.executor.owned else 'shadow',
                        'owns': sorted(self.executor.owned),
                        # ...and what the FILE asked for. The two differ only
                        # for `input`, which stage-1 couchd cannot execute but
                        # which the differ still has to know was flipped: it
                        # decides whether that evening's pad evidence was
                        # supposed to arrive over the supervisor wire.
                        'owns_declared': self.owns.sorted,
                        'owns_file': self.owns.path,
                        # What the differ keys "stale model" off: two runs of
                        # the SAME model are one model's evidence, however many
                        # times the daemon was restarted between them.
                        'model_version': mv['version'],
                        'model_files': mv['files'], 'git': mv['git'],
                        'steam_logs': STEAM_LOGS})
        self.supervisor.start()
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
        self.supervisor.close()
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
