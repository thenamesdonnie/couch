"""Offline renderer for the DS3 HUD bars: predict the screen from the atlas.

WHY. Every texture iteration costs a ~77s game launch. Both stages of the
pipeline are measured, so the on-screen fill pixels are PREDICTABLE from the
built `01_common.tpf.dcx` alone. Predict, compare against the last real
capture, and only spend a launch when the simulator says the build is right.

    hud_sim.py predict  <tpf.dcx> [-o strip.png] [--res 1080|2160] [--cxform C]
    hud_sim.py validate <tpf.dcx> <capture.png> [--cxform C] [--fit] [--dump d.png]

Both accept `--upscaled-1080p` for old captures; see point 5.

`--cxform` is `neutral` (the modded stack, default), `vanilla` (mult 230/256
add +26, the transform er_fe_gfx.py removes), or `M,A` literal floats.

CORRECTION, 2 Sep 2026. This file used to assert "THE GAME RENDERS AT 1920x1080
INTERNALLY, whatever the capture size", and modelled every 4K capture as a
1080p frame blown up 2x by gamescope's bilinear blit. That was an artefact of
the SANDBOX: its GraphicsConfig.xml said WINDOW 1920x1080, so the game really
was rendering 1080p there and gamescope really was upscaling. The evidence
(fractional drawn-row readbacks, a 2.03 rows-per-atlas-row slope, a symmetric
3-tap "blur" PSF) was all downstream of that one setting, not of the engine.
With the sandbox switched to FULLSCREEN 3840x2160, matching the real install, a
checkerboard probe settled it: the game renders NATIVE. See point 1.

THE MODEL, and where each piece was measured:

1. THE GAME RENDERS AT THE CAPTURE RESOLUTION. Measured 2 Sep with the
   `checker` probe (hud_sim_probes.py): a 1-texel blue checkerboard, atlas
   40/80, in the FP block of a scale-2 (512x512) atlas, shot at 3840x2160.
   It came back as a perfect 50/92 alternation in BOTH axes, one screen pixel
   per texel, no blur and no filtering of any kind. So there is no upscaler in
   the path and no engine-side blur: `probe_checker_4k_native.png`, FP screen
   rows 188..211, first row starts 50 at x=384 (texel column 0).
   Let f = capture_height/1080. Everything below scales by f.

2. FILL WINDOW. Each 24-base-row fill block draws only base rows 6..18
   (measured with a 24-level grey ramp), onto 12*f screen rows: 12 at 1080p,
   24 at 2160p (measured, FP rows 188..211 inclusive).
   Atlas scale s (atlas_height/256) puts 12*s texel rows into those 12*f
   screen rows, so the GPU's job is s/f texels per pixel:
     s == f  1:1, no filtering at all (the current stack: s=2 at 4K)
     s > f   minification, area average, with a possible one-texel phase (see
             SAMPLE_PHASE in er_hud_graft.py; validate tries both and reports
             which fits). s=2 at 1080p is the 2:1 pair average.
     s < f   magnification, bilinear. MODELLED, NOT MEASURED - we have never
             shot a build in this regime.

3. HORIZONTAL: fixed scale from the bar's left, NOT stretched to bar length.
   One base texel = f screen pixels; a bar shorter than 256*f px truncates the
   texture, a longer one runs out (the tail past 256*f px is the engine's
   separate end-cap sprite, not fill). Verified on the vanilla pair by grain
   correlation: 0.9994 at width 256 vs 0.976 at +-3 px. Fill origin measured
   at game x=192, i.e. screen x=192*f (the 0.10182 normalised figure is 3 px
   right of the true origin - it was measured off hue, which misses the fill's
   dark first columns). Confirmed at 4K: texel column 0 lands on x=384.

4. TRANSFER, per channel: screen = mult * 255*(atlas/255)^0.87 + add, with
   (mult, add) the Scaleform colour transform (neutralised in the modded
   stack). Gamma is applied after the GPU's texel filtering (order only
   matters when the GPU resamples at all, s != f; validate tries both, and
   says "no free parameters" when neither applies). Sanity: gamma 0.87 with
   vanilla's cxform (230/256, +26) reproduces the OLD measured linear fit
   0.87x+38 within ~1.5 units across the range - the two historical
   measurements agree with each other through this model.

5. LEGACY, opt-in only: `--upscaled-1080p` restores the old path, where the
   game renders 1080p and gamescope blits it 2x with bilinear taps
   [0.75,0.25]/[0.25,0.75]. It applies to captures taken before 2 Sep 2026
   evening, when the sandbox's GraphicsConfig.xml still said WINDOW 1920x1080
   while ds3-shot asked for a 4K grab. Never use it on a fullscreen-4K
   capture; it is kept only so the old shots stay readable.

ACCURACY. Best matched pair, and the one that matters (s=2 atlas
`01_common_probe_checker.tpf.dcx` + native 4K `probe_checker_4k_native.png`,
2 Sep): overall mean abs error 0.76/channel - hp 0.93, fp 0.32, st 1.04 - with
ZERO free parameters. All three bars align at dy=0 dx=0 against FILL_X*f and
FILL_Y*f, which is itself a check on the geometry: nothing was fitted to make
that happen. The earlier 1080p vanilla pair scored 1.83/channel with a
structured error (dominant channel within ~1, dim channels up to ~4.5 too
dark, --fit residual 0.35 at actual = 0.94*pred + 6.7), all of which was the
s=2-at-1080p minification and cxform guesswork; at 1:1 it is gone.

The 0.76 that remains is ONE-SIDED - the prediction is uniformly ~1 unit HIGH,
never low - and the checker says why. Its two exact points, atlas 40 -> screen
50 and atlas 80 -> screen 92, both invert to gamma 0.8795, and 0.87 is outside
the round-to-nearest bracket either point allows ((0.8742, 0.8850) and
(0.8748, 0.8841)). A global refit over all three bars agrees: 0.8795, mean abs
0.17 versus 0.83 at 0.87. GAMMA is paired with er_hud_bars.SCREEN_GAMMA, which
the graft uses to INVERT this transfer, and moving one without the other
breaks the round trip. Both moved from 0.87 to 0.8795 together on 3 Sep 2026
(the flat fill rows had been rendering about one unit under ER's).

KNOWN LIMITS: predicts the fill window only (the drawn rows), not the backdrop
rows above/below; ignores the vkBasalt cap overlay and the bar's own left
end-cap sprite (which is what covers screen x=384..391 at 4K - excluded from
comparison via --exclude-left); at s > f the minification phase and the
gamma-vs-filter order are still fitted, not measured, and the s < f
magnification filter is a guess.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image

GAMMA = 0.8795      # 3 Sep 2026: moved from 0.87 TOGETHER with er_hud_bars.SCREEN_GAMMA (see the header)
VANILLA_CX = (230.0 / 256.0, 26.0)

# base-256 atlas row of each fill block top; window = rows 6..18 inside it
BLOCKS = {"hp": 28, "st": 52, "fp": 76, "lag": 100}
WIN0, WIN1 = 6, 18
N_GAME_ROWS = 12                # the window's height in screen pixels at 1080p
N_GAME_COLS = 256               # full fill width in screen pixels at 1080p

# Fill geometry at 1080p, calibrated on the vanilla pair 2 Sep 2026 by
# alignment search (dy fitted per bar, dx common at -3 from the hue-measured
# 0.10182 figure). Multiply by f = capture_height/1080; the fp figure was
# confirmed directly at 4K (94*2 = 188, 192*2 = 384).
FILL_X = 208                    # 192 until 2 Sep evening: er_fe_gfx.py --shift-bars 16
FILL_Y = {"hp": 77, "fp": 94, "st": 111}

# The 3-tap PSF once fitted to 4K captures, back when those were upscaled.
PSF3 = np.array([0.277, 0.446, 0.277])


# --------------------------------------------------------------- atlas access
def load_atlas(dcx_path: Path) -> np.ndarray:
    from oodle import dcx_decompress
    from tpf_png import decode
    from soulstruct.containers import TPF

    tpf = TPF.from_bytes(dcx_decompress(Path(dcx_path).read_bytes()))
    tex = [t for t in tpf.textures if t.stem == "MENU_PlayerHUD2"]
    if not tex:
        raise SystemExit("no MENU_PlayerHUD2 in this TPF")
    a = np.asarray(decode(tex[0].data)).astype(float)
    if a.shape[0] % 256:
        raise SystemExit(f"atlas height {a.shape[0]} is not a multiple of 256")
    return a


def window(atlas: np.ndarray, bar: str) -> tuple[np.ndarray, int]:
    s = atlas.shape[0] // 256
    top = BLOCKS[bar] * s
    return atlas[top + WIN0 * s: top + WIN1 * s], s


# -------------------------------------------------------------- forward model
def to_screen(t: np.ndarray, cxform: tuple[float, float]) -> np.ndarray:
    g = 255.0 * np.clip(t / 255.0, 0, 1) ** GAMMA
    return np.clip(g * cxform[0] + cxform[1], 0, 255)


def box_resample(img: np.ndarray, n_out: int, phase: float = 0.0) -> np.ndarray:
    """Area-average rows of `img` down to n_out rows, offset by `phase` texels."""
    n = img.shape[0]
    if n == n_out and phase == 0.0:
        return img.copy()
    edges = np.linspace(phase, n + phase, n_out + 1)
    out = np.zeros((n_out,) + img.shape[1:], float)
    for j in range(n_out):
        a, b = edges[j], edges[j + 1]
        acc = np.zeros(img.shape[1:], float)
        for i in range(int(np.floor(a)), int(np.ceil(b))):
            w = min(b, i + 1) - max(a, i)
            if w > 0:
                acc += img[int(np.clip(i, 0, n - 1))] * w
        out[j] = acc / (b - a)
    return out


def bilinear_resample(img: np.ndarray, n_out: int, phase: float = 0.0) -> np.ndarray:
    """Magnify rows of `img` to n_out with GPU-style bilinear texel sampling.

    Output pixel j samples texel coordinate (j+0.5)*n/n_out - 0.5 (+phase),
    which for n_out == 2n gives exactly the 0.75/0.25 taps of a 2x blit.
    UNMEASURED for the HUD - we have never shot an atlas smaller than the
    render (s < f). Point sampling would give hard doubled rows instead.
    """
    n = img.shape[0]
    u = (np.arange(n_out) + 0.5) * n / n_out - 0.5 + phase
    i0 = np.clip(np.floor(u).astype(int), 0, n - 1)
    i1 = np.clip(i0 + 1, 0, n - 1)
    w = (u - np.floor(u)).reshape((-1,) + (1,) * (img.ndim - 1))
    return img[i0] * (1 - w) + img[i1] * w


def resample_axis(img: np.ndarray, n_out: int, phase: float = 0.0) -> np.ndarray:
    """Map axis 0 of `img` onto n_out screen pixels the way the GPU would."""
    n = img.shape[0]
    if n == n_out and phase == 0.0:
        return img.copy()
    if n > n_out:
        return box_resample(img, n_out, phase)      # minification: area average
    return bilinear_resample(img, n_out, phase)     # magnification: bilinear


def upscale2x(img: np.ndarray) -> np.ndarray:
    """LEGACY. gamescope's 2x bilinear blit, both axes: taps 0.75/0.25.

    Only applies to pre-2 Sep 2026 4K captures taken while the sandbox was
    still configured WINDOW 1920x1080. See point 5 of the module docstring.
    """
    def up1(a):                                   # along axis 0
        p = np.pad(a, ((1, 1),) + ((0, 0),) * (a.ndim - 1), mode="edge")
        out = np.empty((a.shape[0] * 2,) + a.shape[1:], float)
        out[0::2] = 0.25 * p[:-2] + 0.75 * p[1:-1]
        out[1::2] = 0.75 * p[1:-1] + 0.25 * p[2:]
        return out
    return np.swapaxes(up1(np.swapaxes(up1(img), 0, 1)), 0, 1)


def predict_bar(atlas: np.ndarray, bar: str, cxform=(1.0, 0.0),
                phase: float = 0.0, gamma_first: bool = True,
                f: int = 1) -> np.ndarray:
    """-> (12f, 256f, 3) predicted SCREEN image of one bar's fill window.

    `f` is the render/capture scale over 1080p, so f=2 is a native 4K frame.
    """
    win, s = window(atlas, bar)
    rgb = win[..., :3]
    if gamma_first:
        scr = to_screen(rgb, cxform)
    else:
        scr = rgb
    scr = resample_axis(scr, N_GAME_ROWS * f, phase)                    # vertical
    scr = np.swapaxes(resample_axis(np.swapaxes(scr, 0, 1),             # horizontal
                                    N_GAME_COLS * f, phase), 0, 1)
    if not gamma_first:
        scr = to_screen(scr, cxform)
    return scr


def filters_apply(s: int, f: int) -> bool:
    """True when the GPU resamples at all, i.e. when phase/gamma order matter."""
    return s != f


# ------------------------------------------------------------------- captures
def find_fill_extent(cap: np.ndarray, bar: str, y0: int, rows: int):
    """(x_start, x_end) of the longest contiguous run of fill-coloured columns."""
    band = cap[y0 + rows // 4: y0 + (3 * rows) // 4]
    r, g, b = band[..., 0], band[..., 1], band[..., 2]
    if bar == "hp":
        m = (r > 40) & (r > g * 1.4) & (r > b * 1.4)
    elif bar == "fp":
        m = (b > 45) & (b - r > 25) & (b - g > 10)
    else:
        m = (g > 45) & (g - b > 10) & (g > r * 1.1)
    hits = m.sum(axis=0) > max(1, band.shape[0] // 3)
    best = cur = None
    for i, v in enumerate(np.append(hits, False)):
        if v and cur is None:
            cur = i
        elif not v and cur is not None:
            if best is None or i - cur > best[1] - best[0]:
                best = (cur, i)
            cur = None
    return best


# ----------------------------------------------------------------------- modes
def parse_cxform(v: str) -> tuple[float, float]:
    if v == "neutral":
        return (1.0, 0.0)
    if v == "vanilla":
        return VANILLA_CX
    m, a = v.split(",")
    return (float(m), float(a))


def mode_predict(argv: list[str]) -> None:
    dcx = Path(argv[0])
    out = Path(_flag(argv, "-o", f"{dcx.stem}_predicted.png", str))
    res = _flag(argv, "--res", 1080, int)
    legacy = _pop(argv, "--upscaled-1080p")
    cx = parse_cxform(_flag(argv, "--cxform", "neutral", str))
    if res not in (1080, 2160):
        raise SystemExit("--res must be 1080 or 2160")
    f = res // 1080
    atlas = load_atlas(dcx)
    strips, pad = [], 4
    for bar in ("hp", "fp", "st"):
        # Legacy path renders 1080p and lets gamescope blow it up; the live
        # path renders straight at the capture resolution.
        p = predict_bar(atlas, bar, cx, f=1 if legacy else f)
        if legacy and f == 2:
            p = upscale2x(p)
        strips.append(np.clip(p, 0, 255).astype(np.uint8))
    w = max(s.shape[1] for s in strips)
    h = sum(s.shape[0] for s in strips) + pad * (len(strips) - 1)
    sheet = np.full((h, w, 3), 24, np.uint8)
    y = 0
    for s_ in strips:
        sheet[y:y + s_.shape[0], :s_.shape[1]] = s_
        y += s_.shape[0] + pad
    Image.fromarray(sheet).save(out)
    print(f"wrote {out}  (hp / fp / st fill windows, {res}p"
          f"{', legacy upscaled 1080p' if legacy else ' native'})")
    for bar, s_ in zip(("hp", "fp", "st"), strips):
        mid = s_[s_.shape[0] // 3: 2 * s_.shape[0] // 3, 40:246]
        m = mid.reshape(-1, 3).mean(axis=0)
        print(f"  {bar:3s} mid-fill mean ({m[0]:.1f}, {m[1]:.1f}, {m[2]:.1f})")


def mode_validate(argv: list[str]) -> None:
    dcx, cap_path = Path(argv[0]), Path(argv[1])
    cx = parse_cxform(_flag(argv, "--cxform", "neutral", str))
    do_fit = _pop(argv, "--fit")
    legacy = _pop(argv, "--upscaled-1080p")
    dump = _flag(argv, "--dump", None, str)
    excl_l = _flag(argv, "--exclude-left", 40, int)
    excl_r = _flag(argv, "--exclude-right", 10, int)

    atlas = load_atlas(dcx)
    cap = np.asarray(Image.open(cap_path).convert("RGB")).astype(float)
    H, W = cap.shape[:2]
    if H not in (1080, 2160):
        raise SystemExit(f"capture is {W}x{H}; only 1920x1080 and 3840x2160 handled")
    f = H // 1080
    s = atlas.shape[0] // 256
    # The game renders at the capture resolution, so the atlas is resampled by
    # s/f. `--upscaled-1080p` is the old path: render at f=1, blit up.
    render_f = 1 if legacy else f
    ratio = {True: "1:1", False: f"{s}:{render_f} "
             + ("minification" if s > render_f else "magnification")}[s == render_f]
    print(f"atlas {atlas.shape[1]}x{atlas.shape[0]} (scale {s}), capture {W}x{H}, "
          f"render {1920*render_f}x{1080*render_f}, texel:pixel {ratio}"
          + ("  [LEGACY gamescope 2x blit]" if legacy else ""))

    totals, dumps = [], []
    for bar in ("hp", "fp", "st"):
        y_def = FILL_Y[bar] * f
        rows = N_GAME_ROWS * f
        ext = find_fill_extent(cap, bar, y_def, rows)
        if ext is None:
            print(f"\n== {bar}: fill not found in capture, skipped")
            continue
        fill_px = min(ext[1] - ext[0], N_GAME_COLS * f)

        # Candidate models: resample phase and gamma-vs-filter order. Both are
        # meaningless when the GPU does not resample at all (s == render_f).
        filt = filters_apply(s, render_f) or legacy
        cands = []
        for ph in ((0.0, 1.0) if s > render_f else (0.0,)):
            for gf in ((True, False) if filt else (True,)):
                cands.append((ph, gf))
        best = None
        for ph, gf in cands:
            pred = predict_bar(atlas, bar, cx, ph, gf, f=render_f)
            if legacy and f == 2:
                pred = upscale2x(pred)
            pred = pred[:, :fill_px]
            # Search nearest offsets first: a periodic pattern (the checker)
            # ties across every offset that preserves its phase, and the
            # honest answer to a tie is dy=dx=0, not the corner of the search.
            for dy, dx in _offsets(4 * f):
                y0, x0 = y_def + dy, FILL_X * f + dx
                act = cap[y0:y0 + rows, x0:x0 + fill_px]
                if act.shape[:2] != pred.shape[:2]:
                    continue
                e = np.abs(pred[:, excl_l * f:-excl_r * f]
                           - act[:, excl_l * f:-excl_r * f]).mean()
                if best is None or e < best[0]:
                    best = (e, ph, gf, dy, dx, pred, act)
        e, ph, gf, dy, dx, pred, act = best
        tag = (f"phase={ph:.0f} gamma_{'first' if gf else 'last'}"
               if len(cands) > 1 else "1:1, no free parameters")
        print(f"\n== {bar}: fill {ext[0]}..{ext[0]+fill_px}px, model {tag}, "
              f"align dy={dy:+d} dx={dx:+d}")

        if do_fit:
            # Per-channel linear refit on top of the model (diagnostic).
            p = pred[:, excl_l * f:-excl_r * f].reshape(-1, 3)
            a_ = act[:, excl_l * f:-excl_r * f].reshape(-1, 3)
            for ch in range(3):
                A = np.stack([p[:, ch], np.ones(len(p))], 1)
                (m, c), *_ = np.linalg.lstsq(A, a_[:, ch], rcond=None)
                r = np.abs(A @ np.array([m, c]) - a_[:, ch]).mean()
                print(f"   fit {'RGB'[ch]}: actual = {m:.3f}*pred {c:+.1f}  "
                      f"(residual {r:.2f})")

        print(f"   {'row':>3} {'predicted':>19} {'actual':>19} {'|err|':>15}")
        for r_ in range(rows):
            pm = pred[r_, excl_l * f:-excl_r * f].mean(axis=0)
            am = act[r_, excl_l * f:-excl_r * f].mean(axis=0)
            d = np.abs(pred[r_, excl_l * f:-excl_r * f]
                       - act[r_, excl_l * f:-excl_r * f]).mean(axis=0)
            print(f"   {r_:3d} {str(pm.round(1)):>19} {str(am.round(1)):>19} "
                  f"{str(d.round(1)):>15}")
        per_ch = np.abs(pred[:, excl_l * f:-excl_r * f]
                        - act[:, excl_l * f:-excl_r * f]).mean(axis=(0, 1))
        print(f"   TOTAL mean abs error  R {per_ch[0]:.2f}  G {per_ch[1]:.2f}  "
              f"B {per_ch[2]:.2f}   (overall {per_ch.mean():.2f})")
        totals.append(per_ch)
        dumps.append((bar, pred, act))

    if totals:
        t = np.mean(totals, axis=0)
        print(f"\nALL BARS mean abs error  R {t[0]:.2f}  G {t[1]:.2f}  B {t[2]:.2f}"
              f"   (overall {t.mean():.2f})")
    if dump and dumps:
        pad = 6
        w = max(p.shape[1] for _, p, _ in dumps)
        h = sum(p.shape[0] * 2 + pad * 2 for _, p, _ in dumps)
        sheet = np.full((h, w, 3), 24, np.uint8)
        y = 0
        for bar, p, a_ in dumps:
            sheet[y:y + p.shape[0], :p.shape[1]] = np.clip(p, 0, 255).astype(np.uint8)
            y += p.shape[0] + 2
            sheet[y:y + a_.shape[0], :a_.shape[1]] = a_.astype(np.uint8)
            y += a_.shape[0] + pad * 2 - 2
        Image.fromarray(sheet).save(dump)
        print(f"wrote {dump}  (per bar: predicted over actual)")


# ------------------------------------------------------------------ arg utils
def _offsets(r: int):
    """(dy, dx) over [-r, r]^2, nearest first, so ties resolve to no shift."""
    return sorted(((dy, dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1)),
                  key=lambda o: (abs(o[0]) + abs(o[1]), abs(o[0]), o))


def _flag(argv, name, default, cast):
    if name in argv:
        i = argv.index(name)
        v = cast(argv[i + 1])
        del argv[i:i + 2]
        return v
    return default


def _pop(argv, name):
    if name in argv:
        argv.remove(name)
        return True
    return False


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(1)
    mode, argv = argv[0], argv[1:]
    if mode == "predict":
        mode_predict(argv)
    elif mode == "validate":
        mode_validate(argv)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
