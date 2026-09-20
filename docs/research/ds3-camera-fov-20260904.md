# DS3 camera FOV, the Bloodborne-style lift (4 Sep 2026)

Ported the same move that worked on Bloodborne: pull the camera back. On BB a
FOV lift of +15 was the keeper ("the fov change is so good i could actually
see"). This does the equivalent for Dark Souls 3.

## The field

`LockCamParam` (paramdef `LOCK_CAM_PARAM_ST`), row size 100 bytes:

    0x00 (0)   CamDistTarget            f32   (camera distance from the player)
    0x14 (20)  FovYChange               f32   (vertical field of view delta)

141 rows total. 110 of them hold the vanilla default `FovYChange = 43.0`
(row 0, the global default, among them); the other 31 are map- or
situation-specific overrides (boss arenas, tight corridors, swimming, etc.)
and are left alone by design. 25 rows hold the default `CamDistTarget = 4.0`.
Elden Ring's own `camFovY` default is 48.0 (132 of 166 rows), i.e. +5 over
DS3's 43.0.

Field offsets were derived, not guessed: loaded `LOCK_CAM_PARAM_ST` from
ModEngine2's own paramdef bundle
(`data/ds3-shot/game/modengine2/assets/debug_menu/paramdef/paramdef.paramdefbnd.dcx`)
via soulstruct, summed each field's byte size in declaration order, and
`FovYChange` landed at cumulative offset 0x14 with the whole row at 100 bytes
-- both numbers matching the file's own row pitch exactly.

## The tool

`tools/ds3-param` reads and writes these fields directly in the encrypted
regulation (`Game/Data0.bdt`), which ModEngine2's `mod/Data0.bdt` shadows.
Full mechanism, AES key source and byte-offset derivation are in the tool's
own header comment.

    tools/ds3-param show <Data0.bdt>
    tools/ds3-param build <in.bdt> <out.bdt> --fov <deg> [--camdist <units>] [--rows all|0]
    tools/ds3-param check <bdt> [--against <baseline.bdt>]

`build` only touches rows that currently hold the row-0 default for the field
being changed, so any row that already differs (a boss arena's own camera
tuning) is left exactly as it was. It verifies its own output by decrypting
it back and re-reading every row it touched, then diffs every OTHER param
table byte-for-byte against the input to prove nothing else moved. `check`
re-runs that second half against any two regulations, so a deployed file can
be re-verified any time without rebuilding it.

AES key: `ds3#jn/8_7(rsY9pg55GFN7VFL#+3n/)`, 32 ASCII bytes, from
`data/ds3-ui-port/SFUtil.cs` line 469. AES-256-CBC, PKCS7 padding, a 16-byte
random IV prefixed to the ciphertext -- confirmed against SFUtil's own
`EncryptByteArray`/`DecryptByteArray`. DCX unwrap/rewrap reuses
`tools/souls-extract/oodle.py`'s `dcx_decompress`/`dcx_compress_dflt`
(DS3 uses DCX_DFLT/zlib, no Oodle). The regulation's BND4 has `hash_table_type
0` and no per-entry compression, so a param edit never needs to grow, move,
or resize anything -- LockCamParam's absolute byte offset inside the 13.4 MB
BND4 is found via `bytes.find()` on its (unique, 17,570-byte) entry data,
and floats are overwritten in place with `struct.pack_into`.

## Byte-level verification (all 4 built variants, DONE)

Every variant below was built with `tools/ds3-param build` and passed both
its own internal verify (re-decrypt the output, re-read every touched row)
and a `tools/ds3-param check` against the real, read-only game install:

| variant | FovYChange | CamDistTarget | rows touched (Fov / CamDist) | check |
|---|---|---|---|---|
| ER's own value | 48 | 4.0 | 110 / 25 | PASS, 102 other tables byte-identical |
| +10 over vanilla | 53 | 4.0 | 110 / 25 | PASS, 102 other tables byte-identical |
| **BB's +15 lift (deployed)** | **58** | **4.0** | **110 / 0** | **PASS, 102 other tables byte-identical** |
| +10 FOV, pulled back further | 53 | 4.8 | 110 / 25 | PASS, 102 other tables byte-identical |

(vanilla DS3 is FovYChange 43, CamDistTarget 4.0, for reference. The deployed
build did not touch CamDistTarget at all -- 4.0 is already the vanilla
default on those rows, so there was nothing to change.)

This proves the regulation edit is correct at the file level: the intended
rows changed to the intended values, nothing else in the 13.4 MB regulation
moved by a single byte, and the AES/DCX round trip is exact.

## In-game capture: BLOCKED by a pre-existing ModEngine2 launcher fault

Not caused by this work. Isolated 4 Sep 2026, ~02:30-05:45, across 10 sandbox
boot attempts:

* Every `DS3SHOT_MOD=1` boot (ModEngine2 launcher path, needed to load
  `mod/Data0.bdt`) failed identically: gamescope and Xwayland come up fine,
  `proton run modengine2_launcher.exe ...` returns in under ~2 seconds
  without ever spawning a wine/DarkSoulsIII.exe process (confirmed with full,
  unfiltered `ps` snapshots every 15s across three separate 180s boot
  windows -- no wine, python3, steam.exe, or DarkSoulsIII process ever
  appears anywhere on the system), and the harness times out after 180s
  waiting for a first frame that was never going to come. `ds3-shot`'s own
  liveness check only watches the gamescope session, not the actual game
  process, so it cannot tell the difference between "still loading" and "the
  launcher already gave up."
* Ruled out, in order: the modified regulation itself (fails identically with
  `mod/Data0.bdt` removed entirely); the shared `agent.lock`/lock contention
  (failed even when acquired immediately); insufficient patience (extended
  the wait to 480 ticks / ~15 minutes wall time in a scratch copy of the
  tool, still nothing); a leftover process or stale `data/ds3-shot/lock`
  (nothing left running between any two attempts, confirmed by `ps`); the
  specific mod list (fails identically with a minimal one-entry
  `mods = [{path = "mod"}]` config, so `mod-jump`/`mod-vo`/`mod-ti` are not
  it either).
* Decisive control test: the exact same harness, exact same sandbox save and
  prefix, launched WITHOUT ModEngine2 (`DS3SHOT_VANILLA=1`, plain
  `DarkSoulsIII.exe`) worked perfectly on the first try -- first frame at
  ~6s, full menu-to-gameplay journey, clean quit, a real `ingame.png` saved.
  So Proton, wine, the GPU, gamescope and the sandbox prefix are all fine
  right now; the fault is specifically in `modengine2_launcher.exe`'s own
  injection path, independent of what config or mod content it is given.
* ModEngine2 itself is not permanently broken: its log
  (`data/ds3-shot/game/modengine2/logs/modengine_2026-09-04.log`) shows a
  clean init ("Applied 3 hooks", "Starting worker thread") for a DIFFERENT
  agent's boot at 04:41:51, i.e. mid-way through this session's failure
  streak. So this looks like transient/racy harness state rather than a
  broken binary -- plausibly shared with whatever the concurrent
  ReShade/showcase work on this box is also fighting, since that work drives
  the identical `modengine2_launcher.exe` injection path.
* Everything used for this diagnosis is disposable: scratch copies of
  `tools/ds3-shot` (480s cap) and a minimal ME2 config, both under this
  session's scratchpad, never touched the shared tool or the real install.

**What this means for the deploy below**: the regulation file is proven
correct independent of rendering it (AES/DCX round trip + byte-diff against
vanilla). Deploying it is a plain file copy to the path ModEngine2 already
reads; it does not require a working boot. The framing screenshots and
character-height measurement table are the one deliverable this session
could not produce, and shouldn't be asserted from memory or invented --
whoever next gets a working `DS3SHOT_MOD=1` boot (or fixes the launcher
fault) can run the four `Data0.*.bdt` variants that are already built and
verified (see below) straight through `tools/ds3-shot inventory` and
`tools/ds3-reshade-compare` with no further param work needed.

## The dial

To change the deployed FOV/camera-distance later:

    tools/ds3-param build \
      "$HOME/.steam/steam/steamapps/common/DARK SOULS III/Game/Data0.bdt" \
      ~/couch/data/ds3-shot/game/mod/Data0.bdt \
      --fov 58 --camdist 4.0

Swap `--fov` (and optionally `--camdist`) for whatever's wanted. The command
always sources from the real, read-only game install, so it is a full,
reproducible rebuild each time, not a patch-on-patch.

## Deployed

`data/ds3-shot/game/mod/Data0.bdt` = FOV 58, CamDist 4.0 (Bloodborne's +15
lift), built and deployed 4 Sep 2026, re-verified in place with
`tools/ds3-param check` after copying (PASS: 102/102 other tables
byte-identical to vanilla, 110 LockCamParam rows changed 43.0 -> 58.0,
nothing else). This is the same path ModEngine2 loads for the real launch
(`data/ds3-mod/mod -> ../ds3-shot/game/mod` symlink), so it is live for both
the sandbox and the real game the next time DS3 is launched through
ModEngine2 -- once the launcher fault above is resolved. No previous
`mod/Data0.bdt` existed before this work (checked: neither `mod`,
`mod-jump`, `mod-vo`, nor `mod-ti` shipped a regulation), so there is nothing
to collide with and no backup was needed.
