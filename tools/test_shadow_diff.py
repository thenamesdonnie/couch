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


def daemon_rec(t, event, model=None, owns=None):
    """A daemon start/stop mark, optionally carrying the model fingerprint
    couchd stamps on every start from 5 Aug 2026, and the owns.conf it booted
    with (the differ reads direction out of these)."""
    r = {'kind': 'daemon', 'event': event, 't': T0 + t, 'pid': 4242}
    if model:
        r['model_version'] = model
    if owns is not None:
        r['owns'] = list(owns)
    return r


# ------------------------------------------------- post-flip record shapes
# The first flip was 5 Aug 2026 13:01 (COUCHD_OWNS="gestures"). From then on
# couchd's acting executor stamps `acted` + `action` on every intent it takes,
# and pad-home-watcher writes its would-do with args.yielded instead of doing
# it. These three helpers mirror those real shapes.
def acted(t, verb, subject=None, reason='gesture:ps-hold', ok=True,
          responsibility='gestures', action=None, **args):
    """couchd's ACTING record: `acted` true if the action fired, false if it
    was declined (precondition gone, deadline pending, backoff) or failed."""
    r = couchd(t, verb, subject, reason=reason, **args)
    r['acted'] = bool(ok)
    r['responsibility'] = responsibility
    r['action'] = {'ok': True} if action is None else action
    return r


def yielded(t, verb, subject=None, src='watcher', **args):
    """A legacy would-do: computed and written, never performed."""
    return legacy(t, verb, subject, src=src, yielded=True, owner='couchd',
                  **args)


def yield_marker(t, gesture='double-tap', action='switcher',
                 reason='ps-double-tap'):
    """The bare marker the watcher writes for a bound gesture it no longer
    performs: it names the GESTURE, not the verbs couchd ran instead."""
    return legacy(t, 'yield', gesture, gesture=gesture, action=action,
                  reason=reason, yielded=True, owner='couchd')


def owns_changed(t, now, was=(), declared=None):
    """The runtime flip record. couchd re-reads owns.conf every tick, so the
    13:01 flip left exactly one of these and restarted nothing.

    `now` is what couchd can EXECUTE, `now_declared` what owns.conf asked for.
    They differ only for `input`, which stage-1 couchd cannot execute but which
    the stage-2 input process owns on the other end of the supervisor wire.
    """
    r = {'kind': 'daemon', 'event': 'owns-changed', 't': T0 + t,
         'was': list(was), 'now': list(now), 'acting': bool(now)}
    if declared is not None:
        r['now_declared'] = list(declared)
    return r


def wire(t, event, **kw):
    """A supervisor-wire lifecycle record (obs source 'supervisor')."""
    return obs(t, 'supervisor', event=event, **kw)


def press(t, value=0, via=None):
    """A pad BTN_MODE observation, optionally labelled with the route it came
    by. No `via` at all is the evdev corpus, which is every evening so far."""
    r = obs(t, 'pad', event='BTN_MODE', value=value, kernel_t=T0 + t)
    if via:
        r['via'] = via
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


def test_bp_hold_flag_with_no_real_freeze_is_exempt_from_ordering():
    """Step 6 of the acceptance night (03:47:20 / 03:48:15): a Big Picture
    hold has no game pids, so couchd correctly SKIPS the freeze and only sets
    the flag, while legacy's yielded would-freeze (pids=[]) lands a beat after
    the flag write. There is no real freeze to order, so freeze-before-flag
    does not apply."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [yielded(10.2, 'freeze', 'bigpicture', pids=[],
                           resolver='game-pids', gesture='hold',
                           action='suspend_to_kodi', reason='ps-hold')],
                  [daemon_rec(-5.0, 'start', model='m1', owns=['gestures']),
                   acted(10.0, 'set_flag', 'suspended',
                         reason='gesture:ps-hold-bigpicture',
                         value='bigpicture', pids=[])])
        a = [x for x in rep['assertions'] if 'set_flag' in x['name']]
        assert [x['ok'] for x in a] == [None], a
        assert 'exempt' in a[0]['detail'], a
        assert rep['gating_count'] == 0, rep['gating_breakdown']


def test_a_real_game_hold_keeps_freeze_before_flag_strict():
    """The BP exemption must not leak: a real game session's freeze arriving
    after the flag write is still an ORDER violation."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(10.2, 'freeze', '730', pids=[100, 101],
                          resolver='game-pids')],
                  [couchd(10.0, 'set_flag', 'suspended', value='730',
                          reason='gesture:ps-hold', pids=[100, 101])])
        a = [x for x in rep['assertions'] if 'set_flag' in x['name']]
        assert [x['ok'] for x in a] == [False], a
        assert rep['gating_count'] >= 1
        row = sections(rep)['COUCHD-ONLY'][0]
        assert 'ORDER' in row['flags'], row


