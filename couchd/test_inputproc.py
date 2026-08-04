#!/usr/bin/env python3
"""Pure-logic tests for stage 2. NO DEVICES ARE CREATED BY THIS FILE.

Everything here runs against importable functions and classes: the FF id
map, the persistence state machine, gesture.py's arithmetic on synthetic
kernel timestamps, and the DualSense->X360 translation table. Nothing opens
/dev/uinput, /dev/uhid or an evdev node, and nothing needs the pad.

The capability tables are checked a different way, and deliberately: they
are PARSED OUT OF ~/.local/bin/vpad and compared to inputproc's copies, so
if vpad is ever edited and inputproc is not, this file fails. SR2 pins the
virtual pad to vpad's exact shape because Kodi resolves its buttonmap by
`<name>_<b>b_<a>a.xml` and ships Microsoft_X-Box_360_pad_11b_8a.xml; drift
in either direction breaks that silently.

    .venv/bin/python -m pytest test_inputproc.py -q
"""
import ast
import errno
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gesture
import inputproc
from inputproc import (A_CREATE, A_DESTROY, A_KEYS_UP, A_REUPLOAD, FF_SLOTS,
                       FFFull, FFMap, GONE, LOST, OWNED, Persistence)

VPAD_PATH = os.path.expanduser('~/.local/bin/vpad')


# =========================================================================
# vpad table equality - drift detection, not a copy of a copy
# =========================================================================
def parse_vpad(path=VPAD_PATH):
    """Read vpad's module-level constants out of its AST.

    Parsing rather than importing: importing vpad would run nothing harmful
    today, but it is one edit away from creating a uinput device at import
    time, and a test suite must never be able to do that.
    """
    with open(path) as f:
        tree = ast.parse(f.read(), filename=path)
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except ValueError:
            continue
        targets = node.targets[0]
        if isinstance(targets, ast.Name):
            out[targets.id] = value
        elif isinstance(targets, ast.Tuple):
            names = [e.id for e in targets.elts if isinstance(e, ast.Name)]
            if len(names) == len(value):
                out.update(dict(zip(names, value)))
    return out


@pytest.fixture(scope='module')
def vpad():
    if not os.path.exists(VPAD_PATH):
        pytest.skip(f'{VPAD_PATH} not present')
    return parse_vpad()


def test_button_table_matches_vpad_exactly(vpad):
    assert inputproc.VPAD_BUTTONS == vpad['BUTTONS']


def test_axis_table_matches_vpad_exactly(vpad):
    assert inputproc.VPAD_AXES == vpad['AXES']


def test_identity_matches_vpad_exactly(vpad):
    assert inputproc.VPAD_NAME.encode() == vpad['NAME']
    assert inputproc.VPAD_BUS == vpad['BUS_USB']
    assert inputproc.VPAD_VENDOR == vpad['VENDOR']
    assert inputproc.VPAD_PRODUCT == vpad['PRODUCT']
    assert inputproc.VPAD_VERSION == vpad['VERSION']


def test_kodi_buttonmap_shape_is_11b_8a(vpad):
    """Kodi ships Microsoft_X-Box_360_pad_11b_8a.xml. Any other count and
    it resolves a different file, or none (SR2)."""
    assert len(vpad['BUTTONS']) == 11
    assert len(vpad['AXES']) == 8
    caps = inputproc.virtual_capabilities()
    from evdev import ecodes
    assert len(caps[ecodes.EV_KEY]) == 11
    assert len(caps[ecodes.EV_ABS]) == 8


def test_capabilities_absinfo_ranges_match_vpad(vpad):
    from evdev import ecodes
    caps = inputproc.virtual_capabilities()
    got = {code: (info.min, info.max) for code, info in caps[ecodes.EV_ABS]}
    want = {code: (lo, hi) for code, lo, hi in vpad['AXES'].values()}
    assert got == want


