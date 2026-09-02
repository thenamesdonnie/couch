import collections, re
from pf import Packfile
A=Packfile('/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx')
b=Packfile('/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash7.hkx')
cls=dict(b.items)
def nm(o):
    try: return b.cstr(o+56) or ''
    except Exception: return ''
ca=collections.Counter(v for _,v in A.items); cb=collections.Counter(v for _,v in b.items)
print("reuse_padding stock=%d v7=%d"%(A.d[18],b.d[18]))
print("objects %d -> %d  delta %s"%(len(A.items),len(b.items),{k:cb[k]-ca[k] for k in set(ca)|set(cb) if cb[k]!=ca[k]}))
print("stock objects unmoved + same class:", A.items==b.items[:len(A.items)])
nc=tot=0
for o,c in b.items:
    if c=='hkbStateMachineTransitionInfoArray':
        p,n=b.array(o+16)
        for i in range(n):
            tot+=1
            if b.ptr(p+i*72+40): nc+=1
print("transitions %d  non-null conditions %d"%(tot,nc))
# name uniqueness across the whole file
names=collections.Counter()
for o,c in b.items:
    n=nm(o)
    if n: names[n]+=1
dups=[k for k,v in names.items() if v>1]
print("named objects %d  DUPLICATE names: %d %s"%(sum(names.values()),len(dups),dups[:5]))
# clip name format compliance for every clip
PAT=re.compile(r'^(.*)_hkx_AutoSet_(\d+)$')
bad=[]
for o,c in b.items:
    if c!='hkbClipGenerator': continue
    n=nm(o); a=b.cstr(o+144); m=PAT.match(n or '')
    if not m:
        if n!=a+'.hkx' and n!=a.replace('_',' ',1)+'.hkx': bad.append((n,a))
    elif m.group(1)!=a: bad.append((n,a))
print("clips whose name does not encode animationName: %d %s"%(len(bad),bad[:4]))
newclips=[o for o,c in b.items[len(A.items):] if c=='hkbClipGenerator']
print("new clip names sample:",[nm(o) for o in newclips[:3]],"... speeds distinct:",set(round(b.f32(o+176),6) for o in newclips))
sd=[o for o,c in b.items if c=='hkbBehaviorGraphStringData'][0]
def sa(pf,o):
    p,n=pf.array(o); return [pf.cstr(p+i*8) for i in range(n)] if p else []
V=sa(b,sd+48); DIR=['Front','Back','Left','Right']
for smn in ('Move StateMachine','Move StateMachine_mirror'):
    sm=[o for o,c in b.items if c=='hkbStateMachine' and nm(o)==smn][0]
    p,n=b.array(sm+208)
    print("\n-- %s --"%smn)
    for i in range(n):
        sp=b.ptr(p+i*8); s=b.cstr(sp+96)
        if not s.startswith('Dash'): continue
        g=b.ptr(sp+88); vbs=b.ptr(g+16); bp,bn=b.array(vbs+16)
        print("  %-18s -> %-40s bind %s<-%s"%(s,nm(g),b.cstr(bp),V[b.s32(bp+28)]))
        gp,gn=b.array(g+136)
        for j in range(gn):
            ch=b.ptr(gp+j*8); cp,cn=b.array(ch+136); k0=b.ptr(cp)
            print("     %-6s %-34s animId=%-5d animeEnd=%d kids=%-3d clip0=%r speed=%.6f"%(
                DIR[j],nm(ch),b.s32(ch+156),b.s32(ch+160),cn,nm(k0),b.f32(k0+176)))
