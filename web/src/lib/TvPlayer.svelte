<script>
  // The "Play on TV" flow for the LG's native Jellyfin app: kick the handoff
  // off, paint each stage as the server reports it (long-poll on seq), then
  // become a small player card driving the TV session - play/pause, scrub,
  // stop. The server's watcher brings the TV back to the PC input after the
  // playback ends; this card only has to notice and bow out.
  import { onMount } from 'svelte';
  import { fadeIn, fadeOut, slideUp, slideDown } from './anim.js';
  import { reducedMotion } from './reduced-motion.js';
  import { portal } from './portal.js';
  import { api, fmtTime } from './state.svelte.js';
  import Icon from './Icon.svelte';

  let { item, onclose } = $props();

  let stage = $state('starting');
  let error = $state(null);
  let failedStage = $state(null);
  let playingName = $state(item.name);

  // Session snapshot + a local clock so the bar moves between the 2s polls.
  let sess = $state(null);
  let syncedAt = $state(0);
  let now = $state(Date.now());
  let ended = $state(false);

  let scrubbing = $state(false);
  let scrubPct = $state(0);
  let pending = $state(false);

  const STAGE_COPY = {
    starting: 'Talking to the box',
    waking: 'Waking the TV',
    launching: 'Opening the Jellyfin app',
    connecting: 'Waiting for the TV app to check in',
  };

  const pos = $derived.by(() => {
    if (!sess) return 0;
    if (sess.paused) return sess.position;
    return Math.min(sess.duration || Infinity, sess.position + (now - syncedAt) / 1000);
  });
  const pct = $derived(sess?.duration ? (pos / sess.duration) * 100 : 0);
  const displayPct = $derived(scrubbing ? scrubPct : pct);

  onMount(() => {
    let dead = false;
    const tick = setInterval(() => (now = Date.now()), 1000);

    (async () => {
      let st;
      try {
        st = await api('/api/tv/play', { itemId: item.id });
      } catch (e) {
        if (!dead) { stage = 'failed'; error = e.message; }
        return;
      }
      // Follow the stages until they resolve one way or the other.
      while (!dead && !['playing', 'failed'].includes(st.stage)) {
        stage = st.stage;
        try {
          st = await api(`/api/tv/play/status?seq=${st.seq}`);
        } catch {
          await new Promise((r) => setTimeout(r, 2000));
          continue;
        }
      }
      if (dead) return;
      stage = st.stage;
      error = st.error;
      failedStage = st.failedStage;
      if (st.item?.name) playingName = st.item.name;
      // Now playing: keep the card honest with a light session poll.
      while (!dead && stage === 'playing') {
        try {
          const s = await api('/api/tv/session');
          if (dead) break;
          if (!s.active) {
            // Stopped on the TV, finished, or handed elsewhere: done here.
            ended = true;
            stage = 'ended';
            break;
          }
          if (!scrubbing && !pending) {
            sess = s;
            syncedAt = Date.now();
          }
          if (s.item?.name) playingName = s.item.name;
        } catch { /* box briefly unreachable; keep the last picture */ }
        await new Promise((r) => setTimeout(r, 2000));
      }
    })();

    return () => { dead = true; clearInterval(tick); };
  });

  const pctAt = (ev, el) => {
    const r = el.getBoundingClientRect();
    return Math.max(0, Math.min(100, ((ev.clientX - r.left) / r.width) * 100));
  };

  function seekDown(ev) {
    if (!sess?.duration) return;
    ev.currentTarget.setPointerCapture(ev.pointerId);
    scrubbing = true;
    scrubPct = pctAt(ev, ev.currentTarget);
  }
  function seekMove(ev) {
    if (scrubbing) scrubPct = pctAt(ev, ev.currentTarget);
  }
  async function seekUp(ev) {
    if (!scrubbing) return;
    scrubPct = pctAt(ev, ev.currentTarget);
    scrubbing = false;
    const target = (scrubPct / 100) * (sess?.duration || 0);
    // Hold the scrubbed spot optimistically; the TV app takes a beat to obey.
    sess = { ...sess, position: target };
    syncedAt = Date.now();
    pending = true;
    try { await api('/api/tv/seek', { seconds: Math.round(target) }); } catch { /* toast shown by api() */ }
    setTimeout(() => (pending = false), 2500);
  }

  async function playpause() {
    if (!sess) return;
    sess = { ...sess, position: pos, paused: !sess.paused };
    syncedAt = Date.now();
    try { await api('/api/tv/playpause', {}); } catch { /* toast shown by api() */ }
  }

  async function stop() {
    try { await api('/api/tv/stop', {}); } catch { /* toast shown by api() */ }
    ended = true;
    stage = 'ended';
  }
</script>

