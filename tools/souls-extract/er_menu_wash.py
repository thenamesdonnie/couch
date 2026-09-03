#!/usr/bin/env python3
"""Repaint DS3's menu panels as Elden Ring's wash (phase A of the menu port).

WHAT ER ACTUALLY DOES, measured at 4K on `er-reference/burst/{equipment-screen,
inventory-key-items,stats-screen}.png`:

  * There is NO panel behind the item-detail column or the character-status
    column. Fitting `out = a*P + (1-a)*S` across those columns' edges returns
    a = 0 to within the estimator's noise: the profile through x1350..1450
    (the gap between the grid and the detail column) and through x1600..1700
    and x3300..3400 agree row for row to about a unit at every y. ER draws
    text straight onto the dimmed frame there, with one vertical hairline.
  * The ONE wash is the item grid's column. Regressing the band just inside
    its edge against the band just outside, over 350 rows on both the left and
    the right edge of two screens:

        edge            a (R/G/B)              P (R/G/B)
        equip right     0.537 0.536 0.496      27.3 25.1 20.5
        equip bottom    0.516 0.553 0.544      30.8 31.4 26.5
        equip left      0.478 0.485 0.431      23.8 22.4 16.1
        inventory right 0.541 0.547 0.510      27.1 25.6 21.0
        inventory botm  0.494 0.540 0.529      27.4 29.1 25.1

    -> a = 0.52, P = (27, 26, 21). It is NOT a black panel: over the dark top
    of the frame (S ~ 17) the wash LIFTS the scene to ~22, and over the bright
    fog at the bottom (S ~ 82) it pulls it down to ~54. Both were checked
    against the capture. Edge feather 45 px at 4K on the sides, ~85 px at the
    bottom, ~20 px at the top where a hairline sits.
  * Everything ER draws in these screens shares one chromaticity,
    R:G:B = 1.00 : 0.99 : 0.81. The wash P, the hairlines and the menu
    background's own average all sit on it, which is what "warm olive" is.
  * HAIRLINES are gold (145,141,110) - the same key-line gold the HUD uses -
    laid down as a Gaussian of sigma 3.3 px at 4K (FWHM 7.8), at three peak
    alphas: 0.22 on the grid wash's top edge (measured 47,47,39 over a
    background of 20,20,17), 0.39 on a section rule (81,82,67 over 41,41,34 in
    the stats screen), 0.66 on the vertical divider left of the character
    status column (110,109,89 over 43,43,35).
  * THE TITLE STRIP IS LIGHT, NOT DARK. The brief expected "a soft dark
    strip"; the capture says a warm HAZE: y 44..190 at 4K, a 12 px top edge
    and a 60 px bottom fade, reading 37,37,28 over a 15,17,13 background at
    x 620..1180 and 51,51,39 at x 0..300, fading to nothing by x ~1400. Solved
    against the same gold that makes the hairlines it is alpha 0.28 at the
    left falling to 0.17 by x900 - and the B channel it predicts (29.4) lands
    on the measured 28, which is what makes the identification trustworthy.
  * ER'S GLOBAL DIM CANNOT BE MEASURED from this reference set: no gameplay
    frame shares the menu frames' scene (equipment/inventory sit over bright
    fog, the pause frames over a dark rock face, correlation 0.005 after
    blurring). What CAN be said is that ER's menu background is not much
    darker than its gameplay: means 48..53 against 27..60 across nine
    gameplay frames. The calm comes from the BLUR, which no texture can do.
    So `A_BG` below is a judgement call, not a measurement, and it is set
    higher than ER's own dim on purpose: halving the scene's contrast is the
    only lever a texture has that does the job a blur does.

HOW DS3 DRAWS ITS MENU FRAME (fe_tree.py over build/menus_xml/02_011_equip.xml,
02_020_inventory.xml, 02_010_equiptop.xml, 02_070_status.xml; identical in all
four). Everything is 1 texel per stage px, i.e. one texel per two 4K pixels:

  MENU_Base            [4..1824, 4..816]   -> 4K x 100..3740  y 268..1892  (BG_L)
  MENU_Base            [4..368,  4..816]   -> 4K x 100..828   y 268..1892  (BG_S)
  MENU_OptionBase      [1444..1740, 4..816]-> 4K x 828..1420  y 268..1892  (BG_S)
  MENU_BaseU           [4..342,  4..804]   -> 4K x 140..816   y 280..1880
  MENU_BaseU           [1368..1658, 812..1612] -> 4K x 816..1396 y 280..1880
  MENU_DetailStatus_Base  [4..1192, 4..804]-> 4K x 1340..3716 y 280..1880
  MENU_DetailStatus_Base2 [4..1192, 4..804]-> the SAME rect, drawn at depth 9
  MENU_InventoryBase   [4..624, 24..696]   -> 4K x 140..1380  y 536..1880
  MENU_Base            [4..1924, 1148..1278] -> 4K x 0..3840 y 0..260    alphaMult 243/256
  MENU_Base            [4..1924, 824..954]   -> 4K x 0..3840 y 1900..2160 alphaMult 243/256

TRAP: BG_S's quad samples MENU_Base texels [4..368, 4..816], which are a
SUBSET of BG_L's [4..1824, 4..816] and land on exactly the same screen pixels.
Whatever is painted there is drawn twice over x 100..828. There is no way to
give the two layers different values from one texture, so the design here puts
the wash in MENU_Base alone, blanks every other panel block, and lets the
capture settle whether the second draw happens: if it does, x 100..828 comes
back darker than x 828..1420 and the two halves of the same painted alpha are
the measurement. (Nothing else changes at x 828: MENU_OptionBase's block is
blanked.)

COLOUR TRANSFORMS found on these placements, all of which thin what is painted:
  * the top and bottom bars carry `alphaMult 243/256 = 0.949`. Compensated
    here by authoring alpha/0.949.
  * BG_PlayerStatus, BG_ItemDetailStatus and the equip screen's BaseU layer
    carry RGB mult 247/256 = 0.965 with add (+2, 0, +4) and alphaMult 256.
    Those three blocks are blanked, so the transform has nothing to act on.
  * nothing else in the BG stack carries one.

THE BLEND, AND THE TRANSFER, measured off the deployed build rather than
assumed (RECIPE: the convention is per element). Predicting the top bar's
1600x2500 x 10..250 window from the vanilla texel, the scene in ingame.png and
the four candidate models:

    gamma 1.0     straight   residual +5.25 +5.30 +5.32   rms 1.28
    gamma 1.0     premult    residual +4.58 +4.63 +4.66   rms 1.13
    gamma 0.8795  straight   residual +0.02 +0.07 +0.10   rms 0.87
    gamma 0.8795  premult    residual -0.93 -0.88 -0.85   rms 0.96

  So these quads blend STRAIGHT alpha and the atlas goes through the same pure
  gamma 0.8795 as the HUD fill: `screen = 255*(atlas/255)^0.8795`. Every colour
  below is written in SCREEN space and pushed back through `to_atlas()`.

  DS3's own dim behind an open menu is engine-side, not a quad: over the strip
  x 0..98 and x 3742..3840, which no BG quad reaches, equipment.png is
  0.940/0.933/0.927 of ingame.png with an intercept of about +1, and the
  laplacian std is unchanged (23.21 -> 23.45), so it dims by ~6% and does not
  blur. That is the whole of DS3's "dim", and it is out of reach from here.

WHAT THIS SCRIPT PAINTS

  A_BG   0.50   the frame veil, everywhere the BG quads reach
  A_COL  0.76   the grid column = ER's 0.52 wash composited over the veil,
                1 - (1-0.50)*(1-0.52), so the column-to-frame contrast is ER's
  P      (27, 26, 21) screen -> (20, 19, 15) atlas
  gold   (145, 141, 110) screen -> (134, 130, 98) atlas

  MENU_Base big block      the veil, the grid column wash with ER's 45 px
                           feather, the column's top hairline, and the vertical
                           divider at DS3's own right-column edge (x 2650)
  MENU_Base top bar        the veil + ER's title haze
  MENU_Base bottom bar     the veil (DS3's dark prompt bar goes)
  MENU_OptionBase block    blanked (the veil covers x 828..1420 from MENU_Base)
  MENU_BaseU both blocks   blanked
  MENU_DetailStatus_Base   [4..1792, 4..804] blanked. Rows 812+ are left alone:
                           they are the 4-texel section rules five other movies
                           draw, and the status screen's second panel, which
                           this harness cannot capture.
  MENU_DetailStatus_Base2  [4..1192, 4..804] blanked ([1200..1876] is
                           02_057_itemdetailtext's own panel, left alone)
  MENU_InventoryBase       [4..624, 24..696] blanked - the grid panel and its
                           gold filigree corners. The tab icons (rows 704..996),
                           the 2x2 selection frame ([268..468, 904..1010]) and
                           the scrollbar ([632..660, 4..528]) are phase B's.
  MENU_BaseDeco            blanked outright: it is only the gold filigree.
  MENU_L_Title             not the title underline. It is the SHOP screen's
                           title panel (/menu/03_000_shoptop.gfx is the only
                           movie in the whole archive that names it, checked by
                           scanning all 104). Given ER's treatment it keeps its
                           soft edges and gets the veil's colour and level.

    python er_menu_wash.py <in.tpf.dcx> <out.tpf.dcx> [--preview dir]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

# ---------------------------------------------------------------- constants
GAMMA = 0.8795                      # screen = 255*(atlas/255)^GAMMA
BAR_ALPHA_MULT = 243 / 256          # the top and bottom bars' cxform

WASH_RGB = np.array([27.0, 26.0, 21.0])     # ER's column wash colour, screen
GOLD_RGB = np.array([145.0, 141.0, 110.0])  # ER's key-line gold, screen

A_BG = 0.50                         # the frame veil (see the note above)
ER_WASH_A = 0.52                    # ER's measured column wash
A_COL = 1.0 - (1.0 - A_BG) * (1.0 - ER_WASH_A)      # 0.76

HAIR_SIGMA = 3.3                    # px at 4K
HAIR_TOP_A = 0.22                   # panel top edge
HAIR_DIV_A = 0.66                   # column divider

# the grid column, in 4K screen px. x is the BG_S quad exactly; y starts under
# DS3's own sub-title row (the item name sits at ~330 and the grid/tab strip
# starts at ~430 in equipment, ~480 in inventory) and runs to the quad's edge.
COL_X0, COL_X1 = 100.0, 1420.0
COL_Y0, COL_Y1 = 415.0, 1892.0
COL_FEATHER = 45.0                  # ER's measured side feather
COL_TOP_RAMP = 24.0

DIVIDER_X = 2650.0                  # DS3's character-status column edge

# ER's title haze
HAZE_Y = (30.0, 46.0, 128.0, 230.0)         # ramp up, hold, fade out
HAZE_X = ((0.0, 0.28), (900.0, 0.17), (1500.0, 0.0))

# texture blocks: (u0, v0, u1, v1) in texels
BASE_BG = (4, 4, 1824, 816)
BASE_TOPBAR = (4, 1148, 1924, 1278)
BASE_BOTBAR = (4, 824, 1924, 954)
OPTION_BLOCK = (1444, 4, 1740, 816)
BASEU_BLOCKS = [(4, 4, 342, 804), (1368, 812, 1658, 1612)]
DETAIL_BLOCK = (4, 4, 1792, 804)
DETAIL2_BLOCK = (4, 4, 1192, 804)
INVENTORY_BLOCK = (4, 24, 624, 696)


def to_atlas(rgb):
    """Screen colour -> the atlas value that renders as it."""
    return 255.0 * np.power(np.clip(np.asarray(rgb, float), 0, 255) / 255.0, 1.0 / GAMMA)


def over(top_a, top_c, bot_a, bot_c):
    """Straight-alpha 'over' of two layers, both in screen colour space."""
    a = top_a + bot_a * (1.0 - top_a)
    c = (top_c * top_a[..., None] + bot_c * (bot_a * (1.0 - top_a))[..., None]) / np.maximum(a, 1e-9)[..., None]
    return a, c


def gauss(d, sigma, peak):
    return peak * np.exp(-0.5 * (d / sigma) ** 2)


def ramp(v, lo, hi):
    return np.clip((v - lo) / (hi - lo), 0.0, 1.0)


def frame_layer(X, Y, with_divider=True):
    """The veil + the grid column wash + the hairlines, at 4K screen coords.

    Returns straight alpha and screen RGB. Everything shares WASH_RGB except
    the hairlines, which are ER's gold laid over the wash.
    """
    fx = np.minimum(ramp(X, COL_X0, COL_X0 + COL_FEATHER),
                    ramp(COL_X1 - X, 0.0, COL_FEATHER))
    fy = np.clip(ramp(Y, COL_Y0, COL_Y0 + COL_TOP_RAMP), 0.0, 1.0) * (Y < COL_Y1)
    a = A_BG + (A_COL - A_BG) * fx * fy
    c = np.broadcast_to(WASH_RGB, a.shape + (3,)).copy()

    # ER's hairline on the wash's top edge, only where the wash is
    ha = gauss(Y - COL_Y0, HAIR_SIGMA, HAIR_TOP_A) * fx
    if with_divider:
        ha = np.maximum(ha, gauss(X - DIVIDER_X, HAIR_SIGMA, HAIR_DIV_A))
    a, c = over(ha, np.broadcast_to(GOLD_RGB, a.shape + (3,)), a, c)
    return a, c


def haze_layer(X, Y):
    """ER's warm title haze, gold at a low alpha, over the top bar."""
    xs = np.array([p[0] for p in HAZE_X])
    ys = np.array([p[1] for p in HAZE_X])
    ax = np.interp(X, xs, ys)
    y0, y1, y2, y3 = HAZE_Y
    ay = np.minimum(ramp(Y, y0, y1), 1.0 - ramp(Y, y2, y3))
    return ax * ay, np.broadcast_to(GOLD_RGB, X.shape + (3,))


