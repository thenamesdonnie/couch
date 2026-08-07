#!/usr/bin/env python3
"""Unit tests for the PS-button key bindings (gestureconf.py).

Everything here is synthetic settings-file TEXT into pure functions, plus a
handful of tmp_path files for the caching. Nothing touches
~/.kodi/userdata/addon_data - that path belongs to Kodi, and a test that wrote
to it would be changing the console's live bindings.

The point of the module is that it NEVER raises and never leaves the room
without a way out of a running game, so most of what is pinned here is the
failure paths.

    .venv/bin/python -m pytest test_gestureconf.py -q
"""
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import gestureconf
from gestureconf import (ACTIONS, DEFAULT_BINDINGS, DEFAULT_TIMINGS, GESTURES,
                         GestureConfig, build, load, parse, suppress, validate)

ADDON_SETTINGS = os.path.expanduser(
    '~/.kodi/addons/script.couch.switcher/resources/settings.xml')


def written(**values):
    """A settings.xml in the shape Kodi 20 actually writes to addon_data."""
    rows = ''.join(f'    <setting id="{k}">{v}</setting>\n'
                   for k, v in values.items())
    return f'<settings version="2">\n{rows}</settings>\n'


def conf(**values):
    return build(written(**values))


# =========================================================================
# the defaults ARE today's console
# =========================================================================
def test_defaults_reproduce_the_shipped_console():
    c = GestureConfig()
    assert c.bindings == {'tap': 'none', 'double_tap': 'switcher',
                          'hold': 'suspend_to_kodi', 'hold_release': 'none',
                          'long_hold': 'none'}
    assert (c.hold_seconds, c.double_tap_seconds, c.long_hold_seconds) == (
        0.9, 0.35, 3.0)
    assert c.warnings == ()
    assert c.is_default


def test_a_file_that_says_nothing_is_the_default_console():
    c = build('<settings version="2"></settings>')
    assert c.bindings == DEFAULT_BINDINGS
    assert c.timings == DEFAULT_TIMINGS
    assert not c.warnings


def test_a_full_default_file_round_trips_without_a_warning():
    c = conf(**{f'gesture.{g}': a for g, a in DEFAULT_BINDINGS.items()},
             **{f'timing.{t}': v for t, v in DEFAULT_TIMINGS.items()})
    assert c.bindings == DEFAULT_BINDINGS
    assert c.timings == DEFAULT_TIMINGS
    assert not c.warnings


# =========================================================================
# every failure path degrades, none of them raise
# =========================================================================
@pytest.mark.parametrize('text', [
    '',
    '   \n ',
    '<settings version="2">',                     # truncated mid-write
    '<settings><setting id="gesture.hold">',      # truncated worse
    'not xml at all',
    '\x00\x01\x02',
])
def test_unparseable_text_is_the_default_console_plus_a_warning(text):
    c = build(text)
    assert c.bindings == DEFAULT_BINDINGS
    assert c.timings == DEFAULT_TIMINGS
    assert c.warnings, 'a degraded read must say so'


def test_an_unknown_action_falls_back_for_that_field_only():
    c = conf(**{'gesture.hold': 'launch_nukes', 'gesture.hold_release': 'desktop'})
    assert c.bindings['hold'] == 'suspend_to_kodi'   # the default, restored
    assert c.bindings['hold_release'] == 'desktop'   # the good field survives
    assert any('launch_nukes' in w for w in c.warnings)


def test_an_unknown_setting_id_is_ignored_silently():
    """Kodi keeps values for settings we removed; they are not an error."""
    c = conf(**{'gesture.hold': 'switcher', 'gesture.middle_click': 'desktop',
                'kodion.setup_wizard': 'false'})
    assert c.requested['hold'] == 'switcher'
    assert not any('middle_click' in w for w in c.warnings)


@pytest.mark.parametrize('raw', ['', 'soon', 'NaN', '1,5', '0.9s'])
def test_a_non_numeric_timing_falls_back(raw):
    c = conf(**{'timing.hold_seconds': raw})
    assert c.hold_seconds == 0.9
    assert c.warnings


