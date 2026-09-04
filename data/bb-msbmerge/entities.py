"""Every entity ID either mod's scripts can address must survive the merge."""
import sys, os, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mergemsb import load
from msbb import SUPERTYPES, PARTS, POINT, EVENT
V='/home/ds2000/couch/data/bb-mod-backups-copy/BloodborneEnhanced-0.11.2-fix9/files/map/mapstudio'
E='/home/ds2000/games/ps4/CUSA00900/dvdroot_ps4/map/mapstudio'
R,M=sys.argv[1],sys.argv[2]
SLOT={PARTS:'ent:0x00', POINT:'ent:0x00', EVENT:'ent:0x08'}
def eids(m):
    s=set()
    for st,k in SLOT.items():
        for e in m.lists[st]:
            b=e.fields.get(k)
            if b is None: continue
            v=int.from_bytes(b,'little',signed=True)
            if v>0: s.add((st,v))
    return s
bad=0; tot=0
for p in sorted(glob.glob(M+'/*.msb.dcx')):
    n=os.path.basename(p)[:-8]
    e=eids(load(f'{E}/{n}.msb.dcx')[0]); r=eids(load(f'{R}/{n}.msb.dcx')[0]); m=eids(load(p)[0])
    tot+=len(e|r)
    for miss,src in ((e-m,'ENHANCED'),(r-m,'REBORNE')):
        if miss:
            print(f'{n}: {len(miss)} entity IDs from {src} missing in merged: {sorted(miss)[:6]}'); bad+=len(miss)
    extra=m-(e|r)
    if extra: print(f'{n}: {len(extra)} entity IDs in merged that are in NEITHER input: {sorted(extra)[:6]}'); bad+=len(extra)
print(f'entity IDs checked: {tot}; missing/spurious: {bad}')
