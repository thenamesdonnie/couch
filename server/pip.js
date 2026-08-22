// The phone's end of pipd (tools/pipd): the picture-in-picture window that
// floats over a running game, which Donnie drags around from the sofa.
//
// pipd owns an X overlay on gamescope's nested display and listens on a unix
// socket, one JSON request per line, one JSON reply, connection closed. This
// file is the only thing on the server that speaks to it, and it exists mostly
// to make ONE fact easy to live with:
//
//   PIPD IS USUALLY NOT RUNNING. It only lives as long as one picture, so "no
//   socket", "connection refused" (a stale socket file left by a daemon that
//   died) and "connected but never answered" are all NORMAL, and every one of
//   them comes back as a clean 200 with {running:false}. The panel on the phone
//   says "nothing is floating over the TV" and offers a picker instead of dead
//   controls. A 500 here would paint an error banner on a state that is not an
//   error.
//
// Since 22 Aug the phone can also CREATE that state: /library lists what is in
// the video library with a real path for each entry, and /start spawns pipd
// detached with the chosen file. Detached matters - the daemon has to survive a
// couch.service restart, since the picture on the TV has nothing to do with
// this server's lifetime.
//
// The timeout matters as much as the missing socket: a unix socket on the same
// box answers in microseconds, so a daemon that has not replied within a second
// is wedged, and an Express request must never be held hostage to it.
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import { spawn as childSpawn } from 'node:child_process';
import express from 'express';
import { PIP_SOCKET, PIPD_BIN, PIP_LOG, PIP_DISPLAY, MEDIA_ROOT } from './config.js';
import { rpc } from './kodi.js';
import { pathsFor } from './jellyfin.js';

// A unix socket to a local process. If this is not enough, the daemon is stuck.
export const REPLY_TIMEOUT_MS = 1000;

// How long a freshly spawned pipd is given to bind its socket. It has an X
// overlay to create and a player to fork before it listens, and the box is
// regularly busy running a game, so this is generous; the phone is holding a
// spinner on a button the whole time, not the whole panel.
export const START_TIMEOUT_MS = 8000;
export const START_POLL_MS = 200;

// mpv flags for a picture in the corner: hardware decode because this is
// running alongside whatever else is on the TV, and no subtitles because they
// would be rendered at the size of a matchbox and be unreadable anyway.
export const PLAYER_ARGS = '--hwdec=auto --no-sub';

// Seams, same shape as screen.js's _setWindowsSeams: tests point the client at
// a stub daemon on a temp path, a fake spawn and a temp media root. Called with
// nothing it restores the real ones.
const DEFAULTS = {
  socketPath: PIP_SOCKET,
  timeoutMs: REPLY_TIMEOUT_MS,
  mediaRoot: MEDIA_ROOT,
  pipd: PIPD_BIN,
  logPath: PIP_LOG,
  display: PIP_DISPLAY,
  spawn: childSpawn,
  startTimeoutMs: START_TIMEOUT_MS,
  pollMs: START_POLL_MS,
  rpc,
  pathsFor,
};

let seams = { ...DEFAULTS };
export function _setPipSeams(over = {}) {
  seams = { ...DEFAULTS };
  for (const [k, v] of Object.entries(over)) {
    if (v !== undefined) seams[k] = v;
  }
}

// "There is no daemon to talk to", as distinct from "the daemon is broken".
// Only this one turns into {running:false}; anything else is a real fault and
// is allowed to surface as one.
export class PipDown extends Error {}

// "There is already a picture up." Not a fault either, but not something to
// paper over: starting a second daemon would fight the first one for the same
// socket path and the phone would end up talking to whichever won.
export class PipBusy extends Error {}

// One command, one reply. Resolves the daemon's own object (which may be
// {ok:false,...} - a refused command is still an answer), rejects with PipDown
// when there is nothing listening, and with a plain Error when whatever is
// listening is not pipd.
export function request(msg, opts = {}) {
  const socketPath = opts.socketPath ?? seams.socketPath;
  const timeoutMs = opts.timeoutMs ?? seams.timeoutMs;
  return new Promise((resolve, reject) => {
    const sock = net.createConnection(socketPath);
    let buf = '';
    let done = false;

    const finish = (err, value) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      sock.destroy();
      if (err) reject(err);
      else resolve(value);
    };

    const timer = setTimeout(
      () => finish(new PipDown(`pipd did not answer within ${timeoutMs}ms`)),
      timeoutMs,
    );
    timer.unref?.();

    // Everything the daemon sends before the newline is the answer; it closes
    // the connection straight after, so a close with a part-line in hand is
    // still worth trying to read.
    const take = (text) => {
      try {
        finish(null, JSON.parse(text));
      } catch {
        finish(new Error('pipd sent something that is not JSON'));
      }
    };

    sock.on('connect', () => sock.write(`${JSON.stringify(msg)}\n`));
    sock.on('data', (chunk) => {
      buf += chunk;
      const nl = buf.indexOf('\n');
      if (nl !== -1) take(buf.slice(0, nl));
    });
    sock.on('close', () => {
      if (buf.trim()) take(buf.trim());
      else finish(new PipDown('pipd closed the connection without answering'));
    });
    // ENOENT (no socket), ECONNREFUSED (stale socket file), EACCES (someone
    // else's daemon): all of them mean the same thing to the phone.
    sock.on('error', (err) => finish(new PipDown(`pipd is not answering (${err.code || err.message})`)));
  });
}

