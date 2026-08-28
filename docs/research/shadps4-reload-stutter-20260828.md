# The death-reload stutter, and the texture-cache collector that stops collecting

28 Aug 2026. Donnie, mid-Bloodborne: "it's definitely when i look at the sky...
but before it was fine, i died and now it's choppy everywhere". Two of my
explanations (vista complexity, then sky overdraw) were knocked down by his own
observations before we measured the right thing.

## The measurement that cracked it

Same save, same area, same activity (standing, looking at the sky):

| arm | img_faults/s | write faults/s | handler | **us per fault** |
|---|---|---|---|---|
| before the death | 2.6 | 5,265 | 14.5% | 27.5 |
| after death+reload (choppy) | **26.7** | 8,612 | 23.6% | 27.4 |
| after emulator restart | 2.2 | 5,470 | 13.6% | 24.9 |

So the elevated rate is **process-local state**: triggered by the game reloading
after a player death, persists across areas and further loads, and is destroyed
with the process. Not the save, not the area, not the mod files. **A restart is
the workaround** and it is reliable.

**Per-fault cost is FLAT across the regression** (27.5 -> 27.4 us). The handler
did not get slower; there are simply more faults. So the stutter is NOT in the
fault handler - it is in the *consequences*: ~24 extra whole-image
detile+re-upload cycles per second on the render thread, plus 3,347 extra
faults/s of raw mprotect/TLB traffic.

## Counter caveat (do not misread this number again)

`g_pm_fault_img` is gated on `MayHaveImageAt`, an occupancy mirror keyed at
**1MB buckets**. An "image fault" is *a fault that landed anywhere in a 1MB
region containing at least one registered image* - NOT a fault that touched an
image, and NOT a re-upload. A 10x rise is equally consistent with **more images
registered in buckets the ordinary buffer storm already writes through**, i.e.
re-labelling. Distinguishing the two matters because **they have opposite
fixes**. Measure before changing anything.

## H1 - the leading hypothesis, and it is three code-certain facts composed

1. **`ImageFlagBits::GpuModified` is set in six places and cleared NOWHERE.**
   `grep -rn "GpuModified" src/` shows no `flags &= ~...GpuModified` in the tree.
   Once an image has been rendered into, it is GpuModified for the life of the
   process.
2. **A tiled + GpuModified + clean image can never be freed, at any pressure**
   (`texture_cache.cpp:984-989`): the `tiled && download` skip is unconditional,
   not gated on memory pressure, with the comment "we can't handle non-linear
   image downloads". Every PS4 render target and virtually every game texture is
   tiled.
3. **The deletion budget is charged for images the GC refuses to delete**
   (`texture_cache.cpp:978-982`): `--num_deletions` runs BEFORE the two skips.
   Budget is 10 per submit. The LRU is walked oldest-first and only reordered by
   use.

Compose them: once >=10 immortal images sit at the head of the LRU, the
collector spends its entire per-submit budget visiting and refusing them,
deletes nothing, and does so on every submit forever. **The texture cache stops
collecting anything, permanently.** A map teardown after a death retires a whole
level's worth of rendered-into textures; those that the new level does not
overwrite stay registered and pin their 1MB buckets forever.

Pressure on this box: 6.55GB of 15.92GB used; trigger_gc ~4GB, pressure_gc
~11.2GB. So the GC **is** running but permanently in the non-pressured mode
where the skips apply. **Plausibly a bug you only get because the card is big** -
a smaller card would hit pressure and collect.

## H2 - the buffer cache has no eviction at all (code-certain, upstream)

`BufferCache::RunGarbageCollector` (`buffer_cache.cpp:850-872`) defines a
`clean_up` lambda **and never invokes it**. No `ForEachItemBelow`. Verified
present in the 0.17.0 tag, so upstream, not ours. Meanwhile buffer extents only
grow (`ResolveOverlaps` unions overlapping buffers and expands past
STREAM_LEAP_THRESHOLD). Wider registered buffers = more pages armed = more write
faults for the same guest activity. Explains the +64% total-fault term with flat
per-fault cost. **Inert on this box until VRAM > ~11.2GB**, so probably not the
cause here - measure before touching.

## Refuted (do not re-walk)

- **Page-watcher refcounts leaking**: a stale tracked image does pin pages, but
  the pin is released on the first guest write there and the image is never
  re-tracked (only a bind re-tracks). Self-limiting, cannot sustain a rate.
  The Head/Tail untrack branches are airtight.
- **Our own `image_page_refs` mirror leaking**: the failure paths log
  LOG_CRITICAL in all build types; the live log has 13 Criticals, all
  `signals.cpp`, none from texture_cache. Never fired.
- **gpu-bits starving ClaimFaultRun**: `pages_per_claim` shows no trend over 51
  minutes (9.7-13.4). Dead.
- **Our ClaimFaultRun touching images**: the texture path is byte-exact and
  ClaimFaultRun only flips cpu bits inside one 4MB region. The v2 separation
  holds.
