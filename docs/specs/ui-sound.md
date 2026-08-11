# Couch UI sound

Status: **in progress, 11 Aug 2026.** Donnie: "can we add sound effects please.
extrapolate."

This doc is the why. The what lives in the addon and the skin; those point here.

---

## 1. What it does for the product

The box is silent. Every other part of the Stagelight identity says "console" -
the tile row, the halo focus mark, the launch flourish - and then you press a
direction and nothing happens except pixels. On a TV across a room, sound is
half of what makes an interface feel like it responded to you: it confirms the
press landed even when your eyes are on the artwork and not the selector.

The goal is not "add beeps". It is a **family** of related cues where the
loudest thing in the set is the rarest, so the interface feels alive without
becoming a slot machine.

---

## 2. Where it plugs in (measured on this box, 11 Aug 2026)

Read straight out of Kodi's own settings definition
(`.../files/share/kodi/system/settings/settings.xml`), not the wiki:

| Setting | Value here | Meaning |
|---|---|---|
| `audiooutput.guisoundmode` | **1** | `AE_SOUND_IDLE` - GUI sounds play **only when playback is stopped**. Enum confirmed in-source: 1 = idle, 2 = always, 0 = off. |
| `audiooutput.guisoundvolume` | 100 | percentage, 0-100 |
| `lookandfeel.soundskin` | `resource.uisounds.kodi` | constrained to `<addontype>kodi.resource.uisounds</addontype>`, `allowempty=true` |
| `audiooutput.audiodevice` | `PULSE:Default` | PipeWire's pulse shim |
| `audiooutput.samplerate` | 48000 | |
| `audiooutput.passthrough` | **false** | no AC3/DTS passthrough, so no passthrough-vs-GUI-sound conflict |
| `audiooutput.streamsilence` | 1 | keep-alive; see the suspend note below |

**CORRECTION, and the reason this doc exists in this shape.** My first pass
concluded "no sound plays because `resource.uisounds.kodi` is not installed".
That was **wrong**: I looked in `/var/lib/flatpak` and the user addon dir, but
this Flatpak is installed per-user, and the addon is bundled inside it at
`~/.local/share/flatpak/app/tv.kodi.Kodi/.../files/share/kodi/addons/`.

So the honest finding, measured rather than reasoned: **GUI sounds already
work.** Capturing the HDMI monitor while driving navigation over JSON-RPC
caught four cursor cues and a select cue:

| event | measured peak | length |
|---|---|---|
| down / right (`cursor.wav`) | **-35.3 dBFS** | ~30 ms |
| select (`click.wav`) | ~-47 dBFS | ~220 ms |

The job is therefore **not** "add sound to a silent box". It is "replace Kodi's
generic stock pack with a designed set that belongs to this interface" - which
is what Donnie is really asking for, and a different build with different risks
(the old sounds must stop, the new ones must map to events this UI actually
has, and the set must be a family rather than five stock samples).

Because the setting takes a `kodi.resource.uisounds` addon, the sounds ship as
**our own resource addon** rather than a folder inside the skin - which also
keeps them versioned next to `script.couch.*` and `context.couch.*` instead of
being buried in a skin fork, and means a skin update cannot revert them.

### The schema, from Kodi's own bundled pack (not the wiki)

`resources/sounds.xml`, verbatim structure:

```xml
<sounds>
  <actions>
    <action><name>left</name><file>cursor.wav</file></action>
    <action><name>select</name><file>click.wav</file></action>
  </actions>
  <windows>
    <window>
      <name>notification</name>
      <activate>notify.wav</activate>
      <deactivate>out.wav</deactivate>
    </window>
  </windows>
</sounds>
```

Action names come from the keymap action list, window names from the window-ID
list. The file states plainly: **"Only wav files are supported"**. The addon
manifest needs `<extension point="kodi.resource.uisounds"/>` and an import of
`kodi.resource` (schema: `addons/kodi.resource/uisounds.xsd`).

Stock actions mapped: left, right, up, down, select, parentdir, previousmenu,
screenshot, error - plus the `notification` and `startup` windows.

### What the stock pack gets wrong for us

Measured from the bundled files:

- **Mixed sample rates** - 22050, 32000 and 44100 Hz, against our 48000 Hz
  output. Every one needs resampling on the way out.
- **Wildly inconsistent levels** - `notify.wav` and `out.wav` peak at **-1.0
  dBFS** while the cursor lands at -35 dBFS on the output. The rare sounds are
  the loudest, which is exactly backwards.
