# Bloodborne QoL port candidates: what to steal from the modern Soulslikes

**Date:** 2 Sep 2026. **Status:** research only, nothing built.
**Context:** first player-control feature shipped today (sprint in all directions
while locked on, Elden Ring behaviour) via `action/script/c0000.hks` plus
`chr/c0000.anibnd.dcx`.

This is a survey of every quality-of-life feature worth porting into Bloodborne
from Elden Ring, Dark Souls 3, Sekiro, Demon's Souls remake, Lies of P and the
rest, rated for feasibility **on our specific stack**, and cross-checked against
what the Nexus modding scene has already built.

---

## Method

- **Nexus**: enumerated the **entire** Bloodborne mod catalogue via the public
  API (mod ids 1-560, 403 live published mods) and full-text searched every
  description. This is a complete census, not a sample, so a "no mod exists"
  claim below is a real negative rather than a failed search.
  API root: `https://api.nexusmods.com/v1/games/bloodborne/mods/{id}.json`.
- **Download size as a layer fingerprint.** A mod's archive size tells you which
  layer it edits, checked against the real sizes in our install
  (`~/games/ps4/CUSA00900/dvdroot_ps4/`):
  - `action/script/c0000.hks` ships as **760,643 bytes of compiled HavokScript**
    (`LuaQ` header), but the control mods replace it with ~430 KB of **plain Lua
    source**, which zips to roughly 20 KB. So every ~17-22 KB control mod is
    *this one file and nothing else*. See the next section.
  - `chr/c0000.anibnd.dcx` is **2,647,091 bytes**. So a ~2.2 MB mod is the whole
    behaviour-and-TAE bundle, and the ~8-10 MB mods are that bundle plus
    additional `chr/` files or a looser repack.

  This is how the feasibility ratings below were anchored to evidence rather
  than guesswork. (Aside: the other `c1xxx.hks` enemy scripts are 1.6-17 KB of
  compiled HKS and no reconstructed source for them is known, so enemy-side
  script changes stay on the bytecode route.)
- Web research on community wishlists and on the modding toolchain.

### Sources checked directly

1. the complete Nexus API census (403 mods, descriptions and file manifests),
2. the actual files in `~/games/ps4/CUSA00900/dvdroot_ps4/`,
3. our own prior research in `~/couch/docs/research/` and `~/couch/data/bb-hks/`,
4. community wishlist and pet-peeve threads on r/bloodborne, r/BloodbornePC and
   r/shadps4, plus the community's own maintained guide (URLs in section H and
   in Sources).

5. a toolchain sweep covering the FFDec Scaleform round trip, Paramdex/Smithbox
   param support, and the shadPS4 cheat catalogue.

### The community's own top three

Worth stating early, because it reframes the whole exercise. The maintained
community guide opens its QoL section by naming the "most widely shared
complaints" as: **lamp-to-lamp fast travel, auto-refill of vials and bullets,
and boss runbacks.** All three are **already solved and already installed** on
this box via Bloodborne Enhanced, though one of them (runbacks) is switched off,
see item 1 of the ranking.

So the obvious wins are banked. Everything below is the second tier, which is
why so much of it lands on feel rather than on convenience.

### One honest note on sentiment

The most-discussed thread on this subject (456 upvotes, Jan 2026) shows near
consensus that these QoL mods are for veterans on a replay, and that **first
time players should skip them** because vial scarcity and runbacks are
load-bearing tension. Donnie is a first-time, blind player who already runs
Enhanced and has cheats available. That is his call and it is already made. The
note is recorded only so the trade-off is explicit: most items in section E buy
convenience by spending tension, whereas the items in sections A, B, C and D
mostly buy feel without spending anything. **The ranking below deliberately
favours the latter.**

## Feasibility scale

| Rating | Means |
|---|---|
| **ALREADY** | An existing mod or a Bloodborne Enhanced setting covers it. Named. |
| **EASY** | Script, param, msg, cheat or menu-texture edit. About a day. |
| **MEDIUM** | Behaviour graph or TAE work, or a new Scaleform behaviour. A few days. |
| **HARD** | Engine reverse engineering, a new system, or new assets. |

---

## Read this first: the HKS source already exists, on this box

Today's sprint feature was built by **patching HavokScript bytecode**, because
`data/bb-hks/FINDINGS.md` concluded, correctly at the time, that hksc's
decompiler is incomplete and that "there is no Lua source out of this file
today", so "an edit made at the bytecode level can be shipped". Every working
variant in `data/bb-hks/` is therefore exactly **760,643 bytes**, the same size
as stock, because a bytecode patch cannot change the file's length.

**That constraint is unnecessary, and the evidence is already in our own
reference folder.** The Nexus control mods do not ship bytecode. They ship the
**complete script as readable Lua source**:

| File | Size | Lines | Functions |
|---|---|---|---|
| `dvdroot_ps4/action/script/c0000.hks` (stock, live) | 760,643 | n/a | compiled `LuaQ` bytecode |
| `data/bb-hks/ref/enhancedcontrols/.../c0000.hks` | 433,755 | **14,175** | **1,185** |
| `data/bb-hks/ref/jumponl3/DS3-Classic/.../c0000.hks` | 428,652 | 14,076 | n/a |

Checks run against those files:

- They contain, by name, **exactly the functions our bytecode work located by
  source line number**: `Run_onUpdate`, `Walk_onUpdate`, `Dash_onUpdate`,
  `DashStart_onUpdate`. All four present, one definition each.
- They open with the named constant block (`Idle = 0`, `Walk = 1`, `Run = 2`,
  `Dash = 3`, the ladder states, the damage directions), so the symbol names are
  intact, not a mechanical decompile.
- The two mods **differ from each other by only 221 lines**, so both derive from
  one shared community-reconstructed source base rather than from independent
  decompiles.
- The game loads them. Jump on L3 has 860 endorsements. This route is
  play-proven at scale, not theoretical.
