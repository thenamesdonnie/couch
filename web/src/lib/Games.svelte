<script>
  import { live, api } from './state.svelte.js';
  import { ui, cache, loadGames, loadSteamLib } from './store.svelte.js';
  import { fadeimg } from './img.js';
  import { fadeIn, fadeOut, slideDown, slideUp } from './anim.js';
  import { dragDismiss } from './drag.js';
  import { portal } from './portal.js';
  import { reducedMotion } from './reduced-motion.js';
  import Icon from './Icon.svelte';
  import Pip from './Pip.svelte';

  let view = $state('box'); // box | library
  // Both lists live in the shared cache: the tab paints instantly from the
  // last visit and the store's focus/poll revalidation keeps them fresh.
  const games = $derived(cache.games ?? []);        // on-the-box games (Steam installed + PS4 + apps)
  const loaded = $derived(cache.games !== null);
  const steamLib = $derived(cache.steamLib ?? []);  // full owned Steam library
  const steamLoaded = $derived(cache.steamLib !== null);
  let downloads = $state([]);
  let installing = $state(new Set());

  async function loadDownloads() {
    try {
      const res = await fetch('/api/steam/downloads');
      if (res.ok) downloads = (await res.json()).downloads;
    } catch { /* leave empty */ }
  }

  // Cold caches fill on first visit; afterwards revalidation is the store's
  // job. Downloads stay local and poll a touch faster so progress moves.
  $effect(() => {
    ui.focusTick; ui.pollTick;
    if (!cache.games) loadGames().catch(() => {});
    if (cache.steamLib === null) loadSteamLib();
    loadDownloads();
  });
  $effect(() => {
    const t = setInterval(loadDownloads, 6000);
    return () => clearInterval(t);
  });

  const pausedId = $derived(live.game.suspended);
  function isPaused(g) {
    if (!pausedId) return false;
    if (g.id === pausedId) return true;
    if (g.kind === 'ps4' && pausedId.startsWith('ps4:')) return g.id === pausedId;
    return false;
  }

  // Games with cheat support open an options sheet instead of launching on
  // tap, so the cheats are reachable without a keyboard at the television.
  let sheet = $state(null);        // the game whose sheet is open
  let cheats = $state(null);       // null while loading
  let cheatNote = $state('');
  let busy = $state(new Set());    // cheat names mid-toggle

  async function loadCheats() {
    cheats = null;
    try { cheats = await api('/api/games/cheats'); } catch { cheats = { cheats: [] }; }
  }

  function openSheet(g) {
    sheet = g;
    cheatNote = '';
    loadCheats();
  }

  // A cheat is "on" if it is live in the running game, or armed for the next
  // launch when nothing is running. Those are the same switch to the player.
  function cheatOn(c) {
    return c.live ? c.live === 'on' : c.boot;
  }

  async function toggleCheat(c) {
    if (busy.has(c.name)) return;
    busy = new Set(busy).add(c.name);
    cheatNote = '';
    try {
      const res = await api('/api/games/cheats', { name: c.name, on: !cheatOn(c) });
      cheatNote = res.note || '';
    } catch (e) {
      cheatNote = String(e.message || e);
    } finally {
      busy = new Set([...busy].filter((n) => n !== c.name));
      await loadCheats();
    }
  }

  async function launch(g) {
    if (isPaused(g)) { await api('/api/games/resume', {}); sheet = null; return; }
    if (live.game.active && !confirm(`A game session is already running. Launch ${g.name} anyway?`)) return;
    await api('/api/games/launch', { id: g.id });
    sheet = null;
  }

  // Always the sheet for a cheat game, paused or not: mid-session is exactly
  // when you want to reach for a cheat, so hiding it behind "resume" would
  // defeat the point. The sheet's own button does the resuming.
  async function tap(g) {
    if (g.cheats) { openSheet(g); return; }
    await launch(g);
  }

  // Steam library tile: launch if installed, else download.
  async function steamTap(g) {
    if (g.state === 'installed') {
      if (live.game.active && !confirm(`A game session is already running. Launch ${g.name} anyway?`)) return;
      await api('/api/games/launch', { id: String(g.appid) });
    } else if (g.state === 'downloading' || g.state === 'queued') {
      // already coming down; nothing to do
    } else {
      const verb = g.state === 'paused' ? 'Resume' : 'Download';
      if (!confirm(`${verb} ${g.name}?`)) return;
      installing = new Set([...installing, g.appid]);
      try {
        await api('/api/steam/install', { appid: g.appid });
        setTimeout(() => { loadSteamLib(); loadDownloads(); }, 2500);
      } finally {
        setTimeout(() => { installing.delete(g.appid); installing = new Set(installing); }, 2500);
      }
    }
  }

  const stateLabel = { installed: 'Installed', downloading: 'Downloading', queued: 'Queued', paused: 'Paused', notinstalled: '' };
  const fmtGB = (b) => (b / 1e9).toFixed(1) + ' GB';
