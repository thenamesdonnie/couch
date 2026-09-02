"""DIRDASH v3: same content as v2, built with the byte-exact append editor."""
import struct, hashlib
from pf import Packfile
from append_hkx import Appender

SRC = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx'
OUT = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash3.hkx'
RATIO = (4.3188 / 0.6666666865348816) / (2.776 / 0.7333333)   # 1.711340

SZ_CLIP, SZ_CMSG, SZ_MSG, SZ_VBS = 352, 256, 216, 48

pf = Packfile(SRC)
cls = dict(pf.items)
byname = {}
for o, c in pf.items:
    n = pf.cstr(o + 56) if c != 'hkbStateMachineStateInfo' else None
    if n:
        byname.setdefault((c, n), o)

def find(c, n):
    o = byname.get((c, n)); assert o, (c, n); return o

# --- Move StateMachine state infos ---
SM = [o for o, c in pf.items if c == 'hkbStateMachine' and pf.cstr(o + 56) == 'Move StateMachine'][0]
sp, sn = pf.array(SM + 208)
states = {}
for i in range(sn):
    s = pf.ptr(sp + i * 8)
    states[pf.cstr(s + 96)] = s

RUNSEL = find('hkbManualSelectorGenerator', 'Run Normal Light Direction ManualSelectorGenerator')
RUNVBS = pf.ptr(RUNSEL + 16)
assert cls[RUNVBS] == 'hkbVariableBindingSet'
print("template selector @%#x  binding set @%#x" % (RUNSEL, RUNVBS))

A = Appender(SRC)

def clone_clip(src_off, speed):
    """New hkbClipGenerator: identical bytes, new name string, new playbackSpeed."""
    assert pf.ptr(src_off + 152) is None, "clip %#x has triggers" % src_off
    body = pf.data[src_off:src_off + SZ_CLIP]
    assert body[56:64] == b'\0'*8 and body[144:152] == b'\0'*8
    o = A.add_object('hkbClipGenerator', SZ_CLIP, body)
    A.add_local(o + 56,  A.add_string(pf.cstr(src_off + 56) + '_DashSpd'))
    A.add_local(o + 144, A.add_string(pf.cstr(src_off + 144)))
    A.f32(o + 176, speed)
    return o

def clone_strafe_cmsg(src_off, label):
    kids_p, kids_n = pf.array(src_off + 136)
    new_kids = [clone_clip(pf.ptr(kids_p + i * 8), RATIO) for i in range(kids_n)]
    body = pf.data[src_off:src_off + SZ_CMSG]
    o = A.add_object('CustomManualSelectorGenerator', SZ_CMSG, body)
    A.add_local(o + 56, A.add_string('DashStrafe' + label))
    arr = A.set_array(o, 136, 8, len(new_kids))
    for i, k in enumerate(new_kids):
        A.add_global(arr + i * 8, k)
    te = pf.ptr(src_off + 168)          # generatorChangedTransitionEffect
    if te is not None:
        A.add_global(o + 168, te)
    print("  %-16s -> CMSG @%#x with %d cloned clips at speed %.6f (animId %d)"
          % (label, o, len(new_kids), RATIO, pf.s32(src_off + 156)))
    return o

def make_selector(label, children):
    """Clone the stock Run direction selector + its MoveDirection binding set."""
    vbs = A.add_object('hkbVariableBindingSet', SZ_VBS, pf.data[RUNVBS:RUNVBS + SZ_VBS])
    bp, bn = pf.array(RUNVBS + 16)
    barr = A.set_array(vbs, 16, 40, bn)
    for i in range(bn):
        A.data[barr + i*40:barr + (i+1)*40] = pf.data[bp + i*40:bp + (i+1)*40]
        A.add_local(barr + i*40, A.add_string(pf.cstr(bp + i*40)))
    sel = A.add_object('hkbManualSelectorGenerator', SZ_MSG, pf.data[RUNSEL:RUNSEL + SZ_MSG])
    A.add_global(sel + 16, vbs)
    A.add_local(sel + 56, A.add_string(label + ' Direction ManualSelectorGenerator'))
    arr = A.set_array(sel, 136, 8, len(children))
    for i, c in enumerate(children):
        A.add_global(arr + i * 8, c)
    # v2 parity: generatorChangedTransitionEffect stays null (not replicated from template)
    print("  %-9s selector @%#x  vbs @%#x  bindings %d  children %s"
          % (label, sel, vbs, bn, [hex(c) for c in children]))
    return sel

print("RATIO = %.6f" % RATIO)
BACK  = clone_strafe_cmsg(find('CustomManualSelectorGenerator', 'RunBack Normal Light'),  'Back')
LEFT  = clone_strafe_cmsg(find('CustomManualSelectorGenerator', 'RunLeft Normal Light'),  'Left')
RIGHT = clone_strafe_cmsg(find('CustomManualSelectorGenerator', 'RunRight Normal Light'), 'Right')

PLAN = [
    ('DashStart', 'DashStart CustomManualSelectorGenerator', BACK, LEFT, RIGHT),
    ('Dash',      'Dash CustomManualSelectorGenerator',      BACK, LEFT, RIGHT),
    ('DashEnd',   'DashEnd CustomManualSelectorGenerator',
        find('CustomManualSelectorGenerator', 'RunEnd Back CustomManualSelectorGenerator'),
        find('CustomManualSelectorGenerator', 'RunEnd Left CustomManualSelectorGenerator'),
        find('CustomManualSelectorGenerator', 'RunEnd Right CustomManualSelectorGenerator')),
]
for label, fwd_name, b, l, r in PLAN:
    fwd = find('CustomManualSelectorGenerator', fwd_name)
    sel = make_selector(label, [fwd, b, l, r])
    st = states[label]
    old = A.retarget_global(st + 88, sel)
    print("     state '%s' @%#x generator %#x -> %#x" % (label, st, old, sel))

out = A.build()
open(OUT, 'wb').write(out)
orig = open(SRC, 'rb').read()
print("\nstock %d -> v3 %d bytes (+%d)" % (len(orig), len(out), len(out) - len(orig)))
print("stock prefix preserved verbatim up to end of stock data region (%#x): %s"
      % (pf.dloc, out[A.dabs:A.dabs + pf.dloc] == orig[A.dabs:A.dabs + pf.dloc]))
print("header + section table unchanged except __data__ sizes:",
      out[:0x40] == orig[:0x40] and out[0x40:0xC0] == orig[0x40:0xC0])
print("sha256", hashlib.sha256(out).hexdigest()[:16])
