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
    --cap-over-fill     move the left end-cap above the fill layer (see the
                        render-tree note at cap_over_fill)
    --shift-bars N      move the three bars right by N stage px (16 = ER's
                        badge-to-bar gap; see shift_bars)
    --er-mapname        move and size the AREA NAME title card onto ER's
                        layout (see the block above er_mapname)
    --mapname-force     PROBE ONLY: park that card on screen permanently so it
                        can be measured; the game never raises it on a plain
                        load (see mapname_force)
    --fill-rim          grow each bar's fill quad one stage px upward so the
                        two rim rows above the fill come from the bar's own
                        texture block instead of the shared backdrop (see
                        fill_rim)

ROUND-TRIP SAFETY was checked before any of this: JPEXS xml2swf reproduces a
554296-byte file, the same size as the original, with 12 bytes differing - all
of them re-encodings of zero with fewer bits - and a second round trip is
byte-identical, i.e. it converges. Loading in game is the part only a real run
can prove.

    python er_fe_gfx.py <in.gfx> <out.gfx> [--neutral-cxform] [--scale-cap N] [--drop-dish]
                        [--cap-over-fill] [--shift-bars N] [--er-slots] [--fill-rim]
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


# HOW THE BAR ACTUALLY RENDERS (read out of the movie, 2 Sep 2026 evening).
# Each bar (sprites 384 HP / 380 MP / 373 SP) is Fade -> {BarFrame, Delay,
# Current}, each holding a 1920-frame "Bar" sprite the engine gotoAndStops at
# a frame proportional to the stat. Inside each Bar: a sliding rectangular
# MASK at depth 1 (its translate moves 0.752 px per frame, 0..1444 px) over six
# 248-px texture tiles of MENU_PlayerHUD2 at depth 3, so the bar's length is
# the mask, never a scale. BarFrame's Bar (361, shared by all three bars) also
# holds the LEFT END-CAP at depth 17: sprite 358 -> shape 357, a 60x23 stage-px
# quad at the bar origin sampling atlas base texels x 4..64, rows 160..183 -
# at atlas scale 2 that is 120x46 texels drawn 1:1 at 4K. The "5x7 sprite
# fixed in engine code" story was never true; the knob is simply the only
# opaque thing in that texture region. The RIGHT end-cap is sprite 360 at
# depth 19, translated with the frame so it rides the bar's end. The fill's
# tiles (shape 117 etc.) sample base rows 34..46 of a 24-row block, which is
# the "middle 12 rows" measured earlier.
#
# The cap sits UNDER Delay and Current, so a cap art that should overlap the
# fill's start (ER's does, by 8 px) would be covered. --cap-over-fill moves it:
# the depth-17 placement comes out of Bar 361 and the same character goes into
# each bar's Fade sprite (383 / 379 / 372) at depth 7, above Current at 5,
# still inside the fade so it fades in with the bar.
CAP_CHAR = "358"
FADE_SPRITES = ("383", "379", "372")
CAP_PLACE = ('<item type="PlaceObject2Tag" characterId="358" depth="7" '
             'forceWriteAsLong="false" placeFlagHasCharacter="true" '
             'placeFlagHasClipActions="false" placeFlagHasClipDepth="false" '
             'placeFlagHasColorTransform="false" placeFlagHasMatrix="true" '
             'placeFlagHasName="false" placeFlagHasRatio="false" placeFlagMove="false">\n'
             '          <matrix type="MATRIX" hasRotate="false" hasScale="false" '
             'nRotateBits="0" nScaleBits="0" nTranslateBits="0" translateX="0" translateY="0"/>\n'
             '        </item>\n')


def cap_over_fill(t: str) -> tuple[str, int]:
    """Move the left end-cap above the fill (see the note above)."""
    n = 0
    # 1. drop the depth-17 placement of the cap inside Bar 361
    pat = re.compile(r'\s*<item type="PlaceObject2Tag" characterId="358" depth="17"[^>]*>'
                     r'.*?</item>', re.S)
    t, k = pat.subn("", t, count=1)
    n += k
    # 2. add it at depth 7 to each Fade sprite, right after the Current placement
    for sid in FADE_SPRITES:
        m = re.search(r'<item type="DefineSpriteTag"[^>]*spriteId="%s"[^>]*>' % sid, t)
        if not m:
            continue
        end = t.index("</item>\n", t.index('<item type="ShowFrameTag"', m.end())) + len("</item>\n")
        # insert before the first ShowFrame of this sprite
        show = t.index('<item type="ShowFrameTag"', m.end())
        line_start = t.rfind("\n", 0, show) + 1
        t = t[:line_start] + "        " + CAP_PLACE + t[line_start:]
        n += 1
    return t, n


