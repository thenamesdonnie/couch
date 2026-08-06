// tvcast unit tests: the session picking, the stage machine, and the
// "only restore input for our own playback" rules. Everything the module
// touches (tv CLI, Jellyfin) is injected as fakes and time is a fake clock -
// no live calls, no real sleeps, no files. Run: npm test (node --test).
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  createTvCast, createHdrRouter, hdrVerdict, pickWebosSession, foregroundApp,
} from './tvcast.js';
import { createTvLights, restorableTemp, restoreLevel } from './tvlights.js';

const ITEM = 'a'.repeat(32);
const WEBOS = {
  Id: 'full-session-id-1234567890abcdef',
  Client: 'Jellyfin for WebOS',
  SupportsRemoteControl: true,
  LastActivityDate: '2026-08-06T01:00:00Z',
};

// Stand-in for the lights driver: records only the TRANSITIONS, the same way
// the real one only shells `lights` when the state actually changes, so tests
// can assert "the room came back up once".
function fakeLights(calls) {
  let dimmed = false;
  return {
    set: (target) => {
      if (target === 'dim' && !dimmed) { dimmed = true; calls.push('lights:dim'); }
      if (target === 'restore' && dimmed) { dimmed = false; calls.push('lights:restore'); }
      return Promise.resolve();
    },
    state: () => ({ dimmed }),
    settled: () => Promise.resolve(),
  };
}

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
    lights: fakeLights(calls),
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

// --- HDR auto-routing: is this item one for the TV? ---

const profile = (over = {}) => ({
  id: ITEM, type: 'Movie', name: 'Test Film',
  videoRange: 'SDR', videoRangeType: 'SDR', codec: 'h264', bitDepth: 8, width: 1920,
  ...over,
});

test('hdrVerdict: every HDR flavour the TV should take', () => {
  for (const t of ['HDR10', 'HDR10Plus', 'DOVI', 'HLG']) {
    const v = hdrVerdict(profile({ videoRange: 'HDR', videoRangeType: t }));
    assert.equal(v.hdr, true, t);
    assert.equal(v.label, t);
  }
  // Dolby Vision is the one Donnie cares most about; spelled out both ways.
  assert.equal(hdrVerdict(profile({ videoRange: 'HDR', videoRangeType: 'DolbyVision' })).hdr, true);
  // VideoRange alone (older files carry no VideoRangeType) still counts.
  assert.equal(hdrVerdict(profile({ videoRange: 'HDR', videoRangeType: null })).hdr, true);
});

test('hdrVerdict: SDR and anything unknown stay in Kodi', () => {
  assert.equal(hdrVerdict(profile()).hdr, false);
  assert.equal(hdrVerdict(profile()).label, 'SDR');
  // No video stream at all, a field we have never seen, nothing at all: all
  // false. Never route on a guess.
  for (const p of [profile({ videoRange: null, videoRangeType: null }),
    profile({ videoRange: 'WHO KNOWS', videoRangeType: 'MYSTERY' }), null]) {
    const v = hdrVerdict(p);
    assert.equal(v.hdr, false);
    assert.equal(v.label, 'unknown');
  }
});

function router(over = {}) {
  const asked = [];
  const r = createHdrRouter({
    profileFor: async (id) => { asked.push(id); return profile({ videoRange: 'HDR', videoRangeType: 'HDR10' }); },
    log: () => {},
    now: () => 0,
    ...over,
  });
  return { r, asked };
}

test('shouldRoute: an HDR film routes, an SDR film does not', async () => {
  const { r } = router();
  const yes = await r.shouldRoute(ITEM);
  assert.equal(yes.route, true);
  assert.match(yes.reason, /HDR10/);
  assert.equal(yes.videoRangeType, 'HDR10');

  const { r: r2 } = router({ profileFor: async () => profile() });
  const no = await r2.shouldRoute(ITEM);
  assert.equal(no.route, false);
  assert.match(no.reason, /Kodi plays it/);
});

test('shouldRoute: junk ids never route and never reach jellyfin', async () => {
  const { r, asked } = router();
  for (const bad of ['', null, undefined, 'not-an-id', ITEM.slice(1), `${ITEM}a`, '../../etc']) {
    const a = await r.shouldRoute(bad);
    assert.equal(a.route, false);
    assert.match(a.reason, /not a jellyfin item id/);
  }
  assert.deepEqual(asked, []);
});

