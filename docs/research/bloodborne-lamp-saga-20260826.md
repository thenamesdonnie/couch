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

## 31 Aug 2026: script/ PUT BACK IN (retry), and what its absence had cost

Discovered while chasing a Cainhurst runback complaint: **a lamp is a talk
object**, so keeping `script/` vanilla did not just cost NPC dialogue - it made
the mod's entire lamp menu inert. Specifically dead the whole time:
Lamp Menu (+ Warp / Level Up / Workshop / Storage / Messengers / Boss
Rematches), **Quick Warp to Bosses** (the Stakes-of-Marika runback skip), and
the Doll's **"Enhanced Features" settings menu** - i.e. all 46 supposedly
in-game-toggleable settings have never once been reachable.

The trap that hid it: `bb-eventflags.py --mod-settings` reads `Quick Warp to
Bosses` (12100857) and `Prompt Quick Warp to Bosses` (12100893) as **ON** in the
live save. The flag being set only means the setting is enabled; it says nothing
about whether anything can deliver it. Donnie had never seen a single prompt.

Retry rationale: the 26 Aug bisect convicted `script/`, but the suspected cause
was a stale talk-flow flag left by that session's freeze/OOM, "sidestepped
rather than explained". Clean save, so worth one honest test.

Done: saves snapshotted (`20260831T132421Z-6da4c59c5a5a.tar.gz`), then
`bb-bisect install script` (19 files, 0 added files, so revert is a pure
restore). `param/` deliberately untouched - it carries the 9999-durability
patch and reads "vanilla" to bb-bisect status for that reason.

**Panic lever: `tools/bb-script-revert`** (and `--check` to ask which state the
dump is in). NOT play-tested at time of writing - the verdict is whether a lamp
still responds on the next launch.

### VERDICT (same evening): RETRY FAILED, script/ IS THE CAUSE. DO NOT RETRY.

Lamps died again on the first launch, on a clean save with no freeze/OOM in the
session. That kills the "stale talk flag" theory outright and convicts the files
themselves for the second time. Reverted with `tools/bb-script-revert` (19 files,
verified VANILLA). **Treat script/ as permanently out unless the root cause below
is actually solved - it is not a coin flip, it is 2 for 2.**

Standing consequence: the runback stays, `Quick Warp to Bosses` stays inert
despite its flag being ON, and the Doll's settings menu stays absent, so any mod
setting Donnie wants changed must be done by writing the flag into the save
(group 12100 = slot 50; flag ids for all 51 settings are in the archive's
`_data/settings.json` under `PossibleValues`). bb-eventflags.py reads; a writer
is ~10 lines on top of it and is the obvious next tool if he wants a setting.

~~UNTESTED LEAD: the patcher.~~ **CLOSED THE SAME EVENING - IT IS NOT THE
PATCHER.** gpt-5.6-sol was pointed at the extracted archive (report +
adjudication in `docs/audits/bloodborne-lamp-script-20260831-*.md`) and the
decisive fact is verified: **the patcher copies `_data/script/talk` to its
output verbatim**, and all 17 of those files are md5-identical to the
`GAME FILES/dvdroot_ps4/script/talk` ones we already install. Running it would
install the same failing bytes. Also verified: our install is NOT incomplete -
the packaged mod byte-matches the live dump in chr 1/1, event 18/18, menu 40/40,
msg 42/42, parts 4/4, sfx 2/2 and 2178 sampled map files, zero differences.
Do not spend an evening reimplementing the patcher on Linux.

**Where the fault actually is:** the mod replaces the talk script of EVERY lamp
in all 16 maps, rewriting the lamp setup call from 7 arguments to 8 to register
a new ActionButtonParam `6103` ("Glimpse into the Hunter's Dream") plus a lamp
index. That param row and its message text are both present and installed, so it
is not a missing row. Which part the runtime rejects cannot be read out of static
bytes. NOTE the ESD-internals detail in that report is UNVERIFIED by us; the
table above is what was checked.

**Cheapest decisive next test** (needs Donnie at the TV, his agreement, and a
save WRITER which bb-eventflags.py does not yet have): install `script/`, set
`12100972 = 1` / `12100872 = 0` in the save so Lamp Menu is Disabled, touch a
lamp. Prompt returns = the ESD loads and the fault is in the enhanced branch;
prompt still absent = the mod's own disabled fallback is broken too and the
expanded setup call is the culprit.

**The side-door worth more than the lamp menu:** `m21_00_00_00.talkesdbnd.dcx`
entry `t210304.esd` grows 34,488 -> 124,512 bytes and carries 100 of the 113
setting flag ids. A hybrid BND keeping the stock Hunter's Dream lamp entries but
taking the mod's `t210304` might restore the Doll's "Enhanced Features" menu
WITHOUT touching any lamp - i.e. make all 46 in-game settings reachable for the
first time. Untested.

### Two Reddit leads, assessed 31 Aug

Donnie found two community answers to the same symptom. Assessment:

**1. "Your mods are conflicting" (they had an SFX mod + Enhanced). RULED OUT
for us, with evidence.** Every category the lamp flow touches is byte-identical
to Enhanced's own packaged output on our dump: chr 1/1, event 18/18, menu 40/40,
msg 42/42, parts 4/4, sfx 2/2, 2178 sampled map files, zero differences. The only
other mod installed is the Vertex Explosion Fix, and its file list is entirely
`parts/fg_a_*` FaceGen - no overlap with talk, event, param, msg or map. There is
nothing here to conflict.

**2. "Put the optional files from the enhanced folder into the game folder."
Looks like STALE advice for an older release, but not fully closed.** The archive
we hold (`FullPackage19mod.0.11.2-fix9`) contains exactly one OPTIONAL folder:
`OPTIONAL CHEATS/gems/dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx` - a
single replacement param giving all blood gems. That is a cheat, not a lamp fix,
and installing it would clobber our 9999-durability patch. `filelist.txt` has no
other "optional" references. The Nexus mod page reportedly states there are **no
longer any OPTIONAL FILES required for shadPS4**, which fits the theory that the
advice predates our version.

**OPEN, and only Donnie can check it** (nexusmods returns 403 to WebFetch without
an account): on mod 19's Files tab, (a) is there an Optional Files section with
anything in it, and (b) **is there a release newer than 0.11.2-fix9?** Ours was
downloaded 23 Aug 2026. A newer build that fixes this would be far cheaper than
the ESD surgery described above.