- **The original FromSoft symbol names survive.** Engine calls are still named
  in Japanese, e.g. `env("アイテムアニメタイプ取得")` ("get item animation
  type"), `env("装備武器カテゴリ番号取得", Right)` ("get equipped weapon
  category number"), `env("武器切替状態を取得")` ("get weapon switch state"),
  `act("メガネ外す")` ("remove glasses"). This is a symbol-preserving
  reconstruction, not a name-mangled decompile, which is why reading it is
  practical rather than archaeological.

**Consequences, and they are large:**

1. We never needed a decompiler. We needed someone else's source, and we
   downloaded two copies of it hours ago as reference material.
2. The same-size constraint disappears. We can **add** code, not just swap
   equal-length instructions.
3. Reading a mod's behaviour stops being reverse engineering and becomes
   `diff`. The 221-line delta between two mods is a readable changelog of
   exactly how each one alters movement.
4. Every **EASY** rating in section A below assumes this route. On the bytecode
   route several of them would be MEDIUM or worse.

**The one real risk:** these sources are a *reconstruction*, so compiling one
yields a script that may differ from stock in ways unrelated to the mod's
intent. Mitigation is the obvious one, and we already have the rig for it:
compile the unmodified reference source with `hksc-be -c` (which `FINDINGS.md`
records as **working**, it is only the decompiler that fails), install it, and
confirm the game plays normally before layering any change on top. Treat that
canary as the gate for the whole HKS route.

**Recommended next action regardless of which feature is chosen first:** run
that canary, and if it passes, rebase today's lock-on sprint change from a
bytecode patch onto the source. `tools/bb-lockon-sprint` and
`data/bb-mod-backups/c0000.hks.stock-20260902` make the revert cheap.

---

## What each layer has been PROVEN to do

This matters more than any individual feature, because it sets the ceiling.

### (a) `action/script/c0000.hks`: compiled on disk, source available (see above)

Proven in the wild, by mods that ship **nothing but this one file**:

- **Jump on L3** (mod 156, 860 endorsements): rebind jump to a stick click,
  decouple jump from roll, "toggle sprint" variant.
- **Enhanced Controls** (mod 473): sprint moved circle to X, jump attack as a
  button *combo* (hold L3 + R1), a bug fix that gates healing while sprinting,
  and dropping off a ladder on a stationary circle press.
- **Elden Ring Controls** (mod 502): the big one. In a 22 KB archive holding
  nothing but that one script it does:
  X-jump gated on sprint, **removes the forced landing roll** after a normal
  jump (keeping it for high falls), L3 as a lunge attack, and **mid-air input
  buffering** where R1/R2/L1/L2 pressed in the air queue a rolling attack,
  backstep attack, transformation attack or gunshot on landing.

**Conclusion: the HKS layer is far more capable than "button remapping".** It is
a state machine you can rewrite: any change of the form "under these conditions,
this button issues that action request, and this animation may be cancelled
into that one" is in reach. Mid-air buffering in particular proves you can add
input state that vanilla never had.

Limit: it routes to **existing** action requests. It cannot invent an animation.

### (a2) The delivery risk that sits under every HKS item

`BEHAVIOUR-FINDINGS.md` records that an earlier patched `.hks` produced **no
observable change**, and ranks the explanations with "**the patched `.hks` was
not actually being loaded**, which is the same overlay-vs-patcher question that
killed the lamp menu" as by far the most likely.

That is the same failure mode as the Bloodborne Enhanced lamp saga, where a
setting read as enabled for weeks with nothing able to deliver it, and where the
open untested lead is still **that we have only ever run a file overlay, never
the mod's patcher**. The rule from that episode generalises here:

> A file on disk proves installed, not loaded.

**Independent confirmation that the patcher is the intended route.** Bloodborne
Enhanced is open source (`github.com/colorsolid/Bloodborne-Enhanced-Directory`,
built on TKGP's SoulsFormats), and it ships a **patcher that merges** event,
msg, param and map edits with other mods rather than overlaying files. That is
the scene's own answer to the conflict problem in surprise 2, and it is the tool
we have never run. It is now implicated in two separate unexplained failures
here. Running it is cheap.

So before ranking any HKS feature by how nice it would be, the cheap and correct
first move is a **delivery canary**: make a change to `c0000.hks` that is
impossible to miss and impossible to misread (something that breaks or visibly
alters a basic movement action), and confirm it in play. `data/bb-hks/` already
has a `c0000.CANARY.hks`, which suggests this was in progress. If the overlay
does not deliver `c0000.hks`, then **items A5, A6 and everything else in
section A are blocked**, not by difficulty but by plumbing, and the patcher
question becomes the highest-value thing on this whole list.

### (b) `chr/c0000.anibnd.dcx`: Havok behaviour graph + TAE

Proven by mods shipping 2-10 MB:

- **Lock-On Roll** (mod 394): replaces the locked-on **dash with a full roll**,
  and ships variants tuned to *Bloodborne dash i-frames* and to *Dark Souls 3
  roll i-frames*. Its changelog explicitly says "fixed issue where i-frames of
  some animations were smaller while camera was locked". So i-frame windows are
  readable, editable and per-animation.
- **Backstep iframes** (mod 273): backsteps from 6 to 8 i-frames, vanilla
  dodges documented at 11.
- **No Dodge Instability** (mod 475): clears the *instability* flag on dodge
  animations `a000_7100`-`a000_7800`, the flag that makes you take extra damage
  for a few frames after invincibility ends. The author names **DSAS**
  (DSAnimStudio) as the tool, which confirms DSAnimStudio reads Bloodborne TAE.
- **Hyperborne** (mod 124): global recovery-frame reduction for player *and*
  bosses, i.e. animation timing is bulk-editable.
- **Queen Von / King Von Movement** (mods 388, 379): wholesale swap of the
  player's run and walk animation set for Lady Maria's and Gascoigne's.

**Conclusion: i-frames, animation speeds, cancel windows, damage-modifier flags
and animation identity are all editable.** Adding a genuinely *new* state is the
hard part, re-pointing an existing one is routine.

**And we already have the toolchain, built today.** `BEHAVIOUR-FINDINGS.md`
records a working round trip: `souls-extract` opens the BND (99 entries: 4
`.hkx`, **80 `.tae`**, 15 others), `JeNoVaViRuS/hkxpack-souls` v0.4 with a
one-class override unpacks the 5 MB behaviour graph to editable XML, and
`~/src/bb-havok/xml_edit.py` has already **added new four-way direction
selectors** to the three dash states by reusing existing generators. Two
warnings from that same document, both worth carrying forward:

- **`Alfred-DMB/HkxPack-Plus` must not be used to pack the behaviour graph.**
  Its reader is correct, its writer is broken for PS4 files.
- **The behaviour graph gates nothing.** It has no conditions, so it is never
  the thing blocking a behaviour. Look in the script or the TAE instead. This
  is why the 80 `.tae` files, not the `.hkx`, are the real lever for every
  i-frame and timing item in this section.

### (c) Params

Proven QoL levers: **lock-on distance** (mod 301 raises it ~3x and ships
Smithbox CSVs), projectile velocity and lifetime, gem slot types (mod 303),
durability, shop prices and their scaling (mods 396, 299), drop rates
(mods 337, 384), item hold caps, upgrade material costs (mod 179), levelling
costs (mod 129), and **which animation an item's use plays** (mod 423 FastMark
makes the Hunter's Mark 3x faster purely by pointing it at a shorter animation).

### (d) shadPS4 cheat / memory patches

Already ours: 60 fps, infinite health/stamina, 1-hit-kill, infinite durability.
The scene adds **FOV**: mod 76 and mod 193 are Cheat Engine tables, and
mod 545 **bbfov** is an open-source DLL injector
(`https://github.com/paylanon/bbfov`) whose value is the *offsets*, which port
straight into our existing cheat XML pipeline.

### (e) Menu textures and Scaleform

HUD **layout** is fully re-authorable, proven several times over: Compact HUD
(mod 392) moves elements to the screen edge, scales them down, and offers
variants that relocate blood echoes and insight to the bottom "like other souls
games" or delete them; 4k Upscaled UI (mod 182); Ultrawide UI Fixes (mod 202)
and 16:10/4:3 fixes (mod 207) reposition every HUD element for new aspect
ratios; Better UI (mod 52) moves item pop-ups; mod 63 recentres the "You Died"
text.

We additionally have something the scene does not: a **working Scaleform
pipeline**, proven by porting Elden Ring's HUD into Dark Souls 3 (see
`ds3-elden-ring-hud-port` memory and `docs/research/ds3-ui-iteration-speed-20260902.md`).
Bloodborne's UI is the same technology.

---

## The candidates

### A. Movement and control (HKS layer)

| # | Feature | From | What it does | Feasibility |
|---|---|---|---|---|
| A1 | Sprint in all directions while locked on | Elden Ring | Locked-on movement is not capped at a strafe walk | **DONE today** (ours) |
| A2 | Jump on a dedicated button | ER / DS3 | Jump without a running-circle-tap, jump from standing | **ALREADY**: Jump on L3 (156), Quality Controller Binds (453), Enhanced Controls (473), Elden Ring Controls (502) |
| A3 | Sprint and jump on separate buttons | ER | Circle is sprint only, so no accidental jumps and sprint flows into a roll | **ALREADY**: mods 453, 473, 502 |
| A4 | Toggle sprint | accessibility standard | Hold-to-sprint becomes a click | **ALREADY**: mod 453, and a "Toggle Sprint on L3" file in mod 156 |
| A5 | **No forced landing roll** | ER | Land from a jump and act immediately instead of eating a roll animation | **EASY**: mod 502 does it in HKS alone. Worth folding into our own script rather than installing a conflicting mod. |
| A6 | **Mid-air attack buffering** | ER | R1/R2/L1/L2 in the air queue an attack on landing | **EASY**: mod 502, HKS only |
| A7 | Jump attack | ER / DS3 | A real plunging/jumping attack | **ALREADY**: mods 473, 453, 502 |
| A8 | Crouch and crouch-poke | ER / Sekiro | Stealth approach and a crouching thrust | **HARD**: Bloodborne has no crouch animation and no stealth system. Mod 502 substitutes an L3 lunge attack for the *muscle memory*, which is the honest ceiling here. |
| A9 | Dodge (roll) instead of dash while locked on | DS3 | Classic roll while locked, for players who never adapted to the quickstep | **ALREADY**: Lock-On Roll (mod 394), with a DS3-i-frame variant. **Caveat: it disables the Old Hunter Bone.** Also arguably a downgrade: the quickstep is Bloodborne's identity. |
| A10 | Free-aim ranged weapons | every other Souls game | Aim the gun without a lock | **HARD**: no mod exists; mod 301's author raised lock-on range *specifically because* "Bloodborne lacks the feature to free-aim". Needs a camera-relative aim state that does not exist. |

### B. Combat feel (anibnd / TAE)

| # | Feature | From | What it does | Feasibility |
|---|---|---|---|---|
| B1 | **Remove dodge instability damage** | none, it is a vanilla wart | Deletes the invisible +damage window right after your i-frames end | **ALREADY / EASY**: mod 475, flag on `a000_7100`-`a000_7800`. A blind player cannot learn a punish he cannot see. |
| B2 | Consistent / retuned i-frames | DS3 | Roll timing you can internalise | **ALREADY**: mod 394 variants, mod 273 for backsteps. **MEDIUM** to tune ourselves. |
| B3 | Faster healing animation | DS3 estus chug speed | Vial chug that does not commit you for so long | **MEDIUM**, and **not via the obvious route**: TAE's `DebugAnimSpeed` is inert in Bloodborne, so animation speed must be changed at `hkbClipGenerator.playbackSpeed` in the behaviour bundle instead. Cheaper alternative: the FastMark trick (mod 423) of pointing the item at a shorter existing animation. Note this is a balance change, not pure QoL. |
| B4 | Faster Hunter's Mark | none | Standard Mark 3x faster | **ALREADY**: FastMark (mod 423), a param edit |
| B5 | Rally / regain window tweak | Bloodborne's own | Longer window to heal by hitting back | **MEDIUM**, and not recommended, rally is the game's thesis |
| B6 | Weapons stop bouncing off walls | ER | No dead-stop on geometry | **ALREADY**: mod 335 |
| B7 | Sekiro posture bar | Sekiro | A deflect/poise meter with a break state | **HARD**: a new stat, a new meter, and new enemy reactions. Bloodborne has no guard. Visceral attacks already fill the "break and punish" role. **Recommend against.** |
| B8 | Guard counter / stance break | ER | Parry-into-riposte from a block | **HARD** and redundant with visceral attacks |
| B9 | Easier gun parry window | quality of life | Wider parry timing | **ALREADY**: mod 122 |
| B10 | Damage numbers | Nioh / Lies of P | Numeric feedback per hit | **HARD**, no mod exists, and **Donnie said no** |

### C. Camera and lock-on

| # | Feature | From | What it does | Feasibility |
|---|---|---|---|---|
| C1 | **FOV slider** | every modern game | Bloodborne's FOV is famously tight, worse on a large TV at couch distance | **EASY on our stack**: mod 545 **bbfov** is open source (`github.com/paylanon/bbfov`); mods 76 and 193 are Cheat Engine tables. All three are Windows binaries and useless to us as shipped, but the **offsets** drop into our existing `tools/bb-cheat` pipeline. **One caveat that decides the implementation**, see below. |

**The FOV caveat.** Mod 76's instructions say the FOV value *must be frozen* or
"the FOV will reset after your death". That means FOV is not a static byte patch
like our existing cheats: something in the game writes the value back every load.
Our `bb-cheat` boot mode (an XML `Address = offset + 0x400000` block) and its
live mode (a one-shot write at `0x800000000 + offset`) both write **once**, so
neither would hold. Two options, and the second is the right one:

1. Poll and rewrite the value, the Cheat Engine "freeze" approach. Cheap, ugly,
   and it fights the game every frame.
2. **Patch the writer, not the value**: find the instruction that stores the
   default FOV and `nop` it, or patch the immediate it loads. That is a normal
   static byte patch and fits our existing boot-mode XML exactly.

Identifying the writer is the only real work, and `bbfov`'s source gives the
address to set a breakpoint on. Budget this as EASY-plus rather than EASY.
| C2 | **Longer lock-on range** | ER | Vanilla lock range is very short, so lock pops off mid-fight | **EASY**: param. Mod 301 raises it ~3x and ships Smithbox CSVs. Take the lock-on rows only and skip its projectile buffs. |
| C3 | **Camera distance and auto-camera off** | ER camera options | Pull the camera back, stop it auto-rotating as you move | **EASY, and nearly free.** The official shadPS4 cheat file, `ps4_cheats/PATCHES/Bloodborne.xml`, **already ships "Increased camera distance" and "Disable Camera Auto Rotation via Movement"**, in the exact XML format `tools/bb-cheat` already writes. This is close to a configuration change. Caveat: shadPS4 issue 3767 reports BB's camera already pulling back further than on PS4 while sprinting, so measure before stacking more distance on top. |
| C4 | ER-style lock-on target switching (by camera direction, not proximity) | ER | Right-stick flick picks what you are looking at | **HARD / unknown**: no evidence this is param-driven; probably code |
| C5 | Hide the lock-on dot | taste | Cleaner screen | **ALREADY**: mod 201 |
| C6 | Mouse-driven camera | PC convention | Not relevant, he plays on a pad | **ALREADY**: mods 189, 218 |

### D. HUD and UI

| # | Feature | From | What it does | Feasibility |
|---|---|---|---|---|
| D1 | **HUD auto-hide out of combat** | ER, Sekiro, Ghost of Tsushima | Bars fade when nothing is happening, return on damage or lock-on | **Mostly ALREADY, natively, and the rest is HARD.** See the correction below. |
| D2 | Manual HUD toggle | screenshot convention | One key hides everything | **ALREADY**: mod 293, via ReShade, presentation layer only |
| D3 | Compact / scaled HUD, echoes and insight moved to the bottom | DS3, ER conventions | Less screen clutter, familiar placement | **ALREADY / EASY**: Compact HUD (mod 392) |
| D4 | 4K and ultrawide correct HUD | modern standard | HUD that fits the panel | **ALREADY**: mods 182, 202, 207, 170 (84 resolutions) |
| D5 | Larger subtitles | accessibility | Readable from the couch | **ALREADY**: mod 441 |
| D6 | Item values shown in descriptions | ER shows rune values | Coldblood items state their echo value | **ALREADY**: mod 542, a pure `msg` edit. **EASY** to extend to anything else. |
| D7 | Elden Ring pouch / radial quick-select | ER pouch, DS3 quick slots | More than one item bank without opening the menu | **HARD**, and harder than it first looks, see the note below. No mod exists anywhere in the catalogue. |
**Correction on D1, and it kills my own best idea.** I had this as the stretch
goal of the whole document. Three findings retire it:

1. **Bloodborne already auto-hides the HUD out of combat, natively and
   hardcoded.** The only thing exposed is the binary System > Display HUD
   toggle. So most of the value is already there and he already has it.
2. Elden Ring exposes the *tuning* of its version as params
   (`MenuCommonParam.autoHide{Hp,Mp,Sp}Threshold{Ratio,Value}`, which is all
   Nexus ER mod 4503 edits). **Bloodborne has no `MenuCommonParam` at all**, so
   there is no data-level knob for when or how fast the fade happens.
3. Changing the *conditions* is therefore an eboot patch, not a `.gfx` or param
   edit. And while FFDec can in principle edit ActionScript inside a `.gfx`,
   **no evidence was found of anyone doing that in any FromSoft title**; every
   documented workflow touches display-list and timeline tags only.

What the Scaleform layer *is* good for is confirmed and still useful:
`menu/01_000_fe.gfx` is Bloodborne's HUD movie, the round trip is
`ffdec -swf2xml` then `-xml2swf`, textures are external
(`DefineExternalImage2` tags pointing into `01_common.tpf.dcx`, the same file we
worked on for DS3), and **adding display objects works**, proven by Extended
SpEffect Icons (mod 261) growing the status-icon strip from 18 to 40 slots.

**Why D7 is hard, checked in the source rather than assumed.** I initially rated
a cheap version of this (a modifier that cycles the existing quick bar
*backwards*) as EASY on the assumption that item selection is a script concern.
It is not. In the reference source, `Act_UseItem()` (line 505) only decides
**which animation to play**, by asking the engine what kind of item is already
selected:

```lua
function Act_UseItem()
    if env("アイテムアニメタイプ取得") == 0 then
        hkbSetVariable("ItemAnime", 0)
    elseif env("アイテムアニメタイプ取得") == 1 and ... then
        hkbSetVariable("ItemAnime", 28)
```

`アイテムアニメタイプ取得` is "get item animation type". The script never sees
the quick-slot list, never selects an item, and has no call to change the
selection. Selection lives engine-side, behind the menu. So **no amount of HKS
work reaches this feature**, cheap version included. Correcting this before
anyone spends a day on it is worth more than the feature would have been.

| D8 | Map or compass | ER | Know where you are | **HARD** in-game (new asset, new system). **But see the surprising note below** about our phone remote. **Also a spoiler hazard for a blind playthrough.** |
| D9 | Photo mode | Demon's Souls remake | Freecam plus HUD off | **MEDIUM**: freecam via the same memory layer as FOV, HUD off via mod 293. A rough version is assemblable today. |

### E. Progression, economy and travel

| # | Feature | From | What it does | Feasibility |
|---|---|---|---|---|
| E1 | **Respawn at the boss lamp instead of the Dream** | ER Stake of Marika | Deletes boss runbacks | **ALREADY, AND ALREADY INSTALLED**: Bloodborne Enhanced settings **20 (Broken Lamp: Victory Respawn)** and **21 (Broken Lamp: Death Respawn)**, both currently sitting on *Hunter's Dream*. Flipping them to *Boss Lamp* is a menu toggle at the Doll. Also available standalone as Stake of Marika (mod 223). |
| E2 | Fast travel lamp to lamp | DS3, ER | No trip through the Dream | **ALREADY**: Enhanced setting 7 (Lamp Menu: Warp), plus Lamp2Lamp (mod 455) and MOAL (mod 107) as alternatives |
| E3 | Level up and upgrade at a lamp | DS3 bonfire, ER grace | No trip to the Doll or the workshop | **ALREADY**: Enhanced settings 8, 9 |
| E4 | Storage and workshop from anywhere | ER's inventory-anywhere | No storage-box pilgrimage | **ALREADY**: Enhanced settings 11 and 26 (Prime Hunter's Mark: Storage, already Enabled), plus Portable Workshop (mod 278) |
| E5 | Estus-style free heal refill | DS3, Sekiro, ER | No blood vial farming, ever | **ALREADY**: Enhanced settings 2/3 (Auto Refill + Kindling), plus mods 206, 257, 217, 549 |
| E6 | Boss rematch | Sekiro Reflection of Strength, ER | Refight anything for practice | **ALREADY**: Enhanced setting 14, plus Boss Arena (mod 533), Boss Rush (mod 9) |
| E7 | Keep echoes on death | Lords of the Fallen, AC6 | No loss spiral | **Available**: mods 140, 130. **Recommend against**: he plays blind and values feel, and this removes the game's only stake. |
| E8 | Shop prices that do not inflate | fairness | Vials stay cheap late | **ALREADY**: mods 396, 299 |
| E9 | No fall damage | convenience | Removes a cheap death source | **ALREADY**: mod 440 |
| E10 | Starting class / gift system | DS3, ER | Pick a build and a starting gift | **ALREADY**: mod 415 |

