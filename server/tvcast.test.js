// tvcast unit tests: the session picking, the stage machine, and the
// "only restore input for our own playback" rules. Everything the module
// touches (tv CLI, Jellyfin) is injected as fakes and time is a fake clock -
// no live calls, no real sleeps, no files. Run: npm test (node --test).
import test from 'node:test';
import assert from 'node:assert/strict';
import { createTvCast, pickWebosSession, foregroundApp } from './tvcast.js';

const ITEM = 'a'.repeat(32);
const WEBOS = {
  Id: 'full-session-id-1234567890abcdef',
  Client: 'Jellyfin for WebOS',
  SupportsRemoteControl: true,
  LastActivityDate: '2026-08-06T01:00:00Z',
};

// A harness around createTvCast: fake clock (sleep advances it), scripted tv
// and Jellyfin sides, and a log of every outbound call.
function rig(overrides = {}) {
  let t = 0;
  const calls = [];
  const state = {
    tvStatusReplies: null, // array consumed in order; last repeats
    sessionsReplies: null, // same
  };
  const next = (arr, fallback) => {
    if (!arr || !arr.length) return fallback;
    return arr.length > 1 ? arr.shift() : arr[0];
  };
  const cast = createTvCast({
    configured: () => true,
    tvStatus: async () => {
      calls.push('tvStatus');
      const v = next(state.tvStatusReplies, 'on (com.webos.app.hdmi2)');
      if (v instanceof Error) throw v;
      return v;
    },
    tvOn: async () => { calls.push('tvOn'); },
    tvInputPc: async () => { calls.push('hdmi1'); },
    tvApp: async () => { calls.push('tvApp'); },
    sessions: async () => {
      calls.push('sessions');
      const v = next(state.sessionsReplies, []);
      if (v instanceof Error) throw v;
      return v;
    },
    playOnSession: async (sid, id) => { calls.push(`play:${sid}:${id}`); },
    sessionCommand: async (sid, cmd) => { calls.push(`cmd:${sid}:${cmd}`); },
    seekSession: async (sid, secs) => { calls.push(`seek:${sid}:${secs}`); },
    resolveItem: async (id) => ({ id, name: 'Test Film' }),
    sleep: async (ms) => { t += ms; },
    now: () => t,
    log: () => {},
    ...overrides,
  });
  return { cast, calls, state, clock: { advance: (ms) => { t += ms; }, now: () => t } };
}

// start() fires run() without awaiting it; settle by letting the microtask
// queue drain until the stage machine stops moving (the fake sleep never
// yields to real timers, so this converges immediately).
async function settle(cast) {
  for (let i = 0; i < 200; i += 1) {
    const before = cast.status().seq;
    await Promise.resolve();
    await new Promise((r) => setImmediate(r));
    if (cast.status().seq === before && !['waking', 'launching', 'connecting'].includes(cast.status().stage)) return;
  }
  throw new Error(`never settled: ${JSON.stringify(cast.status())}`);
}

// --- session picking ---

test('pickWebosSession: only the webOS remote-controllable client counts', () => {
  assert.equal(pickWebosSession([]), null);
  assert.equal(pickWebosSession(null), null);
  assert.equal(pickWebosSession([{ Client: 'Kodi', SupportsRemoteControl: true, Id: 'x' }]), null);
  assert.equal(pickWebosSession([{ Client: 'Jellyfin for WebOS', SupportsRemoteControl: false, Id: 'x' }]), null);
  assert.equal(pickWebosSession([WEBOS]).Id, WEBOS.Id);
});

test('pickWebosSession: several app starts -> the most recent activity wins, full id kept', () => {
  const stale = { ...WEBOS, Id: 'older-session-id-000000000000000', LastActivityDate: '2026-08-06T00:00:00Z' };
  const picked = pickWebosSession([stale, WEBOS]);
  assert.equal(picked.Id, WEBOS.Id);
  assert.equal(picked.Id.length, WEBOS.Id.length); // the FULL id, never truncated
});