def test_capabilities_ff_is_subset_of_physical():
    """SR2's invariant: virtual ffbit is FF_RUMBLE only (plus gain), and
    always a subset of what the physical pad actually has."""
    from evdev import ecodes
    physical = [ecodes.FF_RUMBLE, ecodes.FF_GAIN, ecodes.FF_PERIODIC,
                ecodes.FF_SQUARE]
    chosen = inputproc.choose_ff_codes(physical)
    assert set(chosen) <= set(physical)
    assert ecodes.FF_PERIODIC not in chosen   # no waveform bits = failed uploads
    assert ecodes.FF_RUMBLE in chosen
    # a pad with nothing gets us nothing
    assert inputproc.choose_ff_codes([]) == []
    assert inputproc.choose_ff_codes([ecodes.FF_RUMBLE]) == [ecodes.FF_RUMBLE]


# =========================================================================
# DualSense -> X360 translation
# =========================================================================
def test_face_buttons_are_swapped_positionally():
    """The trap. hid-playstation calls square BTN_WEST and triangle
    BTN_NORTH; xpad calls X (the LEFT button) BTN_NORTH and Y (the TOP one)
    BTN_WEST. Passing codes through unchanged puts square where Y belongs."""
    from evdev import ecodes
    square = inputproc.translate(gesture.EV_KEY, ecodes.BTN_WEST, 1)
    triangle = inputproc.translate(gesture.EV_KEY, ecodes.BTN_NORTH, 1)
    assert square[1] == inputproc.VPAD_BUTTONS['x']
    assert triangle[1] == inputproc.VPAD_BUTTONS['y']
    # and the two that are NOT swapped
    assert inputproc.translate(gesture.EV_KEY, ecodes.BTN_SOUTH, 1)[1] == \
        inputproc.VPAD_BUTTONS['a']
    assert inputproc.translate(gesture.EV_KEY, ecodes.BTN_EAST, 1)[1] == \
        inputproc.VPAD_BUTTONS['b']


def test_every_translated_button_exists_on_the_virtual_pad():
    assert set(inputproc.BTN_MAP.values()) <= set(
        inputproc.VPAD_BUTTONS.values())
    assert len(set(inputproc.BTN_MAP.values())) == len(inputproc.BTN_MAP)


def test_digital_triggers_and_junk_are_dropped():
    from evdev import ecodes
    assert inputproc.translate(gesture.EV_KEY, ecodes.BTN_TL2, 1) is None
    assert inputproc.translate(gesture.EV_KEY, ecodes.BTN_TR2, 1) is None
    assert inputproc.translate(gesture.EV_MSC, 4, 123) is None
    assert inputproc.translate(gesture.EV_ABS, ecodes.ABS_MT_POSITION_X, 5) \
        is None


def test_stick_scaling_spans_the_full_range_without_inverting():
    assert inputproc.scale_stick(0) == -32768        # up / left
    assert inputproc.scale_stick(255) == 32767       # down / right
    assert inputproc.scale_stick(128) == 128 * 257 - 32768
    assert abs(inputproc.scale_stick(128)) < 300     # ~centre
    for raw in range(0, 256):
        v = inputproc.scale_stick(raw)
        assert -32768 <= v <= 32767
    # monotonic
    seq = [inputproc.scale_stick(r) for r in range(256)]
    assert seq == sorted(seq)


def test_triggers_and_hat_pass_through_unscaled():
    from evdev import ecodes
    assert inputproc.translate(gesture.EV_ABS, ecodes.ABS_Z, 200) == \
        (gesture.EV_ABS, ecodes.ABS_Z, 200)
    assert inputproc.translate(gesture.EV_ABS, ecodes.ABS_HAT0Y, -1) == \
        (gesture.EV_ABS, ecodes.ABS_HAT0Y, -1)


def test_syn_report_passes_and_syn_dropped_is_not():
    assert inputproc.translate(gesture.EV_SYN, gesture.SYN_REPORT, 0) == \
        (gesture.EV_SYN, gesture.SYN_REPORT, 0)
    assert inputproc.translate(gesture.EV_SYN, 3, 0) is None   # SYN_DROPPED