test('shouldRoute: jellyfin unreadable answers an honest false', async () => {
  const { r } = router({ profileFor: async () => { throw new Error('jellyfin 500'); } });
  const a = await r.shouldRoute(ITEM);
  assert.equal(a.route, false);
  assert.match(a.reason, /could not read/);
});

test('shouldRoute: containers and non-video types never route', async () => {
  for (const type of ['Series', 'Season', 'MusicVideo', 'BoxSet']) {
    const { r } = router({
      profileFor: async () => profile({ type, videoRange: 'HDR', videoRangeType: 'HDR10' }),
    });
    const a = await r.shouldRoute(ITEM);
    assert.equal(a.route, false, type);
    assert.match(a.reason, /not a film or episode/);
  }
  // ...but an HDR episode is exactly as routable as an HDR film.
  const { r } = router({
    profileFor: async () => profile({ type: 'Episode', videoRange: 'HDR', videoRangeType: 'DOVI' }),
  });
  assert.equal((await r.shouldRoute(ITEM)).route, true);
});

test('shouldRoute: the kill switch beats the file', async () => {
  const { r, asked } = router({ enabled: () => false });
  const a = await r.shouldRoute(ITEM);
  assert.equal(a.route, false);
  assert.equal(a.enabled, false);
  assert.match(a.reason, /switched off/);
  assert.deepEqual(asked, []); // and costs Jellyfin nothing
});

test('shouldRoute: a live game or a busy TV stops the interception', async () => {
  const live = router({ gameLive: () => true });
  assert.match((await live.r.shouldRoute(ITEM)).reason, /game session/);
  assert.deepEqual(live.asked, []);
  const busy = router({ tvBusy: () => true });
  assert.match((await busy.r.shouldRoute(ITEM)).reason, /already playing/);
  assert.deepEqual(busy.asked, []);
});

test('shouldRoute: an explicit "play it in Kodi" is not overruled', async () => {
  // The phone's Play button and its Play on TV button sit on the same card.
  // Pressing the first one has to mean the first one.
  let t = 0;
  const { r, asked } = router({ now: () => t });
  r.suppress();
  const a = await r.shouldRoute(ITEM);
  assert.equal(a.route, false);
  assert.match(a.reason, /asked for in Kodi/);
  assert.deepEqual(asked, []);
  t += 21 * 1000; // the window is only as long as a playback takes to start
  assert.equal((await r.shouldRoute(ITEM)).route, true);
});

test('shouldRoute: answers are cached briefly, failures far more briefly', async () => {
  let t = 0;
  const { r, asked } = router({ now: () => t });
  await r.shouldRoute(ITEM);
  await r.shouldRoute(ITEM);
  assert.equal(asked.length, 1); // a re-click costs nothing
  t += 6 * 60 * 1000;
  await r.shouldRoute(ITEM);
  assert.equal(asked.length, 2); // ...but the cache does expire

  t = 0;
  let fail = true;
  const tries = [];
  const r2 = createHdrRouter({
    now: () => t,
    log: () => {},
    profileFor: async () => {
      tries.push(t);
      if (fail) throw new Error('jellyfin down');
      return profile({ videoRange: 'HDR', videoRangeType: 'HDR10' });
    },
  });
  assert.equal((await r2.shouldRoute(ITEM)).route, false);
  await r2.shouldRoute(ITEM);
  assert.equal(tries.length, 1); // a blip is not re-asked on every tick
  t += 25 * 1000;
  fail = false;
  assert.equal((await r2.shouldRoute(ITEM)).route, true); // ...and heals fast
});

test('shouldRoute: the cache cannot grow without bound', async () => {
  const r = createHdrRouter({
    profileFor: async () => profile(), log: () => {}, now: () => 0, maxEntries: 5,
  });
  for (let i = 0; i < 20; i += 1) {
    await r.shouldRoute(i.toString(16).padStart(32, '0'));
  }
  assert.ok(r._cacheSize() <= 5);
});

// --- cinema lights on the TV path ---

const STATUS = (lines) => lines.join('\n');
const BULB = (ip, on, dim, mode) => `${ip}  ${on ? 'on' : 'off'}  ${dim}%  ${mode}  (rssi -55)`;

function lightRig(script = {}) {
  const calls = [];
  const lights = createTvLights({
    log: () => {},
    run: async (cmd, arg) => {
      calls.push(arg === undefined ? cmd : `${cmd}:${arg}`);
      if (script[cmd] instanceof Error) throw script[cmd];
      if (cmd === 'status') return script.status ?? STATUS([BULB('10.0.0.1', true, 80, '2700K')]);
      return 'ok';
    },
  });
  return { lights, calls };
}

