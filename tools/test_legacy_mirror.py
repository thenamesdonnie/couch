#!/usr/bin/env python3
"""The 6 Aug deploy-day fixes, tested against the REPO MIRRORS.

Unlike test_legacy_yield.py (which pins the LIVE scripts in ~/.local/bin),
these load ~/couch/legacy-mirror/* - the staged copies the main session
reviews and deploys. Until that deploy the two disagree by exactly these
fixes; afterwards this file and that one exercise the same bytes.

What is pinned, all from the acceptance night (docs/acceptance-20260806.md):

  1. steam-input-guard leaves NOTHING behind on ANY exit path - normal
     return, exception, signal. A leaked /tmp/vpad.fifo makes every later
     guard run with vpad_started:false (menu-closing silently dead for both
     stacks); the leaked pidfile put 13 stale invariant records in one differ
     run. Removal is inode-guarded so a superseded guard can never unlink a
     successor's fresh fifo. The supersession protocol itself is pinned
     unchanged (ruling: leak fix only).
  2. the watcher's yielded would-freeze names the pids couchd actually froze:
     running_pids() read after couchd's SIGSTOPs recorded pids=[] on every
     yielded freeze (the 10 gating SET-MISMATCH rows).
  3. the couch-curtain overlay is transparent to the watcher's foreground
     classification, and the frozen-game-visible repair never raises Kodi
     over it (the whitelist tools/curtain's header demands). The guard's
     invariant 2 likewise never restacks Kodi against the curtain - while
     its top_window() keeps REPORTING the curtain, so invariant 3 cannot
     see the frozen game beneath it.

Every path is an injected tmp_path one - never live /tmp (the 5 Aug rule).

Run:  couchd/.venv/bin/pytest tools/test_legacy_mirror.py -q
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import types

import pytest

HOME = os.path.expanduser('~')
MIRROR = os.path.join(HOME, 'couch', 'legacy-mirror')
WATCHER_SRC = os.path.join(MIRROR, 'pad-home-watcher')
GUARD_SRC = os.path.join(MIRROR, 'steam-input-guard')
GAME_LAUNCH_SRC = os.path.join(MIRROR, 'game-launch')

sys.path.insert(0, os.path.join(HOME, 'couch', 'couchd'))
import owns                                                   # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


watcher = _load('pad_home_watcher_mirror', WATCHER_SRC)
guard = _load('steam_input_guard_mirror', GUARD_SRC)


# =========================================================================
# 1. steam-input-guard: cleanup on every exit path
# =========================================================================
class _Run:
    stdout = ''


@pytest.fixture
def gbox(tmp_path, monkeypatch):
    """A guard with every real-world touchpoint moved under tmp_path and
    every effect recorded: no vpad, no X, no signals, no live /tmp."""
    monkeypatch.setattr(guard, 'LOG', str(tmp_path / 'guard.log'))
    monkeypatch.setattr(guard, 'INTENTS', str(tmp_path / 'intents.jsonl'))
    monkeypatch.setattr(guard, 'PIDFILE', str(tmp_path / 'guard.pid'))
    monkeypatch.setattr(guard, 'VPAD_FIFO', str(tmp_path / 'vpad.fifo'))
    monkeypatch.setattr(guard, 'GUIDE_LATCH', str(tmp_path / 'guide-handled'))
    monkeypatch.setattr(guard, 'SESSION', str(tmp_path / 'game-session'))
    monkeypatch.setattr(guard, 'SUSPENDED', str(tmp_path / 'game-suspended'))
    monkeypatch.setattr(guard, 'yielded', lambda *a, **k: False)
    monkeypatch.setattr(guard, 'read_log', lambda: '')
    top = [('Kodi', 'Kodi')]                  # what top_window() reports
    screen_calls = []
    monkeypatch.setattr(guard, 'Screen', lambda: types.SimpleNamespace(
        focused_class=lambda: '', top_window=lambda: top[0],
        focus_kodi=lambda: screen_calls.append('focus_kodi')))
    guard._cleanup.update({'vpad': False, 'mode': None, 'done': False})

    runs, registered, handlers = [], [], []
    monkeypatch.setattr(
        guard.subprocess, 'run',
        lambda cmd, **k: (runs.append(list(cmd)), _Run())[1])
    # atexit/signal are process-global; recorded instead so the test process
    # neither keeps a callback into a torn-down tmp_path nor loses its own
    # SIGINT handling.
    monkeypatch.setattr(guard.atexit, 'register',
                        lambda fn: registered.append(fn) or fn)
    monkeypatch.setattr(guard.signal, 'signal',
                        lambda sig, fn: handlers.append(sig))

    class Box:
        dir = tmp_path
        pidfile = tmp_path / 'guard.pid'
        fifo = tmp_path / 'vpad.fifo'

        @staticmethod
        def intents():
            path = tmp_path / 'intents.jsonl'
            if not path.exists():
                return []
            return [json.loads(l) for l in path.read_text().splitlines() if l]
    Box.runs, Box.registered, Box.handlers = runs, registered, handlers
    Box.top, Box.screen_calls = top, screen_calls
    return Box


def test_a_normal_window_removes_its_own_pidfile(gbox, monkeypatch):
    """The leak reproduced on every run of the acceptance night: the pidfile
    only ever went away on SIGTERM. A zero-second window exits normally."""
    monkeypatch.setattr(sys, 'argv', ['steam-input-guard', 'kodi', '0'])
    guard.main()
    assert not gbox.pidfile.exists()
    verbs = [i['verb'] for i in gbox.intents()]
    assert verbs == ['window_open', 'window_close']      # behaviour unchanged
    # ...and the paths that never reach the finally are covered too.
    assert guard.cleanup_exit in gbox.registered
    assert set(gbox.handlers) == {guard.signal.SIGTERM, guard.signal.SIGINT,
                                  guard.signal.SIGHUP}


def test_an_exception_mid_window_still_cleans_up(gbox, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['steam-input-guard', 'game', '5'])
    monkeypatch.setattr(guard, 'suspended_now',
                        lambda: (_ for _ in ()).throw(RuntimeError('boom')))
    with pytest.raises(RuntimeError):
        guard.main()
    assert not gbox.pidfile.exists()


def test_cleanup_quits_the_vpad_and_guarantees_the_fifo_gone(gbox):
    """`vpad quit` normally removes the fifo itself - but a quit that misses
    (daemon already dead, stale vpad pidfile) leaves it, and a stale fifo is
    what made every later guard log vpad_started:false. The guard now
    guarantees it, not the daemon."""
    gbox.fifo.write_text('')            # the daemon's removal missed
    guard._cleanup.update({'vpad': True, 'mode': 'kodi'})
    guard.cleanup_exit()
    assert [guard.VPAD, 'quit'] in gbox.runs
    assert not gbox.fifo.exists()
    assert guard._cleanup['vpad'] is False


def test_cleanup_never_touches_a_vpad_it_did_not_start(gbox):
    """A live fifo that belongs to somebody else (the fake-pad rig, a manual
    vpad) is not ours to destroy."""
    gbox.fifo.write_text('')
    guard._cleanup.update({'vpad': False, 'mode': 'kodi'})
    guard.cleanup_exit()
    assert [guard.VPAD, 'quit'] not in gbox.runs
    assert gbox.fifo.exists()


def test_cleanup_leaves_a_successors_pidfile_alone(gbox):
    """supersede() means a newer guard may already own the file; deleting it
    would break THAT guard's supersession."""
    gbox.pidfile.write_text('99999')
    guard.cleanup_exit()
    assert gbox.pidfile.read_text() == '99999'