def screen_grid(block, x0, y0, px_per_texel=2.0):
    """4K screen coords of each texel centre in a block."""
    u0, v0, u1, v1 = block
    u = np.arange(u0, u1) + 0.5
    v = np.arange(v0, v1) + 0.5
    X = x0 + (u - u0) * px_per_texel
    Y = y0 + (v - v0) * px_per_texel
    return np.meshgrid(X, Y)


def rgba(a, c, alpha_mult=1.0):
    """straight alpha + screen colour -> an atlas RGBA block, uint8-ready."""
    out = np.zeros(a.shape + (4,), float)
    out[..., :3] = to_atlas(c)
    out[..., 3] = np.clip(a / alpha_mult, 0.0, 1.0) * 255.0
    return out


# ------------------------------------------------------------------- paint
def paint_base(atlas):
    a = atlas.astype(float)
    X, Y = screen_grid(BASE_BG, 100.0, 268.0)
    al, c = frame_layer(X, Y)
    u0, v0, u1, v1 = BASE_BG
    a[v0:v1, u0:u1] = rgba(al, c)

    X, Y = screen_grid(BASE_TOPBAR, 0.0, 0.0)
    al, c = frame_layer(X, Y, with_divider=False)
    ha, hc = haze_layer(X, Y)
    al, c = over(ha, hc, al, c)
    u0, v0, u1, v1 = BASE_TOPBAR
    a[v0:v1, u0:u1] = rgba(al, c, BAR_ALPHA_MULT)

    X, Y = screen_grid(BASE_BOTBAR, 0.0, 1900.0)
    al, c = frame_layer(X, Y, with_divider=False)
    u0, v0, u1, v1 = BASE_BOTBAR
    a[v0:v1, u0:u1] = rgba(al, c, BAR_ALPHA_MULT)
    return np.clip(a, 0, 255).astype(np.uint8)