def shift_bars(t: str, px: float) -> tuple[str, int]:
    """Move the three bars right by `px` stage px (sprite 471's HP/MP/SP).

    WHY: with Elden Ring's cap drawn at ER's offset (33 px left of the fill at
    4K) it ran under DS3's covenant badge, whose frame reaches within 12 px of
    the bar; ER keeps a 43 px gap. +16 stage px (32 at 4K) reproduces ER's gap.
    Everything inside the bars moves with them; nothing else in the HUD does.
    """
    n = 0
    tw = int(round(px * 20))

    def fix(m: re.Match) -> str:
        nonlocal n
        block = m.group(0)
        mm = re.search(r'translateX="(-?\d+)"', block)
        if not mm:
            return block
        new = re.sub(r'translateX="-?\d+"', f'translateX="{int(mm.group(1)) + tw}"', block, count=1)
        new = re.sub(r'nTranslateBits="\d+"', 'nTranslateBits="13"', new, count=1)
        n += 1
        return new

    # Only inside sprite 471 (the player-status sprite): other sprites also
    # name children HP/MP/SP, and matching the whole file shifted seven.
    m471 = re.search(r'<item type="DefineSpriteTag"[^>]*spriteId="471"[^>]*>', t)
    a = m471.start()
    b = t.index('<item type="DefineSpriteTag"', m471.end()) if '<item type="DefineSpriteTag"' in t[m471.end():] else len(t)
    pat = re.compile(r'<item type="PlaceObject2Tag"[^>]*name="(?:HP|MP|SP)"[^>]*>.*?</item>', re.S)
    return t[:a] + pat.sub(fix, t[a:b]) + t[b:], n


# THE RIM ROWS (3 Sep 2026). Elden Ring draws two rows above each fill: a
# translucent dark tint at -2 and an OPAQUE per-bar rim at -1 (HP 94,42,20,
# FP 51,72,64, stamina 54,73,33; identical in every reference frame, see
# hud_rim.py). In DS3 those two 4K rows sit above the fill tile's quad, so
# they came from the shared backdrop and could only ever be one colour for all
# three bars. The fill tiles (shape 117 HP, 365 stamina, 374 FP) are 12 stage
# px tall, y -6..6, sampling base rows 34..46 through a bitmap matrix that
# maps texel row v to stage y = v - 40; growing the quad one stage px UPWARD
# (y -7..6) samples base row 33 too, i.e. scale-2 atlas rows 66..67 = the two
# 4K rows directly above the fill, with the matrix untouched. Each bar's own
# block can then carry its own rim, and er_hud_graft.py authors it.
#
# The quad is clipped by the sliding MASK at depth 1 of each Current Bar
# sprite (381 HP / 377 MP / 370 SP): shape 63 is 47 stage px tall (y +/-23.5)
# and the mask placement scales it by 0.3404, so it clips at y +/-8.0, two px
# clear of the old +/-6 quad and one clear of the new -7..6. No mask edit is
# needed (BarFrame's mask is 0.4256 -> +/-10 over its +/-8 backdrop quad, the
# same one-px margin the fill now has). Delay's tile (shape 113) is left as
# it is: its rim rows would only ever be transparent (the tint over a
# depleted stretch is the trough's own), so widening it would draw nothing.
FILL_SHAPES = ("117", "365", "374")
RIM_GROW_TWIPS = 20                     # one stage px


