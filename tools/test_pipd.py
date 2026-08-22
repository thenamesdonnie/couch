#!/usr/bin/env python3
"""Tests for pipd - the movable picture-in-picture overlay.

The geometry is pure and is tested directly. The X side is tested for real
against an Xvfb server, because the interesting failures there (no 32-bit
visual, a child that does not actually move) are exactly the ones a mock
would hide.

NO REAL DISPLAY IS TOUCHED. Every X test runs on its own Xvfb on a high
display number; nothing here can reach :0, which is the television.

    .venv/bin/python -m pytest tools/test_pipd.py -q
"""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_loader(
    'pipd', importlib.machinery.SourceFileLoader('pipd', os.path.join(HERE, 'pipd')))
pipd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pipd)

OUT = (3840, 2160)          # the television, at the resolution it runs at


# =========================================================================
# geometry
# =========================================================================
def test_a_picture_cannot_be_smaller_than_the_floor():
    w, h = pipd.clamp_size(10, 6, *OUT)
    assert h == pytest.approx(pipd.MIN_FRACTION * 2160, abs=1)
    # Tolerance is a pixel's worth of rounding, not slack: the result is whole
    # pixels, so a 173-pixel-tall box cannot hold 10:6 exactly.
    assert w / h == pytest.approx(10 / 6, abs=2 / h), 'aspect must survive'


def test_a_picture_cannot_swallow_the_game():
    w, h = pipd.clamp_size(3800, 2138, *OUT)
    assert h == pytest.approx(pipd.MAX_FRACTION * 2160, abs=1)


def test_the_cap_is_measured_on_the_short_edge():
    """A 21:9 clip capped on WIDTH would be far taller than the cap intends.
    The short edge is the one that decides how much of the game is hidden."""
    w, h = pipd.clamp_size(2100, 900, *OUT)
    assert h <= pipd.MAX_FRACTION * 2160 + 1
    assert w / h == pytest.approx(2100 / 900, rel=1e-3)


def test_the_picture_can_never_leave_the_screen():
    assert pipd.clamp_position(-500, -500, 640, 360, *OUT) == (0, 0)
    assert pipd.clamp_position(99999, 99999, 640, 360, *OUT) == (3200, 1800)


def test_a_near_edge_drop_snaps_flush():
    x, y = pipd.snap(30, 25, 640, 360, *OUT)
    assert (x, y) == (0, 0), 'a thumb-width gap should tidy up to the corner'


def test_snapping_is_per_axis():
    """Close on one axis and deliberate on the other must not drag the
    deliberate axis to an edge it was nowhere near."""
    x, y = pipd.snap(10, 900, 640, 360, *OUT)
    assert x == 0 and y == 900


def test_a_deliberate_middle_drop_is_left_alone():
    assert pipd.snap(1500, 900, 640, 360, *OUT) == (1500, 900)


def test_width_alone_gives_a_sixteen_nine_box():
    x, y, w, h = pipd.from_normalised({'nx': 0.6, 'ny': 0.1, 'nw': 0.25}, *OUT)
    assert w / h == pytest.approx(16 / 9, rel=1e-3)


def test_normalised_survives_a_round_trip():
    geom = {'nx': 0.62, 'ny': 0.07, 'nw': 0.3}
    x, y, w, h = pipd.from_normalised(geom, *OUT)
    back = pipd.to_normalised(x, y, w, h, *OUT)
    assert back['nx'] == pytest.approx(0.62, abs=0.002)
    assert back['nw'] == pytest.approx(0.30, abs=0.002)


def test_the_same_drag_lands_in_the_same_place_at_any_resolution():
    """The whole reason the phone speaks fractions: a mode change must not
    move the picture."""
    geom = {'nx': 0.6, 'ny': 0.1, 'nw': 0.25}
    a = pipd.to_normalised(*pipd.from_normalised(geom, 3840, 2160), 3840, 2160)
    b = pipd.to_normalised(*pipd.from_normalised(geom, 1920, 1080), 1920, 1080)
    assert a['nx'] == pytest.approx(b['nx'], abs=0.002)
    assert a['nw'] == pytest.approx(b['nw'], abs=0.002)


# =========================================================================
# the control protocol - it faces a no-auth LAN, so it must not be crashable
# =========================================================================
@pytest.mark.parametrize('line', ['', 'not json', '[]', '"a"', '{}',
                                  '{"cmd": 3}', '{"cmd": ""}', 'null'])
def test_rubbish_is_rejected_not_raised(line):
    with pytest.raises(ValueError):
        pipd.parse_command(line)


def test_a_good_line_parses():
    assert pipd.parse_command('{"cmd":"status"}')['cmd'] == 'status'


