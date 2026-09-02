"""In-place byte-exact editor for the Bloodborne c0000 behaviour packfile.

Every edit here changes bytes WITHOUT moving anything, so all section headers,
local/global/virtual fixup tables and item offsets stay valid. That is the only
safe way to edit this file without a full repacker.
"""
import struct, shutil, sys
from pf import Packfile

SRC = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx'

class Patcher:
    def __init__(self, src=SRC):
        self.pf = Packfile(src)
        self.buf = bytearray(open(src,'rb').read())
        self.dabs = self.pf.dabs
        self.log = []
    def set_str_inplace(self, ptr_off, new):
        """Overwrite the C string a hkStringPtr points at. Same length only."""
        p = self.pf.ptr(ptr_off)
        assert p is not None, "null string pointer"
        e = self.pf.data.index(b'\0', p)
        old = self.pf.data[p:e].decode()
        assert len(new) == len(old), "length %d != %d (%s -> %s)" % (len(old),len(new),old,new)
        self.buf[self.dabs+p:self.dabs+p+len(new)] = new.encode()
        self.log.append("str @%#x %s -> %s" % (p, old, new))
    def set_s16(self, off, v):
        old = struct.unpack_from('<h', self.buf, self.dabs+off)[0]
        struct.pack_into('<h', self.buf, self.dabs+off, v)
        self.log.append("s16 @%#x %d -> %d" % (off, old, v))
    def set_s32(self, off, v):
        old = struct.unpack_from('<i', self.buf, self.dabs+off)[0]
        struct.pack_into('<i', self.buf, self.dabs+off, v)
        self.log.append("s32 @%#x %d -> %d" % (off, old, v))
    def set_u16(self, off, v):
        old = struct.unpack_from('<H', self.buf, self.dabs+off)[0]
        struct.pack_into('<H', self.buf, self.dabs+off, v)
        self.log.append("u16 @%#x %#x -> %#x" % (off, old, v))
    def write(self, path):
        open(path,'wb').write(bytes(self.buf))
        return path

if __name__ == '__main__':
    import hashlib
    # ---- round trip 1: no-op rewrite must be byte identical ----
    p = Patcher()
    out = '/tmp/claude-1000/-home-ds2000-couch/23224b64-814e-4ad4-bb3b-10cf9675c5f8/scratchpad/noop.hkx'
    p.write(out)
    a = open(SRC,'rb').read(); b = open(out,'rb').read()
    print("no-op rewrite byte identical:", a==b, len(a), len(b))
    # ---- round trip 2: reparse a patched file ----
    p2 = Patcher()
    # demo edit: retarget one Dash clip, same string length
    dash = 0x19cfe0
    arr,_n = p2.pf.array(dash+136)
    g = p2.pf.ptr(arr+11*8)          # index 11 (a029 set)
    p2.set_str_inplace(g+144, 'a029_004002')
    out2 = '/tmp/claude-1000/-home-ds2000-couch/23224b64-814e-4ad4-bb3b-10cf9675c5f8/scratchpad/demo.hkx'
    p2.write(out2)
    for l in p2.log: print("  ", l)
    q = Packfile(out2)
    print("patched file reparses: items", len(q.items), "== orig", len(p2.pf.items))
    print("size unchanged:", len(open(out2,'rb').read()) == len(a))
    c2 = open(out2,"rb").read()
    d = sum(1 for x,y in zip(a,c2) if x!=y)
    print("differing bytes:", d)
