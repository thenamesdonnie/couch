#!/usr/bin/env python3
"""The supervisor wire: the protocol, both endpoints, and the inert property.

This is the path between the pad and everything else, so it is tested harder
than most of stage 2: a round trip, every shape of malformed line, an
unauthorised peer refused, the send queue overflowing rather than blocking,
a reconnect after the listener dies, and - the one that matters most for a
daemon that owns gestures on a live console tonight - that with NOTHING
connected, couchd behaves exactly as it did before this file existed.

NO DEVICES ARE CREATED HERE and no live path is written: every socket lives
in tmp_path, and both human logs are redirected there before anything can
append to /tmp/couchd.log or /tmp/inputproc.log.

    .venv/bin/python -m pytest test_supervisor.py -q
"""
import json
import os
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import couchd
import gesture
import inputproc
import supervisor
from couchd import PadObserver, Source, SupervisorObserver

TIMEOUT = 5.0


def wait_for(pred, timeout=TIMEOUT, tick=0.01):
    """Poll until pred() is true. Returns the truth of it at the deadline, so
    a failing assertion says what was wrong rather than just timing out."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(tick)
    return pred()


class FakeLog:
    def __init__(self):
        self.recs = []
        self.counts = {}

    def write(self, rec):
        self.recs.append(dict(rec))
        return rec


class FakeWorld:
    """World's surface, minus the asyncio Event - these tests never run a
    loop, and attention() only has to be recordable."""

    def __init__(self):
        self.log = FakeLog()
        self.sources = {}
        self.attentions = []

    def src(self, name):
        return self.sources.setdefault(name, Source(name))

    def attention(self, reason, edge=False, kernel_t=None):
        self.attentions.append({'reason': reason, 'edge': edge,
                                'kernel_t': kernel_t})


@pytest.fixture(autouse=True)
def no_live_paths(tmp_path, monkeypatch):
    """Both stacks' human logs into tmp_path. A test that appends to
    /tmp/couchd.log is scribbling on the evening's evidence."""
    monkeypatch.setattr(couchd, 'HUMAN_LOG', str(tmp_path / 'couchd.log'))
    monkeypatch.setattr(inputproc, 'HUMAN_LOG', str(tmp_path / 'inputproc.log'))


@pytest.fixture
def sock_path(tmp_path):
    return str(tmp_path / 'couchd.sock')


@pytest.fixture
def listener(sock_path):
    li = supervisor.SupervisorListener(path=sock_path)
    assert li.start(), li.error
    yield li
    li.close()


# =========================================================================
# the grammar
# =========================================================================
def test_round_trip_carries_the_kernel_timestamp_intact():
    """The wire's whole job: a raw edge and the kernel time it happened."""
    msg = supervisor.decode(supervisor.encode('press', value=1,
                                              kernel_t=123456.789012))
    assert msg['kind'] == 'press' and msg['value'] == 1
    assert msg['kernel_t'] == pytest.approx(123456.789012, abs=1e-6)
    assert msg['v'] == supervisor.PROTOCOL_VERSION


@pytest.mark.parametrize('kind,fields', [
    ('press', {'value': 0, 'kernel_t': 1.0}),
    ('pad', {'state': 'attached', 'node': '/dev/input/event21', 'grabbed': True}),
    ('pad', {'state': 'detached', 'why': 'eof'}),
    ('hello', {'pid': 4242, 'version': 1, 'owns_input': True}),
    ('health', {'drops': 7, 'owns_input': True, 'state': 'owned'}),
])
def test_every_kind_round_trips(kind, fields):
    msg = supervisor.decode(supervisor.encode(kind, **fields))
    assert msg['kind'] == kind
    for k, v in fields.items():
        assert msg[k] == v


def test_encoding_an_unknown_kind_is_refused_at_the_source():
    with pytest.raises(supervisor.ProtocolError):
        supervisor.encode('gesture', event='ps-hold')


@pytest.mark.parametrize('line', [
    '',
    '   ',
    'not json at all',
    '[1, 2, 3]',
    '"a string"',
    '{}',
    '{"kind": "press"}',                                # no value, no kernel_t
    '{"kind": "press", "value": 1}',                    # no kernel_t
    '{"kind": "press", "kernel_t": 1.0}',               # no value
    '{"kind": "press", "value": 3, "kernel_t": 1.0}',   # not a button state
    '{"kind": "press", "value": "1", "kernel_t": 1.0}',
    '{"kind": "press", "value": true, "kernel_t": 1.0}',
    '{"kind": "press", "value": 1, "kernel_t": "soon"}',
    '{"kind": "press", "value": 1, "kernel_t": null}',
    '{"kind": "press", "value": 1, "kernel_t": 1.0, "v": 2}',
    '{"kind": "gesture", "event": "ps-hold"}',          # a DECISION: not ours
    '{"kind": "pad", "state": "wobbly"}',
    '{"kind": "hello", "pid": 0}',
    '{"kind": "hello", "pid": -1}',
    '{"kind": "health", "drops": -1}',
])
def test_malformed_lines_are_refused_one_by_one(line):
    with pytest.raises(supervisor.ProtocolError):
        supervisor.decode(line)


