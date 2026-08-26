# The lamp saga - 26 Aug 2026

Donnie, mid-evening: lamps gave no interact prompt anywhere; Great Bridge
showed messengers but no prompt, Central Yharnam showed neither. Ladders and
the Doll worked, so interaction itself was fine. Save flags were read directly
(see below) and were correct. Fixed same night by bisecting Bloodborne
Enhanced 0.11.2-fix9 category-by-category with a purpose-built harness.

## Final state (round 7)

**Full mod installed EXCEPT `script/` (talk scripts), which stays VANILLA.**
`script/` is the convicted lamp-breaker: events-only worked (r2), events+param
worked (r5), events+script broke (r4), events+param+script broke (r3).
Open question, deliberately unanswered: the full mod (script included) worked
24-25 Aug on this same save, so script's breakage is state-dependent -
suspicion is a talk-flow flag left set by one of today's freeze/OOM
interruptions, sidestepped rather than explained by keeping vanilla talk.

## The refill mechanism (decoded from the emevd, event 10008300)

Auto Refill is NOT part of any menu flow. It waits for flag 12100862 (Auto
Refill Enabled) AND the player entering the lamp's PROXIMITY REGION, latches
once via flag 10001509, then applies SpEffects 110-116 (the restock). The
region ID arrives as an Init parameter from the MAP script, and the region
entity exists only in the MOD's MSBs - which is why every config with vanilla
maps had no refill: the trigger region did not exist in the world.
Consequence worth remembering: **the refill needs `map/` + `event/`, and
nothing else.**

## Tools built (all reusable)

- `scratchpad/bb-bisect.sh` - category install/clean/status harness driving
  the dump from the preserved mod copy + extracted archive. Categories: chr,
  event, map, menu, msg, param, parts, script, sfx.
- `scratchpad/bb-investigation/bb_eventflags.py` - READ event flags from a
  Bloodborne save. Block offset is self-describing (u32 at 0x34, len 0x38,
  check 0x3C); 1200 slots x 125 bytes, MSB-first, sub = id % 1000.
  **Known slot mappings (empirical): group 12411 (Central Yharnam) = slot
  170, group 12100 (mod settings) = slot 50, group 5 = slot 5.** The general
  group->slot table is a runtime table in the executable and is NOT known.
- `scratchpad/bb-investigation/` - emevd dumps, the 287-instruction EMEDF
  name table, MSB entity dumps, xref tooling.

## Flag facts verified from the live save

- slot 170 (12411): 700 SET = Cleric Beast dead (agent 1's 700/800 labels
  were SWAPPED vs the wiki convention; the save + reality settled it),
  800 clear = Gascoigne alive, no stuck rematch flags (799/812/813 clear).
- slot 50 (12100): Auto Refill Enabled (862), Kindling Disabled (951),
  Lamp Menu Enabled (872) - i.e. mod settings persist in the SAVE; editing
  the defaults event in common.emevd does NOT change an existing save's
  settings. The in-game Doll menu is the mechanism that rewrites them.

## Traps hit tonight (do not re-walk)

- **Central Yharnam is m24_01, NOT m21.** m21 is the Hunter's Dream. An early
  "revert Central Yharnam's map" reverted the Dream and tested nothing.
- **Partial reverts of this mod produce a BROKEN HYBRID**: vanilla common +
  modded map emevds = 18 unresolvable event inits in m24_01 alone (the mod's
  map scripts call mod-only common events). Never mix; use the harness.
- `bb-mod-install revert` deletes its backup dir on success - copy it first
  (preserved at `data/bb-mod-backups-copy/`).
- Two emulator instances ran concurrently against one save for a while
  (Kodi-tile launch + shell launch). Coordinate who launches.
- Vanilla vial refill on death draws from STORAGE; empty storage = no refill.
