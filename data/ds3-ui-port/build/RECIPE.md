# Current DS3 mod stack

Deployed at `~/couch/data/ds3-shot/game/mod/`, loaded by ModEngine2.
Nothing here touches the real install; the fallback is deleting a file.

| file | what |
|---|---|
| `menu/01_common.tpf.dcx` | glyphs, bars, badge, counter, slots, area-name underline, AND the menu chrome: washes (er_menu_wash), cells/highlight/tabs (er_menu_cells), pause tiles (er_pause_menu). Deployed build = `01_common_menus.tpf.dcx` |
| `menu/02_title.tpf.dcx` | DARK SOULS III / ELDEN RING EDITION title logo |
| `font/matissepron/font.gfx` | **Spectral SemiBold** |
| `menu/01_000_fe.gfx` | the in-game HUD movie: bars' colour transform neutralised, cap over fill, bars shifted 16, equipment cross at 0.75 in ER's layout |
| `menu/01_001_fe_soul.gfx` | the SOULS COUNTER movie (it is not part of 01_000_fe), moved and sized to ER's rune counter |
| `menu/02_000_ingametop.gfx` | the PAUSE MENU in ER's vertical list layout (er_pause_gfx.py); Up/Down come from the input layer (tools/ds3-menu-watch + inputproc), the engine walks it Left/Right |
| `sfx/frpg_sfxbnd_m32_effect.ffxbnd.dcx` | Archdragon fog depth fade 2..5 m (tools/ds3-fog-soften) |
| `sfx/frpg_sfxbnd_commoneffects_resource.ffxbnd.dcx` | 4x fog sprite sheets (tools/ds3-texup) |
| `map/m32/m32_000{0..3}.tpfbhd+bdt` | merged Archdragon texture binders: Texture Improvement base + Visual Overhaul `_r` + our 4x clouds/sky (ds3-texup pack --base-dir --inject) |
| ModEngine2 mod list | `mod` > `mod-jump` (Nexus 1911 c0000.hks) > `mod-vo` > `mod-ti` (see docs/research/ds3-graphics-modernisation-20260903.md) |
| `menu/02_010_equiptop, 02_011_equip, 02_020_inventory, 02_070_status, 02_05x_detailstatus_*.gfx` | ER typography per screen (er_menu_gfx.py) |

## Rebuilding the HUD

Three scripts, chained, each taking the previous one's output:

```bash
V=data/ds3-ui-port/.venv/bin/python; B=data/ds3-ui-port/build
$V tools/souls-extract/er_hud_graft.py   $B/01_common.tpf.dcx  $B/01_common_g3.tpf.dcx
$V tools/souls-extract/er_pledge_icon.py $B/01_common_g3.tpf.dcx $B/01_common_g4.tpf.dcx
$V tools/souls-extract/er_hud_chrome.py  $B/01_common_g4.tpf.dcx $B/01_common_g5.tpf.dcx
$V tools/souls-extract/er_item_panel.py  $B/01_common_g5.tpf.dcx $B/01_common_g6.tpf.dcx
$V tools/souls-extract/er_soul_counter.py $B/01_common_g6.tpf.dcx $B/01_common_soul.tpf.dcx
$V tools/souls-extract/er_slot_panel.py  $B/01_common_soul.tpf.dcx $B/01_common_slots2.tpf.dcx
$V tools/souls-extract/er_mapname.py     $B/01_common_slots2.tpf.dcx $B/01_common_final.tpf.dcx
cp $B/01_common_final.tpf.dcx ~/couch/data/ds3-shot/game/mod/menu/01_common.tpf.dcx
```
(`er_lockon.py` would go last; it is NOT in the chain until seen on the TV.)

MENUS (3 Sep, see docs/research/ds3-er-menus-survey-20260903.md), chained
after the HUD build:

```bash
$V tools/souls-extract/er_menu_wash.py  $B/01_common_final.tpf.dcx $B/01_common_m1.tpf.dcx
$V tools/souls-extract/er_menu_cells.py $B/01_common_m1.tpf.dcx    $B/01_common_m2.tpf.dcx
$V tools/souls-extract/er_pause_menu.py $B/01_common_m2.tpf.dcx    $B/01_common_menus.tpf.dcx
cp $B/01_common_menus.tpf.dcx ~/couch/data/ds3-shot/game/mod/menu/01_common.tpf.dcx
# movies: er_menu_gfx.py --screen ... for 02_010_equiptop, 02_011_equip, 02_020_inventory,
# 02_070_status, 02_055_detailstatus_weapon1, 02_050_detailstatus_player, 02_051_detailstatus_item;
# er_pause_gfx.py for 02_000_ingametop. Outputs $B/<name>_er.gfx, deployed as $M/<name>.gfx.
```
`DS3SHOT_PAUSE=1` adds a `pausemenu` shot to the inventory journey.
Pause tiles: ER_CELLS in er_pause_menu.py are the FRAME's outer alpha edge in
SB_In_GameTop (142x146 cells, 4-texel gutters), not an alpha bbox of the ink:
a bbox that starts 13..16 rows high picks up the cell above's bottom frame and
drops the cell's own (3 Sep, three of five tiles). Deployed = `01_common_pause3`.