def test_bp_worded_hold_with_a_real_freeze_is_not_exempt():
    """The exemption keys on the ABSENCE of a real freeze, not on the word
    bigpicture: a nearby freeze carrying pids keeps the assertion strict."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(10.2, 'freeze', '730', pids=[100],
                          resolver='game-pids')],
                  [couchd(10.0, 'set_flag', 'suspended', value='bigpicture',
                          reason='gesture:ps-hold-bigpicture')])
        a = [x for x in rep['assertions'] if 'set_flag' in x['name']]
        assert [x['ok'] for x in a] == [False], a
        assert rep['gating_count'] >= 1


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


def test_t5_curtain_overlay_row_is_pre_declared():
    """6 Aug deploy-day declaration: WM_CLASS couch-curtain is a transition
    overlay, so an enforcement row naming it reads T5 on EITHER side."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(20.0, 'show', 'kodi', src='guard',
                          reason='wanted window not on top',
                          top='couch curtain', topcls='couch-curtain')],
                  [couchd(5.0, 'show', 'kodi',
                          reason='guard:wanted-window-not-on-top',
                          via='xlib-restack', top='couch curtain',
                          topcls='couch-curtain')])
        s = sections(rep)
        for r in s['COUCHD-ONLY'] + s['LEGACY-ONLY']:
            assert r['label'] == 'T5' and 'curtain' in r['note'], r
        assert rep['gating_count'] == 0


def test_a_non_curtain_wrong_window_row_still_diffs():
    """Only the curtain is declared: a wanted-window-not-on-top row about any
    other window stays a real divergence for hand triage."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [],
                  [couchd(5.0, 'show', 'kodi',
                          reason='guard:wanted-window-not-on-top',
                          top='Steam Big Picture Mode',
                          topcls='steamwebhelper')])
        r = sections(rep)['COUCHD-ONLY'][0]
        assert r['label'] == '', r


def test_t5_bp_hide_iconify_from_game_launch_is_pre_declared():
    """6 Aug deploy-day declaration: game-launch iconifies the Big Picture
    steamwebhelper window once the game window maps (the fps root-cause fix).
    A new legacy-side window op, pre-declared rather than a gating novelty."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(5.0, 'iconify', 'steamwebhelper', src='game-launch',
                          via='wm-change-state',
                          reason='hide-bp-after-game-map',
                          window='0x2c0000a')],
                  [])
        r = sections(rep)['LEGACY-ONLY'][0]
        assert r['label'] == 'T5' and 'BP-hide' in r['note'], r
        assert rep['gating_count'] == 0


def test_an_iconify_not_from_game_launch_is_not_bp_hide():
    """The BP-hide entry is keyed on src=game-launch; the same subject from
    another source stays open for hand triage."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(5.0, 'iconify', 'steamwebhelper', src='guard')],
                  [])
        r = sections(rep)['LEGACY-ONLY'][0]
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


# ------------------------------------------- post-flip: the roles reverse
def test_couchd_owning_gestures_reverses_the_roles():
    """The whole point of flip day: couchd's acted freeze is the ACTION and
    the watcher's yielded freeze is the shadow of it. Same join, same
    tolerance, same clean pair - the streams have simply swapped jobs."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [yielded(0.0, 'freeze', '730', pids=[100, 101],
                           resolver='game-pids', gesture='hold',
                           action='suspend_to_kodi', reason='ps-hold')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   acted(0.1, 'freeze', '730', pids=[100, 101])])
        assert rep['ownership']['reversed'] is True
        assert rep['ownership']['owned'] == ['gestures']
        assert rep['matched_total'] == 1 and rep['matched_clean'] == 1
        assert not rep['rows'], rep['rows']
        assert rep['validity']['verdict'] == 'VALID', rep['validity']
        txt = sd.render(rep)
        assert 'couchd acting / legacy shadowing for gestures' in txt
        assert 'couchd ACTING on gestures' in txt
        assert any('DIRECTION REVERSED' in n for n in rep['notes'])


def test_the_same_decisions_with_owns_empty_keep_the_old_direction():
    """The identical pair of decisions recorded before the flip: nothing is
    yielded, couchd owns nothing, and every label reads the old way round."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'freeze', '730', pids=[100, 101],
                          resolver='game-pids'),
                   legacy(5.0, 'dismiss', 'power-menu')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa', owns=[]),
                   couchd(0.1, 'freeze', '730', pids=[100, 101],
                          reason='gesture:ps-hold')])
        assert rep['ownership']['reversed'] is False
        assert rep['ownership']['owned'] == []
        assert [r['section'] for r in rep['rows']] == ['LEGACY-ONLY']
        assert rep['rows'][0]['direction'] == 'legacy-acting'
        txt = sd.render(rep)
        assert 'legacy acting / couchd shadowing' in txt
        assert '== SHADOW-ONLY ==' not in txt and '== ACTED-ONLY ==' not in txt


def test_an_unmatched_yielded_would_do_is_never_a_legacy_only_row():
    """A would-do couchd did not act on is still a divergence - but it is the
    OTHER one: 'couchd, which owns this, did not do it', not 'couchd never
    decided it'. Reporting it as LEGACY-ONLY would poison the evening."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [yielded(5.0, 'route_pad', 'kodi', reason='handoff',
                           via='kodi-jsonrpc')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   acted(0.1, 'freeze', '730', pids=[100])])
        s = sections(rep)
        assert not s['LEGACY-ONLY'], s['LEGACY-ONLY']
        assert [r['verb'] for r in s['SHADOW-ONLY']] == ['route_pad']
        assert s['SHADOW-ONLY'][0]['direction'] == 'couchd-acting'
        assert [r['verb'] for r in s['ACTED-ONLY']] == ['freeze']
        assert 'legacy would have; couchd, which owns it, did NOT' \
            in sd.render(rep)


