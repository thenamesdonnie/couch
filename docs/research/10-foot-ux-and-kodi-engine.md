# Kodi console-UI fork: 10-foot UX rules + skin-engine constraints

(Research agent report, 7 Aug 2026, for the skin.couch console-UI redesign.
Companion: console-ui-patterns.md. Distilled into docs/specs/console-skin.md.)

**CORRECTION (session note):** the report below claims the fork's skin settings
"did not carry over". That inference is wrong - `addon_data/skin.couch/settings.xml`
was copied BEFORE first boot and `Skin.HasSetting(gridview_enabled)` was verified
true live under skin.couch. The ViewModes6.db finding, however, is real and was
acted on (rows migrated to skin='skin.couch').

**Research method note.** kodi.wiki, forum.kodi.tv and kodi.tv all returned HTTP 403
this session. Half B is therefore grounded in (a) the Kodi C++ source on GitHub,
(b) merged PR bodies on xbmc/xbmc, and (c) the installed skin and userdata on this
box. Apple's tvOS HIG is a JS SPA and could not be fetched; tvOS numbers are
second-hand and flagged as such.

---

## HALF A - 10-foot UX rules with concrete numbers

| # | Rule / number | Source | Confidence |
|---|---|---|---|
| A1 | **Overscan safe area = 5% margin.** At 960x540dp: 48dp left/right, 27dp top/bottom. On 1920x1080: "a minimum of 27 pixels from the top and bottom edges and a minimum of 48 pixels from the right and left edges". | Android TV, Building Layouts for TV - direct quote | Strong |
| A2 | Same page's newer sibling states an alternative 58dp sides / 28dp top-bottom. Google's own two pages disagree with each other. | Android TV, Layouts | Strong (that the disagreement exists) |
| A3 | **Safe zone = inner 90%.** "Avoid placing any of your app's UI elements within the outer 5% of any edge on the screen." Focus scale-up must not push a card out of the safe zone. | Amazon Fire TV, Design and UX Guidelines - direct quote | Strong |
| A4 | **Minimum body text = 14sp ~ 19px at 720p, 28px at 1080p.** The only hard, vendor-published minimum verified. | Amazon Fire TV - direct quote | Strong |
| A5 | "Text smaller than 22 pixels becomes unreadable from typical viewing distances." | Legacy Android TV Style for TV doc (current docs contain no numeric minimum at all) | Weak - legacy doc |
| A6 | Baseline TV text size 24px; type scale of 5-6 steps. | Smashing Magazine, Designing For TV (Sep 2025) | Weak - secondary/opinion |
| A7 | tvOS margins: 60pt top/bottom, 80pt left/right (1920x1080 at 1x => 5.5% vertical, 4.2% horizontal). | Smashing citing Apple HIG; could not verify against Apple directly | Medium |
| A8 | Grid: 12 columns, 52dp column width, 20dp gutter, 4dp vertical rhythm. | Android TV, Layouts | Strong |
| A9 | Card widths: 1-up 844dp, 2-up 412dp, 3-up 268dp, 4-up 196dp, 5-up 124dp. 5 is the densest published => treat **5-6 items per row** as the practical ceiling at 1080p. | Android TV, Layouts | Medium - the ceiling inference is the agent's |
| A10 | **Focus scale factors: 1.025x, 1.05x, 1.1x.** "The scaling values for different elements can vary based on their size." | Android TV, Focus system - direct quote | Strong |
| A11 | Focus glow / elevation: 2dp - 32dp. Tonal elevation surfaces +1 to +5. | Android TV, Focus system - direct quote | Strong |
| A12 | **No vendor publishes a focus-animation duration.** | - | Strong (as a negative) |
| A13 | D-pad: "moves focus to the nearest element in the corresponding direction." "Ensure a user can navigate to all focusable elements"; "If there isn't a straight path to get to a control, consider relocating it." | Android TV, Navigation on TV - direct quotes | Strong |
| A14 | **Axis semantics:** "Categories can be traversed on the vertical axis, and items within each category on the horizontal axis." | Android TV, Navigation on TV - direct quote | Strong |
| A15 | **Back must always terminate.** "Ensure that the back button isn't gated by confirmation screens or part of an infinite loop." First screen on launch == last screen before exit. | Android TV Navigation + TV app quality (TV-DB) - direct quotes | Strong |
| A16 | No dependence on a Menu button (TV-DM). Media transport must work from D-pad centre/left/right during playback (TV-PC). | Android TV app quality guidelines | Strong |
| A17 | Overscan compliance is testable: no text or functionality partially cut off by screen edges (TV-OV). | Android TV app quality guidelines | Strong |
| A18 | **Wrap-around: Fire TV says yes.** "1D list views wrap navigation when reaching list ends." | Amazon Fire TV guidelines - direct quote | Strong |
| A19 | **Minimise selections.** NN/g measured Google Fiber's tile browse at 245 clicks to view 500 movies vs 49 clicks for page-based browsing. | NN/g, Smart-TV Usability - measurement | Strong |
| A20 | **Grids of pure cover art fail.** AT&T's art-only movie grid "forc[ed] users to arrow through to see titles"; grid showing artwork + title + year tested better. Titles must be visible without focusing. | NN/g, Smart-TV Usability | Strong |
| A21 | Top-level menu should be "slim and occupy little screen space... so that users who accidentally expose the menu won't have their viewing experience interrupted". | NN/g, Smart-TV Usability | Strong |
| A22 | Search must be visible, not a hidden coloured button. Autocomplete + recent searches expected. | NN/g, Smart-TV Usability | Strong |
| A23 | Text entry on TV is ~4x the keystrokes of mobile ("hey there" = 9 keystrokes mobile, ~38 on a D-pad). | Smashing Magazine (2025) | Medium |
| A24 | **Light text on dark background.** "This style is easier to read on a TV." Avoid lightweight fonts and very narrow/broad strokes; anti-aliased sans-serif. | Android TV - direct quote | Strong |
| A25 | **Desaturate.** TV screens have higher contrast than computer screens; prefer cool colours over warm; less saturated than PC. | Amazon Fire TV - direct quotes | Strong |
| A26 | No TV vendor publishes a contrast ratio. Only numeric standard is WCAG 2.2: 4.5:1 body text, 3:1 large text, 3:1 non-text UI + focus indicators (SC 1.4.3, 1.4.11). | WCAG 2.2 (quoted from knowledge, flagged unverified this session) | Medium |
| A27 | Viewing distance assumption: 3m / 10ft. "limit the amount of text and reading"; "Complex screen layouts and controls are not ideal". | Android TV, Design for TV - direct quote | Strong |
| A28 | "People tend to focus their gaze on the center of the TV screen." | Search-surfaced summary; no primary source located | Weak |
| A29 | Density targets: 1080p = xhdpi = 960x540dp logical; author assets at 1080p. | Android TV / Fire TV | Strong |

