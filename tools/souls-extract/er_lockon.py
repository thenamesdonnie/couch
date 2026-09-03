#!/usr/bin/env python3
"""Repaint DS3's lock-on marker as Elden Ring's soft pale-blue dot.

WHAT DRAWS IT (fe_tree.py, sprite 104 `LockOn` at stage centre): three quads,
each 32x32 stage px, sampling `MENU_Lockon01` (64x32): cell 0 [0..32] is a
white dot, drawn at depth 5; cell 1 [32..64] is a bluish halo, drawn TWICE
(depths 1 and 3). The engine moves the sprite onto the target.

ER, measured on burst/hud-lockon-enemy-bar.png at 4K: a bright core 16 px
across (235,238,250 at the centre) inside a glow about 32 px across
((181,189,221) at r=8, (83,94,128) at r=14), no ring, no cross. The X-and-ring
in SB_Reticle.png is the ranged-aim reticle, not the lock-on.

The atlas ships at 2x (128x64) so a cell is 64 texels for its 64 4K px.
ER's dot is cut from the grab (80x80 around the centre), keyed on luminance
above the dark scene, premultiplied. Cell 0 gets the dot; cell 1 (the halo,
drawn twice) gets the same dot at 35% so the stack of three reads as one
soft dot rather than three white ones.

UNVERIFIED ON SCREEN: the capture harness cannot lock on to anything. Judge
it on the TV; the fallback is dropping this script from the chain.

    python er_lockon.py <in.tpf.dcx> <out.tpf.dcx> [--preview dir]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

ER_REF = Path(__file__).resolve().parents[2] / "data/ds3-ui-port/er-reference/burst/hud-lockon-enemy-bar.png"
ER_CENTRE = (2084, 501)          # 4K px
CUT = 32                         # half-size of the cut, px
SCALE = 2
HALO_STRENGTH = 0.35


def er_dot() -> np.ndarray:
    er = np.asarray(Image.open(ER_REF).convert("RGB")).astype(float)
    cx, cy = ER_CENTRE
    p = er[cy - CUT:cy + CUT, cx - CUT:cx + CUT]
    lum = p.mean(axis=2)
    scene = np.median(lum[:6, :])                      # the dark rock at the edge of the cut
    a = np.clip((lum - scene) / (235.0 - scene), 0.0, 1.0)
    # radial falloff so the cut's square edge never shows
    yy, xx = np.mgrid[0:2 * CUT, 0:2 * CUT].astype(float)
    r = np.hypot(xx - CUT + 0.5, yy - CUT + 0.5)
    a *= np.clip((CUT - 2 - r) / 6.0, 0.0, 1.0)
    rgb = p * a[..., None]                             # premultiplied
    return np.concatenate([rgb, a[..., None] * 255.0], axis=2)


def paint(atlas: np.ndarray) -> np.ndarray:
    a = np.zeros_like(atlas, dtype=float)
    dot = er_dot()
    h, w = dot.shape[:2]
    cell = 32 * SCALE
    for i, strength in ((0, 1.0), (1, HALO_STRENGTH)):
        x0 = i * cell + (cell - w) // 2
        y0 = (cell - h) // 2
        a[y0:y0 + h, x0:x0 + w] = dot * strength
    return np.clip(a, 0, 255).astype(np.uint8)


def build(tpf_in: Path, tpf_out: Path, preview: Path | None = None) -> None:
    from oodle import dcx_decompress, dcx_compress_dflt
    from tpf_png import decode
    from soulstruct.containers import TPF
    from build_glyph_mod import dds_bgra

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    tex = [t for t in tpf.textures if t.stem == "MENU_Lockon01"][0]
    img = decode(tex.data).convert("RGBA")
    target = (64 * SCALE, 32 * SCALE)
    if img.size != target:
        img = img.resize(target, Image.LANCZOS)
    atlas = paint(np.asarray(img).copy())
    if preview:
        preview.mkdir(parents=True, exist_ok=True)
        bg = Image.new("RGBA", target, (60, 20, 80, 255))
        bg.alpha_composite(Image.fromarray(atlas, "RGBA"))
        bg.resize((target[0] * 4, target[1] * 4), Image.NEAREST).save(preview / "MENU_Lockon01_x2_onbg.png")
    tex.data = dds_bgra(Image.fromarray(atlas, "RGBA"))
    tex.format = 9
    dcx = dcx_compress_dflt(tpf.to_bytes())
    rt = TPF.from_bytes(dcx_decompress(dcx))
    if len(rt.textures) != len(tpf.textures):
        raise SystemExit("texture count changed during repack")
    tpf_out.write_bytes(dcx)
    print(f"wrote {tpf_out} ({len(dcx)} bytes); MENU_Lockon01 now {atlas.shape[1]}x{atlas.shape[0]} BGRA")


def main() -> None:
    args = sys.argv[1:]
    preview = None
    if "--preview" in args:
        i = args.index("--preview")
        preview = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) != 2:
        raise SystemExit(__doc__)
    build(Path(args[0]), Path(args[1]), preview)


if __name__ == "__main__":
    main()
