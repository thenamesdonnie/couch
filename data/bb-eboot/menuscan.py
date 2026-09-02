"""Decode Bloodborne's debug-menu registration code.

Two registration shapes exist and they must be handled separately, or the
label-to-variable pairing comes out shifted by one item.

  checkbox      lea rsi, <UTF-16 label>
                lea rdx, <&variable>            (or lea rdx,[rN+disp] for a field)
                mov ecx, 1
                mov rdi, <menu>
                call 0xf9df10 / 0xf9df20 / 0xf9df40

  float slider  lea rdi, <widget>               ; a static widget object
                lea rsi, <UTF-16 label>
                vmovss xmm1..3, <min/max/step>
                call 0x29be330                  ; construct the widget
                ...
                lea rsi, <widget>
                lea rdx, <&variable>
                mov rdi, <menu>
                call 0x122ee50                  ; bind widget to variable, add

so the slider's variable is only visible at the *bind* call, which is a few
instructions after the constructor. Pass 1 learns widget -> label from the
constructor, pass 2 reads the variable off the bind.
"""
from __future__ import annotations

import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from bbeboot import Eboot

E = Eboot()

CHECKBOX_CALLS = {0xF9DF10, 0xF9DF20, 0xF9DF40, 0xF9DEF0, 0xF9DF00}
WIDGET_CTOR = {0x29BE330, 0x29BEB10, 0x29AD100, 0x2985480, 0x2762D00, 0x12D6AE0}
BIND_CALL = {0x122EE50, 0x122EE10}

LINE = re.compile(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)\s*(.*)$")
LEA_RIP = re.compile(r"lea\s+(\w+),\[rip\+0x[0-9a-f]+\]\s+#\s+0x([0-9a-f]+)")
LEA_REG = re.compile(r"lea\s+(\w+),\[(\w+)([+-]0x[0-9a-f]+)?\]")
CALL = re.compile(r"call\s+0x([0-9a-f]+)")
VMOVSS = re.compile(r"vmovss\s+(xmm\d+),DWORD PTR \[rip\+0x[0-9a-f]+\]\s+#\s+0x([0-9a-f]+)")


def wstr(va: int, maxb: int = 300):
    b = E.read(va, maxb)
    if not b or b[:2] == b"\x00\x00":
        return None
    i = 0
    while i + 1 < len(b) and b[i:i + 2] != b"\x00\x00":
        i += 2
    if i == 0 or i > 240:
        return None
    try:
        s = b[:i].decode("utf-16-le")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 0x20 for c in s):
        return None
    return s


def disasm(va: int, size: int):
    off = E.va_to_off(va)
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(E.data[off:off + size])
        p = f.name
    try:
        out = subprocess.run(
            ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64", "-M", "intel",
             f"--adjust-vma={va:#x}", p], capture_output=True, text=True).stdout
    finally:
        Path(p).unlink(missing_ok=True)
    return out.splitlines()


def events(va: int, size: int):
    out = []
    for ln in disasm(va, size):
        m = LINE.match(ln)
        if not m:
            continue
        at, text = int(m.group(1), 16), m.group(3)
        r = LEA_RIP.search(text)
        if r:
            out.append((at, "lea_rip", r.group(1), int(r.group(2), 16)))
            continue
        r = LEA_REG.search(text)
        if r:
            out.append((at, "lea_reg", r.group(1), f"{r.group(2)}{r.group(3) or '+0x0'}"))
            continue
        r = VMOVSS.search(text)
        if r:
            b = E.read(int(r.group(2), 16), 4)
            v = struct.unpack("<f", b)[0] if len(b) == 4 else None
            out.append((at, "float", r.group(1), v))
            continue
        r = CALL.search(text)
        if r:
            out.append((at, "call", None, int(r.group(1), 16)))
    return out


def value_of(va: int):
    off = E.va_to_off(va)
    if off is None:
        return "bss -> 0"
    raw = E.data[off:off + 4]
    f = struct.unpack("<f", raw)[0]
    u = struct.unpack("<I", raw)[0]
    return f"{raw.hex()}  u8={raw[0]}  u32={u}  f32={f:g}"


def scan(start: int, size: int):
    ev = events(start, size)
    widgets = {}          # widget VA -> (label, floats)
    items = []
    for i, (at, kind, reg, val) in enumerate(ev):
        if kind != "call":
            continue
        # walk backwards for the register set-up of this call
        rsi = rdi = rdx = None
        floats = []
        for j in range(i - 1, max(-1, i - 26), -1):
            a2, k2, r2, v2 = ev[j]
            if k2 == "call":
                break
            if k2 == "float":
                floats.append(v2)
            elif k2 in ("lea_rip", "lea_reg"):
                if r2 == "rsi" and rsi is None:
                    rsi = (k2, v2)
                elif r2 == "rdx" and rdx is None:
                    rdx = (k2, v2)
                elif r2 in ("rdi", "r15", "r14", "rbx", "r12") and rdi is None and k2 == "lea_rip":
                    rdi = v2
        if val in WIDGET_CTOR and rsi and rsi[0] == "lea_rip":
            s = wstr(rsi[1])
            if s and rdi:
                widgets[rdi] = (s, list(reversed(floats)))
            continue
        if val in CHECKBOX_CALLS and rsi and rsi[0] == "lea_rip":
            s = wstr(rsi[1])
            if s:
                items.append(dict(site=at, label=s, var=rdx, call=val,
                                  kind="bool", floats=list(reversed(floats))))
            continue
        if val in BIND_CALL and rsi and rsi[0] == "lea_rip" and rsi[1] in widgets:
            lab, fl = widgets[rsi[1]]
            items.append(dict(site=at, label=lab, var=rdx, call=val,
                              kind="slider", floats=fl, widget=rsi[1]))
    return items


def fmt(it):
    v = it["var"]
    if v is None:
        vs = "?"
    elif v[0] == "lea_rip":
        vs = f"{v[1]:#x}"
    else:
        vs = v[1]
    val = value_of(v[1]) if (v and v[0] == "lea_rip") else ""
    fl = ("  args=" + ",".join(f"{x:g}" for x in it["floats"] if x is not None)) if it["floats"] else ""
    return f"{it['site']:#010x} {it['kind']:7s} var={vs:<14s} {val:<40s} {it['label']}{fl}"


if __name__ == "__main__":
    for it in scan(int(sys.argv[1], 16), int(sys.argv[2], 16)):
        print(fmt(it))