| script | element |
|---|---|
| `er_hud_graft.py` | HP/FP/stamina bars, the bone rail, the bevelled left edge |
| `er_pledge_icon.py` | the covenant badge (the bright octagon top-left) |
| `er_hud_chrome.py` | the souls spiral tile bottom-right (now overpainted by er_soul_counter) |
| `er_item_panel.py` | podium removed, rails toned (rails now blanked by er_slot_panel) |
| `er_soul_counter.py` | the rune counter panel + medallion (MENU_PlayerHUD at 2x) |
| `er_slot_panel.py` | the equipment slot field + gold rules, and the small previews (MENU_ItemPanel_02 at 3x) |
| `er_mapname.py` | the area-name card's underline (MENU_MapName_Underline at 2x) |
| `er_lockon.py` | ER's lock-on dot (NOT in the chain, unverified) |

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
$V tools/souls-extract/er_fe_gfx.py $B/01_000_fe_capover_shift16.gfx $B/01_000_fe_slots.gfx --er-slots
$V tools/souls-extract/er_fe_gfx.py $B/01_000_fe_capover_shift16.gfx $B/01_000_fe_final.gfx --er-slots --fill-rim --er-mapname
cp $B/01_000_fe_final.gfx ~/couch/data/ds3-shot/game/mod/menu/01_000_fe.gfx
$V tools/souls-extract/er_soul_gfx.py data/ds3-ui-port/extract/ds3/gfx/01_001_fe_soul.gfx $B/01_001_fe_soul_er.gfx
cp $B/01_001_fe_soul_er.gfx ~/couch/data/ds3-shot/game/mod/menu/01_001_fe_soul.gfx
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

## The souls counter and the equipment slots (2 Sep, night)

### Read the movie, and read the RIGHT movie

`tools/souls-extract/fe_tree.py <xml> --bitmap NAME | --sprite ID | --name RE | --text`
prints the render tree out of a JPEXS `-swf2xml` dump: which shapes sample a
texture (UV rect in texels, ROTATED flagged), who places them, with matrices,
names and parents up to the root. It replaced the tracer-flood method for
"which texture owns what".

The souls counter is NOT in `01_000_fe.gfx`. That movie's only use of the
panel strip is the PvP `Score` sprite. The counter is its own movie,
**`menu/01_001_fe_soul.gfx`** (extract with `menu_gfx_extract.py /menu/...`),
root `Soul` at stage (1713, 990): shape 2 = the 206x46 panel sampling
`MENU_PlayerHUD [208..254, 38..244]` ROTATED (screen x runs down texture rows,
screen y runs UP the columns from 254), shape 4 = the 34x34 icon at (-80,0)
from `[166..200, 40..74]`, `TotalSoul` a right-aligned 24 px text. The texture
is shared with the HUD, which is why a texture edit showed on screen while
the movie being read never mentioned it.

### Alpha convention is PER ELEMENT (counter: run 3; rim rows and map name: 3 Sep)

CORRECTION (3 Sep): the rim-row and area-name agents both measured their
quads blending STRAIGHT alpha (a premultiplied rim came back 5 to 6 dE too
dark on every bar; a premultiplied underline came back at a third of its
alpha with negative lobes). The souls panel, which reads as premultiplied,
sits under a placement with an `alphaMult` colour transform; the bar tiles
and the MapName quad carry none. Whatever the mechanism, MEASURE the
convention for each new translucent element with one capture, never assume.
The original finding for the counter follows.


A straight-alpha field (16,13,10, a=0.65) rendered as `16 + 0.35*S`: the
engine ADDS the texture RGB to the attenuated scene, i.e. Scaleform textures
are **premultiplied**. Measured over two scenes (S 71/43 -> 43/35, straight
prediction 35/26; premultiplied prediction 41/31). With RGB written as `a*P`
the field matched ER's model within 2 units over the rock (run 4). Every
translucent texel authored from now on goes through `premultiply()`. (The
bars' trough was authored straight-alpha with a near-black RGB, where the
difference is negligible, and is unaffected.)

Also: DS3's panel placement carried `alphaMult 179/256`, and the engine
positions `TotalSoul` at runtime (moving its placement did nothing; the child
`Text` placement is what moves the digits).

### The counter, measured (ER hud_full at 4K)

