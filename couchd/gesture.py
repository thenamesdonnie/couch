#!/usr/bin/env python3
"""The PS-button gesture arithmetic, in ONE place (stage-2 design, SR4).

Stage 1 (couchd.py, shadow) and stage 2 (inputproc.py, the grabbing fast
path) must decide "tap" versus "hold" IDENTICALLY, or the shadow corpus
stops being comparable to what the owning process actually did. SR4 makes
that a shared module rather than a copied constant: couchd.py imports the
thresholds AND the tracker below, and so does inputproc.py.

Two rules carried over from stage 1 and preserved exactly:

  * R4 - every duration is measured between KERNEL event timestamps, never
    wall or monotonic time. The one deliberate exception is the handoff
    timeout, which exists precisely BECAUSE no further kernel events are
    coming (a dead pad mid-hold), so it is a monotonic deadline and is
    named as such.
  * the kernel clock is EXTRAPOLATED over the gap since the last event
    (kernel_now): a button held with no further reports must still fire.

Nothing here touches a device, a file or the clock except time.time() for
that extrapolation; it is all pure enough to test with synthetic numbers.
"""
import struct
import time

# -- thresholds (pad-home-watcher's, unchanged) ----------------------------
HOLD_SECONDS = 0.9        # PS held this long = "hold" (suspend/handoff)
HANDOFF_TIMEOUT = 4.0     # release never came: hand over anyway (monotonic)

# A THIRD tier above the hold, for a gesture that has to be hard to do by
# accident (quit the game, TV off). It is opt-in in both senses:
#
#   * the tracker only watches for it when it is given a long_hold_seconds -
#     PressTracker(..., long_hold_seconds=None), the default, behaves exactly
#     as it did before this tier existed and poll() can never return
#     LONG_HOLD, so couchd and inputproc are untouched until asked;
#   * the POLICY (gestureconf.suppress) is that a long hold only fires when
#     `hold` is bound to nothing. A press cannot be both a 0.9s hold and a
#     3.0s long hold: the hold fires at 0.9 exactly as today and the press is
#     spent from then on. Binding both is a mistake, not a chord, so the long
#     hold is dropped with a warning rather than double-firing.
#
# The tracker itself is honest about both: if a caller does hand it a
# long_hold_seconds AND lets the hold fire, poll() returns HOLD once and then
# LONG_HOLD once. Deciding that the second one is unwanted is the config's
# job, not the arithmetic's.
LONG_HOLD_S = 3.0

# Two taps this close together are ONE gesture (the on-TV switcher). Measured
# release-to-next-press, not press-to-press, so a slow second tap can still
# arrive inside the window. 0.35s sits above the ~0.25s a comfortable
# double-tap takes and below the ~0.5s at which two separate presses start to
# read as separate intents; the hold threshold is untouched by it, and a
# tap-then-HOLD is always a hold (see is_double_tap).
DOUBLE_TAP_S = 0.35

# A heavy transition - a suspend, a resume, the on-TV switcher - takes the
# screen, the pad routing and up to 18 processes with it, and it is not
# instantaneous. Presses that land while it is still happening are not new
# intents; they are the tail of the burst that asked for it.
#
# Before this window existed, a spammed PS button composed whole gestures out
# of that tail. Live, 4 Aug 2026, in 0.6 seconds:
#   02:21:51.717  double-tap -> switcher (freezes the game)
#   02:21:51.888  tap        -> resume   (thaws it again)
#   02:21:52.168  double-tap -> switcher (freezes it again)
# The room saw Kodi, the switcher and the game flicker past. Pre-double-tap the
# same spam only flapped Steam's menu, so this is a regression the feature
# brought with it, not a pre-existing sharp edge.
#
# 1.2s: above the ~0.9s a suspend needs to freeze the tree, hand over the pad
# and raise Kodi, and below the ~1.5s at which a deliberate second gesture
# starts to feel refused.
SETTLE_S = 1.2


