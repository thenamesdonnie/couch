// The clickable screen: capture whatever the TV is showing, deliver it to the
// phone, and inject clicks and keys back. Two capture paths because of how the
// box renders: Kodi draws fullscreen GL that X grabs see as BLACK, so while
// Kodi owns the screen we use Kodi's own screenshot action; during a game or
// Steam session (normal X windows) a root grab works and is faster.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { execFile, spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { rpc } from './kodi.js';
import { PAUSED_DIR, listGames } from './games.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const XINPUT = path.join(__dirname, 'xinput.py');
const SHOT_DIR = '/tmp/couch-screen';

const XENV = {
  ...process.env,
  DISPLAY: process.env.DISPLAY || ':0',
  XAUTHORITY: process.env.XAUTHORITY || path.join(os.homedir(), '.Xauthority'),
};

function run(bin, args, opts = {}) {
  return new Promise((resolve, reject) => {
    execFile(bin, args, { env: XENV, timeout: 15000, maxBuffer: 32 * 1024 * 1024, ...opts },
      (err, out, errOut) => (err ? reject(new Error(String(errOut || err.message).trim())) : resolve(out)));
  });
}

function gameSessionActive() {
  return fs.existsSync('/tmp/game-session');
}

// import(1) straight to a downscaled jpeg on stdout.
function xGrab() {
  return run('import', ['-window', 'root', '-resize', '1280', 'jpeg:-'], { encoding: 'buffer' });
}

// Grab Kodi's own GL window by id. This is SILENT - unlike Kodi's screenshot
// action, which pops a shutter sound + "saved" toast on every frame (the noise
// that made the live view unusable). Root grabs are black over Kodi's GL, but
// grabbing the window itself captures the GUI fine. The window id changes when
// Kodi restarts, so it is re-resolved on a failed grab.
let kodiWinId = null;

async function kodiWindow() {
  if (kodiWinId) return kodiWinId;
  kodiWinId = (await run('python3', [XINPUT, 'kodiwin'])).trim();
  return kodiWinId;
}

async function kodiGrab() {
  try {
    const wid = await kodiWindow();
    return await run('import', ['-window', wid, '-resize', '1280', '-quality', '82', 'jpeg:-'], { encoding: 'buffer' });
  } catch {
    kodiWinId = null; // Kodi may have restarted; re-resolve next time.
    const wid = await kodiWindow();
    return run('import', ['-window', wid, '-resize', '1280', '-quality', '82', 'jpeg:-'], { encoding: 'buffer' });
  }
}

export async function capture(src = 'auto') {
  if (src === 'x') return { jpeg: await xGrab(), source: 'x' };
  if (src === 'kodi') return { jpeg: await kodiGrab(), source: 'kodi' };
  // auto: a live game session means Steam or a game owns the screen; otherwise
  // assume Kodi. If Kodi is down (crash window), fall back to the X grab.
  if (gameSessionActive()) return { jpeg: await xGrab(), source: 'x' };
  try {
    return { jpeg: await kodiGrab(), source: 'kodi' };
  } catch {
    return { jpeg: await xGrab(), source: 'x' };
  }
}

// --- live stream ---
// One multipart MJPEG response, same boundary format ffmpeg's mpjpeg muxer
// writes, so both frame producers feed the same <img> on the phone:
// - desktop/game frames from a persistent ffmpeg x11grab at 8fps (cheap,
//   smooth, but sees Kodi's GL as black)
// - Kodi frames from its screenshot action at ~1.3fps (the only capture that
//   works while Kodi owns the screen)
// Auto mode watches the game-session flag and switches producer mid-stream.

const BOUNDARY = 'couchframe';

// iOS keeps MJPEG sockets open after the <img> moves on to a new stream URL,
// so viewers linger past their useful life. Rather than refusing new viewers
// at the cap (which locked the phone out with a broken image after a few
// source switches), evict the oldest.
const MAX_VIEWERS = 3;
const viewers = new Set(); // insertion order = oldest first; entries are evict()

// x11grab needs the real screen size or it grabs a fixed-size corner of the
// desktop. Queried fresh per ffmpeg start: the resolution changes at runtime
// (Steam Big Picture switches modes), so it must not be cached.
async function grabSize() {
  try {
    const [w, h] = (await run('python3', [XINPUT, 'geometry'])).trim().split(' ').map(Number);
    if (w && h) return `${w}x${h}`;
  } catch { /* fall through */ }
  return '1920x1080';
}