Panel 402x75 at x 3341..3742, y 2032..2106; field a~0.65, P~(16,13,10)
(fit over six gameplay scenes; pause-menu frames excluded, the vignette
darkens the scene); gold brackets (161,148,112); medallion 45x42 at
(3368, 2048); digits 30 px tall ending 30 px inside the panel, (203,203,203).
Ours after run 4: brackets 3342..3741 x 2032..2104, digits 2058..2087 (ER
2058..2087), field over rock 39/39/43 against the model's 37.5/37.5/40.6.

`er_soul_counter.py` (texture: MENU_PlayerHUD shipped 512x512, ER's panel
painted from the grab with the field replaced by the solved colour, the
digits and medallion blanked, medallion into the icon cell; everything
premultiplied) + `er_soul_gfx.py` (root to (1771, 1034.5), icon to -76, em
22.5 px, inner Text shifted, alphaMult neutralised).

### The equipment cross

`ItemPanel` (sprite 257 in 472, at (-678,286) from centre) holds Item_Top
(-84) / Item_Bottom (+83) / Item_Left,Right (+/-123); each `Item` = panel
shape 129 (112x152, `MENU_ItemPanel_02 [4..116,4..156]`), the icon quad, two
6-px rails (188/190), the durability bar (219) and the selection Flash (195).
ER's cross at 4K: weapons 163x204 centred x 182/556, spell/flask y 1708/1928,
cross centre (369, 1818); rule lines 203 apart; field a~0.74 P~(11,13,9).

`er_fe_gfx.py --er-slots`: the whole cross scaled **0.75** and moved to
(-775.5, 369) -> a slot is 168x228, arms +/-184 (run 4: every rule within
4 px of ER horizontally); Item_Top/Bottom re-spaced (ER's cross is not
symmetric); label 660 twips grey 195, count 1036 twips sitting on the bottom
rule. `er_slot_panel.py`: `MENU_ItemPanel_02` shipped **768x1536** (3x, so the
0.75 sprite gives exactly two texels per 4K px), ER's field with 5 px
feathered edges and ER's gold rules (cut from the grab, keyed on R-B because
the scene under them is bright fog) painted into the PANEL quad, rail quads
blanked, small preview slot given the same field. Slot field measured run 4:
16/17/15 against the model's 15.2/17.7/16.8. Run 5: every rule line on ER's
row (spell 1607/1810, weapons 1715/1918, flask 1827/2032 vs 2030); run 6: the
label's top on ER's row (2058).

Dead end, do not retry: **the item icon's size is engine-owned.** Scaling the
`ItemIcon` placement (run 6) and then its child `IconImage` quad (run 7)
changed nothing on screen; the engine attaches the real item icon itself.
So DS3's Estus art keeps filling the slot where ER's icons sit at ~80%, and
the count digit, which ER draws over the art in the bottom-right corner, is
drawn UNDER the engine's icon here (dim behind the glow). It is placed on
clear field to the right of the art instead (`STOCK_XY`).

### The small preview slots (3 Sep)

ER draws two previews beside the spell slot and two beside the flask: the
next item, and behind it a smaller, thinner copy of the one after. DS3 has
the same pair, `SubItem_1` (depth 25, in front) and `SubItem_2` (depth 17,
behind), so this was a restyle, not a new element.

**What a preview is made of** (`fe_tree.py fe.xml --sprite 257 --depth 3`,
then `--sprite 201` / `--sprite 206`): sprite 207 = panel shape 199
(`MENU_ItemPanel_02 [4..49, 224..285]`, **45x61 stage px at 1:1** - the 0.4
in the tree is on the `Dish` and the `ItemIcon` inside 207, NOT on the
panel), the icon, and two 45x2 rails (shapes 202/204 at [60..105, 236..238]
and [60..105, 224..226]) that sit on the panel's first and last rows exactly
like the big ones. Sprite 207 is also what `Item_Left_Small` draws, so it
gets the same art for free.

**Measured on ER at 4K** - hud_full plus the five burst frames that actually
have the HUD up (`hud-combat-full`, `hud-damage-lag`, `hud-hp-empty`,
`hud-lockon-enemy-bar`, `interact-prompt-bloodstain`; the other twelve are
menus or a faded HUD and would fit a field against a scene nothing is
covering):

| | front preview | rear preview |
|---|---|---|
| drawn size | 78 x 98, rules 94 apart | 66 x 82, rules 78 apart (0.84 of the front, in both axes) |
| centre, spell pair | (503.5, 1653.5) | (556.5, 1645.5) |
| centre, flask pair | (503.5, 1983.5) | (556.5, 1992.0) |
| field | a 0.69, P (7,8,6) | a 0.54, i.e. 0.78 of the front |
| rule | a 2 px gold line, full slot width, small crest | the same, thinned |

The front preview's top rule sits on the spell slot's own top rule (1606)
and the flask preview's bottom rule on the flask's (2030), and the rear is
staggered further OUT along the cross in both pairs - where DS3 staggers its
top pair inwards (`SubItem_2` 9 px nearer the middle). Rear alpha 0.54 /
front 0.69 = 0.78, and DS3's `SubItem_2` placement already carries
`alphaMult 205/256 = 0.80`: **leave that cxform alone, it is already ER's.**

