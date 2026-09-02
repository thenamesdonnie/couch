from graph import *
sms=[o for o,c in pf.items if c=='hkbStateMachine']
def sm_info(o):
    name=pf.cstr(o+56)
    p,n=pf.array(o+208)
    states=[]
    for i in range(n):
        sp=pf.ptr(p+i*8)
        if sp is None: continue
        states.append((pf.s32(sp+104), pf.cstr(sp+96), sp))
    wc=pf.ptr(o+224)
    return name,states,wc,pf.s32(o+168)
for o in sms:
    name,states,wc,start=sm_info(o)
    print("SM @%#x  %-40s states=%d start=%d wildcards=%s" % (o,name,len(states),start,"yes" if wc else "no"))
