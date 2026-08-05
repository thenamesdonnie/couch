<script>
  import { api } from './state.svelte.js';
  import { cache, loadYtFeed } from './store.svelte.js';
  import { fadeimg } from './img.js';
  import Icon from './Icon.svelte';

  let { onplay } = $props();

  let sub = $state(localStorage.getItem('couch.yt') || 'subscriptions');
  $effect(() => localStorage.setItem('couch.yt', sub));

  // Feeds live in the shared cache, so they survive tab switches and the
  // store's focus/poll revalidation keeps them fresh in the background.
  let search = $state('');
  let searchResults = $state(null);
  let loading = $state(false);

  async function loadFeed(type) {
    loading = true;
    try {
      await loadYtFeed(type);
    } catch { cache.ytFeeds[type] = cache.ytFeeds[type] || []; } finally { loading = false; }
  }

  $effect(() => {
    if (sub === 'search') return;
    if (!cache.ytFeeds[sub]) loadFeed(sub);
  });

  let timer = null;
  let seq = 0;
  function onSearch() {
    clearTimeout(timer);
    if (!search.trim()) { searchResults = null; return; }
    timer = setTimeout(async () => {
      const q = search.trim();
      const mine = ++seq;
      loading = true;
      try {
        const d = await api(`/api/youtube/search?q=${encodeURIComponent(q)}`);
        if (mine === seq) searchResults = d.results;
      } finally { if (mine === seq) loading = false; }
    }, 350);
  }

  async function play(v) {
    await api('/api/youtube/play', { id: v.id });
    onplay?.();
  }

  const list = $derived(sub === 'search' ? (searchResults ?? []) : (cache.ytFeeds[sub] ?? []));
  const showSkeleton = $derived(loading && !list.length);
</script>

<div class="seg ytseg">
  <button class:on={sub === 'subscriptions'} onclick={() => (sub = 'subscriptions')}>Subscriptions</button>
  <button class:on={sub === 'recommendations'} onclick={() => (sub = 'recommendations')}>Recommended</button>
  <button class:on={sub === 'search'} onclick={() => (sub = 'search')}>Search</button>
</div>

{#if sub === 'search'}
  <div class="row srow">
    <input type="text" placeholder="Search YouTube" bind:value={search} oninput={onSearch} />
    {#if search}<button class="clr" onclick={() => { search = ''; searchResults = null; }} aria-label="Clear"><Icon name="x" size={16} /></button>{/if}
  </div>
{/if}

{#if showSkeleton}
  <div class="ylist">
    {#each Array(6) as _}<div class="yrow"><span class="ythumb sk"></span><span class="ymeta"><span class="skline"></span><span class="skline short"></span></span></div>{/each}
  </div>
{:else if !list.length}
  <p class="dim">
    {#if sub === 'search'}{searchResults ? 'No results.' : 'Search for something to watch.'}
    {:else}Nothing here right now.{/if}
  </p>
{:else}
  <div class="ylist">
    {#each list as v (v.id)}
      <button class="yrow" onclick={() => play(v)}>
        <span class="ythumb">
          <img use:fadeimg src={'/api/art/yt?id=' + v.id} alt="" loading="lazy" />
          {#if v.duration}<span class="dur mono">{v.duration}</span>{/if}
        </span>
        <span class="ymeta">
          <span class="ytitle">{v.title}</span>
          {#if v.channel}<span class="ychannel dim small">{v.channel}</span>{/if}
        </span>
        <span class="yplay"><Icon name="play" size={16} /></span>
      </button>
    {/each}
  </div>
{/if}

<style>
  .ytseg { margin-bottom: 4px; }
  .srow { margin-top: 12px; }
  .clr { width: 44px; padding: 0; justify-content: center; color: var(--muted); flex-shrink: 0; }
  .ylist { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
  .yrow {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0;
    background: none;
    text-align: left;
  }
  .ythumb {
    position: relative;
    width: 120px;
    aspect-ratio: 16 / 9;
    flex-shrink: 0;
    border-radius: 10px;
    overflow: hidden;
    background: var(--raise);
  }
  .ythumb img { width: 100%; height: 100%; object-fit: cover; }
  .ythumb.sk { animation: pulse 1.4s ease-in-out infinite; }
  .dur {
    position: absolute;
    bottom: 4px; right: 4px;
    background: rgba(0, 0, 0, 0.8);
    color: #fff;
    font-size: 11px;
    padding: 1px 5px;
    border-radius: 4px;
  }
  .ymeta { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .ytitle {
    font-size: 13.5px;
    line-height: 1.25;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .yplay { color: var(--accent); flex-shrink: 0; display: flex; }
  .skline { height: 12px; width: 100%; border-radius: 4px; background: var(--raise); animation: pulse 1.4s ease-in-out infinite; }
  .skline.short { width: 50%; margin-top: 4px; }
</style>
