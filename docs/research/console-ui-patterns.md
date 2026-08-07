# TV / Console UI Research: What the Best 10-Foot UIs Do Well, and What Users Demonstrably Hate

(Research agent report, 7 Aug 2026, for the skin.couch console-UI redesign.
Companion: 10-foot-ux-and-kodi-engine.md. Distilled into docs/specs/console-skin.md.)

Scope note on evidence quality up front. Vendor design docs (Apple HIG, Google Android TV, Xbox Wire, PlayStation Blog, Netflix newsroom) are primary and reliable for *stated intent*. User-dislike evidence is mostly press reporting plus vendor forums, which is self-selected. Where a vendor **changed or reverted** something, that is the strongest signal available and I have flagged it. Two areas have genuinely thin evidence and I say so rather than inventing consensus: **hero banners** and **TV UI sound design**.

---

## 1. PlayStation 5 system UI

### Does well
- **Structure.** A single horizontal row of large game tiles occupying roughly the top third, with the selected game's key art filling the entire background. Media apps live in a separate tab so they never pollute the games row. EGM's UX review singles this separation out as a genuine improvement over PS4.
- **Overlay-not-a-mode.** The Control Center is invoked with the PS button and composites *over* the running game rather than suspending to a dashboard. EGM: it "offers quick access to what you need without having to drop back to the main interface."
- **Context-sensitive cards.** Activities cards are generated per game and per progress state (percentage complete, estimated time left, deep-link straight into a level). Sony's stated design goal, per SVP Hideaki Nishino at the October 2020 reveal, was that "your play time is valuable" and getting the player where they need to go quickly.
- **Ambient background that earns its keep.** Background art is derived from the focused game, not from a user-chosen wallpaper. Recent additions (Nov 2025 beta, per ScreenRant) add **Showcase Mode**, which fades the widgets away after as little as 15 seconds of idle to reveal the background cleanly, plus a Slideshow mode.

### Disliked, with receipts
- **Home row capacity cut from 15 to 8** and moved into a corner (EGM, Laptop Mag). Laptop Mag: the dashboard shows only the last eight things you touched, so anything else means a trip to the Library.
- **No folders.** PS3 had them, PS4 had them, PS5 shipped without them and still lacks them. A ResetEra thread titled "3 years in and we still don't have proper folders for the PS5 UI" is representative; Push Square's comment threads on the April 2026 home refresh were still demanding them.
- **No themes at launch**, after PS4's dynamic themes were popular.
- **Redundant information hierarchy.** A designer teardown (Brent Say, Oct 2020) counts "three distinct components in this state that are communicating the same information" on the home screen, plus inconsistent corner-radius treatment between sections.
- **Mental split between two surfaces.** EGM's sharpest structural criticism: users "constantly switch back and forth" between Home and Control Center, which are two separate functional worlds with overlapping duties.
- **Navigation depth for system functions.** Settings, trophies, profiles and power all require scrolling far right or multiple menu steps (Laptop Mag).

### Reverted / restored (strong signals)
- **Themes came back, five years late.** PlayStation Blog, 23 April 2025: the "Appearance" feature restores PS1, PS2, PS3 and PS4 looks. Sony's own framing: "Due to the overwhelmingly positive response from our community, we're happy to bring back the look and feel of the four console designs." Animated/dynamic themes returned separately.
- **Home refresh, April 2026.** Push Square: the games row was widened to the full screen and now shows *only* PS5/PS4 games; PS Plus, PS Store, Library and Media were demoted to a secondary menu reachable with L1/R1. Direction of travel is unambiguous: give the primary row back to games. Reception was mixed, with the loudest replies still asking for folders.
- **Not reverted:** folders. Five-plus years of sustained complaint with no response is itself informative about how Sony weights power-user organisation.

---

## 2. Netflix TV app

### Does well
- **Invented the shelf.** Horizontally scrolling themed rows in a vertical stack is the pattern every other TV UI now copies.
- **Persistent top navigation.** Netflix's own May 2025 announcement moved Search and My List out of the left sidebar to a permanently visible top bar (Search, Shows, Movies, Games, My Netflix).
- **Metadata on the focused tile, in place.** Per Netflix's newsroom post, pausing on a title surfaces genre, synopsis, length and rating plus badges ("Emmy Award Winner", "#1 in TV Shows") without a navigation step. This is the single most transferable idea in the redesign.

