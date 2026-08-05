#!/usr/bin/env python3
"""The X11 adapter: the event subscription, and the trap it exists to avoid.

No X server is touched here. `FakeDisplay` models the one behaviour of
python-xlib that this whole design hangs off: requests and events share ONE
socket, so any request/reply pair (query_tree, get_wm_class, ...) silently
pulls queued events off the socket into the library's internal deque - after
which select()/add_reader will never fire for them again. That is precisely
why couchd's x11 observer reported "events: 0" through an entire evening of
window churn on 4-5 Aug 2026, and why `drain()` is called after every scan as
well as on readability.

    .venv/bin/python -m pytest test_x11.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import x11
from x11 import (BANNED, EVENT_RESCAN_INTERVAL, IDLE_RESCAN_INTERVAL,
                 RESCAN_MIN_INTERVAL, STRUCTURE_EVENTS, WATCHED_ATOMS,
                 X11Adapter)

ATOMS = {'_NET_WM_NAME': 1, '_NET_WM_PID': 2,
         'GAMESCOPECTRL_BASELAYER_APPID': 3, 'STEAM_GAMES_RUNNING': 4,
         '_NET_ACTIVE_WINDOW': 5, '_NET_CLIENT_LIST_STACKING': 6,
         '_NET_CLIENT_LIST': 7, '_XROOTPMAP_ID': 99}


class Ev:
    def __init__(self, kind, atom=None):
        self.__class__ = type(kind, (Ev,), {})   # class NAME is the event name
        self.atom = atom


def ev(kind, atom=None):
    e = Ev.__new__(type(kind, (object,), {}))
    e.atom = atom
    return e


class Attr:
    def __init__(self, map_state=2, win_class=1):
        self.map_state = map_state
        self.win_class = win_class


class Geo:
    def __init__(self, w, h):
        self.width, self.height = w, h


class FakeWindow:
    def __init__(self, d, name='', cls='', w=1920, h=1080, mapped=2,
                 children=(), props=None, parent=None):
        self.d = d
        self.name, self.cls = name, cls
        self.w, self.h, self.mapped = w, h, mapped
        self.children = list(children)
        self.props = dict(props or {})
        self.parent = parent

    # every one of these is a REQUEST: it touches the socket.
    def get_attributes(self):
        self.d._request()
        return Attr(self.mapped)

    def get_geometry(self):
        self.d._request()
        return Geo(self.w, self.h)

    def get_wm_name(self):
        self.d._request()
        return self.name

    def get_wm_class(self):
        self.d._request()
        return (self.cls, self.cls) if self.cls else None

    def query_tree(self):
        self.d._request()
        return type('T', (), {'children': list(self.children),
                              'parent': self.parent})()

    def get_full_property(self, atom, _type):
        self.d._request()
        v = self.props.get(atom)
        return None if v is None else type('P', (), {'value': v})()

    def change_attributes(self, event_mask=None):
        self.d._request()
        self.d.mask = event_mask


class FakeDisplay:
    """One socket, shared by requests and events - the whole point."""

    def __init__(self, children=(), focus=None):
        self.wire = []          # bytes on the socket (what select() sees)
        self.queue = []         # already read into the library's deque
        self.mask = None
        self.requests = 0
        self.closed = False
        self.fail = None
        self.root = FakeWindow(self, name='root', children=children)
        self._focus = focus or FakeWindow(self, cls='Kodi', parent=self.root)

    # -- the socket ------------------------------------------------------
    @property
    def readable(self):
        """What an asyncio add_reader would fire on."""
        return bool(self.wire)

    def push(self, *events):
        self.wire.extend(events)

    def _request(self):
        """A request/reply round trip: it reads the socket, and anything that
        was queued there arrives in the event deque as a side effect."""
        if self.fail:
            raise self.fail
        self.requests += 1
        self.queue.extend(self.wire)
        self.wire.clear()

    # -- the Xlib API the adapter uses -----------------------------------
    def pending_events(self):
        self._request()
        return len(self.queue)

    def next_event(self):
        return self.queue.pop(0)

    def screen(self):
        return type('S', (), {'root': self.root})()

    def intern_atom(self, name):
        return ATOMS.get(name, 1000 + len(name))

    def get_input_focus(self):
        self._request()
        return type('F', (), {'focus': self._focus})()

    def sync(self):
        self._request()

    def fileno(self):
        return 42

    def close(self):
        self.closed = True


def adapter_on(display):
    """An adapter wired to a fake display, past connect()."""
    a = X11Adapter(':99')
    a.d = display
    a.root = display.root
    a._atoms = dict(ATOMS)
    a._watched = {ATOMS[n] for n in WATCHED_ATOMS}
    return a


def game_world(d):
    return [FakeWindow(d, name='Kodi', cls='Kodi'),
            FakeWindow(d, name='ELDEN RING', cls='steam_app_367520')]


# =========================================================================
# passivity
# =========================================================================
def test_the_root_mask_is_read_only_and_never_a_window_manager(monkeypatch):
    """The one X write in the whole daemon, and what it may not contain."""
    from Xlib import X, display
    d = FakeDisplay()
    a = X11Adapter(':99')
    monkeypatch.setattr(display, 'Display', lambda name: d)
    assert a.connect()
    assert d.mask & X.PropertyChangeMask
    assert d.mask & X.SubstructureNotifyMask
    assert d.mask & X.FocusChangeMask
    for banned in (X.SubstructureRedirectMask, X.ResizeRedirectMask,
                   X.ButtonPressMask, X.ButtonReleaseMask, X.KeyPressMask,
                   X.KeyReleaseMask, X.PointerMotionMask):
        assert not d.mask & banned


def test_the_file_still_names_what_it_may_never_do():
    src = open(x11.__file__).read()
    for banned in BANNED:
        assert banned in src, 'the ban has to stay written down'
    assert 'grab_pointer' not in src and 'grab_keyboard' not in src
    # exactly one write, and it is on the root window
    assert src.count('change_attributes(') == 1
    assert 'root.change_attributes(' in src


# =========================================================================
# the trap: requests swallow events
# =========================================================================
def test_a_scan_swallows_queued_events_and_they_are_counted_anyway():
    """THE 4-5 Aug bug. The scan's own replies empty the socket, so the
    asyncio reader never fires again - the events are only ever counted if
    the scan drains afterwards."""
    d = FakeDisplay(children=[])
    a = adapter_on(d)
    d.children = game_world(d)
    d.root.children = d.children
    d.push(ev('MapNotify'), ev('ConfigureNotify'))
    assert d.readable, 'the event loop would fire here...'
    a.refresh(force=True)
    assert not d.readable, '...and the scan just took that away'
    assert a.take_events() == 2, 'harvested despite the socket going quiet'
    assert a.events == 2


def test_events_are_counted_once_across_both_paths():
    d = FakeDisplay(children=[])
    a = adapter_on(d)
    d.push(ev('MapNotify'))
    assert a.drain() == 1              # the event path got there first
    a.refresh(force=True)
    assert a.take_events() == 1, 'the scan must not double count it'


def test_uninteresting_root_properties_do_not_dirty_the_cache():
    """A wallpaper refresh is not a window change; dirtying on it would turn
    every xfdesktop repaint into an attention window."""
    d = FakeDisplay(children=[])
    a = adapter_on(d)
    a._dirty = False
    d.push(ev('PropertyNotify', atom=ATOMS['_XROOTPMAP_ID']))
    assert a.drain() == 0
    assert not a._dirty
    d.push(ev('PropertyNotify', atom=ATOMS['_NET_ACTIVE_WINDOW']))
    assert a.drain() == 1
    assert a._dirty


def test_every_structure_event_counts():
    d = FakeDisplay(children=[])
    a = adapter_on(d)
    d.push(*[ev(k) for k in STRUCTURE_EVENTS])
    assert a.drain() == len(STRUCTURE_EVENTS)


# =========================================================================
# one interpretation, two acquisitions
# =========================================================================
def test_the_event_path_and_the_poll_path_produce_the_same_state():
    """The equivalence the design rests on: an event never builds state, it
    just says the screen moved, so both paths end in the same `_scan`."""
    d1 = FakeDisplay()
    d1.root.children = game_world(d1)
    polled = adapter_on(d1).refresh(force=True)

    d2 = FakeDisplay()
    d2.root.children = game_world(d2)
    a2 = adapter_on(d2)
    a2.refresh(force=True)                      # a first, quiescent look
    a2._last_scan -= 10                         # ...a while ago
    d2.push(ev('PropertyNotify', atom=ATOMS['_NET_ACTIVE_WINDOW']))
    a2.drain()                                  # the EVENT path
    evented = a2.refresh()

    assert polled.as_dict() == evented.as_dict()
    assert evented.ok and evented.top_name == 'ELDEN RING'
    assert evented.top_class == 'steam_app_367520'
    assert evented.kodi_present is True


def test_the_scan_reads_the_same_screen_the_guard_would():
    d = FakeDisplay()
    d.root.children = [
        FakeWindow(d, name='tiny', cls='xfce4-panel', w=1920, h=27),
        FakeWindow(d, name='Kodi', cls='Kodi'),
        FakeWindow(d, name='Steam Big Picture Mode', cls='steamwebhelper'),
    ]
    st = adapter_on(d).refresh(force=True)
    assert st.big_picture is True
    assert st.kodi_present is True
    assert st.top_name == 'Steam Big Picture Mode', 'last big window wins'
    assert st.n_windows == 3


def test_steams_root_atoms_come_through():
    d = FakeDisplay()
    d.root.props[ATOMS['GAMESCOPECTRL_BASELAYER_APPID']] = [769, 367520]
    d.root.children = game_world(d)
    st = adapter_on(d).refresh(force=True)
    assert st.atoms['GAMESCOPECTRL_BASELAYER_APPID'] == [769, 367520]


# =========================================================================
# rate limits (R6)
# =========================================================================
def test_an_event_dirtied_cache_rescans_at_the_attention_floor():
    d = FakeDisplay()
    d.root.children = game_world(d)
    a = adapter_on(d)
    a.refresh(force=True)
    before = d.requests
    d.push(ev('MapNotify'))
    a.refresh()                       # dirty, but the floor has not passed
    assert d.requests - before < 5, 'a burst of events is not a scan storm'
    a._last_scan -= EVENT_RESCAN_INTERVAL + 0.01
    d.push(ev('MapNotify'))
    before = d.requests
    a.refresh()
    assert d.requests - before > 5, 'past the floor it rescans'


def test_a_quiet_screen_still_gets_its_belt_and_braces_poll():
    d = FakeDisplay()
    d.root.children = game_world(d)
    a = adapter_on(d)
    a.refresh(force=True)
    a._last_scan -= RESCAN_MIN_INTERVAL + 0.01
    before = d.requests
    a.refresh()
    assert d.requests - before <= 2, 'nothing happened: no rescan yet'
    a._last_scan -= IDLE_RESCAN_INTERVAL
    before = d.requests
    a.refresh()
    assert d.requests - before > 5, 'the poll is what catches a missed event'


# =========================================================================
# resilience: a dying X may never take the daemon with it
# =========================================================================
def test_a_display_that_dies_mid_drain_degrades_instead_of_raising():
    d = FakeDisplay()
    a = adapter_on(d)
    d.fail = IOError('Broken pipe')
    assert a.drain() == 0
    assert a.d is None
    assert a.state.ok is False and 'drain' in a.state.reason


def test_a_display_that_dies_mid_scan_degrades_instead_of_raising():
    d = FakeDisplay()
    d.root.children = game_world(d)
    a = adapter_on(d)

    def boom():
        raise IOError('X connection dropped')
    d.root.query_tree = boom
    a.refresh(force=True)
    assert a.d is None
    assert a.state.ok is False and 'scan' in a.state.reason
    # and the next refresh tries to reconnect rather than exploding
    a.refresh()
    assert a.state.ok is False


def test_refresh_on_a_dead_connection_returns_a_not_ok_state():
    a = X11Adapter('/nonexistent-display-couchd-test')
    st = a.refresh()
    assert st.ok is False and st.reason
    assert a.state.as_dict()['top_name'] == ''


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
