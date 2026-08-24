# Bloodborne Enhanced 0.11.2-fix9 — settings system, reverse-engineered

**Date:** 24 Aug 2026. **Status:** mod INSTALLED, settings left at shipped
defaults, no play-test yet.

Source archive: `~/fileshare/bloodborne-mods/BloodborneEnhanced-FullPackage19mod.0.11.2----patcher.0.5.1----fix9*.zip`
(Nexus mod 19). Installed via `bb-mod-install` as **`BloodborneEnhanced-0.11.2-fix9`**
(2422 files replaced with per-file backups, 40 added).
Revert: `bb-mod-install revert BloodborneEnhanced-0.11.2-fix9`.

## Install trap (this is why the installer refused it)

The archive's top folder holds **two** `dvdroot_ps4` trees:

- `bb_enhanced_0.11.2-fix9/GAME FILES/dvdroot_ps4/` — the real mod
- `bb_enhanced_0.11.2-fix9/OPTIONAL CHEATS/gems/dvdroot_ps4/` — a *replacement*
  `gameparam.parambnd.dcx` (all-blood-gems cheat) that would clobber the main one

`bb-mod-install` finds two roots and dies with "multiple dvdroot_ps4 folders
(variants?)" **by design** — it refuses to guess. Recipe that works:

```bash
unzip -q "<archive>.zip" "bb_enhanced_0.11.2-fix9/GAME FILES/*" -d /tmp/stage
cd /tmp/stage && zip -qr /tmp/stage/BloodborneEnhanced-0.11.2-fix9.zip bb_enhanced_0.11.2-fix9
bb-mod-install install /tmp/stage/BloodborneEnhanced-0.11.2-fix9.zip
```

No collision with the installed Vertex Explosion fix (mod 109): that touches
`parts/fg_a_*` FaceGen files, this one touches `parts/{am,bd,hd,lg}_a_4510`.

## How settings are stored

Settings are **event flags baked into `event/common.emevd.dcx`**, in event
**10008400** (163 instructions, 70 of them setting writes, all `[2003:2]`
SetEventFlag with two int32 args: `(flagId, value)`).

Each setting owns a pair of flag IDs where **Enabled = `X8yy`, Disabled = `X9yy`**
(e.g. Auto Refill: Enabled `12100862`, Disabled `12100962`). Three encodings:

- **binary** — the *flag ID itself* is swapped between the Enabled and Disabled
  value; `value` stays 1
- **multi-value / ForceRotate** — every option has its own flag; the chosen one
  gets `value=1`, the rest `value=0`
- **ActivateOnly** — flag fixed, `value` toggles 1/0

**Only the "Enabled" flag is ever tested by game logic.** The "Disabled" flag ID
is inert — it exists purely so the defaults event can park the setting on a flag
nothing reads. Verified by scanning flag usage across every event in the file.

## The official tools do not run here

`BBEnhancedSettingsGUI.exe` / `BBEnhancedPatcherGUI.exe` / `BBEnhancedInstaller.exe`
are **.NET 8 WinForms**, Windows-only. Source ships in `_src/`. Not worth a Wine
fight.

**A native Linux editor is straightforward and was proven feasible**, not built:
the DCX is plain zlib (`DCX\0` + `DCS`/`DCP`/`DCA` headers, `DFLT` format), and
every setting edit is a same-length int32 swap, so **no file re-layout is needed**.
A full decompress → repack round-trip against the live file returned a
**byte-identical payload** (the container shrinks slightly because we recompress
at level 9; sizes live in the DCS header so that is harmless).

Working parser used for this analysis (drop in a scratch dir):

```python
# dcx.py — DCX (DFLT/zlib) container
import struct, zlib
def dcx_decompress(path):
    d = open(path,'rb').read()
    assert d[:4] == b'DCX\0'
    dcsOffset, dcpOffset = struct.unpack_from('>II', d, 8)
    uncompressedSize, compressedSize = struct.unpack_from('>II', d, dcsOffset+4)
    i = d.find(b'DCA\0', dcpOffset)
    start = i + struct.unpack_from('>I', d, i+4)[0]
    raw = zlib.decompress(d[start:start+compressedSize])
    assert len(raw) == uncompressedSize
    return raw, dict(start=start, dcsOffset=dcsOffset, compressedSize=compressedSize)
```

