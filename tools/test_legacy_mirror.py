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
  4. (6 Aug, the wire-in itself) game-launch curtains its suspend and resume:
     shown on the just-captured freeze-frame BEFORE the window shuffle,
     faded only after the right thing is confirmed on screen, cleared (never
     left up) on the broken paths - and skipped entirely for bigpicture,
     for a missing binary, and for a freeze-frame that is not this pause's
     own (an honest bare shuffle beats a wrong frozen frame).

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


# =========================================================================
# 5. game-launch: the curtain wire-in (suspend/resume transitions)
# =========================================================================
# The flows are shell, so the shell is what runs: the script's PRELUDE (every
# definition before the dispatch case) is sourced into a bash harness, the
# effectors (pad routing, restacks, snaps, guards) are stubbed to a call log,
# and the curtain binary is a recording stub - CURTAIN_BIN and the path seams
# (GAME_LAUNCH_LOG / LEGACY_INTENTS_FILE / GAME_SESSION_FILE /
# GAME_SUSPENDED_FILE / PAUSE_SNAP_DIR) point everything under tmp_path.
# The suspend/quit arm bodies are extracted from the case statement and run
# verbatim; resume_game and focus_game_when_mapped are called as functions.

_GL_STUBS = '''
rec() { echo "$*" >> "$GL_CALLS"; }
session_lock() { :; }
game_pids() { cat "$GL_PIDS_FILE" 2>/dev/null; }
kill() { rec kill "$*"; }
pad_to_kodi() { rec pad_to_kodi; }
pad_to_game() { rec pad_to_game; }
focus_kodi() { rec focus_kodi; }
hide_frozen_game() { rec hide_frozen_game; }
show_frozen_game() { rec show_frozen_game; }
snap_paused() { rec snap_paused "$@"; }
clear_snaps() { rec clear_snaps "$@"; }
cont_all() { rec thaw; }
close_games() { rec close_games "$@"; }
bp_running() { return 1; }
emu_running() { return 1; }
jrpc() { :; }
curl() { :; }
setsid() { rec setsid; }
sleep() { :; }
focus_game() {
  rec focus_game "${1:-game}"
  case "${1:-game}" in bp) return "${FOCUS_BP_RC:-0}" ;; esac
  return "${FOCUS_GAME_RC:-0}"
}
'''

_GL_CURTAIN_STUB = '''#!/usr/bin/env bash
echo "curtain $*" >> "$GL_CALLS"
case "${1:-}" in
  status) [ -f "$GL_CURTAIN_MARK" ]; exit $? ;;
  show) exit "${CURTAIN_SHOW_RC:-0}" ;;
esac
exit 0
'''

_GL_DRIVER = '''set -u
source "$GL_PRELUDE"
source "$GL_STUBS"
source "$GL_BODY"
'''


def _gl_text():
    return open(GAME_LAUNCH_SRC).read()


def _gl_prelude():
    text = _gl_text()
    idx = text.index('\n# The trigger channel')
    return text[:idx]


def _gl_case_body(mode):
    m = re.search(r'\n  %s\)\n(.*?)\n    ;;' % re.escape(mode), _gl_text(),
                  re.S)
    assert m, f'{mode} arm not found in the mirror'
    return m.group(1)


def _in_order(calls, *prefixes):
    """Each prefix happened, and their FIRST occurrences are in this order."""
    pos = []
    for p in prefixes:
        hits = [i for i, c in enumerate(calls) if c.startswith(p)]
        assert hits, f'{p!r} never happened: {calls}'
        pos.append(hits[0])
    assert pos == sorted(pos), f'wrong order {list(zip(prefixes, pos))}'


