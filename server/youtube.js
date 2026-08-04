// In-app YouTube search. Uses Donnie's own YouTube Data API key (the same one
// the Kodi plugin uses). Playback goes to the TV through the Kodi YouTube
// plugin, so it stays ad-free and picks up the 1.25x default.
import { secret } from './config.js';

const API = 'https://www.googleapis.com/youtube/v3';

function key() {
  return secret('YOUTUBE_API_KEY');
}

async function api(pathname, params) {
  const url = new URL(API + pathname);
  url.searchParams.set('key', key());
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, String(v));
  const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
  const data = await res.json();
  if (data.error) throw new Error(data.error.message || 'youtube api error');
  return data;
}

// ISO 8601 duration (PT1H2M3S) -> m:ss / h:mm:ss.
function fmtDur(iso) {
  const m = (iso || '').match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
  if (!m) return '';
  const h = +(m[1] || 0), mm = +(m[2] || 0), s = +(m[3] || 0);
  const pad = (n) => String(n).padStart(2, '0');
  return h ? `${h}:${pad(mm)}:${pad(s)}` : `${mm}:${pad(s)}`;
}

function slim(item, durations) {
  const id = item.id?.videoId || item.id;
  const sn = item.snippet || {};
  return {
    id,
    title: sn.title || '',
    channel: sn.channelTitle || '',
    thumb: sn.thumbnails?.medium?.url || sn.thumbnails?.default?.url || null,
    duration: durations?.[id] || '',
  };
}

// search.list gives no duration; a follow-up videos.list fills them in one call.
async function withDurations(items) {
  const ids = items.map((i) => i.id?.videoId || i.id).filter(Boolean);
  if (!ids.length) return {};
  const data = await api('/videos', { part: 'contentDetails', id: ids.join(','), maxResults: ids.length });
  const out = {};
  for (const v of data.items || []) out[v.id] = fmtDur(v.contentDetails?.duration);
  return out;
}

export async function search(query) {
  const data = await api('/search', {
    part: 'snippet', type: 'video', maxResults: 25, q: query, safeSearch: 'none',
  });
  const durations = await withDurations(data.items || []).catch(() => ({}));
  return (data.items || []).map((i) => slim(i, durations));
}

export async function trending() {
  const data = await api('/videos', {
    part: 'snippet,contentDetails', chart: 'mostPopular', regionCode: 'GB', maxResults: 25,
  });
  const durations = {};
  for (const v of data.items || []) durations[v.id] = fmtDur(v.contentDetails?.duration);
  return (data.items || []).map((i) => slim(i, durations));
}

export function thumbUrl(id, quality = 'mqdefault') {
  return `https://i.ytimg.com/vi/${id}/${quality}.jpg`;
}

// Durations for a batch of video ids in one call, for the subscription /
// recommendation feeds (which come from Kodi without durations).
export async function durationsFor(ids) {
  if (!ids.length) return {};
  const data = await api('/videos', { part: 'contentDetails', id: ids.slice(0, 50).join(','), maxResults: 50 });
  const out = {};
  for (const v of data.items || []) out[v.id] = fmtDur(v.contentDetails?.duration);
  return out;
}