def test_bare_yield_markers_are_context_not_divergences():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [yield_marker(0.0),
                   yield_marker(30.0, 'hold-release', 'power_menu',
                                'ps-hold-release')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   acted(0.2, 'show_switcher', 'tv',
                         reason='gesture:double-tap-switcher')])
        assert rep['yield_markers'] == 2
        assert not [r for r in rep['rows'] if r['verb'] == 'yield'], rep['rows']
        assert any('bare `yield` marker' in n for n in rep['notes'])
        # the marker names the gesture, so the switcher couchd DID run has
        # nothing to join to and stays a plain one-sided row
        assert [r['section'] for r in rep['rows']] == ['ACTED-ONLY']


def test_the_t5_whitelist_still_fires_on_a_reversed_row():
    """The pre-declared entries are keyed on the UNREVERSED section, so a
    whitelist written about a legacy-only row keeps working when the same row
    arrives as SHADOW-ONLY."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [yielded(0.0, 'set_flag', 'suspended', value='730',
                           reason='ps-hold')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   acted(30.0, 'show', 'kodi', reason='gesture:hold-release')])
        row = [r for r in rep['rows'] if r['verb'] == 'set_flag'][0]
        assert row['section'] == 'SHADOW-ONLY'
        assert row['label'] == 'T5' and 'flag verbs' in row['note']
        assert rep['gating_count'] == 0


def test_post_flip_a_yielded_repeat_may_precede_couchds_action():
    """The repeat asymmetry belongs to the ROLES, not to the stacks: the
    actor's repeats can only follow its own action, the shadow's fan-out may
    sit either side of it. Post-flip that freedom moves to the legacy lines,
    so a would-do 2.6s BEFORE couchd acted is a sibling, not a divergence."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [yielded(7.5, 'route_pad', 'kodi', reason='reconcile'),
                   yielded(10.0, 'route_pad', 'kodi', reason='handoff')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   acted(10.1, 'route_pad', 'kodi',
                         reason='gesture:hold-release')])
        assert rep['matched_total'] == 1
        assert len(rep['cooldown_associated']) == 1, rep['cooldown_associated']
        assert rep['cooldown_associated'][0]['offset'] < 0
        assert not sections(rep)['SHADOW-ONLY'], sections(rep)['SHADOW-ONLY']


def test_a_flip_mid_evening_switches_direction_at_the_ownership_record():
    """One corpus, both directions: the owns-changed record is the boundary,
    and rows either side of it are labelled by the direction in force then."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(10.0, 'dismiss', 'power-menu'),
                   yielded(200.0, 'route_pad', 'kodi', reason='handoff')],
                  [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa', owns=[]),
                   couchd(50.0, 'iconify', '730', reason='gesture:ps-hold'),
                   owns_changed(100.0, ['gestures']),
                   acted(250.0, 'close_steam_menu', 'steam',
                         reason='gesture:hold-release')],
                  heartbeat(0, 300))
        w = rep['ownership']['windows']
        assert len(w) == 2, w
        assert w[0]['owned'] == [] and w[1]['owned'] == ['gestures']
        assert round(w[1]['from'] - T0) == 100
        by_verb = {r['verb']: r for r in rep['rows']}
        assert by_verb['dismiss']['section'] == 'LEGACY-ONLY'
        assert by_verb['iconify']['section'] == 'COUCHD-ONLY'
        assert by_verb['route_pad']['section'] == 'SHADOW-ONLY'
        assert by_verb['close_steam_menu']['section'] == 'ACTED-ONLY'
        txt = sd.render(rep)
        assert 'couchd owns nothing' in txt and 'shadowing for gestures' in txt


# ------------------------------------------------ the `input` responsibility
# It produces no intents, so it can never make a divergence row. What it
# decides is where the pad EVIDENCE came from, which is judged the way an
# observer is judged - see shadow-diff's input_wire().
def test_input_is_owned_from_the_declared_list_not_the_actable_one():
    """`input` never appears in `owns`: stage-1 couchd cannot execute it. Read
    only the actable list and a flipped input evening looks unflipped."""
    with tempfile.TemporaryDirectory() as tmp:
        rec = daemon_rec(0.0, 'start', 'aaaaaaaaaaaa', owns=['gestures'])
        rec['owns_declared'] = ['gestures', 'input']
        rep = run(tmp, [],
                  [rec,
                   press(10.0, 1, via='supervisor'),
                   press(10.3, 0, via='supervisor'),
                   wire(1.0, 'connected', pid=4243, user='couchd-input')],
                  heartbeat(0, 60))
        owned = {n for w in rep['ownership']['windows'] for n in w['owned']}
        assert owned == {'gestures', 'input'}, owned
        iw = rep['input_wire']
        assert iw['owned'], iw
        assert iw['pad_by_route'] == {'supervisor': 2}, iw
        assert iw['problems'] == [], iw['problems']
        # (the fixture has no legacy stream, so the verdict is INVALID for
        # that reason alone - what matters is that the wire adds nothing)
        assert not [r for r in rep['validity']['reasons'] if 'wire' in r
                    or '`input`' in r], rep['validity']
        assert 'INPUT WIRE' in sd.render(rep)


def test_a_corpus_that_stamps_no_declared_list_reads_exactly_as_before():
    """Every evening written before the wire existed. `input` is absent, the
    wire section stays out of the report, and nothing gates."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [],
                  [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   press(10.0, 1), press(10.3, 0)],
                  heartbeat(0, 60))
        owned = {n for w in rep['ownership']['windows'] for n in w['owned']}
        assert owned == {'gestures'}
        iw = rep['input_wire']
        assert iw['owned'] == [] and iw['problems'] == []
        assert iw['pad_by_route'] == {'evdev': 2}
        assert 'INPUT WIRE' not in sd.render(rep)


