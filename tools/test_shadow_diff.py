#!/usr/bin/env python3
"""Synthetic fixtures for tools/shadow-diff, using couchd's REAL record schemas.

Every fixture is written to a temp file inside the test; nothing here reads the
real corpus, the box, or any daemon.

Real shapes mirrored here (couchd, 4 Aug 2026):
  intent      {kind:"intent", t, seq, mono, verb, subject, args, reason, regions, predict}
  obs         {kind:"obs", t, source: pad|flags|pids|kodi|x11|steam|trigger|world, ...}
  transition  {kind:"transition", t, region, from, to, reason}   region may be game:<appid>
  agreement   {kind:"agreement", t, metric, ...}
  observer_blind {kind:"observer_blind", t, source, why, age_s, detail}
  snapshot    {kind:"snapshot", t, why, flags, pids, joystick, kodi_window, top,
               focused, steam_route, ui_mode, ledger, pad, regions, games}
  legacy      {t, src, verb, subject, args}   (no kind field at all)

Run:  python3 -m pytest tools/test_shadow_diff.py     (pytest installed)
      python3 tools/test_shadow_diff.py               (plain runner, no pytest)
"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_loader(
    'shadow_diff', importlib.machinery.SourceFileLoader(
        'shadow_diff', os.path.join(HERE, 'shadow-diff')))
sd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sd)

T0 = 1785878000.0          # a fixed evening epoch, so fixtures are deterministic
_SEQ = [0]


def write(tmp, name, records):
    p = os.path.join(tmp, name)
    with open(p, 'w') as fh:
        for r in records:
            fh.write(json.dumps(r) + '\n')
    return p


def legacy(t, verb, subject=None, src='watcher', **args):
    return {'t': T0 + t, 'src': src, 'verb': verb, 'subject': subject, 'args': args}


def couchd(t, verb, subject=None, reason='ps-hold', **args):
    _SEQ[0] += 1
    return {'kind': 'intent', 't': T0 + t, 'seq': _SEQ[0], 'mono': t, 'verb': verb,
            'subject': subject, 'args': args, 'reason': reason,
            'regions': {'input_ownership': 'kodi', 'gesture': 'idle'}, 'predict': {}}


def obs(t, source, **kw):
    return dict({'kind': 'obs', 't': T0 + t, 'source': source}, **kw)


def transition(t, region, frm, to, reason):
    return {'kind': 'transition', 't': T0 + t, 'region': region, 'from': frm, 'to': to,
            'reason': reason}


def snapshot(t, why='tick', **kw):
    base = {'kind': 'snapshot', 't': T0 + t, 'why': why,
            'flags': {'session': None, 'suspended': None}, 'pids': {}, 'joystick': True,
            'kodi_window': 10000, 'top': ['Kodi', 'Kodi'], 'focused': 'Kodi',
            'steam_route': '', 'ui_mode': 7, 'ledger': {},
            'pad': {'present': False, 'down': False},
            'regions': {'input_ownership': 'kodi', 'gesture': 'idle'}, 'games': {}}
    base.update(kw)
    return base


def heartbeat(t_from, t_to, step=30):
    """The world/snapshot cadence the observer-health gate keys off."""
    return [snapshot(t) for t in range(t_from, t_to, step)]


def sections(rep):
    return {s: [r for r in rep['rows'] if r['section'] == s] for s in sd.SECTIONS}


def run(tmp, lrecs, crecs, snaps=None):
    lp = write(tmp, 'legacy.jsonl', lrecs)
    cp = write(tmp, 'couchd.jsonl', crecs)
    sp = write(tmp, 'snaps.jsonl', snaps) if snaps else None
    return sd.build(lp, cp, sp)


# ---------------------------------------------------------------- clean evening
def test_clean_evening():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'freeze', '730', pids=[100, 101], resolver='game-pids'),
                   legacy(0.4, 'route_pad', 'kodi'),
                   legacy(30.0, 'thaw', '730', pids=[100, 101],
                          resolver='game-pids')],
                  [couchd(0.1, 'freeze', '730', pids=[100, 101],
                          resolver='gameprocess_log'),
                   couchd(0.5, 'route_pad', 'kodi'),
                   couchd(30.2, 'thaw', '730', pids=[100, 101], reason='resume',
                          resolver='gameprocess_log'),
                   obs(0.3, 'pad', event='BTN_MODE', value=0, kernel_t=T0 + 0.28),
                   transition(0.31, 'gesture', 'hold-fired', 'idle',
                              reason='hold-release')])
        s = sections(rep)
        assert rep['matched_total'] == 3, rep['matched_total']
        assert rep['matched_clean'] == 3
        assert all(not s[k] for k in sd.SECTIONS), s
        assert rep['validity']['verdict'] == 'VALID', rep['validity']
        assert rep['gating_count'] == 0
        assert rep['offsets']['route_pad']['n'] == 1
        assert 'PASS route_pad(kodi) after gesture release' in sd.render(rep)


# ------------------------------------------------------------ couchd-only diff
def test_couchd_only():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'freeze', '730', pids=[100], resolver='game-pids')],
                  [couchd(0.1, 'freeze', '730', pids=[100], resolver='game-pids'),
                   couchd(3.0, 'iconify', 'steam-bigpicture', reason='guard-enforce')])
        s = sections(rep)
        assert len(s['COUCHD-ONLY']) == 1, s
        assert s['COUCHD-ONLY'][0]['verb'] == 'iconify'
        assert s['COUCHD-ONLY'][0]['label'] == ''      # left for hand triage
        assert not s['LEGACY-ONLY'] and not s['BOTH-BUT-DIFFERENT']


# ------------------------------------------------------------- legacy-only diff
def test_legacy_only():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'route_pad', 'game'),
                   legacy(60.0, 'show', 'kodi', src='guard')],   # way outside +/-2s
                  [couchd(0.05, 'route_pad', 'game')])
        s = sections(rep)
        assert [r['verb'] for r in s['LEGACY-ONLY']] == ['show'], s
        assert rep['matched_total'] == 1
        assert not rep['cooldown_associated']


# ------------------------------------------------------- cooldown many-to-one
def test_cooldown_association():
    """couchd emits one route_pad per (verb,subject,reason) per 3s gesture cooldown;
    legacy's repeats inside that window are not LEGACY-ONLY divergences."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'route_pad', 'kodi'),
                   legacy(1.2, 'route_pad', 'kodi'),      # repeat, inside 3s
                   legacy(2.6, 'route_pad', 'kodi'),      # repeat, inside 3s
                   legacy(40.0, 'route_pad', 'kodi')],    # long after: real divergence
                  [couchd(0.1, 'route_pad', 'kodi', reason='ps-hold')])
        s = sections(rep)
        assert rep['matched_total'] == 1
        assert len(rep['cooldown_associated']) == 2, rep['cooldown_associated']
        assert all('cooldown-associated' in c['note']
                   for c in rep['cooldown_associated'])
        assert [round(r['t'] - T0, 1) for r in s['LEGACY-ONLY']] == [40.0], \
            s['LEGACY-ONLY']
        assert 'COOLDOWN-ASSOCIATED' in sd.render(rep)


