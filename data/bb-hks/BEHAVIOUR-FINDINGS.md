# Bloodborne c0000 behaviour graph: the locked-on sprint, and whether we can edit it

Investigation 2 Sep 2026, follow-on to `FINDINGS.md` (the `.hks` work).
Read-only on the game. Nothing under `~/games/ps4/` or `~/.local/share/shadPS4/`
was modified and the emulator was never launched. All outputs are in
`~/couch/data/bb-hks/anibnd/`, all tools in `~/src/`.

**Headline: the behaviour graph does not gate anything.** It contains zero
condition objects. Every one of its 754 transitions is a bare event trigger. The
`MoveDirection == 0` gate lives only in `c0000.hks`, exactly where we already
found it. What the graph *does* tell us is the thing we could not see from the
script: **Run has a full four-direction animation set and Dash has none.**

---

## 1. Container round trip (BND / DCX)

```
python: ~/couch/data/ds3-ui-port/.venv/bin/python
        sys.path.insert(0, '/home/ds2000/couch/tools/souls-extract')
        from soulstruct.containers import Binder
```

`c0000.anibnd.dcx` is 2,647,091 bytes, `DCXType.DCX_DFLT_10000_44_9`,
BinderVersion.V4, flags 46, 99 entries: 4 `.hkx`, 80 `.tae`, 15 others.

Extracted to `anibnd/hkx/` and `anibnd/tae_list.txt`:

| entry | bytes |
|---|---|
| `...\chr\c0000\hkx\skeleton.HKX` | 11,280 |
| `...\Action\c0000\Export\c0000.hkx` | 461,440 |
| `...\Action\c0000\Export\Characters\c0000.hkx` | 184,128 |
| `...\Action\c0000\Export\Behaviors\c0000.hkx` | **5,015,744** |

**Verdict: not byte-identical, but content-identical, and that is enough to ship.**

- Repacked DCX is 2,699,542 bytes vs 2,647,091. Not identical.
- Decompressed BND payload: 18,851,134 vs 18,850,240. Not identical either;
  first difference at byte **88**, which is inside the entry header table, and
  every subsequent difference is a shifted data offset. soulstruct pads entry
  data to different boundaries than FromSoft's packer did.
- **All 99 entries compare equal** on name, entry id, flags and data bytes.
  Nothing is lost or reordered.
- Isolating the compressor: taking the *original* payload and re-compressing it
  with soulstruct produces a DCX whose header is byte-identical up to offset 33,
  where the stored compressed size differs. The DCX container fields, magic,
  format `DFLT`, level 9 and block layout are all reproduced correctly; only the
  zlib deflate stream differs (ours is slightly larger). Games inflate, they do
  not compare, so this is cosmetic.

Round-trip artefact: `anibnd/c0000.roundtrip.anibnd.dcx`.

## 2. Getting into the .hkx

### What the file is

Havok **packfile**, magic `57e0e05710c0c010`, contents version `hk_2014.1.0-r1`,
version 11, **pointer size 8, little endian, `reuse_base_class_padding = 1`,
empty-base-class optimisation on**. That reuse-padding flag is the PS4 layout and
it is what most Skyrim-era tools get wrong.

Three sections, `__types__` is **empty**, so the file carries no embedded
reflection and every tool needs an external class database:

```
__classnames__  abs=0x100  size=0x320   (30 classes)
__types__       abs=0x420  empty
__data__        abs=0x420  local=0x44b160 global=0x47b0c0 virtual=0x4a24a0 end=0x4c84a0
                24,555 local fixups, 13,394 global, 12,970 virtual (= 12,970 objects)
```

### HKXPack: the stock one cannot, the Souls fork can

`https://github.com/Dexesttp/hkxpack` (Maven, and Maven is not installed, but the
project publishes release jars) fails immediately and exactly like this:

```
[SEVERE] There was an error handling the file.
[SEVERE] Could not find file for CustomLookAtTwistModifier.
```

Its bundled class database is 908 Skyrim/Fallout definitions with no FromSoftware
classes. `aerisarn/hkxpack` is an older snapshot of the same tree, no help.

Two forks matter:

- **`JeNoVaViRuS/hkxpack-souls` v0.4** is the one that works. It targets
  `hk_2014.1.0-r1` and its jar bundles **1,362 DS3 classxml definitions**
  (upstream ships none). Classes are resolved by name, so a directory placed
  ahead of the jar on the classpath overrides any layout.
- **`Alfred-DMB/HkxPack-Plus`** advertises PS4 `reuse_base_class_padding`
  support. Its reader does handle it, and it round-trips
  `Export\c0000.hkx` (461,440 B) **byte-identically**. Its *writer* is broken for
  this file: it stamps `reuse_base_class_padding = 1` in the header but lays the
  data out as if it were 0, producing a 6,467,536 byte file whose objects no
  longer read at the PS4 offsets. **Do not use it to pack the behaviour graph.**

### The one class Bloodborne changed

Feeding the DS3 class set at the behaviour graph aborts inside an offset error.
Comparing all 30 classes in this file against the published DS3 set:

- 25 match byte for byte, 3 more differ only in leading-zero formatting.
- `CustomManualSelectorGenerator` is **`0x623ce73d` in Bloodborne** vs
  `0xff6b0824` in DS3, but its *member layout is unchanged*, so DS3's definition
  reads Bloodborne data correctly. Only the signature needs patching to repack.
- **`CustomLookAtTwistModifier` really is different.** Its `twistParam` array is
  at **+96 in Bloodborne, +104 in DS3**. Proven from the fixup tables, which are
  ground truth: in all four instances the local-fixup table places a pointer at
  `+96` and nowhere near `+104`, and the array header there is coherent
  (count 1/1/2/2, capacity-and-flags `0x8000000n`), while `+104` gives
  count = 1,106,247,680 and no pointer. Reading the angle block at `+112` then
  yields 30.0 / 30.0 / 60.0 / 60.0, which is sane. Bloodborne is missing one
  4-byte member that DS3 has before `twistParam`; `+92` reads 57 in every
  instance, implausible for DS3's 0/1 `rotationAxisType` enum and very plausible
  as `SensingDummyPoly`.

The corrected set is `~/src/bb-havok/classxml-bb/` (1,362 files: the DS3 set with
`CustomLookAtTwistModifier` shifted down 8 bytes from `twistParam` onward, size
192 to 184, and the CMSG signature changed to `0x623ce73d`), staged for the
classpath as `~/src/bb-havok/override/`.

### The command that unpacks the behaviour graph

```
java -Xmx10g -XX:+ExitOnOutOfMemoryError \
  -cp ~/src/bb-havok/override:~/src/bb-havok/hkxpack-souls-cli.jar \
  com.dexesttp.hkxpack.cli.ConsoleView unpack -q c0000_behavior.hkx
```

5,015,744 bytes in, **13,747,565 bytes of XML out**, about 40 seconds. The earlier
out-of-memory failures were not memory at all: a bad `twistParam` offset was
driving a runaway array allocation. With the class fixed it completes comfortably.

### hkx round-trip verdict

Unpack then pack, with no edits, gives **5,027,424 bytes vs 5,015,744. Not
byte-identical, but semantically exact.** Verified with an independent reader
(see below):