### F. Whole systems from other games: the "no" pile

Recorded so the question is closed, not because they are recommended.

- **Spirit ashes / summons** (ER): HARD, needs new NPC AI and assets. No.
- **Lies of P weapon assembly** (mix blade and handle): HARD, a new equipment
  system on top of Bloodborne's trick weapons, which already do this job
  thematically. No.
- **Lies of P pulse cells / Nioh ki pulse**: HARD, new resource systems. No.
- **Sekiro resurrection**: cheaply *fakeable* at the cheat or emevd layer, but
  it deletes death as a consequence for a blind player. No.
- **Torrent / mounts**: HARD, and Yharnam is not built for it. No.
- **Elden Ring "grace guidance" golden trail**: declined by Donnie, and it is a
  direct spoiler vector for a blind run. No.
- **Demon's Souls remake item send / online features**: not applicable offline.
- **Weapon arts / ashes of war visibility**: Bloodborne has no weapon arts;
  trick transformations occupy that slot. Not applicable.

### G. Things unique to our stack (nobody on Nexus can do these)

| # | Feature | What it does | Feasibility |
|---|---|---|---|
| G1 | **Emulator-level pause bound to a gesture** | Bloodborne cannot be paused. shadPS4 can. Binding it through `couchd`'s existing PS-button gesture vocabulary gives a real pause with no game files touched. | **EASY** |
| G2 | Second-screen companion on the phone remote (:8790) | Build status, a map, a checklist, on the phone instead of on the TV | **EASY**, but **a spoiler hazard**, see below |
| G3 | Merged param set rather than stacked mods | Most param mods declare themselves incompatible with each other; we already own `bb-durability-patch.py` and a param pipeline | **EASY**, and it is the *precondition* for adopting more than one of the EASY param items above |
| G0 | **An overlay drawn by the emulator itself** | The features the game cannot express, drawn *over* it in `shadps4-dbg`'s existing ImGui layer: damage numbers, a posture or stagger meter, a stamina readout, a rally-window indicator, a build or checklist panel. There is no FromSoft precedent below Elden Ring for any of these, and every Elden Ring version is a DLL plus ImGui, which is structurally the same thing we would be doing. **We already build the emulator**, so this is the one route that turns several HARD items MEDIUM. | **MEDIUM** |
| G4 | Our own `c0000.hks`, not a downloaded one | Every control mod above is a whole-file replacement of the same 22 KB script, so they cannot be combined. We edit source, so we can take the ideas rather than the files. | **EASY**, already how today's sprint change was done |

