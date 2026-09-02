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


## THE SECOND CORRECTION (2 Sep 2026, evening): THE SANDBOX WAS RENDERING 1080p

Every "4K" capture before this evening was a **1920x1080 window bilinearly
upscaled 2x by gamescope**. The sandbox's `GraphicsConfig.xml` (UTF-16; plain
grep reads nothing) said `ScreenMode WINDOW 1920x1080`, while Donnie's real
install is `FULLSCREEN 3840x2160`. So the whole rail investigation was fought
against the upscaler:

* the "2:1 minification" of a scale-2 atlas: the 1080p window's, not the game's
* the "23.6 texels per 24 rows" fractional drift: the upscaler's sample phase
* the "measured" 3-tap blur `[0.277, 0.446, 0.277]`: the upscaler's bilinear
  kernel forced into a symmetric fit
* the pair duplication, sampling phase and deconvolution in `er_hud_graft.py`:
  all modelling something that does not exist at native 4K. Deleted.

Proven with a one-texel checkerboard (blue 40/80) in the FP block, shot with
the sandbox config switched to fullscreen 4K: it came back as a perfect 50/92
alternation in BOTH axes across exactly 24 screen rows (188..211). **One
scale-2 texel is one 4K pixel. No filtering, no blur.** 40->50 and 80->92 also
re-confirm the pure gamma 0.87 transfer. Capture kept at
`data/ds3-shot/shots/probe_checker_4k_native.png`.

The sandbox config is now fullscreen 4K (old one backed up beside this file as
`GraphicsConfig.sandbox-1080p-window.xml.bak`). Always shoot with
`DS3SHOT_W=3840 DS3SHOT_H=2160`; a 1080p capture of a 4K render is a downscale
and measures nothing useful.

