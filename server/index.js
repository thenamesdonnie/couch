// Couch: the phone-facing control surface for the living room box.
// One process: static frontend, JSON API, a WebSocket for live state.
// This server is the only thing holding credentials; the phone never
// talks to Kodi, Steam, the TV or the bulbs directly.
import http from 'node:http';
import net from 'node:net';
import path from 'node:path';
import fs from 'node:fs';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import express from 'express';
import { WebSocketServer } from 'ws';

import { PORT, LAN_HOST } from './config.js';
import { rpc, artUrl, kodiAuthHeader, KodiEvents, playerState, sendBuiltin } from './kodi.js';
import { listGames, isAllowedArt } from './games.js';
import * as sys from './sys.js';
import * as jellyfin from './jellyfin.js';
import * as jellyseerr from './jellyseerr.js';
import * as screen from './screen.js';
import * as sonarr from './sonarr.js';
import * as steam from './steam.js';
import * as youtube from './youtube.js';
import { activeDownloads } from './downloads.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WEB_DIST = path.join(__dirname, '..', 'web', 'dist');

const app = express();
app.use(express.json());

// Endless silent audio stream for the phone's Media Session. The phone needs a
// real, PLAYING audio element for iOS to show lock-screen / notification media
// controls, but a finite faked track makes iOS put a scrubber on it that can't
// be kept in sync with the TV (it bounced to zero). A stream with NO duration
// reads as LIVE, so iOS shows the controls with no scrubber - nothing to
// bounce. anullsrc generates silence; -re paces it in real time; killed when
// the phone disconnects (pause / close).
app.get('/api/silent', (req, res) => {
  res.writeHead(200, { 'Content-Type': 'audio/mpeg', 'Cache-Control': 'no-store' });
  const ff = spawn('ffmpeg', [
    '-hide_banner', '-loglevel', 'error',
    '-re', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
    '-b:a', '64k', '-f', 'mp3', 'pipe:1',
  ]);
  ff.stdout.pipe(res);
  ff.stderr.resume();
  const kill = () => { try { ff.kill('SIGKILL'); } catch { /* already gone */ } };
  ff.on('error', () => { try { res.end(); } catch { /* already closed */ } });
  res.on('close', kill);
});

const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: '/ws' });

// --- live state ---
// Kodi events schedule a reassessment shortly after rather than reacting to
// each one; that debounce absorbs stop/requeue churn (movie night) the same
// way light-watch does. Volume changes go out immediately, they carry their
// own payload and feel laggy otherwise.

let lastState = { volume: null, muted: false, playing: null };
let reassessTimer = null;

function broadcast(msg) {
  const raw = JSON.stringify(msg);
  for (const client of wss.clients) {
    if (client.readyState === 1) client.send(raw);
  }
}

// YouTube defaults to 1.25x (Donnie's preference); everything else stays 1x.
// Applied once per distinct YouTube video the moment it is actually playing,
// keyed by file so it never fights a manual change on the same video.
let ytDefaultKey = null;
let ytTempoTimers = [];
async function applyYouTubeDefault(playing) {
  if (!playing) { ytDefaultKey = null; return; }
  if (playing.isYouTube && playing.speed && playing.file !== ytDefaultKey) {
    ytDefaultKey = playing.file;
    // Setting tempo WHILE a YouTube stream is still initialising its audio
    // silences the audio and it does not recover on its own (Donnie hit this);
    // re-issuing any tempo kicks it back. So let the stream settle first, then
    // apply, then re-assert once as a safety net. tempo is absolute, so the
    // second send is a no-op when the audio is already fine.
    ytTempoTimers.forEach(clearTimeout);
    ytTempoTimers = [
      setTimeout(() => sendBuiltin('PlayerControl(tempo(1.25))').catch(() => {}), 1300),
      setTimeout(() => sendBuiltin('PlayerControl(tempo(1.25))').catch(() => {}), 2800),
    ];
  }
}