```python
# emevd.py — 64-bit EMEVD (BB/DS3). Header: "EVD\0", 4 pad, version, fileSize,
# then 16 int64 offsets/counts. Event = 48 bytes, Instruction = 32 bytes.
import struct
class Emevd:
    def __init__(self, raw):
        self.raw = bytearray(raw); assert raw[:4] == b'EVD\0'
        (self.eventCount, self.eventOffset, self.instrCount, self.instrOffset,
         _u0, _u1, self.layerCount, self.layerOffset,
         self.paramCount, self.paramOffset, self.linkCount, self.linkOffset,
         self.argsLength, self.argsOffset, self.strLength,
         self.strOffset) = struct.unpack_from('<16q', raw, 0x10)
    def events(self):
        for i in range(self.eventCount):
            o = self.eventOffset + i*48
            eid, ic, io, pc, po = struct.unpack_from('<5q', self.raw, o)
            yield eid, ic, io, o          # paramCount/Offset live at o+24
    def instructions(self, ic, io):
        for j in range(ic):
            o = self.instrOffset + io + j*32
            bank, iid, alen, aoff, loff = struct.unpack_from('<iiqqq', self.raw, o)
            yield bank, iid, alen, self.argsOffset + aoff, o
```

Repack: recompress the payload, rewrite `uncompressedSize`/`compressedSize` at
`dcsOffset+4` (big-endian), splice between `header[:start]` and the original tail.

Parameter table (needed to read parameterised events): 32 bytes each at
`paramOffset + event.paramOffset + i*32` = `instructionIndex(q)`,
`destStartByte(q)`, `sourceStartByte(q)`, `length(i)`, `unk(i)`.

## Verified live state

All 51 settings were resolved from the **installed** `common.emevd.dcx` and
cross-checked against the mod's shipped `_data/settings.json`:
**zero mismatches, zero unmapped flags.** So the table below is ground truth for
what is baked in right now, not just what the readme claims.

