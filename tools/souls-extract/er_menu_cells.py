#!/usr/bin/env python3
"""Restyle DS3's menu grid cells, selection, row chrome and tabs to Elden Ring's.

PHASE B of the menu port (docs/research/ds3-er-menus-survey-20260903.md). Five
textures, no movie edits: the geometry stays DS3's, only the art changes.

    python er_menu_cells.py <in.tpf.dcx> <out.tpf.dcx> [--preview dir] [--probe]

`--probe` is the measurement rig, not part of the build: it floods each edited
region with a flat opaque tracer so one capture gives the EFFECTIVE alpha of
every layer (see PROBE_COLOURS).

WHICH TEXTURE DRAWS WHAT, read out of the movies with fe_tree.py over
build/menus_xml/{02_011_equip,02_020_inventory,02_010_equiptop,02_070_status}.xml
rather than guessed from the atlas layout (the trap that cost the HUD port three
runs). Every region below is a UV rect the movies actually sample:

  MENU_InventoryBase   [268..364, 904..1010]  cell field, gradient A
                       [372..468, 904..1010]  cell field, gradient B
                       [525..755,  690..940]  the 2x2 lattice: a HALF-CELL
                            offset tile (placed at +/-50, +/-55 stage px in
                            sprite 184) whose dark cross therefore falls on the
                            cell boundaries, not through a cell
                       [4..524, 704..996] + [632..712, 604..696]  16 tab icons
  MENU_ItemTab_Edge    32 icons on an 88x100 lattice, uv inset 4 (80x92)
  MENU_ItemParts       [4..180, 304..480]     the ORANGE cell selection glow
                       [460..508, 164..212]   the red X ('inadequacy')
                       tab tiles, 84x96 and 96x100, stone and leather
                       [424..504,224..256] + two more 80x32 drop shadows
  MENU_EquipSlot       14 engraved 160x160 empty-slot plates with a ghost
  MENU_AttributeIcon   16 damage-type badges, 30x30, on the Attack Power /
                            Guarded Damage rows and in the inventory cell corner

NOT ours, found while looking: the per-row gold rules under every stat line are
`MENU_Base[4..572, 976..980]` / `[4..508, 964..968]` and
`MENU_DetailStatus_Base[4..428, 812..816]`, i.e. PHASE A's files. Nothing in
MENU_ItemParts draws a stat-row rule; its only thin quads are the scroll track
([4..132, 488..496] and [4..132, 504..508], drawn ROTATED as verticals).
The Vigor/Attunement/... row icons are `MENU_DummyIcon_0xxxx`, separate textures
the engine fills in, not MENU_AttributeIcon.

THE COLOUR TRANSFORMS ON THE PLACEMENTS (we cannot edit movies, so these scale
whatever we author; all read out of the XML, none of them identity):

  sprite 280 d1   grid gradient A      alphaMult 115/256 = 0.449
  sprite 280 d71  grid gradient B      alphaMult  15/256 = 0.0586
  sprite 280 d141 the 2x2 lattice      alphaMult  26/256 = 0.102
  sprite 302 d1/d61   the same two gradients in the second list layout
  sprite 310 d37..43  scroll track     alphaMult 128 / 102 / 102 / 77
  sprite 165 Item_0_0..4 (BackTabList) rgbMult 179/256 = 0.699, alpha 256
  sprite 321 d1   the grid PANEL       rgbMult 247, add (2,0,4)   <- phase A's
  sprite 0 frames 1..7 and 12..18      the screen fade, 0 -> 219 -> 0; the
                            resting frames carry none, so there is no global dim

The selection glow and the red X carry NO transform, so what is authored is what
is drawn.

MEASURED ON ELDEN RING (4K, er-reference/burst/{equipment-screen,
inventory-key-items,pause-menu-2}.png), each number against the panel at the
SAME screen row so the panel's own wash cancels:

  grid pitch          210.35 x 247 px   (DS3's is 200 x 220: close enough to
                      leave alone, a movie job for phase C)
  ordinary cell       NOT a plate. Zero lift over the top half, rising to
                      +9.5/+10/+8 at 85% of the cell height, back to 0 by 98%.
                      The lift is the same over a panel of 25 and one of 37,
                      i.e. it behaves as an ADD, not as a tint.
  row boundary        a full-width rule ACROSS the gutters, +22/+22/+18 at its
                      centre, ~10 px wide, tapering to +4 at the grid's ends
  column gutter       a shallow darkening, about -1.5
  selection           a soft warm RIM, not a fill: +54 at 18 px inside the
                      cell edge, decaying to +16 at the centre
                      (row cut y1490..1500: 39 47 74 92 93 87 81 ... 55 ... 91 38)
  red X               43 x 36 px, median (152,33,27), core to ~190
  tab strip           no tile behind the icons at all: hairline at the top
                      (peak 80 over 21) and bottom (87 over 31), icons ~100x110
                      with peak ink (103,94,72) - the SAME brightness on the
                      active tab as on the others - and a small gold chevron
                      under the active one
  empty-slot ghost    (pause menu Pouch) ink only +13 over the cell floor

BLEND CONVENTION. Every element here is authored STRAIGHT: out = e*C + (1-e)*S
with e = texel alpha * the placement's alphaMult. That is not inherited from the
HUD work, where the convention turned out to be per element (RECIPE.md): it is
what DS3's own art requires. The 2x2 lattice is opaque white (RGB 245, A 255)
and renders as faint grid lines; premultiplied it would paint 255 over the whole
grid. CONFIRM IT ON THE FIRST CAPTURE ANYWAY - the levels below are one scalar
each (CELL_PEAK_A, RULE_PEAK_A, SEL_PEAK_A, GHOST_A, TAB_INK) precisely so a
capture can retune them without touching the shapes.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

ER_TAB = Path(__file__).resolve().parents[2] / "data/ds3-ui-port/extract/er/png/SB_Tab.png"

# ---------------------------------------------------------------- transforms
CX_GRAD_A = 115 / 256          # sprite 280 depth 1
CX_GRAD_B = 15 / 256           # sprite 280 depth 71
CX_LATTICE = 26 / 256          # sprite 280 depth 141
CX_TAB_RGB = 179 / 256         # sprite 165 Item_0_*, an rgbMult on the whole tab

# The panel these things sit on. ER's grid panel reads 25 (inventory) to 37
# (equipment) at 4K; DS3's is being repainted by phase A. 27 is the value the
# authored levels are solved at; because the authored colours are far from the
# panel the lift is only weakly dependent on it (a panel of 40 instead of 27
# moves the cell lift by 0.7 of a unit).
PANEL = np.array([27.0, 27.0, 22.0])

# ------------------------------------------------------------------ regions
# MENU_InventoryBase (1024x1024)
IB_GRAD_A = (268, 904, 364, 1010)
IB_GRAD_B = (372, 904, 468, 1010)
IB_LATTICE = (525, 690, 755, 940)          # the whole white block
IB_LATTICE_CELL = 100                      # texels between the dark cross lines
# The 16 tab icons, as the EXACT uv rects the movie samples. Not a bounding
# box: the third icon row is only three wide, and x 268..468 of that row is
# where the two cell gradients live. A bounding box re-inked them (caught in
# the preview: the cell field came out at TAB_INK instead of CELL_RGB).
IB_TAB_ICON_UVS = ([(x, y, x + 80, y + 92) for y in (704, 804) for x in (4, 92, 180, 268, 356, 444)]
                   + [(x, 904, x + 80, 996) for x in (4, 92, 180)]
                   + [(632, 604, 712, 696)])
IB_PANEL = (4, 24, 624, 696)               # PHASE A owns this. Never touched.

# MENU_ItemParts (1024x512)
IP_SEL_GLOW = (4, 304, 180, 480)           # the orange square, per cell
IP_RED_X = (460, 164, 508, 212)
IP_TAB_STONE = [(424, 264, 508, 360), (620, 264, 704, 360),
                (620, 368, 704, 464), (412, 368, 508, 468)]
IP_TAB_LEATHER = [(516, 264, 600, 360), (516, 368, 612, 468)]
IP_TAB_SHADOW = [(424, 224, 504, 256), (516, 476, 596, 508), (604, 476, 684, 508)]

# MENU_AttributeIcon (512x32): icons 1..16, icon 0 is never sampled
AI_USED = (30, 0, 510, 32)

# MENU_EquipSlot (1024x512): 14 plates on a 160x160 lattice
ES_TILE = 160
ES_TILES = [(c * 160, r * 160) for r in range(3) for c in range(6)][:14]

# MENU_ItemTab_Edge (528x608): 6 x 6 lattice of 88x100, art inset 4
TE_CELL = (88, 100)
TE_INSET = 4

# ------------------------------------------------------------------- levels
# Each solved from ER's measured lift L as  A = L / (cx * (C - panel)).
CELL_RGB = np.array([200.0, 200.0, 160.0])
CELL_LIFT = np.array([9.5, 10.0, 8.0])          # ER, at 85% of the cell height
CELL_PEAK_H = 0.85                              # where that peak sits
CELL_START_H = 0.45                             # nothing above this
CELL_EDGE_FEATHER = 8                           # texels, left/right

RULE_RGB = np.array([250.0, 248.0, 220.0])
RULE_LIFT = np.array([22.0, 22.0, 18.0])        # ER's row rule at its centre
RULE_SIGMA_PX = 3.0                             # 4K px; 1 lattice texel = 2 px

GUTTER_DARK_A = 0.35                            # texel alpha; RGB 0
GUTTER_HALFWIDTH = 3                            # texels either side of the line

SEL_RGB = np.array([250.0, 244.0, 175.0])
# ER's own cut across its selected cell, y1490..1500 of equipment-screen.png,
# with the panel at 39: the lift as a function of the distance to the nearest
# cell edge, in fractions of the 196 px cell. Interpolated rather than fitted -
# a Gaussian rim plus a flat core came out right at the rim and 10 units short
# across the whole middle third.
SEL_PROFILE_D = np.array([0.000, 0.020, 0.041, 0.071, 0.102, 0.133, 0.163, 0.194,
                          0.224, 0.255, 0.286, 0.316, 0.347, 0.378, 0.408, 0.439,
                          0.469, 0.500])
SEL_PROFILE_LIFT = np.array([0.0, 2.0, 8.0, 35.0, 53.0, 54.0, 48.0, 42.0,
                             39.0, 35.0, 32.0, 30.0, 26.0, 23.0, 21.0, 19.0,
                             17.0, 16.0])
# The engine does not draw the cursor at full alpha. Run 1, the selected EMPTY
# equipment slot (4K x225..422, cut y520..545, no item art in the way): the
# profile came back the right SHAPE in the right place - peak 23 px inside the
# edge against ER's 18 - but at half strength. Solving out = e*C + (1-e)*S for
# the one S that makes the rim and the centre share an e gives S = 28.3 and
# e = 0.52. Run 3, authored through that, then overshot by a third, so the
# number was re-derived from run 3 itself, which needs no assumption about the
# panel: authored alpha 0.525 rendered a lift of 72 over a panel of 25 with
# C = 250, i.e. an effective 0.32, i.e. a placement alpha of 0.61 - and the
# constant that makes `rendered lift == ER's lift` is 0.61*225/191.7 = 0.716.
# (It is not a fade phase: DS3's stock orange renders at the same e, which is
# how it was cross-checked.)
SEL_ENGINE_ALPHA = 0.716

# 147/134/103 * the 179/256 rgbMult should have been ER's (103,94,72); run 1
# measured (83,75,60), so the icon's own alpha eats another 0.80. Scaled by the
# measured 1.24 rather than re-deriving it.
TAB_INK = np.array([147.0, 134.0, 103.0]) * 1.24

GHOST_RGB = np.array([190.0, 184.0, 158.0])
GHOST_LIFT = np.array([13.0, 13.0, 13.0])       # ER's pouch ghost over its cell
GHOST_PANEL = np.array([40.0, 40.0, 34.0])      # the cell a ghost sits in
ES_GHOST_FLOOR_PCT = 55                         # the plate's own level
ES_GHOST_MARGIN = 14                            # texels of bevelled frame to drop

XMARK_RGB = np.array([176.0, 34.0, 28.0])       # ER's red X core
XMARK_SPAN = 0.86                               # of the 48-texel quad -> 41 px
XMARK_STROKE = 0.20                             # of the span -> ~8 px at 4K


def alpha_for(lift, rgb, cx=1.0, panel=PANEL):
    """Texel alpha that lifts the panel by `lift` through a cxform alphaMult."""
    return float(np.mean(lift / (cx * (rgb - panel))))


CELL_PEAK_A = alpha_for(CELL_LIFT, CELL_RGB, CX_GRAD_A)
RULE_PEAK_A = alpha_for(RULE_LIFT, RULE_RGB, CX_LATTICE)
GHOST_A = alpha_for(GHOST_LIFT, GHOST_RGB, panel=GHOST_PANEL)


# ------------------------------------------------------------------ helpers
def put(atlas, box, rgba):
    x0, y0, x1, y1 = box
    atlas[y0:y1, x0:x1] = np.clip(rgba, 0, 255)


def clear(atlas, box):
    put(atlas, box, 0.0)


def solid(w, h, rgb, alpha):
    """h x w x 4 float array, one colour, one alpha field (scalar or h x w)."""
    out = np.zeros((h, w, 4), float)
    out[..., :3] = rgb
    out[..., 3] = np.asarray(alpha) * 255.0
    return out


def feather(n, width):
    """0 at the ends, 1 in the middle, linear over `width` samples."""
    r = np.ones(n)
    if width > 0:
        ramp = np.linspace(0.0, 1.0, width + 2)[1:-1]
        r[:width] = ramp
        r[-width:] = ramp[::-1]
    return r


# --------------------------------------------------------- MENU_InventoryBase
def cell_field(w, h):
    """ER's cell: nothing over the top half, a soft glow along the bottom.

    Vertical profile from the measured lift over the panel at the same row
    (equipment col 4, row y1120..1366): 0 to h=0.49, +2 at .51, +4 at .60,
    +7 at .73, +9.5 at .83, +8 at .88, +4 at .93, 0 at .98.
    """
    y = (np.arange(h) + 0.5) / h
    prof = np.zeros(h)
    rise = (y >= CELL_START_H) & (y <= CELL_PEAK_H)
    prof[rise] = ((y[rise] - CELL_START_H) / (CELL_PEAK_H - CELL_START_H)) ** 1.8
    fall = y > CELL_PEAK_H
    prof[fall] = np.clip(1.0 - (y[fall] - CELL_PEAK_H) / (0.98 - CELL_PEAK_H), 0, 1)
    a = CELL_PEAK_A * prof[:, None] * feather(w, CELL_EDGE_FEATHER)[None, :]
    return solid(w, h, CELL_RGB, a)


def lattice(w, h):
    """The half-cell-offset tile: ER's full-width row rule on the horizontal
    lines of the cross, a shallow darkening on the vertical ones, and NOTHING
    where DS3 puts its light grid field (the white interior)."""
    out = np.zeros((h, w, 4), float)
    # the cross sits every IB_LATTICE_CELL texels, offset so it lands where
    # DS3's own dark lines are: measured at x 536, 636, 736 and y 818 in the
    # atlas, i.e. 11 texels in from IB_LATTICE's origin, then every 100.
    off_x, off_y = 11, 128            # 525+11 = 536, 690+128 = 818
    sigma_t = RULE_SIGMA_PX / 2.0     # one lattice texel is two 4K px
    yy = np.arange(h)[:, None]
    xx = np.arange(w)[None, :]
    rule = np.zeros((h, 1))
    for cy in range(off_y % IB_LATTICE_CELL - IB_LATTICE_CELL, h + IB_LATTICE_CELL,
                    IB_LATTICE_CELL):
        rule = np.maximum(rule, np.exp(-0.5 * ((yy - cy) / sigma_t) ** 2))
    gut = np.zeros((1, w))
    for cx in range(off_x % IB_LATTICE_CELL - IB_LATTICE_CELL, w + IB_LATTICE_CELL,
                    IB_LATTICE_CELL):
        gut = np.maximum(gut, np.clip(1.0 - np.abs(xx - cx) / GUTTER_HALFWIDTH, 0, 1))
    # the gutter first (dark, under), then the rule over it
    a_g = GUTTER_DARK_A * gut * np.ones((h, 1))
    a_r = RULE_PEAK_A * rule * np.ones((1, w))
    # one quad, so compose the two into a single colour+alpha
    a = a_g + a_r * (1 - a_g)
    rgb = np.zeros((h, w, 3))
    wr = (a_r * (1 - a_g))[..., None]
    rgb += RULE_RGB * wr
    with np.errstate(invalid="ignore", divide="ignore"):
        rgb = np.where(a[..., None] > 1e-6, rgb / np.maximum(a[..., None], 1e-6), 0.0)
    out[..., :3] = np.clip(rgb, 0, 255)
    out[..., 3] = a * 255.0
    return out


def tone_icon(atlas, box):
    """One tab icon re-inked to ER's warm bone.

    DS3's tab icons are cool stone reliefs (95th-pct ink (101,96,106) on
    screen); ER's are a flat warm bone (103,94,72), the SAME on the active tab
    as on the others. Keep the silhouette and the modelling as luminance, throw
    the hue away, and author TAB_INK so the 179/256 rgbMult lands on ER's.

    ER's own tab art (extract/er/png/SB_Tab.png) was NOT used: DS3 has 32 tab
    slots across two icon sets and ER's inventory has five tabs, so there is no
    mapping that keeps each tab meaning what it says. Re-inking keeps the
    meaning and buys the whole of the visible difference, which is the hue.
    """
    x0, y0, x1, y1 = box
    tile = atlas[y0:y1, x0:x1].astype(float)
    if tile[..., 3].max() < 8:
        return
    lum = tile[..., :3] @ np.array([0.299, 0.587, 0.114])
    peak = np.percentile(lum[tile[..., 3] > 8], 99)
    k = np.clip(lum / max(peak, 1.0), 0, 1)[..., None]
    tile[..., :3] = TAB_INK * k
    atlas[y0:y1, x0:x1] = np.clip(tile, 0, 255)


def paint_inventory_base(atlas):
    a = atlas.astype(float)
    x0, y0, x1, y1 = IB_GRAD_A
    put(a, IB_GRAD_A, cell_field(x1 - x0, y1 - y0))
    clear(a, IB_GRAD_B)                    # ER has one cell layer, not three
    x0, y0, x1, y1 = IB_LATTICE
    put(a, IB_LATTICE, lattice(x1 - x0, y1 - y0))
    for box in IB_TAB_ICON_UVS:
        tone_icon(a, box)
    return a


# ------------------------------------------------------------ MENU_ItemParts
def selection_glow(w, h):
    """ER's selection: a soft luminous rim just inside the cell edge.

    Measured across ER's selected cell at y1490..1500 with the panel at 39:
    39 47 74 92 93 87 81 78 74 71 69 65 62 60 58 56 55 (centre) then the mirror.
    So the peak is 18 px in from a 196 px cell (9%) and the centre keeps a third
    of it. Modelled as f(d) = mid + (rim-mid) * exp(-((d-d0)/s)^2) on the
    distance to the nearest edge, which reproduces that cut within 3 units.
    """
    yy = (np.arange(h)[:, None] + 0.5) / h
    xx = (np.arange(w)[None, :] + 0.5) / w
    d = np.minimum(np.minimum(xx, 1 - xx), np.minimum(yy, 1 - yy))   # 0 at edge
    lift = np.interp(d, SEL_PROFILE_D, SEL_PROFILE_LIFT)
    a = lift / (float(np.mean(SEL_RGB - PANEL)) * SEL_ENGINE_ALPHA)
    return solid(w, h, SEL_RGB, a)


def red_x(w, h):
    """ER's flat red X. Its own is 43x36 at 4K with a ~8 px stroke; this quad is
    48 texels drawn at 40 4K px (48 * 0.4167 stage * 2), so it is authored in
    quad fractions and comes out at ER's proportions."""
    yy = (np.arange(h)[:, None] + 0.5) / h - 0.5
    xx = (np.arange(w)[None, :] + 0.5) / w - 0.5
    r = XMARK_SPAN / 2
    half = XMARK_STROKE * XMARK_SPAN / 2
    inside = (np.abs(xx) <= r) & (np.abs(yy) <= r)
    d1 = np.abs(xx - yy) / np.sqrt(2.0)
    d2 = np.abs(xx + yy) / np.sqrt(2.0)
    d = np.minimum(d1, d2)
    a = np.clip((half - d) / (half * 0.35), 0, 1) * inside
    return solid(w, h, XMARK_RGB, a)


