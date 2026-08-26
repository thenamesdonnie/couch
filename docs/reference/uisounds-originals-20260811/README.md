# UI sound originals, 11 Aug 2026

Seven wavs that appeared in `kodi-addons/resource.uisounds.couch/resources/`
on 11 Aug 2026, untracked, undocumented, and with no `addon.xml` or
`sounds.xml` beside them - so Kodi could never have loaded them and nobody
has ever heard them on the TV. They are kept here because they are the only
record of that afternoon's design.

On 24 Aug 2026 they were measured off the wave and the design was rewritten
as parameters in `tools/make-uisounds`, which now generates the live set.
What was measured, and what carried over:

| sound  | length | tone            | original peak | now  |
|--------|--------|-----------------|---------------|------|
| cursor |   55ms | 1605 Hz         | -26 dBFS      | -16  |
| select |  150ms | 1184 Hz + octave| -20 dBFS      | -10  |
| back   |  170ms | 800 -> 668 Hz   | -22 dBFS      | -12  |
| in     |  380ms | 773 -> 1148 Hz  | -18 dBFS      |  -8  |
| out    |  400ms | 750 -> 469 Hz   | -21 dBFS      | -11  |
| error  |  130ms | 2098 Hz         | -20 dBFS      | -10  |
| launch |  750ms | 1512 -> 1934 Hz | -18 dBFS      |  -8  |

The shapes are unchanged. Three things are not:

1. **+10 dB, uniformly.** The whole set was too quiet to hear over the
   soundbar - the tick was 11 dB below the *stock* Kodi tick it was replacing.
   The lift is uniform because the internal balance was already right.
2. **An attack ramp.** Every original starts on a full-amplitude sine sample,
   which is a broadband click; through eARC into a real soundbar that reads as
   a pop in front of the note.
3. **A quiet harmonic** on the percussive sounds, which is roughly the
   difference between a beep and a note.

Delete this directory once the regenerated set has been lived with for a
while and nobody wants the old levels back.
