from pf import Packfile
import collections
P='/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash.hkx'
pf=Packfile(P); cls=dict(pf.items)
sd=[o for o,c in pf.items if c=='hkbBehaviorGraphStringData'][0]
def sa(o):
    p,n=pf.array(o); return [pf.cstr(p+i*8) for i in range(n)] if p else []
VARS=sa(sd+48)
print("objects:",len(pf.items),"(orig 12970, +6 expected)")
SM=[o for o,c in pf.items if c=='hkbStateMachine' and pf.cstr(o+56)=='Move StateMachine'][0]
p,n=pf.array(SM+208)
DIR=['Front','Back','Left','Right']
for i in range(n):
    sp=pf.ptr(p+i*8); sid=pf.s32(sp+104); nm=pf.cstr(sp+96); g=pf.ptr(sp+88)
    line="[%d] %-9s -> %-28s '%s'"%(sid,nm,cls.get(g),pf.cstr(g+56))
    vbs=pf.ptr(g+16)
    if vbs and cls.get(vbs)=='hkbVariableBindingSet':
        bp,bn=pf.array(vbs+16)
        line+="  bind:"+",".join("%s<-%s"%(pf.cstr(bp+k*40),VARS[pf.s32(bp+k*40+28)]) for k in range(bn))
    print(line)
    if nm in ('DashStart','Dash','DashEnd'):
        gp,gn=pf.array(g+136)
        for j in range(gn):
            ch=pf.ptr(gp+j*8)
            print("      %-6s -> %-30s '%s'  animId=%s"%(DIR[j],cls.get(ch),pf.cstr(ch+56),
                  pf.s32(ch+156) if cls.get(ch)=='CustomManualSelectorGenerator' else '-'))
