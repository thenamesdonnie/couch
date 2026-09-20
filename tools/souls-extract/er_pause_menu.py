#!/usr/bin/env python3
"""Repaint DS3's pause-menu texture, MENU_Top, as Elden Ring's list chrome.

WHAT DRAWS THE PAUSE MENU (menu/02_000_ingametop.gfx, read with fe_tree.py):
root `ItemList` (sprite 86) at stage (580, 640), one stage px = two 4K px.

  depth 1   sprite 23 -> 22 (alphaMult 218/256) -> shape 21: the 600x400 panel,
            MENU_Top [4..604, 172..572]. Sprite 86's later frames fade it.
  Item_0_0..4  sprites 67/64/61/58/55 at y -100, x -196..196 step 98: each is
            a 90x90 tile quad (shapes 65/62/59/56/53, MENU_Top [4+100k..94+100k,
            4..94]) plus a `Cursor` (sprite 50, MENU_ItemParts highlight at
            0.5625). Item_0_5 (sprite 52) is a Cursor with no tile.
  Item_1_0..4  sprite 51 at y 55: the quick items (Dish -> shape 24 from
            MENU_ItemPanel_02, ItemIcon, StockNum, Cursor).
  RowText   sprite 77: Item_0 / Item_1, each a rule (shape 71), a highlight
            band (shape 68) and ONE right-aligned text `Text_0`. The engine
            writes the highlighted tile's name into Item_0's Text_0 - that is
            the single "Equipment" label left of the panel in the capture.
  depth 68  sprite 79: the orange rule (shape 78, MENU_Top [4..492, 568..576]).
  StatusBar KeyGuide text (the A:OK B:Close prompts). CurrentItem: the
            selected quick item's name.

ER's pause menu (burst/pause-menu-1..3.png, 4K): a vertical list, tile
centres at x 174, y 503 + 192k; the unlit tile frame ~133x137 px; the label
starts at x 283, cap height 30 px, baseline 18 px under the tile centre,
colour (209,197,173) lit or not; the lit tile is a bright wash over the
tile with a glow to the screen's left edge; a soft dark wash behind the
whole column; Pouch grid on the right, cells ~152 px at x 3418/3577,
rows 512/690/868; prompts at x 124, glyph rows 1858..1907.

THE LABELS ARE ART. The movie has one label field for the whole row, so the
five names (Equipment, Inventory, Status, Message, System - FDP_メニューテキスト
101000..101004, DS3's own strings) are baked next to each tile: each tile
quad becomes a 280x80 stage-px STRIP (tile + label) sampling its own row of
this atlas, and the engine's single label is parked off screen.

RESOLUTION. Shipped at 2x (2048x2048 BGRA): the engine normalises UVs to the
declared 1024, so one texel is one 4K px and the text and ER's icons draw
1:1 (the HUD atlases follow the same rule).

ATLAS LAYOUT (base texels; 2x in the file):
  [0..280, 620+80k..700+80k]  strip k: tile centred at (45,40), label from x 99.5
  [300..460, 620..780]        the pouch cell (shape 24 is retargeted here)
  [4..604, 172..572]          the wash (drawn stretched over 4K -100..720 x 300..1900)
  rows 0..100 and the rules   cleared

    python er_pause_menu.py <in.tpf.dcx> <out.tpf.dcx> [--preview dir]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).resolve().parents[2] / "data/ds3-ui-port"
ER_TEX = ROOT / "extract/er/png/SB_In_GameTop.png"
FONT = ROOT / "build/fonts/Spectral-SemiBold.ttf"

SCALE = 2
BASE = 1024

# ER icon cells in SB_In_GameTop (alpha bboxes), matched to the 4K screen by
# correlation (match_icons: Equipment grid11 0.41, Inventory grid01 0.34,
# Status col1 0.61, System col0 0.62; Messages by eye = the finger rows).
ER_CELLS = {
    # 3 Sep evening: the cell = the frame's outer alpha edge (142x146 with a
    # 4-texel transparent gutter between cells, atlas_cells.py). The first
    # crops were alpha bboxes that ran 13..16 rows high and 4 columns right for
    # three of the five, so those tiles carried the cell ABOVE's bottom frame
    # line and lost their own; Status and System were already exact.
    "Equipment": (782, 1536, 924, 1682),
    "Inventory": (782, 1386, 924, 1532),
    "Status": (744, 150, 886, 296),
    "Message": (636, 1386, 778, 1532),
    "System": (744, 0, 886, 146),
}
LABELS = ["Equipment", "Inventory", "Status", "Message", "System"]
TILE_DRAW = 1.0           # 3 Sep, Donnie: 'icons slightly misaligned'. ER's frame measures 137x141 at 4K = the 142x146 cell at 1:1 minus its transparent rim; 0.94 (fitted on the icon ink) drew it 127x119 with the frame clipped
STRIP_W, STRIP_H = 280, 80     # base texels (stage px)
STRIP_V0 = 620
TILE_CX, TILE_CY = 46.5, 40    # base, inside the strip (run: our frame centre sat 3 px left of ER's 175.5 at 4K)
LABEL_X = 99.5                 # base: ER's 283 - 174 = 109 4K px right of the tile centre
LABEL_BASELINE = 49            # base: tile centre + 9 (ER: +18 at 4K)
CAP_PX = 30                    # 4K px
LABEL_RGB = (209, 197, 173)      # ER on screen; written through the inverse transfer
SCREEN_GAMMA = 0.8795            # screen = 255*(atlas/255)^gamma (RECIPE, the HUD atlases); run 1 read the labels at 214/203/181 from 209/197/173 written raw

POUCH_UV = (300, 620, 460, 780)   # base
CELL_PX = 152                     # ER's cell at 4K
CELL_FIELD = ((10, 10, 9), 0.45)   # run 1 at 0.28 / 0.50 / 0.40 was barely readable over DS3's undimmed scene
CELL_RIM = ((75, 70, 55), 0.75)
CELL_DARK = ((0, 0, 0), 0.50)

WASH_UV = (4, 172, 604, 572)      # base, the panel quad
WASH_SCREEN = (-100, 300, 720, 1900)  # 4K rect the quad is stretched over
# ER's band is a light haze over its heavily dimmed frame (the band reads ~47
# where ER's scene outside it reads 15..33). DS3 dims its pause frame by only
# 0.98, so run 1's (42,42,36) at 0.55 (screen 52 after the transfer) vanished
# against rocks that already sit at 50. A haze that the band converges to:
WASH_RGB = (40, 40, 35)          # run 2 at (46,46,40)/0.65 read as a band converging on ~56; ER's converges on ~47
WASH_A = 0.6                     # the renderer multiplies alpha by ~1.2 (run 2 fit 0.78..0.83 from 0.65; the same gain the area-name rule showed)
WASH_X_PLATEAU, WASH_X_END = 430, 720
WASH_Y_IN = (300, 440)
WASH_Y_OUT = (1760, 1900)


def to_atlas(rgb):
    """Screen colour -> atlas value through the inverse of the render transfer."""
    v = np.asarray(rgb, float) / 255.0
    return 255.0 * np.power(np.clip(v, 0, 1), 1.0 / SCREEN_GAMMA)


def font_for_cap(cap_px: int) -> ImageFont.FreeTypeFont:
    """Spectral SemiBold at the size whose capital E is cap_px tall."""
    best = None
    for size in range(30, 90):
        f = ImageFont.truetype(str(FONT), size)
        x0, y0, x1, y1 = f.getbbox("E")
        h = y1 - y0
        if best is None or abs(h - cap_px) < abs(best[1] - cap_px):
            best = (f, h, size)
    return best[0]


def strip_rgba(label: str, font) -> np.ndarray:
    """One tile+label strip at 2x, straight alpha, float RGBA 0..255."""
    W, H = STRIP_W * SCALE, STRIP_H * SCALE
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    er = Image.open(ER_TEX).convert("RGBA")
    x0, y0, x1, y1 = ER_CELLS[label]
    cell = er.crop((x0, y0, x1, y1))
    cw, ch = round((x1 - x0) * TILE_DRAW), round((y1 - y0) * TILE_DRAW)
    cell = cell.resize((cw, ch), Image.LANCZOS)
    c = np.asarray(cell).astype(float)
    c[..., :3] = to_atlas(c[..., :3])          # run 1: the raw cell read 4/6/8 brighter than ER's
    cell = Image.fromarray(c.astype(np.uint8), "RGBA")
    img.alpha_composite(cell, (int(round(TILE_CX * SCALE)) - cw // 2, int(round(TILE_CY * SCALE)) - ch // 2))
    # the label: draw white on black at 1x and use the coverage as alpha
    txt = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(txt)
    ex0, ey0, ex1, ey1 = font.getbbox("E")
    # baseline = the E's bottom; PIL places the glyph top at y + ey0
    y = LABEL_BASELINE * SCALE - ey1
    d.text((LABEL_X * SCALE, y), label, font=font, fill=255)
    cov = np.asarray(txt).astype(float) / 255.0
    out = np.asarray(img).astype(float)
    a = cov[..., None]
    out[..., :3] = out[..., :3] * (1 - a) + to_atlas(LABEL_RGB) * a
    out[..., 3] = np.maximum(out[..., 3], cov * 255.0)
    return out


def pouch_cell_rgba() -> np.ndarray:
    """ER's pouch cell, straight alpha, at the 320x320 texel size shape 24 samples."""
    n = CELL_PX
    rgb = np.zeros((n, n, 3)); a = np.zeros((n, n))
    (fr, fa), (rr, ra), (dr, da) = CELL_FIELD, CELL_RIM, CELL_DARK
    rgb[:] = fr; a[:] = fa
    for k in (2, 3):
        rgb[k, :] = dr; rgb[n - 1 - k, :] = dr; rgb[:, k] = dr; rgb[:, n - 1 - k] = dr
        a[k, :] = da; a[n - 1 - k, :] = da; a[:, k] = da; a[:, n - 1 - k] = da
    for k in (0, 1):
        rgb[k, :] = rr; rgb[n - 1 - k, :] = rr; rgb[:, k] = rr; rgb[:, n - 1 - k] = rr
        a[k, :] = ra; a[n - 1 - k, :] = ra; a[:, k] = ra; a[:, n - 1 - k] = ra
    img = Image.fromarray(np.concatenate([rgb, a[..., None] * 255], axis=2).astype(np.uint8), "RGBA")
    w = (POUCH_UV[2] - POUCH_UV[0]) * SCALE
    return np.asarray(img.resize((w, w), Image.LANCZOS)).astype(float)


