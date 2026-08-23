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

  // pipd lives only as long as one picture, so absent is the ordinary state and
  // gets said plainly. Since 22 Aug the phone can end that state itself: the
  // picker below browses the video library and starts a daemon on what it picks.
  let pip = $state(null);
  let frame; // the TV rectangle, the reference for every drag
  let dragging = $state(false);
  let sizing = false; // a finger is on the size slider
  let fading = false; // ...or the fade one

  let box = $state({ nx: 0.66, ny: 0.05, nw: 0.3, nh: 0.17 });
  let sizePct = $state(30);
  let opPct = $state(100);
  let volPct = $state(100);
  let voling = false; // a finger is on the volume slider
  let scrubbing = $state(false); // ...or on the seek bar
  let scrubPct = $state(0);
  // Held for a moment after a release: mpv's absolute seek is asynchronous, so
  // the status that comes straight back still reports the OLD position and the
  // thumb would snap backwards for one poll. Cleared once the daemon agrees.
  let heldPos = $state(null);

  const running = $derived(pip?.running === true);
  const visible = $derived(pip?.visible !== false);
  // A daemon that reports paused is one that can be told to pause; an older
  // pipd simply never grows the transport row.
  const hasTransport = $derived(typeof pip?.paused === 'boolean');
  const paused = $derived(pip?.paused === true);
  const muted = $derived(pip?.muted === true);
  const pos = $derived(typeof pip?.position === 'number' ? pip.position : null);
  const dur = $derived(typeof pip?.duration === 'number' ? pip.duration : null);
  const seekable = $derived(pos !== null && dur !== null && dur > 0);
  // Where the finger is, in seconds, while it is down.
  const scrubSecs = $derived((scrubPct / 100) * (dur || 0));
  // The position the bar draws: the finger while dragging, the spot just
  // seeked to for the settle window after a release, otherwise the daemon's.
  const shownPos = $derived(scrubbing ? scrubSecs : (heldPos ?? pos ?? 0));
  const pct = $derived(dur ? Math.max(0, Math.min(100, (shownPos / dur) * 100)) : 0);
  const displayPct = $derived(scrubbing ? scrubPct : pct);
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
    if (typeof d.volume === 'number' && !voling) volPct = Math.round(d.volume);
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
      if (document.visibilityState === 'visible' && !dragging && !scrubbing) load();
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

  // --- transport -----------------------------------------------------------
  async function transport(path, body = {}) {
    try { adopt(await api(`/api/pip/${path}`, body)); } catch { /* toasted */ }
  }

  // The seek bar. Same shape as the Playing tab's scrubber, and for the same
  // reasons: a native <input type=range> has no touch-action, so a vertical
  // wobble scrolls the page instead of seeking, its thumb is a tiny target, and
  // its value is rewritten from underneath by every status poll. This owns the
  // pointer (setPointerCapture), draws the finger's position rather than the
  // daemon's, and the 4s poll is held off while it is down, exactly as sizing,
  // fading and voling hold off the sliders.
  const pctAt = (ev, el) => {
    const r = el.getBoundingClientRect();
    return Math.max(0, Math.min(100, ((ev.clientX - r.left) / r.width) * 100));
  };

  // A live seek at most every 300ms, so the picture scrubs ALONG with the drag
  // (mpv redraws where you are going) without a socket round trip per pixel.
  const SEEK_MS = 300;
  let seekTimer = null;
  let heldTimer = null;
  function liveSeek() {
    if (seekTimer) return;
    seekTimer = setTimeout(() => {
      seekTimer = null;
      if (scrubbing) transport('seek', { to: scrubSecs });
    }, SEEK_MS);
  }

  function seekDown(ev) {
    if (!seekable) return;
    ev.currentTarget.setPointerCapture(ev.pointerId);
    scrubbing = true;
    scrubPct = pctAt(ev, ev.currentTarget);
    liveSeek();
  }
  function seekMove(ev) {
    if (!scrubbing) return;
    scrubPct = pctAt(ev, ev.currentTarget);
    liveSeek();
  }
  function seekUp(ev) {
    if (!scrubbing) return;
    scrubPct = pctAt(ev, ev.currentTarget);
    const to = scrubSecs;
    scrubbing = false;
    if (seekTimer) { clearTimeout(seekTimer); seekTimer = null; }
    seekSettle(to, { to });
  }

  // Hold the asked-for spot, seek, then read the daemon again once mpv has
  // actually moved. Without the re-read the bar would sit on a stale position
  // until the 4s poll came round, which reads as the seek not having worked.
  async function seekSettle(target, body) {
    heldPos = Math.max(0, Math.min(dur ?? Infinity, target));
    clearTimeout(heldTimer);
    await transport('seek', body);
    heldTimer = setTimeout(async () => { await load(); heldPos = null; }, 400);
  }

  // The -10s/+30s buttons move off wherever the picture actually is, so they
  // get the same settle treatment as a released thumb.
  const nudge = (seconds) => seekSettle((shownPos ?? 0) + seconds, { seconds });

  let volTimer = null;
  let volIdle = null;
  function setVolume(ev) {
    const value = Number(ev.target.value);
    voling = true;
    clearTimeout(volIdle);
    volIdle = setTimeout(() => { voling = false; }, 700);
    volPct = value;
    clearTimeout(volTimer);
    volTimer = setTimeout(() => transport('volume', { value }), 120);
  }

  // 22:10 for the sofa, 1:02:10 when a film ends up in the corner.
  function fmt(s) {
    const t = Math.max(0, Math.round(s));
    const m = Math.floor(t / 60) % 60;
    const sec = String(t % 60).padStart(2, '0');
    const h = Math.floor(t / 3600);
    return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
  }

  async function stop() {
    if (!confirm('Close the picture? You can put another one up from here after.')) return;
    try { adopt(await api('/api/pip/stop', {})); } catch { /* toasted */ }
    setTimeout(load, 400);
  }

  // --- the picker ----------------------------------------------------------
  // Films are one flat list; shows are three steps (show, season, episode).
  // Each step is fetched when it is opened rather than all at once, because a
  // season of episodes costs the server a path lookup per episode and nobody
  // browsing a list of show names needs any of them yet.
  let picking = $state(false);
  let lib = $state(null); // { movies, shows }
  let libBusy = $state(false);
  let kind = $state('films');
  let filter = $state('');
  let show = $state(null);
  let seasons = $state(null);
  let season = $state(null);
  let episodes = $state(null);
  let starting = $state(''); // the path being started, so its row can say so

  const needle = $derived(filter.trim().toLowerCase());
  const match = (t) => !needle || String(t).toLowerCase().includes(needle);
  const films = $derived((lib?.movies || []).filter((m) => match(m.title)));
  const shows = $derived((lib?.shows || []).filter((s) => match(s.title)));

  async function openPicker() {
    picking = true;
    if (lib || libBusy) return;
    libBusy = true;
    // api() rather than a bare fetch here: unlike the background poll, this is
    // a tap, and a library that will not load is worth a toast.
    try { lib = await api('/api/pip/library'); } catch { picking = false; }
    finally { libBusy = false; }
  }

  function closePicker() {
    picking = false;
    show = null;
    season = null;
  }

  function back() {
    if (season !== null) season = null;
    else show = null;
  }

  async function openShow(s) {
    show = s;
    season = null;
    episodes = null;
    seasons = null;
    try { seasons = (await api(`/api/pip/library/seasons?show=${s.id}`)).seasons; }
    catch { show = null; }
  }

  async function openSeason(n) {
    season = n;
    episodes = null;
    try { episodes = (await api(`/api/pip/library/episodes?show=${show.id}&season=${n}`)).episodes; }
    catch { season = null; }
  }

  // The server holds this one open while pipd creates its overlay and forks a
  // player, so it is a second or two, not a round trip. The row says "Starting"
  // for the whole of it and every other row is disabled, because two pictures
  // is a state with no way back from the phone.
  async function startPip(path) {
    if (!path || starting) return;
    starting = path;
    try {
      adopt(await api('/api/pip/start', { path }));
      closePicker();
      filter = '';
    } catch { /* the toast has it */ }
    finally { starting = ''; }
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
    {#if !picking}
      <p class="dim small note">
        Nothing is floating over the TV. Pick something and it turns up in the
        corner of the screen, and then you can drag it around from here.
      </p>
      <button class="primary put" onclick={openPicker}>Put something on</button>
    {:else}
      <div class="row crumbs">
        {#if show}
          <button class="small" onclick={back} aria-label="Back">
            <Icon name="back" size={14} />
          </button>
          <span class="grow small crumb">
            {show.title}{season !== null ? `, season ${season}` : ''}
          </span>
        {:else}
          <div class="row grow kinds">
            <button class="small grow" class:primary={kind === 'films'}
                    onclick={() => { kind = 'films'; }}>Films</button>
            <button class="small grow" class:primary={kind === 'shows'}
                    onclick={() => { kind = 'shows'; }}>TV shows</button>
          </div>
        {/if}
        <button class="small" onclick={closePicker}>Cancel</button>
      </div>

      {#if libBusy}
        <p class="dim small note">Reading the library.</p>
      {:else if show && season === null}
        {#if !seasons}
          <p class="dim small note">Reading the seasons.</p>
        {:else}
          <div class="list" data-nopull>
            {#each seasons as s (s.season)}
              <button class="pick" onclick={() => openSeason(s.season)}>
                <span class="grow">{s.label}</span>
                <span class="dim small">{s.episodes}</span>
              </button>
            {/each}
          </div>
        {/if}
      {:else if show}
        {#if !episodes}
          <p class="dim small note">Reading the episodes.</p>
        {:else}
          <div class="list" data-nopull>
            {#each episodes as e (e.id)}
              <button class="pick" disabled={!e.path || !!starting} onclick={() => startPip(e.path)}>
                <span class="mono small dim num">{e.episode}</span>
                <span class="grow">{e.title}</span>
                {#if starting === e.path}
                  <span class="dim small">Starting</span>
                {:else if !e.path}
                  <span class="dim small">No file</span>
                {/if}
              </button>
            {/each}
          </div>
        {/if}
      {:else}
        <input class="find" type="text" bind:value={filter}
               placeholder={kind === 'films' ? 'Find a film' : 'Find a show'} />
        <div class="list" data-nopull>
          {#if kind === 'films'}
            {#each films as m (m.id)}
              <button class="pick" disabled={!m.path || !!starting} onclick={() => startPip(m.path)}>
                <span class="grow">{m.title}</span>
                {#if starting === m.path}
                  <span class="dim small">Starting</span>
                {:else if !m.path}
                  <span class="dim small">No file</span>
                {:else if m.year}
                  <span class="dim small">{m.year}</span>
                {/if}
              </button>
            {/each}
            {#if !films.length}
              <p class="dim small note">Nothing here by that name.</p>
            {/if}
          {:else}
            {#each shows as s (s.id)}
              <button class="pick" onclick={() => openShow(s)}>
                <span class="grow">{s.title}</span>
                {#if s.year}<span class="dim small">{s.year}</span>{/if}
              </button>
            {/each}
            {#if !shows.length}
              <p class="dim small note">Nothing here by that name.</p>
            {/if}
          {/if}
        </div>
      {/if}
    {/if}
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

    {#if hasTransport}
      {#if seekable}
        <div
          class="seekbar"
          class:dragging={scrubbing}
          data-nopull
          onpointerdown={seekDown}
          onpointermove={seekMove}
          onpointerup={seekUp}
          onpointercancel={seekUp}
          role="slider"
          tabindex="0"
          aria-label="Seek the picture"
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
          <span>{fmt(shownPos)}</span>
          <span class="grow"></span>
          <span class="dim">{fmt(dur)}</span>
        </div>
      {/if}

      <div class="row transport">
        <button class="small grow" onclick={() => nudge(-10)}>-10s</button>
        <button class="primary playpause" onclick={() => transport(paused ? 'play' : 'pause')}
                aria-label={paused ? 'Play' : 'Pause'}>
          <Icon name={paused ? 'play' : 'pause'} size={16} />
        </button>
        <button class="small grow" onclick={() => nudge(30)}>+30s</button>
      </div>

      <div class="row slider">
        <span class="lab small dim">Vol</span>
        <input class="grow" type="range" min="0" max="100" value={volPct} oninput={setVolume} />
        <button class="small mute" class:primary={muted} onclick={() => transport('mute', { value: !muted })}>
          {muted ? 'Muted' : 'Mute'}
        </button>
      </div>
    {/if}

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

  .transport {
    gap: 8px;
    margin: 0 0 10px;
  }
  .playpause {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 52px;
    padding: 8px 0;
  }
  .mute { flex: none; width: 62px; }

  /* The seek bar, same construction as the Playing tab's: a thin track inside
     a tall padded touch target, and touch-action:none set in CSS rather than
     when the gesture starts, because iOS reads it once, at the first touch. */
  .seekbar {
    position: relative;
    padding: 14px 0 12px;
    margin: 0 2px;
    touch-action: none;
    cursor: pointer;
    user-select: none;
    -webkit-user-select: none;
  }
  .seektrack {
    position: relative;
    height: 6px;
    border-radius: 999px;
    background: var(--raise);
  }
  .seekfill {
    position: absolute;
    top: 0; left: 0; bottom: 0;
    border-radius: 999px;
    background: var(--accent);
  }
  .seekthumb {
    position: absolute;
    top: 50%;
    width: 16px; height: 16px;
    margin: -8px 0 0 -8px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.45);
  }
  /* Never a transition while dragging: the thumb has to track the finger. */
  .seekbar.dragging .seekthumb { transform: scale(1.35); }
  .times { margin: 0 2px 10px; }

  .corners {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  .slider { margin-top: 10px; }
  .lab { width: 34px; flex: none; }
  .val { width: 38px; text-align: right; flex: none; }

  .close { width: 100%; margin-top: 12px; }

  /* The picker. A phone-sized list: rows the width of the card, left aligned
     (the global button centres its content, which reads as a dialog rather
     than a list), and capped in height so a 90-title library scrolls inside
     the card instead of pushing the rest of the tab off the screen. */
  .put { width: 100%; margin-top: 12px; }
  .crumbs { margin-bottom: 10px; }
  .kinds { gap: 8px; }
  .crumb {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .find { margin-bottom: 8px; }

  .list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 46vh;
    overflow-y: auto;
    overscroll-behavior: contain;
    -webkit-overflow-scrolling: touch;
  }
  .pick {
    justify-content: flex-start;
    text-align: left;
    padding: 10px 12px;
    flex: none;
  }
  .pick .grow {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .num { width: 22px; flex: none; text-align: right; }
</style>