@pytest.fixture
def glaunch(tmp_path):
    t = tmp_path
    (t / 'paused').mkdir()
    calls = t / 'calls.log'
    curtain = t / 'curtain'
    curtain.write_text(_GL_CURTAIN_STUB)
    curtain.chmod(0o755)
    (t / 'prelude.sh').write_text(_gl_prelude())
    (t / 'stubs.sh').write_text(_GL_STUBS)
    (t / 'driver.sh').write_text(_GL_DRIVER)

    def run(body, mode='suspend', appid='', env=None,
            session='111 steam 367520', pids='4321'):
        (t / 'body.sh').write_text(body)
        if session is not None:
            (t / 'game-session').write_text(session + '\n')
        if pids is not None:
            (t / 'game-pids').write_text(pids + '\n')
        e = dict(os.environ,
                 GL_PRELUDE=str(t / 'prelude.sh'),
                 GL_STUBS=str(t / 'stubs.sh'),
                 GL_BODY=str(t / 'body.sh'),
                 GL_CALLS=str(calls),
                 GL_CURTAIN_MARK=str(t / 'curtain-up'),
                 GL_PIDS_FILE=str(t / 'game-pids'),
                 GAME_LAUNCH_LOG=str(t / 'game-launch.log'),
                 LEGACY_INTENTS_FILE=str(t / 'intents.jsonl'),
                 GAME_SESSION_FILE=str(t / 'game-session'),
                 GAME_SUSPENDED_FILE=str(t / 'game-suspended'),
                 CURTAIN_BIN=str(curtain),
                 PAUSE_SNAP_DIR=str(t / 'paused'))
        e.update(env or {})
        return subprocess.run(['bash', str(t / 'driver.sh'), mode, appid],
                              capture_output=True, text=True, env=e,
                              timeout=30)
    run.dir = t
    run.calls = lambda: (calls.read_text().splitlines()
                         if calls.exists() else [])
    run.intents = lambda: [
        json.loads(l)
        for l in (t / 'intents.jsonl').read_text().splitlines() if l
    ] if (t / 'intents.jsonl').exists() else []
    return run


def test_suspend_curtains_before_the_shuffle_and_fades_after_kodi(glaunch):
    """The wire point itself: show lands between the snap and the window
    shuffle (pad handoff, Kodi raise, game iconify), the fade only after Kodi
    is focused and the frozen window is gone - so the room sees game,
    dissolve, Kodi, and none of the steps in between."""
    frame = glaunch.dir / 'paused' / '367520__1000.jpg'
    frame.write_bytes(b'jpg')
    r = glaunch(_gl_case_body('suspend'), mode='suspend')
    assert r.returncode == 0, r.stderr
    _in_order(glaunch.calls(), 'snap_paused', 'curtain show', 'pad_to_kodi',
              'focus_kodi', 'hide_frozen_game', 'curtain fade')
    shows = [i for i in glaunch.intents() if i['verb'] == 'curtain_show']
    assert len(shows) == 1
    # wm_class is what shadow-diff's curtain_involved() keys T5 on.
    assert shows[0]['args']['wm_class'] == 'couch-curtain'
    assert shows[0]['args']['image'] == str(frame)
    assert any(i['verb'] == 'curtain_fade' for i in glaunch.intents())


def test_suspend_without_the_binary_is_exactly_todays_behaviour(glaunch):
    """No curtain binary = the pre-wire-in suspend, byte for byte: full
    shuffle, no curtain calls, no curtain intents."""
    (glaunch.dir / 'paused' / '367520__1000.jpg').write_bytes(b'jpg')
    r = glaunch(_gl_case_body('suspend'), mode='suspend',
                env={'CURTAIN_BIN': str(glaunch.dir / 'no-such-curtain')})
    assert r.returncode == 0, r.stderr
    calls = glaunch.calls()
    assert not any(c.startswith('curtain') for c in calls)
    _in_order(calls, 'snap_paused', 'pad_to_kodi', 'focus_kodi',
              'hide_frozen_game')
    assert not any(i['verb'].startswith('curtain') for i in glaunch.intents())


def test_a_bigpicture_suspend_never_curtains(glaunch):
    """The appid-less BP session freezes under the literal 'bigpicture';
    there is nothing worth hiding behind its own freeze-frame. A frame IS on
    disk here, so the skip is the rule, not a missing file."""
    (glaunch.dir / 'paused' / 'bigpicture__1000.jpg').write_bytes(b'jpg')
    r = glaunch(_gl_case_body('suspend'), mode='suspend',
                session='111 bigpicture')
    assert r.returncode == 0, r.stderr
    calls = glaunch.calls()
    assert not any(c.startswith('curtain') for c in calls)
    _in_order(calls, 'pad_to_kodi', 'focus_kodi')


def test_resume_shows_before_the_thaw_and_fades_after_focus(glaunch):
    """The mirror image: curtain up before any thaw/window work (and before
    clear_snaps deletes the very jpg it shows), fade only once focus_game
    reported the game window focused."""
    (glaunch.dir / 'game-suspended').write_text('367520\n')
    (glaunch.dir / 'paused' / '367520__2000.jpg').write_bytes(b'jpg')
    r = glaunch('resume_game\n', mode='resume')
    assert r.returncode == 0, r.stderr
    _in_order(glaunch.calls(), 'curtain show', 'thaw', 'clear_snaps',
              'show_frozen_game', 'pad_to_game', 'focus_game game',
              'curtain fade')
    assert any(i['verb'] == 'curtain_fade' for i in glaunch.intents())


