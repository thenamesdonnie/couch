#!/usr/bin/env python3
"""Unit + property tests for couchd's pure model.

Everything here runs against reconcile() and the transition table only: no
sockets, no X, no /tmp, no daemon. The audit's failure modes are the
scenarios; the two pre-declared legacy bugs (R7) are tested as things couchd
must do RIGHT, not as behaviour to copy.

    .venv/bin/python -m pytest test_reconcile.py -q
"""
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

import couchd
import gesture
from gesture import DOUBLE_TAP_S
from gestureconf import ACTIONS, DEFAULT_BINDINGS
from couchd import (GUARDS, HOLD_SECONDS, REGIONS, REPAIR_COOLDOWN, TRANSITIONS,
                    UNKNOWN,
                    Machine, action_intents, check_invariants, make_obs,
                    reconcile, resolve_appid, want_pad_owner,
                    freeze_set_agreement)

APPID = '367520'
SESSION = {'launcher_pid': 111, 'mode': 'steam', 'appid': APPID,
           'raw': f'111 steam {APPID}'}
BP_SESSION = {'launcher_pid': 222, 'mode': 'bigpicture', 'appid': None,
              'raw': '222 bigpicture '}


def verbs(intents):
    return [(i.verb, i.subject) for i in intents]


def reasons(intents):
    return [i.reason for i in intents]


def find(intents, verb, subject=None):
    return [i for i in intents
            if i.verb == verb and (subject is None or i.subject == subject)]


class Rig:
    """Drives the real Machine + reconcile over a sequence of observations,
    exactly as the daemon's pass_once() does."""

    def __init__(self, **world):
        self.mono = 1000.0
        self.machine = Machine(on_transition=self._log)
        self.machine.since = {r: self.mono for r in REGIONS}
        self.recent = {}
        self.world = world
        self.transitions = []
        self.last = None

    def _log(self, region, frm, to, reason):
        self.transitions.append((region, frm, to, reason))

    def observe(self, dt=0.2, **kw):
        self.mono += dt
        w = dict(self.world)
        w.update(kw)
        w.setdefault('kernel_now', self.mono)
        o = make_obs(now=self.mono, mono=self.mono,
                     regions=dict(self.machine.regions),
                     region_since=dict(self.machine.since),
                     games=dict(self.machine.games),
                     recent=dict(self.recent), **w)
        self.machine.step(o)
        o = replace(o, regions=dict(self.machine.regions),
                    games=dict(self.machine.games))
        intents = reconcile(o)
        assert not check_invariants(o, intents), check_invariants(o, intents)
        for it in intents:
            self.recent[it.key] = self.mono
        self.last = o
        return intents

    def settle(self, passes=3, **kw):
        """Let the regions converge on a static world, then forget what we
        would have done, so a test sees only the decisions it provoked."""
        for _ in range(passes):
            self.observe(**kw)
        self.recent.clear()
        self.transitions.clear()
        return self


# =========================================================================
# the transition table itself
# =========================================================================
def test_every_region_has_an_unknown_state():
    for region in REGIONS:
        assert UNKNOWN in TRANSITIONS[region], region


def test_table_targets_and_guards_all_exist():
    for region, states in TRANSITIONS.items():
        for state, rules in states.items():
            for guard, nxt, reason in rules:
                assert guard in GUARDS, f'{region}.{state}: {guard}'
                assert nxt in states or nxt == UNKNOWN, f'{region}.{state}->{nxt}'
                assert reason and isinstance(reason, str)


# =========================================================================
# the audit's reconcile scenarios (failure modes 6-9)
# =========================================================================
def test_orphaned_session_is_reclaimed():
    """Audit failure 8: launcher SIGKILLed, no game left, pad stranded."""
    o = make_obs(session=SESSION, launcher_alive=False, pid_states={},
                 joystick=False,
                 regions={'session': 'orphaned', 'input_ownership': 'game'})
    got = reconcile(o)
    assert ('clear_flag', 'session') in verbs(got)
    assert ('route_pad', 'kodi') in verbs(got)
    assert ('show', 'kodi') in verbs(got)
    assert all(r.startswith('reconcile:') for r in reasons(got))


def test_stale_suspended_flag_is_removed():
    """Audit failure 9: game killed externally, flag left behind."""
    o = make_obs(suspended=APPID, pid_states={},
                 regions={'session': 'none'})
    got = find(reconcile(o), 'clear_flag', 'suspended')
    assert got and got[0].reason == 'reconcile:stale-suspended-flag'


def test_lost_thaw_is_repaired_with_the_pid_set():
    """Audit failure 6: everything frozen, no paused flag."""
    o = make_obs(session=SESSION, suspended=None,
                 pid_states={200: 'T', 201: 'T'}, joystick=False,
                 regions={'session': 'active', 'input_ownership': 'game'})
    got = find(reconcile(o), 'thaw')
    assert got, verbs(reconcile(o))
    assert got[0].args['pids'] == [200, 201]
    assert got[0].args['resolver']
    assert got[0].subject == APPID


def test_joystick_drift_is_corrected():
    """Audit failure 7: Kodi crash-restart reloads the wrong setting."""
    o = make_obs(joystick=False, session=None,
                 regions={'input_ownership': 'game', 'session': 'none'})
    got = find(reconcile(o), 'route_pad', 'kodi')
    assert got and got[0].reason == 'reconcile:joystick-setting-drift'
    assert got[0].args['was'] is False


def test_frozen_game_visible_raises_kodi():
    """Audit failure 5: the room is looking at a stopped game."""
    o = make_obs(suspended=APPID, pid_states={200: 'T'},
                 top_name='Elden Ring', top_class='steam_app_367520',
                 regions={'session': 'active', 'foreground': 'game'})
    got = find(reconcile(o), 'show', 'kodi')
    assert got
    assert 'reconcile:frozen-game-visible' in reasons(got)


def test_quiescent_world_wants_nothing():
    assert reconcile(make_obs()) == []


# =========================================================================
# guard invariants (steam-input-guard), only inside an enforcement window
# =========================================================================
def test_guard_closes_steam_menu_only_inside_a_window():
    world = dict(steam_route='OnFocusWindowChanged to window type: '
                             'k_nGameIDControllerConfigs_ClientUI, AppID 769',
                 focused_class='Kodi')
    assert not find(reconcile(make_obs(**world)), 'close_steam_menu')
    o = make_obs(regions={'enforcement': 'kodi'}, **world)
    assert find(reconcile(o), 'close_steam_menu')


def test_guard_raises_kodi_when_something_else_is_on_top():
    o = make_obs(top_name='Steam', top_class='steamwebhelper',
                 regions={'enforcement': 'kodi', 'foreground': 'other'})
    got = find(reconcile(o), 'show', 'kodi')
    assert got and got[0].args['invariant'] == 2


def test_guard_thaw_repair_carries_pids():
    o = make_obs(session=SESSION, pid_states={5: 'T', 6: 'T'}, joystick=False,
                 regions={'enforcement': 'game', 'session': 'active',
                          'input_ownership': 'game'})
    got = find(reconcile(o), 'thaw')
    assert got and got[0].args['pids'] == [5, 6]


# =========================================================================
# gestures (pad-home-watcher), driven through the real state machine
# =========================================================================
def _press(rig, k0):
    return rig.observe(button_down=True, down_since_k=k0, kernel_now=k0)


def test_hold_freezes_then_hands_off_on_release():
    rig = Rig(session=SESSION, pid_states={200: 'S', 201: 'S'}, joystick=False,
              top_name='Elden Ring', top_class='steam_app_367520').settle()
    k0 = 5000.0
    assert not _press(rig, k0)                       # gesture: idle -> down
    assert rig.machine.regions['gesture'] == 'down'
    got = rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 0.95)
    assert rig.machine.regions['gesture'] == 'hold-fired'
    freeze = find(got, 'freeze')
    assert freeze and freeze[0].args['pids'] == [200, 201]
    assert find(got, 'set_flag', 'suspended')
    # the pad must NOT move while the button is still down (audit failure 4)
    assert not find(got, 'route_pad')
    got = rig.observe(button_down=False, press_duration=1.1)
    assert rig.machine.regions['gesture'] == 'handoff-pending'
    assert find(got, 'route_pad', 'kodi')
    assert find(got, 'show', 'kodi')
    # ...and NOT a guide press: Steam's menu is not open, and the button is a
    # toggle (T4-1). See the three tests under "the guide press is a toggle".
    assert not find(got, 'close_steam_menu'), verbs(got)
    rig.observe()
    assert rig.machine.regions['gesture'] == 'idle'


def test_tap_with_a_paused_game_resumes_it():
    """...one double-tap window later, which is Donnie's 5 Aug amendment.

    The resume is state logic above the binding dispatch (a paused game with
    no way back is what the safety rail exists to prevent), but while the
    double-tap IS bound the tap cannot yet know it is the whole gesture - a
    double-tap on a paused game opens the switcher, which is exactly when the
    switcher is most useful. So the resume waits out the window and only then
    fires. gesture.paused_tap_decision is the shared rule; the live watcher's
    `pending_resume` is the same deferral.
    """
    rig = Rig(session=SESSION, suspended=APPID, pid_states={200: 'T'},
              joystick=True).settle()
    k0 = 6000.0
    _press(rig, k0)
    got = rig.observe(button_down=False, press_duration=0.3)
    assert rig.machine.regions['gesture'] == 'tap-wait', 'deferred, not fired'
    assert not find(got, 'launch'), 'the window has not run out yet'
    got = rig.observe(dt=DOUBLE_TAP_S + 0.05, button_down=False,
                      press_duration=0.3)
    assert rig.machine.regions['gesture'] == 'tap-resume'
    launch = find(got, 'launch')
    assert launch and launch[0].args['mode'] == 'resume'
    assert launch[0].subject == APPID
    assert not find(got, 'freeze')
    # ...and the window the suspend unmapped comes back with it (R7(c)).
    back = [i for i in find(got, 'show', APPID)
            if i.args.get('reason') == 'deiconify']
    assert back, verbs(got)


def test_an_unbound_double_tap_makes_the_paused_tap_instant_again():
    """The deferral is charged only where there is something to escalate to.

    With `double_tap` bound to Nothing the resume fires on the release, exactly
    as it did before the amendment - which is also what stops the latency from
    being a permanent tax on the recovery path.
    """
    binds = dict(DEFAULT_BINDINGS, double_tap='none')
    rig = Rig(session=SESSION, suspended=APPID, pid_states={200: 'T'},
              joystick=True, bindings=binds).settle()
    k0 = 6100.0
    _press(rig, k0)
    got = rig.observe(button_down=False, press_duration=0.3)
    assert rig.machine.regions['gesture'] == 'tap-resume'
    assert find(got, 'launch')


def test_a_deferred_resume_is_dropped_if_the_game_came_back_meanwhile():
    """The flag is re-read when the window shuts, not remembered from the
    press: a reconcile, the phone or a guard repair may have resumed inside
    those 350ms, and resuming twice raises a window over the Kodi the player
    is looking at."""
    rig = Rig(session=SESSION, suspended=APPID, pid_states={200: 'T'},
              joystick=True).settle()
    k0 = 6200.0
    _press(rig, k0)
    rig.observe(button_down=False, press_duration=0.3)
    assert rig.machine.regions['gesture'] == 'tap-wait'
    got = rig.observe(dt=DOUBLE_TAP_S + 0.05, button_down=False,
                      press_duration=0.3, suspended=None,
                      pid_states={200: 'S'})
    assert rig.machine.regions['gesture'] == 'idle'
    assert not find(got, 'launch')


def test_08_second_press_is_a_tap_and_09_is_a_hold():
    """The boundary is 0.9s of KERNEL time, both sides of it."""
    rig = Rig(session=SESSION, suspended=APPID, pid_states={200: 'T'},
              joystick=True).settle()
    k0 = 7000.0
    _press(rig, k0)
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 0.8)
    assert rig.machine.regions['gesture'] == 'down'          # not yet a hold
    rig.observe(button_down=False, press_duration=0.8)
    got = rig.observe(dt=DOUBLE_TAP_S + 0.05, button_down=False,
                      press_duration=0.8)
    assert find(got, 'launch'), 'a 0.8s press is a tap'

    rig2 = Rig(session=SESSION, pid_states={200: 'S'}, joystick=False).settle()
    k1 = 8000.0
    _press(rig2, k1)
    # +1us: 8000.0 + 0.9 lands a fraction BELOW the threshold in binary
    # floating point, and the comparison is >=, exactly as in the watcher.
    got = rig2.observe(button_down=True, down_since_k=k1,
                       kernel_now=k1 + HOLD_SECONDS + 1e-6)
    assert rig2.machine.regions['gesture'] == 'hold-fired'
    assert find(got, 'freeze'), 'a 0.9s press is a hold'


def test_release_that_never_comes_times_out_into_the_handoff():
    """The watcher's 4s safety net: hand the pad over rather than strand it."""
    rig = Rig(session=SESSION, pid_states={200: 'S'}, joystick=False).settle()
    k0 = 9000.0
    _press(rig, k0)
    got = rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 1.0)
    assert rig.machine.regions['gesture'] == 'hold-fired'
    assert find(got, 'freeze')
    # button still down 5s later and no further kernel events: time it out
    got = rig.observe(dt=5.0, button_down=True, down_since_k=k0,
                      kernel_now=k0 + 6.0)
    assert rig.machine.regions['gesture'] == 'timed-out'
    handoff = find(got, 'route_pad', 'kodi')
    assert handoff and handoff[0].reason == 'gesture:hold-release-timeout'


def test_pad_dying_mid_hold_still_hands_the_pad_back():
    rig = Rig(session=SESSION, pid_states={200: 'S'}, joystick=False).settle()
    k0 = 9200.0
    _press(rig, k0)
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 1.0)
    got = rig.observe(dt=0.2, pad_present=False, button_down=False)
    assert rig.machine.regions['gesture'] == 'handoff-pending'
    assert find(got, 'route_pad', 'kodi')


# =========================================================================
# the double-tap switcher gesture
# =========================================================================
def _tap(rig, k0, length=0.08, **kw):
    """One complete tap through the machine: press, then release."""
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0, **kw)
    return rig.observe(button_down=False, press_duration=length,
                       kernel_now=k0 + length, **kw)


