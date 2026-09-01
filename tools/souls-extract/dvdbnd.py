"""Read FromSoftware dvdbnd archives (Data*.bhd + Data*.bdt) on Linux, natively.

WHY THIS EXISTS. The usual tools for this (UXM, WitchyBND, Yabber) are Windows
.NET, and this box has neither wine nor dotnet. soulstruct handles BND4, TPF and
DCX but has no BHD5 support at all, and BHD5 is the top-level container that
everything else lives inside. So this is the missing bottom layer.

Format and keys are public, from SoulsFormats (JKAnderson) and UXM:
  * BHD5.cs        - the header layout implemented below
  * SFUtil.cs      - FromPathHash, the filename hash
  * ArchiveKeys.cs - the RSA public keys, one per archive

HOW IT WORKS, because none of this is guessable:
  * A .bhd is RSA-encrypted. You DECRYPT WITH THE PUBLIC KEY: raw modexp, no
    padding, 256-byte cipher blocks in, 255-byte plain blocks out (drop the
    leading byte). That is backwards from normal RSA use and is the single
    thing most likely to confuse someone reading this later.
  * Filenames are NOT stored. Each entry carries a 32-bit hash of its path, so
    you cannot enumerate the archive - you can only ask "is this exact path in
    here?". That is fine for our purposes and is why there is no `list` verb.
  * Entries are grouped into buckets by hash % bucket_count, so a lookup only
    scans one bucket.

DS3 FileHeader is 40 bytes: hash u32, padded size i32, offset i64, sha offset
i64, aes key offset i64, unpadded size i64. Elden Ring's is different (64-bit
hash, different field order) and is handled too, but ER's file DATA is Oodle
Kraken compressed, which is a separate problem this module does not solve.
"""
from __future__ import annotations

import base64
import re
import struct
from dataclasses import dataclass
from pathlib import Path

DS3 = "DarkSouls3"
ELDEN_RING = "EldenRing"


# ---------------------------------------------------------------- path hashing

def path_hash(path: str) -> int:
    """SFUtil.FromPathHash: lowercase, backslashes to slashes, leading slash."""
    p = path.lower().replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    h = 0
    for ch in p:
        h = (h * 37 + ord(ch)) & 0xFFFFFFFF
    return h


# ------------------------------------------------------------------- RSA / PEM

def parse_pem_public_key(pem: str) -> tuple[int, int]:
    """PKCS#1 RSAPublicKey ::= SEQUENCE { modulus INTEGER, exponent INTEGER }."""
    b64 = "".join(l for l in pem.splitlines() if not l.startswith("-----"))
    der = base64.b64decode(b64)

    def read_len(data, i):
        n = data[i]; i += 1
        if n < 0x80:
            return n, i
        count = n & 0x7F
        return int.from_bytes(data[i:i + count], "big"), i + count

    assert der[0] == 0x30, "expected DER SEQUENCE"
    _, i = read_len(der, 1)
    ints = []
    for _ in range(2):
        assert der[i] == 0x02, "expected DER INTEGER"
        ln, i = read_len(der, i + 1)
        ints.append(int.from_bytes(der[i:i + ln], "big"))
        i += ln
    return ints[0], ints[1]          # modulus, exponent


def decrypt_bhd(raw: bytes, pem: str) -> bytes:
    """Raw RSA with the PUBLIC key. 256 in, 255 out, leading byte dropped."""
    n, e = parse_pem_public_key(pem)
    out = bytearray()
    for off in range(0, len(raw), 256):
        block = raw[off:off + 256]
        if len(block) < 256:
            break
        m = pow(int.from_bytes(block, "big"), e, n)
        out += m.to_bytes(256, "big")[1:]
    return bytes(out)


# ----------------------------------------------------------------- BHD5 header