# =========================================================================
# command handling, against a fake overlay
# =========================================================================
class FakeOverlay:
    def __init__(self, out=OUT, geometry=(2400, 108, 1152, 648)):
        self.out_w, self.out_h = out
        self.geometry = geometry
        self.opacity = 1.0
        self.visible = True

    def place(self, x, y, w, h):
        self.geometry = (x, y, w, h)

    def set_opacity(self, f):
        self.opacity = f

    def set_visible(self, v):
        self.visible = v


def daemon(**kw):
    args = pipd.parse_args(['--player', 'none'])
    for k, v in kw.items():
        setattr(args, k, v)
    d = pipd.PipDaemon(args)
    d.overlay = FakeOverlay()
    return d


def test_place_in_normalised_coordinates_moves_the_picture():
    d = daemon()
    out = d.handle({'cmd': 'place', 'nx': 0.05, 'ny': 0.5, 'nw': 0.25,
                    'snap': False})
    assert out['pixels']['x'] == pytest.approx(0.05 * 3840, abs=2)
    assert out['normalised']['nw'] == pytest.approx(0.25, abs=0.005)


def test_scale_grows_about_the_centre():
    """Resizing must not walk the picture across the screen, or a pinch
    on the phone turns into a drag."""
    d = daemon()
    x0, y0, w0, h0 = d.overlay.geometry
    cx0, cy0 = x0 + w0 / 2, y0 + h0 / 2
    d.handle({'cmd': 'scale', 'factor': 0.5})
    x, y, w, h = d.overlay.geometry
    assert (x + w / 2, y + h / 2) == pytest.approx((cx0, cy0), abs=2)


def test_corner_puts_it_flush_in_that_corner():
    d = daemon()
    out = d.handle({'cmd': 'corner', 'where': 'se'})
    px = out['pixels']
    assert px['x'] + px['w'] == 3840 and px['y'] + px['h'] == 2160


def test_an_unknown_corner_is_an_error_not_a_crash():
    with pytest.raises(ValueError):
        daemon().handle({'cmd': 'corner', 'where': 'up'})


def test_nudge_is_clamped_to_the_screen():
    d = daemon()
    out = d.handle({'cmd': 'nudge', 'dx': 99999, 'dy': 99999})
    assert out['pixels']['x'] + out['pixels']['w'] == 3840


def test_hide_then_show_round_trips():
    d = daemon()
    assert d.handle({'cmd': 'hide'})['visible'] is False
    assert d.overlay.visible is False
    assert d.handle({'cmd': 'show'})['visible'] is True


def test_unknown_command_is_an_error():
    with pytest.raises(ValueError):
        daemon().handle({'cmd': 'explode'})


# =========================================================================
# transport, against a fake player
# =========================================================================
class FakePlayer:
    """Stands in for Player: answers the mpv IPC surface pipd actually uses."""

    def __init__(self):
        self.kind = 'mpv'
        self.sent = []
        self.props = {'pause': False, 'time-pos': 12.0, 'duration': 60.0,
                      'volume': 80.0, 'mute': False}

    def alive(self):
        return True

    def command(self, *words):
        self.sent.append(words)
        if words[0] == 'get_property':
            return self.props[words[1]]
        if words[0] == 'set_property':
            self.props[words[1]] = words[2]

    def snapshot(self):
        return {'paused': self.props['pause'],
                'position': self.props['time-pos'],
                'duration': self.props['duration'],
                'volume': self.props['volume'],
                'muted': self.props['mute']}


def playing_daemon():
    d = daemon()
    d.player = FakePlayer()
    return d


def test_pause_and_play_are_explicit_never_a_toggle():
    d = playing_daemon()
    assert d.handle({'cmd': 'pause'})['paused'] is True
    # A repeat must be a no-op that lands in the same state, not an undo.
    assert d.handle({'cmd': 'pause'})['paused'] is True
    assert d.handle({'cmd': 'play'})['paused'] is False


def test_seek_is_relative_seconds():
    d = playing_daemon()
    d.handle({'cmd': 'seek', 'seconds': -10})
    assert ('seek', -10.0, 'relative') in d.player.sent


@pytest.mark.parametrize('bad', [{'seconds': 4000}, {'seconds': 'nan'},
                                 {'seconds': float('nan')}])
def test_a_silly_seek_is_refused(bad):
    with pytest.raises(ValueError):
        playing_daemon().handle({'cmd': 'seek', **bad})


def test_volume_is_bounded():
    d = playing_daemon()
    assert d.handle({'cmd': 'volume', 'value': 35})['volume'] == 35.0
    for bad in (-1, 101, float('inf')):
        with pytest.raises(ValueError):
            d.handle({'cmd': 'volume', 'value': bad})