def test_double_tap_in_a_game_suspends_first_then_asks_for_the_switcher():
    """The dialog is Kodi's, so Kodi must own pad and screen before it opens:
    the whole PS-hold suspend, then show_switcher, in that order."""
    rig = Rig(session=SESSION, pid_states={200: 'S', 201: 'S'}, joystick=False,
              top_name='Elden Ring', top_class='steam_app_367520').settle()
    k0 = 11000.0
    assert not find(_tap(rig, k0), 'show_switcher'), 'one tap is not a double'
    assert rig.machine.regions['gesture'] == 'tap-wait'
    got = _tap(rig, k0 + 0.2, double_armed=True)
    assert rig.machine.regions['gesture'] == 'double-tap'
    order = [(i.verb, i.subject) for i in got]
    assert order == [('freeze', APPID), ('set_flag', 'suspended'),
                     ('snapshot', APPID), ('route_pad', 'kodi'),
                     ('show', 'kodi'), ('iconify', APPID),
                     ('spawn_guard', 'kodi'), ('show_switcher', 'tv')]
    assert find(got, 'freeze')[0].args['pids'] == [200, 201]
    assert find(got, 'show_switcher')[0].args['suspended_first'] is True
    rig.observe()
    assert rig.machine.regions['gesture'] == 'idle'


def test_double_tap_with_nothing_running_guards_the_switcher_too():
    """The no-session branch gets the same guard the suspend branch does.

    It did not, and that was the bug behind "the switcher goes to Kodi for a
    second then back". A bare `show kodi` is one restack: nothing holds the
    screen, and whatever owned it - Steam's window is the documented offender
    on this box - takes it straight back, burying the dialog. The shadow log
    for 8 Aug has the shape of it: five double-taps in 22 seconds at 14:22,
    every one of them suspended_first:false, every one a lone show.

    The suspend branch above never had the problem because _handoff_intents
    ends in a guard. So this is not a new mechanism, it is that same last line
    on the branch that was missing it - which is why the assertion below is
    the sequence above with the freeze half removed, and nothing else.
    """
    rig = Rig(top_name='Thunar', top_class='Thunar').settle()
    k0 = 11500.0
    _tap(rig, k0)
    got = _tap(rig, k0 + 0.2, double_armed=True)
    assert verbs(got) == [('show', 'kodi'), ('spawn_guard', 'kodi'),
                          ('show_switcher', 'tv')]
    assert find(got, 'show_switcher')[0].args['suspended_first'] is False
    # the guard it opens is the real one, same window as every other handoff
    guard = find(got, 'spawn_guard')[0]
    assert guard.args['via'] == 'steam-input-guard kodi'
    assert not find(got, 'freeze') and not find(got, 'set_flag')
    assert find(got, 'show_switcher')[0].args['suspended_first'] is False


def test_double_tap_in_big_picture_records_the_suspend_like_a_hold():
    rig = Rig(session=BP_SESSION, big_picture_window=True, joystick=False,
              top_name='Big Picture Mode', top_class='steamwebhelper').settle()
    k0 = 11700.0
    _tap(rig, k0)
    got = _tap(rig, k0 + 0.2, double_armed=True)
    flag = find(got, 'set_flag', 'suspended')
    assert flag and flag[0].args['value'] == 'bigpicture'
    assert find(got, 'route_pad', 'kodi') and find(got, 'show_switcher', 'tv')


def test_tap_then_hold_is_a_hold_and_never_opens_the_switcher():
    rig = Rig(session=SESSION, pid_states={200: 'S'}, joystick=False).settle()
    k0 = 12000.0
    _tap(rig, k0)
    assert rig.machine.regions['gesture'] == 'tap-wait'
    rig.observe(button_down=True, down_since_k=k0 + 0.2, kernel_now=k0 + 0.2,
                double_armed=True)
    assert rig.machine.regions['gesture'] == 'down-again'
    got = rig.observe(button_down=True, down_since_k=k0 + 0.2,
                      kernel_now=k0 + 0.2 + HOLD_SECONDS + 1e-6,
                      double_armed=True)
    assert rig.machine.regions['gesture'] == 'hold-fired'
    assert find(got, 'freeze') and not find(got, 'show_switcher')


def test_a_lone_tap_expires_into_idle_and_asks_for_nothing():
    rig = Rig().settle()
    got = _tap(rig, 12500.0)
    assert not got
    assert rig.machine.regions['gesture'] == 'tap-wait'
    rig.observe(dt=DOUBLE_TAP_S + 0.05)
    assert rig.machine.regions['gesture'] == 'idle'


def test_a_second_press_after_the_window_is_a_new_first_tap():
    """The tracker's kernel-exact arming is what decides, not the state: a
    press that reaches 'down-again' late still releases as a plain tap."""
    rig = Rig().settle()
    k0 = 12800.0
    _tap(rig, k0)
    got = _tap(rig, k0 + 0.5, double_armed=False)
    assert not find(got, 'show_switcher')
    assert rig.machine.regions['gesture'] == 'tap-wait', 're-armed, not fired'


def test_a_double_tap_on_a_paused_game_opens_the_switcher_instead():
    """Donnie's 5 Aug amendment, from the Evening-1 couch: a double-tap on a
    PAUSED game is the switcher, not two resumes.

    Before it, the first tap resumed unconditionally and the second landed on a
    game that was already running - so the switcher, which is most useful
    exactly there (you are sat on Kodi wondering what else is open), could
    never be reached from a paused game at all.
    """
    rig = Rig(session=SESSION, suspended=APPID, pid_states={200: 'T'},
              joystick=True).settle()
    k0 = 13000.0
    got = _tap(rig, k0)
    assert not find(got, 'launch'), 'the first tap waits out the window'
    assert rig.machine.regions['gesture'] == 'tap-wait'
    got = _tap(rig, k0 + 0.2, double_armed=True)
    assert rig.machine.regions['gesture'] == 'double-tap'
    assert find(got, 'show_switcher'), verbs(got)
    # ...and it never resumed on the way through.
    assert not find(got, 'launch')


# =========================================================================
# the paused game's freeze-frame (pause-snap)
#
# An ACTION by the legacy stack - both suspend initiators capture the game
# window's last rendered frame and keep it as that game's artwork while it is
# frozen - so it is a would-do here like any other verb. It landed in both
# stacks in the same change, so like show_switcher there is no T5 whitelist
# entry: it must appear in BOTH streams or it is a real T4.
# =========================================================================
def test_a_hold_that_freezes_a_game_also_snapshots_it():
    """Right after the flag, and BEFORE the pad moves: the frame belongs to
    the freeze, not to the handoff (which does not happen until release)."""
    rig = Rig(session=SESSION, pid_states={200: 'S', 201: 'S'}, joystick=False,
              top_name='Elden Ring', top_class='steam_app_367520').settle()
    k0 = 14000.0
    _press(rig, k0)
    got = rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 0.95)
    assert verbs(got) == [('freeze', APPID), ('set_flag', 'suspended'),
                          ('snapshot', APPID)]
    snap = find(got, 'snapshot')[0]
    assert snap.args['via'] == 'pause-snap'
    assert snap.reason == 'gesture:ps-hold'
    assert snap.requires == ('gesture', 'session')


def test_the_phone_switcher_suspend_snapshots_the_same_way():
    """game-launch's suspend branch is the other initiator; the model does not
    distinguish them, which is the point - one verb, both callers."""
    o = make_obs(session=SESSION, pid_states={200: 'S'}, joystick=False,
                 regions={'gesture': 'hold-fired', 'session': 'active',
                          'input_ownership': 'game', 'foreground': 'game'},
                 top_name='Elden Ring', top_class='steam_app_367520')
    got = action_intents(o, 'hold', APPID, [200], defer_handoff=False)
    order = verbs(got)
    assert order.index(('snapshot', APPID)) == order.index(
        ('set_flag', 'suspended')) + 1
    assert order.index(('snapshot', APPID)) < order.index(('route_pad', 'kodi'))


def test_a_big_picture_suspend_has_no_frame_to_capture():
    """Nothing was frozen, so there is no game window whose last frame means
    anything - and neither live script runs pause-snap on this path."""
    o = make_obs(session=BP_SESSION, big_picture_window=True, joystick=False,
                 regions={'gesture': 'hold-fired', 'session': 'active',
                          'input_ownership': 'game', 'foreground': 'bigpicture'},
                 top_name='Big Picture Mode', top_class='steamwebhelper')
    got = action_intents(o, 'hold', None, [], defer_handoff=False)
    assert find(got, 'set_flag', 'suspended'), 'the suspend is still recorded'
    assert not find(got, 'snapshot')


def test_no_snapshot_when_there_is_nothing_to_suspend():
    o = make_obs(regions={'gesture': 'hold-fired', 'session': 'none'},
                 top_name='Thunar', top_class='Thunar')
    assert not find(action_intents(o, 'hold', None, []), 'snapshot')


def test_the_switcher_gesture_snapshots_too():
    """The double-tap borrows the whole suspend path, frame included."""
    rig = Rig(session=SESSION, pid_states={200: 'S'}, joystick=False,
              top_name='Elden Ring', top_class='steam_app_367520').settle()
    k0 = 14500.0
    _tap(rig, k0)
    got = _tap(rig, k0 + 0.2, double_armed=True)
    snap = find(got, 'snapshot', APPID)
    assert snap and snap[0].reason == 'gesture:ps-double-tap'
    order = verbs(got)
    assert order.index(('snapshot', APPID)) < order.index(('show_switcher', 'tv'))


def test_snapshot_is_suppressed_while_the_session_region_is_unknown():
    """R4: it requires session, so a blind session observer means no
    would-do rather than a guessed one."""
    o = make_obs(session=SESSION, pid_states={200: 'S'}, joystick=False,
                 regions={'gesture': 'hold-fired', 'session': UNKNOWN,
                          'input_ownership': 'game', 'foreground': 'game'},
                 top_name='Elden Ring', top_class='steam_app_367520')
    assert not find(reconcile(o), 'snapshot')


# =========================================================================
# key bindings (the addon's settings page, read through gestureconf)
#
# ONE file feeds both stacks: the live watcher dispatches on it and the model
# below decides its would-do from it, so after a rebind the shadow diff still
# compares like with like instead of scoring the model against a console it
# no longer describes. These tests bind gestures on Observed directly - the
# real settings file belongs to Kodi and a test must never write to it.
# =========================================================================
def bind(**kw):
    """A binding dict: the defaults, with the named gestures changed."""
    b = dict(DEFAULT_BINDINGS)
    b.update(kw)
    return b


def test_the_model_defaults_to_the_console_as_shipped():
    o = make_obs()
    assert o.bindings == DEFAULT_BINDINGS
    assert o.binding('hold') == 'suspend_to_kodi'
    assert o.binding('double_tap') == 'switcher'
    assert (o.hold_seconds, o.double_tap_seconds, o.long_hold_seconds) == (
        0.9, 0.35, 3.0)


def test_wrapped_double_tap_opens_the_rail_not_kodi():
    """The stage-3 overlay path (15 Aug 2026): a gamescope-wrapped game gets
    the rail composited over it - freeze + flag + snapshot + the overlay
    spawn, and NONE of the Kodi handoff. Every excluded verb here fought
    the rail live tonight before this branch existed."""
    o = make_obs(session=SESSION, pid_states={200: 'S'}, joystick=False,
                 top_name='shadPS4 v0.17.0 | CUSA00900', top_class='gamescope',
                 gamescope_display=':1',
                 regions={'gesture': 'double-tap', 'session': 'active',
                          'input_ownership': 'game', 'foreground': 'other'})
    got = reconcile(o)
    assert find(got, 'freeze')
    assert find(got, 'set_flag')
    assert find(got, 'snapshot')
    sw = find(got, 'show_switcher')
    assert sw and sw[0].args['via'] == 'switcher-overlay'
    assert sw[0].args['display'] == ':1'
    assert not find(got, 'route_pad'), verbs(got)
    assert not find(got, 'show', 'kodi'), verbs(got)
    assert not find(got, 'spawn_guard'), verbs(got)
    assert not find(got, 'iconify'), verbs(got)


def test_wrapped_double_tap_with_the_rail_up_is_a_noop():
    o = make_obs(session=SESSION, suspended=APPID, pid_states={200: 'T'},
                 joystick=False, top_class='gamescope',
                 gamescope_display=':1', overlay_up=True,
                 regions={'gesture': 'double-tap', 'session': 'active',
                          'input_ownership': 'game', 'foreground': 'other'})
    assert reconcile(o) == []


def test_wrapped_double_tap_on_a_frozen_game_respawns_the_rail_alone():
    """A cancelled/crashed rail with the frozen game still on screen: no
    second freeze, no snapshot spam, just the rail back."""
    o = make_obs(session=SESSION, suspended=APPID, pid_states={200: 'T'},
                 joystick=False, top_class='gamescope',
                 gamescope_display=':1',
                 regions={'gesture': 'double-tap', 'session': 'active',
                          'input_ownership': 'game', 'foreground': 'other'})
    got = reconcile(o)
    sw = find(got, 'show_switcher')
    assert sw and sw[0].args['via'] == 'switcher-overlay'
    assert not find(got, 'freeze')
    assert not find(got, 'snapshot')
    assert not find(got, 'route_pad') and not find(got, 'show', 'kodi')


def test_stale_gamescope_bridge_cannot_hijack_a_bare_session():
    """/tmp/game-gamescope left by a crashed wrap + a BARE game running:
    the window class is the tell (a bare game is never 'gamescope'), and
    the recipe must fall through to the normal Kodi switcher."""
    o = make_obs(session=SESSION, pid_states={200: 'S'}, joystick=False,
                 top_name='shadPS4 v0.17.0 | CUSA00900', top_class='shadps4',
                 gamescope_display=':1',
                 regions={'gesture': 'double-tap', 'session': 'active',
                          'input_ownership': 'game', 'foreground': 'other'})
    got = reconcile(o)
    sw = find(got, 'show_switcher')
    assert sw and sw[0].args['via'] == 'kodi-addon:script.couch.switcher'
    assert find(got, 'route_pad'), 'the normal handoff'


