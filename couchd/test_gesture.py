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
                     HOLD_SECONDS, LONG_HOLD, LONG_HOLD_S, SETTLE_S, TAP,
                     PressTracker, paused_tap_decision, settle_swallows)

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


def test_reset_forgets_the_completed_press_too():
    """Pad dropped just after a tap: a level-based reader (couchd's Observed)
    must not see 'button up, press_duration = tap' off a press that reset()
    already disowned - that is the phantom-resume path a BT drop used to
    open (adversarial review, 5 Aug 2026)."""
    tr = PressTracker()
    tap(tr, K0)
    tr.reset()
    assert tr.press_duration is None
    assert tr.press_ended_at is None
    assert tr.double_pending(wall=K0 + 0.1) is False


def test_orphan_release_decides_nothing_and_arms_nothing():
    """The button was down when the device dropped; the release arrives on
    the NEW fd after reset(). There is no press to classify: grading it with
    the previous press's duration used to return TAP and arm the double-tap
    window, so ONE real tap later fired the switcher."""
    tr = PressTracker()
    tap(tr, K0)                       # a real tap, then the drop mid-press
    tr.feed(K0 + 0.5, 1)
    tr.reset()
    assert tr.feed(K0 + 0.9, 0) is None       # orphan release: no decision
    assert tr.double_armed is False
    assert tr.last_tap_ended_k is None
    assert tr.press_duration is None
    assert tap(tr, K0 + 1.0) == TAP           # next real tap is a SINGLE
    assert tr.doubles == 0


def test_hold_release_marker_for_level_readers():
    """feed() holds its HOLD_RELEASE decision (hold_release_k) for a
    level-based reader whose sampled state machine missed both edges - the
    hold twin of double_armed. Consumed explicitly, superseded by any new
    press, never set by a tap."""
    tr = PressTracker()
    tr.feed(K0, 1)
    assert tr.feed(K0 + 1.5, 0) == HOLD_RELEASE
    assert tr.hold_release_k == K0 + 1.5
    tr.consume_hold_release()
    assert tr.hold_release_k is None
    tr.feed(K0 + 3.0, 1)
    tr.feed(K0 + 4.5, 0)
    assert tr.hold_release_k == K0 + 4.5
    tr.feed(K0 + 6.0, 1)                  # new press supersedes the marker
    assert tr.hold_release_k is None
    tr.feed(K0 + 6.0 + TAP_LEN, 0)        # a tap never sets it
    assert tr.hold_release_k is None


def test_release_with_no_press_ever_seen_is_ignored():
    """The daemon can start mid-press: the first BTN_MODE event it sees is a
    release. Nothing to classify, nothing armed."""
    tr = PressTracker()
    assert tr.feed(K0, 0) is None
    assert tr.press_duration is None
    assert tr.double_armed is False


def test_the_kernel_clock_is_what_the_window_is_measured_in():
    """Wall time can drift or stall relative to the pad's own timestamps;
    only the kernel numbers decide (R4)."""
    tr = PressTracker()
    tap(tr, K0)
    # a wall clock a full minute ahead changes nothing about the decision
    tr.feed(K0 + TAP_LEN + 0.2, 1, wall=K0 + 60)
    assert tr.double_armed is True
    assert tr.feed(K0 + TAP_LEN + 0.28, 0, wall=K0 + 60.1) == DOUBLE_TAP


# =========================================================================
# the long-hold tier
#
# The semantics, decided here and documented in gesture.py and in the
# settings page's own help text: the HOLD fires at 0.9s exactly as it always
# has, and a long hold is only reachable with the hold bound to Nothing. One
# press cannot be both, and dropping the shadowed binding with a warning
# beats double-firing (gestureconf.suppress owns that rule; the tracker below
# is honest about the arithmetic either way).
# =========================================================================
def test_the_tier_is_off_unless_asked_for():
    """Every existing caller - couchd's PadObserver, inputproc - constructs a
    tracker without it and must never be handed a LONG_HOLD it cannot read."""
    tr = PressTracker()
    assert tr.long_hold_seconds is None
    tr.feed(K0, 1, wall=K0)
    assert tr.poll(wall=K0 + HOLD_SECONDS + 1e-6) == HOLD
    for extra in (LONG_HOLD_S, LONG_HOLD_S + 5, LONG_HOLD_S + 60):
        assert tr.poll(wall=K0 + extra) is None, 'no third tier was asked for'


