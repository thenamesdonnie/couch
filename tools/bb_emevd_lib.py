import struct, zlib, sys

LIVE = '/home/ds2000/games/ps4/CUSA00900/dvdroot_ps4/event/common.emevd.dcx'

def dcx_decompress(path):
    d = open(path,'rb').read()
    assert d[:4] == b'DCX\0'
    dcsOffset, dcpOffset = struct.unpack_from('>II', d, 8)
    uncompressedSize, compressedSize = struct.unpack_from('>II', d, dcsOffset+4)
    i = d.find(b'DCA\0', dcpOffset)
    start = i + struct.unpack_from('>I', d, i+4)[0]
    raw = zlib.decompress(d[start:start+compressedSize])
    assert len(raw) == uncompressedSize
    return raw, d, dict(start=start, dcsOffset=dcsOffset, compressedSize=compressedSize)

class Emevd:
    def __init__(self, raw):
        self.raw = bytearray(raw); assert raw[:4] == b'EVD\0'
        (self.eventCount, self.eventOffset, self.instrCount, self.instrOffset,
         _u0, _u1, self.layerCount, self.layerOffset,
         self.paramCount, self.paramOffset, self.linkCount, self.linkOffset,
         self.argsLength, self.argsOffset, self.strLength,
         self.strOffset) = struct.unpack_from('<16q', raw, 0x10)
    def events(self):
        for i in range(self.eventCount):
            o = self.eventOffset + i*48
            eid, ic, io, pc, po = struct.unpack_from('<5q', self.raw, o)
            yield eid, ic, io
    def instructions(self, ic, io):
        for j in range(ic):
            o = self.instrOffset + io + j*32
            bank, iid, alen, aoff, loff = struct.unpack_from('<iiqqq', self.raw, o)
            yield bank, iid, alen, self.argsOffset + aoff

def find(raw, flag):
    e = Emevd(raw); hits = []
    for eid, ic, io in e.events():
        for bank, iid, alen, ao in e.instructions(ic, io):
            if (bank, iid) == (2003, 2) and alen >= 8:
                f, v = struct.unpack_from('<ii', e.raw, ao)
                if f == flag:
                    hits.append((eid, ao, f, v))
    # every other mention of the flag anywhere in the payload
    total = raw.count(struct.pack('<i', flag))
    return hits, total, e

if __name__ == '__main__':
    flag = int(sys.argv[1])
    raw, _, _ = dcx_decompress(LIVE)
    hits, total, e = find(raw, flag)
    print(f"flag {flag}: {total} raw occurrence(s) in the payload")
    print(f"SetEventFlag [2003:2] writes of it: {len(hits)}")
    for eid, ao, f, v in hits:
        print(f"   event {eid}  argsOffset {ao}  -> SetEventFlag({f}, {v})")