---

### H. Community asks not covered above

These came out of the wishlist threads rather than from the "port a feature from
a later game" framing, and several are better value than things in the sections
above. Grouped by whether they are worth doing.

**Worth doing, cheap:**

| # | Feature | What it does | Feasibility |
|---|---|---|---|
| H1 | **Skip the intro logos** | The community guide's author: "Intro skip is my favourite mod. I can launch the game and be in in under 10 seconds." Matters more here than for most people, because the box launches games from a pad handoff on a TV. | **EASY** |
| H2 | **Consumables should not vanish from the quick bar at 0** | When a stack empties, the slot disappears and everything shifts, so the next press throws the wrong item mid-fight. Souls games keep the slot. Named as a top pain point. | **Unknown, probably menu-side.** No mod exists. Given the D7 finding that the script cannot see item selection, temper expectations. |
| H3 | **Bold Hunter's Mark should restock** | It respawns every enemy but restocks nothing, so you get strong-armed back to the Dream anyway. | **ALREADY**: Enhanced's Prime Hunter's Mark, settings 22-30, several already Enabled |
| H4 | Show echoes-needed-to-level on the status screen | Removes a mental subtraction | **EASY**, `msg` layer, same trick as mod 542 |
| H5 | Training dummy in the Dream | Test weapons and builds without a real fight | **ALREADY**: WTG Weapons Testing Guy (mod 99) |
| H6 | No forced NG+ on the final boss | Keep exploring after the ending | **ALREADY, and already Enabled**: Enhanced setting 38, Prevent Auto NG+ |
| H7 | More visible bloodstain marker | Find your echoes | **EASY**, an effect or texture change. No mod found. |

