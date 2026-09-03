# DS3 -> Elden Ring menu port: survey and plan (3 Sep 2026)

Offline, personal use. Follows the HUD port (RECIPE.md in data/ds3-ui-port/build).
Captures: DS3 at native 4K via `tools/ds3-shot inventory` (full journey, no
FAST) gives `shots/equipment.png` and `shots/inventory.png`; ER references are
`data/ds3-ui-port/er-reference/burst/{pause-menu-1,equipment-screen,
inventory-key-items,stats-screen,system-menu-quit}.png`.

## The finding that sets the plan

The Equipment and Inventory screens have the SAME skeleton in both games:
title with icon top-left, three columns (grid | item detail | character
status), prompt bar along the bottom, tab strip above the grid. The port is
therefore a RESKIN of shared chrome plus typography, not a relayout. The one
real relayout is the pause menu: DS3 shows a horizontal row of five icon
tiles with a single label; ER shows a vertical list of icon + label rows on
the left and Pouch/Gestures grids on the right.

What differs visually, in order of how much it changes the look:
1. The panels. DS3: near-opaque black leather panels with gold borders,
   corner filigree and an orange highlight; the scene behind is only
   slightly dimmed. ER: the whole frame is blurred and dimmed with a warm
   olive gradient, the columns are soft translucent darker washes with no
   borders at all.
2. The grid cells. DS3: engraved dark cells with a gold frame and an orange
   selection box. ER: plain dark squares, selection is a thin gold frame.
3. Row chrome. DS3 draws a thin rule under every stat row and an icon before
   every label. ER has no per-row rules, only section headers with a small
   icon and a hairline under the title.
4. Typography: same family already (Spectral), ER's sizes are smaller and
   the colour is a warm off-white; ER uses a larger title.
