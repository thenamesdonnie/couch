"""Build a plain ELF64 (ET_DYN, base 0) from the Bloodborne 1.09 fake SELF so
Ghidra's stock ELF loader can import it with correct module VAs.

* the two PT_LOAD segments are copied to correct file offsets (the SELF's own
  segment table, not the broken ELF p_offset fields)
* every R_X86_64_RELATIVE relocation is pre-applied (pointer = addend), so
  vtables / string pointers in .data resolve statically
* everything else (dynamic, SCE headers) is dropped

Read-only on the game files. Output goes wherever argv[1] says.
"""
import struct, sys
from bbeboot import Eboot, PT_LOAD

e = Eboot()
out = sys.argv[1]
segs = e.segs
# lay out: ELF header (64) + phdrs (56 each), then segments 16K aligned
phnum = len(segs)
hdr_size = 64 + 56 * phnum
cur = (hdr_size + 0x3fff) & ~0x3fff
blobs = []
for p in segs:
    data = bytearray(e.data[p["file_off"]:p["file_off"] + p["filesz"]])
    blobs.append((p, cur, data))
    cur += (p["filesz"] + 0x3fff) & ~0x3fff

# pre-apply RELATIVE relocs
applied = 0
for off, typ, sym, add in e.relocations():
    if typ != 8:
        continue
    for p, foff, data in blobs:
        rel = off - p["vaddr"]
        if 0 <= rel < p["filesz"] - 7:
            struct.pack_into("<Q", data, rel, add & 0xFFFFFFFFFFFFFFFF)
            applied += 1
            break
print(f"applied {applied} RELATIVE relocations")

with open(out, "wb") as f:
    ident = b"\x7fELF" + bytes([2, 1, 1, 9, 0]) + b"\0" * 7   # FreeBSD ABI
    f.write(ident)
    f.write(struct.pack("<HHIQQQIHHHHHH", 3, 62, 1, e.entry, 64, 0, 0,
                        64, 56, phnum, 0, 0, 0))
    for p, foff, data in blobs:
        f.write(struct.pack("<IIQQQQQQ", PT_LOAD, p["flags"], foff, p["vaddr"],
                            p["vaddr"], p["filesz"], p["memsz"], 0x4000))
    for p, foff, data in blobs:
        f.seek(foff)
        f.write(data)
print("wrote", out)
