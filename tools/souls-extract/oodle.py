"""Oodle Kraken decompression on Linux, and DCX unwrapping for both games.

Elden Ring compresses its DCX payloads with Oodle Kraken, which is proprietary
and Windows-only. soulstruct refuses it outright on Linux ("Can currently only
load Oodle DLL on Windows"). The way round it is `ooz`, an open-source
Kraken/Mermaid/Selkie DECOMPRESSOR, built here as ./ooz/libooz.so.

Porting notes for ooz, since it is an MSVC project and does not build as-is:
  * targetver.h/stdafx.h pull in SDKDDKVer.h, Windows.h, tchar.h and intrin.h.
    Replaced with portable typedefs plus <immintrin.h> for __m128i.
  * _BitScanReverse/_BitScanForward/_byteswap_* mapped to GCC builtins.
    _rotl is NOT redefined - x86intrin.h already provides it and redefining it
    is a compile error that cascades into confusing "does not name a type".
  * Everything after line 4286 of kraken.cpp is a Windows CLI that LoadLibrary's
    the real Oodle DLL to A/B against. Cut; we build kraken_lib.cpp instead,
    which exposes a single `ooz_decompress` entry point.

DS3 and Bloodborne use DCX_DFLT (zlib) and need none of this.
"""
from __future__ import annotations

import ctypes
import struct
import zlib
from pathlib import Path

_LIB = None


def _lib():
    global _LIB
    if _LIB is None:
        # The library is a BUILD ARTIFACT and deliberately lives outside the
        # repo (ooz has no LICENSE, so we do not vendor it). Build it with
        # tools/souls-extract/ooz-linux/build.sh.
        import os
        candidates = [
            Path(os.environ["OOZ_LIB"]) if os.environ.get("OOZ_LIB") else None,
            Path.home() / "couch/data/ds3-ui-port/ooz/libooz.so",
            Path(__file__).with_name("ooz") / "libooz.so",
        ]
        so = next((c for c in candidates if c and c.exists()), None)
        if so is None:
            raise RuntimeError(
                "libooz.so not found. Build it with "
                "tools/souls-extract/ooz-linux/build.sh, or point OOZ_LIB at it."
            )
        _LIB = ctypes.CDLL(str(so))
        _LIB.ooz_decompress_lenient.argtypes = [ctypes.c_char_p, ctypes.c_size_t,
                                        ctypes.c_char_p, ctypes.c_size_t]
        _LIB.ooz_decompress_lenient.restype = ctypes.c_int
        _LIB.ooz_last_unimplemented.argtypes = []
        _LIB.ooz_last_unimplemented.restype = ctypes.c_char_p
    return _LIB


class OozUnimplemented(RuntimeError):
    """ooz reached a decode path its author never finished.

    Distinct from a normal failure on purpose: this is not corrupt data and not
    a bug in our container parsing, it is a known gap in the decompressor. If
    this fires, the named function in ooz is the thing to go and implement.
    """


def kraken_decompress(src: bytes, uncompressed_size: int) -> bytes:
    lib = _lib()
    dst = ctypes.create_string_buffer(uncompressed_size + 64)
    n = lib.ooz_decompress_lenient(src, len(src), dst, uncompressed_size)
    if n != uncompressed_size:
        stub = lib.ooz_last_unimplemented()
        if stub:
            raise OozUnimplemented(
                f"ooz hit an UNIMPLEMENTED decode path: {stub.decode()}. "
                "This is a known gap in ooz, not corrupt data and not a bug in "
                "our DCX/BHD5 parsing. Implementing that function in "
                "ooz/kraken_lib.cpp is the fix; the fallback is the real "
                "oo2core DLL that ships with Elden Ring."
            )
        raise RuntimeError(
            f"Kraken decompress returned {n}, expected {uncompressed_size} "
            "(no unimplemented path was reached, so suspect the input bytes)"
        )
    return dst.raw[:uncompressed_size]


def dcx_decompress(data: bytes) -> bytes:
    """Unwrap a DCX container, handling both DFLT (zlib) and KRAK (Oodle)."""
    if data[:4] != b"DCX\0":
        raise ValueError("not a DCX")
    dcs_offset, dcp_offset = struct.unpack_from(">II", data, 8)
    uncompressed_size, compressed_size = struct.unpack_from(">II", data, dcs_offset + 4)

    # The DCP block names the codec, four ASCII bytes right after "DCP\0".
    codec = data[dcp_offset + 4:dcp_offset + 8]

    i = data.find(b"DCA\0", dcp_offset)
    start = i + struct.unpack_from(">I", data, i + 4)[0]
    payload = data[start:start + compressed_size]

    if codec == b"DFLT":
        out = zlib.decompress(payload)
    elif codec == b"KRAK":
        out = kraken_decompress(payload, uncompressed_size)
    else:
        raise NotImplementedError(f"DCX codec {codec!r} not supported")

    if len(out) != uncompressed_size:
        raise ValueError(f"expected {uncompressed_size} bytes, got {len(out)}")
    return out


def dcx_compress_dflt(payload: bytes, level: int = 9) -> bytes:
    """Wrap bytes in a DS3-style DCX_DFLT container (zlib).

    The 76-byte header is fixed apart from the two sizes; this is templated on
    a real DS3 file (menu/01_common.tpf.dcx) rather than invented. Version is
    0x00010000 for DS3, where Elden Ring uses 0x00011000 with KRAK.

    Only DFLT is written. We never need to WRITE Oodle: ooz decompresses only,
    and DS3, which is what we repack for, uses zlib anyway.
    """
    import zlib

    comp = zlib.compress(payload, level)
    h = bytearray(76)
    h[0:4] = b"DCX\0"
    struct.pack_into(">I", h, 4, 0x00010000)
    struct.pack_into(">I", h, 8, 0x18)      # DCS offset
    struct.pack_into(">I", h, 12, 0x24)     # DCP offset
    struct.pack_into(">I", h, 16, 0x44)
    struct.pack_into(">I", h, 20, 0x4C)
    h[24:28] = b"DCS\0"
    struct.pack_into(">I", h, 28, len(payload))
    struct.pack_into(">I", h, 32, len(comp))
    h[36:40] = b"DCP\0"
    h[40:44] = b"DFLT"
    struct.pack_into(">I", h, 44, 0x20)
    h[48] = level
    struct.pack_into(">I", h, 64, 0x00010100)
    h[68:72] = b"DCA\0"
    struct.pack_into(">I", h, 72, 8)
    return bytes(h) + comp