def test_a_nan_timestamp_is_not_a_timestamp():
    """json.loads accepts NaN and Infinity by default; the arithmetic on the
    far side of this wire does not."""
    for bad in ('NaN', 'Infinity', '-Infinity'):
        with pytest.raises(supervisor.ProtocolError):
            supervisor.decode('{"kind":"press","value":1,"kernel_t":%s}' % bad)


def test_unknown_extra_keys_survive_rather_than_breaking_the_wire():
    """A newer sender adding a field must not take an older receiver down."""
    msg = supervisor.decode('{"kind":"press","value":1,"kernel_t":5.0,'
                            '"battery":88}')
    assert msg['value'] == 1 and msg['battery'] == 88


# =========================================================================
# SR1 - who is on the other end
# =========================================================================
def test_permitted_users_are_resolved_by_name_not_hardcoded():
    """couchd-input's uid is whatever useradd --system picked on this box."""
    uids = supervisor.allowed_uids()
    assert set(uids) <= set(supervisor.ALLOWED_USERS)
    assert all(isinstance(u, int) for u in uids.values())
    import pwd
    for name, uid in uids.items():
        assert pwd.getpwnam(name).pw_uid == uid


def test_our_own_uid_is_permitted_and_an_unknown_one_is_not():
    import pwd
    me = pwd.getpwuid(os.getuid()).pw_name
    ok, who = supervisor.peer_allowed(os.getuid(), ('root', me))
    assert ok is True and who == me
    ok, why = supervisor.peer_allowed(os.getuid(), ('root',))
    assert ok is False and str(os.getuid()) in why


def test_no_such_user_fails_closed():
    """Before stage 2's install there is no couchd-input; that must mean
    "nobody by that name may connect", never "anybody may"."""
    ok, why = supervisor.peer_allowed(os.getuid(), ('definitely-not-a-user',))
    assert ok is False
    assert 'no permitted user exists' in why


def test_an_unauthorised_peer_is_refused_and_said_out_loud(tmp_path):
    """Same mechanism the real refusal uses, driven the only way a non-root
    test can drive it: a listener that does not permit US."""
    logged = []
    li = supervisor.SupervisorListener(path=str(tmp_path / 's.sock'),
                                       allow_users=('root',),
                                       on_log=logged.append)
    assert li.start(), li.error
    try:
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.connect(li.path)
        c.sendall(supervisor.encode('press', value=1, kernel_t=1.0))
        assert wait_for(lambda: li.rejected == 1)
        assert li.connections == 0
        assert li.received == 0
        assert not li.connected
        assert any('REFUSED' in m for m in logged), logged
        c.close()
    finally:
        li.close()


def test_an_authorised_peer_is_accepted(listener):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(listener.path)
    try:
        assert wait_for(lambda: listener.connections == 1)
        assert listener.connected
        assert listener.peer['uid'] == os.getuid()
    finally:
        c.close()


# =========================================================================
# the listening end
# =========================================================================
def test_the_socket_is_group_writable_so_couchd_input_can_connect(listener):
    """~/couch/shadow's default ACL grants couchd-input rw, but a POSIX ACL's
    mask comes from the create mode's GROUP bits - bound under the usual
    umask the socket would be 0755 and the service user's connect() would get
    EACCES with nothing in any log to explain it."""
    mode = os.stat(listener.path).st_mode & 0o777
    assert mode == 0o660, oct(mode)


def test_a_malformed_line_is_counted_and_skipped_not_fatal(listener):
    """A supervisor an input process can kill by writing rubbish is not a
    supervisor. The good line after the bad ones must still arrive."""
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(listener.path)
    try:
        c.sendall(b'{"kind": "press"}\n')
        c.sendall(b'not json\n')
        c.sendall(b'\n')
        c.sendall(b'{"kind": "gesture", "event": "ps-hold"}\n')
        c.sendall(supervisor.encode('press', value=1, kernel_t=99.0))
        assert wait_for(lambda: any(m.get('kind') == 'press'
                                    for m in _peek(listener)))
        assert listener.malformed == 4
        presses = [m for m in _drained(listener) if m.get('kind') == 'press']
        assert [m['kernel_t'] for m in presses] == [99.0]
    finally:
        c.close()


