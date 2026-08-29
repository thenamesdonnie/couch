## Ranked findings

### 1. High confidence: missed periods can progressively erode the OpenAL queue

**Verified**

- Each Bloodborne block is 256 frames at 48 kHz—5.333 ms. OpenAL owns six buffers but initially queues only five, giving about 26.7 ms of runway: [openal_audio_out.cpp:54](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:54), [openal_audio_out.cpp:244](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:244), [openal_audio_out.cpp:317](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:317).
- Every output call reclaims *all* processed buffers but enqueues at most one replacement: [openal_audio_out.cpp:121](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:121), [openal_audio_out.cpp:136](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:136). Therefore, if two buffers became processed during one late period, queued depth drops by one. Normal one-in/one-out cadence does not rebuild it.
- `BUFFER_QUEUE_THRESHOLD` says “queue more buffers” but is never used: [openal_audio_out.cpp:56](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:56).
- If no buffer ID is available, the current guest block is silently discarded by the `if` at [openal_audio_out.cpp:137](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:137).
- Once stopped, recovery merely calls `alSourcePlay`; it does not restore the five-buffer safety margin: [openal_audio_out.cpp:151](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:151).
- There is only one guest staging buffer and one readiness bit per port, so no backlog or catch-up queue exists above OpenAL: [audioout.h:120](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/audioout.h:120), [audioout.cpp:179](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/audioout.cpp:179), [audioout.cpp:550](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/audioout.cpp:550).
- Historical logs on this machine contain 21,455 explicit restarts across 13 older stereo sessions, always reporting `queued: 1`; examples begin at [shad_log.txt:17061](/home/ds2000/.local/share/shadPS4/log/shad_log.txt:17061) and end at [shad_log.txt:169484](/home/ds2000/.local/share/shadPS4/log/shad_log.txt:169484).

**Inference**

This is the best code match for “develops during a session, completely reset by restart.” Successive late calls can remove queue margin until the source repeatedly runs on one 5.3 ms buffer. Restart recreates the port and primes five buffers again. The measured process-local fault/render degradation provides a credible source of scheduling pressure: [shadps4-reload-stutter-20260828.md:12](/home/ds2000/couch/docs/research/shadps4-reload-stutter-20260828.md:12), [shadps4-reload-stutter-20260828.md:23](/home/ds2000/couch/docs/research/shadps4-reload-stutter-20260828.md:23).

It is not yet proven for the current 7.1 crackle. The current log filter is empty/Info: [config.json:85](/home/ds2000/.local/share/shadPS4/config.json:85), and Info is the default: [log.cpp:285](/home/ds2000/src/shadps4-dbg/src/common/logging/log.cpp:285). The underrun message is Debug, so current logs cannot confirm or exclude it.

**Smallest diagnostic**

For one play session, set the filter to `Lib.AudioOut:debug`, then leave running:

```bash
tail -F ~/.local/share/shadPS4/log/shad_log.txt |
  rg --line-buffered 'Audio underrun detected|Skipped .*duplicate'
```

Bursts coincident with crackle confirm full source starvation. For a decisive test including silent drops, the smallest probe is a once-per-second, per-port aggregate of `min_queued`, `processed>1`, `available_buffers.empty()`, and restart counts. Crackle with queue depth staying ≥4 and all three counters at zero kills this hypothesis.

### 2. High confidence: normal underrun does not repeat the previous buffer

**Verified**

- OpenAL looping is explicitly disabled: [openal_audio_out.cpp:560](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:560).
- Processed buffers are unqueued before the current buffer is queued: [openal_audio_out.cpp:121](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:121).
- If the guest has not supplied a block, the backend is not called at all: [audioout.cpp:179](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/audioout.cpp:179).
- The inactive SDL alternative explicitly fills missing output with silence, not repetition: [SDL_audio.c:1206](/home/ds2000/src/shadps4-dbg/externals/sdl3/src/audio/SDL_audio.c:1206), [SDL_audio.c:1230](/home/ds2000/src/shadps4-dbg/externals/sdl3/src/audio/SDL_audio.c:1230).

**Inference**

The earlier music loop during the game wedge is not explained by the normal host underrun path. It more likely originated upstream—the guest repeatedly submitted identical audio, or its music sequencer continued while the Main port stopped. Main and BGM have separate sources and output threads, so asymmetric starvation is possible; repetition itself is not implemented here.

**Smallest diagnostic**

A diagnostic build should record a lightweight sequence number or hash for submitted Main and BGM blocks. Repeating input hashes during the loop proves the repetition arrived from the guest.

### 3. Medium confidence: clipping is possible, but poorly fits the restart signature

**Verified**

- The current session opens Main and BGM as native `Float_8CH`, 48 kHz, 7.1: [shad_log.txt:650042](/home/ds2000/.local/share/shadPS4/log/shad_log.txt:650042), [shad_log.txt:650044](/home/ds2000/.local/share/shadPS4/log/shad_log.txt:650044), [shad_log.txt:650049](/home/ds2000/.local/share/shadPS4/log/shad_log.txt:650049), [shad_log.txt:650051](/home/ds2000/.local/share/shadPS4/log/shad_log.txt:650051).
- `Float_8CH` is copied unchanged into `AL_FORMAT_71CHN32`; no clamp or mixing occurs inside the per-port conversion: [openal_audio_out.cpp:459](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:459), [openal_audio_out.cpp:599](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:599), [openal_audio_out.cpp:887](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:887).
- Main and BGM share one OpenAL device/context and are separate sources: [openal_manager.h:85](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_manager.h:85), [openal_audio_out.cpp:542](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:542).
- OpenAL Soft defaults to no limiter for float output: [alc.cpp:1704](/home/ds2000/src/shadps4-dbg/externals/openal-soft/alc/alc.cpp:1704).
- Per-channel guest volumes are collapsed to the maximum channel gain: [openal_audio_out.cpp:182](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:182). `sceAudioOutSetVolume` also uses `*vol` for every flagged channel rather than indexing the volume array: [audioout.cpp:711](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/audioout.cpp:711).