```
items 12970 == 12970      class histogram identical: True
all 7,784 hkbClipGenerator animationNames identical, in order: True
event / variable / attribute / character-property tables identical: True
Move StateMachine states and transitions identical: True
```

The single meaningful difference is header byte 18: the original says
`reuse_base_class_padding = 1`, the repack says `0`, and every object is then
laid out without reusing base-class padding, which is where the extra 11,680
bytes go. The file is internally consistent and declares what it does, so Havok
should load it, **but it is a real deviation from the shipped layout on a PS4
title and has not been play-tested.** That is the one caveat on everything in
section 5.

### soulstruct-havok

`pip install soulstruct-havok colorama` (1.2.2) parses the packfile structure but
dies with
`TypeNotDefinedError: Type hkbBehaviorGraph is not defined in Havok module hk2014`.
Its hk2014 tree covers animation, skeleton and ragdoll only, no `hkb*` classes.
There is no published Bloodborne class set anywhere: only `classxmlds3` exists,
in `soulsmods/DSMapStudio`, `vawser/Smithbox` and `WarpZephyr/Cauldron`.

### The independent reader used to check all of the above

`~/src/bb-havok/pf.py` - about 90 lines of Python that parse the section headers,
the class name table and the three fixup tables, which gives every object's file
offset and class name directly from the file. Members are then read at the DS3
classxml offsets. Every offset this report relies on is confirmed by the
authoritative DS3 definitions:

```
hkbNode.name@56                    hkbStateMachine.states@208 wildcardTransitions@224 startStateId@168
hkbStateMachineStateInfo           transitions@80 generator@88 name@96 stateId@104
hkbManualSelectorGenerator         generators@136 selectedGeneratorIndex@152
CustomManualSelectorGenerator      generators@136 offsetType@152 animId@156
hkbClipGenerator.animationName@144 hkbBehaviorGraphStringData eventNames@16 variableNames@48
hkbStateMachineTransitionInfo      size 72: transition@32 condition@40 eventId@48 toStateId@52 priority@64 flags@66
```

Cross-check that the stride and offsets are right: reading all 206
`hkbStateMachineTransitionInfoArray` objects yields **754 transitions, every one
with an in-range `eventId` and a `transition` pointer landing on a real
`CustomTransitionEffect` (725) or `hkbBlendingTransitionEffect` (29)**. Wrong
offsets would give noise.

---

## 3. The gate, as actually found in the graph

### There are no conditions. At all.

```
transitions total 754, with non-null condition: 0
```

`hkbExpressionCondition`, `hkbScriptCondition` and `hkbStringCondition` all exist
in HKXPack's database. **None of them appears in this file's 30-entry class name
table**, so no such object can exist here, and every `condition` pointer in every
transition is null. There is no expression string to quote, because there are no
expressions.

The consequence is important: **the behaviour graph cannot be what blocks a
sideways sprint.** It is a pure event machine. Whatever `hkbFireEvent` the script
sends, the state changes.

### The Move StateMachine, in full

`anibnd/graph_move_statemachine.txt`. Object at data offset `0x177070`,
`startStateId = 8`.

Wildcard transitions (global + local, so they fire from any state):

```
on W_Run        -> stateId 9   prio 2   ALLOW_SELF_TRANS_FROM_ANY|IS_GLOBAL_WILDCARD|IS_LOCAL_WILDCARD
on W_Walk       -> stateId 8   prio 1   (same flags)
on W_DashStart  -> stateId 10  prio 0
on W_Dash       -> stateId 11  prio 0
on W_DashEnd    -> stateId 12  prio 0
on W_RunEnd     -> stateId 13  prio 0
on W_WalkEnd    -> stateId 14  prio 0
```

Per-state transitions, all with `cond=NULL`:

```
[8]  Walk       on "Walk to Run"        -> 9   prio 2
                on "Walk to WalkEnd"    -> 14
[9]  Run        on "Run to Walk"        -> 8
                on "Run to RunEnd"      -> 13
                on "Run to DashStart"   -> 10
[10] DashStart  on "DashStart to Dash"  -> 11
                on "DashStart to Run"   -> 9
                on "DashStart to DashEnd" -> 12
                on "DashStart to Walk"  -> 8
[11] Dash       on "Dash to DashEnd"    -> 12
                on "Dash to Run"        -> 9   prio 2
                on "Dash to Walk"       -> 8   prio 1
[12] DashEnd    on "DashEnd to Run"     -> 9   prio 2
                on "DashEnd to Walk"    -> 8   prio 1
[13] RunEnd     on "RunEnd to Walk"     -> 8   prio 1
                on "RunEnd to Run"      -> 9   prio 2
[14] WalkEnd    on "WalkEnd to Walk"    -> 8
                on "WalkEnd to Run"     -> 9
```

There is a mirrored twin, `Move StateMachine_mirror` at `0x2c39e0`, identical in
shape, used by the left-handed/mirrored layer.

### Where the gate really is

Cross-checking the disassembly in `c0000.list.named.txt`, in
`Run_onUpdate` (function at line 3853, instructions 239-275):

```
239-244  if hkbGetVariable("DashLimit") ~= 0 then return end
245-252  if env("精密射撃中か") ~= FALSE then return end        -- precision-aiming
253-258  if hkbGetVariable("MoveSpeedLevel") < 0.97 then return end
259-265  if env("アクション継続時間", 5) < 300 then return end   -- action-held time
266-271  if hkbGetVariable("MoveDirection") ~= 0 then return end   <-- THE GATE
272-275  hkbFireEvent("Run to DashStart")
```

And in `Walk_onUpdate` (function at line 3655), the picture is subtler than we
had it. The function branches on `SlowMove` first:

```
232-237  if SlowMove == 0 then
238-243     if MoveSpeedLevel < 0.97 then return end
244-249     if MoveSpeedLevel > 2 then return end
250-257     if 精密射撃中か ~= FALSE then return end
258-261     hkbFireEvent("Walk to Run")        -- NO MoveDirection test on this path
         else
263-268     if SlowMove ~= 1 then return end
269-274     if DashLimit ~= 0 then return end
275-280     if MoveSpeedLevel < 2 then return end
281-288     if 精密射撃中か ~= FALSE then return end
289-294     if MoveDirection ~= 0 then return end    <-- gate, slow-move path only
295-298     hkbFireEvent("Walk to Run")
```

**So in plain language.** Bloodborne's `Run` state is the normal jog, not the
sprint. `Dash` is the sprint. Walking to Run on the ordinary path is not gated on
direction at all, and the Run state then picks a direction-correct clip, which is
why a locked-on player strafing at speed already gets a proper sideways *run*
animation. The thing that never happens sideways is **Dash**, and it is blocked
by one instruction pair, `Run_onUpdate` 266-271, testing `MoveDirection == 0`.
`MoveDirection` is the stick direction relative to the character's facing, and
while locked on the facing stays welded to the target, so a sideways stick can
never read 0. That is the whole gate, and it is script-side, not graph-side.

Variable and event tables are saved as `anibnd/graph_variables.txt` (83 entries)
and `anibnd/graph_events.txt` (1,109 entries). Relevant indices:

```
variables:  5 MoveSpeedLevel   6 MoveAngle    14 MoveDirection   18 MoveSpeedCondition
           23 UpperCondition  46 LocomotionState  47 Locomotion   50 DashLimit  74 SlowMove
events:     7 DashStart to Dash     9 Walk to Run     10 Run to Walk    11 Run to RunEnd
           13 Run to DashStart     14 DashStart to Run  17 Dash to Run   18 Dash to Walk
           24 W_Run  25 W_Walk  432 W_Dash  433 W_DashStart  431 W_DashEnd  430 W_RunEnd
```

There is **no lock-on variable in the graph at all**. Nothing named IsLockOn or
similar exists among the 83. Lock-on is invisible to the behaviour graph; it only
shows up indirectly, as `MoveDirection` becoming non-zero.

---

## 4. Animation inventory: this is the real finding

`anibnd/graph_locomotion_animations.txt` and `graph_locomotion_trees.txt`.

Walk and Run both hang off a two-level selector: an outer
`hkbManualSelectorGenerator` bound to **`UpperCondition`** (normal vs guard),
then an inner one bound to **`MoveDirection`** with exactly four children in the
order Front, Back, Left, Right. Each leaf is a `CustomManualSelectorGenerator`
holding one `hkbClipGenerator` per weapon animation set (a000, a002, a003, a005,
a020...a033, a200...a233).

```
Walk      Front 003000   Back 003001   Left 003002   Right 003003
Run       Front 004000   Back 004001   Left 004002   Right 004003
                (+ 004010 "RunFront Normal Slow", selected by SlowMove)
WalkEnd   Front 006500   Back 006501   Left 006502   Right 006503
RunEnd    Front 006600   Back 006601   Left 006602   Right 006603

DashStart  005200   <- single CustomManualSelectorGenerator, NO direction selector
Dash       005000   <- same
DashEnd    006700   <- same
```

Independent cross-check, from each selector's own `animId` field (which the DS3
class definition gives us, and which is set separately from the clip names):

```
DashStart   offsetType=IdleCategory  animId=5200      Dash   ...animId=5000    DashEnd ...animId=6700
Run Front   animId=4000 (+4010 Slow)  Back 4001  Left 4002  Right 4003
Walk Front  animId=3000               Back 3001  Left 3002  Right 3003
```

Every `CustomManualSelectorGenerator` in this chain has `offsetType =
IdleCategory`, meaning it picks its child by the idle/weapon category, **never by
direction**. That is the class's own semantics confirming the structure: the
direction dimension exists only in the `hkbManualSelectorGenerator` layer above,
and above the three dash states there is no such layer. Saved as
`anibnd/graph_cmsg_animids.txt`.

**Yes, Bloodborne has sideways and backward run animations, and they are real
files on disk.** Checked against `c0000_a0x.anibnd.dcx` and `c0000_a2x.anibnd.dcx`:
`a002_004002`, `a003_004002`, `a005_004002`, `a021_004002`... every direction ID
(003000-003003, 004000-004003, 006600-006603) resolves to 8+ clips of 16-25 KB
each. Nothing is a stub.

**No, there is no sideways or backward dash.** `DashStart`, `Dash` and `DashEnd`
have a flat list of 13-15 clip generators indexed by *weapon set*, never by
direction, and only the forward IDs 005200 / 005000 / 006700 exist. The four-way
selector that Walk, Run, WalkEnd and RunEnd all have is simply absent above the
three dash states.

So the honest answer to "why does a locked-on sideways sprint not exist": FromSoft
never animated one. The script gate at `Run_onUpdate` 266-271 is guarding an
animation set that has no sideways member. Remove the gate and the character will
sprint sideways playing the forward dash clip, which will read as a moonwalk.

---

## 5. Proposed edit, and the candidate files

### The graph edit for a sideways sprint is: none

There is nothing to unblock. `Walk -> Run` and `Run -> DashStart` already exist as
unconditional event transitions and will fire whenever the script sends the event,
at any `MoveDirection`. The only change needed to make the transitions happen is
the one-instruction `.hks` patch we already have in `c0000.PROTOTYPE.hks`.

That also means the earlier "we patched the script and nothing changed" result is
**not** explained by a second gate in the graph. There isn't one. The remaining
explanations are (a) the patched `.hks` was not actually being loaded, which is
the same overlay-vs-patcher question that killed the lamp menu, or (b) it was
loaded, `Dash` did engage, and it was not visible because the forward dash clip
played while the character faced the target, or (c) `DashLimit`, `MoveSpeedLevel`
or the 300-unit hold time stopped it first. Those are testable in that order and
(a) is by far the most likely given the file's history.

### The graph edit that would make it *look* right, now built and verified

Give the three dash states the same four-way `MoveDirection` selector that Walk,
Run, WalkEnd and RunEnd already have, reusing generators that already exist in
the file. `~/src/bb-havok/xml_edit.py` does it on the unpacked XML:

```
state DashStart -> stateInfo #4454   generator -> new #13060
      Front #4460 DashStart CMSG (5200)   Back #4348 RunBack (4001)
      Left  #4378 RunLeft   (4002)        Right #4408 RunRight (4003)
state Dash      -> stateInfo #4476   generator -> new #13062
      Front #4481 Dash CMSG (5000)        Back/Left/Right as above
state DashEnd   -> stateInfo #4495   generator -> new #13064
      Front #4499 DashEnd CMSG (6700)     Back #4533 / Left #4547 / Right #4561 RunEnd strafes
```

Each new `hkbManualSelectorGenerator` gets a new `hkbVariableBindingSet` binding
`selectedGeneratorIndex` to variable **14 `MoveDirection`**, copied from the
pattern the Run selector already uses. Six new objects, nothing else touched.

Repacked with hkxpack-souls to `c0000_behavior.dirdash.hkx` (5,029,008 bytes) and
verified by reparsing the packed binary with the independent reader
(`anibnd/graph_dirdash_verify.txt`):

```
objects: 12976   (12970 + 6)
class delta: hkbManualSelectorGenerator +3, hkbVariableBindingSet +3
all 7,784 clip animationNames unchanged      conditions introduced: 0
[10] DashStart -> 'DashStart Direction ManualSelectorGenerator' bind:selectedGeneratorIndex<-MoveDirection
[11] Dash      -> 'Dash Direction ManualSelectorGenerator'      bind:selectedGeneratorIndex<-MoveDirection
[12] DashEnd   -> 'DashEnd Direction ManualSelectorGenerator'   bind:selectedGeneratorIndex<-MoveDirection
```

Forward sprint is untouched and still plays 5200/5000/6700. Sideways and backward
sprint now play the run strafe set (4001/4002/4003) instead of moonwalking on the
forward dash clip. It is not a real dash animation, because none exists, but it is
direction-correct.

This still needs the `.hks` gate removed to ever be reached, and it carries the
`reuse_base_class_padding` caveat from section 2.

### The zero-risk alternative, also built

`~/src/bb-havok/patch_hkx.py` is a byte-exact in-place editor. It never moves
anything, so all section headers, fixup tables and object offsets stay valid, and
the file keeps `reuse_base_class_padding = 1`. Proven:

```
no-op rewrite byte identical: True   5015744 == 5015744
demo edit (animationName a029_005000 -> a029_004002, same length):
   size unchanged, 2 bytes differ, reparses to the same 12,970 objects
```