// The one answer shape the phone ever sees, whatever happened underneath:
//   { running: false, reason }                         nothing to talk to
//   { running: true, ok: false, error }                the daemon said no
//   { running: true, ok: true, output, pixels, ... }   a real status
export async function send(msg, opts = {}) {
  try {
    const reply = await request(msg, opts);
    if (!reply || typeof reply !== 'object') throw new Error('pipd sent an answer that is not an object');
    return { running: true, ...reply };
  } catch (err) {
    if (err instanceof PipDown) return { running: false, reason: err.message };
    throw err;
  }
}

export const status = (opts) => send({ cmd: 'status' }, opts);

// --- input checking -------------------------------------------------------
// The phone sends normalised coordinates because the output is 3840x2160 today
// and something else after a mode change (see pipd's module docstring). pipd
// clamps and snaps whatever it is given, so these checks are only here to keep
// nonsense (NaN from an empty field, a string) off the socket.

const CORNERS = ['nw', 'ne', 'sw', 'se'];

const unit = (v) => Number.isFinite(v) && v >= 0 && v <= 1;

export function placeCommand(body = {}) {
  const cmd = { cmd: 'place', snap: body.snap !== false };
  for (const key of ['nx', 'ny', 'nw', 'nh']) {
    if (body[key] === undefined || body[key] === null) continue;
    const v = Number(body[key]);
    if (!unit(v)) throw new RangeError(`${key} must be between 0 and 1`);
    cmd[key] = v;
  }
  if (cmd.nx === undefined && cmd.ny === undefined && cmd.nw === undefined && cmd.nh === undefined) {
    throw new RangeError('place needs at least one of nx, ny, nw, nh');
  }
  return cmd;
}

// --- what to play ---------------------------------------------------------
// The picker's data comes from Kodi's own video library, because that is the
// list Donnie already recognises from the television. Kodi does not know where
// any of it lives on disk though - the jellyfin-kodi addon owns the library, so
// every `file` is a plugin:// url - so the id in that url is handed to Jellyfin
// for the real path. See pathsFor() in jellyfin.js.

const JF_ID = /[?&]id=([0-9a-f]{32})/;

const jellyfinId = (file) => String(file || '').match(JF_ID)?.[1] || null;

// Adds `path` to each Kodi item: its own file if the library happens to hold a
// real one (a source added to Kodi directly), otherwise Jellyfin's answer, and
// null when neither knows. A null path is not fatal here - the picker shows the
// title greyed out, which is a truer account than dropping it silently.
export async function withPaths(items) {
  const ids = items.map((i) => jellyfinId(i.file));
  const found = ids.some(Boolean) ? await seams.pathsFor(ids.filter(Boolean)) : new Map();
  return items.map((item, i) => {
    const direct = typeof item.file === 'string' && item.file.startsWith('/') ? item.file : null;
    return { ...item, path: direct || found.get(ids[i]) || null };
  });
}

export async function listMovies() {
  const res = await seams.rpc('VideoLibrary.GetMovies', {
    properties: ['file', 'year', 'runtime'],
    sort: { method: 'title', order: 'ascending', ignorearticle: true },
  });
  const withFiles = await withPaths(res?.movies || []);
  return withFiles.map((m) => ({
    id: m.movieid, title: m.label || m.title || '', year: m.year || null,
    runtime: m.runtime || null, path: m.path,
  }));
}

export async function listShows() {
  const res = await seams.rpc('VideoLibrary.GetTVShows', {
    properties: ['year'],
    sort: { method: 'title', order: 'ascending', ignorearticle: true },
  });
  return (res?.tvshows || []).map((s) => ({
    id: s.tvshowid, title: s.label || s.title || '', year: s.year || null,
  }));
}

