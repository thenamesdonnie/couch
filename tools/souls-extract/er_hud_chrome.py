"""Darken DS3's remaining bright HUD chrome toward Elden Ring's tone.

After the bars and the covenant badge, what is left standing out on the DS3 HUD
is small bright stone furniture: the spiral SOULS icon tile bottom-right, sitting
at (124,112,92) on screen where ER's equivalent rune medallion is (37,40,33).

Same treatment as the covenant badge, and for the same reason: these tiles carry
an ICON that has to stay readable, so they are not simply multiplied down. Each
region is re-levelled about its OWN stone median, which puts the stone field on
ER's dark value while anything brighter than the stone - the engraved icon, the
rim - keeps its distance above it.

These elements render essentially 1:1 (atlas 121,104,76 -> screen 124,112,92),
unlike the gauge fill with its +34 engine lift, so targets are written directly.

Regions were established by flooding tracer colours and reading the frame back,
not from the atlas layout, which is misleading here - MENU_PlayerHUD's ornate
top-left octagon feeds nothing visible, while its tall right-hand panel is the
souls counter background.

    python er_hud_chrome.py <in.tpf.dcx> <out.tpf.dcx> [--preview dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image

# (texture, (x0, y0, x1, y1), target stone level, label)
REGIONS = [
    ("MENU_PlayerHUD", (160, 38, 205, 76), 34.0, "souls spiral tile"),
]

CONTRAST = 1.0


def relevel(patch: np.ndarray, target: float) -> np.ndarray:
    """Drop a stone tile's field to `target`, keeping its engraving readable."""
    out = patch.astype(float).copy()
    mask = out[..., 3] > 128
    if mask.sum() < 40:
        return patch
    rgb = out[..., :3]
    lum = rgb.mean(axis=2)
    stone = float(np.median(lum[mask]))
    if stone < 1.0:
        return patch
    new = np.clip(target + (lum - stone) * CONTRAST, 0.0, 255.0)
    scale = np.divide(new, np.maximum(lum, 1e-6))[..., None]
    rgb = np.clip(rgb * scale, 0, 255)
    out[..., :3] = np.where(mask[..., None], rgb, patch[..., :3])
    return out.astype(np.uint8)


def build(tpf_in: Path, tpf_out: Path, preview: Path | None = None) -> None:
    from oodle import dcx_decompress, dcx_compress_dflt
    from tpf_png import decode
    from soulstruct.containers import TPF
    from build_glyph_mod import dds_bgra

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    by = {t.stem: t for t in tpf.textures}
    cache: dict[str, np.ndarray] = {}

    for name, (x0, y0, x1, y1), target, label in REGIONS:
        if name not in by:
            print(f"  MISSING texture {name}")
            continue
        if name not in cache:
            cache[name] = np.asarray(decode(by[name].data).convert("RGBA")).copy()
        a = cache[name]
        patch = a[y0:y1, x0:x1]
        m = patch[..., 3] > 128
        before = tuple(patch[..., :3][m].mean(axis=0).round().astype(int)) if m.any() else None
        a[y0:y1, x0:x1] = relevel(patch, target)
        patch = a[y0:y1, x0:x1]
        m = patch[..., 3] > 128
        after = tuple(patch[..., :3][m].mean(axis=0).round().astype(int)) if m.any() else None
        print(f"  {label:22s} {name} [{x0},{y0}-{x1},{y1}]  {before} -> {after}")
        if preview:
            preview.mkdir(parents=True, exist_ok=True)
            bg = Image.new("RGBA", (x1 - x0, y1 - y0), (45, 48, 44, 255))
            bg.alpha_composite(Image.fromarray(patch, "RGBA"))
            bg.convert("RGB").resize(((x1 - x0) * 6, (y1 - y0) * 6), Image.NEAREST) \
              .save(preview / f"{label.replace(' ', '_')}.png")

    for name, a in cache.items():
        by[name].data = dds_bgra(Image.fromarray(a, "RGBA"))
        by[name].format = 9

    dcx = dcx_compress_dflt(tpf.to_bytes())
    rt = TPF.from_bytes(dcx_decompress(dcx))
    if len(rt.textures) != len(tpf.textures):
        raise SystemExit("texture count changed during repack")
    tpf_out.write_bytes(dcx)
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
