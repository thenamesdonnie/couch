<script>
  import { live, api } from './state.svelte.js';
  import { ui, cache, loadGames, loadSteamLib } from './store.svelte.js';
  import { fadeimg } from './img.js';
  import Icon from './Icon.svelte';

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

  async function tap(g) {
    if (isPaused(g)) await api('/api/games/resume', {});
    else if (live.game.active && !confirm(`A game session is already running. Launch ${g.name} anyway?`)) return;
    else await api('/api/games/launch', { id: g.id });
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

<style>
  .bigpic { width: 100%; margin-bottom: 12px; padding: 12px; color: var(--ink); }
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