def test_pad_events_read_straight_off_evdev_while_input_was_owned_invalidate():
    """The input process was supposed to be holding the pad. If couchd read
    the device itself, the stretch is not the arrangement it claims to be."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [],
                  [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa', owns=[]),
                   owns_changed(5.0, [], declared=['input']),
                   wire(6.0, 'connected', pid=4243, user='couchd-input'),
                   press(10.0, 1),               # <- no via: read directly
                   press(10.3, 0, via='supervisor')],
                  heartbeat(0, 60))
        iw = rep['input_wire']
        assert len(iw['problems']) == 1, iw['problems']
        assert 'DIRECTLY' in iw['problems'][0]
        assert rep['validity']['verdict'] == 'INVALID'
        assert any('DIRECTLY' in r for r in rep['validity']['reasons'])


def test_a_wire_that_disconnected_mid_evening_invalidates():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [],
                  [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa', owns=[],),
                   owns_changed(1.0, [], declared=['input']),
                   wire(2.0, 'connected', pid=4243, user='couchd-input'),
                   press(10.0, 1, via='supervisor'),
                   wire(20.0, 'disconnected', pid=4243, why='eof')],
                  heartbeat(0, 60))
        iw = rep['input_wire']
        assert any('DISCONNECTED' in p for p in iw['problems']), iw['problems']
        assert rep['validity']['verdict'] == 'INVALID'


def test_dropped_observations_invalidate_because_couchd_never_heard_them():
    """SR7: the input process drops rather than blocking the pad. Every drop
    is a BTN_MODE edge couchd was never told about."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [],
                  [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa', owns=[]),
                   owns_changed(1.0, [], declared=['input']),
                   wire(2.0, 'connected', pid=4243, user='couchd-input'),
                   wire(30.0, 'peer-health', drops=0, owns_input=True),
                   wire(60.0, 'peer-health', drops=3, owns_input=True),
                   press(10.0, 1, via='supervisor')],
                  heartbeat(0, 90))
        iw = rep['input_wire']
        assert iw['peer_drops'] == 3
        assert any('DROPPED' in p for p in iw['problems']), iw['problems']
        assert rep['validity']['verdict'] == 'INVALID'


def test_owning_input_with_nothing_on_the_wire_at_all_invalidates():
    """The failure the whole wire exists to make impossible, seen from the
    morning: the pad was owned and the evidence simply is not there."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [],
                  [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa', owns=[]),
                   owns_changed(1.0, [], declared=['input'])],
                  heartbeat(0, 60))
        iw = rep['input_wire']
        assert any('missing, not merely quiet' in p for p in iw['problems'])
        assert rep['validity']['verdict'] == 'INVALID'


def test_wire_records_with_nobody_owning_input_are_a_note_not_a_verdict():
    """The mirror case: the evidence is there and couchd classified it the
    same way either route, but owns.conf and the world disagree."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [],
                  [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   wire(2.0, 'connected', pid=4243, user='couchd-input'),
                   press(10.0, 1, via='supervisor')],
                  heartbeat(0, 60))
        assert rep['input_wire']['problems'] == []
        assert any('no ownership window declares `input`' in n
                   for n in rep['notes']), rep['notes']
        assert not [r for r in rep['validity']['reasons'] if 'wire' in r
                    or '`input`' in r], rep['validity']


def test_input_never_produces_a_divergence_row():
    """It decides nothing, so there is nothing to be one-sided about."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [],
                  [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa', owns=[]),
                   owns_changed(1.0, [], declared=['input']),
                   wire(2.0, 'connected', pid=4243, user='couchd-input'),
                   press(10.0, 1, via='supervisor'),
                   press(10.3, 0, via='supervisor')],
                  heartbeat(0, 60))
        assert rep['rows'] == []
        assert rep['gating_breakdown']['rows'] == 0
        assert sd.responsibility_of({'reason': 'input:whatever', 'args': {}}) \
            is None


def test_acting_health_counts_acted_skipped_and_failed_per_verb():
    """C17 from the acting side. A skip changed nothing in the world, so it
    is health rather than a divergence the shadow could contradict."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [yielded(0.0, 'freeze', '730', pids=[100],
                           resolver='game-pids', gesture='hold',
                           action='suspend_to_kodi', reason='ps-hold')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   acted(0.1, 'freeze', '730', pids=[100]),
                   acted(20.0, 'close_steam_menu', 'steam',
                         reason='gesture:hold-release', ok=False,
                         action={'ok': True, 'precondition_gone':
                                 'the toggle target is already closed'}),
                   acted(40.0, 'route_pad', 'kodi',
                         reason='gesture:hold-release', ok=False,
                         action={'ok': False, 'error': 'kodi rpc failed'}),
                   {'kind': 'effect', 't': T0 + 1.0, 'verdict': 'confirmed',
                    'verb': 'freeze', 'subject': '730', 'latency_s': 0.4,
                    'reason': 'gesture:ps-hold'},
                   {'kind': 'effect', 't': T0 + 45.0, 'verdict': 'missed',
                    'verb': 'route_pad', 'subject': 'kodi', 'latency_s': 5.0,
                    'reason': 'gesture:hold-release'}])
        ah = rep['acting_health']
        assert ah['totals'] == {'acted': 1, 'skipped': 1, 'failed': 1,
                                'refused': 0, 'model-only': 0}, ah['totals']
        assert ah['per_verb']['close_steam_menu']['skipped'] == 1
        assert ah['per_verb']['route_pad']['failed'] == 1
        assert ah['effects']['freeze']['confirmed'] == 1
        assert ah['effects']['route_pad']['missed'] == 1
        # the genuine DECLINE (precondition gone) is health, never a row; the
        # FAILURE is a row - a failed action is bad news, not a footnote
        assert not [r for r in rep['rows'] if r['verb'] == 'close_steam_menu']
        failed_rows = [r for r in rep['rows'] if r['verb'] == 'route_pad']
        assert len(failed_rows) == 1, rep['rows']
        assert 'ACT-FAILED' in failed_rows[0]['flags'], failed_rows
        assert len(rep['acting_declined']) == 1, rep['acting_declined']
        # 1 action failure + 1 missed effect both reach the verdict
        assert rep['gating_breakdown']['act_failed'] == 1
        assert rep['gating_breakdown']['effects_missed'] == 1
        assert rep['gating_count'] == 2, rep['gating_count']
        txt = sd.render(rep)
        assert 'ACTING HEALTH' in txt
        assert 'acted 1, skipped 1, failed 1' in txt
        assert 'FAILED' in txt and 'kodi rpc failed' in txt
        assert 'DECLINED' in txt


