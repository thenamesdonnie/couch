# UNADJUDICATED: why Bloodborne's lamp prompts vanish with the mod's script/ installed

**gpt-5.6-sol, high reasoning effort, 31 Aug 2026.** Raw and unedited.
**Every line below is a claim, not a fact.** Brief: `docs/bloodborne-lamp-codex-prompt.md`.
Adjudication is in the sibling `...-adjudication.md` — read that before acting on anything here.

---

## PROVEN

### 1. The failure is in each lamp’s replacement ESD flow

For Central Yharnam lamp index 0, the specific file is:

`artifacts/mod-archive/bb_enhanced_0.11.2-fix9/_data/script/talk/m24_01_00_00.talkesdbnd.dcx`

BND entry:

`N:\SPRJ\data\INTERROOT_ps4\script\talk\m24_01_00_00\t241000.esd`

In the decompressed BND:

| Version | BND data offset | ESD size | SHA-256 |
|---|---:|---:|---|
| Stock | `0x14c0` | 13,816 | `c660fafb5fdc6c1976458e4d3eb015125e185fb2904e671d1d4ae82b953472d5` |
| Mod | `0x1570` | 167,488 | `9f2be8e3758b971f1931e224fadd1bdd1eae36044741e417e9d424f2a5db07a7` |

Offsets below are relative to the start of the extracted `fSSL` ESD payload.

The stock and mod flows both make the same unconditional initial transition:

- Stock condition record `0x1514` targets state 1 at `0x21c`; evaluator `0x316c`, length 2, is `41 a1`.
- Mod condition record `0xb5cc` targets state 1 at `0x59c`; evaluator `0x23db4`, length 2, is also `41 a1`.

State 1 then executes the lamp setup call. This is where the first relevant structural divergence occurs:

```text
Stock command record 0x242c:
  bank 6, command 2147483646, 7 arguments
  [6000, 6001, 6100, 6101, 241, false, 10010715]

Mod command record 0x176bc:
  bank 6, command 2147483646, 8 arguments
  [6000, 6001, 6100, 6101, 6103, 241, 0, 10010715]
```

The mod’s argument records begin at `0x1c2f4`; their literal evaluators are at `0x25b1c` through `0x25b46`. The new value is `6103`, the mod’s “Glimpse into the Hunter’s Dream” ActionButtonParam. The following new argument is the lamp index, here `0`.

This rewrite is systematic, not peculiar to one lamp:

- `m21_01`: `t211000`
- `m22`: `t220000`–`t220001`
- `m23`: `t230000`–`t230002`
- `m24_00`: `t240000`–`t240001`
- `m24_01`: `t241000`–`t241003`
- `m24_02`: `t242000`–`t242002`
- `m25`: `t250000`–`t250002`
- `m26`: `t260000`–`t260003`
- `m27`: `t270000`–`t270001`
- `m28`: `t280000`–`t280003`
- `m29`: `t290110`–`t290118`
- `m32`: `t320000`–`t320003`
- `m33`: `t330000`–`t330001`
- `m34`: `t340000`–`t340003`
- `m35`: `t350000`–`t350002`
- `m36`: `t360000`–`t360002`

In every one, the stock setup vector gains ActionButtonParam `6103` and an explicit lamp index.

The mod also replaces all four Central Yharnam lamp ESDs and adds a helper:

```text
t241000: 13,816 -> 167,488 bytes
t241001: 13,816 -> 167,488 bytes
t241002: 13,816 -> 168,704 bytes
t241003: 13,816 -> 169,472 bytes
t241029: added, 246,512 bytes
```

The added `t241029.esd` is bound to the separate `【BBE】portable_lantern` map actor through `TalkID: 241029` in [`maps.json:6572`](/tmp/claude-1000/-home-ds2000-couch/4ae92559-eebd-4c0c-abc7-33e50ea62d55/scratchpad/lamp-investigation/artifacts/mod-archive/bb_enhanced_0.11.2-fix9/_data/maps.json:6572). Stock lamp `t241000` does not delegate to `t241029`; the enhanced logic is embedded directly in the replacement `t241000`.

The two `.luabnd.dcx` changes are unrelated enemy AI transfers:

- `m22`: adds `006600_logic.lua` and `006600_battle.lua`
- `m33`: adds `006401_logic.lua` and `006401_battle.lua`

That matches `CopyAI`, not lamp interaction code, in [`Form1.cs:2033`](/tmp/claude-1000/-home-ds2000-couch/4ae92559-eebd-4c0c-abc7-33e50ea62d55/scratchpad/lamp-investigation/artifacts/mod-archive/bb_enhanced_0.11.2-fix9/_src/BBEnhancedPatcherGUI/BBEnhancedPatcherGUI/Form1.cs:2033).

