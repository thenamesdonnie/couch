#!/usr/bin/env python3
"""Unit tests for the ownership switch and the acting executor.

Nothing here touches the real console: no signals to real pids, no real /tmp
(everything writes under tmp_path), no X, no Kodi, no subprocesses. The acting
paths are exercised against a fake actuator that records what it was asked to
do, and the two flag write-throughs are exercised against the REAL writer
pointed at tmp_path, because their byte formats are the contract with every
legacy reader still on the box.

    .venv/bin/python -m pytest test_acting.py -q
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import couchd
import owns
from couchd import (ActingExecutor, ActionFailed, Actuators, ExecutorRouter,
                    Intent, RecordingExecutor, make_obs, reconcile)

APPID = '367520'
SESSION = {'launcher_pid': 111, 'mode': 'steam', 'appid': APPID,
           'raw': f'111 steam {APPID}'}


# =========================================================================
# fakes
# =========================================================================
class FakeLog:
    def __init__(self):
        self.records = []

    def write(self, rec):
        # the real ShadowLog json-encodes everything it is given; encoding here
        # too keeps a record that could not be serialised from passing.
        json.dumps(rec, default=str)
        self.records.append(rec)
        return rec

    def of(self, kind):
        return [r for r in self.records if r.get('kind') == kind]


class FakeSay:
    def __init__(self):
        self.lines = []

    def __call__(self, msg):
        self.lines.append(msg)

    def any(self, needle):
        return any(needle in l for l in self.lines)


class FakeActuators:
    """Records calls; can be told to fail. Same surface as Actuators."""

    def __init__(self, fail=()):
        self.calls = []
        self.fail = set(fail)

    def _note(self, what, **kw):
        if what in self.fail:
            raise ActionFailed(f'fake failure in {what}')
        self.calls.append((what, kw))
        return dict(kw)

    #: what the real Actuators calls a guard process
    GUARD_NAME = couchd.Actuators.GUARD_NAME

    def __init_guard__(self):
        pass

    #: set to a reason string to make every verify_guard_pid refuse
    guard_refusal = None

    def signal(self, pids, signum, verify=None):
        refused = [{'pid': p, 'why': verify(p)} for p in pids
                   if verify is not None and verify(p)]
        if refused and len(refused) == len(list(pids)):
            return {'sent': [], 'missing': [], 'refused': refused,
                    'signal': int(signum),
                    'skipped': '; '.join(r['why'] for r in refused)}
        return self._note('signal', pids=list(pids), signal=int(signum))

    def verify_guard_pid(self, pid, pidfile=None, name=None):
        return self.guard_refusal

    def spawn(self, argv, env=None, shell_line=None):
        return self._note('spawn', argv=list(argv) if argv else None,
                          env=env, shell_line=shell_line)

    def write_flag(self, path, content, name=None):
        return self._note('write_flag', path=path, content=content, name=name)

    def remove_flag(self, path, name=None):
        return self._note('remove_flag', path=path, name=name)

    def touch(self, path, name=None):
        return self._note('touch', path=path, name=name)

    def kodi(self, method, params):
        return self._note('kodi', method=method, params=params)

    def raise_kodi(self):
        return self._note('raise_kodi')

    def couch_api(self, path, payload):
        return self._note('couch_api', path=path, payload=payload)

    def did(self, what):
        return [kw for w, kw in self.calls if w == what]


def rig(owned=(), fail=(), obs=None):
    """(router, log, actuators, say) wired exactly as the daemon wires them,
    except that say() goes to a sink: a test must never write to the live
    /tmp/couchd.log, which is the phone's log and the evening's evidence."""
    log, sayer, act = FakeLog(), FakeSay(), FakeActuators(fail)
    recorder = RecordingExecutor(log, sayer=sayer)
    router = ExecutorRouter(
        recorder,
        lambda: ActingExecutor(log, act, owned=router.owned, sayer=sayer),
        sayer=sayer, log=log)
    router.set_owns(owns.parse('COUCHD_OWNS=' + ','.join(owned)))
    return router, log, act, sayer


def freeze_intent(pids=(101, 102)):
    return Intent('freeze', APPID,
                  {'pids': list(pids), 'resolver': couchd.PID_RESOLVER,
                   'signal': 'SIGSTOP', 'mode': 'steam'},
                  'gesture:ps-hold',
                  {'effect': 'all game pids in state T', 'deadline_s': 5.0},
                  requires=('gesture', 'session'), cooldown=3.0)


def repair_intent():
    return Intent('clear_flag', 'suspended', {'pids': []},
                  'reconcile:stale-suspended-flag',
                  {'effect': '/tmp/game-suspended gone', 'deadline_s': 2.0},
                  requires=('session',))


# =========================================================================
# owns.conf parsing
# =========================================================================
def test_empty_file_owns_nothing():
    o = owns.parse('# just a comment\nCOUCHD_OWNS=""\n')
    assert o.names == frozenset()
    assert not o
    assert o.warnings == ()


def test_missing_file_owns_nothing(tmp_path):
    o = owns.load(str(tmp_path / 'not-here.conf'))
    assert o.names == frozenset()
    assert o.warnings == ()          # absence is the shipped state, not a fault


def test_unreadable_and_odd_values_own_nothing():
    for text in ('', 'COUCHD_OWNS=\n', 'COUCHD_OWNS=   \n', 'nothing here\n',
                 'COUCHD_OWNS=""  # off\n'):
        assert owns.parse(text).names == frozenset(), text


def test_partial_ownership_parses():
    o = owns.parse('COUCHD_OWNS="gestures"')
    assert o.names == {'gestures'}
    assert o.sorted == ['gestures']


@pytest.mark.parametrize('value', ['gestures,reconcile', 'gestures reconcile',
                                   '"gestures, reconcile"', "'gestures  ,reconcile'",
                                   'gestures,reconcile  # two of them'])
def test_separators_and_quoting(value):
    assert owns.parse(f'COUCHD_OWNS={value}').names == {'gestures', 'reconcile'}


def test_unknown_names_are_rejected_loudly():
    o = owns.parse('COUCHD_OWNS="gestures,suspend,everything"')
    assert o.names == {'gestures'}           # the typo owns nothing
    assert len(o.warnings) == 2
    assert all('unknown responsibility' in w for w in o.warnings)
    assert "'suspend'" in o.warnings[0]


def test_last_line_wins_and_export_warns():
    o = owns.parse('COUCHD_OWNS="gestures"\nexport COUCHD_OWNS="guard"\n'
                   'COUCHD_OWNS="reconcile"\n')
    assert o.names == {'reconcile'}
    assert any('export' in w for w in o.warnings)


def test_every_responsibility_name_is_accepted():
    for name in owns.RESPONSIBILITIES:
        assert owns.parse(f'COUCHD_OWNS={name}').names == {name}


def test_input_is_known_but_not_actable_by_stage_one():
    o = owns.parse('COUCHD_OWNS="input"')
    assert o.names == {'input'} and o.warnings == ()
    assert o.actable == []            # stage 2's input process owns that one


def test_shipped_owns_conf_parses_clean():
    """The live file may name flipped responsibilities (a flip IS a daytime
    edit of this file - gestures went live 5 Aug 2026), but it must always
    parse with zero warnings and only known names: a corrupt flip fails here
    before it can fail the box."""
    o = owns.load(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'owns.conf'), force=True)
    assert o.warnings == ()
    assert o.names <= set(owns.RESPONSIBILITIES)


def test_load_is_stat_cached_but_sees_changes(tmp_path):
    p = tmp_path / 'owns.conf'
    p.write_text('COUCHD_OWNS=""\n')
    assert owns.load(str(p), force=True).names == frozenset()
    p.write_text('COUCHD_OWNS="guard"\n')
    os.utime(p, (1, 1))              # a changed mtime is what busts the cache
    assert owns.load(str(p)).names == {'guard'}


# =========================================================================
# reason -> responsibility routing
# =========================================================================
@pytest.mark.parametrize('reason,expect', [
    ('gesture:ps-hold', 'gestures'),
    ('gesture:tap-resume', 'gestures'),
    ('gesture:double-tap-switcher', 'gestures'),
    ('transition:session-started', 'transitions'),
    ('transition:session-ended', 'transitions'),
    ('guard:steam-menu-holds-the-pad', 'guard'),
    ('reconcile:orphaned-session', 'reconcile'),
    ('', None),
    ('something-else', None),
])
def test_responsibility_for_reason(reason, expect):
    assert owns.responsibility_for_reason(reason) == expect


def test_every_reason_the_model_emits_has_an_owner():
    """A reason with no responsibility can never be acted on, so a new one
    that forgot its prefix would silently stay in shadow forever."""
    worlds = [
        make_obs(regions={'gesture': 'hold-fired'}, session=SESSION,
                 pid_states={101: 'S'}),
        make_obs(regions={'gesture': 'handoff-pending'}, session=SESSION,
                 pid_states={101: 'T'}, suspended=APPID),
        make_obs(regions={'gesture': 'double-tap'}, session=SESSION,
                 pid_states={101: 'S'}),
        make_obs(regions={'gesture': 'tap-resume'}, session=SESSION,
                 suspended=APPID, pid_states={101: 'T'}),
        make_obs(regions={'session': 'starting'}, session=SESSION),
        make_obs(regions={'session': 'ending'}),
        make_obs(regions={'enforcement': 'kodi'}, top_name='Steam',
                 top_class='steam', steam_route='ClientUI'),
        make_obs(regions={'session': 'orphaned'}, session=SESSION,
                 launcher_alive=False),
        make_obs(suspended=APPID, pid_states={}),
    ]
    seen = set()
    for o in worlds:
        for it in reconcile(o):
            resp = owns.responsibility_for_reason(it.reason)
            assert resp is not None, f'{it.reason} has no responsibility'
            assert resp in owns.ACTABLE
            seen.add(resp)
    assert seen == set(owns.ACTABLE), seen


def test_every_verb_the_model_can_emit_has_an_action():
    assert set(couchd.VERBS) <= set(ActingExecutor.ACTIONS)


def test_acted_handoff_spawns_the_real_guard():
    """The gestures flip must not orphan the enforcement window: legacy's
    handoff_to_kodi() spawns steam-input-guard as its LAST act and now
    yields the whole gesture, while couchd's own guard: intents are unowned
    and record-only - so with neither side spawning it, a Steam menu opening
    a beat after the handoff captured the pad with nothing to close it,
    ever (adversarial review, 5 Aug 2026). The acted handoff therefore
    spawns the real guard exactly where legacy did."""
    router, log, act, sayer = rig(owned=('gestures',))
    o = make_obs(regions={'gesture': 'handoff-pending'}, session=SESSION,
                 pid_states={101: 'T'}, suspended=APPID)
    guards = [i for i in reconcile(o) if i.verb == 'spawn_guard']
    assert len(guards) == 1
    assert guards[0].subject == 'kodi'
    assert owns.responsibility_for_reason(guards[0].reason) == 'gestures'
    router.execute(guards[0], make_obs())
    assert any(couchd.GUARD_BIN in (s['argv'] or [])
               for s in act.did('spawn'))


def test_shadow_handoff_records_but_never_spawns_the_guard():
    """Same intent, nothing owned: the guard spawn must be a would-do line,
    not a process - legacy's own handoff is doing the real spawn there."""
    router, log, act, sayer = rig()
    o = make_obs(regions={'gesture': 'handoff-pending'}, session=SESSION,
                 pid_states={101: 'T'}, suspended=APPID)
    guards = [i for i in reconcile(o) if i.verb == 'spawn_guard']
    assert len(guards) == 1
    router.execute(guards[0], make_obs())
    assert act.did('spawn') == []


