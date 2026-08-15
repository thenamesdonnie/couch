"""switcher-overlay's pure logic, headless. The X/gamescope half is proved
by the live session and (like pipd) can gain a headless rig later; what
lives here is everything that decides - input decode, device discovery,
focus movement, row filtering, layout - because a wrong decision on the
couch is a player stuck in a menu."""
import importlib.util
import json
import os
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


# -- the resident lifecycle: pure plans -----------------------------------
def test_show_steps_frame_waits_only_when_suspended():
    """The frame-wait exists so pause-snap's capture is rail-free; it must
    run only when a show actually maps over a fresh suspend - never at
    daemon start, never on a plain show."""
    steps = mod.show_steps(mapped=False, flag_busy=False, suspended=True)
    assert ('frame_wait',) in steps
    steps = mod.show_steps(mapped=False, flag_busy=False, suspended=False)
    assert ('frame_wait',) not in steps


def test_show_steps_order_is_pads_wait_map_draw_flag_joystick():
    steps = mod.show_steps(False, False, True)
    names = [s[0] for s in steps]
    assert names == ['open_pads', 'frame_wait', 'map', 'draw',
                     'write_flag', 'joystick']
    assert steps[-1] == ('joystick', False)
    # The flag means MAPPED: it may not exist before the sheet does.
    assert names.index('write_flag') > names.index('draw')


def test_show_steps_stand_down_when_mapped_or_busy():
    """Idempotent show (the second double-tap rule) and the singleton."""
    assert mod.show_steps(mapped=True, flag_busy=False, suspended=True) == []
    assert mod.show_steps(mapped=False, flag_busy=True, suspended=True) == []


def test_finish_steps_picked_unmaps_then_activates_then_unflags():
    """unmap first (the rail leaves before the world changes), the flag
    LAST (guard-vs-resume: it must hold the pad through the activate)."""
    steps, code = mod.finish_steps('picked', {'id': '0x1', 'paused': False})
    names = [s[0] for s in steps]
    assert code == 0
    assert names.index('unmap') < names.index('activate') \
        < names.index('remove_flag')
    assert ('joystick', True) in steps


def test_finish_steps_paused_pick_leaves_the_joystick_alone():
    """game-launch's resume owns the routing there."""
    steps, code = mod.finish_steps('picked', {'id': '0x2', 'paused': True})
    assert code == 0
    assert ('joystick', True) not in steps


def test_finish_steps_cancel_resumes_the_paused_row():
    paused = {'id': '0x2', 'paused': True}
    steps, code = mod.finish_steps('cancel', paused_row=paused)
    assert code == 1
    assert ('activate', '0x2') in steps
    assert ('joystick', True) not in steps


def test_finish_steps_cancel_without_resume_restores_kodi():
    steps, code = mod.finish_steps('cancel', paused_row={'id': '0x2'},
                                   resume_on_cancel=False)
    assert code == 1
    assert not any(s[0] == 'activate' for s in steps)
    assert ('joystick', True) in steps
    steps, code = mod.finish_steps('cancel', paused_row=None)
    assert ('joystick', True) in steps


def test_finish_steps_superseded_touches_nothing_but_the_flag():
    """The PS button's own resume already routed the pad."""
    steps, code = mod.finish_steps('superseded')
    assert code == 3
    assert [s[0] for s in steps] == ['unmap', 'remove_flag', 'close_pads']


def test_finish_steps_stopped_leaves_kodi_usable():
    steps, code = mod.finish_steps('stopped')
    assert code == 1
    assert ('joystick', True) in steps


def test_finish_steps_power_dispatches_then_restores():
    steps, code = mod.finish_steps('power', 'all_off')
    assert code == 0
    names = [s[0] for s in steps]
    assert names.index('unmap') < names.index('power') \
        < names.index('remove_flag')


def test_first_paused_and_merge_focus():
    rows = mod.pick_rows(ROWS)
    assert mod.first_paused(rows)['id'] == '0x5800002'
    assert mod.first_paused([{'id': 'x', 'title': 'x'}]) is None
    # Focus follows the row id across a refresh's reorder...
    old = [{'id': 'a', 'title': 'A'}, {'id': 'b', 'title': 'B'}]
    new = [{'id': 'b', 'title': 'B'}, {'id': 'a', 'title': 'A'}]
    assert mod.merge_focus(old, new, 0) == 1
    # ...and a vanished row falls back to initial_focus.
    assert mod.merge_focus(old, [{'id': 'c', 'title': 'C'}], 0) == 0
    assert mod.merge_focus([], [{'id': 'c', 'title': 'C'}], 0) == 0


