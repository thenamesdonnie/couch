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