def test_the_rail_owns_the_pad_while_its_flag_is_up():
    """want_pad_owner: the rail turned Kodi's joystick off itself; the
    joystick-drift repair must not hand the stick back to the Kodi hiding
    behind the game."""
    o = make_obs(session=SESSION, suspended=APPID, pid_states={200: 'T'},
                 joystick=False, top_class='gamescope',
                 gamescope_display=':1', overlay_up=True,
                 regions={'session': 'active', 'input_ownership': 'game',
                          'foreground': 'other'})
    assert want_pad_owner(o) == 'game'
    assert not find(reconcile(o), 'route_pad'), 'no drift repair'


def test_rebinding_the_double_tap_changes_what_it_would_do():
    """The exact thing the shadow diff would otherwise report as a T4."""
    o = make_obs(regions={'gesture': 'double-tap'},
                 bindings=bind(double_tap='power_menu'))
    got = reconcile(o)
    assert verbs(got) == [('show', 'power-menu')]
    assert reasons(got) == ['gesture:ps-double-tap']
    assert not find(got, 'show_switcher'), 'the switcher was unbound'


def test_a_whole_hold_swallowed_by_one_pass_still_suspends():
    """Press AND release of a >=0.9s hold inside one stalled pass gap: the
    machine never saw the button down, but the tracker decided HOLD_RELEASE
    (hold_release_pending) and the table takes that decision - the suspend
    used to fall through to ps-tap-noop and drop in silence (adversarial
    review, 5 Aug 2026; same class as the coalesced double-tap)."""
    rig = Rig(session=SESSION, pid_states={200: 'S'}, joystick=False)
    rig.settle()
    got = rig.observe(button_down=False, press_duration=1.5,
                      hold_release_pending=True)
    assert rig.machine.regions['gesture'] == 'hold-fired'
    assert find(got, 'freeze')
    # the daemon consumes the marker on the hold-fired transition
    # (_on_transition -> tracker.consume_hold_release); the rig mimics that
    got = rig.observe(button_down=False, press_duration=1.5,
                      hold_release_pending=False)
    assert rig.machine.regions['gesture'] == 'handoff-pending'
    assert find(got, 'route_pad', 'kodi')
    assert find(got, 'spawn_guard', 'kodi')


def test_a_whole_double_swallowed_by_two_passes_still_fires_the_switcher():
    """BOTH taps of a 60ms double coalesced (two stalled passes in a row):
    the machine never left idle, so every released_double edge - which only
    exists in the in-flight states - was unreachable and the switcher was
    dropped in silence. Caught live by tools/gesture-sweep, 5 Aug 17:02.
    The tracker's consumable double_tap marker drives the idle edge."""
    rig = Rig(joystick=True)
    rig.settle()
    got = rig.observe(button_down=False, press_duration=0.08,
                      double_tap_pending=True)
    assert rig.machine.regions['gesture'] == 'double-tap'
    assert find(got, 'show_switcher', 'tv')
    # the daemon consumes the marker on the double-tap transition; without
    # it the state must still close normally and NOT re-enter
    got = rig.observe(button_down=False, press_duration=0.08,
                      double_tap_pending=False)
    assert rig.machine.regions['gesture'] == 'idle'
    got = rig.observe(button_down=False, press_duration=0.08,
                      double_tap_pending=False)
    assert rig.machine.regions['gesture'] == 'idle'
    assert not find(got, 'show_switcher', 'tv')


def test_hold_marker_is_spent_when_the_region_finishes_with_the_press():
    """The stuck-hold shape that tools/gesture-sweep caught live (5 Aug
    16:59): the release of a timed-out hold sets the tracker marker while
    the region sits in 'timed-out', so consuming only on hold-fired entry
    left it armed - idle re-entered hold-fired as a phantom and ate every
    press for the next ~12s (five burst taps, zero switchers)."""
    from couchd import hold_marker_spent
    # taking the hold spends it, both coalesced and live
    assert hold_marker_spent('gesture', 'idle', 'hold-fired')
    assert hold_marker_spent('gesture', 'down', 'hold-fired')
    assert hold_marker_spent('gesture', 'hold-fired', 'handoff-pending')
    # ...and so does completing the gesture back to idle from any hold state
    assert hold_marker_spent('gesture', 'timed-out', 'idle')
    assert hold_marker_spent('gesture', 'handoff-pending', 'idle')
    assert hold_marker_spent('gesture', 'hold-fired', 'idle')
    assert hold_marker_spent('gesture', 'long-hold-fired', 'idle')
    # tap traffic never does
    assert not hold_marker_spent('gesture', 'tap-wait', 'idle')
    assert not hold_marker_spent('gesture', 'down', 'tap-wait')
    assert not hold_marker_spent('gesture', 'double-tap', 'idle')
    assert not hold_marker_spent('session', 'none', 'idle')


def test_rebinding_the_hold_to_the_switcher_suspends_and_opens_the_dialog():
    o = make_obs(session=SESSION, pid_states={200: 'S'}, joystick=False,
                 regions={'gesture': 'hold-fired', 'session': 'active',
                          'input_ownership': 'game', 'foreground': 'game'},
                 top_name='Elden Ring', top_class='steam_app_367520',
                 bindings=bind(hold='switcher', double_tap='none',
                               hold_release='suspend_to_kodi'))
    got = reconcile(o)
    assert verbs(got) == [('freeze', APPID), ('set_flag', 'suspended'),
                          ('snapshot', APPID), ('route_pad', 'kodi'),
                          ('show', 'kodi'), ('iconify', APPID),
                          ('spawn_guard', 'kodi'), ('show_switcher', 'tv')]
    # not the hold's deferred handoff: a switcher hands off at once, exactly
    # as the double-tap one always has
    assert find(got, 'show_switcher')[0].reason == 'gesture:ps-hold-switcher'


def test_a_hold_that_is_not_the_suspend_does_not_wait_for_a_handoff():
    """Without this the region would sit in handoff-pending for the 4s
    timeout waiting for a handoff nobody is going to emit, blocking repairs."""
    rig = Rig(bindings=bind(hold='tv_toggle', double_tap='suspend_to_kodi'),
              top_name='Thunar', top_class='Thunar').settle()
    k0 = 20000.0
    _press(rig, k0)
    got = rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 1.0)
    assert rig.machine.regions['gesture'] == 'hold-fired'
    assert verbs(got) == [('tv_toggle', 'tv')]
    rig.observe(button_down=False, press_duration=1.2)
    assert rig.machine.regions['gesture'] == 'idle', 'straight back to idle'


def test_the_default_hold_still_defers_its_handoff_to_the_release():
    rig = Rig(session=SESSION, pid_states={200: 'S'}, joystick=False).settle()
    k0 = 20500.0
    _press(rig, k0)
    got = rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 1.0)
    assert find(got, 'freeze') and not find(got, 'route_pad')
    assert rig.machine.regions['gesture'] == 'hold-fired'
    got = rig.observe(button_down=False, press_duration=1.2)
    assert rig.machine.regions['gesture'] == 'handoff-pending'
    assert find(got, 'route_pad', 'kodi')


def test_a_bound_hold_release_fires_on_top_of_the_handoff():
    o = make_obs(session=SESSION, regions={'gesture': 'handoff-pending',
                                           'session': 'active'},
                 bindings=bind(hold_release='desktop'))
    got = reconcile(o)
    assert verbs(got) == [('route_pad', 'kodi'), ('show', 'kodi'),
                          ('spawn_guard', 'kodi'), ('show', 'desktop')]
    assert find(got, 'show', 'desktop')[0].reason == 'gesture:ps-hold-release'


def test_a_bound_tap_fires_from_the_tap_wait_state():
    o = make_obs(regions={'gesture': 'tap-wait'}, press_duration=0.08,
                 bindings=bind(tap='power_menu', double_tap='none'))
    got = reconcile(o)
    assert verbs(got) == [('show', 'power-menu')]
    assert reasons(got) == ['gesture:ps-tap']


def test_a_long_press_that_lands_in_tap_wait_is_not_a_tap():
    """With `hold` unbound a long press never leaves 'down' for 'hold-fired',
    so it releases into 'tap-wait' - and must not fire the tap action there."""
    o = make_obs(regions={'gesture': 'tap-wait'}, press_duration=5.0,
                 bindings=bind(tap='power_menu', double_tap='none',
                               hold='none', long_hold='suspend_to_kodi'))
    assert reconcile(o) == []


def test_the_default_tap_asks_for_nothing_at_all():
    """tap=none is the shipped console: a no-op tap parks in tap-wait waiting
    for a possible second press and decides nothing."""
    assert reconcile(make_obs(regions={'gesture': 'tap-wait'},
                              press_duration=0.08)) == []


def test_the_long_hold_tier_is_only_reachable_with_the_hold_unbound():
    rig = Rig(session=SESSION, pid_states={200: 'S'}, joystick=False,
              bindings=bind(hold='none', long_hold='quit_game',
                            double_tap='suspend_to_kodi')).settle()
    k0 = 21000.0
    _press(rig, k0)
    # past the 0.9s hold threshold: with the hold unbound nothing fires yet
    got = rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 1.5)
    assert rig.machine.regions['gesture'] == 'down', 'still just a long press'
    assert not got
    got = rig.observe(button_down=True, down_since_k=k0,
                      kernel_now=k0 + 3.0 + 1e-6)
    assert rig.machine.regions['gesture'] == 'long-hold-fired'
    quit_ = find(got, 'quit')
    assert quit_ and quit_[0].reason == 'gesture:ps-long-hold'
    assert quit_[0].args['pids'] == [200] and quit_[0].args['resolver']
    rig.observe(button_down=False, press_duration=3.5)
    assert rig.machine.regions['gesture'] == 'idle'


def test_a_bound_hold_still_wins_the_press_from_the_long_hold():
    """The documented semantics: the hold fires at 0.9 as today and the press
    is spent. gestureconf drops a shadowed long_hold before it gets here, so
    this is the belt-and-braces half of the same rule."""
    rig = Rig(session=SESSION, pid_states={200: 'S'}, joystick=False,
              bindings=bind(long_hold='quit_game')).settle()
    k0 = 21500.0
    _press(rig, k0)
    got = rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 4.0)
    assert rig.machine.regions['gesture'] == 'hold-fired'
    assert find(got, 'freeze') and not find(got, 'quit')


def test_a_custom_hold_threshold_moves_the_boundary():
    rig = Rig(session=SESSION, pid_states={200: 'S'}, joystick=False,
              hold_seconds=1.5).settle()
    k0 = 22000.0
    _press(rig, k0)
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 1.0)
    assert rig.machine.regions['gesture'] == 'down', '1.0s is a tap at 1.5'
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 1.5 + 1e-6)
    assert rig.machine.regions['gesture'] == 'hold-fired'


def test_every_action_gestureconf_names_is_implemented_by_the_model():
    """A binding the settings page offers and the model cannot decide would
    be a gesture that silently does nothing on one side of the diff."""
    o = make_obs(session=SESSION, pid_states={200: 'S'},
                 regions={'gesture': 'double-tap', 'session': 'active'})
    for action in ACTIONS:
        got = action_intents(replace(o, bindings=bind(double_tap=action)),
                             'double_tap', APPID, [200])
        if action == 'none':
            assert got == []
        else:
            assert got, f'{action} decides nothing'
            assert all(i.reason.startswith('gesture:') for i in got)


def test_quit_game_with_nothing_running_decides_nothing():
    o = make_obs(regions={'gesture': 'double-tap'},
                 bindings=bind(double_tap='quit_game'))
    assert reconcile(o) == []


def test_no_repair_intents_while_a_gesture_is_in_flight():
    """Reconciling mid-press is how Kodi gets a phantom held button."""
    rig = Rig(session=SESSION, suspended=APPID, pid_states={},
              joystick=False).settle()
    k0 = 9500.0
    got = _press(rig, k0)
    assert rig.machine.regions['gesture'] == 'down'
    assert not [i for i in got if i.reason.startswith('reconcile:')]
    # the same world with the button up does want repairs
    rig2 = Rig(session=SESSION, suspended=APPID, pid_states={},
               joystick=False).settle()
    got2 = rig2.observe()
    assert [i for i in got2 if i.reason.startswith('reconcile:')]


# =========================================================================
# unknown-region suppression (R4)
# =========================================================================
def test_kodi_down_suppresses_pad_routing_but_not_flag_repairs():
    o = make_obs(kodi_known=False, joystick=None, suspended=APPID,
                 pid_states={}, regions={'input_ownership': UNKNOWN,
                                         'session': 'none'})
    got = reconcile(o)
    assert not find(got, 'route_pad')
    assert find(got, 'clear_flag', 'suspended')


def test_x_down_suppresses_window_intents():
    o = make_obs(x_known=False, top_name='', top_class='', suspended=APPID,
                 pid_states={200: 'T'},
                 regions={'foreground': UNKNOWN, 'session': 'active'})
    assert not find(reconcile(o), 'show')


def test_unknown_pad_suppresses_gesture_intents():
    o = make_obs(pad_known=False, session=SESSION, pid_states={200: 'S'},
                 joystick=False,
                 regions={'gesture': UNKNOWN, 'pad': UNKNOWN,
                          'session': 'active', 'input_ownership': 'game'})
    assert not find(reconcile(o), 'freeze')


def test_unknown_regions_are_reachable_when_a_source_goes_blind():
    rig = Rig(session=SESSION, pid_states={200: 'S'}, joystick=False).settle()
    rig.observe(kodi_known=False, joystick=None)
    assert rig.machine.regions['input_ownership'] == UNKNOWN
    rig.observe(x_known=False)
    assert rig.machine.regions['foreground'] == UNKNOWN
    rig.observe(flags_known=False)
    assert rig.machine.regions['session'] == UNKNOWN


# =========================================================================
# R7: the two pre-declared legacy bugs, done RIGHT
# =========================================================================
def test_r7a_big_picture_hold_records_the_suspend():
    """Legacy freeze_game() writes /tmp/game-suspended only inside `if
    pids:`, so a pure Big Picture hold leaves no flag and reconcile takes the
    pad off Kodi ~10s later - routed to nobody. couchd records it."""
    rig = Rig(session=BP_SESSION, pid_states={}, joystick=False,
              big_picture_window=True, top_name='Big Picture Mode',
              top_class='steamwebhelper').settle()
    k0 = 10000.0
    _press(rig, k0)
    got = rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 1.0)
    flag = find(got, 'set_flag', 'suspended')
    assert flag and flag[0].args['value'] == 'bigpicture'
    assert not find(got, 'freeze'), 'nothing to freeze in pure Big Picture'


