// Play on the LG's NATIVE Jellyfin app (org.jellyfin.webos). The PC path
// tonemaps HDR down to SDR; handing the file to the TV's own app is the only
// route to real 4K HDR / Dolby Vision. The chain (verified live, 6 Aug 2026):
// wake the TV if needed (SSAP times out in standby, so wake MUST come first),
// launch the app, wait for it to register a Jellyfin session (~8-15s cold,
// fresh session id every app start), then PlayNow that session.
//
// The whole orchestration lives behind injected deps so tests drive it with
// fakes and a fake clock - no live TV, no live Jellyfin, no real sleeps.
//
// Stages the phone sees: idle -> waking -> launching -> connecting -> playing,
// or failed (with which stage died). seq bumps on every change so the status
// route can long-poll.
import * as sys from './sys.js';
import * as jellyfin from './jellyfin.js';
import { createTvLights } from './tvlights.js';

// The webOS app's session, out of everything Jellyfin has seen lately. Ids
// rotate per app start, so callers must take the FULL id from this fresh
// answer - a truncated or remembered id 404s (both happened on the live run).
export function pickWebosSession(sessions) {
  const fit = (sessions || []).filter(
    (s) => s && s.Client === 'Jellyfin for WebOS' && s.SupportsRemoteControl && s.Id,
  );
  if (!fit.length) return null;
  // Several entries can linger (old app starts inside activeWithinSeconds);
  // the newest activity is the live one.
  fit.sort((a, b) => String(a.LastActivityDate || '').localeCompare(String(b.LastActivityDate || '')));
  return fit[fit.length - 1];
}

// "on (org.jellyfin.webos)" -> "org.jellyfin.webos"; "standby" -> null.
export function foregroundApp(tvStatusText) {
  const m = /^on\b.*\(([^)]+)\)/.exec(String(tvStatusText || '').trim());
  return m ? m[1] : null;
}

const JELLYFIN_APP = 'org.jellyfin.webos';

class StageFail extends Error {
  constructor(stage, message) {
    super(message);
    this.stage = stage;
  }
}

const DEFAULTS = {
  configured: () => sys.tvConfigured(),
  tvStatus: () => sys.tv('status'),
  tvOn: () => sys.tv('on'),
  tvInputPc: () => sys.tv('hdmi1'),
  tvApp: () => sys.tvJellyfinApp(),
  sessions: () => jellyfin.activeSessions(),
  playOnSession: (sid, itemId) => jellyfin.playOnSession(sid, itemId),
  sessionCommand: (sid, cmd) => jellyfin.sessionCommand(sid, cmd),
  seekSession: (sid, secs) => jellyfin.seekSession(sid, secs),
  resolveItem: (id) => jellyfin.playableFor(id),
  sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
  now: () => Date.now(),
  log: (...a) => console.error('[tvcast]', ...a),
  // Caps from the live timings: wake ~6.5s, app-to-session ~8-15s.
  wakeTimeoutMs: 20000,
  wakePollMs: 1500,
  sessionTimeoutMs: 30000,
  sessionPollMs: 2000,
  monitorPollMs: 5000,
  // Cinema lights, driven off the same session poll (see tvlights.js).
  lights: undefined,
  // If Jellyfin has not confirmed OUR item playing for this long while we are
  // holding a dim, put the lights back. Covers "the poller went blind" (a
  // Jellyfin outage mid-film): ownership is deliberately sticky there, but a
  // dark room must not be.
  lightsBlindMs: 15 * 60 * 1000,
  // How long a vanished/idle session must stay that way before the TV goes
  // back to the PC input; a phone-pressed Stop shortens it (that press IS the
  // "I'm done" signal).
  goneDwellMs: 30000,
  stopDwellMs: 5000,
};

