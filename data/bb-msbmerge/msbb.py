"""
Minimal MSBB (Bloodborne .msb) reader / writer.

Ported from the SoulsFormats reference (JKAnderson/SoulsFormats,
SoulsFormats/Formats/MSB/MSBB/*.cs).  Deliberately NOT a full field-by-field
parser: every entry is carried as an opaque byte blob, because every offset
inside an MSBB entry is relative to that entry's own start, which makes the
blob position independent.  On top of the blob we parse only:

  * supertype / subtype / name          (the merge identity)
  * every index field that references another list, resolved to a NAME
  * a "field decomposition" (named blocks, 4-byte words, strings) so that a
    3-way field-level diff is possible

Writing simply re-emits the header, the param tables and the blobs, so a
read/write cycle with no edits is byte identical by construction.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field as dc_field

# ---------------------------------------------------------------- constants

MODEL, EVENT, POINT, PARTS = "MODEL_PARAM_ST", "EVENT_PARAM_ST", "POINT_PARAM_ST", "PARTS_PARAM_ST"
SUPERTYPES = (MODEL, EVENT, POINT, PARTS)

MODEL_TYPES = {
    0: "MapPiece", 1: "Object", 2: "Enemy", 3: "Item", 4: "Player",
    5: "Collision", 6: "Navmesh", 0xFFFFFFFF: "Other",
}
MODEL_ORDER = [0, 1, 2, 3, 4, 5, 6, 0xFFFFFFFF]

EVENT_TYPES = {
    0: "Light", 1: "Sound", 2: "SFX", 3: "Wind", 4: "Treasure", 5: "Generator",
    6: "Message", 7: "ObjAct", 8: "SpawnPoint", 9: "MapOffset", 10: "Navmesh",
    11: "Environment", 12: "PseudoMultiplayer", 13: "WindSFX", 14: "PatrolInfo",
    15: "DarkLock", 16: "PlatoonInfo", 17: "MultiSummon", 0xFFFFFFFF: "Other",
}
EVENT_ORDER = [1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 0xFFFFFFFF]

PART_TYPES = {
    0: "MapPiece", 1: "Object", 2: "Enemy", 4: "Player", 5: "Collision",
    8: "Navmesh", 9: "DummyObject", 10: "DummyEnemy", 11: "ConnectCollision",
    0xFFFFFFFF: "Other",
}
PART_ORDER = [0, 1, 2, 4, 5, 8, 9, 10, 11, 0xFFFFFFFF]

SHAPE_TYPES = {0: "Point", 1: "Circle", 2: "Sphere", 3: "Cylinder", 4: "Rect", 5: "Box", 6: "Composite"}

# a reference: (list it points into, "kind" of value)
REF_MODELS, REF_PARTS, REF_REGIONS, REF_COLLISIONS = "models", "parts", "regions", "collisions"


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def _i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def _i64(b, o):
    return struct.unpack_from("<q", b, o)[0]


def _i16(b, o):
    return struct.unpack_from("<h", b, o)[0]


def _put_i32(ba, o, v):
    struct.pack_into("<i", ba, o, v)


def _put_i16(ba, o, v):
    struct.pack_into("<h", ba, o, v)


def _utf16(b, o):
    end = o
    while b[end:end + 2] != b"\x00\x00":
        end += 2
    return b[o:end].decode("utf-16-le")


# ---------------------------------------------------------------- entry

@dataclass
class Entry:
    supertype: str
    subtype: int              # raw type enum value
    name: str
    blob: bytearray           # verbatim bytes of the entry, entry-relative offsets inside
    refs: dict                # field_path -> (target_list, name_or_None)
    ref_slots: dict           # field_path -> (byte_offset, width_in_bytes)
    fields: dict              # field_path -> value (for the 3-way diff)
    field_slots: dict         # field_path -> (byte_offset, n_bytes) for patchable words
    dup: int = 0              # occurrence index among entries with the same (supertype, subtype, name)
    needs_id: bool = False    # True for entries we appended; their `id` field is assigned on save
    origin: str = ""          # bookkeeping for the report

    @property
    def subtype_name(self):
        return {MODEL: MODEL_TYPES, EVENT: EVENT_TYPES, PARTS: PART_TYPES}.get(
            self.supertype, {}).get(self.subtype, f"0x{self.subtype:X}") if self.supertype != POINT else "Region"

    @property
    def key(self):
        """
        Stable cross-file identity.  Deliberately NOT SoulsFormats' global
        " {2}" disambiguated name: in m33_00_00_00 Bloodborne Enhanced adds an
        Enemy called "c0000_0003" which sorts ahead of vanilla's Player of the
        same name and would steal the un-suffixed name from it, making the
        Player look deleted-and-re-added.  Counting duplicates within the
        (supertype, subtype) pair instead keeps both stable.
        """
        return (self.supertype, self.subtype, self.name, self.dup)

    @property
    def label(self):
        d = f" #{self.dup + 1}" if self.dup else ""
        return f"{self.supertype.split('_')[0]}/{self.subtype_name}/{self.name}{d}"

    @property
    def display(self):
        return f"{self.name}" + (f" #{self.dup + 1}" if self.dup else "")


# ---------------------------------------------------------------- decoding

def _string_and_word_fields(blob, offsets, string_offsets, header_len, fixed_fields):
    """
    Decompose an entry blob into named fields.

    offsets: {block_name: absolute_offset_inside_blob} for non-string blocks
    string_offsets: {field_name: offset} for null-terminated UTF-16 strings
    header_len: length of the fixed header (its words are named hdr:0xNN)
    fixed_fields: iterable of (name, offset, nbytes, kind) explicitly named header fields
                  kind in {"u32","i32","f32","raw"}; header words not covered are auto-named.
    """
    fields, slots = {}, {}

    skip = set()
    for _n, off, nb, _k in fixed_fields:
        for i in range(off, off + nb):
            skip.add(i)

    for name, off, nb, kind in fixed_fields:
        raw = bytes(blob[off:off + nb])
        if kind == "i32":
            fields[name] = _i32(blob, off)
        elif kind == "u32":
            fields[name] = _u32(blob, off)
        elif kind == "f32":
            fields[name] = struct.unpack_from("<f", blob, off)[0]
        elif kind == "skip":
            continue
        else:
            fields[name] = raw
        slots[name] = (off, nb)

    # remaining header words
    o = 0
    while o + 4 <= header_len:
        if o not in skip:
            fields[f"hdr:0x{o:02X}"] = bytes(blob[o:o + 4])
            slots[f"hdr:0x{o:02X}"] = (o, 4)
        o += 4

    for name, off in string_offsets.items():
        fields[f"str:{name}"] = _utf16(blob, off)
        slots[f"str:{name}"] = (off, None)      # None = variable length, not byte-patchable

    # non-string blocks: extents derived from the sorted offset map + blob end
    bounds = sorted(set(list(offsets.values()) + list(string_offsets.values()) + [len(blob)]))
    for bname, boff in offsets.items():
        nxt = next((x for x in bounds if x > boff), len(blob))
        o = boff
        while o + 4 <= nxt:
            fields[f"{bname}:0x{o - boff:02X}"] = bytes(blob[o:o + 4])
            slots[f"{bname}:0x{o - boff:02X}"] = (o, 4)
            o += 4
        if o < nxt:                                   # ragged tail
            fields[f"{bname}:tail"] = bytes(blob[o:nxt])
            slots[f"{bname}:tail"] = (o, nxt - o)
    return fields, slots


def _decode_model(blob):
    name_off, sib_off = _i64(blob, 0x00), _i64(blob, 0x10)
    subtype = _u32(blob, 0x08)
    name = _utf16(blob, name_off)
    fixed = [
        ("model_type", 0x08, 4, "u32"),
        ("_id", 0x0C, 4, "skip"),             # rewritten on save
        ("_instance_count", 0x18, 4, "skip"),  # rewritten on save
        ("_name_off", 0x00, 8, "skip"), ("_sib_off", 0x10, 8, "skip"),
    ]
    fields, slots = _string_and_word_fields(
        blob, {}, {"name": name_off, "sib": sib_off}, 0x28, fixed)
    return subtype, name, {}, {}, fields, slots


_EVENT_TYPEDATA_REFS = {
    4:  [("treasure_part", 0x08, 4, REF_PARTS)],
    5:  ([(f"spawn_point[{i}]", 0x30 + 4 * i, 4, REF_REGIONS) for i in range(8)] +
         [(f"spawn_part[{i}]", 0x50 + 4 * i, 4, REF_PARTS) for i in range(32)]),
    7:  [("objact_part", 0x04, 4, REF_PARTS)],
    8:  [("spawn_point", 0x00, 4, REF_REGIONS)],
    10: [("navmesh_region", 0x00, 4, REF_REGIONS)],
    13: [("wind_region", 0x04, 4, REF_REGIONS)],
    14: [(f"walk_point[{i}]", 0x10 + 2 * i, 2, REF_REGIONS) for i in range(32)],
    16: [(f"group_part[{i}]", 0x10 + 4 * i, 4, REF_PARTS) for i in range(32)],
}


def _decode_event(blob):
    name_off = _i64(blob, 0x00)
    subtype = _u32(blob, 0x0C)
    ent_off, type_off = _i64(blob, 0x18), _i64(blob, 0x20)
    name = _utf16(blob, name_off)

    ref_slots = {"part": (ent_off + 0x00, 4), "region": (ent_off + 0x04, 4)}
    ref_targets = {"part": REF_PARTS, "region": REF_REGIONS}
    if type_off and subtype in _EVENT_TYPEDATA_REFS:
        for nm, off, w, tgt in _EVENT_TYPEDATA_REFS[subtype]:
            ref_slots[nm] = (type_off + off, w)
            ref_targets[nm] = tgt

    fixed = [
        ("event_id", 0x08, 4, "i32"),
        ("event_type", 0x0C, 4, "u32"),
        ("_id", 0x10, 4, "skip"),
        ("_name_off", 0x00, 8, "skip"), ("_ent_off", 0x18, 8, "skip"), ("_type_off", 0x20, 8, "skip"),
    ]
    blocks = {"ent": ent_off}
    if type_off:
        blocks["type"] = type_off
    fields, slots = _string_and_word_fields(blob, blocks, {"name": name_off}, 0x28, fixed)
    return subtype, name, ref_slots, ref_targets, fields, slots


def _decode_region(blob):
    name_off = _i64(blob, 0x00)
    unka_off, unkb_off = _i64(blob, 0x30), _i64(blob, 0x38)
    shape_off, ent_off = _i64(blob, 0x40), _i64(blob, 0x48)
    name = _utf16(blob, name_off)
    fixed = [
        ("shape_type", 0x10, 4, "u32"),
        ("pos_x", 0x14, 4, "f32"), ("pos_y", 0x18, 4, "f32"), ("pos_z", 0x1C, 4, "f32"),
        ("rot_x", 0x20, 4, "f32"), ("rot_y", 0x24, 4, "f32"), ("rot_z", 0x28, 4, "f32"),
        ("_id", 0x0C, 4, "skip"), ("_name_off", 0x00, 8, "skip"),
        ("_unka", 0x30, 8, "skip"), ("_unkb", 0x38, 8, "skip"),
        ("_shape_off", 0x40, 8, "skip"), ("_ent_off", 0x48, 8, "skip"),
    ]
    blocks = {"unka": unka_off, "unkb": unkb_off, "ent": ent_off}
    if shape_off:
        blocks["shape"] = shape_off
    fields, slots = _string_and_word_fields(blob, blocks, {"name": name_off}, 0x50, fixed)
    return 0, name, {}, {}, fields, slots


_PART_TYPEDATA_REFS = {
    1:  [("collision", 0x08, 4, REF_PARTS)],
    9:  [("collision", 0x08, 4, REF_PARTS)],
    2:  ([("collision", 0x1C, 4, REF_PARTS)] +
         [(f"move_point[{i}]", 0x28 + 2 * i, 2, REF_REGIONS) for i in range(8)]),
    10: ([("collision", 0x1C, 4, REF_PARTS)] +
         [(f"move_point[{i}]", 0x28 + 2 * i, 2, REF_REGIONS) for i in range(8)]),
    11: [("collision", 0x00, 4, REF_COLLISIONS)],
}


def _decode_part(blob):
    desc_off, name_off = _i64(blob, 0x00), _i64(blob, 0x08)
    subtype = _u32(blob, 0x14)
    sib_off = _i64(blob, 0x20)
    ent_off, type_off = _i64(blob, 0xB0), _i64(blob, 0xB8)
    gp_off, sgp_off = _i64(blob, 0xC0), _i64(blob, 0xC8)
    name = _utf16(blob, name_off)

    ref_slots = {"model": (0x1C, 4)}
    ref_targets = {"model": REF_MODELS}
    if type_off and subtype in _PART_TYPEDATA_REFS:
        for nm, off, w, tgt in _PART_TYPEDATA_REFS[subtype]:
            ref_slots[nm] = (type_off + off, w)
            ref_targets[nm] = tgt

    fixed = [
        ("instance_id", 0x10, 4, "i32"),
        ("part_type", 0x14, 4, "u32"),
        ("_id", 0x18, 4, "skip"),
        ("_model_index", 0x1C, 4, "skip"),
        ("pos_x", 0x28, 4, "f32"), ("pos_y", 0x2C, 4, "f32"), ("pos_z", 0x30, 4, "f32"),
        ("rot_x", 0x34, 4, "f32"), ("rot_y", 0x38, 4, "f32"), ("rot_z", 0x3C, 4, "f32"),
        ("scale_x", 0x40, 4, "f32"), ("scale_y", 0x44, 4, "f32"), ("scale_z", 0x48, 4, "f32"),
        ("_desc_off", 0x00, 8, "skip"), ("_name_off", 0x08, 8, "skip"), ("_sib_off", 0x20, 8, "skip"),
        ("_ent_off", 0xB0, 8, "skip"), ("_type_off", 0xB8, 8, "skip"),
        ("_gp_off", 0xC0, 8, "skip"), ("_sgp_off", 0xC8, 8, "skip"),
    ]
    blocks = {"ent": ent_off}
    if type_off:
        blocks["type"] = type_off
    if gp_off:
        blocks["gparam"] = gp_off
    if sgp_off:
        blocks["sgparam"] = sgp_off
    fields, slots = _string_and_word_fields(
        blob, blocks, {"desc": desc_off, "name": name_off, "sib": sib_off}, 0xD0, fixed)
    return subtype, name, ref_slots, ref_targets, fields, slots


_DECODERS = {MODEL: _decode_model, EVENT: _decode_event, POINT: _decode_region, PARTS: _decode_part}
_ID_SLOT = {MODEL: 0x0C, EVENT: 0x10, POINT: 0x0C, PARTS: 0x18}


# ---------------------------------------------------------------- MSB

class MSB:
    def __init__(self):
        self.lists = {st: [] for st in SUPERTYPES}
        self.versions = {st: 3 for st in SUPERTYPES}

    # ---- read ----
    @classmethod
    def from_bytes(cls, data: bytes) -> "MSB":
        msb = cls()
        assert data[0:4] == b"MSB ", "not an MSB"
        assert _i32(data, 4) == 1 and _i32(data, 8) == 0x10
        assert data[12:16] == b"\x00\x00\x01\xff", f"unexpected MSB flags {data[12:16]!r}"

        pos = 0x10
        raw = {}
        for _ in range(4):
            version = _i32(data, pos)
            count = _i32(data, pos + 4)
            name_off = _i64(data, pos + 8)
            entry_offs = [_i64(data, pos + 0x10 + 8 * i) for i in range(count - 1)]
            next_off = _i64(data, pos + 0x10 + 8 * (count - 1))
            pname = _utf16(data, name_off)
            assert pname in SUPERTYPES, pname
            msb.versions[pname] = version
            ends = entry_offs[1:] + [next_off if next_off else len(data)]
            raw[pname] = [bytearray(data[s:e]) for s, e in zip(entry_offs, ends)]
            if next_off == 0:
                pos = 0
                break
            pos = next_off
        assert pos == 0, f"final next-param offset was 0x{pos:X}"
        assert set(raw) == set(SUPERTYPES), sorted(raw)

        # decode, then resolve indices -> names
        pending = {}
        for st in SUPERTYPES:
            for blob in raw[st]:
                subtype, name, ref_slots, ref_targets, fields, slots = _DECODERS[st](blob)
                e = Entry(st, subtype, name, blob, {}, ref_slots, fields, slots)
                msb.lists[st].append(e)
                pending[id(e)] = ref_targets

        msb._assign_dups()
        by_list = msb._ref_lists()
        for st in SUPERTYPES:
            for e in msb.lists[st]:
                tgts = pending[id(e)]
                for fname, (off, width) in e.ref_slots.items():
                    idx = _i32(e.blob, off) if width == 4 else _i16(e.blob, off)
                    tgt = tgts[fname]
                    if idx == -1:
                        e.refs[fname] = (tgt, None)
                    else:
                        lst = by_list[tgt]
                        assert 0 <= idx < len(lst), f"{e.label}.{fname} index {idx} out of range for {tgt}"
                        e.refs[fname] = (tgt, lst[idx].key)
        return msb

    def _assign_dups(self):
        """Number repeated names within each (supertype, subtype) group."""
        for st in SUPERTYPES:
            seen = {}
            for e in self.lists[st]:
                k = (e.subtype, e.name)
                e.dup = seen.get(k, 0)
                seen[k] = e.dup + 1

    def _ref_lists(self):
        return {
            REF_MODELS: self.lists[MODEL],
            REF_PARTS: self.lists[PARTS],
            REF_REGIONS: self.lists[POINT],
            REF_COLLISIONS: [p for p in self.lists[PARTS] if p.subtype == 5],
        }

    # ---- write ----
    def to_bytes(self, strict_refs=True) -> bytes:
        lost = []
        by_list = self._ref_lists()
        pos_of = {k: {e.key: i for i, e in enumerate(v)} for k, v in by_list.items()}

        # rebuild every index field from its stored name
        for st in SUPERTYPES:
            for e in self.lists[st]:
                for fname, (tgt, refkey) in e.refs.items():
                    off, width = e.ref_slots[fname]
                    if refkey is None:
                        idx = -1
                    else:
                        idx = pos_of[tgt].get(refkey, None)
                        if idx is None:
                            lost.append((e.label, fname, tgt, refkey))
                            idx = -1
                    if width == 4:
                        _put_i32(e.blob, off, idx)
                    else:
                        _put_i16(e.blob, off, idx)

        # Per-subtype running "id" field.  From's own files are not always
        # canonical here (vanilla m23_00_00_01's Other events start at 1, not
        # 0), so existing entries keep the id byte they shipped with and only
        # entries we appended get a fresh one.  That keeps an unedited
        # read/write cycle byte identical.
        for st in SUPERTYPES:
            highest = {}
            for e in self.lists[st]:
                if not e.needs_id:
                    highest[e.subtype] = max(highest.get(e.subtype, -1), _i32(e.blob, _ID_SLOT[st]))
            for e in self.lists[st]:
                if e.needs_id:
                    if st == PARTS and e.subtype == 0xFFFFFFFF:
                        v = 0
                    else:
                        v = highest.get(e.subtype, -1) + 1
                        highest[e.subtype] = v
                    _put_i32(e.blob, _ID_SLOT[st], v)
                    e.needs_id = False

        # model instance counts
        part_model_count = {}
        for p in self.lists[PARTS]:
            mk = p.refs["model"][1]
            if mk is not None:
                part_model_count[mk] = part_model_count.get(mk, 0) + 1
        for m in self.lists[MODEL]:
            _put_i32(m.blob, 0x18, part_model_count.get(m.key, 0))

        if strict_refs and lost:
            raise ValueError(f"dangling references: {lost[:5]}")

        out = bytearray(b"MSB \x01\x00\x00\x00\x10\x00\x00\x00\x00\x00\x01\xff")
        for pi, st in enumerate(SUPERTYPES):
            entries = self.lists[st]
            table = 0x10 + 8 * len(entries) + 8   # ver+count+nameoff + entry offsets + nextoff
            body = bytearray()
            body += struct.pack("<ii", self.versions[st], len(entries) + 1)
            name_off_slot = len(body)
            body += b"\x00" * 8
            entry_slots = len(body)
            body += b"\x00" * (8 * len(entries))
            next_slot = len(body)
            body += b"\x00" * 8
            assert len(body) == table
            base = len(out)
            # param name string, padded to 8
            struct.pack_into("<q", body, name_off_slot, base + len(body))
            body += st.encode("utf-16-le") + b"\x00\x00"
            while len(body) % 8:
                body += b"\x00"
            for i, e in enumerate(entries):
                struct.pack_into("<q", body, entry_slots + 8 * i, base + len(body))
                body += e.blob
            out += body
            if pi < 3:
                struct.pack_into("<q", out, base + next_slot, len(out))
            else:
                struct.pack_into("<q", out, base + next_slot, 0)
        return bytes(out), lost

    # ---- convenience ----
    def order_check(self):
        """Assert every param is grouped by subtype in the canonical order."""
        for st, order in ((MODEL, MODEL_ORDER), (EVENT, EVENT_ORDER), (PARTS, PART_ORDER)):
            seen, last = [], None
            for e in self.lists[st]:
                if e.subtype != last:
                    assert e.subtype not in seen, f"{st}: subtype {e.subtype} not contiguous"
                    seen.append(e.subtype)
                    last = e.subtype
            ranks = [order.index(s) for s in seen]
            assert ranks == sorted(ranks), f"{st}: subtype order {seen} not canonical"