def fill_rim(t: str) -> tuple[str, int]:
    """Grow the three fill quads one stage px upward (see the note above)."""
    n = 0
    for sid in FILL_SHAPES:
        m = re.search(r'<item type="DefineShapeTag"[^>]*shapeId="%s"[^>]*>' % sid, t)
        a = m.start()
        b = t.index("</shapeRecords>", m.end())
        blk = t[a:b]
        new, k = re.subn(r'Ymin="-120"', f'Ymin="-{120 + RIM_GROW_TWIPS}"', blk, count=1)
        # the rectangle's vertical edges: +/-240 twips -> +/-260, and the
        # records' bit width goes with them (JPEXS numBits = bits - 2; 260
        # needs 10 signed bits, 240 needed 9 which JPEXS stored as 7)
        new, k2 = re.subn(r'deltaY="(-?)240" generalLineFlag="false" numBits="7"',
                          lambda mm: f'deltaY="{mm.group(1)}{240 + RIM_GROW_TWIPS}" generalLineFlag="false" numBits="8"',
                          new)
        # a shape whose path starts at the TOP edge moves there first
        new, k3 = re.subn(r'moveDeltaY="-120"', f'moveDeltaY="-{120 + RIM_GROW_TWIPS}"', new, count=1)
        if k != 1 or k2 != 2:
            raise SystemExit(f"shape {sid}: expected 1 bound + 2 edges, got {k} + {k2}")
        t = t[:a] + new + t[b:]
        n += 1
    return t, n


def drop_dish(t: str) -> tuple[str, int]:
    """Remove the brown elliptical item base placements."""
    pat = re.compile(r'\s*<item type="PlaceObject2Tag"[^>]*name="Dish"[^>]*>'
                     r'.*?</item>', re.S)
    out, n = pat.subn("", t)
    return out, n


# --- Elden Ring equipment-slot layout -------------------------------------
# ER's four main slots form a tight cross at the bottom-left: at 4K the
# weapons are 163x204 px centred at x 182 / 556, the spell and flask at
# y 1708 / 1928, cross centre (369, 1818). DS3's `ItemPanel` (sprite 257 in
# 472) is the same cross at 224x304 per slot, centre (564, 1652). Scaling the
# whole panel 0.75 brings every slot to 168x228 and the arms to +/-184 px,
# matching ER within a few px; everything inside (icons, rails, durability,
# labels) scales with it, which is what ER's smaller icons look like anyway.
# Text sizes are then set so the label and the count come out at ER's size
# AFTER the 0.75: name 573 twips (28.7 px em -> 21.5 stage px -> 30 px caps
# at 4K), count 840 twips (ER's flask count is a large 44 px digit).
SLOT_SCALE = 0.75
SLOT_XY = (-775.5, 369.0)       # stage px, relative to PlayerHUD's (960, 540)
NAME_TEXT_IDS = (208, 214)       # Item_Top / Item_Bottom label
COUNT_TEXT_IDS = (213,)          # Item_Bottom stock count
NAME_TWIPS = 660                 # run 4: 573 gave 26 px caps against ER's 30
COUNT_TWIPS = 1036               # run 4: 840 gave a 30 px digit against ER's 37 (Spectral's figures are x-height)
TEXT_GREY = 195                  # ER's labels read (194,195,194); DS3's were 255
# run 4 (0.75, uniform): weapons landed within 4 px of ER, but the spell slot
# sat 18 px high and the flask 20 px low (ER's cross is not symmetric).
# Local px inside the 0.75 sprite: 4K px / 1.5.
ITEM_TOP_Y = -72.0               # was -84
ITEM_BOTTOM_Y = 70.0             # was 83
STOCK_XY = (4.0, -55.0)          # ER's count sits ON the bottom rule, right edge 7 px past the slot. Runs 6-8: y -73 was 35 px high, x -15 was 29 px left, y -44 was 17 px low
NAME_BOTTOM_Y = 6.0              # run 5: 9 put the label 5 px lower than ER (28 px under the rule)
ICON_SCALE = None                # DEAD END (runs 6-7): neither the ItemIcon placement nor its IconImage child changes the drawn icon; the engine attaches the real item icon itself. Set a float to retry.