5. Tabs and prompts: ER's tab strip is icons with LB/RB glyphs and a chevron
   under the active tab; prompts use the same glyph style both sides (the
   glyphs are already ER's from the HUD work).

## Which movie draws what (fe_tree.py over build/menus_xml/*.xml)

    == 01_010_messagebox: 34 sprites, 17 shapes, 12 texts
       images: ItemParts MessageBox
       fonts(px): F01@24x12
       root: ? ? ItemList
    == 02_000_ingametop: 50 sprites, 11 shapes, 5 texts
       images: DummyIcon_00000 DummyIcon_00001 DummyIcon_01000 DummyIcon_01001 DummyIcon_01002 DummyIcon_02000 DummyIcon_03000 DummyIcon_03001 DummyIcon_03002 DummyIcon_03003 DummyIcon_04000 DummyIcon_04001 DummyIcon_05000 DummyIcon_06000 DummyIcon_07000 DummyIcon_08000 DummyIcon_09000 ItemPanel_02 ItemParts Top
       fonts(px): F01@21x1, F01@24x4
       root: ItemList
    == 02_010_equiptop: 121 sprites, 56 shapes, 13 texts
       images: AttributeIcon Base BaseU DetailStatus_Base DummyIcon_00000 DummyIcon_00001 DummyIcon_01000 DummyIcon_01001 DummyIcon_01002 DummyIcon_02000 DummyIcon_03000 DummyIcon_03001 DummyIcon_03002 DummyIcon_03003 DummyIcon_04000 DummyIcon_04001 DummyIcon_05000 DummyIcon_06000 DummyIcon_07000 DummyIcon_08000 DummyIcon_09000 EquipSlot InventoryBase ItemPanel_02 ItemParts OptionBase Top
       fonts(px): F01@21x1, F01@24x11, F01@30x1
       root: BG ? StatusBar ? MenuTitle MenuSubTitle ItemName ItemList DetailStatusView AdditionalProperties
    == 02_011_equip: 112 sprites, 53 shapes, 13 texts
       images: AttributeIcon Base BaseU DetailStatus_Base DetailStatus_Base2 DummyIcon_00000 DummyIcon_00001 DummyIcon_01000 DummyIcon_01001 DummyIcon_01002 DummyIcon_02000 DummyIcon_03000 DummyIcon_03001 DummyIcon_03002 DummyIcon_03003 DummyIcon_04000 DummyIcon_04001 DummyIcon_05000 DummyIcon_06000 DummyIcon_07000 DummyIcon_08000 DummyIcon_09000 InventoryBase ItemPanel_02 ItemParts OptionBase Top
       fonts(px): F01@21x1, F01@24x11, F01@30x1
       root: BG WindowList TabList ? StatusBar ? MenuTitle DetailStatusView AdditionalProperties
    == 02_020_inventory: 212 sprites, 118 shapes, 17 texts
       images: AttributeIcon Base BaseDeco DetailStatus_Base DetailStatus_Base2 DummyIcon_00000 DummyIcon_00001 DummyIcon_01000 DummyIcon_01001 DummyIcon_01002 DummyIcon_02000 DummyIcon_03000 DummyIcon_03001 DummyIcon_03002 DummyIcon_03003 DummyIcon_04000 DummyIcon_04001 DummyIcon_05000 DummyIcon_06000 DummyIcon_07000 DummyIcon_08000 DummyIcon_09000 InventoryBase ItemPanel_02 ItemParts ItemTab_Edge OptionBase Top
       fonts(px): F01@21x6, F01@24x10, F01@30x1
       root: BG BackTabList WindowList TabList ? StatusBar ? MenuTitle DetailStatusView AdditionalProperties
    == 02_030_inventory_commandlist: 10 sprites, 4 shapes, 2 texts
       images: CommandList_Base ItemParts MessageBox
       fonts(px): F01@24x2
       root: ItemList StatusBar
    == 02_031_numselect: 11 sprites, 5 shapes, 8 texts
       images: DetailStatus_Base ItemParts NumSelect
       fonts(px): F01@21x4, F01@24x4
       root: ItemList
    == 02_032_sortmenu: 22 sprites, 10 shapes, 3 texts
       images: ItemParts SortList_Base
       fonts(px): F01@24x3
       root: ItemList
    == 02_033_iconhelp: 9 sprites, 5 shapes, 1 texts
       images: IconHelp ItemParts
       fonts(px): F01@24x1
       root: ItemList
    == 02_040_optionsetting: 96 sprites, 40 shapes, 24 texts
       images: Base BaseDeco BrightnessSetting DummyStatus_Face ItemParts OptionBase PC_SettingParts Top
       fonts(px): F01@24x23, F01@30x1
       root: ? BackTabList WindowList TabList ? StatusBar ? MenuTitle
    == 02_050_detailstatus_player: 15 sprites, 3 shapes, 7 texts
       images: DetailStatus_Base DummyIcon_00000 DummyIcon_00001 DummyIcon_01000 DummyIcon_01001 DummyIcon_01002 DummyIcon_02000 DummyIcon_03000 DummyIcon_03001 DummyIcon_03002 DummyIcon_03003 DummyIcon_04000 DummyIcon_04001 DummyIcon_05000 DummyIcon_06000 DummyIcon_07000 DummyIcon_08000 DummyIcon_09000
       fonts(px): F01@21x4, F01@24x3
       root: DetailStatusView
    == 02_051_detailstatus_item: 38 sprites, 4 shapes, 11 texts
       images: DetailStatus_Base DummyIcon_00000 DummyIcon_00001 DummyIcon_01000 DummyIcon_01001 DummyIcon_01002 DummyIcon_02000 DummyIcon_03000 DummyIcon_03001 DummyIcon_03002 DummyIcon_03003 DummyIcon_04000 DummyIcon_04001 DummyIcon_05000 DummyIcon_06000 DummyIcon_07000 DummyIcon_08000 DummyIcon_09000 ItemPanel_02
       fonts(px): F01@21x4, F01@24x7
       root: DetailStatusView
    == 02_052_detailstatus_armor: 37 sprites, 5 shapes, 10 texts
       images: DetailStatus_Base DummyIcon_00000 DummyIcon_00001 DummyIcon_01000 DummyIcon_01001 DummyIcon_01002 DummyIcon_02000 DummyIcon_03000 DummyIcon_03001 DummyIcon_03002 DummyIcon_03003 DummyIcon_04000 DummyIcon_04001 DummyIcon_05000 DummyIcon_06000 DummyIcon_07000 DummyIcon_08000 DummyIcon_09000 ItemPanel_02
       fonts(px): F01@21x5, F01@24x5
       root: DetailStatusView
    == 02_053_detailstatus_spell: 38 sprites, 4 shapes, 11 texts
       images: DetailStatus_Base DummyIcon_00000 DummyIcon_00001 DummyIcon_01000 DummyIcon_01001 DummyIcon_01002 DummyIcon_02000 DummyIcon_03000 DummyIcon_03001 DummyIcon_03002 DummyIcon_03003 DummyIcon_04000 DummyIcon_04001 DummyIcon_05000 DummyIcon_06000 DummyIcon_07000 DummyIcon_08000 DummyIcon_09000 ItemPanel_02
       fonts(px): F01@21x5, F01@24x6
       root: DetailStatusView
    == 02_054_detailstatus_arrow: 37 sprites, 4 shapes, 10 texts
       images: DetailStatus_Base DummyIcon_00000 DummyIcon_00001 DummyIcon_01000 DummyIcon_01001 DummyIcon_01002 DummyIcon_02000 DummyIcon_03000 DummyIcon_03001 DummyIcon_03002 DummyIcon_03003 DummyIcon_04000 DummyIcon_04001 DummyIcon_05000 DummyIcon_06000 DummyIcon_07000 DummyIcon_08000 DummyIcon_09000 ItemPanel_02
       fonts(px): F01@21x5, F01@24x5
       root: DetailStatusView
    == 02_055_detailstatus_weapon1: 72 sprites, 25 shapes, 30 texts
       images: AttributeIcon DetailStatus_Base DummyIcon_00000 DummyIcon_00001 DummyIcon_01000 DummyIcon_01001 DummyIcon_01002 DummyIcon_02000 DummyIcon_03000 DummyIcon_03001 DummyIcon_03002 DummyIcon_03003 DummyIcon_04000 DummyIcon_04001 DummyIcon_05000 DummyIcon_06000 DummyIcon_07000 DummyIcon_08000 DummyIcon_09000 ItemPanel_02
       fonts(px): F01@21x20, F01@24x10
       root: DetailStatusView
    == 02_057_itemdetailtext: 9 sprites, 2 shapes, 14 texts
       images: DetailStatus_Base DetailStatus_Base2 Dish DummyItemKnowledgeIcon
       fonts(px): F01@24x14
       root: DetailStatusView
    == 02_070_status: 115 sprites, 55 shapes, 24 texts
       images: AttributeIcon Base BaseU DetailStatus_Base DummyIcon_00000 DummyIcon_00001 DummyIcon_01000 DummyIcon_01001 DummyIcon_01002 DummyIcon_02000 DummyIcon_03000 DummyIcon_03001 DummyIcon_03002 DummyIcon_03003 DummyIcon_04000 DummyIcon_04001 DummyIcon_05000 DummyIcon_06000 DummyIcon_07000 DummyIcon_08000 DummyIcon_09000 DummyStatus_Face DummyStatus_Preview EquipSlot ItemPanel_02 OptionBase StatusCharaNoise Top
       fonts(px): F01@21x9, F01@24x14, F01@30x1
       root: ? StatusBar ? MenuTitle BG DetailStatus LeftPane
    == 02_080_warp: 67 sprites, 33 shapes, 7 texts
       images: AutoSave Base BaseDeco BusyIcon BusyTab DummyStatus_Face ItemParts OptionBase WarpIcon
       fonts(px): F01@24x6, F01@30x1
       root: ? BackTabList BackTabList_HL WindowList TabList TabList_HL ? StatusBar ? MenuTitle
    == 02_110_detailkeyguide: 17 sprites, 10 shapes, 4 texts
       images: ItemParts MessageBox
       fonts(px): F01@24x4
       root: ItemList
    == 03_002_bonfire: 20 sprites, 9 shapes, 5 texts
       images: Base BaseDeco DetailStatus_Base ItemParts OptionBase
       fonts(px): F01@21x1, F01@24x3, F01@30x1
       root: Base
    == 03_010_levelup: 62 sprites, 21 shapes, 18 texts
       images: Base BaseDeco BaseU DetailStatus_Base DummyIcon_00000 DummyIcon_00001 DummyIcon_01000 DummyIcon_01001 DummyIcon_01002 DummyIcon_02000 DummyIcon_03000 DummyIcon_03001 DummyIcon_03002 DummyIcon_03003 DummyIcon_04000 DummyIcon_04001 DummyIcon_05000 DummyIcon_06000 DummyIcon_07000 DummyIcon_08000 DummyIcon_09000 EquipSlot ItemPanel_02 ItemParts LV_UP OptionBase
       fonts(px): F01@21x8, F01@24x9, F01@30x1
       root: ? StatusBar ? MenuTitle BG Status_0 Status_Player Control

Shared chrome textures in `menu/01_common.tpf.dcx` (see the contact sheet in
the session scratchpad; `tpf_png.py` re-exports them):

| texture | what |
|---|---|
| MENU_Base 2048x2048 | the big black leather panels + the title bar strip + stat-row rules |
| MENU_BaseU 2048x2048 | more panels (the column backs) |
| MENU_DetailStatus_Base / _Base2 | the detail and status column backs |
| MENU_InventoryBase 1024x1024 | the grid panel + tab icons + the 2x2 selection frame |
| MENU_OptionBase | option/warp panels, small icons |
| MENU_Top 1024x1024 | the PAUSE MENU: five icon tiles, the tile row backdrop, the orange rule |
| MENU_ItemParts 1024x512 | orange highlight frames, glows, thin rules, arrows, the red X |
| MENU_EquipSlot 1024x512 | the engraved equipment grid cells |
| MENU_ItemTab_Edge | inventory tab icons |
| MENU_BaseDeco 256x256 | the gold corner filigree |
| MENU_L_Title 848x96 | the title bar underline |
| MENU_AttributeIcon, MENU_EquipLabel | per-row stat icons, equipment labels |

ER's art for the same jobs (`extract/er/png`): SB_MainMenu (2048x2048: the
big washes and gradients), SB_MainMenu_02 (panels, section icons),
SB_MainMenu_03 (a full-frame gradient), SB_In_GameTop (pause menu list
chrome + the menu icons), SB_Tab (tab icons), SB_ItemBox (grid cell art),
SB_Status_00 (stat icons), SB_Icon_00..03 (item icons, 4096x2048 each).

## Plan, in phases that can run in parallel (different files each)

A. **The wash** (textures only: MENU_Base, MENU_BaseU, MENU_DetailStatus_Base,
   MENU_DetailStatus_Base2, MENU_InventoryBase panel regions, MENU_OptionBase,
   MENU_L_Title, MENU_BaseDeco). Measure ER's column washes (fit
   a*P+(1-a)*S against the blurred scene; note ER blurs and dims the WHOLE
   frame, which DS3 may do with its own full-screen dim, measure that too),
   repaint the panels as ER's soft washes, drop the gold borders and the
   filigree. Biggest visual change, no movie edits, applies to every screen.
B. **Grid cells, highlight, row rules** (textures MENU_EquipSlot,
   MENU_ItemParts, MENU_ItemTab_Edge, MENU_AttributeIcon). ER's plain dark
   cells and thin gold selection frame; remove the per-row rules or thin them
   to ER's hairline; tab icons to ER's SB_Tab art.
C. **Typography and headers** (movies 02_010_equiptop, 02_011_equip,
   02_020_inventory, 02_070_status, 02_055_detailstatus_weapon1): text sizes,
   colours and positions to ER's measured values; the title size; section
   headers. `er_fe_gfx.py`-style flags, one per movie, via fe_tree.py.
D. **The pause menu** (02_000_ingametop.gfx + MENU_Top): vertical icon+label
   list on the left like ER's; ER's icons from SB_In_GameTop. The hardest
   piece: the labels are one text field today, ER shows one per row.

