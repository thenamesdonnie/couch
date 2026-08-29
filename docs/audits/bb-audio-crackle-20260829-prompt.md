# Lens: Bloodborne audio crackle under shadPS4 (29 Aug 2026)

You are reviewing the shadPS4 emulator source at `~/src/shadps4-dbg` (a 0.17.0
tag plus local patches, branch `tc-gc-probe`). Read-only. Never edit, never
commit, never run `systemctl`, never start or stop anything. The machine is a
live TV console.

Findings only, with file:line. No architecture summaries, no praise. Separate
what you verified in code from what you are inferring.

## The symptom, from the user

- Bloodborne audio "goes crackly", **most noticeable on people talking and on
  louder music**. Quiet passages are fine or less affected.
- **It clears completely on an emulator restart.** It does not come back
  immediately after; it develops during a session.
- It was previously associated with one specific boss fight (Darkbeast Paarl,
  an electrically-themed boss with dense loud audio). That boss is now dead so
  the trigger is not reproducible on demand.
- A related earlier event during a different boss: **the music looped/repeated
  and other sounds were drowned out**, coinciding with the game wedging.

## Known configuration on this box

- The emulator opens **7.1** (`Float_8CH` on both audio ports). **PipeWire folds
  it to stereo**, deliberately: the fold was moved out of SDL because SDL's fold
  puts LFE in at full level and LFE is mastered ~10dB down in this game.
- Output goes to a soundbar over **eARC**.
- Prior art on this same machine, different producer: a crackle on the Spotify
  path was root-caused to **16-bit output with dither**, fixed by forcing a
  float (F32) format. So the downstream chain has a demonstrated sensitivity to
  sample format, though that was a different application.
- The launcher passes the Bloodborne **60fps unlock** (`-f true`).

## The strongest clue, and what I want you to weigh

"Clears on restart, develops during a session" is **process-local accumulating
state**, not a fixed configuration error. A wrong channel map or a wrong sample
format would be wrong from the first second and would not be fixed by a
restart.

Note there is a separately documented, independently measured degradation on
this build with exactly the same signature: guest write-fault rates and texture
cache behaviour that worsen during a session and reset on restart (see
`~/couch/docs/research/shadps4-reload-stutter-20260828.md` if reachable; if not,
take it as given). So one live hypothesis is that the crackle is **not an audio
bug at all** but the audible symptom of the audio thread missing its deadline as
the process degrades, i.e. buffer underruns.

Test that hypothesis honestly against the code, and say if it does not hold.

## Specifically worth attacking

- The audio output path: buffer sizing, the ring/queue between the guest audio
  port and the host sink, and what happens on **underrun**. Does it insert
  silence, repeat the last buffer, or drop? A repeated buffer on underrun would
  explain "the music looped and repeated" exactly.
- Whether anything in that path **grows or leaks** over a session: queue depth,
  allocated ports, resampler state, accumulated latency.
- Sample-format and channel handling for `Float_8CH`, including any conversion
  or mixing step, and whether it can **clip**. Clipping would explain "worse on
  speech and loud music" and would get worse as more voices sum.
- Any place where audio timing is derived from the frame rate or the presenter,
  which would couple it to the 60fps unlock and to render-thread stalls.
- Thread priority/scheduling of the audio thread relative to the render and
  guest-fault paths.

Rank by confidence. For each, give the smallest diagnostic that would confirm or
kill it on a live session, since the user can reproduce this only by playing.
Cheap diagnostics that can be left running are worth more here than clever ones.