def blank(atlas, *blocks):
    a = atlas.astype(float)
    for u0, v0, u1, v1 in blocks:
        a[v0:v1, u0:u1] = 0.0
    return np.clip(a, 0, 255).astype(np.uint8)


def paint_l_title(atlas):
    """Keep the shop title panel's soft edges, give it the veil's colour/level."""
    a = atlas.astype(float)
    peak = a[..., 3].max()
    if peak > 0:
        a[..., 3] *= A_BG * 255.0 / peak
    a[..., :3] = to_atlas(WASH_RGB)
    return np.clip(a, 0, 255).astype(np.uint8)


# --- The Status screen (3 Sep, Donnie: "status is still using the Dark Souls
# background"). 02_070_status.gfx draws quads the equipment pass never met:
#   MENU_BaseU [4..1792, 4..804]       shape 44, the LeftPane's leather (only the
#                                      [4..342] strip had been blanked)
#   MENU_BaseU [4..528, 812..1612]     shape 46, BG_S
#   MENU_Base  [1160..1680, 1780..2044] shape 125, Status_page2's black blob
#   MENU_StatusCharaNoise [4..572,4..780] shape 128, the black box behind the
#                                      character preview
#   MENU_Base rows 976..980 / 988..992 and MENU_DetailStatus_Base rows
#   812..816 / 860..864: the thin gold rule under every stat row, which the
#   Equipment screen draws too. ER has no per-row rules (only section
#   hairlines), so they go as well.
# ER's Status (stats-screen.png) is three text columns on the dimmed frame,
# nothing else, so every one of these is blanked.
STATUS_BASEU_BLOCKS = [(4, 4, 1792, 804), (4, 812, 528, 1612)]
STATUS_BASE_BLOCKS = [(1160, 1780, 1680, 2044), (4, 976, 572, 980), (4, 988, 572, 992), (4, 964, 508, 968)]
STATUS_DETAIL_RULES = [(4, 812, 428, 816), (4, 860, 572, 864)]
CHARA_NOISE_BLOCK = (4, 4, 572, 780)


