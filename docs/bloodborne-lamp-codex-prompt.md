# Brief: why do Bloodborne's lamp prompts vanish when the mod's `script/` is installed?

## Rails (this box is a live living-room console)

- You may write ONLY inside your own working directory. Everything under
  `/home/ds2000/games/`, `/home/ds2000/couch/` and `/home/ds2000/.local/` is
  **read-only** to you.
- Never run the game or the emulator. Never `systemctl`. Never `git commit`.
  Never install packages. You do not need the network and will not get it.
- Everything you need has been staged locally under `./artifacts/`. Do not go
  looking for it online.

## The system, as it actually is today

Bloodborne (`CUSA00900`, base 1.00 + patch 1.09), a decrypted PS4 dump at
`/home/ds2000/games/ps4/CUSA00900/dvdroot_ps4`, run under shadPS4 on Linux.

The mod is **Bloodborne Enhanced 0.11.2-fix9** (Nexus mod 19). It was installed
as a **plain file overlay**: copy the mod's `dvdroot_ps4` tree over the dump's,
keeping a per-file backup of everything overwritten. Nothing else was done.

**We have never run the mod's own installer or patcher.** The archive ships
`BBEnhancedInstaller.exe`, `BBEnhancedPatcherGUI.exe` and
`BBEnhancedSettingsGUI.exe`, all .NET 8 WinForms and Windows-only. We are on
Linux and skipped them.

Currently installed categories: `chr`, `event`, `map`, `menu`, `msg`, `param`,
`parts`, `sfx`. **`script/` is at stock**, deliberately, because of the bug
below.

One local modification worth knowing so you do not misread it: the live
`param/gameparam/gameparam.parambnd.dcx` is **the mod's param plus one edit of
ours** (durability/durabilityMax set to 9999 on all 2107 EquipParamWeapon rows,
a same-length in-place edit). Verified: our pre-edit backup is byte-identical to
the mod's shipped param. So param is modded, despite our own bisect tool
labelling it "vanilla" (its probe just compares one file and our edit changes it).

## The symptom

With the mod's `script/` installed (19 files: 2 `.luabnd.dcx`, 17
`talk/*.talkesdbnd.dcx`), **every lamp in the game loses its interaction
prompt.** Walk up to a lamp and nothing happens: no prompt, no menu, cannot
rest, cannot warp. The lamps are visibly there. Messengers still appear.
Talking to the Doll still worked, so interaction in general was not dead.

With `script/` at stock, lamps behave normally and the rest of the mod works
(its Auto Refill event fires correctly, its params and menus are live).

**Reproduced twice, and this matters:**

1. 26 Aug 2026, found by a 7-round category bisect. At the time we suspected a
   state-dependent cause, because the full mod including `script/` had
   apparently worked for two days beforehand, and that session had suffered
   freezes and an OOM. The theory was a talk-flow flag left stuck in the save.
2. 31 Aug 2026, re-installed `script/` on a clean session with no crash, and
   **the lamps died again on the first launch.** That kills the stuck-flag
   theory. It is the files.

## What we already know. Do not spend tokens re-deriving any of this

- Mod settings are event flags baked into `event/common.emevd.dcx`, event
  **10008400**. Each setting owns a flag pair, Enabled `X8yy` / Disabled `X9yy`,
  and only the Enabled id is ever tested. All 51 were resolved and matched the
  shipped `_data/settings.json` exactly.
- Those settings persist **in the save**, group 12100 = slot 50. Editing the
  defaults event does not change an existing save.
- **Mixing categories produces broken hybrids.** Vanilla `common.emevd.dcx`
  with modded map emevds gives 18 unresolvable event inits in `m24_01` alone,
  because the mod's map scripts call mod-only common events.
- Central Yharnam is `m24_01`, not `m21`. `m21` is the Hunter's Dream.
- DCX is a plain zlib container (`DCX\0` + `DCS`/`DCP`/`DCA`, `DFLT` format).
  A decompress and repack round-trip against the live files returns a
  byte-identical payload. A working Python parser is in
  `./artifacts/docs/bloodborne-enhanced-settings-20260824.md`, along with a
  64-bit EMEVD reader. Use them rather than writing your own from scratch.
- `talkesdbnd.dcx` is a BND4 of `.esd` files; `luabnd.dcx` is a BND4 of
  lua/luagnl/luainfo.

## The questions, in priority order

1. **Mechanistically, why does the lamp prompt disappear?** Name the specific
   file and the specific flow. "The talk scripts are broken" is not an answer;
   which ESD, referencing what, failing how. A prompt that never appears
   suggests the interaction is never registered rather than a menu that opens
   and closes, so say whether the evidence supports that.
2. **Is running the patcher the missing step?** `_src/BBEnhancedPatcherGUI/`
   ships the full C# source, and `_data/emevd_patches.json` is a 1MB data file
   next to it. Read them and say what the patcher actually does to a dump.
   Specifically: do the shipped `script/` files assume a patcher pass over the
   game's own files, such that a raw overlay is an incomplete install? If so,
   what exactly would we have to replicate on Linux?
3. **Is there a way to get the mod's lamp menu working here without breaking
   lamps?** A minimal file subset, a hand-applied equivalent of whatever the
   patcher does, a single edit. Or a clear "no, and here is why".

We care about question 2 more than a perfect answer to 1. The lamp menu being
inert costs real features: warp from a lamp, level up at a lamp, boss
rematches, "Quick Warp to Bosses" (which reads as ENABLED in the save while
nothing can deliver it), and the Doll's entire settings menu, meaning 46 of the
mod's 51 settings have never been reachable on this install.

## Artifacts, all staged locally

- `./artifacts/mod-archive/bb_enhanced_0.11.2-fix9/` — the full extracted
  archive. Note `GAME FILES/dvdroot_ps4/` (the mod payload, including the 19
  `script/` files), `_src/BBEnhancedPatcherGUI/` (patcher source, `Form1.cs` is
  ~114KB), `_data/emevd_patches.json`, `_data/settings.json`, `_data/Defs/*.xml`
  (paramdefs, including `ActionButtonParam.xml`).
- `./artifacts/vanilla-script/` — the **stock** versions of exactly the 19 files
  the mod's `script/` overwrites. This is your diff baseline.
- `./artifacts/docs/` — our two write-ups: the lamp saga and the settings
  reverse-engineering.
- The live dump is readable at `/home/ds2000/games/ps4/CUSA00900/dvdroot_ps4`.
  Read only. It currently has stock `script/` and modded everything else, so it
  is the "working" configuration.

## Output

Findings only. No preamble, no praise, no summary of this brief back at me, no
architecture tour.

- Separate **PROVEN** (you read the bytes and can cite file + offset or entry
  name) from **HYPOTHESIS** (consistent with evidence but not demonstrated).
  Do not blur them. A confident wrong mechanism costs us more than an honest
  "I could not determine this".
- Cite concrete evidence for every claim: file path, BND entry name, ESD state
  id, event id, offset. We will verify each one against the files before acting
  on it.
- Finish with **the single cheapest decisive experiment** we could run next,
  stated as a command or a specific file edit, that would confirm or kill your
  leading hypothesis.