export function createTvCast(overrides = {}) {
  const d = { ...DEFAULTS, ...overrides };
  // One lights driver per cast, built lazily so importing this module never
  // touches the bulbs and tests can inject a fake.
  const lights = d.lights ?? createTvLights();

  let stage = 'idle';
  let seq = 0;
  let error = null;
  let failedStage = null;
  let item = null; // { id, name } in flight or playing
  let waiters = [];

  // The playback WE started: session + item, so the input restore can never
  // yank the TV away from something Donnie started himself on the TV.
  let owned = null; // { sessionId, itemId, goneAt, stopRequested }
  let monitorTimer = null;
  let runToken = 0;

  const status = () => ({ stage, seq, error, failedStage, item });
  const busy = () => stage === 'waking' || stage === 'launching' || stage === 'connecting';

  function setStage(next, extra = {}) {
    stage = next;
    error = extra.error ?? null;
    failedStage = extra.failedStage ?? null;
    if ('item' in extra) item = extra.item;
    seq += 1;
    const w = waiters;
    waiters = [];
    for (const resolve of w) resolve();
  }

  // Long-poll: answer immediately if the client's seq is already stale,
  // otherwise hold until the next change or the timeout.
  function waitForChange(knownSeq, timeoutMs = 25000) {
    if (!Number.isFinite(knownSeq) || knownSeq !== seq) return Promise.resolve(status());
    return new Promise((resolve) => {
      let timer = null;
      const done = () => {
        clearTimeout(timer);
        resolve(status());
      };
      timer = setTimeout(() => {
        waiters = waiters.filter((w) => w !== done);
        done();
      }, timeoutMs);
      timer.unref?.();
      waiters.push(done);
    });
  }

  function start(itemId) {
    if (!d.configured()) {
      return { ok: false, code: 503, error: 'TV control is not configured on the box (tv.json missing)' };
    }
    if (busy()) {
      return { ok: false, code: 409, error: 'already handing a playback to the TV, give it a moment' };
    }
    // A fresh handoff supersedes any tracked playback AND any pending input
    // restore - restoring hdmi1 mid-launch would yank the TV out from under
    // the very thing we are starting.
    owned = null;
    stopMonitor();
    const token = ++runToken;
    run(itemId, token).catch((e) => d.log('unhandled:', e));
    return { ok: true };
  }

  async function run(itemId, token) {
    const dead = () => token !== runToken;
    try {
      setStage('waking', { item: null });
      // Resolve first: a bad id must fail before the TV is touched. For a
      // series this also picks the next-up episode.
      const target = await d.resolveItem(itemId).catch((e) => {
        throw new StageFail('resolving', `could not resolve the item: ${e.message}`);
      });
      if (dead()) return;
      setStage('waking', { item: target });

      let st = await d.tvStatus().catch((e) => {
        throw new StageFail('waking', `tv status failed: ${e.message}`);
      });
      if (!/^on\b/.test(st)) {
        await d.tvOn().catch((e) => {
          throw new StageFail('waking', `could not wake the TV: ${e.message}`);
        });
        const deadline = d.now() + d.wakeTimeoutMs;
        while (!/^on\b/.test(st)) {
          if (d.now() >= deadline) {
            throw new StageFail('waking', `the TV did not wake within ${Math.round(d.wakeTimeoutMs / 1000)}s`);
          }
          await d.sleep(d.wakePollMs);
          if (dead()) return;
          st = await d.tvStatus().catch(() => '');
        }
      }
      if (dead()) return;

      setStage('launching');
      await d.tvApp().catch((e) => {
        throw new StageFail('launching', `could not open the Jellyfin app on the TV: ${e.message}`);
      });
      if (dead()) return;

      setStage('connecting');
      const deadline = d.now() + d.sessionTimeoutMs;
      let session = null;
      for (;;) {
        const list = await d.sessions().catch(() => null);
        session = list ? pickWebosSession(list) : null;
        if (session) break;
        if (d.now() >= deadline) {
          throw new StageFail('connecting', `the TV app never checked in with Jellyfin (${Math.round(d.sessionTimeoutMs / 1000)}s)`);
        }
        await d.sleep(d.sessionPollMs);
        if (dead()) return;
      }
      if (dead()) return;

      await d.playOnSession(session.Id, target.id).catch((e) => {
        throw new StageFail('playing', `Jellyfin refused the play command: ${e.message}`);
      });
      if (dead()) return;

      owned = {
        sessionId: session.Id,
        itemId: target.id,
        goneAt: null,
        stopRequested: false,
        // Last tick that saw Jellyfin actually playing our item; the lights
        // blind-timer counts from here.
        seenAt: d.now(),
      };
      startMonitor();
      setStage('playing', { item: target });
      lights.set('dim');
    } catch (e) {
      if (dead()) return;
      const at = e instanceof StageFail ? e.stage : stage;
      d.log(`failed while ${at}:`, e.message);
      setStage('failed', { error: e.message, failedStage: at });
      // A handoff that died after a previous one dimmed the room (start()
      // keeps the dim on purpose, expecting to play again) must not leave it
      // dark with nothing playing.
      lights.set('restore');
    }
  }

  // --- the tracked session as a remote-controllable player ---

  const ticksToSecs = (t) => (t ? Math.round(t / 10_000_000) : 0);

  // Snapshot for the phone's TV player card. Always queried fresh: position
  // only updates as Jellyfin hears from the app, so the card interpolates
  // between polls itself.
  async function nowPlaying() {
    if (!owned) return { active: false };
    const mine = owned;
    const list = await d.sessions();
    const s = (list || []).find((x) => x.Id === mine.sessionId);
    const np = s?.NowPlayingItem;
    if (!np || np.Id !== mine.itemId) return { active: false };
    return {
      active: true,
      item: { id: np.Id, name: item?.name || np.Name },
      position: ticksToSecs(s.PlayState?.PositionTicks),
      duration: ticksToSecs(np.RunTimeTicks),
      paused: !!s.PlayState?.IsPaused,
    };
  }

  function requireOwned() {
    if (!owned) throw new Error('nothing playing on the TV that couch started');
    return owned;
  }

  async function stop() {
    const mine = requireOwned();
    // The press itself says "done here": let the monitor bring the input back
    // quickly once the session goes quiet, instead of the full 30s dwell.
    mine.stopRequested = true;
    await d.sessionCommand(mine.sessionId, 'Stop');
    return { ok: true };
  }

  async function playpause() {
    const mine = requireOwned();
    await d.sessionCommand(mine.sessionId, 'PlayPause');
    return { ok: true };
  }

  async function seek(seconds) {
    const mine = requireOwned();
    await d.seekSession(mine.sessionId, Math.max(0, seconds));
    return { ok: true };
  }

  // --- input restore (the "hand the TV back" half) ---
  // Watches the session we started; when it stops playing (session gone, or
  // NowPlayingItem empty for the dwell) the TV goes back to hdmi1 - but ONLY
  // if the TV's foreground app is still the Jellyfin app. If Donnie switched
  // to another app or input meanwhile, he went elsewhere deliberately: never
  // touch the input. tv status is one subprocess call, so it is only polled
  // while a restore is actually pending.

  function startMonitor() {
    if (monitorTimer) return;
    monitorTimer = setInterval(() => {
      monitorTick().catch((e) => d.log('monitor:', e.message));
    }, d.monitorPollMs);
    monitorTimer.unref?.();
  }

  function stopMonitor() {
    if (monitorTimer) {
      clearInterval(monitorTimer);
      monitorTimer = null;
    }
  }

  function disown() {
    owned = null;
    stopMonitor();
    // Every way out of ownership passes through here, which is exactly why the
    // lights hang off it: whatever ended the playback, the room comes back up.
    lights.set('restore');
    if (stage === 'playing') setStage('idle', { item: null });
  }

  // We are holding a dim but cannot see the session. Ownership stays (the TV
  // may well still be playing) - the lights do not, past the blind timeout.
  function lightsBlindCheck(mine) {
    if (!lights.state().dimmed) return;
    if (d.now() - mine.seenAt < d.lightsBlindMs) return;
    d.log('no confirmed playback for the blind timeout, putting the lights back');
    lights.set('restore');
  }

  async function monitorTick() {
    const mine = owned;
    if (!mine) {
      stopMonitor();
      return;
    }
    let list;
    try {
      list = await d.sessions();
    } catch {
      // Jellyfin unreachable: we know nothing, so we touch nothing - except
      // that a dim cannot be held blind forever.
      lightsBlindCheck(mine);
      return;
    }
    if (owned !== mine) return; // superseded while we were querying
    const s = (list || []).find((x) => x.Id === mine.sessionId);
    const nowId = s?.NowPlayingItem?.Id || null;
    if (nowId && nowId !== mine.itemId) {
      // Donnie picked something else on the TV himself: it is his playback
      // now, not ours. Walk away without touching the input.
      disown();
      return;
    }
    if (nowId === mine.itemId) {
      mine.goneAt = null; // still ours, still going (credits pause included)
      mine.seenAt = d.now();
      // Same rule light-watch uses on Kodi: playing = dim, paused = back up.
      lights.set(s.PlayState?.IsPaused ? 'restore' : 'dim');
      return;
    }
    // Session gone, or alive with nothing playing. The film is over as far as
    // the room is concerned, so the lights come up now rather than after the
    // input-restore dwell (which exists for the TV, not for the bulbs).
    lights.set('restore');
    if (mine.goneAt === null) {
      mine.goneAt = d.now();
      return;
    }
    // Restore pending: from here every tick checks the TV's foreground.
    let st;
    try {
      st = await d.tvStatus();
    } catch {
      return; // can't see the TV: never restore blind, try again next tick
    }
    if (owned !== mine) return;
    const fg = foregroundApp(st);
    if (fg !== JELLYFIN_APP) {
      // Another app, another input, or the TV is off: the user (or the TV)
      // moved on. The restore is cancelled for good, not retried.
      disown();
      return;
    }
    const dwell = mine.stopRequested ? d.stopDwellMs : d.goneDwellMs;
    if (d.now() - mine.goneAt < dwell) return;
    disown();
    try {
      await d.tvInputPc();
    } catch (e) {
      d.log('hdmi1 restore failed:', e.message);
    }
  }

  return {
    start,
    stop,
    playpause,
    seek,
    status,
    waitForChange,
    nowPlaying,
    configured: () => d.configured(),
    ownedPlayback: () => (owned ? { ...owned } : null),
    lightsState: () => lights.state(),
    // test hooks: drive the monitor by hand, no timers involved
    _monitorTick: monitorTick,
  };
}