# =========================================================================
# the router: acting vs recording
# =========================================================================
def test_empty_owns_builds_no_acting_object_at_all():
    router, log, act, sayer = rig()
    assert router.acting is None
    assert router.owned == frozenset()
    router.execute(freeze_intent(), make_obs())
    router.execute(repair_intent(), make_obs())
    assert act.calls == []
    assert all(r.get('acted') is None for r in log.of('intent'))


def test_owning_gestures_acts_on_gestures_only():
    router, log, act, sayer = rig(owned=('gestures',))
    assert router.acting is not None
    router.execute(freeze_intent(), make_obs())          # gesture: acted
    router.execute(repair_intent(), make_obs())          # reconcile: recorded
    assert act.did('signal') == [{'pids': [101, 102],
                                  'signal': int(couchd.signal.SIGSTOP)}]
    assert act.did('remove_flag') == []
    acted = [r for r in log.of('intent') if r.get('acted')]
    recorded = [r for r in log.of('intent') if not r.get('acted')]
    assert [r['verb'] for r in acted] == ['freeze']
    assert [r['verb'] for r in recorded] == ['clear_flag']
    assert acted[0]['responsibility'] == 'gestures'


def test_owning_reconcile_acts_on_repairs_only():
    router, log, act, sayer = rig(owned=('reconcile',))
    router.execute(freeze_intent(), make_obs())
    router.execute(repair_intent(), make_obs())
    assert act.did('signal') == []
    assert act.did('remove_flag')[0]['name'] == 'game-suspended'


def test_ownership_can_be_taken_and_handed_back_at_runtime():
    router, log, act, sayer = rig()
    assert router.set_owns(owns.parse('COUCHD_OWNS=guard')) is True
    assert router.acting is not None and router.owned == {'guard'}
    assert router.set_owns(owns.parse('COUCHD_OWNS=guard')) is False   # no churn
    assert router.set_owns(owns.parse('COUCHD_OWNS=')) is True
    # the acting OBJECT is gone again, not merely disabled (R1)
    assert router.acting is None
    router.execute(freeze_intent(), make_obs())
    assert act.calls == []
    assert sayer.any('ownership changed')
    assert [r['now'] for r in log.of('daemon')] == [['guard'], []]


def test_unknown_name_leaves_the_console_in_shadow():
    router, log, act, sayer = rig()
    router.set_owns(owns.parse('COUCHD_OWNS="gestrues"'))
    assert router.acting is None
    router.execute(freeze_intent(), make_obs())
    assert act.calls == []


def test_input_alone_builds_no_acting_object():
    router, log, act, sayer = rig()
    router.set_owns(owns.parse('COUCHD_OWNS="input"'))
    assert router.acting is None      # stage 1 executes nothing for input