@dataclass
class AESKey:
    """AES-128-ECB, no padding, applied only to specific byte ranges."""
    key: bytes
    ranges: list[tuple[int, int]]

    def decrypt(self, data: bytearray) -> None:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        cipher = Cipher(algorithms.AES(self.key), modes.ECB())
        for start, end in self.ranges:
            # -1 means "unused slot"; equal bounds mean an empty range.
            if start == -1 or end == -1 or start == end:
                continue
            end = min(end, len(data))
            count = (end - start) // 16 * 16      # ECB works in whole blocks
            if count <= 0:
                continue
            d = cipher.decryptor()
            data[start:start + count] = d.update(bytes(data[start:start + count])) + d.finalize()


@dataclass
class Entry:
    name_hash: int
    padded_size: int
    unpadded_size: int
    offset: int
    aes_key_offset: int
    aes: AESKey | None = None


class BHD5:
    def __init__(self, data: bytes, game: str = DS3):
        if data[:4] != b"BHD5":
            raise ValueError("not a BHD5 (decryption probably failed)")
        # byte 4 is 0 for big-endian, -1 (0xFF) for little. Every PC game is LE.
        big_endian = data[4] == 0
        if big_endian:
            raise NotImplementedError("big-endian BHD5 (console) not supported")
        one, _file_size, bucket_count, buckets_offset = struct.unpack_from("<4i", data, 8)
        if one != 1:
            raise ValueError(f"unexpected version field {one}")
        pos = 24
        salt_len = struct.unpack_from("<i", data, pos)[0]
        self.salt = data[pos + 4:pos + 4 + salt_len].decode("ascii", "replace")

        self.entries: dict[int, Entry] = {}
        for b in range(bucket_count):
            count, off = struct.unpack_from("<ii", data, buckets_offset + b * 8)
            for i in range(count):
                e = self._read_entry(data, off, i, game)
                if e.aes_key_offset:
                    e.aes = self._read_aes(data, e.aes_key_offset)
                self.entries[e.name_hash] = e

    @staticmethod
    def _read_aes(data: bytes, off: int) -> AESKey:
        key = data[off:off + 16]
        count = struct.unpack_from("<i", data, off + 16)[0]
        ranges = [struct.unpack_from("<qq", data, off + 20 + i * 16) for i in range(count)]
        return AESKey(key, ranges)

    @staticmethod
    def _read_entry(data: bytes, base: int, i: int, game: str) -> Entry:
        if game == ELDEN_RING:
            o = base + i * 40
            h, padded, unpadded, offset, _sha, aes = struct.unpack_from("<QiiQqq", data, o)
            return Entry(h, padded, unpadded, offset, aes)
        o = base + i * 40
        h, padded, offset, _sha, aes, unpadded = struct.unpack_from("<iiqqqq", data, o)
        return Entry(h & 0xFFFFFFFF, padded, unpadded, offset, aes)


# --------------------------------------------------------------------- archive

class DvdBnd:
    """One game's set of Data*.bhd/.bdt pairs, queried by exact path."""

    def __init__(self, game_dir: Path, keys: dict[str, str], game: str = DS3):
        self.game = game
        self.archives: list[tuple[Path, BHD5]] = []
        for bhd in sorted(game_dir.glob("*.bhd")):
            stem = bhd.stem
            bdt = bhd.with_suffix(".bdt")
            if not bdt.exists():
                continue
            raw = bhd.read_bytes()
            if raw[:4] != b"BHD5":
                key = keys.get(stem)
                if key is None:
                    continue                      # no key: cannot read, skip
                raw = decrypt_bhd(raw, key)
            try:
                self.archives.append((bdt, BHD5(raw, game)))
            except Exception:
                continue

    def get(self, path: str) -> bytes | None:
        h = path_hash(path)
        for bdt, bhd in self.archives:
            e = bhd.entries.get(h)
            if e is None:
                continue
            # Read the PADDED extent: encrypted ranges can run into the
            # padding, so decrypt first and only then trim to the real size.
            with open(bdt, "rb") as f:
                f.seek(e.offset)
                buf = bytearray(f.read(e.padded_size))
            if e.aes is not None:
                e.aes.decrypt(buf)
            size = e.unpadded_size if e.unpadded_size > 0 else e.padded_size
            return bytes(buf[:size])
        return None