**How the field alpha was got, and the trap.** Same fit as the main slot,
`F = a*P + (1-a)*S` over the six frames, with S from the gap between the
main slot and the preview. The first fit said a = 0.60 because that gap was
sampled from x 452, which is still inside the MAIN slot's edge feather - it
runs a full 12 px, x 450..462, not the 5 px the code assumes. Sampling
x 458..463 moved the preview to 0.69 AND moved the main slot's own re-fit
onto its known 0.74, which is what makes the number trustworthy. The rear
needs no scene at all: read it off the OVERLAP, where the front field covers
the rear and the front is the probe (known a and P). That also proved the
rear's extent for free - the overlap fit returns a = 0 on exactly the rows
where the rear slot is not there (1690..1698 and 1941..1951).

**Size: matching ER's width, then insetting.** DS3's preview panel is a
narrower rectangle than ER's (45x61 vs 78x98), so no single scale matches
both axes. `SUB_SCALE = 1.156` matches the WIDTH and makes the quad
78 x 105.8; `er_slot_panel.small_slot_rgba` then puts the rules 94 px apart
centred in it and leaves the spare 5 px at each end fully transparent, so
the DRAWN slot is ER's 78 x 98 in both axes. Cost: the atlas holds 1.73
texels per screen px here instead of the main panel's exact 2.00.
Sub-pixel residual, left alone: shape 199's bounds are (-22,-30)..(23,31),
so its centre is half a stage px past the sprite origin; the placements put
the origin (and therefore the icon, which IS centred) on ER's slot centre,
which leaves the panel art 0.87 px right and down.

**ER's field has no hard edge anywhere.** Across, from the left edge:
0.25 0.37 0.49 0.62 0.62 0.66 ... 0.69. Down, from the row above the top
rule: 0.27 [rule] 0.52 0.60 0.65 0.67. A linear ramp whose 50% point falls
~1.2 px outside the quad fits the first; the vertical is softer and begins
before the rule.

**Where the placements are read.** The four translates live in the `Fade`
sprite's frame (211 for Item_Top, 217 for Item_Bottom), and **Item_Top's
Fade placement carries t=(9,8) which the engine IGNORES** - measured, not
assumed: our spell panel lands at 4K (370, 1709) and our flask at
(371, 1930), which is the chain with the Fade's own translate dropped and
the `Item` (1,5) inside 217 kept. Another instance of the rule that bit
`TotalSoul`: some named instances are positioned at runtime.

**NOT VERIFIED ON SCREEN, and it cannot be with this save.** The harness
character (shotbot, a fresh Knight) has one item per slot and no spells, so
DS3 draws no previews at all. Proven rather than assumed: run 2 flooded
shape 199 magenta and both rail quads cyan/yellow and captured at 4K - zero
magenta and zero cyan pixels in the whole frame (the only yellow is the
Estus art). So the previews are hidden when there is no next item, and the
sandbox cannot show them; Donnie's real character will. Run 1, the real
build, changed nothing else: the four main rules still read 1607 / 1810 /
1827 / 2030 and the cross is unchanged.

Build: `er_slot_panel.py $B/01_common_soul.tpf.dcx $B/01_common_small.tpf.dcx`
and `er_fe_gfx.py $B/01_000_fe_capover_shift16.gfx $B/01_000_fe_small.gfx --er-slots`.

### The lock-on marker (3 Sep, UNVERIFIED on screen)

`er_lockon.py`: ER's lock-on is a soft pale-blue dot (16 px core, 32 px
glow, measured on burst/hud-lockon-enemy-bar.png; the X-and-ring in
SB_Reticle is the ranged-aim reticle). DS3's `LockOn` sprite 104 stacks
three 32-px quads of `MENU_Lockon01` (white dot once, blue halo twice). The
script ships the atlas at 2x with ER's dot in cell 0 and the same dot at 35%
in cell 1. The harness cannot lock on, so this is NOT in the deployed chain
until Donnie has seen it; to try it, run it last in the texture chain.

### The rim rows (3 Sep)

The two 4K rows directly above each fill. ER draws them as part of the bar;
ours were the shared backdrop's trough rows (black at 0.23 / 0.42 over the
scene), one colour for all three bars. Read against ER's model rather than
against one ER frame, because row -2 is translucent and the scene behind it
differs between ER's sage fog and the sandbox's dark rock.

**ER's rim, measured (`hud_rim.py --er`, six reference frames with different
scenes behind the bars, window 40..100 px in from the fill start):**

| row | what | HP | FP | stamina |
|---|---|---|---|---|
| -1 | OPAQUE, identical in every frame to 0.1 | 94,42,20 | 51,72,64 | 54,73,33 |
| -2 | translucent, `out = c + k*scene` (max residual 0.3) | c=(41,18,10) k=0.264 | c=(16,27,27) k=0.338 | c=(11,20,12) k=0.423 |

