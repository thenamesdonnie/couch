"""Replace one named texture inside a .tpf.dcx, and write a new .tpf.dcx.

The general form of what build_glyph_mod.py does for forty glyphs at once.
Used for the title logo, where a single 2048x512 texture is the whole change.

    python replace_texture.py <in.tpf.dcx> <TEXTURE_STEM> <new.png> <out.tpf.dcx>

Everything not named is copied through untouched, and the result is verified by
reading it back before it is written, because a silent bad write looks exactly
like a good one until the game refuses to boot.

Replacements are written as TPF format 9 (uncompressed B8G8R8A8). Nothing on
Linux encodes BC7 and ImageMagick tops out at DXT5, but uncompressed needs no
encoder and is lossless. It costs size: a 2048x512 texture goes from 512KB of
DXT1 to 4MB raw. That is fine here because it zlib-compresses back down inside
the DCX, but do not do it to a whole atlas without checking.

FITTING. If the new image does not match the slot's dimensions it is scaled to
fit and centred, preserving aspect. It is NOT stretched. The background fill is
taken from whether the original texture had any transparency: fully-opaque
slots (like DS3's title logo, which is white-on-black with no alpha at all) get
black, and slots with alpha get transparent. Getting that backwards puts a
black box where the UI expected a cut-out.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_glyph_mod import dds_bgra          # noqa: E402
from oodle import dcx_compress_dflt, dcx_decompress   # noqa: E402
from tpf_png import decode, dds_describe      # noqa: E402

TPF_FORMAT_BGRA = 9


def replace(tpf_dcx: Path, stem: str, png: Path, out: Path) -> None:
    from PIL import Image
    import numpy as np
    from soulstruct.containers import TPF

    tpf = TPF.from_bytes(dcx_decompress(tpf_dcx.read_bytes()))
    match = [t for t in tpf.textures if t.stem == stem]
    if not match:
        raise SystemExit(f"no texture named {stem!r}; have: "
                         f"{sorted(t.stem for t in tpf.textures)[:10]}...")
    tex = match[0]

    w, h, kind, _ = dds_describe(tex.data)
    original = decode(tex.data)
    opaque = original is not None and np.asarray(original)[..., 3].min() == 255

    img = Image.open(png).convert("RGBA")
    if img.size != (w, h):
        fitted = img.copy()
        fitted.thumbnail((w, h), Image.LANCZOS)
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 255) if opaque else (0, 0, 0, 0))
        canvas.alpha_composite(fitted, ((w - fitted.width) // 2, (h - fitted.height) // 2))
        img = canvas
        print(f"  fitted {png.name} to the slot's {w}x{h} "
              f"({'opaque black' if opaque else 'transparent'} background)")

    before = (tex.format, len(tex.data))
    tex.data = dds_bgra(img)
    tex.format = TPF_FORMAT_BGRA
    print(f"  {stem}: fmt {before[0]} {before[1]:,}B -> fmt {tex.format} {len(tex.data):,}B")

    packed = tpf.to_bytes()
    dcx = dcx_compress_dflt(packed)

    # Verify BEFORE writing: read the finished bytes back and decode the texture.
    rt = TPF.from_bytes(dcx_decompress(dcx))
    got = {t.stem: t for t in rt.textures}
    if len(rt.textures) != len(tpf.textures):
        raise SystemExit("texture count changed during repack")
    check = decode(got[stem].data)
    if check is None or check.size != (w, h):
        raise SystemExit("replacement does not decode back correctly")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(dcx)
    print(f"  wrote {out} ({len(dcx):,} bytes), {len(rt.textures)} textures, verified")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)
    replace(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]))
