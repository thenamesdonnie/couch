# Current DS3 mod stack

Deployed at `~/couch/data/ds3-shot/game/mod/`, loaded by ModEngine2.
Nothing here touches the real install; the fallback is deleting a file.

| file | what |
|---|---|
| `menu/01_common.tpf.dcx` | 40 Elden Ring button glyphs (both Xbox and PS4 slots) + 17 panels denoised to grain ~1.0 + the HP/FP/stamina bars grafted from Elden Ring |
| `menu/02_title.tpf.dcx` | DARK SOULS III / ELDEN RING EDITION title logo |
| `font/matissepron/font.gfx` | **Spectral SemiBold** |
| `menu/01_000_fe.gfx` | the in-game HUD movie, with the bars' colour transform neutralised |

## Rebuilding the HUD

Three scripts, chained, each taking the previous one's output:

```bash
V=data/ds3-ui-port/.venv/bin/python; B=data/ds3-ui-port/build
$V tools/souls-extract/er_hud_graft.py   $B/01_common.tpf.dcx  $B/01_common_g3.tpf.dcx
$V tools/souls-extract/er_pledge_icon.py $B/01_common_g3.tpf.dcx $B/01_common_g4.tpf.dcx
$V tools/souls-extract/er_hud_chrome.py  $B/01_common_g4.tpf.dcx $B/01_common_final.tpf.dcx
cp $B/01_common_final.tpf.dcx ~/couch/data/ds3-shot/game/mod/menu/01_common.tpf.dcx
```

| script | element |
|---|---|
| `er_hud_graft.py` | HP/FP/stamina bars, the bone rail, the bevelled left edge |
| `er_pledge_icon.py` | the covenant badge (the bright octagon top-left) |
| `er_hud_chrome.py` | the souls spiral tile bottom-right |

WHICH TEXTURE OWNS WHAT was established by flooding tracer colours and reading
the frame back, NOT from the atlas layout, which misleads here:

* the top-left octagon on screen is `MENU_PledgeIcon` (the COVENANT badge), not
  anything in `MENU_PlayerHUD`
* `MENU_PlayerHUD`'s ornate top-left octagon feeds nothing visible at all
* `MENU_PlayerHUD` x212-252 y50-235 is the SOULS COUNTER background
* `MENU_PlayerHUD2` rows 124+ are the bar end-caps

Guessing from names and atlas position cost three wrong runs before the tracer
method was used.

Real Elden Ring pixels, cut from 4K grabs of the live game and inverse-
compensated for DS3's own transfer. The three facts that make it work, all
measured rather than assumed, and all documented in the script:

* `screen = 0.87 * atlas + 38` for the fill, `0.833 * atlas + 48` for the
  backdrop. The +38 is engine-side and IRREDUCIBLE - it survives blacking the
  backdrop, blacking `MENU_PlayerHUD`, blacking `MENU_HUD_Status`, varying
  alpha, and an all-black bar with no bright neighbour anywhere (still 35,35,36
  neutral against a bluish 32,36,42 scene, so it is not bleed-through either).
  There is no player-HUD `.gfx` to hold a colour transform; the gauges are
  drawn by engine code. Reaching ER's green 26 / blue 22 would mean patching
  `DarkSoulsIII.exe`.
* **The game draws only the middle 12 of the 24 atlas rows** (indices 6-17).
  Author into `DRAWN_ROWS`; anything outside is silently discarded.
* An ER bar is fill + bevel + rail, and the bevel is nearly as tall as the
  fill. Paste the whole assembly, not just the fill.

Verify with `DS3SHOT_W=3840 DS3SHOT_H=2160 tools/ds3-shot inventory` and
compare against `data/ds3-ui-port/er-reference/hud_full.png` at native 4K.
Sample INSIDE the bar - it ends at x912 at 4K, and sampling past it into the
scene has produced three separate false readings.

## Rebuilding the font

Chosen by measurement, not taste alone: ink coverage on a text crop is
8.81% against vanilla Matisse's 8.82%, i.e. it matches vanilla's weight
while being wider and more open. Crimson Pro at the same nominal weight
measures 8.38%; Crimson Pro at its DEFAULT variable weight was 6.79%,
which is 23% lighter than vanilla and actively worse to read.

```bash
# static weight first - FFDec takes a variable font's default instance
python -m fontTools.varLib.instancer Font.ttf wght=600 -o Font-600.ttf   # if variable
tools/souls-extract/swap_font.sh \
    data/ds3-ui-port/extract/ds3/font_matissepron.gfx \
    data/ds3-ui-port/build/fonts/Spectral-SemiBold.ttf \
    out.gfx
cp out.gfx ~/couch/data/ds3-shot/game/mod/font/matissepron/font.gfx
```

FFDec is vendored at `data/ds3-ui-port/ffdec/` (it lived in /tmp and would
not have survived a reboot). Set `FFDEC=` to point elsewhere.

## Testing

`DS3SHOT_MOD=1 ~/couch/tools/ds3-shot inventory` - ~90s, headless, never
touches the TV. Shots land in `~/couch/data/ds3-shot/shots/`.


## THE CORRECTION THAT MATTERS MOST

