"""Append-style in-place editor for Havok 2014 PS4 packfiles.

The stock bytes of the __data__ region and of all three fixup tables are kept
verbatim. New objects, arrays and strings are appended past the end of the data
region, new fixup entries are appended to the tables, and only the __data__
section header's region offsets are rewritten. Nothing that already exists moves,
so `reuse_base_class_padding` and every one of the 12,970 stock objects keep
their exact shipped layout.

A build with no additions reproduces the input file byte for byte.
"""
import struct

SEC_HDR = 0x40
SEC_STRIDE = 0x40
DATA_SEC_INDEX = 2
CLASSNAMES_SEC_INDEX = 0


def pad_to_16(n):
    """Havok pads each fixup region up to 16 with 0xff, and never leaves none."""
    r = 16 - (n % 16)
    return 16 if r == 0 else r


class Appender:
    def __init__(self, path):
        self.raw = raw = open(path, 'rb').read()
        self.nsec = struct.unpack_from('<i', raw, 0x14)[0]
        self.sec = []
        for i in range(self.nsec):
            o = SEC_HDR + i * SEC_STRIDE
            name = raw[o:o+19].rstrip(b'\0').decode()
            vals = list(struct.unpack_from('<7I', raw, o + 20))
            self.sec.append([name, vals, o])
        (self.cn_abs, self.cn_loc) = self.sec[CLASSNAMES_SEC_INDEX][1][0:2]
        d_abs, d_loc, d_glob, d_virt, d_exp, d_imp, d_end = self.sec[DATA_SEC_INDEX][1]
        self.dabs = d_abs

        # class name -> offset within __classnames__ (what a virtual fixup stores)
        sec = raw[self.cn_abs:self.cn_abs + self.cn_loc]
        self.classnames = {}
        i = 0
        while i < len(sec) - 5:
            if sec[i:i+4] == b'\xff\xff\xff\xff':
                break
            j = sec.index(b'\0', i + 5)
            self.classnames[sec[i+5:j].decode()] = i + 5
            i = j + 1

        # regions, entries only, padding dropped and regenerated on build
        self.data = bytearray(raw[d_abs:d_abs + d_loc])
        self.local = bytearray(self._entries(raw, d_abs + d_loc, d_abs + d_glob, 8))
        self.glob  = bytearray(self._entries(raw, d_abs + d_glob, d_abs + d_virt, 12))
        self.virt  = bytearray(self._entries(raw, d_abs + d_virt, d_abs + d_exp, 12))
        self.n_local = len(self.local) // 8
        self.n_glob = len(self.glob) // 12
        self.n_virt = len(self.virt) // 12

    @staticmethod
    def _entries(raw, start, end, stride):
        out = bytearray()
        o = start
        while o + stride <= end:
            if struct.unpack_from('<I', raw, o)[0] == 0xffffffff:
                break
            out += raw[o:o+stride]
            o += stride
        return out

    # ---------- allocation ----------
    def _align(self, n=16):
        while len(self.data) % n:
            self.data.append(0)

    def alloc(self, nbytes, align=16):
        self._align(align)
        off = len(self.data)
        self.data += bytearray(nbytes)
        return off

    def add_string(self, s):
        off = self.alloc(len(s) + 1, align=1)
        self.data[off:off+len(s)] = s.encode('ascii')
        return off

    def add_object(self, class_name, size, src_bytes=None):
        assert class_name in self.classnames, "class %s not in __classnames__" % class_name
        off = self.alloc(size)
        if src_bytes is not None:
            assert len(src_bytes) == size
            self.data[off:off+size] = src_bytes
        self.virt += struct.pack('<III', off, CLASSNAMES_SEC_INDEX, self.classnames[class_name])
        self.n_virt += 1
        return off

    # ---------- fixups ----------
    def add_local(self, src, dst):
        self.local += struct.pack('<II', src, dst)
        self.n_local += 1

    def add_global(self, src, dst):
        self.glob += struct.pack('<III', src, DATA_SEC_INDEX, dst)
        self.n_glob += 1

    def find_global(self, src):
        for i in range(self.n_glob):
            if struct.unpack_from('<I', self.glob, i*12)[0] == src:
                return i
        return None

    def retarget_global(self, src, new_dst):
        i = self.find_global(src)
        assert i is not None, "no global fixup at src %#x" % src
        old = struct.unpack_from('<I', self.glob, i*12 + 8)[0]
        struct.pack_into('<I', self.glob, i*12 + 8, new_dst)
        return old

    def clear_local(self, src):
        """Drop a local fixup (used when a copied pointer slot is re-pointed)."""
        for i in range(self.n_local):
            if struct.unpack_from('<I', self.local, i*8)[0] == src:
                del self.local[i*8:(i+1)*8]
                self.n_local -= 1
                return True
        return False

    # ---------- helpers ----------
    def set_array(self, obj_off, member_off, elem_size, count):
        """Allocate array storage, wire the hkArray header, return the data offset."""
        arr = self.alloc(elem_size * count) if count else 0
        if count:
            self.add_local(obj_off + member_off, arr)
        struct.pack_into('<II', self.data, obj_off + member_off + 8, count, count | 0x80000000)
        return arr

    def u8(self, o, v):  struct.pack_into('<B', self.data, o, v)
    def s16(self, o, v): struct.pack_into('<h', self.data, o, v)
    def s32(self, o, v): struct.pack_into('<i', self.data, o, v)
    def f32(self, o, v): struct.pack_into('<f', self.data, o, v)

    # ---------- output ----------
    def build(self):
        self._align(16)
        data = bytes(self.data)
        loc = bytes(self.local) + b'\xff' * pad_to_16(len(self.local))
        glo = bytes(self.glob)  + b'\xff' * pad_to_16(len(self.glob))
        vir = bytes(self.virt)  + b'\xff' * pad_to_16(len(self.virt))
        d_loc = len(data)
        d_glob = d_loc + len(loc)
        d_virt = d_glob + len(glo)
        d_end = d_virt + len(vir)
        out = bytearray(self.raw[:self.dabs])
        o = self.sec[DATA_SEC_INDEX][2]
        struct.pack_into('<7I', out, o + 20, self.dabs, d_loc, d_glob, d_virt, d_end, d_end, d_end)
        out += data + loc + glo + vir
        return bytes(out)


if __name__ == '__main__':
    import sys, hashlib
    src = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx'
    a = Appender(src)
    print("sections:", [(n, [hex(x) for x in v]) for n, v, _ in a.sec])
    print("entries: local %d global %d virtual %d" % (a.n_local, a.n_glob, a.n_virt))
    print("classes in table:", len(a.classnames))
    out = a.build()
    orig = open(src, 'rb').read()
    print("no-op build size %d vs %d" % (len(out), len(orig)))
    print("NO-OP BUILD BYTE IDENTICAL:", out == orig)
    if out != orig:
        for i in range(min(len(out), len(orig))):
            if out[i] != orig[i]:
                print("first diff at %#x" % i); break