### Where the guidelines disagree

1. **Safe-area size.** Android: 48/27dp (5%). Android's newer page: 58/28dp. Fire TV: outer 5%. Apple (second-hand): 80pt/60pt = 4.2%/4.2%-5.5%. No consensus; all share "at least 5%". **Resolution: 5% (96px H / 54px V at 1080p) as the hard floor; nothing but background art outside it.**
2. **Minimum text size.** Fire TV 28px @1080p; legacy Android 22px; community 24px; current Android docs no number. **Resolution: 28px floor (only vendor-published figure, most conservative).**
3. **Focus wrap-around.** Fire TV wraps; Android silent; tvOS famously does not wrap. **A product decision, not compliance. Consistency beats compliance.**
4. **Focus indication.** Android gives numbers but no durations; Apple's model is scale + parallax; Fire TV only "clearly indicated". WCAG 1.4.11's 3:1 is the only contrast number available for the focus ring.
5. **Grid vs rows.** NN/g: art-only grids are worse than labelled ones; click-count matters more than density. Android's grid guidance is purely geometric. They optimise different things.

**Honest gaps:** BBC GEL has no usable TV guidance publicly (web-only, 15-18px browser text - wrong for TV). Netflix's TV engineering posts unreachable (Medium redirect wall).

---

## HALF B - What the Kodi skin engine can actually do

Local ground truth: skin.copacetic 1.6.1 (xbmc.gui 5.16.0, 1920x1080, effectslowdown="0.7"), 170 XML files, 3.2MB XML + 6.7MB media/Textures.xbt. Kodi 20.5 Debian package.

### 1. Scale/zoom on focus, blur, rounded corners, gradients, drop shadows

From xbmc/guilib/VisibleEffect.h (CAnimEffect::EFFECT_TYPE) and VisibleEffect.cpp:

- **Effects: fade, fadediffuse, slide, rotate (z), rotatex, rotatey, zoom.** Complete set. No shader hooks.
- **Triggers: WindowOpen, WindowClose, Visible, Hidden, Focus, UnFocus, Conditional.**
- **Tweens: linear, quadratic, cubic, sine, back, circle, bounce, elastic. Easing: in, out, inout.** Default time 0ms.

**Zoom-on-focus is first-class and cheap.** Copacetic uses 59 zoom animations and 957 slides - but 1042 Conditional animations vs only 17 Focus animations. Copacetic's idiom is "drive layout from $EXP[] boolean state with time=0 conditional slides", not "animate on focus". A console UI wanting punchy focus scaling writes new Focus/UnFocus animations - less-trodden ground in this codebase.

**Not supported at all:** blur, rounded corners as a property, gradients as a primitive, box shadows on controls. No backdrop-filter, no clip path, no mask on arbitrary controls.

**Workarounds that are real and in-engine:**
- **diffuse="mask.png" on <texture>** multiplies the texture by a second texture - THE mechanism for rounded corners, vignettes, soft edges over dynamic artwork. **Copacetic uses zero diffuse masks today** (every diffuse= hit is actually colordiffuse=). Unexploited headroom.
- **border + infill="false"** = 9-slice with hollow centre - resizable rounded outline/frame from one PNG.
- **<shadowcolor> IS parsed** for any control with a CLabelInfo. Text drop shadows are free. Copacetic uses none.
- **Gradients/blurs must be baked into PNGs** (Textures.xbt or loose files under media/).
- **Blur/crop/recolour of DYNAMIC artwork requires the Python helper.** script.copacetic.helper's art.py uses PIL (ImageEditor.clearlogo_cropper/crop_image), caches to a folder with an XML lookup, extracts dominant colour + luminosity into window properties. Clearlogo crops capped 1600x620. The escape hatch for anything the GUI can't do - at the cost of a Python round-trip and cache management.

### 2. Horizontal rows, and building them dynamically

**Row mechanism: <control type="fixedlist"> with horizontal orientation** - focus stays at a fixed slot, content slides past (the Netflix/tvOS behaviour). Canonical: 16x9/Templates_Widgets.xml:29 (Widget_List), preloaditems=2, scrolltime 360ms sine-inout. Container inventory: list x15, fixedlist x5, panel x6, wraplist x2, grouplist x65, epggrid x1.

- **wraplist** = infinite wrap-around; Copacetic uses it only for the on-screen keyboard - available but a deliberate choice.
- **panel** = the 2-D grid (view 505). Full control-type list from GUIControlFactory.cpp: button, colorbutton, edit, epggrid, fadelabel, fixedlist, gamecontroller, gamecontrollerlist, gamewindow, group, grouplist, image, label, list, mover, multiimage, panel, progress, radiobutton, ranges, renderaddon, resize, rss, scrollbar, slider, sliderex, spincontrol, spincontrolex, textbox, togglebutton, videowindow, visualisation, wraplist.

**Dynamic content: yes, three ways, all in use here:**
1. **<content target="videos" sortby="..." limit="20">videodb://...</content>** - built-in CDirectoryProvider; accepts smart playlists (special://skin/extras/playlists/inprogress_movies.xsp). Auto-refresh on library change.
2. **Plugin paths** - plugin://script.copacetic.helper/?info=games etc. The Games row works this way.
3. **Skin-string indirection** - Widget1_Custom_Path...Widget9_Custom_Path from Skin.String, user picks each row's source at runtime. Home_Widgets is a **hard-coded stack of exactly 9 slots** gated on !Skin.HasSetting(WidgetN_Content_Disabled).

**The constraint that matters: rows are statically declared and conditionally hidden, not generated. You cannot loop in skin XML.** Nine rows = nine hand-written include blocks, control IDs (3201-3209), Custom_113N focus files, settings blocks. Copacetic hit this wall (Custom_1137/1138/1139 are stubs).

Note: <content browse="never"> is used in Templates_Widgets.xml but the browse attribute only exists from PR #23814 (Omega) - silently ignored on Kodi 20.

### 3. What is expensive / slow (Linux + X11)

