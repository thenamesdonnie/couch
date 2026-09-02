"""Patch DS3's in-game HUD Scaleform movie, menu/01_000_fe.gfx.

THE FINDING THIS EXISTS FOR. I spent a long time concluding that the +34 lift on
the gauge fill was engine-side and irreducible - that reaching Elden Ring's real
green (26) and blue (22) would mean patching DarkSoulsIII.exe. That was WRONG,
and it was wrong in a way worth recording, because the reasoning looked sound:

    * I checked `menu/02_000_ingametop.gfx` for a HUD colour transform, found it
      referenced none of the HUD textures, and concluded no HUD .gfx existed.
      02_* is the START MENU stack. The in-game HUD is `01_000_fe.gfx` ("front
      end"), which I never opened.
    * I then "proved" the lift was engine-side by elimination - blacking the
      backdrop, MENU_PlayerHUD, MENU_HUD_Status, varying alpha, an all-black
      bar. Every one of those tests was sound and every one was consistent with
      a Scaleform colour transform, which is exactly what it turned out to be.
      Eliminating asset causes does not prove an ENGINE cause.

The actual source, in sprite 471's three bar placements (names HP / MP / SP):

    CXFORMWITHALPHA  mult 230/256 = 0.898   add +26 on R, G and B

0.898x + 26, then DS3's downstream gamma, lands on the 0.87x + 34 I measured
off the ramp. Zeroing it lets the texture reach ER's colours directly, with no
post-process pass involved.

WHAT THIS SCRIPT CAN DO
    --neutral-cxform    set the three bar cxforms to mult 256 / add 0
    --scale-cap N       scale the left end-cap (sprite 361, depth 17, one
                        matrix, shared by all three bars)
    --drop-dish         remove the brown elliptical item base (three named
                        `Dish` placements) instead of erasing it from a texture

ROUND-TRIP SAFETY was checked before any of this: JPEXS xml2swf reproduces a
554296-byte file, the same size as the original, with 12 bytes differing - all
of them re-encodings of zero with fewer bits - and a second round trip is
byte-identical, i.e. it converges. Loading in game is the part only a real run
can prove.

    python er_fe_gfx.py <in.gfx> <out.gfx> [--neutral-cxform] [--scale-cap N] [--drop-dish]
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

FFDEC = Path.home() / "couch/data/ds3-ui-port/ffdec/ffdec.sh"

# The three player bars live here. Anything else carrying an additive cxform in
# this file is the item-flash or the covenant-badge pulse and must be left be.
BAR_NAMES = ("HP", "MP", "SP")


def to_xml(gfx: Path, xml: Path) -> None:
    subprocess.run([str(FFDEC), "-swf2xml", str(gfx), str(xml)],
                   check=True, capture_output=True, timeout=600)


def to_gfx(xml: Path, gfx: Path) -> None:
    subprocess.run([str(FFDEC), "-xml2swf", str(xml), str(gfx)],
                   check=True, capture_output=True, timeout=600)


def neutral_cxform(t: str) -> tuple[str, int]:
    """Zero the additive lift on the three bar placements only."""
    n = 0

    def fix(m: re.Match) -> str:
        nonlocal n
        block = m.group(0)
        if not any(f'name="{b}"' in block for b in BAR_NAMES):
            return block
        new = re.sub(r'(red|green|blue)AddTerm="\d+"',
                     lambda a: f'{a.group(1)}AddTerm="0"', block)
        new = re.sub(r'(red|green|blue)MultTerm="\d+"',
                     lambda a: f'{a.group(1)}MultTerm="256"', new)
        if new != block:
            n += 1
        return new

    # One PlaceObject2Tag element, including its nested colorTransform.
    pat = re.compile(r'<item type="PlaceObject2Tag"[^>]*name="(?:HP|MP|SP)"'
                     r'.*?</item>', re.S)
    return pat.sub(fix, t), n


def scale_cap(t: str, factor: float) -> tuple[str, int]:
    """Scale the shared left end-cap placement (sprite 361, depth 17)."""
    n = 0
    fixed = 1 << 16
    val = int(round(factor * fixed))

    def fix(m: re.Match) -> str:
        nonlocal n
        block = m.group(0)
        if 'characterId="358"' not in block or 'depth="17"' not in block:
            return block
        if "<matrix" not in block:
            return block
        new = re.sub(
            r'<matrix type="MATRIX"[^/]*/>',
            f'<matrix type="MATRIX" hasRotate="false" hasScale="true" '
            f'nRotateBits="0" nScaleBits="20" nTranslateBits="0" '
            f'scaleX="{val}" scaleY="{val}" translateX="0" translateY="0"/>',
            block)
        if new != block:
            n += 1
        return new

    pat = re.compile(r'<item type="PlaceObject2Tag"[^>]*>.*?</item>', re.S)
    return pat.sub(fix, t), n


def drop_dish(t: str) -> tuple[str, int]:
    """Remove the brown elliptical item base placements."""
    pat = re.compile(r'\s*<item type="PlaceObject2Tag"[^>]*name="Dish"[^>]*>'
                     r'.*?</item>', re.S)
    out, n = pat.subn("", t)
    return out, n


def main() -> None:
    argv = sys.argv[1:]
    do_cx = "--neutral-cxform" in argv
    do_dish = "--drop-dish" in argv
    cap = None
    if "--scale-cap" in argv:
        i = argv.index("--scale-cap")
        cap = float(argv[i + 1])
        del argv[i:i + 2]
    argv = [a for a in argv if not a.startswith("--")]
    if len(argv) != 2:
        print(__doc__)
        sys.exit(1)
    src, dst = Path(argv[0]), Path(argv[1])

    with tempfile.TemporaryDirectory() as td:
        xml = Path(td) / "fe.xml"
        print(f"  decompiling {src.name} ...")
        to_xml(src, xml)
        t = xml.read_text(encoding="utf-8", errors="replace")
        before = len(t)

        if do_cx:
            t, n = neutral_cxform(t)
            print(f"  neutralised the colour transform on {n} bar placements "
                  f"(was mult 230 / add 26)")
            if n != 3:
                raise SystemExit(f"expected 3 bar placements, patched {n} - refusing")
        if cap is not None:
            t, n = scale_cap(t, cap)
            print(f"  scaled the end-cap x{cap} on {n} placement(s)")
            if n != 1:
                raise SystemExit(f"expected 1 cap placement, patched {n} - refusing")
        if do_dish:
            t, n = drop_dish(t)
            print(f"  removed {n} 'Dish' (item base) placements")

        print(f"  xml {before:,} -> {len(t):,} bytes")
        xml.write_text(t, encoding="utf-8")
        print("  recompiling ...")
        to_gfx(xml, dst)

    print(f"  wrote {dst} ({dst.stat().st_size:,} bytes; "
          f"original {src.stat().st_size:,})")


if __name__ == "__main__":
    main()
