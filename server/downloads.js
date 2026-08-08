// qBittorrent's active queue. qBittorrent runs inside the gluetun VPN
// container, so its localhost no-auth whitelist doesn't apply to us; we reach
// it at its published address and log in with the WebUI credentials from the
// environment. The auth cookie is cached and refreshed on 403.
import { QBITTORRENT_URL, secret } from './config.js';

const BASE = `${QBITTORRENT_URL}/api/v2`;

let cookie = null;

function creds() {
  return { user: process.env.QBITTORRENT_USER || 'admin', pass: secret('QBITTORRENT_PASSWORD') };
}

async function login() {
  const { user, pass } = creds();
  const body = new URLSearchParams({ username: user, password: pass });
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded', Referer: QBITTORRENT_URL },
    body,
    signal: AbortSignal.timeout(4000),
  });
  const setCookie = res.headers.get('set-cookie');
  if (!res.ok || !setCookie) throw new Error('qbittorrent login failed');
  cookie = setCookie.split(';')[0];
}

async function api(pathname, retry = true) {
  if (!cookie) await login();
  const res = await fetch(BASE + pathname, {
    headers: { cookie, Referer: QBITTORRENT_URL },
    signal: AbortSignal.timeout(4000),
  });
  if (res.status === 403 && retry) { cookie = null; return api(pathname, false); }
  if (!res.ok) throw new Error(`qbittorrent ${res.status}`);
  return res.json();
}

// qBittorrent's `active` filter means "moving bytes", in either direction, so
// a finished torrent that is seeding is active - and the Downloads view was
// showing exactly that: 100%-complete films with 0 B/s down, sitting above
// anything real. `downloading` is the filter that means what this view means.
//
// The state check is ours and stays even though the filter should make it
// redundant: trusting a filter name for this is precisely what went wrong,
// the names are qBittorrent's to redefine, and one line here is cheaper than
// noticing again. Every upload state ends in `UP`; the rest are the
// not-yet-complete ones (metaDL is a magnet still fetching its metadata,
// which has no size or progress yet but is very much a download).
const UPLOAD_STATE = /UP$|^uploading$/;

export async function activeDownloads() {
  const torrents = await api('/torrents/info?filter=downloading');
  return torrents
    .filter((t) => !UPLOAD_STATE.test(t.state) && t.progress < 1)
    .map((t) => ({
      name: t.name,
      progress: t.progress,
      state: t.state,
      speed: t.dlspeed,
      size: t.size,
      eta: t.eta,
    }))
    .sort((a, b) => b.progress - a.progress);
}
