"""Minimal Bloodborne TAE reader: animation id -> list of (event_type, start, end).
Layout taken from soulstruct.base.animations.tae.core (its own reader is broken by a
constrata version mismatch, so this hand-rolls the same structs)."""
import struct, sys

class TAEFile:
    def __init__(self, data):
        d = self.d = data
        assert d[:4] == b'TAE ', d[:4]
        self.tae_id, self.count = struct.unpack_from('<ii', d, 0x50)
        self.anims_off = struct.unpack_from('<q', d, 0x58)[0]
        self.index = {}
        for i in range(self.count):
            aid, off = struct.unpack_from('<qq', d, self.anims_off + i*16)
            self.index[aid] = off
    def events(self, aid):
        d = self.d
        off = self.index[aid]
        ev_hdr, ev_grp, ev_times, anim_file = struct.unpack_from('<qqqq', d, off)
        n_ev, n_grp, n_times, _z = struct.unpack_from('<iiii', d, off+32)
        out = []
        for i in range(n_ev):
            s_off, e_off, data_off = struct.unpack_from('<qqq', d, ev_hdr + i*24)
            start = struct.unpack_from('<f', d, s_off)[0]
            end   = struct.unpack_from('<f', d, e_off)[0]
            etype = struct.unpack_from('<q', d, data_off)[0]
            payload = d[data_off+16:data_off+16+32]
            out.append((etype, start, end, payload))
        return out

TYPES = {}
try:
    import re
    src = open('/home/ds2000/couch/data/ds3-ui-port/.venv/lib/python3.12/site-packages/'
               'soulstruct/base/animations/tae/enums.py').read()
    for m in re.finditer(r'^\s{4}(\w+)\s*=\s*(\d+)', src, re.M):
        TYPES[int(m.group(2))] = m.group(1)
except Exception:
    pass

if __name__ == '__main__':
    t = TAEFile(open(sys.argv[1],'rb').read())
    print("tae_id=%d animations=%d" % (t.tae_id, t.count))
    for aid in [int(x) for x in sys.argv[2:]]:
        if aid not in t.index:
            print("\nanim %d: NOT IN THIS TAE" % aid); continue
        ev = t.events(aid)
        print("\nanim %d: %d events" % (aid, len(ev)))
        for etype, s, e, pay in ev:
            print("   type %-5d %-28s %6.3f -> %6.3f  data %s" % (
                etype, TYPES.get(etype,'?'), s, e, pay[:16].hex()))
