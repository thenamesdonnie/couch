# souls-extract — reading FromSoftware game archives on Linux, natively

Built 1 Sep 2026 for the Elden-Ring-UI-into-Dark-Souls-3 project, but there is
nothing project-specific in it. It reads Dark Souls 3, Elden Ring and (with the
same DCX code) Bloodborne archives with **no wine and no dotnet**.

The usual tools (UXM, WitchyBND, Yabber, Smithbox) are all Windows .NET.
`soulstruct` is native Python and handles BND4, TPF and DCX, but has **no BHD5
support at all** and refuses Oodle outright on Linux. BHD5 is the top-level
container everything else lives inside, so those two gaps are what this fills.

## What's here

| File | What it does |
|---|---|
| `dvdbnd.py` | BHD5/BDT reader: RSA header decryption, buckets, path hashing, AES range decryption |
| `oodle.py` | DCX unwrapping for both DFLT (zlib) and KRAK (Oodle), via ooz |
| `ooz-linux/` | The Linux port of ooz: portability shims, our patch, and a build script |

`soulstruct` supplies TPF and BND4 on top. `pip install soulstruct cryptography`.

## The things that are not guessable

**RSA is backwards.** A `.bhd` is decrypted with the PUBLIC key: raw modexp, no
padding, 256-byte cipher blocks in, 255-byte plain blocks out, dropping the
leading byte. Block size follows the modulus, so do not hardcode it if a game
ever ships a key that is not 2048-bit.

**Get Elden Ring's keys from the player's own executable.** The published key
lists (UXM, BinderTool) are stale — none of them opened a current install, and
FromSoft rotates them in patches. The keys sit in `eldenring.exe` as plain PEM
text; grep for `-----BEGIN RSA PUBLIC KEY-----`, and match each one to an
archive by trying it against the first block. Five keys, five archives. This is
version-proof and needs no external list.

**Filenames are not stored.** Entries carry a hash of the path, so you cannot
enumerate an archive, only ask "is this exact path present?". You need a path
dictionary for anything you cannot name.

**The path hash differs per game.**
- DS3 / Bloodborne / Sekiro: 32-bit, `hash = hash * 37 + char`
- Elden Ring: **64-bit, `hash = hash * 133 + char`**

Both lowercase the path, convert backslashes to forward slashes and prepend a
leading slash. The Elden Ring variant is not in any SoulsFormats fork I could
find; it was determined empirically by testing candidate primes against paths
that were near-certain to exist, and confirmed by 7 hits out of 9 versus 0.

**AES covers ranges, not whole files.** Each entry may carry a 16-byte key plus
a list of byte ranges, decrypted with AES-128-ECB, no padding. Ranges are
relative to the file start and can extend into the padding, so read the *padded*
extent, decrypt, and only then trim to the unpadded size.

**Elden Ring needs Oodle, and ooz has a bug.** See `ooz-linux/build.sh` for the
full explanation. Short version: ER compresses with `seekChunkReset`, so every
256KB block restarts its match window, and ooz got the window base wrong for
every block after the first. Everything under 256KB worked, everything over it
failed. That is fixed in our patch.

## Usage

```bash
tools/souls-extract/ooz-linux/build.sh      # once, builds libooz.so
```

```python
from dvdbnd import DvdBnd, DS3
bnd = DvdBnd(ds3_game_dir, ds3_keys, DS3)
data = bnd.get("/menu/01_common.tpf.dcx")
```

Then `oodle.dcx_decompress(data)` and `soulstruct.containers.TPF.from_bytes(...)`.

## Known gap

ooz has two decode paths its author never finished. They are instrumented, so
hitting one raises `OozUnimplemented` naming the function rather than a bare
`-1` that looks like data corruption. Nothing in DS3 or Elden Ring's menu files
has hit either so far. The fallback if one ever bites is the real `oo2core` DLL
that ships in the Elden Ring folder.

## Verified

- DS3: all 7 archives open, `menu/01_common.tpf.dcx` extracted, 126 textures.
- Elden Ring: all 5 archives open, `menu/hi/01_common.tpf.dcx` extracted,
  203,701,084 bytes decompressed in 0.7s, 56 textures.
- ooz: 60 of its 72 testdata files decompress, **identical before and after our
  patch**, so the patch causes no regression. The 12 failures are all
  `*.leviathan` and are a PRE-EXISTING ooz limitation, verified against an
  unpatched control build. Nothing in DS3 or Elden Ring's menu data uses
  Leviathan, so it has not bitten us.
