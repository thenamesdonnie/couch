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


def run(tmp, lrecs, crecs, snaps=None, window=None):
    lp = write(tmp, 'legacy.jsonl', lrecs)
    cp = write(tmp, 'couchd.jsonl', crecs)
    sp = write(tmp, 'snaps.jsonl', snaps) if snaps else None
    return sd.build(lp, cp, sp, window=window)


def daemon_rec(t, event, model=None):
    """A daemon start/stop mark, optionally carrying the model fingerprint
    couchd stamps on every start from 5 Aug 2026."""
    r = {'kind': 'daemon', 'event': event, 't': T0 + t, 'pid': 4242}
    if model:
        r['model_version'] = model
    return r


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
        assert all('legacy repeat of the pair' in c['note']
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


def test_couchd_fanout_associates_to_one_legacy_action():
    """The real 02:13:38 shape: couchd splits ONE decision across several reasons
    (hold-release-timeout, then a joystick-drift repair 120ms later) while the old
    stack writes the pad once. A strict 1:1 join orphaned the siblings."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(37.780, 'route_pad', 'kodi')],
                  [couchd(38.000, 'route_pad', 'kodi',
                          reason='gesture:hold-release-timeout'),
                   couchd(38.123, 'route_pad', 'kodi',
                          reason='reconcile:joystick-setting-drift')])
        assert rep['matched_total'] == 1
        assert not sections(rep)['COUCHD-ONLY'], sections(rep)['COUCHD-ONLY']
        assert len(rep['cooldown_associated']) == 1
        c = rep['cooldown_associated'][0]
        assert c['side'] == 'couchd' and 'fan-out' in c['note']
        assert 'joystick-setting-drift' in c['note']


def test_couchd_fanout_before_the_legacy_action_also_associates():
    """The 00:17:51.641 case: the drift repair fired 0.77s BEFORE legacy routed, and
    the session-ended intent 0.14s after; greedy took the closer and orphaned it."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(52.408, 'route_pad', 'kodi', src='game-launch')],
                  [couchd(51.641, 'route_pad', 'kodi',
                          reason='reconcile:joystick-setting-drift'),
                   couchd(52.550, 'route_pad', 'kodi',
                          reason='transition:session-ended')])
        assert rep['matched_total'] == 1
        assert not sections(rep)['COUCHD-ONLY'], sections(rep)['COUCHD-ONLY']
        assert rep['cooldown_associated'][0]['offset'] < 0     # the earlier sibling


def test_fanout_outside_the_window_stays_a_divergence():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'route_pad', 'kodi')],
                  [couchd(0.1, 'route_pad', 'kodi', reason='gesture:hold-release'),
                   couchd(90.0, 'route_pad', 'kodi', reason='gesture:hold-release')])
        assert len(sections(rep)['COUCHD-ONLY']) == 1
        assert not rep['cooldown_associated']


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


def test_kernel_edge_wins_over_the_gesture_transition():
    """The transition is written in the SAME pass as the intent it would judge
    (handoff-decided), which manufactured 0ms 'preceded the release' failures on the
    real 5 Aug corpus. The pad's kernel-stamped BTN_MODE release is the truth."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(20.0, 'route_pad', 'kodi')],
                  [couchd(20.1, 'route_pad', 'kodi', reason='gesture:hold-release'),
                   obs(19.7, 'pad', event='BTN_MODE', value=0, kernel_t=T0 + 19.65),
                   transition(20.1, 'gesture', 'handoff-pending', 'idle',
                              reason='handoff-decided')])
        a = [x for x in rep['assertions'] if 'gesture release' in x['name']]
        assert [x['ok'] for x in a] == [True], a
        assert 'kernel' in a[0]['detail']
        assert not sections(rep)['BOTH-BUT-DIFFERENT']


def test_hold_release_timeout_is_exempt_from_the_ordering_rule():
    """A hold that times out is decided with the button still down, by design."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(20.0, 'route_pad', 'kodi')],
                  [couchd(20.1, 'route_pad', 'kodi',
                          reason='gesture:hold-release-timeout'),
                   obs(20.4, 'pad', event='BTN_MODE', value=0, kernel_t=T0 + 20.42)])
        a = [x for x in rep['assertions'] if 'gesture release' in x['name']]
        assert [x['ok'] for x in a] == [None], a
        assert 'exempt' in a[0]['detail']
        assert rep['gating_count'] == 0
        assert not sections(rep)['BOTH-BUT-DIFFERENT']


