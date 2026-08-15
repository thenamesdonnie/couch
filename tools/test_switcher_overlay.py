"""switcher-overlay's pure logic, headless. The X/gamescope half is proved
by the live session and (like pipd) can gain a headless rig later; what
lives here is everything that decides - input decode, device discovery,
focus movement, row filtering, layout - because a wrong decision on the
couch is a player stuck in a menu."""
import importlib.util
import json
import struct
import sys
from pathlib import Path

spec = importlib.util.spec_from_loader('switcher_overlay', loader=None)
mod = importlib.util.module_from_spec(spec)
src = (Path(__file__).parent / 'switcher-overlay').read_text()
exec(compile(src, 'switcher-overlay', 'exec'), mod.__dict__)
sys.modules['switcher_overlay'] = mod

EV_KEY, EV_ABS = mod.EV_KEY, mod.EV_ABS


def ev(etype, code, value):
    return struct.pack(mod.EVENT_FMT, 0, 0, etype, code, value)


# -- device discovery -----------------------------------------------------
DEVICES = """\
I: Bus=0005 Vendor=054c Product=0ce6 Version=8100
N: Name="DualSense Wireless Controller"
H: Handlers=event18 js1

I: Bus=0005 Vendor=054c Product=0ce6 Version=8100
N: Name="DualSense Wireless Controller Motion Sensors"
H: Handlers=event19

I: Bus=0005 Vendor=054c Product=0ce6 Version=8100
N: Name="DualSense Wireless Controller Touchpad"
H: Handlers=event20 mouse2

I: Bus=0011 Vendor=0001 Product=0001 Version=ab41
N: Name="AT Translated Set 2 keyboard"
H: Handlers=sysrq kbd event3 leds
"""


def test_parse_devices_pairs_names_with_event_nodes():
    got = mod.parse_devices(DEVICES)
    assert ('DualSense Wireless Controller', '/dev/input/event18') in got
    assert ('AT Translated Set 2 keyboard', '/dev/input/event3') in got


def test_pad_nodes_keeps_the_buttons_and_drops_the_side_nodes():
    got = mod.pad_nodes(mod.parse_devices(DEVICES))
    assert got == ['/dev/input/event18']


# -- event decode + action mapping ---------------------------------------
def test_decode_events_drops_a_trailing_partial():
    buf = ev(EV_KEY, mod.BTN_SOUTH, 1) + b'\x00' * 5
    assert mod.decode_events(buf) == [(EV_KEY, mod.BTN_SOUTH, 1)]


def test_buttons_map_and_releases_do_not_fire():
    st = mod.PadState()
    assert mod.pad_action((EV_KEY, mod.BTN_SOUTH, 1), st) == 'select'
    assert mod.pad_action((EV_KEY, mod.BTN_SOUTH, 0), st) is None
    assert mod.pad_action((EV_KEY, mod.BTN_EAST, 1), st) == 'back'


def test_dpad_hat_maps_edges_and_centre_is_silent():
    st = mod.PadState()
    assert mod.pad_action((EV_ABS, mod.ABS_HAT0X, -1), st) == 'left'
    assert mod.pad_action((EV_ABS, mod.ABS_HAT0X, 0), st) is None
    assert mod.pad_action((EV_ABS, mod.ABS_HAT0X, 1), st) == 'right'


def test_dpad_hat_vertical_maps_up_and_down():
    st = mod.PadState()
    assert mod.pad_action((EV_ABS, mod.ABS_HAT0Y, -1), st) == 'up'
    assert mod.pad_action((EV_ABS, mod.ABS_HAT0Y, 0), st) is None
    assert mod.pad_action((EV_ABS, mod.ABS_HAT0Y, 1), st) == 'down'


def test_stick_y_edge_detects_and_maps_vertically():
    st = mod.PadState()
    assert mod.pad_action((EV_ABS, mod.ABS_Y, 255), st) == 'down'
    assert mod.pad_action((EV_ABS, mod.ABS_Y, 250), st) is None
    assert mod.pad_action((EV_ABS, mod.ABS_Y, 128), st) is None
    assert mod.pad_action((EV_ABS, mod.ABS_Y, 0), st) == 'up'
    assert mod.pad_action((EV_ABS, mod.ABS_Y, -30000), st) is None  # held


def test_stick_axes_engage_independently():
    """A diagonal that latched X must not eat Y's move (and vice versa)."""
    st = mod.PadState()
    assert mod.pad_action((EV_ABS, mod.ABS_X, 255), st) == 'right'
    assert mod.pad_action((EV_ABS, mod.ABS_Y, 255), st) == 'down'
    assert mod.pad_action((EV_ABS, mod.ABS_X, 128), st) is None
    assert mod.pad_action((EV_ABS, mod.ABS_X, 0), st) == 'left'
    assert mod.pad_action((EV_ABS, mod.ABS_Y, 250), st) is None  # still held