# =========================================================================
# force feedback: the SR7 contract, as bookkeeping
# =========================================================================
def test_create_maps_and_translates_both_ways():
    m = FFMap()
    assert m.phys_for(7) is None
    m.bind(virt=7, phys=3, blob=b'x')
    assert m.phys_for(7) == 3
    assert m.virt_for(3) == 7
    assert m.live() == 1


def test_update_reuses_the_slot():
    """If update allocated a new slot, sixteen re-uploads of ONE effect
    would exhaust the device. This is finding F10."""
    m = FFMap()
    m.bind(virt=1, phys=9, blob=b'first')
    before = m.live()
    assert m.update(1, b'second') == 9
    assert m.live() == before == 1
    assert m.phys_for(1) == 9
    assert m.virt_for(9) == 1
    assert dict(m.cached())[1] == b'second'


def test_update_of_unknown_effect_is_an_error_not_a_silent_create():
    m = FFMap()
    with pytest.raises(KeyError):
        m.update(4, b'x')


def test_sixteen_slots_then_enospc():
    m = FFMap()
    for i in range(FF_SLOTS):
        m.bind(virt=i, phys=100 + i, blob=b'e')
    assert m.live() == FF_SLOTS == 16
    assert not m.can_create()
    with pytest.raises(FFFull):
        m.bind(virt=99, phys=999)
    # and the map is untouched by the failure
    assert m.live() == FF_SLOTS
    assert m.phys_for(99) is None


def test_erase_frees_a_slot_and_a_create_then_succeeds():
    m = FFMap()
    for i in range(FF_SLOTS):
        m.bind(virt=i, phys=100 + i)
    assert m.erase(0) == 100
    assert m.live() == FF_SLOTS - 1
    assert m.can_create()
    assert m.virt_for(100) is None
    m.bind(virt=42, phys=100)
    assert m.phys_for(42) == 100


def test_erase_of_unknown_effect_is_a_quiet_none():
    """A game erasing an effect we never saw must still get an answer -
    unhandled, it stalls 30 seconds per effect (SR7)."""
    assert FFMap().erase(5) is None


def test_the_map_stays_a_bijection_through_every_operation():
    m = FFMap()
    for i in range(FF_SLOTS):
        m.bind(virt=i, phys=200 + i)
    m.update(3, b'z')
    m.erase(4)
    m.erase(9)
    m.bind(virt=50, phys=204)
    m.rebind(50, 250)
    assert m.to_phys == {v: p for p, v in m.to_virt.items()}
    assert len(m.to_phys) == len(m.to_virt)
    assert set(m.blobs) == set(m.to_phys)


def test_rebind_moves_a_virtual_id_to_a_new_physical_slot():
    """The reconnect path: same effect, new slot numbers from the pad."""
    m = FFMap()
    m.bind(virt=1, phys=5, blob=b'a')
    m.rebind(1, 11)
    assert m.phys_for(1) == 11
    assert m.virt_for(5) is None
    assert m.virt_for(11) == 1
    assert m.live() == 1


def test_double_bind_and_double_physical_are_refused():
    m = FFMap()
    m.bind(virt=1, phys=1)
    with pytest.raises(ValueError):
        m.bind(virt=1, phys=2)
    with pytest.raises(ValueError):
        m.bind(virt=2, phys=1)


def test_forget_physical_keeps_the_cache_for_reupload():
    """SR6/F11: after a BT hiccup the pad's slots are empty but the game's
    effects still exist. Losing the cache is how rumble dies silently."""
    m = FFMap()
    m.bind(virt=1, phys=5, blob=b'rumble')
    m.bind(virt=2, phys=6, blob=b'more')
    m.forget_physical()
    assert m.to_virt == {}
    assert [v for v, _ in m.cached()] == [1, 2]
    assert dict(m.cached())[1] == b'rumble'
    m.rebind(1, 0)
    m.rebind(2, 1)
    assert m.to_phys == {1: 0, 2: 1}


