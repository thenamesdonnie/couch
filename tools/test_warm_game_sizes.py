#!/usr/bin/env python3
"""Install sizes: measured hourly, never on the listing's critical path.

The Games row shows an install size. It used to be computed inside the
listing and cached under the game FOLDER'S OWN MTIME - and a directory's mtime
does not move when its contents grow, only when its own entries do. So a game
that gained 11 GB of mods three levels down kept its old number for ever.
Measured on this box: Bloodborne's tile read 29.3 GB for a 40.5 GB game, and
had done since the mods went in.

Invalidating harder would have made things worse, not better: the miss path is
a full os.walk - 28,778 files, 267ms for that game - with the player waiting
on a directory listing. So the walk moved to the hourly warmer and games.py
became a pure reader.

What is pinned here is the property that broke: growth deep in the tree must
be seen. Plus the reader's manners, because it runs in front of the room.

Run:  couchd/.venv/bin/pytest tools/test_warm_game_sizes.py -q
"""
import importlib.machinery
import importlib.util
import json
import os
import types

import pytest

HOME = os.path.expanduser('~')
TOOL = os.path.join(HOME, 'couch', 'tools', 'warm-game-sizes')


def _load(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_loader(
        'warm_game_sizes',
        importlib.machinery.SourceFileLoader('warm_game_sizes', TOOL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, 'CACHE', str(tmp_path / 'sizes.json'))
    monkeypatch.setattr(mod, 'STEAMAPPS', str(tmp_path / 'steamapps'))
    monkeypatch.setattr(mod, 'PS4_DIR', str(tmp_path / 'ps4'))
    return mod


@pytest.fixture
def box(tmp_path, monkeypatch):
    mod = _load(monkeypatch, tmp_path)
    common = tmp_path / 'steamapps' / 'common'
    common.mkdir(parents=True)
    ps4 = tmp_path / 'ps4'
    ps4.mkdir()
    return types.SimpleNamespace(mod=mod, tmp=tmp_path, common=common, ps4=ps4,
                                 cache=tmp_path / 'sizes.json')


def write(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'x' * size)


def cached(box):
    return {k: v[1] for k, v in json.load(open(box.cache)).items()}


# =========================================================================
# the bug
# =========================================================================
def test_growth_deep_in_the_tree_is_seen(box):
    """THE regression. The old cache keyed on the game folder's mtime, which
    a file written three levels down never touches - so a modded game's size
    froze at whatever it was the day it was installed."""
    game = box.ps4 / 'CUSA00900'
    write(game / 'eboot.bin', 1000)
    box.mod.main()
    first = cached(box)[str(game)]

    # mods land deep, leaving the top folder's own mtime untouched
    before = os.path.getmtime(game)
    write(game / 'dvdroot_ps4' / 'parts' / 'huge.dat', 50_000)
    os.utime(game, (before, before))
    assert os.path.getmtime(game) == before, 'the premise: top mtime unmoved'

    box.mod.main()
    assert cached(box)[str(game)] == first + 50_000


def test_a_steam_game_is_measured_too(box):
    write(box.common / 'ELDEN RING' / 'game.pak', 4096)
    box.mod.main()
    assert cached(box)[str(box.common / 'ELDEN RING')] == 4096


def test_ps4_patch_folders_are_not_their_own_entry(box):
    """games.py hides the -patch sibling behind the base game's tile; sizing
    it separately would invite someone to add it up twice."""
    write(box.ps4 / 'CUSA00900' / 'eboot.bin', 10)
    write(box.ps4 / 'CUSA00900-patch' / 'thing.dat', 10)
    box.mod.main()
    assert str(box.ps4 / 'CUSA00900-patch') not in cached(box)


def test_a_folder_with_no_eboot_is_not_a_game(box):
    """~/games/ps4 also holds the user's own pkg downloads."""
    write(box.ps4 / 'bloodborne' / 'base.pkg', 999)
    box.mod.main()
    assert str(box.ps4 / 'bloodborne') not in cached(box)


# =========================================================================
# manners
# =========================================================================
def test_an_unreadable_game_keeps_its_last_known_size(box):
    """An unmounted disk or a dump mid-re-extract must not blink the tile to
    nothing - it adds, it never blanks."""
    game = box.ps4 / 'CUSA00900'
    write(game / 'eboot.bin', 4242)
    box.mod.main()
    assert cached(box)[str(game)] == 4242

    for f in (game / 'eboot.bin',):
        f.unlink()
    box.mod.main()
    assert cached(box)[str(game)] == 4242


def test_a_corrupt_cache_is_rebuilt_not_fatal(box):
    box.cache.write_text('{ this is not json')
    write(box.common / 'Hollow Knight' / 'x.dat', 7)
    assert box.mod.main() == 0
    assert cached(box)[str(box.common / 'Hollow Knight')] == 7


def test_the_write_is_atomic(box):
    """The reader is a Kodi listing; a half-written sizes.json in front of
    the room would be a listing with no sizes at best."""
    write(box.common / 'Brawlhalla' / 'x.dat', 3)
    box.mod.main()
    assert not (box.tmp / 'sizes.json.part').exists()
    json.load(open(box.cache))


# =========================================================================
# the reader half, in games.py
# =========================================================================
def test_games_py_never_walks_a_tree_any_more():
    """The point of the split: the listing reads, it does not measure."""
    src = open(os.path.join(HOME, 'couch', 'kodi-addons',
                            'copacetic-helper-patches', 'games.py')).read()
    start = src.index('def _dir_size_cached(')
    body = src[start:src.index('\ndef ', start + 10)]
    assert 'os.walk' not in body, 'the listing walks the tree again'
    assert 'getmtime' not in body, 'the mtime key is back'
    assert 'warm-game-sizes' in src, 'nothing warms the cache any more'