**Where the rows come from in the movie.** The fill quads (shape 117 HP,
365 stamina, 374 FP) are 12 stage px tall, y -6..6, and sample base rows
34..46 through a bitmap matrix `stage y = texel v - 40`. Growing each quad
one stage px UPWARD (y -7..6: `Ymin` -120 -> -140 twips, the two vertical
edge records 240 -> 260 with `numBits` 7 -> 8, the top-starting path's
`moveDeltaY`) makes it sample base row 33 as well, i.e. scale-2 atlas rows
+10/+11 of each bar's block, drawn 1:1 on screen rows -2/-1, with the
matrix untouched. `er_fe_gfx.py --fill-rim`. The Current bar's sliding mask
(shape 63, 47 px tall, placed at scaleY 0.3404) clips at y +/-8.0, so the
widened quad needs no mask edit; Delay's quad (113) is left alone because
the tint over a depleted stretch is the trough's own. Round-trip is
byte-count identical (554,317) and `fe_tree.py` reads the new quads as
`uv=[4..252, 33..46]`.

**What the texel has to be.** Under the rim texel on screen sits the
backdrop's trough row (black, alpha `TROUGH[r]`) over the scene, and
Scaleform textures are premultiplied, so with a rim texel (C, a):
`out = C + (1-a)(1-a_trough) * scene`. Matching ER's k gives
`a = 1 - k/(1-a_trough)` (HP 0.66, FP 0.56, stamina 0.45 at -2; 1.0 at -1)
and `C = to_atlas(c)`. Grain comes from the sheet's own rim rows
(`SB_FE_01` strip-2 / strip-1), luminance-relative, pinned to ER's measured
on-screen std for that row (the raw sheet rows at GRAIN_CONTRAST were three
times too grainy: their RGB is noise under alpha ~40). `er_hud_graft.py
graft_rims`.

**Run 1 (native 4K, written premultiplied):** row -1 landed on all three
bars (HP 96,42,21 / FP 52,73,65 / stamina 55,74,34 against the model's
94,42,20 / 51,72,64 / 55,73,33, dE 0.7 / 0.4 / 0.8), which proves the quad
edit and the opaque path. Row -2 came back 5-6 dE too DARK on every bar.
Fitting the three measured rows against the two alpha conventions:
straight alpha with the gamma on RGB predicts FP 17.9,24.8,27.1 and stamina
18.5,23.6,22.9 against the measured 18,26,28 and 18,24,23; premultiplied
predicts 19.9,29.5,31.8 and 20.8,28.6,25.3. **This quad blends STRAIGHT
alpha** (the area-name agent found the same on its MapName quad the same
night). The souls counter's "premultiplied" reading was taken on a placement
carrying an alphaMult cxform; the bar tiles carry none. So the rim texel is
`rgb = to_atlas(c / a)`, alpha `a` as above.

**Run 2 (straight alpha, plus FP's row means pinned to the 40..200 window
instead of the whole mirrored cut, which had FP rows +10..+12 one to two
units high):** the six rim rows against the model evaluated on the capture's
own scene (`hud_rim.py <capture>`):

| bar | row -2 ours / model / dE | row -1 ours / model / dE |
|---|---|---|
| HP | 57,34,28 / 54,33,26 / 1.4 | 96,42,21 / 94,42,20 / 0.7 |
| FP | 33,47,49 / 32,45,47 / 1.0 | 52,73,65 / 51,72,64 / 0.3 |
| stamina | 32,44,38 / 29,39,34 / 2.5 | 55,74,34 / 55,73,34 / 0.8 |