</script>

<button class="bigpic" onclick={() => { if (!live.playing || confirm('Open Steam Big Picture? This takes over the TV from what is playing.')) api('/api/games/launch', { id: 'bigpicture' }); }}>
  <Icon name="gamepad" size={18} />Steam Big Picture
</button>

<div class="seg">
  <button class:on={view === 'box'} onclick={() => (view = 'box')}>On the box</button>
  <button class:on={view === 'library'} onclick={() => (view = 'library')}>Steam library</button>
</div>

{#if downloads.length}
  <div class="card">
    <h2>Downloading</h2>
    {#each downloads as d (d.appid)}
      <div class="dl">
        <div class="row dlhead">
          <span class="dlname grow">{d.name}</span>
          <span class="mono small" class:paused={d.state === 'paused'}>
            {d.state === 'paused' ? 'Paused' : d.state === 'queued' ? 'Queued' : fmtGB(d.done) + ' / ' + fmtGB(d.total)}
          </span>
        </div>
        <span class="bar"><span style:width={(d.progress || 0) * 100 + '%'}></span></span>
        {#if d.state === 'paused'}
          <button class="resume small" disabled={installing.has(d.appid)} onclick={() => steamTap({ appid: d.appid, name: d.name, state: 'paused' })}>Resume</button>
        {/if}
      </div>
    {/each}
  </div>
{/if}

<!-- The picture that floats over a game lives with the games, and says so
     plainly when there is no picture (which is most of the time). -->
<Pip />

{#if view === 'box'}
  {#if live.game.active || pausedId}
    <div class="card">
      <h2>Session</h2>
      <div class="row wrap">
        <span class="grow small">
          {pausedId ? 'Paused: ' + (games.find(isPaused)?.name || pausedId) : 'A game is running on the TV.'}
        </span>
        {#if pausedId}
          <button class="primary" onclick={() => api('/api/games/resume', {})}>Resume</button>
        {:else}
          <button onclick={() => api('/api/games/suspend', {})}>Suspend</button>
        {/if}
        <button class="danger" onclick={() => { if (confirm('Quit the game? It gets a chance to save, then closes.')) api('/api/games/quit', {}); }}>Quit</button>
      </div>
    </div>
  {/if}

  {#if !loaded}
    <div class="grid">{#each Array(6) as _}<span class="sk-cell"></span>{/each}</div>
  {:else if games.length === 0}
    <p class="dim">No games found.</p>
  {:else}
    <div class="grid">
      {#each games as g (g.id)}
        <button class="tile" onclick={() => tap(g)}>
          {#if g.poster}
            <img class="tile-img" use:fadeimg src={g.poster} alt="" loading="lazy" />
          {:else}
            <div class="blank"><span>{g.name}</span></div>
          {/if}
          <span class="name">{g.name}{isPaused(g) ? ' · paused' : ''}</span>
          {#if isPaused(g)}<span class="badge"><Icon name="pause" size={12} /></span>{/if}
        </button>
      {/each}
    </div>
  {/if}
{:else}
  {#if !steamLoaded}
    <div class="grid">{#each Array(9) as _}<span class="sk-cell"></span>{/each}</div>
  {:else if steamLib.length === 0}
    <p class="dim">Steam library unavailable.</p>
  {:else}
    <div class="grid">
      {#each steamLib as g (g.appid)}
        <button class="tile" onclick={() => steamTap(g)}>
          <img class="tile-img" use:fadeimg src={'/api/art/steam?appid=' + g.appid} alt="" loading="lazy" />
          {#if g.state !== 'installed' && g.state !== 'notinstalled'}
            <span class="badge dl-badge">
              {#if g.progress != null}{Math.round(g.progress * 100)}%{:else}<Icon name="rotate-cw" size={12} />{/if}
            </span>
          {:else if g.state === 'notinstalled'}
            <span class="badge get" class:busy={installing.has(g.appid)}><Icon name="plus" size={13} /></span>
          {/if}
          <span class="name" class:on={g.state === 'installed'}>{g.name}</span>
        </button>
      {/each}
    </div>
  {/if}
{/if}

{#if sheet}
  <div use:portal use:fadeIn={{ reduced: $reducedMotion }} out:fadeOut={{ reduced: $reducedMotion }} class="scrim" onclick={() => (sheet = null)} role="presentation">
    <div use:slideUp={{ reduced: $reducedMotion }} out:slideDown={{ reduced: $reducedMotion }} use:dragDismiss={{ onClose: () => (sheet = null) }} class="sheet" onclick={(e) => e.stopPropagation()} role="dialog" aria-label={sheet.name}>
      <div class="sheetbar">
        <span class="sheettitle">{sheet.name}</span>
        <button class="closebtn" onclick={() => (sheet = null)} aria-label="Close"><Icon name="x" size={16} /></button>
      </div>

      <button class="primary launch" onclick={() => launch(sheet)}>
        {isPaused(sheet) ? 'Resume game' : 'Launch game'}
      </button>

      <div class="chead">
        <span class="clabel">Cheats</span>
        {#if cheats?.running}<span class="dim small">game running</span>{/if}
      </div>

      {#if cheats === null}
        <p class="dim small">Loading…</p>
      {:else if cheats.cheats.length === 0}
        <p class="dim small">Cheat list unavailable.</p>
      {:else}
        <div class="cheats">
          {#each cheats.cheats as c (c.name)}
            <button class="cheat" class:on={cheatOn(c)} disabled={busy.has(c.name)} onclick={() => toggleCheat(c)}>
              <span class="cname">{c.name}</span>
              <span class="pill">{busy.has(c.name) ? '…' : cheatOn(c) ? 'ON' : 'off'}</span>
            </button>
          {/each}
        </div>
        <p class="dim small note">
          {#if cheatNote}
            {cheatNote}
          {:else if cheats.liveError}
            Cannot reach the running game: {cheats.liveError}. Changes still apply on the next launch.
          {:else if cheats.running}
            Changes apply immediately and stick for the next launch.
          {:else}
            Changes apply the next time the game launches.
          {/if}
        </p>
      {/if}
    </div>
  </div>
{/if}

<style>
  .bigpic { width: 100%; margin-bottom: 12px; padding: 12px; color: var(--ink); }

  .scrim {
    position: fixed;
    inset: 0;
    background: var(--scrim);
    z-index: 20;
    display: flex;
    align-items: flex-end;
  }
  .sheet {
    background: var(--card);
    border-radius: 20px 20px 0 0;
    padding: 0 16px max(18px, env(safe-area-inset-bottom));
    width: 100%;
    max-height: 85dvh;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    overscroll-behavior: contain;
    touch-action: pan-y;
  }
  .sheetbar { display: flex; align-items: center; justify-content: space-between; padding: 14px 0 10px; }
  .sheettitle { font-weight: 600; }
  .closebtn { padding: 6px; background: none; color: var(--muted); }
  .launch { width: 100%; padding: 13px; }
  .chead { display: flex; align-items: baseline; justify-content: space-between; margin: 18px 0 8px; }
  .clabel { font-size: 0.78rem; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
  .cheats { display: flex; flex-direction: column; gap: 6px; }
  .cheat {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    width: 100%;
    padding: 12px 14px;
    text-align: left;
    color: var(--ink);
  }
  .cheat.on { color: var(--accent); }
  .cheat:disabled { opacity: 0.55; }
  .cname { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pill {
    flex: none;
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    padding: 3px 9px;
    border-radius: 999px;
    background: var(--chip, rgba(127, 127, 127, 0.18));
  }
  .cheat.on .pill { background: var(--accent); color: var(--on-accent, #000); }
  .note { margin: 12px 0 4px; }
  .seg { margin-bottom: 12px; }
  .seg button { flex: 1; }

  .grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
  }
  .tile {
    position: relative;
    padding: 0;
    background: none;
    text-align: left;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .tile img, .blank { width: 100%; }
  .blank {
    aspect-ratio: 2 / 3;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
    border-radius: 12px;
    background: var(--raise);
  }
  .name {
    font-size: 12px;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    width: 100%;
  }
  .name.on { color: var(--ink); }
  .badge {
    position: absolute;
    top: 6px; right: 6px;
    background: var(--accent);
    color: #fff;
    border-radius: 8px;
    padding: 3px 7px;
    font-size: 11px;
    display: flex;
    align-items: center;
    font-variant-numeric: tabular-nums;
  }
  .dl-badge { background: var(--accent); }
  .get { background: color-mix(in srgb, var(--bg) 55%, transparent); backdrop-filter: blur(4px); }
  .get.busy { opacity: 0.5; }

  .dl { margin-bottom: 12px; }
  .dl:last-child { margin-bottom: 0; }
  .dlhead { margin-bottom: 6px; }
  .dlname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
  .dlhead .paused { color: var(--muted); }
  .bar { display: block; height: 5px; background: var(--raise); border-radius: 3px; overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--accent); }
  .resume { margin-top: 8px; padding: 7px 12px; }
</style>