| # | Setting | Default | Options | In-game? |
|---|---|---|---|---|
| 1 | Prevent Lamp Deactivation | **Enabled** | Disabled / Enabled | yes |
| 2 | Auto Refill Bullets And Vials | **Enabled** | Disabled / Enabled | yes |
| 3 | Auto-Refill: Lamp Kindling | **Disabled** | Disabled / Enabled | yes |
| 4 | Lamp Menu | **Enabled** | Disabled / Enabled | yes |
| 5 | Lamp Menu: Resting (Auto Reawaken) | **Enabled** | Disabled / Enabled | yes |
| 6 | Lamp Menu: Auto Resting | **Enabled** | Disabled / Enabled | yes |
| 7 | Lamp Menu: Warp | **Enabled** | Disabled / Enabled | yes |
| 8 | Lamp Menu: Level Up | **Enabled** | Disabled / Enabled | yes |
| 9 | Lamp Menu: Workshop | **Enabled** | Disabled / Enabled | yes |
| 10 | Lamp Menu: Memory Alter | **Enabled** | Disabled / Enabled | yes |
| 11 | Lamp Menu: Storage | **Enabled** | Disabled / Enabled | yes |
| 12 | Lamp Menu: Messengers | **Enabled** | Disabled / Enabled | yes |
| 13 | Lamp Menu: Change Appearance | **Disabled** | Disabled / Enabled | yes |
| 14 | Lamp Menu: Boss Rematches | **Enabled** | Disabled / Enabled | yes |
| 15 | Quick Warp to Bosses | **Enabled** | Disabled / Enabled | yes |
| 16 | Prompt Quick Warp to Bosses | **Enabled** | Disabled / Enabled | yes |
| 17 | Spawn Iosefka Clinic Lamp at Start | **Disabled** | Disabled / Enabled | no (file only) |
| 18 | Lamp Music | **Disabled** | Disabled / Enabled | yes |
| 19 | Broken Lamp | **Enabled** | Disabled / Enabled | yes |
| 20 | Broken Lamp: Victory Respawn Location | **Hunter's Dream** | Hunter's Dream / Boss Lamp | yes |
| 21 | Broken Lamp: Death Respawn Location | **Hunter's Dream** | Hunter's Dream / Boss Lamp | yes |
| 22 | Prime Hunter's Mark: Warp | **Enabled** | Disabled / Enabled | yes |
| 23 | Prime Hunter's Mark: Level Up | **Disabled** | Disabled / Enabled | yes |
| 24 | Prime Hunter's Mark: Workshop | **Disabled** | Disabled / Enabled | yes |
| 25 | Prime Hunter's Mark: Memory Alter | **Enabled** | Disabled / Enabled | yes |
| 26 | Prime Hunter's Mark: Storage | **Enabled** | Disabled / Enabled | yes |
| 27 | Prime Hunter's Mark: Messengers | **Disabled** | Disabled / Enabled | yes |
| 28 | Prime Hunter's Mark: Change Appearance | **Disabled** | Disabled / Enabled | yes |
| 29 | Prime Hunter's Mark: Enhanced Features | **Disabled** | Disabled / Enabled | yes |
| 30 | Prime Hunter's Mark: Double Tap Action | **Hunter's Dream** | Warp Menu / Hunter's Dream / Reawaken / Do Nothing | yes |
| 31 | Grand-Resonance Bell: Double Tap Action | **Gather Summons** | Gather Summons / Do Nothing | yes |
| 32 | Always Show Summon Signs | **Disabled** | Disabled / Enabled | yes |
| 33 | Boss Rematch Scaling | **Disabled** | Disabled / Enabled | yes |
| 34 | Advance the Cycle | **NG** | NG / NG+1 / NG+2 / NG+3 / NG+4 / NG+5 / NG+6 | no (file only) |
| 35 | Dark Fog | **Disabled** | Disabled / Always On / Random Spawn / Random Time | yes |
| 36 | Hunter's Dream: Fire | **Default** | Default / Always On / Disabled | yes |
| 37 | Hunter's Dream: Music | **Default** | Default / Music 1 / Music 2 / Disabled | yes |
| 38 | Prevent Auto NG+ | **Enabled** | Disabled / Enabled | yes |
| 39 | Stocked Shop | **Disabled** | Disabled / Enabled | yes |
| 40 | Temporary Stocked Shop | **Disabled** | Disabled / Enabled | no (file only) |
| 41 | Shops Plus | **Enabled** | Disabled / Enabled | yes |
| 42 | Rematch Death Action | **End Rematch** | End Rematch / Restart Rematch | yes |
| 43 | Rematch Cutscenes | **Enabled** | Disabled / Enabled | yes |
| 44 | Auto Unlock Chalice Doors | **Disabled** | Disabled / Enabled | yes |
| 45 | Random Moon Cycles | **Disabled** | Disabled / Enabled | yes |
| 46 | Require Gesture for Mod Menu | **Disabled** | Disabled / Enabled | yes |
| 47 | Great Bridge Door | **Disabled** | Disabled / Enabled | yes |
| 48 | Unlock All Lamps | **Disabled** | Disabled / Enabled | no (file only) |
| 49 | Activate All Shortcuts | **Disabled** | Disabled / Enabled | no (file only) |
| 50 | Infinite Durability | **Enabled** | Disabled / Enabled | yes |
| 51 | Ghost Shop | **Disabled** | Disabled / Enabled | yes |

## The in-game menu

Nearly everything is toggleable **in-game at the Doll** in the Hunter's Dream,
under **"Enhanced Features"**. `Require Gesture for Mod Menu` is **Disabled**, so
the option sits there permanently (no bowing needed). Confirmed from `_data/msg.json`:
**35 on/off toggles** plus multi-value entries (Dark Fog mode, Victory/Death
Respawn, Double Tap actions, Hunter's Dream Music/Workshop Fire, and a large
Ghost Shop "Visual Effect" list).

