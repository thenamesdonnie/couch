<script>
  // The picture in picture window that floats over a game on the TV: a 16:9
  // rectangle standing in for the television, with a smaller rectangle inside
  // it standing in for the show. Drag the small one, the real picture moves.
  //
  // Two rules make it feel direct rather than remote:
  //   1. the local rectangle moves on the finger, not on the reply, so nothing
  //      waits for the box, and
  //   2. the television is still the authority - pipd clamps the picture to the
  //      screen and snaps it flush to a near edge, so where it ENDS UP is often
  //      not where the finger asked. Every answer is adopted back, except while
  //      a finger is down (adopting mid-drag would fight it).
  //
  // Coordinates are normalised 0..1 of the output the whole way through, so a
  // drag that ends at the same place on the phone lands at the same place on
  // the TV whatever resolution the box is running.
  import { onMount } from 'svelte';
  import { api } from './state.svelte.js';
  import Icon from './Icon.svelte';

  // pipd only exists while a game is wrapped in gamescope with a video over it,
  // which is rare. Absent is the ordinary state and gets said plainly.
  let pip = $state(null);
  let frame; // the TV rectangle, the reference for every drag
  let dragging = $state(false);
  let sizing = false; // a finger is on the size slider
  let fading = false; // ...or the fade one

  let box = $state({ nx: 0.66, ny: 0.05, nw: 0.3, nh: 0.17 });
  let sizePct = $state(30);
  let opPct = $state(100);

  const running = $derived(pip?.running === true);
  const visible = $derived(pip?.visible !== false);
  const mediaName = $derived(
    pip?.media ? decodeURIComponent(String(pip.media).split(/[/\\]/).pop() || '') : '',
  );

  function adopt(d) {
    if (!d) return;
    pip = d;
    if (!d.running) return;
    // Position and size are adopted separately, because different fingers hold
    // them: a drag owns nx/ny, the size slider owns nw/nh (and its own value,
    // which must not be rewritten under the thumb). One guard for both meant a
    // corner press inside the slider's settle window drew the rectangle
    // nowhere near where the picture had actually gone, hanging over the edge
    // of the television.
    if (!d.normalised) return;
    const n = d.normalised;
    if (!dragging) box = { ...box, nx: n.nx, ny: n.ny };
    if (!sizing) {
      box = { ...box, nw: n.nw, nh: n.nh };
      sizePct = Math.round(n.nw * 100);
    }
    if (typeof d.opacity === 'number' && !fading) opPct = Math.round(d.opacity * 100);
  }

  // Raw fetch, not api(): the daemon is missing most evenings and a background
  // poll finding nothing must never raise the error toast.
  async function load() {
    try {
      const res = await fetch('/api/pip', { cache: 'no-store' });
      if (res.ok) adopt(await res.json());
    } catch { /* keep the last reading */ }
  }

  onMount(() => {
    load();
    const t = setInterval(() => {
      if (document.visibilityState === 'visible' && !dragging) load();
    }, 4000);
    return () => clearInterval(t);
  });

  async function place(body) {
    try { adopt(await api('/api/pip/place', body)); } catch { /* the toast has it */ }
  }

  // --- the drag ------------------------------------------------------------
  // Pointer events with the pointer captured and touch-action:none pre-set in
  // CSS (iOS ignores a touch-action change made mid-gesture), so a drag moves
  // the picture instead of scrolling the page under it.
  const clamp = (v, hi) => Math.max(0, Math.min(hi, v));
  let grab = null; // where inside the box the finger landed, in output units

  function down(ev) {
    ev.currentTarget.setPointerCapture(ev.pointerId);
    const r = frame.getBoundingClientRect();
    grab = {
      dx: (ev.clientX - r.left) / r.width - box.nx,
      dy: (ev.clientY - r.top) / r.height - box.ny,
    };
    dragging = true;
  }

  function move(ev) {
    if (!dragging) return;
    const r = frame.getBoundingClientRect();
    box = {
      ...box,
      nx: clamp((ev.clientX - r.left) / r.width - grab.dx, 1 - box.nw),
      ny: clamp((ev.clientY - r.top) / r.height - grab.dy, 1 - box.nh),
    };
    livePlace();
  }

  function up() {
    if (!dragging) return;
    dragging = false;
    if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
    // The authoritative one: it snaps, and its answer is what the rectangle
    // settles to, so the phone and the television agree at the end of a drag.
    place({ nx: box.nx, ny: box.ny });
  }

  // At most one place per 50ms while the finger moves (a pointermove stream is
  // far faster than that), each carrying the latest position. snap is off
  // mid-drag so the picture cannot jump out from under the finger.
  const SEND_MS = 50;
  let liveTimer = null;
  function livePlace() {
    if (liveTimer) return;
    liveTimer = setTimeout(() => {
      liveTimer = null;
      if (dragging) place({ nx: box.nx, ny: box.ny, snap: false });
    }, SEND_MS);
  }

  // Arrow keys for anyone driving this with a keyboard; same 2% step as a nudge.
  function onKeydown(ev) {
    const step = { ArrowLeft: [-0.02, 0], ArrowRight: [0.02, 0], ArrowUp: [0, -0.02], ArrowDown: [0, 0.02] }[ev.key];
    if (!step) return;
    ev.preventDefault();
    box = { ...box, nx: clamp(box.nx + step[0], 1 - box.nw), ny: clamp(box.ny + step[1], 1 - box.nh) };
    place({ nx: box.nx, ny: box.ny, snap: false });
  }

  // --- size, fade, corners -------------------------------------------------
  let sizeTimer = null;
  let sizeIdle = null;
  function setSize(ev) {
    const nw = Number(ev.target.value) / 100;
    sizing = true;
    clearTimeout(sizeIdle);
    sizeIdle = setTimeout(() => { sizing = false; }, 700);
    // Grow the local rectangle about its own top left, keeping its shape, and
    // hold it inside the screen on the way - a box that grows off the edge for
    // the length of a round trip reads as a bug. pipd clamps too, and its
    // answer corrects whatever this got slightly wrong.
    const nh = box.nh * (nw / box.nw);
    box = { nw, nh, nx: clamp(box.nx, 1 - nw), ny: clamp(box.ny, 1 - nh) };
    sizePct = Math.round(nw * 100);
    clearTimeout(sizeTimer);
    sizeTimer = setTimeout(() => place({ nx: box.nx, ny: box.ny, nw }), 120);
  }

  let opTimer = null;
  let opIdle = null;
  function setOpacity(ev) {
    const value = Number(ev.target.value);
    fading = true;
    clearTimeout(opIdle);
    opIdle = setTimeout(() => { fading = false; }, 700);
    opPct = value;
    clearTimeout(opTimer);
    opTimer = setTimeout(async () => {
      try { adopt(await api('/api/pip/opacity', { value: value / 100 })); } catch { /* toasted */ }
    }, 120);
  }

  const CORNERS = [
    { where: 'nw', label: 'Top left' },
    { where: 'ne', label: 'Top right' },
    { where: 'sw', label: 'Bottom left' },
    { where: 'se', label: 'Bottom right' },
  ];

  async function corner(where) {
    try { adopt(await api('/api/pip/corner', { where })); } catch { /* toasted */ }
  }

  async function toggleVisible() {
    try { adopt(await api(visible ? '/api/pip/hide' : '/api/pip/show', {})); } catch { /* toasted */ }
  }

  async function stop() {
    if (!confirm('Close the picture? It cannot be opened again from the phone yet.')) return;
    try { adopt(await api('/api/pip/stop', {})); } catch { /* toasted */ }
    setTimeout(load, 400);
  }
