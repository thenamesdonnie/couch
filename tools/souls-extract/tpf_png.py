"""Turn a TPF's textures into PNGs, and into one contact sheet you can eyeball.

The point of the contact sheet: when you are reskinning a UI you need to SEE
what is in an atlas, and opening 126 files one at a time is not seeing. One
labelled sheet answers "what is in here and what does it look like" in a glance.

Formats actually used by DS3 and Elden Ring menu atlases, measured:
  * BC7  (DDS DX10 header, DXGI format 98) - the overwhelming majority
  * DXT1 (BC1, classic FourCC header)      - a handful
Pillow will not decode BC7, hence texture2ddecoder.

Note the TPF entries already contain a COMPLETE DDS file, header included.
soulstruct's `get_headerized_dds` exists for entries that lack one and will
raise "console texture without console_info" here; you do not need it.

Usage:
    python tpf_png.py <file.tpf> <outdir> [--sheet]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

DXGI_BC7_UNORM = 98
DXGI_BC7_UNORM_SRGB = 99


def dds_describe(d: bytes) -> tuple[int, int, str, int]:
    """-> (width, height, kind, pixel_data_offset)."""
    if d[:4] != b"DDS ":
        raise ValueError("not a DDS")
    height, width = struct.unpack_from("<II", d, 12)
    pf_flags = struct.unpack_from("<I", d, 80)[0]
    fourcc = d[84:88]
    if fourcc == b"DX10":
        dxgi = struct.unpack_from("<I", d, 128)[0]
        kind = "BC7" if dxgi in (DXGI_BC7_UNORM, DXGI_BC7_UNORM_SRGB) else f"dxgi{dxgi}"
        return width, height, kind, 148          # 128 header + 20 DX10 header
    if pf_flags & 0x40:                          # DDPF_RGB: uncompressed
        bpp = struct.unpack_from("<I", d, 88)[0]
        rmask = struct.unpack_from("<I", d, 92)[0]
        # We write B8G8R8A8, i.e. red in the third byte -> mask 0x00FF0000.
        return width, height, f"RAW{bpp}" + ("_BGRA" if rmask == 0x00FF0000 else "_RGBA"), 128
    return width, height, fourcc.decode("ascii", "replace"), 128


def decode(d: bytes):
    """DDS bytes -> PIL Image, or None if the format is one we do not handle."""
    from PIL import Image
    import texture2ddecoder

    width, height, kind, offset = dds_describe(d)
    if width == 0 or height == 0:
        return None
    payload = d[offset:]
    if kind.startswith("RAW32"):
        order = "BGRA" if kind.endswith("_BGRA") else "RGBA"
        return Image.frombytes("RGBA", (width, height),
                               payload[:width * height * 4], "raw", order)
    if kind == "BC7":
        raw = texture2ddecoder.decode_bc7(payload, width, height)
    elif kind in ("DXT1",):
        raw = texture2ddecoder.decode_bc1(payload, width, height)
    elif kind in ("DXT5",):
        raw = texture2ddecoder.decode_bc3(payload, width, height)
    else:
        return None
    # texture2ddecoder returns BGRA
    return Image.frombytes("RGBA", (width, height), raw, "raw", "BGRA")


def export(tpf_path: Path, out_dir: Path, sheet: bool = False) -> list[tuple[str, object]]:
    from soulstruct.containers import TPF

    out_dir.mkdir(parents=True, exist_ok=True)
    tpf = TPF.from_bytes(tpf_path.read_bytes())
    done = []
    for t in tpf.textures:
        try:
            img = decode(t.data)
        except Exception as e:
            print(f"  {t.stem}: decode failed ({type(e).__name__}: {e})")
            continue
        if img is None:
            w, h, kind, _ = dds_describe(t.data)
            print(f"  {t.stem}: unhandled format {kind} ({w}x{h})")
            continue
        img.save(out_dir / f"{t.stem}.png")
        done.append((t.stem, img))
    print(f"exported {len(done)}/{len(tpf.textures)} textures to {out_dir}")

    if sheet and done:
        make_sheet(done, out_dir / "_contact_sheet.png")
    return done


def make_sheet(items, path: Path, cell: int = 160, cols: int = 10) -> None:
    """One labelled grid of everything, on a mid grey so alpha edges show."""
    from PIL import Image, ImageDraw

    rows = (len(items) + cols - 1) // cols
    label_h = 14
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h)), (70, 70, 76))
    draw = ImageDraw.Draw(sheet)
    for i, (name, img) in enumerate(items):
        x, y = (i % cols) * cell, (i // cols) * (cell + label_h)
        thumb = img.copy()
        thumb.thumbnail((cell - 8, cell - 8))
        # Composite onto grey so transparent icons are visible rather than black.
        tile = Image.new("RGBA", (cell - 8, cell - 8), (70, 70, 76, 255))
        tile.alpha_composite(thumb, ((cell - 8 - thumb.width) // 2,
                                     (cell - 8 - thumb.height) // 2))
        sheet.paste(tile.convert("RGB"), (x + 4, y + 4))
        draw.text((x + 4, y + cell), name[:24], fill=(230, 230, 235))
    sheet.save(path)
    print(f"contact sheet: {path}  ({sheet.width}x{sheet.height})")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    export(Path(sys.argv[1]), Path(sys.argv[2]), sheet="--sheet" in sys.argv)