# --- the small preview slots (3 Sep) --------------------------------------
# ER puts two previews beside the spell slot and two beside the flask: the
# next item, and behind it a smaller, thinner copy of the one after. DS3 has
# exactly the same pair, `SubItem_1` (depth 25, in front) and `SubItem_2`
# (depth 17, behind, carrying an alphaMult of 205/256 = 0.80 which happens to
# be ER's own front-to-rear ratio, 0.54/0.69 - leave the cxform alone).
#
# Measured on ER at 4K, as slot centres:
#     spell   front (503.5, 1653.5)   rear (556.5, 1645.5)
#     flask   front (503.5, 1983.5)   rear (556.5, 1992.0)
#     the main slots they hang off: spell (369, 1708.5), flask (369, 1928.5)
# so the front sits +134.5 px out and +/-55 px along the cross, the rear
# +187.5 out and +/-63.5 along. DS3's own numbers are close for the flask but
# stagger the spell pair the wrong way (its rear is 9 px nearer the middle of
# the cross where ER's is 8 px further out).
#
# SIZE. ER's front preview is 78 px wide with its rules 94 px apart; DS3's
# panel (45x61 stage px) draws 67.5 x 91.5 inside the 0.75 cross, and its
# aspect is narrower than ER's, so one scale cannot match both. x1.156 matches
# the WIDTH and er_slot_panel then insets the field and rules inside the taller
# quad, which lands both axes on ER. The rear is x0.84 of the front (ER: 66 px
# wide, rules 78 apart, both ratios 0.83-0.85).
#
# WHERE THE FRAME IS. These translates live in the `Fade` sprite's frame (211
# for Item_Top, 217 for Item_Bottom), whose origin is Item_Top / Item_Bottom's
# own origin: at 4K, (369, 1710) and (369, 1923). Item_Top's Fade placement
# carries t=(9,8) and THE ENGINE IGNORES IT - measured, not assumed. Our spell
# panel lands at 4K (370, 1709) and our flask at (371, 1930), which is the
# chain Item_Top -> Fade -> Item with the Fade's own translate dropped and the
# Item's (1,5) inside 217 kept. So a value here is (ER's slot centre - the
# Fade origin) / 1.5, and NOT measured from the main panel.
SUB_SCALE = 1.156                # front preview, ER's 78 px width / DS3's 67.5
SUB_REAR_SCALE = 0.971           # = SUB_SCALE * 0.84
SUB_TOP_FRONT = (89.7, -37.7)    # sprite 211
SUB_TOP_REAR = (125.0, -43.0)
SUB_BOT_FRONT = (89.7, 40.3)     # sprite 217
SUB_BOT_REAR = (125.0, 46.0)


