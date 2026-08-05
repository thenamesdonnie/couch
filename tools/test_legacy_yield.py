#!/usr/bin/env python3
"""Does the OLD stack yield exactly what couchd was given, and nothing else?

These tests import the two live scripts (~/.local/bin/pad-home-watcher and
~/.local/bin/steam-input-guard) as modules and drive their decision points with
every side effect replaced by a recorder: no signals, no Kodi, no X, no vpad,
no real /tmp (the logs, the intent stream, the flags and owns.conf all live
under tmp_path).

Two properties are pinned, and they are the two that keep the console safe:

  1. with owns.conf EMPTY every path behaves exactly as it did before the
     switch existed - the effects still fire and the intent lines carry no
     `yielded` marker;
  2. with a responsibility named, the effects do NOT fire, the decision is
     still written to the intent stream (legacy becomes the shadow), and
     nothing signals a process or claims the guard pidfile.

Run:  couchd/.venv/bin/pytest tools/test_legacy_yield.py -q
"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import time

import pytest

HOME = os.path.expanduser('~')
WATCHER_SRC = os.path.join(HOME, '.local/bin/pad-home-watcher')
GUARD_SRC = os.path.join(HOME, '.local/bin/steam-input-guard')
pytestmark = pytest.mark.skipif(
    not (os.path.exists(WATCHER_SRC) and os.path.exists(GUARD_SRC)),
    reason='the legacy scripts are not installed on this box')

sys.path.insert(0, os.path.join(HOME, 'couch', 'couchd'))
import owns                                                   # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


watcher = _load('pad_home_watcher', WATCHER_SRC)
guard = _load('steam_input_guard_yield', GUARD_SRC)


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A whole fake console: paths under tmp_path, owns.conf switchable."""
    conf = tmp_path / 'owns.conf'
    conf.write_text('COUCHD_OWNS=""\n')
    monkeypatch.setenv('COUCHD_OWNS_FILE', str(conf))
    # couchd's heartbeat, ours to age at will - never the live daemon's, or
    # these tests would pass or fail depending on whether couchd is running.
    status = tmp_path / 'status.json'
    status.write_text('{"mode": "acting"}')
    monkeypatch.setenv('COUCHD_STATUS_FILE', str(status))
    owns._cache.clear()
    for mod in (watcher, guard):
        monkeypatch.setattr(mod, 'LOG', str(tmp_path / 'legacy.log'))
        monkeypatch.setattr(mod, 'INTENTS', str(tmp_path / 'intents.jsonl'))
        monkeypatch.setattr(mod, 'SUSPENDED', str(tmp_path / 'game-suspended'))
    monkeypatch.setattr(watcher, 'SESSION', str(tmp_path / 'game-session'))
    monkeypatch.setattr(guard, 'SESSION', str(tmp_path / 'game-session'))
    monkeypatch.setattr(guard, 'PIDFILE', str(tmp_path / 'guard.pid'))
    monkeypatch.setattr(watcher, 'GUARD_PIDFILE', str(tmp_path / 'guard.pid'))
    watcher._owns_said[0] = None
    watcher._heartbeat_said[0] = None

    class Box:
        dir = tmp_path
        owns_file = conf
        status_file = status

        @staticmethod
        def own(*names):
            conf.write_text('COUCHD_OWNS="%s"\n' % ','.join(names))
            owns._cache.clear()

        @staticmethod
        def age_heartbeat(seconds):
            """Pretend couchd last wrote status.json `seconds` ago - which is
            what `systemctl --user stop couchd` looks like from out here."""
            when = time.time() - seconds
            os.utime(status, (when, when))

        @staticmethod
        def stop_couchd():
            status.unlink()

        @staticmethod
        def intents():
            path = tmp_path / 'intents.jsonl'
            if not path.exists():
                return []
            return [json.loads(l) for l in path.read_text().splitlines() if l]

        @staticmethod
        def verbs():
            return [(i['verb'], i['subject']) for i in Box.intents()]

    return Box


class Conf:
    """The bindings object the watcher's act() takes."""

    def __init__(self, **b):
        self.bindings = dict(watcher.DEFAULT_BINDINGS, **b)
        self.hold_seconds = 0.9
        self.double_tap_seconds = 0.35
        self.long_hold_seconds = 3.0

    def action_for(self, gesture):
        return self.bindings.get(gesture, 'none')