def test_a_release_driven_route_pad_still_gates():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(20.0, 'route_pad', 'kodi')],
                  [couchd(20.1, 'route_pad', 'kodi', reason='gesture:hold-release'),
                   obs(20.4, 'pad', event='BTN_MODE', value=0, kernel_t=T0 + 20.42)])
        assert rep['gating_count'] == 1
        assert 'ORDER' in sections(rep)['BOTH-BUT-DIFFERENT'][0]['flags']


def test_ordering_violation_gates_even_when_unmatched():
    """R5 evaluates happens-before independently of matching, so a couchd-only
    intent that beat its own release edge gates too."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [],
                  [couchd(20.1, 'route_pad', 'kodi', reason='gesture:hold-release'),
                   obs(20.4, 'pad', event='BTN_MODE', value=0, kernel_t=T0 + 20.42)])
        row = sections(rep)['COUCHD-ONLY'][0]
        assert 'ORDER' in row['flags'] and 'release edge' in row['note']
        assert rep['gating_count'] == 1


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


def test_t5_r7c_pointer_grab_iconify_and_deiconify():
    """The suspend unmaps the frozen game (a SIGSTOPped client keeps its pointer
    grab) and the resume maps it back. Legacy-only until couchd's model catches
    up, so both verbs are pre-declared rather than gating."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'iconify', '730', src='watcher',
                          via='wm-change-state', reason='release-pointer-grab',
                          window='0x4200007'),
                   legacy(30.0, 'show', '730', src='game-launch',
                          via='activate', reason='deiconify',
                          window='0x4200007')],
                  [])
        rows = {r['verb'] + r['section']: r for r in rep['rows']}
        for verb in ('iconify', 'show'):
            r = rows[verb + 'LEGACY-ONLY']
            assert r['label'] == 'T5' and 'R7(c)' in r['note'], r
            assert 'catch-up pending' in r['note'], r
        assert rep['gating_count'] == 0


def test_a_normal_raise_is_still_diffable():
    """Only the activate-flavoured show is pre-declared; focus_game's ordinary
    xlib-restack raise must stay a real divergence."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'game', src='game-launch',
                               via='xlib-restack')], [])
        r = {x['verb'] + x['section']: x for x in rep['rows']}['showLEGACY-ONLY']
        assert r['label'] == '', r


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
        assert len(rep['runs']) == 2, rep['runs']
        assert rep['validity']['verdict'] == 'VALID', rep['validity']
        assert any('couchd ran 2 times' in n for n in rep['notes'])
        # health is judged inside the CURRENT-model run only
        assert rep['observer_health']['runs'] == [(T0 + 3600, T0 + 3930 - 30)] or \
            len(rep['observer_health']['runs']) == 1, rep['observer_health']['runs']


def test_older_runs_are_marked_stale_model_and_never_gate():
    """A restart means new code: rows from before the newest daemon start are
    informational, not evidence about the model running now."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(10.0, 'freeze', '730', pids=[1, 2], resolver='game-pids'),
                   legacy(3610.0, 'freeze', '730', pids=[1, 2], resolver='game-pids')],
                  [daemon(0.0, 'start'),
                   couchd(10.1, 'freeze', '730', pids=[1, 2, 3, 4, 5],
                          resolver='gameprocess_log'),          # stale-model mismatch
                   daemon(300.0, 'stop'),
                   daemon(3600.0, 'start'),
                   couchd(3610.1, 'freeze', '730', pids=[1, 2],
                          resolver='gameprocess_log')],
                  heartbeat(0, 330) + heartbeat(3600, 3930))
        rows = sections(rep)['BOTH-BUT-DIFFERENT']
        assert len(rows) == 1 and rows[0]['stale'] is True, rows
        assert rows[0]['run'] == 1
        assert rep['gating_count'] == 0, rep['gating_count']   # stale never gates
        txt = sd.render(rep)
        assert 'STALE-MODEL' in txt and 'stale-model' in txt
        assert [r['stale'] for r in rep['runs']] == [True, False]