`make_candidate.py` uses it for the crude version of the same idea: it rewrites
**one global fixup entry** so state 11 `Dash` uses the existing
`Run ManualSelectorGenerator` instead of `Dash CustomManualSelectorGenerator`.

```
global fixup @0x488650: src 0x19cab8  dst 0x19cfe0 -> 0x18a9f0
VERIFY Dash.generator -> hkbManualSelectorGenerator 'Run ManualSelectorGenerator'
size same: True   differing bytes: 3   items: 12970
```

Sideways sprint then looks right, but forward sprint loses its dash animation too.
Three bytes, no layout change, trivially reversible. Try this one first if the
repacked file misbehaves.

### Files, none of them installed

```
~/couch/data/bb-hks/anibnd/
  hkx/Behaviors__c0000.hkx        extracted behaviour graph (5,015,744 B)
  hkx/c0000_behavior.hkx          working copy
  hkx/c0000_behavior.xml          full unpacked XML (13,747,565 B)
  hkx/c0000_behavior.repack.hkx   no-edit round trip, semantically exact
  hkx/c0000_behavior.dirdash.xml  the edited XML
  hkx/c0000_behavior.dirdash.hkx  packed, verified (5,029,008 B)
  hkx/c0000.hkx                   Export\c0000.hkx, round-trips byte-identical
  hkx/Characters__c0000.hkx, hkx/skeleton.HKX
  tae_list.txt                    80 .tae entries with ids and sizes
  graph_variables.txt             83 variables, indexed
  graph_events.txt                1,109 events, indexed
  graph_statemachines.txt         all 62 state machines
  graph_move_statemachine.txt     Move StateMachine, states + transitions
  graph_locomotion_animations.txt the direction/animation table
  graph_locomotion_trees.txt      full generator trees
  graph_cmsg_animids.txt          CMSG animId / offsetType cross-check
  graph_dirdash_verify.txt        verification of the edited graph
  c0000.roundtrip.anibnd.dcx      unmodified repack (content-identical)
  c0000_behavior.candidate.hkx    the 3-byte in-place edit
  c0000.CANDIDATE.anibnd.dcx      3-byte edit, repacked   (2,699,543 B)
  c0000.DIRDASH.anibnd.dcx        full direction-aware dash (2,700,236 B)

~/src/bb-havok/    pf.py graph.py sms.py move.py inv.py gens.py cmsg.py
                   patch_hkx.py make_candidate.py xml_edit.py verify_dirdash.py
                   classxml-bb/ (1,362 Bloodborne-corrected class defs)
                   override/    (classpath overlay: classxml + classxmllist)
                   hkxpack-souls-cli.jar
~/src/hkxpack-plus/    HkxPack-Plus (reader good, writer broken here)
~/src/hkxpack-bin/     Dexesttp release jar
~/src/hkxpack/, ~/src/hkxpack-aerisarn/   source clones
```

### Missing packages

**None.** Everything above ran on the installed OpenJDK 21 and system Python. No
sudo was needed and none is needed to repeat it. `dotnet-sdk-8.0` remains the only
outstanding want, and only for `katalash/DSLuaDecompiler` on the `.hks` side, as
noted in `FINDINGS.md`. HKLib is not an alternative: its current releases are
Elden Ring / Nightreign only and handle neither DS3 nor Bloodborne.

---

## 6. v2: the directional dash bundle, with measured speed (2 Sep, later)

The script side is now solved in game: a 21-byte patch removing every
`or MoveDirection > 0` exit lets the player dash while locked on and pushing
sideways, and the engine reports the sprint speed level off-axis. Direction is
therefore entirely the graph's job, which is what v2 builds.

### Speed ratio: measured, not guessed

The extracted-motion track **is** readable. `soulstruct-havok` 1.2.2 loads the
animation hkx fine (it only lacks `hkb*` behaviour types, not animation types):
`hkaSplineCompressedAnimation.extractedMotion` is an
`hkaDefaultAnimatedReferenceFrame` whose `referenceFrameSamples` give the root
translation. Ground speed is (last sample - first sample) / `duration`, measured
over every weapon set present. Saved as `anibnd/rootmotion_measurements.txt`.

| animId | what | sets | duration | distance | units/s |
|---|---|---|---|---|---|
| 005200 | DashStart | 10 | 0.800 | 4.000 | **5.000** |
| 005000 | Dash loop | 9 | 0.667 | 4.319 | **6.478** |
| 006700 | DashEnd | 9 | 1.000 | 1.100 | **1.100** |
| 004000 | RunFront | 20 | 0.800 | 3.202 | 4.002 |
| 004001/2/3 | Run Back/Left/Right | 18 each | 0.733 | 2.776 | **3.786** |
| 006601/2/3 | RunEnd Back/Left/Right | 9 each | 0.83-1.17 | 0.17-0.40 | 0.18-0.40 |

Every clip is identical to two decimal places across all weapon sets (min == max
in the table), so the ratio is not an average over noisy data.

```
RATIO = 6.4782 / 3.7855 = 1.711340
```

Checked first that this is meaningful: **every** clip generator involved
(005000, 005200, 006700, 004000, 004001/2/3) already has `playbackSpeed = 1.0`
and `MODE_LOOPING` (006700 is `MODE_SINGLE_PLAY`), so the measured root motion is
the in-game speed and the multiplier applies directly.

### What v2 adds

`~/src/bb-havok/xml_edit_v2.py`. **96 new objects**, verified by reparsing the
packed binary (`anibnd/graph_dirdash2_verify.txt`):

```
objects 12970 -> 13066 (+96)
class delta: hkbClipGenerator +87, CustomManualSelectorGenerator +3,
             hkbManualSelectorGenerator +3, hkbVariableBindingSet +3
transitions 754, non-null conditions: 0
event + variable tables identical: True
```

