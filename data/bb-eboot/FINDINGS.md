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
