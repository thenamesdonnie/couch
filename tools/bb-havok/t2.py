p='/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx'
from soulstruct.havok.core import HKX
h=HKX.from_path(p)
print("type",type(h))
print("root",type(h.root))
print("hk_version", getattr(h,'hk_version',None))
