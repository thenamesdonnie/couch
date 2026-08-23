// Jellyfin access for the catalogue. Credentials are NOT ours: the jellyfin-kodi
// addon's device token is read from its data.json on every (re)auth, so if the
// addon re-authenticates we follow it. Nothing here writes to Jellyfin beyond
// what browsing needs.
//
// The catalogue is scoped to the library views the addon actually syncs to the
// TV (Movies, Shows), so everything shown is castable; the Discovery library
// stays out until Jellyseerr lands in phase 3.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { JELLYFIN_URL } from './config.js';
import { addonData, userdata } from './kodiprofile.js';

// Resolved per call, not once at import: the Kodi 21 Flatpak keeps its profile
// somewhere else entirely (~/.var/app/tv.kodi.Kodi/data), and this server
// outlives a flavour flip. A stale path here reads as "Jellyfin credentials
// unavailable", which looks like Jellyfin being down.
const dataJson = () => path.join(addonData('plugin.video.jellyfin'), 'data.json');
const mapDb = () => path.join(userdata(), 'Database', 'jellyfin.db');
const BASE = JELLYFIN_URL;

let creds = null;
let views = null;

// Couch has its own API key (Donnie approved it, 3 Aug 2026), created via
// /Auth/Keys and supplied as JELLYFIN_API_KEY. The user id still comes from the
// addon's data.json since browsing is scoped to that user's watch state; if the
// key is not set, fall back to borrowing the addon's token at runtime.
function readCreds() {
  const server = JSON.parse(fs.readFileSync(dataJson(), 'utf8')).Servers?.[0];
  if (!server?.UserId) throw new Error('jellyfin credentials unavailable');
  let token = process.env.JELLYFIN_API_KEY || null;
  if (!token) token = server.AccessToken;
  if (!token) throw new Error('jellyfin credentials unavailable');
  return { token, userId: server.UserId };
}

async function jf(pathname, params = {}, retry = true) {
  if (!creds) creds = readCreds();
  const url = new URL(BASE + pathname);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
  }
  const res = await fetch(url, {
    headers: { 'X-Emby-Token': creds.token },
    signal: AbortSignal.timeout(10000),
  });
  if (res.status === 401 && retry) {
    // Token rotated under us: re-read what the addon holds now, once.
    creds = null;
    return jf(pathname, params, false);
  }
  if (!res.ok) throw new Error(`jellyfin ${res.status} on ${pathname}`);
  return res.json();
}

// POST twin of jf(): Jellyfin's session commands take their arguments as query
// params with an empty body and answer 204. Same token, same 401-retry.
async function jfPost(pathname, params = {}, retry = true) {
  if (!creds) creds = readCreds();
  const url = new URL(BASE + pathname);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
  }
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'X-Emby-Token': creds.token },
    signal: AbortSignal.timeout(10000),
  });
  if (res.status === 401 && retry) {
    creds = null;
    return jfPost(pathname, params, false);
  }
  if (!res.ok) throw new Error(`jellyfin ${res.status} on ${pathname}`);
}

// The sessions Jellyfin has seen recently. The TV's webOS app registers one on
// each app start - with a FRESH id every time, so callers must always query
// and always use the full id (a truncated one 404s).
export function activeSessions() {
  return jf('/Sessions', { activeWithinSeconds: 120 });
}

export function playOnSession(sessionId, itemId, startTicks = 0) {
  const params = { playCommand: 'PlayNow', itemIds: itemId };
  // Only when meaningful: a 0 tick is "from the start" either way, and some
  // clients treat an explicit 0 differently from an absent parameter.
  if (startTicks > 0) params.startPositionTicks = Math.floor(startTicks);
  return jfPost(`/Sessions/${encodeURIComponent(sessionId)}/Playing`, params);
}

