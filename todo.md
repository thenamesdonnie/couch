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

## ▶ Resume here (9 Aug 2026 ~13:40 — overnight build, then a live disk incident)

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
3. **Donnie's sudo session** (~10 min, `couchd/stage2/INSTALL.md`):
   couchd-input group + system user, udev rule (staged `.off`), rollback
   script + sudoers, inputproc.service, rollback REHEARSAL. Plus fix
   pad-connect-daemon + tv-waker's any-`js*` checks (see Open decisions).
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
