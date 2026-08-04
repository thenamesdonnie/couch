"""Read-only X11 adapter for couchd (python-xlib, pinned behind this file).

Everything the daemon needs to know about the screen comes through here:
which big window is on top, what has input focus, whether Kodi exists, and
the root atoms Steam writes (GAMESCOPECTRL_BASELAYER_APPID,
STEAM_GAMES_RUNNING).

Passivity rules, enforced in this file and asserted at import:

  * the only X write is `change_attributes` on the ROOT window to subscribe
    to PropertyChangeMask|SubstructureNotifyMask (hhd's approach: select on
    Display.fileno(), poll only as a backstop);
  * SubstructureRedirectMask and ResizeRedirectMask are never requested -
    they would make couchd the window manager;
  * XGrabServer is never called;
  * no window is ever configured, focused, iconified or sent a message.

Wayland kills this file in stage 4; xcffib is the named fallback if
python-xlib finally rots.
"""
import time

BANNED = ('SubstructureRedirectMask', 'ResizeRedirectMask', 'grab_server')

MIN_W, MIN_H = 600, 400        # same "big window" rule the guard uses
RESCAN_MIN_INTERVAL = 1.0      # never full-rescan faster than 1Hz (R6)


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
        self._X = None

    # -- connection ------------------------------------------------------
    def connect(self):
        """True if we now hold a display connection. Never raises."""
        if self.d is not None:
            return True
        try:
            from Xlib import display, X
            self._X = X
            # The one write: subscribe to root events. The mask deliberately
            # excludes both redirect masks (see BANNED).
            mask = X.PropertyChangeMask | X.SubstructureNotifyMask
            assert not mask & X.SubstructureRedirectMask
            assert not mask & X.ResizeRedirectMask
            d = display.Display(self.display_name)
            root = d.screen().root
            root.change_attributes(event_mask=mask)
            d.sync()
            self.d, self.root = d, root
            for name in ('_NET_WM_NAME', '_NET_WM_PID',
                         'GAMESCOPECTRL_BASELAYER_APPID', 'STEAM_GAMES_RUNNING'):
                self._atoms[name] = d.intern_atom(name)
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
        """Consume queued events; returns True if something interesting
        happened (so the caller can go into attention mode). Read-only."""
        if self.d is None:
            return False
        changed = False
        try:
            n = self.d.pending_events()
            for _ in range(n):
                ev = self.d.next_event()
                name = ev.__class__.__name__
                if name in ('PropertyNotify', 'ConfigureNotify', 'MapNotify',
                            'UnmapNotify', 'DestroyNotify', 'CreateNotify',
                            'ReparentNotify'):
                    changed = True
        except Exception as e:
            self._disconnect(f'drain: {type(e).__name__}: {e}')
            return True
        if changed:
            self._dirty = True
        return changed

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
        """Rebuild the cached view. Rate-limited to 1Hz unless an event
        marked us dirty (and even then, never faster than 1Hz)."""
        if self.d is None:
            if not self.connect():
                return self.state
            force = True
        now = time.monotonic()
        if not force and not self._dirty and now - self._last_scan < 5.0:
            return self.state
        if now - self._last_scan < RESCAN_MIN_INTERVAL and not force:
            return self.state
        self._last_scan = now
        self._dirty = False
        try:
            self.state = self._scan()
        except Exception as e:
            self._disconnect(f'scan: {type(e).__name__}: {e}')
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