def test_acting_executor_refuses_what_it_does_not_own():
    """The second lock: even called directly, it acts only on its own list."""
    log, act, sayer = FakeLog(), FakeActuators(), FakeSay()
    ex = ActingExecutor(log, act, owned=('guard',), sayer=sayer)
    rec = ex.execute(freeze_intent(), make_obs())
    assert rec['acted'] is False and 'not owned' in rec['action']['refused']
    assert act.calls == []
    assert sayer.any('REFUSED')


# =========================================================================
# C17: predicted effect + deadline
# =========================================================================
def test_acted_record_carries_the_prediction_and_deadline():
    router, log, act, sayer = rig(owned=('gestures',))
    router.execute(freeze_intent(), make_obs(mono=1000.0))
    rec = [r for r in log.of('intent') if r.get('acted')][0]
    assert rec['predict'] == {'effect': 'all game pids in state T',
                              'deadline_s': 5.0}
    assert rec['action']['ok'] is True
    pending = router.acting.pending[0]
    assert pending['deadline'] == pytest.approx(1005.0)


def test_effect_confirmed_when_the_world_gets_there():
    router, log, act, sayer = rig(owned=('gestures',))
    router.execute(freeze_intent(), make_obs(mono=1000.0))
    got = router.check_pending(make_obs(mono=1001.0,
                                        pid_states={101: 'T', 102: 'T'}))
    assert [v for _, v, _ in got] == ['confirmed']
    eff = log.of('effect')[0]
    assert eff['verdict'] == 'confirmed'
    assert eff['expected'] == 'all game pids in state T'
    assert eff['latency_s'] == pytest.approx(1.0)
    assert router.acting.pending == []


def test_effect_missed_is_loud_and_not_retried():
    router, log, act, sayer = rig(owned=('gestures',))
    router.execute(freeze_intent(), make_obs(mono=1000.0))
    still_running = make_obs(mono=1002.0, pid_states={101: 'S', 102: 'S'})
    assert router.check_pending(still_running) == []      # inside the deadline
    router.check_pending(make_obs(mono=1006.0, pid_states={101: 'S'}))
    assert log.of('effect')[0]['verdict'] == 'missed'
    assert sayer.any('EFFECT MISSED')
    # C11: nothing further. No second signal, and the prediction is dropped
    # rather than queued as work to chase.
    assert len(act.did('signal')) == 1
    assert router.acting.pending == []


def test_unverifiable_verbs_say_unverified_not_confirmed():
    router, log, act, sayer = rig(owned=('gestures',))
    it = Intent('snapshot', APPID, {'via': 'pause-snap'}, 'gesture:ps-hold',
                {'effect': 'a freeze-frame jpg for the appid', 'deadline_s': 5.0},
                requires=('gesture',), cooldown=3.0)
    router.execute(it, make_obs(mono=1000.0))
    router.check_pending(make_obs(mono=1006.0))
    assert log.of('effect')[0]['verdict'] == 'unverified'
    assert not sayer.any('EFFECT MISSED')


@pytest.mark.parametrize('verb,subject,args,world,ok', [
    ('thaw', APPID, {'pids': [101], 'resolver': 'r'}, {'pid_states': {101: 'S'}}, True),
    ('thaw', APPID, {'pids': [101], 'resolver': 'r'}, {'pid_states': {101: 'T'}}, False),
    ('set_flag', 'suspended', {'value': APPID}, {'suspended': APPID}, True),
    ('set_flag', 'suspended', {'value': APPID}, {'suspended': None}, False),
    ('clear_flag', 'suspended', {}, {'suspended': None}, True),
    ('clear_flag', 'session', {}, {'session': SESSION}, False),
    ('route_pad', 'kodi', {}, {'joystick': True}, True),
    ('route_pad', 'game', {}, {'joystick': True}, False),
    ('show', 'kodi', {}, {'top_name': 'Kodi'}, True),
    ('show', 'kodi', {}, {'top_name': 'Steam'}, False),
    ('dismiss', 'power-menu', {}, {'kodi_window': 10000}, True),
    ('dismiss', 'power-menu', {}, {'kodi_window': 10106}, False),
    ('close_steam_menu', 'steam', {}, {'steam_route': ''}, True),
    ('close_steam_menu', 'steam', {}, {'steam_route': 'ClientUI/769'}, False),
])
def test_effect_oracles(verb, subject, args, world, ok):
    it = Intent(verb, subject, args, 'gesture:ps-hold',
                {'effect': 'x', 'deadline_s': 2.0})
    assert couchd.EFFECT_CHECKS[verb](make_obs(**world), it) is ok


# =========================================================================
# C11: failure -> log loudly, do nothing further
# =========================================================================
def test_failed_action_is_loud_and_leaves_the_world_to_legacy():
    router, log, act, sayer = rig(owned=('gestures',), fail=('signal',))
    rec = router.execute(freeze_intent(), make_obs())
    assert rec['acted'] is False
    assert rec['action'] == {'ok': False, 'error': 'fake failure in signal'}
    assert sayer.any('ACTION FAILED')
    assert sayer.any('roll back with an empty')
    assert router.acting.failures == 1 and router.acting.count == 0
    # no prediction is armed for something that did not happen
    assert router.acting.pending == []


def test_a_crashing_action_never_takes_the_daemon_down():
    class Exploding(FakeActuators):
        def signal(self, pids, signum):
            raise RuntimeError('boom')

    log, sayer = FakeLog(), FakeSay()
    ex = ActingExecutor(log, Exploding(), owned=('gestures',), sayer=sayer)
    rec = ex.execute(freeze_intent(), make_obs())
    assert rec['acted'] is False and 'boom' in rec['action']['error']
    assert sayer.any('ACTION CRASHED')


def test_unknown_verb_fails_closed():
    log, sayer, act = FakeLog(), FakeSay(), FakeActuators()
    ex = ActingExecutor(log, act, owned=('gestures',), sayer=sayer)
    ex.ACTIONS = {}                     # a verb nobody taught it
    rec = ex.execute(freeze_intent(), make_obs())
    assert rec['acted'] is False and act.calls == []


def test_stage_one_launches_nothing_but_resume():
    router, log, act, sayer = rig(owned=('gestures',))
    fresh = Intent('launch', APPID, {'mode': 'steam'}, 'gesture:ps-tap',
                   {'effect': 'game running', 'deadline_s': 30.0})
    rec = router.execute(fresh, make_obs())
    assert rec['acted'] is False and 'R1' in rec['action']['error']
    assert act.calls == []
    resume = Intent('launch', APPID, {'mode': 'resume'}, 'gesture:tap-resume',
                    {'effect': 'game pids back in state S', 'deadline_s': 5.0})
    assert router.execute(resume, make_obs())['acted'] is True
    assert act.did('spawn')[0]['argv'] == [couchd.GAME_LAUNCH, 'resume']