def test_cooldown_class_from_reason():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'show', 'kodi', src='guard'),
                   legacy(20.0, 'show', 'kodi', src='guard')],   # inside 30s repair
                  [couchd(0.1, 'show', 'kodi', reason='reconcile-repair')])
        assert len(rep['cooldown_associated']) == 1
        assert not sections(rep)['LEGACY-ONLY']
        assert sd.cooldown_s('reconcile-repair') == 30.0
        assert sd.cooldown_s('ps-hold') == 3.0
        assert sd.cooldown_s('guard-enforce') == 5.0
        assert sd.cooldown_s('session-started') == 10.0     # default class


# ---------------------------------------------------------------- pid mismatch
def test_pid_set_mismatch_is_gating():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'freeze', '413090', pids=[100, 101, 102],
                          resolver='game-pids')],
                  [couchd(1.2, 'freeze', '413090', pids=[100, 101, 102, 103, 104, 105],
                          resolver='gameprocess_log')])
        s = sections(rep)
        assert len(s['BOTH-BUT-DIFFERENT']) == 1, s
        row = s['BOTH-BUT-DIFFERENT'][0]
        assert 'SET-MISMATCH' in row['flags']
        assert row['label'] == ''            # too big a delta for the reaper whitelist
        assert rep['gating_count'] == 1
        assert '103' in row['note']
        assert 'gating' in sd.render(rep)


