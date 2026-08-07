# skin.couch console UI - design spec

7 Aug 2026. Research receipts: `docs/research/console-ui-patterns.md` (what
PS5/Netflix/tvOS/Big Picture/Xbox/webOS/Google TV do well and what users
demonstrably hate) and `docs/research/10-foot-ux-and-kodi-engine.md` (vendor
10-foot numbers + what the Kodi engine can actually deliver, from Kodi source).
Base: our Copacetic fork (commit a43c5fa), live on the TV since 7 Aug.

## What this is

Recreate the TV UI as a proper console UI: pad-first, content-first, readable
from the sofa, instant-feeling. Donnie's brief: "based off stuff like the ps5,
netflix, other well known UIs - see what they do well and any things people
don't like."

The one-sentence thesis the research supports: **copy the platforms'
mechanics (focus model, rows, background art), skip their business model
(hero ads, autoplay, promoted content) - and measure everything in button
presses, not pixels.**

## The surface area (measured, couchd logs 4-7 Aug)

Daily: video library 10025 (dominant by 10x), home 10000, fullscreen video
12005 + OSD, the switcher's own dialog. Weekly tail that must stay navigable:
select 10106, yes/no 10100, busy 10138, shutdown menu 10111, keyboard,
settings windows. ~18 windows seen all week out of ~170 skin files - the
restyle touches the daily 8 hard, keeps the tail functional and merely
re-themed.

## Named constraints (each from evidence; parameters fixed now)

- **C1 PRESS BUDGET.** Every screen is judged by D-pad presses to target, not
  looks. NN/g measured 245 presses to browse 500 movies vs 49 with paging.
  Rule: any list > ~30 items gets L2/R2 (or L1/R1) page/letter jump.
