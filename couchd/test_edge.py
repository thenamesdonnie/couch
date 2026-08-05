#!/usr/bin/env python3
"""The gesture edge (R5) and the x11 observer's event integration.

Two things are pinned here:

  * a PS-button edge produces a DECISION without waiting for the 5s tick, and
    the latency from the edge to that decision is in the corpus - measured
    p95 was 1.4s against a 250ms perceptual bound, which is the whole reason
    the edge path exists;
  * couchd's x11 observer counts events from BOTH acquisition paths (the
    asyncio reader and the scan's own drain) and survives an X that dies.

Nothing here touches the real X server, Kodi, Steam, /tmp or ~/couch/shadow:
every path the daemon writes is redirected into tmp_path first (a test that
sprays the live /tmp/couchd.log is destroying the evening's evidence).

    .venv/bin/python -m pytest test_edge.py -q
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import couchd
from couchd import (ATTENTION_PERIOD, EDGE_DEBOUNCE, HANDOFF_TIMEOUT,
                    MIN_PERIOD, TICK_SECONDS, Couchd, World, make_obs)


# =========================================================================
# World.attention: edges, coalescing, single delivery
# =========================================================================
class NullLog:
    def __init__(self):
        self.recs = []
        self.counts = {}

    def write(self, rec):
        self.recs.append(rec)


def test_a_plain_attention_is_not_an_edge():
    w = World(NullLog())
    w.attention('steam-log')
    assert w.edge_pending is False
    assert w.take_edge() is None
    assert w.wake.is_set(), 'it still wakes the loop, as it always did'


def test_a_ps_button_edge_is_pending_until_a_pass_takes_it():
    w = World(NullLog())
    w.attention('ps-button', edge=True, kernel_t=12345.5)
    assert w.edge_pending
    edge = w.take_edge()
    assert edge['reason'] == 'ps-button' and edge['kernel_t'] == 12345.5
    assert w.edge_pending is False, 'exactly one pass ever sees an edge'
    assert w.take_edge() is None


def test_edges_inside_one_pass_coalesce_onto_the_oldest():
    """A press and its release land tens of ms apart and are one decision;
    the latency that matters is the OLDEST undecided edge's."""
    w = World(NullLog())
    w.attention('ps-button', edge=True, kernel_t=100.0)
    first = dict(w.edge)
    w.attention('ps-button', edge=True, kernel_t=100.08)
    edge = w.take_edge()
    assert edge['mono'] == first['mono'], 'the clock starts at the first edge'
    assert edge['coalesced'] == 1
    assert edge['kernel_t'] == 100.08, 'but the newest kernel stamp is kept'
    assert w.edges == 2 and w.edges_coalesced == 1


# =========================================================================
# the pacing rule
# =========================================================================
def daemon(tmp_path, monkeypatch):
    """A real Couchd with every path it writes redirected into tmp_path."""
    monkeypatch.setattr(couchd, 'SHADOW_DIR', str(tmp_path))
    monkeypatch.setattr(couchd, 'HUMAN_LOG', str(tmp_path / 'couchd.log'))
    monkeypatch.setattr(couchd, 'TMP_DIR', str(tmp_path))
    monkeypatch.setattr(couchd, 'SESSION_FLAG', str(tmp_path / 'game-session'))
    monkeypatch.setattr(couchd, 'SUSPENDED_FLAG',
                        str(tmp_path / 'game-suspended'))
    monkeypatch.setattr(couchd, 'GUARD_PIDFILE',
                        str(tmp_path / 'steam-input-guard.pid'))
    monkeypatch.setattr(couchd, 'GAMEPROCESS_LOG', str(tmp_path / 'gp.txt'))
    monkeypatch.setattr(couchd, 'CONTROLLER_UI_LOG', str(tmp_path / 'cui.txt'))
    monkeypatch.setattr(couchd, 'LOCK_PATH', str(tmp_path / 'couchd.lock'))
    monkeypatch.setattr(couchd, 'notify', lambda state: None)
    d = Couchd()
    # Nothing may reach the live console: Kodi's notification socket, the pad
    # nodes and X are all stubbed out. The LOOP is the thing under test.
    async def forever(*a, **kw):
        await asyncio.sleep(3600)
    d.kodi.run_notifications = forever
    d.pad.run = forever
    d.flags.run = forever

    async def nopoll():
        return None
    d.kodi.poll = nopoll
    d.steam.poll = lambda: False
    d.triggers.poll = lambda: False
    d.x11.poll = lambda loop: None
    d.x11.attach = lambda loop: None
    d.x11.close = lambda loop: None
    return d