def test_a_backoff_skip_is_health_and_a_model_only_refusal_is_named():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [yielded(0.0, 'freeze', '730', pids=[100],
                                resolver='game-pids')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   acted(0.1, 'freeze', '730', pids=[100]),
                   acted(10.0, 'kill', 'steam-input-guard',
                         reason='gesture:hold-release', ok=False,
                         action={'ok': False, 'backoff': True,
                                 'consecutive_failures': 3, 'retry_in_s': 30.0}),
                   acted(20.0, 'launch', 'bigpicture',
                         reason='transition:ensure-bp-before-game',
                         responsibility='transitions', ok=False,
                         action={'ok': True, 'model_only': 'legacy keeps this '
                                 'step (game-launch does not yield it)'})])
        ah = rep['acting_health']
        assert ah['per_verb']['kill']['skipped'] == 1
        assert ah['per_verb']['launch']['model-only'] == 1
        assert sd.acting_outcome({'acted': False,
                                  'action': {'ok': False, 'refused':
                                             'guard is not owned'}}) \
            == ('refused', 'guard is not owned')
        assert 'C11 backoff after 3 consecutive failure(s)' in sd.render(rep)


def test_ownership_is_handed_back_when_the_daemon_stops():
    """Ownership is a LEASE: a stopped couchd owns nothing, and the legacy
    scripts are acting again within 30s whatever owns.conf still says."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(10.0, 'show', 'kodi')],
                  [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   acted(10.1, 'show', 'kodi', reason='gesture:hold-release'),
                   daemon_rec(60.0, 'stop'),
                   daemon_rec(600.0, 'start', 'aaaaaaaaaaaa', owns=[]),
                   couchd(610.0, 'show', 'desktop', reason='gesture:ps-hold')],
                  heartbeat(0, 90) + heartbeat(600, 660))
        owned = [w['owned'] for w in rep['ownership']['windows']]
        assert ['gestures'] in owned and [] in owned, owned
        assert sd.owned_at(sd.ownership_windows(
            [{'kind': 'daemon', 'event': 'start', 't': 0.0,
              'owns': ['gestures']},
             {'kind': 'daemon', 'event': 'stop', 't': 100.0}], (0.0, 200.0)),
            'gestures', 150.0) is False


def test_a_corpus_with_no_daemon_records_reads_as_owning_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp, [legacy(0.0, 'show', 'kodi')],
                  [couchd(0.1, 'show', 'kodi', reason='gesture:hold-release')])
        assert rep['ownership']['reversed'] is False
        assert len(rep['ownership']['windows']) == 1
        assert rep['ownership']['windows'][0]['owned'] == []


# ------------------------------------------------ the gate must not lie green
# The 5 Aug adversarial review: five ways the differ could say VALID / gating 0
# over an evening that was actually broken. Each test below is one of them.
def test_a_dead_actuator_arm_gates_instead_of_reading_green():
    """Defect 1: couchd owns gestures, every acted intent FAILED and every
    effect verdict is 'missed' - the old differ said gating 0, VALID, exit 0."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [yielded(0.0, 'freeze', '730', pids=[100],
                           resolver='game-pids'),
                   yielded(20.0, 'route_pad', 'kodi', reason='handoff')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   acted(0.1, 'freeze', '730', pids=[100], ok=False,
                         action={'ok': False,
                                 'error': 'ptrace: permission denied'}),
                   acted(20.1, 'route_pad', 'kodi',
                         reason='gesture:hold-release', ok=False,
                         action={'ok': False, 'error': 'kodi rpc dead'}),
                   {'kind': 'effect', 't': T0 + 2.0, 'verdict': 'missed',
                    'verb': 'freeze', 'subject': '730', 'latency_s': 5.0,
                    'reason': 'gesture:ps-hold'},
                   {'kind': 'effect', 't': T0 + 25.0, 'verdict': 'missed',
                    'verb': 'route_pad', 'subject': 'kodi', 'latency_s': 5.0,
                    'reason': 'gesture:hold-release'}])
        gb = rep['gating_breakdown']
        assert gb['act_failed'] == 2 and gb['effects_missed'] == 2, gb
        assert rep['gating_count'] == 4, rep['gating_count']
        # the evening is still judgeable - VALID with bad news, exit 1 via gating
        assert rep['validity']['verdict'] == 'VALID', rep['validity']
        flagged = [r for r in rep['rows'] if 'ACT-FAILED' in r['flags']]
        assert len(flagged) == 2, rep['rows']
        txt = sd.render(rep)
        assert 'GATING: 2 action failure(s) + 2 missed effect(s)' in txt


