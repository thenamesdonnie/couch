"""Fill-texture check at native 4K: is our grain Elden Ring's, texel for texel?

    hud_grain.py <capture.png>

Per bar: dominant-channel std, column-profile std and autocorrelation of the
flat fill rows, ours vs ER's reference; then the per-pixel correlation of our
flat rows against ER's SB_FE_01 strip at the expected alignment (atlas column
c = strip texel c-3, our red starts at BAR_X+8) with a small offset search.
Windows stay inside the shortest bar (a 480 px window ran the FP and stamina
checks into scenery and read 0.05; the trap from the notes). A 1:1 landing
reads as correlation ~0.95 at offset 0 for HP; FP and stamina start on strip
texels 8 and 7 rather than 5, so they read +3 and +2 (er_hud_graft strip_x0) (the capture adds ~1 unit
of noise); the old screenshot-resampled fill reads ~0.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from hud_rows import OURS, ER, REF   # noqa: E402

SHEET = Path.home() / "couch/data/ds3-ui-port/extract/er/png/SB_FE_01.png"
STRIP = {"hp": 119, "fp": 155, "st": 83}
CH = {"hp": 0, "fp": 2, "st": 1}


def stats(band):
    dev = band - band.mean(axis=1, keepdims=True)
    col = dev.mean(axis=0)
    ac = [float(np.corrcoef(col[:-k], col[k:])[0, 1]) for k in (1, 2, 4, 8, 16)]
    return band.std(), col.std(), ac


def main():
    cap = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(float)
    sheet = np.asarray(Image.open(SHEET).convert("RGB")).astype(float)
    for bar in ("hp", "fp", "st"):
        ch = CH[bar]
        y0, x0 = OURS[bar]
        f, ey, ex = ER[bar]
        er = np.asarray(Image.open(REF / f).convert("RGB")).astype(float)
        n = 260                      # INSIDE every bar: the FP bar is the shortest at ~280 px
        ours = cap[y0 + 1: y0 + 11, x0 + 8 + 20: x0 + 8 + 20 + n, ch]
        theirs = er[ey + 1: ey + 11, ex + 20: ex + 20 + n, ch]
        so, co, ao = stats(ours)
        st, ct, at = stats(theirs)
        ss, cs, _ = stats(sheet[STRIP[bar] + 1: STRIP[bar] + 11, 25: 25 + n, ch])
        print(f"{bar}: std ours {so:.2f} ER {st:.2f} strip {ss:.2f} | column std strip {cs:.2f} | column std ours {co:.2f} ER {ct:.2f} | "
              f"autocorr lags 1,2,4,8,16 ours {[round(a,2) for a in ao]} ER {[round(a,2) for a in at]}")
        # per-pixel correlation against the strip: capture column x0+8+j holds strip texel 5+j
        best = None
        for k in (2, 6, 10):
            row = cap[y0 + k, x0 + 8: x0 + 8 + 280, ch]
            for off in range(-5, 7):
                srow = sheet[STRIP[bar] + k, 5 + off: 5 + off + 280, ch]
                if len(srow) != len(row):
                    continue
                c = float(np.corrcoef(row, srow)[0, 1])
                if best is None or c > best[0]:
                    best = (c, off, k)
        print(f"     per-pixel vs strip: best corr {best[0]:.3f} at column offset {best[1]:+d} (row +{best[2]})")


if __name__ == "__main__":
    main()
