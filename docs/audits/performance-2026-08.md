# Efficiency audit: the whole couch stack (8 Aug 2026)

Scope: the phone app (Svelte `web/` + Node `server/`), the Kodi/TV side
(`games.py`, `skin.couch`, the art pipeline), and the transition machinery.
Production — the living-room TV on Kodi 21.3 and the phone server on :8790 —
stayed green throughout; the set never left standby and Bloodborne stayed
suspended.

Prior art read first, so nothing already shipped is re-reported:
`docs/transition-speedups.md` (6 Aug) and `docs/transition-latency-budget.md`.
**Batch 1 of that document is fully shipped** — the resume converge, the launch
cadence, `ensure_big_picture`, the teardown polls, `curtain_show`'s pre-probe,
and `screen.js`'s 700ms guard beat (now `awaitGuardClaim`). Its gated second
batch is still open and still gated (see *Deferred*).

**The stack was already fast.** The Games row listing is p50 **4.1 ms**, Kodi
RPC is **0.22 ms**, the app-start prefetch burst of 7 requests completes in
**97 ms**, and there is no N+1 on any media path. The wins below are mostly
about work that was on the wrong side of a boundary — in front of the user
rather than behind them, or sized for the television and sent to a phone.

## Shipped, with measurements

| # | Finding | Before | After |
|---|---|---|---|
| 1 | **`/api/windows` rebuilt the world on every ask** — a python spawn and an X walk, in front of the switcher sheet, which is a *gesture* | 215 ms | **0.7 ms** warm |
| 2 | …and its cold path ran three subprocesses nose to tail when only two were dependent | 210 ms | **159 ms** |
| 3 | **Nothing compressed anything** — no middleware, and no `encode` in Caddy either | library 48.6 KB | **17.9 KB** (−63%) |
| 4 | **Game art is cut for a 4K television and was sent whole to a phone tile ~117 px wide** — and the biggest was the FIRST tile, so lazy loading never saved it | 1.30 MB per Games tab | **316 KB** (−76%) |
| 5 | — the Bloodborne tile alone | 947 KB | **45 KB** (−96%) |
| 6 | **Reading TV volume on every Remote mount** — Remote is the default tab | 3.18 s | **0.001 s** cached |
| 7 | **`onMount` + `$effect` both fire at mount in Svelte 5** — three components fetched everything twice; House dialled the TV and the bulbs twice per visit at 3.26 s and 2.58 s each | 2× | 1× |
| 8 | — Screen.svelte opened **two MJPEG streams and abandoned the first**, in a file whose own comments record a stale Safari MJPEG socket as a past bug | 2 streams | 1 |
| 9 | **Games and Services were never prefetched** — Games is the tab reached in a hurry | cold on arrival | warm at +400 ms |
| 10 | **Install size was computed in the listing and cached under the game folder's own mtime**, which never moves when content grows in subdirectories | Bloodborne read **29.3 GB** for a 40.5 GB game, permanently | **41 GB**, measured hourly off the critical path |

Finding 10 is a correctness bug that a performance audit found, and the fix is
the performance fix: the miss path was a 28,778-file `os.walk` (267 ms) with
the player waiting on a directory listing. Invalidating harder would have made
the stall *more* common. The walk moved to `tools/warm-game-sizes`, on the
hourly slot that already warms achievements, heroes and loading cards.

Verification: 997 python tests, 70 server tests, new suites for the window
memo, the size warmer, and the app-edge fixes. Finding 10 was confirmed on the
television by screenshot after a Kodi restart through the hardened path.

## Checked, and NOT changed

Four things that looked like findings and were not. Each was measured before
being believed, which is the only reason they are in this column.

- **`/api/art/game`'s 1-hour cache.** Reported as "the whole 1.24 MB refetches
  hourly". It does not: the route emits an ETag and revalidation returns
  **304 with 0 bytes**.
- **409 KB of font files.** `unicode-range` means a UK phone fetches only the
  latin subsets (~79 KB), already woff2. Trimming the rest is a deploy-size
  tidy, not a speed win — and gzip makes every woff2 *larger*.
- **`imageres 1440 / fanartres 2160`.** Deliberate for a 4K GUI, and the whole
  Thumbnails cache is only 31 MB. Do not revert.
- **Jellyfin's `startupDelay=45`.** It outlived the Kodi 20 crash it mitigated,
  but Home is unaffected and only the Library is stale for 48 s. Changing it
  blind buys little and risks the boot churn window.

Also verified good and left alone: hashed immutable assets, a proper
stale-while-revalidate store with cold-gated skeletons, `aspect-ratio` on every
image so there is **no layout shift anywhere**, correct `loading="lazy"`,
optimistic UI already on play/pause/seek/speed/volume/TV-power, keyed lists,
debounced search and volume, visibility-gated polls, MJPEG backpressure and
eviction with no stray ffmpeg, and the Games row hot path itself (4.1 ms, only
possible because `reuselanguageinvoker` keeps the interpreter warm — another
reason not to retire that flag by reflex).