Sum over the six rows 6.7, from 132.2 at the baseline (where they read
24,27,32 / 19,21,25 and so on: the trough's black over the scene). Row -2's
residual is proportional to the scene on every bar: the trough row under the
rim lets through 0.82-0.98 (median 0.86, mean 0.89) of the scene where the
ER-measured trough alpha 0.23 says 0.77, so `TROUGH_UNDER_RIM = 0.88` is the
calibrated transmission and the alpha is `a = 1 - k / 0.88` (HP 0.70, FP
0.62, stamina 0.52).

**Run 3 (final, `TROUGH_UNDER_RIM` 0.88):**

| bar | row -2 ours / model / dE | row -1 ours / model / dE | baseline (rows -2 / -1) |
|---|---|---|---|
| HP | 54,31,24 / 54,33,26 / 1.7 | 96,42,21 / 94,42,20 / 0.7 | 24,27,32 / 19,21,25 (dE 16.5 / 39.7) |
| FP | 30,43,45 / 29,42,44 / 0.8 | 52,73,65 / 51,72,64 / 0.3 | 20,23,27 / 16,18,22 (7.5 / 25.7) |
| stamina | 28,40,33 / 27,38,32 / 1.6 | 55,74,34 / 55,73,34 / 0.8 | 24,27,32 / 19,21,25 (8.7 / 35.9) |

Sum over the six rim rows 5.9 (baseline 132.2). What is left at row -2 is
about two units of G/B on HP and stamina and moves with the scene estimate
(row -5 stands in for the scene under the bar); not worth a fourth run.

**The gamma, 0.87 -> 0.8795 (same runs):** `er_hud_bars.SCREEN_GAMMA` and
`hud_sim.GAMMA` moved together. `hud_rows.py` sum dE over the 24 drawn rows:
HP 9 -> 9, FP 10 -> 7, stamina 11 -> 8, every row within 0.6 (baseline's
worst was 0.8 on three rows; FP row +11 briefly read 1.0 in run 1 until its
row means were pinned to the window, see above).

**Files:** `build/01_common_rim.tpf.dcx` (chain graft -> pledge -> chrome ->
item_panel -> soul_counter -> slot_panel, intermediates `01_common_rim_g3..g6`
and `_soul`) and `build/01_000_fe_rim.gfx` (`01_000_fe_slots.gfx --fill-rim`).
Captures `rim_run1..3.png` in the session scratchpad. Not left deployed.

**Trap, new:** `ds3-shot`'s teardown does `pgrep -f "compatdata-374320|ds3-shot[/\\]game"`
and kills everything that matches, so a `flock ... sh -c 'cp x data/ds3-shot/game/mod/...; tools/ds3-shot ...; cp shots/ingame.png out'`
dies at ANOTHER agent's teardown while still waiting for the lock (empty
log, exit 144, nothing deployed), and at its own teardown before the
trailing `cp` runs. Put the deploy+capture+copy in a script FILE whose
command line names nothing under the sandbox (scratchpad `rim_capture.sh`
pattern: `exec 8>agent.lock; flock 8; cp; ds3-shot; cp`).

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

### The area name card (3 Sep)

The big title that appears mid-screen on entering a new area. `MapName`, in
`01_000_fe.gfx` again, one quad and one text field:

```
sprite 0 depth 475 name='MapName' at stage (960, 488)
  sprite 520   121 frames; every depth-1 placement is a CXFORMWITHALPHA move -
               this sprite IS the fade, nothing else
    sprite 519 78 frames, SIX PER LANGUAGE (labels jpnJP, fraFR, itaIT, deuDE,
               spaES, spaAR, porBR, engUS at frame 42, polPL, rusRU, zhoTW,
               korKR, zhoCN). Language frames re-place the TEXT at their own y;
               engUS re-places nothing, so it inherits fraFR's (0, -43). The
               underline is placed once at frame 0 and survives every frame.
      sprite 516 (0, 64)  -> shape 515, 1200x8 stage px = 2400x16 at 4K,
                             MENU_MapName_Underline (declared 2048x16) UV
                             [4..1204, 4..12], one texel per stage px
      sprite 518 (0, -43) -> text 517, MenuFont_02, 1800 twips, centred, white,
                             with a DROPSHADOWFILTER on the placement
```

**ER's card is not a band.** The brief described "a dark horizontal band with
thin rule lines above and below"; `er-reference/burst/area-name-banner.png` has
no band and no rule above. Fitting `a*P + (1-a)*S` on rows 900..1010 and on the
smooth wall beside the card returns the regression's own bias (~0.12 everywhere,
including rows well outside the card) and nothing else. It is white serif text
and ONE tapered rule beneath it. Measured at 4K:

| | ER |
|---|---|
| text colour | 254,254,254 (clipped white), no visible halo |
| text centre / baseline | x 1919.5 (screen centre), y 1130 |
| cap height | 117 px ('S' apex 1013 to baseline; the 1003 an earlier pass used is the `t`/`l` ASCENDER, and using it made ours 18% too big) |
| rule centre | y 1156, i.e. 26 px under the baseline |
| rule colour / peak alpha | straight (138,139,113) at 0.563, from a per-column regression over the full-strength core (r 0.5-0.7) |
| rule row profile | 1152 .29, 1153 .37, 1154 .48, 1155 .53, 1156 .56, 1157 .54, 1158 .51, 1159 .41, 1160 .29, 1161 .19, 1162 .09 - a Gaussian of sigma 3.4, FWHM 8 px |
| rule width | ~1700 px, full strength to \|dx\| 550 then a near-linear fade to 0 at 850. The left and right fades measure differently (530 px against 200); averaging the two halves about screen centre is the symmetric fit that is painted |

```bash
$V tools/souls-extract/er_mapname.py $B/01_common_slots.tpf.dcx $B/01_common_mapname.tpf.dcx
$V tools/souls-extract/er_fe_gfx.py  $B/01_000_fe_slots.gfx     $B/01_000_fe_mapname.gfx --er-mapname
```

