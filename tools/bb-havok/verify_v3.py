from pf import Packfile
import collections
A='/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx'
B='/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash3.hkx'
a=Packfile(A); b=Packfile(B); cls=dict(b.items)
print("reuse_base_class_padding: stock=%d v3=%d"%(a.d[18],b.d[18]))
print("objects %d -> %d (%+d)"%(len(a.items),len(b.items),len(b.items)-len(a.items)))
ca=collections.Counter(v for _,v in a.items); cb=collections.Counter(v for _,v in b.items)
print("class delta:",{k:cb[k]-ca[k] for k in set(ca)|set(cb) if cb[k]!=ca[k]})
print("fixups local %d->%d global %d->%d virtual %d->%d"%(len(a.local),len(b.local),len(a.glob),len(b.glob),len(a.virt),len(b.virt)))
nc=tot=0
for o,c in b.items:
    if c=='hkbStateMachineTransitionInfoArray':
        p,n=b.array(o+16)
        for i in range(n):
            tot+=1
            if b.ptr(p+i*72+40): nc+=1
print("transitions %d, non-null conditions %d"%(tot,nc))
sd=[o for o,c in b.items if c=='hkbBehaviorGraphStringData'][0]
sda=[o for o,c in a.items if c=='hkbBehaviorGraphStringData'][0]
def sa(pf,o):
    p,n=pf.array(o); return [pf.cstr(p+i*8) for i in range(n)] if p else []
V=sa(b,sd+48)
print("event+variable tables identical:",(sa(a,sda+16),sa(a,sda+48))==(sa(b,sd+16),V))
# every stock object still parses to the same class at the same offset
print("all stock objects unmoved and same class:", a.items==b.items[:len(a.items)])
SM=[o for o,c in b.items if c=='hkbStateMachine' and b.cstr(o+56)=='Move StateMachine'][0]
p,n=b.array(SM+208); DIR=['Front','Back','Left','Right']
for i in range(n):
    sp=b.ptr(p+i*8); nm=b.cstr(sp+96)
    if nm not in ('DashStart','Dash','DashEnd'): continue
    g=b.ptr(sp+88); vbs=b.ptr(g+16); bp,bn=b.array(vbs+16)
    print("\n[%d] %-9s -> %s '%s'  bind %s<-%s (var %d)"%(b.s32(sp+104),nm,cls.get(g),b.cstr(g+56),
        b.cstr(bp),V[b.s32(bp+28)],b.s32(bp+28)))
    gp,gn=b.array(g+136)
    for j in range(gn):
        ch=b.ptr(gp+j*8); cp,cn=b.array(ch+136); k0=b.ptr(cp)
        print("   %-6s %-32s animId=%-5d kids=%-3d clip0 anim=%s speed=%.6f mode=%d"%(
            DIR[j],b.cstr(ch+56),b.s32(ch+156),cn,b.cstr(k0+144),b.f32(k0+176),b.u8(k0+190)))