async function reassess() {
  reassessTimer = null;
  try {
    const state = await playerState();
    // End-of-stream glitch guard: a YouTube HLS/DVR stream can reach its end
    // without Kodi stopping the player - it just keeps ticking the clock past
    // the duration with no video (Donnie hit this: "glitched out instead of
    // gracefully backing out"). When the position overruns the duration, stop
    // it so it backs out cleanly instead of spinning forever.
    const pl = state.playing;
    if (pl && pl.duration > 0 && pl.position > pl.duration + 3) {
      await rpc('Player.Stop', { playerid: pl.playerid }).catch(() => {});
      state.playing = null;
    }
    state.pad = sys.padState();
    state.game = sys.gameSession();
    await applyYouTubeDefault(state.playing);
    lastState = state;
    broadcast({ type: 'state', state });
    // While a stream is at/near its end, poll faster so the end-of-stream glitch
    // guard above catches an overrun within a few seconds, not up to the 30s
    // safety poll. Stops on its own once playback ends (state.playing == null).
    if (state.playing?.isStream && state.playing.duration > 0 &&
        state.playing.position > state.playing.duration - 20) {
      scheduleReassess(4000);
    }
  } catch {
    // Kodi down (crash, restart): report an empty player, keep volume unknown.
    lastState = { volume: null, muted: false, playing: null, pad: sys.padState(), game: sys.gameSession(), kodiDown: true };
    broadcast({ type: 'state', state: lastState });
  }
}

function scheduleReassess(delay = 1500) {
  if (reassessTimer) return;
  reassessTimer = setTimeout(reassess, delay);
}

const events = new KodiEvents();
events.on('connect', () => scheduleReassess(500));
events.on('disconnect', () => scheduleReassess(2000));
events.on('notification', (method, params) => {
  if (method === 'Application.OnVolumeChanged') {
    lastState.volume = params?.data?.volume ?? lastState.volume;
    lastState.muted = params?.data?.muted ?? lastState.muted;
    broadcast({ type: 'volume', volume: lastState.volume, muted: lastState.muted });
    return;
  }
  if (method.startsWith('Player.') || method === 'Playlist.OnAdd') scheduleReassess();
});

// Pad and game-session changes have no event source; a light poll keeps the
// header fresh. Only broadcast when something actually changed.
let lastSideband = '';
setInterval(() => {
  const pad = sys.padState();
  const game = sys.gameSession();
  const key = JSON.stringify([pad, game]);
  if (key !== lastSideband) {
    lastSideband = key;
    lastState.pad = pad;
    lastState.game = game;
    broadcast({ type: 'sideband', pad, game });
  }
}, 5000);

// Safety poll so a missed event cannot leave the UI stale for long.
setInterval(() => scheduleReassess(0), 30000);

wss.on('connection', (client) => {
  client.send(JSON.stringify({ type: 'state', state: lastState }));
  scheduleReassess(0);
});

// --- helpers ---

const wrap = (fn) => async (req, res) => {
  try {
    const out = await fn(req, res);
    if (!res.headersSent) res.json(out ?? { ok: true });
  } catch (err) {
    if (!res.headersSent) res.status(502).json({ error: String(err.message || err) });
  }
};

// --- remote input ---

const INPUT_ACTIONS = {
  up: ['Input.Up'], down: ['Input.Down'], left: ['Input.Left'], right: ['Input.Right'],
  select: ['Input.Select'], back: ['Input.Back'], home: ['Input.Home'],
  context: ['Input.ContextMenu'], info: ['Input.Info'],
  osd: ['Input.ExecuteAction', { action: 'osd' }],
};

// Type into whatever text field Kodi has focused (its search box, a login
// field). done:true submits and closes Kodi's on-screen keyboard. Declared
// before the :action route so it isn't swallowed by it.
app.post('/api/input/text', wrap(async (req) => {
  const text = String(req.body?.text ?? '');
  await rpc('Input.SendText', { text, done: !!req.body?.done });
}));

app.post('/api/input/:action', wrap(async (req) => {
  const call = INPUT_ACTIONS[req.params.action];
  if (!call) throw new Error('unrecognised input action');
  await rpc(call[0], call[1]);
}));

// --- player ---

async function activePlayerId() {
  const players = await rpc('Player.GetActivePlayers');
  const p = players.find((x) => x.type === 'video' || x.type === 'audio');
  if (!p) throw new Error('nothing is playing');
  return p.playerid;
}

