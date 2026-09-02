"""Row-by-row profile of our bars against Elden Ring's, at native 4K.

    hud_rows.py <capture.png> [--bar hp|fp|st] [--cols 40:200]

For each bar, prints per-row mean RGB over a column window INSIDE the fill
(offsets from the fill's left edge, default 40..200 px, well short of any
bar's end) for rows -3..+27 relative to the fill window's top, beside Elden
Ring's own rows from the reference grab, with the per-row deltaE.

Geometry is fixed because both frames are native 4K: our fill window tops are
at 4K rows 154 (HP), 188 (FP), 222 (stamina), x from BAR_X (measured by the
checkerboard probe 2 Sep 2026, then shifted with the bars). ER's assembly rows are those in
er_hud_graft.SOURCES (fill/bevel/rail = 24 rows, HP 96..120 etc., with one
row of context either side).
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from hud_tune import _de   # noqa: E402

REF = Path.home() / "couch/data/ds3-ui-port/er-reference"
# x is the BAR ORIGIN at 4K. It was 384 until 2 Sep evening, when
# er_fe_gfx.py --shift-bars 16 moved the bars 32 px right so Elden Ring's cap
# clears the covenant badge (ER's own badge-to-bar gap). The red fill starts
# 8 px right of the origin (the tile's first displayed texel is base 4).
BAR_X = 416
OURS = {"hp": (154, BAR_X), "fp": (188, BAR_X), "st": (222, BAR_X)}
ER = {
    "hp": ("hud_full.png", 96, 350),
    "fp": ("burst/hud-combat-full.png", 132, 330),
    "st": ("hud_full.png", 168, 350),
}
ER_WIDTH = {"hp": 1300, "fp": 369, "st": 660}


def profile(img, y0, x0, width, lo=-3, hi=27):
    out = {}
    for r in range(lo, hi + 1):
        band = img[y0 + r, x0 + 40: x0 + min(200, width - 10)]
        out[r] = band.mean(axis=0)
    return out


def main():
    argv = sys.argv[1:]
    bars = ["hp", "fp", "st"]
    if "--bar" in argv:
        i = argv.index("--bar"); bars = [argv[i + 1]]; del argv[i:i + 2]
    cap = np.asarray(Image.open(argv[0]).convert("RGB")).astype(float)
    if cap.shape[0] != 2160:
        raise SystemExit("native 4K capture expected")
    for bar in bars:
        y0, x0 = OURS[bar]
        f, ey, ex = ER[bar]
        er = np.asarray(Image.open(REF / f).convert("RGB")).astype(float)
        ours = profile(cap, y0, x0, 512)
        theirs = profile(er, ey, ex, ER_WIDTH[bar])
        print(f"\n{bar.upper()}  row   ours (RGB)        ER (RGB)        dE")
        tot = 0.0
        for r in ours:
            o, t = ours[r], theirs[r]
            de = _de(o, t)
            if 0 <= r < 24:
                tot += de
            tag = "" if 0 <= r < 24 else "  (context)"
            print(f"     {r:+3d}  {o.round().astype(int)!s:16s} {t.round().astype(int)!s:16s} {de:5.1f}{tag}")
        print(f"     sum dE over the 24 drawn rows: {tot:.0f}")


if __name__ == "__main__":
    main()