def settle_swallows(now, settle_until):
    """Is `now` inside a settle window? The rule every caller shares.

    A press inside the window is swallowed WHOLE. Two consequences that matter
    more than the drop itself:

      * it must also clear whatever half-formed tap sequence it would have
        seeded, or the tail of a burst composes a fresh double-tap out of the
        last two presses exactly as the window expires - which is the bug,
        arriving 1.2s later;
      * a hold that STARTS inside the window is swallowed too. It is part of
        the same burst, and a burst that happens to hold the button down on its
        last press did not mean something different by it. (A hold already in
        progress when the window opens is untouched: its release still has to
        run, or a pad handed halfway over is stranded.)
    """
    return settle_until is not None and now < settle_until

# InputPlumber's write_chord_events spacing, ported as earned knowledge:
# a synthesised press/release pair sent back-to-back is dropped or coalesced
# by consumers, 80ms apart is seen by everything, release order reversed.
CHORD_GAP = 0.080

# -- struct input_event, x86_64 -------------------------------------------
EVENT_FORMAT = 'llHHi'
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03
EV_MSC = 0x04
EV_FF = 0x15
SYN_REPORT = 0

BTN_MODE = 0x13c          # the PS button


# =========================================================================
# pure predicates - the guards couchd.py and inputproc.py share
# =========================================================================
def kernel_now(last_k, last_k_wall, wall=None):
    """The kernel timebase, extrapolated over the gap since the last event.

    `last_k` is the timestamp of the last event we read (kernel clock),
    `last_k_wall` the wall clock when we read it. Before any event has been
    seen there is no anchor, so wall time is the honest answer.
    """
    now = time.time() if wall is None else wall
    if not last_k:
        return now
    return last_k + (now - last_k_wall)


def hold_reached(button_down, down_since_k, k_now, threshold=HOLD_SECONDS):
    """0.9s measured between KERNEL timestamps (R4)."""
    return bool(button_down and down_since_k is not None
                and (k_now - down_since_k) >= threshold)


def long_hold_reached(button_down, down_since_k, k_now, threshold=LONG_HOLD_S):
    """The third tier: the same arithmetic as hold_reached, further out.

    Kept as its own predicate rather than a second call with an argument so
    the two thresholds read as two decisions in the callers, and so a test can
    pin "0.9 is a hold, 3.0 is a long hold" against named functions.
    """
    return bool(button_down and down_since_k is not None
                and (k_now - down_since_k) >= threshold)


def is_tap(press_duration, threshold=HOLD_SECONDS):
    """A completed press shorter than the hold threshold."""
    return press_duration is not None and press_duration < threshold


def within_double_tap(gap, window=DOUBLE_TAP_S):
    """Release-to-next-press gap short enough for the two to be one gesture.

    `gap` is None before any tap has been completed, which is not a double.
    """
    return gap is not None and gap < window


def is_double_tap(gap, second_duration, window=DOUBLE_TAP_S, hold=HOLD_SECONDS):
    """The whole double-tap rule in one predicate.

    A second press counts only if it arrived inside the window AND is itself
    a tap: a tap followed by a HOLD is a hold (the suspend), never a double.
    The first press being a tap is the caller's business - the tracker below
    only arms the window on a completed TAP, so a hold never arms one.
    """
    return within_double_tap(gap, window) and is_tap(second_duration, hold)


def paused_tap_decision(deferred, gap, second_duration, double_tap_bound,
                        window=DOUBLE_TAP_S, hold=HOLD_SECONDS):
    """What a tap should do while a game is PAUSED. Returns one of:

      'double_tap'  the second half landed inside the window - open the
                    switcher, which is what a double-tap means everywhere else
      'defer'       wait out the window; a second tap may still be coming
      'resume'      act now, exactly as a paused tap always has

    A tap on a paused game jumps back into it (the recovery path, above the
    binding dispatch - see pad-home-watcher.resume_game). That made the first
    tap unconditional, so a double-tap on a paused game could only ever resume.
    Donnie's call, 5 Aug 2026, overriding the earlier ruling: a double-tap on a
    paused game should open the switcher, because that is exactly when the
    switcher is most useful - you are already on Kodi wondering what else is
    running.

    The cost is one double-tap window of latency, and it is charged ONLY here:
    with the double-tap unbound there is nothing to wait for and the resume is
    instant again, and an unpaused tap never reaches this function at all.
    """
    if not double_tap_bound:
        return 'resume'      # nothing to wait for, and nothing to escalate to
    if deferred and is_double_tap(gap, second_duration, window, hold):
        return 'double_tap'
    return 'defer'


