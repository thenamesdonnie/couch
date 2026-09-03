#!/usr/bin/env python3
"""Retype DS3's start-menu movies (menu/02_*.gfx) to Elden Ring's measured typography.

PHASE C of the menu port (docs/research/ds3-er-menus-survey-20260903.md). Every
number here was measured at native 4K on the ER burst frames
(er-reference/burst/equipment-screen.png, inventory-key-items.png,
stats-screen.png) against the DS3 4K captures (ds3_equipment_4k.png,
ds3_inventory_4k.png), glyph by glyph, with the session's textrows.py /
glyphs.py. What the measurements said, and therefore what this edits:

  * BODY TEXT IS ALREADY ER'S SIZE. Labels 'L' cap 31-32 px on both games
    (480 twips = 24 stage px, cap 0.667 em), digits 27-28 px (420 twips),
    row pitch 59-60 px in the equipment/inventory status column and 64 on
    the status screen, both games. The survey's "ER's sizes are smaller"
    was wrong: nothing in the body changes size.
  * ER'S BODY COLOUR IS NEUTRAL (204,204,204), the same #cccccc DS3 uses for
    most fields, and its headers are the same gold (192,177,148). The "warm
    off-white" is the olive wash behind the anti-aliased edges, not the
    core. What DOES differ: DS3 paints its stat labels and every value in a
    greenish (193,194,178). ER has one grey for label and value. So every
    (193,194,178) field goes to (204,204,204).
  * THE TITLE IS BIGGER AND HIGHER. ER 'E' cap 43 px at 4K (DS3 40), cap top
    y 97 (DS3 156), left x 245 (DS3 287); its icon is the same 120 px but
    centred at (156.5,111.5) against DS3's (207.5,173.5). Title text
    600 -> 645 twips; the Text_0 and icon placements INSIDE MenuTitle move
    (the root instance may be engine-positioned, its children are not).
  * THE CENTRE COLUMN'S ITEM NAME IS BIGGER. ER 'R' cap 40 (600 twips) where
    DS3 draws it at 480. Kept on DS3's baseline (the field moves up 6 stage
    px), same x: in both games the name sits ~55 px left of the label column.
  * THE PROMPT BAR SITS LOWER AND FURTHER RIGHT. ER's "Select item to equip"
    baseline 2021 / second line 2094, x 246; DS3 1962 / 2034, x 206. The two
    text fields inside StatusBar move (+20, +30) stage px.
  * The status screen's player name (ER "Arcana": grey, cap 40) goes from
    gold 480 to grey 600.

Layout model used for the y numbers (checked on the subtitle and prompt bar
before use): first baseline = field top + 2 + 1.0 * em for MenuFont_01, cap
height 0.667 em. See RECIPE "The area name card" for the same model on the
HUD movie.

    er_menu_gfx.py <in.gfx> <out.gfx> --screen equiptop|equip|inventory|status|weapon1|player|item
                   [--tracer] [--keep-title] [--keep-prompt] [--no-gamma]

--tracer paints one field per movie a pure colour (equiptop ItemName red,
equip WindowList name blue) so a capture can say which movie the harness
screenshot is showing. Not for the build.

JPEXS round trip as er_fe_gfx.py; every edit is counted and asserted.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FFDEC = Path.home() / "couch/data/ds3-ui-port/ffdec/ffdec.sh"

ER_GREY = (204, 204, 204)          # ER body text, measured mode (3149 px at exactly 204)
ER_GOLD = (192, 177, 148)          # ER headers/title, measured mode; DS3 authors the same #c0b194
DS3_GREEN = (193, 194, 178)        # DS3's label/value tint, absent from ER

# DS3 draws text through the same output transfer the HUD textures go through
# (RECIPE: screen = 255*(c/255)^0.8795): authored 204 reads 210 on screen and
# (192,177,148) reads (199,185,158), measured on run 1 and on the baseline
# capture. ER's screen values ARE its authored values. So the authored colours
# are pre-compensated: 198 reads 204.1, (185,168,137) reads (192.3,176.7,147.7).
SCREEN_GAMMA = 0.8795


def authored(rgb):
    return tuple(int(round(255 * (c / 255) ** (1 / SCREEN_GAMMA))) for c in rgb)


GREY_AUTH = authored(ER_GREY)      # (198,198,198)
GOLD_AUTH = authored(ER_GOLD)      # (185,168,137)

TITLE_TWIPS = 645                  # 600 * 43/40
TITLE_TEXT_XY = (-147.0, -49.25)   # stage px, Text_0 inside MenuTitle (was -126, -19)
TITLE_ICON_XY = (-189.5, -31.0)    # stage px, icon sprite inside MenuTitle (was -164, 0)
NAME_TWIPS = 600                   # centre-column item name / status player name
NAME_DY = -6.0                     # keep the baseline where DS3 had it at 480
PROMPT_DXY = (20.0, 30.0)          # KeyGuide / LineHelp inside StatusBar

# Per screen: which ids to touch. "green" = every DefineEditText whose textColor
# is DS3_GREEN (asserted count), so a stray extra field is caught.
SCREENS = {
    "equiptop": dict(engine=4, 
        title=dict(text=76, sprite=77, icon=75), green=5, grey=11, gold=2,
        prompt=dict(sprite=70, texts=(68, 69)),
        tracer=dict(text=82, rgb=(255, 0, 0)),
    ),
    "equip": dict(engine=4, 
        title=dict(text=185, sprite=186, icon=184), green=5, grey=11, gold=2,
        prompt=dict(sprite=179, texts=(177, 178)),
        tracer=dict(text=169, rgb=(0, 0, 255)),
    ),
    "inventory": dict(engine=5, 
        title=dict(text=362, sprite=363, icon=361), green=5, grey=12, gold=3,
        prompt=dict(sprite=351, texts=(349, 350)),
    ),
    "status": dict(engine=8, 
        title=dict(text=40, sprite=41, icon=39), green=16, grey=19, gold=5,
        prompt=dict(sprite=34, texts=(32, 33)),
        name=dict(text=216, sprite=217, grey=True),
    ),
    # the detail-column movies the engine loads into DetailStatusView
    "weapon1": dict(engine=16, green=16, grey=28, gold=2, name=dict(text=144, sprite=145)),
    "player": dict(engine=3, green=6, grey=6, gold=1),
    "item": dict(engine=6, green=6, grey=10, gold=1, name=dict(text=69, sprite=70)),
}


def tw(px: float) -> int:
    return int(round(px * 20))


def to_xml(gfx: Path, xml: Path) -> None:
    subprocess.run([str(FFDEC), "-swf2xml", str(gfx), str(xml)], check=True, capture_output=True, timeout=600)


def to_gfx(xml: Path, gfx: Path) -> None:
    subprocess.run([str(FFDEC), "-xml2swf", str(xml), str(gfx)], check=True, capture_output=True, timeout=600)


# ----------------------------------------------------------------- primitives
def _text_block(t: str, cid: int):
    m = re.search(r'<item type="DefineEditTextTag"[^>]*characterID="%d"[^>]*>.*?</item>' % cid, t, re.S)
    assert m, f"DefineEditText {cid} not found"
    return m


def set_font_height(t: str, cid: int, twips: int) -> str:
    m = _text_block(t, cid)
    blk = m.group(0)
    old = int(re.search(r'fontHeight="(\d+)"', blk).group(1))
    new = re.sub(r'fontHeight="\d+"', f'fontHeight="{twips}"', blk, count=1)
    # grow the bounds with the font so nothing clips or wraps early
    k = twips / old

    new, n = re.subn(r'<bounds type="RECT" Xmax="(\d+)" Xmin="(-?\d+)" Ymax="(\d+)" Ymin="(-?\d+)" nbits="\d+"/>',
                     lambda mm: (f'<bounds type="RECT" Xmax="{int(round(int(mm.group(1)) * k))}" Xmin="{mm.group(2)}" '
                                 f'Ymax="{int(round(int(mm.group(3)) * k))}" Ymin="{mm.group(4)}" nbits="16"/>'), new, count=1)
    assert n == 1, f"bounds of text {cid}: {n}"
    assert new != blk
    return t[:m.start()] + new + t[m.end():]


def set_colour(t: str, cid: int, rgb) -> str:
    m = _text_block(t, cid)
    blk = m.group(0)
    new, n = re.subn(r'<textColor type="RGBA" alpha="(\d+)" blue="\d+" green="\d+" red="\d+"/>',
                     lambda mm: f'<textColor type="RGBA" alpha="{mm.group(1)}" blue="{rgb[2]}" green="{rgb[1]}" red="{rgb[0]}"/>',
                     blk, count=1)
    assert n == 1, f"textColor of {cid}"
    return t[:m.start()] + new + t[m.end():]


def recolour_all(t: str, src, dst) -> tuple[str, int]:
    pat = (r'<textColor type="RGBA" alpha="(\d+)" blue="%d" green="%d" red="%d"/>' % (src[2], src[1], src[0]))
    return re.subn(pat, lambda mm: f'<textColor type="RGBA" alpha="{mm.group(1)}" blue="{dst[2]}" green="{dst[1]}" red="{dst[0]}"/>', t)


def _sprite_span(t: str, sid: int):
    m = re.search(r'<item type="DefineSpriteTag"[^>]*spriteId="%d"[^>]*>' % sid, t)
    assert m, f"sprite {sid} not found"
    end = t.index("\n    </item>", m.end())
    return m.start(), end


def move_placement(t: str, sid: int, cid: int, xy=None, dxy=None) -> str:
    """Set (xy) or offset (dxy) the matrix translate of character cid's placement inside sprite sid."""
    s, e = _sprite_span(t, sid)
    blk = t[s:e]
    pat = re.compile(r'(<item type="PlaceObject[23]Tag" characterId="%d" [^>]*>\s*<matrix type="MATRIX"[^>]*?)'
                     r'nTranslateBits="\d+"([^>]*?)translateX="(-?\d+)" translateY="(-?\d+)"' % cid)

    def fix(mm):
        x, y = int(mm.group(3)), int(mm.group(4))
        if xy is not None:
            x, y = tw(xy[0]), tw(xy[1])
        else:
            x, y = x + tw(dxy[0]), y + tw(dxy[1])
        return f'{mm.group(1)}nTranslateBits="16"{mm.group(2)}translateX="{x}" translateY="{y}"'
    new, n = pat.subn(fix, blk)
    assert n == 1, f"placement of {cid} in sprite {sid}: {n} matches"
    return t[:s] + new + t[e:]