# =========================================================================
# gesture arithmetic, on synthetic kernel timestamps
# =========================================================================
def test_hold_boundary_is_inclusive_at_the_threshold():
    k0 = 0.0                      # exact float arithmetic at the boundary
    assert not gesture.hold_reached(True, k0, k0 + 0.70)
    assert not gesture.hold_reached(True, k0, k0 + 0.899999)
    assert gesture.hold_reached(True, k0, k0 + gesture.HOLD_SECONDS)
    assert gesture.hold_reached(True, k0, k0 + 0.95)


def test_hold_boundary_at_a_realistic_epoch_timestamp():
    """Kernel timestamps are ~1.7e9, where 0.9 does not round-trip: (k+0.9)-k
    is 0.8999999999999773. The threshold is therefore accurate to about a
    microsecond, not exactly, which is far inside anything a thumb can do.
    test_reconcile.py's existing 1e-6 epsilon is the same acknowledgement."""
    k0 = 1785000000.0
    assert not gesture.hold_reached(True, k0, k0 + 0.70)
    assert gesture.hold_reached(True, k0, k0 + gesture.HOLD_SECONDS + 1e-6)
    assert gesture.hold_reached(True, k0, k0 + 0.95)


def test_hold_needs_a_button_that_is_actually_down():
    k0 = 5000.0
    assert not gesture.hold_reached(False, k0, k0 + 10.0)
    assert not gesture.hold_reached(True, None, k0 + 10.0)


@pytest.mark.parametrize('duration,tap', [
    (0.70, True), (0.899999, True), (0.9, False), (0.95, False), (1.1, False)])
def test_tap_classification_at_the_boundary(duration, tap):
    assert gesture.is_tap(duration) is tap


def test_tap_of_unknown_duration_is_not_a_tap():
    assert gesture.is_tap(None) is False


def test_tracker_short_press_is_a_tap():
    t = gesture.PressTracker()
    k = 1000.0
    assert t.feed(k, 1, mono=0.0) == gesture.DOWN
    assert t.button_down and t.down_since_k == k
    assert t.feed(k + 0.70, 0, mono=0.70) == gesture.TAP
    assert t.press_duration == pytest.approx(0.70)
    assert not t.button_down
    assert t.presses == 1


def test_tracker_long_press_is_a_hold_release_even_without_polling():
    t = gesture.PressTracker()
    k = 1000.0
    t.feed(k, 1, mono=0.0)
    assert t.feed(k + 0.95, 0, mono=0.95) == gesture.HOLD_RELEASE


def test_tracker_poll_fires_hold_exactly_once_on_the_kernel_clock():
    t = gesture.PressTracker()
    k = 0.0
    # wall= is passed explicitly so nothing here depends on real time
    t.feed(k, 1, mono=0.0, wall=0.0)
    assert t.poll(wall=0.70) is None            # 0.70s held
    assert t.poll(wall=0.89) is None
    assert t.poll(wall=0.90) == gesture.HOLD    # crossed
    assert t.poll(wall=1.50) is None            # and only once
    assert t.feed(k + 1.6, 0, mono=1.6, wall=1.6) == gesture.HOLD_RELEASE
    # the next press starts clean
    t.feed(k + 2.0, 1, mono=2.0, wall=2.0)
    assert t.poll(wall=2.0 + 0.95) == gesture.HOLD


def test_kernel_clock_is_extrapolated_over_silence():
    """A button held with no further reports must still decide (R4): the
    kernel clock is anchored on the last event and run forward with wall
    time for the gap."""
    t = gesture.PressTracker()
    t.feed(1000.0, 1, mono=0.0, wall=500.0)
    assert t.kernel_now(wall=500.0) == pytest.approx(1000.0)
    assert t.kernel_now(wall=500.95) == pytest.approx(1000.95)
    assert t.held_for(wall=500.95) == pytest.approx(0.95)
    assert t.poll(wall=500.95) == gesture.HOLD


def test_kernel_clock_before_any_event_is_wall_time():
    assert gesture.kernel_now(0.0, 0.0, wall=123.0) == 123.0


