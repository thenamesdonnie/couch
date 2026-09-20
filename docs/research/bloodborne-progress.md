# Bloodborne playthrough ledger (Donnie-safe: contains nothing he doesn't know)

Companion state for the nudge service. Assistant: read this + the
SPOILERS guide (bloodborne-nudge-guide-SPOILERS.md, NEVER quote it to him)
before answering any game question. Update this file at every milestone.

## The service rules (agreed 26 Aug 2026)
- Nudges are DIRECTIONS + DEADLINES only ("talk to X before killing Y").
  Never outcomes, never reasons, never trajectory answers ("will X happen
  to this character" is refused on principle).
- **ASSUME VANILLA (28 Aug).** "What's this attack / door / thing" is
  CURIOSITY, not a bug report. Answer it as normal game content (wiki
  lookup is fine). Do NOT audit mod files, the save or the emulator log
  unless HE frames it as broken, or it cannot be vanilla. His words:
  "bloodborne is full of mysteries and im just curious".
  **AND DO NOT SAY IT EITHER (29 Aug, he had to repeat himself).** No "that's
  vanilla", no "not a bug", no "you haven't broken anything" - not even as a
  clause. He knows, and he will report breakage himself. The assumption is
  silent. Just answer, or just enjoy the moment with him.
- **SWEEP PROTOCOL (agreed 28 Aug, his idea).** He explores an area fully, then
  reports WHAT HE FOUND. Assistant speaks only to the GAPS, never lists back
  what he already has. Hints are TIERED and he chooses the escalation:
  (1) how many things missed + the kind of each (item / route / person /
  shortcut), (2) roughly where, (3) exact. Default is tier 1; do not volunteer
  tier 2+ unless asked.
  **EXCEPTION: deadlines never wait for the sweep.** Anything that becomes
  permanently unavailable before he finishes exploring gets raised immediately
  and unprompted (as with Eileen/Henryk and the Afflicted Beggar). Missables
  are the clock, not secrets.
- **DIRECTIONS MUST NOT NAME THE DESTINATION (29 Aug, his callout).** Saying
  "the cave leads to Iosefka's Clinic" spoiled the reveal at the end of the
  route. Route him by LANDMARKS ONLY (lamp, dog cages, side path left, winding
  steps, poison swamp, ladder) and let the place announce itself when he gets
  there. He raised it mildly and said it was okay, but logged as a rule.
- No-stakes choices get "follow your gut, nothing mechanical hinges".
- He reports sends/choices AFTER making them; assistant confirms whether
  anything needs flagging, still without outcomes.
- The mid-game hard watershed: assistant must loudly say "settle everyone
  now" BEFORE he reaches it. This promise is load-bearing.
- His four sensors (taught, he uses them): exhaust dialogue to the loop;
  judge people by how they speak of others; incense logic (would the
  beast-warding incense object); circumstances they're found in.
  Plus: the send system announces itself - no offer, no stakes.

## Progress (updated 3 Sep 2026: Logarius dead, Vileblood joined, Summons given to Alfred - see the 3 Sep entries at the bottom)
- 31 Aug: **HE IS IN CAINHURST, AT THE ROOFTOP BOSS** (asked for tips, then
  "what resistance do i need, his spells do so much damage"). So the summons
  chain is running and the lake is still untouched. Given, combat only:
  parry-into-visceral is the win condition, stay close or he casts, the
  planted-sword AoE can be SHOT to destroy it early, pillars break the skull
  volleys, Bolt Paper (he resists fire/arcane/bolt... i.e. do not bring
  molotovs), all his spells are ARCANE, wear the Black Church Set (280 arcane
  vs the Doll Set's 150), and Bloodborne has no resistance stat so Vitality is
  the real mitigation. Boss NOT named to him, nothing about what is behind him.
  **FLAG ALREADY GIVEN AND STILL OPEN: he must ping before handing anything to
  Alfred** (order matters: join the queen first if he wants both). Do not let
  that slip, and Eileen's post-Rom beat is still on me.
- 31 Aug: the sprint-roll annoyed him ("disable the jump?"). I first said L3,
  he TESTED IT and it is circle-after-sprint, i.e. the sprint roll doubling as
  the gap jump - same button, state-dependent, so no remap can fix it. Offered
  the Nexus mod "Jump on L3" (mod 156) as an after-the-fight job: he downloads
  to ~/fileshare/bloodborne-mods, bb-mod-install does the rest, and CHECK A LAMP
  before he commits a session (behaviour layer = the lamp saga layer).
- 31 Aug: **RUNBACK: "can we turn on spawn at boss" - NOTHING TO DO, IT IS
  ALREADY ON.** Enhanced's `Quick Warp to Bosses` (12100857) and `Prompt Quick
  Warp to Bosses` (12100893) both read ON in the LIVE save (checked with
  tools/bb-eventflags.py --mod-settings against
  ~/.local/share/shadPS4/home/1000/savedata/CUSA00900/SPRJ0005/userdata0000).
  It is the mod's Stakes-of-Marika: once a boss is met and until it dies,
  nearby lamps get a warp entry straight to the arena, and the prompt auto-pops
  on respawn. Told him no restart needed (read-only check, flags set since
  install), and that if the entry is genuinely absent it may be a script/-less
  menu gap and I want to hear about it.
  RED HERRING RULED OUT: `Broken Lamp: Death Respawn Location` (12100859 =
  Boss Lamp) applies ONLY to broken-lamp rematches, not first kills.
  Full flag map for all 51 settings is in the mod archive at
  `_data/settings.json` (PossibleValues gives both flag ids per setting) -
  the tool's MOD_SETTINGS list only covers 12 of them.
- 31 Aug: asked where to get Blood Stone Chunks. Told: Cainhurst is the best
  pre-lake source (~5), costs are 3/5/8 = 16 chunks for one weapon +6 to +9,
  so he cannot climb two, and to spend nothing above +6 until the Ludwig's
  decision is made. Future sources given WITHOUT names: buyable with Insight
  from the bath messengers at a later point (I flag when live - this is the
  payoff for his banked Madman's Knowledge), plentiful after the lake, and
  chalice dungeons as the infinite farm if he ever wants it.

## Progress (updated 29 Aug 2026, evening)
- 29 Aug: **SHADOWS OF YHARNAM DEAD.** Forbidden Woods is cleared, Byrgenwerth
  is open, and **the watershed is now literally the next thing** (the lake off
  the Byrgenwerth pier IS Rom). Bosses: Cleric Beast, Gascoigne, Witch, BSB,
  Paarl, Amelia, Shadows.
  **THE LOAD-BEARING WARNING WAS DELIVERED** (settle everyone before the lake).
  Told: Byrgenwerth itself is safe to walk into and to talk to the man in the
  rocking chair, the pier/lake is the line, no outcomes given.
  Open pre-Rom business handed to him, deadlines only:
  1. **BEGGAR SENT TO THE CLINIC (he reported it after the fact) - this is a
     SAFE play.** The chapel roster (Adella, Arianna, Lonely Old Dame) is out
     of danger and cord C's chapel risk is now only the Adella jealousy one.
     Told only "nothing to flag" plus "there is something worth collecting at
     the clinic later, I will raise it when it is live" (= Beast rune off the
     mob post-Rom, NOT named).
  2. Poison cave ladder at the far end of the Woods -> back door of the clinic.
     Item on a table there opens an optional region + a whole NPC chain that
     wants finishing pre-lake. TRAP GIVEN: do not attack the woman upstairs,
     it costs something permanent (cord B, not named).
  3. Alfred is still waiting on the balcony; his chain runs through that item.
  4. Hypogean Gaol full sweep if never done (that area changes at the lake).
     Adella herself is already safe at the chapel, so only loot is at risk.
  5. Visit the window people, incl. Gilbert, before the lake. Last chance.
  6. Never drink Blood of Arianna (standing).
  7. **CORD A CONFIRMED HELD.** He looted the whole Abandoned Old Workshop and
     gave the Small Hair Ornament to the Doll (so the Tear Stone is his too).
     Cord tally: A held, D unmissable, B is post-watershed, C rides on Arianna.
  8. **He refused to re-sweep the Woods ("it all looks the same") and asked for
     tier-3 directions instead - GIVEN, from the Forbidden Woods lamp:**
     (a) Valtr = the shortcut hut right beside the first lamp; if its door is
     still barred he has not run the elevator yet and must come up from below.
     Framed as an optional oath rune, no deadline, DLC NPC so "if he is not
     there, no loss".
     (b) The cave = main path down from the first lamp to the dog cages/kennels
     shacks, side path off to the left of the cages, winding steps down
     (antidotes on the way), poison swamp with the big Church Giants (run it,
     do not fight), ladder at the far end, up into the clinic's back courtyard.
     Told to take the summons off the table, that it opens an optional region
     reached from the Hemwick crossroads obelisk he was already shown, that
     the region ends in a proper boss, and that the chain it starts is what
     eventually gives Alfred his item. Do it before the lake to be safe.
     TRAP RESTATED: do not attack the woman upstairs in the clinic.
     Sources: Fextralife Forbidden Woods + Valtr pages, bloodborne-guide
     tumblr walkthrough. Route corroborated across three sources.
  9. He will not tour the window NPCs; **only Gilbert was asked for.**
  10. **CAINHURST SUMMONS OBTAINED 29 Aug.** He ran the cave, came up the
     ladder, opened the clinic door from the inside, saw the operating room and
     the Celestial Mobs, and took a blood vial off her. He did NOT attack her
     (trap restated twice, held). He asked outright "is the woman upstairs the
     one I was speaking to" - answered YES, plain object identity only, and
     nothing about impostor/cord B. **He is piecing the clinic out himself, do
     not get ahead of him.** Deliberately did NOT tell him the Celestial Mobs
     are the people he sent.
  11. **SEND SYSTEM IS EFFECTIVELY CLOSED: all six are placed.** Adella,
     Arianna, Lonely Old Dame -> chapel; Skeptical Man, Suspicious Beggar ->
     clinic; Young Girl brooched (out of the system, stays indoors). Told him
     sends still pay out until the lake but there is nobody left to send.
  Weapons thread: wants a STRENGTH mainstay. Told Kirkhammer is already
  buyable (3,000, Cleric Beast badge) as a cheap feel-test, Ludwig's Holy Blade
  is the destination (20,000 + Radiant Sword Hunter Badge, chest on the top
  floor of the Healing Church Workshop, looks like the wall coffins), Str 16 /
  Skl 12, and that the real cost of switching is re-climbing to +6 in Twin
  Shards. Told to keep the Cleaver as the beast killer. Stats never given.
  Insight: 21 lost to a Brainsucker grab at Byrgenwerth (2 per grab, permanent);
  he holds 27 Madman's Knowledge. Advised to bank them and stay under 15 for
  the Frenzy and enemy-upgrade thresholds, spending one only to wake the Doll.
  Eileen's next beat is still post-watershed and still on me to raise.

## Progress (updated 28 Aug 2026, morning)
- 28 Aug: **DARKBEAST PAARL DEAD** ("that spark boss just outside the gaol
  area"), so he reached Hypogean Gaol / Yahar'gul via the Snatcher route and
  went down. Bosses now: Cleric Beast, Gascoigne, Witch of Hemwick, BSB, Paarl.
  **RISK CLOSED 28 Aug: he HAS the Black Church Set.** He had been searching
  the right alley off the emblem gate but missed the immediate left behind the
  cart; given the exact route and found it. Told only the CHEST slot is
  checked. Still owed: the return lap of the Gaol wearing it, before Rom.
  Deliberately NOT told what Adella does or that she can be sent anywhere -
  outcomes stay withheld, he reports sends after making them.

- Checkpoint: OLD YHARNAM entered (via the Cathedral Ward descent). The
  m23 silent crash did NOT repeat on the same hallway; bb-crash-watch
  armed for any future death (see todo.md item 2).
- 29 Aug: **IOSEFKA'S CLINIC IS UNLOCKED as a second send destination** - and
  note it STILL WORKED post-Amelia. I had warned him it was "probably" closed
  by that fight; it was not. Do not repeat that caution. Route that actually
  works, stated simply: first lamp, turn around, up the stairs (I gave him a
  waffly landmark version first and he rightly called it out).
  **Current housing: Adella + Arianna + Lonely Old Dame at Oedon Chapel; the
  Narrow-minded/Skeptical Man at the clinic.** The last one was NOT a fumble -
  he does the opposite of whatever he is told, and at the time the chapel was
  the only destination available, so the contrarian send was unavoidable.
  Identified from the reward item (Numbing Mist = adult, Lead Elixir = the
  girl) rather than by digging the save - remember that discriminator.
  **Sends are now a REAL choice with two destinations: the ask-me-first rule
  matters more from here.**
- 29 Aug: **PATCHES IS ACTIVE** (triggered by entering the Forbidden Woods): he
  replaces the occupant of any RED-LANTERN window in Yharnam, incl. Gilbert's,
  and re-greets from scratch at each one. Donnie flagged it as a suspected bug;
  install was checked (talk scripts confirmed byte-identical to vanilla - the
  26 Aug mtimes are the RESTORE, not an install) and the dialogue was confirmed
  verbatim base-game. Not a bug. He worked out it was Patches himself.
- 29 Aug: **AFFLICTED BEGGAR HAZARD CLEARED - he did NOT send him.** Found him
  in the Forbidden Woods sat eating three corpses and read it himself; the
  pre-warning (ask before any chapel send) did its job and the chapel
  residents are safe. Not killed either, which is fine - no deadline on that
  choice. He is in the Forbidden Woods now and has met the Small Celestial
  Emissaries; told only that the TENDRILLED ones cast and hit hard.
- 28 Aug night: **VICAR AMELIA DEAD (first try)**, skull touched, password
  obtained, world is now NIGHT. Bosses: Cleric Beast, Gascoigne, Witch, BSB,
  Paarl, Amelia. Lore given only to the level the game had already shown him
  (vicar = head of the Healing Church, blood ministration, the rosary); deeper
  reveals deliberately withheld. He also has the **TONSIL STONE** (red-lantern
  house) - told NOT to use it yet: the area behind the grab is over-tuned for
  him and full of Frenzy, which his high Insight makes lethal. No deadline.
- 28 Aug night: **EILEEN DEADLINE RESOLVED - he helped her kill Henryk** at the
  Tomb of Oedon, in time (before first entering the Forbidden Woods). Told to
  loot Henryk for the Heir Rune and to talk to her for the Approval gesture.
  His lamp warp failed because he had never lit the Tomb of Oedon lamp, NOT
  because of the fight - corrected that. **NEXT EILEEN BEAT IS ON ME TO RAISE:
  she reappears at the Grand Cathedral after Rom, and it is a very hard hunter
  fight.** He has been promised I will flag it, so do not let it slip.
- 28 Aug: **ABANDONED OLD WORKSHOP REACHED** (the §127 nudge landed). He got
  there himself after the exact drop route: left edge near the ropes, walk off
  onto the small ledge, then the bigger one. He struggled because he was trying
  to JUMP - the unblocker was "you walk off an edge, there is no jump here".
  He spotted the Dream connection unaided and was thrilled; deliberately told
  NOTHING further about it. Told to clear the area fully (cord A is the reason)
  and to leave by Hunter's Mark, no lamp down there. **Confirm he actually
  picked the cord up before he goes through the cathedral boss.**
- 28 Aug: Saw Cleaver **+6 at level 43** - cleared as ready for the cathedral
  boss. Pre-boss kit given: Molotovs (she is a beast), Numbing Mist, Sedatives.
- 28 Aug: **CHAPEL ROOMMATE HAZARD IS LIVE.** He sent BOTH Adella and Arianna
  to Oedon Chapel (found Adella after a Dream round trip). **He is holding
  Blood of Arianna, 1 of the 3 acceptances that triggers the murder.** He has
  been told: never drink it, it is a plain consumable (25% HP + stamina regen,
  needed for NOTHING later), and since you can only hold one and she only
  regifts after you drink, never drinking keeps him at 1 forever. Adella's
  blood is safe but currently blocked by holding Arianna's. Outcome deliberately
  withheld. **NEW STANDING RULE given: he asks BEFORE any future chapel send.**
- 28 Aug: high **INSIGHT** noticed and correctly self-diagnosed by him (lamp
  Church Servants gained projectiles; Lesser Amygdala visible on the chapel,
  needs 40+ pre-Rom). Told: unkillable scenery, its grab is Frenzy, Insight
  raises Frenzy damage taken, and SPENDING insight lowers the counter.
- 28 Aug: **BLOOD-STARVED BEAST DEAD.** Post-BSB chain is now LIVE and he
  has been briefed on it: Snatchers spawn in Yharnam/Cathedral Ward, dying
  to one = Hypogean Gaol, explore it fully WEARING A HEALING CHURCH CHEST
  PIECE (Adella only responds then), and the Gaol has the back door into
  Old Yharnam behind Djura. **DEADLINE: all of it before Rom** (Gaol lamp
  breaks, Adella gone). Healing Church Workshop door also unlocks on this
  kill. Bosses so far: Cleric Beast, Gascoigne, Witch of Hemwick, BSB.
- 28 Aug: **Witch of Hemwick DEAD** (fought at 0 Insight, so no Mad Ones -
  told him this deliberately before he went). Rune Workshop Tool obtained,
  rune equipping unlocked. Boss kill = +1 Insight, so the Doll animates
  again. Told about the Hemwick crossroads obelisk being a later-return
  landmark. The "hunter tied to a chair" was a CORPSE holding the Rune
  Workshop Tool - resolved, nothing missed. An NPC in a wheelchair pointed
  him to the Healing Church Workshop; gave him the §127 nudge (the
  drop-down inside the tower to the Abandoned Old Workshop, which players
  routinely never find - holds cord A [ending-relevant], Doll set, Small
  Hair Ornament, Old Hunter Bone). NOT time-limited.
- 27 Aug: went to Old Yharnam, fought BSB (died, then the m23 wedge - see
  Tech state). Told BSB is optional; routed him back to Cathedral Ward for
  the emblem-gated main path. Now in Cathedral Ward (m24_00 confirmed from
  the emulator log), killed a hostile HUNTER enemy there with the help of a
  summoned NPC (his first co-op summon). Standing at door NPCs ("bless us
  with blood") - the send system is open and he has been told sends carry
  stakes and to report each one. Combat taught: parry-into-visceral is the
  answer to hunters; close the distance against firearms.
- Nudges given on Old Yharnam arrival: confirm the Alfred first-talk near
  the Old Yharnam route was done (accept cooperation); the hostile hunter
  in Old Yharnam is a no-deadline choice, nothing mechanical lost either
  way, a non-hostile approach exists later; standing door-knock + chapel
  visit reminders repeated.
- Previous checkpoint: POST-GASCOIGNE. Cathedral Ward entered, Oedon
  Chapel found and lamp lit, Chapel Dweller met.
- Bosses: Cleric Beast, Father Gascoigne.
- Done: elevator shortcut; Tiny Music Box obtained (used vs Gascoigne);
  Red Jeweled Brooch found and GIVEN to the girl (told her nothing about
  the chapel); Flamesprayer from Gilbert; Eileen met at first location,
  dialogue exhausted (standing orders given: talk when seen, side with
  her against any hunter); Lonely Old Dame sent to CHAPEL (confirmed fine).
- Weapons: Saw Cleaver (+music box, Hunter Pistol, Flamesprayer). Saw
  Spear pointed out, not confirmed taken.
- Open nudges he holds: knock doors in Cathedral Ward as he explores;
  visit chapel tenants after each milestone; keep checking Gilbert.

## Tech state (game side)
- Bloodborne Enhanced runs MINUS script/ (talk scripts vanilla) after the
  lamp saga - see bloodborne-lamp-saga-20260826.md. Auto Refill works.
- Durability (26 Aug ~23:55): Enhanced's Infinite Durability is BROKEN AS
  SHIPPED (flag 12100855 set, event 12102069 applies SpEffect 1331,
  insideDurability -150/10s - engine ignores it; known upstream, the
  "Enhanced Enhanced" patch mod fixes it). Our fix: durability/durabilityMax
  = 9999 on all 2107 EquipParamWeapon rows, in-place (tools/
  bb-durability-patch.py; backup data/bb-param-backups/). Effective NEXT
  launch. NOTE: a bb-bisect param reinstall WIPES this - re-run the patch
  after any param category install.
- Debug emulator build, 1440p internal (he has explicitly refused 1080p),
  Fifo-vs-Mailbox present question open (Mailbox free-runs during loads).
- 28 Aug 07:24: emulator REBUILT with the texture-cache GC census + budget fix
  (shadps4-dbg `1fdc058`, see shadps4-reload-stutter-20260828.md). Aimed at the
  death-reload choppiness. NOT play-tested - first suspect if anything looks or
  runs worse. Kill switches: `touch ~/couch/data/shadps4-gc-fix-off` for the
  control arm, `rm ~/couch/data/shadps4-local-build` for the stock AppImage.
- OPEN MYSTERY: GPU pins 100% (usual 50-60%) with frametime chaos during
  normal gameplay; first episode min 62-64 of the 18:42 session; MangoHud
  showed presents up to 4372fps at max clocks/176W. tools/gpu-spike-watch
  armed (6h self-expiring) to attribute per-process on next episode.

## 31 Aug 2026 (late): CHEATS, because Logarius stopped being fun

He asked outright for an invincibility mode ("this fight just isn't fun ...
there's not really much counterplay"). Delivered, and it is his game, so no
hand-wringing about it - but note for the companion service that the blind-run
rules still apply to INFORMATION. Cheats are a difficulty valve, not a licence
to start narrating what is coming.

**`tools/bb-cheat`** (new). Enables shadPS4's official cheats for Bloodborne
without the Qt GUI, which is unreachable here (SDL build, no keyboard/mouse at
the TV). Available: Infinite Health, Infinite Stamina, 1 Hit Kill, Infinite
Items, Infinite BloodEcho, Infinite Lucidity.
  * Cheat file: `~/.local/share/shadPS4/cheats/CUSA00900_01.09.json` (fetched
    from shadps4-emu/ps4_cheats).
  * Boot mode: rewrites them as `<Metadata>` blocks into the SAME XML the 60fps
    unlock uses (`patches/shadPS4/Bloodborne.xml`), which the SDL build applies
    automatically at eboot load. Blocks are tagged `couch-cheat: ` so upstream's
    59 blocks are never touched; verified 59 -> 61 blocks, 2615 patch lines intact.
  * **Address rule (verified in src/common/memory_patcher.cpp, not guessed):**
    a cheat JSON offset is eboot-relative, an XML Address is an absolute PS4 VA
    and the emulator subtracts 0x400000. So `Address = offset + 0x400000`.
    `Type="bytes"` values are raw hex pairs, NO 0x prefix.
  * Live mode: `bb-cheat live on|off|status`. Writes the bytes into the running
    process at `0x800000000 + offset` (eboot base is fixed; it is the first
    `base_virtual_addr` line in shad_log). Verifies the current bytes match
    either the patched or the original set before writing, and reads back after.
  * **Needs `sudo sysctl kernel.yama.ptrace_scope=0`** (scope is 1 by default,
    which forbids cross-process memory writes). Handed to Donnie to paste.

## 3 Sep 2026: Logarius down

Beaten. Companion notes: keep to mechanics-only until he asks for more; no
spoilers about what follows.

## 3 Sep 2026 (later): Logarius, Alfred, Vilebloods

Confirmed: gave the Unopened Summons to Alfred, joined the Vileblood
covenant. Beat Logarius at character level 52 (community-recommended ~75).
Order was the safe one (queen first, then Alfred), so both chains stay open;
told him nothing was lost. Given, directions only: Alfred's chain has TWO more
beats, the throne room in Cainhurst first, then the spot where he first met
Alfred in Cathedral Ward (left-side door by the Old Yharnam lever), pick up
anything left lying in either place, and do both before the lake (the
anecdotal Blood Moon vanish). NOT told what he will find (Annalise pulped,
Roar gesture, Alfred's corpse + Radiance rune, Queenly Flesh / Altar of
Despair revival - all withheld; the Queenly Flesh payoff is post-Rom and on me
to raise when live). Told the Wheel Hunter Badge he now holds puts a STRENGTH
weapon in the Dream shop (his mainstay ask). Vileblood side: no deadline, no
outcome given. Rom is still the next line; pre-lake list unchanged (Alfred
beats, Gaol return lap in the Black Church Set, Gilbert, Tonsil Stone optional).
Eileen's post-Rom beat still on me.
- 3 Sep: **GILBERT VISITED** ("why did the gods do this to me", he has gotten
  a lot worse). The pre-lake visit is done; Flamesprayer was already his.
  Nothing flagged, no trajectory given (his transformation and what it drops
  are withheld). Pre-lake list: Alfred's two beats, Gaol lap, Tonsil Stone opt.
- 3 Sep: the crash at the Crown cutscene was read from the core dump: a
  stock-engine HUD race at the scene transition (equip + cutscene in the same
  second), nothing to do with the sprint or FOV patches. Both re-enabled.
- 3 Sep: Jump on L3 (Modern: jumps standing still) installed, merged with the
  lock-on sprint; not yet play-tested. Ask him to check a lamp on first load.
- 5 Sep: **HE FOUND WILLEM ("the man in the rocking chair") on the Byrgenwerth
  balcony**, so the Lunarium Key + ladder are done and he is standing on the
  line. Restated: the drop/pier off that balcony is the watershed, do NOT
  follow the gesture yet. Pre-lake list repeated: Alfred's two beats
  (Cainhurst throne room, then Alfred's first spot by the Old Yharnam lever),
  Gaol lap in the Black Church chest, chapel tenants one last time, Tonsil
  Stone optional. Willem's identity/lore withheld; told only to exhaust him
  and watch what he does.
- 5 Sep: **HE FOUND ANNALISE PULPED** ("pop queen vile blood is dead"). Alfred
  beat 1 reached. Told: nothing he held is lost, take what is left in that
  room and KEEP it (never sell/drop), I raise its use when it is live
  (post-Rom, Altar of Despair, still withheld), exhaust whoever is in the
  room, then beat 2 (Alfred's first spot). Who did it and why: withheld, he
  works it out.
- 5 Sep: Lonely Old Dame gave him a Sedative and laughs oddly (post-Amelia
  chapel lines). Nothing flagged; told to keep the Sedative for Frenzy.
- 5 Sep: Gaol lap clarified: the church chest was only for Adella (done);
  only a loot check of the cells remains (Tonitrus, tier 1 as "one weapon in
  a cell"). Willem: told plainly he never speaks, the arm is the whole thing.
- 5 Sep: Pre-lake double-check run against the crib's Blood Moon table: every
  item ticked (sends, Adella, beggar, Eileen/Henryk, Gilbert, brooch, Tonsil
  Stone held, Alfred done, Cainhurst joined + Queenly Flesh held, cord A,
  Gaol looted incl. Tonitrus). Cleared him for the drop. Rom identified as
  "the spider from the notes"; combat tips only (children first, flank, bolt).
- 5 Sep: **ROM DEAD, BLOOD MOON UP** ("ritual secret broken"). He asked if the
  woman in white was "the moon presence" (he knows the name from somewhere,
  probably the trophy list): told NO, she has a name the game gives later,
  nothing more. Also spelled out (his ask) the Logarius/Annalise/Alfred
  reading from lines he already held: Logarius = jailer not prisoner, the
  mask, the crown, Alfred's "freed" master. Read Alfred's and Annalise's
  dialogue back to him verbatim (wikidot), pre-throne-room only.
  **POST-ROM LIVE LIST GIVEN:** (1) Eileen at the Grand Cathedral steps, do
  NOT attack her, talk, the hunter inside is solo + very hard, kill him FIRST
  then talk to her again; (2) clinic rule LIFTED: back door, the woman is on
  the table, what she leaves is another cord (ending-relevant, no deadline);
  (3) the clinic's blue creatures drop their things, the beggar's is worth
  having; (4) check the Insight messenger's stock (chunks expected); (5)
  someone new may be at the brooch girl's window, nothing hinges (no ribbon
  exists); (6) Gaol lamp gone, snatchers gone, new area open.
  STILL ON ME: Queenly Flesh payoff when he reaches Upper Cathedral Ward
  (key in Yahar'gul chapel side room, altar beneath Ebrietas); Micolash ->
  Arianna's baby (cord C) when Mensis is live; Patches forgive at Lecture 2F;
  cords-consumed nudge before the tree.
- 5 Sep: Gilbert killed (Blood Moon beast); told him there was no saving him.
  Adella "heh heh" = Blood Moon line; asked him to report if she ever says
  "tainted" (jealousy armed). Arianna "not feeling well" = Blood Moon, nothing
  said. He quit; **Reborne LIGHTING modules reverted for an A/B** (see memory
  homelab-bloodborne-mods, lever tools/bb-reborne-lighting).
- 5 Sep (evening): **THE ONE REBORN DEAD** (combat tips only: chanters first,
  fire, back legs). Told: the village holds a key (not named, no deadline),
  ping me when he finds what it opens (= Upper Cathedral Ward -> Altar of
  Despair / Queenly Flesh, still withheld). Standing rule given: "if anyone
  ever asks your forgiveness, give it" (Patches, Lecture 2F, rune) with the
  Frontier detour framed as worth doing before the next big boss run.
  STILL ON ME: Micolash -> chapel -> below the chapel (cord C); cords-consumed
  nudge before the tree; Eileen finale still parked (he bounced off the Crow).
  Tech: crash 19:22 = VRAM OOM on a Yahar'gul->Central Yharnam warp with the
  2x textures (buffer.cpp:89 ErrorOutOfDeviceMemory, 9.3->14.2 GB in 10 s);
  Reborne Textures 0-3 reverted; 90 fps armed on 2560x1440@120 + VRR (TV
  FreeSync ON); he reports "pretty stable 90" and PREFERS THE LOOK WITHOUT
  THE MODS. Reborne Flver/Obj still in, offered to pull them next quit.
- 5 Sep: **CORD B CONFIRMED** (clinic table done). Cords: A + B held, C rides on
  Arianna (post-Micolash), D unmissable. Told to hold them until "the tree"
  talk. He is in the Lecture Building ("nightmare library"); told both floors,
  the optional side door (Frontier) before the next boss run, forgiveness rule.
- 5 Sep (late): **EBRIETAS DEAD, QUEENLY FLESH PLACED at the Altar of Despair**
  ("time flows in reverse for this scrap of flesh"). Told him: go back to the
  Cainhurst throne room. Upper Cathedral Ward done (Emissary + Ebrietas).
  Damian summoned once; particle bug on that boss handed to a subagent.
- 6 Sep 00:15: Donnie: "with BB Enhanced the NG+ does not happen
  automatically". CHECKED: Enhanced setting "Prevent Auto NG+" flag 12100873
  (Enabled) = True in the live save, 12100973 = False, and all 18 Enhanced
  event scripts (incl. common.emevd) are byte-identical to the effective
  loaded copies (no patch-dir twins except m29, already handled). Delivery
  never tested; cheap proof = the Doll shows the mod's extra menu (talk layer
  live since 3 Sep). Told him: he is probably right, DLC order is his choice,
  still ping before the tree.

## 9 Sep 2026: endgame, ~2 bosses left, in Nightmare of Mensis
- He is on the Mensis bridge (killed "a character-type NPC" there - asked if it
  was "the frenzy guy / emote" one; told the bridge brides = frenzy enemies not
  quest NPCs, and Make Contact is done at the Brain in the pit, not on them;
  asked him to describe who he killed - no quest NPC lives on that bridge so
  nothing broke, awaiting his detail). Also mixed up Mensis vs Nightmare Frontier.
- ASKED THE BIG THREE (endgame). Answered directions+deadlines only:
  1. **Bloody Crow (Eileen finale):** live now in the blood moon, NO hard
     deadline at his remaining bosses, do before the ending. Grand Cathedral
     steps, don't hit wounded Eileen. Combat tips: solo, parry->visceral,
     Chikage rapid blood loss + Evelyn parry, red blade self-drains. He bounced
     off it earlier; this is the retry nudge.
  2. **Other quests:** told him Alfred / Vileblood+Queenly Flesh / clinic /
     Gilbert / Adella / Upper Cathedral all DONE. Open: Eileen finale; Patches
     forgiveness in the Lecture Building (2F, "give it", rune) - he is IN the
     building now; Arianna cord C after Micolash.
  3. **Third cord / ending 3:** told him he's guaranteed - holds A+B, D drops
     unmissably from a remaining boss (= 3), C (Arianna, below Oedon Chapel
     after Micolash) is a bonus. REAL risk = CONSUME 3 before Gehrman dies;
     "ping me at the great tree" reminder set. Did NOT name Wet Nurse/Gehrman/
     the ending or what cords do.
- STILL ON ME: cords-consumed nudge at the tree; Arianna cord C after Micolash;
  Patches forgiveness (he may hit it this session); Micolash->Arianna baby (C).
- 9 Sep: **MICOLASH DEAD; CORD C TAKEN** (Arianna's newborn below the chapel;
  he hit Arianna by accident, nothing hinges). Cords A+B+C held; D = Wet
  Nurse. Told: her child is "one of them, not the one", the ritual's newborn is
  what he has been hearing. His Oedon-fathered-it theory: told it is the read
  the game's own text supports (Formless Oedon rune, the chapel, her blood).
  Mensis tips given (gaze, lanterns, Blood Rock unnamed, Micolash chase, Wet
  Nurse dark phase). NEXT ON ME: cords-consumed talk BEFORE the tree.
- 9 Sep (late): Wet Nurse dead (first try), Eileen finished (Crow killed at 0
  vials), cord D taken, Make Contact at the brain (Moon rune), the cords
  "sentence" and the whole plot spelled out from his own text, endings
  described by ACTION only (yes / no / no + 3 cords). Save snapshot
  `save-backups/pre-ending-20260909-4cords` (verified). **He did an ending
  and NG+ AUTO-STARTED: Enhanced's "Prevent Auto NG+" flag was ON with its
  scripts loaded and it was NOT delivered** (set flag != delivered, again).
  NG+ save kept as `save-backups/post-ending-ng+-20260909`; pre-ending
  snapshot RESTORED (md5-verified) so he can do the other endings + DLC.
  Which ending he took: not yet told.