def test_since_narrows_the_window():
    with tempfile.TemporaryDirectory() as tmp:
        lp = write(tmp, 'legacy.jsonl', [legacy(10.0, 'show', 'kodi'),
                                         legacy(3610.0, 'show', 'kodi')])
        cp = write(tmp, 'couchd.jsonl', [daemon(0.0, 'start'),
                                         couchd(3610.1, 'show', 'kodi')])
        rep = sd.build(lp, cp, None, since=T0 + 1800)
        assert rep['matched_total'] == 1
        assert not sections(rep)['LEGACY-ONLY'], sections(rep)['LEGACY-ONLY']
        assert any('--since' in n for n in rep['notes'])
        assert sd.parse_since('02:05', '20260805') > 0
        assert sd.parse_since(None, '20260805') is None


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
        # invoked + both launches are trigger context: a launch is the user's finger,
        # not a decision couchd could ever have predicted
        assert rep['context_records'] == 3
        assert rep['matched_total'] == 0
        assert any('unparseable' in n for n in rep['notes'])
        assert not rep['rows']


# ------------------------------------------------------------- the launch block
def test_launch_and_tv_wake_are_context_never_rows():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'invoked', 'steam', src='game-launch'),
                   legacy(0.1, 'launch', '367520', src='game-launch', mode='steam'),
                   legacy(0.2, 'request_tv_wake', 'tv', src='game-launch')],
                  [couchd(60.0, 'show', 'kodi', reason='guard:kodi-on-top')])
        assert rep['context_records'] == 3
        assert not sections(rep)['LEGACY-ONLY'], sections(rep)['LEGACY-ONLY']
        assert len(sections(rep)['COUCHD-ONLY']) == 1      # far from the launch


def test_launch_cluster_downgrades_to_launch_sequence():
    """The real 02:05 shape: game-launch routes and raises during the launch, couchd
    reacts to session-started a few seconds off. Not a decision divergence."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'launch', '367520', src='game-launch', mode='steam'),
                   legacy(1.0, 'show', 'game', src='game-launch', mode='steam'),
                   legacy(300.0, 'show', 'game', src='game-launch')],   # far away
                  [couchd(0.05, 'show', '367520', reason='transition:session-started'),
                   couchd(12.0, 'show', '367520', reason='guard:kodi-on-top-mid-game')])
        s = sections(rep)
        # show(game) canonicalises against show(<appid>), so the first one MATCHES
        assert rep['matched_total'] == 1, rep['matched_total']
        assert len(rep['launch_sequence']) == 1, rep['launch_sequence']
        assert rep['launch_sequence'][0]['side'] == 'couchd'
        assert 'launch-sequence artifact' in rep['launch_sequence'][0]['note']
        assert [r['verb'] for r in s['LEGACY-ONLY']] == ['show']   # the 300s one
        assert 'LAUNCH-SEQUENCE' in sd.render(rep)


def test_subject_alias_show_game_matches_show_appid():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'game', src='game-launch')],
                  [couchd(0.4, 'show', '367520', reason='transition:session-started')])
        assert rep['matched_total'] == 1 and not rep['rows']


def test_alias_does_not_leak_to_other_verbs():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'route_pad', 'game')],
                  [couchd(0.1, 'route_pad', '367520')])
        assert rep['matched_total'] == 0
        assert len(sections(rep)['LEGACY-ONLY']) == 1
        assert len(sections(rep)['COUCHD-ONLY']) == 1


def test_t5_guard_supersede_is_pre_declared():
    """R5's written-before-evening-one entry: single arbiter replaces guard supersede."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'kill', 'steam-input-guard', src='guard', pids=[999],
                          resolver='guard-pidfile'),
                   legacy(0.1, 'window_open', 'kodi', src='guard'),
                   legacy(9.0, 'window_close', 'kodi', src='guard'),
                   legacy(20.0, 'kill', 'runaway', src='watcher', pids=[5])],
                  [couchd(60.0, 'show', 'kodi')])
        rows = {(r['verb'], r['t'] - T0): r for r in sections(rep)['LEGACY-ONLY']}
        assert all(r['label'] == 'T5' for k, r in rows.items() if k[1] < 10), rows
        assert 'single arbiter' in rows[('kill', 0.0)]['note']
        assert rows[('kill', 20.0)]['label'] == ''      # not the guard: still triage
        assert rep['gating_count'] == 0