def test_a_stale_freeze_frame_resumes_bare(glaunch):
    """A frame older than the suspended flag belongs to some earlier pause:
    an honest quick shuffle beats a wrong frozen frame, so the curtain is
    skipped entirely - the resume itself is untouched."""
    import time
    now = time.time()
    flag = glaunch.dir / 'game-suspended'
    flag.write_text('367520\n')
    frame = glaunch.dir / 'paused' / '367520__2000.jpg'
    frame.write_bytes(b'jpg')
    os.utime(frame, (now - 400, now - 400))       # well past the 30s slack
    os.utime(flag, (now, now))
    r = glaunch('resume_game\n', mode='resume')
    assert r.returncode == 0, r.stderr
    calls = glaunch.calls()
    assert not any(c.startswith('curtain show') for c in calls)
    _in_order(calls, 'thaw', 'show_frozen_game', 'focus_game game')
    assert not any(i['verb'] == 'curtain_show' for i in glaunch.intents())


def test_resume_with_nothing_focusable_clears_not_fades(glaunch):
    """Failure honesty: when neither the game nor Big Picture takes focus the
    pad falls back to Kodi and the curtain is CLEARED - a fade would dissolve
    prettily over a state the script just called broken."""
    (glaunch.dir / 'game-suspended').write_text('367520\n')
    (glaunch.dir / 'paused' / '367520__2000.jpg').write_bytes(b'jpg')
    r = glaunch('resume_game\n', mode='resume',
                env={'FOCUS_GAME_RC': '1', 'FOCUS_BP_RC': '1'})
    assert r.returncode == 0, r.stderr
    calls = glaunch.calls()
    _in_order(calls, 'curtain show', 'focus_game game', 'focus_game bp',
              'curtain clear', 'pad_to_kodi', 'focus_kodi')
    assert not any(c.startswith('curtain fade') for c in calls)
    clears = [i for i in glaunch.intents() if i['verb'] == 'curtain_clear']
    assert clears and clears[-1]['args']['reason'] == 'resume-nothing-to-focus'


def test_focus_timeout_clears_the_curtain(glaunch):
    """The launch path's converging focus gives up: nothing may sit over the
    window that never came."""
    r = glaunch('CURTAIN_UP=1\nFOCUS_WAIT_MAX_S=0\nfocus_game_when_mapped\n'
                'exit 0\n', mode='steam', appid='367520',
                env={'FOCUS_GAME_RC': '1'})
    assert r.returncode == 0, r.stderr
    assert any(c.startswith('curtain clear') for c in glaunch.calls())
    verbs = [i['verb'] for i in glaunch.intents()]
    assert verbs.index('focus_timeout') < verbs.index('curtain_clear')
    clears = [i for i in glaunch.intents() if i['verb'] == 'curtain_clear']
    assert clears[-1]['args']['reason'] == 'focus-timeout'


def test_a_curtain_already_up_is_handed_straight_to_show(glaunch):
    """Two curtains still never stack, but the stacking rule lives in the
    tool now: cmd_show (tools/curtain) swaps a LIVE daemon onto the new image
    atomically, replaces a wedged one, and clears stale state before a fresh
    spawn - all verified against tools/curtain before the shell's status
    pre-probe (~45ms every curtained transition, ~300ms in the stale case)
    was dropped. So with a curtain already up, curtain_show goes straight to
    `curtain show`: no probe, no shell-side clear."""
    (glaunch.dir / 'curtain-up').write_text('')   # the stub's status says up
    (glaunch.dir / 'paused' / '367520__1000.jpg').write_bytes(b'jpg')
    r = glaunch(_gl_case_body('suspend'), mode='suspend')
    assert r.returncode == 0, r.stderr
    calls = glaunch.calls()
    assert any(c.startswith('curtain show') for c in calls)
    assert not any(c.startswith('curtain status') for c in calls)
    assert not any(c.startswith('curtain clear') for c in calls)
    assert not any(i['verb'] == 'curtain_clear' for i in glaunch.intents())


