# Attempt #2 at the shadPS4 fault storm: widen the protection, never the claim

23 Aug 2026. Companion to `shadps4-autosave-fault-storm-20260822.md`, which
measured the storm and records the death of attempt #1. Read that first.

Attempt #1 made the emulator 34x cheaper and rendered characters black. This
document is the redesign: what the source actually guarantees, what the
failure really was, what upstream and other emulators do, four candidate
designs, and the one that was built.

---

## 1. Plain language: what is actually going on

shadPS4 keeps a copy on the graphics card of chunks of the PlayStation's
memory. Vertex data, animation matrices, textures, whatever a shader needs to
read. Once a chunk has been copied over, the emulator has a problem: if the
game later changes those bytes on the CPU side, the card's copy is stale.

The trick it uses is a hardware alarm. After copying a page of guest memory to
the card, it asks the operating system to make that page **read-only**. The
game does not know this. The next time the game writes there, the CPU traps,
Linux delivers a SIGSEGV, and shadPS4's signal handler runs. The handler says
"right, that page is dirty again, re-upload it before the next draw", removes
the read-only protection so the write can complete, and returns.

That is one CPU trap, one `mprotect` system call, and one cross-core TLB
shootdown (every core that might have the old permission cached has to be
interrupted and told to forget it) **for every 4KB page the game writes**.
Bloodborne does this about 48,000 times a second, forever.

Two separate things are expensive here, and it matters which is which:

* **The number of faults.** One per page per write burst.
* **The cost of each fault.** Measured at ~17.7 microseconds of wall time
  inside the handler, which is enormous. A bare trap plus `mprotect` should be
  1-3us. The rest is shadPS4's own bookkeeping and lock contention.

Attempt #1 attacked only the first number, by the crudest means available, and
broke the game.

## 2. Why attempt #1 broke rendering, at source level

The handler used to call `rasterizer->InvalidateMemory(addr, 8)`. Attempt #1
changed it to `InvalidateMemory(AlignDown(addr, 64KB), 64KB)`.

The range handed to `InvalidateMemory` is not a hint. It is a **claim**: "guest
memory is the truth over these bytes". Two consumers act on it.

**Buffer cache** (`buffer_cache.cpp:69` → `memory_tracker.h InvalidateRegion`
→ `region_manager.h ChangeRegionState<CPU, true>`): sets a per-4KB-page "CPU
modified" bit. On the next draw that uses the buffer, `ForEachUploadRange`
copies those pages from guest memory to the card, overwriting whatever was
there.

**Texture cache** (`texture_cache.cpp:126`): for every image registered
anywhere in the touched pages, it asks `image.Overlaps(addr, size)` — using the
**exact byte range passed in**, not the page range. If the claim overlaps the
image's own bytes, the image is flagged `CpuDirty` and will be re-uploaded from
guest memory. If it does not overlap, upstream deliberately does *not* flag it,
and the code says so:

> This page access may or may not modify the image. We should not mark it as
> dirty now. If it really was modified it will receive more invalidations on
> its other pages.

Upstream is careful. Attempt #1 drove straight through that care. A 64KB claim
overlaps the bytes of every image that has so much as a corner in the window —
including render targets and images the CPU has never written, whose real
content only ever existed on the GPU. Those got flagged `CpuDirty` and
re-uploaded from guest memory that was zeroed (renders **black**) or stale
(renders **multicoloured**). One mechanism, both of Donnie's sightings.

**The lesson, stated once:** you may widen the *protection* work as much as you
can prove is harmless. You may never widen the *claim*.

## 3. What the source actually guarantees (Phase 1 findings)

Reading `~/src/shadps4-dbg/src` at the 0.17.0 tag.

### 3.1 Downstream of InvalidateMemory

`Rasterizer::InvalidateMemory` (`vk_rasterizer.cpp:1045`) gates on
`IsMapped(addr, size)` — which demands the **whole** range be mapped, hence
attempt #1's fallback — then calls both caches. **Nothing is destroyed.** Both
caches only *mark*: the buffer cache sets a dirty bit, the texture cache sets
`CpuDirty` and stops watching the pages. The damage is done later, lazily, when
the marked thing is next used and re-uploaded.

### 3.2 How CPU authority and GPU authority are distinguished

This is the important answer, and it is much better than expected on one side
and absent on the other.

