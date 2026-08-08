<script>
  import { flushSync, onMount } from 'svelte';
  import { live, api, optimisticStep, optimisticPlayPause } from './state.svelte.js';
  import { ui } from './store.svelte.js';
  import Icon from './Icon.svelte';
  import Tracks from './Tracks.svelte';

  let showTracks = $state(false);

  // TV power toggle. `tv status` reads like "on (com.mediatek...)". Drive it with
  // the proven on/off commands off the current status (a reliable single-button
  // toggle) and flip optimistically so the blue light responds on tap. Re-read on
  // focus since the physical remote or the House page can change it behind us.
  let tvStatus = $state(null);
  let tvBusy = $state(false);
  const tvOn = $derived(!!tvStatus && tvStatus.startsWith('on'));

  function loadTv() { api('/api/tv').then((d) => (tvStatus = d.status)).catch(() => {}); }
  onMount(loadTv);
  $effect(() => { ui.focusTick; loadTv(); });

  async function tvToggle() {
    if (tvBusy) return;
    tvBusy = true;
    const turningOn = !tvOn;
    tvStatus = turningOn ? 'on' : 'off'; // optimistic
    try {
      await api(`/api/tv/${turningOn ? 'on' : 'off'}`, {});
      const d = await api('/api/tv?fresh=1');
      tvStatus = d.status;
    } catch { /* keep the optimistic state */ } finally {
      tvBusy = false;
      // The bar only answers while the set is awake, so a power change is the
      // one moment worth re-reading it outside the initial load.
      loadTvVolume();
    }
  }

  // --- TV / soundbar volume ---
  //
  // Separate knob from the Kodi mixer below: the soundbar is on eARC, so these
  // calls move the ROOM's volume while /api/volume only moves Kodi's own
  // output. Read ONCE when this tab opens - a standby TV costs the server ~3s
  // of refused sockets, which is fine as a one-off and unacceptable on a
  // timer. Nothing here can wake the set; when it is asleep the card greys out
  // and says so rather than showing an error.
  let tvVol = $state(null);
  let tvMuted = $state(false);
  let tvVolOff = $state(false);
  let tvVolLoading = $state(true);

  // Bumped by every user action. A reply from an older request is dropped, so
  // a slow round-trip can never yank the slider back under a moving thumb.
  let volSeq = 0;
  let tvVolTimer = null;

  function adoptTvVolume(d) {
    tvVolOff = !!d.off;
    if (d.off) return;
    if (Number.isFinite(d.volume)) tvVol = d.volume;
    tvMuted = !!d.muted;
  }

  function loadTvVolume() {
    tvVolLoading = true;
    const seq = ++volSeq;
    api('/api/tv/volume')
      .then((d) => { if (seq === volSeq) adoptTvVolume(d); })
      .catch(() => { if (seq === volSeq) tvVolOff = true; })
      .finally(() => { if (seq === volSeq) tvVolLoading = false; });
  }
  onMount(loadTvVolume);

  async function sendTvVolume(body, seq) {
    try {
      const d = await api('/api/tv/volume', body);
      if (seq === volSeq) adoptTvVolume(d);
    } catch { /* api() surfaces it in the error toast */ }
  }

  // Optimistic: the thumb follows the finger immediately and the POST is
  // debounced, so a full sweep is one call to the TV rather than fifty.
  function setTvVolume(ev) {
    const level = Number(ev.target.value);
    tvVol = level;
    if (tvMuted) tvMuted = false; // any set unmutes the bar
    clearTimeout(tvVolTimer);
    const seq = ++volSeq;
    tvVolTimer = setTimeout(() => sendTvVolume({ level }, seq), 150);
  }

  function toggleTvMute() {
    const next = !tvMuted;
    tvMuted = next; // optimistic
    clearTimeout(tvVolTimer);
    sendTvVolume({ action: next ? 'mute' : 'unmute' }, ++volSeq);
  }

  const input = (action) => () => api(`/api/input/${action}`, {});
  const step = (seconds) => () => { optimisticStep(seconds); api('/api/player/step', { seconds }); };
  function playpause() { optimisticPlayPause(); api('/api/player/playpause', {}); }

  let volTimer = null;
  function setVolume(ev) {
    const level = Number(ev.target.value);
    clearTimeout(volTimer);
    volTimer = setTimeout(() => api('/api/volume', { level }), 150);
  }

  // The touch surface: swipe anywhere for direction, tap for OK. A long drag
  // keeps stepping every STEP px so one slow swipe walks a whole list; taps
  // are gated by movement so a swipe never selects.
  const STEP = 52;
  let flash = $state(null);
  let pressed = $state(false);
  let start = null;
  let last = null;
  let moved = false;
  let flashTimer = null;

  function show(dir) {
    flash = dir;
    clearTimeout(flashTimer);
    flashTimer = setTimeout(() => (flash = null), 260);
    navigator.vibrate?.(8);
  }

  function fire(dx, dy) {
    const dir = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up');
    show(dir);
    api(`/api/input/${dir}`, {});
  }

  let surfaceEl;

  function padDown(ev) {
    ev.currentTarget.setPointerCapture(ev.pointerId);
    start = last = { x: ev.clientX, y: ev.clientY, t: Date.now() };
    moved = false;
    pressed = true;
  }

  // A tap picks its direction from where you touched: near an edge sends that
  // way (so the pad works as a d-pad too), the middle sends Select.
  function tapZone(ev) {
    const r = surfaceEl.getBoundingClientRect();
    const dx = (ev.clientX - r.left) / r.width - 0.5;
    const dy = (ev.clientY - r.top) / r.height - 0.5;
    if (Math.hypot(dx, dy) < 0.2) return 'ok';
    return Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up');
  }

  function padMove(ev) {
    if (!start) return;
    const dx = ev.clientX - last.x;
    const dy = ev.clientY - last.y;
    if (Math.hypot(ev.clientX - start.x, ev.clientY - start.y) > 12) moved = true;
    if (Math.hypot(dx, dy) >= STEP) {
      fire(dx, dy);
      last = { x: ev.clientX, y: ev.clientY };
    }
  }

  function padUp(ev) {
    pressed = false;
    if (!start) return;
    const quick = Date.now() - start.t < 500;
    if (!moved && quick) {
      const zone = tapZone(ev);
      show(zone);
      api(`/api/input/${zone === 'ok' ? 'select' : zone}`, {});
    }
    start = last = null;
  }

  function bigPicture() {
    if (live.playing && !confirm('Open Steam Big Picture? This takes over the TV from what is playing.')) return;
    api('/api/games/launch', { id: 'bigpicture' });
  }

  // On-demand keyboard: a floating input that types into whatever text field
  // Kodi has focused. The tick sends the text and closes.
  let kbdOpen = $state(false);
  let kbdText = $state('');
  let kbdInput;

  function openKbd() {
    kbdOpen = true;
    // Render the input NOW, still inside the tap, then focus synchronously -
    // mobile browsers only raise the on-screen keyboard from within the gesture.
    flushSync();
    kbdInput?.focus();
  }
  function sendKbd() {
    if (kbdText) api('/api/input/text', { text: kbdText, done: true });
    kbdText = '';
    kbdOpen = false;
  }