def test_quit_drops_a_leftover_curtain(glaunch):
    """A quit mid-transition changes what is true under the overlay; the
    teardown starts by dropping it."""
    (glaunch.dir / 'curtain-up').write_text('')
    r = glaunch(_gl_case_body('quit'), mode='quit', pids=None)
    assert r.returncode == 0, r.stderr
    assert any(c.startswith('curtain clear') for c in glaunch.calls())
    clears = [i for i in glaunch.intents() if i['verb'] == 'curtain_clear']
    assert clears and clears[-1]['args']['reason'] == 'quit'


# =========================================================================
# 6. the reconcile-flip hard gate: flag first, thaw second + debounced repairs
# =========================================================================
# Legacy's resume flows used to thaw BEFORE clearing /tmp/game-suspended; in
# that gap every repairer read "flag set, pids running" and its one repair is
# to RE-FREEZE the game (couchd's shadow decided exactly that 3x on the
# acceptance night: 03:18, 03:33, 03:42). The fix is a protocol both stacks
# share: (i) the flag is cleared before the SIGCONTs on every thawing path,
# (ii) the repairs treat a sub-second flag/pid disagreement as a transition
# in flight, not drift (watcher THAW_RECHECK_S re-sample, guard THAW_CONFIRM_S
# one-pass debounce, couchd FLAG_DRIFT_PERSIST_S - the last is pinned in
# couchd/test_reconcile.py).

def test_resume_clears_the_flag_before_the_thaw(glaunch):
    """The ordering itself, behaviourally: by the time the SIGCONTs run the
    flag is already gone, so no repairer can read thawed-pids-under-a-set-flag
    off this resume ever again."""
    (glaunch.dir / 'game-suspended').write_text('367520\n')
    body = ('cont_all() { rec thaw "flag=$([ -f "$SUSPENDED" ]'
            ' && echo present || echo gone)"; }\n'
            'resume_game\n')
    r = glaunch(body, mode='resume')
    assert r.returncode == 0, r.stderr
    assert 'thaw flag=gone' in glaunch.calls(), glaunch.calls()
    # ...and the rest of the flow is intact behind it.
    _in_order(glaunch.calls(), 'thaw flag=gone', 'show_frozen_game',
              'pad_to_game', 'focus_game game')
    clears = [i for i in glaunch.intents() if i['verb'] == 'clear_flag']
    assert clears and clears[0]['args']['reason'] == 'resume'
    assert clears[0]['args']['was'] == '367520'


def test_back_to_big_picture_clears_the_flag_before_the_thaw(glaunch):
    """The bigpicture refocus arm thaws too; same protocol, and it now takes
    the session lock like the resume it is."""
    (glaunch.dir / 'game-suspended').write_text('367520\n')
    body = ('bp_running() { return 0; }\n'
            'cont_all() { rec thaw "flag=$([ -f "$SUSPENDED" ]'
            ' && echo present || echo gone)"; }\n'
            + _gl_case_body('bigpicture'))
    r = glaunch(body, mode='bigpicture')
    assert r.returncode == 0, r.stderr
    assert 'thaw flag=gone' in glaunch.calls(), glaunch.calls()
    _in_order(glaunch.calls(), 'thaw flag=gone', 'pad_to_game',
              'focus_game bp')
    clears = [i for i in glaunch.intents() if i['verb'] == 'clear_flag']
    assert clears and clears[0]['args']['reason'] == 'back-to-big-picture'
    assert 'session_lock' in _gl_case_body('bigpicture')


def test_close_games_clears_the_flag_before_the_thaw():
    """close_games cannot run under the harness (its WM_DELETE python needs a
    live X and writes /tmp/game-pids), so its ordering is pinned textually:
    the ONE flag clear sits before the thaw, and the widest old window - the
    whole thaw-ask-wait-kill teardown under a still-set flag - is gone."""
    m = re.search(r'\nclose_games\(\) \{\n(.*?)\n\}\n', _gl_text(), re.S)
    assert m, 'close_games() not found in the mirror'
    body = m.group(1)
    assert body.count('rm -f "$SUSPENDED"') == 1
    assert body.index('rm -f "$SUSPENDED"') < body.index('cont_all')
    assert body.index('cont_all') < body.index('sleep 1')


