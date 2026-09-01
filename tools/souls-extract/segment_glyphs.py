"""Cut a glyph sheet into individual glyphs, without cutting or leakage.

Two approaches were tried and the first was WRONG, which is worth recording.

A fixed grid (512/7 = ~70px cells) LOOKS right and is not: Elden Ring's SB_KG
is not a uniform grid. Glyph bounding boxes range 36-92 wide and 27-89 tall,
the OPTIONS label is about two cells wide, and the stick glyphs are taller than
one cell. A grid slices those in half. Donnie caught this by zooming in on a
contact sheet; the defect is invisible at thumbnail scale.

What works:
  1. Threshold alpha high (>200) to get glyph CORES, ignoring the soft glow
     which otherwise merges every glyph into one blob.
  2. Dilate slightly (r=3) and label, so the parts of one glyph join up - a
     d-pad is four separate arrows, a circled letter is a ring plus a letter.
     Bigger radii over-merge: r=9 collapses 49 glyphs into 14.
  3. VORONOI-ASSIGN every pixel to its nearest component, then mask each glyph
     to the pixels it owns. This is the step that matters. Cropping a plain
     rectangle pulls in whatever neighbouring glyph happens to fall inside it,
     which produced stray bars through half the set. Nearest-owner assignment
     keeps each glyph's own glow while making leakage impossible, and as a
     bonus it splits pairs that step 2 over-merged (OPTIONS and its pill).

Usage:
    python segment_glyphs.py <sheet.png> <outdir> [--sheet]
"""
from __future__ import annotations

import sys
from pathlib import Path

CORE_ALPHA = 200      # above the glow, below the glyph body
GROUP_RADIUS = 3      # joins parts of one glyph; larger over-merges
MIN_CORE_PX = 120     # discards specks


def segment(path: Path):
    """-> list of (index, RGBA Image) with each glyph isolated."""
    from PIL import Image
    import numpy as np
    from scipy import ndimage

    im = Image.open(path).convert("RGBA")
    a = np.asarray(im)
    alpha = a[..., 3]

    r = GROUP_RADIUS
    st = np.zeros((2 * r + 1, 2 * r + 1), bool)
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    st[xx * xx + yy * yy <= r * r] = True
    core = alpha > CORE_ALPHA
    lbl, n = ndimage.label(ndimage.binary_dilation(core, st))

    _, (iy, ix) = ndimage.distance_transform_edt(lbl == 0, return_indices=True)
    owner = lbl[iy, ix]
    sizes = ndimage.sum(core, lbl, range(1, n + 1))

    out = []
    for i in range(1, n + 1):
        if sizes[i - 1] < MIN_CORE_PX:
            continue
        mine = (owner == i) & (alpha > 4)
        ys, xs = np.where(mine)
        if len(ys) < 100:
            continue
        box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        sub = a.copy()
        sub[..., 3] = np.where(owner == i, alpha, 0)     # only THIS glyph
        out.append((box, Image.fromarray(sub[box[1]:box[3], box[0]:box[2]], "RGBA")))

    out.sort(key=lambda g: (round(g[0][1] / 40), g[0][0]))   # reading order
    return [(i, img) for i, (_, img) in enumerate(out)]


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, dest = Path(sys.argv[1]), Path(sys.argv[2])
    dest.mkdir(parents=True, exist_ok=True)
    glyphs = segment(src)
    for i, img in glyphs:
        img.save(dest / f"{i:02d}.png")
    print(f"{len(glyphs)} glyphs -> {dest}")
