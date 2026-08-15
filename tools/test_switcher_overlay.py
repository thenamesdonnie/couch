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
