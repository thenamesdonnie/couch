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

// A viewer that stops reading (iOS backgrounds the tab, the phone walks out of
// range) keeps its socket open, so unchecked writes queue frames in memory for
// it forever - tens of megabytes a minute per stalled viewer. Frames are
// droppable by nature: skip them while the socket is backed up, and cut a
// viewer that never drains.
const STALL_MS = 15000;

function writeFrame(v, jpeg) {
  if (v.blocked) {
    if (Date.now() - v.blockedAt > STALL_MS) v.evict();
    return;
  }
  v.res.write(`--${BOUNDARY}\r\nContent-type: image/jpeg\r\nContent-length: ${jpeg.length}\r\n\r\n`);
  v.res.write(jpeg);
  if (v.res.write('\r\n')) return;
  v.blocked = true;
  v.blockedAt = Date.now();
  clearTimeout(v.stall);
  v.stall = setTimeout(() => { if (v.blocked) v.evict(); }, STALL_MS);
  v.res.once('drain', () => { v.blocked = false; clearTimeout(v.stall); });
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
  // This viewer's write state; evict is filled in below, before any frame can
  // reach it.
  const v = { res, blocked: false, blockedAt: 0, stall: null, evict: () => {} };

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
    clearTimeout(v.stall);
    stopFfmpeg();
    viewers.delete(evict);
  };
  const evict = () => {
    cleanup();
    try { res.destroy(); } catch { /* already gone */ }
  };
  v.evict = evict;
  viewers.add(evict);
  res.on('close', cleanup);
  res.on('error', cleanup);

  const wantX = () => src === 'x' || (src === 'auto' && gameSessionActive());

  while (!closed) {
    if (wantX()) {
      // ffmpeg's mpjpeg parts use its own boundary; rewrite is more work than
      // it is worth, so just re-frame each complete jpeg onto ours.
      const size = await grabSize();
      let ffFailed = false;
      await new Promise((resolve) => {
        if (closed) { resolve(); return; }
        ff = spawn('ffmpeg', ffmpegArgs(size), { env: XENV });
        FF_PROCS.add(ff);
        ff.on('close', () => FF_PROCS.delete(ff));
        // No ffmpeg on the box (or exec denied): an unhandled 'error' event
        // would kill the server, and respawning it flat out would spin.
        ff.on('error', (err) => { ffFailed = true; console.error('ffmpeg:', err.message); resolve(); });
        let buf = Buffer.alloc(0);
        ff.stdout.on('data', (chunk) => {
          buf = Buffer.concat([buf, chunk]);
          // Extract complete JPEGs (SOI ... EOI) out of the mpjpeg wrapping.
          let start;
          while ((start = buf.indexOf(Buffer.from([0xff, 0xd8, 0xff]))) !== -1) {
            const end = buf.indexOf(Buffer.from([0xff, 0xd9]), start + 3);
            if (end === -1) { if (start > 0) buf = buf.subarray(start); break; }
            writeFrame(v, buf.subarray(start, end + 2));
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
      if (ffFailed && !closed) await new Promise((r) => setTimeout(r, 2000));
    } else {
      try {
        const jpeg = await kodiGrab();
        if (closed) break;
        writeFrame(v, jpeg);
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
const GUARD_PIDFILE = '/tmp/steam-input-guard.pid';

// The guard stamps its pidfile the moment it starts enforcing (supersede());
// a pidfile written AFTER `since` means the suspend's guard is registered and
// safe to supersede. Bounded at the old fixed beat's 700ms so the worst case
// is exactly what the blind sleep gave; typical convergence is one or two
// 100ms beats. Exported with injectable knobs so the test can run it against
// a tmp pidfile at ms grain - never live /tmp.
export async function awaitGuardClaim(since, {
  pidfile = GUARD_PIDFILE, capMs = 700, grainMs = 100,
} = {}) {
  const end = Date.now() + capMs;
  for (;;) {
    try {
      if ((await fs.promises.stat(pidfile)).mtimeMs >= since) return true;
    } catch { /* not written yet */ }
    if (Date.now() >= end) return false; // cap reached - proceed like the old beat
    await new Promise((r) => setTimeout(r, Math.min(grainMs, end - Date.now())));
  }
}

// The desktop is not a window, but it is a destination - the phone has always
// offered it and the on-TV switcher (script.couch.switcher) needs it in the
// list it renders. One pseudo-entry here keeps both remotes reading the same
// menu from the same place.
const DESKTOP = { id: 'desktop', title: 'Desktop', kodi: false, cls: 'desktop' };

// Desktop plumbing is never a destination. The xfce display helper pops its
// "keep this configuration?" minimal dialog on every TV hotplug (root cause
// silenced 15 Aug with xfconf displays /Notify=0, but that reverts if xfce
// settings are ever reset) and it was showing up in BOTH switchers as a grey
// mystery card. Classes here vanish from the list before anything else looks
// at it.
const IGNORED_CLASSES = new Set(['xfce4-display-settings']);

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
    .filter((n) => n.startsWith(prefix) && n.endsWith('.jpg') && !n.endsWith('.tile.jpg')
                && !n.endsWith('.full.jpg'))
    .sort();
  return hits.length ? path.join(PAUSED_DIR, hits[hits.length - 1]) : null;
}

function gameLaunch(mode) {
  const p = spawn(GAME_LAUNCH, [mode], { env: XENV, detached: true, stdio: 'ignore' });
  // Unhandled 'error' events are fatal to the process; a missing launcher must
  // only cost this one switch.
  p.on('error', (err) => console.error(`game-launch ${mode}:`, err.message));
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

// Building the window list costs a python3 spawn and an X walk: measured
// 215ms end to end on this box for a 523-byte answer, of which ~33ms is the
// interpreter plus python-xlib and the rest is the walk. That is not a
// background number - it sits in front of the switcher sheet, which is a
// GESTURE (double-tap PS), and in front of every Screen-tab poll.
//
// So: one in-flight walk at a time, and a very short memory of the answer.
// The window doesn't have to be long to work, because the cost is bursty -
// the switcher and the phone both ask two or three times in quick succession
// while a sheet opens. TTL is deliberately shorter than a human notices a
// stale row (a window that closed 400ms ago still being listed) and shorter
// than the switcher's own list timeout.
//
// activateWindow() clears it, because the one moment staleness would be felt
// is the redraw straight after acting.
export const WINDOWS_TTL_MS = 600;
const _cache = { at: 0, value: null, inflight: null };
let _now = () => Date.now();
let _build = () => buildWindows();

// Test seams, in the shape awaitGuardClaim already uses: the real work stays
// the default and the test injects a clock and a builder rather than a live
// X server and a python spawn.
export function _setWindowsSeams({ now, build } = {}) {
  _now = now || (() => Date.now());
  _build = build || (() => buildWindows());
  invalidateWindows();
}

export function invalidateWindows() {
  _cache.at = 0;
  _cache.value = null;
}

export function windows() {
  if (_cache.value && _now() - _cache.at < WINDOWS_TTL_MS) {
    return Promise.resolve(_cache.value);
  }
  if (_cache.inflight) return _cache.inflight;      // single-flight
  _cache.inflight = Promise.resolve()
    .then(_build)
    .then((list) => {
      _cache.value = list;
      _cache.at = _now();
      return list;
    })
    .finally(() => { _cache.inflight = null; });
  return _cache.inflight;
}

async function buildWindows() {
  // Three subprocesses used to run nose to tail here: the window walk (53ms),
  // then game-pids (41ms), then gamewin (116ms) - 210ms in a straight line.
  // Only the last two are actually dependent on each other; neither needs the
  // window list. Starting the frozen-game lookup alongside the walk takes the
  // cold path to the length of its longer half, ~157ms, and changes nothing
  // about what is returned.
  //
  // suspendedFlag() is a sync file check, so it is safe to decide up front
  // whether the second half is needed at all.
  const walking = run('python3', [XINPUT, 'windows']);
  const findingPaused = suspendedFlag() ? pausedWindowId() : null;

  const out = await walking;
  let list;
  try { list = JSON.parse(out); } catch { return []; }
  list = list.filter((w) => !IGNORED_CLASSES.has(w.cls || ''));
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
      const wid = await (findingPaused || pausedWindowId());
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
  // Alt-tab thumbnails: any window still on screen (mapped - the compositor
  // holds real pixels even when Kodi covers it) gets a live-capture URL. The
  // timestamp busts Kodi's by-URL texture cache, same lesson as pause-snap's
  // stamped filenames. Frozen games keep their freeze-frame thumb from above
  // (truth at suspend time beats a capture of an unmapped window).
  const ts = Date.now();
  for (const w of list) {
    if (!w.thumb && w.mapped && !w.kodi) {
      w.thumb = `/api/art/winthumb?id=${w.id}&t=${ts}`;
    }
  }
  return [...list, { ...DESKTOP }];
}

// One X window, as pixels, resized for a tile. import(1) reads through the
// compositor so an obscured window still captures; an unmapped one would be
// black, which is why windows() only hands this URL to mapped rows.
export async function windowThumb(id) {
  if (!/^0x[0-9a-f]+$/i.test(id)) throw new Error('bad window id');
  return await new Promise((resolve, reject) => {
    execFile('import', ['-silent', '-window', id, '-resize', '480', 'jpeg:-'],
      { env: XENV, encoding: 'buffer', maxBuffer: 4 * 1024 * 1024, timeout: 4000 },
      (err, stdout) => {
        if (err || !stdout || stdout.length < 1000) {
          reject(err || new Error('empty capture'));
        } else resolve(stdout);
      });
  });
}

export async function activateWindow(id) {
  // Whatever happens below changes the stacking, and the next thing the
  // caller does is ask for the list again. Drop the memo so that redraw is
  // the truth rather than a copy of the world before the tap.
  invalidateWindows();
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
      const suspendStarted = Date.now();
      await run(GAME_LAUNCH, ['suspend']);
      // game-launch backgrounds its guard, so wait for it to claim the
      // pidfile - superseding a guard that has not registered yet would
      // leave the old one running and fighting for the screen. This was a
      // blind 700ms beat; the claim typically lands in 100-200ms, so poll
      // for a pidfile stamped after our suspend instead, same 700ms cap
      // (the cap is the old worst case: on timeout we proceed exactly as
      // the fixed sleep always did).
      await awaitGuardClaim(suspendStarted);
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