def test_stick_8bit_edge_detects_one_move_per_deflection():
    """hid-playstation reports ABS_X 0..255 centred 128: a held deflection
    is a stream of large values and must be ONE move until it returns to
    centre."""
    st = mod.PadState()
    assert mod.pad_action((EV_ABS, mod.ABS_X, 255), st) == 'right'
    assert mod.pad_action((EV_ABS, mod.ABS_X, 250), st) is None
    assert mod.pad_action((EV_ABS, mod.ABS_X, 128), st) is None
    assert mod.pad_action((EV_ABS, mod.ABS_X, 0), st) == 'left'


def test_stick_16bit_pads_still_work():
    st = mod.PadState()
    assert mod.pad_action((EV_ABS, mod.ABS_X, 30000), st) == 'right'
    assert mod.pad_action((EV_ABS, mod.ABS_X, 500), st) is None
    assert mod.pad_action((EV_ABS, mod.ABS_X, -30000), st) == 'left'


# -- focus + rows ---------------------------------------------------------
def test_move_focus_wraps_both_ways():
    assert mod.move_focus(0, 'left', 3) == 2
    assert mod.move_focus(2, 'right', 3) == 0
    assert mod.move_focus(1, 'select', 3) == 1


def test_move_power_clamps_at_the_ends():
    """The XML's power bar hands its ends to a hidden spotify list, which
    parks focus in place - so the overlay clamps, never wraps."""
    assert mod.move_power(0, 'left') == 0
    assert mod.move_power(0, 'right') == 1
    assert mod.move_power(2, 'right') == 2
    assert mod.move_power(2, 'left') == 1


def test_deck_move_hops_between_rail_and_power_and_remembers():
    st = mod.deck_move('rail', 1, 0, 0, 'up', 3)
    assert st == ('power', 1, 0, 0)
    st = mod.deck_move(*st, 'right', 3)
    assert st == ('power', 1, 1, 0)           # capsule moved, card held
    st = mod.deck_move(*st, 'up', 3)
    assert st[0] == 'power'                   # top edge is a wall
    st = mod.deck_move(*st, 'down', 3)
    assert st == ('rail', 1, 1, 0)            # both indices survived
    st = mod.deck_move(*st, 'down', 3)
    assert st[0] == 'rail'                    # bottom edge is a wall
    st = mod.deck_move(*st, 'left', 3)
    assert st == ('rail', 0, 1, 0)            # rail still wraps its own way


def test_deck_move_without_spotify_clamps_the_power_bar():
    """n_media=0 (no live session): the strip is the power bar alone and
    its ends are walls, pixel-model-identical to the pre-spotify deck."""
    assert mod.deck_move('power', 0, 0, 0, 'left', 3) == ('power', 0, 0, 0)
    assert mod.deck_move('power', 0, 2, 0, 'right', 3) == ('power', 0, 2, 0)


def test_deck_move_with_spotify_joins_the_strip():
    """The XML's _join_strip repair: power and spotify act as ONE wrapping
    strip - rightwards entry lands on the first pill, the screen-edge wrap
    lands on the last, and never wherever the bar last was."""
    n = 3
    st = mod.deck_move('power', 0, 2, 1, 'right', 3, n)
    assert st == ('media', 0, 2, 0)           # off the end -> first pill
    st = mod.deck_move(*st, 'right', 3, n)
    assert st == ('media', 0, 2, 1)           # interior move
    st = mod.deck_move('media', 0, 2, 2, 'right', 3, n)
    assert st == ('power', 0, 0, 2)           # screen-edge wrap -> capsule 0
    st = mod.deck_move('media', 0, 1, 0, 'left', 3, n)
    assert st == ('power', 0, 2, 0)           # leftwards entry -> last capsule
    st = mod.deck_move('power', 0, 0, 1, 'left', 3, n)
    assert st == ('media', 0, 0, 2)           # screen-edge wrap -> last pill
    st = mod.deck_move('media', 2, 0, 1, 'down', 3, n)
    assert st == ('rail', 2, 0, 1)            # ondown 9000, indices held
    assert mod.deck_move('media', 0, 0, 1, 'up', 3, n)[0] == 'media'
    assert mod.deck_move('rail', 0, 0, 1, 'up', 3, n) \
        == ('power', 0, 0, 1)                 # rail's onup is 9010, never 9020


def test_spotify_active_gates_exactly_like_default_py():
    assert not mod.spotify_active(None)
    assert not mod.spotify_active({})
    assert not mod.spotify_active({'active': False})
    assert mod.spotify_active({'active': True})