**Requested a lot, but not for this playthrough:**

| # | Feature | Why not | Feasibility |
|---|---|---|---|
| H8 | **Respec / rebuild stats** | From DS3 Rosaria and ER Rennala, and the single most cited "thing Bloodborne lacks". | **ALREADY**: Enhanced's Character Reset, though its own author calls it a compromise (drops you to level 10 and refunds echoes) and points at a save editor instead (mod 108). |
| H9 | Turn off motion-control gestures | A very highly voted ask: you gesture accidentally mid-fight and die. **Probably already moot here**, since the pad reaches the game through shadPS4 and the DualShock motion path is unlikely to be wired through. Worth confirming rather than building. | **Verify first** |
| H10 | Chalice dungeon material gating and shared progress | Re-grinding every base chalice per character. He is not doing chalices blind. | **ALREADY**: mods 121, 289 |
| H11 | Grid inventory, fast menu scrolling, storage visible from inventory, gem-set transfer, hide menu while changing armour | The whole menu-UX cluster. Genuinely wanted, genuinely fiddly. | **MEDIUM-HARD**, Scaleform and menu layer, no mods exist |
| H12 | Co-op summon signs, restock after co-op | Online only | Not applicable offline |
| H13 | Respawn at the nearest lamp to where you died | Superseded by H3 and by ranking item 1 | Not needed |