test('foregroundApp parses the tv status line', () => {
  assert.equal(foregroundApp('on (org.jellyfin.webos)'), 'org.jellyfin.webos');
  assert.equal(foregroundApp('on (com.webos.app.hdmi1)'), 'com.webos.app.hdmi1');
  assert.equal(foregroundApp('standby'), null);
  assert.equal(foregroundApp(''), null);
});

// --- stage machine ---

test('happy path: standby TV -> waking, launching, connecting, playing', async () => {
  const { cast, calls, state } = rig();
  state.tvStatusReplies = ['standby', 'standby', 'on (com.webos.app.hdmi2)'];
  state.sessionsReplies = [[], [], [WEBOS]];
  const r = cast.start(ITEM);
  assert.equal(r.ok, true);
  await settle(cast);
  const s = cast.status();
  assert.equal(s.stage, 'playing');
  assert.equal(s.item.name, 'Test Film');
  assert.ok(calls.includes('tvOn'));
  assert.ok(calls.includes('tvApp'));
  assert.ok(calls.includes(`play:${WEBOS.Id}:${ITEM}`));
  // the wake happened before the app launch, the app launch before the play
  assert.ok(calls.indexOf('tvOn') < calls.indexOf('tvApp'));
  assert.ok(calls.indexOf('tvApp') < calls.findIndex((c) => c.startsWith('play:')));
  assert.equal(cast.ownedPlayback().sessionId, WEBOS.Id);
});

test('TV already on: no wake command is sent', async () => {
  const { cast, calls, state } = rig();
  state.sessionsReplies = [[WEBOS]];
  cast.start(ITEM);
  await settle(cast);
  assert.equal(cast.status().stage, 'playing');
  assert.ok(!calls.includes('tvOn'));
});

test('wake timeout fails loudly at the waking stage', async () => {
  const { cast, state } = rig();
  state.tvStatusReplies = ['standby'];
  cast.start(ITEM);
  await settle(cast);
  const s = cast.status();
  assert.equal(s.stage, 'failed');
  assert.equal(s.failedStage, 'waking');
  assert.match(s.error, /did not wake/);
  assert.equal(cast.ownedPlayback(), null);
});

test('no session appearing fails at the connecting stage', async () => {
  const { cast, state } = rig();
  state.sessionsReplies = [[]];
  cast.start(ITEM);
  await settle(cast);
  const s = cast.status();
  assert.equal(s.stage, 'failed');
  assert.equal(s.failedStage, 'connecting');
  assert.match(s.error, /never checked in/);
});

test('a bad item fails before the TV is touched', async () => {
  const { cast, calls } = rig({
    resolveItem: async () => { throw new Error('jellyfin 404 on /Users/x/Items/y'); },
  });
  cast.start(ITEM);
  await settle(cast);
  const s = cast.status();
  assert.equal(s.stage, 'failed');
  assert.equal(s.failedStage, 'resolving');
  assert.ok(!calls.includes('tvOn'));
  assert.ok(!calls.includes('tvApp'));
});

test('refuses to start unconfigured (tv.json absent) and while mid-handoff', async () => {
  const bare = createTvCast({ configured: () => false });
  const r = bare.start(ITEM);
  assert.equal(r.ok, false);
  assert.equal(r.code, 503);
  assert.match(r.error, /not configured/);

  const { cast, state } = rig();
  state.tvStatusReplies = ['standby', 'standby', 'standby', 'on (x)'];
  state.sessionsReplies = [[WEBOS]];
  cast.start(ITEM);
  // The machine is inside the wake poll now (fake sleeps have not drained).
  const second = cast.start(ITEM);
  assert.equal(second.ok, false);
  assert.equal(second.code, 409);
  await settle(cast);
});

test('long-poll answers immediately on a stale seq and holds otherwise', async () => {
  const { cast } = rig();
  const s0 = cast.status();
  // stale seq: immediate
  assert.equal((await cast.waitForChange(s0.seq - 1, 5000)).seq, s0.seq);
  // current seq: resolves when the stage moves (start() bumps it)
  const held = cast.waitForChange(s0.seq, 5000);
  cast.start(ITEM);
  const after = await held;
  assert.ok(after.seq > s0.seq);
  await settle(cast);
});