test('lights: a lit warm room dims to 10 and comes back to where it was', async () => {
  const { lights, calls } = lightRig();
  await lights.set('dim');
  assert.deepEqual(calls, ['status', 'warm', 'dim:10']);
  assert.equal(lights.state().dimmed, true);
  calls.length = 0;
  await lights.set('restore');
  assert.deepEqual(calls, ['warm', 'on:80']);
  assert.equal(lights.state().dimmed, false);
});

test('lights: a dark room stays dark', async () => {
  const { lights, calls } = lightRig({
    status: STATUS([BULB('10.0.0.1', false, 80, '2700K'), BULB('10.0.0.2', false, 50, '2700K')]),
  });
  await lights.set('dim');
  assert.deepEqual(calls, ['status']); // looked, touched nothing
  assert.equal(lights.state().dimmed, false);
  calls.length = 0;
  await lights.set('restore'); // and never "restores" a room it did not dim
  assert.deepEqual(calls, []);
});

test('lights: a colour the CLI cannot put back means brightness only', async () => {
  for (const mode of ['scene 6', 'rgb', '4000K']) {
    const { lights, calls } = lightRig({ status: STATUS([BULB('10.0.0.1', true, 65, mode)]) });
    await lights.set('dim');
    assert.deepEqual(calls, ['status', 'dim:10'], mode); // no warm: it is not reversible
    calls.length = 0;
    await lights.set('restore');
    assert.deepEqual(calls, ['on:65'], mode);
  }
});

test('lights: bulbs disagreeing on colour are left on their colours', async () => {
  const { lights, calls } = lightRig({
    status: STATUS([BULB('10.0.0.1', true, 40, '2700K'), BULB('10.0.0.2', true, 90, '5000K')]),
  });
  await lights.set('dim');
  assert.deepEqual(calls, ['status', 'dim:10']);
  calls.length = 0;
  await lights.set('restore');
  assert.deepEqual(calls, ['on:90']); // the brightest wins: never leave the room darker
});

test('lights: a cool room dims and returns cool', async () => {
  const { lights, calls } = lightRig({ status: STATUS([BULB('10.0.0.1', true, 100, '5000K')]) });
  await lights.set('dim');
  assert.deepEqual(calls, ['status', 'warm', 'dim:10']);
  calls.length = 0;
  await lights.set('restore');
  assert.deepEqual(calls, ['cool', 'on:100']);
});

test('lights: helpers agree with the transitions', () => {
  assert.equal(restorableTemp([{ on: true, mode: '2700K' }]), 'warm');
  assert.equal(restorableTemp([{ on: true, mode: '5000K' }]), 'cool');
  assert.equal(restorableTemp([{ on: true, mode: 'scene 6' }]), null);
  assert.equal(restorableTemp([]), null);
  assert.equal(restoreLevel([{ on: true, dimming: 20 }, { on: true, dimming: 70 }]), 70);
  assert.equal(restoreLevel([]), 100); // knowing nothing, come back bright
});

test('lights: no bulbs answering is a shrug, not a failure', async () => {
  const { lights, calls } = lightRig({ status: 'no bulbs answered' });
  await lights.set('dim');
  assert.deepEqual(calls, ['status']);
  assert.equal(lights.state().dimmed, false);
});

test('lights: an unreachable CLI never throws and never claims a dim', async () => {
  const { lights, calls } = lightRig({ status: new Error('ENOENT lights') });
  await lights.set('dim');
  assert.deepEqual(calls, ['status']);
  assert.equal(lights.state().dimmed, false);

  const dead = lightRig({ warm: new Error('no reply'), dim: new Error('no reply') });
  await dead.lights.set('dim');
  assert.equal(dead.lights.state().dimmed, false); // nothing landed: nothing to undo
  dead.calls.length = 0;
  await dead.lights.set('restore');
  assert.deepEqual(dead.calls, []);
});

test('lights: a half-failed dim is still a dim, and a failed restore is not retried', async () => {
  const half = lightRig({ warm: new Error('no reply') });
  await half.lights.set('dim');
  assert.equal(half.lights.state().dimmed, true); // brightness did land
  const broken = lightRig({ on: new Error('no reply') });
  await broken.lights.set('dim');
  await broken.lights.set('restore');
  assert.equal(broken.lights.state().dimmed, false);
  broken.calls.length = 0;
  await broken.lights.set('restore');
  assert.deepEqual(broken.calls, []); // never a retry storm against dead bulbs
});

