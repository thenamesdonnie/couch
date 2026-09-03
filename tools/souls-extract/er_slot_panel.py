#!/usr/bin/env python3
"""Paint Elden Ring's equipment-slot chrome into DS3's slot kit.

WHAT DRAWS A SLOT (fe_tree.py on 01_000_fe.gfx, sprite 257 `ItemPanel`):
each of the four main slots is an `Item` sprite holding, in draw order,
  sprite 131  the PANEL   shape 129, 112x152 stage px, MENU_ItemPanel_02 [4..116, 4..156]
  (Dish       the podium, already removed by er_item_panel.py / --drop-dish)
  ItemIcon    the item art, a 160x160 quad
  sprite 192  two RAILS   shapes 188/190, 112x6 each at y -76 / +76,
                          [4..116, 164..170] and [4..116, 180..186]
  HP_Base/HP  the durability bar (weapons only), shape 219 [4..112, 196..202]
  Flash       the orange selection glow, shape 195 [124..252, 4..172]
The small "next item" previews are sprite 207 (`SubItem_1` on top,
`SubItem_2` behind it with an alphaMult of 205/256): panel shape 199
[4..49, 224..285], 45x61 stage px at 1:1 - it is the DISH and the ICON
inside 207 that carry the 0.4, not the panel - plus its own 45x2 rails
(shapes 202/204 at [60..105, 236..238] and [60..105, 224..226], sitting on
the panel's first and last rows exactly like the big ones). Sprite 207 is
also what `Item_Left_Small` draws, so this art serves that too.

`er_fe_gfx.py --er-slots` scales the whole cross to 0.75 so a slot becomes
168x228 px at 4K against ER's 163x218. THIS script makes the slot look like
ER's: a translucent near-black field with softened edges and one thin gold
rule with a crest at the top and at the bottom. ER's rule sits just outside
the field, and the crest reaches ~10 px into it; DS3's rail quads are only
6 stage px tall, so the rules are painted into the PANEL quad instead (at its
first and last rows) and the rail quads are blanked.

RESOLUTION. The atlas ships at 3x (768x1536, format 9). With the 0.75 sprite
scale that is exactly two texels per 4K pixel, so ER's 4K art is pasted at
2x and the GPU minifies cleanly, instead of the 1.43x-then-0.7x round trip a
2x atlas would give. Everything else in the sheet is LANCZOS-upscaled. The
PREVIEW panel is the one exception: it is drawn at 0.75 * 1.156 so that it
comes out ER's width, which leaves 1.73 texels per 4K pixel there.

MEASURED ON ER (hud_full and five burst frames, 4K):
  * field = a*P + (1-a)*S with a ~0.74, P ~ (11,13,9)
  * rules: 4 px double line, 170 wide, tips at both ends, a crest in the
    middle pointing INTO the slot; gold (161,148,112) family
  * flask slot: top rule y 1827, bottom rule y 2030 (203 apart), x 290..449
  * the previews get the same treatment at their own size: field a ~0.69
    P ~ (7,8,6), a 2 px gold line with a small crest, 94 px apart, in a slot
    78 px wide. See the ER SMALL block below for how each number was got.

    python er_slot_panel.py <in.tpf.dcx> <out.tpf.dcx> [--preview dir]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

ER_REF = Path(__file__).resolve().parents[2] / "data/ds3-ui-port/er-reference/hud_full.png"

SCALE = 3                                   # atlas texels per base texel
PANEL = (4, 4, 116, 156)                    # base texels
RAILS = [(4, 164, 116, 170), (4, 180, 116, 186)]
SMALL = (4, 224, 49, 285)                   # the preview panel, shape 199
# shapes 204 / 202, each a 45x2 quad, blanked with a one-texel margin: the
# quads are only 2 texels tall and the vanilla rail art in the row just past
# each one still carries alpha 69, which the sampler would bleed back in.
SMALL_RAILS = [(60, 223, 105, 227), (60, 235, 105, 239)]
SLOT_SCALE = 0.75                           # er_fe_gfx.SLOT_SCALE
SUB_SCALE = 1.156                           # er_fe_gfx.SUB_SCALE, keep in step

FIELD_RGB = np.array([11.0, 13.0, 9.0])
FIELD_ALPHA = 0.74
EDGE_FEATHER = 5.0                          # 4K px, each side
RULE_INSET = 4                              # run 4: rules at the quad edges were 211 apart, ER's are 203

# ER's flask slot at 4K: rule rows (inclusive) and the columns they span
ER_TOP_RULE = (286, 1820, 456, 1838)        # x0, y0, x1, y1 (exclusive)
ER_BOTTOM_RULE = (286, 2022, 456, 2040)
ER_RULE_GAP = 203                           # rule line to rule line
ER_SLOT_W = 163

# --- ER's SMALL preview slots (3 Sep) -------------------------------------
# ER draws two previews per slot: the next item, and behind it a smaller,
# thinner copy of the one after. Measured on hud_full plus the five burst
# frames that actually have the HUD up (the other twelve are menus or a faded
# HUD and would fit a field against a scene that is not being covered):
#
#   front preview  x 464.5..541.5, gold rules at y 1606/1700 (spell)
#                  and 1936/2030 (flask): 78 px wide, 94 px rule to rule,
#                  98 px of drawn assembly, field a 0.69 P (7,8,6)
#   rear preview   the same art at 0.84 scale (66 px wide, 78 px rule to
#                  rule), its right edge at x 589, and thinner: a 0.54
#                  against the front's 0.69, i.e. 0.78 of it. DS3 already
#                  carries an alphaMult of 205/256 = 0.80 on `SubItem_2`,
#                  so that one needs no help - do not touch the cxform.
#
# The field alpha was fitted the same way as the main slot's, F = a*P+(1-a)*S
# over the six frames, with S taken from the 5 px gap between the main slot
# and the preview. TRAP: the first fit read a = 0.60 because that gap was
# sampled from x 452, which is still inside the MAIN slot's edge feather (it
# runs a full 12 px, x 450..462). Sampling x 458..463 moved the answer to
# 0.69 and moved the main slot's own re-fit onto its known 0.74. The rear's
# alpha needs no scene at all: it is read off the OVERLAP where the front
# field covers it (the front is then the probe, with known a and P), which
# also proved the rear's extent - the overlap fit returns a = 0 on the rows
# where the rear slot is not there.
ER_SMALL_TOP_RULE = (464, 1931, 544, 1943)  # flask preview, gold line at rows 5-6
ER_SMALL_BOT_RULE = (464, 2023, 544, 2035)  # gold line at rows 7-8, crest above
ER_SMALL_TOP_LINE = 5                       # row of the line inside each cut
ER_SMALL_BOT_LINE = 7
ER_SMALL_RULE_GAP = 94                      # line to line, 4K px
SMALL_FIELD_RGB = np.array([7.0, 8.0, 6.0])
SMALL_FIELD_ALPHA = 0.69
# ER's preview field does not have a hard edge anywhere. Measured as alpha,
# with the scene taken from the 5 px gap to the left of the slot (the band on
# the RIGHT is inside the rear preview's own field below y 1953, and using it
# invented a fade-out over the bottom six rows that is not there):
#   across, from the left edge:  0.25 0.37 0.49 0.62 0.62 0.66 ... 0.69
#   down, from the row above the top rule: 0.27 [rule] 0.52 0.60 0.65 0.67
#   up, from the row below the bottom rule: 0.34 [rule] 0.49 0.61 0.65 0.67
# A linear ramp whose 50% point sits ~1.2 px outside the quad fits the
# horizontal one; the vertical is softer still and starts before the rule.
SMALL_EDGE_FEATHER = 5.5
SMALL_EDGE_OVERHANG = 1.5                   # px of the ramp that fall outside the quad
SMALL_END_FEATHER = 5.0
SMALL_END_OVERHANG = 2.0                    # rows of ramp outside the rule lines


def cut_rule(box) -> np.ndarray:
    """A gold rule from the ER grab as straight-alpha RGBA, keyed on gold.

    The scene under the rule is bright fog in hud_full, so a luminance key
    would keep the fog; gold is keyed on R-B instead (fog R-B ~ -2, gold ~49).
    """
    er = np.asarray(Image.open(ER_REF).convert("RGB")).astype(float)
    x0, y0, x1, y1 = box
    p = er[y0:y1, x0:x1]
    goldness = np.clip((p[..., 0] - p[..., 2] - 8.0) / 28.0, 0.0, 1.0)
    return np.concatenate([p, goldness[..., None] * 255.0], axis=2)


def slot_rgba(w: int, h: int) -> np.ndarray:
    """ER's slot at 4K scale: w x h, rules at the top and bottom rows."""
    out = np.zeros((h, w, 4), float)
    # the field between the rules, feathered
    top = cut_rule(ER_TOP_RULE)
    bot = cut_rule(ER_BOTTOM_RULE)
    rh = top.shape[0]
    field_y0 = RULE_INSET + rh - 6          # ER's field starts under the rule line
    field_y1 = h - RULE_INSET - rh + 6
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    fx = np.clip(np.minimum(xx + 0.5, w - xx - 0.5) / EDGE_FEATHER, 0, 1)
    fy = np.clip(np.minimum(yy + 0.5 - field_y0, field_y1 - yy - 0.5) / EDGE_FEATHER, 0, 1)
    fa = fx * fy * FIELD_ALPHA
    out[..., :3] = FIELD_RGB
    out[..., 3] = fa * 255.0
    # composite the rules over the field (straight alpha "over")
    for rule, y in ((top, RULE_INSET), (bot, h - rh - RULE_INSET)):
        composite_rule(out, rule, y)
    return out


