import struct, collections
from pf import Packfile
B='/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash3.hkx'
pf=Packfile(B); cls=dict(pf.items)
# 1. duplicate global fixups?
d=pf.d; dabs=pf.dabs
srcs=[]
o=dabs+pf.dglob
while o+12<=dabs+pf.dvirt:
    s,sec,t=struct.unpack_from('<III',d,o)
    if s==0xffffffff: break
    srcs.append((s,sec,t)); o+=12
c=collections.Counter(s for s,_,_ in srcs)
dup=[s for s,n in c.items() if n>1]
print("global fixup entries:",len(srcs),"duplicate srcs:",len(dup))
for s in dup[:10]:
    print("   dup src %#x ->"%s,[hex(t) for ss,_,t in srcs if ss==s])
lc=collections.Counter()
o=dabs+pf.dloc
while o+8<=dabs+pf.dglob:
    s,t=struct.unpack_from('<II',d,o)
    if s==0xffffffff: break
    lc[s]+=1; o+=8
print("duplicate local srcs:",[hex(s) for s,n in lc.items() if n>1][:10])
# 2. chain from behaviour root
root=[o for o,cc in pf.items if cc=='hkbBehaviorGraph'][0]
print("\nhkbBehaviorGraph @%#x rootGenerator=%s"%(root,hex(pf.ptr(root+80)) if pf.ptr(root+80) else None))
def name(o): 
    try: return pf.cstr(o+56) or ''
    except Exception: return ''
def kids(o):
    c=cls.get(o)
    out=[]
    if c in ('hkbManualSelectorGenerator','CustomManualSelectorGenerator'):
        p,n=pf.array(o+136)
        out=[('gen[%d]'%i,pf.ptr(p+i*8)) for i in range(n)]
    elif c=='hkbBlenderGenerator':
        p,n=pf.array(o+160)
        for i in range(n):
            ch=pf.ptr(p+i*8)
            if ch: out.append(('child[%d]'%i,pf.ptr(ch+48)))
    elif c=='hkbModifierGenerator':
        out=[('modifier',pf.ptr(o+136)),('generator',pf.ptr(o+144))]
    elif c=='hkbStateMachine':
        p,n=pf.array(o+208)
        for i in range(n):
            sp=pf.ptr(p+i*8)
            if sp: out.append(('state %d %r'%(pf.s32(sp+104),pf.cstr(sp+96)),pf.ptr(sp+88)))
    elif c=='hkbModifierList':
        p,n=pf.array(o+136)
        out=[('mod[%d]'%i,pf.ptr(p+i*8)) for i in range(n)]
    return [(k,v) for k,v in out if v]
# find path root -> the Dash state generator
target=None
SM=[o for o,cc in pf.items if cc=='hkbStateMachine' and name(o)=='Move StateMachine'][0]
import sys
sys.setrecursionlimit(10000)
path=None
seen=set()
def dfs(o,trail):
    global path
    if path or o in seen: return
    seen.add(o)
    if o==SM:
        path=trail+[('','%s @%#x %r'%(cls.get(o),o,name(o)))]; return
    for k,v in kids(o):
        dfs(v,trail+[(k,'%s @%#x %r'%(cls.get(o),o,name(o)))])
dfs(pf.ptr(root+80),[])
print("\n--- path from rootGenerator to 'Move StateMachine' ---")
if path:
    for k,desc in path: print("   %-28s %s"%(k,desc))
else:
    print("   NOT REACHABLE from rootGenerator")
