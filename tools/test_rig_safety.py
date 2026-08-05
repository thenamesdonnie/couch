#!/usr/bin/env python3
"""Failure-mode tests for the three evidence/rig tools: tools/fake-pad,
tools/gesture-sweep, tools/intents-archive.

NOTHING here touches the live box. No uhid device is created, no systemctl
runs, no real /tmp flag file (/tmp/fake-pad.pid, /tmp/game-suspended,
/tmp/tv-wake-request) is read or written, and ~/couch/shadow is never opened:
every path each tool knows about is bent into tmp_path first.

What these cover is the set of defects found in the 5 Aug review, all of
which share a shape - the tool works, and its FAILURE mode quietly leaves the
console in a bad state (inhibit units stopped, two pads live, an operator's
shell parked, evidence duplicated or lost).

Run:  couchd/.venv/bin/pytest tools/test_rig_safety.py -q
"""
import ast
import importlib.machinery
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(script, modname):
    path = os.path.join(HERE, script)
    if not os.path.exists(path):
        pytest.skip(f'tools/{script} not present')
    loader = importlib.machinery.SourceFileLoader(modname, path)
    spec = importlib.util.spec_from_loader(modname, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)          # imports only; creates nothing
    return mod


@pytest.fixture
def fp():
    return load('fake-pad', 'fake_pad_safety')


@pytest.fixture
def gs():
    return load('gesture-sweep', 'gesture_sweep_safety')


@pytest.fixture
def ia():
    return load('intents-archive', 'intents_archive_safety')


# =========================================================================
# fake-pad: the single-instance claim
# =========================================================================
CLAIM_IN_A_CHILD = """
import importlib.machinery, importlib.util, sys
loader = importlib.machinery.SourceFileLoader('m', sys.argv[1])
spec = importlib.util.spec_from_loader('m', loader)
m = importlib.util.module_from_spec(spec); loader.exec_module(m)
print('GOT' if m.claim_pidfile(sys.argv[2]) is not None else 'REFUSED')
"""


def claim_in_a_child(pidfile):
    r = subprocess.run([sys.executable, '-c', CLAIM_IN_A_CHILD,
                        os.path.join(HERE, 'fake-pad'), str(pidfile)],
                       capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def test_two_ups_cannot_both_claim_the_rig(fp, tmp_path):
    """The double-`up` race. The pidfile used to be written inside serve(),
    ~8s after startup: two `up`s inside that window both passed
    daemon_alive(), both created a uhid pad, and the second clobbered the
    first's FIFO and pidfile - so killing "the rig" restored tv-waker while a
    fake pad was still live."""
    pidfile = tmp_path / 'fake-pad.pid'
    held = fp.claim_pidfile(str(pidfile))
    assert held is not None
    assert pidfile.read_text() == str(os.getpid())
    try:
        assert claim_in_a_child(pidfile) == 'REFUSED'
    finally:
        os.close(held)


def test_a_dead_rigs_pidfile_does_not_block_the_next_one(fp, tmp_path):
    """The lock lives as long as the process, not as long as the file: a rig
    that died hard must not lock the operator out of the next run."""
    pidfile = tmp_path / 'fake-pad.pid'
    held = fp.claim_pidfile(str(pidfile))
    assert held is not None
    os.close(held)                       # as if the holder exited
    assert claim_in_a_child(pidfile) == 'GOT'


def test_the_claim_happens_before_anything_can_leak(fp):
    """Ordering is the whole fix: claim, then arm signals, then the inhibit
    frame, then the device. Asserted structurally because the cost of getting
    it wrong is only visible on a live box."""
    src = open(os.path.join(HERE, 'fake-pad')).read()
    tree = ast.parse(src)
    daemon = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == 'daemon')
    order = []
    for node in ast.walk(daemon):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ('claim_pidfile', 'install_signal_handlers',
                                'make_device', 'serve'):
                order.append((node.lineno, node.func.id))
        if isinstance(node, ast.With):
            for item in node.items:
                if (isinstance(item.context_expr, ast.Call)
                        and getattr(item.context_expr.func, 'id', None)
                        == 'SafetyFrame'):
                    order.append((node.lineno, 'SafetyFrame'))
    names = [n for _, n in sorted(order)]
    assert names.index('claim_pidfile') < names.index('SafetyFrame')
    assert names.index('install_signal_handlers') < names.index('SafetyFrame')
    assert names.index('SafetyFrame') < names.index('make_device')


def test_serve_no_longer_owns_the_pidfile_or_the_handlers(fp):
    """Two installations of the same handler, or two writers of the same
    pidfile, is how the window between them becomes a bug. serve() reads the
    process-wide flag and nothing else."""
    src = open(os.path.join(HERE, 'fake-pad')).read()
    tree = ast.parse(src)
    serve = next(n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == 'serve')
    body = ast.dump(serve)
    assert 'signal' not in body, 'serve() installs its own signal handlers'
    assert 'PIDFILE' not in body, 'serve() still writes the pidfile'


