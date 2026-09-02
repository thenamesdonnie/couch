"""Tune the DS3 HUD port against a captured frame, without launching the game.

WHY. Every iteration on this port has cost a ~2 minute game launch, and most of
them changed something whose effect was entirely predictable. Both stages of the
pipeline are now MEASURED, so both can be simulated on a frame we already have:

    atlas -> screen   fill      screen = 0.87  * atlas + 38
                      backdrop  screen = 0.833 * atlas + 48
                      the fill block draws only rows 6-17 of 24, 1:1
                      horizontally from the bar's left (2:1 at 4K)

    screen -> final   the vkBasalt pass, per-bar constant offsets

So: composite a candidate change onto a real capture, look at it, and only spend
a launch when it is worth validating. Simulation is NOT proof - it shares my
assumptions, so anything it blesses still gets one real run before I call it
done - but it turns twenty launches into one.

MODES

    shader  <frame.png> <out.png>
        Apply the vkBasalt correction offline. Same gates and per-bar offsets
        as ds3_hud_deepen.fx, so the .fx can be tuned by editing the constants
        here and looking, instead of by launching.

    overlay <frame.png> <cap.png> <out.png> [--dx N] [--dy N] [--scale S]
        Composite a cap image at each bar's left end. This is the one thing the
        texture route cannot do: the fill can only paint INSIDE the bar's
        rectangle, so a cap that overhangs has to come from the post-process
        pass. Use this to find the placement, then bake the numbers into the .fx.

    measure <frame.png>
        Report every HUD element in the frame against Elden Ring's measured
        values in one go: bar colours with deltaE, the cap's pixel footprint,
        the rail, the rune slot. Written because checking a change by hand
        meant cropping four regions and eyeballing them, which is slow and is
        how three false readings got made (each time by sampling past the end
        of a bar into the scene).

    compare <frame.png> <out.png>
        Stack our HP bar against Elden Ring's at matched scale.

Bar geometry, measured at 3840x2160 and stored NORMALISED so it holds at any
resolution: all three bars start at x 0.1018; HP y 0.0708-0.0806, FP
0.0870-0.0949, stamina 0.1028-0.1120.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

REF = Path.home() / "couch/data/ds3-ui-port/er-reference"

# Normalised, so these hold at 1080p and 4K alike.
BAR_LEFT = 0.11016      # 423/3840: bars shifted +16 stage px 2 Sep evening (was 0.10182)
BARS = {
    "hp":      dict(y0=0.07083, y1=0.08056, offset=(-2.0, -8.0, -12.0)),
    "fp":      dict(y0=0.08704, y1=0.09491, offset=(-10.0, 0.0, -2.0)),
    "stamina": dict(y0=0.10278, y1=0.11204, offset=(-10.0, 1.0, 1.0)),
}

# Mirrors ds3_hud_deepen.fx. Keep the two in step.
STRIP_TOP, STRIP_BOTTOM = 0.050, 0.145
STRIP_RIGHT = 0.62
CHROMA_MIN, CHROMA_FULL = 0.075, 0.150
BRIGHT_KEEP, BRIGHT_FADE = 0.42, 0.52


def _smoothstep(a: float, b: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def apply_shader(frame: np.ndarray) -> np.ndarray:
    """The vkBasalt pass, in numpy. Same gates, same per-bar offsets."""
    h, w = frame.shape[:2]
    out = frame.astype(float).copy()
    ys = (np.arange(h) / h)[:, None]
    xs = (np.arange(w) / w)[None, :]

    region = (_smoothstep(STRIP_TOP - 0.012, STRIP_TOP + 0.012, ys)
              * (1 - _smoothstep(STRIP_BOTTOM - 0.012, STRIP_BOTTOM + 0.012, ys))
              * (1 - _smoothstep(STRIP_RIGHT - 0.05, STRIP_RIGHT + 0.05, xs)))

    mx = out.max(axis=2) / 255.0
    mn = out.min(axis=2) / 255.0
    chroma = _smoothstep(CHROMA_MIN, CHROMA_FULL, mx - mn)
    dark = 1.0 - _smoothstep(BRIGHT_KEEP, BRIGHT_FADE, mx)
    amount = region * chroma * dark

    r, g, b = out[..., 0], out[..., 1], out[..., 2]
    off = np.zeros_like(out)
    is_hp = (r >= g) & (r >= b)
    is_fp = (~is_hp) & (b >= g) & (b >= r)
    is_st = ~(is_hp | is_fp)
    for mask, key in ((is_hp, "hp"), (is_fp, "fp"), (is_st, "stamina")):
        off[mask] = BARS[key]["offset"]

    return np.clip(out + off * amount[..., None], 0, 255).astype(np.uint8)


def apply_overlay(frame: np.ndarray, cap: Image.Image,
                  dx: int = 0, dy: int = 0, scale: float = 1.0) -> np.ndarray:
    """Composite `cap` at each bar's left end exactly as the vkBasalt shader does.

    Geometry is the shader's (ds3_hud_deepen.fx, 2 Sep evening): the 41x36
    sprite drawn 1:1 at 2160p with its origin 33 px left of the first fill
    column (x=424 since the bars moved +32) and 6 rows above each fill window's top (154/188/222).
    Expressed normalised so a 1080p frame gets the same placement at half
    size. dx/dy/scale are pixel nudges at 2160p for experiments only.
    """
    h, w = frame.shape[:2]
    out = frame.astype(float).copy()
    f = h / 2160.0
    cw, ch = max(1, int(round(41 * f * scale))), max(1, int(round(36 * f * scale)))
    piece = np.asarray(cap.resize((cw, ch), Image.LANCZOS)).astype(float)
    for name, top in (("hp", 148), ("fp", 182), ("sta", 216)):
        x0 = int(round((391 + dx) * f))   # 359 before the +32 bar shift
        y0 = int(round((top + dy) * f))
        x1, y1 = x0 + cw, y0 + ch
        sx0, sy0 = max(0, -x0), max(0, -y0)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        if x1 <= x0 or y1 <= y0:
            continue
        p = piece[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
        a = p[..., 3:4] / 255.0
        out[y0:y1, x0:x1] = out[y0:y1, x0:x1] * (1 - a) + p[..., :3] * a
        print(f"  {name:8s} cap {cw}x{ch} at ({x0},{y0})")
    return np.clip(out, 0, 255).astype(np.uint8)


# Elden Ring's measured truth, all from 4K grabs of the live game.
ER_TRUTH = {
    "HP fill":   (94, 26, 22),
    "FP fill":   (28, 68, 85),
    "STA fill":  (28, 69, 45),
    "rail":      (145, 139, 108),
    "rune slot": (25, 32, 26),
}
# ER's cap, measured with the SAME detector this tool uses on our frames.
# An earlier figure of 56x29 came from a tighter crop that clipped ER's own
# ornament, and comparing it against our full measurement made the cap look
# 1.4x oversized when it was not. Measure both sides the same way or do not
# compare them at all.
ER_CAP_PX = (75, 40)
ER_CAP_RIGHT_OF_BAR = 29        # px at 4K, cap's right edge past the fill start


def _lab(rgb):
    c = np.array(rgb, float) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]])
    xyz = m @ c / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def _de(a, b):
    return float(np.linalg.norm(_lab(a) - _lab(b)))


def measure(frame: np.ndarray) -> None:
    """Report every element against ER in one pass."""
    h, w = frame.shape[:2]
    a = frame.astype(int)

    # Find each bar by hue rather than by fixed coordinates, so this works on
    # a harness capture and on a TV grab where the window is offset.
    tests = {
        "HP fill":  lambda p: (p[..., 0] > 55) & (p[..., 0] > p[..., 1] * 1.6) & (p[..., 0] > p[..., 2] * 1.6),
        "FP fill":  lambda p: (p[..., 2] > 55) & (p[..., 2] > p[..., 0] * 1.5) & (p[..., 2] > p[..., 1] * 1.1),
        "STA fill": lambda p: (p[..., 1] > 50) & (p[..., 1] > p[..., 0] * 1.3) & (p[..., 1] > p[..., 2] * 1.2),
    }
    print(f"frame {w}x{h}")
    print(f"{'element':10s} {'measured':>18} {'Elden Ring':>16} {'deltaE':>7}")
    # Restrict to the HUD strip. Searching the top 30% of the frame found the
    # SKY for FP - it is blue-dominant and far larger than the bar, so the
    # longest-run logic legitimately picked it. The gauges live above y=0.16
    # and left of x=0.55, and are DARK, so a brightness ceiling separates them
    # from any lit scenery that shares their hue.
    top = a[: int(h * 0.16), : int(w * 0.55)]
    top = np.where((top.max(axis=2, keepdims=True) > 150), 0, top)
    for name, f in tests.items():
        m = f(top)
        def longest_run(mask):
            best = cur = None
            for i, v in enumerate(np.append(mask, False)):
                if v and cur is None:
                    cur = i
                elif not v and cur is not None:
                    if best is None or (i - cur) > (best[1] - best[0]):
                        best = (cur, i)
                    cur = None
            return best

        rowmask = m.sum(axis=1) > max(20, w // 120)
        rr = longest_run(rowmask)
        if rr is None:
            print(f"{name:10s} {'not found':>18}")
            continue
        rows = np.arange(rr[0], rr[1])
        # Take the LONGEST CONTIGUOUS run of matching columns, not min..max.
        # Stray matches elsewhere in the frame stretch min..max across the
        # whole screen, and the sample then lands on scenery: that is how FP
        # first measured (53,54,57) grey at deltaE 15.5 when the bar itself was
        # fine. Every false reading on this project has been this same mistake.
        colmask = m[rows.min():rows.max() + 1].sum(axis=0) > 2
        best = longest_run(colmask)
        if best is None:
            print(f"{name:10s} {'no contiguous run':>18}")
            continue
        c0, c1 = best
        # Start a fifth of the way in, not a twelfth: the ER end-cap now
        # overhangs the bar's left and its bone colour lifted FP's red from 34
        # to 42, making the shader look like it had made things worse when it
        # had not. Sample past the ornament.
        x0 = c0 + max(10, (c1 - c0) // 5)
        x1 = c0 + (c1 - c0) * 2 // 3
        # Sample only the FLAT fill: the top half of the hue-matched rows.
        # At native 4K the bevel rows (+12..+17) also pass the hue test and
        # they are deliberately brighter (ER's are too), so averaging them
        # in reported HP at dE 3.15 when every row matched ER within 0.8.
        # Row-by-row truth is hud_rows.py; this is the one-number summary.
        y0 = rows.min() + 1
        y1 = rows.min() + max(3, (rows.max() - rows.min()) // 2)
        if x1 <= x0 or y1 <= y0:
            print(f"{name:10s} {'too small to sample':>18}")
            continue
        got = tuple(top[y0:y1, x0:x1].reshape(-1, 3).mean(axis=0).round().astype(int))
        er = ER_TRUTH[name]
        print(f"{name:10s} {str(got):>18} {str(er):>16} {_de(got, er):7.2f}")

    # The cap: bone-coloured pixels immediately left of the HP bar's start.
    m = tests["HP fill"](top)
    rows = np.where(m.sum(axis=1) > max(20, w // 120))[0]
    if len(rows):
        cols = np.where(m[rows.min():rows.max() + 1].sum(axis=0) > 2)[0]
        bx, by = cols.min(), rows.min()
        # Look LEFT of the bar's start, not right. Extending 60 px to the
        # right caught the bone RAIL that runs under the bar, so the "cap"
        # measured 64 px wide no matter what the cap actually was - including
        # across a resize that changed nothing in the number.
        # Box must be comfortably bigger than the thing measured: at 48 px
        # tall it returned exactly 48, i.e. it was clipping and reporting its
        # own bounds as the cap's height.
        box = top[max(0, by - 34):by + 60, max(0, bx - 70):bx + 8]
        bone = ((box[..., 0] > 95) & (box[..., 0] > box[..., 2] + 20)
                & (box[..., 1] > box[..., 2] + 6))
        if bone.sum() > 20:
            ys, xs = np.where(bone)
            cw, ch = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
            print("")
            print(f"cap footprint {cw}x{ch} px   Elden Ring "
                  f"{ER_CAP_PX[0]}x{ER_CAP_PX[1]}   "
                  f"({cw / ER_CAP_PX[0]:.2f}x wide, {ch / ER_CAP_PX[1]:.2f}x tall)")
        else:
            print("")
            print("cap: no bone pixels found beside the bar")


def compare(frame: np.ndarray, out_path: Path) -> None:
    h, w = frame.shape[:2]
    y0 = int(BARS["hp"]["y0"] * h) - 4
    y1 = int(BARS["hp"]["y1"] * h) + 10
    ours = Image.fromarray(frame[y0:y1, int(BAR_LEFT * w) - 30:int(BAR_LEFT * w) + 520])
    er = Image.open(REF / "hud_full.png").convert("RGB").crop((280, 88, 1350, 126))
    W, H, Z, pad = 520, 26, 3, 12
    er = er.resize((W, H), Image.LANCZOS)
    ours = ours.resize((W, H), Image.LANCZOS)
    c = Image.new("RGB", (W * Z, (H * Z + pad) * 2 + pad), (18, 18, 18))
    c.paste(er.resize((W * Z, H * Z), Image.LANCZOS), (0, pad))
    c.paste(ours.resize((W * Z, H * Z), Image.LANCZOS), (0, pad * 2 + H * Z))
    c.save(out_path)
    print(f"  wrote {out_path}  (top ER, bottom ours)")


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(1)
    mode, argv = argv[0], argv[1:]

    def flag(name, default, cast=float):
        if name in argv:
            i = argv.index(name)
            v = cast(argv[i + 1])
            del argv[i:i + 2]
            return v
        return default

    dx = flag("--dx", 0, int)
    dy = flag("--dy", 0, int)
    scale = flag("--scale", 1.0, float)

    if mode == "shader":
        frame = np.asarray(Image.open(argv[0]).convert("RGB"))
        Image.fromarray(apply_shader(frame)).save(argv[1])
        print(f"  wrote {argv[1]}")
    elif mode == "overlay":
        frame = np.asarray(Image.open(argv[0]).convert("RGB"))
        cap = Image.open(argv[1]).convert("RGBA")
        Image.fromarray(apply_overlay(frame, cap, dx, dy, scale)).save(argv[2])
        print(f"  wrote {argv[2]}")
    elif mode == "measure":
        measure(np.asarray(Image.open(argv[0]).convert("RGB")))
    elif mode == "compare":
        compare(np.asarray(Image.open(argv[0]).convert("RGB")), Path(argv[1]))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