def test_an_edge_runs_a_pass_without_waiting_for_the_tick(tmp_path,
                                                          monkeypatch):
    """The requirement in one line: press the button, get a pass - not in
    5 seconds, not in 200ms, but in the debounce."""
    d = daemon(tmp_path, monkeypatch)
    passes = []
    real = d.pass_once

    def spy(loop):
        started = time.monotonic()
        out = real(loop)            # pass_once claims the edge on entry
        passes.append((started, d.edge))
        return out
    d.pass_once = spy

    async def drive():
        task = asyncio.create_task(d.run())
        await asyncio.sleep(0.3)          # settle: first pass, then the wait
        n_before = len(passes)
        fired = time.monotonic()
        d.world.attention('ps-button', edge=True, kernel_t=time.time())
        await asyncio.sleep(EDGE_DEBOUNCE + 0.15)
        d.stop.set()
        d.world.wake.set()
        await asyncio.wait_for(task, 5)
        return n_before, fired

    n_before, fired = asyncio.run(drive())
    after = [p for p in passes[n_before:]]
    assert after, 'the edge produced no pass at all'
    latency = after[0][0] - fired
    assert latency >= EDGE_DEBOUNCE * 0.8, 'the debounce still coalesces'
    assert latency < 0.25, f'edge-to-pass was {latency:.3f}s (bound 250ms)'
    assert latency < MIN_PERIOD and latency < TICK_SECONDS
    assert after[0][1] is not None, 'the pass was handed the edge'
    assert after[0][1]['reason'] == 'ps-button'


def test_the_watchdog_and_the_slow_tick_are_not_starved_by_edges(tmp_path,
                                                                 monkeypatch):
    """A spammed PS button must not push the anti-entropy tick or the
    watchdog ping out: both are keyed off elapsed time, never off how the
    pass was triggered."""
    d = daemon(tmp_path, monkeypatch)
    monkeypatch.setattr(couchd, 'TICK_SECONDS', 0.2)
    pings = []
    monkeypatch.setattr(couchd, 'notify',
                        lambda state: pings.append(state) if state == 'WATCHDOG=1'
                        else None)
    ticks = []
    real = d.anti_entropy
    d.anti_entropy = lambda o: (ticks.append(time.monotonic()), real(o))[1]

    async def drive():
        task = asyncio.create_task(d.run())
        end = time.monotonic() + 0.8
        while time.monotonic() < end:      # a burst, faster than the debounce
            d.world.attention('ps-button', edge=True, kernel_t=time.time())
            await asyncio.sleep(0.01)
        d.stop.set()
        d.world.wake.set()
        await asyncio.wait_for(task, 5)

    asyncio.run(drive())
    assert len(ticks) >= 2, 'the slow tick kept running under a press burst'
    assert len(pings) >= 5, 'the watchdog was pinged every pass'


def test_the_edge_debounce_is_a_floor_the_loop_cannot_spin_through(tmp_path,
                                                                   monkeypatch):
    d = daemon(tmp_path, monkeypatch)

    async def drive():
        d.stop = asyncio.Event()
        d.world.attention('ps-button', edge=True)
        t0 = time.monotonic()
        await d._sleep_until_next(t0)
        return time.monotonic() - t0

    took = asyncio.run(drive())
    assert took >= EDGE_DEBOUNCE * 0.8
    assert took < ATTENTION_PERIOD + 0.05


def test_without_an_edge_the_old_pacing_is_untouched(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)

    async def drive():
        d.stop = asyncio.Event()
        d.world.attention('steam-log')          # attentive, but not an edge
        t0 = time.monotonic()
        await d._sleep_until_next(t0)
        return time.monotonic() - t0

    took = asyncio.run(drive())
    assert took >= ATTENTION_PERIOD * 0.8, 'the attention floor still applies'