- **C2 FOCUS IS MULTI-CHANNEL.** Focused tile: scale 1.05-1.1x (cap 1.1 -
  Google's layout-shift warning) + border/glow + label brighten. Never colour
  alone (Android TV explicit don't; WCAG 3:1 for the ring). Focus animation
  100-200ms; nobody publishes a duration, Netflix got burned going bigger.
- **C3 ANIMATE THE FOCUS, NEVER THE LAYOUT.** No reflow under the pointer
  (Apple "fluid"; Netflix 2025 nausea complaints + their own "reduce
  animation" concession). Engine reason too: Kodi's dirty-region solver
  redraws the FULL viewport whenever anything animates - so transitions
  animate, then the screen goes fully static. NO ambient/looping motion, ever.
- **C4 ROWS FOR CURATED, GRID FOR THE LIBRARY.** Rows (fixedlist, focus
  pinned, content slides) for Continue Watching / Recently Added / Games /
  curated sets - carousel research says multi-row beats single-list for
  browsing satisfaction. The FULL library stays a dense labelled grid with
  C1 jumps - Apple's "large collections on a single screen" + NN/g's click
  math. We optimise retrieval of things we own, not discovery of things to
  sell.
- **C5 TITLES VISIBLE UNFOCUSED.** Art-only grids measurably fail (NN/g:
  users arrow through just to read names). Title + year on every unfocused
  card.
- **C6 METADATA IN PLACE.** Focus a tile -> synopsis/duration/rating appear
  on the spot (Netflix 2025's best idea; Google immersive-list). Never a
  press just to learn what something is.
- **C7 BACKGROUND FOLLOWS FOCUS, DEBOUNCED.** The one ambient behaviour every
  platform converged on (Xbox responsive art, PS5, Google scrim spec). Fanart
  crossfade ~300ms, debounced so fast scrolling doesn't strobe. Scrim under
  any text over art.
- **C8 NOTHING PROMOTED, EVER.** The universal complaint across Xbox/Google
  TV/webOS/Apple. No "Trending on TMDB" widgets above owned content. Hero
  spot, if any, shows only in-progress or owned items.
- **C9 NO AUTOPLAYING PREVIEWS.** Netflix publicly capitulated (2020); ACM
  DIS 2022 classifies them as a dark pattern. Static art only while browsing.
- **C10 READABILITY FLOOR.** Min text 28px at the 1080p design res (Fire TV,
  the only vendor-published floor; Copacetic goes down to 13px - audit
  Font.xml). 5-6 step type scale. Light-on-dark, desaturated, cool-leaning.
  Safe area 96px H / 54px V; focus scale-up must stay inside it.
- **C11 DENSITY.** 5-6 posters visible per row (Google's densest published
  card spec; Netflix's 2025 "10x slower" backlash was sparser rows; Big
  Picture's failure was handheld density on a TV).
- **C12 BACK IS SACRED.** One level up, position restored (focus memory),
  top level = home, never gated, never loops (Apple + Android TV-DB). The
  pad's B does this everywhere including our custom windows.
- **C13 CRASH-SAFE XML.** No conditional nested blocks inside cached include
  definitions (the Kodi 20 include-cache segfault we already hit); non-empty
  defaults on every parameterised condition (xbmc #22137); minimise boot-time
  Python widget calls (the Py3.12 teardown lottery, until Kodi 21).
- **C14 QUICK LADDER ONLY.** Ship the 25-100ms transition ladder as the only
  ladder (Copacetic's Quick_Transitions, made permanent). Console = instant.

## The design (per surface)

**Home (10000)** - v5 structure (Donnie, 7 Aug, after seeing and rejecting
both the hero variant and the crate/index recomposition): ONE PS5-style row
of square tiles, recency-mixed games + in-progress media, focused tile grows
and its art fills the screen behind a scrim (C7), metadata under the row
(C6). A LIBRARY TILE sits at the LEFT END of the row (grid glyph) - no tab
bar anywhere. Up reveals search/system; idle ~20s fades chrome to clean art
(a transition to a STATIC state, not a loop - C3).

**Library (10025)** - v5: the Library tile opens a Netflix-shaped page of
IMAGE rows: "Next up" (wide stills, per-tile progress lightbar in the item's
own colour), "Continue watching", "New" (posters), then "Everything" as the
full A-Z poster grid with L1/R1 letter jumps (C1). Focused item's facts in a
bottom strip, in place (C6). Every row is a widget fed by a smart playlist.
Approved interactive mockup: the artifact (stagelight-v5-ps5-netflix label).

**Playing (12005 + OSD)** - minimal OSD, transport on d-pad centre/left/right
(Android TV-PC), our pause-snap freeze-frames already integrate here. Seek
bar + time + title, nothing else on screen.

**Dialogs (tail windows)** - re-themed to the same tokens (type scale,
colours, focus ring), structurally untouched (C13; the keyboard/confirm/
shutdown paths must never break - they are the recovery paths).

**Switcher + Games row** - already ours (couch addons); restyle to the same
tokens so the whole thing reads as one system.

## Engine envelope (from Kodi source - what we build with)

Native + cheap: fixedlist rows w/ pinned focus, zoom-on-focus (first-class),
crossfades, slides, <shadowcolor> text shadows (unused by Copacetic - free
legibility win), rounded corners via diffuse masks + 9-slice (also unused -
our route to the soft console look), rows fed by videodb://, smart playlists,
plugin paths. Fonts re-rasterise at output res (sharp at 4K).

Costed: blur/colour-extraction only via the PIL helper (proven for
clearlogos; budget cache + first-view latency). Gradients/glows baked as
PNGs. Max 9 widget rows without writing new include blocks (no loops in
skin XML - fine, C4 wants few rows anyway).

Impossible: real-time blur/shaders, ambient animation (C3), runtime-generated
layouts. Note: 4K poster sharpness needs <imageres> raised in
advancedsettings.xml (default cache is 720px long-edge - visibly soft on a
poster-forward UI; measure disk cost first: Thumbnails/ currently 59MB).

## Phasing

1. **Tokens** - colours, type scale (28px floor), focus ring, quick ladder,
   safe-area constants. One include file the rest imports. (C10, C2, C14)
2. **Library grid** - the 10x-dominant window. Grid+captions, letter jump,
   in-place info, focus-follow background. (C1, C4-C7, C11)
3. **Home** - the PS5-skeleton row + ambient art + idle fade. (C6-C8)
4. **Playing OSD** - minimal transport. 
5. **Dialog re-theme sweep** - tokens only, no structure. (C13)
Each phase ships live (symlink + ReloadSkin), gets couch-tested with the pad,
and is committed separately. Screenshots per phase via Kodi's screenshot
action for the record.

## Kodi 21 prerequisites (park until the Flatpak move)

xbmc.gui bump to 5.17.0 (hard reject otherwise); add MyFavourites.xml
(DialogFavourites removed); verify SettingsScreenCalibration.xml against the
Omega rewrite; decide patch-forward vs re-fork from Copacetic 2.7.0 (upstream
keeps separate nexus/master branches). The more we replace Copacetic's XML
with our own, the smaller the rebase surface - an argument for the restyle
going deep rather than shallow.

## The identity: STAGELIGHT (decided 7 Aug, Donnie: no hero, "BOLD,
## over-engineer, cool as hell, not generic")

One idea carried all the way down: **the artwork lights the room.**

- **Dynamic accent.** The focused item's dominant colour IS the interface's
  accent, extracted live. Feasible today: script.copacetic.helper's art.py
  already extracts dominant colour + luminosity into window properties, and
  every Kodi texture takes colordiffuse from an infolabel. No fixed accent
  anywhere in the chrome; amber #E8A849 is the "pilot light" fallback when
  nothing has art.
- **The lightbar.** Focus signature everywhere (tiles, posters, tabs, seek
  bar): a thin bar in the live colour with a baked glow PNG, under the
  focused element. DualSense lightbar as the motif, pad-first console.
- **Type: Figtree** (OFL, shipped in skin fonts/), Donnie's pick 7 Aug after
  rejecting Chakra Petch ("2015") and the wide/loud candidates. PS5
  treatment: sentence case, medium weights (400/600), tight tracking, air.
  Quiet face for plots/captions is Figtree 400 (one family everywhere).
  28px floor holds (C10).
- **Ground:** near-black cool greys (#0A0C10 / #12151B / #8A93A0 / #ECEEF1)
  so the art is the only colour that matters.
- **Motion:** focus ~150ms, relight crossfade ~350ms debounced, then fully
  static (C3, C14).
- Mockup (approved direction): claude.ai/code/artifact/fb5b7dfe-b72c-42a1-a006-09fc2634398e

## Open choices (Donnie's, remaining)

- **O1 Wrap-around rows?** Ships behind a skin setting; Donnie feels both
  on the pad and picks.
- **O4 Sound?** Later, subtle, always with an off switch (Netflix's 2025
  mistake was no switch).
