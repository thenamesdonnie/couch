// Linux port of ooz's stdafx.h. The original pulls in Windows.h, tchar.h and
// intrin.h purely for fixed-width typedefs and a handful of MSVC intrinsics.
// Everything below is the portable equivalent; no logic is changed.
#pragma once
#include "targetver.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <stdint.h>
#include <immintrin.h>   // __m128i and friends (MSVC gets these from intrin.h)

typedef unsigned char byte;
typedef unsigned char uint8;
typedef unsigned int uint32;
typedef uint64_t uint64;
typedef int64_t int64;
typedef signed int int32;
typedef unsigned short uint16;
typedef signed short int16;
typedef unsigned int uint;

#define __forceinline inline __attribute__((always_inline))

// MSVC intrinsics -> GCC builtins. _BitScan* return 0 when the input is zero
// and otherwise write the bit index, which is what the callers rely on.
static __forceinline unsigned char _BitScanReverse(unsigned long *index, unsigned int mask) {
    if (!mask) return 0;
    *index = 31 - __builtin_clz(mask);
    return 1;
}
static __forceinline unsigned char _BitScanForward(unsigned long *index, unsigned int mask) {
    if (!mask) return 0;
    *index = __builtin_ctz(mask);
    return 1;
}
// _rotl is already provided by x86intrin.h on GCC, so we do not redefine it.
#define _byteswap_ulong(x)  __builtin_bswap32(x)
#define _byteswap_uint64(x) __builtin_bswap64(x)
#define _byteswap_ushort(x) __builtin_bswap16(x)
