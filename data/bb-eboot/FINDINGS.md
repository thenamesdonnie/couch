# Bloodborne eboot (1.09) findings, 2 Sep 2026 evening

Written from the reverse-engineering subagent's report (its own write was
blocked). Tooling: `bbeboot.py` in this directory; command table in
`script_commands.md`.

## Address mapping
PS4 SELF, ELF header at file 0x120. ELF p_offset fields are WRONG; the SELF
segment table holds the real file positions. phdr0 r-x VA 0 -> file = VA +
0x28eb0; phdr1 rw- VA 0x50dc000 -> file = VA + 0x27df0; .bss from VA 0x53e5b38.
Runtime = 0x800000000 + VA. Cheat-JSON offset == module VA; bb-cheat's XML
Address = VA + 0x400000. Verified against six known cheat "original bytes".

## Script command tables (the env/act API)
Pointers in .data are zero on disk and materialised from R_X86_64_RELATIVE
addends (236,517 relocs at file 0x5410490), so a byte search for pointers finds
nothing; resolve through the reloc index. Entry = {uint64 id, wchar_t* name}.
act: base 0x5334490, 56 entries. env: base 0x5334810, 129 entries. 185 commands;
the shipped script calls 86. Dispatch is by id through std::maps
(0x557a278 / 0x557a2d8), so there is no handler pointer array to walk.
Hidden commands of interest: act 52 "表示方向をY軸中心に固定" (fix the DISPLAYED
facing about Y), act 53 "特殊移動切替", act 13 "旋回アニメ補正率を計算", act 34
"頭旋回可能か", env 50 "新ロック状態取得", env 48/49 lock distance/angle state,
env 112 "移動タイプ取得". Argument counts unknown without a disassembler.

## Facing / lock debug variables (tested 2 Sep, both NO EFFECT on sprint facing)
* "操作の前方向とカメラ前方向を一致させない": bool at VA 0x555428c (.bss, default
  0); consumer 0x1528c64 latches the control-forward yaw instead of tracking
  the camera. Loads fine as a cheat; no change to locked-on running.