### Disliked, with receipts
- **Autoplaying previews.** The clearest documented capitulation in this entire report. After sustained complaints across Twitter, YouTube and Reddit, Netflix tweeted in February 2020: "We've heard the feedback loud and clear" and shipped an account-level toggle, "Autoplay previews while browsing on all devices." Covered contemporaneously by Variety, Forbes, TechRadar and What Hi-Fi.
- **The 2025 TV redesign.** Documented complaints (TechRadar, The Hollywood Reporter, TV Guide, What's on Netflix):
  - Fewer titles per row (down from around seven posters), so materially more scrolling for the same content. One user quote via What's on Netflix: "Scrolling through titles is 10x slower."
  - "New & Popular" and "Categories" tabs removed.
  - Home and My Netflix became near-duplicates of each other.
  - Motion complaints including a reported case of nausea.
  - Navigation sound effects with no in-app off switch, which reportedly override the tvOS system menu-sound setting.

### Reverted / conceded
- Autoplay previews toggle (2020), as above.
- **"Reduce animation effects when navigating on TV"**, a per-profile account setting added in response to the 2025 animation complaints (What's on Netflix). Note it only *reduces*, does not disable, and is not exposed on all TV devices.

### Prominent contradiction (flagged)
Roger Dooley in Forbes (June 2025) reports that Netflix's year-long global beta showed users **preferred** the new design, and Netflix's Chief Product Officer publicly said members "prefer the new experience." Dooley attributes the backlash to loss aversion, status-quo bias and vocal-minority sampling. **However**, Dooley explicitly notes that Netflix published **no metrics, percentages or sample sizes**. So both sides are weak evidence: an unverifiable vendor A/B claim versus self-selected complaints.

What survives the contradiction is the one mechanical complaint that is independently corroborated: larger tiles mean fewer items per screen, which means more D-pad presses per item found. That is a measurable interaction cost, not a taste preference, and it matches Nielsen Norman Group's smart-TV finding directly (see cross-cutting).

---

## 3. Apple TV (tvOS)

(Apple's HIG pages are JavaScript-rendered and did not fetch. Sourced via Microsoft's archived Xamarin tvOS focus documentation, which mirrors the HIG text nearly verbatim, plus a Black Pixel HIG summary.)

### Does well (the best-specified focus model in the industry)
- **No cursor, ever.** "Never display a cursor. Users expect to navigate your app's UI using Focus."
- **Focus indicated on multiple channels simultaneously:** the focused item grows slightly, is elevated with a shadow, sways in real time in response to small circular gestures (parallax via 2 to 5 layered images), and gains an illuminated sheen. After a period of inactivity, unfocused content dims and the focused item grows further.
- **"Ensure that the Focused Item is Obvious."** For custom controls Apple names item size or shadow explicitly.
- **"Design UI Elements to Look Good Either Focused or Unfocused"**, and supply larger assets so the focused state is not a blurry upscale.
- **"Represent Focus Changes Fluidly"** by animating between states "to keep transitions from being jarring."
- **Back behavior is a single rule.** "Typically Avoid Displaying a Back Button." The Menu button goes up one level, and at the app's top level it exits to the system Home screen. The only sanctioned exception is purchase or destructive screens, which get an explicit Cancel.
- **Focus Guides.** The focus engine only handles up/down/left/right on a grid, so any control not grid-aligned with its neighbours becomes *unreachable*. Apple provides `UIFocusGuide` to bridge diagonal gaps.
- **Focus memory.** `RemembersLastFocusedIndexPath` restores focus to the last item when a collection loses and regains focus.
- **Typography split point:** San Francisco UI Text at 39pt and below, San Francisco Display at 40pt and above.
- **Apple's own anti-ad rule:** "Don't use top shelf images for advertisements."

### Disliked, with receipts
- **Apple broke its own rule.** TidBITS (Jan 2020, "Why Is the Apple TV Constantly Advertising at Us?") documents the Top Shelf shifting from showing *your* Up Next queue to autoplaying iTunes Store trailers **with audio**, on by default.
- **tvOS 16.2 "Watch Now" redesign** demoted Up Next in favour of a large featured autoplaying section. Complaint threads on MacRumors Forums and Apple's own Support Communities are numerous.
- **Ongoing Top Shelf bugs into tvOS 18**, where Up Next / Still Frame settings are ignored and only the TV logo renders. Apple support acknowledged a known issue.

### Conceded
- Apple ships an off switch: Up Next Display set to **Still Frame** rather than Video (MacRumors). Two of the three biggest TV platforms therefore ship an autoplay-preview kill switch.

### Internal contradiction worth noting
Apple's HIG says content-forward, no cursor, no ads in Top Shelf. Apple's own TV app does the opposite. **Copy the guideline, not the product.**

---

## 4. Steam Big Picture (2022 redesign)

**Evidence quality warning.** Reputable press coverage of the 2022 redesign is largely announcement-flavoured (PC Gamer, GamingOnLinux, Windows Central). The substantive criticism lives on Valve's own Steam Client Beta forums and GitHub. That is primary user feedback but self-selected.

### Does well
- **Overlay model.** The guide button raises a system menu (Recent, Store, Library) plus a quick access menu (notifications, friends, quick settings). PC Gamer describes it as sleeker than the old version's left-edge tabs. Structurally the same idea as PS5's Control Center.
- **Controller-first and boots straight into it.** The Steam Machine boots directly to Gaming Mode.

### Disliked, with receipts (Steam Client Beta forum thread "OLD BIG PICTURE MODE BETTER!", ~15 concurring comments)
- **It is a 1:1 port of an 800p handheld UI onto 1440p and 4K TVs.** Oversized icons showing a maximum of three rows *regardless of screen resolution*. The most instructive single finding for our project: handheld density scaled to TV size is the worst of both worlds. Simultaneously too big (few items visible) and not readable-by-design (elements not sized for distance, just scaled).
- **Navigation hierarchy hard to parse**; users report losing track of how they got where they are.
- **Features removed:** music player, web browser, Steam Controller Bluetooth firmware updates, the desktop Big Picture overlay option.
- **Controller configurator buried in sub-menus** compared with the old flow.
- **Input reliability:** controller stops working after exiting a game, requiring a mouse click; parts of the on-screen keyboard unreachable with a Steam Controller.
- **Forced onto beta users while still alpha-quality.**
- 2026 Steam Machine reviews still flag inconsistent control widget types and scaling confusion at boot (weaker sourcing, flagged).

### Reverted?
**No, and that is itself the data point.** Valve removed the `-oldbigpicture` launch parameter and the old UI's underlying tech was removed from the client. GitHub issue ValveSoftware/steam-for-linux#9589 requesting its return has no Valve response. Users reported migrating to Playnite instead. Valve's strategy is one UI across handheld, desktop and TV, and TV users pay the density tax for it.

---

## 5. Xbox dashboard

### Does well: the single best-documented listen-and-revert in this review
- **Microsoft paused and pulled a shipped experiment.** Per Microsoft's own Xbox Wire post (1 May 2023): feedback was that the top of Home felt "crowded and didn't leave enough space for you to enjoy your background." Microsoft removed the UI from testers, paused the experiment, generated "hundreds of options", ran prototype testing and research-lab user studies, then shipped a rework.
- **What the rework actually did:** reduced tile sizes, moved tiles to the bottom of the screen to expose the background, added a quick-access menu at the top (library, store, Game Pass, search, settings), and added **responsive game art** that swaps the background as you hover each tile.
- Kotaku's review praised the balance and specifically the promotion of Quick Resume out of a submenu.

### Disliked, with receipts
- **Ads, persistently and universally.** Kotaku: one home slot reserved for Game Pass promotion, a dedicated tile selling paid content and deals, plus multiple rows of Game Pass recommendations below the pinned icons. Community shorthand was "an explosion of ads."
- **Irrelevant ads.** Notebookcheck and Pure Xbox document a Call of Duty: Mobile advert appearing on Series consoles, for a game the console cannot run.
- **Full-screen startup ads** (Modern Warfare 3), covered by TechRadar.
- **Still live in 2026.** Pure Xbox, May 2026: "Dear Asha..." open letter asking the new CEO to remove irrelevant dashboard ads.

### Reverted / conceded
- The crowded-Home experiment: **yes, genuinely reverted and reworked** before general release.
- The ads: **no.** In August 2025 Microsoft added a toggle between *standard* and *personalised* dashboard ads (Pure Xbox). The choice on offer is which ads, not whether.
- 2025's **Full Screen Experience** for Windows handhelds (Xbox Wire, 21 Nov 2025) is explicitly pitched as "a clean, distraction-free interface for controller-first gaming", which reads as an admission about the main dashboard.

---

## 6. LG webOS (brief)

- **The original pattern was excellent and minimal.** webOS 1 through 5 used a slim bottom launcher bar overlaid on live content: maximum content, minimum chrome. Closest to what NN/g recommends.
- **webOS 6.0 (2021) replaced it with a full-screen home**, marketed at CES 2021 as "content-first" (Digital Trends).
- **The ad banner arrived with webOS 22 above the fold and persists through webOS 23, 24 and 25 with no toggle.** Turning off "AI Recommendation" does not remove the ad slot. Screensaver ads pushed to OLEDs back to 2020 models (Tom's Guide). Mid-tier sourcing, flagged.
- **webOS 25 concessions:** hide preinstalled apps; reorder/pin app cards to the front of the launcher row.

## 7. Google TV (brief)

- **Worst offender for chrome-over-content.** The most prominent area of the home screen is a promotional banner carrying recommendations, rental promos and outright ads, rather than the user's apps.
- **Google publicly doubted itself.** November 2024: Google surveyed users asking whether the volume of home-screen ads is "acceptable" (9to5Google, TechRadar).
- **Google shipped an escape hatch: "Apps-only mode"**, a plain app launcher with the recommendation surface removed. A real partial revert. **But it is being eroded**: HDTVTest reports ads appearing inside apps-only mode.
- **Google's published design system is the best free source of hard numbers:**
  - Design canvas 960 x 540 dp at mdpi, 16:9 fixed.
  - Safe margins **5%**: 48dp left/right, 24 to 27dp top/bottom.
  - 12-column grid, 52dp columns, 20dp gutters, 58dp side padding, 4dp row spacing.
  - Focus **scale**: 1.025x, 1.05x, 1.1x depending on element size (smaller elements get the larger factor).
  - Focus **glow/elevation**: 2dp to 32dp; cards typically 2dp default, 8dp focused, 16dp pressed.
  - Focus **outline**: 2 to 4px width with 2 to 4px inset, for buttons, chips and text-based elements.
  - Explicit don'ts: **never rely on colour alone**; do not exceed 1.1x scale (layout shift); do not apply glow to small elements.
  - **Immersive list** component: focused card scales 1.1x, background image is 16:9 with a "cinematic scrim", subject composed to the top-right so the content block does not cover it, and the row's height *increases* on focus to reveal title and description in place.

---

## Cross-cutting findings

### A. Rows vs grids: consensus exists but it is constraint-driven, and it has a real counter-argument

**For rows:** Smashing Magazine's two-part "Designing For TV" (Aug and Sep 2025) makes the cleanest argument. TV interaction reduces to six buttons (four directions, OK, Back). Shelves exist because vertical movement switches content *group* and horizontal switches *item within group*, which is the only two-axis scheme a D-pad supports efficiently. Quote: "Every step on TV costs an action, so we might as well optimize movement."

**Measured support:** recommender-systems research (Felicioni et al. 2021; "The Magic of Carousels", ACM Hypertext 2022) finds multi-list carousel interfaces are rated **more favourably than single-list interfaces on perceived diversity and choice satisfaction**. The same literature notes the cost: carousels require deliberate navigation; users not in an exploratory mood find the extra steps cumbersome.

**Against rows:** Apple's own HIG says **"Show Large Collections on a Single Screen, Instead of Many"**. And Nielsen Norman Group's smart-TV study gives the hardest number in this report: browsing 500 movies took **245 clicks**, reduced to **49** with page-based navigation. Pure sequential row browsing does not scale.

**Resolution for a personal library:** rows are correct for curated, small, editorially-motivated sets (Continue Watching, Recently Added, In Progress). A dense grid with paging or letter-jump is correct for the complete library, where the user usually already knows what they want. Copying Netflix wholesale is the wrong move, because Netflix optimises for discovery of things you do not own; we optimise for retrieval of things we do.

### B. Hero banners: tolerated, not loved, and the evidence is genuinely thin

**Honest finding: no rigorous study on hero banners in TV UIs found.** What exists is design-blog opinion. Smashing treats the "spotlight" as a legitimate structural device to break the monotony of uniform shelves - a composition argument, not a usability one.

What *is* well documented: the hero slot is exactly where every platform puts the thing users complain about (Google TV's promo banner, Xbox's Game Pass slot, Apple's Top Shelf trailers, LG's webOS 22 ad banner). The correlation is near-perfect.

The defensible reading: **a hero is fine when it shows content you already own or are already watching, and toxic when it shows content you do not have.**

### C. Autoplaying previews: the most decisively negative finding in this review

- **Two of three major platforms publicly capitulated** (Netflix Feb 2020 toggle; Apple Still Frame setting).
- **Peer-reviewed classification as a dark pattern.** "Are You Still Watching?" (ACM DIS 2022; 180-participant survey, 22-participant diary study) classifies instant-start video previews and infinitely scrolling recommendations as dark patterns. Participants described autopreview as "annoying or unethical".
- **Measured behavioural effect, with caveat.** A 2024 field experiment (76 US Netflix users) found disabling autoplay cut average daily watching by 21 minutes (p=0.003). **Caveat: measures autoplay-next-episode, not browse previews.** Establishes these features change behaviour rather than merely irritate. Post-study preference genuinely split (~50% re-enable, ~33% keep off).
- **Conclusion for us:** autoplay previews are engagement-optimised, not satisfaction-optimised. A personal media box has no engagement KPI, so there is no reason to autoplay anything while browsing. If built at all, default off.

### D. Density is the recurring failure mode, in both directions

Every documented backlash in this report is, at root, a density mistake:
- Netflix 2025: **too sparse.** Fewer titles per row, "10x slower" scrolling.
- Steam Big Picture: **wrong density model.** Handheld pixel density scaled up, three rows max at any resolution.
- Xbox 2022 pre-revert: **too crowded**, no room for backgrounds.
- PS5: **too shallow**, 8 slots instead of 15, no folders.

NN/g's framing is the right metric: count the button presses to reach a target, not the pixels. Both "too big" and "too small" fail on the same axis.

### E. Ads and promoted content: the only complaint universal to every platform reviewed except Steam

Every vendor's response has been a partial concession rather than removal. This is a free win for a self-hosted skin, and it warns against the Kodi-skin habit of putting "Trending on TMDB" or "Recommended" widgets above the user's own library.

### F. Sound design: no published treatment worth calling research

Honest finding. The only substantive writing found is an essay (Vale.Rocks, "The Death of Character in Game Console Interfaces") arguing persuasively but without data that older consoles used per-section ambient music and audio-tactile feedback to make the UI a destination, and that modern ones are interchangeable. Hard corroboration is commercial only: Sony restored PS1-PS4 themes with their sounds in April 2025 citing "overwhelmingly positive response". Netflix's 2025 navigation sounds with no off switch produced complaints.

---

## The 10 most actionable, evidence-backed principles for our skin

1. **Indicate focus on at least three channels at once, and never on colour alone.** Google: scale 1.025x/1.05x/1.1x (larger factor for smaller elements), glow/elevation 2-32dp, outline 2-4px; "rely on colour alone" is an explicit don't. Apple: the focused item must be "obvious" (size + shadow). For Kodi: scale the focused tile ~1.08x, add a bright outline, shift the tile background. Cap scale at 1.1x (layout shift).

2. **Budget D-pad presses, not pixels, and add a jump mechanism to any long list.** NN/g measured 245 presses to browse 500 movies, cut to 49 with page-based navigation. Smashing: "Every step on TV costs an action." Bind shoulder buttons to page/letter jump on anything over ~30 items.

3. **Rows for curated sets, a dense grid for the full library.** Carousel research (ACM Hypertext 2022) finds multi-list beats single-list on perceived diversity and satisfaction; Apple's HIG counters "Show Large Collections on a Single Screen"; Netflix's 2025 backlash was overwhelmingly scroll distance. Do not make someone traverse rows to reach a film they already own.

4. **Never autoplay video on a browse screen.** Netflix publicly reversed (Feb 2020); Apple ships Still Frame; ACM DIS 2022 classifies instant-start previews as a dark pattern.

5. **Put metadata on the focused item, in place, not one press away.** Netflix (May 2025) surfaces genre, synopsis, length, rating on the focused tile. Google's immersive list increases row height on focus to reveal title and description over a cinematic scrim. One press should never be required just to learn what something is.

6. **Let the background art follow focus, with a debounce.** The one ambient behaviour every platform independently converged on (Xbox responsive game art, PS5 per-game backgrounds, Google immersive list: 16:9 art, subject top-right, scrim for legibility). Debounce so it does not strobe during fast scrolling.

7. **One back button, no on-screen Back, and it restores your previous position.** Apple: "Typically Avoid Displaying a Back Button"; Menu goes up one level; top level exits. Focus memory (RemembersLastFocusedIndexPath) so returning from a detail page lands on item 27, not item 1.

8. **Animate the focus indicator, not the layout.** Apple: "Represent Focus Changes Fluidly". Netflix's 2025 zoom transitions generated complaints (including reported nausea) and a "Reduce animation effects" setting. Keep focus transitions 100-200ms and never reflow the page underneath.

9. **Hard typographic and safe-area floor: ~24px base at 1080p, a 5-6 step scale, 5% margins.** Smashing: start at 24px (vs 16-18 for web), keep to a 5-6 size scale. Google: 5% margins (48dp horizontal, 24-27dp vertical on 960x540dp canvas).

10. **Give the home screen to content the user actually has, and let the skin have a point of view.** Promoted content is the universal complaint (Xbox Game Pass slot, Google TV promo banner, LG ad banner, Apple Top Shelf trailers). Sony's April 2026 refresh moved Store/PS Plus off the primary row. Sony's theme restoration is the only commercial evidence that a distinctive, characterful UI is wanted. Treat "Trending on TMDB" widgets as the Kodi equivalent of a Game Pass ad slot.

---

## Sources

- Nielsen Norman Group, Smart-TV Usability: https://www.nngroup.com/articles/smart-tv-usability/
- Smashing Magazine, Designing For TV Part 1: https://www.smashingmagazine.com/2025/08/designing-tv-evergreen-pattern-shapes-tv-experiences/
- Smashing Magazine, Designing For TV Part 2: https://www.smashingmagazine.com/2025/09/designing-tv-principles-patterns-practical-guidance/
- Microsoft Learn (archived Xamarin), tvOS Navigation and Focus: https://learn.microsoft.com/en-us/previous-versions/xamarin/ios/tvos/app-fundamentals/navigation-focus
- BPXL Craft, Apple TV HIG summary: https://medium.com/bpxl-craft/getting-started-with-apple-tv-human-interface-guidelines-4d991737ddec
- Android Developers, TV Layouts: https://developer.android.com/design/ui/tv/guides/styles/layouts
- Android Developers, TV Focus System: https://developer.android.com/design/ui/tv/guides/styles/focus-system
- Android Developers, Immersive List: https://developer.android.com/design/ui/tv/guides/components/immersive-list
- Xbox Wire, Your Feedback Shapes the New Home Experience (May 2023): https://news.xbox.com/en-us/2023/05/01/xbox-insiders-your-feedback-shapes-the-new-home-experience/
- Xbox Wire, Full Screen Experience (Nov 2025): https://news.xbox.com/en-us/2025/11/21/the-full-screen-experience-is-available-for-xbox-insiders-starting-today/
- Kotaku, New Xbox Dashboard: https://kotaku.com/xbox-series-x-s-dashboard-update-game-pass-ui-1850679127
- Pure Xbox, Personalised Ads: https://www.purexbox.com/news/2025/08/youll-soon-be-able-to-see-personalised-ads-on-your-xbox-dashboard
- PlayStation Blog, classic console UI customizations (Apr 2025): https://blog.playstation.com/2025/04/23/new-ps5-system-software-update-features-audio-focus-and-the-return-of-the-classic-console-ui-customizations/
- Push Square, PS5 Home Page Refresh (Apr 2026): https://www.pushsquare.com/news/2026/04/ps5-home-page-refresh-live-now-for-some-users
- EGM, PS5 user experience review: https://egmnow.com/the-good-and-bad-of-the-playstation-5s-user-experience/
- Laptop Mag, PS5 UX: https://www.laptopmag.com/features/ps5-user-experience
- ScreenRant, PS5 Showcase Mode: https://screenrant.com/playstation-5-system-update-new-features/
- Brent Say, PS5 UI observations: https://old.whatbrentsay.com/2020/10/21/playstation-5-ui-reveal-observations-from-a-designer/
- About Netflix, New TV Experience (May 2025): http://about.netflix.com/en/news/unveiling-our-innovative-new-tv-experience
- Variety, Netflix autoplay toggle (2020): https://variety.com/2020/digital/news/netflix-autoplay-turn-off-1203495489
- Forbes (Dooley), Netflix redesign psychology: https://www.forbes.com/sites/rogerdooley/2025/06/16/netflixs-homepage-redesign-shows-the-psychology-behind-user-backlash/
- What's on Netflix, UI criticism: https://www.whats-on-netflix.com/news/netflixs-new-ui-update-sparks-backlash-as-global-rollout-continues/
- What's on Netflix, animations off switch: https://www.whats-on-netflix.com/news/netflix-introduces-new-animations-in-tv-app-how-to-turn-them-off/
- Hollywood Reporter, Netflix redesign dislike: https://www.hollywoodreporter.com/tv/tv-news/netflix-new-layout-homepage-why-changed-1236263688/
- TidBITS, Apple TV advertising: https://tidbits.com/2020/01/16/why-is-the-apple-tv-constantly-advertising-at-us/
- MacRumors, disable autoplay previews: https://www.macrumors.com/how-to/disable-autoplay-video-apple-tv/
- MacRumors Forums, tvOS 16.2 complaints: https://forums.macrumors.com/threads/apple-tv-users-complain-about-tvos-16-2-watch-now-redesign.2376428/
- Steam Client Beta forum, "OLD BIG PICTURE MODE BETTER!": https://steamcommunity.com/groups/SteamClientBeta/discussions/3/3775742015030843946/
- ValveSoftware/steam-for-linux#9589: https://github.com/ValveSoftware/steam-for-linux/issues/9589
- 9to5Google, Google TV ads survey: https://9to5google.com/2024/11/18/google-tv-homescreen-ads-survey/
- HDTVTest, ads in apps-only mode: https://www.hdtvtest.co.uk/news/google-tv-starts-pushing-ads-in-apps-only-mode
- Digital Trends, webOS 6.0: https://www.digitaltrends.com/home-theater/lg-webos-6-0-new-magic-remote-ces-2021/
- ACM DIS 2022, "Are You Still Watching?": https://dl.acm.org/doi/abs/10.1145/3532106.3533562
- arXiv, Netflix autoplay field experiment: https://arxiv.org/html/2412.16040v1
- ACM Hypertext 2022, The Magic of Carousels: https://dl.acm.org/doi/10.1145/3511095.3531278
- ACM IUI 2025, Under the Hood of Carousels (paywalled): https://dl.acm.org/doi/10.1145/3708359.3712130
- Vale.Rocks, The Death of Character in Game Console Interfaces: https://vale.rocks/posts/game-console-interfaces
