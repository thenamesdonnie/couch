// Sonarr's calendar: upcoming episodes of shows in the library. Read-only.
// API key read from Sonarr's own config.xml on the box (readable as ds2000).
import fs from 'node:fs';
import { SONARR_URL, SONARR_CONFIG } from './config.js';

const BASE = `${SONARR_URL}/api/v3`;

let apiKey = null;

function readKey() {
  if (process.env.SONARR_API_KEY) return process.env.SONARR_API_KEY;
  const xml = fs.readFileSync(SONARR_CONFIG, 'utf8');
  const m = xml.match(/<ApiKey>([^<]+)<\/ApiKey>/);
  if (!m) throw new Error('sonarr api key unavailable');
  return m[1];
}

async function sfetch(pathname, { method, body } = {}) {
  if (!apiKey) apiKey = readKey();
  const res = await fetch(`${BASE}${pathname}`, {
    method: method || 'GET',
    headers: { 'X-Api-Key': apiKey, ...(body ? { 'content-type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(8000),
  });
  if (res.status === 401) { apiKey = null; throw new Error('sonarr auth failed'); }
  if (!res.ok) throw new Error(`sonarr ${res.status}`);
  return res.json();
}

// The "UHD" profile (4K with 1080p fallback, created 5 Aug 2026), by name so
// the id is never hardcoded. Cached for the process life.
let uhdId = null;
export async function uhdProfileId() {
  if (uhdId) return uhdId;
  const profiles = await sfetch('/qualityprofile');
  uhdId = profiles.find((p) => p.name === 'UHD')?.id || null;
  if (!uhdId) throw new Error('sonarr UHD profile missing');
  return uhdId;
}

let hdId = null;
async function hdProfileId() {
  if (hdId) return hdId;
  const profiles = await sfetch('/qualityprofile');
  hdId = profiles.find((p) => p.name === 'HD-1080p')?.id || null;
  if (!hdId) throw new Error('sonarr HD-1080p profile missing');
  return hdId;
}

async function seriesByTmdb(tmdbId) {
  const all = await sfetch('/series');
  return all.find((s) => s.tmdbId === tmdbId) || null;
}

// Take a show off the UHD profile again (profile only; monitoring untouched).
// Already-downloaded 4K files stay - Sonarr never deletes on a profile change.
export async function revertToHd(tmdbId) {
  const s = await seriesByTmdb(tmdbId);
  if (!s) throw new Error('show not in sonarr');
  s.qualityProfileId = await hdProfileId();
  await sfetch(`/series/${s.id}`, { method: 'PUT', body: s });
}

// Is the show in Sonarr, and already on the UHD profile?
export async function libraryInfo(tmdbId) {
  const s = await seriesByTmdb(tmdbId);
  if (!s) return null;
  const uhd = await uhdProfileId().catch(() => null);
  return { uhd: !!uhd && s.qualityProfileId === uhd };
}

// Flip an existing series to the UHD profile without searching, so a 4K
// request on a partly-available show sticks before Jellyseerr's own update
// and search land. Returns false if the show isn't in Sonarr yet.
export async function setUhdIfPresent(tmdbId) {
  const s = await seriesByTmdb(tmdbId);
  if (!s) return false;
  s.qualityProfileId = await uhdProfileId();
  s.monitored = true;
  await sfetch(`/series/${s.id}`, { method: 'PUT', body: s });
  return true;
}

// Upgrade to 4K: UHD profile, series monitored, and only the seasons that
// already have files get (re)monitored - upgrading what's there, not pulling
// seasons never asked for. The search then replaces cutoff-unmet episodes.
export async function upgradeTo4k(tmdbId) {
  const s = await seriesByTmdb(tmdbId);
  if (!s) throw new Error('show not in sonarr');
  s.qualityProfileId = await uhdProfileId();
  s.monitored = true;
  for (const season of s.seasons) {
    if (season.seasonNumber > 0 && (season.statistics?.episodeFileCount || 0) > 0) {
      season.monitored = true;
    }
  }
  await sfetch(`/series/${s.id}`, { method: 'PUT', body: s });
  await sfetch('/command', { method: 'POST', body: { name: 'SeriesSearch', seriesId: s.id } });
}

// Upcoming episodes from today forward. Sonarr returns one entry per episode
// with the series title inlined.
export async function upcoming(days = 21) {
  if (!apiKey) apiKey = readKey();
  const start = new Date();
  const end = new Date(start.getTime() + days * 86400000);
  const url = `${BASE}/calendar?start=${start.toISOString()}&end=${end.toISOString()}&includeSeries=true`;
  const res = await fetch(url, { headers: { 'X-Api-Key': apiKey }, signal: AbortSignal.timeout(6000) });
  if (res.status === 401) { apiKey = null; throw new Error('sonarr auth failed'); }
  if (!res.ok) throw new Error(`sonarr ${res.status}`);
  const items = await res.json();
  return items.map((e) => ({
    series: e.series?.title || '',
    title: e.title,
    season: e.seasonNumber,
    episode: e.episodeNumber,
    airDate: e.airDateUtc,
    hasFile: !!e.hasFile,
    tvdbId: e.series?.tvdbId,
  }));
}
