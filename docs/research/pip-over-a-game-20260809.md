# A show in the corner while a game runs — what's actually possible

Written 9 Aug 2026, answering "can we do our own version, has anyone done
it". Short answer: yes, and yes. gamescope has a compositing plane built for
exactly this, Valve's own feature request for it names our use case, and it
is alive in the tree we already built. It also means one claim in
`docs/couchd-stage3-design.md` is wrong and is corrected there.

## The mechanism: gamescope's external overlay plane

An application opens an X window inside gamescope's nested Xwayland and sets
one property on it:

    GAMESCOPE_EXTERNAL_OVERLAY = 1

gamescope then composites that window as **its own plane, above the game**.
Verified in our own checkout (`~/src/gamescope`, tag 3.16.25, tip commit
`17baf4a` of 20 Jul 2026), not taken from the web:

* `src/steamcompmgr.cpp:1111` defines the property.
* `:7819` interns the atom; `:4846` reads it off any window; `:6075` watches
  for it changing at runtime, so a window can become an overlay and stop
  being one while it lives.
* `:2673-2683` paints it, ahead of the Steam overlay plane, gated on the
  window's own opacity and on a ConVar (`paint_external_overlay_plane`,
  default true) that can turn the whole plane off live.
* It is painted with `PaintWindowFlag::NoScale` — **unscaled, at its own
  size and position**. Which is the entire feature: make the window
  480x270 in a corner and that is what lands on screen over the game. This
  is picture-in-picture, not a fullscreen overlay we have to be clever about.
* `:2680` lets it take input focus and updates touch scaling for it, so it
  can be interactive rather than just a picture, if we ever want that.

The important structural point for this box: it is a **plane**, not a window
restacked over a fullscreen game. Nothing is asking xfwm4 to composite
anything, and the game is not sharing a stacking order with a video player.
That matters here more than most places, because putting a window over a
live fullscreen game is the exact move that has already wrecked this box
twice - Big Picture left mapped behind a game gave us "Steam says 60, feels
20", and toggling xfwm4 compositing under a live game black-screened it.
The external overlay plane sidesteps both, because gamescope owns the game's
surface and ours as textures and never involves the outer X server.

## Has anyone done it

Yes, and the feature exists *because* someone asked for this.

* **ValveSoftware/gamescope#288, "External application overlay"** is the
  original request, and its stated use cases lead with "streaming services
  to do picture-in-picture while you play games", followed by clan chat and
  voice-channel status. The design ask was explicitly that it "needs to be
  agnostic in usage so it would be possible for most applications to draw
  their own overlay". So this is not us bending a mechanism to a new purpose;
  it is the purpose.
* **mangoapp** (MangoHud's gamescope companion) is the reference consumer
  and sets the atom itself - `src/main.cpp:619` in our tree says exactly
  that: "We no longer need to set GAMESCOPE_EXTERNAL_OVERLAY from steam,
  mangoapp now does it itself".
* **Discover** (a Discord overlay for the Steam Deck) tried to use the same
  layer, which is how the contention below got noticed.

**The one reported regression does not apply to us.** MangoHud#775 (May
2022, commit `74e83c0`) is that on Steam Deck, mangoapp is started with the
session and never releases the overlay layer, so nothing else can draw into
it. That is a property of *SteamOS's session configuration*, not of the
mechanism. We would be running nested gamescope ourselves, per game, and
mangoapp only runs if we start it. The layer is ours.

## What it would take here, honestly

This is a PROJECT, not a weekend, and most of the cost is not the overlay.

1. **It requires adopting stage 3 for at least one game.** gamescope is
   parked; `tools/gamescope-wrap` is written and tested and nothing is wired
   to it. Nothing about the overlay is reachable without a game actually
   running nested.
2. **The client has to live on gamescope's nested display.** mpv is the
   obvious first client - one window, one `DISPLAY`, one `xprop` to set the
   atom. Kodi is much harder now that it is a Flatpak, because pointing it
   at a nested X server crosses the sandbox. Do not start with Kodi.
3. **The Steam overlay problem is unchanged and is the real risk.** The
   spike already found that for any Vulkan-swapchain backend (which nested
   SDL is), gamescope strips `gameoverlayrenderer.so` from the children's
   LD_PRELOAD - `steamcompmgr.cpp:8248-8266`. `steam-input-guard` depends on
   the Steam overlay. So wrapping a Steam title has knock-on effects on the
   enforcement window that have nothing to do with PiP and everything to do
   with whether stage 3 is adoptable at all. That question is unanswered and
   is the actual gate.
4. **Audio is still unsolved and is common to every route.** Two sources,
   one soundbar. Most likely the show goes to the headphones (which follow
   the TV since 8 Aug) and the game keeps the room.
5. Frame-pacing cost of the extra plane is unmeasured. On AMD it may land on
   a hardware overlay plane and cost approximately nothing, or it may force
   composition. Measure before believing either.

A first experiment that proves the whole idea, with no Steam and no couchd
involvement: run glxgears (or Hollow Knight, the spike's chosen first game)
under `gamescope-wrap`, start `mpv` on the nested display, set the atom with
`xprop`, and see whether a video lands in the corner and what it costs.
That is an evening, and it either works or it does not.

## The routes we are not taking, and why

* **A window over the game on bare X11.** This is what the wider internet
  does and it is the thing that has already bitten us twice. Exclusive
  fullscreen bypasses the window manager; "always on top" is not reliably
  above it. Not on this box.
* **The TV's own Multi View.** Researched the same day. Dual HDMI needs the
  Alpha 11 processor - G4/G5/M5 only, not our C5 - and on a C5 the second
  source comes from a short whitelist (screen share, AirPlay, camera,
  YouTube) that does not include Jellyfin or Kodi. Two things survive:
  YouTube in the corner for free, and phone screen share, which routes
  around the whitelist because the TV only sees a cast. Still worth the
  five-minute manual test (`tools/tv-multiview-probe`), because if it works
  it costs the PC nothing. LG also lists 4K high frame rate as unsupported
  content in Multi View, which is a warning about our 4K120.
* **The phone, on its own.** Zero work, available tonight, and genuinely
  most of the value: the remote is already a full client of the library.
  Worth saying out loud before anyone builds a compositor feature.

## Sources

* ValveSoftware/gamescope#288 — External application overlay (the request,
  and the PiP use case in its own words).
* flightlessmango/MangoHud#775 — the Deck-only overlay-layer contention.
* Our own tree: `~/src/gamescope` at `17baf4a`, and
  `docs/gamescope-spike-20260806.md` for everything already measured here.
