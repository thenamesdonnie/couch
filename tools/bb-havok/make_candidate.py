import struct
from patch_hkx import Patcher, SRC
from pf import Packfile

OUT = '/home/ds2000/couch/data/bb-hks/anibnd/c0000_behavior.candidate.hkx'
p = Patcher()
pf = p.pf
d = p.buf

# locate the Move StateMachine 'Dash' state (stateId 11)
SM = 0x177070
arr,n = pf.array(SM+208)
dash_state = None
for i in range(n):
    sp = pf.ptr(arr+i*8)
    if pf.s32(sp+104) == 11:
        dash_state = sp
print("Dash state @%#x '%s' generator=%s" % (dash_state, pf.cstr(dash_state+96), hex(pf.ptr(dash_state+88))))

RUN_SELECTOR = 0x18a9f0   # 'Run ManualSelectorGenerator' (UpperCondition -> MoveDirection -> Front/Back/Left/Right)

# the generator pointer at dash_state+88 is a GLOBAL fixup; rewrite the fixup table entry
src_off = dash_state + 88
found = False
for o in range(pf.dabs+pf.dglob, pf.dabs+pf.dvirt, 12):
    s, si, t = struct.unpack_from('<III', d, o)
    if s == src_off:
        struct.pack_into('<III', d, o, s, si, RUN_SELECTOR)
        print("global fixup @%#x: src %#x  dst %#x -> %#x" % (o, s, t, RUN_SELECTOR))
        found = True
        break
assert found, "generator fixup not located"
p.write(OUT)

# verify
q = Packfile(OUT)
qarr,qn = q.array(SM+208)
for i in range(qn):
    sp = q.ptr(qarr+i*8)
    if q.s32(sp+104) == 11:
        g = q.ptr(sp+88)
        print("VERIFY Dash.generator -> %s '%s'" % (dict(q.items).get(g), q.cstr(g+56)))
a = open(SRC,'rb').read(); b = open(OUT,'rb').read()
print("size same:", len(a)==len(b), " differing bytes:", sum(1 for x,y in zip(a,b) if x!=y))
print("items:", len(q.items))
