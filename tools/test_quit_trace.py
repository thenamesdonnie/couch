"""quit-trace: the close-forensics recorder.

The Tracer is exercised synchronously against real child processes; the
game-world PATTERNS are stubbed to something unmatchable in most tests so
whatever Steam machinery happens to live on the box cannot leak into the
assertions.
"""
import importlib.util
import importlib.machinery
import json
import os
import re
import subprocess
import threading
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_loader(
    'quit_trace', importlib.machinery.SourceFileLoader(
        'quit_trace', os.path.join(HERE, 'quit-trace')))
qt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qt)

MATCH_NOTHING = re.compile(r'\bx-nothing-matches-this-x\b')


@pytest.fixture
def child():
    procs = []

    def spawn(seconds='300'):
        p = subprocess.Popen(['sleep', seconds])
        procs.append(p)
        return p

    yield spawn
    for p in procs:
        if p.poll() is None:
            p.kill()
        p.wait()


# -- tracked_set ----------------------------------------------------------
def test_kernel_threads_never_match():
    procs = {2: ('kthreadd', 'S', 0), 42: ('oom_reaper', 'S', 2)}
    cmds = {2: [], 42: []}
    assert qt.tracked_set(procs, cmds, roster=set()) == set()


def test_roster_patterns_and_descendants():
    procs = {10: ('bash', 'S', 1), 20: ('shadps4', 'S', 10),
             30: ('helper', 'S', 20), 40: ('unrelated', 'S', 1),
             50: ('rostered', 'T', 1), 60: ('kid-of-rostered', 'S', 50)}
    cmds = {p: [procs[p][0]] for p in procs}
    got = qt.tracked_set(procs, cmds, roster={50})
    assert got == {20, 30, 50, 60}, 'pattern + roster + both closures'
    assert 40 not in got and 10 not in got


def test_the_idle_steam_client_is_not_game_world():
    """The client's own steamwebhelper tree lives under an srt-bwrap whose
    cmdline says pressure-vessel; it must stay out of frame. A GAME's
    pressure-vessel tree descends from Steam's reaper and is captured by
    that seed's closure instead."""
    procs = {100: ('srt-bwrap', 'S', 1), 101: ('steamwebhelper', 'S', 100),
             200: ('reaper', 'S', 1), 201: ('srt-bwrap', 'S', 200),
             202: ('eldenring.exe', 'S', 201)}
    cmds = {100: ['/steamrt/pressure-vessel/srt-bwrap'],
            101: ['./steamwebhelper'],
            200: ['/steam/ubuntu12_32/reaper'],
            201: ['/steamrt/pressure-vessel/srt-bwrap'],
            202: ['Z:\\eldenring.exe']}
    got = qt.tracked_set(procs, cmds, roster=set())
    assert got == {200, 201, 202}, \
        'reaper tree in, client web helper tree out'


def test_a_reparented_process_stays_tracked_by_identity():
    """The ER-leak shape: eldenring.exe's ancestors die and it reparents to
    init - a tree walk loses it, an identity match must not."""
    procs = {70: ('eldenring.exe', 'S', 1)}   # parent is init already
    cmds = {70: ['Z:\\eldenring.exe']}
    assert qt.tracked_set(procs, cmds, roster=set()) == {70}


# -- the tracer loop ------------------------------------------------------
def run_tracer(tmp_path, monkeypatch, roster_pids, body):
    """Drive a real Tracer in a thread with roster-only tracking; `body`
    gets (child-management window) while it samples."""
    monkeypatch.setattr(qt, 'PATTERNS', MATCH_NOTHING)
    monkeypatch.setattr(qt, 'read_windows', lambda: None)
    trace = str(tmp_path / 'trace.jsonl')
    roster = str(tmp_path / 'roster')
    done = str(tmp_path / 'done')
    with open(roster, 'w') as f:
        f.write('\n'.join(f'{p} 0 x' for p in roster_pids) + '\n')
    tr = qt.Tracer(trace, 'test', roster, interval=0.05, post=0.15,
                   max_s=10.0, done_flag=done)
    th = threading.Thread(target=tr.run)
    th.start()
    try:
        body()
    finally:
        open(done, 'w').close()
        th.join(timeout=10)
    assert not th.is_alive(), 'tracer must stop after done + post'
    with open(trace) as f:
        return [json.loads(line) for line in f]


def test_a_death_is_recorded_with_its_time(tmp_path, monkeypatch, child):
    p = child()

    def body():
        time.sleep(0.2)
        p.terminate()
        p.wait()
        time.sleep(0.2)

    recs = run_tracer(tmp_path, monkeypatch, [p.pid], body)
    procs = [r for r in recs if r['kind'] == 'proc']
    assert [r['pid'] for r in procs] == [p.pid]
    assert procs[0]['roster'] is True
    summary = recs[-1]
    assert summary['kind'] == 'summary'
    entry = summary['procs'][str(p.pid)]
    assert 'died' in entry and 'survived' not in entry
    assert summary['survivors'] == []