_seen = {}


def _peek(li):
    """Drain into a per-listener stash so a waiter can look without losing."""
    _seen.setdefault(id(li), []).extend(li.get_all())
    return _seen[id(li)]


def _drained(li):
    out = _peek(li)
    _seen[id(li)] = []
    return out


def test_a_line_with_no_newline_in_it_cannot_grow_without_bound(listener):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(listener.path)
    try:
        c.sendall(b'x' * (supervisor.MAX_LINE + 100))
        assert wait_for(lambda: listener.malformed >= 1)
        c.sendall(supervisor.encode('press', value=0, kernel_t=1.5))
        assert wait_for(lambda: any(m.get('kind') == 'press'
                                    for m in _peek(listener)))
    finally:
        c.close()
        _drained(listener)


def test_messages_split_across_packets_are_reassembled(listener):
    line = supervisor.encode('press', value=1, kernel_t=7.25)
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(listener.path)
    try:
        for i in range(0, len(line), 3):
            c.sendall(line[i:i + 3])
            time.sleep(0.001)
        assert wait_for(lambda: any(m.get('kind') == 'press'
                                    for m in _peek(listener)))
        assert [m['kernel_t'] for m in _drained(listener)
                if m['kind'] == 'press'] == [7.25]
    finally:
        c.close()


def test_the_listener_refuses_to_steal_a_live_socket(listener, tmp_path):
    """Two daemons, one path. Unlinking blind would take the wire away from
    whoever is actually holding it."""
    second = supervisor.SupervisorListener(path=listener.path)
    assert second.start() is False
    assert 'already listening' in (second.error or '')


def test_a_stale_socket_file_is_cleared_and_rebound(sock_path):
    first = supervisor.SupervisorListener(path=sock_path)
    assert first.start()
    # Close the socket WITHOUT unlinking, the way a SIGKILL leaves it.
    first._stop.set()
    first._sock.close()
    first._sock, first.listening = None, False
    assert os.path.exists(sock_path)
    second = supervisor.SupervisorListener(path=sock_path)
    # A socket closed a moment ago still accepts for a beat, so the corpse is
    # not cold instantly. That is exactly why the check asks the socket rather
    # than the filesystem - what is being pinned here is that a LEFTOVER FILE
    # is cleared once nothing answers on it, not how fast the kernel notices.
    assert wait_for(lambda: second._stale_socket()[0] is True)
    try:
        assert second.start(), second.error
    finally:
        second.close()


# =========================================================================
# SR7 - the sending end never blocks the input fast path
# =========================================================================
def test_send_drops_instead_of_blocking_when_the_queue_is_full(sock_path):
    """The rule this whole class exists for: an input process must never
    stall because a supervisor is slow. The queue is deliberately tiny here
    and the sender thread is deliberately not running."""
    c = supervisor.SupervisorClient(path=sock_path, maxsize=4)
    c._connected.set()          # pretend the wire is up; nothing drains it
    started = time.monotonic()
    results = [c.send('press', value=i % 2, kernel_t=float(i))
               for i in range(200)]
    elapsed = time.monotonic() - started
    assert results.count(True) == 4
    assert c.drops == 196
    assert elapsed < 0.5, 'send() blocked: %.3fs for 200 calls' % elapsed
    assert c.q.qsize() == 4


def test_send_with_nobody_listening_drops_rather_than_hoarding(sock_path):
    """Queueing while disconnected would hand couchd a burst of seconds-old
    presses the moment it came back. Stale input is worse than none."""
    c = supervisor.SupervisorClient(path=sock_path, maxsize=64)
    assert c.connected is False
    for i in range(10):
        assert c.send('press', value=1, kernel_t=float(i)) is False
    assert c.drops == 10 and c.q.qsize() == 0


def test_send_never_raises_on_anything_it_is_given(sock_path):
    """It is called between a kernel event and the virtual pad."""
    c = supervisor.SupervisorClient(path=sock_path, maxsize=4)
    c._connected.set()
    assert c.send('press', value=1, kernel_t=float('nan')) is True
    assert c.send('nonsense-kind', whatever=object()) is True   # caught later


