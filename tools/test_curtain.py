#!/usr/bin/env python3
"""Tests for tools/curtain, the suspend/resume freeze-frame overlay.

NOTHING here touches the live console. The X tests spawn their OWN Xvfb on a
free display and every one of them asserts that DISPLAY is not :0 before it
draws anything; the daemon's pid/fifo/status/log all live under tmp_path via
COUCH_CURTAIN_DIR. No service is started or stopped, and ~/couch is only ever
read.

The X-dependent tests SKIP (with a reason) when Xvfb, python-xlib or an image
maker is missing, so the suite stays green on a box without them.

Run:  couchd/.venv/bin/python -m pytest tools/test_curtain.py -q
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, 'curtain')
SCREEN_W, SCREEN_H = 1280, 720


def load(script='curtain', modname='curtain_under_test'):
    if not os.path.exists(TOOL):
        pytest.skip('tools/curtain not present')
    loader = importlib.machinery.SourceFileLoader(modname, TOOL)
    spec = importlib.util.spec_from_loader(modname, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)          # imports only; opens no display
    return mod


@pytest.fixture(scope='module')
def curtain():
    return load()


# =========================================================================
# pure logic - no X server, no daemon, no files outside tmp_path
# =========================================================================
def test_parse_show_defaults(curtain):
    opts = curtain.parse_args(['show', 'frame.jpg'])
    assert opts['cmd'] == 'show'
    assert opts['timeout'] == curtain.DEFAULT_TIMEOUT
    assert opts['image'] == os.path.abspath('frame.jpg')


@pytest.mark.parametrize('argv', [['show', 'f.jpg', '--timeout', '2.5'],
                                  ['show', '--timeout=2.5', 'f.jpg'],
                                  ['show', '--timeout', '2.5', 'f.jpg']])
def test_parse_show_timeout_both_spellings(curtain, argv):
    assert curtain.parse_args(argv)['timeout'] == 2.5


def test_parse_fade_and_the_no_argument_verbs(curtain):
    assert curtain.parse_args(['fade'])['duration'] == curtain.DEFAULT_FADE
    assert curtain.parse_args(['fade', '--duration', '0.2'])['duration'] == 0.2
    assert curtain.parse_args(['clear']) == {'cmd': 'clear'}
    assert curtain.parse_args(['status']) == {'cmd': 'status'}


@pytest.mark.parametrize('argv, why', [
    ([], 'no command at all'),
    (['show'], 'show without an image'),
    (['show', 'a.jpg', 'b.jpg'], 'two images'),
    (['show', 'a.jpg', '--timeout'], 'flag with no value'),
    (['show', 'a.jpg', '--timeout', 'soon'], 'non-numeric timeout'),
    (['show', 'a.jpg', '--timeout', '999'], 'timeout past the cap'),
    (['show', 'a.jpg', '--timeout', '0'], 'timeout below the floor'),
    (['fade', 'now'], 'fade with a positional'),
    (['clear', 'all'], 'clear with a positional'),
    (['wibble'], 'unknown verb'),
])
def test_parse_rejects(curtain, argv, why):
    with pytest.raises(curtain.Usage):
        curtain.parse_args(argv)


def test_bad_arguments_exit_two_not_one(curtain):
    """Exit 2 is 'you typed it wrong'; exit 1 is 'no curtain'. A caller that
    throws away non-zero does not care, but an operator does."""
    r = subprocess.run([sys.executable, TOOL, 'wibble'], capture_output=True)
    assert r.returncode == 2


@pytest.mark.parametrize('iw, ih, expect', [
    (1280, 720, (1280, 720, 0, 0)),          # exact fit, no letterbox
    (960, 540, (1280, 720, 0, 0)),           # pause-snap's 16:9 frame, upscaled
    (640, 640, (720, 720, 280, 0)),          # square: pillarboxed, centred
    (1000, 100, (1280, 128, 0, 296)),        # very wide: letterboxed, centred
    (100, 1000, (72, 720, 604, 0)),          # very tall: pillarboxed, centred
])
def test_fit_box(curtain, iw, ih, expect):
    got = curtain.fit_box(iw, ih, SCREEN_W, SCREEN_H)
    assert got == expect
    w, h, x, y = got
    assert 0 <= x and 0 <= y and x + w <= SCREEN_W and y + h <= SCREEN_H
    # centred to within the odd pixel integer division leaves over
    assert abs((SCREEN_W - w - 2 * x)) <= 1 and abs((SCREEN_H - h - 2 * y)) <= 1


@pytest.mark.parametrize('args', [(0, 100, 1280, 720), (100, 0, 1280, 720),
                                  (100, 100, 0, 720), (-1, 10, 1280, 720)])
def test_fit_box_refuses_nonsense(curtain, args):
    with pytest.raises(curtain.CurtainError):
        curtain.fit_box(*args)


CLAIM_IN_A_CHILD = """
import importlib.machinery, importlib.util, sys, time
loader = importlib.machinery.SourceFileLoader('m', sys.argv[1])
spec = importlib.util.spec_from_loader('m', loader)
m = importlib.util.module_from_spec(spec); loader.exec_module(m)
fd = m.claim_pidfile(sys.argv[2])
print('GOT' if fd is not None else 'REFUSED', flush=True)
if fd is not None and len(sys.argv) > 3:
    time.sleep(float(sys.argv[3]))
