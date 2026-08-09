# couchd stage 3 — decision record: gamescope PARKED (4 Aug 2026)

Status: /build research complete; decision is PARK, not GO. This file
exists so the next session doesn't re-derive it. Full findings in the
session's research pass; essentials below.

## REASSESSED 9 Aug 2026 — the park is stale, re-open it

The verdict below is sound reasoning about a box that no longer exists.
Three of its four pillars have gone, and the fourth is smaller than it
looked. Nothing here says ADOPT; it says the parking decision cannot carry
its own weight any more and the evidence gate in §6 should be run.

**Gone: the display.** "The TV is 1080p60 SDR with no VRR (its 4K modes are
30Hz and below)" is now an LG C5 OLED at 4K120 with VRR and HDR. That is
revisit trigger 1 verbatim, and trigger 1 says it "flips the gains column
immediately".

**Gone: the driver family.** The 4070 is out and an RX 9070 XT is in.
gamescope's home platform is AMD. And bug #2171, cited as "open and
unowned", is NVIDIA-only - alpha blending on overlay layers, reported on an
RTX 4090 - so it does not reach us. Worth noting it is exactly the failure
we would have hit: transparent overlay planes rendering as solid black.

**Gone: the packaging risk.** "Noble has no gamescope package... a source
build needs wayland >= 1.23.1 and pixman >= 0.43.0" was solved by the 6 Aug
spike. 3.16.25+ is built at `~/src/gamescope/build/src/gamescope` and I ran
it today, headless, on the 9070 XT.

**Smaller than documented: the guard.** The verdict says "Steam Input +
overlay are broken by default in nested mode... and our guard depends on
both". Reading `legacy-mirror/steam-input-guard` rather than the summary:

  * its DETECTION reads `~/.steam/.../logs/controller_ui.txt`, a log the
    Steam CLIENT writes about controller UI routing. What gamescope strips
    is `gameoverlayrenderer.so` from the GAME's LD_PRELOAD. Those are not
    the same thing, and the log should survive;
  * its ACTUATOR - the synthetic guide press - has been disabled since
    7 Aug (`1ac3ab0`) after it walked into Steam's power menu and suspended
    the machine mid-game, and the code's own note says "the mechanism also
    has never demonstrably worked: every close_steam_menu effect check
    tonight verdicted MISSED".

So the guard's dependency on the in-game overlay is largely theoretical
today. **Steam INPUT in nested mode is still a real unknown** and is
separate from the overlay question; do not let this paragraph blur them.

**Still standing, unchanged:** the three sites keying on `steam_app_*` (§2
enumerates every one, and they are small), no prior art for a Kodi-first
gamescope setup, and every experiment in §6.

**Also new since the park:** picture-in-picture over a game is proved
working on this box - `tools/pip-gamescope-rig` composites an overlay plane
above the game at an arbitrary rectangle and moves it, headless, and it
passes. That was the thing this document said gamescope could not do (see
the correction under trigger 4). It is a gain in the column that was empty.

Recommendation: run §6's experiments 4, 5 and 7 with Donnie - they are
brief - and let the answers decide. Experiment 5 (Steam Input and the
overlay in nested mode for a real Steam title) is the one that still gates
everything.

## The verdict in one paragraph

On this hardware there is nothing to win. The TV is 1080p60 SDR with no
VRR (its 4K modes are 30Hz and below), the 4070 renders natively, and
frame pacing addresses no problem the audit found. Gamescope's entire
gain here is "multi-window games collapse into one window". Against
that: three code sites key on the `steam_app_*` window class and would
silently regress under a `gamescope`-class window (steam-input-guard:272
= audit invariant 3, screen.js:271 and :291 = the phone panic button
degrading to a raw raise); Steam Input + overlay are broken by default in
nested mode (the LD_PRELOAD unset/reset dance, ScopeBuddy's reason to
exist) and our guard depends on both; noble has no gamescope package (the
3v1n0 PPA ships 3.16.19 but swaps system libwayland/libpixman on the
living-room box; a source build needs wayland >= 1.23.1 and pixman >=
0.43.0 pulled as meson subprojects — noble has neither); driver-family
rendering bug #2171 is open and unowned; and there is zero prior art for
a Kodi-first gamescope setup anywhere. Bad trade against the prime rule.