def test_cleanup_runs_once_however_many_paths_reach_it(gbox):
    """finally + atexit + a signal handler all funnel here; only the first
    arrival acts."""
    gbox.pidfile.write_text(str(os.getpid()))
    guard.cleanup_exit()
    assert not gbox.pidfile.exists()
    gbox.pidfile.write_text(str(os.getpid()))     # a NEW guard's file now
    guard.cleanup_exit()
    assert gbox.pidfile.exists()


def test_sigterm_cleans_fifo_and_pidfile_then_exits(gbox, monkeypatch):
    exits = []
    monkeypatch.setattr(guard.os, '_exit', lambda code: exits.append(code))
    gbox.pidfile.write_text(str(os.getpid()))
    gbox.fifo.write_text('')
    guard._cleanup.update({'vpad': True, 'mode': 'game'})
    guard._on_term(guard.signal.SIGTERM, None)
    assert exits == [0]
    assert not gbox.pidfile.exists()
    assert not gbox.fifo.exists()
    last = gbox.intents()[-1]
    assert (last['verb'], last['args']['reason']) == ('window_close',
                                                      'superseded')


def test_cleanup_leaves_a_successors_fresh_fifo_alone(gbox, monkeypatch):
    """The ms-scale TOCTOU: superseded guard A's remove must never land on
    the fifo a successor's brand-new daemon just mkfifo'd at the same path -
    that daemon would block forever in open() on an unreachable inode while
    holding vpad's pidfile, which is the exact menu-closing-dead symptom
    this cleanup cures. The inode taken before the quit is the guard."""
    gbox.fifo.write_text('old')

    def run(cmd, **k):
        gbox.runs.append(list(cmd))
        if list(cmd) == [guard.VPAD, 'quit']:
            # The quit is delivered: the old daemon removes its fifo, and a
            # successor's fresh daemon immediately owns the path (a NEW
            # inode - created beside, swapped in, so the test cannot flake
            # on filesystem inode reuse).
            new = gbox.fifo.with_suffix('.new')
            new.write_text('new')
            os.replace(new, gbox.fifo)
        return _Run()
    monkeypatch.setattr(guard.subprocess, 'run', run)
    guard._cleanup.update({'vpad': True, 'mode': 'kodi'})
    guard.cleanup_exit()
    assert gbox.fifo.exists()
    assert gbox.fifo.read_text() == 'new'