## Deferred

**[A], specified and ready, not done today**

- **Composed row tiles are the only art asset with no background warmer.**
  `games.py:225-258` composes inline on a miss: **96–181 ms per game, 706 ms
  for all five**, and it demonstrably happens — heroes stamped 05:45, composed
  tiles 05:47, one listing paying ~506 ms in front of the player.
  `tools/warm-loading-cards` is the precedent and already walks the same
  targets. This is the largest remaining TV-side win.
- **Jellyfin posters at `quality: 90`** (`index.js:741`): 55,852 B → 39,738 B
  at q80 (−29%) for the same item; width is already correct.
- **Sonarr `seriesByTmdb` refetches the full series list — 186,954 B — on
  every lookup**, uncached. Radarr already avoids this twice over (15 s cache
  plus a filtered endpoint: 11,830 B vs 696,513 B). Copy Radarr's pattern for
  the read path only.
- **JSON responses carry an ETag but no `Cache-Control`**, so revalidation is
  heuristic. `/api/downloads` is polled every 5 s.

**[B], needs a block or a ruling**

- House keeps TV/lights/health in component-local state, so it shows
  "Loading…" and re-dials the hardware every visit — that is where the 3.26 s
  lives. Wants the shared cache the media tabs already have.
- Remote re-reads TV volume on mount at the same standby cost, on the default
  tab. Finding 6 caches it; the mount itself could be deferred.
- `/api/windows` could reach **53 ms** with shadPS4 class recognition, but that
  needs a ruling on the identity predicate.
- `winthumb` spawns ImageMagick per tile, cache-busted on every open.
- Tab switches lose scroll position; game launch has no tap feedback.
- The 6 Aug gated batch: the watcher's 0.2 s select tick (SR4-flagged, needs a
  gesture sweep and a differ evening) and the game-pids/xinput round-trip
  consolidation.

**[C] decided — and one of them then shipped**

- **The Games row still does not rebuild on Home.** The 5 Aug limitation in
  `tools/kodi-refresh-games` predates the Stagelight home, so it was re-tested
  properly: `Container.Refresh` is **still a no-op there**, and there is now a
  reason — `Home.xml` is `KEEP_IN_MEMORY`. This is the answer to the earlier
  open question about how quickly the paused card appears: the *animation* is
  instant (a window property, ~0.2 s after the freeze), but the card's steady
  state and the "· paused" label wait until the player leaves the row and comes
  back. A `<content>` container **does** rebuild when its resolved URL string
  changes (proven live, ~1 s, while unfocused), so making `Home.xml:386`'s
  hand-bumped `&v=8` dynamic would work.

  **SHIPPED the same evening**, once Donnie freed Bloodborne for testing.
  Measured with a real quit: `game-launch quit` cleared the flag at **107 ms**
  and deleted the freeze-frames at **164 ms**, while the row went on reading
  "· paused" and drawing a card whose image file no longer existed — Kodi had
  cached the texture. It was not lag: the row never corrected itself at all.
  The content URL now carries `$INFO[Window(Home).Property(CouchGamesRev)]`
  and `pause-snap` stamps it on every capture and every clear. The focus worry
  was the only reason to hesitate and it was wrong — verified in both
  directions with focus parked on item #4, which stayed on item #4.

**[D] human**

- **The Kodi YouTube plugin is signed out.** `/api/youtube/feed` returns 502
  for both default feeds; `popular_right_now` works, so our path format is
  fine. It costs ~3.5 s on every YouTube tab open and the error-caching in
  `YouTube.svelte:22` retries it forever. Needs Donnie's Google device-code
  sign-in.

## What this audit could still have wrong

- **Fixes verified?** All ten were measured after the change, seven on the live
  service and finding 10 on the television itself.
- **A rubric area skipped?** Playback was never exercised — starting a film
  wakes the TV, which was out of bounds. So the player OSD, seek and the
  cast path are unmeasured under load. Also unmeasured: `/api/art/kodi`, which
  is proxied with no resize and feeds a 116 px hero, a 24 px strip and a
  full-bleed backdrop. Nothing was playing; if that poster exceeds ~200 KB it
  graduates to [A].
- **A fix that broke a neighbour?** The compression allowlist was chosen
  specifically so the MJPEG stream and the silent audio stream cannot be
  touched; verified after — the stream carries no `content-encoding`. The
  window memo is dropped on every act, so the switcher cannot act on a stale
  list.
- **Anything fixed that was not broken?** The four items in *Checked and NOT
  changed* were all candidates that measurement killed.