@pytest.mark.parametrize('raw,field', [
    ('0.01', 'hold_seconds'),       # below the slider's minimum
    ('30', 'hold_seconds'),         # above its maximum
    ('-1', 'double_tap_seconds'),
    ('99', 'long_hold_seconds'),
])
def test_a_timing_outside_the_sliders_range_falls_back(raw, field):
    c = conf(**{f'timing.{field}': raw})
    assert c.timings[field] == DEFAULT_TIMINGS[field]
    assert c.warnings


def test_a_long_hold_shorter_than_the_hold_is_repaired():
    """A long hold that fires BEFORE the hold is not a tier, it is a race."""
    c = conf(**{'timing.hold_seconds': '2.0', 'timing.long_hold_seconds': '1.5'})
    assert c.long_hold_seconds > c.hold_seconds
    assert any('long_hold_seconds' in w for w in c.warnings)


def test_a_hold_longer_than_the_default_long_hold_still_leaves_room():
    c = conf(**{'timing.hold_seconds': '3.0', 'timing.long_hold_seconds': '2.0'})
    assert c.hold_seconds == 3.0
    assert c.long_hold_seconds == 4.0, 'pushed clear of the hold'


def test_partial_files_keep_the_defaults_for_everything_else():
    c = conf(**{'gesture.double_tap': 'desktop'})
    assert c.bindings['double_tap'] == 'desktop'
    assert c.bindings['hold'] == 'suspend_to_kodi'
    assert c.timings == DEFAULT_TIMINGS


def test_the_old_attribute_form_is_still_read():
    """An addon_data file written by an older Kodi survives an upgrade."""
    c = build('<settings><setting id="gesture.hold" value="switcher"/>'
              '<setting id="gesture.double_tap" value="suspend_to_kodi"/>'
              '<setting id="timing.hold_seconds" value="1.2"/></settings>')
    assert c.bindings['hold'] == 'switcher'
    assert c.bindings['double_tap'] == 'suspend_to_kodi'
    assert c.hold_seconds == 1.2


def test_build_never_raises_on_anything():
    for text in (None, 12, b'bytes', object()):
        c = build(text)
        assert c.bindings == DEFAULT_BINDINGS


# =========================================================================
# the safety rail
# =========================================================================
def test_binding_the_escape_away_everywhere_is_rejected():
    """The whole config is rejected, not patched field by field: the hold
    goes back to the suspend so the room can always get out of a game."""
    c = conf(**{'gesture.hold': 'tv_toggle', 'gesture.double_tap': 'desktop'})
    assert c.bindings['hold'] == 'suspend_to_kodi'
    assert c.requested['hold'] == 'tv_toggle', 'what was asked for is kept'
    assert any('REJECTED' in w for w in c.warnings)
    # ...and the rest of the config it came with is NOT silently kept
    assert c.bindings['double_tap'] == 'desktop'


def test_the_escape_on_any_other_gesture_satisfies_the_rail():
    c = conf(**{'gesture.hold': 'power_menu',
                'gesture.double_tap': 'suspend_to_kodi'})
    assert c.bindings['hold'] == 'power_menu', 'not forced: there is a way out'
    assert not any('REJECTED' in w for w in c.warnings)


def test_the_escape_on_a_SUPPRESSED_gesture_does_not_count():
    """long_hold is dead while hold is bound, so it is not an escape route.
    The rail runs on what can actually fire, not on what the file says."""
    c = conf(**{'gesture.hold': 'switcher',
                'gesture.long_hold': 'suspend_to_kodi'})
    assert c.bindings['long_hold'] == 'none'
    assert c.bindings['hold'] == 'suspend_to_kodi', 'the rail forced it back'
    assert any('REJECTED' in w for w in c.warnings)


