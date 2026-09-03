"""Restyle DS3's HP/FP/stamina bars in the Elden Ring direction.

Rewrites MENU_PlayerHUD2 (256x256, in menu/01_common.tpf.dcx) using the atlas
map in hud_atlas_map.json, which was derived EMPIRICALLY on 2 Sep 2026: each
candidate strip was flooded with a unique flat colour plus black notches at
x=64/128/192, the game was booted headless through ds3-shot, and the mapping
read off the capture. See the JSON for the full rect list and the observed
screen mapping.

Short form of the map (texture rows, strips are full 256 width):
    6-21    bar backdrop/frame, drawn 1:1 vertically (16 px on screen at
            1080p), horizontal 1:1 from bar start (64 tex px = 64 screen px)
    28-51   HP fill      } each 24-row block is ONE bar graphic, minified
    52-75   stamina fill } 2:1 vertically to the 12 px fill band; the fill
    76-99   FP fill      } sits centred inside the 16 px backdrop
    100-123 unconfirmed (never appeared at full bars; olive colour suggests
            the damage-lag/depleted variant) - styled to match anyway
    124+    end-cap ornaments and status icons - left untouched

The backdrop is composed from Elden Ring's OWN art (SB_In_Game_02 out of
menu/hi/01_common.tpf.dcx): the pale gold key-line at y0-3 and the dark
leather strip at y12-60. The fill tints are authored: ER's fill art is
greyscale in the files and tinted by the engine, so the exact colours do not
exist as texture data to lift.

Usage:
    python er_hud_bars.py <in.tpf.dcx> <er_SB_In_Game_02.png> <out.tpf.dcx>
                          [--preview out.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image

DS3_PNG_CACHE = None  # set in main

# Fill colours MEASURED off Elden Ring, then COMPENSATED for DS3's blend.
#
# Two separate facts, both measured, neither guessed:
#
# 1. Elden Ring's real on-screen bar colours (screen-grabbed at 4K off the
#    live game, then independently re-sampled from a second capture set):
#        HP        94, 26, 22     brick red
#        FP        28, 68, 85     slate blue  (two samples: 32,67,84 / 25,68,86)
#        stamina   28, 69, 45     forest green
#        lag       140,114, 23    olive gold, NOT orange
#        trough     46, 56, 46    (sample from an empty-HP frame; it is
#                                  translucent and reads 80-100 over bright fog)
#        key-line  145,141,110
#
# 2. DS3 does not draw this atlas 1:1. A grey step-ramp painted across the FP
#    band (8 levels, read back from an in-game capture) gives a dead-linear
#        screen = 0.87 * atlas + 38
#    identical on all three channels, r-squared eyeball-perfect. The +38 is
#    LOCAL to the bar fill, not a global tone lift: 28% of the same frame sits
#    below 38 and the frame minimum is 0.
#
# CONSEQUENCE, and it is a real constraint: ER's green (26) and blue (22) on HP
# are BELOW that floor. No atlas value can reach them - a pure black fill still
# lands at 38. So the fills below are the inverse-transfer (target-38)/0.87
# CLAMPED AT ZERO, which gets each bar's dominant channel exactly right and
# leaves the other two sitting at 38 instead of ER's 22-26. The bars come out
# very slightly greyer than Elden Ring's. That is a floor, not a tuning miss.
#
# Do NOT "fix" these by eye against the atlas - they are pre-compensation
# values and are SUPPOSED to look wrong there (green and blue at zero on HP).
# Judge them on screen, or run them back through 0.87x+38 first.
#
# Constraint: ds3-shot's HUD probe needs the on-screen HP band red-dominant
# (r > 1.6g, 1.6b) and stamina green-dominant (g > 1.2r, 1.2b). Post-transfer
# these pass: HP (94,38,38), 94 > 61; stamina (38,69,45), 69 > 46 and > 54.

# DS3's measured atlas -> screen transfer (see above). Used to convert both the
# fill colours and the grain amplitude out of screen units into atlas units.
# WAS 0.87 / 38.0. That transfer was real, but it was not the ENGINE - it was a
# Scaleform colour transform (mult 230/256, add +26) on the three bar
# placements in menu/01_000_fe.gfx, which er_fe_gfx.py now neutralises. With it
# gone the channels reach zero: HP measured (76,0,0) where it used to floor at
# (96,34,34). So the pre-compensation that fought the lift must come off too,
# or the bars render far too dark.
SCREEN_GAIN = 1.0
SCREEN_FLOOR = 0.0

# With the +26 cxform gone, what remains is a pure GAMMA, no offset. Writing
# ER's values straight in rendered them bright - HP (94,26,22) came back as
# (107,38,32) - and fitting those three points gives
#     screen = 255 * (atlas/255) ** 0.87
# which reproduces all three channels within ~3. There is no additive term left
# to fight, so this inverts cleanly and every channel is reachable.
#
# 0.87 -> 0.8795 (3 Sep 2026). The one-texel checkerboard at native 4K gave
# two exact points, atlas 40 -> screen 50 and 80 -> 92, and BOTH invert to
# 0.8795; 0.87 sits outside the round-to-nearest bracket either point allows,
# and hud_sim's global refit over all three bars agreed (mean abs error 0.17
# against 0.83). At 0.87 every flat fill row rendered about one unit under
# ER's. PAIRED with hud_sim.GAMMA: the graft inverts this transfer and the
# simulator applies it, so they move together or not at all.
SCREEN_GAMMA = 0.8795


def to_atlas(target):
    """ER's on-screen target -> the atlas value that renders as it."""
    import numpy as _np
    a = _np.asarray(target, dtype=float) / 255.0
    return _np.clip(255.0 * _np.power(_np.clip(a, 0, 1), 1.0 / SCREEN_GAMMA), 0, 255)


