# Adjudication: sol's lamp-prompt investigation, 31 Aug 2026

Raw report: `bloodborne-lamp-script-20260831-sol.md`. Brief:
`../bloodborne-lamp-codex-prompt.md`. One reviewer only (Donnie asked
specifically for Codex), so there is no blind second opinion to converge
against; everything below is my own check of sol's claims against the files.

## Verified, and these settle the question we asked

| Claim | Verdict | How I checked it |
|---|---|---|
| The patcher copies `_data/script/talk` to the output **verbatim**, so running it would install the same failing bytes | **CONFIRMED** | All 17 `_data/script/talk/*.talkesdbnd.dcx` md5-match the `GAME FILES/dvdroot_ps4/script/talk` copies exactly. Nothing transforms them. |
| Our install is complete in every non-script category | **CONFIRMED** | Byte-compared the packaged mod against the live dump: chr 1/1, event 18/18, menu 40/40, msg 42/42, parts 4/4, sfx 2/2, map 2178 sampled, **zero differences**. |
| `12100972` = Lamp Menu **Disabled**, `12100872` = Lamp Menu **Enabled** | **CONFIRMED** | `_data/settings.json`, `PossibleValues` for "Lamp Menu". |
| The mod's `m24_01` talk archive is enormously larger than stock | **CONFIRMED** | Decompressed payloads: mod 1,433,072 bytes vs vanilla 568,518. |
| BND entry naming, e.g. `N:\SPRJ\data\INTERROOT_ps4\script\talk\m24_01_00_00\t241000.esd` | **CONFIRMED** | Read the BND4 name table directly; the first four entries are exactly as quoted. |
| The Disabled flag is referenced by the mod's lamp talk and the stock one never mentions it | **CONFIRMED at archive level** | `12100972` little-endian appears 7 times in the mod's m24_01 payload, 0 times in vanilla's. |

**So the headline answer is sound and the lead I had written into the lamp-saga
doc is dead: the patcher is not the missing step.** Delete that as an
explanation, it cannot be one.

## Not verified, and one wording slip

- **"`12100872` (Enabled) does not occur in this ESD."** Sol scoped that to
  `t241000.esd`. I only counted across the whole `m24_01` archive, where it
  appears **4 times** — which does not contradict it (the archive holds 33
  scripts including the added `t241029`), but does not confirm it either.
  Anyone relying on that branch analysis should split the BND per entry first.
- **The ESD internals** — command record offsets, the 7-argument to 8-argument
  setup call, the `6103` argument, the evaluator bytes at `0x259a3` — are
  **unverified**. They are specific and self-consistent and I have no reason to
  doubt them, but I have not read those offsets myself.
- Sol writes the ESD magic as `fSSL`; it is actually **`fsSL`** (33 entries in
  m24_01). A transcription slip, not a substantive error — its container
  reading is otherwise exactly right.

## What this changes

1. **The patcher lead is closed.** Nobody should spend an evening
   reimplementing `BBEnhancedPatcherGUI` on Linux hoping it fixes lamps.
2. **The install is not incomplete.** Every category we ship matches the mod's
   own output byte for byte, so "we installed it wrong" is also dead.
3. The cause is inside the mod's replacement lamp scripts themselves, which
   rewrite **every lamp in all 16 maps** to register a new ActionButtonParam
   (`6103`, "Glimpse into the Hunter's Dream") with an added lamp index. Static
   bytes cannot say which part the runtime rejects.

## The proposed experiment, and why it is not run yet

Sol's cheapest decisive test: install the mod's `script/`, then set
`12100972 = 1` and `12100872 = 0` in the save (group 12100, slot 50) so Lamp
Menu is Disabled, and touch a lamp.

- Prompt returns → the ESD loads fine, the fault is in the enhanced branch.
- Prompt still absent → the mod's own disabled fallback is broken too, and the
  unconditional expanded setup call is the culprit.

**It needs three things we do not have right now:** a save *writer*
(`bb-eventflags.py` only reads), Donnie physically at the TV, and his
agreement, because the test deliberately reinstalls the thing that breaks his
lamps. It also writes to his live save. Not to be done unilaterally.

## The more interesting side-door

Sol notes `m21_00_00_00.talkesdbnd.dcx` entry `t210304.esd` grows 34,488 →
124,512 bytes and carries 100 of the 113 setting flag ids. A **hybrid BND**
keeping stock Hunter's Dream lamp entries but taking the mod's `t210304` might
restore **the Doll's "Enhanced Features" settings menu without touching any
lamp**. That is the thing actually worth having: it would make all 46 in-game
settings reachable for the first time on this install. Untested, and it does
not restore the lamp menu or Quick Warp to Bosses.
