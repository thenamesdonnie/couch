# Bloodborne playthrough ledger (Donnie-safe: contains nothing he doesn't know)

Companion state for the nudge service. Assistant: read this + the
SPOILERS guide (bloodborne-nudge-guide-SPOILERS.md, NEVER quote it to him)
before answering any game question. Update this file at every milestone.

## The service rules (agreed 26 Aug 2026)
- Nudges are DIRECTIONS + DEADLINES only ("talk to X before killing Y").
  Never outcomes, never reasons, never trajectory answers ("will X happen
  to this character" is refused on principle).
- No-stakes choices get "follow your gut, nothing mechanical hinges".
- He reports sends/choices AFTER making them; assistant confirms whether
  anything needs flagging, still without outcomes.
- The mid-game hard watershed: assistant must loudly say "settle everyone
  now" BEFORE he reaches it. This promise is load-bearing.
- His four sensors (taught, he uses them): exhaust dialogue to the loop;
  judge people by how they speak of others; incense logic (would the
  beast-warding incense object); circumstances they're found in.
  Plus: the send system announces itself - no offer, no stakes.

## Progress (updated 26 Aug 2026, night)
- Checkpoint: OLD YHARNAM entered (via the Cathedral Ward descent). The
  m23 silent crash did NOT repeat on the same hallway; bb-crash-watch
  armed for any future death (see todo.md item 2).
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
- Debug emulator build, 1440p internal, Fifo-vs-Mailbox present question
  open (Mailbox free-runs during loads).
- OPEN MYSTERY: GPU pins 100% (usual 50-60%) with frametime chaos during
  normal gameplay; first episode min 62-64 of the 18:42 session; MangoHud
  showed presents up to 4372fps at max clocks/176W. tools/gpu-spike-watch
  armed (6h self-expiring) to attribute per-process on next episode.