ENGINE_NAMES = re.compile(r'^(Value|OwnNum|RequiredNum|StockNum)')
ENGINE_MULT = 248
CXFORM = ('<colorTransform type="CXFORMWITHALPHA" alphaMultTerm="256" blueMultTerm="%d" greenMultTerm="%d" '
          'hasAddTerms="false" hasMultTerms="true" nbits="10" redMultTerm="%d"/>' % (ENGINE_MULT, ENGINE_MULT, ENGINE_MULT))


def engine_group(t: str):
    """Add the dimming cxform to every placement of a text field the engine colours (by instance name)."""
    texts = set(int(m) for m in re.findall(r'<item type="DefineEditTextTag"[^>]*characterID="(\d+)"', t))
    ids = set()
    n = 0

    def fix(m):
        nonlocal n
        tag, matrix = m.group(1), m.group(2)
        cid = int(re.search(r'characterId="(\d+)"', tag).group(1))
        nm = re.search(r' name="([^"]*)"', tag)
        if cid not in texts or not nm or not ENGINE_NAMES.match(nm.group(1)):
            return m.group(0)
        assert 'placeFlagHasColorTransform="false"' in tag, f"text {cid} already carries a cxform"
        n += 1
        ids.add(cid)
        tag = tag.replace('placeFlagHasColorTransform="false"', 'placeFlagHasColorTransform="true"')
        indent = re.search(r'\n(\s*)<matrix', m.group(0)).group(1)
        return tag + matrix + "\n" + indent + CXFORM

    pat = re.compile(r'(<item type="PlaceObject[23]Tag" characterId="\d+"[^>]*>)(\s*<matrix type="MATRIX"[^>]*/>)')
    t = pat.sub(fix, t)
    return t, n, ids