def test_the_curtain_is_matched_on_name_or_class():
    assert guard.curtain_on_top('couch-curtain', 'couch-curtain') is True
    assert guard.curtain_on_top('couch-curtain', '') is True
    assert guard.curtain_on_top('', 'couch-curtain') is True
    assert guard.curtain_on_top('Kodi', 'Kodi') is False
    assert guard.curtain_on_top('', '') is False


def test_invariant_2_never_restacks_kodi_against_the_curtain(gbox,
                                                             monkeypatch):
    """A kodi-mode window with the curtain on top: without the skip the
    guard would raise Kodi ABOVE the override-redirect overlay within ~1s of
    it mapping, cosmetically defeating it on every suspend. The suspended
    flag is set too, pinning that invariant 3 stays quiet as well: the
    curtain must keep being what top_window() reports (topcls couch-curtain,
    not the steam_app beneath), or invariant 3 gains a reason to fire."""
    monkeypatch.setattr(sys, 'argv', ['steam-input-guard', 'kodi', '0.05'])
    monkeypatch.setattr(guard.time, 'sleep', lambda s: None)
    (gbox.dir / 'game-suspended').write_text('367520')
    gbox.top[0] = ('couch-curtain', 'couch-curtain')
    guard.main()
    assert gbox.screen_calls == []
    assert all(i['verb'] != 'show' for i in gbox.intents())


def test_invariant_2_still_raises_kodi_over_anything_else(gbox, monkeypatch):
    """...and the repair itself is intact: any other squatter still gets
    Kodi restacked over it."""
    monkeypatch.setattr(sys, 'argv', ['steam-input-guard', 'kodi', '0.05'])
    monkeypatch.setattr(guard.time, 'sleep', lambda s: None)
    gbox.top[0] = ('Steam', 'steamwebhelper')
    guard.main()
    assert 'focus_kodi' in gbox.screen_calls
    shows = [i for i in gbox.intents() if i['verb'] == 'show']
    assert shows and shows[0]['args']['reason'] == 'wanted window not on top'


def test_the_supersession_protocol_is_unchanged(gbox, monkeypatch):
    """Ruling R-a is Donnie's to make; today is the leak fix ONLY. A new
    guard still SIGTERMs whoever the pidfile names and claims the file."""
    kills = []
    monkeypatch.setattr(guard.os, 'kill',
                        lambda pid, sig: kills.append((pid, sig)))
    gbox.pidfile.write_text('4242')
    guard.supersede()
    assert kills == [(4242, 15)]
    assert gbox.pidfile.read_text() == str(os.getpid())
    rec = gbox.intents()[-1]
    assert rec['verb'] == 'kill'
    assert rec['args']['reason'] == 'superseded-by-newer-guard'


# =========================================================================
# 2 + 3. pad-home-watcher: yield pids, curtain whitelist
# =========================================================================
class Conf:
    """The bindings object the watcher's act() takes."""

    def __init__(self, **b):
        self.bindings = dict(watcher.DEFAULT_BINDINGS, **b)
        self.hold_seconds = 0.9
        self.double_tap_seconds = 0.35
        self.long_hold_seconds = 3.0

    def action_for(self, gesture):
        return self.bindings.get(gesture, 'none')