def er_slots(t: str) -> tuple[str, int]:
    """Scale and move the equipment cross to Elden Ring's layout."""
    n = 0

    def place(m: re.Match) -> str:
        nonlocal n
        n += 1
        return (m.group(1)
                + f'<matrix type="MATRIX" hasRotate="false" hasScale="true" nRotateBits="0" '
                  f'nScaleBits="16" nTranslateBits="16" scaleX="{SLOT_SCALE}" scaleY="{SLOT_SCALE}" '
                  f'translateX="{int(round(SLOT_XY[0] * 20))}" translateY="{int(round(SLOT_XY[1] * 20))}"/>')
    t = re.sub(r'(<item type="PlaceObject2Tag" characterId="257" depth="1"[^>]*name="ItemPanel"[^>]*>\s*)<matrix[^>]*/>',
               place, t, count=1)
    for cid, twips in [(c, NAME_TWIPS) for c in NAME_TEXT_IDS] + [(c, COUNT_TWIPS) for c in COUNT_TEXT_IDS]:
        t, k = re.subn(r'(<item type="DefineEditTextTag"[^>]*characterID="%d"[^>]*fontHeight=")\d+(")' % cid,
                       lambda m: f'{m.group(1)}{twips}{m.group(2)}', t, count=1)
        n += k
    # label colour (the DefineEditText's textColor child)
    for cid in NAME_TEXT_IDS:
        t, k = re.subn(r'(<item type="DefineEditTextTag"[^>]*characterID="%d"[^>]*>\s*(?:<[^>]*/>\s*)*?<textColor type="RGBA" alpha="255" blue=")\d+(" green=")\d+(" red=")\d+(")' % cid,
                       lambda m: f'{m.group(1)}{TEXT_GREY}{m.group(2)}{TEXT_GREY}{m.group(3)}{TEXT_GREY}{m.group(4)}', t, count=1)
        n += k

    def move(pattern: str, x=None, y=None) -> None:
        nonlocal t, n
        def fix(m):
            blk = m.group(0)
            if x is not None:
                blk = re.sub(r'translateX="-?\d+"', f'translateX="{int(round(x * 20))}"', blk, count=1)
            if y is not None:
                blk = re.sub(r'translateY="-?\d+"', f'translateY="{int(round(y * 20))}"', blk, count=1)
            return blk
        t, k = re.subn(pattern, fix, t, count=1)
        n += k
    # the icon art. Run 6: scaling the `ItemIcon` placements (153 in 198/247)
    # did nothing - the engine owns that instance's matrix. Its child
    # `IconImage` (152 at (-80,-80) inside 153) is the 160x160 quad itself and
    # is not script-driven, so the scale goes there, about the quad's centre.
    off = -80.0 * (ICON_SCALE or 1.0)
    if ICON_SCALE:
      t, k = re.subn(r'(<item type="PlaceObject2Tag" characterId="152" depth="1"[^>]*name="IconImage"[^>]*>\s*)<matrix type="MATRIX" hasRotate="false" hasScale="false"[^>]*/>',
                   lambda m: m.group(1) + f'<matrix type="MATRIX" hasRotate="false" hasScale="true" nRotateBits="0" nScaleBits="16" nTranslateBits="16" scaleX="{ICON_SCALE}" scaleY="{ICON_SCALE}" translateX="{int(round(off * 20))}" translateY="{int(round(off * 20))}"/>', t)
      n += k
    move(r'<item type="PlaceObject2Tag" characterId="212" depth="1"[^>]*name="Item_Top"[^>]*>\s*<matrix[^>]*/>', y=ITEM_TOP_Y)
    move(r'<item type="PlaceObject2Tag" characterId="218" depth="3"[^>]*name="Item_Bottom"[^>]*>\s*<matrix[^>]*/>', y=ITEM_BOTTOM_Y)
    move(r'<item type="PlaceObject[23]Tag" characterId="213" depth="1"[^>]*name="Stock"[^>]*>\s*<matrix[^>]*/>', x=STOCK_XY[0], y=STOCK_XY[1])
    move(r'<item type="PlaceObject[23]Tag" characterId="214" depth="2"[^>]*name="Name"[^>]*>\s*<matrix[^>]*/>', y=NAME_BOTTOM_Y)

    # the two preview slots per item slot. Both are character 207, so the
    # substitution has to be scoped to one Fade sprite at a time, the way
    # shift_bars scopes to sprite 471: a DefineSprite's subtags never contain
    # another DefineSprite, so "up to the next DefineSpriteTag" is its body.
    def sub_place(sprite: str, depth: str, name: str, scale: float, xy) -> None:
        nonlocal t, n
        m = re.search(r'<item type="DefineSpriteTag"[^>]*spriteId="%s"[^>]*>' % sprite, t)
        if not m:
            return
        nxt = t.find('<item type="DefineSpriteTag"', m.end())
        b = nxt if nxt != -1 else len(t)
        body, k = re.subn(
            r'(<item type="PlaceObject2Tag" characterId="207" depth="%s"[^>]*name="%s"[^>]*>\s*)'
            r'<matrix[^>]*/>' % (depth, name),
            lambda mm: mm.group(1) + (
                f'<matrix type="MATRIX" hasRotate="false" hasScale="true" nRotateBits="0" '
                f'nScaleBits="16" nTranslateBits="16" scaleX="{scale}" scaleY="{scale}" '
                f'translateX="{int(round(xy[0] * 20))}" translateY="{int(round(xy[1] * 20))}"/>'),
            t[m.start():b], count=1)
        t = t[:m.start()] + body + t[b:]
        n += k
    sub_place("211", "25", "SubItem_1", SUB_SCALE, SUB_TOP_FRONT)
    sub_place("211", "17", "SubItem_2", SUB_REAR_SCALE, SUB_TOP_REAR)
    sub_place("217", "25", "SubItem_1", SUB_SCALE, SUB_BOT_FRONT)
    sub_place("217", "17", "SubItem_2", SUB_REAR_SCALE, SUB_BOT_REAR)
    return t, n