**Inference**

Main+BGM summing, followed by PipeWire’s stereo fold, can exceed full scale. That fits “worse on loud speech/music.” The volume handling can also defeat intended per-channel attenuation. But clipping alone does not explain a persistent condition cleared by restart unless guest port gains or voice/mixer state change and remain wrong during the session.

**Smallest diagnostic**

While crackle is present, reduce the emulator volume slider to 50%. It is applied before OpenAL mixing and polled every 50 ms: [openal_audio_out.cpp:382](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:382). Immediate disappearance at 50% and return at 100%, without underrun-counter changes, strongly supports clipping.

### 4. High confidence negative: the Spotify S16+dither failure is not reproduced here

**Verified**

- OpenAL Soft defaults its device format to float: [devformat.h:55](/home/ds2000/src/shadps4-dbg/externals/openal-soft/core/devformat.h:55).
- Its Pulse backend requests `PA_SAMPLE_FLOAT32NE`: [pulseaudio.cpp:980](/home/ds2000/src/shadps4-dbg/externals/openal-soft/alc/backends/pulseaudio.cpp:980).
- Dither remains disabled for float output: [alc.cpp:1670](/home/ds2000/src/shadps4-dbg/externals/openal-soft/alc/alc.cpp:1670).
- The 7.1 channel orders agree: shadPS4 uses FL, FR, FC, LFE, rear L/R, side L/R: [audioout.h:110](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/audioout.h:110); the Pulse map uses the same order: [pulseaudio.cpp:237](/home/ds2000/src/shadps4-dbg/externals/openal-soft/alc/backends/pulseaudio.cpp:237).

**Inference**

A fixed format or map error should be present immediately and is a very poor match for restart-cleared degradation.

**Smallest diagnostic**

While playing:

```bash
pactl list sink-inputs |
  rg 'Sample Specification|application.name|media.name'
```

`float32le 8ch 48000` kills the S16/dither hypothesis at the OpenAL→PipeWire boundary.

### 5. Low confidence: OpenAL errors can permanently shrink the usable buffer pool

**Verified**

- A buffer is restored to `available_buffers` only when `alGetError()` reports success; otherwise processing stops: [openal_audio_out.cpp:125](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:125).
- A buffer ID is removed before `alBufferData` and `alSourceQueueBuffers`, and neither operation’s result is checked or restores the ID: [openal_audio_out.cpp:137](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:137).

**Inference**

Any real AL error can permanently reduce capacity until the port/process is recreated. This fits accumulating state and restart recovery, but there is no evidence that AL errors occurred. An unqueue failure could also leave old processed buffers queued and make the subsequent `alSourcePlay` replay them—the only host-side route found that could resemble the earlier loop.

**Smallest diagnostic**

Count AL errors after unqueue, buffer upload, and queue operations, alongside `available_buffers.size()`. Stable size and zero errors throughout crackle kill this branch.

### 6. High confidence: no direct FPS/presenter timing coupling; indirect contention remains

**Verified**

- Audio timing comes only from `buffer_frames/sample_rate`: [audioout.cpp:167](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/audioout.cpp:167), [openal_audio_out.cpp:244](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/openal_audio_out.cpp:244).
- Vblank timing is confined to the presenter: [driver.cpp:339](/home/ds2000/src/shadps4-dbg/src/core/libraries/videoout/driver.cpp:339).
- The audio thread requests no priority or realtime scheduling: [audioout.cpp:161](/home/ds2000/src/shadps4-dbg/src/core/libraries/audio/audioout.cpp:161). Its host thread is created with default pthread attributes: [thread.cpp:29](/home/ds2000/src/shadps4-dbg/src/core/thread.cpp:29).
- Linux realtime setup is unimplemented: [thread.cpp:75](/home/ds2000/src/shadps4-dbg/src/common/thread.cpp:75).
- `-f true` is fullscreen, not a 60-fps unlock: [main.cpp:78](/home/ds2000/src/shadps4-dbg/src/main.cpp:78). The installed Bloodborne 60 FPS entries currently say `isEnabled="false"`: [Bloodborne.xml:458](/home/ds2000/.local/share/shadPS4/patches/shadPS4/Bloodborne.xml:458), [Bloodborne.xml:624](/home/ds2000/.local/share/shadPS4/patches/shadPS4/Bloodborne.xml:624).

**Inference**

There is no direct frame-rate/audio-clock coupling. An actual 60-fps mod can still increase contention and expose the queue defect because the audio producer is ordinary `SCHED_OTHER`. The cited launcher argument itself does not enable that mod.

**Smallest diagnostic**

First verify which FPS patch/mod is actually applied. Then compare per-minute queue-health counters at 30 versus 60 FPS in the same area. Correlation with the existing once-per-second fault census would test whether the known process degradation is the trigger rather than merely a coincident condition.