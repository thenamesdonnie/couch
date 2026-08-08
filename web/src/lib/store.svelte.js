// Persistent, module-scoped caches so switching tabs shows what was there
// instantly and revalidates in the background (stale-while-revalidate), instead
// of unmounting, refetching and flashing a loader every time. Also prefetches
// the media tabs on app start so their first open is already warm.
import { api } from './state.svelte.js';
import { preload } from './img.js';

export const cache = $state({
  continue: null,
  movies: {},   // keyed by `${sort}` -> { items }
  shows: {},
  discover: null, // { trending, popularFilms, popularShows }
  services: null,
  games: null,    // on-the-box games list
  steamLib: null, // full owned Steam library
  ytFeeds: {},    // keyed by feed name -> results
  upcoming: null, // airing-soon episodes (Coming up strip)
});

// Bumped when the app regains focus/visibility. Data-owning components watch it
// to refresh things that can change outside the app (media downloaded via
// Sonarr/Radarr, games installed, lights toggled by Alexa, TV turned on by the
// physical remote). The active tab is the only one mounted, so only it reacts.
export const ui = $state({ focusTick: 0, pollTick: 0 });

// A manual full refresh (pull-to-refresh, or a focus): bump focusTick so the
// active tab reloads its own data, and refresh the shared caches.
export function refreshNow() {
  ui.focusTick++;
  revalidateCached();
}

function jfArt(item, w = 300) {
  if (item.imageTag) return `/api/art/jf/${item.id}/Primary?tag=${item.imageTag}&w=${w}`;
  if (item.seriesId && item.seriesImageTag) return `/api/art/jf/${item.seriesId}/Primary?tag=${item.seriesImageTag}&w=${w}`;
  return null;
}

export async function loadContinue() {
  const d = await api('/api/library/continue');
  cache.continue = d;
  preload([...d.resume, ...d.nextUp].map((i) => jfArt(i)).filter(Boolean));
  return d;
}

export async function loadLibrary(kind, sort = 'title') {
  const bucket = kind === 'shows' ? cache.shows : cache.movies;
  const d = await api(`/api/library/${kind}?sort=${sort}`);
  bucket[sort] = d;
  preload(d.items.slice(0, 12).map((i) => jfArt(i)).filter(Boolean));
  return d;
}

export async function loadDiscover() {
  const [t, pm, pt] = await Promise.all([
    api('/api/discover/trending').catch(() => ({ results: [] })),
    api('/api/discover/popular?type=movies').catch(() => ({ results: [] })),
    api('/api/discover/popular?type=tv').catch(() => ({ results: [] })),
  ]);
  cache.discover = { trending: t.results, popularFilms: pm.results, popularShows: pt.results };
  const tmdb = (p) => (p ? `/api/art/tmdb?p=${encodeURIComponent(p)}` : null);
  preload([...t.results, ...pm.results, ...pt.results].slice(0, 18).map((r) => tmdb(r.poster)).filter(Boolean));
  return cache.discover;
}

export async function loadServices() {
  const d = await api('/api/services');
  cache.services = d.services;
  return d.services;
}

export async function loadGames() {
  const d = await api('/api/games');
  cache.games = d.games;
  // Warm the tiles the way Library and Discover already warm theirs. Worth
  // doing now that /api/art/game resizes for the phone: the whole row is
  // ~316 KB, where the raw television art was 1.3 MB and preloading it would
  // have been an act of vandalism.
  preload(d.games.map((g) => g.poster).filter(Boolean));
  return d.games;
}

export async function loadSteamLib() {
  // No Steam key configured is a normal state, not an error: cache an empty
  // library so the tab stops showing a loader and doesn't retry forever.
  try {
    const d = await api('/api/steam/library');
    cache.steamLib = d.games;
  } catch {
    cache.steamLib = cache.steamLib || [];
  }
  return cache.steamLib;
}

export async function loadYtFeed(name) {
  const d = await api(`/api/youtube/feed?type=${name}`);
  cache.ytFeeds[name] = d.results;
  return d.results;
}

export async function loadUpcoming() {
  const u = await api('/api/upcoming');
  cache.upcoming = u.episodes.filter((e) => !e.hasFile).slice(0, 8);
  return cache.upcoming;
}

// Refresh whatever is already cached (stale-while-revalidate on demand). Called
// on focus so lists reflect media added inside or outside the app.
function revalidateCached() {
  if (cache.continue) loadContinue().catch(() => {});
  for (const s of Object.keys(cache.movies)) loadLibrary('movies', s).catch(() => {});
  for (const s of Object.keys(cache.shows)) loadLibrary('shows', s).catch(() => {});
  if (cache.discover) loadDiscover().catch(() => {});
  if (cache.services) loadServices().catch(() => {});
  if (cache.games) loadGames().catch(() => {});
  if (cache.steamLib?.length) loadSteamLib();
  for (const f of Object.keys(cache.ytFeeds)) loadYtFeed(f).catch(() => {});
  if (cache.upcoming) loadUpcoming().catch(() => {});
}

// Warm the caches shortly after launch, off the critical path, so the first
// visit to Library or Discover is instant. Also wire the focus revalidation.
let warmed = false;
let lastFocus = 0;
export function prefetchAll() {
  if (warmed) return;
  warmed = true;
  setTimeout(() => {
    loadContinue().catch(() => {});
    loadLibrary('movies').catch(() => {});
    loadLibrary('shows').catch(() => {});
    loadDiscover().catch(() => {});
    // Games and Services were the two tabs left cold. Both are cheap - the
    // games list is ~1ms and 1.5 KB - and Games is the one tab that is
    // reached in a hurry, because the person opening it wants to start a
    // game. Steam's library is deliberately NOT warmed: it can be a slow
    // upstream and nothing on the first screen needs it.
    loadGames().catch(() => {});
    loadServices().catch(() => {});
  }, 400);

  const onFocus = () => {
    if (document.visibilityState === 'hidden') return;
    const now = Date.now();
    if (now - lastFocus < 4000) return; // debounce rapid focus/visibility events
    lastFocus = now;
    ui.focusTick++;      // wakes the active tab's own loaders
    revalidateCached();  // refreshes the shared media/service caches
  };
  document.addEventListener('visibilitychange', onFocus);
  window.addEventListener('focus', onFocus);

  // Gentle background refresh: while the app is visible, quietly revalidate the
  // caches every 30s so the tab you are looking at stays current without a
  // reload. Cached views update reactively; pollTick nudges the non-cached
  // ones (Games list, House health).
  setInterval(() => {
    if (document.visibilityState !== 'visible') return;
    revalidateCached();
    ui.pollTick++;
  }, 30000);
}