def to_screen(atlas):
    import numpy as _np
    a = _np.asarray(atlas, dtype=float) / 255.0
    return _np.clip(255.0 * _np.power(_np.clip(a, 0, 1), SCREEN_GAMMA), 0, 255)


def compensate(target) -> tuple:
    """ER's on-screen target -> the atlas value that produces it in DS3.

    Clamped at zero, which is where the floor bites: any target channel below
    38 is simply unreachable and comes out at 38.
    """
    return tuple(int(round(v)) for v in to_atlas(target))


# Elden Ring's measured on-screen colours, and the compensated atlas values
# they imply. Only "mid" is needed now: ER's fill is flat, and the shape comes
# from ER_ROW_PROFILE plus the real grain rather than an authored gradient.
FILLS = {
    "hp":      {"rows": (28, 52),  "er": (94, 26, 22),   "mid": compensate((94, 26, 22))},
    "stamina": {"rows": (52, 76),  "er": (28, 69, 45),   "mid": compensate((28, 69, 45))},
    "fp":      {"rows": (76, 100), "er": (28, 68, 85),   "mid": compensate((28, 68, 85))},
    "lag":     {"rows": (100, 124),"er": (140, 114, 23), "mid": compensate((140, 114, 23))},
}
BACKDROP_ROWS = (6, 22)


# Elden Ring's ACTUAL vertical profile through the HP fill, luminance per row,
# measured off the 4K reference grab (rows 95-107; row 108 onward is the bone
# key-line UNDER the bar, not the fill, and including it is what first made
# this look like a bottom-up gradient).
#
# The whole span is 46.3 to 49.4. The fill is essentially FLAT. The gradient
# that used to be here ran 116 down to 66 on screen - about 15x too much
# contrast, in the wrong direction, and it is why the bars read as painted
# plastic next to ER's.
ER_ROW_PROFILE = np.array([49.4, 47.3, 46.6, 46.3, 46.6, 47.2, 47.6,
                           47.8, 48.1, 48.1, 47.8, 47.4, 48.4])

# ER's measured horizontal grain amplitude on screen, as a luminance std. The
# bars are scaled to reproduce THIS on screen rather than to carry a fixed
# atlas amplitude, because the floor clips whichever channels sit at zero and
# swallows part of the variation before it is drawn.
ER_GRAIN_STD = 2.48

_GRAIN_CACHE = None


def _grain_screen(h: int, width: int) -> np.ndarray:
    """ER's vertical brush-stroke texture, in SCREEN luminance units.

    Baked by extract_fill_grain.py off the live-game reference and stored as
    delta+128 at 1 unit per screen RGB unit. Callers convert to atlas units.
    """
    global _GRAIN_CACHE
    if _GRAIN_CACHE is None:
        p = Path(__file__).parent / "hud_fill_grain.png"
        if not p.exists():
            raise SystemExit(f"missing {p} - run extract_fill_grain.py first")
        _GRAIN_CACHE = Image.open(p).convert("L")
    g = _GRAIN_CACHE
    if g.size != (width, h):
        g = g.resize((width, h), Image.BILINEAR)
    return np.asarray(g).astype(float) - 128.0