@pytest.fixture
def spy(monkeypatch):
    """Every effect either script can have, replaced by a recorder."""
    calls = []

    def rec(name):
        def f(*a, **kw):
            calls.append((name, a, kw))
            return None
        return f

    for name in ('act_suspend', 'act_switcher', 'act_steam_menu',
                 'act_power_menu', 'act_quit_game', 'act_tv_toggle',
                 'act_desktop', 'set_joystick', 'clear_snapshots',
                 'iconify_frozen_game', 'map_game_window', 'focus_kodi',
                 'pad_to_kodi'):
        monkeypatch.setattr(watcher, name, rec(name))
    monkeypatch.setattr(watcher.subprocess, 'Popen', rec('Popen'))
    monkeypatch.setattr(watcher.os, 'kill', rec('kill'))
    monkeypatch.setattr(watcher, 'game_pids', lambda: [101, 102])
    monkeypatch.setattr(watcher, 'screen_classes', lambda: ('Kodi', 'Kodi'))
    monkeypatch.setattr(watcher, 'top_is_frozen_game', lambda: False)
    monkeypatch.setattr(watcher, 'get_joystick', lambda: True)
    calls.clear()
    return calls


def names(calls):
    return [c[0] for c in calls]


# =========================================================================
# gestures
# =========================================================================
def test_with_owns_empty_the_watcher_acts_exactly_as_before(box, spy):
    (box.dir / 'game-session').write_text('111 steam 367520\n')
    assert watcher.act('hold', Conf(), defer_handoff=True) is None or True
    assert 'act_suspend' in names(spy)
    assert all('yielded' not in i['args'] for i in box.intents())


def test_yielded_gesture_records_the_freeze_set_and_does_nothing(box, spy):
    (box.dir / 'game-session').write_text('111 steam 367520\n')
    box.own('gestures')
    assert watcher.act('hold', Conf(), defer_handoff=True) is False
    assert names(spy) == []                     # no action of any kind
    shadow = box.intents()[-1]
    assert shadow['verb'] == 'freeze'
    assert shadow['subject'] == '367520'
    assert shadow['args']['pids'] == [101, 102]   # the diffable part, recorded
    assert shadow['args']['yielded'] is True
    assert shadow['args']['owner'] == 'couchd'


def test_yielded_switcher_records_a_plain_yield_marker(box, spy):
    box.own('gestures')
    assert watcher.act('double_tap', Conf()) is False
    assert names(spy) == []
    assert box.verbs() == [('yield', 'double-tap')]
    assert box.intents()[0]['args']['action'] == 'switcher'


def test_an_unbound_gesture_still_does_nothing_either_way(box, spy):
    for owned in ((), ('gestures',)):
        box.own(*owned)
        assert watcher.act('tap', Conf()) is False
    assert box.intents() == []


def test_yielded_resume_does_not_launch_but_is_recorded(box, spy):
    (box.dir / 'game-suspended').write_text('367520')
    box.own('gestures')
    watcher.resume_game()
    assert 'Popen' not in names(spy)
    rec = box.intents()[-1]
    assert (rec['verb'], rec['subject']) == ('launch', '367520')
    assert rec['args']['mode'] == 'resume' and rec['args']['yielded'] is True


def test_unyielded_resume_still_launches(box, spy):
    (box.dir / 'game-suspended').write_text('367520')
    watcher.resume_game()
    assert 'Popen' in names(spy)
    assert 'yielded' not in box.intents()[-1]['args']


# =========================================================================
# ownership is a LEASE: a stopped couchd hands everything back
# =========================================================================
def test_a_stale_heartbeat_takes_the_gesture_back(box, spy):
    """`systemctl --user stop couchd` with a non-empty owns.conf must not
    leave the PS button owned by a corpse."""
    (box.dir / 'game-session').write_text('111 steam 367520\n')
    box.own('gestures')
    assert watcher.act('hold', Conf(), defer_handoff=True) is False   # yields
    box.age_heartbeat(120)
    watcher.act('hold', Conf(), defer_handoff=True)
    assert 'act_suspend' in names(spy)             # acting again, unprompted
    assert any('heartbeat is STALE' in l for l in
               (box.dir / 'legacy.log').read_text().splitlines())


def test_no_status_file_at_all_takes_it_back(box, spy):
    box.own('reconcile', 'gestures', 'guard')
    box.stop_couchd()
    (box.dir / 'game-suspended').write_text('367520')
    watcher.resume_game()
    assert 'Popen' in names(spy)                   # the resume really happened


def test_the_lease_is_reinstated_when_couchd_comes_back(box, spy):
    (box.dir / 'game-session').write_text('111 steam 367520\n')
    box.own('gestures')
    box.age_heartbeat(120)
    watcher.act('hold', Conf(), defer_handoff=True)
    assert 'act_suspend' in names(spy)
    spy.clear()
    box.age_heartbeat(0)                           # couchd is back
    watcher.act('hold', Conf(), defer_handoff=True)
    assert names(spy) == []


