#!/usr/bin/env python3
"""Synthetic fixtures for tools/shadow-diff.

Every fixture is written to a temp file inside the test; nothing here reads the
real corpus, the box, or any daemon.

Run:  python3 -m pytest tools/test_shadow_diff.py     (pytest installed)
      python3 tools/test_shadow_diff.py               (plain runner, no pytest)
"""
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

T0 = 1754340000.0          # a fixed evening epoch, so fixtures are deterministic


def write(tmp, name, records):
    p = os.path.join(tmp, name)
    with open(p, 'w') as fh:
        for r in records:
            fh.write(json.dumps(r) + '\n')
    return p


def legacy(t, verb, subject=None, src='watcher', **args):
    return {'t': T0 + t, 'src': src, 'verb': verb, 'subject': subject, 'args': args}


def couchd(t, verb, subject=None, seq=0, reason='gesture', **args):
    return {'kind': 'intent', 't': T0 + t, 'seq': seq, 'mono': t, 'verb': verb,
            'subject': subject, 'args': args, 'reason': reason,
            'regions': {'input': 'kodi'}, 'predict': {}}


def obs(t, source, **kw):
    r = {'kind': 'obs', 't': T0 + t, 'source': source}
    r.update(kw)
    return r


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
                          resolver='game-pids'),
                   couchd(0.5, 'route_pad', 'kodi', release_t=T0 + 0.3),
                   couchd(30.2, 'thaw', '730', pids=[100, 101],
                          resolver='game-pids')])
        s = sections(rep)
        assert rep['matched_total'] == 3, rep['matched_total']
        assert rep['matched_clean'] == 3
        assert all(not s[k] for k in sd.SECTIONS), s
        assert rep['validity']['verdict'] == 'VALID', rep['validity']
        assert rep['gating_count'] == 0
        assert rep['offsets']['route_pad']['n'] == 1
        assert 'PASS' in sd.render(rep)


# ------------------------------------------------------------ couchd-only diff
def test_couchd_only():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'freeze', '730', pids=[100], resolver='game-pids')],
                  [couchd(0.1, 'freeze', '730', pids=[100], resolver='game-pids'),
                   couchd(3.0, 'iconify', 'steam-bigpicture')])
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
                   legacy(9.0, 'show', 'kodi', src='guard')],   # 9s away: out of +/-2s
                  [couchd(0.05, 'route_pad', 'game')])
        s = sections(rep)
        assert [r['verb'] for r in s['LEGACY-ONLY']] == ['show'], s
        assert rep['matched_total'] == 1


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
    """route_pad(kodi) matched inside +/-2s but fired BEFORE the gesture release."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(10.0, 'route_pad', 'kodi')],
                  [couchd(9.6, 'route_pad', 'kodi'),
                   obs(10.4, 'gesture', region='gesture', event='release')])
        s = sections(rep)
        assert rep['matched_total'] == 1
        assert len(s['BOTH-BUT-DIFFERENT']) == 1, s
        assert 'ORDER' in s['BOTH-BUT-DIFFERENT'][0]['flags']
        assert rep['gating_count'] == 1
        fails = [a for a in rep['assertions'] if a['ok'] is False]
        assert fails and 'gesture release' in fails[0]['name']


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


# ------------------------------------------------------- observer-health gate
def test_observer_blind_invalidates_evening():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'freeze', '730', pids=[100], resolver='game-pids'),
                   legacy(1800.0, 'thaw', '730', pids=[100], resolver='game-pids')],
                  [couchd(0.1, 'freeze', '730', pids=[100], resolver='game-pids'),
                   couchd(1800.1, 'thaw', '730', pids=[100], resolver='game-pids')] +
                  [obs(t, s) for s in sd.EXPECTED_SOURCES
                   for t in range(0, 1800, 30) if not (s == 'steam_log'
                                                       and 400 < t < 1300)] +
                  [obs(401, 'steam_log', event='observer_blind', duration=880,
                       detail='log truncated (dev,ino,size)')])
        assert rep['validity']['verdict'] == 'INVALID', rep['validity']
        why = ' '.join(rep['validity']['reasons'])
        assert 'steam_log' in why and 'observer_blind' in why, why
        assert rep['matched_total'] == 2         # diffing itself still ran
        health = {s['source']: s for s in rep['observer_health']['sources']}
        assert health['steam_log']['max_gap'] > 300
        assert health['pad']['max_gap'] <= 60


def test_absent_source_invalidates_long_window():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'kodi')],
                  [couchd(0.1, 'show', 'kodi'), obs(1200, 'pad')])
        assert rep['validity']['verdict'] == 'INVALID'
        assert any('absent' in r for r in rep['validity']['reasons'])


# ----------------------------------------------------- graceful degradation
def test_missing_legacy_stream_degrades():
    with tempfile.TemporaryDirectory() as tmp:
        cp = write(tmp, 'couchd.jsonl', [couchd(0.0, 'freeze', '730', pids=[1])])
        rep = sd.build(os.path.join(tmp, 'nope.jsonl'), cp, None)
        assert rep['validity']['verdict'] == 'INVALID'
        assert any('MISSING' in n for n in rep['notes'])
        assert len(sections(rep)['COUCHD-ONLY']) == 1
        sd.render(rep)                       # must not raise


def test_partial_lines_and_context_verbs():
    with tempfile.TemporaryDirectory() as tmp:
        lp = os.path.join(tmp, 'legacy.jsonl')
        with open(lp, 'w') as fh:
            fh.write(json.dumps(legacy(0.0, 'invoked', 'game-launch',
                                       src='game-launch', argv=['launch', '730'])))
            fh.write('\n')
            fh.write(json.dumps(legacy(0.5, 'launch', '730', src='game-launch')))
            fh.write('\n{"t": 17543400')      # truncated tail
        cp = write(tmp, 'couchd.jsonl', [couchd(1.0, 'launch', '730')])
        rep = sd.build(lp, cp, None)
        assert rep['context_records'] == 1
        assert rep['matched_total'] == 1
        assert any('unparseable' in n for n in rep['notes'])
        assert not rep['rows']


def test_snapshot_context_shown():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(5.0, 'dismiss', 'power-menu')],
                  [couchd(0.0, 'show', 'kodi')],
                  [{'t': T0 + 4.0, 'focus': 'kodi', 'suspended': False}])
        row = [r for r in rep['rows'] if r['verb'] == 'dismiss'][0]
        assert 'focus=kodi' in row['context']
        assert 'focus=kodi' in sd.render(rep)


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
