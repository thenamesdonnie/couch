"""Find RIP-relative references to a set of module VAs inside the code segment.

x86-64 position-independent code addresses data with `lea r, [rip+disp32]` /
`mov r, [rip+disp32]`, where disp32 = target - (address of the next
instruction). A 4-byte field at file position p therefore "points at"
va(p) + 4 + disp32 whenever the instruction happens to end right after it,
which is the common case for these forms.

So: compute the implied target for every 4-byte window in .text in one numpy
pass, then look up all wanted targets at once. False positives exist (any four
bytes can look like a displacement) but they are easy to reject by
disassembling the few candidates.
"""
from __future__ import annotations

import numpy as np

from bbeboot import Eboot


def implied_targets(e: Eboot, seg_index: int = 0):
    """(positions_as_module_VA, implied_target_VA) arrays for the code segment."""
    p = e.segs[seg_index]
    buf = np.frombuffer(e.data, dtype=np.uint8,
                        count=p["filesz"], offset=p["file_off"])
    n = p["filesz"] - 4
    disp = (buf[0:n].astype(np.uint32)
            | (buf[1:n + 1].astype(np.uint32) << 8)
            | (buf[2:n + 2].astype(np.uint32) << 16)
            | (buf[3:n + 3].astype(np.uint32) << 24))
    pos = np.arange(n, dtype=np.uint32) + np.uint32(p["vaddr"])
    tgt = disp + pos + np.uint32(4)      # wraps mod 2^32, which is correct
    return pos, tgt


def find_refs(e: Eboot, targets, seg_index: int = 0):
    """{target_va: [ref_site_va, ...]} - ref_site_va is where the disp32 starts."""
    pos, tgt = implied_targets(e, seg_index)
    want = np.array(sorted(set(targets)), dtype=np.uint32)
    hit = np.isin(tgt, want)
    idx = np.nonzero(hit)[0]
    out = {}
    for i in idx:
        out.setdefault(int(tgt[i]), []).append(int(pos[i]))
    return out