# ------------------------------------------------------- ordering violation
def test_order_violation_despite_in_window_match():
    """route_pad(kodi) matched inside +/-2s but fired BEFORE the release edge."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(10.0, 'route_pad', 'kodi')],
                  [couchd(9.6, 'route_pad', 'kodi'),
                   transition(10.4, 'gesture', 'hold-fired', 'idle',
                              reason='hold-release')])
        s = sections(rep)
        assert rep['matched_total'] == 1
        assert len(s['BOTH-BUT-DIFFERENT']) == 1, s
        assert 'ORDER' in s['BOTH-BUT-DIFFERENT'][0]['flags']
        assert rep['gating_count'] == 1
        fails = [a for a in rep['assertions'] if a['ok'] is False]
        assert fails and 'gesture release' in fails[0]['name']


def test_pad_kernel_timestamp_beats_log_write_time():
    """BTN_MODE release edges use kernel_t, not the log-write time (R4)."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(5.0, 'route_pad', 'kodi')],
                  [couchd(5.0, 'route_pad', 'kodi'),
                   # written late, but the kernel saw the release before the intent
                   obs(5.9, 'pad', event='BTN_MODE', value=0, kernel_t=T0 + 4.8)])
        assert [a['ok'] for a in rep['assertions']
                if 'gesture release' in a['name']] == [True], rep['assertions']
        assert not sections(rep)['BOTH-BUT-DIFFERENT']


# --------------------------------------------------------------- T5 auto-label
def test_t5_autolabels():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'set_flag', 'suspended', src='game-launch'),
                   legacy(0.1, 'freeze', '730', pids=[100, 101, 102],
                          resolver='game-pids'),
                   legacy(60.0, 'quit', 'bigpicture', src='game-launch',
                          appid='bigpicture')],
                  [couchd(0.2, 'freeze', '730', pids=[100, 101, 102, 103],
                          resolver='gameprocess_log')])
        s = sections(rep)
        by_verb = {r['verb']: r for r in rep['rows']}
        assert by_verb['set_flag']['label'] == 'T5'
        assert 'flag verbs' in by_verb['set_flag']['note']
        assert by_verb['quit']['label'] == 'T5'
        assert 'R7(b)' in by_verb['quit']['note']
        assert by_verb['freeze']['label'] == 'T5'      # one transient reaper child
        assert 'reaper' in by_verb['freeze']['note']
        assert len(s['BOTH-BUT-DIFFERENT']) == 1
        assert rep['gating_count'] == 0 and rep['whitelisted_hard'] == 1


