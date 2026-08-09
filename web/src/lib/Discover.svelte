<script>
  import { slideUp, fadeIn, slideDown, fadeOut } from './anim.js';
  import { dragDismiss } from './drag.js';
  import { portal } from './portal.js';
  import { untrack } from 'svelte';
  import { api } from './state.svelte.js';
  import { cache, loadDiscover, ui } from './store.svelte.js';
  import { fadeimg, decodeImages } from './img.js';
  import Icon from './Icon.svelte';

  let search = $state('');
  let results = $state(null);
  let requests = $state(null);
  let showRequests = $state(false);
  let busyId = $state(null);
  let requested = $state(new Set());

  // From the shared cache, filled by prefetch on launch; revalidate on mount.
  const trending = $derived(cache.discover?.trending ?? []);
  const popularFilms = $derived(cache.discover?.popularFilms ?? []);
  const popularShows = $derived(cache.discover?.popularShows ?? []);
  const cold = $derived(!cache.discover);

  // Revalidate on mount and on app focus. untrack keeps the effect from
  // re-running just because the requests sheet opened.
  $effect(() => {
    ui.focusTick;
    loadDiscover().catch(() => {});
    untrack(() => { if (showRequests) openRequests(); });
  });

  async function openRequests() {
    showRequests = true;
    const d = await api('/api/discover/requests').catch(() => ({ requests: [] }));
    requests = d.requests;
  }

  let searchTimer = null;
  let seq = 0;
  function onSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      const q = search.trim();
      if (!q) { results = null; return; }
      const mySeq = ++seq;
      const d = await api(`/api/discover/search?q=${encodeURIComponent(q)}`);
      if (mySeq === seq) results = d.results;
    }, 350);
  }

  let detail = $state(null);
  let detailLoading = $state(false);
  let openingId = $state(null);
  let pickedSeasons = $state(new Set());
  let want4k = $state(false);
  let upgraded4k = $state(new Map());
  let upgradeBusy = $state(false);

  // Seasons still up for grabs: not already requested/downloading/available.
  const selectableSeasons = $derived(
    detail?.mediaType === 'tv' ? (detail.seasonList || []).filter((s) => !s.status) : []
  );

  const tmdbUrl = (p) => (p ? '/api/art/tmdb?p=' + encodeURIComponent(p) : null);

  // Full details cached per title: the first open waits for everything (sheet
  // slides up complete), reopening is instant from cache with a quiet refresh
  // behind it so statuses stay current.
  const detailCache = new Map();

  async function fetchDetail(item) {
    const d = await api(`/api/discover/detail?type=${item.mediaType}&tmdbId=${item.tmdbId}`);
    const full = { ...item, ...d };
    detailCache.set(item.mediaType + item.tmdbId, full);
    return full;
  }

  async function openDetail(item) {
    const key = item.mediaType + item.tmdbId;
    want4k = false;
    const cached = detailCache.get(key);
    if (cached) {
      pickedSeasons = new Set((cached.seasonList || []).filter((s) => !s.status).map((s) => s.number));
      detail = cached;
      // Refresh behind the sheet; keep the user's season picks as they are.
      fetchDetail(item).then((full) => {
        if (detail && detail.mediaType + detail.tmdbId === key) detail = full;
      }).catch(() => {});
      return;
    }
    // Fetch the full detail AND decode its art before opening, so the sheet
    // slides up complete instead of popping fields and images in piecemeal.
    // The tapped card shows a spinner while this happens.
    openingId = key;
    detailLoading = true;
    try {
      const full = await fetchDetail(item);
      await decodeImages([tmdbUrl(full.poster), tmdbUrl(full.backdrop)]);
      // Everything still missing starts selected, so one tap requests the lot.
      pickedSeasons = new Set((full.seasonList || []).filter((s) => !s.status).map((s) => s.number));
      detail = full;
    } catch {
      pickedSeasons = new Set();
      detail = { ...item }; // fall back to the slim card
    } finally {
      detailLoading = false;
      openingId = null;
    }
  }

  async function request(item) {
    // A show with a picker may be requestable even while "partly available";
    // there the guard is an empty selection, not the show-level status.
    const usePicker = item.mediaType === 'tv' && item.seasonList?.length;
    if (usePicker ? !pickedSeasons.size || requested.has(item.tmdbId) : statusOf(item)) return;
    busyId = item.tmdbId;
    try {
      const body = { mediaType: item.mediaType, tmdbId: item.tmdbId };
      if (usePicker) body.seasons = [...pickedSeasons].sort((a, b) => a - b);
      if (want4k) body.is4k = true;
      await api('/api/discover/request', body);
      requested = new Set([...requested, item.tmdbId]);
      detail = null;
    } finally {
      busyId = null;
    }
  }

  function toggleSeason(n) {
    const next = new Set(pickedSeasons);
    if (next.has(n)) next.delete(n); else next.add(n);
    pickedSeasons = next;
  }

  // mode 'all' upgrades what's already there and searches; 'future' flips the
  // profile only, so new episodes come in 4K; 'off' reverts to 1080p
  // (already-downloaded 4K files stay).
  async function upgrade4k(item, mode) {
    if (upgradeBusy) return;
    upgradeBusy = true;
    try {
      await api('/api/discover/upgrade4k', { mediaType: item.mediaType, tmdbId: item.tmdbId, mode });
      const next = new Map(upgraded4k);
      if (mode === 'off') next.delete(item.tmdbId); else next.set(item.tmdbId, mode);
      upgraded4k = next;
      if (detail && detail.tmdbId === item.tmdbId) detail = { ...detail, uhd: mode !== 'off' };
    } finally {
      upgradeBusy = false;
    }
  }

  function toggleAllSeasons() {
    pickedSeasons = pickedSeasons.size === selectableSeasons.length
      ? new Set()
      : new Set(selectableSeasons.map((s) => s.number));
  }

  function statusOf(item) {
    if (requested.has(item.tmdbId)) return 'requested';
    return item.status;
  }

  const fmtRuntime = (m) => (m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`);

  const fmtGB = (b) => (b / 1e9).toFixed(1) + ' GB';
</script>

<div class="row">
  <input type="text" placeholder="Search films and shows" bind:value={search} oninput={onSearch} />
  <button class="reqbtn" onclick={openRequests} aria-label="Your requests"><Icon name="check" size={16} /></button>
</div>

{#if results}
  <div class="list">
    {#each results as item (item.mediaType + item.tmdbId)}
      <button class="hit" class:opening={openingId === item.mediaType + item.tmdbId} onclick={() => openDetail(item)}>
        {#if item.poster}
          <img use:fadeimg src={'/api/art/tmdb?p=' + encodeURIComponent(item.poster)} alt="" loading="lazy" />
        {:else}
          <div class="noart"></div>
        {/if}
        {#if openingId === item.mediaType + item.tmdbId}<span class="hitspin"></span>{/if}
        <div class="grow meta">
          <span class="title">{item.title}</span>
          <span class="dim small">{[item.year, item.mediaType === 'tv' ? 'Series' : 'Film'].filter(Boolean).join(' · ')}</span>
        </div>
        {#if statusOf(item) === 'available'}
          <span class="chip ok">On Jellyfin</span>
        {:else if statusOf(item)}
          <span class="chip">{statusOf(item)}</span>
        {:else}
          <span class="chip go">Add</span>
        {/if}
      </button>
    {/each}
    {#if !results.length}<p class="dim">No matches.</p>{/if}
  </div>
{:else if cold}
  {#each ['Trending', 'Popular films', 'Popular shows'] as label}
    <h3>{label}</h3>
    <div class="hscroll noscrollbar">
      {#each Array(5) as _}<span class="sk-trend"></span>{/each}
    </div>
  {/each}
{:else}
  {#each [['Trending', trending], ['Popular films', popularFilms], ['Popular shows', popularShows]] as [label, items]}
    {#if items.length}
      <h3>{label}</h3>
      <div class="hscroll noscrollbar">
        {#each items as item (item.mediaType + item.tmdbId)}
          <button class="trend" class:opening={openingId === item.mediaType + item.tmdbId} onclick={() => openDetail(item)}>
            {#if item.poster}
              <img use:fadeimg src={'/api/art/tmdb?p=' + encodeURIComponent(item.poster)} alt="" loading="lazy" />
            {/if}
            {#if openingId === item.mediaType + item.tmdbId}<span class="hitspin"></span>{/if}
            <span class="tname">{item.title}</span>
            {#if statusOf(item)}<span class="badge"><Icon name={statusOf(item) === 'available' ? 'check' : 'dots'} size={12} /></span>{/if}
          </button>
        {/each}
      </div>
    {/if}
  {/each}
{/if}

{#if detail}
  <div use:portal use:fadeIn out:fadeOut class="scrim" onclick={() => (detail = null)} role="presentation">
    <div use:slideUp out:slideDown use:dragDismiss={{ onClose: () => (detail = null) }} class="dsheet" onclick={(e) => e.stopPropagation()} role="dialog" aria-label={detail.title}>
      {#if detail.backdrop}
        <div class="dback" style:background-image={'url(/api/art/tmdb?p=' + encodeURIComponent(detail.backdrop) + ')'}></div>
        <div class="dback-fade"></div>
      {/if}
      <button class="dclose" onclick={() => (detail = null)} aria-label="Close"><Icon name="x" size={16} /></button>
      <div class="dbody">
        <div class="dhead">
          {#if detail.poster}<img class="dposter" use:fadeimg src={'/api/art/tmdb?p=' + encodeURIComponent(detail.poster)} alt="" />{/if}
          <div class="dtop">
            <div class="dtitle display">{detail.title}</div>
            <div class="dmeta dim small">
              {[detail.year, detail.mediaType === 'tv' ? 'Series' : 'Film',
                detail.runtime ? fmtRuntime(detail.runtime) : null,
                detail.seasons ? `${detail.seasons} season${detail.seasons > 1 ? 's' : ''}` : null,
                detail.uhd ? '4K' : null
              ].filter(Boolean).join(' · ')}
            </div>
            {#if detail.rating}<div class="drating mono">★ {detail.rating}</div>{/if}
          </div>
        </div>
        {#if detail.genres?.length}
          <div class="genres">
            {#each detail.genres.slice(0, 4) as g}<span class="genre">{g}</span>{/each}
          </div>
        {/if}
        {#if detail.releaseNote}
          <div class="relnote"><Icon name="dots" size={14} />{detail.releaseNote}</div>
        {/if}
        {#if detail.tagline}<p class="tagline">{detail.tagline}</p>{/if}
        {#if detail.overview}<p class="small dim overview">{detail.overview}</p>{/if}
        {#if detailLoading && !detail.overview}<p class="dim small">Loading...</p>{/if}
        {#if selectableSeasons.length && statusOf(detail) !== 'available' && !requested.has(detail.tmdbId)}
          <div class="seasonshead">
            <span class="small dim">Seasons</span>
            {#if selectableSeasons.length > 1}
              <button class="allbtn" onclick={toggleAllSeasons}>
                {pickedSeasons.size === selectableSeasons.length ? 'None' : 'All'}
              </button>
            {/if}
          </div>
          <div class="seasons">
            {#each detail.seasonList as s (s.number)}
              {#if s.status}
                <span class="season done" class:ok={s.status === 'available'} title={s.status}>
                  S{s.number}<Icon name={s.status === 'available' ? 'check' : 'dots'} size={11} />
                </span>
              {:else}
                <button class="season" class:on={pickedSeasons.has(s.number)} onclick={() => toggleSeason(s.number)}>
                  S{s.number}
                </button>
              {/if}
            {/each}
          </div>
        {/if}
        <div class="daction">
          {#if !detail.uhd && !requested.has(detail.tmdbId) && (selectableSeasons.length || !statusOf(detail))}
            <div class="qrow">
              <span class="small dim">Quality</span>
              <div class="qseg">
                <button class:on={!want4k} onclick={() => (want4k = false)}>1080p</button>
                <button class:on={want4k} onclick={() => (want4k = true)}>4K</button>
              </div>
            </div>
          {/if}
          {#if statusOf(detail) === 'available'}
            <span class="statusline ok">Already on Jellyfin</span>
          {:else if requested.has(detail.tmdbId)}
            <span class="statusline">Requested</span>
          {:else if selectableSeasons.length}
            <button class="primary big" disabled={busyId === detail.tmdbId || !pickedSeasons.size} onclick={() => request(detail)}>
              {#if !pickedSeasons.size}
                Pick a season
              {:else if pickedSeasons.size === detail.seasonList.length}
                Request series
              {:else}
                Request {pickedSeasons.size} season{pickedSeasons.size > 1 ? 's' : ''}
              {/if}
            </button>
          {:else if statusOf(detail)}
            <span class="statusline">{statusOf(detail) === 'requested' ? 'Requested' : statusOf(detail)}</span>
          {:else}
            <button class="primary big" disabled={busyId === detail.tmdbId} onclick={() => request(detail)}>
              Request {detail.mediaType === 'tv' ? 'series' : 'film'}
            </button>
          {/if}
          <!-- Deliberately NOT gated on `requested`. Hiding these the moment
               something is requested is what made "I forgot to tick 4K and
               now I cannot change it" a dead end: the request has already
               reached Radarr, so the profile is exactly the thing that is
               still changeable. -->
          {#if detail.inArr && detail.uhd}
            <div class="uprow center">
              <span class="uhdchip">4K</span>
              {#if upgraded4k.get(detail.tmdbId) === 'all'}
                <span class="dim small">searching for 4K</span>
              {:else}
                <button class="up4k" disabled={upgradeBusy} onclick={() => upgrade4k(detail, 'all')}>
                  {detail.mediaType === 'tv' ? 'Upgrade existing' : 'Search for 4K'}
                </button>
              {/if}
              <button class="up4k" disabled={upgradeBusy} onclick={() => upgrade4k(detail, 'off')}>Turn off 4K</button>
            </div>
          {:else if detail.inArr && !detail.uhd}
            {#if detail.mediaType === 'tv'}
              <div class="uprow">
                <button class="up4k" disabled={upgradeBusy} onclick={() => upgrade4k(detail, 'future')}>4K new episodes</button>
                <button class="up4k" disabled={upgradeBusy} onclick={() => upgrade4k(detail, 'all')}>Upgrade all to 4K</button>
              </div>
            {:else if detail.releaseNote}
              <!-- No home release yet, so 'future': flip the profile and stop.
                   'all' would fire a search for a film that does not exist as
                   a release, and the UHD profile falls back to 1080p, so a
                   search now is how a cinema rip gets grabbed. -->
              <button class="up4k wide" disabled={upgradeBusy} onclick={() => upgrade4k(detail, 'future')}>Get it in 4K when it lands</button>
            {:else}
              <button class="up4k wide" disabled={upgradeBusy} onclick={() => upgrade4k(detail, 'all')}>Upgrade to 4K</button>
            {/if}
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}

{#if showRequests}
  <div use:portal use:fadeIn out:fadeOut class="scrim" onclick={() => (showRequests = false)} role="presentation">
    <div use:slideUp out:slideDown use:dragDismiss={{ onClose: () => (showRequests = false) }} class="sheet" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Your requests">
      <div class="sheetbar">
        <span class="sheettitle">Requests</span>
        <button class="closebtn" onclick={() => (showRequests = false)} aria-label="Close"><Icon name="x" size={16} /></button>
      </div>
      {#if !requests}
        <p class="dim small">Loading...</p>
      {:else if !requests.length}
        <p class="dim small">Nothing requested yet. Search above and tap Request.</p>
      {:else}
        <div class="list">
          {#each requests as r (r.id)}
            <div class="hit">
              {#if r.poster}
                <img use:fadeimg src={'/api/art/tmdb?p=' + encodeURIComponent(r.poster)} alt="" loading="lazy" />
              {:else}
                <div class="noart"></div>
              {/if}
              <div class="grow meta">
                <span class="title">{r.title}</span>
                <span class="dim small">{[r.year, r.requestedBy].filter(Boolean).join(' · ')}</span>
                {#each r.downloads as dl}
                  <span class="dl small">
                    <span class="bar"><span style:width={dl.size ? ((dl.size - dl.sizeLeft) / dl.size) * 100 + '%' : '0%'}></span></span>
                    <span class="dim">{dl.size ? fmtGB(dl.size - dl.sizeLeft) + ' of ' + fmtGB(dl.size) : dl.status}</span>
                  </span>
                {/each}
              </div>
              <span class="chip" class:ok={r.available} class:busy={r.downloading} class:waiting={r.waiting}>{r.status}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  h3 {
    font-size: 13px;
    font-weight: 600;
    color: var(--muted);
    margin: 16px 0 8px;
  }
  .reqbtn {
    width: 44px; height: 44px;
    padding: 0;
    border-radius: 12px;
    justify-content: center;
    color: var(--muted);
    flex-shrink: 0;
  }
  .list { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
  .hit {
    display: flex;
    align-items: center;
    gap: 12px;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 8px 10px;
  }
  .hit img, .noart {
    width: 44px;
    aspect-ratio: 2 / 3;
    object-fit: cover;
    border-radius: 7px;
    background: var(--raise);
    flex-shrink: 0;
  }
  .meta { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chip {
    font-size: 11px;
    color: var(--muted);
    background: var(--raise);
    border-radius: 999px;
    padding: 5px 10px;
    white-space: nowrap;
    text-transform: capitalize;
  }
  .chip.ok { color: var(--ok); background: color-mix(in srgb, var(--ok) 14%, transparent); }
  .chip.busy { color: var(--accent); background: var(--accent-tint); }
  .chip.waiting { color: #c99a3a; background: rgba(201, 154, 58, 0.14); }
  .chip.go { color: var(--accent); background: var(--accent-tint); }
  .hit { position: relative; border: 1px solid var(--line); width: 100%; text-align: left; cursor: pointer; }
  .hit:active { background: var(--raise); }
  .hit.opening, .trend.opening { opacity: 0.55; }
  .hitspin {
    position: absolute;
    top: 50%; left: 50%;
    width: 24px; height: 24px;
    margin: -12px 0 0 -12px;
    border-radius: 50%;
    border: 2px solid color-mix(in srgb, var(--ink) 25%, transparent);
    border-top-color: var(--accent);
    animation: hitspin 0.7s linear infinite;
    z-index: 4;
    pointer-events: none;
  }
  .trend .hitspin { top: 30%; }
  @keyframes hitspin { to { transform: rotate(360deg); } }

  .dl { display: flex; flex-direction: column; gap: 3px; margin-top: 4px; }
  .bar { display: block; height: 3px; background: var(--raise); border-radius: 2px; overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--accent); }

  .hscroll { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 4px; }
  .sk-trend { flex: 0 0 104px; aspect-ratio: 2/3; border-radius: 11px; background: var(--raise); animation: pulse 1.4s ease-in-out infinite; }
  .trend {
    position: relative;
    flex: 0 0 104px;
    padding: 0;
    background: none;
    display: flex;
    flex-direction: column;
    gap: 5px;
    text-align: left;
  }
  .trend img {
    width: 104px;
    aspect-ratio: 2 / 3;
    object-fit: cover;
    border-radius: 11px;
    background: var(--raise);
  }
  .tname {
    font-size: 11px;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    width: 104px;
  }
  .badge {
    position: absolute;
    top: 6px; right: 6px;
    background: var(--accent);
    color: #fff;
    border-radius: 7px;
    padding: 3px 6px;
    display: flex;
  }

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
    border-radius: 22px 22px 0 0;
    padding: 0 16px max(18px, env(safe-area-inset-bottom));
    width: 100%;
    max-height: 80dvh;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .sheetbar {
    position: sticky;
    top: 0;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0 -16px 10px;
    padding: 14px 16px 10px;
    background: var(--card);
  }
  .sheettitle { flex: 1; font-weight: 600; }
  .closebtn {
    width: 34px; height: 34px;
    padding: 0;
    border-radius: 50%;
    justify-content: center;
    color: var(--muted);
  }

  .dsheet {
    position: relative;
    background: var(--card);
    border-radius: 22px 22px 0 0;
    width: 100%;
    max-height: 88dvh;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .dback {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 200px;
    background-size: cover;
    background-position: center 22%;
    border-radius: 22px 22px 0 0;
  }
  .dback-fade {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 200px;
    background: linear-gradient(180deg,
      color-mix(in srgb, var(--card) 20%, transparent) 0%,
      color-mix(in srgb, var(--card) 55%, transparent) 55%,
      var(--card) 98%);
    border-radius: 22px 22px 0 0;
  }
  .dclose {
    position: absolute;
    top: 12px; right: 12px;
    z-index: 3;
    width: 34px; height: 34px;
    padding: 0;
    border-radius: 50%;
    justify-content: center;
    background: color-mix(in srgb, var(--bg) 55%, transparent);
    backdrop-filter: blur(6px);
    color: var(--ink);
  }
  .dbody {
    position: relative;
    z-index: 2;
    padding: 90px 16px max(18px, env(safe-area-inset-bottom));
  }
  .dhead { display: flex; gap: 14px; align-items: flex-end; }
  .dposter {
    width: 92px;
    aspect-ratio: 2 / 3;
    object-fit: cover;
    border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    flex-shrink: 0;
  }
  .dtop { flex: 1; min-width: 0; padding-bottom: 2px; }
  .dtitle { font-size: 21px; line-height: 1.1; }
  .dmeta { margin-top: 5px; }
  .drating { margin-top: 6px; color: var(--accent); font-size: 13px; }
  .genres { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px; }
  .genre {
    font-size: 11px;
    color: var(--muted);
    background: var(--raise);
    border-radius: 999px;
    padding: 4px 10px;
  }
  .relnote {
    display: flex;
    align-items: center;
    gap: 7px;
    margin-top: 14px;
    padding: 9px 12px;
    border-radius: 10px;
    background: rgba(201, 154, 58, 0.13);
    color: #c99a3a;
    font-size: 13px;
  }
  .seasonshead {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 18px;
  }
  .allbtn {
    font-size: 12px;
    color: var(--accent);
    background: none;
    padding: 4px 8px;
  }
  .seasons { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 8px; }
  .season {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    padding: 8px 13px;
    border-radius: 999px;
    background: var(--raise);
    color: var(--muted);
    border: 1px solid transparent;
  }
  .season.on {
    color: var(--accent);
    background: var(--accent-tint);
    border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  }
  .season.done { opacity: 0.6; }
  .season.done.ok { color: var(--ok); background: color-mix(in srgb, var(--ok) 12%, transparent); opacity: 1; }
  .tagline { font-style: italic; color: var(--muted); margin: 14px 0 0; font-size: 14px; }
  .overview { margin: 10px 0 0; line-height: 1.5; }
  .daction { margin-top: 18px; display: flex; flex-direction: column; gap: 10px; }
  .big { width: 100%; padding: 14px; font-size: 15px; }
  .qrow { display: flex; align-items: center; justify-content: space-between; }
  .qseg {
    display: flex;
    background: var(--raise);
    border-radius: 10px;
    padding: 3px;
    gap: 2px;
  }
  .qseg button {
    font-size: 12px;
    padding: 6px 14px;
    border-radius: 8px;
    background: none;
    color: var(--muted);
  }
  .qseg button.on { background: var(--card); color: var(--ink); box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25); }
  .uprow { display: flex; gap: 8px; }
  .uprow.center { align-items: center; }
  .uhdchip {
    font-size: 11px;
    font-weight: 600;
    color: var(--accent);
    background: var(--accent-tint);
    border-radius: 6px;
    padding: 3px 8px;
  }
  .up4k {
    flex: 1;
    padding: 11px;
    font-size: 13px;
    border-radius: 12px;
    background: var(--raise);
    color: var(--ink);
    border: 1px solid var(--line);
    justify-content: center;
  }
  .up4k.wide { width: 100%; }
  .statusline {
    display: block;
    text-align: center;
    padding: 13px;
    border-radius: 12px;
    background: var(--raise);
    color: var(--muted);
    font-weight: 500;
  }
  .statusline.ok { color: var(--ok); background: color-mix(in srgb, var(--ok) 12%, transparent); }
</style>
