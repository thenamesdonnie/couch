"""Shift DS3's menu panels toward Elden Ring's palette, preserving geometry.

WHY A RECOLOUR AND NOT A SWAP. Both games' panels are mostly flat gradients and
grain rather than intricate shapes, and their atlases are laid out completely
differently, so pasting Elden Ring's panel art into DS3's slots would misalign
every border and corner. What actually differs is TONE, and that was measured
rather than guessed:

    DS3 panel bodies   RGB (18.4, 18.0, 17.7)   red only +0.7 over blue: neutral
    Elden Ring panels  RGB (44.4, 42.9, 35.1)   red +9.3 over blue: distinctly warm

Elden Ring's are also ~2.4x brighter, and that part is deliberately NOT copied.
A 2.4x lift blows out the gold trim and hurts readability; the warmth is what
reads as "Elden Ring", not the exposure.

So this applies Elden Ring's measured hue ratio at a chosen strength while
PRESERVING each pixel's luminance, which means: no element gets brighter or
darker, nothing shifts position, alpha is untouched, and the 9-slice regions the
UI stretches are pixel-identical in shape. The only thing that changes is colour.

Strength 2.0 was chosen by eye from a 0/1/2/3 comparison: 1 is too subtle to
notice in motion, 3 starts going yellow-green because Elden Ring's blue channel
is much lower than its red and green.

Icons and glyphs are deliberately NOT recoloured. Tinting item art would make
things harder to recognise, which is a real cost for no aesthetic gain.
"""
from __future__ import annotations

import numpy as np

# Elden Ring's measured panel ratio, normalised on red.
ER_RATIO = np.array([1.0, 0.966, 0.790])
LUMA = np.array([0.299, 0.587, 0.114])

# Panel and frame art only. Everything else in the atlas is left alone.
PANEL_TEXTURES = [
    "MENU_Base", "MENU_BaseU", "MENU_BaseDeco", "MENU_InventoryBase",
    "MENU_DetailStatus_Base", "MENU_DetailStatus_Base2", "MENU_ItemBoxBase",
    "MENU_SpellBase", "MENU_ShopBase", "MENU_OptionBase", "MENU_SortList_Base",
    "MENU_EquipSlot", "MENU_ItemPanel_02", "MENU_Top", "MENU_ItemTab_Edge",
    "MENU_MessageBase" , "MENU_MessageBox", "MENU_CommandList_Base",
]


def warm(img, strength: float = 2.0):
    """RGBA Image -> RGBA Image, hue shifted toward ER, luminance preserved."""
    from PIL import Image

    a = np.asarray(img).astype(float)
    rgb = a[..., :3]
    lum = rgb @ LUMA
    gain = 1.0 + (ER_RATIO - 1.0) * strength
    out = rgb * gain
    new = out @ LUMA
    out = np.clip(out * np.divide(lum, np.maximum(new, 1e-6))[..., None], 0, 255)
    return Image.fromarray(np.dstack([out, a[..., 3]]).astype(np.uint8), "RGBA")


def clean(img, size: int = 5):
    """Flatten DS3's panel grain toward Elden Ring's smoothness.

    MEASURED, not eyeballed. Local variation against a 5px box mean:

        DS3   MENU_BaseU 2.54, MENU_Base 3.75, MENU_ItemBoxBase 4.78,
              MENU_InventoryBase 5.56
        ER    SB_MainMenu_03 0.21, SB_MainMenu 0.81

    Elden Ring's panels are 3-25x smoother. That, not colour and not fonts,
    is most of what reads as "cleaner". (Fonts are a dead end: both games use
    FOT-Matisse ProN DB, the same typeface.)

    A MEDIAN filter, not a blur. Median kills grain while leaving hard edges
    alone, so panel borders and the gold trim stay crisp; a Gaussian would
    smear them. size=5 lands DS3's panels at grain ~1.0 against Elden Ring's
    0.8. size=7 reaches 0.69 but starts costing the art its character.

    Luminance is effectively untouched: measured +0.7 max on a mean of 30-50,
    under 2.5%, so nothing gets harder to read. Panels look lighter afterwards
    but are not - that is the smoothness fooling the eye.

    Bonus: smoother data compresses better, so the packed mod is SMALLER than
    the recoloured one (28.8 MB against 36.7 MB) despite the same pixel count.
    """
    from PIL import Image
    from scipy.ndimage import median_filter

    a = np.asarray(img).astype(float)
    rgb = np.dstack([median_filter(a[..., c], size=size) for c in range(3)])
    return Image.fromarray(np.dstack([rgb, a[..., 3]]).astype(np.uint8), "RGBA")