@pytest.fixture
def wbox(tmp_path, monkeypatch):
    """The watcher over a fake console: flags, logs and owns.conf under
    tmp_path, couchd's heartbeat ours to fake."""
    conf = tmp_path / 'owns.conf'
    conf.write_text('COUCHD_OWNS=""\n')
    monkeypatch.setenv('COUCHD_OWNS_FILE', str(conf))
    status = tmp_path / 'status.json'
    status.write_text('{"mode": "acting"}')
    monkeypatch.setenv('COUCHD_STATUS_FILE', str(status))
    owns._cache.clear()
    monkeypatch.setattr(watcher, 'LOG', str(tmp_path / 'watcher.log'))
    monkeypatch.setattr(watcher, 'INTENTS', str(tmp_path / 'intents.jsonl'))
    monkeypatch.setattr(watcher, 'SESSION', str(tmp_path / 'game-session'))
    monkeypatch.setattr(watcher, 'SUSPENDED', str(tmp_path / 'game-suspended'))
    monkeypatch.setattr(watcher, 'GUARD_PIDFILE', str(tmp_path / 'guard.pid'))
    watcher._owns_said[0] = None
    watcher._heartbeat_said[0] = None

    class Box:
        dir = tmp_path

        @staticmethod
        def own(*names):
            conf.write_text('COUCHD_OWNS="%s"\n' % ','.join(names))
            owns._cache.clear()

        @staticmethod
        def intents():
            path = tmp_path / 'intents.jsonl'
            if not path.exists():
                return []
            return [json.loads(l) for l in path.read_text().splitlines() if l]
    return Box


def test_a_yielded_would_freeze_names_the_pids_couchd_froze(wbox, monkeypatch):
    """The 10 gating SET-MISMATCH rows: couchd's SIGSTOPs land before the
    shadow line is written, so a running_pids() filter (drops 'T') recorded
    pids=[] on every yielded freeze. The would-do must name the whole set."""
    (wbox.dir / 'game-session').write_text('111 steam 367520\n')
    wbox.own('gestures')
    frozen = list(range(9001, 9019))                  # couchd's 18, all 'T'
    monkeypatch.setattr(watcher, 'game_pids', lambda: frozen)
    monkeypatch.setattr(watcher, 'running_pids', lambda pids: [])
    assert watcher.act('hold', Conf(), defer_handoff=True) is False
    rec = wbox.intents()[-1]
    assert rec['verb'] == 'freeze'
    assert rec['subject'] == '367520'
    assert rec['args']['pids'] == frozen              # not []
    assert rec['args']['yielded'] is True
    assert rec['args']['owner'] == 'couchd'


def test_the_acting_freeze_still_skips_already_frozen_pids(wbox, monkeypatch):
    """The counterpart pin: the ACTING path keeps its running_pids() filter -
    there it reads before it stops anything, and 'T' really does mean
    already-frozen by someone else."""
    (wbox.dir / 'game-session').write_text('111 steam 367520\n')
    kills = []
    monkeypatch.setattr(watcher, 'game_pids', lambda: [101, 102, 103])
    monkeypatch.setattr(watcher, 'running_pids', lambda pids: [101, 102])
    monkeypatch.setattr(watcher.os, 'kill',
                        lambda pid, sig: kills.append((pid, sig)))
    monkeypatch.setattr(watcher, 'supersede_guard', lambda *a, **k: None)
    monkeypatch.setattr(watcher, 'snapshot', lambda *a, **k: None)
    assert watcher.freeze_game() is True
    rec = [i for i in wbox.intents() if i['verb'] == 'freeze'][-1]
    assert rec['args']['pids'] == [101, 102]
    assert 'yielded' not in rec['args']
    assert sorted(p for p, _ in kills) == [101, 102]


def test_the_curtain_is_transparent_to_classification():
    assert watcher._foreground_class('couch-curtain') is False
    assert watcher._foreground_class('Kodi') is True
    assert watcher._foreground_class('steam_app_367520') is True
    assert watcher._foreground_class('') is False