function ffmpegArgs(size) {
  return [
    '-hide_banner', '-loglevel', 'error',
    '-f', 'x11grab', '-framerate', '8', '-video_size', size, '-i', XENV.DISPLAY,
    '-vf', 'scale=1280:-2', '-c:v', 'mjpeg', '-q:v', '8',
    '-f', 'mpjpeg', '-',
  ];
}

// couch.service runs with KillMode=process so a couch restart cannot take a
// running game down with it - which also means systemd no longer reaps our
// ffmpeg children. Kill them ourselves on the way out.
const FF_PROCS = new Set();
for (const sig of ['SIGTERM', 'SIGINT']) {
  process.on(sig, () => {
    for (const p of FF_PROCS) { try { p.kill('SIGKILL'); } catch { /* gone */ } }
    process.exit(0);
  });
}

function writeFrame(res, jpeg) {
  res.write(`--${BOUNDARY}\r\nContent-type: image/jpeg\r\nContent-length: ${jpeg.length}\r\n\r\n`);
  res.write(jpeg);
  res.write('\r\n');
}

export async function stream(req, res, src = 'auto') {
  while (viewers.size >= MAX_VIEWERS) {
    viewers.values().next().value(); // evict the oldest viewer
  }
  res.writeHead(200, {
    'content-type': `multipart/x-mixed-replace; boundary=${BOUNDARY}`,
    'cache-control': 'no-store',
    connection: 'close',
  });

  let closed = false;
  let ff = null;

  const stopFfmpeg = () => {
    if (ff) { ff.kill('SIGKILL'); ff = null; }
  };

  // The response's close is the reliable end-of-viewer signal; the request's
  // own close does not always fire for a finished GET, which left the loop
  // spawning ffmpeg into a dead socket.
  let cleaned = false;
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    closed = true;
    stopFfmpeg();
    viewers.delete(evict);
  };
  const evict = () => {
    cleanup();
    try { res.destroy(); } catch { /* already gone */ }
  };
  viewers.add(evict);
  res.on('close', cleanup);
  res.on('error', cleanup);

  const wantX = () => src === 'x' || (src === 'auto' && gameSessionActive());

  while (!closed) {
    if (wantX()) {
      // ffmpeg's mpjpeg parts use its own boundary; rewrite is more work than
      // it is worth, so just re-frame each complete jpeg onto ours.
      const size = await grabSize();
      await new Promise((resolve) => {
        if (closed) { resolve(); return; }
        ff = spawn('ffmpeg', ffmpegArgs(size), { env: XENV });
        FF_PROCS.add(ff);
        ff.on('close', () => FF_PROCS.delete(ff));
        let buf = Buffer.alloc(0);
        ff.stdout.on('data', (chunk) => {
          buf = Buffer.concat([buf, chunk]);
          // Extract complete JPEGs (SOI ... EOI) out of the mpjpeg wrapping.
          let start;
          while ((start = buf.indexOf(Buffer.from([0xff, 0xd8, 0xff]))) !== -1) {
            const end = buf.indexOf(Buffer.from([0xff, 0xd9]), start + 3);
            if (end === -1) { if (start > 0) buf = buf.subarray(start); break; }
            writeFrame(res, buf.subarray(start, end + 2));
            buf = buf.subarray(end + 2);
          }
          if (buf.length > 8 * 1024 * 1024) buf = Buffer.alloc(0);
        });
        ff.on('close', resolve);
        // In auto mode, fall back to Kodi frames when the game session ends.
        const watch = setInterval(() => {
          if (closed || !wantX()) { clearInterval(watch); stopFfmpeg(); }
        }, 1000);
        ff.on('close', () => clearInterval(watch));
      });
    } else {
      try {
        const jpeg = await kodiGrab();
        if (closed) break;
        writeFrame(res, jpeg);
      } catch {
        if (closed) break;
        // Kodi down or mid-restart: brief black frame beats a dead stream.
        await new Promise((r) => setTimeout(r, 1000));
      }
      await new Promise((r) => setTimeout(r, 350));
    }
  }
  res.end();
}