## Revisit triggers

1. TV upgrade to 4K120 / VRR / HDR — flips the gains column immediately
   (that's the actual reason gamescope exists for NVIDIA owners).
2. Ubuntu ships gamescope in-repo (packaging risk disappears).
3. Stage 4 — where "one compositor owning the screen" is the goal and
   gamescope/cage become prior art to study, not a wrapper to bolt on.
4. (Added 4 Aug, post-parking) Donnie's stated appetite for
   picture-in-picture and animated Kodi<->game transitions — features this
   parking decision did NOT weigh, because they aren't achievable on bare
   X11 either way. They are native stage-4 outcomes (surfaces the
   compositor owns can be scaled/faded freely), and gamescope-nested gets
   only partway (a scalable window, no PiP composition). If that appetite
   grows, it strengthens the case for stage 4, not for un-parking stage 3.

   **CORRECTED 9 Aug 2026: the "no PiP composition" half of that is wrong.**
   gamescope has a dedicated external-overlay PLANE - a window that sets the
   `GAMESCOPE_EXTERNAL_OVERLAY` property is composited above the game,
   unscaled, at its own size and position, which is picture-in-picture by
   construction. Verified in our own checkout, not inferred: see
   `docs/research/pip-over-a-game-20260809.md` for the source lines. So PiP
   is reachable from stage 3 and this trigger now cuts the other way - the
   appetite argues for un-parking stage 3, not only for stage 4. It does NOT
   change the gate: the Steam-overlay stripping in §6 is still what decides
   whether stage 3 is adoptable at all, and PiP rides on that being settled
   first.

## If resuming: the preserved recipe

- Pin **3.16.19** (predates the SDL-backend lifecycle regressions #2133 /
  #2139 / #2204 — nested-on-X11 always resolves to the SDL backend).
- NEVER: `-e`/`--steam` (broken, ScopeBuddy strips them), `-g` (keyboard
  grab + our SIGSTOP = grab held by a frozen client), setcap CAP_SYS_NICE
  (kills the Steam overlay the guard depends on).
- Integration shape: per-game launch option `scopebuddy -- %command%`
  (option (a)) — the ONLY reversible shape. steam:// launches can't be
  wrapped by game-launch (Steam spawns the game, not us); gamescope lands
  inside the reaper tree so game-pids/freeze/thaw survive unchanged.
- Pre-flight gates (30s each, before Steam is involved): glxgears renders
  in nested gamescope; gamescope EXITS when the child exits (the
  #2133/#2139 gate — if it lingers, stop, our session lifecycle can't
  survive it); `import -window root` isn't black (phone screen tab).
- First game: Hollow Knight (offline, fast, chaos-test baseline exists).
  Success = the 6 criteria + re-run of audit modes 1/5/6/8/9/12 under
  gamescope. Rollback = delete the launch option.
- ~/gamescope-deps.sh is WRONG as staged: missing libluajit-5.1-dev,
  libxcursor-dev, libx11-xcb-dev (hard failures), xwayland (runtime),
  libpipewire-0.3-dev + hwdata (wanted); its "all exist on 24.04"
  premise fails on wayland/pixman minimums. Fix before any build.

## Actionable regardless of gamescope (routed to todo)

The three `steam_app_*` class predicates (steam-input-guard:272,
screen.js:271, screen.js:291) are fragile identity assumptions;
focus_game already learned the pid-first lesson (matches _NET_WM_PID
first). Same treatment for those three when convenient — or they simply
dissolve when the relevant responsibilities cut over to couchd, whose
observation interface is pid-first by design (C24). Low urgency while
gamescope is parked.
