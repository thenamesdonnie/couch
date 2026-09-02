from pf import Packfile
import collections
A='/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx'
B='/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash2.hkx'
a=Packfile(A); b=Packfile(B); cls=dict(b.items)
sd=[o for o,c in b.items if c=='hkbBehaviorGraphStringData'][0]
def sa(o):
    p,n=b.array(o); return [b.cstr(p+i*8) for i in range(n)] if p else []
V=sa(sd+48); E=sa(sd+16)
ca=collections.Counter(v for _,v in a.items); cb=collections.Counter(v for _,v in b.items)
print("objects %d -> %d  (delta %+d)"%(len(a.items),len(b.items),len(b.items)-len(a.items)))
print("class delta:", {k:cb[k]-ca[k] for k in set(ca)|set(cb) if cb[k]!=ca[k]})
# conditions
nc=0; tot=0
for o,c in b.items:
    if c=='hkbStateMachineTransitionInfoArray':
        p,n=b.array(o+16)
        for i in range(n):
            tot+=1
            if b.ptr(p+i*72+40): nc+=1
print("transitions %d, non-null conditions: %d"%(tot,nc))
# string tables untouched
sda=[o for o,c in a.items if c=='hkbBehaviorGraphStringData'][0]
def saa(o):
    p,n=a.array(o); return [a.cstr(p+i*8) for i in range(n)] if p else []
print("event+variable tables identical:", (saa(sda+16),saa(sda+48))==(E,V))
# the three states
SM=[o for o,c in b.items if c=='hkbStateMachine' and b.cstr(o+56)=='Move StateMachine'][0]
p,n=b.array(SM+208); DIR=['Front','Back','Left','Right']
for i in range(n):
    sp=b.ptr(p+i*8); nm=b.cstr(sp+96)
    if nm not in ('DashStart','Dash','DashEnd'): continue
    g=b.ptr(sp+88); vbs=b.ptr(g+16)
    bp,bn=b.array(vbs+16)
    print("\n[%d] %-9s -> %s '%s'  bind %s<-%s"%(b.s32(sp+104),nm,cls.get(g),b.cstr(g+56),
        b.cstr(bp),V[b.s32(bp+28)]))
    gp,gn=b.array(g+136)
    for j in range(gn):
        ch=b.ptr(gp+j*8)
        cp,cn=b.array(ch+136)
        k0=b.ptr(cp)
        print("   %-6s %-30s animId=%-5d children=%-3d clip0='%s' anim=%s speed=%.4f mode=%d"%(
            DIR[j],b.cstr(ch+56),b.s32(ch+156),cn,b.cstr(k0+56),b.cstr(k0+144),
            b.f32(k0+176), b.u8(k0+190)))