def double_tap_window_over(since_tap, window=DOUBLE_TAP_S):
    """No second press came: the single tap is final.

    Like handoff_overdue this is a deadline rather than an event, so callers
    feed it elapsed time in whatever clock they own; the tracker's own arming
    stays on kernel timestamps (R4).
    """
    return since_tap > window


def handoff_overdue(since_gesture, timeout=HANDOFF_TIMEOUT):
    """The release never arrived (pad died mid-hold, or the button is stuck).

    MONOTONIC, not kernel: no more kernel events are coming, which is the
    whole reason this deadline exists.
    """
    return since_gesture > timeout


def gesture_stale(button_down, since_gesture, timeout=HANDOFF_TIMEOUT):
    """Nothing pending and the button is up: fall back to idle."""
    return (not button_down) and since_gesture > timeout * 2


def chord_schedule(gap=CHORD_GAP):
    """The (offset, value) pairs for re-injecting one synthetic tap.

    Returned rather than slept through so the caller owns its own clock and
    the shape is testable. Press at 0, release at `gap`.
    """
    return ((0.0, 1), (gap, 0))


# =========================================================================
# the tracker - one press's worth of state, driven by kernel timestamps
# =========================================================================
#: feed() outcomes
DOWN = 'down'
TAP = 'tap'
DOUBLE_TAP = 'double-tap'
HOLD_RELEASE = 'hold-release'
#: poll() outcomes
HOLD = 'hold'
LONG_HOLD = 'long-hold'   # only ever returned when long_hold_seconds is set