// --- the input-restore monitor ---

async function playing(overrides = {}) {
  const r = rig(overrides);
  r.state.sessionsReplies = [[WEBOS]];
  r.cast.start(ITEM);
  await settle(r.cast);
  assert.equal(r.cast.status().stage, 'playing');
  r.calls.length = 0; // watch only what the monitor does from here
  return r;
}

const ourPlaying = { ...WEBOS, NowPlayingItem: { Id: ITEM }, PlayState: {} };
const idleSession = { ...WEBOS, NowPlayingItem: null };
const otherPlaying = { ...WEBOS, NowPlayingItem: { Id: 'b'.repeat(32) }, PlayState: {} };

test('monitor: still playing ours -> nothing happens', async () => {
  const { cast, calls, state } = await playing();
  state.sessionsReplies = [[ourPlaying]];
  await cast._monitorTick();
  assert.equal(cast.status().stage, 'playing');
  assert.ok(!calls.includes('hdmi1'));
  assert.ok(!calls.includes('tvStatus')); // no restore pending -> no tv polling
});

test('monitor: session idle past the dwell, Jellyfin app still foreground -> hdmi1 once', async () => {
  const { cast, calls, state, clock } = await playing();
  state.sessionsReplies = [[idleSession]];
  state.tvStatusReplies = ['on (org.jellyfin.webos)'];
  await cast._monitorTick(); // arms goneAt
  assert.ok(!calls.includes('hdmi1'));
  clock.advance(31000);
  await cast._monitorTick();
  assert.equal(calls.filter((c) => c === 'hdmi1').length, 1);
  assert.equal(cast.status().stage, 'idle');
  assert.equal(cast.ownedPlayback(), null);
  // and never again: nothing is owned any more
  await cast._monitorTick();
  assert.equal(calls.filter((c) => c === 'hdmi1').length, 1);
});

test('monitor: session vanished entirely counts the same as idle', async () => {
  const { cast, calls, state, clock } = await playing();
  state.sessionsReplies = [[]];
  state.tvStatusReplies = ['on (org.jellyfin.webos)'];
  await cast._monitorTick();
  clock.advance(31000);
  await cast._monitorTick();
  assert.ok(calls.includes('hdmi1'));
});

test('monitor: dwell not yet served -> input untouched', async () => {
  const { cast, calls, state, clock } = await playing();
  state.sessionsReplies = [[idleSession]];
  state.tvStatusReplies = ['on (org.jellyfin.webos)'];
  await cast._monitorTick();
  clock.advance(10000);
  await cast._monitorTick();
  assert.ok(!calls.includes('hdmi1'));
  assert.equal(cast.status().stage, 'playing');
});

test('monitor: playback resuming clears the pending restore', async () => {
  const { cast, calls, state, clock } = await playing();
  state.sessionsReplies = [[idleSession], [ourPlaying], [idleSession]];
  state.tvStatusReplies = ['on (org.jellyfin.webos)'];
  await cast._monitorTick(); // idle: arms
  clock.advance(29000);
  await cast._monitorTick(); // ours again: disarms
  clock.advance(5000);
  await cast._monitorTick(); // idle again: re-arms fresh, dwell restarts
  assert.ok(!calls.includes('hdmi1'));
});

test('monitor: Donnie started something else on the TV -> disown, input untouched', async () => {
  const { cast, calls, state, clock } = await playing();
  state.sessionsReplies = [[otherPlaying]];
  await cast._monitorTick();
  assert.equal(cast.ownedPlayback(), null);
  clock.advance(60000);
  await cast._monitorTick();
  assert.ok(!calls.includes('hdmi1'));
});

test('monitor: foreground left the Jellyfin app -> restore cancelled for good', async () => {
  const { cast, calls, state, clock } = await playing();
  state.sessionsReplies = [[idleSession]];
  state.tvStatusReplies = ['on (youtube.leanback.v4)'];
  await cast._monitorTick(); // arms
  clock.advance(31000);
  await cast._monitorTick(); // dwell served, but Donnie is in YouTube
  assert.ok(!calls.includes('hdmi1'));
  assert.equal(cast.ownedPlayback(), null); // disowned, never retried
});