def test_reset_forgets_the_press_but_keeps_the_counters():
    t = gesture.PressTracker()
    t.feed(1.0, 1, mono=0.0)
    t.feed(1.5, 0, mono=0.5)
    t.feed(2.0, 1, mono=1.0)
    t.reset()
    assert not t.button_down and t.down_since_k is None
    assert t.presses == 2                 # R5 cross-check evidence survives


def test_autorepeat_is_ignored():
    t = gesture.PressTracker()
    t.feed(1.0, 1, mono=0.0)
    assert t.feed(1.1, 2, mono=0.1) is None
    assert t.button_down


def test_handoff_and_staleness_deadlines():
    assert not gesture.handoff_overdue(3.9)
    assert gesture.handoff_overdue(4.1)
    assert not gesture.gesture_stale(True, 100.0)     # still held
    assert not gesture.gesture_stale(False, 7.9)
    assert gesture.gesture_stale(False, 8.1)


def test_chord_schedule_is_the_80ms_pacing():
    sched = gesture.chord_schedule()
    assert sched == ((0.0, 1), (0.080, 0))
    assert sched[1][0] - sched[0][0] == pytest.approx(gesture.CHORD_GAP)


def test_couchd_and_inputproc_share_one_threshold():
    """SR4 in one assertion: if these ever diverge, the shadow corpus stops
    being comparable to what the owning process actually did."""
    import couchd
    assert couchd.HOLD_SECONDS is gesture.HOLD_SECONDS
    assert couchd.HANDOFF_TIMEOUT is gesture.HANDOFF_TIMEOUT
    assert couchd.BTN_MODE == gesture.BTN_MODE


# =========================================================================
# persistence state machine (SR6)
# =========================================================================
def test_loss_emits_keys_up_once_then_silence():
    p = Persistence(persist_secs=120.0)
    assert p.state == OWNED
    assert p.on_loss(1000.0) == [A_KEYS_UP]
    assert p.state == LOST
    assert p.on_loss(1001.0) == []          # not again
    assert p.tick(1001.0) == []             # and nothing else is emitted


def test_hold_window_then_give_up_destroys_the_node():
    p = Persistence(persist_secs=120.0)
    p.on_loss(1000.0)
    assert p.tick(1119.9) == []
    assert p.remaining(1119.9) == pytest.approx(0.1)
    assert p.tick(1120.0) == [A_DESTROY]
    assert p.state == GONE
    assert p.remaining(1120.0) is None
    assert p.tick(1200.0) == []             # give-up happens once


def test_reconnect_inside_the_window_rekeys_and_reuploads():
    p = Persistence(persist_secs=120.0)
    p.on_loss(1000.0)
    assert p.on_reconnect(1030.0) == [A_KEYS_UP, A_REUPLOAD]
    assert p.state == OWNED
    assert p.remaining(1030.0) is None


def test_reconnect_after_give_up_recreates_the_node_first():
    p = Persistence(persist_secs=120.0)
    p.on_loss(1000.0)
    p.tick(1120.0)
    assert p.on_reconnect(1200.0) == [A_CREATE, A_KEYS_UP, A_REUPLOAD]
    assert p.state == OWNED


def test_reconnect_while_owned_is_a_no_op():
    p = Persistence()
    assert p.on_reconnect(1.0) == []
    assert p.state == OWNED


def test_a_full_flap_cycle_returns_to_owned_each_time():
    p = Persistence(persist_secs=10.0)
    for i in range(5):
        base = 1000.0 + i * 100
        assert p.on_loss(base) == [A_KEYS_UP]
        assert p.on_reconnect(base + 1) == [A_KEYS_UP, A_REUPLOAD]
        assert p.state == OWNED


def test_reupload_always_follows_a_rekey_never_precedes_it():
    """Order matters: re-uploading effects to a pad we have not yet cleared
    can start a rumble against a stuck button state."""
    for actions in ([Persistence(10.0).on_loss(0.0)],):
        assert actions
    p = Persistence(10.0)
    p.on_loss(0.0)
    acts = p.on_reconnect(1.0)
    assert acts.index(A_KEYS_UP) < acts.index(A_REUPLOAD)
    p2 = Persistence(10.0)
    p2.on_loss(0.0)
    p2.tick(20.0)
    acts2 = p2.on_reconnect(30.0)
    assert acts2.index(A_CREATE) < acts2.index(A_KEYS_UP) < acts2.index(A_REUPLOAD)


