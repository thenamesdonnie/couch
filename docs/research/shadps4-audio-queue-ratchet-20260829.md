# The OpenAL queue that only ever ratchets down

29 Aug 2026. Donnie: Bloodborne audio "goes crackly", worst on speech and louder
music, develops during a session, and **only an emulator restart clears it**.
Previously noticed around Darkbeast Paarl (dense, loud audio) but not tied to it.

## It was already in the log, 21,455 times

```
Lib.AudioOut <Debug> openal_audio_out.cpp:159
  Output: Audio underrun detected (queued: 1), restarting source
```

21,455 underruns. **21,425 of them at `queued: 1`.** Thirty at `queued: 2`.
Nothing higher. The queue had collapsed to a single 5.33ms buffer and stayed
there.

## Mechanism (code-certain, `openal_audio_out.cpp`)

- Bloodborne submits 256-frame blocks at 48kHz = **5.33ms** each.
- `Initialize()` primes **5** blocks of silence out of `NUM_BUFFERS = 6`. That
  is the entire cushion: **~27ms**.
- `Output()` reclaims **all** processed buffers but queues **at most one**. So a
  call late enough for two buffers to drain drops depth by one, and the strict
  one-in/one-out cadence never rebuilds it.
- Recovery on underrun is `alSourcePlay()` only. It does not restore depth.
- With no free buffer, the guest block is **silently discarded**.
- `BUFFER_QUEUE_THRESHOLD = 2 // Queue more buffers when below this` was defined
  for exactly this and **never referenced anywhere**.

A ratchet: every hitch costs runway, nothing gives it back, recreating the port
is the only reset. Hence "restarting the emulator fixes it".

## The fix (commit `47b62e9`, shadps4-dbg)

`Output()` tops the queue back up to `QUEUE_TARGET_BUFFERS` after servicing the
block. Silence, because the audio missed while the guest was late never existed
and cannot be refilled with real sound - and silence is what `Initialize()`
already primes with. Topping up to the **same fixed target** is self-limiting:
it restores the designed cushion, it cannot accumulate latency. Both AL calls
are error-checked and return the buffer to the pool on failure, unlike the
existing path. Silence block allocated once per port. Prime depth and restore
target are now one constant.

Backup of the pre-fix binary: `data/shadps4-binary-backups-v2-1fdc058`; this
build is `-audioqueue`.

## NOT proven to be the crackle

Clipping is a live alternative: Main and BGM are separate OpenAL sources summed
with **no limiter for float output**, and per-channel guest volumes are
collapsed to the maximum channel gain (`openal_audio_out.cpp:182`,
`audioout.cpp:711` uses `*vol` for every flagged channel instead of indexing).
That fits "worse on loud speech/music" but NOT "cleared by restart".

**Five-second discriminator, for when it is audibly crackling:** drop the
emulator volume slider to 50%. Applied before OpenAL mixing, polled every 50ms.
Instant disappearance at 50% and return at 100% = clipping. No change = the
queue.

## Ruled out

- **The Spotify S16+dither story does not repeat here.** OpenAL Soft defaults to
  float, its Pulse backend requests `PA_SAMPLE_FLOAT32NE`, dither is off for
  float, and the 7.1 channel orders agree between shadPS4 and Pulse.
- **The host never repeats a buffer on underrun** - looping is explicitly
  disabled. So the repeating music during the Blood-Starved Beast wedge came
  from the GUEST, not the emulator.
- **No direct fps/audio coupling.** Audio timing is `buffer_frames/sample_rate`
  only. But the audio thread runs plain `SCHED_OTHER` with no realtime priority
  (Linux RT setup is unimplemented), so it is fully exposed to contention.

## The frame rate: UNRESOLVED, and I got this badly wrong twice

**Do not repeat either of my confident claims here.** The honest state:

**Measured, and it is the strongest evidence we have:** the newest MangoHud
capture is **188,951 frames, median 60.0 fps, p5 59.9, p95 60.2**. MangoHud
hooks the swapchain, so that is 60 *presents per second* from the emulator, not
display refreshes. Donnie also insists from feel that it is 60 and that he would
know the difference - which for an action game is a reliable instrument.

**Also true:** the CURRENT session's log applies exactly five patches - Skip
Intro, Performance Patch, Disable Dynamic Light Shadows, 4k Light Grid,
Resolution 2560x1440 - and **no 60fps patch**. Both 60fps entries in the live
`Bloodborne.xml` are `isEnabled="false"`.

These are not obviously compatible and I could not reconcile them. The one
reading where both hold is that shadPS4's presenter runs at display rate
decoupled from game logic (the Fifo-vs-Mailbox question is already open in
`bloodborne-progress.md`). Unverified.

**The mistakes, recorded so they are not repeated:**
1. I asserted "not 60fps" from a config file without measuring, when the
   measurement was already in `data/perf-logs` and I had analysed that very
   file earlier the same day.
2. I then retracted that based on a `60 FPS (With Deltatime)` line in the log -
   which is at line 134,496 of a 684,054-line **append-mode** log, i.e. an old
   session. Always bound a shad_log grep to the current session.
3. `-f true` IS `--fullscreen` (verified in `main.cpp`); that part stands. The
   launcher comment attributing a 60fps unlock to game patches is at best
   imprecise.

**Decisive test not yet run:** launch with `--show-fps`, which counts game
frames rather than presents.

**Consequence for the 28 Aug cutscene hang:** I told Donnie to discard the
"known 60fps issue" explanation because 60fps was off. That reasoning is void.
The 60fps association is back to being an open possibility, neither confirmed
nor excluded.

## sol review error worth recording

The review claimed the log filter was Info-only so Debug underruns "cannot
confirm or exclude" the theory. Wrong: `logFilter`/`logType` are unset in
`config.json` and the Debug lines are plainly present in the log - which is how
the 21,455 were counted. Its own strongest evidence was sitting in a file it
had told itself it could not use.