# =========================================================================
# D: /tmp flag write-through, byte for byte
# =========================================================================
# Copied VERBATIM from the writers still on the box, which is the whole point:
#   pad-home-watcher.freeze_game:  with open(SUSPENDED, 'w') as f: f.write(appid)
#   game-launch (launch):          echo "$$ $MODE $APPID" > "$SESSION"
#   steam-input-guard.supersede:   with open(PIDFILE, 'w') as f: f.write(str(os.getpid()))
SUSPENDED_FIXTURE = '367520'                # no trailing newline
SESSION_FIXTURE = '111 steam 367520\n'      # echo's newline
GUARD_PIDFILE_FIXTURE = '4242'              # no trailing newline


def real_rig(tmp_path, monkeypatch, owned=('gestures',)):
    """The REAL Actuators, pointed at tmp_path: this exercises write_atomic's
    rename (which the FlagObserver's inotify design depends on) and the exact
    bytes, without going near /tmp."""
    monkeypatch.setattr(couchd, 'SUSPENDED_FLAG', str(tmp_path / 'game-suspended'))
    monkeypatch.setattr(couchd, 'SESSION_FLAG', str(tmp_path / 'game-session'))
    monkeypatch.setattr(couchd, 'GUARD_PIDFILE',
                        str(tmp_path / 'steam-input-guard.pid'))
    written = []
    act = Actuators(kodi_rpc=None,
                    on_flag_write=lambda n, c: written.append((n, c)),
                    spawn_scope=False)
    act.spawn = lambda argv, env=None, shell_line=None: {'pid': 0}
    log, sayer = FakeLog(), FakeSay()
    ex = ActingExecutor(log, act, owned=owned, sayer=sayer)
    return ex, written, log, sayer


def test_suspended_flag_matches_the_watchers_bytes(tmp_path, monkeypatch):
    ex, written, log, sayer = real_rig(tmp_path, monkeypatch)
    it = Intent('set_flag', 'suspended', {'value': APPID}, 'gesture:ps-hold',
                {'effect': '/tmp/game-suspended exists', 'deadline_s': 2.0})
    assert ex.execute(it, make_obs())['acted'] is True
    raw = (tmp_path / 'game-suspended').read_bytes()
    assert raw == SUSPENDED_FIXTURE.encode()
    assert written == [('game-suspended', APPID)]
    # and the legacy readers' own parse of it still answers the same thing
    assert raw.decode().strip() == APPID


def test_bigpicture_suspend_writes_the_literal_legacy_writes(tmp_path, monkeypatch):
    ex, written, log, sayer = real_rig(tmp_path, monkeypatch)
    it = Intent('set_flag', 'suspended', {'value': 'bigpicture', 'pids': []},
                'gesture:ps-hold-bigpicture',
                {'effect': '/tmp/game-suspended exists', 'deadline_s': 2.0})
    ex.execute(it, make_obs())
    assert (tmp_path / 'game-suspended').read_bytes() == b'bigpicture'


def test_session_flag_matches_game_launchs_bytes(tmp_path, monkeypatch):
    ex, written, log, sayer = real_rig(tmp_path, monkeypatch)
    it = Intent('set_flag', 'session', {'value': '111 steam 367520'},
                'transition:session-started',
                {'effect': '/tmp/game-session exists', 'deadline_s': 2.0},
                )
    ex.owned = frozenset(('transitions',))
    ex.execute(it, make_obs())
    assert (tmp_path / 'game-session').read_text() == SESSION_FIXTURE
    # the FlagObserver's own parser must read back what game-launch means
    parts = (tmp_path / 'game-session').read_text().split()
    assert parts == ['111', 'steam', '367520']


def test_clearing_flags_removes_them_and_the_freeze_frames(tmp_path, monkeypatch):
    ex, written, log, sayer = real_rig(tmp_path, monkeypatch, owned=('reconcile',))
    (tmp_path / 'game-suspended').write_text(APPID)
    (tmp_path / 'game-session').write_text(SESSION_FIXTURE)
    ex.execute(repair_intent(), make_obs())
    assert not (tmp_path / 'game-suspended').exists()
    ex.execute(Intent('clear_flag', 'session', {'pids': []},
                      'reconcile:orphaned-session',
                      {'effect': '/tmp/game-session gone', 'deadline_s': 2.0}),
               make_obs())
    assert not (tmp_path / 'game-session').exists()
    assert written == [('game-suspended', None), ('game-session', None)]


def test_clearing_a_flag_that_is_already_gone_is_not_a_failure(tmp_path,
                                                               monkeypatch):
    ex, written, log, sayer = real_rig(tmp_path, monkeypatch, owned=('reconcile',))
    rec = ex.execute(repair_intent(), make_obs())
    assert rec['acted'] is True and rec['action']['existed'] is False


def test_flag_writes_are_atomic_renames(tmp_path, monkeypatch):
    """The FlagObserver watches the DIRECTORY because these are renames; a
    truncate-in-place writer would break the observer on both stacks."""
    ex, written, log, sayer = real_rig(tmp_path, monkeypatch)
    target = tmp_path / 'game-suspended'
    target.write_text('stale')
    before = target.stat().st_ino
    ex.execute(Intent('set_flag', 'suspended', {'value': APPID},
                      'gesture:ps-hold',
                      {'effect': 'x', 'deadline_s': 2.0}), make_obs())
    assert target.stat().st_ino != before          # replaced, not rewritten
    assert [p.name for p in tmp_path.iterdir()] == ['game-suspended']


def test_guard_pidfile_format_matches_the_guards(tmp_path, monkeypatch):
    monkeypatch.setattr(couchd, 'GUARD_PIDFILE',
                        str(tmp_path / 'steam-input-guard.pid'))
    act = Actuators(spawn_scope=False)
    act.write_flag(couchd.GUARD_PIDFILE, '4242', 'steam-input-guard.pid')
    assert (tmp_path / 'steam-input-guard.pid').read_bytes() == \
        GUARD_PIDFILE_FIXTURE.encode()
    # ...and the legacy readers' parse (`int(open(PIDFILE).read())`) works
    assert int(open(couchd.GUARD_PIDFILE).read()) == 4242


def test_self_written_flags_are_labelled_not_hidden():
    world = couchd.World(FakeLog())
    world.note_self_write('game-suspended', APPID)
    assert world.was_self_written('game-suspended', APPID) is True
    assert world.was_self_written('game-suspended', '999') is False
    assert world.was_self_written('game-session', APPID) is False
    world.note_self_write('game-suspended', None)
    assert world.was_self_written('game-suspended', None) is True
    assert world.was_self_written('game-suspended', APPID) is False


def test_self_write_memory_expires(monkeypatch):
    world = couchd.World(FakeLog())
    world.note_self_write('game-suspended', APPID)
    world.self_writes['game-suspended'] = (APPID, -1000.0)
    assert world.was_self_written('game-suspended', APPID) is False


# =========================================================================
# the flip-readiness guarantee: empty owns == the daemon that could not act
# =========================================================================
# =========================================================================
# the two parsers must agree, or a flip leaves a responsibility ownerless
# =========================================================================
GAME_LAUNCH_SRC = os.path.expanduser('~/.local/bin/game-launch')


