from pf import Packfile
import collections
pf=Packfile('/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx')
allo=sorted(o for o,_ in pf.items)
nextof={o:(allo[i+1] if i+1<len(allo) else pf.dloc) for i,o in enumerate(allo)}
loc=set(pf.local); glo=set(pf.glob)
res=collections.defaultdict(lambda: collections.Counter())
gapmin=collections.defaultdict(lambda: 10**9)
for o,c in pf.items:
    nx=nextof[o]
    gapmin[c]=min(gapmin[c], nx-o)
    for r in range(0,nx-o,8):
        if o+r in loc: res[c][('L',r)]+=1
        if o+r in glo: res[c][('G',r)]+=1
for c in ('hkbClipGenerator','CustomManualSelectorGenerator','hkbManualSelectorGenerator','hkbVariableBindingSet','hkbStateMachineStateInfo'):
    ptr=sorted(res[c].items())
    mx=max(r for (_k,r),_n in ptr) if ptr else -1
    print("%-32s n=%-5d minGapToNextObj=%-5d maxPtrOffset=%-4d ptrs=%s"%(
        c,sum(1 for _,cc in pf.items if cc==c),gapmin[c],mx,
        [(k,r,n) for (k,r),n in ptr]))
# header bytes of a clip generator
o=0x1070  # any object
print("\nfirst 16 bytes of some objects (vtable/refcount area):")
for o,c in pf.items[:1]+[(x,y) for x,y in pf.items if y=='hkbClipGenerator'][:2]:
    print("  %-30s %s"%(c, pf.data[o:o+16].hex(' ',4)))
# fixup region padding bytes
d=pf.d
print("\npadding after local fixups:", d[pf.dabs+pf.dglob-8:pf.dabs+pf.dglob].hex())
print("padding after global fixups:", d[pf.dabs+pf.dvirt-8:pf.dabs+pf.dvirt].hex())
print("padding after virtual fixups:", d[pf.dabs+pf.dexp-8:pf.dabs+pf.dexp].hex())
print("data region tail:", d[pf.dabs+pf.dloc-16:pf.dabs+pf.dloc].hex(' ',4))
print("\nlocal fixups sorted by src:", sorted(pf.local)==list(pf.local.keys()))