// Playstate commands ride POST /Sessions/{id}/Playing/{command} with an empty
// body. Whitelisted: this is the phone driving OUR playback, not a general
// remote for arbitrary sessions.
const SESSION_COMMANDS = new Set(['Stop', 'Pause', 'Unpause', 'PlayPause']);
export function sessionCommand(sessionId, command) {
  if (!SESSION_COMMANDS.has(command)) return Promise.reject(new Error('unrecognised session command'));
  return jfPost(`/Sessions/${encodeURIComponent(sessionId)}/Playing/${command}`);
}

// Seek is the same shape with its target as a query param, in ticks.
export function seekSession(sessionId, seconds) {
  const s = Number(seconds);
  if (!Number.isFinite(s) || s < 0) return Promise.reject(new Error('bad seek position'));
  return jfPost(`/Sessions/${encodeURIComponent(sessionId)}/Playing/Seek`, {
    seekPositionTicks: Math.round(s * 10_000_000),
  });
}

// What a "play this" on an item actually plays: films and episodes play
// themselves; a series plays its next-up episode. A series with no next-up
// (all watched, or never started and NextUp is empty) plays as itself -
// Jellyfin expands a series id to its episodes from the start.
export async function playableFor(itemId) {
  if (!creds) creds = readCreds();
  const item = await jf(`/Users/${creds.userId}/Items/${itemId}`);
  // The resume point rides along so the cast can START THERE. PlayNow with
  // no startPositionTicks begins at zero AND overwrites the stored resume -
  // found 23 Aug when a test cast of a half-watched film wiped its place.
  const ticks = item.UserData?.PlaybackPositionTicks || 0;
  if (item.Type !== 'Series') {
    const ep = item.Type === 'Episode' && item.ParentIndexNumber !== undefined
      ? ` S${String(item.ParentIndexNumber).padStart(2, '0')}E${String(item.IndexNumber).padStart(2, '0')}`
      : '';
    return { id: item.Id, name: `${item.SeriesName || item.Name}${ep}`, resumeTicks: ticks };
  }
  const next = await jf('/Shows/NextUp', { userId: creds.userId, seriesId: itemId, Limit: 1 });
  const ep = next.Items?.[0];
  if (!ep) return { id: item.Id, name: item.Name, resumeTicks: ticks };
  return {
    id: ep.Id,
    name: `${item.Name} S${String(ep.ParentIndexNumber).padStart(2, '0')}E${String(ep.IndexNumber).padStart(2, '0')}`,
    resumeTicks: ep.UserData?.PlaybackPositionTicks || 0,
  };
}

// The HDR facts for one item, straight from the file Jellyfin would play.
// MediaSources[0] is that file; the Type=Video stream inside it carries
// VideoRange ("HDR"/"SDR") and VideoRangeType ("HDR10"/"HDR10Plus"/"DOVI"/
// "HLG"/"SDR"). Verified live 6 Aug 2026: The Batman reports HDR / HDR10,
// hevc, 10-bit, 3840 wide; Batman (1989) reports SDR / SDR, h264, 8-bit.
// NOTE the route: /Items/{id} on its own 404s, it has to be the user-scoped
// one, and that is also what carries MediaSources without extra Fields.
export async function videoProfileFor(itemId) {
  if (!creds) creds = readCreds();
  const item = await jf(`/Users/${creds.userId}/Items/${itemId}`);
  const video = ((item.MediaSources || [])[0]?.MediaStreams || [])
    .find((s) => s.Type === 'Video') || null;
  return {
    id: item.Id,
    type: item.Type,
    name: item.Name,
    videoRange: video?.VideoRange ?? null,
    videoRangeType: video?.VideoRangeType ?? null,
    codec: video?.Codec ?? null,
    bitDepth: video?.BitDepth ?? null,
    width: video?.Width ?? null,
  };
}

export function jfImageRequest(itemId, type, params) {
  if (!creds) creds = readCreds();
  const url = new URL(`${BASE}/Items/${itemId}/Images/${type}`);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
  }
  return { url, headers: { 'X-Emby-Token': creds.token } };
}