def test_the_sender_drops_a_message_it_cannot_encode(sock_path, listener):
    """An unencodable message must cost one message, not the connection."""
    c = supervisor.SupervisorClient(path=listener.path, reconnect_min=0.02,
                                    reconnect_max=0.05)
    c.start()
    try:
        assert wait_for(lambda: c.connected)
        c.q.put_nowait(('press', {'value': 'not a number', 'kernel_t': 1.0}))
        assert wait_for(lambda: c.send_failures >= 1)
        assert wait_for(lambda: c.connected)        # reconnected on its own
        c.send('press', value=1, kernel_t=42.0)
        assert wait_for(lambda: any(m.get('kernel_t') == 42.0
                                    for m in _peek(listener)))
    finally:
        c.close()
        _drained(listener)


# =========================================================================
# the two ends together
# =========================================================================
def test_client_to_listener_end_to_end(listener):
    c = supervisor.SupervisorClient(
        path=listener.path,
        on_connect=lambda: [('hello', {'pid': os.getpid(), 'version': 1,
                                       'owns_input': True})])
    c.start()
    try:
        assert wait_for(lambda: c.connected)
        for k, v in ((100.0, 1), (100.2, 0)):
            c.send('press', value=v, kernel_t=k)
        assert wait_for(lambda: len([m for m in _peek(listener)
                                     if m.get('kind') == 'press']) == 2)
        msgs = _drained(listener)
        kinds = [m['kind'] for m in msgs]
        assert kinds[0] == '_connected'
        assert 'hello' in kinds
        presses = [m for m in msgs if m['kind'] == 'press']
        assert [(m['kernel_t'], m['value']) for m in presses] == [(100.0, 1),
                                                                  (100.2, 0)]
        assert c.drops == 0
    finally:
        c.close()


def test_the_client_reconnects_after_the_listener_dies(sock_path):
    """couchd going away must not stop the pad working; it just means nobody
    is listening for a while."""
    first = supervisor.SupervisorListener(path=sock_path)
    assert first.start(), first.error
    hellos = []
    c = supervisor.SupervisorClient(
        path=sock_path, reconnect_min=0.02, reconnect_max=0.05,
        on_connect=lambda: (hellos.append(1) or
                            [('hello', {'pid': os.getpid(), 'version': 1,
                                        'owns_input': True})]))
    c.start()
    try:
        assert wait_for(lambda: c.connected)
        assert wait_for(lambda: first.connected)
        first.close()
        # It notices the moment it next tries to send, and then keeps trying.
        assert wait_for(lambda: (c.send('press', value=1, kernel_t=1.0)
                                 is False and not c.connected), timeout=5.0)
        second = supervisor.SupervisorListener(path=sock_path)
        assert second.start(), second.error
        try:
            assert wait_for(lambda: c.connected), 'never reconnected'
            assert c.connects == 2 and len(hellos) == 2
            c.send('press', value=0, kernel_t=2.0)
            assert wait_for(lambda: any(m.get('kernel_t') == 2.0
                                        for m in _peek(second)))
        finally:
            _drained(second)
            second.close()
    finally:
        c.close()


def test_whatever_piled_up_while_disconnected_is_discarded_on_reconnect(
        sock_path):
    c = supervisor.SupervisorClient(path=sock_path, maxsize=64,
                                    reconnect_min=0.02, reconnect_max=0.05)
    c._connected.set()                      # queue up as though connected...
    for i in range(10):
        c.send('press', value=1, kernel_t=float(i))
    c._connected.clear()
    assert c.q.qsize() == 10
    li = supervisor.SupervisorListener(path=sock_path)
    assert li.start(), li.error
    c.start()
    try:
        assert wait_for(lambda: c.connected)
        assert wait_for(lambda: c.q.qsize() == 0)
        assert c.drops >= 10
        c.send('press', value=0, kernel_t=999.0)
        assert wait_for(lambda: any(m.get('kind') == 'press'
                                    for m in _peek(li)))
        fresh = [m for m in _drained(li) if m['kind'] == 'press']
        assert [m['kernel_t'] for m in fresh] == [999.0], (
            'stale presses from before the reconnect reached couchd')
    finally:
        c.close()
        li.close()


# =========================================================================
# couchd's side: a second source for pad events
# =========================================================================
def build_pad(monkeypatch):
    """A PadObserver on a FakeWorld, with node discovery stubbed to nothing so
    a real DualSense on the desk cannot change what these tests see."""
    monkeypatch.setattr(PadObserver, 'find_pads', staticmethod(dict))
    w = FakeWorld()
    return w, PadObserver(w)


def strip(recs):
    """Log records minus the volatile bits, for byte-for-byte comparison."""
    return [{k: v for k, v in r.items() if k not in ('t', 'mono', 'seq')}
            for r in recs]


