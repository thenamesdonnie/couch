"""Read-only X11 adapter for couchd (python-xlib, pinned behind this file).

Everything the daemon needs to know about the screen comes through here:
which big window is on top, what has input focus, whether Kodi exists, and
the root atoms Steam writes (GAMESCOPECTRL_BASELAYER_APPID,
STEAM_GAMES_RUNNING).

Passivity rules, enforced in this file and asserted at import:

  * the only X write is `change_attributes` on the ROOT window to subscribe
    to PropertyChangeMask|SubstructureNotifyMask|FocusChangeMask (hhd's
    approach: select on Display.fileno(), poll only as a backstop);
  * no input mask is EVER requested (ButtonPress, KeyPress, PointerMotion...)
    and no pointer/keyboard/server grab is ever taken - couchd watches the
    screen, it never competes for it;
  * SubstructureRedirectMask and ResizeRedirectMask are never requested -
    they would make couchd the window manager;
  * XGrabServer is never called;
  * no window is ever configured, focused, iconified or sent a message.

TWO ACQUISITION PATHS, ONE INTERPRETATION. Events (this file's `drain`) never
build state themselves: they say "something moved", which marks the cache
dirty and lets the daemon reconcile now instead of at the next tick. The only
thing that ever turns X into an X11State is `_scan()`, so the event path and
the poll path cannot drift into two different opinions of the screen.

The trap this file exists to avoid: python-xlib's request/reply machinery
(`query_tree`, `get_wm_class`, ...) reads the SAME socket the event loop
selects on, so a scan silently swallows every queued event into the library's
internal deque and the fd goes unreadable again. That is why `drain()` is
called after every scan as well as on readability - without it the observer
reports "0 events" through an entire evening of window churn, which is
exactly what it did until 5 Aug 2026.

Wayland kills this file in stage 4; xcffib is the named fallback if
python-xlib finally rots.
"""
import time

BANNED = ('SubstructureRedirectMask', 'ResizeRedirectMask', 'grab_server')

MIN_W, MIN_H = 600, 400        # same "big window" rule the guard uses
RESCAN_MIN_INTERVAL = 1.0      # never full-rescan faster than 1Hz (R6)
# ...unless an EVENT said the screen moved, in which case R6's attention-mode
# floor applies instead: a window change that the daemon has to decide on is
# worth a 200ms rescan, and the events themselves rate-limit the rescans.
EVENT_RESCAN_INTERVAL = 0.2
IDLE_RESCAN_INTERVAL = 5.0     # nothing said anything: the belt-and-braces poll

# Root properties worth a rescan. Everything else on the root window
# (_XROOTPMAP_ID, the desktop image, RESOURCE_MANAGER, timestamps...) changes
# for reasons the console does not care about, and dirtying the cache for
# those would turn a wallpaper refresh into an attention window.
WATCHED_ATOMS = ('_NET_ACTIVE_WINDOW', '_NET_CLIENT_LIST_STACKING',
                 '_NET_CLIENT_LIST', 'GAMESCOPECTRL_BASELAYER_APPID',
                 'STEAM_GAMES_RUNNING')
# Structure events that mean a top-level window appeared, vanished, moved or
# changed stacking. MapNotify/UnmapNotify are how a game window and Big
# Picture arrive and leave; DestroyNotify is how a crashed one leaves.
STRUCTURE_EVENTS = ('ConfigureNotify', 'MapNotify', 'UnmapNotify',
                    'DestroyNotify', 'CreateNotify', 'ReparentNotify',
                    'FocusIn', 'FocusOut')


class X11State:
    """Immutable-ish snapshot handed to the daemon each pass."""

    __slots__ = ('ok', 'reason', 'top_name', 'top_class', 'focused_class',
                 'kodi_present', 'big_picture', 'game_windows', 'atoms',
                 'n_windows', 'ts')

    def __init__(self):
        self.ok = False
        self.reason = 'not connected'
        self.top_name = ''
        self.top_class = ''
        self.focused_class = ''
        self.kodi_present = False
        self.big_picture = False
        self.game_windows = ()
        self.atoms = {}
        self.n_windows = 0
        self.ts = 0.0

    def as_dict(self):
        return {'ok': self.ok, 'reason': self.reason, 'top_name': self.top_name,
                'top_class': self.top_class, 'focused_class': self.focused_class,
                'kodi_present': self.kodi_present, 'big_picture': self.big_picture,
                'game_windows': list(self.game_windows), 'atoms': dict(self.atoms),
                'n_windows': self.n_windows}


