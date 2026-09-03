#!/usr/bin/env python3
"""Relayout DS3's pause menu movie, menu/02_000_ingametop.gfx, as Elden Ring's.

The tree is in er_pause_menu.py's docstring. Everything below is measured on
ER's burst/pause-menu-1..3.png at 4K and written in stage px (4K / 2),
relative to the root `ItemList` sprite at stage (580, 640).

  * the five tiles (Item_0_0..4, plus the tile-less Item_0_5) go from a row
    at y -100, x -196..196 into a column: x -493, y -388.5 + 96k
    (ER: tile centres at 4K (174, 503 + 192k)).
  * each tile shape (65/62/59/56/53) becomes a 280x80 strip quad sampling its
    own atlas row, so the label art sits beside the tile (the movie has ONE
    engine-written label for the row; ER shows one per row).
  * the tile Cursor (MENU_ItemParts highlight, phase B's texture) is scaled
    to hug ER's 68 stage-px tile instead of the 90 px one.
  * the panel (sprite 23) becomes the column wash: scaled (0.6833, 2.0) to
    cover 4K -100..720 x 300..1900, its alphaMult 218 -> 256 so the texture's
    own alpha is what shows.
  * the orange rule (sprite 79) is dropped; RowText's rules and bands are
    dropped and both Text_0 fields parked 4000 px off screen.
  * the quick items (Item_1_0..4) become ER's Pouch grid on the right: 0.76
    scale, two columns at 4K x 3494/3654, rows y 590/768/946; shape 24 (the
    Dish) is retargeted from MENU_ItemPanel_02 to MENU_Top's pouch cell and
    centred under the icon; its Cursor scaled to the cell.
  * KeyGuide (A:OK B:Close) to ER's prompt position, 27 px em; the selected
    quick item's name (CurrentItemName) under the pouch grid.

    python er_pause_gfx.py <in.gfx> <out.gfx>
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FFDEC = Path.home() / "couch/data/ds3-ui-port/ffdec/ffdec.sh"

TILE_X = -493.0
TILE_Y0 = -388.5       # run 2 at -392.75 put the frames 9 px high on the clean rows; the "8.5 px low" reading had come from a row polluted by icon ink
ROW_PITCH = 96.0
STRIP = (-45.0, -40.0, 235.0, 40.0)     # stage px, tile centre at the origin
STRIP_V0, STRIP_H = 620, 80             # base texels
TILE_SHAPES = {65: 0, 62: 1, 59: 2, 56: 3, 53: 4}
TILE_SPRITES = ("67", "64", "61", "58", "55")
TILE_CURSOR_SCALE = 0.425               # 0.5625 * 68/90
WASH_SCALE = (0.68333, 2.0)
WASH_XY = (-425.0, -90.0)
POUCH_SCALE = 0.76
POUCH_XY = [(1167.0, -345.0), (1247.0, -345.0), (1167.0, -256.0), (1247.0, -256.0), (1167.0, -167.0)]
POUCH_UV = (300, 620)
POUCH_CURSOR_SCALE = 0.568
KEYGUIDE_XY = (-522.0, 140.0)      # run 1 at -518: text at 4K x 196 vs ER's 188; run 2 at -554 overshot (124)
KEYGUIDE_TWIPS = 540
CURRENT_XY = (1130.0, -111.0)
PARK_X = 300.0 if "--show-label" in sys.argv else -4000.0   # --show-label: DIAGNOSTIC, keeps the engine's own label on screen (mid-frame) to read which item each row is


def tw(px: float) -> int:
    return int(round(px * 20))


def bits(*vals: int) -> int:
    return max(abs(int(v)) for v in vals).bit_length() + 1


def matrix_xml(tx: float, ty: float, sx: float | None = None, sy: float | None = None) -> str:
    x, y = tw(tx), tw(ty)
    if sx is None:
        return (f'<matrix type="MATRIX" hasRotate="false" hasScale="false" nRotateBits="0" '
                f'nScaleBits="0" nTranslateBits="{bits(x, y)}" translateX="{x}" translateY="{y}"/>')
    return (f'<matrix type="MATRIX" hasRotate="false" hasScale="true" nRotateBits="0" '
            f'nScaleBits="16" nTranslateBits="{bits(x, y)}" scaleX="{sx}" scaleY="{sy}" '
            f'translateX="{x}" translateY="{y}"/>')


def sprite_span(t: str, sid: str) -> tuple[int, int]:
    m = re.search(r'<item type="DefineSpriteTag"[^>]*spriteId="%s"[^>]*>' % sid, t)
    nxt = t.find('<item type="DefineSpriteTag"', m.end())
    return m.start(), (nxt if nxt != -1 else len(t))


def in_sprite(t: str, sid: str, fn) -> tuple[str, int]:
    a, b = sprite_span(t, sid)
    body, n = fn(t[a:b])
    return t[:a] + body + t[b:], n


def set_place_matrix(body: str, char: str, depth: str, mat: str, name: str | None = None) -> tuple[str, int]:
    nm = f'[^>]*name="{name}"' if name else ""
    pat = (r'(<item type="PlaceObject[23]Tag" characterId="%s" depth="%s"%s[^>]*>\s*)<matrix[^>]*/>'
           % (char, depth, nm))
    return re.subn(pat, lambda m: m.group(1) + mat, body, count=1)


def drop_place(body: str, char: str, depth: str) -> tuple[str, int]:
    pat = re.compile(r'\s*<item type="PlaceObject[23]Tag" characterId="%s" depth="%s"[^>]*>.*?</item>'
                     % (char, depth), re.S)
    return pat.subn("", body, count=1)


def rect_shape(t: str, sid: int, x0: float, y0: float, x1: float, y1: float,
               u0: float, v0: float, bitmap: int | None = None) -> tuple[str, int]:
    """Rewrite a one-fill rectangle shape: bounds, bitmap translate, records.

    Texel = stage - translate/20 (bitmap matrix scale 20 = one texel per
    stage px), so translate = (x0 - u0) * 20. JPEXS bit widths: RECT nbits
    and moveBits = bitlen + 1, edge numBits = bitlen - 1 (fill_rim's finding).
    """
    m = re.search(r'<item type="DefineShapeTag"[^>]*shapeId="%d"[^>]*>' % sid, t)
    a = m.end()
    b = t.index("</shapeRecords>", a)
    blk = t[a:b]
    X0, Y0, X1, Y1 = tw(x0), tw(y0), tw(x1), tw(y1)
    W, H = X1 - X0, Y1 - Y0
    nb = bits(X0, Y0, X1, Y1)
    blk, k1 = re.subn(r'<shapeBounds type="RECT"[^>]*/>',
                      f'<shapeBounds type="RECT" Xmax="{X1}" Xmin="{X0}" Ymax="{Y1}" Ymin="{Y0}" nbits="{nb}"/>', blk, count=1)
    TX, TY = tw(x0 - u0), tw(y0 - v0)
    blk, k2 = re.subn(r'<bitmapMatrix type="MATRIX"[^>]*/>',
                      f'<bitmapMatrix type="MATRIX" hasRotate="false" hasScale="true" nRotateBits="0" '
                      f'nScaleBits="22" nTranslateBits="{bits(TX, TY)}" scaleX="20.0" scaleY="20.0" '
                      f'translateX="{TX}" translateY="{TY}"/>', blk, count=1)
    k3 = 0
    if bitmap is not None:
        blk, k3 = re.subn(r'bitmapId="\d+"', f'bitmapId="{bitmap}"', blk, count=1)
    eb = max(W, H).bit_length() - 1
    recs = (f'\n          <item type="StyleChangeRecord" fillStyle1="1" moveBits="{nb}" moveDeltaX="{X1}" moveDeltaY="{Y1}" '
            f'stateFillStyle0="false" stateFillStyle1="true" stateLineStyle="false" stateMoveTo="true" stateNewStyles="false"/>'
            f'\n          <item type="StraightEdgeRecord" deltaX="{-W}" generalLineFlag="false" numBits="{eb}" vertLineFlag="false"/>'
            f'\n          <item type="StraightEdgeRecord" deltaY="{-H}" generalLineFlag="false" numBits="{eb}" vertLineFlag="true"/>'
            f'\n          <item type="StraightEdgeRecord" deltaX="{W}" generalLineFlag="false" numBits="{eb}" vertLineFlag="false"/>'
            f'\n          <item type="StraightEdgeRecord" deltaY="{H}" generalLineFlag="false" numBits="{eb}" vertLineFlag="true"/>'
            f'\n          <item type="EndShapeRecord" endOfShape="0"/>\n        ')
    i = blk.index("<shapeRecords>") + len("<shapeRecords>")
    blk = blk[:i] + recs
    if k1 != 1 or k2 != 1:
        raise SystemExit(f"shape {sid}: bounds {k1} matrix {k2}")
    return t[:a] + blk + t[b:], 1 + k3


def edit(t: str) -> str:
    n = 0

    def count(res, want, what):
        nonlocal n
        body, k = res
        if k != want:
            raise SystemExit(f"{what}: expected {want} edits, made {k}")
        n += k
        return body

    # 1. tiles into a column (sprite 86), the sixth too
    def tiles(body):
        k = 0
        for i, (char, depth) in enumerate([("67", "56"), ("64", "52"), ("61", "48"), ("58", "44"), ("55", "40"), ("52", "38")]):
            body, j = set_place_matrix(body, char, depth, matrix_xml(TILE_X, TILE_Y0 + ROW_PITCH * i), f"Item_0_{i}")
            k += j
        return body, k
    t = count(in_sprite(t, "86", tiles), 6, "tile placements")
    # 2. tile quads -> strips
    for sid, k in TILE_SHAPES.items():
        t = count(rect_shape(t, sid, *STRIP, 0, STRIP_V0 + STRIP_H * k), 1, f"strip shape {sid}")
    # 3. tile cursors
    for sid in TILE_SPRITES:
        t = count(in_sprite(t, sid, lambda b: set_place_matrix(
            b, "50", "3", matrix_xml(0, 0, TILE_CURSOR_SCALE, TILE_CURSOR_SCALE), "Cursor")), 1, f"cursor in {sid}")
    # 4. the wash
    t = count(in_sprite(t, "86", lambda b: set_place_matrix(
        b, "23", "1", matrix_xml(*WASH_XY, *WASH_SCALE))), 1, "wash placement")
    t = count(in_sprite(t, "23", lambda b: re.subn(r'alphaMultTerm="218"', 'alphaMultTerm="256"', b, count=1)), 1, "wash cxform")
    # 5. the orange rule
    t = count(in_sprite(t, "86", lambda b: drop_place(b, "79", "68")), 1, "orange rule")
    # 6. RowText: rules and bands out, labels parked
    for sid, txt in (("76", "75"), ("74", "73")):
        t = count(in_sprite(t, sid, lambda b: drop_place(b, "70", "1")), 1, f"band in {sid}")
        t = count(in_sprite(t, sid, lambda b: drop_place(b, "72", "3")), 1, f"rule in {sid}")
        t = count(in_sprite(t, sid, lambda b, txt=txt: set_place_matrix(
            b, txt, "5", matrix_xml(PARK_X, -32.0), "Text_0")), 1, f"label in {sid}")
    # 7. quick items -> pouch grid
    def pouch(body):
        k = 0
        for i, (depth, xy) in enumerate(zip(("31", "24", "17", "10", "3"), POUCH_XY)):
            body, j = set_place_matrix(body, "51", depth, matrix_xml(*xy, POUCH_SCALE, POUCH_SCALE), f"Item_1_{i}")
            k += j
        return body, k
    t = count(in_sprite(t, "86", pouch), 5, "pouch placements")
    # 8. the Dish -> ER's pouch cell from MENU_Top (bitmap 1)
    t = count(rect_shape(t, 24, -80, -80, 80, 80, *POUCH_UV, bitmap=1), 2, "pouch cell shape")
    # 9. the quick-item cursor
    t = count(in_sprite(t, "51", lambda b: set_place_matrix(
        b, "50", "6", matrix_xml(0, 0, POUCH_CURSOR_SCALE, POUCH_CURSOR_SCALE), "Cursor")), 1, "pouch cursor")
    # 10. the prompts
    t = count(in_sprite(t, "81", lambda b: set_place_matrix(b, "80", "1", matrix_xml(*KEYGUIDE_XY), "KeyGuide")), 1, "KeyGuide")
    t = count(re.subn(r'(<item type="DefineEditTextTag"[^>]*characterID="80"[^>]*fontHeight=")\d+(")',
                      lambda m: f'{m.group(1)}{KEYGUIDE_TWIPS}{m.group(2)}', t, count=1), 1, "KeyGuide size")
    # 11. the selected quick item's name
    t = count(in_sprite(t, "83", lambda b: set_place_matrix(b, "82", "1", matrix_xml(*CURRENT_XY), "CurrentItemName")), 1, "CurrentItemName")
    print(f"  er-pause: {n} edits")
    return t


GRID_RENAME = "--grid-rename" in sys.argv


def grid_rename(t: str) -> tuple[str, int]:
    """EXPERIMENT: rename the tiles Item_0_k -> Item_k_0 and the quick items
    Item_1_k -> Item_k_1. The engine walks the pause list with Left/Right
    because the tiles are named as row 0's five COLUMNS; if it builds its
    navigation grid from the instance names, five rows of one column would
    make Up/Down walk ER's vertical list. One capture (DS3SHOT_PAUSE=down)
    answers it."""
    n = 0
    for k in range(6):
        t, c = re.subn(r'name="Item_0_%d"' % k, 'name="ITEMTMP_%d_0"' % k, t); n += c
    for k in range(5):
        t, c = re.subn(r'name="Item_1_%d"' % k, 'name="ITEMTMP_%d_1"' % k, t); n += c
    t = t.replace('name="ITEMTMP_', 'name="Item_')
    return t, n


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        raise SystemExit(__doc__)
    src, dst = Path(args[0]), Path(args[1])
    with tempfile.TemporaryDirectory() as d:
        xin, xout = Path(d) / "in.xml", Path(d) / "out.xml"
        subprocess.run([str(FFDEC), "-swf2xml", str(src), str(xin)], check=True, capture_output=True, timeout=600)
        edited = edit(xin.read_text(encoding="utf-8"))
        if GRID_RENAME:
            edited, k = grid_rename(edited)
            print(f"  grid-rename: {k} names")
        xout.write_text(edited, encoding="utf-8")
        subprocess.run([str(FFDEC), "-xml2swf", str(xout), str(dst)], check=True, capture_output=True, timeout=600)
        Path(dst.with_suffix(".xml")).write_text(xout.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"wrote {dst} ({dst.stat().st_size} bytes; original {src.stat().st_size})")


if __name__ == "__main__":
    main()
