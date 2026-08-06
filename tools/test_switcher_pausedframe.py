#!/usr/bin/env python3
"""Unit tests for the switcher addon's freeze-frame picker (pausedframe.py).

Pure functions only: which jpg in a directory is the paused session's frame,
and which appid the /api/windows rows name. No Kodi, no live paths - every
directory here is pytest's tmp_path. The impure edges (the dialog property,
the 200ms poll thread) live in default.py and are covered by the operator's
live re-test on deploy day (todo.md step 2).

Run:  couchd/.venv/bin/pytest tools/test_switcher_pausedframe.py -q
"""
import importlib.machinery
import importlib.util
import os

_spec = importlib.util.spec_from_loader(
    'pausedframe', importlib.machinery.SourceFileLoader(
        'pausedframe', os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..',
            'kodi-addons', 'script.couch.switcher', 'pausedframe.py')))
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)

NOW = 1_786_012_930_000  # an arbitrary "now", ms


def touch(d, name):
    (d / name).write_bytes(b'jpg')


# -- newest_frame -------------------------------------------------------------

def test_picks_the_newest_fresh_frame(tmp_path):
    touch(tmp_path, '367520__%d.jpg' % (NOW - 8_000))
    touch(tmp_path, '367520__%d.jpg' % (NOW - 1_000))
    assert pf.newest_frame(str(tmp_path), '367520', NOW) == \
        str(tmp_path / ('367520__%d.jpg' % (NOW - 1_000)))


def test_tiles_are_never_the_backdrop(tmp_path):
    # The .tile.jpg is newer than the frame - a plain endswith('.jpg') filter
    # would pick the 600x900 poster crop. It must not.
    touch(tmp_path, '367520__%d.jpg' % (NOW - 2_000))
    touch(tmp_path, '367520__%d.tile.jpg' % (NOW - 1_000))
    assert pf.newest_frame(str(tmp_path), '367520', NOW) == \
        str(tmp_path / ('367520__%d.jpg' % (NOW - 2_000)))


def test_other_games_frames_are_ignored(tmp_path):
    touch(tmp_path, '1086940__%d.jpg' % (NOW - 1_000))
    assert pf.newest_frame(str(tmp_path), '367520', NOW) is None


def test_appid_prefix_cannot_partial_match(tmp_path):
    # appid "36752" must not claim 367520's frame: the "__" separator is part
    # of the prefix.
    touch(tmp_path, '367520__%d.jpg' % (NOW - 1_000))
    assert pf.newest_frame(str(tmp_path), '36752', NOW) is None


def test_stale_frames_never_show(tmp_path):
    # A frame from an earlier suspend that escaped pause-snap --clear: 61s old
    # is beyond FRESH_MS, so the backdrop stays off rather than showing the
    # wrong moment.
    touch(tmp_path, '367520__%d.jpg' % (NOW - 61_000))
    assert pf.newest_frame(str(tmp_path), '367520', NOW) is None


def test_freshness_boundary_is_inclusive(tmp_path):
    touch(tmp_path, '367520__%d.jpg' % (NOW - 60_000))
    assert pf.newest_frame(str(tmp_path), '367520', NOW) is not None


def test_small_clock_skew_tolerated_big_future_rejected(tmp_path):
    touch(tmp_path, '367520__%d.jpg' % (NOW + 1_500))
    assert pf.newest_frame(str(tmp_path), '367520', NOW) is not None
    (tmp_path / ('367520__%d.jpg' % (NOW + 1_500))).unlink()
    touch(tmp_path, '367520__%d.jpg' % (NOW + 10_000))
    assert pf.newest_frame(str(tmp_path), '367520', NOW) is None


def test_junk_names_are_ignored(tmp_path):
    touch(tmp_path, '367520__notanumber.jpg')
    touch(tmp_path, '367520.jpg')            # no separator
    touch(tmp_path, '367520__%d.png' % NOW)  # wrong extension
    assert pf.newest_frame(str(tmp_path), '367520', NOW) is None


def test_missing_dir_and_empty_appid(tmp_path):
    assert pf.newest_frame(str(tmp_path / 'nope'), '367520', NOW) is None
    touch(tmp_path, '367520__%d.jpg' % (NOW - 1_000))
    assert pf.newest_frame(str(tmp_path), '', NOW) is None


def test_shadps4_appid_is_matched_through_the_sanitizer(tmp_path):
    # pause-snap files a shadPS4 game under safe(eboot path); the picker must
    # apply the same mangle to find it.
    appid = '/games/ps4/CUSA00003/eboot.bin'
    touch(tmp_path, pf.safe(appid) + '__%d.jpg' % (NOW - 1_000))
    assert pf.newest_frame(str(tmp_path), appid, NOW) is not None


def test_safe_mirrors_pause_snap():
    # Byte-for-byte the sanitizer in ~/.local/bin/pause-snap: [^A-Za-z0-9._-]
    # -> '_', first 100 chars, 'game' when nothing survives.
    assert pf.safe('/games/eboot.bin') == '_games_eboot.bin'
    assert pf.safe('367520') == '367520'
    assert pf.safe('a' * 150) == 'a' * 100
    assert pf.safe('') == 'game'


# -- session_appid ------------------------------------------------------------

def test_appid_from_proton_window_class():
    rows = [{'id': '0x1', 'title': 'Big Picture', 'cls': 'steamwebhelper'},
            {'id': '0x2', 'title': 'Hollow Knight · paused',
             'cls': 'steam_app_367520', 'paused': True}]
    assert pf.session_appid(rows) == '367520'


def test_appid_from_thumb_when_class_is_synthetic():
    # The shadPS4 shape: cls carries no appid, but the capture landed before
    # the dialog opened so the server attached the frame url.
    rows = [{'id': 'paused', 'title': 'Bloodborne · paused',
             'cls': 'paused-game', 'paused': True,
             'thumb': '/api/art/game?p=%2Fhome%2Fds2000%2Fcouch%2Fdata'
                      '%2Fpaused%2F_games_eboot.bin__1786012922364.jpg'}]
    assert pf.session_appid(rows) == '_games_eboot.bin'


def test_fallback_answers_when_rows_are_silent():
    # shadPS4 AND the capture is still being written: no cls appid, no thumb.
    rows = [{'id': 'paused', 'title': 'Bloodborne · paused',
             'cls': 'paused-game', 'paused': True}]
    assert pf.session_appid(rows, fallback='CUSA00003') == 'CUSA00003'


def test_unpaused_rows_never_supply_an_appid():
    # A running (not suspended) game session: no paused row, so no session
    # appid and no backdrop - even though the class carries an appid.
    rows = [{'id': '0x2', 'title': 'Hollow Knight',
             'cls': 'steam_app_367520'}]
    assert pf.session_appid(rows) == ''
