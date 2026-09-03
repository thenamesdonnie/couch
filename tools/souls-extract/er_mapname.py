#!/usr/bin/env python3
"""Restyle DS3's AREA NAME title card underline as Elden Ring's rule.

WHAT DRAWS IT (read out of 01_000_fe.gfx with fe_tree.py, never guessed):

  sprite 0 depth 475 name='MapName' at stage (960, 488)
    sprite 520          121 frames, animates depth 1's alphaMult - the fade
      sprite 519        78 frames, ONE PER LANGUAGE (frame labels jpnJP,
                        fraFR, ..., engUS at frame 42). Each language frame
                        re-places the TEXT sprite at its own y; the underline
                        is placed once at frame 0 and persists.
        sprite 516 at (0, 64)     -> shape 515, the underline quad
        sprite 518 at (0, -43)    -> text 517 (see below; -43 is what engUS
                                     inherits, from the fraFR frame)

  shape 515  bounds (-600,-4)..(600,4) stage px, filled from
             MENU_MapName_Underline, declared 2048x16, UV [4..1204, 4..12],
             1 texel per stage px.
  text 517   MenuFont_02, fontHeight 1800 twips = 90 stage px em, align 2
             (centre), white, with a DROPSHADOWFILTER on its placement.

So on screen at 4K (one stage px = two 4K px) the underline quad is
x 720..3120, y 1096..1112 - a 2400x16 strip centred on the screen, and the
whole card is one quad plus one centred text field. There is no band quad and
nothing else to work with, which is fine, because ER has no band either.

ELDEN RING'S CARD, measured on er-reference/burst/area-name-banner.png
("Stormveil Castle", native 4K). It is NOT a dark band with rules above and
below. It is white serif text and ONE tapered rule beneath it, nothing else:

  * text   pure white (254,254,254); baseline y=1130, the 'S' apex at 1013, so
           a cap height of 117 px (the row-1003 top an earlier pass quoted is
           the 't'/'l' ASCENDER, and sizing to it made ours 18% too big);
           x 1352..2487, centre 1919.5 = screen centre; stem 15 px.
  * rule   a soft glow 26 px below the text baseline, straight colour
           C = (138,139,113), a warm bone, the same family as ER's gold
           brackets (161,148,112). Alpha per column is the least-squares
           `sum((out-S)(C-S)) / sum((C-S)^2)` with S from rows +/-14, MEDIAN
           over the full-strength columns - the plain regression of out on S
           carries a 0.3 pedestal on a busy scene, which is bigger than the
           thing being measured, while the median estimator reads 0.00 on rows
           outside the rule. The resulting profile, curve_fit to a Gaussian:
           amplitude 0.554, centre y 1156.37, sigma 2.98 (FWHM 7.0 px).
           Row by row: 1150 .046, 1152 .174, 1154 .438, 1156 .544, 1158 .484,
           1160 .272, 1162 .078.
           Horizontal: full strength across the middle, fading to nothing by
           x 1120 / 2720. Left and right fades measure differently (the left
           runs ~530 px, the right ~200 px), which is a capture artefact more
           than a design - averaging the two about screen centre gives
           1.0 out to |dx| 550 then a near-linear ramp to 0 at |dx| 850, and
           that symmetric fit is what is painted.
  * NOT THERE: any dark band behind the text, and any second rule above it.
           Checked by fitting the same alpha model on rows 900..1010 and on
           the smooth wall left of the card: the residual is the regression's
           own bias (~0.12 everywhere, including rows well outside the card).

RESOLUTION. Same trick as the bars and the slot panel: ship the texture at 2x
(4096x32 BGRA) so that, with the SWF still declaring 2048x16, one texel is one
4K pixel across the quad. At 1x the 16-row-tall quad would only get 8 texels
and ER's 12 px gradient would come out in 2 px steps. In the 2x texture the
quad is source x 8..2408, y 8..24, and with er_fe_gfx.py --er-mapname applied
4K x = 720 + (sx - 8), 4K y = 1148 + (sy - 8). Verified exactly by the tracer.

ALPHA: THIS QUAD IS **STRAIGHT**, NOT PREMULTIPLIED. The souls counter proved
its own panel premultiplied, and the port has premultiplied everything
translucent since. Run 8 says this quad is not. Authored premultiplied, ER's
0.563-peak rule came back with a measured peak of 0.178 (against ER's own 0.544
measured identically), a visibly narrower profile, and NEGATIVE lobes either
side - the texel DARKENING the scene where its alpha is low. Only one model
does that: `out = a*RGB + (1-a)*S` applied to an RGB that was already `a*C`,
i.e. `a^2*C - a*S`, which goes negative wherever `a*C < S`. Row for row, as the
estimator reports alpha (scene S ~ 45, C ~ 138):

    row                 1150   1152   1154   1155   1157   1159   1161
    authored a          .152   .331   .511   .557   .511   .331   .152
    if premultiplied    .152   .331   .511   .557   .511   .331   .152
    if straight        -.039   .003   .140   .191   .140   .003  -.039
    MEASURED           -.040  -.033   .113   .178   .121  -.042  -.076

So the RGB written here is ER's straight colour and the alpha is ER's alpha.
premultiply() is kept, unused by default, because the next translucent element
may well be premultiplied again: MEASURE it, do not inherit the assumption.

    python er_mapname.py <in.tpf.dcx> <out.tpf.dcx> [--tracer] [--preview dir]

--tracer paints the quad opaque white with coloured end markers instead of the
rule. It is the geometry probe: it proves the card is on screen at all and
pins the quad's real extent, which is what run 1 was for.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

TEXNAME = "MENU_MapName_Underline"
DECLARED = (2048, 16)      # what the SWF's DefineExternalImage2 says
SCALE = 2                  # ship at 2x -> one texel per 4K pixel

# the quad, in DECLARED texels (fe_tree: uv=[4..1204, 4..12], 1 texel/stage px)
QUAD_U = (4, 1204)
QUAD_V = (4, 12)
# Where those texels land at 4K. x is unaffected by anything er_fe_gfx.py does;
# y is the quad top AFTER --er-mapname has moved the card. Both were confirmed
# by the run-6 tracer, which put the 40 red columns at 720..759, the 40 blue at
# 3080..3119, the two green rows at 1148..1149 and the bar at 1150..1163.
QUAD_X0_4K = 720           # stage 360 = 960 - 600
QUAD_TOP_4K = 1148         # stage 574 = 488 + 34.22 (drop) + 64 - 8.22 - 4

# ER's rule, all at 4K px. Gaussian parameters are a curve_fit to the alpha
# profile of ER's own frame (A 0.554, centre 1156.37, sigma 2.98) rather than
# the eyeballed 3.4 an earlier pass used.
RULE_COLOUR = np.array([138.0, 139.0, 113.0])   # straight, warm bone
ER_ALPHA = 0.554                                # peak, ER's fitted amplitude
ER_SIGMA = 2.98                                 # ER's fitted sigma, FWHM 7.0 px
ER_CENTRE_4K = 1156.37                          # ER's fitted centre row
RULE_FLAT = 550.0                               # full strength to |dx| this far
RULE_END = 850.0                                # zero by here (1700 px total)

# WHAT THE ENGINE DOES TO AN AUTHORED ALPHA RAMP, measured (run 9). Authoring
# A 0.557 / centre 1155.50 / sigma 3.40 rendered as A 0.673 / centre 1155.66 /
# sigma 3.25 (curve_fit on both, same estimator). So the shape survives - the
# centre moves 0.16 px and sigma shrinks 4% - but the AMPLITUDE comes out 1.21x
# what was written. It is not a gamma: a gamma on alpha would change the width,
# and the measured/authored ratio is flat across the whole ramp. Splitting the
# core columns by scene brightness and solving `out = a*C + (1-a)*S` puts the
# gain on the alpha (0.557 -> ~0.72) rather than on the colour (C_eff 127/131/
# 112 against the 138/139/113 written), so the compensation goes on alpha.
RENDER_ALPHA_GAIN = 1.208
RENDER_SIGMA_GAIN = 3.25 / 3.40
RENDER_CENTRE_SHIFT = 0.16                      # 4K px, rendered - authored

RULE_ALPHA = ER_ALPHA / RENDER_ALPHA_GAIN       # 0.459
RULE_SIGMA = ER_SIGMA / RENDER_SIGMA_GAIN       # 3.12


def premultiply(rgba: np.ndarray) -> np.ndarray:
    """Straight -> premultiplied alpha. See er_soul_counter.premultiply."""
    out = rgba.copy()
    out[..., :3] *= out[..., 3:4] / 255.0
    return out


def rule_patch(w: int, h: int) -> np.ndarray:
    """ER's rule as a straight-alpha RGBA patch filling the quad, w x h at 4K.

    The Gaussian is centred on the quad's middle row and then windowed to zero
    over the outer two rows, because the quad is only 16 px tall and a hard
    0.06-alpha edge at its bottom would read as a seam.
    """
    # ER's rule does not sit on the quad's middle row: its fitted centre is 4K
    # y 1156.37 and the quad runs 1148..1163, so the Gaussian is centred on
    # quad row 8.21 (less the 0.16 px the renderer adds).
    cy = ER_CENTRE_4K - QUAD_TOP_4K - RENDER_CENTRE_SHIFT
    y = np.arange(h) - cy
    f = np.exp(-(y ** 2) / (2.0 * RULE_SIGMA ** 2))
    edge = np.clip(np.minimum(np.arange(h), h - 1 - np.arange(h)) / 2.0, 0.0, 1.0)
    f = f * edge

    cx = (w - 1) / 2.0
    dx = np.abs(np.arange(w) - cx)
    g = np.clip((RULE_END - dx) / (RULE_END - RULE_FLAT), 0.0, 1.0)

    alpha = RULE_ALPHA * f[:, None] * g[None, :]
    rgb = np.broadcast_to(RULE_COLOUR, (h, w, 3))
    return np.concatenate([rgb, alpha[..., None] * 255.0], axis=2)


def tracer_patch(w: int, h: int) -> np.ndarray:
    """Opaque white with red/blue ends and a green top rows: the geometry probe."""
    p = np.zeros((h, w, 4), float)
    p[..., :3] = 255.0
    p[..., 3] = 255.0
    p[:, :40, :3] = (255, 0, 0)
    p[:, -40:, :3] = (0, 0, 255)
    p[:2, :, :3] = (0, 255, 0)
    return p


def paint(atlas: np.ndarray, tracer: bool = False) -> np.ndarray:
    """atlas: (32, 4096, 4) float/uint8 RGBA at SCALE, edited and returned."""
    a = atlas.astype(float)
    u0, u1 = (v * SCALE for v in QUAD_U)
    v0, v1 = (v * SCALE for v in QUAD_V)
    w, h = u1 - u0, v1 - v0                     # 2400 x 16, i.e. 4K pixels
    # STRAIGHT, not premultiplied: see the docstring's row-by-row measurement.
    patch = tracer_patch(w, h) if tracer else rule_patch(w, h)
    a[v0:v1, u0:u1] = patch
    return np.clip(a, 0, 255).astype(np.uint8)


def build(tpf_in: Path, tpf_out: Path, tracer: bool = False,
          preview: Path | None = None) -> None:
    from oodle import dcx_decompress, dcx_compress_dflt
    from tpf_png import decode
    from soulstruct.containers import TPF
    from build_glyph_mod import dds_bgra

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    tex = [t for t in tpf.textures if t.stem == TEXNAME][0]
    img = decode(tex.data).convert("RGBA")
    want = (DECLARED[0] * SCALE, DECLARED[1] * SCALE)
    if img.size != want:
        img = img.resize(want, Image.LANCZOS)
    atlas = paint(np.asarray(img).copy(), tracer)
    if preview:
        preview.mkdir(parents=True, exist_ok=True)
        Image.fromarray(atlas, "RGBA").save(preview / f"{TEXNAME}_x{SCALE}.png")
        # what the quad looks like over a mid-grey scene, at 4K, 1:1
        u0, u1 = (v * SCALE for v in QUAD_U)
        v0, v1 = (v * SCALE for v in QUAD_V)
        q = atlas[v0:v1, u0:u1].astype(float)
        scene = np.full(q.shape[:2] + (3,), 45.0)
        al = q[..., 3:4] / 255.0
        comp = q[..., :3] * al + (1.0 - al) * scene
        Image.fromarray(np.clip(comp, 0, 255).astype(np.uint8)).save(
            preview / "rule_over_scene45.png")
    tex.data = dds_bgra(Image.fromarray(atlas, "RGBA"))
    tex.format = 9
    dcx = dcx_compress_dflt(tpf.to_bytes())
    rt = TPF.from_bytes(dcx_decompress(dcx))
    if len(rt.textures) != len(tpf.textures):
        raise SystemExit("texture count changed during repack")
    tpf_out.write_bytes(dcx)
    print(f"wrote {tpf_out} ({len(dcx):,} bytes); {TEXNAME} now "
          f"{atlas.shape[1]}x{atlas.shape[0]} BGRA"
          f"{' (TRACER)' if tracer else ''}")


def main() -> None:
    args = sys.argv[1:]
    tracer = "--tracer" in args
    args = [a for a in args if a != "--tracer"]
    preview = None
    if "--preview" in args:
        i = args.index("--preview")
        preview = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) != 2:
        raise SystemExit(__doc__)
    build(Path(args[0]), Path(args[1]), tracer, preview)


if __name__ == "__main__":
    main()