</script>

<div class="card">
  <div class="row head">
    <h2 class="grow">Picture in picture</h2>
    {#if running}
      <button class="vis" class:primary={visible} onclick={toggleVisible}>{visible ? 'On screen' : 'Hidden'}</button>
    {/if}
  </div>

  {#if !running}
    <p class="dim small note">
      Nothing is floating over the TV. The little window turns up while a video is
      playing over a game, and then you can drag it around from here.
    </p>
  {:else}
    <div class="tv" bind:this={frame} data-nopull>
      <div
        class="pic"
        class:dragging
        class:off={!visible}
        style:left={box.nx * 100 + '%'}
        style:top={box.ny * 100 + '%'}
        style:width={box.nw * 100 + '%'}
        style:height={box.nh * 100 + '%'}
        style:opacity={Math.max(0.25, opPct / 100)}
        onpointerdown={down}
        onpointermove={move}
        onpointerup={up}
        onpointercancel={up}
        onkeydown={onKeydown}
        role="button"
        tabindex="0"
        aria-label="Drag to move the picture on the TV"
      >
        <Icon name="play" size={13} />
      </div>
    </div>

    <p class="hint dim small">
      {mediaName || 'Drag the small window to move it on the TV.'}
    </p>

    <div class="corners">
      {#each CORNERS as c (c.where)}
        <button class="small" onclick={() => corner(c.where)}>{c.label}</button>
      {/each}
    </div>

    <div class="row slider">
      <span class="lab small dim">Size</span>
      <input class="grow" type="range" min="8" max="75" value={sizePct} oninput={setSize} />
      <span class="mono small dim val">{sizePct}%</span>
    </div>

    <div class="row slider">
      <span class="lab small dim">Fade</span>
      <input class="grow" type="range" min="20" max="100" value={opPct} oninput={setOpacity} />
      <span class="mono small dim val">{opPct}%</span>
    </div>

    <button class="danger close" onclick={stop}>Close the picture</button>
  {/if}
</div>

<style>
  .head { margin-bottom: 10px; }
  .head h2 { margin: 0; }
  .vis { padding: 7px 12px; }
  .note { margin: 0; }

  /* The television. Same treatment as the live screen viewport so the two read
     as the same kind of object. */
  .tv {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: #000;
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
    touch-action: none;
  }
  /* touch-action must be pre-set, not toggled when the drag starts: iOS reads
     it once, at the first touch. */
  .pic {
    position: absolute;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--on-accent);
    background: var(--accent);
    border-radius: 6px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.45);
    touch-action: none;
    cursor: grab;
    user-select: none;
    -webkit-user-select: none;
    transition: box-shadow 0.13s ease;
  }
  /* At the smallest size pipd allows, the rectangle is about 26x15 on a phone,
     which is well under a thumb. The grab area is grown past the drawn box so
     the small picture is still catchable; a pseudo-element keeps the picture
     itself honest about the size it represents. */
  .pic::after {
    content: '';
    position: absolute;
    inset: -11px;
  }
  .pic.dragging {
    cursor: grabbing;
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.6);
  }
  .pic.off {
    background: var(--raise);
    color: var(--muted);
    border: 1px dashed var(--faint);
  }

  .hint {
    margin: 8px 0 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .corners {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  .slider { margin-top: 10px; }
  .lab { width: 34px; flex: none; }
  .val { width: 38px; text-align: right; flex: none; }

  .close { width: 100%; margin-top: 12px; }
</style>