test('monitor: TV in standby during the window -> never touch the input', async () => {
  const { cast, calls, state, clock } = await playing();
  state.sessionsReplies = [[idleSession]];
  state.tvStatusReplies = ['standby'];
  await cast._monitorTick();
  clock.advance(31000);
  await cast._monitorTick();
  assert.ok(!calls.includes('hdmi1'));
  assert.equal(cast.ownedPlayback(), null);
});

test('monitor: tv status unreadable -> hold position, keep ownership, retry later', async () => {
  const { cast, calls, state, clock } = await playing();
  state.sessionsReplies = [[idleSession]];
  state.tvStatusReplies = [new Error('no route to tv')];
  await cast._monitorTick();
  clock.advance(31000);
  await cast._monitorTick();
  assert.ok(!calls.includes('hdmi1'));
  assert.notEqual(cast.ownedPlayback(), null);
});

test('monitor: jellyfin unreachable -> touch nothing, decide nothing', async () => {
  const { cast, calls, state, clock } = await playing();
  state.sessionsReplies = [new Error('jellyfin down')];
  await cast._monitorTick();
  clock.advance(60000);
  await cast._monitorTick();
  assert.ok(!calls.includes('hdmi1'));
  assert.notEqual(cast.ownedPlayback(), null);
});

test('a new handoff cancels the pending restore', async () => {
  const { cast, calls, state, clock } = await playing();
  state.sessionsReplies = [[idleSession]];
  state.tvStatusReplies = ['on (org.jellyfin.webos)'];
  await cast._monitorTick(); // arms the restore
  clock.advance(31000);
  state.sessionsReplies = [[WEBOS]];
  cast.start(ITEM); // supersedes: ownership reset before any restore can land
  await settle(cast);
  assert.ok(!calls.includes('hdmi1'));
  assert.equal(cast.status().stage, 'playing');
});

// --- phone-as-remote over the owned session ---

test('stop routes to our session and shortens the restore dwell', async () => {
  const { cast, calls, state, clock } = await playing();
  await cast.stop();
  assert.ok(calls.includes(`cmd:${WEBOS.Id}:Stop`));
  state.sessionsReplies = [[idleSession]];
  state.tvStatusReplies = ['on (org.jellyfin.webos)'];
  await cast._monitorTick(); // arms
  clock.advance(6000); // > stopDwellMs (5s), well under the normal 30s
  await cast._monitorTick();
  assert.ok(calls.includes('hdmi1'));
});

test('playpause and seek drive the owned session; without one they refuse', async () => {
  const { cast, calls } = await playing();
  await cast.playpause();
  await cast.seek(432);
  assert.ok(calls.includes(`cmd:${WEBOS.Id}:PlayPause`));
  assert.ok(calls.includes(`seek:${WEBOS.Id}:432`));

  const bare = rig().cast;
  await assert.rejects(() => bare.stop(), /nothing playing/);
  await assert.rejects(() => bare.playpause(), /nothing playing/);
  await assert.rejects(() => bare.seek(10), /nothing playing/);
});

test('nowPlaying reports the owned session and goes inactive when it is not ours', async () => {
  const { cast, state } = await playing();
  state.sessionsReplies = [[{
    ...WEBOS,
    NowPlayingItem: { Id: ITEM, Name: 'Test Film', RunTimeTicks: 7200 * 10_000_000 },
    PlayState: { PositionTicks: 65 * 10_000_000, IsPaused: true },
  }]];
  const np = await cast.nowPlaying();
  assert.deepEqual(np, {
    active: true,
    item: { id: ITEM, name: 'Test Film' },
    position: 65,
    duration: 7200,
    paused: true,
  });
  state.sessionsReplies = [[otherPlaying]];
  assert.equal((await cast.nowPlaying()).active, false);
  const bare = rig().cast;
  assert.equal((await bare.nowPlaying()).active, false);
});
