<script>
  import { slideUp, fadeIn, slideDown, fadeOut } from './lib/anim.js';
  import { reducedMotion } from './lib/reduced-motion.js';
  import { onMount } from 'svelte';
  import { live, connect } from './lib/state.svelte.js';
  import { prefetchAll, refreshNow } from './lib/store.svelte.js';
  import { pullToRefresh } from './lib/pull.js';
  import Icon from './lib/Icon.svelte';
  import Remote from './lib/Remote.svelte';
  import Playing from './lib/Playing.svelte';
  import Library from './lib/Library.svelte';
  import Games from './lib/Games.svelte';
  import Screen from './lib/Screen.svelte';
  import House from './lib/House.svelte';

  const ICONS = {
    remote: 'M12 2a7 7 0 0 1 7 7v6a7 7 0 0 1-14 0V9a7 7 0 0 1 7-7Zm0 4.4a3.1 3.1 0 1 0 0 6.2 3.1 3.1 0 0 0 0-6.2Zm0 10.2a1.3 1.3 0 1 0 0 2.6 1.3 1.3 0 0 0 0-2.6Z',
    playing: 'M5 4.8c0-1.4 1.5-2.2 2.7-1.5l11.2 6.7c1.1.7 1.1 2.3 0 3L7.7 19.7c-1.2.7-2.7-.1-2.7-1.5V4.8Z',
    library: 'M3 5.5C3 4.7 3.7 4 4.5 4h5C10.3 4 11 4.7 11 5.5v13c0 .8-.7 1.5-1.5 1.5h-5C3.7 20 3 19.3 3 18.5v-13Zm10 0c0-.8.7-1.5 1.5-1.5h5c.8 0 1.5.7 1.5 1.5v7c0 .8-.7 1.5-1.5 1.5h-5c-.8 0-1.5-.7-1.5-1.5v-7Z',
    games: 'M7.5 6h9a5.5 5.5 0 0 1 5.4 6.6l-.9 4.4a2.8 2.8 0 0 1-5 1.1L14.6 16H9.4L8 18.1a2.8 2.8 0 0 1-5-1.1l-.9-4.4A5.5 5.5 0 0 1 7.5 6ZM8 9.2a.9.9 0 0 0-.9.9v.7h-.7a.9.9 0 1 0 0 1.8h.7v.7a.9.9 0 1 0 1.8 0v-.7h.7a.9.9 0 1 0 0-1.8h-.7v-.7A.9.9 0 0 0 8 9.2Zm8.4.2a1.1 1.1 0 1 0 0 2.2 1.1 1.1 0 0 0 0-2.2Zm-2.4 2.8a1.1 1.1 0 1 0 0 2.2 1.1 1.1 0 0 0 0-2.2Z',
    screen: 'M3 6.5C3 5.7 3.7 5 4.5 5h15c.8 0 1.5.7 1.5 1.5v9c0 .8-.7 1.5-1.5 1.5h-15C3.7 17 3 16.3 3 15.5v-9ZM8 19.5c0-.6.4-1 1-1h6a1 1 0 1 1 0 2H9a1 1 0 0 1-1-1Z',
    house: 'M11 3.8a1.5 1.5 0 0 1 2 0l7.5 6.7c.9.9.3 2.5-1 2.5H19v6.5c0 .8-.7 1.5-1.5 1.5h-11C5.7 21 5 20.3 5 19.5V13h-.5c-1.3 0-1.9-1.6-1-2.5L11 3.8Z',
  };

  const TABS = [
    { id: 'remote', label: 'Remote' },
    { id: 'playing', label: 'Playing' },
    { id: 'library', label: 'Library' },
    { id: 'games', label: 'Games' },
    { id: 'screen', label: 'Screen' },
    { id: 'house', label: 'House' },
  ];

  const THEMES = [
    { id: 'dark', name: 'Dark', blurb: 'Graphite, made for the sofa', chip: '#16161a' },
    { id: 'oled', name: 'Black', blurb: 'True black, easy on OLED and eyes', chip: '#000000' },
    { id: 'light', name: 'Light', blurb: 'Clean and bright for daytime', chip: '#f2f2f6' },
  ];
  const THEME_BAR = { dark: '#0a0a0c', oled: '#000000', light: '#f2f2f6' };
  const LEGACY = { cinema: 'dark', midnight: 'oled', paper: 'light' };

  let tab = $state(localStorage.getItem('couch.tab') || 'remote');
  $effect(() => localStorage.setItem('couch.tab', tab));

  let stored = localStorage.getItem('couch.theme') || 'dark';
  let theme = $state(LEGACY[stored] || stored);
  let themeSheet = $state(false);
  $effect(() => {
    localStorage.setItem('couch.theme', theme);
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name=theme-color]')?.setAttribute('content', THEME_BAR[theme]);
  });

  onMount(() => { connect(); prefetchAll(); });

  // Pull-to-refresh indicator state.
  let pullProgress = $state(0);
  let refreshing = $state(false);

  const statusText = $derived(
    !live.connected ? 'reconnecting'
    : live.kodiDown ? 'Kodi is down'
    : live.game.suspended ? 'game paused'
    : live.game.active ? 'in game'
    : ''
  );
