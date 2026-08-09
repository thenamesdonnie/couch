// pip.js against stub daemons on temp sockets. The thing under test is not
// really the happy path - it is the four ways pipd fails to be there, because
// NOT RUNNING IS ITS NORMAL STATE (it only exists while a game is wrapped in
// gamescope with a video over it). Every one of those has to reach the phone as
// a calm 200 with running:false; a 500 would paint an error banner on a state
// that is not an error.
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
import { status, send, request, placeCommand, routes, _setPipSeams, PipDown } from './pip.js';

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
