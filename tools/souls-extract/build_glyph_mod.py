"""Build the Elden Ring glyph replacement for Dark Souls 3.

Reads DS3's menu/01_common.tpf.dcx, swaps the mapped KG_PS4_* textures for
Elden Ring glyphs, and writes a repacked .tpf.dcx ready to drop into a Mod
Engine mod folder. The game install is never touched.

WHY UNCOMPRESSED. DS3's glyphs ship as BC7 (TPF format 102) and nothing on
Linux encodes BC7: ImageMagick tops out at DXT5, and no Python library does it
at all. But TPF format 9 is plain B8G8R8A8, which needs no encoder, is
lossless, and costs 4KB for a 32x32 glyph. Fallback if the game rejects it is
format 5 (BC3/DXT5), which ImageMagick can write.

WHY BOTH SETS get the PlayStation art: DS3 picks between KG_* and KG_PS4_*
based on the controller it detects, and Steam Input usually presents a
DualSense as an Xbox pad, so the Xbox set is what would actually be displayed.
Writing PlayStation art into both means the glyphs are right either way.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).parent
TARGET_SIZE = 32          # DS3's KG_* glyphs are all 32x32
TPF_FORMAT_BGRA = 9       # B8G8R8A8_UNORM, see TPF_TEXTURE_FORMAT_TO_DXGI_FORMAT


def dds_bgra(img) -> bytes:
    """A complete uncompressed B8G8R8A8 DDS. TPF entries hold whole DDS files."""
    import numpy as np

    w, h = img.size
    rgba = np.asarray(img.convert("RGBA"))
    bgra = rgba[..., [2, 1, 0, 3]].tobytes()

    DDSD = 0x1 | 0x2 | 0x4 | 0x8 | 0x1000          # CAPS HEIGHT WIDTH PITCH PIXELFORMAT
    header = bytearray(128)
    header[0:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)          # header size
    struct.pack_into("<I", header, 8, DDSD)
    struct.pack_into("<I", header, 12, h)
    struct.pack_into("<I", header, 16, w)
    struct.pack_into("<I", header, 20, w * 4)       # pitch
    struct.pack_into("<I", header, 28, 1)           # mipmap count
    # DDS_PIXELFORMAT at offset 76
    struct.pack_into("<I", header, 76, 32)          # size
    struct.pack_into("<I", header, 80, 0x41)        # DDPF_RGB | DDPF_ALPHAPIXELS
    struct.pack_into("<I", header, 88, 32)          # bits per pixel
    struct.pack_into("<I", header, 92, 0x00FF0000)  # R mask
    struct.pack_into("<I", header, 96, 0x0000FF00)  # G
    struct.pack_into("<I", header, 100, 0x000000FF) # B
    struct.pack_into("<I", header, 104, 0xFF000000) # A
    struct.pack_into("<I", header, 108, 0x1000)     # DDSCAPS_TEXTURE
    return bytes(header) + bgra


def fit(img, size: int = TARGET_SIZE):
    """Centre the glyph in a square, preserving aspect. No stretching."""
    from PIL import Image

    g = img.copy()
    g.thumbnail((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(g, ((size - g.width) // 2, (size - g.height) // 2))
    return out


def build(tpf_path: Path, glyph_dir: Path, out_path: Path, both_sets: bool = True):
    from PIL import Image
    from soulstruct.containers import TPF

    cfg = json.loads((HERE / "glyph_map.json").read_text())
    mapping = cfg["map"]

    tpf = TPF.from_bytes(tpf_path.read_bytes())
    by_stem = {t.stem: t for t in tpf.textures}

    replaced, missing = [], []
    for slot, glyph_id in mapping.items():
        src = glyph_dir / f"{glyph_id}.png"
        if not src.exists():
            src = glyph_dir / f"{int(glyph_id):02d}.png"
        if not src.exists():
            missing.append(f"glyph {glyph_id}")
            continue

        art = fit(Image.open(src).convert("RGBA"))
        dds = dds_bgra(art)

        targets = [f"KG_PS4_{slot}"] + ([f"KG_{slot}"] if both_sets else [])
        for name in targets:
            tex = by_stem.get(name)
            if tex is None:
                missing.append(name)
                continue
            tex.data = dds
            tex.format = TPF_FORMAT_BGRA
            replaced.append(name)

    print(f"replaced {len(replaced)} textures ({len(mapping)} slots"
          f"{' x2 sets' if both_sets else ''})")
    if missing:
        print(f"  NOT FOUND: {missing}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    packed = tpf.to_bytes()
    out_path.with_suffix(".tpf").write_bytes(packed)
    print(f"wrote {out_path.with_suffix('.tpf')} ({len(packed):,} bytes)")
    return replaced, packed


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    build(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