app.post('/api/player/playpause', wrap(async () => {
  await rpc('Player.PlayPause', { playerid: await activePlayerId() });
  scheduleReassess(300);
}));

app.post('/api/player/stop', wrap(async () => {
  await rpc('Player.Stop', { playerid: await activePlayerId() });
  scheduleReassess(500);
}));

const seekTarget = (target) => ({
  time: { hours: Math.floor(target / 3600), minutes: Math.floor((target % 3600) / 60), seconds: Math.floor(target % 60), milliseconds: 0 },
});

// After a seek, a STREAMED source (YouTube via inputstream.adaptive) throws away
// its buffer and re-fetches, so it plays through empty video/audio for a beat.
// Poll until the re-buffer finishes: Kodi reports it via Player.Seeking (settling
// the seek), Player.Caching (refetching) and Player.CacheLevel (fill %). Local
// files never dip, so this returns almost immediately.
async function waitForBuffer(timeoutMs = 4000) {
  const start = Date.now();
  await new Promise((r) => setTimeout(r, 120)); // let the seek register first
  while (Date.now() - start < timeoutMs) {
    const [b, l] = await Promise.all([
      rpc('XBMC.GetInfoBooleans', { booleans: ['Player.Caching', 'Player.Seeking'] }).catch(() => ({})),
      rpc('XBMC.GetInfoLabels', { labels: ['Player.CacheLevel'] }).catch(() => ({})),
    ]);
    const level = parseInt(l['Player.CacheLevel'] || '100', 10);
    if (!b['Player.Caching'] && !b['Player.Seeking'] && level >= 90) return;
    await new Promise((r) => setTimeout(r, 120));
  }
}

// Relative seek computed as an absolute target: portable across Kodi's seek
// dialects and exact for the skip-intro style nudges. For a streamed source we
// pause across the re-buffer and resume once it is ready, so the rewind comes
// back cleanly instead of showing a "playing but blank" gap (Donnie's ask).
app.post('/api/player/step', wrap(async (req) => {
  const offset = Number(req.body?.seconds);
  if (!Number.isFinite(offset)) throw new Error('seconds required');
  const playerid = await activePlayerId();
  const props = await rpc('Player.GetProperties', { playerid, properties: ['time', 'totaltime'] });
  const toSecs = (t) => t.hours * 3600 + t.minutes * 60 + t.seconds;
  const total = toSecs(props.totaltime);
  const target = Math.max(0, Math.min(total - 1, toSecs(props.time) + offset));
  const buffered = lastState.playing?.isStream && lastState.playing?.speed;
  if (buffered) await rpc('Player.PlayPause', { playerid, play: false });
  await rpc('Player.Seek', { playerid, value: seekTarget(target) });
  if (buffered) {
    await waitForBuffer();
    await rpc('Player.PlayPause', { playerid, play: true });
  }
  scheduleReassess(500);
}));

// Skip the intro exactly: if Jellyfin has an Intro segment for what is playing
// and we are inside it, jump to its end; otherwise fall back to a +85s nudge.
app.post('/api/player/skip-intro', wrap(async (req) => {
  const playerid = await activePlayerId();
  const jfId = lastState.playing?.jellyfinId;
  const props = await rpc('Player.GetProperties', { playerid, properties: ['time', 'totaltime'] });
  const toSecs = (t) => t.hours * 3600 + t.minutes * 60 + t.seconds;
  const nowSecs = toSecs(props.time);
  const total = toSecs(props.totaltime);
  let target = Math.min(total - 1, nowSecs + 85);
  let exact = false;
  if (jfId) {
    const segs = await jellyfin.segmentsFor(jfId).catch(() => []);
    // The nearest intro/recap segment we are currently within.
    const seg = segs.find((s) => (s.type === 'Intro' || s.type === 'Recap') && nowSecs >= s.start - 1 && nowSecs < s.end);
    if (seg) { target = seg.end; exact = true; }
  }
  await rpc('Player.Seek', { playerid, value: seekTarget(target) });
  scheduleReassess(500);
  return { exact, target };
}));

