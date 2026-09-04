# Bloodborne c0000.hks: toolchain + the locked-on sprint gate

Investigation 2 Sep 2026. Read-only on game files. Nothing under `~/games/ps4/` or
`~/.local/share/shadPS4/` was modified, and the emulator was never launched.

Target: `/home/ds2000/games/ps4/CUSA00900/dvdroot_ps4/action/script/c0000.hks`
(760,643 bytes, Havok Script / Lua 5.1 variant).

---

## 1. Toolchain

### What the file actually is

The header decodes as: version 0x51, format 0x0e, **big endian**, sizeof int 4,
sizeof size_t 8, sizeof Instruction 4, **lua_Number = 4-byte float**, extensions
`MEMOIZATION | STRUCTURES`.

Big endian is the surprise. Bloodborne is a PS4 (little-endian x86-64) title, but
its `.hks` files are stored big endian, and every integer, size and float in the
file is byte-swapped relative to host order. Every tool has to be told this or it
silently produces garbage.

The right hksc compatibility profile is `--game=ds3` (FromSoftware extensions:
structures on, getglobal memoization on, doubles off, native int off), which
matches the header exactly.

### Build

```
cd ~/src
git clone https://github.com/Jake-NotTheMuss/hksc.git hksc
cd hksc
./configure --game=ds3 --with-decompiler --prefix=$PWD/local
make -j8
```

Three local source patches were then needed (all in `~/src/hksc/src`, all marked
with a `PATCH:` comment):

1. **`hksclib.c:541`** - `settings->bytecode_endianness` defaulted to
   `HKSC_DEFAULT_ENDIAN` (host order) and there is no CLI flag for it, so the
   dumper always wrote little-endian output. Changed the default to
   `HKSC_BIG_ENDIAN`. The resulting binary is kept as **`~/src/hksc/src/hksc-be`**
   (the stock little-endian `hksc` is also still in that directory, but a `make`
   now rebuilds both from the patched source).

2. **`lundump.c` `LoadDebug()`** - the endian-swapping branch for the `lineinfo`
   array was wrapped in `#ifdef HKSC_MULTIPLAT`. In a non-multiplat build the
   `#ifdef` compiles the branch out entirely, so it *always* took the raw
   `LoadVector` memcpy path. Every source line number came back byte-swapped:
   line 437 loaded as 3,036,938,240. This is why the first decompile attempt
   emitted 453 MB of blank lines. The guard is now written so the swap branch
   exists in both build configurations.

3. **`lprintf.c` `getfarg()`** - declared `va_list *pap` and was called with
   `&ap`. On x86-64 SysV `va_list` is the array type `__va_list_tag[1]`, so `&ap`
   has type `__va_list_tag(*)[1]`, not `va_list*`. gcc warned about it at build
   time and the listing mode segfaulted inside `getfarg` on the first `%*d`-style
   conversion. Changed to take the `va_list` by value (it decays to a pointer, so
   the consumption is still visible to the caller).

### What works, and the exact commands

| mode | verdict |
|---|---|
| `hksc-be -p` (parse) | works |
| `hksc-be -l -l` (full listing / disassembly) | **works, this is the usable one** |
| `hksc-be -b -c` (load binary, re-dump binary) | works, byte-identical |
| `hksc-be -c` (compile source to bytecode) | works |
| `hksc-be -d` (decompile to Lua source) | **FAILS** |

The winning command:

```
~/src/hksc/src/hksc-be -l -l \
  ~/games/ps4/CUSA00900/dvdroot_ps4/action/script/c0000.hks > c0000.list.txt
```

The decompiler is not a near miss, and it is not our patches: hksc's own
`STATUS-decompiler` says "The decompiler is currently incomplete and is not
expected to pass any tests." On this file it allocates until the OOM killer takes
it (exit 137), or with an 8 GB `ulimit -v` it dies with "not enough memory" after
emitting 11 lines. There is no Lua source out of this file today.

`katalash/DSLuaDecompiler` was not attempted: it is a C# project and dotnet is not
installed on this box. **If you want an actual decompiler, that is the package to
install** (`dotnet-sdk-8.0`); it is the tool the Bloodborne/DS3 modding scene
actually uses for `.hks`, and it would remove the need for the bytecode-level
editing described below.

### Second tool, used as an independent cross-check

`https://github.com/Surasia/hksc-disassembler` (Python) also parses the file
correctly and is what confirmed the big-endian + MEMOIZATION|STRUCTURES reading
before hksc was patched:

```
cd ~/src/hksc-disassembler && python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/hksc_disassembler disassemble <path>/c0000.hks > py_disasm.txt
```

Its loader classes are also what `offsets.py` (in this directory) reuses to turn a
function + instruction number into an exact file byte offset.

`horkrux/hksdisasm` was cloned but not used: it is a C# solution, same dotnet
blocker.

### Readability post-processing

Two things make the raw listing hard to read, and both are fixed in
`c0000.list.named.txt`:

- Every `env()` / `act()` query name is a **UTF-8 Japanese string**, printed by
  hksc as decimal escapes (`\227\131\173...`). These are decoded back to Japanese.
- All 1185 functions are anonymous closures; the listing calls them
  `(anonymous)`. The main chunk assigns each one with a `CLOSURE Rn, <proto idx>`
  immediately followed by `SETGLOBAL <name>`, so the proto index to name mapping
  is exact and complete (1185 closures, 1185 protos, no gaps). Names are
  substituted into the function headers, and `function_index.txt` lists them all.

---

## 2. Round-trip verdict

**Binary in, binary out is byte-identical.** After the endianness and `lineinfo`
patches:

```
hksc-be -b -c -o roundtrip.hks c0000.hks
cmp c0000.hks roundtrip.hks   # no differences, 760643 == 760643 bytes
```

That is a strong result: it means hksc's loader and dumper both understand every
structure in this file, including the FromSoft-specific bits, the structure
extension and the debug info. Nothing is lost or normalised on the way through.

It is worth recording how it failed on the way there, because each failure was a
real bug rather than a compatibility guess:

- unpatched: first difference at **byte 7** (the endianness byte), 233,529 bytes
  differing, every integer byte-swapped;
- after the endianness patch: header correct, first difference at **byte 52,336**,
  194,558 bytes differing, all of it inside the debug `lineinfo` arrays;
- after the `lineinfo` patch: **identical**.

**Source in, binary out also produces a correct header.** A small hand-written
test compiles with the same settings to a header byte-for-byte equal to the
game's (`1b4c 7561 510e 0004 0804 0400 0300 0000`), parses back, and re-dumps
identically:

```
hksc-be -c -o t.hks t.lua && hksc-be -p t.hks && hksc-be -b -c -o t2.hks t.hks
cmp t.hks t2.hks   # identical
```

**The honest limitation:** we cannot do the full source round trip that would let
us ship an edited *script*, because there is no decompiler that will produce the
source in the first place. What is proven is:

- we can read the file completely and accurately (listing),
- we can write a valid file back out (byte-identical dump),
- so an edit made **at the bytecode level** can be shipped.

That is enough to build the mod, and section 4 demonstrates it end to end. It is
not enough to maintain the mod as readable Lua.

---

## 3. The locked-on sprint gate

### There is no lock-on check in the movement code

The string `"ロック中か"` ("is locked on?") appears exactly **three** times in the
whole 760 KB script, and none of them are in the movement states:

- `Act_RollingDirection` (which way a dodge goes),
- `Act_Damage`,
- `Act_AttackRight`.

Searching for `IsLockOn`, `LockOn`, `GetLockonState` etc. returns nothing at all,
because this script's engine queries are all Japanese strings passed to `env()`
and `act()`.

The gate is not a lock-on test. It is a **direction** test, on a Havok behaviour
variable called `MoveDirection`.

### The variable

`MoveDirection` is written **once** in the entire script (in `Act_Damage`, set to
0) and read 14 times, exclusively by the six locomotion state callbacks:
`Walk_onUpdate`, `WalkEnd_onUpdate`, `Run_onUpdate`, `RunEnd_onUpdate`,
`DashStart_onUpdate`, `Dash_onUpdate`.

So it is produced by the engine / Havok behaviour graph, not by the script.
Semantics, read off how it is compared: **0 means the stick is pushed forward
relative to the character's facing; greater than 0 means any other direction.**
When you are not locked on, the character turns to face the stick, so
`MoveDirection` is 0 whenever you are moving at all. When you *are* locked on the
character keeps facing the target, so pushing left, right or back leaves
`MoveDirection` non-zero. That is the entire mechanism. Lock-on is never
mentioned; it just changes whether facing can track the stick.

Speed tiers, from the globals at the top of the file: `Idle = 0, Walk = 1,
Run = 2, Dash = 3`. `Act_Move` maps `MoveSpeedCondition` to the Havok variable
`Locomotion` (8 = walk, 9 = run, 10 = dash) and contains **no** direction check of
its own.

### The gate itself

