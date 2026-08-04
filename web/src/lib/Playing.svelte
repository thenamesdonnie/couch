<script>
  import { onMount } from 'svelte';
  import { live, api, positionNow, fmtTime, optimisticSeekTo, optimisticStep, optimisticPlayPause, optimisticSpeed } from './state.svelte.js';
  import Icon from './Icon.svelte';
  import { fadeimg } from './img.js';
  import Tracks from './Tracks.svelte';

  let showTracks = $state(false);
  let now = $state(Date.now());
  let scrubbing = $state(false);
  let scrubPct = $state(0);

  onMount(() => {
    const t = setInterval(() => (now = Date.now()), 1000);
    return () => clearInterval(t);
  });

  const p = $derived(live.playing);
  const pos = $derived((now, p ? positionNow() : 0));
  const pct = $derived(p && p.duration ? (pos / p.duration) * 100 : 0);
  // While dragging show the finger's position; otherwise the live playback pos.
  const displayPct = $derived(scrubbing ? scrubPct : pct);

  // Custom pointer-driven scrubber. A native <input type=range> was the problem:
  // it has no touch-action so a vertical wobble scrolled the page instead of
  // seeking, its thumb is a tiny target, and its value is rewritten every second
  // from the playback clock, which fights your finger. This owns the pointer
  // (setPointerCapture), moves optimistically, and never fights the clock.
  const pctAt = (ev, el) => {
    const r = el.getBoundingClientRect();
    return Math.max(0, Math.min(100, ((ev.clientX - r.left) / r.width) * 100));
  };

  // Throttle live seeks so the TV scrubs ALONG with the drag (watch as you seek)
  // without flooding Kodi - one seek per window, using the latest position.
  let liveTimer = null;
  function liveSeek() {
    if (liveTimer) return;
    liveTimer = setTimeout(() => {
      liveTimer = null;
      if (scrubbing) api('/api/player/seek', { percentage: scrubPct });
    }, 200);
  }

  function seekDown(ev) {
    if (!p?.duration) return;
    ev.currentTarget.setPointerCapture(ev.pointerId);
    scrubbing = true;
    scrubPct = pctAt(ev, ev.currentTarget);
    liveSeek();
  }
  function seekMove(ev) {
    if (!scrubbing) return;
    scrubPct = pctAt(ev, ev.currentTarget);
    liveSeek();
  }
  function seekUp(ev) {
    if (!scrubbing) return;
    scrubPct = pctAt(ev, ev.currentTarget);
    scrubbing = false;
    if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
    // Hold the scrubbed spot optimistically so the bar doesn't snap back to the
    // old position for the second before the server confirms.
    optimisticSeekTo((scrubPct / 100) * (p?.duration || 0));
    api('/api/player/seek', { percentage: scrubPct });
  }

  const step = (seconds) => () => { optimisticStep(seconds); api('/api/player/step', { seconds }); };
  function playpause() { optimisticPlayPause(); api('/api/player/playpause', {}); }

  // Volume, matching the Remote page: debounce the server call so a drag does
  // not flood it, but the slider itself moves instantly.
  let volTimer = null;
  function setVolume(ev) {
    const level = Number(ev.target.value);
    clearTimeout(volTimer);
    volTimer = setTimeout(() => api('/api/volume', { level }), 150);
  }

  const SPEEDS = [1, 1.25, 1.5, 2];
  const fmtX = (s) => (s === 1 ? '1x' : s + 'x');
  function setSpeed(s) { optimisticSpeed(s); api('/api/player/speed', { speed: s }); }

  const subtitle = $derived(
    p?.type === 'episode' && p.showtitle
      ? `${p.showtitle} · S${String(p.season).padStart(2, '0')}E${String(p.episode).padStart(2, '0')}`
      : p?.year ? String(p.year) : ''
  );
</script>