def test_the_wire_is_completely_inert_with_nothing_connected(monkeypatch,
                                                             sock_path):
    """THE safety property. couchd owns gestures on a real TV right now, and
    the new path must not change one record, one region or one decision until
    something authorised is on the other end of the socket.

    Two identical worlds are driven through the same button sequence; one of
    them is also listening on a socket nobody connects to. Their corpora must
    be identical.
    """
    plain_w, plain = build_pad(monkeypatch)
    wired_w, wired = build_pad(monkeypatch)
    obs = SupervisorObserver(wired_w, wired, path=sock_path)
    assert obs.start(), obs.listener.error
    try:
        for k, value in ((1000.0, 1), (1000.2, 0), (1000.4, 1), (1001.6, 0)):
            plain.note_button(k, value)
            obs.drain()
            wired.note_button(k, value)
            obs.drain()
        assert strip(wired_w.log.recs) == strip(plain_w.log.recs)
        assert wired_w.attentions == plain_w.attentions
        assert wired.supervised is False
        assert wired.present == plain.present
        assert wired.tracker.presses == plain.tracker.presses
        assert wired.tracker.press_duration == plain.tracker.press_duration
        assert obs.events == 0 and obs.messages == 0
        st = obs.status()
        assert st['connected'] is False and st['events'] == 0
        assert st['listening'] is True and st['last_event_age_s'] is None
    finally:
        obs.close()


def test_a_pad_observer_with_no_supervisor_object_at_all_is_unchanged(
        monkeypatch):
    """The defaults, on their own: a PadObserver nobody ever hands a wire to
    reports its own evdev truth and writes no `via` key."""
    w, pad = build_pad(monkeypatch)
    assert pad.supervised is False and pad.present is False
    pad._present = True
    assert pad.present is True
    pad.note_button(500.0, 1)
    rec = [r for r in w.log.recs if r.get('event') == 'BTN_MODE'][0]
    assert 'via' not in rec, 'the evdev corpus grew a key it never had'


def test_a_press_over_the_wire_reaches_the_press_tracker(monkeypatch,
                                                         sock_path):
    w, pad = build_pad(monkeypatch)
    obs = SupervisorObserver(w, pad, path=sock_path)
    assert obs.start(), obs.listener.error
    c = supervisor.SupervisorClient(path=sock_path)
    c.start()
    try:
        assert wait_for(lambda: c.connected)
        c.send('pad', state='attached', node='/dev/input/event21')
        c.send('press', value=1, kernel_t=2000.0)
        c.send('press', value=0, kernel_t=2000.25)
        assert wait_for(lambda: (obs.drain(), obs.events)[1] == 2)
        assert pad.supervised is True
        assert pad.present is True, 'the pad region must follow the wire'
        assert pad.tracker.presses == 1
        assert pad.tracker.press_duration == pytest.approx(0.25)
        btn = [r for r in w.log.recs if r.get('event') == 'BTN_MODE']
        assert [r['via'] for r in btn] == ['supervisor', 'supervisor']
        assert [r['value'] for r in btn] == [1, 0]
        assert [r['kernel_t'] for r in btn] == [2000.0, 2000.25]
        # The gesture edge still fires: a press over the wire is decided now,
        # not at the next 5s tick (R5).
        assert [a['reason'] for a in w.attentions].count('ps-button') == 2
        assert all(a['edge'] for a in w.attentions if a['reason'] == 'ps-button')
    finally:
        c.close()
        obs.close()


def test_the_wire_and_evdev_reach_the_same_verdict(monkeypatch, sock_path):
    """SR4 across the wire: the same kernel timestamps, classified by two
    PressTrackers that were fed through the two different channels, must come
    out as the same gesture. This is the whole reason the wire carries
    timestamps rather than the word 'hold'."""
    seq = ((3000.0, 1), (3000.85, 0),          # a tap (under 0.9)
           (3001.0, 1), (3002.2, 0))           # a hold
    direct_w, direct = build_pad(monkeypatch)
    for k, v in seq:
        direct.note_button(k, v)

    wired_w, wired = build_pad(monkeypatch)
    obs = SupervisorObserver(wired_w, wired, path=sock_path)
    assert obs.start(), obs.listener.error
    c = supervisor.SupervisorClient(path=sock_path)
    c.start()
    try:
        assert wait_for(lambda: c.connected)
        for k, v in seq:
            c.send('press', value=v, kernel_t=k)
        assert wait_for(lambda: (obs.drain(), obs.events)[1] == len(seq))
        assert wired.tracker.presses == direct.tracker.presses
        assert wired.tracker.press_duration == direct.tracker.press_duration
        assert wired.tracker.doubles == direct.tracker.doubles
        assert wired.hold_release_pending == direct.hold_release_pending
        assert [r['value'] for r in wired_w.log.recs
                if r.get('event') == 'BTN_MODE'] == [v for _, v in seq]
    finally:
        c.close()
        obs.close()


