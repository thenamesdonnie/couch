"""Flatten DS3's equipment slots toward Elden Ring's: no podium, plainer rails.

WHAT THIS IS. `MENU_ItemPanel_02` (256x512) is the entire in-game equipment
slot kit: the tall dark panel, an orange selection glow, two ornate gold rails
carrying an S-scroll motif, the dark red durability bar, small item-type
emblems, and - the thing Donnie asked about - the BROWN ELLIPTICAL PODIUM each
equipped item appears to stand on. Elden Ring just puts a flat icon in a square.

HOW IT WAS FOUND, after several wrong turns worth recording:
  * `MENU_EquipSlot` sounds right and is not it - flooded it, nothing changed.
  * `MENU_Dish` is literally named for the podium, is 320x128, brown with a
    gold rim, and is ALSO not it - flooded it, zero pixels changed on screen.
  * I had wrongly "ruled out" `MENU_ItemPanel_02` from runs that FAILED rather
    than runs that came back clean, so it sat on the excluded list for hours.

The thing that settled it was decompiling the HUD's own Scaleform movie and
reading its image table. `menu/01_000_fe.gfx` - NOT `02_000_ingametop.gfx`,
which is the start-menu root and references none of this - lists exactly 46
external images for the in-game overlay, and `MENU_ItemPanel_02` is char 19
while `MENU_Dish` does not appear at all. Read the manifest, do not guess.

THE PODIUM is removed by alpha rather than painted out, so nothing shows where
it used to be: the panel behind it is already dark, which is what ER has.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image

# The brown ellipse, located by colour within the 256x512 sheet.
PODIUM_BOX = (112, 172, 232, 224)          # x0, y0, x1, y1, generous
# ER's bone. The rails keep their shape - that is geometry, and geometry lives
# in fe.gfx - but they stop being gold and become ER's muted bone.
RAIL_BOXES = [(0, 148, 256, 174), (0, 176, 256, 196)]
ER_BONE = np.array([145.0, 139.0, 108.0])


def strip_podium(a: np.ndarray) -> int:
    x0, y0, x1, y1 = PODIUM_BOX
    patch = a[y0:y1, x0:x1]
    rgb = patch[..., :3].astype(float)
    # brown: warm, mid-dark, red clearly above blue
    brown = ((rgb[..., 0] > 28) & (rgb[..., 0] < 150)
             & (rgb[..., 0] > rgb[..., 2] + 12) & (patch[..., 3] > 40))
    n = int(brown.sum())
    patch[..., 3] = np.where(brown, 0, patch[..., 3])
    a[y0:y1, x0:x1] = patch
    return n


def tone_rails(a: np.ndarray) -> int:
    changed = 0
    for x0, y0, x1, y1 in RAIL_BOXES:
        patch = a[y0:y1, x0:x1]
        rgb = patch[..., :3].astype(float)
        vis = patch[..., 3] > 40
        gold = vis & (rgb[..., 0] > rgb[..., 2] + 8) & (rgb[..., 0] > 40)
        if not gold.any():
            continue
        lum = rgb.mean(axis=2, keepdims=True)
        scale = ER_BONE[None, None, :] / max(float(lum[gold].mean()), 1.0)
        out = np.clip(lum * scale, 0, 255)
        rgb[gold] = out[gold]
        patch[..., :3] = rgb.round().astype(np.uint8)
        a[y0:y1, x0:x1] = patch
        changed += int(gold.sum())
    return changed


def build(tpf_in: Path, tpf_out: Path, preview: Path | None = None) -> None:
    from oodle import dcx_decompress, dcx_compress_dflt
    from tpf_png import decode
    from soulstruct.containers import TPF
    from build_glyph_mod import dds_bgra

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    tex = [t for t in tpf.textures if t.stem == "MENU_ItemPanel_02"][0]
    a = np.asarray(decode(tex.data).convert("RGBA")).copy()

    n_pod = strip_podium(a)
    n_rail = tone_rails(a)
    print(f"  podium: {n_pod} px cleared to transparent")
    print(f"  rails : {n_rail} px retoned to ER bone {tuple(ER_BONE.astype(int))}")

    if preview:
        bg = Image.new("RGBA", (256, 260), (50, 80, 60, 255))
        bg.alpha_composite(Image.fromarray(a[:260], "RGBA"))
        bg.convert("RGB").resize((256 * 3, 260 * 3), Image.NEAREST).save(preview)

    tex.data = dds_bgra(Image.fromarray(a, "RGBA"))
    tex.format = 9
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