</script>

<header>
  <span class="brand display">Couch</span>
  {#if statusText}<span class="status" class:warn={!live.connected || live.kodiDown}>{statusText}</span>{/if}
  <span class="grow"></span>
  {#if live.pad.connected}
    <span class="padchip" class:low={live.pad.battery !== null && live.pad.battery <= 15}>
      <span class="paddot"></span>
      {#if live.pad.battery === null}
        <span class="mono">?</span>
      {:else}
        <span class="batt" title={`${live.pad.battery}%`}>
          <span class="battfill" style:width={`${live.pad.battery}%`}></span>
        </span>
      {/if}
      {#if live.pad.charging}<span class="chg mono">+</span>{/if}
    </span>
  {/if}
  <button class="themebtn" onclick={() => (themeSheet = true)} aria-label="Change theme">
    <span class="swatch"></span>
  </button>
</header>

{#if live.error}
  <div class="toast">{live.error}</div>
{/if}

<div class="ptr" style:opacity={refreshing ? 1 : Math.min(1, pullProgress)}>
  <span class="ptr-spin" class:spinning={refreshing} style:transform={`rotate(${refreshing ? 0 : pullProgress * 270}deg)`}>
    <Icon name="rotate-cw" size={20} />
  </span>
</div>

<main
  class:withstrip={live.playing && tab !== "playing"}
  use:pullToRefresh={{ refresh: refreshNow, onPull: (p) => (pullProgress = p), onRefresh: (r) => (refreshing = r) }}
>
  {#if tab === 'remote'}<Remote />{/if}
  {#if tab === 'playing'}<Playing />{/if}
  {#if tab === 'library'}<Library oncast={() => (tab = 'playing')} />{/if}
  {#if tab === 'games'}<Games />{/if}
  {#if tab === 'screen'}<Screen />{/if}
  {#if tab === 'house'}<House />{/if}
</main>

{#if live.playing && tab !== 'playing'}
  <button class="ministrip" onclick={() => (tab = 'playing')}>
    {#if live.playing.art.poster}
      <img src={'/api/art/kodi?p=' + encodeURIComponent(live.playing.art.poster)} alt="" />
    {/if}
    <span class="mini-title">
      {live.playing.showtitle ? `${live.playing.showtitle}: ` : ''}{live.playing.title}
    </span>
    <span class="mini-state"><Icon name={live.playing.speed ? 'play' : 'pause'} size={13} /></span>
  </button>
{/if}

<nav>
  {#each TABS as t}
    <button class:active={tab === t.id} onclick={() => (tab = t.id)} aria-label={t.label}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[t.id]} /></svg>
      <span>{t.label}</span>
    </button>
  {/each}
</nav>

{#if themeSheet}
  <div use:fadeIn={{ reduced: $reducedMotion }} out:fadeOut={{ reduced: $reducedMotion }} class="scrim" onclick={() => (themeSheet = false)} role="presentation">
    <div use:slideUp={{ reduced: $reducedMotion }} out:slideDown={{ reduced: $reducedMotion }} class="sheet" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Theme">
      <h2>Theme</h2>
      {#each THEMES as t}
        <button class="themerow" class:on={theme === t.id} onclick={() => { theme = t.id; }}>
          <span class="chipbox" style:background={t.chip} class:lightchip={t.id === 'light'}></span>
          <span class="grow tmeta">
            <span>{t.name}</span>
            <span class="dim small">{t.blurb}</span>
          </span>
          {#if theme === t.id}<span class="tick"><Icon name="check" size={16} /></span>{/if}
        </button>
      {/each}
      <button class="close" onclick={() => (themeSheet = false)}>Done</button>
      <p class="buildstamp mono">build {__BUILD__}</p>
    </div>
  </div>
{/if}

<style>
  header {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: calc(var(--topbar) + env(safe-area-inset-top));
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 14px 0 16px;
    padding-top: env(safe-area-inset-top);
    background: color-mix(in srgb, var(--bg) 82%, transparent);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    z-index: 10;
  }
  .brand { font-size: 17px; }
  .status { font-size: 13px; color: var(--muted); }
  .status.warn { color: var(--danger); }

  .padchip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    color: var(--muted);
  }
  .paddot { width: 6px; height: 6px; border-radius: 50%; background: var(--ok); }
  .padchip.low { color: var(--danger); }
  .padchip.low .paddot { background: var(--danger); }
  /* Battery drawn as a bar: the case borders in the chip colour, the fill
     tracks charge, and the nub is the little terminal on the right. */
  .batt {
    position: relative;
    width: 23px;
    height: 11px;
    border: 1.5px solid currentColor;
    border-radius: 3.5px;
    padding: 1.5px;
    opacity: 0.9;
  }
  .batt::after {
    content: '';
    position: absolute;
    right: -4px;
    top: 50%;
    transform: translateY(-50%);
    width: 2px;
    height: 5px;
    border-radius: 0 1.5px 1.5px 0;
    background: currentColor;
  }
  .battfill {
    display: block;
    height: 100%;
    border-radius: 1.5px;
    background: var(--ok);
    min-width: 2px;
  }
  .padchip.low .battfill { background: var(--danger); }
  .chg { margin-left: 2px; }

  .themebtn { padding: 7px; border-radius: 50%; background: var(--raise); }
  .swatch {
    width: 15px; height: 15px;
    border-radius: 50%;
    background: conic-gradient(#16161a 0 33%, #000 33% 66%, #f2f2f6 66%);
    border: 1px solid var(--line);
  }

  .ptr {
    position: fixed;
    top: calc(var(--topbar) + env(safe-area-inset-top) - 6px);
    left: 50%;
    transform: translateX(-50%);
    width: 36px; height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 50%;
    color: var(--accent);
    z-index: 8;
    pointer-events: none;
  }
  .ptr-spin { display: flex; }
  /* Own compositor layer, so the rotation keeps running while the main thread
     is busy - see the matching note on .tilespin in Library.svelte. */
  .ptr-spin.spinning {
    animation: ptrspin 0.9s linear infinite;
    will-change: transform;
    backface-visibility: hidden;
  }
  @keyframes ptrspin { to { transform: rotate(360deg); } }

  .toast {
    position: fixed;
    top: calc(var(--topbar) + env(safe-area-inset-top) + 8px);
    left: 50%;
    transform: translateX(-50%);
    background: var(--danger);
    color: #fff;
    padding: 8px 14px;
    border-radius: 10px;
    font-size: 13px;
    z-index: 30;
    max-width: 90vw;
  }

  .ministrip {
    position: fixed;
    bottom: calc(var(--tabbar) + 6px + env(safe-area-inset-bottom));
    left: 10px; right: 10px;
    display: flex;
    align-items: center;
    gap: 10px;
    background: color-mix(in srgb, var(--card) 78%, transparent);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid var(--line);
    border-radius: 13px;
    padding: 7px 12px;
    z-index: 9;
    text-align: left;
  }
  .ministrip img { width: 24px; height: 36px; object-fit: cover; border-radius: 5px; }
  .mini-title {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 13px;
    font-weight: 500;
  }
  .mini-state { color: var(--accent); display: flex; }

  nav {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    height: calc(var(--tabbar) + env(safe-area-inset-bottom));
    padding-bottom: env(safe-area-inset-bottom);
    display: flex;
    background: color-mix(in srgb, var(--bg) 86%, transparent);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border-top: 1px solid var(--line);
    z-index: 10;
  }
  nav button {
    flex: 1;
    min-width: 0;
    padding: 7px 0 0;
    background: none;
    border-radius: 0;
    color: var(--faint);
    font-size: 10.5px;
    font-weight: 500;
    letter-spacing: 0.01em;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    overflow: hidden;
    white-space: nowrap;
  }
  nav button:active { background: none; }
  nav svg { width: 21px; height: 21px; fill: currentColor; }
  nav button.active { color: var(--accent); }

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
    padding: 18px 16px max(18px, env(safe-area-inset-bottom));
    width: 100%;
  }
  .sheet h2 {
    margin: 0 0 12px;
    font-size: 13px;
    font-weight: 600;
    color: var(--muted);
  }
  .themerow {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    text-align: left;
    margin-bottom: 8px;
    background: var(--raise);
  }
  .themerow.on { outline: 2px solid var(--accent); outline-offset: -2px; }
  .chipbox {
    width: 28px; height: 28px;
    border-radius: 9px;
    border: 1px solid var(--line);
    flex-shrink: 0;
  }
  .chipbox.lightchip { border-color: rgba(20, 20, 30, 0.15); }
  .tmeta { display: flex; flex-direction: column; gap: 1px; }
  .tick { color: var(--accent); display: flex; }
  .close { width: 100%; margin-top: 10px; }
  .buildstamp { text-align: center; color: var(--faint); font-size: 11px; margin: 10px 0 0; }
</style>