- **87 new `hkbClipGenerator`**: the 29 children of each of `RunBack Normal Light`
  (#4348), `RunLeft Normal Light` (#4378) and `RunRight Normal Light` (#4408),
  cloned verbatim with only two changes: `playbackSpeed` 1.0 to **1.711340**, and
  `_DashSpd` appended to the name. `animationName`, `mode`, `flags`, `startTime`,
  `enforcedDuration`, crop times, `animationBindingIndex` and the null `triggers`
  are all untouched. All 87 originals were confirmed to have null triggers first,
  so nothing had to be shared or rebuilt.
- **3 new `CustomManualSelectorGenerator`** `DashStrafeBack` / `DashStrafeLeft` /
  `DashStrafeRight`, cloning the originals' `offsetType`, `animId`,
  `animeEndEventType`, `enableScript`, `enableTae`, `userData` and transition
  effect, pointing at the new clips.
- **3 new `hkbManualSelectorGenerator` + 3 `hkbVariableBindingSet`**, each binding
  `selectedGeneratorIndex` to variable **14 `MoveDirection`**, wired onto the
  three states:

```
[10] DashStart  F #4460 DashStart CMSG (5200, speed 1.0)  B/L/R DashStrafe* (speed 1.7113)
[11] Dash       F #4481 Dash CMSG      (5000, speed 1.0)  B/L/R DashStrafe* (speed 1.7113)
[12] DashEnd    F #4499 DashEnd CMSG   (6700, speed 1.0)  B/L/R RunEnd Back/Left/Right (stock)
```

**DashStart and Dash share one set of sped-up strafe generators at 1.7113.** The
alternative was a per-state ratio (DashStart's own forward speed is 5.000, giving
1.3206), but the sideways clip is a *looping* strafe rather than an acceleration
clip, so changing speed between DashStart and Dash would put a visible speed pop
mid-stride. One shared speed is smoother, and the error is confined to the 0.8 s
startup.

**DashEnd sideways reuses the stock `RunEnd` strafe CMSGs unchanged.** Those are
real deceleration animations that plant the foot, which is exactly what is wanted,
and they are near in-place (0.17 to 0.40 units total) so speeding them up would
add nothing. No new objects were needed for DashEnd.

Forward sprint is bit-for-bit untouched in all three states.

### Stamina: the sideways sprint will be free, and that is a balance change

Asked, and answered from the TAE tables. soulstruct's own TAE reader is broken by
a `constrata` version mismatch (`TypeError: rstrip arg must be None or str` at
import), so `~/src/bb-havok/tae_read.py` hand-rolls the same structs from
soulstruct's layout definitions. Dump: `anibnd/tae_dash_vs_run_events.txt`.

```
a00.tae, anim 5000 (Dash):       DisableStaminaRegen 0.000 -> 1.467
                                 CreateSpEffect1 391  0.000 -> 0.833
                                 CreateSpEffect1 210  0.000 -> 0.833
a00.tae, anim 5200 (DashStart):  DisableStaminaRegen, CreateSpEffect1 210 and 391
a00.tae, anim 6700 (DashEnd):    DisableStaminaRegen 0.000 -> 0.333
a00.tae, anims 4000/4001/4002/4003 (run + strafes):  NONE of the above
```

So **yes**, the dash's stamina behaviour is carried as TAE events on the dash
animations, and the run strafes carry none of them. Because a
`CustomManualSelectorGenerator` looks up TAE by its own `animId`, and the new
`DashStrafe*` selectors keep `animId` 4001/4002/4003, a sideways sprint in this
build will fire the run strafe's TAE: **no `DisableStaminaRegen`, and neither
SpEffect 210 nor 391.** Sideways and backward sprinting will cost no stamina and
will regenerate stamina while sprinting. Not fixed here, as instructed.

### Before installing

1. **Sideways sprint is free.** See above. It is a real balance change, not a
   cosmetic one, and it also means SpEffects 210 and 391 never fire off-axis, so
   anything else keyed to them is absent too.
2. **The `reuse_base_class_padding` caveat from section 2 still applies.** The
   packed file declares `0` where the shipped file declares `1`. Header byte 18.
   Self-consistent and it should load, but it is untested on hardware or emulator.
3. **Needs the script patch.** Without the `.hks` gate removed, none of this is
   reachable and the bundle is inert.
4. The sideways legs run at 1.71x cadence. The ground speed is right by
   construction; the stride will read as fast. That is inherent to reusing a run
   clip, since no dash strafe animation exists.
5. `c0000.DIRDASH.anibnd.dcx` (v1) is superseded. It pointed `Dash` at the whole
   `Run ManualSelectorGenerator` at normal speed, so it also lost the forward
   dash. Use v2.

### Output

```
~/couch/data/bb-hks/anibnd/c0000.DIRDASH2.anibnd.dcx    2,702,871 bytes
    sha256 a8da7ff5b520c6438bb9f0494d804c8136bcb7f5038b71c8ac4da5fd7883351c
  hkx/c0000_behavior.dirdash2.hkx    5,070,352 bytes  (behaviour entry)
  hkx/c0000_behavior.dirdash2.xml    the edited XML
  rootmotion_measurements.txt        the speed table above
  tae_dash_vs_run_events.txt         the TAE stamina evidence
  graph_dirdash2_verify.txt          reparse of the packed binary
  anim/                              the animation hkx measured (150 files)
~/src/bb-havok/xml_edit_v2.py  motion_all.py  tae_read.py  verify_v2.py
```

Nothing is installed. Game files verified bit-identical to session start.

---

## 7. v3: byte-exact packing, after DIRDASH2 crashed the game

DIRDASH2 crashed. The modded anibnd opened and closed normally, then the process
died silently a few hundred file loads later while loading armour parts, with no
exception. That is the signature of heap corruption seeded earlier, and the
`reuse_base_class_padding` mismatch I flagged is the obvious candidate: the whole
behaviour graph was re-laid-out by a packer that declares a layout it does not
produce.

### Route taken: (c), an append-style in-place editor

Routes (a) and (b) were looked at and rejected. HKXPack-Plus does have a
`ps4Layout` flag on the write side, but what it does is:

```java
if (ps4Layout && object.getDescriptor().isExtendsReferencedObject() && lastOffset >= 16) {
    lastOffset -= 4;
}
```

That is a guess, not the reuse-base-class-padding rule, which is that a derived
class's first member may begin inside the tail padding of its base and therefore
depends on the whole base chain, not on a flat 4 bytes. hkxpack-souls has no PS4
write path at all and simply stamps the flag as 0. Fixing either properly means
reimplementing Havok's layout algorithm inside someone else's Java, which is a
poor thing to be doing while chasing a crash.

`~/src/bb-havok/append_hkx.py` instead keeps every stock byte. It parses the
section table and the three fixup tables, holds the stock `__data__` region and
the stock fixup entries verbatim, appends new objects, arrays and strings past
the end of the data region, appends new fixup entries, and rewrites only the
`__data__` section header's five region offsets. Nothing that already exists
moves by a single byte, so all 12,970 stock objects keep their shipped layout and
the header keeps `reuse_base_class_padding = 1`.

Details that had to be measured from the stock file first:

- Each fixup region is padded up to a 16-byte boundary with `0xff`, and the pad is
  never zero length: `pad = 16 - (size % 16)`, or 16 if that is 0. The stock
  counts (24,555 local, 13,394 global, 12,970 virtual) each land 8 bytes short of
  a boundary, which is exactly the 8 bytes of `0xff` the file carries.
- Local fixups are **not** sorted by source, so entries can simply be appended.
- Global fixups all carry section index 2 (`__data__`); virtual fixups carry
  section index 0 (`__classnames__`) and store the offset of the class name.
- `hkArray` is pointer(8) + size(4) + (capacity | 0x80000000)(4).
- Strings are never shared in the stock file (24,555 local fixups, 24,555 distinct
  destinations), so every new object gets its own string rather than borrowing one.
- Object sizes come from the DS3 classxml and were validated against the fixup
  tables: the maximum pointer offset inside any `hkbClipGenerator` is 152 (size
  352), inside any `CustomManualSelectorGenerator` is 168 (size 256), inside any
  `hkbManualSelectorGenerator` is 176 (size 216).

**Proof, the gold standard asked for:**

```
$ cmp c0000_behavior.hkx c0000_behavior.noop3.hkx
IDENTICAL (5015744 bytes)
```

A build with no additions reproduces the stock packfile byte for byte.

### The BND payload was byte-exact too, and soulstruct was wrong about it

Worth noting because it is a second, independent deviation that was shipping in
v1 and v2. The BND4 header field at 0x28 is **the end of the UTF-16 name table**
(0x34b4), not the first entry's data offset. Entry data actually starts at
`align16(0x34b4) = 0x34c0`, and every entry is laid out back to back on a 16-byte
boundary. soulstruct starts the first entry at 0x34b4 directly, which shifted
every data offset by 12 bytes and changed the file's padding by 894 bytes.

`~/src/bb-havok/bnd4.py` implements the real rule:

```
$ cmp stock.bnd ROUNDTRIP3.bnd
IDENTICAL   (18,850,240 bytes)
```

### v3 content, identical to v2

`~/src/bb-havok/build_v3.py`. Rather than constructing objects from scratch, it
**clones** stock ones, which keeps every non-pointer field automatically correct:

- 87 `hkbClipGenerator`, byte-for-byte copies of the 29 children of each of
  `RunBack` / `RunLeft` / `RunRight Normal Light`, with a new name string, a new
  `animationName` string and `playbackSpeed` 1.711340. Asserted first that every
  source clip has null `triggers` and zeroed pointer slots.
- 3 `CustomManualSelectorGenerator` (`DashStrafeBack/Left/Right`), copies of the
  run strafe selectors with a new name and a new 29-pointer generators array,
  replicating the source's `generatorChangedTransitionEffect`.
- 3 `hkbManualSelectorGenerator` + 3 `hkbVariableBindingSet`, cloned from the
  stock `Run Normal Light Direction ManualSelectorGenerator` and its binding set,
  which already binds `selectedGeneratorIndex` to variable 14 `MoveDirection` and
  already has four children. Only the name, the binding-set pointer and the four
  child pointers are new. `generatorChangedTransitionEffect` is left null to match
  v2 exactly, which is a proven-legal configuration (102 of the 419 stock
  `hkbManualSelectorGenerator` objects have it null). Deliberately not "improved",
  so that packing method is the only variable against v2.

Verification by reparsing the packed binary (`anibnd/graph_dirdash3_verify.txt`):

```
reuse_base_class_padding: stock=1 v3=1
objects 12970 -> 13066 (+96)
class delta: hkbClipGenerator +87, CustomManualSelectorGenerator +3,
             hkbManualSelectorGenerator +3, hkbVariableBindingSet +3
fixups local 24555->24747  global 13394->13499  virtual 12970->13066
transitions 754, non-null conditions 0
event + variable tables identical: True
all stock objects unmoved and same class: True
```

The three states resolve exactly as in v2: forward on the untouched dash CMSGs at
`playbackSpeed` 1.0 (animIds 5200 / 5000 / 6700), back/left/right on the
`DashStrafe*` selectors at 1.711340 (animIds 4001 / 4002 / 4003), and DashEnd's
sideways slots on the stock `RunEnd` strafe CMSGs.

### Outputs

```
c0000.ROUNDTRIP3.anibnd.dcx   2,699,402 B   sha256 9c68944afba1d665...
    stock hkx, stock BND payload byte-identical, only the DCX stream rebuilt
c0000.DIRDASH3.anibnd.dcx     2,702,476 B   sha256 ab158dd5e4e3d087...
    behaviour hkx 5,015,744 -> 5,057,264 B, BND payload identical up to byte 3565
hkx/c0000_behavior.dirdash3.hkx   5,057,264 B
hkx/c0000_behavior.noop3.hkx      the byte-identical no-op proof
graph_dirdash3_verify.txt         the reparse above
~/src/bb-havok/append_hkx.py  bnd4.py  build_v3.py  verify_v3.py
```

Install ROUNDTRIP3 first. It is the discriminator: its BND payload is bit-identical
to stock and its behaviour graph is the stock bytes, so if it also crashes then the
fault is our DCX compression, not the packing or the edit.

### Residual doubt

1. **The DCX deflate stream is still not stock.** For an identical payload, ours is
   2,699,402 bytes against FromSoft's 2,647,091, so they used a stronger deflate
   (zopfli or similar). Every DCX header field matches except the stored compressed
   size. The game inflates rather than compares, so this should be irrelevant, and
   ROUNDTRIP3 tests exactly this and nothing else.
2. **The crash cause is still unproven.** The padding mismatch is the best
   candidate, not a demonstrated one. v3 removes it along with the BND offset
   deviation, but if DIRDASH3 still crashes the next suspect is the edit itself,
   most likely the 87 appended clip generators.
3. **Bloodborne's `CustomManualSelectorGenerator` signature differs from DS3's**
   (0x623ce73d vs 0xff6b0824), so its true size could exceed 256. I clone 256
   bytes into a zero-filled slot, so any members beyond that read as null. The
   measured maximum pointer offset inside a stock CMSG is 168, so anything past it
   is non-pointer, but this is the one place where the layout is inferred rather
   than proven.
4. **Nothing here is play-tested,** and the stamina finding from section 6 still
   stands: sideways sprint costs no stamina.

---

## 8. v4: why v3 loaded cleanly and still did nothing

ROUNDTRIP3 and DIRDASH3 both load and play with no crash, so the byte-exact append
method and the BND writer are settled and the game accepts the 96 appended objects.
But the locked-on sideways dash was unchanged. Here is why.

### The traced live chain

Traced from `hkbBehaviorGraph` using the global fixup table as ground truth rather
than class offsets, because `hkbBehaviorGraph` turned out to be one of the classes
whose Bloodborne layout is shifted from DS3's (`rootGenerator` is at +184 here, not
+192). Saved as `anibnd/graph_live_chain_trace.txt`.