def test_the_default_long_threshold():
    assert LONG_HOLD_S == 3.0
    assert gesture.long_hold_reached(True, K0, K0 + 2.999) is False
    assert gesture.long_hold_reached(True, K0, K0 + LONG_HOLD_S) is True
    assert gesture.long_hold_reached(False, K0, K0 + 99) is False
    assert gesture.long_hold_reached(True, None, K0 + 99) is False


def test_hold_fires_at_09_and_the_long_hold_at_30_each_once():
    tr = PressTracker(long_hold_seconds=LONG_HOLD_S)
    tr.feed(K0, 1, wall=K0)
    assert tr.poll(wall=K0 + 0.5) is None
    assert tr.poll(wall=K0 + HOLD_SECONDS + 1e-6) == HOLD
    assert tr.poll(wall=K0 + 1.5) is None, 'the hold does not repeat'
    assert tr.poll(wall=K0 + LONG_HOLD_S + 1e-6) == LONG_HOLD
    assert tr.poll(wall=K0 + 6.0) is None, 'nor does the long hold'
    assert tr.feed(K0 + 6.0, 0, wall=K0 + 6.0) == HOLD_RELEASE


def test_a_long_hold_release_is_never_a_tap_or_half_a_double():
    """Even if the caller never polled the 0.9s threshold, a press that only
    crossed the long one still ends as a hold, not a tap."""
    tr = PressTracker(long_hold_seconds=LONG_HOLD_S)
    tr.feed(K0, 1, wall=K0)
    assert tr.poll(wall=K0 + LONG_HOLD_S + 1e-6) == HOLD, 'hold comes first'
    assert tr.poll(wall=K0 + LONG_HOLD_S + 2e-6) == LONG_HOLD
    assert tr.feed(K0 + 4.0, 0, wall=K0 + 4.0) == HOLD_RELEASE
    assert tap(tr, K0 + 4.2) == TAP, 'the window was never armed'
    assert tr.doubles == 0


def test_the_next_press_starts_the_tiers_over():
    tr = PressTracker(long_hold_seconds=LONG_HOLD_S)
    tr.feed(K0, 1, wall=K0)
    tr.poll(wall=K0 + HOLD_SECONDS + 1e-6)
    tr.poll(wall=K0 + LONG_HOLD_S + 1e-6)
    tr.feed(K0 + 4.0, 0, wall=K0 + 4.0)
    assert (tr.hold_fired, tr.long_hold_fired) == (False, False)
    k1 = K0 + 5.0
    tr.feed(k1, 1, wall=k1)
    assert tr.poll(wall=k1 + HOLD_SECONDS + 1e-6) == HOLD
    assert tr.poll(wall=k1 + LONG_HOLD_S + 1e-6) == LONG_HOLD


def test_reset_forgets_a_long_hold_in_flight():
    tr = PressTracker(long_hold_seconds=LONG_HOLD_S)
    tr.feed(K0, 1, wall=K0)
    tr.poll(wall=K0 + LONG_HOLD_S + 1e-6)
    tr.reset()
    assert tr.long_hold_fired is False and tr.hold_fired is False


def test_a_custom_long_threshold_is_honoured():
    tr = PressTracker(long_hold_seconds=1.5)
    tr.feed(K0, 1, wall=K0)
    assert tr.poll(wall=K0 + HOLD_SECONDS + 1e-6) == HOLD
    assert tr.poll(wall=K0 + 1.4) is None
    assert tr.poll(wall=K0 + 1.5) == LONG_HOLD


def test_the_long_hold_is_extrapolated_like_the_hold_is():
    """A button held with no further kernel reports must still cross both
    thresholds - the whole reason kernel_now extrapolates (R4)."""
    tr = PressTracker(long_hold_seconds=LONG_HOLD_S)
    tr.feed(K0, 1, wall=K0)          # the only event this press will produce
    assert tr.poll(wall=K0 + 5.0) == HOLD
    assert tr.poll(wall=K0 + 5.0) == LONG_HOLD


# ------------------------------------------------------- the settle window
# A faithful mirror of pad-home-watcher.watch()'s press/release branch order,
# small enough to read: press swallowed inside a settle window (and seeding
# nothing), otherwise the ordinary tap / double-tap / hold arithmetic, with a
# heavy transition arming a new window. The watcher itself is a 1000-line
# select loop over evdev and cannot be imported; keeping the ORDER honest here
# is what makes these tests mean something.
HEAVY = {'suspend', 'switcher', 'resume'}


