// Radarr, read-only, to tell a requested film's real state apart: waiting for
// a home release vs actually searching/downloading. API key from Radarr's own
// config.xml (readable as ds2000). The movie list is small (~100) so it is
// fetched whole and cached briefly, keyed by tmdbId.
import fs from 'node:fs';
import { RADARR_URL, RADARR_CONFIG } from './config.js';

const BASE = `${RADARR_URL}/api/v3`;

let apiKey = null;
let cache = { at: 0, byTmdb: new Map() };

function readKey() {
  if (process.env.RADARR_API_KEY) return process.env.RADARR_API_KEY;
  const m = fs.readFileSync(RADARR_CONFIG, 'utf8').match(/<ApiKey>([^<]+)<\/ApiKey>/);
  if (!m) throw new Error('radarr api key unavailable');
  return m[1];
}

async function refresh() {
  if (Date.now() - cache.at < 15000 && cache.byTmdb.size) return cache.byTmdb;
  if (!apiKey) apiKey = readKey();
  const res = await fetch(`${BASE}/movie`, { headers: { 'X-Api-Key': apiKey }, signal: AbortSignal.timeout(6000) });
  if (res.status === 401) { apiKey = null; throw new Error('radarr auth failed'); }
  if (!res.ok) throw new Error(`radarr ${res.status}`);
  const movies = await res.json();
  const byTmdb = new Map();
  for (const m of movies) {
    byTmdb.set(m.tmdbId, {
      isAvailable: !!m.isAvailable,
      hasFile: !!m.hasFile,
      status: m.status, // announced | inCinemas | released
      inCinemas: m.inCinemas || null,
      digitalRelease: m.digitalRelease || null,
      physicalRelease: m.physicalRelease || null,
    });
  }
  cache = { at: Date.now(), byTmdb };
  return byTmdb;
}

async function rfetch(pathname, { method, body } = {}) {
  if (!apiKey) apiKey = readKey();
  const res = await fetch(`${BASE}${pathname}`, {
    method: method || 'GET',
    headers: { 'X-Api-Key': apiKey, ...(body ? { 'content-type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(8000),
  });
  if (res.status === 401) { apiKey = null; throw new Error('radarr auth failed'); }
  if (!res.ok) throw new Error(`radarr ${res.status}`);
  return res.json();
}

// The "UHD" profile (4K with 1080p fallback, created 5 Aug 2026), by name so
// the id is never hardcoded. Cached for the process life.
let uhdId = null;
export async function uhdProfileId() {
  if (uhdId) return uhdId;
  const profiles = await rfetch('/qualityprofile');
  uhdId = profiles.find((p) => p.name === 'UHD')?.id || null;
  if (!uhdId) throw new Error('radarr UHD profile missing');
  return uhdId;
}

let hdId = null;
async function hdProfileId() {
  if (hdId) return hdId;
  const profiles = await rfetch('/qualityprofile');
  hdId = profiles.find((p) => p.name === 'HD-1080p')?.id || null;
  if (!hdId) throw new Error('radarr HD-1080p profile missing');
  return hdId;
}

async function movieByTmdb(tmdbId) {
  const [m] = await rfetch(`/movie?tmdbId=${tmdbId}`);
  return m || null;
}

// Take a film off the UHD profile again (profile only; existing files stay).
export async function revertToHd(tmdbId) {
  const m = await movieByTmdb(tmdbId);
  if (!m) throw new Error('film not in radarr');
  m.qualityProfileId = await hdProfileId();
  await rfetch(`/movie/${m.id}`, { method: 'PUT', body: m });
}

// Is the film in Radarr, and already on the UHD profile?
export async function libraryInfo(tmdbId) {
  const m = await movieByTmdb(tmdbId);
  if (!m) return null;
  const uhd = await uhdProfileId().catch(() => null);
  return { uhd: !!uhd && m.qualityProfileId === uhd };
}

// Flip an existing film to the UHD profile without searching. Returns false
// if the film isn't in Radarr yet.
export async function setUhdIfPresent(tmdbId) {
  const m = await movieByTmdb(tmdbId);
  if (!m) return false;
  m.qualityProfileId = await uhdProfileId();
  m.monitored = true;
  await rfetch(`/movie/${m.id}`, { method: 'PUT', body: m });
  return true;
}

// Upgrade to 4K: UHD profile, monitored, and a search so the existing file
// (now below the 4K cutoff) gets replaced when a capped 4K release exists.
export async function upgradeTo4k(tmdbId) {
  const m = await movieByTmdb(tmdbId);
  if (!m) throw new Error('film not in radarr');
  m.qualityProfileId = await uhdProfileId();
  m.monitored = true;
  await rfetch(`/movie/${m.id}`, { method: 'PUT', body: m });
  await rfetch('/command', { method: 'POST', body: { name: 'MoviesSearch', movieIds: [m.id] } });
}

// For a movie tmdbId: its release phase and the date it is waiting on, if any.
export async function releaseInfo(tmdbId) {
  let byTmdb;
  try { byTmdb = await refresh(); } catch { return null; }
  const m = byTmdb.get(tmdbId);
  if (!m) return null;
  if (m.hasFile) return { phase: 'available' };
  if (m.isAvailable) return { phase: 'searching' };
  // Not yet released for home viewing: report the soonest known home date.
  const date = m.digitalRelease || m.physicalRelease || null;
  const kind = m.digitalRelease ? 'digital' : m.physicalRelease ? 'disc' : null;
  return { phase: 'waiting', status: m.status, date, kind };
}
