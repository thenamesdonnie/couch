"""Empirical atlas mapper: flood MENU_PlayerHUD2's strips with tracer colours.

Each candidate strip gets a unique flat colour plus black notches at
x=64/128/192 (widths 2/4/6 px so a screenshot identifies WHICH notch it sees).
Build the tpf, boot through ds3-shot, and read off from the in-game capture
which atlas rect feeds which HUD element and at what scale. This is how
hud_atlas_map.json was derived on 2 Sep 2026; see that file for the results.

The tracer palette is probe-legal: ds3-shot's hud probe needs red-dominant
pixels in the HP band and green-dominant in the stamina band, so the strips
that were suspected to feed those bars stay red/green enough to let the
unattended inventory journey pass.

    python flood_map_hud.py <in.tpf.dcx> <out.tpf.dcx>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

REGIONS = [  # (y0, y1, rgb, tag)
    (6,   22,  (255, 0, 255),   "backdrop -> magenta"),
    (28,  42,  (255, 0, 0),     "red block A -> pure red"),
    (42,  52,  (255, 140, 0),   "red block B -> orange"),
    (52,  66,  (0, 255, 0),     "green block A -> pure green"),
    (66,  76,  (0, 220, 140),   "green block B -> teal"),
    (76,  90,  (0, 90, 255),    "blue block A -> azure"),
    (90,  100, (150, 0, 255),   "blue block B -> violet"),
    (100, 114, (255, 255, 0),   "olive block A -> yellow"),
    (114, 124, (255, 255, 255), "olive block B -> white"),
]
NOTCHES = [(63, 65), (126, 130), (189, 195)]


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    tpf_in, tpf_out = Path(sys.argv[1]), Path(sys.argv[2])

    import tempfile
    import numpy as np
    from PIL import Image
    from tpf_png import decode
    from oodle import dcx_decompress
    from soulstruct.containers import TPF
    from replace_texture import replace

    tpf = TPF.from_bytes(dcx_decompress(tpf_in.read_bytes()))
    src = decode([t for t in tpf.textures if t.stem == "MENU_PlayerHUD2"][0].data)
    a = np.asarray(src.convert("RGBA")).copy()
    for y0, y1, rgb, tag in REGIONS:
        a[y0:y1, :, :3] = rgb
        a[y0:y1, :, 3] = 255
        for x0, x1 in NOTCHES:
            a[y0:y1, x0:x1, :3] = 0
        print(f"  rows {y0}-{y1}: {tag}")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        Image.fromarray(a).save(f.name)
        replace(tpf_in, "MENU_PlayerHUD2", Path(f.name), tpf_out)


if __name__ == "__main__":
    main()