def test_r7a_pad_is_never_routed_to_an_invisible_big_picture():
    """The other half of the bug: session present, nothing frozen, nothing
    running, Kodi on screen. Legacy's `want = not (session and not
    suspended)` says the pad belongs to the game. couchd asks what is
    actually in front of the room."""
    o = make_obs(session=BP_SESSION, suspended=None, pid_states={},
                 joystick=True, top_name='Kodi', top_class='Kodi',
                 big_picture_window=True,
                 regions={'session': 'active', 'input_ownership': 'kodi',
                          'foreground': 'kodi'})
    assert want_pad_owner(o) == 'kodi'
    assert not find(reconcile(o), 'route_pad', 'game')


def test_r7b_a_game_launched_inside_big_picture_keeps_its_real_appid():
    """Legacy records appid as the literal string "bigpicture", so that
    game's own Kodi tile CLOSES it instead of resuming. Steam's ledger knows
    better, and couchd asks the ledger."""
    o = make_obs(session=BP_SESSION, suspended='bigpicture',
                 pid_states={200: 'T', 201: 'T'},
                 ledger={APPID: (200, 201)}, games={APPID: 'FROZEN'},
                 joystick=True,
                 regions={'session': 'active', 'gesture': 'tap-resume'})
    assert resolve_appid(o) == APPID
    got = reconcile(o)
    launch = find(got, 'launch')
    assert launch and launch[0].subject == APPID
    assert launch[0].args['mode'] == 'resume'
    assert launch[0].args['suspended_flag'] == 'bigpicture'
    assert not find(got, 'quit') and not find(got, 'kill')


def test_r7b_freeze_subject_is_the_ledger_appid_too():
    o = make_obs(session=BP_SESSION, pid_states={200: 'S'},
                 ledger={APPID: (200,)}, games={APPID: 'RUNNING'},
                 joystick=False,
                 regions={'session': 'active', 'gesture': 'hold-fired',
                          'input_ownership': 'game'})
    freeze = find(reconcile(o), 'freeze')
    assert freeze and freeze[0].subject == APPID


# =========================================================================
# transitions, agreement metric, convergence
# =========================================================================
def test_session_start_and_end_produce_the_transition_intents():
    rig = Rig().settle()
    got = rig.observe(session=SESSION, pid_states={}, joystick=False)
    assert rig.machine.regions['session'] == 'starting'
    assert find(got, 'route_pad', 'game')
    assert find(got, 'show')
    assert find(got, 'request_tv_wake')
    rig.observe(session=SESSION, pid_states={200: 'S'}, joystick=False)
    assert rig.machine.regions['session'] == 'active'
    got = rig.observe(session=None, pid_states={}, joystick=True)
    assert rig.machine.regions['session'] == 'ending'
    assert find(got, 'route_pad', 'kodi')


def test_freeze_set_agreement_flags_a_proton_style_miss():
    o = make_obs(pid_states={1: 'S', 2: 'S'})
    ok = freeze_set_agreement(o, ledger_pids={1, 2}, tree_pids={1, 2})
    assert ok['agree']
    # the audit's failure 1 shape: the tree knows about a pid we would miss
    bad = freeze_set_agreement(o, ledger_pids={1, 2, 3}, tree_pids={1, 2, 3})
    assert not bad['agree'] and bad['tree_minus_couchd'] == [3]


def test_repeated_reconcile_on_a_static_world_reaches_a_fixpoint():
    o = make_obs(session=SESSION, suspended=None, pid_states={9: 'T'},
                 joystick=False, top_class='steam_app_367520',
                 regions={'session': 'active', 'input_ownership': 'game',
                          'foreground': 'game'})
    first = reconcile(o)
    assert first
    recent = {i.key: o.mono for i in first}
    assert reconcile(replace(o, recent=recent)) == []


# =========================================================================
# the wire schema the differ (MVS-2) will read
# =========================================================================
def test_intent_records_match_the_shared_schema(tmp_path, monkeypatch):
    import couchd
    from couchd import RecordingExecutor, ShadowLog
    # never let a test line into the real corpus's human log
    monkeypatch.setattr(couchd, 'HUMAN_LOG', str(tmp_path / 'couchd.log'))
    log = ShadowLog(directory=str(tmp_path), prefix='couchd')
    ex = RecordingExecutor(log)
    o = make_obs(session=SESSION, pid_states={200: 'S'}, joystick=False,
                 regions={'gesture': 'hold-fired', 'session': 'active',
                          'input_ownership': 'game'})
    intents = reconcile(o)
    assert intents
    for it in intents:
        ex.execute(it, o)
    log.close()
    import json
    recs = [json.loads(line) for line in
            (tmp_path / f'couchd-{__import__("time").strftime("%Y%m%d")}.jsonl')
            .read_text().splitlines()]
    assert len(recs) == len(intents)
    required = {'t', 'seq', 'mono', 'verb', 'subject', 'args', 'reason',
                'regions', 'predict', 'kind'}
    for r in recs:
        assert required <= set(r), required - set(r)
        assert r['kind'] == 'intent'
        assert isinstance(r['t'], float) and isinstance(r['seq'], int)
        assert isinstance(r['mono'], float)
        assert r['predict'] is None or set(r['predict']) == {'effect', 'deadline_s'}
        assert set(r['regions']) >= set(REGIONS)
    assert [r['seq'] for r in recs] == sorted(r['seq'] for r in recs)
    freeze = [r for r in recs if r['verb'] == 'freeze']
    assert freeze and freeze[0]['args']['pids'] == [200]
    assert freeze[0]['args']['resolver']


# =========================================================================
# stateful property testing (C20) - in-process, against the pure reconcile
# =========================================================================
class ConsoleModel(RuleBasedStateMachine):
    """Random observation sequences, including impossible orderings, driven
    straight into Machine+reconcile. Every step asserts the named invariants;
    Hypothesis hunts for the illegal cross-region combination."""

    def __init__(self):
        super().__init__()
        self.mono = 1000.0
        self.kernel = 5000.0
        self.machine = Machine()
        self.machine.since = {r: self.mono for r in REGIONS}
        self.recent = {}
        self.w = dict(session=None, suspended=None, pid_states={},
                      joystick=True, launcher_alive=None,
                      top_name='Kodi', top_class='Kodi', focused_class='Kodi',
                      big_picture_window=False, steam_route='', ledger={},
                      pad_known=True, pad_present=True, button_down=False,
                      down_since_k=None, press_duration=None,
                      double_armed=False,
                      flags_known=True, pids_known=True, kodi_known=True,
                      x_known=True, steam_known=True, kodi_window=10000)
        self.violations = []

    # -- world mutations -------------------------------------------------
    @rule(mode=st.sampled_from(['steam', 'bigpicture', 'shadps4']))
    def start_session(self, mode):
        self.w['session'] = {'launcher_pid': 111, 'mode': mode,
                             'appid': APPID if mode == 'steam' else None,
                             'raw': f'111 {mode}'}
        self.w['launcher_alive'] = True

    @rule()
    def end_session(self):
        self.w['session'] = None
        self.w['launcher_alive'] = None

    @rule()
    def kill_launcher(self):
        self.w['launcher_alive'] = False

    @rule(n=st.integers(min_value=0, max_value=4))
    def game_processes(self, n):
        self.w['pid_states'] = {200 + i: 'S' for i in range(n)}
        self.w['ledger'] = {APPID: tuple(self.w['pid_states'])} if n else {}

    @rule()
    def freeze_processes(self):
        self.w['pid_states'] = {p: 'T' for p in self.w['pid_states']}

    @rule(v=st.sampled_from([APPID, 'bigpicture', None]))
    def set_suspended(self, v):
        self.w['suspended'] = v

    @rule(v=st.booleans())
    def set_joystick(self, v):
        self.w['joystick'] = v

    @rule(top=st.sampled_from([('Kodi', 'Kodi'),
                               ('Elden Ring', 'steam_app_367520'),
                               ('Big Picture Mode', 'steamwebhelper'),
                               ('Thunar', 'Thunar'),
                               # the transition curtain: an overlay that may
                               # appear over ANY of the worlds above, in any
                               # ordering Hypothesis can invent
                               ('couch-curtain', 'couch-curtain')]))
    def set_top_window(self, top):
        self.w['top_name'], self.w['top_class'] = top
        self.w['big_picture_window'] = 'Big Picture' in top[0]

    @rule(open_=st.booleans())
    def steam_menu(self, open_):
        self.w['steam_route'] = ('... ClientUI, AppID 769' if open_ else
                                 '... Desktop, AppID 413080')

    @rule(armed=st.booleans())
    def press(self, armed):
        # `armed` is what the tracker would have decided in kernel time: this
        # press began inside DOUBLE_TAP_S of the previous tap's release. Left
        # free so Hypothesis can also produce the impossible orderings (armed
        # with no preceding tap at all) the model must survive.
        self.kernel += 0.05
        self.w['button_down'] = True
        self.w['down_since_k'] = self.kernel
        self.w['double_armed'] = armed

    @rule(held=st.floats(min_value=0.0, max_value=3.0))
    def release(self, held):
        if self.w['down_since_k'] is not None:
            self.w['press_duration'] = held
        self.w['button_down'] = False
        self.w['down_since_k'] = None
        self.kernel += held

    @rule()
    def pad_gone(self):
        self.w['pad_present'] = False
        self.w['button_down'] = False
        self.w['down_since_k'] = None
        self.w['double_armed'] = False   # PressTracker.reset() does this

    @rule()
    def pad_back(self):
        self.w['pad_present'] = True

    @rule(source=st.sampled_from(['flags_known', 'pids_known', 'kodi_known',
                                  'x_known', 'steam_known', 'pad_known']),
          ok=st.booleans())
    def observer_health(self, source, ok):
        self.w[source] = ok
        if source == 'kodi_known' and not ok:
            self.w['joystick'] = None

    @rule(dt=st.floats(min_value=0.05, max_value=12.0))
    def tick(self, dt):
        self.mono += dt
        self.kernel += dt

    # -- the pass under test ---------------------------------------------
    def _pass(self):
        self.mono += 0.2
        w = dict(self.w)
        if w['kodi_known'] and w['joystick'] is None:
            w['joystick'] = True
        o = make_obs(now=self.mono, mono=self.mono, kernel_now=self.kernel,
                     regions=dict(self.machine.regions),
                     region_since=dict(self.machine.since),
                     games=dict(self.machine.games), recent=dict(self.recent),
                     **w)
        self.machine.step(o)
        o = replace(o, regions=dict(self.machine.regions),
                    games=dict(self.machine.games))
        intents = reconcile(o)
        for it in intents:
            self.recent[it.key] = self.mono
        return o, intents

    @invariant()
    def model_invariants_hold(self):
        o, intents = self._pass()
        bad = check_invariants(o, intents)
        assert not bad, f'{bad} regions={o.regions}'
        # named invariants, spelled out again at the property level
        if o.regions['gesture'] != 'idle':
            assert not [i for i in intents if i.reason.startswith('reconcile:')]
        for i in intents:
            for r in i.requires:
                assert o.regions.get(r) != UNKNOWN
            if i.verb in ('freeze', 'thaw', 'quit', 'kill'):
                assert 'pids' in i.args and 'resolver' in i.args
        # convergence: nothing new on an unchanged world
        recent = dict(self.recent)
        assert reconcile(replace(o, recent=recent)) == []


# =========================================================================
# Evening-1 model catch-up: the "couchd model catch-up pending" T5 notes
#
# Each of these reproduces a decision the LEGACY stack took on the couch on
# 4-5 Aug 2026 and couchd's model did not. The observation values are the real
# ones out of shadow/archive/legacy-intents-evening1-20260805.jsonl wherever
# the corpus has them (appid 367520, the 18-process freeze set, the guard pid
# and the window id from the iconify lines), so a test failing here means the
# model disagrees with something that actually happened in the room.
# =========================================================================
#: the freeze set of the 5 Aug 02:05:35 PS-hold, verbatim
E1_PIDS = [1651480, 1651481, 1651482, 1651618, 1651649, 1651654, 1651656,
           1651660, 1651663, 1651672, 1651683, 1651690, 1651708, 1651720,
           1651730, 1651732, 1651737, 1651749]
E1_GUARD_PID = 1694350          # the guard superseded at 02:34:32
E1_TOPCLS = 'steam_app_367520'


def _running(pids, state='S'):
    return {p: state for p in pids}


def test_t5_iconify_the_frozen_game_at_the_handoff():
    """R7(c): legacy `iconify 367520 via=wm-change-state` at 02:33:46.

    A SIGSTOPped client keeps whatever pointer grab it froze holding, so its
    cursor sits over Kodi and the phone's clicks are eaten; X only drops a
    grab when the grab window stops being viewable. Raising Kodi does not do
    it - unmapping does.
    """
    rig = Rig(session=SESSION, pid_states=_running(E1_PIDS), joystick=False,
              top_name='ELDEN RING', top_class=E1_TOPCLS).settle()
    k0 = 20000.0
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0)
    got = rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 0.95)
    assert find(got, 'freeze'), verbs(got)
    assert not find(got, 'iconify'), 'not while the button is still down'
    # release: the world now has the flag and the stopped processes in it
    got = rig.observe(button_down=False, press_duration=1.1, suspended=APPID,
                      pid_states=_running(E1_PIDS, 'T'))
    icon = find(got, 'iconify')
    assert icon, verbs(got)
    assert icon[0].subject == APPID
    assert icon[0].args['via'] == 'wm-change-state'
    # ...and it comes AFTER Kodi has the screen, exactly as the watcher does it
    order = [i.verb for i in got]
    assert order.index('show') < order.index('iconify')


