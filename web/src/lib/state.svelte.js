// Shared live state. One WebSocket feeds every view; REST calls go through
// api() so errors surface in one place.

export const live = $state({
  connected: false,
  kodiDown: false,
  volume: null,
  muted: false,
  playing: null,
  pad: { connected: false, battery: null, charging: false },
  game: { active: false, mode: null, appid: null, suspended: null },
  error: null,
});

function apply(state) {
  live.kodiDown = !!state.kodiDown;
  live.volume = state.volume;
  live.muted = !!state.muted;
  live.playing = state.playing ?? null;
  if (state.pad) live.pad = state.pad;
  if (state.game) live.game = state.game;
  updateMediaSession();
}

// Lock-screen / notification media controls via the Media Session API. The
// phone shows what is on the TV with poster and transport, and the buttons
// drive Kodi. iOS only surfaces the controls while a REAL audio element is
// playing, and only lets audio start inside a user gesture - so we play an
// ENDLESS silent stream from the box (/api/silent) and unlock it on the first
// tap. Because that stream has no duration, iOS treats it as LIVE and shows NO
// scrubber: there is nothing to keep in sync with the TV and nothing to bounce.
// (Every attempt to fake a finite track's position drifted or bounced to zero,
// because iOS reads position from the element's own clock, which we can't make
// match the TV.) So: solid play/pause + title + artwork, no scrubber.
let silent = null;
function armSilent() {
  if (silent || typeof Audio === 'undefined') return;
  silent = new Audio('/api/silent');
  silent.preload = 'auto';
}

function unlockAudio() {
  armSilent();
  silent?.play().then(() => { if (!live.playing?.speed) silent.pause(); }).catch(() => {});
}
if (typeof window !== 'undefined') {
  window.addEventListener('pointerdown', unlockAudio, { once: true });
  window.addEventListener('touchend', unlockAudio, { once: true });
}

function updateMediaSession() {
  if (!('mediaSession' in navigator)) return;
  const p = live.playing;
  if (!p) {
    navigator.mediaSession.metadata = null;
    navigator.mediaSession.playbackState = 'none';
    silent?.pause();
    return;
  }
  armSilent();
  // iOS reads the lock-screen play/pause ICON from the element's own paused
  // state (not playbackState), so the element must mirror the TV: play when
  // playing, pause when paused, or the icon sticks. (Trade-off: a very long
  // pause can let iOS reclaim the Now Playing session; a correct, responsive
  // icon is worth more than surviving a long idle pause.)
  if (p.speed) silent?.play().catch(() => {});
  else silent?.pause();
  navigator.mediaSession.metadata = new MediaMetadata({
    title: p.title,
    artist: p.showtitle || (p.year ? String(p.year) : 'On the TV'),
    artwork: p.art?.poster
      ? [{ src: '/api/art/kodi?p=' + encodeURIComponent(p.art.poster), sizes: '512x512', type: 'image/jpeg' }]
      : [],
  });
  navigator.mediaSession.playbackState = p.speed ? 'playing' : 'paused';
  try {
    // Optimistic: flip our local state + the session immediately so the icon
    // updates on tap instead of waiting ~1.5s for the server's next broadcast.
    const toggle = () => { optimisticPlayPause(); updateMediaSession(); api('/api/player/playpause', {}); };
    navigator.mediaSession.setActionHandler('play', toggle);
    navigator.mediaSession.setActionHandler('pause', toggle);
    navigator.mediaSession.setActionHandler('seekbackward', () => { optimisticStep(-10); updateMediaSession(); api('/api/player/step', { seconds: -10 }); });
    navigator.mediaSession.setActionHandler('seekforward', () => { optimisticStep(30); updateMediaSession(); api('/api/player/step', { seconds: 30 }); });
    navigator.mediaSession.setActionHandler('previoustrack', () => api('/api/player/previous', {}));
    navigator.mediaSession.setActionHandler('nexttrack', () => api('/api/player/next', {}));
  } catch { /* some handlers unsupported on some browsers */ }
  // No setPositionState: it is a live source with no scrubber, so there is no
  // position to report and nothing to bounce.
}

let socket = null;
let retry = null;

export function connect() {
  if (socket) return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  socket = ws;
  ws.onopen = () => { live.connected = true; };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === 'state') apply(msg.state);
    else if (msg.type === 'volume') { live.volume = msg.volume; live.muted = msg.muted; }
    else if (msg.type === 'sideband') { live.pad = msg.pad; live.game = msg.game; }
  };
  ws.onclose = () => {
    live.connected = false;
    socket = null;
    clearTimeout(retry);
    retry = setTimeout(connect, 2000);
  };
  ws.onerror = () => ws.close();
}

let errorTimer = null;

export async function api(path, body) {
  try {
    const res = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? undefined : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `request failed (${res.status})`);
    return data;
  } catch (err) {
    live.error = String(err.message || err);
    clearTimeout(errorTimer);
    errorTimer = setTimeout(() => { live.error = null; }, 4000);
    throw err;
  }
}

// Live position for whatever is playing, interpolated between server updates.
export function positionNow() {
  const p = live.playing;
  if (!p) return 0;
  if (!p.speed) return p.position;
  // Real advance rate is the fast-forward speed times the smooth tempo (only
  // one is ever non-1 in practice): normal 1, tempo 1.5x, fast-forward 2x.
  const rate = p.speed * (p.tempo || 1);
  return Math.min(p.duration, p.position + ((Date.now() - p.at) / 1000) * rate);
}

// Optimistic playback updates: reflect the action immediately so the scrub bar
// and buttons don't snap back to the old position for the second before the
// server's next state broadcast lands. The real update corrects anything off.
function clampPos(s) {
  const p = live.playing;
  return Math.max(0, Math.min(p.duration || Infinity, s));
}
export function optimisticSeekTo(seconds) {
  if (!live.playing) return;
  live.playing.position = clampPos(seconds);
  live.playing.at = Date.now();
}
export function optimisticStep(delta) {
  if (!live.playing) return;
  optimisticSeekTo(positionNow() + delta);
}
export function optimisticPlayPause() {
  const p = live.playing;
  if (!p) return;
  p.position = positionNow(); // freeze the clock at the current spot
  p.at = Date.now();
  p.speed = p.speed ? 0 : 1;
  // Push the new state to the lock-screen controls NOW rather than waiting for
  // the server's next broadcast (~1.5s), so pausing in the app flips the
  // notification's play/pause icon immediately.
  updateMediaSession();
}
export function optimisticSpeed(tempo) {
  if (!live.playing) return;
  live.playing.position = positionNow();
  live.playing.at = Date.now();
  live.playing.tempo = tempo;
}

export function fmtTime(secs) {
  secs = Math.max(0, Math.floor(secs));
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}
