// Kodi access: JSON-RPC over HTTP for commands and queries, plus a persistent
// connection to the TCP notification socket so player state changes reach us
// the moment they happen instead of on a poll.
import net from 'node:net';
import { EventEmitter } from 'node:events';
import { execFile } from 'node:child_process';
import { KODI_URL, KODI_USER, KODI_EVENT_HOST, KODI_EVENT_PORT, secret } from './config.js';

const HTTP_URL = `${KODI_URL}/jsonrpc`;
const EVENT_PORT = KODI_EVENT_PORT;

let idCounter = 1;

export async function rpc(method, params) {
  const body = { jsonrpc: '2.0', id: idCounter++, method };
  if (params !== undefined) body.params = params;
  const res = await fetch(HTTP_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: kodiAuthHeader() },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) throw new Error(`kodi http ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(`kodi: ${data.error.message || JSON.stringify(data.error)}`);
  return data.result;
}

// Kodi item art values are image:// urls (or raw http ones from the jellyfin
// addon); the webserver decodes them at /image/<urlencoded>. This builds the
// fetchable form so the server can proxy posters to the phone.
export function artUrl(kodiPath) {
  if (!kodiPath) return null;
  return `${KODI_URL}/image/${encodeURIComponent(kodiPath)}`;
}

// Built on first use, not at import time, so a missing password fails on the
// request that needs it rather than taking the whole server down at boot.
let authHeader = null;
export function kodiAuthHeader() {
  if (!authHeader) {
    authHeader = 'Basic ' + Buffer.from(`${KODI_USER}:${secret('KODI_PASSWORD')}`).toString('base64');
  }
  return authHeader;
}

// Run a Kodi builtin via the EventServer. JSON-RPC can't run builtins (removed
// for security), so PlayerControl(tempo(x)) - the smooth playback-speed control
// with pitch-corrected audio - only reachable this way, not Input.ExecuteAction.
export function sendBuiltin(action) {
  return new Promise((resolve, reject) => {
    execFile('kodi-send', [`--action=${action}`], { timeout: 5000 },
      (err) => (err ? reject(err) : resolve()));
  });
}

// The notification socket speaks bare concatenated JSON objects with no
// framing, so balance braces to split them. Strings can contain braces;
// track quoting.
function makeStreamParser(onMessage) {
  let buf = '';
  let depth = 0;
  let inString = false;
  let escaped = false;
  let start = 0;
  return (chunk) => {
    buf += chunk;
    for (let i = start; i < buf.length; i++) {
      const c = buf[i];
      if (inString) {
        if (escaped) escaped = false;
        else if (c === '\\') escaped = true;
        else if (c === '"') inString = false;
        continue;
      }
      if (c === '"') inString = true;
      else if (c === '{') depth++;
      else if (c === '}') {
        if (depth === 0) {
          // A stray '}' with nothing open (a dropped chunk, a socket picked up
          // mid-object) would take depth negative and every later object would
          // close one brace short: the parser goes silent until the socket
          // reconnects. Drop it and resync on the next '{' instead.
          buf = buf.slice(i + 1);
          i = -1;
          continue;
        }
        depth--;
        if (depth === 0) {
          const raw = buf.slice(0, i + 1).trim();
          buf = buf.slice(i + 1);
          i = -1;
          try { onMessage(JSON.parse(raw)); } catch { /* partial garbage, drop */ }
        }
      }
    }
    start = buf.length;
    if (buf.length > 1_000_000) { buf = ''; depth = 0; inString = false; start = 0; }
  };
}

// Emits 'notification' with {method, params} for every Kodi event, and
// 'connect'/'disconnect' for the socket itself. Reconnects forever; Kodi
// restarts (the watchdog cycles it after crashes) must be invisible to the app.
export class KodiEvents extends EventEmitter {
  constructor() {
    super();
    this.sock = null;
    this.alive = false;
    this._connect();
  }

  _connect() {
    const sock = net.connect(EVENT_PORT, KODI_EVENT_HOST);
    this.sock = sock;
    sock.setEncoding('utf8');
    const feed = makeStreamParser((msg) => {
      if (msg.method) this.emit('notification', msg.method, msg.params);
    });
    sock.on('connect', () => { this.alive = true; this.emit('connect'); });
    sock.on('data', feed);
    const drop = () => {
      if (this.alive) { this.alive = false; this.emit('disconnect'); }
      sock.destroy();
      clearTimeout(this._retry);
      this._retry = setTimeout(() => this._connect(), 3000);
    };
    sock.on('error', drop);
    sock.on('close', drop);
  }
}

// One snapshot of what is on the TV: active player, item, position, streams,
// volume. Everything the Playing view and the mini strip need.
export async function playerState() {
  const [app, players] = await Promise.all([
    rpc('Application.GetProperties', { properties: ['volume', 'muted'] }),
    rpc('Player.GetActivePlayers'),
  ]);
  const state = { volume: app.volume, muted: app.muted, playing: null };
  const player = players.find((p) => p.type === 'video' || p.type === 'audio');
  if (!player) return state;
  const [itemRes, props, labels] = await Promise.all([
    rpc('Player.GetItem', {
      playerid: player.playerid,
      properties: ['title', 'showtitle', 'season', 'episode', 'art', 'duration', 'file', 'year'],
    }),
    rpc('Player.GetProperties', {
      playerid: player.playerid,
      properties: [
        'time', 'totaltime', 'percentage', 'speed', 'subtitles',
        'currentsubtitle', 'subtitleenabled', 'audiostreams', 'currentaudiostream',
      ],
    }),
    // The smooth tempo (1.00, 1.25, ...) lives only in this infolabel, not in
    // GetProperties.speed (which is the fast-forward multiplier).
    rpc('XBMC.GetInfoLabels', { labels: ['Player.PlaySpeed'] }).catch(() => ({})),
  ]);
  const item = itemRes.item || {};
  const toSecs = (t) => (t ? t.hours * 3600 + t.minutes * 60 + t.seconds : 0);
  // The jellyfin-kodi plugin's file url carries the Jellyfin item id (?id=...);
  // pull it so skip-intro can look up the intro segment.
  const jfId = (item.file || '').match(/[?&]id=([0-9a-f]{32})/)?.[1] || null;
  const file = item.file || '';
  // isYouTube keys the 1.25x default and is only true at START (the plugin:// url
  // before it resolves). isStream is the broader "re-buffers on seek" flag: once
  // playing, YouTube reports its resolved googlevideo/HLS url, so match that too.
  // LAN Jellyfin files are http but never dip, so waitForBuffer is a no-op there.
  const isYouTube = file.includes('plugin.video.youtube');
  const isStream = isYouTube || /googlevideo\.com|\.m3u8|manifest\./i.test(file);
  state.playing = {
    playerid: player.playerid,
    type: item.type,
    jellyfinId: jfId,
    file,
    isYouTube,
    isStream,
    title: item.title || item.label || '',
    showtitle: item.showtitle || '',
    season: item.season,
    episode: item.episode,
    year: item.year,
    art: {
      poster: item.art?.poster || item.art?.['tvshow.poster'] || item.art?.thumb || null,
      fanart: item.art?.fanart || null,
    },
    position: toSecs(props.time),
    duration: toSecs(props.totaltime),
    speed: props.speed,
    tempo: parseFloat(labels['Player.PlaySpeed']) || 1,
    at: Date.now(),
    subtitles: props.subtitles || [],
    currentSubtitle: props.subtitleenabled ? props.currentsubtitle : null,
    subtitleEnabled: !!props.subtitleenabled,
    audioStreams: props.audiostreams || [],
    currentAudioStream: props.currentaudiostream || null,
  };
  return state;
}