# =========================================================================
# fake-pad: signals, and the frame that must unwind
# =========================================================================
@pytest.fixture
def restore_signals():
    saved = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    yield
    for s, h in saved.items():
        signal.signal(s, h)


@pytest.mark.parametrize('sig', [signal.SIGTERM, signal.SIGINT])
def test_signals_set_the_flag_and_never_raise(fp, restore_signals, sig):
    """A handler that RAISES can still tear the process out of
    SafetyFrame.__enter__ (20s per systemctl stop, three of them) before the
    with-body is entered, so __exit__ never runs and tv-waker/pad-record/
    pad-battery stay stopped. A flag cannot."""
    fp.STOPPING['now'] = False
    fp.install_signal_handlers()
    try:
        os.kill(os.getpid(), sig)        # must NOT raise, must NOT kill us
        time.sleep(0.05)
        assert fp.STOPPING['now'] is True
    finally:
        fp.STOPPING['now'] = False


def test_a_signal_inside_the_frame_still_unwinds_through_exit(fp, tmp_path,
                                                              monkeypatch):
    """The SIGTERM-during-__enter__ / SIGTERM-before-serve() window: whatever
    happens, the restore runs and no device is created."""
    seen = {'enter': False, 'exit': False}

    class FakeFrame:
        def __enter__(self):
            seen['enter'] = True
            return self

        def __exit__(self, *exc):
            seen['exit'] = True
            return False

    pidfile = tmp_path / 'fake-pad.pid'
    monkeypatch.setattr(fp, 'SafetyFrame', FakeFrame)
    monkeypatch.setattr(fp, 'PIDFILE', str(pidfile))
    monkeypatch.setattr(fp, 'FIFO', str(tmp_path / 'fifo'))
    monkeypatch.setattr(fp, 'STATUSFILE', str(tmp_path / 'status'))
    monkeypatch.setattr(fp, 'claim_pidfile',
                        lambda *a, **k: os.open(str(pidfile),
                                                os.O_CREAT | os.O_RDWR, 0o600))
    monkeypatch.setattr(fp, 'make_device',
                        lambda: pytest.fail('a device was created after the '
                                            'stop flag was already set'))
    fp.STOPPING['now'] = True            # as if a SIGTERM landed in __enter__
    try:
        fp.daemon()
    finally:
        fp.STOPPING['now'] = False
    assert seen == {'enter': True, 'exit': True}
    assert not pidfile.exists(), 'the claim was not cleaned up on the way out'


def test_a_second_up_is_refused_by_the_claim_not_just_by_daemon_alive(
        fp, tmp_path, monkeypatch):
    monkeypatch.setattr(fp, 'PIDFILE', str(tmp_path / 'fake-pad.pid'))
    monkeypatch.setattr(fp, 'claim_pidfile', lambda *a, **k: None)
    with pytest.raises(SystemExit) as e:
        fp.daemon()
    assert 'already up' in str(e.value)


# =========================================================================
# fake-pad: talking to a rig that may already be dead
# =========================================================================
def test_fifo_send_does_not_park_the_shell_on_a_dead_rig(fp, tmp_path,
                                                         monkeypatch):
    """Opening a FIFO for write BLOCKS until a reader arrives - forever, if
    the rig died leaving its files behind. That is the worst moment to hang:
    the inhibit units are down and the process that would restore them is the
    one that vanished."""
    fifo = tmp_path / 'fifo'
    os.mkfifo(str(fifo), 0o600)
    monkeypatch.setattr(fp, 'FIFO', str(fifo))
    started = time.time()
    with pytest.raises(SystemExit) as e:
        fp.fifo_send('press ps')
    assert time.time() - started < 5, 'fifo_send blocked'
    assert 'nothing is reading' in str(e.value)


def test_fifo_send_delivers_when_a_reader_is_there(fp, tmp_path, monkeypatch):
    fifo = tmp_path / 'fifo'
    os.mkfifo(str(fifo), 0o600)
    monkeypatch.setattr(fp, 'FIFO', str(fifo))
    rfd = os.open(str(fifo), os.O_RDONLY | os.O_NONBLOCK)
    try:
        fp.fifo_send('press ps')
        assert os.read(rfd, 4096) == b'press ps\n'
    finally:
        os.close(rfd)


# =========================================================================
# gesture-sweep: the world can change under a run
# =========================================================================
def write_status(path, session='none'):
    with open(path, 'w') as f:
        json.dump({'regions': {'session': session}}, f)