**Result, the 1:1 graft rendered at native 4K** (`hud_rows.py`, per row over
columns 40..200 of each bar, against ER's reference rows):

| bar | rows matched within dE 0.8 | sum dE over the 24 drawn rows | rail rows (ER 145/84/146/144) |
|---|---|---|---|
| HP | 24 of 24 | 11 | 144 / 83 / 144 / 143 |
| FP | 24 of 24 | 12 | 131 / 85 / 133 / 145 vs ER 131 / 85 / 133 / 146 |
| stamina | 24 of 24 | 12 | 127 / 97 / 130 / 148 vs ER 128 / 98 / 131 / 149 |

The rail is done. What is left outside the fill's drawn window: the two brown
backdrop rows above each bar (ours 56,42,32 / 67,51,38 on all three; ER has a
dark line then a per-bar tinted rim, e.g. HP 63,47,35 / 90,38,18), and the
cap. Row-by-row truth is `hud_rows.py <capture>`; `hud_tune.py measure` is the
one-number summary and now samples only the flat top half of each bar (with
the bevel included it reported HP at 3.15 while every row was within 0.8).

## The cap, done properly (2 Sep evening): it is part of the HUD movie now

Donnie: "the shader just paints it on the screen no matter what I'm on. can
we look deep into how the health bar actually renders and edit that
directly?" Yes, and the answer killed another "engine-side" myth.

### How a bar actually renders (read out of `01_000_fe.gfx`)

Sprite 471 places the three bars: **384 HP, 380 MP, 373 SP** (named, at stage
x 50 (now 66), y -53/-36/-19; one stage px = two 4K px). Each is
`Fade -> {BarFrame 362, Delay 364, Current}`, and each of those holds a
**1920-frame "Bar" sprite** the engine `gotoAndStop`s at a frame proportional
to the stat. Inside a Bar:

| depth | what | detail |
|---|---|---|
| 1 | sliding MASK (sprite 64, clipDepth 15) | translate moves 0.752 px per frame, 0..1444 px. **Bar length is the mask, never a scale.** |
| 3 | six 248-px texture TILES | `MENU_PlayerHUD2`, 1 texel per stage px. Fill tiles sample base rows 34..46 = the "middle 12 rows" |
| 17 | LEFT END-CAP, sprite 358 / shape 357 | a 60x23 stage-px quad at the bar origin sampling base texels x 4..64, rows 160..183 (`bm t=(-34,-171)`). **Not "a 5x7 sprite fixed in engine code"**: the knob was the only opaque thing in that region |
| 19 | RIGHT END-CAP, sprite 360 | translated with the frame so it rides the bar's end |

BarFrame's Bar (361) is shared by all three bars, so one cap texture serves
all three. The cap sat UNDER Delay and Current, so an ER-style cap that
overlaps the fill's start would be covered.

### The edit

1. `er_fe_gfx.py --cap-over-fill`: removes the depth-17 placement from Bar
   361 and places sprite 358 at depth 7 in each Fade sprite (383/379/372),
   above Current at 5, inside the fade so it fades with the bar.
2. `er_hud_graft.py` clears the end-cap texture region and writes Elden
   Ring's 41x36 sprite (real alpha, `er-reference/er_bar_cap.png`) at scale-2
   texel (35, 324), pre-compensated through the fill transfer and scaled by
   0.961 (ER renders the sprite at 0.961x its file values, measured).
   Mapping: 4K x = origin + 2*(tx-34), 4K y = 166 + 2*(ty-171), bar origin
   at 4K x = 392 before the shift. A first attempt assumed the origin was 384
   and the cap landed exactly 8 px right (cross-correlation), which is how
   the origin was pinned: the fill's first displayed texel is already red.
3. `er_fe_gfx.py --shift-bars 16`: with ER's cap at ER's offset (33 px left of
   the fill) it ran under DS3's covenant badge, which is drawn above the bars
   and reaches within 12 px of them; ER keeps a 43 px gap. +16 stage px (32 at
   4K) reproduces that gap. Scoped to sprite 471 (other sprites also name
   children HP/MP/SP; unscoped it shifted seven).

Result (run 9, native 4K): cap at the intended origin on all three bars,
dx=0 dy=0 by cross-correlation; opaque-pixel mean 112.3/100.6/73.6 against
ER's 113.6/101.9/74.8; fill rows unchanged (sum dE 11/12/12). Red now starts
at 4K x=424; the tools' geometry (`hud_rows.BAR_X`, `hud_sim.FILL_X`,
`hud_tune.BAR_LEFT`) moved with it.

**The vkBasalt pass now does nothing** (cap call commented out, colour
correction already off). The Steam launch options that enable it can go.
Old placement-only shader kept as `ds3_hud_deepen.fx.bak-20260902-cap-overlap32`.

### Movie build chain

```bash
V=data/ds3-ui-port/.venv/bin/python; B=data/ds3-ui-port/build
$V tools/souls-extract/er_fe_gfx.py <vanilla 01_000_fe.gfx> $B/01_000_fe_neutral.gfx --neutral-cxform
$V tools/souls-extract/er_fe_gfx.py $B/01_000_fe_neutral.gfx $B/01_000_fe_capover.gfx --cap-over-fill
$V tools/souls-extract/er_fe_gfx.py $B/01_000_fe_capover.gfx $B/01_000_fe_capover_shift16.gfx --shift-bars 16
cp $B/01_000_fe_capover_shift16.gfx ~/couch/data/ds3-shot/game/mod/menu/01_000_fe.gfx
```
(the flags can also be combined in one call). `ds3-shot` kills a FOREGROUND
shell at teardown; run it with the harness in the background and measure
afterwards.

## The fill texture (2 Sep, late): Elden Ring's own texels, one for one

Donnie: "can we match the textures on it too now?" The screenshot cut had the
colours right but not the grain: 1300 screen columns squeezed into 512 made
our streaks finer and weaker than ER's (HP red std 1.94 vs 3.14, 16-px
autocorrelation 0.24 vs 0.66).

