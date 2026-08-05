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

from gesture import DOUBLE_TAP_S
from gestureconf import ACTIONS, DEFAULT_BINDINGS
from couchd import (GUARDS, HOLD_SECONDS, REGIONS, TRANSITIONS, UNKNOWN,
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
    assert find(got, 'close_steam_menu')
    rig.observe()
    assert rig.machine.regions['gesture'] == 'idle'


def test_tap_with_a_paused_game_resumes_it():
    rig = Rig(session=SESSION, suspended=APPID, pid_states={200: 'T'},
              joystick=True).settle()
    k0 = 6000.0
    _press(rig, k0)
    got = rig.observe(button_down=False, press_duration=0.3)
    launch = find(got, 'launch')
    assert launch and launch[0].args['mode'] == 'resume'
    assert launch[0].subject == APPID
    assert not find(got, 'freeze')


def test_08_second_press_is_a_tap_and_09_is_a_hold():
    """The boundary is 0.9s of KERNEL time, both sides of it."""
    rig = Rig(session=SESSION, suspended=APPID, pid_states={200: 'T'},
              joystick=True).settle()
    k0 = 7000.0
    _press(rig, k0)
    rig.observe(button_down=True, down_since_k=k0, kernel_now=k0 + 0.8)
    assert rig.machine.regions['gesture'] == 'down'          # not yet a hold
    got = rig.observe(button_down=False, press_duration=0.8)
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
                     ('show', 'kodi'), ('close_steam_menu', 'steam'),
                     ('show_switcher', 'tv')]
    assert find(got, 'freeze')[0].args['pids'] == [200, 201]
    assert find(got, 'show_switcher')[0].args['suspended_first'] is True
    rig.observe()
    assert rig.machine.regions['gesture'] == 'idle'


def test_double_tap_with_nothing_running_just_opens_the_switcher():
    rig = Rig(top_name='Thunar', top_class='Thunar').settle()
    k0 = 11500.0
    _tap(rig, k0)
    got = _tap(rig, k0 + 0.2, double_armed=True)
    assert verbs(got) == [('show', 'kodi'), ('show_switcher', 'tv')]
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


def test_a_tap_that_resumes_a_paused_game_cannot_become_a_double():
    """The first tap already handed the pad back to the game; a Kodi dialog
    on top of that would be unnavigable, so the switcher stays out of it."""
    rig = Rig(session=SESSION, suspended=APPID, pid_states={200: 'T'},
              joystick=True).settle()
    k0 = 13000.0
    got = _tap(rig, k0)
    assert find(got, 'launch'), 'unchanged: a tap still resumes'
    assert rig.machine.regions['gesture'] == 'tap-resume', 'not tap-wait'
    rig.observe()                                   # resume decided -> idle
    got = _tap(rig, k0 + 0.2, double_armed=True)
    assert not find(got, 'show_switcher')


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


def test_rebinding_the_double_tap_changes_what_it_would_do():
    """The exact thing the shadow diff would otherwise report as a T4."""
    o = make_obs(regions={'gesture': 'double-tap'},
                 bindings=bind(double_tap='power_menu'))
    got = reconcile(o)
    assert verbs(got) == [('show', 'power-menu')]
    assert reasons(got) == ['gesture:ps-double-tap']
    assert not find(got, 'show_switcher'), 'the switcher was unbound'


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
                          ('show', 'kodi'), ('close_steam_menu', 'steam'),
                          ('show_switcher', 'tv')]
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
    o = make_obs(regions={'gesture': 'handoff-pending'},
                 bindings=bind(hold_release='desktop'))
    got = reconcile(o)
    assert verbs(got) == [('route_pad', 'kodi'), ('show', 'kodi'),
                          ('close_steam_menu', 'steam'), ('show', 'desktop')]
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
                               ('Thunar', 'Thunar')]))
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


TestConsoleModel = ConsoleModel.TestCase
TestConsoleModel.settings = settings(
    max_examples=60, stateful_step_count=40, deadline=None,
    suppress_health_check=[HealthCheck.too_slow])


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
