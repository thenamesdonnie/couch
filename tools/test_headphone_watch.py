#!/usr/bin/env python3
"""The headphone rule in tv-waker-webos, pinned without a TV or headphones.

Donnie, 9 Aug 2026: "can you make sure the way it works is if my tv is off it
disconnects and / or does not try to connect".

Those are two guarantees, and the interesting one is the second half of the
first: the headphones are the party that initiates a connection (press their
power button and they dial the box, the television having done nothing), so
"disconnect when the TV is off" cannot be a TV-off event handler. It has to
hold for as long as the set is off. These tests are written against that,
not against the transition.

Run:  couchd/.venv/bin/pytest tools/test_headphone_watch.py -q
"""
import importlib.machinery
import importlib.util
import os
import sys
import types

import pytest

HOME = os.path.expanduser('~')
LIVE = os.path.join(HOME, '.local', 'bin', 'tv-waker-webos')
MIRROR = os.path.join(HOME, 'couch', 'legacy-mirror', 'tv-waker-webos')


def _load(name, path):
    # lgssap lives beside the script at runtime (sys.path[0]) and is not
    # importable here; the rule under test never touches it.
    if 'lgssap' not in sys.modules:
        stub = types.ModuleType('lgssap')
        stub.LGTV = object

        async def _probe(*_a, **_k):
            return (None, None)

        stub.probe = _probe
        sys.modules['lgssap'] = stub
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


waker = _load('tv_waker_webos_live', LIVE)
decide = waker.headphone_decision


# =========================================================================
# TV off: disconnect, and never connect
# =========================================================================
def test_tv_off_and_connected_disconnects():
    assert decide(tv_on=False, connected=True,
                  just_turned_on=False, override=False) == 'disconnect'


def test_tv_off_enforced_continuously_not_only_on_the_off_event():
    """The headphones dial US. Long after the TV went off, powering them on
    must still be undone - so the rule cannot depend on a transition."""
    for _tick in range(5):
        assert decide(tv_on=False, connected=True,
                      just_turned_on=False, override=False) == 'disconnect'


def test_tv_off_and_already_disconnected_does_nothing():
    assert decide(tv_on=False, connected=False,
                  just_turned_on=False, override=False) is None


def test_tv_off_never_connects_even_on_a_stale_turned_on_flag():
    """just_turned_on is derived from the previous poll; if the set went back
    to standby in between, the off state wins."""
    assert decide(tv_on=False, connected=False,
                  just_turned_on=True, override=False) != 'connect'


# =========================================================================
# TV on
# =========================================================================
def test_connects_only_on_the_off_to_on_transition():
    assert decide(tv_on=True, connected=False,
                  just_turned_on=True, override=False) == 'connect'


def test_tv_merely_being_on_does_not_retry_forever():
    """Watching on the soundbar with the headphones off must not mean a
    connect attempt every poll - each one blocks for its whole timeout."""
    assert decide(tv_on=True, connected=False,
                  just_turned_on=False, override=False) is None


def test_tv_on_and_already_connected_does_nothing():
    assert decide(tv_on=True, connected=True,
                  just_turned_on=True, override=False) is None


def test_daemon_restart_while_watching_does_not_grab_the_headphones():
    """On startup prev_on is None, so just_turned_on is False: restarting the
    service mid-film must not yank audio into headphones nobody asked for."""
    assert decide(tv_on=True, connected=False,
                  just_turned_on=False, override=False) is None


# =========================================================================
# Unknowns and the escape hatch
# =========================================================================
@pytest.mark.parametrize('tv_on', [True, False, None])
@pytest.mark.parametrize('connected', [True, False, None])
@pytest.mark.parametrize('just', [True, False])
def test_override_file_means_hands_off_in_every_state(tv_on, connected, just):
    assert decide(tv_on=tv_on, connected=connected,
                  just_turned_on=just, override=True) is None


@pytest.mark.parametrize('just', [True, False])
def test_unknown_bluetooth_state_is_never_acted_on(just):
    """None is 'bluetoothctl could not say'. Treating it as disconnected
    would connect on a guess; as connected, disconnect on a guess."""
    assert decide(tv_on=True, connected=None,
                  just_turned_on=just, override=False) is None
    assert decide(tv_on=False, connected=None,
                  just_turned_on=just, override=False) is None


def test_unknown_tv_state_is_never_acted_on():
    assert decide(tv_on=None, connected=True,
                  just_turned_on=False, override=False) is None
    assert decide(tv_on=None, connected=False,
                  just_turned_on=True, override=False) is None


# =========================================================================
# Wiring: the guarantees above are worthless if the loop is not running
# =========================================================================
def test_headphone_watch_is_actually_gathered_in_main():
    src = open(LIVE, encoding='utf-8').read()
    assert 'headphone_watch(conf)' in src.split('async def main')[1], \
        'headphone_watch defined but never scheduled'


def test_absent_mac_leaves_the_watcher_idle():
    """Ships disarmed: no headphones_mac in tv.json means no bluetooth calls
    at all, so this can land before the pair is even bonded."""
    import asyncio
    calls = []
    waker.bt = lambda *a, **k: calls.append(a)
    asyncio.run(waker.headphone_watch({}))          # returns immediately
    assert calls == []


def test_bluetoothctl_runs_off_the_event_loop():
    """A connect blocks for up to HP_TIMEOUT; done inline it would freeze the
    pad watcher and the Kodi socket with it."""
    src = open(LIVE, encoding='utf-8').read()
    body = src.split('async def headphone_watch')[1].split('async def main')[0]
    for verb in ('bt, "connect"', 'bt, "disconnect"', 'hp_connected'):
        assert f'to_thread({verb}' in body, f'{verb} not run via to_thread'


def test_mirror_matches_the_live_script():
    """legacy-mirror is the git record; the live file is the truth. A drift
    here means the history does not describe what actually runs."""
    if not os.path.exists(MIRROR):
        pytest.fail('legacy-mirror/tv-waker-webos missing')
    assert open(MIRROR, encoding='utf-8').read() == \
        open(LIVE, encoding='utf-8').read()