def test_the_rail_prefers_the_previous_working_binding():
    previous = GestureConfig(bindings=dict(DEFAULT_BINDINGS))
    got, warn = validate({'tap': 'none', 'double_tap': 'desktop',
                          'hold': 'none', 'hold_release': 'none',
                          'long_hold': 'none'}, previous=previous)
    assert got['hold'] == 'suspend_to_kodi'
    assert any('REJECTED' in w for w in warn)


def test_every_default_config_passes_the_rail_untouched():
    got, warn = validate(dict(DEFAULT_BINDINGS))
    assert got == DEFAULT_BINDINGS and warn == ()


# =========================================================================
# precedence: a gesture a stronger one would shadow is dropped, not doubled
# =========================================================================
def test_a_bound_hold_suppresses_the_long_hold():
    got, warn = suppress({'hold': 'suspend_to_kodi', 'long_hold': 'quit_game',
                          'tap': 'none', 'double_tap': 'none',
                          'hold_release': 'none'})
    assert got['long_hold'] == 'none'
    assert any('long_hold' in w for w in warn)


def test_an_unbound_hold_lets_the_long_hold_through():
    c = conf(**{'gesture.hold': 'none', 'gesture.long_hold': 'quit_game',
                'gesture.double_tap': 'suspend_to_kodi'})
    assert c.bindings['long_hold'] == 'quit_game'
    assert c.bindings['hold'] == 'none'


def test_a_bound_double_tap_suppresses_the_tap():
    c = conf(**{'gesture.tap': 'power_menu'})       # double_tap defaults bound
    assert c.bindings['tap'] == 'none'
    assert c.requested['tap'] == 'power_menu'
    assert any('tap' in w for w in c.warnings)


def test_an_unbound_double_tap_lets_the_tap_through():
    c = conf(**{'gesture.tap': 'power_menu', 'gesture.double_tap': 'none'})
    assert c.bindings['tap'] == 'power_menu'


def test_suppression_runs_again_after_the_rail_forces_the_hold():
    """Forcing hold back can newly shadow a long hold; the rail must not
    leave a binding behind that can never fire."""
    c = conf(**{'gesture.hold': 'tv_toggle', 'gesture.long_hold': 'none',
                'gesture.double_tap': 'none', 'gesture.tap': 'desktop'})
    assert c.bindings['hold'] == 'suspend_to_kodi'
    assert c.bindings['tap'] == 'desktop', 'double_tap is free, so tap stands'


# =========================================================================
# the accessors
# =========================================================================
def test_action_for_and_bound_to():
    c = GestureConfig()
    assert c.action_for('hold') == 'suspend_to_kodi'
    assert c.action_for('nonsense') == 'none'
    assert c.bound_to('suspend_to_kodi') == ('hold',)
    assert c.bound_to('quit_game') == ()


# =========================================================================
# the cache: cheap to poll, but it must SEE a change
# =========================================================================
def test_a_missing_file_is_the_default_console_not_an_error(tmp_path):
    p = str(tmp_path / 'never-written.xml')
    gestureconf.forget(p)
    c = load(p)
    assert c.bindings == DEFAULT_BINDINGS
    assert c.stamp is None and c.warnings == ()


def test_the_cache_returns_the_same_object_until_the_file_changes(tmp_path):
    p = tmp_path / 'settings.xml'
    p.write_text(written(**{'gesture.double_tap': 'desktop'}))
    gestureconf.forget(str(p))
    first = load(str(p))
    assert load(str(p)) is first, 'unchanged file: no re-parse'
    os.utime(p, (1, 1))
    assert load(str(p)) is not first, 'mtime moved: re-parsed'


def test_a_rewrite_is_picked_up(tmp_path):
    p = tmp_path / 'settings.xml'
    p.write_text(written(**{'gesture.hold': 'suspend_to_kodi'}))
    gestureconf.forget(str(p))
    assert load(str(p)).bindings['hold'] == 'suspend_to_kodi'
    p.write_text(written(**{'gesture.hold': 'none',
                            'gesture.double_tap': 'suspend_to_kodi'}))
    os.utime(p, (2, 2))
    assert load(str(p)).bindings['hold'] == 'none'