def wash_rgba() -> np.ndarray:
    """The column wash, painted in 4K screen space and resampled onto the quad."""
    sx0, sy0, sx1, sy1 = WASH_SCREEN
    xs = np.arange(sx0, sx1); ys = np.arange(sy0, sy1)
    def ramp(v, a, b):          # 1 at a, 0 at b, cosine
        t = np.clip((v - a) / (b - a), 0, 1)
        return 0.5 * (1 + np.cos(np.pi * t))
    ax = ramp(xs, WASH_X_PLATEAU, WASH_X_END)
    ay = (1 - ramp(ys, WASH_Y_IN[0], WASH_Y_IN[1])) * ramp(ys, WASH_Y_OUT[0], WASH_Y_OUT[1])
    a = ay[:, None] * ax[None, :] * WASH_A
    rgba = np.zeros((len(ys), len(xs), 4)); rgba[..., :3] = WASH_RGB; rgba[..., 3] = a * 255
    img = Image.fromarray(rgba.astype(np.uint8), "RGBA")
    w = (WASH_UV[2] - WASH_UV[0]) * SCALE; h = (WASH_UV[3] - WASH_UV[1]) * SCALE
    return np.asarray(img.resize((w, h), Image.LANCZOS)).astype(float)


def paint(atlas: np.ndarray) -> np.ndarray:
    a = atlas.astype(float)
    S = SCALE
    a[0:100 * S, 0:600 * S] = 0                      # the old tile row
    a[568 * S:604 * S, 4 * S:784 * S] = 0            # the orange rule and the row rules
    x0, y0, x1, y1 = WASH_UV
    a[y0 * S:y1 * S, x0 * S:x1 * S] = wash_rgba()
    font = font_for_cap(CAP_PX)
    for k, label in enumerate(LABELS):
        v0 = (STRIP_V0 + STRIP_H * k) * S
        a[v0:v0 + STRIP_H * S, 0:STRIP_W * S] = strip_rgba(label, font)
    x0, y0, x1, y1 = POUCH_UV
    a[y0 * S:y1 * S, x0 * S:x1 * S] = pouch_cell_rgba()
    return np.clip(a, 0, 255).astype(np.uint8)