- **Dirty-region solver default 3 = FILL_VIEWPORT_ON_CHANGE** (AdvancedSettings.cpp; GUIWindowManager renders a single full-viewport pass whenever dirtyRegions is non-empty). A static screen costs ~nothing; **one animating pixel anywhere = full-screen redraw that frame.** Continuous ambient motion converts the GUI from idle to full-res fill every frame, forever. The single biggest perf lever for the redesign: **animate on transition, then settle to static.**
- **effectslowdown="0.7"** multiplies every animation duration globally. Constants.xml defines two time ladders - Default_Transition_* (90/180/270/360...3600ms) and Quick_Transition_* (25/50/75/100 capped) - switched by Skin.HasSetting(Quick_Transitions). A console UI should probably ship only the fast ladder.
- **Artwork is downscaled on cache: imageres=720, fanartres=1080, jpeg quality 4.** Thumbnails capped at 720px long edge by default - a poster-forward UI at 4K upscales from a 720px cache, noticeably soft. Fix: <imageres> in advancedsettings.xml (none exists on this box); grows Thumbnails/ (currently 59MB) and Textures13.db.
- **Fonts: one 8-bit alpha atlas per (font file, size, style)**, padded to power-of-two, max texture 16384 on this GPU. Bold/light are synthesised unless real weight files shipped - Copacetic ships real Inter weights (4.1MB). 175 font entries across 3 fontsets at **17 distinct sizes: 13,17,20,21,22,25,27,29,30,33,34,35,37,40,50,55,60**. Every distinct size is another atlas.
- **4K crispness: fonts re-rasterise at output resolution** (ReloadTTFFonts on RENDERER_RESET; videoscreen.limitguisize=0 here). Text sharp at 4K; textures are not re-rasterised.
- **This box:** RX 9070 XT radeonsi Mesa 25.2.8, GL 4.6, VSYNC on. **videoscreen.fakefullscreen=true AND xfwm4 compositing on** - every Kodi frame goes through the compositor: extra full-screen copy + latency floor on top of vsync. For focus-move responsiveness this is a real cost. (Project history: never toggle xfwm4 compositing under a live game. Testing true fullscreen for Kodi is a separate, safer experiment.)
- **Skin-authoring cost:** $EXP/$VAR re-evaluated as conditions change. Colors.xml is 86KB; Components_Viewtypes.xml 86KB of nested conditional includes; 1042 Conditional animations each carry a condition. Deep conditional nesting inside cached includes is both slow and the known Kodi 20 crash vector.

### 4. What breaks between Kodi 20 and Kodi 21

**A hard break.** Nexus xbmc.gui 5.16.0 (backwards-compat abi 5.15.0); **Omega xbmc.gui 5.17.0 with backwards-compat abi 5.17.0 - i.e. none.** A skin importing 5.16.0 is rejected by Kodi 21. skin.couch currently declares 5.16.0.

