// Steam: the owned library (Web API), live download/install state (read from
// Steam's own appmanifests), and triggering a download headlessly. Steam runs
// signed in and -silent on the box; the GUI install path can't be driven
// blind, so installs use the manifest-seed method proven in the console build:
// seed appmanifest_<id>.acf with StateFlags "Update Required" + the exact
// installdir from appinfo.vdf, then relaunch `steam -silent` so Steam's own
// downloader resolves and pulls it.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFile, spawn } from 'node:child_process';
import { secret } from './config.js';

const HOME = os.homedir();
const STEAMAPPS = path.join(HOME, '.steam/debian-installation/steamapps');
const APPINFO = path.join(HOME, '.steam/debian-installation/appcache/appinfo.vdf');
const LIBCACHE = path.join(HOME, '.steam/debian-installation/appcache/librarycache');

function creds() {
  return { key: secret('STEAM_API_KEY'), id: secret('STEAM_ID') };
}

// --- owned library (Web API) ---

let ownedCache = { at: 0, games: [] };

export async function ownedGames() {
  if (Date.now() - ownedCache.at < 300000 && ownedCache.games.length) return ownedCache.games;
  const { key, id } = creds();
  const url = `https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key=${key}&steamid=${id}&include_appinfo=1&include_played_free_games=1`;
  const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
  if (!res.ok) throw new Error(`steam api ${res.status}`);
  const games = (await res.json()).response?.games || [];
  ownedCache = {
    at: Date.now(),
    games: games.map((g) => ({ appid: g.appid, name: g.name, playtime: g.playtime_forever || 0 }))
      .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase())),
  };
  return ownedCache.games;
}

// --- local manifest state (installed / downloading / paused) ---

function acf(txt, key) {
  const m = txt.match(new RegExp(`"${key}"\\s+"([^"]*)"`));
  return m ? m[1] : '';
}

// StateFlags bits: 4 installed, 2 update required, 16 update running,
// 1024 update paused. A game mid-download carries byte counts.
function manifestState(appid) {
  const file = path.join(STEAMAPPS, `appmanifest_${appid}.acf`);
  let txt;
  try { txt = fs.readFileSync(file, 'utf8'); } catch { return null; }
  const flags = parseInt(acf(txt, 'StateFlags'), 10) || 0;
  const done = Number(acf(txt, 'BytesDownloaded')) || 0;
  const total = Number(acf(txt, 'BytesToDownload')) || 0;
  let state = 'installed';
  if (flags & 1024) state = 'paused';
  else if (flags & 16) state = 'downloading';
  else if (flags & 2) state = 'queued';
  else if (flags & 4) state = 'installed';
  else state = 'unknown';
  return { name: acf(txt, 'name'), flags, done, total, state };
}

export function libraryState() {
  const map = new Map();
  let files;
  try { files = fs.readdirSync(STEAMAPPS); } catch { files = []; }
  for (const f of files) {
    const m = f.match(/^appmanifest_(\d+)\.acf$/);
    if (!m) continue;
    const st = manifestState(m[1]);
    if (st) map.set(Number(m[1]), st);
  }
  return map;
}

// Owned games decorated with their on-disk state; the app shows one grid.
export async function library() {
  const owned = await ownedGames();
  const state = libraryState();
  return owned.map((g) => {
    const st = state.get(g.appid);
    return {
      appid: g.appid,
      name: g.name,
      playtime: g.playtime,
      state: st ? st.state : 'notinstalled',
      progress: st && st.total ? st.done / st.total : null,
    };
  });
}

// Just the in-flight ones, for the Downloads panel.
export async function downloads() {
  const owned = await ownedGames();
  const names = new Map(owned.map((g) => [g.appid, g.name]));
  const PLUMBING = /proton|steam linux runtime|steamworks common|redistributable/i;
  const out = [];
  for (const [appid, st] of libraryState()) {
    if (PLUMBING.test(st.name)) continue; // runtimes/redists, not real downloads
    if (st.state === 'downloading' || st.state === 'paused' || st.state === 'queued') {
      out.push({
        appid,
        name: names.get(appid) || st.name,
        state: st.state,
        done: st.done,
        total: st.total,
        progress: st.total ? st.done / st.total : null,
      });
    }
  }
  return out.sort((a, b) => (b.progress || 0) - (a.progress || 0));
}

// --- appinfo.vdf: the exact install-directory name per app ---