class X11Adapter:
    def __init__(self, display_name=':0'):
        self.display_name = display_name
        self.d = None
        self.root = None
        self.state = X11State()
        self._last_scan = 0.0
        self._dirty = True
        self._atoms = {}
        self._watched = set()      # atom ids of WATCHED_ATOMS, for PropertyNotify
        self._X = None
        # Event accounting. `events` is the lifetime count of INTERESTING
        # events (the number the observer-health gate reports); `seen` counts
        # everything the server sent us, so "0 interesting, 400 seen" reads
        # differently from "the connection is dead".
        self.events = 0
        self.seen = 0
        self.kinds = {}
        self._pending = 0          # interesting events not yet handed over

    # -- connection ------------------------------------------------------
    def connect(self):
        """True if we now hold a display connection. Never raises."""
        if self.d is not None:
            return True
        try:
            from Xlib import display, X
            self._X = X
            # The one write: subscribe to root events. The mask deliberately
            # excludes both redirect masks AND every input mask (see BANNED).
            mask = (X.PropertyChangeMask | X.SubstructureNotifyMask
                    | X.FocusChangeMask)
            assert not mask & X.SubstructureRedirectMask
            assert not mask & X.ResizeRedirectMask
            for banned in (X.ButtonPressMask, X.ButtonReleaseMask,
                           X.KeyPressMask, X.KeyReleaseMask,
                           X.PointerMotionMask):
                assert not mask & banned
            d = display.Display(self.display_name)
            root = d.screen().root
            root.change_attributes(event_mask=mask)
            d.sync()
            self.d, self.root = d, root
            for name in ('_NET_WM_NAME', '_NET_WM_PID',
                         'GAMESCOPECTRL_BASELAYER_APPID', 'STEAM_GAMES_RUNNING'):
                self._atoms[name] = d.intern_atom(name)
            self._watched = set()
            for name in WATCHED_ATOMS:
                try:
                    self._watched.add(d.intern_atom(name))
                except Exception:
                    pass
            self._dirty = True
            self.state.reason = ''
            return True
        except Exception as e:          # no X, no auth, display gone
            self.d = self.root = None
            self.state = X11State()
            self.state.reason = f'{type(e).__name__}: {e}'
            return False

    def fileno(self):
        return self.d.fileno() if self.d is not None else None

    def close(self):
        if self.d is not None:
            try:
                self.d.close()
            except Exception:
                pass
        self.d = self.root = None
        self.state = X11State()
        self.state.reason = 'closed'

    # -- event pump ------------------------------------------------------
    def drain(self):
        """Consume queued events; returns the number of INTERESTING ones.

        Called from two places and it must be both: on fd readability (the
        event path) AND after every scan (because the scan's own replies pull
        those same events off the socket into python-xlib's internal deque,
        where select will never see them again). Read-only throughout; an
        event is never interpreted here beyond "the screen moved".
        """
        if self.d is None:
            return 0
        interesting = 0
        try:
            n = self.d.pending_events()
            for _ in range(n):
                ev = self.d.next_event()
                name = ev.__class__.__name__
                self.seen += 1
                self.kinds[name] = self.kinds.get(name, 0) + 1
                if name == 'PropertyNotify':
                    atom = getattr(ev, 'atom', None)
                    # An unresolved atom set is a fresh connection, not a
                    # reason to ignore the world: fail towards rescanning.
                    if not self._watched or atom in self._watched:
                        interesting += 1
                elif name in STRUCTURE_EVENTS:
                    interesting += 1
        except Exception as e:
            self._disconnect(f'drain: {type(e).__name__}: {e}')
            return 0
        if interesting:
            self._dirty = True
            self.events += interesting
            self._pending += interesting
        return interesting

    def take_events(self):
        """Interesting events since the last call - the observer's tally."""
        n, self._pending = self._pending, 0
        return n

    def _disconnect(self, reason):
        try:
            if self.d is not None:
                self.d.close()
        except Exception:
            pass
        self.d = self.root = None
        self.state = X11State()
        self.state.reason = reason

    # -- scanning --------------------------------------------------------
    def refresh(self, force=False):
        """Rebuild the cached view - the ONE interpretation of the screen.

        Rate limits, all of them R6's: an event-dirtied cache rescans at the
        attention floor (200ms), an undirtied one no faster than 1Hz, and a
        silent screen still gets its belt-and-braces poll every 5s.
        """
        if self.d is None:
            if not self.connect():
                return self.state
            force = True
        # Harvest first: events that arrived since the last look decide
        # whether this call is a dirty rescan or an idle one.
        self.drain()
        if self.d is None:                      # drain lost the connection
            return self.state
        now = time.monotonic()
        since = now - self._last_scan
        floor = EVENT_RESCAN_INTERVAL if self._dirty else RESCAN_MIN_INTERVAL
        if not force:
            if not self._dirty and since < IDLE_RESCAN_INTERVAL:
                return self.state
            if since < floor:
                return self.state
        self._last_scan = now
        self._dirty = False
        try:
            self.state = self._scan()
        except Exception as e:
            self._disconnect(f'scan: {type(e).__name__}: {e}')
            return self.state
        # ...and harvest again: the scan's own replies just emptied the socket,
        # taking any events that landed during it into python-xlib's deque
        # where the event loop can no longer see them. Without this the
        # observer counts zero events through an entire evening of churn.
        self.drain()
        return self.state

    def _prop(self, w, atom):
        try:
            p = w.get_full_property(self._atoms[atom], 0)
            if not p:
                return None
            return p.value
        except Exception:
            return None

    def _name_of(self, w, depth=0):
        try:
            v = self._prop(w, '_NET_WM_NAME')
            nm = v.decode('utf-8', 'replace') if isinstance(v, bytes) else ''
            nm = nm or (w.get_wm_name() or '')
            cls = (w.get_wm_class() or ('', ''))[0]
            if nm or cls:
                return nm or cls
            if depth < 3:
                for c in w.query_tree().children:
                    r = self._name_of(c, depth + 1)
                    if r:
                        return r
        except Exception:
            pass
        return ''

    def _class_of(self, w, depth=0):
        try:
            cls = (w.get_wm_class() or ('', ''))[0]
            if cls:
                return cls
            if depth < 3:
                for c in w.query_tree().children:
                    r = self._class_of(c, depth + 1)
                    if r:
                        return r
        except Exception:
            pass
        return ''

    def _scan(self):
        st = X11State()
        st.ok = True
        st.reason = ''
        st.ts = time.time()
        children = self.root.query_tree().children   # bottom -> top
        st.n_windows = len(children)
        games = []
        for c in children:
            try:
                a = c.get_attributes()
                if a.map_state != 2 or a.win_class == 2:   # unmapped/InputOnly
                    continue
                g = c.get_geometry()
                if g.width < 20 or g.height < 20:          # C26: ignore specks
                    continue
                nm = self._name_of(c)
                cls = self._class_of(c)
                if cls == 'Kodi' or nm == 'Kodi':
                    st.kodi_present = True
                if 'Big Picture' in (nm or ''):
                    st.big_picture = True
                if cls.startswith('steam_app'):
                    games.append(cls)
                if g.width < MIN_W or g.height < MIN_H:
                    continue
                if nm:
                    st.top_name, st.top_class = nm, cls
            except Exception:
                continue
        st.game_windows = tuple(games)
        # focused window's class, walking up to a client that has one
        try:
            f = self.d.get_input_focus().focus
            for _ in range(5):
                if not hasattr(f, 'get_wm_class'):
                    break
                try:
                    cls = (f.get_wm_class() or ('', ''))[0]
                except Exception:
                    cls = ''
                if cls:
                    st.focused_class = cls
                    break
                f = f.query_tree().parent
        except Exception:
            pass
        # Steam's root atoms (C24)
        for name in ('GAMESCOPECTRL_BASELAYER_APPID', 'STEAM_GAMES_RUNNING'):
            v = self._prop(self.root, name)
            if v is not None:
                try:
                    st.atoms[name] = list(v)
                except Exception:
                    st.atoms[name] = str(v)
        return st