# =========================================================================
# permissions, ownership, flags
# =========================================================================
def test_read_only_fd_is_refused_loudly():
    """SR2: python-evdev falls back to O_RDONLY without saying so, and FF
    playback is a write(). Fail here, not three hours into a game."""
    with pytest.raises(PermissionError) as e:
        inputproc.assert_writable(os.O_RDONLY | os.O_NONBLOCK, '/dev/input/x')
    assert e.value.errno == errno.EACCES
    assert 'READ-ONLY' in str(e.value)
    assert inputproc.assert_writable(os.O_RDWR | os.O_NONBLOCK) is True


def test_ownership_is_ok_only_when_everything_is_ok():
    ok, problems = inputproc.evaluate_ownership('couchd-input', 0o020660, '')
    assert ok and problems == []


def test_ownership_rejects_a_leftover_ds2000_acl():
    acl = 'user::rw-\nuser:ds2000:rw-\ngroup::rw-\nother::---\n'
    ok, problems = inputproc.evaluate_ownership('couchd-input', 0o020660, acl)
    assert not ok
    assert any('ds2000' in p for p in problems)


def test_ownership_rejects_wrong_group_and_read_only_group():
    ok, problems = inputproc.evaluate_ownership('input', 0o020660, '')
    assert not ok and any('group is' in p for p in problems)
    ok, problems = inputproc.evaluate_ownership('couchd-input', 0o020640, '')
    assert not ok and any('rw' in p for p in problems)


def test_ownership_rejects_world_access():
    ok, problems = inputproc.evaluate_ownership('couchd-input', 0o020666, '')
    assert not ok and any('world' in p for p in problems)


def test_couchd_owns_flag_parsing():
    assert inputproc.owns('input', {'COUCHD_OWNS': 'input'})
    assert inputproc.owns('input', {'COUCHD_OWNS': 'gestures,input'})
    assert inputproc.owns('input', {'COUCHD_OWNS': 'gestures input'})
    assert not inputproc.owns('input', {'COUCHD_OWNS': 'gestures'})
    assert not inputproc.owns('input', {'COUCHD_OWNS': ''})
    assert not inputproc.owns('input', {})
    # substring must not count
    assert not inputproc.owns('input', {'COUCHD_OWNS': 'inputs'})
    assert not inputproc.owns('input', {'COUCHD_OWNS': 'not-input'})


def test_observe_mode_is_the_default_without_the_flag(monkeypatch):
    monkeypatch.delenv('COUCHD_OWNS', raising=False)
    assert not inputproc.owns('input')


# =========================================================================
# device discovery (parsing only - no devices)
# =========================================================================
PROC_TWO_PADS = '''\
I: Bus=0005 Vendor=054c Product=0ce6 Version=8111
N: Name="DualSense Wireless Controller"
U: Uniq=aa:bb:cc:dd:ee:ff
H: Handlers=event21 js0

I: Bus=0005 Vendor=054c Product=0ce6 Version=8111
N: Name="DualSense Wireless Controller Motion Sensors"
U: Uniq=aa:bb:cc:dd:ee:ff
H: Handlers=event22

I: Bus=0005 Vendor=054c Product=0ce6 Version=8111
N: Name="DualSense Wireless Controller Touchpad"
U: Uniq=aa:bb:cc:dd:ee:ff
H: Handlers=event23 mouse2

I: Bus=0005 Vendor=054c Product=0ce6 Version=8111
N: Name="DualSense Wireless Controller"
U: Uniq=de:ad:be:ef:fa:ce
H: Handlers=event31 js1
'''


