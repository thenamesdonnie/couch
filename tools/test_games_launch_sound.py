#!/usr/bin/env python3
"""Selecting a game makes the launch noise, and never at the cost of the game.

Donnie, 24 Aug 2026: "can we add a noise to navigating the menu and selecting
a game pls". Navigating is Kodi's own job once the sound set is installed
(resource.uisounds.couch); "selecting a game" is not, because Kodi has no
action name for "a game started" - the Games row hands off to game-launch and
the press is over. So games.py plays the swell itself.

What is pinned here:

  * the sound plays on a real launch, and BEFORE the handoff - after it, the
    interpreter is racing a game for the machine.
  * the Library tile is not a launch and stays silent.
  * every way the sound can fail (no sound set installed, no audio, an older
    Kodi without playSFX) still launches the game. This is the whole reason
    `_launch_sound` swallows exceptions, and swallowing exceptions is exactly
    the sort of thing a later reader tidies up.

Kodi is stubbed as in test_games_paused_tile.py.

Run:  couchd/.venv/bin/pytest tools/test_games_launch_sound.py -q
"""
import importlib.machinery
import importlib.util
import os
import sys
import types

import pytest

HOME = os.path.expanduser('~')
GAMES = os.path.join(HOME, 'couch', 'kodi-addons', 'copacetic-helper-patches',
                     'games.py')
SOUNDS = os.path.join(HOME, 'couch', 'kodi-addons', 'resource.uisounds.couch')


class StubListItem:
    def __init__(self, label='', offscreen=False):
        self.label = label

    def setArt(self, art):
        pass

    def setProperty(self, key, value):
        pass

    def setInfo(self, *a, **k):
        pass

    def setProperties(self, props):
        pass


@pytest.fixture
def games(tmp_path, monkeypatch):
    played = []
    launched = []

    xbmcgui = types.ModuleType('xbmcgui')
    xbmcgui.ListItem = StubListItem
    xbmcgui.Window = lambda *a, **k: types.SimpleNamespace(
        setProperty=lambda *a, **k: None, getProperty=lambda *a: '',
        clearProperty=lambda *a: None)
    xbmcplugin = types.ModuleType('xbmcplugin')
    for name in ('setContent', 'addDirectoryItems', 'endOfDirectory',
                 'setPluginCategory', 'addSortMethod'):
        setattr(xbmcplugin, name, lambda *a, **k: None)
    xbmc = types.ModuleType('xbmc')
    xbmc.log = lambda *a, **k: None
    xbmc.executebuiltin = lambda *a, **k: None
    xbmc.playSFX = lambda path, **k: played.append(path)
    xbmcvfs = types.ModuleType('xbmcvfs')
    # The real one maps special://home to the profile; for the test the repo
    # copy is the addon, which is what deploy-addons puts there anyway.
    xbmcvfs.translatePath = lambda p: p.replace(
        'special://home/addons/resource.uisounds.couch',
        SOUNDS)
    for name, mod in (('xbmc', xbmc), ('xbmcgui', xbmcgui),
                      ('xbmcplugin', xbmcplugin), ('xbmcvfs', xbmcvfs)):
        sys.modules[name] = mod

    monkeypatch.setattr(sys, 'argv', ['plugin://x', '1', ''])
    spec = importlib.util.spec_from_loader(
        'games_launch_under_test',
        importlib.machinery.SourceFileLoader('games_launch_under_test', GAMES))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Nothing in this test may start a game.
    monkeypatch.setattr(module, 'host_popen',
                        lambda cmd, **k: launched.append(cmd))
    return types.SimpleNamespace(mod=module, played=played,
                                 launched=launched, xbmc=xbmc)


def test_launching_a_steam_game_plays_the_swell(games):
    games.mod.games_route('launch_game', {'id': '367520'})
    assert games.launched == [[games.mod.LAUNCHER, 'steam', '367520']]
    assert len(games.played) == 1
    assert games.played[0].endswith('launch.wav')


def test_the_wav_it_asks_for_actually_exists(games):
    """The path is a string in a try/except that eats its own failures, so
    nothing else in this file would notice it going stale."""
    games.mod.games_route('launch_game', {'id': '367520'})
    assert os.path.exists(games.played[0]), games.played[0]


def test_ps4_and_big_picture_launches_get_it_too(games):
    games.mod.games_route('launch_game', {'id': 'bigpicture'})
    games.mod.games_route('launch_game', {'id': 'ps4:/home/ds2000/games/ps4/x'})
    games.mod.games_route('launch_game', {'id': 'shadps4'})
    assert len(games.launched) == 3
    assert len(games.played) == 3


def test_the_library_tile_is_a_destination_and_stays_silent(games):
    """It is the one item on the row that does not take the machine away."""
    games.mod.games_route('launch_game', {'id': 'library'})
    assert games.played == []
    assert games.launched == []


def test_the_sound_comes_before_the_handoff(games):
    """Once game-launch is running, this interpreter is on borrowed time -
    Kodi is about to lose the screen, the pad and the audio device."""
    order = []
    games.xbmc.playSFX = lambda path, **k: order.append('sound')
    games.mod.host_popen = lambda cmd, **k: order.append('launch')
    games.mod.games_route('launch_game', {'id': '367520'})
    assert order == ['sound', 'launch']


def test_a_missing_sound_set_still_launches_the_game(games, monkeypatch):
    monkeypatch.setattr(games.mod, 'LAUNCH_SFX',
                        'special://home/addons/nope/resources/launch.wav')
    games.mod.games_route('launch_game', {'id': '367520'})
    assert games.launched == [[games.mod.LAUNCHER, 'steam', '367520']]
    assert games.played == []


def test_an_audio_device_that_throws_still_launches_the_game(games):
    def boom(*a, **k):
        raise RuntimeError('no audio device')
    games.xbmc.playSFX = boom
    games.mod.games_route('launch_game', {'id': '367520'})
    assert games.launched == [[games.mod.LAUNCHER, 'steam', '367520']]


def test_an_old_kodi_without_playsfx_still_launches_the_game(games):
    del games.xbmc.playSFX
    games.mod.games_route('launch_game', {'id': '367520'})
    assert games.launched == [[games.mod.LAUNCHER, 'steam', '367520']]
