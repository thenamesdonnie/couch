# Console research — triaged. What I built, and what needs you.

Written overnight, 10 Aug 2026, against
`docs/research/console-behaviour-2026-08.md` (811 observations from 12
web-backed researchers) and `docs/research/console-undocumented-sol-20260810.md`
(285 from sol, recall not research).

Donnie's instruction: *"sort the list in to no brainers and stuff that you want
to ask me about and build the no brainers and i'll take a look at the rest when
i wake up"*.

## The rule I sorted by

**No-brainer** = small, reversible, obviously right, nobody would argue for the
current behaviour, and it does not need your sudo, a flip, a ruling, or the
television to verify.

**Ask** = anything you would NOTICE and might not want, anything touching
couchd's decisions or the pad or the enforcement window, anything needing sudo
or a flip, anything that is a project, and anything where two reasonable people
would choose differently. Those are yours, not mine.

I have been deliberately strict. Several things the synthesis filed under
"cheap" are below in ASK, because cheap to build is not the same as obviously
right.

---

## Built tonight

**Reduce motion in the phone remote.** The app had a deliberate motion pass and
respected `prefers-reduced-motion` nowhere, which is the one accessibility
setting iOS actually exposes to Safari. Transitions collapse to 1ms rather than
0 so anything waiting on `transitionend` still fires, movement transforms are
dropped, opacity cross-fades are kept because they carry state without
vestibular cost, and the picture-in-picture DRAG is untouched - reduced motion
is about incidental animation, not about direct manipulation you are driving
with your own finger.

**Two audits, findings below.** Measuring is a no-brainer. Acting on what they
found is not, so both are in ASK.

---

## Findings from the audits

### Text size — the skin is failing its own floor in four places

The research puts minimum body text at 26px at 1080p (52px at 4K). The skin
designs in 1920x1080 space, so 26 is the number to beat.

**Our own scale passes.** `Couch_Caption` 28, `Couch_Label` 32, `Couch_Emph` 36,
`Couch_Header` 44, `Couch_Title` 64, `Couch_Display` 90.

**Eleven inherited Copacetic fonts are under it**, and four are text you
actually read across the room:

| size | font | where it hurts |
|---|---|---|
| 20px | `Grid_Info_Small` | grid metadata |
| 25px | `Description` | plot and synopsis text - the worst one |
| 25px | `Grid_Info` | grid metadata |
| 25px | `Player_Time` | the seek bar clock |

The other seven are `Debug_Label` (13), `Unwatched_Indicator` (17), `font13`
(21), `Visualisation_Time` (22), `PVR_Channel2` and `PVR_Time` (22, and we have
no PVR), and `LoginScreen_Info` (25). None of those matter.

Why this is ASK and not a no-brainer: text size on your own television is a
taste decision, it changes every screen at once, and it needs your eyes at
viewing distance rather than my arithmetic. The patch is four numbers.

### The E-runbook still cannot certify the thing it now covers

Separately from the console research, and worth your attention because it gates
stage 2: no rung of E1 drives inputproc and a live couchd **together**. The
supervisor wire is tested end to end in isolation and has never met the real
pad. The runbook says so now rather than implying coverage it does not have.

---

## Ask me — ranked, most valuable first

### 1. Controller-disconnect handling
Freeze the game when the active pad dies, show "reconnect your controller",
resume on re-association. Certification MANDATES this on both consoles and
essentially no PC game does it. couchd already knows the pad is gone and
already knows how to freeze a game, so the parts are on the shelf.
**Why I did not just build it:** it decides to freeze your game. That is a
behaviour change you would notice at the worst possible moment if I got the
detection window wrong, and this box has a documented Bluetooth fault that
drops the pad spuriously.

### 2. Wrap versus bump at the end of a list
Consoles do NOT wrap. Sony shipped an update whose only navigation change was
making the dead-end sound louder. We wrap in some places and bump in others.
Picking one, and giving the bump a sound and a pad rumble, is cheap.
**Why ask:** it is muscle memory, and it is yours. Also `ff_memless` is loaded,
so a rumble on the bump is available if you want it.

### 3. The notification matrix
Category x context: what may interrupt during a film, during a game, on home.
Display duration, position, a session-scoped do-not-disturb that clears on
restart, and a small unsuppressible tier.
**Why ask:** every cell is a judgement about your evening, not mine.

### 4. Two idle timers, split by activity
Consoles time out differently for gameplay and for media, driven by actual
playback state rather than input idleness, with a cancellable 30-second warning.
Ours does not distinguish.
**Why ask:** the durations are yours, and it can turn your TV off.

### 5. Pad status surfacing
Three-bar battery rather than a percentage (consoles never show a percentage),
connect and disconnect toasts, a repeating low-battery warning that fires even
during a fullscreen game, charging fault states, lightbar dimming during films.
**Why ask:** "never a percentage" is console convention, and you may simply
prefer the number.

### 6. The error registry
Stable short IDs, one plain sentence each, rendered identically on TV and
phone, never a raw errno. One cause, one device, one sentence.
**Why ask:** it is a cross-cutting change to every failure path, so it is a
project rather than an evening, and the wording should sound like you.

### 7. The overnight maintenance window
A ~03:30 `WakeSystem=true` timer: Steam depots, apt and flatpak, Jellyfin and
Bazarr scans, a disk-monitor pass, then back to sleep, with an on-screen record
of what actually completed. Xbox does exactly this at 0.5W.
**Why ask:** it wakes your machine while you sleep, and it needs sudo.

### 8. Make resume look like nothing happened
Hold a frame over the DPMS and modeset ugliness, and force a clean restart if
nothing renders N seconds after a resume request. `tools/curtain` was built for
this and is still unwired - and its 7 tests are still failing.
**Why ask:** it sits directly on the display path, which bit us twice tonight.

### 9. Cache artwork locally and pin it
Offline should look identical to online. Sony got this publicly wrong.
**Why ask:** it is a real chunk of work in the app and it costs disk.

### 10. A read-only display state page
What the sink actually claims, with unsupported modes greyed out and the reason
given. Tonight would have been much shorter with this.
**Why ask:** it is additive and safe, but it is a new feature rather than a
fix, and you may want it somewhere specific.

Then, lower down and genuinely projects: the overlay over a live game (which is
the PiP work, gated on stage 3), suspend-then-hibernate as a Quick Resume
analogue, learned active hours, the recovery ladder, a single Manage
destination, a per-game hub, fault injection in couchd, compositor zoom, the
touchpad as a real pointer, and a critical-section concept that disables
interrupting shortcuts while a write is in flight.

## Explicitly not worth it

From the research, and I agree: matching 0.5W standby, multi-game Quick Resume,
per-game hover music, adaptive triggers from the shell, chat transcription and
the social layer, a full factory-reset flow.

## What the research itself is missing

The critique named 24 gaps and two structural caveats, both stated openly in
§22 of the main document: the **accessibility pass was truncated mid-report**,
and the **accounts** and **refusals** passes were not available in full, so
their material is only partly reflected. The biggest content gap is **text
entry and search** - nothing on the on-screen keyboard, which is the single
most painful thing a normal person does on a console, and something this box
has a phone in its hand to solve better than either console does.

Worth a second pass, and cheap to run now the fleet pattern works.
