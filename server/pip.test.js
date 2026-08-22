// pip.js against stub daemons on temp sockets. The thing under test is not
// really the happy path - it is the four ways pipd fails to be there, because
// NOT RUNNING IS ITS NORMAL STATE (it lives only as long as one picture). Every
// one of those has to reach the phone as a calm 200 with running:false; a 500
// would paint an error banner on a state that is not an error.
//
// The exception is /start, at the bottom: it is the one route that hands a path
// to a process that reads files and shows them on a television, and the phone
// is not authenticated. Most of its tests are about what it REFUSES.
//
// Every stub gets its own mkdtemp socket and is closed in the test that made
// it, so nothing is left listening in /tmp.
// Run: npm test (node --test), from server/.
import test from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import express from 'express';
import {
  status, send, request, placeCommand, routes, _setPipSeams, PipDown,
  resolveMedia, listEpisodes, PLAYER_ARGS,
} from './pip.js';

const STATUS_REPLY = {
  ok: true,
  output: { w: 3840, h: 2160 },
  pixels: { x: 2534, y: 108, w: 1152, h: 648 },
  normalised: { nx: 0.66, ny: 0.05, nw: 0.3, nh: 0.3 },
  visible: true,
  opacity: 1,
  player: 'mpv',
  playing: true,
  media: 'http://box/stream.mkv',
};

// A stand-in for pipd: JSON per line in, whatever `handler` returns out, then
// the connection closes - the real daemon's protocol exactly. `handler`
// returning undefined means "say nothing", which is the wedged-daemon case.
async function stubDaemon(handler) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'couch-pip-test-'));
  const socketPath = path.join(dir, 'pip.sock');
  const seen = [];
  const server = net.createServer((conn) => {
    conn.on('error', () => {}); // the client destroys its end first; not a fault
    conn.on('data', (chunk) => {
      const line = String(chunk).trim();
      seen.push(JSON.parse(line));
      const reply = handler(JSON.parse(line));
      if (reply === undefined) return;
      conn.end(typeof reply === 'string' ? reply : `${JSON.stringify(reply)}\n`);
    });
  });
  await new Promise((resolve) => server.listen(socketPath, resolve));
  return {
    socketPath,
    seen,
    async close() {
      await new Promise((resolve) => server.close(resolve));
      fs.rmSync(dir, { recursive: true, force: true });
    },
  };
}

// A path in a real temp dir with nothing listening on it.
function missingSocket() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'couch-pip-test-'));
  return {
    socketPath: path.join(dir, 'pip.sock'),
    close() { fs.rmSync(dir, { recursive: true, force: true }); },
  };
}

test('no socket at all is not an error - it is the normal state', async () => {
  const gone = missingSocket();
  try {
    const out = await status({ socketPath: gone.socketPath });
    assert.equal(out.running, false);
    assert.match(out.reason, /not answering/);
  } finally { gone.close(); }
});