<div use:portal use:fadeIn={{ reduced: $reducedMotion }} out:fadeOut={{ reduced: $reducedMotion }} class="scrim" onclick={() => onclose?.()} role="presentation">
  <div use:slideUp={{ reduced: $reducedMotion }} out:slideDown={{ reduced: $reducedMotion }} class="card" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Play on TV">
    {#if stage === 'failed'}
      <div class="head">
        <span class="title">{item.name}</span>
        <button class="closebtn" onclick={() => onclose?.()} aria-label="Close"><Icon name="x" size={16} /></button>
      </div>
      <div class="failbox">
        <p class="failmsg">{error || 'The handoff to the TV failed.'}</p>
        {#if failedStage}<p class="dim small">Stage that failed: {failedStage}</p>{/if}
      </div>
      <button onclick={() => onclose?.()}>Close</button>
    {:else if stage === 'ended'}
      <div class="head">
        <span class="title">{playingName}</span>
        <button class="closebtn" onclick={() => onclose?.()} aria-label="Close"><Icon name="x" size={16} /></button>
      </div>
      <p class="dim">Playback finished. The TV comes back to the PC on its own.</p>
      <button onclick={() => onclose?.()}>Done</button>
    {:else if stage === 'playing'}
      <div class="head">
        <span class="onchip"><span class="dot"></span>Playing on TV</span>
        <button class="closebtn" onclick={() => onclose?.()} aria-label="Close"><Icon name="x" size={16} /></button>
      </div>
      <div class="title big">{playingName}</div>
      {#if sess}
        <div
          class="seekbar"
          class:dragging={scrubbing}
          onpointerdown={seekDown}
          onpointermove={seekMove}
          onpointerup={seekUp}
          onpointercancel={seekUp}
          role="slider"
          tabindex="0"
          aria-label="Seek"
          aria-valuemin="0"
          aria-valuemax="100"
          aria-valuenow={Math.round(displayPct)}
        >
          <div class="seektrack">
            <div class="seekfill" style:width={displayPct + '%'}></div>
            <div class="seekthumb" style:left={displayPct + '%'}></div>
          </div>
        </div>
        <div class="row times mono small">
          <span>{fmtTime(scrubbing ? (scrubPct / 100) * (sess.duration || 0) : pos)}</span>
          <span class="grow"></span>
          <span class="dim">{fmtTime(sess.duration || 0)}</span>
        </div>
        <div class="transport">
          <button class="tbtn main primary" onclick={playpause} aria-label="Play or pause">
            <Icon name={sess.paused ? 'play' : 'pause'} size={22} />
          </button>
          <button class="tbtn stopbtn danger" onclick={stop} aria-label="Stop">
            <Icon name="stop" size={18} />
          </button>
        </div>
      {:else}
        <p class="dim small">Starting on the TV, a few seconds...</p>
      {/if}
    {:else}
      <div class="head">
        <span class="title">{item.name}</span>
        <button class="closebtn" onclick={() => onclose?.()} aria-label="Close"><Icon name="x" size={16} /></button>
      </div>
      <div class="stagebox">
        <span class="spin"></span>
        <span>{STAGE_COPY[stage] || 'Working on it'}</span>
      </div>
      <p class="dim small">Handing playback to the TV's own Jellyfin app for full quality.</p>
    {/if}
  </div>
</div>

<style>
  .scrim {
    position: fixed;
    inset: 0;
    background: var(--scrim);
    z-index: 25;
    display: flex;
    align-items: flex-end;
  }
  .card {
    background: var(--card);
    border-radius: 22px 22px 0 0;
    padding: 16px 16px max(18px, env(safe-area-inset-bottom));
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .head { display: flex; align-items: center; gap: 10px; }
  .title {
    flex: 1;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .title.big { font-size: 18px; font-weight: 700; }
  .closebtn {
    width: 34px; height: 34px;
    padding: 0;
    border-radius: 50%;
    justify-content: center;
    color: var(--muted);
    flex-shrink: 0;
  }

  .stagebox {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 2px;
    font-size: 15px;
  }
  .spin {
    width: 20px; height: 20px;
    flex-shrink: 0;
    border-radius: 50%;
    border: 2px solid color-mix(in srgb, var(--ink) 25%, transparent);
    border-top-color: var(--accent);
    animation: tvspin 0.7s linear infinite;
  }
  @keyframes tvspin { to { transform: rotate(360deg); } }

  .onchip {
    flex: 1;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 12px;
    font-weight: 600;
    color: var(--accent);
  }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }

  .failbox { padding: 4px 2px; }
  .failmsg { color: var(--danger); margin: 0 0 4px; }

  /* Same custom scrubber as the Playing page: tall touch target, thin track,
     touch-action none so a drag seeks instead of scrolling. */
  .seekbar {
    position: relative;
    padding: 15px 0;
    margin: 0 2px;
    touch-action: none;
    cursor: pointer;
    user-select: none;
    -webkit-user-select: none;
  }
  .seektrack { position: relative; height: 6px; border-radius: 999px; background: var(--raise); }
  .seekfill { position: absolute; top: 0; left: 0; bottom: 0; border-radius: 999px; background: var(--accent); }
  .seekthumb {
    position: absolute;
    top: 50%;
    width: 16px; height: 16px;
    margin: -8px 0 0 -8px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.45);
  }
  .seekbar:not(.dragging) .seekfill { transition: width 1s linear; }
  .seekbar:not(.dragging) .seekthumb { transition: left 1s linear; }
  .seekbar.dragging .seekthumb { transform: scale(1.35); }
  .times { margin: 0 2px; }

  .transport {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 14px;
    margin-top: 4px;
  }
  .tbtn { border-radius: 50%; padding: 0; justify-content: center; }
  .tbtn.main { width: 62px; height: 62px; }
  .stopbtn { width: 50px; height: 50px; }
</style>