# ----------------------------------------------------------------- the edits
def edit(t: str, screen: str, tracer: bool, keep_title: bool, keep_prompt: bool, no_gamma: bool = False) -> tuple[str, list[str]]:
    cfg = SCREENS[screen]
    log = []
    # 1. colours: every DS3-green field to ER's grey
    t, n = recolour_all(t, DS3_GREEN, ER_GREY)
    assert n == cfg["green"], f"{screen}: {n} green fields, expected {cfg['green']}"
    log.append(f"{n} fields {DS3_GREEN} -> {ER_GREY}")
    # 2. the title
    if "title" in cfg and not keep_title:
        c = cfg["title"]
        t = set_font_height(t, c["text"], TITLE_TWIPS)
        t = move_placement(t, c["sprite"], c["text"], xy=TITLE_TEXT_XY)
        t = move_placement(t, c["sprite"], c["icon"], xy=TITLE_ICON_XY)
        log.append(f"title text {c['text']} -> {TITLE_TWIPS} twips at {TITLE_TEXT_XY}, icon {c['icon']} at {TITLE_ICON_XY}")
    # 3. the prompt bar
    if "prompt" in cfg and not keep_prompt:
        c = cfg["prompt"]
        for cid in c["texts"]:
            t = move_placement(t, c["sprite"], cid, dxy=PROMPT_DXY)
        log.append(f"prompt texts {c['texts']} moved by {PROMPT_DXY}")
    # 4. the big name (centre column item name / status player name)
    if "name" in cfg:
        c = cfg["name"]
        t = set_font_height(t, c["text"], NAME_TWIPS)
        t = move_placement(t, c["sprite"], c["text"], dxy=(0.0, NAME_DY))
        if c.get("grey"):
            t = set_colour(t, c["text"], ER_GREY)
        log.append(f"name text {c['text']} -> {NAME_TWIPS} twips, dy {NAME_DY}" + (", grey" if c.get("grey") else ""))
    # 5. the output transfer: pre-compensate every grey and gold field so the
    #    SCREEN reads ER's numbers (counts include the fields converted above)
    if not no_gamma:
        t, n = recolour_all(t, ER_GREY, GREY_AUTH)
        assert n == cfg["grey"], f"{screen}: {n} grey fields, expected {cfg['grey']}"
        t, m = recolour_all(t, ER_GOLD, GOLD_AUTH)
        assert m == cfg["gold"], f"{screen}: {m} gold fields, expected {cfg['gold']}"
        log.append(f"gamma: {n} grey -> {GREY_AUTH}, {m} gold -> {GOLD_AUTH}")
    # 5b. the fields the ENGINE colours. Every value (and the item category
    #     line, "Consumable") is written at runtime as html with its own
    #     colour, so textColor is moot there: the baseline capture had the
    #     values reading 210 while their textColor was (193,194,178), and run 2
    #     had them at 210 while every Text_0 beside them read 204. Those
    #     placements get a colour transform instead (mult 248/256: the engine's
    #     #cccccc times 0.969 = 197.6, which the transfer lifts to ER's 204),
    #     and their textColor goes back to plain 204 so nothing is compensated
    #     twice if the engine ever leaves it alone.
    if not no_gamma:
        t, n, ids = engine_group(t)
        assert n == cfg["engine"], f"{screen}: {n} engine-coloured placements, expected {cfg['engine']}"
        for cid in ids:
            t = set_colour(t, cid, ER_GREY)
        log.append(f"{n} engine-coloured placements (texts {sorted(ids)}) -> cxform mult {ENGINE_MULT}/256, textColor {ER_GREY}")
    # 6. tracer
    if tracer and "tracer" in cfg:
        c = cfg["tracer"]
        t = set_colour(t, c["text"], c["rgb"])
        log.append(f"TRACER text {c['text']} -> {c['rgb']}")
    return t, log


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--screen", required=True, choices=sorted(SCREENS))
    ap.add_argument("--tracer", action="store_true")
    ap.add_argument("--keep-title", action="store_true")
    ap.add_argument("--keep-prompt", action="store_true")
    ap.add_argument("--no-gamma", action="store_true", help="author ER's screen colours verbatim (run 1 did; they read 3%% bright)")
    a = ap.parse_args()
    src, dst = Path(a.src), Path(a.dst)
    with tempfile.TemporaryDirectory() as d:
        xin, xout = Path(d) / "in.xml", Path(d) / "out.xml"
        to_xml(src, xin)
        t, log = edit(xin.read_text(), a.screen, a.tracer, a.keep_title, a.keep_prompt, a.no_gamma)
        xout.write_text(t)
        to_gfx(xout, dst)
    for line in log:
        print("  " + line)
    print(f"wrote {dst} ({dst.stat().st_size} bytes, source {src.stat().st_size})")


if __name__ == "__main__":
    main()
