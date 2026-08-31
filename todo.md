# Couch — todo / resume

Phone-first web remote for the living-room Kodi box. Node/Express backend
(`server/`) brokering Kodi JSON-RPC + kodi-send + games/TV/lights, Svelte 5 +
Vite frontend (`web/`), served at `http://192.168.4.147:8790`. Runs as the
systemd **user** unit `couch.service` — never `node index.js` by hand (double-binds 8790).

Deep context lives in auto-memory: `~/.claude/projects/-home-ds2000-couch/memory/`
(`homelab-couch-app.md` = full build log, `couch-ios-ui-quirks.md` = the iOS gotchas).

## Build / deploy
- Frontend edit → `cd ~/couch/web && npm run build` then `systemctl --user restart couch`.
- Server-only edit → just `systemctl --user restart couch` (no rebuild).
- Build stamp shows in the theme sheet (`build YYYY-MM-DD HH:MM`) to confirm the phone loaded fresh.

## ✅ DISK INCIDENT (5 Aug 14:57) - RESOLVED, experiment concluded

disk1 dropped offline under the Simpsons season-pack write load (second
RTL9210 dropout; first was during zip extraction). Donnie applied the
UAS quirk + rebooted 15:36: fsck clean, both enclosures now on
usb-storage, pool complete, qB prefs reverted, all six Simpsons packs
resumed. **Live experiment:** if it drops again on usb-storage it's
thermal, not the driver. GOTCHA found: couchd's WantedBy=
graphical-session.target never fires (lightdm autologin doesn't activate
the user target) so couchd does NOT autostart on boot - started by hand
15:41, unit fix belongs to the couchd session. Full detail in
auto-memory `homelab-usb-disk-dropout.md`.

## ▶ PICTURE-IN-PICTURE - a show over a game (added 9 Aug, NEEDS DONNIE)

**FIRST LIVE RUN 22 Aug ~22:30, AND IT DID NOT NEED GAMESCOPE.** With the
wrap benched, pipd ran straight on :0 over a bare Bloodborne session -
xfwm4's compositor is ON (checked: /general/use_compositing true), so the
ARGB overlay + mpv child composite exactly as designed. Screenshot-verified
at native 4K: Simpsons top-right, game alive underneath, phone API live
(`/api/pip` running:true). mpv IS installed now (0.37.0). Two findings:
(1) classic Simpsons is 4:3 and the 16:9 default window shows opaque black
pillars (mpv paints its own bg) - fixed live by placing with nh matching
the aspect (nw .30 -> nh .40); the phone drag should learn the video's
aspect or accept the bars. (2) the fullscreen overlay blocks xfwm4's
fullscreen unredirect, so the game is COMPOSITED while PiP is up - MangoHud
showed GPU 58->65%, max frametime 28.7ms during the title card; combat feel
verdict is Donnie's. Launch used: `DISPLAY=:0 setsid tools/pipd --display :0
--player-args '--hwdec=auto --no-sub' <file>`. Audio mixes both sources on
the soundbar (undecided question still open). Stop = `{"cmd":"quit"}` on
/tmp/couch-pip.sock.

Built: `tools/pipd` (the overlay + control socket, 31 tests), `server/pip.js`
+ `/api/pip`, and the phone control in `web/src/lib/Pip.svelte` - a TV
rectangle with a draggable picture inside it, live on the Games tab now.
Research and the gamescope source reading: `docs/research/pip-over-a-game-20260809.md`.

**PROVED 9 Aug, headless, TV asleep:** `tools/pip-gamescope-rig` runs
gamescope on its headless backend and screenshots its own composition. The
overlay composites above the game plane, at the exact rectangle asked for,
and moving it moves the picture. So the mechanism works on this box. What is
left needs a display, not a debugger.

**FREEZE/THAW SURVIVES THE WRAPPER** (9 Aug, `tools/stage3-freeze-rig`,
headless, passes twice): gamescope-wrap reports the child's exit status not
gamescope's, game-pids finds the whole wrapped tree, SIGSTOP puts every
process in state T and a counter stops dead, SIGCONT resumes it and
gamescope comes back. So stage 3 does not die on the mechanism the console
is built on. One thing it raises rather than settles: the freeze included
GAMESCOPE ITSELF (faithful to a real Steam launch, where Steam's reaper sits
above it), so suspending a game also suspends the compositor drawing it.
That is the §6 freeze-shape ruling, still yours.

**STAGE 3 IS RE-OPENED.** The 4 Aug parking decision rested on a 1080p60
no-VRR TV, an NVIDIA 4070, and noble packaging - all three are gone, and the
guard's dependency on the Steam overlay turns out to be largely theoretical
(its actuator has been disabled since 7 Aug and never worked). Reassessment
is at the top of `docs/couchd-stage3-design.md`. The one thing still gating
everything is §6 experiment 5: Steam Input and the overlay inside nested
gamescope for a real Steam title.

These are yours:

- [ ] `sudo apt install mpv` - not installed, so pipd currently draws no
      picture (`--player none` exercises everything else).
- [ ] The first live test, an evening, no Steam and no couchd involved:
      run something under `tools/gamescope-wrap`, start
      `tools/pipd --display <gamescope's nested display> <a video>`, and see
      whether a picture lands over the game and whether the phone drags it.
- [ ] Measure what the overlay plane costs. It is output-sized every frame
      whatever size the picture is. On the 9070 XT it may be a free hardware
      plane or it may force composition - unmeasured, and it decides whether
      this is usable in a game that matters.
- [ ] The drag on real iOS Safari. Verified in headless Chromium only, which
      proves the pointer path but nothing about iOS scroll hijacking.
- [ ] THE GATE, and it is not a PiP question: gamescope strips the Steam
      overlay under the nested Vulkan backend, and `steam-input-guard`
      depends on that overlay. Whether stage 3 is adoptable at all rests on
      this, and PiP rides on it.
- [ ] Audio. Two sources, one soundbar. Probably the show to the headphones
      and the game keeps the room, but it is undecided.

Also open, unrelated to gamescope: `tools/tv-multiview-probe` (run at the TV,
five minutes) for whether the C5 can do this itself. Dual HDMI is G5/M5 only,
but HDMI + YouTube or HDMI + phone screen share are on LG's whitelist, and
the TV route costs the PC nothing.

## ▶ LIBRARY: BROWSING IS NOT FINISHED (added 11 Aug ~14:10, NEEDS DONNIE)

Donnie, 11 Aug: "i can only see films in everything - it's hard to look
through so add proper full functionality to find what i want etc."

FIXED already (a911327, live): the sliced captions and the yellow slab. See
that commit - both were size bugs, not layout taste.

DONE 11 Aug (abdc42b): FILMS / TV TABS, Donnie's call ("yeah make movie and
tv separate tabs"). Kodi has no videodb node that merges movies and tvshows
and smart playlists are per-type too, so one grid could only ever be one of
them; the tabs set Window(home).Property(CouchBrowse) and
$VAR[Couch_Browse_Node] resolves the grid's path. Switching is on CLICK not
focus, deliberately - see the commit. Verified live: Films 88, TV 30.
DO NOT RE-TRY conditional navigation tags to make onup return to the active
tab. `<onup condition="...">` CRASHES Kodi hard, three times in ninety
seconds, mid-skin-load (11 Aug, crashlogs logged as ours in
docs/kodi21-flatpak-migration.md).

STILL OPEN, and it is a design decision, not a bug:
- No search, no sort, no filter, no letter jump. The v5 spec called for "A-Z
  grid with L1 R1 letter jump" (docs/specs/console-skin.md) and only the grid
  got built.

THE OPTIONS, cheapest first:
  1. Add a "TV · A to Z" section next to the movies one. Trivial, but it is
     two places to look, which is the thing he is complaining about.
  2. Make the Everything section SWITCH source - All / Films / TV - on the
     shoulder buttons or a small tab strip above the grid. Kodi can do this
     with a window property driving the panel's content string (the same
     trick the games row uses for its revision kicker). "All" still needs two
     panels stacked or a script-built list.
  3. Build the browse page properly: letter rail down the side (L1/R1 jump),
     sort/filter, and a search that covers both libraries. This is the spec'd
     answer and the real fix for "hard to look through".
  Recommendation: 2 now (it directly answers "I can only see films"), 3 as
  the proper build, since global search already exists as script.globalsearch
  and is wired to the home corner strip.

NOTE for whoever does it: the Next up row (7900) caches EMPTY if its plugin
invocation is in flight during a skin reload - seen twice on 11 Aug. Its
content string has no revision kicker like the games row's CouchGamesRev, so
Container.Refresh cannot save it; leaving and re-entering the window fixes it.
Worth giving it the same kicker.

## ▶ GAMES ROW: DONE (11-12 Aug) - the tile leaves, into a real slot

**UPDATED 12 Aug** (`23d8d06`, `7c349ea`, `a2d2893`): the unconditional Focus
fade is gone (it read as a flash, not a grow); pitch tightened 170 -> 156 so
gaps went 40 -> 26; and the container now starts off-screen at x=-55 with a
third slot, so the outgoing tile is clipped at the SCREEN edge rather than
100px inside it. Kodi has no per-item opacity so a real fade is impossible -
the answer was space, not animation. Selector never moved: focused slot =
list_left + focusposition*W, so -55 + 2*156 = 257 = the old 101 + 1*156.
**STILL UNVERIFIED BY EYE while scrolling.**


FIVE attempts, and the one that worked added nothing. focusposition 1 gives the
outgoing item a real slot to travel into and shrink inside; every earlier try
kept the selector pinned at the head, where there is nowhere for it to go, and
tried to fake the exit with an extra control instead. That is what produced the
ghost (3e92b89) and the hoisted frame (3bd9b05), both of which made tiles appear
from nowhere and were reverted.

Live geometry: pitch 156 (= the focused tile exactly), resting 130 flush to the
slot's right edge at offset 26, gaps 26px, grow 83.3% -> 100%, rings at 206 with
centre 392,179. The ring is ALLOWED to overlap the neighbour it sits in front of
- it is a static control drawn after the list, so that is depth-correct, and
reserving 30px for it is what made the first pass look too airy.

Verified on the live home at 60fps, not just the twin.

THE LESSON, worth more than the geometry: a fixedlist gives an outgoing item one
slot of travel and then culls it, and the container clips it before that. No
animation and no extra control can conjure space that does not exist. If the
exit ever needs changing again, change the SPACE, not the animation.

Remaining, cosmetic and Donnie has seen it: at the head of the row the left slot
is empty, so the row starts ~156px in. That space is the exit lane; it fills as
soon as you move right.

## ▶ (superseded) GAMES ROW: REVERTED TO REAL TILES

Donnie, 11 Aug: "all i want is the current tile to leave and shrink and the new
tile to enter and get bigger... tiles are appearing out of thin air".

The exit ghost and the hoisted focus frame are BOTH GONE. Each faked the exit
with an extra control, and that is precisely why tiles materialised. The row is
back to 09cc7ac: one real tile per game, Kodi's own Focus/Unfocus zooms doing
the grow and the shrink. Verified on the live home at 60fps.

THE ONE THING STILL NOT DONE is the outgoing tile actually leaving the screen.
It shrinks away and the last of it is clipped at the container bound. Four
attempts to add an exit have each made the row worse, so DO NOT ADD ANOTHER
CONTROL. With real tiles there is exactly one way:

  focusposition 1 - a genuine slot to the left for the outgoing tile to travel
  into and shrink inside. Nothing culled, nothing invented, and it is what he
  described wanting.

  THE COST, worked out and not yet paid: the focused tile is 156 and the slot
  pitch is 120, so with a left neighbour the focused tile overlaps it by 36px
  (this is the old "the next game loses its left edge" bug, from the other
  side). Pitch must be >= the focused width. Options:
    - pitch 166, resting tiles stay 110: gaps go 10 -> 56px. Airy, fewer tiles.
    - pitch 166, resting tiles grow to ~130: gaps ~36px. Closer to the current
      density, but every tile changes size.
    - keep pitch 120 and shrink the focused tile to <=120: the grow becomes
      ~9%, probably too subtle to read as "gets bigger".
  Plus: the halo ring sits 30px outside the tile, so it will overlap the left
  neighbour unless the pitch grows further, OR the ring is dropped for the
  lightbar (which IS the skin's stated focus grammar - Includes_Couch.xml).

  Needs Donnie to pick, because all three change how the row LOOKS at rest.

## ▶ (superseded) GAMES ROW: THE TILE NOW LEAVES

DONE: Donnie chose the flying exit ("go back to the way it worked when it left
the box") and it is LIVE on Home.xml as of 3e92b89. Verified by recording a
real press on the live home, not just the twin.

DONE 11 Aug (3bd9b05): Donnie picked (b), "the proper fix". The focus frame is
hoisted out of the list, the container bound moved 80 -> 116 with every layout
x dropped 36 to compensate, and the outgoing tile now lands entirely left of
the bound - clipped to nothing. focusedlayout is identical to itemlayout; the
row only ever draws resting tiles. The frame no longer grows: it is fixed and
the artwork flows through it, fadetime 0 (a crossfade there is the same smudge
rejected on 10 Aug).

STILL TO JUDGE BY EYE: for ~200ms during the slide the INCOMING game shows
twice - in the frame, which adopts it immediately, and as its own resting tile
still travelling into place behind the frame. Hiding the traveller trades it
for a moving gap between the frame and the next tile, which is probably worse.
Left alone deliberately. Comparison clip sent 11 Aug.

The original framing below is kept - the fixedlist limits it describes are why
the ghost exists at all.

## ▶ (original) GAMES ROW: THE TILE THAT CANNOT LEAVE (added 10 Aug ~23:00)

Donnie, three passes: "pressing RIGHT, the outgoing focused tile does not
visibly LEAVE the selector box". Two separate things were tangled up here, and
slow-motion capture in the 1198 twin (10x, 60fps, frame-differenced) separated
them:

1. A REAL BUG, now fixed (see below). The dissolve emptied the box by frame
   138 of the transition, then Kodi reverted the item to itemlayout at frame
   141 and a fully opaque resting tile POPPED BACK IN (strip luminance stepped
   48.9 -> 67.3 in a single frame) before sliding out. Fade, flicker back, get
   eaten. Every previous pass tuned the focusedlayout fade, which cannot
   reach the itemlayout copy that is the thing you actually watch leave.
   FIXED by deleting the dissolve: the tile now stays solid the whole way out,
   no frame-difference spike anywhere in the exit.

2. SOLVED IN PROTOTYPE (0950c8f, window 1198 only - clip sent 10 Aug). The
   tile now genuinely leaves the ring and exits the screen. It is NOT the
   list's tile: it is an "exit ghost", a plain image drawn OUTSIDE the
   container (nothing clips it, no slot limit) textured with
   $INFO[Container(9000).ListItem(-1).Art(thumb)] = the item just left.
   THE KEY FACT, measured, worth never re-deriving: Container(9000).OnNext is
   a ONE-FRAME PULSE (1 frame of 420 recorded; does not scale with
   scrolltime). It can trigger an animation - a Focus/Unfocus condition is
   read once at trigger time, which is why the old dissolve worked - but it
   can never gate a 210ms flight with <visible>. The working shape is a
   HIDDEN animation: Kodi keeps the control rendered while its Hidden
   animation plays, so it flies out AFTER the pulse has gone. Flight measured
   at 183ms real; ~3.5 skin px/frame, fully off the left screen edge.
   TO DECIDE: (a) does the 183ms flight feel right or does it want to be
   slower/faster, (b) the open artefact - the list's own outgoing tile still
   crawls out inside the ring (skin x80..116) while the ghost flies, so two
   copies are briefly visible. That remnant is the itemlayout instance and no
   focusedlayout animation reaches it; killing it means changing the row's
   slot geometry so the outgoing slot lands entirely left of the container
   bound, which changes the resting rhythm of the whole row. Not done
   unilaterally. Then port 1198 -> Home.xml.

3. The ORIGINAL framing below is kept because the trade-offs still apply if
   you would rather change the control than keep a ghost. A fixedlist at
   focusposition 0 gives the outgoing item exactly ONE SLOT of travel and then
   culls it at the container's left bound. The bound is at skin x80 and the
   ring's stroke is drawn at x50, so the tile evaporates 30px INSIDE the ring
   - it never reaches an edge, which is exactly why it reads as "it doesn't
   leave the box". No animation tuning fixes this; the control shape has to
   change. The options, with their costs:
   - focusposition 1: the outgoing tile lands in a REAL slot and stays
     visible, so it genuinely travels away and nothing is culled or faded.
     Cost: a permanent slot left of the selector, so the whole row shifts
     right to keep that slot clear of the ring - a composition change to the
     home screen, not a tweak. This is closest to "the old tile physically
     travels away".
   - widen the exit lane (container bound left of the ring): MEASURED to make
     things worse, not better. Travel is fixed at one slot, so a wider lane
     just means MORE of the tile is still on screen when the cull fires
     (36px visible at bound=x80, 110px = the whole tile at bound=x6). The
     lane needs a fade to hide the cull, and a fade is what we just removed.
   - clip on the ring's stroke (bound x50, every layout x +30): the tile dies
     on a drawn line instead of in mid-air. Cheap, honest, but it is still
     "swallowed", not "left".
   - accept it: the tile crossfades in place and the row reads as a reel.

   Not decided, deliberately. Comparison clip recorded 10 Aug (before/after
   the bug fix, 10x): the fix is committed, the design question is not.

## ▶ STAGELIGHT - the console skin build (added 7 Aug ~23:00, phase 1 LIVE)

The evening session: skin.couch forked (a43c5fa, ACTIVE on the TV, symlinked
from ~/couch/kodi-addons/skin.couch - edit + ReloadSkin to iterate) and the
console-UI redesign researched, specced, mocked and STARTED. Read
`docs/specs/console-skin.md` first: 14 constraints, the Stagelight identity
(artwork lights the room via Window(home).Property(clearlogo_cropped-color),
lightbar focus mark, Figtree, no hero, v5 structure = PS5 home row with a
Library tile -> Netflix-style image rows + A-Z grid). Approved interactive
mockup: claude.ai/code/artifact/fb5b7dfe-b72c-42a1-a006-09fc2634398e (v5).
Research receipts: docs/research/console-ui-patterns.md +
10-foot-ux-and-kodi-engine.md (read the engine one before writing XML).

- [x] Phase 1 (dff2d13): Figtree in fonts/Figtree + Couch_* scale in all 3
      fontsets (28/32/36/44/64/90), 16x9/Includes_Couch.xml (Couch_Live_Color
      + Couch_Lightbar/GlowField/Scrim includes, safe-area constants),
      media/couch/ white textures (tint via colordiffuse). Verified live
      22:49:42, clean reload.
- [ ] Phase 2 NEXT: the Library page (v5 mockup, frame 2) - Next up /
      Continue (widgets, per-tile progress lightbar) / New / Everything A-Z
      grid with L1 R1 letter jump. Smart playlists feed the rows. Exercises
      the phase-1 tokens for real.
- [x] Phase 3 built as window 1198 (8 Aug, all-nighter): PS5 layout per
      Donnie's reference photo - 110px tile row, halo H (live-colour glow +
      white core, slice-safe assets after 3 clipping fixes), clearlogo +
      Play pill lower-left, corner strip (Lucide search/settings/power +
      pad battery chip), composed square game tiles (hero art + Steam
      logo.png centred; tile.png override for PS4 dumps - Bloodborne).
      NOT yet the real Home - the swap is still the next big step.
- [x] Switcher restyled to the Stagelight tile rail + ALT-TAB THUMBNAILS
      (live window captures via /api/art/winthumb, mapped-only, compositor
      reads obscured windows; phone switcher gets them free).
- [x] kodi-tv flock (twin-instance crash-race fixed, 8 Aug).
SLEEP SESSION (8 Aug ~06:45, "fix everything while i sleep") - done, all
verified loading + committed, TV left OFF:
- [x] Continue tiles: resume progress bar (CouchProgress property, helper
      1.1.7.4).
- [x] Volume bar: moved off the top-right clock to a bottom-centre pill
      (DialogVolumeBar, no dB number - Kodi only exposes dB).
- [x] Power menu (PS-hold / corner icon): Stagelight tile sheet replaces
      Copacetic's DialogButtonMenu (Home/Suspend/Restart/Power off/Exit,
      Lucide icons, amber halo). ondown=Close was self-closing it - fixed.
- [x] Film seek bar fill -> amber (Seekbar_Focused_Color default, token-only,
      seekbar STRUCTURE untouched so playback cannot break).
- [x] Stock dialog accent -> amber (Accent_Hex ff5174 -> e8a849): select,
      confirm, context, keyboard, settings, notification all match Stagelight
      now via one variable. Hand-built windows use literals, unaffected.
- [x] 4K120 WORKS (kernel 7.0, 4:2:0 via force_yuv420) - persistence staged,
      NEEDS: sudo cp ~/couch/tools/systemd/couch-4k120.service /etc/systemd/
      system/ && systemctl enable it.
NOT done (deliberately - need Donnie awake / would wake the TV / risk the
working UI blind):
- [ ] Full player OSD restyle (play/pause controls, info) - needs watched
      playback, which fires OnPlay -> tv-waker. Seek fill amber is the only
      safe piece done.
- [ ] YouTube row on Library - adding a 5th section reworks the slide-stack
      geometry; risky blind, do it awake.
- [ ] Games in search - needs a custom search window (globalsearch is
      library-only). Bigger feature.