def test_an_unreadable_file_degrades_rather_than_raising(tmp_path):
    p = tmp_path / 'settings.xml'
    p.write_text(written(**{'gesture.hold': 'switcher'}))
    os.chmod(p, 0o000)
    gestureconf.forget(str(p))
    try:
        c = load(str(p))
    finally:
        os.chmod(p, 0o644)
    if os.geteuid() == 0:                    # pragma: no cover - root reads it
        pytest.skip('root can read a 000 file')
    assert c.bindings == DEFAULT_BINDINGS
    assert c.warnings


def test_load_never_raises_on_a_directory(tmp_path):
    gestureconf.forget(str(tmp_path))
    assert load(str(tmp_path)).bindings == DEFAULT_BINDINGS


def test_forget_clears_everything(tmp_path):
    p = tmp_path / 'settings.xml'
    p.write_text(written())
    load(str(p))
    gestureconf.forget()
    assert gestureconf._CACHE == {}


# =========================================================================
# the addon's settings.xml IS the contract - drift between the two is the
# whole failure mode this module exists to make impossible
# =========================================================================
@pytest.mark.skipif(not os.path.exists(ADDON_SETTINGS),
                    reason='the addon is not installed on this machine')
def test_the_addon_settings_page_offers_exactly_our_vocabulary():
    root = ET.parse(ADDON_SETTINGS).getroot()
    assert root.tag == 'settings' and root.get('version') == '1', \
        'the versioned schema, as every other Kodi 19+ addon on the box uses'
    ids = [s.get('id') for s in root.iter('setting')]
    # ui.* settings are the addon's own (the sheet-animation toggle landed
    # with the speedups batch); the contract this test guards is only the
    # gesture/timing vocabulary gestureconf reads.
    ours = [i for i in ids if not i.startswith('ui.')]
    assert ours == [f'gesture.{g}' for g in GESTURES] + \
        [f'timing.{t}' for t in DEFAULT_TIMINGS]
    for s in root.iter('setting'):
        sid = s.get('id')
        if not sid.startswith('gesture.'):
            continue
        options = [o.text for o in s.iter('option')]
        assert options == list(ACTIONS), f'{sid} offers {options}'
        default = s.find('default').text
        assert default == DEFAULT_BINDINGS[sid.split('.', 1)[1]], sid


@pytest.mark.skipif(not os.path.exists(ADDON_SETTINGS),
                    reason='the addon is not installed on this machine')
def test_the_sliders_agree_with_our_limits_and_defaults():
    root = ET.parse(ADDON_SETTINGS).getroot()
    for s in root.iter('setting'):
        sid = s.get('id')
        if not sid.startswith('timing.'):
            continue
        name = sid.split('.', 1)[1]
        lo, hi = gestureconf.TIMING_LIMITS[name]
        assert float(s.find('default').text) == DEFAULT_TIMINGS[name], sid
        assert float(s.find('constraints/minimum').text) == lo, sid
        assert float(s.find('constraints/maximum').text) == hi, sid


@pytest.mark.skipif(not os.path.exists(ADDON_SETTINGS),
                    reason='the addon is not installed on this machine')
def test_every_label_the_page_uses_exists_in_the_language_file():
    """A label id with no string renders as an empty row on the TV."""
    po = os.path.join(os.path.dirname(ADDON_SETTINGS), 'language',
                      'resource.language.en_gb', 'strings.po')
    have = set()
    for line in open(po, encoding='utf-8'):
        if line.startswith('msgctxt "#'):
            have.add(line.split('#', 1)[1].split('"', 1)[0])
    root = ET.parse(ADDON_SETTINGS).getroot()
    want = set()
    for el in root.iter():
        for attr in ('label', 'help'):
            v = el.get(attr)
            if v and v.isdigit():
                want.add(v)
        if el.tag == 'heading' and (el.text or '').strip().isdigit():
            want.add(el.text.strip())
    assert want and not (want - have), sorted(want - have)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