# ---------------------------------------------------------------- area name
# THE AREA NAME TITLE CARD (3 Sep 2026), read out of the movie with fe_tree.py:
#
#   sprite 0 depth 475 name='MapName' at stage (960, 488)
#     sprite 520     121 frames; its depth-1 placements animate alphaMult -
#                    this is the card's fade in and out, nothing else.
#     sprite 519     78 frames, SIX PER LANGUAGE, labelled jpnJP, fraFR, itaIT,
#                    deuDE, spaES, spaAR, porBR, engUS (frame 42), polPL,
#                    rusRU, zhoTW, korKR, zhoCN. Each language frame that needs
#                    a different text height re-places the TEXT sprite at its
#                    own y; engUS re-places nothing, so it inherits fraFR's
#                    (0, -43). The UNDERLINE is placed once at frame 0 and
#                    persists through every language frame.
#       sprite 516 at (0, 64)   -> shape 515, the underline quad, 1200x8 stage
#                                  px = 2400x16 at 4K, centred on the screen
#       sprite 518 at (0, -43)  -> text 517, MenuFont_02, fontHeight 1800 twips
#                                  (90 stage px em), align 2, white, with a
#                                  DROPSHADOWFILTER on the placement
#
# ER's card (er_mapname.py has the full measurement) is white serif text with
# ONE tapered rule 26 px (4K) below the text baseline, and nothing else: no
# band, no second rule. So the port is a texture repaint plus geometry: resize
# the text to ER's caps, then move the whole card down and the underline to
# ER's gap. Both moves go on placements the engine does not own (the inner 519
# and 516 placements), not on the named `MapName` instance at the root - the
# souls counter taught us that the engine positions named instances itself.
#
# WHERE THE TEXT LANDS. A DefineEditText's first baseline is bounds.Ymin + 2
# (Flash's gutter) + the font's ascent at that fontHeight, so it is computable -
# but only if you know the font, and MenuFont_02 is NOT the one this mod swaps.
# Rendering "Cemetery of Ash" in Spectral SemiBold beside the run-5 capture at
# a matched cap height shows two different faces: MenuFont_01 (the equipment
# labels, the souls digits) resolves to font/matissepron/font.gfx, which the
# port replaced with Spectral, while MenuFont_02 - the area name, and only it
# so far - comes from a font resource the port has never touched. Its Latin is
# a lighter, higher-contrast old-style serif, and its metrics are its own.
# So the numbers below were MEASURED in game rather than read out of a TTF: at
# 1920 twips the baseline landed at 4K y 1138 (predicted 1130 from Spectral's
# ascent, i.e. 8 px out) with the 'C' 139 px above it (predicted 126.7, 10%
# out), and at 1620 twips y 1128 with the 'C' 117 px above. Two font sizes give
# a line rather than a single point, and the line does NOT pass through
# bounds.Ymin + 2: fitting stage baseline = MAPNAME_BASE_K + ascent * em over
# the two runs is what puts the baseline on ER's row.
MAPNAME_ASCENT_EM = 1.1133       # (547.47 - 530.77) / (96 - 81)
MAPNAME_BASE_K = 440.6           # 547.47 - 1.1133 * 96, stage px
MAPNAME_CAP_EM = 0.7222          # 117 / 162, cap above baseline at 4K, run 8
# ER, area-name-banner.png at 4K. The cap number is the 'S' of "Stormveil"
# (apex 1013, baseline 1130) measured the same way ours was - a round capital
# at threshold 150. The 127 px an earlier pass quoted was the 't'/'l' ASCENDER
# top at 1003, not a cap, and using it made the text 18% too big in run 5.
MAPNAME_ER_BASELINE = 1130.0
MAPNAME_ER_RULE_GAP = 26.0       # ER: rule centre 1156, baseline 1130
MAPNAME_ER_CAP = 117.0
MAPNAME_RULE_Y_4K = 1104.0       # DS3's underline quad centre as shipped
                                 # (stage 488 + 64, one stage px = two 4K px)