class PressTracker:
    """BTN_MODE press bookkeeping on kernel timestamps.

    couchd's PadObserver uses it to fill Observed (button_down, down_since_k,
    press_duration, ...) for the pure transition table; inputproc uses the
    same instance to decide, live, whether a press it is WITHHOLDING from the
    virtual pad turned out to be a tap (re-inject it) or a hold (keep it).

    The two consumers differ only in whether they call poll(): stage 1 never
    needs the moment the threshold is crossed, stage 2 does.
    """

    def __init__(self, hold_seconds=HOLD_SECONDS, double_tap_s=DOUBLE_TAP_S,
                 long_hold_seconds=None):
        self.hold_seconds = hold_seconds
        self.double_tap_s = double_tap_s
        # None = the tier is off, which is the default: an existing caller
        # (couchd's PadObserver, inputproc) can never be handed a LONG_HOLD it
        # does not know what to do with.
        self.long_hold_seconds = long_hold_seconds
        self.long_hold_fired = False    # poll() already announced this one
        self.button_down = False
        self.down_since_k = None
        self.press_duration = None      # last COMPLETED press, seconds
        self.press_ended_at = None      # monotonic when that press ended
        self.presses = 0                # cross-checked against Steam's log
        self.doubles = 0                # completed double-taps
        self.hold_fired = False         # poll() already announced this hold
        self.last_k = 0.0               # last kernel timestamp seen
        self.last_k_wall = 0.0          # wall clock when we saw it
        # double-tap bookkeeping, kernel clock throughout (R4). A hold never
        # arms the window, so tap-then-hold can only ever be a hold.
        self.last_tap_ended_k = None    # kernel ts of the last completed TAP
        self.double_armed = False       # this press began inside that window

    # -- clock ------------------------------------------------------------
    def note_event(self, k, wall=None):
        """Advance the kernel clock anchor. EVERY event does this, not just
        BTN_MODE ones: a stick wiggle is a perfectly good clock tick."""
        self.last_k = k
        self.last_k_wall = time.time() if wall is None else wall

    def kernel_now(self, wall=None):
        return kernel_now(self.last_k, self.last_k_wall, wall)

    # -- decisions --------------------------------------------------------
    def feed(self, k, value, mono=None, wall=None):
        """One BTN_MODE event. Returns DOWN / TAP / DOUBLE_TAP /
        HOLD_RELEASE / None.

        `value` 2 is autorepeat and is deliberately ignored (the kernel does
        not repeat BTN_*, but a synthetic stream might).

        DOUBLE_TAP is a TAP that closed a window opened by the previous tap;
        callers that only care about "was this press withheld from the pad"
        must treat it exactly as TAP. `double_armed` stays set through the
        release so a level-based reader (couchd's Observed) can see WHY the
        press it is looking at was a double.
        """
        self.note_event(k, wall)
        if value == 1:
            self.button_down = True
            self.down_since_k = k
            self.hold_fired = False
            self.long_hold_fired = False
            self.presses += 1
            gap = (None if self.last_tap_ended_k is None
                   else k - self.last_tap_ended_k)
            self.double_armed = within_double_tap(gap, self.double_tap_s)
            return DOWN
        if value == 0:
            if self.down_since_k is not None:
                self.press_duration = k - self.down_since_k
                self.press_ended_at = (time.monotonic() if mono is None
                                       else mono)
            was_hold = self.hold_fired or self.long_hold_fired
            self.button_down = False
            self.down_since_k = None
            self.hold_fired = False
            self.long_hold_fired = False
            if was_hold or not is_tap(self.press_duration, self.hold_seconds):
                # tap-then-hold: the hold wins, and it disarms the window too.
                self.last_tap_ended_k = None
                self.double_armed = False
                return HOLD_RELEASE
            if self.double_armed:
                # Three taps are one double plus one single, never two
                # overlapping doubles: the window closes when it is used.
                self.last_tap_ended_k = None
                self.doubles += 1
                return DOUBLE_TAP
            self.last_tap_ended_k = k
            return TAP
        return None

    def double_pending(self, wall=None):
        """A completed single tap whose window has not run out yet.

        The window is measured in the kernel clock, extrapolated the same way
        hold detection is, so a tap followed by silence still expires.
        """
        if self.button_down or self.last_tap_ended_k is None:
            return False
        return not double_tap_window_over(
            self.kernel_now(wall) - self.last_tap_ended_k, self.double_tap_s)

    def poll(self, wall=None):
        """Called on every loop iteration by the owner of the pad. Returns
        HOLD exactly once per press, the moment the kernel clock crosses the
        threshold - including when no further events arrive at all.

        With long_hold_seconds set it also returns LONG_HOLD exactly once, at
        the further threshold. Both can fire in one press (HOLD first, then
        LONG_HOLD); which of them the console ACTS on is gestureconf's
        precedence rule, not this function's - see LONG_HOLD_S above.
        """
        if not self.button_down:
            return None
        k = self.kernel_now(wall)
        if not self.hold_fired and hold_reached(
                self.button_down, self.down_since_k, k, self.hold_seconds):
            self.hold_fired = True
            return HOLD
        if (self.long_hold_seconds is not None and not self.long_hold_fired
                and long_hold_reached(self.button_down, self.down_since_k, k,
                                      self.long_hold_seconds)):
            self.long_hold_fired = True
            return LONG_HOLD
        return None

    def held_for(self, wall=None):
        """Seconds the current press has lasted, or None if nothing is down."""
        if not self.button_down or self.down_since_k is None:
            return None
        return self.kernel_now(wall) - self.down_since_k

    def reset(self):
        """Device lost / ownership changed: forget the in-flight press but
        keep the counters, which are cross-check evidence (R5)."""
        self.button_down = False
        self.down_since_k = None
        self.hold_fired = False
        self.long_hold_fired = False
        self.last_tap_ended_k = None
        self.double_armed = False