def test_an_unverified_effect_stays_health_not_gating():
    """'unverified' means the observer could not say - R5 already polices the
    observer, so it must not gate as if it were a miss."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [yielded(0.0, 'freeze', '730', pids=[100],
                           resolver='game-pids')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   acted(0.1, 'freeze', '730', pids=[100]),
                   {'kind': 'effect', 't': T0 + 2.0, 'verdict': 'unverified',
                    'verb': 'freeze', 'subject': '730', 'latency_s': 5.0,
                    'reason': 'gesture:ps-hold'}])
        assert rep['gating_count'] == 0, rep['gating_count']
        assert rep['validity']['verdict'] == 'VALID'


def test_a_shadow_only_miss_gates_when_couchd_owns_it():
    """Defect 2: one-sided rows never carry SET-MISMATCH/ORDER, so post-flip
    'couchd owns it and did NOT do it' was structurally unable to gate."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [yielded(5.0, 'route_pad', 'kodi', reason='handoff',
                           via='kodi-jsonrpc')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   acted(0.1, 'freeze', '730', pids=[100])])
        row = sections(rep)['SHADOW-ONLY'][0]
        assert 'OWNER-MISSED' in row['flags'], row
        assert rep['gating_breakdown']['rows'] == 1, rep['gating_breakdown']
        assert rep['gating_count'] == 1, rep['gating_count']
        assert 'OWNER-MISSED' in sd.render(rep)


def test_a_missed_set_flag_no_longer_hides_behind_the_flag_verb_t5():
    """Defect 2b: the 'flag verbs are absent from couchd's stream' T5 predates
    ActingExecutor growing set_flag/clear_flag. When couchd speaks the verb in
    this very corpus, a missed one is a real divergence, not a vocabulary gap."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [yielded(0.0, 'freeze', '730', pids=[100],
                           resolver='game-pids'),
                   yielded(0.1, 'set_flag', 'suspended', value='730',
                           reason='ps-hold')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
                   acted(0.1, 'freeze', '730', pids=[100]),
                   acted(200.0, 'set_flag', 'suspended', value='730',
                         reason='gesture:ps-hold')])
        row = [r for r in rep['rows'] if r['verb'] == 'set_flag'
               and r['section'] == 'SHADOW-ONLY'][0]
        assert row['label'] != 'T5', row
        assert 'OWNER-MISSED' in row['flags'], row
        assert rep['gating_count'] >= 1, rep['gating_count']


def test_a_second_start_closes_a_crashed_run():
    """Defect 3: a watchdog kill / power loss writes no stop record, so the
    next start used to be swallowed and two runs read as one - with the dead
    gap inside it, so legacy acting alone there looked like divergences."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(10.0, 'show', 'kodi'),
                   legacy(1000.0, 'show', 'kodi'),        # while couchd was DEAD
                   legacy(3610.0, 'show', 'kodi')],
                  [daemon_rec(0.0, 'start', 'aaaaaaaaaaaa'),
                   couchd(10.1, 'show', 'kodi'),
                   couchd(50.0, 'iconify', 'steam-bigpicture'),  # last breath
                   daemon_rec(3600.0, 'start', 'aaaaaaaaaaaa'),  # crash restart
                   couchd(3610.1, 'show', 'kodi'),
                   daemon_rec(3700.0, 'stop')],
                  heartbeat(0, 60) + heartbeat(3600, 3700))
        assert len(rep['runs']) == 2, rep['runs']
        # the crashed run ends at couchd's own last record, not at the restart
        assert round(rep['runs'][0]['end'] - T0, 1) == 50.0, rep['runs']
        assert any('CRASHED' in n for n in rep['notes']), rep['notes']
        # the legacy show at t=1000 fell in the dead gap: couchd was not running
        assert rep['matched_total'] == 2, rep['matched_total']
        assert not sections(rep)['LEGACY-ONLY'], sections(rep)['LEGACY-ONLY']
        assert any('outside couchd' in n for n in rep['notes'])