- **8-bit** cursor and click files. (They do play - that hypothesis was tested
  and rejected, they are audible in the capture.)
- Not a family: they are unrelated samples with no shared timbre.

The `guisoundmode = 1` default is already exactly the behaviour we want: **no
clicking over a film**, for free, without a single line of skin logic.

---

## 3. Calibration - measured on OUR content, not imported

Published loudness targets (EBU R128 -23 LUFS, ATSC A/85 -24 LKFS) are mastering
targets for broadcasters, not a description of what actually plays here. So the
reference was measured on the real files with `ffmpeg -filter_complex ebur128`,
three separate 3-minute windows across two different masters:

| Sample | Integrated | LRA | True peak |
|---|---|---|---|
| Silo S03E06 (4K HDR, E-AC3 5.1) @ 15:00 | -27.9 LUFS | 9.8 LU | -7.8 dBFS |
| Silo S03E06 @ 40:00 | -28.7 LUFS | 11.4 LU | -6.5 dBFS |
| Silo S03E05 (1080p, different master) @ 20:00 | -29.1 LUFS | 7.2 LU | -5.9 dBFS |

**Content on this box sits at roughly -28 LUFS integrated with true peaks around
-6 to -8 dBFS.** That is the anchor: the room volume is set so that -28 LUFS is
comfortable dialogue. UI cues are chosen relative to that, so they are audible
in a quiet room at that volume and never startle.

(Target levels per cue are filled in below once the research pass lands, so the
numbers are argued rather than picked.)

---

## 4. The capture rig (how any claim here gets checked)

Claims about sound are worth nothing without a measurement, so there is one:

    parec --format=s16le --rate=48000 --channels=2 \
          -d alsa_output.pci-0000_09_00.1.hdmi-stereo-extra2.monitor > cap.raw

**Probe validated before use**: a -20 dBFS 1 kHz tone was played and read back at
-23.0 dBFS RMS (exactly the RMS of a 0.10-amplitude sine), so the rig measures
level correctly rather than just detecting "something happened".

**A probe artefact worth knowing about.** The HDMI sink SUSPENDS when idle. I
tried to test whether the first sound after idle gets clipped, and measured two
identical 50 ms bursts at -24.6 dBFS - no clipping. That result is **void**:
opening the monitor source with `parec` itself moves the sink SUSPENDED -> IDLE,
so the capture woke the device and the cold-start case was never actually
tested. Recorded here so nobody quotes it later.

Cold-start clipping is therefore **unverified by measurement**, and is handled by
mitigation instead (keeping the device alive), plus a listen by ear.

---

## 5. Research findings

_(pending - two agents running: console/TV UI sound design practice + published
research on auditory feedback, and Kodi 21's exact sound mechanics.)_

## 6. Constraints and parameters

_(pending research)_

## 7. Ways this build could be wrong

Written before building, swept item by item at the end:

1. **Annoying.** The single biggest failure mode. A nav tick fires many times
   per second when scrolling a long A-Z grid; anything with a tail, a pitch that
   sticks out, or too much level becomes unbearable within a day.
2. **Machine-gunning.** Holding a direction scrolls fast. If Kodi overlaps or
   queues sounds rather than cutting them off, fast scrolling turns into a
   buzzsaw. Needs checking against Kodi's behaviour, not assumed.
3. **Plays over a film.** `guisoundmode=1` should prevent it. Must be verified
   with something actually playing, not reasoned about.
4. **First sound of the session missing** because the sink or the soundbar was
   asleep. See the void measurement above.
5. **Too loud / too quiet at the volume he actually uses.** Calibrated against
   measured content loudness, but the soundbar has its own processing.
6. **Latency.** If the cue trails the press it feels worse than silence.
7. **Wrong events.** Sounds on things that are not user-initiated (a row
   populating, a widget refreshing, art loading) read as the box malfunctioning.
8. **Breaks something else.** `lookandfeel.soundskin` is a global Kodi setting;
   the switcher, the YouTube window and the player OSD all share it. Changing
   audio settings on a box whose audio path took days to get right (eARC,
   4K120, mode-keeper) is not free.
9. **Survives a skin update?** Anything written into the skin folder reverts on
   a skin update - hence a separate addon.
10. **No way to turn it off.** There must be an obvious off switch, and it must
    be one Donnie can reach from the couch.