def test_t5_a_big_picture_suspend_has_no_window_to_iconify():
    """Nothing was frozen, so there is no stuck grab and no window to unmap -
    and neither live script emits an iconify on that path."""
    rig = Rig(session=BP_SESSION, pid_states={}, joystick=False,
              big_picture_window=True, top_name='Steam Big Picture Mode',
              top_class='steamwebhelper').settle()
    assert rig.machine.regions['foreground'] == 'bigpicture'
    k0 = 20100.0
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0)
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 0.95)
    got = rig.observe(button_down=False, press_duration=1.1,
                      suspended='bigpicture')
    assert find(got, 'route_pad', 'kodi')
    assert not find(got, 'iconify'), verbs(got)


def test_t5_the_resume_maps_the_frozen_window_back():
    """R7(c) the other way round: legacy `show 367520 via=activate
    reason=deiconify window=0x7e00001` on every resume. A thawed game left
    iconified is audible, holds the pad, and shows the room nothing."""
    rig = Rig(session=SESSION, suspended=APPID,
              pid_states=_running(E1_PIDS, 'T'), joystick=True).settle()
    k0 = 20200.0
    _tap(rig, k0)
    got = rig.observe(dt=DOUBLE_TAP_S + 0.05, button_down=False,
                      press_duration=0.08)
    assert find(got, 'launch'), verbs(got)
    back = [i for i in find(got, 'show', APPID)
            if i.args.get('reason') == 'deiconify']
    assert back and back[0].args['via'] == 'activate'


def test_t5_a_repair_thaw_maps_the_window_back_too():
    """The watcher's `map_game_window(appid, 'reconcile:thawed-without-flag')`
    after the lost-thaw repair, for the same reason."""
    o = make_obs(session=SESSION, suspended=None,
                 pid_states=_running(E1_PIDS[:3], 'T'), joystick=False,
                 regions={'session': 'active', 'input_ownership': 'game'})
    got = reconcile(o)
    assert find(got, 'thaw'), verbs(got)
    back = [i for i in find(got, 'show', APPID)
            if i.args.get('reason') == 'deiconify']
    assert back and back[0].reason == 'reconcile:thawed-without-flag'


def test_t5_a_freeze_supersedes_an_open_guard_window_first():
    """R7(d): legacy `kill steam-input-guard pids=[1694350]
    reason=superseded-by-freeze` at 02:34:32, BEFORE the STOPs.

    A guard opened by a recent resume asserts "a game that should be running
    must be thawed"; a PS hold inside that window raced its own repair and
    lost (4 Aug, 18 processes SIGCONTed 1.8s after being frozen).
    """
    rig = Rig(session=SESSION, pid_states=_running(E1_PIDS), joystick=False,
              top_name='ELDEN RING', top_class=E1_TOPCLS,
              guard_pid=E1_GUARD_PID).settle()
    k0 = 20300.0
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0)
    got = rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 0.95)
    kill = find(got, 'kill', 'steam-input-guard')
    assert kill, verbs(got)
    assert kill[0].args['pids'] == [E1_GUARD_PID]
    assert kill[0].args['signal'] == 'SIGTERM'
    assert kill[0].args['reason'] == 'superseded-by-freeze'
    order = [i.verb for i in got]
    assert order.index('kill') < order.index('freeze'), 'before the STOPs'


def test_t5_a_freeze_never_supersedes_couchds_own_guard_window():
    """The pidfile holding couchd's own write-through IS couchd's enforcement
    window. SIGTERMing it would kill the daemon holding the console together -
    the same rule the legacy watcher yields on."""
    rig = Rig(session=SESSION, pid_states=_running(E1_PIDS), joystick=False,
              top_name='ELDEN RING', top_class=E1_TOPCLS,
              guard_pid=E1_GUARD_PID, guard_pid_ours=True).settle()
    k0 = 20400.0
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0)
    got = rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 0.95)
    assert find(got, 'freeze')
    assert not find(got, 'kill'), verbs(got)


def test_t5_a_suspend_inside_a_game_window_ends_the_window():
    """R7(d): the guard's `window_close reason=suspended-mid-window`.

    Every game-mode invariant is moot once the game is meant to be frozen, and
    spending the remaining seconds fighting the player's own gesture is how
    the 4 Aug race happened. couchd is the single arbiter, so for it the
    enforcement REGION is what closes.
    """
    rig = Rig(session=SESSION, pid_states=_running(E1_PIDS), joystick=False,
              top_name='ELDEN RING', top_class=E1_TOPCLS).settle()
    rig.machine.regions['enforcement'] = 'game'
    o = rig.observe(enforcement_target='game',
                    enforcement_until=rig.mono + 6.0)
    assert rig.machine.regions['enforcement'] == 'game'
    rig.observe(enforcement_target='game', enforcement_until=rig.mono + 6.0,
                suspended=APPID, pid_states=_running(E1_PIDS, 'T'))
    assert rig.machine.regions['enforcement'] == 'none'
    assert ('enforcement', 'game', 'none', 'suspended-mid-window') \
        in rig.transitions
    # ...and it stays closed rather than flapping straight back in
    rig.observe(enforcement_target='game', enforcement_until=rig.mono + 6.0,
                suspended=APPID, pid_states=_running(E1_PIDS, 'T'))
    assert rig.machine.regions['enforcement'] == 'none'


BB_SESSION = {'launcher_pid': 2685994, 'mode': 'shadps4',
              'appid': '/home/ds2000/games/ps4/CUSA00900/eboot.bin',
              'raw': ('2685994 shadps4 '
                      '/home/ds2000/games/ps4/CUSA00900/eboot.bin')}


def test_a_foreign_suspend_flag_never_resumes_over_a_live_session():
    """Replay of 22 Aug 2026 21:42:44 ("blood borne had loaded but then
    elden ring appeared? out of nowbere").

    One minute into a fresh Bloodborne session: /tmp/game-suspended still
    said '1245620' from the PREVIOUS night (the ER quit leaked its whole
    frozen wine tree and the flag with it), Steam's ledger still carried
    the leaked pids, and a PS tap was classified tap-resume - couchd
    launched and showed Elden Ring over the game Donnie was playing.
    The world below is built from the shadow log of that pass. A suspend
    flag that names a different game than the live session is debris and
    must never be a resume target.
    """
    leaked = {1015591: 'T', 1015927: 'T', 1015945: 'T', 2686001: 'S'}
    rig = Rig(session=BB_SESSION, suspended='1245620',
              pid_states=leaked,
              ledger={'1245620': (1015591, 1015927)},
              joystick=False).settle()
    k0 = 9000.0
    _press(rig, k0)
    got = rig.observe(button_down=False, press_duration=0.15)
    assert rig.machine.regions['gesture'] != 'tap-resume', \
        'instant resume path took the debris'
    # ...and the deferred path when the double-tap window shuts:
    got = rig.observe(dt=DOUBLE_TAP_S + 0.05, button_down=False,
                      press_duration=0.15)
    assert rig.machine.regions['gesture'] != 'tap-resume', \
        'deferred resume path took the debris'
    assert not find(got, 'launch', '1245620'), verbs(got)


def test_a_foreign_suspend_flag_never_resumes_even_when_instant():
    """The same debris with double_tap unbound (the instant-resume path)."""
    binds = dict(DEFAULT_BINDINGS, double_tap='none')
    rig = Rig(session=BB_SESSION, suspended='1245620',
              pid_states={1015591: 'T'}, ledger={'1245620': (1015591,)},
              joystick=False, bindings=binds).settle()
    _press(rig, 9100.0)
    got = rig.observe(button_down=False, press_duration=0.15)
    assert rig.machine.regions['gesture'] != 'tap-resume'
    assert not find(got, 'launch', '1245620'), verbs(got)


def test_a_matching_suspend_flag_still_resumes_with_a_live_session():
    """The control: the guard keys on the MISMATCH, not on the session.

    A healthy suspend (flag == the session's own appid) resumes exactly
    as before - this is the ordinary paused-game tap.
    """
    rig = Rig(session=SESSION, suspended=APPID, pid_states={200: 'T'},
              joystick=True).settle()
    _press(rig, 9200.0)
    rig.observe(button_down=False, press_duration=0.3)
    got = rig.observe(dt=DOUBLE_TAP_S + 0.05, button_down=False,
                      press_duration=0.3)
    assert rig.machine.regions['gesture'] == 'tap-resume'
    assert find(got, 'launch', APPID)


def test_t5_a_tap_resume_supersedes_a_legacy_kodi_guard():
    """R7(d)'s mirror (15 Aug 2026, the wrapped-Bloodborne flap): a KODI
    guard spawned by the preceding suspend was still enforcing when the
    tap-resume raised the game, and it won the last round - Kodi on top,
    game running behind, pad with the game. The resume must close the
    legacy guard exactly as a freeze does, before the launch."""
    rig = Rig(session=SESSION, suspended=APPID, pid_states={200: 'T'},
              joystick=True, guard_pid=E1_GUARD_PID).settle()
    k0 = 20500.0
    _press(rig, k0)
    rig.observe(button_down=False, press_duration=0.3)
    got = rig.observe(dt=DOUBLE_TAP_S + 0.05, button_down=False,
                      press_duration=0.3)
    assert find(got, 'launch'), verbs(got)
    kill = find(got, 'kill', 'steam-input-guard')
    assert kill, verbs(got)
    assert kill[0].args['pids'] == [E1_GUARD_PID]
    assert kill[0].args['reason'] == 'superseded-by-resume'
    order = [i.verb for i in got]
    assert order.index('kill') < order.index('launch'), 'before the resume'


def test_t5_a_resume_inside_a_kodi_window_flips_it_to_the_game():
    """R7(d)'s mirror, the region half: acting a tap-resume sets the
    enforcement target to 'game' at once, but the 'kodi' STATE could only
    leave via enf_game, which also waits on the legacy suspended flag -
    cleared ~1.1s into the resume. For that second the still-kodi region
    raised Kodi over the freshly-shown game window, twice per press."""
    rig = Rig(session=SESSION, suspended=APPID, pid_states={200: 'T'},
              joystick=True).settle()
    rig.machine.regions['enforcement'] = 'kodi'
    # The flag file is still there (game-launch clears it mid-resume), but
    # the acted resume has already flipped the target: the kodi window ends.
    rig.observe(enforcement_target='game',
                enforcement_until=rig.mono + 6.0, suspended=APPID)
    assert rig.machine.regions['enforcement'] != 'kodi'
    assert ('enforcement', 'kodi', 'game', 'resumed-mid-window') \
        in rig.transitions


def test_t5_refreezes_a_game_whose_suspend_was_undone():
    """R7(d): `freeze ... reason=reconcile:refreeze-lost-suspend`.

    Flag set, game running, Kodi on screen: nothing converged this state until
    5 Aug, which is why the 4 Aug guard-vs-freeze race stuck - the room heard
    a game it could not see and no loop repaired it.
    """
    o = make_obs(session=SESSION, suspended=APPID,
                 pid_states=_running(E1_PIDS[:4]), joystick=True,
                 top_name='Kodi', top_class='Kodi', focused_class='Kodi',
                 regions={'session': 'active', 'foreground': 'kodi'})
    got = reconcile(o)
    fr = find(got, 'freeze')
    assert fr and fr[0].reason == 'reconcile:refreeze-lost-suspend'
    assert fr[0].args['pids'] == E1_PIDS[:4]
    assert fr[0].args['resolver']
    # a game that ran on behind Kodi has a live pointer grab again
    assert find(got, 'iconify'), verbs(got)


def test_t5_but_clears_the_flag_when_the_player_is_actually_playing():
    """The other half of the same repair: what is ON SCREEN says which way to
    converge. Game on top AND focused = the flag is the wrong thing, not the
    game - and Kodi must NOT be raised over it."""
    o = make_obs(session=SESSION, suspended=APPID,
                 pid_states=_running(E1_PIDS[:4]), joystick=False,
                 top_name='ELDEN RING', top_class=E1_TOPCLS,
                 focused_class=E1_TOPCLS,
                 regions={'session': 'active', 'foreground': 'game',
                          'input_ownership': 'game'})
    got = reconcile(o)
    clear = find(got, 'clear_flag', 'suspended')
    assert clear and clear[0].reason == 'reconcile:stale-suspended-while-playing'
    assert not find(got, 'freeze'), verbs(got)
    assert not find(got, 'show', 'kodi'), 'never raise Kodi over a live game'
    assert not find(got, 'route_pad'), 'and the pad stays with the game'


def test_t5_closes_steams_desktop_overlay_after_a_tap_resume():
    """R7(f): legacy `close_steam_menu reason=desktop-overlay-after-tap` at
    02:38:41 and 02:39:09.

    In desktop UI mode (7) Steam's routing config is Desktop/413080 and never
    ClientUI, so invariant 1's original arm cannot fire and never has. What
    Steam does log is the press itself: a TAP is "sent to JS" (consumed - it
    opened the overlay), a HOLD is "skipped due to length" (it opened
    nothing), which is exactly why only the tap-resume path was ever affected.
    """
    o = make_obs(session=SESSION, ui_mode=7, focused_class='Kodi',
                 mono=5000.0, guide_consumed_at=4998.5,
                 enforcement_target='kodi', enforcement_until=5003.0,
                 regions={'enforcement': 'kodi'})
    got = find(reconcile(o), 'close_steam_menu')
    assert got, [i.key for i in reconcile(o)]
    assert got[0].reason == 'guard:desktop-overlay-after-tap'
    assert got[0].args['reason'] == 'desktop-overlay-after-tap'
    # the latch: a toggle whose cooldown outlasts the whole 6s window, so it
    # can never fire twice inside one (our own press is logged like Steam's)
    assert got[0].cooldown > 6.0


def test_t5_the_desktop_overlay_arm_waits_out_the_first_beat():
    """Steam's overlay shows up 0.3-1s after the press; a check that ran
    before the log line existed would waste the one shot on nothing."""
    o = make_obs(session=SESSION, ui_mode=7, focused_class='Kodi',
                 mono=5000.0, guide_consumed_at=4999.6,
                 enforcement_target='kodi', enforcement_until=5005.4,
                 regions={'enforcement': 'kodi'})
    assert not find(reconcile(o), 'close_steam_menu')


