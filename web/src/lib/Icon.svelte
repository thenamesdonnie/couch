<script>
  // One icon set for the whole app: Lucide-style 24-unit strokes, plus a few
  // filled transport shapes where solid reads better at small sizes.
  let { name, size = 18 } = $props();

  const STROKE = {
    'chevron-up': 'm18 15-6-6-6 6',
    'chevron-down': 'm6 9 6 6 6-6',
    'chevron-left': 'm15 18-6-6 6-6',
    'chevron-right': 'm9 18 6-6-6-6',
    back: 'M9 14 4 9l5-5 M4 9h10.5a5.5 5.5 0 0 1 0 11H11',
    home: 'M3 10.6 12 3l9 7.6 M5 10.4V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9.6',
    sliders: 'M21 4h-7 M10 4H3 M21 12h-9 M8 12H3 M21 20h-5 M12 20H3 M14 2v4 M8 10v4 M16 18v4',
    'rotate-ccw': 'M3 12a9 9 0 1 0 2.83-6.54L3 8 M3 3v5h5',
    'rotate-cw': 'M21 12a9 9 0 1 1-2.83-6.54L21 8 M21 3v5h-5',
    check: 'M20 6 9 17l-5-5',
    x: 'M18 6 6 18 M6 6l12 12',
    plus: 'M12 5v14 M5 12h14',
    minus: 'M5 12h14',
    fit: 'M8 3H5a2 2 0 0 0-2 2v3 M16 3h3a2 2 0 0 1 2 2v3 M16 21h3a2 2 0 0 0 2-2v-3 M8 21H5a2 2 0 0 1-2-2v-3',
    backspace: 'M20 5H9.5a2 2 0 0 0-1.5.68L3.6 11a1.5 1.5 0 0 0 0 2L8 18.32A2 2 0 0 0 9.5 19H20a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2Z M12 9.5l5 5 M17 9.5l-5 5',
    keyboard: 'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z M7 15h10 M7 9h.01 M11 9h.01 M15 9h.01 M7 12h.01 M11 12h.01 M15 12h.01 M19 9h-.01 M19 12h-.01',
    esc: 'M9 6 3 12l6 6 M21 12H3.5',
    dots: 'M5 12h.01 M12 12h.01 M19 12h.01',
    power: 'M12 2v9 M18.4 6.6a9 9 0 1 1-12.8 0',
    gamepad: 'M7 8h10a4 4 0 0 1 3.9 4.9l-.7 3a2.4 2.4 0 0 1-4.3.7L14 14h-4l-1.9 2.6a2.4 2.4 0 0 1-4.3-.7l-.7-3A4 4 0 0 1 7 8Z M8 11v2 M7 12h2 M15.5 11.5h.01 M17 13h.01',
    speaker: 'M11 5 6 9H2v6h4l5 4V5Z M15.5 8.5a5 5 0 0 1 0 7 M19 5a9 9 0 0 1 0 14',
    'speaker-off': 'M11 5 6 9H2v6h4l5 4V5Z M22 9l-6 6 M16 9l6 6',
  };

  const FILL = {
    play: 'M7.5 4.6c0-1.2 1.3-1.9 2.3-1.3l11 6.9c1 .6 1 2 0 2.6l-11 6.9c-1 .6-2.3-.1-2.3-1.3V4.6Z',
    pause: 'M6.5 4.5A1.5 1.5 0 0 1 8 3h1.5A1.5 1.5 0 0 1 11 4.5v15A1.5 1.5 0 0 1 9.5 21H8a1.5 1.5 0 0 1-1.5-1.5v-15Zm6.5 0A1.5 1.5 0 0 1 14.5 3H16a1.5 1.5 0 0 1 1.5 1.5v15A1.5 1.5 0 0 1 16 21h-1.5a1.5 1.5 0 0 1-1.5-1.5v-15Z',
    stop: 'M5.5 7A1.5 1.5 0 0 1 7 5.5h10A1.5 1.5 0 0 1 18.5 7v10a1.5 1.5 0 0 1-1.5 1.5H7A1.5 1.5 0 0 1 5.5 17V7Z',
    prev: 'M18.7 4.3c1-.6 2.3.1 2.3 1.3v12.8c0 1.2-1.3 1.9-2.3 1.3L8.5 13.3a1.5 1.5 0 0 1 0-2.6L18.7 4.3ZM3 5.5A1.5 1.5 0 0 1 4.5 4h.2A1.5 1.5 0 0 1 6.2 5.5v13A1.5 1.5 0 0 1 4.7 20h-.2A1.5 1.5 0 0 1 3 18.5v-13Z',
    next: 'M5.3 4.3C4.3 3.7 3 4.4 3 5.6v12.8c0 1.2 1.3 1.9 2.3 1.3l10.2-6.4a1.5 1.5 0 0 0 0-2.6L5.3 4.3ZM17.8 5.5A1.5 1.5 0 0 1 19.3 4h.2A1.5 1.5 0 0 1 21 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-.2a1.5 1.5 0 0 1-1.5-1.5v-13Z',
  };
</script>

{#if FILL[name]}
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path d={FILL[name]} fill="currentColor" />
  </svg>
{:else}
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"
    fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d={STROKE[name] || ''} />
  </svg>
{/if}