async function getViews() {
  if (views) return views;
  if (!creds) creds = readCreds();
  const data = await jf(`/Users/${creds.userId}/Views`);
  views = {
    movies: data.Items.find((v) => v.CollectionType === 'movies')?.Id,
    shows: data.Items.find((v) => v.CollectionType === 'tvshows')?.Id,
  };
  return views;
}

const ticksToSecs = (t) => (t ? Math.round(t / 10_000_000) : 0);

function slim(i) {
  return {
    id: i.Id,
    type: i.Type,
    name: i.Name,
    year: i.ProductionYear,
    overview: i.Overview || '',
    genres: i.Genres || [],
    runtime: ticksToSecs(i.RunTimeTicks),
    imageTag: i.ImageTags?.Primary || null,
    // Episodes carry their series context and usually only the series has art.
    seriesName: i.SeriesName,
    seriesId: i.SeriesId,
    seriesImageTag: i.SeriesPrimaryImageTag || null,
    season: i.ParentIndexNumber,
    episode: i.IndexNumber,
    // 3200 not 3840: scope-ratio 4K files report cropped widths.
    fourK: (i.Width || 0) >= 3200,
    played: !!i.UserData?.Played,
    playCount: i.UserData?.PlayCount || 0,
    resumeSecs: ticksToSecs(i.UserData?.PlaybackPositionTicks),
    unplayedCount: i.UserData?.UnplayedItemCount,
    ended: i.Status ? i.Status !== 'Continuing' : undefined,
  };
}

const SORTS = {
  title: 'SortName',
  year: 'ProductionYear,SortName',
  added: 'DateCreated',
  played: 'DatePlayed',
};

const FIELDS = 'ProductionYear,Overview,Genres,RunTimeTicks,Status,Width,Height';

// Fold a title or query to bare lowercase alphanumerics: strips accents
// (Fiancé -> fiance), punctuation and spacing, so "911" matches "9-1-1",
// "alien romulus" matches "Alien: Romulus", "spiderman" matches "Spider-Man".
function fold(s) {
  return (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '');
}

export async function listLibrary(kind, { search, sort, order } = {}) {
  const v = await getViews();
  // The library is small enough to fetch whole and match ourselves - Jellyfin's
  // own searchTerm breaks on punctuation, which is exactly what we want to
  // forgive. Sort stays server-side, so filtered results keep their order.
  const data = await jf(`/Users/${creds.userId}/Items`, {
    IncludeItemTypes: kind === 'shows' ? 'Series' : 'Movie',
    ParentId: kind === 'shows' ? v.shows : v.movies,
    Recursive: true,
    SortBy: SORTS[sort] || 'SortName',
    SortOrder: order === 'desc' || (!order && (sort === 'added' || sort === 'played')) ? 'Descending' : 'Ascending',
    Limit: 2000,
    Fields: FIELDS,
  });
  let items = data.Items;
  if (search && search.trim()) {
    // Every whitespace-separated token must appear in the folded title, so
    // word order and punctuation don't matter.
    const tokens = search.trim().split(/\s+/).map(fold).filter(Boolean);
    items = items.filter((i) => {
      const hay = fold(i.Name);
      return tokens.every((t) => hay.includes(t));
    });
  }
  return { total: items.length, items: items.map(slim) };
}

export async function showEpisodes(seriesId) {
  if (!creds) creds = readCreds();
  const data = await jf(`/Shows/${seriesId}/Episodes`, {
    userId: creds.userId,
    Fields: 'Overview,RunTimeTicks,Width',
  });
  return data.Items.map(slim);
}