PAINTERS = {
    "MENU_Base": lambda t: blank(paint_base(t), *STATUS_BASE_BLOCKS),
    "MENU_OptionBase": lambda t: blank(t, OPTION_BLOCK),
    "MENU_BaseU": lambda t: blank(t, *BASEU_BLOCKS, *STATUS_BASEU_BLOCKS),
    "MENU_DetailStatus_Base": lambda t: blank(t, DETAIL_BLOCK, *STATUS_DETAIL_RULES),
    "MENU_StatusCharaNoise": lambda t: blank(t, CHARA_NOISE_BLOCK),
    "MENU_DetailStatus_Base2": lambda t: blank(t, DETAIL2_BLOCK),
    "MENU_InventoryBase": lambda t: blank(t, INVENTORY_BLOCK),
    "MENU_BaseDeco": lambda t: np.zeros_like(t),
    "MENU_L_Title": paint_l_title,
}


def build(tpf_in, tpf_out, preview=None):
    from oodle import dcx_decompress, dcx_compress_dflt
    from tpf_png import decode
    from soulstruct.containers import TPF
    from build_glyph_mod import dds_bgra

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    done = []
    for tex in tpf.textures:
        fn = PAINTERS.get(tex.stem)
        if fn is None:
            continue
        img = decode(tex.data).convert("RGBA")
        arr = fn(np.asarray(img).copy())
        out = Image.fromarray(arr, "RGBA")
        if preview:
            preview.mkdir(parents=True, exist_ok=True)
            bg = Image.new("RGBA", out.size, (60, 20, 80, 255))
            bg.alpha_composite(out)
            w, h = out.size
            s = min(1.0, 1000 / max(w, h))
            bg.convert("RGB").resize((int(w * s), int(h * s)), Image.LANCZOS).save(
                preview / f"{tex.stem}_onbg.png")
        tex.data = dds_bgra(out)
        tex.format = 9
        done.append(f"{tex.stem} {out.size[0]}x{out.size[1]}")
    missing = set(PAINTERS) - {d.split()[0] for d in done}
    if missing:
        raise SystemExit(f"textures not found in the TPF: {sorted(missing)}")
    dcx = dcx_compress_dflt(tpf.to_bytes())
    rt = TPF.from_bytes(dcx_decompress(dcx))
    if len(rt.textures) != len(tpf.textures):
        raise SystemExit("texture count changed during repack")
    tpf_out.write_bytes(dcx)
    print(f"wrote {tpf_out} ({len(dcx)} bytes)")
    for d in done:
        print("  repainted", d)


def main():
    args = sys.argv[1:]
    preview = None
    if "--preview" in args:
        i = args.index("--preview")
        preview = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) != 2:
        raise SystemExit(__doc__)
    build(Path(args[0]), Path(args[1]), preview)


if __name__ == "__main__":
    main()
