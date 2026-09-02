"""Restyle DS3's covenant badge to sit where Elden Ring puts its Great Rune slot.

WHAT THIS IS. The bright cracked-stone octagon top-left of the DS3 HUD, next to
the bars, is the COVENANT badge - MENU_PledgeIcon, a 10x4 grid of 128px cells
(row 1 normal, rows 2-4 the lit and darkened variants). With no covenant joined
it shows cell (0,0), a blank plaque, and that plaque is the single brightest
thing on the HUD at (129,115,90) on screen.

Elden Ring puts its Great Rune indicator in exactly that spot and it is nearly
black - measured (25,32,26) - with a thin pale border. Ours was five times
brighter, which made it the loudest mismatch left after the bars.

HOW IT WAS FOUND. Not by name. Six textures were flooded with distinct tracer
colours and the frame read back: the medallion came out magenta, which was
MENU_PledgeIcon. Guessing had already cost two wrong runs on MENU_PlayerHUD's
top-left octagon, which turns out to feed nothing visible here.

NO COMPENSATION NEEDED. Unlike the gauge fill, this element renders essentially
1:1 - atlas (126,111,83) arrives as screen (129,115,90). So the target values
below are written directly rather than pre-compensated.

WHY NOT JUST MULTIPLY IT DOWN. The badge carries the covenant emblem, and
Donnie plays this character; crushing the whole cell would take the emblem with
it. Instead each cell is re-levelled about its OWN stone median, so the plaque
field lands on ER's dark value while anything brighter than the stone - the
emblem, the rim highlights - keeps its distance above it and stays readable.
A joined covenant should still be identifiable at a glance.

    python er_pledge_icon.py <in.tpf.dcx> <out.tpf.dcx>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image

CELL = 128
COLS, ROWS = 10, 4

# ER's Great Rune octagon, measured off the live game.
TARGET_STONE = 20.0
# Above 1.0 the emblem separates further from the darkened field. 1.0 keeps ER's
# flatness; higher starts looking like a different game again.
CONTRAST = 1.0
# ER's thin pale border. Its rail and key-line family, same bone.
BORDER_RGB = (150, 144, 112)
BORDER_PX = 2


def restyle_cell(cell: np.ndarray) -> np.ndarray:
    """One 128px badge: darken the plaque, keep the emblem, add ER's border."""
    from scipy.ndimage import binary_erosion

    out = cell.astype(float).copy()
    mask = out[..., 3] > 128
    if mask.sum() < 50:
        return cell

    rgb = out[..., :3]
    lum = rgb.mean(axis=2)

    # The stone field is the bulk of the badge, so its median IS the plaque
    # level. Using the mean instead would be dragged up by bright emblems.
    stone = float(np.median(lum[mask]))
    if stone < 1.0:
        return cell

    new_lum = TARGET_STONE + (lum - stone) * CONTRAST
    new_lum = np.clip(new_lum, 0.0, 255.0)

    # Scale RGB toward the new luminance, preserving hue.
    scale = np.divide(new_lum, np.maximum(lum, 1e-6))[..., None]
    rgb = np.clip(rgb * scale, 0, 255)

    ring = mask & ~binary_erosion(mask, iterations=BORDER_PX)
    rgb[ring] = BORDER_RGB

    out[..., :3] = rgb
    out[~mask, :3] = cell[~mask, :3]      # leave fully transparent pixels alone
    return out.astype(np.uint8)


def build(tpf_in: Path, tpf_out: Path) -> None:
    from oodle import dcx_decompress, dcx_compress_dflt
    from tpf_png import decode
    from soulstruct.containers import TPF
    from build_glyph_mod import dds_bgra

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    tex = [t for t in tpf.textures if t.stem == "MENU_PledgeIcon"][0]
    a = np.asarray(decode(tex.data).convert("RGBA")).copy()

    before = a[0:CELL, 0:CELL]
    bm = before[..., 3] > 128
    print(f"  before: blank plaque mean "
          f"{tuple(before[..., :3][bm].mean(axis=0).round().astype(int))}")

    for r in range(ROWS):
        for c in range(COLS):
            y, x = r * CELL, c * CELL
            if y + CELL > a.shape[0] or x + CELL > a.shape[1]:
                continue
            a[y:y + CELL, x:x + CELL] = restyle_cell(a[y:y + CELL, x:x + CELL])

    after = a[0:CELL, 0:CELL]
    am = after[..., 3] > 128
    print(f"  after : blank plaque mean "
          f"{tuple(after[..., :3][am].mean(axis=0).round().astype(int))}"
          f"   (ER's octagon is 25,32,26)")

    tex.data = dds_bgra(Image.fromarray(a, "RGBA"))
    tex.format = 9
    dcx = dcx_compress_dflt(tpf.to_bytes())
    rt = TPF.from_bytes(dcx_decompress(dcx))
    if len(rt.textures) != len(tpf.textures):
        raise SystemExit("texture count changed during repack")
    tpf_out.write_bytes(dcx)
    print(f"  wrote {tpf_out} ({len(dcx):,} bytes), verified")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    build(Path(sys.argv[1]), Path(sys.argv[2]))
