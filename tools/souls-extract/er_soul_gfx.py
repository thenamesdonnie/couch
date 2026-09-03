#!/usr/bin/env python3
"""Move and size DS3's souls counter movie to Elden Ring's rune counter.

`menu/01_001_fe_soul.gfx` (see er_soul_counter.py for the tree). Edits, all
measured at 4K against ER's hud_full:

  * root `Soul` sprite: (1713, 990) -> (1771, 1034.5). ER's panel is centred
    at 4K (3541.5, 2069); DS3's sat 120 px further left and 90 px higher.
  * the medallion quad: (-80, 0) -> (-76, 0). ER's medallion centre is 151 px
    from the panel's left edge at 4K; DS3's was 160.
  * TotalSoul number: 24 px em -> 22.5 (ER's digits are 30 px tall at 4K
    against Spectral SemiBold's 32 at 24), and its right edge pulled in so the
    digits end 30 px inside the panel as ER's do (DS3: 19), 4 px lower.
  * the panel sprite's alphaMult 0.70 neutralised (the texture carries ER's
    measured alpha; the transform on top of it let the scene through).

JPEXS round trip, same as er_fe_gfx.py.

    python er_soul_gfx.py <in.gfx> <out.gfx>
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FFDEC = Path.home() / "couch/data/ds3-ui-port/ffdec/ffdec.sh"

ROOT_XY = (1771.0, 1034.5)      # stage px
ICON_X = -76.0
TEXT_EM = 22.5                  # stage px
TEXT_DX = -8.5                  # stage px, on the inner Text (run 4: -14 there put the digits 11 px too far left)
TEXT_DY = 2.0                   # ER's digits sit 4 px lower at 4K


def tw(px: float) -> int:
    return int(round(px * 20))


def edit(t: str) -> str:
    # 1. root placement (sprite 0, name="Soul")
    def root(m):
        blk = m.group(0)
        blk = re.sub(r'translateX="-?\d+"', f'translateX="{tw(ROOT_XY[0])}"', blk, count=1)
        blk = re.sub(r'translateY="-?\d+"', f'translateY="{tw(ROOT_XY[1])}"', blk, count=1)
        return blk
    t, n = re.subn(r'<item type="PlaceObject2Tag" characterId="12"[^>]*name="Soul"[^>]*>\s*<matrix[^>]*/>', root, t)
    assert n == 1, f"root Soul placement: {n}"

    # 2. the icon quad (sprite 5 at depth 3 inside sprite 6)
    t, n = re.subn(r'(<item type="PlaceObject2Tag" characterId="5" depth="3"[^>]*>\s*<matrix[^>]*translateX=")-?\d+(")',
                   lambda m: f'{m.group(1)}{tw(ICON_X)}{m.group(2)}', t)
    assert n == 1, f"icon placement: {n}"

    # 3. TotalSoul: font size (text 9) and placement (sprite 10 named TotalSoul)
    t, n = re.subn(r'(<item type="DefineEditTextTag"[^>]*characterID="9"[^>]*fontHeight=")\d+(")',
                   lambda m: f'{m.group(1)}{tw(TEXT_EM)}{m.group(2)}', t)
    assert n == 1, f"TotalSoul text: {n}"

    def total(m):
        blk = m.group(0)
        mm = re.search(r'translateX="(-?\d+)"', blk)
        blk = blk.replace(mm.group(0), f'translateX="{int(mm.group(1)) + tw(TEXT_DX)}"', 1)
        mm = re.search(r'translateY="(-?\d+)"', blk)
        return blk.replace(mm.group(0), f'translateY="{int(mm.group(1)) + tw(TEXT_DY)}"', 1)
    # RUN 3: moving TotalSoul itself did nothing - the engine sets that
    # instance's position at runtime. Its child Text (char 9 inside sprite 10)
    # is not touched by script, so the offset goes there.
    t, n = re.subn(r'<item type="PlaceObject3Tag" characterId="9"[^>]*name="Text"[^>]*>\s*<matrix[^>]*/>', total, t)
    assert n == 1, f"TotalSoul Text placement: {n}"
    # 4. the panel+icon sprite (6) carries alphaMult 179/256 = 0.70, which is
    #    how DS3 makes its own panel faint. Ours carries its alpha in the
    #    texture (measured off ER), so the transform goes to 1.0 or the field
    #    lands at 0.65*0.70 = 0.46 and the rock shows through (run 1).
    t, n = re.subn(r'(<item type="PlaceObject2Tag" characterId="6" depth="1"[^>]*>\s*<matrix[^>]*/>\s*<colorTransform[^>]*alphaMultTerm=")\d+(")',
                   lambda m: f'{m.group(1)}256{m.group(2)}', t)
    assert n == 1, f"panel cxform: {n}"
    # make sure the translate fields have room (JPEXS recomputes on write, but be explicit)
    t = re.sub(r'nTranslateBits="\d+"', 'nTranslateBits="16"', t)
    return t


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    with tempfile.TemporaryDirectory() as d:
        xin, xout = Path(d) / "in.xml", Path(d) / "out.xml"
        subprocess.run([str(FFDEC), "-swf2xml", str(src), str(xin)], check=True, capture_output=True, timeout=600)
        xout.write_text(edit(xin.read_text()))
        subprocess.run([str(FFDEC), "-xml2swf", str(xout), str(dst)], check=True, capture_output=True, timeout=600)
    print(f"wrote {dst} ({dst.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