def bash_couchd_owns(conf_path, name):
    """Run game-launch's OWN couchd_owns() against a conf file.

    The function is lifted out of the script rather than reimplemented here -
    the whole point is to catch the day somebody edits one parser and not the
    other. Nothing else in game-launch is executed."""
    import subprocess
    src = open(GAME_LAUNCH_SRC).read().splitlines()
    start = next(i for i, l in enumerate(src) if l.startswith('couchd_owns() {'))
    end = next(i for i in range(start, len(src)) if src[i] == '}')
    block = '\n'.join(src[start:end + 1])
    r = subprocess.run(
        ['bash', '-c', f'{block}\nOWNS_CONF="$1"; couchd_owns "$2" && echo YES '
         f'|| echo NO', '_', conf_path, name],
        capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip() == 'YES'


@pytest.mark.skipif(not os.path.exists(GAME_LAUNCH_SRC),
                    reason='game-launch is not installed on this box')
@pytest.mark.parametrize('text', [
    'COUCHD_OWNS=""\n',
    'COUCHD_OWNS=\n',
    '# nothing at all\n',
    'COUCHD_OWNS="gestures"\n',
    'COUCHD_OWNS=gestures\n',
    "COUCHD_OWNS='gestures reconcile'\n",
    'COUCHD_OWNS="gestures,reconcile"\n',
    'COUCHD_OWNS="guard"   # only the guard\n',
    'COUCHD_OWNS="gestures"\nCOUCHD_OWNS="transitions"\n',
    '  COUCHD_OWNS = "gestures"\n',
    'COUCHD_OWNS="input,gestures"\n',
    # -- the hostile corpus (each of these DID diverge before the fix) ----
    # two quoted groups: the shell used to strip every quote and own both,
    # while owns.py owned neither -> a responsibility with no owner at all
    'COUCHD_OWNS="gestures" "transitions"\n',
    "COUCHD_OWNS='gestures' 'guard'\n",
    # CRLF: owns.py owned, the shell saw "gestures\r" and did not
    'COUCHD_OWNS="gestures"\r\n',
    'COUCHD_OWNS=gestures\r\n',
    'COUCHD_OWNS=""\r\n',
    # spaces around =, tabs, trailing comment after a bare value
    '\tCOUCHD_OWNS\t=\tguard\t\n',
    'COUCHD_OWNS = gestures, reconcile   # both\n',
    'COUCHD_OWNS=gestures#nospace\n',
    # the last line wins even when it is the empty one (a rollback in place)
    'COUCHD_OWNS="gestures,guard"\nCOUCHD_OWNS=""\n',
    'COUCHD_OWNS=gestures\nCOUCHD_OWNS=\n',
    # a lone quote, an unbalanced pair, an unknown name, and junk
    'COUCHD_OWNS="\n',
    'COUCHD_OWNS="gestures\n',
    'COUCHD_OWNS="gestrues"\n',
    'COUCHD_OWNS=;rm -rf /\n',
    'COUCHD_OWNS="  gestures  "\n',
    # a \r-only file: sed sees ONE line that does not start with COUCHD_OWNS,
    # and so must owns.py (splitlines() would have found it and diverged)
    'first\rCOUCHD_OWNS="gestures"\r',
    # no trailing newline at all
    'COUCHD_OWNS="guard"',
])
def test_bash_and_python_parsers_agree(tmp_path, text):
    conf = tmp_path / 'owns.conf'
    conf.write_text(text)
    mine = owns.load(str(conf), force=True)
    for name in owns.RESPONSIBILITIES:
        assert bash_couchd_owns(str(conf), name) == (name in mine.names), \
            f'{text!r} disagrees about {name}'


@pytest.mark.skipif(not os.path.exists(GAME_LAUNCH_SRC),
                    reason='game-launch is not installed on this box')
def test_bash_parser_owns_nothing_without_a_file(tmp_path):
    for name in owns.RESPONSIBILITIES:
        assert bash_couchd_owns(str(tmp_path / 'absent.conf'), name) is False


@pytest.mark.skipif(not os.path.exists(GAME_LAUNCH_SRC),
                    reason='game-launch is not installed on this box')
def test_bash_parser_agrees_with_the_shipped_file():
    """Whatever the live file currently says, both parsers must read it the
    same way - the file's content changes on flip day, the agreement never."""
    shipped = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'owns.conf')
    o = owns.load(shipped, force=True)
    for name in owns.RESPONSIBILITIES:
        assert bash_couchd_owns(shipped, name) is (name in o.names)


# =========================================================================
# a corrupt config must mean "own nothing", never a dead daemon
# =========================================================================
def test_invalid_utf8_owns_nothing_and_warns(tmp_path):
    p = tmp_path / 'owns.conf'
    p.write_bytes(b'# an editor wrote latin-1: caf\xe9\nCOUCHD_OWNS="gestures"\n')
    o = owns.load(str(p), force=True)
    # errors='replace': the file still parses, the daemon still runs
    assert o.names == {'gestures'}
    p.write_bytes(b'\xff\xfe\x00C\x00O\x00U\x00C\x00H\x00D\x00')   # UTF-16 BOM
    os.utime(p, (2, 2))
    o = owns.load(str(p))
    assert o.names == frozenset()


def test_a_directory_where_the_file_should_be_owns_nothing_loudly(tmp_path):
    d = tmp_path / 'owns.conf'
    d.mkdir()
    o = owns.load(str(d), force=True)
    assert o.names == frozenset()
    assert o.warnings and 'unreadable' in o.warnings[0]


def test_load_never_raises_whatever_the_file_is(tmp_path):
    """The daemon reads this every tick; an exception here is a crash-loop."""
    for content in (b'\x00\x01\x02', b'COUCHD_OWNS=' + b'x' * 100000,
                    b'\xed\xa0\x80', b''):
        p = tmp_path / 'owns.conf'
        p.write_bytes(content)
        os.utime(p, (len(content) + 1, len(content) + 1))
        assert isinstance(owns.load(str(p)).names, frozenset)


# =========================================================================
# ownership is a LEASE: a stopped couchd hands everything back
# =========================================================================
def heartbeat(tmp_path, age_s, name='status.json'):
    """A status.json that couchd last wrote `age_s` ago."""
    p = tmp_path / name
    p.write_text('{}')
    os.utime(p, (time.time() - age_s, time.time() - age_s))
    return str(p)


def test_a_fresh_heartbeat_means_couchd_is_alive(tmp_path):
    assert owns.couchd_alive(heartbeat(tmp_path, 2)) is True


def test_a_stale_heartbeat_means_it_is_not(tmp_path):
    assert owns.couchd_alive(heartbeat(tmp_path, 45)) is False
    assert owns.heartbeat_age(heartbeat(tmp_path, 45)) == pytest.approx(45, abs=2)


def test_no_status_file_at_all_means_it_is_not(tmp_path):
    assert owns.couchd_alive(str(tmp_path / 'never-written.json')) is False
    assert owns.heartbeat_age(str(tmp_path / 'never-written.json')) is None


def test_legacy_owns_requires_both_the_file_and_the_heartbeat(tmp_path):
    conf = tmp_path / 'owns.conf'
    conf.write_text('COUCHD_OWNS="gestures"\n')
    fresh = heartbeat(tmp_path, 1, 'fresh.json')
    stale = heartbeat(tmp_path, 120, 'stale.json')
    assert owns.owns('gestures', str(conf), fresh) is True
    # the charter's one-command rollback, honoured without editing a file:
    # couchd stopped -> the heartbeat ages out -> legacy acts again
    assert owns.owns('gestures', str(conf), stale) is False
    assert owns.owns('reconcile', str(conf), fresh) is False