def composite_rule(out: np.ndarray, rule: np.ndarray, y: int) -> None:
    """Straight-alpha "over" of a rule cut, centred, into the field at row y.

    ER's rule overhangs its own field by a few px, so a cut wider than the
    quad is trimmed equally from both sides rather than squeezed.
    """
    h, w = out.shape[:2]
    if rule.shape[1] > w:
        c = (rule.shape[1] - w) // 2
        rule = rule[:, c:c + w]
    rh, rw = rule.shape[:2]
    x = (w - rw) // 2
    dst = out[y:y + rh, x:x + rw]
    rule = rule[:dst.shape[0], :dst.shape[1]]
    a_r = rule[..., 3:4] / 255.0
    a_d = dst[..., 3:4] / 255.0
    a_o = a_r + a_d * (1 - a_r)
    rgb = (rule[..., :3] * a_r + dst[..., :3] * a_d * (1 - a_r)) / np.maximum(a_o, 1e-6)
    dst[..., :3] = rgb
    dst[..., 3:4] = a_o * 255.0


def small_slot_rgba(w: int, h: int) -> np.ndarray:
    """ER's PREVIEW slot at 4K: a thin field between two thin gold rules.

    The quad is taller than ER's assembly on purpose. DS3's preview panel
    (shape 199, 45x61 stage px) is a narrower rectangle than ER's preview
    (78x98), so a uniform scale cannot match both. Matching ER's WIDTH costs
    x1.156 and makes the quad 78 x 105.8 at 4K, and the extra 5 px at each
    end is simply left transparent: the drawn slot is then ER's 78 x 98 in
    both axes, with the rules exactly ER's 94 px apart. Scaling to match the
    height instead would have left the slot 7 px narrow with nowhere to put
    the error.
    """
    out = np.zeros((h, w, 4), float)
    top = cut_rule(ER_SMALL_TOP_RULE)
    bot = cut_rule(ER_SMALL_BOT_RULE)
    y_top = int(round((h - ER_SMALL_RULE_GAP) / 2))        # 6 for h = 106
    y_bot = y_top + ER_SMALL_RULE_GAP                      # 100
    # the field: from one row above the top line to one row below the bottom
    # one, which is where ER's own transition rows sit (1935 and 2032)
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    fx = np.clip((np.minimum(xx + 0.5, w - xx - 0.5) + SMALL_EDGE_OVERHANG)
                 / SMALL_EDGE_FEATHER, 0, 1)
    fy = np.clip(np.minimum(yy + 0.5 - (y_top - SMALL_END_OVERHANG),
                            (y_bot + SMALL_END_OVERHANG + 1) - yy - 0.5)
                 / SMALL_END_FEATHER, 0, 1)
    out[..., :3] = SMALL_FIELD_RGB
    out[..., 3] = fx * fy * SMALL_FIELD_ALPHA * 255.0
    composite_rule(out, top, y_top - ER_SMALL_TOP_LINE)
    composite_rule(out, bot, y_bot - ER_SMALL_BOT_LINE)
    return out