def active_tab_mark(w, h):
    """ER marks the active tab with a warm glow rising from the strip's bottom
    edge plus a small chevron below it, and no tile. Authored into the LEATHER
    tab tile so the shape only appears on the selected tab."""
    yy = (np.arange(h)[:, None] + 0.5) / h
    xx = (np.arange(w)[None, :] + 0.5) / w
    glow = np.exp(-0.5 * ((1.0 - yy) / 0.34) ** 2) * np.exp(-0.5 * ((xx - 0.5) / 0.34) ** 2)
    # the chevron POINTS DOWN (ER's sits under the active tab, apex at the
    # bottom): 50 x 30 px at 4K under a 171 px tab, so ~26% of the tile wide.
    apex, half_w, thick = 0.985, 0.13, 0.028
    rise = np.abs(xx - 0.5) * (0.115 / half_w)
    chev = (np.clip(1.0 - np.abs(yy - (apex - rise)) / thick, 0, 1)
            * (np.abs(xx - 0.5) < half_w))
    a = np.clip(0.34 * glow + 0.85 * chev, 0, 1)
    return solid(w, h, SEL_RGB, a)


def paint_item_parts(atlas):
    a = atlas.astype(float)
    x0, y0, x1, y1 = IP_SEL_GLOW
    put(a, IP_SEL_GLOW, selection_glow(x1 - x0, y1 - y0))
    x0, y0, x1, y1 = IP_RED_X
    put(a, IP_RED_X, red_x(x1 - x0, y1 - y0))
    for box in IP_TAB_STONE + IP_TAB_SHADOW:
        clear(a, box)                      # ER draws no tile and no drop shadow
    for box in IP_TAB_LEATHER:
        x0, y0, x1, y1 = box
        put(a, box, active_tab_mark(x1 - x0, y1 - y0))
    return a


