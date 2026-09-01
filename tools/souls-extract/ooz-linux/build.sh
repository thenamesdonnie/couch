#!/usr/bin/env bash
# Build ooz (Oodle Kraken decompressor) as a Linux shared library.
#
# ooz ships as an MSVC project with no LICENSE file, so its source is NOT
# vendored into this repo. This script fetches it and applies our port on top.
# What our patch does, all of it necessary and none of it cosmetic:
#
#   1. Portability. targetver.h/stdafx.h pull in SDKDDKVer.h, Windows.h,
#      tchar.h and intrin.h. Replaced with portable typedefs plus
#      <immintrin.h> for __m128i, and MSVC intrinsics mapped to GCC builtins.
#      Do NOT redefine _rotl: x86intrin.h already provides it and redefining it
#      produces a cascade of confusing "does not name a type" errors.
#   2. Cut the Windows CLI (everything past line 4286 of kraken.cpp), which
#      LoadLibrary's the real Oodle DLL, and expose C entry points instead.
#   3. THE REAL BUG FIX. Elden Ring compresses with Oodle's seekChunkReset, so
#      every 256KB block is independently decodable and its match window
#      restarts at the block boundary. ooz honours that restart bit only for
#      LZNA/Bitknit; for Kraken it kept passing the stream-absolute buffer
#      start as the window base, so from the second block on it allowed matches
#      reaching into the previous block and skipped the raw-first-8-bytes path
#      a restarted block begins with. Anything under 256KB is a single block at
#      offset 0 where the two bases coincide, which is why only larger files
#      failed. Fix: a block-local window base when the restart bit is set.
#   4. Name the two genuinely unimplemented stubs so a failure says which one
#      it hit instead of a bare -1 (see oodle.py's OozUnimplemented).
#
# Verified: 60 of ooz's 72 testdata files decompress, the same 60 as an
# unpatched control build, so this patch introduces no regression. The 12
# failures are all Leviathan and are a pre-existing ooz gap. Elden Ring's 203MB
# menu atlas decompresses in under a second.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="${1:-$HOME/couch/data/ds3-ui-port/ooz}"

if [ ! -d "$BUILD/.git" ]; then
    echo "cloning ooz into $BUILD"
    mkdir -p "$(dirname "$BUILD")"
    git clone --depth 1 https://github.com/powzix/ooz.git "$BUILD"
fi

cd "$BUILD"
cp "$HERE/stdafx.h" "$HERE/targetver.h" .

# kraken_lib.cpp is kraken.cpp truncated + patched; regenerate it every time so
# the patch stays the single source of truth.
git checkout -- kraken.cpp 2>/dev/null || true
patch -p0 -o kraken_lib.cpp kraken.cpp < "$HERE/kraken-lib.patch"

g++ -O2 -fPIC -shared -o libooz.so kraken_lib.cpp lzna.cpp bitknit.cpp -I.
echo "built $BUILD/libooz.so"
nm -D libooz.so | grep ooz_ || true