def test_mute_round_trips():
    d = playing_daemon()
    assert d.handle({'cmd': 'mute', 'value': True})['muted'] is True
    assert d.handle({'cmd': 'mute', 'value': False})['muted'] is False


def test_transport_without_a_player_is_an_error_not_a_crash():
    for cmd in ('play', 'pause', 'seek', 'volume', 'mute'):
        with pytest.raises(ValueError):
            daemon().handle({'cmd': cmd})


def test_status_carries_the_transport_state():
    st = playing_daemon().handle({'cmd': 'status'})
    assert st['paused'] is False and st['muted'] is False
    assert st['position'] == 12.0 and st['duration'] == 60.0
    assert st['volume'] == 80.0


# =========================================================================
# the X side, for real, on a throwaway Xvfb
# =========================================================================
@pytest.fixture
def xvfb():
    display = ':94'
    proc = subprocess.Popen(['Xvfb', display, '-screen', '0', '1920x1080x24'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            from Xlib import display as xd
            xd.Display(display).close()
            break
        except Exception:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.skip('Xvfb did not come up')
    yield display
    proc.terminate()
    proc.wait(timeout=5)


def test_the_overlay_is_fullscreen_and_carries_the_atom(xvfb):
    """The two things gamescope actually looks for. If either is wrong the
    plane either never appears or appears at the wrong size, and both look
    identical from the sofa: nothing happened."""
    ov = pipd.Overlay(xvfb)
    try:
        ov.create(1200, 60, 600, 338)
        geom = ov.parent.get_geometry()
        assert (geom.width, geom.height) == (1920, 1080), 'plane must be output-sized'
        prop = ov.parent.get_full_property(
            ov.dpy.get_atom(pipd.OVERLAY_PROP), 0)
        assert prop is not None and list(prop.value) == [1]
    finally:
        ov.close()


def test_the_overlay_uses_a_32_bit_visual(xvfb):
    """Depth 24 here means an opaque fullscreen rectangle over the game."""
    ov = pipd.Overlay(xvfb)
    try:
        ov.create(100, 100, 400, 225)
        assert ov.parent.get_geometry().depth == 32
        assert ov.child.get_geometry().depth == 32
    finally:
        ov.close()


def test_moving_the_child_is_what_moves_the_picture(xvfb):
    """The load-bearing behaviour of the whole design: the PARENT never
    moves (gamescope ignores its position anyway), the CHILD does."""
    ov = pipd.Overlay(xvfb)
    try:
        ov.create(100, 100, 400, 225)
        ov.place(900, 700, 640, 360)
        child = ov.child.get_geometry()
        assert (child.x, child.y, child.width, child.height) == (900, 700, 640, 360)
        parent = ov.parent.get_geometry()
        assert (parent.x, parent.y) == (0, 0)
        assert (parent.width, parent.height) == (1920, 1080)
    finally:
        ov.close()


def test_opacity_is_written_where_gamescope_reads_it(xvfb):
    ov = pipd.Overlay(xvfb)
    try:
        ov.create(100, 100, 400, 225)
        ov.set_opacity(0.5)
        prop = ov.parent.get_full_property(
            ov.dpy.get_atom('_NET_WM_WINDOW_OPACITY'), 0)
        assert prop is not None
        assert list(prop.value)[0] == pytest.approx(0xffffffff * 0.5, rel=1e-3)
    finally:
        ov.close()


def test_the_daemon_serves_its_socket_end_to_end(xvfb, tmp_path):
    """Start it the way the couch server will, drive it the way the phone
    will, and read back what the phone would draw."""
    sock_path = str(tmp_path / 'pip.sock')
    proc = subprocess.Popen(
        [sys.executable, os.path.join(HERE, 'pipd'), '--display', xvfb,
         '--player', 'none', '--socket', sock_path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(100):
            if os.path.exists(sock_path):
                break
            if proc.poll() is not None:
                pytest.fail(f'pipd died: {proc.stdout.read()}')
            time.sleep(0.05)
        else:
            pytest.fail('control socket never appeared')

        def send(msg):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(sock_path)
            s.sendall((json.dumps(msg) + '\n').encode())
            reply = s.recv(65536).decode()
            s.close()
            return json.loads(reply)

        status = send({'cmd': 'status'})
        assert status['ok'] and status['output'] == {'w': 1920, 'h': 1080}

        moved = send({'cmd': 'place', 'nx': 0.5, 'ny': 0.5, 'nw': 0.2,
                      'snap': False})
        assert moved['pixels']['x'] == pytest.approx(960, abs=3)

        assert send({'cmd': 'corner', 'where': 'sw'})['pixels']['x'] == 0
        assert send({'cmd': 'garbage'})['ok'] is False
        assert send({'cmd': 'quit'})['stopping'] is True
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()