def fill_block(colours: dict, width: int = 256) -> np.ndarray:
    """One 24-row bar-fill graphic: ER's flat profile plus its real grain.

    Drawn at full row granularity even though the game minifies the block 2:1
    vertically - the grain is vertical streaks, so it survives the minify.

    Built in SCREEN space and compensated back at the end, rather than authored
    directly in atlas values. That matters for the grain: added flat in atlas
    space it would clip against zero on HP's green and blue (both compensate to
    0) and survive only on its positive lobe, rippling the hue. Modelled as a
    proportional modulation of the tint, which is what ER's greyscale-texture-
    times-shader-colour actually does, it stays neutral.
    """
    h = colours["rows"][1] - colours["rows"][0]
    er = np.array(colours["er"], float)
    er_luma = max(er.mean(), 1.0)

    # ER's row profile, resampled to this block's height, normalised to 1.0.
    prof = np.interp(np.linspace(0, len(ER_ROW_PROFILE) - 1, h),
                     np.arange(len(ER_ROW_PROFILE)), ER_ROW_PROFILE)
    prof = prof / prof.mean()

    # Grain as a fraction of the bar's own brightness (ER: +-11 on a mean of
    # ~48, so roughly +-22% at the extremes).
    grain = _grain_screen(h, width) / er_luma

    def render(scale: float):
        screen = er[None, None, :] * prof[:, None, None] * (1.0 + scale * grain[:, :, None])
        atlas = np.clip((screen - SCREEN_FLOOR) / SCREEN_GAIN, 0, 255)
        actual = atlas * SCREEN_GAIN + SCREEN_FLOOR      # what the screen gets
        lum = actual.mean(axis=2)
        return atlas, (lum - lum.mean(axis=1, keepdims=True)).std()

    # Solve for the scale that lands ER's real luminance variation on screen.
    # Needed because the floor clips whichever channels compensate to zero, so
    # the grain only rides the dominant one and arrives diluted: HP measured
    # 1.59 against ER's 2.48 before this correction. One proportional step is
    # enough - the relationship is near-linear until the clipping bites.
    atlas, got = render(1.0)
    if got > 0.01:
        scale = float(np.clip(ER_GRAIN_STD / got, 0.5, 3.0))
        atlas, got = render(scale)

    block = np.zeros((h, width, 4), np.uint8)
    block[..., :3] = atlas
    block[..., 3] = 255
    return block


# The backdrop strip renders through a DIFFERENT transfer from the fill.
BACKDROP_GAIN = 0.833
BACKDROP_FLOOR = 48.0

# ER's bone key-line, measured on screen, and its ruling amplitude.
ER_KEYLINE = (145, 139, 108)

# The baked ticks arrive weaker than ER's because extract_fill_grain collapses
# four 4K rows into one. Do NOT calibrate against ER's 4K per-row std of 11.1 -
# that compares a 4K row against our 1080p row and would overdrive it 2.2x.
# Downsampled to 1080p, ER's key-line rows measure 5.87 and 8.46; ours came
# back at 5.11, so this closes a real but modest gap.
TICK_GAIN = 1.4
_TICKS_CACHE = None


def _back_compensate(target) -> tuple:
    """Backdrop target -> atlas value.

    Uses the same gamma as the fill now. The old linear 0.833x+48 was measured
    while the HUD's colour transform was still adding +26; with that gone it
    over-darkened, and the dark edge above the bar rendered (28,3,1) where ER
    has (65,48,36).
    """
    return tuple(int(round(v)) for v in to_atlas(target))


