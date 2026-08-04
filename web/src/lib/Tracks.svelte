<script>
  import { slideUp, fadeIn, slideDown, fadeOut } from './anim.js';
  import { portal } from './portal.js';
  import { live, api } from './state.svelte.js';

  let { onclose } = $props();

  const p = $derived(live.playing);

  function trackName(s, i) {
    const bits = [s.language, s.name].filter(Boolean);
    return bits.length ? bits.join(' · ') : `Track ${i + 1}`;
  }
</script>

<div use:portal use:fadeIn out:fadeOut class="scrim" onclick={onclose} role="presentation">
  <div use:slideUp out:slideDown class="sheet" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Audio and subtitles">
    {#if p}
      <h2>Subtitles</h2>
      <div class="list">
        <button class:on={!p.subtitleEnabled} onclick={() => api('/api/player/subtitle', { index: 'off' })}>Off</button>
        {#each p.subtitles as s, i}
          <button class:on={p.subtitleEnabled && p.currentSubtitle?.index === s.index} onclick={() => api('/api/player/subtitle', { index: s.index })}>
            {trackName(s, i)}
          </button>
        {/each}
      </div>
      <h2>Audio</h2>
      <div class="list">
        {#each p.audioStreams as s, i}
          <button class:on={p.currentAudioStream?.index === s.index} onclick={() => api('/api/player/audio', { index: s.index })}>
            {trackName(s, i)}
          </button>
        {/each}
      </div>
    {/if}
    <button class="close" onclick={onclose}>Done</button>
  </div>
</div>

<style>
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
    border-top: 1px solid var(--line);
    border-radius: 20px 20px 0 0;
    padding: 18px 16px max(18px, env(safe-area-inset-bottom));
    width: 100%;
    max-height: 75dvh;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  h2 {
    margin: 14px 0 8px;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
  }
  h2:first-child { margin-top: 0; }
  .list { display: flex; flex-direction: column; gap: 6px; }
  .list button { text-align: left; }
  .list button.on { border-color: var(--accent); color: var(--accent); }
  .close { width: 100%; margin-top: 16px; }
</style>