- [ ] Notification/volume toasts still overlap the clock corner on the rare
      stock-notification path (volume's own bar is fixed; the toast is
      Copacetic's shared layout).
- [ ] Continue/Next up rows take ~10s to paint (plugin walks the library per
      open) - consider caching.
- [ ] Open: wrap-around ships behind a skin setting (Donnie feels both);
      nav sounds later, off switch mandatory.
- Gotchas for the builder: C13 crash rules (no conditional nested blocks in
  cached includes, non-empty param defaults); no ambient animation EVER
  (full-viewport redraw); helper colour only updates when
  Skin.HasSetting(Crop_Clearlogos); posters upscale soft at 4K until
  <imageres> is raised in advancedsettings.xml (measure disk first);
  screenshots via kodi-send TakeScreenshot. Kodi log may be rotated out from
  under the live instance after a watchdog double-relaunch race (19:33
  today) - if kodi.log looks stale, read /proc/$(pgrep -x kodi.bin)/fd/8.

## ▶ Also 24 Aug (~17:50) — Codex is a /codex skill now, and it finds the right memory by itself

`~/.claude/skills/codex/` writes up the three proven shapes (no-repo consult,
blind adversarial review + adjudication, worktree-fenced terra task) with the
exact invocations, verified against CLI 0.144.6.

**The routing fix that mattered:** `~/.codex/AGENTS.md` hardcoded venue-finder's
memory path, so a Codex session pointed at couch had no memory at all. It now
tells Codex to run **`claude-memory`** (new, `~/.local/bin`, so it is on PATH
and inside the nightly backup). That resolves the Claude Code memory dir for
whatever directory it is in - **and through a git worktree back to the origin
repo**, which is the case that matters here: `tools/terra-task` hands Codex a
throwaway worktree under `/tmp`, and naive `$PWD` mangling finds nothing there.
Proven end to end: codex run with `-C /tmp/wt-probe` resolved to couch and read
the index.

`tools/terra-task`'s fence had to change with it - it said "never reference
/home/ds2000/.local/bin", which forbade exactly what AGENTS.md now asks for.
It now says never WRITE outside the worktree, with one named read-only
exception.

Measured while validating (in the skill's traps): `codex exec` defaults to
`reasoning effort: none` - pin `-c model_reasoning_effort=high` for reviews;
there is a ~4.3k token floor per invocation; and piping `codex exec` into
`head` SIGPIPEs the run so the `-o` file never lands.

## ▶ Resume here (31 Aug 2026 ~15:30 — Bloodborne cheats end to end, script/ convicted for good, mode-keeper is OFF)

A Bloodborne companion session that turned into three pieces of engineering.
Donnie hit a wall on the Cainhurst boss and the day ended with cheat toggles on
his phone.

### ▶▶ DONNIE'S TO-DO (only he can do these)

1. **`sudo sysctl kernel.yama.ptrace_scope=0`** — NEW, and it is what unlocks
   live cheat toggling. The scope is 1 by default, which forbids one process
   writing another's memory, so `bb-cheat live` and the phone's toggle-while-
   running path both fail without it. Lasts until reboot; undo with
   `sudo sysctl kernel.yama.ptrace_scope=1`. Without it everything still works,
   it just applies at the next launch instead of instantly.
2. **Look at the new Bloodborne sheet on your phone.** Games tab, tap
   Bloodborne. The API is verified end to end but **the sheet has never been
   rendered** — there is no browser on the box (playwright wants Chrome at
   /opt/google/chrome/chrome, which is not installed). First human eyes on it
   are his.
3. **`sudo systemctl restart inputproc.service`** — STILL OUTSTANDING from
   29 Aug, now four days stale. pid 1161 is running 27 Aug code, so the
   input-ownership fix (`9d11873`) has never gone live. Do it at the TV, not
   from work. Panic lever `sudo couchd-input-release`. Every inputproc restart
   deafens flatpak Kodi until `peripheral.joystick` is addon-bounced, which the
   assistant can do over Kodi's API afterwards, no sudo needed.
4. Still outstanding from 26 Aug:
   `sudo rm /var/lib/apport/coredump/core._tmp_claude*bbcw-dummy*`

Judging the UI sounds by ear is still open too, see the 30 Aug block below.

### 1. CHEATS: `tools/bb-cheat` + a Bloodborne sheet in the phone remote

Donnie, after an hour on the Cainhurst boss: "this fight just isn't fun ... i'm
looking through the debug menu for like an invincibility mode". Then: "can we
make it so we can toggle mid game", then: "can you add toggles to the remote
app?". All three are done.

**`tools/bb-cheat`** wraps shadPS4's official cheat file
(`~/.local/share/shadPS4/cheats/CUSA00900_01.09.json`, from shadps4-emu/
ps4_cheats). Six cheats: Infinite Health, Infinite Stamina, 1 Hit Kill,
Infinite Items, Infinite BloodEcho, Infinite Lucidity.

The problem it solves: **shadPS4's cheat UI lives in the Qt GUI**, our launcher
runs the SDL build, and there is **no keyboard or mouse at the television**
(`/dev/input/by-id` is empty), so those tickboxes are physically unreachable.

Two paths, both verified against the emulator source rather than guessed:

- **Boot mode** writes the cheats as `<Metadata>` blocks into the SAME XML the
  60fps unlock uses, `patches/shadPS4/Bloodborne.xml`, which the SDL build
  applies automatically at eboot load (`MemoryPatcher::OnGameLoaded`, called
  from `module.cpp` when eboot.bin loads). **The address rule matters:** a cheat
  JSON offset is eboot-relative, an XML `Address` is an absolute PS4 VA and the
  emulator subtracts 0x400000, so `Address = offset + 0x400000`. `Type="bytes"`
  values are raw hex pairs with **no 0x prefix** — a prefix parses as 0 and
  writes garbage. Our blocks are tagged `couch-cheat: ` and upstream's 59 blocks
  and 2615 patch lines were re-counted intact after repeated toggles.
- **Live mode** (`bb-cheat live on|off|status`) writes into the running process
  at `0x800000000 + offset`. The eboot base is fixed — it is the first
  `base_virtual_addr` line in shad_log. It reads the current bytes first and
  **refuses unless they match either the patched or the original set** (the
  cheat file carries both), then reads back after writing. A wrong address
  errors instead of corrupting the game. Needs ptrace_scope 0, see to-do 1.

**Phone remote**: `server/cheats.js` (thin wrapper, absolute path because the
systemd PATH has no `~/couch/tools` — the launch PATH trap again),
`GET/POST /api/games/cheats`, a `cheats: true` flag on the CUSA00900 tile from
`games.js`, and a sheet in `Games.svelte`. Tapping Bloodborne now opens options
instead of launching: Launch/Resume, then six tap-to-toggle rows. A toggle does
**both halves** — the running game and the next launch — because doing only one
looks like the switch did nothing. Verified by round trip through the HTTP API;
NOT verified visually.

`bb-cheat off` returns to a clean game whenever he wants.

### 2. script/ IS CONVICTED FOR GOOD — and its absence cost more than we knew

Chasing "can we turn on spawn at boss, i'm sick of the runback" turned up that
Enhanced's **`Quick Warp to Bosses` has been ENABLED in his save the whole
time** (flag 12100857, read live with `bb-eventflags.py --mod-settings`) and he
has never once seen it. **A lamp is a talk object**, so keeping `script/`
vanilla after the August lamp saga did not just cost NPC dialogue — it made the
mod's entire lamp menu inert: warp, level up, workshop, boss rematches, quick
warp, and the Doll's "Enhanced Features" menu. All 46 supposedly in-game
settings have never been reachable.

**The trap worth remembering: a set flag proves the setting is enabled, not
that anything can deliver it.**

So `script/` went back in as a retry (the 26 Aug bisect convicted it, but the
suspected cause was a stale talk flag from that session's freeze/OOM, never
explained). **Lamps died again on the first launch, clean save, no crash.**
That kills the stale-flag theory: 2 for 2, it is the files. Reverted, verified
byte-identical to vanilla. **Do not retry.**

New panic lever `tools/bb-script-revert` (`--check` reports which state the dump
is in). Full write-up appended to
`docs/research/bloodborne-lamp-saga-20260826.md`, including the one untested
lead: the archive is a "full package + **patcher**" and ships
`BBEnhancedPatcherGUI` plus a 1MB `_data/emevd_patches.json`, and **we have only
ever done a plain file overlay, never run the patcher**. If the shipped talk
ESDs assume a patcher pass, a raw copy would break in exactly this way. Read
`_src/BBEnhancedPatcherGUI/Form1.cs` before ever touching `script/` again.

Consequence for the companion: any mod setting he wants must be written into the
save as an event flag (group 12100 = slot 50; all 51 flag ids are in the
archive's `_data/settings.json` under `PossibleValues`). `bb-eventflags.py`
reads; a writer is ~10 lines on top of it and is the obvious next tool.

### 3. mode-keeper IS STOPPED — the TV lost signal, deliberately left off

Mid-session, quitting the emulator dropped the display to plain 3840x2160,
mode-keeper spotted it 4 seconds later (`correction 10`) and forced the hand-made
`4k120` modeline back on. **The TV did not accept it and went to no signal.**
Not a crash: Kodi and X were both fine throughout.

Fixed by `systemctl --user stop mode-keeper.service` then
`xrandr --output DisplayPort-2 --mode 3840x2160 --rate 60`. Picture confirmed
back by Donnie.

**mode-keeper is still stopped and the box is on 4K60.** He explicitly parked
the handshake investigation ("park looking in to the handshake"). To restore the
old behaviour: `systemctl --user start mode-keeper.service` — but expect the
same blank if the handshake is genuinely flaky now, and it has corrected fine
ten times this boot, so it is intermittent. Also note a modeset resets Kodi's
audio sink; `tools/kodi-restart` if sound is missing.

### 4. Companion service — he is at the Cainhurst boss and struggling

Ledger `docs/research/bloodborne-progress.md` is current with every answer
given. He has **Ludwig's Holy Blade at +7** (bought it himself), 10 Insight,
and has not touched the lake. Headlines:

- Corrected myself twice in his favour: **Bolt Paper is wrong on this boss**
  (he is strong vs fire/arcane/bolt, 290 arcane defence vs 133 physical), and
  **greatsword form kills the parry** because it is two-handed and takes the gun.
- Stat answer: Ludwig's is a **quality** weapon, 25/25, Skill first because
  visceral damage scales with Skill.
- **The ladder mystery was STAMINA** and he confirmed it. On a ladder, stamina
  is what keeps you attached; he had started sprinting the runback and was
  arriving empty. Two wrong theories were offered before that (two shooters,
  then Bound Widows) and the second one landed as condescending — he was right
  to push back. Go to mechanics before theories about what he can or cannot see.
- **STILL OPEN AND LOAD-BEARING: he must ping before handing anything to
  Alfred** (order matters), and **Eileen's post-Rom beat is on me to raise**.

### 4b. Three more mods dropped in (31 Aug ~20:40) — two installed, one refused

- **60fps Cutscene Fix (mod 70) — INSTALLED**, 11 files. Its `sfx/` files are
  `frpg_sfxbnd_m21` and `m25`; Enhanced's are `commoneffects` and `m29d`, so
  **no overlap** and the Reddit "sfx mod conflicts with Enhanced" scenario does
  not arise here. Plus 9 `remo/` cutscene files Enhanced does not ship.
- **Visual Upgrade Mod (mod 160) — INSTALLED AS A SAFE SUBSET.** All 23
  `param/drawparam` lighting files (Enhanced ships only `param/gameparam`, so no
  collision, and the durability patch is untouched - md5 re-verified) plus the 8
  map MSBs Enhanced does not ship. **16 map MSBs were HELD BACK** because
  Enhanced ships them too, and **Enhanced's Auto Refill is a proximity region
  living in its own MSBs** - overwriting them would kill Auto Refill in 16
  areas including Central Yharnam and Cainhurst. Cost of holding them: some of
  v1.3's shadow/LoD fixes in those maps. To take the full mod and lose Auto
  Refill instead: `bb-mod-install install "<the original 160 zip>"`.
  Staged subset zip: scratchpad `vum/VisualUpgrade-160-v1.3-SAFE-SUBSET.zip`.
- **Jump on L3 (mod 156) — NOT INSTALLED, and it looks wrong.** The dump's
  `action/script/c0000.hks` is **compiled Lua bytecode** (`\x1bLuaQ` header,
  760,643 bytes). The mod ships **plain text HKS source** with a UTF-8 BOM,
  428KB, in two undocumented variants ("DS3 - Modern" and "DS3 - Classic").
  Text where the engine wants bytecode will not load, and this file IS the
  player behaviour script, so a bad one breaks the character outright. Needs
  either an HKS compiler or proof Bloodborne accepts source. Do not install it
  blind while he is out.

**Verified after both installs:** Bloodborne Enhanced is untouched - chr 1/1,
event 18/18, menu 40/40, msg 42/42, parts 4/4, sfx 2/2 and **all 2335 map
files** byte-identical to its packaged output. gameparam still carries the
durability patch.

### 5. Git state

Committed to `master` as `2f6a32b` (this repo has only ever had the one branch,
so a handoff branch would just orphan the work). **Deliberately left
uncommitted, and none of it is from this session:** `tools/game-quiet` and
`tools/test_game_quiet.py` were already modified when the session started, and
`shadow/*.jsonl` are the running shadow logs. Someone should work out what the
game-quiet edits were for before they get committed by accident.

### 6. Small thing left on the table

The Nexus mod **"Jump on L3"** (mod 156) would move the sprint-roll's gap jump
onto its own button, which he wanted. It needs him to download it to
`~/fileshare/bloodborne-mods`. It edits the same behaviour layer as the lamp
saga, so check a lamp before committing a session to it.

## ▶ Previous (30 Aug 2026 ~16:45 — UI sounds rewritten and LIVE, Bloodborne is a Steam shortcut, the DS3 save came back from the dead)

### ▶▶ DONNIE'S TO-DO (only he can do these)

1. **`sudo systemctl restart inputproc.service`** — STILL OUTSTANDING. pid 1161,
   up since 27 Aug 10:20, so it is running 27 Aug code and the input-ownership
   fix (`9d11873`) has never gone live. **Do it at the TV, not from work**: that
   process holds the exclusive grab on the only controller. Panic lever
   `sudo couchd-input-release`. Every inputproc restart deafens flatpak Kodi
   until `peripheral.joystick` is addon-bounced — the assistant can do that
   over Kodi's API afterwards, no sudo needed.
2. **Judge the new UI sounds by ear.** They are live on the box and measured
   correct (see §1), but whether they *sound* right in the room over the
   soundbar is the one thing no measurement here can settle. mp3 A/B of the old
   and new sets was sent in chat. Retuning is a number in `SOUNDS`, never a wav.
3. Still outstanding from 26 Aug:
   `sudo rm /var/lib/apport/coredump/core._tmp_claude*bbcw-dummy*`

**Item 2 of the 29 Aug list is DEAD**: "pick UI sounds from the Kenney audition
page" is obsolete. He heard them, said they "kind of sucked", and the set was
rewritten from scratch instead. Do not re-offer that page.

### 1. UI sounds — REWRITTEN, DEPLOYED, LIVE, AND PROVEN AT THE SINK

The 29 Aug diagnosis ("just mixed too quiet") was half wrong and **measured
wrong**. The old set was seven pure SINE waves under an exponential decay; no
amount of gain makes a sine sound like a console.

**MEASURE loud50, NOT whole-file RMS.** Whole-file RMS divides by length, so
giving a sound a reverb tail makes the number go DOWN while it gets louder —
the first pass of this rewrite looked like a regression by that metric while
plainly being louder. `tools/make-uisounds --measure` now reports peak, RMS and
**loud50** (RMS of the hottest 50ms window). Only loud50 means anything here.

Each sound is now three layers, all still numbers in `SOUNDS`:
transient (band-passed noise at the attack — the reason a click reads as
physical), body (inharmonic partials, 2.63x/3.06x not 2x/3x), room (150-500ms
damped Schroeder). `in`/`out`/`launch` add a swept-bandpass noise layer.

Levels (loud50 dBFS): cursor -21.8, launch -12.5, the rest -17.5 to -18.8.
**The cursor was 18.7 dB under launch; it is 9.3 now.** Noise uses a seeded rng
so output stays byte-reproducible and `--check` still means something.

**Verified, not asserted.** Attack windows measure spectral flatness 0.5-0.7
(broadband) against bodies at 0.18-0.44 (tonal); no clipping, no DC. Then
recorded the HDMI sink monitor while sending two d-pad presses:
`2 bursts, 96ms each, peak -5.7 dBFS, dominant 2427 Hz` — against a design of
-6.0 dBFS at 2400 Hz. That is the new tick coming out of the real sink.
Old wavs kept at `data/uisounds-backup-20260830/`.

### 2. Bloodborne is a Steam shortcut now (`tools/steam-shortcut`) — CONFIRMED WORKING

Donnie: "can you pause and add bloodborne as a steam game so i can launch from
big picture". He has since launched it from Big Picture and confirmed it brings
up our own loading card.

`shortcuts.vdf` is a **binary VDF that Steam rewrites from memory on shutdown**,
so the only safe sequence is `steam -shutdown` → edit → start, which the tool
does and then verifies by reading the file back after Steam is up again. The
shortcut points at **`game-launch`, not the emulator**, so it gets the Kodi
input handover, the curtain, the TV wake and suspend/resume. `AllowOverlay=0`
on purpose: the overlay works by LD_PRELOAD, which is a good way to break a
shell script that execs something else.

Grid art goes in `userdata/1024364793/config/grid/<appid>.*` — **Steam does not
own that folder**, so `--art-only` rewrites art with no shutdown at all.

**One thing found and NOT chased:** `game-launch bigpicture` brought Big Picture
up at full size but left it **stacked underneath Kodi**, so the screen never
changed. Had to raise it by hand with `_NET_ACTIVE_WINDOW`. May be the known
restack weakness, may only bite when the request comes from a shell rather than
the pad. Does not affect launching a game from Big Picture.

### 3. Loading spinner — smoother, and a real drift bug fixed

Donnie: "can we increase the frame rate and in between frames". Two problems.

`loading-card` was **24 frames at 12fps** — a 15-degree jump every 83ms. Now
**60 at 30**, measured off the generated strip at `mean 6.00 deg` per frame,
`360.0 deg over 60 frames = 2.00s`. Same speed, 2.5x the resolution.

The bigger one was in `curtain`: the tick loop scheduled `now + period`,
restarting the clock from each wakeup, so every tick's lateness compounded.
Simulated with realistic jitter: **old 27.8 fps, new 30.0** — it was silently
losing ~9 frames every 4 seconds. Now advances the schedule, with a resync if
it falls more than a whole frame behind.

Also: **`SPIN_VERSION`** in `loading-card`, because the card cache validates on
the ART's mtimes, which say nothing about the spinner — without it a redesign
silently keeps serving the old strip. And **all 13 cards were pre-warmed**
(cold compose 2.0s, warm 22ms), or the first launch per game would show the
shuffle the curtain exists to hide. 52 curtain tests pass.

### 4. Bloodborne hero art replaced — it was a SPOILER sitting on the home screen

Donnie: "can we change the bloodborne artwork to a proper game poster / banner
art instead of a screencap of a final boss". He is playing **blind**. Replaced
with the official textless key art, genuine 3840x2160 native (picked from six
4K candidates, the only one unambiguously safe for a blind player). Old one at
`data/art-backups/`. **Do not tell him what the old one was.**

Live on both surfaces, screenshot-verified: Kodi home and the Steam Big Picture
backdrop. Two traps: the card cache busts itself on the hero's mtime (good), but
**Kodi kept drawing the old texture even after `Textures.RemoveTexture` and
navigating away and back — only a Kodi restart cleared it.**

### 5. THE DARK SOULS III SAVE CAME BACK, and the hole it exposed is closed

His DS3 save from **17 Oct 2024** was recovered from `C:\Windows.old` on his
Windows PC — a folder Windows should have deleted ten days after a May 2026
"keep my files" factory reset (which still wipes AppData) and had kept for
three months. Pure luck. Installed and checksum-verified.

**None of these games have cloud saves.** DS3 never had Steam Cloud (DS1 did);
Elden Ring and Sekiro have none; Bloodborne is an emulator. Every save on the
box lived in exactly one place.

`tools/save-backup` + `save-backup.timer` (user, 10 min) now snapshots all four,
content-hashed so idle costs nothing. It deliberately does **not** wait for the
game to quit (a file touched in the last 20s is deferred as mid-write instead)
and deliberately does **not** sync to the PC (a sync conflict eating a save is
worse than the problem). Restore snapshots the current save first; the path was
exercised end to end on Sekiro. Every archive was extracted and compared
byte-for-byte against the live files: 19/19 identical.

**Off-box needed no work**: `~/.local/bin/backup-all.sh` (root crontab 03:35,
rsync to dns2) already lists `/home/ds2000/couch` and no exclude touches
`data/`. The 03:35 run has already carried them; verified on dns2 by MD5.

### 6. Bloodborne companion — HE IS AT THE WATERSHED

`docs/research/bloodborne-progress.md` is current. **Shadows of Yharnam dead,
Byrgenwerth open, and the lake off the pier IS Rom** — the load-bearing "settle
everyone before the lake" warning was delivered in full.

Pre-lake business he holds: the Cainhurst summons chain (obtained; next stop the
Hemwick obelisk, feeds Alfred), and Gilbert. Everything else is settled — all
six refugees are placed, beggar sent to the clinic (safe), cord A confirmed
held. **Eileen's Grand Cathedral beat after Rom is still MINE to raise.**

New standing rule, his callout: **directions must not name the destination.**
Saying "the cave leads to Iosefka's Clinic" spoiled the reveal at the end of the
route. Landmarks only; let the place announce itself.

Also this session: he lost 21 Insight to a Brainsucker at Byrgenwerth (2 per
grab, permanent, mash out to lose 1) and holds 27 Madman's Knowledge — advised
to bank them and stay under 15 for the Frenzy and enemy-upgrade thresholds. The
"bell on a stick coming out of the ground" in the Dream is the **Beckoning
Bell's summon marker**, not an item; Silencing Blank clears it and refunds.

### Uncommitted / loose

Standing convention, deliberately uncommitted: `data/`, `shadow/`,
`recordings/`. **Inherited and NOT mine:** `tools/game-quiet` +
`tools/test_game_quiet.py` (predates this session, left alone).

`tools/console-idle` exists on disk from a thread Donnie asked to drop. It is a
read-only "is the console in use" check. Not documented further on purpose.

The `save-backup` systemd units live in `~/.config/systemd/user/` and are **not
in the repo** — consistent with `spotify-heal`, which is not either.

## ▶ Previous (29 Aug 2026 ~22:00 — sol reviews landed, trophies fixed, two emulator fixes armed, sounds waiting on Donnie)

### ▶▶ DONNIE'S TO-DO (only he can do these)

1. **`sudo systemctl restart inputproc.service`** — the input-ownership fix is
   COMMITTED AND ON DISK but pid 1161 is still running 27 Aug code. It is a
   SYSTEM unit, so it needs his password. **Do it at the TV, not from work**:
   that process holds the exclusive grab on the only controller. Panic lever
   `sudo couchd-input-release`. Every inputproc restart also deafens flatpak
   Kodi until `peripheral.joystick` is addon-bounced — the assistant can do
   that bounce over Kodi's API afterwards, no sudo needed.
2. **Pick UI sounds** from the audition page (link in chat; page source
   `scratchpad/ui-sound-audition.html`, Kenney CC0 packs downloaded). One
   filename per slot: cursor / select / back / error / launch.
3. Still outstanding from 26 Aug:
   `sudo rm /var/lib/apport/coredump/core._tmp_claude*bbcw-dummy*`

### 1. couchd: the four sol findings — FIXED, LIVE except inputproc (`9d11873`)

Two read-only gpt-5.6-sol reviews (`docs/audits/*-20260829-*`), adjudicated
against the code before anything was applied. Codex wrote the fix in a fenced
worktree over two rounds; round 1 introduced a switcher double-fire and its own
test pollution, both caught by running the suite and both fixed in round 2.

- **Input ownership was cached at startup** — `grants_input()` ran once, so
  removing `input` from `owns.conf` did NOTHING to a running inputproc. It
  presented as a *selectively dead PS button*, not a dead service. Now a
  continuous interlock (one cached `stat()` per pass) + the existing 30s
  supervisor lease; release ungrabs, re-acquire takes a FRESH BTN_MODE baseline.
- **Configured timings never reached couchd's classifier** — `PressTracker()`
  built with no args. Now configured, and only updated between presses.
- **The PS-button switcher raised Kodi with nothing over it** for the addon's
  own measured 1.3-1.5s startup. The frozen game now covers Kodi and the swap
  happens on POSITIVE confirmation of the dialog window. **The wait is bounded
  (`SWITCHER_REVEAL_GRACE = 6.0`) — that bound and its test are mine, added
  because unbounded it suppressed the only net that rescues the screen.**
- **A retiring launcher stamped on the next launch's curtain** — the EXIT trap
  guarded the session flag by ownership but called `restore_on_exit`
  unconditionally. Deployed to `~/.local/bin/game-launch` (backup in
  `data/legacy-bin-backups/`); repo copy and live copy verified identical.

Live tree: **1434 tests pass, 0 fail.** couchd restarted, healthy, `acting`.

### 2. shadPS4 texture-cache GC — ARMED BUT THE FIX DOES NOT WORK (`1fdc058`)

H1 is **PROVEN** by the census: `tc_gc_frees` frozen at 51272 for an entire
session while `tc_gc_visits` climbs 15,360 per tick and `tc_immortal` = 430.
The collector visits ~15k textures/sec, skips 99.9%, frees nothing, ever.
**But my Fix 1 (charge the budget on frees only) changed nothing** — visits
rise by exactly 256/flip, i.e. the visit cap is being hit every pass, so the
code runs and does not help. Capping the wasted walk was the wrong lever.
**Next lever is probe C** (top-N offenders by `fault_hits`), which separates
real invalidation from re-labelling. Kill switches:
`touch data/shadps4-gc-fix-off` (control arm), `rm data/shadps4-local-build`
(stock AppImage). Doc: `docs/research/shadps4-reload-stutter-20260828.md`.

### 3. shadPS4 audio: the OpenAL queue ratchet — FIXED, ARMED, UNCONFIRMED (`47b62e9`)

The crackle had been logging itself **21,455 times, 21,425 at `queued: 1`**.
`Initialize()` primes 5 blocks (~27ms); `Output()` reclaims ALL processed
buffers but queues at most ONE, so every late call permanently costs depth and
nothing rebuilds it. Only recreating the port resets it — hence "restarting the
emulator fixes it". `BUFFER_QUEUE_THRESHOLD` existed for this and was never
referenced. Now tops back up to a fixed target with silence (self-limiting).
**NOT confirmed to be Donnie's crackle.** Discriminator, 5 seconds, when it is
audibly crackling: **drop the emulator volume slider to 50%.** Instant fix =
clipping (Main+BGM summed with no float limiter); no change = the queue.
Doc: `docs/research/shadps4-audio-queue-ratchet-20260829.md`.

### 4. Trophy shelf — FIXED (`15956d1`), now reads 11/40

`tools/ps4-trophies` globbed the right directory then discarded every file:
the filter needed the SERIAL in the path, but shadPS4 writes
`home/<user>/trophy/NPWR05818_00.xml`, named by the **NP comm id**.
`game_data/<serial>/` does not exist on this build at all. The skip also ran
before the `.xml` test so nothing reached `unknown` — the diagnostic said "no
unlock data" with no paths, which read as "no trophies earned yet" for weeks.
**Not a cache fault**: the JSON was fresh, correct-looking and empty.
`np_comm_id()` returns BYTES — decode before comparing or it raises TypeError.

### 5. Frame rate: UNRESOLVED — do not assert either way

Measured **188,951 frames, median 60.0 fps** (p5 59.9, p95 60.2) and MangoHud
counts emulator presents, not display refreshes. BUT the current session's log
applies five patches and **no 60fps patch**. Unreconciled. **Decisive test not
run: launch with `--show-fps`** (counts game frames). I asserted "not 60fps"
from a config file, then flip-flopped on a log line from an OLD session —
`shad_log.txt` is APPEND-MODE and 684k lines deep, **always bound a grep to the
current session.** The 28 Aug cutscene-hang "known 60fps issue" call is
withdrawn and back to open.

### 6. Bloodborne companion — ledger is current

`docs/research/bloodborne-progress.md`, updated every milestone this session.
He is post-Amelia (night), in the Forbidden Woods, level 43, Saw Cleaver +6.
**Standing rule tightened: never SAY "that's vanilla / not a bug" — he asked
twice.** Housing: Adella + Arianna + Lonely Old Dame at the chapel, the
Narrow-minded Man at Iosefka's. Open: the beggar (fight or leave, clock is the
Blood Moon), the woods sweep under the agreed tiered-hint protocol, and
**Eileen's next beat at the Grand Cathedral after Rom is MINE to raise.**
The Old Hunters DLC IS installed (`/home/ds2000/games/ps4/bloodborne/DLC`).

Deliberately uncommitted, standing convention: `data/`, `shadow/`,
`recordings/` runtime artefacts. **Also inherited-uncommitted and NOT mine:**
`tools/game-quiet` + `tools/test_game_quiet.py` (+344 lines, a third
ambush-noise source) — predates this session, left alone deliberately.

## ▶ Previous (26 Aug 2026 ~22:20 — marathon handoff: sounds, switcher, codex, zombie pids, lamp saga, companion)

Three-day session (24-26 Aug). Everything below "Previous" blocks is detailed
per-track; this is the pickup order:

1. **[A] MemoryMax for claude-sessions — DONE 26 Aug 23:07**: drop-in
   `~/.config/systemd/user/claude-sessions.service.d/memory.conf` sets
   MemoryHigh=6G MemoryMax=8G MemorySwapMax=2G (High kept below Max so the
   throttle phase exists; overrides the unit's own 12G/16G rail). Verified
   applied to the LIVE cgroup without a restart.
2. **BB crash: watcher ARMED 26 Aug 23:09** — `tools/bb-crash-watch` +
   user unit `bb-crash-watch.service` (enabled, running, armed on the live
   session). Trigger: emulator gone while /tmp/game-session persists (clean
   quit removes the flag FIRST, seconds before death - verified ordering in
   game-launch's EXIT trap l.1463). Snapshot → `data/quit-traces/crash-<ts>/`
   (shad_log + emulator + launcher log tails, kernel journal, save
   mtimes+md5s, newest perf CSV tail, core locations). Validated with a
   dummy proc: crash fires, clean quit doesn't. CORES: no coredumpctl on
   this box; apport writes unpackaged-binary cores to
   `/var/lib/apport/coredump` gated on ulimit (verified live) - the shadps4
   wrapper now sets `ulimit -c unlimited`, effective from the NEXT launch
   (the 23:02 session predates it). A 450KB test core sits in that dir
   (root-owned dir): `sudo rm /var/lib/apport/coredump/core._tmp_claude*bbcw-dummy*`.
   If it repeats at the m23 descent: `tools/bb-bisect clean` (full vanilla)
   to cross, then re-install per the lamp-saga config. Needs BB_BISECT_STAGE
   re-extracted (see tools/bb-bisect header).
3. **gpu-spike mystery — the watcher DID catch it**: 9 snapshots 20:00-20:13
   in `data/perf-logs/gpu-spike-*.txt`. In-game pattern: busy% swings
   12→100 while shadPS4:Main's gfx-engine share stays FLAT at ~58-66% and
   census chatter ~0 - no second process is eating the GPU. Oddest file:
   20:13:47, ~95s AFTER the crash - busy 94% at 3328MHz with NO shadPS4
   alive and every listed client at 0%. presentMode Mailbox→Fifo still the
   next lever (free-run during loads measured: 4372fps presents, 176W).
4. Bloodborne companion service: ledger `docs/research/bloodborne-progress.md`
   (update EVERY milestone), crib `...-nudge-guide-SPOILERS.md` (never quote).
   He is post-Gascoigne, in Cathedral Ward, descending toward m23.

Deliberately uncommitted, standing convention: `data/`, `shadow/`,
`recordings/` runtime artefacts. `data/bb-mod-backups-copy/` (325MB) and
`data/bb-emevd-backups/` are the lamp-saga safety nets - do not clean.

## ▶ Previous: 26 Aug evening — THE LAMP SAGA + the companion service (game-side, all documented elsewhere)

Bloodborne lamps died; a 7-round bisect convicted the mod's talk scripts;
Enhanced now runs MINUS script/. Full story + tools:
`docs/research/bloodborne-lamp-saga-20260826.md`. Donnie's playthrough now
has a spoiler-free nudge service: rules + progress in
`docs/research/bloodborne-progress.md`, assistant-only crib in
`...-nudge-guide-SPOILERS.md` (never quote it to him). Memory:
bloodborne-companion.

Open engineering tails from tonight:
- [A] **MemoryMax for claude-sessions.service** — a claude.exe hit 20.8GB and
  OOM'd the box at 16:19 mid-game. My tooling must not be able to do that.
- [B] GPU-100% mystery during normal gameplay - `tools/gpu-spike-watch`
  armed (self-expires); snapshot lands in data/perf-logs/gpu-spike-*.txt.
  If nothing trips, consider presentMode Mailbox->Fifo (free-run during
  loads confirmed: 4372fps presents, 176W).
- [B] Why the mod's talk scripts break lamps NOW when they worked 24-25 Aug
  (suspect: stuck talk-flow flag from the freeze/OOM day; save-flag reader
  exists: bb-investigation/bb_eventflags.py, slots 12411=170, 12100=50).
- [B] bb-bisect.sh + the extracted mod staging live in the SESSION SCRATCHPAD
  (/tmp) - copy to the repo if they should survive a reboot.
- [B] game-launch quit under a timeout that expires leaves an orphan whose
  restore_on_exit later yanks the screen to Kodi - twice tonight. Guard it.

## ▶ LIVE INCIDENT 26 Aug ~15:45 — "it keeps taking me back to kodi with no control of kodi" — ROOT CAUSE: zombies in game-pids

Donnie, mid-Bloodborne: "i'm trying to get on to bloodborne through the ps tap
and it keeps taking me back to kodi with no control of kodi". Room stranded.

**Recovered live** with `game-launch focus` (game was running the whole time,
just buried). Then found the cause.

**THE FREEZE HAS BEEN FAILING 100% OF THE TIME TODAY.** Effect verdicts for
`freeze`, by day: 21 Aug `confirmed=7`; 22 Aug `confirmed=4 missed=1`; 23 Aug
`confirmed=20 missed=4`; **26 Aug `missed=6`, zero confirmed.**

`game-pids` was returning SEVEN pids for the session: the emulator, two
`tools/bb-event-tail` shells, its `tail -F` and `grep`, a `sleep 2` (a new pid
every two seconds) - and **two ZOMBIES**. couchd predicts a freeze with "all
game pids in state T"; a zombie is `Z` forever, so that prediction was
**structurally unsatisfiable** and every suspend was verdicted `missed`.

The consequence chain, all visible in `shadow/couchd-20260826.jsonl` around
15:43-15:45: tap fires the full switcher batch (set_flag/route_pad/show/
iconify/spawn_guard/show_switcher all CONFIRMED) but the game is never really
suspended, so it keeps re-mapping its window over Kodi (the endless
`RUNNING -> MISSING_WINDOW -> RUNNING` flap every ~4s) and the pad drifts back
to it (`input_ownership: kodi -> game (joystick-disabled)`). Net effect for the
room: Kodi on screen, switcher up, pad answering to a hidden game.

The 22 Aug first-miss lines up with the local dbg build landing - the
`shadps4` wrapper spawns `bb-event-tail` beside the emulator with `$$`, so the
sidecar and everything it leaks lands inside the session tree.

**FIXED** in `~/.local/bin/game-pids`: zombies are walked but excluded from the
answer (and from the exit code). Verified against the live broken session -
seven pids became one. Backup of the original in the session scratchpad.

**STILL OPEN:**
- [A] **Donnie has not re-tested the PS tap yet.** The freeze is now
  *satisfiable*; whether the whole tap experience is right needs his hands.
- [B] `bb-event-tail` should not be in the session tree at all - it is a
  diagnostic sidecar and it leaks zombies. Either exclude our own tooling in
  game-pids (the standing todo item "exclude transient reaper children that
  are not games", now proven real) or have the wrapper start it outside the
  reaper tree. Killing it live cleaned 4 of the 7 pids.
- [B] No unit test for the zombie exclusion - game-pids reads /proc directly
  and has no seam. Verified live instead. Add a seam when it is next touched.
- [B] Honest note on yesterday's `g_tap_resume_due` fix: it did NOT cause this,
  but it removed the accident that was HIDING it. The old self-resume bounced
  him back into the game 350ms after every tap, which papered over a freeze
  that was already failing. Correct fix, uncomfortable timing.

## ▶ Previous (24 Aug 2026 ~13:20 — THE SWITCHER'S SELF-RESUME BUG IS DEAD, and the open is measured end to end)

Donnie: "can we optimise the shit out of the switcher menu. make it instant
and stop when i'm on a game it keeps switching to kodi and stuff and
sometimes when i go off a game it's just sat open".

**The last two are ONE bug and it is fixed.** `couchd/couchd.py`
`g_tap_resume_due` now also requires `binding('double_tap') != 'none'`.
couchd restarted, fix live, 1411 tests pass.

### The bug

Since the 23 Aug rebind (`tap=switcher`, `double_tap=none`) a tap on a
RUNNING game fires the bound switcher action - freeze, set the suspended
flag, hand pad and screen to Kodi, open the dialog. 350ms later
`g_tap_resume_due` re-read the world, saw "a tap, and a paused game", and
resumed it. **The same press.** The game came back on top of the switcher
that was still opening.

That is both halves of the report: the flip to Kodi and straight back, and a
sheet left open underneath, discovered whenever the game finally exited.
Nothing ever closes that dialog, so it just sat there.

Live shape, `shadow/couchd-20260823.jsonl` at 22:07:10 (there are dozens):

```
.156 gesture idle -> down          ps-press
.207 gesture down -> tap-wait      ps-tap-noop
.207 freeze/set_flag/.../show_switcher        gesture:ps-tap
.558 gesture tap-wait -> tap-resume  paused-tap-window-expired
.558 launch resume + show game            gesture:tap-resume
1.249 show_switcher CONFIRMED - foreground already back on the game
```

The guard was level-based over a world **this machine had just changed**.
`gesture.paused_tap_decision` has always said an unpaused tap never reaches
the deferral at all, and that the deferral only exists when there is a
double-tap to escalate to; with it unbound the paused tap already resumes at
the release edge (`g_released_tap_resume`). So the fix restores the intended
pairing rather than inventing a new rule. Re-reading the flag was never the
mistake - re-reading it as if we had not just written it was.

Pinned by three new tests in `couchd/test_reconcile.py` (the bug, the
still-must-work paused tap, and the deferred resume with the double-tap
bound). The bug test reproduces the live log exactly before the fix.

### Speed: what it actually costs, measured

`kodi.log` TIMING lines off an instrumented deployed copy, console idle:

| phase | before | after |
| --- | --- | --- |
| Kodi spins up a fresh interpreter | ~85ms | ~85ms |
| `get_windows` | ~63ms | ~58ms |
| suspended appid + Spotify status | ~12ms serial | ~0ms (alongside) |
| build + show the window | ~16ms | ~16ms |
| **to window created** | **165-205ms** | **144-168ms** |
| entrance animation | 280ms slide / 240ms fade | 170 / 140 |

So ~445ms to a settled sheet, now ~310ms. The animation was the biggest
single item and is six numbers in the window XML if it now reads abrupt.

**Two things tried and REJECTED, recorded so nobody spends the afternoon
again** (both written up in `default.py` above `get_windows` and in
`addon.xml`):

- `<reuselanguageinvoker>` is **inert on this path**. Kodi does not reuse the
  interpreter for a script launched with `Addons.ExecuteAddon`, which is how
  couchd opens the switcher. Proven, not assumed: a marker stashed on `sys`
  came back unset on five consecutive opens.
- Replacing urllib with a raw socket saved **5ms, not the 65 the theory
  predicted**, because the time is not in urllib. `/api/windows` costs a flat
  ~54ms whenever the server's 600ms window cache is cold, which it always is
  by the time you press the button: `server/screen.js` shells out to
  `python3 xinput.py windows` and that subprocess IS the 58ms. A bespoke HTTP
  client in the room's only escape hatch from a game is not worth 5ms, so it
  went back.

**The remaining lever is the server's, not the addon's:** making the window
walk not a per-call subprocess (~54ms, every open). Not attempted - it is a
real change to a tool with many callers. The tempting shortcut, having couchd
warm `/api/windows` concurrently with the addon launch, is NOT safe as it
stands: the warm would observe the world ~85ms earlier than the addon's own
call, i.e. possibly before the iconify lands, and the 600ms cache would then
serve that stale list to the sheet.

### Two things found on the way

- **`tools/gesture-sweep` refuses to run on Donnie's bindings.** It preflights
  "bindings are not the defaults" and stops. His console has not been on the
  default vocabulary since 23 Aug, so the one rig that drives real gestures
  through the live daemon has not covered his actual configuration - and this
  bug lived exactly there. Worth a `--bindings-as-configured` mode.
- **A transient Kodi wedge, new to me:** `Addons.ExecuteAddon` returned OK and
  no script ran at all - not ours, not `script.globalsearch` - while the GUI
  stayed fully responsive to JSON-RPC (windows activated, sounds played). The
  Python invoker alone was dead. `tools/kodi-restart` cleared it. If the
  switcher is ever "not opening" and kodi.log shows nothing, suspect this
  before the addon.

### Verified live, not asserted

Switcher opened, navigated (row -> power bar -> back), a power action
dispatched (`quit` -> tvpoweroff -> "nothing to quit", Steam's 7 processes
untouched, no session flags), and a row pick activated
(`activating 0x5400002 (Kodi)`), latch cleared each time. couchd restarted
into `mode: acting, owns: ['gestures']`, inputproc untouched, Kodi joystick
still enabled.

**NEEDS DONNIE:** the fix is proven in the model and the daemon is running it,
but nobody has tapped a real PS button over a real game since. That is the
test that matters. Also: if part of "it keeps switching to kodi" is
*accidental* taps, that is a separate thing and a settings choice, not a bug -
with `tap=switcher` any brush of the PS button leaves the game. Moving the
switcher back to the double-tap is one settings page away, at the cost of
350ms on a paused-game resume. Uncommitted; say the word.

## ▶ Previous (24 Aug 2026 ~12:30 — UI SOUNDS ARE LIVE: the console has its own noises)

Donnie: "can we add a noise to navigating the menu and selecting a game pls".
**Done and verified on the live sink; nothing is mid-flight.**

The surprise going in: **Kodi was already making a noise.** GUI sounds were on
(`guisoundmode=1`, "only when playback stopped") with the stock
`resource.uisounds.kodi` selected, and recording the HDMI monitor while
sending `Input.Right` caught six clean blips at -13.7 dBFS against a -91 dBFS
silent control. So this was never "add sound", it was "the stock set is a
mixed bag and has nothing to say about launching a game": its cursor peaks at
-15 dBFS and its *select* at -27, i.e. the confirmation you most want to hear
is the quietest thing in the pack.

Also found: seven hand-made wavs had been sitting in
`kodi-addons/resource.uisounds.couch/resources/` since **11 Aug**, untracked,
with **no `addon.xml` and no `sounds.xml`** — so Kodi could never have loaded
them and nobody had ever heard them. They were a good coherent family, ~10 dB
too quiet.

What is live now:

- **`resource.uisounds.couch`** is a real, enabled addon and is the selected
  sound skin (`lookandfeel.soundskin`, survives a Kodi restart). It ships
  `addon.xml`, `resources/sounds.xml`, an icon, and seven wavs.
- **`tools/make-uisounds`** GENERATES those wavs from parameters — length,
  fundamental, glide, envelope, peak dBFS, harmonics — measured off the 11 Aug
  originals. "Make select warmer" or "the tick is too loud" is now a number to
  change, not a re-synthesis. `--check` regenerates to a temp dir and diffs.
  The 11 Aug originals live in `docs/reference/uisounds-originals-20260811/`
  with a table of what changed and why.
- **Mapping** (`resources/sounds.xml`): cursor.wav on up/down/left/right,
  select.wav on select, back.wav on parentdir/previousmenu/back, error.wav on
  error. `in.wav`/`out.wav` ship but are **deliberately unmapped** — Kodi fires
  the action sound AND the window activate/deactivate sound, so wiring the
  swoosh pair means every step back makes two noises at once. The commented
  block in that file says so.
- **Selecting a game plays launch.wav** — a 750ms swell rising 1512→1934 Hz —
  from `_launch_sound()` in `copacetic-helper-patches/games.py`, one statement
  before the `game-launch` handoff. Kodi's own select click fires first from
  the button press and the two are MEANT to overlap: the click is the button,
  the swell is the console taking the machine away. launch.wav ramps in over
  its first 240ms exactly so the click lands in front of it. The Library tile
  is not a launch and stays silent.

Levels, deliberately staged: cursor -16 dBFS (it fires on every d-pad step, so
it has to read as texture), back -12, select/error -10, in/launch -8.

**Verified live, not asserted** (recorded off
`alsa_output.pci-0000_09_00.1.hdmi-stereo-extra2.monitor` and FFT'd):
- nav ticks are OURS, not stock — 1605 Hz, peak exactly -16.0 dBFS (stock's is
  a 15ms broadband click); back came back at 773 Hz / -12.0 dBFS.
- one tick per press: onsets 576ms apart for a 0.6s press loop (the detector
  splits each 55ms tone into a 24ms pair, that is the gate, not a double).
- **the launch swell fired through the real plugin route**: 728ms, peak -8.0
  dBFS, 1512→1852 Hz. To get that without starting a game, the DEPLOYED
  `games.py` had `LAUNCHER` swapped to `/bin/true`, Kodi restarted, the route
  driven with `Addons.ExecuteAddon` (`Files.GetDirectory` rejects a plugin://
  with "Invalid params"), then `tools/deploy-addons` + restart put the real
  launcher back — **confirmed restored**, no stale `/tmp/game-session` or
  `/tmp/game-suspended`, no plugin errors in kodi.log.

Traps banked for next time:
- a new addon dropped into the profile comes up **`enabled: false`**, and
  `Settings.SetSettingValue` on `lookandfeel.soundskin` then **returns `true`
  and silently does nothing**. `Addons.SetAddonEnabled` first, then set it.
- `tools/deploy-addons` copies whole trees, so keeping the source wavs beside
  the generated ones would have shipped a second identical-looking set into
  the profile — a trap for whoever next debugs "why is the tick quiet". Hence
  `docs/reference/`.

Tests: `tools/test_games_launch_sound.py` (8 cases — the sound plays, it plays
BEFORE the handoff, the Library tile is silent, and a missing sound set / a
throwing audio device / an old Kodi with no `playSFX` each still launch the
game). `couchd/.venv/bin/pytest tools/test_games_launch_sound.py
tools/test_games_paused_tile.py -q` → 14 passed.

**NEEDS DONNIE:** it is all measured, none of it is *judged* — nobody has
heard this set on the soundbar. A preview mp3 of the whole family (including
the click+swell overlap as it really happens) was sent in chat. If the tick is
too loud, too quiet, too high or too plasticky, it is one number in
`tools/make-uisounds` then `tools/deploy-addons` + `tools/kodi-restart`.
Uncommitted; say the word.

## ▶ Previous (24 Aug 2026 ~12:00 — BLOODBORNE ENHANCED INSTALLED; its settings system fully reverse-engineered; NEEDS DONNIE in-game)

**Nothing is mid-flight. No repo code changed this session** — this was a
mod install plus an investigation. The console is exactly as 23 Aug left it.
Committed: `8860383` (this block + the research doc). **Deliberately left
uncommitted, unchanged by this session and inherited from 23 Aug:** the
untracked runtime artefacts under `data/` (perf-logs, save-backups,
gamescope-soak, quit-traces, autosave-rig) and the `shadow/*.jsonl` logs.
They are not in `.gitignore`, so they will keep showing in `git status` —
standing tidy-up, not a blocker.

**THE EXACT NEXT STEP is unchanged from last session** (this session did
not touch it): the controlled A/B for the shadPS4 fault-batching v2 patch,
```
cd ~/src/shadps4-dbg && ./soak-v2.sh stock 180 && ./soak-v2.sh v2 180 \
  && ./score-frames.py soak-out/stock soak-out/v2
```
See the 23 Aug block below for the full framing.

**BLOODBORNE ENHANCED 0.11.2-fix9 IS INSTALLED** (Nexus mod 19), on top of
the vanilla + Vertex Explosion fix stack. It is a *gameplay* mod: boss
rematches, quick-warp to bosses, vial/bullet restock, lamp menus, big QoL
set. 2422 files replaced (per-file backups), 40 added.
Revert: `bb-mod-install revert BloodborneEnhanced-0.11.2-fix9`.
**NOT PLAY-TESTED.** It is the newest variable since the 21-22 Aug stable
baseline, so it is suspect #1 if a crash or an audio regression appears.

**Install trap, recorded so it is never re-derived:** the archive holds TWO
`dvdroot_ps4` trees (`GAME FILES/` = the mod, `OPTIONAL CHEATS/gems/` = a
replacement gameparam, all-gems cheat). `bb-mod-install` refuses to guess
and errors "multiple dvdroot_ps4 folders". Fix: extract only
`bb_enhanced_0.11.2-fix9/GAME FILES/*`, re-zip that subtree, install that.

**FULL SETTINGS ANALYSIS:
`docs/research/bloodborne-enhanced-settings-20260824.md`** — all 51 settings
with their live values, verified by parsing the *installed*
`common.emevd.dcx` (event 10008400) and cross-checking the mod's own
settings.json: **zero mismatches**. Includes a working Python DCX+EMEVD
parser, the flag encoding, and the parameter-table recipe.

Headline findings:
- **46 of 51 are toggleable in-game** at the **Doll** in the Hunter's Dream
  under **"Enhanced Features"**. The Windows .NET tools are not needed.
- **5 need file-level editing** (Spawn Iosefka Lamp, Advance the Cycle,
  Temporary Stocked Shop, Unlock All Lamps, Activate All Shortcuts) — all
  already correct for a first playthrough, so **no file editing is owed**.
- **Lamp Kindling is a sub-mode of Auto Refill, not a replacement.** The
  restock event gates on the Auto Refill *Enabled* flag first; disabling
  Auto Refill makes kindling silently do nothing. Set BOTH to use kindling.
- **Kindle level is stored PER LAMP** (event parameterised, 126 lamp
  initialisations, 2 bits each). The two "global counters" that look like
  the kindle store are scratch registers for current vial/bullet counts.
- A **native Linux settings editor is feasible and was proven, not built**:
  DCX is plain zlib and every edit is a same-length int swap. Round-trip
  returned a byte-identical payload. Offered to Donnie, not taken up.

**▶ NEEDS DONNIE — in-game, at the Doll, whenever he next plays.** These
are decisions he made this session; none are applied yet:
1. **Quick Warp to Boss → OFF.** His call: start without it, flip it on if
   runbacks start grating. Safe to toggle mid-playthrough (menu option only,
   no save-state effect). `Quick Warp to Boss Prompt` becomes inert; leave it.
2. **Auto Refill → leave ON** (already on). He raised "20 vials after every
   death feels OP"; the researched answer is that **vanilla already refills
   to 20 from storage after every death**, so the mod removes farming, not
   difficulty. The real change is economic: it deletes the vial echo sink
   (180 echoes early → 900 in NG+), so he will run slightly over-levelled.
   Agreed plan: start generous, flip **Lamp Kindling ON** later if the vial
   economy feels weightless.
3. **Worth flipping early:** `Prime Hunter's Mark: Enhanced Features` → ON,
   so the settings menu opens anywhere instead of Doll-only.
4. **Considered, his call, not decided:** turning OFF `Lamp Menu: Level Up /
   Workshop / Storage / Messengers` so the Hunter's Dream stays the hub the
   game was written around. Keep `Lamp Menu: Warp` on either way.

## ▶ Previous (23 Aug 2026 ~22:30 — STAGE 2 IS LIVE; the shadPS4 fault fix works; the evening of six live bugs)

**Nothing is mid-flight. Everything below is committed and running.**
Donnie went to bed on a working console.

**THE EXACT NEXT STEP, when the box is free (it can run unattended):**
the controlled A/B for the shadPS4 fault-batching v2 patch, which is
the last thing standing between it and an upstream PR:
```
cd ~/src/shadps4-dbg && ./soak-v2.sh stock 180 && ./soak-v2.sh v2 180 \
  && ./score-frames.py soak-out/stock soak-out/v2
```
Foreground only; it refuses to start if a shadps4 is running. Then
sweep `SHADPS4_FAULT_CLAIM_WINDOW_KB=16|64|256|1024` (no rebuild —
Xenia measured 256KB as their sweet spot, we default to 64KB and are
claiming 12.8 of a possible 16 pages). Design + results:
`docs/research/fault-batching-redesign-20260823.md`.

**STAGE 2 WENT LIVE ~18:39** (owns.conf = "gestures input"). couchd
owns the pad, Steam never hears the guide press again, bug #9's whole
mechanism is dead, and force feedback reaches the DualSense for the
first time ("i felt one rumble on my controller for the first time").
Panic lever unchanged: `sudo couchd-input-release`. Five levers now:
gestures OWNED, input OWNED, reconcile/transitions/guard still legacy.

**THE PS BUTTON WAS REBOUND** (Donnie's call: "i'm probably not going
to be going to the home menu a lot as it's not actually a ps4"):
tap = switcher, hold = home, double-tap = NOTHING. Unbinding the
double-tap is what makes taps instant — no 350ms window to wait out —
and Kodi now LEADS the switcher's list because the tap opens it.
Settings page in Kodi changes any of this; old values backed up at
`data/save-backups/switcher-settings.pre-tap-switcher.xml`.

**SIX LIVE BUGS, all found by playing, all fixed and committed:**
1. `e55f8e2` doubled input (sticky udev TAGS defeat TAG-="uaccess"; the
   new 74-rule setfacl-strips the ACL *after* the uaccess builtin) +
   the switcher's Steam row losing a raise fight with the kodi guard.
2. `e2ae776`/`a862aba` owns.py and kodiprofile resolved paths under
   `$HOME` while inputproc runs as couchd-input with HOME=/nonexistent
   — so the flip was silently refused, and then bound taps were
   replayed at the vpad and opened Big Picture's menu.
3. `1805562` a ~100ms tap fits inside one decision pass, so press and
   release landed between two looks and the tap VANISHED. The 5 Aug
   coalesced fixes covered holds and double-taps, never the single tap.
4. `80f21f2` the curtain had been crashing 25ms after every show since
   a mangled edit ate `self.spin = None` — so the freeze-frame feature
   has never once worked until tonight.
5. `8b3cf47` Steam Input's mirror pad ("Microsoft X-Box 360 pad 0")
   fed Kodi a second copy of every press; its js node is now fenced.
6. `942752d` **THE BAD ONE — it cost a Bloodborne death.** couchd's pid
   resolver knew only shadPS4's AppImage names, so a LOCAL-BUILD
   session read as zero processes and the escape gesture took the
   screen WITHOUT freezing the game. game-pids learned this on 22 Aug;
   couchd's in-process copy never did. Both now share one predicate.

**THE SUSPEND/RESUME IS A REAL ANIMATION NOW** (`2fff89f`, `4df3eae`,
`eff106d`, `18df11b`, `fe7e812`): the paused card grows to fullscreen
on resume (the PS5 maximise, mirroring the 14 Aug minimise), the warm
curtain takes over the same frame in 54ms instead of rebuilding it in
1.15s, and the whole resume is 1.66s with every millisecond animated.
The minimise had ALSO been invisible since the frame went 4K — Kodi
was still decoding the jpg when the animation ran — so the trigger now
follows the path by 0.45s.

**AUDIO, three variants heard and one kept** (`3598e37`): SDL's own
7.1→stereo fold takes LFE at full level, so impacts came out ~10dB hot
("crashing in to boxes is super loud"); leaving the card on 7.1 gives
the soundbar a discrete LFE it can't reproduce ("completely flat");
emulator opens 8ch + card on stereo puts the fold in PipeWire with
proper coefficients — kept. The shim now does that dance itself.
Separately, spotifyd's eARC crackle was its 16-bit output: `F32` fixed
it, and `tools/spotify-heal` (`d79f002`) now restarts spotifyd when its
websocket dies silently, as it had for 40 hours.

**THE FAULT-STORM FIX, v2** (`276ab19`): v1 was killed today for
corrupting rendering — it widened the *claim*, so guest RAM was
declared authoritative over pages the GPU owned (black entities,
multicoloured corpse). v2 widens only the *protection work*, never the
claim, and only over pages provably identical in RAM and on the card,
so that failure is unreachable by construction. Live: 5,308 faults/s
against ~48,000 stock, fault time 13% of a core against ~85%, and 15
minutes of clean play. **Donnie reports it "always smooth" where stock
"didn't feel smooth at parts" — and the logs do NOT show that**
(frametime, jitter, per-window variance and hitch rate are all
statistically indistinguishable). Unresolved, and honestly so: either
it is input latency / present pacing that MangoHud cannot see, or it
is expectation. Worth measuring properly before any upstream claim.

**NEEDS DONNIE:** bluetooth.ko rebuild for kernel 7.0.0-30 BEFORE the
next reboot (or pin -29 in grub) — this has been owed all day; the
`perf` confirmation of the fault cost model needs root:
`sudo perf stat -e page-faults,syscalls:sys_enter_mprotect -p $(pgrep -f shadps4) -- sleep 10`;
PiP scrubber on the real phone; the Big Picture shell experiment; 2001
resume position if he remembers it; memtest still never run.

**A Kodi restart is owed** (not urgent): the switcher's self-healing
latch (`adc29b6`) is deployed but Python addons only load at start.
The stale latch that wedged the double-tap tonight is already cleared
by hand.

## ▶ Previous (23 Aug 2026 ~10:30 — STAGE 2 ARMED MID-FLIP; the afternoon of PiP controls, TV-cast resume fix, and the shell question)

**THE EXACT NEXT STEP: Donnie turns the pad ON (one PS press).** Then:
(1) verify the fence on the real nodes: getfacl on the pad's event/js
devices must show group couchd-input rw, NO ds2000 ACL, and udevadm
CURRENT_TAGS without uaccess; the vpad ('Microsoft X-Box 360 pad')
appears; Steam adopts it (E2's essence). (2) The flip: edit
couchd/owns.conf to COUCHD_OWNS="gestures input", then Donnie runs
`sudo systemctl restart inputproc`. (3) Live checks: PS tap in a Steam
title opens NO Steam menu; gestures flow via the wire
(/tmp/couchd.log); press counter in shadow/inputproc-*.jsonl matches.
Panic lever at any moment: `sudo couchd-input-release`.

**Stage-1 state (all green, ~10:15):** armed rules live (0254174),
inputproc enabled + running as a FORWARDER, evidence JSONL writing,
EPP unit installed+enabled, bison in, ReBAR verified ON (16G BAR -
memory corrected, Donnie had flipped it ~20 Aug). THE TRAP FOUND AND
FIXED (717d707): couchd's user unit ran ProtectSystem=strict inside an
implicit user namespace, so SO_PEERCRED read inputproc as nobody/65534
and the supervisor wire flapped every 30s - mount-sandbox options
removed, wire authenticates as couchd-input and holds. Pre-flight also
done: watcher reconciles from its PermissionError branch, Steam config
backed up (data/steam-config-backups/2026-08-23-pre-stage2), vpad
invisible to all DualSense-scoped checks. Deviations Donnie authorized:
E2 folded into first live minutes; psfuzz/chaos port (F21) skipped.

**The five owns.conf levers after today: gestures OWNED, input OWNED,
reconcile/transitions/guard still legacy.** Next after input settles:
reconcile (gate: run the differ over the shadow archive for the "clean
evening" evidence + Donnie's daytime yes), then transitions (7 yield
sites in game-launch already built), guard last (it shrinks once Steam
stops hearing guide presses).

**Also this session (all committed d465c02..717d707):**
- **TV-cast resume bug fixed:** Play on TV used PlayNow with no start
  ticks - started at zero AND WIPED the item's stored resume point.
  Casts now resume; fromStart:true overrides. COST: Donnie's 2001: A
  Space Odyssey position was wiped by the verification cast before the
  bug was understood (recover: his memory of the position -> set via
  API, or root ssh to dns2's nightly backup). See the new
  couch-tv-cast memory - the whole cast + HDR-auto-route feature had
  no memory and even Donnie forgot it exists.
- **PiP got proper media control:** absolute seek in pipd (45 tests), a
  real draggable scrubber on the phone (Playing.svelte's pointer idiom,
  400ms held-position after release because mpv answers seeks stale),
  and "Play as PiP" on every library item (film button + episode-row
  buttons, /api/pip/start {itemId} through the same containment; server
  107 tests).
- **Pad attribution:** app-initiated connect/disconnect writes
  /tmp/pad-user-action; couchd watches it, quit-trace tapes it (the
  morning's "pad disconnected" was Donnie pressing the app's button).
- **The shell question (decision brewing, nothing built):** Donnie
  watches media on the TV's native Jellyfin app anyway; his lean is
  Big Picture as pad shell + TV apps for media/YouTube + phone as
  glue. Offered: the BP weekend experiment (BB as non-Steam shortcut
  with artwork). The "LIBRARY: BROWSING IS NOT FINISHED" section below
  likely becomes wontfix if BP sticks.

**NEEDS DONNIE (beyond the pad-on):** bluetooth.ko rebuild for kernel
7.0.0-30 BEFORE the next reboot (stock module = pad reconnect bug
returns; or pin -29 in grub); one clean Bloodborne session for the
tripwire verdict (flag armed, cache warm); PiP scrubber/picker on the
real phone; the BP experiment yes/no; 2001 resume position if he
remembers it; memtest still never run.

## ▶ Previous (23 Aug ~09:00 — STAGE 2 ACTIVATION IN FLIGHT, Donnie: "i want to activate that now")

Pre-flight COMPLETE this session: watcher reconciles from its
PermissionError branch (the SR4 patch, outside-repo), Steam config
backed up (data/steam-config-backups/2026-08-23-pre-stage2), couchd
supervisor socket verified listening, panic lever NOPASSWD verified,
pad-connect/tv-waker verified vpad-safe (vpad = 'Microsoft X-Box 360
pad', invisible to every DualSense-scoped check and to the udev fence).
Armed rules file committed: couchd/stage2/72-...rules.armed (0254174).
WAITING ON DONNIE'S 3 SUDO LINES (stage 1: cp rules + udev reload +
enable inputproc, then pad off/on), THEN my forwarder verification
(getfacl + CURRENT_TAGS + evidence JSONL + Steam-adopts-vpad = E2's
essence), THEN the flip (owns.conf gains input + sudo restart
inputproc). Panic lever at any moment: sudo couchd-input-release.
Declared deviations, Donnie-authorized: E2 folded into first live
minutes; psfuzz/chaos port (F21) skipped.

## ▶ Previous (23 Aug 2026 ~07:45 — THE MORNING SHAKEDOWN: launch race + emu-matcher blindness both bit live and are fixed; tripwire A/B ran but is CONTAMINATED, rerun tonight)

Donnie's first fix-build morning found three real bugs in an hour, all
fixed and committed (970bcdb, 0833b1d; game-launch edits outside-repo):

**1. Black/no signal at launch** = the overnight launch-assert setting
4k120 MID-TV-WAKE, racing the HDMI handshake; the sink rejected it and
the CRTC was left with no active mode. Fixed: launch-assert now needs 3s
of link stability, verifies each fix for 6s, auto-reverts to 4K60 if the
sink drops, and its game-window guard actually sees windows now
(_NET_CLIENT_LIST, not toplevels - xfwm4 frames hid every class).

**2. "shadps4 never appeared (60s)" tore down a HEALTHY session.**
game-pids got the 22 Aug local-build fix but game-launch's OWN
emu_running() and close_games kill sites still only knew the AppImage
names. First live fix-build boot = cold shader recompile >60s, launcher
gave up, trap removed the session flag and restored Kodi over the game,
torrents came back mid-session, and the reconcilers kept yanking Donnie
to Kodi. Fixed: ONE variable EMU_PAT in game-launch
('Shadps4-sdl|mount_Shadps|^~/src/shadps4-dbg/build/shadps4'), used by
all 7 sites. THE LESSON, now in full: a new emulator binary must be
added to EVERY matcher - game-pids AND game-launch - before its first
live session; grep for the old pattern, don't trust one fix.

**3. quit-sweep false alarm + zombie bug** (from the first real traces):
verify now gives stragglers 3s to die on their own (bb-event-tail's 2s
poll lost the race and got called a LEAK), and zombies read as dead
(verify used to TERM corpses and report leaks forever). The 07:29 quit
trace reads CLEAN end to end - quit-trace works.

**THE TRIPWIRE A/B (bb-drop-report, session 07:22-07:29): PROMISING BUT
CONTAMINATED - do not call the verdict.** 6m53s, avg 60.0, 1% low 26.
The 1% low is one 35s shader-compile storm at 01:51 (cold cache on the
new binary, one-time) plus blips while the box was UNQUIET (bug 2 had
resumed torrents+whisper for the first 4 minutes). The tail after 04:49
was drop-free 60.0 ("smooth as butter"). THE HEADLINE: **no ~20s
autosave cadence anywhere in the session** - the metronome the fix
targets is absent. Save backed up pre-session
(data/save-backups/2026-08-23-pre-tripwire-ab). TONIGHT: same flags
(shadps4-local-build stays ON, cache now warm, box quiet), one proper
session, then the adoption verdict + probe-strip + upstream.

**PAD: the "lost control" at 07:28 was a real DISCONNECT** (couchd:
pad-disconnected 07:28:20), on top of connect trouble pre-session.
The patched bluetooth.ko for 7.0.0-29 looks intact (rebuilt 12 Aug),
battery is the cheap suspect - BUT **kernel 7.0.0-30 is INSTALLED and
waiting: the next reboot boots a STOCK bluetooth.ko and the pad
reconnect bug returns. Rebuild the patch for -30 before/at next reboot
(homelab-ps5-pad-bluetooth memory), or pin -29 in grub.**

Room state on leaving: game quit cleanly (autosaved to the last ~20s),
TV off (Donnie, manually), flags clean, torrents/whisper restored by
the one-shot janitor, second quit-trace artifact archived.

## ▶ Previous resume block (23 Aug 2026 ~00:20 — THE OVERNIGHT SHIFT: PiP is a real feature, four bugs fixed, two gamescope soaks in flight)

Donnie went to bed ~22:45 after "it works really well except the mouse
shows now and i can't control the media from the app", then "look in to
what you can add or fix with this and with the bloodborne stuff and work
until everything is fixed". Everything below is committed (8a9261b..
426fb71) and tested; the TV never woke.

**PiP IS NOW A COMPLETE PHONE FEATURE, running on BARE X11 (no gamescope
needed).** The 9 Aug pipd ran unmodified on :0 over live Bloodborne -
xfwm4's compositor is ON, so the ARGB overlay composites; screenshot-
verified at native 4K. Tonight's additions: (1) mpv IPC + play/pause/
seek/volume/mute on the socket, server routes, and a transport row +
volume slider + time readout in the phone panel (explicit play/pause,
never a toggle); (2) invisible cursor baked into both overlay windows
(the desktop arrow appeared over the game - Donnie saw it); (3) the
window auto-adopts the video's real shape (classic Simpsons is 4:3; the
16:9 default drew opaque black pillars); (4) a 2s restack loop so a
game-window raise can't bury the picture (Xvfb-tested); (5) START FROM
THE PHONE (agent build, ab945ea): Films/TV picker (Kodi titles +
Jellyfin path resolution - the library is all plugin:// URLs, paths come
from one batched Jellyfin /Items call), POST /api/pip/start spawns pipd
detached with double containment checks on the path, 409 when one is
up; (6) /start reads the /tmp/game-gamescope display bridge first, so
PiP lands on the nested display the day the rail returns. Suites: pipd
41, server 101, all green. pipd is STOPPED right now; start one from
the phone's Games tab.

**NEEDS DONNIE (PiP):** the picker and transport by eye on the real
iPhone (headless-verified only); the drag on iOS Safari (never tested
on-device); whether game feel changes with a picture up (the overlay
blocks xfwm4's fullscreen unredirect, so the game is COMPOSITED while
PiP is up - MangoHud showed GPU 58->65% tonight); the audio question
(both sources mix on the soundbar; mpv volume/mute is now on the phone
panel, headphone routing still undecided).

**CLOSE FORENSICS (23 Aug morning, Donnie: "set something up so you can
see exactly what happens when the game closes"): tools/quit-trace
(7a4ab4b, 11 tests) records every close** - process states at 4Hz
(roster + game-world patterns + descendant closure, reparent-proof),
EWMH windows, flag lifecycle, game-launch's steps as marks - one
artifact per close in data/quit-traces/, `tools/quit-trace report` for
the merged timeline + survivor list. Hooked in game-launch: close_games
(commanded quits, marks at thaw/WM_DELETE/sweeps/emu TERM-KILL) AND
each mode's self-exit detection (the path the ER leak used), done in
the EXIT trap, 45s post-window for late deaths. Smoke-tested twice;
first real artifact arrives with the next game quit. Traps learned:
Steam's idle client tree must not seed the tracker (reaper's closure
covers real games), and xfwm4 frames hide classes from toplevel walks.

**THE 21:42 "ELDEN RING OUT OF NOWHERE" IS FIXED, and the todo's first
read of it was WRONG.** The shadow log (couchd-20260822.jsonl, seq
~111810) shows /tmp/game-suspended='1245620' ON DISK at the tap - 23h-
old debris, not process memory; the resume path deletes the flag before
SIGCONT, which is why a later check found it absent. Two fixes landed:
(1) couchd (8a9261b, deployed + restarted): both tap-resume predicates
veto a suspend flag that names a different game than the live session
(foreign_suspend); three replay tests built from the shadow corpus.
(2) The leak that CREATED the debris (af039a3): tools/quit-sweep (8
tests) records every pid a quit intends to end (with start times,
pid-reuse-safe) and verifies each died after the graces - TERM, 10s,
KILL for survivors; wired into close_games in ~/.local/bin/game-launch
(outside-repo edit, bash -n checked).

**THE 4K60 LAUNCH RACE IS FIXED (ecca723).** mode-keeper grew
--launch-assert: game-launch backgrounds it right after writing the
session flag; it reasserts 4k120 through the TV-wake hotplug settle for
15s, ignoring the game gate its caller vouches for, and stops dead if a
game-class window maps. Dry-run verified on the live display;
mode-keeper.service restarted. REAL verification = next phone launch
with the TV asleep: /tmp/game-launch.log should show launch-assert
lines and the session should hold 120Hz.

**SOAK 1 VERDICT (01:52): stock 3.16.25 SURVIVED 3h in-game at 4K120
headless - the crash does NOT reproduce on the headless backend in 3h.**
That is the weak-evidence branch: it does not clear 3.16.25 (the live
crash was on the SDL backend presenting a real 4K120 stream, which
headless cannot exercise), it just means headless soaking cannot
discriminate. Teardown clean (joystick + watcher restored). soak120-2
(fix build, verified launching src/gamescope-fix/build) started 01:52:45.

**SOAK 2 VERDICT (04:57): the FIX BUILD also SURVIVED 3h in-game at
4K120 headless; chain exited 0, teardown clean both times, zero strays,
MangoHud CSVs for both runs in data/gamescope-soak/.** Net: headless
cannot reproduce the SDL-backend crash, so the soaks cannot discriminate
- but the fix build is proven stable under everything headless can
throw, and the bug it fixes is real upstream (an unbounded layer-array
write, the exact malloc-corruption shape). RECOMMENDATION: when you
want the rail back, run the wrap on the fix build for a supervised
evening: `touch ~/couch/data/gamescope-fix-build` (the new lever in
game-launch, logs "FIX BUILD e42aa76" at launch) then
`touch ~/couch/data/gamescope-shadps4-enabled`. First crash = rm both,
you are back to bare in one launch. The -r 60 interim remains the
conservative alternative. Re-enabling is YOUR call - it risks a live
session, and headless proved nothing about the crash path.

**GAMESCOPE: TWO SOAKS RAN OVERNIGHT (both done by 05:00).**
soak120-1 = stock 3.16.25, headless 3840x2160@120, isolated dbg-userdir,
fake-pad in-game since 22:52, 3h; results in
~/couch/data/gamescope-soak/. A chain script then runs soak120-2 with
**~/src/gamescope-fix/build/src** (via GSWRAP_GAMESCOPE_DIR): that is
3.16.25 + upstream 6ab4a7d cherry-picked (local commit e42aa76),
"rendervulkan: bound FrameInfo_t layers behind a stack - a frame with
enough planes could write past the array", which is the EXACT shape of
the 22:16 heap corruption (first 4K120 session, rail overlay plane in
frame, malloc corruption abort). Read the soak logs before touching the
wrap flag. Decision tree: soak1 crashes + soak2 survives -> the fix is
confirmed, run the wrap on the fix build (rail back); both survive ->
headless doesn't repro the SDL-backend path, consider the fix build
anyway (the bug is real upstream) or -r 60 interim; soak1 survives 3h
is NOT proof of absence. Full master build is BLOCKED on bison (sudo
apt install bison) - wlroots 0.20 needs xkbcommon>=1.8 built from wrap.
Build recipe that works (worktrees): copy wayland/pixman wraps from
~/src/gamescope/subprojects, apply the protocol/meson.build scanner
patch, PKG_CONFIG_PATH=~/src/prefix/lib/pkgconfig:~/src/prefix/xwayland/
usr/lib/x86_64-linux-gnu/pkgconfig, then the option set from
~/src/gamescope/build/meson-logs/meson-log.txt (force_fallback_for=
libliftoff,vkroots,wayland,pixman).

**Upstream drafts WRITTEN (not filed, gated on the bare A/B):**
docs/research/upstream-issue-draft-fault-storm.md, upstream-pr-draft-
fault-widening.md, upstream-issue-draft-write-path-gap.md. Note in the
PR draft: the fix-side "1.4k faults/s" is the optimistic end of the
census spread (fix1c bursts to 5-6.7k/tick); the drafts claim the order
of magnitude, which holds.

**NEEDS DONNIE (sudo, ~2 min, plain commands):**
- Pin performance EPP across reboots (staged tonight, mirrors couch-4k120):
  sudo cp ~/couch/tools/systemd/couch-epp-performance.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now couch-epp-performance.service
- For future gamescope-master builds: sudo apt install bison
- Still standing: ReBAR + Above-4G in BIOS (rerun/verify EPP after - the
  unit above now covers it), memtest never run, the stage-2 udev re-arm
  paste, and the bare fix-build Bloodborne session (touch
  ~/couch/data/shadps4-local-build, play, bb-drop-report).

## ▶ Previous resume block (22 Aug 2026 ~23:00 — END STATE: bare stock stack is the BEST SESSION ON RECORD; fix build and gamescope both benched with exact retest plans)

**WHERE THINGS LANDED tonight, after a chaotic play test:** Donnie's final
session (stock AppImage, NO gamescope wrap, 4K120 display, performance
EPP, game-mode active) = **avg 60.0, 1% low 55.7 (previous best 49), five
sub-50ms drops total, and the ~20s autosave metronome NOT VISIBLE in the
data**. Donnie: "i didn't feel any hitches in that run. also it loaded a
lot faster." The platform fixes alone (EPP + no compositor + quiet box +
warm pipeline cache) carried most of the felt win.

**CURRENT SWITCH STATE (all deliberate):**
- `data/shadps4-local-build` ABSENT -> stock AppImage. The fault-widening
  build is EXONERATED of tonight's crashes (all three were console/
  gamescope bugs, see below) but its adoption case now needs a fair BARE
  retest: one session with `touch ~/couch/data/shadps4-local-build`, no
  other changes, compare bb-drop-report + feel vs tonight's baseline.
- `data/gamescope-shadps4-enabled` ABSENT -> bare launches, resident rail
  OFFLINE. gamescope 3.16.25 heap-corruption-aborted at its first-ever
  4K120 session (see the 💥 block). Before re-enabling: headless soak at
  -r 120 (rig exists: gamescope-wrap --backend headless --rate 120 +
  emulator, hours), and/or try a newer gamescope, and/or run the wrap at
  -r 60 as interim (rail back, smaller crash surface).

**NEXT STEPS in order:** (1) gamescope-at-120 headless soak -> decide
fix/upgrade/60Hz-interim; (2) bare fix-build session with Donnie ->
adoption verdict; (3) if adopted: strip the three probes, upstream
issue+PR (fault-widening + the write-path correctness gap + the 48k/s
census numbers); (4) the two couchd replay tests owed (stale tap-resume,
ER process leak - see 🐞 block); (5) game-launch should restore 4k120
BEFORE reading the mode at launch (race documented below).

**NEEDS DONNIE:** ReBAR + Above-4G in BIOS (NOTE: that reboot also resets
performance EPP - rerun the tee one-liner after, or ask for the pinning
unit); the bare fix-build session above; memtest is STILL never run.

**Living outside this repo (committed nowhere, by convention):** the 22 Aug
edits to `~/.local/bin/game-launch` (game-quiet hooks), `~/.local/bin/shadps4`
(local-build flag + MangoHud + pin lever + bb-event-tail), `~/.local/bin/
game-pids` (local-build first-token match), `~/.config/systemd/user/
mode-keeper.service`, and the shadPS4 checkout `~/src/shadps4-dbg` (fault
widening + 3 probes as uncommitted local diffs; audio-era work in `git
stash`). Untracked here and deliberately left: shadow/ data churn, data/
perf-logs + autosave-rig outputs, and kodi-addons/resource.uisounds.couch
(predates 21 Aug, unknown owner - triage some quiet day).

Full receipts: **docs/research/shadps4-autosave-fault-storm-20260822.md**
(measurements, the falsified-then-inverted hypothesis, fix, A/B table,
residual risks). The one-paragraph version: the autosave stall was the tip
of a permanent **48,000 faults/s page-fault storm** (0.85 CPU cores burned
all through gameplay - the emulator invalidates 8 BYTES per tracked-page
write fault). Our fix: widen to an aligned 64KB window with a precise
fallback (correctness-safe superset). A/B headless: faults 48k->1.4k/s,
handler time 850->40ms/s, all autosave cycles clean (worst 19.5ms vs
53-62ms stalls), steady 60.

**TO GO LIVE (Donnie, one command):** `touch ~/couch/data/shadps4-local-build`
then launch BB normally - the wrapper runs our fix build (same 0.17.0
release, same config/saves). `rm` the flag = instant AppImage rollback.
Judge: autosave blink gone? combat headroom better? any NEW visual
weirdness (over-invalidation would look like texture flicker; none seen
headless). bb-drop-report after the session as usual. THEN: strip the
probes, upstream issue+PR (also report the write-path correctness gap the
source dive found: file writes never download GPU-modified guest data).

**💥 THIRD FAILURE (22:16) = GAMESCOPE 3.16.25 HEAP CORRUPTION AT 4K120,
wrap BENCHED for now.** The emulog is unambiguous: gamescope aborted
(glibc "malloc(): unsorted double linked list corrupted", exit -6
SIGABRT) and gamescopereaper then killed the healthy emulator mid-
autosave-write ("Parent of gamescopereaper was killed. Killing
children."). Key context: tonight's sessions were the wrap's FIRST EVER
at -r 120 / 4K120 output - every prior wrapped session actually ran at
4K60 (the display kept falling back before mode-keeper existed). Fix
build NOT implicated in this one. Save survived intact (sizes verified,
backups present). Mitigation: data/gamescope-shadps4-enabled REMOVED -
bare emulator until gamescope-at-120 is proven headless (repro rig:
gamescope -r 120 + emulator + hours-long soak) or gamescope is
upgraded/pinned differently; the resident rail is offline meanwhile.
TO INVESTIGATE: (a) reproduce headless at -r 120, (b) try gamescope
newer release, (c) consider -r 60 wrap on a 120Hz display as interim
(rail back, no crash surface). Also retest the fault-widening build
BARE - with gamescope out of the picture its play test is still owed.

**⚡ ROOT CAUSE OF THE WHOLE 22 Aug EVENING (found 22:15, fixed live):
game-pids was BLIND to the local fix build.** It matches shadPS4 by
AppImage names (`Shadps4-sdl|mount_Shads`); the fix build's cmdline is
`~/src/shadps4-dbg/build/shadps4` = no match = every safety system
believed NO game was running during fix-build sessions. Consequences,
all downstream of this one gap: the watcher's drift repair repeatedly
routed the pad to Kodi and raised Kodi over a HEALTHY game ("went back
to kodi after ~10s"); suspend/resume flows operated on an invisible
session (wedge + double-launch = "crash" #1). FIXED in game-pids:
exact-first-token match for the local binary (never substring - the
pgrep-self-match rule), live-verified against a running session. The
fault-widening build is EXONERATED and re-armed. LESSON for the file:
any alternate emulator binary must be added to game-pids BEFORE its
first live session.

**🐞 TWO LIVE BUGS, 22 Aug 21:42 (Donnie: "blood borne had loaded but
then elden ring appeared? out of nowbere") - replay tests owed:**
(1) **couchd stale tap-resume**: at 21:42:44, one minute into a fresh
shadps4 session, couchd classified a PS tap as tap-resume and
launched+showed appid 1245620 using PAUSE STATE LEFT FROM 21 AUG
(~22:35) - /tmp/game-suspended did NOT exist; the stale state lived in
couchd's 36h-old process memory. The gesture engine must not carry a
resumable appid across session boundaries / flag absence. Timestamps for
the corpus: couchd.log 21:42:44.105-372, 22 Aug.
(2) **ER quit leaked the game process**: eldenring.exe (pid 1015927)
survived the 21 Aug ~22:54 "save and close" quit and sat windowless for
22h49m; the stale resume then MAPPED it (instant appearance). The quit
path's WM_DELETE-then-pkill believed it had won; it had not - Proton's
wine tree needs a deeper liveness check. Cleared live via TERM (clean
exit); BB session was untouched, game-launch focus re-asserted.
ALSO: the TV-wake -> fast-launch race locked this session at 4K60 again
(mode-keeper politely refused mid-game) - game-launch should restore the
mode BEFORE reading it (needs a force/ordering tweak since the session
flag already exists at that point).

**Also shipped 22 Aug evening: GAME-MODE + performance EPP.** (1)
`tools/game-quiet` (41 tests) + wiring in game-launch: every session now
pauses the ACTIVE torrents (exact-set restore, manual pauses respected,
qB 5.x stop/start dialect auto-detected, login success = SID cookie not
body - this box's qB replies 204-empty) and stops whisper-asr, restoring
both on quit; best-effort by contract, can never delay a launch. Live
round-trip verified (22 torrents). (2) Donnie ran the performance-EPP
one-liner (he called it "the rebar stuff" - ReBAR BIOS toggle is STILL
pending, needs a reboot); EPP verified performance on all cores, RESETS
AT REBOOT - offer the pinning unit if he likes it.

Ops notes from the day: the session's BACKGROUND-task plumbing killed two
rig runs deterministically (~273s) - run rigs FOREGROUND; the rig inhibits
pad-home-watcher (its reconcile treats rig state as drift to repair) and
Kodi joystick input; one leftover emulator survived the surgical teardown
once - re-add a precise kill-belt if the rig is promoted from scratchpad.
Isolated everything: live save/config verified untouched (mtimes 21 Aug),
fresh backup at save-backups/2026-08-22-pre-autosave-work. E1 ladder also
COMPLETE from last night (couchd/stage2/e1-results-20260821.md, k=3 green);
udev re-arm paste is STILL PENDING with Donnie.

## ▶ Previous resume block (21 Aug 2026 ~21:45 — BLOODBORNE COMBAT PERF PASS, the staged 15 Aug experiments finally ran)

Donnie asked for Bloodborne "as optimised as possible in a fight / starting
one". The 15 Aug experiment list was run tonight, headless (gamescope
`--backend headless` + SDL_AUDIODRIVER=dummy, TV and Kodi untouched), with a
web-research pass corroborating each lever first. Four ~100s boot tests, all
clean, no strays. **PLAY-TESTED same night, Donnie: "frame drops are far
less common now and i think just happen on new actions" - i.e. what's left
is first-encounter pipeline compiles, which the new disk cache makes
one-time-ever costs, so sessions keep smoothing out. TWO WRINKLES from the
first launch: (1) the game presented so slowly (full shader recompile under
the new patch set) that focus bounced to Kodi; PS press recovered it, and
the pipeline cache should mostly cure the slow present - watch the next
cold launch. (2) THE SILENT-SFX BUG APPEARED on that first session DESPITE
the 0x204E flag being verified 01 at boot (both save copies, set by
game-launch at 21:41:03) - so the flag workaround does NOT cover every
trigger. Clean in-game-menu quit + relaunch was the fix attempt;
outcome unconfirmed. If silence recurs on the upstream patch set, suspect
the 227-poke Performance Patch (precedent: upstream's old fps patch broke
Ebrietas sfx) and A/B against Bloodborne.xml.live-nexus-tasksplit.**

**Live config now (`~/.local/share/shadPS4/config.json`, backup
`config.json.pre-combat-tuning-20260821.bak`):**
- `readbacks_mode` 1 -> 0. #4215: Relaxed degrades BB progressively as map
  assets stream (60 -> 10-30 over a session) - a literal combat-drops bug.
  WATCH FOR: the translucent ghost rectangles Relaxed was set for (seen by
  eye on vanilla, never confirmed fixed). If they return, options are:
  live with them / readbacks 2 (Precise, slower) / the Nexus "Vertex
  Explosion Fix" mod (research says streaming corruption is what readbacks
  actually covers in BB; costs face customisation).
- `extra_dmem_in_mbytes` 0 -> 4096 (log-verified: direct mem 5.25 -> 9.25GB).
  Needed by the upstream res patches' baked-in heap bumps.
- `Log.filter` "Lib.AudioOut:debug" -> "" and `Log.sync` true -> false. The
  audio-debug filter was for the solved sound bug; sync logging flushed on
  the emitting thread and combat is an audio-event storm. Source-verified:
  sync=false routes through spdlog's async sink.
- `Vulkan.pipeline_cache_enabled` false -> true. Last session compiled
  16,371 shaders/pipelines live with NOTHING persisted; this is the on-disk
  store + boot-time WarmUp preload = the fight-start first-encounter hitch
  fix. Proven across two boots: run N cache write, run N+1 "WarmUp:
  Preloaded 24 pipelines", compiles 60 -> 8 on the same boot path. Known
  rough edges are NVIDIA/macOS (#4805/#4878); if post-restart weirdness
  ever appears, `rm -r ~/.local/share/shadPS4/cache/CUSA00900`.

**Live patch set (`patches/shadPS4/Bloodborne.xml`) = the UPSTREAM file, fps
patch OFF - and it BOOTS.** The 15 Aug boot crash was the 60 FPS++
double-patch on the baked-60 eboot (and/or dmem=0), exactly as suspected:
same file with fps off + dmem 4096 ran clean, 301 pokes applied. Enabled:
{Performance Patch (the modern TaskSplit superset - upstream folded
TaskSplit into it Feb 2026 with retuned values), Disable Dynamic Light
Shadows, Resolution 2560x1440, 4k Light Grid (matches the 4K WINDOW, note
says window res not render res), Skip Intro}. Combat ~30fps drops are
CPU-bound light-grid/draw-call generation - these are the two patches aimed
straight at that. **VISUAL TRADE DONNIE HASN'T SEEN: dynamic light shadows
(torch enemies etc.) are OFF.** If he hates it, flip that one entry to
isEnabled="false". Fallbacks in patches/shadPS4/: `.live-nexus-tasksplit`
(today's conservative alternative: old nexus pack + standalone TaskSplit,
also boot-tested), `.pre-combat-tuning-20260821.bak` (what was live before
tonight).

**CPU pinning lever, OFF by default** (in `~/.local/bin/shadps4`): #1542's
+17fps/5-core datum is Dec 2024 and the issue closed as fixed upstream, so
it's an A/B knob only: `echo 0-4 > ~/couch/data/shadps4-pin-cores`, rm to
undo. Affinity verified applying through the wrapper (cpus 0-7 physical,
8-15 SMT twins).

**Bonus: in-game trophies were silently broken** ("Couldn't extract trophy
file", 34 sessions) - keys.json ReleaseTrophyKey was empty; filled from
~/.config/couch/ps4-trophy-key. Log now: "Successfully extracted 65 trophy
files". Vkvalidation_core=true is INERT (source-verified, layer never loads
with validation off) - stop suspecting it.

**FOR DONNIE'S FIRST SESSION:** fps counter is already on. Judge: (1)
fight-start hitches (pipeline cache warm after ~1 session), (2) the
progressive combat sag (readbacks fix), (3) ghost rectangles returning,
(4) how the game looks without dynamic light shadows. Then A/B the pin
file if drops persist.

**PERF INSTRUMENTATION BUILT (21 Aug ~22:30, live from the next launch).**
The tiny --show-fps counter is gone; the shadps4 wrapper now runs MangoHud
(big fps + frame-time graph top-right, config
~/couch/data/mangohud-shadps4.conf) logging every frame to
~/couch/data/perf-logs/, plus tools/bb-event-tail stamping shadPS4's
compile/error lines with wall time (shadPS4's log has none), and
**tools/bb-drop-report** (44 tests) joins them and names each drop's cause:
shader compile / GPU-bound / CPU-engine / unclear. FIRST REAL REPORT (the
22:08 session, CPU pin ON): avg 60, 1% low 49, 11 drops = 3 compiles +
**8 CPU/engine stalls on a ~20s CLOCK** (00:40, 01:01, 01:21, 01:42...) -
suspicion: a periodic background task (docker healthcheck? poller)
preempting the 5 pinned cores. Pin REMOVED after (Donnie: "made it worse");
next unpinned session's report is the A/B. If the 20s ticker survives
unpinned, hunt it - the period makes it findable. ALSO surveyed
box interference: CPU EPP is balance_performance (gave Donnie the sudo
one-liner for performance EPP - not yet run), and the ambush risks are
qBittorrent+unpackerr IO, remote Jellyfin GPU transcodes (donflix tunnel),
and whisper-asr GPU jobs. Proposed-not-built: game-mode in game-launch
(pause torrents + stop whisper for the session).

**THE 20s TICKER IS BLOODBORNE'S AUTOSAVE (caught live ~22:18).** 100s
stakeout: every ~20.5s the SLSession thread unlinks backup0000/0010 and
rewrites userdata0000 (1.3MB, grows with progress) and the 2-frame 34ms
stall follows within a second, 5/5 matches. Research verdict: UNTRACKED
upstream (no issue mentions it), no fsync in the emulator's save path
(io_file Commit has zero callers), no async-save option, no patch exists;
most plausible mechanism per source reading is guest-memory page-tracker
faults during save serialization. Cheap discriminating test if ever
chasing it: toggle the "Disable HTTP Requests" patch (only other periodic
game-side activity). GOOD upstream-issue candidate - we have measurements.
Do NOT get clever with the save path: the game deletes its backups before
rewriting (#4803), a failed write there loses the safety net.

**CONTROLLER LAG (~22:25) = the TV was on 4K60 all session.** The 4k120
modeline had been hotplug-cleared earlier that day and tools/mode-keeper -
built for exactly this - was NEVER RUNNING. Fixed twice over: its
GAME_FLAGS watched /tmp/game-running which nothing writes (now includes
/tmp/game-session, the real file; only the game-pids backstop had
protected live games), and it now runs as user unit mode-keeper.service
(enabled). Verified: refused to touch the mode mid-game, restored 4k120 8s
after quit, Kodi bounced after. Remaining latency levers offered: USB-C
cable to the pad (a few ms vs BT), and a wrap-off A/B session
(rm ~/couch/data/gamescope-shadps4-enabled) to feel gamescope's ~1 frame.
Bose-on-PC BT contention (the 14 Aug pad-lag cause) checked: not present.

**BUG #9 SURFACED LIVE (~22:35, Elden Ring).** First Steam-title session
since the perf work and PS tap pops Steam's BP overlay over the game -
exactly the couch-legacy-bugs-open #9 gap: Steam hears raw guide presses
on hidraw, and the guard's closer stays DISABLED (guard log: "guide press
SKIPPED... 7 Aug suspend incident" x3 on his presses). Gestures themselves
verified healthy in couchd's log (double-tap freeze/switcher, tap-resume,
COUCHD_OWNS=gestures executing). shadPS4 titles never show it (Steam's
menu opens behind gamescope). Workaround told to Donnie: close with
B/circle, NEVER another PS press (that is also a gesture). Real fix =
stage-2 input ownership (couchd/stage2/ is built: inputproc.py + tests,
udev rules, INSTALL.md, E-runbook); next step is Donnie's ~10min sudo
session then E2 per the plan at the bottom of this file. Do NOT re-enable
the synthetic guide press. (vertex-explosion
lines off models after a death/respawn - the thing Relaxed was masking).
Fixed the keeper way: **Nexus Vertex Explosion Fix (mod 109) installed via
bb-mod-install** after the game closed (a Monitor watched for quit; the
installer's in-place `cp` is unsafe under a running game). 144 FaceGen
parts files replaced, per-file backups, NOT a Reborne module. Trade: face
customization disabled (standard hunter face). Revert:
`bb-mod-install revert 'Vertex Explosion fix-109-1-0-1769210766'`.
The game is no longer strictly vanilla - memory updated.

## ▶ Previous resume block (15 Aug 2026 ~02:15 — GAMESCOPE TRACK IS LIVE, the switcher floats over the game)

**The whole stage-3 arc shipped in one night, live-tested with Donnie.**
(Ran CONCURRENTLY with the spotify/deck session below - its deck XML is
exactly what the rail clones; the two interleave cleanly in git.)
Bloodborne runs inside nested gamescope (`beaea0d`, switch file
~/couch/data/gamescope-shadps4-enabled), and double-tap now composites the
SWITCHER OVER THE LIVE GAME - Donnie: "double tap does work". The rail is
`tools/switcher-overlay` (gamescope external-overlay plane, pad read raw
from /dev/input, zero switching logic - same server endpoints as the
phone), agent-restyled into a faithful PIL clone of the deck (`9b47293`)
including the spotify bar (`34857c4`, gated on /api/spotify). couchd's
double-tap recipe branches on two flag bridges (`cfd1bb6`):
/tmp/game-gamescope (the nested display, written by game-launch - Xwayland
reparents to SYSTEMD, so it is found by "any Xwayland that isn't :0",
`da5be71`) and /tmp/switcher-overlay (the rail announcing itself;
want_pad_owner honours it, second double-tap is a no-op). Also fixed live
tonight: the resume flap (tap-resume supersedes the standing kodi guard,
BOTH halves - `8b9b54c`), quit dead-buttons + the emu-only 8s WM_DELETE
burn (`ae48dc8`), the +8s sweep that SIGKILLed the emulator and made the
14 Aug 30s grace dead code (in `beaea0d`), native-res freeze-frames for
the TV (`959cafd`), and the TV's Just Scan was cropping the frame edge
(fixed on the set - it hid the fps counter).

**FPS, where it stands - CORRECTED ~02:30 after re-reading
homelab-bloodborne-mods:** (1) **config.toml IS DEAD on this build; the
live config is `~/.local/share/shadPS4/config.json`** - every toml edit
tonight (dmem keys, logType async) was a dead letter, which is WHY no
"extraDmemInMbytes" line ever appeared. config.json HAS
`General.extra_dmem_in_mbytes` (currently 0) - the heap-bump theory was
right, the file was wrong. (2) **The eboot has 60fps BAKED IN**
(1080p.60fps.MOD pkg) - that is where tonight's "60fps with no patch
enabled" came from, and it makes ANY fps patch on top a double-patch:
upstream `60 FPS++` (192 blind writes) on the modded eboot is now the
PRIME suspect for the boot crash, not (only) the heaps. (3)
`GPU.readbacks_mode = 1` (Relaxed) IS live in config.json (set 14 Aug for
ghost rectangles, unverified) - and shadPS4 #4215 documents progressive
Bloodborne fps degradation under Relaxed, so it is a real combat-drops
suspect. Live now and verified booting ~02:03: safe pack (nexus-84res)
with `[FPS-MODE]: 60 FPS (With Deltatime)` + 1440p + Skip intro - the
fps entry is REDUNDANT on the baked eboot and should come back off at the
next quit. THE NEXT EXPERIMENT, one launch: upstream set {4k Light Grid,
Disable Dynamic Light Shadows, Resolution 2560x1440, Skip Intro} - NO fps
patch - plus config.json extra_dmem_in_mbytes 0 -> 4096. Then, separate
A/Bs in order: readbacks_mode 1 -> 0 (watch for ghost rectangles
returning), taskset pinning (#1542: +17fps on a 5800X3D at 5 cores),
40fps lock via GPU.vblank_frequency=40 (120/3 even cadence). Staged:
patches/shadPS4/Bloodborne.xml.upstream-current-crashes.bak (perf set,
re-edit before use: fps patch OFF), .safe-60fps.bak (live now).

**Rail latency - RESIDENT RAIL BUILT (15 Aug evening, `a2cce1f`), awaiting
Donnie's first live feel.** `switcher-overlay --resident` lives with the
game session: game-launch parks it when the display bridge lands, plane
built UNMAPPED, rows/thumbs/sheet pre-baked to BGRA, control socket at
/tmp/switcher-overlayd.sock (pipd's shape). couchd pokes the socket
(Actuators.rail_show, two-stage ack so a pass never blocks) and falls back
to the one-shot spawn; a spawned one-shot also hands off to a live
resident. PROVEN on a headless 4K gamescope rig (scratchpad
resident-rail-rig): **signal-to-mapped 170ms** with no frame-wait (the
cold spawn was seconds; live suspends still pay pause-snap's real wait -
the log line `show: signal-to-mapped Xms (frame-wait Yms...)` in
/tmp/switcher-overlayd.log separates the two). NEW TRAP FOUND BY THE RIG:
unmapping a once-shown external overlay does NOT hide it - steamcompmgr
never clears the commit (literal `// TODO clear done commits here?`) and
the overlay pick ignores map state; the paint IS gated on
`externalOverlay->opacity`, so hide = _NET_WM_WINDOW_OPACITY 0 (+ unmap
for honesty). Flag contract unchanged: /tmp/switcher-overlay = mapped-and-
owning-the-pad only. Teardown: game-launch TERMs the pidfile (cmdline-
verified) before gamescope's grace; the resident also retires itself when
the bridge clears or the nested display dies. Cheap wins in the same
commit: second full-sheet draw dropped, ThumbCache.

**Watch items:** freeze under the wrap leaves gamescope UNFROZEN (the
compositor keeps drawing - better shape, but the §6 freeze ruling is still
formally Donnie's); the logType-async claim was a dead letter (config.toml
is dead - logging is still sync via config.json defaults); pgrep/pkill
SELF-MATCH burned this session THREE times (harness shell contains the
pattern) - always bracket: `pgrep -f '[S]hadps4'`.

**NEEDS DONNIE:** (1) combat fps verdict on the current safe setup;
(2) the one-launch perf experiment go-ahead (staged above); (3) did you
ever actually SEE the ghost rectangles readbacks=Relaxed was set for? If
not, it comes off; (4) the §6 freeze-shape ruling is now live behaviour -
bless or veto; (5) rail look/feel notes after a few days of use;
(6) NEW: double-tap on the next wrapped launch - it should feel instant
now (resident rail); if it still lags, read the `signal-to-mapped` line in
/tmp/switcher-overlayd.log before blaming the rail: frame-wait is
pause-snap's time, not the rail's.

## ▶ Previous resume block (15 Aug 2026 ~01:20 — SPOTIFY LIVE + THE SWITCHER DECK; next: GAMESCOPE, unchanged)

**This session: the box is a Spotify Connect speaker, and the switcher got
its "deck" redesign.** All committed (3a0e256 spotify server, a051cc0 deck,
8135b9c display-dialog filter). Deep detail in auto-memory
`homelab-spotify-connect.md` - read it before touching spotifyd or the bar.

- **Spotify**: spotifyd v0.4.2 at `~/.local/bin/spotifyd`, user unit
  `spotifyd.service`, conf at `~/.config/spotifyd/spotifyd.conf`. Phone picks
  "Couch" in the Spotify app (zeroconf, Premium, no stored login). Server:
  `server/spotify.js` -> `/api/spotify`. TRAPS: MPRIS name only exists while
  a session is live; PlayPause is a toggle that RACES its own read-back -
  send explicit play/pause, draw labels from intent.
- **The deck** (script.couch.switcher, deployed by rsync to
  `~/.var/app/tv.kodi.Kodi/data/addons/`): no sheet, PIL-baked gradient
  scrim over the freeze-frame, white-inversion focus, icon media pills
  (play/pause first), `_join_strip` makes power+spotify one continuous bar,
  `pretty_title` turns shadPS4 window titles into game names. 30 tests in
  `tools/test_switcher_dialog.py`; every state verified on screenshots off
  the live render at native 4K.
- **Display popups dead**: xfconf displays /Notify=0 AND screen.js filters
  `xfce4-display-settings` from `/api/windows` (belt + braces; the xfconf
  bit reverts if xfce settings reset).
- CAPTURE RECIPE that worked (memory-worthy): kodi-send RunScript to open
  the dialog behind a running game, `TakeScreenshot(special://temp/x.png,sync)`
  (lands in `~/.var/app/tv.kodi.Kodi/data/temp/`), Action(Back) to close;
  assert state via GUI.GetProperties currentcontrol first. NEVER leave the
  dialog open - Donnie's pad drives it invisibly. Read tool auto-boosts
  near-black pixels: measure luminance before believing faint "ghosting".

**► THE EXACT NEXT STEP is unchanged from the previous block: the gamescope
track** ("double tap takes me away from bloodborne when ideally it would
show on top") - plan `gamescope-wrap` into `game-launch shadps4`, test with
Donnie at the TV. See the previous resume block below for the full standing
start; `data/gamescope-shadps4-enabled` (untracked flag file) is that
track's, not this session's.

### ▶ NEEDS DONNIE (this session's additions)
1. **The deck by eye**: entrance/close motion feel (static frames proved
   layout, not motion), the icon pills at couch distance, and whether the
   fully-opaque lower scrim reads right over a real paused game.
2. **Headphone crackle checklist** (BT to the LG C5; TV is WIRED, ruled
   that out): (a) next crackle, note if you're playing media stored on the
   USB disks - USB3 enclosures jam 2.4GHz; (b) forget + re-pair headphones
   on the TV; (c) make sure TV sound output isn't in a "Bluetooth + X" dual
   mode; (d) TV firmware check. Offer stands: report crackle times and the
   box can correlate against disk I/O.
3. Carried from previous block: readbacks verdict, games-row motion, fan
   curve, GPU pin revert, memtest.

## ▶ Previous resume block (15 Aug 2026 ~00:30 — BLOODBORNE FULLY WORKING; next: GAMESCOPE)

**NEXT TRACK, asked for by Donnie in his own words: the switcher OVER a live
game.** "double tap takes me away from bloodborne when ideally it would show
on top." That is the gamescope build: run shadPS4 (Bloodborne first) inside
gamescope so Kodi's switcher dialog can composite over the running game.
Standing start: `gamescope-wrap` is committed (couchd stage 3), and
`tools/pip-gamescope-rig` PROVED overlay-over-game composition works on this
box (9 Aug, headless). Plan the wrap into `game-launch shadps4`, test with
Donnie at the TV, watch for: pad input through gamescope, 1440p scaling,
shadPS4-under-gamescope quirks, and the freeze/suspend dance interacting
with a nested compositor. See docs/research/pip-over-a-game-20260809.md.

**BLOODBORNE: everything works as of tonight.** The full arc is in
auto-memory homelab-bloodborne-mods.md - read it BEFORE touching anything
BB-related. Headlines: (1) the combat crash was the BB REBORNE MOD PACK -
all 12 modules reverted (Donnie: "doesn't even change much, keep it like
this"); zips + per-file backups remain for a rainy-day bisect. (2) The
silent-SFX bug is the save's clean-exit byte 0x204E; game-launch now
force-sets it before every launch (5c9d5fc) - if combat crashes EVER return,
remove that block first. (3) readbacks_mode=1 (Relaxed) applied for the
stuck translucent ghost-rectangles - UNVERIFIED by eye, first thing to ask
about; also watch the fps cost (was 50-60 CPU-bound). (4) FMOD Crash Fix
patch entry exists in Bloodborne.xml but isEnabled=false - do NOT re-enable.

### Also this session
- Gestures: hold rebound context_menu -> switcher, so hold == double_tap;
  edited script.couch.switcher settings.xml directly, verified via
  gestureconf.load(), no rail warnings. Backup at scratchpad
  switcher-settings.bak.
- 0e445d1: launch flourish - halo rings now zoom+fade WITH the tile
  (CouchLaunching), stale zoom centre 93->78 fixed. Motion unverified by eye.
- Xfce display popups: 7 stacked "keep configuration?" dialogs killed;
  xfconf displays /Notify -> false so TV hotplugs stop breeding them.
- Pad lag mystery solved: the Bose headphones auto-connected to the PC's
  bluetooth (radio contention with the DualSense). Offered
  `bluetoothctl untrust E4:58:BC:7F:38:74` - NOT run, Donnie hasn't said.
  Kernel BT patch verified still in place (kernel 7.0.0-28 unchanged).
- Jellyfin: HardwareAccelerationType was STILL nvenc on an AMD-only box (6
  days broken transcode); fix line given to Donnie (vaapi + restart) -
  UNCONFIRMED whether run. Tone mapping needs mesa-opencl-icd (not
  installed) before 4K HDR transcode looks right. The Inception/Dark Knight
  "file not supported" on the LG app may ALSO be webOS DV-in-MKV refusal -
  test after the vaapi fix; Kodi plays both fine regardless.
- Disk: 3rd/4th link resets on disk1 13 Aug; monitor upgrade READY at
  scratchpad disk-monitor.sh (unsafe-shutdown counter per serial) - install
  line given, UNCONFIRMED whether run. Cable-swap discrimination experiment
  still pending at the box.

### ▶ NEEDS DONNIE (carry-overs + new)
1. Readbacks verdict: ghost rectangles gone? fps cost?
2. Games row: pitch/off-screen exit/launch flourish still never verified by
   eye while moving.
3. CPU fan curve extension (scratchpad fancontrol.new) - line given, not run.
4. GPU still pinned `high` from coil-whine test; revert line given.
5. YouTube bass: check the Hisense soundbar's own sub level / sound mode.
6. memtest STILL never run.

### Deliberately uncommitted
- kodi-addons/resource.uisounds.couch/ (unfinished addon, no addon.xml) and
  shadow/*.jsonl runtime logs.

## ▶ Previous resume block (12 Aug 2026 ~10:30 — BLOODBORNE SOUND SOLVED, and it was our launcher)

**The headline: the missing attack/menu/footstep sounds were caused by
`game-launch` force-killing the emulator.** Bloodborne notices it was not
exited through its own menu and silences a whole audio category for the
session while music keeps playing. Donnie's own hunch ("i was thinking it
could be about it not quitting cleanly") cracked it after a night of my
theories that did not survive contact with evidence. Matches shadPS4 #1641,
#1189, compat #211. Full detail + everything eliminated: auto-memory
`homelab-bloodborne-mods.md`.

Two layers of fix are in:
- `59aa7fb` — quit grace 6s -> 30s, SIGKILL only if genuinely ignored, and it
  now LOGS `exited under its own power (clean)` vs `IGNORED SIGTERM ... NEXT
  LAUNCH WILL START DIRTY`. So session state stops being a mystery.
- The community SoundCrashFix byte, `0x204E: 00 -> 01`, applied to BOTH
  `userdata0010` and `backup0010` under
  `~/.local/share/shadPS4/home/1000/savedata/CUSA00900/SPRJ0005/`
  (note the `home/1000/` path). Full save backup at
  `~/games/ps4/bloodborne/save-backups/2026-08-12-pre-soundfix/`.
  **NOT yet confirmed in play** — next launch, check sounds AND that the save
  loads with progress intact. Restore = `cp -a <backup>/. <savedir>/`.

**THE METHOD LESSON worth carrying:** all six captured sessions had been
force-killed, so "wait for a working session and diff it" could never have
produced one. When an intermittent bug never shows its good case, suspect the
harness before the subject.

### Also fixed this session
- **`0359b6d` — phone launches were ALWAYS broken.** `shadps4: command not
  found`: couch.service inherits systemd's PATH with no `~/.local/bin`, while
  Kodi launches go via flatpak-spawn which sets it. Hit every helper (`tv`,
  `game-pids`, `pause-snap`…), not just the emulator. Stayed invisible because
  the launcher sent the emulator's output to `/dev/null` — now kept at
  `/tmp/shadps4-launch.log`. New memory: `couch-launch-path-trap.md`.
- **`4b33bd7` — fancontrol had been dead since boot.** `tools/fan-remap` ran as
  ExecStartPre before amdgpu registered its hwmon node, exited 1, took the
  service down; case fan sat on the board's flat 50% all evening at idle. Now
  polls up to 30s. Donnie restarted the service: case fan 1664 -> 1148 rpm.
- **4K on Bloodborne WORKS** (the "needs a 4090" note is folklore — the limit
  is a guest-side fixed heap, not host VRAM). Currently reverted to 1440p
  because 4K cost 60 -> 45-50fps (CPU-bound: `NexusRevolution` and
  `shadPS4:GpuComm` each peg a core) and the HUD is pinned at 1080p so it
  pixelates. The working 4K patch file is kept at
  `~/.local/share/shadPS4/patches/shadPS4/Bloodborne.xml.upstream-4k.bak`
  (needs `extra_dmem_in_mbytes: 4000` with it). Detail in auto-memory.
- **`7c349ea` / `a2d2893` — games row**: pitch tightened 170 -> 156 (gaps 40 ->
  26), and the row now starts off-screen at x=-55 with a third slot so the
  outgoing tile is clipped at the screen edge instead of mid-screen. Kodi has
  no per-item opacity, so a true fade is not available — change the space, not
  the animation.
- **`42e9b36` — spinners** get their own compositor layer and run at 0.9s.

### ▶ NEEDS DONNIE (nothing here can be done from this side)
1. **Confirm the Bloodborne save is fine** on next launch — sounds present,
   progress intact. It is the one change made to his save data.
2. **The games row still has NO eyes on it.** Pitch + off-screen exit were
   verified by measurement on a 4K grab, never by looking while scrolling.
   Static frames cannot show motion.
3. **CPU fan is now the loudest thing in the box** (1247 rpm at 36C, still on
   the BIOS curve; only the case fan is managed). Proposed config extending the
   curve to pwm2 via TSI0_TEMP is at scratchpad `fancontrol.new` — the apply
   line was given, not yet run. Risk stated: if fancontrol dies the fan stays
   put (CPU throttles, no damage).
4. **GPU is still pinned at `high`** from the coil-whine test. Clicking
   "helped but didn't go away completely". Revert when done:
   `sudo bash -c 'echo auto > /sys/class/drm/card1/device/power_dpm_force_performance_level'`
5. **YouTube bass**: TV is on `standard` sound mode, output `external_arc` to a
   **Hisense Sound Bar** — so the TV's own EQ is bypassed and a bass setting
   made on the TV does nothing. Check the SOUNDBAR's separate subwoofer level
   and its sound mode (Virtual:X/Movie upmix dumps low end into the sub;
   Music/Standard is right for YouTube). The soundbar is HDMI-only, not
   readable from here.

### Open / not done
- **`kodi-addons/resource.uisounds.couch/` is UNTRACKED and unfinished** — 7
  rendered WAVs + `tools/uisound-render` + `docs/specs/ui-sound.md`, but no
  `addon.xml`, no `resources/sounds.xml`, not installed. Deliberately left out
  of every commit this session. Spec notes Kodi 21 produces no action sounds
  from controller input (upstream #27184) — verify before building further.
- **disk1 (Lexar NM790 4TB, `/mnt/disk1`) USB alert 12 Aug 10:09** — assessed
  and benign: ONE failed **READ**, no ext4 errors ever, drive SMART pristine
  (0% used, 0 media errors, 100% spare). The fault is the RTL9210 USB link, not
  the drive. **33 unsafe shutdowns** is the number to watch — offered to add it
  to disk-monitor, not yet built. Real fix is eventually moving that NVMe out
  of the enclosure into an M.2 slot.
- SMART on these enclosures needs `-d sntrealtek` (NVMe behind Realtek bridge);
  `-d sat` returns nothing.
- memtest still never run (the 5 Aug idle-freeze mystery).
- **Left uncommitted on purpose:** `kodi-addons/resource.uisounds.couch/`
  (unfinished, above) and `shadow/*.jsonl` + `shadow/status.json` - couchd
  runtime logs, already dirty when this session started; they are not build
  artefacts and nothing this session changed them.

## ▶ Previous resume block (9 Aug 2026 ~13:40 — overnight build, then a live disk incident)

All work committed on master. **This repo has NO git remote**, so "committed"
is the only backup that exists — a standing risk worth naming.

Live state at handoff: Kodi 21.3 up on Home, TV in **standby** (never woken all
session), couchd / couch / tv-waker / disk-reset-watch all active,
tv-power-watcher finally **disabled**, no disk reset since 05:06:51, Sonarr's
four-day error loop at zero.

**What shipped (each verified, see the commit bodies for the evidence):**
- **Switcher power bar** — "Quit game / Controller off / Controller + TV off"
  as a top row on the switcher, dispatching to `script.tvpoweroff` so the
  quit-politely-first logic has one home. Text not glyphs (we A/B'd; glyphs
  could not carry "controller" vs "controller and TV").
- **Home tiles grow and shrink** instead of snapping. Kodi does NOT reverse a
  Focus animation on a list item, so the shrink needs an explicit `Unfocus` —
  and even then Kodi truncates its tail, hence 120ms easing-out down against
  170ms up.
- **`tools/kodi-restart`** — quit over JSON-RPC, no crashlog, verifies the new
  process answers before claiming success. Replaces hand-rolled `pkill -9`,
  which forged 13 fake crashlogs and caused an outage when one kill wasn't
  followed by a relaunch.
- **Headphone watcher** in `tv-waker-webos` — armed by config, ships disarmed.
- **Disk tooling** — `tools/disk-triage` (one sudo, everything) and
  `tools/disk-reset-watch` (running now; captures whether the disk was busy
  when the next link reset happens).

**► THE EXACT NEXT STEP** is nothing in code — it is waiting for evidence:
`disk-reset-watch` is running and will write `recordings/disk-resets.log` when
disk1's USB link next drops. Read that file first next session. If it shows
low/zero throughput at the moment of the reset, the load theory is dead and
the answer is a marginal cable/enclosure on disk1 (reseat it). Detail in the
"Disk1 link resets" section below.

**Open decisions (no action taken, deliberately):**
- The switcher's power bar is unreachable when nothing else is running — see
  its section below. Two routes exist (PS-button hold covers it), so this was
  left as Donnie's call rather than guessed at.
- Whether the hero-backdrop "sometimes instant, sometimes fades" is real: ten
  measured transitions at a stretched 3000ms fade ALL faded cleanly (slow,
  fast-scroll, cold cache, no-art, window re-entry). Could not reproduce. Not
  a Kodi 20-vs-21 thing. Three of nine row items have no fanart at all
  (Library, Big Picture, shadPS4), which is the one real inconsistency found.

**Needs Donnie's eyes, with the TV actually ON** (stills cannot answer these):
- Does the 12px amber underline on the power bar read from the couch, and does
  170/120ms on the tile grow/shrink feel right at speed? If the shrink pops,
  the lever is dropping it to ~90ms.
- `all_off` ("Controller + TV off") — its parameter crossing is proved with a
  sentinel, its side effects are NOT tested, because testing meant driving the
  television.

### ▶ Donnie's to-do (needs sudo, hands, or the TV on)

DONE this session: `disk-monitor.sh` deployed; `tv-power-watcher.service`
disabled (it had crash-looped 9,948 times against the dead Toshiba's address,
burying the journal the disk problem had to be read from).

Still open:
1. **Temperature during a disk event** — the one measurement never taken, and
   the thing that would settle thermal vs cable:
   `sudo ~/couch/tools/disk-triage -o /tmp/t.txt`
   Worth running once cold anyway for the SMART lifetime counters (Media and
   Data Integrity Errors, Warning Comp. Temperature Time) — never read on this
   disk. smartctl says NOTHING about these bridges without `-d sntrealtek`.
2. **Reseat disk1's USB cable/enclosure.** Cheapest fix for the leading theory.
   Evidence: disk2 is an identical RTL9210 on the adjacent port with identical
   config and zero errors all boot, which rules out controller/PSU/driver/
   ambient. And 55GB of sustained 400MB/s reads during the torrent rechecks
   produced ZERO resets, which argues hard against load being the trigger.
3. **Pair the headphones**, then put the MAC in `~/.config/tv-remote/tv.json`
   as `"headphones_mac"` and `systemctl --user restart tv-waker.service`.
4. **Re-Size BAR still OFF** in BIOS; **memtest still never run** (the 5 Aug
   idle freeze remains unexplained).

## ▶ Previous resume block (8 Aug 2026 ~19:50 — KODI 21 IS LIVE)

**THE MIGRATION IS DONE. Kodi 21.3-Omega is running on skin.couch.** Donnie
ran `sudo apt install flatpak`; everything else executed the same evening,
with the TV in standby throughout. Full account, including what was verified
and how: **`docs/kodi21-flatpak-migration.md`**.

Verified live, not assumed: library intact (88 films, 30 shows, databases
migrated to MyVideos131 beside the untouched 121); Games row renders 8 tiles
with Bloodborne reading "· paused" (so `/tmp/game-suspended` crosses the
sandbox); achievements/trophies (ER 42, Bloodborne 40, HK 63); Library page
1197 and YouTube 1196; DualSense button map and both keymaps travelled.

**ROLLBACK, if the evening goes wrong:**
```
cd ~/couch && couchd/.venv/bin/python tools/kodi21-migrate rollback
```
then restart Kodi. Nothing was uninstalled; `~/.kodi` is untouched and has its
own frozen Nexus copy of the skin.

**AUDITED the same evening** (`docs/audits/kodi21-migration-2026-08.md`).
Four [A]s, all in the migration's own code and three of them in
`tools/kodi21-migrate`, whose whole job is to be safe to re-run: deploy-addons
would have replaced the frozen rollback skin with a symlink to the 5.17.0 repo;
a second `profile` run could write the frozen Nexus skin back into the git
checkout; the copy's skip test was `newer AND same size`, so anything Kodi 21
rewrote to a different LENGTH got reverted (this one fired for real and took
the Omega repo index with it - repaired); and `profile` had no guard against
copying forward over the live profile. All fixed, all with tests.
Decided rather than escalated: **addon updates are now NOTIFY-ONLY** (five
addons carry hand-applied patches whose only protection is out-ranking the
repo version); the dead `Custom_1196_Couch_HaloPicker.xml` deleted.

The audit's one [B] is now CLOSED too: `kodi-tv`'s crash-relaunch **does**
propagate through `flatpak run`. Verified by `POST /api/system/kodi-restart`
(server/sys.js SIGABRTing kodi.bin) - back in ~6s, wrapper still supervising.
So the hardened restart the phone app offers still works on Kodi 21.

**Home tweak the same evening:** a paused game's row tile keeps its own cover
art now; only the dedicated card shows the screencap (Donnie: "we now have a
dedicated space"). `tools/test_games_paused_tile.py`.

**EFFICIENCY AUDIT, 8 Aug** (`docs/audits/performance-2026-08.md`). Ten wins
shipped and measured: /api/windows 215ms -> 0.7ms warm and 210 -> 159ms cold,
HTTP compression (there was none - library 48.6 -> 17.9 KB), game art resized
for the phone (1.30 MB -> 316 KB per Games tab; the Bloodborne tile 947 -> 45
KB), TV volume cached (3.18s -> 0.001s on the DEFAULT tab), three components
that fetched everything twice at mount (Screen was opening two MJPEG streams),
Games/Services prefetched, and install sizes moved off the listing - which
also fixed a real wrong number (Bloodborne read 29.3 GB for a 40.5 GB game;
the TV now says 41 GB).

TOP REMAINING [A]: composed row tiles are the only art asset with no
background warmer - 96-181ms per game, 706ms for all five, paid in front of
the player. `tools/warm-loading-cards` is the precedent. Then Jellyfin poster
quality 90 -> 80 (-29%), a Sonarr series cache (186 KB per lookup, uncached,
while Radarr already avoids it twice over), and Cache-Control on JSON.

[D] FOR DONNIE: **the Kodi YouTube plugin is signed out.** Both default feeds
502, it costs ~3.5s on every YouTube tab open, and the app retries forever.
Needs the Google device-code sign-in again.

ANSWERED AND FIXED, the paused-card question. Container.Refresh is a no-op on
Home (Home.xml is KEEP_IN_MEMORY), so the Games row never corrected itself:
measured with a real quit, game-launch cleared the flag at 107ms and deleted
the freeze-frames at 164ms while the row kept reading "- paused" and kept
drawing a card whose image file was gone - Kodi had cached the texture. Not
lag; it never corrected itself at all until you left the row and came back.
The row's content URL now carries $INFO[Window(Home).Property(CouchGamesRev)]
and pause-snap stamps it on every capture and every clear. Verified both
directions on the TV, and focus stayed on item #4 across both rebuilds, which
was the one thing worth checking. The minimise ANIMATION was always instant
(~0.2s) because it rides a window property, not the row.

**STILL NEEDS DONNIE'S EYES ON THE TV** — nothing else can settle these:
picture, audio over eARC, 4K120; the DualSense actually driving the UI (the
map travelled and the pad enumerates with its 13 buttons, but no synthetic
press proves the feel); a film; a game launch and a suspend/resume cycle; and
the first deliberate `ReloadSkin()`, which is the test that retires the
never-live-switch-skins rule.

**THREE THINGS TO KNOW:**
1. Kodi 21 offered to install `game.controller.ps.dualanalog` and it was
   **declined on purpose** — our keymaps bind `profile="game.controller.default"`
   and a mismatched controller profile means the keymap never attaches. If the
   prompt reappears, say no.
2. `Custom_1196_Couch_HaloPicker.xml` and `Custom_1196_Couch_YouTube.xml` both
   claim window 1196. YouTube wins, the halo picker is dead and its own comment
   says "temporary". One error line per boot; deleting it is a one-liner.
3. **couchd's model fingerprint is now `44d3542b8bba`** (gestureconf changed
   shape) — the shadow differ compares against it.

**NOT RETIRED, deliberately.** The kodi-tv crash-restart loop,
`reuselanguageinvoker`, the never-ReloadSkin rule and jellyfin's 45s
`startupDelay` all still stand, each with a written retirement criterion in
the doc. Ironically Kodi **20** wedged on its way out during this very
migration (`CPythonInvoker: waiting on thread`, 110% CPU, needed SIGKILL) —
which is exactly the bug being escaped, and exactly why "we're on 21 now" is
not evidence. Give it two weeks of cold boots first.

**THE THREE FACTS THAT DECIDED THE DESIGN** (all from primary sources, not
memory — they are the ones a fresh session would get wrong):
1. The Flathub build patches kodi.sh with `export KODI_DATA=$XDG_DATA_HOME`,
   so the profile is **`~/.var/app/tv.kodi.Kodi/data`** — NOT `~/.kodi`, and
   NOT `~/.var/app/tv.kodi.Kodi/.kodi` (what `--persist=.kodi` would give,
   and what everyone guesses).
2. Kodi 21 declares `xbmc.gui 5.17.0` with `backwards-compatibility
   abi="5.17.0"`; Kodi 20 provides 5.16.0 with none. **No single value
   satisfies both**, and `~/.kodi/addons/skin.couch` is a symlink to the repo.
   Bumping it while apt-Kodi is the launcher drops the TV to Estuary at the
   next restart. `tools/test_skin_omega.py` enforces this; `freeze-skin` is
   what makes the bump safe.
3. Inside the sandbox `~/.local/bin/game-launch` is **visible but unrunnable**
   (it wants xdotool, wmctrl, steam, the host python3), and `/tmp` is a
   private tmpfs so the session flags read empty — which would have the power
   menu offering "turn off the TV" mid-game. `kodi-addons/couchhost/` is the
   crossing, vendored into the three addons that need it, a literal
   passthrough on the apt build.

**WHAT NEEDS DONNIE'S EYES ON THE TV** (nothing else can settle these):
picture + audio over eARC + 4K120 under the Flatpak; the DualSense (the
button map travels in `addon_data/peripheral.joystick`, but verify); a film;
a game launch and a suspend/resume cycle; and the first deliberate
`ReloadSkin()` — that is the test that retires the never-live-switch-skins
rule.

**NOT RETIRED, deliberately.** The crash-restart loop, `reuselanguageinvoker`,
the no-ReloadSkin rule and the jellyfin 45s `startupDelay` all still exist.
Each has a written retirement criterion in the doc; none can be *proved* dead
from a work-day session with the TV in standby, and the whole point of the
loop is the cold boot nobody was watching.

### What 8 Aug shipped (all committed on master, all verified live)
- **Achievements/trophies shelf** on home: Down from a game opens a PS5-style
  shelf (icons, name, description, Unlocked/Locked + global rarity). Steam via
  the Web API key already in `.env`; PS4 via `tools/ps4-trophies` (TRP parser,
  real icons; Bloodborne trophy TEXT decrypts now that the ESFM key is at
  `~/.config/couch/ps4-trophy-key`, mode 600, NOT in git). Stats line reads
  playtime · last played · achievements · install size.
- **Launch cinematic**: tile expands + fades (a group control - animations on a
  focusedlayout element are silently ignored, that was v1's bug), room fades to
  black, then the loading card. Cards are PRE-BAKED to `data/loading-cards`
  (mtime-validated; warm hit 22ms vs 1.7s compose) by `tools/warm-loading-cards`,
  spawned hourly from games.py. Card = game art + logo + an animated WHITE
  SPINNER (24-frame strip blitted by tools/curtain, `--spin strip,x,y,d,n,fps`).
- **PS5 minimise**: pause-snap announces the suspend (CouchJustPaused*) and Home
  flies the fullscreen freeze-frame into the paused card. Paused game shows the
  screencap in the CARD only; the 4K hero owns the backdrop.
- **PS button, PS5 grammar** (both stacks + 479 tests): tap = home (in-game it
  IS the suspend escape), double-tap = switcher, hold = Steam menu in-game /
  power screen at home. Tap now DEFERS by the double-tap window (Donnie accepted
  the latency) - needed a new `tap-fired` state in couchd, the level-based
  emission never ran. Power screen redone (dark takeover, circular glyph row).
- **YouTube section** (window 1196): sidebar (Home/Subs/Watch Later/History/
  Trending/Search/Couch Home) + 3-col grid, duration badge in-thumb, "views |
  upload age". Addon patches in `kodi-addons/youtube-plugin-patches/README.md`
  (reapply after addon updates): no comment count, no likes, no descriptions.
- **Bloodborne**: full BB Reborne (minus the SFX overhaul - it BREAKS ATTACK
  SOUNDS, keep it reverted), 84Resolutions patch pack at
  `~/.local/share/shadPS4/patches/shadPS4/` with **2160p + Skip intro** enabled
  (was 1440p: GPU 71%, VRAM 4.6/15.9 GB, so 4K was worth trying - REVERT TO
  1440p IF DONNIE SAYS IT'S BAD), 4K hero + official wordmark.
- **4K120 pinned** (couch-4k120.service enabled), soundbar on eARC (TV reports
  `external_arc`), phone app got a TV/soundbar volume card, Kodi's volume bar
  fill no longer warps.

### Waiting on Donnie (first real-world test, nothing to build)
Cold-launch Bloodborne (4K + skip intro + the whole cinematic), PS tap in-game
(the fix + the minimise animation's live timing), hold-at-home power screen,
first earned trophy (does shadPS4 record unlocks?), phone slider with the TV on.
Also: the switcher's new power bar with the TV actually on — does a 12px amber
underline read from the couch, and does "Controller + TV off" do the right
thing for real? Its parameter crossing is proved, its side effects are not
(deliberately: testing it meant driving the television).

### Disk1 link resets + 2 corrupt files from 5 Aug (9 Aug 02:43)
Four `usb 4-4: reset SuperSpeed` on disk1 in 33 min, then quiet. NOT the 5 Aug
failure: zero writes, transport errors (DID_ERROR, no medium error), link
recovered every time, ext4 never faulted. disk2 on an identical RTL9210 at the
next port was clean all boot, which rules out controller/PSU/driver/ambient.
No job explains it - qBittorrent isn't seeding (0.04GB/21h), Sonarr's retry
loop has run constantly since 23:01 through hours with no resets, and
Jellyfin's scan started 2s AFTER the last reset. Both ports are configured
identically, so it points at disk1's physical enclosure/cable/drive.
Temperature during an event has still never been measured:
`sudo ~/couch/tools/disk-triage -o /tmp/t.txt`.

SEPARATE, and now FIXED: the 5 Aug outage DID lose data, recorded as "nothing
lost". Header sweep found 335 good and 2 all-zero (Simpsons S03E11, S06E06).
Repaired 9 Aug by force-rechecking both torrents in qBittorrent - it still
thought them complete, so the recheck found the bad pieces and re-pulled only
those. Sweep is now 337/337 valid, both episodes imported to /mnt/media/tv,
and Sonarr's retry loop went from 4 failures a minute to zero.

### disk-monitor.sh had 4 bugs - FIXED AND DEPLOYED (9 Aug)
It alerted TWICE for the single 05:06 reset, which is what exposed it. Donnie
deployed the fix (`/usr/local/bin/disk-monitor.sh`, 5-min timer) and the two
copies are now identical. Its first run replayed the whole ring buffer once (a
new cursor filename with nothing seeded - my miss); it has been correctly quiet
since. Source of truth for edits is `~/diskhealth/disk-monitor.sh`; NOT in git,
because the file carries the Discord webhook.

  1. Duplicate alerts: cursor was a dmesg LINE COUNT read with
     `tail -n "+$LAST_POS"` - 1-indexed and inclusive, so it always re-emitted
     the line at the cursor. When an error is the NEWEST line (the interesting
     case) it re-fired every run. A line count is also meaningless once the
     ring buffer wraps. Now cursors on the kernel timestamp.
  2. SMART was checked on /dev/sdc and /dev/sdd. The USB disks are sda/sdb
     this boot and the letters swap by design, so the loop ran ZERO times -
     "no SMART alert" has never meant anything. Now discovers USB disks.
  3. The reset check grepped 'reset high-speed USB' AND required sdc|sdd|disk
     in the line. Real events are 'reset SuperSpeed' (USB3) and the kernel
     names the PORT, never a disk - so it could never match. This is why five
     link resets produced only I/O-error alerts and never a reset alert.
  4. smartctl used -d sat / -d nvme; RTL9210 bridges need -d sntrealtek.

Verified with shimmed dmesg/smartctl/curl: alerts once then stays silent on
the same input, reports a genuinely new error, fires the reset check with the
port, and survives the kernel clock rewinding on reboot. NOT committed - the
file carries the Discord webhook.

### Headphones: built and armed-by-config, waiting on the pairing (9 Aug)
`headphone_watch` in `~/.local/bin/tv-waker-webos` (already run by
tv-waker.service). It ships DISARMED and logs "watcher idle" until a MAC
exists. When home:

1. Pair the headphones (`bluetoothctl` scan/pair/trust).
2. Add the MAC to `~/.config/tv-remote/tv.json` as `"headphones_mac"`.
3. `systemctl --user restart tv-waker.service`, then check
   `journalctl --user -u tv-waker.service` says `headphones: watching <MAC>`.

The rule, per the ask: never connect while the TV is off, and disconnect them
if they come up while it is off. The second half is a POLL, not a TV-off
event, because the headphones initiate - powering them on dials the box with
the television doing nothing. Escape hatch for using them with the PC while
the TV is off: `touch ~/.config/couch/headphones-anytime` and the watcher
leaves them alone entirely.

NOT verified live (needs the set on and the headphones in the room): the
actual connect on TV-on, and a real disconnect - nothing was BT-connected to
test the enforcement against. The decision rule has 33 tests
(`tools/test_headphone_watch.py`); the loop was confirmed armed, reading the
TV, and correctly doing nothing with the set in standby.

`~/.local/bin/tv-power-watcher` is the DEAD Toshiba version - headed off with
a warning so its `HEADPHONES_MAC = ""` is not mistaken for the switch. It DOES
have a systemd unit (a system one - the first pass only checked `--user` and
wrongly called it unscheduled), and that unit is in a crash loop against the
old TV's address: 8922 restarts, ~17k journal lines an hour, since 6 Aug.
Needs `sudo systemctl disable --now tv-power-watcher.service`.

### Open: the power bar is unreachable when nothing else is running
`script.couch.switcher`'s main() returns early with "Nothing else is running"
when the window list has no non-Kodi rows, which was right when the dialog was
only a switcher — but the power bar is now the other half of it, and "turn the
controller off" is *most* wanted when you are sitting in Kodi with nothing
running. Not changed yet because the PS-button hold menu still covers that case
and opening a switcher with an empty switch list needs a considered empty
state (focus has to start on the bar; 9000 is the defaultcontrol). Decide:
open with the bar only, or leave the two routes as they are.

### Levers not yet flipped
couchd `owns.conf` still only has `gestures` - transitions/guard/reconcile are
next, one at a time, daytime, 5-min acceptance each (charter). Re-Size BAR is
still OFF in BIOS. memtest still never run (the 5 Aug idle freeze is still
unexplained).

## ▶ Previous resume block (7 Aug 2026 ~16:00 — hardware settled, one live incident)

**READ FIRST - THE INCIDENT (7 Aug 01:55): our synthetic Steam guide press
SUSPENDED THE MACHINE mid-game.** couchd's close_steam_menu fired one vpad
guide press and the legacy guard fired three more inside 5s; in a live Big
Picture session those presses drive Steam's OWN menu, reached its power
options, and Steam called logind to sleep the box. Donnie lost an Elden Ring
session and had to press the power button (TV had lost signal, PSU light
blinking - it read exactly like a crash). Receipts: Steam's
console-linux.txt "Closing timeline on system suspend" 01:55:13 plus a dbus
method return at 01:55:16.466, the same millisecond logind logged "The system
will suspend now!". FIXED + committed (1ac3ab0): both call sites are inert
behind `~/couch/data/steam-guide-press-enabled` (absent = off). The verb still
exists so the differ keeps comparing it. Model fingerprint now **90366b2bd84b**.
**RULING NEEDED before re-enabling:** the underlying job (make Steam release
the pad on handoff) still has no working mechanism - every close_steam_menu
effect check has ALWAYS verdicted MISSED. Redesign must be: a press that
cannot reach a power menu, gated on evidence the menu is really open, owned by
exactly ONE stack. Aftershock also seen: Steam Input's virtual Xbox pad stayed
registered alongside the real DualSense while a session was loaded, doubling
every Kodi button press (cleared by closing the session).

**DISPLAY / ADAPTER (7 Aug): Cable Matters 102101 DP->HDMI 2.1 is IN.**
Output renamed again: **DisplayPort-2** (card1-DP-3); the TV's native HDMI
input is now unused and its old xfconf profiles are deleted. Running
**4K60 full colour**; Kodi re-set to 4K (mode string
`0384002160059.94000pstd` - the 60.00 variant is NOT in Kodi's list and
silently drops it back to 1080p). **4K120 does NOT work yet**: a hand-built
CVT-RB 4K120 modeline applied on the DP side but produced NO SIGNAL, and the
adapter advertises max 4K60. The adapter is ALREADY on the VRR firmware, so
the remaining suspect is **Ultra HD Deep Colour being off for the HDMI port
the adapter now sits in** (it is per-port; enabling it on the previous port is
exactly what made 4K120 appear over native HDMI). NEXT STEP: Donnie enables
Deep Colour for that input, then re-probe with
`xrandr | grep -A3 "DisplayPort-2 connected"`. TV EDID advertises HDMI 2.1
FRL rate 4 (32 Gbps), so the panel side is ready.
LESSON: Kodi enumerates screen modes ONCE at startup - after any output
change it must be restarted or it keeps re-applying a stale mode (it dragged
the desktop back to 1080p twice). Also: the TV's EDID physical size is
nonsense (reports ~72" for a 42" set) - never trust that field.

**FAN CONTROL (7 Aug): case fan now on a measured curve, CPU fan untouched.**
fancontrol installed + enabled; config lives in `~/fancontrol.conf` (copy of
/etc/fancontrol). MEASURED, do not re-derive: **fan2/pwm2 is the CPU FAN**
(ramped 1231->2125 RPM as Tctl went 37->77C) and **fan1/pwm1 is the CASE FAN**
(sat at 1656 RPM throughout) - the header numbering lies, and trusting it made
me quieten the CPU fan first. The case fan STALLS at duty 60 and needs 70 to
start, so the floor is 80 (~1136 RPM) with a 110 restart kick. Curve follows
**GPU edge temp** (55->85C), because SYSTIN is inert (pinned 32.0C through a
77C CPU load) and Ryzen's Tctl is too spiky (idles 37-43C but flicks past 50C,
which made the fan hunt). Verified ramping to ~2160 RPM under load and
settling back. NOT yet verified across a reboot - check
`systemctl is-active fancontrol` and that fan1 reads ~1136 RPM after the next
boot (hwmon renumbering is the risk; fancontrol has a guard, failure is safe).

**STILL OPEN (Donnie):**
- Enable Ultra HD Deep Colour for the adapter's HDMI input -> then 4K120.
- BIOS trip (he was heading there): **Re-Size BAR + Above 4G Decoding is OFF**
  and worth real performance (kernel reports BAR=256M against 16GB VRAM);
  **Power Supply Idle Control = Typical Current Idle** (the documented fix for
  the unexplained 5 Aug idle freeze, still unexplained, memtest still never
  run); Restore on AC Power Loss = Power On; WoL needs "Power On by PCI-E" AND
  ErP/EuP DISABLED. Leave RAM at stock 2667 and Secure Boot OFF (patched
  bluetooth.ko). After the BIOS trip, the NIC still needs `ethtool wol g`
  set + persisted (currently `disabled`).
- Wall mount for the 42" C5: **VESA 300x200, M6**, screws must not enter more
  than ~20mm; small mounts often ship M4 only.
- Witcher 3 mods: game IS installed (next-gen build, 58G, `mods/` created).
  Blocked on Nexus needing a login - drop files at http://files.home into
  `witcher3-mods` (or paste a CDN link) and the install is mine. No Script
  Merger needed (texture/config mods only). RT costs roughly half the frame
  rate on this card; benchmark plan is MangoHud, RT off vs tuned vs ultra.
- Main PC (separate machine): colour glitching after taking the 4070. Likely
  driver leftovers -> DDU then clean install. Diagnostic: does it glitch in
  BIOS screens too (hardware/cable) or only in Windows (drivers)?

**HDR AUTO-ROUTING: still built, installed and OFF** (both kill switches on:
`~/couch/data/tv-autoroute-off` exists AND the addon toggle is false). Server
half verified live. Turning it on needs Donnie watching a real HDR film,
because Kodi 20 has no pre-play veto: the addon lets playback start then stops
it, so expect a flicker, and Kodi writes a resume position on that stop.

## ▶ Previous resume block (6 Aug 2026 ~21:00 — deploy day + evening build run)

**EVENING BUILD RUN (6 Aug ~18:00-21:00, commits cbbe281..9d78c86):**
- **DEPLOYED + verified tonight:** Play on TV (phone button + full remote:
  /api/tv/* endpoints, foreground-aware input restore; chain proven live -
  Batman Returns via API); Kodi context item "Play on TV (HDR)" (enabled
  after a graceful Kodi restart, TV stayed asleep); whisper-asr on Vulkan
  (3x faster; rollback = ~/.local/bin/whisper-asr-server.cpu-fallback.bak);
  curtain wired into game-launch suspend/resume (sweep 12/12 after).
- **DEPLOYED ~19:10 (commits 7d7da3a + the R7(d) rescope): the
  resume-ordering protocol is LIVE.** Adversarial review verdict: core
  protocol REFUTED every attack; the one FIX-FIRST item (stale differ
  exemption eating the validation evidence) was rescoped + pinned before
  deploy. Deployed tightly (mirrors -> couchd restart -> pad-home restart),
  fingerprint now 58d8b15bee6b, sweep 12/12, 0 failures. **The reconcile
  flip now needs only: one clean shadow evening (differ shows zero
  refreeze rows near resumes - normal couch use provides it), then
  Donnie's daytime flip decision.** Reviewer's note-grade residuals are in
  the differ docstring (guard latency ~2s, watcher 0.6s hold-measure edge,
  close_games crash-at-entry resurrection trade, couchd's lockless acted
  suspend for the flip design discussion).
- **Stage 3 kicked off (committed, nothing wired):** tools/gamescope-wrap
  (exit-code laundering via sh shim - gamescope NEVER forwards child status,
  source-verified) + docs/stage3-gamescope-migration.md (18 window-model
  sites mapped, LD_PRELOAD overlay-strip finding, freeze-tree asymmetry
  ruling needed, guinea pig = shadPS4 Bloodborne). Donnie chose "games into
  gamescope" as the migration track.
- **Known dirt:** test_gestureconf settings-page test fails against the
  deployed switcher addon (it gained ui.animated_dialog) - reconcile the
  test; curtain resume worst-case vs its 8s watchdog unverified live.

**NEW BUILD ITEM (Donnie, 6 Aug evening, OLED burn-in worry): TV idle guard**
- the C5 is an OLED and Kodi's home screen is static; build the tv-waker
  counterpart: TV on + no Kodi playback + no game session + no input for
  ~15 min -> `tv off`. Conditions must be conservative (never mid-film,
  never mid-game, respect a manual-on grace period). Natural home: a small
  daemon beside tv-waker or a couch-server poller. Build in daylight.

**SWITCHER VERIFIED BY RIG 6 Aug ~19:25 (fake-pad + screenshots), item 1
of the checklist is DONE:** double-tap opened the animated sheet, rows show
NAMES ("Switch to" header, labelled rows, Cancel), LEFT-STICK navigation
moves the highlight (blue accent bar), and CROSS picks the focused row
(Cancel -> "couch.switcher: cancelled"). The id-3 fix is confirmed end to
end through the real input path. NOT verifiable without a game: the
freeze-frame backdrop (correctly inert with no session - the control stays
hidden). RIG NOTE: fake-pad's DPAD does not reach Kodi (it enumerates with
hats: 0, unlike the real pad), so rig navigation must use the left stick;
that is a rig limitation, not a console bug.

**RIG-VERIFIED 6 Aug ~19:30-19:40 (fake-pad + screenshots + live chain),
nothing left for Donnie except the game-dependent items:**
- Play on TV, FULL end-to-end from the Kodi context menu: item visible in
  the menu on a real film, id extracted (The Batman), stages walked
  waking -> launching -> connecting -> playing, TV foreground went to
  org.jellyfin.webos, phone endpoints pause/seek/resume/stop all 200 and
  reflected in the session (paused true, position 12 -> 600), and the
  **auto-restore to hdmi1 fired by itself** after the stop. TV then off.
- whisper-asr on Vulkan: live service transcribed 60s of film dialogue
  accurately in ~2s.
- gamescope-wrap rig: all checks pass (fallbacks, refusals, laundering).
- differ over the post-deploy window: VALID, 0 gating, acted 12, 0 failures,
  edge-to-decision p50 71ms on the new model.

**HDR AUTO-ROUTING: BUILT + INSTALLED, DELIBERATELY SWITCHED OFF.** Donnie's
ruling: a plain click on an HDR/DV film should play on the TV's Jellyfin app;
SDR stays in Kodi. Server half is LIVE and verified (GET
/api/tv/should-route: The Batman -> route true "HDR10 on the TV app";
Batman Returns -> false "SDR, Kodi plays it"; junk id -> false). Kodi half
(service.couch.autoroute) is installed and running but its setting is
pre-seeded FALSE **and** the server kill switch file exists
(~/couch/data/tv-autoroute-off) - EITHER off means no routing.
TO TURN ON (do it with eyes on the TV): rm ~/couch/data/tv-autoroute-off,
then set the addon's toggle on (Settings > Add-ons > service.couch.autoroute).
WHY IT IS OFF: Kodi 20 has no pre-play veto, so the addon lets Kodi start and
then stops it - expect a visible flicker/busy-dialog before the TV takes over,
and Kodi WILL write a resume position on that stop (unverified whether it
damages the resume point of a part-watched film). Watch both on the first try.
KNOWN GAP - cinema lights: TV playback now drives the lights via the `lights`
CLI (dim 10, restore on stop/pause). light-watch instead speaks WiZ UDP
directly (2200K, per-bulb save/restore, 1.8s ramp), so TV-playback lighting
is slightly different (2700K, all-bulbs) and the two can confuse each other
(light-watch may capture our dimmed state if a Kodi film starts during a TV
playback). Proper fix = teach light-watch about TV playbacks (a ~/.local/bin
edit, needs its own review). Lights cannot get stuck through the normal
paths (disown/failed-handoff/15-min blind timer all restore).

**TRANSITION SPEEDUPS BATCH 1 DEPLOYED + SWEPT (7 Aug ~00:05, commit
651d6ac):** resume sleep-1 -> 100ms converge (expect ~0.45s resumes),
launch BP-hide lands on window-map, BP-confirm/teardown polls at 0.25s
grain (same totals/graces), screen.js guard beat polls the pidfile,
curtain probe dropped. Sweep 12/12 after deploy. Evidence docs:
docs/transition-latency-budget.md + docs/transition-speedups.md.
NOT touched (by class): [DESIGN] BP-before-game overlap (pad-safety
ruling), gesture window constants (0.9 hold / 0.35 double-tap / 1.2
settle), [MODEL] route_pad async hygiene, watcher select-tick (SR4).
Donnie's first resume/launch tonight is the live proof - the phase logger
in /tmp/game-launch.log shows the per-leg ms if it doesn't feel faster.

**DONNIE'S PAD-IN-HAND CHECKLIST (now 2 items, both need a real game):**
(1) with a game paused, double-tap: the sheet should float over the game's
freeze-frame. (2) suspend/resume from the PHONE: first live
curtain (freeze -> fade -> Kodi and back). TV odds+ends still open: soundbar eARC + Kodi passthrough, Deep Colour + Game Optimizer.

## ▶ Previous resume block (updated 6 Aug 2026 ~04:30 — GESTURES ACCEPTED)

**HARDWARE DAY DONE (6 Aug evening): 5700X3D + RX 9070 XT + LG C5 all in
and working.** CPU 8c/16t boosting 4.15GHz, Tctl ~59C. GPU on Mesa 25.2
radeonsi, VAAPI HEVC decode AND encode present (Sunshine keeps hw encode);
gpu-swap script ran clean, no NVIDIA left. TV paired (`tv-setup-lg` ->
~/.config/tv-remote/tv.json backend=webos, 192.168.4.227); `tv`, tv-waker
and the House tab all flipped to webOS automatically and verified live.
**pc_input corrected to HDMI_1** (tv.json said HDMI_2; TV reported hdmi1
active while the PC was on screen - if a wake ever selects the wrong input,
that field is the one to flip). Display: output is now `HDMI-A-0` (was
HDMI-0), running **1920x1080@120** - the C5 offers 4K60/1080p120 over
amdgpu's native HDMI; 4K120 waits on the DP->HDMI 2.1 adapters. Bloodborne
(shadPS4) ran a smooth 60 with dips to ~40 only during shader compilation.
Also: both USB media enclosures were unplugged during the swap and are back,
mounted, pool whole at 5.5T; disk-monitor healthy (it is a 10-min timer).
STILL TO DO on the TV: soundbar into eARC (HDMI 3) + Kodi passthrough,
Jellyfin from the LG store, reserve the TV's IP, "Turn on via Wi-Fi" if not
already, Ultra HD Deep Colour + Game Optimizer on the PC's input.

**ADAPTER-ARRIVAL CHECKLIST (DP->HDMI 2.1, both ordered 5 Aug):**
1. Cable Matters 102101 first (works on stock 6.14): BEFORE fitting, flash
   its VRR firmware from a Windows machine with DP out = Donnie's main PC.
2. Fit into any DP on the 9070 XT; the X output will rename again
   (DisplayPort-N). kodi-tv's TearFree xrandr line auto-picks the first
   connected output; tv.json needs nothing (TV-side port unchanged).
3. Expect 4K120 in xrandr; pick mode. Ultra HD Deep Colour must be ON for
   that TV input or the link caps out.
4. VRR honesty: X11 only engages VariableRefresh (already in
   /etc/X11/xorg.conf.d/10-amdgpu.conf) for UNREDIRECTED fullscreen, and the
   compositor stays on (hard rule), so X-side VRR will mostly not engage.
   The real VRR/HDR path is gamescope = stage 3
   (docs/gamescope-spike-20260806.md once the spike lands).
5. UGREEN 85564 is the better adapter but its VRR needs a kernel patch that
   was not mainlined as of 5 Aug - re-check patch status before choosing it.

**RX-unlocked prep status (6 Aug evening):** xorg VariableRefresh pre-staged
by the swap script; House GPU card verified reading amdgpu sysfs; MangoHud
already installed; whisper-asr running on CPU int8 fallback (Vulkan
whisper.cpp build+benchmark agent running); gamescope source-build
feasibility agent running (no noble apt package).

**SWITCHER: root cause FOUND AND FIXED (commit 44a2379), but left OFF pending
one pad test.** The animated sheet ate every select press because **Kodi
reserves control ids 2/3/4/12** - `WindowXML::OnMessage` intercepts clicks
from them for its internal sort/view buttons ("WindowXML: Internal sort
button not implemented" in kodi.log at the exact moment of each press) and
returns before Python's onClick. The list was id 3. Renumbered to 9000
(the XML dodged 50-59 but nobody knew about 2/3/4/12); the `_filled` re-init
path now re-asserts focus too. **Deployed and verified live** while Donnie
was out: onClick fires ("couch.switcher: activating ..."). NOT verified:
row-to-row navigation - RPC-injected Input.Down landed inconsistently (two
test picks activated the wrong rows), which may be an artifact of injecting
input rather than a real bug, since the pad path is different. So
`ui.animated_dialog` is still **false** (stock dialog in use, works).
TO FINISH: flip that setting to true, double-tap with the pad, confirm the
stick moves the highlight and a press picks that row. Then the freeze-frame
backdrop can be judged too. Expect one cosmetic "Control 9000 ... asked to
focus, but it can't" line per open (WINDOW_INIT racing Python's addItems);
it is not a failure.

**DEPLOY-DAY PROGRESS (~13:30, commits da20a80..cdbe999):** checklist items
1, 2, 4-8 are LIVE and committed: guard cleanup (+curtain skip + fifo inode
guard), BP-hide (+launch-path retry after it missed live - HK maps at ~20-25s,
focus_game now converges, show intent honest), yield pids, curtain whitelists
in all THREE places (watcher, couchd fg region, GUARD - review caught the
third), oracles (snapshot order-anchored, iconify stacking-based, BP launch
window-based), differ exemption + pre-declarations, FFCP gone from kodi-tv
AND live, fingerprint now 6c658480a2da, post-restart sweep 12/12. Animated
switcher DEPLOYED with label hotfix + freeze-frame backdrop (Donnie's
"switcher over the game" ask - pending his visual verify). STILL OPEN today:
switcher visual verify (labels + backdrop), curtain standalone test + wiring
into game-launch suspend/resume, final sweep, CPU work. Hardware: 5700X3D +
LG C5 arriving today (tv-setup-lg flow below; C5 needs LG control wired into
tv-waker eventually - `tv` speaks Toshiba).

**FIRST FLIP ACCEPTED.** Donnie accepted `gestures` at ~04:15 BST 6 Aug after
the overnight couch pass (02:30-04:15, Hollow Knight + Big Picture, every
scripted step run). couchd keeps owning gestures; nothing else is flipped.
Full evidence: `docs/acceptance-20260806.md`. Differ re-run:
`tools/shadow-diff --window 02:30-04:10` (VALID, 207 decisions).

**The night in one line:** acted 87, action_failures 0, refused 0, 0
OWNER-MISSED rows, edge-to-decision p50 83ms / p95 191ms (bound 250), every
first-live-run item passed (spawn_guard, launch-resume oracle, coalesced
double-tap under real timing), yesterday's BP flag-fight fix held (pad stayed
on Kodi, no tug-of-war), BT-drop reconnect produced zero phantom gestures.

**Differ gating 14 — all explained, none a couchd misbehavior:**
- 10x freeze SET-MISMATCH: legacy's YIELDED would-freezes all record pids=[]
  (its acting thaws resolve 18 fine) — legacy yield-path recording bug (T3).
- 2x ORDER on BP holds: "freeze before flag" assertion not aware pids-less
  BP sessions skip freeze. Assertion gap.
- 2x missed effects (honest): close_steam_menu (menu not routed, 8.5s) and
  launch-bigpicture (oracle waits on game pids; BP has none).
Plus 13 invariant records = stale guard pidfiles (see finding G below), and
matched-offset p95 ~1s = legacy's lazy shadow writes (not couchd's latency).

**DEPLOY DAY (today, in order).** Steps 1-5 were already agreed; 6-9 are from
the acceptance night:
1. Whitelist WM_CLASS couch-curtain in BOTH stacks' foreground classification
   (model change: differ note, fingerprint moves, couchd restart).
2. Reload the switcher addon; verify dialog draws + stick navigates during the
   slide + effect verdicts confirmed.
3. Live-test curtain standalone; then wire curtain into game-launch
   suspend/resume.
4. **steam-input-guard cleanup on exit** (pidfile + vpad.fifo). NOT cosmetic:
   with a stale vpad.fifo present, every later guard logs vpad_started:false
   and menu-closing is silently dead for BOTH stacks (proved live: cleanup at
   03:41 -> next guard's vpad worked). Also dedupe the guard-supersession
   protocol (see ruling R-a).
5. **Hide/minimize Big Picture's window once the game window maps** (in
   game-launch AND its resume path). Root cause of the night's fps saga:
   BP left mapped fullscreen behind the game = compositor juggles stacked
   live surfaces = "Steam says 60, feels 20". Minimizing BP fixed it
   instantly, twice. (couchd transitions model wants the same move later.)
6. **kodi-tv FFCP decision**: line 24 reapplies ForceFullCompositionPipeline
   on every Kodi start; it double-composites games under xfwm4. I removed it
   live at ~03:25 (returns on next Kodi restart). Decide: drop it / make it
   session-conditional. xfwm4 compositing MUST stay on (two live experiments
   of turning it off under a fullscreen game broke presentation: black
   screen / frozen frame with audio). Check Kodi for tearing without FFCP.
7. Effect-oracle fixes: snapshot + iconify verdicted UNVERIFIED on all 5 live
   suspends (5-17s timeouts) — they never confirm in the real environment;
   launch-bigpicture needs a window-based oracle (no game pids); BP-hold
   ORDER assertion exemption (item above).
8. Legacy yield-path pid recording bug (the 10 SET-MISMATCH rows).
9. gesture-sweep 12/12 must pass after ALL of it.
Also queued: CPU work (60fps cap via DXVK_FRAME_RATE + MangoHud in Steam unit
env — MangoHud also wanted for real frame-time debugging; CPUWeight slice;
game-session-keyed governor watcher — governor flip needs sudo, Donnie's
list). GPU PowerMizer pinning was tested and is NOT needed (red herring).
Maybe: session-start volume clamp (fresh game streams open at 100%; one blast
at ~03:30. Master baseline set to 60%).

**NEW RULINGS for Donnie (from the acceptance night):**
- R-a: guard supersession across stacks. Legacy's switcher-pick resume
  spawned guard(game) which SIGTERM'd couchd's freshly spawned kodi-guard
  ("superseded-by-newer-guard") and enforced game-on-top against the suspend
  the user just asked for (the 03:16-03:20 Kodi<->BP loop). Who arbitrates
  when stacks disagree, until `guard` flips?
- R-b: switcher-pick resume routes through Steam BP ("show game via steam")
  on EVERY session shape — user picks a game, sees Steam's shell first. Keep
  (with BP hidden after, per deploy item 5) or reroute?
- R-c: switcher's Big Picture tile pressed while a session sat FROZEN hung
  Steam BP "loading" forever (blocked on SIGSTOPped game IPC); Donnie's
  tap-resume unstuck it. Disable/thaw-first?
- (Standing rulings from 5 Aug remain: settle window, phone suspend/quit
  yield, differ launch verb, hold-handoff-at-release, ACTED-ONLY gating.)

**HARD GATE for the reconcile flip (do not flip until fixed):**
`refreeze-lost-suspend` fired in shadow 3x live (03:18, 03:33, 03:42): legacy
resume thaws BEFORE clearing the suspended flag; in that gap couchd-owning-
reconcile would RE-FREEZE the game mid-resume, every time. Fix the ordering
(or model the resume window) first.

**Live state (all reversible, none committed config):**
FFCP off (until next Kodi restart), xfwm4 compositing ON, PowerMizer auto,
BP window minimized, master volume 60%, /tmp guard pidfile+fifo cleaned once
at 03:41 (new stale ones have accumulated since — deploy item 4).
Console left on Kodi home, no session, couchd acting on gestures.

**Environment notes that cost time tonight:** /tmp/couchd.log timestamps are
UTC (BST-1); python-xlib's damage/error decoding is broken on this box (use
MangoHud tomorrow, not X11 archaeology); tools/game-pids does not exist (the
real one is on PATH as `game-pids` in ~/.local/bin).

## ▶ Previous resume block (5 Aug 2026 ~15:40 — first flip live, pre-acceptance)

**`gestures` IS FLIPPED AND ACTING** (owns.conf, since 13:01). couchd
executes the PS-button vocabulary; pad-home-watcher yields and shadows it.
Rollback: empty `couchd/owns.conf` (instant), or `systemctl --user stop
couchd` (legacy takes it back within 30s via the heartbeat lease).
**Acceptance is still OPEN**: Donnie's evening pass is the gate.

Afternoon (commits f3ee617..bf34a27):
- Real-pad mini-test 13:56: 8 acted, 0 failures, switcher confirmed on
  screen. But it silently DROPPED one double-tap (see below).
- Synthetic pass in the fake-pad inhibit frame (14:07-14:15, TV never
  woke) found 3 bugs, all now FIXED in bf34a27:
  1. **Coalesced double-taps were silently dropped** (gating). Tap-1
     release + tap-2 press inside one ~50ms pass coalesce, the machine
     never reached `down-again`, no intent, no failure counter. Hit
     Donnie's own 48ms double-tap at 13:57:11. Fix: the table asks
     `gesture.PressTracker`'s decision (computed at the press in kernel
     time) from every state with a press in flight. Gaps 0/48/60/120ms
     all fire now; >=350ms correctly does not; multi-tap collapses to one.
  2. `show_switcher` had NO effect check and Kodi is the rate-limited
     observer, so an open dialog verdicted "unverified" forever. Added the
     check (window 12000) + targeted Kodi reads while a prediction is
     outstanding (0.5s floor).
  3. A no-session PS hold made couchd act where legacy does nothing. Now
     gated on `session_present`; "PS hold as universal return-to-Kodi"
     is a T5 candidate awaiting Donnie's ruling, NOT live.
  Plus: gestures that decide nothing now log `gesture-no-op` (a silent
  no-op is indistinguishable from a dropped press - that is how 1 hid).
- **Differ is post-flip aware**: reconstructs per-responsibility ownership
  windows, swaps roles when couchd owns (ACTED-ONLY/SHADOW-ONLY), never
  files yielded data as legacy-only, and prints an ACTING HEALTH block.
  First post-flip run: 12 acted, **0 gating divergences**, edge-to-decision
  **p95 97ms** vs the 250ms bound (Evening 1 baseline was 1445ms).
- `intents-archive.timer` (2 min) copies /tmp/legacy-intents.jsonl into
  shadow/legacy-intents-YYYYMMDD.jsonl - the last corpus that lived only
  on /tmp, which the 05:19 reboot ate mid-flip.
- Legacy bug 3 FIXED: tv-waker + pad-connect-daemon match a real DualSense
  by device name instead of any js* (Sunshine's virtual mouse held js0, so
  the TV silently stopped waking on pad connect). **`sudo systemctl
  restart pad-connect` still owed** to load it there.
- NEW legacy bug found live: Kodi can miss the BT-disconnect udev event,
  keep deleted fds, and never re-open the reconnected pad (dead controller
  in the UI). tv-waker now verifies Kodi holds the real node after each
  connect and toggles peripheral.joystick to force a rescan. Kodi's raw
  hotplug worked on all 3 later connects, so it is intermittent.
- Model fingerprint moved to `ecd01e9fdfa3` at 14:31. Tonight's pre-14:31
  rows read as stale-model; use `tools/shadow-diff --window` for a
  whole-evening read.

Late afternoon while Donnie was out (commits 500c6ae, 87c40fa):
- **Synthetic gesture sweep 15:22-15:25: 12/12 PASS, 0 action failures,
  TV never woke, frame restored, corpus clean.** `tools/gesture-sweep`
  (new, committed) drives fake-pad through the whole unexercised list:
  gap sweep 0/48/60/120/350ms (0/48 coalesce and take the bf34a27 edge
  from `down`, 60/120 walk `down-again`, 350 stays two singles), all 5
  switcher effects verdicted **confirmed** (0.8-1.7s vs the 3s deadline),
  no-session holds log their no-ops, tap-then-hold decides hold, stuck
  hold reaches release-never-came, 5-tap burst collapses to one switcher,
  uhid disconnect mid-hold survived acting on nothing. The bf34a27 fixes
  are end-to-end confirmed through the real acting daemon.
- Sweep review found a live-console fact worth knowing: **Kodi's own
  joystick layer opens the tv-poweroff context menu (10106) on every
  >=1s PS hold** (peripheral.joystick buttonmap + gamepad-poweroff.xml
  holdtime). Normal console behaviour, but the sweep dismisses 12000/
  10106 between scenarios and asserts nothing modal is left standing.
- fake-pad grew a `sleep` command (gap timing in the rig's own stream).
- **Legacy bug 5 FIXED**: server/sys.js + server/steam.js now identify
  the game via `game-pids` (Steam's reaper tree) instead of
  `pgrep -f steamapps/common` - the phone's suspend button can no longer
  SIGSTOP a bystander, and under Proton it now finds the real game
  (S:\ cmdlines never matched the old pattern). Errors fail safe.
  couch restarted on the fix; phone UI verified serving.
- Suites: 608 passing (couchd 430 + tools 178).

Review-fleet pass (~16:00-17:15, Donnie's "wire it in now then fix
everything else", commits a414699..d43fb75):
- Four Fable adversarial reviewers swept the codebase; every confirmed
  finding is FIXED except three design questions left for Donnie (below).
- **Guard wired in** (a414699): couchd's acted handoffs spawn the real
  steam-input-guard exactly where legacy's handoff_to_kodi did; the verb
  is pre-declared T5 in the differ (legacy's spawn was implicit).
- **couchd model** (99901a4, d43fb75): the whole coalescing family is
  closed with CONSUMABLE tracker markers (hold_release_k + double_tap_k,
  twins of double_armed but spendable) - a whole hold or whole double
  swallowed by stalled passes now decides from idle; escape verbs cap
  backoff at 30s; a failed step skips its same-pass dependents; freeze
  effects no longer count vanished pids as frozen; launch-resume has a
  real oracle; couchd declines to act on a stale own-heartbeat (closes
  the both-stacks window); rebind hazards closed; iconify waits for the
  pause snap; stale Steam routes can't justify guide presses.
- **Differ gates honestly** (e393061): action failures, missed effects,
  SHADOW-ONLY owner-inaction and pid-set-different repeats all gate now;
  crashed runs split correctly (the 05:19 freeze reads right); rollover
  seeds anchors from yesterday. "gating 0" finally means something.
- **Server** (0109a45): install() can't kill Steam under a session;
  phone suspend = full game-launch suspend; MJPEG backpressure; CSRF
  cover on POSTs; corrupt appinfo.vdf can't spin the loop; game-launch
  suspend/resume/quit serialize on a flock.
- **Rigs** (e921dac): fake-pad signal-safe + atomic claim; sweep
  re-checks safety before every press; intents-archive survives crashes.
- **The sweep caught two of my own regressions live** (16:59 burst, 17:02
  60ms) that 441 unit tests could not - both fixed, final sweep 12/12.
- Model fingerprint is now `d1adeed4083a` (several restarts this
  afternoon; tonight's differ read MUST use --window from ~17:10).

Transition polish track (evening, Donnie's "start on transition stuff",
commits 4912383 + 049d114 - BUILT AND TESTED, NOTHING DEPLOYED):
- `tools/curtain`: freeze-frame overlay hiding the suspend/resume window
  shuffle, synchronous show (~0.24s), fade via compositor opacity,
  double watchdog (a stuck curtain is impossible), click-through, 40
  Xvfb-isolated tests. NOT wired into anything yet.
- Switcher dialog rebuilt as an animated bottom sheet (280ms slide+fade
  in, thumbnails), addon-local textures so skin updates can't revert
  it; `ui.animated_dialog=false` = instant rollback to the stock
  dialog; XML failure falls back to stock loudly. couchd's effect check
  and the sweep already accept both window shapes (12000 + the
  13000-13099 python-window pool - Kodi can't pin custom dialog ids).
- DEPLOY DAY (after the gestures acceptance, in order): (1) whitelist
  WM_CLASS couch-curtain in BOTH stacks' foreground classification
  (couchd fg region + legacy frozen-game-visible repair) - a model
  change: differ note, fingerprint moves, couchd restart; (2) reload
  the switcher addon, verify dialog draws + stick navigates during the
  slide + effect verdicts confirmed; (3) live-test curtain standalone;
  (4) wire curtain into game-launch suspend/resume; (5) gesture-sweep
  must pass 12/12 after all of it. Longer arc: the curtain becomes
  couchd's opening move when `transitions` flips.
- Also agreed in chat, not yet built: CPU work for tomorrow (global
  60fps cap via DXVK_FRAME_RATE + MangoHud in the Steam unit env,
  CPUWeight slice for qB/arr/Jellyfin, game-session-keyed governor
  watcher - governor flip needs sudo, goes on Donnie's list). GPU plan:
  9070 XT stays on Ubuntu (kernel 6.14 + Mesa 25.2 ready); SteamOS
  ruled out for this box; stage 3 gamescope spike after the swap.

**NEXT:** (1) Donnie's evening pass = the acceptance for `gestures`;
(2) morning after: `tools/shadow-diff --window` over the evening (the
differ now gates on acting health too);
(3) then the next flip (`reconcile` argued next), one at a time;
(4) fault rig (needs him + a live game); (5) rulings: the three below
PLUS two new from the fleet: should hold=switcher defer its handoff to
release like suspend does (currently hands off mid-press, a pinned
earlier decision the review challenged), and should ACTED-ONLY differ
rows gate post-flip (currently hand-triage).

**Suites:** couchd 441, tools 213, gitleaks clean.

### TV upgrade — BOUGHT 5 Aug evening: LG C5 + Hisense AX5140Q (5.1.4)

Arrival day: TV = the tv-setup-lg flow below; soundbar = C5 eARC port
(HDMI 3 on most C5s), enable passthrough in Kodi audio settings, TV
sound out = HDMI-ARC device. Also install Jellyfin from the LG store
(native 4K HDR/DV) and reserve the TV's IP on the router. Un-parks
couchd stage 3 (HDMI 2.1 + VRR exists now).

**GPU swap-day is prepped (5 Aug):** base OS is already RDNA4-ready (Mesa
25.2, kernel 6.14, navi48 firmware present). Pre-staged: couch House GPU
card reads amdgpu sysfs when nvidia-smi is gone (cb102ca), whisper-asr
falls back to CPU int8 by itself, kodi-tv applies amdgpu TearFree
alongside the NVIDIA line, Sunshine auto-detects VAAPI (nothing pinned).
Swap day = fit card + PSU, then `sudo bash ~/gpu-swap/gpu-swap-9070xt.sh`
(purges NVIDIA stack, deletes the xorg.conf NVIDIA pins that would
black-screen X, installs TearFree conf + VA/Vulkan tools), reboot, run
the printed sanity checks. Revert path in the script header.

**GPU swap plan (researched 5 Aug, Donnie leaning yes):** 9070 XT into this
box (PSU swap needed, ~300W card), 4070 to the main PC. On Linux amdgpu can't
do HDMI 2.1 (4K60 max over native HDMI) BUT: (a) DP->HDMI 2.1 adapters are
proven at 4K120+HDR+VRR on AMD+LG OLED - buy BOTH the UGREEN 85564 (CH7218,
best, VRR needs a not-yet-mainlined kernel patch) and Cable Matters 102101
(works on stock 6.14, VRR firmware must be flashed from a Windows DP machine
= Donnie's main PC, some flicker reports); (b) AMD started landing OFFICIAL
native HDMI 2.1 FRL+VRR kernel patches mid-2026, expected in a released
kernel ~7.3/7.4, so the adapter is a bridge not a life sentence. AMD also
unlocks Kodi GBM HDR + gamescope HDR properly. Sequence: RAM freeze
investigation closed -> PSU+GPU swap -> display-stack work. Whisper ASR
(Bazarr) is CUDA today, needs CPU/Vulkan rework after the swap.

**Switch-day is prepped (5 Aug):** webOS backend built beside the Android TV
one; `tv`/`tv-waker`/couch House tab all flip over when
`~/.config/tv-remote/tv.json` exists. Day-one steps: plug in the LG, put it
on the LAN, enable Settings > General > Devices > External Devices > "Turn
on via Wi-Fi", run `tv-setup-lg` (accept the prompt on the TV), done.
Optional after: install Jellyfin from the LG content store for native 4K
HDR/DV, reserve the TV's IP on the router. Rollback: delete tv.json,
restart tv-waker. The webOS code is untested until a real LG exists.

The current 1080p60 Toshiba with no VRR is what parks stage 3. Any HDMI
2.1 + VRR set un-parks it. The 4070 + 5700X3D drives 4K60 comfortably
(DLSS for heavy titles; at 4K everything is GPU-bound so the CPU is never
the limit), and 4K120 + VRR is the actual upgrade worth paying for.

Shortlist, UK prices checked 5 Aug:
- **LG C5 42" - the pick for a small room.** Full gaming spec survives at
  42" (4x HDMI 2.1, 4K144, G-Sync + FreeSync + HDMI VRR, ~9ms lag);
  panel is 20-30% dimmer in HDR than 55"+ (no Brightness Booster), blacks
  identical. New floor today £749 (Crampton and Moore / Spatial); Richer
  Sounds £769 with code RSTV80 buys a **6-year** guarantee; John Lewis
  ~£729 list with a 10% member discount and **5-year** guarantee is the
  best route if live. Dipped to £611-656 in June, cycles roughly monthly.
- **Currys eBay refurb 42" C5 £597**, "excellent", 12-month warranty -
  cheapest way in, and below every live new price.
- **LG C5 55" £969 / 65" £1,499** if the room suits it. C6 (2026) is
  better (165Hz, ~20% brighter) but not £700 better.
- **Burn-in-proof alternatives:** Samsung QN90F 43" £589 (only non-OLED
  sub-50" with real HDMI 2.1; no Dolby Vision, hurts the Jellyfin
  library), TCL C8K 65" ~£1,199 (only 2x HDMI 2.1, no 55" in UK).
- **No-gaming budget baseline:** TCL C6KS 50" ~£400. Kills stage 3.
- Skip Samsung generally here: no Dolby Vision or DTS anywhere in range.
- Sub-50" TVs with real HDMI 2.1 barely exist: TCL/Hisense/Sony UK ranges
  start at 55" for 120Hz. The gap between "best £400 TV" and "cheapest
  real gaming TV" is only ~£200.

Burn-in worry is handled: TV off when idle + Kodi screensaver now set to
black at 5 min (was none at all). OLED is fine for this usage.

**When a TV lands, couchd/homelab work:**
1. Port the `tv` command + tv-waker from Toshiba to LG webOS network
   control (the RTX 4070 passes no CEC at all, so network control stays
   the mechanism; webOS does network + WoL well; Pulse-Eight USB-CEC
   adapter is the fallback).
2. Set the input label to "PC" or 4K text fringes (chroma subsampling).
3. Add TV-standby-on-idle: couchd already knows menu + no playback + pad
   absent, which is exactly the trigger.
4. Revisit stage 3 (gamescope) - it only pays off with VRR. Known
   blocker to check first: NVIDIA's Linux driver has documented
   HDR+VRR flicker inside gamescope above 1440p120, driver-side and
   TV-independent.
5. 10-min panel check inside the return window: full-screen colour
   slides via Kodi for dead pixels, banding, uniformity.

## ▶ Overnight mandate (5 Aug 2026 ~08:45) — DONE

**THE OVERNIGHT MANDATE IS COMPLETE** (6 commits, 0e1169f..f3ee617):
task 0 startup hang fixed (fifo blocking open + faulthandler), task 1
acting executor + COUCHD_OWNS lease + legacy yielding flip-ready and
adversarially reviewed (7 SEV-2s found and fixed, ships OFF, owns.conf
empty), task 2 x11 events unswallowed + gesture-edge decisions + 9/10 T5
catch-ups, task 3 Evening-1 replay (38 divergences closed, matched 93->138,
found 3 real T4s, ALL FIXED: conditional guide press, verified supersede
kill, shared repair cooldowns; differ got model-version staleness +
--window + honest verdicts), task 4 fault rig staged NOT run, task 5
suites 410+167 green + gitleaks clean + MORNING SUMMARY written.
**READ: docs/handoff-2026-08-04.md MORNING SUMMARY** (top) - Donnie's
daytime list and the three rulings. docs/replay-2026-08-05.md has the
replay analysis.

**THE BOX HARD-FROZE at 05:19** (idle, no logs, lights on / no ssh / no
video; power-cycled 08:05; first ever; 27h after the RAM swap). RAM
config is prime suspect - dmidecode check + BIOS stock speed test are
item 1 on Donnie's sheet. A 16-min graphical-session cycle at 04:41
remains unexplained (not agents, not updates, not lightdm). Everything
recovered green at boot; snapshots-20260805.jsonl has a NUL crash hole
(the differ now counts and skips those).

**NEXT (in order):** Donnie's daytime sheet (morning summary items 1-4),
then Evening 2 per the compressed gate plan below, then daytime flips one
responsibility at a time. Legacy scripts are mirrored in legacy-mirror/
(deploy = cp to ~/.local/bin). The couch server/web now show owns state
on the Screen-tab card.

**5 Aug daytime notes:** gestures FLIPPED live ~13:01 (first flip; couch
acceptance pending Donnie's pad pass). RAM is at stock 2667 (XMP off), so
the freeze wasn't a boosted profile; if a second freeze happens, BIOS
"Power Supply Idle Control = Typical Current Idle" + overnight memtest.
Kodi screensaver set to black @ 5 min (was: none) for OLED safety. TV
shortlist researched (LG C5 65" ~£1,499 is the pick, agent report in
session); when a TV lands: port `tv` command + tv-waker to LG webOS
network control, add TV-standby-on-idle (couchd knows menu+no-playback+
pad-absent), revisit stage 3 (mind the NVIDIA gamescope HDR+VRR flicker
issue above 1440p120).

## ▶ Previous resume block (5 Aug 2026 ~03:15 — after Evening 1)

**EVENING 1 IS DONE and it worked**: 9 real bugs found with Donnie on the
couch, 8 fixed live + 1 deliberately stopped (see below), differ v3's
verdict on the current-model window: 0 gating divergences across 76
matched decisions. couchd out-decided the legacy stack during a live race
(guard thawed a fresh freeze; couchd re-emitted the correct freeze).
Evidence: docs/handoff-2026-08-04.md + this file's 5 Aug changelog +
shadow/couchd-20260805.jsonl + /tmp/legacy-intents.jsonl (copy into
~/couch/shadow/archive/ before any /tmp cleanup!).

**THE AGREED DECISION (Donnie, 03:00): stop fixing legacy coordination
bugs — accelerate the cutover.** The remaining visible issue (tap-resume
menu/raise dance, ~5s, always converges) is the coordination class that
couchd deletes by construction; patching it further = reimplementing
couchd in bash. Interim workaround given: resume with A on the tile, not
PS tap.

**OVERNIGHT MANDATE (Donnie, 03:15): execute everything remaining toward
flip-readiness while he sleeps.** Boundaries: NO real-game launches or
anything that wakes the TV or makes noise overnight (tv-waker fires on
launch; he is asleep at home) — synthetic/fake-pad work uses the rig's
inhibit frame only; no COUCHD_OWNS flips without his daytime acceptance
(charter). The work list, in order:
0. **FIRST: couchd is stuck "activating" as of 03:05** — watchdog killed
   it ~03:00, restart hangs before sd_notify READY (last log line
   02:57:51, single thread). Diagnose the startup hang (run foreground,
   faulthandler/SIGABRT for the stack; suspect a blocking observer init —
   Kodi socket / Steam log seed / pad node — that lacks a timeout under
   tonight's new conditions: BP mode churn, paused game). Fix + add a
   startup watchdog test. A down shadow costs nothing tonight, but the
   overnight work needs it healthy.
1. **Acting executor** in couchd + COUCHD_OWNS plumbing + legacy yielding
   (watcher/guard skip responsibilities couchd owns; couchd write-through
   of /tmp flags per R5-17). Adversarial review before merge (charter).
2. **couchd daemon fixes**: x11 observer emits NOTHING (wire its event
   subscription — blocking window-enforcement flip); gesture-adjacent
   show/route decisions must ride the gesture edge not the 5s tick
   (p95 1.4s vs 250ms bound); model catch-up for all "couchd model
   catch-up pending" T5 notes (iconify, refreeze, supersede-kill,
   suspended-mid-window, BP ensure/adoption, desktop-overlay close,
   snapshot, show_switcher on paused double-tap, settle window).
3. **Replay Evening 1** through the updated model (recordings/ has the
   real corpus + snapshots + legacy intents) — diffs should drop to
   ~zero retrospectively; what remains is real and gets triaged.
4. **Injected-fault rig staged** (commands scripted, NOT run overnight —
   they need a live game; morning/daytime job, listed on his sheet).
5. Re-run full test suites + gitleaks; commit each stage; update
   docs/handoff sheet with a fresh "MORNING SUMMARY" section on top:
   what's flip-ready, what needs his daytime 5 minutes.
Charter rules stand: shadow until his acceptance, one responsibility per
flip, daytime flips, rollback = stop couchd + old stack intact.

## ▶ Previous resume block (4 Aug 2026, late night — couchd build session)

**READ FIRST: `docs/handoff-2026-08-04.md`** — the phone-readable sheet for
Donnie (what to test, the one command needed before pad use, the two
decisions only he can make). This block is the technical version.

**couch is now a GIT REPO** (standing risk closed). ~20 commits, history
born clean: all secrets scrubbed to `.env` (`server/config.js` reads env;
`data/secrets.json` legacy file still on disk, gitignored, deletable once
healthy), gitleaks-verified. Local only, no remote. `.env.example` current.

**LIVE on the box now** (all reversible; `systemctl --user stop couchd
pad-record` = back to 4-Aug-green, and that line is cheat-sheet line 1):
- `couchd.service` — stage-1 SHADOW daemon (`couchd/couchd.py`, 2.2k lines
  + `x11.py`). 7 observers, orthogonal state regions with `unknown`, pure
  `reconcile(observed)->intents`, invariants incl. owned-resources leak
  check, JSONL corpus in `shadow/`, `status.json`, Type=notify + watchdog,
  crash-loop-safe (Restart=on-failure/RestartSec=10/StartLimitBurst=5).
  Acts on NOTHING (only RecordingExecutor exists).
- `pad-record.service` — recorder, fixed: mtime-stamped markers at ~100ms,
  inline gzip, 14-day retention.
- Old stack instrumented (R3): watcher/game-launch/guard write machine
  intents to `/tmp/legacy-intents.jsonl` (log-only edits, behavior same).
- Phone: `/api/couchd/status` + Screen-tab couchd card.
- **Double-tap PS → TV switcher** (`script.couch.switcher` Kodi addon,
  versioned in `kodi-addons/`) and **gesture keybind settings** in Kodi
  (`couchd/gestureconf.py` is the single source both stacks read; safety
  rail forces a suspend_to_kodi binding). Both verified live tonight.

**NEXT (in order):**
1. **Donnie's couch pass** — checklist in the handoff sheet (his original
   pad checklist + the three new features). Every evening he uses the TV
   is shadow evidence toward the C9 gates.
   **AGREED 5 Aug: the compressed 2-evening gate plan.** The C9 unit is
   transition coverage, not calendar. Evening 1 = directed scripted pass
   (write the numbered phone-readable step list into the handoff sheet
   FIRST) + live differ triage between segments (expect T1 comparator
   artifacts, fix in-loop) + injected-fault runs with legacy repairs
   briefly paused (Donnie present = the charter's monitoring). Evening 2
   = clean re-run + 1h organic free play. Gates close → COUCHD_OWNS
   flips happen in a DAYTIME window, one responsibility at a time, 5-min
   couch acceptance each. Post-cutover, Donnie reports bugs by timestamp
   (the corpus has the full decision trace); each becomes a replay test;
   two unexplained regressions = auto-revert to shadow per charter.
2. **Morning after any evening:** `~/couch/tools/shadow-diff` (offline,
   never touches the TV). First real run: VALID, 0 divergences.
3. **Donnie's sudo session — DONE 21 Aug 2026 ~22:50** (INSTALL.md steps
   1-8, prompted by bug #9 surfacing on Elden Ring that evening). All
   verified live: couchd-input user/group (ds2000 NOT in the fence),
   rollback script root-owned + NOPASSWD proven by an actual rehearsal
   (disarm -> .off -> re-arm), unit installed disabled, ACL probe
   write+read both directions, rule armed RIG-SCOPED (de:ad:be:ef:fa:ce)
   and confirmed NOT matching the real pad (event18 keeps
   user:ds2000:rw- + uaccess; hidraw2 ACL intact; NB event20 is the
   TOUCHPAD node - don't check ownership there). STILL TO DO from this
   step: fix pad-connect-daemon + tv-waker's any-`js*` checks (see Open
   decisions). Next: E1 fake-pad ladder (E-runbook.md, no sudo), then E2.
4. Then E2 (Steam adopts the virtual pad; daytime, back up
   `~/.steam/debian-installation/config` first), then stage-2 flag day.

**Deferred to a daytime window:** psfuzz/chaos identity runs with couchd
live (M9), the `STEAM_GAMES_RUNNING` atom re-test with a game running.

## Changelog — 2026-08-04 (late night, couchd build session)
Notes: `docs/couchd-stage1-design.md` (C1-C31 + rulings R1-R8),
`couchd-stage2-design.md` (S1-S9 + SR1-SR9), `couchd-stage3-design.md`.
- **Stage 1 SHIPPED to shadow.** /build pass (3 research agents: parallel-run
  practice, reconciler/statechart architecture, console-daemon prior art) then
  2 adversarial reviews. Biggest ruling: the old stack ALREADY logs its
  decisions, so the planned effect-inference engine died and ~4k LOC became
  ~1k. couchd + `tools/shadow-diff` (22 tests) + 30→191 test suite.
- **Stage 2 designed and built synthetic-only.** InputPlumber evaluated per
  charter and DECLINED with receipts (root-only #202, crash-bricks-pad #582,
  20-month rumble TODO #224, no kernel timestamps); its udev technique,
  persistence and 80ms chord pacing ported instead. Review found 8 blockers
  (no-root claim unimplementable as written → system-user model; 0640 would
  have silently killed rumble; sudo-at-night rollback; rig would wake the TV).
  Built: `couchd/gesture.py` (shared), `inputproc.py` (grab + exact-vpad X360
  clone + full FF contract), `tools/fake-pad` (uhid DS5 rig with inhibit
  frame), `couchd/stage2/` install bundle. **E0 + E1-functional PASSED**:
  forwarding p99 0.065-0.17ms (10ms budget), FF contract live, PS tap
  re-injected at 80.3ms / hold swallowed, persistence machine, Kodi buttonmap
  resolves, face-button transposition confirmed on hardware.
- **Stage 3 PARKED** with a written decision record (nothing to win at
  1080p60 SDR; `~/gamescope-deps.sh` is wrong as staged, corrections in the
  note). Revisit on TV upgrade / in-repo packaging / stage 4.
- **Double-tap PS → TV switcher** and **Kodi gesture keybind settings**
  (Donnie's requests) shipped and verified live.

## Roadmap: couchd (agreed 4 Aug 2026 — build rules: docs/couchd-charter.md)
The accretion phase is over; the architecture is understood (see
docs/audits/console-robustness-2026-08.md = the requirements spec, and
tools/psfuzz.py + tools/chaos.py = the acceptance tests). Strangler-pattern
consolidation into one control-plane daemon; engines (Kodi/Steam/games) stay.
The TV must keep working at every stage. Start AFTER the physical-pad pass.
1. **couchd**: one daemon absorbing pad-home-watcher + game-launch +
   steam-input-guard + reconcile. Internal state machine (no /tmp flags),
   API socket for couch app + Kodi tiles, structured logs, events stream.
2. **Input ownership**: couchd exclusively grabs the DualSense (evdev grab +
   udev-hide hidraw from Steam), presents a virtual pad (uinput/uhid) to the
   focused app. PS button becomes ours by construction; guard war deleted.
   Tradeoff accepted: games see generic X360 pad (no DS gyro/haptics).
3. **Gamescope-nested games**: game launches wrap in gamescope (deps script
   staged at ~/gamescope-deps.sh, needs Donnie's sudo once). Frame pacing +
   contained fullscreen. EXPERIMENT: NVIDIA+X11 is gamescope's weak combo.
4. **Own session compositor** (smithay/wlroots): couchd becomes the session;
   Kodi + games are surfaces. Months; only if 1-3 leave us hungry.

**Publishing (agreed direction):** share as a reference project ("my console
setup"), not a product - killer README from the audit doc, positioned as
"console-ify the box you already have" (vs Bazzite's OS takeover; see the
why-not-Bazzite reasoning: patched bluetooth.ko, X11 click-through, SIGSTOP
suspend all need a mutable X11 box). PREREQS before anything public: git init
(private first), scrub secrets into .env + .env.example (kodi password in
kodi.js, qBittorrent creds in downloads.js, LAN IPs throughout) so public
history never contains them. couchd, once real, is the properly adoptable
core. Generalise (Android TV pairing UI etc.) only if it gets traction.

Older "watch it on the couch" items (media controls track):

1. **Media Session / lock-screen + Dynamic Island** — REWRITTEN to an endless
   silent live stream from the box (`GET /api/silent`, ffmpeg anullsrc); no
   scrubber by design (a faked finite track's position can't be synced and
   bounced). Working: lock screen + Control Center + Dynamic Island, correct
   play/pause. KNOWN TRADE-OFF (chosen): the silent stream pauses when the TV
   pauses so the icon is right, which means a *very long* idle pause can let iOS
   drop the Now Playing session. If Donnie would rather keep the notification
   through long pauses at the cost of a less-correct paused icon, flip
   `updateMediaSession` in `web/src/lib/state.svelte.js` back to keeping the
   stream playing. Truly having both needs a native app wrapper.
2. **End-of-stream glitch guard** (`server/index.js reassess`) — YouTube HLS/DVR
   streams can run past EOF with Kodi never stopping (clock ticks past duration,
   no video). Guard stops the player when `position > duration + 3`. WATCH: that
   it backs out cleanly on the next YouTube finish AND never cuts a normal video
   ~3s early (if it does, raise the +3 margin).
3. **Smart rewind** (`server/index.js /api/player/step`) — for streams, pauses →
   seeks → waits for the buffer (`Player.Caching`/`CacheLevel`) → resumes, so
   YouTube rewind comes back cleanly. Confirmed snappier. Local files unaffected.

## Open decisions / risks
- ~~Couch is NOT under version control~~ **CLOSED 4 Aug**: git init done,
  secrets scrubbed first, history clean.
- **Sunshine's virtual `js0` breaks pad reconnect + TV wake** (found 4 Aug).
  `pad-connect-daemon:34` and `tv-waker:39` both test `glob('/dev/input/js*')`,
  so ANY virtual joystick (Sunshine, vpad rigs, the uhid test pad) makes them
  believe the pad is already there. Immediate: `systemctl --user stop
  app-dev.lizardbyte.app.Sunshine.service`. Real fix (needs Donnie): test the
  DualSense's own node instead of any js*. Sunshine is enabled and returns on
  every login.
- **Three legacy bugs found by the shadow work, NOT fixed (Donnie's call —
  behavioral edits to live plumbing).** Pre-declared in the differ so they
  don't read as couchd faults: (a) pure Big Picture PS-holds never write
  `/tmp/game-suspended`, so reconcile takes the pad off Kodi ~10s later and it
  belongs to nobody; (b) games launched FROM Big Picture record appid as the
  literal string `"bigpicture"`, so that game's Kodi tile CLOSES it instead of
  resuming; (c) the guard's pidfile isn't removed on normal exit (couchd's
  owned-resources invariant flags it every tick).
- **Three `steam_app_*` window-class predicates are fragile identity
  assumptions** (steam-input-guard:272, screen.js:271 and :291). They dissolve
  as couchd absorbs those responsibilities (its observation is pid-first);
  only worth fixing sooner if gamescope ever un-parks.
- **No auth** (LAN-only by design). A rota-style login MUST be added before any
  Cloudflare-tunnel exposure (pattern in the ROTA memory:
  rota-app-cloudflare-tunnel, rota-app-accounts).
- **Dynamic Island / lock-screen scrubber** are as good as a web app gets; a real
  Live Activity or a synced progress bar would need a native iOS wrapper.

## Changelog — 2026-08-04 (evening, robustness audit)
Full audit: `docs/audits/console-robustness-2026-08.md`. Headline: **Proton
games never actually froze on suspend** (Proton maps the library to `S:` so
path-matching missed eldenring.exe; only wrappers froze). Fixed with
`~/.local/bin/game-pids` (reaper process-tree identity, shared by watcher /
game-launch / guard / couch server) - verified live, all 18 ER processes
freeze/thaw now. Added: watcher `reconcile()` standing repair loop (orphaned
session, stale flag, lost thaw, joystick drift, frozen-game-visible, ~10s),
guard SIGTERM cleanup, 5s ACL retry.
- [B] Physical-pad end-to-end pass of today's changes (Donnie, from the couch).
- [B] uhid DualSense emulation to synthetically test Steam's hidraw path (project).
- [B] game-pids: exclude transient reaper children that are not games (Steam
  redistributable installers) if a phantom session ever appears.
- [B] Optional: dedicated "rescue" button in couch app (Screen->switcher->Kodi
  already serves as the panic button).

## Changelog — 2026-08-04 (afternoon, state-aware screen switcher)
- **Screen tab's app switcher now speaks the console state machine** (server
  only, no rebuild): picking Kodi mid-game runs `game-launch suspend` (freeze +
  pad to Kodi + guard) instead of a raw X raise; picking a paused game resumes
  it; picking a running game re-focuses it properly. Raw raises could strand
  the box (frozen game on top / Kodi shown while the pad stayed with the game).
- `xinput.py windows` now returns `cls` (wm_class); `screen.js windows()` badges
  the suspended game "· paused" in the list.
- Backing this: `steam-input-guard` (new, ~/.local/bin) enforcement loop after
  every suspend/resume - closes Steam's invisibly-open BP menu (root cause of
  the "black screen + steam menu, controller stolen" bug), re-asserts the right
  window, thaws a game that should be running, and never lets a frozen game sit
  visibly on top. See homelab-console-setup memory for the full story.

## Changelog — 2026-08-04 (media controls + playback polish)
- **Media Session REWRITTEN to a live silent stream.** Journey: generated silent
  WAV in memory → grew it per content (memory blew up on films) → seeking a fake
  finite track to the real position always bounced (iOS reads position from the
  element's own clock). Terminal fix: `GET /api/silent` streams endless silent
  MP3 (ffmpeg anullsrc, `-re`, killed on disconnect); the client plays it as one
  reused, gesture-unlocked element. No duration → iOS treats it LIVE → no
  scrubber, nothing to bounce. Side effect: it now shows on the **Dynamic Island**.
- **Play/pause icon** — iOS reads the icon from the element's paused state, so the
  element mirrors the TV (play/pause). `optimisticPlayPause` now calls
  `updateMediaSession` so an in-app pause flips the lock-screen icon instantly.
- **YouTube auto-1.25x audio-loss FIXED** — applying tempo mid audio-init silenced
  the stream; now settle ~1.3s, apply, re-assert ~2.8s (`applyYouTubeDefault`).
- **Smart rewind + end-of-stream guard** — see Resume items 2 and 3.

## Changelog — 2026-08-03 (evening, UI polish + fixes)
- **Sheet/card animation FIXED.** iOS snaps `transform` on a `position:fixed`
  element nested in scrolled `<main>`. Fix: `lib/portal.js` moves every sheet to
  `<body>` before animating. Entrance JS-driven in `lib/anim.js`; bottom-sheet slide.
- **Exit animations** — `slideDown`/`fadeOut` `out:` transitions on every sheet.
- **Scroll-behind fixed with CSS** — `.scrim{touch-action:none}` +
  `.sheet/.dsheet/.chooser{touch-action:pan-y;overscroll-behavior:contain}`.
  Removed a `position:fixed` body lock that jumped the nav bar + left a grey strip.
- **Safe-area sheet padding** → `max(18px, env(...))` (killed a dead grey band).
- **Discover detail holds until loaded** — fetch + decode art (`img.js
  decodeImages`) before opening; tapped card spins. No piecemeal pop-in.
- **Custom in-app seek scrubber** (Playing.svelte) — `setPointerCapture`,
  `touch-action:none`, optimistic, throttled ~200ms live seeks. (This is the
  in-app bar; the lock screen has no scrubber, see 4 Aug.)
- **TV power toggle on the Remote page** — top row, blue when on, `/api/tv` on/off.
- **Volume row added to Now Playing** (Playing.svelte).