def _keyline_row(width: int) -> np.ndarray:
    """One row of ER's bone key-line, complete with its fine ruling.

    The ticks are baked in SCREEN luminance units by extract_fill_grain.py and
    applied proportionally, so the line keeps its hue while it varies.
    """
    global _TICKS_CACHE
    if _TICKS_CACHE is None:
        p = Path(__file__).parent / "hud_keyline_ticks.png"
        if not p.exists():
            raise SystemExit(f"missing {p} - run extract_fill_grain.py first")
        _TICKS_CACHE = Image.open(p).convert("L")
    t = _TICKS_CACHE
    if t.size[0] != width:
        t = t.resize((width, 1), Image.BILINEAR)
    ticks = np.asarray(t).astype(float).reshape(-1) - 128.0

    base = np.array(ER_KEYLINE, float)
    screen = base[None, :] * (1.0 + (TICK_GAIN * ticks / base.mean())[:, None])
    atlas = (screen - BACKDROP_FLOOR) / BACKDROP_GAIN
    return np.clip(atlas, 0, 255).astype(np.uint8)


def backdrop_block(er: np.ndarray, width: int = 256) -> np.ndarray:
    """16-row backdrop: ER's gold key-lines framing ER's dark leather.
    Baked opaque over near-black so translucent ER pixels do not let the
    scene bleed through more than vanilla did."""
    h = BACKDROP_ROWS[1] - BACKDROP_ROWS[0]
    out = np.zeros((h, width, 4), np.uint8)

    def flatten(rgba: np.ndarray, base=(12, 10, 8)) -> np.ndarray:
        a = rgba[..., 3:4].astype(float) / 255.0
        rgb = rgba[..., :3].astype(float) * a + np.array(base, float) * (1 - a)
        return np.clip(rgb, 0, 255).astype(np.uint8)

    leather = np.asarray(Image.fromarray(er[12:60, 0:800]).resize((width, h - 4), Image.LANCZOS))

    # Only four rows of this block are ever visible: the fill covers the middle
    # 12 of 16. Rows 0-1 sit above the fill and rows h-2, h-1 below it.
    #
    # ER's bar is ASYMMETRIC and the first version had it backwards. Measured
    # off the reference grab, above the fill (row 94) is a DARK edge at
    # (65,49,37) against the scene; below it (rows 116-119) is a pale bone
    # key-line at (145,139,108), finely ruled like hatching on a ruler. Ours
    # had a bright (164,154,143) line ON TOP and a duller one underneath -
    # the inversion of ER, which is what Donnie spotted: "we also need the long
    # paler bar at the bottom of the texture".
    #
    # The backdrop has its OWN transfer, not the fill's. Two clean data points
    # from a capture (atlas 139 -> screen 164, atlas 121 -> screen 149) give
    #     screen = 0.833 * atlas + 48
    # so the floor here is 48, not the fill's 38. ER's top-edge blue of 37 is
    # under it and clamps; everything else is reachable.
    out[0, :, :3] = (24, 19, 12)                       # outer dark seam
    out[1, :, :3] = _back_compensate((65, 49, 37))     # ER's DARK top edge
    out[2:h - 2, :, :3] = (flatten(leather).astype(float) * 0.8).astype(np.uint8)
    out[h - 2, :, :3] = _keyline_row(width)            # ER's ruled bone key-line
    out[h - 1, :, :3] = (24, 19, 12)
    out[..., 3] = 255
    return out


def build_png(vanilla_hud2: Image.Image, er_atlas: Image.Image) -> Image.Image:
    a = np.asarray(vanilla_hud2.convert("RGBA")).copy()
    er = np.asarray(er_atlas.convert("RGBA"))
    a[BACKDROP_ROWS[0]:BACKDROP_ROWS[1]] = backdrop_block(er)
    for colours in FILLS.values():
        y0, y1 = colours["rows"]
        a[y0:y1] = fill_block(colours)
    return Image.fromarray(a)


def main() -> None:
    argv = sys.argv[1:]
    preview = None
    if "--preview" in argv:
        i = argv.index("--preview")
        preview = Path(argv[i + 1])
        del argv[i:i + 2]
    if len(argv) != 3:
        print(__doc__)
        sys.exit(1)
    tpf_in, er_png, tpf_out = map(Path, argv)

    from tpf_png import decode
    from oodle import dcx_decompress
    from soulstruct.containers import TPF
    from replace_texture import replace

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    vanilla = decode([t for t in tpf.textures if t.stem == "MENU_PlayerHUD2"][0].data)
    out_img = build_png(vanilla, Image.open(er_png))

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        out_img.save(f.name)
        if preview:
            out_img.save(preview)
        replace(tpf_in, "MENU_PlayerHUD2", Path(f.name), tpf_out)


if __name__ == "__main__":
    main()