def test_verb_absent_from_the_other_stream_is_annotated():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'window_open', 'kodi', src='guard')],
                  [couchd(30.0, 'close_steam_menu', 'steam',
                          reason='gesture:hold-release')])
        notes = {r['verb']: r['note'] for r in rep['rows']}
        assert 'never appears in the other stream' in notes['window_open']
        assert 'never appears in the other stream' in notes['close_steam_menu']


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


# ------------------------------------------- the paused game's freeze-frame
# Verb name collision worth stating: the shadow stream ALSO has a world record
# with kind=="snapshot". as_intent() takes kind in (None, 'intent') only, so
# the two never meet - the tests below and test_snapshot_context_uses_real_schema
# above exercise both halves of that.
def test_pause_snap_matches_across_the_watchers_background_delay():
    """The watcher runs pause-snap off its select loop, so the legacy line can
    trail the freeze it belongs to. 5s of tolerance covers that."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'freeze', '730', pids=[100], resolver='game-pids'),
                   legacy(0.1, 'set_flag', 'suspended', value='730'),
                   legacy(1.8, 'snapshot', '730', via='pause-snap',
                          gesture='hold', reason='ps-hold')],
                  [couchd(0.1, 'freeze', '730', pids=[100], resolver='game-pids'),
                   couchd(0.15, 'set_flag', 'suspended', value='730'),
                   couchd(0.2, 'snapshot', '730', via='pause-snap')])
        s = sections(rep)
        assert rep['matched_total'] == 3, rep['matched_total']
        assert all(not s[k] for k in sd.SECTIONS), s


def test_a_snapshot_only_one_stack_took_is_a_divergence():
    """No T5 entry: it landed in both stacks in the same change, so a missing
    frame on either side is a real row for triage."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'freeze', '730', pids=[100], resolver='game-pids')],
                  [couchd(0.1, 'freeze', '730', pids=[100], resolver='game-pids'),
                   couchd(0.2, 'snapshot', '730', via='pause-snap')])
        s = sections(rep)
        assert [r['verb'] for r in s['COUCHD-ONLY']] == ['snapshot'], s
        assert not s['LEGACY-ONLY']


def test_snapshots_of_different_games_never_pair_up():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'snapshot', '730', via='pause-snap')],
                  [couchd(0.2, 'snapshot', '367520', via='pause-snap')])
        s = sections(rep)
        assert len(s['LEGACY-ONLY']) == 1 and len(s['COUCHD-ONLY']) == 1, s


# ------------------------------------------------- couchd's own edge latency
def latency(t, decide, intents=('show|kodi|gesture:ps-hold',), kernel=None,
            coalesced=0):
    return {'kind': 'latency', 'event': 'gesture-edge', 't': T0 + t,
            'reason': 'ps-button', 'edge_seq': int(t * 10) + 1,
            'coalesced': coalesced, 'decide_latency_s': decide,
            'kernel_latency_s': kernel, 'intents': list(intents),
            'gesture': 'hold-fired'}


