import sys, bisect, collections
from pf import Packfile
B=sys.argv[1] if len(sys.argv)>1 else '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash3.hkx'
pf=Packfile(B); cls=dict(pf.items); objs=sorted(cls)
def owner(off):
    i=bisect.bisect_right(objs,off)-1
    return objs[i] if i>=0 else None
def nm(o):
    try: return pf.cstr(o+56) or ''
    except Exception: return ''
def desc(o): return "%s @%#x %r"%(cls.get(o),o,nm(o))
# ground-truth edges from GLOBAL fixups only: src attributed to the object that owns it
fwd=collections.defaultdict(list); rev=collections.defaultdict(list)
for src,(sec,dst) in pf.glob.items():
    ow=owner(src)
    if ow is None or dst not in cls: continue
    fwd[ow].append((src-ow,dst)); rev[dst].append((ow,src-ow))
root=[o for o,c in pf.items if c=='hkbBehaviorGraph'][0]
print("hkbBehaviorGraph @%#x outgoing pointers:"%root)
for rel,dst in sorted(fwd[root]): print("   +%-4d -> %s"%(rel,desc(dst)))
# BFS reachability from root
seen={root:None}
q=[root]
while q:
    o=q.pop()
    for rel,dst in fwd[o]:
        if dst not in seen:
            seen[dst]=(o,rel); q.append(dst)
print("\nreachable objects from hkbBehaviorGraph: %d of %d"%(len(seen),len(cls)))
def path(o):
    out=[]
    while o is not None and seen.get(o) is not None:
        p,rel=seen[o]; out.append((rel,o)); o=p
    out.append((None,root)); return list(reversed(out))
for want in ('Move StateMachine','Move StateMachine_mirror'):
    tgt=[o for o,c in pf.items if c=='hkbStateMachine' and nm(o)==want]
    if not tgt: continue
    t=tgt[0]
    print("\n=== %s @%#x reachable: %s ==="%(want,t,t in seen))
    if t in seen:
        for rel,o in path(t): print("   %-8s %s"%(('+%d'%rel) if rel is not None else 'root',desc(o)))
# are the new selectors reachable?
print("\n=== new objects ===")
for o,c in pf.items:
    n=nm(o)
    if c=='hkbManualSelectorGenerator' and n.endswith('Direction ManualSelectorGenerator') and n.split()[0] in ('DashStart','Dash','DashEnd'):
        print("   %s reachable=%s"%(desc(o),o in seen))
        for rel,dst in sorted(fwd[o]): print("        +%-4d -> %s"%(rel,desc(dst)))
        print("        referenced by:",[desc(a)+" +%d"%r for a,r in rev[o]])