app.post('/api/player/seek', wrap(async (req) => {
  const pct = Number(req.body?.percentage);
  if (!Number.isFinite(pct)) throw new Error('percentage required');
  await rpc('Player.Seek', { playerid: await activePlayerId(), value: { percentage: Math.max(0, Math.min(100, pct)) } });
  scheduleReassess(500);
}));

app.post('/api/player/next', wrap(async () => {
  await rpc('Player.GoTo', { playerid: await activePlayerId(), to: 'next' });
}));

// Smooth playback speed (pitch-corrected audio), the real thing - via the
// PlayerControl(tempo(x)) builtin over the EventServer. Works on library files
// and YouTube alike; needs "Sync playback to display" on (set at startup).
// Kodi caps tempo around its own range, so values are clamped to a sane set.
const TEMPOS = new Set([0.75, 1, 1.25, 1.5, 1.75, 2]);
app.post('/api/player/speed', wrap(async (req) => {
  const speed = Number(req.body?.speed);
  if (!TEMPOS.has(speed)) throw new Error('unsupported speed');
  await activePlayerId(); // 400s if nothing is playing
  await sendBuiltin(`PlayerControl(tempo(${speed}))`);
  scheduleReassess(500);
}));

app.post('/api/player/previous', wrap(async () => {
  await rpc('Player.GoTo', { playerid: await activePlayerId(), to: 'previous' });
}));

app.post('/api/player/subtitle', wrap(async (req) => {
  const playerid = await activePlayerId();
  const { index } = req.body ?? {};
  if (index === null || index === undefined || index === 'off') {
    await rpc('Player.SetSubtitle', { playerid, subtitle: 'off' });
  } else {
    await rpc('Player.SetSubtitle', { playerid, subtitle: Number(index), enable: true });
  }
  scheduleReassess(500);
}));

app.post('/api/player/audio', wrap(async (req) => {
  const playerid = await activePlayerId();
  await rpc('Player.SetAudioStream', { playerid, stream: Number(req.body?.index) });
  scheduleReassess(500);
}));

// --- volume ---

app.post('/api/volume', wrap(async (req) => {
  const { level, step, mute } = req.body ?? {};
  if (mute !== undefined) await rpc('Application.SetMute', { mute: !!mute });
  else if (Number.isFinite(Number(level))) await rpc('Application.SetVolume', { volume: Math.max(0, Math.min(100, Number(level))) });
  else if (step === 'up' || step === 'down') await rpc('Application.SetVolume', { volume: step === 'up' ? 'increment' : 'decrement' });
  else throw new Error('level, step or mute required');
}));

// --- notify the TV screen ---

app.post('/api/notify', wrap(async (req) => {
  const { title, message } = req.body ?? {};
  if (!message) throw new Error('message required');
  await rpc('GUI.ShowNotification', { title: title || 'Couch', message: String(message).slice(0, 200), displaytime: 8000 });
}));

// --- games ---

app.get('/api/games', wrap(async () => {
  const games = listGames().map((g) => ({
    ...g,
    poster: g.poster ? `/api/art/game?p=${encodeURIComponent(g.poster)}` : null,
    hero: undefined,
  }));
  return { games, session: sys.gameSession() };
}));

app.post('/api/games/launch', wrap(async (req) => {
  const id = String(req.body?.id || '');
  if (!id) throw new Error('id required');
  sys.launchGame(id);
}));

app.post('/api/games/suspend', wrap(async () => {
  const froze = await sys.suspendGame();
  if (froze) {
    // Hand the pad back to Kodi, as the PS-hold path does.
    await rpc('Settings.SetSettingValue', { setting: 'input.enablejoystick', value: true }).catch(() => {});
  }
  return { suspended: froze };
}));

app.post('/api/games/resume', wrap(async () => sys.resumeGame()));
app.post('/api/games/quit', wrap(async () => sys.quitGame()));

// --- steam library + downloads ---

app.get('/api/steam/library', wrap(async () => ({ games: await steam.library() })));
app.get('/api/steam/downloads', wrap(async () => ({ downloads: await steam.downloads() })));

app.post('/api/steam/install', wrap(async (req) => {
  const { appid } = req.body ?? {};
  return steam.install(appid);
}));