# -- the resident lifecycle: control surface ------------------------------
def test_parse_command_rejects_malformed_lines():
    """pipd's rule: the socket must never crash the daemon."""
    import pytest
    for bad in ('not json', '[]', '{}', '{"cmd": 3}'):
        with pytest.raises(ValueError):
            mod.parse_command(bad)
    assert mod.parse_command('{"cmd": "show"}')['cmd'] == 'show'


def test_show_reply_two_stage_ack():
    ok, should = mod.show_reply({'cmd': 'show'}, ':1', False, False)
    assert ok['ok'] and should
    ok, should = mod.show_reply({'cmd': 'show', 'display': ':1'},
                                ':1', False, False)
    assert ok['ok'] and should


def test_show_reply_is_idempotent_while_mapped():
    reply, should = mod.show_reply({'cmd': 'show'}, ':1', True, False)
    assert reply['ok'] and reply.get('mapped') and not should


def test_show_reply_stands_down_for_a_foreign_rail_or_wrong_display():
    reply, should = mod.show_reply({'cmd': 'show'}, ':1', False, True)
    assert not reply['ok'] and not should
    reply, should = mod.show_reply({'cmd': 'show', 'display': ':2'},
                                   ':1', False, False)
    assert not reply['ok'] and not should


class FakeConn:
    def __init__(self, line):
        self.line = line.encode()
        self.sent = b''

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def settimeout(self, t):
        pass

    def recv(self, n):
        return self.line

    def sendall(self, b):
        self.sent += b


class FakeSock:
    def __init__(self, conn):
        self.conn = conn

    def accept(self):
        return self.conn, None


def test_resident_show_is_acked_then_mapped_from_the_loop(monkeypatch):
    """The two-stage ack: the poker (couchd mid-pass) gets its reply in
    milliseconds; the frame-wait and the map happen afterwards, from the
    run loop, on the resident's own time."""
    monkeypatch.setattr(mod, 'rail_already_up', lambda: False)
    rail = mod.ResidentRail(':1')
    conn = FakeConn(json.dumps({'cmd': 'show', 'display': ':1',
                                'resume_on_cancel': False}))
    rail.sock = FakeSock(conn)
    assert rail.handle_conn() is None        # never an outcome while hidden
    assert json.loads(conn.sent)['accepted']
    assert rail.pending_show is not None     # the loop maps, not the ack
    assert rail.resume_on_cancel is False    # the client's flag came along


def test_resident_second_show_is_a_no_op(monkeypatch):
    monkeypatch.setattr(mod, 'rail_already_up', lambda: False)
    rail = mod.ResidentRail(':1')
    rail.mapped = True
    conn = FakeConn(json.dumps({'cmd': 'show'}))
    rail.sock = FakeSock(conn)
    assert rail.handle_conn() is None
    assert json.loads(conn.sent)['mapped']
    assert rail.pending_show is None


def test_resident_quit_stops_and_unwinds_a_mapped_deck(monkeypatch):
    monkeypatch.setattr(mod, 'rail_already_up', lambda: False)
    rail = mod.ResidentRail(':1')
    rail.mapped = True
    conn = FakeConn(json.dumps({'cmd': 'quit'}))
    rail.sock = FakeSock(conn)
    assert rail.handle_conn() == 'stopped'   # deck_loop ends -> finish_steps
    assert rail.stop['sig'] is True          # ...and the daemon retires
    rail2 = mod.ResidentRail(':1')
    rail2.sock = FakeSock(FakeConn(json.dumps({'cmd': 'quit'})))
    assert rail2.handle_conn() is None       # hidden: nothing to unwind
    assert rail2.stop['sig'] is True


def test_resident_malformed_line_is_answered_not_fatal(monkeypatch):
    rail = mod.ResidentRail(':1')
    conn = FakeConn('not json at all')
    rail.sock = FakeSock(conn)
    assert rail.handle_conn() is None
    assert json.loads(conn.sent)['ok'] is False


