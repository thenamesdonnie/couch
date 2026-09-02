"""Disassemble a window of the eboot's code segment with objdump.

No radare2/ghidra on this box; objdump on a raw slice with --adjust-vma gives
correct absolute addresses, which is all that is needed here.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from bbeboot import Eboot

_E = Eboot()


def dis(va: int, size: int = 0x80, start_at: int | None = None) -> str:
    off = _E.va_to_off(va)
    if off is None:
        return f"; {va:#x} not file-backed"
    buf = _E.data[off:off + size]
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(buf)
        p = f.name
    try:
        out = subprocess.run(
            ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64",
             "-M", "intel", f"--adjust-vma={va:#x}", p],
            capture_output=True, text=True).stdout
    finally:
        Path(p).unlink(missing_ok=True)
    lines = [l for l in out.splitlines() if re.match(r"^\s+[0-9a-f]+:", l)]
    return "\n".join(lines)


def dis_around(va: int, back: int = 0x60, fwd: int = 0x60) -> str:
    """Disassemble starting some way back. The start is not instruction
    aligned, so treat the first couple of lines as suspect."""
    return dis(va - back, back + fwd)


if __name__ == "__main__":
    import sys
    va = int(sys.argv[1], 16)
    back = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x60
    fwd = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x60
    print(dis_around(va, back, fwd))
