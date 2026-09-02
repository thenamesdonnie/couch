"""Byte-exact BND4 reader/writer for c0000.anibnd (FromSoft PS4 layout).

Entry data is laid out back to back, each entry starting on a 16-byte boundary
after the (unaligned) end of the UTF-16 name table. soulstruct starts the first
entry at the header's data_offset field without aligning it, which shifts every
subsequent entry by 12 bytes and changes the file's padding.
"""
import struct

ENTRY_STRIDE = 0x24
HEADER_SIZE = 0x40


class BND4:
    def __init__(self, payload):
        self.raw = payload
        self.header = bytearray(payload[:HEADER_SIZE])
        n = struct.unpack_from('<i', payload, 0x0c)[0]
        assert payload[:4] == b'BND4'
        assert struct.unpack_from('<q', payload, 0x20)[0] == ENTRY_STRIDE
        self.entries = []
        for i in range(n):
            b = HEADER_SIZE + i * ENTRY_STRIDE
            flags, unk, csz, usz, doff, eid, noff = struct.unpack_from('<IiqqIII', payload, b)
            e = payload[noff:]
            k = 0
            while e[k:k+2] != b'\0\0':
                k += 2
            self.entries.append(dict(flags=flags, unk=unk, usz=usz, eid=eid,
                                     name=e[:k].decode('utf-16-le'),
                                     data=payload[doff:doff + csz]))

    def build(self):
        n = len(self.entries)
        names_start = HEADER_SIZE + n * ENTRY_STRIDE
        name_blob = bytearray()
        name_offsets = []
        for e in self.entries:
            name_offsets.append(names_start + len(name_blob))
            name_blob += e['name'].encode('utf-16-le') + b'\0\0'
        names_end = names_start + len(name_blob)

        out = bytearray(self.header)
        struct.pack_into('<q', out, 0x28, names_end)      # header data_offset = name table end
        out += bytearray(n * ENTRY_STRIDE)
        out += name_blob
        while len(out) % 16:
            out.append(0)
        for i, e in enumerate(self.entries):
            while len(out) % 16:
                out.append(0)
            doff = len(out)
            out += e['data']
            struct.pack_into('<IiqqIII', out, HEADER_SIZE + i * ENTRY_STRIDE,
                             e['flags'], e['unk'], len(e['data']), e['usz'],
                             doff, e['eid'], name_offsets[i])
        return bytes(out)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, '/home/ds2000/couch/tools/souls-extract')
    from soulstruct.dcx import decompress
    payload, dt = decompress(open('/home/ds2000/games/ps4/CUSA00900/dvdroot_ps4/chr/c0000.anibnd.dcx', 'rb').read())
    b = BND4(payload)
    out = b.build()
    print("entries", len(b.entries), "dcx type", dt)
    print("payload %d -> rebuilt %d" % (len(payload), len(out)))
    print("NO-OP BND PAYLOAD BYTE IDENTICAL:", out == payload)
    if out != payload:
        for i in range(min(len(out), len(payload))):
            if out[i] != payload[i]:
                print("first diff at %#x" % i); break
