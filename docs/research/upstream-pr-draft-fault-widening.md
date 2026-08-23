# DRAFT ONLY. NOT TO BE FILED.

**Hold until the fair bare A/B play session (fix build, no gamescope wrap,
against the 22 Aug bare-stock baseline) returns an adoption verdict.** The
headless A/B below stands on its own, but the 22 Aug live evening never gave
this build a fair hearing (three unrelated console-side failures, then a
bare-stock session that was the best on record for other reasons), so the
adoption case has to be re-made before anything goes upstream. The probes
described at the end must be stripped from the branch first. Nothing here
has been sent to anyone. Do not post, do not push.

Target: `shadps4-emu/shadPS4` pull request description. Pairs with
`upstream-issue-draft-fault-storm.md`, which carries the measurements and
should be filed first so this can reference it.

---

## Title

video_core: widen guest write-fault invalidation to an aligned 64KB window

## What this changes

One function: `GuestFaultSignalHandler` in `src/video_core/page_manager.cpp`
(the signal-handler tracking path, line 210 at the 0.17.0 tag).

Before, a guest write fault invalidates 8 bytes:

```cpp
if (Common::IsWriteError(context)) {
    return rasterizer->InvalidateMemory(addr, 8);
}
```

After, it invalidates the aligned 64KB window containing the faulting
address, falling back to the original 8-byte invalidation if the widened
range is rejected:

```cpp
if (Common::IsWriteError(context)) {
    constexpr u64 WIDE_WINDOW = 64_KB;
    const VAddr wide = Common::AlignDown(addr, WIDE_WINDOW);
    if (rasterizer->InvalidateMemory(wide, WIDE_WINDOW)) {
        return true;
    }
    return rasterizer->InvalidateMemory(addr, 8);
}
```

Plus one include (`common/alignment.h`). The read-fault branch is untouched.
Nothing else in the tree changes.

## Why

An 8-byte invalidation means a bulk guest write pays one fault and one
per-page re-protect, with its cross-core TLB shootdown, for every 4KB page
it touches. Measured on Bloodborne (CUSA00900, 01.09), gameplay sustains
roughly 48,000 faults per second and about 850ms of handler time per wall
second, which is about 0.85 of a CPU core, permanently, for the whole of
gameplay. Bloodborne's roughly 20.5 second autosave cycle then lands a burst
on top of that saturated economy, and the burst is what the player feels as
a stall. Details and method are in the companion issue.

## Why it is correct

The widened invalidation is a strict superset of the precise one. It can
only ever cause an extra re-upload of guest memory the GPU may have cached,
never skip a required one, so no stale-data case is introduced.

The fallback exists because `Rasterizer::InvalidateMemory` gates on
`IsMapped(addr, size)`, which requires the *whole* range to be mapped
(`vk_rasterizer.cpp:1068`). A 64KB window straddling a mapping boundary
would therefore be rejected wholesale and the fault would go unhandled, so
in that case we do exactly what upstream does today. Behaviour for those
addresses is identical to current main.

Widened fault granularity is standard practice in this class of emulator.
Dolphin, RPCS3 and yuzu all invalidate at a coarser granularity than the
faulting access. 64KB is our own choice, calibrated only in the sense that
it was the first value tried and it worked. We have not swept it. See open
questions.

## A/B results

Rig: isolated user directory, headless gamescope (1920x1080, headless
backend, `-r 60`), synthetic controller driving a fixed route from the same
save, MangoHud per-frame CSV, `readbacksMode = 0`. Both arms are the same
0.17.0 tree with the same diagnostic probes compiled in, differing only in
the widening. Fault figures are differences between consecutive
once-per-second census log lines, taken from the in-game portion of each
run.

| metric (in-game)                  | baseline 0.17.0 | 64KB widening |
|---|---|---|
| faults per second                 | ~48,000         | ~1,400        |
| fault handler ms per wall second  | ~850            | ~40           |
| worst frame in an autosave cycle  | 53 to 62ms      | 16.8 to 19.5ms |
| frame median                      | 16.7ms          | 16.7ms        |

For honesty about spread rather than headline figures: baseline per-second
census deltas sat at roughly 46,000 median and 52,000 at p90, peaking at
54,500. The fixed build's deltas were around 150 per second while quiet,
with in-game bursts to about 5,000 to 6,700 per second. The order of
magnitude is the claim, not the third digit.

The 1.3MB save write itself was never the problem in either arm: 254 to 457
microseconds of wall time, single-digit faults during the call.

## Known risks

- **Over-invalidation costs upload bandwidth.** Invalidating 64KB where 8
  bytes were written can force re-upload of buffer or texture data the GPU
  already had. In a texture-heavy scene this could plausibly show up as a
  frame-time cost or, if something else in the pipeline is fragile, as
  visual artefacts. We saw neither headlessly, and no visual difference was
  observed in the frames we did look at, but headless runs at 1080p are a
  weak test for exactly this risk. It has not been ruled out.
- **Only one title tested.** Bloodborne only. The mechanism is title
  agnostic but the trade-off may not be.
- **Only one platform tested.** Linux, RADV on RDNA4, signal-handler
  tracking path. Not tested on Windows, not tested on macOS, and the
  `ENABLE_USERFAULTFD` path is not touched by this change at all even
  though it has the same 1-byte shape at `page_manager.cpp:177`.
- **The texture cache mutex coupling is not addressed.** `PrepareFrame`
  takes the global texture cache mutex on every flip and the fault path
  takes it too. This change reduces how often the fault path takes it, but
  does not remove the coupling. Our probe never saw `PrepareFrame` exceed
  2ms headlessly, so we have no evidence it matters, and no evidence it does
  not.
- **Long-session behaviour unproven.** The autosave stall grew with session
  length in the original reports. We suspect a separate term (the source
  dive pointed at `buffer_cache.cpp` `ResolveOverlaps`) which this change
  does nothing about. Our A/B runs were minutes, not hours.

## Open questions for maintainers

1. Is 64KB the right window? We have not swept 16KB, 32KB or 128KB, and a
   sweep on hardware other than ours would be more informative than one on
   ours.
2. Should the window be tied to something structural instead of a constant,
   for example the buffer or image granularity the caches already work in,
   so that the invalidation lines up with what actually gets re-uploaded?
3. Would you prefer the fallback expressed differently, for example by
   clamping the window to the mapped range rather than dropping straight to
   8 bytes? We took the conservative route so that boundary-crossing
   addresses behave exactly as they do today, but clamping would keep more
   of the benefit near mapping edges.
4. Should the `ENABLE_USERFAULTFD` path get the same treatment in this PR,
   or separately? We have not built or tested it and would rather not change
   code we cannot exercise.
5. Is there a title or scene you would want this tested against before it
   lands, particularly a texture-churn-heavy one where over-invalidation
   would show worst?

## Not included in this PR

The measurement work that produced the numbers is deliberately excluded:
atomic fault counters in the signal handler, a per-second census log line in
`Presenter::PrepareFrame`, and a wall-plus-fault-delta probe around
`file->Write` in the kernel write path. They were useful for the
investigation and are not something upstream should carry. If any of it
would be welcome as an optional debug counter, say so and it can be
submitted separately in a form that compiles out by default.