def test_a_detached_pad_over_the_wire_clears_the_region_and_the_press(
        monkeypatch, sock_path):
    w, pad = build_pad(monkeypatch)
    obs = SupervisorObserver(w, pad, path=sock_path)
    assert obs.start(), obs.listener.error
    c = supervisor.SupervisorClient(path=sock_path)
    c.start()
    try:
        assert wait_for(lambda: c.connected)
        c.send('pad', state='attached', node='/dev/input/event21')
        c.send('press', value=1, kernel_t=4000.0)
        assert wait_for(lambda: (obs.drain(), pad.tracker.button_down)[1])
        c.send('pad', state='detached', why='eof')
        assert wait_for(lambda: (obs.drain(), pad.present)[1] is False)
        assert pad.tracker.button_down is False, (
            'a pad that went away must take its in-flight press with it')
        assert pad.tracker.down_since_k is None
    finally:
        c.close()
        obs.close()


def test_a_disconnect_hands_the_pad_region_back_to_our_own_eyes(monkeypatch,
                                                                sock_path):
    w, pad = build_pad(monkeypatch)
    obs = SupervisorObserver(w, pad, path=sock_path)
    assert obs.start(), obs.listener.error
    c = supervisor.SupervisorClient(path=sock_path)
    c.start()
    try:
        assert wait_for(lambda: c.connected)
        c.send('pad', state='attached', node='/dev/input/event21')
        assert wait_for(lambda: (obs.drain(), pad.supervised)[1])
        c.close()
        # The peer vanishing and the record of it are two separate moments -
        # `connected` goes false when the reader thread unwinds, the record
        # arrives through the queue - so wait for the later of the two.
        assert wait_for(lambda: (obs.drain(),
                                 any(r.get('event') == 'disconnected'
                                     for r in w.log.recs))[1])
        obs.drain()
        assert pad.supervised is False
        assert pad.supervised_present is False
        assert pad.present is False       # which is what evdev says: no nodes
    finally:
        obs.close()


def test_the_peer_drop_count_reaches_status(monkeypatch, sock_path):
    """SR7's cost, visible where the health check looks. A non-zero count
    means couchd's view of the button has holes in it."""
    w, pad = build_pad(monkeypatch)
    obs = SupervisorObserver(w, pad, path=sock_path)
    assert obs.start(), obs.listener.error
    c = supervisor.SupervisorClient(path=sock_path)
    c.start()
    try:
        assert wait_for(lambda: c.connected)
        c.send('hello', pid=os.getpid(), version=1, owns_input=True)
        c.send('health', drops=17, owns_input=True, state='owned')
        c.send('press', value=1, kernel_t=5000.0)
        assert wait_for(lambda: (obs.drain(), obs.peer_drops)[1] == 17)
        st = obs.status()
        assert st['peer_drops'] == 17
        assert st['connected'] is True and st['peer_owns_input'] is True
        assert st['peer_pid'] == os.getpid()
        assert st['last_event_age_s'] is not None
        assert st['rejected'] == 0 and st['malformed'] == 0
        # ...and it is JSON, because status.json is written with json.dumps.
        json.dumps(st)
    finally:
        c.close()
        obs.close()


def test_a_listener_that_cannot_bind_is_a_note_not_a_crash(monkeypatch,
                                                           tmp_path):
    w, pad = build_pad(monkeypatch)
    obs = SupervisorObserver(w, pad,
                             path=str(tmp_path / 'no' / 'such' / 'dir.sock'))
    assert obs.start() is False
    obs.drain()                                  # still safe to call
    assert pad.supervised is False
    assert obs.status()['listening'] is False
    assert any(r.get('kind') == 'observer_blind' for r in w.log.recs)


def build_daemon(tmp_path, monkeypatch):
    """A real Couchd with every path it writes redirected into tmp_path.
    Same recipe as test_edge.py's fixture; nothing here starts its loop."""
    for name, value in (('SHADOW_DIR', str(tmp_path)),
                        ('TMP_DIR', str(tmp_path)),
                        ('SESSION_FLAG', str(tmp_path / 'game-session')),
                        ('SUSPENDED_FLAG', str(tmp_path / 'game-suspended')),
                        ('GUARD_PIDFILE', str(tmp_path / 'guard.pid')),
                        ('GAMEPROCESS_LOG', str(tmp_path / 'gp.txt')),
                        ('CONTROLLER_UI_LOG', str(tmp_path / 'cui.txt')),
                        ('LOCK_PATH', str(tmp_path / 'couchd.lock'))):
        monkeypatch.setattr(couchd, name, value)
    monkeypatch.setattr(PadObserver, 'find_pads', staticmethod(dict))
    return couchd.Couchd()