**The clearest unfilled request in the entire scene**, worth recording because
it is a genuinely good design idea nobody has built:

| # | Feature | What it does | Feasibility |
|---|---|---|---|
| H14 | **Vial scarcity while exploring, Estus guarantee at boss fights** | Keeps the survival-horror pressure of a dwindling stock in the world, and removes the farming loop that only ever punishes you for losing to a boss. It is the exact split the arguments on both sides keep circling. | **MEDIUM**: an emevd change conditioned on the boss fog-gate flags, which is a layer we have already parsed and edited. If anything in this document deserves to be built rather than borrowed, it is this. |

---

## Ranked top 10 by value for effort

For a player who has cheats available, **plays blind**, and values feel.
Ordered so that everything above the line is worth doing before anything below.

**Two prerequisites, not features.** Both are cheap, both gate item 4 and
everything below the line, and doing them in this order is the point:

1. **Delivery canary.** Confirm the game actually loads a modified
   `c0000.hks` from the overlay at all. If it does not, no script feature in
   this document can land, and the unrun Bloodborne Enhanced *patcher* becomes
   the most valuable open lead we have. `c0000.CANARY.hks` already exists.
2. **Prove the source route.** Compile the unmodified reference Lua with
   `hksc-be -c`, install, play-test. Retires the same-size bytecode constraint
   permanently.

| # | Feature | From | Feasibility | Why it wins |
|---|---|---|---|---|
| 1 | Flip Enhanced's Broken Lamp respawn to **Boss Lamp** (settings 20 and 21) | ER Stake of Marika | **ALREADY, installed** | Zero effort, zero risk, already paid for. Deletes every boss runback. It is a menu toggle at the Doll. Directly relevant given Logarius was abandoned as "not fun". |
| 2 | **FOV slider** via our cheat XML | every modern game | **EASY** | Bloodborne's FOV is its most-complained-about presentation flaw and it is worst exactly where he plays, on a big TV. Offsets are open source in `bbfov`. Pure feel, zero balance impact. |
| 3 | **Longer lock-on range** | ER | **EASY** | Param edit. Vanilla lock range is short enough that lock drops mid-fight, which reads as the game misbehaving. Fixes frustration without making anything easier. |
| 4 | **No landing roll + mid-air attack buffering**, folded into our own HKS | ER | **EASY** | Proven by mod 502 in the script alone. The single biggest "this feels like a 2022 game" change available, and it composes with today's sprint work in the same file. |
| 5 | **Remove dodge instability damage** | vanilla wart | **EASY** | An invisible +damage window a blind player cannot learn from. Removing it makes deaths legible. Known animation IDs, known flag. |
| 6 | **Camera distance + disable camera auto-rotation** | ER camera options | **EASY** | Both patches already exist in the official shadPS4 `Bloodborne.xml`, in the format `tools/bb-cheat` writes. Close to free, and auto-rotation fighting the player is a real feel problem. |
| 7 | **Compact HUD**, echoes and insight moved to the bottom | DS3 / ER convention | **EASY** | Existing mod, and it lines up with our DS3 Scaleform experience so we can retune rather than accept. |
| 8 | **Emulator pause on a gesture** | every game since 1985 | **EASY** | Uniquely ours via couchd. Bloodborne genuinely cannot be paused, and he plays on a TV in a house with other people in it. |
| 9 | **Coldblood echo values in item text** (and the same trick elsewhere) | ER rune values | **EASY** | Pure `msg` edit, removes a wiki lookup, and a wiki lookup is a spoiler risk for a blind run. |
| 10 | **Skip the intro logos** | modern standard | **EASY** | Cheapest item here. The box launches games from a pad handoff on a TV, so boot time is felt every single session, not once. |