**Buffers: there is a real per-page GPU-authority bit.** Each `RegionManager`
covers 4MB of guest address space and holds four bitsets at 4KB granularity
(`region_manager.h:189`):

| bitset      | meaning |
|---|---|
| `cpu`       | page written by the guest since the last upload; needs re-upload |
| `gpu`       | page written by the GPU; guest memory is stale here |
| `writeable` | mirror of `cpu`; a page is write-protected exactly when `cpu` is 0 |
| `readable`  | mirror of `~gpu`, for the read-protection path |

`gpu` is set by `ForEachUploadRange` whenever a buffer is bound writable, and
by `CopyBuffer`, regardless of readback mode. It is cleared only by an actual
download. So `IsRegionGpuModified(addr, size)` is a **cheap, existing,
per-page** answer to "does the GPU own this?" for buffer memory.

**Textures: there is no such per-page bit.** The texture cache knows GPU
authority only per image (`ImageFlagBits::GpuDirty`, `MaybeCpuDirty`, the
`track_addr`/`track_addr_end` head/tail trimming), and its page table
(`texture_cache.h:47`) is keyed at **1MB** granularity. The *only* precise
authority test it has is the byte-exact `image.Overlaps(addr, size)` in
`InvalidateMemory` itself.

**So: yes, there is a cheap existing way to ask "is anything GPU-owned here" —
for buffers.** For textures there is not, and the honest engineering answer is
therefore not to try, but to leave the texture path byte-exact.

### 3.3 What the page tracker costs

`PageManager::Impl` (`page_manager.cpp`) keeps a `PageState` per 4KB page with
a 7-bit `num_write_watchers` count (buffer cache and texture cache can both
watch the same page) and a 1-bit read watcher. A page is protected iff
`num_write_watchers > 0`.

`UpdatePageWatchers` **already coalesces**: it walks the page range and emits
one `Protect()` call per contiguous run of pages whose permissions change. So
the batching machinery exists. What did not exist is anything that gives it a
run to batch — on the fault path it is always handed exactly one page.

`Protect()` is a plain `mprotect` (`address_space.cpp:778`). Per fault that
means:

* the kernel takes `mmap_write_lock` on the whole process,
* splits or merges VMAs (the live process oscillates around **1,850 VMAs**,
  measured passively tonight on Donnie's own session, so this is really
  happening),
* and flushes the TLB, which for a process with ~10 running threads means IPIs
  to every core in `mm_cpumask` with the initiator waiting for acknowledgement.

**Which of the three is the real cost: measured or reasoned?** Reasoned from
code, with two passive measurements as support, and stated as such. Section 4.3
corrects the conclusion with published numbers: the `mprotect` is a smaller
share than I first assumed, and the handler's own bookkeeping is a larger one.

1. `min_flt` on the live stock session is only ~250/s. Linux does **not**
   count a fault that ends in SIGSEGV (`mm_account_fault` returns early on
   `VM_FAULT_ERROR`), so the 48,000/s never appear there. The corollary is that
   the kernel-side fault work is the *cheap* part: no page table population,
   just the access check and signal delivery.
2. System time on the live session runs ~0.44 cores process-wide, spread over
   the guest threads. That is consistent with an `mprotect` storm and with
   signal frame setup, and it is well below the 0.85 "cores" the handler census
   reported.

That gap is the finding. **The census probe measures wall time inside the
handler, not CPU time.** Time spent blocked on `TextureCache::mutex` or a
`RegionManager` lock counts fully towards the 850ms/s figure while burning no
CPU at all. So a large part of attempt #1's headline number was probably
*contention*, not work — and contention is removable without touching
semantics. This also means the "0.85 of a CPU core" line in the issue draft
overstates the case and must be reworded before filing.

Per-fault, the handler does: an `IsMapped` shared-lock plus interval query; a
`buffer_ranges.Intersects` query; a `RegionManager` adaptive-mutex acquire
contended with the GPU thread; the `mprotect`; and **`TextureCache::mutex`, a
single global `std::mutex` held by the render thread across image lookups and
uploads, taken on every single fault** even when no image exists within a
megabyte of the faulting address.

### 3.4 Where the faults come from

Steady state, not bursts. Each frame the buffer cache uploads dirty pages and
immediately re-protects them (`ForEachModifiedRange<CPU, clear=true>` →
`UpdateProtection<true>`), the game writes them again, they fault again. At
48,000/s over 60fps that is ~800 faults per frame, i.e. ~3.2MB/frame of guest
memory that is both CPU-written and GPU-visible. Entirely plausible for
Bloodborne's skinning and particle data. The autosave burst (~320 pages for the
1.3MB serialisation) rides on top of that, which is why it is felt.