def test_a_crash_restart_does_not_mislabel_the_second_runs_model():
    """Defect 3b: the swallowed second start also swallowed its model_version,
    so the new model's rows inherited the old fingerprint and went stale."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(10.0, 'route_pad', 'kodi'),
                   legacy(3610.0, 'route_pad', 'kodi')],
                  [daemon_rec(0.0, 'start', 'oldoldoldold'),
                   couchd(10.5, 'route_pad', 'game'),
                   daemon_rec(3600.0, 'start', 'newnewnewnew'),  # crash restart
                   couchd(3610.5, 'route_pad', 'game')])
        assert [r['model'] for r in rep['runs']] == \
            ['oldoldoldold', 'newnewnewnew'], rep['runs']
        assert [r['stale'] for r in rep['runs']] == [True, False], rep['runs']
        stale = {round(r['t'] - T0, 1): r['stale'] for r in rep['rows']}
        assert stale[10.5] is True and stale[3610.5] is False, stale


def test_a_cooldown_repeat_with_a_different_pid_set_gates():
    """Defect 4: legacy refroze {100,101,102} where the matched decision froze
    {100,101}. The old association absorbed it silently - a half-frozen game
    read green. A repeat that grows or shrinks the set is not a repeat."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(0.0, 'freeze', '730', pids=[100, 101],
                          resolver='game-pids'),
                   legacy(1.0, 'freeze', '730', pids=[100, 101],
                          resolver='game-pids'),           # true repeat: absorbed
                   legacy(2.0, 'freeze', '730', pids=[100, 101, 102],
                          resolver='game-pids')],          # grew the set: gates
                  [couchd(0.1, 'freeze', '730', pids=[100, 101],
                          reason='gesture:ps-hold')])
        assert rep['matched_total'] == 1
        assert len(rep['cooldown_associated']) == 1, rep['cooldown_associated']
        rows = sections(rep)['LEGACY-ONLY']
        assert len(rows) == 1, rows
        assert 'REPEAT-SET-MISMATCH' in rows[0]['flags'], rows
        assert '102' in rows[0]['note'], rows
        assert rep['gating_count'] == 1, rep['gating_count']


def test_midnight_rollover_seeds_runs_and_ownership_from_yesterday():
    """Defect 5: the shadow log rotates nightly, so a daemon started yesterday
    leaves today's file with no start and no ownership records. The differ used
    to read 'owns nothing' and fall back to whole-span-model-None."""
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, 'couchd-20260804.jsonl',
              [daemon_rec(-50000.0, 'start', 'aaaaaaaaaaaa', owns=[]),
               owns_changed(-49000.0, ['gestures'])])      # still open at midnight
        cp = write(tmp, 'couchd-20260805.jsonl',
                   [acted(0.1, 'freeze', '730', pids=[100])])
        lp = write(tmp, 'legacy.jsonl',
                   [yielded(0.0, 'freeze', '730', pids=[100],
                            resolver='game-pids')])
        rep = sd.build(lp, cp, None)
        assert rep['ownership']['reversed'] is True, rep['ownership']
        assert rep['ownership']['owned'] == ['gestures']
        assert rep['scope']['model_rule'] == 'model_version', rep['scope']
        assert rep['scope']['model'] == 'aaaaaaaaaaaa'
        assert not any(r['stale'] for r in rep['rows'])
        assert any('rollover' in n.lower() for n in rep['notes']), rep['notes']
        assert rep['matched_total'] == 1


def test_rollover_after_a_clean_stop_reads_owns_nothing_and_says_why():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, 'couchd-20260804.jsonl',
              [daemon_rec(-50000.0, 'start', 'aaaaaaaaaaaa', owns=['gestures']),
               daemon_rec(-40000.0, 'stop')])              # yesterday ended clean
        cp = write(tmp, 'couchd-20260805.jsonl',
                   [couchd(0.1, 'show', 'kodi')])
        lp = write(tmp, 'legacy.jsonl', [legacy(0.0, 'show', 'kodi')])
        rep = sd.build(lp, cp, None)
        assert rep['ownership']['reversed'] is False
        assert any('STOPPED' in n for n in rep['notes']), rep['notes']


def test_rollover_with_no_previous_day_file_is_loud():
    with tempfile.TemporaryDirectory() as tmp:
        cp = write(tmp, 'couchd-20260805.jsonl',
                   [couchd(0.1, 'show', 'kodi')])
        lp = write(tmp, 'legacy.jsonl', [legacy(0.0, 'show', 'kodi')])
        rep = sd.build(lp, cp, None)
        assert any('NO RUN/OWNERSHIP ANCHORS' in n for n in rep['notes']), \
            rep['notes']


def test_since_rejects_an_implausible_numeric_epoch():
    """Defect 6: --since 90000 used to return None silently and the whole file
    was analysed as if no --since had been given."""
    day = '20260805'
    assert sd.parse_since('1785878000', day) == 1785878000.0
    assert sd.parse_since(None, day) is None
    for bad in ('90000', '0', '12'):
        try:
            sd.parse_since(bad, day)
        except SystemExit:
            continue
        raise AssertionError('accepted %r' % bad)


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


