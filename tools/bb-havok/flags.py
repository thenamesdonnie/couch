from pf import Packfile
B='/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash3.hkx'
pf=Packfile(B); cls=dict(pf.items)
def nm(o):
    try: return pf.cstr(o+56) or ''
    except Exception: return ''
def show(o):
    vbs=pf.ptr(o+16); te=pf.ptr(o+176)
    b=''
    if vbs:
        p,n=pf.array(vbs+16)
        b=' | '.join("memberPath=%r varIdx=%d bitIdx=%d type=%d"%(pf.cstr(p+i*40),pf.s32(p+i*40+28),pf.s8(p+i*40+32),pf.u8(p+i*40+33)) for i in range(n))
    print("%-46s selIdx=%-3d indexSelector=%-6s canChangeAfterActivate=%-5s genChangedTE=%-22s endOfClipEventId=%-4d"%(
        nm(o),pf.s16(o+152),'null' if not pf.ptr(o+160) else hex(pf.ptr(o+160)),
        bool(pf.u8(o+168)), (cls.get(te,'null') if te else 'null'), pf.s32(o+208)))
    print("      binding: %s"%(b or 'NONE'))
targets=['Run Normal Light Direction ManualSelectorGenerator','Walk Normal Light Direction ManualSelectorGenerator',
         'RunEnd Direction ManualSelectorGenerator','WalkEnd Direction ManualSelectorGenerator',
         'DashStart Direction ManualSelectorGenerator','Dash Direction ManualSelectorGenerator','DashEnd Direction ManualSelectorGenerator']
for t in targets:
    for o,c in pf.items:
        if c=='hkbManualSelectorGenerator' and nm(o)==t: show(o); break
# order of Run direction children -> animIds
run=[o for o,c in pf.items if c=='hkbManualSelectorGenerator' and nm(o)=='Run Normal Light Direction ManualSelectorGenerator'][0]
p,n=pf.array(run+136)
print("\nRun direction child order (index -> animId):")
for i in range(n):
    g=pf.ptr(p+i*8)
    if cls.get(g)=='CustomManualSelectorGenerator': print("   [%d] %-30s animId=%d"%(i,nm(g),pf.s32(g+156)))
    else:
        gp,gn=pf.array(g+136); g0=pf.ptr(gp)
        print("   [%d] %-30s (selector) first child animId=%d"%(i,nm(g),pf.s32(g0+156)))