# -- the resident lifecycle: steps against the world ----------------------
class FakeOverlay:
    out_w, out_h = 320, 180

    def __init__(self, events):
        self.events = events

    def map_now(self):
        self.events.append('map')

    def unmap_now(self):
        self.events.append('unmap')


def _runner(monkeypatch, tmp_path, events):
    flag = tmp_path / 'switcher-overlay'
    monkeypatch.setattr(mod, 'OVERLAY_FLAG', str(flag))
    monkeypatch.delenv('SWITCHER_OVERLAY_NO_PAD', raising=False)
    monkeypatch.setattr(mod, 'open_pads',
                        lambda: [os.open(os.devnull, os.O_RDONLY)])
    monkeypatch.setattr(mod, 'wait_for_fresh_frame',
                        lambda: events.append('frame_wait') or True)
    monkeypatch.setattr(mod, 'kodi_joystick',
                        lambda v: events.append(('joystick', v)))
    monkeypatch.setattr(mod, 'activate',
                        lambda i: events.append(('activate', i)))
    monkeypatch.setattr(mod, 'power_dispatch',
                        lambda k: events.append(('power', k)))
    ov = FakeOverlay(events)
    runner = mod.StepRunner(
        ov, ov.unmap_now,
        lambda: (flag.write_text(str(os.getpid())),
                 events.append('flag'))[-1],
        lambda: events.append('draw'))
    return runner, flag


def test_step_runner_show_then_finish_holds_the_flag_contract(
        monkeypatch, tmp_path):
    """The whole map/unmap state machine end to end: the flag exists
    exactly while the rail is mapped-and-owning-the-pad, and survives
    through the activate (guard-vs-resume) before clearing."""
    import os as _os
    events = []
    runner, flag = _runner(monkeypatch, tmp_path, events)
    assert runner.run(mod.show_steps(False, False, True))
    assert flag.exists(), 'mapped -> announced'
    assert events == ['frame_wait', 'map', 'draw', 'flag',
                      ('joystick', False)]
    events.clear()
    steps, code = mod.finish_steps('picked', {'id': '0x9', 'paused': True})
    assert runner.run(steps)
    assert events == ['unmap', ('activate', '0x9')]
    assert not flag.exists(), 'unmapped -> silent'
    assert runner.fds == [], 'pads handed back'


def test_step_runner_aborts_the_show_when_no_pad_exists(
        monkeypatch, tmp_path):
    """Mapping a deck nothing can drive would strand the room: no pad, no
    map, no flag - couchd's effect check times out and says so."""
    events = []
    runner, flag = _runner(monkeypatch, tmp_path, events)
    monkeypatch.setattr(mod, 'open_pads', lambda: [])
    assert not runner.run(mod.show_steps(False, False, True))
    assert 'map' not in events
    assert not flag.exists()


def test_step_runner_unmap_failure_still_clears_the_flag(
        monkeypatch, tmp_path):
    """A dead nested display (gamescope teardown mid-deck) must not leave
    a flag that says the rail owns a pad it can no longer read."""
    events = []
    runner, flag = _runner(monkeypatch, tmp_path, events)
    assert runner.run(mod.show_steps(False, False, False))
    def boom():
        raise RuntimeError('display gone')
    runner._unmap = boom
    steps, _ = mod.finish_steps('stopped')
    assert runner.run(steps)
    assert not flag.exists()


# -- deck_loop outcomes (headless: no X, no pads) -------------------------
def test_deck_loop_superseded_when_the_suspend_clears(monkeypatch,
                                                      tmp_path):
    monkeypatch.setattr(mod, 'SUSPENDED_FLAG',
                        str(tmp_path / 'never-written'))
    rows = [{'id': 'a', 'title': 'A'}]
    out = mod.deck_loop(None, rows, {}, {}, [], {'sig': False})
    assert out == ('superseded', None, rows)


def test_deck_loop_stopped_on_signal(monkeypatch, tmp_path):
    flag = tmp_path / 'game-suspended'
    flag.write_text('x')
    monkeypatch.setattr(mod, 'SUSPENDED_FLAG', str(flag))
    rows = [{'id': 'a', 'title': 'A'}]
    out = mod.deck_loop(None, rows, {}, {}, [], {'sig': True})
    assert out == ('stopped', None, rows)