def test_discovery_finds_button_nodes_only(tmp_path):
    p = tmp_path / 'devices'
    p.write_text(PROC_TWO_PADS)
    found = inputproc.find_pad(procfile=str(p))
    assert [f[0] for f in found] == ['/dev/input/event21', '/dev/input/event31']


def test_discovery_scopes_by_uniq(tmp_path):
    """The fake pad and the real one are the same model. MAC is the only
    thing that tells them apart (SR8)."""
    p = tmp_path / 'devices'
    p.write_text(PROC_TWO_PADS)
    fake = inputproc.find_pad(uniq='DE:AD:BE:EF:FA:CE', procfile=str(p))
    assert [f[0] for f in fake] == ['/dev/input/event31']
    real = inputproc.find_pad(uniq='aa:bb:cc:dd:ee:ff', procfile=str(p))
    assert [f[0] for f in real] == ['/dev/input/event21']
    assert inputproc.find_pad(uniq='00:00:00:00:00:00', procfile=str(p)) == []


def test_discovery_of_a_missing_procfile_is_empty_not_an_error():
    assert inputproc.find_pad(procfile='/nonexistent/devices') == []


# =========================================================================
# the rig's own safety predicates
# =========================================================================
def load_fake_pad():
    import importlib.machinery
    import importlib.util
    path = os.path.expanduser('~/couch/tools/fake-pad')
    if not os.path.exists(path):
        pytest.skip('tools/fake-pad not present')
    loader = importlib.machinery.SourceFileLoader('fake_pad_under_test', path)
    spec = importlib.util.spec_from_loader('fake_pad_under_test', loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)          # imports only; creates nothing
    return mod


def test_rig_refuses_when_a_real_pad_is_connected(tmp_path):
    mod = load_fake_pad()
    p = tmp_path / 'devices'
    p.write_text(PROC_TWO_PADS)
    assert mod.real_pad_present(procfile=str(p)) == 'aa:bb:cc:dd:ee:ff'


def test_rig_is_happy_when_only_the_fake_pad_is_there(tmp_path):
    mod = load_fake_pad()
    p = tmp_path / 'devices'
    p.write_text(PROC_TWO_PADS.split('\n\n')[-1])
    assert mod.real_pad_present(procfile=str(p)) is None


def test_rig_fake_mac_is_nothing_like_the_real_one():
    mod = load_fake_pad()
    assert mod.FAKE_MAC != mod.REAL_MAC
    assert mod.FAKE_MAC.split(':')[0] != mod.REAL_MAC.split(':')[0]
    assert all(len(b) == 2 and int(b, 16) >= 0 for b in mod.FAKE_MAC.split(':'))
    assert len(mod.FAKE_MAC.split(':')) == 6


def test_rig_detects_corpus_pollution():
    """SR8: a rig run that adds a file to ~/couch/recordings has polluted
    the gesture corpus, and the comparator would silently eat it."""
    mod = load_fake_pad()
    assert mod.compare_recordings(['a.gz'], ['a.gz']) == []
    assert mod.compare_recordings(['a.gz'], ['a.gz', 'b.gz']) == ['b.gz']


def test_rig_can_send_the_ps_button():
    """hid-tools caps self.buttons at 12, which makes button 13 - BTN_MODE,
    the entire point of the rig - unsendable. The subclass fixes it; this
    asserts the index it relies on has not moved."""
    mod = load_fake_pad()
    assert mod.BUTTONS['ps'] == 13
    from hidtools.device.sony_gamepad import PS5Controller
    assert PS5Controller.buttons_map[13] == 'BTN_MODE'


# =========================================================================
# small helpers
# =========================================================================
def test_percentiles_for_the_latency_budget():
    """E1 reports p50/p99 against a <10ms p99 budget (SR9)."""
    values = [i / 1000.0 for i in range(1, 101)]
    assert inputproc.percentile(values, 50) == pytest.approx(0.050, abs=0.002)
    assert inputproc.percentile(values, 99) == pytest.approx(0.099, abs=0.002)
    assert inputproc.percentile([], 50) is None
    assert inputproc.percentile([0.5], 99) == 0.5