def test_t5_r7a_bigpicture_hold():
    """Legacy's reconcile pulls the pad off Kodi ~10s after a pure Big Picture hold."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(10.0, 'route_pad', 'game', src='watcher',
                          reason='reconcile')],
                  [couchd(0.0, 'freeze', 'bigpicture', pids=[], reason='ps-hold'),
                   couchd(0.2, 'route_pad', 'kodi', release_t=T0 - 0.1)])
        rows = {r['verb'] + r['section']: r for r in rep['rows']}
        r = rows['route_padLEGACY-ONLY']
        assert r['label'] == 'T5' and 'R7(a)' in r['note'], r


# ------------------------------------------------------------ agreement records
def test_agreement_disagreement_is_gating():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'kodi')],
                  [couchd(0.1, 'show', 'kodi', reason='guard-enforce'),
                   {'kind': 'agreement', 't': T0 + 5, 'metric': 'freeze_set',
                    'agree': True, 'ledger_only': [], 'game_pids_only': []},
                   {'kind': 'agreement', 't': T0 + 9, 'metric': 'freeze_set',
                    'agree': False, 'ledger_only': ['9004'],
                    'game_pids_only': ['9010']},
                   {'kind': 'agreement', 't': T0 + 12, 'metric': 'ps_press_channels',
                    'evdev_presses': 2, 'steam_guide_lines': 2,
                    'pad_first_event_latency_s': 0.9}])
        assert rep['agreement']['total'] == 3
        assert len(rep['agreement']['disagreements']) == 1
        assert rep['gating_count'] == 1
        txt = sd.render(rep)
        assert 'AGREEMENT' in txt and 'freeze_set' in txt
        # a non-empty *_only list alone is enough, even without agree=false
        assert sd.disagrees({'metric': 'freeze_set', 'ledger_only': ['1']})
        assert not sd.disagrees({'metric': 'ps_press_channels', 'evdev_presses': 1})


# ------------------------------------------------------- observer-health gate
def test_observer_blind_record_invalidates_evening():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'freeze', '730', pids=[100], resolver='game-pids'),
                   legacy(1800.0, 'thaw', '730', pids=[100], resolver='game-pids')],
                  [couchd(0.1, 'freeze', '730', pids=[100], resolver='game-pids'),
                   couchd(1800.1, 'thaw', '730', pids=[100], resolver='game-pids'),
                   {'kind': 'observer_blind', 't': T0 + 401, 'source': 'steam',
                    'why': 'truncation', 'age_s': 880,
                    'detail': 'gameprocess_log.txt shrank (dev,ino,size)'}],
                  heartbeat(0, 1810))
        assert rep['validity']['verdict'] == 'INVALID', rep['validity']
        why = ' '.join(rep['validity']['reasons'])
        assert 'steam' in why and 'observer_blind' in why, why
        assert rep['matched_total'] == 2         # diffing itself still ran


def test_short_blind_is_a_note_not_a_verdict():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'kodi')],
                  [couchd(0.1, 'show', 'kodi'),
                   {'kind': 'observer_blind', 't': T0 + 60, 'source': 'steam',
                    'why': 'rotation', 'age_s': 12, 'detail': 'reopened'}],
                  heartbeat(0, 700))
        assert rep['validity']['verdict'] == 'VALID', rep['validity']
        assert any('observer_blind' in n for n in rep['notes'])


def test_heartbeat_gap_invalidates():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'kodi')],
                  [couchd(0.1, 'show', 'kodi')] +
                  [obs(t, 'world', session=None, suspended=None, pids={},
                       pad={'present': False}) for t in list(range(0, 200, 30)) +
                   list(range(900, 1000, 30))])            # 700s hole
        assert rep['validity']['verdict'] == 'INVALID'
        assert any('heartbeat gap' in r for r in rep['validity']['reasons'])


def test_quiet_change_driven_source_is_only_a_note():
    """Silence on a change-driven source must NOT invalidate an evening."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'kodi')],
                  [couchd(0.1, 'show', 'kodi')], heartbeat(0, 1800))
        assert rep['validity']['verdict'] == 'VALID', rep['validity']
        assert any('no x11 observations' in n for n in rep['notes'])
        silent = {s['source'] for s in rep['observer_health']['sources']
                  if not s['present']}
        assert 'x11' in silent and 'pids' in silent


def test_pad_observer_silent_while_pad_present_invalidates():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'kodi')],
                  [couchd(0.1, 'show', 'kodi')],
                  [snapshot(t, pad={'present': True, 'down': False})
                   for t in range(0, 1800, 30)])
        assert rep['validity']['verdict'] == 'INVALID'
        assert any('pad observer silent' in r for r in rep['validity']['reasons'])


# --------------------------------------------- daemon runs bound the comparison
def daemon(t, event, **kw):
    return dict({'kind': 'daemon', 't': T0 + t, 'event': event}, **kw)


