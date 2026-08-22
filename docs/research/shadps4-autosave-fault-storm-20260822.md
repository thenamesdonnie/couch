# The Bloodborne autosave stall, and the fault storm underneath it

22 Aug 2026. Donnie: "can we look at fixing the auto save frame drops?
whetherer it's a community patch or we do it ourself." No community patch
exists (researched 21-22 Aug: untracked upstream, no save-related patch in
ps4_cheats, no async-save option in the emulator). We did it ourselves.

## What was measured, in order

1. **Live session (21 Aug, bb-drop-report):** a 34ms-230ms frame stall
   within 1s of every ~20.5s autosave cycle (SLSession unlinks
   backup0000/0010, rewrites userdata0000 1.3MB + userdata0010 256KB),
   growing with session length. GPU 55-65% during stalls (card waiting).
2. **Source dive (agent, line-cited):** the write path is buffered stdio
   with NO fsync (io_file.h flushes to page cache only); no lock shared
   with the render thread spans the write. Original hypothesis (host READ
   of guest memory faulting) FALSIFIED: with readbacks_mode=0/1 no guest
   page is read-protected. But guest WRITES fault: tracked pages are
   write-protected, and the fault handler invalidates just **8 bytes**
   (page_manager.cpp GuestFaultSignalHandler), costing one mprotect (with
   its cross-core TLB shootdown) per page of any bulk write, plus locks
   shared with the GPU thread (TextureCache::mutex taken unconditionally
   per fault AND per flip in Presenter::PrepareFrame).
3. **Instrumented build (this repo's checkout at 0.17.0 = the exact live
   release, ~/src/shadps4-dbg):** three probes - fault census (atomics in
   the signal handler), write-probe (wall + fault deltas around
   file->Write), prepare-probe (slow-flip detector). Findings:
   - the 1.3MB save write itself: **316us**, ~20 faults. Host I/O and the
     write call are innocent.
   - **gameplay runs a permanent fault storm: ~48,000 faults/s costing
     ~850ms/s of handler time** (0.85 CPU cores, forever). Title screens
     quiet; the storm starts the moment the world loads. Saves and combat
     ride ON TOP of this saturated economy - their bursts are the felt
     drops.
   - PrepareFrame never exceeded 2ms headlessly (the mutex coupling did
     not manifest in rig conditions; may still matter under real display
     load).

## The fix (built, A/B-verified headless)

`page_manager.cpp` GuestFaultSignalHandler: on a write fault, invalidate an
**aligned 64KB window** instead of 8 bytes, falling back to the precise
8-byte invalidate when the window fails IsMapped (range crossing a mapping
boundary - preserving upstream semantics exactly). Correctness-safe by
construction: the widened invalidate is a strict superset (only ever ADDS
re-upload, never skips one). Precedent: Dolphin/RPCS3/yuzu all use widened
fault granularity.

**A/B (isolated dbg-userdir, headless gamescope, fake-pad-driven, scored by
autosave-score.py + bb-drop-report):**

| metric (in-game)            | baseline 0.17.0 | 64KB widening |
|---|---|---|
| faults/s                    | ~48,000         | ~1,400        |
| fault handler ms per second | ~850            | ~40           |
| autosave-cycle worst frame  | 53-62ms (stall) | 16.8-19.5ms   |
| frame median                | 16.7ms          | 16.7ms        |

## Postscript (22 Aug ~23:00, after the live evening)

The play test was derailed by three console-side failures, all root-caused,
NONE of them this fix: (1) game-pids only matched shadPS4 by AppImage name,
so every safety system was blind to fix-build sessions (fixed: exact
first-token match); (2) couchd stale tap-resume + a leaked eldenring.exe
from 21 Aug (replay tests owed); (3) gamescope 3.16.25 heap-corruption
SIGABRT at its first-ever 4K120 session, whose reaper killed a healthy
emulator mid-autosave-write (save survived; wrap benched). The evening's
final BARE STOCK session was the best on record (1% low 55.7 vs 49; no
visible autosave metronome) - performance EPP + no compositor + game-mode
+ warm caches carried most of the felt win. CONSEQUENCE: this fix is
exonerated but its adoption case must be re-made with a fair bare A/B
against that new baseline before the probes are stripped and it goes
upstream. The 34x fault-economy reduction stands regardless and is
upstream-worthy on its own.

## Status and the adoption plan

- The fix build (with instrumentation still in - useful for the play-test,
  strip before upstreaming) lives at `~/src/shadps4-dbg/build/shadps4`.
  Local diffs: fault widening + 3 probes; audio-era diffs stashed
  (`git stash list`).
- **NOT live.** Donnie play-tests first: flip the launcher to the local
  build (see todo), fight something, watch the fps overlay, run
  bb-drop-report after. Rollback = remove the flag, next launch is the
  AppImage again.
- Upstream: file the issue with the census numbers (48k/s is a general
  finding, not BB-specific) and PR the widening; also report the
  correctness gap the dive found (file WRITES of guest memory never
  download GPU-modified data - ReadFile invalidates, write does not).
- Residual risks, stated: over-invalidation could cost GPU upload
  bandwidth in texture-heavy scenes (not seen headless; watch the overlay
  in combat); the TextureCache-mutex-per-flip coupling remains unpatched
  (Fix 2 in the agent report) if stalls persist under real display load.

## Rig + tools (reusable)

- `autosave-rig.sh` (scratchpad; promote if reused): isolated-userdir
  headless boot, fake-pad menu navigation (cross-only), activity loop,
  stamped SLSession log, MangoHud per-frame CSV. MUST run foreground (the
  session's background-task plumbing killed two runs deterministically at
  ~273s; foreground immune). Inhibits pad-home-watcher (its 10s reconcile
  repairs rig state as drift) and Kodi joystick input for the duration.
- `autosave-score.py` (scratchpad): per-save-cycle worst-frame scorer.
- Full mechanism map with file:line citations: the 22 Aug source-dive
  agent report (session transcript); key anchors: page_manager.cpp
  GuestFaultSignalHandler / UpdatePageWatchers, buffer_cache.cpp
  ResolveOverlaps (the session-growth term), texture_cache.cpp
  InvalidateMemory (global mutex), file_system.cpp write().
