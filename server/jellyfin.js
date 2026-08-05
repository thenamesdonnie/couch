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

const DATA_JSON = path.join(os.homedir(), '.kodi/userdata/addon_data/plugin.video.jellyfin/data.json');
const MAP_DB = path.join(os.homedir(), '.kodi/userdata/Database/jellyfin.db');
const BASE = JELLYFIN_URL;

let creds = null;
let views = null;

// Couch has its own API key (Donnie approved it, 3 Aug 2026), created via
// /Auth/Keys and supplied as JELLYFIN_API_KEY. The user id still comes from the
// addon's data.json since browsing is scoped to that user's watch state; if the
// key is not set, fall back to borrowing the addon's token at runtime.
function readCreds() {
  const server = JSON.parse(fs.readFileSync(DATA_JSON, 'utf8')).Servers?.[0];
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

const FIELDS = 'ProductionYear,Overview,Genres,RunTimeTicks,Status';

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
    Fields: 'Overview,RunTimeTicks',
  });
  return data.Items.map(slim);
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
      'sqlite3', ['-readonly', '-json', MAP_DB,
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