def build(tpf_in: Path, tpf_out: Path, preview: Path | None = None) -> None:
    from oodle import dcx_decompress, dcx_compress_dflt
    from tpf_png import decode
    from soulstruct.containers import TPF
    from build_glyph_mod import dds_bgra

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    tex = [t for t in tpf.textures if t.stem == "MENU_Top"][0]
    img = decode(tex.data).convert("RGBA")
    if img.size != (BASE * SCALE, BASE * SCALE):
        img = img.resize((BASE * SCALE, BASE * SCALE), Image.LANCZOS)
    atlas = paint(np.asarray(img).copy())
    if preview:
        preview.mkdir(parents=True, exist_ok=True)
        Image.fromarray(atlas, "RGBA").save(preview / "MENU_Top_x2.png")
        bg = Image.new("RGBA", atlas.shape[1::-1], (60, 20, 80, 255))
        bg.alpha_composite(Image.fromarray(atlas, "RGBA"))
        bg.save(preview / "MENU_Top_x2_onbg.png")
    tex.data = dds_bgra(Image.fromarray(atlas, "RGBA"))
    tex.format = 9
    dcx = dcx_compress_dflt(tpf.to_bytes())
    rt = TPF.from_bytes(dcx_decompress(dcx))
    if len(rt.textures) != len(tpf.textures):
        raise SystemExit("texture count changed during repack")
    tpf_out.write_bytes(dcx)
    print(f"wrote {tpf_out} ({len(dcx)} bytes); MENU_Top now {atlas.shape[1]}x{atlas.shape[0]} BGRA")


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