// Where the files actually are, for a batch of item ids.
//
// This exists because of one awkward fact about this box: Kodi's video library
// is fed entirely by the jellyfin-kodi addon, so every `file` Kodi reports is a
// `plugin://plugin.video.jellyfin/...?id=<32 hex>` url and NOTHING in Kodi
// knows the path on disk. Jellyfin does - /Items carries Path - and it takes a
// comma separated id list, so a whole season of episodes costs one request.
//
// Anything Jellyfin does not know about is simply absent from the map; callers
// decide what an unresolvable item means to them.
export async function pathsFor(ids) {
  const wanted = [...new Set((ids || []).filter(Boolean))];
  const out = new Map();
  // Chunked because this is a GET and the ids are 32 characters each: a whole
  // movie library in one query string is a few kilobytes of url.
  for (let i = 0; i < wanted.length; i += 100) {
    const data = await jf('/Items', { ids: wanted.slice(i, i + 100).join(','), fields: 'Path' });
    for (const item of data.Items || []) {
      if (item.Id && item.Path) out.set(item.Id, item.Path);
    }
  }
  return out;
}

export async function continueWatching() {
  if (!creds) creds = readCreds();
  const [resume, nextUp] = await Promise.all([
    jf(`/Users/${creds.userId}/Items/Resume`, { Limit: 12, MediaTypes: 'Video', Fields: FIELDS }),
    jf('/Shows/NextUp', { userId: creds.userId, Limit: 12, Fields: FIELDS }),
  ]);
  return {
    resume: resume.Items.map(slim),
    nextUp: nextUp.Items.map(slim),
  };
}

// The TMDB id Jellyfin knows for an item, to key Sonarr/Radarr lookups.
export async function tmdbIdFor(itemId) {
  if (!creds) creds = readCreds();
  const item = await jf(`/Users/${creds.userId}/Items/${itemId}`);
  const id = Number(item.ProviderIds?.Tmdb);
  return Number.isFinite(id) && id > 0 ? id : null;
}

// Media segments (intro/outro times) for whatever is playing, so skip-intro
// can jump the exact intro rather than a fixed nudge. Keyed by the Jellyfin
// item id, which the Kodi player carries in its file url.
export async function segmentsFor(jellyfinId) {
  const res = await jf(`/MediaSegments/${jellyfinId}`).catch(() => null);
  if (!res?.Items) return [];
  return res.Items.map((s) => ({
    type: s.Type,
    start: Math.round(s.StartTicks / 10_000_000),
    end: Math.round(s.EndTicks / 10_000_000),
  }));
}

// The best trailer for an item, as a YouTube video id. Jellyfin carries
// RemoteTrailers for both movies and series; prefer one actually named
// Trailer over teasers and sneak peeks.
export async function trailerFor(itemId) {
  if (!creds) creds = readCreds();
  const item = await jf(`/Users/${creds.userId}/Items/${itemId}`);
  const trailers = item.RemoteTrailers || [];
  if (!trailers.length) throw new Error('No trailer available for this title');
  const pick = trailers.find((t) => /trailer/i.test(t.Name || '')) || trailers[0];
  const m = pick.Url.match(/[?&]v=([\w-]{6,})/) || pick.Url.match(/youtu\.be\/([\w-]{6,})/);
  if (!m) throw new Error('No playable trailer link');
  return m[1];
}

// Jellyfin id -> the Kodi library id the TV plays by. The jellyfin-kodi addon
// maintains this mapping in its own sqlite db; read-only via the CLI so we add
// no native deps and can never hold a write lock against Kodi.
export function kodiIdFor(jellyfinId) {
  if (!/^[0-9a-f]{32}$/.test(jellyfinId)) return Promise.reject(new Error('bad jellyfin id'));
  return new Promise((resolve, reject) => {
    execFile(
      'sqlite3', ['-readonly', '-json', mapDb(),
        `select media_type, kodi_id from jellyfin where jellyfin_id='${jellyfinId}'`],
      { timeout: 5000 },
      (err, out) => {
        if (err) return reject(new Error('library mapping unavailable'));
        const rows = out.trim() ? JSON.parse(out) : [];
        if (!rows.length) return reject(new Error('not on the TV library yet'));
        resolve({ mediaType: rows[0].media_type, kodiId: rows[0].kodi_id });
      });
  });
}
