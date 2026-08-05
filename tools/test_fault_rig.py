#!/usr/bin/env python3
"""Dry-run tests for tools/fault-rig.

NOTHING here touches the real box. Every path the rig knows about is bent into
tmp_path, every process call goes to a fake shell that records commands and
never executes, signals go to a recorder, and Kodi is a dict. The point is the
rig's OWN logic: the pre-checks that stop it running at the wrong moment, the
order it does things in (watchdog first), and the promise that `restore` puts
everything back however many times you run it.

The one thing these tests cannot prove is that couchd reacts. That is the
daytime session in docs/fault-rig-runbook.md.

Run:  couchd/.venv/bin/pytest tools/test_fault_rig.py -q
"""
import importlib.machinery
import importlib.util
import json
import os
import signal

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_loader(
    'fault_rig', importlib.machinery.SourceFileLoader(
        'fault_rig', os.path.join(HERE, 'fault-rig')))
fr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fr)


# =========================================================================
# the fake world
# =========================================================================
class World:
    """Units, processes, Kodi settings and a clock, all in memory."""

    def __init__(self, root):
        self.root = str(root)
        self.tmp = os.path.join(self.root, 'tmp')
        self.shadow = os.path.join(self.root, 'shadow')
        self.bin = os.path.join(self.root, 'bin')
        for d in (self.tmp, self.shadow, self.bin):
            os.makedirs(d, exist_ok=True)
        self.t = 1785900000.0
        self.units = {'couchd': True, 'pad-home': True}
        self.cmds = []                   # every command the rig "ran"
        self.signals = []                # (pid, signum)
        self.spawned = []                # argv lists
        self.procs = {}                  # pid -> cmdline
        self.alive_pids = set()
        self.kodi = {'input.enablejoystick': True}
        self.game_pids = []
        self.systemd_run_rc = 0
        self.spawn_raises = False
        self.lines = []
        self.on_sleep = None
        self._next_pid = 5000
        self.status = {'t': self.t, 'regions': {'session': 'none'},
                       'resource_leaks': []}
        self.write_status()

    # -- clock ------------------------------------------------------------
    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s
        if self.on_sleep:
            self.on_sleep(self)

    # -- files ------------------------------------------------------------
    def write_status(self):
        with open(os.path.join(self.shadow, 'status.json'), 'w') as fh:
            json.dump(self.status, fh)

    def shadow_log(self, records):
        import time as _t
        day = _t.strftime('%Y%m%d', _t.localtime(self.t))
        with open(os.path.join(self.shadow, 'couchd-%s.jsonl' % day), 'a') as fh:
            for r in records:
                fh.write(json.dumps(r) + '\n')

    def injections(self):
        import time as _t
        day = _t.strftime('%Y%m%d', _t.localtime(self.t))
        path = os.path.join(self.shadow, 'injections-%s.jsonl' % day)
        if not os.path.exists(path):
            return []
        return [json.loads(l) for l in open(path) if l.strip()]

    # -- the swappable callables -----------------------------------------
    def run(self, cmd, timeout=15):
        self.cmds.append(list(cmd))

        class R:
            returncode = 0
            stdout = ''
            stderr = ''
        r = R()
        if cmd[:1] == ['systemd-run']:
            r.returncode = self.systemd_run_rc
        elif cmd[:2] == ['systemctl', '--user']:
            action = cmd[2]
            if action == 'is-active':
                r.stdout = 'active' if self.units.get(cmd[3]) else 'inactive'
            elif action in ('start', 'stop'):
                for unit in cmd[3:]:
                    self.units[unit.split('.')[0]] = (action == 'start')
        elif cmd[0].endswith('game-pids'):
            r.stdout = '\n'.join(str(p) for p in self.game_pids)
            r.returncode = 0 if self.game_pids else 1
        return r

    def kill(self, pid, sig):
        self.signals.append((int(pid), int(sig)))
        if int(sig) == int(signal.SIGKILL):
            self.alive_pids.discard(int(pid))
            self.procs.pop(int(pid), None)

    def alive(self, pid):
        return int(pid) in self.alive_pids

    def cmdlines(self):
        return dict(self.procs)

    def jrpc(self, method, params):
        if method == 'Settings.GetSettingValue':
            return {'value': self.kodi.get(params['setting'])}
        if method == 'Settings.SetSettingValue':
            self.kodi[params['setting']] = params['value']
            return True
        return None

    def spawn(self, cmd):
        if self.spawn_raises:
            raise OSError('no fork for you')
        self.spawned.append(list(cmd))
        pid = self._next_pid
        self._next_pid += 1
        self.alive_pids.add(pid)
        # mirror what exec -a would produce, so decoy sweeping is exercised
        if len(cmd) >= 3 and cmd[0] == '/bin/bash':
            self.procs[pid] = cmd[2].split('"')[1] + ' 900'
        else:
            self.procs[pid] = ' '.join(cmd)
        return pid

    def out(self, line):
        self.lines.append(line)