```
hkbBehaviorGraph @0x60 'c0000.hkb'
 +184  hkbStateMachine @0x220 'MasterLayer'
 +352  hkbStateMachineStateInfo @0x390
 +88   hkbBlenderGenerator @0x420 'Master Blend'
 +240  hkbBlenderGeneratorChild @0x530
 +48   hkbModifierGenerator @0x580 'ModifierGenerator'
 +144  hkbStateMachine @0x1490 'Master StateMachine'
 +384  hkbStateMachineStateInfo @0x176c50
 +88   hkbBlenderGenerator @0x176ce0 'Locomotion Blend'
        child[0] weight 1.0  worldFromModelWeight 0.0  -> hkbStateMachine 'Upper'
        child[1] weight 1.0  worldFromModelWeight 1.0  -> hkbStateMachine 'Lower'
```

13,065 of the 13,066 objects are reachable, the new selectors among them, each
correctly referenced from a state info at +88. There are no duplicate fixup
sources (0 duplicate global srcs, 0 duplicate local srcs), so the loader is not
applying a stale stock entry over the appended one. The wiring was never the
problem.

### The verdict: there are two locomotion state machines, and I edited the wrong one

`Locomotion Blend` blends an **Upper** layer and a **Lower** layer, split by bone
weights. The Lower child is the one with `worldFromModelWeight = 1.0`, so it owns
the legs and the root motion, which is to say everything you can actually see.

```
'Upper' state 0 'LocomotionUpper'  -> hkbStateMachine 'Move StateMachine'
'Lower' state 0 'LocomotionLower'  -> hkbStateMachine 'Move StateMachine_mirror'
```