def test_t5_the_desktop_overlay_arm_is_desktop_mode_only():
    """In Big Picture the original ClientUI arm covers it, and firing both
    would close the menu and immediately reopen it."""
    o = make_obs(session=SESSION, ui_mode=4, focused_class='Kodi',
                 mono=5000.0, guide_consumed_at=4998.5,
                 enforcement_target='kodi', enforcement_until=5003.0,
                 regions={'enforcement': 'kodi'})
    assert not find(reconcile(o), 'close_steam_menu')
    # ...and never while the player is deliberately IN Steam
    o = replace(o, ui_mode=7, focused_class='steamwebhelper')
    assert not find(reconcile(o), 'close_steam_menu')


def test_t5_big_picture_is_ensured_before_a_game_launch():
    """R7(g): legacy `launch bigpicture reason=ensure-bp-before-game was=7`
    at 02:50:57. Steam autostarts -silent into DESKTOP mode, where the pad
    talks to an overlay the guard could never see (that is R7(f))."""
    o = make_obs(session=SESSION, ui_mode=7, joystick=False,
                 regions={'session': 'starting'})
    got = find(reconcile(o), 'launch', 'bigpicture')
    assert got, [i.key for i in reconcile(o)]
    assert got[0].args['was'] == 7
    assert got[0].args['reason'] == 'ensure-bp-before-game'
    # MODEL ONLY: the shell that is launching the game does this step and does
    # not yield it, so couchd decides it and performs nothing.
    assert got[0].model_only is True
    # already in Big Picture: legacy does nothing at all, and neither do we
    assert not find(reconcile(replace(o, ui_mode=4)), 'launch', 'bigpicture')


def test_t5_the_real_appid_is_adopted_under_a_big_picture_session():
    """R7(e): legacy `set_flag session reason=bigpicture-appid-adoption`.

    A game started from inside Big Picture leaves the session line's appid
    field EMPTY, so every consumer works on the string "bigpicture" - which on
    5 Aug made the game's own Kodi tile read a running game as "a different
    game was picked", closed it and relaunched it. The operator lost his
    progress to that.
    """
    o = make_obs(session=BP_SESSION, ledger={APPID: (200,)},
                 pid_states={200: 'S'}, joystick=False,
                 regions={'session': 'active'})
    got = find(reconcile(o), 'set_flag', 'session')
    assert got, [i.key for i in reconcile(o)]
    assert got[0].args['value'] == f'{BP_SESSION["launcher_pid"]} steam {APPID}'
    assert got[0].args['reason'] == 'bigpicture-appid-adoption'
    assert got[0].model_only is True
    # a session that already names its appid needs no adoption
    o2 = make_obs(session=SESSION, ledger={APPID: (200,)},
                  pid_states={200: 'S'}, joystick=False,
                  regions={'session': 'active'})
    assert not find(reconcile(o2), 'set_flag', 'session')


def test_model_only_intents_are_never_performed():
    """The safety half of the two catch-ups above: they are decisions couchd
    RECORDS, and the acting executor cannot perform them even when it owns the
    responsibility they are tagged with."""
    from couchd import ActingExecutor, ShadowLog
    import types
    log = types.SimpleNamespace(written=[], counts={})
    log.write = log.written.append
    said = []
    ex = ActingExecutor(log, actuators=None, owned=('transitions',),
                        sayer=said.append)
    o = make_obs(session=SESSION, ui_mode=7, joystick=False,
                 regions={'session': 'starting'})
    it = find(reconcile(o), 'launch', 'bigpicture')[0]
    rec = ex.execute(it, o)
    assert rec['acted'] is False
    assert rec['action']['ok'] is True and 'model_only' in rec['action']
    assert ex.count == 0 and ex.failures == 0
    assert not said, 'not a failure and not a refusal: nothing to say'


# =========================================================================
# the guide press is a TOGGLE (T4-1, from the Evening-1 replay)
#
# The handoff used to press it on every hold-release. Legacy does not: its
# handoff spawns steam-input-guard, whose invariant 1 reads the routing log
# first. Evening 1: couchd 21 emissions, legacy 11, one match - so post-flip
# roughly ten handoffs in twenty-one would have OPENED the Steam menu over
# the Kodi the gesture exists to return to.
# =========================================================================
#: Steam's own routing line when the menu has the pad (Evening-1 corpus)
MENU_ROUTE = ('OnFocusWindowChanged to window type: '
              'k_nGameIDControllerConfigs_ClientUI, AppID 769')


def _release(rig, k0=30000.0, **world):
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0, **world)
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 0.95,
                **world)
    return rig.observe(button_down=False, press_duration=1.1, **world)


def test_t4_1_the_handoff_presses_guide_only_when_the_menu_is_open():
    rig = Rig(session=SESSION, pid_states=_running(E1_PIDS), joystick=False,
              top_name='ELDEN RING', top_class=E1_TOPCLS).settle()
    got = _release(rig, suspended=APPID, pid_states=_running(E1_PIDS, 'T'),
                   steam_route=MENU_ROUTE, focused_class='Kodi')
    press = find(got, 'close_steam_menu')
    assert press, verbs(got)
    assert 'ClientUI' in press[0].args['route']
    assert press[0].cooldown > float(press[0].predict['deadline_s'])


def test_t4_1_a_closed_menu_gets_no_guide_press_at_all():
    rig = Rig(session=SESSION, pid_states=_running(E1_PIDS), joystick=False,
              top_name='ELDEN RING', top_class=E1_TOPCLS).settle()
    got = _release(rig, suspended=APPID, pid_states=_running(E1_PIDS, 'T'),
                   steam_route='', focused_class='Kodi')
    assert find(got, 'route_pad', 'kodi'), 'the handoff itself is unchanged'
    assert find(got, 'show', 'kodi')
    assert not find(got, 'close_steam_menu'), verbs(got)


def test_t4_1_an_unreadable_steam_log_is_unknown_not_closed():
    """A toggle fired on an unknown state is a coin flip with the screen."""
    rig = Rig(session=SESSION, pid_states=_running(E1_PIDS), joystick=False,
              top_name='ELDEN RING', top_class=E1_TOPCLS).settle()
    got = _release(rig, suspended=APPID, pid_states=_running(E1_PIDS, 'T'),
                   steam_route=MENU_ROUTE, steam_known=False)
    assert not find(got, 'close_steam_menu'), verbs(got)


def test_t4_1_steam_focused_means_the_player_chose_steam():
    """Closing a menu the player deliberately opened would be rude, and it is
    the same clause legacy's guard uses."""
    o = make_obs(regions={'gesture': 'handoff-pending'},
                 steam_route=MENU_ROUTE, focused_class='steamwebhelper')
    assert not find(reconcile(o), 'close_steam_menu')


def test_t4_1_the_guard_window_still_catches_a_menu_steam_opens_late():
    """Steam opens its menu ~0.3-1s after the press, i.e. after the handoff
    has already been decided. That is what the enforcement window is for, and
    it is the reason gating the handoff's own press loses nothing."""
    o = make_obs(regions={'enforcement': 'kodi'}, steam_route=MENU_ROUTE,
                 focused_class='Kodi')
    got = find(reconcile(o), 'close_steam_menu')
    assert got and got[0].reason == 'guard:steam-menu-holds-the-pad'


# =========================================================================
# one repair, one cadence (T4-3)
# =========================================================================
def test_t4_3_the_refreeze_and_its_iconify_share_a_cooldown():
    """9 freezes against 48 iconifies over one Evening-1 episode: the pair
    had cooldowns 6x apart, so it stopped behaving as one decision."""
    o = make_obs(session=SESSION, suspended=APPID,
                 pid_states=_running(E1_PIDS[:4]), joystick=True,
                 top_name='Kodi', top_class='Kodi', focused_class='Kodi',
                 regions={'session': 'active', 'foreground': 'kodi'})
    got = reconcile(o)
    freeze = find(got, 'freeze')[0]
    icon = find(got, 'iconify')[0]
    assert icon.cooldown == freeze.cooldown == REPAIR_COOLDOWN


def test_t4_3_the_handoffs_iconify_rides_with_its_route_and_show():
    rig = Rig(session=SESSION, pid_states=_running(E1_PIDS), joystick=False,
              top_name='ELDEN RING', top_class=E1_TOPCLS).settle()
    got = _release(rig, suspended=APPID, pid_states=_running(E1_PIDS, 'T'))
    icon = find(got, 'iconify')[0]
    assert icon.cooldown == find(got, 'route_pad', 'kodi')[0].cooldown
    assert icon.cooldown == find(got, 'show', 'kodi')[0].cooldown


def test_t4_3_the_repair_thaw_and_its_deiconify_share_a_cooldown():
    o = make_obs(session=SESSION, suspended=None,
                 pid_states=_running(E1_PIDS[:3], 'T'), joystick=False,
                 regions={'session': 'active', 'input_ownership': 'game'})
    got = reconcile(o)
    thaw = find(got, 'thaw')[0]
    back = [i for i in find(got, 'show', APPID)
            if i.args.get('reason') == 'deiconify'][0]
    assert back.cooldown == thaw.cooldown == REPAIR_COOLDOWN


# =========================================================================
# COALESCED EDGES: a double-tap the passes did not see in pieces
#
# The region is SAMPLED and the button is not. Two edges landing between two
# passes leave the machine looking at the last one only, so the path a real
# double-tap walks depends on how the presses fell relative to the 50ms
# debounce - which is sampling luck, not something the player did.
#
# Live proof, 5 Aug 13:57:11.5 (the owner's own double-tap, 48ms between
# tap-1's release and tap-2's press): latency record edge_seq 19,
# coalesced:1, no intent, machine stuck in 'down', while the yielded watcher
# recorded that legacy would have opened the switcher. Measured boundary:
# >=120ms fired, 48ms did not.
#
# The table now asks the tracker (SR4's single source of truth) from every
# state with a press in flight, so the gap between the two taps no longer
# decides whether the gesture exists.
# =========================================================================
def _edges(rig, taps, gap, length=0.1, lengths=None, k0=40000.0, **world):
    """Drive `taps` presses `gap` apart, coalescing any pair of edges that
    lands inside one pass - exactly what the daemon's debounce does.

    A pass is emitted per PASS, not per edge: edges closer together than the
    debounce arrive at the machine as one observation, which is the whole
    bug. `gap` is release-to-next-press, in seconds.
    """
    out = []
    k = k0
    pending = []                     # edges not yet shown to the machine
    for n in range(taps):
        pending.append(('down', k))
        k += (lengths[n] if lengths else length)
        pending.append(('up', k))
        k += gap
    # group edges into passes: an edge opens a pass, everything inside
    # DEBOUNCE of it rides along
    passes, cur = [], []
    for kind, t in pending:
        if not cur or t - cur[0][1] < couchd.EDGE_DEBOUNCE:
            cur.append((kind, t))
        else:
            passes.append(cur)
            cur = [(kind, t)]
    if cur:
        passes.append(cur)
    tracker = gesture.PressTracker()
    for group in passes:
        for kind, t in group:
            tracker.feed(t, 1 if kind == 'down' else 0, mono=t)
        last_t = group[-1][1]
        out.append(rig.observe(
            dt=max(0.05, last_t - (rig.mono - 1000.0) - 40000.0 + 0.05),
            button_down=tracker.button_down,
            down_since_k=tracker.down_since_k,
            kernel_now=last_t,
            press_duration=tracker.press_duration,
            double_armed=tracker.double_armed, **world))
    return out


def _switcher_fired(passes):
    return any(find(p, 'show_switcher') for p in passes)


def test_a_double_tap_with_a_120ms_gap_fires_the_switcher():
    """The gap that always worked: every edge got its own pass, so the machine
    walked idle->down->tap-wait->down-again->double-tap."""
    rig = Rig(joystick=True).settle()
    assert _switcher_fired(_edges(rig, 2, gap=0.120))
    assert rig.machine.regions['gesture'] in ('double-tap', 'idle')


def test_a_double_tap_with_the_owners_48ms_gap_fires_it_too():
    """13:57:11.5, the press that was silently dropped: tap-1's release and
    tap-2's press coalesce, the machine never leaves 'down', and the release
    used to fall through to ps-tap-noop."""
    rig = Rig(joystick=True).settle()
    passes = _edges(rig, 2, gap=0.048)
    assert _switcher_fired(passes), [verbs(p) for p in passes]
    assert ('gesture', 'down', 'double-tap', 'ps-double-tap-coalesced') \
        in rig.transitions


def test_a_double_tap_whose_taps_share_one_pass_entirely_fires_it():
    """0ms gap: both edges of tap-2 land in the same pass as each other."""
    rig = Rig(joystick=True).settle()
    passes = _edges(rig, 2, gap=0.0, length=0.04)
    assert _switcher_fired(passes), [verbs(p) for p in passes]


def test_a_second_tap_that_lands_whole_inside_one_pass_fires_it():
    """The same hazard one step later: tap-1 walked into 'tap-wait' normally,
    then tap-2's press AND release both landed between two passes, so the
    machine never entered 'down-again' either."""
    rig = Rig(joystick=True).settle()
    passes = _edges(rig, 2, gap=0.06, lengths=[0.09, 0.04])
    assert _switcher_fired(passes), [verbs(p) for p in passes]
    assert ('gesture', 'tap-wait', 'double-tap', 'ps-double-tap-coalesced') \
        in rig.transitions


def test_a_first_tap_shorter_than_the_debounce_is_a_KNOWN_residual():
    """The one case this fix does NOT close, pinned so it cannot rot quietly.

    If tap-1's press and release BOTH land inside one pass, no pass ever sees
    the button down, the machine never leaves 'idle', and there is no press in
    flight for the tracker's arming to attach to. Closing it means firing a
    double-tap from 'idle' - and `double_armed` stays set after a release, so
    an idle machine carrying a stale arming would fire the switcher again for
    free. That trade is not worth it at these numbers: it needs BOTH taps
    under the 50ms debounce, and the fastest real tap in the whole corpus is
    69ms against a 350ms double-tap window.

    If it ever does bite, the fix is a one-shot the tracker owns (a
    consumed-doubles counter on Observed), not a freshness window here.
    """
    rig = Rig(joystick=True).settle()
    passes = _edges(rig, 2, gap=0.06, length=0.04)
    assert not _switcher_fired(passes)
    assert rig.machine.regions['gesture'] == 'idle', 'never entered a gesture'