Just below the line, in order: an emulator-drawn overlay (G0) as the route to
anything the game cannot express, the boss-fight-only vial guarantee (H14) as
the one genuinely novel design idea in the scene, faster Hunter's Mark (B4),
photo mode (D9), and a retuned i-frame set (B2).

**Dropped from the top 10 during research, and worth saying why**, since both
were high on my list before the evidence came in:

- **HUD auto-hide** was going to be number 10. Bloodborne already does it
  natively and hardcoded, and Bloodborne has no `MenuCommonParam` to tune it
  with, so the remaining work is an eboot patch for a feature he already has.
- **Reverse-cycling the quick item bar** was going to sit just below the line.
  The script cannot see item selection at all, so there is no cheap version.

Both were killed by checking rather than by reasoning, which is the main reason
this document is worth more than the list I would have written from memory. The quick-item improvement that would otherwise have
sat here is **struck off**: reading the source showed the script cannot reach
item selection at all (see the D7 note).

---

## Surprises worth flagging

0. **The biggest one, covered in full above: the full Lua source of
   `c0000.hks` is already sitting in `data/bb-hks/ref/`**, 14,175 lines and
   1,185 named functions, downloaded today as reference for two mods and not
   recognised for what it was. Today's feature was built the hard way, by
   same-size bytecode patching, on the conclusion that no source existed. It
   did. Every HKS rating in this document assumes we switch routes.

1. **The HKS layer is a state machine, not a keymap.** Mod 502 adds *mid-air
   input buffering* to a game that has no aerial combat, editing nothing but
   `c0000.hks`. That reframes what "control-logic change" means: the constraint
   is the set of existing animations, not the set of existing behaviours. It
   also means the ceiling on today's sprint work is much higher than it looked.

2. **The whole scene fights over the same three files.** Nearly every control
   mod is a complete replacement of `c0000.hks`; nearly every param mod declares
   itself incompatible with anything else touching `gameparam.parambnd.dcx`, and
   Bloodborne Enhanced touches `gameparam` *and* `common.emevd.dcx` *and* the
   msgbnds. Users cannot combine them. **We can**, because we edit sources and
   merge params ourselves. That is the real leverage here, and it means the
   right move is almost never "install the mod", it is "read the mod, take the
   change". This should be the default posture for everything above.

3. **Four obvious features have no Bloodborne mod at all**, confirmed against
   the complete 403-mod census: a radial or pouch quick-select, damage numbers,
   a posture bar, and a map or compass. All four are hard *inside the game*, and
   all four are the same shape as things that already exist as DLL-plus-ImGui
   overlays in the Elden Ring scene. Since we build the emulator, the honest
   route for every one of them is G0, an overlay in `shadps4-dbg`, not a mod.

   A fifth, HUD auto-hide, is absent for a better reason: **Bloodborne already
   does it natively.** I had it ranked as the stretch goal of this document
   before checking.

4. **The same delivery trap is still live.** The reason the lamp menu never
   worked was that a file overlay could not deliver it, and we have still never
   run the mod's patcher. `BEHAVIOUR-FINDINGS.md` independently reaches for that
   same explanation for a `.hks` patch that did nothing. Two unrelated
   investigations converging on one untested cause is a strong signal. **A file
   on disk proves installed, not loaded** is the sibling of the flag rule from
   31 Aug, and it should gate this whole roadmap.

5. **Two of the best wins are already installed and switched off.** Enhanced
   settings 20 and 21 have been sitting on "Hunter's Dream" this whole time,
   which means every boss runback he has walked was optional. Related, and
   consistent with the lamp-menu finding of 31 Aug: **a set flag proves enabled,
   not delivered**: verify at the Doll rather than in the file.

6. **A map is technically the easiest of the "impossible" features and the
   worst idea.** We own a phone at :8790 that could render one without touching
   the game. It is also the single most effective way to destroy a blind
   playthrough. Recorded as a deliberate no.

7. **Two camera features people write Cheat Engine tables for are already
   sitting in the official shadPS4 cheat file.** `ps4_cheats/PATCHES/Bloodborne.xml`
   ships "Increased camera distance" and "Disable Camera Auto Rotation via
   Movement", in the exact format `tools/bb-cheat` already writes. Meanwhile FOV
   itself is genuinely code-only in Bloodborne (no `DirectionCameraParam`, no
   `ChrCamParam`), which is why every FOV mod in the scene is a memory hack.
   Worth checking that file before building anything camera-shaped.

8. **The features Bloodborne cannot express are the ones we are best placed to
   build, because we compile the emulator.** Damage numbers, a posture meter, a
   map: there is no FromSoft precedent for any of them below Elden Ring, and
   every Elden Ring version is a DLL plus an ImGui overlay. `shadps4-dbg`
   already has an ImGui layer. That is structurally the same solution, and it
   means "impossible in Bloodborne" and "impossible for us" are different sets.

9. **`shadPS4 Runtime Injection and Mod Loader` (mod 551, added Aug 2026)** is a
   patched shadPS4 that layers mods as folders and *merges* two mods' edits to
   the same data file instead of letting them clobber each other. We build
   shadPS4 ourselves already (`shadps4-dbg`), so this is worth reading as prior
   art for the merge problem in surprise 2, even if we do not adopt it.

---

## Sources

**Nexus mods** (`https://www.nexusmods.com/bloodborne/mods/{id}`):
19 Bloodborne Enhanced, 52 Better UI, 63 You Died and Texts In Center,
76 FOV Control, 107 More Options At Lamps, 122 more easy gun parry,
124 Hyperborne, 129 Level For Free, 130 Retrieve Blood Echoes from Anywhere,
140 No Blood Echo Loss On Death, 156 Jump on L3, 170 Updated Patches XML incl.
84 Resolutions, 179 No Upgrade Material, 182 4k Upscaled UI, 189 Mouse-Driven
Camera, 193 Move camera with mouse and change FOV, 195 Infinite Durability,
199 Unstucker, 201 No lock-on dot, 202 Ultrawide UI Fixes, 206 Estus Vial and
Bullet, 207 16x10 and 4x3 UI Fixes, 217 Auto refill from storage,
218 MKB2Controller, 223 Stake of Marika, 257 Estus of Marika,
273 Backstep iframes, 278 Portable Workshop, 293 Hide HUD, 299 Anti-Inflation
Shop Prices, 301 Increased Range for Weapons and Lock-On, 303 Universal Gem
Slots, 335 Weapons don't bounce off walls, 337 Blood Gem Drop Booster,
379 King Von Movement, 388 Queen Von Movement, 392 Compact HUD, 394 Lock-On
Roll, 396 No Shop Price Scaling, 415 Return 2 Yharnam, 423 FastMark,
440 Bloodborne Enhanced Enhanced, 441 Big Subtitles for Tiny Screens,
453 Quality Controller Binds, 455 Lamp2Lamp, 462 HardBorne, 473 Enhanced
Controls, 475 No Dodge Instability, 478 Dark UI Overhaul, 502 Elden Ring
Controls for Bloodborne, 533 Boss Arena, 542 Coldblood Items Show Value,
545 FOV Slider (bbfov), 549 Auto-Refill From Storage, 551 shadPS4 Runtime
Injection and Mod Loader.