**ER's fills are in `extract/er/png/SB_FE_01.png`** as three 2889-texel strips
(HP rows 117..139, FP 153..175, stamina 81..102: two fading rim rows, the fill
top, 12 flat rows, 6 bevel rows, 2 fading rows). Cross-correlating the HP
strip's column profile against the 4K reference: **correlation 0.945 at exactly
1.00 screen px per texel**, so ER draws it 1:1 at 2160p, and the rows map 1:1
too. Our scale-2 atlas is also one texel per 4K px, so the strip goes into the
fill block with no resampling. Per bar, ER starts on a different strip texel
(HP 5, stamina 7, FP 8, each found at correlation 0.94-0.96), and ER's screen
shows the strip at about 0.85 of its contrast (regression slopes 0.79-0.88
across bars and frames). `er_hud_graft.py`: rows +0..+16 from the strip with
each row's mean pinned to ER's measured screen mean and the deviation scaled
by `GRAIN_CONTRAST = 0.85`; rows +17..+23 (bevel bottom, rail) stay from the
screenshot cut. The rail is a separate frame element in ER, drawn OVER the
strip's last rows, which is why those rows diverge from the sheet.

Verified run 12, native 4K (`hud_grain.py`):

| bar | per-pixel corr vs strip | std ours / ER / strip | rows sum dE | fill dE |
|---|---|---|---|---|
| HP | 0.955 at offset 0 | 3.40 / 2.87 / 4.05 | 9 | 0.53 |
| FP | 0.957 at offset 0 | 3.12 / 3.21 / 3.77 | 10 | 1.42 |
| stamina | 0.963 at offset 0 | 2.61 / 2.42 / 3.18 | 11 | 0.43 |

TRAP, again: the first grain check read 0.05 for FP and 0.4 for stamina
because its 480 px window ran past the ends of those shorter bars into
scenery. Windows must stay inside the shortest bar (~280 px here).
Also: `pkill -f` on a pattern that appears in your own shell's command line
kills your shell (exit 144); that was every unexplained 144 today.

## Playing it for real (2 Sep, late): the modded Steam launch

Steam launch options for DS3 are now `/home/ds2000/couch/tools/ds3-modded-launch %command%`
(set by editing localconfig.vdf with Steam shut down; backups beside this
file as `localconfig.vdf.bak-*`). The wrapper swaps the game exe in Steam's
command for `data/ds3-mod/modengine2_launcher.exe` and passes the real exe
back with `-p`, so the install is untouched and the REAL save is used.
`data/ds3-mod/mod` is a symlink to `data/ds3-shot/game/mod`, so every rebuild
deploys to the sandbox and the real launch at once. Menu assets load at boot:
restart DS3 to see a rebuild. Log: `/tmp/ds3-modded-launch.log`.
**OFFLINE ONLY** (System > Network > Launch Setting > Play Offline); the wrapper
cannot check it. The vkBasalt launch option is gone; the pass is inert anyway.

## The trough (2 Sep, late): synthesised from ER's profile

A TV grab of a damaged bar showed the depleted part as opaque brown leather
with a tile seam and a brightness step, and the rail stopping at the fill's
end. ER's trough, measured on two frames with different scenes, is a
translucent darkening (~0.52 of the scene through the body, ~0.77 at row -2,
~0.58 at -1, easing to ~0.41 at +18), a warm dark bevel row at +19, the same
bone rail at +20..+23 running the full width, a dark olive line at +24 and a
faint fade. `er_hud_graft.py` now builds the backdrop block from that profile
(rail rows copied from the HP fill after the graft) instead of cutting ER's
leather art. Alpha is assumed linear; UNVERIFIED on screen until the next
damaged-bar grab (`DISPLAY=:0 import -window root`; the HUD auto-hides, so
have Donnie cycle an item first; a 4K grab takes ~4 s).

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
* `hud_rows.py <capture>` - every drawn row of every bar against ER's row,
  with deltaE. The definitive rail/bevel/fill check at native 4K.
* `hud_cap.py <capture> | --er` - cap footprint measured the SAME way on both
  frames (per-row and per-column bone counts printed, so a scenery false
  positive is visible instead of silently becoming the box's bounds).
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
