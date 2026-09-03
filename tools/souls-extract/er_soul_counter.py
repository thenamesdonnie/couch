#!/usr/bin/env python3
"""Restyle DS3's souls counter (bottom-right) as Elden Ring's rune counter.

WHAT DRAWS IT. Not the HUD movie. `01_000_fe.gfx` never touches this panel;
the counter is its own movie, `menu/01_001_fe_soul.gfx` (read with
`fe_tree.py`), root sprite `Soul` at stage (1713, 990):

  shape 2  the panel   206x46 stage px, MENU_PlayerHUD [208..254, 38..244] ROTATED:
           screen x (left->right) runs down texture ROWS 38->244, screen y
           (top->bottom) runs down texture COLUMNS 254->208. So the strip that
           looks vertical in the atlas is the horizontal panel, and its top edge
           is the atlas column nearest x=254.
  shape 4  the icon    34x34 at (-80, 0), MENU_PlayerHUD [166..200, 40..74]
  text 9   TotalSoul   right-aligned, 24 px em, (204,204,204), at (+25, 0)
  text 7   GetSoul     the "+N" gain, 34 px above

Both share `01_common.tpf.dcx` with the HUD, which is why a texture edit showed
up on screen while the movie being read never mentioned it. `er_soul_gfx.py`
moves the sprite to ER's spot and sizes the number; this script paints the
texture.

RESOLUTION. Like the bars (MENU_PlayerHUD2), the atlas is shipped at 2x
(512x512, format 9 BGRA): the engine normalises UVs to the declared 256, so a
512 texture lands one texel per 4K pixel with no filtering. Everything ER-side
is painted at 4K scale directly; the untouched remainder is LANCZOS-upscaled.

ER'S PANEL, measured at 4K on hud_full and the burst frames:
  * 402x75 px, x 3341..3742, y 2032..2106 (DS3's is 412x92 at 3220..3632 x
    1934..2026; ER's is painted centred inside DS3's quad, margins transparent)
  * the field is TRANSLUCENT: across six gameplay scenes, field = a*P + (1-a)*S
    fits a ~0.65, P ~ (16,13,10). (Pause-menu frames were excluded: the pause
    vignette darkens the scene under the panel.)
  * gold end brackets (161,148,112), the medallion 45x42 at x 3368, y 2048,
    i.e. its centre 151 px right of the panel's left edge (DS3: 160).

    python er_soul_counter.py <in.tpf.dcx> <out.tpf.dcx> [--preview dir]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

ER_REF = Path(__file__).resolve().parents[2] / "data/ds3-ui-port/er-reference/hud_full.png"

SCALE = 2
# base-texel regions (from fe_tree.py on 01_001_fe_soul.gfx)
STRIP = (208, 38, 254, 244)          # x0, y0, x1, y1 : the rotated panel
ICON = (166, 40, 200, 74)

# ER at 4K
ER_PANEL = (3341, 2032, 3743, 2107)  # x0, y0, x1, y1 (exclusive) -> 402x75
ER_ICON = (3368, 2048, 3413, 2090)   # 45x42
ER_TEXT = (3560, 2042, 3728, 2098)   # the digits in hud_full, blanked
FIELD_RGB = np.array([16.0, 13.0, 10.0])
FIELD_ALPHA = 0.65
FIELD_SCREEN = np.array([13.0, 16.0, 13.0])   # what hud_full shows, for keying


def er_panel_rgba() -> np.ndarray:
    """ER's panel as a straight-alpha RGBA patch, 402x75, from the live grab.

    The field is replaced by the solved translucent colour; anything brighter
    than the field (brackets, the medallion's rim) is taken as-is and made
    opaque in proportion to how far it rises above the field.
    """
    er = np.asarray(Image.open(ER_REF).convert("RGB")).astype(float)
    x0, y0, x1, y1 = ER_PANEL
    p = er[y0:y1, x0:x1]
    lum = p.mean(axis=2)
    rise = np.clip((lum - FIELD_SCREEN.mean()) / 45.0, 0.0, 1.0)      # 0 field .. 1 detail
    rgb = p * rise[..., None] + FIELD_RGB * (1.0 - rise[..., None])
    a = FIELD_ALPHA + (1.0 - FIELD_ALPHA) * rise
    out = np.concatenate([rgb, a[..., None] * 255.0], axis=2)
    # the medallion is drawn by its own sprite; blank it here so it is not
    # painted twice (ER's sits inside the panel; ours is a separate quad)
    ix0, iy0, ix1, iy1 = ER_ICON
    out[iy0 - y0 - 2:iy1 - y0 + 2, ix0 - x0 - 2:ix1 - x0 + 2] = [*FIELD_RGB, FIELD_ALPHA * 255.0]
    # and ER's own rune count ("5247" in hud_full) is text, not chrome
    tx0, ty0, tx1, ty1 = ER_TEXT
    out[ty0 - y0:ty1 - y0, tx0 - x0:tx1 - x0] = [*FIELD_RGB, FIELD_ALPHA * 255.0]
    return out


def er_icon_rgba() -> np.ndarray:
    er = np.asarray(Image.open(ER_REF).convert("RGB")).astype(float)
    x0, y0, x1, y1 = ER_ICON
    p = er[y0:y1, x0:x1]
    lum = p.mean(axis=2)
    a = np.clip((lum - FIELD_SCREEN.mean()) / 30.0, 0.0, 1.0)
    return np.concatenate([p, a[..., None] * 255.0], axis=2)


def premultiply(rgba: np.ndarray) -> np.ndarray:
    """Straight -> premultiplied alpha.

    RUN 3 (2 Sep late): with straight (16,13,10,a=0.65) the field came out as
    16 + 0.35*S, i.e. the engine ADDED our RGB to the attenuated scene instead
    of multiplying it in - Scaleform GFx textures are premultiplied. Measured
    over two scenes (S 71/43 -> 43/35 against a straight-alpha prediction of
    35/26). ER's model a*P + (1-a)*S is reproduced by writing a*P as the RGB.
    """
    out = rgba.copy()
    out[..., :3] *= out[..., 3:4] / 255.0
    return out


def paint(atlas: np.ndarray) -> np.ndarray:
    """atlas: 512x512 RGBA uint8, edited in place and returned."""
    a = atlas.astype(float)

    # --- the panel strip, rotated into texture space ---------------------
    sx0, sy0, sx1, sy1 = (v * SCALE for v in STRIP)
    a[sy0:sy1, sx0:sx1] = 0.0                                   # clear: transparent margins
    panel = premultiply(er_panel_rgba())                        # H=75 (screen y), W=402 (screen x)
    ph, pw = panel.shape[:2]
    # screen x -> texture row (down), screen y -> texture column (UP: top of
    # panel is the column nearest x1). Centre inside the quad.
    rows = sy1 - sy0                                            # 412
    cols = sx1 - sx0                                            # 92
    r0 = sy0 + (rows - pw) // 2
    c1 = sx1 - (cols - ph) // 2                                 # top edge column (exclusive)
    # texture[r, c] = panel[y, x] with r = r0 + x, c = c1 - 1 - y
    block = np.transpose(panel, (1, 0, 2))[:, ::-1, :]          # (x, y_flipped, rgba)
    a[r0:r0 + pw, c1 - ph:c1] = block

    # --- the medallion, centred in the icon cell --------------------------
    ix0, iy0, ix1, iy1 = (v * SCALE for v in ICON)
    a[iy0:iy1, ix0:ix1] = 0.0
    icon = premultiply(er_icon_rgba())
    ih, iw = icon.shape[:2]
    ox = ix0 + ((ix1 - ix0) - iw) // 2
    oy = iy0 + ((iy1 - iy0) - ih) // 2
    a[oy:oy + ih, ox:ox + iw] = icon
    return np.clip(a, 0, 255).astype(np.uint8)


def build(tpf_in: Path, tpf_out: Path, preview: Path | None = None) -> None:
    from oodle import dcx_decompress, dcx_compress_dflt
    from tpf_png import decode
    from soulstruct.containers import TPF
    from build_glyph_mod import dds_bgra

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    tex = [t for t in tpf.textures if t.stem == "MENU_PlayerHUD"][0]
    img = decode(tex.data).convert("RGBA")
    if img.size != (256 * SCALE, 256 * SCALE):
        img = img.resize((256 * SCALE, 256 * SCALE), Image.LANCZOS)
    atlas = paint(np.asarray(img).copy())
    if preview:
        preview.mkdir(parents=True, exist_ok=True)
        Image.fromarray(atlas, "RGBA").save(preview / "MENU_PlayerHUD_x2.png")
        bg = Image.new("RGBA", (512, 512), (60, 20, 80, 255))
        bg.alpha_composite(Image.fromarray(atlas, "RGBA"))
        bg.save(preview / "MENU_PlayerHUD_x2_onbg.png")
    tex.data = dds_bgra(Image.fromarray(atlas, "RGBA"))
    tex.format = 9
    dcx = dcx_compress_dflt(tpf.to_bytes())
    rt = TPF.from_bytes(dcx_decompress(dcx))
    if len(rt.textures) != len(tpf.textures):
        raise SystemExit("texture count changed during repack")
    tpf_out.write_bytes(dcx)
    print(f"wrote {tpf_out} ({len(dcx)} bytes); MENU_PlayerHUD now {atlas.shape[1]}x{atlas.shape[0]} BGRA")


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
