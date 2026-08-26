#!/usr/bin/env python3
"""mode-keeper's refusals: it must not change the display mode under a game,
and (25 Aug 2026) must not change it under a playing video either.

Donnie, 25 Aug 2026, explaining why he had abandoned our YouTube for the
television's own app: "it was skipping seconds and going really fast and idk
if the audio was even synced".

A modeset raises an X RandR event, and Kodi answers it by re-enumerating audio
devices and resetting the sink - kodi.log carries the pair every time:

    WinSystemX11::RefreshWindow - failed to query xrandr
    ValidateOutputDevices: audio output device setting has been updated
      from 'PULSE:Default' to 'ALSA:default|...'

That resets the audio clock mid-video; Kodi's video clock is slaved to it, so
the picture skips to catch up. Eight of those landed in five minutes around
20:20 on 25 Aug, one per correction this keeper made.

The refusal is free: films and YouTube are 60fps at most, so the 4K60 the TV
fell back to already holds every frame they have.

No X, no Kodi, no network: xrandr and the Kodi query are both stubbed, so
these run anywhere.

Run:  couchd/.venv/bin/pytest tools/test_mode_keeper.py -q
"""
import importlib.machinery
import importlib.util
import os
import sys
import urllib.error

import pytest

TOOLS = os.path.dirname(os.path.abspath(__file__))
MK = os.path.join(TOOLS, 'mode-keeper')


@pytest.fixture
def mk(monkeypatch):
    sys.path.insert(0, TOOLS)          # mode-keeper imports couchenv from here
    spec = importlib.util.spec_from_loader(
        'mode_keeper_under_test',
        importlib.machinery.SourceFileLoader('mode_keeper_under_test', MK))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # A world that WOULD be corrected: fallen to an EDID mode, no game.
    monkeypatch.setattr(mod, 'state', lambda display=':0':
                        ('DisplayPort-2', '3840x2160'))
    monkeypatch.setattr(mod, 'game_running', lambda: False)
    # Keep a handle on the REAL one: the tick() tests stub it, and the
    # semantics tests below would otherwise be testing the stub.
    mod._real_playback_running = mod.playback_running
    monkeypatch.setattr(mod, 'playback_running', lambda: False)
    applied = []
    monkeypatch.setattr(mod, 'reapply',
                        lambda output, display=':0', dry_run=False:
                        applied.append(output) or True)
    mod._applied = applied
    return mod


def test_it_corrects_a_fallen_display_when_nothing_is_happening(mk):
    """The baseline: without this, the rest of the file proves nothing."""
    mk.tick(':0', False, 0.0, 0)
    assert mk._applied == ['DisplayPort-2']


def test_it_will_not_touch_the_display_while_something_is_playing(mk, monkeypatch):
    monkeypatch.setattr(mk, 'playback_running', lambda: True)
    last_fix, corrections = mk.tick(':0', False, 0.0, 0)
    assert mk._applied == [], 'a modeset landed under a playing video'
    assert corrections == 0, 'a deferral must not count as a correction'


def test_it_will_not_touch_the_display_while_a_game_is_up(mk, monkeypatch):
    monkeypatch.setattr(mk, 'game_running', lambda: True)
    mk.tick(':0', False, 0.0, 0)
    assert mk._applied == []


def test_the_deferral_is_not_a_cooldown_it_retries_next_tick(mk, monkeypatch):
    """Deferring must leave last_fix alone, or the correction that IS due the
    moment playback stops would be swallowed by the cooldown."""
    monkeypatch.setattr(mk, 'playback_running', lambda: True)
    last_fix, _ = mk.tick(':0', False, 123.0, 0)
    assert last_fix == 123.0
    monkeypatch.setattr(mk, 'playback_running', lambda: False)
    mk.tick(':0', False, 0.0, 0)
    assert mk._applied == ['DisplayPort-2'], 'never re-claimed after playback'


# -- playback_running's own failure semantics --------------------------------
#
# The rule is "doubt counts as leave-it-alone", with ONE carve-out: a refused
# connection means Kodi is not running, and a Kodi that is not running is
# certainly not playing. Without that, a box with Kodi stopped sits at 60Hz
# forever.

def _urlopen_raising(exc):
    def fake(*_a, **_k):
        raise exc
    return fake


def test_kodi_down_is_a_real_no_not_doubt(mk, monkeypatch):
    monkeypatch.setattr(mk.urllib.request, 'urlopen', _urlopen_raising(
        urllib.error.URLError(ConnectionRefusedError(111, 'refused'))))
    assert mk._real_playback_running() is False


def test_a_timeout_counts_as_playing(mk, monkeypatch):
    """A wedged-but-running Kodi could well be mid-video, and the cost of
    guessing wrong is a ruined film against a few minutes at 60Hz."""
    monkeypatch.setattr(mk.urllib.request, 'urlopen', _urlopen_raising(
        urllib.error.URLError(TimeoutError('timed out'))))
    assert mk._real_playback_running() is True


def test_junk_from_kodi_counts_as_playing(mk, monkeypatch):
    monkeypatch.setattr(mk.urllib.request, 'urlopen',
                        _urlopen_raising(ValueError('not json')))
    assert mk._real_playback_running() is True


def test_an_active_player_is_playing_and_an_empty_list_is_not(mk, monkeypatch):
    class Resp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(mk.urllib.request, 'urlopen',
                        lambda *a, **k: Resp(b'{"result":[{"playerid":1}]}'))
    assert mk._real_playback_running() is True
    monkeypatch.setattr(mk.urllib.request, 'urlopen',
                        lambda *a, **k: Resp(b'{"result":[]}'))
    assert mk._real_playback_running() is False