def test_the_double_tap_boundary_is_the_tracker_not_the_sampling():
    """The whole point, as one assertion: across every gap from 'same pass'
    to comfortably-apart, the SAME physical gesture produces the same
    decision. Below DOUBLE_TAP_S it is a double-tap; above it, it is not."""
    for gap in (0.0, 0.03, 0.048, 0.08, 0.12, 0.2, 0.3):
        rig = Rig(joystick=True).settle()
        assert _switcher_fired(_edges(rig, 2, gap=gap)), f'gap {gap}s'
    rig = Rig(joystick=True).settle()
    assert not _switcher_fired(_edges(rig, 2, gap=0.5)), 'past the window'


def test_a_rapid_triple_tap_opens_the_switcher_exactly_once():
    """13:57:05, and the semantics pinned deliberately.

    The tracker closes a double-tap window when it USES it, so three taps are
    one double plus one single - and a fourth tap re-arms against the third.
    couchd trusts that (it is legacy's `last_tap_at` rule, in gesture.py), and
    what stops the burst re-firing the dialog is the switcher intent's own 3s
    cooldown: the region may bounce through 'double-tap' again, the DECISION
    happens once. Legacy reaches the same end through its 1.2s settle window,
    which couchd does not model - a declared gap, not this bug.
    """
    rig = Rig(joystick=True).settle()
    passes = _edges(rig, 4, gap=0.06, length=0.07)
    fired = [i for p in passes for i in find(p, 'show_switcher')]
    assert len(fired) == 1, [verbs(p) for p in passes]


def test_a_coalesced_double_tap_still_suspends_a_running_game_first():
    """The dialog is Kodi's, so the suspend half must survive the fix."""
    rig = Rig(session=SESSION, pid_states={200: 'S'}, joystick=False,
              top_name='ELDEN RING', top_class=E1_TOPCLS).settle()
    passes = _edges(rig, 2, gap=0.048)
    flat = [i for p in passes for i in p]
    assert [(i.verb, i.subject) for i in flat if i.verb in
            ('freeze', 'show_switcher')] == [('freeze', APPID),
                                             ('show_switcher', 'tv')]


def test_a_stale_arming_can_never_fire_from_an_idle_machine():
    """`double_armed` stays set through a release, so the guard is only safe
    where a press has happened since the machine arrived. 'idle' is
    deliberately NOT one of those states."""
    o = make_obs(regions={'gesture': 'idle'}, double_armed=True,
                 press_duration=0.08, button_down=False)
    m = Machine()
    m.regions.update(o.regions)
    m.step(o)
    assert m.regions['gesture'] == 'idle'
    assert not find(reconcile(o), 'show_switcher')


# =========================================================================
# a hold with no session decides NOTHING (bug 3)
# =========================================================================
def test_a_hold_with_no_session_emits_no_handoff():
    """pad-home-watcher.hold_ready() returns os.path.exists(SESSION) for
    suspend_to_kodi, so legacy never spends the hold at all. couchd used to
    emit the full handoff regardless - idempotent on a Kodi screen, but from
    the desktop it would raise Kodi where the old stack did nothing."""
    o = make_obs(regions={'gesture': 'handoff-pending', 'session': 'none'},
                 session=None, top_name='Thunar', top_class='Thunar')
    assert reconcile(o) == []


def test_a_hold_with_a_session_still_hands_off():
    o = make_obs(session=SESSION, regions={'gesture': 'handoff-pending',
                                           'session': 'active'})
    got = reconcile(o)
    assert find(got, 'route_pad', 'kodi') and find(got, 'show', 'kodi')


def test_the_timeout_arm_is_gated_the_same_way():
    o = make_obs(regions={'gesture': 'timed-out', 'session': 'none'},
                 session=None)
    assert reconcile(o) == []


# =========================================================================
# ...EXCEPT a session-less Big Picture, ruled 7 Aug 2026: Steam's shell
# raised itself (off the raw PS presses, or left over after a session
# ended), there is no session file, and the operator is stuck - the old
# stack's hold_ready() never spends the hold at all there. Donnie ruled the
# hold must hand the room back to Kodi on exactly this screen; the desktop
# case above stays a no-op.
# =========================================================================
def test_a_hold_on_a_sessionless_big_picture_hands_off():
    o = make_obs(regions={'gesture': 'handoff-pending', 'session': 'none',
                          'foreground': 'bigpicture'},
                 session=None, top_name='Steam Big Picture Mode',
                 top_class='steam', big_picture_window=True)
    got = reconcile(o)
    assert find(got, 'route_pad', 'kodi') and find(got, 'show', 'kodi')
    # ...under its own reason, so the differ's pre-declared entry can key on
    # it (legacy writes no shadow line at all for this hold).
    assert all('bp-return' in i.reason for i in
               find(got, 'route_pad') + find(got, 'show'))
    # NO flag: stamping "bigpicture" with no session armed every later tap
    # into "resume big picture" (the trap that stuck the operator on BP).
    assert not find(got, 'set_flag', 'suspended')


def test_a_sessionless_big_picture_hold_fire_writes_no_flag():
    """The hold-fired half (flag write deferred-handoff) must also stay
    silent: it used to stamp /tmp/game-suspended = "bigpicture" off the
    foreground region alone, which legacy never does without a session."""
    o = make_obs(regions={'gesture': 'hold-fired', 'session': 'none',
                          'foreground': 'bigpicture'},
                 session=None, top_name='Steam Big Picture Mode',
                 top_class='steam', big_picture_window=True)
    assert not find(reconcile(o), 'set_flag', 'suspended')


def test_a_real_bigpicture_session_hold_still_writes_the_flag():
    """R7(a) unchanged where it was right: WITH a bigpicture session the
    flag is recorded, so the joystick repair can never decide the pad
    belongs to an invisible Big Picture."""
    o = make_obs(session=BP_SESSION,
                 regions={'gesture': 'hold-fired', 'session': 'active',
                          'foreground': 'bigpicture'},
                 top_name='Steam Big Picture Mode', top_class='steam',
                 big_picture_window=True)
    flag = find(reconcile(o), 'set_flag', 'suspended')
    assert flag and flag[0].args['value'] == 'bigpicture'


# =========================================================================
# the transition curtain (deploy item 1, 6 Aug 2026)
#
# tools/curtain draws a freeze-frame overlay (WM_CLASS couch-curtain) over
# the suspend/resume window shuffle. By construction it is an unknown
# fullscreen window on top of the console - exactly the shape the guards
# read as drift - so the classifier and every screen-reading repair must
# treat it as "a transition being hidden", never as something to fight.
# =========================================================================
CURTAIN_TOP = dict(top_name=couchd.CURTAIN_CLASS,
                   top_class=couchd.CURTAIN_CLASS)


def test_curtain_classifies_as_transition_overlay_not_other():
    rig = Rig().settle()
    rig.observe(**CURTAIN_TOP)
    assert rig.machine.regions['foreground'] == 'curtain'
    assert ('foreground', 'kodi', 'curtain',
            'transition-curtain-on-top') in rig.transitions
    # it settles there (no flap to 'other') while the overlay is up...
    rig.observe(**CURTAIN_TOP)
    assert rig.machine.regions['foreground'] == 'curtain'
    # ...and drops back to what the fade reveals
    rig.observe()
    assert rig.machine.regions['foreground'] == 'kodi'


def test_curtain_is_reachable_from_other_and_vice_versa():
    rig = Rig().settle()
    rig.observe(top_name='Thunar', top_class='Thunar')
    assert rig.machine.regions['foreground'] == 'other'
    rig.observe(**CURTAIN_TOP)
    assert rig.machine.regions['foreground'] == 'curtain'
    rig.observe(top_name='Thunar', top_class='Thunar')
    assert rig.machine.regions['foreground'] == 'other'


def test_guard_tolerates_the_curtain_over_its_kodi_window():
    """guard:wanted-window-not-on-top must not restack Kodi against the
    overlay that is covering the very handoff the guard window belongs to
    (the curtain re-raises itself; that fight has no winner)."""
    o = make_obs(regions={'enforcement': 'kodi', 'foreground': 'curtain'},
                 **CURTAIN_TOP)
    assert not find(reconcile(o), 'show', 'kodi'), verbs(reconcile(o))
    # ...and the guard is NOT weakened: any other unexpected window still
    # gets repaired exactly as before.
    o2 = make_obs(top_name='Steam', top_class='steamwebhelper',
                  regions={'enforcement': 'kodi', 'foreground': 'other'})
    got = find(reconcile(o2), 'show', 'kodi')
    assert got and got[0].reason == 'guard:wanted-window-not-on-top'


def test_refreeze_repair_holds_off_under_the_curtain():
    """Flag set + pids running is what the MIDDLE of a curtained transition
    looks like (a suspend's freeze in flight; a resume that thaws before it
    clears the flag - the reconcile-flip hard gate). The repair pair reads
    WHAT IS ON SCREEN to pick a direction, and the screen is covered: hold
    off, and re-decide the pass after the curtain drops."""
    o = make_obs(session=SESSION, suspended=APPID,
                 pid_states=_running(E1_PIDS[:4]), joystick=True,
                 focused_class='Kodi',
                 regions={'session': 'active', 'foreground': 'curtain'},
                 **CURTAIN_TOP)
    got = reconcile(o)
    assert not find(got, 'freeze'), verbs(got)
    assert not find(got, 'clear_flag', 'suspended'), verbs(got)
    assert not find(got, 'iconify'), verbs(got)
    # the same world with the curtain gone still repairs (regression guard)
    o2 = replace(o, top_name='Kodi', top_class='Kodi')
    assert find(reconcile(o2), 'freeze')


def test_frozen_game_under_the_curtain_is_not_repaired_visible():
    """A frozen game covered by the curtain is mid-suspend, not 'what the
    room is looking at': neither the reconcile repair nor guard invariant 3
    may fire while the overlay is the top window."""
    o = make_obs(session=SESSION, suspended=APPID, pid_states={200: 'T'},
                 regions={'session': 'active', 'foreground': 'curtain',
                          'enforcement': 'kodi'},
                 **CURTAIN_TOP)
    assert not find(reconcile(o), 'show', 'kodi'), verbs(reconcile(o))


def test_curtain_does_not_mark_the_game_window_missing():
    """MISSING_WINDOW keys off 'processes but no game window on screen';
    a curtain covering a freshly resumed game must not read as that."""
    m = Machine()
    base = dict(session=SESSION, ledger={APPID: (200,)}, pid_states={200: 'S'},
                joystick=False)
    m.step(make_obs(mono=1000.0, top_name='ELDEN RING', top_class=E1_TOPCLS,
                    **base))
    assert m.games[APPID] == 'RUNNING'
    m.step(make_obs(mono=1010.0, **CURTAIN_TOP, **base))
    assert m.games[APPID] == 'RUNNING', 'curtain is a transition, not a loss'
    # ...and the grace path still works once the screen is genuinely wrong
    m.step(make_obs(mono=1020.0, top_name='Thunar', top_class='Thunar',
                    **base))
    assert m.games[APPID] == 'MISSING_WINDOW'


def test_bigpicture_tap_resume_predicts_a_window_not_pids():
    """The bigpicture pseudo-app has no game pids to come back, so its
    resume launch predicts the observable effect - Big Picture's shell on
    top - instead of 'game pids back in state S' (which verdicted an honest
    resume MISSED on the acceptance night, 03:48)."""
    o = make_obs(session=BP_SESSION, suspended='bigpicture',
                 regions={'session': 'active', 'gesture': 'tap-resume'})
    got = find(reconcile(o), 'launch')
    assert got and got[0].subject == 'bigpicture'
    assert got[0].predict['effect'] == 'big picture window on top'
    # a real game's resume still predicts pids (unchanged)
    o2 = make_obs(session=SESSION, suspended=APPID, pid_states={200: 'T'},
                  regions={'session': 'active', 'gesture': 'tap-resume'})
    got2 = find(reconcile(o2), 'launch')
    assert got2 and got2[0].predict['effect'] == 'game pids back in state S'


# =========================================================================
# the reconcile-flip hard gate: flag/pid drift must PERSIST before repair
# (FLAG_DRIFT_PERSIST_S, 6 Aug 2026)
# =========================================================================
# game-launch clears /tmp/game-suspended BEFORE its SIGCONTs on every resume
# path, so any flag/pid disagreement that lives for under a second is a
# transition's critical section, not drift. The acceptance night's 3x shadow
# `would freeze [reconcile:refreeze-lost-suspend]` (03:18/03:33/03:42) was
# the model deciding inside the OLD ordering's gap - acted, a SIGSTOP
# mid-resume. Machine._track_drift stamps first sightings; the repairs
# require them to be FLAG_DRIFT_PERSIST_S old. A None clock (hand-built
# Observed, or a daemon plumbing regression) reads "held forever" so every
# test above this section keeps its old meaning.
def _drift_world(**kw):
    """The refreeze shape: flag set, game running, Kodi on screen."""
    base = dict(session=SESSION, suspended=APPID,
                pid_states=_running(E1_PIDS[:4]), joystick=True,
                top_name='Kodi', top_class='Kodi', focused_class='Kodi',
                regions={'session': 'active', 'foreground': 'kodi'})
    base.update(kw)
    return make_obs(**base)


def test_refreeze_waits_out_a_resume_transient():
    """A fresh suspended-running clock is a resume mid-flight, not drift."""
    o = _drift_world(suspended_running_since=999.5)      # 0.5s ago (mono 1000)
    got = reconcile(o)
    assert not find(got, 'freeze'), verbs(got)
    assert not find(got, 'iconify'), verbs(got)          # the pair stands down


def test_refreeze_fires_once_the_drift_has_persisted():
    o = _drift_world(suspended_running_since=1000.0 - couchd.FLAG_DRIFT_PERSIST_S)
    fr = find(reconcile(o), 'freeze')
    assert fr and fr[0].reason == 'reconcile:refreeze-lost-suspend'


def test_stale_while_playing_shares_the_refreeze_debounce():
    """One condition, one clock: the tie-breaker (what is on screen) decides
    the direction, but neither direction repairs a sub-second disagreement."""
    o = _drift_world(top_name='ELDEN RING', top_class='steam_app_367520',
                     focused_class='steam_app_367520',
                     regions={'session': 'active', 'foreground': 'game'},
                     suspended_running_since=999.5)
    assert not find(reconcile(o), 'clear_flag', 'suspended')
    o = replace(o, suspended_running_since=996.0)
    got = find(reconcile(o), 'clear_flag', 'suspended')
    assert got and got[0].reason == 'reconcile:stale-suspended-while-playing'


