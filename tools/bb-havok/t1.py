import sys
p='/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx'
import soulstruct_havok
print(soulstruct_havok.__file__)
from soulstruct_havok.core import HKX
h=HKX.from_path(p)
print(type(h))
print(h.hk_version if hasattr(h,'hk_version') else '')
print(h.root)