</script>

<div class="toprow">
  <button class="pwrbtn" class:on={tvOn} disabled={tvBusy} onclick={tvToggle} aria-label="TV power" aria-pressed={tvOn}>
    <Icon name="power" size={18} />
  </button>
  <button class="bigpic grow" onclick={bigPicture}>
    <Icon name="gamepad" size={18} />Big Picture
  </button>
  <button class="kbdbtn" onclick={openKbd} aria-label="Keyboard">
    <Icon name="keyboard" size={18} />
  </button>
</div>

<div
  class="surface"
  class:pressed
  bind:this={surfaceEl}
  data-nopull
  onpointerdown={padDown}
  onpointermove={padMove}
  onpointerup={padUp}
  onpointercancel={padUp}
  role="button"
  tabindex="0"
  aria-label="Touch surface. Swipe or tap an edge to move, tap the middle to select"
>
  <span class="edge up" class:lit={flash === 'up'}><Icon name="chevron-up" size={16} /></span>
  <span class="edge down" class:lit={flash === 'down'}><Icon name="chevron-down" size={16} /></span>
  <span class="edge left" class:lit={flash === 'left'}><Icon name="chevron-left" size={16} /></span>
  <span class="edge right" class:lit={flash === 'right'}><Icon name="chevron-right" size={16} /></span>
  <span class="center" class:lit={flash === 'ok'}></span>
</div>
<p class="dim small hint">Swipe or tap an edge, middle to select</p>