def test_constructing_the_daemon_binds_no_socket(tmp_path, monkeypatch):
    """Importing or instantiating couchd must never open a listening socket:
    the test suite, the replay tools and the differ all construct one."""
    d = build_daemon(tmp_path, monkeypatch)
    assert d.supervisor.started is False
    assert d.supervisor.listener.listening is False
    assert not os.path.exists(str(tmp_path / 'couchd.sock'))
    assert d.pad.supervised is False
    d.log.close()
    d.snapshots.close()


def test_status_json_carries_the_wire_and_reads_inert(tmp_path, monkeypatch):
    """What the health check looks at. With nothing connected it must say so
    plainly rather than looking like a healthy supervised console."""
    d = build_daemon(tmp_path, monkeypatch)
    try:
        assert d.supervisor.start(), d.supervisor.listener.error
        assert os.path.exists(str(tmp_path / 'couchd.sock'))
        d.write_status(couchd.make_obs())
        status = json.loads((tmp_path / 'status.json').read_text())
        wire = status['supervisor']
        assert wire['listening'] is True and wire['connected'] is False
        assert wire['events'] == 0 and wire['drops'] == 0
        assert wire['peer_drops'] == 0 and wire['rejected'] == 0
        assert wire['last_event_age_s'] is None
        assert status['regions']['pad'] == 'present'   # unchanged by the wire
        assert status['observers']['supervisor']['ok'] is True
    finally:
        d.supervisor.close()
        d.log.close()
        d.snapshots.close()


def test_the_daemon_start_record_names_input_for_the_differ(tmp_path,
                                                            monkeypatch):
    """`input` is never in `owns` (couchd cannot execute it), so without the
    declared list the morning differ reads a flipped input evening as one
    that was never flipped."""
    d = build_daemon(tmp_path, monkeypatch)
    try:
        d.write_status(couchd.make_obs())
        status = json.loads((tmp_path / 'status.json').read_text())
        assert 'owns_declared' in status
        # ...and the same pair on the record shadow-diff actually reads.
        import owns as ownsmod
        d.executor.log = FakeLog()
        d.executor.set_owns(ownsmod.parse('COUCHD_OWNS=gestures,input'))
        rec = [r for r in d.executor.log.recs
               if r.get('event') == 'owns-changed'][-1]
        assert rec['now'] == ['gestures'], 'couchd cannot execute input'
        assert rec['now_declared'] == ['gestures', 'input']
    finally:
        d.log.close()
        d.snapshots.close()


# =========================================================================
# inputproc's side
# =========================================================================
class RecordingWire:
    """Stands in for SupervisorClient, recording what the fast path sent."""

    def __init__(self):
        self.msgs = []
        self.path = '/nowhere'
        self.last_error = None

    def send(self, kind, **fields):
        self.msgs.append((kind, fields))
        return True

    def stats(self):
        return {'connected': True, 'drops': 0, 'sent': len(self.msgs),
                'connects': 1, 'send_failures': 0, 'error': None,
                'queued': 0, 'path': self.path}

    def start(self):
        pass

    def close(self):
        pass


def build_proc(tmp_path, own):
    args = inputproc.parse_args(['--log-dir', str(tmp_path),
                                 '--supervisor-sock',
                                 str(tmp_path / 'couchd.sock')])
    args.own_input = own
    proc = inputproc.InputProc(args)
    proc.own = own
    proc.wire = RecordingWire()
    return proc


def test_both_edges_of_a_press_go_on_the_wire_while_owning(tmp_path):
    """couchd runs its own PressTracker, and a tracker fed only the presses
    computes nothing. report() names the release as a classified gesture and
    never as an edge, so the wire has to carry it from on_guide."""
    proc = build_proc(tmp_path, own=True)
    proc.on_guide(6000.0, 1, 6000, 0)
    proc.on_guide(6000.2, 0, 6000, 200000)
    assert [(k, f['value'], f['kernel_t']) for k, f in proc.wire.msgs] == [
        ('press', 1, 6000.0), ('press', 0, 6000.2)]


