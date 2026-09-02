"""Cap geometry, measured the SAME WAY on Elden Ring's reference and on ours.

    hud_cap.py <capture.png>            # ours, native 4K
    hud_cap.py --er                     # the ER reference

Reports, for the HP bar: where the fill starts (first red-dominant column on
the fill's flat rows), and the bounding box of BONE pixels in a box that spans
60 px left of that start to 40 px right of it and 20 px above the fill top to
the rail. Bone = bright and warm (R > 110, R > B + 25, G > B + 10), tested on
a box where the ONLY bone thing is the cap and the rail (the rail is excluded
by stopping the box above it). Prints offsets relative to the fill start and
fill top so the two frames compare directly.

The earlier detector in hud_tune.py reported its own box bounds because DS3's
brown scenery passed its threshold on a stray pixel per row; this one prints
the count of bone pixels per row so a scenery false positive is visible.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
from PIL import Image

REF = Path.home() / "couch/data/ds3-ui-port/er-reference/hud_full.png"
# HP fill window top row and search band (both native 4K)
GEOM = {"er": (96, 119), "ours": (154, 177)}


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--er":
        img = np.asarray(Image.open(REF).convert("RGB")).astype(int)
        top, bot = GEOM["er"]
    else:
        img = np.asarray(Image.open(argv[0]).convert("RGB")).astype(int)
        top, bot = GEOM["ours"]
    flat = img[top + 2: top + 10]                      # flat fill rows
    red = (flat[..., 0] > 60) & (flat[..., 0] > flat[..., 1] * 2) & (flat[..., 0] > flat[..., 2] * 2)
    cols = np.where(red.sum(axis=0) >= 6)[0]
    # first column of the longest run
    runs, cur = [], [cols[0]]
    for c in cols[1:]:
        if c == cur[-1] + 1:
            cur.append(c)
        else:
            runs.append(cur); cur = [c]
    runs.append(cur)
    run = max(runs, key=len)
    x_start = run[0]
    print(f"fill: starts x={x_start}, top y={top}, flat-row run {len(run)} px long")
    y0, y1 = top - 20, top + 16                      # stop above the bevel's bright rows (+16)
    x0, x1 = x_start - 60, x_start + 40
    box = img[y0:y1, x0:x1]
    bone = (box[..., 0] > 110) & (box[..., 0] > box[..., 2] + 25) & (box[..., 1] > box[..., 2] + 10)
    per_row = bone.sum(axis=1)
    per_col = bone.sum(axis=0)
    print("bone px per row (y rel. to fill top): " +
          " ".join(f"{y - top:+d}:{n}" for y, n in zip(range(y0, y1), per_row) if n))
    print("bone px per col (x rel. to fill start): " +
          " ".join(f"{x - x_start:+d}:{n}" for x, n in zip(range(x0, x1), per_col) if n))
    # The covenant badge's gold frame sits at the far left of the box on both
    # frames and DS3's brown scenery fires the odd pixel: count a column as cap
    # only if it holds 3+ bone pixels, a row only if it holds 2+.
    keep_c = per_col >= 3
    keep_r = per_row >= 2
    bone = bone & keep_c[None, :] & keep_r[:, None]
    ys, xs = np.where(bone)
    if len(ys) == 0:
        print("no bone pixels"); return
    print(f"cap bbox: x {xs.min() + x0 - x_start:+d}..{xs.max() + x0 - x_start:+d} rel. to fill start "
          f"({xs.max() - xs.min() + 1} wide), y {ys.min() + y0 - top:+d}..{ys.max() + y0 - top:+d} "
          f"rel. to fill top ({ys.max() - ys.min() + 1} tall), {int(bone.sum())} bone px")


if __name__ == "__main__":
    main()