`Prime Hunter's Mark: Enhanced Features` is **Disabled**, so settings are
Doll-only until that is flipped once (it is itself an in-game toggle).

There is also an in-game toggle **"Item Drop Hunt"** with no entry in
settings.json — likely Ghost-Shop-adjacent, unexplored.

## Two dependency findings that matter (both measured, not inferred)

**1. Lamp Kindling is a SUB-MODE of Auto Refill, not a replacement.**
The restock lives in event **10008300**, whose *first* condition tests the Auto
Refill **Enabled** flag (`12100862`). The tiered kindling logic sits inside that
same event, after the gate. Setting Auto Refill to Disabled means `12100862` is
never set, the event exits at the top, and **kindling silently does nothing**.
To get kindling: leave `Auto Refill Bullets And Vials` **Enabled** *and* set
`Auto-Refill: Lamp Kindling` **Enabled**.

**2. Kindle level is stored PER LAMP.**
Event 10008300 is parameterised (15 params) and is initialised **126 times**
across the map emevds, once per lamp. Parameter `sourceByte 8` feeds each lamp's
own flag into the tier comparisons (instructions 33/40/47/53/60/67). Lamp flags
are spaced by 2 (`12112100`, `12112102`, … Hemwick `12112500`, Nightmare
`12902900`), i.e. **2 bits of kindle level per lamp**, matching levels 0-3.
The globals `12104030`/`12104040`/`12104050` are **scratch registers** holding
the player's current vial/bullet counts during the calculation, *not* the kindle
store — they look like global counters and are not.

Tiers: unkindled tops up **to 5** of each, kindled once **10**, twice **15**,
three times **full (20)**. It is a top-up ("up to N"), not an add. 1 insight per
kindle; kindling past level 1 needs the **Rite of Kindling** (Shadow of Yharnam,
Forbidden Woods, mid-game).

## The five that need file-level editing

The in-game menu cannot set these, and three are one-way by design
("cannot be disabled in game"):

1. Spawn Iosefka Clinic Lamp at Start
2. **Advance the Cycle** (NG → NG+6 starting difficulty)
3. Temporary Stocked Shop
4. **Unlock All Lamps**
5. **Activate All Shortcuts**

All five are already at the right values for a first playthrough, so no file
editing is needed unless that changes.

## Community sentiment on auto-restock (researched 24 Aug)

Donnie's worry was that a guaranteed 20 vials per death is overpowered. The fact
that defuses it: **vanilla Bloodborne already refills to 20 after every death**,
pulling from the storage box (600 cap). The mod does not add that; it removes the
moment the stockpile hits zero and you must farm or buy.

The vial system is widely considered a step back from Estus, and FromSoft never
repeated it (Sekiro and Elden Ring returned to auto-replenishing). Main criticism
is a death-spiral argument: farming lands hardest on players already struggling.
The defence is that scarcity creates a real "burn the last vials or bail"
decision, which auto-refill does delete. The mod author clearly anticipated the
objection — kindling exists as the "in case the regular restock feels too cheaty"
answer.

**The actual mechanical change is economic, not combat.** Vials cost 180 echoes
early, scaling to 720 after Rom and 900 in NG+. Auto-refill deletes that echo
sink entirely, so everything goes into levels and gems. The honest answer to
"is it OP" is: not the heals, but you will run a couple of levels ahead of where
vanilla would have left you.

Sources: [Fextralife Blood Vial](https://bloodborne.wiki.fextralife.com/Blood+Vial),
[Bloodborne wiki Storage](https://bloodborne.fandom.com/wiki/Storage),
[Nexus mod 19](https://www.nexusmods.com/bloodborne/mods/19).
ResetEra / NeoGAF / abstractinggames all returned HTTP 403 to WebFetch, so those
positions come from search summaries rather than a direct read.