// --- should this item auto-route to the TV? -----------------------------
//
// Donnie's ruling (7 Aug 2026): a plain click on an HDR or Dolby Vision film
// or episode should play on the TV's own Jellyfin app by itself; SDR keeps
// playing in Kodi exactly as before. The Kodi service addon asks this before
// it intercepts anything, so ALL the "when not to" rules live here, in one
// place, where the server can see the game session and its own TV state.
//
// The bias is absolute: anything we are not sure about answers false. A
// missing video stream, an unreadable Jellyfin, a container item, an id that
// is not an id - all of them mean "play it in Kodi", which is the behaviour
// that existed before this feature and cannot surprise anyone.

// VideoRangeType values that mean "the TV should do this one". HDR10+ and
// Dolby Vision report DOVI/HDR10Plus; HLG is broadcast HDR and equally
// tonemapped by the PC path.
const HDR_RANGE_TYPES = new Set(['HDR10', 'HDR10PLUS', 'DOVI', 'DOLBYVISION', 'HLG', 'HDR']);
const ROUTABLE_TYPES = new Set(['Movie', 'Episode']);

// profile (from jellyfin.videoProfileFor) -> { hdr, label }. Pure.
export function hdrVerdict(profile) {
  if (!profile) return { hdr: false, label: 'unknown' };
  const type = String(profile.videoRangeType || '').toUpperCase().replace(/[\s_-]/g, '');
  const range = String(profile.videoRange || '').toUpperCase();
  if (type && HDR_RANGE_TYPES.has(type)) return { hdr: true, label: profile.videoRangeType };
  // VideoRange alone is the older field and only ever says HDR or SDR; trust
  // it when the finer one is missing or is something we have never seen.
  if (range === 'HDR') return { hdr: true, label: profile.videoRangeType || 'HDR' };
  if (range === 'SDR') return { hdr: false, label: 'SDR' };
  return { hdr: false, label: 'unknown' };
}