// Kodi hands seasons back in whatever order the database felt like (verified:
// a show came back 5, 3, 4, 6, 7, 8), so they are sorted here rather than
// trusted.
export async function listSeasons(tvshowid) {
  const res = await seams.rpc('VideoLibrary.GetSeasons', {
    tvshowid, properties: ['season', 'episode'],
  });
  return (res?.seasons || [])
    .map((s) => ({ season: s.season, label: s.label || `Season ${s.season}`, episodes: s.episode || 0 }))
    .sort((a, b) => a.season - b.season);
}

export async function listEpisodes(tvshowid, season) {
  const res = await seams.rpc('VideoLibrary.GetEpisodes', {
    tvshowid, season, properties: ['title', 'season', 'episode', 'file', 'runtime'],
  });
  const withFiles = await withPaths(res?.episodes || []);
  return withFiles
    .map((e) => ({
      id: e.episodeid, title: e.title || e.label || '', season: e.season,
      episode: e.episode, runtime: e.runtime || null, path: e.path,
    }))
    .sort((a, b) => a.episode - b.episode);
}

// --- starting a picture ---------------------------------------------------

// Containers worth handing mpv. The point of the list is not mpv's capability
// (it plays nearly anything) but the picker's honesty: a .srt or a .nfo sitting
// beside an episode is not something to put on the television.
const VIDEO_EXTS = new Set([
  '.mkv', '.mp4', '.m4v', '.avi', '.mov', '.ts', '.m2ts', '.mts',
  '.mpg', '.mpeg', '.webm', '.wmv', '.flv', '.ogv', '.divx', '.iso',
]);

// The gate between an unauthenticated phone and the filesystem. Whatever comes
// out of here is a real, existing video file inside the media library, and
// nothing else ever reaches the spawn.
export function resolveMedia(input) {
  if (typeof input !== 'string' || !input.trim()) throw new RangeError('a file to play is required');
  let base;
  try {
    base = fs.realpathSync(seams.mediaRoot);
  } catch {
    throw new RangeError(`the media library (${seams.mediaRoot}) is not there`);
  }
  const inside = (p) => p === base || p.startsWith(base + path.sep);

  // Checked twice on purpose. Lexically first, so "/mnt/media/../etc/shadow" is
  // refused by its own shape before the filesystem is touched at all; then
  // again on the resolved path, so a symlink INSIDE the library cannot be used
  // to step out of it. Either check alone is bypassable.
  const lexical = path.resolve(input.trim());
  if (!inside(lexical)) throw new RangeError('that file is not in the media library');
  let real;
  try {
    real = fs.realpathSync(lexical);
  } catch {
    throw new RangeError('there is no file there');
  }
  if (!inside(real)) throw new RangeError('that file is not in the media library');
  if (!fs.statSync(real).isFile()) throw new RangeError('that is a folder, not a video');
  const ext = path.extname(real).toLowerCase();
  if (!VIDEO_EXTS.has(ext)) throw new RangeError(`${ext || 'that'} is not a video file`);
  return real;
}

// pipd must outlive this server: a couch.service restart has nothing to do with
// the picture on the television, and a child that dies with its parent would
// take the video with it. detached:true is setsid, stdio goes to a log file
// (the ONLY account of a start that fails after the fork), and unref lets node
// exit while the daemon carries on.
export function spawnPipd(media) {
  const args = [
    '--display', seams.display,
    '--socket', seams.socketPath,
    '--player-args', PLAYER_ARGS,
    media,
  ];
  let fd = null;
  try { fd = fs.openSync(seams.logPath, 'a'); } catch { /* a start with no log beats no start */ }
  const child = seams.spawn(seams.pipd, args, {
    detached: true,
    stdio: ['ignore', fd ?? 'ignore', fd ?? 'ignore'],
    env: { ...process.env, DISPLAY: seams.display },
  });
  // An unexecutable pipd raises 'error' on the child, which is fatal to the
  // whole process if nobody is listening. The route reports the failure by
  // the socket never coming up, which is the same signal as any other bad
  // start.
  child.on?.('error', (err) => console.error('pipd failed to start:', err.message));
  child.unref?.();
  if (fd !== null) { try { fs.closeSync(fd); } catch { /* already gone */ } }
  return child;
}

// Poll the socket until the new daemon answers. Returns the last status either
// way, so the caller can tell "it came up" from "it never did".
export async function waitForPipd() {
  const deadline = Date.now() + seams.startTimeoutMs;
  for (;;) {
    const now = await status();
    if (now.running) return now;
    if (Date.now() >= deadline) return now;
    await new Promise((r) => setTimeout(r, seams.pollMs));
  }
}

// --- routes ---------------------------------------------------------------
// Mounted at /api/pip by index.js. `answer` is index.js's own wrap in local
// form: the routes return a body, a thrown error becomes a 502, and a bad
// request answers 400 itself.