test('a stale socket file nobody is listening on reads the same way', async () => {
  // What a daemon killed with -9 leaves behind: the file is there, connecting
  // to it is refused.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'couch-pip-test-'));
  const socketPath = path.join(dir, 'pip.sock');
  fs.writeFileSync(socketPath, '');
  try {
    const out = await status({ socketPath });
    assert.equal(out.running, false);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

test('a live daemon answers with its status, flagged running', async () => {
  const stub = await stubDaemon(() => STATUS_REPLY);
  try {
    const out = await status({ socketPath: stub.socketPath });
    assert.equal(out.running, true);
    assert.equal(out.ok, true);
    assert.deepEqual(out.normalised, STATUS_REPLY.normalised);
    assert.deepEqual(out.output, { w: 3840, h: 2160 });
    assert.deepEqual(stub.seen, [{ cmd: 'status' }]);
  } finally { await stub.close(); }
});

test('a refused command comes back as ok:false, still running', async () => {
  // pipd answers {"ok":false,"error":...} and stays up, so this is a state to
  // draw, not a fault to raise.
  const stub = await stubDaemon(() => ({ ok: false, error: "corner must be one of ['ne', 'nw', 'se', 'sw']" }));
  try {
    const out = await send({ cmd: 'corner', where: 'up' }, { socketPath: stub.socketPath });
    assert.equal(out.running, true);
    assert.equal(out.ok, false);
    assert.match(out.error, /corner must be one of/);
  } finally { await stub.close(); }
});

test('a daemon that accepts and never replies times out as not running', async () => {
  const stub = await stubDaemon(() => undefined); // connects, listens, says nothing
  try {
    const t0 = Date.now();
    const out = await status({ socketPath: stub.socketPath, timeoutMs: 80 });
    assert.equal(out.running, false);
    assert.match(out.reason, /did not answer/);
    // The point of the timeout: a wedged daemon cannot hold an Express request.
    assert.ok(Date.now() - t0 < 1000, `waited ${Date.now() - t0}ms`);
  } finally { await stub.close(); }
});

test('malformed JSON from the daemon is a real fault, not a quiet not-running', async () => {
  // Something IS listening and it is not pipd. Reporting that as "not running"
  // would hide a broken daemon behind a state that looks fine.
  const stub = await stubDaemon(() => 'this is not json\n');
  try {
    await assert.rejects(
      request({ cmd: 'status' }, { socketPath: stub.socketPath }),
      (err) => !(err instanceof PipDown) && /not JSON/.test(err.message),
    );
  } finally { await stub.close(); }
});

test('a daemon that closes without saying anything reads as not running', async () => {
  const stub = await stubDaemon(() => '');
  try {
    const out = await status({ socketPath: stub.socketPath });
    assert.equal(out.running, false);
  } finally { await stub.close(); }
});

// --- the command the phone's drag turns into ------------------------------

test('place keeps the coordinates it is given and snaps by default', () => {
  assert.deepEqual(placeCommand({ nx: 0.6, ny: 0.05, nw: 0.3 }),
    { cmd: 'place', snap: true, nx: 0.6, ny: 0.05, nw: 0.3 });
  // Mid-drag the phone sends snap:false so the box does not jump under the
  // finger; the release sends the authoritative snapping one.
  assert.equal(placeCommand({ nx: 0.6, ny: 0.05, snap: false }).snap, false);
});

test('place refuses coordinates that are not 0..1', () => {
  assert.throws(() => placeCommand({ nx: 1.4 }), RangeError);
  assert.throws(() => placeCommand({ nw: 'wide' }), RangeError);
  assert.throws(() => placeCommand({}), RangeError);
});

// --- the routes the phone actually calls ----------------------------------

async function testServer() {
  const app = express();
  app.use(express.json());
  app.use('/api/pip', routes);
  const server = app.listen(0);
  await new Promise((resolve) => server.once('listening', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  return {
    get: (p) => fetch(base + p),
    post: (p, body) => fetch(base + p, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    }),
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

test('GET /api/pip with no daemon is a 200, not a 500', async () => {
  const gone = missingSocket();
  _setPipSeams({ socketPath: gone.socketPath });
  const app = await testServer();
  try {
    const res = await app.get('/api/pip');
    assert.equal(res.status, 200);
    assert.deepEqual(Object.keys(await res.json()).sort(), ['reason', 'running']);
  } finally { await app.close(); gone.close(); _setPipSeams(); }
});

test('GET /api/pip passes a live status through', async () => {
  const stub = await stubDaemon(() => STATUS_REPLY);
  _setPipSeams({ socketPath: stub.socketPath });
  const app = await testServer();
  try {
    const body = await (await app.get('/api/pip')).json();
    assert.equal(body.running, true);
    assert.deepEqual(body.pixels, STATUS_REPLY.pixels);
  } finally { await app.close(); await stub.close(); _setPipSeams(); }
});

test('a drag POST reaches the daemon as a place command and answers the new status', async () => {
  const stub = await stubDaemon(() => STATUS_REPLY);
  _setPipSeams({ socketPath: stub.socketPath });
  const app = await testServer();
  try {
    const res = await app.post('/api/pip/place', { nx: 0.1, ny: 0.2, nw: 0.25 });
    assert.equal(res.status, 200);
    // The reply is the daemon's, NOT the request echoed back: pipd clamps and
    // snaps, so the phone's rectangle has to be reconciled to this.
    assert.deepEqual((await res.json()).normalised, STATUS_REPLY.normalised);
    assert.deepEqual(stub.seen, [{ cmd: 'place', snap: true, nx: 0.1, ny: 0.2, nw: 0.25 }]);
  } finally { await app.close(); await stub.close(); _setPipSeams(); }
});

test('every write route works with no daemon and none of them 500', async () => {
  const gone = missingSocket();
  _setPipSeams({ socketPath: gone.socketPath });
  const app = await testServer();
  try {
    const calls = [
      ['/api/pip/place', { nx: 0.5, ny: 0.5 }],
      ['/api/pip/corner', { where: 'se' }],
      ['/api/pip/scale', { factor: 1.25 }],
      ['/api/pip/opacity', { value: 0.8 }],
      ['/api/pip/show', {}],
      ['/api/pip/hide', {}],
      ['/api/pip/stop', {}],
    ];
    for (const [route, body] of calls) {
      const res = await app.post(route, body);
      assert.equal(res.status, 200, `${route} answered ${res.status}`);
      assert.equal((await res.json()).running, false, route);
    }
  } finally { await app.close(); gone.close(); _setPipSeams(); }
});

test('nonsense in a body is a 400 and never reaches the socket', async () => {
  const stub = await stubDaemon(() => STATUS_REPLY);
  _setPipSeams({ socketPath: stub.socketPath });
  const app = await testServer();
  try {
    assert.equal((await app.post('/api/pip/corner', { where: 'up' })).status, 400);
    assert.equal((await app.post('/api/pip/scale', { factor: 0 })).status, 400);
    assert.equal((await app.post('/api/pip/opacity', { value: 4 })).status, 400);
    assert.equal((await app.post('/api/pip/place', { nx: -1 })).status, 400);
    assert.deepEqual(stub.seen, []);
  } finally { await app.close(); await stub.close(); _setPipSeams(); }
});

// --- putting a picture up -------------------------------------------------
// The phone is not authenticated, so /start is the one route here that could
// do real harm: it hands a path to a process that reads files and puts them on
// a television. Most of what follows is about the paths it must REFUSE.

// A stand-in media library: a real directory with a real video file in it, so
// realpath and stat have something true to say.
function fakeLibrary() {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'couch-pip-media-')));
  fs.mkdirSync(path.join(root, 'tv', 'A Show', 'Season 5'), { recursive: true });
  const episode = path.join(root, 'tv', 'A Show', 'Season 5', 'A Show - S05E02.mkv');
  fs.writeFileSync(episode, 'not really a matroska');
  fs.writeFileSync(path.join(root, 'tv', 'A Show', 'Season 5', 'A Show - S05E02.srt'), '1\n');
  return { root, episode, close() { fs.rmSync(root, { recursive: true, force: true }); } };
}

// Records the spawn instead of performing it, and answers with something
// child-process shaped (on/unref) so the caller cannot tell.
function fakeSpawn(onCall = () => {}) {
  const calls = [];
  const fn = (cmd, args, opts) => {
    calls.push({ cmd, args, opts });
    onCall();
    return { pid: 4242, on() {}, unref() {} };
  };
  fn.calls = calls;
  return fn;
}

test('a path outside the media library is refused, whatever shape it arrives in', () => {
  const lib = fakeLibrary();
  _setPipSeams({ mediaRoot: lib.root });
  try {
    // Somewhere else entirely.
    assert.throws(() => resolveMedia('/etc/passwd'), RangeError);
    // Traversal that LOOKS like it is inside: refused lexically, before the
    // filesystem is consulted at all.
    assert.throws(() => resolveMedia(`${lib.root}/../../etc/passwd`), RangeError);
    assert.throws(() => resolveMedia(`${lib.root}/tv/../../etc/passwd`), RangeError);
    // A relative path resolves against the server's cwd, which is not the
    // library either.
    assert.throws(() => resolveMedia('index.js'), RangeError);
    // Empty and non-strings.
    assert.throws(() => resolveMedia(''), RangeError);
    assert.throws(() => resolveMedia(undefined), RangeError);
    assert.throws(() => resolveMedia(42), RangeError);
  } finally { _setPipSeams(); lib.close(); }
});

test('a symlink inside the library that points out of it is refused', () => {
  // The lexical check passes here - the path really is under the root - so
  // this is the case the second, post-realpath check exists for.
  const lib = fakeLibrary();
  const link = path.join(lib.root, 'escape.mkv');
  fs.symlinkSync('/etc/passwd', link);
  _setPipSeams({ mediaRoot: lib.root });
  try {
    assert.throws(() => resolveMedia(link), RangeError);
  } finally { _setPipSeams(); lib.close(); }
});

test('a path inside the library that is not a playable video is refused', () => {
  const lib = fakeLibrary();
  _setPipSeams({ mediaRoot: lib.root });
  try {
    // Missing.
    assert.throws(() => resolveMedia(path.join(lib.root, 'tv', 'nothing.mkv')),
      (err) => err instanceof RangeError && /no file there/.test(err.message));
    // A directory.
    assert.throws(() => resolveMedia(path.join(lib.root, 'tv')),
      (err) => err instanceof RangeError && /folder/.test(err.message));
    // The subtitle sitting next to the episode.
    assert.throws(() => resolveMedia(lib.episode.replace(/\.mkv$/, '.srt')),
      (err) => err instanceof RangeError && /not a video/.test(err.message));
    // ...and the one that is fine.
    assert.equal(resolveMedia(lib.episode), lib.episode);
  } finally { _setPipSeams(); lib.close(); }
});

test('POST /api/pip/start refuses a bad path with a 400 and never spawns anything', async () => {
  const lib = fakeLibrary();
  const gone = missingSocket();
  const spawn = fakeSpawn();
  _setPipSeams({ socketPath: gone.socketPath, mediaRoot: lib.root, spawn });
  const app = await testServer();
  try {
    for (const bad of [undefined, '', '/etc/passwd', `${lib.root}/../../etc/passwd`,
                       path.join(lib.root, 'tv'), lib.episode.replace(/\.mkv$/, '.srt')]) {
      const res = await app.post('/api/pip/start', { path: bad });
      assert.equal(res.status, 400, `${bad} answered ${res.status}`);
      assert.ok((await res.json()).error, 'a 400 must say why');
    }
    assert.deepEqual(spawn.calls, [], 'nothing may be spawned for a refused path');
  } finally { await app.close(); gone.close(); lib.close(); _setPipSeams(); }
});

test('POST /api/pip/start refuses with 409 while a picture is already up', async () => {
  // Two daemons on one socket path is a hole with no way out from the phone:
  // the second unlinks the first one's socket, and the first is then
  // unreachable AND unkillable from here.
  const lib = fakeLibrary();
  const stub = await stubDaemon(() => STATUS_REPLY);
  const spawn = fakeSpawn();
  _setPipSeams({ socketPath: stub.socketPath, mediaRoot: lib.root, spawn });
  const app = await testServer();
  try {
    const res = await app.post('/api/pip/start', { path: lib.episode });
    assert.equal(res.status, 409);
    const body = await res.json();
    assert.match(body.error, /already/);
    assert.equal(body.running, true);
    assert.deepEqual(spawn.calls, [], 'the running daemon must not be trampled');
    // Only the probe reached the socket; no start command was invented.
    assert.deepEqual(stub.seen, [{ cmd: 'status' }]);
  } finally { await app.close(); await stub.close(); lib.close(); _setPipSeams(); }
});

test('POST /api/pip/start spawns pipd detached and answers the new status', async () => {
  const lib = fakeLibrary();
  // The stub is silent until the spawn happens, so the route sees exactly what
  // it sees in life: nothing there, then a daemon.
  let up = false;
  const stub = await stubDaemon(() => (up ? STATUS_REPLY : undefined));
  const spawn = fakeSpawn(() => { up = true; });
  _setPipSeams({
    socketPath: stub.socketPath, mediaRoot: lib.root, spawn,
    display: ':9', pipd: '/opt/pipd', logPath: path.join(lib.root, 'pip.log'),
    timeoutMs: 80, pollMs: 10, startTimeoutMs: 2000,
    // Pin the bridge to nowhere: a live /tmp/game-gamescope on the box this
    // suite runs on must not leak into the assertion below.
    bridgePath: path.join(lib.root, 'no-bridge'),
  });
  const app = await testServer();
  try {
    const res = await app.post('/api/pip/start', { path: lib.episode });
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.running, true);
    assert.equal(body.started, lib.episode);

    assert.equal(spawn.calls.length, 1);
    const { cmd, args, opts } = spawn.calls[0];
    assert.equal(cmd, '/opt/pipd');
    assert.deepEqual(args, ['--display', ':9', '--socket', stub.socketPath,
                            '--player-args', PLAYER_ARGS, lib.episode]);
    // Detached, or the picture dies with the next couch.service restart.
    assert.equal(opts.detached, true);
    assert.equal(opts.env.DISPLAY, ':9');
    // Never our own stdio: an inherited pipe keeps the daemon tied to us.
    assert.notEqual(opts.stdio[1], 'inherit');
  } finally { await app.close(); await stub.close(); lib.close(); _setPipSeams(); }
});

test('a start under a live gamescope wrap targets the nested display, and garbage in the bridge does not', async () => {
  const lib = fakeLibrary();
  let up = false;
  const stub = await stubDaemon(() => (up ? STATUS_REPLY : undefined));
  const spawn = fakeSpawn(() => { up = true; });
  const bridge = path.join(lib.root, 'game-gamescope');
  fs.writeFileSync(bridge, ':1');
  _setPipSeams({
    socketPath: stub.socketPath, mediaRoot: lib.root, spawn,
    display: ':9', pipd: '/opt/pipd', logPath: path.join(lib.root, 'pip.log'),
    timeoutMs: 80, pollMs: 10, startTimeoutMs: 2000, bridgePath: bridge,
  });
  const app = await testServer();
  try {
    let res = await app.post('/api/pip/start', { path: lib.episode });
    assert.equal(res.status, 200);
    let { args, opts } = spawn.calls[0];
    assert.deepEqual(args.slice(0, 2), ['--display', ':1'],
      'the picture must land on the display that is presenting');
    assert.equal(opts.env.DISPLAY, ':1');

    // A corrupt bridge (a crashed wrap can leave anything) falls back to the
    // ordinary display rather than handing mpv a nonsense DISPLAY.
    up = false;
    fs.writeFileSync(bridge, 'not a display\n');
    res = await app.post('/api/pip/start', { path: lib.episode });
    assert.equal(res.status, 200);
    ({ args, opts } = spawn.calls[1]);
    assert.deepEqual(args.slice(0, 2), ['--display', ':9']);
    assert.equal(opts.env.DISPLAY, ':9');
  } finally { await app.close(); await stub.close(); lib.close(); _setPipSeams(); }
});

test('POST /api/pip/start reports a daemon that never comes up rather than claiming success', async () => {
  const lib = fakeLibrary();
  const gone = missingSocket();
  const spawn = fakeSpawn(); // spawns "successfully", binds nothing
  _setPipSeams({
    socketPath: gone.socketPath, mediaRoot: lib.root, spawn,
    logPath: path.join(lib.root, 'pip.log'), timeoutMs: 40, pollMs: 5, startTimeoutMs: 60,
  });
  const app = await testServer();
  try {
    const res = await app.post('/api/pip/start', { path: lib.episode });
    assert.equal(res.status, 502);
    assert.match((await res.json()).error, /did not come up/);
  } finally { await app.close(); gone.close(); lib.close(); _setPipSeams(); }
});

// --- the list the picker draws --------------------------------------------

test('episodes carry the local path Kodi does not know, in episode order', async () => {
  // Kodi's library here is fed by the jellyfin addon, so its `file` is a
  // plugin:// url with the Jellyfin id in it and no path at all.
  const asked = [];
  _setPipSeams({
    rpc: async () => ({
      episodes: [
        { episodeid: 2, title: 'Second', season: 5, episode: 2, runtime: 1374,
          file: 'plugin://plugin.video.jellyfin/abc/?filename=b.mkv&id=' + 'b'.repeat(32) + '&mode=play' },
        { episodeid: 1, title: 'First', season: 5, episode: 1, runtime: 1374,
          file: 'plugin://plugin.video.jellyfin/abc/?filename=a.mkv&id=' + 'a'.repeat(32) + '&mode=play' },
        { episodeid: 3, title: 'Unknown to jellyfin', season: 5, episode: 3, file: '' },
      ],
    }),
    pathsFor: async (ids) => {
      asked.push(...ids);
      return new Map([['a'.repeat(32), '/mnt/media/tv/A/a.mkv'], ['b'.repeat(32), '/mnt/media/tv/A/b.mkv']]);
    },
  });
  try {
    const eps = await listEpisodes(30, 5);
    assert.deepEqual(eps.map((e) => e.episode), [1, 2, 3], 'Kodi does not sort these');
    assert.deepEqual(eps.map((e) => e.path),
      ['/mnt/media/tv/A/a.mkv', '/mnt/media/tv/A/b.mkv', null]);
    assert.equal(asked.length, 2, 'one batched lookup, ids only');
  } finally { _setPipSeams(); }
});