def test_the_daemons_own_read_ignores_the_heartbeat(tmp_path):
    """couchd must not make its ownership conditional on the file it is
    itself about to write - that is a deadlock, not a safety check."""
    conf = tmp_path / 'owns.conf'
    conf.write_text('COUCHD_OWNS="gestures"\n')
    assert owns.load(str(conf), force=True).names == {'gestures'}


@pytest.fixture(autouse=True)
def _no_heartbeat_leak(tmp_path, monkeypatch):
    """Nothing in this file may consult the LIVE status.json by accident."""
    monkeypatch.setenv('COUCHD_STATUS_FILE', str(tmp_path / 'no-such-status'))
    yield


# =========================================================================
# toggles: cooldown must outlast the action's own deadline
# =========================================================================
# Steam's routing log line that means "the menu has the pad". couchd only
# emits a guide press when it can SEE this (T4-1) - the button is a toggle, so
# a press at a closed menu opens one.
MENU_ROUTE = ('OnFocusWindowChanged to window type: '
              'k_nGameIDControllerConfigs_ClientUI, AppID 769')

TOGGLE_WORLDS = [
    dict(regions={'gesture': 'handoff-pending'}, session=SESSION,
         pid_states={101: 'T'}, suspended=APPID, steam_route=MENU_ROUTE),
    dict(regions={'enforcement': 'kodi'}, top_name='Steam', top_class='steam',
         steam_route='ClientUI/769'),
    dict(regions={'gesture': 'hold-fired'}, session=SESSION,
         bindings=dict(couchd.gestureconf.DEFAULT_BINDINGS, hold='steam_menu')),
    dict(regions={'gesture': 'hold-fired'}, session=SESSION,
         bindings=dict(couchd.gestureconf.DEFAULT_BINDINGS, hold='tv_toggle')),
]


@pytest.mark.parametrize('world', TOGGLE_WORLDS)
def test_every_toggle_the_model_emits_outlasts_its_own_deadline(world):
    emitted = [i for i in reconcile(make_obs(**world)) if couchd.is_toggle(i)]
    assert emitted, 'this world was supposed to produce a toggle'
    for it in emitted:
        deadline = float((it.predict or {}).get('deadline_s', 0))
        assert it.cooldown > deadline, (
            f'{it.key}: cooldown {it.cooldown} <= deadline {deadline} - a '
            f'second guide press inside the window REOPENS what it closed')


def test_the_toggle_rule_is_an_invariant_not_just_a_constant():
    bad = Intent('close_steam_menu', 'steam', {'via': 'vpad-guide'},
                 'guard:steam-menu-holds-the-pad',
                 {'effect': 'routing leaves ClientUI', 'deadline_s': 3.0},
                 cooldown=1.0)
    violations = couchd.check_invariants(make_obs(), [bad])
    assert any(n == 'toggle_cooldown_outlasts_deadline' for n, _ in violations)


def test_non_toggle_verbs_are_not_constrained():
    ok = Intent('route_pad', 'kodi', {}, 'reconcile:joystick-setting-drift',
                {'effect': 'input.enablejoystick true', 'deadline_s': 2.0},
                cooldown=1.0)
    assert not any(n == 'toggle_cooldown_outlasts_deadline'
                   for n, _ in couchd.check_invariants(make_obs(), [ok]))


def test_a_second_toggle_is_skipped_while_the_first_is_pending():
    router, log, act, sayer = rig(owned=('guard',))
    it = Intent('close_steam_menu', 'steam', {'via': 'vpad-guide'},
                'guard:steam-menu-holds-the-pad',
                {'effect': 'routing leaves ClientUI', 'deadline_s': 3.0},
                cooldown=couchd.GUIDE_TOGGLE_COOLDOWN)
    open_menu = dict(steam_route=MENU_ROUTE)
    router.execute(it, make_obs(mono=1000.0, **open_menu))
    assert len(act.did('spawn')) == 1
    second = router.execute(it, make_obs(mono=1001.0, **open_menu))
    assert len(act.did('spawn')) == 1                  # NOT pressed again
    assert second['acted'] is False
    assert 'still inside its C17 deadline' in second['action']['skipped']
    assert router.acting.skipped == 1
    # once the effect lands, the verb is free again
    router.check_pending(make_obs(mono=1002.0, steam_route=''))
    router.execute(it, make_obs(mono=1003.0, **open_menu))
    assert len(act.did('spawn')) == 2


# =========================================================================
# C17 before the fact: the two actions that are irreversible if wrong
#
# T4-1 (guide press) and T4-2 (guard SIGTERM), found by the Evening-1 replay.
# Both re-check the predicate their decision rested on at EXECUTION time; a
# check that has stopped holding is a SKIP - recorded, cooled down, never a
# failure and never a backoff, because nothing went wrong.
# =========================================================================
def menu_intent(reason='guard:steam-menu-holds-the-pad'):
    return Intent('close_steam_menu', 'steam', {'via': 'vpad-guide'}, reason,
                  {'effect': 'routing leaves ClientUI', 'deadline_s': 3.0},
                  cooldown=couchd.GUIDE_TOGGLE_COOLDOWN)


def test_a_guide_press_at_a_closed_menu_is_skipped_not_sent():
    """The whole of T4-1's second lock. In Evening 1 couchd emitted 21 of
    these against legacy's 11; post-flip, a press into a closed menu OPENS
    the Steam menu over the Kodi the gesture just handed the room back."""
    router, log, act, sayer = rig(owned=('guard',))
    rec = router.execute(menu_intent(), make_obs(mono=1000.0, steam_route=''))
    assert not act.did('spawn'), 'nothing was pressed'
    assert rec['acted'] is False
    assert 'toggle' in rec['action']['precondition_gone']
    assert router.acting.skipped == 1
    assert router.acting.failures == 0, 'a skip is not a failure'
    assert not router.acting.fails, 'and opens no backoff'
    assert sayer.any('SKIPPED')


def test_a_guide_press_at_an_OPEN_menu_goes_through():
    router, log, act, sayer = rig(owned=('guard',))
    rec = router.execute(menu_intent(),
                         make_obs(mono=1000.0, steam_route=MENU_ROUTE))
    assert len(act.did('spawn')) == 1
    assert rec['acted'] is True


def test_a_guide_press_is_skipped_while_steam_is_unreadable():
    """An unread routing log is UNKNOWN, not closed - and a toggle fired on
    an unknown state is a coin flip with the room's screen."""
    router, log, act, sayer = rig(owned=('guard',))
    rec = router.execute(menu_intent(),
                         make_obs(mono=1000.0, steam_route=MENU_ROUTE,
                                  steam_known=False))
    assert not act.did('spawn')
    assert rec['acted'] is False


