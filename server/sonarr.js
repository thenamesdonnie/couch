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
