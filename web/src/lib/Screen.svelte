<script>
  import { slideUp, fadeIn, slideDown, fadeOut } from './anim.js';
  import { portal } from './portal.js';
  import { onMount, flushSync } from 'svelte';
  import { api } from './state.svelte.js';
  import Icon from './Icon.svelte';

  let src = $state('auto');
  let live = $state(true);
  let streamUrl = $state(null);
  let clicking = $state(false);
  let marker = $state(null);
  let kbd = $state(false);
  let kbdInput = $state(null);

  // Zoom and pan state; transforms apply to the image, taps map through its
  // on-screen rect so zoom never changes the click maths.
  let scale = $state(1);
  let tx = $state(0);
  let ty = $state(0);

  let frame; // the clipping viewport element
  let img;

  let gen = 0;
  function startStream() {
    gen++;
    streamUrl = `/api/screen/stream?src=${src}&g=${gen}`;
  }
  function stopStream() {
    streamUrl = null;
  }

  onMount(() => {
    startStream();
    return stopStream;
  });

  $effect(() => {
    src;
    if (live) startStream();
  });

  function toggleLive() {
    live = !live;
    if (live) startStream();
    else stopStream();
  }

  // If the stream drops (server restart, error), come back gently.
  let retryTimer = null;
  function onImgError() {
    clearTimeout(retryTimer);
    if (live) retryTimer = setTimeout(startStream, 2000);
  }

  // --- gestures: 1-finger tap = click, 1-finger drag (zoomed) = pan,
  // 2-finger pinch = zoom. A drag or pinch never clicks.
  const pointers = new Map();
  let gesture = null;

  function clampPan() {
    const limX = (frame.clientWidth * (scale - 1)) / 2;
    const limY = (frame.clientHeight * (scale - 1)) / 2;
    tx = Math.max(-limX, Math.min(limX, tx));
    ty = Math.max(-limY, Math.min(limY, ty));
  }

  function down(ev) {
    ev.preventDefault();
    frame.setPointerCapture(ev.pointerId);
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (pointers.size === 1) {
      gesture = { kind: 'tap', startX: ev.clientX, startY: ev.clientY, startTx: tx, startTy: ty, t: Date.now() };
    } else if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      gesture = {
        kind: 'pinch',
        startDist: Math.hypot(a.x - b.x, a.y - b.y),
        startScale: scale,
        startTx: tx, startTy: ty,
      };
    }
  }

  function move(ev) {
    if (!pointers.has(ev.pointerId)) return;
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (!gesture) return;
    if (gesture.kind === 'pinch' && pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      scale = Math.max(1, Math.min(5, gesture.startScale * (dist / gesture.startDist)));
      clampPan();
    } else if (pointers.size === 1) {
      const dx = ev.clientX - gesture.startX;
      const dy = ev.clientY - gesture.startY;
      if (gesture.kind === 'tap' && Math.hypot(dx, dy) > 12) gesture.kind = scale > 1 ? 'pan' : 'swipe';
      if (gesture.kind === 'pan') {
        tx = gesture.startTx + dx;
        ty = gesture.startTy + dy;
        clampPan();
      }
    }
  }

  function up(ev) {
    const wasTap = gesture?.kind === 'tap' && pointers.size === 1 && Date.now() - gesture.t < 500;
    pointers.delete(ev.pointerId);
    if (pointers.size === 0) {
      const g = gesture;
      gesture = null;
      if (wasTap) tap(ev, g);
    } else if (pointers.size === 1) {
      // Pinch ended with one finger still down; treat the remainder as a pan.
      const p = [...pointers.values()][0];
      gesture = { kind: 'pan', startX: p.x, startY: p.y, startTx: tx, startTy: ty, t: Date.now() };
    }
  }

  async function tap(ev, g) {
    const rect = img.getBoundingClientRect();
    const x = (ev.clientX - rect.left) / rect.width;
    const y = (ev.clientY - rect.top) / rect.height;
    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    marker = { left: ev.clientX, top: ev.clientY };
    clicking = true;
    try {
      const res = await api('/api/screen/click', { x, y });
      if (res.text) openKeyboard();
    } finally {
      clicking = false;
      setTimeout(() => (marker = null), 600);
    }
  }

  function resetZoom() { scale = 1; tx = 0; ty = 0; }
  function zoomTo(s) {
    scale = s;
    clampPan();
  }

  // --- live keyboard: every keystroke relays immediately, so typing on the
  // phone is typing on the box. beforeinput carries intent even from mobile
  // keyboards; the field itself stays empty.
  function openKeyboard() {
    kbd = true;
    // Render + focus synchronously so a tap on Show raises the keyboard. When
    // called from the click-detected-a-text-box path it is not a gesture, so
    // the keyboard may not rise then - the field still focuses and one tap on
    // it opens the keyboard.
    flushSync();
    kbdInput?.focus();
  }

  function onBeforeInput(ev) {
    ev.preventDefault();
    if (ev.inputType === 'insertText' && ev.data) api('/api/screen/type', { text: ev.data });
    else if (ev.inputType === 'deleteContentBackward') api('/api/screen/key', { key: 'BackSpace' });
    else if (ev.inputType === 'insertLineBreak') api('/api/screen/key', { key: 'Return' });
  }

  function onKbdKeydown(ev) {
    if (ev.key === 'Enter') { ev.preventDefault(); api('/api/screen/key', { key: 'Return' }); }
    else if (ev.key === 'Backspace' && !ev.isComposing) { ev.preventDefault(); api('/api/screen/key', { key: 'BackSpace' }); }
  }

  const key = (k) => () => api('/api/screen/key', { key: k });

  // --- couchd: three lines from the shadow daemon's status file.
  // Raw fetch, not api(): couchd is stopped whenever we like, so a poll that
  // finds nothing must not raise the error toast. ok:false is a normal answer
  // and collapses the card to one dim line.
  let couchd = $state(null);

  async function loadCouchd() {
    try {
      const res = await fetch('/api/couchd/status', { cache: 'no-store' });
      if (res.ok) couchd = await res.json();
    } catch { /* keep the last reading */ }
  }

  onMount(() => {
    loadCouchd();
    const t = setInterval(() => {
      if (document.visibilityState === 'visible') loadCouchd();
    }, 5000);
    return () => clearInterval(t);
  });

  const regions = $derived(couchd?.regions ?? {});
  const regionLine = $derived(
    `pad ${regions.pad ?? '?'} · session ${regions.session ?? '?'} · gesture ${regions.gesture ?? '?'}`,
  );
  // A source that is not ok (or has gone quiet) degrades the daemon without
  // stopping it, so it is named rather than alarmed about.
  const sickObservers = $derived(
    Object.entries(couchd?.observers ?? {})
      .filter(([, o]) => !o.ok || o.stale)
      .map(([name]) => name),
  );
  const wouldDo = $derived(couchd?.wouldDo?.[0] ?? '');

  // Window switcher: list the open windows and jump to one, plus quick Kodi and
  // show-desktop actions.
  let winOpen = $state(false);
  let wins = $state([]);
  async function openWindows() {
    winOpen = true;
    try { wins = (await api('/api/windows')).windows; } catch { wins = []; }
  }
  async function activate(id) {
    winOpen = false;
    // A window switch means the desktop/game source; nudge to that so the view
    // follows, and restart the stream to pick up the newly-raised window.
    await api('/api/windows/activate', { id });
    if (id !== 'kodi') src = 'x';
    else src = 'auto';
    if (live) setTimeout(startStream, 400);
  }
