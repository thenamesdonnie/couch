#!/usr/bin/env python3
"""The paused game's tile keeps its own cover.

Donnie, 8 Aug 2026, once the paused CARD existed: "can we make the game tile
not change to the screencap as we now have a dedicated space".

The freeze-frame used to be pushed into the row tile's `thumb` and `poster`
as well as the card, which made sense back when the frame had nowhere else to
live. With a dedicated card it costs the row the thing that makes it
scannable - every game recognisable by its own art at a glance - and says the
same thing twice. A paused game is still marked: it keeps the "- paused"
label and it has the card.

Pinned here because it is a design decision, not an implementation detail:
the next person to touch `_paused_frame` will find a function that reads a
freeze-frame path and no longer has any obvious reason not to use it for the
tile again.

Kodi is stubbed and the paused dir is a tmp_path one, as in
test_switcher_dialog.py - the real ~/couch/data/paused holds the live
console's actual freeze-frames.

Run:  couchd/.venv/bin/pytest tools/test_games_paused_tile.py -q
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


class StubListItem:
    def __init__(self, label='', offscreen=False):
        self.label = label
        self.art = {}
        self.props = {}

    def setArt(self, art):
        self.art.update(art)

    def setProperty(self, key, value):
        self.props[key] = value

    def setInfo(self, *a, **k):
        pass

    def setProperties(self, props):
        self.props.update(props)


def _install_stubs():
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
    for name, mod in (('xbmc', xbmc), ('xbmcgui', xbmcgui),
                      ('xbmcplugin', xbmcplugin)):
        sys.modules[name] = mod


@pytest.fixture
def games(tmp_path, monkeypatch):
    _install_stubs()
    monkeypatch.setattr(sys, 'argv', ['plugin://x', '1', ''])
    spec = importlib.util.spec_from_loader(
        'games_under_test',
        importlib.machinery.SourceFileLoader('games_under_test', GAMES))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paused = tmp_path / 'paused'
    paused.mkdir()
    monkeypatch.setattr(module, 'PAUSED_DIR', str(paused))
    return types.SimpleNamespace(mod=module, dir=paused)


def test_the_newest_freeze_frame_is_found(games):
    for name in ('367520__1000.jpg', '367520__2000.jpg', '367520__1500.jpg'):
        (games.dir / name).write_bytes(b'jpg')
    assert games.mod._paused_frame('367520').endswith('367520__2000.jpg')


def test_the_2x3_tile_crop_is_no_longer_chosen(games):
    """pause-snap still writes a `.tile.jpg` centre crop beside the frame -
    it existed only to be the tile art. It must never come back as the
    answer, and the frame must not be mistaken for it either."""
    (games.dir / '367520__2000.jpg').write_bytes(b'jpg')
    (games.dir / '367520__2000.tile.jpg').write_bytes(b'jpg')
    assert games.mod._paused_frame('367520').endswith('367520__2000.jpg')
    assert not games.mod._paused_frame('367520').endswith('.tile.jpg')


def test_it_returns_a_path_not_an_art_dict(games):
    """The shape change IS the fix: while it handed back {'thumb':...,
    'poster':...} every call site was one `art.update()` away from putting
    the screencap back on the tile."""
    (games.dir / '367520__2000.jpg').write_bytes(b'jpg')
    assert isinstance(games.mod._paused_frame('367520'), str)


def test_nothing_paused_is_an_empty_string_not_a_crash(games):
    assert games.mod._paused_frame('367520') == ''
    games.mod.PAUSED_DIR = '/does/not/exist'
    assert games.mod._paused_frame('367520') == ''


def test_a_ps4_eboot_path_is_made_filename_safe(games):
    """PS4 tiles are keyed by their eboot path, which is full of slashes."""
    (games.dir / '_home_ds2000_games_ps4_CUSA00900_eboot.bin__9.jpg').write_bytes(b'j')
    got = games.mod._paused_frame('/home/ds2000/games/ps4/CUSA00900/eboot.bin')
    assert got.endswith('_eboot.bin__9.jpg')


def test_no_call_site_can_put_the_freeze_frame_into_the_tile_art():
    """The invariant, read off the source: the paused frame reaches the item
    only through the CouchPausedSnap property that Home.xml's card renders -
    never through setArt. Both call sites (Steam and PS4) are covered."""
    text = open(GAMES).read()
    assert '_paused_art' not in text, 'the art-override helper is back'
    for line in text.splitlines():
        if '_paused_frame(' in line and 'def ' not in line:
            assert 'snap =' in line, line
    # the frame is only ever handed to the card
    assert text.count("setProperty('CouchPausedSnap', snap)") == 2
    assert 'art.update(pa)' not in text
