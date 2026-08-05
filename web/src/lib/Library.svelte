<script>
  import { slideUp, fadeIn, slideDown, fadeOut } from './anim.js';
  import { portal } from './portal.js';
  import { api, fmtTime } from './state.svelte.js';
  import { cache, loadContinue, loadLibrary, ui } from './store.svelte.js';
  import { fadeimg, decodeImages } from './img.js';
  import Discover from './Discover.svelte';
  import YouTube from './YouTube.svelte';
  import Icon from './Icon.svelte';

  let { oncast } = $props();

  let view = $state(localStorage.getItem('couch.lib') || 'continue');
  $effect(() => localStorage.setItem('couch.lib', view));

  let search = $state('');
  let sort = $state('title');
  let searchItems = $state(null); // non-null only while a search is active
  let detail = $state(null);
  let episodes = $state(null);
  let casting = $state(false);

  // Read from the shared cache so switching tabs shows the last data instantly;
  // loaders below revalidate in the background.
  const cont = $derived(cache.continue);
  const items = $derived(searchItems ?? cache[view]?.[sort]?.items ?? []);
  // Only show skeletons on a genuinely cold view, never on a revalidate.
  const cold = $derived(
    view === 'continue' ? !cache.continue
    : view === 'movies' || view === 'shows' ? !cache[view]?.[sort]
    : false
  );

  function jfArt(item, w = 300) {
    if (item.imageTag) return `/api/art/jf/${item.id}/Primary?tag=${item.imageTag}&w=${w}`;
    if (item.seriesId && item.seriesImageTag) return `/api/art/jf/${item.seriesId}/Primary?tag=${item.seriesImageTag}&w=${w}`;
    return null;
  }

  let searchTimer = null;
  let loadSeq = 0;

  let upcoming = $state([]);
  const airLabel = (iso) => {
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const dd = new Date(iso);
    const dayDiff = Math.round((new Date(iso).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000);
    if (dayDiff === 0) return 'Today';
    if (dayDiff === 1) return 'Tomorrow';
    if (dayDiff < 7) return days[dd.getDay()];
    return `${months[dd.getMonth()]} ${dd.getDate()}`;
  };

  async function loadList() {
    if (view === 'add' || view === 'yt') return;
    const seq = ++loadSeq;
    try {
      if (view === 'continue') {
        loadContinue().catch(() => {});
        api('/api/upcoming')
          .then((u) => { if (seq === loadSeq) upcoming = u.episodes.filter((e) => !e.hasFile).slice(0, 8); })
          .catch(() => {});
      } else {
        loadLibrary(view, sort).catch(() => {});
      }
    } finally { /* cache updates drive the view */ }
  }

  // Switching view/sort, or the app regaining focus, revalidates against the
  // cache (no reload flash - cached data stays visible while it refreshes).
  $effect(() => {
    view; sort; ui.focusTick;
    if (!search.trim()) loadList();
  });

  async function runSearch() {
    const q = search.trim();
    if (!q) { searchItems = null; return; }
    const seq = ++loadSeq;
    const d = await api(`/api/library/${view}?sort=${sort}&search=${encodeURIComponent(q)}`);
    if (seq === loadSeq) searchItems = d.items;
  }

  function onSearch() {
    clearTimeout(searchTimer);
    if (!search.trim()) { searchItems = null; return; }
    searchTimer = setTimeout(runSearch, 250);
  }

  let season = $state(null);
  let arrInfo = $state(null);
  let upgraded4k = $state(new Map());
  let upgradeBusy = $state(false);

  // 'all' upgrades what's downloaded and searches; 'future' flips the profile
  // only, so new episodes arrive in 4K and the back catalogue stays put.
  async function upgrade4k(mode) {
    if (upgradeBusy || !arrInfo?.tmdbId || upgraded4k.has(detail.id)) return;
    upgradeBusy = true;
    try {
      await api('/api/discover/upgrade4k', {
        mediaType: detail.type === 'Series' ? 'tv' : 'movie',
        tmdbId: arrInfo.tmdbId,
        mode,
      });
      upgraded4k = new Map([...upgraded4k, [detail.id, mode]]);
    } finally {
      upgradeBusy = false;
    }
  }

  // Episodes + arr standing per item, cached for the app's life. First open
  // waits for the lot (spinner on the tile, sheet slides up complete, like
  // Discover); later opens serve the cache instantly and refresh behind it.
  const detailCache = new Map();
  let openingId = $state(null);

  async function fetchDetailBits(item) {
    const [eps, info] = await Promise.all([
      item.type === 'Series'
        ? api(`/api/library/show/${item.id}`).then((d) => d.episodes).catch(() => [])
        : Promise.resolve(null),
      api(`/api/library/arrinfo?id=${item.id}&type=${item.type}`).catch(() => null),
    ]);
    const bits = { episodes: eps, arrInfo: info };
    detailCache.set(item.id, bits);
    return bits;
  }

  function applyBits(item, bits) {
    if (detail?.id !== item.id) return;
    episodes = bits.episodes;
    arrInfo = bits.arrInfo;
    // Land on the season you are actually up to: the first with an unwatched
    // episode, otherwise the last. A refresh keeps whatever you switched to.
    if (bits.episodes?.length && season === null) {
      const next = bits.episodes.find((e) => !e.played);
      season = next ? next.season : bits.episodes[bits.episodes.length - 1]?.season ?? null;
    }
  }

  async function openDetail(item) {
    const cached = detailCache.get(item.id);
    if (cached) {
      detail = item;
      episodes = null;
      season = null;
      arrInfo = null;
      applyBits(item, cached);
      fetchDetailBits(item).then((bits) => applyBits(item, bits)).catch(() => {});
      return;
    }
    openingId = item.id;
    try {
      const bits = await fetchDetailBits(item);
      await decodeImages([jfArt(item)]);
      detail = item;
      episodes = null;
      season = null;
      arrInfo = null;
      applyBits(item, bits);
    } finally {
      openingId = null;
    }
  }

  let resumeChoice = $state(null);

  async function playChoice(fromStart) {
    const item = resumeChoice;
    resumeChoice = null;
    await cast(item, fromStart);
  }

  async function trailer(item) {
    casting = true;
    try {
      await api('/api/trailer', { id: item.id });
      detail = null;
      oncast?.();
    } finally {
      casting = false;
    }
  }

  async function cast(item, fromStart = false) {
    casting = true;
    try {
      await api('/api/cast', { id: item.id, fromStart });
      detail = null;
      oncast?.();
    } finally {
      casting = false;
    }
  }

  const fmtRuntime = (s) => (s >= 3600 ? `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m` : `${Math.round(s / 60)}m`);
  const epLabel = (e) => `S${String(e.season).padStart(2, '0')}E${String(e.episode).padStart(2, '0')}`;

  const seasons = $derived.by(() => {
    if (!episodes) return [];
    const by = new Map();
    for (const e of episodes) {
      if (!by.has(e.season)) by.set(e.season, []);
      by.get(e.season).push(e);
    }
    return [...by.entries()];
  });
</script>

<div class="seg noscrollbar">
  <button class:on={view === 'continue'} onclick={() => (view = 'continue')}>Continue</button>
  <button class:on={view === 'movies'} onclick={() => (view = 'movies')}>Films</button>
  <button class:on={view === 'shows'} onclick={() => (view = 'shows')}>Shows</button>
  <button class:on={view === 'yt'} onclick={() => (view = 'yt')}>YouTube</button>
  <button class:on={view === 'add'} onclick={() => (view = 'add')}>Discover</button>
</div>

{#if view === 'yt'}
  <YouTube onplay={() => oncast?.()} />
{:else if view === 'add'}
  <Discover />
{:else if view === 'continue'}
  {#if !cont}
    <div class="sk-head"></div>
    <div class="hscroll noscrollbar">
      {#each Array(4) as _}<span class="sk-resume"></span>{/each}
    </div>
  {:else}
    {#if cont.resume.length}
      <h3>Pick up where you left off</h3>
      <div class="hscroll noscrollbar">
        {#each cont.resume as item (item.id)}
          <button class="resume" onclick={() => (resumeChoice = item)} disabled={casting}>
            <span class="thumb">
              {#if jfArt(item)}<img use:fadeimg src={jfArt(item)} alt="" loading="lazy" />{/if}
              <span class="bar"><span style:width={item.runtime ? (item.resumeSecs / item.runtime) * 100 + '%' : '0%'}></span></span>
            </span>
            <span class="rname">{item.seriesName ? `${item.seriesName} ${epLabel(item)}` : item.name}</span>
          </button>
        {/each}
      </div>
    {/if}
    {#if cont.nextUp.length}
      <h3>Next up</h3>
      <div class="list">
        {#each cont.nextUp as item (item.id)}
          <button class="epi" onclick={() => cast(item)} disabled={casting}>
            {#if jfArt(item, 120)}<img use:fadeimg src={jfArt(item, 120)} alt="" loading="lazy" />{/if}
            <span class="grow">
              <span class="ename">{item.seriesName}</span>
              <span class="esub dim small">{epLabel(item)} · {item.name}</span>
            </span>
            <span class="go"><Icon name="play" size={14} /></span>
          </button>
        {/each}
      </div>
    {/if}
    {#if upcoming.length}
      <h3>Coming up</h3>
      <div class="uplist">
        {#each upcoming as e}
          <div class="up">
            <span class="upday mono small">{airLabel(e.airDate)}</span>
            <span class="grow upmeta">
              <span class="upname">{e.series}</span>
              <span class="dim small">S{String(e.season).padStart(2, '0')}E{String(e.episode).padStart(2, '0')} · {e.title}</span>
            </span>
          </div>
        {/each}
      </div>
    {/if}
    {#if !cont.resume.length && !cont.nextUp.length && !upcoming.length}
      <p class="dim">Nothing in progress. Browse Films or Shows and tap to play on the TV.</p>
    {/if}
  {/if}
{:else}
  <div class="row filters">
    <input type="text" placeholder={view === 'movies' ? 'Search films' : 'Search shows'} bind:value={search} oninput={onSearch} />
    <select bind:value={sort}>
      <option value="title">A to Z</option>
      <option value="year">Year</option>
      <option value="added">New in</option>
    </select>
  </div>
  {#if cold && !items.length}
    <div class="sk-grid">
      {#each Array(9) as _}<span class="sk-cell"></span>{/each}
    </div>
  {:else if !items.length}
    <p class="dim">No matches.</p>
  {:else}
    <div class="grid">
      {#each items as item (item.id)}
        <button class="tile" class:opening={openingId === item.id} onclick={() => openDetail(item)}>
          {#if jfArt(item)}
            <img class="tile-img" use:fadeimg src={jfArt(item)} alt="" loading="lazy" />
          {:else}
            <div class="blank"><span>{item.name}</span></div>
          {/if}
          {#if openingId === item.id}<span class="tilespin"></span>{/if}
          {#if item.type === 'Series' && item.unplayedCount}
            <span class="badge mono">{item.unplayedCount}</span>
          {/if}
          <span class="name">{item.name}</span>
        </button>
      {/each}
    </div>
  {/if}
{/if}

{#if resumeChoice}
  <div use:portal use:fadeIn out:fadeOut class="scrim" onclick={() => (resumeChoice = null)} role="presentation">
    <div use:slideUp out:slideDown class="chooser" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Play options">
      <span class="ctitle">{resumeChoice.seriesName ? `${resumeChoice.seriesName} ${epLabel(resumeChoice)}` : resumeChoice.name}</span>
      <button class="primary" disabled={casting} onclick={() => playChoice(false)}>Resume from {fmtTime(resumeChoice.resumeSecs)}</button>
      <button disabled={casting} onclick={() => playChoice(true)}>From beginning</button>
      <button class="cancelbtn" onclick={() => (resumeChoice = null)}>Cancel</button>
    </div>
  </div>
{/if}

{#if detail}
  <div use:portal use:fadeIn out:fadeOut class="scrim" onclick={() => (detail = null)} role="presentation">
    <div use:slideUp out:slideDown class="sheet" onclick={(e) => e.stopPropagation()} role="dialog" aria-label={detail.name}>
      <div class="sheetbar">
        <span class="sheettitle">{detail.name}</span>
        <button class="closebtn" onclick={() => (detail = null)} aria-label="Close"><Icon name="x" size={16} /></button>
      </div>
      <div class="dhead">
        {#if jfArt(detail)}<img use:fadeimg src={jfArt(detail)} alt="" />{/if}
        <div>
          <div class="dtitle display">{detail.name}</div>
          <div class="dim small">
            {[detail.year, detail.runtime ? fmtRuntime(detail.runtime) : null, detail.genres.slice(0, 2).join(', ')].filter(Boolean).join(' · ')}
          </div>
          <div class="dactions">
            {#if detail.type === 'Movie'}
              <button class="primary" disabled={casting} onclick={() => cast(detail)}>
                {detail.resumeSecs ? 'Resume on TV' : 'Play on TV'}
              </button>
              {#if detail.resumeSecs}
                <button disabled={casting} onclick={() => cast(detail, true)}>From start</button>
              {/if}
            {/if}
            <button disabled={casting} onclick={() => trailer(detail)}>Trailer</button>
          </div>
          {#if arrInfo?.inArr && !arrInfo.uhd}
            <div class="dactions">
              {#if detail.type === 'Movie'}
                <button class="fourk" disabled={upgradeBusy || upgraded4k.has(detail.id)} onclick={() => upgrade4k('all')}>
                  {upgraded4k.has(detail.id) ? '4K upgrade started' : 'Upgrade to 4K'}
                </button>
              {:else}
                <button class="fourk" disabled={upgradeBusy || upgraded4k.has(detail.id)} onclick={() => upgrade4k('future')}>
                  {upgraded4k.get(detail.id) === 'future' ? '4K on for new episodes' : '4K new episodes'}
                </button>
                <button class="fourk" disabled={upgradeBusy || upgraded4k.has(detail.id)} onclick={() => upgrade4k('all')}>
                  {upgraded4k.get(detail.id) === 'all' ? '4K upgrade started' : 'Upgrade all'}
                </button>
              {/if}
            </div>
          {:else if arrInfo?.uhd}
            <div class="dactions"><span class="uhdchip">4K</span></div>
          {/if}
        </div>
      </div>
      {#if detail.overview}<p class="overview small dim">{detail.overview}</p>{/if}
      {#if detail.type === 'Series'}
        {#if !episodes}
          <p class="dim small">Loading episodes...</p>
        {:else}
          {#if seasons.length > 1}
            <div class="seasonrow">
              {#each seasons as [sn]}
                <button class="seasonpill" class:on={season === sn} onclick={() => (season = sn)}>
                  {sn === 0 ? 'Specials' : `Season ${sn}`}
                </button>
              {/each}
            </div>
          {:else if seasons.length === 1}
            <h3>{seasons[0][0] === 0 ? 'Specials' : `Season ${seasons[0][0]}`}</h3>
          {/if}
          <div class="list eplist">
            {#each (seasons.find(([sn]) => sn === season)?.[1] ?? seasons[0]?.[1] ?? []) as e (e.id)}
              <button class="epi" class:seen={e.played} onclick={() => cast(e)} disabled={casting}>
                <span class="grow">
                  <span class="ename">{epLabel(e)} · {e.name}</span>
                  {#if e.resumeSecs}<span class="esub dim small">in progress</span>{/if}
                </span>
                <span class="go" class:seenicon={e.played}><Icon name={e.played ? "check" : "play"} size={14} /></span>
              </button>
            {/each}
          </div>
        {/if}
      {/if}
    </div>
  </div>
{/if}

<style>
  .seg { margin-bottom: 12px; overflow-x: auto; }

  h3 {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin: 16px 0 8px;
  }

  .filters { margin-bottom: 12px; }
  .filters select {
    font: inherit;
    color: var(--ink);
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 10px;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
  }
  .tile {
    position: relative;
    padding: 0;
    background: none;
    border: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
    text-align: left;
  }
  .tile img, .blank {
    width: 100%;
    aspect-ratio: 2 / 3;
    object-fit: cover;
    border-radius: 10px;
    border: 1px solid var(--line);
    background: var(--card);
  }
  .blank {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
  }
  .name {
    font-size: 12px;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    width: 100%;
  }
  .badge {
    position: absolute;
    top: 6px; right: 6px;
    background: var(--accent);
    color: #fff;
    border-radius: 6px;
    padding: 2px 7px;
    font-size: 11px;
  }
  .tile.opening { opacity: 0.55; }
  .tilespin {
    position: absolute;
    top: 40%; left: 50%;
    width: 24px; height: 24px;
    margin: -12px 0 0 -12px;
    border-radius: 50%;
    border: 2px solid color-mix(in srgb, var(--ink) 25%, transparent);
    border-top-color: var(--accent);
    animation: tilespin 0.7s linear infinite;
    z-index: 4;
    pointer-events: none;
  }
  @keyframes tilespin { to { transform: rotate(360deg); } }

  .hscroll {
    display: flex;
    gap: 10px;
    overflow-x: auto;
    padding-bottom: 4px;
  }
  .resume {
    flex: 0 0 110px;
    padding: 0;
    background: none;
    border: none;
    display: flex;
    flex-direction: column;
    gap: 5px;
    text-align: left;
  }
  .thumb { position: relative; display: block; width: 110px; }
  .thumb img {
    display: block;
    width: 110px;
    aspect-ratio: 2 / 3;
    object-fit: cover;
    border-radius: 10px;
  }
  .bar {
    position: absolute;
    left: 7px; right: 7px; bottom: 7px;
    height: 4px;
    background: rgba(255, 255, 255, 0.3);
    border-radius: 2px;
    overflow: hidden;
    box-shadow: 0 0 6px rgba(0, 0, 0, 0.4);
  }
  .bar span { display: block; height: 100%; background: var(--accent); }

  .chooser {
    background: var(--card);
    border-radius: 22px 22px 0 0;
    padding: 18px 16px max(18px, env(safe-area-inset-bottom));
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .ctitle {
    font-weight: 600;
    margin-bottom: 6px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .cancelbtn { background: none; color: var(--muted); }
  .rname {
    font-size: 11px;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    width: 110px;
  }

  .list { display: flex; flex-direction: column; gap: 6px; }
  .uplist { display: flex; flex-direction: column; gap: 10px; }
  .sk-head { height: 14px; width: 190px; border-radius: 6px; background: var(--raise); margin: 16px 0 10px; animation: pulse 1.4s ease-in-out infinite; }
  .sk-resume { flex: 0 0 110px; aspect-ratio: 2/3; border-radius: 10px; background: var(--raise); animation: pulse 1.4s ease-in-out infinite; }
  .up { display: flex; gap: 10px; align-items: flex-start; }
  .upday { width: 66px; color: var(--accent); padding-top: 1px; flex-shrink: 0; }
  .upmeta { display: flex; flex-direction: column; min-width: 0; }
  .upname { font-weight: 500; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .epi {
    display: flex;
    align-items: center;
    gap: 10px;
    text-align: left;
  }
  .epi.seen { opacity: 0.55; }
  .epi img { width: 34px; aspect-ratio: 2/3; object-fit: cover; border-radius: 6px; }
  .epi .grow { display: flex; flex-direction: column; min-width: 0; }
  .ename { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .go { color: var(--accent); display: flex; }
  .go.seenicon { color: var(--faint); }

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
    overflow: hidden;
    overscroll-behavior: contain;
  }
  /* The sheet itself no longer scrolls: the episode list (and, when space is
     tight, the overview) scroll on their own so the art, actions and season
     pills stay put. */
  .sheet .overview {
    flex-shrink: 1;
    min-height: 3.9em;
    overflow-y: auto;
    touch-action: pan-y;
    overscroll-behavior: contain;
  }
  .sheet .seasonrow, .sheet h3, .sheet .dhead, .sheet .sheetbar { flex-shrink: 0; }
  .eplist {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    touch-action: pan-y;
    overscroll-behavior: contain;
    padding-bottom: 4px;
  }
  .sheetbar {
    position: sticky;
    top: 0;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0 -16px 12px;
    padding: 14px 16px 10px;
    background: var(--card);
  }
  .sheettitle {
    flex: 1;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .closebtn {
    width: 34px; height: 34px;
    padding: 0;
    border-radius: 50%;
    justify-content: center;
    color: var(--muted);
    flex-shrink: 0;
  }
  .seasonrow {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    margin: 14px 0 10px;
    padding-bottom: 2px;
  }
  .seasonpill {
    flex-shrink: 0;
    padding: 8px 13px;
    border-radius: 999px;
    font-size: 13px;
    color: var(--muted);
  }
  .seasonpill.on { background: var(--accent-tint); color: var(--accent); }
  .dhead { display: flex; gap: 14px; margin-bottom: 10px; }
  .dhead img {
    width: 96px;
    aspect-ratio: 2 / 3;
    object-fit: cover;
    border-radius: 10px;
    border: 1px solid var(--line);
  }
  .dtitle { font-size: 19px; font-weight: 700; line-height: 1.15; margin-bottom: 4px; }
  .dactions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
  .fourk {
    font-size: 12px;
    padding: 8px 12px;
    border-radius: 10px;
    background: var(--raise);
    color: var(--muted);
    border: 1px solid var(--line);
  }
  .uhdchip {
    font-size: 11px;
    font-weight: 600;
    color: var(--accent);
    background: var(--accent-tint);
    border-radius: 6px;
    padding: 3px 8px;
  }
</style>
