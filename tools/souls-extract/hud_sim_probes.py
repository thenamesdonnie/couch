"""Probe builds that pin down the parts of hud_sim's model that are still fitted.

Each probe writes a `01_common.tpf.dcx` you deploy and shoot AS A BATCH -
nothing here launches the game. Every probe keeps the on-screen HP band
red-dominant and stamina green-dominant so ds3-shot's `wait_probe hud` still
fires (the grey-impulse lesson: a probe that breaks the probe reads a stale
frame).

    python hud_sim_probes.py build <base.tpf.dcx> <out.tpf.dcx> --probe X
    python hud_sim_probes.py read-X <capture.png>

Then, per probe:

    ramp     WHAT: 16-step per-channel ramps - HP block ramps RED (g=b=0),
             stamina ramps GREEN, FP ramps BLUE, 32 texels per step.
             ANSWERS: the full atlas->screen transfer curve per channel in one
             run (the gamma 0.87 was fitted on three dark points only; the
             vanilla calibration pair shows a +4.5 dark-end lift on dim
             channels that the gamma misses - likely a PARENT cxform above the
             HP/MP/SP placements that er_fe_gfx.py does not touch). Also nails
             the horizontal origin and scale: the step edges land at known
             texel columns.
             RUN: deploy, shoot 1080p (`DS3SHOT_FAST=1 tools/ds3-shot`), then
                  `hud_sim_probes.py read-ramp shots/ingame.png`.

    impulse  WHAT: flat dominant-channel background (60) with one bright texel
             ROW (255) at window row 6-of-24 (scale 2) and one bright texel
             COLUMN at texel 256, per bar.
             ANSWERS: (a) vertical PSF; (b) horizontal PSF; (c) the resample
             phase when the atlas scale does not match the render scale (s > f
             - which screen row the impulse lands in tells whether pairs are
             (0,1) or (1,2), SAMPLE_PHASE). At the live setting (s=2, 4K) the
             mapping is 1:1 and there is nothing left for it to measure: the
             impulse should come back as ONE screen row, unblurred.
             RUN: shoot 1080p and 4K (DS3SHOT_W=3840 DS3SHOT_H=2160) and
                  read-impulse each. The pair separates the atlas-vs-render
                  ratio from anything the display path might add.

    checker  WHAT: FP block filled with a 1-texel blue checkerboard (40/80);
             HP and stamina left as the base build's fills.
             ANSWERS: the internal render resolution. RESULT, 2 Sep 2026 at
             3840x2160 fullscreen: it did NOT dissolve. It came back as a
             perfect 50/92 alternation in both axes, one screen pixel per
             texel, so the game renders NATIVE 4K and the old "renders 1080p,
             gamescope upscales" model was an artefact of the sandbox being
             configured WINDOW 1920x1080. Capture kept at
             `data/ds3-shot/shots/probe_checker_4k_native.png`. It doubles as
             a transfer probe: 40 -> 50 and 80 -> 92 are two exact points, and
             both invert to gamma 0.8795 (not the 0.87 hud_sim still uses).
             RUN: shoot at DS3SHOT_W=3840, `read-checker shots/ingame.png`.

Readers print measurements and a verdict against the model's prediction.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image

from hud_sim import (BLOCKS, WIN0, WIN1, FILL_X, FILL_Y, N_GAME_ROWS,
                     find_fill_extent, load_atlas)

SCALE = 2                       # build probes at the current stack's scale
ATLAS_W = 256 * SCALE
RAMP_STEPS = 16
RAMP_COLS = ATLAS_W // RAMP_STEPS
IMPULSE_ROW = 6                 # scale-2 texel row inside the 48-row window... see build
IMPULSE_COL = 256               # scale-2 texel column of the bright column
CHECKER_LO, CHECKER_HI = 40, 80

BAR_CH = {"hp": 0, "st": 1, "fp": 2}        # dominant channel per bar


def _blocks_scaled():
    return {b: BLOCKS[b] * SCALE for b in ("hp", "st", "fp")}


def build(base: Path, out: Path, probe: str) -> None:
    from oodle import dcx_decompress, dcx_compress_dflt
    from tpf_png import decode
    from soulstruct.containers import TPF
    from build_glyph_mod import dds_bgra

    tpf = TPF.from_bytes(dcx_decompress(base.read_bytes()))
    tex = [t for t in tpf.textures if t.stem == "MENU_PlayerHUD2"][0]
    img = decode(tex.data).convert("RGBA").resize((ATLAS_W, ATLAS_W), Image.LANCZOS)
    atlas = np.asarray(img).copy()

    w0, w1 = WIN0 * SCALE, WIN1 * SCALE
    for bar, top in _blocks_scaled().items():
        ch = BAR_CH[bar]
        block = atlas[top + w0: top + w1]           # the drawn window only
        if probe == "ramp":
            block[..., :3] = 0
            for step in range(RAMP_STEPS):
                v = 8 + step * 16                   # 8, 24, ... 248
                block[:, step * RAMP_COLS:(step + 1) * RAMP_COLS, ch] = v
            block[..., 3] = 255
        elif probe == "impulse":
            block[..., :3] = 0
            block[..., ch] = 60
            block[IMPULSE_ROW * SCALE: IMPULSE_ROW * SCALE + 1, :, ch] = 255
            block[:, IMPULSE_COL: IMPULSE_COL + 1, ch] = 255
            block[..., 3] = 255
        elif probe == "checker":
            if bar != "fp":
                continue                            # leave hp/st for the probe
            yy, xx = np.mgrid[0:block.shape[0], 0:block.shape[1]]
            block[..., :3] = 0
            block[..., 2] = np.where((yy + xx) % 2 == 0, CHECKER_LO, CHECKER_HI)
            block[..., 3] = 255
        else:
            raise SystemExit(f"unknown probe {probe}")
        atlas[top + w0: top + w1] = block
        # clamp-extend into the never-drawn rows, as the graft does
        atlas[top: top + w0] = atlas[top + w0]
        atlas[top + w1: top + 24 * SCALE] = atlas[top + w1 - 1]

    tex.data = dds_bgra(Image.fromarray(atlas, "RGBA"))
    tex.format = 9
    dcx = dcx_compress_dflt(tpf.to_bytes())
    rt = TPF.from_bytes(dcx_decompress(dcx))
    if len(rt.textures) != len(tpf.textures):
        raise SystemExit("texture count changed during repack")
    out.write_bytes(dcx)
    print(f"wrote {out} ({len(dcx):,} bytes) - probe '{probe}' at atlas scale {SCALE}")
    print("deploy:  cp", out, "~/couch/data/ds3-shot/game/mod/menu/01_common.tpf.dcx")


# ------------------------------------------------------------------- readers
def _cap(path: str) -> tuple[np.ndarray, int]:
    cap = np.asarray(Image.open(path).convert("RGB")).astype(float)
    f = cap.shape[0] // 1080
    if cap.shape[0] not in (1080, 2160):
        raise SystemExit(f"capture height {cap.shape[0]} unsupported")
    return cap, f


def read_ramp(path: str) -> None:
    cap, f = _cap(path)
    print(f"capture {cap.shape[1]}x{cap.shape[0]}")
    print("atlas value -> screen value per channel (sampled mid-fill, one row "
          "per 32-texel step; last steps missing on short bars):")
    for bar in ("hp", "fp", "st"):
        ch = BAR_CH[bar]
        y0 = FILL_Y[bar] * f
        rows = N_GAME_ROWS * f
        pts = []
        for step in range(RAMP_STEPS):
            # step spans texels [step*64, step*64+64) at s=2 = game px /2
            x_lo = FILL_X * f + (step * RAMP_COLS // SCALE + 4) * f
            x_hi = FILL_X * f + ((step + 1) * RAMP_COLS // SCALE - 4) * f
            if x_hi * 1.0 > FILL_X * f + 250 * f:   # off the end of the bar
                break
            band = cap[y0 + rows // 3: y0 + 2 * rows // 3, x_lo:x_hi, ch]
            pts.append((8 + step * 16, float(np.median(band))))
        print(f"  {bar} ({'RGB'[ch]}): " + "  ".join(f"{a}->{s:.0f}" for a, s in pts))
        print("      (short bars truncate the ramp: ignore any flat tail - it "
              "is the trough, not a step)")
        if len(pts) > 3:
            a = np.array([p[0] for p in pts], float)
            s = np.array([p[1] for p in pts], float)
            best = None
            for g in np.arange(0.6, 1.2, 0.005):
                x = 255.0 * (a / 255.0) ** g
                A = np.stack([x, np.ones_like(x)], 1)
                coef, *_ = np.linalg.lstsq(A, s, rcond=None)
                e = np.abs(A @ coef - s).mean()
                if best is None or e < best[3]:
                    best = (g, coef[0], coef[1], e)
            print(f"      fit: screen = {best[1]:.3f} * 255*(a/255)^{best[0]:.3f} "
                  f"{best[2]:+.1f}   (meanabs {best[3]:.2f})")


def read_impulse(path: str) -> None:
    cap, f = _cap(path)
    print(f"capture {cap.shape[1]}x{cap.shape[0]}")
    for bar in ("hp", "fp", "st"):
        ch = BAR_CH[bar]
        y0, rows = FILL_Y[bar] * f, N_GAME_ROWS * f
        x0 = FILL_X * f
        # vertical PSF: column profile away from the bright column
        prof = cap[y0 - 2 * f: y0 + rows + 2 * f, x0 + 40 * f: x0 + 100 * f, ch].mean(axis=1)
        base = np.median(prof)
        peak = prof.max()
        resp = np.clip(prof - base, 0, None)
        resp = resp / max(resp.sum(), 1e-6)
        hot = np.where(resp > 0.04)[0]
        print(f"  {bar} vertical: rows {list(hot)} weights "
              f"{[round(float(resp[i]), 3) for i in hot]} (base {base:.0f} peak {peak:.0f})")
        # horizontal PSF around the bright column (texel 256 -> game px 128)
        px = x0 + (IMPULSE_COL // SCALE) * f
        row = cap[y0 + rows // 3: y0 + 2 * rows // 3, px - 4 * f: px + 5 * f, ch].mean(axis=0)
        print(f"  {bar} horizontal, px {px-4*f}..{px+4*f}: {row.round(1)}")
    print(f"\nmodel says, for a scale-{SCALE} atlas at this capture size "
          f"(render scale f={f}):")
    if SCALE == f:
        print("  1:1 - the impulse is ONE screen row and ONE screen column,")
        print("  full amplitude, no spread in either axis.")
    elif SCALE > f:
        print(f"  {SCALE}:{f} minification - the impulse is averaged into a")
        print("  pair, so it lands at ~half amplitude across 1 screen row")
        print("  (which row of the pair tells you SAMPLE_PHASE).")
    else:
        print(f"  {f}:{SCALE} magnification - bilinear spread over 2 rows and")
        print("  2 columns. UNMEASURED regime, treat the result as new data.")


def read_checker(path: str) -> None:
    cap, f = _cap(path)
    y0, rows = FILL_Y["fp"] * f, N_GAME_ROWS * f
    x0 = FILL_X * f
    band = cap[y0 + 2 * f: y0 + rows - 2 * f, x0 + 20 * f: x0 + 140 * f, 2]
    # Measure the alternation ITSELF, per row and per column. The old reader
    # averaged each column down to one number first, which cancels a
    # checkerboard exactly (every column holds equal counts of lo and hi) and
    # so reported "delta 0.00" on the native capture that in fact showed a
    # perfect 50/92 alternation. Never collapse an axis before differencing it.
    d_x = float(np.abs(np.diff(band, axis=1)).mean())      # along each row
    d_y = float(np.abs(np.diff(band, axis=0)).mean())      # down each column
    lo, hi = np.percentile(band, [10, 90])
    print(f"capture {cap.shape[1]}x{cap.shape[0]}: FP band blue mean "
          f"{band.mean():.1f} p10/p90 {lo:.0f}/{hi:.0f}")
    print(f"  mean |neighbour delta|: horizontal {d_x:.2f}  vertical {d_y:.2f}")
    print(f"  (the collapsed-column figure the old reader printed: "
          f"{np.abs(np.diff(band.mean(axis=0))).mean():.2f} - it lies, see source)")
    alt = min(d_x, d_y)
    if alt > 15:
        print("verdict: NATIVE. Both axes alternate one screen pixel per texel,")
        print("so the game renders at the capture resolution and nothing")
        print("filters the HUD. This is what the 2 Sep 4K run measured (50/92,")
        print("atlas 40/80), and it is why hud_sim no longer models an upscale.")
    elif alt < 1.5:
        print("verdict: checker DISSOLVED - the texels are being averaged in")
        print("pairs, so the render is half the capture resolution (or the")
        print("atlas is scale 4). Check GraphicsConfig.xml before believing it.")
    else:
        print(f"verdict: UNCLEAR, partial alternation ({alt:.2f}). Something is")
        print("filtering but not fully averaging - suspect a non-integer scale.")


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(1)
    mode, argv = argv[0], argv[1:]
    if mode == "build":
        probe = "ramp"
        if "--probe" in argv:
            i = argv.index("--probe")
            probe = argv[i + 1]
            del argv[i:i + 2]
        build(Path(argv[0]), Path(argv[1]), probe)
    elif mode == "read-ramp":
        read_ramp(argv[0])
    elif mode == "read-impulse":
        read_impulse(argv[0])
    elif mode == "read-checker":
        read_checker(argv[0])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
