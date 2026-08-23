#!/usr/bin/env python3
"""Tests for tools/spotify-heal: does it read the journal the way we read it?

NOTHING here touches the live box. The two functions under test - judge()
and plan() - take a history and a clock and return a verdict, so every case
below is a fabricated journal and a fabricated `now`. No journalctl, no
dbus, no systemctl, and therefore no way for a failing test to restart
Donnie's speaker mid-track.

The histories are not invented shapes. Four of them are transcribed from the
real spotifyd journal on donniespc, including the two that matter most:

  * 21 Aug 18:27:37 died, 18:28:29 back by itself - 52 seconds. This is why
    a death has to age before we believe it, and it is the case a naive
    watchdog would have restarted for no reason.
  * 22 Aug 00:45:30 died, 02:48:03 said so again, and then NOTHING for forty
    hours while systemd showed active (running). This is the bug.

Run:  couchd/.venv/bin/python -m pytest tools/test_spotify_heal.py -q
"""
import importlib.machinery
import importlib.util
import os
from datetime import datetime, timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, 'spotify-heal')


def load():
    if not os.path.exists(TOOL):
        pytest.skip('tools/spotify-heal not present')
    loader = importlib.machinery.SourceFileLoader('spotify_heal_under_test',
                                                  TOOL)
    spec = importlib.util.spec_from_loader('spotify_heal_under_test', loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def sh():
    return load()


def when(day, hhmm, sec=0):
    """A tz-aware moment in the real journal's timezone (BST, +01:00)."""
    return datetime.fromisoformat(f'2026-08-{day:02d}T{hhmm}:{sec:02d}+01:00')


def journal(*lines):
    """Build journalctl -o short-iso text from (day, hh:mm, ss, who, msg)."""
    out = []
    for day, hhmm, sec, who, msg in lines:
        stamp = when(day, hhmm, sec).isoformat()
        out.append(f'{stamp} donniespc {who}: {msg}')
    return '\n'.join(out) + '\n'


SPOTIFYD = 'spotifyd[2830]'
SYSTEMD = 'systemd[2631]'

# The healthy start, verbatim from 23 Aug 18:21.
BORN = [
    (23, '18:21', 49, SYSTEMD,
     'Started spotifyd.service - Spotify Connect receiver (spotifyd).'),
    (23, '18:21', 49, SPOTIFYD,
     '[INFO] Connecting to AP "ap-gew1.spotify.com:443"'),
    (23, '18:21', 50, SPOTIFYD,
     "[INFO] Authenticated as 'ktjzmzy60oomoy74wqztu8479' !"),
    (23, '18:21', 50, SPOTIFYD,
     '[INFO] active device is <> with session <7Hj6sO6vSKmxdbUPKZ5hio>'),
]


def verdict_for(sh, lines, now):
    return sh.judge(sh.parse_journal(journal(*lines)), now)


# =========================================================================
# ALIVE. The current state of the box, which must be left alone.
# =========================================================================

def test_alive_after_a_clean_start(sh):
    """23 Aug 18:21, exactly as it stands now: authenticated, idle, and the
    active device is EMPTY. The empty device is the normal idle broadcast
    and must not read as a death."""
    v = verdict_for(sh, BORN, when(23, '18:25'))
    assert v.state == 'alive'
    assert 'Authenticated as' in v.marker


def test_alive_stays_alive_after_days_of_silence(sh):
    """An idle speaker logs nothing for days. Silence after a life marker is
    not evidence of anything, no matter how long it runs."""
    v = verdict_for(sh, BORN, when(23, '18:21') + timedelta(days=3))
    assert v.state == 'alive'


def test_alive_while_a_phone_is_driving_it(sh):
    """A track load can only happen over a working session, so it clears an
    earlier websocket warning on its own."""
    lines = BORN + [
        (23, '18:23', 0, SPOTIFYD,
         '[WARN] Websocket connection failed: WebSocket protocol error'),
        (23, '18:24', 26, SPOTIFYD,
         '[INFO] Loading <Sandman> with Spotify URI <spotify:track:14lD>'),
    ]
    v = verdict_for(sh, lines, when(23, '19:00'))
    assert v.state == 'alive'


def test_unknown_history_does_nothing(sh):
    """An empty window (nothing in the journal at all) is not a death. The
    only safe move on no evidence is no move."""
    v = sh.judge([], when(23, '18:25'))
    assert v.state == 'unknown'
    assert sh.plan(v, False, None, when(23, '18:25')).action == 'none'


def test_chatter_never_votes(sh):
    """Volume updates and the context warning are the noisiest lines in the
    journal and mean nothing either way."""
    for msg in ('[INFO] delayed volume update for all devices: volume is now 65535',
                "[WARN] couldn't load context info because: context is not available",
                '[INFO] Connecting to AP "ap-gew1.spotify.com:443"',
                '[INFO] active device is <> with session <2CRzv5ymKvbYuA0gbTibTB>'):
        assert sh.classify(msg) is None, msg


# =========================================================================
# DEAD. The forty-hour bug.
# =========================================================================

def test_dead_the_forty_hour_silence(sh):
    """22 Aug 00:45 -> 23 Aug 18:21, the real one. Systemd said active the
    whole way."""
    lines = BORN[:1] + [
        (21, '09:03', 37, SPOTIFYD,
         "[INFO] Authenticated as 'ktjzmzy60oomoy74wqztu8479' !"),
        (22, '00:45', 30, SPOTIFYD, '[ERROR] Connection to server closed.'),
        (22, '02:48', 3, SPOTIFYD, '[WARN] Websocket peer does not respond.'),
    ]
    now = when(23, '18:21')
    v = verdict_for(sh, lines, now)
    assert v.state == 'dead'
    assert sh.plan(v, False, None, now).action == 'heal'


def test_dead_when_the_redial_hangs(sh):
    """A death, then `Connecting to AP`, then nothing. Dialling is not
    connected: this is still dead."""
    lines = BORN + [
        (23, '19:00', 0, SPOTIFYD, '[ERROR] Connection to server closed.'),
        (23, '19:01', 0, SPOTIFYD,
         '[INFO] Connecting to AP "ap-gew1.spotify.com:443"'),
    ]
    v = verdict_for(sh, lines, when(23, '19:30'))
    assert v.state == 'dead'


# =========================================================================
# DEAD THEN RECOVERED. spotifyd's own redial, which we must not step on.
# =========================================================================

def test_dead_then_recovered_is_alive(sh):
    """21 Aug: died 18:27:37, authenticated again 18:28:30. Alive, and alive
    however long ago it happened."""
    lines = BORN[:1] + [
        (21, '18:27', 37, SPOTIFYD, '[ERROR] Connection to server closed.'),
        (21, '18:28', 29, SPOTIFYD,
         '[INFO] Connecting to AP "ap-gew1.spotify.com:443"'),
        (21, '18:28', 30, SPOTIFYD,
         "[INFO] Authenticated as 'ktjzmzy60oomoy74wqztu8479' !"),
        (21, '18:28', 30, SPOTIFYD,
         '[INFO] active device is <20a82e0d15ca2b7a> with session <2CRzv5>'),
    ]
    for now in (when(21, '18:35'), when(23, '18:00')):
        assert verdict_for(sh, lines, now).state == 'alive'


def test_a_restart_wipes_the_slate(sh):
    """The unit's own restart line ends the previous process's history: a
    death before it is not evidence about the process running now."""
    lines = [
        (22, '00:45', 30, SPOTIFYD, '[ERROR] Connection to server closed.'),
        (23, '18:21', 49, SYSTEMD,
         'Started spotifyd.service - Spotify Connect receiver (spotifyd).'),
    ]
    v = verdict_for(sh, lines, when(23, '19:30'))
    assert v.state == 'unknown'           # fresh process, nothing said yet
    assert sh.plan(v, False, None, when(23, '19:30')).action == 'none'


def test_a_new_pid_wipes_the_slate(sh):
    """Same guarantee without the systemd line: pid 2830's death says nothing
    about pid 59665."""
    lines = [
        (22, '00:45', 30, 'spotifyd[2830]',
         '[ERROR] Connection to server closed.'),
        (23, '18:21', 50, 'spotifyd[59665]',
         "[INFO] Authenticated as 'ktjzmzy60oomoy74wqztu8479' !"),
        (23, '18:22', 0, 'spotifyd[59665]',
         '[INFO] delayed volume update for all devices: volume is now 65535'),
    ]
    assert verdict_for(sh, lines, when(23, '19:30')).state == 'alive'


# =========================================================================
# DEAD BUT PLAYING. The absolute veto.
# =========================================================================

def test_dead_but_playing_is_never_touched(sh):
    """If sound is coming out, the journal is wrong and the journal loses.
    Notable, though: we want to see this in the log if it ever happens."""
    lines = BORN + [
        (23, '19:00', 0, SPOTIFYD, '[WARN] Websocket peer does not respond.'),
    ]
    now = when(23, '20:00')
    v = verdict_for(sh, lines, now)
    assert v.state == 'dead'
    step = sh.plan(v, True, None, now)
    assert step.action == 'none'
    assert step.reason == 'playing'
    assert step.notable


def test_absent_mpris_is_not_a_veto(sh):
    """The MPRIS name only exists while a session is live, so 'no player' is
    the normal idle state - it must not stop a heal."""
    lines = BORN + [
        (23, '19:00', 0, SPOTIFYD, '[WARN] Websocket peer does not respond.'),
    ]
    now = when(23, '20:00')
    assert sh.plan(verdict_for(sh, lines, now), False, None, now).action == 'heal'


# =========================================================================
# DEBOUNCE AND COOLDOWN.
# =========================================================================

def test_dead_under_five_minutes_is_left_to_settle(sh):
    """The 52-second self-recovery is why this exists. At four minutes we
    wait; at six we act."""
    lines = BORN + [
        (23, '19:00', 0, SPOTIFYD, '[ERROR] Connection to server closed.'),
    ]
    early = when(23, '19:04')
    v = verdict_for(sh, lines, early)
    assert v.state == 'settling'
    assert sh.plan(v, False, None, early).action == 'none'
    assert not sh.plan(v, False, None, early).notable

    late = when(23, '19:06')
    assert verdict_for(sh, lines, late).state == 'dead'


def test_the_boundary_is_exactly_dead_after(sh):
    lines = BORN + [
        (23, '19:00', 0, SPOTIFYD, '[ERROR] Connection to server closed.'),
    ]
    base = when(23, '19:00')
    assert verdict_for(sh, lines,
                       base + timedelta(seconds=sh.DEAD_AFTER - 1)).state == 'settling'
    assert verdict_for(sh, lines,
                       base + timedelta(seconds=sh.DEAD_AFTER)).state == 'dead'


def test_one_heal_per_cooldown(sh):
    """A restart that does not fix it must produce log lines, not a restart
    every five minutes."""
    lines = BORN + [
        (23, '19:00', 0, SPOTIFYD, '[ERROR] Connection to server closed.'),
    ]
    now = when(23, '19:30')
    v = verdict_for(sh, lines, now)
    just_healed = now - timedelta(seconds=sh.COOLDOWN / 2)
    held = sh.plan(v, False, just_healed, now)
    assert held.action == 'none' and held.reason == 'cooldown' and held.notable

    long_ago = now - timedelta(seconds=sh.COOLDOWN * 2)
    assert sh.plan(v, False, long_ago, now).action == 'heal'


# =========================================================================
# The parser itself.
# =========================================================================

def test_parser_survives_the_real_journal_furniture(sh):
    """Boot separators, the CPU-time line, blank lines: skipped, not guessed
    at."""
    text = (
        '-- Boot 5696b2f345fc4b538db390fd924d28cc --\n'
        '\n'
        '2026-08-23T18:21:49+01:00 donniespc systemd[2631]: '
        'spotifyd.service: Consumed 1.199s CPU time, 21.7M memory peak.\n'
        '2026-08-23T18:21:50+01:00 donniespc spotifyd[59665]: '
        "[INFO] Authenticated as 'ktjzmzy60oomoy74wqztu8479' !\n"
    )
    events = sh.parse_journal(text)
    assert len(events) == 1
    assert events[0].kind == 'life' and events[0].pid == 59665


def test_every_observed_death_line_is_recognised(sh):
    """Transcribed from the journal. If spotifyd rewords one of these the
    watchdog goes blind, so they are pinned here."""
    for msg in ('[WARN] Websocket peer does not respond.',
                '[ERROR] Connection to server closed.',
                '[WARN] Websocket connection failed: WebSocket protocol error: '
                'Connection reset without closing handshake',
                '[WARN] Error while closing websocket: Trying to work with '
                'closed connection',
                '[ERROR] connection to spotify failed: Service unavailable'):
        assert sh.classify(msg) == 'death', msg
