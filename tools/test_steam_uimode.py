#!/usr/bin/env python3
"""Unit tests for ~/.local/bin/steam-uimode - Steam's UI mode detection.

Pure: synthetic ledger text and synthetic argv strings into the two parsers.
The impure edges (which log file exists, walking /proc) are the caller's and
are covered by the operator's live re-test.

Fixture lines are copied from the REAL logs on this box, 5 Aug 2026 - including
the two transitions that bracket the operator's Big Picture session:
    [2026-08-05 02:28:57] SSGL: UI mode (7->4)     he opened Big Picture
    [2026-08-05 02:30:32] SSGL: UI mode (4->7)     he left it

Run:  couchd/.venv/bin/pytest tools/test_steam_uimode.py -q
"""
import importlib.machinery
import importlib.util
import os

HOME = os.path.expanduser('~')
_spec = importlib.util.spec_from_loader(
    'steam_uimode', importlib.machinery.SourceFileLoader(
        'steam_uimode', os.path.join(HOME, '.local/bin/steam-uimode')))
uimode = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uimode)

from_ledger = uimode.from_ledger
from_argv = uimode.from_argv
BIG_PICTURE = uimode.BIG_PICTURE
DESKTOP = uimode.DESKTOP

LEDGER = """\
[2026-08-04 18:34:13] SSGL: UI mode (7->4)
[2026-08-04 18:34:55] SSGL: UI mode (4->7)
[2026-08-05 02:28:57] SSGL: UI mode (7->4)
[2026-08-05 02:30:32] AppID 367520 adding PID 1688799 as a tracked process
[2026-08-05 02:30:32] SSGL: UI mode (4->7)
"""

ARGV = ('./steamwebhelper -nocrashdialog -lang=en_US '
        '-cachedir=/home/ds2000/.steam/debian-installation/config/htmlcache '
        '-steampid=7154 -buildid=1785799196 -steamid=0 -uimode=7 -startcount=0')


# --------------------------------------------------------------- the ledger
def test_the_newest_transition_wins():
    """The arrow's RIGHT side is the mode Steam is in now."""
    assert from_ledger(LEDGER) == DESKTOP == 7


def test_a_switch_into_big_picture_is_read():
    assert from_ledger(LEDGER[:LEDGER.index('[2026-08-05 02:30:32] SSGL')]) \
        == BIG_PICTURE == 4


def test_both_directions_are_understood():
    assert from_ledger('[x] SSGL: UI mode (7->4)\n') == 4
    assert from_ledger('[x] SSGL: UI mode (4->7)\n') == 7


def test_a_ledger_with_no_transitions_says_nothing():
    """A fresh log, or one that predates any mode switch, is not an answer -
    the argv fallback exists for exactly this."""
    assert from_ledger('[x] AppID 367520 adding PID 1 as a tracked process\n') is None
    assert from_ledger('') is None


def test_unrelated_lines_never_confuse_it():
    assert from_ledger('[x] SSGL: change [367520] LCT 909457200->0\n') is None


# ----------------------------------------------------------------- the argv
def test_the_webhelper_argv_carries_the_start_mode():
    assert from_argv(ARGV) == DESKTOP == 7


def test_an_empty_uimode_flag_is_not_an_answer():
    """A bare '-uimode=' with no number appears on other processes' argv; it
    must not read as mode 0 or crash the parse."""
    assert from_argv('./something -uimode= -other') is None


def test_a_missing_argv_says_nothing():
    assert from_argv('') is None
    assert from_argv(None) is None
    assert from_argv('./steamwebhelper -nocrashdialog -lang=en_US') is None


def test_big_picture_in_the_argv_is_read_too():
    assert from_argv('./steamwebhelper -uimode=4 -startcount=0') == BIG_PICTURE


# ------------------------------------------------- the "already in BP" branch
def test_already_in_big_picture_needs_no_action():
    """The branch game-launch's ensure_big_picture short-circuits on. Without
    it, every tile press would re-open Big Picture and flap the UI."""
    assert from_ledger('[x] SSGL: UI mode (7->4)\n') == BIG_PICTURE
    # ...and the ledger outranks a stale argv, which is the whole point: the
    # argv still says 7 while Big Picture is open, because steamwebhelper is
    # not restarted for a mode switch.
    assert from_argv(ARGV) == DESKTOP
    assert from_ledger('[x] SSGL: UI mode (7->4)\n') != from_argv(ARGV)


def test_the_mode_names_are_config_not_magic():
    """Spelled once, in one dict, so a Steam renumbering is one edit."""
    assert uimode.MODES[BIG_PICTURE] == 'big-picture'
    assert uimode.MODES[DESKTOP] == 'desktop'


def test_ledger_paths_dedupes_the_symlinked_steam_roots():
    paths = uimode.ledger_paths()
    assert len(paths) == len(set(paths))