app.get('/api/art/steam', wrap(async (req, res) => {
  const appid = Number(req.query.appid);
  if (!Number.isInteger(appid)) { res.status(404).end(); return; }
  const src = steam.artRequest(appid);
  res.set('cache-control', 'public, max-age=86400');
  if (src.file) { res.set('content-type', 'image/jpeg'); res.send(fs.readFileSync(src.file)); return; }
  for (const url of src.urls) {
    try {
      const up = await fetch(url, { signal: AbortSignal.timeout(6000) });
      if (up.ok) {
        res.set('content-type', up.headers.get('content-type') || 'image/jpeg');
        res.send(Buffer.from(await up.arrayBuffer()));
        return;
      }
    } catch { /* try next */ }
  }
  res.status(404).end();
}));

// --- pad ---

app.get('/api/pad', wrap(async () => sys.padState()));
app.post('/api/pad/connect', wrap(async () => ({ out: await sys.padConnect() })));
app.post('/api/pad/disconnect', wrap(async () => ({ out: await sys.padDisconnect() })));

// --- tv and lights ---

let tvCache = { at: 0, status: null };
app.get('/api/tv', wrap(async (req) => {
  if (req.query.fresh || Date.now() - tvCache.at > 60000) {
    tvCache = { at: Date.now(), status: await sys.tv('status') };
  }
  return { status: tvCache.status, at: tvCache.at };
}));

app.post('/api/tv/:cmd', wrap(async (req) => {
  const out = await sys.tv(req.params.cmd);
  tvCache = { at: 0, status: null };
  return { out };
}));

let lightsCache = { at: 0, bulbs: [] };
app.get('/api/lights', wrap(async (req) => {
  if (req.query.fresh || Date.now() - lightsCache.at > 60000) {
    const out = await sys.lights('status');
    lightsCache = { at: Date.now(), bulbs: sys.parseLightsStatus(out) };
  }
  return { bulbs: lightsCache.bulbs, at: lightsCache.at };
}));

app.post('/api/lights/:cmd', wrap(async (req) => {
  const out = await sys.lights(req.params.cmd, req.body?.dim);
  lightsCache = { at: 0, bulbs: [] };
  return { out };
}));

// --- library (jellyfin-backed) ---

app.get('/api/library/show/:id', wrap(async (req) => ({
  episodes: await jellyfin.showEpisodes(req.params.id),
})));

app.get('/api/library/continue', wrap(async () => jellyfin.continueWatching()));

app.get('/api/library/:kind', wrap(async (req) => {
  if (!['movies', 'shows'].includes(req.params.kind)) throw new Error('unrecognised library kind');
  return jellyfin.listLibrary(req.params.kind, {
    search: req.query.search,
    sort: req.query.sort,
    order: req.query.order,
  });
}));

// Cast to the TV: resolve the Jellyfin item to its synced Kodi library entry
// and play THAT, so resume points and skip-intro segments behave exactly as a
// pad-picked play would.
app.post('/api/cast', wrap(async (req) => {
  const { id, fromStart } = req.body ?? {};
  const { mediaType, kodiId } = await jellyfin.kodiIdFor(String(id || ''));
  const keys = { movie: 'movieid', episode: 'episodeid', musicvideo: 'musicvideoid' };
  const key = keys[mediaType];
  if (!key) throw new Error(`cannot cast a ${mediaType}`);
  await rpc('Player.Open', {
    item: { [key]: kodiId },
    options: { resume: !fromStart },
  });
  scheduleReassess(3000);
  return { ok: true, mediaType };
}));

// --- in-app youtube: search, trending, play on TV ---

app.get('/api/youtube/search', wrap(async (req) => {
  const q = String(req.query.q || '').trim();
  if (!q) return { results: [] };
  return { results: await youtube.search(q) };
}));

app.get('/api/youtube/trending', wrap(async () => ({ results: await youtube.trending() })));