def test_legacy_outside_daemon_runs_is_excluded():
    """couchd was stopped: what legacy did then is not a divergence (R6)."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(-1800.0, 'route_pad', 'game'),     # long before couchd start
                   legacy(10.0, 'show', 'kodi', src='guard')],
                  [daemon(0.0, 'start', pid=1, mode='shadow'),
                   couchd(10.1, 'show', 'kodi', reason='guard-enforce'),
                   daemon(600.0, 'stop', passes=37, intents=1)],
                  heartbeat(0, 600))
        assert rep['matched_total'] == 1
        assert not sections(rep)['LEGACY-ONLY'], sections(rep)['LEGACY-ONLY']
        assert any('outside couchd' in n for n in rep['notes'])
        assert rep['validity']['verdict'] == 'VALID', rep['validity']


def test_gap_between_daemon_runs_is_not_blindness():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(10.0, 'show', 'kodi')],
                  [daemon(0.0, 'start'), couchd(10.1, 'show', 'kodi'),
                   daemon(300.0, 'stop', passes=9, intents=1),
                   daemon(3600.0, 'start'),          # an hour of daemon downtime
                   couchd(3610.0, 'iconify', 'steam-bigpicture')],
                  heartbeat(0, 330) + heartbeat(3600, 3930))
        h = rep['observer_health']
        assert len(h['runs']) == 2, h['runs']
        assert rep['validity']['verdict'] == 'VALID', rep['validity']
        assert any('couchd ran 2 times' in n for n in rep['notes'])


# ----------------------------------------------------- graceful degradation
def test_missing_legacy_stream_degrades():
    with tempfile.TemporaryDirectory() as tmp:
        cp = write(tmp, 'couchd.jsonl', [couchd(0.0, 'freeze', '730', pids=[1])])
        rep = sd.build(os.path.join(tmp, 'nope.jsonl'), cp, None)
        assert rep['validity']['verdict'] == 'INVALID'
        assert any('MISSING' in n for n in rep['notes'])
        assert len(sections(rep)['COUCHD-ONLY']) == 1
        sd.render(rep)                       # must not raise


def test_non_intent_kinds_are_never_diffed():
    """transition/invariant/daemon/agreement records must not become intents."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'kodi')],
                  [couchd(0.1, 'show', 'kodi'),
                   transition(1, 'game:413090', 'LAUNCHING', 'RUNNING', 'window-seen'),
                   {'kind': 'invariant', 't': T0 + 2, 'ok': False,
                    'name': 'owned_resources', 'leaks': ['stale guard pidfile']},
                   {'kind': 'daemon', 't': T0 + 3, 'event': 'stop', 'passes': 37,
                    'intents': 1}])
        assert rep['matched_total'] == 1 and not rep['rows']
        assert any('failing invariant' in n for n in rep['notes'])
        assert any('daemon stop' in n for n in rep['notes'])


def test_partial_lines_and_context_verbs():
    with tempfile.TemporaryDirectory() as tmp:
        lp = os.path.join(tmp, 'legacy.jsonl')
        with open(lp, 'w') as fh:
            fh.write(json.dumps(legacy(0.0, 'invoked', '730', src='game-launch',
                                       argv=['launch', '730'], appid='730')) + '\n')
            fh.write(json.dumps(legacy(0.5, 'launch', '730', src='game-launch')) + '\n')
            fh.write('{"t": 17858780')      # truncated tail
        cp = write(tmp, 'couchd.jsonl', [couchd(1.0, 'launch', '730',
                                                reason='trigger:argv')])
        rep = sd.build(lp, cp, None)
        assert rep['context_records'] == 1
        assert rep['matched_total'] == 1
        assert any('unparseable' in n for n in rep['notes'])
        assert not rep['rows']


def test_snapshot_context_uses_real_schema():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(5.0, 'dismiss', 'power-menu')],
                  [couchd(0.0, 'show', 'kodi')],
                  [snapshot(4.0, why='transition:pad', focused='Kodi',
                            flags={'session': '730', 'suspended': '1'},
                            pids={'100': 'T'},
                            regions={'input_ownership': 'kodi', 'gesture': 'idle'})])
        row = [r for r in rep['rows'] if r['verb'] == 'dismiss'][0]
        assert 'focused=Kodi' in row['context'] and 'session=730' in row['context']
        assert 'input_ownership:kodi' in row['context']
        assert 'transition:pad' in sd.render(rep)


if __name__ == '__main__':
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('ok   %s' % name)
            except AssertionError as e:
                fails += 1
                print('FAIL %s: %s' % (name, e))
            except Exception as e:                       # noqa: BLE001
                fails += 1
                print('ERR  %s: %r' % (name, e))
    print('%d failure(s)' % fails)
    sys.exit(1 if fails else 0)
