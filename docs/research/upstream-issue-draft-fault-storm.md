# DRAFT ONLY. NOT TO BE FILED.

**Hold until the fair bare A/B play session (fix build, no gamescope wrap,
against the 22 Aug bare-stock baseline) returns an adoption verdict.** The
22 Aug evening play test was derailed by three console-side failures that
had nothing to do with this finding, and the new bare-stock baseline is much
faster than the old one, so the adoption case has to be re-made before
anything is posted upstream. Nothing here has been sent to anyone. Do not
post, do not open a browser tab, do not push.

Target: `shadps4-emu/shadPS4` issue tracker. Audience: maintainers.
Companion drafts: `upstream-pr-draft-fault-widening.md` (the proposed fix),
`upstream-issue-draft-write-path-gap.md` (a separate, unrelated report).

---

## Title

Guest write-fault handler invalidates 8 bytes per fault, producing a
sustained ~48,000 faults/s (about 0.85 of a CPU core) during Bloodborne
gameplay

## Summary

On the signal-handler memory tracking path, every guest write to a tracked
page takes a fault and the handler invalidates only 8 bytes
(`page_manager.cpp`, `GuestFaultSignalHandler`). Each such fault also costs
a re-protect of the containing page, so any bulk guest write pays one fault
plus one `mprotect` per 4KB page touched, with the cross-core TLB shootdown
that comes with it.

Measured on Bloodborne (CUSA00900, app version 01.09), this is not an
occasional cost. It is a permanent background load for the whole of
gameplay: roughly 46,000 to 54,000 faults per second, consuming about 800 to
910 ms of handler time per wall second, which is about 0.85 of a CPU core
burned continuously. Title and menu screens are quiet. The storm starts when
the world loads and does not stop.

The visible symptom we started from is Bloodborne's autosave: a frame stall
on a roughly 20.5 second cycle. That turned out to be a burst riding on top
of an already saturated fault economy, not a cost of the file write itself.
The host write of the 1.3MB save file measures 254 to 457 microseconds and
takes single-digit faults. The file I/O is innocent.

We think the fault census is a general finding rather than a Bloodborne one,
since nothing about the mechanism is title specific, but we have only
measured one title, so please read the numbers as one data point.

## Environment

- shadPS4 0.17.0 (release tag, built locally from the same tree, plus
  measurement probes described below)
- Linux, kernel 7.0, Ubuntu userspace
- Ryzen 7 5700X3D, Radeon RX 9070 XT, RADV (Mesa 25.2)
- Bloodborne CUSA00900, app version 01.09, firmware 0x4500000
- `readbacksMode = 0`, `readbackLinearImages = false`, vblank frequency 60
- Signal-handler tracking path (the default). `ENABLE_USERFAULTFD` was not
  built in.
- Measurement sessions ran headless under gamescope (1920x1080, headless
  backend, `-r 60`) with a synthetic controller driving the game, so that
  runs were repeatable. MangoHud wrote a per-frame CSV.

## How it was measured

Three probes were added to a local build. They are diagnostics only and are
not part of the proposed fix.

1. **Fault census.** Three relaxed atomics incremented inside
   `GuestFaultSignalHandler`: fault count, total handler nanoseconds
   (`clock_gettime(CLOCK_MONOTONIC)` around the body), and a hit count for
   faults where the rasterizer claimed the address. Atomics only, so the
   handler stays async-signal-safe.
2. **Census log line.** Every 60th `Presenter::PrepareFrame` (so roughly
   once per second at 60Hz) logs the running totals, giving the census a
   time axis that lines up with the frame log and the save events.
3. **Write probe.** Wall time and fault-counter deltas around
   `file->Write(...)` in the kernel `write` path, logged for writes of 64KB
   or more or writes taking over 2ms. This is what separated host I/O cost
   from tracker cost.

Per-second figures below are differences between consecutive census lines.
"In-game" means the portion of the run after the world had loaded, which is
where the storm lives.

A maintainer does not need our probes to see the shape of this. Two
no-patch cross-checks that should show the same thing, though we have not
run them ourselves and cannot vouch for the exact counts:

- `perf stat -e page-faults -p $(pidof shadps4) -- sleep 10` during
  gameplay, compared with the same during a title screen.
- `strace -f -c -e trace=mprotect -p $(pidof shadps4)` for a few seconds of
  gameplay, which should show a very large `mprotect` call count.

## Numbers

Same rig, same save, same route, instrumented 0.17.0 build.