# =========================================================================
# gesture deadlines: the edges with no event behind them
# =========================================================================
def test_the_hold_threshold_is_a_deadline_the_sleeper_wakes_on(tmp_path,
                                                               monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    o = make_obs(button_down=True, down_since_k=500.0, kernel_now=500.6)
    due = d.gesture_deadline(o)
    assert due == pytest.approx(0.3, abs=0.01), '0.9s hold, 0.6s in'
    # ...and it caps the sleep, instead of the 5s tick doing it
    assert due < TICK_SECONDS


def test_the_double_tap_window_is_a_deadline_too(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    o = make_obs(mono=1000.2, regions={'gesture': 'tap-wait'},
                 region_since={'gesture': 1000.0})
    assert d.gesture_deadline(o) == pytest.approx(0.15, abs=0.01)


def test_the_handoff_timeout_is_a_deadline_too(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    o = make_obs(mono=1001.0, regions={'gesture': 'handoff-pending'},
                 region_since={'gesture': 1000.0})
    assert d.gesture_deadline(o) == pytest.approx(HANDOFF_TIMEOUT - 1.0,
                                                  abs=0.01)


def test_a_quiet_gesture_region_has_no_deadline(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    assert d.gesture_deadline(make_obs()) is None
    assert d.gesture_deadline(None) is None


def test_an_unbound_hold_does_not_schedule_its_own_threshold(tmp_path,
                                                             monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    from gestureconf import DEFAULT_BINDINGS
    o = make_obs(button_down=True, down_since_k=500.0, kernel_now=500.6,
                 bindings=dict(DEFAULT_BINDINGS, hold='none'))
    assert d.gesture_deadline(o) is None, 'nothing fires at 0.9s any more'


# =========================================================================
# the instrumentation itself
# =========================================================================
def test_an_intent_decided_on_an_edge_carries_its_latency(tmp_path,
                                                          monkeypatch):
    """The field the differ's offset distribution is checked against."""
    d = daemon(tmp_path, monkeypatch)
    d.world.attention('ps-button', edge=True, kernel_t=time.time() - 0.05)
    d.edge = d.world.take_edge()
    o = make_obs()
    d.recorder.execute(couchd.Intent('show', 'kodi', {'via': 'xlib-restack'},
                                     'gesture:ps-hold'), o)
    rec = json.loads(open(tmp_path / f'couchd-{time.strftime("%Y%m%d")}.jsonl')
                     .read().strip().splitlines()[-1])
    assert rec['trigger'] == 'edge'
    assert rec['edge']['reason'] == 'ps-button'
    assert rec['edge']['edge_seq'] == 1
    assert 0 <= rec['edge_latency_s'] < 1.0
    assert rec['edge_kernel_latency_s'] >= 0.0


def test_an_intent_decided_on_the_tick_says_so(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    d.edge = None
    d.recorder.execute(couchd.Intent('show', 'kodi', {}, 'reconcile:drift'),
                       make_obs())
    rec = json.loads(open(tmp_path / f'couchd-{time.strftime("%Y%m%d")}.jsonl')
                     .read().strip().splitlines()[-1])
    assert rec['trigger'] == 'tick'
    assert 'edge_latency_s' not in rec


def test_every_decided_edge_leaves_one_latency_record(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    d.edge = {'reason': 'ps-button', 'mono': time.monotonic() - 0.07,
              'kernel_t': None, 'seq': 3}
    o = make_obs()
    d.log_edge(o, [couchd.Intent('show', 'kodi', {}, 'gesture:ps-hold')])
    rec = json.loads(open(tmp_path / f'couchd-{time.strftime("%Y%m%d")}.jsonl')
                     .read().strip().splitlines()[-1])
    assert rec['kind'] == 'latency' and rec['event'] == 'gesture-edge'
    assert rec['edge_seq'] == 3, 'the log owns `seq`; the edge keeps its own'
    assert rec['decide_latency_s'] >= 0.06
    assert rec['intents'] == ['show|kodi|gesture:ps-hold']
    assert d.last_edge_latency == rec['decide_latency_s']


def test_a_tick_pass_writes_no_latency_record(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    d.edge = None
    d.log_edge(make_obs(), [])
    path = tmp_path / f'couchd-{time.strftime("%Y%m%d")}.jsonl'
    body = path.read_text() if path.exists() else ''
    assert 'gesture-edge' not in body


# =========================================================================
# the x11 observer's two acquisition paths, at the daemon level
# =========================================================================
class FakeAdapter:
    def __init__(self):
        self.d = object()
        self.events = 0
        self.pending = 0
        self.arriving = 0
        self.state = type('S', (), {'ok': True, 'reason': '', 'top_name': 'Kodi',
                                    'top_class': 'Kodi', 'focused_class': 'Kodi',
                                    'kodi_present': True, 'big_picture': False,
                                    'game_windows': (), 'n_windows': 3,
                                    'atoms': {}})()
        self.display_name = ':99'

    def fileno(self):
        return 41

    def connect(self):
        return True

    # the real adapter's semantics: drain() ACCUMULATES, take_events() claims
    def drain(self):
        n, self.pending = self.pending, self.pending + self.arriving
        self.arriving = 0
        self.events += self.pending - n
        return self.pending - n

    def take_events(self):
        n, self.pending = self.pending, 0
        return n

    def refresh(self):
        self.drain()                # the real adapter drains around its scan
        return self.state

    def close(self):
        self.d = None


def observer(tmp_path, monkeypatch):
    monkeypatch.setattr(couchd, 'SHADOW_DIR', str(tmp_path))
    monkeypatch.setattr(couchd, 'HUMAN_LOG', str(tmp_path / 'couchd.log'))
    w = World(NullLog())
    obs = couchd.X11Observer(w)
    obs.adapter = FakeAdapter()
    return obs, w


def test_the_event_path_counts_and_wakes(tmp_path, monkeypatch):
    obs, w = observer(tmp_path, monkeypatch)
    obs.adapter.arriving = 3
    obs._readable(loop=None)
    assert w.src('x11').events == 3
    obs.poll(loop=None)
    assert w.src('x11').events == 3, 'the poll must not count them again'
    assert w.attention_reason == 'x11-event'
    assert w.edge_pending is False, 'a window change is not a gesture edge'


def test_the_poll_path_counts_what_the_scan_swallowed(tmp_path, monkeypatch):
    """The whole 4-5 Aug bug, at the observer level: these events never made
    the fd readable, so only the post-scan drain can find them."""
    obs, w = observer(tmp_path, monkeypatch)
    obs.adapter.arriving = 5
    obs.poll(loop=None)
    assert w.src('x11').events == 5
    assert w.src('x11').ok


def test_the_observer_gives_the_corpus_an_x11_channel(tmp_path, monkeypatch):
    obs, w = observer(tmp_path, monkeypatch)
    obs.poll(loop=None)
    recs = [r for r in w.log.recs if r.get('source') == 'x11']
    assert recs and recs[0]['event'] == 'screen'
    assert recs[0]['top'] == ['Kodi', 'Kodi']
    n = len(w.log.recs)
    obs.poll(loop=None)
    assert len(w.log.recs) == n, 'an unchanged screen is not news'
    obs.adapter.state.top_name = 'ELDEN RING'
    obs._last_log -= 2.0
    obs.poll(loop=None)
    assert len(w.log.recs) == n + 1, '...a changed one is'


def test_a_dead_display_marks_the_observer_blind_and_never_raises(tmp_path,
                                                                  monkeypatch):
    obs, w = observer(tmp_path, monkeypatch)

    def die():
        obs.adapter.d = None
        obs.adapter.state.reason = 'drain: IOError: Broken pipe'
        return 0
    obs.adapter.drain = die
    obs._readable(loop=None)
    assert w.src('x11').ok is False
    assert 'Broken pipe' in w.src('x11').detail


def test_reconnect_backs_off_and_resets(tmp_path, monkeypatch):
    obs, w = observer(tmp_path, monkeypatch)
    obs.adapter.connect = lambda: False
    obs._load = lambda: obs.adapter
    waits = []
    for _ in range(4):
        obs._next_connect = 0.0
        obs.attach(loop=None)
        waits.append(obs._next_connect - time.monotonic())
    assert waits == sorted(waits), f'backoff must not shrink: {waits}'
    assert waits[-1] > waits[0]
    assert waits[-1] <= max(couchd.X11Observer.BACKOFF) + 0.1
    assert w.src('x11').ok is False
    # ...and a successful connect forgets it
    obs.adapter.connect = lambda: True
    obs._next_connect = 0.0
    obs.attach(loop=None)
    assert obs._fails == 0


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