def test_a_survivor_is_named(tmp_path, monkeypatch, child):
    p = child()
    recs = run_tracer(tmp_path, monkeypatch, [p.pid],
                      lambda: time.sleep(0.2))
    summary = recs[-1]
    assert summary['survivors'] == [p.pid]
    assert summary['procs'][str(p.pid)]['survived'] is True


def test_a_state_change_lands_in_the_timeline(tmp_path, monkeypatch, child):
    p = child()

    def body():
        time.sleep(0.2)
        os.kill(p.pid, 19)          # SIGSTOP: S -> T, the freeze shape
        time.sleep(0.2)
        os.kill(p.pid, 18)
        time.sleep(0.1)

    recs = run_tracer(tmp_path, monkeypatch, [p.pid], body)
    states = [s for _t, s in recs[-1]['procs'][str(p.pid)]['states']]
    assert 'T' in states, f'freeze must be visible in {states}'


# -- marks and report -----------------------------------------------------
def test_mark_is_silent_with_no_trace_running(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(qt, 'CURRENT', str(tmp_path / 'nope'))
    assert qt.main(['mark', 'anything']) == 0


def test_report_orders_marks_deaths_and_say_lines(tmp_path, monkeypatch,
                                                  capsys):
    trace = tmp_path / 'quit-x.jsonl'
    t0 = time.time()
    rows = [
        {'kind': 'begin', 't': t0, 'why': 'test'},
        {'kind': 'proc', 't': t0, 'pid': 9, 'comm': 'eldenring.exe',
         'ppid': 1, 'cmd': ['er.exe'], 'roster': True},
        {'kind': 'mark', 't': t0 + 1, 'label': 'wm-delete-asked',
         'windows': '3'},
        {'kind': 'summary', 't': t0 + 5, 'why': 'test', 'survivors': [9],
         'procs': {'9': {'comm': 'eldenring.exe', 'cmd': ['er.exe'],
                         'first': t0, 'survived': True,
                         'states': [[t0, 'S'], [t0 + 2, 'T']]}}},
    ]
    with open(trace, 'w') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    saylog = tmp_path / 'say.log'
    stamp = time.strftime('%H:%M:%S', time.localtime(t0 + 3))
    saylog.write_text(f'{stamp}.000 closing shadps4\nnot a stamped line\n')
    monkeypatch.setattr(qt, 'SAY_LOG', str(saylog))
    assert qt.main(['report', str(trace)]) == 0
    out = capsys.readouterr().out
    order = [out.index(x) for x in
             ('eldenring.exe', 'wm-delete-asked', '-> T',
              'say: closing shadps4', 'SURVIVORS')]
    assert order == sorted(order), f'timeline out of order:\n{out}'


def test_report_says_clean_when_everything_died(tmp_path, capsys):
    trace = tmp_path / 'quit-clean.jsonl'
    t0 = time.time()
    with open(trace, 'w') as f:
        f.write(json.dumps({'kind': 'begin', 't': t0, 'why': 'x'}) + '\n')
        f.write(json.dumps({'kind': 'summary', 't': t0 + 1, 'why': 'x',
                            'survivors': [], 'procs': {}}) + '\n')
    assert qt.main(['report', str(trace)]) == 0
    assert 'CLEAN' in capsys.readouterr().out


# -- the CLI round trip, daemon and all -----------------------------------
def test_cli_start_mark_done_produces_a_summary(tmp_path):
    if os.path.exists(qt.PIDFILE):
        pytest.skip('a real quit-trace is running; not touching it')
    tool = os.path.join(HERE, 'quit-trace')
    out_dir = str(tmp_path / 'traces')
    r = subprocess.run([tool, 'start', '--why', 'selftest',
                        '--interval', '0.05', '--post', '0.2', '--max', '10',
                        '--roster', str(tmp_path / 'no-roster'),
                        '--out-dir', out_dir],
                       capture_output=True, text=True, timeout=10)
    assert r.returncode == 0 and 'tracing ->' in r.stdout
    time.sleep(0.3)
    subprocess.run([tool, 'mark', 'selftest-mark', 'k=v'], timeout=10)
    subprocess.run([tool, 'done'], timeout=10)
    deadline = time.time() + 10
    while os.path.exists(qt.PIDFILE) and time.time() < deadline:
        time.sleep(0.1)
    assert not os.path.exists(qt.PIDFILE), 'tracer must clean up after itself'
    traces = os.listdir(out_dir)
    assert len(traces) == 1 and 'selftest' in traces[0]
    with open(os.path.join(out_dir, traces[0])) as f:
        recs = [json.loads(line) for line in f]
    kinds = [r['kind'] for r in recs]
    assert kinds[0] == 'begin' and kinds[-1] == 'summary'
    assert any(r['kind'] == 'mark' and r.get('label') == 'selftest-mark'
               and r.get('k') == 'v' for r in recs)