// The subscription and recommendation feeds, read from the Kodi plugin's own
// folders (Files.GetDirectory) so they match exactly what the TV shows and use
// the plugin's signed-in session - no separate OAuth. Durations backfilled in
// one Data API call.
const YT_FOLDERS = {
  subscriptions: 'special/my_subscriptions',
  recommendations: 'special/recommendations',
  trending: 'special/popular_right_now',
};
app.get('/api/youtube/feed', wrap(async (req) => {
  const folder = YT_FOLDERS[req.query.type];
  if (!folder) throw new Error('unknown feed');
  const dir = await rpc('Files.GetDirectory', {
    directory: `plugin://plugin.video.youtube/${folder}`,
    media: 'video',
    properties: ['art'],
  });
  const items = [];
  for (const f of dir.files || []) {
    const id = (f.file || '').match(/video_id=([\w-]+)/)?.[1];
    if (!id) continue; // skip navigation sub-folders (Shorts, Live, ...)
    items.push({ id, title: (f.label || '').replace(/\[[^\]]+\]/g, '').trim(), channel: '', duration: '' });
  }
  const durations = await youtube.durationsFor(items.map((i) => i.id)).catch(() => ({}));
  for (const i of items) i.duration = durations[i.id] || '';
  return { results: items };
}));

app.post('/api/youtube/play', wrap(async (req) => {
  const id = String(req.body?.id || '');
  if (!/^[\w-]{6,15}$/.test(id)) throw new Error('bad video id');
  await rpc('Player.Open', {
    item: { file: `plugin://plugin.video.youtube/play/?video_id=${id}` },
  });
  scheduleReassess(3000);
}));

app.get('/api/art/yt', wrap(async (req, res) => {
  const id = String(req.query.id || '');
  if (!/^[\w-]{6,15}$/.test(id)) { res.status(404).end(); return; }
  const up = await fetch(youtube.thumbUrl(id), { signal: AbortSignal.timeout(6000) });
  if (!up.ok) { res.status(404).end(); return; }
  res.set('content-type', up.headers.get('content-type') || 'image/jpeg');
  res.set('cache-control', 'public, max-age=86400');
  res.send(Buffer.from(await up.arrayBuffer()));
}));

// Play a title's trailer on the TV through Kodi's YouTube addon, which plays
// the raw stream ad-free at 1080p.
app.post('/api/trailer', wrap(async (req) => {
  const id = String(req.body?.id || '');
  if (!/^[0-9a-f]{32}$/.test(id)) throw new Error('id required');
  const videoId = await jellyfin.trailerFor(id);
  await rpc('Player.Open', {
    item: { file: `plugin://plugin.video.youtube/play/?video_id=${videoId}` },
  });
  scheduleReassess(3000);
}));

// Jellyfin posters, proxied with the server-held token.
app.get('/api/art/jf/:id/:type', wrap(async (req, res) => {
  if (!['Primary', 'Backdrop', 'Thumb'].includes(req.params.type)) { res.status(404).end(); return; }
  if (!/^[0-9a-f]{32}$/.test(req.params.id)) { res.status(404).end(); return; }
  const { url, headers } = jellyfin.jfImageRequest(req.params.id, req.params.type, {
    tag: req.query.tag,
    maxWidth: Math.min(Number(req.query.w) || 400, 1280),
    quality: 90,
  });
  const upstream = await fetch(url, { headers });
  if (!upstream.ok) { res.status(404).end(); return; }
  res.set('content-type', upstream.headers.get('content-type') || 'image/jpeg');
  res.set('cache-control', 'public, max-age=86400');
  res.send(Buffer.from(await upstream.arrayBuffer()));
}));

// --- discover (jellyseerr) ---

app.get('/api/discover/search', wrap(async (req) => {
  const q = String(req.query.q || '').trim();
  if (!q) return { total: 0, results: [] };
  return jellyseerr.search(q, Number(req.query.page) || 1);
}));

app.get('/api/discover/trending', wrap(async () => ({ results: await jellyseerr.trending() })));

app.get('/api/discover/popular', wrap(async (req) => ({
  results: await jellyseerr.popular(req.query.type === 'tv' ? 'tv' : 'movies'),
})));

// --- the rest of the fleet: every web UI on the box, with reachability ---

