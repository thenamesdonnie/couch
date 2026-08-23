# DRAFT ONLY. NOT TO BE FILED.

**Hold until the fair bare A/B play session (fix build, no gamescope wrap)
returns an adoption verdict on the fault-widening work.** This report is
independent of that fix, but it came out of the same investigation and
should go upstream in the same batch, under the same name, once we are
posting at all. Nothing here has been sent to anyone. Do not post, do not
push.

Target: `shadps4-emu/shadPS4` issue tracker. This is a report from reading
the source, not a fix, and not a bug we have observed at runtime.

---

## Title

File write paths never download GPU-modified guest memory, while the read
path invalidates it

## What this is

While instrumenting the kernel file paths for an unrelated performance
issue, we noticed an asymmetry between reads and writes in how guest memory
is synchronised with the GPU caches. We have not seen a game misbehave
because of it. We are reporting it because it looks wrong from the source
and a maintainer will know in seconds whether it is intended.

All references are to the 0.17.0 tag.

## The read path synchronises. The write path does not.

`ReadFile` in `src/core/libraries/kernel/file_system.cpp:343` invalidates
the destination guest buffer before filling it:

```cpp
s64 ReadFile(Core::FileSys::File* file, void* buf, u64 nbytes) {
    const auto* memory = Core::Memory::Instance();
    // Invalidate up to the actual number of bytes that could be read.
    const auto remaining = file->GetSize() - file->Tell();
    memory->InvalidateMemory(reinterpret_cast<VAddr>(buf), std::min<u64>(nbytes, remaining));
    ...
```

That call reaches `MemoryManager::InvalidateMemory`
(`src/core/memory.cpp:1413`), then `Rasterizer::InvalidateMemory`
(`src/video_core/renderer_vulkan/vk_rasterizer.cpp:1045`), then
`BufferCache::InvalidateMemory` (`src/video_core/buffer_cache/buffer_cache.cpp:69`),
which is where the interesting part is:

```cpp
void BufferCache::InvalidateMemory(VAddr device_addr, u64 size) {
    if (!IsRegionRegistered(device_addr, size)) {
        return;
    }
    memory_tracker->InvalidateRegion(
        device_addr, size, [this, device_addr, size] { ReadMemory(device_addr, size, true); });
}
```

So the read path does download GPU-side modifications back to guest memory
first, where the tracker says the region is GPU dirty. The same shape
appears in `src/core/libraries/np/np_trophy.cpp:289` and in
`src/core/libraries/avplayer/avplayer_source.cpp:691`.

The write paths call nothing. `write`
(`src/core/libraries/kernel/file_system.cpp:301`) ends in:

```cpp
    return file->Write(buf, nbytes);
```

with no preceding synchronisation of `buf`. The same is true of `writev`
(line 409, `file->Write(iov[i].iov_base, iov[i].iov_len)` at line 433) and
`posix_pwritev` (line 1121, the same call at line 1158).

## Why it looks wrong

`buf` is guest memory. If the region has been modified by the GPU and the
modification is still sitting in a GPU-side buffer awaiting download, the
host reads whatever the CPU-visible copy holds and writes that stale content
to the file. The read direction has been given machinery for exactly this
hazard, and the write direction has none.

There is no `ReadMemory` or download entry point on `MemoryManager` at all.
`src/core/memory.h:291` exposes only `InvalidateMemory`. The download call
exists one layer down (`Rasterizer::ReadMemory`,
`vk_rasterizer.cpp:1055`, and `BufferCache::ReadMemory`,
`buffer_cache.cpp:77`, whose header already carries an `is_write` flag,
`buffer_cache.h:110`), but nothing in `core/` can reach it. That absence is
what makes us think this is an oversight rather than a decision, though we
may simply be missing where it is handled.

## What we are not claiming

We want to be careful about how far this goes, because we have not
demonstrated a failure:

- **No observed bug.** We found this by reading, not by reproducing. We do
  not have a title, a save, or a screenshot showing a corrupted file.
- **It may be unreachable in practice.** Whether real titles ever hand a
  file write a buffer whose most recent writer was the GPU is exactly the
  thing we cannot answer. If they do not, this is theoretical.
- **Readback configuration probably matters.** Our measurements were taken
  with `readbacksMode = 0`, where, as far as we could tell, no guest page is
  read-protected. Under configurations that do read-protect tracked pages,
  the emulator's own read of guest memory inside `file->Write` would itself
  take a read fault, land in `GuestFaultSignalHandler`, and call
  `rasterizer->ReadMemory(addr, 8)`, which downloads. If that is right, the
  hazard may be covered incidentally in readback modes, 8 bytes at a time,
  and uncovered in the default mode. We have not verified this, and we would
  not want the conclusion to rest on it either way.
- **We have not attempted a fix.** The obvious shape is a download of the
  source range before the write, symmetric with what `ReadFile` does, but
  the cost and the correct placement (and whether it wants the existing
  `is_write` flag) are maintainer calls, not ours. Given the fault volumes
  we measured elsewhere in this codebase, adding a per-write synchronisation
  without thought about granularity could be expensive.

## Code references (0.17.0 tag)

- `src/core/libraries/kernel/file_system.cpp:343` `ReadFile`, invalidates
  the destination, line 347
- `src/core/libraries/kernel/file_system.cpp:301` `write`, no
  synchronisation, `file->Write` at line 325
- `src/core/libraries/kernel/file_system.cpp:409` `writev`, same, line 433
- `src/core/libraries/kernel/file_system.cpp:1121` `posix_pwritev`, same,
  line 1158
- `src/core/memory.h:291` only `InvalidateMemory` is exposed
- `src/core/memory.cpp:1413` `MemoryManager::InvalidateMemory`
- `src/video_core/renderer_vulkan/vk_rasterizer.cpp:1045` and `:1055`
  `InvalidateMemory` and `ReadMemory`
- `src/video_core/buffer_cache/buffer_cache.cpp:69` and `:77`, the download
  callback and `ReadMemory(device_addr, size, is_write)`
- `src/video_core/buffer_cache/buffer_cache.h:110` the `is_write` parameter,
  default false
