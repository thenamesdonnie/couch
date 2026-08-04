#!/usr/bin/env python3
"""Unit tests for the shared PS-button arithmetic (gesture.py).

Everything here is synthetic kernel timestamps into pure functions and one
PressTracker - no device, no clock, no files. The point of the module is that
stage 1 (couchd's shadow model), stage 2 (inputproc's grabbing fast path) and
the live watcher all answer "tap, double-tap or hold?" the same way, so the
timings are pinned here rather than in three places.

    .venv/bin/python -m pytest test_gesture.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import gesture
from gesture import (DOUBLE_TAP, DOUBLE_TAP_S, DOWN, HOLD, HOLD_RELEASE,
                     HOLD_SECONDS, TAP, PressTracker)

TAP_LEN = 0.08          # a comfortable tap, well under the hold threshold
K0 = 5000.0             # an arbitrary kernel epoch


# The synthetic wall clock is kept equal to the synthetic kernel clock: only
# poll()'s extrapolation reads it, and a real wall clock there would make the
# hold arithmetic depend on how fast the test ran.
def tap(tr, k, length=TAP_LEN):
    """Press and release at kernel times k .. k+length. Returns the release
    outcome; the release is what decides tap vs double vs hold."""
    tr.feed(k, 1, wall=k)
    return tr.feed(k + length, 0, wall=k + length)


def hold(tr, k, length=HOLD_SECONDS + 0.3):
    """A press that crosses the hold threshold, polled the way an owner of
    the pad polls it (stage 2) so hold_fired latches mid-press."""
    tr.feed(k, 1, wall=k)
    outcome = tr.poll(wall=k + HOLD_SECONDS + 1e-6)
    return outcome, tr.feed(k + length, 0, wall=k + length)


# =========================================================================
# the pure predicates
# =========================================================================
def test_within_double_tap_is_strictly_under_the_window():
    assert gesture.within_double_tap(0.0)
    assert gesture.within_double_tap(DOUBLE_TAP_S - 1e-6)
    assert not gesture.within_double_tap(DOUBLE_TAP_S)
    assert not gesture.within_double_tap(DOUBLE_TAP_S + 1e-6)
    assert not gesture.within_double_tap(None), 'no previous tap is not a gap'


def test_is_double_tap_needs_both_halves():
    assert gesture.is_double_tap(0.2, TAP_LEN)
    assert not gesture.is_double_tap(0.5, TAP_LEN), 'gap too long'
    assert not gesture.is_double_tap(0.2, HOLD_SECONDS), 'second press is a hold'
    assert not gesture.is_double_tap(None, TAP_LEN), 'nothing to double'


def test_double_tap_window_over_is_the_complement():
    assert not gesture.double_tap_window_over(0.0)
    assert not gesture.double_tap_window_over(DOUBLE_TAP_S)
    assert gesture.double_tap_window_over(DOUBLE_TAP_S + 1e-6)


def test_the_hold_threshold_is_untouched_by_any_of_it():
    assert HOLD_SECONDS == 0.9
    assert gesture.is_tap(0.899)
    assert not gesture.is_tap(0.9)


# =========================================================================
# the tracker: the five cases the switcher gesture has to get right
# =========================================================================
def test_clean_double_tap():
    tr = PressTracker()
    assert tap(tr, K0) == TAP
    assert tr.double_armed is False
    assert tap(tr, K0 + TAP_LEN + 0.15) == DOUBLE_TAP
    assert tr.double_armed is True, 'the reason survives the release (R4 readers)'
    assert tr.presses == 2 and tr.doubles == 1


def test_tap_then_nothing_stays_a_single_tap():
    tr = PressTracker()
    assert tap(tr, K0) == TAP
    assert tr.doubles == 0
    # still inside the window: a reader must not call it final yet
    assert tr.double_pending(wall=K0 + TAP_LEN + 0.2)
    # ... and after it, it is
    assert not tr.double_pending(wall=K0 + TAP_LEN + DOUBLE_TAP_S + 0.01)


def test_tap_then_hold_is_a_hold_and_never_a_double():
    """The switcher must never steal the suspend gesture."""
    tr = PressTracker()
    assert tap(tr, K0) == TAP
    k1 = K0 + TAP_LEN + 0.1                       # well inside the window
    assert tr.feed(k1, 1, wall=k1) == DOWN
    assert tr.double_armed is True, 'armed, and about to lose to the hold'
    assert tr.poll(wall=k1 + HOLD_SECONDS + 1e-6) == HOLD
    assert tr.feed(k1 + 1.2, 0, wall=k1 + 1.2) == HOLD_RELEASE
    assert tr.doubles == 0
    # and the hold disarmed the window: the next quick tap is a first tap
    assert tap(tr, K0 + 3.0) == TAP


def test_hold_then_quick_tap_is_not_a_double_either():
    """A hold never arms the window, so the tap that follows it is a single."""
    tr = PressTracker()
    assert hold(tr, K0) == (HOLD, HOLD_RELEASE)
    assert tap(tr, K0 + 1.3) == TAP
    assert tr.doubles == 0


@pytest.mark.parametrize('gap,expect', [
    (0.30, DOUBLE_TAP),                 # comfortably inside
    (DOUBLE_TAP_S - 1e-6, DOUBLE_TAP),  # the last microsecond that counts
    (DOUBLE_TAP_S, TAP),                # the boundary itself is OUT (< not <=)
    (0.40, TAP),                        # comfortably outside
])
def test_boundary_gaps(gap, expect):
    """The gap is release -> next press, in kernel time."""
    tr = PressTracker()
    assert tap(tr, K0) == TAP
    assert tap(tr, K0 + TAP_LEN + gap) == expect


# +1e-6 rather than exactly 0.9: a release timestamp differenced out of two
# kernel timestamps near 5000 lands a fraction BELOW 0.9 in binary floating
# point, and the comparison is >=, exactly as in the watcher.
OVER_HOLD = HOLD_SECONDS + 1e-6


@pytest.mark.parametrize('first,second,expect', [
    (0.899, 0.08, DOUBLE_TAP),          # both taps, the first only just
    (OVER_HOLD, 0.08, TAP),             # first press was a hold: nothing armed
    (0.08, 0.899, DOUBLE_TAP),          # second tap only just under
    (0.08, OVER_HOLD, HOLD_RELEASE),    # second press crossed: the hold wins
])
def test_taps_straddling_the_hold_boundary(first, second, expect):
    tr = PressTracker()
    tap(tr, K0, first)
    assert tap(tr, K0 + first + 0.1, second) == expect


def test_three_taps_are_one_double_plus_one_single():
    tr = PressTracker()
    assert tap(tr, K0) == TAP
    assert tap(tr, K0 + 0.2) == DOUBLE_TAP
    assert tap(tr, K0 + 0.4) == TAP, 'the window closed when it was used'
    assert tap(tr, K0 + 0.6) == DOUBLE_TAP
    assert tr.doubles == 2


def test_four_fast_taps_never_produce_overlapping_doubles():
    tr = PressTracker()
    outcomes = [tap(tr, K0 + i * 0.2) for i in range(4)]
    assert outcomes == [TAP, DOUBLE_TAP, TAP, DOUBLE_TAP]


def test_reset_forgets_the_window():
    """Pad lost mid-gesture: the tap before the disconnect must not pair with
    the first tap after it, however quickly the pad comes back."""
    tr = PressTracker()
    tap(tr, K0)
    tr.reset()
    assert tr.double_armed is False
    assert tap(tr, K0 + 0.2) == TAP


def test_the_kernel_clock_is_what_the_window_is_measured_in():
    """Wall time can drift or stall relative to the pad's own timestamps;
    only the kernel numbers decide (R4)."""
    tr = PressTracker()
    tap(tr, K0)
    # a wall clock a full minute ahead changes nothing about the decision
    tr.feed(K0 + TAP_LEN + 0.2, 1, wall=K0 + 60)
    assert tr.double_armed is True
    assert tr.feed(K0 + TAP_LEN + 0.28, 0, wall=K0 + 60.1) == DOUBLE_TAP


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
