// The phone's end of pipd (tools/pipd): the picture-in-picture window that
// floats over a running game, which Donnie drags around from the sofa.
//
// pipd owns an X overlay on gamescope's nested display and listens on a unix
// socket, one JSON request per line, one JSON reply, connection closed. This
// file is the only thing on the server that speaks to it, and it exists mostly
// to make ONE fact easy to live with:
//
//   PIPD IS USUALLY NOT RUNNING. It only exists while a game is wrapped in
//   gamescope with a video handed to it, which is a rare state and not one the
//   phone can create yet. So "no socket", "connection refused" (a stale socket
//   file left by a daemon that died) and "connected but never answered" are all
//   NORMAL, and every one of them comes back as a clean 200 with
//   {running:false}. The panel on the phone says "nothing is floating over the
//   TV" and offers no dead controls. A 500 here would paint an error banner on
//   a state that is not an error.
//
// The timeout matters as much as the missing socket: a unix socket on the same
// box answers in microseconds, so a daemon that has not replied within a second
// is wedged, and an Express request must never be held hostage to it.
import net from 'node:net';
import express from 'express';
import { PIP_SOCKET } from './config.js';

// A unix socket to a local process. If this is not enough, the daemon is stuck.
export const REPLY_TIMEOUT_MS = 1000;

// Seams, same shape as screen.js's _setWindowsSeams: tests point the client at
// a stub daemon on a temp path. Called with nothing it restores the real ones.
let seams = { socketPath: PIP_SOCKET, timeoutMs: REPLY_TIMEOUT_MS };
export function _setPipSeams({ socketPath, timeoutMs } = {}) {
  seams = {
    socketPath: socketPath ?? PIP_SOCKET,
    timeoutMs: timeoutMs ?? REPLY_TIMEOUT_MS,
  };
}

// "There is no daemon to talk to", as distinct from "the daemon is broken".
// Only this one turns into {running:false}; anything else is a real fault and
// is allowed to surface as one.
export class PipDown extends Error {}

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
    else res.status(502).json({ error: String(err.message || err) });
  }
};

export const routes = express.Router();

// Never cached: this is a live reading of something that mostly does not exist.
routes.get('/', answer(async (req, res) => {
  res.set('cache-control', 'no-store');
  return status();
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

// "Stop" rather than "quit" on the wire the phone speaks: closing the picture
// is what the button does, and the daemon exiting is how it is done.
routes.post('/stop', answer(async () => send({ cmd: 'quit' })));