function readInstalldir(appid) {
  const data = fs.readFileSync(APPINFO);
  const ver = data[0];
  let strings = null;
  let off;
  if (ver >= 0x29) {
    const soff = Number(data.readBigInt64LE(8));
    let p = soff;
    const cnt = data.readUInt32LE(p); p += 4;
    strings = [];
    for (let i = 0; i < cnt; i++) {
      const e = data.indexOf(0, p);
      strings.push(data.toString('utf8', p, e));
      p = e + 1;
    }
    off = 16;
  } else {
    off = 8;
  }
  function readKV(o) {
    const out = {};
    for (;;) {
      const t = data[o]; o += 1;
      if (t === 0x08) return [out, o];
      let key;
      if (strings) { key = strings[data.readUInt32LE(o)]; o += 4; }
      else { const e = data.indexOf(0, o); key = data.toString('utf8', o, e); o = e + 1; }
      if (t === 0x00) { const [sub, no] = readKV(o); out[key] = sub; o = no; }
      else if (t === 0x01) { const e = data.indexOf(0, o); out[key] = data.toString('utf8', o, e); o = e + 1; }
      else if (t === 0x02) { out[key] = data.readInt32LE(o); o += 4; }
      else if (t === 0x07) { out[key] = Number(data.readBigInt64LE(o)); o += 8; }
      else throw new Error('vdf type ' + t);
    }
  }
  while (off < data.length - 4) {
    const id = data.readUInt32LE(off);
    if (id === 0) break;
    const size = data.readUInt32LE(off + 4);
    const body = off + 8;
    let hdr = 4 + 4 + 8 + 20 + 4;
    if (ver >= 0x29) hdr += 20;
    if (id === appid) {
      try {
        const [kv] = readKV(body + hdr);
        return (kv.appinfo || kv)?.config?.installdir || null;
      } catch { return null; }
    }
    off = body + size;
  }
  return null;
}

// --- trigger a download / resume ---

function gameRunning() {
  return new Promise((resolve) => {
    execFile('pgrep', ['-f', 'steamapps/common'], (err, out) => resolve(!err && out.trim().length > 0));
  });
}

export async function install(appid) {
  appid = Number(appid);
  if (!Number.isInteger(appid) || appid <= 0) throw new Error('bad appid');
  // Never restart Steam out from under a running game.
  if (await gameRunning()) throw new Error('a game is running, quit it before downloading');

  const owned = await ownedGames();
  const game = owned.find((g) => g.appid === appid);
  if (!game) throw new Error('not in your library');

  const file = path.join(STEAMAPPS, `appmanifest_${appid}.acf`);
  if (fs.existsSync(file)) {
    // Partially downloaded or paused: clear the paused bit and mark it wanted.
    let txt = fs.readFileSync(file, 'utf8');
    let flags = parseInt(acf(txt, 'StateFlags'), 10) || 0;
    flags = (flags & ~1024) | 2;
    txt = txt.replace(/("StateFlags"\s+")\d+(")/, `$1${flags}$2`);
    fs.writeFileSync(file, txt);
  } else {
    const installdir = readInstalldir(appid);
    if (!installdir) throw new Error('could not resolve the install folder');
    const manifest = `"AppState"
{
\t"appid"\t\t"${appid}"
\t"Universe"\t\t"1"
\t"name"\t\t"${game.name.replace(/"/g, '')}"
\t"StateFlags"\t\t"2"
\t"installdir"\t\t"${installdir}"
\t"buildid"\t\t"0"
}
`;
    fs.writeFileSync(file, manifest);
    fs.mkdirSync(path.join(STEAMAPPS, 'common', installdir), { recursive: true });
  }

  // Bounce Steam so it rescans and starts the download, exactly as the console
  // build does. Detached; Steam autostarts -silent.
  await new Promise((resolve) => {
    execFile('bash', ['-c', 'pkill -9 -x steam; pkill -9 -f steamwebhelper; sleep 1'], () => resolve());
  });
  spawn('setsid', ['steam', '-silent'], { detached: true, stdio: 'ignore' }).unref();
  return { name: game.name };
}

// Portrait art: local librarycache if installed, else Steam's CDN.
export function artRequest(appid) {
  const local = path.join(LIBCACHE, String(appid));
  for (const name of ['library_600x900.jpg', 'library_capsule.jpg']) {
    const hit = localFind(local, name);
    if (hit) return { file: hit };
  }
  return { urls: [
    `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${appid}/library_600x900.jpg`,
    `https://cdn.cloudflare.steamstatic.com/steam/apps/${appid}/library_600x900.jpg`,
    `https://cdn.cloudflare.steamstatic.com/steam/apps/${appid}/header.jpg`,
  ] };
}

function localFind(dir, name) {
  const direct = path.join(dir, name);
  if (fs.existsSync(direct)) return direct;
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return null; }
  for (const e of entries) {
    if (e.isDirectory() && fs.existsSync(path.join(dir, e.name, name))) return path.join(dir, e.name, name);
  }
  return null;
}
