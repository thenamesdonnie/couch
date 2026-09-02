"""Lift the vertical brush-stroke grain off Elden Ring's real HP bar.

Donnie, looking at a build where the bars were the right colour and still read
wrong: "the elden ring health bar has an actual texture on the health btw".
He was right. er_hud_bars.fill_block was painting flat colour with a vertical
gradient, and ER's fill is close to the opposite of that:

    vertical profile   46.3 -> 49.4 luminance across the whole fill. FLAT.
                       (the bright 51.8/58.1/63.8/69.8 rows underneath it are
                       the bone key-line BELOW the bar, not the fill lifting.
                       Including them is what made the first read wrong.)
    horizontal grain   std 2.48, range -11.7..+15.2, in coherent VERTICAL
                       streaks - brush strokes, not noise.

So the texture is nearly all horizontal variation, and the gradient that was
there before (a 116->66 span on screen against ER's 46->49) was ~15x too
strong and pointing the wrong way.

WHY THIS IS A SEPARATE FILE AND A BAKED PNG. The grain is lifted from a 4K
screen-grab of the live game, which is not something the build should depend
on being present. Run this once, commit hud_fill_grain.png, and er_hud_bars.py
just reads the asset.

SCALE. The PNG stores delta+128, one stored unit = one RGB unit ON SCREEN at
4K. er_hud_bars.py divides by DS3's measured 0.87 gain to get atlas units.

    python extract_fill_grain.py [hud_full.png] [out.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

# The HP fill in the reference grab, found by red-dominance then trimmed.
# Rows 95-107 is fill; 108+ is the key-line and must stay out of it.
FILL_ROWS = (95, 108)
FILL_COLS = (350, 1600)          # inset from both end-caps
OUT_SIZE = (256, 24)             # the atlas fill block

# ER's grab is 4K; DS3's bar is authored at 1:1 against 1920. Halving x keeps
# the streaks at the right apparent width instead of blurring them away.
X_DOWNSAMPLE = 2


def extract(src: Path, out: Path) -> None:
    a = np.asarray(Image.open(src).convert("RGB")).astype(float)
    band = a[FILL_ROWS[0]:FILL_ROWS[1], FILL_COLS[0]:FILL_COLS[1]]
    lum = band.mean(axis=2)

    # Grain is deviation from each row's own mean, so the (tiny) vertical
    # profile does not leak into the texture. The profile is handled
    # separately, and is nearly flat anyway.
    grain = lum - lum.mean(axis=1, keepdims=True)
    print(f"source grain: std {grain.std():.2f}, "
          f"range {grain.min():.1f}..{grain.max():.1f}, shape {grain.shape}")

    # Halve horizontally by averaging pairs, then tile/crop to 256 wide.
    w = (grain.shape[1] // X_DOWNSAMPLE) * X_DOWNSAMPLE
    half = grain[:, :w].reshape(grain.shape[0], -1, X_DOWNSAMPLE).mean(axis=2)
    reps = int(np.ceil(OUT_SIZE[0] / half.shape[1]))
    tiled = np.tile(half, (1, reps))[:, :OUT_SIZE[0]]

    # Stretch to the block's 24 rows. Streaks are vertical, so this costs
    # nothing - it is smearing along the direction they already run.
    img = Image.fromarray((tiled + 128).clip(0, 255).astype(np.uint8), "L")
    img = img.resize(OUT_SIZE, Image.BILINEAR)

    final = np.asarray(img).astype(float) - 128
    print(f"baked grain:  std {final.std():.2f}, "
          f"range {final.min():.1f}..{final.max():.1f}, size {img.size}")
    img.save(out)
    print(f"wrote {out}")


# The bone key-line UNDER the bar - Donnie: "we also need the long paler bar at
# the bottom of the texture". It is not a plain line: it is finely ruled, like
# hatching on a ruler, std 11.1 on a mean of 129 at 4K.
KEYLINE_ROWS = (116, 120)
KEYLINE_COLS = (350, 1600)


def extract_keyline(src: Path, out: Path) -> None:
    a = np.asarray(Image.open(src).convert("RGB")).astype(float)
    band = a[KEYLINE_ROWS[0]:KEYLINE_ROWS[1], KEYLINE_COLS[0]:KEYLINE_COLS[1]]
    lum = band.mean(axis=2)
    ticks = lum.mean(axis=0)                      # collapse to one row of ticks
    ticks = ticks - ticks.mean()
    print(f"keyline ticks: std {ticks.std():.2f}, "
          f"range {ticks.min():.1f}..{ticks.max():.1f}, {len(ticks)} px")

    w = (len(ticks) // X_DOWNSAMPLE) * X_DOWNSAMPLE
    half = ticks[:w].reshape(-1, X_DOWNSAMPLE).mean(axis=1)
    reps = int(np.ceil(OUT_SIZE[0] / len(half)))
    tiled = np.tile(half, reps)[:OUT_SIZE[0]]

    img = Image.fromarray((tiled + 128).clip(0, 255).astype(np.uint8)[None, :], "L")
    print(f"baked ticks:   std {np.asarray(img).astype(float).std():.2f}, size {img.size}")
    img.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    ref = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path.home() / "couch/data/ds3-ui-port/er-reference/hud_full.png"
    here = Path(__file__).parent
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else here / "hud_fill_grain.png"
    extract(ref, dst)
    extract_keyline(ref, here / "hud_keyline_ticks.png")