## 4. What upstream and other emulators do (Phase 2 findings)

### 4.1 shadPS4 itself

Researched live on GitHub tonight.

* **Our target code has not moved.** `page_manager.cpp`,
  `buffer_cache/memory_tracker.h` and `buffer_cache/region_manager.h` have had
  **no commits since March 2026**. `texture_cache.cpp` has one commit since
  0.17.0 (#4889, 21 Aug) which does not touch `InvalidateMemory`. So the
  problem is unsolved upstream and our 0.17.0 reading is current.
* **Upstream has already merged a widening — but in a different place, and
  with the safety property attempt #1 lacked.** PR **#4839**, merged 12 Aug
  2026, shipped in 0.18.0. It widens the **readback/download** window on a
  fault to 512KB, and critically it *clamps the window to the owning buffer*:
  ```cpp
  window_start = max(AlignDown(device_addr, 512_KB), buf_start);
  window_end   = min(max(window_start + 512_KB, device_addr + size), buf_end);
  ```
  Downloading more of a buffer the GPU owns is safe (the GPU is authoritative,
  guest memory is being refreshed). Uploading more, which is what attempt #1
  did, is not. The clamp-to-object idea is worth stealing regardless.
* **An RFC in exactly our space has sat unanswered for four months.** Issue
  #4316 (24 Apr 2026) proposes measurement instrumentation plus a batched
  readback mode, with Bloodborne numbers. No maintainer has replied. Meanwhile
  #4839, a 22-line concrete PR, was approved and merged in days. **Practical
  consequence for us: ship a small patch, do not ship an RFC.**
* **A collision is coming.** PR **#3798** (raphaelthegreat, open since Nov
  2025, last touched 29 Jul 2026) rewrites `memory_tracker.h` and
  `region_manager.h` to per-page locking with CAS. Any patch of ours in those
  two files lands on top of a maintainer's own in-flight rewrite. Keep our
  footprint there minimal and be ready to rebase.
* **Widening downloads has a live hazard.** Issue #4816 (8 Aug 2026) reports a
  readback overrun causing Vulkan device loss in Battlefield 4, because
  `StreamBuffer::Map()` returns null past its 32MB budget and the download
  proceeds anyway. Our change does not widen downloads, so it does not touch
  this, but it is a reason not to reach for "just widen the readback too".
* Bloodborne-specific: issue #3826, readbacks cause hangs in Bloodborne
  loading screens, open since Nov 2025, no maintainer response. Our config
  (`readbacksMode = 0`) avoids that path entirely.

### 4.2 Other emulators

The survey found the design below already exists, independently invented, in a
codebase none of us had thought to look at.

**Xenia (Xbox 360) is the same design, down to the safety argument.** Its
`SharedMemory` keeps two parallel bitmaps at one bit per 4KB page,
`system_page_flags_valid_` and `system_page_flags_valid_and_gpu_written_`. On a
fault it widens the un-protection outward using `lzcnt`/`tzcnt` over the
GPU-written bitmap, stopping at the first GPU-authoritative page. The
justification, from the Xenia dev blog, is our paragraph 2 of section 5:

> the range being invalidated may actually be smaller if render-to-texture or
> shader memory export results are placed nearby, as while **it's safe to upload
> the same CPU-side memory contents multiple times, GPU-generated data is not
> mirrored in CPU-visible memory in Xenia, so it must be invalidated as
> precisely as possible**

That is exactly why attempt #1 broke and exactly what design (A) fixes. The
motivation is ours too: without widening, software-rendered Doom ran at 3fps.

**Xenia's window is 256KB, not 64KB, and they measured it.** 4KB callbacks gave
4fps on one title; 64KB left the game code at 3ms/frame; 256KB brought it to
0.7ms. Our 64KB was a guess. The build now reads
`SHADPS4_FAULT_CLAIM_WINDOW_KB` at startup so sweeping 16/64/256/1024 is one env
var per run. Xenia also caps total excess (`kMaxUnwatchExcess = 4MB`) so a very
sparse region cannot claim an unbounded run; we get that for free by clamping to
the 4MB `RegionManager`.