def test_edge_latency_is_summarised_from_couchds_own_records():
    """R5's number measured from the inside, so it survives the flip: the
    matched-offset table needs a legacy stack to compare against, this does
    not."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'kodi')],
                  [couchd(0.05, 'show', 'kodi'),
                   latency(0.05, 0.06, kernel=0.09),
                   latency(1.05, 0.07, kernel=0.11),
                   latency(2.05, 0.20, kernel=0.24, coalesced=1)])
        el = rep['edge_latency']
        assert el['n'] == 3
        assert el['p50'] == 0.07
        assert el['within_bound'] is True
        assert el['coalesced'] == 1
        assert 'edge-to-decision' in sd.render(rep)


def test_an_edge_that_decided_nothing_is_not_a_latency_sample():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'kodi')],
                  [couchd(0.05, 'show', 'kodi'), latency(0.05, 0.06, intents=())])
        assert rep['edge_latency'] is None


def test_edge_latency_above_the_bound_is_called_out_but_never_gates():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'kodi')],
                  [couchd(0.05, 'show', 'kodi'), latency(0.05, 1.4)])
        assert rep['edge_latency']['within_bound'] is False
        assert 'ABOVE the 250ms bound' in sd.render(rep)
        assert rep['gating_count'] == 0


# ------------------------------------------------ staleness by MODEL version
def test_a_restart_of_the_same_model_does_not_make_the_evening_stale():
    """The defect the 5 Aug replay found: staleness keyed off the newest
    process start, so ANY later restart voided the whole evening's gating -
    and Evening 1's own '0 gating divergences' turned out to be computed over
    a 4-minute idle window with nothing in it."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(10.0, 'route_pad', 'kodi')],
                  [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa'),
                   couchd(10.5, 'route_pad', 'game'),   # a divergence to judge
                   daemon_rec(20.0, 'stop'),
                   daemon_rec(21.0, 'start', 'aaaaaaaaaaaa'),
                   daemon_rec(30.0, 'stop')])
        assert [r['stale'] for r in rep['rows']] == [False] * len(rep['rows'])
        assert rep['scope']['model_rule'] == 'model_version'
        assert rep['scope']['rows_stale'] == 0
        assert rep['scope']['decisions'] > 0


def test_a_run_of_an_older_model_is_stale_and_does_not_gate():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(10.0, 'route_pad', 'kodi')],
                  [daemon_rec(0.0, 'start', 'oldoldoldold'),
                   couchd(10.5, 'route_pad', 'game'),
                   daemon_rec(20.0, 'stop'),
                   daemon_rec(21.0, 'start', 'newnewnewnew'),
                   daemon_rec(30.0, 'stop')])
        assert all(r['stale'] for r in rep['rows'])
        assert rep['scope']['model'] == 'newnewnewnew'
        assert any('OLDER model' in n for n in rep['notes'])


def test_a_corpus_without_fingerprints_says_which_rule_it_fell_back_to():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(10.0, 'route_pad', 'kodi')],
                  [daemon_rec(0.0, 'start'), couchd(10.5, 'route_pad', 'game'),
                   daemon_rec(20.0, 'stop'), daemon_rec(21.0, 'start'),
                   daemon_rec(30.0, 'stop')])
        assert 'newest-start' in rep['scope']['model_rule']
        assert all(r['stale'] for r in rep['rows'])
        assert any('--window to pin' in n for n in rep['notes'])


# --------------------------------------------------------------- the window
def test_window_clips_the_analysis_and_the_verdict_says_so():
    with tempfile.TemporaryDirectory() as tmp:
        recs = [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa'),
                couchd(10.5, 'route_pad', 'game'), daemon_rec(60.0, 'stop'),
                daemon_rec(600.0, 'start', 'aaaaaaaaaaaa'),
                couchd(610.0, 'show', 'desktop'), daemon_rec(660.0, 'stop')]
        legacy_recs = [legacy(10.0, 'route_pad', 'kodi'),
                       legacy(609.0, 'show', 'kodi')]
        rep = run(tmp, legacy_recs, recs, window=(T0 - 1, T0 + 120))
        assert rep['scope']['source'] == '--window'
        assert rep['scope']['runs_clipped'] == 1
        ts = [r['t'] for r in rep['rows']]
        assert ts and all(t <= T0 + 120 for t in ts), 'the later run is gone'
        text = sd.render(rep)
        assert 'window' in text and 'judged' in text
        assert 'decision(s)' in text


