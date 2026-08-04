// Jellyseerr: search everything, request from the couch, watch requests land.
// The API key is Jellyseerr's own, read from its docker-mounted config on
// demand (re-read on auth failure) so we never store a copy.
import fs from 'node:fs';
import { JELLYSEERR_URL, JELLYSEERR_SETTINGS } from './config.js';

const BASE = `${JELLYSEERR_URL}/api/v1`;

let apiKey = null;

function readKey() {
  if (process.env.JELLYSEERR_API_KEY) return process.env.JELLYSEERR_API_KEY;
  return JSON.parse(fs.readFileSync(JELLYSEERR_SETTINGS, 'utf8')).main.apiKey;
}

async function js(pathname, { params, method, body } = {}, retry = true) {
  if (!apiKey) apiKey = readKey();
  // Build the query string with encodeURIComponent (space -> %20). Jellyseerr's
  // validator rejects the '+' that URLSearchParams uses, so multi-word searches
  // would fail with "must be url encoded".
  const qs = Object.entries(params || {})
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  const url = BASE + pathname + (qs ? `?${qs}` : '');
  const res = await fetch(url, {
    method: method || 'GET',
    headers: {
      'X-Api-Key': apiKey,
      ...(body ? { 'content-type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(15000),
  });
  if ((res.status === 401 || res.status === 403) && retry) {
    apiKey = null;
    return js(pathname, { params, method, body }, false);
  }
  if (!res.ok) {
    let msg = `jellyseerr ${res.status}`;
    try { msg = (await res.json()).message || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

// Media status: 2 pending, 3 processing, 4 partially available, 5 available.
const MEDIA_STATUS = { 2: 'requested', 3: 'downloading', 4: 'partly available', 5: 'available' };

function slimResult(r) {
  return {
    mediaType: r.mediaType,
    tmdbId: r.id,
    title: r.title || r.name || '',
    year: (r.releaseDate || r.firstAirDate || '').slice(0, 4) || null,
    overview: r.overview || '',
    poster: r.posterPath || null,
    status: MEDIA_STATUS[r.mediaInfo?.status] || null,
  };
}

export async function search(query, page = 1) {
  const data = await js('/search', { params: { query, page } });
  return {
    total: data.totalResults,
    results: data.results
      .filter((r) => r.mediaType === 'movie' || r.mediaType === 'tv')
      .map(slimResult),
  };
}

export async function trending() {
  const data = await js('/discover/trending', { params: { page: 1 } });
  return data.results
    .filter((r) => r.mediaType === 'movie' || r.mediaType === 'tv')
    .map(slimResult);
}

export async function popular(kind) {
  const data = await js(kind === 'tv' ? '/discover/tv' : '/discover/movies', { params: { page: 1 } });
  // These endpoints return one media type and omit mediaType per result.
  return data.results.map((r) => slimResult({ ...r, mediaType: kind === 'tv' ? 'tv' : 'movie' }));
}

// Full detail for the info card: overview, rating, runtime/seasons, genres,
// backdrop. mediaType keeps movie/tv apart at the endpoint.
export async function detail(mediaType, tmdbId) {
  const d = await js(`/${mediaType === 'tv' ? 'tv' : 'movie'}/${tmdbId}`);
  return {
    mediaType,
    tmdbId,
    title: d.title || d.name || '',
    year: (d.releaseDate || d.firstAirDate || '').slice(0, 4) || null,
    overview: d.overview || '',
    tagline: d.tagline || '',
    poster: d.posterPath || null,
    backdrop: d.backdropPath || null,
    rating: d.voteAverage ? Math.round(d.voteAverage * 10) / 10 : null,
    runtime: d.runtime || null,
    seasons: d.numberOfSeasons || null,
    episodes: d.numberOfEpisodes || null,
    genres: (d.genres || []).map((g) => g.name),
    status: MEDIA_STATUS[d.mediaInfo?.status] || null,
  };
}

export function requestMedia(mediaType, tmdbId) {
  const body = { mediaType, mediaId: Number(tmdbId) };
  if (mediaType === 'tv') body.seasons = 'all';
  return js('/request', { method: 'POST', body });
}

// The request list's media objects carry no titles, so titles and posters are
// filled from the details endpoints, cached per tmdb id for the process life.
const detailsCache = new Map();

async function details(mediaType, tmdbId) {
  const key = `${mediaType}:${tmdbId}`;
  if (!detailsCache.has(key)) {
    detailsCache.set(key, js(`/${mediaType === 'tv' ? 'tv' : 'movie'}/${tmdbId}`).then(
      (d) => ({
        title: d.title || d.name || `tmdb ${tmdbId}`,
        poster: d.posterPath || null,
        year: (d.releaseDate || d.firstAirDate || '').slice(0, 4) || null,
      }),
      () => ({ title: `tmdb ${tmdbId}`, poster: null, year: null }),
    ));
  }
  return detailsCache.get(key);
}

const REQUEST_STATUS = { 1: 'waiting approval', 2: 'approved', 3: 'declined', 4: 'failed', 5: 'done' };

// A film not yet out for home viewing sits at Jellyseerr "processing" forever,
// which the app used to call "downloading". Radarr knows better - phase() turns
// its release state into an honest label. Movies only; series air per episode.
function phaseLabel(media, downloads, release) {
  if (media.status === 5) return { phase: 'available', label: 'Available' };
  if (downloads.length) return { phase: 'downloading', label: 'Downloading' };
  if (release?.phase === 'available') return { phase: 'available', label: 'Available' };
  if (release?.phase === 'waiting') {
    if (release.date) {
      const d = new Date(release.date);
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      return { phase: 'waiting', label: `Waiting · ${release.kind} ${d.getDate()} ${months[d.getMonth()]}` };
    }
    return { phase: 'waiting', label: release.status === 'inCinemas' ? 'Waiting · in cinemas' : 'Waiting for release' };
  }
  if (release?.phase === 'searching') return { phase: 'searching', label: 'Searching' };
  if (media.status === 3) return { phase: 'searching', label: 'Searching' };
  return { phase: 'requested', label: MEDIA_STATUS[media.status] || REQUEST_STATUS[0] || 'Requested' };
}

export async function listRequests() {
  const { releaseInfo } = await import('./radarr.js');
  const data = await js('/request', { params: { take: 30, sort: 'added' } });
  return Promise.all(data.results.map(async (r) => {
    const d = await details(r.type, r.media.tmdbId);
    const downloads = (r.media.downloadStatus || []).map((dl) => ({
      title: dl.title,
      size: dl.size,
      sizeLeft: dl.sizeLeft,
      status: dl.status,
    }));
    const release = r.type === 'movie' ? await releaseInfo(r.media.tmdbId).catch(() => null) : null;
    const { phase, label } = phaseLabel(r.media, downloads, release);
    return {
      id: r.id,
      mediaType: r.type,
      tmdbId: r.media.tmdbId,
      title: d.title,
      year: d.year,
      poster: d.poster,
      requestedBy: r.requestedBy?.displayName || '',
      createdAt: r.createdAt,
      status: label,
      phase,
      available: phase === 'available',
      downloading: phase === 'downloading',
      waiting: phase === 'waiting',
      downloads,
    };
  }));
}