Both machines have the same seven states, and for Walk, Run, RunEnd and WalkEnd
they **share the very same generator objects** (both point at `0x17d480`,
`0x18a9f0`, `0x1a0360`, `0x177600`), which is why the stock direction selectors
work in both layers from one object. But the state infos themselves are separate
objects, and v3 retargeted only the Upper set:

```
Move StateMachine          Dash  info@0x19ca60  -> 0x454160  (v3's new selector)
Move StateMachine_mirror   Dash_mirror info@0x2c41c0 -> 0x19cfe0  (STOCK forward CMSG)
```

So v3 gave the upper body a direction-aware dash and left the legs and the root
motion on the stock forward clip. Nothing visible changed, exactly as reported.
The fix is to retarget both state infos to the same selector, which is precisely
the sharing pattern the stock Walk and Run states already use.

### Flag values, all correct already

`anibnd/graph_selector_flags.txt`. The v3 clones matched the stock direction
selectors on everything that governs re-evaluation:

| selector | selectedGeneratorIndex | indexSelector | selectedIndexCanChangeAfterActivate | generatorChangedTransitionEffect | endOfClipEventId |
|---|---|---|---|---|---|
| Run Normal Light Direction | 0 | null | **True** | hkbBlendingTransitionEffect | -1 |
| Walk / RunEnd / WalkEnd Direction | 0 | null | **True** | hkbBlendingTransitionEffect | -1 |
| v3 DashStart / Dash / DashEnd Direction | 0 | null | **True** | **null** | -1 |

Binding on all of them, stock and cloned: `memberPath = "selectedGeneratorIndex"`,
`variableIndex = 14` (MoveDirection), `bitIndex = -1`, `bindingType = 0`
(BINDING_TYPE_VARIABLE). So the latch-at-activation theory is ruled out:
`selectedIndexCanChangeAfterActivate` is True on the clones, inherited from the
template. There is no `hkbEvaluateExpressionModifier` or any other extra machinery
on the stock direction selectors.

Index order, confirmed from the Run selector's children: **0 Front (4000), 1 Back
(4001), 2 Left (4002), 3 Right (4003)**, which is what the clones use.

The one real gap was `generatorChangedTransitionEffect`, null on the v3 clones
because I kept strict v2 parity. It is not why v3 did nothing, but it would have
made direction changes mid-dash a hard cut instead of a blend. v4 sets it to the
same `hkbBlendingTransitionEffect` object all four stock direction selectors share.

### v4 and the diagnostic

`~/src/bb-havok/build_v4.py`, same byte-exact append method, same 96 objects,
two changes:

1. Both layers retargeted. `DashStart`/`Dash`/`DashEnd` and
   `DashStart_mirror`/`Dash_mirror`/`DashEnd_mirror` all point at the same three
   new selectors.
2. `generatorChangedTransitionEffect` set to the stock blending effect.

`--diag` additionally points the Dash selector's **forward** slot (MoveDirection 0)
at `DashStrafeLeft`. It is built on the v4 base, not v3, so the test is
unambiguous: with DIAG installed, an ordinary **unlocked forward sprint** should
visibly play a left-strafe animation at 1.71x. If it looks normal, the game is not
reaching our objects at all and the remaining suspect is the CMSG layout inference
from section 7. If it strafes, our objects are live and any residual problem is the
runtime value of MoveDirection during a dash.

Verification of both (`anibnd/graph_dirdash4_verify.txt`): `reuse_base_class_padding`
1, 12,970 to 13,066 objects, same class delta, all stock objects unmoved and same
class, 754 transitions with 0 conditions, and both `Move StateMachine` and
`Move StateMachine_mirror` resolving through the new selectors with
`canChange=True` and the blending transition effect.

### Outputs

```
c0000.DIRDASH4.anibnd.dcx   2,702,486 B   sha256 11692991803e7ae1...
c0000.DIAG.anibnd.dcx       2,702,483 B   sha256 87f1b5e4553fa450...
hkx/c0000_behavior.dirdash4.hkx  5,057,296 B   sha256 5ad7cd19e140b3fe...
hkx/c0000_behavior.diag.hkx      5,057,296 B   sha256 840135bd96e09bea...
graph_live_chain_trace.txt  graph_layer_split.txt
graph_selector_flags.txt    graph_dirdash4_verify.txt
~/src/bb-havok/build_v4.py  trace3.py  layers.py  flags.py  verify_v4.py
```

Install DIRDASH4. Keep DIAG for the case where it still does nothing. The stamina
finding from section 6 is unchanged: sideways sprint costs no stamina.

---

## 9. v5 and v6: the sideways slots resolve to nothing

DIRDASH4 proved the selector is live, because the forward dash stopped happening
off-axis. But the sideways and back slots produce no movement at all, so whatever
they resolve to is not playing.

### H1, clip names: the strongest suspect, and my `_DashSpd` suffix broke the format

`anibnd/graph_clip_naming.txt`. Across all 7,784 stock `hkbClipGenerator` objects:

- **7,606 follow `<animationName>_hkx_AutoSet_NN` exactly.** The other 178 follow
  `<animationName>.hkx` (some with a space instead of the underscore, e.g.
  `a000 000000.hkx`). There is no third form.
- **The name prefix equals `animationName` in every single case. Zero mismatches.**
- **Zero duplicate names in the whole file**, while `animationName` is reused
  freely: 6,426 distinct animation names across 7,784 clips, one reused six times.
  The `_AutoSet_NN` index is what disambiguates them, and it really is used as a
  counter: 6,160 clips at `_00`, 778 at `_01`, 418 at `_02`, down to two at `_20`
  and `_21`.

So the name is a structured, globally unique key that carries the animation id in a
fixed position, and the suffix is a numeric index rather than free text. My clones
were named `a000_004002_hkx_AutoSet_00_DashSpd`, which is not a form that occurs
anywhere in the shipped file. If FromSoft's CMSG resolves its child by parsing or
matching that name, the clones resolve to nothing, which is exactly the symptom.
This is the leading hypothesis.

### H2, CMSG fields: my clones were faithful, but the DashStart slot is wrong anyway

Every field on the cloned CMSGs is byte-identical to its source, including the one
that matters most:

```
                                    offsetType animId animeEndEventType script tae changeType TE
Dash CustomManualSelectorGenerator      11      5000        2            1    1     1      0x4990
DashStart CustomManualSelectorGenerator 11      5200        0            1    1     1      0x4990
DashEnd CustomManualSelectorGenerator   11      6700        2            1    1     1      0x4990
RunLeft / RunBack / RunRight Normal     11    4002/1/3      2            1    1     1      0x4990
```

`animId` is preserved (4001 / 4002 / 4003), `offsetType` is `IdleCategory` on all of
them, so the engine builds the real animation id the same way for a clone as for the
original.

But note the one genuine mismatch, which is **not** about the clones and applies to
v5 too: `DashStart`'s own CMSG has `animeEndEventType = 0` (**FireNextStateEvent**),
which is what drives `DashStart -> Dash`, while every run strafe CMSG has
`animeEndEventType = 2` (**FireIdleEvent**). So a sideways DashStart fires an idle
event at clip end instead of advancing to Dash, and the state machine can be kicked
out of the dash chain entirely. That is an independent candidate cause of "no
movement" and it survives in both v5 and v6. Flagging it rather than fixing it,
since changing it as well would confound this round of testing.