"""


def test_pidfile_claim_is_exclusive_while_the_holder_lives(curtain, tmp_path):
    pidfile = str(tmp_path / 'curtain.pid')
    script = tmp_path / 'claim.py'
    script.write_text(CLAIM_IN_A_CHILD)
    holder = subprocess.Popen([sys.executable, str(script), TOOL, pidfile, '5'],
                              stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == 'GOT'
        assert int(open(pidfile).read()) == holder.pid
        # A second daemon must NOT be able to put up a second overlay.
        assert curtain.claim_pidfile(pidfile) is None
    finally:
        holder.terminate()
        holder.wait(timeout=5)


def test_pidfile_claim_takes_over_from_a_daemon_that_died_hard(curtain, tmp_path):
    """The flock, not the pid, is the test: a killed curtain leaves its
    pidfile behind and the next show must not be blocked by a corpse."""
    pidfile = str(tmp_path / 'curtain.pid')
    script = tmp_path / 'claim.py'
    script.write_text(CLAIM_IN_A_CHILD)
    dead = subprocess.Popen([sys.executable, str(script), TOOL, pidfile, '30'],
                            stdout=subprocess.PIPE, text=True)
    assert dead.stdout.readline().strip() == 'GOT'
    dead.kill()
    dead.wait(timeout=5)
    assert os.path.exists(pidfile)             # stale, and still claimable
    fd = curtain.claim_pidfile(pidfile)
    assert fd is not None
    assert int(open(pidfile).read()) == os.getpid()
    os.close(fd)


def test_load_frame_refuses_missing_and_empty(curtain, tmp_path):
    empty = tmp_path / 'empty.jpg'
    empty.write_bytes(b'')
    with pytest.raises(curtain.CurtainError):
        curtain.load_frame(str(tmp_path / 'nope.jpg'), 320, 200)
    with pytest.raises(curtain.CurtainError):
        curtain.load_frame(str(empty), 320, 200)


# =========================================================================
# the X tests: our own Xvfb, never the console's server
# =========================================================================
def _have_xlib():
    try:
        import Xlib.display            # noqa: F401
        return True
    except ImportError:
        return False


def _free_display():
    for n in range(93, 110):
        if not os.path.exists(f'/tmp/.X{n}-lock'):
            return n
    return None


@pytest.fixture(scope='module')
def xdisplay():
    """A private Xvfb. HARD RULE: the console's real server is never touched,
    so this both refuses :0 and only ever hands back a display it started."""
    if not shutil.which('Xvfb'):
        pytest.skip('Xvfb is not installed')
    if not _have_xlib():
        pytest.skip('python-Xlib is not importable by this interpreter')
    n = _free_display()
    if n is None:
        pytest.skip('no free display number in :93-:109')
    name = f':{n}'
    assert name != ':0'
    proc = subprocess.Popen(
        ['Xvfb', name, '-screen', '0', f'{SCREEN_W}x{SCREEN_H}x24',
         '-nolisten', 'tcp'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import Xlib.display
    deadline = time.time() + 15
    while time.time() < deadline:
        if proc.poll() is not None:
            pytest.skip(f'Xvfb exited immediately ({proc.returncode})')
        try:
            d = Xlib.display.Display(name)
            d.close()
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.terminate()
        pytest.skip('Xvfb never became connectable')
    yield name
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def rig(xdisplay, tmp_path):
    """One curtain sandbox: private display, private runtime dir, and a
    teardown that leaves no daemon behind whatever the test did."""
    class Rig:
        display = xdisplay
        dir = str(tmp_path / 'run')
        env = None

        def run(self, *args, timeout=20, extra_env=None):
            return subprocess.run([sys.executable, TOOL, *args],
                                  capture_output=True, text=True,
                                  timeout=timeout,
                                  env=dict(self.env, **(extra_env or {})))

        def pixel(self, x, y):
            """(r, g, b) straight off the curtain window - the only honest
            test that the image really landed, in the right channel order."""
            import Xlib.display
            from Xlib import X
            d = Xlib.display.Display(self.display)
            try:
                wid = self.windows()[0][0]
                w = d.create_resource_object('window', wid)
                img = w.get_image(x, y, 1, 1, X.ZPixmap, 0xffffffff)
                data = img.data if isinstance(img.data, bytes) else bytes(img.data)
                return data[2], data[1], data[0]        # BGRX on the wire
            finally:
                d.close()

        def windows(self):
            """Every curtain window currently on the server, top to bottom."""
            import Xlib.display
            d = Xlib.display.Display(self.display)
            try:
                out = []
                for c in d.screen().root.query_tree().children:
                    try:
                        cls = c.get_wm_class() or ('', '')
                    except Exception:
                        continue
                    if cls[0] == 'couch-curtain':
                        out.append((c.id, c.get_geometry(), c.get_attributes()))
                return out
            finally:
                d.close()

        def wait_gone(self, seconds):
            end = time.time() + seconds
            while time.time() < end:
                if not self.windows():
                    return time.time()
                time.sleep(0.02)
            return None

        def pidfile(self):
            return os.path.join(self.dir, 'couch-curtain.pid')

        def status(self):
            with open(os.path.join(self.dir, 'couch-curtain.status')) as f:
                return json.load(f)

    r = Rig()
    os.makedirs(r.dir, exist_ok=True)
    r.env = dict(os.environ, DISPLAY=xdisplay, COUCH_CURTAIN_DIR=r.dir)
    r.env.pop('XAUTHORITY', None)
    yield r
    r.run('clear', timeout=10)
    try:
        pid = int(open(r.pidfile()).read())
        os.kill(pid, signal.SIGKILL)
    except (OSError, ValueError):
        pass


@pytest.fixture
def frame(tmp_path):
    """A 16:9 jpg the size pause-snap writes. Pillow if there is one, else
    ffmpeg - the same two paths the tool itself picks from."""
    path = str(tmp_path / 'frame.jpg')
    try:
        from PIL import Image
        Image.linear_gradient('L').convert('RGB').resize((960, 540)).save(
            path, quality=80)
        return path
    except ImportError:
        pass
    if not shutil.which('ffmpeg'):
        pytest.skip('neither Pillow nor ffmpeg to make a test frame')
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    'testsrc=size=960x540:duration=1', '-frames:v', '1', path],
                   check=True, capture_output=True)
    return path


@pytest.fixture
def tall_frame(tmp_path):
    """A portrait image, so a replace is visibly a different picture (and
    exercises the letterbox arithmetic against a real screen)."""
    path = str(tmp_path / 'tall.jpg')
    try:
        from PIL import Image
        Image.new('RGB', (300, 900), (200, 10, 10)).save(path)
        return path
    except ImportError:
        pass
    if not shutil.which('ffmpeg'):
        pytest.skip('neither Pillow nor ffmpeg to make a test frame')
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=c=red:size=300x900', '-frames:v', '1', path],
                   check=True, capture_output=True)
    return path


def test_show_maps_a_fullscreen_override_redirect_curtain(rig, frame):
    r = rig.run('show', frame, '--timeout', '8')
    assert r.returncode == 0, r.stderr
    wins = rig.windows()
    assert len(wins) == 1
    _wid, geom, attrs = wins[0]
    assert (geom.width, geom.height) == (SCREEN_W, SCREEN_H)
    assert (geom.x, geom.y) == (0, 0)
    assert attrs.map_state == 2                # IsViewable
    assert attrs.override_redirect == 1        # the WM never manages it
    st = rig.status()
    assert st['image'] == frame and st['mapped'] and st['shows'] == 1


def test_show_sets_the_names_both_stacks_whitelist_on(rig, frame):
    assert rig.run('show', frame, '--timeout', '8').returncode == 0
    import Xlib.display
    d = Xlib.display.Display(rig.display)
    try:
        net = d.intern_atom('_NET_WM_NAME')
        wid = rig.windows()[0][0]
        w = d.create_resource_object('window', wid)
        assert w.get_wm_class() == ('couch-curtain', 'couch-curtain')
        assert w.get_full_property(net, 0).value.decode() == 'couch-curtain'
    finally:
        d.close()


def test_fade_removes_it_within_the_duration_plus_margin(rig, frame):
    assert rig.run('show', frame, '--timeout', '8').returncode == 0
    start = time.time()
    r = rig.run('fade', '--duration', '0.4')
    assert r.returncode == 0, r.stderr
    assert rig.windows() == [], 'fade returned with the curtain still up'
    assert time.time() - start < 0.4 + 2.0
    assert not os.path.exists(rig.pidfile())


def test_the_watchdog_kills_a_curtain_nobody_faded(rig, frame):
    """THE contract: no fade, no clear, no caller - and it still goes away."""
    assert rig.run('show', frame, '--timeout', '1').returncode == 0
    assert rig.windows(), 'nothing was up to watchdog'
    start = time.time()
    gone = rig.wait_gone(6)
    assert gone is not None, 'the curtain outlived its timeout'
    took = gone - start
    assert took >= 0.5, f'it vanished in {took:.2f}s - that is not the watchdog'
    assert took < 1 + 3.0, f'watchdog took {took:.2f}s'
    assert not os.path.exists(rig.pidfile())


def test_a_second_show_replaces_the_image_on_the_same_window(rig, frame,
                                                             tall_frame):
    assert rig.run('show', frame, '--timeout', '8').returncode == 0
    first = rig.windows()
    assert len(first) == 1
    r = rig.run('show', tall_frame, '--timeout', '8')
    assert r.returncode == 0, r.stderr
    second = rig.windows()
    assert len(second) == 1, 'a second show created a second window'
    assert second[0][0] == first[0][0], 'the window was recreated, not reused'
    st = rig.status()
    assert st['shows'] == 2 and st['image'] == tall_frame


def _assert_red_frame_on_black_bars(rig):
    r, g, b = rig.pixel(SCREEN_W // 2, SCREEN_H // 2)
    assert r > 150 and g < 60 and b < 60, f'centre pixel is {(r, g, b)}, not red'
    for x in (2, SCREEN_W - 3):                # the pillarbox, left and right
        assert max(rig.pixel(x, SCREEN_H // 2)) < 12, f'bar at x={x} is not black'


def test_the_frame_is_drawn_letterboxed_on_black(rig, tall_frame):
    """A 300x900 red frame on a 1280x720 screen: red down the middle, black
    bars either side. Catches both a swapped channel order and a stretch."""
    assert rig.run('show', tall_frame, '--timeout', '8').returncode == 0
    _assert_red_frame_on_black_bars(rig)


def test_the_ffmpeg_fallback_draws_the_same_frame(rig, tall_frame, tmp_path):
    """The Pillow-less box. A stub PIL that raises on import forces the one
    fallback, and the result on screen must be indistinguishable."""
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg is not installed')
    stub = tmp_path / 'nopil'
    stub.mkdir()
    (stub / 'PIL.py').write_text('raise ImportError("no pillow on this box")\n')
    r = rig.run('show', tall_frame, '--timeout', '8',
                extra_env={'PYTHONPATH': str(stub)})
    assert r.returncode == 0, r.stderr
    assert len(rig.windows()) == 1
    _assert_red_frame_on_black_bars(rig)


def test_sigterm_tears_it_down(rig, frame):
    assert rig.run('show', frame, '--timeout', '20').returncode == 0
    pid = int(open(rig.pidfile()).read())
    os.kill(pid, signal.SIGTERM)
    assert rig.wait_gone(5) is not None, 'SIGTERM left the curtain up'
    assert not os.path.exists(rig.pidfile())


def test_clear_destroys_it_instantly(rig, frame):
    assert rig.run('show', frame, '--timeout', '20').returncode == 0
    start = time.time()
    assert rig.run('clear').returncode == 0
    assert rig.windows() == []
    assert time.time() - start < 2.0
    assert not os.path.exists(rig.pidfile())


def test_a_garbage_image_exits_nonzero_and_leaves_nothing(rig, tmp_path):
    junk = tmp_path / 'not-really.jpg'
    junk.write_text('this is not a jpeg\n')
    r = rig.run('show', str(junk), '--timeout', '8')
    assert r.returncode != 0
    assert r.stderr.strip(), 'a failure must say why on stderr'
    assert rig.windows() == [], 'a broken image left a window on screen'
    assert not os.path.exists(rig.pidfile())


def test_a_missing_image_exits_nonzero_without_starting_a_daemon(rig, tmp_path):
    r = rig.run('show', str(tmp_path / 'nope.jpg'))
    assert r.returncode != 0
    assert rig.windows() == []
    assert not os.path.exists(rig.pidfile())


def test_fade_and_status_with_nothing_up(rig):
    """fade/clear are idempotent - the wanted end state (no curtain) already
    holds, so they exit 0. status is a query, so it exits non-zero when there
    is nothing to report."""
    assert rig.run('fade').returncode == 0
    assert rig.run('clear').returncode == 0
    assert rig.run('status').returncode != 0