**RPCS3 names the decoupling.** `rsx::buffered_section` carries three ranges —
`locked_range` (page-aligned, what is actually `mprotect`ed), `cpu_range` (the
resource's extent) and `confirmed_range` (the exact sub-range known to matter) —
and every overlap query takes an explicit `section_bounds` argument saying which
one it means. It also has the deferred-re-protect idea we should steal:
`rsx::mm_protect` **un-protects synchronously (correctness) but queues
re-protection** and flushes the queue on the RSX thread, because re-protection is
the direction that costs a TLB shootdown.

**Ryujinx has the thing that would let us widen the texture side too.**
`BufferModifiedRangeList.ExcludeModifiedRegions` slices a dirty range against an
interval list of GPU-modified sub-ranges and uploads only the gaps. That makes
widening safe *by construction* rather than by careful bounding. RPCS3 has the
mirror image in `add_flush_exclusion`. Ryujinx also has design (D) as
`RegionHandle._volatile`: five consecutive dirty/consume cycles and the handle is
never protected again — gated on `_preAction == null`, i.e. only where the GPU is
a pure consumer.

**yuzu's `OnCPUWrite` is a one-line statement of our rule:** if
`IsRegionGpuModified(addr, size)` it returns without unprotecting at all, leaving
the page to keep faulting rather than hand it to guest RAM. (Correction to
earlier notes: the write-streaming heuristic I half-remembered is
`uniform_buffer_skip_cache_size`, which drops small uniform uploads out of the
cache when the hit rate falls below ~98% — and it is gated on
`!IsRegionGpuModified` too. `has_stream_leap` is a buffer *allocation* heuristic,
not a protection one.) yuzu's texture cache, by contrast, marks a whole image
CPU-modified for any byte written anywhere in it — **the exact over-claim that
killed attempt #1, permanently baked in.** Do not copy yuzu for textures.

**Dolphin and PCSX2 do not page-protect guest RAM for GPU coherency at all**,
and that is the most interesting result in the survey. Dolphin hashes texture
content once per bind instead; for EFB copies (its render targets) it `memset`s
the guest range to a known pattern and hashes that, so the hash is not a checksum
of correct data but **a token proving nobody has touched these bytes since the
GPU claimed the region**. PCSX2, for recompiler pages, demotes a page out of
protection on its *first* fault into a "manual" mode that compares the exact
compiled bytes at block entry, with a size-weighted counter to promote back and a
four-strike permanent lock-in. The shared insight is worth stating plainly:
page-protection cost scales with **guest write count** and is unbounded;
hash/validate cost scales with **draw or bind count** and is bounded by the frame
budget. Two mature emulators picked the bounded one.

### 4.3 The per-fault cost, corrected

The survey overturned part of my reasoning in 3.3, and the correction matters.
Peter Xu's measurements (Linux 5.9, i7-8665U) decompose a single-page
write-protection fault as:

| stage | cost |
|---|---|
| fault → handler entry | 0.74us |
| `mprotect` resolve | **0.36us** |
| return / `sigreturn` | 0.81us |
| **total bare mechanism** | **1.92us** |

So `mprotect` is only ~19% of the bare cost; **signal delivery and return are
81%**. And our handler measures ~17.7us of wall time, nine times the bare
mechanism. That gap is shadPS4's own bookkeeping and lock waiting, which
reinforces the conclusion that the lock-free texture early-out is the larger of
the two wins in this patch.

Two further corrections. Naive `userfaultfd` write-protect with a handler thread
is **worse** (4.74us), not better — the usual advice is wrong for this workload.
And this CPU has no `INVLPGB`: it is a Zen 3 feature but is not exposed on a
5700X3D, so we get none of the hardware TLB-broadcast relief that landed in Linux
6.15. Shootdowns here really are IPIs.

**The mechanism-level answer, for later.** `PAGEMAP_SCAN` +
`UFFD_FEATURE_WP_ASYNC`, both Linux 6.7, let the kernel resolve write-protection
faults itself with no message and no signal, and then hand you the whole batch of
dirty pages run-length encoded in one `ioctl` that also re-arms protection
atomically. No signal frame, no per-page syscall, no VMA splitting, no
`mmap_lock` write. It was contributed to emulate Windows `GetWriteWatch`, with
Wine and Dolphin named as intended consumers; Wine shipped it in 10.7 and
measured *Streets of Rage 4* level loads dropping from 6-8s to 1.5-2s. **This box
runs kernel 7.0, so it is available today.** That is a much bigger change than
this patch and needs a fallback for older kernels, Windows and macOS, but it is
the direction that removes the storm rather than thinning it.

One line from the Wine work is worth keeping in mind for Bloodborne: the win came
partly because slow fault handling had been *changing the guest's own behaviour*,
pushing it into a memory strategy that hit protected pages more often than it
otherwise would. A feedback loop like that would not show up in any static
analysis of the fault path.

## 5. Candidate designs

### (A) Widen only over pages with no GPU-side authority — RECOMMENDED, BUILT

Keep the reported access at 8 bytes. Split the two roles:

* **Texture cache: unchanged, byte-exact.** It is told the guest wrote 8 bytes,
  exactly as today, so it can flag `CpuDirty` on exactly the images upstream
  would have flagged. *Attempt #1's failure is unreachable from here.*
* **Buffer cache: batch the un-protection.** On a fault at `addr`, take the
  aligned 64KB window containing it, clamped inside the one 4MB
  `RegionManager`, and grow a contiguous run outward from the faulting page
  over neighbours that are **currently protected by this cache** (`cpu` bit 0)
  **and not GPU modified** (`gpu` bit 0). Set `cpu` over the whole run in one
  operation. Because the run is contiguous, the existing coalescer emits **one
  `Protect()` call**: one `mprotect`, one TLB shootdown, one VMA operation, for
  up to 16 pages.

**Why it cannot reproduce the black-texture failure.** Two independent reasons,
either sufficient:

1. The texture cache is never handed a widened range. The only thing that can
   mark an image `CpuDirty` is a byte-exact overlap with the 8 bytes the guest
   really wrote — identical to upstream, line for line.
2. On the buffer side, claiming a neighbour is provably a **no-op on content**.
   Take page P in the claimed run. It was write-protected, so its `cpu` bit was
   0, so its GPU-side copy was uploaded from guest memory and the guest has not
   written it since (a guest write would have faulted and set `cpu`). Its `gpu`
   bit is 0, so the GPU has not written it since either. Therefore guest memory
   and the card's copy are **byte-identical**, and the extra upload we schedule
   copies the same bytes back. It costs PCIe bandwidth. It cannot change a
   pixel.

Note the contrast with attempt #1, which claimed pages with **no test at all** —
including pages whose `gpu` bit was set, and pages holding render targets.

Cost: bounded at 16x the upload volume of the pages actually written, worst
case, and in practice much less because the run stops at the first page that is
already dirty or GPU-owned. Complexity: ~90 lines across five files.
Upstreamability: good on argument, with the #3798 collision to manage.

**Companion, separable: a lock-free texture-cache early-out.** Mirror the
texture page table's occupancy into a plain array of atomic counters, so the
fault path can ask "could any image be here?" without taking the global
`TextureCache::mutex`. When the answer is no — which is most faults, since most
of the storm is buffer memory — `InvalidateMemory` would have been a pure no-op
anyway, so skipping it is exactly equivalent. This attacks the *cost per fault*
rather than the count, and if section 3.3's reasoning is right it may be the
larger win of the two. Kept as its own commit so it can be A/B'd and dropped
independently.

### (B) Widen within the same guest mapping, over pages tracked as CPU-written

Rejected as stated. Pages "currently tracked as CPU-written" are by definition
already unprotected and do not fault, so the condition selects nothing useful.
Reading it charitably as "within the same mapping", clamping to a mapping is
far too coarse: guest mappings are megabytes and contain render targets. It is
attempt #1 with a bigger fallback. The right clamp is the one upstream chose in
#4839 — the owning *object* — and design (A) goes further by testing each page.

### (C) Batch the mprotect / defer re-protection to end of frame

Real, and semantically neutral in its weak form — but the weak form is already
implemented (`UpdatePageWatchers` coalesces runs; there is simply never a run to
coalesce on the fault path). The strong form, leaving uploaded pages unprotected
until end of frame, is **unsound as stated**: an unprotected clean page that the
guest writes is undetectable, so you would silently miss invalidations, which is
a worse class of bug than attempt #1 (stale data with no visible trigger). It
can be made sound by unconditionally marking every deferred page dirty at frame
end, but that needs exactly the same `gpu`-bit gate as design (A) and buys less.
Design (A) is the good half of (C) with the soundness proof attached.

Its value depends on an unmeasured number: how many *distinct* pages fault per
frame versus total faults per frame. If pages fault repeatedly within a frame
(bind, upload, re-protect, write, fault, repeat), deferral wins big. The probe
for this is in the build; see section 7.

### (D) Temporal: unprotect a region during a burst, re-invalidate at a sync point

The yuzu write-streaming idea. Count faults per region; when a region is hot,
stop protecting it entirely and treat it as permanently CPU-dirty, re-uploading
it wholesale each frame; revert when it goes quiet or when the GPU claims it.
Highest ceiling — a hot region drops to *zero* faults — and highest risk: it
must never cover an image (an unwatched texture page means a missed texture
update, i.e. silent staleness), it needs the `gpu` bit gate anyway, and it needs
hysteresis tuning that we cannot calibrate on one title. It is also the most
likely to be rejected upstream as a heuristic. Correct next step *after* (A),
not instead of it.

## 6. What was built

Branch `fault-batch-v2` in `~/src/shadps4-dbg`, off the 0.17.0 tag. Attempt #1
is preserved on `fault-widening-v1-dead` (commit 4a34e65) so nothing is lost.

| file | change |
|---|---|
| `region_definitions.h` | `FAULT_ACCESS_BYTES = 8` with the "never grow this" comment |
| `region_manager.h` | `ClaimFaultRun(offset, window)` — the gated run growth |
| `memory_tracker.h` | `InvalidateRegionFromFault` — single-region, same readback decision as `InvalidateRegion` |
| `buffer_cache.{h,cpp}` | `InvalidateMemoryFromFault` |
| `vk_rasterizer.{h,cpp}` | `InvalidateMemoryFromFault` — widened buffer path, byte-exact texture path, `FAULT_CLAIM_WINDOW = 64KB` |
| `texture_cache.{h,cpp}` | `MayHaveImageAt` + atomic occupancy mirror |
| `page_manager.{h,cpp}` | handler calls the new entry point; probe counters |
| `vk_presenter.cpp` | census line extended with image-fault and claim-width counters; `SHADPS4_AUTOSHOT_FRAMES` self-capture |

`FAULT_CLAIM_WINDOW` is read once at `Rasterizer` construction from
`SHADPS4_FAULT_CLAIM_WINDOW_KB` (never in the fault path), so the window can be
swept without a rebuild.

Probes added for the two numbers the design turns on, both to be stripped
before any PR: `img_faults` (how much of the storm is image memory, which
bounds what design (A) can achieve) and `claim_calls`/`claim_pages` (the mean
run width actually achieved, which is the real fault-reduction factor).

## 7. Test plan, and the rule that must not be broken again

A headless fault-count win is exactly what fooled us on 22 Aug. The rig must
score **rendering correctness** as a first-class result, not as an afterthought.

* Fault economy: census deltas from the presenter log line, in-game portion
  only, against a stock arm of the same tree.
* **Rendering: frame capture and luminance comparison.** The failure signature
  is known and quantified from
  `evidence-fault-widening-black-entities-20260823.png`: affected geometry read
  mean luminance 8-10 against 47-51 for correct geometry in the same frame.
  Any arm whose character/prop regions sit near the environment's luminance
  passes; any arm where they collapse to single digits fails.
* Rig hygiene from the 22 Aug notes: foreground only, isolated `XDG_DATA_HOME`
  via the dbg-userdir pattern, pad-home-watcher and Kodi joystick inhibited.

Two tools are staged in `~/src/shadps4-dbg` (outside this repo on purpose):

* `soak-v2.sh <arm> <seconds>` — headless gamescope run against the isolated
  user dir, census extraction, periodic frame capture. It **refuses to start if
  any shadps4 process is already running**, so it cannot trample a live session.
  Frame capture goes through the emulator's own GameOnly screenshot path
  (`SHADPS4_AUTOSHOT_FRAMES`), not `import`/`xwd`, because a headless gamescope
  has no window on `:0` to grab. Getting this wrong would have produced zero
  frames and a silent "could not verify rendering", which is the failure this
  whole redesign exists to avoid.
* `score-frames.py` — the rendering-correctness scorer. Paired mode reports the
  share of pixels that were lit (>30) in the stock arm and collapsed into the
  4-14 "black entity" band in the v2 arm; that number should be ~0. Calibration:
  run against the known-bad attempt #1 capture it reports a 5.59% dark-band
  share, so the signature is detectable at this resolution.

The paired test is the decisive one. A single frame's dark-band share is not,
because a genuinely dark scene has dark pixels too.

## 8. What is left for a human

Nothing here has been armed, and `data/shadps4-local-build` is still
`.disabled-20260823-corruption`, so every launch is the stock AppImage.

1. **Run the A/B.** Box must be free of any shadps4 session.
   `cd ~/src/shadps4-dbg && git stash && ./soak-v2.sh stock 180` then
   `git stash pop && ninja -C build shadps4 && ./soak-v2.sh v2 180`, then
   `./score-frames.py soak-out/stock soak-out/v2`. Foreground, both arms.
   Adoption needs **both** a fault-economy win and a clean rendering verdict.
2. **`perf` needs root here.** `/proc/sys/kernel/perf_event_paranoid` is 4, so
   the no-patch cross-checks the issue draft offers a maintainer cannot be run
   from a user shell on this box. To confirm the `mprotect` half of the cost
   model, Donnie can run in his own terminal, during gameplay:
   `sudo perf stat -e page-faults,syscalls:sys_enter_mprotect -p $(pgrep -f Shadps4-sdl.AppImage) -- sleep 10`
3. **Play it.** Same scene as the 23 Aug corruption, same weapon, kill
   something. The failure was only ever visible in play.
4. **Decide about 0.18.0.** We are pinned at 0.17.0 and upstream has moved
   (see 4.1). Rebasing onto main before filing anything is the honest move, and
   also the moment to check whether PR #3798 has landed.
5. **Sweep the window.** `WINDOW_KB=16|64|256|1024 ./soak-v2.sh v2 180`, no
   rebuild needed. Xenia's numbers suggest 256KB, but their workload is not
   ours and over-claiming costs upload bandwidth, which the `pages_per_claim`
   census column will show directly.

### Next, if this one works

In rough order of value, from the survey:

* **Deferred re-protection** (RPCS3 `mm_protect`): un-protect synchronously,
  queue the re-locks, flush them on a worker or on overlap. Re-protection is
  the direction that costs the shootdown, and this CPU has no `INVLPGB`.
* **`ExcludeModifiedRegions`** (Ryujinx): subtract GPU-modified sub-ranges at
  upload time. That turns widening from a correctness question into a bandwidth
  question, and it is the only thing that would let us widen the *texture* side,
  which design (A) deliberately refuses to touch.
* **Count faults per host RIP for one session.** Both PCSX2 and Dolphin attack
  the faulting *instruction* rather than the page. We already have the faulting
  RIP in every SIGSEGV and are throwing it away; if the distribution is skewed,
  and it usually is, that is a lever nothing in this design uses.
* **`PAGEMAP_SCAN` + `UFFD_FEATURE_WP_ASYNC`** (section 4.3). The real fix, and
  a much bigger project.

## 9. Honest residuals

* **NOT TESTED AT ALL YET, headless or otherwise.** The patch compiles, links
  and starts, and it has been reviewed line by line against the invariants in
  section 3, but it has never rendered a frame. Donnie was mid-session on the
  stock AppImage for the whole of this work and the rig would have fought him
  for the GPU. No fault numbers, no frames, no verdict. Everything in section 5
  about design (A) is an argument from the source, not a measurement.
* **Not verified in play.** Only Donnie can do that, and only after a clean
  headless pass.
* **The `MayHaveImageAt` early-out slightly widens an existing race.** If the
  GPU thread registers an image in the same microsecond as a guest write, an
  unlocked read can see zero and skip. A freshly registered image uploads from
  guest memory at registration, so the new bytes are normally picked up anyway,
  but this is a real (small) widening of a window the mutex used to narrow. It
  is a separate commit for that reason.
* **We are one week behind upstream.** 0.18.0 landed 18 Aug with #4839 in it.
  Nothing in it touches the write-fault path, but the census should be
  re-confirmed on 0.18.0 or main before anything is filed.
* **The issue draft needs a correction before filing.** "0.85 of a CPU core"
  should become "0.85 seconds of wall time per second inside the handler,
  including time blocked on locks" — see 3.3. Overstating this is the fastest
  way to lose a maintainer.
* **One title, one platform.** Bloodborne, Linux, RADV on RDNA4, signal-handler
  path. The `ENABLE_USERFAULTFD` path is untouched and untested.