### H3, clip flags: clean, nothing there

Every clip in the Dash CMSG and in all three run strafe CMSGs has an identical
tuple:

```
playbackSpeed 1.0, mode MODE_LOOPING(1), flags 0, animationBindingIndex -1,
startTime 0.0, enforcedDuration 0.0, triggers null
```

`flags = 0` everywhere, so no `FLAG_IGNORE_MOTION` and no mirror or sync bit is
involved, and the clones differ from their originals in `playbackSpeed` and nothing
else.

### The two bundles

Both by the byte-exact append method, both retargeting the Upper and Lower state
machines as v4 does, both with `generatorChangedTransitionEffect` set to the stock
blending effect.

- **v5, the minimal one.** No clones at all. Only 6 new objects (3 selectors, 3
  binding sets); the sideways and back slots point straight at the **stock**
  `RunBack` / `RunLeft` / `RunRight Normal Light` CMSGs at speed 1.0. Verified:
  12,970 to 12,976 objects, delta `hkbManualSelectorGenerator +3`,
  `hkbVariableBindingSet +3`, 754 transitions, 0 conditions. If this moves, the
  clones are the fault and the speed multiplier has to come from somewhere else.
- **v6, the naming test.** The 96-object build again, but every cloned clip
  generator and cloned CMSG carries the **exact** stock name and animationName,
  with `playbackSpeed` the only difference. Verified: 12,970 to 13,066 objects,
  same class delta as v4, sideways slots reading speed 1.711340. This deliberately
  introduces duplicate names, which the stock file never has, so if it works the
  follow-up is to bump the `_AutoSet_NN` index instead (unique and still parseable)
  rather than leave duplicates in place.

```
c0000.DIRDASH5.anibnd.dcx   2,699,674 B   sha256 7e3d1bc1d19aeba4...
c0000.DIRDASH6.anibnd.dcx   2,702,518 B   sha256 ecb8c70e07ff8a85...
hkx/c0000_behavior.dirdash5.hkx  5,017,376 B   sha256 c617e4dd91ba7085...
hkx/c0000_behavior.dirdash6.hkx  5,057,344 B   sha256 674fcbf0132c09e4...
graph_clip_naming.txt   graph_dirdash56_verify.txt
~/src/bb-havok/build_v56.py  names.py
```

Test v5 first: it is the one that isolates the clones from everything else.

---

## 10. v7: the one field that mattered

DIRDASH5 confirmed the diagnosis. Locked on and pushing sideways with circle held,
the player just strafes at normal speed and only dashes once the stick goes forward.
The selector is live and the sideways slots resolve to a real, moving animation, so
clip naming (section 9, H1) was **not** the fault after all. The machine simply
never advances out of DashStart.

### Field-by-field CMSG comparison

`anibnd/graph_cmsg_field_diff.txt`. Every member of `CustomManualSelectorGenerator`,
compared across the three dash CMSGs and the three run strafe CMSGs:

```
                          DashStart  Dash   DashEnd  RunLeft  RunBack  RunRight  RunEnd L/B/R
userData                  18087939   ...40  ...41    18087938 18087938 18087938  18087942
generators.count          15         13     13       29       29       29        13
offsetType                11         11     11       11       11       11        11
animId                    5200       5000   6700     4002     4001     4003      6602/1/3
animeEndEventType         0          2      2        2        2        2         2
enableScript              1          1      1        1        1        1         1
enableTae                 1          1      1        1        1        1         1
changeTypeOfSelected...   1          1      1        1        1        1         1
generatorChangedTE        0x4990     0x4990 0x4990   0x4990   0x4990   0x4990    0x4990
checkAnimEndSlotNo        0          0      0        0        0        0         0
replanningAI              0          0      0        0        0        0         0
```

The differences, per pair:

- **DashStart forward vs run strafe**: `userData`, `generators.count`, `animId`, and
  **`animeEndEventType` 0 (FireNextStateEvent) vs 2 (FireIdleEvent)**. A raw byte
  diff of the whole 256-byte object, excluding the pointer slots and the array
  header, differs at exactly four offsets: 48 (`userData`), 156 and 157 (`animId`),
  and 160 (`animeEndEventType`). Nothing else in the class differs at all.
- **Dash forward vs run strafe**: `userData`, `generators.count`, `animId` only.
  `animeEndEventType` already matches at 2.
- **DashEnd forward vs RunEnd strafe**: `userData` and `animId` only.
  `animeEndEventType` already matches at 2.

`userData` is an editor id (a dense counter, 18087938 to 18087942 across these
seven objects) and is left as the strafe's. So exactly one functional field needed
changing, and only for DashStart.

### What v7 changes

- **87 sped-up clip clones, shared** by both CMSG sets. Sharing a generator between
  two simultaneously active parents is the stock pattern: `Run ManualSelectorGenerator`
  is already used by the Upper and Lower state machines at the same time.
- **Names in the exact stock form.** Each clone is
  `<animationName>_hkx_AutoSet_NN` with NN the lowest index not already used by any
  stock clip of that animation, so they all came out `_01`. Verified: **0 duplicate
  names across all 11,049 named objects**, preserving the stock invariant, and 0 new
  clips whose name fails to encode its animationName (the 149 stock oddities like
  `a123_52901` are pre-existing and untouched).
- **Two CMSG sets, not one.** `Run{Back,Left,Right} Normal Light DashStart` with
  `animeEndEventType = 0`, and `Run{Back,Left,Right} Normal Light Dash` with it left
  at 2. Everything else, `animId`, `offsetType`, `enableScript`, `enableTae`,
  `changeType`, the transition effect, is the strafe's.
- **DashEnd unchanged from v4**: the stock RunEnd strafe CMSGs, since the comparison
  says nothing there matters for the chain.
- Both state machines retargeted, `generatorChangedTransitionEffect` set as in v4.

### Verification

```
reuse_base_class_padding: stock 1, v7 1
objects 12970 -> 13069  delta hkbClipGenerator +87, CustomManualSelectorGenerator +6,
                              hkbManualSelectorGenerator +3, hkbVariableBindingSet +3
stock objects unmoved and same class: True
transitions 754, non-null conditions 0
named objects 11049, duplicate names: 0
new clip names: a000_004001_hkx_AutoSet_01 ...   all speeds 1.711340
DashStart sideways slots animeEnd=0   Dash sideways slots animeEnd=2
both Move StateMachine and Move StateMachine_mirror resolve through the new selectors
```

### Output

```
c0000.DIRDASH7.anibnd.dcx   2,702,982 B   sha256 3631afb8da06a440...
hkx/c0000_behavior.dirdash7.hkx  5,060,096 B  sha256 51a884d7d1bbd260...
graph_cmsg_field_diff.txt   graph_dirdash7_verify.txt
~/src/bb-havok/build_v7.py  cmsg_diff.py  verify_v7.py
```

If the sideways dash now engages but the speed feels wrong, `playbackSpeed` is a
one-number change in `build_v7.py`. The stamina finding from section 6 is unchanged:
sideways sprint still costs no stamina, because the clones keep `animId` 4001/4002/4003
and so fire the run strafe TAE.