def test_a_game_starting_mid_run_stops_the_sweep(gs, tmp_path, monkeypatch):
    """preflight is check-once. A game launching mid-run turns the next
    scenario's `hold` into a real suspend_to_kodi against a LIVE session."""
    status = tmp_path / 'status.json'
    monkeypatch.setattr(gs, 'STATUS', str(status))
    monkeypatch.setattr(gs, 'GAME_SUSPENDED', str(tmp_path / 'game-suspended'))
    write_status(status, 'none')
    assert gs.still_safe_to_press() is None
    write_status(status, 'running')
    assert 'session region turned' in gs.still_safe_to_press()


def test_a_suspend_flag_appearing_mid_run_stops_the_sweep(gs, tmp_path,
                                                          monkeypatch):
    """A stale/fresh /tmp/game-suspended turns the next tap into a real
    resume: game-launch spawned and the TV woken."""
    status = tmp_path / 'status.json'
    flag = tmp_path / 'game-suspended'
    monkeypatch.setattr(gs, 'STATUS', str(status))
    monkeypatch.setattr(gs, 'GAME_SUSPENDED', str(flag))
    write_status(status, 'none')
    flag.write_text('')
    assert 'appeared mid-run' in gs.still_safe_to_press()


def test_an_unreadable_status_is_also_unsafe(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(gs, 'STATUS', str(tmp_path / 'gone.json'))
    monkeypatch.setattr(gs, 'GAME_SUSPENDED', str(tmp_path / 'game-suspended'))
    assert 'unreadable' in gs.still_safe_to_press()


def test_every_stimulus_is_guarded(gs):
    """Both send sites - the scenario loop and the disconnect scenario - must
    re-check. Structural, because the live proof costs an evening."""
    src = open(os.path.join(HERE, 'gesture-sweep')).read()
    tree = ast.parse(src)
    main = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == 'main')
    calls = [n.func.id for n in ast.walk(main)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert calls.count('still_safe_to_press') >= 2
    assert calls.count('rig_send') <= calls.count('still_safe_to_press')


# =========================================================================
# gesture-sweep: reading a log with a crash hole in it
# =========================================================================
def test_interior_nuls_do_not_destroy_a_record(gs, tmp_path):
    """An unclean shutdown leaves a HOLE, not a truncation - the 05:19 power
    event left 1154 NUL bytes mid-file. They carry no newline, so they arrive
    glued INSIDE the next record; stripping only the ends left json.loads to
    fail and the record was dropped, which grades as "the daemon did
    nothing"."""
    log = tmp_path / 'couchd.jsonl'
    rec = json.dumps({'kind': 'intent', 'verb': 'show_switcher',
                      'acted': True, 'reason': 'gesture:double-tap-switcher'})
    holed = rec[:20] + '\x00' * 12 + rec[20:]
    log.write_bytes((holed + '\n').encode())
    tail = gs.Tail(str(log))
    tail.offset = 0
    got = tail.records()
    assert len(got) == 1 and got[0]['verb'] == 'show_switcher'
    assert gs.acted(got, 'show_switcher')


def test_the_offset_only_advances_over_complete_lines(gs, tmp_path):
    log = tmp_path / 'couchd.jsonl'
    log.write_bytes(b'{"kind": "intent", "verb": "a", "acted": true}\n'
                    b'{"kind": "inte')
    tail = gs.Tail(str(log))
    tail.offset = 0
    assert len(tail.records()) == 1
    with open(log, 'ab') as f:
        f.write(b'nt", "verb": "b", "acted": true}\n')
    got = tail.records()
    assert [r['verb'] for r in got] == ['b']


# =========================================================================
# intents-archive: evidence must not be lost, duplicated or misfiled
# =========================================================================
def bend(ia, tmp_path):
    ia.SHADOW = str(tmp_path)
    ia.STATE = str(tmp_path / '.intents-archive-state.json')
    ia.SRC = str(tmp_path / 'legacy-intents.jsonl')
    return ia


def epoch(text):
    return time.mktime(time.strptime(text, '%Y-%m-%d %H:%M:%S'))


def test_lines_are_filed_by_their_own_day_not_the_clock(ia, tmp_path):
    """The timer fires every two minutes, so the run at 00:00:30 is carrying
    lines written at 23:59. Filing those under today smears one evening
    across two archives and makes the differ read short at both ends."""
    bend(ia, tmp_path)
    with open(ia.SRC, 'w') as f:
        for t, s in ((epoch('2026-08-05 23:58:30'), 'late'),
                     (epoch('2026-08-06 00:00:10'), 'early')):
            f.write(json.dumps({'t': t, 'src': 'watcher', 'verb': 'yield',
                                'subject': s}) + '\n')
    assert ia.main() == 0
    assert 'late' in (tmp_path / 'legacy-intents-20260805.jsonl').read_text()
    assert 'early' in (tmp_path / 'legacy-intents-20260806.jsonl').read_text()


def test_a_line_with_no_usable_timestamp_still_lands_somewhere(ia, tmp_path):
    bend(ia, tmp_path)
    with open(ia.SRC, 'w') as f:
        f.write('{"no t here": 1}\n')
        f.write('not json at all\n')
    assert ia.main() == 0
    today = tmp_path / f'legacy-intents-{time.strftime("%Y%m%d")}.jsonl'
    assert today.exists() and 'not json at all' in today.read_text()


def test_a_corrupt_state_file_refuses_instead_of_re_copying(ia, tmp_path,
                                                            capsys):
    """The old fallback was offset=0, which re-appended the whole source and
    doubled every line already archived. Duplicated evidence is as bad as
    lost evidence and much harder to spot."""
    bend(ia, tmp_path)
    with open(ia.SRC, 'w') as f:
        f.write(json.dumps({'t': epoch('2026-08-05 12:00:00'),
                            'subject': 'one'}) + '\n')
    assert ia.main() == 0
    archive = tmp_path / 'legacy-intents-20260805.jsonl'
    before = archive.read_text()

    with open(ia.STATE, 'w') as f:
        f.write('{"offset": 12, tru')
    assert ia.main() == 1
    assert archive.read_text() == before, 'a corrupt state duplicated evidence'
    assert 'REFUSING' in capsys.readouterr().err


def test_a_state_file_that_is_not_an_object_also_refuses(ia, tmp_path):
    bend(ia, tmp_path)
    with open(ia.SRC, 'w') as f:
        f.write('{"t": 1, "subject": "x"}\n')
    with open(ia.STATE, 'w') as f:
        f.write('[1, 2, 3]')
    assert ia.main() == 1
    assert not list(tmp_path.glob('legacy-intents-*.jsonl'))


def test_a_missing_state_file_is_an_ordinary_first_run(ia, tmp_path):
    """MISSING is not CORRUPT: the first run, and the run after a human
    deliberately deletes the state, must still copy."""
    bend(ia, tmp_path)
    with open(ia.SRC, 'w') as f:
        f.write(json.dumps({'t': epoch('2026-08-05 12:00:00'),
                            'subject': 'one'}) + '\n')
    assert ia.main() == 0
    assert (tmp_path / 'legacy-intents-20260805.jsonl').exists()


def test_nothing_new_copies_nothing(ia, tmp_path):
    bend(ia, tmp_path)
    with open(ia.SRC, 'w') as f:
        f.write(json.dumps({'t': epoch('2026-08-05 12:00:00'),
                            'subject': 'one'}) + '\n')
    assert ia.main() == 0
    archive = tmp_path / 'legacy-intents-20260805.jsonl'
    before = archive.read_text()
    assert ia.main() == 0
    assert archive.read_text() == before


def test_a_partial_last_line_is_never_copied(ia, tmp_path):
    bend(ia, tmp_path)
    good = json.dumps({'t': epoch('2026-08-05 12:00:00'), 'subject': 'one'})
    with open(ia.SRC, 'w') as f:
        f.write(good + '\n{"t": 1785, "subj')
    assert ia.main() == 0
    archive = tmp_path / 'legacy-intents-20260805.jsonl'
    assert archive.read_text() == good + '\n'


def test_the_archive_is_durable_before_the_offset_advances(ia, tmp_path,
                                                           monkeypatch):
    """The ordering that makes a crash survivable: every archived byte is
    fsync'd - file AND directory - before the state file's os.replace. The
    other order persists "copied up to N" while the bytes are still in page
    cache, and a power cut then loses them from both copies."""
    bend(ia, tmp_path)
    with open(ia.SRC, 'w') as f:
        f.write(json.dumps({'t': epoch('2026-08-05 12:00:00'),
                            'subject': 'one'}) + '\n')
    events = []
    real_fsync, real_replace = os.fsync, os.replace

    def spy_fsync(fd):
        try:
            events.append(('fsync', os.fstat(fd).st_ino))
        except OSError:
            events.append(('fsync', None))
        return real_fsync(fd)

    def spy_replace(src, dst):
        events.append(('replace', dst))
        return real_replace(src, dst)

    monkeypatch.setattr(os, 'fsync', spy_fsync)
    monkeypatch.setattr(os, 'replace', spy_replace)
    assert ia.main() == 0
    monkeypatch.undo()

    kinds = [e[0] for e in events]
    assert 'replace' in kinds, 'the state file was never replaced'
    assert kinds.index('fsync') < kinds.index('replace')
    archive = tmp_path / 'legacy-intents-20260805.jsonl'
    dir_ino = os.stat(tmp_path).st_ino
    file_ino = os.stat(archive).st_ino
    synced = [ino for kind, ino in events if kind == 'fsync']
    before_replace = synced[:kinds.index('replace')]
    assert file_ino in before_replace, 'the archive file was not fsynced'
    assert dir_ino in before_replace, 'the archive directory was not fsynced'
