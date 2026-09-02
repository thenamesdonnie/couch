import sys, collections
from pf import Packfile
A=Packfile('/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx')
for path in sys.argv[1:]:
    b=Packfile(path); cls=dict(b.items)
    def nm(o):
        try: return b.cstr(o+56) or ''
        except Exception: return ''
    print("\n########## %s"%path.split('/')[-1])
    ca=collections.Counter(v for _,v in A.items); cb=collections.Counter(v for _,v in b.items)
    print("reuse_padding stock=%d new=%d | objects %d->%d | delta %s"%(A.d[18],b.d[18],len(A.items),len(b.items),
        {k:cb[k]-ca[k] for k in set(ca)|set(cb) if cb[k]!=ca[k]}))
    print("stock objects unmoved+same class:", A.items==b.items[:len(A.items)])
    nc=tot=0
    for o,c in b.items:
        if c=='hkbStateMachineTransitionInfoArray':
            p,n=b.array(o+16)
            for i in range(n):
                tot+=1
                if b.ptr(p+i*72+40): nc+=1
    print("transitions %d conditions %d"%(tot,nc))
    sd=[o for o,c in b.items if c=='hkbBehaviorGraphStringData'][0]
    def sa(pf,o):
        p,n=pf.array(o); return [pf.cstr(p+i*8) for i in range(n)] if p else []
    V=sa(b,sd+48)
    DIR=['Front','Back','Left','Right']
    for smname in ('Move StateMachine','Move StateMachine_mirror'):
        sm=[o for o,c in b.items if c=='hkbStateMachine' and nm(o)==smname][0]
        p,n=b.array(sm+208)
        print("  -- %s --"%smname)
        for i in range(n):
            sp=b.ptr(p+i*8); s=b.cstr(sp+96)
            if not s.startswith(('Dash','DashStart','DashEnd')): continue
            g=b.ptr(sp+88); vbs=b.ptr(g+16); bp,bn=b.array(vbs+16)
            te=b.ptr(g+176)
            print("   %-18s -> %-42s bind %s<-%s  canChange=%s TE=%s"%(s,nm(g),b.cstr(bp),V[b.s32(bp+28)],
                bool(b.u8(g+168)), cls.get(te,'null') if te else 'null'))
            gp,gn=b.array(g+136)
            for j in range(gn):
                ch=b.ptr(gp+j*8); cp,cn=b.array(ch+136); k0=b.ptr(cp)
                print("        %-6s %-34s animId=%-5d anim=%s speed=%.6f"%(DIR[j],nm(ch),b.s32(ch+156),b.cstr(k0+144),b.f32(k0+176)))
