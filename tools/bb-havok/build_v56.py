"""DIRDASH v5 / v6, both by the byte-exact append method, both retargeting the
Upper and Lower state machines like v4.

  v5  sideways/back slots point at the STOCK run strafe CMSGs, no clones, speed 1.0.
  v6  clones kept, named EXACTLY like their stock originals, only playbackSpeed changed.
"""
import sys, hashlib
from pf import Packfile
from append_hkx import Appender

MODE = 'v6' if '--v6' in sys.argv else 'v5'
SRC = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx'
OUT = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash%s.hkx' % MODE[1]
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
LOWER = states_of(find('hkbStateMachine', 'Move StateMachine_mirror'))
RUNSEL = find('hkbManualSelectorGenerator', 'Run Normal Light Direction ManualSelectorGenerator')
RUNVBS = pf.ptr(RUNSEL + 16); RUNTE = pf.ptr(RUNSEL + 176)

A = Appender(SRC)

def clone_clip(src_off):
    assert pf.ptr(src_off + 152) is None
    o = A.add_object('hkbClipGenerator', SZ_CLIP, pf.data[src_off:src_off + SZ_CLIP])
    A.add_local(o + 56,  A.add_string(pf.cstr(src_off + 56)))   # v6: EXACT stock name
    A.add_local(o + 144, A.add_string(pf.cstr(src_off + 144)))
    A.f32(o + 176, RATIO)
    return o

def clone_strafe_cmsg(src_off, label):
    kp, kn = pf.array(src_off + 136)
    kids = [clone_clip(pf.ptr(kp + i*8)) for i in range(kn)]
    o = A.add_object('CustomManualSelectorGenerator', SZ_CMSG, pf.data[src_off:src_off + SZ_CMSG])
    A.add_local(o + 56, A.add_string(nm(src_off)))               # v6: EXACT stock name
    arr = A.set_array(o, 136, 8, len(kids))
    for i, k in enumerate(kids): A.add_global(arr + i*8, k)
    te = pf.ptr(src_off + 168)
    if te is not None: A.add_global(o + 168, te)
    print("  cloned %-22s -> @%#x  %d clips, name kept %r, speed %.6f"
          % (label, o, len(kids), pf.cstr(kp and pf.ptr(kp) or 0 and 0 or pf.ptr(kp)) if False else nm(src_off), RATIO))
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
    A.add_global(sel + 176, RUNTE)
    arr = A.set_array(sel, 136, 8, len(children))
    for i, c in enumerate(children): A.add_global(arr + i*8, c)
    return sel

RB = find('CustomManualSelectorGenerator', 'RunBack Normal Light')
RL = find('CustomManualSelectorGenerator', 'RunLeft Normal Light')
RR = find('CustomManualSelectorGenerator', 'RunRight Normal Light')
print("MODE %s  RATIO %.6f" % (MODE, RATIO))
if MODE == 'v6':
    BACK, LEFT, RIGHT = (clone_strafe_cmsg(RB, 'Back'), clone_strafe_cmsg(RL, 'Left'), clone_strafe_cmsg(RR, 'Right'))
else:
    BACK, LEFT, RIGHT = RB, RL, RR
    print("  no clones: sideways slots use the stock run strafe CMSGs at speed 1.0")

PLAN = [
    ('DashStart', 'DashStart', 'DashStart_mirror', 'DashStart CustomManualSelectorGenerator', BACK, LEFT, RIGHT),
    ('Dash',      'Dash',      'Dash_mirror',      'Dash CustomManualSelectorGenerator',      BACK, LEFT, RIGHT),
    ('DashEnd',   'DashEnd',   'DashEnd_mirror',   'DashEnd CustomManualSelectorGenerator',
        find('CustomManualSelectorGenerator', 'RunEnd Back CustomManualSelectorGenerator'),
        find('CustomManualSelectorGenerator', 'RunEnd Left CustomManualSelectorGenerator'),
        find('CustomManualSelectorGenerator', 'RunEnd Right CustomManualSelectorGenerator')),
]
for label, up, lo, fwd_name, b, l, r in PLAN:
    sel = make_selector(label, [find('CustomManualSelectorGenerator', fwd_name), b, l, r])
    for layer, sname, table in (('Upper', up, UPPER), ('Lower', lo, LOWER)):
        old = A.retarget_global(table[sname] + 88, sel)
        print("     %-5s %-18s generator %#x -> %#x" % (layer, sname, old, sel))

out = A.build()
open(OUT, 'wb').write(out)
orig = open(SRC, 'rb').read()
print("\nwrote %s  %d bytes  sha256 %s" % (OUT, len(out), hashlib.sha256(out).hexdigest()[:16]))
print("stock data region preserved verbatim:", out[A.dabs:A.dabs + pf.dloc] == orig[A.dabs:A.dabs + pf.dloc])
