#!/usr/bin/env python3
"""Unit tests for ~/.local/bin/game-appid - the Big Picture appid resolver.

Everything here is synthetic ledger text into pure functions. No Steam, no
/proc, no files: the two impure edges (which log file to read, which pids are
live) are the caller's, and are covered by the operator's live re-test.

The fixture text is copied from the REAL log on this box, 5 Aug 2026, spellings
and all - including the "no longer tracking" form, which is not the spelling
the original brief assumed ("Remove <id> from running list"). Both are handled
because both have shipped.

Run:  couchd/.venv/bin/pytest tools/test_game_appid.py -q
"""
import importlib.machinery
import importlib.util
import os

HOME = os.path.expanduser('~')
_spec = importlib.util.spec_from_loader(
    'game_appid', importlib.machinery.SourceFileLoader(
        'game_appid', os.path.join(HOME, '.local/bin/game-appid')))
game_appid = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(game_appid)

from_ledger = game_appid.from_ledger
tracked_pids = game_appid.tracked_pids

# Two games in one evening: 1086940 (Baldur's Gate 3) opened and fully torn
# down, then 367520 (Hollow Knight) started from inside Big Picture. Steam
# recycles nothing here, but it does drop pids mid-session.
LEDGER = """
[2026-08-05 01:10:01] AppID 1086940 adding PID 900 as a tracked process "reaper SteamLaunch AppId=1086940"
[2026-08-05 01:10:01] AppID 1086940 adding PID 901 as a tracked process
[2026-08-05 01:10:02] AppID 1086940 adding PID 902 as a tracked process
[2026-08-05 01:10:09] SSGL: InternalUpdateClientGame indicates change to games list
[2026-08-05 01:55:00] AppID 1086940 no longer tracking PID 902, exit code 0
[2026-08-05 01:55:01] Remove 1086940 from running list
[2026-08-05 02:30:36] AppID 367520 adding PID 1688799 as a tracked process "reaper SteamLaunch AppId=367520"
[2026-08-05 02:30:36] AppID 367520 adding PID 1688800 as a tracked process
[2026-08-05 02:30:38] AppID 367520 adding PID 1688919 as a tracked process
[2026-08-05 02:30:39] AppID 367520 no longer tracking PID 1688800, exit code -1
[2026-08-05 02:30:40] AppID 367520 adding PID 1689005 as a tracked process
"""


def test_the_replay_keeps_only_what_is_still_tracked():
    live = tracked_pids(LEDGER)
    assert live['367520'] == {1688799, 1688919, 1689005}   # 1688800 dropped
    assert live['1086940'] == set()                        # whole game retired


def test_the_running_game_is_resolved_from_its_pids():
    assert from_ledger(LEDGER, [1688799, 1688919, 1689005, 4242]) == '367520'


def test_one_overlapping_pid_is_enough():
    """Steam tracks the reaper itself, which is the single process game-pids
    roots its whole tree on - so an overlap of one is decisive."""
    assert from_ledger(LEDGER, [1688799]) == '367520'


def test_a_finished_game_never_wins():
    """1086940's pids are all retired; asking with them resolves to nothing
    rather than to a game that ended an hour ago."""
    assert from_ledger(LEDGER, [900, 901, 902]) is None


def test_the_biggest_overlap_breaks_a_tie():
    """Pids are recycled by the kernel. A stale appid that happens to share one
    reused number must not outvote the game that owns the rest."""
    text = LEDGER + (
        '[2026-08-05 02:31:00] AppID 999999 adding PID 1688799 as a tracked process\n')
    assert from_ledger(text, [1688799, 1688919, 1689005]) == '367520'


def test_no_pids_resolves_to_nothing():
    assert from_ledger(LEDGER, []) is None


def test_an_unknown_pid_set_resolves_to_nothing():
    assert from_ledger(LEDGER, [7, 8, 9]) is None


def test_a_readd_after_a_drop_counts_as_tracked():
    """Order is the only thing that matters in the replay."""
    text = LEDGER + (
        '[2026-08-05 02:31:10] AppID 367520 adding PID 1688800 as a tracked process\n')
    assert 1688800 in tracked_pids(text)['367520']


def test_the_older_removing_spelling_is_understood():
    """Steam has used both; the box currently writes "no longer tracking"."""
    text = ('[x] AppID 42 adding PID 5 as a tracked process\n'
            '[x] AppID 42 removing PID 5\n')
    assert tracked_pids(text)['42'] == set()


def test_garbage_lines_are_ignored():
    assert from_ledger('not a ledger at all\n\n[x] SSGL: noise\n', [1]) is None


def test_the_reaper_argv_fallback_reads_the_appid():
    """The second source, parsed from the same argv game-pids already matches
    on. The /proc read itself is the impure edge and is not tested here."""
    m = game_appid.REAPER.search(
        '/…/reaper SteamLaunch AppId=367520 -- /…/_v2-entry-point --verb=waitforexitandrun')
    assert m and m.group(1) == '367520'


def test_ledger_paths_dedupes_the_symlinked_steam_roots():
    """~/.steam/steam is a symlink to ~/.steam/debian-installation on this box,
    so the same file must not be read (or ranked) twice."""
    paths = game_appid.ledger_paths()
    assert len(paths) == len(set(paths))