def test_top_is_frozen_game_is_vetoed_while_the_curtain_is_up(monkeypatch):
    """Mid-handover the frozen game's window can still sit mapped BENEATH the
    curtain; transparency alone would read that as 'frozen game visible' and
    raise Kodi over the overlay. The curtain being up means the room sees the
    curtain, so there is nothing to repair."""
    monkeypatch.setattr(watcher, 'screen_classes',
                        lambda: ('steam_app_367520', 'steam_app_367520'))
    monkeypatch.setattr(watcher, 'curtain_visible', lambda: True)
    assert watcher.top_is_frozen_game() is False
    monkeypatch.setattr(watcher, 'curtain_visible', lambda: False)
    assert watcher.top_is_frozen_game() is True


def _quiet_repairs(monkeypatch, calls):
    def rec(name):
        def f(*a, **kw):
            calls.append((name, a, kw))
        return f
    for name in ('set_joystick', 'clear_snapshots', 'iconify_frozen_game',
                 'map_game_window', 'pad_to_kodi', 'focus_kodi'):
        monkeypatch.setattr(watcher, name, rec(name))
    monkeypatch.setattr(watcher, 'get_joystick', lambda: True)
    monkeypatch.setattr(watcher, 'game_pids', lambda: [])


def test_reconcile_never_raises_kodi_over_the_curtain(wbox, monkeypatch):
    """The whole repair, end to end: a suspended bigpicture flag (its normal
    pidless resting state) with a steam_app cls on top - but under a curtain."""
    calls = []
    _quiet_repairs(monkeypatch, calls)
    (wbox.dir / 'game-suspended').write_text('bigpicture')
    monkeypatch.setattr(watcher, 'screen_classes',
                        lambda: ('steam_app_367520', 'steam_app_367520'))
    monkeypatch.setattr(watcher, 'curtain_visible', lambda: True)
    watcher._reconcile(dry=False)
    assert calls == []                                # no repair of any kind


def test_reconcile_still_raises_kodi_without_the_curtain(wbox, monkeypatch):
    """...and the repair itself is intact once the curtain is gone."""
    calls = []
    _quiet_repairs(monkeypatch, calls)
    (wbox.dir / 'game-suspended').write_text('bigpicture')
    monkeypatch.setattr(watcher, 'screen_classes',
                        lambda: ('steam_app_367520', 'steam_app_367520'))
    monkeypatch.setattr(watcher, 'curtain_visible', lambda: False)
    watcher._reconcile(dry=False)
    assert ('focus_kodi', ('reconcile:frozen-game-visible',),
            {'dry': False}) in calls


# =========================================================================
# 4. game-launch: the focus python's success signal (and the BP-hide gates)
# =========================================================================
# The retry loop that consumes this signal is shell (focus_game_when_mapped)
# and its paths are the live ones, so it is covered by review + bash -n; what
# IS testable is the contract it terminates on: the embedded python exits 0
# only when it found and showed the wanted window, 1 when it did not - and
# the BP-hide fires exactly on the successful attempt. The python runs here
# against a fake Xlib (built under tmp_path, first on PYTHONPATH) and the
# GAME_PIDS_FILE / LEGACY_INTENTS_FILE seams, so no X and no live /tmp.

_FAKE_DISPLAY = '''
import json, os


class Prop:
    def __init__(self, value):
        self.value = value


class Tree:
    def __init__(self, children):
        self.children = children


class Attrs:
    def __init__(self, map_state):
        self.map_state = map_state


class Geom:
    def __init__(self, w, h):
        self.width, self.height = w, h


class Win:
    def __init__(self, spec):
        self.spec = spec

    def query_tree(self):
        return Tree([Win(s) for s in self.spec.get('children', [])])

    def get_attributes(self):
        return Attrs(2 if self.spec.get('mapped', True) else 0)

    def get_full_property(self, prop, _):
        if prop == '_NET_WM_PID' and self.spec.get('pid'):
            return Prop([self.spec['pid']])
        if prop == '_NET_WM_NAME' and self.spec.get('name'):
            return Prop(self.spec['name'].encode())
        return None

    def get_wm_class(self):
        cls = self.spec.get('cls')
        return (cls, cls) if cls else None

    def get_geometry(self):
        return Geom(self.spec.get('w', 1920), self.spec.get('h', 1080))

    def configure(self, **kw):
        pass

    def send_event(self, ev, **kw):
        pass


class _Screen:
    def __init__(self, root):
        self.root = root


class Display:
    def __init__(self):
        spec = json.load(open(os.environ['FAKE_SCREEN']))
        self._root = Win({'children': spec})

    def screen(self):
        return _Screen(self._root)

    def intern_atom(self, name):
        return name

    def set_input_focus(self, *a, **kw):
        pass

    def sync(self):
        pass
'''