def test_a_window_with_nothing_in_it_can_never_read_as_a_pass():
    """The exact shape of the original defect: a verdict over an idle stretch
    must not look like an evening's verdict."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(10.0, 'route_pad', 'kodi')],
                  [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa'),
                   couchd(10.5, 'route_pad', 'game'), daemon_rec(60.0, 'stop')],
                  window=(T0 + 1000, T0 + 2000))
        assert rep['scope']['decisions'] == 0
        assert rep['gating_count'] == 0
        assert rep['validity']['verdict'] == 'INVALID'
        assert any('0 comparable decisions' in r
                   for r in rep['validity']['reasons'])
        assert 'over NOTHING; not a pass' in sd.render(rep)


def test_window_lets_a_fingerprintless_evening_be_judged_on_request():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(10.0, 'route_pad', 'kodi')],
                  [daemon_rec(0.0, 'start'), couchd(10.5, 'route_pad', 'game'),
                   daemon_rec(60.0, 'stop'), daemon_rec(600.0, 'start'),
                   daemon_rec(660.0, 'stop')],
                  window=(T0 - 1, T0 + 120))
        assert not any(r['stale'] for r in rep['rows'])
        assert '--window' in rep['scope']['model_rule']
        assert any('your assertion' in n for n in rep['notes'])


def test_parse_window_accepts_open_ends_and_rejects_nonsense():
    day = '20260805'
    lo, hi = sd.parse_window('00:38-03:15', day)
    assert hi > lo
    assert sd.parse_window('-03:15', day)[0] == 0.0
    assert sd.parse_window('21:00-', day)[1] == float('inf')
    assert sd.parse_window(None, day) is None
    for bad in ('03:15', '03:15-00:38', 'tea-time'):
        try:
            sd.parse_window(bad, day)
        except SystemExit:
            continue
        raise AssertionError('accepted %r' % bad)


# ------------------------------------------------------- crash-holed corpora
def test_a_nul_hole_from_a_crash_is_counted_and_stepped_over():
    """The 05:19 power event left 1154 NUL bytes in snapshots-20260805.jsonl:
    the tail was allocated and never reached the platter."""
    with tempfile.TemporaryDirectory() as tmp:
        cp = os.path.join(tmp, 'couchd.jsonl')
        with open(cp, 'w') as fh:
            fh.write(json.dumps(couchd(10.5, 'route_pad', 'kodi')) + '\n')
            fh.write('\x00' * 1154 + '\n')          # the hole
            fh.write(json.dumps(couchd(30.5, 'show', 'kodi')) + '\n')
        lp = write(tmp, 'legacy.jsonl', [legacy(10.0, 'route_pad', 'kodi'),
                                         legacy(30.0, 'show', 'kodi')])
        rep = sd.build(lp, cp, None)
        assert any('NUL bytes' in n for n in rep['notes'])
        assert rep['matched_total'] == 2, 'the records either side survived'


def test_a_nul_hole_glued_to_a_real_record_still_yields_the_record():
    """A hole carries no newline, so it arrives stuck to whatever follows."""
    with tempfile.TemporaryDirectory() as tmp:
        cp = os.path.join(tmp, 'couchd.jsonl')
        with open(cp, 'w') as fh:
            fh.write('\x00' * 64 + json.dumps(couchd(10.5, 'route_pad', 'kodi'))
                     + '\n')
        lp = write(tmp, 'legacy.jsonl', [legacy(10.0, 'route_pad', 'kodi')])
        rep = sd.build(lp, cp, None)
        assert rep['matched_total'] == 1
        assert any('NUL bytes' in n for n in rep['notes'])


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