def test_the_guard_also_requires_a_live_heartbeat(box, monkeypatch):
    box.own('guard')
    box.age_heartbeat(120)
    monkeypatch.setattr(sys, 'argv', ['steam-input-guard', 'kodi', '0'])
    monkeypatch.setattr(guard, 'Screen', lambda: (_ for _ in ()).throw(
        RuntimeError('reached X, so it did not yield')))
    with pytest.raises(RuntimeError):              # i.e. it did NOT yield
        guard.main()
    assert (box.dir / 'guard.pid').read_text() == str(os.getpid())


def test_a_broken_owns_module_leaves_the_watcher_acting(box, spy, monkeypatch):
    """A SyntaxError in owns.py must not crash-loop the watcher and take the
    PS button with it: no module means no yielding."""
    monkeypatch.setattr(watcher, 'couchd_owns', None)
    monkeypatch.setattr(watcher, '_owns_import_error',
                        SyntaxError('invalid syntax'), raising=False)
    watcher._owns_said[0] = None
    box.own('gestures')
    (box.dir / 'game-session').write_text('111 steam 367520\n')
    assert watcher.yielded('gestures') is False
    watcher.act('hold', Conf(), defer_handoff=True)
    assert 'act_suspend' in names(spy)
    assert 'owns.py unavailable' in (box.dir / 'legacy.log').read_text()


def test_owning_reconcile_does_not_yield_gestures(box, spy):
    (box.dir / 'game-session').write_text('111 steam 367520\n')
    box.own('reconcile')
    watcher.act('hold', Conf(), defer_handoff=True)
    assert 'act_suspend' in names(spy)


# =========================================================================
# the guard pidfile: yielding must never SIGTERM couchd
# =========================================================================
def test_supersede_guard_kills_when_it_owns_the_guard(box, spy):
    (box.dir / 'guard.pid').write_text('4242')
    watcher.supersede_guard()
    # the liveness probe and then the SIGTERM, exactly as before the switch
    assert [a for n, a, _ in spy if n == 'kill'] == \
        [(4242, 0), (4242, watcher.signal.SIGTERM)]


def test_supersede_guard_never_signals_a_yielded_owner(box, spy):
    """couchd write-throughs this pidfile with its OWN pid: a SIGTERM here
    would kill the daemon holding the console together."""
    (box.dir / 'guard.pid').write_text('4242')
    box.own('guard')
    watcher.supersede_guard()
    assert names(spy) == []
    rec = box.intents()[-1]
    assert (rec['verb'], rec['args']['yielded']) == ('kill', True)
    assert rec['args']['pids'] == [4242]


# =========================================================================
# reconcile: the repairs still get COMPUTED, they just do not fire
# =========================================================================
def stage_stale_flag(box, monkeypatch):
    """A paused flag with nothing frozen - the stale-suspended-flag repair."""
    (box.dir / 'game-suspended').write_text('367520')
    monkeypatch.setattr(watcher, 'game_pids', lambda: [])


def test_reconcile_repairs_for_real_when_owns_is_empty(box, spy, monkeypatch):
    stage_stale_flag(box, monkeypatch)
    watcher._reconcile()
    assert not (box.dir / 'game-suspended').exists()      # really removed
    assert 'clear_snapshots' in names(spy)
    rec = box.intents()[0]
    assert rec['verb'] == 'clear_flag' and 'yielded' not in rec['args']


def test_yielded_reconcile_computes_but_never_touches_the_world(box, spy,
                                                                monkeypatch):
    stage_stale_flag(box, monkeypatch)
    box.own('reconcile')
    watcher._reconcile(dry=True)
    assert (box.dir / 'game-suspended').exists()          # flag untouched
    assert names(spy) == []                               # no snapshots, no X
    rec = box.intents()[0]
    assert rec['verb'] == 'clear_flag' and rec['args']['yielded'] is True
    assert rec['args']['owner'] == 'couchd'