def mkrig(tmp_path):
    w = World(tmp_path)
    rig = fr.Rig(tmp=w.tmp, shadow_dir=w.shadow, bin_dir=w.bin, run=w.run,
                 now=w.now, sleep=w.sleep, kill=w.kill, alive=w.alive,
                 cmdlines=w.cmdlines, jrpc=w.jrpc, spawn=w.spawn, out=w.out,
                 self_path=os.path.join(HERE, 'fault-rig'))
    return rig, w


def inject(rig, name, *extra):
    return fr.main(['inject', name, '--i-am-present', *extra], rig=rig)


# =========================================================================
# the catalogue itself
# =========================================================================
def test_catalogue_is_well_formed():
    names = [f['name'] for f in fr.FAULTS]
    assert len(names) == len(set(names))
    for f in fr.FAULTS:
        for key in ('name', 'audit', 'proves', 'legacy_repair', 'needs_game',
                    'forbids_game', 'pause_legacy', 'watch_s', 'expect',
                    'c17', 'tv'):
            assert key in f, (f['name'], key)
        assert f['expect'], f['name']
        assert any(m.get('required') for m in f['expect']), f['name']
        for m in f['expect']:
            assert m['kind'] in ('intent', 'invariant', 'agreement-excludes')
            assert m['deadline_s'] <= f['watch_s'], (f['name'], m)
        # a fault cannot both require and forbid a live game
        assert not (f['needs_game'] and f['forbids_game']), f['name']


def test_every_audit_repair_class_has_an_injection():
    """The four reconcile repairs couchd implements, plus guard invariant 1."""
    reasons = {m.get('reason') for f in fr.FAULTS for m in f['expect']}
    for reason in ('reconcile:orphaned-session',
                   'reconcile:stale-suspended-flag',
                   'reconcile:frozen-without-suspended-flag',
                   'reconcile:joystick-setting-drift',
                   'reconcile:frozen-game-visible',
                   'guard:steam-menu-holds-the-pad'):
        assert reason in reasons, reason


def test_list_names_every_fault(tmp_path):
    rig, w = mkrig(tmp_path)
    assert fr.main(['list'], rig=rig) == 0
    text = '\n'.join(w.lines)
    for f in fr.FAULTS:
        assert f['name'] in text
        assert f['proves'][:30] in text