def test_tile_resumes_take_the_session_lock():
    """The tile-resume paths are resumes in all but name and exit right
    after; they now hold the same lock the `resume` verb takes, so a suspend
    cannot interleave their thaw. The fall-through launch paths must NOT
    take it (a launcher lives as long as its game)."""
    for mode in ('steam', 'shadps4'):
        arm = _gl_case_body(mode)
        assert 'session_lock' in arm, f'{mode} tile-resume is unlocked'
        assert arm.index('session_lock') < arm.index('resume_game')
        # only inside the resume branch, which exits before the launch flow
        assert arm.index('session_lock') < arm.index('exit 0')


def test_the_mirror_still_parses():
    r = subprocess.run(['bash', '-n', GAME_LAUNCH_SRC],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ---- the watcher's side of the protocol ---------------------------------
def _screen_kodi(monkeypatch):
    monkeypatch.setattr(watcher, 'screen_classes', lambda: ('Kodi', 'Kodi'))
    monkeypatch.setattr(watcher, 'curtain_visible', lambda: False)


def test_refreeze_backs_off_when_the_flag_clears_mid_pass(wbox, monkeypatch):
    """The dangerous direction, closed at the decision: this pass read the
    flag before a resume's rm and the pids after its SIGCONTs. Under
    flag-first ordering that combination PROVES the flag is already gone, so
    the fresh re-read must always find it gone and the refreeze must not
    fire - a SIGSTOP here is the mid-resume freeze the flip is gated on."""
    calls = []
    _quiet_repairs(monkeypatch, calls)
    _screen_kodi(monkeypatch)
    (wbox.dir / 'game-session').write_text('111 steam 367520\n')
    flag = wbox.dir / 'game-suspended'
    flag.write_text('367520')
    kills = []
    monkeypatch.setattr(watcher.os, 'kill',
                        lambda pid, sig: kills.append((pid, sig)))

    def running_and_resume_lands():
        flag.unlink(missing_ok=True)      # the resume's rm, mid-pass
        return {101: 'S', 102: 'S'}
    monkeypatch.setattr(watcher, '_pid_states', running_and_resume_lands)
    watcher._reconcile(dry=False)
    assert kills == []
    assert not [i for i in wbox.intents() if i['verb'] == 'freeze']
    assert not [c for c in calls if c[0] == 'iconify_frozen_game']


def test_refreeze_still_fires_when_the_stale_flag_persists(wbox, monkeypatch):
    """...and the real 4 Aug-style repair is intact: flag on disk at the
    decision, game running behind Kodi - re-freeze, iconify, converge."""
    calls = []
    _quiet_repairs(monkeypatch, calls)
    _screen_kodi(monkeypatch)
    (wbox.dir / 'game-session').write_text('111 steam 367520\n')
    (wbox.dir / 'game-suspended').write_text('367520')
    kills = []
    monkeypatch.setattr(watcher.os, 'kill',
                        lambda pid, sig: kills.append((pid, sig)))
    monkeypatch.setattr(watcher, '_pid_states', lambda: {101: 'S'})
    watcher._reconcile(dry=False)
    rec = [i for i in wbox.intents() if i['verb'] == 'freeze']
    assert rec and rec[0]['args']['reason'] == 'reconcile:refreeze-lost-suspend'
    assert kills == [(101, watcher.signal.SIGSTOP)]
    assert [c for c in calls if c[0] == 'iconify_frozen_game']


def test_lost_thaw_waits_out_a_resume_transient(wbox, monkeypatch):
    """Frozen-without-flag re-sampled THAW_RECHECK_S later: if the pids came
    back on their own it was a resume's critical section, and a thaw fired
    into it would have told the differ a repair happened where none did."""
    calls = []
    _quiet_repairs(monkeypatch, calls)
    (wbox.dir / 'game-session').write_text('111 steam 367520\n')
    kills, naps = [], []
    monkeypatch.setattr(watcher.os, 'kill',
                        lambda pid, sig: kills.append((pid, sig)))
    monkeypatch.setattr(watcher.time, 'sleep', lambda s: naps.append(s))
    samples = iter([{101: 'T'}, {101: 'S'}])
    monkeypatch.setattr(watcher, '_pid_states', lambda: next(samples))
    watcher._reconcile(dry=False)
    assert watcher.THAW_RECHECK_S in naps
    assert kills == []
    assert not [i for i in wbox.intents() if i['verb'] == 'thaw']


def test_lost_thaw_still_repairs_when_the_freeze_persists(wbox, monkeypatch):
    calls = []
    _quiet_repairs(monkeypatch, calls)
    (wbox.dir / 'game-session').write_text('111 steam 367520\n')
    kills = []
    monkeypatch.setattr(watcher.os, 'kill',
                        lambda pid, sig: kills.append((pid, sig)))
    monkeypatch.setattr(watcher.time, 'sleep', lambda s: None)
    monkeypatch.setattr(watcher, '_pid_states', lambda: {101: 'T'})
    watcher._reconcile(dry=False)
    rec = [i for i in wbox.intents() if i['verb'] == 'thaw']
    assert rec and rec[0]['args']['reason'] == 'frozen-without-suspended-flag'
    assert kills == [(101, watcher.signal.SIGCONT)]
    assert [c for c in calls if c[0] == 'map_game_window']


def test_lost_thaw_backs_off_when_a_suspend_lands_mid_pass(wbox, monkeypatch):
    """The 4 Aug guard lesson, applied to this net: the flag REAPPEARING
    during the confirm means a fresh suspend, and thawing it would undo the
    player's own gesture."""
    calls = []
    _quiet_repairs(monkeypatch, calls)
    (wbox.dir / 'game-session').write_text('111 steam 367520\n')
    kills = []
    monkeypatch.setattr(watcher.os, 'kill',
                        lambda pid, sig: kills.append((pid, sig)))
    monkeypatch.setattr(watcher.time, 'sleep', lambda s: None)
    flag = wbox.dir / 'game-suspended'
    samples = []

    def frozen_then_suspend_lands():
        if samples:                        # the confirm re-sample
            flag.write_text('367520')
        samples.append(1)
        return {101: 'T'}
    monkeypatch.setattr(watcher, '_pid_states', frozen_then_suspend_lands)
    watcher._reconcile(dry=False)
    assert kills == []
    assert not [i for i in wbox.intents() if i['verb'] == 'thaw']


def test_the_shadow_reconcile_confirms_the_same_way(wbox, monkeypatch):
    """Dry mode runs the identical confirm: a shadow that skipped it would
    record a repair the acting path never fires, and the differ would read
    that as a divergence between the stacks' own halves."""
    calls = []
    _quiet_repairs(monkeypatch, calls)
    wbox.own('reconcile')
    (wbox.dir / 'game-session').write_text('111 steam 367520\n')
    monkeypatch.setattr(watcher.time, 'sleep', lambda s: None)
    samples = iter([{101: 'T'}, {101: 'S'}])
    monkeypatch.setattr(watcher, '_pid_states', lambda: next(samples))
    watcher._reconcile(dry=True)
    assert not [i for i in wbox.intents() if i['verb'] == 'thaw']


# ---- the guard's side (invariant 4's one-pass debounce) ------------------
def test_lost_thaw_due_debounces_one_pass():
    """lost_thaw_due: nothing fires on a first sighting; the clock survives
    only while the condition does; the thaw fires once it has held for
    THAW_CONFIRM_S of passes."""
    fire, since = guard.lost_thaw_due(False, True, None, 100.0)
    assert (fire, since) == (False, 100.0)          # first sighting arms
    fire, since = guard.lost_thaw_due(False, True, since, 100.5)
    assert (fire, since) == (False, 100.0)          # not yet
    fire, since = guard.lost_thaw_due(False, True, since, 101.0)
    assert (fire, since) == (True, 100.0)           # persisted a full pass
    # the flag reappearing (a suspend) or a thaw landing resets the clock
    assert guard.lost_thaw_due(True, True, 100.0, 101.5) == (False, None)
    assert guard.lost_thaw_due(False, False, 100.0, 101.5) == (False, None)


# =========================================================================
# 7. transition speed-ups, first batch (6-7 Aug): fixed sleeps -> converges
# =========================================================================
# The behavioural halves run under the glaunch harness (its sleep stub makes
# the converge loops instant, so what is pinned is the DECISION sequence:
# attempt counts, fallbacks, honest timeout intents). The polls that cannot
# run here (ensure_big_picture probes the live steam-uimode path; close_games
# needs X) are pinned textually - grain and deadline together, so a grain
# change that silently moved a total timeout fails loudly.

def _gl_fn(name):
    m = re.search(r'\n%s\(\) \{.*?\n\}\n' % re.escape(name), _gl_text(), re.S)
    assert m, f'{name}() not found in the mirror'
    return m.group(0)


def test_resume_has_no_fixed_sleep_left(glaunch):
    """The headline: the flat `sleep 1` that was ~77% of a measured resume is
    gone from resume_game; the converge helper owns the wait now."""
    body = _gl_fn('resume_game')
    assert not re.search(r'^\s*sleep 1\s*$', body, re.M)
    assert 'resume_focus_converge' in body


def test_resume_converge_lands_on_the_first_mapped_frame(glaunch):
    """A window that is already mapped (the common case - the budget doc
    measures the map done in ~50-500ms while pad routing runs) is focused on
    the FIRST attempt: one focus_game call, no retry tail, fade as before."""
    (glaunch.dir / 'game-suspended').write_text('367520\n')
    (glaunch.dir / 'paused' / '367520__2000.jpg').write_bytes(b'jpg')
    r = glaunch('resume_game\n', mode='resume')
    assert r.returncode == 0, r.stderr
    calls = glaunch.calls()
    assert len([c for c in calls if c == 'focus_game game']) == 1
    _in_order(calls, 'focus_game game', 'curtain fade')


def test_resume_converge_is_bounded_then_falls_back_to_bp(glaunch):
    """A window that never maps: exactly RESUME_FOCUS_TRIES (15 x 0.1s
    grain = the 1.5s cap, past the old sleep's 1.0s guarantee) attempts on
    the game, then the same bp -> kodi fallback chain as before, with the
    curtain CLEARED not faded - none of the failure honesty regressed."""
    (glaunch.dir / 'game-suspended').write_text('367520\n')
    (glaunch.dir / 'paused' / '367520__2000.jpg').write_bytes(b'jpg')
    r = glaunch('resume_game\n', mode='resume',
                env={'FOCUS_GAME_RC': '1', 'FOCUS_BP_RC': '1'})
    assert r.returncode == 0, r.stderr
    calls = glaunch.calls()
    assert len([c for c in calls if c == 'focus_game game']) == 15
    _in_order(calls, 'focus_game game', 'focus_game bp', 'curtain clear',
              'pad_to_kodi', 'focus_kodi')


def test_resume_flag_first_ordering_survives_the_converge(glaunch):
    """The reconcile-flip hard gate must not move: flag cleared before the
    SIGCONTs, curtain shown before either, all with the converge in place."""
    (glaunch.dir / 'game-suspended').write_text('367520\n')
    (glaunch.dir / 'paused' / '367520__2000.jpg').write_bytes(b'jpg')
    body = ('cont_all() { rec thaw "flag=$([ -f "$SUSPENDED" ]'
            ' && echo present || echo gone)"; }\n'
            'resume_game\n')
    r = glaunch(body, mode='resume')
    assert r.returncode == 0, r.stderr
    _in_order(glaunch.calls(), 'curtain show', 'thaw flag=gone',
              'show_frozen_game', 'pad_to_game', 'focus_game game',
              'curtain fade')


def test_launch_focus_cadence_backs_off_and_keeps_the_40s_cap(glaunch):
    """The adaptive cadence, counted: 20 attempts in the 0.5s stretch
    (10s / 0.5), 15 in the 2s stretch (30s / 2), plus the final look at the
    cap = 36 attempts across exactly 40s of budgeted sleep - then the same
    honest focus_timeout intent, now stamped waited=40."""
    r = glaunch('focus_game_when_mapped\nexit 0\n', mode='steam',
                appid='367520', env={'FOCUS_GAME_RC': '1'})
    assert r.returncode == 0, r.stderr
    assert len([c for c in glaunch.calls() if c == 'focus_game game']) == 36
    tos = [i for i in glaunch.intents() if i['verb'] == 'focus_timeout']
    assert len(tos) == 1
    assert tos[0]['args']['waited'] == '40'
    assert tos[0]['args']['reason'] == 'game-window-never-mapped'


def test_launch_focus_still_stops_when_the_game_dies(glaunch):
    """The early-out is untouched: pids gone means stop retrying, no timeout
    intent, no curtain touch. (pids=None leaves no game-pids file at all -
    the stub's `cat` then fails exactly like the real helper with no game.)"""
    r = glaunch('focus_game_when_mapped; echo "rc=$?" >> "$GL_CALLS"\n'
                'exit 0\n', mode='steam', appid='367520',
                env={'FOCUS_GAME_RC': '1'}, pids=None)
    assert r.returncode == 0, r.stderr
    calls = glaunch.calls()
    assert len([c for c in calls if c == 'focus_game game']) == 1
    assert 'rc=1' in calls
    assert not any(i['verb'] == 'focus_timeout' for i in glaunch.intents())


def test_the_launch_arm_lost_its_fixed_sleep_4():
    """Textual: the steam launch arm goes straight from "running" into the
    converge (the 4s predated focus_game_when_mapped and was pure padding
    spent in the BP-behind-game state), and the process poll runs at 0.5s
    with the same 180s leash (360 half-second beats)."""
    text = _gl_text()
    arm = text[text.index('# Into Big Picture first'):]
    arm = arm[:arm.index(';;')]
    assert not re.search(r'^\s*sleep 4\s*$', arm, re.M)
    assert 'sleep 0.5; t=$((t+1))' in arm
    assert '[ $t -ge 360 ]' in arm and '(180s)' in arm


def test_ensure_big_picture_confirms_at_quarter_second_grain():
    """Textual: 0.25s probes, same 6s total (BP_CONFIRM_S x 4 beats), and the
    give-up path still reports the full wait and never blocks the launch."""
    fn = _gl_fn('ensure_big_picture')
    assert 'sleep 0.25' in fn
    assert '$((BP_CONFIRM_S * 4))' in fn
    assert re.search(r'^BP_CONFIRM_S=6$', _gl_text(), re.M)
    assert 'waited=$BP_CONFIRM_S' in fn


def test_teardown_polls_are_quarter_second_same_deadlines():
    """Textual: the save-on-quit grace keeps its deliberate totals - 8s ask
    (32 x 0.25), 30s shadPS4 (120 x 0.25; was 6s until 59aa7fb, when the
    Bloodborne clean-exit work showed the emulator needs real time to bow
    out or the save's dirty flag silences the session's sounds), 10s
    launcher bow-out (40 x 0.25, both arms) - and the post-thaw `sleep 1`
    grace before the WM_DELETE ask is untouched (it is settle time for the
    thawed game, not a poll)."""
    text = _gl_text()
    fn = _gl_fn('close_games')
    assert 'for _ in $(seq 32); do game_running || break; sleep 0.25; done' in fn
    assert 'for _ in $(seq 120); do emu_running || break; sleep 0.25; done' in fn
    assert re.search(r'^\s*sleep 1\s*$', fn, re.M)      # the thaw grace stays
    assert text.count(
        'for _ in $(seq 40); do [ -f "$SESSION" ] || break; sleep 0.25; done') == 2
    assert not re.search(r'\[ -f "\$SESSION" \] \|\| break; sleep 1;', text)


def test_close_ignored_sweep_never_sigkills_the_emulator():
    """Textual: the +8s WM_DELETE force-kill sweep excludes shadPS4's pids.
    game_pids includes them, so without the filter the sweep SIGKILLed the
    emulator - the dirty exit that silences Bloodborne's session sounds -
    and made the SIGTERM + 30s emulator branch below it unreachable on
    every in-game quit (shadPS4 ignores WM_DELETE while a game runs;
    caught live 15 Aug 2026)."""
    fn = _gl_fn('close_games')
    assert "shad=\" $(pgrep -f 'Shadps4-sdl|mount_Shadps' | tr '\\n' ' ') \"" in fn
    assert 'case "$shad" in *" $p "*) continue ;; esac' in fn
    # the kill loop runs on the filtered list, and only when it is non-empty
    assert 'scope=steam-only' in fn


def test_quit_gives_kodi_the_pad_first_and_skips_the_ask_for_emu_only():
    """Textual twins of the 15 Aug quit-feel fixes. (1) The quit path routes
    the pad to Kodi BEFORE the closing graces - the player has already left,
    and the old order meant tens of seconds of dead buttons while the game
    died in the background. (2) close_games skips the WM_DELETE ask and its
    8s grace when the session is emulator-only: shadPS4 ignores the ask
    in-game, and under the gamescope wrap the visible window is not even
    the emulator's."""
    text = _gl_text()
    quit_block = text[text.index('=== quit (save and close)'):
                      text.index('nothing to quit')]
    assert 'pad_to_kodi' in quit_block
    fn = _gl_fn('close_games')
    assert 'steam_present=0' in fn
    assert 'emulator-only session' in fn


def test_curtain_show_has_no_status_preprobe():
    """Textual twin of the behavioural test above: curtain_show never shells
    `status` (curtain_clear legitimately still does)."""
    fn = _gl_fn('curtain_show')
    assert '"$CURTAIN" status' not in fn
    assert '"$CURTAIN" show' in fn
