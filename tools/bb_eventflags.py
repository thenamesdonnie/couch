"""
Bloodborne (PS4 / shadPS4) save file -- event flag block.

WHAT IS PROVEN (verified empirically against real saves, see validate() below)
----------------------------------------------------------------------------
* userdata0000 / backup0000 are plaintext, exactly 1310720 bytes, no checksum.
* The file header contains a section table.  The u32 at offset 0x34 is the
  EVENT FLAG BLOCK OFFSET and the u32 at 0x38 is its LENGTH (always 150001).
  The u32 at 0x3C equals offset+length, which is the validation chain.
  The offset is NOT constant across saves (observed 106377 and 109505), so it
  must be read from the header every time.
* The block is a flat MSB-first bit array of 1200 "group slots" of 125 bytes
  (= 1000 flags) each, plus one trailing pad byte.  1200*125 + 1 == 150001.
* Within a group slot, for a flag whose id ends in the 3 digits `sub`:
      byte = base + slot*125 + (sub >> 3)
      mask = 0x80 >> (sub & 7)          # MSB-first
  i.e. sub == flag_id % 1000.  This matches the FromSoft convention
  (group = id // 1000, bit = id % 1000, MSB-first) and is confirmed by the
  DS3 in-memory implementation reverse engineered in SoulSplitter.

WHAT IS *NOT* KNOWN
-------------------
The map from a flag id's GROUP (flag_id // 1000) to its 0..1199 slot index.
In DS3 this is a runtime table lookup (`worldBlockInfo`), not arithmetic, and
the equivalent table for Bloodborne is not published anywhere I could find.
It is also not stored as a plain array in eboot.bin.
Therefore read_flag(save, flag_id) can only resolve groups present in
GROUP_SLOTS below.  Use calibrate() to add entries yourself.
"""

from __future__ import annotations

import struct

SAVE_SIZE = 1310720
BLOCK_LEN = 150001          # 1200 groups * 125 bytes + 1 pad byte
GROUP_STRIDE = 125          # bytes per group = 1000 flags
N_GROUPS = 1200

_HDR_BLOCK_OFF = 0x34       # u32: offset of the event flag block
_HDR_BLOCK_LEN = 0x38       # u32: length of the event flag block (150001)
_HDR_NEXT_OFF = 0x3C        # u32: == off + len   (validation chain)


class SaveFormatError(Exception):
    pass


class UnknownGroup(KeyError):
    """The flag's group has no known slot index. Pin it with calibrate()."""


# ---------------------------------------------------------------- block locate

def locate_flag_block(save_bytes: bytes) -> tuple[int, int]:
    """Return (base_offset, length) of the event flag block.

    Reads the header section table and validates it.  Falls back to the
    Bloodborne-save-editor anchor chain (FACE marker) if the header looks wrong.
    """
    if len(save_bytes) != SAVE_SIZE:
        raise SaveFormatError(f"expected {SAVE_SIZE} bytes, got {len(save_bytes)}")

    off, length, nxt = struct.unpack_from("<3I", save_bytes, _HDR_BLOCK_OFF)
    if length == BLOCK_LEN and off + length == nxt and 0 < off < SAVE_SIZE - length:
        return off, length

    # Fallback: locate via the appearance block, as the Noxde save editor does.
    # username = FACE_offset - 34497 ; flag AOB = username + 68545 ; base = AOB + 377
    i = save_bytes.find(b"FACE", 0xF000)
    if i < 0:
        raise SaveFormatError("header section table invalid and no FACE anchor found")
    base = (i - 34497) + 68545 + 377
    if not (0 < base < SAVE_SIZE - BLOCK_LEN):
        raise SaveFormatError("fallback anchor produced an out-of-range base")
    return base, BLOCK_LEN


# ---------------------------------------------------------------- core reads

def read_flag_at(save_bytes: bytes, group_slot: int, sub: int) -> bool:
    """Read the bit at (group_slot, sub). This is the fully verified primitive."""
    if not 0 <= group_slot < N_GROUPS:
        raise ValueError(f"group_slot {group_slot} out of range 0..{N_GROUPS - 1}")
    if not 0 <= sub < 1000:
        raise ValueError(f"sub {sub} out of range 0..999")
    base, _ = locate_flag_block(save_bytes)
    byte = base + group_slot * GROUP_STRIDE + (sub >> 3)
    return bool(save_bytes[byte] & (0x80 >> (sub & 7)))


# group (flag_id // 1000) -> slot index 0..1199.
# EMPTY on purpose: the table is not publicly documented and I would not
# guess it.  Add entries you have pinned with calibrate().
GROUP_SLOTS: dict[int, int] = {}


