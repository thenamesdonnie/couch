#!/usr/bin/env bash
# Replace Dark Souls 3's Latin typeface with any TTF.
#
# DS3 keeps its Latin text in /font/matissepron/font.gfx, a 10MB Scaleform GFX
# with the typeface embedded. Authoring one normally needs Scaleform's
# gfxexport, which is proprietary and long dead. JPEXS FFDec turns out to read
# AND write Scaleform GFX (it reports gfx=true and emits a valid "GFX\x0b"
# header back), which is the whole reason this is possible on Linux.
#
# Note DS3 and Elden Ring already share a typeface (FOT-Matisse ProN DB), so
# this is NOT the route to an Elden Ring look - it is the route to a better one.
#
#   swap_font.sh <font.gfx> <replacement.ttf> <out.gfx>
#
# Then drop the result at mod/font/matissepron/font.gfx in the ModEngine2 mod
# folder. Verified in game: Noto Serif and Crimson Pro both render correctly.
# Character id 1 is the embedded font; DS3's font.gfx contains exactly one.
set -euo pipefail
FFDEC="${FFDEC:-/tmp/ffdec/ffdec-cli.jar}"
[ -f "$FFDEC" ] || { echo "FFDec not found at $FFDEC. Get it from" \
  "https://github.com/jindrapetrik/jpexs-decompiler/releases and set FFDEC." >&2; exit 1; }
java -Xmx4g -jar "$FFDEC" -replace "$1" "$3" 1 "$2"
head -c 4 "$3" | grep -q GFX || { echo "output is not a GFX - refusing" >&2; exit 1; }
echo "wrote $3 ($(stat -c%s "$3") bytes)"