def premultiply(rgba: np.ndarray) -> np.ndarray:
    """Scaleform textures are premultiplied (see er_soul_counter.premultiply)."""
    out = rgba.copy()
    out[..., :3] *= out[..., 3:4] / 255.0
    return out


def paint(atlas: np.ndarray) -> np.ndarray:
    a = atlas.astype(float)
    # --- the panel quad: 112x152 base -> at 0.75 it is 168x228 4K px ------
    x0, y0, x1, y1 = (v * SCALE for v in PANEL)
    w4k = int(round((PANEL[2] - PANEL[0]) * 2 * SLOT_SCALE))    # 168
    h4k = int(round((PANEL[3] - PANEL[1]) * 2 * SLOT_SCALE))    # 228
    slot = premultiply(slot_rgba(w4k, h4k))
    img = Image.fromarray(np.clip(slot, 0, 255).astype(np.uint8), "RGBA")
    img = img.resize((x1 - x0, y1 - y0), Image.LANCZOS)         # 2x up, into 336x456 texels
    a[y0:y1, x0:x1] = np.asarray(img).astype(float)
    # --- the rails: gone, the rules live in the panel now -------------------
    for rx0, ry0, rx1, ry1 in RAILS:
        a[ry0 * SCALE:ry1 * SCALE, rx0 * SCALE:rx1 * SCALE] = 0.0
    # --- the small preview panel: ER's field AND ER's thin gold rules ------
    # 45x61 base texels drawn at SLOT_SCALE * SUB_SCALE = 0.867, i.e. 78 x
    # 105.8 px at 4K, so the atlas holds 1.73 texels per screen pixel here
    # (the main panel's 2.00 needs no resampling; this one cannot have both
    # an integer texel ratio and ER's width, and the width was worth more).
    sx0, sy0, sx1, sy1 = (v * SCALE for v in SMALL)
    sw4k = int(round((SMALL[2] - SMALL[0]) * 2 * SLOT_SCALE * SUB_SCALE))   # 78
    sh4k = int(round((SMALL[3] - SMALL[1]) * 2 * SLOT_SCALE * SUB_SCALE))   # 106
    small = premultiply(small_slot_rgba(sw4k, sh4k))
    img = Image.fromarray(np.clip(small, 0, 255).astype(np.uint8), "RGBA")
    a[sy0:sy1, sx0:sx1] = np.asarray(
        img.resize((sx1 - sx0, sy1 - sy0), Image.LANCZOS)).astype(float)
    # --- the small rails: blanked, the rules live in the panel now ---------
    for rx0, ry0, rx1, ry1 in SMALL_RAILS:
        a[ry0 * SCALE:ry1 * SCALE, rx0 * SCALE:rx1 * SCALE] = 0.0
    return np.clip(a, 0, 255).astype(np.uint8)


