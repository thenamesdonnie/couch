"""Compose DARK SOULS III - ELDEN RING EDITION for DS3's title screen.

Deliberately a joke, and also the best possible mod-loading test: one texture,
unmissable on screen, so "did the mod load" is answered in one launch.

The EDITION word is DS3's OWN letterforms, lifted out of the original subtitle
rather than set in a lookalike font, so weathering and tracking match exactly.
Only ELDEN RING is imported art.

That was forced rather than chosen: DS3's logo cannot spell it. Between
"DARK SOULS III" and "THE FIRE FADES EDITION" the texture has most of the
alphabet but NO G, so "RING" is impossible in the native font.

Two things learned composing it, both invisible until you look at native size:
  * Crop the Elden Ring LETTERS only (y 520-880 in the extracted panel, a 6.9:1
    band). The ring artwork sits below them and turns into a grey smudge once
    shrunk to subtitle height.
  * The gold needs about a 1.35x brightness lift to stay legible at 70px tall.

Slot facts: MENU_DS3_LOGO is 2048x512, fully opaque with no alpha anywhere, so
the background must be black. The subtitle band sits at y 435-483 and the
original spans x 82-1024, centred on x=553.
"""
from __future__ import annotations

import sys
from pathlib import Path


def build(ds3_logo_png: Path, er_panel_png: Path, out_png: Path) -> None:
    from PIL import Image, ImageEnhance
    import numpy as np

    logo = Image.open(ds3_logo_png).convert("RGB")

    edition = logo.crop((720, 425, 1045, 495))
    a = np.asarray(edition.convert("L"))
    ys, xs = np.where(a > 40)
    edition = edition.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))

    er = Image.open(er_panel_png).convert("RGB").crop((24, 512, 2512, 888))
    er = ImageEnhance.Brightness(er).enhance(1.35)
    H = 70
    erw = er.resize((int(er.width * H / er.height), H), Image.LANCZOS)

    out = logo.copy()
    out.paste((0, 0, 0), (0, 412, 2048, 508))     # clear the old subtitle
    gap = 44
    total = erw.width + gap + edition.width
    x0, cy = 553 - total // 2, 460
    out.paste(erw, (x0, cy - erw.height // 2))
    out.paste(edition, (x0 + erw.width + gap, cy - edition.height // 2))
    out.save(out_png)
    print(f"wrote {out_png}: lockup {total}px at x{x0}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    build(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