Also referenced: mod 49 Customizable HUD (HUD animation timing at 60fps), mod 99
WTG Weapons Testing Guy, mod 108 Save Editor, mod 121 Add Chalice Dungeons, mod
261 Extended SpEffect Icons, mod 277 merge tutorial, mod 289 Obtain Multiple
Gems, mod 527 Free Blood Vials.

**Tools and toolchain:**

- WitchyBND, mod 20, `https://github.com/ividyon/WitchyBND`
- DSAnimStudio, `https://github.com/Meowmaritus/DSAnimStudio`. Bloodborne
  support is extensive but has known gaps, notably **`DebugAnimSpeed` is inert
  for Bloodborne**.
- Smithbox, `https://github.com/vawser/Smithbox`, supports Bloodborne.
  Soulstruct is the scriptable Python alternative, which suits this box better.
- **Bloodborne's paramdefs shipped with the game**, so field names, types and
  offsets are FromSoft's own rather than reverse-engineered, a better position
  than Elden Ring. Human-readable per-param docs:
  `https://soulsmodding.com/doku.php?id=bb-refmat:main`
- FFDec Scaleform round trip: `ffdec -swf2xml file.gfx file.xml`, then
  `-xml2swf`. Tutorial: `https://soulsmodding.com/doku.php?id=tutorial:ffdec-tutorial`
- HKS references the scene uses: `https://www.nexusmods.com/sekiro/articles/271`
  and `http://soulsmodding.wikidot.com/modding-movesets-the-muffin-knowledge-compenium-ds3`
- Bloodborne Enhanced source and its **patcher**:
  `https://github.com/colorsolid/Bloodborne-Enhanced-Directory`
- BB_Launcher, `https://github.com/rainmakerv3/BB_Launcher`
- Official shadPS4 cheat catalogue, which already contains the camera patches:
  `https://github.com/shadps4-emu/ps4_cheats/blob/main/PATCHES/Bloodborne.xml`
- shadPS4 issue 3767 (camera pulls back further than PS4 while sprinting):
  `https://github.com/shadps4-emu/shadPS4/issues/3767`
- bbfov, `https://github.com/paylanon/bbfov`
- Elden Ring's HUD auto-hide params, for contrast with Bloodborne's absence of
  `MenuCommonParam`:
  `https://raw.githubusercontent.com/soulsmods/Paramdex/master/ER/Defs/MenuCommonParam.xml`
  and `https://www.nexusmods.com/eldenring/mods/4503`

**Community wishlist threads** (the ranking's sentiment input):

- The maintained community guide, pinned on r/shadps4 and r/BloodbornePC:
  `https://www.reddit.com/r/shadps4/comments/1q4kx50/new_ultimate_mod_list_for_bloodborne/`
- `https://www.reddit.com/r/bloodborne/comments/89ptdm/missed_qol_opportunities_whatre_your_small_pet/`
- `https://www.reddit.com/r/bloodborne/comments/qcb8n1/my_single_largest_complaint_with_the_game/`
- `https://www.reddit.com/r/bloodborne/comments/1e05x9y/qol_changes_in_a_remasterremake/`
- `https://www.reddit.com/r/bloodborne/comments/ouwchm/what_should_be_added_improved_in_a_bloodborne_remaster/`
- `https://www.reddit.com/r/bloodborne/comments/1tft3es/some_qol_changes_i_would_like_to_have/`
- `https://www.reddit.com/r/BloodbornePC/comments/1qk8pry/bloodborne_having_godtier_qol_mods_on_an_emulator/`
  (the veterans-only sentiment thread)
- `https://www.reddit.com/r/BloodbornePC/comments/1sr18fb/any_mod_to_change_blood_vial_behavior_only_during_boss_fights/`
  (the unfilled request, item H14)

Caveat carried from the web research: `nexusmods.com` page HTML returns 403 to
fetches and Reddit blocks direct fetching, so a few of those facts come from
search snippets and mirrors. Everything sourced from the Nexus **API**, from
GitHub raw files, and from the local filesystem was read verbatim.

**Our own prior work** (all paths relative to `~/couch`):

- `docs/research/bloodborne-enhanced-settings-20260824.md`: the 51-setting
  table, the flag encoding, and settings 20/21 sitting on Hunter's Dream.
- `docs/research/bloodborne-lamp-saga-20260826.md`: the overlay-vs-patcher
  failure and the "a set flag proves enabled, not delivered" rule.
- `docs/research/ds3-ui-iteration-speed-20260902.md`: the Scaleform pipeline
  that makes item D1 plausible.
- `data/bb-hks/FINDINGS.md`: the hksc build, the working compiler, the failed
  decompiler, and the bytecode-level conclusion this document supersedes.
- `data/bb-hks/BEHAVIOUR-FINDINGS.md`: the HKX round trip, the hkxpack-souls
  toolchain, the "graph gates nothing" result, the dash animation inventory,
  and the not-being-loaded suspicion.
- `data/bb-hks/ref/`: **two complete Lua sources of `c0000.hks`.**
- `tools/bb-cheat` (the `Address = offset + 0x400000` rule), `tools/bb-lockon-sprint`,
  `tools/bb-anibnd-swap`, `tools/souls-extract`, `tools/bb-durability-patch.py`.
