# DS3 graphics modernisation: what exists, what we can do (3 Sep 2026)

Researched with agent-reach (Exa + Jina) and the archive tools. Offline,
personal use.

## Existing mods (all file-based ones work through ModEngine2 on our stack)

| mod | what | notes |
|---|---|---|
| Texture Improvement (Nexus 1579, 2023) | ~1500 textures replaced/upscaled to 2K/4K, 24 GB | file overrides; if it ships menu/01_common.tpf.dcx our UI chain must run ON its copy |
| DS3TexUp (RunDevelopment, GitHub, CC0) | the upscaling project's code + metadata | tooling, not a pack |
| DS3 Visual Overhaul (1849, Apr 2026) | gparam lighting/fog edits, SSAO, dynamic shadows, colour, textures | file-based (Smithbox edits) |
| InfiniDetail (1778, Apr 2026) | no LOD pop-in, draw distance, Yebis effects, tonemapping | likely param + DLL |
| Dynamic Shadows and No Pop-in (2056) | world-wide dynamic shadows, LOD tables | companion to DS3LE Lite |
| DS3 Lighting Engine (FromSoftserve/Ragevitamins, 2025) | GGX lighting model, GTAO, screen-space shadows, FSR/DLSS; Lite on ko-fi, full "coming to Nexus" | a DX11-hooking DLL; Proton compatibility untested |
| Filmic RTGI (1856), eden CYCLES (808), Lighting Overhaul (163) | ReShade presets (RTGI is Marty's paid shader) | ReShade under Proton works; vkBasalt cannot run RTGI |
| Eclipsed Archdragon Peak (1576), Blue Sky (1612) | sky swap; fog colour | neither touches the cloud sea textures |
| Special K HDR retrofit | Windows only (needs the Windows HDR desktop) | on Linux the route is gamescope HDR + inverse tone mapping, and our gamescope wrap is benched (SIGABRT at 4K120, see couch-gamescope-switcher) |
| OptiScaler | DLSS/FSR injection | needs a game with upscaler inputs; DS3 has none (DS3LE adds them). Moot at 4K60 on the 9070 XT |

## The Archdragon Peak cloud sea, what it is made of

`/map/m32/m32_000{0..3}.tpfbhd` (1796 textures). The clouds are
`m32_00_kumo_*` ("kumo" = cloud): albedo tiles at **1024x1024 BC1 sRGB**
(01/11 are 1024x256 strips, 50 is 2048x512, 60 is 512x512), masks
`kumo_30_m/40_m` at 2048x2048 BC4, normals `_n`, a `sky_02_a` panorama at
4096x2048 BC7, `stormsky_03/04` strips. So the "outdated" look is 1024 px
BC1 cloud tiles stretched across a huge sea: soft mush plus BC1 block
artefacts on the gradients, and no volumetrics. Decoded sheet in the
session scratchpad (`kumo_sheet.png`); `tpf_png.decode` now handles the
DX10 BC1/2/3/4/5 codes those files use.

## What we can do ourselves

1. Cloud sea texture upscale: 4x the kumo albedo/mask/normal set with an
   AI upscaler (Real-ESRGAN class models handle clouds well), re-encode
   BC7 (needs a Linux BC7 encoder, bc7enc builds in a minute; uncompressed
   BGRA is 64 MB per 4K texture, too much x12), ship the TPFs through
   ModEngine2 as map/m32 overrides. Verification needs a save at Archdragon
   Peak: the harness character is in the Cemetery, so either a warp step
   in the journey or Donnie's eyes on the TV.
2. Install Texture Improvement + Visual Overhaul under ModEngine2 and
   rebase our UI chain on their 01_common if they ship one.
3. Try DS3 Lighting Engine Lite under Proton (DLL, unknown).
4. ReShade under Proton for RTGI-style GI (paid shader).

## What else Elden Ring can donate (we can decompress its archives)

Textures transfer (TPF/DDS in both games, DS3 reads BC7): ER's Farum
Azula cloud/sky assets (in /asset/aet/*, numeric names, needs the map's
asset list to find them), fog and mist particle textures, rock and
ground detail textures where a DS3 material has the same role. Sounds
convert (ER Wwise .wem -> DS3 FMOD .fsb) for menu ambience and the "YOU
DIED" sting. Music likewise for the title screen. Item icons exist in
SB_Icon_00..03 but swapping item identity is a design choice. Models do
not transfer (FLVER versions and material/shader ids differ).

## The Archdragon Peak fog, dissected (3 Sep evening)

Donnie: "the way it clips through everything so it does not feel like it
is coming from the doors or in the room, like it is placed on top of the
screen". Three ingredients, all read out of the files:

1. The cloud SEA is geometry: cloud-sea meshes textured with the `kumo`
   tiles, 1024x1024 BC1. Where a mesh plane meets a floor or a doorway it
   is a hard edge, and BC1 blocks the soft gradients.
2. The fog WISPS are particle billboards (`BillboardEx`, 452 of them in
   the 132 readable m32 FXRs) drawing 8x8 flipbook smoke sheets, i.e.
   128 px per frame (s11630, s11633, s11617, s11624 ...), scaled to 7 to
   30 m.
3. The ambient HAZE is the same billboard type scaled to 30 and 100 m
   (f000650305, f000732115) drawing s50065, a 64x64 radial blob.

DS3 does have soft particles: 376 of 456 billboards carry
`depthBlend=true`, but the fade control (`unkDepthBlend1`) is 1.0 (0.1
on f000832040), i.e. a default-width fade on a hundred metre sprite, which
is why the haze looks cut by every wall and floor. (Corrected below: the
field is almost certainly a unitless scale on the falloff, not a distance
in metres. Nobody has published what it is. See "Depth fade tool".)

Tooling: `@cccode/fxr` v32 (installed at data/ds3-ui-port/fxr-node) reads
and writes DS3's FXR version 4 with named fields. (Corrected below: the
"4 of the 136 files fail to parse" reading was a node Buffer byteOffset
bug on our side, not a file problem. All 136 parse.) Extracted
FXRs at data/ds3-ui-port/extract/ds3/sfx_m32/, the dump in the session
scratchpad (m32_fxr_dump.txt). Elden Ring's sprite sheets are reachable
(`/sfx/sfxbnd_commoneffects.ffxbnd.dcx`, ER keys + ooz).

Fixes, in order of effect per hour:
A. Depth fade: raise `unkDepthBlend1` on the big fog and haze billboards,
   ship `frpg_sfxbnd_m32_effect.ffxbnd.dcx` as an override. DONE, see
   "Depth fade tool" below; built but not yet judged on the TV.
B. Sprite quality: 4x the fog flipbook sheets and the haze blob, BC7.
C. Cloud sea: 4x the kumo albedo/mask/normal tiles, BC7.
D. Donor sprites from ER where the frame layout matches.
Volumetric fog is engine-level (DS3 Lighting Engine territory).
Verification needs a save at Archdragon Peak.

## Depth fade tool (fix A, built 3 Sep 2026)

`tools/ds3-fog-soften` (python wrapper) plus
`data/ds3-ui-port/fxr-node/fog_soften.mjs` (the FXR half). Extracts an effect
binder from the archives, widens the depth fade on the big fog and haze
billboards, repacks, and proves the result. Nothing is written into the game
install or the mod folder; it prints the copy command.

### What the depth fields mean, honestly

`depthBlend` (DS3 fields1 index 14) is documented and unambiguous: the
soft-particle toggle, "fade out with distance from the object's surface that is
blocking the view of the particle."

`unkDepthBlend1` and `unkDepthBlend2` (DS3 fields2 indices 22 and 23, on-disk
dwords 25 and 26 because bloomColor is a Vector4) are BOTH "Unknown float." in
@cccode/fxr, and the public record has nothing better. RainbowStoneFXR and the
community ER FXR Notes sheet, which share one source, say only "These two
fields control how the depth blending effect works, but exactly how is
unknown." The older DS3 FXR Notes sheet is the most informative line anyone has
written: field 25 "Always >0. Some scale or something, maybe?", field 26
"Always 0". No issue, commit, thread or mod has ever published a before/after
test of either.

Both ARE written for DS3: they sit in the DS3 `fields2` list in the library's
per-game structure table, so the library reads and writes them for
Game.DarkSouls3. The edit is possible; only the meaning is uncertain.

Two traps recorded so we do not fall into them twice:

* @cccode/fxr tags `unkDepthBlend2` with `ScaleCondition.Distance`, which reads
  like a claim that it is a distance in metres. It is not a finding. That flag
  arrived in a bulk sweep (abae51f, "Scaling is now data driven", 329 flags in
  one commit) and was reclassified in a second sweep (55d42f2). When the author
  actually identified the neighbouring field he said so in the changelog
  ("unk_ds3_f2_29 has been identified as some kind of view distance
  threshold"). Nothing like that was ever written for unkDepthBlend2.
* The advice to zero `unk_sdt_f2_32` before testing depth blending does not
  apply to DS3: that field starts at Sekiro, DS3's fields2 stops at
  `unk_ds3_f2_29`.

The vanilla numbers point at `unkDepthBlend1` as a unitless SCALE on the
falloff rather than a distance. Across the 569 depth-capable actions in m32:

    unkDepthBlend1: 1.0 x507  2.0 x26  2.5 x14  0.5 x11  1.5 x6  0.1 x3  0.25 x1  0.75 x1
    unkDepthBlend2: 0.0 x566, plus 100 / 500 / 1000 (all three in f000832002)

unkDepthBlend2 being zero almost everywhere rules it out as THE fade distance,
since depth blending demonstrably works with it at zero. So the tool defaults to
`--field unkDepthBlend1`. Under either reading, raising it widens the band. The
caveat to watch on the TV: the default clamp tops out at 15.0, six times the
largest value FromSoft ever authored, so if the field is a multiplier the big
haze sheets may fade too eagerly near geometry. `--fade-max 4` is the dial. The
definitive test is a live sweep with fxr-reloader (0 / 0.1 / 1 / 10 / 100 on one
wall-intersecting particle), which would put us ahead of the entire public
record.

### Round trip: the library cannot rewrite these files cleanly

`FXR.read` then `toArrayBuffer` is NOT byte-faithful. Measured on all 136 m32
files: 0 of 136 byte-identical, though every file returns the same LENGTH. The
churn is structural, not semantic: a trailing 0x01 marker byte in property
headers written back as 0x00 (dword `74270001` -> `74270000`), a count of 255
written back as 256, section offsets shifted by 16, offset slots the original
left at 0 filled in. Worst offenders: f000221504 17,555 bytes (16 percent of the
file), f000650114 16,041, f000650137 15,988. Reproduce with
`node roundtrip_test.mjs <dir>`.

So the tool does NOT re-serialise. It uses the library only to read, locates
each action's `fields1 + fields2` block in the ORIGINAL bytes by exact match
(the two lists are stored back to back, so one match pins both), and overwrites
the two dwords. Result: byte-identical to vanilla apart from the intended
floats, and the tool proves it by diffing the patched buffer against the
original and refusing to write any file with a byte changed outside the dwords
it named. Measured on the m32 build: **104 bytes changed across 28 files, 0 of
them stray.**

Two things make the locate step non-trivial, both handled:

* Vanilla actions do not always carry the full field list; the library pads a
  short on-disk `fields2` with its own defaults. 11 of the 28 fog effects hit
  this, their on-disk fields2 stopping at 25 or 26 of 27 names. The tool
  searches with fields1 plus a fields2 PREFIX ending at the target field, and
  shortens fields1 from the tail until the concatenation matches, which is
  exactly where our field count equals the file's.
* Several actions in one file routinely encode to the same bytes. f000732200
  has two BillboardEx actions on texture 11633 that differ only in their size
  curve (2 m and 40 m), so one pattern has two hits. The tool groups ALL
  depth-capable actions, pairs hit k with action k (file order against walk
  order), then proves the pairing by re-reading the patched file and checking
  every action by index, including that no action we did not target moved.

### The "4 files do not parse" story was a node bug, not a file problem

f000432002/012/022 and f000613815 reported "Read: 47 | Expected: 5396550".
5396550 is `FXR` as a little-endian uint32 and 47 is `/`, i.e. the reader was
looking at the wrong place in memory. `fs.readFileSync` returns a Buffer that is
a VIEW into a shared 64 KB pool for small files, so `byteOffset` is non-zero,
and the library reads from `buffer.buffer` ignoring it. Wrapping in
`new Uint8Array(...)` copies to a standalone ArrayBuffer. **All 136 m32 entries
parse, and all 1818 commoneffects entries parse.** Nothing needs passing
through untouched.

### The m32 build

`tools/ds3-fog-soften` with the defaults (fade = 0.25 x width, clamped 2..15 m,
textures 11630/11633/11617/11624/11626/11621/11623/50065/50255, width >= 5 m,
`depthBlend` forced on). 3000 and 1001 are glows and are deliberately out: a
glow that fades near geometry loses the bloom that is the point of it.

50 particles in 28 effects, no skips. The ones that matter:

| effect | action | fog tex | width m | old | new |
|---|---|---|---|---|---|
| f000732115 | BillboardEx | 50065 | 100.0 | 1.0 | 15.0 |
| f000732100 | BillboardEx | 11633 | 40.0 | 1.0 | 10.0 |
| f000732210 | BillboardEx | 11633 | 40.0 | 1.0 | 10.0 |
| f000732220 | BillboardEx | 11633 | 40.0 | 1.0 | 10.0 |
| f000732230 | BillboardEx | 11633 | 40.0 | 1.0 | 10.0 |
| f000650305 | BillboardEx | 50065 | 30.0 | 1.0 | 7.5 |
| f000832040 | MultiTextureBillboardEx x2 + BillboardEx | 50255 | 30.0 | 0.1 | 7.5 |
| f000732300 | BillboardEx | 11633 | 20.0 | 1.0 | 5.0 |
| f000650131 / f000650140 | BillboardEx | 50065 | 10.0 | 1.0 | 2.5 |
| 37 more at 5.0 to 7.5 m | BillboardEx | 11630 / 11633 / 50065 | | 1.0 or 0.5 | 2.0 |

f000732115 is the ambient haze the doc identified earlier, and it is the single
biggest win: a 100 m sprite that faded over one metre now fades over fifteen.

Repack proof: `data/ds3-ui-port/build/fog/frpg_sfxbnd_m32_effect.ffxbnd.dcx`,
243,826 bytes DCX. Reopened after writing: 136 entries, ids match, paths match,
flags match, and all 50 fog particles read back out of the built binder with
the new `unkDepthBlend1` and `depthBlend` on. That check compares MULTISETS,
not dicts: several particles in one effect share an effect id, action type,
texture and width, and a dict key silently collapsed them into "35 of 35"
before the comparison was fixed. The rebuilt payload is 2,928,504 bytes against
vanilla's 2,927,152: soulstruct's BND4 writer appends ten zero pad bytes after
every entry "for byte-perfect writes", so 135 gaps x 10 bytes less an 8-byte
shift of the data region. Recorded entry sizes and offsets are correct, it is
padding only.

Deploy (deliberately NOT automatic, the harness cannot capture Archdragon Peak
yet):

    mkdir -p ~/couch/data/ds3-shot/game/mod/sfx
    cp ~/couch/data/ds3-ui-port/build/fog/frpg_sfxbnd_m32_effect.ffxbnd.dcx \
       ~/couch/data/ds3-shot/game/mod/sfx/frpg_sfxbnd_m32_effect.ffxbnd.dcx

### Common effects, dry run only

`tools/ds3-fog-soften --binder commoneffects --dry-run`. 1818 entries, all
parse. 19 particles in 10 effects use the fog textures at >= 5 m:

| effect | action | fog tex | width m | old | new |
|---|---|---|---|---|---|
| f000000002 | MultiTextureBillboardEx x2 + BillboardEx | 50255 | 6.25 | 0.1 | 2.0 |
| f000000003 | MultiTextureBillboardEx x2 + BillboardEx | 50255 | 10.0 | 0.1 | 2.5 |
| f000000004 | MultiTextureBillboardEx x2 + BillboardEx | 50255 | 15.0 | 0.1 | 3.75 |
| f000440002 | BillboardEx | 50065 | 5.0 | 1.0 | 2.0 |
| f000440035 | BillboardEx | 50065 | 5.0 | 1.0 | 2.0 |
| f000440225 | BillboardEx | 11630 | 5.0 | 1.0 | 2.0 |
| f000523551 | BillboardEx | 50065 | 6.25 | 1.0 | 2.0 |
| f000525312 | BillboardEx | 50065 | 20.0 | 1.0 | 5.0 |
| f000526204 | BillboardEx x2 | 11621, 11626 | 7.5 | 1.0 | 2.0 |
| f000526252 | BillboardEx x3 | 50065 | 5.0 | 0.1 | 2.0 |

f000000002/003/004 are the low-numbered common effects, which usually means
something ubiquitous (bonfire or ambient smoke), so this binder is the one to
change LAST and only after m32 has been judged on the TV. One of the
f000000002 billboards is also the only particle in either binder with
`depthBlend` off, so it would go from hard-cut to soft in one step.

### Depth fade, verified on screen (3 Sep 19:45, Donnie's save at Archdragon Peak)

The sandbox save was refreshed from the real prefix (his character stands
in the temple with fog through the doorway; baseline
build/fog/archdragon_baseline_4k.png). Three builds of
frpg_sfxbnd_m32_effect.ffxbnd.dcx captured at the same spot, mean
luminance of four regions (floor left, floor right, doorway, upper right):

| build | floor L | floor R | doorway | upper R |
|---|---|---|---|---|
| stock (fade 1.0) | 38.2 | 41.0 | 63.1 | 40.4 |
| fade 2..5 m (0.25 x width) | 42.0 | 40.2 | 59.3 | 44.3 |
| fade up to 15 m | 54.6 | 45.3 | 65.9 | 39.8 |
| tracer, fade 0.01 | 35.8 | 44.1 | 68.0 | 43.1 |

The tracer thinned the haze to almost nothing near every surface and the
15 m build filled the room, so the override loads and `unkDepthBlend1` is
the depth-fade distance (bigger = more of each sprite survives near
geometry). 15 m roughly doubles the floor haze; 2..5 m keeps stock density
and softens the intersections. DEPLOYED: `--fade-min 2 --fade-max 5`
(copy kept as build/fog/DEPLOYED_m32_fade2-5.ffxbnd.dcx). The commoneffects
binder (19 particles in 10 effects, three of them in the low-numbered
f000000002/3/4) is untouched; do it after the map-specific one is judged.

## Pipeline: `tools/ds3-texup` (fixes B and C, built 3 Sep 2026)

Fixes B and C are now a tool, not a plan. It reads the archives through
souls-extract, upscales, re-encodes BC7/BC4 with full mip chains, and rebuilds
the binders into `data/ds3-ui-port/build/texup/mod/`. Nothing is deployed and
the real install is never touched.

```
tools/ds3-texup extract | upscale | encode | pack | preview | seamcheck
tools/ds3-texup all           the lot, in order
tools/ds3-texup report        the manifest as a table
tools/ds3-texup deploy-cmds   prints the cp commands, does not run them
```
Flags: `--only SUBSTR`, `--force`, `--quality N` (bc7e 0..6, default 6).

### The two build fixes that make BC7 possible on Linux

"Nothing on Linux encodes BC7" is dead. `bc7enc_rdo`
(github richgel999/bc7enc_rdo, `~/src/bc7enc_rdo`) builds in about a minute
once two things are fixed, neither of which is in the README:

1. `ert.h` uses `uint8_t`/`uint32_t` without including `<cstdint>`. GCC 13+
   errors with "'uint8_t' does not name a type" and then cascades into dozens
   of bogus "no member named m_c" messages that look like a broken checkout.
   Add `#include <cstdint>` at the top of `ert.h`.
2. For the good encoder you want `-DSUPPORT_BC7E=TRUE`, which needs ispc
   (`~/src/ispc-v1.23.0-linux`, a tarball, no install). The CMakeLists invokes
   ispc without `--pic`, and the link then fails with
   "relocation R_X86_64_32S against `.bss' can not be used when making a PIE
   object". Add `--pic` to the ispc command in `CMakeLists.txt`.

Built into `~/src/bc7enc_rdo/build-bc7e/bc7enc`; `-U -u6` selects bc7e.ispc at
its highest quality, which uses all BC7 modes rather than bc7enc.cpp's 1/5/6/7.
Measured: 4096x4096 in 6.1 s wall (48 s CPU across the pool). Compressonator
was never needed. bc7enc cannot write mipmaps, so ds3-texup generates the chain
itself and concatenates the encoded levels.

### Upscaler

`realesrgan-ncnn-vulkan` v0.2.5.0 (`~/src/realesrgan`), model
`realesrgan-x4plus`. Static Vulkan binary, runs on the 9070 XT through RADV, no
PyTorch and no ROCm. 1024x1024 -> 4096x4096 in 16.0 s whole-sheet, 5.7 s as 64
separate 128 px frames (the binary reloads the model and re-enumerates Vulkan
on every start, so batching small tiles wins).

**Two findings worth more than the tool itself.**

*It bicubics your alpha.* Give realesrgan-ncnn-vulkan an RGBA PNG and the
network only ever sees RGB; alpha is bicubic-resized. Measured on s50065: its
alpha output sits 0.26/255 from a bicubic resize and 1.66/255 from the network's
own output on that channel. Every fog sprite in this map IS its alpha channel,
so the naive call decides the only channel that matters with the cheapest filter
in the binary, silently.

*And the network is the wrong tool for that channel anyway.* Split out and run
through the net, one 128 px frame of s11630 at 4x:

| alpha path | what it does to a fog puff |
|---|---|
| LANCZOS | soft feathered edge survives, nothing invented |
| realesrgan-x4plus | edge hardens, the feather becomes RADIAL FILAMENTS, a hairy fringe |
| realesr-animevideov3-x4 | feather smoothed away into a flat blob |

A smoke billboard is its soft edge, and these are drawn 7 to 30 m tall, so the
filaments are damage, not detail. **RGB through the network, alpha through
LANCZOS.** RGB is dilated into the transparent region first (exact distance
transform) so the net cannot drag junk from behind alpha=0 into a visible edge.

### Formats: DS3 reads the DDS header, not the TPF format byte

Proof from its own files: `m32_00_sky_02_a` and the stormsky set are TPF format
102 with DXGI **99** (BC7_UNORM_SRGB), while the sfx sprites are TPF format 102
with DXGI **98** (BC7_UNORM). One TPF code, two DXGI codes. So ds3-texup clones
each original DDS header and patches only width, height, mipMapCount,
linearSize, and the DXGI code where a format really changes. Flags 0xa1007 and
caps 0x401008 come through untouched rather than being reinvented.

The one deliberate format change is the cloud albedo: BC1_UNORM_SRGB (DXGI 72,
TPF 0/1), which is what puts block artefacts on the soft gradients, becomes
BC7_UNORM_SRGB (DXGI 99, TPF 102) - a pairing DS3 already ships. Normals stay
BC7 linear (DXGI 98, TPF 106/107), masks stay BC4 (FourCC ATI1, TPF 103).

sRGB albedo mips are built in LINEAR light. Halving sRGB bytes directly
brightens every level, which on a cloud sea reads as a horizon that pales with
distance.

Normals are two-channel: X in R, Y in G, B a near-constant third channel
(measured on kumo_20_n: R and G span 66..189 around 127, B sits at 57..66).
LANCZOS overshoot can push (x, y) off the unit disc, so anything outside is
scaled back onto it. Measured count on this set: 0 texels, on all four normals.

### Flipbook seams

Sheets are sliced into frames before upscaling, for the network AND for LANCZOS
(at 4x, LANCZOS reaches about four source texels either side). `seamcheck`
measures whole-sheet against per-frame as a function of distance from a frame
edge. s11630, 8x8 of 128 px:

| distance from frame edge | RGB mean / max diff |
|---|---|
| 0 px | 1.51 / **57** |
| 4 px | 1.31 / **64** |
| 16 px | 1.15 / 10 |
| 32 px | 0.96 / 6 |
| 256 px (frame interior) | 1.11 / 29 |

The means barely move but the maxima spike to 57-64/255 within 8 px of a frame
edge and fall to 6-10 by 32 px in. That spike is one frame bleeding into the
next, and it is why the slice exists. Alpha shows 0 difference at every seam
column on this sheet because its cell gutters are exactly alpha 0.

s11640 is the exception: 8 columns x **5** rows in a 2048x1024 sheet, so cells
are 204.8 px tall and there is no integer slice. It is upscaled whole.

### What was produced

33 textures upscaled, 1 (`kumo_50_m`, already 4096x1024) skipped. 4x, capped at
4096 on the long side, so 2048 sources get 2x. The sky panorama
`m32_00_sky_02_a` is the one exception, allowed 8192x4096 because it is the
single texture wrapped round the whole sky: 4x then LANCZOS halved, encoded in
72.9 s to 44,739,428 bytes over 14 mip levels, and it decodes back at 55.46 dB.

Round-trip PSNR (decode the finished DDS, score against the PNG it came from):
**min 44.39, median 56.37, max 75.33 dB over 33 textures**. The floor is
s11640, whose near-binary alpha is the hardest thing here for BC7; the albedo
tiles all sit at 55-59 dB.

Binder rebuild, and the proof:

| binder | entries | replaced | untouched entries bit-identical | size |
|---|---|---|---|---|
| map/m32/m32_0000 | 245 | 20 | 225/225 | 138.7 MB -> 256.3 MB |
| map/m32/m32_0003 | 600 | 3 | 597/597 | 129.8 MB -> 165.0 MB |
| sfx/frpg_sfxbnd_commoneffects_resource | 349 | 10 | 339/339 | -> 117.9 MB |

Every rebuilt binder is reloaded from disk, every replaced texture is decoded
again at its new size, and every entry we did not touch is hashed against what
the archive held. About 539 MB of mod for this map.

### The first build BROKE the game, and why every check passed anyway

Captured at Archdragon Peak: the temple arch, ceiling, floor stones and pillars
drew the WRONG textures, white geometry chunks appeared, and the fog became
dense white slabs. Untouched geometry drawing wrong textures is not a texture
fault, it is the container handing the engine the wrong entry.

The first build re-serialised the binders with soulstruct and proved itself by
reloading them with soulstruct. That proof is worth nothing: a library
re-parsing its own output only shows the library is self-consistent. soulstruct
finds entries by walking the record array, so it cannot see either of the two
faults that were actually there.

**Fault 1, the fatal one: `path_hashes_offset` is an ABSOLUTE file offset.** A
BND4 hash table (`hash_table_type == 4`) is laid out as

```
+0x00 int64  path_hashes_offset   ABSOLUTE, from the start of the FILE
+0x08 uint32 group_count
+0x0C bytes  10 08 08 00          header size, group record size, hash record size
+0x10        group_count * (int32 length, int32 first_index)
then         (uint32 path_hash, int32 ENTRY INDEX) pairs
```

and the pairs point at ENTRY INDICES, i.e. positions in the entry-header array.
The re-serialised BHD came out **2 bytes shorter** than the original (24,990 vs
24,992) because soulstruct does not pad the UTF-16 name block to 8 before the
table. So the table landed at 0x58BE instead of 0x58C0, its own header still
said the path hashes were at 23032 when they were at 23030, and the last record
ran 2 bytes past the end of the file. Every path the engine looked up read the
hash array skewed and got a stale index pointing at an unrelated texture. That
is the broken frame, exactly.

**Fault 2: entry data alignment.** soulstruct writes 10 pad bytes between entry
data blocks. BND4/BXF4 requires each entry's data to be 16-byte aligned
(`bw.Pad(0x10)` in SoulsFormats). Measured: 228 of 245 offsets misaligned in the
broken build, against 245 of 245 in the shipped file and 42,548 of 42,548 across
100 vanilla DS3 tpfbhd files.

Both were found by reading DS3's own bytes and SoulsFormats' source. Two more
things worth writing down while we were in there:

* **soulstruct's path hash is not FromSoft's.** `binder_hash.py` computes
  `h += i * 37 + ord(c)` with `i` the enumerate index and no lowercasing.
  FromSoft's (`SFUtil.FromPathHash`) is lowercase, backslashes to slashes,
  leading `/`, then `h = h * 37 + c` wrapping at 32 bits. Verified on 42,548
  real records, 100 percent match. So letting soulstruct REBUILD a hash table
  would have been just as fatal as letting it copy a stale one.
* **soulstruct cannot write a BND4 split binder at all** in 2.3.2:
  `_to_split_writers()` ends with `header_writer.fill("file_size", 0)` on a V4
  header that has no such field, and builds the BDT header with
  `BDTHeaderV4.object_to_writer(binder)` when a `Binder` has none of `unknown1`,
  `unknown2` or `bit_little_endian` as attributes. It also writes the BDT magic
  as `BDT4` when DS3 ships `BDF4`, and gets away with it because `from_bytes`
  never parses the BDT header, it seeks by the offsets in the BHD.

### The fix: patch in place, never re-serialise

`pack` now appends each new payload to the END of the original bytes, 16-byte
aligned, and rewrites ONLY three fields of the replaced entry's own record:
compressed size, uncompressed size, data offset (offsets 0x08, 0x10 and 0x18 of
the 0x24-byte record). Every other byte of both files keeps its value AND its
position, so the hash table stays valid by construction. The cost is dead space,
8.6 MB in m32_0000 and 9.3 MB in m32_0003, which is the right price.

Record layout, for the next person (DS3 format byte 0x74, entry header size
0x24, `LongOffsets` NOT set so the data offset is 32-bit):

```
+0x00 u8 flags (0x40)   +0x01 pad3   +0x04 int32 = -1
+0x08 int64 compressed_size          +0x10 int64 uncompressed_size
+0x18 uint32 data_offset             +0x1C int32 entry_id
+0x20 uint32 name_offset (UTF-16LE, NUL-NUL terminated)
```

Verified output, all three binders:

| check | m32_0000 | m32_0003 | commoneffects |
|---|---|---|---|
| BHD length unchanged | 24,992 = 24,992 | 61,752 = 61,752 | n/a, single file |
| header, name block, hash table byte-identical and in place | yes | yes | yes |
| path hashes resolving to the right entry | 245/245 | 600/600 | 349/349 |
| entry data 16-byte aligned | 245/245 | 600/600 | 349/349 |
| untouched records byte-identical | 225/225 | 597/597 | 339/339 |
| changed byte ranges, all inside a replaced record | 60 | 9 | 48 |
| original prefix unchanged, growth appended only | yes | yes | yes |

`tools/ds3-texup check FILE [BDT]` runs that structural test on any binder. As
controls it passes the shipped m32_0000 and the Nexus Texture Improvement pack's
rebuilt m32_0000, which is known to run in the game.

### The texture layers were never the problem

Compared against a shipped BC7 map texture (`m32_00_sky_02_a`) and against the
known-good Texture Improvement pack:

* **DCX wrapper**: byte-identical to a shipped entry apart from the two size
  fields. Version 0x00010000, DFLT, level 9, same DCS/DCP/DCA blocks.
* **TPF texture record**: format 102, texture type 0, texture flags 0,
  mipmap count matching the DDS. Same as shipped.
* **DDS header**: 3 bytes differ from the shipped BC7 panorama, in `height` and
  `linearSize`. Nothing else.
* The TPF container's `data_size = file_size + 2` and `file_offset = 72`, which
  looked like a soulstruct quirk, appear IDENTICALLY in the Texture Improvement
  pack that runs fine. Not a fault.
* Entry flags stay 0x40 and compressed size equals uncompressed size, because
  these binders do not use per-entry compression: the payload is already a
  complete `.tpf.dcx`.

### Deploying

Nothing is deployed. `tools/ds3-texup deploy-cmds` prints the copies into
`data/ds3-shot/game/mod/` (which is what `config_darksouls3.toml` points
ModEngine2 at), as TWO separate blocks: `mod-map/` (the cloud sea, sky and storm
strips) and `mod-sfx/` (the ten fog and haze sprites). They are separate so a
capture can blame one of them rather than both. Deploy one, capture, then the
other.

Previews at `data/ds3-ui-port/build/texup/preview_*.png` (original nearest-
neighbour vs upscaled, both at 1:1): kumo_20_a shows the BC1 blocks gone off the
gradients, s11630 shows real puff structure with the soft edge intact,
stormsky_03_a shows the cloud bank resolving.

## The Nexus packs, downloaded and dissected (3 Sep 20:30, premium API)

All at /mnt/disk1/ds3-mods/nexus (69 GB), extracted under
/mnt/disk1/ds3-mods/staging (`ti/` is the full Texture Improvement).

| pack | layout | notes |
|---|---|---|
| Texture Improvement 1.1 (4K parts 1..3 + Characters) | `map/mXX/*.tpfbhd+bdt` full binders per map, `chr/*.texbnd.dcx` | m32: same entry counts and SAME .tpfbhd size as the originals, 48/83/74/115 entries changed per binder. A working binder rebuild to learn from. (Corrected in "Merged m32" below: eleven of them ARE kumo cloud tiles, `kumo_01/02/03/10/11/20/30/40/50/60/70_a`; the sky and storm strips it does leave alone.) |
| DS3 Visual Overhaul 0.6 | `param/drawparam/*.gparam` (204), `map/MapStudio/*.msb` (37), `map/mXX_.../*.btl` lights, one mapbnd, and full m32 tpfbhd+bdt | its m32 binders change ONLY `_r` (reflectance) textures, 27/82/72/90 per binder, zero overlap with the texture pack; its .tpfbhd files are a different size (another writer), also known to work |
| InfiniDetail 0.3 | old ModEngine 1 layout (`dinput8.dll` + `modengine.ini`, overrides under `InfiniDetail/`): gparams, params, msg, event, obj, and sfx `*_effect.ffxbnd` for m31/m37/m39/m45/m51 + commoneffects | gparam conflicts with Visual Overhaul; its commoneffects effect binder would collide with a future fog fade on that binder |
| Dynamic Shadows 0.2 | `Data0.bdt` (whole params archive) + MSBs + btl for ~16 maps | MSB/btl conflicts with Visual Overhaul, which already claims dynamic shadows; skip |
| DS3 TAA | one ini | trivial |

Merge plan: base = Texture Improvement binders; patch Visual Overhaul's `_r`
entries and our kumo/sky/sfx upscales into them entry by entry with the
in-place patcher (once it is proven in game); Visual Overhaul's gparams,
MSBs and btl on top; our menu/font/sfx-effect overrides first. ModEngine2
takes several mod directories, so the file-level layering is config, and
only the binders that two sources both touch need merging.

Checker results on the packs (`tools/ds3-texup check`): Texture
Improvement's m32_0000 and m30_0000 are structurally sound (hash table
resolves 245/245 and 811/811, all data 16-byte aligned). Visual Overhaul's
m32_0000 appeared to resolve 0/245 hashes with a smaller BHD (18080 bytes).
THAT WAS OUR BUG, not theirs: BND4 header byte 0x30 is the name encoding and
VO's writer sets it to 0 (single-byte) where FromSoft sets 1 (UTF-16), so our
reader was hashing mojibake. With the encoding honoured all four of VO's m32
binders pass `check` outright. See "Merged m32" below. Both packs are staged as extra ModEngine2 mod directories
(data/ds3-shot/game/mod-ti and mod-vo, symlinks to /mnt/disk1), not yet
listed in any config.

### Deployed (3 Sep 20:30)

Our mod dir now carries the depth-fade m32 effect binder, the 4x kumo/sky
map binders (patched in place, `tools/ds3-texup check` clean) and the 4x
fog sprite resource binder; ModEngine2 loads it first, then Visual
Overhaul, then the Texture Improvement 4K pack, in both the sandbox and the
real launcher config. The sandbox booted in 86 s with all three and
rendered Archdragon Peak correctly. The in-place packer's root-cause
write-up (hash table offset, 16-byte alignment, soulstruct's writer) is in
the Pipeline section above.

## Merged m32: one binder carrying all three sources (3 Sep 2026, late)

### The problem

ModEngine2's mod loader is FIRST MATCH WINS on whole FILES, not on entries.
Three mods that each ship a complete `map/m32/m32_0000.tpfbhd+bdt` therefore do
not layer, they shadow. With `mod` listed first, our four upscaled cloud
textures were the only thing the game saw in that map: the Texture Improvement
4K stone and Visual Overhaul's reflectance maps were both dead in Archdragon
Peak, in the exact spot we keep photographing.

### The tool

`tools/ds3-texup pack` grew three options, all built on the SAME in-place
patcher the earlier build proved (append 16-byte aligned, rewrite only the
replaced entry's own compressed size, uncompressed size and data offset, never
re-serialise):

    --base-dir DIR   start from this pack's binders. The base supplies the
                     CONTAINER too: header, name block, hash table and every
                     record we do not replace keep their bytes and their file
                     positions, so the base's hash table stays valid by
                     construction.
    --inject DIR     take every entry in DIR's binders whose payload differs
                     from the GAME ORIGINAL and patch it into the base.
                     Repeatable; later wins. ENTRY DATA ONLY, never the
                     container.
    --out-name NAME  build subdirectory (default mod-map)
    --skip-sfx       map binders only

Plus: `--only` now applies to `pack` as well, `m32_0001` and `m32_0002` joined
`MAP_BINDERS` (a binder with nothing to do is still skipped), and `check` reads
only the BDT's SIZE rather than its bytes, because a merged BDT is 1.5 GB.

Why diff against the archive rather than trust a mod's file list: these packs
ship FULL binders, all 245/499/452/600 entries, of which only a handful are
edited. Copying a whole binder would overwrite the base pack's work with vanilla
bytes. The only honest definition of "what this mod changed" is a
payload-by-payload comparison with the game's own archive.

    tools/ds3-texup pack --skip-sfx --out-name mod-map-merged \
      --base-dir /mnt/disk1/ds3-mods/staging/ti \
      --inject   /mnt/disk1/ds3-mods/staging/visual-overhaul

### Two things the merge found in the reader

**Visual Overhaul's binders are NOT broken.** This doc previously recorded
"VO's m32_0000 resolves 0/245 hashes ... works but unexplained". That was our
bug, not theirs. BND4 header byte 0x30 is the NAME ENCODING: FromSoft and the
Texture Improvement pack write 1 (UTF-16LE), VO's writer writes 0 (single-byte).
Reading a `unicode = 0` binder as UTF-16 does not fail, it succeeds one byte out
of phase, so `m32_00_c3010_Angle01_r.tpf.dcx` came back as `㍭弲〰...` and every
path hash then compared against a mojibake name. With the encoding honoured,
ALL FOUR of VO's m32 binders pass `check`: hash tables consistent and resolving
245/245, 499/499, 452/452 and 600/600, all data 16-byte aligned, nothing running
past the end of the BDT. The smaller BHDs (18,080 against 24,992) are just the
single-byte name block. VO's container is still not copied, because the base's
is what the merged records are laid out for, but "unexplained" is retired.

**Texture Improvement DOES upscale eleven of our cloud tiles.** The earlier
reading, "none of them the kumo cloud tiles or the sky", was wrong. TI changes
`m32_00_kumo_01/02/03/10/11/20/30/40/50/60/70_a`, i.e. eleven of the twenty
entries we replace in m32_0000. It does not touch the masks, the normals, the
sky panorama or the storm strips. Ours is applied last and wins, deliberately:
our set is the one measured in the Pipeline section (BC1 to BC7, mips built in
linear light, 44.4 to 75.3 dB round trip) and the one judged on the TV.

### What was built

Precedence base, then Visual Overhaul, then ours.

| binder | entries | TI base changed vs archive | VO injected | ours injected | total patched | BHD | BDT base -> merged |
|---|---|---|---|---|---|---|---|
| m32_0000 | 245 | 48 | 27 | 20 | 47 | 24,992 unchanged | 393,028,092 -> 519,324,041 |
| m32_0001 | 499 | 83 | 82 | 0 | 82 | 56,024 unchanged | 1,458,881,602 -> 1,459,084,737 |
| m32_0002 | 452 | 74 | 72 | 0 | 72 | 50,024 unchanged | 1,079,616,048 -> 1,079,683,905 |
| m32_0003 | 600 | 115 | 90 | 3 | 93 | 61,752 unchanged | 1,507,354,675 -> 1,552,016,865 |

4.6 GB of merged binders at
`data/ds3-ui-port/build/texup/mod-map-merged/map/m32/`. The VO counts
(27/82/72/90) and the TI counts (48/83/74/115) reproduce this doc's earlier
survey exactly, which is the cross-check that the diff is finding the right
thing. TI and VO overlap on ZERO entries in all four binders, and VO and ours
overlap on zero: TI does albedo, VO does `_r` reflectance, we do the cloud sea.

Dead space (a replaced entry's old payload is left where it was): 8.9 MB, 1.4 MB,
1.2 MB and 10.4 MB. That is the price of never moving a byte, and it is worth it.

### Proof

`tools/ds3-texup check` on all four merged binders: hash tables consistent and
resolving 245/245, 499/499, 452/452, 600/600, entry data 16-byte aligned
245/245, 499/499, 452/452, 600/600, zero entries running past the end of the
BDT, VERDICT structurally sound on all four.

`pack`'s own `_verify`, per binder: header identical, name block identical and
in place, hash table bytes identical and at the same offset, untouched records
byte-identical (198/198, 417/417, 380/380, 507/507), every changed BHD byte
range inside a replaced entry's own record, and the BDT's first `base_bdt_len`
bytes identical to the base by streamed sha256 (the comparison is a hash, not
`==`, because two copies of a 1.46 GB buffer is how a verification step becomes
the reason a build cannot run). All growth appended.

Independent byte proof (`merge/prove.py` in the session scratchpad), reading the
finished files and the three sources side by side. A sample per source per
binder, then EVERY entry:

| binder | ours | VO | TI/base | mismatches |
|---|---|---|---|---|
| m32_0000 | 20 | 27 | 198 | 0 |
| m32_0001 | 0 | 82 | 417 | 0 |
| m32_0002 | 0 | 72 | 380 | 0 |
| m32_0003 | 3 | 90 | 507 | 0 |

All 1,796 entries accounted for, zero mismatches: every VO entry equals VO's
bytes, every untouched entry equals TI's bytes, and each of ours decodes to a
DDS byte-identical to `build/texup/dds/<name>.dds`. Ours is proved on the DDS
INSIDE the payload rather than on the whole entry, because the merge swaps our
texture into the BASE pack's TPF wrapper: for the eleven kumo tiles TI had also
rebuilt, the entry bytes legitimately differ from our own `mod-map` build while
the texture is bit-identical.

### What the merged binder actually hands the engine

The point of the merge, in three textures read straight out of the finished
files and compared with the game's own:

| entry | vanilla | merged | from |
|---|---|---|---|
| `m32_00_o324030_stone_tablet_03_a` | 1024x1024 BC1 sRGB (dxgi 72), 699,212 B | **4096x4096 BC7 sRGB (dxgi 99), 22,369,796 B** | Texture Improvement |
| `m32_00_Mountain_a` | 1024x1024 BC1 sRGB, 699,212 B | **4096x4096 BC7 sRGB, 22,369,796 B** | Texture Improvement |
| `m32_00_kumo_20_a` | 1024x1024 BC1 sRGB, 699,212 B | **4096x4096 BC7 sRGB, 22,369,796 B** | ours |
| `m32_00_o324030_stone_tablet_03_r` | 256x256 BC1, mean 56.8, **sd 5.45** | 256x256 BC1, mean 55.5, **sd 1.37** | Visual Overhaul |

Visual Overhaul does not change reflectance RESOLUTION, it flattens the CONTENT:
every `_r` map it ships comes out near-uniform at about 55/255, which is why its
payloads DFLT-compress from 6-28 KB down to 250-490 bytes and why they were easy
to mistake for stubs. The temple stone therefore answers light uniformly instead
of with vanilla's per-texel variation. That is the whole-scene effect the mod is
named for, and before this merge it was not reaching Archdragon Peak at all.

### Verified in the game (3 Sep 21:43, Donnie's save at Archdragon Peak)

Deployed the four merged binders into `data/ds3-shot/game/mod/map/m32/` under
the agent lock (the previous two binders backed up first and restored by an EXIT
trap), then `DS3SHOT_FAST=1 DS3SHOT_MOD=1 DS3SHOT_W=3840 DS3SHOT_H=2160
tools/ds3-shot inventory`. Exit 0 in **101 s** against 86 s for the two-binder
run: the extra fifteen seconds is the engine reading 4.6 GB of binders instead
of 0.4 GB. Shot: `merged_run1.png` in the session scratchpad, against
`archdragon_layered.png` (same spot, ours-only m32).

**The scene renders correctly.** Same masonry, same geometry, textures on the
surfaces they belong to. None of the first build's signatures are present: no
wrong textures on the arch, pillars or floor, no white geometry chunks, no fog
as solid white slabs. 39.8 percent of the frame differs by more than 8/255 and
the whole-frame mean drops 47.9 to 43.2, consistent with VO's flatter, less
reflective stone.

Detail (standard deviation of the image minus an 8 px box blur, i.e. the
high-frequency content), on static masonry that is aligned to within a pixel
between the two frames:

| region | deployed | merged |
|---|---|---|
| arch frieze, upper left | 0.949 | **2.064** (+118%) |
| corbel and pillar, left | 1.275 | 1.410 (+11%) |
| upper right masonry | 0.632 | 0.653 (+3%) |

HONEST CAVEAT: the fog is animated and the two frames caught it at different
phases, so part of that gain is thinner haze in front of the wall rather than
sharper stone, and the region means are not attributable to the merge alone.
What is not ambiguous is the offline half: the temple's stone albedo now arrives
at 4096x4096 BC7 where vanilla ships 1024x1024 BC1, every untouched entry is
byte-identical to Texture Improvement's, and the game booted and rendered on it.
A dead-on before/after of the stone alone would need the fog override lifted for
one pair of shots.

### Copy commands (nothing is deployed)

    mkdir -p ~/couch/data/ds3-shot/game/mod/map/m32
    cp ~/couch/data/ds3-ui-port/build/texup/mod-map-merged/map/m32/m32_000{0,1,2,3}.tpfbhd \
       ~/couch/data/ds3-shot/game/mod/map/m32/
    cp ~/couch/data/ds3-ui-port/build/texup/mod-map-merged/map/m32/m32_000{0,1,2,3}.tpfbdt \
       ~/couch/data/ds3-shot/game/mod/map/m32/

Note that this ADDS m32_0001 and m32_0002, which our mod dir did not carry
before, and that `mod-vo` and `mod-ti` stay in the ModEngine2 list: they are
still first-match for every other map, for the gparams, MSBs, lights and the
character binders. Only m32 needed merging, because m32 is the only place all
three of us collide. 4.6 GB, so check free space before copying.
20:50: the merged m32 binders (see "Merged m32") replaced the two-binder
set in the mod dir; mod/map/m32 now carries all four. Mod dir 4.5 GB.

## Wishlist items 1 and 2 (3 Sep, 21:10)

FPS unlock: two memory writes (community-known, DS3DebugFPS / ds3fps):
`[DarkSoulsIII.exe+0x489DD10]` is the SprjFlipper object, `+0x354` its
float frame cap, `+0x358` a byte that enables the debug cap path. Done in
`tools/ds3-menu-watch` because it is already the game's ancestor (yama
ptrace scope 1), no sysctl. `DS3_FPS` (launcher default 120, 0 = off).
Jump from Neutral: a plain-text c0000.hks (DS3 compiles Lua at load),
layered as `mod-jump`. Verified in the sandbox: see todo.md.
