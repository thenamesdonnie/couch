from pf import Packfile
import collections, sys
pf = Packfile('/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx')
cls = sys.argv[1]
offs = sorted(o for o,c in pf.items if c==cls)
# item size: distance to next item start
allo = sorted(o for o,_ in pf.items)
idx = {o:i for i,o in enumerate(allo)}
sizes = collections.Counter()
for o in offs:
    i = idx[o]
    if i+1 < len(allo): sizes[allo[i+1]-o]+=1
print(cls, "count", len(offs), "size hist", sizes.most_common(6))
# fixup offsets relative to item start
loc = collections.Counter(); glo = collections.Counter()
sz = sizes.most_common(1)[0][0]
for o in offs[:400]:
    for r in range(0, sz, 8):
        if o+r in pf.local: loc[r]+=1
        if o+r in pf.glob:  glo[r]+=1
print("local-ptr member offsets:", sorted(loc.items()))
print("global-ptr member offsets:", sorted(glo.items()))