// Host comes from COUCH_LAN_HOST so no LAN address is baked into the source.
const SERVICES = [
  { name: 'Jellyfin', desc: 'Media server', port: 8096 },
  { name: 'Jellyseerr', desc: 'Requests', port: 5055 },
  { name: 'Sonarr', desc: 'Shows', port: 8989 },
  { name: 'Radarr', desc: 'Films', port: 7878 },
  { name: 'Bazarr', desc: 'Subtitles', port: 6767 },
  { name: 'Prowlarr', desc: 'Indexers', port: 9696 },
  { name: 'qBittorrent', desc: 'Downloads', port: 8080 },
  { name: 'Autobrr', desc: 'Auto grabbing', port: 7474 },
  { name: 'File browser', desc: 'Drop zone', port: 8082 },
  { name: 'Crafty', desc: 'Minecraft', port: 8443, scheme: 'https' },
  { name: 'Glances', desc: 'System monitor', port: 61208 },
  { name: 'WireGuard', desc: 'VPN', port: 51821 },
  { name: 'Rota', desc: 'Work rota', port: 8787 },
  { name: 'Norish', desc: 'Recipes', port: 3000 },
  { name: 'Howff', desc: 'Nights out', port: 3310 },
  { name: 'MacroLog', desc: 'Macros', port: 8321 },
  { name: 'Easy Cribs', desc: 'Property', port: 3005 },
].map((s) => ({ name: s.name, desc: s.desc, url: `${s.scheme || 'http'}://${LAN_HOST}:${s.port}` }));

// Reachability by TCP connect: works for self-signed https (Crafty) and
// auth-walled UIs alike.
function portOpen(host, port) {
  return new Promise((resolve) => {
    const sock = net.connect({ host, port, timeout: 1500 });
    sock.on('connect', () => { sock.destroy(); resolve(true); });
    sock.on('timeout', () => { sock.destroy(); resolve(false); });
    sock.on('error', () => resolve(false));
  });
}

app.get('/api/services', wrap(async () => {
  const checked = await Promise.all(SERVICES.map(async (s) => {
    const u = new URL(s.url);
    return { ...s, up: await portOpen(u.hostname, Number(u.port) || (u.protocol === 'https:' ? 443 : 80)) };
  }));
  return { services: checked };
}));

app.get('/api/discover/detail', wrap(async (req) => {
  const { type, tmdbId } = req.query;
  if (!['movie', 'tv'].includes(type) || !tmdbId) throw new Error('type and tmdbId required');
  const detail = await jellyseerr.detail(type, tmdbId);
  // For films, note if a home release hasn't landed yet, so a request is an
  // informed one.
  if (type === 'movie') {
    const { releaseInfo } = await import('./radarr.js');
    const rel = await releaseInfo(Number(tmdbId)).catch(() => null);
    if (rel?.phase === 'waiting') {
      detail.releaseNote = rel.date
        ? `Not out for home viewing yet · ${rel.kind} release ${new Date(rel.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`
        : 'In cinemas now · no home release date yet';
    }
  }
  return detail;
}));

app.post('/api/discover/request', wrap(async (req) => {
  const { mediaType, tmdbId } = req.body ?? {};
  if (!['movie', 'tv'].includes(mediaType) || !tmdbId) throw new Error('mediaType and tmdbId required');
  await jellyseerr.requestMedia(mediaType, tmdbId);
}));

app.get('/api/discover/requests', wrap(async () => ({ requests: await jellyseerr.listRequests() })));

app.get('/api/downloads', wrap(async () => ({ downloads: await activeDownloads() })));

app.get('/api/upcoming', wrap(async () => ({ episodes: await sonarr.upcoming() })));

// TMDB posters for discover results, proxied so the phone stays local-only.
app.get('/api/art/tmdb', wrap(async (req, res) => {
  const p = String(req.query.p || '');
  if (!/^\/[\w.-]+\.(jpg|png)$/.test(p)) { res.status(404).end(); return; }
  const upstream = await fetch(`https://image.tmdb.org/t/p/w342${p}`);
  if (!upstream.ok) { res.status(404).end(); return; }
  res.set('content-type', upstream.headers.get('content-type') || 'image/jpeg');
  res.set('cache-control', 'public, max-age=604800');
  res.send(Buffer.from(await upstream.arrayBuffer()));
}));

// --- health and system actions ---

app.get('/api/health', wrap(async () => sys.health()));

