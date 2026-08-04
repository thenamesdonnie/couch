// The games list, ported from the Kodi helper's games.py so both surfaces
// show the same tiles: installed Steam games read live from their install
// manifests, PS4 dumps under ~/games/ps4 named and arted from their own
// metadata, plus the Big Picture and shadPS4 library tiles.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const HOME = os.homedir();
export const STEAMAPPS = path.join(HOME, '.steam/steam/steamapps');
export const LIBCACHE = path.join(HOME, '.steam/debian-installation/appcache/librarycache');
export const PS4_DIR = path.join(HOME, 'games/ps4');
export const TILE_DIR = path.join(HOME, '.local/share/game-tiles');
const SHADPS4_APP = path.join(HOME, '.local/share/shadps4/Shadps4-sdl.AppImage');

const PLUMBING = /proton|steam linux runtime|steamworks common/i;

function acfField(key, txt) {
  const m = txt.match(new RegExp(`"${key}"\\s+"([^"]*)"`));
  return m ? m[1] : '';
}

function findFirst(dir, names) {
  // Steam nests art under hash subdirectories; search one level of those too.
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return null; }
  for (const name of names) {
    const direct = path.join(dir, name);
    if (fs.existsSync(direct)) return direct;
  }
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    for (const name of names) {
      const nested = path.join(dir, e.name, name);
      if (fs.existsSync(nested)) return nested;
    }
  }
  return null;
}

function steamArt(appid) {
  const base = path.join(LIBCACHE, appid);
  const poster = findFirst(base, ['library_600x900.jpg', 'library_capsule.jpg']);
  const hero = findFirst(base, ['library_hero.jpg']);
  const header = findFirst(base, ['header.jpg', 'library_header.jpg']);
  return { poster: poster || header || hero, hero };
}

function steamGames() {
  let files;
  try { files = fs.readdirSync(STEAMAPPS); } catch { return []; }
  const out = [];
  for (const f of files) {
    if (!f.startsWith('appmanifest_') || !f.endsWith('.acf')) continue;
    let txt;
    try { txt = fs.readFileSync(path.join(STEAMAPPS, f), 'utf8'); } catch { continue; }
    const appid = acfField('appid', txt);
    const name = acfField('name', txt);
    if (!appid || !name || PLUMBING.test(name)) continue;
    const flags = parseInt(acfField('StateFlags', txt), 10);
    if (Number.isNaN(flags) || !(flags & 4)) continue; // 4 = fully installed
    const art = steamArt(appid);
    out.push({ id: appid, kind: 'steam', name, poster: art.poster, hero: art.hero });
  }
  return out;
}

// param.sfo is a small binary key/value blob PS4 dumps carry in sce_sys.
// Just enough parsing to pull TITLE out of it.
function sfo(file) {
  let data;
  try { data = fs.readFileSync(file); } catch { return {}; }
  if (data.length < 20 || data.toString('latin1', 0, 4) !== '\x00PSF') return {};
  try {
    const keyStart = data.readUInt32LE(8);
    const dataStart = data.readUInt32LE(12);
    const count = data.readUInt32LE(16);
    const out = {};
    for (let i = 0; i < count; i++) {
      const off = 20 + i * 16;
      const koff = data.readUInt16LE(off);
      const fmt = data.readUInt16LE(off + 2);
      const length = data.readUInt32LE(off + 4);
      const doff = data.readUInt32LE(off + 12);
      const ks = keyStart + koff;
      const key = data.toString('utf8', ks, data.indexOf(0, ks));
      const raw = data.subarray(dataStart + doff, dataStart + doff + length);
      if (fmt === 0x0404) out[key] = raw.readUInt32LE(0);
      else {
        const z = raw.indexOf(0);
        out[key] = raw.toString('utf8', 0, z === -1 ? raw.length : z);
      }
    }
    return out;
  } catch { return {}; }
}

function ps4Games() {
  let entries;
  try { entries = fs.readdirSync(PS4_DIR); } catch { return []; }
  const out = [];
  for (const entry of entries) {
    // Patch folders overlay the base automatically; they are not games.
    if (entry.endsWith('-patch') || entry.endsWith('-UPDATE')) continue;
    const gdir = path.join(PS4_DIR, entry);
    const eboot = path.join(gdir, 'eboot.bin');
    if (!fs.existsSync(eboot)) continue;
    const title = sfo(path.join(gdir, 'sce_sys', 'param.sfo')).TITLE || entry;
    const cover = path.join(gdir, 'cover.png');
    const icon0 = path.join(gdir, 'sce_sys', 'icon0.png');
    const art = fs.existsSync(cover) ? cover : (fs.existsSync(icon0) ? icon0 : null);
    out.push({ id: 'ps4:' + eboot, kind: 'ps4', name: title, poster: art, hero: null });
  }
  return out;
}

export function listGames() {
  const games = [...steamGames(), ...ps4Games()]
    .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
  // Big Picture is a launcher, not a game - it lives as a header action in the
  // Games tab now, not a tile in the grid.
  if (fs.existsSync(SHADPS4_APP)) {
    const tile = path.join(TILE_DIR, 'shadps4.png');
    games.push({
      id: 'shadps4', kind: 'app', name: 'shadPS4',
      poster: fs.existsSync(tile) ? tile : null, hero: null,
    });
  }
  return games;
}

// Art files may only be served from the known art roots; anything else is
// refused however the path was built.
export function isAllowedArt(p) {
  const real = path.resolve(p);
  return [LIBCACHE, PS4_DIR, TILE_DIR].some((root) => real.startsWith(root + path.sep));
}
