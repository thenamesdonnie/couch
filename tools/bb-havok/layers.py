from pf import Packfile
B='/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash3.hkx'
pf=Packfile(B); cls=dict(pf.items)
def nm(o):
    try: return pf.cstr(o+56) or ''
    except Exception: return ''
LB=0x176ce0
p,n=pf.array(LB+160)
print("=== 'Locomotion Blend' hkbBlenderGenerator @%#x children=%d ==="%(LB,n))
for i in range(n):
    ch=pf.ptr(p+i*8)
    g=pf.ptr(ch+48); bw=pf.ptr(ch+56)
    vbs=pf.ptr(ch+16)
    print("  child[%d] weight=%.3f worldFromModelWeight=%.3f boneWeights=%s gen=%s '%s'"%(
        i,pf.f32(ch+64),pf.f32(ch+68),'yes' if bw else 'no',cls.get(g),nm(g)))
for lay in (0x176e40,0x2c37b0):
    p2,n2=pf.array(lay+208)
    print("\n=== '%s' hkbStateMachine @%#x states=%d ==="%(nm(lay),lay,n2))
    for i in range(n2):
        sp=pf.ptr(p2+i*8); g=pf.ptr(sp+88)
        print("   state %-3d %-22r -> %s '%s'"%(pf.s32(sp+104),pf.cstr(sp+96),cls.get(g),nm(g)))
for sm,label in ((0x177070,'Move StateMachine'),(0x2c39e0,'Move StateMachine_mirror')):
    p3,n3=pf.array(sm+208)
    print("\n=== %s @%#x ==="%(label,sm))
    for i in range(n3):
        sp=pf.ptr(p3+i*8); g=pf.ptr(sp+88)
        print("   state %-3d %-12r info@%#-9x -> %-30s @%#x '%s'"%(
            pf.s32(sp+104),pf.cstr(sp+96),sp,cls.get(g),g,nm(g)))