test('lights: repeats are free and overlapping asks settle on the last one', async () => {
  const { lights, calls } = lightRig();
  await lights.set('dim');
  await lights.set('dim');
  assert.deepEqual(calls, ['status', 'warm', 'dim:10']);
  calls.length = 0;
  // Fired without awaiting, the way the monitor does it.
  lights.set('restore');
  lights.set('dim');
  lights.set('restore');
  await lights.settled();
  assert.equal(lights.state().dimmed, false);
  assert.ok(calls.length > 0);
});

// --- the lights as the monitor drives them ---

const pausedSession = { ...WEBOS, NowPlayingItem: { Id: ITEM }, PlayState: { IsPaused: true } };

test('lights: playing on the TV dims the room', async () => {
  const { cast, calls, state } = rig();
  state.sessionsReplies = [[WEBOS]];
  cast.start(ITEM);
  await settle(cast);
  assert.ok(calls.includes('lights:dim'));
  assert.equal(cast.lightsState().dimmed, true);
});

test('lights: pause brings them up, resume takes them down again', async () => {
  const { cast, calls, state } = await playing();
  state.sessionsReplies = [[pausedSession]];
  await cast._monitorTick();
  assert.deepEqual(calls.filter((c) => c.startsWith('lights')), ['lights:restore']);
  state.sessionsReplies = [[ourPlaying]];
  await cast._monitorTick();
  assert.deepEqual(calls.filter((c) => c.startsWith('lights')), ['lights:restore', 'lights:dim']);
  // and a second unpaused tick is not a second dim
  await cast._monitorTick();
  assert.equal(calls.filter((c) => c === 'lights:dim').length, 1);
});

test('lights: the film ending brings them up at once, not after the input dwell', async () => {
  const { cast, calls, state } = await playing();
  state.sessionsReplies = [[idleSession]];
  state.tvStatusReplies = ['on (org.jellyfin.webos)'];
  await cast._monitorTick(); // only arms the input restore...
  assert.ok(!calls.includes('hdmi1'));
  assert.ok(calls.includes('lights:restore')); // ...but the room is already back
});

test('lights: every way out of ownership restores them', async () => {
  // Donnie started something else on the TV himself
  const a = await playing();
  a.state.sessionsReplies = [[otherPlaying]];
  await a.cast._monitorTick();
  assert.ok(a.calls.includes('lights:restore'));

  // he walked off to another app
  const b = await playing();
  b.state.sessionsReplies = [[idleSession]];
  b.state.tvStatusReplies = ['on (youtube.leanback.v4)'];
  await b.cast._monitorTick();
  b.clock.advance(31000);
  await b.cast._monitorTick();
  assert.equal(b.cast.lightsState().dimmed, false);

  // the normal end: dwell served, input handed back
  const c = await playing();
  c.state.sessionsReplies = [[idleSession]];
  c.state.tvStatusReplies = ['on (org.jellyfin.webos)'];
  await c.cast._monitorTick();
  c.clock.advance(31000);
  await c.cast._monitorTick();
  assert.ok(c.calls.includes('hdmi1'));
  assert.equal(c.cast.lightsState().dimmed, false);
});

test('lights: a handoff that fails after a dim does not leave the room dark', async () => {
  const { cast, calls, state } = await playing();
  assert.equal(cast.lightsState().dimmed, true);
  state.sessionsReplies = [[]]; // the app never checks in this time
  cast.start(ITEM);
  await settle(cast);
  assert.equal(cast.status().stage, 'failed');
  assert.equal(cast.lightsState().dimmed, false);
  assert.ok(calls.includes('lights:restore'));
});

test('lights: jellyfin going dark keeps ownership but not the dim forever', async () => {
  const { cast, calls, state, clock } = await playing();
  state.sessionsReplies = [new Error('jellyfin down')];
  await cast._monitorTick();
  clock.advance(60 * 1000);
  await cast._monitorTick();
  assert.equal(cast.lightsState().dimmed, true); // a minute of blindness is nothing
  clock.advance(15 * 60 * 1000);
  await cast._monitorTick();
  assert.ok(calls.includes('lights:restore'));
  assert.notEqual(cast.ownedPlayback(), null); // the TV is still ours; only the room came back
});
