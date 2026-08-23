"""quit-sweep: the post-quit liveness contract, against real processes.

Every test spawns its own throwaway children (sleep), so nothing here can
touch a real game; the pid-reuse test fakes the roster instead of waiting
for the kernel to actually reuse a pid.
"""
import importlib.util
import os
import signal
import subprocess
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_loader(
    'quit_sweep', importlib.machinery.SourceFileLoader(
        'quit_sweep', os.path.join(HERE, 'quit-sweep')))
qs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qs)


@pytest.fixture
def child():
    procs = []

    def spawn():
        p = subprocess.Popen(['sleep', '300'])
        procs.append(p)
        return p

    yield spawn
    for p in procs:
        if p.poll() is None:
            p.kill()
        p.wait()


def test_starttime_reads_a_real_process(child):
    p = child()
    assert qs.starttime(p.pid) is not None
    assert qs.starttime(999999999) is None


def test_capture_skips_the_already_dead(tmp_path, child):
    p = child()
    dead = subprocess.Popen(['true'])
    dead.wait()
    roster = str(tmp_path / 'roster')
    qs.capture(roster, [p.pid, dead.pid])
    rows = qs.load_roster(roster)
    assert [r[0] for r in rows] == [p.pid]


def test_a_clean_quit_verifies_clean(tmp_path, child):
    p = child()
    roster = str(tmp_path / 'roster')
    qs.capture(roster, [p.pid])
    p.terminate()
    p.wait()
    assert qs.verify(roster, grace=1.0) == 0


def test_a_survivor_is_terminated_and_reported(tmp_path, child, capsys):
    p = child()
    roster = str(tmp_path / 'roster')
    qs.capture(roster, [p.pid])
    rc = qs.verify(roster, grace=5.0, natural=0.2)
    assert rc == 1, 'a leak must be reported even when cleaned'
    assert p.wait(timeout=5) is not None
    out = capsys.readouterr().out
    assert 'LEAK' in out and str(p.pid) in out


def test_a_term_ignorer_is_killed(tmp_path, capsys):
    # A child that ignores SIGTERM: only SIGKILL can end it.
    p = subprocess.Popen(
        ['python3', '-c',
         'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); '
         'print("up", flush=True); time.sleep(300)'],
        stdout=subprocess.PIPE)
    try:
        assert p.stdout.readline().strip() == b'up'
        roster = str(tmp_path / 'roster')
        qs.capture(roster, [p.pid])
        rc = qs.verify(roster, grace=1.0, natural=0.2)
        assert rc == 1
        assert p.wait(timeout=5) == -signal.SIGKILL
        assert 'KILL' in capsys.readouterr().out
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()


def test_a_reused_pid_is_never_touched(tmp_path, child, capsys):
    """The roster says pid X started at time T; the live X started at T'.

    That is some innocent process that inherited the number - it must be
    left alone and said so."""
    p = child()
    roster = str(tmp_path / 'roster')
    real = qs.starttime(p.pid)
    with open(roster, 'w') as f:
        f.write(f'{p.pid} {real - 12345} eldenring.exe\n')
    assert qs.verify(roster, grace=1.0) == 0
    assert p.poll() is None, 'the reused pid must survive'
    assert 'reused' in capsys.readouterr().out


def test_an_unreadable_roster_is_a_usage_error(tmp_path):
    assert qs.verify(str(tmp_path / 'missing'), grace=1.0) == 2


def test_cli_capture_and_verify_round_trip(tmp_path, child):
    p = child()
    roster = str(tmp_path / 'roster')
    tool = os.path.join(HERE, 'quit-sweep')
    r = subprocess.run([tool, 'capture', roster, '--pids', str(p.pid)],
                       capture_output=True, text=True)
    assert r.returncode == 0 and 'captured 1' in r.stdout
    p.terminate(); p.wait()
    r = subprocess.run([tool, 'verify', roster, '--grace', '1'],
                       capture_output=True, text=True)
    assert r.returncode == 0 and 'clean' in r.stdout


def test_a_straggler_that_dies_on_its_own_is_not_a_leak(tmp_path, capsys):
    """bb-event-tail's shape (23 Aug, the first live trace): a sibling
    cleaner on a 2s poll follows the game down moments after the roster
    check starts. It must be given time to die untouched."""
    p = subprocess.Popen(['sleep', '0.4'])
    try:
        roster = str(tmp_path / 'roster')
        qs.capture(roster, [p.pid])
        rc = qs.verify(roster, grace=1.0, natural=3.0)
        assert rc == 0, 'a natural death within the grace is not a leak'
        out = capsys.readouterr().out
        assert 'stragglers' in out and 'LEAK' not in out
    finally:
        if p.poll() is None:
            p.kill()
        p.wait()
