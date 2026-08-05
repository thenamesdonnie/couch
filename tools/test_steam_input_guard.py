#!/usr/bin/env python3
"""Unit tests for ~/.local/bin/steam-input-guard's invariant-1 detection.

Pure: synthetic controller_ui.txt text and synthetic clock values into the two
functions that decide. No Steam, no X, no vpad, no files - importing the guard
module is safe because Xlib is only touched inside Screen.__init__, which
nothing here constructs.

The fixture lines are copied from the REAL log on this box, 5 Aug 2026 02:34,
including the desktop-mode routing (Desktop/413080) that made the original
'ClientUI' arm unfireable.

Run:  couchd/.venv/bin/pytest tools/test_steam_input_guard.py -q
"""
import importlib.machinery
import importlib.util
import os
import time

import pytest

HOME = os.path.expanduser('~')
_spec = importlib.util.spec_from_loader(
    'steam_input_guard', importlib.machinery.SourceFileLoader(
        'steam_input_guard', os.path.join(HOME, '.local/bin/steam-input-guard')))
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

guide_consumed_since = guard.guide_consumed_since
desktop_overlay_open = guard.desktop_overlay_open


@pytest.fixture(autouse=True)
def hermetic_latch(tmp_path, monkeypatch):
    """guide_consumed_since latches the handled stamp in a real file so two
    overlapping guard WINDOWS cannot answer the same press twice (the menu
    reopen dance, commit f2ac188). That file is live console state: these
    tests give every case its own, so the suite neither reads a stamp a real
    guard left behind nor leaves a fixture stamp for one to find."""
    monkeypatch.setattr(guard, 'GUIDE_LATCH', str(tmp_path / 'guide-handled'))


def ts(text):
    """Steam's stamp -> epoch, using the same local-time reading the guard does."""
    return time.mktime(time.strptime(text, '%Y-%m-%d %H:%M:%S'))


WINDOW_OPEN = ts('2026-08-05 02:34:35')

TAP = """\
[2026-08-05 02:34:36] Guide button sent to JS
[2026-08-05 02:34:36] OnFocusWindowChanged to window type: k_nGameIDControllerConfigs_Desktop, AppID 413080
[2026-08-05 02:34:37] OnFocusWindowChanged to game window type: AppID 367520, 367520
"""

HOLD = """\
[2026-08-05 02:34:36] Guide button skipped due to length
[2026-08-05 02:34:37] OnFocusWindowChanged to game window type: AppID 367520, 367520
"""

EARLIER_TAP = """\
[2026-08-05 02:34:20] Guide button sent to JS
[2026-08-05 02:34:21] OnFocusWindowChanged to game window type: AppID 367520, 367520
"""


# ------------------------------------------------------------- detection
def test_a_consumed_guide_press_is_detected():
    assert guide_consumed_since(WINDOW_OPEN, TAP) is True


def test_a_hold_is_never_detected():
    """Steam ignores a long press outright - it opens nothing, so there is
    nothing to close. This is why the hold path always looked clean."""
    assert guide_consumed_since(WINDOW_OPEN, HOLD) is False


def test_a_press_before_the_window_is_not_ours():
    assert guide_consumed_since(WINDOW_OPEN, EARLIER_TAP) is False


def test_a_press_in_the_same_second_as_the_window_counts():
    """Steam stamps whole seconds, so the press that opened the window and the
    window's own start land in the same second more often than not."""
    assert guide_consumed_since(ts('2026-08-05 02:34:36') + 0.9, TAP) is True


def test_the_desktop_routing_never_says_ClientUI():
    """The whole reason the original arm could not fire. Pinned so nobody
    'simplifies' the new arm away on the assumption ClientUI covers it."""
    assert 'ClientUI' not in TAP                  # nowhere in the log at all
    # route() reports the LAST routing line, which after a tap-resume is the
    # game window - so arm (a) sees neither ClientUI nor a Steam focus.
    assert guard.route(TAP).endswith('AppID 367520, 367520')
    assert 'ClientUI' not in guard.route(TAP)


def test_unstamped_and_garbage_lines_are_ignored():
    assert guide_consumed_since(WINDOW_OPEN, 'Guide button sent to JS\n') is False
    assert guide_consumed_since(WINDOW_OPEN, '') is False


# ------------------------------------------------------- the firing decision
ARMED = 0.0          # arm2_at already passed
NOW = 10.0


def test_it_fires_once_when_everything_lines_up():
    assert desktop_overlay_open(NOW, ARMED, False, True, 'steam_app_367520',
                                True) is True


def test_two_passes_in_one_window_toggle_exactly_once():
    """THE safety property. The guide button is a TOGGLE: a second press would
    reopen the menu the first one closed - and our own synthetic press is
    logged as another 'Guide button sent to JS', so a non-latching arm would
    flip the overlay on and off for the rest of the window."""
    fired = False
    toggles = 0
    for _ in range(6):                      # six passes of a six-second window
        if desktop_overlay_open(NOW, ARMED, fired, True, 'steam_app_367520',
                                True):
            fired = True                    # main() latches before pressing
            toggles += 1
    assert toggles == 1


def test_it_does_not_fire_while_steam_is_focused():
    """Steam focused means the player is deliberately in Steam's UI; closing it
    under them is the opposite of the repair."""
    assert desktop_overlay_open(NOW, ARMED, False, True, 'steamwebhelper',
                                True) is False


def test_it_does_not_fire_without_a_consumed_press():
    assert desktop_overlay_open(NOW, ARMED, False, True, 'steam_app_367520',
                                False) is False


def test_it_does_not_fire_without_a_game_session():
    assert desktop_overlay_open(NOW, ARMED, False, False, 'steam_app_367520',
                                True) is False


def test_it_holds_off_until_the_arm_deadline():
    """Steam's overlay appears ~0.3-1s after the press; checking sooner would
    spend the one shot on nothing."""
    assert desktop_overlay_open(1.0, 1.2, False, True, 'steam_app_367520',
                                True) is False
    assert desktop_overlay_open(1.2, 1.2, False, True, 'steam_app_367520',
                                True) is True


def test_an_empty_focus_class_still_fires():
    """A fullscreen game that owns no readable class must not be a loophole:
    the check is 'steam is not focused', not 'something is'."""
    assert desktop_overlay_open(NOW, ARMED, False, True, '', True) is True
    assert desktop_overlay_open(NOW, ARMED, False, True, None, True) is True