* "新ロック制御使うか": byte at VA 0x5128330 (file 0x5150120), default 01 = the
  new lock control. Set to 00: loads fine, no change to locked-on running.
  (The first attempt crashed, but that launch also carried the official
  cheat file's "master" hook, which is what crashed; see below.)
* "見た目/移動方向をY軸中心に回転するか" and "移動中に旋回アニメを実行できるか" are
  INSTANCE fields (+0x326/+0x327 of the HavokChara debug struct; +0x40 of
  another object), not globals: not statically patchable.
* Tunables, file-backed floats at VA (add 0x27df0 for file): 0x5127b34=85.0
  turn-anim start angle while moving, 0x5127b38=1.25, 0x5127b3c=1.75,
  0x5127b40=0.5 dash turn-anim threshold (read at 0x151fa36/0x151fc67),
  0x5127b48=0.4 dash button window, 0x5127b50=0.2, 0x5127b54=0.12, 0x5127b58=60.
* The locomotion controller (this of 0x15363b0, debug menu 0x1536200) holds
  the real facing rules as instance fields: +0x1d8 Turn Gain, +0x1dc/+0x1e0
  Forward Limit/Margin Angle, +0x1e4/+0x1e8 Back Limit/Margin Angle,
  +0x1ec/+0x1f0 Dash Threshold(+Margin), +0x254 UpperBody Rotation Rate,
  +0x194 dash time, +0x198 run-to-turn time, +0x240 Dash To Walk Limit Time.
  Changing these needs a CODE patch (their initialisation or the consumer),
  which needs ghidra or radare2 (both installable under ~/src without sudo;
  Java 21 is present).

## The master-hook crash
bb-cheat adds the official cheat file's "master" hook whenever any cheat is
on. On 2 Sep two launches with it crashed at world load (last file opened:
map/m32/gi_env_m32.tpfbdt); the same flags without the hook loaded fine. So
the Infinite Health / Stamina / 1 Hit Kill cheats (which need the hook) will
crash too until the conflict is found. They worked on 31 Aug; suspects are
the performance patch set and the 60 fps patches enabled since. Our flag
entries are marked "standalone" in the JSON and bb-cheat skips the hook for
them.

## Bottom line
No global switch gives Elden Ring's locked-on sprint. The facing rule lives on
the per-character locomotion controller; the remaining route is a code patch
found with a real disassembler.

## 3 Sep 2026 (small hours): the facing rule, found with Ghidra, and the patch

Tooling now: Ghidra 12.1.3 at `~/src/ghidra_12.1.3_PUBLIC`, project
`~/src/bb-ghidra` (`full` = fully analysed, ~30 min; `quick` = no analysis).
`mkelf.py` here turns the fake SELF into a plain ET_DYN ELF at base 0 with
the 231,478 RELATIVE relocations pre-applied, so vtables resolve statically.
Helpers in `~/src/bb-ghidra`: `gq <Script> args` runs a script against the
full project (`XrefsTo`, `DecompileContaining`, `DecompileAt`, `PtrsAt`,
`DecompileRange start end file`); decompiles of 0x1480000-0x1580000 are in
`dec-range-*.txt`. Ghidra missed a few vtable-only functions (e.g. 0x152b020),
`DecompileAt` creates them.

### Object model (player), all offsets verified in code
* `CC` (the script owner, `*param_1` in act/env): `+0x58` -> `ChrIns`,
  `+0xf8` locked-on flag, `+0x100` lock target position, `+0x110/0x114`
  lock angle/new-lock state, `+0x3b0` -> X; `X+0x68` -> `T` (transform:
  `+0x1d0` euler angles, `+0x1e0` position, `+0x210/0x211` dirty flags).
* `ChrIns`: `+0x8` -> CC (mutual), `+0x1c8` -> `LOCO`, `+0x244` "追加旋回不可"
  (act 14 sets it), **`+0x245` = NOT locked on** (the lock manager
  FUN_0188e900 writes `CC+0xf8=1; ChrIns+0x245=0` on lock and the reverse on
  unlock; env "ロック中か" returns `!ChrIns[0x245]` under new lock control),
  `+0x280`/`+0x80` -> `INP` (player input state / AI fallback), `+0x2a0` ->
  `ROT` (rotation controller, vtable 0x53260e0), `+0x100` local move vector.
  Player vtable 0x5370610 (base class 0x536fe80): `+0x48` getLoco,
  `+0x80` additionalTurn (FUN_0152b020), `+0xb8` applyRotation (FUN_0152b380).
* `LOCO` (vtable family 0x5370cc0, update FUN_01533940): `+0x138` move
  state (-1 none, 0 walk/run, 1 dash, 2/3 the same with the +0x140 mode;
  the engine's own "is dashing" test everywhere is `(state|2)==3`),
  `+0x194` dash time, `+0x1dc..0x1f0` the Forward/Back limit + Dash
  threshold fields (used to classify the move vector into fwd/back/side),
  `+0x23c/0x240` dash-to-walk timer/limit.
* `INP` (class vtable 0x5370430, update FUN_01526750 = slot +0x48):
  `+0x10` world move vector, `+0x20` desired rotation (relative angles),
  `+0x30` absolute target angles, `+0x40` stick, `+0x50` camera angles,
  `+0x88` -> CC, `+0x194/0x195` mode flags.

### The facing chain, per frame
1. `FUN_01526750(INP, ...)`: at its top (0x15267b3)
   `if (ChrIns+0x245 == 0 || INP+0x194) -> variant A else variant B`.
   Variant A (locked): `INP+0x30` = angles from the character to `CC+0x100`,
   `INP+0x20` = wrap(that - T angles). Variant B (unlocked): `INP+0x20` =
   the stick direction in world (camera-relative), plus the control-forward
   latch (DAT_0555428c). The stick -> world move vector uses the camera in
   BOTH variants, which is why the control frame never changes when locked.
2. `FUN_01513c10(dt, ChrIns)`: takes `INP+0x20/+0x30`, quantises the turn
   (30/60/100 deg -> 45/90/180 turn anims), adds the "additional turn" from
   vtable `+0x80` = `FUN_0152b020`, which is **only active when
   `ChrIns+0x245 != 0`** (unlocked) and not vetoed by `+0x244`.
3. `FUN_0152b380` (vtable `+0xb8`): calls `ROT->vt+0x10` (`FUN_0150e690`, the
   rate-limited turn, 720 deg/s while moving) and writes the result to
   `T+0x1d0`; afterwards copies `ChrIns+0x245` into `ROT+0x58` bit 3, which
   selects the unlocked vs locked path inside FUN_0150e690 next frame.

So the locked-on facing is not one rule but the same flag read at three
places in the movement chain. The camera lock lives in CC (+0xf8/+0x100)
and the lock manager, and none of the three sites touch it.

### The patch: "Lock-on sprint faces the stick" (v2 installed 3 Sep ~00:00; v1 verified for the sprint, then caught turning the body during a plain locked-on jog)

**v1 lesson: `LOCO+0x138 == 1` is RUN, not sprint.** Donnie: sprinting was
perfect, but "when you are jogging you aren't looking at the enemy so an
attack will miss". So the engine's `(state|2)==3` test means "moving fast",
and the real sprint signal is the circle hold: FUN_01526750 sets the sprint
flag `REQ+0x9c |= 2` exactly when `INP+0xd0` (circle hold time, reset to 0 on
release) exceeds `DAT_05127b48` (the 0.4 s "dash button window" tunable).
v2 uses that: sprinting := INP=[ChrIns+0x280] && INP+0xd0 > [0x5127b48]
(signed-int compare of the float bits, so no xmm register is touched; xmm0 =
dt is live at the second site) && LOCO state|2 == 3 (still there as the
"actually moving" guard). Caves moved to 0x50db000/50/a0. **v2 verified by Donnie** (jog strafes, sprint
turns).

**v3: no skid on release.** Donnie: "he skids if the angle changes quickly
once you let go". That is the turn-animation picker FUN_0151f500 (vtable
0x53261e0 slot 0; r14 = TURN object, TURN+8 = ChrIns, +0x28/+0x30 angle
thresholds, +0x44 dash timer, +0x3c the DASH turn anim id played when the
timer is past DAT_05127b40 = 0.5 s: the skid). Vanilla only reaches
locked + big angle + dash timer via our feature (a vanilla locked-on sprint
is forward only). v3 hooks its two "may play a turn anim" tests (r13b at
0x151f9f9 and 0x151fc2d) and takes the no-turn path when locked and the LOCO
dash time (+0x194, decays at 2x after the dash) is still > 0. Caves
0x50db0f0/0x50db130. rax is dead at both continue and no-turn targets.
`lockdash/cave.s` (source), `lockdash/cave.bin`, `lockdash/lockdash.cheat.json`
(the mod entry, installed with `bb-cheat add`, enabled with `bb-cheat on`).
While locked AND sprinting (definition above), each of the three sites
treats the character as unlocked:
* 0x15267b3 (25 bytes) -> cave 0x50db000: variant B when locked+sprinting.
* 0x152b020 (13 bytes) -> cave 0x50db050: additional turn allowed.
* 0x152b40d (6 bytes)  -> cave 0x50db0a0: ROT bit 3 = notLocked | sprinting.
Caves sit in the zero tail of the code segment (mapped, executable: the
official master hook lives at 0x50db810 in the same pages). rax is dead at
all three sites (checked in the asm); cave_c saves/restores it anyway.
Expected behaviour: lock on, hold circle, push sideways: the body turns to
the stick at the unlocked turn rate, MoveDirection goes to 0, the forward
dash clip plays (DIRDASH5 selects it), the camera stays on the target;
release circle: the body snaps back to facing the target via variant A.
Risk to watch: if LOCO+0x138 never reaches 1 while locked (the engine's own
dash classification might be vetoed some way I did not see), nothing changes
at all; that is the first thing to check, not the caves. Revert:
`tools/bb-cheat off`.

**v3 did not stop the skid; v4 (3 Sep ~01:40) fixes the real cause.** The
skid is script-driven: `Act_Turn` in c0000.hks fires `W_Turn_Dash` when the
Havok variable TurnAngle passes 90 degrees while the sprint SpEffect (390/391)
is active. TurnAngle is published by the rotation controller's UNLOCKED path
(`*(ROT+0x38)+0x24`, FUN_0150e690; the locked path writes 0 there). Frame
order inside FUN_01513c10 is: additional turn (cave_b) -> apply rotation ->
copy the lock flag into ROT+0x58 bit 3 (cave_c) -> THEN the input update
(cave_a) for the next frame. With cave_a on the live sprint state, the release
frame asked for a 180 degree turn while the controller was still in unlocked
mode for one more frame, so TurnAngle spiked and the script skidded. v4:
cave_c keeps the live sprint test; cave_a and cave_b follow ROT+0x58 bit 3
instead. The 180 degree request now arrives one frame later, when the
controller is already back in locked mode. The v3 picker hooks (0x151f9f9,
0x151fc2d) are removed; the JSON also zeroes their old cave bytes.

**v4 stopped the turning (3 Sep ~01:50): the flag-copy hook never runs for
the player.** Two classes carry the rotation applier (+0xb8): 0x5370610
(FUN_0152b380, hooked) and 0x536fe80 (FUN_0151e6a0, whose ctor FUN_018e4870
references SprjSessionManager). v4 made cave_a follow ROT+0x58 bit 3 and the
body stopped turning, so for the player the bit is never set, i.e. the
player's rotation always ran in the LOCKED path in v2 as well, and the stick
target simply drove that path. Lesson: v2's "cave_c" and "cave_b" are inert
for the player. v5 restores v2's a/b/c exactly (known good) and fixes the
skid where it really comes from: FUN_01513c10 quantises the desired yaw
(>30/60/100 deg -> 45/90/180) into [rbp-0x60] = param_5 of the rotation
applier, separate from the rotation request in [rbp-0x50] = param_4; that
value becomes the Havok TurnAngle, and the script's Act_Turn fires
W_Turn_Dash (the skid) when it passes 90 with the sprint SpEffect on. cave_e
(0x50db0f0, from 0x1513cfa) zeroes [rbp-0x60] whenever locked on, so no turn
animation is ever requested while locked; the rotation itself is unchanged.
Side effect, intended: locked-on pivots when an enemy gets behind you become
smooth rotations (Elden Ring behaviour).

**v5 still skidded (3 Sep ~02:20): TurnAngle is not the quantised angle.**
The Havok variables are published by FUN_01a18bf0 (names at 0x4992c8c..:
IsLockon, MoveAngle, MoveSpeedLevel, MoveDirection, TurnAngle; param_1+8 =
CC). IsLockon = CC+0xf8 (the camera lock flag, untouched by us). TurnAngle =
`INP+0x24 * 57.29578` (the raw desired-rotation yaw straight from the input
object, gated by ChrIns+0x1d9 and !(Y+0x10 & 4)), at 0x1a19109. So the
release frame's 180 degree request reaches the script directly and
Act_Turn fires W_Turn_Dash. v6: cave_f (0x50db0f0, 13-byte site 0x1a19109)
publishes 0 while locked on, except when idle with no recent dash (LOCO
state -1 and dash time 0) so the vanilla standing pivot survives. cave_e
removed. v6 = v2's a/b/c + cave_f.

**v6 still skidded; the skid is DashEnd, not a turn animation (3 Sep ~03:00).**
Donnie's decisive test: releasing circle with the stick still pushed gives
no skid (the script goes Dash -> Run); releasing everything skids (the
script fires "Dash to DashEnd", the 1.0 s sprint-stop slide, root motion
1.1 units, and our immediate snap-back to the target rotates it). v7:
cave_a keeps a facing-hold timer in scratch memory at 0x56d3f00 (the
zero-filled tail of the RW segment past memsz 0x56d30f4; page end
0x56d4000). Sprinting arms it to 1.0 s; when the sprint ends with the stick
released (both stick floats INP+0x40/+0x44 under 0.1) the input keeps
variant B (stick facing) and counts the timer down by dt ([rbp-0x134]);
any stick push zeroes it and the snap-back happens at once (the verified
Dash -> Run case). cave_f now publishes TurnAngle = 0 whenever locked, so
the turn after the hold is a plain rotation. Cave layout 0x50db000/c0/110/
160, older bytes up to 0x50db200 zeroed by the JSON. Lesson for next time:
ask what the stick was doing before touching the engine.

**v7 VERIFIED by Donnie 3 Sep ~03:15: "that works perfectly".** Final shape
of the feature, three layers that must stay installed together:
script LOCKSPRINT (`tools/bb-lockon-sprint install lockspint`, the trigger),
bundle DIRDASH5 (`tools/bb-anibnd-swap`, clip selection), and the cheat
"Lock-on sprint faces the stick" (`tools/bb-cheat on`, the facing: v2 hooks +
the 1.0 s facing hold through DashEnd + TurnAngle zeroed while locked).