export async function click(xFrac, yFrac, button = 1) {
  const xf = Math.max(0, Math.min(1, Number(xFrac)));
  const yf = Math.max(0, Math.min(1, Number(yFrac)));
  const out = await run('python3', [XINPUT, 'click', String(xf), String(yf), String(button)]);
  try { return JSON.parse(out); } catch { return { text: false }; }
}

export function typeText(text) {
  const t = String(text).slice(0, 500);
  if (!t) return Promise.resolve('');
  return run('python3', [XINPUT, 'type', t]);
}

const KEYS = new Set(['Return', 'BackSpace', 'Tab', 'Escape', 'Up', 'Down', 'Left', 'Right', 'space']);

export function pressKey(name) {
  if (!KEYS.has(name)) return Promise.reject(new Error('unrecognised key'));
  return run('python3', [XINPUT, 'key', name]);
}

// --- window switching ---
// The switcher is state-aware, not a raw X raise: raw raises can strand the
// console (a frozen game visibly on top, or Kodi on screen while the pad
// still belongs to the game). Switching to Kodi mid-game suspends properly;
// switching to a paused game resumes it, exactly like the PS button paths.

const GAME_LAUNCH = path.join(os.homedir(), '.local/bin/game-launch');
const GUARD = path.join(os.homedir(), '.local/bin/steam-input-guard');

// The desktop is not a window, but it is a destination - the phone has always
// offered it and the on-TV switcher (script.couch.switcher) needs it in the
// list it renders. One pseudo-entry here keeps both remotes reading the same
// menu from the same place.
const DESKTOP = { id: 'desktop', title: 'Desktop', kodi: false, cls: 'desktop' };

function suspendedFlag() {
  return fs.existsSync('/tmp/game-suspended');
}

function suspendedAppid() {
  try { return fs.readFileSync('/tmp/game-suspended', 'utf8').trim(); } catch { return ''; }
}

// The paused game's last rendered frame, captured at suspend time by
// ~/.local/bin/pause-snap. Names carry the capture time
// (<appid>__<epoch_ms>.jpg), so the newest is simply the last one in sort
// order - and every capture is a new url, which is what stops a phone (or
// Kodi) serving the frame from the previous time this game was paused.
function pausedFrame(appid) {
  const prefix = `${String(appid).replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 100)}__`;
  let names;
  try { names = fs.readdirSync(PAUSED_DIR); } catch { return null; }
  const hits = names
    .filter((n) => n.startsWith(prefix) && n.endsWith('.jpg') && !n.endsWith('.tile.jpg'))
    .sort();
  return hits.length ? path.join(PAUSED_DIR, hits[hits.length - 1]) : null;
}

function gameLaunch(mode) {
  const p = spawn(GAME_LAUNCH, [mode], { env: XENV, detached: true, stdio: 'ignore' });
  p.unref();
}

async function anyGameRunning() {
  try {
    const pids = (await run(path.join(os.homedir(), '.local/bin/game-pids'), [])).trim().split('\n');
    return pids.some((p) => {
      try {
        const stat = fs.readFileSync(`/proc/${p}/stat`, 'utf8');
        // state is the first field after the (comm), which may contain spaces
        return stat.slice(stat.lastIndexOf(')') + 2).split(' ')[0] !== 'T';
      } catch { return false; }
    });
  } catch { return false; }
}

// The frozen game's own window id, iconified and all (the suspend unmaps it to
// drop the pointer grab it was holding - see xinput.py iconify). 'paused' when
// X cannot name it at all: activateWindow takes that sentinel and resumes by
// the flag, since there is nothing to raise anyway.
async function pausedWindowId() {
  try {
    const pids = (await run(path.join(os.homedir(), '.local/bin/game-pids'), []))
      .trim().split(/\s+/).filter(Boolean);
    if (!pids.length) return 'paused';
    const wid = (await run('python3', [XINPUT, 'gamewin', '--any-state', ...pids])).trim();
    return /^0x[0-9a-f]+$/i.test(wid) ? wid : 'paused';
  } catch { return 'paused'; }
}

// A paused game is named by its appid on disk; the library knows it by name.
function pausedLabel(appid) {
  try {
    const g = listGames().find((x) => String(x.id) === String(appid));
    if (g && g.name) return g.name;
  } catch { /* library unreadable - the appid still names it */ }
  return appid || 'Game';
}