For a long time I believed the +34 lift on the gauge fill was engine-side and
irreducible - that Elden Ring's real green (26) and blue (22) could never be
reached without patching `DarkSoulsIII.exe`. That was WRONG twice over:

1. I checked `menu/02_000_ingametop.gfx` for a HUD colour transform, found it
   referenced none of the HUD textures, and concluded no HUD `.gfx` existed.
   `02_*` is the START MENU stack. The in-game HUD is **`menu/01_000_fe.gfx`**.
2. I then "proved" the lift was engine-side by elimination - blacking the
   backdrop, `MENU_PlayerHUD`, `MENU_HUD_Status`, varying alpha, an all-black
   bar with no bright neighbour. Every test was sound. Every result was ALSO
   consistent with a Scaleform colour transform. Ruling out asset causes does
   not prove an engine cause.

The lift was three XML attributes: sprite 471's `HP` / `MP` / `SP` placements
each carried `CXFORMWITHALPHA` mult 230/256, **add +26** on R, G and B.

With it neutralised the channels reach zero - HP measured (76,0,0) where it had
floored at (96,34,34) - and after re-deriving the residual transfer as a pure
gamma (`screen = 255*(atlas/255)^0.87`, no offset), the TEXTURE ALONE measures:

| bar | ours | Elden Ring | deltaE |
|---|---|---|---|
| HP | 95,30,25 | 94,26,22 | 1.85 |
| FP | 28,68,87 | 28,68,85 | 1.37 |
| stamina | 32,70,47 | 28,69,45 | 1.37 |

No post-processing involved. The vkBasalt shader's colour correction, which was
built entirely to fight this lift, is now switched off; it only draws the cap.

## Editing the HUD movie

```bash
tools/souls-extract/er_fe_gfx.py <in.gfx> <out.gfx> --neutral-cxform
```
Also supports `--scale-cap N` (the left end-cap is ONE matrix, sprite 361 depth
17, shared by all three bars) and `--drop-dish` (the brown item base is three
named `Dish` placements, so it can be removed properly rather than erased from
a texture).

JPEXS round-trip is safe for this file: rebuilt size is byte-count identical,
12 bytes differ as re-encodings of zero, and a second round trip converges.

## Tools

* `hud_tune.py measure <frame>` - every element vs ER with deltaE, one command.
  Sample INSIDE bars and use the longest CONTIGUOUS run: min..max spans stray
  matches and lands on scenery, which caused several false readings.
* `hud_tune.py shader|overlay|compare` - simulate the post-process pass offline.
* `tools/ds3-state save|load|list` - emulator-style save states for the sandbox.


## Iteration speed: what was tried and what actually worked

The loop is ~91s per change (build, deploy, boot, load, shoot, quit) and I ran
about ninety of them. Three levers were investigated; two measured as nothing,
and recording that is the point - they are the obvious ideas and they do not
work here.

**Hot reload: does not work. Measured, not assumed.** ModEngine2 serves override
bytes at every file open, so the question was whether DS3 re-opens the menu
files on quit-to-title -> Continue. `tools/ds3-hotreload-test` answers it
directly: get in game, quit to title WITHOUT ending the process, swap in a build
whose HP bar is solid magenta, press Continue. The bar came back its normal
(92,25,22). Menu resources are resident from process start. This also rules out
any "keep the session alive" design.

**Pre-decrypting the archive headers (BootBoost-style): no measurable gain.**
DS3 RSA-decrypts eight `.bhd` headers per boot and the community figure is
10-15s. `tools/ds3-bootboost` does it natively (reusing `dvdbnd.decrypt_bhd`,
no Windows exe, sandbox only, real install untouched, `--revert` restores the
symlinks). Timed over four runs: decrypted 92s and 91s, encrypted 91s and 91s.
No difference - the filesystem cache presumably already absorbs it. The tool
works and is kept, but the symlinks are left in place because there is no gain
to justify breaking them.

**DS3SHOT_FAST=1: the one that worked, ~11%.** The full journey also walks into
Equipment and Inventory for two more screenshots, which HUD work never looks at.
Fast mode goes straight from the in-game shot to the clean quit. Measured 81s
against 91s.

**Save states do not help speed, and cannot.** `tools/ds3-state` restores a save
FILE, so the game still boots and still loads. Emulator save states are instant
because they snapshot RAM; no such tool exists for DS3 and CRIU cannot checkpoint
GPU state. `ds3-state` is for reproducibility - every run starting byte-identical
- not for speed.

**Logo skip: a real 4s.** DS3 plays five Scaleform logo/warning movies before
the title, 155 frames each. `tools/ds3-nologo build` truncates them to one frame
and drops them in the mod dir (no Windows DLL needed - they are ordinary
archive files ModEngine2 can override). Menu now arrives 3s after first frame
instead of ~25s; total 77s against 81s. Less than the animation length suggests,
because the logos overlapped other boot work rather than adding to it.
`tools/ds3-nologo remove` reverts.

**Cumulative: 91s -> 77s** (fast mode 10s, logo skip 4s).

**Not yet tried:** rendering `01_000_fe.gfx` in JPEXS with the atlas DDS beside it
(it loads `DefineExternalImage2` files from the same directory), which would give
a zero-launch static preview for layout work; and Special K's live
`ReloadAllTextures` for texture-only tweaks.