Each phase verifies with `tools/ds3-shot inventory` (full journey, 4K,
DS3SHOT_MOD=1) under the shared flock, reading equipment.png and
inventory.png; D needs the pause-menu shot (see run_dev / ig_menu.png in
shots/ for how it was taken on 1 Sep).

Alpha convention is per element (see RECIPE): measure each new translucent
texture with one capture before trusting its blend.

## Phase C: typography (3 Sep 2026, night)

Tool: `tools/souls-extract/er_menu_gfx.py <in.gfx> <out.gfx> --screen
equiptop|equip|inventory|status|weapon1|player|item`. Outputs
`build/02_*_er.gfx` for the seven movies (the four named in the plan plus
`02_055_detailstatus_weapon1`, `02_050_detailstatus_player` and
`02_051_detailstatus_item`, which the engine loads into `DetailStatusView`
and which draw the centre and right columns). Nothing is left deployed; the
deploy recipe is `build/typography_capture.sh`. Verified at native 4K on
`build/typography_run3_{equipment,inventory,status}.png`.

### What the harness shows

Tracer run 1 (equiptop's `ItemName` text 82 painted pure red, equip's text 169
pure blue): the equipment screenshot has the red "Fists" under "Right Hand
Weapon 1" and no blue anywhere, so **`shots/equipment.png` is
`02_010_equiptop` (the slot picker)**; `02_011_equip` (the item list behind
a slot) is never on screen in the journey. An attempt to add it (press `e` on
the slot, shoot, `q`) broke the journey: the "equipment" shot came back as the
Inventory screen with the Use/Leave/Discard popup, and every later shot was
bare gameplay. Not retried. The Status screen was added instead and works:
from Inventory, `q`, `Right`, `e`, shoot, then `q`, `Right`, `Right`, `e` to
System for the clean quit (`build/ds3-shot-status-copy`, a scratch copy of
`tools/ds3-shot`; the tool itself is untouched).

### ER measured, glyph by glyph (4K px, `glyphs.py` in the session scratchpad)

| | Elden Ring | DS3 baseline (`ds3_equipment_4k.png`) |
|---|---|---|
| title cap ('E' of Equipment) | 43, top y 97, left x 245 | 40, top 156, left 287 |
| title icon | 120x120 at x 97..216, y 52..171 | 120x120 at 148..267, 114..233 |
| title colour (mode) | (192,177,148) | (199,185,158) |
| grid subtitle ('R' of Right Hand) | cap 32, y 244, x 244 | cap 32, y 312, x 218 |
| grid item name | cap 33, y 321, x 244 | cap 32, y 372, x 218 |
| centre item name ('R' of Rivers) | cap 40, y 246, x 1488, (204,204,204) | cap 32, y 312, x 1378, (210,210,210) |
| centre labels | cap 32, x 1549 | cap 32, x 1430 (icon at 1377) |
| centre values, right edge | 2102 (guard sub-column 2755) | 1959 (2461) |
| right column header | cap 33, x 2914 (icon 2870), gold | cap 32, x 2674, gold |
| right column labels ('L' of Level) | cap 31, x 2913, (204,204,204) | cap 32, x 2726 (icon 2690), (200,200,186) |
| right column values | digits 27 tall, right edge 3621, (204,204,204) | 28 tall, 3622, (210,210,210) |
| row pitch, status column | 59-60 | 60 |
| row pitch, Status screen | 64 | 64 (`Status_0` rows every 32 stage px) |
| section gap (Level -> Vigor, etc) | 116-122 | 116-152 |
| prompt line 1 ('S' of Select) | cap 33, baseline 2021, x 246 | cap 33, baseline 1962, x 206 |
| prompt line 2 (badge / text) | badge 250..304 x 2050..2104, baseline 2094 | badge 208..263, baseline 2034 |
| body colour (mode over the status column) | (204,204,204), 3149 px exactly 204 | see above |
| Status screen player name ('A' of Arcana) | cap 40, (204,204,204) | gold, 480 twips |

Two things the plan had wrong. **Body text is already ER's size**: labels are
cap 31-32 in both games (480 twips, cap 0.667 em), digits 27-28 (420 twips),
prompts cap 33, pitches equal. Only the title (43 vs 40) and the centre
column's item name (40 vs 32) differ. And **ER's text is neutral, not warm**:
the core is (204,204,204) on 3149 px of the status column, the same `#cccccc`
DS3 authors, and its headers are DS3's own gold (192,177,148). The warmth is
the olive wash showing through the anti-aliased edges. What DS3 does
differently is paint every stat label and value in a green-grey
(193,194,178), and lift everything through its output transfer.

### The transfer, and who owns a field's colour

DS3 draws text through the same `screen = 255*(c/255)^0.8795` the HUD
textures go through (RECIPE): authored 204 reads 210, (192,177,148) reads
(199,185,158), both measured on the baseline and on run 1. ER's screen values
are its authored values. So the movies author pre-compensated colours,
**198 for grey and (185,168,137) for gold**, and run 2/3 read exactly
(204,204,204) and (192,177,148) on every field that honours `textColor`.

Not every field does. **Every `Value_*`, `OwnNum`, `RequiredNum` and
`StockNum` instance is written by the engine as html with its own colour**:
on the baseline the values read 210 while their `textColor` was
(193,194,178), and on run 2 they still read 210 beside labels at 204. Those
placements get a `CXFORMWITHALPHA` mult 248/256 instead (the engine's
`#cccccc` times 0.969 = 197.6, lifted to 204) and their `textColor` goes back
to plain 204. Fields named `Text_0`, `StaticText_*`, `KeyGuide`, `LineHelp`,
`ItemName` and the unnamed separators honour `textColor`. Run 3: values,
"Consumable", the item-effect text, the Status screen's name and every
number read (204,204,204).

### Edits per movie (ids)

| movie | edits |
|---|---|
| 02_010_equiptop | title text 76: 600 -> 645 twips, bounds scaled, placement in sprite 77 (-126,-19) -> (-147,-49.25) stage px; icon 75 in sprite 77 (-164,0) -> (-189.5,-31); prompt texts 68/69 in sprite 70 +(20,30); 5 green fields -> grey; 11 grey -> 198, 2 gold -> (185,168,137); cxform on 190, 208, 213, 215 |
| 02_011_equip | the same on 185 / sprite 186 / icon 184, prompts 177/178 in 179, cxform 135, 190, 199, 204 (NOT verified on screen, see above) |
| 02_020_inventory | title 362 / sprite 363 / icon 361, prompts 349/350 in 351, 12 grey, 3 gold, cxform 275, 278, 313, 314, 373 |
| 02_070_status | title 40 / sprite 41 / icon 39, prompts 32/33 in 34, player name 216: 480 -> 600 twips, gold -> grey, dy -6 (baseline kept); 16 green, 19 grey, 5 gold, cxform 78, 85, 87, 90, 94, 163, 216, 218 |
| 02_055_detailstatus_weapon1 | item name 144: 480 -> 600, dy -6 in sprite 145; 16 green, 28 grey, 2 gold, cxform on 16 value placements |
| 02_050_detailstatus_player | 6 green -> grey (the Player Status labels), 1 gold, cxform 26, 30, 34 |
| 02_051_detailstatus_item | item name 69: 480 -> 600, dy -6 in sprite 70; 6 green, 10 grey, 1 gold, cxform 25, 31, 34, 37, 39, 41 |

The y numbers come from `baseline = field top + 2 + 1.0*em` (cap 0.667 em),
checked on the subtitle and the prompt bar before use; the title's field top
was solved for ER's baseline 140 at em 32.25. Named root instances were left
alone and their children moved, after the `TotalSoul` lesson; on these
screens the children moved exactly as computed.

### After (run 3, 4K) against ER

