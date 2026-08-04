<script>
  import { onMount } from 'svelte';
  import { live, api } from './state.svelte.js';
  import { cache, loadServices, ui } from './store.svelte.js';
  import Icon from './Icon.svelte';

  let tvStatus = $state(null);
  let tvBusy = $state(false);
  let bulbs = $state([]);
  let lightsBusy = $state(false);
  let padBusy = $state(false);
  let message = $state('');

  function loadTv() { api('/api/tv').then((d) => (tvStatus = d.status)).catch(() => {}); }
  function loadLights() { api('/api/lights').then((d) => (bulbs = d.bulbs)).catch(() => {}); }
  onMount(() => { loadTv(); loadLights(); });

  // On returning to the app, re-read the things that change outside it: TV
  // power (physical remote), bulbs (Alexa/wall switch), system health, services.
  $effect(() => {
    ui.focusTick;
    loadTv();
    loadLights();
    loadHealth();
    loadServices().catch(() => {});
  });

  // The gentle 30s poll refreshes health only (services come via the cache);
  // TV and lights are slow to dial, so they stay on focus/pull/manual.
  $effect(() => { ui.pollTick; loadHealth(); });

  async function tv(cmd) {
    tvBusy = true;
    try {
      await api(`/api/tv/${cmd}`, {});
      const d = await api('/api/tv?fresh=1');
      tvStatus = d.status;
    } finally { tvBusy = false; }
  }

  async function lightsCmd(cmd, dim) {
    lightsBusy = true;
    try {
      await api(`/api/lights/${cmd}`, dim ? { dim } : {});
      const d = await api('/api/lights?fresh=1');
      bulbs = d.bulbs;
    } finally { lightsBusy = false; }
  }

  let dimTimer = null;
  function setDim(ev) {
    const v = Number(ev.target.value);
    clearTimeout(dimTimer);
    dimTimer = setTimeout(() => lightsCmd('dim', v), 250);
  }

  async function pad(cmd) {
    padBusy = true;
    try { await api(`/api/pad/${cmd}`, {}); } finally { padBusy = false; }
  }

  async function sendMessage() {
    if (!message.trim()) return;
    await api('/api/notify', { message: message.trim() });
    message = '';
  }

  let health = $state(null);
  let restarting = $state(false);
  const services = $derived(cache.services ?? []);
  let downloads = $state([]);
  let scene = $state(null);

  // Raw fetch, not api(): a background poll shouldn't raise the error toast
  // when qBittorrent is behind the VPN and unreachable.
  async function loadDownloads() {
    try {
      const res = await fetch('/api/downloads');
      if (res.ok) downloads = (await res.json()).downloads;
    } catch { /* leave the card hidden */ }
  }

  onMount(() => {
    loadDownloads();
    const t = setInterval(loadDownloads, 5000);
    return () => clearInterval(t);
  });

  // Scenes compose the controls that already exist; each step is best-effort
  // so one failure (say no bulbs answer) does not abort the rest.
  async function runScene(name) {
    scene = name;
    const tryStep = (fn) => fn().catch(() => {});
    try {
      if (name === 'movie') {
        await tryStep(() => api('/api/tv/on', {}));
        await tryStep(() => api('/api/lights/warm', {}));
        await tryStep(() => api('/api/lights/dim', { dim: 12 }));
      } else if (name === 'bedtime') {
        await tryStep(() => api('/api/games/quit', {}));
        await tryStep(() => api('/api/player/stop', {}));
        await tryStep(() => api('/api/lights/off', {}));
        await tryStep(() => api('/api/pad/disconnect', {}));
        await tryStep(() => api('/api/tv/off', {}));
      }
    } finally {
      setTimeout(() => (scene = null), 1500);
    }
  }

  // Sleep timer: stop playback and turn the TV off after a delay. Held in the
  // browser tab; a note says as much.
  let sleepAt = $state(null);
  let sleepTimer = null;
  let sleepNow = $state(Date.now());
  function setSleep(mins) {
    clearTimeout(sleepTimer);
    if (!mins) { sleepAt = null; return; }
    sleepAt = Date.now() + mins * 60000;
    sleepTimer = setTimeout(async () => {
      sleepAt = null;
      await api('/api/player/stop', {}).catch(() => {});
      await api('/api/tv/off', {}).catch(() => {});
    }, mins * 60000);
  }
  onMount(() => {
    const t = setInterval(() => (sleepNow = Date.now()), 1000);
    return () => { clearInterval(t); clearTimeout(sleepTimer); };
  });
  const sleepLeft = $derived(sleepAt ? Math.max(0, Math.round((sleepAt - sleepNow) / 60000)) : 0);
  const fmtSpeed = (b) => (b > 1e6 ? (b / 1e6).toFixed(1) + ' MB/s' : Math.round(b / 1e3) + ' KB/s');

  function loadHealth() {
    api('/api/health').then((d) => (health = d)).catch(() => {});
  }

  async function restartKodi() {
    if (!confirm('Restart Kodi? The TV drops to a black screen for a few seconds while the watchdog brings it back.')) return;
    restarting = true;
    try {
      await api('/api/system/kodi-restart', {});
      setTimeout(() => { loadHealth(); restarting = false; }, 8000);
    } catch { restarting = false; }
  }

  const fmtFree = (d) => (d.free / 1e9).toFixed(0) + ' GB free';
  const upDays = (s) => (s >= 172800 ? Math.floor(s / 86400) + ' days' : Math.floor(s / 3600) + ' hours');

  // Reflect real state on the On/Off buttons instead of always lighting On.
  const tvOn = $derived(!!tvStatus && tvStatus.startsWith('on'));
  const anyLightOn = $derived(bulbs.some((b) => b.on));