# fontHeight for text 517, in twips, rounded to a whole stage px of em so the
# glyphs land on a clean grid. 1620 = 81 stage px em -> 117.3 px caps at 4K.
MAPNAME_TWIPS = 20 * round(MAPNAME_ER_CAP / MAPNAME_CAP_EM / 2.0)


def _mapname_baseline_4k(twips: int = None) -> float:
    """Where text 517's baseline lands at 4K, before any card move."""
    em = (MAPNAME_TWIPS if twips is None else twips) / 20.0
    return 2.0 * (MAPNAME_BASE_K + MAPNAME_ASCENT_EM * em)


def _mapname_offsets() -> tuple[float, float]:
    """(card drop, underline shift) in stage px. One stage px is two 4K px."""
    drop = (MAPNAME_ER_BASELINE - _mapname_baseline_4k()) / 2.0
    rule_target = MAPNAME_ER_BASELINE + MAPNAME_ER_RULE_GAP
    shift = (rule_target - (MAPNAME_RULE_Y_4K + 2.0 * drop)) / 2.0
    return drop, shift


def er_mapname(t: str) -> tuple[str, int]:
    """Move and size DS3's area name card onto Elden Ring's layout."""
    n = 0
    drop, shift = _mapname_offsets()

    def matrix(x: float, y: float) -> str:
        return ('<matrix type="MATRIX" hasRotate="false" hasScale="false" '
                'nRotateBits="0" nScaleBits="0" nTranslateBits="16" '
                f'translateX="{int(round(x * 20))}" translateY="{int(round(y * 20))}"/>')

    # the whole card: sprite 519 inside 520, the one placement the language
    # frames never touch
    t, k = re.subn(r'(<item type="PlaceObject2Tag" characterId="519" depth="1"[^>]*'
                   r'name="Text_0"[^>]*>\s*)<matrix[^>]*/>',
                   lambda m: m.group(1) + matrix(0.0, drop), t, count=1)
    n += k
    # the underline, relative to the text: sprite 516 inside 519, shipped (0,64)
    t, k = re.subn(r'(<item type="PlaceObject2Tag" characterId="516" depth="1"[^>]*>\s*)'
                   r'<matrix[^>]*/>',
                   lambda m: m.group(1) + matrix(0.0, 64.0 + shift), t, count=1)
    n += k
    # text size
    t, k = re.subn(r'(<item type="DefineEditTextTag"[^>]*characterID="517"[^>]*fontHeight=")\d+(")',
                   lambda m: f'{m.group(1)}{MAPNAME_TWIPS}{m.group(2)}', t, count=1)
    n += k
    return t, n


def mapname_force(t: str) -> tuple[str, int]:
    """PROBE ONLY: park the area name card permanently on screen.

    DS3 does NOT raise the card when you Continue into a save in the area you
    saved in - proved with the DS3SHOT_EARLY sweep, which keeps every frame
    from the loading screen to six frames past the HUD appearing: the world
    arrives with no card and none of the nine frames has any white text or any
    underline (run 1 painted the quad opaque white as a tracer and it never
    showed). The harness character stands in Cemetery of Ash with no area
    boundary and no bonfire warp within reach, so the card cannot be triggered
    the way the game triggers it.

    What hides it is the fade: sprite 520's 121 frames are a chain of depth-1
    CXFORMWITHALPHA moves starting at alphaMult 0 on the frame labelled
    "Normal", and the engine parks the sprite on one of them. Pinning every
    alphaMult in that sprite to 256, and putting a known string in text 517's
    initialText in case the engine never writes one, leaves the card drawn at
    full opacity all the time. That is a measurement rig, NOT part of the
    build: it would also leave the card on screen during play.
    """
    i = t.index('<item type="DefineSpriteTag" forceWriteAsLong="true" frameCount="121" '
                'hasEndTag="true" spriteId="520">')
    j = t.index("</item>", t.index("</subTags>", i))
    blk, n = re.subn(r'alphaMultTerm="\d+"', 'alphaMultTerm="256"', t[i:j])
    t = t[:i] + blk + t[j:]
    t, k = re.subn(r'(<item type="DefineEditTextTag"[^>]*characterID="517"[^>]*initialText=")[^"]*(")',
                   lambda m: f'{m.group(1)}Cemetery of Ash{m.group(2)}', t, count=1)
    # RUN 4: forcing the alphas alone was NOT enough - the card still never
    # appeared, so the engine hides the named `MapName` instance itself
    # (_visible, the same class of runtime ownership as the souls counter's
    # TotalSoul). So place a SECOND, UNNAMED copy of sprite 520 beside it, at
    # the same stage position and one depth above. Nothing in the engine knows
    # that instance's name, so nothing hides it.
    clone = ('<item type="PlaceObject2Tag" characterId="520" depth="476" '
             'forceWriteAsLong="true" placeFlagHasCharacter="true" '
             'placeFlagHasClipActions="false" placeFlagHasClipDepth="false" '
             'placeFlagHasColorTransform="false" placeFlagHasMatrix="true" '
             'placeFlagHasName="false" placeFlagHasRatio="false" placeFlagMove="false">\n'
             '      <matrix type="MATRIX" hasRotate="false" hasScale="false" '
             'nRotateBits="0" nScaleBits="0" nTranslateBits="16" '
             'translateX="19200" translateY="9760"/>\n'
             '    </item>\n    ')
    m = re.search(r'<item type="PlaceObject2Tag" characterId="520" depth="475"[^>]*>.*?</item>\s*',
                  t, re.S)
    if m:
        t = t[:m.end()] + clone + t[m.end():]
        k += 1
    return t, n + k


