# Console behaviour, in detail: what PS5 and Xbox Series actually do

(Research synthesis, 10 Aug 2026. Twelve research passes, 811 observations, plus a
completeness critique. Written for the couch project - the Kodi-shell / Steam /
DualSense / LG C5 / phone-remote / couchd box - to answer "what do real consoles do,
including the mundane things", so we can decide what to build.)

## How to read this

The value here is the small specifics, so they are preserved rather than summarised.
Exact menu paths, option names, millisecond timings and byte offsets are quoted where
the source gave them. If a number is here, it came from somewhere; if it is folklore,
it says so.

Confidence labels used throughout:

- **documented** - stated by Sony, Microsoft, in a kernel/SDL source file, or in
  published certification requirements. Quotable.
- **widely-reported** - consistent across multiple secondary sources or community
  measurement, but not vendor-stated. Believable, not quotable.
- **folklore** - asserted confidently in secondary write-ups, unverifiable, and often
  wrong. Flagged so it does not get treated as fact later.

Two provenance surprises worth knowing. Microsoft's Xbox Requirements (XRs) are almost
entirely **public** on Microsoft Learn - the full requirement list, the per-XR
certification test cases with literal pass/fail examples, the distribution of top
failing tests, the 27-language terminology table, and the failure-mode scoring maths.
Sony's TRC is NDA-only, but the 1998 PlayStation 1 TRC v1.3 is publicly archived in
full and is startlingly relevant. Sony's modern TRC is confidential licensee material,
and its specifics are deliberately not reproduced in this document.
So a great deal of console behaviour that looks like taste is in fact a written rule
with a number attached.

Each area ends with a **What this would mean for couch** note, sorted into: already
done, cheap, project, not worth it.

---

## 0. The seven through-lines

Everything below is a variation on seven ideas. If the detail is too much, this is the
document in miniature.

1. **The system is an overlay, not a destination.** One button composites the shell
   over a live, still-rendering game. Leaving to Home is a separate, heavier gesture
   that may suspend. Sony: the Control Center "lets you quickly access various features
   of your PS5 console without leaving your game." Microsoft's Guide slides in from the
   left edge over live gameplay. Neither pauses the game to show a menu.

2. **"Off" is a spectrum and it is a policy page, not a switch.** Rest mode / Sleep
   hold a suspended game, keep the network up, drain the download queue, and wake
   themselves overnight to do maintenance. Every capability is a separately named
   toggle with its stated power cost.

3. **Failure is a product surface.** Sony publishes ~290 user-facing error codes, each
   with one plain sentence. Microsoft makes error handling a contractual test with
   pass/fail examples. Both refuse to show a raw code, a stack trace, or a spinner that
   never ends.

4. **Feedback is multi-channel and redundant.** Screen, speaker, chassis beep, pad
   rumble, pad LED. The beep exists specifically so a power action confirms itself when
   the TV is off or on the wrong input.

5. **Numbers are published and enforced.** 20 seconds of static screen fails Xbox
   certification, and PlayStation has an equivalent requirement. 1 GiB of writes per
   rolling 5 minutes triggers a user-visible toast naming the offender. 26 px minimum
   body text at 1080p. 15 gamelists of 100 games. 16-player parties. A 60-minute Share
   Play hard stop.

6. **Interruption is a matrix, not a switch.** ~20 notification categories x three
   contexts (playing games / watching videos / broadcasting), plus position, plus
   duration, plus a session-scoped Do Not Disturb that self-clears on restart.

7. **The direction of travel is: get everything that is not the user's content off the
   main row.** Sony's 2026 home redesign moved PS Plus and PS Store off the tile row
   into an L1/R1 ribbon. Xbox added "hide system apps" and "reduce tile count". Five
   years of iteration converged on less.

---

## 1. The overlay: system UI over a live game

This is the single highest-value pattern in the whole document.

### PS5

- **Single tap of PS** opens the Control Center as a translucent strip along the bottom
  of the running game. Sony: "Press once to access the control center". The game keeps
  rendering and **is not suspended**. (documented)
- **Press and hold PS** goes to the home screen instead. Sony: "Some games and apps are
  paused when you display the home screen. To return to the game you were playing,
  select it from your games home." There is no separate Resume verb - **the game tile
  is the resume affordance**. (documented)
- The hold threshold is user-adjustable: Settings > Accessories > Controller (General)
  > **Press and Hold Delay**, and it applies to both the PS button and the create
  button. (documented)
- **Double-press PS** returns to your most recent card, bypassing the Control Center
  entirely. Sony: "While in a game or an app, you can press the PS button twice to
  return to your most recent card without going through the control center." Also used
  to open chat-transcription text entry while in Picture-in-Picture or Pin to Side.
  (documented)
- The Control Center is two zones: a row of **cards** (contextual, game-supplied) above
  a row of **controls** (persistent system functions). Sony labels them "A) Cards" and
  "B) Control center controls". Selecting a control opens "the control menu", a panel
  that expands upward from the icon. Only the controls are user-arrangeable.
  (documented)

**The ten default controls, in Sony's order and wording** (documented):

| Control | Sony's description |
|---|---|
| Home | "Displays the home screen" |
| Switcher | "Displays recently started games and apps" |
| Notifications | - |
| Game Base | - |
| Music | - |
| Sound | "Manage your sound settings" |
| Mic | "Change your input device, mute and unmute your mic, and adjust the mic level" |
| Accessories | "Check your controller or headset battery level" |
| Profile | "update your online status, access your profile, view your trophies, switch users, and log out" |
| Power | "Turn off your PS5 console or put it in rest mode" |

Customisation is an in-place drag mode, not a settings sub-page of checkboxes: press
PS, highlight an icon, press **Options**, select the icon to move, move it, press X to
set. To hide, physically drag it into the **"Hidden Controls"** area on the same
screen; drag it back out to unhide. Press Options again to exit edit mode. Sony's own
caveat: "Please note, some icons cannot be hidden." (documented)

**Card types** observed across Sony's documentation (documented): Activity, Game Help,
Trophies, Voice Chat (party / game / Discord variants), Broadcast, Share Screen, Media
/ Now Playing, "Recently created", "In Progress" game-group, "Play With Friends",
Tournaments, Messages. Each has a labelled anatomy. The Broadcast card documents A)
Time elapsed, B) Viewers, C) mic/camera/overlay options, D) Pause Broadcast, E) Stop
Broadcast. The "Recently created" card holds exactly the **last 15** captures and only
exists once you have taken one.

Cards support two named multitasking layouts, selectable per card: **Picture-in-Picture**
and **Pin to Side**. "Press the options button or select Multitasking on the voice chat
card, and then select Picture-in-Picture or Pin to Side." Pin to Side splits the screen
with the game still live. Explicitly disabled during 8K output on PS5 Pro - Sony states
the constraint rather than hiding it. (documented)

The **create menu** is a separate overlay on a separate physical button, with five
documented regions: A) Recently created thumbnail, B) capture methods (Save Recent
Gameplay / Take Screenshot / Start New Recording), C) Broadcast, D) Share Screen, E)
Capture Options. (documented)

### Xbox Series

- **Single tap of Xbox** slides the Guide in from the left edge over the running game.
  Microsoft: "the guide is the Xbox quick-start menu that gives you easy access to your
  favorite features from anywhere on your console." Reported open latency around one
  second on Series X|S. Closed with Xbox again or B. (documented)
- **LB / RB cycle the Guide's top tabs.** Verbatim from Xbox Support: "Press the XBOX
  button on your controller to open the guide. Press the Left bumper and Right bumper
  to cycle through the tabs." D-pad/stick moves focus **within** a tab; shoulders move
  **between** tabs. (documented)
- **Six top tabs**, in the documented default order: Guide (Home), People, Parties &
  chats, Game activity, Capture & share, Profile & system. (documented)
- **A second, bottom row of five utility tabs** that most write-ups miss entirely:
  Notifications, Game Pass, Store, Search, Audio & music. Introduced August 2020;
  Xbox Wire described adding "buttons to the bottom of the page for important utilities
  like notifications, search, and audio settings, making it easier to access them from
  wherever you are." (documented)
- Tabs are user-reorderable with an explicit one-action **return to default positions**.
  (documented)
- **Hold Xbox** opens the Power Center: turn console off, restart console, turn
  controller off, switch profile. Roughly a two-second hold. (widely-reported)
- **Double-tap Xbox** switches directly between the two most recent apps or games,
  bypassing the Guide. (widely-reported)
- The Guide is reported to reopen on whichever tab you last used. **(folklore - could
  not be confirmed on a Microsoft page, and it conflicts with the more commonly
  described behaviour of always opening on Guide/Home. Decide deliberately either way;
  do not assume.)**

### The shared rule about audio and pausing

Neither shell ducks game audio for the overlay itself. The game keeps playing at full
level under a dimmed/blurred frame. Ducking is reserved for voice chat (Xbox chat mixer
at 50% or 80%) and for explicit notification tones. (widely-reported)

Neither shell shows a launch sound. The transition into a game is visual only; the next
audio you hear is the game's own. The shell's ambient music **stops before** the game's
first frame, not after - an overlap reads as a bug. (widely-reported)

### What this would mean for couch

- **Already done.** PS tap/double/hold/long-hold vocabulary exists and is bound from
  Kodi's own settings page, with one config file both stacks read plus a safety rail.
  The switcher power bar exists. couchd's freeze/thaw machinery exists.
- **Cheap.** Bind double-tap to "swap between Kodi and the running game" - both
  platforms converged on this independently, which is decent evidence it is the right
  default. Add a user-tunable hold delay to the gesture config, copying "Press and Hold
  Delay". Make the Kodi home tile for a running game *be* the resume affordance rather
  than adding a separate "Resume" entry.
- **Project.** The real prize: an overlay that composites over a **live gamescope
  surface** without SIGSTOPing the game. Today the shell has to take the screen. The
  design rule to enforce is Sony's: the overlay never suspends; only leaving to Home
  does. That boundary is exactly where the game-pids/Proton suspend logic already sits,
  so it is a routing decision more than new machinery.
- **Not worth it.** Pin to Side over a Steam game on X11. Sony hit real constraints
  doing it with full control of the stack.

---

## 2. Home, tiles, and the two-homes split

### PS5

- Home is a **single horizontal row of large tiles** with a full-bleed background image
  that changes to match the highlighted tile, plus a top-left toggle between two
  "homes". Sony: "From the home screen, you can go to two types of content: games or
  media. In the games home, you'll find your games, PlayStation Store, and other
  game-related apps. In the media home, you'll find music, video, and other non-game
  related apps." Tiles are auto-sorted by recency/frequency; you do not hand-arrange the
  row. (documented)
- **The giant background is a live network fetch, not local key art - and it broke.**
  Eurogamer, 30 Sept 2024: the home screen began "prominently displaying promotional
  article headlines across the centre of its homescreen alongside full-sized background
  images, based on whatever happens to be top of the currently selected game's
  newsfeed", replacing the previously static art. Users reported it "seemingly can only
  be disabled by disconnecting the PS5 from the internet". Sony blamed an unintended
  "tech error" on 1 Oct 2024. (widely-reported, and the single best cautionary tale in
  this document)
- The **Disc Player** tile appears in media home automatically the moment a disc is
  inserted: "To play a Blu-ray Disc or DVD, insert the disc into the disc slot. Disc
  Player appears on your media home, and playback can begin." (documented)
- **Welcome hub** replaced the US-only Explore hub in 24.06-10.00.00 and sits at the
  head of the games row. It is a widget canvas, not a content feed. Rollout was staged
  and Sony said so: "A limited number of users will receive the Welcome hub in this
  update. All users worldwide will receive this enhancement within 1-2 months."
  (documented)
- **The twelve Welcome hub widgets**, as Sony names them: Friend Activity, Friends
  Online, Messages, Console Storage, Trophies, PlayStation Store, PlayStation Plus,
  News, Accessibility, Media Gallery, Battery, Your Wishlist. (documented)
- Widget editing is a modal grid with direct manipulation on the shoulders: **L1
  shrinks, R1 grows, Square picks up and moves, X toggles on/off**. R3 is a shortcut
  straight into edit mode (or Triangle then Edit Widgets). Three named presets plus your
  own: Highlights, Social, Solo, Your Preset. A **"Large Layout"** toggle blows every
  widget up to maximum size at once, "which can make navigating through all the widgets
  a bit easier". (documented)
- **Showcase Mode** (26.02-13.00.00): "You can now use Showcase Mode to display a full
  view of your Welcome hub background when your PS5 console is idle. When turned on,
  your Welcome hub automatically enters Showcase mode when idle... You can also set the
  idle time to enter Showcase mode according to your preference." A companion Slideshow
  mode rotates through a Media Gallery album as the background. (documented)
- Background sources are three tabs: **From PlayStation** (original artwork, some
  animated), **Games** (per-title art), **Media Gallery** (your own captures). Since
  26.02 you can also set it from *inside* the Media Gallery - the action lives in both
  places. (documented)
- Since 25.03-11.20.00, **Appearance and Sound** (Settings > System > Appearance) can
  re-skin the entire shell as PS1, PS2, PS3 or PS4, changing visuals **and sound effects
  together**, including the PS1 boot screen and the PS3 wave with "the classic tick
  sound as you move through the UI". Originally a limited-time 30th-anniversary feature
  (Dec 2024), made permanent. (documented)
- **Every game has a game hub** reached by selecting its tile: activities, add-ons,
  news, broadcasts, trophy progress, tournaments, PS4-to-PS5 upgrade offer. Trophy
  progress shows in the corner when a game is highlighted on the row, and since
  21.02-04 it breaks down Gold/Silver/Bronze counts rather than just a percentage.
  (documented)

### Xbox Series

- Home allows exactly **10 pinned games and 10 pinned groups**. Xbox Support: "You can
  add up to 10 games and 10 groups to Home." The group cap was 2 until an April 2026
  update raised it to 10. (documented)
- Groups **roam with the profile**: "Your groups stay with your profile, so you'll see
  them when you sign in on any Xbox console." (documented)
- **"Add to home"** is reachable from three surfaces - Microsoft Store, My games & apps,
  and a tile already on Home - always via the **Menu (hamburger)** button on the tile.
  (documented)
- Within the recently-played row you can **pin up to three** items so they never age
  out. Xbox Wire, May 2025. (documented)
- **"Hide system apps"** toggle for the recently-played row, "creating a cleaner view
  focused on your games and entertainment". (documented)
- A separate **"reduce the number of tiles shown"** setting, available from 22 May 2025.
  Density and membership are treated as two different axes. (documented)
- **Dynamic Backgrounds**: animated wallpapers, roughly 134 of them, some recoloured by
  the user's chosen accent colour. An option makes the background follow whichever game
  is focused in the recently-played row - which drew complaints about crowding and
  prompted a rework. (documented / widely-reported for the count)
- **Custom accent colour** with sliders beyond the fixed palette (March 2026 Insider),
  tinting the Guide, switchable off at Settings > General > Personalization > Customize
  the guide. The nice detail: **the last custom colour is remembered if you temporarily
  pick a system preset**, so returning is lossless. (documented)
- All community/activity posts are rendered at **a single uniform size**, deliberately.
  Xbox Wire, Aug 2020: "all posts shared on Xbox are now the same size: no more guessing
  on how they will show up". (documented)

### The 2026 direction of travel

A PS5 home redesign has been in staged beta since early April 2026 and, as of early
August 2026, still has no official patch note (26.03 through 26.05 mention only
messaging and usability). It replaces the two-way Games/Media toggle with a
**five-section ribbon navigated by L1/R1**: Games, Library, Media (Apps), PS Plus, PS
Store. The horizontal tile row becomes games-only; PS Plus and PS Store move off the
row into the ribbon. The Welcome page stays at the head of the games row.
(widely-reported)

That is the lesson: after five years, Sony's own fix was to get everything that is not
your content off the main row and behind a shoulder-button ribbon.

### What this would mean for couch

- **Already done.** Home tiles animate their grow/shrink (Kodi-side skin work, 8-9 Aug).
  The Games row self-updates. The achievements shelf exists.
- **Cheap.** A hard cap on the home row (10 is a deliberate, defensible number) with
  replace-oldest. A "hide system entries" filter so Settings, the Steam shim and the
  switcher never occupy the recency row. A density setting - the skin already animates
  tile scale, so "how many" is nearly free. Three sticky slots inside the MRU row so the
  thing used daily never ages out.
- **Cheap and high value.** A Welcome-hub equivalent as the first item in the row: disk
  free space, disk health, download queue, what is newly added, TV/soundbar state. That
  is the actual couch use case and it beats Sony's news feeds for a private box.
- **Cheap.** Auto-surface a tile the moment media is physically present - USB stick
  mounted, disk2 reattached - the way Disc Player appears on insert.
- **Project.** An idle Showcase mode: fade the widgets, show the background full-screen,
  with a configurable idle timeout that fires *before* the display-off timeout. Kodi has
  screensavers but they are rarely wired to the home skin's own background.
- **Project (worth it).** A per-game hub aggregating what is currently scattered:
  achievements, playtime, last played, ProtonDB/compat notes, gamescope wrap status,
  install size, launch button.
- **Rule to adopt now.** If home tiles pull artwork from TMDB, the Steam CDN or
  SteamGridDB: cache locally, pin the asset, and never let a network fetch change what
  the user sees on a tile they already know. Offline must look identical to online.
  Sony got this wrong in public and could not turn it off.
- **Not worth it.** Two-way Games/Media toggle as a mode. Sony is currently migrating
  away from it toward a ribbon.
---

## 3. Library, organisation, and the store/library divide

### PS5 Game Library

- Exactly **two tabs**: "Your Collection" and "Installed". A third, "Movable to USB
  Extended Storage", appears **only if both M.2 and USB extended storage are present** -
  a tab that exists only when the hardware condition that makes it meaningful is true.
  (documented)
- In-library search was added in 23.02-08.00.00: "In game library, you can now search
  for games just within your game library." (documented)
- **Hiding** is per-account and global: highlight a game in Your Collection, Options >
  Hide. "Games you hide will be hidden from your Library on all consoles." To see them
  again: Filter and Sort > turn on **Hidden Items** "to temporarily show your hidden
  games". Note **temporarily** - the reveal does not persist as a filter state you
  forget you set. (documented)
- **Gamelists** are user-made folders, hard-capped at **15 lists x 100 games**, with a
  game allowed in multiple lists. Sony's beta notes via Gematsu: "You can have up to 15
  gamelists and 100 games per gamelist. All games under the Your Collection tab of your
  Game Library can be added to a gamelist, including disc, digital and streaming titles.
  You can also add the same game to multiple gamelists." Lists pin to the very top of
  Your Collection. Add via Options > Add to Gamelist on any game, or Add More to
  Gamelist from inside the list. Options on the list itself gives Edit Name / Delete
  Gamelist. (documented)

  The design point: gamelists are **tags** (many-to-many) presented as folders. The
  caps exist so the row never becomes a scrolling problem.

- **Media Gallery** has four fixed tabs plus a conditional fifth: All, Favorites,
  Trophies ("Watch a video clip of the moment you unlocked a trophy"), Albums (grouped
  by game), and "When you connect a USB drive to your PlayStation 5 console, the USB tab
  appears in the Media Gallery." Per-item actions: Share, Add to Favorites, Edit,
  Delete, and under More: Copy to USB Drive, Edit in Share Factory Studio, Information
  (rename). Bulk via "Select Multiple". Media is one-way: "Media can't be copied from
  the USB drive to your console storage." (documented)

### Xbox My games & apps

- **Six tabs**: Games, Apps, Groups, Play history, Full library, Manage.
  (widely-reported)
- Note the axis split: what is installed (Games/Apps), what I organised (Groups), what I
  did (Play history), plumbing (Manage).
- **Full library** is sub-sectioned by **entitlement**, not genre: All games, Owned
  games, Xbox Game Pass, Games with Gold, Free with Xbox, Owned apps, subscriptions.
  It additionally groups by generation/enhancement tier: Optimized for Xbox Series X|S,
  Xbox One X Enhanced, Xbox One, Xbox 360 & Xbox. (widely-reported)
- **Manage** deliberately holds download queue, pending updates, storage devices and
  save data in one place, away from the browsing tabs. (widely-reported)
- **Partial / customised installs**: for supporting titles you choose which components
  to install - campaign only, specific multiplayer modes, HD texture packs, language
  packs. Xbox Support: "you can customize the installation of the game to focus on the
  modes and features best suited for your device and preferences." (documented)
- There is a setting to **hide games with no achievements** from achievement views, with
  its own support article. (documented)

### Store versus library