def test_yielded_reconcile_records_the_orphan_repair_in_full(box, spy,
                                                             monkeypatch):
    # pid 999999 has no /proc entry, so the launcher reads as dead with no
    # game left: the orphan repair, which is the one that clears BOTH flags.
    (box.dir / 'game-session').write_text('999999 steam 367520\n')
    (box.dir / 'game-suspended').write_text('367520')
    monkeypatch.setattr(watcher, 'game_pids', lambda: [])
    box.own('reconcile')
    watcher._reconcile(dry=True)
    assert (box.dir / 'game-session').exists()
    assert (box.dir / 'game-suspended').exists()
    verbs = box.verbs()
    assert ('clear_flag', 'session') in verbs
    assert ('clear_flag', 'suspended') in verbs
    assert all(i['args'].get('yielded') for i in box.intents())
    # the pad and the screen halves are handed the same yield, which is what
    # makes them log-only (their own intent lines are tested via the real
    # functions in test_pad_to_kodi_and_focus_kodi_yield_log_only below)
    assert [(n, kw) for n, a, kw in spy if n in ('pad_to_kodi', 'focus_kodi')] \
        == [('pad_to_kodi', {'dry': True}), ('focus_kodi', {'dry': True})]
    assert 'set_joystick' not in names(spy)


def test_pad_to_kodi_and_focus_kodi_yield_log_only(box, monkeypatch):
    """The two handover halves, unmocked: dry writes the intent and returns
    without a JSON-RPC call or an X connection."""
    called = []
    monkeypatch.setattr(watcher, 'set_joystick',
                        lambda v: called.append(('set_joystick', v)))
    watcher.pad_to_kodi('reconcile:orphaned-session', dry=True)
    watcher.focus_kodi('reconcile:orphaned-session', dry=True)
    assert called == []
    assert box.verbs() == [('route_pad', 'kodi'), ('show', 'kodi')]
    assert all(i['args']['yielded'] for i in box.intents())
    watcher.pad_to_kodi('handoff')
    assert called == [('set_joystick', True)]
    assert 'yielded' not in box.intents()[-1]['args']


def test_yielded_reconcile_never_signals_a_lost_thaw(box, spy, monkeypatch):
    """The repair with the loudest side effect: 18 SIGCONTs, or none.

    A frozen game with no suspended flag is the lost-thaw repair; /proc is
    faked so the two pids read as state T without any real process."""
    real_open = open

    def fake_open(path, *a, **kw):
        if str(path).startswith('/proc/'):
            import io
            return io.StringIO('1 (game) T 0 0')
        return real_open(path, *a, **kw)

    monkeypatch.setattr('builtins.open', fake_open)
    box.own('reconcile')
    watcher._reconcile(dry=True)             # game_pids is [101, 102] (spy)
    assert 'kill' not in names(spy)
    assert 'map_game_window' not in names(spy)
    thaws = [i for i in box.intents() if i['verb'] == 'thaw']
    assert len(thaws) == 1
    assert thaws[0]['args']['pids'] == [101, 102]
    assert thaws[0]['args']['yielded'] is True


def test_unyielded_reconcile_does_signal_a_lost_thaw(box, spy, monkeypatch):
    """The other half of the pin: with owns empty the SIGCONTs still fire."""
    real_open = open

    def fake_open(path, *a, **kw):
        if str(path).startswith('/proc/'):
            import io
            return io.StringIO('1 (game) T 0 0')
        return real_open(path, *a, **kw)

    monkeypatch.setattr('builtins.open', fake_open)
    watcher._reconcile()
    assert names(spy).count('kill') == 2
    assert 'map_game_window' in names(spy)
    assert 'yielded' not in [i for i in box.intents()
                             if i['verb'] == 'thaw'][0]['args']


# =========================================================================
# the guard
# =========================================================================
def test_guard_runs_its_window_when_owns_is_empty(box, monkeypatch):
    """Not the whole window - just far enough to prove it did not yield: the
    next thing main() does is claim the pidfile."""
    monkeypatch.setattr(sys, 'argv', ['steam-input-guard', 'kodi', '0'])
    monkeypatch.setattr(guard, 'Screen', lambda: (_ for _ in ()).throw(
        RuntimeError('no X in a unit test')))
    with pytest.raises(RuntimeError):
        guard.main()
    assert (box.dir / 'guard.pid').read_text() == str(os.getpid())
    assert box.verbs() == []          # window_open comes after Screen()


def test_guard_yields_before_touching_the_pidfile(box, monkeypatch):
    box.own('guard')
    monkeypatch.setattr(sys, 'argv', ['steam-input-guard', 'kodi', '6'])
    monkeypatch.setattr(guard, 'Screen', lambda: (_ for _ in ()).throw(
        RuntimeError('a yielded guard must never reach X')))
    guard.main()
    assert not (box.dir / 'guard.pid').exists()
    assert box.verbs() == [('window_open', 'kodi'), ('window_close', 'kodi')]
    assert all(i['args']['yielded'] for i in box.intents())