</script>

<div class="card">
  <div class="row head">
    <div class="seg">
      <button class:on={src === 'auto'} onclick={() => (src = 'auto')}>Auto</button>
      <button class:on={src === 'kodi'} onclick={() => (src = 'kodi')}>Kodi</button>
      <button class:on={src === 'x'} onclick={() => (src = 'x')}>Desktop</button>
    </div>
    <span class="grow"></span>
    <button class="winbtn" onclick={openWindows} aria-label="Switch window"><Icon name="library" size={17} /></button>
    <button class:primary={live} onclick={toggleLive}>{live ? 'Live' : 'Paused'}</button>
  </div>

  <div
    class="frame"
    data-nopull
    bind:this={frame}
    onpointerdown={down}
    onpointermove={move}
    onpointerup={up}
    onpointercancel={up}
  >
    {#if streamUrl}
      <!-- Keyed so a source switch tears the element down and builds a fresh
           one; reusing the element left Safari holding the old MJPEG socket. -->
      {#key streamUrl}
        <img
          bind:this={img}
          src={streamUrl}
          alt="What the TV is showing"
          onerror={onImgError}
          style:transform={`translate(${tx}px, ${ty}px) scale(${scale})`}
          draggable="false"
        />
      {/key}
    {:else}
      <div class="paused dim small">Paused</div>
    {/if}
  </div>
  {#if marker}
    <span class="ripple" style:left={marker.left + 'px'} style:top={marker.top + 'px'}></span>
  {/if}

  <div class="row zoomrow">
    <button onclick={() => zoomTo(Math.max(1, scale - 1))} disabled={scale <= 1}><Icon name="minus" size={16} /></button>
    <button onclick={() => zoomTo(Math.min(5, scale + 1))} disabled={scale >= 5}><Icon name="plus" size={16} /></button>
    <button onclick={resetZoom} disabled={scale === 1}><Icon name="fit" size={16} /></button>
    <span class="grow"></span>
    <span class="dim small">{scale > 1 ? scale.toFixed(1) + 'x · drag to pan' : 'Pinch to zoom, tap to click'}</span>
  </div>
</div>

<div class="card">
  <div class="row">
    <h2 class="grow" style="margin:0">Keyboard</h2>
    <button class:primary={kbd} onclick={() => { kbd ? (kbd = false) : openKeyboard(); }}>{kbd ? 'Hide' : 'Show'}</button>
  </div>
  {#if kbd}
    <input
      bind:this={kbdInput}
      type="text"
      class="kbd"
      placeholder="Keys go straight to the box"
      autocomplete="off"
      autocapitalize="off"
      spellcheck="false"
      onbeforeinput={onBeforeInput}
      onkeydown={onKbdKeydown}
    />
    <div class="row keys">
      <button class="grow" onclick={key('Escape')}>Esc</button>
      <button class="grow" onclick={key('Tab')}>Tab</button>
      <button class="grow" onclick={key('BackSpace')}><Icon name="backspace" size={16} /></button>
      <button class="grow" onclick={key('Return')}>Enter</button>
    </div>
  {:else}
    <p class="dim small hint">Tapping a text box on screen opens this automatically.</p>
  {/if}
</div>

{#if couchd}
  <div class="card cd">
    {#if !couchd.ok}
      <p class="small dim cdline">{couchd.reason}</p>
    {:else}
      <h2>couchd</h2>
      <p class="small mono dim cdline">{regionLine}</p>
      <p class="small cdline" class:warn={sickObservers.length} class:dim={!sickObservers.length}>
        {sickObservers.length ? `observers: ${sickObservers.join(', ')}` : 'observers: all ok'}
      </p>
      <p class="small cdline" class:dim={!wouldDo}>{wouldDo || 'no would-do yet'}</p>
    {/if}
  </div>
{/if}

{#if winOpen}
  <div use:portal use:fadeIn out:fadeOut class="scrim" onclick={() => (winOpen = false)} role="presentation">
    <div use:slideUp out:slideDown class="sheet" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Switch window">
      <div class="sheetbar">
        <span class="sheettitle">Switch to</span>
        <button class="closebtn" onclick={() => (winOpen = false)} aria-label="Close"><Icon name="x" size={16} /></button>
      </div>
      <div class="winlist">
        <button class="winrow" onclick={() => activate('kodi')}>
          <Icon name="home" size={18} /><span class="grow">Kodi</span><Icon name="chevron-right" size={16} />
        </button>
        <!-- Kodi and the desktop have their own rows above and below; the
             desktop arrives in the list too now (the on-TV switcher renders
             the list verbatim), so it is filtered out here rather than
             appearing twice. -->
        {#each wins.filter((w) => !w.kodi && w.id !== 'desktop') as w (w.id)}
          <button class="winrow" onclick={() => activate(w.id)}>
            <Icon name="screen" size={18} /><span class="grow wintitle">{w.title}</span><Icon name="chevron-right" size={16} />
          </button>
        {/each}
        <button class="winrow" onclick={() => activate('desktop')}>
          <Icon name="sliders" size={18} /><span class="grow">Show desktop</span>
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .head { margin-bottom: 10px; }
  .winbtn { width: 42px; padding: 0; justify-content: center; color: var(--ink); }

  .scrim { position: fixed; inset: 0; background: var(--scrim); z-index: 20; display: flex; align-items: flex-end; }
  .sheet {
    background: var(--card);
    border-radius: 22px 22px 0 0;
    padding: 0 16px max(18px, env(safe-area-inset-bottom));
    width: 100%;
    max-height: 75dvh;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .sheetbar {
    position: sticky; top: 0; z-index: 2;
    display: flex; align-items: center; gap: 10px;
    margin: 0 -16px 8px; padding: 14px 16px 10px;
    background: var(--card);
  }
  .sheettitle { flex: 1; font-weight: 600; }
  .closebtn { width: 34px; height: 34px; padding: 0; border-radius: 50%; justify-content: center; color: var(--muted); }
  .winlist { display: flex; flex-direction: column; gap: 6px; }
  .winrow { justify-content: flex-start; gap: 12px; text-align: left; color: var(--ink); }
  .winrow :global(svg):first-child { color: var(--muted); }
  .wintitle { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .seg button { padding: 8px 12px; }

  .frame {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: #000;
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
    touch-action: none;
    cursor: crosshair;
  }
  .frame img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
    transform-origin: center;
    user-select: none;
    -webkit-user-drag: none;
  }
  .paused {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
  }

  .ripple {
    position: fixed;
    width: 26px; height: 26px;
    margin: -13px 0 0 -13px;
    border: 2px solid var(--accent);
    border-radius: 50%;
    pointer-events: none;
    z-index: 40;
    animation: pop 0.5s ease-out;
  }
  @keyframes pop {
    from { transform: scale(0.4); opacity: 1; }
    to { transform: scale(1.4); opacity: 0; }
  }

  .cd p:last-child { margin-bottom: 0; }
  .cdline { margin: 0 0 5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .warn { color: var(--warn); }

  .zoomrow { margin-top: 10px; }
  .kbd { margin: 10px 0 8px; }
  .keys { margin-top: 0; }
  .hint { margin: 8px 0 0; }
</style>
