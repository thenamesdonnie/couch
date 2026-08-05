#!/usr/bin/env python3
"""Regression tests for FlagObserver.read_all.

The 5 Aug 2026 ~03:00 startup hang: /tmp/vpad.fifo (a FIFO left behind by the
fake-pad rig with no live guard) was blocking-open()ed by read_all, parking
the whole daemon in fifo_open/wait_for_partner before sd_notify READY.
read_all must stat-gate: only regular files get their content read; special
files are observed by existence alone. These tests run read_all in a daemon
thread with a join timeout so a regression fails in seconds instead of
hanging pytest forever.

    .venv/bin/python -m pytest test_flagobserver.py -q
"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import couchd
from couchd import FlagObserver, Source

READ_ALL_TIMEOUT = 5.0


class FakeLog:
    def __init__(self):
        self.entries = []

    def write(self, entry):
        self.entries.append(entry)


class FakeWorld:
    def __init__(self):
        self.log = FakeLog()
        self.sources = {}

    def src(self, name):
        return self.sources.setdefault(name, Source(name))

    def attention(self, reason):
        pass


def run_observer(tmp_path, monkeypatch):
    """Construct FlagObserver (which calls read_all) against tmp_path,
    bounded by a timeout. Returns the observer or fails the test on hang."""
    monkeypatch.setattr(couchd, 'TMP_DIR', str(tmp_path))
    world = FakeWorld()
    box = {}

    def build():
        box['obs'] = FlagObserver(world)

    t = threading.Thread(target=build, daemon=True)
    t.start()
    t.join(READ_ALL_TIMEOUT)
    assert not t.is_alive(), (
        'FlagObserver.read_all hung >%ss - blocking open of a special file?'
        % READ_ALL_TIMEOUT)
    return box['obs'], world


def test_fifo_in_watched_dir_does_not_hang(tmp_path, monkeypatch):
    os.mkfifo(tmp_path / 'vpad.fifo')
    (tmp_path / 'game-session').write_text('111 steam 367520\n')
    obs, world = run_observer(tmp_path, monkeypatch)
    # the fifo is observed by existence, not content
    content, mtime = obs.state['vpad.fifo']
    assert content is not None
    assert content.startswith('<')
    assert mtime is not None
    # regular files still read normally
    assert obs.state['game-session'][0] == '111 steam 367520'


def test_fifo_appearing_later_does_not_hang(tmp_path, monkeypatch):
    obs, world = run_observer(tmp_path, monkeypatch)
    assert obs.state['vpad.fifo'][0] is None
    os.mkfifo(tmp_path / 'vpad.fifo')

    changed_box = {}

    def reread():
        changed_box['changed'] = obs.read_all()

    t = threading.Thread(target=reread, daemon=True)
    t.start()
    t.join(READ_ALL_TIMEOUT)
    assert not t.is_alive(), 'read_all hung on a FIFO that appeared later'
    assert any(name == 'vpad.fifo' for name, _, _ in changed_box['changed'])


def test_missing_files_read_as_absent(tmp_path, monkeypatch):
    obs, world = run_observer(tmp_path, monkeypatch)
    for name in sorted(couchd.WATCHED_TMP):
        assert obs.state[name] == (None, None)