Line numbers below are into `c0000.list.named.txt`; the `[nnnn]` in each row is
the original Lua source line.

**a) `Run_onUpdate`, source line 3924 - the sprint gate.** This is the one that
matters: it is the transition from the jog into the sprint.

```
c0000.list.named.txt:18476   239  [3924]  GETGLOBAL_MEM   0 -42   ; hkbGetVariable
                             241  [3924]  LOADK           1 -67   ; "DashLimit"
                             243  [3924]  EQ              0 0 -16 ; - 0
                             244  [3924]  JMP             118     ; to 363   (bail)
                             245  [3924]  ... env("精密射撃中か")            (precision aiming?)
                             251  [3924]  EQ              0 0 1
                             252  [3924]  JMP             110     ; to 363   (bail)
                             253  [3924]  ... hkbGetVariable("MoveSpeedLevel")
                             257  [3924]  LE_BK           0 -65 0 ; 0.97 -
                             258  [3924]  JMP             104     ; to 363   (bail)
                             259  [3924]  ... env("アクション継続時間", 5)     (how long held)
                             264  [3924]  LT_BK           0 -70 0 ; 300 -
                             265  [3924]  JMP             97      ; to 363   (bail)
c0000.list.named.txt:18503   266  [3924]  GETGLOBAL_MEM   0 -42   ; hkbGetVariable
                             268  [3924]  LOADK           1 -71   ; "MoveDirection"
                             269  [3924]  CALL_I          0 2 2
c0000.list.named.txt:18507   270  [3924]  EQ              0 0 -16 ; - 0     <-- THE GATE
c0000.list.named.txt:18508   271  [3924]  JMP             91      ; to 363   (bail)
                             272  [3925]  GETGLOBAL_MEM   0 -47   ; hkbFireEvent
                             274  [3925]  LOADK           1 -72   ; "Run to DashStart"
                             275  [3925]  CALL_I          0 2 1
```

In plain Lua that whole block is:

```lua
if hkbGetVariable("DashLimit") == 0
   and env("精密射撃中か") == FALSE
   and hkbGetVariable("MoveSpeedLevel") >= 0.97
   and env("アクション継続時間", 5) > 300
   and hkbGetVariable("MoveDirection") == 0     -- forward only
then
  hkbFireEvent("Run to DashStart")
end
```

**b) `Walk_onUpdate`, source line 3734 - the jog gate.** Same shape, one tier
down. Locked-on strafing never even reaches Run, so it can never reach Dash:

```
c0000.list.named.txt:18717   289  [3734]  GETGLOBAL_MEM   0 -43   ; hkbGetVariable
                             291  [3734]  LOADK           1 -70   ; "MoveDirection"
c0000.list.named.txt:17721   293  [3734]  EQ              0 0 -14 ; - 0     <-- gate
                             294  [3734]  JMP             4       ; to 299   (bail)
                             295  [3735]  ... hkbFireEvent("Walk to Run")
```

**c) The two bail-outs that would undo a one-line fix.** `Dash_onUpdate` (source
line 4204) and `DashStart_onUpdate` (source line 4109) both drop back down the
moment `MoveDirection` becomes non-zero:

```
c0000.list.named.txt:19718   214  [4204]  GETGLOBAL_MEM   0 -44   ; hkbGetVariable
                             216  [4204]  LOADK           1 -68   ; "MoveDirection"
                             217  [4204]  CALL_I          0 2 2
c0000.list.named.txt:19722   218  [4204]  LT_BK           0 -7 0  ; 0 -   (0 < MoveDirection)
                             219  [4204]  JMP             5       ; to 225
                             220  [4205]  ... hkbFireEvent("Dash to Run")
```

i.e. `if MoveSpeedLevel <= 0.97 or MoveSpeedLevel > 1 or MoveDirection > 0 then
fireEvent("Dash to Run") end`. Patching only (a) would give a visible flicker:
sprint starts, is cancelled on the next tick, restarts.

**d) `Act_Damage`, source lines 1686-1691** carries the canonical "which speed do
I resume into" table and states the design intent outright:

```
if MoveSpeedLevel > 1.5 and MoveDirection >  0 then MoveSpeedCondition = Run
if MoveSpeedLevel > 2   and MoveDirection == 0 then MoveSpeedCondition = Dash
```

Fast and sideways is explicitly Run. Fast and forward is Dash.

### What "DashLimit" actually is

`DashLimit` is **not** related to lock-on or direction. It is a stamina lockout
with hysteresis, set in `Act_Damage` at source lines 1671-1673:

