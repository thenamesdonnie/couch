import sys, collections
from pf import Packfile
B=sys.argv[1] if len(sys.argv)>1 else '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash3.hkx'
pf=Packfile(B); cls=dict(pf.items)
objs=sorted(cls)
def owner(off):
    import bisect
    i=bisect.bisect_right(objs,off)-1
    return objs[i] if i>=0 else None
def nm(o):
    try: return pf.cstr(o+56) or ''
    except Exception: return ''
def desc(o): return "%s @%#x %r"%(cls.get(o),o,nm(o))
CHILD={'hkbManualSelectorGenerator':[('generators',136,'ARRPTR')],
       'CustomManualSelectorGenerator':[('generators',136,'ARRPTR')],
       'hkbBlenderGenerator':[('children',160,'ARRCHILD')],
       'hkbModifierGenerator':[('generator',144,'PTR')],
       'hkbBehaviorGraph':[('rootGenerator',192,'PTR')],
       'hkbStateMachine':[('states',208,'ARRSTATE')]}
def kids(o):
    out=[]
    for label,off,kind in CHILD.get(cls.get(o),[]):
        if kind=='PTR':
            v=pf.ptr(o+off)
            if v: out.append((label,v))
        elif kind=='ARRPTR':
            p,n=pf.array(o+off)
            for i in range(n):
                v=pf.ptr(p+i*8)
                if v: out.append(('%s[%d]'%(label,i),v))
        elif kind=='ARRCHILD':
            p,n=pf.array(o+off)
            for i in range(n):
                ch=pf.ptr(p+i*8)
                if ch:
                    v=pf.ptr(ch+48)
                    if v: out.append(('child[%d] w=%.2f'%(i,pf.f32(ch+64)),v))
        elif kind=='ARRSTATE':
            p,n=pf.array(o+off)
            for i in range(n):
                sp=pf.ptr(p+i*8)
                if sp:
                    v=pf.ptr(sp+88)
                    if v: out.append(("state %d %r (info @%#x)"%(pf.s32(sp+104),pf.cstr(sp+96),sp),v))
    return out
root=[o for o,c in pf.items if c=='hkbBehaviorGraph'][0]
rg=pf.ptr(root+192)
print("hkbBehaviorGraph @%#x  rootGenerator -> %s"%(root,desc(rg)))
TARGETS={}
for o,c in pf.items:
    if c=='hkbStateMachine' and nm(o) in ('Move StateMachine','Move StateMachine_mirror'):
        TARGETS[nm(o)]=o
def find_path(goal):
    seen=set(); stack=[(rg,[('rootGenerator',rg)])]
    while stack:
        o,tr=stack.pop()
        if o==goal: return tr
        if o in seen: continue
        seen.add(o)
        for k,v in kids(o): stack.append((v,tr+[(k,v)]))
    return None
for label,goal in TARGETS.items():
    p=find_path(goal)
    print("\n=== path rootGenerator -> %s ==="%label)
    if not p: print("   NOT REACHABLE"); continue
    for i,(k,v) in enumerate(p): print("   %2d %-46s %s"%(i,k,desc(v)))
