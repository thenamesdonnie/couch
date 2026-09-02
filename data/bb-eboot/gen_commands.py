# -*- coding: utf-8 -*-
"""Emit script_commands.md from the recovered dispatch tables."""
import json, re, sys
sys.path.insert(0, '/home/ds2000/couch/data/bb-eboot')
from bbeboot import Eboot

E = Eboot()
byoff = {o: a for o, t, s, a in E.relocations() if t == 8}

def wstr(va):
    b = E.read(va, 400); i = 0
    while i + 1 < len(b) and b[i:i+2] != b'\x00\x00': i += 2
    return b[:i].decode('utf-16-le')

def table(base):
    """entries are {u64 id; wchar_t* name}, id first."""
    out = []; va = base; expect = 0
    while (va + 8) in byoff:
        i = E.u64(va)
        if i != expect:          # the two tables are contiguous; the id resets
            break                # at the boundary, which is what ends the walk
        out.append((i, va, byoff[va + 8], wstr(byoff[va + 8])))
        va += 16; expect += 1
    return out

ACT = table(0x5334490)
ENV = table(0x5334810)

TR = json.load(open('translations.json', encoding='utf-8'))
FLAG = re.compile('|'.join(['ロック', '旋回', '方向', '移動', 'ダッシュ', 'カメラ',
                            '表示', '見た目', '入力', '走', '斜面', '着地']))

used = set(l.strip() for l in open('used_commands.txt', encoding='utf-8') if l.strip())

def emit(f, title, prefix, rows):
    f.write(f"\n## {title} ({len(rows)} commands, ids {rows[0][0]}-{rows[-1][0]})\n\n")
    f.write("| id | entry VA | name | translation | used by c0000.hks | flag |\n")
    f.write("|---:|---|---|---|---|---|\n")
    for i, ev, sv, name in rows:
        u = "yes" if name in used else ""
        fl = "**" if FLAG.search(name) else ""
        f.write(f"| {i} | `{ev:#x}` | {fl}`{name}`{fl} | {TR.get(name,'')} | {u} | "
                f"{'facing/movement' if FLAG.search(name) else ''} |\n")

with open('script_commands.md', 'w', encoding='utf-8') as f:
    f.write("""# Bloodborne 1.09: the complete env() / act() script API

Recovered from `eboot.bin` by walking the two name-to-id registration tables the
engine builds its lookup maps from at startup. Nothing here is guessed: every row
is one 16-byte table entry, and the ids are the table's own, read from the file.

Addresses are **module VAs** (what the shadPS4 cheat JSON calls an "offset").
Runtime address = `0x800000000 + VA`. File offset = `VA + 0x28eb0` in the code
segment, `VA + 0x27df0` in the data segment.

## Table format

Both tables are arrays of

```c
struct ScriptCommand { uint64_t id; const wchar_t *name; };   // 16 bytes
```

with `name` a UTF-16LE string in the code segment. The name pointer is stored as
zero in the file and materialised at load time from an `R_X86_64_RELATIVE`
relocation, so the pointers are only visible through `PT_SCE_RELA`.

| table | first entry VA | entries | ids | script function |
|---|---|---:|---|---|
| act commands | `0x5334490` | 56 | 0-55 | `act("name", ...)` |
| env queries | `0x5334810` | 129 | 0-128 | `env("name", ...)` |

The registration loop that walks them is at `0x1a12870` (act) and `0x1a15ef0`
(env); both do `lea rcx,[rip+table]; mov rbx,[rax+rcx+8]` with `rax = i * 16`,
which is what fixes the id-then-pointer field order. Each name is inserted into a
`std::map` at `0x557a278` / `0x557a2d8`.

The shipped `c0000.hks` calls 86 of the 185 (25 of 56 act, 61 of 129 env).
**99 commands exist that no shipped player script ever calls.**
""")
    emit(f, "act() - commands the script issues to the engine", "act", ACT)
    emit(f, "env() - queries the script makes of the engine", "env", ENV)
print("act", len(ACT), "env", len(ENV))