const ID_RE = /^[0-9a-f]{32}$/;

const ROUTER_DEFAULTS = {
  profileFor: (id) => jellyfin.videoProfileFor(id),
  // The kill switch. Anything truthy from this means auto-routing is on.
  enabled: () => true,
  // Auto-routing while a game is up would yank the room mid-session.
  gameLive: () => false,
  // The TV is already busy with a handoff we started.
  tvBusy: () => false,
  now: () => Date.now(),
  log: (...a) => console.error('[tvroute]', ...a),
  // How long an explicit "play it in Kodi" (the phone's own Play button)
  // switches auto-routing off for. It only has to outlive the gap between
  // Player.Open and the service addon making up its mind, a few seconds.
  suppressMs: 20 * 1000,
  // A file's HDR-ness does not change; the cache only exists so a click does
  // not wait on Jellyfin twice (the addon asks, then the user re-clicks).
  ttlMs: 5 * 60 * 1000,
  // Failures are cached far more briefly: a Jellyfin blip must not pin an
  // item to "SDR" for the evening.
  failTtlMs: 20 * 1000,
  maxEntries: 200,
};

export function createHdrRouter(overrides = {}) {
  const d = { ...ROUTER_DEFAULTS, ...overrides };
  const cache = new Map(); // itemId -> { at, profile|null }
  // The phone's Play button opens the item in KODI on purpose - the same card
  // carries a separate Play on TV button. Auto-routing that click would take
  // one of the two explicit overrides away, so a deliberate Kodi play buys a
  // short window in which nothing is intercepted.
  let suppressUntil = 0;

  async function profile(itemId) {
    const hit = cache.get(itemId);
    if (hit && d.now() - hit.at < (hit.profile ? d.ttlMs : d.failTtlMs)) return hit.profile;
    let got = null;
    try {
      got = await d.profileFor(itemId);
    } catch (e) {
      d.log(`could not read ${itemId}:`, e.message);
      got = null;
    }
    if (cache.size >= d.maxEntries) cache.delete(cache.keys().next().value);
    cache.set(itemId, { at: d.now(), profile: got });
    return got;
  }

  // Always resolves; never throws. { route, reason, ... }
  async function shouldRoute(itemId) {
    const id = String(itemId || '').toLowerCase();
    if (!ID_RE.test(id)) return { route: false, reason: 'not a jellyfin item id' };
    if (!d.enabled()) return { route: false, reason: 'auto-routing is switched off', enabled: false };
    if (d.now() < suppressUntil) return { route: false, reason: 'this playback was asked for in Kodi' };
    if (d.gameLive()) return { route: false, reason: 'a game session is live' };
    if (d.tvBusy()) return { route: false, reason: 'the TV is already playing something couch started' };
    const p = await profile(id);
    if (!p) return { route: false, reason: 'could not read the item from jellyfin' };
    if (!ROUTABLE_TYPES.has(p.type)) return { route: false, reason: `not a film or episode (${p.type})` };
    const v = hdrVerdict(p);
    return {
      route: v.hdr,
      reason: v.hdr ? `${v.label} on the TV app` : `${v.label}, Kodi plays it`,
      videoRange: p.videoRange,
      videoRangeType: p.videoRangeType,
      width: p.width,
      bitDepth: p.bitDepth,
      name: p.name,
    };
  }

  return {
    shouldRoute,
    // Called by whatever deliberately starts a Kodi playback.
    suppress: () => { suppressUntil = d.now() + d.suppressMs; },
    _cacheSize: () => cache.size,
  };
}