def build(tpf_in: Path, tpf_out: Path, preview: Path | None = None) -> None:
    from oodle import dcx_decompress, dcx_compress_dflt
    from tpf_png import decode
    from soulstruct.containers import TPF
    from build_glyph_mod import dds_bgra

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    tex = [t for t in tpf.textures if t.stem == "MENU_ItemPanel_02"][0]
    img = decode(tex.data).convert("RGBA")
    target = (256 * SCALE, 512 * SCALE)
    if img.size != target:
        img = img.resize(target, Image.LANCZOS)
    atlas = paint(np.asarray(img).copy())
    if preview:
        preview.mkdir(parents=True, exist_ok=True)
        Image.fromarray(atlas, "RGBA").save(preview / "MENU_ItemPanel_02_x3.png")
        bg = Image.new("RGBA", target, (60, 20, 80, 255))
        bg.alpha_composite(Image.fromarray(atlas, "RGBA"))
        bg.save(preview / "MENU_ItemPanel_02_x3_onbg.png")
    tex.data = dds_bgra(Image.fromarray(atlas, "RGBA"))
    tex.format = 9
    dcx = dcx_compress_dflt(tpf.to_bytes())
    rt = TPF.from_bytes(dcx_decompress(dcx))
    if len(rt.textures) != len(tpf.textures):
        raise SystemExit("texture count changed during repack")
    tpf_out.write_bytes(dcx)
    print(f"wrote {tpf_out} ({len(dcx)} bytes); MENU_ItemPanel_02 now {atlas.shape[1]}x{atlas.shape[0]} BGRA")


def main() -> None:
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