Both platforms split the two jobs cleanly: **the store is where you decide, the library
is where you install and manage.** On PS5 you buy in the Store ("Select Buy > Confirm
Purchase > Download") and then find the download at Game Library > Your Collection >
select game > Download. "Require Password at Checkout" is the anti-accident guard.
Pre-orders auto-download at release if automatic downloads are configured. (documented)

On Xbox, Store and Game Pass are **two separate Guide bottom-row tabs** - "available to
buy" and "available to me right now" are treated as different browsing surfaces.
(documented)

Xbox also puts **Search** in that bottom utility row, spanning store, library and apps
from one field, reachable mid-game. (documented)

### Uninstall framing

Xbox states plainly that uninstalling is non-destructive: "Any data for your games and
apps (preferences, saved games) syncs online when you sign in, so when you reinstall a
deleted game or app, your saved data comes right back with it." That one sentence is
what makes people willing to uninstall to free space. (documented)

When an install will not fit, the flow is offered **at the point of failure**, not
buried in Settings: "If there isn't enough space when you try installing a new game or
app, we have tips to help you make room so you can install it right away." (documented)

### What this would mean for couch

- **Already done.** Library and Discover tabs exist; the couch app has 4K request
  toggles and upgrade buttons for the arr stack.
- **Cheap.** Adopt the two-tab library shape (everything / installed) and the temporary
  hidden-items reveal. Make context actions identical on every representation of an item
  - the Kodi skin and the phone app should both expose the same verbs, the way Xbox puts
  "Add to home" on Menu everywhere.
- **Cheap.** Tags-presented-as-folders is the right model for a Steam + emulator + media
  library. Cap them so the row stays scannable.
- **Cheap.** Group by **how it runs** - native Linux, Proton, shadPS4 - the way Xbox
  groups by generation. It is honest and it sets expectations before launch.
- **Cheap.** Show tabs only when their precondition is true (no USB tab with no USB
  attached; no soundbar card with nothing on eARC).
- **Project.** A single Manage destination: Steam downloads, pending updates, disk
  state, save/prefix data. Steam downloads are currently invisible from the couch.
- **Project.** Surface Steam's optional depots and language selection at install time,
  the way Xbox exposes "skip the 60 GB HD texture pack". Genuinely useful given the disk
  situation.
- **Not worth it.** Entitlement sub-sectioning. Steam has one entitlement model.

---

## 4. Navigation grammar: buttons, focus, sticks, lists

### The button contract

Sony documents the whole shell's semantics (documented):

- **Cross** - select
- **Circle** - cancel
- **Triangle** - "rearrange the items in a list, or view related information"
- **Square** - "Use as a shortcut for context-sensitive commands and to view more
  functions for a specific item"
- **D-pad** - move focus
- **Options** - opens the options menu

That is why Triangle opens Welcome hub editing and trophy comparison, and Square deletes
a notification and picks up a widget.

Microsoft's equivalent (documented): **A** selects, **B** goes back and closes the
Guide, **Menu (hamburger)** opens the context menu on the focused item, **View** is a
secondary/filter action. Xbox Wire noted a deliberate 2020 pass to make "shortcuts and
button commands more consistent" across guide pages.

The 1998 PS1 TRC already had the rule, and the useful half is the second sentence
(documented): "The Triangle button should be used to take the user back to the previous
menu. When the user presses the triangle button, the game must return the user to the
previous screen **without accepting any changes** that may have been made on the screen
they are quitting from." Back discards.

### Sticks and shoulders

Sony's User's Guide navigation table (documented):

| Input | Role |
|---|---|
| Directional buttons | Move focus |
| **Left stick** | **Move pointer** |
| **Right stick** | **Scroll** |
| L1 | Back |
| R1 | Forward |
| Cross | Select |
| Circle | Back |

The left stick is a genuine free pointer, not a d-pad emulator. The same idiom drives
the Share Screen pointer/ping/draw and pans the zoomed display area.

**L1/R1 are reserved for lateral section jumps throughout the shell, never for page
scroll** (documented): back/forward in the User's Guide; cycling content *within* a
Welcome hub widget (news stories, wishlist items, featured store titles, accessibility
categories); resizing widgets in edit mode; swapping between console and external
storage in the Storage Summary widget; and moving between the 2026 redesign's five
ribbon sections. Xbox uses the same pair for Guide tabs.

### Lists do not wrap

This is the most actionable single finding in the document.

PS5 lists **do not wrap around**, and Sony shipped an update whose only navigation
change was to make the dead-end feedback louder. Version 23.02-08.00.00, verbatim: "The
console navigation experience has been improved. When moving the cursor while
navigating the console, the sound effect you hear when you reach the point where you
can't move any further is now more pronounced and noticeable." (documented)

The same update added Settings > Accessibility > Controllers > **Haptic Feedback During
Console Navigation**, whose documented triggers are: moving a slider / moving your
focus; selecting a checkbox / turning a setting on or off; receiving a notification;
selecting a highlighted item / cancelling a command; and using the on-screen keyboard.
(documented)

So the end of a list is signalled on three channels at once: it does not move, it makes
a distinct louder sound, and it bumps the pad.

### Focus is never nowhere

Xbox Wire, Aug 2020: the visual refresh "includes some changes to our tile shape, fonts,
and focus indicator across the experience". Focus is never lost - there is no state
where nothing is focused. (documented) This is the rule Kodi skins most often break: a
dialog opens with no focused control.

### Hold-to-repeat

**Folklore warning.** Community/developer lore puts Xbox's initial d-pad repeat delay
around 400-500 ms with acceleration after roughly a second of hold. No Microsoft
documentation of the delay or rate could be found. Treat as unverified.

What *is* documented is that Sony treats repeat as a tunable rather than a constant, at
Settings > Accessories > Other Accessories for keyboards: **"Key Repeat (Delay): Select
how long it takes for a character to start repeating when you press and hold"** and
**"Key Repeat (Rate): Select how fast a character repeats"**. Kodi exposes similar
values only in advancedsettings.xml. (documented)

### Contextual hints

Xbox Wire, Aug 2020: "We've added hints tailored for new customers, helping them
understand the purpose of each page, and how to get started using it." A one-line "what
this tab is for" under each tab header. (documented)

### Multiple paths to the same control, on purpose

Sony documents both routes rather than picking one (documented). Examples: Audio Focus
from Settings > Sound > Volume **and** from Control Center > Sound; keyboard/mouse
settings from Settings > Accessories **and** Control Center > Accessories; online status
from the profile, the Control Center, **and** Options on the user-selection screen;
Welcome hub background from the hub **and** from Media Gallery; saved-data sync from
Settings **and** from Options on a game tile; restore licence from Settings > Users and
Accounts > Other **and** from Options on a game in home or Game Library.

The general rule: **any action concerning an object lives on that object's Options menu,
and also exists in the settings tree.**

### What this would mean for couch

- **Cheap, highest ratio in the document.** Decide wrap-versus-bump for every container
  in skin.couch, and give the bump an audible and haptic signature. `ff_memless` is
  already bound to `hid-playstation` on this box, so the pad can be rumbled from
  userspace today.
- **Cheap.** Commit to a face-button contract system-wide - Triangle = rearrange/related,
  Square = context shortcut, or the Xbox equivalent - and enforce "back discards". Kodi's
  default pad map is inconsistent about the third and fourth face buttons.
- **Cheap.** Reserve L1/R1 exclusively for lateral section jumps. Never page-scroll.
- **Cheap.** Assert "focus is never nowhere" as a skin invariant and add it to the
  view-image verification checklist.
- **Cheap.** Make every object's context menu the same everywhere, and mirror it in the
  phone app.
- **Project.** A genuine left-stick pointer mode for dense screens (settings, keyboards,
  web views) with right-stick scroll. The DualSense touchpad is a better answer - see
  section 7.
- **Do not assume.** Pick your own repeat delay/rate and tune by feel; the console
  numbers floating around are folklore.

---

## 5. Motion: the numbers

Microsoft publishes the exact recipe its console shell family descends from. This is
directly copyable into Kodi `<animation>` blocks and into the Svelte remote's CSS.

### The page-transition spec

Verbatim from Microsoft Learn, *Motion in practice* (documented):

| Phase | Motion | Duration | Easing |
|---|---|---|---|
| Forward Out | Fade out | 150 ms | Default Accelerate |
| Forward In | Slide up 150 px + fade in | 300 ms | Default Decelerate |
| Backward Out | Slide down 150 px | 150 ms | Default Accelerate |
| Backward In | Fade in | 300 ms | Default Decelerate |

Note the asymmetry: **leaving is always half the duration of arriving.**

### The two curves that do almost all the work

(documented)

- **"Fast Out, Slow In"** = `cubic-bezier(0, 0, 0, 1)` for UI **entering** the scene.
  Extreme deceleration; reads as "travelled from far away, arrived instantly".
- **"Slow Out, Fast In"** = `cubic-bezier(1, 0, 1, 1)` for UI **leaving**. Accelerates
  to escape velocity, "gets out of your way".

Microsoft says these are extreme on purpose, and states the trick explicitly: even if
entry is preceded by a moment of unresponsiveness, the incoming velocity makes it feel
fast. **The animation is the loading cover.**

Nothing uses a symmetric ease-in-out for entry/exit.

### The Fluent 2 duration ladder

Eight steps, nothing above 500 ms (documented):

`durationUltraFast` 50 ms, `durationFaster` 100 ms, `durationFast` 150 ms,
`durationNormal` 200 ms, `durationGentle` 250 ms, `durationSlow` 300 ms,
`durationSlower` 400 ms, `durationUltraSlow` 500 ms.

**Rule that falls out of it: any Kodi window animation longer than half a second is
wrong.**

### The Fluent 2 easing palette

Nine curves, graded max/mid/min so you pick intensity rather than shape (documented):

```
curveAccelerateMax   cubic-bezier(0.9, 0.1, 1,    0.2)
curveAccelerateMid   cubic-bezier(1,   0,   1,    1)
curveAccelerateMin   cubic-bezier(0.8, 0,   0.78, 1)
curveDecelerateMax   cubic-bezier(0.1, 0.9, 0.2,  1)
curveDecelerateMid   cubic-bezier(0,   0,   0,    1)
curveDecelerateMin   cubic-bezier(0.33,0,   0.1,  1)
curveEasyEaseMax     cubic-bezier(0.8, 0,   0.2,  1)
curveEasyEase        cubic-bezier(0.33,0,   0.67, 1)
curveLinear          cubic-bezier(0,   0,   1,    1)
```

**Linear is reserved for rotation (spinners) only.** That is a useful constraint for any
busy indicator.

### Control-level micro-animation

WinUI 3 shared durations, all under a quarter second (documented):

- `ControlFasterAnimationDuration` **83 ms**
- `ControlFastAnimationDuration` **167 ms**
- `ControlNormalAnimationDuration` **250 ms**

83 ms and 167 ms are conspicuously **5 and 10 frames at 60 Hz**. Expressing focus
feedback in whole frames avoids the half-frame stutter you get from round numbers like
100 ms at 60 Hz.

### Expand and contract are not symmetric

Microsoft's object example: **Expand = 300 ms, easing Standard. Contract = 150 ms,
easing Default Accelerate.** Exactly 2:1. Growing is considered; shrinking is
dismissive. (documented)

### Decoupled timings on PS5's home screen

Highlighting a game repaints the whole screen: the tile scales up, and the backdrop
cross-fades to that title's key art. The two are **deliberately out of sync** - the
backdrop cross-fade is slower than the tile scale. Fast tile response (~150 ms) with a
slow backdrop cross-fade (~400-500 ms) reads as responsive *and* cinematic; matching
them reads as sluggish. (widely-reported)

### No spinners for ordinary navigation

Neither shell shows a spinner for normal navigation. Busy states hide behind the
transition animation itself; a spinner appearing is an admission of failure. Progress
rings are reserved for genuinely long operations - store pages, installs, sign-in,
system updates. (widely-reported)

**Rule to adopt:** if an operation can complete in under ~300 ms, run the entrance
animation and never show a busy indicator. Only escalate to a visible indicator after a
delay threshold (300-500 ms is the common band).

### The opposite treatment for system updates

Full-screen, unskippable, percentage-accurate progress with no animation flourishes and
no music, on a flat background, with an explicit "do not turn off" warning. The absence
of decoration **is** the design - it signals seriousness and that the number is real.
(widely-reported)

### Reduce motion

- PS5: Settings > Accessibility > Display and Sound > **Reduce Motion** - "Turn on to
  reduce motion effects and screen movement." Sony does not publish exactly which
  effects it kills; user reporting says it flattens the home-screen background
  parallax/drift and shortens or removes context transitions. (documented)
- Xbox splits it into **two** switches, because they bother different people:
  **"Disable background images"** and **"Disable animations"**. (documented)
- Xbox Accessibility Guideline **117** goes further and is a formal rule: for
  auto-updating content you must provide "a method to control the frequency of updates"
  **and** "a method to pause, stop, or hide"; for moving/blinking/scrolling/flashing
  content you must provide "a mechanism to entirely disable this content" **and** "a
  mechanism to pause or hide". Microsoft's own cited example is the Xbox Store app,
  which exposes **separate "Autoplay Video" and "Autoplay Sound" toggles**. (documented)

### What this would mean for couch

- **Already done.** A modern UI pass is complete; sheet animation and the home-tile
  grow/shrink exist.
- **Cheap, do it now.** Adopt the eight-step duration ladder as CSS custom properties in
  the phone remote and as a documented ms table for skin.couch. Adopt the 150/300
  forward-transition asymmetry and the two curves. Audit every animation over 500 ms.
- **Cheap.** Re-check the existing home-tile grow/shrink against the 2:1 rule (expand
  300 ms standard, contract 150 ms accelerate).
- **Cheap.** Decouple tile-scale timing from backdrop cross-fade timing. Currently they
  are probably the same value.
- **Cheap.** Express focus feedback in whole frames (5/10/15 at 60 Hz), not round ms.
- **Cheap.** A single "Reduce motion" flag that clamps skin animation times, plus
  honouring `prefers-reduced-motion` in the web remote. Ship the Xbox split: motion and
  background imagery are separate switches.
- **Cheap.** If Discover ever autoplays trailers, ship **two** toggles - video and its
  sound - per XAG 117.
- **Rule.** No busy indicator under ~300 ms; use the entrance animation as the cover.
  Kodi is prone to showing busy dialogs for trivial operations.
---

## 6. Sound: the numbers, and the deliberate silence

The two platforms have **opposite philosophies**, and this is a fork in the road we have
to pick rather than blend.

### PS5: sonically dense

- The circulated system-software SFX rip contains **45 distinct files** (KHInsider,
  added Aug 2025, ~1 MB, MP3 and FLAC). That is roughly one sound per interaction class,
  not one click reused. (widely-reported)
- **Home Screen Music** is continuous ambient audio that **changes per highlighted
  game** - hovering a tile swaps the soundtrack to that title's own music, because games
  ship a home-screen music stem. Settings > Sound > Audio Output > "Home Screen Music:
  Turn on/off the music that plays in the background on your home screen." Turning it
  off kills the per-game hover music too. (documented)
- **Sound Effects** is the single master toggle, sitting immediately below Home Screen
  Music in the same General section: "Turn on/off the sounds heard during some functions
  such as scrolling." (documented)
- Navigation ticks are short, sharp and pitched. The launch UI videos were specifically
  noted for the on-screen keyboard producing "short, sharp bursts of sound each time
  they move the cursor". (widely-reported)
- There is a **distinct end-of-list sound**, deliberately made "more pronounced and
  noticeable" in 23.02-08.00.00 (see section 4). (documented)
- **Controller haptics are a third feedback channel** for system navigation, not just
  games (see section 4). (documented)

### Xbox: nearly silent

Xbox has no per-move navigation tick. The audible system events are the boot chime, the
achievement unlock (with a distinct rare variant), notification tones, and
controller/accessory events. Xbox spends its feedback budget on motion.
(widely-reported)

Both approaches work. **Doing both would feel noisy.** Given Kodi's animation strengths,
the Xbox model - silent navigation, sound reserved for events - is probably the cheaper
and safer default, with PS5-style ticks as an opt-in.

### The chassis beep: feedback that does not need the TV

The PS5 has a speaker in the console itself, independent of HDMI/TV audio.

- Settings > System > **Beep and Light**. Volume: **High (Standard) / Medium / Low**.
  Separate **"Mute Beep Sound"** toggle. (documented)
- Sony's carve-out is precise: the mute toggle "applies to the beep sound made when you
  turn your console on or off, or enter rest mode" - other beeps (disc insert) are
  **not** silenced by the mute toggle, but **are** affected by the volume setting.
  Physical media moving is treated as safety-critical and exempted from the user's mute.
  (documented)
- **Beep count encodes power intent.** Tap the power button = one beep = Rest Mode.
  Press and hold: first beep immediately, keep holding roughly 3 seconds (commonly
  reported as ~7 s to the second beep on some models) until a second beep = full
  shutdown. Because it is audio, the confirmation works with the TV off or on the wrong
  input. (widely-reported)

### Boot identity

- Xbox Series X launch boot: the X logo fades in starting with the **inner lines** before
  the full logo emerges as solid white on black; audio is a rising sequence of ethereal
  chords, roughly 10 s at launch. No voice, no fanfare, no percussion. (widely-reported)
- Microsoft **cut the boot animation in half twice, for psychological reasons**. 2022:
  animation from ~9 s to ~4 s, total cold boot ~20 s to ~15 s, explicitly so the
  power-saving mode would be tolerable enough that people stopped leaving the console in
  standby. May 2026: repeated, cold start ~12 s to ~7 s, animation 9 s to 4 s, with a
  new "glassy" green logo and, per reporting, "a softer soundscape that ditches the
  sharp Xbox One-era tones". (documented)
- **The animation only exists on cold boot.** Instant-on/Sleep wake skips it entirely and
  lands on the exact screen you left. Reporting is explicit: "you don't see this startup
  animation when your console isn't placed into Energy Saver mode". (documented)
- Part of what the animation is *for* is covering HDMI handshake time - neither console
  shows a boot animation until the display has actually synced. (widely-reported)

### Achievement and trophy sounds are tiered

- Xbox: rare achievements (unlock percentage **below 10%**) play "a special, epic version
  of the sound", get a diamond glyph, and dwell longer - reporting puts the rare toast on
  screen for roughly **eleven seconds** versus a few seconds for standard. A 2026 update
  refreshed both icons and animations. (widely-reported)
- PS5: the platinum has its own longer fanfare, distinct from the shared non-platinum
  sound. There is no user setting to change trophy sounds. (widely-reported)

**Two sounds, not four.** One distinct longer sound for the rare/completion case, one
reused sound for everything else.

### Ducking, with real numbers

- Xbox **Chat mixer**: Profile & system > Settings > General > Volume & audio output >
  Advanced > Additional options > Chat mixer. Options reduce other sounds by **50%** or
  **80%**. Party chat also has noise suppression, on by default. (documented)

  Note the magnitude: half or more, not the timid 10-20% most software uses.

- PS5 **Audio Focus** (added 25.03-11.20.00): Settings > Sound > Volume > Audio Focus >
  Use Audio Focus, or from the Control Center mid-game. Four presets named for what you
  want to hear, not for frequencies: **Boost Low Pitch** (roaring engines, rumbling),
  **Boost Voices** (voice chats, character voices, middle frequencies), **Boost High
  Pitch** (footsteps, metallic noises), **Boost Quiet Sounds**. Adjustment Level:
  **Weak / Medium / Strong**. **Adjust L/R Separately**. An **"Audio Preview"** button
  A/Bs it on the settings screen. Headphones only - explicitly not supported over HDMI
  to TV, AV receivers or soundbars. One user at a time. Incompatible with PS VR
  (CUH-ZVR). (documented)

### Deliberate silence

- **No launch sound on either platform.** (widely-reported)
- **No spinner sound.** (widely-reported)
- **Sitting on the home screen must be silent.** Both consoles run near-silent at the
  dashboard and ramp under load; Series X is widely measured as effectively inaudible at
  the dashboard. If the box is audible while Kodi idles, that is a shell-experience bug,
  not just a thermal preference. (widely-reported)

### Text entry is the densest sound moment

The on-screen keyboard with a d-pad is where repeat rate is highest and where people
notice the sound design. If ticks exist anywhere, they must be **shortest and quietest**
here. Consider lowering gain on repeated ticks within roughly 120 ms of each other.
(widely-reported)

### Sound is part of the theme, not a separate setting

Sony's Appearance feature bundles the visual look and the navigation sounds together as
one named preset. PS1 look ships with PS1 sounds; the PS3 wave ships with "the classic
tick sound". (documented)

### Three independent sound controls, not one

Sony keeps **UI Sound Effects**, **Home Screen Music** and the **hardware Beep** as three
separate controls with three separate scopes, plus a fourth for indicator LED
brightness. Xbox has a discrete accessibility setting, **"Mute sound effects"**, for the
shell's own UI sounds separate from all other volume, with its own support article.
(documented)

### What this would mean for couch

- **Decide first.** Pick the Xbox model (silent navigation, sound on events) as the
  default. It is cheaper, it will not fight Kodi's animations, and UI sounds are one of
  the first things people turn off.
- **Cheap.** Kodi skin sound support accepts a folder of named WAVs mapped to actions.
  If sounds are added, ship a coherent named set as part of a skin *appearance*, not as
  a scatter of toggles. Give it one obvious off switch next to the music toggle.
- **Cheap.** Tier the achievements shelf's notification: one longer distinct sound for
  rare/completion, one for everything else.
- **Cheap.** A short chime plus logo on cold boot only, from a systemd unit, sized to
  the *measured* 4K120 mode-set plus TV input-switch time. It must never fire on resume.
  Keep it under 4 s.
- **Cheap and good.** The PS5 beep principle: physical actions deserve feedback that does
  not depend on the TV being awake. The box has no chassis speaker, but a short beep
  through the soundbar, a pad rumble, or a phone-remote haptic all work. "Command
  received, TV still waking" is a real state here.
- **Cheap.** PipeWire filter-chain EQ presets named the Sony way - "Boost Voices" beats
  "presence EQ +4 dB @ 2 kHz" - with an in-place preview button. A late-night
  dialogue-boost preset is exactly what a couch box should offer, and unlike Sony's we
  can apply it to the soundbar path as well as headphones.
- **Cheap.** Use 50% / 80% as the ducking ladder if couchd ever ducks Kodi/Steam audio
  under a notification or voice event. Do **not** duck for the overlay opening.
- **Rule.** Stop home-screen ambience *before* the game's first frame, never after.
- **Not worth it.** Per-game hover music. High effort, high annoyance, needs cached
  per-title stems.

---

## 7. The controller as a system device

The pad is a peripheral of the OS, not just of the game: a power button, a mute switch,
a notification surface, an identity badge, a capture trigger and a battery-reporting
device. Most of it is system software talking to firmware over vendor HID reports.

**The good news for this box:** the in-tree `hid-playstation` driver (written by Sony's
own Roderick Colenbrander) is loaded right now on kernel 7.0.0-28 with
`led_class_multicolor` and `ff_memless` as dependencies. It exposes the five player
LEDs, the RGB lightbar, rumble, the mic-mute LED and battery through standard
LED / power_supply / force-feedback classes. A Kodi shell can drive most of the console
vocabulary with sysfs writes today.

### Button vocabularies

| Gesture | PS5 | Xbox |
|---|---|---|
| Tap system button | Control Center overlay | Guide overlay |
| Double-tap | Return to most recent card (PS4: switch to previous app) | Switch between two most recent apps |
| Hold | Home screen | Power Center (off / restart / turn off controller / switch profile) |
| Hold ~3 s (pad disconnected) | - | Re-associate a dropped controller |
| Hold ~6 s (console off) | - | Powers on **both** controller and console |
| Hold ~6 s (no console) | - | Controller powers off |
| Hold 10-15 s | Controller powers off | ~15 s forces a hard controller reset |
| Console button hold ~10 s | Hard power off (2nd beep at ~7 s = full shutdown) | Hard power off |

(PS5 items documented or widely-reported as noted in section 6; Xbox hold durations
widely-reported.)

**Trap:** any host-side long-hold binding must be **shorter than 6 s** on an Xbox pad, or
it races the pad's own firmware power-off. The PS5 pad's own power-off at 10-15 s is
firmware-level and produces a clean Bluetooth disconnect - couchd must not treat that as
a fault or try to re-wake.

**Pressing PS on a sleeping console wakes it.** The PS5 keeps its Bluetooth radio alive
in Rest Mode specifically to listen for this, and no other button does it. (documented)

Sanctioned pad power-down: **Control Center > Accessories > DualSense Wireless Controller
> Turn Off** - which also drops a second pad without unpairing it. (documented)

### The Create / Share button: one button, three actions

PS5 **Standard** mapping (widely-reported): single press opens the Create menu; press and
hold takes a screenshot; double press saves a clip of recent gameplay.

Sony ships **named presets** rather than raw per-action remapping: Settings > Captures
and Broadcasts > Captures > **Shortcuts for Create Button** > **Standard / Easy
Screenshots / Easy Video Clips**. Easy Screenshots swaps single-press and hold; Easy
Video Clips puts start/stop recording on the double-press. (documented)

Microsoft does the opposite: **press** and **hold** are two independently configurable
slots, each settable to Take screenshot / Record what happened / Start-Stop recording.
(documented)

Both models are defensible. Presets are easier to explain; slots are more flexible.

For PS4 games running on PS5, where the rich overlay is unavailable, Sony documents raw
button-timing shortcuts as the fallback so muscle memory still yields something: "Single
press the create button to show the create menu. Press and hold the create button to take
a screenshot. Double press the create button to save a video clip of your recent
gameplay." (documented)

**Linux gotcha:** the Xbox Share button is at firmware-dependent byte offsets. SDL's
`SDL_hidapi_xboxone.c` reads it at offset 14 for reports under 44 bytes, 18 at 44 bytes,
28 at 46 bytes, 42 at 60 bytes. Let SDL or the kernel parse it; never hand-parse HID
reports. (documented)

### The rolling capture buffer

PS5 continuously records gameplay so "Save Recent Gameplay" can retroactively keep
anywhere from **the last 15 seconds up to the last 1 hour**. New manual recordings also
cap at 1 hour. (documented)

### Mute: a two-tier panic button

- **Tap** the DualSense mute button: mutes only the pad's own microphone, button glows
  **solid orange**.
- **Hold** it: mutes **all PS5 audio output** - TV speakers, AV receiver, soundbar,
  headphones - and the mic, with the button **pulsing orange** instead of steady, and an
  on-screen confirmation reading "All audio and your microphone are muted." Unmute via
  the button or Control Center > Sound > Turn Off Muting. (documented)

Solid versus pulsing as "partial versus total" is a nice cheap encoding, and the LED is
the only state indicator.

Mic policy also has an anti-hot-mic default: Control Center > Mic > **"Microphone Status
When Logged In"** and **"Microphone Status When Starting Voice Chat or Broadcast"** with
options **Don't Change / Switch to Mute** ("To prevent unintentional hot-mic
situations"). (documented)

The Xbox pad has **no microphone and no mute button** - mute lives on the headset.
(documented)

### Status bits the host can read

From `hid-playstation` (documented): `DS_STATUS1_MIC_MUTE` BIT(2), `DS_STATUS1_MIC_DETECT`
BIT(1), `DS_STATUS1_HP_DETECT` BIT(0).

`HP_DETECT` means the box can know a headset was plugged into the **pad's** 3.5 mm jack
and switch audio routing automatically. That is a real living-room behaviour (late-night
headphone mode) that currently needs a manual step.

### Haptics

- **PS5 system UI has haptics.** Settings > Accessibility > Controllers > **Haptic
  Feedback During Console Navigation**, added 23.02-08.00.00. Requires a Vibration
  Intensity level to be selected. DualSense, DualSense Edge and PSVR2 Sense only.
  Console navigation only, never games. (documented)
- **Xbox's dashboard never rumbles.** Rumble is a game-only channel there.
  (widely-reported)
- **Vibration Intensity** is a system setting with four values: **Strong (Standard) /
  Medium / Weak / Off**, and it scales what games request rather than only turning it
  off. **Trigger Effect Intensity** is a *separate* setting with its own
  Strong/Medium/Weak/Off, because they are different hardware and different accessibility
  needs. (documented)
- DualSense replaces the two eccentric-rotating-mass motors with **voice-coil actuators**
  driven by waveform data. This is exactly why the Linux kernel driver does not support
  them: Sony's own driver author noted adaptive triggers and VCM haptics "require large
  amounts of data and complex data structures" and left them out. What you get through
  `ff_memless` is two 8-bit magnitudes (`motor_left = strong_magnitude/256`,
  `motor_right = weak_magnitude/256`). **UI haptics on Linux will feel like a DualShock,
  not a DualSense. Fine for menu ticks; do not promise more.** (documented)
- "Vibration v2" (enhanced rumble) is firmware-gated: `hid-playstation` requires
  `update_version >= DS_FEATURE_VERSION(2, 21)`; SDL independently gates on firmware
  `>= 0x0224`. Another reason to go through the kernel/SDL rather than raw hidraw.
  (documented)
- Xbox pads have **four** independent motors: two body (left = low frequency, right =
  high frequency) plus one small motor in each trigger. SDL writes them as separate
  bytes; over Bluetooth a 9-byte report `{0x03,0x0F,LT,RT,LF,HF,0xFF,0x00,0xEB}`. Plain
  XInput never exposed the trigger motors, which is why so many PC games have dead
  impulse triggers. Use SDL and you get all four. (documented)

### Lights

- **Five white player LEDs** under the touchpad, exposed via leds-class. Kernel bit
  patterns are symmetric and centred: P1 = BIT(2) (one lit, centre), P2 = BIT(3)|BIT(1),
  P3 = BIT(4)|BIT(2)|BIT(0), P4 = BIT(4)|BIT(3)|BIT(1)|BIT(0), P5 = all five.
  (documented)

  That is a five-segment display sitting on the user's hands. Nothing else in the living
  room can show state that way.

- **RGB lightbar** strips flanking the touchpad, via leds-class-multicolor. The kernel
  deliberately boots them to blue: `dualsense_set_lightbar(ds, 0, 0, 128)`. Gated by
  `DS_OUTPUT_VALID_FLAG1_LIGHTBAR_CONTROL_ENABLE`. (documented)
- **Brightness of Controller Indicators** is a first-class system setting with three
  values: **Bright (Standard) / Medium / Dim**, at Settings > Accessories > Controller
  (General). (documented)
- Pairing signalling: "After the light bar blinks, the player indicator lights up."
  Blink = negotiating, steady = ready. (documented)
- **Ownership conflict to resolve:** Steam and SDL assign a per-player **colour** rather
  than a per-player LED count. SDL's `SetLedsForPlayerIndex` uses Blue, Red, Green, Pink,
  Orange, Teal, White across seven slots, and Steam Input lets Action Sets change the
  lightbar colour mid-game. If couchd also sets the lightbar, they will fight. Decide who
  owns the LED - couchd outside a game, Steam inside one - and hand over explicitly at
  launch/exit, the same way the game-launch pad handoff already works. (documented)
- The Xbox pad has **no lightbar and no player LEDs**; the Xbox button's own light is the
  only indicator. (The 360 pad's four-quadrant ring was dropped for Xbox One onward.)
  Any "the pad tells you things with light" design only works if the household pad is a
  DualSense. (documented)

### Pairing

- **First-time pairing is over the supplied USB cable, not over the air.** Console on,
  plug in, press PS. Sony removed the discovery step entirely for the first pad - the
  cable **is** the pairing gesture. (documented)
- Additional pads: hold **Create + PS** until the lightbar blinks. (documented)
- Player slot assignment uses the **same chord at two different hold lengths**: hold an
  action button + PS for **over 5 seconds** to set the destination slot (lightbar and
  player indicator blink); hold action button + PS for **3 seconds** to switch to an
  already-assigned slot. The blinking confirmation is what makes duration-based bindings
  usable at all. (documented)
- Xbox: a dedicated recessed **Pair** button on the top edge held ~3 s; the Xbox button
  then flashes rapidly. Fast flash = discoverable, slow/steady = connected.
  (widely-reported)
- **A pad is bonded to exactly one host at a time.** Pairing to a PC silently unpairs it
  from the console, because Bluetooth link keys are overwritten. Users hit this constantly
  and assume the pad is broken. (documented)
- Simultaneous limits: Xbox **8** connected controllers (via the proprietary 2.4 GHz Xbox
  Wireless protocol), PS5 **4**. Xbox Wireless and Bluetooth are mutually exclusive on
  the pad. (documented / widely-reported)
- Sony exposes an explicit **Communication Method: Use USB Cable / Use Bluetooth** escape
  hatch, with the note that selecting Bluetooth keeps it on Bluetooth even when a cable is
  attached. (documented)
- Since 25.06-12.00.00 a DualSense can be paired to **up to 4 devices** and switched
  between them from the controller itself. (documented)
- There is a **physical reset pinhole** on the back of the DualSense next to the Sony
  logo: "Use a pin or a similar tool (not included) to press and hold the reset button for
  at least 5 seconds", console powered off and cable unplugged, then reconnect over USB.
  This is the fix for a pad that will not pair and it is genuinely hard to find.
  (documented)

### Battery

- **DualSense reports battery in ten steps, not a percentage.** `hid-playstation`:
  `DS_STATUS0_BATTERY_CAPACITY` is `GENMASK(3,0)`, and capacity is
  `min(battery_data * 10 + 5, 100)`. SDL does the identical maths. So the pad can only
  ever say 5%, 15%, 25% ... 95%, 100%. **Do not render a precise percentage - it will
  jump in 10-point steps and look broken.** (documented)
- Sony's own UI shows **three bars** plus an animated lightning bolt while charging that
  stops animating and shows three bars when full. (documented)
- **Charging state is a 4-bit field with real error values**, not a boolean:
  `DS_STATUS0_CHARGING` = `GENMASK(7,4)`; 0x0 discharging, 0x1 charging, 0x2 full,
  **0xA and 0xB out of range (voltage or temperature fault)**, 0xF charging error. On a
  box in a warm AV cabinet, "pad too warm to charge" is a plausible real state and beats
  silently showing "not charging". (documented)
- The Xbox pad reports only **four** coarse levels; SDL maps firmware 0-3 to 10%, 40%,
  70%, 100%. (documented)
- DualSense carries a **1560 mAh** cell, roughly 3 hours to full, typically 6-12 hours of
  use depending on how hard haptics and triggers are driven - about 56% larger than the
  DualShock 4's cell, with the extra capacity largely eaten by the actuators.
  (widely-reported)
- Both platforms warn early enough to reach a save point. Xbox's threshold is
  widely-reported as roughly 10-20% and is not published. (widely-reported)
- **Pads have their own idle-off timer, separate from the console's.** PS5: Settings >
  System > Power Saving > "Set Time Until Controllers Turn Off" - After 10 Minutes /
  After 30 Minutes / After 60 Minutes / Don't Turn Off. Xbox is a fixed, non-adjustable
  ~15 minutes. (widely-reported)

### The touchpad and sensors nobody uses

`hid-playstation` reports the touchpad as **1920 x 1080 with 2 contact points**, on its
**own evdev node** separate from the gamepad node. Motion is a third node, with
`DS_ACC_RES_PER_G` 8192 and `DS_GYRO_RES_PER_DEG_S` 1024 plus per-axis bias and
sensitivity calibration read from the device. (documented)

A 1920x1080 two-finger absolute trackpad is an excellent text-entry and pointer device
for Kodi - search boxes, scrubbing a film, the on-screen keyboard - without picking up
the phone. Kodi may need explicit configuration to see the separate node.

### Controller disconnect: a certification requirement, and our biggest gap

Console TRC/XR checklists **require** that a game detect the active controller
disconnecting, pause, show a platform-standard reconnect message, and resume cleanly.
Shipping without it fails cert.

- Xbox **XR-115**: "If the player's controller that's driving gameplay is removed during
  gameplay, titles must allow reestablishment of a new active controller (for example,
  'Press A to continue')", via `XUserDeviceAssociationChangedCallback` (GDK) or
  `ControllerPairingChanged` (ERA), or by calling
  `XUserFindControllerForUserWithUiAsync` to raise the system pairing dialog.
  Implementation guidance: "A best practice is to pause gameplay when an active player's
  controller is removed." (documented)
- The 1998 PS1 TRC 18.8 says the same thing more bluntly: "This title enters Pause mode
  if a controller or peripheral becomes connected or disconnected any time after boot",
  recovered by pressing START, and covering extra unused controllers or memory cards on
  the multitap. (documented)
- PS1 TRC 9.1/10.3/10.4 additionally require hot-plug of **any** licensed peripheral at
  **any** time after boot without hanging. (documented)
- Xbox **XR-115** also forbids a second controller hijacking the session: "the title must
  not automatically switch active users to the new user or interrupt the active users'
  experience based on a new signed-in user event." (documented)
- **SDL treats a DualSense as gone after 500 ms of Bluetooth silence** -
  `BLUETOOTH_DISCONNECT_TIMEOUT_MS = 500` in `SDL_hidapi_ps5.c`. That is a concrete
  number for our own detection: shorter produces false positives on a congested 2.4 GHz
  band, much longer and the pause overlay arrives too late to feel like a console.
  (documented)

**PC games mostly do not do this.** A pad dropping mid-game leaves the game running and
the player helpless. couchd is exactly the component that can fill the gap, and it is
the single most console-feeling mundane behaviour available to us.

### Copilot and accessibility input merging

- Xbox **Copilot** merges two physical controllers into one logical controller,
  system-level, works in every game. (documented)
- PS5 **Second Controller for Assistance** (Sept 2023): Settings > Accessibility >
  Controllers > Use Second Controller for Assistance > "Use Assist Controller". Each
  session, press PS on the main pad and pick a user, then PS on the assist pad and pick
  the **same** user. The assist controller is deliberately second-class: **no haptic
  feedback, no adaptive triggers, no mic functions, no custom button assignments**. A
  DualSense Edge can only ever be the main controller. (documented)

  That capability loss is instructive: if you merge two pads at uinput level you hit the
  identical problem - rumble and gyro have to be routed to exactly one physical device.

- Up to **two Access controllers plus one DualSense** can be combined into a single
  virtual controller. (documented)

### System-wide remapping

- PS5: Settings > Accessibility > Controllers > **Custom Button Assignments for DualSense
  Wireless Controller**. Select the button, select the function, then select **Apply**.
  The explicit Apply step means the remap is transactional, not live - a live-applied
  remap can lock you out of the UI you need to undo it. Applies to the whole system
  including the dashboard. (documented)
- Xbox: system-level remapping applies across all games, configured through the **Xbox
  Accessories app** rather than Settings - which is a real discoverability failure. It
  stores several named profiles per controller and can bind the share button's tap,
  double-tap and hold to different actions. (widely-reported)

Steam Input covers remapping inside games. **Nothing covers it inside Kodi.**

### Firmware

- PS5 pad firmware updates via the console over **USB cable only**, at Settings >
  Accessories > Controller (General) > DualSense Wireless Controller Device Software.
  Old firmware means no vibration v2. There is no Linux path; the practical options are a
  real PS5 or Sony's Windows-only updater. Flag it if haptics feel wrong. (documented)
- Xbox pad firmware updates have retroactively added features to already-sold pads
  (notably Bluetooth low-latency to older Xbox One pads in 2021), which is why two
  identical-looking pads can behave differently. No Linux path. (widely-reported)

### Dynamic Latency Input (and why the console is not magic)

Microsoft's GDK documents DLI: the pad's report rate adjusts on the fly to deliver input
just before the game asks for it, as little as 2 ms rather than a fixed 8 ms. It keeps an
internal confidence value and **disables itself if the game's read cadence is
inconsistent**, and it is **hard-capped at 125 Hz** - attempting a higher cadence turns
DLI off. Xbox console only, never implemented on PC. (documented)

This debunks a common assumption: the console is not polling at some enormous rate. It is
capped at 125 Hz and *synchronised*. **Steady frame pacing matters more than raw polling
rate.**

### What this would mean for couch

- **Already done.** Gesture vocabulary and bindings; patched `bluetooth.ko` for the
  L2CAP reconnect bug; game-launch pad handoff; steam-input-guard; Steam per-pad gyro
  calibration.
- **Cheap, highest value.** UI haptics: `ff_memless` is already bound. A tick on focus
  change, a heavier bump at end-of-row, a double-buzz on error. Ship it **off by default**
  with a four-step intensity setting including a real Off, because the two platforms
  disagree about whether this is even a good idea.
- **Cheap.** Battery as a three-bar indicator, never a percentage. Handle charging states
  0xA/0xB as "pad too warm/cold to charge".
- **Cheap.** Toast on pad connect/disconnect (TV and phone), plus a repeating low-battery
  warning that fires **during a full-screen Steam game**, not only in Kodi - which is the
  harder half.
- **Cheap.** Drive the lightbar: colour = current mode (Kodi vs game), pulse on low
  battery, and **dim it during films** alongside the WiZ bulbs, since the pad is otherwise
  a glowing object in a dark room. Add the three-step brightness setting.
- **Cheap.** Use the five player LEDs as a second display - loading chase, battery gauge,
  mute indicator.
- **Cheap.** Auto-switch audio routing on `HP_DETECT` when headphones go into the pad's
  jack.
- **Cheap.** Pad idle-disconnect after N minutes with no input while video plays. It saves
  battery and - usefully - makes "pad connects" a meaningful event again for tv-waker,
  which a permanently-connected pad prevents.
- **Cheap.** Document the pairing chords (Create + PS; reset pinhole; USB-first) in the
  House/settings screen. That is most of the battle for a pad that will not pair.
- **Project, and the flagship.** Controller-disconnect handling: on losing the active pad,
  freeze the game via the existing game-pids machinery and show a full-screen "Reconnect
  your controller - press PS to continue" overlay; resume on re-association. Use SDL's
  500 ms as the detection window. No PC game does this. couchd can.
- **Project.** Use the touchpad as a real pointer/text-entry device in Kodi.
- **Project.** A system-wide remap layer that applies to the shell as well as games, in
  the existing single config file both stacks read. Copy the transactional **Apply** step.
- **Resolve.** Lightbar ownership between couchd and Steam Input, with an explicit handoff
  at launch/exit.
- **Not worth it.** Adaptive triggers and voice-coil haptics from the shell - out of scope
  for the in-tree driver by design. Copilot-style input merging - non-trivial, and better
  named as a known gap than half-built.
---

## 8. Power, standby, idle and boot

Both consoles treat "off" as a spectrum, and both spend real engineering on making the
low-power state still useful.

### PS5 rest mode

- Rest mode is a **true suspend that keeps the running game alive**, not a fast reboot.
  Sony's framing: it "keeps the system software and open video games in memory". **Only
  one** title is held (unlike Xbox's three). On wake you land back exactly where you
  were, with no reload. (documented)
- Entered from Control Center: PS > Power > **"Enter Rest Mode" / "Turn Off PS5" /
  "Restart PS5"**. Restart is a distinct third option that "turns off completely and then
  turns on again" - deliberately not buried in a settings tree. (documented)
- Redundant physical paths, with an asymmetry worth copying: **a tap of the power button
  sleeps; a hold powers off** ("until your console beeps"). Turn on from rest or off: PS
  button on a paired controller, or the console's power button. (documented)

**"Features Available in Rest Mode"** is three explicit toggles rather than an opaque
standby switch (documented), at Settings > System > Power Saving:

| Toggle | Options | What it gates |
|---|---|---|
| Supply Power to USB Ports | **Off / 3 Hours / Always** (plus Adaptive on CFI-2000/7000) | Pad charging overnight |
| Stay Connected to the Internet | on/off | Game and app downloads, pre-orders/pre-loads, automatic system software updates, PS Plus cloud save upload, Remote Play |
| Enable Turning On PS5 from Network | on/off | PS App wake, Remote Play wake |

Sony states the cost plainly: "If you enable any of these features, your PS5 console
doesn't automatically lower power consumption below 0.5 W when entering rest mode."

The **3 Hours** option is the interesting one - a bounded grace period when "always"
wastes power and "never" breaks the morning. Adaptive "adjusts to the remaining battery
level of the controller you connected before your console enters rest mode."

**Idle timers are split by activity type** (documented), Settings > System > Power Saving
> "Set Time Until PS5 Enters Rest Mode", two independent settings:

- **While Playing Games**: 20 minutes up to 5 hours, or "Don't Put in Rest Mode" ("your
  PS5 console stays turned on, and consumes more power").
- **During Media Playback**: **1 hour** up to 5 hours, or "Don't Put in Rest Mode".
- Intermediate steps: 1, 2, 3, 5 hours.

A film has no controller input, so it gets a longer floor. That split is exactly what a
Kodi box needs and is a common omission.

Before auto-sleeping, a dismissible warning toast appears with a countdown; any
controller input cancels it. (widely-reported - it is a common support search)

PS4 additionally exposed a toggle the PS5 does not: **"Keep Application Suspended"**.
Making the hold-the-game promise optional is the right call when suspend is unreliable.
(documented)

**Power Saver for Games** (25.06-12.00.00) is an opt-in per-title performance cap; VR is
unavailable while it is active, and a Power Saver icon appears next to the game in the
Switcher. (documented, though the exact scaling behaviour is uncertain)

### PS5 power draw and timings

- Rest mode: roughly **0.35 W** with everything off; about **1.3-1.5 W** with network
  standby up (Sony's spec and Eurogamer's measurement agree on ~1.3 W); up to ~3.2 W
  while charging a pad. (widely-reported)
- Cold boot: Sony claims ready for use in **under 14 seconds**. Rest-mode resume: community
  measurements range widely - Push Square ~5 s, Dave Lee ~9 s, Tom Warren ~14 s. The
  variance is real and depends on what was suspended. (widely-reported)

### PS5 power indicator LED

A documented five-plus-state vocabulary readable across a dark room with the TV off
(documented):

| State | Meaning |
|---|---|
| Blue then transitioning to white | Powering on |
| Solid white | On |
| Blinking white then off | Powering off |
| Blinking orange (may look amber) | Entering rest mode |
| Solid orange | In rest mode |
| Pulsing orange | Downloading/installing in rest mode (widely-reported, not in Sony's table) |
| Blinking white that never resolves, solid blue, or blinking blue | Console error / frozen. Documented remedy: unplug, wait 3 minutes, replug |
| No light | Off |
| Pulsing red | Overheating - **PS4 only**; Sony lists no thermal colour for PS5, so the on-screen message is the only channel |

Brightness: Settings > System > Beep and Light > **Dim / Medium / Bright**, added in
24.02-09.00.00.

### Xbox power modes

Two modes with plain-language names, under one question: **"Choose how this console turns
off"**. Settings > General > Power options. Options are **Sleep** and **Shutdown (energy
saving)**, renamed from the Xbox One era's "Instant-on" and "Energy-saving" because the
old names did not say what they did. (documented)

The cost gap is enormous (documented):

| Mode | Draw | Boot | Remote wake |
|---|---|---|---|
| Sleep | **10-15 W** | under 5 s | Yes |
| Shutdown (energy saving) | **0.5 W** | ~15-20 s | **No** |

Microsoft's own figure: Shutdown uses "up to 20X" less power than Sleep. Series X drew
close to 30 W in Instant-on at launch before firmware reduced it.

Microsoft switched the out-of-box default to energy-saving around March 2022, and in
**January 2023 pushed a one-time update that forcibly switched existing consoles from
Sleep to Shutdown** - changing a setting the user had chosen. Users could switch back.
Microsoft's justification: it "does not affect performance, gameplay, or the console's
ability to receive overnight updates". (documented)

**Active Hours** is the hybrid, and it is the single most stealable item in this section.
Settings > General > Power options > (Sleep selected) > **Customize power options** >
**"Adjust active hours"**. A dropdown offers an automatic mode where the schedule is
**learned from when the console was previously used**, and "Manually", where you set
"Start active hours" and "End active hours". Inside active hours the console sits at
10-15 W with fast wake and remote wake available; outside them it drops to 0.5 W with a
slower boot. (documented)

**Customize power options** also holds "turn off after N hours idle" (roughly "1 hour of
inactivity" / "6 hours of inactivity" / "Don't turn off") and **"turn off external
storage when the console is off"** - with the documented, deliberate tradeoff that games
on external drives are then not kept updated. (documented / widely-reported for the exact
values)

That last one is pointed: powering external storage down while idle is precisely the
class of behaviour we have been fighting on disk1. Xbox's answer is to make it an
explicit user-visible policy rather than a surprise.

### The maintenance window

Even in full **Shutdown at 0.5 W**, the console wakes itself once every 24 hours.
Microsoft's wording: "the console will wake, check for updates and download them during
the maintenance window (if available), shutting down again after the download completes.
This occurs once every 24 hours." The window is **2:00 AM - 6:00 AM local**. (documented)

Since **11 January 2023** the exact moment inside that window is chosen using **regional
carbon-intensity data**, so the download runs when the local grid is greenest, rather
than at a random time in the window. Marketed as the first carbon-aware console.
(documented)

### Xbox boot times as a product promise

Sleep: **under 5 seconds** from off to signed in. Shutdown: ~15 s (some measurements
~20 s), and couch-to-controlling-a-character in about 20 s total with Quick Resume. The
new dashboard claims "50% faster" boot on Series X|S. Microsoft treated 5 seconds of
splash animation as a performance regression worth engineering away. (widely-reported /
documented)

### Quick Resume

- Snapshots a game's RAM **to SSD**, so it survives a **full power-down**, not merely
  sleep. The snapshot is written when you launch a different game or power off. Reported
  budget: up to **13.5 GB per title** against roughly **40 GB reserved** on the drive.
  (widely-reported)
- Holds roughly **three** modern Series X|S titles and more backward-compatible ones,
  because it is a **byte budget, not a slot count**. At least one reviewer got six
  suspended at once. (widely-reported)
- Presented as an ordinary group of tiles called **"Quick Resume"** inside My games &
  apps - not as a special mode, dialog or badge. Suspended titles look like any other
  tile. (documented)
- **Explicit eviction**: Menu > Quit / "Remove from Quick Resume" on the tile "will close
  the game app entirely and free up the system slot". Next launch is a cold boot.
  (widely-reported)
- **Per-game disable** (April 2026), reachable from two places: More options on a tile in
  the Quick Resume group, or Manage game and add-ons > Quick Resume settings. Aimed at
  online titles that behave badly after long suspension. (documented)
- **Pinning up to two** games so they are never evicted. **(folklore - appears in
  secondary coverage only; could not be confirmed against a Microsoft page.)**
- Online behaviour is explicitly unspecified and left to the developer. No network
  connection is maintained while suspended; the game sees a resumed process with a dead
  socket. "Some games may allow you to jump back in where you left off, but that's rare."
  Always-online titles whose server session timed out cannot be resumed and force-restart;
  users report login error loops when it is attempted anyway. (documented)
- Snapshots are invalidated when the game receives a title update. (widely-reported)
- Resume takes roughly 5-10 seconds regardless of how long a game has been suspended.
  (widely-reported)

### Certification's numbers for suspend

Xbox certification defines exactly two ways a game gets suspended, and tests both,
verbatim across test cases 001-02, 003-18, 052-02, 074-03, 074-04 (documented):

> "On retail consoles, a game will be suspended under the following conditions: When the
> console enters Connected Standby by being turned off with the power mode set to
> Instant-on. When the game remains out of focus for **ten minutes**. For example,
> launching an application such as Settings and keeping it in focus for ten minutes."

Once suspend is signalled, a game has **about 1 second** to write its state before the OS
terminates it (Xbox One ERA Process Lifetime Management). XR-001 001-02 fail example:
"The game is terminated as a result of a failure to suspend." (widely-reported for the
1 s figure, documented for the fail example)

**On resume, three different behaviours are all acceptable** (documented), which is
liberating:

- resumes and "the user can immediately continue from their last gameplay location";
- "the user is prompted whether they want to resume from their last gameplay location";
- "returns to a previous menu or initial interactive state, however the user can load
  their last save location".

After suspend during online play, returning to a previous menu is an explicit **pass**.
The **fail** is: "The game resumes from suspend and the user is unable to load their last
save location."

You do not have to restore perfectly. You must never lose the ability to resume.

PlayStation has an equivalent requirement: suspend/resume certification uses a
deliberately long rest-mode dwell, after which the application must wake with all areas
and game modes accessible and must not hang. Sony's modern TRC is confidential licensee
material, and its specifics are deliberately not reproduced in this document.

### Unclean shutdown

Losing power during rest mode is treated as a filesystem crash. On next boot the console
displays "Repairing console storage..." or "Rebuilding database...", which can take from
a few minutes to over an hour depending on how much data is on the SSD. Saves normally
survive; unsaved progress in the suspended game is lost. Sony's guidance is explicit: "do
not disconnect the power cable in rest mode." (widely-reported)

### The rest-mode defect, as a warning

For months after launch, PS5 consoles crashed on wake or refused to wake - console
unresponsive to the PS button, orange light stuck on, or waking and immediately
crashing. Reported from November 2020 and still being written about six months later.
Sony's stopgap advice was to **disable rest-mode downloads entirely**. (widely-reported)

Suspend/resume on Linux with an AMD GPU plus a DP-to-HDMI adapter plus a USB storage
stack is exactly this class of thing. If we ship suspend, we ship a watchdog.

### The transition itself

Neither console shows a "sleeping..." or "resuming..." technical state. The transition is
either instant or covered by an animation. Neither shows a desktop, a window manager, or
a loading spinner labelled with a subsystem. The only status surface is the external LED.
(widely-reported)

### What this would mean for couch

- **Already done.** tv-waker / tv-waker-webos, light-watch, the couch-4k120 pin,
  Wake-on-LAN potential, game-pids suspend machinery.
- **Cheap.** Two idle timers, split the Sony way: a shorter one at the home screen, a
  longer one during media playback, plus "never". couchd already sees Kodi's
  OnPlay/OnStop, so it can hold off suspend during playback. **Kodi's own idle timer
  counts input, not playback state** - which is almost certainly a live bug class here.
- **Cheap.** A 30-second "going to sleep" toast with a countdown, cancellable by any
  input, pushed to both the TV and the phone. Kodi's screensaver just appears.
- **Cheap.** Name our power modes for what they do, and state the tradeoffs as bluntly as
  Microsoft does. Logind `HandlePowerKey=suspend` on short press, ATX hold as the
  emergency, plus an audible beep on power actions.
- **Cheap.** Put **Restart** in the power menu as a first-class option, not in a settings
  tree.
- **Cheap.** A three-hour bounded USB port power window, or the equivalent - the pattern
  generalises far beyond charging.
- **Cheap.** Defer suspend while a Steam download is actively writing, or pause it
  cleanly first, given disk1's documented dropout history under sustained write load.
- **Cheap.** A single unambiguous state chip in the phone app (Off / Waking / Ready /
  Downloading / Error) as our substitute for the chassis LED. The phone can be the status
  light, and it works when the TV is off.
- **Project, highest value in this section.** The overnight maintenance window:
  `rtcwake` or a systemd timer with `WakeSystem=true` boots the box at, say, 03:30, runs
  Steam depot updates plus apt/flatpak plus Jellyfin/Bazarr scans plus the disk-monitor
  pass, then suspends again. The user never sees it. This is precisely the console
  behaviour that makes a machine feel maintained rather than maintaining.
- **Project.** Learned Active Hours: stay in a fast-wake state during the hours the box
  is actually used, power down fully outside them, with a manual override for the
  all-weekend-session case. couchd already has usage history.
- **Project.** Hold **one** Steam game suspended and make "resume last game" the default
  action on wake. One is the honest limit; the console lesson is to budget by RSS, not by
  a slot count, and to expose a per-title "never suspend" flag for anything with a
  heartbeat. Suspend-to-disk (`suspend-then-hibernate`) is the closer analogue to Quick
  Resume and would survive the unexplained 5 Aug idle freeze.
- **Project.** Make resume look like nothing happened. On Linux that means DPMS
  re-negotiation on the DP-to-HDMI adapter, X11 redraw, and the known hazard that **Kodi
  enumerates display modes once at startup**. Hold a black or branded frame over the ugly
  part, and have couchd force a clean restart if no frame is rendered N seconds after a
  resume request.
- **Charm, low priority.** Carbon-aware scheduling. The UK has a free public carbon
  intensity API; picking the lowest-intensity half-hour in the maintenance window is a
  shell script.
- **Measure.** Time-to-interactive from a cold TV is the metric that decides whether the
  room feels like a console. Target: under 5 s from S3 with Kodi already running, under
  20 s cold. Also measure actual idle draw - a box awake at the Kodi home screen is
  probably worse than Xbox's 10-15 W Sleep, which is the strongest argument for actually
  implementing suspend.
- **Not worth it.** Matching 0.5 W. Multi-game Quick Resume.

---

## 9. Background work: downloads, updates, and not making people wait

### The split that matters: download is not install

Both platforms separate fetching from applying, and say why.

- PS5, Settings > Saved Data and Game/App Settings > **Automatic Updates**:
  **"Auto-Download"** and **"Auto-Install in Rest Mode"** are separate toggles. Sony:
  "When you don't want to close your suspended game, only turn on Auto-Download. Only the
  download is automatic in rest mode. When you resume your game, you can choose whether or
  not to install the update." (documented)
- System software has the same pair at Settings > System > System Software > System
  Software Update and Settings: **"Download Update Files Automatically"** and **"Install
  Update Files Automatically"**. The install happens in rest mode, so the user meets an
  already-updated console. Sony also notes: "There may be times when an update needs your
  approval." (documented)
- Xbox, Settings > System > Updates: **"Keep my console up to date"** and **"Keep my games
  & apps up to date"** - one for the OS and one for content, so you can freeze one without
  freezing the other. Unticking the latter means you are notified of an update **only when
  you launch that game**, and can choose "update now" or "later". (documented)

That last fallback is the important bit: **a game that will not start because it is
silently patching is the worst possible living-room experience.**

### Downloads are throttled during gameplay, with an escape hatch

Xbox deliberately reserves part of the connection for gameplay traffic. A March 2021
update added a **"suspend in queue"** checkbox: from the download queue you can suspend
the running game so the download gets full bandwidth, **without quitting**, because Quick
Resume brings it back. (documented)

There is **no user-facing bandwidth cap** on Xbox. The console decides. The only user
controls are which downloads run, whether they run automatically, and suspending the
running game. Contrast Steam, which exposes a numeric KB/s limit and a scheduled window.
(widely-reported)

The lesson is a decision, not a mechanism: most users should never see the number. Pick a
sane cap automatically and hide it behind an advanced toggle.

### Updates in the low-power state, and how they fail

Xbox installs system and game updates while in the low-power Shutdown state, not only in
Sleep - but reporting is candid that updates "sometimes stop downloading after switching
the console off, leaving you with a half-downloaded update", and recommends checking
manually. Games on **external storage never update in Shutdown** because storage is
powered down. (widely-reported)

**Silent partial work is worse than no work.** That is the same lesson as the
disk-monitor checks that had never once fired.

### Games playable before the download completes

- Xbox **XR-034 / test 034-01 Streaming Installation**. Pass: "Provides gameplay
  experience (tutorial, first level, quick multiplayer match)". Fail: "Only progress bar,
  videos/images, main menu only, or non-interactive experience." (documented)
- PlayStation has an equivalent streaming-installation requirement: a capped initial
  payload that must contain gameplay representative of the application, no blocking of
  progress while the rest downloads, no hang when the player outruns it, and newly
  downloaded chunks usable **without rebooting the application**. (widely-reported)

Steam has no equivalent for the vast majority of titles. On our box, downloaded means
downloaded - which is worth stating so expectations are set.

### Progress lives on the object

Both shells overlay progress on the game's own tile - a ring or bar plus percentage -
with a dedicated queue view as the secondary path. Xbox had a bug era where tiles flashed
repeatedly during install/update, and it was treated as a defect precisely because the
tile is the primary progress surface. (widely-reported)

### DLC and add-ons must not require a relaunch

Xbox **XR-123**: "Titles that offer downloadable content (DLC) must allow users to
download/unlock and use the content without having to terminate and relaunch the game."
Test 123-01 explicitly repeats the scenario with the download completing while the game
is constrained, and again while suspended, using both suspend methods. A prompt to return
to the main menu to load the DLC is an accepted **pass**; requiring a restart is a
**fail**. (documented)

### Downloads survive interruption and never cancel on power-off

Neither console cancels an in-flight download when the user presses power. It is handed
to the background scheduler: continued in rest/sleep, or resumed at the next
maintenance-window wake in Shutdown. Downloads also resume automatically across reboots
and network drops without user action. (widely-reported)

Failed downloads report as a completed-with-error job **in the notification list, never
as a modal**, and are resumable, with a red exclamation badge. On a transient network drop
the download pauses with the elapsed timer still counting and resumes on its own.
(documented / widely-reported)

The distinction between "paused, retrying" and "failed, needs you" is the whole UX.

### Update UI is deliberately ugly

Full-screen, unskippable, numeric percentage, flat background, "do not turn off"
warning, no animation, no music. If the box ever shows a TTY, a plymouth-less boot, an X
cursor on grey, or a Kodi splash sitting behind an apt run, the illusion breaks.
(widely-reported)

### Rate limits as a user-visible event

Xbox **XR-132 Service Access Limitations** caps service calls, with certification failing
on "red results in report or sustain limit exceeded by **10x** (e.g., 3000 calls if limit
is 300 per 300 seconds)", and **XR-133 Local Storage Write Limitations** caps a title at
**1 GiB of writes to persistent or temporary local storage in any rolling 5-minute
window**. In both cases the visible symptom of abuse is **a system toast shown to the
user**, and triggering it is itself a certification failure. (documented)

The philosophy: misbehaviour by a component is shown to the user, on the assumption the
user will report it, rather than swallowed into a log nobody reads.

### The "rest mode downloads are faster" claim

**Folklore.** The plausible mechanism (no game competing for CPU, network and SSD) is
real, but Sony has never documented a rest-mode download speed-up. Do not advertise a
speed-up we cannot measure. What *is* real and worth copying is that background work is
scheduled when nothing is contending for the disk.

### What this would mean for couch

- **Cheap.** Split fetch from apply for Steam: pull depot content overnight, stage the
  install, and never block a resumed session on an in-progress patch. Steam's own setting
  is coarser than this and couchd can enforce the rule.
- **Cheap.** "Update available (2.1 GB) - Play anyway / Update first" at launch, where
  Steam permits it.
- **Cheap.** Progress on the poster, not in a separate tab, for both Steam installs and
  arr/Jellyseerr requests.
- **Cheap.** Failed background jobs land in a list with a badge, never in a dialog over a
  playing film. Distinguish "paused, retrying" from "failed, needs you".
- **Cheap.** An on-screen record of what overnight work actually completed. Never leave
  partial work silent.
- **Cheap.** A poll budget for the phone app hitting couchd/Kodi/Jellyfin, with a log
  warning when a client exceeds it, so a runaway tab cannot hammer the box.
- **Cheap.** A write-rate budget monitor that **names the offending process** (Kodi
  texture cache, Jellyfin sync, torrent recheck), not just the disk. That is precisely the
  guard-rail that would have surfaced the disk1 issue earlier.
- **Project, and genuinely better than Steam.** The suspend-in-queue escape hatch: a
  phone-remote button that suspends the running game, lets a download finish at full
  speed, and resumes it. Steam has nothing like it.
- **Project.** Schedule apt/flatpak/Steam updates into the maintenance window (section 8)
  so an OS update is never a thing the user waits for at the start of a session.
- **Rule.** Any user-visible maintenance is one full-screen branded progress screen with
  a real percentage and a do-not-power-off warning. Nothing else.

---

## 10. Storage

### PS5

- Settings > **Storage** covers Console Storage, M.2 SSD Storage and USB Extended
  Storage, and Sony publishes the **capability matrix** rather than a list (documented):
  - PS5 games **can be stored on** USB extended storage but **cannot be played from it** -
    they must be copied back to internal.
  - PS4 games **can** be played directly from USB extended.
  - Save data goes to cloud only (or USB for PS4 saves).
  - Captures go **one way** to a USB drive: "Media can't be copied from the USB drive to
    your console storage."
- USB extended storage constraints: **250 GB minimum, 8 TB maximum, SuperSpeed USB 5 Gbps
  or later, no hubs, only one connected at a time**. (documented)
- Cloud saves: **100 GB PS5 + 100 GB PS4, max 1000 PS4 files**. (documented)
- Version 24.06-10.00.00 added "a friendly recommendation about your storage space that
  you'll sometimes see in Settings > Storage" - a proactive nudge, not just a bar.
  (documented)
- Safe removal: Settings > Storage > USB Extended Storage > **Safely Remove from PS5**, or
  "make sure your console's power indicator is completely off before disconnecting".
  Sony's warning for improper removal: "there may be data loss, corruption, or damage to
  your console or USB drive." Recognition failures get their own codes: **CE-100006-7**
  "The external storage drive cannot be recognized." and **CE-109737-7** "The USB storage
  device cannot be recognized." (documented)
- Storage exhaustion is split by pool: **CE-107872-5** "There is not enough free space on
  the console storage." versus **CE-100028-1** "There is not enough free space on the
  SSD." Widely reported (not Sony-documented): installs need roughly **2x the package
  size** free because the download is staged then unpacked, so a 50 GB game can fail with
  ~60 GB free. (documented / widely-reported)

### Xbox

- **Optimized for Xbox Series X|S titles are hard-restricted** to the internal SSD or the
  official expansion card and cannot run from USB. USB can store them (cold storage) and
  can run older-generation titles. (documented)
- Content installs commonly fail with **0x80070070** (insufficient disk space); community
  guidance is again to keep roughly **2x the game size** free. A named message,
  **"Your XBOX is almost full"**, is one of six documented update-failure situations.
  (documented / widely-reported)
- The "free up space" flow is offered **at the point of failure**: "If there isn't enough
  space when you try installing a new game or app, we have tips to help you make room so
  you can install it right away." (documented)
- **Persistent Local Storage is a guaranteed allocation**: "The system ensures that the
  space is allocated prior to the title being allowed to launch. If insufficient hard
  drive space is available, the user is prompted to free up space to allow the title to
  run." There is an API, `XPersistentLocalStoragePromptUserForSpaceAsync`, whose entire
  job is to raise the system "free up space" UI mid-game. **The system never
  auto-deletes anything in PLS; only the user can.** Temp storage (T:) is 2 GB and
  survives suspend/resume including Quick Resume. (documented)

That is the best idea in this section: **check preconditions at launch and prompt once,
rather than letting a 40-minute session die at the save point.**

### Certification's storage rules

- PlayStation has equivalent save-data requirements: a per-user cap on total save size;
  on an out-of-space save the application must show the **system's** own message rather
  than inventing one, then recover to a state where the save can be retried without
  losing progress and without the user restarting the application; and progress may not
  be stored in download or temporary data areas, with the save required to survive
  deleting the application **including its download data** and reinstalling.
  (widely-reported)
- PS1 TRC 12.3: worst-case space must be **reserved up front**, with a worked example (a
  game needing 5 blocks at stage 20 but 2 at the start must reserve 5), and 12.3.1: "The
  title lets the user know the necessary number of blocks required to save the title
  **before** saving or overwriting." (documented)
- PS1 TRC 12.12.3: storage must be checked **immediately before every save and load** -
  present, formatted, enough free blocks - but the check may be skipped if the app already
  knows, and **must be redone if the media changed**. 12.6.2 adds that free space must be
  counted in real free blocks, not files, and "Be sure to retry several times."
  (documented)
- PS1 TRC 12.12.6.1, and this one is written for us: "The user is able to select the
  Memory Card slot to be used when saving and loading. **The application does not make a
  decision automatically.** Avoid situations in which data is automatically saved to the
  Memory Card in Memory Card slot 2 because the Memory Card in Memory Card slot 1 is not
  formatted (it is either missing or cannot be used for some reason). This is because it
  can become quite complicated to determine when data should be saved... and programming
  mistakes can easily occur." (documented)

  **Never silently fail over from disk1 to disk2 for writes.** That is how content ends up
  split unpredictably across two enclosures.

- PS1 TRC 12.5.1 / 12.5.2, on formatting: auto-formatting is **forbidden**; do not even
  display a "format" option button "since this may cause users to inadvertently erase all
  the existing data"; the prompt must be explicit ("Memory Card is unformatted. Do you
  want to format? Yes? or No?"); and **the default option should be not to format** -
  explicitly because line noise can make a good card look unformatted. (documented)

  A transient link reset must never trigger anything destructive. That is exactly the
  disk1 situation.

- PS1 TRC 12.8.1: a **"Delete All"** function is banned outright as an in-game function,
  "For the user, the 'Delete All' function is equivalent to Memory Card formatting."
  (documented)

### What this would mean for couch

- **Already done.** Two USB media disks; a disk-monitor with four bugs fixed on 9 Aug; a
  Discord webhook for alerts.
- **Cheap.** A storage page that states plainly what each disk can and cannot hold, plus a
  proactive nudge when one fills. The "can be stored but not played from here" distinction
  is literally our situation with games on the slow disk.
- **Cheap.** Pre-flight free-space check against **2x the download size**, before the
  download starts rather than at 94%.
- **Cheap.** Precondition checks at launch, with an in-place uninstall picker offered at
  the moment of failure rather than a bare error.
- **Cheap.** Verify the mount and free bytes immediately before writing, invalidate that
  knowledge on any device event, and never trust a cached figure. `sdX` letters swap
  between boots on this box.
- **Cheap.** State that saves are kept when uninstalling. That single sentence is what
  makes people willing to free space.
- **Cheap.** Audit where couchd and skin.couch actually put user state, and move anything
  that matters out of cache directories that a reinstall would clear.
- **Policy to adopt.** Follow the Xbox model: fast internal storage for anything
  performance-sensitive, USB as the archive you copy from. Do not run Proton games off
  disk1. Consider refusing to launch a game whose install path is on a degraded disk, and
  offering to move it, rather than letting it crash at a load boundary.
- **Rule.** Never auto-fail-over between disks. Never auto-format. Never offer a one-tap
  "clear everything" on a phone screen where a mis-tap can hit it. No destructive action
  without a confirm whose default is "no", naming exactly what will go.
- **Project.** A boot-time integrity pass with a visible, cancellable progress screen
  after an unclean shutdown, the way both consoles rebuild. Note the 9 Aug lesson stands:
  a clean fsck cannot see zeroed file content, so the real equivalent of "rebuild
  database" here is a torrent recheck.
---

## 11. Display and audio output

Both platforms expose far more of the HDMI plumbing than a PC desktop does, and both do
it with a simple front page and an Advanced section behind it.

### PS5 Screen and Video > Video Output

The full documented tree (documented):

- **Current Video Output Signal** - resolution, colour format, HDCP version. Read-only.
- **Information for the Connected HDMI Device** - per-frequency HDR and VRR support.
  Read-only, redesigned in 2023.
- **Resolution** - Automatic / 1080p / 1440p / 2160p
- **Test 1440p Output** - tests SDR and HDR at 60 and 120 Hz, and VRR
- **Allow 8K Output** - CFI-7000 only, needs DSC
- **Enhance Image Quality for PS4 Games** - CFI-7000 only, needs a 4K or 1440p screen
- **VRR**, with a sub-toggle **"Apply to Unsupported Games"**
- **120 Hz Output**
- **ALLM**
- **Video Transfer Rate** - Auto / -1 / -2, **with the exact output modes each level
  sacrifices spelled out**
- **HDR** - Always On / On When Supported / Off
- **Adjust HDR**
- **Deep Color Output**
- **RGB Range**
- **Enhance PSSR Image Quality** - CFI-7000 only

Screen > **Adjust Display Area** handles overscan.

Sony documents that **ALLM cannot be fully disabled while VRR is on**, rather than hiding
the interaction.

**HDR is on by default, and the note that it must be turned off is buried in the
backward-compatibility page, not the HDR page**: "HDR is automatically switched on for
PS5 consoles. To turn off HDR, go to Settings > Screen and Video > Video Output > HDR and
select Off." Separately, enabling **Invert Colors** forcibly disables HDR. (documented)

That is exactly the trap this box has already hit with Kodi-on-X11 tonemapping.

### Xbox TV & display options

A three-item simple page - **Resolution, Refresh rate, Device control** - with everything
else behind **Advanced**: Video modes, Video fidelity & overscan, 4K TV details. "Calibrate
HDR for games" sits under a Setup grouping. (documented)

**Advanced > Video modes** is a list of explicit capability checkboxes, and **unsupported
ones are greyed out rather than hidden** (documented):

- Allow 50Hz
- **Allow 24Hz**
- Allow auto-low latency mode
- Allow variable refresh rate
- Allow 4K
- Allow HDR10
- Allow YCC 4:2:2
- Allow Dolby Vision
- Auto HDR

Greying-out rather than hiding is the key detail: it tells the user the feature exists and
that their TV or cable is the limit. Given our DP-to-HDMI 2.1 adapter chain, a screen that
said "VRR: unavailable on this link" would have saved hours.

**Allow 24Hz** exists as a separate toggle so films output at their native cadence. Kodi's
"adjust display refresh rate" does the same job but is buried in Player settings where
nobody finds it. (documented)

**Advanced > Video fidelity** exposes colour depth - 24 bpp (8-bit), 30 bpp (10-bit),
36 bpp (12-bit) - and colour space: **Standard** (limited range, correct for TVs) or **PC
RGB** (full range). Colour depth applies to SDR only; the console switches automatically
for HDR. Getting the colour space wrong produces crushed blacks that people misdiagnose as
a TV fault. (documented)

**"Calibrate HDR for games"** is a once-per-console guided wizard, deliberately not
per-game. You set the TV's tone mapping to off (or HGiG) and follow on-screen test
patterns. FlatpanelsHD: doing it once from the system menu means "you avoid having to do
HDR calibration for each individual game (that's the idea, at least)". (documented)

### HDMI-CEC, exposed as directions rather than a single switch

Both platforms split CEC into separately refusable directions.

- PS5, Settings > System > **HDMI** (arrived 14 April 2021): **Enable HDMI Device Link**
  (master), **Enable One-Touch Play** (PS5 powering on turns the TV on and switches
  input), **Enable Power Off Link** (turning the TV off puts the PS5 into rest mode),
  **Enable HDCP**. TV compatibility was patchy at launch. (documented)
- Xbox, Settings > General > TV & display options > **TV & A/V power options** > **Device
  control**: "Console turns on other devices", "Console turns off other devices", "Console
  sends volume commands", "Other devices can turn console off". (documented)

Note the naming: Xbox calls it "Device control" in the simple view and "TV & A/V power
options" in the detailed one, because **"CEC" means nothing to users**.

Two documented failure modes worth knowing: the console waking itself when an unrelated
device sends a CEC signal, and dropping to rest mode mid-game when the TV is toggled. Both
are common enough that Sony's own community pages lead with "turn off Enable HDMI Device
Link" as the fix for "my PS5 turns on by itself". Community consensus is that the inbound
"other devices can turn console off" direction should default **off**. (widely-reported)

### The FreeSync trap

Xbox defaults to AMD FreeSync when a TV advertises both FreeSync and HDMI VRR, and **this
silently breaks Dolby Vision**: FreeSync occupies an additional EDID block, "effectively
Dolby Vision's space", so the console concludes the TV has no DV support. The fix is to
disable FreeSync on the TV and use HDMI VRR. (documented, FlatpanelsHD)

This is directly relevant to the RX 9070 XT + LG C5 chain, and it is exactly the kind of
silent capability loss that produces a false "it works".

### The 120 Hz double-image trap

When set to 120 Hz output, the Xbox outputs **everything** at 120 Hz including 60fps
content (except Dolby Vision, which drops to 60 Hz). FlatpanelsHD notes this can cause a
double-image artefact on displays using black frame insertion or scanning backlights, and
recommends running at 60 Hz and raising it manually only for genuine 120 Hz modes.
(documented)

Worth checking on the C5 with OLED Motion Pro off, since 4K120 is pinned here by
`couch-4k120.service`.

### Audio output as a top-level concern

Xbox puts **Volume & audio output** at the General level, on a par with network and
display - HDMI/optical output format, headset format, bitstream versus uncompressed, party
chat routing, per-output volume, Windows Sonic and Dolby Atmos for Headphones.
(widely-reported)

The Guide's **Audio & music** bottom tab gives volume, chat mixer and music-app transport
controls without leaving the game - and the lesson is that it lives in the always-available
utility row, not as a top-level destination. (widely-reported)

PS5 keeps volume in the Control Center under **Sound**, with headphones and controller
speaker as separate sliders, plus Audio Focus (section 6). Volume changes surface a
transient on-screen overlay that appears instantly, holds, then fades - one of the very
few things that renders over full-screen game content. (documented / widely-reported)

Music is a persistent shell-level card with its own transport, designed to sit under a
running game, with **game and music volumes independent**, and it survives context
switches including into and out of a game. 24.01-08.60.00 redesigned the music control
centre with a two-column layout. (documented)

### PS5 USB media playback, as an instructive contrast

Deliberately narrow (documented):

| Container | Video | Audio |
|---|---|---|
| MKV | H.264 High Profile L4.2 | AAC LC |
| MP4 | H.264 High Profile L5.2 | AAC LC |
| WEBM | VP9 | Opus |

"Maximum video resolution is 3840 x 2160." Music from USB requires a folder literally named
**"Music"** in the root; FLAC, MP3, AAC. Drive must be exFAT or FAT32. **No HEVC, no AC-3,
no DTS from USB.**

Kodi's codec support is vastly wider and that is our advantage - but Sony's narrowness
means playback never stutters or fails ambiguously. Worth remembering when deciding how
much to expose.

### Certification: resolution and safe area

- PlayStation has equivalent requirements here. The entire application must be checked at
  each supported resolution, with the visibility needed to use it and to play maintained
  throughout, and testers are told to check full-motion video and animation specifically.
  Essential items - which explicitly includes error and warning messages, legal text and
  online IDs - must sit inside a safe area inset from the screen edges, re-tested with the
  console's Adjust Display Area setting at arbitrary values. Long strings must scroll or
  offer a details affordance rather than being clipped. (widely-reported)
- Xbox **XR-131**: HDR titles must render **both** an SDR and an HDR swap chain, "because
  the SDR swap chain is used for SDR screenshots, broadcasting, and Game DVR". Test 131-01
  turns HDR off in console settings while the title is running and validates. Fail
  examples: "SDR significantly lighter/darker than HDR, smaller SDR image, significant
  black bars/borders." (documented)

### What this would mean for couch

- **Already done.** The `tv` command over webOS; 4K120 with `force_yuv420_output` plus a
  hand-made modeline pinned by `couch-4k120.service`; soundbar on eARC; headphones
  following the TV via tv-waker-webos; the Remote tab's TV/soundbar volume card.
- **Cheap and overdue.** A read-only "what is the sink actually claiming" page - EDID/DRM
  state, current mode, colour format, HDR support per frequency. Sony ships two read-only
  pages for exactly this and they are the first thing you want when the picture is wrong.
- **Cheap.** A three-item front page (resolution, refresh, TV control) with everything else
  behind Advanced. Right now the 4K120 setup is entirely hidden in shell scripts.
- **Cheap.** Grey out unsupported modes rather than hiding them, with the reason: "VRR:
  unavailable on this link".
- **Cheap.** Surface the film-cadence toggle (Kodi's refresh-rate switching) as a plain
  capability checkbox, not a playback preference.
- **Cheap.** Use plain language, not "CEC". Xbox's "Device control" is the right label.
- **Cheap.** A transient on-TV volume overlay when volume changes, so the person holding
  the pad sees it too - the phone card only serves the person holding the phone.
- **Cheap.** Check the skin's essential text against a safe box inset from the screen
  edges. Five-minute test, real payoff on a TV with overscan.
- **Cheap.** Eyeball the skin at 1080p **and** 2160p. Text authored under 1080p
  assumptions is likely half the console minimum at 4K (see section 15).
- **Check.** Whether anything enabled on the C5 is displacing an EDID block we need
  (the FreeSync/Dolby Vision precedent), and whether running the desktop permanently at
  120 Hz inherits the double-image artefact.
- **Project.** Borrow the **Video Transfer Rate** idea: a fallback ladder that explicitly
  lists which modes get dropped at each level, rather than silently degrading.
- **Project.** A one-time system-level display/audio wizard, rather than N per-app
  calibrations - only worth it if we ever get real HDR passthrough.
- **Rule.** Any display feature that is on by default needs its off switch on the same
  page as the feature, not documented somewhere else.

---

## 12. Notifications and interruption policy

This is where the consoles are furthest ahead of anything a PC does, and most of it is
cheap.

### PS5: a category x context matrix

Settings > **Notifications** (documented).

Global toggles:

- **Allow Pop-Up Notifications**
- **Show Preview**
- **Play Sound**
- **Haptic Feedback** ("available only when a Vibration Intensity level is selected")
- **Display Time** - "Change how long you see a pop-up before it disappears"

Then **Manage pop-ups**, where **for each type** you choose to suppress it "while you're
playing games, watching videos, during broadcasts, or any combination of the three".

The roughly twenty categories: When Friends Go Online, Game Invitations, Trophies,
Tournaments, Challenges, Friend Requests, Messages, Message Reactions, Parties, Song
Change, Downloads and Copies, Uploads, Power Saver for Games, Controller Profiles, PS Link
Device Nearby, Wishlist Updates, From PlayStation, Feedback, Subscriptions, Game Help.

Note that even **Song Change** and **Power Saver for Games** - utterly mundane - are
individually suppressible per context.

Some categories only appear in the list **if you own the relevant hardware**: "Controller
Profiles: Only users that have a DualSense Edge wireless controller (CFI-ZCP series) or
Access controller (CFI-ZAC series) currently assigned to them can see this setting." Same
for "PS Link Device Nearby". (documented)

### Do Not Disturb is session-scoped

Control Center > Notifications > **Do Not Disturb**. Sony: "Pop-ups for notifications
don't appear on-screen until you **log out of or restart** your PS5 console, or until you
turn off Do Not Disturb." (documented)

So it survives a whole evening and dies at reboot. That is more forgiving than a permanent
mute you forget you set, and it prevents the classic "notifications stopped working three
weeks ago" support call.

Square deletes a single highlighted notification; Options > Delete All Notifications
clears the list. A toast can be expanded in place by pressing PS while it is on screen.
(documented)

### Xbox: position, duration, and a unified inbox

- Notifications are configurable on **three axes**: which types appear, **where on screen**
  they appear, and **how long** they stay. Xbox Support: "To turn notifications off or on,
  or to change which notifications appear, where they appear on screen, and how long they
  appear..." (documented)
- Settings > Preferences > Notifications > **Default Notification Position**. The screen is
  a 3x3 grid; the three top panes and three bottom panes are selectable, **the middle row
  is not**. Default is bottom-centre, which is why achievement toasts land on subtitles and
  HUD elements. Caveat: "Some games might choose to alter the position of Xbox game
  achievements no matter what position you choose." (documented)
- Games can hint at position via the GDK. `XGameUiSetNotificationPositionHint` takes
  `XGameUiNotificationPositionHint` with exactly six values: **BottomCenter = 0,
  BottomLeft = 1, BottomRight = 2, TopCenter = 3, TopLeft = 4, TopRight = 5**. "By default
  on Xbox, toast notifications are shown at the bottom center of the screen." Microsoft's
  remark: "The notification position is a hint to the operating system... In some cases,
  the system may choose to ignore the setting if the current UI cannot support displaying
  notifications in that location." The same API exists on Windows and has no effect there.
  (documented)

  The enum corroborates the user-facing six-pane grid exactly. **The middle row exclusion
  exists to protect subtitles**, which matters directly given the Bazarr-driven external
  SRT setup.

- **One unified inbox**, reachable from the Guide's bottom bell. Xbox Wire, Aug 2020: "the
  inbox includes notifications from across all Xbox apps... **Acting on a notification in
  one place clears it everywhere.**" (documented)

### The unsuppressible tier

Both platforms reserve the right to interrupt regardless of user settings. Not suppressible
in the same way: low-storage warnings during updates, the XR-132/XR-133 abuse toasts,
thermal warnings, and family screen-time countdowns. Sony's equivalent hard tier includes
the overheating message and playtime enforcement. (widely-reported)

### Notification-adjacent: the persistent status banner

Xbox and PS5 both learned that a *persistent* banner over gameplay is a different problem
from a toast. PS5 added **"Hide Remote Play Connection Status Pop-Up"** in 24.03-09.20.00
specifically because the "Remote Play connected." message sat over gameplay. (documented)

### Escalation: notify then act

- PS5 parental playtime: Settings > Family and Parental Controls > select user > Playtime
  Settings. **"When Playtime Ends"** is a two-way choice - **"Notify Only"** (message,
  play continues) or **"Log Out"**. Notifications appear at the top of the screen as the
  limit approaches, and the console can repeat a reminder **every 5 minutes** after the
  limit is hit. (documented)
- Xbox screen time is configured only from the web or the Family Settings app, never from
  the console. A parent can remotely pause play, which shows a "your screen time is up"
  message plus an option for the child to **request more**; requests land on the parent's
  app notifications tab. Microsoft's honest caveat: "After screen time limits are set, time
  counts down whenever a member is signed in. Make sure that they sign out when they're not
  actively using their device." (documented)

The notify-then-act ladder with a repeating nag is the right shape for anything the box
wants to do to a running session - a pending reboot after a kernel update, a scheduled disk
check.

### One system error dialog primitive

Xbox exposes `XGameUiShowErrorDialogAsync`, which "Displays UI for an error dialog with a
service defined error string for the specified error code" - the game passes an HRESULT and
the platform supplies the localized text. `XGameUiShowMessageDialogAsync` gives a
customizable dialog with a fixed button enum `XGameUiMessageDialogButton`. Both async with
explicit `*Result` getters. (documented)

One error-dialog component, taking a code, means the phone remote and the TV render the
same failure identically and you never write the same modal twice.

### What this would mean for couch

- **Cheap, and probably the best-value item in this whole document.** Build the matrix:
  category x context. Categories that already exist here - disk-monitor alerts, Steam
  download done, Jellyfin/arr activity, pad connect/disconnect, low battery, TV mode
  change, box-vs-netbook ping alerts. Contexts: during video, during a game, on the home
  screen. Plus a global **Display Time** control.
- **Cheap.** Session-scoped Do Not Disturb that self-clears on restart. Pairs naturally
  with light-watch's dim-on-play hook - a film-night DND is one line away from something
  that already exists.
- **Cheap.** Notification **position** as a user setting, and never the middle band. On a
  TV this is not a nicety: overscan eats corners and subtitles own the bottom-centre.
- **Cheap.** A position **hint** API from couchd, so Kodi playing a film with subtitles can
  ask for top-right while a game asks for bottom-left, with the shell free to override.
- **Cheap.** One shared notification store between the phone app and the Kodi overlay, so
  clearing a disk alert on the phone clears it on the TV. The plumbing (couchd + web
  remote) already exists.
- **Cheap.** Hide settings for hardware that is not present.
- **Cheap.** One error-dialog component that takes a code, used by both surfaces.
- **Cheap.** An explicit toggle to suppress any persistent status banner couchd draws over
  a game.
- **Required.** A small hard-coded "always shows" tier that sits above DND: disk fault,
  thermal, storage nearly full, pending forced reboot.
- **Rule.** Disk-monitor and download alerts must not toast over a film. That is the entire
  reason the matrix exists.

---

## 13. Errors and failure

### The shape of Sony's error system

Sony's public PS5 error-code index lists roughly **290 codes** across five prefixes
(documented):

| Prefix | Domain |
|---|---|
| CE- | Console / application |
| NP- | Network platform / account |
| NW- | Network |
| WS- | Web service |
| SU- | System update / startup |

Each has **one short sentence**. Examples: **CE-107872-5** "There is not enough free space
on the console storage."; **CE-110555-7** "The disc cannot be read."; **CE-108255-1** "An
error occurred with the game/application."

**The sentences are heavily reused.** "Unable to connect to the server." appears on at
least twelve distinct codes. "Please install the latest system software." on six. "This
service is currently under maintenance." on six (WS-116449-5, WS-116521-6, NP-103105-0,
NP-103109-4, NP-103111-7, NP-103117-3). And there are at least six separate generic
catch-alls reading some variant of "An error has occurred." - CE-105771-1, CE-100022-5,
CE-113227-6, CE-100008-9, CE-113511-2, CE-117773-6.

**The code is for support; the sentence is for the sofa.** You do not need bespoke copy for
every failure path. A generic sentence plus a distinct code per call site is a legitimate,
shipped design, and it is far better than a stack trace or an endless spinner.

Even the no-op has an identifier: **SU-101495-0** "This code indicates that the system is
up to date."

### The register: describe when they can't act, instruct when they can

Across Sony's ~290 codes the modal length is one sentence and the modal voice is
passive-descriptive: "An error has occurred.", "Internal error.", "Application error.",
"Network connection error." Where the user **can** act, it becomes an imperative: "Please
install the latest system software.", "Please check the connection status of HD camera and
PS Camera.", "Please check that the information for your registered payment method is
correct." (documented)

Microsoft's cloud-save messages are the same length in first-person plural: "We couldn't
get your latest saved data", "We couldn't sync your info with the cloud". (documented)

**Rule: describe when the user cannot act, instruct when they can, never mix the two in one
sentence.** Sony avoids "we"; Microsoft prefers it. Both are defensible; consistency is
what matters.

### Failure taxonomy is deliberately fine-grained where it changes the fix

Sony splits things a generic system would merge (documented):

- Disc unreadable (CE-110555-7, CE-110551-3, CE-110552-4, CE-110538-8) versus **drive not
  enumerated at boot** (SU-101312-8 "Blu-ray Disc drive does not exist.")
- Disc-versus-install mismatch gets its own code: **CE-107649-7** "The inserted disc
  contains content that is different from the installed data."
- Slow-but-alive network (**NP-102947-3** "The internet connection is too slow or unstable
  to perform the update.") versus timeout (**NW-102417-5**) versus **DNS failure**
  (**CE-118527-4** "There was a problem resolving the hostname.")
- Licence/entitlement (CE-109245-1, NP-104291-7, CE-105638-3, CE-110032-7) versus network
- Subscription verification (CE-107255-0, CE-116799-3, CE-118415-0) versus everything else
- Update phases: download failed (CE-118446-4, CE-113338-9), bad file (CE-100009-0),
  install failed (CE-127527-2 / CE-107527-2), already up to date (SU-101495-0)
- Purchase/store (CE-112987-8, CE-106487-6, CE-112988-9, WS-116129-0 "We can't find this
  content, or the content isn't currently available.", WS-113947-5 payment method)
- Streaming specifically (CE-117722-0 "Your streaming connection has an error.",
  CE-112069-9, NP-104627-0)
- Peripherals (CE-109531-9 audio device, CE-111161-1 / CE-108360-8 camera, CE-119224-9
  PS VR2 Sense device software)
- Sign-in: wrong credentials (WS-116329-2, NP-102955-2), **account** suspended temporarily
  (WS-116331-5, WS-116330-4) versus permanently (WS-116367-4) versus **console** blocked
  (WS-116332-6), age restriction (NP-102942-8), 2FA problems (WS-117224-7, WS-117176-3),
  catch-all (NP-103028-4)

### The 1998 rule that says it best

PS1 TRC 12.12.5, still the sharpest statement of the principle (documented):

> "Use clear messages to explain all aspects of Memory Card operation. For example, 'There
> is no Memory Card in Memory Card slot 1' or 'Memory Card in Memory Card slot 1 is not
> formatted'. **Do not use mixed messages such as** 'Memory Card in Memory Card slot 1 is
> not formatted or there is not enough space on the Memory Card to save your game.'"

12.12.6.2 adds that messages must say **which** slot they refer to.

**One cause, one device, one sentence.** "Playback failed" is banned; "disk1 is not
mounted" is the standard.

### Retry before you report

PS1 TRC 12.12.4: "When the title determines that loading, saving or formatting has failed
or that the saved data has been damaged, **it attempts several retries** and, if it
continues to fail, it then displays an appropriate message." 13.2-13.4 require error flags
checked on every CD access and repeated retry on failed Seek and Read. Both recommend
"Displaying an appropriate message **while retrying**." (documented)

That is the documented origin of the console habit of never showing an error on the first
failure.

### Do not lie about whose fault it is

Xbox **XR-074**: "If a partner service isn't available, the game must not indicate that
there's an issue with the Xbox network." Suggested wording is given verbatim: "Sorry,
*non-Microsoft service* is not currently available. Please try again later. For more
information, contact *non-Microsoft support contact information*." Fail examples: "Message
displayed implies issues with Microsoft services" and "Non-descriptive error message is
displayed." (documented)

Certification actually runs **Fiddler** and blocks every host that is not
microsoft/msft/xboxlive/xboxservices/live/PlayFabApi/msn/bing, to see who gets blamed.

That host-classification trick is a neat way to audit which failures the couch app blames
on the wrong thing.

### Network failure is an eight-scenario contract with a bandwidth floor

Xbox XR-074 test cases (documented):

- 074-01 WAN disconnect mid-save, mid-load, mid-matchmaking
- 074-02 physically pulling the cable or killing the router
- 074-03 disconnect while suspended
- 074-04 reconnect while suspended
- 074-05 **constant low bandwidth** via `xbstress.exe` "minimum" profile - **192 Kbps**
- 074-06 variable low bandwidth
- 074-07 partner-service outage simulated with Fiddler
- 074-08 pre-launch downtime

Requirement: "Titles must not crash or cause user data loss when user's internet connection
drops below 192 Kbps." Pass example: "User-friendly message is displayed indicating
possible impact to online play due to low bandwidth." Explicit fail: showing a network
error during purely offline play.

A game can also declare `RequireXboxLive` in its manifest, and then **the system**, not the
game, blocks launch when offline and suspends-then-terminates on connectivity loss.
(documented)

PlayStation has an equivalent requirement, and it prescribes the disconnection methods to
test with: turning off the router or unplugging the WAN cable, removing the LAN cable,
turning off the console's internet connection in Settings, closing the application, signing
out, entering Rest Mode, and running the debug network emulation. The core of it: the
application must not hang, **user cancel operations must not be blocked**, and the
application must not otherwise become inoperable. (widely-reported)

**A hung network call must never block the user's escape route.**

### Raw codes are banned from the screen

PlayStation has an equivalent requirement: raw hexadecimal error codes returned by SDK
APIs **must not be displayed**, only the platform's own short error-code forms and only
through system dialogs, and a developer may not invent codes that imitate that format.
(widely-reported)

### Losing user data is a named failure mode

Xbox XR-001/XR-003 fail examples include the bare statement "The game causes the loss of
user data." XR-001-02 requires that "Users must not lose save progress after returning to
gameplay" after suspend/resume - **and explicitly allows the pass case "Game terminated by
system due to connected storage de-synchronization".** (documented)

**When integrity and continuity conflict, kill the session.** For couchd that means a
detected disk fault or a de-synced save should terminate the game rather than let it keep
writing. That is exactly the lesson from the two silently zeroed files.

### Cloud save conflicts

- PS5: **CE-118851-4** and **CE-122154-5** "Your PlayStation 5 console can't sync your save
  data with Cloud Storage." The user-facing conflict dialog is widely reported as "Couldn't
  sync your save data due to a conflict", offering per-title selection **plus an "Apply to
  All" button**. Sony's own doc claims PS5 games sync to the most recent data automatically
  - contradicted in practice by the conflict dialog users report. (documented, with the
  contradiction flagged)
- Xbox names **nine** distinct verbatim messages rather than using codes (documented):
  "Your previous device is still uploading your game save"; "You may have unsynced progress
  on a previous device..."; "Unable to complete your sync from your previous cloud gaming
  session"; "We can't save additional info for..."; "Which one do you want to use?"; "Your
  other device is taking a long time to sync to the cloud"; "We couldn't sync your info
  with the cloud"; "We are unable to sync your data with the cloud at the moment"; "We
  couldn't get your latest saved data". Options on the waiting case are **"Sync last saved
  data"** (steal the lock) and **"Keep waiting"**.

  Three of the nine are about the **other** device. A distributed-state UI has to explain
  what a machine you cannot see is doing.

- Xbox prevents most conflicts with an explicit **lock**, not after-the-fact merging.
  Microsoft's Game Saves guide: "**Lock**: a mechanism that grants exclusive access to a
  title's Game Saves for a specific user on the device that they're actively using. A lock
  ensures that no other device can modify the Game Saves for the user while the lock is
  held." Conflict UI is the crash-recovery fallback. (documented)
- Certification fail, verbatim: "The saves in the cloud are not recognized by the title on
  first launch, and **through no user interaction**, are subsequently overwritten on the
  second device." That test (052-06) is joint-8th most common failure at 3%. (documented)

**Conflict dialogs must be batchable** ("Apply to All") or they become unusable after an
offline weekend.

### Crashes are soft

A game crashing produces a dialog with a code, the game closes, and you land back on the
home screen with the system intact. Sony's own remediation for CE-108255-1 is a single
line: "Try updating your game." Related codes distinguish the phase: CE-100095-5 "There was
an issue when starting the application.", CE-100096-6 "There was a problem loading the
application.", CE-105841-9, CE-107750-0, CE-109573-5, CE-107622-8 "Failed to launch the
application." (documented)

### Thermal

- PS5: the message widely reported verbatim is "Your PS5 is too hot. Turn off your PS5, and
  wait until the temperature goes down." The console then powers itself down. Sony gives
  an **instruction, not a temperature**. Community consensus is at least ~4 inches
  clearance. Note there is **no PS5 thermal LED colour** - the on-screen message is the
  only channel. (widely-reported)
- Xbox warns when running warm and shuts down to prevent damage, but multiple sources note
  that "if a heating issue is particularly serious, your Xbox Series X can shut down
  without warning." Most-cited real-world cause: a soundbar or shelf on the top exhaust
  vent. (widely-reported)

**The warning path and the protection path must be independent.** A hard thermal trip must
not depend on the UI being alive to render a warning.

### Guide failure is itself an error

Xbox **0x8027025a** is documented as the app or the Guide "took too long to start".
Community remediation is a full power cycle. (widely-reported)

When the shell or switcher fails to appear, that must produce a visible, coded failure and
an obvious recovery - otherwise the user just holds the power button, which here means an
unclean shutdown of a mounted media disk.

### Beta software must announce itself

Xbox **XR-117**: betas and Game Previews "must have a splash screen or message that's
displayed within the experience, after it's launched but before gameplay", communicating
that it is pre-release software, that some platform features might not work correctly, and
that some game features might not work and might crash, plus "the support boundaries for
the title". (documented)

### Fault injection is a shipped feature

PlayStation has an equivalent requirement: the application must not hang when a Share
capture API fails for lack of disk space, and the test procedure drives that from the
console's **Fake Generated Error** debug setting. The platform ships a **menu of fake
failures** so developers can test them. (widely-reported)

### What this would mean for couch

- **Cheap, do this first.** A couchd error registry: stable short IDs (`COUCH-DISK-001`),
  one plain sentence each, rendered identically on the TV and in the phone remote. Reuse
  sentences freely; the ID is what makes support conversations tractable. Keep several
  generic catch-alls with distinct IDs rather than agonising over copy for rare paths.
- **Cheap.** Never surface a raw errno, HTTP status, or Python traceback. Define our own
  short code namespace that is greppable in the logs, and show that plus a sentence.
- **Cheap.** One cause, one device, one sentence. Name the actual failing component:
  Jellyfin, dnsmasq, the Caddy proxy, Sonarr, the WAN, disk1. A single symptom on this box
  can come from any of eight things, and generic messages make it unfixable.
- **Cheap.** Distinguish DNS failure from service-down. dnsmasq and `*.home` names make
  this a real, recurring, currently-invisible distinction.
- **Cheap.** Retry transient failures with a visible "retrying..." state before declaring
  failure. Startup races (Kodi JSON-RPC, Jellyfin first sync) and USB link resets are all
  in this class.
- **Cheap.** Distinguish "Jellyfin is restarting" (we did that) from "Jellyfin crashed". If
  couchd knows it just restarted a service, say so.
- **Cheap.** A thermal warning on the TV before throttling, with Sony's tone: what
  happened, what to do, two sentences. Pair it with a hard trip that does not need the UI.
- **Cheap.** A visible marker in the couch app for anything running behind a flag or in
  shadow mode, so an unexplained failure is attributable.
- **Project.** A fault-injection switch in couchd - simulate disk-full, disk-unmounted,
  Kodi-not-responding, Steam-offline - rather than waiting for the real thing at 2am.
- **Project.** Audit which failures the app currently blames on the wrong thing, using the
  Fiddler-style approach: block one host at a time and read the message.
- **Rule.** Cancel must always work. A hung network call must never block the escape route.
- **Rule.** When integrity and continuity conflict, kill the session.
- **Rule.** If anything ever syncs state (watched positions, resume points, save
  directories), fail closed and ask. Never silently overwrite. Make the conflict dialog
  batchable.
---

## 14. Recovery: safe mode, resets, and escalation ladders

The single most transferable structure here is that **recovery options are ordered
least-destructive first, and every rung says what it keeps.**

### PS5 Safe Mode

Entered by feel, with audible confirmation and no screen required: hold power 3 s to power
off, then hold power again and **release after the SECOND beep** - "one beep sounds when
you first press, and another seven seconds later" - then connect a controller **by USB**
and press PS. (documented)

The eight options, in Sony's order (documented):

1. **Restart PS5**
2. **Change Video Output** - exists purely so a wrong display mode cannot lock you out
3. **Repair Console Storage** - "Scans storage without erasing data"
4. **Update System Software**
5. **Restore Default Settings** - preserving games and saved data
6. **Clear Cache and Rebuild Database** - does not delete games, saves or settings
7. **Reset PS5** - "Deletes all user data"
8. **Reset PS5 (Reinstall System Software)**

Separately, **Restore Default Settings** in the normal settings tree (Settings > System >
System Software > Reset Options) is a distinct, non-destructive operation that **previews
what it will change**: "The settings affected by restoring default settings appear on
screen" before you confirm. Sony explicitly contrasts it with resetting, which "deletes
user and game data as well as any personalized settings". (documented)

### Xbox recovery

- The failure screen is branded with **exactly two actions**: "Restart this Xbox" and
  "Troubleshoot" (which opens the Xbox Startup Troubleshooter). (documented)
- Documented E-code groups route to six different recovery paths: E100/E200/E204/E207 (a
  6-step path ending in repair); **E101** (3-step, straight to Offline System Update
  OSU1); **E102** (4-step, starting with "Can you bring up the Xbox Startup
  Troubleshooter?" and including an offline factory reset; also appears as "E102 xxxxxxxx
  xxxxxxxx" with varying hex); **E105** (2-step); E106/E203/E208/E305 (5-step).
  (documented)
- The middle rung is the one people actually use: Reset console > **"RESET AND KEEP MY
  GAMES & APPS"** versus "Remove everything". (documented)
- **Offline System Update (OSU1)**: downloaded on a PC, unzipped to a **FAT32** USB drive,
  applied by holding **BIND + EJECT** while pressing power. A documented,
  user-executable recovery that needs no second console. (documented)
- Holding the console power button **10 seconds** forces a hard shutdown, and a full power
  cycle (unplug ~10 s) is the documented cache-clearing remedy, recommended periodically
  even in Sleep mode. (documented)
- Power loss during a system update produces the E1xx/E2xx family and needs the OSU path,
  not a retry. (widely-reported)

### The beta channel has a documented exit

PS5 system-software beta is opt-in via a 12-character voucher, at Settings > System >
System Software > System Software Update and Settings > Update System Software (beta), and
leaving is a single visible control: **"Stop Using Beta Version"**. The beta version number
is shown at Console Information. Guest users, child accounts and offline users cannot
update to beta. Sony advises backing up first and states the backup file should be under
200 GB with at least 1 GB free. (documented)

Xbox does the same with named Insider rings (Alpha Skip-Ahead, Alpha) and publishes what is
in each. (documented)

### Backup and transfer

Xbox, Settings > System > **Backup & transfer**, writes console settings to a USB drive or
transfers them over the network to another console. It has its own support article.
(documented)

Consoles ship this and homelabs never do.

### On-box help

PS5 ships the **User's Guide** as a settings entry (Settings > User's Guide, Health and
Safety, and Other Information > User's Guide), rendered as a navigable webview with its own
navigation table (L1 back, R1 forward, D-pad focus, left stick pointer, right stick scroll,
X select, Circle back), closed via Options > Close or repeated Circle, and: "You can change
the appearance by switching Theme in the top right of the User's Guide." A separate **Guide
and Tips > Discover Tips** feed was added in 23.02-08.00.00. (documented)

### What this would mean for couch

- **Already done.** `tools/kodi-restart` exists, and the standing rule that a killed
  `kodi.bin` forges a crashlog so `pkill -9` is banned.
- **Cheap.** Make the *safe* restart prominent in the power menu so the hard path is rarely
  needed. That is exactly how Xbox keeps people off the 10-second hold.
- **Cheap.** A "hard restart" action in the couch app that does the graceful equivalent -
  clear Kodi's texture cache and userdata Temp, restart the session cleanly - so nobody
  reaches for the ATX button.
- **Cheap.** A "put display and audio settings back to known-good, list exactly what will
  change, keep my library" button. On a box with hand-made modelines and fan curves this
  is genuinely valuable, and the preview-what-will-change step is what makes it safe to
  press.
- **Cheap.** Annotate every recovery rung with what it keeps. Users choose the wrong rung
  when the consequences are unlabelled.
- **Cheap.** A visible "you are on the test build / go back to stable" control. The
  shadow/couchd staging already has this shape; it just is not a control.
- **Cheap and overdue.** An on-box help page describing this box's own quirks: never
  live-switch skins on Kodi 20, how the 4K120 flag works, what the pad lights mean, the
  pairing chords, how to get back to Kodi. Kodi can render it, and it will survive our own
  memory better than a markdown file.
- **Project.** The escalation ladder itself, reachable without a keyboard and ideally
  without a working display: restart shell → **reset video output** → repair library DB →
  restore default settings → full reset. The video-output rung matters here specifically,
  because 4K120 plus hotplug clearing `force_yuv420_output` is a real way to lose the
  screen.
- **Project.** An audible or out-of-band confirmation channel for exactly the state where
  the screen is what broke: a beep, the Discord webhook that already exists, or the phone
  remote's status pill.
- **Project.** "Back up settings to USB". Config currently lives across `~/.config/couch`,
  `~/.config/tv-remote`, the skin, and systemd units.
- **Project.** A bootable USB recovery image that restores couchd plus Kodi config. Note
  the risk it mitigates: the box updates via apt/flatpak with **no A/B partitioning**, so a
  power cut mid-upgrade is a genuine brick risk. The console-grade answer is A/B partitions,
  which is what SteamOS does; the cheap mitigations are scheduling OS updates into the
  maintenance window and snapshotting before upgrading.
- **Not worth it.** A full factory-reset flow. There is nothing to reset to.

---

## 15. Accessibility

Both platforms treat accessibility as an OS-level service layer overlaying every app, not
a per-game concern. A useful sanity check: a shell that ships a screen reader, remapping,
captions and colour correction is considered the **minimum**; everything else accreted
over five years.

### PS5: the menu

Settings > **Accessibility**, grouping nine sub-areas (documented): Check game
accessibility, Haptic Feedback, Controllers, Enlarge Display Area (Zoom), Display and
Sound, Screen Reader, Closed Captions, Chat Transcription, Mono Audio.

Crucially, **Accessibility can be pinned into the Control Center** so settings are
reachable mid-game: "If you add Accessibility to the control center, you can adjust these
settings from here as well." There is also an Accessibility widget on the Welcome hub where
L1/R1 cycle categories and clicking **deep-links into the exact settings sub-page** rather
than dropping you at the top of a tree. (documented)

### PS5: display settings, as a flat list

Settings > Accessibility > **Display and Sound** (documented):

- **Zoom** (Enable Zoom, Adjust Display Area to Movement)
- **Invert Colors** - "When this setting is enabled, HDR is turned off"
- **Color Correction** - Enable Color Filter + filter choice + **Color Intensity** slider
- **Text Size**
- **Bold Text**
- **High Contrast**
- **Show Check Mark on Enabled Settings** - "Show a check mark on enabled settings so you
  can easily see that they're turned on"
- **Auto-Scroll Speed** - "Set the speed of horizontal scrolling of text"
- **Reduce Motion**

Four separate controls for size, weight, contrast and inversion, rather than one "large
print" mode. Someone who needs bold usually does not need everything huge.

**Show Check Mark on Enabled Settings** exists because a green-versus-grey toggle pill is
invisible to some users. It is a one-line markup change and almost nobody ships it.

### PS5: Zoom

Enable at Settings > Accessibility > Display and Sound > Zoom > Enable Zoom. Then from
**anywhere**: **PS + Square** enters adjustment; each further PS + Square press steps the
magnification up ("The zoom magnification changes with each press"); **Cross** confirms and
**you keep operating the UI while zoomed**; right stick pans when auto-follow is off;
PS + Square again then Circle exits. (documented)

**"Adjust Display Area to Movement"** auto-pans the viewport to follow UI focus - and Sony
documents that in some contexts (playing a game, watching disc media) it will **not**
follow, because there is no focus signal to follow. (documented)

Zoom is explicitly unavailable during Remote Play, broadcasting, Share Screen/Share Play,
8K output, and PS VR. Sony states plainly where the feature cannot work. (documented)

Web cards get a separate two-mode magnification with different semantics: **Zoom** enlarges
and **reflows** the page; **Magnify** enlarges pixels without changing layout so you must
scroll. L3 and R3 zoom in and out. (documented)

### PS5: screen reader

Settings > Accessibility > **Screen Reader** > enable. Sub-settings: **Speech Speed, Voice
Type, Voice Volume**. The language is tied to the console language, not independently
selectable. Documented languages: Arabic, Dutch, English, French, German, Italian,
Japanese, Korean, Polish, Portuguese, Russian, Spanish, plus Turkish, Swedish and
Portuguese (Portugal) added in 23.02-08.00.00. (documented; note Sony's own 2025
retrospective claims 15 languages from April 2022, so marketing and support pages
disagree)

**Chords that work while it is speaking** (documented):

- **PS + Triangle** - pause / resume speech
- **PS + R1** - start reading the current item from the beginning

A screen reader with no shut-up key and no repeat key is unusable. This is the pattern to
copy for any voice output.

### PS5: captions

Settings > Accessibility > **Closed Captions** > Display Closed Captions, then **Closed
Captions Settings > Custom Caption Style**: font size, colour, edges, opacity; background
colour and opacity; window colour and opacity. Default is "what you're watching determines
the way closed captions are displayed". (documented)

That is the full CEA-708 style model, and Kodi already has the equivalent knobs buried in
Player > Language.

### PS5: mono audio, in the wrong place

**Mono Audio for Headphones** is **not** in the Accessibility menu. It lives at Settings >
Sound > Audio Output > Headphones - "Play the same audio from both your left and right
headphones." The Accessibility page links to it but does not host it. It is headphone-only;
there is no documented mono downmix for the TV/soundbar path. (documented)

A cautionary tale about information architecture, and an opportunity: a PipeWire/ALSA mono
downmix applied to the **whole** output would actually beat Sony here.

### PS5: chat transcription

Settings > Accessibility > **Chat Transcription**. Speech-to-text and text-to-speech in
both directions, six languages (English, French, German, Italian, Japanese, Spanish). You
pick a **Voice Type** that represents you when your typed text is spoken. Others' speech
appears as text on the right of the voice chat card. In-game chat transcription only works
in games that opted in. (documented)

### PS5: the Access controller

Launched 6 December 2023. Not directly relevant, but the details are instructive
(documented):

- A flat 8-button disc operable from **any 360-degree orientation**, on a table, a
  wheelchair tray, or bolted to an **AMPS-pattern** mount. The stick has an extension arm
  that lengthens, shortens and locks.
- **19 interchangeable button caps, 3 stick caps, and 23 physical labels**: 8 pillow
  (fitted), 4 flat, 4 curve (mountable to push from the top or pull from the bottom), 2
  overhang (closer to centre, for smaller hands), 1 wide flat (spans two sockets so one
  press hits two slots). Sticks: dome (fitted), standard, ball. Sony accepted that a
  30-profile remapping system needs a paper index.
- **30 profiles on the console, 3 cached on the controller**, switched by a dedicated
  hardware **profile button** - no menu involved.
- Per-button options: map freely; set a press to **toggle** a command on/off rather than
  requiring a hold; **disable** a button entirely to prevent accidental presses; **map two
  commands to a single button**.
- Stick **north-direction recalibration** so the pad can sit at any rotation, plus
  independent sensitivity and deadzone.
- Four 3.5 mm expansion ports (E1-E4), two-contact single miniature plugs meeting IEC
  60603-11:1992. Sony **publishes the port specification and 3D printing data** for caps at
  playstation.com/support/hardware/access-specifications, with no support or warranty.
- The packaging itself opens one-handed: pull loops on both sides, internal loops so the
  controller slides out without gripping.

The most transferable pieces: **hold-to-toggle conversion** (hold-to-sprint becomes
tap-to-sprint) is one of the highest-value accessibility transforms that needs no game
cooperation and is implementable in Steam Input; **disable a button entirely** is equally
easy and equally overlooked; and a **hardware/chord profile switch that needs no menu**
beats a settings page.

### PS5: store accessibility tags

Launched April 2023. **50+ publisher-declared tags in 6 categories**: Visual, Audio,
Subtitles and Captions, Controls, Gameplay, Online Communication. Over 700 tagged games by
2025. **Self-declared by the publisher, not verified by Sony.** (documented)

Individual tags are specific and testable rather than vague: Clear text, Large text, High
contrast visuals, Color alternatives, Audio cue alternatives, Directional audio indicators,
Volume controls, 3D audio, Mono audio, Screen reader, Visual cue alternatives, **Playable
without subtitles**, Subtitles (advanced), Subtitle size, Clear subtitles, Clear captions,
Large subtitles, Large captions, Controller remapping, Adjustable stick inversion (basic),
Thumbstick sensitivity, **Playable without button holds**, **Playable without rapid button
presses**, **Playable without motion controls**, **Playable without touch controls**,
**Playable without controller vibration**, **Playable without adaptive trigger effect**,
difficulty levels, skippable puzzles, simplified QTEs, game speed, text or voice chat
transcription, ping communication. (documented)

The "Playable without X" phrasing is the useful bit - a negative capability statement is
far more actionable than "has accessibility options".

**And then they hid it.** The tags are reached by: Games home > PlayStation Store > select a
game to open the game hub > **press the triangle button** (or select the side panel). A
whole metadata system behind an unlabelled face-button press. This is the worst
discoverability decision on either platform. (documented)

### Xbox

Reached from the guide: Profile & system > Settings > **Accessibility**. If a USB keyboard
is attached, **Windows logo key + U** opens it directly - the same chord as Windows Ease of
Access, because the Xbox shell is a Windows variant. (documented)

The page is organised **by task phrasing, not feature names**, and the section headers are
literally (documented):

- "Listen to what's on your screen"
- "Enlarge what's on the screen"
- "Customize closed captioning text"
- "Sharpen what you see"
- "Adjust the screen brightness"
- "Customize your controller"
- "Convert speech-to-text or text-to-speech"
- "Adjust sound settings"
- "Correct the color"

Someone who needs a magnifier does not know the word "magnifier". This costs nothing and is
strictly better.

The features themselves: Narrator, Magnifier, High contrast, Colour filters, Closed
captioning, Game transcription (speech-to-text and text-to-speech, plus "Let games read to
me"), Controller (remap / vibration / Copilot), Audio, **Night mode**, **Animation
effects**, **Mute sound effects**, Listen in mono, Focus. (documented)

- **Narrator**: full screen reader with adjustable **voice, volume and pitch**. Widely
  reported activation chord: hold Xbox, then press Menu. Pitch as a separate axis from
  speed matters - some users tune pitch to cut through game audio. (widely-reported)
- **Narrator has a setting to warn you BEFORE it activates**, specifically to defend against
  accidental chord presses: "There's also a setting within Narrator that can be enabled to
  warn you before Narrator is activated to reduce potential confusion in the event of
  accidental activation." Two lines of code; almost nobody does it. (documented)
- **Narrator works during out-of-box setup**, before an account exists. Microsoft maintains
  a dedicated article, "Use Narrator to set up an Xbox console or PC". The chicken-and-egg
  problem is solved by making the chord live at first boot. (documented)
- Narrator extends into media apps - separate support articles exist for the Blu-ray player,
  Movies & TV, and live TV - so it annotates transport controls and content lists, not just
  settings menus. That is exactly the Kodi case. (documented)
- A connected USB keyboard unlocks a substantially larger shortcut set than the controller
  can offer, because a pad has too few inputs. Microsoft publishes both lists separately.
  (documented)
- **Magnifier**: up to **16x**, multiple viewing modes, system-level so it works over games
  and the Guide alike. Activation chord: hold Xbox then press View; right/left triggers zoom
  in and out; right thumbstick pans. Works with a keyboard too. (widely-reported)
- **Night mode** is filed under **accessibility**, not display, with its own support
  article: screen dimming and blue-light reduction on a schedule, **and it dims the
  controller's Xbox button light**. (documented)
- **Mute sound effects** and **Animation effects** are discrete, separately-articled
  accessibility settings. (documented)
- **Copilot**: two physical controllers as one logical controller, system-level. (documented)
- Controllers can be bound to a user profile so picking up a specific pad signs that person
  in. (documented)
- **Break reminder** is a first-class Preferences item that nags after a configurable play
  duration, filed under accessibility as well. (documented)

### Xbox Accessibility Guidelines: the numbers

XAG v3.2. **These are explicitly best practices, not certification requirements** - which
matters, because they are the most concrete text-sizing numbers available anywhere.

**XAG 101 Text Display** (documented):

| Platform | Minimum default body height |
|---|---|
| **Console, 1080p** | **26 px** |
| **Console, 4K** | **52 px** |
| PC / VR, 1080p | 18 px |
| PC / VR, 4K | 36 px |
| Mobile, 100 DPI | 18 px |
| Mobile, 200 DPI | 36 px |
| Mobile, 400 DPI | 72 px |

Plus:

- Text must scale to **200%** of the minimum without loss of content or function, and
  icons/glyphs must scale with it.
- The player must never have to scroll both horizontally and vertically in one UI.
- Line width max **80 characters** (40 for CJK).
- Line spacing at least **1.5**; paragraph spacing at least **2x** line spacing; letter
  spacing at least **0.12x** font size; word spacing at least **0.16x**.
- At least one sans-serif face must be offered; a non-stylised alternative must exist for
  decorative fonts.
- Text left/right aligned per language, **never centred or fully justified** for blocks.
- "Platform-provided screen magnification tools **aren't an appropriate mitigation** for
  small text size."

**XAG 117 Moving Content** (documented): for auto-updating content, provide "a method to
control the frequency of updates" **and** "a method to pause, stop, or hide"; for
moving/blinking/scrolling/flashing content, provide "a mechanism to entirely disable this
content" **and** "a mechanism to pause or hide". Microsoft's cited example is the Xbox
Store app's separate **"Autoplay Video"** and **"Autoplay Sound"** toggles.

Xbox store tags additionally require, among others: **32 px subtitles scalable to 46 px**,
**4.5:1 contrast**, **±50% sensitivity range**, and testers must "engage with gameplay for
30 minutes". Notably, **system-level features do not count toward a game's tag** - system
mono audio and system remapping both fail the criteria, because the game must do it itself.
(documented)

### PS4, as a minimum viable set

Settings > Accessibility on PS4: Custom Button Assignments, Zoom, Larger Text, Bold Text,
Invert Colors, High Contrast, **Auto-Scroll Speed** (named range Very Slow to Fast), Text to
Speech, Closed Captions, Chat Transcription. (documented)

Implementing exactly these ten on a Linux couch box would match a 2013 console. That is a
reasonable first milestone.

### What this would mean for couch

- **Cheap.** A single Accessibility node in the couch shell that proxies to the real Kodi
  and OS settings, wherever they actually live. Kodi's are scattered across Interface,
  Player and System.
- **Cheap.** Task-phrased section headers, Xbox-style.
- **Cheap.** "Show a check mark on enabled settings" - a real toggle, one markup change.
- **Cheap.** Auto-Scroll Speed for marquee text, or a "wrap instead of scroll" option. Long
  titles that marquee too fast to read is a real Kodi problem.
- **Cheap.** Reduce Motion, split Xbox-style into motion and background imagery. Also
  honour `prefers-reduced-motion` in the web remote. Doubles as a performance escape hatch
  and a debugging aid when chasing render stalls.
- **Cheap.** Surface Kodi's existing subtitle style knobs as one "Caption style" page - the
  same seven controls Sony ships.
- **Cheap.** Mono downmix via PipeWire, applied to the whole output rather than headphones
  only.
- **Cheap.** Mute UI sound effects as a named setting rather than a buried skin option.
- **Cheap.** Deep-link from widgets into the exact settings sub-page.
- **Cheap.** Audit body text against **26 px at 1080p / 52 px at 4K**. Since the box now
  runs 4K120, any text authored under 1080p assumptions is likely half the console
  minimum. This is a concrete, testable, probably-failing check.
- **Cheap.** Line width, line spacing and alignment rules from XAG 101 - all free in CSS
  and in a Kodi skin.
- **Project.** A compositor-level zoom (gamescope or a KMS/xrandr scale) bound to a pad
  chord, with the confirm/cancel state machine so it never traps input. Decide up front
  whether it is pre- or post-encode, because it will interact with capture and streaming
  paths.
- **Project.** TTS: Kodi has `service.xbmc.tts` driving speech-dispatcher/festival/piper,
  and the box already runs whisper on the GPU. If it happens, ship the pause and repeat
  chords, and the warn-before-activating setting.
- **Project.** Hold-to-toggle conversion and per-button disable via Steam Input, plus a
  system-wide remap layer for the shell using the existing shared config file, with a
  transactional Apply.
- **Not worth it.** Chat transcription (no social layer). The Access controller ecosystem.
  Verifying accessibility metadata for Steam titles - Steam has no comparable structured
  field, so it would be scraping community sources.
- **Rule.** If a first-run wizard ever exists, the accessibility chord must work on the
  very first screen, before any config file exists to read a preference from.
---

## 16. Certification: the rules that force the behaviour

Most of what makes a console feel like a console is a written requirement with a number
attached. Microsoft's Xbox Requirements are public, and the 1998 PS1 TRC v1.3 is fully
archived. Sony's modern TRC is confidential licensee material, and its specifics are
deliberately not reproduced in this document.

### The time budgets

**Xbox XR-001 Title Stability**, verbatim fail examples (documented):

- "A non-interactive pause or static screen is presented lasting over **twenty seconds**"
- "The title contains a loading screen which is more than **two minutes** with no
  indication of progress"
- "The title contains a loading screen which is more than **three minutes** with a progress
  indicator"

Instability itself is defined as "any state where user input isn't recognized, or user
blocked from progressing due to software crash without notification."

**PlayStation has equivalent requirements** (widely-reported): a long scene transition
must display an animation, and a longer one must display **progress information** - a
progress bar or a time remaining.

**PlayStation also bounds suspended unresponsive screens** (widely-reported): a screen that
does not change **AND** whose user operations receive no response may not persist.
Excluded: static screens that prompt user action, and continuously changing displays
during transitions or cutscenes.

That is a precise and stealable definition: **the sin is not "slow", it is "frozen and
deaf".**

**PS1 TRC 18.7** (Recommended, and the tightest number of all): "During the initial load or
any subsequent loads, the user should not be presented with a blank screen lasting more
than **5 seconds**. Whenever loading occurs which may interrupt play, some sort of display
should be used. Any load that lasts longer than 5 seconds while on screen should notify the
user that a load is occurring." (documented)

5 seconds is where a console starts **apologising**. 20 seconds is where it **fails**.

### The aging tests

**PS1 TRC section 5** (documented): an aging test is "a test to find out whether or not the
title hangs or malfunctions when it is left running for **eight hours**." Three separate
required runs:

- 5.1 - 8 hours in **Demo Mode** (title/attract screen)
- 5.2 - 8 hours in **Pause Mode**
- 5.3 - 8 hours "in all areas of this title where a consumer could reasonably be expected
  to leave this title unattended for extended periods (e.g. menu screens, save game
  screens, etc.)"

5.4 additionally requires correct boot and run after hard resets via the Power button, soft
resets via Reset, and after exiting the CD player and the console memory-card screens.

This box has an unexplained 5 Aug idle freeze and a 9 Aug idle disk link-reset, and has
deliberately passed **none** of these three tests.

### The top failing tests, published

Microsoft publishes the actual distribution (Version 2.0, 1 April 2024). The boring stuff
dominates (documented):

| Test | Share |
|---|---|
| 001-01 Title Stability | **38%** |
| 003-02 Title Integrity | 14% |
| 045-01 Respect User Privileges | 11% |
| 064-02 Joining a Game Session from the Same Game | 8% |
| 055-01 Achievements | 7% |
| 124-01 Game Invitations | 6% |
| 015-01 User Communication | 3% |
| 052-06 Cloud Storage Roaming | 3% |
| 052-05 Correct User Association | 2% |
| 022-01 Official Naming Standards | 2% |
| 001-03 Title Stability after Suspend | 2% |
| 064-01 Joining from Outside the Game | 2% |

Named stability triggers include "**Crash or hang when rapidly entering and backing out of
all game menus**" and "Crash or hang when testing suspend/resume scenarios."

"Rapidly enter and back out of every menu" is a free, high-yield test, and it is exactly
the class of bug that has produced Kodi segfaults on this box before.

### The scoring maths

Xbox Certification Failure Mode Analysis (documented). Severity + probability +
repeatability, summed:

**Severity**: -4 (no relevant effect), 1 (very minor), 2 (minor), 6 (moderate), 12
(critical), 22 (catastrophic / High Business Impact, e.g. product becomes inoperative).

**Probability** (share of users exposed): -3 for 0-10%, 2 for 11-20%, 3 for 21-40%, 4 for
41-70%, 6 for 71-90%, 8 for 91-100%.

**Repeatability**: -3 won't happen again, 2 low, 3 moderate, 4 high, 5 almost certain, 6
certain; computed as (successful repros / attempts) x 6. Worked example: 5/5 and 4/5 gives
9/10 x 6 = 5.4, rounded to 5.

Outcomes: **Condition for Resubmission (CFR)** blocks ship, **Standard Reporting Issue
(SRI)**, **Issue of Note (ION)**. Microsoft's worked probability example: "The issue occurs
when launching the title. Probability = 8."

That is a ready-made rubric for the audit skill: score severity x sessions-hit x
reproducibility rather than arguing about whether a bug is bad.

### The test bench

**XR-003** prescribes a five-console bench with deliberately awkward configurations
(documented):

| | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Resolution | 720p | 4K | 1080p | 1080p | 720p |
| Colour depth | 24 | 36 | 30 | 24 | 30 bits |
| HDR | - | **Alternate after 4 hours** | - | - | - |
| Colour space | PC / Standard mixed across the bench | | | | |
| Audio | Stereo | 5.1 Bitstream | Stereo | Headset + Windows Sonic | Stereo |
| Controllers | 1 | 1 | 4 | 1 | 2 |
| Power | Instant-On | Instant-on | Energy Saving | Instant-On | Energy Saving |
| Storage | Internal | Internal | Internal | USB HDD | USB HDD |
| Install | digital | digital | digital | digital | disc |
| Console language | all different | | | | |
| Game settings | "Opposite to default" | "Default" | "**Change the settings every 30 minutes or after each level**" | "first quartile" | "third quartile" |

The equivalent bench for this box writes itself: 4K120 vs 1080p output; eARC soundbar vs
headphones vs TV speakers; disk1 present vs dropped; Kodi cold-start vs restarted; Steam
online vs offline. Worth writing down as a fixed bench rather than testing ad hoc.

### Terminology is a certification item

Xbox **XR-022 Official Naming Standards**, backed by a **27-language** Terminology List.
Mandated English terms include: console, controller, guide, Home, achievement, gamerscore,
gamertag, matchmaking, screenshot, add-ons, downloadable content ("DLC can be used after
first mention"), game clip, Quick Resume, Smart Delivery, A/B/X/Y button, Xbox button, Menu
button, View button, D-pad, left/right bumper ("LB"/"RB" also OK), left/right stick,
left/right trigger, vibration, Share button. Localisations are prescribed per language -
D-pad is "Steuerkreuz" in German, "cruceta" in Spanish (Spain), "pad direccional" in
Spanish (Mexico). There is a separate NDA-only Forbidden Terms List. (documented)

Microsoft's note on the most common failures: "The most common failures are when a title
references competing platforms in text or images... don't reference competing platforms
(i.e. images of a competitor's controller or button call outs)." 022-01 is 2% of all
failures.

PS1 TRC 7.1 does the same in English/French/German plus appendices, right down to "Memory
Card slot 1" and "controller port 2". (documented)

**A one-page terminology table for skin.couch plus the phone app would stop drift.** Is it
"Library" or "Media"? "Games" or "Play"? "Screen" or "Display"? Pick once.

### Miscellaneous rules worth having

- **XR-112**: a title must name its active user on screen **before the first
  profile-related action**, and if the player declines sign-in it must warn that progress
  will not be saved **before** any data is lost. Fail: "notifies after data loss already
  occurred." (documented)
- **XR-045 Respect User Privileges** (11% of all failures): when a restriction blocks
  something, the game must invoke the **system's resolution UI** rather than just refusing,
  so a child can request permission from inside the game. Blocking correctly but silently
  is still a failure. Privilege IDs: 254 multiplayer, 185 cross-network, 252
  communications, 189 shared sessions, 247 user-created content, 220 social sharing.
  Fallback strings are prescribed verbatim, e.g. "Sorry, you're currently prevented from
  playing online multiplayer games." plus a pointer to Settings > Account > Family settings
  > Manage family members. (documented)

  **Generalise it: whenever couchd refuses to do something, the refusal must include the
  route to fixing it - which setting, which screen - not just a "no".**

- **XR-037**: "Game saves with unique content tied to add-on content must still load on the
  base game or provide clear messaging explaining why it can't be loaded", with the message
  shape given: "Content X needs to be installed". Fail: "Game unusable, unable to access
  save without notification." (documented)

  A Kodi entry whose file lives on a dropped disk should say "disk1 is not mounted", not
  just fail to play.

- **XR-129 Intelligent Delivery**: changing the in-game language must **trigger the
  download** of that language's assets, and the user is allowed to cancel the install and
  the title must handle that return value. (documented)
- **XR-048**: games must not persist platform profile data beyond "a locally stored cache
  intended to support scenarios of network disconnection. Any offline caches must be updated
  upon the next available connection to the service." (documented)

  Cache for offline, treat the source as truth, refresh on reconnect. That is the rule for
  Jellyfin/Steam/TMDB metadata.

- **XR-055 / XR-060 Achievements**: minimum 10, maximum 100, exactly 1000 gamerscore at
  launch; semi-annual additions up to 100 achievements / 1000 gamerscore (Jan-Jun and
  Jul-Dec); lifetime 500 achievements / 5000 gamerscore; a single achievement cannot exceed
  200 gamerscore; all must be achievable. And once published, **the unlock rules and rewards
  can never change** - only the text and art. Names/descriptions must be PEGI 12 / ESRB
  E10+ or lower with no profanity "in a clear text or redacted form". (documented)
- **PlayStation has an equivalent requirement**: a Share affordance must use the Share
  icon or the plain word, with no decorating text before or after it. (widely-reported)

  **Pick the noun, do not decorate it.** "Share", not "Share it!".

- **PlayStation has an equivalent requirement**: the tile itself is certified - icon, title,
  background, BGM, startup image and the default save-data icon all have required formats
  and per-language variants, and **the startup image should not be black**. It displays
  until the application shows its own interface. (widely-reported)

  The transition from "tile selected" to "app drawing its own frames" should be covered by
  a deliberate image, never a black frame - which is exactly the gap during a
  Steam/gamescope launch.

- **PS4 submission, reported by a developer**: the two mandatory fixes flagged by Sony were
  "Placeholder icon is used for save data icon" and "The application deletes save data
  without informing the user a deletion will occur." (widely-reported)
- **PlayStation has an equivalent requirement**: the application must periodically yield a
  suspend point while using the GPU, and all graphics pipe processing must complete promptly
  afterwards so the GPU goes idle, with named violation messages emitted when it does not.
  (widely-reported)

  The reason for the rule is so the **system** can reliably take over the GPU - for the
  overlay, screenshots, rest mode. The Linux analogue is making sure a fullscreen game never
  wedges the compositor so hard that Kodi or an overlay cannot come back. That is the same
  territory as the FFCP/xfwm4 compositing lesson already learned here.

- **PlayStation has an equivalent requirement**: remote play, recording, streaming and Share
  Play may not be blocked wholesale - only in sections that genuinely need it (spoilers,
  licensed content, personal information) - and the system shows informational messages at
  the boundaries as recording pauses and resumes. **Scope restrictions to the smallest
  region that needs them, and announce entering and leaving.** (widely-reported)
- **PS1 TRC 10.1**, on robustness against worn hardware: "This title continues to function
  correctly when three or more of the directional buttons on any licensed controller are
  pressed simultaneously", with the stated reason that "After using the control device for
  an excessively long time, the props to support the buttons can become worn away." 10.2:
  "Even if unused buttons are pressed, this title continues to function correctly."
  (documented)

  A drifting DualSense is the modern version of a worn D-pad.

- **PS1 TRC 12.3.4 / 12.3.5 / 12.11.1**: media can be removed and reinserted, and the user
  can cancel, right up until the write actually starts - and **the application's own soft
  reset is disabled while saving**, because normal access cannot be guaranteed if the user
  resets mid-write. 12.12.8 recommends warning the user that resetting, powering off or
  removing the card during a save can destroy data. (documented)

  This is where the modern "do not turn off the console" banner comes from. couchd needs an
  explicit **critical-section** concept: while a write is in flight, disable the shortcuts
  that would interrupt it (PS-hold-to-quit, the phone app's power tile) and show the banner.

- **PS1 TRC 18.1** (Recommended): "Include a 'quick start' functionality that will allow a
  user to bypass the introductory credits or FMV sequences... For example, if the user
  depresses **L1+R1** during the start of the application, the title will bypass
  non-essential title screens." An alternative given: check for a save and auto-load, so the
  publisher logos are only shown the first time. (documented)
- **PS1 TRC 6.5 / 6.8**: no effects or fades on the boot logo; "The screen is cleared
  instantaneously when shifting to the section in the software which displays the image";
  and "The trailing note of the PlayStation logo sound played at start-up must terminate at
  the same time the logo is cleared." The handoff between two owners of the screen must be
  instantaneous and clean - no cross-fade, no dead frame. (documented)
- **XR-003**: the packaging tool silently runs the Submission Validator on every build -
  "Submission Validator isn't a standalone tool that the developer uses. Rather, it's
  automatically called to check an app whenever the `makepkg pack` command is used" - and
  its logs must accompany the submission. Developers cannot opt out or forget. (documented)

### Versioning discipline

Xbox Requirements are at Version 16.3, dated 07/01/2026, with a per-release change table
(the July 2026 release removed XR-083 and folded it into XR-003, and re-added test case
052-05 which had been "accidentally removed in the last update"). Individual XRs carry
their own versions (XR-001 v5.0 11/01/2025; XR-045 v2.0 03/01/2023; XR-115 v1.1
05/01/2021). The Terminology List has its own change history (18 June 2026: "Broad updates
to reflect XBOX rebranding"). (documented)

Sony's PS5 TRC 2021.02 was issued 14 October 2020 and **enforced from 1 February 2021** - a
3.5 month grace period between publication and enforcement. Only requirements marked
**"TEST"** are actually validated by SIE Global Format QA; the rest are stated but
unchecked. (widely-reported)

**Version the rules, date them, keep a change log, give a grace period, and mark which ones
are actually enforced versus aspirational.** That distinction - enforced versus stated - is
worth adopting in this project's own conventions.

### Folklore flag

An academic games-degree workshop states that "there will be close to two hundred TRCs",
that "a set of TRCs must be adhered to 100%", and that licence-holders "often employ a
'three strikes and you're out' policy, whereby all testing on a title will cease if three
minor TRC failures, or one major failure, are found." **This is teaching material, not
quoted policy. Treat the ~200 figure and the three-strikes rule as folklore.**

What survives is the useful distinction it draws: the TRCs "are not focused on finding bugs
in the game, they are focused on ensuring that the software works correctly **within the
constraints of the particular platform**." A compliance checklist is about
platform-citizenship, not quality. Keep those two lists separate.

### What this would mean for couch

- **Cheap.** Adopt the time budgets as couchd watchdog thresholds: something moves by 5 s;
  an animation by 20-30 s; a real percentage by 60 s; over 2-3 minutes without progress is
  definitionally broken.
- **Cheap.** Run the three 8-hour aging tests deliberately: Kodi on the home screen, a game
  paused, the couch app open on the phone. Three different tests, none yet done on purpose.
- **Cheap.** Run "rapidly enter and back out of every menu" against skin.couch and the web
  app. 38% of console certification failures are plain instability.
- **Cheap.** A one-page terminology table.
- **Cheap.** Never show a black frame between "tile selected" and "app draws its own
  frames". Use a deliberate image.
- **Cheap.** Bake validation into the deploy script for skin.couch rather than as a
  "remember to run it" - does the skin still have the include-cache fix, are the grid views
  still enabled, did the settings survive the update.
- **Cheap.** Every refusal names the route to fixing it.
- **Cheap.** A quick-start bypass: a held button, or "you have been here before" state that
  skips straight to the last thing you were doing.
- **Project.** A critical-section concept in couchd: while a write is in flight, disable the
  interrupting shortcuts and show the banner.
- **Adopt.** The FMA scoring rubric for the audit skill, and the versioned/dated/change-logged
  discipline with an enforced-versus-stated marker for this project's own conventions.

---

## 17. Settings information architecture

Worth having as a template, because a settings tree navigable with a d-pad is a genuinely
different problem from one navigable with a mouse.

### Xbox: six top-level groups, six to eight leaves each

(widely-reported for the exact leaf lists)

**General** - the six things a couch user actually changes:
Network settings, Personalization, TV & display options, Online safety & family, Volume &
audio output, Power options.

**Account** (8): Sign-in security & passkey, Payment & billing, Linked social accounts,
Subscriptions, Privacy & online safety, Family settings, Content restrictions, Remove
accounts.

**System** (7): Console info, Storage devices, Updates, Signed-out content restrictions,
Language & location, Backup & transfer, Time.

**Devices & connections** (7): Accessories, Media remote, **Remote features**, Disc,
Digital assistants, Blu-ray, **Mouse**.

**Preferences** (5): Notifications, **Idle options**, Capture & share, Break reminder,
Activity feed.

**Accessibility** (renamed from "Ease of Access", ~9-11 leaves).

Two observations. First, **Xbox ships a first-class Mouse settings page** - a TV shell that
supports a mouse is a real accessibility path. Second, **"Idle options" is a distinct page
from "Power options"**: how long before the screen dims, before the box sleeps, before it
drops the TV input, all in one place.

### PS5's structural habits

- Multiple paths to the same control, documented deliberately (section 4).
- Settings that only appear when the relevant hardware is present (section 12).
- Read-only information pages alongside the controls (section 11).
- **Game Presets** - Settings > Saved Data and Game/App Settings > Game Presets - system
  defaults that games query before first launch, so you never see their setup screens:
  Difficulty; Performance Mode or Resolution Mode; First-Person View (invert/pan per axis);
  Third-Person View (invert/pan per axis); **Subtitles and Audio** (subtitles on, and audio
  language = console language or original); Online Multiplayer Sessions. "These settings
  apply only to PS5 games. Some settings may not apply to all your games." (documented)

  No Steam equivalent exists. But the transferable idea - a single system page for things
  you set once and want honoured everywhere (subtitle default, preferred audio language,
  stick inversion) - is something Kodi can do for media even if Steam ignores it.

- **Named presets that visibly degrade to "Customize" when touched.** Parental controls
  offer three levels (Late Teens or Older, Early Teens, Child), and: "You can also change
  specific settings in a preset restriction level. When you do this, the restriction level
  changes to **Customize**." (documented)

  That pattern is valuable well beyond parental controls: the user always knows whether they
  are on a supported configuration. Good for display and audio presets on a box with
  hand-made modelines.

### What this would mean for couch

- **Cheap.** Target six top-level buckets with 6-8 leaves each. Copy Xbox's **General**
  six almost verbatim - network, personalisation, display, safety, audio, power - and we
  cover almost every real need.
- **Cheap.** Add the pages we plainly lack: **Console info** (name, kernel version, couchd
  version, uptime, OS version - currently requires SSH), **Idle options** as a single page,
  and **Remote features** as the home for the couch app and its wake behaviour.
- **Cheap.** A "Screen and audio preset" that degrades visibly to "Custom" when touched.
- **Cheap.** A media-side Game Presets equivalent: default subtitle on/off, preferred audio
  language, set once and honoured everywhere.
- **Direct gap.** There is currently no single place that says what happens after 10, 30 and
  60 minutes of nothing. TV wake, light dimming, screensaver and disk spin-down are
  independent daemons with independent timers. One Idle page would make that legible - and
  couchd is the right component to own it, because it is the only thing that knows a Steam
  game is running.

---

## 18. Achievements and trophies as a runtime surface

We already have the shelf, the Steam Web API pipeline and the PS4 TRP pipeline, so this is
about presentation rather than data.

### PS5 trophies

- The **trophies card** in the Control Center. Anatomy: A) Trophy stats, B) Pin to Side,
  C) Sort by, D) Pinned trophies, E) Available trophies ("Trophies appear based on your
  progress", with a View All Trophies escape). (documented)
- **You can pin up to five trophies per game.** (documented)
- Rarity has four documented tiers: **Ultra rare, Very rare, Rare, Common**. (documented)
- Auto-capture: Settings > Captures and Broadcasts > Auto-Captures > Trophies: **Save Trophy
  Screenshots**, **Save Trophy Videos**, **Trophy Video Duration** - each filterable by
  trophy grade. Media Gallery has a dedicated **Trophies** tab: "Watch a video clip of the
  moment you unlocked a trophy." (documented)
- **Trophy lists became vertical (rather than a horizontal card row) in 21.02-04** - a
  useful warning about card-row overuse. (documented)
- Trophy progress shows in the corner when a game is highlighted on the home row, broken
  down by Gold/Silver/Bronze since 21.02-04, not just a percentage. (documented)
- List shape rules (widely-reported, community-documented): a trophy list and all its DLC
  trophies cannot exceed **128 trophies** total; DLC packs cannot exceed **200 points**
  each; a list containing a platinum has a minimum total of **1,260 points**.

### Xbox achievements

- **Game activity** is a whole Guide tab dedicated to the currently running title -
  achievements, progress and challenges for **that game specifically**. Documented path for
  viewing achievements in-game: open the guide, go to Game activity > Achievements.
  (documented)
- A setting to **hide games with no achievements** from achievement views, with its own
  support article. (documented)
- Rare achievements (below **10%** unlock rate) get a distinct "epic" sound, a diamond
  glyph, and roughly **eleven seconds** of dwell versus a few seconds for standard.
  (widely-reported)
- Profile badges surface in the Guide: viewing a profile shows the **five most recently
  unlocked** badges, recency-ordered. (documented)
- Certification caps and immutability rules are in section 16. Note that **055-01
  Achievements is the 5th most common certification failure at 7%**, purely because
  achievements do not fire when their criteria are met. (documented)

### What this would mean for couch

- **Already done.** The shelf, the Steam Web API and PS4 TRP pipelines, the ESFM trophy key
  at `~/.config/couch/ps4-trophy-key`. Note the standing Kodi-restart cache gotcha.
- **Cheap.** Tier the unlock toast: one longer, distinct sound and a longer dwell for the
  rare/platinum case; one shared treatment for everything else. Two sounds, not four.
- **Cheap.** "Five most recent" is a better default than "rarest" or "all" for a glanceable
  strip.
- **Cheap.** Hide entries with no achievement data - emulated and non-Steam titles will
  otherwise pad the list with empty rows.
- **Cheap.** Pin a small number of in-progress achievements (five is Sony's number) rather
  than showing everything.
- **Cheap.** Test the pipelines against a known-earned trophy. Achievements silently not
  firing is the 5th most common console certification failure and it would look identical
  here.
- **Project.** A context-sensitive "this game" pane in the overlay while a game runs, which
  is where people actually want it. Today the shelf lives on Home.
- **Design decision.** Steam achievements and PS4 trophies have incompatible shapes - Steam
  has no points, PlayStation has grades and a platinum. Pick one visual grammar and
  normalise, rather than showing raw numbers that mean different things side by side.
- **Rule.** Never retroactively change what an earned thing meant. Sony and Microsoft both
  allow text and art edits and forbid changing unlock rules and rewards.
- **Warning from Sony's own retreat.** Both the 21.02-04 reversion from horizontal trophy
  cards to a vertical list, and version 24.06-10.00.00's "Game hubs now only display
  activities that are currently in progress", are arguments for keeping the shelf short.
---

## 19. Social features: none for this box, but the mechanics are worth stealing

Nearly all of this is irrelevant to a single-user private box. It is kept short, and only
for the transferable mechanics.

- **Game Base** is a Control Center control with tabbed sub-screens: Friends, Parties,
  Messages, and since 24.04-09.40.00 a **Discord** tab. The Parties tab groups into
  **Joinable / Recent**, and since 24.01-08.60.00 the Recent list lets you **restart a past
  party in one action**. An **ON AIR** badge marks a joinable party where someone is sharing
  their screen. (documented)

  *Transferable:* a "Recent" list that lets you re-enter a previous **configuration** in one
  press. Good pattern for re-launching a game with the same gamescope wrap options.

- **Parties cap at 16.** Two types - Open (friends of members can join uninvited) and Closed
  (invite only) - with a third modifier, "Require Request to Join", available on Open
  parties. Party link sharing generates a **QR code you scan with a phone** to get a URL.
  (documented)

  *Transferable:* the couch app at :8790 could be reachable by a QR code shown on the TV.
  Far nicer than typing an IP.

- **Share Play sessions terminate automatically after exactly one hour.** "A Share Play
  session lasts for one hour and automatically ends one hour after the visitor joins." The
  visitor's own game is suspended for the duration, and an online game's connection ends and
  must be manually reconnected. Minimum 2 Mbps up and down recommended for both parties. Only
  the host earns trophies; visitors cannot capture; when the host navigates away the visitor
  sees a standby image. (documented)

  *Transferable:* a hard, stated time limit on an expensive session is more honest than
  silent degradation.

- **Share Screen viewer interaction** uses a modifier-plus-face-button gesture: left stick
  moves a pointer, X pings, hold X and move to draw, and "Press and hold the R2 button and
  then press one of the action buttons, each of which corresponds to a reaction. Release the
  R2 button to send the reaction. You can send bigger reactions by pressing one of the action
  buttons multiple times before releasing the R2 button." Host controls this with a "Viewer
  Interactions" toggle and a "Reactions Position" setting. (documented)

  *Transferable, and genuinely clever:* hold a shoulder to enter a transient modifier layer
  where the four face buttons become four verbs, and the **count of presses before release is
  a magnitude**. A compact way to add verbs to a pad without menus.

- **Sharing limits are published rather than discovered at submit time**: "You can share only
  one video clip at a time. You can share a maximum of four screenshots at a time. When
  sharing a video clip with a group, the time limit is 3 minutes." (documented)
- **Game Help** is a card, gated per-objective, with **spoiler suppression** - spoiler content
  "appears as hidden activities" requiring an explicit reveal. Community Game Help is opt-in
  with a "Monthly Capture Limit"; opting out permanently deletes your published videos.
  (documented)

  *Transferable:* spoiler-gating. Hiding a list entry's text behind an explicit reveal is a
  nice touch for a media library showing episode titles and synopses.

- **Tournaments** are a single card carrying a whole scheduling state machine: Register now >
  View All Details (estimated playtime, number of players, format) > Register > accept rules;
  notifications when starting soon, when your match is coming up, when a match ends; a bracket
  view; and documented failure semantics - quitting hands the win to whoever stays, missing a
  match is an automatic loss, ties are settled by coin toss. Included only to show that a
  mature shell will build an entire state machine into one card type. (documented)
- **Sign-in is decoupled from play.** Xbox Wire, Aug 2020: "You will be able to sign in on as
  many Xboxes or Xbox Apps as you want, all at the same time... you'll be able to play on one
  device at a time so all your progress, achievements and saves stay up to date." Signing in
  elsewhere evicts the older session (SPOP), and Xbox's message for it is deliberately
  low-drama: **"Signed out elsewhere"**, with Microsoft's own gloss - "This message means that
  you used a different XBOX console the last time you signed in to your profile. If this is
  true, go ahead and have fun. The message is just a notification." Signing out everywhere
  "may take up to 24 hours". (documented)

  *Transferable:* Steam does the same thing and explains it far worse. And the tone of
  "Signed out elsewhere" is a masterclass for any state-change notice that is 99% benign and
  1% a security signal. Also: stating a propagation delay out loud beats implying instant.

- **The pad is the identity token.** On Xbox a pad is bound to a profile so the Xbox button
  signs that person in; on PS5 a pad is bound to a player slot and a PSN account. Profile
  switching lives in the Power Center / Control Center rather than a login screen. (documented)

  *Transferable, and it frames an open question here:* **no auth prompt should ever appear on
  the TV.** That makes the couch app's current lack of auth a defensible choice for the TV
  surface and an open question only for the network surface.

- Online status persists across logout rather than resetting ("The next time you log in, you
  keep the same online status from when you last logged out.") - a small honesty about state
  that applies to any mode the user can set, such as a "do not wake the TV" mode. (documented)

---

## 20. Every hard number in one place

Useful as a reference and as a set of targets. Confidence as marked earlier in the document.

### Time budgets and thresholds

| Number | What |
|---|---|
| 5 s | PS1 TRC 18.7 - max blank screen; loads over this must notify |
| 20 s | Xbox XR-001 - max non-interactive pause or static screen |
| 2 min | Xbox XR-001 - max loading screen with **no** progress indicator |
| 3 min | Xbox XR-001 - max loading screen **with** a progress indicator |
| ~1 s | Xbox - time a game gets to save state after suspend is signalled |
| 10 min | Xbox - out-of-focus duration that triggers system suspend |
| 8 hours | PS1 TRC 5 - aging test, x3 (attract, paused, unattended screens) |
| 500 ms | SDL `BLUETOOTH_DISCONNECT_TIMEOUT_MS` for a DualSense |
| 300-500 ms | Common threshold before escalating to a visible busy indicator |

### Motion

| Number | What |
|---|---|
| 150 ms / 300 ms | Forward Out / Forward In page transition; leaving is half of arriving |
| 150 px | Slide distance for page transitions |
| 50/100/150/200/250/300/400/500 ms | Fluent 2 duration ladder; nothing exceeds 500 ms |
| 83 / 167 / 250 ms | WinUI control durations (5, 10, 15 frames at 60 Hz) |
| 300 ms expand / 150 ms contract | Object grow-shrink, exactly 2:1 |
| `cubic-bezier(0,0,0,1)` | Entering |
| `cubic-bezier(1,0,1,1)` | Leaving |
| ~150 ms tile / ~400-500 ms backdrop | PS5's deliberately decoupled home-screen timings |
| 9 s → 4 s, 20 s → 15 s | Xbox boot animation and cold boot, cut in 2022 |
| 12 s → 7 s | Xbox cold start, cut again May 2026 |
| ~10 s | Xbox Series X launch boot chime length |

### Text and accessibility

| Number | What |
|---|---|
| 26 px | XAG 101 minimum console body text at 1080p |
| 52 px | XAG 101 minimum console body text at 4K |
| 200% | Required text scaling headroom |
| 80 chars | Max line width (40 CJK) |
| 1.5 / 2x / 0.12x / 0.16x | Min line spacing / paragraph spacing / letter spacing / word spacing |
| 32 px → 46 px | Xbox store tag subtitle size and scaling |
| 4.5:1 | Xbox store tag contrast minimum |
| ±50% | Xbox store tag sensitivity range |
| 30 min | Xbox store tag - tester gameplay engagement time |
| 16x | Xbox Magnifier maximum |

### Power and storage

| Number | What |
|---|---|
| 0.35 W / 1.3-1.5 W / ~3.2 W | PS5 rest: everything off / network standby / charging a pad |
| 0.5 W | PS5 rest floor with no features; Xbox Shutdown |
| 10-15 W | Xbox Sleep |
| 20x | Microsoft's stated Shutdown-vs-Sleep power ratio |
| 2:00-6:00 AM | Xbox maintenance window, once every 24 hours |
| under 5 s / ~15-20 s | Xbox boot from Sleep / from Shutdown |
| under 14 s | Sony's claimed PS5 cold boot |
| 5-14 s | Community-measured PS5 rest-mode resume (high variance) |
| 20 min / 1 hour | PS5 minimum idle-to-rest for gameplay / for media playback |
| 1, 2, 3, 5 hours | PS5 idle-to-rest intermediate steps |
| Off / 3 Hours / Always | PS5 rest-mode USB port power |
| 10 / 30 / 60 min | PS5 controller idle-off options; Xbox is a fixed ~15 min |
| 13.5 GB / ~40 GB | Xbox Quick Resume per-title snapshot / total reserve |
| ~3 titles | Xbox Quick Resume concurrent (a byte budget, not a slot count) |
| 5-10 s | Xbox Quick Resume time to resume |
| 1 GiB / 5 min | Xbox XR-133 local storage write cap |
| 10x | Xbox XR-132 service-call overrun that fails certification |
| 2 GB | Xbox temporary local storage (T:) |
| 250 GB - 8 TB | PS5 USB extended storage size limits, 5 Gbps+, no hubs, one at a time |
| 100 GB + 100 GB, 1000 files | PS5 cloud save quota (PS5 + PS4, max PS4 file count) |
| ~2x package size | Free space actually needed to install (both platforms, community) |
| 192 Kbps | Xbox XR-074 bandwidth floor below which nothing may crash or lose data |

### Caps, counts and limits

| Number | What |
|---|---|
| 10 games + 10 groups | Xbox Home pins (groups was 2 until April 2026) |
| 3 | Xbox pins inside the recently-played row |
| 15 lists x 100 games | PS5 gamelists |
| 15 | PS5 "Recently created" capture card |
| 15 s to 1 hour | PS5 retroactive "Save Recent Gameplay" range; manual recording caps at 1 hour |
| 5 | PS5 pinned trophies per game |
| 5 | Xbox recent badges shown on a profile |
| 128 / 200 / 1,260 | PS trophy list total / DLC pack points / minimum points for a list with a platinum |
| 10-100, exactly 1000 | Xbox achievements and gamerscore at launch |
| 500 / 5000 | Xbox lifetime achievement and gamerscore caps |
| 200 | Xbox max gamerscore for a single achievement |
| below 10% | Xbox "rare" achievement threshold |
| ~11 s | Xbox rare achievement toast dwell |
| 16 | PS5 party voice chat maximum |
| 60 min | Share Play hard stop |
| 1 clip / 4 screenshots / 3 min | PS5 sharing limits |
| 4 / 8 | PS5 / Xbox simultaneous controller limits |
| 4 | Devices a DualSense can be paired to (25.06-12.00.00) |
| 45 | Files in the circulating PS5 system SFX rip |
| ~290 | Public PS5 error codes |
| 27 | Languages in Xbox's mandated terminology list |
| ~134 | Xbox dynamic backgrounds |
| 6 / 5 | Xbox Guide top tabs / bottom utility tabs |
| 30 / 3 / 19 / 23 | Access controller profiles on console / cached on pad / button caps / labels |
| 50% / 80% | Xbox chat mixer ducking levels |
| 125 Hz | Xbox DLI hard cap (2 ms floor, self-disabling) |
| 1920 x 1080, 2 contacts | DualSense touchpad resolution |
| 8192 / 1024 | DualSense accel counts per g / gyro counts per deg/s |
| 10 steps (5,15,...,100) | DualSense battery reporting granularity |
| 4 levels (10/40/70/100) | Xbox pad battery reporting granularity |
| 1560 mAh, ~3 h charge, 6-12 h use | DualSense battery |

---

## 21. The borrow list, ranked

Consolidated from every section. Ordered by value-per-effort within each tier.

### Already done

PS tap/double/hold/long-hold gesture vocabulary with one shared config file and a safety
rail. The couch switcher and power bar. Home tiles that animate grow/shrink. The
achievements shelf with Steam and PS4 TRP pipelines. tv-waker / tv-waker-webos, light-watch,
4K120 pinned by a service, soundbar on eARC, headphones following the TV. `tools/kodi-restart`
and the no-`pkill -9` rule. game-pids Proton suspend, steam-input-guard, watcher reconcile.
Discord webhook alerting. The modern UI pass and sheet animations. The Remote tab's
TV/soundbar volume card.

### Cheap, and do these first

1. **Decide wrap-versus-bump for every list**, and give the bump a sound and a pad rumble.
   `ff_memless` is already loaded.
2. **The notification matrix**: category x context (during video / during a game / on home),
   plus display time, plus position, plus a session-scoped DND that clears on restart, plus a
   small unsuppressible tier.
3. **The error registry**: stable short IDs, one plain sentence each, reused freely, rendered
   identically on TV and phone. One cause, one device, one sentence. Never a raw errno.
4. **Two idle timers**, split for gameplay versus media playback, driven by actual playback
   state rather than input idleness, plus a cancellable 30-second warning toast.
5. **Adopt the motion tokens**: the 8-step duration ladder, the two curves, the 150/300
   asymmetry, the 2:1 expand/contract rule, decoupled tile-versus-backdrop timings, and no
   busy indicator under ~300 ms.
6. **Audit body text against 26 px at 1080p / 52 px at 4K.** Probably currently failing.
7. **Pad status surfacing**: three-bar battery (never a percentage), connect/disconnect
   toasts, repeating low-battery warning that fires during a full-screen game, charging fault
   states, lightbar dimming during films.
8. **Cache artwork locally and pin it.** Offline must look identical to online. Sony got this
   wrong in public.
9. **A read-only display state page** - what the sink actually claims - plus greyed-out
   unsupported modes with the reason.
10. **Reduce motion**, split into motion and background imagery, honouring
    `prefers-reduced-motion` in the web remote.
11. **Home row cap with replace-oldest, hide-system-entries, and three sticky slots.**
12. **A one-page terminology table** for the skin and the app.
13. **Session-level rules**: every refusal names the fix; retry transiently before reporting;
    cancel always works; never auto-fail-over between disks; never auto-format; no
    "delete all" on a phone screen.
14. **Run the three 8-hour aging tests and the rapid-menu-thrash test.**

### Projects, roughly in order of value

1. **Controller-disconnect handling.** Freeze the game on losing the active pad, show
   "Reconnect your controller - press PS", resume on re-association. 500 ms detection window.
   No PC game does this; couchd can.
2. **The overnight maintenance window.** `rtcwake` or a `WakeSystem=true` timer at ~03:30:
   Steam depots, apt/flatpak, Jellyfin/Bazarr scans, disk-monitor pass, then back to sleep,
   with an on-screen record of what actually completed.
3. **The overlay over a live game.** Compositing the shell over a running gamescope surface
   without suspending it, with the rule that the overlay never freezes and only Home does.
4. **Suspend one game, and make resume the default action on wake.** Per-title "never
   suspend" flag. `suspend-then-hibernate` is the closer analogue to Quick Resume and would
   survive a power cut.
5. **Make resume look like nothing happened.** Hold a frame over the DPMS/modeset/X11 ugly
   part; force a clean restart if no frame renders N seconds after a resume request. Note that
   Kodi enumerates display modes once at startup.
6. **Learned Active Hours** with a manual override.
7. **The recovery ladder**, reachable without a keyboard and ideally without a working
   display, with a "reset video output" rung and every rung annotated with what it keeps.
8. **A single Manage destination** for downloads, updates, disk state and prefixes.
9. **Suspend-in-queue**: a phone button that suspends the running game so a download finishes
   at full speed, then resumes.
10. **A per-game hub** aggregating achievements, playtime, compat notes, wrap status, install
    size and the launch button.
11. **Fault injection** in couchd, so disk-full / disk-unmounted / Kodi-unresponsive /
    Steam-offline can be tested at will rather than at 2am.
12. **Compositor zoom** on a pad chord, with confirm/cancel semantics.
13. **The DualSense touchpad as a real pointer and text-entry device.**
14. **A critical-section concept**: disable interrupting shortcuts and show the banner while a
    write is in flight.
15. **Back up settings to USB**, and a bootable recovery image (mitigating the no-A/B-partition
    brick risk).
16. **An on-box help page** describing this box's own quirks.

### Not worth it

Matching 0.5 W standby. Multi-game Quick Resume. Per-game hover music. Pin to Side over a
Steam game on X11. Adaptive triggers and voice-coil haptics from the shell. Copilot-style
input merging (name it as a gap instead). Chat transcription and the whole social layer.
Entitlement sub-sectioning in the library. A full factory-reset flow. Verifying accessibility
metadata for Steam titles.

---

## 22. Not covered - worth a second pass

The twelve research passes were organised by system area, and that left real holes. These are
listed so they are visible rather than hidden. Roughly in order of how much they matter for a
couch shell.

Two structural caveats first. The accessibility pass was **truncated mid-report** (it cuts off
inside the Xbox Magnifier item), so the Xbox half of section 15 is thinner than the PS5 half
and there is almost certainly more there. And two of the twelve passes - one on **accounts and
profiles**, one on **refusals** (what consoles decline to do, and their latency budgets) - are
referenced by the critique but were not available in full when this document was written, so
their material is only partially reflected here.

1. **Text entry and search.** The single biggest omission. Nothing on the on-screen keyboard:
   grid versus QWERTY layouts, L1/R1 case-shift, per-character click sounds, hold-to-repeat
   backspace, predictive/autocomplete strips, password masking with a "show" toggle, using the
   phone companion app as a keyboard, voice dictation into a field, Bluetooth/USB keyboard
   support, search-as-you-type, recent-search history. A Wi-Fi password is the single most
   painful thing a normal user does on a console.

2. **Save data and the "do not turn off" grammar.** Cloud upload/download, sync-conflict
   dialogs, save data management UI, per-game save size, upload-on-suspend, corrupted save
   handling, save transfer between consoles, autosave spinner/icon conventions, and the
   certification-mandated "do not turn off the console while this icon is displayed" rules. The
   certification pass covered pause and load limits but not the save-in-progress indicator
   rules, which are a TRC/XR staple.

3. **Achievements as a runtime surface.** Section 18 is assembled from fragments. Missing: the
   pop-in toast animation itself, progress-tracked achievements and the "3/10" mid-play toast,
   rarity percentages as displayed, per-game completion rings, hidden achievements, Challenges,
   Milestones, "recently unlocked" feeds, friend comparison.

4. **Media playback and transport controls.** The Explore/Media split is named but not what
   happens inside it: transport bar layout, scrub with stick versus d-pad, skip 10 s / 85 s,
   chapter jump, subtitle and audio-track switching mid-playback, resume-where-you-left-off
   prompts, the PS5 and Xbox Media Remote button maps, play/pause/stop mapped to pad buttons in
   media apps, screensaver suppression during playback. Plus the disc drive: insert/eject,
   spin-up, UHD Blu-ray playback UI, "insert disc" prompts, disc-required checks, eject while
   the console is off.

5. **First-run setup (OOBE) and calibration wizards.** Language/region/timezone, network setup,
   account sign-in and QR/phone handoff, pairing the first controller over USB, the HDR
   calibration three-image ramp, the Xbox TV & display calibration app with its test patterns,
   "does this look right" confirmations with a revert-in-15-seconds timer, resume-setup-later.

6. **Networking as a user surface.** Wi-Fi list and signal bars, connection test with measured
   download/upload and NAT type A/B/C, "connected to PSN/Xbox network" state, offline mode and
   what silently degrades, sign-in-expired reconnection, download speed limiting while playing,
   pause/resume/reorder in the download queue, per-download progress and ETA, and what a
   download does when the game it belongs to is launched.

7. **The transition into and out of a game.** The launch sequence (tile press, card fade, black
   gap, publisher logos, game boot), how you actually close a game (PS5 options menu "Close
   game", Xbox menu on tile), the "unsaved data may be lost" confirmation, what the shell shows
   while a game shuts down, and where focus lands when you return to Home.

8. **Empty states, placeholder art and asset loading.** Skeleton/shimmer tiles, art that pops
   in after the row is drawn, fallback icons for games with no box art, "no captures yet" /
   "no games installed" screens, offline states where network art is unavailable, and the local
   art cache and its invalidation. Exactly the mundane layer a Kodi skin lives or dies on.

9. **Focus mechanics at the millisecond level.** D-pad initial repeat delay and repeat rate,
   acceleration on hold, analog stick deadzone and step behaviour in menus, page-jump on
   bumpers and triggers, alphabet jump bars, scroll-position memory when you return to a
   screen, focus restoration after a modal, marquee and ellipsis behaviour on focus. Section 4
   flags the available numbers as folklore precisely because this was not covered properly.

10. **Idle, screensaver and burn-in mitigation.** UI dimming after N minutes, the screensaver's
    own motion, "press any button" resume, static-logo dimming, HDR UI brightness caps, and how
    all of it interacts with media playback and OLED panels. Directly relevant to a C5.

11. **Confirm/cancel button grammar and dialog conventions.** Section 4 has the semantics but
    not: Sony's unification of Cross-to-confirm including Japan, hold-to-confirm progress
    rings, destructive-action confirmation wording, whether Back ever exits a dialog, and where
    default focus sits in a two-button dialog.

12. **Comparison platforms with no coverage at all.** The whole set is PlayStation and Xbox. A
    couch shell's real peers are **Nintendo Switch** (HOME-hold Quick Settings, dock
    transitions, a famously terse sound set), **Steam Big Picture and Steam Deck** (Quick Access
    Menu, per-game performance overlay - and the closest analogue to what we are building),
    **Apple TV and Google TV** (focus engine, parallax art, the Siri Remote). Their conventions
    are directly borrowable and are entirely missing. This is probably the highest-value second
    pass after text entry.

13. **Remote play, cloud gaming and the phone as a second screen.** PS Remote Play and Xbox
    Remote Play session handover, wake-from-standby to stream, cloud gaming with no install,
    streaming to a phone or handheld, the companion app as remote control and notification
    mirror, QR-code sign-in. This is the closest analogue to the product being built and it is
    barely covered.

14. **Voice control and assistants.** "Hey Xbox", the Cortana era and its removal, Alexa and
    Google Assistant integration, PS5 Voice Command (Preview) beyond the fragments in section 1,
    voice search, pad-mic push-to-talk versus system voice. Relevant given the Vulkan whisper
    work.

15. **Store, purchase and licence/DRM behaviour.** Purchase confirmation and PIN, wallet and
    gift cards, redeem-a-code, wishlist, pre-order and pre-load with an unlock countdown,
    refunds, demos and trials with timers, subscription upsell interstitials, and the launch-time
    licence check: primary/home console, playing offline, "cannot start this game, licence could
    not be verified", disc-in-drive checks.

16. **Parties, voice chat and invites as live state.** Party creation and join, invite toasts and
    their accept flow, join-someone's-game, chat audio ducking of game audio, the game/chat
    balance slider, per-person mute, push-to-talk, mic monitoring, and what happens to a party
    when you launch a different game.

17. **Background music and third-party audio apps.** Spotify or Apple Music playing under a
    game, controlling it from the guide, ducking against game audio and chat, and what stops it
    (a media app launching, a video playing).

18. **Peripheral detection and handling.** The USB-drive-inserted toast and format-for-games
    flow, headset connect/disconnect toasts, keyboard and mouse support and where it works,
    arcade sticks and third-party pad quirks, camera, VR handoff.

19. **Personalisation and identity surfaces.** Avatars and gamerpics, profile colours and
    backgrounds, dynamic themes, the online-status indicator, custom console names, and what a
    profile picture is used for across the shell.

20. **Content rating and age gating at runtime.** Store age gates, mature-content blur and
    reveal, PIN prompts to launch a restricted title, the play-time-limit countdown toast and
    forced sign-out, and how a restricted account sees a library it cannot launch.

21. **Console status lights and physical affordances.** Beyond the PS5 LED table and chassis
    beep: the Xbox button light, disc eject and pair buttons, LED brightness settings, fan noise
    as feedback, and what each light means during update or safe mode.

22. **Localisation, region and time.** Language switching and what needs a restart, per-title
    language packs and optional install pieces, region locking, date/time and NTP, 12/24h clock
    in the guide, units, keyboard layouts, and text expansion breaking layouts.

23. **Privacy, telemetry and consent surfaces.** Data-collection consent screens, privacy
    settings controlling who sees your activity, presence sharing, "hide game being played",
    screenshot/broadcast restrictions a game can impose on system capture, block and report
    flows.

24. **Degraded operation beyond the error taxonomy.** What the shell does with a failing storage
    device over time, running with a full drive, running with a broken network mid-download, a
    corrupted install detected at launch and the repair path, and the report-this prompt after a
    crash-to-dashboard.

### Thin counts worth deepening rather than re-scoping

- **Motion and sound (52 observations)** has global tokens but no **per-screen inventory** -
  what exactly animates when the guide opens, when a tile is focused, when a toast enters and
  exits, when a sheet dismisses - and no catalogue mapping the ~45 PS5 sound files to the events
  that trigger them.
- **Power and standby (47)** has no measured **boot-to-home** or **wake-to-input** timings and no
  description of the cold-boot chime and logo sequence beyond length.
- **The refusals pass (53)** names latency budgets but no measured numbers for guide open, tile
  focus response, app launch, or input-to-photon. Those four numbers would be worth more than
  another fifty behaviours.