### 2. The referenced param and message are present

The packaged mod param contains ActionButtonParam row `6103`:

- BND entry ID 0, `ActionButtonParam.param`
- entry data offset `0x2d70`
- row header at PARAM offset `0x1630`
- row data at PARAM offset `0x5860`
- 238 total rows

Its source definition specifies radius `1.4`, height `2.0`, text ID `70011002`, priority `5`, and circle-button execution in [`enhanced_params.json:3`](/tmp/claude-1000/-home-ds2000-couch/4ae92559-eebd-4c0c-abc7-33e50ea62d55/scratchpad/lamp-investigation/artifacts/mod-archive/bb_enhanced_0.11.2-fix9/_data/enhanced_params.json:3).

Message `70011002`, “Glimpse into the Hunter’s Dream”, is present in `_data/msg.json` at lines 1256–1257. All 42 packaged `msg/` files are byte-identical to the live files.

Therefore this is not explained by a missing ActionButtonParam row or missing prompt text.

### 3. The evidence supports failure before a prompt is registered

The mod replaces the state that establishes the lamp action-button set. The visible symptom is no action prompt at all, rather than a prompt followed by a closing menu. Stock scripts restore the prompt without changing map, event, param or message files.

That locates the failure in or immediately after the enhanced lamp setup/registration flow. There is no byte evidence supporting “the menu opens and immediately closes.”

I cannot prove from static ESD bytes which engine-side check rejects or suppresses that setup call. There is no execution trace in the staged artifacts.

### 4. The lamp-disabled branch exists

In mod `t241000.esd`:

- condition record `0x1717c`
- evaluator offset `154015`, length 5
- evaluator bytes at `0x259a3`: `82 6c a5 b8 00`
- embedded integer: `12100972`, the “Lamp Menu Disabled” flag

`12100872`, the Enabled partner, does not occur in this ESD. The setting definition says Disabled makes lamps function exactly as unmodded in [`settings.json:29`](/tmp/claude-1000/-home-ds2000-couch/4ae92559-eebd-4c0c-abc7-33e50ea62d55/scratchpad/lamp-investigation/artifacts/mod-archive/bb_enhanced_0.11.2-fix9/_data/settings.json:29).

### 5. Running the installer is not a missing step

`BBEnhancedInstaller` enumerates every file below `GAME FILES/dvdroot_ps4` and copies it directly over the destination, making backups first. It performs no patching or conversion: [`Program.cs:135`](/tmp/claude-1000/-home-ds2000-couch/4ae92559-eebd-4c0c-abc7-33e50ea62d55/scratchpad/lamp-investigation/artifacts/mod-archive/bb_enhanced_0.11.2-fix9/_src/BBEnhancedInstaller/BBEnhancedInstaller/Program.cs:135) and [`Program.cs:187`](/tmp/claude-1000/-home-ds2000-couch/4ae92559-eebd-4c0c-abc7-33e50ea62d55/scratchpad/lamp-investigation/artifacts/mod-archive/bb_enhanced_0.11.2-fix9/_src/BBEnhancedInstaller/BBEnhancedInstaller/Program.cs:187).

Your plain overlay is functionally equivalent, apart from its backup bookkeeping and `bbe.txt`.

### 6. The patcher does not patch talk ESDs

The compatibility patcher:

1. Reads target resources with precedence external mods, patch, then app: [`Form1.cs:296`](/tmp/claude-1000/-home-ds2000-couch/4ae92559-eebd-4c0c-abc7-33e50ea62d55/scratchpad/lamp-investigation/artifacts/mod-archive/bb_enhanced_0.11.2-fix9/_src/BBEnhancedPatcherGUI/BBEnhancedPatcherGUI/Form1.cs:296).
2. Generates maps, events, params, messages, SFX, animation, menu and AI: [`Form1.cs:361`](/tmp/claude-1000/-home-ds2000-couch/4ae92559-eebd-4c0c-abc7-33e50ea62d55/scratchpad/lamp-investigation/artifacts/mod-archive/bb_enhanced_0.11.2-fix9/_src/BBEnhancedPatcherGUI/BBEnhancedPatcherGUI/Form1.cs:361).
3. Applies 1,902 textual replacements to 18 EMEVDs from `_data/emevd_patches.json`: [`Form1.cs:1185`](/tmp/claude-1000/-home-ds2000-couch/4ae92559-eebd-4c0c-abc7-33e50ea62d55/scratchpad/lamp-investigation/artifacts/mod-archive/bb_enhanced_0.11.2-fix9/_src/BBEnhancedPatcherGUI/BBEnhancedPatcherGUI/Form1.cs:1185).
4. Copies `_data/script/talk` verbatim to the output: [`Form1.cs:2119`](/tmp/claude-1000/-home-ds2000-couch/4ae92559-eebd-4c0c-abc7-33e50ea62d55/scratchpad/lamp-investigation/artifacts/mod-archive/bb_enhanced_0.11.2-fix9/_src/BBEnhancedPatcherGUI/BBEnhancedPatcherGUI/Form1.cs:2119).

