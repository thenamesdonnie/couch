"""DIRDASH v4: v3 plus the two fixes found by tracing the live graph.

  1. The Lower layer drives the legs and the root motion (worldFromModelWeight 1.0)
     and it runs 'Move StateMachine_mirror', whose Dash* state infos are SEPARATE
     objects from the Upper layer's. v3 retargeted only the Upper ones, so the
     visible dash never left the stock forward CMSG. v4 retargets both, sharing one
     selector between the layers exactly as stock Walk/Run/RunEnd/WalkEnd do.
  2. generatorChangedTransitionEffect is set to the same hkbBlendingTransitionEffect
     all four stock direction selectors use, instead of null.

DIAG mode additionally points the Dash selector's forward slot at DashStrafeLeft,
so an ordinary unlocked forward sprint visibly plays a strafe if our objects are live.
"""
import sys, hashlib
from pf import Packfile
from append_hkx import Appender

DIAG = '--diag' in sys.argv
SRC = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx'
OUT = ('/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.diag.hkx' if DIAG
       else '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash4.hkx')
RATIO = (4.3188 / 0.6666666865348816) / (2.776 / 0.7333333)
SZ_CLIP, SZ_CMSG, SZ_MSG, SZ_VBS = 352, 256, 216, 48

pf = Packfile(SRC); cls = dict(pf.items)
def nm(o):
    try: return pf.cstr(o + 56) or ''
    except Exception: return ''
byname = {}
for o, c in pf.items:
    if nm(o): byname.setdefault((c, nm(o)), o)
def find(c, n):
    o = byname.get((c, n)); assert o, (c, n); return o

def states_of(sm):
    p, n = pf.array(sm + 208)
    return {pf.cstr(pf.ptr(p + i*8) + 96): pf.ptr(p + i*8) for i in range(n)}
UPPER = states_of(find('hkbStateMachine', 'Move StateMachine'))
LOWER = states_of(states_of(find('hkbStateMachine', 'Lower'))['LocomotionLower'] and
                  find('hkbStateMachine', 'Move StateMachine_mirror'))

RUNSEL = find('hkbManualSelectorGenerator', 'Run Normal Light Direction ManualSelectorGenerator')
RUNVBS = pf.ptr(RUNSEL + 16)
RUNTE  = pf.ptr(RUNSEL + 176)
assert cls[RUNTE] == 'hkbBlendingTransitionEffect', cls.get(RUNTE)

A = Appender(SRC)

def clone_clip(src_off):
    assert pf.ptr(src_off + 152) is None
    body = pf.data[src_off:src_off + SZ_CLIP]
    assert body[56:64] == b'\0'*8 and body[144:152] == b'\0'*8
    o = A.add_object('hkbClipGenerator', SZ_CLIP, body)
    A.add_local(o + 56,  A.add_string(pf.cstr(src_off + 56) + '_DashSpd'))
    A.add_local(o + 144, A.add_string(pf.cstr(src_off + 144)))
    A.f32(o + 176, RATIO)
    return o

def clone_strafe_cmsg(src_off, label):
    kp, kn = pf.array(src_off + 136)
    kids = [clone_clip(pf.ptr(kp + i*8)) for i in range(kn)]
    o = A.add_object('CustomManualSelectorGenerator', SZ_CMSG, pf.data[src_off:src_off + SZ_CMSG])
    A.add_local(o + 56, A.add_string('DashStrafe' + label))
    arr = A.set_array(o, 136, 8, len(kids))
    for i, k in enumerate(kids): A.add_global(arr + i*8, k)
    te = pf.ptr(src_off + 168)
    if te is not None: A.add_global(o + 168, te)
    print("  %-6s CMSG @%#x  %d clips @ speed %.6f (animId %d)" % (label, o, len(kids), RATIO, pf.s32(src_off + 156)))
    return o

def make_selector(label, children):
    vbs = A.add_object('hkbVariableBindingSet', SZ_VBS, pf.data[RUNVBS:RUNVBS + SZ_VBS])
    bp, bn = pf.array(RUNVBS + 16)
    barr = A.set_array(vbs, 16, 40, bn)
    for i in range(bn):
        A.data[barr + i*40:barr + (i+1)*40] = pf.data[bp + i*40:bp + (i+1)*40]
        A.add_local(barr + i*40, A.add_string(pf.cstr(bp + i*40)))
    sel = A.add_object('hkbManualSelectorGenerator', SZ_MSG, pf.data[RUNSEL:RUNSEL + SZ_MSG])
    A.add_global(sel + 16, vbs)
    A.add_local(sel + 56, A.add_string(label + ' Direction ManualSelectorGenerator'))
    A.add_global(sel + 176, RUNTE)          # FIX 2: match the stock direction selectors
    arr = A.set_array(sel, 136, 8, len(children))
    for i, c in enumerate(children): A.add_global(arr + i*8, c)
    return sel, arr

print("RATIO %.6f   DIAG=%s" % (RATIO, DIAG))
BACK  = clone_strafe_cmsg(find('CustomManualSelectorGenerator', 'RunBack Normal Light'),  'Back')
LEFT  = clone_strafe_cmsg(find('CustomManualSelectorGenerator', 'RunLeft Normal Light'),  'Left')
RIGHT = clone_strafe_cmsg(find('CustomManualSelectorGenerator', 'RunRight Normal Light'), 'Right')

PLAN = [
    ('DashStart', 'DashStart', 'DashStart_mirror', 'DashStart CustomManualSelectorGenerator', BACK, LEFT, RIGHT),
    ('Dash',      'Dash',      'Dash_mirror',      'Dash CustomManualSelectorGenerator',      BACK, LEFT, RIGHT),
    ('DashEnd',   'DashEnd',   'DashEnd_mirror',   'DashEnd CustomManualSelectorGenerator',
        find('CustomManualSelectorGenerator', 'RunEnd Back CustomManualSelectorGenerator'),
        find('CustomManualSelectorGenerator', 'RunEnd Left CustomManualSelectorGenerator'),
        find('CustomManualSelectorGenerator', 'RunEnd Right CustomManualSelectorGenerator')),
]
for label, up, lo, fwd_name, b, l, r in PLAN:
    fwd = find('CustomManualSelectorGenerator', fwd_name)
    sel, arr = make_selector(label, [fwd, b, l, r])
    if DIAG and label == 'Dash':
        A.retarget_global(arr + 0, LEFT)
        print("     DIAG: %s selector forward slot -> DashStrafeLeft" % label)
    for layer, sname, table in (('Upper', up, UPPER), ('Lower', lo, LOWER)):
        st = table[sname]
        old = A.retarget_global(st + 88, sel)
        print("     %-5s '%s' info@%#x  generator %#x -> %#x" % (layer, sname, st, old, sel))

out = A.build()
open(OUT, 'wb').write(out)
print("\nwrote %s  %d bytes  sha256 %s" % (OUT, len(out), hashlib.sha256(out).hexdigest()[:16]))
orig = open(SRC, 'rb').read()
print("stock data region preserved verbatim:", out[A.dabs:A.dabs + pf.dloc] == orig[A.dabs:A.dabs + pf.dloc])