def test_the_wire_carries_no_classification_ever(tmp_path):
    """THE load-bearing decision. If a gesture name ever appears on this wire,
    couchd has stopped deciding and the shadow corpus is comparing a stack
    against itself."""
    proc = build_proc(tmp_path, own=True)
    proc.on_guide(7000.0, 1, 7000, 0)          # down
    proc.poll_hold(time.monotonic())           # may announce ps-hold
    proc.on_guide(7002.0, 0, 7002, 0)          # a hold release
    kinds = {k for k, _ in proc.wire.msgs}
    assert kinds == {'press'}, kinds
    blob = json.dumps(proc.wire.msgs, default=str)
    for word in ('ps-tap', 'ps-hold', 'ps-double-tap', 'ps-long-hold',
                 'gesture'):
        assert word not in blob, ('%r reached the supervisor wire' % word)
    # ...and the classification is still in the JSONL, which is the evidence.
    gestures = [r for r in _jsonl(tmp_path) if r.get('kind') == 'gesture']
    assert gestures, 'the evidence trail lost the classified gesture'


def test_observe_mode_reports_the_button_too(tmp_path):
    """Not owning the pad does not mean not observing it: couchd should get
    the same edges either way, so a shadow evening and an owning one produce
    the same corpus shape."""
    proc = build_proc(tmp_path, own=False)
    proc.on_guide(8000.0, 1, 8000, 0)
    proc.on_guide(8000.1, 0, 8000, 100000)
    assert [f['value'] for k, f in proc.wire.msgs if k == 'press'] == [1, 0]


def test_report_writes_the_jsonl_and_touches_no_socket(tmp_path):
    """report()'s signature and its JSONL behaviour are unchanged; the wire
    is additional, not a replacement."""
    proc = build_proc(tmp_path, own=True)
    proc.report('gesture', event='ps-tap', held=0.2, kernel_t=1.0)
    assert proc.wire.msgs == []
    recs = [r for r in _jsonl(tmp_path) if r.get('kind') == 'gesture']
    assert recs[-1]['event'] == 'ps-tap'
    assert recs[-1]['owns_input'] is True


def test_the_health_tick_carries_the_drop_count(tmp_path):
    proc = build_proc(tmp_path, own=True)
    proc.health(time.monotonic())
    rec = [r for r in _jsonl(tmp_path) if r.get('event') == 'tick'][-1]
    assert 'wire' in rec and 'drops' in rec['wire']
    assert ('health', ) in [(k, ) for k, _ in proc.wire.msgs]


def test_the_resync_tells_a_restarted_couchd_about_the_pad(tmp_path):
    """couchd restarts; inputproc reconnects. Without this the daemon's `pad`
    region sits on whatever it last believed until the pad is next unplugged.
    """
    proc = build_proc(tmp_path, own=True)
    kinds = [k for k, _ in proc.wire_resync()]
    assert kinds == ['hello', 'pad']
    assert dict(proc.wire_resync())['pad']['state'] == 'detached'
    proc.phys, proc.phys_path, proc.grabbed = object(), '/dev/input/event9', True
    pad = dict(proc.wire_resync())['pad']
    assert pad['state'] == 'attached' and pad['node'] == '/dev/input/event9'
    for kind, fields in proc.wire_resync():     # every one of them is legal
        supervisor.decode(supervisor.encode(kind, **fields))


def test_the_stub_interlock_is_gone_and_the_rig_escape_is_not(tmp_path):
    """main() no longer refuses on the SHAPE of report(); run() refuses on the
    world - no listener, no grab - and the rig flag still exists."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'inputproc.py')).read()
    assert 'still a\n            stub' not in src
    assert 'supervisor wire is still a stub' not in src
    assert '--supervisor-stub-ok' in src
    assert 'wait_connected' in src, 'the startup interlock disappeared'


def _jsonl(directory):
    path = os.path.join(directory, 'inputproc-%s.jsonl'
                        % time.strftime('%Y%m%d'))
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


# =========================================================================
# threads, tidied up
# =========================================================================
def test_no_supervisor_threads_are_left_running(sock_path):
    """A listener or client that leaks a thread per connection would take the
    daemon down over an evening."""
    before = threading.active_count()
    li = supervisor.SupervisorListener(path=sock_path)
    assert li.start(), li.error
    c = supervisor.SupervisorClient(path=sock_path)
    c.start()
    assert wait_for(lambda: c.connected and li.connected)
    c.close()
    li.close()
    assert wait_for(lambda: threading.active_count() <= before, timeout=5.0), (
        'threads left over: %d -> %d' % (before, threading.active_count()))