const answer = (fn) => async (req, res) => {
  try {
    const out = await fn(req, res);
    if (!res.headersSent) res.json(out ?? { ok: true });
  } catch (err) {
    if (res.headersSent) return;
    if (err instanceof RangeError) res.status(400).json({ error: String(err.message) });
    else if (err instanceof PipBusy) res.status(409).json({ error: String(err.message), running: true });
    else res.status(502).json({ error: String(err.message || err) });
  }
};

export const routes = express.Router();

// Never cached: this is a live reading of something that mostly does not exist.
routes.get('/', answer(async (req, res) => {
  res.set('cache-control', 'no-store');
  return status();
}));

// What the phone can put on the TV. Three shallow steps rather than one big
// tree: a season of a long-running show is 25 Jellyfin path lookups, and there
// is no sense paying for all of them to draw a list of show names.
routes.get('/library', answer(async (req, res) => {
  res.set('cache-control', 'no-store');
  const [movies, shows] = await Promise.all([listMovies(), listShows()]);
  return { movies, shows };
}));

routes.get('/library/seasons', answer(async (req, res) => {
  const show = Number(req.query.show);
  if (!Number.isInteger(show) || show <= 0) throw new RangeError('show must be a tvshowid');
  res.set('cache-control', 'no-store');
  return { show, seasons: await listSeasons(show) };
}));

routes.get('/library/episodes', answer(async (req, res) => {
  const show = Number(req.query.show);
  const season = Number(req.query.season);
  if (!Number.isInteger(show) || show <= 0) throw new RangeError('show must be a tvshowid');
  if (!Number.isInteger(season) || season < 0) throw new RangeError('season must be a season number');
  res.set('cache-control', 'no-store');
  return { show, season, episodes: await listEpisodes(show, season) };
}));

// Put a picture up. The status probe first is not just politeness: two daemons
// on one socket path is a state with no good way out from the phone, since the
// second one unlinks the first one's socket and the first one is then
// unreachable and unkillable from here.
routes.post('/start', answer(async (req) => {
  const media = resolveMedia(req.body?.path);
  const before = await status();
  if (before.running) throw new PipBusy('a picture is already on the TV, close that one first');
  spawnPipd(media);
  const now = await waitForPipd();
  if (!now.running) throw new Error(`pipd did not come up (${now.reason}). See ${seams.logPath}`);
  return { ...now, started: media };
}));

// Every write answers with the resulting status, so the phone's rectangle can
// be reconciled to where the picture actually ended up. pipd clamps to the
// screen and snaps to edges, so the answer is regularly not what was asked for.
routes.post('/place', answer(async (req) => send(placeCommand(req.body ?? {}))));

routes.post('/corner', answer(async (req) => {
  const where = String(req.body?.where || '');
  if (!CORNERS.includes(where)) throw new RangeError(`where must be one of ${CORNERS.join(', ')}`);
  return send({ cmd: 'corner', where });
}));

routes.post('/scale', answer(async (req) => {
  const factor = Number(req.body?.factor);
  if (!Number.isFinite(factor) || factor <= 0) throw new RangeError('factor must be a positive number');
  return send({ cmd: 'scale', factor });
}));

routes.post('/opacity', answer(async (req) => {
  const value = Number(req.body?.value);
  if (!unit(value)) throw new RangeError('value must be between 0 and 1');
  return send({ cmd: 'opacity', value });
}));

routes.post('/show', answer(async () => send({ cmd: 'show' })));
routes.post('/hide', answer(async () => send({ cmd: 'hide' })));

// Transport. play/pause are explicit rather than a toggle - a toggle races
// its own read-back (the spotify lesson), and a doubled tap would undo itself.
routes.post('/play', answer(async () => send({ cmd: 'play' })));
routes.post('/pause', answer(async () => send({ cmd: 'pause' })));

routes.post('/seek', answer(async (req) => {
  const seconds = Number(req.body?.seconds);
  if (!Number.isFinite(seconds) || Math.abs(seconds) > 3600) {
    throw new RangeError('seconds must be a number within an hour either way');
  }
  return send({ cmd: 'seek', seconds });
}));

routes.post('/volume', answer(async (req) => {
  const value = Number(req.body?.value);
  if (!Number.isFinite(value) || value < 0 || value > 100) throw new RangeError('value must be 0..100');
  return send({ cmd: 'volume', value });
}));

routes.post('/mute', answer(async (req) => send({ cmd: 'mute', value: req.body?.value !== false })));

// "Stop" rather than "quit" on the wire the phone speaks: closing the picture
// is what the button does, and the daemon exiting is how it is done.
routes.post('/stop', answer(async () => send({ cmd: 'quit' })));