All 17 `_data/script/talk/*.talkesdbnd.dcx` files are byte-identical to the corresponding packaged `GAME FILES/dvdroot_ps4/script/talk` files.

The installed non-script companion files are also the complete packaged output:

```text
chr:   1/1 identical
event: 18/18 identical
map:   2335/2335 identical
menu:  40/40 identical
msg:   42/42 identical
parts: 4/4 identical
sfx:   2/2 identical
```

Therefore there is no omitted patcher transformation of the talk files, and no missing packaged event/map/menu companion category. Running the patcher would still install these exact failing talk ESD bytes.

A Linux reimplementation of the complete compatibility generator would need to reproduce the source sequence above using SoulsFormats-compatible MSBB, EMEVD, PARAM, FMG, TAE and BND readers, including duplicate-ID remapping and the 1,902 EMEVD substitutions. It would then copy the same talk ESDs unchanged. That is not a targeted repair for this bug.

## HYPOTHESIS

### Leading mechanism

The enhanced setup call in each replacement lamp ESD is not becoming an active action-button registration on this runtime. The strongest candidate is the systematic change from:

```text
[6000, 6001, 6100, 6101, map, lamp-index-expression, 10010715]
```

to:

```text
[6000, 6001, 6100, 6101, 6103, map, lamp-index, 10010715]
```

Because the initial state transition still exists, the failure is more consistent with this expanded setup call, or an immediately following enhanced-state condition, failing than with the ESD never starting.

An eight-argument `bank 6 / command 2147483646` call is not inherently illegal: the staged stock ESD set contains 22 valid eight-argument uses. Therefore “shadPS4 supports only seven arguments” is ruled out. The remaining possibilities are:

- this particular expanded argument signature is mishandled;
- ActionButtonParam `6103` is rejected despite the row being present;
- a later enhanced-flow condition prevents the registered action from remaining active;
- a CUSA00900-specific runtime difference affects this static enhanced ESD.

The bytes do not distinguish these.

### Patcher-related residual possibility

The patcher can regenerate target-specific maps and events from CUSA00900, so a region-specific companion-file mismatch is not logically impossible. The source does not identify which title ID produced the packaged `GAME FILES` output.

However, this would be a compatibility regeneration issue, not an installer step assumed by the talk files. The talk ESDs themselves remain unchanged, and every directly visible dependency they reference here, including `6103`, its message, map additions and mod events, is already installed.

### Available repair paths

There is no proven minimal shipped subset that gives standard lamps the enhanced menu:

- Stock `t241000`–`t241003` restore stock prompts but contain none of the enhanced menu flow.
- Adding only `t241029` adds the separate portable-lantern talk flow; stock lamps do not call it.
- Installing any replacement standard-lamp ESD also installs the expanded setup call implicated above.
- Running or cloning the patcher will not edit that call.

A hand repair is plausible, but the correct edit is not yet demonstrated. The narrow candidates are the `6103` argument, the additional lamp-index argument, or the enhanced/disabled branch around flag `12100972`. Editing one without proving which is wrong risks producing a lamp that prompts but cannot safely complete its menu state machine.

A separate partial-recovery experiment is possible for the settings menu: `m21_00_00_00.talkesdbnd.dcx` entry `t210304.esd` expands from 34,488 to 124,512 bytes and contains 100 of the 113 setting-value flag IDs, including both `12100872` and `12100972`. A hybrid BND retaining stock Dream lamp entries while using mod `t210304` might restore the Doll settings UI, but this is untested and would not restore the enhanced lamp menu.

## Cheapest decisive experiment

With the mod’s full `script/` installed, edit a copy of the save so that group `12100`, slot `50` has bit `972` set and bit `872` cleared:

```text
12100972 = 1    # Lamp Menu Disabled
12100872 = 0    # Lamp Menu Enabled cleared
```

Apply the same change to the game’s backup save, then test the same lamp.

If its stock prompt returns, the replacement ESD loads correctly and the failure is conclusively inside the enhanced branch, not a missing patcher pass or archive-loading failure. If the prompt remains absent, the advertised disabled fallback is also failing, which kills the leading branch hypothesis and points directly at the unconditional expanded setup call.