from pf import Packfile
pf = Packfile('/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx')
sd = [o for o,c in pf.items if c=='hkbBehaviorGraphStringData'][0]
def strarray(o):
    p,n = pf.array(o)
    if p is None: return []
    return [pf.cstr(p+i*8) for i in range(n)]
ev = strarray(sd+16); at = strarray(sd+32); va = strarray(sd+48); cp = strarray(sd+64)
print("events %d attrs %d vars %d charprops %d" % (len(ev),len(at),len(va),len(cp)))
import io
with open('/home/ds2000/couch/data/bb-hks/anibnd/graph_events.txt','w') as f:
    for i,s in enumerate(ev): f.write("%d\t%s\n"%(i,s))
with open('/home/ds2000/couch/data/bb-hks/anibnd/graph_variables.txt','w') as f:
    for i,s in enumerate(va): f.write("%d\t%s\n"%(i,s))
print("--- variables ---")
for i,s in enumerate(va): print(i,s)