<div class="roundrow">
  <div class="rbtn-wrap">
    <button class="rbtn" onclick={input('back')} aria-label="Back"><Icon name="back" size={20} /></button>
    <span>Back</span>
  </div>
  <div class="rbtn-wrap">
    <button class="rbtn" onclick={input('home')} aria-label="Home"><Icon name="home" size={20} /></button>
    <span>Home</span>
  </div>
  <div class="rbtn-wrap">
    <button class="rbtn" onclick={input('context')} aria-label="Menu"><Icon name="dots" size={20} /></button>
    <span>Menu</span>
  </div>
  <div class="rbtn-wrap">
    <button class="rbtn" onclick={input('osd')} aria-label="On-screen controls"><Icon name="sliders" size={20} /></button>
    <span>OSD</span>
  </div>
</div>

<div class="card">
  <div class="transport">
    <button class="tbtn" onclick={() => api('/api/player/previous', {})} disabled={!live.playing} aria-label="Previous"><Icon name="prev" size={18} /></button>
    <button class="tbtn seek" onclick={step(-10)} disabled={!live.playing} aria-label="Back 10 seconds">
      <Icon name="rotate-ccw" size={18} /><span class="mono">10</span>
    </button>
    <button class="tbtn main" class:primary={!!live.playing} onclick={playpause} disabled={!live.playing} aria-label="Play or pause">
      <Icon name={live.playing && live.playing.speed ? 'pause' : 'play'} size={22} />
    </button>
    <button class="tbtn seek" onclick={step(30)} disabled={!live.playing} aria-label="Forward 30 seconds">
      <Icon name="rotate-cw" size={18} /><span class="mono">30</span>
    </button>
    <button class="tbtn" onclick={() => api('/api/player/next', {})} disabled={!live.playing} aria-label="Next"><Icon name="next" size={18} /></button>
  </div>
  <div class="row navrow">
    <button class="grow" onclick={() => api('/api/player/skip-intro', {})} disabled={!live.playing}>Skip intro</button>
    <button class="grow" onclick={() => (showTracks = true)} disabled={!live.playing}>Tracks</button>
    <button class="grow" onclick={() => { if (confirm('Stop playback?')) api('/api/player/stop', {}); }} disabled={!live.playing}><Icon name="stop" size={15} />Stop</button>
  </div>
</div>

<div class="card">
  <h2>Kodi volume</h2>
  <div class="row">
    <button class="mutebtn" class:primary={live.muted} onclick={() => api('/api/volume', { mute: !live.muted })}>
      {live.muted ? 'Unmute' : 'Mute'}
    </button>
    <input class="grow" type="range" min="0" max="100" value={live.volume ?? 0} oninput={setVolume} disabled={live.volume === null} aria-label="Volume" />
    <span class="mono vol dim">{live.volume ?? '--'}</span>
  </div>
</div>