def read_flag(save_bytes: bytes, flag_id: int) -> bool:
    """Read a Bloodborne event flag by its id, e.g. read_flag(buf, 12100872).

    Splits the id the FromSoft way: group = id // 1000, sub = id % 1000.
    `sub` -> byte/bit is verified.  `group` -> slot needs GROUP_SLOTS.
    """
    group, sub = divmod(int(flag_id), 1000)
    try:
        slot = GROUP_SLOTS[group]
    except KeyError:
        raise UnknownGroup(
            f"flag {flag_id}: group {group} has no known slot index. "
            f"The group->slot table for Bloodborne is not public; pin this group "
            f"with calibrate() by diffing two saves around a known in-game event, "
            f"or read it positionally with read_flag_at(save, slot, {sub})."
        ) from None
    return read_flag_at(save_bytes, slot, sub)


# ---------------------------------------------------------------- calibration

def iter_set_flags(save_bytes: bytes):
    """Yield (slot, sub) for every set bit in the flag block."""
    base, length = locate_flag_block(save_bytes)
    blk = save_bytes[base:base + length]
    for slot in range(N_GROUPS):
        seg = blk[slot * GROUP_STRIDE:(slot + 1) * GROUP_STRIDE]
        for i, byte in enumerate(seg):
            if byte:
                for k in range(8):
                    if byte & (0x80 >> k):
                        yield slot, i * 8 + k


def calibrate(before: bytes, after: bytes):
    """Diff two saves and report which (slot, sub) flags changed.

    This is the practical way to pin a group: do one known thing in game
    (light a lamp, open a door), snapshot the save, and look at which slot
    lit up.  You then know GROUP_SLOTS[group_of_that_flag] = that slot.
    Returns a list of (slot, sub, old, new) sorted by slot then sub.
    """
    b0, n0 = locate_flag_block(before)
    b1, n1 = locate_flag_block(after)
    out = []
    for slot in range(N_GROUPS):
        o0 = b0 + slot * GROUP_STRIDE
        o1 = b1 + slot * GROUP_STRIDE
        for i in range(GROUP_STRIDE):
            x, y = before[o0 + i], after[o1 + i]
            if x == y:
                continue
            for k in range(8):
                m = 0x80 >> k
                if (x & m) != (y & m):
                    out.append((slot, i * 8 + k, bool(x & m), bool(y & m)))
    return out


# ---------------------------------------------------------------- boss table
# Verified: with the header-derived base, every one of these lands on
# sub 700 / 800 / 850 of its group, which is the FromSoft boss-defeat
# convention.  Ported from Noxde/Bloodborne-save-editor bosses.json
# (rel_offset there is relative to base-377).
BOSSES: dict[str, tuple[int, int]] = {   # name -> (group_slot, sub)
    "Gehrman": (165, 800),
    "Moon Presence": (165, 850),
    "Witch Of Hemwick": (167, 800),
    "Dark Beast Paarl": (168, 700),
    "Blood Starved Beast": (168, 800),
    "Vicar Amelia": (169, 800),
    "Cleric Beast": (170, 700),
    "Father Gascoigne": (170, 800),
    "Celestial Emissary": (171, 700),
    "Ebrietas": (171, 800),
    "Martyr Logarius": (172, 800),
    "Mergo's Wet Nurse": (173, 800),
    "Micolash": (173, 848),      # editor uses a 6-bit mask 848..853
    "Shadow Of Yharnam": (174, 800),
    "One Reborn": (175, 800),
    "Rom": (177, 800),
    "Amygdala": (178, 800),
    "Ludwig": (179, 800),
    "Laurence": (179, 850),
    "Lady Maria": (180, 800),
    "Living Failures": (180, 850),
    "Kos": (181, 800),
}


def bosses_defeated(save_bytes: bytes) -> list[str]:
    return [n for n, (s, b) in BOSSES.items() if read_flag_at(save_bytes, s, b)]


# ---------------------------------------------------------------- self-test

def validate(paths: list[str]) -> None:
    for p in paths:
        d = open(p, "rb").read()
        base, ln = locate_flag_block(d)
        n = sum(1 for _ in iter_set_flags(d))
        print(f"{p}\n  base={base} (0x{base:x}) len={ln}  set flags={n}  "
              f"bosses dead={bosses_defeated(d)}")


if __name__ == "__main__":
    import sys
    args = sys.argv[1:] or ["save/userdata0000", "save/backup0000"]
    validate(args)
    if len(args) >= 2:
        a = open(args[0], "rb").read()
        b = open(args[1], "rb").read()
        print("\ncalibrate(before=%s, after=%s):" % (args[0], args[1]))
        ch = calibrate(a, b)
        cur = None
        for slot, sub, old, new in ch:
            if slot != cur:
                print(f"  slot {slot}:")
                cur = slot
            print(f"     sub {sub:3}  {int(old)} -> {int(new)}")