export async function windows() {
  const out = await run('python3', [XINPUT, 'windows']);
  let list;
  try { list = JSON.parse(out); } catch { return []; }
  if (suspendedFlag()) {
    // The frozen game keeps its row, marked, and now wearing the frame it was
    // frozen on: the switcher answers "where was I?" without resuming first.
    const appid = suspendedAppid();
    const frame = pausedFrame(appid);
    const thumb = frame ? { thumb: `/api/art/game?p=${encodeURIComponent(frame)}` } : {};
    let marked = 0;
    for (const w of list) {
      if (!(w.cls || '').startsWith('steam_app')) continue;
      w.title += ' · paused';
      w.paused = true;
      Object.assign(w, thumb);
      marked += 1;
    }
    if (!marked) {
      // Nothing in the list carries Proton's class - a shadPS4 game never
      // does, and an iconified window would not if a window manager dropped it
      // from _NET_CLIENT_LIST (xfwm4 keeps them, but the only route back into
      // a frozen game must not rest on that: this same endpoint feeds BOTH the
      // phone switcher and the Kodi addon). So ask X which window the frozen
      // processes own, iconified and all, and mark that row if it is already
      // here; only if it is genuinely absent is a synthetic row appended.
      // Either way activateWindow routes it by its paused flag, not by its id.
      const wid = await pausedWindowId();
      const own = wid !== 'paused'
        && list.find((w) => String(w.id).toLowerCase() === wid.toLowerCase());
      if (own) {
        own.title += ' · paused';
        own.paused = true;
        Object.assign(own, thumb);
      } else {
        list.push({
          id: wid,
          title: `${pausedLabel(appid)} · paused`,
          kodi: false,
          cls: 'paused-game',
          paused: true,
          ...thumb,
        });
      }
    }
  }
  return [...list, { ...DESKTOP }];
}

export async function activateWindow(id) {
  const session = gameSessionActive();
  const suspended = suspendedFlag();
  if (id === 'desktop') {
    // The desktop hides everything, so a game left running behind it would
    // be playing to nobody with the pad still routed to it: suspend first,
    // exactly as picking Kodi does. game-launch suspend is synchronous, but
    // it leaves a 6s kodi-guard behind that would raise Kodi back over the
    // desktop a second later - so a zero-length guard supersedes it through
    // the guard's own SIGTERM handoff rather than a blind kill.
    if (session && !suspended && await anyGameRunning()) {
      await run(GAME_LAUNCH, ['suspend']);
      // game-launch backgrounds its guard, so give it a beat to claim the
      // pidfile - superseding a guard that has not registered yet would
      // leave the old one running and fighting for the screen.
      await new Promise((r) => setTimeout(r, 700));
      await run(GUARD, ['kodi', '0']).catch(() => { /* nothing to supersede */ });
    }
    return run('python3', [XINPUT, 'showdesktop']);
  }
  // Anything else is a window, and a window under a shown desktop stays
  // hidden however politely it is raised.
  await run('python3', [XINPUT, 'showdesktop', 'off']).catch(() => { /* no wm */ });
  if (id === 'kodi') {
    if (session && !suspended && await anyGameRunning()) {
      gameLaunch('suspend'); // freeze + pad to Kodi + guard, like a PS hold
      return 'suspending';
    }
    const wid = (await run('python3', [XINPUT, 'kodiwin'])).trim();
    return run('python3', [XINPUT, 'activate', wid]);
  }
  if (id === 'paused') {
    // The synthetic row windows() falls back to when the frozen game has no
    // listable window. There is nothing to raise; the resume is the whole
    // answer, and game-launch maps the window back on its way in.
    if (!suspended) throw new Error('nothing is paused');
    gameLaunch('resume');
    return 'resuming';
  }
  if (!/^0x[0-9a-f]+$/i.test(id)) throw new Error('bad window id');
  const target = (await windows()).find((w) => w.id.toLowerCase() === id.toLowerCase());
  if (target && (target.paused || (target.cls || '').startsWith('steam_app'))) {
    if (suspended) {
      gameLaunch('resume'); // thaw + pad to game + guard, like a PS tap
      return 'resuming';
    }
    if (session) {
      gameLaunch('focus'); // raise properly (iconifies Steam's squatters)
      return 'focusing';
    }
  }
  return run('python3', [XINPUT, 'activate', id]);
}