def main() -> None:
    argv = sys.argv[1:]
    do_cx = "--neutral-cxform" in argv
    do_dish = "--drop-dish" in argv
    do_capover = "--cap-over-fill" in argv
    do_slots = "--er-slots" in argv
    do_mapname = "--er-mapname" in argv
    do_force = "--mapname-force" in argv
    do_rim = "--fill-rim" in argv
    shift = None
    if "--shift-bars" in argv:
        i = argv.index("--shift-bars")
        shift = float(argv[i + 1])
        del argv[i:i + 2]
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
        if do_slots:
            t, n = er_slots(t)
            want = (1 + len(NAME_TEXT_IDS) + len(COUNT_TEXT_IDS) + len(NAME_TEXT_IDS)
                    + 4 + 4 + (1 if ICON_SCALE else 0))   # +4: the preview slots
            print(f"  er-slots: {n} edits ({want} expected)")
            if n != want:
                raise SystemExit(f"expected {want} slot edits, made {n} - refusing")
        if do_mapname:
            # NOT `shift` - that name belongs to --shift-bars in this scope, and
            # binding it here silently shifted the three HUD bars as well.
            drop, rule_dy = _mapname_offsets()
            t, n = er_mapname(t)
            print(f"  er-mapname: {n} edits (3 expected); card down {drop:g} "
                  f"stage px, underline {rule_dy:+g}, text {MAPNAME_TWIPS} twips")
            if n != 3:
                raise SystemExit(f"expected 3 mapname edits, made {n} - refusing")
        if do_force:
            t, n = mapname_force(t)
            print(f"  mapname-force (PROBE, not for the build): {n} edits")
            if n < 2:
                raise SystemExit(f"expected the cxform chain plus the text, made {n} - refusing")
        if do_capover:
            t, n = cap_over_fill(t)
            print(f"  cap-over-fill: {n} edits (1 removal + 3 placements expected)")
            if n != 4:
                raise SystemExit(f"expected 4 cap edits, made {n} - refusing")
        if do_rim:
            t, n = fill_rim(t)
            print(f"  fill-rim: {n} fill quads grown (3 expected)")
            if n != 3:
                raise SystemExit(f"expected 3 rim edits, made {n} - refusing")
        if shift is not None:
            t, n = shift_bars(t, shift)
            print(f"  shifted {n} bars right by {shift:g} stage px")
            if n != 3:
                raise SystemExit(f"expected 3 bar placements, shifted {n} - refusing")

        print(f"  xml {before:,} -> {len(t):,} bytes")
        xml.write_text(t, encoding="utf-8")
        print("  recompiling ...")
        to_gfx(xml, dst)

    print(f"  wrote {dst} ({dst.stat().st_size:,} bytes; "
          f"original {src.stat().st_size:,})")


if __name__ == "__main__":
    main()