# --------------------------------------------------------- MENU_AttributeIcon
def paint_attribute_icon(atlas):
    """ER shows no icon on a plain stat row - Status, Attack Power,
    Defense/Dmg Negation and Resistance are bare label + value, and only the
    section headers carry a mark. So the 16 badges go, in both places they are
    used: the stat rows and the inventory cell's corner."""
    a = atlas.astype(float)
    clear(a, AI_USED)
    return a


# ------------------------------------------------------------ MENU_EquipSlot
def paint_equip_slot(atlas):
    """Strip the engraved stone plate, keep the ghost at ER's contrast.

    ER's empty slots (pause menu Pouch) are the plain cell with a silhouette
    only +13 above the cell floor. DS3 draws a stone plate with a bevelled
    frame and the ghost on it. The plate is the slow part of the image, so it
    comes off as a large-radius blur; what is left is the silhouette.
    """
    a = atlas.astype(float)
    for tx, ty in ES_TILES:
        tile = a[ty:ty + ES_TILE, tx:tx + ES_TILE]
        if tile.shape[0] != ES_TILE or tile.shape[1] != ES_TILE:
            continue
        lum = tile[..., :3] @ np.array([0.299, 0.587, 0.114])
        cov = tile[..., 3] / 255.0
        # The plate is the LOW half of the tile's histogram and the ghost the
        # high half (measured: tile mean 37.7, ghost peaks 84). A high-pass
        # was tried first and is wrong here - the ghost is a broad smooth
        # shape, so a blur removes the ghost and keeps the plate's grain and
        # bevel, which came back as a bright frame with a dark silhouette.
        base = np.percentile(lum[cov > 0.5], ES_GHOST_FLOOR_PCT) if (cov > 0.5).any() else 0.0
        ink = np.clip(lum - base, 0, None) * cov
        ink[:ES_GHOST_MARGIN] = 0                 # the plate's bevelled frame
        ink[-ES_GHOST_MARGIN:] = 0
        ink[:, :ES_GHOST_MARGIN] = 0
        ink[:, -ES_GHOST_MARGIN:] = 0
        peak = np.percentile(ink, 99.5)
        k = np.clip(ink / max(peak, 1.0), 0, 1)
        out = np.zeros_like(tile)
        out[..., :3] = GHOST_RGB
        out[..., 3] = GHOST_A * k * 255.0
        a[ty:ty + ES_TILE, tx:tx + ES_TILE] = out
    return a