_FAKE_X = '''
Above = 0
RevertToParent = 1
CurrentTime = 0
SubstructureRedirectMask = 1 << 20
SubstructureNotifyMask = 1 << 19
'''

_FAKE_PROTOCOL = '''
class _ClientMessage:
    def __init__(self, **kw):
        self.kw = kw


class event:
    ClientMessage = _ClientMessage
'''

KODI = {'cls': 'Kodi', 'name': 'Kodi'}
BP = {'cls': 'steamwebhelper', 'name': 'Steam Big Picture Mode'}
GAME = {'cls': 'steam_app_367520', 'name': 'Hollow Knight', 'pid': 4321}


def _focus_python():
    text = open(GAME_LAUNCH_SRC).read()
    m = re.search(r"WANT=\"\$what\" HIDE_BP=\"\$hide_bp\" python3 - "
                  r"<<'EOF'[^\n]*\n(.*?)\nEOF\n", text, re.S)
    assert m, 'focus_game heredoc not found in the mirror'
    return m.group(1)


@pytest.fixture
def fscreen(tmp_path):
    """Runs focus_game's embedded python over a described fake screen."""
    pkg = tmp_path / 'Xlib'
    pkg.mkdir()
    (pkg / '__init__.py').write_text('from . import display, X, protocol\n')
    (pkg / 'display.py').write_text(_FAKE_DISPLAY)
    (pkg / 'X.py').write_text(_FAKE_X)
    (pkg / 'protocol.py').write_text(_FAKE_PROTOCOL)
    code = _focus_python()

    def run(windows, want='game', hide_bp='1', game_pids='4321'):
        (tmp_path / 'screen.json').write_text(json.dumps(windows))
        (tmp_path / 'game-pids').write_text(game_pids)
        env = dict(os.environ,
                   PYTHONPATH=str(tmp_path),
                   WANT=want, HIDE_BP=hide_bp,
                   FAKE_SCREEN=str(tmp_path / 'screen.json'),
                   GAME_PIDS_FILE=str(tmp_path / 'game-pids'),
                   LEGACY_INTENTS_FILE=str(tmp_path / 'intents.jsonl'))
        return subprocess.run([sys.executable, '-'], input=code, text=True,
                              capture_output=True, env=env, cwd=tmp_path,
                              timeout=30)
    run.intents = lambda: [
        json.loads(l)
        for l in (tmp_path / 'intents.jsonl').read_text().splitlines() if l
    ] if (tmp_path / 'intents.jsonl').exists() else []
    return run


def test_focus_python_exits_nonzero_while_the_window_is_missing(fscreen):
    """The retry loop's continue condition, and the launch-path bug itself:
    processes up, window not mapped yet. Nothing may be iconified either -
    hiding BP on a failed attempt would blank the screen for the wait."""
    r = fscreen([KODI, BP])
    assert r.returncode == 1
    assert 'game window not found' in r.stdout
    assert 'iconified' not in r.stdout
    assert fscreen.intents() == []


def test_focus_python_exit_0_is_found_and_shown_and_bp_hidden(fscreen):
    """The retry loop's stop condition: the window mapped, the restack ran,
    and the BP-hide rode the same successful attempt."""
    r = fscreen([KODI, BP, GAME])
    assert r.returncode == 0
    assert 'game focused' in r.stdout
    assert 'iconified big picture behind the game' in r.stdout
    recs = [i for i in fscreen.intents() if i['subject'] == 'bigpicture']
    assert len(recs) == 1 and recs[0]['verb'] == 'iconify'
    assert recs[0]['args']['reason'] == 'bp mapped fullscreen behind the game'


def test_focus_python_success_without_the_hide_gate_leaves_bp(fscreen):
    r = fscreen([KODI, BP, GAME], hide_bp='0')
    assert r.returncode == 0
    assert 'game focused' in r.stdout
    assert 'iconified big picture' not in r.stdout
    assert fscreen.intents() == []


def test_focus_python_finds_proton_windows_by_class_not_just_pid(fscreen):
    """Pin the pre-existing matcher the retry now leans on: a steam_app_*
    class counts even when the window's pid belongs to a wine helper."""
    stranger = dict(GAME, pid=9999)               # pid NOT in game-pids
    r = fscreen([KODI, stranger])
    assert r.returncode == 0
    assert 'game focused' in r.stdout