```lua
if env("スタミナ取得") <= 0 then
  hkbSetVariable("DashLimit", 1)                 -- out of stamina, sprint locked
elseif env("スタミナ取得") >= 70 and hkbGetVariable("DashLimit") == 1 then
  hkbSetVariable("DashLimit", 0)                 -- recovered past 70, unlock
end
```

It is read as a precondition by `Walk_onUpdate`, `Run_onUpdate`,
`WalkEnd_onUpdate` and `RunEnd_onUpdate`. Leave it alone.

---

## 4. The proposed change, and proof that it can be shipped

Four 4-byte instruction edits, all in the `.hks`, all verified. The offsets were
derived with `offsets.py`, each patch site is guarded by an expected-value assert,
and the result was re-listed with hksc to confirm the new control flow.

| file offset | function | instruction | before | after | effect |
|---|---|---|---|---|---|
| `0x02bea8` | `Walk_onUpdate` | #294 | `39000300` (JMP 4) | `38ffff00` (JMP 0) | Walk to Run regardless of direction |
| `0x02db04` | `Run_onUpdate` | #271 | `39005a00` (JMP 91) | `38ffff00` (JMP 0) | Run to DashStart regardless of direction |
| `0x02f834` | `DashStart_onUpdate` | #218 | `720c0000` (LT_BK) | `39000500` (JMP 6) | drop the MoveDirection bail-out |
| `0x030730` | `Dash_onUpdate` | #218 | `720c0000` (LT_BK) | `39000500` (JMP 6) | drop the MoveDirection bail-out |

The first two work because HKS comparison opcodes are "skip the following JMP if
the test passes". Turning the JMP into `JMP 0` makes both the pass and the fail
path fall through to the next instruction, so the `hkbFireEvent` always runs while
every other precondition (stamina, speed, hold time, not aiming) is left fully
intact. The last two replace the `MoveDirection > 0` test with an unconditional
jump over the "drop back to Run" call, which deletes that one disjunct from the
OR-chain and leaves the speed-based exits working.

Instruction encoding, for anyone editing further: opcode is `raw >> 25`, `A` is
`raw & 0xFF`, `B` is `(raw >> 17) & 0x1FF`, `C` is `(raw >> 8) & 0x1FF`, and for
JMP the signed offset is `((raw >> 8) & 0x1FFFF) - 0xFFFF`. So
`JMP n = (28 << 25) | ((0xFFFF + n) << 8)`. Words are stored big endian.

Verification of the prototype (`c0000.PROTOTYPE.hks` in this directory):

```
hksc-be -p c0000.PROTOTYPE.hks          -> Successfully parsed
hksc-be -b -c -o rt.hks c0000.PROTOTYPE.hks; cmp -> byte-identical
hksc-be -l -l c0000.PROTOTYPE.hks       -> control flow reads as intended:
    Run_onUpdate   271  JMP 0  ; to 272        (was JMP 91 ; to 363)
    Walk_onUpdate  294  JMP 0  ; to 295        (was JMP 4  ; to 299)
    DashStart      218  JMP 6  ; to 225        (was LT_BK)
    Dash           218  JMP 6  ; to 225        (was LT_BK)
```

**`c0000.PROTOTYPE.hks` has never been run in the game.** It is a structurally
valid, correctly-encoded file, and that is the entire claim. It was not installed
into `dvdroot_ps4`.

---

## 5. Risks, in the order they are likely to bite

1. **The animations may not exist.** This is the real risk and the script cannot
   answer it. Note what the gate implies: when locked on, Bloodborne never even
   enters the **Run** state sideways, only Walk. So the character almost certainly
   has locked-on directional *walk/strafe* animations, but there is no evidence
   from the script that locked-on directional *run* or *dash* animations were ever
   authored. If they do not exist, the likely results are the forward sprint
   animation playing while the character slides sideways, or a fallback pose. DS3
   and Elden Ring allow this because they shipped the directional animations, not
   because their script is more permissive.

2. **The Havok behaviour graph may gate it too, and we have not looked.** The
   script only fires named events (`"Run to DashStart"`, `"Dash to Run"`). Whether
   those transitions fire depends on the state machine in `c0000.anibnd.dcx`
   (DCX-compressed, then a BND archive, then `.hkx`). If the graph has its own
   condition on `MoveDirection` for those transitions, the script patch alone does
   nothing. **This is the single biggest unknown and should be checked before
   anything else.** It also means a null result in game does not prove the script
   patch wrong.