# ------------------------------------------- resume-transient thaw (hard gate)
def test_t5_resume_transient_thaw_is_pre_declared():
    """6 Aug hard-gate declaration: game-launch clears the suspended flag
    BEFORE its SIGCONTs, so a legacy repairer sampling the sub-second between
    the two can emit a thaw that duplicates the resume's own. couchd
    debounces (FLAG_DRIFT_PERSIST_S) and is silent by design - the row is
    one-sided by construction, in BOTH repairer flavours."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(9.8, 'clear_flag', 'suspended', src='game-launch',
                          reason='resume', was='730'),
                   legacy(10.0, 'thaw', '730', src='watcher',
                          pids=[100, 101], resolver='game-pids',
                          reason='frozen-without-suspended-flag',
                          repair='reconcile')],
                  [couchd(9.7, 'launch', '730', reason='gesture:tap-resume',
                          mode='resume', via='game-launch resume')])
        rows = {r['verb'] + r['section']: r for r in rep['rows']}
        r = rows['thawLEGACY-ONLY']
        assert r['label'] == 'T5' and 'resume-ordering' in r['note'], r


def test_t5_guard_invariant_4_thaw_near_a_resume_is_pre_declared():
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(10.0, 'clear_flag', 'suspended', src='game-launch',
                          reason='back-to-big-picture'),
                   legacy(10.4, 'thaw', '730', src='guard',
                          pids=[100], resolver='game-pids', invariant=4,
                          reason='all frozen with no suspended flag',
                          mode='game')],
                  [])
        rows = {r['verb'] + r['section']: r for r in rep['rows']}
        r = rows['thawLEGACY-ONLY']
        assert r['label'] == 'T5' and 'resume-ordering' in r['note'], r


def test_a_lost_thaw_far_from_any_resume_still_diffs():
    """Only the transient is declared: the same repair with no resume in
    sight is a real one-sided decision and must stay on the hand-triage
    pile - the entry must not eat the genuine lost-thaw net."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(60.0, 'thaw', '730', src='watcher',
                          pids=[100, 101], resolver='game-pids',
                          reason='frozen-without-suspended-flag',
                          repair='reconcile')],
                  [])
        rows = {r['verb'] + r['section']: r for r in rep['rows']}
        assert rows['thawLEGACY-ONLY']['label'] == '', rows['thawLEGACY-ONLY']


def test_a_legacy_refreeze_near_a_resume_is_no_longer_auto_t5():
    """R7(d) rescoped: the old unconditional T5 would have eaten the exact
    row the resume-ordering validation evening must catch - a legacy refreeze
    fighting an in-flight resume. Pre-flip (legacy acting reconcile) the row
    lands in LEGACY-ONLY for hand triage, UNLABELLED: one-sided legacy rows
    carry no gating flags by design, so losing the auto-T5 is what keeps it
    on the triage pile instead of vanishing as pre-declared."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(9.8, 'clear_flag', 'suspended', src='game-launch',
                          reason='resume', was='730'),
                   legacy(10.1, 'freeze', '730', src='watcher',
                          pids=[100, 101], resolver='game-pids',
                          signal='SIGSTOP', repair='reconcile',
                          reason='reconcile:refreeze-lost-suspend',
                          topcls='Kodi'),
                   # a matched freeze elsewhere keeps the verb in couchd's
                   # stream, so the row cannot demote to a vocabulary gap
                   legacy(200.1, 'freeze', '730', pids=[100, 101],
                          resolver='game-pids', reason='ps-hold')],
                  [couchd(200.0, 'freeze', '730', reason='gesture:ps-hold',
                          pids=[100, 101], resolver='game-pids')])
        rows = {r['verb'] + r['section']: r for r in rep['rows']}
        r = rows['freezeLEGACY-ONLY']
        assert r['label'] == '', r          # hand triage, not auto-T5
        assert 'rescoped' not in r.get('note', ''), r


def test_a_shadow_refreeze_near_a_resume_gates_once_reconcile_is_owned():
    """The post-flip reading, where the hazard gates NUMERICALLY: with
    reconcile owned, a yielded legacy refreeze near a resume that couchd
    (correctly debounced) did not act arrives as SHADOW-ONLY - and unlabelled
    it takes OWNER-MISSED and gates. If this row ever appears live it means
    a refreeze slipped past the decision-time flag re-read: the exact hazard
    the flip was gated on, and it must never file as pre-declared."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(9.8, 'clear_flag', 'suspended', src='game-launch',
                          reason='resume', was='730'),
                   yielded(10.1, 'freeze', '730', pids=[100, 101],
                           resolver='game-pids', signal='SIGSTOP',
                           repair='reconcile',
                           reason='reconcile:refreeze-lost-suspend',
                           topcls='Kodi'),
                   yielded(200.2, 'freeze', '730', pids=[100, 101],
                           resolver='game-pids',
                           reason='reconcile:refreeze-lost-suspend')],
                  [daemon_rec(-10.0, 'start', 'aaaaaaaaaaaa',
                              owns=['gestures', 'reconcile']),
                   acted(200.0, 'freeze', '730',
                         reason='reconcile:refreeze-lost-suspend',
                         responsibility='reconcile',
                         pids=[100, 101], resolver='game-pids')])
        rows = {r['verb'] + r['section']: r for r in rep['rows']}
        r = rows['freezeSHADOW-ONLY']
        assert r['label'] == '', r
        assert 'OWNER-MISSED' in r['flags'], r
        assert rep['gating_count'] >= 1


def test_a_legacy_refreeze_far_from_any_resume_keeps_the_rescoped_t5():
    """...while the far-from-resume shape stays exempt on the honest cadence
    rationale (legacy's 10s net vs couchd's debounce + repair cooldown)."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = run(tmp,
                  [legacy(60.0, 'freeze', '730', src='watcher',
                          pids=[100, 101], resolver='game-pids',
                          signal='SIGSTOP', repair='reconcile',
                          reason='reconcile:refreeze-lost-suspend',
                          topcls='Kodi')],
                  [])
        rows = {r['verb'] + r['section']: r for r in rep['rows']}
        r = rows['freezeLEGACY-ONLY']
        assert r['label'] == 'T5' and 'rescoped' in r['note'], r
        assert rep['gating_count'] == 0