app.post('/api/system/kodi-restart', wrap(async () => ({ out: await sys.kodiRestart() })));

// --- couchd ---

// The phone's window on the shadow daemon: its status file, read fresh on every
// request (never cached - a cached reading of a liveness file is worse than no
// reading). couchd being absent answers ok:false, not an error.
app.get('/api/couchd/status', wrap(async (req, res) => {
  res.set('cache-control', 'no-store');
  return sys.couchdStatus();
}));

// --- live screen ---

app.get('/api/screen', wrap(async (req, res) => {
  const { jpeg, source } = await screen.capture(String(req.query.src || 'auto'));
  res.set('content-type', 'image/jpeg');
  res.set('cache-control', 'no-store');
  res.set('x-screen-source', source);
  res.send(jpeg);
}));

app.get('/api/screen/stream', (req, res) => {
  screen.stream(req, res, String(req.query.src || 'auto')).catch(() => {
    try { res.end(); } catch {}
  });
});

app.post('/api/screen/click', wrap(async (req) => {
  const { x, y, button } = req.body ?? {};
  if (!Number.isFinite(Number(x)) || !Number.isFinite(Number(y))) throw new Error('x and y required');
  const result = await screen.click(x, y, Number(button) || 1);
  return { ok: true, text: !!result.text };
}));

app.post('/api/screen/type', wrap(async (req) => {
  if (!req.body?.text) throw new Error('text required');
  await screen.typeText(req.body.text);
}));

app.post('/api/screen/key', wrap(async (req) => {
  await screen.pressKey(String(req.body?.key || ''));
}));

app.get('/api/windows', wrap(async () => ({ windows: await screen.windows() })));

app.post('/api/windows/activate', wrap(async (req) => {
  await screen.activateWindow(String(req.body?.id || ''));
  scheduleReassess(1500);
}));

// --- art proxies ---

// Kodi art (posters for whatever is playing): proxy through Kodi's webserver,
// which decodes its own image:// urls. The phone never needs Kodi's password.
app.get('/api/art/kodi', wrap(async (req, res) => {
  const p = String(req.query.p || '');
  if (!p) throw new Error('p required');
  const upstream = await fetch(artUrl(p), { headers: { authorization: kodiAuthHeader() } });
  if (!upstream.ok) { res.status(404).end(); return; }
  res.set('content-type', upstream.headers.get('content-type') || 'image/jpeg');
  res.set('cache-control', 'public, max-age=86400');
  res.send(Buffer.from(await upstream.arrayBuffer()));
}));

// Game art comes straight off disk, restricted to the known art roots.
app.get('/api/art/game', wrap(async (req, res) => {
  const p = String(req.query.p || '');
  if (!p || !isAllowedArt(p) || !fs.existsSync(p)) { res.status(404).end(); return; }
  // Not res.sendFile: express refuses dotfile path segments and Steam's art
  // lives under ~/.steam.
  res.set('cache-control', 'public, max-age=3600');
  res.set('content-type', p.endsWith('.png') ? 'image/png' : 'image/jpeg');
  res.send(fs.readFileSync(p));
}));

// --- state snapshot for first paint ---

app.get('/api/state', wrap(async () => lastState));

// --- static frontend ---

// Hashed assets never change under a given URL, so cache them hard; but
// index.html must never be cached, or iOS keeps serving an old build that
// points at old assets (the "updates every other time" staleness).
app.use(express.static(WEB_DIST, {
  etag: true,
  setHeaders(res, filePath) {
    if (filePath.includes(`${path.sep}assets${path.sep}`)) {
      res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
    } else {
      res.setHeader('Cache-Control', 'no-store');
    }
  },
}));
app.get(/^\/(?!api\/).*/, (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  res.sendFile(path.join(WEB_DIST, 'index.html'));
});

server.listen(PORT, () => {
  console.log(`couch listening on :${PORT}`);
  scheduleReassess(0);
  // Smooth playback speed needs "Sync playback to display"; ensure it's on so
  // the speed control always works. Best-effort, Kodi may be down at boot.
  rpc('Settings.SetSettingValue', { setting: 'videoplayer.usedisplayasclock', value: true }).catch(() => {});
});