From PR #23927 / #23926 (the ABI-break rationale):
1. DialogColorPicker.xml required (local skin HAS it).
2. SettingsScreenCalibration.xml rewrite (#21364) - local skin has the file; content not verified against new schema.
3. **DialogFavourites.xml REMOVED in Omega (#23862); MyFavourites.xml required (from #22001). Local skin has DialogFavourites.xml and does NOT have MyFavourites.xml - confirmed concrete break.**
4. DialogSelect.xml savestate-manager changes (#20913) - relevant to Games.

Other Omega skinner-visible changes: #22735 (complex expressions on fallback label), #22841 (theme change also switches fontset), #22993 (fontsets in /fonts dir xmls), #23163 (disabled slider texture), #23814 (browse attr), #23682 ("more..." item), #23850 (video width/height infolabels), #22234 ($PARAM-with-comments fix - relevant to a heavily-commented fork), #24146 (DialogVideoManager.xml), #24147 (games button combos), #22107 (continue watching).

**The elephant:** upstream Copacetic master (Omega) is v2.7.0 requiring 5.17.0; our base is 1.6.1. The Kodi 21 move is either (a) bump 1.6.1 to 5.17.0 and hand-fix Favourites/calibration, or (b) re-fork from 2.7.0 and re-apply local changes. Upstream keeps separate nexus/master branches.

### 5. Per-skin settings and view modes across a fork under a new addon id

| Store | Location | Keyed by | Survives a fork? |
|---|---|---|---|
| Skin settings (Skin.SetBool/SetString) | addon_data/<skin.id>/settings.xml | addon id | Plain XML; cp is a valid migration (WAS copied before first boot - carried). |
| **View modes (which view each path uses)** | Database/ViewModes6.db, table view (idView, window, path, viewMode, sortMethod, sortOrder, sortAttributes, skin) | addon id | **No - resets. Zero rows for skin.couch on first check.** Migrate with INSERT...SELECT swapping the skin column, Kodi stopped. |
| Skinshortcuts menus | addon_data/script.skinshortcuts/ | Mixed: *.DATA.xml not skin-keyed; <skinid>.hash/.properties are | Menu content carries; per-skin properties/hash regenerate (or copy). |

guisettings.xml holds lookandfeel.skin/skintheme/skincolors/**skinzoom** - the last is Kodi's built-in GUI overscan compensation (currently 0), a global escape hatch if the TV overscans.

### 6. Known landmines

a) **The include-cache segfault** - already hit and patched on this box (see homelab-kodi-crashes memory). General lesson for the redesign: **do not put conditional <nested/>/Object_Include blocks inside cached include definitions.** Related upstream: xbmc/xbmc#22137 (empty condition="" on an include crashes - trivially triggered by <include condition="$PARAM[x]"> with an empty default; fixed by #22146 but guard every parameterised condition with a non-empty default).

b) **Bad XML Kodi tolerates:** 16x9/Includes.xml ends with `<include file="Variables_Textures_Icons.xml" />s` - stray `s`. Harmless today, fatal after a parser change. Clean in the fork.

c) **Python teardown segfault at startup** (Kodi 20 + Py3.12, wont-fix #24440): ~1/3-1/2 of boots crash once; watchdog nets it. One global parked-invoker slot. **A home screen firing many widget/helper Python calls at boot makes this worse.** Real fix is Kodi 21.

d) **Font floor:** Copacetic's smallest sizes 13/17/20/21/22px at 1080p are all below the Fire TV 28px floor. Audit Font.xml and lift.

e) **Texture caching:** skin art in media/Textures.xbt (6.7MB) - repack after edits, or ship loose files under media/ (Kodi accepts; far easier during development).

f) **Skin <res> fixed at 1920x1080.** Author in that space; matrix-scaled to output. Textures not re-rasterised; fonts are.

---

## Design envelope - what this console UI can safely promise

**Cheap and native:** fixedlist rows with pinned focus slot (360ms sine-inout stock, ~100ms quick ladder); zoom-on-focus 1.05-1.1x with sine/back tweens; crossfades, slide-in panels, conditional layout, rotate; text drop shadows via <shadowcolor> (unused today, free legibility win); rounded corners/soft frames/vignettes via diffuse masks + 9-slice (unexploited, the correct route); crisp text at 4K; rows from library queries/smart playlists/plugin paths; full D-pad reachability + Back-always-terminates via <onleft>/<onright>/<onup>/<ondown> discipline; wrap-around rows if wanted (keyboard proves it).

**At a cost:** blurred backdrops, colour-extracted accents, cropped logos - only via the PIL helper (Python round-trip, disk cache, XML lookup; proven for clearlogos; budget cache invalidation and first-view latency). Gradients/glows/glass - bake as PNGs; static, cannot respond to artwork colour without the helper. More than 9 rows - every extra row is hand-written; no loop.

**Must not promise:** any continuously-running ambient animation (dirty-region solver = full-viewport redraw forever, through a compositor); real-time blur/shader effects; arbitrary clipping/masking; runtime-generated layouts; sub-frame focus latency (fakefullscreen + compositing + vsync sets a floor - measure true-fullscreen as a separate experiment before promising "instant").

**Hard prerequisites before the Kodi 21 move:**
1. Bump skin.couch to xbmc.gui 5.17.0 (will not load otherwise).
2. Add MyFavourites.xml (DialogFavourites.xml removed in Omega).
3. Verify SettingsScreenCalibration.xml against the #21364 rewrite.
4. Decide: patch 1.6.1 forward vs re-fork from Copacetic 2.7.0.
5. Re-apply the include-cache workaround if rebasing.

**Design constants fixed from Half A:**
- Safe area 96px horizontal / 54px vertical at 1920x1080 design res (5%, union of all vendors). Nothing but background art outside it; focus scale-up must stay inside.
- Minimum text 28px at design res; audit Copacetic's 13-22px entries.
- Max 5-6 items visible per row.
- Focus scale 1.05-1.1x plus a second cue (border or inversion); WCAG 3:1 for the focus ring.
- Titles visible on unfocused cards (NN/g's measured failure).
- Light-on-dark, desaturated, cool-leaning palette.
- Wrap-around: pick one behaviour and apply it everywhere.