| metric (in-game, per wall second) | value                        |
|---|---|
| guest faults                      | ~46,000 median, 52,000 at p90, 54,500 peak |
| fault handler time                | ~800ms median, 910ms at p90  |
| effective CPU cost                | ~0.85 core, continuously     |
| faults during the 1.3MB save write | 0 to 6                      |
| wall time of the 1.3MB save write | 254 to 457 microseconds      |
| frame median                      | 16.7ms                       |
| worst frame in an autosave cycle  | 53 to 62ms                   |

The two right-hand rows are the reason we looked at this at all. The stall
is real and repeatable on the autosave cycle, but the write call is a
rounding error inside it. What is expensive is the fault traffic the guest
generates while it serialises the save, on top of the traffic gameplay is
already generating.

One thing we could not reproduce headlessly:
`Presenter::PrepareFrame` takes the global texture cache mutex on every
flip, and `TextureCache::InvalidateMemory` takes the same mutex on every
fault, which looks like a coupling between the fault storm and the flip
path. Our probe never saw `PrepareFrame` exceed 2ms in these headless runs,
so we cannot claim that coupling matters. It may still matter under real
display load. We are flagging it as unproven, not as a finding.

## Reproduction

1. Build 0.17.0 (or current main) on Linux, default tracking path.
2. Run Bloodborne with `readbacksMode = 0`. Any title should do for the
   census, but the numbers above are from this one.
3. At a title screen, sample fault volume (probe, `perf stat -e page-faults`,
   or `strace -c -e trace=mprotect`). It should be quiet.
4. Load a save and stand in the world, then sample again over ten seconds.
   We see tens of thousands of faults per second and roughly 0.8 seconds of
   handler time per second.
5. For the autosave symptom specifically: play for a few minutes so the
   autosave cycle is running (Bloodborne rewrites `userdata0000`, about
   1.3MB, plus `userdata0010`, about 256KB, on a roughly 20.5 second cycle,
   unlinking `backup0000` and `backup0010` first). Log per-frame times.
   Worst frames in each save cycle land at 53 to 62ms against a 16.7ms
   median, and get worse as the session goes on.

The session-length growth is probably a separate term. The source dive
pointed at `buffer_cache.cpp` `ResolveOverlaps` as the likely cause, but we
did not measure that and are not claiming it.

## Proposed direction

Widen the write-fault invalidation from 8 bytes to an aligned 64KB window,
and fall back to the precise 8-byte invalidation when the widened range
fails `IsMapped` (which requires the whole range to be mapped, so the
fallback covers ranges crossing a mapping boundary and preserves current
semantics exactly).

This is a correctness-safe superset by construction. Invalidating more than
the guest actually wrote can only ever add a re-upload, never skip one. The
cost is upload bandwidth in exchange for fault and `mprotect` volume.
Widened fault granularity is what Dolphin, RPCS3 and yuzu all do, so the
trade is well trodden even if 64KB is our own choice of number.

Measured effect of that change on the same rig: faults drop from about
48,000/s to about 1,400/s, handler time from about 850ms/s to about 40ms/s,
and every autosave cycle in the run came in clean, worst frame 16.8 to
19.5ms against 53 to 62ms before. Frame median unchanged at 16.7ms. Full
A/B detail is in the companion PR draft.

We have not yet proven this in a long real-display play session, and there
is a plausible cost we have not seen: over-invalidation could cost GPU
upload bandwidth in texture-heavy scenes. Nothing of the sort showed up
headlessly, but headless runs are not the same test.

The `ENABLE_USERFAULTFD` path has the same shape (`page_manager.cpp` line
177 in 0.17.0, `rasterizer->InvalidateMemory(addr, 1)`) and would presumably
want the same treatment. We did not build or test that path, so we have left
it alone.

## Code references (0.17.0 tag)

- `src/video_core/page_manager.cpp:210` `GuestFaultSignalHandler`, the
  8-byte invalidate on write faults and the 8-byte `ReadMemory` on read
  faults
- `src/video_core/page_manager.cpp:177` the userfaultfd equivalent, 1 byte
- `src/video_core/page_manager.cpp:222` `UpdatePageWatchers`, the per-page
  protection state and the batched `Protect` calls
- `src/video_core/renderer_vulkan/vk_rasterizer.cpp:1045`
  `Rasterizer::InvalidateMemory`, and the `IsMapped` gate at line 1068
- `src/video_core/texture_cache/texture_cache.cpp` `InvalidateMemory`, the
  global mutex mentioned above
- `src/video_core/renderer_vulkan/vk_presenter.cpp` `Presenter::PrepareFrame`,
  the other taker of that mutex
