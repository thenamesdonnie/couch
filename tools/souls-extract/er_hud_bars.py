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

# ER-palette fill colours (bright top -> dark bottom), authored to read like
# Elden Ring's bars. Constraint: ds3-shot's HUD probe needs the on-screen HP
# band red-dominant (r > 1.6g, 1.6b) and the stamina band green-dominant
# (g > 1.2r, 1.2b); these satisfy that with margin.
FILLS = {
    "hp":      {"rows": (28, 52), "top": (188, 44, 32),  "mid": (150, 24, 18),  "bot": (80, 10, 8)},
    "stamina": {"rows": (52, 76), "top": (124, 166, 58), "mid": (94, 140, 44),  "bot": (44, 72, 20)},
    "fp":      {"rows": (76, 100), "top": (56, 116, 180), "mid": (34, 84, 146), "bot": (14, 36, 74)},
    "lag":     {"rows": (100, 124), "top": (232, 202, 140), "mid": (208, 174, 112), "bot": (140, 112, 66)},
}
BACKDROP_ROWS = (6, 22)


def fill_block(colours: dict, width: int = 256) -> np.ndarray:
    """One 24-row bar-fill graphic, ER style: thin bright top edge, flat body
    with a gentle vertical falloff, darker base. Drawn at 2px granularity
    because the game minifies the block 2:1 vertically."""
    h = colours["rows"][1] - colours["rows"][0]
    top, mid, bot = (np.array(colours[k], float) for k in ("top", "mid", "bot"))
    block = np.zeros((h, width, 4), np.uint8)
    for y in range(h):
        t = y / (h - 1)
        if y < 2:                                # bright key edge
            c = top * 1.22
        elif t < 0.45:                           # upper body: top -> mid
            c = top + (mid - top) * (t / 0.45)
        else:                                    # lower body: mid -> bot
            c = mid + (bot - mid) * ((t - 0.45) / 0.55)
        if y >= h - 2:                           # grounding shadow line
            c = bot * 0.55
        block[y, :, :3] = np.clip(c, 0, 255)
    block[..., 3] = 255
    return block


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

    gold = np.asarray(Image.fromarray(er[0:3, 5:1004]).resize((width, 1), Image.LANCZOS))
    leather = np.asarray(Image.fromarray(er[12:60, 0:800]).resize((width, h - 4), Image.LANCZOS))
    out[0, :, :3] = (24, 19, 12)                     # outer dark seam
    out[1, :, :3] = flatten(gold)[0] * 0.92          # gold key-line, top
    out[2:h - 2, :, :3] = (flatten(leather).astype(float) * 0.8).astype(np.uint8)
    out[h - 2, :, :3] = flatten(gold)[0] * 0.8       # gold key-line, bottom
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