def _run(presses, double_tap_bound=True, hold_bound=True):
    """presses = [(down_at, up_at), ...] in monotonic seconds.

    Returns (dispatched gestures, settle-suppressed press count)."""
    fired, suppressed = [], 0
    settle_until, last_tap_at, swallowed = None, None, False

    def dispatch(g):
        fired.append(g)
        if g in ('suspend', 'switcher', 'resume'):
            nonlocal settle_until
            settle_until = fired_at[0] + SETTLE_S

    fired_at = [0.0]
    for down, up in presses:
        fired_at[0] = up
        if settle_swallows(down, settle_until):
            suppressed += 1
            swallowed, last_tap_at = True, None   # seeds nothing
            continue
        swallowed = False
        if hold_bound and up - down >= HOLD_SECONDS:      # the hold path
            last_tap_at = None
            dispatch('suspend')
            continue
        gap = None if last_tap_at is None else down - last_tap_at
        if double_tap_bound and gesture.is_double_tap(gap, up - down):
            last_tap_at = None
            dispatch('switcher')
        else:
            last_tap_at = up
    assert swallowed in (True, False)
    return fired, suppressed


def test_a_spam_burst_dispatches_one_gesture():
    """The 4 Aug 2026 regression: five taps in 0.6s became
    switcher -> resume -> switcher and the TV flickered through all three."""
    burst = [(t, t + TAP_LEN) for t in (0.00, 0.20, 0.40, 0.60, 0.80)]
    fired, suppressed = _run(burst)
    assert fired == ['switcher'], fired      # the FIRST double-tap, and no more
    assert suppressed == 3


def test_a_press_inside_the_window_seeds_no_new_gesture():
    """The subtle half: a swallowed press must also clear the half-formed tap
    sequence, or the tail of a burst composes a fresh double-tap the moment the
    window expires - the same bug, arriving 1.2s late."""
    # tap, tap (=switcher, window opens at 0.28), then a press inside the
    # window, then a tap just after it expires. The pair either side of the
    # boundary must NOT read as a double-tap.
    fired, suppressed = _run([(0.00, 0.08), (0.20, 0.28),
                              (1.30, 1.38),          # swallowed (< 1.48)
                              (1.50, 1.58)])         # window over, lone tap
    assert fired == ['switcher'] and suppressed == 1


def test_a_hold_starting_inside_the_window_is_suppressed():
    """Documented choice: it is part of the same burst. A burst that happens to
    hold the button on its last press did not mean something different by it."""
    fired, suppressed = _run([(0.00, 0.08), (0.20, 0.28),   # -> switcher
                              (0.40, 0.40 + HOLD_SECONDS + 0.1)])
    assert fired == ['switcher'] and suppressed == 1


def test_a_deliberate_second_gesture_still_lands_after_the_window():
    """The window refuses a burst, not the user. Past SETTLE_S it is over."""
    fired, _ = _run([(0.00, 0.08), (0.20, 0.28),            # -> switcher
                     (2.00, 2.08), (2.20, 2.28)])           # -> switcher again
    assert fired == ['switcher', 'switcher']


def test_settle_swallows_is_inclusive_of_neither_end():
    assert settle_swallows(1.0, None) is False       # no window at all
    assert settle_swallows(1.0, 1.2) is True
    assert settle_swallows(1.2, 1.2) is False        # the deadline itself is out


# ------------------------------------------ a tap on a PAUSED game (5 Aug 2026)
def test_paused_double_tap_opens_the_switcher():
    assert paused_tap_decision(True, 0.20, TAP_LEN, True) == 'double_tap'


def test_paused_first_tap_defers_while_the_double_tap_is_bound():
    assert paused_tap_decision(False, None, TAP_LEN, True) == 'defer'


def test_paused_tap_resumes_instantly_when_the_double_tap_is_unbound():
    """The latency is charged only where the ambiguity exists."""
    assert paused_tap_decision(False, None, TAP_LEN, False) == 'resume'
    assert paused_tap_decision(True, 0.20, TAP_LEN, False) == 'resume'


def test_a_slow_second_tap_on_a_paused_game_is_not_a_double():
    """Past the window it is two separate taps: the first already resumed."""
    assert paused_tap_decision(True, DOUBLE_TAP_S + 0.01, TAP_LEN, True) == 'defer'


def test_tap_then_hold_on_a_paused_game_is_never_a_double():
    """The same rule is_double_tap enforces everywhere: a tap-then-HOLD is a
    hold. It must not be answered with the switcher."""
    assert paused_tap_decision(True, 0.20, HOLD_SECONDS + 0.1, True) == 'defer'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
