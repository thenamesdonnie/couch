# couchd stage 3 — decision record: gamescope PARKED (4 Aug 2026)

Status: /build research complete; decision is PARK, not GO. This file
exists so the next session doesn't re-derive it. Full findings in the
session's research pass; essentials below.

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