{#if !p}
  <div class="card empty">
    <p class="dim">Nothing is playing on the TV.</p>
    <p class="dim small">Pick something in the Library, or start a game from Games.</p>
  </div>
{:else}
  {#if p.art.fanart}
    <div class="backdrop backdrop-in" style:background-image={'url(/api/art/kodi?p=' + encodeURIComponent(p.art.fanart) + ')'}></div>
    <div class="backdrop-fade"></div>
  {/if}

  <div class="hero">
    {#if p.art.poster}
      <img class="poster" use:fadeimg src={'/api/art/kodi?p=' + encodeURIComponent(p.art.poster)} alt="" />
    {/if}
    <div class="titles">
      <div class="title display">{p.title}</div>
      {#if subtitle}<div class="sub dim">{subtitle}</div>{/if}
      <div class="state" class:pausedstate={!p.speed}>
        <Icon name={p.speed ? 'play' : 'pause'} size={12} />
        {p.speed ? (p.speed !== 1 ? `${p.speed}x` : 'Playing') : 'Paused'}
      </div>
    </div>
  </div>

  <div class="panel">
    <div
      class="seekbar"
      class:dragging={scrubbing}
      onpointerdown={seekDown}
      onpointermove={seekMove}
      onpointerup={seekUp}
      onpointercancel={seekUp}
      role="slider"
      tabindex="0"
      aria-label="Seek"
      aria-valuemin="0"
      aria-valuemax="100"
      aria-valuenow={Math.round(displayPct)}
    >
      <div class="seektrack">
        <div class="seekfill" style:width={displayPct + '%'}></div>
        <div class="seekthumb" style:left={displayPct + '%'}></div>
      </div>
    </div>
    <div class="row times mono small">
      <span>{fmtTime(scrubbing ? (scrubPct / 100) * p.duration : pos)}</span>
      <span class="grow"></span>
      <span class="dim">{fmtTime(p.duration)}</span>
    </div>
    <div class="transport">
      <button class="tbtn seek" onclick={step(-10)} aria-label="Back 10 seconds">
        <Icon name="rotate-ccw" size={18} /><span class="mono">10</span>
      </button>
      <button class="tbtn main primary" onclick={playpause} aria-label="Play or pause">
        <Icon name={p.speed ? 'pause' : 'play'} size={24} />
      </button>
      <button class="tbtn seek" onclick={step(30)} aria-label="Forward 30 seconds">
        <Icon name="rotate-cw" size={18} /><span class="mono">30</span>
      </button>
    </div>
    <div class="row navrow">
      <button class="grow" onclick={() => api('/api/player/skip-intro', {})}>Skip intro</button>
      <button class="grow" onclick={() => (showTracks = true)}>Tracks</button>
      <button class="grow danger" onclick={() => { if (confirm('Stop playback?')) api('/api/player/stop', {}); }}><Icon name="stop" size={15} />Stop</button>
    </div>
    <div class="row volrow">
      <button class="mutebtn" class:primary={live.muted} onclick={() => api('/api/volume', { mute: !live.muted })}>
        {live.muted ? 'Unmute' : 'Mute'}
      </button>
      <input class="grow" type="range" min="0" max="100" value={live.volume ?? 0} oninput={setVolume} disabled={live.volume === null} aria-label="Volume" />
      <span class="mono vol dim">{live.volume ?? '--'}</span>
    </div>
    <div class="speedrow">
      <span class="small dim">Speed</span>
      <div class="seg speedseg">
        {#each SPEEDS as s}
          <button class:on={(p.tempo || 1) === s} onclick={() => setSpeed(s)}>{fmtX(s)}</button>
        {/each}
      </div>
    </div>
  </div>
{/if}

{#if showTracks}
  <Tracks onclose={() => (showTracks = false)} />
{/if}

<style>
  .empty { text-align: center; padding: 40px 20px; }

  /* The artwork is the interface: fanart floods the top and fades into the
     ground before the controls. */
  .backdrop {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 48dvh;
    background-size: cover;
    background-position: center 25%;
    z-index: -2;
  }
  .backdrop-in { animation: bgfade 0.5s ease both; }
  @keyframes bgfade { from { opacity: 0; } to { opacity: 1; } }
  .backdrop-fade {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 48dvh;
    background: linear-gradient(180deg,
      color-mix(in srgb, var(--bg) 45%, transparent) 0%,
      color-mix(in srgb, var(--bg) 25%, transparent) 45%,
      var(--bg) 96%);
    z-index: -1;
  }

  .hero {
    display: flex;
    gap: 16px;
    align-items: flex-end;
    margin: 13dvh 2px 18px;
  }
  .poster {
    width: 116px;
    aspect-ratio: 2 / 3;
    object-fit: cover;
    border-radius: 14px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
  }
  .titles { flex: 1; min-width: 0; padding-bottom: 2px; }
  .title { font-size: 25px; line-height: 1.08; text-wrap: balance; }
  .sub { margin-top: 5px; font-size: 14px; }
  .state {
    margin-top: 10px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    color: var(--accent);
    background: var(--accent-tint);
    border-radius: 999px;
    padding: 4px 11px;
  }
  .state.pausedstate { color: var(--muted); background: var(--raise); }

  .panel {
    background: color-mix(in srgb, var(--card) 82%, transparent);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 16px 14px 14px;
  }
  /* Custom seek bar. The padding makes a tall, easy-to-grab touch target around
     a thin visual track; touch-action:none is what stops a drag from scrolling
     the page (it must be set in CSS, before the gesture starts). */
  .seekbar {
    position: relative;
    padding: 15px 0;
    margin: 0 2px;
    touch-action: none;
    cursor: pointer;
    user-select: none;
    -webkit-user-select: none;
  }
  .seektrack {
    position: relative;
    height: 6px;
    border-radius: 999px;
    background: var(--raise);
  }
  .seekfill {
    position: absolute;
    top: 0; left: 0; bottom: 0;
    border-radius: 999px;
    background: var(--accent);
  }
  .seekthumb {
    position: absolute;
    top: 50%;
    width: 16px; height: 16px;
    margin: -8px 0 0 -8px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.45);
  }
  /* Smooth the ~1s clock ticks during playback, but never while dragging - the
     thumb must track the finger instantly. */
  .seekbar:not(.dragging) .seekfill { transition: width 1s linear; }
  .seekbar:not(.dragging) .seekthumb { transition: left 1s linear; }
  .seekbar.dragging .seekthumb { transform: scale(1.35); }

  .times { margin: 2px 2px 12px; }

  .transport {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 14px;
    margin-bottom: 14px;
  }
  .tbtn { border-radius: 50%; padding: 0; justify-content: center; }
  .tbtn.seek { width: 58px; height: 58px; gap: 3px; }
  .tbtn.seek .mono { font-size: 10px; }
  .tbtn.main { width: 68px; height: 68px; }

  .navrow button { font-size: 14px; }
  .volrow { margin-top: 12px; }
  .mutebtn { min-width: 84px; }
  .vol { width: 30px; text-align: right; font-size: 13px; }
  .speedrow { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
  .speedseg { flex: 1; }
  .speedseg button { flex: 1; font-size: 13px; padding: 7px; }
</style>