| | ER | run 3 |
|---|---|---|
| title 'E' | 245..277 x 97..139, cap 43 | 245..280 x 97..140, cap 44 |
| title icon right edge / top | 216 / 52 | 216 / 52 |
| title colour | (192,177,148) | (192,177,148) |
| centre item name cap | 40 | 41 ('F' 304..344, baseline 344 as before) |
| centre name / labels / values colour | 204 | 204 / 204 / 204 |
| right column labels / values | 204 / 204 | 204 / 204 (baseline 200,200,186 / 210) |
| gold headers and subtitle | (192,177,148) | (192,177,148) (baseline 199,185,158) |
| prompt line 1 'S' | 246..264, 1989..2021 | 246..267, 1990..2022 |
| prompt line 2 badge | 250..304, 2050..2104 | 248..303, 2050..2106 |
| prompt colour | 204 | 204 (baseline 210) |
| Status screen name | grey cap 40 | grey, 600 twips ("shotbot" has no capital to measure) |
| Status screen pitch | 64 | 64 |

The DS3 rendering measures caps one px taller than ER's throughout (32 vs 31,
28 vs 27, 44 vs 43): that is the threshold on a different face's
anti-aliasing, not a size error, and the same 1 px shows on the untouched
body text.

### Not changed, and why

* **Column x positions.** ER's columns sit further right and wider (panels at
  4K: left 192..1382, centre 1470..2820, right 2880..3725 against DS3's
  182..1344, 1354..2621, 2630..3648; label columns 1549 / 2913 against 1430 /
  2726; value right edges equal). They are governed by the panel quads in the
  `BG` sprites and by `DetailStatusView`'s children, and phase A paints the
  washes into those quads, so moving the text alone would leave it off the
  wash. Text-to-column insets are within a few px of ER's already. Left as a
  measured table for a later relayout pass, if one is wanted.
* The centre item name's x (ER 1488, ours 1378): in both games it sits ~55 px
  left of the label column, so it moves with the column, not on its own.
* Per-row icons, rules, section-header icons, the LB/RB tab labels: phase B
  textures. ER's header icons would also need placements; not attempted.
* "Attack power" vs ER's "Attack Power": engine strings.
* `02_011_equip` carries the same edits as `02_010_equiptop` but the harness
  cannot show it.

## Phase D: the pause menu (3 Sep)

### How it is built (`02_000_ingametop.gfx`, fe_tree.py over build/menus_xml)

Root `ItemList` (sprite 86, 41 frames) at stage (580, 640); one stage px is
two 4K px. Everything below is relative to that origin.

| what | sprites | detail |
|---|---|---|
| the panel | 86 depth 1 -> 23 -> 22 (alphaMult 218/256) -> shape 21 | 600x400 stage px, MENU_Top [4..604, 172..572]. Sprite 86's frames 1..41 re-place depth 1 with alphaMult 0 -> 256 -> 0: the panel's fade in and out |
| the five tiles | `Item_0_0..4` = sprites 67/64/61/58/55 at y -100, x -196 + 98k | each is one 90x90 quad (shapes 65/62/59/56/53, MENU_Top [4+100k..94+100k, 4..94], one texel per stage px) plus a `Cursor` (sprite 50, MENU_ItemParts [4..180, 304..480] at 0.5625 = 99 stage px). Sprite 67 has 18 frames; a later frame dims the tile (mult 90/256) |
| a sixth slot | `Item_0_5` = sprite 52 at (296, -100) | a Cursor and NO tile; the sixth icon in the texture ([504..594, 4..94], a face) is referenced by no shape |
| the quick items | `Item_1_0..4` = sprite 51 at y 55, x -196 + 98k | `Dish` (sprite 26 at 0.625 -> shape 24, MENU_ItemPanel_02 [124..220, 180..216], the brown ellipse), `ItemIcon` (engine-attached art, 160 px at 0.625), `StockNum` (21 px, right-aligned at (2,24)), `Cursor` at (0.5625, 0.625) |
| the label | `RowText` (77) -> `Item_0` (76, y -29) and `Item_1` (74, y 118) | each holds a highlight band (shape 68, 780x12), a rule (shape 71, 780x4, MENU_Top [4..784, 580..584]) and ONE right-aligned 24 px text `Text_0` at (-480, -32): bounds 210 wide, so it ends at stage x 310, LEFT of the panel. **The engine writes the highlighted tile's name into Item_0's Text_0** (its initialText is a run of black squares); that is the lone "Equipment" beside the panel in the 1 Sep capture, with the rule under it running the panel's width. Item_1's says "Personal Effects" and never shows |
| the orange rule | 86 depth 68 -> sprite 79 (scale 1.07) -> shape 78 | MENU_Top [4..492, 568..576] |
| the prompts | `StatusBar` (81, y 144) -> `KeyGuide` text 80 at (-270, -15) | 24 px, left-aligned, 542 wide |
| the selected quick item's name | `CurrentItem` (85, y -9) -> `Text` -> `Item_0` -> `CurrentItemName` text 82 at (-239, -15) | 24 px, 480 wide, sits between the two rows |

The strings are DS3's own, from `FDP_メニューテキスト.fmg` 101000..101005 in
`msg/engus/menu_dlc2.msgbnd.dcx` (the base `menu.msgbnd` is not in the
archives this box has; the DLC2 bundle carries the full set): Equipment,
Inventory, Status, System, Message, Toolbelt. Tile order on the bar:
Equipment, Inventory, Status, Message, System.

### Elden Ring, measured (burst/pause-menu-1..3.png, 4K)

| | ER |
|---|---|
| row pitch | 192 px (label baselines 521, 711, 904, 1096, 1289, 1479, 1672) |
| tile | unlit frame x 108..240, y 434..570 (~133x137), centre (174, 503 + 192k); the lit tile is a bright wash over the tile (row-1 interior 113/106/80 lit vs 94/86/67 unlit) with a glow that runs to the screen's left edge (+17..40 lum at x 0..300 over the row's 150 px) and fades out by x ~900 |
| label | starts x 283, cap height 30 px ('S' 875..904), baseline = tile centre + 18, colour (209,197,173) whether lit or not (lit reads +3) |
| icons | SB_In_GameTop cells, 142x146 texels, drawn at ~0.94: System col0, Status col1, Item Crafting col4, Inventory grid01, Equipment grid11 (correlation 0.41..0.62 against the screen tiles), Messages grid00 |
| band | a light haze BEHIND the list, not a shadow: the band reads ~45..50 where ER's dimmed scene outside it reads 15..33. The art is SB_In_GameTop's 620x1240 blob, (42,42,36) at alpha 250 in the sheet |
| pouch | "Pouch" header x 3381..3538, y 436..475; two columns of ~152 px cells at x 3418 / 3577, rows from y 512 with a 178 px pitch (cell 155 tall); items sit in the cell with the count bottom-right |
| prompts | A glyph x 124..172, y 1858..1907; "OK" text rows 1866..1898, x 188..456; B glyph x 281..332 |
| frame dim | the whole scene is dimmed and blurred; DS3's pause dims by only 0.98 (measured against the same-scene `ingame` shot) |

### What was changed

`tools/souls-extract/er_pause_gfx.py <in.gfx> <out.gfx>` (36 edits, JPEXS
round trip, `build/02_000_ingametop_er.gfx` plus the edited XML beside it)
and `tools/souls-extract/er_pause_menu.py <in.tpf.dcx> <out.tpf.dcx>
[--preview dir]` (`build/01_common_pause.tpf.dcx` from `01_common_final`;
MENU_Top shipped at 2x, 2048x2048 BGRA, one texel per 4K px):

* the six `Item_0_k` placements go from a row into a column at stage
  (-493, -388.5 + 96k) relative to ItemList, i.e. 4K tile centres (174, 503 + 192k).