def test_media_items_face_the_current_state_play_pause_first():
    assert mod.media_items({'active': True, 'playing': True}) == [
        ('Pause', 'icon-pause.png'), ('Previous', 'icon-prev.png'),
        ('Next', 'icon-next.png')]
    assert mod.media_items({'active': True})[0] == ('Play', 'icon-play.png')


def test_media_click_uses_explicit_verbs_and_intent():
    """Never PlayPause: spotifyd's read-back lags the command it just
    took, so the verb comes from the pill's state and the pill's next
    state from intent. Skips leave play/pause alone."""
    assert mod.media_click({'playing': True}, 0) == ('pause', False)
    assert mod.media_click({'playing': False}, 0) == ('play', True)
    assert mod.media_click({'playing': True}, 1) == ('previous', True)
    assert mod.media_click({'playing': False}, 2) == ('next', False)


def test_now_playing_label_joins_track_and_artist():
    assert mod.now_playing_label({'track': 'Hunter', 'artist': 'Sakuraba'}) \
        == 'Hunter - Sakuraba'
    assert mod.now_playing_label({'track': 'Hunter'}) == 'Hunter'
    assert mod.now_playing_label({}) == 'Spotify'


def test_power_actions_match_the_kodi_dialog():
    """The bar is a clone of default.py's POWER_ACTIONS - if the addon
    grows or renames an action, this must fail until the overlay follows."""
    src = (Path(__file__).parent.parent / 'kodi-addons'
           / 'script.couch.switcher' / 'default.py').read_text()
    assert mod.POWER_ADDON in src
    for label, key in mod.POWER_ACTIONS:
        assert '("%s", "%s")' % (label, key) in src


def test_card_label_keeps_the_paused_marker():
    assert mod.card_label({'title': 'shadPS4 v0.17.0 | CUSA00900 - '
                                    'Bloodborne <01.09> · paused',
                           'paused': True}) == 'Bloodborne · paused'
    assert mod.card_label({'title': 'Desktop'}) == 'Desktop'


ROWS = {'windows': [
    {'id': '0x2600080', 'title': 'Kodi', 'kodi': True, 'cls': 'Kodi'},
    {'id': '0x5800002', 'title': 'shadPS4 v0.17.0 | CUSA00900 - Bloodborne '
                                 '<01.09> · paused',
     'cls': 'gamescope', 'paused': True},
    {'id': 'desktop', 'title': 'Desktop', 'cls': 'desktop'},
    {'id': '', 'title': 'stray'},
]}


def test_pick_rows_drops_idless_strays_and_keeps_the_rest():
    rows = mod.pick_rows(ROWS)
    assert [r['id'] for r in rows] == ['0x2600080', '0x5800002', 'desktop']


def test_initial_focus_is_the_first_unpaused_row():
    rows = mod.pick_rows(ROWS)
    assert mod.initial_focus(rows) == 0
    flipped = [dict(rows[1]), dict(rows[0])]
    assert mod.initial_focus(flipped) == 1
    assert mod.initial_focus([dict(rows[1])]) == 0   # only the paused game


def test_short_label_extracts_the_game_name():
    assert mod.short_label('shadPS4 v0.17.0 | CUSA00900 - Bloodborne '
                           '<01.09> · paused') == 'Bloodborne'
    assert mod.short_label('Kodi') == 'Kodi'


def test_layout_centres_and_never_overlaps():
    n = 4
    strip_w, strip_h, tile_w, tile_h, gap, xs = mod.layout(n, 3840, 2160)
    assert len(xs) == n
    for (x1, _), (x2, _) in zip(xs, xs[1:]):
        assert x2 - x1 == tile_w + gap, 'even pitch'
        assert x2 > x1 + tile_w, 'no overlap'
    assert xs[-1][0] + tile_w < strip_w
    assert tile_h < strip_h


def test_rows_seam_reads_a_file(tmp_path, monkeypatch):
    p = tmp_path / 'rows.json'
    p.write_text(json.dumps(ROWS))
    monkeypatch.setenv('SWITCHER_OVERLAY_ROWS', str(p))
    assert [r['id'] for r in mod.fetch_rows()] == \
        ['0x2600080', '0x5800002', 'desktop']


def test_spotify_seam_reads_a_file(tmp_path, monkeypatch):
    p = tmp_path / 'spotify.json'
    p.write_text(json.dumps({'active': True, 'playing': True,
                             'track': 'Hunter'}))
    monkeypatch.setenv('SWITCHER_OVERLAY_SPOTIFY', str(p))
    assert mod.fetch_spotify()['track'] == 'Hunter'


def test_spotify_fetch_is_never_fatal(monkeypatch):
    """An unreachable /api/spotify must cost the bar, never the deck."""
    monkeypatch.delenv('SWITCHER_OVERLAY_SPOTIFY', raising=False)
    monkeypatch.setattr(mod, 'API', 'http://127.0.0.1:1')
    assert mod.fetch_spotify() == {}
