"""Graft Elden Ring's ACTUAL bar pixels onto DS3's HUD atlas.

Donnie, on the synthesised version: "the new bar looks pretty bad. you are
comparing them side by side can you just cut a section of the elden ring bar
out and slap it on the ds3 asset?"

Yes, and it is the better idea. er_hud_bars.py reconstructed the fill from
statistics - a measured colour, a measured row profile, a baked grain asset
scaled to hit a target standard deviation. Every one of those steps was
faithful on its own and the stack of them still drifted: the grain came out
blotchy because a 13-row source was stretched to 24 and then amplitude-boosted
to fight the floor. This cuts the real pixels instead.

WHAT GETS CUT, all from 4K grabs of the live game:
    hp       hud_full.png            rows  95-107  (fill only, above the key-line)
    stamina  hud_full.png            rows 168-182
    fp       hud-combat-full.png     rows 132-144  (hud_full's FP bar is only
                                     151 px of fill; this frame has 389)
    lag      hud-damage-lag.png      rows  95-107, the yellow damage-lag segment
                                     sitting to the right of current HP
    keyline  hud_full.png            rows 116-119, the ruled bone line

SCALE. DS3's atlas is 256 px mapping 1:1 to screen at 1080p, so 512 columns of
a 4K grab, averaged down 2:1. Vertically ER's fill is 13 rows at 4K where DS3's
is 24 rows of atlas (12 on screen at 1080p, so 24 at 4K-equivalent) - DS3's bar
is ~1.85x the height, so the cut is stretched to fit. Stretching is free here
because the texture is vertical streaks; it smears along the grain, not across.

FP IS TILED. Only 389 columns of real FP fill exist in any frame and 512 are
needed, so it is MIRRORED and then cut. Mirroring rather than repeating avoids
a hard seam at the join.

COLOUR. The cut pixels are ER's final composited screen values, and DS3 will
put them through its own transfer (screen = 0.87 * atlas + 38 for the fill,
0.833 * atlas + 48 for the backdrop). So everything is inverse-compensated on
the way in. The clamp at zero is the known floor: ER's HP green (26) and blue
(22) are below 38 and cannot be reached, so they land at 38 and the bar reads
slightly greyer than ER's. The dominant channel, which carries the grain, is
unaffected.

    python er_hud_graft.py <in.tpf.dcx> <out.tpf.dcx> [--preview out.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image

from er_hud_bars import (BACKDROP_FLOOR, BACKDROP_GAIN, BACKDROP_ROWS,
                         ER_KEYLINE, FILLS, SCREEN_FLOOR, SCREEN_GAIN,
                         backdrop_block, to_atlas, to_screen)

REF = Path.home() / "couch/data/ds3-ui-port/er-reference"

# THE GAME RENDERS AT NATIVE 4K, AND THE ATLAS MAPS 1:1. Established 2 Sep
# 2026 (evening) with a one-texel checkerboard in the FP block: it came back on
# screen as a perfect 50/92 alternation in BOTH axes over exactly 24 rows, so
# one scale-2 texel is one 4K pixel, with no filtering, no mip and no blur.
#
# THAT CONTRADICTS EVERYTHING BELOW THIS FILE USED TO SAY, and here is why the
# old measurements were wrong without being mismeasured: the sandbox's
# GraphicsConfig.xml said `ScreenMode WINDOW 1920x1080`, so the game rendered a
# 1080p window and gamescope bilinearly upscaled it 2x into the "4K" capture.
# Donnie's REAL install runs FULLSCREEN 3840x2160. Every 4K figure taken
# before this evening - the 2:1 minification, the fractional 23.6-texels-per-
# 24-rows drift, the "measured" 3-tap PSF [0.277, 0.446, 0.277], the pair
# sampling phase, the deconvolution - described the UPSCALER, not the game.
# The sandbox config is now fullscreen 4K to match the real one (backup of the
# old one in build/GraphicsConfig.sandbox-1080p-window.xml.bak).
#
# MENU_PlayerHUD2 is 256x256 in the game files and is sampled by normalised
# UV, so a bigger texture is simply more detail in the same places. The fill
# block draws 12 base rows (DRAWN_ROWS) over 24 screen rows at 4K, so scale 2
# is exactly 1:1 vertically; horizontally 512 texels land on the bar's 512 px
# at 4K, also 1:1. Scale 4 would be a 2:1 minification for real.
ATLAS_SCALE = 2
BASE_WIDTH = 256
ATLAS_WIDTH = BASE_WIDTH * ATLAS_SCALE

# 256 base texels = 256 screen px at 1080p = 512 px at 4K. The ER source is
# resampled straight to the target texel count, so no detail is thrown away.
SRC_COLS_NEEDED = 512

# THE GAME DOES NOT DRAW THE WHOLE 24-ROW FILL BLOCK. Measured 2 Sep 2026 by
# painting the FP block with 24 distinct grey levels: it samples the MIDDLE 12
# base rows and discards the outer six on each side. Everything pasted outside
# this window is invisible, which is exactly how the bevel got clipped. Author
# the whole assembly into DRAWN_ROWS. (Re-confirmed by the checkerboard: the
# pattern occupied screen rows 188..211, 24 rows, i.e. base rows 6..18 at 2x.)
DRAWN_ROWS = (6 * ATLAS_SCALE, 18 * ATLAS_SCALE)

# PURE FILL ROWS ONLY. Every ER bar has a bevel under the fill where it
# brightens into the key-line, and the first cut included it: stamina took
# 168-182, but 180-182 are bevel (33,71,48 rising to 49,81,58 against the fill's
# flat 28,69,45), and FP took one bevel row at 144. That baked a bright bottom
# edge into the fill AND inflated the variation measurement, so the amplitude
# solve then over-boosted those bars to compensate for contamination it had
# introduced itself. Stamina came out visibly harsher than the other two.
#
# Fill ends, verified row by row: hp 107, stamina 179, fp 143.
#
# BUT THE FILL ALONE IS THE WRONG THING TO PASTE, which is what Donnie caught:
# "there's a pale bar at the bottom and the actual frame is taller too. i don't
# think you pasted that top one". Every ER bar is a three-part assembly of a
# consistent shape:
#
#         fill     bevel    rail
#     hp  95-107   108-115  116-119
#     fp  132-143  144-151  152-155
#     sta 168-179  180-187  188-191
#
# The bevel is a wide soft brightening into the rail (HP goes 94,27,24 up to
# 96,80,64 across those 8 rows) and it is nearly as tall as the fill itself.
# Pasting fill-only put ER's colour inside DS3's frame: the fill ended up 80%
# of the bar's height where ER's is about 46%, with a one-pixel key-line where
# ER has a thick ruled rail. Right colours, wrong silhouette.
#
# So the cut is now fill+bevel, and the rail goes into the backdrop below.
# THE CUT NOW INCLUDES THE RAIL, and that is a positioning fix rather than a
# cosmetic one. With only fill+bevel in the cut (21 source rows) our assembly
# filled the 24 screen rows the block gets at 4K, which pushed the separately
# drawn backdrop rail down to +27 where ER's sits at +23. Measured row by row,
# everything above that matched within a delta of 5 and the rail was out by 4
# rows - the single largest remaining difference.
#
# Cutting ER's whole assembly instead (fill 13 + bevel 8 + rail 4 = 25 rows)
# into the same 24 rows is a 25:24 squeeze, near 1:1, and lands every part
# where ER has it. The backdrop rail stays as well: it runs the full trough, so
# it continues past the fill when the bar is damaged, which is what ER does.
SOURCES = {
    # EXACTLY 24 SOURCE ROWS EACH, because the drawn window renders over 24
    # screen rows at 4K. At 25 rows the resample had to drop one, and NEAREST
    # dropped one of ER's TWO bright rail lines - leaving a single line where
    # ER has bright/dark/bright. Two different resampling fixes changed nothing
    # because the problem was never the filter, it was the row count. 24 -> 24
    # needs no resampling at all. HP starts one row later than the others to
    # make its count match; that row is uniform fill and costs nothing.
    "hp":      dict(file="hud_full.png",              rows=(96, 120),  cols=(350, 1650), strip=119, strip_x0=5),
    "stamina": dict(file="hud_full.png",              rows=(168, 192), cols=(350, 1010), strip=83,  strip_x0=7),
    "fp":      dict(file="burst/hud-combat-full.png", rows=(132, 156), cols=(330, 699),  strip=155, strip_x0=8),
}

# THE FILL TEXTURE IS ELDEN RING'S OWN, TEXEL FOR TEXEL (2 Sep, late evening).
# Donnie: "can we match the textures on it too now?" The screenshot cut above
# gives the right colours but not the right GRAIN: 1300 screen columns were
# squeezed into 512, so our streaks were finer and weaker than ER's (HP red
# std 1.94 vs 3.14, autocorrelation at 16 px 0.24 vs 0.66).
#
# ER's fills live in SB_FE_01.png as three 2889-texel strips (rows 117..139
# HP, 153..175 FP, 81..102 stamina, with two fading rim rows above each).
# Cross-correlating the HP strip's column profile against the 4K screenshot
# gives correlation 0.945 at EXACTLY 1.00 screen px per texel, screen x315 =
# texel 10, so ER draws it 1:1 at 2160p; and the rows map 1:1 too: strip row
# `strip` is the fill's top screen row, then 12 flat, 6 bevel, 2 fading.
# Our scale-2 atlas is also one texel per 4K px, so the strip goes in with NO
# resampling. Alignment: our red starts at atlas column 8 (base texel 4, the
# tile's first displayed texel) and ER's at strip texel 5, so atlas column c
# holds strip texel c - 3.
#
# Rows +0..+16 come from the strip, each row's mean pinned to ER's measured
# SCREEN mean for that row (the screenshot cut's row mean; ER renders the
# strip at about 0.98 gain and the bevel rows blend with the frame drawn
# over them). Rows +17..+23 (bevel bottom and the rail, which is a separate
# frame element in ER) stay from the screenshot cut, which measured within
# 0.7 dE. Per-pixel, screen vs strip*gain differs by ~1 unit: capture noise.
ER_SHEET = Path.home() / "couch/data/ds3-ui-port/extract/er/png/SB_FE_01.png"
STRIP_ROWS = 17            # fill rows taken from the strip (+0..+16)
# Each bar starts on a different strip texel in ER (measured by correlating
# the reference frames against the strips: HP texel 5, stamina 7, FP 8, each
# at correlation 0.94-0.96). `strip_x0` per source; our red starts at atlas
# column 8, so atlas column c holds strip texel (c - 8) + strip_x0.
RED_START_COL = 8
# ER's SCREEN shows the strip at reduced contrast: regressing the reference
# frames' deviations on the strip's gives slopes 0.79-0.88 (HP 0.79/0.86 in
# two frames, FP 0.86, stamina 0.88). The row means are pinned separately,
# so this scales only the deviation from the row mean.
GRAIN_CONTRAST = 0.85

# The damage-lag segment cannot be cut the same way: only 58 columns of it
# exist in any frame (a sliver to the right of current HP in hud-damage-lag),
# and tiling 58 into 512 repeats nine times and reads as wallpaper. Its real
# colour IS measured - (140,115,23), which matches an independent sample to
# within a unit - so lag reuses HP's 1300 columns of real grain, retinted.
# That is justified rather than convenient: the bars share one greyscale
# texture in the files, and HP-vs-stamina streaks at the same screen columns
# correlate +0.54 against a +0.14 shifted-self control.
LAG_COLOUR = (140, 115, 23)
KEYLINE_SRC = dict(file="hud_full.png", rows=(116, 120), cols=(350, 1650))


def rows_of(name: str) -> tuple[int, int]:
    """FILLS holds base-256 rows; everything here works in the scaled atlas."""
    r0, r1 = FILLS[name]["rows"]
    return r0 * ATLAS_SCALE, r1 * ATLAS_SCALE


def backdrop_rows() -> tuple[int, int]:
    return BACKDROP_ROWS[0] * ATLAS_SCALE, BACKDROP_ROWS[1] * ATLAS_SCALE


def _widen(a: np.ndarray, need: int) -> np.ndarray:
    """Mirror-tile along x until there are at least `need` columns."""
    while a.shape[1] < need:
        a = np.concatenate([a, a[:, ::-1]], axis=1)
    return a[:, :need]


def _to_atlas_width(a: np.ndarray) -> np.ndarray:
    """Source columns -> ATLAS_WIDTH, mirror-tiling first if there are too few."""
    a = _widen(a, SRC_COLS_NEEDED)[:, :SRC_COLS_NEEDED]
    img = Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGB")
    return np.asarray(img.resize((ATLAS_WIDTH, a.shape[0]), Image.LANCZOS)).astype(float)


def cut(spec: dict) -> np.ndarray:
    src = np.asarray(Image.open(REF / spec["file"]).convert("RGB")).astype(float)
    band = src[spec["rows"][0]:spec["rows"][1], spec["cols"][0]:spec["cols"][1]]
    return _to_atlas_width(band)


def _source_lum_std(spec: dict) -> float:
    """ER's own LUMINANCE variation for this cut, at the atlas's sampling.

    The thing to match, because the floor decides how it gets distributed
    across channels on our side but not how much of it there should be.
    """
    band = _source_band(spec)
    lum = band.mean(axis=2)
    return float((lum - lum.mean(axis=1, keepdims=True)).std())


def _source_band(spec: dict) -> np.ndarray:
    src = np.asarray(Image.open(REF / spec["file"]).convert("RGB")).astype(float)
    band = src[spec["rows"][0]:spec["rows"][1], spec["cols"][0]:spec["cols"][1]]
    if spec.get("retint"):
        band = retint(band, spec["retint"])
    w = band.shape[1] // 2 * 2
    return band[:, :w].reshape(band.shape[0], w // 2, 2, 3).mean(axis=2)


def _source_std(spec: dict, channel: int) -> float:
    """ER's own per-channel horizontal variation for this cut, at 1080p scale.

    Measured on the source band downsampled 2:1 the same way the graft is, so
    it is the amplitude ER would show at DS3's resolution, not at 4K.
    """
    src = np.asarray(Image.open(REF / spec["file"]).convert("RGB")).astype(float)
    band = src[spec["rows"][0]:spec["rows"][1], spec["cols"][0]:spec["cols"][1]]
    if spec.get("retint"):
        band = retint(band, spec["retint"])
    w = band.shape[1] // 2 * 2
    ds = band[:, :w].reshape(band.shape[0], w // 2, 2, 3).mean(axis=2)
    ch = ds[..., channel]
    return float((ch - ch.mean(axis=1, keepdims=True)).std())


def retint(piece: np.ndarray, colour) -> np.ndarray:
    """Keep a cut's luminance texture, swap its colour for another measured one.

    Normalised by the cut's OWN mean, not used as an absolute. Scaling HP's
    luminance (~47) straight into lag's hue lands the bar at (71,58,38) rather
    than lag's real (140,115,23) - the texture would be right and the bar half
    as bright as the thing it is copying.
    """
    lum = piece.mean(axis=2, keepdims=True)
    base = np.array(colour, float)
    return base[None, None, :] * (lum / max(float(lum.mean()), 1.0))


def graft_fills(atlas: np.ndarray) -> np.ndarray:
    jobs = dict(SOURCES)
    jobs["lag"] = dict(SOURCES["hp"], retint=LAG_COLOUR)

    for name, spec in jobs.items():
        r0, r1 = rows_of(name)
        h = r1 - r0
        piece = cut(spec)
        if spec.get("retint"):
            piece = retint(piece, spec["retint"])

        # Fit the assembly into the rows the game ACTUALLY DRAWS, not the whole
        # block. See DRAWN_ROWS: only the middle 12 of the 24 are sampled, so a
        # cut spread over all 24 loses its top and bottom quarter. That is what
        # clipped the bevel - it sat in rows 16-23 and only rows 16-17 of it
        # ever reached the screen, which is why the bar had an abrupt bottom
        # where ER's graduates softly into the rail.
        d0, d1 = DRAWN_ROWS
        # 1:1. The drawn window is (d1-d0) = 24 texels and the game renders it
        # over 24 screen rows at native 4K, so the 24 source rows go in
        # untouched: no vertical resample, no pair duplication, no phase roll,
        # no deconvolution. Horizontal LANCZOS only (the fill's streaks are
        # fine detail worth filtering well; the source is wider than 512).
        #
        # Deleted here on 2 Sep evening: the "resample to 12 screen rows, then
        # duplicate each into a texel pair" step, the SAMPLE_PHASE roll, and
        # the tridiagonal PSF deconvolution (both the straight and lambda 0.02
        # regularised forms). All of it modelled a 2:1 minification and a
        # 3-tap blur that only ever existed in gamescope's upscale of a 1080p
        # window (see the header). Rendered at native 4K the duplication was
        # visible as literal doubled pixel rows.
        img = Image.fromarray(piece.clip(0, 255).astype(np.uint8), "RGB")
        img = img.resize((ATLAS_WIDTH, img.height), Image.LANCZOS)
        if img.height != d1 - d0:
            # Only if a source is ever cut at a different height; the SOURCES
            # are all exactly 24 rows so this is normally a no-op.
            img = img.resize((ATLAS_WIDTH, d1 - d0), Image.NEAREST)
        drawn = np.asarray(img).astype(float)

        # Rows outside the drawn window are never sampled at this resolution,
        # but clamp-extend the edges into them rather than leaving whatever was
        # underneath, so nothing ugly appears if the window ever shifts.
        piece = np.empty((h, ATLAS_WIDTH, 3), float)
        piece[d0:d1] = drawn
        piece[:d0] = drawn[0]
        piece[d1:] = drawn[-1]

        # Restore the variation that resampling ate, measured against ER's own.
        #
        # A straight graft arrives too FLAT: 2x horizontal averaging and the
        # vertical stretch cost roughly 40% of the amplitude, so HP's red came
        # back at std 2.05 against ER's 3.55.
        #
        # The target is ER's DOMINANT-CHANNEL std, deliberately not its
        # luminance std. Matching luminance would demand ~3.6x here, because
        # the floor pins the other two channels at a dead-flat 38 (measured
        # std 0.00) and only the dominant channel can carry anything - so
        # luminance-matching drives that one channel to swing three times
        # harder than ER's does, which is what made the previous attempt look
        # blotchy. Matching per-channel keeps the bar's redness varying
        # exactly as ER's does and accepts the desaturation as the floor's
        # unavoidable cost.
        # Restore the LUMINANCE variation the floor destroys.
        #
        # Pre-compensation already inverts the transfer, but two of three
        # channels invert to negative and clamp to zero, so they render dead
        # flat: measured green std 0.19 and blue 0.00 against ER's 3.06 and
        # 1.94. Only the dominant channel can carry any texture at all, which
        # left total luminance variation at about 0.85 against ER's 2.42 - the
        # bar read smoother than ER's however faithful the source pixels were.
        #
        # So the texture is pushed onto the channel that survives, scaling
        # until the PREDICTED SCREEN luminance matches ER's. That is a real
        # trade: the dominant channel ends up varying more than ER's does, so
        # it shimmers slightly in saturation where ER shimmers in brightness.
        # Matching total variation looks closer than matching per-channel and
        # leaving the bar visibly flatter.
        target_lum = _source_lum_std(spec)
        rowmean = piece.mean(axis=1, keepdims=True)
        dev = piece - rowmean
        scale = 1.0
        for _ in range(12):
            trial = np.clip(rowmean + dev * scale, 0, 255)
            screen = to_screen(to_atlas(trial))
            lum = screen.mean(axis=2)
            got = float((lum - lum.mean(axis=1, keepdims=True)).std())
            if got < 0.01 or abs(got - target_lum) < 0.02:
                break
            scale = float(np.clip(scale * (target_lum / got), 0.2, 8.0))
        piece = np.clip(rowmean + dev * scale, 0, 255)

        # ER's own texels for the fill body (see STRIP_ROWS above). `piece`
        # is in screen units here, rows d0..d1 being the drawn window.
        if spec.get("strip") is not None:
            sheet = np.asarray(Image.open(ER_SHEET).convert("RGB")).astype(float)
            cols = np.clip(np.arange(ATLAS_WIDTH) - RED_START_COL + spec.get("strip_x0", 5),
                           0, sheet.shape[1] - 1)
            for k in range(STRIP_ROWS):
                srow = sheet[spec["strip"] + k, cols]
                if spec.get("retint"):
                    srow = retint(srow[None], spec["retint"])[0]
                target = piece[d0 + k].mean(axis=0)
                srow = srow * (target / np.maximum(srow.mean(axis=0), 1e-6))
                srow = target + (srow - target) * GRAIN_CONTRAST
                piece[d0 + k] = np.clip(srow, 0, 255)

        compensated = to_atlas(piece)
        atlas[r0:r1, :, :3] = compensated.round().astype(np.uint8)
        atlas[r0:r1, :, 3] = 255

        back = compensated * SCREEN_GAIN + SCREEN_FLOOR
        lum = back.mean(axis=2)
        tag = f"{spec['file']}{' retinted' if spec.get('retint') else ''}"
        print(f"  {name:8s} cut {spec['rows'][1]-spec['rows'][0]}x"
              f"{spec['cols'][1]-spec['cols'][0]} from {tag:36s}"
              f" -> screen {tuple(back.reshape(-1,3).mean(axis=0).round().astype(int))}"
              f"  grain {(lum - lum.mean(axis=1, keepdims=True)).std():.2f}")
    return atlas


# ER'S LEFT CAP, pasted for real now that the atlas is 4x.
#
# Donnie: "can we fix the left side edge of the health bars" and then "up the
# resolution and attach the elden ring cap properly". The first attempt at 256
# gave the cap 30 texels for 60 px of fine 4K filigree and it came out a yellow
# smear, so it was replaced with a plain diagonal bevel. At 1024 the cap gets
# 120 texels, which is 2 texels per pixel of source - no detail is lost.
#
# Safe to author into the fill because the fill maps 1:1 horizontally FROM THE
# BAR'S LEFT (2:1 at 4K), so these texels always land at the bar's left edge at
# a fixed size however long the bar is.
#
# The source is a screenshot with no alpha, so the sage scene behind the
# filigree is keyed out by colour distance and written transparent, letting
# DS3's own dark backdrop show through the gaps the way the scene does in ER.
CAP_COLS_SRC = (280, 340)          # 4K columns holding the cap and the bevel
CAP_TEXELS = 30 * ATLAS_SCALE
ER_SCENE = (110, 128, 108)
KEY_NEAR, KEY_FAR = 30.0, 70.0


def graft_left_cap(atlas: np.ndarray, name: str, spec: dict) -> np.ndarray:
    """Paste ER's ornate left cap into the first CAP_TEXELS of one fill block.

    ALWAYS cut from the HP frame, whatever bar this is. The cap art is the same
    on all three bars, but the SCENE behind it is not: hud_full has ER's sage
    fog, which keys out cleanly, while hud-combat-full has a pale sky that
    defeats the same test and left a sage triangle above the FP and stamina
    caps. Cutting once from the frame that keys well and reusing it removes the
    problem instead of trying to key two different backgrounds.
    """
    spec = SOURCES["hp"]
    r0, r1 = rows_of(name)
    d0, d1 = DRAWN_ROWS
    y0, y1 = spec["rows"][0] - 3, spec["rows"][1] + 4      # the cap overhangs
    src = np.asarray(Image.open(REF / spec["file"]).convert("RGB")).astype(float)
    band = src[y0:y1, CAP_COLS_SRC[0]:CAP_COLS_SRC[1]]

    img = Image.fromarray(band.clip(0, 255).astype(np.uint8), "RGB")
    cap = np.asarray(img.resize((CAP_TEXELS, d1 - d0), Image.LANCZOS)).astype(float)

    # Colour distance alone leaves a sage triangle above each cap, where the
    # scene is lit differently enough to escape the threshold. The reliable
    # discriminator is hue, not distance: ER's backdrop there is GREEN-dominant
    # while the filigree is warm (red >= green > blue), so anything greener
    # than it is red is scene and gets keyed out outright.
    dist = np.linalg.norm(cap - np.array(ER_SCENE, float), axis=2)
    alpha = np.clip((dist - KEY_NEAR) / (KEY_FAR - KEY_NEAR), 0.0, 1.0)
    # BOTH conditions, not just hue: the stamina and FP fills are themselves
    # green-dominant, so hue alone deleted the bars (solid texels fell from
    # 3370 to 925). The scene is also BRIGHT where the fills are dark - sage
    # sits at red 110, stamina and FP at red 28 - so requiring a high red as
    # well keys the backdrop and leaves the bar alone.
    alpha[(cap[..., 1] > cap[..., 0] + 3.0) & (cap[..., 0] > 70.0)] = 0.0

    # Write ONLY the bone ornament, never the whole patch. The cut is taken
    # from the HP frame, so it carries HP's RED fill on its right-hand side;
    # pasting all of it put a red wedge at the start of the FP and stamina bars.
    # Three cases: background keys to transparent (which is what produces ER's
    # slanted start), filigree is written, and anything else is left as the
    # bar's own fill that graft_fills already put there.
    comp = to_atlas(cap)
    lum = cap.mean(axis=2)
    bg = alpha < 0.5
    # A hard brightness cut kept only 357 texels and the ornament read as
    # scattered specks. Blend by HOW bone-like each pixel is instead, so the
    # filigree lands solid with soft edges. Fill is <= 60 luminance, filigree
    # ~143, so the ramp sits between them.
    # THE ORNAMENT IS NO LONGER DRAWN HERE. Donnie: "i think you just need to
    # alter how the health bar renders?" - correct. Baked into the fill it is
    # trapped inside the bar's rectangle and cannot overhang the way ER's does,
    # and DS3's own end-cap element is a 5x7 sprite whose on-screen size is
    # fixed in engine code. So the filigree moved to the vkBasalt pass, which
    # draws on the finished frame and is not bounded by anything.
    #
    # What stays here is the part only the texture can do: the SLANTED START.
    # bg keys to transparent, which cuts the fill's bottom-left corner away, so
    # the bar emerges on a diagonal under wherever the ornament is drawn.
    w = np.zeros_like(lum)

    sub = atlas[r0 + d0:r0 + d1, :CAP_TEXELS]
    rgb = sub[..., :3].astype(float)
    rgb = rgb * (1.0 - w[..., None]) + comp * w[..., None]
    sub[..., :3] = np.clip(rgb, 0, 255).round().astype(np.uint8)
    a = sub[..., 3].astype(float)
    a[bg] = 0.0
    a[w > 0.05] = 255.0
    sub[..., 3] = a.round().astype(np.uint8)
    atlas[r0 + d0:r0 + d1, :CAP_TEXELS] = sub
    bone = w > 0.5
    atlas[r0:r0 + d0, :CAP_TEXELS] = atlas[r0 + d0, :CAP_TEXELS]
    atlas[r0 + d1:r1, :CAP_TEXELS] = atlas[r0 + d1 - 1, :CAP_TEXELS]
    print(f"  {name:8s} left cap: {CAP_COLS_SRC[1]-CAP_COLS_SRC[0]}px of 4K source "
          f"-> {CAP_TEXELS} texels, {int(bone.sum())} filigree, {int(bg.sum())} cut")
    return atlas


def graft_keyline(atlas: np.ndarray) -> np.ndarray:
    src = np.asarray(Image.open(REF / KEYLINE_SRC["file"]).convert("RGB")).astype(float)
    band = src[KEYLINE_SRC["rows"][0]:KEYLINE_SRC["rows"][1],
               KEYLINE_SRC["cols"][0]:KEYLINE_SRC["cols"][1]]
    # ER's rail is 4 rows at 4K = 2 at 1080p, and it is the bar's loudest
    # feature. It used to get one atlas row, which is half its real thickness
    # and reads as a hairline. It now takes BOTH backdrop rows under the fill
    # (h-2 and h-1), giving 2 screen px at full trough length. The outer dark
    # seam that used to sit at h-1 is dropped: ER has rail then scene, no seam.
    # ER's rail is 4 rows carrying a bright/dark/bright/bright ruling
    # (141, 85, 145, 144). The backdrop gets RAIL_ROWS texels and the game
    # renders them over half as many screen rows, so resample to the SCREEN row
    # count with NEAREST and then duplicate - exactly as the fill does. A
    # LANCZOS resize straight to RAIL_ROWS averaged the 85 dip away, and
    # because this rail is drawn by the BACKDROP rather than the fill, fixing
    # the fill's resampling did nothing for it: the profile stayed at 118 delta
    # on that row across two attempts before I checked which element owned it.
    RAIL_ROWS = 2 * ATLAS_SCALE
    rail_screen = max(1, RAIL_ROWS // 2)
    wide = _to_atlas_width(band)
    img = Image.fromarray(wide.clip(0, 255).astype(np.uint8), "RGB")
    img = img.resize((ATLAS_WIDTH, rail_screen), Image.NEAREST)
    pairs = np.repeat(np.asarray(img).astype(float), RAIL_ROWS // rail_screen, axis=0)
    if pairs.shape[0] != RAIL_ROWS:
        pairs = np.asarray(Image.fromarray(pairs.clip(0, 255).astype(np.uint8), "RGB")
                           .resize((ATLAS_WIDTH, RAIL_ROWS), Image.NEAREST)).astype(float)

    # Averaging dims it - the block spans the bright ruled rows AND the darker
    # gap between them, so a plain mean landed at (125,119,90) against ER's
    # (145,139,108). Renormalise onto the measured colour, keeping the ruling.
    #
    # JOINTLY, not row by row. ER's rail is a DOUBLE line: rows 116-119 read
    # 142 / 85 / 145 / 144, a bright line, a dark gap, then a brighter line.
    # Normalising each output row to the same mean erased that and produced one
    # solid block. Scaling both by a single factor keeps the two rows different
    # from each other, which is what makes it read as a ruled rail.
    pairs *= np.array(ER_KEYLINE, float) / np.maximum(pairs.reshape(-1, 3).mean(axis=0), 1e-6)

    # Restore the rail's ruling amplitude. Resampling 1300 source columns down
    # to the atlas width, then the game's own 2:1 downsample, halves it: the
    # ticking measured std 5.20 on screen against ER's 12.35, so the rail read
    # as a smooth bar rather than a ruled one. (I had guessed from the picture
    # that ours was too CHUNKY - it was the opposite, which is why this is
    # measured and not eyeballed.)
    RAIL_TICK_GAIN = 12.35 / 5.20
    rowmean = pairs.mean(axis=1, keepdims=True)
    pairs = np.clip(rowmean + (pairs - rowmean) * RAIL_TICK_GAIN, 0, 255)

    compensated = np.clip((pairs - BACKDROP_FLOOR) / BACKDROP_GAIN, 0, 255)
    y0 = backdrop_rows()[1] - RAIL_ROWS
    for i in range(RAIL_ROWS):
        atlas[y0 + i, :, :3] = compensated[i].round().astype(np.uint8)
        atlas[y0 + i, :, 3] = 255
    back = compensated * BACKDROP_GAIN + BACKDROP_FLOOR
    print(f"  rail     -> screen {tuple(back.reshape(-1,3).mean(axis=0).round().astype(int))}"
          f"  x{RAIL_ROWS} rows  ticks std {back.mean(axis=2).std():.2f}")
    return atlas


def build(tpf_in: Path, tpf_out: Path, preview: Path | None = None) -> None:
    from oodle import dcx_decompress
    from tpf_png import decode
    from soulstruct.containers import TPF
    from replace_texture import replace

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    vanilla = decode([t for t in tpf.textures if t.stem == "MENU_PlayerHUD2"][0].data)

    # Upscale the untouched parts of the atlas to the working resolution. The
    # end-caps and icons above row 124 come along for the ride; they gain no
    # detail, but nothing regresses either, and everything WE author below is
    # generated at the higher resolution rather than upscaled.
    vanilla = vanilla.convert("RGBA").resize((ATLAS_WIDTH, ATLAS_WIDTH), Image.LANCZOS)
    atlas = np.asarray(vanilla).copy()

    # THE BACKDROP (the trough that shows where a bar is depleted) IS NOW
    # SYNTHESISED FROM ER'S MEASURED PROFILE, not cut from ER's leather art.
    # Donnie, 2 Sep late, from a TV grab of a damaged bar: "the depleted
    # health bar has gradient jumps". The old block was ER's SB_In_Game_02
    # backdrop resampled to the trough, an OPAQUE brown leather with a tile
    # seam and a brightness step, and its rail rows were transparent so the
    # bone rail stopped dead at the fill's end. ER's real trough, measured on
    # two reference frames with different scenes behind it (hud_full FP and
    # hud_depleted HP), is a translucent darkening of the scene: ratio to the
    # scene ~0.77 at row -2, ~0.58 at -1, ~0.52 flat through the body, easing
    # to ~0.41 at +18, a warm dark bevel row at +19, the same bone rail as the
    # fill at +20..+23 running the FULL width, one dark olive line at +24 and
    # a faint fade below. Rows are scale-2 texels, one per 4K screen row; the
    # backdrop tiles draw base rows 6..22, so texel row j lands on screen row
    # (j - 4) relative to the fill's top. The rail rows are copied from the
    # HP fill block after the graft so the ruling continues seamlessly.
    #
    # Alpha is assumed linear (the fill transfer gamma applies to RGB only);
    # verify on the next damaged-bar grab from the TV.
    # (synthesised below, after graft_fills, because it borrows the rail)
    atlas = graft_fills(atlas)

    b0, b1 = backdrop_rows()
    H = b1 - b0                                    # 32 texel rows at scale 2
    back = np.zeros((H, ATLAS_WIDTH, 4), float)
    # (screen row rel. fill top) -> (rgb, alpha) in SCREEN units
    prof = {-4: ((0, 0, 0), 0.03), -3: ((0, 0, 0), 0.06), -2: ((0, 0, 0), 0.23),
            -1: ((0, 0, 0), 0.42), 0: ((0, 0, 0), 0.45)}
    for r in range(1, 14):
        prof[r] = ((0, 0, 0), 0.48)
    prof.update({14: ((0, 0, 0), 0.50), 15: ((0, 0, 0), 0.52), 16: ((0, 0, 0), 0.53),
                 17: ((0, 0, 0), 0.55), 18: ((0, 0, 0), 0.59), 19: ((50, 39, 30), 0.56),
                 24: ((68, 70, 56), 1.0), 25: ((27, 27, 21), 0.32),
                 26: ((0, 0, 0), 0.13), 27: ((0, 0, 0), 0.10)})
    hp0, _ = rows_of("hp")
    d0, d1 = DRAWN_ROWS
    for j in range(H):
        r = j - 2 * ATLAS_SCALE                     # screen row rel. fill top
        if 20 <= r <= 23:
            back[j] = atlas[hp0 + d0 + r, :, :]     # the fill's own rail, already compensated
            back[j, :, 3] = 255
        elif r in prof:
            rgb, al = prof[r]
            back[j, :, :3] = to_atlas(np.array(rgb, float))
            back[j, :, 3] = al * 255
    atlas[b0:b1] = np.clip(back, 0, 255).round().astype(np.uint8)
    print(f"  backdrop: synthesised translucent trough, rail rows copied from the HP fill")

    # ELDEN RING'S CAP GOES INTO THE TEXTURE THE GAME ALREADY DRAWS AT THE
    # BAR'S LEFT END. Read out of 01_000_fe.gfx (see er_fe_gfx.py): the left
    # end-cap is shape 357, a 60x23 stage-px quad at the bar origin sampling
    # MENU_PlayerHUD2 base texels x 4..64, rows 160..183, i.e. the bitmap
    # matrix maps texel (tx, ty) to stage (tx - 34, ty - 171). One stage px is
    # two 4K px, one scale-2 texel is one 4K px, so the region is drawn 1:1.
    # DS3's own knob was just the only opaque thing in it.
    #
    # ER's 41x36 sprite (its own art, real alpha, from SB_FE_01) sits with its
    # origin 33 px left of the first red fill column and 6 rows above the
    # fill's top, measured by template-matching into ER's reference. The bar
    # ORIGIN is at 4K x=392 (the fill's first displayed texel is already red;
    # a first attempt assumed 384 and the cap landed exactly 8 px right,
    # measured by cross-correlation in game), fill centre at y=166:
    # 4K x = 392 + 2*(tx - 34)  ->  x=359 gives tx = 17.5, scale-2 column 35
    # 4K y = 166 + 2*(ty - 171)  ->  y=148 gives ty = 162,  scale-2 row  324
    # The region is cleared first (that removes the knob), then the cap is
    # written pre-compensated through the same transfer as the fills.
    x0, x1 = 4 * ATLAS_SCALE, 64 * ATLAS_SCALE
    y0, y1 = 160 * ATLAS_SCALE, 184 * ATLAS_SCALE
    atlas[y0:y1, x0:x1, 3] = 0
    cap = Image.open(REF / "er_bar_cap.png").convert("RGBA")
    if ATLAS_SCALE != 2:
        cap = cap.resize((cap.width * ATLAS_SCALE // 2, cap.height * ATLAS_SCALE // 2), Image.LANCZOS)
    c = np.asarray(cap).astype(float)
    cx, cy = 35 * ATLAS_SCALE // 2, 324 * ATLAS_SCALE // 2
    dst = atlas[cy:cy + c.shape[0], cx:cx + c.shape[1]]
    # ER renders this sprite at 0.961x its file values (measured: the opaque
    # cap pixels in ER's frame average 113.6/101.9/74.8 against the sprite's
    # 118.2/106.0/77.9, the same ratio on all three channels). Our first
    # in-game render came out at 1.024x ER's; this closes it.
    ER_CAP_GAIN = 0.961
    dst[..., :3] = np.clip(to_atlas(c[..., :3] * ER_CAP_GAIN), 0, 255).round().astype(np.uint8)
    dst[..., 3] = c[..., 3].round().astype(np.uint8)
    print(f"  ER cap {c.shape[1]}x{c.shape[0]} written at atlas ({cx},{cy}); "
          f"end-cap region x{x0}-{x1} y{y0}-{y1} cleared first")

    # THE BACKDROP RAIL IS NO LONGER DRAWN. It made sense when the fill cut
    # stopped at the bevel, but the cut now carries ER's rail rows itself and
    # lands them row-for-row. Keeping both stacked a second rail underneath the
    # first and, once its ticking was boosted, produced a thick bright bone
    # band where ER has a fine ruled line - the most obvious remaining
    # difference at 2x. One element owns the rail.
    #
    # REINSTATED. Removing it made the profile WORSE (assembly delta 399 -> 558)
    # and row +24 still showed a rail afterwards, which proves my model of which
    # element draws rows +20..+24 was wrong. Three changes were made on that
    # model - fill resampling, backdrop resampling, tick amplitude - and each
    # was neutral or harmful. The rail region is left as measured-best until
    # its ownership is established by a tracer rather than by inference.
    # BACKDROP RAIL OFF. The tracer settled ownership: the fill block draws
    # screen rows +20..+23 and the backdrop draws +25..+28, so with both on we
    # rendered EIGHT rows of rail against ER's four - which is exactly why ours
    # read as a thick bone band next to ER's fine ruled line.
    #
    # An earlier attempt to remove it made things worse, but that was at atlas
    # scale 4 where the fill's own rail was being destroyed by minification and
    # the backdrop's was the only one surviving. At scale 2 the fill carries it
    # correctly (its dark gap now measures 83 against ER's 85), so the
    # backdrop's copy is pure duplication.
    #
    # Cost, unchanged: ER's rail continues past the fill on a damaged bar and
    # ours will stop with the fill.
    # atlas = graft_keyline(atlas)
    # THE LEFT-END TREATMENT IS GONE FROM THE TEXTURE. It cut the fill's
    # bottom-left corner away on a diagonal to imply a terminus, which was the
    # best the texture could do while the cap was unavailable. Now that the
    # post-process pass draws Elden Ring's actual cap over that spot, the two
    # fought each other: the cut left an orange rust smear and a stray dark
    # block between the cap and the start of the fill, clearly visible at 3x.
    # One thing should own the bar's left end, and it is the cap.

    if preview:
        Image.fromarray(atlas, "RGBA").save(preview)

    # Write the texture ourselves rather than via replace_texture: that helper
    # FITS the image to the original slot's dimensions, which would silently
    # scale our 1024 atlas straight back down to 256 and undo the whole point.
    from oodle import dcx_compress_dflt
    from build_glyph_mod import dds_bgra
    tex = [x for x in tpf.textures if x.stem == "MENU_PlayerHUD2"][0]
    tex.data = dds_bgra(Image.fromarray(atlas, "RGBA"))
    tex.format = 9
    dcx = dcx_compress_dflt(tpf.to_bytes())
    rt = TPF.from_bytes(dcx_decompress(dcx))
    if len(rt.textures) != len(tpf.textures):
        raise SystemExit("texture count changed during repack")
    tpf_out.write_bytes(dcx)
    print(f"  MENU_PlayerHUD2 written at {ATLAS_WIDTH}x{ATLAS_WIDTH}")
    print(f"  wrote {tpf_out} ({len(dcx):,} bytes), verified")


if __name__ == "__main__":
    argv = sys.argv[1:]
    prev = None
    if "--preview" in argv:
        i = argv.index("--preview")
        prev = Path(argv[i + 1])
        del argv[i:i + 2]
    if len(argv) != 2:
        print(__doc__)
        sys.exit(1)
    build(Path(argv[0]), Path(argv[1]), prev)