- **`img_faults` rising monotonically in general**: FALSE. Across 20 sessions it
  swings 1.2/s to 2,663/s and returns to the floor. Only the controlled
  same-scene A/B is trustworthy.

## Upstream state (researched 28 Aug)

- **Issue #2042 is NOT a diagnosis.** Closed 2025-02-01 as stale: two comments, a
  maintainer asked for a log, the reporter never replied. The PR #1973
  attribution is the reporter's own unverified bisect. **PR #1973 touches no
  texture-cache code at all.** Do not cite either in a writeup.
- Nearest live issue: **#4215** (progressive FPS degradation tied to map asset
  loading) - but explicitly conditional on readbacks, which we have OFF.
- **We are two releases behind**: 0.18.0 shipped 2026-08-18. Its relevant fix
  (#4839, `e5fcae6a5`) widens fault servicing to a 512KB window on the **read**
  path only. Our problem is the **write** path, unfixed in current upstream and
  nobody is working on it.
- Upstream's own direction (per-page locking #3798, readback rework #3404) has
  been stalled 9-12 months.
- **The death-reload trigger appears to be an original finding.** Nothing in
  their tracker connects this to dying, the sky, or clouds.

## What actually shipped (28 Aug 07:24)

Built and committed on branch `tc-gc-probe` as `1fdc058`, in
`~/src/shadps4-dbg`. Probes A + B and Fix 1 landed together; C, D and E were
not built (only needed if A/B fails to settle H1).

- Census line now carries `tc_num_registered`, `tc_occupied_buckets`,
  `tc_gc_visits`, `tc_gc_skips`, `tc_gc_frees`, `tc_immortal`. Computed on the
  render thread once per 60 flips. **Nothing added to the fault path.**
- Fix 1 is behind `SHADPS4_TC_GC_FIX`, **default ON**, with a 256-image visit
  cap so charging on frees alone cannot turn one pass into a full-LRU scan.
- `ForEachItemBelowStoppable` added because the existing early-out has never
  worked (see the upstream trait bug, now documented in `lru_cache.h`).

Levers, both in `~/.local/bin/shadps4`:
- `touch ~/couch/data/shadps4-gc-fix-off` -> upstream control arm.
- `rm ~/couch/data/shadps4-local-build` -> back to the stock AppImage entirely.
Rollback binaries: `data/shadps4-binary-backups-v2-e4b6c51` (pre-fix) and
`-1fdc058` (this build).

**The read, next session:** play, die, keep playing. Then compare against the
A/B table above.
- **H1 proven** if the control arm shows `tc_gc_frees` ~0 while `tc_gc_visits`
  climbs ~10/submit and `tc_immortal` >= 10.
- **Fix works** if post-death `img_faults/s` stays near the 2-3/s floor instead
  of stepping to ~27/s, and the choppiness does not arrive.
- **Fix is irrelevant** if `tc_immortal` is small or `tc_gc_frees` was never ~0.
  Then H1 is wrong and probe C (top-N offenders by fault_hits) is the next move,
  because that is the one that separates real invalidation from re-labelling.

Not yet play-tested. First suspect if anything visual or performance-related
changes for the worse.

## The plan

**Probes only first, no behaviour change.** Nothing new in the signal handler;
counters on non-hot paths plus one LRU walk per second, folded into the existing
census line at `vk_presenter.cpp:722-736`.

- A: registered-image census (`tc_num_registered`, `tc_registered_bytes`,
  `tc_occupied_buckets`, `tc_gc_visits/skips/frees`) - decides H1.
- B: the immortal set (count GpuModified && !Dirty && IsTiled in the LRU).
  **If `tc_gc_frees` ~0 while `tc_gc_visits` ~10/submit and immortal >= 10,
  H1 is proven outright.**
- C: top-N offenders by `fault_hits` per image, logged with size/format/tiling -
  names the actual image and distinguishes real invalidation from re-labelling.
- D: Map/UnmapMemory trace - decides whether Bloodborne ever unmaps on teardown
  (if it never does, H1's immortal set is unbounded).
- E: buffer growth counters - decides H2.

**Fix 1 (recommended, can land with the probes): move `--num_deletions` to after
the skips** (`texture_cache.cpp:982` -> after `:992`), so the budget is only
charged for actual frees. One line. The set of deletable images is bit-for-bit
unchanged, no invalidation range changes, **zero v1 risk**. Add a visit cap
(~256) so the walk stays bounded.

**Fix 2 (age out GpuModified) MUST NOT ship without the paired luminance gate.**
Freeing a tiled GpuModified image discards GPU-only content; a later rebind
re-uploads from guest memory = zeros read as black, stale bytes read as
multicoloured. **That is exactly the v1 failure mode** (see
fault-batching-redesign-20260823.md).

**Rule that falls out of this analysis, worth keeping:** freeing a GpuModified
image is semantically a widened claim by another route. The v1 rule was "widen
the protection work, never the claim"; this is the same rule wearing a hat.

**Do not touch invalidation width.** The byte-exact texture path
(`vk_rasterizer.cpp:1106`) is correct and is the only thing standing between us
and v1.