# =========================================================================
# the operator acknowledgment
# =========================================================================
def test_refuses_without_i_am_present(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    assert fr.main(['inject', 'stale-suspended-flag'], rig=rig) == 3
    assert fr.main(['restore'], rig=rig) == 3
    assert w.cmds == [] and w.spawned == []
    assert not rig.journal.exists()


def test_read_only_commands_need_no_acknowledgment(tmp_path):
    rig, _ = mkrig(tmp_path)
    assert fr.main(['list'], rig=rig) == 0
    assert fr.main(['status'], rig=rig) == 0


# =========================================================================
# pre-checks
# =========================================================================
def test_refuses_when_couchd_is_down(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    w.units['couchd'] = False
    assert inject(rig, 'stale-suspended-flag') == 4
    assert 'couchd is not active' in capsys.readouterr().err
    assert not rig.journal.exists()


def test_refuses_when_couchd_status_is_stale(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    w.status['t'] = w.t - 600
    w.write_status()
    assert inject(rig, 'stale-suspended-flag') == 4
    assert 'not observing' in capsys.readouterr().err


def test_refuses_when_a_real_game_is_running(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    w.game_pids = [111, 222]
    assert inject(rig, 'orphaned-session') == 4
    err = capsys.readouterr().err
    assert 'real game session is running' in err
    assert not os.path.exists(rig.flag_path('game-session'))


def test_refuses_when_no_game_and_the_fault_needs_one(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    assert inject(rig, 'menu-capture') == 4
    assert 'needs a live game session' in capsys.readouterr().err


def test_refuses_while_the_guard_is_still_working(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    w.alive_pids.add(4321)
    with open(rig.flag_path('steam-input-guard.pid'), 'w') as fh:
        fh.write('4321')
    assert inject(rig, 'stale-suspended-flag') == 4
    assert 'steam-input-guard is running' in capsys.readouterr().err


def test_refuses_when_an_injection_is_already_staged(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    rig.journal.start(id='x', fault='y', t=w.t)
    assert inject(rig, 'stale-suspended-flag') == 4
    assert 'already staged' in capsys.readouterr().err


def test_refuses_when_the_legacy_loop_is_not_running(tmp_path, capsys):
    """If pad-home is already down the rig cannot promise to put it back."""
    rig, w = mkrig(tmp_path)
    w.units['pad-home'] = False
    assert inject(rig, 'stale-suspended-flag') == 4
    assert 'cannot pause it' in capsys.readouterr().err


def test_refuses_to_clobber_an_existing_flag(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    with open(rig.flag_path('game-session'), 'w') as fh:
        fh.write('999 steam 413150')
    assert inject(rig, 'stale-suspended-flag') == 4
    assert 'already exists' in capsys.readouterr().err
    assert open(rig.flag_path('game-session')).read() == '999 steam 413150'


def test_refuses_when_old_decoys_are_still_alive(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    w.alive_pids.add(9001)
    w.procs[9001] = 'reaper SteamLaunch AppId=999999 -- %s 900' % fr.DECOY_TOKEN
    assert inject(rig, 'stale-suspended-flag') == 4
    assert 'decoy processes from an earlier run' in capsys.readouterr().err


def test_live_flag_rejected_for_faults_without_a_live_mode(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    assert inject(rig, 'stale-suspended-flag', '--live') == 4
    assert 'no --live mode' in capsys.readouterr().err


# =========================================================================
# the watchdog is armed BEFORE anything is broken
# =========================================================================
def test_watchdog_is_armed_before_any_mutation(tmp_path):
    rig, w = mkrig(tmp_path)
    assert inject(rig, 'stale-suspended-flag', '--no-watch', '--hold') == 0
    names = [c[0] for c in w.cmds]
    assert 'systemd-run' in names
    arm = names.index('systemd-run')
    stops = [i for i, c in enumerate(w.cmds)
             if c[:4] == ['systemctl', '--user', 'stop', 'pad-home']]
    assert stops and min(stops) > arm
    data = rig.journal.load()
    assert data['watchdog']['kind'] == 'systemd'
    assert data['timeout_s'] >= fr.MIN_TIMEOUT_S


def test_watchdog_falls_back_to_a_background_process(tmp_path):
    rig, w = mkrig(tmp_path)
    w.systemd_run_rc = 1
    assert inject(rig, 'stale-suspended-flag', '--no-watch', '--hold') == 0
    assert rig.journal.load()['watchdog']['kind'] == 'process'
    assert any('_watchdog' in c for c in w.spawned[0])


def test_refuses_to_inject_when_no_watchdog_can_be_armed(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    w.systemd_run_rc = 1
    w.spawn_raises = True
    assert inject(rig, 'stale-suspended-flag', '--no-watch') == 4
    assert 'cannot arm the auto-restore watchdog' in capsys.readouterr().err
    assert not rig.journal.exists()
    assert not os.path.exists(rig.flag_path('game-suspended'))
    assert w.units['pad-home'] is True


def test_timeout_is_clamped(tmp_path):
    rig, w = mkrig(tmp_path)
    inject(rig, 'stale-suspended-flag', '--no-watch', '--hold',
           '--timeout', '99999')
    assert rig.journal.load()['timeout_s'] == fr.MAX_TIMEOUT_S


# =========================================================================
# staging: each fault actually stages what it says
# =========================================================================
def test_orphaned_session_stages_a_dead_launcher(tmp_path):
    rig, w = mkrig(tmp_path)
    assert inject(rig, 'orphaned-session', '--no-watch', '--hold') == 0
    raw = open(rig.flag_path('game-session')).read().split()
    assert not w.alive(int(raw[0])) and raw[1] == 'steam'
    assert w.units['pad-home'] is False          # repair loop paused


def test_stale_suspended_flag_stages_an_appid_that_is_not_bigpicture(tmp_path):
    rig, w = mkrig(tmp_path)
    inject(rig, 'stale-suspended-flag', '--no-watch', '--hold')
    value = open(rig.flag_path('game-suspended')).read()
    assert value == fr.DECOY_APPID != 'bigpicture'


def test_joystick_drift_flips_the_setting_and_refuses_if_already_wrong(tmp_path):
    rig, w = mkrig(tmp_path)
    inject(rig, 'joystick-drift', '--no-watch', '--hold')
    assert w.kodi['input.enablejoystick'] is False
    fr.restore(rig)
    assert w.kodi['input.enablejoystick'] is True
    w.kodi['input.enablejoystick'] = False       # already drifted on its own
    assert inject(rig, 'joystick-drift', '--no-watch') == 4


def test_lost_thaw_decoy_is_a_reaper_child_and_gets_stopped(tmp_path):
    rig, w = mkrig(tmp_path)
    inject(rig, 'lost-thaw', '--no-watch', '--hold')
    pid = rig.journal.load()['undo'][1]['pid']
    assert fr.REAPER in w.procs[pid] and fr.DECOY_TOKEN in w.procs[pid]
    assert (pid, int(signal.SIGSTOP)) in w.signals
    assert not os.path.exists(rig.flag_path('game-suspended'))   # the fault


def test_lost_thaw_live_freezes_the_real_session(tmp_path):
    rig, w = mkrig(tmp_path)
    w.game_pids = [3001, 3002, 3003]
    with open(rig.flag_path('game-session'), 'w') as fh:
        fh.write('3000 steam 413150')
    assert inject(rig, 'lost-thaw', '--live', '--no-watch', '--hold') == 0
    for pid in w.game_pids:
        assert (pid, int(signal.SIGSTOP)) in w.signals
    assert w.spawned == []                       # no decoys in live mode
    fr.restore(rig)
    for pid in w.game_pids:
        assert (pid, int(signal.SIGCONT)) in w.signals


def test_lost_thaw_live_refuses_if_the_game_is_already_paused(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    w.game_pids = [3001]
    with open(rig.flag_path('game-suspended'), 'w') as fh:
        fh.write('413150')
    assert inject(rig, 'lost-thaw', '--live', '--no-watch') == 4
    assert 'already paused' in capsys.readouterr().err


def test_frozen_game_visible_stages_process_flag_and_window(tmp_path):
    rig, w = mkrig(tmp_path)
    inject(rig, 'frozen-game-visible', '--no-watch', '--hold')
    ops = [u['op'] for u in rig.journal.load()['undo']]
    assert ops.count('decoy') == 2 and 'thaw' in ops and 'flag' in ops
    assert open(rig.flag_path('game-suspended')).read() == fr.DECOY_APPID
    window = [c for c in w.spawned if '_decoy-window' in c]
    assert len(window) == 1 and fr.DECOY_TOKEN in window[0]


def test_bystander_decoy_looks_like_steamapps_but_is_not_a_reaper_child(tmp_path):
    rig, w = mkrig(tmp_path)
    inject(rig, 'bystander-process', '--no-watch', '--hold')
    pid = rig.journal.load()['undo'][0]['pid']
    assert 'steamapps/common' in w.procs[pid]
    assert fr.REAPER not in w.procs[pid]
    assert w.units['pad-home'] is True            # no pause needed for this one


def test_menu_capture_opens_the_steam_menu_once_the_hold_lands(tmp_path):
    """The operator's PS hold writes the paused flag; that is our cue."""
    rig, w = mkrig(tmp_path)
    w.game_pids = [3001]
    with open(rig.flag_path('game-session'), 'w') as fh:
        fh.write('3000 steam 413150')

    def thumb(world):
        if world.t > 1785900002.0 and not os.path.exists(
                rig.flag_path('game-suspended')):
            with open(rig.flag_path('game-suspended'), 'w') as fh:
                fh.write('413150')
    w.on_sleep = thumb
    assert inject(rig, 'menu-capture', '--no-watch', '--hold') == 0
    vpad = [c for c in w.cmds if c[0].endswith('vpad')]
    assert ['up'] == vpad[0][1:] and ['press', 'guide'] == vpad[1][1:]
    assert w.units['pad-home'] is True            # the gesture path stays live
    fr.restore(rig)
    assert [c[1:] for c in w.cmds if c[0].endswith('vpad')][-1] == ['quit']


def test_menu_capture_waits_for_the_operator_and_gives_up_cleanly(tmp_path, capsys):
    rig, w = mkrig(tmp_path)
    w.game_pids = [3001]
    with open(rig.flag_path('game-session'), 'w') as fh:
        fh.write('3000 steam 413150')
    assert inject(rig, 'menu-capture', '--no-watch') == 4
    assert 'no PS hold seen' in capsys.readouterr().err
    assert w.t > 1785900000.0                     # it really waited
    assert not any('vpad' in c[0] for c in w.cmds)


# =========================================================================
# restore
# =========================================================================
def test_restore_puts_everything_back(tmp_path):
    rig, w = mkrig(tmp_path)
    inject(rig, 'frozen-game-visible', '--no-watch', '--hold')
    assert fr.restore(rig) == 0
    assert not os.path.exists(rig.flag_path('game-suspended'))
    assert not rig.journal.exists()
    assert w.units['pad-home'] is True
    assert rig.decoys() == []
    assert any(c[:3] == ['systemctl', '--user', 'stop'] and
               'fault-rig-restore.timer' in c for c in w.cmds)


def test_restore_is_idempotent(tmp_path):
    rig, w = mkrig(tmp_path)
    inject(rig, 'orphaned-session', '--no-watch', '--hold')
    assert fr.restore(rig) == 0
    before = len(w.cmds)
    assert fr.restore(rig) == 0
    assert fr.restore(rig) == 0
    assert not os.path.exists(rig.flag_path('game-session'))
    assert w.units['pad-home'] is True
    assert len(w.cmds) > before                   # ran, just changed nothing


def test_restore_never_deletes_a_flag_someone_else_rewrote(tmp_path):
    """A real session that starts during the window must survive the abort."""
    rig, w = mkrig(tmp_path)
    inject(rig, 'orphaned-session', '--no-watch', '--hold')
    with open(rig.flag_path('game-session'), 'w') as fh:
        fh.write('4242 steam 413150')              # the real thing appeared
    fr.restore(rig)
    assert open(rig.flag_path('game-session')).read() == '4242 steam 413150'
    assert any('left' in l and 'alone' in l for l in w.lines)


def test_restore_sweeps_decoys_with_no_journal_at_all(tmp_path):
    rig, w = mkrig(tmp_path)
    w.alive_pids.add(9100)
    w.procs[9100] = 'reaper SteamLaunch AppId=999999 -- %s 900' % fr.DECOY_TOKEN
    assert fr.restore(rig) == 0
    assert (9100, int(signal.SIGCONT)) in w.signals
    assert (9100, int(signal.SIGKILL)) in w.signals
    assert rig.decoys() == []


def test_restore_restarts_the_legacy_loop_even_without_a_journal(tmp_path):
    rig, w = mkrig(tmp_path)
    w.units['pad-home'] = False
    fr.restore(rig)
    assert w.units['pad-home'] is True
    assert any('was down' in l for l in w.lines)


def test_restore_logs_a_marker_the_differ_can_read(tmp_path):
    rig, w = mkrig(tmp_path)
    inject(rig, 'stale-suspended-flag', '--no-watch', '--hold')
    fr.restore(rig, by='watchdog')
    events = [m['event'] for m in w.injections()]
    assert events == ['inject', 'restore']
    rec = w.injections()[-1]
    assert rec['by'] == 'watchdog' and rec['legacy_active'] is True
    assert rec['failed'] == []


# =========================================================================
# markers and evidence
# =========================================================================
def test_inject_marker_carries_the_c17_expectation(tmp_path):
    rig, w = mkrig(tmp_path)
    inject(rig, 'orphaned-session', '--no-watch', '--hold')
    rec = w.injections()[0]
    assert rec['kind'] == 'injection' and rec['event'] == 'inject'
    assert rec['fault'] == 'orphaned-session'
    assert rec['legacy_paused'] is True
    assert rec['expected_detection'].startswith('the launch grace')
    assert rec['expect'][0]['reason'] == 'reconcile:orphaned-session'
    assert rec['diff_hint'].startswith('tools/shadow-diff --since')
    assert isinstance(rec['t'], float) and rec['iso']


def test_everything_written_stays_inside_the_sandbox(tmp_path):
    rig, w = mkrig(tmp_path)
    inject(rig, 'frozen-game-visible', '--no-watch', '--hold')
    fr.restore(rig)
    for path in (rig.flag_path('game-suspended'), rig.journal.path,
                 rig.injections_path(), rig.shadow_log_path()):
        assert os.path.abspath(path).startswith(str(tmp_path))


# =========================================================================
# detection: reading couchd back out of the shadow log
# =========================================================================
def intent(t, reason, verb, subject='kodi'):
    return {'kind': 'intent', 't': t, 'verb': verb, 'subject': subject,
            'args': {}, 'reason': reason, 'seq': 1}


def test_detects_the_expected_repair_and_its_latency(tmp_path):
    rig, w = mkrig(tmp_path)
    fault = fr.BY_NAME['stale-suspended-flag']
    t0 = w.t
    w.shadow_log([intent(t0 - 5, 'reconcile:stale-suspended-flag', 'clear_flag'),
                  intent(t0 + 1.5, 'reconcile:stale-suspended-flag', 'clear_flag')])
    rows = fr.evaluate(rig.shadow_records(t0), t0, fault, {})
    assert rows[0][1] is True and rows[0][2] == 1.5
    assert fr.passed(rows) is True                # the optional leak row missing


def test_a_late_decision_is_a_miss(tmp_path):
    rig, w = mkrig(tmp_path)
    fault = fr.BY_NAME['stale-suspended-flag']
    t0 = w.t
    w.shadow_log([intent(t0 + 99, 'reconcile:stale-suspended-flag', 'clear_flag')])
    rows = fr.evaluate(rig.shadow_records(t0), t0, fault, {})
    assert rows[0][1] is False and 'LATE' in rows[0][3]
    assert fr.passed(rows) is False


def test_silence_is_a_miss(tmp_path):
    rig, w = mkrig(tmp_path)
    rows = fr.evaluate([], w.t, fr.BY_NAME['stale-suspended-flag'], {})
    assert rows[0][1] is False and rows[0][2] is None
    assert fr.passed(rows) is False


def test_the_owned_resources_leak_row_is_context_not_a_gate(tmp_path):
    rig, w = mkrig(tmp_path)
    fault = fr.BY_NAME['stale-suspended-flag']
    t0 = w.t
    w.shadow_log([
        intent(t0 + 1, 'reconcile:stale-suspended-flag', 'clear_flag'),
        {'kind': 'invariant', 't': t0 + 2, 'ok': False,
         'name': 'owned_resources',
         'leaks': ['suspended flag with no frozen processes']}])
    rows = fr.evaluate(rig.shadow_records(t0), t0, fault, {})
    assert [r[4] for r in rows] == [True, False]  # required, then context
    assert all(r[1] for r in rows)


def test_bystander_passes_when_couchd_ignores_the_decoy(tmp_path):
    rig, w = mkrig(tmp_path)
    t0 = w.t
    w.shadow_log([{'kind': 'agreement', 't': t0 + 3, 'couchd_would_freeze': [],
                   'game_pids_tree': [], 'steam_ledger': []}])
    rows = fr.evaluate(rig.shadow_records(t0), t0,
                       fr.BY_NAME['bystander-process'], {'pid': 5000})
    assert fr.passed(rows) is True


def test_bystander_fails_loudly_when_couchd_claims_the_decoy(tmp_path):
    rig, w = mkrig(tmp_path)
    t0 = w.t
    w.shadow_log([{'kind': 'agreement', 't': t0 + 3,
                   'couchd_would_freeze': [5000], 'game_pids_tree': [5000],
                   'steam_ledger': []}])
    rows = fr.evaluate(rig.shadow_records(t0), t0,
                       fr.BY_NAME['bystander-process'], {'pid': 5000})
    assert rows[0][1] is False and 'claimed the decoy' in rows[0][3]


def test_watch_stops_as_soon_as_couchd_decides(tmp_path):
    rig, w = mkrig(tmp_path)
    fault = fr.BY_NAME['stale-suspended-flag']
    t0 = w.t
    w.shadow_log([
        intent(t0 + 1, 'reconcile:stale-suspended-flag', 'clear_flag'),
        {'kind': 'invariant', 't': t0 + 1, 'ok': False,
         'name': 'owned_resources',
         'leaks': ['suspended flag with no frozen processes']}])
    rows = fr.watch(rig, t0, fault, {}, 30.0)
    assert fr.passed(rows) and w.t - t0 < 5.0     # did not burn the window


def test_inject_returns_nonzero_when_couchd_says_nothing(tmp_path):
    rig, w = mkrig(tmp_path)
    assert inject(rig, 'stale-suspended-flag', '--watch', '3') == 1
    detect = [m for m in w.injections() if m['event'] == 'detect'][0]
    assert detect['ok'] is False
    assert not os.path.exists(rig.flag_path('game-suspended'))   # auto-restored


def test_inject_returns_zero_and_restores_when_couchd_repairs(tmp_path):
    rig, w = mkrig(tmp_path)
    # couchd's answer is already in the log, dated inside the watch window
    w.shadow_log([intent(w.t + 1, 'reconcile:stale-suspended-flag',
                         'clear_flag')])
    assert inject(rig, 'stale-suspended-flag', '--watch', '10') == 0
    assert not rig.journal.exists()
    assert w.units['pad-home'] is True


# =========================================================================
# a clean sweep: every no-game fault stages and unstages without residue
# =========================================================================
@pytest.mark.parametrize('name', [f['name'] for f in fr.FAULTS
                                  if not f['needs_game']])
def test_stage_then_restore_leaves_no_residue(tmp_path, name):
    rig, w = mkrig(tmp_path)
    assert inject(rig, name, '--no-watch', '--hold') == 0
    assert fr.restore(rig) == 0
    assert rig.decoys() == []
    assert not rig.journal.exists()
    assert w.units['couchd'] is True and w.units['pad-home'] is True
    assert w.kodi['input.enablejoystick'] is True
    for flag in ('game-session', 'game-suspended'):
        assert not os.path.exists(rig.flag_path(flag))
    stopped = {p for p, s in w.signals if s == int(signal.SIGSTOP)}
    killed = {p for p, s in w.signals if s == int(signal.SIGKILL)}
    assert stopped <= killed                      # nothing left frozen


def test_status_shows_a_staged_injection_and_the_abort_line(tmp_path):
    rig, w = mkrig(tmp_path)
    inject(rig, 'orphaned-session', '--no-watch', '--hold')
    w.lines.clear()
    assert fr.main(['status'], rig=rig) == 0
    text = '\n'.join(w.lines)
    assert 'STAGED: orphaned-session' in text
    assert 'restore --i-am-present' in text
    assert 'auto-restore in' in text
    assert 'STOPPED' in text                      # the paused repair loop


def test_dead_pid_is_really_dead(tmp_path):
    rig, w = mkrig(tmp_path)
    pid = fr.dead_pid(rig)
    assert not w.alive(pid) and pid > 4000000
