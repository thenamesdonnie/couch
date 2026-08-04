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