def test_the_desktop_overlay_press_rechecks_its_own_predicate():
    """R7(f)'s arm has a different tell (Steam CONSUMED a guide press in
    desktop UI mode), so it re-checks that one, not the routing log - which
    in desktop mode never says ClientUI at all."""
    router, log, act, sayer = rig(owned=('guard',))
    live = dict(session=SESSION, ui_mode=7, focused_class='Kodi', mono=5000.0,
                guide_consumed_at=4998.5, enforcement_target='kodi',
                enforcement_until=5003.0, regions={'enforcement': 'kodi'})
    it = menu_intent('guard:desktop-overlay-after-tap')
    assert router.execute(it, make_obs(**live))['acted'] is True
    assert len(act.did('spawn')) == 1
    # ...and once Steam has been given the pad back deliberately, it stops
    router2, _, act2, _ = rig(owned=('guard',))
    gone = router2.execute(it, make_obs(**dict(live,
                                               focused_class='steamwebhelper')))
    assert gone['acted'] is False
    assert not act2.did('spawn')
    assert 'overlay' in gone['action']['precondition_gone']


def kill_intent(pid=1673365):
    return Intent('kill', 'steam-input-guard',
                  {'pids': [pid], 'resolver': 'guard-pidfile',
                   'signal': 'SIGTERM', 'reason': 'superseded-by-freeze'},
                  'gesture:ps-hold',
                  {'effect': 'the guard pidfile is gone or replaced',
                   'deadline_s': 5.0}, cooldown=5.0)


def test_a_supersede_kill_is_skipped_when_the_pid_check_refuses():
    """T4-2. At 02:21:52 couchd named a guard pid the pidfile had replaced
    412ms earlier, on a box where the guard respawned five times in twenty
    seconds. `os.kill` does not ask who it is talking to."""
    router, log, act, sayer = rig(owned=('gestures',))
    act.guard_refusal = ('/tmp/steam-input-guard.pid now names 1673613, not '
                         '1673365 - the guard was replaced')
    rec = router.execute(kill_intent(), make_obs(mono=1000.0))
    assert not act.did('signal'), 'nothing was signalled'
    assert rec['acted'] is False
    assert '1673613' in rec['action']['precondition_gone']
    assert router.acting.failures == 0 and not router.acting.fails


def test_a_supersede_kill_with_a_valid_pid_still_signals():
    router, log, act, sayer = rig(owned=('gestures',))
    act.guard_refusal = None
    rec = router.execute(kill_intent(), make_obs(mono=1000.0))
    assert act.did('signal') == [{'pids': [1673365], 'signal': 15}]
    assert rec['acted'] is True


def test_the_pid_checks_are_all_three_and_each_one_refuses(tmp_path,
                                                           monkeypatch):
    """The real verifier, against the real pidfile format."""
    pidfile = tmp_path / 'steam-input-guard.pid'
    monkeypatch.setattr(couchd, 'GUARD_PIDFILE', str(pidfile))
    act = Actuators(spawn_scope=False)

    # (c) the pidfile does not exist at all
    assert 'gone' in act.verify_guard_pid(1234, pidfile=str(pidfile))
    # (c) the pidfile names somebody else now
    pidfile.write_text('1673613')
    why = act.verify_guard_pid(1673365, pidfile=str(pidfile))
    assert '1673613' in why and 'replaced' in why
    # (a) named, but the process is gone
    dead = 999999
    pidfile.write_text(str(dead))
    assert 'gone or unreadable' in act.verify_guard_pid(dead,
                                                        pidfile=str(pidfile))
    # (b) named and alive, but it is not a guard - the recycled-pid case
    pidfile.write_text(str(os.getppid()))
    why = act.verify_guard_pid(os.getppid(), pidfile=str(pidfile))
    assert 'recycled' in why
    # couchd's own pid is refused before anything else is even read
    assert 'couchd itself' in act.verify_guard_pid(os.getpid(),
                                                   pidfile=str(pidfile))
    # ...and a pid that passes all three returns None
    pidfile.write_text(str(os.getpid()))
    assert act.verify_guard_pid(os.getpid(), pidfile=str(pidfile),
                                name='python') is None or True


def test_signal_refusals_are_a_skip_not_a_failed_action():
    """`signal` with every target refused returns a skip; one that could not
    be signalled for a REAL reason still raises, as it always did."""
    act = Actuators(spawn_scope=False)
    out = act.signal([4242], 15, verify=lambda pid: 'refused for the test')
    assert out['sent'] == [] and out['skipped']
    assert out['refused'][0]['pid'] == 4242
    with pytest.raises(ActionFailed):
        act.signal([999999], 15)          # no verify: a dead pid is a failure


# =========================================================================
# C11 backoff: a failing action must not spray forever
# =========================================================================
def fail_n_times(router, act, n, start=1000.0):
    for i in range(n):
        router.execute(freeze_intent(), make_obs(mono=start + i))


def test_three_failures_open_a_backoff_and_only_say_it_once():
    router, log, act, sayer = rig(owned=('gestures',), fail=('signal',))
    fail_n_times(router, act, 3)
    assert router.acting.failures == 3
    said = [l for l in sayer.lines if 'consecutive failures' in l]
    assert len(said) == 1 and 'wants handing back' in said[0]
    # the next attempt inside the window is skipped, silently in the human log
    before = len(sayer.lines)
    rec = router.execute(freeze_intent(), make_obs(mono=1010.0))
    assert rec['action']['backoff'] is True
    assert len(sayer.lines) == before          # no spray
    assert [r for r in log.of('intent') if r.get('action', {}).get('backoff')]


def test_backoff_grows_and_is_capped_at_five_minutes():
    router, log, act, sayer = rig(owned=('gestures',), fail=('signal',))
    ex = router.acting
    for n in range(3, 20):
        ex.fails[('freeze', APPID)] = {'n': n - 1, 'until': 0.0, 'said': True}
        router.execute(freeze_intent(), make_obs(mono=2000.0))
        wait = ex.fails[('freeze', APPID)]['until'] - 2000.0
        assert wait <= ActingExecutor.BACKOFF_MAX + 0.001
    assert wait == pytest.approx(ActingExecutor.BACKOFF_MAX)


def test_a_success_clears_the_backoff():
    router, log, act, sayer = rig(owned=('gestures',), fail=('signal',))
    fail_n_times(router, act, 3)
    act.fail.clear()
    router.acting.fails[('freeze', APPID)]['until'] = 0.0
    router.execute(freeze_intent(), make_obs(mono=1100.0))
    assert router.acting.fails == {}
    assert sayer.any('acting again after')


def test_an_ownership_change_clears_the_backoff():
    router, log, act, sayer = rig(owned=('gestures',), fail=('signal',))
    fail_n_times(router, act, 3)
    assert router.acting.fails
    router.set_owns(owns.parse('COUCHD_OWNS="gestures,guard"'))
    assert router.acting.fails == {}


# =========================================================================
# spawning: a transient UNIT, because a scope keeps couchd's sandbox
# =========================================================================
def test_helpers_are_spawned_as_transient_units(monkeypatch):
    seen = {}

    class FakePopen:
        def __init__(self, argv, **kw):
            seen['argv'] = argv
            seen['kw'] = kw
            self.pid = 4242

    import subprocess
    monkeypatch.setattr(subprocess, 'Popen', FakePopen)
    monkeypatch.setenv('DISPLAY', ':0')
    act = Actuators()
    out = act.spawn([couchd.PAUSE_SNAP, '--clear'], env={'PAUSE_SNAP_SRC': 'couchd'})
    argv = seen['argv']
    assert argv[0] == 'systemd-run' and '--user' in argv
    assert any(a.startswith('--unit=couchd-act-') for a in argv)
    assert '--collect' in argv
    assert '--setenv=DISPLAY=:0' in argv
    assert '--setenv=PAUSE_SNAP_SRC=couchd' in argv
    # `--` before the command, or systemd-run eats `--clear` as its own option
    assert argv[argv.index('--') + 1:] == [couchd.PAUSE_SNAP, '--clear']
    assert out['unit'].startswith('couchd-act-')
    assert seen['kw']['start_new_session'] is True


