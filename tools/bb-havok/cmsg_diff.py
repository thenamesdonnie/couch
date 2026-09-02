import collections
from pf import Packfile
pf=Packfile('/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx')
cls=dict(pf.items)
def nm(o):
    try: return pf.cstr(o+56) or ''
    except Exception: return ''
def find(n):
    return [o for o,c in pf.items if c=='CustomManualSelectorGenerator' and nm(o)==n][0]
F=[('variableBindingSet',16,'P'),('userData',48,'U64'),('generators.count',144,'U32'),
   ('offsetType',152,'I32'),('animId',156,'I32'),('animeEndEventType',160,'I32'),
   ('enableScript',164,'U8'),('enableTae',165,'U8'),('changeTypeOfSelectedIndexAfterActivate',166,'U8'),
   ('generatorChangedTransitionEffect',168,'P'),('checkAnimEndSlotNo',176,'I32'),('replanningAI',180,'U8')]
import struct
def get(o,off,k):
    if k=='P': return pf.ptr(o+off)
    if k=='U64': return struct.unpack_from('<Q',pf.data,o+off)[0]
    if k=='U32': return pf.u32(o+off)
    if k=='I32': return pf.s32(o+off)
    if k=='U8': return pf.u8(o+off)
def row(o): return {k:get(o,off,t) for k,off,t in F}
NAMES=['DashStart CustomManualSelectorGenerator','Dash CustomManualSelectorGenerator','DashEnd CustomManualSelectorGenerator',
       'RunLeft Normal Light','RunBack Normal Light','RunRight Normal Light',
       'RunEnd Left CustomManualSelectorGenerator','RunEnd Back CustomManualSelectorGenerator','RunEnd Right CustomManualSelectorGenerator']
R={n:row(find(n)) for n in NAMES}
print("%-42s %s"%("field"," ".join("%-12s"%n.split()[0][:12] for n in NAMES)))
for k,_,_ in F:
    print("%-42s %s"%(k," ".join("%-12s"%(hex(R[n][k]) if k in('variableBindingSet','generatorChangedTransitionEffect') and R[n][k] else R[n][k]) for n in NAMES)))
print("\n--- differences DashStart-forward vs RunLeft strafe ---")
for k,_,_ in F:
    a=R['DashStart CustomManualSelectorGenerator'][k]; b=R['RunLeft Normal Light'][k]
    if a!=b: print("   %-42s dash=%-10s strafe=%s"%(k,a,b))
print("--- differences Dash-forward vs RunLeft strafe ---")
for k,_,_ in F:
    a=R['Dash CustomManualSelectorGenerator'][k]; b=R['RunLeft Normal Light'][k]
    if a!=b: print("   %-42s dash=%-10s strafe=%s"%(k,a,b))
print("--- differences DashEnd-forward vs RunEnd Left strafe ---")
for k,_,_ in F:
    a=R['DashEnd CustomManualSelectorGenerator'][k]; b=R['RunEnd Left CustomManualSelectorGenerator'][k]
    if a!=b: print("   %-42s dash=%-10s strafe=%s"%(k,a,b))
# raw byte diff of the whole 256-byte object, non-pointer, non-name
print("\n--- raw byte-range differences (DashStart fwd vs RunLeft), excluding ptr slots 16,56,136,168 ---")
A=pf.data[find('DashStart CustomManualSelectorGenerator'):find('DashStart CustomManualSelectorGenerator')+256]
B=pf.data[find('RunLeft Normal Light'):find('RunLeft Normal Light')+256]
skip=set()
for s in (16,56,136,168): skip.update(range(s,s+8))
skip.update(range(144,152))
runs=[i for i in range(256) if A[i]!=B[i] and i not in skip]
print("   differing byte offsets:",runs)
# global name uniqueness
allnames=collections.Counter()
for o,c in pf.items:
    n=nm(o)
    if n: allnames[n]+=1
print("\nnamed objects %d, duplicates across ALL classes: %d %s"%(sum(allnames.values()),
      sum(1 for v in allnames.values() if v>1),[k for k,v in allnames.items() if v>1][:5]))
