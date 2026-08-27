"""Set durability/durabilityMax = 9999 on every EquipParamWeapon row, in place.
Same-length edit: no BND4 re-layout. Dry-run by default; --apply writes."""
import re, struct, sys, zlib

MOD_DEFS = '/tmp/claude-1000/-home-ds2000-couch/a8218b1e-8a68-4ed2-8494-332b744ac1cd/scratchpad/bbe/bb_enhanced_0.11.2-fix9/_data/Defs/EquipParamWeapon.xml'
TARGET = '/home/ds2000/games/ps4/CUSA00900/dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx'

SIZES = {'u8':1,'s8':1,'dummy8':1,'u16':2,'s16':2,'u32':4,'s32':4,'f32':4,'b32':4,'f64':8}

def field_offsets(xml_path):
    """Walk Field defs in order, tracking byte offset incl. bitfields/arrays."""
    offs, off = {}, 0
    bit_base_type, bits_used = None, 0
    for m in re.finditer(r'<Field Def="([^"]+)"', open(xml_path).read()):
        d = m.group(1).split('=')[0].strip()          # e.g. "u16 durability"
        parts = d.split()
        typ, name = parts[0], parts[1]
        arr = 1
        am = re.search(r'\[(\d+)\]', name)
        if am: arr = int(am.group(1)); name = name[:name.index('[')]
        bm = re.search(r':(\d+)$', name)
        if bm:
            nbits = int(bm.group(1)); name = name[:name.index(':')]
            if bit_base_type != typ or bits_used + nbits > SIZES[typ]*8:
                if bit_base_type is not None: off += SIZES[bit_base_type]
                bit_base_type, bits_used = typ, 0
            offs[name] = off
            bits_used += nbits
            continue
        if bit_base_type is not None:
            off += SIZES[bit_base_type]; bit_base_type, bits_used = None, 0
        offs[name] = off
        off += SIZES[typ]*arr
    if bit_base_type is not None: off += SIZES[bit_base_type]
    return offs, off

def dcx_split(path):
    d = open(path,'rb').read()
    assert d[:4] == b'DCX\0'
    dcsOffset, dcpOffset = struct.unpack_from('>II', d, 8)
    uSize, cSize = struct.unpack_from('>II', d, dcsOffset+4)
    i = d.find(b'DCA\0', dcpOffset)
    start = i + struct.unpack_from('>I', d, i+4)[0]
    return d, dcsOffset, start, cSize, zlib.decompress(d[start:start+cSize])

offs, rowsize_guess = field_offsets(MOD_DEFS)
DUR, DURMAX = offs['durability'], offs['durabilityMax']
print(f"paramdef: durability@+{DUR} durabilityMax@+{DURMAX} rowsize~{rowsize_guess}")

container, dcsOffset, payload_start, cSize, pl = dcx_split(TARGET)
pl = bytearray(pl)
t = pl.find(b'EQUIP_PARAM_WEAPON_ST')
assert t > 0x0C, "param type not found"
base = t - 0x0C                                    # param header start
rowCount = struct.unpack_from('<H', pl, base+0x0A)[0]
print(f"EQUIP_PARAM_WEAPON_ST at 0x{base:x}, rowCount={rowCount}")

# Row table starts at base+0x40. Detect entry width (12 vs 24 bytes) by sanity.
for entry, fmt in ((24, '<IIQQ'), (12, '<III')):
    ids, dats = [], []
    ok = True
    for r in range(min(rowCount, 8)):
        v = struct.unpack_from(fmt, pl, base+0x40+r*entry)
        rid, dat = (v[0], v[2]) if entry == 24 else (v[0], v[1])
        ids.append(rid); dats.append(dat)
        if not (0 < dat < len(pl)-base): ok = False
    if ok and ids == sorted(ids) and len(set(ids)) == len(ids):
        print(f"entry width {entry}: first ids {ids[:4]}, first data offs {dats[:2]}")
        break
else:
    sys.exit("row table layout not recognised")

rows = []
for r in range(rowCount):
    v = struct.unpack_from(fmt, pl, base+0x40+r*entry)
    rid, dat = (v[0], v[2]) if entry == 24 else (v[0], v[1])
    rows.append((rid, base+dat))

# Sanity: read current durability values across all rows
import collections
cur = collections.Counter()
for rid, da in rows:
    d0 = struct.unpack_from('<H', pl, da+DUR)[0]
    d1 = struct.unpack_from('<H', pl, da+DURMAX)[0]
    cur[(d0,d1)] += 1
print("value histogram (durability,durabilityMax) top10:", cur.most_common(10))

if '--apply' in sys.argv:
    n = 0
    for rid, da in rows:
        struct.pack_into('<HH', pl, da+DUR, 9999, 9999) if DURMAX == DUR+2 else None
        if DURMAX != DUR+2:
            struct.pack_into('<H', pl, da+DUR, 9999)
            struct.pack_into('<H', pl, da+DURMAX, 9999)
        n += 1
    comp = zlib.compress(bytes(pl), 9)
    out = bytearray(container)
    struct.pack_into('>II', out, dcsOffset+4, len(pl), len(comp))
    new = bytes(out[:payload_start]) + comp + bytes(container[payload_start+cSize:])
    open(TARGET + '.new', 'wb').write(new)
    print(f"patched {n} rows -> {TARGET}.new ({len(new)} bytes)")