def test_lost_thaw_repair_waits_out_a_resume_transient():
    """Frozen-without-flag for half a second IS the resume (flag cleared,
    SIGCONTs milliseconds away); the net stays quiet."""
    o = make_obs(session=SESSION, suspended=None,
                 pid_states={200: 'T', 201: 'T'}, joystick=False,
                 regions={'session': 'active', 'input_ownership': 'game'},
                 frozen_noflag_since=999.6)
    got = reconcile(o)
    assert not find(got, 'thaw'), verbs(got)
    o = replace(o, frozen_noflag_since=997.0)
    got = find(reconcile(o), 'thaw')
    assert got and got[0].args['pids'] == [200, 201]


def test_guard_invariant_4_shares_the_lost_thaw_debounce():
    o = make_obs(session=SESSION, pid_states={5: 'T', 6: 'T'}, joystick=False,
                 regions={'enforcement': 'game', 'session': 'active',
                          'input_ownership': 'game'},
                 frozen_noflag_since=999.6)
    got = [i for i in reconcile(o) if i.reason.startswith('guard:')]
    assert not [i for i in got if i.verb == 'thaw'], got
    o = replace(o, frozen_noflag_since=997.0)
    got = find(reconcile(o), 'thaw')
    assert got and got[0].reason == 'guard:all-frozen-without-flag'


def test_an_untracked_clock_keeps_the_old_behaviour():
    """None = no tracking info: hand-built worlds (every test above) and a
    daemon that forgot the plumbing fail OPEN to the pre-debounce repairs."""
    o = _drift_world()                                   # since fields None
    assert find(reconcile(o), 'freeze')


def test_machine_tracks_the_flag_drift_clocks():
    m = Machine()
    o = make_obs(mono=100.0, session=SESSION, suspended=APPID,
                 pid_states={200: 'S'})
    m.step(o)
    assert m.drift_since['suspended_running'] == 100.0
    assert m.drift_since['frozen_noflag'] is None
    m.step(replace(o, mono=105.0))                       # first sighting kept
    assert m.drift_since['suspended_running'] == 100.0
    o2 = make_obs(mono=106.0, session=SESSION, suspended=None,
                  pid_states={200: 'T'})
    m.step(o2)
    assert m.drift_since['suspended_running'] is None
    assert m.drift_since['frozen_noflag'] == 106.0
    m.step(make_obs(mono=107.0, session=SESSION, pid_states={200: 'S'}))
    assert m.drift_since['frozen_noflag'] is None


def test_a_bigpicture_flag_never_starts_the_refreeze_clock():
    """A Big Picture suspend has no pids to freeze BY DESIGN (R7(a)): pids
    running under a 'bigpicture' flag are not the refreeze condition, so the
    clock must not run on them either."""
    m = Machine()
    m.step(make_obs(mono=100.0, session=BP_SESSION, suspended='bigpicture',
                    pid_states={200: 'S'}))
    assert m.drift_since['suspended_running'] is None


TestConsoleModel = ConsoleModel.TestCase
TestConsoleModel.settings = settings(
    max_examples=60, stateful_step_count=40, deadline=None,
    suppress_health_check=[HealthCheck.too_slow])


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))


def test_a_same_batch_freeze_still_iconifies_the_frozen_window():
    """23 Aug, first Steam title after the stage-2 flip: the tap's handoff
    checked the OBSERVED frozen flags, which are still false in the batch
    that itself carries the freeze - so the iconify was dropped, the frozen
    window stayed mapped, Steam's focus routing flapped over it, and Steam
    Input's mirror pad fed Kodi a second copy of every press. The batch
    knows it is freezing; the iconify must ride along."""
    o = make_obs(session=SESSION, pid_states={200: 'S'}, joystick=False,
                 regions={'gesture': 'tap-fired', 'session': 'active',
                          'input_ownership': 'game', 'foreground': 'game'},
                 top_name='Hollow Knight', top_class='steam_app_367520',
                 bindings=bind(tap='home'))
    got = action_intents(o, 'tap', APPID, [200], defer_handoff=False)
    order = verbs(got)
    assert ('freeze', APPID) in order
    assert ('iconify', APPID) in order, (
        'the handoff dropped the iconify because suspended_present/frozen '
        'are observed-state and this batch does the freezing itself')
    assert order.index(('iconify', APPID)) > order.index(('snapshot', APPID)), (
        'iconify frees the compositing pixmap the freeze-frame is read from')


def test_a_whole_tap_swallowed_by_one_pass_still_resumes_the_game():
    """Press AND release of an ordinary ~100ms tap inside one pass gap: the
    machine sat in idle throughout and the tap used to vanish - five in a
    row eaten live at a frozen Hollow Knight (23 Aug, stage-2 flip night).
    Unlike the hold/double variants this needs no stall: human taps run
    90-145ms and a pass costs 50-130ms, so the coin flips on every tap. The
    tracker's consumable marker (tap_pending) carries the decision, and the
    machine resumes life in tap-wait exactly as if it had seen the press."""
    rig = Rig(session=SESSION, suspended=APPID, pid_states={200: 'T'},
              joystick=True).settle()
    got = rig.observe(button_down=False, press_duration=0.09,
                      tap_pending=True)
    assert rig.machine.regions['gesture'] == 'tap-wait', \
        'the swallowed tap must land where a seen tap goes'
    assert not find(got, 'launch'), 'the double-tap window still applies'
    # the daemon consumes the marker on the tap-wait transition; the window
    # then expires and the deferred resume fires exactly as for a seen tap
    got = rig.observe(dt=DOUBLE_TAP_S + 0.05, button_down=False,
                      press_duration=0.09, tap_pending=False)
    assert rig.machine.regions['gesture'] == 'tap-resume'
    launch = find(got, 'launch')
    assert launch and launch[0].args['mode'] == 'resume'
    # ...and a spent marker must not re-fire from idle
    rig.observe(button_down=False, press_duration=0.09, tap_pending=False)
    rig.observe(button_down=False, press_duration=0.09, tap_pending=False)
    assert rig.machine.regions['gesture'] == 'idle'


def test_the_tracker_sets_and_spends_the_tap_marker():
    """SR4: the marker is the tracker's decision, in kernel time - set at a
    TAP, superseded by a new press, spent by consume_tap()."""
    t = gesture.PressTracker()
    t.feed(1000.0, 1, wall=500.0)
    assert t.tap_k is None
    t.feed(1000.1, 0, wall=500.1)
    assert t.tap_k is not None, 'a completed tap arms the marker'
    t.consume_tap()
    assert t.tap_k is None
    # a hold never arms it
    t.feed(1002.0, 1, wall=502.0)
    t.feed(1003.5, 0, wall=503.5)
    assert t.tap_k is None


def test_the_local_emulator_build_is_seen_as_the_game():
    """23 Aug, live, and it cost a Bloodborne death: the pid resolver knew
    only the AppImage names, so a LOCAL-BUILD session read as zero processes.
    The escape gesture's freeze branch is `if session and running`, so with
    running empty the switcher took the screen and the game played on
    underneath it with the pad still pointed at it.

    game-pids learned this on 22 Aug; couchd's in-process port did not, which
    is exactly why the shapes now live behind ONE predicate."""
    from couchd import is_emulator_cmd, SHAD_LOCAL
    assert is_emulator_cmd(SHAD_LOCAL)
    assert is_emulator_cmd(
        f'{SHAD_LOCAL} -f true -g /home/ds2000/games/ps4/CUSA00900/eboot.bin')
    # the AppImage shapes still match
    assert is_emulator_cmd('/tmp/.mount_Shadps4abc/AppRun')
    assert is_emulator_cmd('/home/ds2000/Apps/Shadps4-sdl.AppImage')
    # ...and nothing else does. The last one is the pgrep-self-match trap:
    # a command that merely MENTIONS the binary is not the binary.
    assert not is_emulator_cmd('/usr/bin/kodi.bin')
    assert not is_emulator_cmd('')
    assert not is_emulator_cmd(f'tail -F {SHAD_LOCAL}.log')
    assert not is_emulator_cmd(f'grep -n x {SHAD_LOCAL}')


def test_a_running_local_build_is_frozen_by_the_switcher_gesture():
    """The failure end to end: session live, emulator processes present, the
    switcher gesture MUST freeze before it takes the screen."""
    o = make_obs(session={'launcher_pid': 111, 'mode': 'shadps4',
                          'appid': '/home/ds2000/games/ps4/CUSA00900/eboot.bin',
                          'raw': '111 shadps4 eboot.bin'},
                 pid_states={900: 'S'}, joystick=False,
                 regions={'gesture': 'tap-fired', 'session': 'active',
                          'input_ownership': 'game', 'foreground': 'game'},
                 top_name='shadPS4', top_class='shadps4',
                 bindings=bind(tap='switcher'))
    got = action_intents(o, 'tap', '/home/ds2000/games/ps4/CUSA00900/eboot.bin',
                         [900], defer_handoff=False)
    order = verbs(got)
    assert ('freeze', '/home/ds2000/games/ps4/CUSA00900/eboot.bin') in order, (
        'the switcher took the screen without freezing the game: %s' % order)
    assert order.index(('freeze',
                        '/home/ds2000/games/ps4/CUSA00900/eboot.bin')) \
        < order.index(('show_switcher', 'tv')), 'freeze before the dialog'


# =========================================================================
# tap-as-switcher: the press must not resume the game it just paused
# =========================================================================
TAP_SWITCHER = dict(DEFAULT_BINDINGS, tap='switcher', double_tap='none')


def test_a_tap_that_opens_the_switcher_does_not_then_resume_the_game():
    """Donnie, 24 Aug 2026: "stop when i'm on a game it keeps switching to
    kodi and stuff and sometimes when i go off a game it's just sat open".

    Both are one bug, and it arrived with the 23 Aug rebind that moved the
    switcher onto the TAP and unbound the double-tap.

    A tap on a running game fires the bound `switcher` action: freeze, flag,
    snapshot, hand the pad and screen to Kodi, open the dialog. That action
    sets /tmp/game-suspended - and 350ms later g_tap_resume_due looked at the
    world, saw a paused game and a tap, and resumed it. THE SAME PRESS. The
    game came back on top of the switcher that was still opening, which is
    exactly what the room saw: a flip to Kodi and straight back, and a dialog
    left sitting open underneath, discovered whenever the game finally exited.

    Live evidence, shadow/couchd-20260823.jsonl at 22:07:10:

        .156 gesture idle -> down        ps-press
        .207 gesture down -> tap-wait    ps-tap-noop
        .207 freeze/set_flag/.../show_switcher      gesture:ps-tap
        .558 gesture tap-wait -> tap-resume  paused-tap-window-expired
        .558 launch resume + show game          gesture:tap-resume
       1.249 show_switcher CONFIRMED - foreground already back on the game

    gesture.paused_tap_decision has always said an unpaused tap never reaches
    the deferral at all; this pins couchd to that.
    """
    rig = Rig(session=SESSION, pid_states={200: 'S', 201: 'S'}, joystick=False,
              bindings=TAP_SWITCHER,
              top_name='Bloodborne', top_class='steam_app_367520').settle()
    k0 = 12800.0
    got = _tap(rig, k0)
    # the tap IS the switcher now, so it acts at once
    assert find(got, 'show_switcher'), 'the tap should open the switcher'
    assert find(got, 'freeze'), 'and suspend the game first'
    assert rig.machine.regions['gesture'] == 'tap-wait'

    # ...and now the world reports what that batch just did. press_duration
    # is carried the way the real tracker carries it: a completed press stays
    # readable until the next one (gesture.Tracker.reset is the only thing
    # that clears it), which is exactly why a level-based reader can walk the
    # tap paths again on a later pass.
    extra = []
    for _ in range(6):
        got = rig.observe(dt=0.2, suspended=APPID, press_duration=0.08,
                          pid_states={200: 'T', 201: 'T'})
        assert not find(got, 'launch'), (
            'the press resumed the game it had just paused: %s' % verbs(got))
        extra += got
    assert rig.machine.regions['gesture'] != 'tap-resume'
    # And the press must go quiet rather than park somewhere that keeps
    # re-deciding: the route out of 'tap-wait' with the double-tap unbound is
    # now the plain expiry, tap-wait -> tap-fired -> idle.
    assert rig.machine.regions['gesture'] == 'idle', rig.machine.regions
    assert not find(extra, 'show_switcher'), (
        'the switcher was asked for twice: %s' % verbs(extra))
    assert not find(extra, 'freeze'), 'and the game was frozen twice'


def test_a_tap_on_an_already_paused_game_still_resumes_it():
    """The other half, and the reason the deferral cannot simply be deleted:
    a tap is how you get back INTO a paused game."""
    rig = Rig(session=SESSION, suspended=APPID,
              pid_states={200: 'T', 201: 'T'}, joystick=True,
              bindings=TAP_SWITCHER).settle()
    got = _tap(rig, 13000.0)
    assert find(got, 'launch'), 'a tap on a paused game must resume it'
    assert find(got, 'launch')[0].reason == 'gesture:tap-resume'
    assert not find(got, 'show_switcher'), 'and must not re-open the switcher'


def test_the_deferred_resume_still_works_when_the_double_tap_is_bound():
    """With something to escalate to, the paused tap waits out the window and
    resumes when it shuts - gesture.paused_tap_decision's 'defer'. That path
    is untouched, and this is the test that says so."""
    rig = Rig(session=SESSION, suspended=APPID,
              pid_states={200: 'T', 201: 'T'}, joystick=True,
              bindings=dict(DEFAULT_BINDINGS, tap='none',
                            double_tap='switcher')).settle()
    got = _tap(rig, 13200.0)
    assert not find(got, 'launch'), 'a second tap may still be coming'
    assert rig.machine.regions['gesture'] == 'tap-wait'
    got = rig.observe(dt=DOUBLE_TAP_S + 0.1, press_duration=0.08)
    assert find(got, 'launch'), 'the window shut with no second tap: resume'
    assert find(got, 'launch')[0].reason == 'gesture:tap-resume'
