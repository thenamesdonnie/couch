# The realm of possibility

Written 5 Aug 2026, evening of the first flip, at Donnie's request:
"assuming everything works, what does this unlock?" Grounded in what is
actually built or already planned; each item is tagged with what it
rides on and how hard it is (EASY = days, PROJECT = a focused week or
two through /build, RESEARCH = worth a spike before believing in it).
Nothing here is committed work; it is the menu.

## What we actually have (the assets)

The unlocks below all fall out of six capabilities, so name them first:

1. **One brain with eyes** - couchd sees the pad, every process, Kodi,
   X11, Steam's own logs, the /tmp contracts, and soon the TV; and it
   can act on all of it with effect verification and instant rollback.
2. **Proof-before-trust machinery** - the shadow corpus + differ mean
   ANY new automation can run as a proposal stream first and only get
   hands when the evidence says it decides correctly. This is rare;
   almost all home automation acts blind on day one.
3. **Zero-cost pause** - SIGSTOP suspend parks a game at literally zero
   CPU with its last frame captured. Consoles do not have this; they
   keep games resident and hot.
4. **Input ownership** (stage 2, built, uninstalled) - the pad becomes
   a stream we own end to end: rewritable, filterable, injectable.
5. **Compositor control** (stage 3, unblocked by the 9070 XT) -
   gamescope makes every window a texture: scale it, fade it, place it,
   overlay it, at VRR/HDR quality once the LG lands.
6. **A second screen with a full API** - the phone app is not a remote,
   it is a client of everything the brain knows.

## Tier 1 - rides on what is live NOW (plus the polish track)

- **Quick Resume, better than Xbox's.** (EASY-PROJECT) Multiple games
  suspended AT ONCE, each at zero CPU, each with its freeze-frame in
  the switcher; picking one thaws it in about a second. The mechanism
  already exists per-game; the work is bookkeeping (per-appid frozen
  sets, RAM budget guard - 32GB fits maybe 3-5 parked games, zram
  swap stretches it since a frozen game's pages compress and never
  wake), plus switcher rows for every parked session. This is the
  flagship: no PC does this, and the parts are all on the shelf.
- **One "Continue" row for the whole room.** (EASY) couchd is the only
  thing that knows BOTH the paused game and the half-watched episode.
  A single Kodi home row mixing resumable sessions of any kind - game
  freeze-frames next to episode thumbnails - is just plumbing between
  what pause-snap and Jellyfin already know.
- **Per-game room profiles.** (EASY) couchd knows the appid at launch:
  auto-apply a frame cap, a lights scene (light-watch already does
  films), a volume profile, and later the LG's picture mode per game.
  One config file, applied on transition, restored on suspend.
- **Couch notifications.** (EASY) couchd's attention flag + the phone =
  push when a download lands, when the pad battery is low mid-session,
  when a Jellyseerr request needs approving. On the LG: native toasts
  on the TV itself for the gentle ones.
- **Save-game safety net.** (EASY-PROJECT) On every suspend, rsync the
  game's save directory into a dated snapshot (suspend is the perfect
  hook: the game is frozen, files quiescent). "Rewind my save to
  before last night" becomes a switcher long-press. Needs a per-game
  save-path map (Proton prefixes make this mostly mechanical).

## Tier 2 - rides on the transitions flip + stage 2 install

- **Choreographed transitions everywhere.** (lands WITH the flip) The
  curtain becomes couchd's opening move: freeze, curtain, restack,
  fade, every time, from every trigger (PS button, phone, Kodi tile).
  The console stops ever showing its desktop underwear.
- **The pad as a status object.** (EASY once stage 2 is in) The
  DualSense lightbar and haptics are writable: battery colour on
  connect, a pulse when a download finishes, red while the fault rig
  runs. Silly, delightful, cheap.
- **A richer gesture language.** (PROJECT) Stage 2 owns every button,
  not just PS: chords (PS+triangle = screenshot), per-context remaps
  (media controls while Kodi plays), turbo/accessibility modes. The
  same shadow-first discipline applies: new gestures run as proposals
  in the corpus before they act.
- **Phone-to-game text input.** (PROJECT) The virtual pad can type: a
  game asks for a name, the phone keyboard appears, keystrokes arrive
  as pad/keyboard events. Ends the on-screen keyboard stick-dance.
- **Multi-pad arbitration.** (PROJECT) Second controller: who owns
  Kodi, who owns the game, guest mode that cannot invoke the switcher.

## Tier 3 - rides on the 9070 XT + gamescope (stage 3) + the LG

- **True crossfades and scaling.** Game-to-Kodi as a compositor fade,
  not a restack; FSR upscaling per game (run at 1440p, present at 4K)
  as a per-game profile knob; VRR/HDR done properly.
- **Picture-in-picture, both directions.** (PROJECT, one ruling) Kodi
  video in a corner over a running game (podcasts/football while
  grinding), or a LIVE game thumbnail while browsing. The catch is
  design, not tech: a game in PiP is not suspended, so it burns
  CPU/GPU - it needs its own room-state with the frame limiter dropped
  to something tiny. gamescope's per-window FPS limits are exactly
  this shape.
- **A couchd HUD.** (PROJECT) An overlay couchd owns, drawn over
  anything: volume, pad battery, "suspending...", incoming request
  approvals. Independent of Steam's overlay and Kodi's UI.
- **"Continue on the phone."** (PROJECT) Suspend on the TV, resume the
  same session as a Sunshine/Moonlight stream on the phone in bed.
  All the pieces exist (suspend, Sunshine, the phone app); the work is
  the handoff choreography and input rerouting.

## Tier 4 - the horizon (worth spikes, not promises)

- **True game hibernation.** (RESEARCH) CRIU checkpoint of a frozen
  game's process tree to disk: survive a reboot, park a dozen games,
  resume days later. Proton trees are hostile territory for CRIU
  (GPU state, futexes, dmabuf) - a weekend spike would tell us if even
  one well-behaved native game can do it. If it works at all, it is a
  headline feature no platform has.
- **The couch shell.** (RESEARCH/stage 4) The phone app's codebase
  rendered ON the TV as the home screen - one UI language for phone
  and television, Kodi demoted to a media engine behind it. This is
  the "own compositor" endgame the charter already names as stage 4.
- **Room profiles / multi-user.** (PROJECT, needs rulings) Whose pad,
  whose saves, whose watchlist, whose Steam account; the switcher and
  continue-row filtered per person.
- **The strangler pattern as a service.** (PHILOSOPHY) The
  shadow-then-flip machinery is not gesture-specific. Anything scary
  we ever want to automate on this box - disk housekeeping, service
  healing, download scheduling - can be introduced the same way:
  observe, propose into a corpus, diff against what the human did,
  flip one responsibility when the evidence is clean. That discipline
  is the actual asset this year built.

## What to pick first

The compounding order, if the acceptance and deploy-day go clean:
Quick Resume (it multiplies the value of everything else, and it is
mostly bookkeeping), then the Continue row (visible daily, trivial),
then per-game profiles, with the transitions flip carrying the
choreography in parallel. PiP and the HUD wait for stage 3 by
necessity; hibernation gets one honest spike before anyone falls in
love with it. Big items go through /build (research-rooted, per the
house rule); everything acts-on-the-box goes shadow-first, because
that is now simply how this project does things.
