// screen.js unit tests: awaitGuardClaim, the pidfile poll that replaced the
// blind 700ms guard beat on the phone's desktop switch. Everything is
// injected - a mkdtemp pidfile and ms-scale knobs - so no live console state
// is read or written and the suite runs in well under a second.
// Run: npm test (node --test).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { awaitGuardClaim } from './screen.js';

function tmpPidfile() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'couch-screen-test-'));
  return path.join(dir, 'guard.pid');
}

test('resolves as soon as the guard stamps its pidfile', async () => {
  const pidfile = tmpPidfile();
  const since = Date.now();
  setTimeout(() => fs.writeFileSync(pidfile, '4242'), 30);
  const t0 = Date.now();
  const claimed = await awaitGuardClaim(since, { pidfile, capMs: 700, grainMs: 10 });
  assert.equal(claimed, true);
  // The whole point: nowhere near the 700ms cap once the claim lands.
  assert.ok(Date.now() - t0 < 500, `took ${Date.now() - t0}ms`);
});

test('gives up at the cap when no guard ever registers', async () => {
  const pidfile = tmpPidfile(); // never written
  const t0 = Date.now();
  const claimed = await awaitGuardClaim(Date.now(), { pidfile, capMs: 80, grainMs: 10 });
  assert.equal(claimed, false);
  // The cap IS the old fixed beat: on timeout the caller proceeds as before.
  assert.ok(Date.now() - t0 >= 80, `gave up after only ${Date.now() - t0}ms`);
});

test('a stale pidfile from an earlier guard does not count as the claim', async () => {
  const pidfile = tmpPidfile();
  fs.writeFileSync(pidfile, '1111'); // an older guard's leftover
  const { mtimeMs } = fs.statSync(pidfile);
  const claimed = await awaitGuardClaim(mtimeMs + 5, { pidfile, capMs: 60, grainMs: 10 });
  assert.equal(claimed, false);
});

test('a stale pidfile re-stamped by the new guard counts', async () => {
  const pidfile = tmpPidfile();
  fs.writeFileSync(pidfile, '1111');
  const since = fs.statSync(pidfile).mtimeMs + 5;
  // The new guard supersedes: same path, fresh write (supersede() rewrites).
  setTimeout(() => fs.writeFileSync(pidfile, '2222'), 30);
  const claimed = await awaitGuardClaim(since, { pidfile, capMs: 700, grainMs: 10 });
  assert.equal(claimed, true);
});

// --- the window list memo (perf audit, 8 Aug 2026) -------------------------
// Building the list costs a python3 spawn and an X walk: measured 215ms end
// to end on this box for a 523-byte answer. That sits in front of the
// switcher sheet, which is a gesture, so it is felt. One in-flight walk at a
// time plus a 600ms memory takes the burst - the switcher and the phone both
// ask two or three times while a sheet opens - without letting the list go
// stale enough for a human to catch it.
import {
  windows, invalidateWindows, _setWindowsSeams, WINDOWS_TTL_MS,
} from './screen.js';

function windowsRig() {
  let t = 0;
  let builds = 0;
  let release;
  const rig = {
    calls: () => builds,
    tick: (ms) => { t += ms; },
    // Resolve the pending build by hand, so the single-flight window is a
    // real window and not a scheduling accident. windows() starts the build
    // on a microtask, so yield until it has actually begun before releasing
    // it - otherwise the test races the implementation it is describing.
    finish: async () => {
      for (let i = 0; i < 50 && !release; i += 1) await Promise.resolve();
      if (!release) throw new Error('the build never started');
      release();
      release = null;
    },
  };
  _setWindowsSeams({
    now: () => t,
    build: () => {
      builds += 1;
      const n = builds;
      return new Promise((res) => { release = () => res([{ id: `w${n}` }]); });
    },
  });
  return rig;
}

test('a second ask inside the window reuses the first walk', async () => {
  const rig = windowsRig();
  const a = windows();
  await rig.finish();
  assert.deepEqual(await a, [{ id: 'w1' }]);
  const b = await windows();
  assert.deepEqual(b, [{ id: 'w1' }]);
  assert.equal(rig.calls(), 1, 'the X walk ran twice for one answer');
  _setWindowsSeams();
});

test('concurrent asks share ONE walk - the switcher and the phone collide', async () => {
  const rig = windowsRig();
  const all = Promise.all([windows(), windows(), windows()]);
  await rig.finish();
  const [x, y, z] = await all;
  assert.equal(rig.calls(), 1);
  assert.deepEqual(x, y);
  assert.deepEqual(y, z);
  _setWindowsSeams();
});

test('past the window it walks again - a stale list is the thing to avoid', async () => {
  const rig = windowsRig();
  const first = windows(); await rig.finish(); await first;
  rig.tick(WINDOWS_TTL_MS + 1);
  const second = windows(); await rig.finish();
  assert.deepEqual(await second, [{ id: 'w2' }]);
  assert.equal(rig.calls(), 2);
  _setWindowsSeams();
});

test('acting on a window drops the memo, so the redraw is the truth', async () => {
  const rig = windowsRig();
  const first = windows(); await rig.finish(); await first;
  invalidateWindows();                      // what activateWindow() does
  const second = windows(); await rig.finish();
  assert.deepEqual(await second, [{ id: 'w2' }]);
  assert.equal(rig.calls(), 2);
  _setWindowsSeams();
});

test('a failed walk is not remembered as an answer', async () => {
  // A transient X error must not pin an empty switcher for the next 600ms.
  let calls = 0;
  _setWindowsSeams({
    now: () => 0,
    build: () => { calls += 1; return calls === 1 ? Promise.reject(new Error('no X')) : Promise.resolve([{ id: 'ok' }]); },
  });
  await assert.rejects(windows());
  assert.deepEqual(await windows(), [{ id: 'ok' }]);
  assert.equal(calls, 2);
  _setWindowsSeams();
});
