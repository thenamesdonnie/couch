"""The two rim rows above each bar: Elden Ring's model, and ours against it.

    hud_rim.py --er                 fit ER's rim model from the reference frames
    hud_rim.py <capture.png>        our rim rows against the model, at native 4K

WHY A MODEL AND NOT A ROW OF PIXELS. hud_rows.py compares our rows with ER's
rows from ONE frame, which is right for the fill (opaque) and wrong for the
two rows above it: ER's rim is translucent at -2 and the reference frame has
sage fog behind it where our sandbox has a dark bluish scene, so a straight
pixel comparison there measures the two scenes, not the rim. Measured across
five reference frames with different scenes behind the bars (3 Sep 2026,
window 40..100 px in from the fill's start so the shortest bar stays inside):

    row -1 is OPAQUE: identical in every frame to 0.1 units
        HP 94.3,42.1,20.6   FP 51.7,72.6,64.6   stamina 55.4,73.4,34.0
    row -2 is a translucent tint, out = c + k * scene (least squares, one k
    for all three channels because it is an alpha, max residual 0.3):
        HP      c=(40.6,18.0,10.1) k=0.264
        FP      c=(16.1,26.8,26.8) k=0.338
        stamina c=(11.4,19.8,11.8) k=0.423

The scene for the fit is each frame's row -5, which is above everything the
HUD draws there (the trough profile's alpha is 0.03 at -4 and nothing at -5).

Our side, from the same window: rows -2/-1 of the capture against the model
evaluated on OUR scene (the capture's own row -5), plus ER's hud_full row for
context. dE is the CIE76 distance hud_tune uses everywhere else.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from hud_tune import _de   # noqa: E402
from hud_rows import OURS, ER, REF   # noqa: E402

# (file, fill-top row, fill x) for every frame with all three bars at full
# length over the window; frames where a bar is depleted past the window are
# dropped by the fill check at run time.
FRAMES = ["hud_full.png", "hud_depleted.png", "burst/hud-combat-full.png",
          "burst/interact-prompt-bloodstain.png", "burst/hud-damage-lag.png",
          "burst/hud-lockon-enemy-bar.png"]
FILL = {"hp": (93, 26, 22), "fp": (27, 67, 86), "st": (28, 68, 45)}
W0, W1 = 40, 100
SCENE_ROW = -5
RIM_ROWS = (-2, -1)


def band(img, y, x, r):
    return img[y + r, x + W0:x + W1]


def fit_er():
    """Per bar and rim row: c (RGB) and k such that out = c + k*scene."""
    out = {}
    for bar in ("hp", "fp", "st"):
        f0, ey, ex = ER[bar]
        samples = []
        for f in FRAMES:
            im = np.asarray(Image.open(REF / f).convert("RGB")).astype(float)
            if np.abs(band(im, ey, ex, 3).mean(axis=0) - np.array(FILL[bar])).max() > 8:
                continue
            s = band(im, ey, ex, SCENE_ROW).mean(axis=0)
            samples.append((s, {r: band(im, ey, ex, r).mean(axis=0) for r in RIM_ROWS}))
        out[bar] = {}
        for r in RIM_ROWS:
            S = np.array([s for s, _ in samples])
            O = np.array([o[r] for _, o in samples])
            # one k for all channels (it is an alpha), c per channel
            A = np.column_stack([S.reshape(-1), np.repeat(np.eye(3), len(samples), axis=0).reshape(3, len(samples), 3).transpose(1, 0, 2).reshape(-1, 3)])
            sol, *_ = np.linalg.lstsq(A, O.reshape(-1), rcond=None)
            k, c = float(sol[0]), sol[1:4]
            resid = O - (c + k * S)
            out[bar][r] = (c, max(k, 0.0), float(np.abs(resid).max()), len(samples))
    return out


def main():
    argv = sys.argv[1:]
    model = fit_er()
    if "--er" in argv:
        for bar, rows in model.items():
            for r, (c, k, res, n) in rows.items():
                print(f"{bar}  row {r:+d}: c=({c[0]:.1f},{c[1]:.1f},{c[2]:.1f}) k={k:.3f}  max resid {res:.1f} over {n} frames")
        return
    cap = np.asarray(Image.open(argv[0]).convert("RGB")).astype(float)
    if cap.shape[0] != 2160:
        raise SystemExit("native 4K capture expected")
    ref = np.asarray(Image.open(REF / "hud_full.png").convert("RGB")).astype(float)
    tot = 0.0
    for bar in ("hp", "fp", "st"):
        y0, x0 = OURS[bar]
        f0, ey, ex = ER[bar]
        scene = band(cap, y0, x0, SCENE_ROW).mean(axis=0)
        print(f"\n{bar.upper()}  scene(-5) {scene.round(1)}   row  ours            predicted       dE    ER hud_full")
        for r in RIM_ROWS:
            c, k, _, _ = model[bar][r]
            ours = band(cap, y0, x0, r).mean(axis=0)
            pred = c + k * scene
            de = _de(ours, pred)
            tot += de
            print(f"{'':38s}{r:+3d}  {ours.round().astype(int)!s:15s} {pred.round().astype(int)!s:15s} {de:5.1f}  {band(ref, ey, ex, r).mean(axis=0).round().astype(int)}")
    print(f"\nsum dE over the six rim rows: {tot:.1f}")


if __name__ == "__main__":
    main()