# ------------------------------------------------------------ MENU_ItemTab_Edge
def paint_item_tab_edge(atlas):
    a = atlas.astype(float)
    h, w = a.shape[:2]
    cw, ch = TE_CELL
    for gy in range(0, h - ch + 1, ch):
        for gx in range(0, w - cw + 1, cw):
            tone_icon(a, (gx + TE_INSET, gy + TE_INSET,
                          gx + cw - TE_INSET, gy + ch - TE_INSET))
    return a


# ------------------------------------------------------------------- probe
# --probe floods each edited region with a known opaque colour. One capture
# then gives the EFFECTIVE alpha of every layer directly (out = e*C + (1-e)*S,
# with C known and S read from the untouched channels), which is the only way
# to settle a chain of alphaMults you cannot see the renderer apply. The HUD
# port learned this the hard way: the atlas does not tell you what is drawn.
PROBE_COLOURS = {
    "grad_a": (255, 0, 0),
    "grad_b": (0, 0, 255),
    "lattice": (0, 255, 0),
    "sel": (255, 0, 255),
    "red_x": (0, 255, 255),
    "tab_leather": (255, 255, 0),
}


def probe_inventory_base(atlas):
    a = atlas.astype(float)
    put(a, IB_GRAD_A, solid(IB_GRAD_A[2] - IB_GRAD_A[0], IB_GRAD_A[3] - IB_GRAD_A[1],
                            PROBE_COLOURS["grad_a"], 1.0))
    put(a, IB_GRAD_B, solid(IB_GRAD_B[2] - IB_GRAD_B[0], IB_GRAD_B[3] - IB_GRAD_B[1],
                            PROBE_COLOURS["grad_b"], 1.0))
    put(a, IB_LATTICE, solid(IB_LATTICE[2] - IB_LATTICE[0], IB_LATTICE[3] - IB_LATTICE[1],
                             PROBE_COLOURS["lattice"], 1.0))
    return a


