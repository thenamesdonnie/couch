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

export async function activeDownloads() {
  const torrents = await api('/torrents/info?filter=active');
  return torrents
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