3. **Camera and turn behaviour.** `Act_Turn` drives `TurnAngle`, and there are
   dedicated `Turn_Run_*` / `Turn_Dash_*` states. Sprinting sideways while locked
   on puts the character into a facing/velocity combination the turn states were
   not tuned for. Expect the character to fight the camera, or to snap-turn at the
   moment the sprint starts.

4. **Every other consumer of these states.** `Dash` gates the dash attacks
   (`AtkRightDash_*`, `AtkBothDash_*`, `AtkLeftDash_*`, and the
   `*_GunShot_Dash_*` variants). Being in Dash sideways means a sideways dash
   attack becomes reachable, with the same animation question.

5. **Patch (b) is optional and is the more invasive half.** Patching only
   `Run_onUpdate` plus the two bail-outs (a, c, d) gives all-direction *sprint*
   from an existing jog. Adding `Walk_onUpdate` (b) also gives all-direction
   *jog*, which is a larger behavioural change and more likely to expose a missing
   animation. Consider shipping without (b) first.

6. **This is a bytecode patch, not a source patch.** It is exact and it is
   verified, but it is not readable and it will not survive being regenerated. If
   this becomes a real mod, install dotnet and get `DSLuaDecompiler` working so it
   can be maintained as Lua.

7. Bloodborne's own `.hks` files are big endian. Any tool from the DS3/Sekiro/ER
   scene that assumes little endian will read this file as garbage, or silently
   write a file the game cannot load.

---

## 6. DS3 reference

Not available. `find / -iname 'c0000.hks'` outside `CUSA00900` returns nothing on
this machine, and the only `.hks` files present are Bloodborne's own set under
`dvdroot_ps4/action/script/`. No DS3 comparison was possible.

---

## Files in this directory

- `FINDINGS.md` - this document.
- `c0000.list.named.txt` - the full hksc disassembly with Japanese strings decoded
  and all 1185 functions named. **This is the artefact to read.**
- `function_index.txt` - proto index, name, and line number in the listing above.
- `py_disasm.txt` - the independent Python disassembly, kept as a cross-check.
- `offsets.py` - maps (proto index, instruction number) to an exact file byte
  offset; also defines the `jmp(sbx)` encoder.
- `fgrep.py` - grep the listing and report which function each hit is in.
  Usage: `python3 fgrep.py '"MoveDirection"' 4`
- `c0000.PROTOTYPE.hks` - the four-instruction prototype. **Never run in game.**

Tools live at `~/src/hksc` (binary `~/src/hksc/src/hksc-be`) and
`~/src/hksc-disassembler`. `~/src/hksdisasm` was cloned but is unused.

## 3 Sep 2026: Jump on L3 (Nexus 156) merged with lockspint, installed

N3R4i's mod ships `c0000.hks` as PLAIN LUA SOURCE (UTF-8 BOM, a decompile of
stock 1.09 plus the jump: `Arm_L3` request with `アクション継続時間 2 <= 0` fires
`W_Jump`, Modern = works standing still; the zip's Backup/ is byte-identical
stock 335a1af8). So no bytecode surgery: the seven lockspint sites map to seven
source lines and the merge is textual, each asserted to match exactly once
inside the named function:
  Walk_onUpdate  drop `and MoveDirection == 0` from the SlowMove==1 Walk->Run
  Run_onUpdate   drop `and MoveDirection == 0` from Run->DashStart
  DashStart      drop `or 0 < MoveDirection` from the ->Run speed test, the
                 `(MoveSpeedLevel == 1 or 0 < MoveDirection)` timer test, and
                 the ->Walk test
  Dash           drop `or 0 < MoveDirection` from ->Run and ->Walk
(cross-checked against the LOCKSPRINT bytecode: the five LT_BK sites became
jumps to the next elseif = the disjunct treated as false; the two EQ+JMP sites
became JMP 0 = the conjunct dropped.) `hksc-be -p` parses both files.
Files: data/bb-hks/c0000.JUMPL3-LOCKSPRINT.hks (installed, sha 3f62d3b0d),
c0000.JUMPL3-MODERN.stock-mod.hks (the unmerged mod). Lever:
`tools/bb-lockon-sprint install jumpl3` / `install lockspint` (back to
no-jump) / `revert`. Downloaded with the new `tools/nexus-dl 156 1085`
(premium API downloads work since 3 Sep). Classic variant (dash-to-jump) and
both Enhanced variants (jump attack, ladder drop) are in the same zips in
~/fileshare/bloodborne-mods if he wants them; each would need the same merge.
