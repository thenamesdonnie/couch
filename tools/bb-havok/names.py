import re, collections
from pf import Packfile
pf=Packfile('/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx')
clips=[o for o,c in pf.items if c=='hkbClipGenerator']
pat=re.compile(r'^(a\d{3}_\d{6})_hkx_AutoSet_(\d+)$')
bad=[]; names=collections.Counter(); mismatch=0
for o in clips:
    n=pf.cstr(o+56); a=pf.cstr(o+144)
    names[n]+=1
    m=pat.match(n or '')
    if not m: bad.append((o,n,a))
    elif m.group(1)!=a: mismatch+=1
print("clip generators: %d"%len(clips))
print("names NOT matching '<animationName>_hkx_AutoSet_NN': %d"%len(bad))
for o,n,a in bad[:8]: print("    @%#x name=%r animationName=%r"%(o,n,a))
print("names where the prefix != animationName: %d"%mismatch)
print("name == animationName anywhere: %d"%sum(1 for o in clips if pf.cstr(o+56)==pf.cstr(o+144)))
dups=[(n,c) for n,c in names.most_common() if c>1]
print("DUPLICATE clip names in stock: %d  (top: %s)"%(len(dups),dups[:3]))
# H3: flags on the 87 source clips vs the dash clips
def clipinfo(o):
    return (pf.f32(o+176), pf.u8(o+190), pf.s8(o+191), pf.s16(o+188), pf.f32(o+172), pf.f32(o+180), pf.ptr(o+152) is not None)
def cmsgkids(name):
    src=[o for o,c in pf.items if c=='CustomManualSelectorGenerator' and pf.cstr(o+56)==name][0]
    p,n=pf.array(src+136)
    return src,[pf.ptr(p+i*8) for i in range(n)]
print("\n(playbackSpeed, mode, flags, animationBindingIndex, startTime, enforcedDuration, hasTriggers)")
for nm2 in ('Dash CustomManualSelectorGenerator','RunLeft Normal Light','RunBack Normal Light','RunRight Normal Light'):
    src,ks=cmsgkids(nm2)
    st=set(clipinfo(k) for k in ks)
    print("  %-36s kids=%-3d distinct=%s"%(nm2,len(ks),st))
# H2: full CMSG field comparison
print("\nCMSG fields: offsetType animId animeEndEventType enableScript enableTae changeType checkAnimEndSlotNo replanningAI TE")
for nm2 in ('Dash CustomManualSelectorGenerator','DashStart CustomManualSelectorGenerator','DashEnd CustomManualSelectorGenerator',
            'RunLeft Normal Light','RunBack Normal Light','RunRight Normal Light','RunFront Normal Light'):
    src=[o for o,c in pf.items if c=='CustomManualSelectorGenerator' and pf.cstr(o+56)==nm2][0]
    te=pf.ptr(src+168)
    print("  %-38s %-3d %-6d %-3d %d %d %-3d %-3d %-3d %s"%(nm2,pf.s32(src+152),pf.s32(src+156),pf.s32(src+160),
        pf.u8(src+164),pf.u8(src+165),pf.u8(src+166),pf.s32(src+176),pf.u8(src+180),hex(te) if te else 'null'))
