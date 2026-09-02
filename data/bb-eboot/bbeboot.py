"""Bloodborne 1.09 eboot.bin: SELF/ELF parsing, VA <-> file offset, relocations.

Read-only. Nothing here writes to the game files.

Address conventions in play (three of them, do not mix them up):

  file offset   byte position inside ~/games/ps4/CUSA00900-patch/eboot.bin
  module VA     p_vaddr-based address; ph0 (code) starts at 0. This is what the
                shadPS4 cheat JSON calls "offset".
  runtime VA    0x800000000 + module VA (shadPS4 loads the module at that base)

The SELF container's own segment table, NOT the ELF p_offset fields, gives the
real file position of each ELF segment. Verified against six known-good cheat
offsets from CUSA00900_01.09.json (original bytes matched at delta 0x28eb0).
"""
from __future__ import annotations

import struct
from bisect import bisect_right
from pathlib import Path

EBOOT = Path("/home/ds2000/games/ps4/CUSA00900-patch/eboot.bin")
LOAD_BASE = 0x800000000          # shadPS4 base_virtual_addr
CHEAT_XML_BIAS = 0x400000        # bb-cheat: XML Address = module VA + this

PT_LOAD = 1
PT_SCE_RELA = 0x61000000
PT_SCE_DYNLIBDATA = 0x61000001
PT_SCE_DYNAMIC = 0x6FFFFF00


class Eboot:
    def __init__(self, path: Path = EBOOT):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self._parse_self()
        self._parse_elf()

    # ---------------- containers ----------------
    def _parse_self(self):
        d = self.data
        (magic, ver, mode, endian, attr, keytype, hsize, msize,
         fsize, nseg, flags, _pad) = struct.unpack_from("<IBBBBIHHQHHI", d, 0)
        assert magic == 0x1D3D154F, "not a PS4 SELF"
        self.self_header_size = hsize
        self.self_segments = []
        for i in range(nseg):
            f_, fo, fsz, msz = struct.unpack_from("<QQQQ", d, 0x20 + i * 32)
            self.self_segments.append(
                dict(flags=f_, file_off=fo, file_size=fsz, mem_size=msz,
                     phdr_index=(f_ >> 20) & 0xFFF, has_data=bool(f_ & 0x800)))
        self.elf_off = 0x20 + nseg * 32

    def _parse_elf(self):
        d = self.data
        e = self.elf_off
        assert d[e:e + 4] == b"\x7fELF"
        self.entry, phoff, _shoff = struct.unpack_from("<QQQ", d, e + 24)
        phentsize, phnum = struct.unpack_from("<HH", d, e + 54)
        self.phdrs = []
        for i in range(phnum):
            t, fl, off, va, pa, fsz, msz, al = struct.unpack_from(
                "<IIQQQQQQ", d, e + phoff + i * phentsize)
            self.phdrs.append(dict(index=i, type=t, flags=fl, p_offset=off,
                                   vaddr=va, filesz=fsz, memsz=msz, align=al))
        # real file offset for each phdr, from the SELF segment table
        by_idx = {s["phdr_index"]: s for s in self.self_segments if s["has_data"]}
        self.segs = []            # loadable, with file backing
        for ph in self.phdrs:
            s = by_idx.get(ph["index"])
            if s is None:
                continue
            ph["file_off"] = s["file_off"]
            if ph["type"] == PT_LOAD:
                self.segs.append(ph)
        self.segs.sort(key=lambda p: p["vaddr"])
        self._seg_starts = [p["vaddr"] for p in self.segs]
        self.rela_ph = next((p for p in self.phdrs if p["type"] == PT_SCE_RELA), None)

    # ---------------- address arithmetic ----------------
    def va_to_off(self, va: int):
        """module VA -> file offset, or None if not file-backed (bss/unmapped)."""
        if va >= LOAD_BASE:
            va -= LOAD_BASE
        i = bisect_right(self._seg_starts, va) - 1
        if i < 0:
            return None
        p = self.segs[i]
        rel = va - p["vaddr"]
        if rel >= p["filesz"]:
            return None
        return p["file_off"] + rel

    def off_to_va(self, off: int):
        """file offset -> module VA, or None."""
        for p in self.segs:
            if p["file_off"] <= off < p["file_off"] + p["filesz"]:
                return p["vaddr"] + (off - p["file_off"])
        return None

    def runtime(self, va: int) -> int:
        return LOAD_BASE + (va - LOAD_BASE if va >= LOAD_BASE else va)

    def cheat_offset(self, va: int) -> str:
        """module VA -> the hex string the shadPS4 cheat JSON uses."""
        return f"{va:X}"

    def cheat_address(self, va: int) -> str:
        """module VA -> the Address= a bb-cheat XML <Line> wants."""
        return f"0x{va + CHEAT_XML_BIAS:08x}"

    def seg_of(self, va: int):
        i = bisect_right(self._seg_starts, va) - 1
        return self.segs[i] if i >= 0 else None

    def read(self, va: int, n: int) -> bytes:
        o = self.va_to_off(va)
        if o is None:
            return b""
        return self.data[o:o + n]

    def u64(self, va: int) -> int:
        b = self.read(va, 8)
        return struct.unpack("<Q", b)[0] if len(b) == 8 else 0

    # ---------------- relocations ----------------
    _rela = None

    def relocations(self):
        """[(r_offset_va, r_type, r_sym, addend)] from PT_SCE_RELA."""
        if self._rela is None:
            p = self.rela_ph
            base = p["file_off"]
            n = p["filesz"] // 24
            out = []
            d = self.data
            for i in range(n):
                off, info, add = struct.unpack_from("<QQq", d, base + i * 24)
                out.append((off, info & 0xFFFFFFFF, info >> 32, add))
            self._rela = out
        return self._rela

    def relative_targets(self):
        """{addend -> [r_offset...]} for R_X86_64_RELATIVE (type 8).

        In a PIE PS4 module a pointer stored in .data is written as 0 in the
        file and materialised at load time from the relocation addend, so a
        raw byte search for a pointer value finds nothing. This is the index
        that actually resolves 'who points at this string'.
        """
        idx = {}
        for off, typ, sym, add in self.relocations():
            if typ == 8:
                idx.setdefault(add, []).append(off)
        return idx


if __name__ == "__main__":
    e = Eboot()
    print(f"{e.path} {len(e.data):,} bytes, ELF at {e.elf_off:#x}")
    print("loadable segments (module VA space):")
    for p in e.segs:
        print(f"  ph{p['index']} flags={p['flags']:#x} "
              f"va {p['vaddr']:#010x}..{p['vaddr']+p['memsz']:#010x} "
              f"filesz={p['filesz']:#x} file_off={p['file_off']:#010x} "
              f"-> file = va + {p['file_off']-p['vaddr']:#x}")
    print(f"runtime = module VA + {LOAD_BASE:#x}")
    r = e.relocations()
    print(f"{len(r):,} relocations in PT_SCE_RELA at file {e.rela_ph['file_off']:#x}")