<div class="card" class:asleep={tvVolOff && !tvVolLoading}>
  <h2>
    <Icon name="speaker" size={14} />TV &amp; soundbar
    {#if tvVolLoading}<span class="tag">reading…</span>
    {:else if tvVolOff}<span class="tag">TV off</span>{/if}
  </h2>
  <div class="row">
    <button
      class="mutebtn"
      class:primary={tvMuted && !tvVolOff}
      onclick={toggleTvMute}
      disabled={tvVolOff || tvVolLoading}
    >
      {tvMuted && !tvVolOff ? 'Unmute' : 'Mute'}
    </button>
    <input
      class="grow"
      type="range"
      min="0"
      max="100"
      value={tvVol ?? 0}
      oninput={setTvVolume}
      disabled={tvVolOff || tvVolLoading}
      aria-label="TV and soundbar volume"
    />
    <span class="mono vol dim">{tvVolOff || tvVol === null ? '--' : tvVol}</span>
  </div>
</div>

{#if showTracks}
  <Tracks onclose={() => (showTracks = false)} />
{/if}

{#if kbdOpen}
  <div class="kbd-scrim" onclick={() => (kbdOpen = false)} role="presentation"></div>
  <div class="kbd-bar">
    <input
      bind:this={kbdInput}
      bind:value={kbdText}
      type="text"
      placeholder="Type on the TV"
      autocomplete="off"
      autocapitalize="off"
      spellcheck="false"
      onkeydown={(e) => e.key === 'Enter' && sendKbd()}
    />
    <button class="kbd-tick primary" onclick={sendKbd} aria-label="Send"><Icon name="check" size={20} /></button>
  </div>
{/if}

<style>
  .toprow { display: flex; gap: 8px; margin-bottom: 12px; }
  .bigpic { padding: 12px; color: var(--ink); }
  .kbdbtn { width: 52px; padding: 0; justify-content: center; color: var(--ink); }
  .pwrbtn {
    width: 52px;
    padding: 0;
    justify-content: center;
    color: var(--ink);
    transition: background 0.2s ease, color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
  }
  .pwrbtn.on {
    color: #fff;
    background: #2f81f7;
    border-color: #2f81f7;
    box-shadow: 0 0 0 1px #2f81f7, 0 0 18px rgba(47, 129, 247, 0.55);
  }
  .pwrbtn:disabled { opacity: 0.55; }

  .kbd-scrim { position: fixed; inset: 0; z-index: 25; }
  .kbd-bar {
    position: fixed;
    left: 10px; right: 10px;
    bottom: calc(var(--tabbar) + env(safe-area-inset-bottom) + 8px);
    display: flex;
    gap: 8px;
    z-index: 26;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 8px;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4);
  }
  .kbd-bar input { flex: 1; }
  .kbd-tick { width: 48px; padding: 0; justify-content: center; flex-shrink: 0; }

  /* The one bold element: a tall glass slab that is all touch surface. */
  .surface {
    position: relative;
    height: 290px;
    border-radius: 24px;
    background: linear-gradient(180deg, var(--raise), var(--card) 78%);
    border: 1px solid var(--line);
    touch-action: none;
    cursor: pointer;
    user-select: none;
    transition: box-shadow 0.18s ease;
  }
  .surface.pressed { box-shadow: inset 0 0 0 2px var(--accent), inset 0 0 44px var(--accent-tint); }

  .edge {
    position: absolute;
    color: var(--faint);
    display: flex;
    transition: color 0.1s ease, transform 0.15s ease;
  }
  .edge.up { top: 14px; left: 50%; transform: translateX(-50%); }
  .edge.down { bottom: 14px; left: 50%; transform: translateX(-50%); }
  .edge.left { left: 16px; top: 50%; transform: translateY(-50%); }
  .edge.right { right: 16px; top: 50%; transform: translateY(-50%); }
  .edge.lit { color: var(--accent); }
  .edge.up.lit { transform: translateX(-50%) translateY(-3px); }
  .edge.down.lit { transform: translateX(-50%) translateY(3px); }
  .edge.left.lit { transform: translateY(-50%) translateX(-3px); }
  .edge.right.lit { transform: translateY(-50%) translateX(3px); }

  .center {
    position: absolute;
    top: 50%; left: 50%;
    width: 10px; height: 10px;
    margin: -5px 0 0 -5px;
    border-radius: 50%;
    background: var(--faint);
    opacity: 0.6;
    transition: background 0.12s ease, box-shadow 0.12s ease;
  }
  .center.lit { background: var(--accent); opacity: 1; box-shadow: 0 0 14px var(--accent); }

  .hint { text-align: center; margin: 10px 0 14px; }

  .roundrow {
    display: flex;
    justify-content: space-evenly;
    margin-bottom: 16px;
  }
  .rbtn-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
  }
  .rbtn-wrap > span { font-size: 11px; color: var(--faint); }
  .rbtn {
    width: 58px; height: 58px;
    border-radius: 50%;
    padding: 0;
    justify-content: center;
    color: var(--ink);
  }

  .transport {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }
  .tbtn {
    width: 52px; height: 52px;
    padding: 0;
    border-radius: 50%;
    justify-content: center;
  }
  .tbtn.seek { gap: 3px; font-size: 10px; width: 60px; }
  .tbtn.seek .mono { font-size: 10px; }
  .tbtn.main { width: 64px; height: 64px; }

  .navrow button { font-size: 14px; }

  .mutebtn { min-width: 84px; }
  .vol { width: 30px; text-align: right; font-size: 13px; }

  /* A standby TV is not an error, so the card recedes rather than shouting:
     the controls grey out and the heading says why. */
  .card h2 { display: flex; align-items: center; gap: 6px; }
  .card.asleep { opacity: 0.6; }
  .tag {
    margin-left: auto;
    font-size: 11px;
    font-weight: 500;
    color: var(--faint);
    background: var(--raise);
    border-radius: 999px;
    padding: 2px 8px;
  }
</style>