`er_mapname.py` ships `MENU_MapName_Underline` at **2x (4096x32 BGRA)** so one
texel is one 4K pixel across the quad - at 1x the 16-row quad gets 8 texels and
ER's 12 px gradient comes out in 2 px steps. `--er-mapname` sets text 517 to
**1620 twips**, drops the whole card 33.2 stage px (on 519's placement inside
520, which no language frame touches) and moves the underline **-7.2** stage px
(on 516's placement inside 519).

**MenuFont_02 is not the font this mod swaps.** Rendering "Cemetery of Ash" in
Spectral SemiBold beside the capture at a matched cap height shows two
different faces. MenuFont_01 - equipment labels, souls digits - does resolve to
`font/matissepron/font.gfx`, which the port replaced; the area name comes from
a font resource nothing here has touched, and its Latin is a lighter,
higher-contrast old-style serif. So `MAPNAME_ASCENT_EM` (1.0466) and
`MAPNAME_CAP_EM` (0.7240) in `er_fe_gfx.py` are measured off a capture, not
read out of a TTF. Predicting them from Spectral put the baseline 8 px out and
the caps 10% out.

The layout model itself - **first baseline = bounds.Ymin + 2 (Flash's gutter) +
the font's ascent at that fontHeight** - was checked before being trusted: it
predicts the equipment cross's "Estus Flask" label at 4K baseline 2095.7 with
32.7 px caps, and the capture measures 2094 and cap top 2063.

#### The game never raises this card in the harness

`tools/ds3-shot` grew **`DS3SHOT_EARLY=1`**: an early sweep that shoots
continuously from the moment Continue is pressed until six frames past the HUD
probe, keeping every non-blank frame in a 16-deep ring (`ingame_early00..15`,
so a long load cannot fill the disk). It costs no wall clock - the sweep is the
wait - and the default journey is unchanged.

It settles the question. Loading the sandbox save covers the loading screen,
the fade, and the first 25 s of play, and **no frame has the card**: not the
text, and not an underline painted opaque white as a tracer. DS3 raises the
area name on a map transition, and the harness character stands in Cemetery of
Ash with no boundary and no bonfire warp in reach.

So `er_fe_gfx.py --mapname-force` is the measurement rig. Two steps, and the
first alone is not enough:

1. pin every alphaMult in sprite 520 to 256, and put a known string in text
   517's initialText. **Run 4: still nothing** - the engine hides the named
   `MapName` instance itself, the same runtime ownership as `TotalSoul`.
2. place a SECOND, UNNAMED copy of sprite 520 at depth 476, same stage
   position. Nothing knows that instance's name, so nothing hides it. **Run 5:
   the card is on screen**, permanently, and measurable.

It is a probe, not part of the build - it would leave the card up during play.

#### Verified on screen

* run 5 (1920 twips, the wrong cap number): text baseline 1138, 'C' 139 px
  above it, colour 254.7, centre x 1923.5. That is what re-derived
  `MAPNAME_ASCENT_EM` and `MAPNAME_CAP_EM` and dropped the size to 1620.
* run 6, tracer texture: the quad's four edges land **exactly** where the
  arithmetic says. Red marker (source columns 8..47) at 4K x 720..759, blue
  (the last 40) at 3080..3119, the two green top rows at y 1148..1149, the bar
  filling rows 1150..1163. So the quad is x 720..3119, y 1148..1163, its centre
  row 1155.5 against ER's 1156, and **an opaque white texel comes back as
  exactly (255,255,255)** - the 2x atlas is one texel per 4K pixel with no
  filtering and no transfer, the same as `MENU_PlayerHUD2`.
* run 8 (1620 twips, the ER-colour rule): the text is ER's, measured the same
  way on both frames.

  | | ER | ours | |
  |---|---|---|---|
  | baseline (4K y) | 1130 | 1128 | |
  | cap above baseline | 117 ('S') | 117 ('C') | |
  | colour | 254.73 | 254.67 | |
  | centre x | 1919.5 | 1922.5 | screen centre is 1920 |
  | rule centre | 1156 | 1155.5 | gap under the baseline 26 vs 27.5 |

#### The alpha trap: this quad is STRAIGHT, not premultiplied

Run 8's rule came back at a **peak alpha of 0.178 against ER's 0.544**, visibly
narrower, and with NEGATIVE lobes either side - the texel DARKENING the scene
where its alpha was low. Nothing premultiplied can do that. The model that fits
row for row is `out = a*RGB + (1-a)*S` applied to an RGB that was already
`a*C`, i.e. `a^2*C - a*S`, which goes negative wherever `a*C < S`:

| row | 1150 | 1152 | 1154 | 1155 | 1157 | 1159 | 1161 |
|---|---|---|---|---|---|---|---|
| authored a | .152 | .331 | .511 | .557 | .511 | .331 | .152 |
| if premultiplied | .152 | .331 | .511 | .557 | .511 | .331 | .152 |
| if straight | -.039 | .003 | .140 | .191 | .140 | .003 | -.039 |
| **measured** | -.040 | -.033 | .113 | .178 | .121 | -.042 | -.076 |

So `er_mapname.py` writes ER's STRAIGHT colour and ER's alpha here, and keeps
`premultiply()` around unused. **The souls counter's premultiplied finding is
not a property of the engine, it is a property of that quad.** Measure the
blend on each new translucent element rather than inheriting the assumption -
this cost run 8, and the tell was free: an authored alpha ramp whose measured
profile is narrower than the one you painted is being squared.

Estimator note: measure alpha as the per-column least squares
`sum((out-S)(C-S)) / sum((C-S)^2)` with S from rows +/-14, and take the MEDIAN
over columns. The plain regression of `out` on `S` carries a 0.3 pedestal on a
scene as busy as Cemetery of Ash, which is bigger than the thing being
measured; the median estimator reads 0.00 on rows outside the rule on both
frames, which is how you know it is unbiased.

#### The renderer's alpha gain, and the finished card

With the rule authored straight (run 9) the shape came through but the
amplitude did not. Fitting a Gaussian to the alpha profile on both frames with
`curve_fit`:

| | amplitude | centre (4K y) | sigma |
|---|---|---|---|
| authored | 0.557 | 1155.50 | 3.40 |
| rendered (run 9) | 0.673 | 1155.66 | 3.25 |
| Elden Ring | 0.554 | 1156.37 | 2.98 |

So the renderer moves the centre 0.16 px, leaves the width alone, and multiplies
the amplitude by **1.21**. It is not a gamma - a gamma on alpha would change the
width, and the measured/authored ratio is flat along the whole ramp. Splitting
the core columns by scene brightness and solving `out = a*C + (1-a)*S` puts the
gain on the alpha (0.557 -> ~0.72) rather than the colour (C_eff 127/131/112
against the 138/139/113 written), so `er_mapname.py` divides the authored alpha
by `RENDER_ALPHA_GAIN` and fits the Gaussian to ER's own numbers.

ER's rule is also **not centred on the quad's middle row** - fitted centre
1156.37 against a quad of 1148..1163 - and its own centre sits 26 px under a
baseline of 1130, so `rule_patch` centres on quad row 8.21, not 7.5.

The baseline needed two font sizes to pin. `bounds.Ymin + 2 + ascent*em` is the
right shape but the intercept is not `bounds.Ymin + 2`: with 1920 twips landing
at 1138 and 1620 at 1128, the line through both is `stage baseline = 440.6 +
1.1133*em`, and that is what `MAPNAME_ASCENT_EM` / `MAPNAME_BASE_K` hold.

**Run 10, the finished card at native 4K** (`--er-mapname` plus the rule
texture, shot through `--mapname-force`; crop kept as
`build/mapname_ingame_4k.png`):

| | Elden Ring | ours | |
|---|---|---|---|
| text baseline | 1130 | 1130 | |
| cap height | 117 | 117 | round capital, threshold 150 |
| text colour | 254.8 | 254.4 | |
| text centre x | 1919.5 | 1917.0 | different strings |
| rule centre | 1156.37 | 1156.18 | |
| rule peak alpha | 0.554 | 0.581 | 5% high |
| rule sigma | 2.97 | 3.24 | 9% wide |
| rule taper (x 1200/1500/1800/2100/2400/2700) | .19 .48 .57 .57 .58 .27 | .27 .55 .59 .67 .53 .11 | |

The remaining 5% on amplitude is inside the run-to-run spread of the estimator:
the same gain measured 1.208 on run 9's scene and 1.267 on run 10's, and the
apparent sigma gain flipped from 0.96 to 1.04 between them. Tuning further
would be fitting one scene, not the game.

The three player bars are unaffected: HP red still starts at 4K x 424 and ends
at 945, identical to the pre-mapname build. (It nearly was not - binding
`drop, shift = _mapname_offsets()` in `main` clobbered the `shift` that
`--shift-bars` uses in the same scope, and moved all three bars 4.5 px. The
second variable is called `rule_dy` now.)

**Output files** (nothing deployed; the deploy is left on the shared baseline):

| file | what |
|---|---|
| `build/01_common_mapname.tpf.dcx` | the texture, from `01_common_slots.tpf.dcx` |
| `build/01_000_fe_mapname.gfx` | the movie, from `01_000_fe_slots.gfx` |
| `build/01_common_mapname_probe.tpf.dcx` | tracer texture, geometry probe |
| `build/01_000_fe_mapname_force.gfx` | `--er-mapname --mapname-force`, the measurement rig |
| `build/mapname_ingame_4k.png` | run 10, the card on screen at 4K |