def test_deck_loop_refresh_once_redraws_and_keeps_the_eye(monkeypatch):
    """The post-map refresh trues up the pre-baked sheet (the fresh
    ' · paused' marker) without yanking focus off the row the player is
    already aiming at."""
    calls = []
    monkeypatch.setattr(
        mod, 'compose_strip',
        lambda rows, focus, *a, **k: calls.append((rows, focus)) or 'sheet')
    drawn = []

    class Ov:
        out_w, out_h = 10, 10

        def draw(self, s):
            drawn.append(s)

    old = [{'id': 'a', 'title': 'A'}, {'id': 'b', 'title': 'B'}]
    new = [{'id': 'b', 'title': 'B'},
           {'id': 'a', 'title': 'A', 'paused': True}]
    out = mod.deck_loop(Ov(), old, {}, {}, [], {'sig': True},
                        refresh_once=lambda: (new, {}, {}))
    assert out == ('stopped', None, new)
    assert drawn == ['sheet']
    assert calls[0] == (new, 1)      # focus followed row id 'a'


# -- thumb cache and the baked sheet --------------------------------------
def test_thumb_cache_fetches_once_and_survives_a_failed_refetch():
    fetched = []

    def fetch(row):
        fetched.append(row['id'])
        return 'img-%s' % row['id'] if len(fetched) < 3 else None

    tc = mod.ThumbCache(fetch=fetch)
    row = {'id': 'a', 'thumb': '/api/art/winthumb?id=a'}
    assert tc.get(row) == 'img-a'
    assert tc.get(row) == 'img-a'
    assert fetched == ['a'], 'second get was the cache'
    assert tc.refetch(row) == 'img-a'        # refetch 2 succeeded
    assert tc.refetch(row) == 'img-a'        # refetch 3 failed -> cache
    assert fetched == ['a', 'a', 'a']


def test_thumb_cache_a_fresh_freeze_frame_misses_by_construction():
    """pause-snap stamps each capture's filename, so a new suspend's row
    carries a NEW thumb url and get() fetches it even at show time."""
    fetched = []
    tc = mod.ThumbCache(fetch=lambda r: fetched.append(r['thumb']) or 'img')
    tc.get({'id': 'a', 'thumb': '/paused/bb__100.jpg'})
    tc.get({'id': 'a', 'thumb': '/paused/bb__200.jpg'})
    assert fetched == ['/paused/bb__100.jpg', '/paused/bb__200.jpg']


def test_bake_bgra_swizzles_rgba():
    from PIL import Image
    img = Image.new('RGBA', (2, 1), (10, 20, 30, 40))
    w, h, bgra = mod.bake_bgra(img)
    assert (w, h) == (2, 1)
    assert bgra[:4] == bytes([30, 20, 10, 40])


# -- the client half ------------------------------------------------------
def test_resident_show_talks_to_a_live_socket(monkeypatch, tmp_path):
    import socket as pysocket
    import threading
    path = str(tmp_path / 'rail.sock')
    monkeypatch.setattr(mod, 'RESIDENT_SOCK', path)
    server = pysocket.socket(pysocket.AF_UNIX, pysocket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)
    got = {}

    def serve():
        conn, _ = server.accept()
        got['msg'] = json.loads(conn.recv(4096).decode())
        conn.sendall(b'{"ok": true, "accepted": true}\n')
        conn.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    assert mod.resident_show(':1', resume_on_cancel=False) is True
    t.join(2)
    assert got['msg'] == {'cmd': 'show', 'display': ':1',
                          'resume_on_cancel': False}
    server.close()


def test_resident_show_false_when_refused_or_absent(monkeypatch, tmp_path):
    import socket as pysocket
    import threading
    monkeypatch.setattr(mod, 'RESIDENT_SOCK', str(tmp_path / 'nothing'))
    assert mod.resident_show(':1') is False   # no socket -> one-shot path
    path = str(tmp_path / 'rail.sock')
    monkeypatch.setattr(mod, 'RESIDENT_SOCK', path)
    server = pysocket.socket(pysocket.AF_UNIX, pysocket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)

    def serve():
        conn, _ = server.accept()
        conn.recv(4096)
        conn.sendall(b'{"ok": false, "error": "display mismatch"}\n')
        conn.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    assert mod.resident_show(':1') is False   # refused -> one-shot path
    t.join(2)
    server.close()