def probe_item_parts(atlas):
    a = atlas.astype(float)
    put(a, IP_SEL_GLOW, solid(IP_SEL_GLOW[2] - IP_SEL_GLOW[0], IP_SEL_GLOW[3] - IP_SEL_GLOW[1],
                              PROBE_COLOURS["sel"], 1.0))
    put(a, IP_RED_X, solid(IP_RED_X[2] - IP_RED_X[0], IP_RED_X[3] - IP_RED_X[1],
                           PROBE_COLOURS["red_x"], 1.0))
    for box in IP_TAB_LEATHER:
        put(a, box, solid(box[2] - box[0], box[3] - box[1], PROBE_COLOURS["tab_leather"], 1.0))
    for box in IP_TAB_STONE + IP_TAB_SHADOW:
        clear(a, box)
    return a


PROBES = {
    "MENU_InventoryBase": probe_inventory_base,
    "MENU_ItemParts": probe_item_parts,
}

PAINTERS = {
    "MENU_InventoryBase": paint_inventory_base,
    "MENU_ItemParts": paint_item_parts,
    "MENU_AttributeIcon": paint_attribute_icon,
    "MENU_EquipSlot": paint_equip_slot,
    "MENU_ItemTab_Edge": paint_item_tab_edge,
}


def build(tpf_in: Path, tpf_out: Path, preview: Path | None = None,
          probe: bool = False) -> None:
    from oodle import dcx_decompress, dcx_compress_dflt
    from tpf_png import decode
    from soulstruct.containers import TPF
    from build_glyph_mod import dds_bgra

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    painters = dict(PAINTERS, **PROBES) if probe else PAINTERS
    done = []
    for tex in tpf.textures:
        fn = painters.get(tex.stem)
        if fn is None:
            continue
        img = decode(tex.data).convert("RGBA")
        out = np.clip(fn(np.asarray(img).copy()), 0, 255).astype(np.uint8)
        tex.data = dds_bgra(Image.fromarray(out, "RGBA"))
        tex.format = 9
        done.append((tex.stem, img.size, out))
        if preview:
            preview.mkdir(parents=True, exist_ok=True)
            Image.fromarray(out, "RGBA").save(preview / f"{tex.stem}.png")
            bg = Image.new("RGBA", img.size, (28, 28, 24, 255))
            bg.alpha_composite(Image.fromarray(out, "RGBA"))
            bg.convert("RGB").save(preview / f"{tex.stem}_onpanel.png")
    missing = set(painters) - {n for n, _, _ in done}
    if missing:
        raise SystemExit(f"textures not in {tpf_in}: {sorted(missing)}")
    dcx = dcx_compress_dflt(tpf.to_bytes())
    rt = TPF.from_bytes(dcx_decompress(dcx))
    if len(rt.textures) != len(tpf.textures):
        raise SystemExit("texture count changed during repack")
    tpf_out.write_bytes(dcx)
    print(f"wrote {tpf_out} ({len(dcx)} bytes)")
    for n, size, _ in done:
        print(f"  {n} {size[0]}x{size[1]} BGRA")
    print(f"  solved levels: cell A={CELL_PEAK_A:.4f} rule A={RULE_PEAK_A:.4f} "
          f"sel rim A={SEL_PROFILE_LIFT.max()/(float(np.mean(SEL_RGB-PANEL))*SEL_ENGINE_ALPHA):.4f} "
          f"ghost A={GHOST_A:.4f}")


def main() -> None:
    args = sys.argv[1:]
    preview = None
    probe = "--probe" in args
    if probe:
        args.remove("--probe")
    if "--preview" in args:
        i = args.index("--preview")
        preview = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) != 2:
        raise SystemExit(__doc__)
    build(Path(args[0]), Path(args[1]), preview, probe)


if __name__ == "__main__":
    main()