* each 90x90 tile quad (shapes 65/62/59/56/53) is rewritten as a 280x80
  stage-px STRIP (bounds -45..235 x -40..40) sampling its own atlas row
  [0..280, 620+80k..700+80k]: ER's icon cell at 0.94 centred at (45,40) and
  the label baked beside it (Spectral SemiBold sized for a 30 px cap, x 99.5,
  baseline +9). The shape rewrite is one helper, `rect_shape` (bounds, the
  bitmap matrix translate, the five records, JPEXS's bit widths), reused for
  the Dish below.
* the tile `Cursor` (sprite 50, phase B's MENU_ItemParts highlight) scaled
  0.5625 -> 0.425 so it hugs the 68 stage-px tile.
* the panel (sprite 23) is now the band: placement scaled (0.6833, 2.0) and
  moved so the 600x400 quad covers 4K -100..720 x 300..1900, its alphaMult
  218 -> 256, and the leather art replaced by a painted haze (plateau to
  x 430, cosine fade to 720; vertical fades 300..440 and 1760..1900).
* the orange rule placement dropped; RowText's two bands and two rules
  dropped; both `Text_0` fields moved 4000 px off screen (kept, so the
  engine's write still has a target).
* the quick items become the Pouch grid: `Item_1_k` scaled 0.76 at 4K
  centres (3494/3654, 590/768/946) in ER's left-to-right, top-to-bottom order;
  shape 24 (the Dish ellipse, MENU_ItemPanel_02) is retargeted to MENU_Top's
  bitmap id and made a 160x160 quad centred under the icon, sampling a
  painted ER-style cell (dark field, thin rim); its Cursor 0.568.
* KeyGuide to ER's prompt spot (-554, 140) at 27 px em; CurrentItemName
  under the pouch grid.
* atlas values are written through the inverse of the render transfer
  (`to_atlas`, gamma 0.8795): run 1 read the labels at 214/203/181 from a raw
  209/197/173 and the unlit tile 4/6/8 brighter than ER's.

### What the static timeline could not do

* **Per-row labels are art, not text.** One engine-written field per row
  exists; there is no way to have the engine write five names. Baked labels
  cost nothing while the strings are fixed, but a language change or a
  renamed item would need the atlas repainted. The engine's own label is
  parked off screen rather than removed.
* **The lit row.** ER lights the tile with a wash and a glow to the screen's
  left edge. DS3's only highlight element is the `Cursor` (MENU_ItemParts,
  phase B's texture); it is sized to the tile, and the look of the highlight
  is whatever phase B paints there.
* **The unavailable item dims as a whole strip.** The engine dims
  `Item_0_3` (Message, offline) with mult 90/256; since the label is part of
  the strip quad, the label greys with it. ER greys unavailable items too.
* **No frame dim, no headers.** DS3's pause dims the frame by 0.98 (ER dims
  and blurs the whole scene); that is not in this movie. ER's "Pouch" and
  "Gestures" headers and the Gestures grid have no DS3 element to carry them.
* **The sixth slot.** `Item_0_5` is a cursor with no tile; it is placed at
  row 6 (y 91.5) in case a mode ever shows it.

### Captures (native 4K, `DS3SHOT_PAUSE=sweep DS3SHOT_MOD=1`, scratchpad `pause_runN_pausemenu*.png`)

`tools/ds3-shot` grew `DS3SHOT_PAUSE=1` (a `pausemenu` shot right after the
Escape that opens the bar, before the Equipment step; the default journey is
unchanged) and `DS3SHOT_PAUSE=sweep` (also `pausemenu_1..4`, stepping Right
through the other four items and walking back). The 1080p 1 Sep `ig_menu.png`
is the before.

| | ER | before (DS3 1080p x2) | run 1 | run 2 | run 3 |
|---|---|---|---|---|---|
| layout | column, 7 rows | a row of five tiles, one label left of the panel | column, 5 rows | same | same |
| tile centre row 1 | (174, 503) | (965, 1078), row of five | (170.5, 503) | (170, 502.5) | (171, 503); lit System row centre 1271.0 against a target 1271 |
| tile frame | 133x137 | 172x174 | 130x137 | 131x136 | 127x137 |
| label x / cap / baseline | 283 / 30 / 521 | 344..590 right-aligned, left of the panel / 44 / 1204 | 286 / 30 / 520 | 286 / 30 / 520 | 286 / 30 / 520 |
| label rows Status / Message | 875..904 / 1259..1301 | n/a | 875..904 / 1259..1288 | 875..904 / 1259..1288 | 875..904 / 1259..1288 (ER's 1301 is the g descender) |
| label colour | 209,197,173 | 172,159,137 | 214,203,181 | 209,197,173 | 209,197,173 |
| unlit Inventory tile interior | 102.6, 92.3, 72.7 | (DS3 art) | 107.0, 98.7, 81.5 | 99.0, 90.4, 72.4 | 97.8, 89.2, 71.5 |
| unlit Status tile interior | 68.6, 64.1, 51.7 | | 73.1, 70.0, 60.6 | 69.7, 66.5, 55.6 | 66.2, 62.9, 53.1 (System 93.1, 85.5, 69.3 vs ER 96.1, 87.5, 69.2) |
| band | haze converging on ~47 | opaque leather panel 560..1760 x 880..1680 | invisible: (42,42,36)@0.55 is screen 52 over rocks at 50 | converges on ~55, fit out = 55 + 0.22 S at x<250 | out = 41.5 + 0.12 S (x 250..500), 44.9 + 0.24 S (x<250): converges on ~47; 0.87 S at x 700..900 (the fade), 0.97 S above the list (DS3's own dim) |
| prompt: glyph / text start | 124..172 / 188 | 694 | 142..169 / 196 | 70..97 / 124 | 134..161 (centre 147.5 vs ER 148) / 188 |
| pouch cell 1 | 512..667, interior 37..40 vs ~48 outside | n/a (a row of five) | rims at 514 and 666 | same | rims 514/515 and 664/665, interior 37.8 over a scene of 48.2 |

Run 3 is the build left in `build/` (`01_common_pause.tpf.dcx`,
`02_000_ingametop_er.gfx`); nothing is deployed, the mod dir is back on the
shared baseline. The lit tile is DS3's orange Cursor at the tile's size until
phase B repaints MENU_ItemParts. Per-run captures: scratchpad
`pause_run{1,2,3}_pausemenu*.png`.

## Phase A: the wash (3 Sep)

Script: `tools/souls-extract/er_menu_wash.py <in.tpf.dcx> <out.tpf.dcx>
[--preview dir]`. Build:

```bash
V=data/ds3-ui-port/.venv/bin/python; B=data/ds3-ui-port/build
$V tools/souls-extract/er_menu_wash.py $B/01_common_final.tpf.dcx $B/01_common_wash.tpf.dcx
```

Textures touched: MENU_Base, MENU_BaseU, MENU_DetailStatus_Base,
MENU_DetailStatus_Base2, MENU_InventoryBase (panel region only), MENU_OptionBase,
MENU_L_Title, MENU_BaseDeco. No movie edits.

### What ER actually does, measured at 4K

**There is only ONE column wash, and it is the item grid's.** The plan above
said "each column is a soft translucent darker wash"; the capture says the
item-detail and character-status columns have NO panel at all. The profile
through the gap between the grid and the detail column (x 1350..1450) and the
profiles through the detail column (x 1600..1700) and the status column
(x 3300..3400) agree row for row within about a unit at every y. ER draws that
text straight onto the dimmed frame, with one vertical hairline as the divider.

**The grid wash**, fitted as `out = a*P + (1-a)*S` by regressing the band just
inside each edge against the band just outside, over ~350 rows, on two screens:

| edge | a (R/G/B) | P (R/G/B) |
|---|---|---|
| equipment right | 0.537 / 0.536 / 0.496 | 27.3 / 25.1 / 20.5 |
| equipment bottom | 0.516 / 0.553 / 0.544 | 30.8 / 31.4 / 26.5 |
| equipment left | 0.478 / 0.485 / 0.431 | 23.8 / 22.4 / 16.1 |
| inventory right | 0.541 / 0.547 / 0.510 | 27.1 / 25.6 / 21.0 |
| inventory bottom | 0.494 / 0.540 / 0.529 | 27.4 / 29.1 / 25.1 |

**a = 0.52, P = (27, 26, 21).** It is not a black panel. Over the dark top of
the frame (S ~ 17) it LIFTS the scene to ~22; over the bright fog at the bottom
(S ~ 82) it pulls it down to ~54, and both were checked against the capture.
Feather 45 px at 4K on the sides, ~85 px at the bottom, ~20 px at the top with
a hairline sitting on it.

**Everything ER draws in these screens shares one chromaticity, R:G:B =
1.00 : 0.99 : 0.81.** The wash colour, the hairlines and the menu background's
own average all sit on it. That is what "warm olive" is, and it is also the
tell that ER GRADES its menus: across nine gameplay frames the background sits
at R/G 0.54..0.80 and B/G 0.86..0.95 (green-dominant); across the three menu
frames it sits at R/G 1.00..1.07 and B/G 0.78..0.82, on two different scenes.

**Hairlines** are the same gold as the HUD key line, (145, 141, 110), as a
Gaussian of sigma 3.3 px at 4K (FWHM 7.8), at three peak alphas:

| line | measured | over | solved alpha |
|---|---|---|---|
| grid wash top edge | 47, 47, 39 | 20, 20, 17 | 0.22 |
| section rule (stats screen, y306) | 81, 82, 67 | 41, 41, 34 | 0.39 |
| column divider (x 2882) | 110, 109, 89 | 43, 43, 35 | 0.66 |

**The title strip is LIGHT, not dark.** The plan expected "a soft dark strip";
the capture has a warm HAZE, y 44..190 at 4K with a 12 px top edge and a 60 px
bottom fade, reading 37,37,28 over a 15,17,13 background at x 620..1180 and
51,51,39 at x 0..300, fading to nothing by x ~1400. Solved against the same
gold it is alpha 0.28 at the left falling to 0.17 by x900, and the B channel
that solution predicts (29.4) lands on the measured 28, which is what makes the
identification trustworthy. Equipment and inventory give the same numbers to
within a unit on different scenes, so it is a UI element and not the sky.

**ER's global dim cannot be measured from this reference set.** No gameplay
frame shares the menu frames' scene: equipment/inventory sit over bright fog,
the pause frames over a dark rock face, correlation 0.005 after a sigma-30
blur. What can be said is that ER's menu background is not much darker than its
gameplay (means 48..53 against 27..60 over nine gameplay frames): the calm
comes from the BLUR, which no texture can do.

### How DS3 draws its menu frame

`fe_tree.py` over `build/menus_xml/{02_011_equip, 02_020_inventory,
02_010_equiptop, 02_070_status}.xml`. Identical in all four; everything is one
texel per stage px, i.e. one texel per two 4K pixels.

| texture | uv | 4K rect | cxform |
|---|---|---|---|
| MENU_Base | [4..1824, 4..816] | x 100..3740, y 268..1892 (BG_L) | none |
| MENU_Base | [4..368, 4..816] | x 100..828, y 268..1892 (BG_S) | none |
| MENU_OptionBase | [1444..1740, 4..816] | x 828..1420, y 268..1892 (BG_S) | none |
| MENU_BaseU | [4..342, 4..804] | x 140..816, y 280..1880 | RGB 247/256, add (+2,0,+4) |
| MENU_BaseU | [1368..1658, 812..1612] | x 816..1396, y 280..1880 | same |
| MENU_DetailStatus_Base | [4..1192, 4..804] | x 1340..3716, y 280..1880 | same |
| MENU_DetailStatus_Base2 | [4..1192, 4..804] | the SAME rect, depth 9 | same |
| MENU_InventoryBase | [4..624, 24..696] | x 140..1380, y 536..1880 | none |
| MENU_Base | [4..1924, 1148..1278] | x 0..3840, y 0..260 (top bar) | **alphaMult 243/256 = 0.949** |
| MENU_Base | [4..1924, 824..954] | x 0..3840, y 1900..2160 (bottom bar) | **alphaMult 243/256** |

The two alphaMults are compensated in the script (author alpha/0.949). The
RGB 247/256 + add cxforms sit on blocks that are blanked, so they have nothing
to act on. In the status screen MENU_DetailStatus_Base is used differently:
[4..1792, 4..804] -> x 140..3716 and [4..528, 812..1612] -> x 816..1864.

**Trap: BG_S samples a SUBSET of BG_L's texels and lands on the same pixels.**
MENU_Base [4..368, 4..816] is inside [4..1824, 4..816] and both map to
x 100..828. One texture cannot give the two layers different values, so the
design puts the whole wash in MENU_Base and blanks every other panel block; the
capture then answers whether the second draw happens. **It does not** - see
the verification below, where the left half and the right half of the same
painted alpha come back identical. So exactly one of BG_L / BG_S reaches the
frame buffer.

### The blend and the transfer, measured off the deployed build

Predicting the top bar (x 1600..2500, y 10..250) from the vanilla texel, the
scene in `ingame.png` and the four candidate models:

| model | residual R/G/B | rms |
|---|---|---|
| gamma 1.0, straight | +5.25 +5.30 +5.32 | 1.28 |
| gamma 1.0, premultiplied | +4.58 +4.63 +4.66 | 1.13 |
| **gamma 0.8795, straight** | **+0.02 +0.07 +0.10** | **0.87** |
| gamma 0.8795, premultiplied | -0.93 -0.88 -0.85 | 0.96 |

So the menu panel quads blend **STRAIGHT alpha** and the atlas goes through the
same pure gamma as the HUD fill, `screen = 255*(atlas/255)^0.8795`. Every
colour in the script is written in screen space and pushed back through
`to_atlas()`.

**DS3's own dim behind an open menu is engine-side, not a quad.** Over the
strips x 0..98 and x 3742..3840, which no BG quad reaches, `equipment.png` is
0.940 / 0.933 / 0.927 of `ingame.png` with an intercept of about +1, and the
laplacian std is unchanged (23.21 -> 23.45). DS3 dims ~6% and does not blur.
That is the whole of it and it is out of reach from a texture.

### What was painted

| target | value |
|---|---|
| frame veil `A_BG` | 0.50 at P = (27,26,21) |
| grid column `A_COL` | 0.76 = 1 - (1-0.50)(1-0.52), i.e. ER's own wash over the veil |
| P in atlas units | (20, 19, 15) |
| gold in atlas units | (134, 130, 98) |
| column rect | 4K x 100..1420 (the BG_S quad), y 415..1892, 45 px side feather, 24 px top ramp |
| column top hairline | y 415, sigma 3.3, peak 0.22 |
| column divider | x 2650 (DS3's own status-column edge), sigma 3.3, peak 0.66 |
| title haze | gold, y 30/46..128/230, alpha 0.28 at x0 -> 0.17 at x900 -> 0 at x1500 |

Blanked outright: MENU_BaseDeco (it is only the filigree), MENU_BaseU both
blocks, MENU_DetailStatus_Base [4..1792, 4..804], MENU_DetailStatus_Base2
[4..1192, 4..804], MENU_InventoryBase [4..624, 24..696] (the grid panel and its
gold corners; the tab icons at rows 704..996, the 2x2 selection frame at
[268..468, 904..1010] and the scrollbar at [632..660, 4..528] are left for
phase B), MENU_OptionBase [1444..1740, 4..816].

`MENU_L_Title` is **not** the title underline. Scanning all 104 `/menu/*.gfx`
in the archive for the string, the ONLY movie that names it is
`/menu/03_000_shoptop.gfx`: it is the shop screen's title panel (a 848x96 dark
strip, RGB 17, alpha 185). It keeps its soft edges and gets the veil's colour
and level, and it cannot be verified in this harness.

### Verified on screen (run 1, native 4K, DS3SHOT_MOD=1)

The scene reference failed this run - `ingame.png` and `equipment.png` do not
share a camera (correlation 0.70 on the strip outside every quad, and the
control fit that should return a = 0.065 returns 0.42), so the alphas were read
off the wash's own edges instead, which needs no scene at all: across a 45 px
feather the scene is constant, so two points on the ramp give both S and a.

| what | measured | authored |
|---|---|---|
| column, x 148 (inside the x100..828 half) | a 0.754 | 0.76 |
| column, x 1352..1370 (the x828..1420 half) | same value, 33 | 0.76 |
| frame veil, from the y260..268 gap | a 0.50 (0.43 above the gap, 0.57 below) | 0.50 |
| column divider | peak 99 over 39 | ER: 103 over 40 |
| column top hairline | 61 over 42 | ER: 47 over 20 |
| title haze plateau | 52 over 37 | ER: 32 over 14 (+15 vs ER's +18) |
| column / background mean ratio | 0.752 | ER: 0.773 |

The two column halves reading identically is the proof that BG_L and BG_S do
not both land. Captures kept in the session scratchpad as
`wash_run1_{ingame,equipment,inventory}.png`.

### What a texture could not do, for phase C

1. **The blur.** ER's frame is blurred; nothing in a texture can do it. A
   BLURFILTER on the BG placement, or a full-screen quad with a MULTIPLY blend
   mode for the grade, are the only Scaleform routes.
2. **The warm grade.** A veil at ER's own wash colour only partly warms a cold
   scene: over the sandbox's blue-grey Cemetery of Ash the frame comes back at
   R:G:B 0.93:1.00:0.98 against ER's 1.00:0.99:0.81. Pushing further would mean
   inventing a saturated colour ER does not use. A cxform cannot fix it either
   - it multiplies the SOURCE, not the scene behind - so this needs a
   multiply-blended full-screen quad.
3. **The 100 px strips at x < 100 and x > 3740** are outside every BG quad and
   stay at the engine's own 6% dim. Growing shape 28's bounds from +/-910 to
   +/-960 stage px (the `--fill-rim` trick) closes them.
4. **The 8 px gaps at y 260..268 and y 1892..1900**, between the top bar and
   the main quad and between the main quad and the bottom bar, are uncovered
   and read as bright seams (50 against the frame's 35). Growing the bar quads
   4 stage px each closes them. They are less visible than before, because the
   panels either side used to be near-black.
5. **The status screen's second panel** (MENU_DetailStatus_Base
   [4..528, 812..1612] -> x 816..1864) is left alone: those same texel rows
   812..924 are the 4-texel section rules that five other movies draw, and the
   harness cannot capture the status screen to check either decision.
6. The equipment-slot diamond and the slot cell chrome in
   MENU_OptionBase rows 964..1116 are untouched and still read as DS3.

### Before and after, the same regions

Background = y 400..2100, x 1500..2800; column = y 600..1800, x 250..1300.
Both boxes contain the screens' own text and grid art, so they measure the
whole look rather than the wash alone.

| | background mean / median | column mean / median | column / background |
|---|---|---|---|
| DS3 before | 34,32,35 / 25.7 | 45,43,43 / 40.7 | 1.295 |
| DS3 after (run 1) | 49,51,49 / 42.7 | 48,47,44 / 42.7 | 0.936 |
| Elden Ring | 54,54,45 / 45.3 | 43,41,35 / 36.7 | 0.773 |

The background lands on ER's level. The column still reads bright because
DS3's grid CELLS are untouched here - on clean strips with no cell art the
wash itself measures 0.752 against ER's 0.773. Closing the rest is phase B's
grid-cell work, not more wash.

## Phase B: cells, highlight, rules, tabs

Done 3 Sep. One script, `tools/souls-extract/er_menu_cells.py`, five textures,
no movie edits:

```bash
V=data/ds3-ui-port/.venv/bin/python; B=data/ds3-ui-port/build
$V tools/souls-extract/er_menu_cells.py $B/01_common_final.tpf.dcx $B/01_common_cells.tpf.dcx
$V tools/souls-extract/er_menu_cells.py $B/01_common_final.tpf.dcx $B/01_common_cells_probe.tpf.dcx --probe
```
`--probe` floods every edited region with a flat tracer colour; one capture then
gives the effective alpha of each layer. It is a measurement rig, not a build.

### What the movies actually draw (fe_tree.py, not the atlas layout)

| region | what | placement alpha |
|---|---|---|
| `MENU_ItemParts[4..180, 304..480]` | `Cursor` (sprite 279 depth 19). THE selection, and the same quad on every other cell at a low alpha | ~0.61 selected, ~0.033 not |
| `MENU_ItemParts[516..692, 4..180]` | `Selected` / `CursorLock` (depth 3/5), per cell | ~0.018 |
| `MENU_ItemParts[460..508, 164..212]` | `inadequacy`, the red X | none |
| `MENU_ItemParts` 84x96 / 96x100 tiles | the stone and leather tab tiles | none |
| `MENU_ItemParts` 3 x 80x32 | the drop shadow under a tab | none |
| `MENU_InventoryBase[268..364, 904..1010]` | cell gradient A | 115/256 |
| `MENU_InventoryBase[372..468, 904..1010]` | cell gradient B | 15/256 |
| `MENU_InventoryBase[525..755, 690..940]` | a 2x2 lattice tile placed at +/-50, +/-55 stage px, i.e. HALF a cell, so its dark cross lands on the cell boundaries | 26/256 |
| `MENU_InventoryBase` 16 x 80x92 + `MENU_ItemTab_Edge` 32 x 80x92 | the tab icons, both sets under `BackTabList` | rgbMult 179/256 |
| `MENU_EquipSlot` 14 x 160x160 | the engraved empty-slot plates | none |
| `MENU_AttributeIcon` 16 x 30x30 | damage-type badges: the Attack Power / Guarded Damage rows AND the inventory cell corner | none |

**The tracer run killed the plan for three of these.** In the Equipment and
Inventory screens the game draws only the `Cursor` quad and, in the inventory,
the same quad faintly on every cell. Gradients A and B and the 2x2 lattice are
**not drawn at all** on either screen: a magenta flood of the cursor covered the
whole grid, a red flood of gradient A and a green flood of the lattice showed
nothing but one small bar at the bottom right. So DS3's "engraved cells with
light grid lines" come from the cursor quad's own ring art plus the panel
behind, not from the lattice. Their art is authored to ER anyway, for wherever
they do draw, but nothing here depends on them.

### Elden Ring, measured at 4K

Every lift is against the panel at the SAME screen row, so the panel's own wash
cancels (the equipment panel drifts 25 -> 44 down a single row, which is bigger
than everything being measured).

| | ER | DS3 before | DS3 after (run 4) |
|---|---|---|---|
| grid pitch | 210.35 x 247 | 200 x 220 | unchanged, movie job |
| ordinary cell | no plate: 0 lift over the top half, +9.5/+10/+8 at 85% of the height, 0 by 98%; the same over a panel of 25 and one of 37, i.e. an add | engraved plate, light grid lines at 10% alpha | ~+4 rim, no plate, no grid lines |
| row boundary | a full-width rule ACROSS the gutters, +22/+22/+18, ~10 px, tapering to +4 at the grid's ends | a ~25 px engraved band, +10 | none (see below) |
| column gutter | about -1.5 | -8 engraved | none |
| selection | a soft warm RIM, not a fill: peak +54 18 px inside the edge, +16 at the centre. Cut at y1490..1500 over a panel of 39: 39 47 74 92 93 87 81 78 74 71 69 65 62 60 58 56 55 | a solid orange box, (164,87,20) | 21 23 46 68 76 72 65 62 60 57 56 55 53 53 50 45 43 over a panel of 21; lift peak 54 against ER's 54, mean abs error 5.9 over the 16 samples, interior 22 against 16 |
| red X | 43x36 px, median (152,33,27), core to 190 | 40x40, orange-red | authored flat (176,34,28); the harness has no unusable item so it is UNVERIFIED on screen |
| tab tile | none at all | stone / leather tiles + a drop shadow | gone, (28,28,28) where it was |
| tab icon ink | (103,94,72), the SAME on the active tab as on the others | (101,96,106), a cool stone relief | (100,92,72) |
| active tab | a chevron under it plus a soft glow | a leather tile | chevron + glow, in the leather tile's region |
| empty-slot ghost | ink +13 over the cell floor (pause menu Pouch) | plate lifts the panel 52 vs 29, ghost +36 | plate gone (median 29), ghost +15 |
| stat-row icons | none on plain rows | one per row | unchanged: NOT MENU_AttributeIcon, see below |

### The three alphaMult chains that decide the levels

* `sprite 165 Item_0_0..4` (the tab strip) carries **rgbMult 179/256 = 0.699**
  on the whole tab, icon included. Authoring TAB_INK at (147,134,103) to land
  on ER's (103,94,72) measured (83,75,60); the icon's own alpha eats another
  0.80, so TAB_INK carries a measured x1.24.
* the `Cursor` placement's own alpha is **0.61**, derived from run 3 without
  assuming the panel (authored 0.525 rendered a lift of 72 over a panel of 25
  with C = 250). `SEL_ENGINE_ALPHA = 0.716` is what makes the authored ER lift
  come out as the rendered ER lift. Cross-checked: DS3's stock orange renders
  at the same effective alpha, so it is not a fade phase.
* the grid layers carry 115 / 15 / 26 of 256 and the scroll track 128/102/102/77.
  None of them matter, because none of them are drawn (above).

**The blend is STRAIGHT here**, `out = e*C + (1-e)*S`. Not inherited: DS3's own
2x2 lattice is opaque white (RGB 245, A 255) and renders as faint lines, which
premultiplied could not do. Every level was still confirmed by capture, and the
first attempt was 4x low, which is what the probe run was for.

### What needs a movie edit (phase C)

1. **The ordinary cell field and the row rules.** One texture cannot serve both
   states: DS3 draws the cursor quad at 0.61 selected and 0.033 unselected, a
   ratio of 18, where ER's selected-to-ordinary ratio is 5.7. Authored for the
   selection, the ordinary cell comes out at about +4 instead of ER's +9.5. The
   fix is in the movie: raise the unselected `Cursor` alpha (sprite 279 depth 19
   in 02_020_inventory), or give the cell its own quad. ER's full-width row rule
   has no quad at all in DS3 that spans the gutters, so it needs a new placement
   or the 2x2 lattice re-enabled.
2. **The grid pitch**, 200x220 against ER's 210.35x247.
3. **The per-row stat icons are NOT ours.** The Vigor / Attunement / Physical /
   Magic rows draw `MENU_DummyIcon_0xxxx`, separate textures the engine fills
   in; only `MENU_DummyBase` is in `01_common`, so those icons live in another
   archive. `MENU_AttributeIcon` is a different thing (the 16 damage-type
   badges) and blanking it removes nothing from a stat row; it removes the
   badge in the inventory cell corner, which ER also does not have.
4. **The per-row gold rules under every stat line are phase A's**:
   `MENU_Base[4..572, 976..980]`, `MENU_Base[4..508, 964..968]` and
   `MENU_DetailStatus_Base[4..428, 812..816]`. Nothing in `MENU_ItemParts`
   draws a stat-row rule; its only thin quads are the scroll track.
5. **ER's own tab art was not used.** `extract/er/png/SB_Tab.png` has the icons,
   but DS3 has 32 tab slots over two icon sets against ER's five tabs and there
   is no mapping that keeps each tab meaning what it says. The icons were
   re-inked to ER's bone instead, which is where the whole visible difference
   was (hue and the tile behind them).

### Files

| file | what |
|---|---|
| `build/01_common_cells.tpf.dcx` | the build, from `01_common_final.tpf.dcx` |
| `build/01_common_cells_probe.tpf.dcx` | the tracer rig (`--probe`) |
| `build/cells_inventory_4k.png`, `build/cells_equipment_4k.png` | run 4 on screen at 4K |

Nothing is left deployed; the sandbox is back on `01_common_final.tpf.dcx`.

### Status screen (3 Sep afternoon, follow-up to Phase A)

Donnie: "status is still using the Dark Souls background". `02_070_status`
draws quads the Equipment pass never met, all now blanked in
`er_menu_wash.py`: MENU_BaseU [4..1792, 4..804] (shape 44, the LeftPane's
leather; only the [4..342] strip had been blanked) and [4..528, 812..1612]
(BG_S), MENU_Base [1160..1680, 1780..2044] (Status_page2's black blob),
MENU_StatusCharaNoise [4..572, 4..780] (the black box behind the character
preview), and the per-row rule strips MENU_Base rows 964..968 / 976..980 /
988..992 and MENU_DetailStatus_Base rows 812..816 / 860..864, which the
Equipment stat rows draw too (ER has no per-row rules). Verified at 4K with
`DS3SHOT_STATUS=1` (a `status` shot after Inventory: q, Right, e; then q,
Right, Right to reach System for the clean quit): the Status screen is three
text columns on the veil, and Equipment lost its row rules with no other
change. Left as is: the BG_L grid wash lands under the Status screen's left
pane (ER has no wash there), and Phase A's two bright seams at y 260..268 and
1892..1900.

### Phase D follow-ups (3 Sep afternoon)

Alignment: ER's tile frame is 137x141 at 4K, which is the 142x146
SB_In_GameTop cell at 1:1 minus its transparent rim; the strips had been
drawn at 0.94 (fitted on icon ink) and clipped the frame. TILE_DRAW 1.0 and
TILE_CX 46.5 put rows at 816..958 / 1200..1341, x 107..245 against ER's
817..958 / 1201..1342, x 107..244. TILE_Y0 stays -388.5 (a row polluted by
icon ink had read 8.5 px low; the clean rows were right).

Navigation, DEAD END: the engine addresses the pause list as
`Item_<list>_<index>` with fixed meaning, list 0 the menu tiles, list 1 the
toolbelt; Left/Right moves the index, Up/Down switches list. Renaming the
tiles to five rows (`--grid-rename`, kept as the record) made Down enter the
toolbelt list and light the tile now named Item_1_0 (the engine's own label
read "Toolbelt", prompts Close/Switch, seen with `--show-label` and
`DS3SHOT_PAUSE=downsweep`). The vertical list therefore navigates with
Left/Right, or the strips go back in a row.

### The navigation fix, in the input layer (3 Sep afternoon)

UPDATE 17:05: the memory route below is a DEAD END and the watcher now
reads the SCREEN. Eight scans (2..8) showed the flag bytes live in
pointer-heavy, zero-padded objects: no two-hop chain from the exe's static
data recurred across launches (runs 2, 3, 4 gave 8, 5 and 235 chains with
no overlap), no vtable pointer sits within 16 KB before any flag, and 128
byte neighbourhoods matched across runs only on zeros. So
`tools/ds3-menu-watch --screen` finds the game window (WM_CLASS DarkSoulsIII
or a gamescope window), grabs three small regions of its pixmap through
the compositor (the same XGetImage route pause-snap uses, 0.3 ms each, 30 Hz)
at 4K coordinates scaled by the window width, and raises the flag when the
first tile's gold frame edges AND the bone "Equipment" label are there.
Sandbox test at 1080p: bar up reads left edge 0.29..0.42, top 0.24, label
367; closed reads 0/0/0; inside Inventory the edges read 0 while the title
text lands in the label box, which is why both are required. Thresholds
0.15 and 120*scale^2. `tools/ds3-modded-launch` runs the game under it
(`DS3_NO_MENU_WATCH=1` opts out); `--screen-probe` prints the readings.
The memory scanner and its findings are kept below as the record.

The movie cannot do it, so the pad does: `couchd/inputproc.py` turns
ABS_HAT0Y into ABS_HAT0X (Up -> Left, Down -> Right, HAT0X untouched) while
`/tmp/couch-dpad-rotate` exists (`rotate_dpad`, pure, tested; the file is
checked at most every 50 ms). `tools/ds3-menu-watch` holds that file while
the game's "top menu bar open" byte reads 1, polling /proc/<pid>/mem at
30 Hz through a pointer chain; `tools/ds3-modded-launch` runs the game
under the watcher so it is the game's ancestor, which is what
yama ptrace_scope 1 allows without sudo (the watcher makes itself a child
subreaper because Proton and ModEngine2 re-exec and orphan).

The chain came from `tools/ds3-menuflag-scan`, a differential scan of the
sandbox game's writable memory across closed / open / closed / open /
open+Right / closed / Equipment / bar-again (784 bytes survive the first
six states, 71 read "closed" inside Equipment, i.e. top-bar-only), then a
hunt for pointers in the exe's data that reach those bytes in one or two
hops. One static root, `DarkSoulsIII.exe+0x465c330`, reaches the same byte
six ways; `data/ds3-shot/menuflag.json` keeps `+0x1688 -> +0x8d0`, open=1.
The scanner also runs the game as its own descendant (subreaper) so the
experiment needed no sysctl.