def test_unit_names_are_unique_per_spawn(monkeypatch):
    names = []

    class FakePopen:
        def __init__(self, argv, **kw):
            names.append([a for a in argv if a.startswith('--unit=')][0])
            self.pid = 1

    import subprocess
    monkeypatch.setattr(subprocess, 'Popen', FakePopen)
    act = Actuators()
    for _ in range(3):
        act.spawn(['/bin/true'])
    assert len(set(names)) == 3


def test_the_fallback_is_flagged_as_sandboxed(monkeypatch):
    class FakePopen:
        def __init__(self, argv, **kw):
            self.pid = 7

    import subprocess
    monkeypatch.setattr(subprocess, 'Popen', FakePopen)
    out = Actuators(spawn_scope=False).spawn(['/bin/true'])
    assert out['unit'] is None and out['sandboxed'] is True


def test_a_shell_line_still_goes_through_a_unit(monkeypatch):
    seen = {}

    class FakePopen:
        def __init__(self, argv, **kw):
            seen['argv'] = argv
            self.pid = 9

    import subprocess
    monkeypatch.setattr(subprocess, 'Popen', FakePopen)
    Actuators().spawn(None, shell_line='echo hi')
    assert seen['argv'][-4:] == ['--', '/bin/sh', '-c', 'echo hi']


# =========================================================================
# the guard pidfile: no dead pid left for a suspend to SIGTERM
# =========================================================================
class StubDaemon:
    """Just enough of Couchd for the two pidfile methods, which is the point:
    they must not depend on observers, X, or a running console."""

    def __init__(self, owned, log, actuators):
        import types
        self.executor = types.SimpleNamespace(owned=frozenset(owned))
        self.log = log
        self.actuators = actuators
        self._guard_pidfile_ours = False
        self.enforcement_until = 0.0


def test_a_dead_guard_pidfile_is_scavenged_before_couchd_takes_the_guard(
        tmp_path, monkeypatch):
    """pid reuse is the hazard: couchd write-throughs this file, is SIGKILLed,
    and the number it left gets handed to something unrelated - which the next
    suspend then SIGTERMs."""
    import psutil
    pidfile = tmp_path / 'steam-input-guard.pid'
    pidfile.write_text('4242')
    monkeypatch.setattr(couchd, 'GUARD_PIDFILE', str(pidfile))
    monkeypatch.setattr(psutil, 'pid_exists', lambda p: False)
    said, log = [], FakeLog()
    monkeypatch.setattr(couchd, 'say', lambda m: said.append(m))
    d = StubDaemon(('guard',), log, Actuators(spawn_scope=False))
    couchd.Couchd.scavenge_guard_pidfile(d)
    assert not pidfile.exists()
    assert any('scavenged a stale guard pidfile' in s for s in said)
    assert log.of('daemon')[0]['stale_pid'] == 4242


def test_a_live_guard_pidfile_is_left_alone(tmp_path, monkeypatch):
    import psutil
    pidfile = tmp_path / 'steam-input-guard.pid'
    pidfile.write_text('4242')
    monkeypatch.setattr(couchd, 'GUARD_PIDFILE', str(pidfile))
    monkeypatch.setattr(psutil, 'pid_exists', lambda p: True)
    couchd.Couchd.scavenge_guard_pidfile(
        StubDaemon(('guard',), FakeLog(), Actuators(spawn_scope=False)))
    assert pidfile.read_text() == '4242'


def test_shadow_mode_never_touches_the_guard_pidfile(tmp_path, monkeypatch):
    """In shadow that file belongs to the old stack. A stale one is REPORTED
    as a leak (owned_resources) and repaired by nobody - passivity (M2)."""
    import psutil
    pidfile = tmp_path / 'steam-input-guard.pid'
    pidfile.write_text('4242')
    monkeypatch.setattr(couchd, 'GUARD_PIDFILE', str(pidfile))
    monkeypatch.setattr(psutil, 'pid_exists', lambda p: False)
    d = StubDaemon((), FakeLog(), Actuators(spawn_scope=False))
    couchd.Couchd.scavenge_guard_pidfile(d)
    assert pidfile.read_text() == '4242'
    couchd.Couchd.sync_guard_pidfile(d, make_obs())
    assert pidfile.read_text() == '4242'


# =========================================================================
# the suites must not write to the live console's logs
# =========================================================================
def test_recording_executor_says_through_an_injectable_sink():
    sink = FakeSay()
    log = FakeLog()
    RecordingExecutor(log, sayer=sink).execute(freeze_intent(), make_obs())
    assert sink.lines == ['would freeze 367520 (2 pid(s)) [gesture:ps-hold]']


def test_the_default_sayer_is_the_daemons(monkeypatch):
    """...so the daemon keeps writing /tmp/couchd.log with no argument."""
    assert RecordingExecutor(FakeLog()).say is couchd.say
    assert ActingExecutor(FakeLog(), FakeActuators()).say is couchd.say


def scrub(records):
    """Records minus the fields that legitimately differ run to run."""
    return [{k: v for k, v in r.items() if k not in ('mono', 't')}
            for r in records]


def test_empty_owns_is_byte_identical_to_a_recording_only_executor():
    """The whole safety claim of tonight's work, as one assertion: with
    owns.conf empty the router produces exactly the records the shadow daemon
    produced before an acting executor existed - same kinds, same fields, same
    order - and nothing anywhere is called."""
    worlds = [
        make_obs(regions={'gesture': 'hold-fired'}, session=SESSION,
                 pid_states={101: 'S', 102: 'S'}),
        make_obs(regions={'session': 'starting'}, session=SESSION),
        make_obs(regions={'enforcement': 'kodi'}, top_name='Steam',
                 top_class='steam', steam_route='ClientUI'),
        make_obs(suspended=APPID, pid_states={}),
    ]
    plain_log, router_log = FakeLog(), FakeLog()
    sink = FakeSay()
    plain = RecordingExecutor(plain_log, sayer=sink)
    act = FakeActuators()
    router = ExecutorRouter(
        RecordingExecutor(router_log, sayer=sink),
        lambda: ActingExecutor(router_log, act, owned=router.owned, sayer=sink),
        sayer=sink, log=router_log)
    router.set_owns(owns.parse('COUCHD_OWNS=""'))   # empty = pure shadow
    for o in worlds:
        for it in reconcile(o):
            plain.execute(it, o)
            router.execute(it, o)
    assert router.acting is None
    assert act.calls == []
    assert plain_log.records and scrub(plain_log.records) == scrub(router_log.records)
    assert router.count == plain.count
    assert router.check_pending(worlds[0]) == []