</script>

<div class="card">
  <h2>Scenes</h2>
  <div class="row">
    <button class="scene grow" class:primary={scene === 'movie'} onclick={() => runScene('movie')}>
      <Icon name="play" size={16} />Movie night
    </button>
    <button class="scene grow" class:primary={scene === 'bedtime'} onclick={() => runScene('bedtime')}>
      <Icon name="power" size={16} />Bedtime
    </button>
  </div>
  <div class="row sleeprow">
    <span class="small dim grow">
      {#if sleepAt}Sleep in {sleepLeft} min{:else}Sleep timer{/if}
    </span>
    {#each [30, 60, 90] as m}
      <button class="sleepbtn small" onclick={() => setSleep(m)}>{m}m</button>
    {/each}
    {#if sleepAt}<button class="sleepbtn small" onclick={() => setSleep(0)}>Off</button>{/if}
  </div>
</div>

{#if downloads.length}
  <div class="card">
    <h2>Downloading</h2>
    {#each downloads as d}
      <div class="dl">
        <div class="row dlhead">
          <span class="dlname grow">{d.name}</span>
          <span class="mono small dim">{d.state === 'downloading' ? fmtSpeed(d.speed) : d.state}</span>
        </div>
        <span class="bar"><span style:width={(d.progress * 100) + '%'}></span></span>
      </div>
    {/each}
  </div>
{/if}

<div class="card">
  <h2>TV {#if tvStatus}<span class="dim">· {tvStatus}</span>{/if}</h2>
  <div class="row wrap">
    <button class:primary={tvOn} disabled={tvBusy} onclick={() => tv('on')}>On</button>
    <button class:primary={!!tvStatus && !tvOn} disabled={tvBusy} onclick={() => { if (confirm('Turn the TV off?')) tv('off'); }}>Off</button>
    <button disabled={tvBusy} onclick={() => tv('hdmi2')}>PC (HDMI 2)</button>
    <button disabled={tvBusy} onclick={() => tv('hdmi1')}>HDMI 1</button>
  </div>
</div>

<div class="card">
  <h2>Lights</h2>
  {#if bulbs.length === 0}
    <p class="dim small">No bulbs answered yet. Powered-off wall switches keep bulbs silent.</p>
  {:else}
    {#each bulbs as b}
      <div class="row small bulb mono">
        <span class="bdot" class:on={b.on}></span>
        <span>{b.ip}</span>
        <span class="dim">{b.on ? `${b.dimming}% · ${b.mode}` : 'off'}</span>
      </div>
    {/each}
  {/if}
  <div class="row wrap">
    <button class:primary={anyLightOn} disabled={lightsBusy} onclick={() => lightsCmd('on')}>On</button>
    <button class:primary={bulbs.length > 0 && !anyLightOn} disabled={lightsBusy} onclick={() => lightsCmd('off')}>Off</button>
    <button disabled={lightsBusy} onclick={() => lightsCmd('warm')}>Warm</button>
    <button disabled={lightsBusy} onclick={() => lightsCmd('cool')}>Cool</button>
  </div>
  <div class="row" style="margin-top:10px">
    <span class="small dim">Dim</span>
    <input class="grow" type="range" min="10" max="100" value={bulbs[0]?.dimming ?? 60} oninput={setDim} disabled={lightsBusy || bulbs.length === 0} />
  </div>
</div>

<div class="card">
  <h2>Controller</h2>
  <div class="row wrap">
    <span class="grow small">
      {#if live.pad.connected}
        Connected{#if live.pad.battery !== null}, {live.pad.battery}%{live.pad.charging ? ', charging' : ''}{/if}
      {:else}
        Not connected. Connecting from here only works if the pad is awake.
      {/if}
    </span>
    {#if live.pad.connected}
      <button disabled={padBusy} onclick={() => pad('disconnect')}>Disconnect</button>
    {:else}
      <button class="primary" disabled={padBusy} onclick={() => pad('connect')}>Connect</button>
    {/if}
  </div>
</div>

<div class="card">
  <h2>System</h2>
  {#if health}
    <div class="stats mono small">
      <span>CPU {health.cpuTemp ?? '?'}°</span>
      {#if health.gpu}<span>GPU {health.gpu.temp}° · {health.gpu.util}%</span>{/if}
      <span>load {health.load}</span>
      <span>mem {health.memUsedPct}%</span>
      <span>up {upDays(health.uptime)}</span>
    </div>
    {#each health.disks as d}
      <div class="disk small">
        <span class="mono">{d.mount === '/' ? 'system' : 'media'}</span>
        <span class="bar"><span style:width={d.usedPct + '%'} class:hot={d.usedPct > 90}></span></span>
        <span class="dim mono">{fmtFree(d)}</span>
      </div>
    {/each}
    <div class="services">
      {#each Object.entries(health.services) as [name, state]}
        <span class="svc small" class:down={state !== 'active'}>
          <span class="dot"></span>{name}
        </span>
      {/each}
    </div>
    <div class="row" style="margin-top:10px">
      <button disabled={restarting} onclick={restartKodi}>{restarting ? 'Restarting...' : 'Restart Kodi'}</button>
      <button onclick={loadHealth}>Refresh</button>
    </div>
  {:else}
    <p class="dim small">Loading...</p>
  {/if}
</div>

<div class="card">
  <h2>Services</h2>
  {#if services.length === 0}
    <div class="svcgrid">
      {#each Array(8) as _}<span class="sk-svc"></span>{/each}
    </div>
  {:else}
    <div class="svcgrid">
      {#each services as s (s.name)}
        <a class="svclink" href={s.url} target="_blank" rel="noreferrer">
          <span class="svcdot" class:down={!s.up}></span>
          <span class="svcmeta">
            <span class="svcname">{s.name}</span>
            <span class="dim">{s.desc}</span>
          </span>
        </a>
      {/each}
    </div>
  {/if}
</div>

<div class="card">
  <h2>Message the TV</h2>
  <div class="row">
    <input type="text" placeholder="Shows as a toast on screen" bind:value={message} onkeydown={(e) => e.key === 'Enter' && sendMessage()} />
    <button onclick={sendMessage} disabled={!message.trim()}>Send</button>
  </div>
</div>

<style>
  .bulb { margin-bottom: 8px; }
  .bdot { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); flex-shrink: 0; }
  .bdot.on { background: var(--accent); }

  .stats { display: flex; flex-wrap: wrap; gap: 6px 14px; color: var(--muted); margin-bottom: 10px; }
  .disk { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
  .disk .mono:first-child { width: 52px; color: var(--muted); }
  .bar { flex: 1; display: block; height: 4px; background: var(--line); border-radius: 2px; overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--accent); }
  .bar span.hot { background: var(--danger); }
  .services { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .svc {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 3px 9px;
    color: var(--muted);
  }
  .svc .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--ok); }
  .svc.down { color: var(--danger); }
  .svc.down .dot { background: var(--danger); }

  .svcgrid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
  .svclink {
    display: flex;
    align-items: center;
    gap: 9px;
    background: var(--raise);
    border-radius: 12px;
    padding: 10px 12px;
    text-decoration: none;
    color: var(--ink);
  }
  .svclink:active { background: var(--press); }
  .svcdot { width: 7px; height: 7px; border-radius: 50%; background: var(--ok); flex-shrink: 0; }
  .svcdot.down { background: var(--danger); }
  .svcmeta { display: flex; flex-direction: column; min-width: 0; }
  .sk-svc { height: 54px; border-radius: 12px; background: var(--raise); animation: pulse 1.4s ease-in-out infinite; }
  .svcname { font-weight: 500; font-size: 14px; }
  .svcmeta .dim { font-size: 11.5px; }

  .scene { padding: 13px; }
  .sleeprow { margin-top: 10px; }
  .sleepbtn { padding: 7px 10px; }
  .dl { margin-bottom: 12px; }
  .dl:last-child { margin-bottom: 0; }
  .dlhead { margin-bottom: 6px; }
  .dlname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
  .bar { display: block; height: 5px; background: var(--raise); border-radius: 3px; overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--accent); }
</style>
